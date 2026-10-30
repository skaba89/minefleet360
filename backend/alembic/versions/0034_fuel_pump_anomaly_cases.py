"""Dossiers d'anomalies de pompe et événements de traitement append-only.

Revision ID: 0034
Revises: 0033
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fuel_pump_anomaly_case (
  fuel_pump_anomaly_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_pump_id uuid NOT NULL,
  start_reading_id uuid NOT NULL,
  end_reading_id uuid NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_pump_anomaly_case_tenant UNIQUE (tenant_id, fuel_pump_anomaly_case_id),
  CONSTRAINT uq_fuel_pump_anomaly_interval UNIQUE (tenant_id, fuel_pump_id, start_reading_id, end_reading_id),
  CONSTRAINT fk_fuel_pump_anomaly_pump FOREIGN KEY (tenant_id, fuel_pump_id, site_id)
    REFERENCES fuel_pump (tenant_id, fuel_pump_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_pump_anomaly_start FOREIGN KEY (tenant_id, start_reading_id)
    REFERENCES fuel_pump_meter_reading (tenant_id, fuel_pump_meter_reading_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_pump_anomaly_end FOREIGN KEY (tenant_id, end_reading_id)
    REFERENCES fuel_pump_meter_reading (tenant_id, fuel_pump_meter_reading_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_pump_anomaly_creator FOREIGN KEY (tenant_id, created_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_pump_anomaly_distinct_readings CHECK (start_reading_id <> end_reading_id)
);
CREATE INDEX ix_fuel_pump_anomaly_site ON fuel_pump_anomaly_case (tenant_id, site_id, created_at DESC);
SELECT app.apply_tenant_rls('fuel_pump_anomaly_case', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_pump_anomaly_case_append_only BEFORE UPDATE OR DELETE ON fuel_pump_anomaly_case
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE fuel_pump_anomaly_event (
  fuel_pump_anomaly_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  fuel_pump_anomaly_case_id uuid NOT NULL,
  event_type text NOT NULL,
  justification text NOT NULL,
  actor_user_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_fuel_pump_anomaly_event_case FOREIGN KEY (tenant_id, fuel_pump_anomaly_case_id)
    REFERENCES fuel_pump_anomaly_case (tenant_id, fuel_pump_anomaly_case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_pump_anomaly_event_user FOREIGN KEY (tenant_id, actor_user_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_pump_anomaly_event_type CHECK (event_type IN ('ACKNOWLEDGED', 'JUSTIFIED', 'CLOSED')),
  CONSTRAINT ck_fuel_pump_anomaly_justification CHECK (char_length(justification) BETWEEN 10 AND 2000)
);
CREATE INDEX ix_fuel_pump_anomaly_event_case
  ON fuel_pump_anomaly_event (tenant_id, fuel_pump_anomaly_case_id, occurred_at);
SELECT app.apply_tenant_rls('fuel_pump_anomaly_event', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_pump_anomaly_event_append_only BEFORE UPDATE OR DELETE ON fuel_pump_anomaly_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE fuel_pump_anomaly_event;
DROP TABLE fuel_pump_anomaly_case;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
