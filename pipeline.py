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


def fetch() -> dict:
    all_items = []
    for feed in config.FEEDS:
        try:
            items = fetcher.parse_feed(feed)
        except Exception as e:  # feed lỗi thì bỏ qua, không chặn cả pipeline
            log.warning("Feed lỗi %s: %s", feed, e)
            continue
        log.info("%s: %d bài", feed, len(items))
        all_items.extend(items)

    # Gộp tất cả feed rồi chỉ lấy N bài mới nhất, tránh tốn token khi có nhiều feed
    all_items.sort(key=lambda it: it["published"] or "", reverse=True)
    all_items = all_items[:config.MAX_NEW_ARTICLES_PER_RUN]

    new = 0
    with db.conn() as c:
        for it in all_items:
            cur = c.execute(
                """INSERT OR IGNORE INTO articles
                   (url, title, author, published, feed, content_en, word_count, partial)
                   VALUES (:url, :title, :author, :published, :feed, :content_en,
                           :word_count, :partial)""",
                it,
            )
            new += cur.rowcount
    log.info("Bài mới: %d", new)
    return {"fetched_new": new}


def score() -> dict:
    with db.conn() as c:
        cur = c.execute("UPDATE articles SET status='skipped' WHERE status='new' AND partial=1")
        member_only = cur.rowcount
        rows = c.execute(
            "SELECT id, title, content_en FROM articles WHERE status='new'"
        ).fetchall()
    log.info("Cần chấm: %d", len(rows))
    scored = low_score = failed = 0
    for r in rows:
        try:
            s = llm.score_article(r["title"], r["content_en"])
            status = "scored" if s["score"] >= config.SCORE_THRESHOLD else "skipped"
            scored += status == "scored"
            low_score += status == "skipped"
            with db.conn() as c:
                c.execute(
                    """UPDATE articles SET status=?, score=?, score_reason=?, title_vi=?, tldr_vi=?
                       WHERE id=?""",
                    (status, s["score"], s.get("reason"), s.get("title_vi"), s.get("tldr_vi"), r["id"]),
                )
            log.info("[%d/10] %s", s["score"], r["title"])
        except Exception as e:
            log.warning("Chấm lỗi #%d: %s", r["id"], e)
            failed += 1
            with db.conn() as c:
                c.execute("UPDATE articles SET status='failed' WHERE id=?", (r["id"],))
    return {"member_only": member_only, "scored": scored, "low_score": low_score, "failed": failed}


def translate() -> dict:
    with db.conn() as c:
        rows = c.execute(
            """SELECT id, title, content_en FROM articles
               WHERE status='scored' AND partial=0
               ORDER BY score DESC, published DESC LIMIT ?""",
            (config.MAX_TRANSLATE_PER_RUN,),
        ).fetchall()
    translated = failed = 0
    for r in rows:
        try:
            vi = llm.translate_markdown(r["content_en"])
            with db.conn() as c:
                c.execute("UPDATE articles SET status='translated', content_vi=? WHERE id=?",
                          (vi, r["id"]))
            log.info("Đã dịch: %s", r["title"])
            translated += 1
        except Exception as e:
            log.warning("Dịch lỗi #%d: %s", r["id"], e)
            failed += 1
    return {"translated": translated, "failed": failed}


STEPS = {"fetch": fetch, "score": score, "translate": translate}


def save_stats(stats: dict) -> None:
    with db.conn() as c:
        c.execute(
            """INSERT INTO run_stats (id, finished_at, fetched_new, member_only, scored, low_score, translated, failed)
               VALUES (1, CURRENT_TIMESTAMP, :fetched_new, :member_only, :scored, :low_score, :translated, :failed)
               ON CONFLICT(id) DO UPDATE SET
                 finished_at=CURRENT_TIMESTAMP, fetched_new=:fetched_new, member_only=:member_only,
                 scored=:scored, low_score=:low_score, translated=:translated, failed=:failed""",
            {
                "fetched_new": stats.get("fetched_new", 0),
                "member_only": stats.get("member_only", 0),
                "scored": stats.get("scored", 0),
                "low_score": stats.get("low_score", 0),
                "translated": stats.get("translated", 0),
                "failed": stats.get("failed", 0),
            },
        )


def run_all() -> None:
    db.init_db()
    stats = {}
    for step in STEPS.values():
        for k, v in step().items():
            stats[k] = stats.get(k, 0) + v
    save_stats(stats)


if __name__ == "__main__":
    db.init_db()
    for name in (sys.argv[1:] or list(STEPS)):
        STEPS[name]()
