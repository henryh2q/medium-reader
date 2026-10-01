"""Cấu hình app."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Token xác thực cho POST /admin/import (dùng bởi browser extension đưa bài bạn đang
# đọc vào app — xem extension/). Tự đặt chuỗi ngẫu nhiên dài, khác AUTH_PASS.
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "")

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "reader.db"))

MODEL_TRANSLATE = os.getenv("MODEL_TRANSLATE", "claude-sonnet-5")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "claude-sonnet-5")

# ---------- Deploy ----------
# Basic auth: đặt cả hai biến thì mọi trang đều yêu cầu đăng nhập
AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")
# Trên Railway mà quên đặt mật khẩu thì app từ chối phục vụ (fail closed)
ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))
