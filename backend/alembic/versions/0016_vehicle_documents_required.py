"""Documents exigés par catégorie, documents immuables (revue L2C, décisions D-42 et D-43).

Revision ID: 0016
Revises: 0015

La PR #16 a été fusionnée avec la migration 0015 d'origine : celle-ci reste inchangée et cette migration
applique les correctifs de la revue sécurité du lot 2c.
- L'exigence documentaire passe du document (`blocks_assignment`, colonne conservée mais plus lue) à la
  CATÉGORIE du véhicule (catalogue par tenant copié d'un modèle global, D-18), sans suppression (D-19).
- Nouveaux types : inspection technique interne, vérification de levage.
- Échéance obligatoire sauf pour la carte grise : contrainte posée puis VALIDÉE, la migration échoue
  si un document non daté existe (aucun en recette ni en production à cette date).
- Document immuable une fois saisi : seul le retrait motivé est permis (trigger).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UPGRADE = r"""
SET LOCAL row_security = on;

DO $$
BEGIN
  IF current_user <> 'mf_owner' THEN
    RAISE EXCEPTION 'migration 0016 requires role mf_owner';
  END IF;
END $$;

ALTER TABLE vehicle_document DROP CONSTRAINT ck_vd_blocking_dated;
-- Colonne conservée mais plus utilisée (aucune suppression de données sans accord, CLAUDE.md) :
-- l'exigence vient désormais de la catégorie. Suppression à décider une fois la version validée.
ALTER TABLE vehicle_document ALTER COLUMN blocks_assignment DROP NOT NULL;
ALTER TABLE vehicle_document ALTER COLUMN blocks_assignment SET DEFAULT false;
COMMENT ON COLUMN vehicle_document.blocks_assignment IS 'Obsolète depuis 0016 (D-42) : non lue par l''application.';
ALTER TABLE vehicle_document DROP CONSTRAINT ck_vd_type;
ALTER TABLE vehicle_document ADD CONSTRAINT ck_vd_type CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION','INTERNAL_INSPECTION','LIFTING_INSPECTION',
                                              'ROAD_PERMIT','REGISTRATION','SITE_ACCESS_PERMIT','OTHER'));
-- Seule la carte grise est sans échéance (revue L2C-R-03).
ALTER TABLE vehicle_document ADD CONSTRAINT ck_vd_dated
  CHECK (doc_type = 'REGISTRATION' OR valid_until IS NOT NULL) NOT VALID;
-- Validation immédiate (hors RLS) : la migration ÉCHOUE plutôt que de laisser un document non daté
-- couvrir indéfiniment un type exigé ; un tel document devra être daté ou retiré à la main avant.
ALTER TABLE vehicle_document VALIDATE CONSTRAINT ck_vd_dated;

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
  CONSTRAINT ck_vcd_type CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION','INTERNAL_INSPECTION','LIFTING_INSPECTION',
                                              'ROAD_PERMIT','REGISTRATION','SITE_ACCESS_PERMIT','OTHER'))
);
SELECT app.apply_tenant_rls('vehicle_category_document', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_category_document');

-- Copie des valeurs par défaut pour les tenants existants (visibilité temporaire limitée au rôle de
-- migration, comme 0007 ; retirée dans la même transaction).
CREATE POLICY migration_0016_owner_select ON vehicle_category FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0016_owner_insert ON vehicle_category_document FOR INSERT TO mf_owner WITH CHECK (true);
INSERT INTO vehicle_category_document (tenant_id, vehicle_category_id, doc_type)
SELECT vc.tenant_id, vc.vehicle_category_id, t.doc_type
  FROM vehicle_category vc
  JOIN vehicle_category_document_template t ON t.category_code = vc.code
 WHERE vc.is_system;
DROP POLICY migration_0016_owner_insert ON vehicle_category_document;
DROP POLICY migration_0016_owner_select ON vehicle_category;
"""

DOWNGRADE = r"""
DROP TABLE vehicle_category_document;
DROP TABLE vehicle_category_document_template;
DROP TRIGGER tg_vehicle_document_guard ON vehicle_document;
DROP FUNCTION app.tg_vehicle_document_guard();
ALTER TABLE vehicle_document DROP CONSTRAINT ck_vd_dated;
ALTER TABLE vehicle_document DROP CONSTRAINT ck_vd_type;
ALTER TABLE vehicle_document ADD CONSTRAINT ck_vd_type CHECK (doc_type IN ('INSURANCE','TECHNICAL_INSPECTION',
  'ROAD_PERMIT','REGISTRATION','SITE_ACCESS_PERMIT','OTHER')) NOT VALID;
ALTER TABLE vehicle_document ALTER COLUMN blocks_assignment SET NOT NULL;
ALTER TABLE vehicle_document ALTER COLUMN blocks_assignment DROP DEFAULT;
COMMENT ON COLUMN vehicle_document.blocks_assignment IS NULL;
ALTER TABLE vehicle_document ADD CONSTRAINT ck_vd_blocking_dated
  CHECK (NOT blocks_assignment OR valid_until IS NOT NULL) NOT VALID;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
