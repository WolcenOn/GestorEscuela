from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_RESEND_API_URL = "https://api.resend.com/emails"


def deliver_password_reset(email: str, token: str) -> None:
    """Send a one-time password reset link through the Resend HTTPS API.

    Delivery is intentionally disabled unless RESEND_API_KEY and EMAIL_FROM are both present.
    The token is only included in the outbound message body and is never written to application
    logs by this module.
    """

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "").strip()
    if not api_key or not sender:
        return

    frontend_url = os.getenv(
        "PASSWORD_RESET_FRONTEND_URL",
        "https://wolcenon.github.io/Horario-PT-AL/",
    ).strip()
    separator = "&" if "?" in frontend_url else "?"
    reset_url = f"{frontend_url}{separator}{urlencode({'reset_token': token})}"

    payload = json.dumps(
        {
            "from": sender,
            "to": [email],
            "subject": "Restablecer contraseña · Planificador del centro",
            "text": (
                "Se ha solicitado restablecer la contraseña de tu cuenta.\n\n"
                "Abre este enlace para elegir una contraseña nueva:\n"
                f"{reset_url}\n\n"
                "Si no has solicitado este cambio, puedes ignorar este mensaje."
            ),
        }
    ).encode("utf-8")

    request = Request(
        _RESEND_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "GestorEscuela/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed HTTPS provider endpoint.
        response.read()
