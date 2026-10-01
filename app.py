"""Web đọc bài:  uvicorn app:app --reload"""
import base64
import json
import logging
import re
import secrets
import threading
from contextlib import asynccontextmanager

import markdown
import nh3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import config
import db
import fetcher
import llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="Đọc gì hôm nay", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=config.BASE_DIR / "templates")

_translating: set[int] = set()
_translating_lock = threading.Lock()


# ---------- Basic auth ----------

def _auth_ok(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    return (secrets.compare_digest(user.encode(), config.AUTH_USER.encode())
            and secrets.compare_digest(pw.encode(), config.AUTH_PASS.encode()))


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    # /healthz: health check. /admin/import: gọi từ extension trình duyệt (không phải
    # form trên chính app), tự xác thực riêng bằng X-Import-Token thay vì Basic Auth.
    # /favicon.ico: một số trình duyệt (Safari) tự fetch path này mà không gửi kèm
    # Authorization header, nên để sau Basic Auth thì icon sẽ không bao giờ hiện được.
    if request.url.path in ("/healthz", "/admin/import", "/favicon.ico"):
        return await call_next(request)
    if not (config.AUTH_USER and config.AUTH_PASS):
        if config.ON_RAILWAY:  # fail closed: không lộ app + API key ra internet
            return Response("Chưa đặt BASIC_AUTH_USER / BASIC_AUTH_PASS.", status_code=503)
        return await call_next(request)
    if _auth_ok(request.headers.get("authorization", "")):
        # Chặn CSRF: trình duyệt tự gửi basic auth kèm request từ trang khác
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin.split("://")[-1] != request.headers.get("host"):
            return Response("Sai nguồn gửi request.", status_code=403)
        return await call_next(request)
    return Response("Cần đăng nhập.", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="reader", charset="UTF-8"'})


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.BASE_DIR / "static" / "favicon.ico")


class ImportIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    author: str = Field(default="", max_length=200)
    html: str = Field(min_length=1, max_length=500_000)


@app.post("/admin/import")
def admin_import(body: ImportIn, request: Request):
    # Đưa bài bạn đang đọc trên trình duyệt (vd. bài Medium member-only, đã mở bằng
    # tài khoản trả phí của bạn) vào app qua extension. Không tự động truy cập Medium.
    if not config.IMPORT_TOKEN:
        raise HTTPException(503, "Chưa đặt IMPORT_TOKEN trên server.")
    token = request.headers.get("x-import-token", "")
    if not secrets.compare_digest(token.encode(), config.IMPORT_TOKEN.encode()):
        raise HTTPException(401, "Sai import token.")

    md = fetcher.html_to_markdown_full(body.html)
    words = len(md.split())
    url = fetcher.clean_url(body.url)
    title = body.title.strip()
    try:
        summary_en = llm.summarize_article(title, md)
    except Exception:
        log.exception("Tóm tắt lỗi khi import %s", url)
        summary_en = None
    with db.conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO articles (url, title, author, content_en, summary_en, word_count, status)
               VALUES (?, ?, ?, ?, ?, ?, 'new')""",
            (url, title, body.author.strip(), md, summary_en, words),
        )
        if cur.rowcount == 0:
            return {"ok": False, "reason": "Bài đã có trong hệ thống."}
    return {"ok": True, "words": words}


def render_md(text: str | None) -> str:
    html = markdown.markdown(text or "", extensions=["fenced_code", "tables"])
    return nh3.clean(html)  # nội dung đến từ bên ngoài => luôn sanitize


def fmt_date(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


templates.env.filters["date"] = fmt_date


@app.get("/")
def index(request: Request):
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM articles ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    with _translating_lock:
        translating_ids = set(_translating)
    return templates.TemplateResponse(request, "index.html", {
        "articles": rows,
        "translating_ids": translating_ids,
    })


def _translate_one(article_id: int) -> None:
    with _translating_lock:
        if article_id in _translating:
            return
        _translating.add(article_id)
    try:
        with db.conn() as c:
            a = c.execute("SELECT title, content_en, summary_en FROM articles WHERE id=?",
                          (article_id,)).fetchone()
        if not a:
            return
        content_vi = llm.translate_markdown(a["content_en"])
        title_vi, summary_vi = a["title"], a["summary_en"]
        try:
            ts = llm.translate_title_summary(a["title"], a["summary_en"] or "")
            title_vi, summary_vi = ts["title_vi"], ts.get("summary_vi") or summary_vi
        except Exception:
            log.exception("Dịch title/summary lỗi #%d (vẫn dùng bản gốc)", article_id)
        with db.conn() as c:
            c.execute(
                """UPDATE articles SET status='translated', content_vi=?, title_vi=?, summary_vi=?
                   WHERE id=?""",
                (content_vi, title_vi, summary_vi, article_id),
            )
        log.info("Đã dịch #%d", article_id)
    except Exception:
        log.exception("Dịch lỗi #%d", article_id)
        with db.conn() as c:
            c.execute("UPDATE articles SET status='failed' WHERE id=?", (article_id,))
    finally:
        with _translating_lock:
            _translating.discard(article_id)


@app.post("/admin/translate/{article_id}")
def admin_translate_one(article_id: int):
    with db.conn() as c:
        a = c.execute("SELECT id FROM articles WHERE id=?", (article_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Không tìm thấy bài viết")
    threading.Thread(target=_translate_one, args=(article_id,), daemon=True).start()
    return {"ok": True}


class TranslateBatchIn(BaseModel):
    article_ids: list[int] = Field(min_length=1, max_length=200)


@app.post("/admin/translate-batch")
def admin_translate_batch(body: TranslateBatchIn):
    with db.conn() as c:
        placeholders = ",".join("?" * len(body.article_ids))
        rows = c.execute(
            f"""SELECT id FROM articles WHERE id IN ({placeholders})
                AND status != 'translated'""",
            body.article_ids,
        ).fetchall()
    with _translating_lock:
        ids = [r["id"] for r in rows if r["id"] not in _translating]
    for article_id in ids:
        threading.Thread(target=_translate_one, args=(article_id,), daemon=True).start()
    return {"ok": True, "count": len(ids)}


@app.get("/a/{article_id}")
def article(request: Request, article_id: int):
    with db.conn() as c:
        a = c.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Không tìm thấy bài viết")
    return templates.TemplateResponse(request, "article.html", {
        "a": a,
        "html_vi": render_md(a["content_vi"]),
        "html_en": render_md(a["content_en"]),
    })


class ExplainIn(BaseModel):
    term: str = Field(min_length=1, max_length=100)
    context: str = Field(default="", max_length=3000)
    article_id: int


def term_key(term: str) -> str:
    t = re.sub(r"\s+", " ", term).strip().strip(".,;:!?\"'()[]“”‘’").lower()
    return t


@app.post("/api/explain")
def explain(body: ExplainIn):
    key = term_key(body.term)
    if not key:
        raise HTTPException(400, "Thuật ngữ trống")
    with db.conn() as c:
        hit = c.execute("SELECT data FROM explanations WHERE term_key=? AND article_id=?",
                        (key, body.article_id)).fetchone()
        if hit:
            return json.loads(hit["data"])
        a = c.execute("SELECT title FROM articles WHERE id=?", (body.article_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Không tìm thấy bài viết")
    try:
        data = llm.explain_term(body.term, body.context, a["title"])
    except Exception:
        raise HTTPException(502, "Model không phản hồi. Thử lại sau vài giây.")
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO explanations (term_key, article_id, data) VALUES (?,?,?)",
                  (key, body.article_id, json.dumps(data, ensure_ascii=False)))
    return data
