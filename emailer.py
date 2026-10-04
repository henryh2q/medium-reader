"""Gửi email thông báo qua Resend API (https://resend.com)."""
import html as html_lib
import logging

import httpx

import config

log = logging.getLogger("emailer")

RESEND_URL = "https://api.resend.com/emails"
# Resend chỉ cho gửi từ domain đã xác minh, hoặc dùng domain test có sẵn này khi
# chưa verify domain riêng (chỉ gửi được tới chính email đăng ký tài khoản Resend).
FROM_ADDRESS = "Đọc gì hôm nay <onboarding@resend.dev>"


def _send(subject: str, html: str) -> bool:
    """Trả False nếu chưa cấu hình RESEND_API_KEY/ADMIN_EMAIL hoặc gửi lỗi — không
    raise, vì gửi email luôn là tác vụ phụ, không nên chặn luồng chính."""
    if not (config.RESEND_API_KEY and config.ADMIN_EMAIL):
        log.warning("Chưa cấu hình RESEND_API_KEY/ADMIN_EMAIL, bỏ qua gửi email.")
        return False
    try:
        resp = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            json={"from": FROM_ADDRESS, "to": [config.ADMIN_EMAIL], "subject": subject, "html": html},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        log.exception("Gửi email '%s' thất bại", subject)
        return False


def send_token_request_notice(request_id: str, note: str) -> bool:
    """Báo cho admin có người vừa yêu cầu cấp IMPORT_TOKEN."""
    admin_link = f"{config.PUBLIC_URL}/admin/requests" if config.PUBLIC_URL else "/admin/requests"
    body = (
        f"<p>Có người vừa yêu cầu IMPORT_TOKEN.</p>"
        f"<p><b>Request ID:</b> {html_lib.escape(request_id)}</p>"
        f"<p><b>Ghi chú:</b> {html_lib.escape(note) or '(không có)'}</p>"
        f"<p><a href=\"{admin_link}\">Duyệt tại {admin_link}</a></p>"
    )
    return _send("Yêu cầu cấp token — Đọc gì hôm nay", body)


def send_submission_notice(url: str, note: str) -> bool:
    """Báo cho admin có URL mới trong hàng đợi."""
    admin_link = f"{config.PUBLIC_URL}/admin/queue" if config.PUBLIC_URL else "/admin/queue"
    body = (
        f"<p>Có link mới trong hàng đợi.</p>"
        f"<p><b>Link:</b> {html_lib.escape(url)}</p>"
        f"<p><b>Ghi chú:</b> {html_lib.escape(note) or '(không có)'}</p>"
        f"<p><a href=\"{admin_link}\">Xử lý tại {admin_link}</a></p>"
    )
    return _send("Link mới trong hàng đợi — Đọc gì hôm nay", body)


def send_feedback_notice(kind: str, message: str, contact: str) -> bool:
    """Báo cho admin có người gửi báo cáo sự cố / đóng góp ý kiến."""
    label = "Báo cáo sự cố" if kind == "bug" else "Đóng góp ý tưởng"
    body = (
        f"<p><b>Loại:</b> {label}</p>"
        f"<p><b>Liên hệ:</b> {html_lib.escape(contact) or '(không có)'}</p>"
        f"<p><b>Nội dung:</b></p><p>{html_lib.escape(message)}</p>"
    )
    return _send(f"{label} — Đọc gì hôm nay", body)
