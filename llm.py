"""Các lời gọi Claude: dịch, giải thích thuật ngữ."""
import base64
import html
import io
import json
import re
import zipfile
from datetime import date

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


# ---------- 1. Tóm tắt + tag ----------

SUMMARIZE_SYSTEM = """You help a software engineer triage a reading list.

Given an article's title and content, produce:
- A 1-2 sentence summary in English capturing what's genuinely useful or new in it,
  not a generic restatement of the title.
- 2-3 short topic tags (English, Title Case, e.g. "System Design", "AI Agents",
  "Career Growth") that best categorize the article for filtering a reading list.

Return ONLY JSON: {"summary": "<1-2 sentences>", "tags": ["<tag1>", "<tag2>"]}"""


def summarize_article(title: str, content: str) -> dict:
    """Trả về {"summary": str, "tags": list[str]}."""
    user = f"Title: {title}\n\nContent:\n{content[:3000]}"
    data = _parse_json(_call(config.MODEL_SUMMARIZE, SUMMARIZE_SYSTEM, user, 300))
    return {
        "summary": (data.get("summary") or "").strip(),
        "tags": [t.strip() for t in data.get("tags", []) if t.strip()][:3],
    }


# ---------- 2. Dịch ----------

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


TRANSLATE_TITLE_SUMMARY_SYSTEM = """Translate the article title and summary from English
to Vietnamese, for a Vietnamese software engineer. Natural, concise Vietnamese; keep
established technical terms in English (agent, pull request, N+1 query...).

Return ONLY JSON: {"title_vi": "<translated title>", "summary_vi": "<translated summary>"}"""


def translate_title_summary(title: str, summary: str) -> dict:
    user = f"Title: {title}\n\nSummary: {summary}"
    return _parse_json(_call(config.MODEL_TRANSLATE, TRANSLATE_TITLE_SUMMARY_SYSTEM, user, 500))


# ---------- 3. Giải thích thuật ngữ ----------

EXPLAIN_SYSTEM = """You explain technical terms to a Vietnamese backend developer
(PHP/Laravel, Python/Django) who is reading an English tech article and wants to truly
understand a term, the way they would otherwise search Google for it.

Write in Vietnamese. Keep the term itself and other jargon in English.
Use the article title and the surrounding paragraph to choose the right meaning.
If the selection is a phrase rather than a term, explain the phrase.

If the term is an English word/phrase with a non-obvious pronunciation for a
Vietnamese speaker, include IPA plus a simple Vietnamese-spelling approximation of the
sound (the way Vietnamese dictionaries romanize English pronunciation, e.g. "cache" ->
"/kæʃ/" and "kiếts" or similar — approximate, optimized for a Vietnamese reader to say
it out loud, not for phonetic precision). Omit pronunciation for acronyms read letter by
letter (API, SQL) or terms that are not really "spoken" as English words.

Return ONLY JSON:
{"term": "<the term>",
 "pronunciation": null or {"ipa": "<IPA, e.g. /kæʃ/>", "vi": "<cách đọc phỏng theo tiếng Việt>"},
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


# ---------- 4. Tóm tắt ý chính cả bài ----------

KEYPOINTS_SYSTEM = """You summarize a technical article for a Vietnamese software engineer
who wants the gist before deciding to read it in full.

Write in Vietnamese; keep established technical terms in English. Be concrete: name the
actual techniques, numbers and conclusions from the article, not generic statements.

Return ONLY JSON:
{"tldr": "<1-2 sentence overall takeaway>",
 "points": ["<key point 1>", "... 4 to 7 points, each one self-contained sentence, in the article's order"]}"""

_KEYPOINTS_MAX_CHARS = 60_000


def summarize_key_points(title: str, content: str) -> dict:
    """Trả về {"tldr": str, "points": list[str]}."""
    user = f"Title: {title}\n\nArticle:\n{content[:_KEYPOINTS_MAX_CHARS]}"
    data = _parse_json(_call(config.MODEL_SUMMARIZE, KEYPOINTS_SYSTEM, user, 1200))
    return {
        "tldr": (data.get("tldr") or "").strip(),
        "points": [p.strip() for p in data.get("points", []) if isinstance(p, str) and p.strip()],
    }



# ---------- 5. Trích xuất tin tuyển dụng ----------

JOB_EXTRACT_SYSTEM = """You extract ONE job posting into a fixed JSON format for a Vietnamese IT job board.
The input is whatever the admin pasted or uploaded: a Facebook/LinkedIn post, an email, a
full JD, a PDF, a screenshot. Today is {today}.

Rules:
- Use only what the source says. Never invent a company, salary, contact or deadline. If a
  field is not in the source use null / "" / [].
- Keep the source language for text (Vietnamese stays Vietnamese, English stays English); do
  not translate. Write bullets as short, self-contained lines without bullet symbols/emoji.
- If the source holds several jobs, extract the first/most complete one and say so in notes.
- mode: "remote" | "hybrid" | "onsite" | null.
- type: "Full-time" | "Part-time" | "Contract" | "Intern" | null.
- level: short label such as "Intern", "Fresher / Junior", "Mid", "Senior", "Lead+", "Mid – Senior".
- location: normalized city, e.g. "TP. Hồ Chí Minh" (HCM, Sài Gòn, Q.7 -> that), "Hà Nội", "Đà Nẵng".
- salary: min/max as plain numbers. unit "triệu VND" (40-60tr -> 40 and 60) or "USD". per: "tháng" |
  "năm" | "giờ". negotiable=true when the source says negotiable/thoả thuận and gives no figure.
- deadline: YYYY-MM-DD; assume the nearest upcoming year when the year is missing.
- skills: canonical technology names (Go, Kubernetes, PostgreSQL, Spring Boot...), at most 10.
- description / requirements / benefits: lists of lines, split into the right section.
- contact: email, phone, person (name + role if given), link (application URL). Copy exactly.
- inferred: names of fields you had to GUESS rather than read (e.g. "type", "level", "mode",
  "company"). Fields stated explicitly in the source must not be listed.
- notes: 0-4 short Vietnamese remarks the admin should know (normalizations done, ambiguity,
  missing key info, multiple jobs found).

Return ONLY JSON:
{{"title": "", "company": "", "location": "", "mode": null, "level": "", "type": null,
 "salary": {{"min": null, "max": null, "unit": "triệu VND", "per": "tháng", "negotiable": false}},
 "headcount": null, "deadline": null, "skills": [],
 "description": [], "requirements": [], "benefits": [],
 "contact": {{"email": "", "phone": "", "person": "", "link": ""}},
 "inferred": [], "notes": []}}"""

_IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}
JOB_FILE_EXTS = ("pdf", "docx", "txt", "md", *_IMAGE_TYPES)


def _docx_text(data: bytes) -> str:
    """Lấy chữ từ .docx (zip + XML), không cần thư viện ngoài."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>|<w:br\s*/>|<w:tab\s*/>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def extract_job(text: str, filename: str = "", data: bytes | None = None) -> dict:
    """Đọc text và/hoặc 1 file (pdf, docx, txt/md, ảnh) rồi trả về dict thô theo định dạng
    ở JOB_EXTRACT_SYSTEM. Việc làm sạch/kiểm tra giá trị do jobs.py đảm nhiệm."""
    content: list[dict] = []
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = text.strip()
    if data:
        if ext == "pdf":
            content.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode()}})
        elif ext in _IMAGE_TYPES:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": _IMAGE_TYPES[ext],
                "data": base64.standard_b64encode(data).decode()}})
        elif ext == "docx":
            text = f"{text}\n\n{_docx_text(data)}".strip()
        else:  # txt / md
            text = f"{text}\n\n{data.decode('utf-8', 'replace')}".strip()
    if text:
        content.append({"type": "text", "text": f"Job posting text:\n{text[:40_000]}"})
    if not content:
        raise ValueError("Không có nội dung để trích xuất.")
    resp = client().messages.create(
        model=config.MODEL_JOB,
        max_tokens=2500,
        system=JOB_EXTRACT_SYSTEM.format(today=date.today().isoformat()),
        messages=[{"role": "user", "content": content}],
    )
    return _parse_json("".join(b.text for b in resp.content if b.type == "text"))
