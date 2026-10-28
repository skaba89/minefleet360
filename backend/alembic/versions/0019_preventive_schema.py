"""Plans d'entretien préventif et échéances (lot 3b.2, schéma uniquement).

Revision ID: 0019
Revises: 0018

Aucune création automatique d'OT dans cette migration. L'intégration API et le
moteur idempotent viendront dans une tranche ultérieure, après revue sécurité.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_plan (
  maintenance_plan_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  code text NOT NULL,
  version integer NOT NULL DEFAULT 1,
  km_interval numeric(12,1),
  hours_interval numeric(12,1),
  days_interval integer,
  active boolean NOT NULL DEFAULT true,
  suspension_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_maintenance_plan PRIMARY KEY (maintenance_plan_id),
  CONSTRAINT uq_maintenance_plan_tenant_id UNIQUE (tenant_id, maintenance_plan_id),
  CONSTRAINT uq_maintenance_plan_vehicle UNIQUE (tenant_id, maintenance_plan_id, vehicle_id),
  CONSTRAINT uq_maintenance_plan_code_version UNIQUE (tenant_id, vehicle_id, code, version),
  CONSTRAINT fk_mp__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT ck_mp_code CHECK (char_length(btrim(code)) BETWEEN 1 AND 80),
  CONSTRAINT ck_mp_version CHECK (version >= 1),
  CONSTRAINT ck_mp_intervals CHECK (
    (km_interval IS NOT NULL AND km_interval > 0) OR
    (hours_interval IS NOT NULL AND hours_interval > 0) OR
    (days_interval IS NOT NULL AND days_interval > 0)
  ),
  CONSTRAINT ck_mp_km CHECK (km_interval IS NULL OR km_interval > 0),
  CONSTRAINT ck_mp_hours CHECK (hours_interval IS NULL OR hours_interval > 0),
  CONSTRAINT ck_mp_days CHECK (days_interval IS NULL OR days_interval > 0),
  CONSTRAINT ck_mp_suspension CHECK (active OR nullif(btrim(suspension_reason),'') IS NOT NULL),
  CONSTRAINT ck_mp_row_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_mp_one_active_code
 ON maintenance_plan (tenant_id, vehicle_id, code) WHERE active;
CREATE INDEX ix_mp_vehicle ON maintenance_plan (tenant_id, vehicle_id, active);
SELECT app.apply_tenant_rls('maintenance_plan', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('maintenance_plan');

CREATE TABLE maintenance_due (
  maintenance_due_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  maintenance_plan_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  trigger_kind text NOT NULL,
  trigger_key text NOT NULL,
  status text NOT NULL DEFAULT 'DUE',
  due_on date,
  due_meter numeric(12,1),
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  work_order_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_maintenance_due PRIMARY KEY (maintenance_due_id),
  CONSTRAINT uq_maintenance_due_tenant_id UNIQUE (tenant_id, maintenance_due_id),
  CONSTRAINT uq_maintenance_due_idempotence UNIQUE (tenant_id, maintenance_plan_id, trigger_key),
  CONSTRAINT fk_md__plan FOREIGN KEY (tenant_id, maintenance_plan_id, vehicle_id)
    REFERENCES maintenance_plan (tenant_id, maintenance_plan_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_md__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_md__work_order FOREIGN KEY (tenant_id, work_order_id)
    REFERENCES work_order (tenant_id, work_order_id) ON DELETE RESTRICT,
  CONSTRAINT ck_md_trigger CHECK (trigger_kind IN ('KM','HOURS','DAYS')),
  CONSTRAINT ck_md_status CHECK (status IN ('DUE','SCHEDULED','COMPLETED','CANCELLED')),
  CONSTRAINT ck_md_trigger_key CHECK (char_length(btrim(trigger_key)) BETWEEN 1 AND 160),
  CONSTRAINT ck_md_due_detail CHECK (
    (trigger_kind = 'DAYS' AND due_on IS NOT NULL AND due_meter IS NULL)
    OR
    (trigger_kind IN ('KM','HOURS') AND due_meter IS NOT NULL AND due_meter >= 0 AND due_on IS NULL)
  ),
  CONSTRAINT ck_md_scheduled CHECK (status NOT IN ('SCHEDULED','COMPLETED') OR work_order_id IS NOT NULL)
);
CREATE INDEX ix_md_vehicle_status ON maintenance_due (tenant_id, vehicle_id, status, evaluated_at DESC);
CREATE UNIQUE INDEX uq_md_work_order ON maintenance_due (tenant_id, work_order_id)
 WHERE work_order_id IS NOT NULL;
SELECT app.apply_tenant_rls('maintenance_due', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE maintenance_due;
DROP TABLE maintenance_plan;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
