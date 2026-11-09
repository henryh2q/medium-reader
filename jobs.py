"""Tin tuyển dụng: admin dán text / tải file -> Claude trích xuất -> admin duyệt -> đăng ở /viec-lam.

- Admin (Basic Auth qua middleware /admin/* của app.py): /admin/jobs, /admin/jobs/new,
  /admin/jobs/<id>.
- Công khai: /viec-lam (danh sách + chi tiết kiểu LinkedIn) và /viec-lam/<slug>.
"""
import base64
import binascii
import json
import logging
import re
from datetime import date
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

import db
import llm
import search

log = logging.getLogger("jobs")

MODES = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite"}
TYPES = ("Full-time", "Part-time", "Contract", "Intern")
UNITS = ("triệu VND", "USD")
PERS = ("tháng", "năm", "giờ")
# Bộ lọc cấp bậc ở /viec-lam -> từ khoá (đã bỏ dấu) tìm trong trường level.
LEVEL_FILTERS = {"intern": "Intern / Fresher", "junior": "Junior", "mid": "Mid",
                 "senior": "Senior", "lead": "Lead+"}
_LEVEL_KEYS = {"intern": ("intern", "fresher", "thuc tap"), "junior": ("junior", "fresher"),
               "mid": ("mid",), "senior": ("senior",), "lead": ("lead", "manager", "truong nhom")}

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # giới hạn ảnh của API Claude
LIST_LIMIT = 100

# Các trường mà form duyệt đánh dấu "thiếu"/"suy luận" (khoá giao diện, không phải tên cột).
FIELD_KEYS = ("title", "company", "location", "mode", "level", "type", "salary", "headcount",
              "deadline", "skills", "desc", "req", "ben", "email", "phone", "person", "link")


# ---------- Làm sạch dữ liệu (dùng cho cả đầu ra của AI lẫn form admin gửi lên) ----------

def _s(v, n: int) -> str:
    return v.strip()[:n] if isinstance(v, str) else ""


def _lines(v, max_items: int = 30, max_len: int = 400) -> list[str]:
    if not isinstance(v, list):
        return []
    out = [_s(x, max_len) for x in v if isinstance(x, str)]
    return [x for x in out if x][:max_items]


def _num(v) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _date(v) -> str:
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return ""
    try:
        date.fromisoformat(v.strip())
    except ValueError:
        return ""
    return v.strip()


def _url(v) -> str:
    """Chỉ nhận http(s) — giá trị này được render thành href công khai."""
    v = _s(v, 500)
    if v and not re.match(r"^[a-z][a-z0-9+.-]*:", v, re.I) and re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", v):
        v = "https://" + v
    return v if re.match(r"^https?://\S+$", v, re.I) else ""


def _email(v) -> str:
    v = _s(v, 200)
    return v if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) else ""


def clean_job(d: dict) -> dict:
    """Chuẩn hoá về đúng các cột của bảng jobs. Giá trị lạ bị bỏ chứ không báo lỗi — admin
    còn xem lại ở form duyệt trước khi đăng."""
    sal = d.get("salary") if isinstance(d.get("salary"), dict) else {}
    mode = d.get("mode") if d.get("mode") in MODES else ""
    c = d.get("contact") if isinstance(d.get("contact"), dict) else {}
    # Form admin gửi phẳng, AI trả lồng nhau: nhận cả hai.
    get = lambda flat, nested, key: d.get(flat, nested.get(key) if nested else None)  # noqa: E731
    smin, smax = _num(get("salary_min", sal, "min")), _num(get("salary_max", sal, "max"))
    if smin is not None and smax is not None and smin > smax:
        smin, smax = smax, smin
    hc = _num(d.get("headcount"))
    return {
        "title": _s(d.get("title"), 200),
        "company": _s(d.get("company"), 150),
        "location": _s(d.get("location"), 120),
        "mode": mode,
        "level": _s(d.get("level"), 60),
        "job_type": d.get("job_type", d.get("type")) if d.get("job_type", d.get("type")) in TYPES else "",
        "salary_min": smin or None,
        "salary_max": smax or None,
        "salary_unit": get("salary_unit", sal, "unit") if get("salary_unit", sal, "unit") in UNITS else UNITS[0],
        "salary_per": get("salary_per", sal, "per") if get("salary_per", sal, "per") in PERS else PERS[0],
        "salary_nego": 1 if get("salary_nego", sal, "negotiable") in (True, 1) else 0,
        "headcount": int(hc) if hc and hc >= 1 else None,
        "deadline": _date(d.get("deadline")),
        "skills": _lines(d.get("skills"), 12, 40),
        "description": _lines(d.get("description")),
        "requirements": _lines(d.get("requirements")),
        "benefits": _lines(d.get("benefits")),
        "contact_email": _email(get("contact_email", c, "email")),
        "contact_phone": _s(get("contact_phone", c, "phone"), 40),
        "contact_person": _s(get("contact_person", c, "person"), 120),
        "contact_link": _url(get("contact_link", c, "link")),
    }


def _ai_meta(raw: dict) -> dict:
    inferred = [k for k in raw.get("inferred", []) if isinstance(raw.get("inferred"), list) and k in FIELD_KEYS]
    return {"inferred": inferred, "notes": _lines(raw.get("notes"), 6, 300)}


_JSON_COLS = ("skills", "description", "requirements", "benefits")
_COLS = ("title", "company", "location", "mode", "level", "job_type", "salary_min", "salary_max",
         "salary_unit", "salary_per", "salary_nego", "headcount", "deadline", *_JSON_COLS,
         "contact_email", "contact_phone", "contact_person", "contact_link")


def _db_values(job: dict) -> list:
    return [json.dumps(job[c], ensure_ascii=False) if c in _JSON_COLS else job[c] for c in _COLS]


def make_unique_slug(c, title: str, company: str) -> str:
    base = db.slugify(f"{title} {company}".strip()) or "viec-lam"
    slug, n = base, 2
    while c.execute("SELECT 1 FROM jobs WHERE slug=?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    return slug


# ---------- Dữ liệu hiển thị ----------

def _n(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") if v == int(v) else str(v).replace(".", ",")


def salary_text(j: dict, long: bool = False) -> str:
    if j["salary_nego"]:
        return "Thoả thuận"
    unit = " USD" if j["salary_unit"] == "USD" else " triệu"
    lo, hi = j["salary_min"], j["salary_max"]
    if lo and hi:
        t = f"{_n(lo)} – {_n(hi)}{unit}"
    elif lo:
        t = f"Từ {_n(lo)}{unit}"
    elif hi:
        t = f"Tới {_n(hi)}{unit}"
    else:
        return ""
    return f"{t}{'' if j['salary_unit'] == 'USD' else ' VND'} / {j['salary_per']}" if long else t


def _days_ago(day: str | None) -> int | None:
    try:
        return (date.today() - date.fromisoformat((day or "")[:10])).days
    except ValueError:
        return None


def _ago(day: str | None) -> str:
    d = _days_ago(day)
    if d is None:
        return ""
    if d <= 0:
        return "Đăng hôm nay"
    if d == 1:
        return "Đăng hôm qua"
    return f"Đăng {d} ngày trước" if d < 7 else f"Đăng {d // 7} tuần trước"


def _apply(j: dict) -> dict | None:
    if j["contact_link"]:
        return {"href": j["contact_link"], "external": True}
    if j["contact_email"]:
        return {"href": f"mailto:{j['contact_email']}?subject={quote('Ứng tuyển ' + j['title'])}", "external": False}
    return None


def view(row) -> dict:
    j = dict(row)
    for k in _JSON_COLS:
        j[k] = j[k] if isinstance(j[k], list) else json.loads(j[k] or "[]")
    j["ai_meta"] = j["ai_meta"] if isinstance(j["ai_meta"], dict) else json.loads(j["ai_meta"] or "{}")
    day = (j["published_at"] or j["created_at"] or "")[:10]
    j["expired"] = bool(j["deadline"]) and j["deadline"] < date.today().isoformat()
    j["is_new"] = not j["expired"] and (_days_ago(day) or 0) <= 3
    j["state"] = "draft" if j["status"] == "draft" else "expired" if j["expired"] else "published"
    j["state_label"] = {"draft": "Bản nháp", "expired": "Hết hạn", "published": "Đang đăng"}[j["state"]]
    j["search"] = search.fold(" ".join([j["title"], j["company"], j["location"]]))
    j["mode_label"] = MODES.get(j["mode"], "")
    j["salary_short"] = salary_text(j)
    j["salary_long"] = salary_text(j, long=True)
    j["posted"] = _ago(day)
    j["apply"] = _apply(j)
    j["company_or_unknown"] = j["company"] or "Chưa rõ công ty"
    j["initial"] = (j["company"] or j["title"])[:1].upper()
    j["hue"] = sum(map(ord, j["company"] or j["title"])) % 360
    j["days_left"] = (date.fromisoformat(j["deadline"]) - date.today()).days if j["deadline"] and not j["expired"] else None
    j["brief"] = not j["expired"] and not j["company"] and not j["requirements"] and not j["benefits"]
    return j


def _flags(j: dict) -> dict:
    """Trạng thái từng ô ở form duyệt: 'miss' (trống) | 'inf' (AI suy luận) | ''."""
    have = {
        "title": j["title"], "company": j["company"], "location": j["location"], "mode": j["mode"],
        "level": j["level"], "type": j["job_type"],
        "salary": j["salary_min"] or j["salary_max"] or j["salary_nego"],
        "headcount": j["headcount"], "deadline": j["deadline"], "skills": j["skills"],
        "desc": j["description"], "req": j["requirements"], "ben": j["benefits"],
        "email": j["contact_email"], "phone": j["contact_phone"],
        "person": j["contact_person"], "link": j["contact_link"],
    }
    inferred = set(j["ai_meta"].get("inferred", []))
    return {k: "miss" if not v else "inf" if k in inferred else "" for k, v in have.items()}


def _published_jobs(c) -> list[dict]:
    rows = c.execute("SELECT * FROM jobs WHERE status='published' ORDER BY published_at DESC, id DESC").fetchall()
    jobs = [view(r) for r in rows]
    jobs.sort(key=lambda j: j["expired"])  # ổn định: hết hạn xuống cuối, còn lại giữ thứ tự mới nhất
    return jobs


def _filter(jobs: list[dict], q: str, mode: str, level: str, salary: bool) -> list[dict]:
    terms = search.parse_terms(q)
    out = []
    for j in jobs:
        if mode and j["mode"] != mode:
            continue
        if level and not any(k in search.fold(j["level"]) for k in _LEVEL_KEYS.get(level, ())):
            continue
        if salary and not (j["salary_min"] or j["salary_max"]) :
            continue
        if terms:
            hay = search.fold(" ".join([j["title"], j["company"], j["location"], *j["skills"], *j["description"]]))
            if not all(t in hay for t in terms):
                continue
        out.append(j)
    return out


def make_router(templates) -> APIRouter:
    r = APIRouter()

    # ---------- Admin ----------

    @r.get("/admin/jobs")
    def admin_jobs(request: Request):
        with db.conn() as c:
            jobs = [view(x) for x in c.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()]
        return templates.TemplateResponse(request, "admin_jobs.html", {"jobs": jobs})

    @r.get("/admin/jobs/new")
    def admin_job_new(request: Request):
        return templates.TemplateResponse(request, "admin_job_new.html", {"exts": llm.JOB_FILE_EXTS})

    @r.post("/admin/jobs/extract")
    def admin_job_extract(body: dict = Body(...)):
        """Nhận {text, filename, content_b64} (file gửi dạng base64 trong JSON để khỏi cần
        python-multipart), nhờ Claude trích xuất rồi tạo ngay 1 bản nháp để admin duyệt."""
        text = body.get("text") if isinstance(body.get("text"), str) else ""
        filename = _s(body.get("filename"), 200)
        data = None
        if body.get("content_b64"):
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in llm.JOB_FILE_EXTS:
                raise HTTPException(400, "Chỉ nhận file PDF, Word (.docx), ảnh, .txt hoặc .md.")
            try:
                data = base64.b64decode(body["content_b64"], validate=True)
            except (binascii.Error, ValueError, TypeError):
                raise HTTPException(400, "File tải lên bị lỗi, hãy thử chọn lại.")
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, "File quá lớn (tối đa 10 MB).")
            if ext in ("png", "jpg", "jpeg", "webp", "gif") and len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "Ảnh quá lớn (tối đa 5 MB).")
        if not text.strip() and not data:
            raise HTTPException(400, "Hãy dán nội dung hoặc chọn file.")
        try:
            raw = llm.extract_job(text, filename, data)
        except Exception:
            log.exception("extract_job thất bại")
            raise HTTPException(502, "AI không đọc được nội dung này. Thử lại hoặc dán text trực tiếp.")
        job = clean_job(raw if isinstance(raw, dict) else {})
        if not job["title"]:
            raise HTTPException(422, "AI không tìm thấy tin tuyển dụng nào trong nội dung này.")
        with db.conn() as c:
            slug = make_unique_slug(c, job["title"], job["company"])
            cur = c.execute(
                f"INSERT INTO jobs (slug, {', '.join(_COLS)}, source_text, source_file, ai_meta) "
                f"VALUES (?, {', '.join('?' * len(_COLS))}, ?, ?, ?)",
                [slug, *_db_values(job), text.strip()[:20_000], filename,
                 json.dumps(_ai_meta(raw), ensure_ascii=False)])
            job_id = cur.lastrowid
        return {"id": job_id, "url": f"/admin/jobs/{job_id}"}

    @r.post("/admin/jobs/preview")
    def admin_job_preview(request: Request, body: dict = Body(...)):
        """Dựng thẻ + trang chi tiết đúng như trên site từ dữ liệu form đang gõ (chưa lưu),
        dùng chung template với trang công khai nên bản xem trước luôn khớp."""
        job = clean_job(body)
        job["title"] = job["title"] or "(Chưa có chức danh)"
        today = date.today().isoformat()
        j = view({**job, "id": 0, "slug": "", "status": "draft", "published_at": today,
                  "created_at": today, "ai_meta": {}, "source_text": "", "source_file": ""})
        return templates.TemplateResponse(request, "_job_preview.html", {"j": j})

    @r.get("/admin/jobs/{job_id}")
    def admin_job_edit(request: Request, job_id: int):
        with db.conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy job")
        j = view(row)
        flags = _flags(j)
        return templates.TemplateResponse(request, "admin_job_edit.html", {
            "j": j, "flags": flags, "missing": sum(v == "miss" for v in flags.values()),
            "inferred": sum(v == "inf" for v in flags.values()), "total": len(flags),
            "levels": ["Intern", "Fresher / Junior", "Mid", "Mid – Senior", "Senior", "Lead+"],
            "modes": MODES, "types": TYPES, "units": UNITS, "pers": PERS,
        })

    @r.post("/admin/jobs/{job_id}")
    def admin_job_save(job_id: int, body: dict = Body(...)):
        """Lưu form duyệt. action='publish' đăng lên site, 'save' giữ nguyên trạng thái."""
        job = clean_job(body)
        if not job["title"]:
            raise HTTPException(400, "Cần nhập Chức danh.")
        with db.conn() as c:
            row = c.execute("SELECT status, published_at, ai_meta FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy job")
            publish = body.get("action") == "publish"
            status = "published" if publish else row["status"]
            meta = json.loads(row["ai_meta"] or "{}")
            meta["inferred"] = []  # admin đã xem lại
            c.execute(
                f"UPDATE jobs SET {', '.join(f'{k}=?' for k in _COLS)}, status=?, ai_meta=?, "
                "published_at=CASE WHEN ?='published' AND published_at IS NULL THEN CURRENT_TIMESTAMP ELSE published_at END "
                "WHERE id=?",
                [*_db_values(job), status, json.dumps(meta, ensure_ascii=False), status, job_id])
            slug = c.execute("SELECT slug FROM jobs WHERE id=?", (job_id,)).fetchone()["slug"]
        return {"ok": True, "status": status, "slug": slug}

    @r.post("/admin/jobs/{job_id}/status")
    def admin_job_status(job_id: int, body: dict = Body(...)):
        if body.get("status") not in ("draft", "published"):
            raise HTTPException(400, "Trạng thái không hợp lệ")
        with db.conn() as c:
            cur = c.execute(
                "UPDATE jobs SET status=?, published_at=CASE WHEN ?='published' AND published_at IS NULL "
                "THEN CURRENT_TIMESTAMP ELSE published_at END WHERE id=?",
                (body["status"], body["status"], job_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "Không tìm thấy job")
        return {"ok": True}

    @r.post("/admin/jobs/{job_id}/delete")
    def admin_job_delete(job_id: int):
        with db.conn() as c:
            cur = c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "Không tìm thấy job")
        return {"ok": True}

    # ---------- Công khai: bố cục kiểu LinkedIn (danh sách trái, chi tiết phải) ----------

    def board(request: Request, slug: str | None, q: str, mode: str, level: str, salary: str):
        mode = mode if mode in MODES else ""
        level = level if level in LEVEL_FILTERS else ""
        q = q.strip()[:search.MAX_QUERY_LEN]
        with db.conn() as c:
            everything = _published_jobs(c)
        jobs = _filter(everything, q, mode, level, salary == "1")[:LIST_LIMIT]
        selected = None
        if slug:
            selected = next((j for j in everything if j["slug"] == slug), None)
            if not selected:
                raise HTTPException(404, "Không tìm thấy tin tuyển dụng")
        elif jobs:
            selected = jobs[0]  # desktop: mở sẵn tin đầu tiên như LinkedIn
        params = {k: v for k, v in (("q", q), ("mode", mode), ("level", level), ("salary", "1" if salary == "1" else "")) if v}
        return {"jobs": jobs, "selected": selected, "explicit": bool(slug), "q": q, "mode": mode,
                "level": level, "salary": salary == "1", "modes": MODES, "level_filters": LEVEL_FILTERS,
                "qs": "?" + urlencode(params) if params else "",
                "open_count": sum(not j["expired"] for j in everything), "total": len(jobs)}

    @r.get("/viec-lam")
    def jobs_page(request: Request, q: str = "", mode: str = "", level: str = "", salary: str = ""):
        return templates.TemplateResponse(request, "jobs.html", board(request, None, q, mode, level, salary))

    @r.get("/viec-lam/{slug}")
    def job_page(request: Request, slug: str, partial: int = 0, q: str = "", mode: str = "",
                 level: str = "", salary: str = ""):
        ctx = board(request, slug, q, mode, level, salary)
        if partial:  # desktop: JS thay riêng khung chi tiết, không tải lại cả trang
            return templates.TemplateResponse(request, "_job_detail.html", {"j": ctx["selected"]})
        return templates.TemplateResponse(request, "jobs.html", ctx)

    return r
