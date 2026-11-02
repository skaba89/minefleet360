"""HSE (lot HSE-1) : incidents, chronologie en ajout seul et actions correctives.

Revision ID: 0052
Revises: 0051

Voir docs/LIVRAISON_HSE1.md. Un incident suit REPORTED → INVESTIGATING → CLOSED (ou CANCELLED) ; chaque
transition est tracée dans `hse_incident_event` (ajout seul). Les actions correctives suivent
OPEN → DONE → VERIFIED (ou CANCELLED), la vérification étant faite par une autre personne que celle qui a
réalisé l'action. Numéro lisible par tenant via un compteur verrouillé (comme les OT).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE hse_counter (
  tenant_id uuid NOT NULL,
  last_number integer NOT NULL DEFAULT 0,
  CONSTRAINT pk_hse_counter PRIMARY KEY (tenant_id),
  CONSTRAINT fk_hsec__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hsec_number CHECK (last_number >= 0)
);
SELECT app.apply_tenant_rls('hse_counter', 'SELECT, INSERT, UPDATE');

CREATE TABLE hse_incident (
  hse_incident_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  number integer NOT NULL,
  category text NOT NULL,
  severity text NOT NULL,
  title text NOT NULL,
  description text NOT NULL,
  occurred_at timestamptz NOT NULL,
  location_note text,
  vehicle_id uuid,
  injured_count integer NOT NULL DEFAULT 0,
  lost_time boolean NOT NULL DEFAULT false,
  immediate_actions text,
  status text NOT NULL DEFAULT 'REPORTED',
  status_reason text,
  root_cause text,
  investigation_summary text,
  reported_at timestamptz NOT NULL,
  reported_by uuid NOT NULL,
  closed_at timestamptz,
  closed_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_hse_incident PRIMARY KEY (hse_incident_id),
  CONSTRAINT uq_hse_incident_tenant_id UNIQUE (tenant_id, hse_incident_id),
  CONSTRAINT uq_hse_incident_site_id UNIQUE (tenant_id, hse_incident_id, site_id),
  CONSTRAINT uq_hse_incident_number UNIQUE (tenant_id, number),
  CONSTRAINT fk_hsei__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsei__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsei__reporter FOREIGN KEY (tenant_id, reported_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsei__closer FOREIGN KEY (tenant_id, closed_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hsei_category CHECK (category IN ('INJURY','NEAR_MISS','VEHICLE_COLLISION','PROPERTY_DAMAGE',
                                                  'ENVIRONMENT','SPILL','FIRE','UNSAFE_CONDITION','OTHER')),
  CONSTRAINT ck_hsei_severity CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  CONSTRAINT ck_hsei_status CHECK (status IN ('REPORTED','INVESTIGATING','CLOSED','CANCELLED')),
  CONSTRAINT ck_hsei_injured CHECK (injured_count BETWEEN 0 AND 500),
  -- Tolérance de décalage d'horloge d'un terminal de terrain (CLAUDE.md : clock skew).
  CONSTRAINT ck_hsei_occurred CHECK (occurred_at <= reported_at + interval '10 minutes'),
  CONSTRAINT ck_hsei_reason CHECK (status <> 'CANCELLED' OR status_reason IS NOT NULL),
  CONSTRAINT ck_hsei_closed CHECK (status <> 'CLOSED' OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
                                                          AND root_cause IS NOT NULL)),
  CONSTRAINT ck_hsei_text CHECK (char_length(title) BETWEEN 3 AND 200
                                 AND char_length(description) BETWEEN 10 AND 4000
                                 AND char_length(coalesce(location_note,'')) <= 200
                                 AND char_length(coalesce(immediate_actions,'')) <= 2000
                                 AND char_length(coalesce(root_cause,'')) <= 4000
                                 AND char_length(coalesce(investigation_summary,'')) <= 4000),
  CONSTRAINT ck_hsei_version CHECK (row_version >= 1)
);
CREATE INDEX ix_hsei_site_status ON hse_incident (tenant_id, site_id, status, occurred_at DESC);
CREATE INDEX ix_hsei_vehicle ON hse_incident (tenant_id, vehicle_id) WHERE vehicle_id IS NOT NULL;
SELECT app.apply_tenant_rls('hse_incident', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('hse_incident');

CREATE TABLE hse_incident_event (
  hse_incident_event_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  hse_incident_id uuid NOT NULL,
  event_type text NOT NULL,
  from_status text,
  to_status text NOT NULL,
  reason text,
  actor_user_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_hse_incident_event PRIMARY KEY (hse_incident_event_id),
  CONSTRAINT fk_hsee__incident FOREIGN KEY (tenant_id, hse_incident_id)
    REFERENCES hse_incident (tenant_id, hse_incident_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hsee__actor FOREIGN KEY (tenant_id, actor_user_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hsee_type CHECK (event_type IN ('REPORTED','INVESTIGATION_STARTED','NOTED','CLOSED','CANCELLED',
                                                'ACTION_ADDED','ACTION_COMPLETED','ACTION_VERIFIED',
                                                'ACTION_REOPENED','ACTION_CANCELLED')),
  CONSTRAINT ck_hsee_reason CHECK (char_length(coalesce(reason,'')) <= 500)
);
CREATE INDEX ix_hsee_incident ON hse_incident_event (tenant_id, hse_incident_id, occurred_at);
SELECT app.apply_tenant_rls('hse_incident_event', 'SELECT, INSERT');
CREATE TRIGGER tg_hse_incident_event_append_only BEFORE UPDATE OR DELETE ON hse_incident_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE hse_corrective_action (
  hse_corrective_action_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  hse_incident_id uuid NOT NULL,
  title text NOT NULL,
  description text,
  owner_user_id uuid NOT NULL,
  due_date date NOT NULL,
  status text NOT NULL DEFAULT 'OPEN',
  status_reason text,
  completion_note text,
  completed_at timestamptz,
  completed_by uuid,
  verified_at timestamptz,
  verified_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_hse_corrective_action PRIMARY KEY (hse_corrective_action_id),
  CONSTRAINT uq_hseca_tenant_id UNIQUE (tenant_id, hse_corrective_action_id),
  -- Le site de l'action est celui de l'incident : une action ne peut pas changer de périmètre.
  CONSTRAINT fk_hseca__incident FOREIGN KEY (tenant_id, hse_incident_id, site_id)
    REFERENCES hse_incident (tenant_id, hse_incident_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hseca__owner FOREIGN KEY (tenant_id, owner_user_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hseca__completer FOREIGN KEY (tenant_id, completed_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hseca__verifier FOREIGN KEY (tenant_id, verified_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_hseca_status CHECK (status IN ('OPEN','DONE','VERIFIED','CANCELLED')),
  CONSTRAINT ck_hseca_reason CHECK (status <> 'CANCELLED' OR status_reason IS NOT NULL),
  CONSTRAINT ck_hseca_done CHECK (status NOT IN ('DONE','VERIFIED')
                                  OR (completed_at IS NOT NULL AND completed_by IS NOT NULL
                                      AND completion_note IS NOT NULL)),
  CONSTRAINT ck_hseca_verified CHECK (status <> 'VERIFIED' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL
                                                                AND verified_by <> completed_by)),
  CONSTRAINT ck_hseca_text CHECK (char_length(title) BETWEEN 3 AND 200
                                  AND char_length(coalesce(description,'')) <= 2000
                                  AND char_length(coalesce(completion_note,'')) <= 2000
                                  AND char_length(coalesce(status_reason,'')) <= 500),
  CONSTRAINT ck_hseca_version CHECK (row_version >= 1)
);
CREATE INDEX ix_hseca_incident ON hse_corrective_action (tenant_id, hse_incident_id);
CREATE INDEX ix_hseca_open_due ON hse_corrective_action (tenant_id, site_id, due_date) WHERE status = 'OPEN';
CREATE INDEX ix_hseca_owner ON hse_corrective_action (tenant_id, owner_user_id, status);
SELECT app.apply_tenant_rls('hse_corrective_action', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('hse_corrective_action');
"""

DOWNGRADE = r"""
DROP TABLE hse_corrective_action;
DROP TABLE hse_incident_event;
DROP TABLE hse_incident;
DROP TABLE hse_counter;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
