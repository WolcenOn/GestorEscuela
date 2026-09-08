from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from gestor_escuela.api.auth import SessionDep, ViewerDep, legacy_role_bootstrap_enabled
from gestor_escuela.persistence.models import UserRow

router = APIRouter()


@router.get("/schools/{school_id}/auth/context")
def school_auth_context(
    school_id: UUID,
    session: SessionDep,
    actor: ViewerDep,
) -> dict[str, object]:
    user = session.get(UserRow, actor.user_id) if actor.user_id is not None else None
    return {
        "school_id": school_id,
        "user_id": actor.user_id,
        "email": user.email if user is not None else None,
        "display_name": user.display_name if user is not None else None,
        "role": actor.role.value,
        "legacy_bootstrap": actor.user_id is None,
        "legacy_bootstrap_enabled": legacy_role_bootstrap_enabled(),
    }
