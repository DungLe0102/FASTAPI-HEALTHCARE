"""
Utility helpers — aligned with full-stack-fastapi-template.
Bao gồm email sending, password-reset token generation/verification.
"""
import logging
import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


# ── Email sending ─────────────────────────────────────────────────────────────

def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    """Send an email via SMTP. Only called when settings.emails_enabled is True."""
    assert settings.emails_enabled, "No SMTP configuration provided"
    try:
        import emails  # type: ignore[import-untyped]
        message = emails.Message(
            subject=subject,
            html=html_content,
            mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
        )
        smtp_options: dict[str, Any] = {
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
        }
        if settings.SMTP_TLS:
            smtp_options["tls"] = True
        elif settings.SMTP_SSL:
            smtp_options["ssl"] = True
        if settings.SMTP_USER:
            smtp_options["user"] = settings.SMTP_USER
        if settings.SMTP_PASSWORD:
            smtp_options["password"] = settings.SMTP_PASSWORD
        response = message.send(to=email_to, smtp=smtp_options)
        logger.info(f"send email result: {response}")
    except ImportError:
        logger.warning("python-emails not installed — email not sent")


# ── Email content builders ────────────────────────────────────────────────────

def generate_new_account_email(
    email_to: str, full_name: str | None, password: str
) -> EmailData:
    project_name = settings.APP_NAME
    name = full_name or email_to
    subject = f"{project_name} - New account created"
    html_content = f"""
    <h2>Welcome to {project_name}, {name}!</h2>
    <p>Your account has been created.</p>
    <ul>
        <li><strong>Email:</strong> {email_to}</li>
        <li><strong>Password:</strong> {password}</li>
    </ul>
    <p>Please log in and change your password immediately.</p>
    <p><a href="{settings.FRONTEND_HOST}">Go to {project_name}</a></p>
    """
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(
    email_to: str, email: str, token: str
) -> EmailData:
    project_name = settings.APP_NAME
    subject = f"{project_name} - Password recovery for {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = f"""
    <h2>Password Recovery</h2>
    <p>Hi,</p>
    <p>Click the link below to reset your password. This link expires in
    {settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS} hours.</p>
    <p><a href="{link}">Reset Password</a></p>
    <p>If you did not request this, ignore this email.</p>
    """
    return EmailData(html_content=html_content, subject=subject)


# ── Password-reset token (JWT) ────────────────────────────────────────────────

def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    encoded_jwt = jwt.encode(
        {"exp": expires.timestamp(), "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return str(decoded["sub"])
    except InvalidTokenError:
        return None


# ── OTP helpers ──────────────────────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Sinh mã OTP gồm chữ số, độ dài mặc định 6."""
    return "".join(random.choices(string.digits, k=length))


def generate_otp_email(email_to: str, otp: str, full_name: str | None = None) -> EmailData:
    """Email template gửi OTP xác minh địa chỉ email."""
    name = full_name or email_to
    subject = f"{settings.APP_NAME} - Xác minh email của bạn"
    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                border:1px solid #e2e8f0;border-radius:12px;background:#fff">
      <h2 style="color:#2d3748;margin-bottom:8px">✉️ Xác minh Email</h2>
      <p style="color:#4a5568">Xin chào <strong>{name}</strong>,</p>
      <p style="color:#4a5568">Mã OTP xác minh email của bạn là:</p>
      <div style="text-align:center;margin:24px 0">
        <span style="font-size:40px;font-weight:bold;letter-spacing:12px;
                     color:#4f46e5;background:#eef2ff;padding:16px 24px;
                     border-radius:8px;display:inline-block">{otp}</span>
      </div>
      <p style="color:#718096;font-size:14px">⏰ Mã có hiệu lực trong <strong>15 phút</strong>.</p>
      <p style="color:#718096;font-size:14px">🔒 Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email này.</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
      <p style="color:#a0aec0;font-size:12px;text-align:center">{settings.APP_NAME}</p>
    </div>
    """
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_otp_email(email_to: str, otp: str, full_name: str | None = None) -> EmailData:
    """Email template gửi OTP đặt lại mật khẩu."""
    name = full_name or email_to
    subject = f"{settings.APP_NAME} - Đặt lại mật khẩu"
    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                border:1px solid #e2e8f0;border-radius:12px;background:#fff">
      <h2 style="color:#2d3748;margin-bottom:8px">🔑 Đặt lại mật khẩu</h2>
      <p style="color:#4a5568">Xin chào <strong>{name}</strong>,</p>
      <p style="color:#4a5568">Chúng tôi nhận được yêu cầu đặt lại mật khẩu. Mã OTP của bạn là:</p>
      <div style="text-align:center;margin:24px 0">
        <span style="font-size:40px;font-weight:bold;letter-spacing:12px;
                     color:#dc2626;background:#fef2f2;padding:16px 24px;
                     border-radius:8px;display:inline-block">{otp}</span>
      </div>
      <p style="color:#718096;font-size:14px">⏰ Mã có hiệu lực trong <strong>15 phút</strong>.</p>
      <p style="color:#718096;font-size:14px">🚨 Nếu bạn không yêu cầu, hãy đổi mật khẩu ngay và liên hệ hỗ trợ.</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
      <p style="color:#a0aec0;font-size:12px;text-align:center">{settings.APP_NAME}</p>
    </div>
    """
    return EmailData(html_content=html_content, subject=subject)
def generate_notification_email(
    email_to: str, title: str, content: str, full_name: str | None = None
) -> EmailData:
    """Email template chung cho các thông báo hệ thống."""
    name = full_name or email_to
    subject = f"{settings.APP_NAME} - {title}"
    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:24px;
                border:1px solid #edf2f7;border-radius:8px;background:#f8fafc">
      <div style="background:#fff;padding:32px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05)">
        <h2 style="color:#1a202c;margin-top:0">{title}</h2>
        <p style="color:#4a5568">Xin chào <strong>{name}</strong>,</p>
        <div style="color:#2d3748;line-height:1.6;margin:24px 0;padding:16px;
                    background:#f1f5f9;border-left:4px solid #4f46e5;border-radius:4px">
          {content}
        </div>
        <p style="color:#718096;font-size:14px">Bạn nhận được thông báo này vì là thành viên của hệ thống {settings.APP_NAME}.</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:32px 0">
        <p style="color:#a0aec0;font-size:12px;text-align:center">
          © {datetime.now().year} {settings.APP_NAME}. All rights reserved.
        </p>
      </div>
    </div>
    """
    return EmailData(html_content=html_content, subject=subject)
