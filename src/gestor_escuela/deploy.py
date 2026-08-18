from __future__ import annotations

import time

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from alembic import command
from gestor_escuela.persistence.db import database_url


def wait_for_database(*, attempts: int = 12, delay_seconds: float = 2.0) -> None:
    url = database_url()
    parsed = make_url(url)
    print(
        "Railway database target: "
        f"driver={parsed.drivername} host={parsed.host} port={parsed.port} "
        f"database={parsed.database}",
        flush=True,
    )

    engine = create_engine(url, pool_pre_ping=True)
    try:
        for attempt in range(1, attempts + 1):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                print("Database connection OK.", flush=True)
                return
            except OperationalError as exc:
                if attempt == attempts:
                    raise
                print(
                    f"Database not ready (attempt {attempt}/{attempts}): "
                    f"{type(exc.orig).__name__}. Retrying...",
                    flush=True,
                )
                time.sleep(delay_seconds)
    finally:
        engine.dispose()


def run_migrations() -> None:
    print("Running Alembic migrations...", flush=True)
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
    print("Alembic migrations complete.", flush=True)


def main() -> None:
    wait_for_database()
    run_migrations()


if __name__ == "__main__":
    main()
