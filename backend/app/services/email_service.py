"""Optional SMTP helpers for password recovery."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import load_settings


def smtp_configured() -> bool:
    """Return whether outbound email is configured."""
    settings = load_settings()
    return bool(
        settings.smtp_host
        and settings.smtp_from_email
        and settings.smtp_password
    )


def _to_ascii_email(address: str) -> str:
    """Convert an email address to ASCII (punycode domain if needed)."""
    local, separator, domain = address.partition("@")
    if not separator:
        return address

    try:
        ascii_domain = domain.strip().encode("idna").decode("ascii")
    except UnicodeError:
        ascii_domain = domain.strip()

    return f"{local}@{ascii_domain}"


def send_password_reset_email(*, recipient: str, reset_url: str) -> None:
    """Send a password reset link to the user."""
    settings = load_settings()
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured.")

    from_email = settings.smtp_from_email or ""
    from_ascii = _to_ascii_email(from_email)
    login_user = _to_ascii_email(settings.smtp_username or from_email)

    message = EmailMessage()
    message["Subject"] = "Восстановление пароля"
    message["From"] = formataddr(("Медицинский консультант", from_ascii))
    message["To"] = recipient
    message.set_content(
        "Вы запросили восстановление пароля.\n\n"
        f"Перейдите по ссылке, чтобы задать новый пароль:\n{reset_url}\n\n"
        "Если вы не запрашивали восстановление, просто проигнорируйте это письмо."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if login_user and settings.smtp_password:
            smtp.login(login_user, settings.smtp_password)
        smtp.send_message(message)


def send_admin_notification_email(
    *,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Send an administrative notification email."""
    settings = load_settings()
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured.")

    from_email = settings.smtp_from_email or ""
    from_ascii = _to_ascii_email(from_email)
    login_user = _to_ascii_email(settings.smtp_username or from_email)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("Медицинский консультант", from_ascii))
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if login_user and settings.smtp_password:
            smtp.login(login_user, settings.smtp_password)
        smtp.send_message(message)
