"""Cấu hình app. Sửa FEEDS và INTERESTS cho hợp gu đọc của bạn."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# RSS của Medium: /feed/tag/<tag>, /feed/<publication>, /feed/@<username>
FEEDS = [
    "https://medium.com/feed/tag/software-engineering",
    "https://medium.com/feed/tag/software-architecture",
    "https://medium.com/feed/tag/system-design",
    "https://medium.com/feed/tag/laravel",
    "https://medium.com/feed/tag/python",
    "https://medium.com/feed/tag/ai-agents",
    "https://medium.com/feed/tag/llm",
]

# Mô tả mối quan tâm — model dùng để chấm điểm độ liên quan
INTERESTS = os.getenv(
    "INTERESTS",
    "backend engineering, PHP/Laravel, Python/Django, AI engineering, "
    "agentic systems, system design, code quality, code review, team leadership",
)

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "reader.db"))

MODEL_SCORE = os.getenv("MODEL_SCORE", "claude-haiku-4-5-20251001")
MODEL_TRANSLATE = os.getenv("MODEL_TRANSLATE", "claude-sonnet-5")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "claude-sonnet-5")

SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "7"))       # 1–10
MAX_TRANSLATE_PER_RUN = int(os.getenv("MAX_TRANSLATE_PER_RUN", "3"))
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
