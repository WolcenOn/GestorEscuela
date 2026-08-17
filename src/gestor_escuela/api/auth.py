from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

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


def get_actor_context(
    session: SessionDep,
    school_id: UUID | None = None,
    x_actor_id: Annotated[UUID | None, Header(alias="X-Actor-Id")] = None,
    x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> ActorContext:
    if x_actor_id is not None:
        if session.get(UserRow, x_actor_id) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unknown actor identity",
            )
        if school_id is not None:
            membership = session.scalar(
                select(SchoolMembershipRow).where(
                    SchoolMembershipRow.school_id == school_id,
                    SchoolMembershipRow.user_id == x_actor_id,
                )
            )
            if membership is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Actor is not a member of this school",
                )
            return ActorContext(user_id=x_actor_id, role=_parse_role(membership.role))
        if x_actor_role is not None:
            return ActorContext(user_id=x_actor_id, role=_parse_role(x_actor_role))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="School membership context is required",
        )

    if x_actor_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Actor-Id or X-Actor-Role header is required",
        )

    if school_id is not None and _school_has_memberships(session, school_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Actor-Id is required after school bootstrap",
        )

    return ActorContext(user_id=None, role=_parse_role(x_actor_role))


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
