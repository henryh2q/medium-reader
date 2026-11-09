"""API công khai cho ứng dụng bên ngoài đọc dữ liệu blog: /api/v1/*, xác thực bằng API key.

Key do admin cấp ở /admin/api-keys (xem app.py), mỗi hệ thống một key để thu hồi riêng.
Gửi key qua header `X-API-Key: <key>` hoặc `Authorization: Bearer <key>`.
"""
import hashlib
import secrets
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import categories
import db
import fetcher
import search

KEY_PREFIX = "mrk_"
MAX_LIMIT = 100


# ---------- Quản lý key (dùng bởi các route /admin/api-keys) ----------

def hash_key(key: str) -> str:
    # Key là chuỗi ngẫu nhiên 256 bit nên SHA-256 thường là đủ, không cần hash chậm.
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(name: str) -> dict:
    """Tạo key mới. Trả key gốc kèm thông tin; key gốc không lưu lại, chỉ hiện lần này."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with db.conn() as c:
        cur = c.execute("INSERT INTO api_keys (name, key_hash, key_prefix) VALUES (?, ?, ?)",
                        (name, hash_key(key), key[:8]))
    return {"id": cur.lastrowid, "name": name, "key": key}


def list_api_keys() -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, name, key_prefix, status, created_at, last_used_at FROM api_keys ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_api_key(key_id: int) -> bool:
    with db.conn() as c:
        cur = c.execute("UPDATE api_keys SET status='revoked' WHERE id=? AND status='active'", (key_id,))
    return cur.rowcount > 0


# ---------- Xác thực ----------

def _extract_key(request: Request) -> str:
    key = request.headers.get("x-api-key", "").strip()
    if key:
        return key
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def require_api_key(request: Request) -> None:
    key = _extract_key(request)
    ok = False
    if key:
        with db.conn() as c:
            ok = c.execute("SELECT 1 FROM api_keys WHERE key_hash=? AND status='active'",
                           (hash_key(key),)).fetchone() is not None
            if ok:  # ghi last_used_at tối đa 5 phút một lần để không biến mỗi lần đọc thành một lần ghi
                c.execute(
                    """UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP
                       WHERE key_hash=? AND (last_used_at IS NULL
                                             OR last_used_at < datetime('now', '-5 minutes'))""",
                    (hash_key(key),))
    if not ok:
        raise HTTPException(401, "API key thiếu hoặc không hợp lệ.",
                            headers={"WWW-Authenticate": "Bearer"})


# ---------- Dữ liệu ----------

# Danh sách không kèm nội dung bài (nặng); chỉ lấy đủ cột khi cần tìm trong nội dung.
_LIST_COLUMNS = ("id, url, slug, title, author, summary_en, word_count, status, "
                 "title_vi, summary_vi, created_at")


def _article_json(row, tags: list[str], web_url: str, with_content: bool = False) -> dict:
    out = {
        "id": row["id"],
        "slug": row["slug"],
        "web_url": web_url,
        "source_url": row["url"],
        "title": row["title"],
        "title_vi": row["title_vi"],
        "author": row["author"] or "",
        "summary_en": row["summary_en"],
        "summary_vi": row["summary_vi"],
        "tags": tags,
        "categories": categories.categories_for_tags(tags),
        "word_count": row["word_count"],
        "status": row["status"],  # new | translated | failed; bản _vi chỉ có khi translated
        "created_at": row["created_at"],
    }
    if with_content:
        out["content_en"] = fetcher.strip_ui_noise(row["content_en"])
        out["content_vi"] = fetcher.strip_ui_noise(row["content_vi"]) if row["content_vi"] else None
    return out


def make_router(public_base: Callable[[Request], str]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)], tags=["public-api"])

    def web_url(request: Request, slug: str) -> str:
        return f"{public_base(request)}/bai-viet/{slug}"

    @router.get("/articles")
    def list_articles(
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=MAX_LIMIT),
        tag: str | None = None,
        category: str | None = Query(None, description="AI | System Design"),
        q: str | None = Query(None, description="Tìm theo từ khoá (không phân biệt dấu/hoa thường)"),
        status: str | None = Query(None, pattern="^(new|translated|failed)$"),
        created_after: str | None = Query(
            None, pattern=r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$",
            description="Chỉ bài tạo sau mốc này (UTC), vd. 2025-10-01 hoặc 2025-10-01T08:30:00"),
    ):
        """Danh sách bài, mới nhất trước (khi có `q` thì xếp theo độ khớp). Không kèm nội dung bài."""
        if category and category not in categories.CATEGORIES:
            raise HTTPException(400, f"category phải là một trong: {', '.join(categories.CATEGORIES)}")
        terms = search.parse_terms((q or "").strip()[:search.MAX_QUERY_LEN])

        joins, where, params = "", [], []
        if tag:
            joins = "JOIN article_tags at ON at.article_id = a.id JOIN tags t ON t.id = at.tag_id"
            where.append("t.name = ?")
            params.append(tag)
        if status:
            where.append("a.status = ?")
            params.append(status)
        if created_after:
            where.append("a.created_at > ?")
            params.append(created_after.replace("T", " "))
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        columns = "a.*" if terms else ", ".join("a." + col.strip() for col in _LIST_COLUMNS.split(","))

        with db.conn() as c:
            rows = c.execute(
                f"SELECT {columns} FROM articles a {joins} {where_sql} ORDER BY a.created_at DESC, a.id DESC",
                params,
            ).fetchall()
            tags_by = db.tags_for_articles(c, [r["id"] for r in rows])

        if category:
            rows = [r for r in rows if category in categories.categories_for_tags(tags_by[r["id"]])]
        if terms:
            rows = [r for r in rows if search.article_view(r, tags_by[r["id"]], terms)[0]]
            rows.sort(key=lambda r: -search.score_article(r, tags_by[r["id"]], terms))  # sort ổn định

        total = len(rows)
        start = (page - 1) * limit
        return {
            "data": [_article_json(r, tags_by[r["id"]], web_url(request, r["slug"]))
                     for r in rows[start:start + limit]],
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": start + limit < total,
        }

    @router.get("/articles/{slug}")
    def get_article(request: Request, slug: str):
        """Một bài đầy đủ, kèm nội dung Markdown (`content_en`, và `content_vi` nếu đã dịch)."""
        with db.conn() as c:
            row = c.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy bài viết")
            tags = db.tags_for_articles(c, [row["id"]])[row["id"]]
        return _article_json(row, tags, web_url(request, row["slug"]), with_content=True)

    @router.get("/tags")
    def list_tags():
        """Mọi tag kèm số bài, nhiều bài nhất trước."""
        with db.conn() as c:
            rows = c.execute(
                """SELECT t.name, COUNT(at.article_id) AS articles FROM tags t
                   JOIN article_tags at ON at.tag_id = t.id
                   GROUP BY t.id ORDER BY articles DESC, t.name"""
            ).fetchall()
        return {"data": [{"name": r["name"], "articles": r["articles"]} for r in rows]}

    return router
