"""Maintenance (lot 3a) : ordres de travail, événements et temps passé en ajout seul.

Revision ID: 0017
Revises: 0016

Voir docs/PLAN_LOT3.md. Le cycle de vie suit MODELE_CONCEPTUEL §4.5 (codes figés). Les transitions sont
tracées dans `work_order_event` (ajout seul) : base des durées d'immobilisation (3b) et de la
traçabilité. Le temps passé est en ajout seul. Numéro lisible par tenant via un compteur verrouillé.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_counter (
  tenant_id uuid NOT NULL,
  last_number integer NOT NULL DEFAULT 0,
  CONSTRAINT pk_maintenance_counter PRIMARY KEY (tenant_id),
  CONSTRAINT fk_mc__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT ck_mc_number CHECK (last_number >= 0)
);
SELECT app.apply_tenant_rls('maintenance_counter', 'SELECT, INSERT, UPDATE');

CREATE TABLE work_order (
  work_order_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  number     integer NOT NULL,
  site_id    uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  mission_id uuid,
  kind       text NOT NULL DEFAULT 'CORRECTIVE',
  priority   text NOT NULL,
  symptom_code text NOT NULL,
  description text,
  immobilize boolean NOT NULL DEFAULT false,
  status     text NOT NULL DEFAULT 'REQUESTED',
  status_reason text,
  assigned_to uuid,
  expected_ready_at timestamptz,
  diagnosis  text,
  work_done  text,
  parts_note text,
  reported_at timestamptz NOT NULL,
  reported_by uuid NOT NULL,
  approved_at timestamptz, approved_by uuid,
  started_at  timestamptz,
  submitted_at timestamptz,
  closed_at   timestamptz, closed_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_work_order PRIMARY KEY (work_order_id),
  CONSTRAINT uq_work_order_tenant_id UNIQUE (tenant_id, work_order_id),
  CONSTRAINT uq_work_order_number UNIQUE (tenant_id, number),
  CONSTRAINT fk_wo__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wo__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wo__mission FOREIGN KEY (tenant_id, mission_id) REFERENCES mission (tenant_id, mission_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wo__assignee FOREIGN KEY (tenant_id, assigned_to) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_wo_kind CHECK (kind IN ('CORRECTIVE','PREVENTIVE')),
  CONSTRAINT ck_wo_priority CHECK (priority IN ('CRITICAL','HIGH','NORMAL','LOW')),
  CONSTRAINT ck_wo_symptom CHECK (symptom_code IN ('ENGINE','BRAKES','TYRES','HYDRAULICS','ELECTRICAL',
                                                   'TRANSMISSION','STEERING','COOLING','BODY',
                                                   'SAFETY_EQUIPMENT','SERVICE','OTHER')),
  CONSTRAINT ck_wo_status CHECK (status IN ('REQUESTED','APPROVED','ASSIGNED','IN_PROGRESS','AWAITING_PARTS',
                                            'QUALITY_CHECK','CLOSED','REJECTED','CANCELLED')),
  CONSTRAINT ck_wo_assigned CHECK (status IN ('REQUESTED','APPROVED','REJECTED','CANCELLED') OR assigned_to IS NOT NULL),
  CONSTRAINT ck_wo_reason CHECK (status NOT IN ('REJECTED','CANCELLED','AWAITING_PARTS') OR status_reason IS NOT NULL),
  CONSTRAINT ck_wo_closed CHECK (status <> 'CLOSED' OR (closed_at IS NOT NULL AND closed_by IS NOT NULL)),
  CONSTRAINT ck_wo_text CHECK (char_length(coalesce(description,'')) <= 2000 AND char_length(coalesce(diagnosis,'')) <= 4000
                               AND char_length(coalesce(work_done,'')) <= 4000 AND char_length(coalesce(parts_note,'')) <= 2000),
  CONSTRAINT ck_wo_version CHECK (row_version >= 1)
);
CREATE INDEX ix_wo_site_status ON work_order (tenant_id, site_id, status, reported_at DESC);
CREATE INDEX ix_wo_vehicle ON work_order (tenant_id, vehicle_id, status);
SELECT app.apply_tenant_rls('work_order', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('work_order');

CREATE TABLE work_order_event (
  work_order_event_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  work_order_id uuid NOT NULL,
  event_type text NOT NULL,
  from_status text,
  to_status text NOT NULL,
  reason text,
  actor_user_id uuid NOT NULL,
  -- Personne visée (mécanicien assigné) : chaîne des assignés reconstituable (revue L3A-R-08).
  subject_user_id uuid,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_work_order_event PRIMARY KEY (work_order_event_id),
  CONSTRAINT fk_woe__wo FOREIGN KEY (tenant_id, work_order_id) REFERENCES work_order (tenant_id, work_order_id) ON DELETE RESTRICT,
  CONSTRAINT fk_woe__subject FOREIGN KEY (tenant_id, subject_user_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_woe_type CHECK (event_type IN ('REQUESTED','APPROVED','REJECTED','ASSIGNED','STARTED','AWAITING_PARTS',
                                               'RESUMED','SUBMITTED','NOTED','QC_FAILED','CLOSED','CANCELLED'))
);
CREATE INDEX ix_woe_wo ON work_order_event (tenant_id, work_order_id, occurred_at);
SELECT app.apply_tenant_rls('work_order_event', 'SELECT, INSERT');
CREATE TRIGGER tg_work_order_event_append_only BEFORE UPDATE OR DELETE ON work_order_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE work_order_labour (
  work_order_labour_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  work_order_id uuid NOT NULL,
  mechanic_id uuid NOT NULL,
  minutes integer NOT NULL,
  performed_on date NOT NULL,
  note text,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_work_order_labour PRIMARY KEY (work_order_labour_id),
  CONSTRAINT fk_wol__wo FOREIGN KEY (tenant_id, work_order_id) REFERENCES work_order (tenant_id, work_order_id) ON DELETE RESTRICT,
  CONSTRAINT fk_wol__mechanic FOREIGN KEY (tenant_id, mechanic_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_wol_minutes CHECK (minutes BETWEEN 1 AND 960),
  CONSTRAINT ck_wol_note CHECK (char_length(coalesce(note,'')) <= 500)
);
CREATE INDEX ix_wol_wo ON work_order_labour (tenant_id, work_order_id);
SELECT app.apply_tenant_rls('work_order_labour', 'SELECT, INSERT');
CREATE TRIGGER tg_work_order_labour_append_only BEFORE UPDATE OR DELETE ON work_order_labour
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE work_order_labour;
DROP TABLE work_order_event;
DROP TABLE work_order;
DROP TABLE maintenance_counter;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
