import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
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
"""


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
