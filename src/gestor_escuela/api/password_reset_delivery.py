from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


def deliver_password_reset(email: str, token: str) -> None:
    """Send a one-time password reset link when SMTP is configured.

    Delivery is intentionally disabled unless SMTP_HOST and SMTP_FROM are both present. The
    token is never written to application logs by this module.
    """

    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return

    port = _int_env("SMTP_PORT", 587, minimum=1, maximum=65535)
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    use_starttls = _bool_env("SMTP_STARTTLS", True)
    frontend_url = os.getenv(
        "PASSWORD_RESET_FRONTEND_URL",
        "https://wolcenon.github.io/Horario-PT-AL/",
    ).strip()
    separator = "&" if "?" in frontend_url else "?"
    reset_url = f"{frontend_url}{separator}{urlencode({'reset_token': token})}"

    message = EmailMessage()
    message["Subject"] = "Restablecer contraseña · Planificador del centro"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Se ha solicitado restablecer la contraseña de tu cuenta.\n\n"
        f"Abre este enlace para elegir una contraseña nueva:\n{reset_url}\n\n"
        "Si no has solicitado este cambio, puedes ignorar este mensaje."
    )

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_starttls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
