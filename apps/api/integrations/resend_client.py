"""
integrations/resend_client.py — Resend Email API Client

Gửi email transactional qua Resend API (https://resend.com).
Free tier: 100 emails/ngày, 3,000 emails/tháng.

Dùng httpx async để không block event loop.
"""

import httpx
from typing import Optional
from core.logging import get_logger
from core.config import settings

logger = get_logger(__name__)

# Resend API endpoint
RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(
    to: str | list[str],
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Gửi email qua Resend API.

    Args:
        to:          Email người nhận (string hoặc list strings).
        subject:     Tiêu đề email.
        html:        Nội dung HTML của email.
        from_email:  Email người gửi (mặc định: settings.resend_from_email).
        reply_to:    Email reply-to.

    Returns:
        dict: Response từ Resend API {"id": "...", "from": "...", ...}

    Raises:
        RuntimeError: Nếu RESEND_API_KEY chưa cấu hình.
        httpx.HTTPStatusError: Nếu Resend API trả về lỗi.
    """
    if not settings.resend_api_key:
        # Mock mode — log thay vì gửi thật
        logger.info(
            "[MOCK EMAIL] Gửi email",
            extra={
                "event": "mock_email_sent",
                "to": to,
                "subject": subject,
            },
        )
        return {"id": "mock-email-id", "mock": True}

    sender = from_email or settings.resend_from_email
    recipients = [to] if isinstance(to, str) else to

    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            RESEND_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        result = response.json()
        logger.info(
            f"Email gửi thành công: {result.get('id')}",
            extra={"event": "email_sent", "email_id": result.get("id"), "to": recipients},
        )
        return result


async def send_evaluation_complete_email(
    to_email: str,
    user_name: str,
    meeting_title: str,
    meeting_status: str,
    reason: str,
    meeting_url: str,
) -> None:
    """
    Gửi email thông báo kết quả AI đánh giá cuộc họp.

    Args:
        to_email:       Email người nhận.
        user_name:      Tên người nhận.
        meeting_title:  Tên cuộc họp.
        meeting_status: READY hoặc RESCHEDULED.
        reason:         Lý do từ AI.
        meeting_url:    URL xem chi tiết cuộc họp.
    """
    is_ready = meeting_status == "READY"
    status_vi = "Sẵn sàng" if is_ready else "Cần dời lịch"
    status_color = "#22c55e" if is_ready else "#ef4444"
    status_icon = "✅" if is_ready else "⚠️"

    html = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kết quả đánh giá cuộc họp — MeetWise</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
             background-color: #f8fafc; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; 
                border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">🤝 MeetWise</h1>
            <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0;">
                AI đánh giá cuộc họp thông minh
            </p>
        </div>
        
        <!-- Content -->
        <div style="padding: 30px;">
            <p style="color: #374151; font-size: 16px;">Xin chào {user_name},</p>
            <p style="color: #374151;">
                AI của MeetWise vừa hoàn thành đánh giá cuộc họp 
                <strong>"{meeting_title}"</strong>.
            </p>
            
            <!-- Status Badge -->
            <div style="background: #f8fafc; border-left: 4px solid {status_color}; 
                        border-radius: 8px; padding: 20px; margin: 20px 0;">
                <div style="font-size: 28px; margin-bottom: 8px;">{status_icon}</div>
                <div style="font-size: 20px; font-weight: 700; color: {status_color};">
                    {status_vi}
                </div>
                <p style="color: #6b7280; margin: 8px 0 0; font-size: 14px;">
                    {reason}
                </p>
            </div>
            
            <!-- CTA -->
            <div style="text-align: center; margin: 30px 0;">
                <a href="{meeting_url}" 
                   style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white; padding: 12px 28px; border-radius: 8px;
                          text-decoration: none; font-weight: 600; font-size: 15px;
                          display: inline-block;">
                    Xem chi tiết cuộc họp →
                </a>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background: #f8fafc; padding: 20px; text-align: center; 
                    border-top: 1px solid #e5e7eb;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                © 2026 MeetWise · Xây dựng bởi Đoàn Hoàng Việt
            </p>
        </div>
    </div>
</body>
</html>
"""

    try:
        await send_email(
            to=to_email,
            subject=f"{status_icon} MeetWise: Cuộc họp '{meeting_title}' — {status_vi}",
            html=html,
        )
    except Exception as exc:
        # Email lỗi không được crash pipeline chính
        logger.error(
            f"Gửi email thất bại (non-critical): {exc}",
            extra={"event": "email_send_error", "to": to_email},
        )
