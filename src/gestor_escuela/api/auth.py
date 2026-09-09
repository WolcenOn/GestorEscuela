from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gestor_escuela.api.auth_tokens import authenticated_user
from gestor_escuela.persistence.db import get_session
from gestor_escuela.persistence.models import SchoolMembershipRow, UserRow


class ActorRole(StrEnum):
    ADMIN = "ADMIN"
    PLANNER = "PLANNER"
    VIEWER = "VIEWER"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: UUID | None
    role: ActorRole


SessionDep = Annotated[Session, Depends(get_session)]


def legacy_role_bootstrap_enabled() -> bool:
    """Temporary integration switch.

    Keep enabled while the GitHub Pages integration still uses the prototype actor headers.
    Production must set ALLOW_LEGACY_ROLE_BOOTSTRAP=false once signed authentication is enabled.
    """

    return os.getenv("ALLOW_LEGACY_ROLE_BOOTSTRAP", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _parse_role(value: str) -> ActorRole:
    try:
        return ActorRole(value.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown actor role",
        ) from exc


def _school_has_memberships(session: Session, school_id: UUID) -> bool:
    membership_id = session.scalar(
        select(SchoolMembershipRow.id)
        .where(SchoolMembershipRow.school_id == school_id)
        .limit(1)
    )
    return membership_id is not None


def _remember_actor(request: Request, session: Session, actor: ActorContext) -> ActorContext:
    request.state.db_session = session
    request.state.actor_user_id = actor.user_id
    request.state.actor_role = actor.role.value
    return actor


def _membership_actor(
    request: Request,
    session: Session,
    school_id: UUID,
    user_id: UUID,
) -> ActorContext:
    membership = session.scalar(
        select(SchoolMembershipRow).where(
            SchoolMembershipRow.school_id == school_id,
            SchoolMembershipRow.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Actor is not a member of this school",
        )
    return _remember_actor(
        request,
        session,
        ActorContext(user_id=user_id, role=_parse_role(membership.role)),
    )


def get_actor_context(
    request: Request,
    session: SessionDep,
    school_id: UUID | None = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_actor_id: Annotated[UUID | None, Header(alias="X-Actor-Id")] = None,
    x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> ActorContext:
    # Keep the request-associated database bind available to the audit middleware even when
    # authentication later fails. No request body is stored by the audit trail.
    request.state.db_session = session

    bearer_identity = authenticated_user(session, authorization)
    if bearer_identity is not None:
        user, _auth_session = bearer_identity
        if school_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="School membership context is required",
            )
        return _membership_actor(request, session, school_id, user.id)

    if x_actor_id is not None:
        if session.get(UserRow, x_actor_id) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unknown actor identity",
            )
        if school_id is not None:
            return _membership_actor(request, session, school_id, x_actor_id)
        if x_actor_role is not None and legacy_role_bootstrap_enabled():
            return _remember_actor(
                request,
                session,
                ActorContext(user_id=x_actor_id, role=_parse_role(x_actor_role)),
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="School membership context is required",
        )

    if x_actor_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated actor identity is required",
        )

    if not legacy_role_bootstrap_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Legacy role bootstrap is disabled",
        )

    if school_id is not None and _school_has_memberships(session, school_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Actor-Id is required after school bootstrap",
        )

    return _remember_actor(
        request,
        session,
        ActorContext(user_id=None, role=_parse_role(x_actor_role)),
    )


ActorDep = Annotated[ActorContext, Depends(get_actor_context)]


def require_admin(actor: ActorDep) -> ActorContext:
    if actor.role is not ActorRole.ADMIN:
        raise HTTPException(status_code=403, detail="ADMIN role required")
    return actor


def require_planner(actor: ActorDep) -> ActorContext:
    if actor.role not in {ActorRole.ADMIN, ActorRole.PLANNER}:
        raise HTTPException(status_code=403, detail="PLANNER or ADMIN role required")
    return actor


def require_viewer(actor: ActorDep) -> ActorContext:
    return actor


AdminDep = Annotated[ActorContext, Depends(require_admin)]
PlannerDep = Annotated[ActorContext, Depends(require_planner)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]
