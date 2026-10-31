"""Read-only staging gate: compare deployed DB Alembic revisions to code heads.

Run from the migration image with the owner account, never from the public API.
"""
from __future__ import annotations

import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def revisions_match(current: set[str], heads: set[str]) -> bool:
    return bool(current) and current == heads


def main() -> int:
    settings = get_settings()
    # This check must never initiate a migration; only query alembic_version.
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    expected = set(script.get_heads())
    engine = create_engine(settings.database_url(owner=True), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            current = {str(row[0]) for row in conn.execute(text("SELECT version_num FROM alembic_version"))}
    except (SQLAlchemyError, OSError):
        print("FAIL: cannot inspect Alembic revision (details withheld)", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    if not revisions_match(current, expected):
        print(
            f"FAIL: database schema revision differs from deployed code "
            f"(db heads={len(current)}, code heads={len(expected)})",
            file=sys.stderr,
        )
        return 2
    print("OK: database revision matches all Alembic heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
