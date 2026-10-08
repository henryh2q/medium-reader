"""Web đọc bài:  uvicorn app:app --reload"""
import base64
import io
import json
import logging
import re
import secrets
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import markdown
import nh3
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import categories
import config
import db
import emailer
import fetcher
import llm
import search

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


def public_base(request: Request) -> str:
    """URL gốc công khai của app. Ưu tiên PUBLIC_URL (đặt đúng https thủ công) vì
    Railway (và proxy nói chung) terminate TLS trước khi request tới app — request.url
    thấy scheme là http dù người dùng thực sự vào bằng https."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL.rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{scheme}://{request.url.netloc}"


templates.env.globals["public_base"] = public_base


# ---------- Basic Auth riêng cho /admin/* ----------

def _admin_auth_ok(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    return (secrets.compare_digest(user.encode(), config.ADMIN_USER.encode())
            and secrets.compare_digest(pw.encode(), config.ADMIN_PASS.encode()))


# Các route /admin/* công khai, không qua Basic Auth admin:
# - /admin/import: xác thực riêng bằng X-Import-Token (extension của bất kỳ ai được
#   cấp token qua /submit, không phải chỉ admin).
# - /admin/translate*: nút "Dịch" trên trang chủ công khai gọi, ai xem trang cũng
#   bấm được — không phải thao tác quản trị dù tiền tố path là /admin/.
ADMIN_PUBLIC_PREFIXES = ("/admin/import", "/admin/translate")


@app.middleware("http")
async def admin_auth(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/admin/") or path.startswith(ADMIN_PUBLIC_PREFIXES):
        return await call_next(request)
    if not (config.ADMIN_USER and config.ADMIN_PASS):
        return Response("Chưa đặt ADMIN_USER / ADMIN_PASS.", status_code=503)
    if _admin_auth_ok(request.headers.get("authorization", "")):
        return await call_next(request)
    return Response("Cần đăng nhập.", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="admin", charset="UTF-8"'})


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.BASE_DIR / "static" / "favicon.ico")


@app.get("/extension.zip", include_in_schema=False)
def extension_zip():
    # Đóng gói thư mục extension/ ngay khi có request, để trang /submit không phải
    # trỏ sang GitHub (repo có thể để private, không phải ai yêu cầu token cũng vào
    # xem được mã nguồn).
    buf = io.BytesIO()
    ext_dir = config.BASE_DIR / "extension"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in ext_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(Path("extension") / path.relative_to(ext_dir)))
    buf.seek(0)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=doc-gi-hom-nay-extension.zip"},
    )


@app.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request):
    base = public_base(request)
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /submit\n"
        "Disallow: /admin/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request):
    base = public_base(request)
    with db.conn() as c:
        rows = c.execute(
            "SELECT slug, created_at FROM articles WHERE status='translated' ORDER BY created_at DESC"
        ).fetchall()
    urls = [f"<url><loc>{base}/</loc></url>"]
    for r in rows:
        urls.append(
            f"<url><loc>{base}/bai-viet/{r['slug']}</loc>"
            f"<lastmod>{r['created_at'][:10]}</lastmod></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls) + "</urlset>"
    )
    return Response(xml, media_type="application/xml")


class ImportIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    author: str = Field(default="", max_length=200)
    html: str = Field(min_length=1, max_length=3_000_000)
    tags: list[str] = Field(default_factory=list, max_length=10)


def _valid_import_token(token: str) -> bool:
    """Chấp nhận token gốc của chủ site (IMPORT_TOKEN) hoặc bất kỳ token nào đã
    được admin duyệt qua /admin/requests (xem token_requests)."""
    if not token:
        return False
    if config.IMPORT_TOKEN and secrets.compare_digest(token.encode(), config.IMPORT_TOKEN.encode()):
        return True
    with db.conn() as c:
        row = c.execute(
            "SELECT 1 FROM token_requests WHERE status='approved' AND token=?", (token,)
        ).fetchone()
    return row is not None


@app.post("/admin/import")
def admin_import(body: ImportIn, request: Request):
    # Đưa bài bạn đang đọc trên trình duyệt (vd. bài Medium member-only, đã mở bằng
    # tài khoản trả phí của bạn) vào app qua extension. Không tự động truy cập Medium.
    token = request.headers.get("x-import-token", "")
    if not _valid_import_token(token):
        raise HTTPException(401, "Sai import token.")

    md = fetcher.html_to_markdown_full(body.html)
    words = len(md.split())
    url = fetcher.clean_url(body.url)
    title = body.title.strip()
    # Ưu tiên tag thật lấy từ trang (extension đọc được, vd. tag Medium); nếu không
    # có thì để LLM tự sinh 2-3 tag cùng lúc tóm tắt (không tốn thêm lần gọi riêng).
    page_tags = [t.strip() for t in body.tags if t.strip()][:3]
    summary_en = None
    tags = page_tags
    try:
        result = llm.summarize_article(title, md)
        summary_en = result["summary"]
        if not tags:
            tags = result["tags"]
    except Exception:
        log.exception("Tóm tắt lỗi khi import %s", url)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM articles WHERE url=?", (url,)).fetchone():
            _mark_submission_imported(c, url)
            return {"ok": False, "reason": "Bài đã có trong hệ thống."}
        slug = db.make_unique_slug(c, title)
        cur = c.execute(
            """INSERT INTO articles (url, slug, title, author, content_en, summary_en, word_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'new')""",
            (url, slug, title, body.author.strip(), md, summary_en, words),
        )
        article_id = cur.lastrowid
        if tags:
            db.set_article_tags(c, article_id, tags)
        _mark_submission_imported(c, url)
    return {"ok": True, "words": words}


# ---------- Hàng đợi URL (gửi từ mobile, admin xử lý ở PC) ----------

MAX_PENDING_SUBMISSIONS = 500
_SUBMIT_LIMIT = 5          # số lần gửi tối đa mỗi IP...
_SUBMIT_WINDOW = 3600      # ...trong khoảng này (giây)
_submit_hits: dict[str, list[float]] = {}
_submit_lock = threading.Lock()


def queue_key(url: str) -> str:
    """Khoá chuẩn hoá để chống trùng và khớp URL hàng đợi với URL lúc import (bỏ query,
    fragment, dấu / cuối)."""
    return fetcher.clean_url(url).split("#")[0].rstrip("/")


def _mark_submission_imported(c, url: str) -> None:
    c.execute("UPDATE submissions SET status='imported' WHERE url_key=? AND status!='imported'",
              (queue_key(url),))


def _client_ip(request: Request) -> str:
    # Lấy phần tử CUỐI của X-Forwarded-For: proxy của Railway nối IP thật vào cuối, còn
    # các giá trị đứng trước có thể do client tự giả mạo.
    fwd = request.headers.get("x-forwarded-for", "")
    last = fwd.split(",")[-1].strip()
    return last or (request.client.host if request.client else "unknown")


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _submit_lock:
        hits = [t for t in _submit_hits.get(ip, []) if now - t < _SUBMIT_WINDOW]
        limited = len(hits) >= _SUBMIT_LIMIT
        if not limited:
            hits.append(now)
        _submit_hits[ip] = hits
        if len(_submit_hits) > 10_000:  # dọn IP cũ để dict không phình mãi
            for k in [k for k, v in _submit_hits.items() if not v or now - v[-1] >= _SUBMIT_WINDOW]:
                del _submit_hits[k]
    return limited


class SubmissionIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    note: str = Field(default="", max_length=300)


@app.post("/api/submissions")
def create_submission(body: SubmissionIn, request: Request, background: BackgroundTasks):
    url = body.url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or re.search(r"\s", url):
        raise HTTPException(400, "Link không hợp lệ — cần bắt đầu bằng http:// hoặc https://")
    # Chủ site (có import token) không bị giới hạn tần suất.
    if not _valid_import_token(request.headers.get("x-import-token", "")) \
            and _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Bạn gửi quá nhiều link, thử lại sau ít phút.")
    note = body.note.strip()
    key = queue_key(url)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM articles WHERE url IN (?, ?)", (key, key + "/")).fetchone():
            return {"ok": True, "state": "exists", "message": "Bài này đã có trên site rồi."}
        pending = c.execute("SELECT COUNT(*) AS n FROM submissions WHERE status='pending'").fetchone()["n"]
        if pending >= MAX_PENDING_SUBMISSIONS:
            raise HTTPException(503, "Hàng đợi đang đầy, thử lại sau.")
        cur = c.execute("INSERT OR IGNORE INTO submissions (url, url_key, note) VALUES (?, ?, ?)",
                        (url, key, note))
        if cur.rowcount == 0:
            return {"ok": True, "state": "duplicate", "message": "Link này đã được gửi trước đó."}
    background.add_task(emailer.send_submission_notice, url, note)
    return {"ok": True, "state": "queued", "message": "Đã gửi! Admin sẽ xem và đưa bài vào site."}


@app.get("/admin/queue")
def admin_queue_page(request: Request):
    with db.conn() as c:
        pending = c.execute(
            "SELECT * FROM submissions WHERE status='pending' ORDER BY id ASC").fetchall()
        done = c.execute(
            "SELECT * FROM submissions WHERE status!='pending' ORDER BY id DESC LIMIT 50").fetchall()
    return templates.TemplateResponse(request, "admin_queue.html", {"pending": pending, "done": done})


@app.post("/admin/queue/{submission_id}/reject")
def admin_reject_submission(submission_id: int):
    with db.conn() as c:
        cur = c.execute("UPDATE submissions SET status='rejected' WHERE id=? AND status='pending'",
                        (submission_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy link đang chờ")
    return {"ok": True}


# ---------- Yêu cầu cấp token (/submit) ----------

@app.get("/submit")
def submit_page(request: Request):
    return templates.TemplateResponse(request, "submit.html", {})


class TokenRequestIn(BaseModel):
    note: str = Field(default="", max_length=300)


@app.post("/api/token-requests")
def create_token_request(body: TokenRequestIn):
    request_id = str(uuid.uuid4())
    with db.conn() as c:
        c.execute(
            "INSERT INTO token_requests (request_id, note) VALUES (?, ?)",
            (request_id, body.note.strip()),
        )
    emailer.send_token_request_notice(request_id, body.note.strip())
    return {"request_id": request_id}


@app.get("/api/token-requests/{request_id}")
def check_token_request(request_id: str):
    with db.conn() as c:
        row = c.execute(
            "SELECT status, token FROM token_requests WHERE request_id=?", (request_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy yêu cầu")
    return {"status": row["status"], "token": row["token"] if row["status"] == "approved" else None}


@app.get("/admin/requests")
def admin_requests_page(request: Request):
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM token_requests ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return templates.TemplateResponse(request, "admin_requests.html", {"requests": rows})


@app.post("/admin/requests/{request_id}/approve")
def admin_approve_request(request_id: str):
    with db.conn() as c:
        row = c.execute("SELECT status FROM token_requests WHERE request_id=?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy yêu cầu")
        token = secrets.token_urlsafe(24)
        c.execute(
            "UPDATE token_requests SET status='approved', token=? WHERE request_id=?",
            (token, request_id),
        )
    return {"ok": True, "token": token}


# ---------- Báo cáo sự cố / đóng góp ----------

class FeedbackIn(BaseModel):
    kind: str = Field(pattern="^(bug|idea)$")
    message: str = Field(min_length=1, max_length=2000)
    contact: str = Field(default="", max_length=200)


@app.post("/api/feedback")
def submit_feedback(body: FeedbackIn):
    sent = emailer.send_feedback_notice(body.kind, body.message.strip(), body.contact.strip())
    if not sent:
        raise HTTPException(503, "Chưa cấu hình gửi email trên server.")
    return {"ok": True}


def render_md(text: str | None) -> str:
    # Bài import trước đây còn dính nhãn "Member-only story" trong DB: lọc lúc hiển thị.
    html = markdown.markdown(fetcher.strip_ui_noise(text), extensions=["fenced_code", "tables"])
    return nh3.clean(html)  # nội dung đến từ bên ngoài => luôn sanitize


def fmt_date(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def fmt_host(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def home_url(category: str | None = None, tag: str | None = None, q: str | None = None) -> str:
    """URL trang chủ kèm các bộ lọc đang chọn (bỏ giá trị rỗng)."""
    params = {k: v for k, v in (("category", category), ("tag", tag), ("q", q)) if v}
    return "/?" + urlencode(params) if params else "/"


templates.env.filters["date"] = fmt_date
templates.env.filters["highlight"] = search.highlight
templates.env.globals["home_url"] = home_url
templates.env.filters["host"] = fmt_host


@app.get("/")
def index(request: Request, tag: str | None = None, category: str | None = None,
          q: str | None = None):
    with db.conn() as c:
        if tag:
            rows = c.execute(
                """SELECT a.* FROM articles a
                   JOIN article_tags at ON at.article_id = a.id
                   JOIN tags t ON t.id = at.tag_id
                   WHERE t.name = ?
                   ORDER BY a.created_at DESC LIMIT 200""",
                (tag,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM articles ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        article_ids = [r["id"] for r in rows]
        tags_by_article: dict[int, list[str]] = {aid: [] for aid in article_ids}
        if article_ids:
            placeholders = ",".join("?" * len(article_ids))
            for r in c.execute(
                f"""SELECT at.article_id, t.name FROM article_tags at
                    JOIN tags t ON t.id = at.tag_id
                    WHERE at.article_id IN ({placeholders})
                    ORDER BY t.name""",
                article_ids,
            ):
                tags_by_article[r["article_id"]].append(r["name"])
        all_tags = [r["name"] for r in c.execute("SELECT name FROM tags ORDER BY name")]

    categories_by_article = {
        aid: categories.categories_for_tags(names) for aid, names in tags_by_article.items()
    }
    if category:
        rows = [r for r in rows if category in categories_by_article.get(r["id"], [])]

    q = (q or "").strip()[:search.MAX_QUERY_LEN]
    terms = search.parse_terms(q)
    snippets: dict[int, object] = {}
    if terms:
        kept = []
        for r in rows:
            ok, snippet = search.article_view(r, tags_by_article[r["id"]], terms)
            if ok:
                kept.append(r)
                if snippet:
                    snippets[r["id"]] = snippet
        # rows đã sắp mới nhất trước; sort ổn định nên cùng điểm vẫn giữ thứ tự theo ngày
        rows = sorted(kept, key=lambda r: -search.score_article(r, tags_by_article[r["id"]], terms))

    with _translating_lock:
        translating_ids = set(_translating)
    return templates.TemplateResponse(request, "index.html", {
        "articles": rows,
        "translating_ids": translating_ids,
        "tags_by_article": tags_by_article,
        "categories_by_article": categories_by_article,
        "all_categories": categories.CATEGORIES,
        "all_tags": all_tags,
        "active_tag": tag,
        "active_category": category,
        "q": q,
        "terms": terms,
        "snippets": snippets,
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


@app.get("/api/status")
def api_status(ids: str):
    try:
        id_list = [int(x) for x in ids.split(",") if x]
    except ValueError:
        raise HTTPException(400, "ids không hợp lệ")
    if not id_list:
        return {"articles": []}
    with db.conn() as c:
        placeholders = ",".join("?" * len(id_list))
        rows = c.execute(
            f"""SELECT id, slug, status, title, title_vi, summary_vi
                FROM articles WHERE id IN ({placeholders})""",
            id_list,
        ).fetchall()
    with _translating_lock:
        translating_ids = set(_translating)
    return {
        "articles": [
            {
                "id": r["id"],
                "slug": r["slug"],
                "status": "translating" if r["id"] in translating_ids else r["status"],
                "title_vi": r["title_vi"],
                "summary_vi": r["summary_vi"],
            }
            for r in rows
        ]
    }


@app.get("/bai-viet/{slug}")
def article(request: Request, slug: str):
    with db.conn() as c:
        a = c.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
    if not a:
        raise HTTPException(404, "Không tìm thấy bài viết")
    translated = a["status"] == "translated"
    with _translating_lock:
        translating = a["id"] in _translating
    return templates.TemplateResponse(request, "article.html", {
        "a": a,
        "translated": translated,
        "translating": translating,
        "html_vi": render_md(a["content_vi"]) if translated else "",
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


@app.post("/api/articles/{article_id}/summary")
def article_summary(article_id: int):
    """Tóm tắt ý chính cả bài. Gọi Claude đúng một lần cho mỗi bài, lần sau trả từ cache."""
    with db.conn() as c:
        hit = c.execute("SELECT data FROM article_summaries WHERE article_id=?", (article_id,)).fetchone()
        if hit:
            return json.loads(hit["data"])
        a = c.execute("SELECT title, content_en FROM articles WHERE id=?", (article_id,)).fetchone()
    if not a or not a["content_en"]:
        raise HTTPException(404, "Không tìm thấy bài viết")
    try:
        data = llm.summarize_key_points(a["title"], a["content_en"])
    except Exception:
        log.exception("Tóm tắt ý chính lỗi cho bài %s", article_id)
        raise HTTPException(502, "Model không phản hồi. Thử lại sau vài giây.")
    if not data["points"]:
        raise HTTPException(502, "Model trả về tóm tắt rỗng. Thử lại sau vài giây.")
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO article_summaries (article_id, data) VALUES (?, ?)",
                  (article_id, json.dumps(data, ensure_ascii=False)))
    return data
