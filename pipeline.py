"""Chạy định kỳ (cron): lấy RSS -> chấm điểm -> dịch bài tốt nhất.

    python pipeline.py            # chạy cả 3 bước
    python pipeline.py fetch      # chỉ lấy bài
    python pipeline.py score      # chỉ chấm điểm
    python pipeline.py translate  # chỉ dịch
"""
import logging
import sys

import config
import db
import fetcher
import llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


def fetch() -> None:
    new = 0
    with db.conn() as c:
        for feed in config.FEEDS:
            try:
                items = fetcher.parse_feed(feed)
            except Exception as e:  # feed lỗi thì bỏ qua, không chặn cả pipeline
                log.warning("Feed lỗi %s: %s", feed, e)
                continue
            for it in items:
                cur = c.execute(
                    """INSERT OR IGNORE INTO articles
                       (url, title, author, published, feed, content_en, word_count, partial)
                       VALUES (:url, :title, :author, :published, :feed, :content_en,
                               :word_count, :partial)""",
                    it,
                )
                new += cur.rowcount
            log.info("%s: %d bài", feed, len(items))
    log.info("Bài mới: %d", new)


def score() -> None:
    with db.conn() as c:
        rows = c.execute("SELECT id, title, content_en FROM articles WHERE status='new'").fetchall()
    log.info("Cần chấm: %d", len(rows))
    for r in rows:
        try:
            s = llm.score_article(r["title"], r["content_en"])
            status = "scored" if s["score"] >= config.SCORE_THRESHOLD else "skipped"
            with db.conn() as c:
                c.execute(
                    """UPDATE articles SET status=?, score=?, score_reason=?, title_vi=?, tldr_vi=?
                       WHERE id=?""",
                    (status, s["score"], s.get("reason"), s.get("title_vi"), s.get("tldr_vi"), r["id"]),
                )
            log.info("[%d/10] %s", s["score"], r["title"])
        except Exception as e:
            log.warning("Chấm lỗi #%d: %s", r["id"], e)
            with db.conn() as c:
                c.execute("UPDATE articles SET status='failed' WHERE id=?", (r["id"],))


def translate() -> None:
    with db.conn() as c:
        rows = c.execute(
            """SELECT id, title, content_en FROM articles
               WHERE status='scored' AND partial=0
               ORDER BY score DESC, published DESC LIMIT ?""",
            (config.MAX_TRANSLATE_PER_RUN,),
        ).fetchall()
    for r in rows:
        try:
            vi = llm.translate_markdown(r["content_en"])
            with db.conn() as c:
                c.execute("UPDATE articles SET status='translated', content_vi=? WHERE id=?",
                          (vi, r["id"]))
            log.info("Đã dịch: %s", r["title"])
        except Exception as e:
            log.warning("Dịch lỗi #%d: %s", r["id"], e)


STEPS = {"fetch": fetch, "score": score, "translate": translate}


def run_all() -> None:
    db.init_db()
    for step in STEPS.values():
        step()


if __name__ == "__main__":
    db.init_db()
    for name in (sys.argv[1:] or list(STEPS)):
        STEPS[name]()
