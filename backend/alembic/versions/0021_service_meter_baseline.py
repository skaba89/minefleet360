"""Cumuls vérifiés au moment d'un entretien préventif clôturé.

Revision ID: 0021
Revises: 0020

La preuve relie le plan, l'échéance, l'OT et l'approbation de compteur.
Elle reste ajout seul et n'active aucun traitement automatique.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_service_meter_baseline (
  service_meter_baseline_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  maintenance_plan_id uuid NOT NULL,
  maintenance_due_id uuid NOT NULL,
  work_order_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  meter_kind text NOT NULL,
  cumulative_total numeric(12,1) NOT NULL,
  reconciliation_approval_id uuid NOT NULL,
  serviced_at timestamptz NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_maintenance_service_meter_baseline
    PRIMARY KEY (service_meter_baseline_id),
  CONSTRAINT uq_msmb_tenant_id
    UNIQUE (tenant_id, service_meter_baseline_id),
  CONSTRAINT uq_msmb_work_order_kind
    UNIQUE (tenant_id, work_order_id, meter_kind),
  CONSTRAINT fk_msmb__plan FOREIGN KEY (tenant_id, maintenance_plan_id)
    REFERENCES maintenance_plan (tenant_id, maintenance_plan_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__due FOREIGN KEY (tenant_id, maintenance_due_id)
    REFERENCES maintenance_due (tenant_id, maintenance_due_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__work_order FOREIGN KEY (tenant_id, work_order_id)
    REFERENCES work_order (tenant_id, work_order_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__approval
    FOREIGN KEY (tenant_id, reconciliation_approval_id)
    REFERENCES maintenance_meter_reconciliation_approval (tenant_id, approval_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_msmb__recorder FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_msmb_kind
    CHECK (meter_kind IN ('ODOMETER_KM','HOUR_METER')),
  CONSTRAINT ck_msmb_total
    CHECK (cumulative_total >= 0 AND cumulative_total < 100000000)
);
CREATE INDEX ix_msmb_plan_service
  ON maintenance_service_meter_baseline
     (tenant_id, vehicle_id, maintenance_plan_id, serviced_at DESC);
SELECT app.apply_tenant_rls(
  'maintenance_service_meter_baseline', 'SELECT, INSERT'
);
CREATE TRIGGER tg_maintenance_service_meter_baseline_append_only
  BEFORE UPDATE OR DELETE ON maintenance_service_meter_baseline
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE maintenance_service_meter_baseline;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
