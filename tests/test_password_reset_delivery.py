from __future__ import annotations

import json
from typing import Any

from gestor_escuela.api import password_reset_delivery


class _FakeResponse:
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"id":"email_123"}'


def test_delivery_is_disabled_without_resend_configuration(monkeypatch: Any) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)

    called = False

    def fake_urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        nonlocal called
        called = True
        return _FakeResponse()

    monkeypatch.setattr(password_reset_delivery, "urlopen", fake_urlopen)

    password_reset_delivery.deliver_password_reset("user@example.test", "secret-token")

    assert called is False


def test_delivery_uses_resend_https_api(monkeypatch: Any) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_secret")
    monkeypatch.setenv("EMAIL_FROM", "Planificador del centro <no-reply@example.test>")
    monkeypatch.setenv(
        "PASSWORD_RESET_FRONTEND_URL",
        "https://example.test/app/?view=account",
    )
    captured: dict[str, object] = {}

    def fake_urlopen(request: Any, *, timeout: int) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(password_reset_delivery, "urlopen", fake_urlopen)

    password_reset_delivery.deliver_password_reset("user@example.test", "secret token+/=")

    request = captured["request"]
    assert captured["timeout"] == 15
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "Bearer re_test_secret"
    assert request.headers["Content-type"] == "application/json"

    payload = json.loads(request.data.decode("utf-8"))
    assert payload["from"] == "Planificador del centro <no-reply@example.test>"
    assert payload["to"] == ["user@example.test"]
    assert payload["subject"] == "Restablecer contraseña · Planificador del centro"
    assert "reset_token=secret+token%2B%2F%3D" in payload["text"]
    assert "view=account&reset_token=" in payload["text"]
