"""Cumul figé à la clôture d'un entretien : approuvé, ou calculé depuis le jalon validé.

Revision ID: 0059
Revises: 0058

Décision client du 3 novembre 2026 (docs/PREVENTIVE_DUES.md) : le cumul de clôture peut être calculé à partir du
jalon validé précédent et des relevés bruts jusqu'à la clôture (`source = 'READINGS'`, sans approbation). Une
approbation explicite reste possible (`source = 'APPROVAL'`). La table reste en ajout seul.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE maintenance_service_meter_baseline
  ADD COLUMN source text NOT NULL DEFAULT 'APPROVAL',
  ALTER COLUMN reconciliation_approval_id DROP NOT NULL,
  ADD CONSTRAINT ck_msmb_source CHECK (source IN ('APPROVAL','READINGS')),
  ADD CONSTRAINT ck_msmb_source_proof CHECK ((source = 'APPROVAL') = (reconciliation_approval_id IS NOT NULL));
"""

DOWNGRADE = r"""
-- Retour arrière destructif (garde guard_destructive) : les cumuls calculés depuis les relevés disparaissent.
-- Table en ajout seul et RLS forcée : garde et RLS levés le temps de la suppression multi-tenant, puis rétablis.
ALTER TABLE maintenance_service_meter_baseline DISABLE TRIGGER tg_maintenance_service_meter_baseline_append_only;
ALTER TABLE maintenance_service_meter_baseline NO FORCE ROW LEVEL SECURITY;
DELETE FROM maintenance_service_meter_baseline WHERE source = 'READINGS';
ALTER TABLE maintenance_service_meter_baseline FORCE ROW LEVEL SECURITY;
ALTER TABLE maintenance_service_meter_baseline ENABLE TRIGGER tg_maintenance_service_meter_baseline_append_only;
ALTER TABLE maintenance_service_meter_baseline
  DROP CONSTRAINT ck_msmb_source_proof,
  DROP CONSTRAINT ck_msmb_source,
  ALTER COLUMN reconciliation_approval_id SET NOT NULL,
  DROP COLUMN source;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
