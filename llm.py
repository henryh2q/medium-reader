"""Các lời gọi Claude: dịch, giải thích thuật ngữ."""
import json
import re

from anthropic import Anthropic

import config

_client = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()  # đọc ANTHROPIC_API_KEY từ env
    return _client


def _call(model: str, system: str, user: str, max_tokens: int) -> str:
    resp = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


# ---------- 1. Dịch ----------

TRANSLATE_SYSTEM = """Translate the Markdown the user sends from English to Vietnamese,
for a Vietnamese software engineer.

Rules:
- Keep the Markdown structure exactly: headings, lists, links, images, tables, emphasis.
- Never translate or change fenced code blocks, inline code, URLs or image paths.
- Keep established technical terms in English (agent, pull request, N+1 query,
  dependency injection, harness...). Do not force-translate jargon.
- Natural, concise Vietnamese. No additions, no notes, no commentary.
Output only the translated Markdown."""


def split_markdown(md: str, limit: int = 5000) -> list[str]:
    """Cắt theo đoạn văn, không bao giờ cắt giữa code block."""
    blocks, cur, in_fence = [], [], False
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip() and cur:
            blocks.append("\n".join(cur))
            cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))

    chunks, buf = [], ""
    for b in blocks:
        if buf and len(buf) + len(b) + 2 > limit:
            chunks.append(buf)
            buf = b
        else:
            buf = f"{buf}\n\n{b}" if buf else b
    if buf:
        chunks.append(buf)
    return chunks


def translate_markdown(md: str) -> str:
    parts = [_call(config.MODEL_TRANSLATE, TRANSLATE_SYSTEM, chunk, 8000).strip()
             for chunk in split_markdown(md)]
    return "\n\n".join(parts)


# ---------- 2. Giải thích thuật ngữ ----------

EXPLAIN_SYSTEM = """You explain technical terms to a Vietnamese backend developer
(PHP/Laravel, Python/Django) who is reading an English tech article and wants to truly
understand a term, the way they would otherwise search Google for it.

Write in Vietnamese. Keep the term itself and other jargon in English.
Use the article title and the surrounding paragraph to choose the right meaning.
If the selection is a phrase rather than a term, explain the phrase.

Return ONLY JSON:
{"term": "<the term>",
 "short": "<one-sentence definition>",
 "detail": "<clear explanation, 2 short paragraphs separated by \\n\\n: what it is, why it matters, how it works>",
 "analogy": "<an everyday comparison that makes it click>",
 "example": "<a concrete, realistic scenario a backend developer would meet>",
 "code": null or {"lang": "php|python|sql|bash|...", "snippet": "<max 15 lines>"},
 "in_this_article": "<1-2 sentences: what the term means in this article>"}
Include code only when it genuinely helps; prefer PHP/Laravel or Python."""


def explain_term(term: str, context: str, article_title: str) -> dict:
    user = (f"Article: {article_title}\n"
            f"Term: {term}\n\n"
            f"Paragraph containing it:\n{context[:1500]}")
    return _parse_json(_call(config.MODEL_EXPLAIN, EXPLAIN_SYSTEM, user, 1500))
