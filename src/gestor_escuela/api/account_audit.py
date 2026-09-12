from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from gestor_escuela.api.auth import SessionDep
from gestor_escuela.api.password_auth import CurrentAuthDep
from gestor_escuela.persistence.audit_models import AuditLogRow

router = APIRouter(tags=["authentication"])


@router.get("/auth/audit-log")
def list_account_audit_log(
    current: CurrentAuthDep,
    session: SessionDep,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Return the authenticated user's own account-level audit history.

    School-scoped events stay available through /schools/{school_id}/audit-log. This endpoint
    intentionally filters only by the authenticated user and therefore works for account events
    that do not belong to one specific school, such as password or session changes.
    """

    bounded_limit = max(1, min(200, limit))
    rows = session.scalars(
        select(AuditLogRow)
        .where(AuditLogRow.actor_user_id == current.user.id)
        .order_by(AuditLogRow.created_at.desc(), AuditLogRow.id.desc())
        .limit(bounded_limit)
    ).all()
    return [
        {
            "id": item.id,
            "request_id": item.request_id,
            "school_id": item.school_id,
            "actor_user_id": item.actor_user_id,
            "actor_role": item.actor_role,
            "event_type": item.event_type,
            "method": item.method,
            "path": item.path,
            "status_code": item.status_code,
            "created_at": item.created_at,
        }
        for item in rows
    ]
