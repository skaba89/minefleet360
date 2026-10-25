"""Outils pour les migrations Alembic (rôle mf_owner)."""

from alembic import op
from app.core.config import get_settings


def run_sql(statement: str) -> None:
    """Exécute du SQL brut via le pilote, sans interprétation des paramètres (`%` dans PL/pgSQL)."""
    driver_connection = op.get_bind().connection.driver_connection
    assert driver_connection is not None
    driver_connection.execute(statement)


def guard_destructive() -> None:
    """Les downgrade détruisent des données : refusés hors local/test/ci (CLAUDE.md)."""
    settings = get_settings()
    if not settings.destructive_migrations_allowed:
        raise RuntimeError(f"downgrade refusé en environnement {settings.env!r} (opération destructive)")
