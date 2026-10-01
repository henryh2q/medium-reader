"""Chạy pipeline hằng ngày trong web process.

Railway không cho 2 service dùng chung 1 volume, nên cron service riêng
không đọc/ghi được file SQLite. Vì vậy pipeline chạy ngay trong service web.
Yêu cầu: chỉ 1 replica, và tắt chế độ Serverless (app sleeping).
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import pipeline

log = logging.getLogger("scheduler")
_lock = threading.Lock()


def next_run(now: datetime, hour: int) -> datetime:
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def run_now() -> bool:
    """Chạy pipeline ở thread nền. Trả về False nếu đang có lượt khác chạy."""
    if not _lock.acquire(blocking=False):
        return False

    def job():
        try:
            log.info("Pipeline bắt đầu")
            pipeline.run_all()
            log.info("Pipeline xong")
        except Exception:
            log.exception("Pipeline lỗi")
        finally:
            _lock.release()

    threading.Thread(target=job, daemon=True).start()
    return True


def is_running() -> bool:
    return _lock.locked()


def _loop() -> None:
    tz = ZoneInfo(config.TZ)
    while True:
        now = datetime.now(tz)
        nxt = next_run(now, config.PIPELINE_HOUR)
        log.info("Lượt chạy kế tiếp: %s", nxt.isoformat())
        time.sleep((nxt - now).total_seconds())
        run_now()


def start() -> None:
    if config.PIPELINE_HOUR < 0:
        return
    threading.Thread(target=_loop, daemon=True, name="scheduler").start()
