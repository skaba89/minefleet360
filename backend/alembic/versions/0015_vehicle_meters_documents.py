"""Compteurs, documents réglementaires et documents exigés par catégorie (lot 2c, US-2.09, US-2.10, C-06).

Revision ID: 0015
Revises: 0014

Voir docs/PLAN_LOT2.md §8 et DECISIONS_A_ARBITRER.md D-42, D-43.
- Relevés de compteur en AJOUT SEUL ; une remise à zéro est un relevé motivé (action distincte).
- Documents immuables une fois saisis : seul le retrait motivé est possible (trigger) ; une erreur se
  corrige par retrait puis nouvel exemplaire. Validité dérivée des dates (D-03).
- L'exigence documentaire naît de la CATÉGORIE du véhicule (catalogue par tenant, copié d'un modèle
  global comme les catégories, D-18) : un document manquant ou échu d'un type exigé bloque l'affectation.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = r"""
SET LOCAL row_security = on;

DO $$
BEGIN
  IF current_user <> 'mf_owner' THEN
    RAISE EXCEPTION 'migration 0015 requires role mf_owner';
  END IF;
END $$;

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
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle_document PRIMARY KEY (vehicle_document_id),
  CONSTRAINT fk_vd__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vd_type   CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION','INTERNAL_INSPECTION',
                                              'LIFTING_INSPECTION','ROAD_PERMIT','REGISTRATION',
                                              'SITE_ACCESS_PERMIT','OTHER')),
  CONSTRAINT ck_vd_status CHECK (status IN ('VALID','WITHDRAWN')),
  CONSTRAINT ck_vd_reason CHECK ((status = 'WITHDRAWN') = (status_reason IS NOT NULL)),
  CONSTRAINT ck_vd_dates  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from),
  -- Seule la carte grise est sans échéance : tout autre document a une date de fin surveillée (revue L2C-R-03).
  CONSTRAINT ck_vd_dated  CHECK (doc_type = 'REGISTRATION' OR valid_until IS NOT NULL),
  CONSTRAINT ck_vd_reference CHECK (char_length(reference) BETWEEN 1 AND 60),
  CONSTRAINT ck_vd_version CHECK (row_version >= 1)
);
CREATE INDEX ix_vd_vehicle ON vehicle_document (tenant_id, vehicle_id, doc_type);
CREATE INDEX ix_vd_expiry ON vehicle_document (tenant_id, valid_until) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('vehicle_document', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_document');

-- Revue L2C-R-02 / R-09 : un document saisi ne change plus ; seul le retrait motivé est permis, une fois.
CREATE FUNCTION app.tg_vehicle_document_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'VALID' OR NEW.status <> 'WITHDRAWN' OR NEW.status_reason IS NULL
     OR (NEW.tenant_id, NEW.vehicle_id, NEW.doc_type, NEW.reference, NEW.issuer, NEW.valid_from,
         NEW.valid_until, NEW.created_at, NEW.created_by)
        IS DISTINCT FROM
        (OLD.tenant_id, OLD.vehicle_id, OLD.doc_type, OLD.reference, OLD.issuer, OLD.valid_from,
         OLD.valid_until, OLD.created_at, OLD.created_by) THEN
    RAISE EXCEPTION 'vehicle_document is immutable except for its withdrawal' USING ERRCODE = 'MF001';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_vehicle_document_guard BEFORE UPDATE ON vehicle_document
  FOR EACH ROW EXECUTE FUNCTION app.tg_vehicle_document_guard();

-- Documents exigés par catégorie (D-42) : modèle global, puis copie par tenant comme les catégories.
CREATE TABLE vehicle_category_document_template (
  category_code text NOT NULL,
  doc_type      text NOT NULL,
  CONSTRAINT pk_vehicle_category_document_template PRIMARY KEY (category_code, doc_type),
  CONSTRAINT fk_vcdt__template FOREIGN KEY (category_code) REFERENCES vehicle_category_template (code)
);
-- Valeurs par défaut (expert flotte, à valider localement) : véhicules routiers, engins de site, levage.
INSERT INTO vehicle_category_document_template (category_code, doc_type)
SELECT c, d FROM unnest(ARRAY['LIGHT_VEHICLE','PERSONNEL_BUS','ROAD_DUMP_TRUCK','FUEL_TANKER',
                              'WATER_TANKER','LOWBED_TRAILER']) AS c,
                 unnest(ARRAY['INSURANCE','TECHNICAL_INSPECTION','REGISTRATION']) AS d
UNION ALL
SELECT c, d FROM unnest(ARRAY['ARTICULATED_DUMP_TRUCK','RIGID_DUMP_TRUCK','HYDRAULIC_EXCAVATOR',
                              'WHEEL_LOADER','BULLDOZER','MOTOR_GRADER','COMPACTOR',
                              'FORKLIFT_TELEHANDLER']) AS c,
                 unnest(ARRAY['INSURANCE','INTERNAL_INSPECTION','SITE_ACCESS_PERMIT']) AS d
UNION ALL
SELECT 'FORKLIFT_TELEHANDLER', 'LIFTING_INSPECTION'
UNION ALL
SELECT 'GENERATOR_LIGHTING_TOWER', 'INTERNAL_INSPECTION';
REVOKE ALL ON vehicle_category_document_template FROM PUBLIC;
GRANT SELECT ON vehicle_category_document_template TO mf_app;

CREATE TABLE vehicle_category_document (
  tenant_id uuid NOT NULL,
  vehicle_category_id uuid NOT NULL,
  doc_type text NOT NULL,
  -- Exigence retirée = désactivée, jamais supprimée (D-19) ; l'audit garde l'historique.
  required boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle_category_document PRIMARY KEY (tenant_id, vehicle_category_id, doc_type),
  CONSTRAINT fk_vcd__category FOREIGN KEY (tenant_id, vehicle_category_id)
    REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vcd_type CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION','INTERNAL_INSPECTION',
                                             'LIFTING_INSPECTION','ROAD_PERMIT','REGISTRATION',
                                             'SITE_ACCESS_PERMIT','OTHER'))
);
SELECT app.apply_tenant_rls('vehicle_category_document', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_category_document');

-- Copie des valeurs par défaut pour les tenants existants (visibilité temporaire limitée au rôle de
-- migration, comme 0007 ; retirée dans la même transaction).
CREATE POLICY migration_0015_owner_select ON vehicle_category FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0015_owner_insert ON vehicle_category_document FOR INSERT TO mf_owner WITH CHECK (true);
INSERT INTO vehicle_category_document (tenant_id, vehicle_category_id, doc_type)
SELECT vc.tenant_id, vc.vehicle_category_id, t.doc_type
  FROM vehicle_category vc
  JOIN vehicle_category_document_template t ON t.category_code = vc.code
 WHERE vc.is_system;
DROP POLICY migration_0015_owner_insert ON vehicle_category_document;
DROP POLICY migration_0015_owner_select ON vehicle_category;
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS vehicle_category_document;
DROP TABLE IF EXISTS vehicle_category_document_template;
DROP TABLE vehicle_document;
DROP FUNCTION IF EXISTS app.tg_vehicle_document_guard();
DROP TABLE vehicle_meter_reading;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
