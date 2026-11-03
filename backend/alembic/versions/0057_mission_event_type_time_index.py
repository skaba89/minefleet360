"""Index des événements de mission par type et date (coût complet, indicateurs de pesée).

Revision ID: 0057
Revises: 0056

Les écrans coût complet (missions terminées par engin) et indicateurs de pesée filtrent `mission_event` sur
`event_type = 'COMPLETED'` et une période : sans index, PostgreSQL lisait tous les événements de la société
(54 000 lus pour 1 400 gardés sur le jeu DEMO `large`, 24 → 6 ms). `mission_id` est inclus pour un parcours
d'index seul. Voir docs/PERFORMANCE_DEMO.md. Création non concurrente : verrou d'écriture bref sur la table,
acceptable aux volumes actuels (à déployer hors pointe sur une grosse base).
"""

from app.core.migration_tools import run_sql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(
        "CREATE INDEX ix_me_type_time ON mission_event (tenant_id, event_type, occurred_at) INCLUDE (mission_id)"
    )


def downgrade() -> None:
    run_sql("DROP INDEX ix_me_type_time")
