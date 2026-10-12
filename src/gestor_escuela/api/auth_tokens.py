from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gestor_escuela.persistence.auth_models import AuthSessionRow, UserCredentialRow
from gestor_escuela.persistence.models import UserRow

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, salt_hex, digest_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_ttl() -> timedelta:
    raw = os.getenv("AUTH_SESSION_TTL_HOURS", "12")
    try:
        hours = int(raw)
    except ValueError:
        hours = 12
    return timedelta(hours=max(1, min(24 * 30, hours)))


def session_idle_timeout() -> timedelta:
    raw = os.getenv("AUTH_SESSION_IDLE_MINUTES", "120")
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 120
    return timedelta(minutes=max(5, min(24 * 7 * 60, minutes)))


def session_touch_interval() -> timedelta:
    raw = os.getenv("AUTH_SESSION_TOUCH_INTERVAL_MINUTES", "5")
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 5
    return timedelta(minutes=max(1, min(60, minutes)))


def issue_session(session: Session, user_id: UUID) -> tuple[str, AuthSessionRow]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    row = AuthSessionRow(
        user_id=user_id,
        token_hash=token_digest(token),
        expires_at=now + session_ttl(),
        last_seen_at=now,
    )
    session.add(row)
    session.flush()
    return token, row


def bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required",
        )
    return value.strip()


def authenticated_user(
    session: Session,
    authorization: str | None,
) -> tuple[UserRow, AuthSessionRow] | None:
    token = bearer_token(authorization)
    if token is None:
        return None
    auth_session = session.scalar(
        select(AuthSessionRow).where(AuthSessionRow.token_hash == token_digest(token))
    )
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or _aware(auth_session.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session is invalid or expired",
        )
    last_seen_at = _aware(auth_session.last_seen_at)
    if last_seen_at + session_idle_timeout() <= now:
        auth_session.revoked_at = now
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session is invalid or expired",
        )
    credential = session.get(UserCredentialRow, auth_session.user_id)
    user = session.get(UserRow, auth_session.user_id)
    if user is None or credential is None or not credential.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not active",
        )
    if now - last_seen_at >= session_touch_interval():
        auth_session.last_seen_at = now
        session.commit()
    return user, auth_session


def require_authenticated_user(
    session: Session,
    authorization: str | None,
) -> tuple[UserRow, AuthSessionRow]:
    result = authenticated_user(session, authorization)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required",
        )
    return result


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
