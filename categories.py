"""Gộp các tag chi tiết về 2 category chính hiển thị trên trang chủ: AI, System Design.
Tag chi tiết vẫn giữ nguyên trên từng bài và trong bộ lọc theo tag (`/?tag=`) — category
chỉ là một lớp lọc thô hơn, dựa theo từ khoá trong tên tag, không cần sinh thêm bằng LLM."""

CATEGORIES = ["AI", "System Design"]

_KEYWORDS: dict[str, list[str]] = {
    "AI": ["ai", "artificial intelligence", "agent", "llm", "machine learning", "ml",
           "data science", "prompt", "model", "generative"],
    "System Design": ["system design", "architecture", "distributed", "scalab",
                       "large-scale", "microservice", "scheduler", "infrastructure",
                       "database", "kafka", "queue"],
}


def category_for_tag(tag_name: str) -> str | None:
    lower = tag_name.lower()
    for category, keywords in _KEYWORDS.items():
        if any(k in lower for k in keywords):
            return category
    return None


def categories_for_tags(tag_names: list[str]) -> list[str]:
    """Danh sách category (giữ thứ tự CATEGORIES) mà ít nhất 1 tag của bài khớp vào."""
    matched = {category_for_tag(t) for t in tag_names}
    return [c for c in CATEGORIES if c in matched]
