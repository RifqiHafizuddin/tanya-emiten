"""Postgres connection and a minimal numbered-SQL migrations runner."""
from functools import cache
from pathlib import Path

import psycopg

from backend.config import env
from backend.net import retry

MIGRATIONS = Path(__file__).parent / "migrations"


def connect(url_var: str = "DATABASE_URL", **kwargs) -> psycopg.Connection:
    # Pooled URI (Neon, D54); prepare_threshold=None because poolers can drop prepared statements.
    return retry(lambda: psycopg.connect(env(url_var), connect_timeout=15, prepare_threshold=None, **kwargs))


@cache
def pool():
    """Connections kept open for the request path. Neon (Singapore) is far from the Space, and a fresh TLS connection
    per query cost about 1 s each (traces, 2026-11-02). `check` replaces a connection Neon closed while idle."""
    from psycopg_pool import ConnectionPool

    return ConnectionPool(env("DATABASE_URL"), min_size=1, max_size=4, max_idle=240, name="api",
                          kwargs={"connect_timeout": 15, "prepare_threshold": None},
                          check=ConnectionPool.check_connection)


def pooled():
    """`with pooled() as conn:` like `connect()`: commits on success, rolls back on error, then returns the
    connection to the pool instead of closing it."""
    return pool().connection()


def migrate() -> list[str]:
    """Apply every migrations/NNN_*.sql not yet recorded in schema_migrations, each in its own transaction."""
    applied_now = []
    with connect() as conn:
        conn.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())"
        )
        conn.commit()
        done = {row[0] for row in conn.execute("select name from schema_migrations")}
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
            applied_now.append(path.name)
    return applied_now
