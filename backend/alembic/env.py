"""Migrations exécutées sous le rôle propriétaire mf_owner (jamais mf_app). MODELE_PHYSIQUE_LOT1 §8.

Chaque downgrade appelle `guard_destructive()` (app/core/migration_tools.py) : refus hors local/test/ci.
"""

from sqlalchemy import create_engine, text

from alembic import context
from app.core.config import get_settings


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url(owner=True))
    with engine.connect() as connection:
        connection.execute(text("SET lock_timeout = '10s'"))
        connection.commit()
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Le mode hors ligne d'Alembic n'est pas pris en charge.")
run_migrations_online()
