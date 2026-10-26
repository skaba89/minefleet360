"""Flotte : catalogue de référence, catégories par tenant, véhicules, historique de statut (§5.5).

Revision ID: 0005
Revises: 0004
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- Catalogue de référence GLOBAL (D-18) copié dans chaque tenant à sa création.
-- Valeurs FICTIVES de développement, à valider avec le client et localement (C-07).
CREATE TABLE vehicle_category_template (
  code      text NOT NULL,
  label_fr  text NOT NULL,
  family    text NOT NULL,
  requires_driver                 boolean NOT NULL,
  requires_internal_authorization boolean NOT NULL,
  has_odometer   boolean NOT NULL,
  has_hour_meter boolean NOT NULL,
  CONSTRAINT pk_vehicle_category_template PRIMARY KEY (code)
);
CREATE TABLE vehicle_category_template_license (
  category_code         text NOT NULL,
  license_category_code text NOT NULL,
  CONSTRAINT pk_vehicle_category_template_license PRIMARY KEY (category_code, license_category_code),
  CONSTRAINT fk_vctl__template FOREIGN KEY (category_code) REFERENCES vehicle_category_template (code),
  CONSTRAINT fk_vctl__license  FOREIGN KEY (license_category_code) REFERENCES license_category_ref (code)
);
INSERT INTO vehicle_category_template VALUES
 ('ARTICULATED_DUMP_TRUCK','Camion-benne articulé','HAULAGE',true,true,true,true),
 ('RIGID_DUMP_TRUCK','Camion-benne rigide (tombereau)','HAULAGE',true,true,true,true),
 ('ROAD_DUMP_TRUCK','Camion-benne routier (porteur ou semi)','HAULAGE',true,true,true,true),
 ('HYDRAULIC_EXCAVATOR','Pelle hydraulique','LOADING_EXCAVATION',true,true,false,true),
 ('WHEEL_LOADER','Chargeuse sur pneus','LOADING_EXCAVATION',true,true,false,true),
 ('BULLDOZER','Bulldozer','EARTHWORKS',true,true,false,true),
 ('MOTOR_GRADER','Niveleuse','EARTHWORKS',true,true,false,true),
 ('COMPACTOR','Compacteur','EARTHWORKS',true,true,false,true),
 ('FUEL_TANKER','Camion-citerne carburant','TANKER',true,true,true,true),
 ('WATER_TANKER','Camion-citerne d''arrosage de pistes','TANKER',true,true,true,true),
 ('LOWBED_TRAILER','Porte-engins (semi-remorque surbaissée)','SUPPORT_EQUIPMENT',true,true,true,false),
 ('FORKLIFT_TELEHANDLER','Chariot élévateur / télescopique','SUPPORT_EQUIPMENT',true,true,false,true),
 ('LIGHT_VEHICLE','Véhicule léger (pick-up, 4x4)','LIGHT_VEHICLE',true,false,true,false),
 ('PERSONNEL_BUS','Bus de transport de personnel','PERSONNEL_TRANSPORT',true,true,true,false),
 ('GENERATOR_LIGHTING_TOWER','Groupe électrogène / tour d''éclairage','SUPPORT_EQUIPMENT',false,false,false,true);
INSERT INTO vehicle_category_template_license VALUES
 ('ARTICULATED_DUMP_TRUCK','C'), ('RIGID_DUMP_TRUCK','C'), ('ROAD_DUMP_TRUCK','C'),
 ('FUEL_TANKER','C'), ('WATER_TANKER','C'), ('LOWBED_TRAILER','E'),
 ('LIGHT_VEHICLE','B'), ('PERSONNEL_BUS','D');
REVOKE ALL ON vehicle_category_template, vehicle_category_template_license FROM PUBLIC;
GRANT SELECT ON vehicle_category_template, vehicle_category_template_license TO mf_app;

CREATE TABLE vehicle_category (
  vehicle_category_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code      text NOT NULL,
  label_fr  text NOT NULL,
  family    text NOT NULL,
  requires_driver                  boolean NOT NULL DEFAULT true,
  requires_internal_authorization  boolean NOT NULL DEFAULT true,
  has_odometer   boolean NOT NULL DEFAULT false,
  has_hour_meter boolean NOT NULL DEFAULT false,
  is_system boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle_category PRIMARY KEY (vehicle_category_id),
  CONSTRAINT fk_vehicle_category__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_vehicle_category_tenant_id   UNIQUE (tenant_id, vehicle_category_id),
  CONSTRAINT uq_vehicle_category_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_vehicle_category_code   CHECK (code ~ '^[A-Z0-9_]{3,40}$'),
  CONSTRAINT ck_vehicle_category_family CHECK (family IN ('HAULAGE','LOADING_EXCAVATION','EARTHWORKS','TANKER',
                                                          'PERSONNEL_TRANSPORT','LIGHT_VEHICLE','SUPPORT_EQUIPMENT')),
  CONSTRAINT ck_vehicle_category_version CHECK (row_version >= 1)
);

CREATE TABLE vehicle_category_license_category (
  tenant_id             uuid NOT NULL,
  vehicle_category_id   uuid NOT NULL,
  license_category_code text NOT NULL,
  CONSTRAINT pk_vcat_license PRIMARY KEY (tenant_id, vehicle_category_id, license_category_code),
  CONSTRAINT fk_vcat_license__category FOREIGN KEY (tenant_id, vehicle_category_id)
    REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vcat_license__license FOREIGN KEY (license_category_code)
    REFERENCES license_category_ref (code) ON DELETE RESTRICT
);

-- Copie pour les tenants clients existants, AVANT d'activer FORCE RLS (DB-26).
INSERT INTO vehicle_category (tenant_id, code, label_fr, family, requires_driver, requires_internal_authorization,
                              has_odometer, has_hour_meter, is_system)
SELECT t.tenant_id, c.code, c.label_fr, c.family, c.requires_driver, c.requires_internal_authorization,
       c.has_odometer, c.has_hour_meter, true
FROM tenant t CROSS JOIN vehicle_category_template c WHERE t.kind = 'CUSTOMER';
INSERT INTO vehicle_category_license_category (tenant_id, vehicle_category_id, license_category_code)
SELECT vc.tenant_id, vc.vehicle_category_id, l.license_category_code
FROM vehicle_category vc JOIN vehicle_category_template_license l ON l.category_code = vc.code;

SELECT app.apply_tenant_rls('vehicle_category', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_category');
SELECT app.apply_tenant_rls('vehicle_category_license_category', 'SELECT, INSERT, DELETE');

CREATE TABLE vehicle (
  vehicle_id          uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  site_id             uuid NOT NULL,
  vehicle_category_id uuid NOT NULL,
  fleet_number        text NOT NULL,
  fleet_number_norm   text GENERATED ALWAYS AS (lower(btrim(fleet_number))) STORED,
  registration_number text,
  registration_norm   text GENERATED ALWAYS AS (upper(regexp_replace(registration_number, '[\s\-]', '', 'g'))) STORED,
  serial_number       text,
  serial_key          text GENERATED ALWAYS AS (lower(coalesce(make, '')) || '|' || lower(btrim(serial_number))) STORED,
  make text, model text, model_year smallint,
  ownership_type text NOT NULL DEFAULT 'OWNED',
  fuel_type      text,
  rated_payload_kg integer,
  status             text NOT NULL DEFAULT 'AVAILABLE',
  status_reason_code text,
  status_changed_at  timestamptz NOT NULL DEFAULT now(),
  commissioned_on  date,
  decommissioned_on date,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle PRIMARY KEY (vehicle_id),
  CONSTRAINT fk_vehicle__tenant   FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vehicle__site     FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vehicle__category FOREIGN KEY (tenant_id, vehicle_category_id) REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT uq_vehicle_tenant_id           UNIQUE (tenant_id, vehicle_id),
  CONSTRAINT uq_vehicle_tenant_fleet_number UNIQUE (tenant_id, fleet_number_norm),
  CONSTRAINT uq_vehicle_tenant_registration UNIQUE (tenant_id, registration_norm),
  CONSTRAINT uq_vehicle_tenant_serial       UNIQUE (tenant_id, serial_key),
  CONSTRAINT ck_vehicle_fleet_number CHECK (fleet_number ~ '^[^\s]{1,30}$'),
  CONSTRAINT ck_vehicle_registration CHECK (registration_number IS NULL OR registration_norm <> ''),
  CONSTRAINT ck_vehicle_status    CHECK (status IN ('AVAILABLE','IN_MAINTENANCE','IMMOBILIZED','OUT_OF_SERVICE','RETIRED')),
  CONSTRAINT ck_vehicle_reason    CHECK (status NOT IN ('IMMOBILIZED','OUT_OF_SERVICE','RETIRED') OR status_reason_code IS NOT NULL),
  CONSTRAINT ck_vehicle_retired   CHECK ((status = 'RETIRED') = (decommissioned_on IS NOT NULL)),
  CONSTRAINT ck_vehicle_ownership CHECK (ownership_type IN ('OWNED','LEASED','SUBCONTRACTED')),
  CONSTRAINT ck_vehicle_fuel      CHECK (fuel_type IS NULL OR fuel_type IN ('DIESEL','PETROL','ELECTRIC','OTHER')),
  CONSTRAINT ck_vehicle_payload   CHECK (rated_payload_kg IS NULL OR rated_payload_kg > 0),
  CONSTRAINT ck_vehicle_year      CHECK (model_year IS NULL OR model_year BETWEEN 1950 AND 2100),
  CONSTRAINT ck_vehicle_version   CHECK (row_version >= 1)
);
CREATE INDEX ix_vehicle_tenant_site_status ON vehicle (tenant_id, site_id, status);
CREATE INDEX ix_vehicle_tenant_category    ON vehicle (tenant_id, vehicle_category_id);
SELECT app.apply_tenant_rls('vehicle', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle');

CREATE TABLE vehicle_status_history (
  vehicle_status_history_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  vehicle_id  uuid NOT NULL,
  from_status text,
  to_status   text NOT NULL,
  reason_code text,
  changed_at  timestamptz NOT NULL,
  changed_by  uuid,
  CONSTRAINT pk_vehicle_status_history PRIMARY KEY (vehicle_status_history_id),
  CONSTRAINT fk_vsh__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vsh_to CHECK (to_status IN ('AVAILABLE','IN_MAINTENANCE','IMMOBILIZED','OUT_OF_SERVICE','RETIRED'))
);
CREATE INDEX ix_vsh_vehicle_time ON vehicle_status_history (tenant_id, vehicle_id, changed_at DESC);
SELECT app.apply_tenant_rls('vehicle_status_history', 'SELECT, INSERT');
CREATE TRIGGER tg_vsh_append_only BEFORE UPDATE OR DELETE ON vehicle_status_history
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE FUNCTION app.tg_vehicle_status_before() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN NEW.status_changed_at := now(); END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION app.tg_vehicle_status_after() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO vehicle_status_history (tenant_id, vehicle_id, from_status, to_status, reason_code, changed_at, changed_by)
    VALUES (NEW.tenant_id, NEW.vehicle_id, NULL, NEW.status, NEW.status_reason_code, NEW.status_changed_at, NEW.created_by);
  ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO vehicle_status_history (tenant_id, vehicle_id, from_status, to_status, reason_code, changed_at, changed_by)
    VALUES (NEW.tenant_id, NEW.vehicle_id, OLD.status, NEW.status, NEW.status_reason_code, NEW.status_changed_at, NEW.updated_by);
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER tg_vehicle_status_before BEFORE UPDATE ON vehicle FOR EACH ROW EXECUTE FUNCTION app.tg_vehicle_status_before();
CREATE TRIGGER tg_vehicle_status_after  AFTER INSERT OR UPDATE OF status ON vehicle FOR EACH ROW EXECUTE FUNCTION app.tg_vehicle_status_after();
"""

DOWNGRADE = r"""
DROP TABLE vehicle_status_history;
DROP TABLE vehicle;
DROP FUNCTION app.tg_vehicle_status_after();
DROP FUNCTION app.tg_vehicle_status_before();
DROP TABLE vehicle_category_license_category;
DROP TABLE vehicle_category;
DROP TABLE vehicle_category_template_license;
DROP TABLE vehicle_category_template;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
