"""Pneumatiques (chantier B) : pneus individuels, positions montées, chronologie en ajout seul.

Revision ID: 0053
Revises: 0052

Voir docs/LIVRAISON_PNEUS.md. Un pneu est identifié par marque + numéro de série et peut être rattaché à un
article du catalogue de pièces (pas de second référentiel d'articles). États : IN_STOCK → MOUNTED → IN_STOCK,
IN_STOCK → IN_REPAIR → IN_STOCK (réparé ou rechapé), toute sortie définitive → SCRAPPED. Une position d'un
engin ne porte qu'un pneu à la fois (index unique partiel). Chaque étape est un événement en ajout seul
portant les compteurs de l'engin : base du coût au kilomètre et à l'heure.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE tyre (
  tyre_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  serial_number text NOT NULL,
  brand text NOT NULL,
  model text NOT NULL,
  size text NOT NULL,
  category text NOT NULL,
  spare_part_id uuid,
  purchase_cost numeric(20,2),
  currency text,
  initial_tread_mm numeric(5,1) NOT NULL,
  scrap_tread_mm numeric(5,1) NOT NULL,
  nominal_pressure_kpa integer,
  status text NOT NULL DEFAULT 'IN_STOCK',
  vehicle_id uuid,
  position_code text,
  mounted_at timestamptz,
  retread_count integer NOT NULL DEFAULT 0,
  last_tread_mm numeric(5,1),
  last_pressure_kpa integer,
  last_inspected_at timestamptz,
  scrap_reason text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_tyre PRIMARY KEY (tyre_id),
  CONSTRAINT uq_tyre_tenant_id UNIQUE (tenant_id, tyre_id),
  CONSTRAINT fk_tyre__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tyre__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tyre__part FOREIGN KEY (tenant_id, spare_part_id) REFERENCES spare_part (tenant_id, spare_part_id) ON DELETE RESTRICT,
  CONSTRAINT ck_tyre_category CHECK (category IN ('STEER','DRIVE','TRAILER','ALL_POSITION')),
  CONSTRAINT ck_tyre_status CHECK (status IN ('IN_STOCK','MOUNTED','IN_REPAIR','SCRAPPED')),
  CONSTRAINT ck_tyre_mounted CHECK ((status = 'MOUNTED') = (vehicle_id IS NOT NULL AND position_code IS NOT NULL
                                                           AND mounted_at IS NOT NULL)),
  CONSTRAINT ck_tyre_scrapped CHECK (status <> 'SCRAPPED' OR scrap_reason IS NOT NULL),
  CONSTRAINT ck_tyre_cost CHECK ((purchase_cost IS NULL) = (currency IS NULL)
                                 AND coalesce(purchase_cost, 0) >= 0 AND (currency IS NULL OR currency ~ '^[A-Z]{3}$')),
  CONSTRAINT ck_tyre_tread CHECK (initial_tread_mm > 0 AND initial_tread_mm <= 300 AND scrap_tread_mm >= 0
                                  AND scrap_tread_mm < initial_tread_mm
                                  AND (last_tread_mm IS NULL OR last_tread_mm BETWEEN 0 AND 300)),
  CONSTRAINT ck_tyre_pressure CHECK (coalesce(nominal_pressure_kpa, 1) BETWEEN 1 AND 2000
                                     AND coalesce(last_pressure_kpa, 0) BETWEEN 0 AND 2000),
  CONSTRAINT ck_tyre_position CHECK (position_code IS NULL OR position_code ~ '^[A-Z0-9-]{1,16}$'),
  CONSTRAINT ck_tyre_text CHECK (char_length(serial_number) BETWEEN 1 AND 64 AND char_length(brand) BETWEEN 1 AND 64
                                 AND char_length(model) BETWEEN 1 AND 64 AND char_length(size) BETWEEN 1 AND 32),
  CONSTRAINT ck_tyre_retread CHECK (retread_count BETWEEN 0 AND 20),
  CONSTRAINT ck_tyre_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_tyre_serial ON tyre (tenant_id, lower(brand), lower(serial_number));
-- Une position d'engin ne porte qu'un pneu à la fois : le second montage concurrent échoue.
CREATE UNIQUE INDEX uq_tyre_mounted_position ON tyre (tenant_id, vehicle_id, position_code) WHERE status = 'MOUNTED';
CREATE INDEX ix_tyre_site_status ON tyre (tenant_id, site_id, status);
SELECT app.apply_tenant_rls('tyre', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('tyre');

CREATE TABLE tyre_event (
  tyre_event_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  tyre_id uuid NOT NULL,
  event_type text NOT NULL,
  vehicle_id uuid,
  position_code text,
  odometer_km numeric(12,1),
  hour_meter numeric(12,1),
  tread_mm numeric(5,1),
  pressure_kpa integer,
  cost numeric(20,2),
  currency text,
  reason_code text,
  work_order_id uuid,
  note text,
  actor_user_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_tyre_event PRIMARY KEY (tyre_event_id),
  CONSTRAINT fk_tyree__tyre FOREIGN KEY (tenant_id, tyre_id) REFERENCES tyre (tenant_id, tyre_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tyree__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tyree__wo FOREIGN KEY (tenant_id, work_order_id) REFERENCES work_order (tenant_id, work_order_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tyree__actor FOREIGN KEY (tenant_id, actor_user_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_tyree_type CHECK (event_type IN ('REGISTERED','MOUNTED','DISMOUNTED','INSPECTED','SENT_TO_REPAIR',
                                                 'REPAIRED','RETREADED','SCRAPPED')),
  -- Montage et démontage portent au moins un compteur de l'engin : base du coût au km / à l'heure.
  CONSTRAINT ck_tyree_meter CHECK (event_type NOT IN ('MOUNTED','DISMOUNTED')
                                   OR (vehicle_id IS NOT NULL AND position_code IS NOT NULL
                                       AND (odometer_km IS NOT NULL OR hour_meter IS NOT NULL))),
  CONSTRAINT ck_tyree_values CHECK (coalesce(odometer_km, 0) >= 0 AND coalesce(hour_meter, 0) >= 0
                                    AND (tread_mm IS NULL OR tread_mm BETWEEN 0 AND 300)
                                    AND coalesce(pressure_kpa, 0) BETWEEN 0 AND 2000
                                    AND (cost IS NULL) = (currency IS NULL) AND coalesce(cost, 0) >= 0),
  CONSTRAINT ck_tyree_note CHECK (char_length(coalesce(note,'')) <= 1000)
);
CREATE INDEX ix_tyree_tyre ON tyre_event (tenant_id, tyre_id, occurred_at);
CREATE INDEX ix_tyree_vehicle ON tyre_event (tenant_id, vehicle_id, occurred_at) WHERE vehicle_id IS NOT NULL;
SELECT app.apply_tenant_rls('tyre_event', 'SELECT, INSERT');
CREATE TRIGGER tg_tyre_event_append_only BEFORE UPDATE OR DELETE ON tyre_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE tyre_event;
DROP TABLE tyre;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
