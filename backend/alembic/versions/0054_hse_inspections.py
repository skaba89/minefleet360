"""HSE-2 : modèles de checklists, inspections, preuves photo et actions correctives d'inspection.

Revision ID: 0054
Revises: 0053

Voir docs/LIVRAISON_HSE2.md. Additif : la seule modification d'une table existante rend `hse_incident_id`
facultatif sur `hse_corrective_action` (une action naît d'un incident OU d'une inspection, exactement un parent).
Les inspections, leurs réponses et les preuves sont en ajout seul. Les éléments d'un modèle de checklist sont
immuables : toute modification crée une nouvelle version, l'inspection référence la version utilisée.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE hse_counter ADD COLUMN last_inspection_number integer NOT NULL DEFAULT 0;

CREATE TABLE hse_checklist_template (
  hse_checklist_template_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code text NOT NULL,
  version integer NOT NULL,
  name text NOT NULL,
  target_type text NOT NULL,
  items jsonb NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_hse_checklist_template PRIMARY KEY (hse_checklist_template_id),
  CONSTRAINT uq_hsect_tenant_id UNIQUE (tenant_id, hse_checklist_template_id),
  CONSTRAINT fk_hsect__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsect__author FOREIGN KEY (tenant_id, created_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hsect_code CHECK (code ~ '^[A-Za-z0-9_-]{1,48}$'),
  CONSTRAINT ck_hsect_name CHECK (char_length(name) BETWEEN 3 AND 200),
  CONSTRAINT ck_hsect_target CHECK (target_type IN ('PRE_SHIFT','VEHICLE','WORK_AREA')),
  CONSTRAINT ck_hsect_items CHECK (jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 100),
  CONSTRAINT ck_hsect_version CHECK (version BETWEEN 1 AND 10000)
);
CREATE UNIQUE INDEX uq_hsect_code_version ON hse_checklist_template (tenant_id, lower(code), version);
SELECT app.apply_tenant_rls('hse_checklist_template', 'SELECT, INSERT, UPDATE');

-- Seul l'indicateur `active` peut changer : le contenu d'une version déjà utilisée reste celui des inspections.
CREATE FUNCTION app.tg_hse_template_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.tenant_id, NEW.code, NEW.version, NEW.name, NEW.target_type, NEW.items, NEW.created_by, NEW.created_at)
     IS DISTINCT FROM
     (OLD.tenant_id, OLD.code, OLD.version, OLD.name, OLD.target_type, OLD.items, OLD.created_by, OLD.created_at) THEN
    RAISE EXCEPTION 'modèle de checklist immuable : créer une nouvelle version' USING ERRCODE = 'MF001';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_hse_checklist_template_immutable BEFORE UPDATE ON hse_checklist_template
  FOR EACH ROW EXECUTE FUNCTION app.tg_hse_template_immutable();
CREATE TRIGGER tg_hse_checklist_template_no_delete BEFORE DELETE ON hse_checklist_template
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE hse_inspection (
  hse_inspection_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  number integer NOT NULL,
  hse_checklist_template_id uuid NOT NULL,
  target_type text NOT NULL,
  vehicle_id uuid,
  area_note text,
  performed_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL,
  performed_by uuid NOT NULL,
  result text NOT NULL,
  nonconformities integer NOT NULL,
  critical_nonconformities integer NOT NULL,
  note text,
  CONSTRAINT pk_hse_inspection PRIMARY KEY (hse_inspection_id),
  CONSTRAINT uq_hsein_tenant_id UNIQUE (tenant_id, hse_inspection_id),
  CONSTRAINT uq_hsein_site_id UNIQUE (tenant_id, hse_inspection_id, site_id),
  CONSTRAINT uq_hsein_number UNIQUE (tenant_id, number),
  CONSTRAINT fk_hsein__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsein__template FOREIGN KEY (tenant_id, hse_checklist_template_id)
    REFERENCES hse_checklist_template (tenant_id, hse_checklist_template_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsein__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsein__inspector FOREIGN KEY (tenant_id, performed_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hsein_target CHECK (target_type IN ('PRE_SHIFT','VEHICLE','WORK_AREA')),
  CONSTRAINT ck_hsein_vehicle CHECK (target_type <> 'VEHICLE' OR vehicle_id IS NOT NULL),
  CONSTRAINT ck_hsein_area CHECK (target_type <> 'WORK_AREA' OR area_note IS NOT NULL),
  CONSTRAINT ck_hsein_result CHECK (result IN ('PASS','FAIL')),
  CONSTRAINT ck_hsein_counts CHECK (nonconformities >= 0 AND critical_nonconformities BETWEEN 0 AND nonconformities),
  CONSTRAINT ck_hsein_performed CHECK (performed_at <= recorded_at + interval '10 minutes'),
  CONSTRAINT ck_hsein_text CHECK (char_length(coalesce(area_note,'')) <= 200 AND char_length(coalesce(note,'')) <= 2000)
);
CREATE INDEX ix_hsein_site ON hse_inspection (tenant_id, site_id, performed_at DESC);
CREATE INDEX ix_hsein_vehicle ON hse_inspection (tenant_id, vehicle_id, performed_at DESC) WHERE vehicle_id IS NOT NULL;
SELECT app.apply_tenant_rls('hse_inspection', 'SELECT, INSERT');
CREATE TRIGGER tg_hse_inspection_append_only BEFORE UPDATE OR DELETE ON hse_inspection
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE hse_inspection_answer (
  hse_inspection_answer_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  hse_inspection_id uuid NOT NULL,
  position integer NOT NULL,
  item_key text NOT NULL,
  label text NOT NULL,
  critical boolean NOT NULL,
  result text NOT NULL,
  comment text,
  CONSTRAINT pk_hse_inspection_answer PRIMARY KEY (hse_inspection_answer_id),
  CONSTRAINT uq_hseia_item UNIQUE (tenant_id, hse_inspection_id, item_key),
  CONSTRAINT fk_hseia__inspection FOREIGN KEY (tenant_id, hse_inspection_id)
    REFERENCES hse_inspection (tenant_id, hse_inspection_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hseia_result CHECK (result IN ('COMPLIANT','NON_COMPLIANT','NOT_APPLICABLE')),
  CONSTRAINT ck_hseia_comment CHECK (result <> 'NON_COMPLIANT' OR comment IS NOT NULL),
  CONSTRAINT ck_hseia_text CHECK (char_length(item_key) BETWEEN 1 AND 48 AND char_length(label) BETWEEN 1 AND 300
                                  AND char_length(coalesce(comment,'')) <= 1000)
);
SELECT app.apply_tenant_rls('hse_inspection_answer', 'SELECT, INSERT');
CREATE TRIGGER tg_hse_inspection_answer_append_only BEFORE UPDATE OR DELETE ON hse_inspection_answer
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE hse_evidence (
  hse_evidence_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  hse_inspection_id uuid,
  hse_incident_id uuid,
  object_key text NOT NULL,
  content_type text NOT NULL,
  size_bytes integer NOT NULL,
  sha256 text NOT NULL,
  uploaded_by uuid NOT NULL,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_hse_evidence PRIMARY KEY (hse_evidence_id),
  CONSTRAINT uq_hseev_key UNIQUE (object_key),
  CONSTRAINT fk_hseev__inspection FOREIGN KEY (tenant_id, hse_inspection_id, site_id)
    REFERENCES hse_inspection (tenant_id, hse_inspection_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hseev__incident FOREIGN KEY (tenant_id, hse_incident_id, site_id)
    REFERENCES hse_incident (tenant_id, hse_incident_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hseev__uploader FOREIGN KEY (tenant_id, uploaded_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hseev_parent CHECK (num_nonnulls(hse_inspection_id, hse_incident_id) = 1),
  CONSTRAINT ck_hseev_type CHECK (content_type IN ('image/jpeg','image/png')),
  CONSTRAINT ck_hseev_size CHECK (size_bytes BETWEEN 1 AND 2000000),
  CONSTRAINT ck_hseev_hash CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_hseev_key CHECK (object_key ~ '^hse/[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|png)$')
);
CREATE INDEX ix_hseev_inspection ON hse_evidence (tenant_id, hse_inspection_id) WHERE hse_inspection_id IS NOT NULL;
SELECT app.apply_tenant_rls('hse_evidence', 'SELECT, INSERT');
CREATE TRIGGER tg_hse_evidence_append_only BEFORE UPDATE OR DELETE ON hse_evidence
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

ALTER TABLE hse_corrective_action ALTER COLUMN hse_incident_id DROP NOT NULL;
ALTER TABLE hse_corrective_action ADD COLUMN hse_inspection_id uuid;
ALTER TABLE hse_corrective_action ADD CONSTRAINT fk_hseca__inspection FOREIGN KEY (tenant_id, hse_inspection_id, site_id)
  REFERENCES hse_inspection (tenant_id, hse_inspection_id, site_id) ON DELETE RESTRICT;
ALTER TABLE hse_corrective_action ADD CONSTRAINT ck_hseca_parent
  CHECK (num_nonnulls(hse_incident_id, hse_inspection_id) = 1);
CREATE INDEX ix_hseca_inspection ON hse_corrective_action (tenant_id, hse_inspection_id) WHERE hse_inspection_id IS NOT NULL;
"""

DOWNGRADE = r"""
-- Retour arrière destructif (garde guard_destructive) : les actions nées d'une inspection disparaissent avec
-- les inspections. RLS forcée levée le temps de la suppression multi-tenant, puis rétablie.
ALTER TABLE hse_corrective_action NO FORCE ROW LEVEL SECURITY;
DELETE FROM hse_corrective_action WHERE hse_inspection_id IS NOT NULL;
ALTER TABLE hse_corrective_action FORCE ROW LEVEL SECURITY;
DROP INDEX ix_hseca_inspection;
ALTER TABLE hse_corrective_action DROP CONSTRAINT ck_hseca_parent;
ALTER TABLE hse_corrective_action DROP CONSTRAINT fk_hseca__inspection;
ALTER TABLE hse_corrective_action DROP COLUMN hse_inspection_id;
ALTER TABLE hse_corrective_action ALTER COLUMN hse_incident_id SET NOT NULL;
DROP TABLE hse_evidence;
DROP TABLE hse_inspection_answer;
DROP TABLE hse_inspection;
DROP TABLE hse_checklist_template;
DROP FUNCTION app.tg_hse_template_immutable();
ALTER TABLE hse_counter DROP COLUMN last_inspection_number;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
