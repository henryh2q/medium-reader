"""Cấu hình app."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Token xác thực cho POST /admin/import (dùng bởi browser extension đưa bài bạn đang
# đọc vào app — xem extension/). Tự đặt chuỗi ngẫu nhiên dài.
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "")

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "reader.db"))

MODEL_SUMMARIZE = os.getenv("MODEL_SUMMARIZE", "claude-haiku-4-5-20251001")
MODEL_TRANSLATE = os.getenv("MODEL_TRANSLATE", "claude-sonnet-5")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "claude-sonnet-5")
