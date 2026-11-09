import re
import sqlite3
from contextlib import contextmanager

import config

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    slug         TEXT UNIQUE NOT NULL,        -- định danh trong URL /bai-viet/<slug>, cố định từ lúc tạo
    title        TEXT NOT NULL,
    author       TEXT,
    content_en   TEXT,
    summary_en   TEXT,
    word_count   INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'new',         -- new | translated | failed
    title_vi     TEXT,
    summary_vi   TEXT,
    content_vi   TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);

CREATE TABLE IF NOT EXISTS explanations (
    term_key   TEXT NOT NULL,
    article_id INTEGER NOT NULL,
    data       TEXT NOT NULL,                -- JSON
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (term_key, article_id)
);

-- Tóm tắt ý chính của cả bài (nút tóm tắt ở trang đọc). Mỗi bài chỉ gọi Claude một
-- lần rồi lưu lại ở đây để các lần sau không tốn token.
CREATE TABLE IF NOT EXISTS article_summaries (
    article_id INTEGER PRIMARY KEY,
    data       TEXT NOT NULL,                -- JSON {"tldr": str, "points": [str]}
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);

-- Hàng đợi URL do người dùng gửi (thường từ mobile, nơi không cài được extension).
-- Admin mở từng URL ở PC rồi đưa vào bằng extension, hoặc từ chối. Khi bài được import
-- với URL khớp url_key thì mục tự chuyển sang 'imported'.
CREATE TABLE IF NOT EXISTS submissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,                 -- nguyên văn người dùng gửi, để admin mở
    url_key    TEXT UNIQUE NOT NULL,          -- URL đã chuẩn hoá, dùng chống trùng + khớp lúc import
    note       TEXT,
    status     TEXT DEFAULT 'pending',        -- pending | imported | rejected
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL,
    PRIMARY KEY (article_id, tag_id),
    FOREIGN KEY (article_id) REFERENCES articles(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
CREATE INDEX IF NOT EXISTS idx_article_tags_tag ON article_tags(tag_id);

-- Yêu cầu cấp IMPORT_TOKEN từ người dùng ngoài (qua trang /submit). Admin duyệt thủ
-- công ở /admin/requests và gán token cho đúng request_id; trang /submit polling để
-- biết khi nào có token.
CREATE TABLE IF NOT EXISTS token_requests (
    request_id TEXT PRIMARY KEY,              -- UUID phiên của người yêu cầu
    status     TEXT DEFAULT 'pending',         -- pending | approved
    token      TEXT,                           -- gán khi duyệt
    note       TEXT,                           -- ghi chú tuỳ chọn (vd. email liên hệ)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- API key cho ứng dụng bên ngoài đọc blog qua /api/v1/*. Chỉ lưu SHA-256 của key (key
-- gốc hiện đúng 1 lần lúc tạo ở /admin/api-keys); thu hồi bằng status='revoked'.
CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,                -- tên hệ thống được cấp key, để nhận biết khi thu hồi
    key_hash     TEXT UNIQUE NOT NULL,
    key_prefix   TEXT NOT NULL,                -- vài ký tự đầu của key, chỉ để admin đối chiếu
    status       TEXT DEFAULT 'active',        -- active | revoked
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT
);

-- Tin tuyển dụng (/viec-lam). Admin chỉ dán text / tải file; Claude trích xuất thành các
-- cột dưới đây (jobs.py). Danh sách (skills, description, requirements, benefits) lưu JSON.
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE NOT NULL,       -- định danh trong URL /viec-lam/<slug>, cố định từ lúc tạo
    title         TEXT NOT NULL,
    company       TEXT DEFAULT '',
    location      TEXT DEFAULT '',
    mode          TEXT DEFAULT '',            -- remote | hybrid | onsite | ''
    level         TEXT DEFAULT '',
    job_type      TEXT DEFAULT '',            -- Full-time | Part-time | Contract | Intern | ''
    salary_min    REAL,
    salary_max    REAL,
    salary_unit   TEXT DEFAULT 'triệu VND',   -- 'triệu VND' | 'USD'
    salary_per    TEXT DEFAULT 'tháng',       -- tháng | năm | giờ
    salary_nego   INTEGER DEFAULT 0,          -- 1 = lương thoả thuận
    headcount     INTEGER,
    deadline      TEXT DEFAULT '',            -- YYYY-MM-DD, '' = không ghi
    skills        TEXT DEFAULT '[]',          -- JSON list[str]
    description   TEXT DEFAULT '[]',          -- JSON list[str]
    requirements  TEXT DEFAULT '[]',
    benefits      TEXT DEFAULT '[]',
    contact_email  TEXT DEFAULT '',
    contact_phone  TEXT DEFAULT '',
    contact_person TEXT DEFAULT '',
    contact_link   TEXT DEFAULT '',
    status        TEXT DEFAULT 'draft',       -- draft | published
    source_text   TEXT DEFAULT '',            -- nội dung gốc admin đưa vào (để đối chiếu lúc duyệt)
    source_file   TEXT DEFAULT '',            -- tên file đã tải lên (chỉ để hiển thị, không lưu file)
    ai_meta       TEXT DEFAULT '{}',          -- JSON {"inferred": [field], "notes": [str]}
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    published_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, published_at);
"""


def slugify(title: str) -> str:
    s = _SLUG_STRIP.sub("-", title.lower()).strip("-")
    return s[:80].rstrip("-") or "bai-viet"


def make_unique_slug(c, title: str) -> str:
    """Sinh slug từ title, thêm hậu tố -2, -3... nếu đã tồn tại."""
    base = slugify(title)
    slug = base
    n = 2
    while c.execute("SELECT 1 FROM articles WHERE slug=?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    return slug


def set_article_tags(c, article_id: int, tag_names: list[str]) -> None:
    """Thay toàn bộ tag của 1 bài. So khớp trùng theo tên nguyên văn (case-sensitive) —
    "AI Agents" và "ai agents" được coi là 2 tag khác nhau."""
    c.execute("DELETE FROM article_tags WHERE article_id=?", (article_id,))
    for raw in tag_names:
        name = raw.strip()
        if not name:
            continue
        c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = c.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        c.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?,?)",
                  (article_id, row["id"]))


def tags_for_articles(c, article_ids: list[int]) -> dict[int, list[str]]:
    """Tên tag (sắp theo tên) của từng bài; bài không có tag vẫn có mục với list rỗng."""
    tags: dict[int, list[str]] = {aid: [] for aid in article_ids}
    for i in range(0, len(article_ids), 500):  # chunk để không vượt giới hạn biến của SQLite
        chunk = article_ids[i:i + 500]
        for r in c.execute(
            f"""SELECT at.article_id, t.name FROM article_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.article_id IN ({",".join("?" * len(chunk))})
                ORDER BY t.name""",
            chunk,
        ):
            tags[r["article_id"]].append(r["name"])
    return tags


@contextmanager
def conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
