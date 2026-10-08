"""Chuyển HTML bài viết (lấy từ extension) sang Markdown."""
import re

from markdownify import markdownify

_TRACKING_IMG = re.compile(r"<img[^>]+medium\.com/_/stat[^>]*>", re.I)


def clean_url(url: str) -> str:
    return url.split("?")[0]


# Nhãn của giao diện Medium lọt vào nội dung (cả bản gốc lẫn bản đã dịch). Chỉ xoá khi cả
# dòng chỉ gồm đúng nhãn đó (có thể kèm dấu # nếu bị nhận nhầm là tiêu đề), để không đụng
# tới câu văn có nhắc cụm từ này.
_UI_NOISE_LINE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:member-only story|chỉ dành cho thành viên)[ \t]*$[\r\n]*",
    re.I | re.M,
)


def strip_ui_noise(md: str | None) -> str:
    return _UI_NOISE_LINE.sub("", md or "")


def html_to_markdown_full(html: str) -> str:
    html = _TRACKING_IMG.sub("", html)
    md = strip_ui_noise(markdownify(html, heading_style="ATX"))
    return re.sub(r"\n{3,}", "\n\n", md).strip()
