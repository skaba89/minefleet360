"""Compteurs et documents réglementaires des véhicules (lot 2c, US-2.09, US-2.10, C-06).

Revision ID: 0015
Revises: 0014

Voir docs/PLAN_LOT2.md §8. Les relevés de compteur sont en AJOUT SEUL (une erreur se corrige par un
relevé de remise à zéro motivé). Les documents ne se suppriment jamais : ils sont retirés ou remplacés ;
leur validité est dérivée des dates (D-03) et ceux marqués bloquants conditionnent l'affectation (RM-104).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE vehicle_meter_reading (
  vehicle_meter_reading_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id    uuid NOT NULL,
  meter_kind text NOT NULL,
  value      numeric(12,1) NOT NULL,
  read_at    timestamptz NOT NULL,
  source     text NOT NULL DEFAULT 'MANUAL',
  reset_reason text,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_vehicle_meter_reading PRIMARY KEY (vehicle_meter_reading_id),
  CONSTRAINT fk_vmr__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vmr__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vmr_kind   CHECK (meter_kind IN ('ODOMETER_KM','HOUR_METER')),
  CONSTRAINT ck_vmr_value  CHECK (value >= 0 AND value < 100000000),
  CONSTRAINT ck_vmr_source CHECK (source IN ('MANUAL','TELEMATICS')),
  CONSTRAINT ck_vmr_reset  CHECK (reset_reason IS NULL OR reset_reason IN ('METER_REPLACED','ROLLOVER','ENTRY_ERROR'))
);
CREATE INDEX ix_vmr_vehicle ON vehicle_meter_reading (tenant_id, vehicle_id, meter_kind, read_at DESC, recorded_at DESC);
SELECT app.apply_tenant_rls('vehicle_meter_reading', 'SELECT, INSERT');
CREATE TRIGGER tg_vehicle_meter_reading_append_only BEFORE UPDATE OR DELETE ON vehicle_meter_reading
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE vehicle_document (
  vehicle_document_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  doc_type   text NOT NULL,
  reference  text NOT NULL,
  issuer     text,
  valid_from date,
  valid_until date,
  status     text NOT NULL DEFAULT 'VALID',
  status_reason text,
  blocks_assignment boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle_document PRIMARY KEY (vehicle_document_id),
  CONSTRAINT fk_vd__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vd_type   CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION','ROAD_PERMIT','REGISTRATION',
                                              'SITE_ACCESS_PERMIT','OTHER')),
  CONSTRAINT ck_vd_status CHECK (status IN ('VALID','WITHDRAWN')),
  CONSTRAINT ck_vd_reason CHECK ((status = 'WITHDRAWN') = (status_reason IS NOT NULL)),
  CONSTRAINT ck_vd_dates  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from),
  -- Un document bloquant a toujours une échéance : sinon il ne bloquerait jamais (RM-104).
  CONSTRAINT ck_vd_blocking_dated CHECK (NOT blocks_assignment OR valid_until IS NOT NULL),
  CONSTRAINT ck_vd_reference CHECK (char_length(reference) BETWEEN 1 AND 60),
  CONSTRAINT ck_vd_version CHECK (row_version >= 1)
);
CREATE INDEX ix_vd_vehicle ON vehicle_document (tenant_id, vehicle_id, doc_type);
CREATE INDEX ix_vd_expiry ON vehicle_document (tenant_id, valid_until) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('vehicle_document', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_document');
"""

DOWNGRADE = r"""
DROP TABLE vehicle_document;
DROP TABLE vehicle_meter_reading;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
