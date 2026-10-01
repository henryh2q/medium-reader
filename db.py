import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    author       TEXT,
    published    TEXT,
    feed         TEXT,
    content_en   TEXT,
    word_count   INTEGER DEFAULT 0,
    partial      INTEGER DEFAULT 0,          -- 1 = member-only / bị cắt
    status       TEXT DEFAULT 'new',         -- new | scored | skipped | translated | failed
    score        INTEGER,
    score_reason TEXT,
    title_vi     TEXT,
    tldr_vi      TEXT,
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

-- Thống kê lần chạy pipeline gần nhất (luôn chỉ có 1 dòng, id=1)
CREATE TABLE IF NOT EXISTS run_stats (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    finished_at     TEXT,
    fetched_new     INTEGER DEFAULT 0,
    member_only     INTEGER DEFAULT 0,
    scored          INTEGER DEFAULT 0,
    low_score       INTEGER DEFAULT 0,
    translated      INTEGER DEFAULT 0,
    failed          INTEGER DEFAULT 0
);
"""


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
