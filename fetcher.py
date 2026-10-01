"""Chuyển HTML bài viết (lấy từ extension) sang Markdown."""
import re

from markdownify import markdownify

_TRACKING_IMG = re.compile(r"<img[^>]+medium\.com/_/stat[^>]*>", re.I)


def clean_url(url: str) -> str:
    return url.split("?")[0]


def html_to_markdown_full(html: str) -> str:
    html = _TRACKING_IMG.sub("", html)
    md = markdownify(html, heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", md).strip()
