from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError


class Base(DeclarativeBase):
    pass


class VersionedSession(Session):
    def commit(self) -> None:
        try:
            super().commit()
        except StaleDataError as exc:
            self.rollback()
            raise IntegrityError("Concurrent update", None, exc) from exc


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def database_url() -> str:
    configured = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://gestor:gestor@localhost:5432/gestor_escuela",
    )
    return normalize_database_url(configured)


engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(
    bind=engine,
    class_=VersionedSession,
    autoflush=False,
    expire_on_commit=False,
)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
