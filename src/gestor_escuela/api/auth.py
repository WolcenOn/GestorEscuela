from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status


class ActorRole(StrEnum):
    ADMIN = "ADMIN"
    PLANNER = "PLANNER"
    VIEWER = "VIEWER"


def get_actor_role(
    x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> ActorRole:
    if x_actor_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Actor-Role header is required",
        )
    try:
        return ActorRole(x_actor_role.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown actor role",
        ) from exc


RoleDep = Annotated[ActorRole, Depends(get_actor_role)]


def require_admin(role: RoleDep) -> ActorRole:
    if role is not ActorRole.ADMIN:
        raise HTTPException(status_code=403, detail="ADMIN role required")
    return role


def require_planner(role: RoleDep) -> ActorRole:
    if role not in {ActorRole.ADMIN, ActorRole.PLANNER}:
        raise HTTPException(status_code=403, detail="PLANNER or ADMIN role required")
    return role


def require_viewer(role: RoleDep) -> ActorRole:
    return role


AdminDep = Annotated[ActorRole, Depends(require_admin)]
PlannerDep = Annotated[ActorRole, Depends(require_planner)]
ViewerDep = Annotated[ActorRole, Depends(require_viewer)]
