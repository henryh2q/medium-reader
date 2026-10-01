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
