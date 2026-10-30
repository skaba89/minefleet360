"""Qualification serveur et tolérances persistantes des anomalies de pompe.

Revision ID: 0035
Revises: 0034
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fuel_pump
  ADD COLUMN anomaly_tolerance_liters numeric(12,3) NOT NULL DEFAULT 5,
  ADD COLUMN anomaly_tolerance_percent numeric(6,3) NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_fuel_pump_anomaly_tolerance_liters
    CHECK (anomaly_tolerance_liters BETWEEN 0 AND 1000),
  ADD CONSTRAINT ck_fuel_pump_anomaly_tolerance_percent
    CHECK (anomaly_tolerance_percent BETWEEN 0 AND 100);

ALTER TABLE fuel_pump_anomaly_case
  ADD COLUMN meter_delta_liters numeric(16,3),
  ADD COLUMN approved_issue_liters numeric(16,3),
  ADD COLUMN variance_liters numeric(16,3),
  ADD COLUMN variance_percent numeric(9,3),
  ADD COLUMN tolerance_liters numeric(12,3),
  ADD COLUMN tolerance_percent numeric(6,3),
  ADD COLUMN qualification_reason text NOT NULL DEFAULT 'LEGACY_UNQUALIFIED',
  ADD CONSTRAINT ck_fuel_pump_anomaly_qualification_reason CHECK (
    qualification_reason IN (
      'LEGACY_UNQUALIFIED',
      'METER_VOLUME_EXCEEDS_APPROVED_ISSUES',
      'APPROVED_ISSUES_EXCEED_METER_VOLUME'
    )
  ),
  ADD CONSTRAINT ck_fuel_pump_anomaly_qualification_snapshot CHECK (
    qualification_reason = 'LEGACY_UNQUALIFIED'
    OR (
      meter_delta_liters IS NOT NULL
      AND approved_issue_liters IS NOT NULL
      AND variance_liters IS NOT NULL
      AND variance_percent IS NOT NULL AND variance_percent >= 0
      AND tolerance_liters IS NOT NULL AND tolerance_liters >= 0
      AND tolerance_percent IS NOT NULL AND tolerance_percent >= 0
    )
  );
"""

DOWNGRADE = r"""
ALTER TABLE fuel_pump_anomaly_case
  DROP CONSTRAINT ck_fuel_pump_anomaly_qualification_snapshot,
  DROP CONSTRAINT ck_fuel_pump_anomaly_qualification_reason,
  DROP COLUMN qualification_reason,
  DROP COLUMN tolerance_percent,
  DROP COLUMN tolerance_liters,
  DROP COLUMN variance_percent,
  DROP COLUMN variance_liters,
  DROP COLUMN approved_issue_liters,
  DROP COLUMN meter_delta_liters;

ALTER TABLE fuel_pump
  DROP CONSTRAINT ck_fuel_pump_anomaly_tolerance_percent,
  DROP CONSTRAINT ck_fuel_pump_anomaly_tolerance_liters,
  DROP COLUMN anomaly_tolerance_percent,
  DROP COLUMN anomaly_tolerance_liters;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
