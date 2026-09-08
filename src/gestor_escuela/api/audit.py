from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.responses import Response

from gestor_escuela.persistence.audit_models import AuditLogRow

_LOG = logging.getLogger(__name__)
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SCHOOL_PATH = re.compile(r"/schools/([0-9a-fA-F-]{36})(?:/|$)")


async def audit_mutating_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Record minimal metadata for mutating requests without capturing request bodies."""

    request_id = uuid4()
    status_code = 500
    response: Response | None = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = str(request_id)
        return response
    finally:
        if request.method.upper() in _MUTATING_METHODS:
            _record_audit_entry(request, request_id=request_id, status_code=status_code)


def _record_audit_entry(request: Request, *, request_id: UUID, status_code: int) -> None:
    source_session = getattr(request.state, "db_session", None)
    if not isinstance(source_session, Session):
        return

    try:
        bind = source_session.get_bind()
        with Session(bind=bind) as audit_session:
            audit_session.add(
                AuditLogRow(
                    request_id=request_id,
                    school_id=_school_id_from_path(request.url.path),
                    actor_user_id=getattr(request.state, "actor_user_id", None),
                    actor_role=getattr(request.state, "actor_role", None),
                    method=request.method.upper(),
                    path=request.url.path[:500],
                    status_code=status_code,
                )
            )
            audit_session.commit()
    except Exception:  # pragma: no cover - auditing must never mask the application response.
        _LOG.exception("Could not persist audit log entry")


def _school_id_from_path(path: str) -> UUID | None:
    match = _SCHOOL_PATH.search(path)
    if match is None:
        return None
    try:
        return UUID(match.group(1))
    except ValueError:
        return None
