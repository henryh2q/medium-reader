"""Web đọc bài:  uvicorn app:app --reload"""
import base64
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager

import markdown
import nh3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import config
import db
import fetcher
import llm
import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    scheduler.start()
    yield


app = FastAPI(title="Đọc gì hôm nay", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=config.BASE_DIR / "templates")


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
    if request.url.path in ("/healthz", "/admin/import"):
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


@app.post("/admin/run")
def admin_run():
    started = scheduler.run_now()
    return RedirectResponse("/?run=started" if started else "/?run=busy", status_code=303)


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
    with db.conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO articles
               (url, title, author, feed, content_en, word_count, partial, status)
               VALUES (?, ?, ?, 'manual-import', ?, ?, 0, 'new')""",
            (url, body.title.strip(), body.author.strip(), md, words),
        )
        if cur.rowcount == 0:
            return {"ok": False, "reason": "Bài đã có trong hệ thống."}
    return {"ok": True, "words": words}


def render_md(text: str | None) -> str:
    html = markdown.markdown(text or "", extensions=["fenced_code", "tables"])
    return nh3.clean(html)  # nội dung đến từ RSS/model => luôn sanitize


def fmt_date(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def fmt_datetime(iso: str | None) -> str:
    if not iso:
        return ""
    date, _, time = iso.partition(" ")
    return f"{date[8:10]}/{date[5:7]}/{date[:4]} {time[:5]}"


templates.env.filters["date"] = fmt_date
templates.env.filters["datetime"] = fmt_datetime


@app.get("/")
def index(request: Request):
    with db.conn() as c:
        rows = c.execute(
            """SELECT id, url, title, title_vi, tldr_vi, author, published, score, partial, status
               FROM articles WHERE status IN ('translated', 'scored')
               ORDER BY COALESCE(published, created_at) DESC LIMIT 100"""
        ).fetchall()
        stats = c.execute("SELECT * FROM run_stats WHERE id=1").fetchone()
    return templates.TemplateResponse(request, "index.html", {
        "articles": rows,
        "running": scheduler.is_running(),
        "run": request.query_params.get("run"),
        "stats": stats,
    })


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
