"""Pesées (lot 2b) : tickets immuables, décisions (approbation, annulation), mission idempotente.

Revision ID: 0014
Revises: 0013

Voir docs/PLAN_LOT2.md §7. Le poids net est calculé par la base (brut − tare), jamais saisi. Un ticket ne se
modifie jamais : une correction l'annule (décision `VOIDED`) et crée un ticket qui le référence (RM-073).
Le pont-bascule est un lieu du site de type `WEIGHBRIDGE` (référentiel 2a). Aucune donnée GPS (RM-070).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE rotation ADD CONSTRAINT uq_rotation_tenant_id UNIQUE (tenant_id, rotation_id);

-- Revue L2A-R-08 : un renvoi de création de mission (coupure réseau) ne crée pas de doublon.
ALTER TABLE mission ADD COLUMN client_request_id uuid;
ALTER TABLE mission ADD CONSTRAINT uq_mission_client_request UNIQUE (tenant_id, client_request_id);

CREATE TABLE weighing_ticket (
  weighing_ticket_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  site_id    uuid NOT NULL,
  mission_id uuid NOT NULL,
  rotation_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  weighbridge_location_id uuid NOT NULL,
  ticket_number text NOT NULL,
  source     text NOT NULL,
  degraded_reason text,
  weighed_at timestamptz NOT NULL,
  gross_kg   integer NOT NULL,
  tare_kg    integer NOT NULL,
  net_kg     integer GENERATED ALWAYS AS (gross_kg - tare_kg) STORED,
  -- Capacité nominale au moment de la pesée (copie) et alerte de surcharge (RM-076).
  rated_payload_kg integer,
  overload   boolean NOT NULL DEFAULT false,
  replaces_ticket_id uuid,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_weighing_ticket PRIMARY KEY (weighing_ticket_id),
  CONSTRAINT uq_wt_tenant_id UNIQUE (tenant_id, weighing_ticket_id),
  CONSTRAINT fk_wt__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wt__mission FOREIGN KEY (tenant_id, mission_id) REFERENCES mission (tenant_id, mission_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wt__rotation FOREIGN KEY (tenant_id, rotation_id) REFERENCES rotation (tenant_id, rotation_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wt__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wt__weighbridge FOREIGN KEY (tenant_id, site_id, weighbridge_location_id)
    REFERENCES site_location (tenant_id, site_id, site_location_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wt__replaces FOREIGN KEY (tenant_id, replaces_ticket_id)
    REFERENCES weighing_ticket (tenant_id, weighing_ticket_id) ON DELETE RESTRICT,
  CONSTRAINT ck_wt_source CHECK (source IN ('WEIGHBRIDGE','MANUAL_DEGRADED')),
  CONSTRAINT ck_wt_degraded CHECK ((source = 'MANUAL_DEGRADED') = (degraded_reason IS NOT NULL)),
  CONSTRAINT ck_wt_weights CHECK (tare_kg > 0 AND gross_kg > tare_kg AND gross_kg <= 500000),
  CONSTRAINT ck_wt_number CHECK (ticket_number ~ '^[A-Za-z0-9/_-]{1,40}$'),
  CONSTRAINT ck_wt_not_self CHECK (replaces_ticket_id IS NULL OR replaces_ticket_id <> weighing_ticket_id)
);
-- RM-074 : un numéro par pont-bascule pour les tickets d'origine ; un correctif peut reprendre le numéro.
CREATE UNIQUE INDEX uq_wt_number ON weighing_ticket (tenant_id, weighbridge_location_id, ticket_number)
  WHERE replaces_ticket_id IS NULL;
CREATE UNIQUE INDEX uq_wt_replaces ON weighing_ticket (tenant_id, replaces_ticket_id)
  WHERE replaces_ticket_id IS NOT NULL;
CREATE INDEX ix_wt_rotation ON weighing_ticket (tenant_id, rotation_id);
CREATE INDEX ix_wt_site_time ON weighing_ticket (tenant_id, site_id, weighed_at DESC);
SELECT app.apply_tenant_rls('weighing_ticket', 'SELECT, INSERT');
CREATE TRIGGER tg_weighing_ticket_append_only BEFORE UPDATE OR DELETE ON weighing_ticket
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

-- Garde-fous en base, quel que soit le chemin d'écriture (revue L2B-R-01, R-04, R-05) :
--   cohérence avec la rotation (mission, véhicule, site), une seule pesée non annulée par rotation,
--   un numéro non annulé par pont-bascule (correctifs compris). La rotation est verrouillée ; le numéro
--   est protégé par un verrou consultatif de transaction. L'annulation est lue dans la table des décisions.
CREATE FUNCTION app.tg_weighing_ticket_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  r record;
BEGIN
  SELECT ro.mission_id, ro.vehicle_id, m.site_id INTO r
    FROM rotation ro
    JOIN mission m ON m.tenant_id = ro.tenant_id AND m.mission_id = ro.mission_id
   WHERE ro.tenant_id = NEW.tenant_id AND ro.rotation_id = NEW.rotation_id
   FOR UPDATE OF ro;
  IF NOT FOUND OR r.mission_id <> NEW.mission_id OR r.vehicle_id <> NEW.vehicle_id
     OR r.site_id <> NEW.site_id THEN
    RAISE EXCEPTION 'weighing ticket inconsistent with its rotation'
      USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_wt_rotation_consistency';
  END IF;
  IF EXISTS (
    SELECT 1 FROM weighing_ticket t
     WHERE t.tenant_id = NEW.tenant_id AND t.rotation_id = NEW.rotation_id
       AND NOT EXISTS (SELECT 1 FROM weighing_ticket_decision d
                        WHERE d.tenant_id = t.tenant_id AND d.weighing_ticket_id = t.weighing_ticket_id
                          AND d.decision = 'VOIDED')
  ) THEN
    RAISE EXCEPTION 'rotation already has a live weighing ticket'
      USING ERRCODE = 'unique_violation', CONSTRAINT = 'uq_wt_live_rotation';
  END IF;
  PERFORM pg_advisory_xact_lock(
    hashtextextended(NEW.tenant_id::text || '/' || NEW.weighbridge_location_id::text || '/' || NEW.ticket_number, 14));
  IF EXISTS (
    SELECT 1 FROM weighing_ticket t
     WHERE t.tenant_id = NEW.tenant_id AND t.weighbridge_location_id = NEW.weighbridge_location_id
       AND t.ticket_number = NEW.ticket_number
       AND NOT EXISTS (SELECT 1 FROM weighing_ticket_decision d
                        WHERE d.tenant_id = t.tenant_id AND d.weighing_ticket_id = t.weighing_ticket_id
                          AND d.decision = 'VOIDED')
  ) THEN
    RAISE EXCEPTION 'ticket number already used by a live weighing ticket'
      USING ERRCODE = 'unique_violation', CONSTRAINT = 'uq_wt_live_number';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_weighing_ticket_guard BEFORE INSERT ON weighing_ticket
  FOR EACH ROW EXECUTE FUNCTION app.tg_weighing_ticket_guard();

CREATE TABLE weighing_ticket_decision (
  weighing_ticket_decision_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  weighing_ticket_id uuid NOT NULL,
  decision  text NOT NULL,
  reason    text,
  decided_by uuid NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_weighing_ticket_decision PRIMARY KEY (weighing_ticket_decision_id),
  CONSTRAINT fk_wtd__ticket FOREIGN KEY (tenant_id, weighing_ticket_id)
    REFERENCES weighing_ticket (tenant_id, weighing_ticket_id) ON DELETE RESTRICT,
  CONSTRAINT uq_wtd_once UNIQUE (tenant_id, weighing_ticket_id, decision),
  CONSTRAINT ck_wtd_decision CHECK (decision IN ('APPROVED','VOIDED')),
  CONSTRAINT ck_wtd_reason CHECK (decision <> 'VOIDED' OR reason IS NOT NULL)
);
SELECT app.apply_tenant_rls('weighing_ticket_decision', 'SELECT, INSERT');
CREATE TRIGGER tg_weighing_ticket_decision_append_only BEFORE UPDATE OR DELETE ON weighing_ticket_decision
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE weighing_ticket_decision;
DROP TABLE weighing_ticket;
DROP FUNCTION IF EXISTS app.tg_weighing_ticket_guard();
ALTER TABLE mission DROP CONSTRAINT uq_mission_client_request;
ALTER TABLE mission DROP COLUMN client_request_id;
ALTER TABLE rotation DROP CONSTRAINT uq_rotation_tenant_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
