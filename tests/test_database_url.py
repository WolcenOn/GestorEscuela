from gestor_escuela.persistence.db import normalize_database_url


def test_normalize_database_url_converts_postgres_scheme() -> None:
    assert normalize_database_url("postgres://u:p@host:5432/db") == (
        "postgresql+psycopg://u:p@host:5432/db"
    )


def test_normalize_database_url_converts_postgresql_scheme() -> None:
    assert normalize_database_url("postgresql://u:p@host:5432/db") == (
        "postgresql+psycopg://u:p@host:5432/db"
    )


def test_normalize_database_url_preserves_explicit_driver() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert normalize_database_url(url) == url


def test_normalize_database_url_preserves_sqlite() -> None:
    url = "sqlite+pysqlite:///:memory:"
    assert normalize_database_url(url) == url
