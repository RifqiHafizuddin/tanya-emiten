"""Postgres connection and a minimal numbered-SQL migrations runner."""
from pathlib import Path

import psycopg

from backend.config import env
from backend.net import retry

MIGRATIONS = Path(__file__).parent / "migrations"


def connect(url_var: str = "DATABASE_URL", **kwargs) -> psycopg.Connection:
    # Pooled URI (Neon, D54); prepare_threshold=None because poolers can drop prepared statements.
    return retry(lambda: psycopg.connect(env(url_var), connect_timeout=15, prepare_threshold=None, **kwargs))


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
