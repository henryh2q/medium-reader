"""Cấu hình app. Sửa FEEDS và INTERESTS cho hợp gu đọc của bạn."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# RSS tập trung vào: system design, interview software engineering, AI
# (coding agent harness, AI SDLC, AI agent, AI workflow)
FEEDS = [
    "https://blog.bytebytego.com/feed",            # system design
    "https://martinfowler.com/feed.atom",           # system design / architecture
    "https://blog.pragmaticengineer.com/rss/",      # interview, career, system design
    "https://simonwillison.net/atom/everything/",   # AI agent / coding harness
    "https://blog.langchain.dev/rss.xml",           # AI agent / workflow
    "https://www.latent.space/feed",                # AI engineering / AI SDLC
    "https://feed.infoq.com/ai-ml-data-eng/",       # AI
    "https://medium.com/feed/tag/system-design",    # Medium: system design
    "https://medium.com/feed/tag/ai-agents",        # Medium: AI agent
    "https://medium.com/feed/tag/coding-interviews",  # Medium: interview
]

# Token xác thực cho POST /admin/import (dùng bởi browser extension đưa bài member-only
# bạn đang đọc vào app — xem extension/). Tự đặt chuỗi ngẫu nhiên dài, khác AUTH_PASS.
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "")

# Mô tả mối quan tâm — model dùng để chấm điểm độ liên quan
INTERESTS = os.getenv(
    "INTERESTS",
    "system design, software engineering interview (system design interview, "
    "coding/algorithm interview, behavioral & career interview for senior/staff engineers), "
    "AI coding agent harness (Claude Code, Cursor, Devin, OpenHands...), AI SDLC "
    "(AI trong vòng đời phát triển phần mềm), AI agents, AI workflow automation",
)

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "reader.db"))

MODEL_SCORE = os.getenv("MODEL_SCORE", "claude-haiku-4-5-20251001")
MODEL_TRANSLATE = os.getenv("MODEL_TRANSLATE", "claude-sonnet-5")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "claude-sonnet-5")

SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "7"))       # 1–10
MAX_TRANSLATE_PER_RUN = int(os.getenv("MAX_TRANSLATE_PER_RUN", "3"))
MAX_NEW_ARTICLES_PER_RUN = int(os.getenv("MAX_NEW_ARTICLES_PER_RUN", "10"))  # tổng số bài mới nhất lấy mỗi lần fetch (gộp mọi feed)
MIN_WORDS_FULL = 400   # ít hơn số từ này => coi là bài bị cắt (member-only)

# ---------- Deploy ----------
# Basic auth: đặt cả hai biến thì mọi trang đều yêu cầu đăng nhập
AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")
# Trên Railway mà quên đặt mật khẩu thì app từ chối phục vụ (fail closed)
ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))

# Pipeline chạy ngay trong web process mỗi ngày lúc PIPELINE_HOUR (theo TZ).
# Đặt -1 để tắt (khi chạy local bằng cron).
PIPELINE_HOUR = int(os.getenv("PIPELINE_HOUR", "-1"))
TZ = os.getenv("TZ_NAME", "Asia/Ho_Chi_Minh")
