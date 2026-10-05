"""Tìm kiếm bài viết theo từ khoá ở trang chủ: không phân biệt hoa/thường và dấu tiếng
Việt ("thiet ke" khớp "thiết kế"), mọi từ khoá đều phải xuất hiện (AND), và tô vàng chỗ khớp."""
import re
import unicodedata

from markupsafe import Markup, escape

MAX_QUERY_LEN = 100
MAX_TERMS = 6
SNIPPET_WIDTH = 170


def _build_fold_table() -> dict[int, int]:
    """Bảng ánh xạ 1 ký tự -> 1 ký tự (bỏ dấu + chữ thường). Phải là 1-1 để vị trí trong
    chuỗi đã chuẩn hoá trùng khớp vị trí trong văn bản gốc khi tô vàng."""
    table: dict[int, int] = {}
    for cp in [*range(0x41, 0x5B), *range(0xC0, 0x2000)]:
        ch = chr(cp)
        if ch in "đĐ":
            table[cp] = ord("d")
            continue
        low = unicodedata.normalize("NFD", ch)[0].lower()
        if len(low) == 1 and low != ch:
            table[cp] = ord(low)
    return table


_FOLD = _build_fold_table()


def fold(text: str) -> str:
    return text.translate(_FOLD)


def parse_terms(q: str | None) -> list[str]:
    """Tách câu tìm kiếm thành các từ khoá đã chuẩn hoá, bỏ trùng, giữ thứ tự."""
    if not q:
        return []
    terms = list(dict.fromkeys(fold(q.strip()[:MAX_QUERY_LEN]).split()))
    return terms[:MAX_TERMS]


def matches(haystack: str, terms: list[str]) -> bool:
    folded = fold(haystack)
    return all(t in folded for t in terms)


def _intervals(folded: str, terms: list[str]) -> list[tuple[int, int]]:
    spans = []
    for t in terms:
        i = folded.find(t)
        while i != -1:
            spans.append((i, i + len(t)))
            i = folded.find(t, i + len(t))
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def highlight(text: str | None, terms: list[str]):
    """Trả HTML đã escape, bọc chỗ khớp trong <mark class="hit">."""
    if not text:
        return ""
    if not terms:
        return text
    out, pos = [], 0
    for a, b in _intervals(fold(text), terms):
        out.append(escape(text[pos:a]))
        out.append(Markup('<mark class="hit">{}</mark>').format(text[a:b]))
        pos = b
    out.append(escape(text[pos:]))
    return Markup("").join(out)


_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_NOISE = re.compile(r"[`*_>#|]+")


def _plain(markdown: str) -> str:
    text = _MD_IMAGE.sub(" ", markdown)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _window(text: str, folded: str, anchor: str, terms: list[str]):
    """Cắt đoạn ~SNIPPET_WIDTH ký tự quanh lần khớp đầu tiên của `anchor`, rồi tô vàng."""
    pos = folded.find(anchor)
    if pos == -1:
        return None
    start = max(0, pos - SNIPPET_WIDTH // 3)
    if start > 0:  # lùi/tiến tới ranh giới từ để không cắt giữa chữ
        sp = text.find(" ", start)
        start = sp + 1 if 0 <= sp < pos else start
    end = min(len(text), start + SNIPPET_WIDTH)
    if end < len(text):
        sp = text.rfind(" ", pos + len(anchor), end)
        end = sp if sp > pos else end
    piece = text[start:end].strip()
    body = highlight(piece, terms)
    return Markup("{}{}{}").format("… " if start > 0 else "", body, " …" if end < len(text) else "")


def article_view(row, tags: list[str], terms: list[str]):
    """Quyết định bài này cần hiện đoạn trích không. Trả (khớp?, snippet|None).
    Đoạn trích chỉ hiện khi có từ khoá khớp ở chỗ KHÔNG nằm trong phần đang hiển thị
    (tiêu đề/tóm tắt/tác giả/tag) — vd. khớp trong nội dung bài hoặc bản tiếng Anh."""
    translated = row["status"] == "translated"
    shown_title = (row["title_vi"] or row["title"]) if translated else row["title"]
    shown_desc = (row["summary_vi"] if translated else row["summary_en"]) or ""
    visible = fold("\n".join([shown_title, shown_desc, row["author"] or "", *tags]))

    # Nguồn để tìm đoạn trích, ưu tiên bản đang hiển thị rồi tới bản còn lại.
    sources = [row["title"], row["summary_en"], row["summary_vi"], row["title_vi"]]
    contents = [row["content_vi"], row["content_en"]] if translated else [row["content_en"], row["content_vi"]]
    sources += contents

    everything = visible + "\n" + "\n".join(fold(s) for s in sources if s)
    if not all(t in everything for t in terms):
        return False, None

    missing = [t for t in terms if t not in visible]
    if not missing:
        return True, None
    for src in sources:
        if not src:
            continue
        text = _plain(src)
        folded = fold(text)
        for anchor in missing:
            snippet = _window(text, folded, anchor, terms)
            if snippet:
                return True, snippet
    return True, None
