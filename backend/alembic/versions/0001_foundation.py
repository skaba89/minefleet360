"""Fondations : fonctions RLS/triggers, référentiels globaux, tenant (MODELE_PHYSIQUE_LOT1 §4, §5.1).

Revision ID: 0001
Revises:
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = r"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')
     OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist')
     OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'citext') THEN
    RAISE EXCEPTION 'extensions postgis, btree_gist et citext requises (infra/db/init/00_bootstrap.sh)';
  END IF;
END $$;

-- Contexte tenant : jamais d'erreur sur valeur vide (DB-03, D-08).
CREATE FUNCTION app.current_tenant_id() RETURNS uuid
  LANGUAGE sql STABLE PARALLEL SAFE
  AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE FUNCTION app.platform_tenant_id() RETURNS uuid
  LANGUAGE sql IMMUTABLE PARALLEL SAFE
  AS $$ SELECT '00000000-0000-4000-8000-000000000001'::uuid $$;

CREATE FUNCTION app.is_platform_context() RETURNS boolean
  LANGUAGE sql STABLE PARALLEL SAFE
  AS $$ SELECT app.current_tenant_id() IS NOT DISTINCT FROM app.platform_tenant_id() $$;

CREATE FUNCTION app.tg_touch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at  := now();
  NEW.row_version := OLD.row_version + 1;
  RETURN NEW;
END $$;

CREATE FUNCTION app.tg_forbid_tenant_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'tenant_id is immutable on %', TG_TABLE_NAME USING ERRCODE = 'MF002';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION app.tg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (% refused)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'MF001';
END $$;

CREATE FUNCTION app.apply_tenant_rls(p_table regclass, p_grants text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', p_table);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', p_table);
  EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', p_table);
  EXECUTE format($p$CREATE POLICY tenant_isolation ON %s AS PERMISSIVE FOR ALL TO mf_app
                    USING (tenant_id = app.current_tenant_id())
                    WITH CHECK (tenant_id = app.current_tenant_id())$p$, p_table);
  EXECUTE format('REVOKE ALL ON %s FROM PUBLIC', p_table);
  EXECUTE format('GRANT %s ON %s TO mf_app', p_grants, p_table);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_forbid_tenant_change ON %s', p_table);
  EXECUTE format($t$CREATE TRIGGER tg_forbid_tenant_change BEFORE UPDATE OF tenant_id ON %s
                    FOR EACH ROW EXECUTE FUNCTION app.tg_forbid_tenant_change()$t$, p_table);
END $$;

CREATE FUNCTION app.apply_touch(p_table regclass) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('DROP TRIGGER IF EXISTS tg_touch ON %s', p_table);
  EXECUTE format('CREATE TRIGGER tg_touch BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION app.tg_touch()',
                 p_table);
END $$;

REVOKE EXECUTE ON FUNCTION app.apply_tenant_rls(regclass, text), app.apply_touch(regclass) FROM PUBLIC;

-- Référentiels globaux (catalogue système, D-18) -------------------------------------------------
CREATE TABLE role (
  role_code      text PRIMARY KEY,
  label_fr       text NOT NULL,
  description_fr text,
  is_optional    boolean NOT NULL DEFAULT false,
  CONSTRAINT ck_role_code CHECK (role_code ~ '^[A-Z][A-Z0-9_]*$')
);
ALTER TABLE role RENAME CONSTRAINT role_pkey TO pk_role;

CREATE TABLE role_allowed_scope (
  role_code  text NOT NULL,
  scope_type text NOT NULL,
  CONSTRAINT pk_role_allowed_scope PRIMARY KEY (role_code, scope_type),
  CONSTRAINT fk_role_allowed_scope__role FOREIGN KEY (role_code) REFERENCES role (role_code) ON DELETE RESTRICT,
  CONSTRAINT ck_role_allowed_scope_type CHECK (scope_type IN ('PLATFORM','TENANT','SITE'))
);

CREATE TABLE license_category_ref (
  code              text NOT NULL,
  label_fr          text NOT NULL,
  validated_locally boolean NOT NULL DEFAULT false,
  is_active         boolean NOT NULL DEFAULT true,
  CONSTRAINT pk_license_category_ref PRIMARY KEY (code)
);

-- Tenant ---------------------------------------------------------------------------------------------
CREATE TABLE tenant (
  tenant_id        uuid NOT NULL DEFAULT gen_random_uuid(),
  code             text NOT NULL,
  kind             text NOT NULL DEFAULT 'CUSTOMER',
  legal_name       text NOT NULL,
  legal_name_norm  text GENERATED ALWAYS AS (lower(regexp_replace(btrim(legal_name), '\s+', ' ', 'g'))) STORED,
  display_name     text NOT NULL,
  status           text NOT NULL DEFAULT 'ACTIVE',
  is_demo          boolean NOT NULL DEFAULT false,
  default_timezone text NOT NULL DEFAULT 'Africa/Conakry',
  default_locale   text NOT NULL DEFAULT 'fr-GN',
  country_code     char(2) NOT NULL DEFAULT 'GN',
  currency_code    char(3) NOT NULL DEFAULT 'GNF',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_tenant                 PRIMARY KEY (tenant_id),
  CONSTRAINT uq_tenant_code            UNIQUE (code),
  CONSTRAINT uq_tenant_legal_name_norm UNIQUE (legal_name_norm),
  CONSTRAINT uq_tenant_id_kind         UNIQUE (tenant_id, kind),
  CONSTRAINT ck_tenant_code    CHECK (code ~ '^[a-z0-9-]{3,32}$'),
  CONSTRAINT ck_tenant_kind    CHECK (kind IN ('CUSTOMER','PLATFORM')),
  CONSTRAINT ck_tenant_status  CHECK (status IN ('ACTIVE','SUSPENDED','ARCHIVED')),
  CONSTRAINT ck_tenant_tz      CHECK (default_timezone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$'),
  CONSTRAINT ck_tenant_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_tenant_single_platform ON tenant ((true)) WHERE kind = 'PLATFORM';

-- Amorçage AVANT FORCE RLS (DB-26) : tenant plateforme et référentiels.
INSERT INTO tenant (tenant_id, code, kind, legal_name, display_name)
VALUES (app.platform_tenant_id(), 'mf-platform', 'PLATFORM', 'MINEFLEET 360 (plateforme)', 'Plateforme');

INSERT INTO role (role_code, label_fr, is_optional) VALUES
 ('PLATFORM_ADMIN','Administrateur plateforme',false), ('TENANT_ADMIN','Administrateur de tenant',false),
 ('DIRECTION','Direction générale',false),            ('OPS_MANAGER','Direction des opérations',false),
 ('DISPATCHER','Dispatcher / régulateur',false),      ('HR','Ressources humaines',false),
 ('DRIVER','Conducteur / opérateur d''engin',false),  ('WORKSHOP_CHIEF','Chef d''atelier',false),
 ('MECHANIC','Mécanicien',false),                     ('STOREKEEPER','Magasinier',false),
 ('FUEL_MANAGER','Responsable carburant',false),      ('HSE','Responsable HSE',false),
 ('FINANCE','Finance / contrôle de gestion',false),   ('AUDITOR','Auditeur',true);
INSERT INTO role_allowed_scope (role_code, scope_type) VALUES
 ('PLATFORM_ADMIN','PLATFORM'),
 ('TENANT_ADMIN','TENANT'), ('DIRECTION','TENANT'), ('AUDITOR','TENANT'),
 ('OPS_MANAGER','TENANT'),('OPS_MANAGER','SITE'), ('DISPATCHER','SITE'),
 ('HR','TENANT'),('HR','SITE'), ('WORKSHOP_CHIEF','TENANT'),('WORKSHOP_CHIEF','SITE'),
 ('MECHANIC','TENANT'),('MECHANIC','SITE'), ('STOREKEEPER','TENANT'),('STOREKEEPER','SITE'),
 ('FUEL_MANAGER','TENANT'),('FUEL_MANAGER','SITE'), ('HSE','TENANT'),('HSE','SITE'),
 ('FINANCE','TENANT'),('FINANCE','SITE'),
 ('DRIVER','SITE');
-- Catégories de permis : valeurs FICTIVES de développement, à valider localement (C-07).
INSERT INTO license_category_ref (code, label_fr) VALUES
 ('A','Motocyclettes'),('B','Véhicules légers'),('C','Poids lourds (porteurs)'),
 ('D','Transport en commun de personnes'),('E','Ensemble avec remorque / semi-remorque');

REVOKE ALL ON role, role_allowed_scope, license_category_ref FROM PUBLIC;
GRANT SELECT ON role, role_allowed_scope, license_category_ref TO mf_app;

-- tenant : politiques dédiées (§6.1)
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON tenant FOR SELECT TO mf_app USING (
     tenant_id = app.current_tenant_id()
  OR app.is_platform_context()
  OR code = NULLIF(current_setting('app.login_tenant_code', true), ''));
CREATE POLICY tenant_insert ON tenant FOR INSERT TO mf_app WITH CHECK (app.is_platform_context());
CREATE POLICY tenant_update ON tenant FOR UPDATE TO mf_app
  USING (tenant_id = app.current_tenant_id() OR app.is_platform_context())
  WITH CHECK (tenant_id = app.current_tenant_id() OR app.is_platform_context());
REVOKE ALL ON tenant FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON tenant TO mf_app;

CREATE FUNCTION app.tg_tenant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT app.is_platform_context() AND
     (NEW.code, NEW.kind, NEW.status, NEW.is_demo, NEW.legal_name)
       IS DISTINCT FROM (OLD.code, OLD.kind, OLD.status, OLD.is_demo, OLD.legal_name) THEN
    RAISE EXCEPTION 'tenant governance fields require platform context' USING ERRCODE = 'MF002';
  END IF;
  IF NEW.kind IS DISTINCT FROM OLD.kind THEN
    RAISE EXCEPTION 'tenant.kind is immutable' USING ERRCODE = 'MF002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_tenant_guard BEFORE UPDATE ON tenant FOR EACH ROW EXECUTE FUNCTION app.tg_tenant_guard();
SELECT app.apply_touch('tenant');
"""

DOWNGRADE = r"""
DROP TABLE tenant;
DROP TABLE license_category_ref;
DROP TABLE role_allowed_scope;
DROP TABLE role;
DROP FUNCTION app.tg_tenant_guard();
DROP FUNCTION app.apply_touch(regclass);
DROP FUNCTION app.apply_tenant_rls(regclass, text);
DROP FUNCTION app.tg_append_only();
DROP FUNCTION app.tg_forbid_tenant_change();
DROP FUNCTION app.tg_touch();
DROP FUNCTION app.is_platform_context();
DROP FUNCTION app.platform_tenant_id();
DROP FUNCTION app.current_tenant_id();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
