from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gestor_escuela.api.auth import AdminDep, SessionDep
from gestor_escuela.api.auth_tokens import (
    hash_password,
    issue_session,
    normalize_email,
    require_authenticated_user,
    token_digest,
    verify_password,
)
from gestor_escuela.persistence.auth_models import (
    AuthSessionRow,
    SchoolInvitationRow,
    UserCredentialRow,
)
from gestor_escuela.persistence.models import SchoolMembershipRow, SchoolRow, UserRow

router = APIRouter(tags=["authentication"])


class RegisterSchoolRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    school_name: str = Field(min_length=1, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validated_email(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validated_email(value)


class InvitationCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["ADMIN", "PLANNER", "VIEWER"]
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 30)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validated_email(value)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str


class MembershipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    school_id: UUID
    user_id: UUID
    role: str


class SchoolSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class AuthRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserSummary
    memberships: list[MembershipSummary]
    school: SchoolSummary | None = None


class InvitationRead(BaseModel):
    id: UUID
    school_id: UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    token: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentAuth:
    user: UserRow
    auth_session: AuthSessionRow


def current_auth(
    session: SessionDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CurrentAuth:
    user, auth_session = require_authenticated_user(session, authorization)
    return CurrentAuth(user=user, auth_session=auth_session)


CurrentAuthDep = Annotated[CurrentAuth, Depends(current_auth)]


@router.post(
    "/auth/register-school",
    response_model=AuthRead,
    status_code=status.HTTP_201_CREATED,
)
def register_school(payload: RegisterSchoolRequest, session: SessionDep) -> AuthRead:
    email = normalize_email(payload.email)
    if session.scalar(select(UserRow.id).where(UserRow.email == email)) is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    user = UserRow(email=email, display_name=payload.display_name.strip())
    school = SchoolRow(name=payload.school_name.strip())
    session.add_all([user, school])
    session.flush()
    credential = UserCredentialRow(user_id=user.id, password_hash=hash_password(payload.password))
    membership = SchoolMembershipRow(school_id=school.id, user_id=user.id, role="ADMIN")
    session.add_all([credential, membership])
    raw_token, auth_session = issue_session(session, user.id)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Could not create the account") from exc
    return _auth_response(session, user, raw_token, auth_session, school=school)


@router.post("/auth/login", response_model=AuthRead)
def login(payload: LoginRequest, session: SessionDep) -> AuthRead:
    email = normalize_email(payload.email)
    user = session.scalar(select(UserRow).where(UserRow.email == email))
    credential = session.get(UserCredentialRow, user.id) if user is not None else None
    if (
        user is None
        or credential is None
        or not credential.is_active
        or not verify_password(payload.password, credential.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    raw_token, auth_session = issue_session(session, user.id)
    session.commit()
    return _auth_response(session, user, raw_token, auth_session)


@router.get("/auth/me", response_model=AuthRead)
def me(current: CurrentAuthDep, session: SessionDep) -> AuthRead:
    return AuthRead(
        access_token="",
        token_type="bearer",
        expires_at=current.auth_session.expires_at,
        user=UserSummary.model_validate(current.user),
        memberships=_membership_summaries(session, current.user.id),
        school=None,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: CurrentAuthDep, session: SessionDep) -> Response:
    current.auth_session.revoked_at = datetime.now(UTC)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schools/{school_id}/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    school_id: UUID,
    payload: InvitationCreateRequest,
    session: SessionDep,
    actor: AdminDep,
) -> InvitationRead:
    school = session.get(SchoolRow, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if actor.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user identity is required to create invitations",
        )
    hours = payload.expires_in_hours or _default_invitation_hours()
    raw_token = secrets.token_urlsafe(32)
    invitation = SchoolInvitationRow(
        school_id=school_id,
        email=normalize_email(payload.email),
        role=payload.role,
        token_hash=token_digest(raw_token),
        invited_by_user_id=actor.user_id,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )
    session.add(invitation)
    session.commit()
    session.refresh(invitation)
    return _invitation_response(invitation, token=raw_token)


@router.get(
    "/schools/{school_id}/invitations",
    response_model=list[InvitationRead],
)
def list_invitations(
    school_id: UUID,
    session: SessionDep,
    _actor: AdminDep,
) -> list[InvitationRead]:
    rows = session.scalars(
        select(SchoolInvitationRow)
        .where(SchoolInvitationRow.school_id == school_id)
        .order_by(SchoolInvitationRow.created_at.desc())
    ).all()
    return [_invitation_response(item) for item in rows]


@router.post("/auth/invitations/accept", response_model=AuthRead)
def accept_invitation(payload: InvitationAcceptRequest, session: SessionDep) -> AuthRead:
    invitation = session.scalar(
        select(SchoolInvitationRow)
        .where(SchoolInvitationRow.token_hash == token_digest(payload.token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation has already been accepted")
    if _aware(invitation.expires_at) <= now:
        raise HTTPException(status_code=410, detail="Invitation has expired")

    user = session.scalar(select(UserRow).where(UserRow.email == invitation.email))
    if user is None:
        if not payload.display_name:
            raise HTTPException(
                status_code=422,
                detail="display_name is required when creating a new account",
            )
        user = UserRow(email=invitation.email, display_name=payload.display_name.strip())
        session.add(user)
        session.flush()
        session.add(
            UserCredentialRow(user_id=user.id, password_hash=hash_password(payload.password))
        )
    else:
        credential = session.get(UserCredentialRow, user.id)
        if credential is None:
            session.add(
                UserCredentialRow(user_id=user.id, password_hash=hash_password(payload.password))
            )
        elif not credential.is_active or not verify_password(
            payload.password, credential.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password for the invited account",
            )

    membership = session.scalar(
        select(SchoolMembershipRow).where(
            SchoolMembershipRow.school_id == invitation.school_id,
            SchoolMembershipRow.user_id == user.id,
        )
    )
    if membership is None:
        membership = SchoolMembershipRow(
            school_id=invitation.school_id,
            user_id=user.id,
            role=invitation.role,
        )
        session.add(membership)

    invitation.accepted_at = now
    invitation.accepted_by_user_id = user.id
    raw_token, auth_session = issue_session(session, user.id)
    session.commit()
    school = session.get(SchoolRow, invitation.school_id)
    return _auth_response(session, user, raw_token, auth_session, school=school)


def _auth_response(
    session: SessionDep,
    user: UserRow,
    raw_token: str,
    auth_session: AuthSessionRow,
    *,
    school: SchoolRow | None = None,
) -> AuthRead:
    return AuthRead(
        access_token=raw_token,
        expires_at=auth_session.expires_at,
        user=UserSummary.model_validate(user),
        memberships=_membership_summaries(session, user.id),
        school=SchoolSummary.model_validate(school) if school is not None else None,
    )


def _membership_summaries(session: SessionDep, user_id: UUID) -> list[MembershipSummary]:
    rows = session.scalars(
        select(SchoolMembershipRow)
        .where(SchoolMembershipRow.user_id == user_id)
        .order_by(SchoolMembershipRow.created_at, SchoolMembershipRow.id)
    ).all()
    return [MembershipSummary.model_validate(item) for item in rows]


def _invitation_response(
    invitation: SchoolInvitationRow,
    *,
    token: str | None = None,
) -> InvitationRead:
    return InvitationRead(
        id=invitation.id,
        school_id=invitation.school_id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        created_at=invitation.created_at,
        token=token,
    )


def _default_invitation_hours() -> int:
    raw = os.getenv("INVITATION_TTL_HOURS", "72")
    try:
        value = int(raw)
    except ValueError:
        value = 72
    return max(1, min(24 * 30, value))


def _validated_email(value: str) -> str:
    normalized = normalize_email(value)
    local, separator, domain = normalized.partition("@")
    if not separator or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Enter a valid email address")
    return normalized


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
