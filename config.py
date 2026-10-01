"""Cấu hình app."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Token xác thực cho POST /admin/import (dùng bởi browser extension đưa bài bạn đang
# đọc vào app — xem extension/). Tự đặt chuỗi ngẫu nhiên dài. Đây là token "gốc" của
# chủ site; người khác được cấp token riêng qua /submit (xem token_requests trong db.py).
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "")

# Basic Auth riêng cho /admin/* (duyệt token request) — không áp dụng cho phần còn
# lại của site, vốn công khai hoàn toàn. Để trống thì /admin/* tự chặn (fail closed).
ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

# Email admin nhận thông báo khi có người yêu cầu cấp token qua /submit.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

# URL công khai của chính app này (dùng để build link trong email thông báo).
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "reader.db"))

MODEL_SUMMARIZE = os.getenv("MODEL_SUMMARIZE", "claude-haiku-4-5-20251001")
MODEL_TRANSLATE = os.getenv("MODEL_TRANSLATE", "claude-sonnet-5")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "claude-sonnet-5")
