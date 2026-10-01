"""Đọc RSS (engineering blog) và chuyển nội dung HTML sang Markdown."""
import re
from datetime import datetime, timezone

import feedparser
from markdownify import markdownify

import config

UA = "Mozilla/5.0 (personal RSS reader)"
_TRACKING_IMG = re.compile(r"<img[^>]+medium\.com/_/stat[^>]*>", re.I)
_CONTINUE = re.compile(r"<p>\s*<a[^>]*>\s*Continue reading on[^<]*</a>\s*</p>", re.I)


def clean_url(url: str) -> str:
    return url.split("?")[0]


def html_to_markdown(html: str) -> tuple[str, bool]:
    """Trả về (markdown, truncated). truncated=True nếu RSS chỉ có đoạn đầu."""
    truncated = bool(_CONTINUE.search(html))
    html = _CONTINUE.sub("", _TRACKING_IMG.sub("", html))
    md = markdownify(html, heading_style="ATX")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md, truncated


def parse_feed(feed_url: str) -> list[dict]:
    d = feedparser.parse(feed_url, agent=UA)
    items = []
    for e in d.entries:
        html = e.content[0].value if e.get("content") else e.get("summary", "")
        md, truncated = html_to_markdown(html)
        words = len(md.split())
        published = None
        if e.get("published_parsed"):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        items.append({
            "url": clean_url(e.link),
            "title": e.get("title", "").strip(),
            "author": e.get("author", ""),
            "published": published,
            "feed": feed_url,
            "content_en": md,
            "word_count": words,
            "partial": int(truncated or words < config.MIN_WORDS_FULL),
        })
    return items


def html_to_markdown_full(html: str) -> str:
    """Như html_to_markdown nhưng cho HTML đầy đủ lấy từ extension (không cắt đoạn)."""
    html = _TRACKING_IMG.sub("", html)
    md = markdownify(html, heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", md).strip()
