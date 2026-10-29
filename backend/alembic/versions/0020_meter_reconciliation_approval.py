"""Approbations durables et immuables des cumuls de compteurs.

Revision ID: 0020
Revises: 0019

Cette table conserve qui a approuvé quel cumul et sa référence de réconciliation.
Elle ne raccorde pas encore ces cumuls au calcul automatique des échéances.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_meter_reconciliation_approval (
  approval_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  meter_kind text NOT NULL,
  baseline_total numeric(12,1) NOT NULL,
  current_total numeric(12,1) NOT NULL,
  reconciliation_reference text NOT NULL,
  approved_by uuid NOT NULL,
  approved_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_maintenance_meter_reconciliation_approval PRIMARY KEY (approval_id),
  CONSTRAINT uq_mmra_tenant_id UNIQUE (tenant_id, approval_id),
  CONSTRAINT fk_mmra__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mmra__site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mmra__approver FOREIGN KEY (tenant_id, approved_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_mmra_kind CHECK (meter_kind IN ('ODOMETER_KM','HOUR_METER')),
  CONSTRAINT ck_mmra_totals CHECK (
    baseline_total >= 0 AND current_total >= baseline_total
  ),
  CONSTRAINT ck_mmra_reference CHECK (
    char_length(btrim(reconciliation_reference)) BETWEEN 1 AND 160
  )
);
CREATE INDEX ix_mmra_vehicle_meter_approved
  ON maintenance_meter_reconciliation_approval
     (tenant_id, vehicle_id, meter_kind, approved_at DESC);
SELECT app.apply_tenant_rls(
  'maintenance_meter_reconciliation_approval', 'SELECT, INSERT'
);
CREATE TRIGGER tg_maintenance_meter_reconciliation_approval_append_only
  BEFORE UPDATE OR DELETE ON maintenance_meter_reconciliation_approval
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE maintenance_meter_reconciliation_approval;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
