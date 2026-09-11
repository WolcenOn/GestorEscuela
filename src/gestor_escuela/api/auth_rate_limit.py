from __future__ import annotations

import hashlib
import math
import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from gestor_escuela.persistence.auth_models import LoginThrottleRow


def check_login_allowed(session: Session, email: str, *, now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    row = session.get(LoginThrottleRow, _login_key(email))
    if row is None or row.blocked_until is None:
        return
    blocked_until = _aware(row.blocked_until)
    if blocked_until <= current:
        return
    retry_after = max(1, math.ceil((blocked_until - current).total_seconds()))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


def register_login_failure(
    session: Session,
    email: str,
    *,
    now: datetime | None = None,
) -> LoginThrottleRow:
    current = now or datetime.now(UTC)
    key_hash = _login_key(email)
    row = session.get(LoginThrottleRow, key_hash)
    window = _window_duration()

    if row is None:
        row = LoginThrottleRow(
            key_hash=key_hash,
            failures=1,
            window_started_at=current,
            blocked_until=None,
        )
        session.add(row)
    elif current - _aware(row.window_started_at) >= window:
        row.failures = 1
        row.window_started_at = current
        row.blocked_until = None
    else:
        row.failures += 1

    if row.failures >= _max_failures():
        row.blocked_until = current + _block_duration()
    session.flush()
    return row


def clear_login_failures(session: Session, email: str) -> None:
    row = session.get(LoginThrottleRow, _login_key(email))
    if row is not None:
        session.delete(row)
        session.flush()


def _login_key(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def _max_failures() -> int:
    return _bounded_int("AUTH_LOGIN_MAX_FAILURES", default=5, minimum=2, maximum=100)


def _window_duration() -> timedelta:
    minutes = _bounded_int(
        "AUTH_LOGIN_WINDOW_MINUTES", default=15, minimum=1, maximum=24 * 60
    )
    return timedelta(minutes=minutes)


def _block_duration() -> timedelta:
    minutes = _bounded_int(
        "AUTH_LOGIN_BLOCK_MINUTES", default=15, minimum=1, maximum=24 * 60
    )
    return timedelta(minutes=minutes)


def _bounded_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
