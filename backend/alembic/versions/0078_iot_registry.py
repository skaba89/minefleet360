"""Industrial IoT registry foundation; no ingestion or activation.

Revision ID: 0078
Revises: 0077
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE iot_manufacturer (
  manufacturer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, manufacturer_id)
);
CREATE UNIQUE INDEX uq_iot_manufacturer_name ON iot_manufacturer (tenant_id, lower(btrim(name)));
SELECT app.apply_tenant_rls('iot_manufacturer', 'SELECT, INSERT');

CREATE TABLE iot_gateway (
  gateway_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  manufacturer_id uuid NOT NULL,
  external_id text NOT NULL CHECK (char_length(btrim(external_id)) BETWEEN 1 AND 120),
  model text NOT NULL CHECK (char_length(btrim(model)) BETWEEN 1 AND 120),
  source_kind text NOT NULL CHECK (source_kind IN ('SIMULATED','PHYSICAL')),
  status text NOT NULL DEFAULT 'REGISTERED' CHECK (status IN ('REGISTERED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, gateway_id, site_id, source_kind),
  UNIQUE (tenant_id, manufacturer_id, external_id, source_kind),
  FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, manufacturer_id)
    REFERENCES iot_manufacturer (tenant_id, manufacturer_id) ON DELETE RESTRICT
);
CREATE INDEX ix_iot_gateway_site ON iot_gateway (tenant_id, site_id);
SELECT app.apply_tenant_rls('iot_gateway', 'SELECT, INSERT');

CREATE TABLE iot_sensor (
  sensor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  gateway_id uuid NOT NULL,
  manufacturer_id uuid NOT NULL,
  external_id text NOT NULL CHECK (char_length(btrim(external_id)) BETWEEN 1 AND 120),
  model text NOT NULL CHECK (char_length(btrim(model)) BETWEEN 1 AND 120),
  source_kind text NOT NULL CHECK (source_kind IN ('SIMULATED','PHYSICAL')),
  sensor_kind text NOT NULL CHECK (sensor_kind IN ('TPMS','HUB_TEMPERATURE','WHEEL_LOOSENING','COMBINED')),
  status text NOT NULL DEFAULT 'REGISTERED' CHECK (status IN ('REGISTERED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sensor_id),
  UNIQUE (tenant_id, gateway_id, external_id),
  FOREIGN KEY (tenant_id, gateway_id, site_id, source_kind)
    REFERENCES iot_gateway (tenant_id, gateway_id, site_id, source_kind) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, manufacturer_id)
    REFERENCES iot_manufacturer (tenant_id, manufacturer_id) ON DELETE RESTRICT
);
CREATE INDEX ix_iot_sensor_site ON iot_sensor (tenant_id, site_id);
SELECT app.apply_tenant_rls('iot_sensor', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE iot_sensor;
DROP TABLE iot_gateway;
DROP TABLE iot_manufacturer;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
