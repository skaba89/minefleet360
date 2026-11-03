"""Dernier entretien connu (point de départ des plans préventifs) et échéance « entretien initial ».

Revision ID: 0058
Revises: 0057

- `maintenance_service_declaration` : l'atelier déclare, pour un engin et un code de plan, le dernier entretien
  connu (date et cumuls km / heures relevés ce jour-là) ou qu'il est inconnu. Une **autre personne** l'approuve
  ou le rejette (contrainte en base). Une seule déclaration en attente par engin et code de plan.
- `maintenance_due.trigger_kind` accepte `INITIAL` : un dernier entretien inconnu et approuvé donne une échéance
  immédiate « entretien initial » (date d'approbation), qui établira le premier jalon.
Voir docs/PREVENTIVE_DUES.md.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_service_declaration (
  service_declaration_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  plan_code text NOT NULL,
  knowledge text NOT NULL,
  serviced_at timestamptz,
  odometer_km numeric(12,1),
  hour_meter numeric(12,1),
  note text,
  status text NOT NULL DEFAULT 'PENDING',
  declared_by uuid NOT NULL,
  declared_at timestamptz NOT NULL DEFAULT now(),
  decided_by uuid,
  decided_at timestamptz,
  decision_note text,
  CONSTRAINT pk_maintenance_service_declaration PRIMARY KEY (service_declaration_id),
  CONSTRAINT uq_msd_tenant_id UNIQUE (tenant_id, service_declaration_id),
  CONSTRAINT fk_msd__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msd__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msd__declared_by FOREIGN KEY (tenant_id, declared_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_msd__decided_by FOREIGN KEY (tenant_id, decided_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_msd_plan_code CHECK (char_length(btrim(plan_code)) BETWEEN 1 AND 80),
  CONSTRAINT ck_msd_knowledge CHECK (knowledge IN ('KNOWN','UNKNOWN')),
  CONSTRAINT ck_msd_detail CHECK (
    (knowledge = 'KNOWN' AND serviced_at IS NOT NULL AND serviced_at <= declared_at)
    OR (knowledge = 'UNKNOWN' AND serviced_at IS NULL AND odometer_km IS NULL AND hour_meter IS NULL)
  ),
  CONSTRAINT ck_msd_meters CHECK ((odometer_km IS NULL OR odometer_km >= 0) AND (hour_meter IS NULL OR hour_meter >= 0)),
  CONSTRAINT ck_msd_note CHECK (note IS NULL OR char_length(note) <= 500),
  CONSTRAINT ck_msd_status CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  CONSTRAINT ck_msd_decision CHECK (
    (status = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL AND decision_note IS NULL)
    OR (status IN ('APPROVED','REJECTED') AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
  ),
  CONSTRAINT ck_msd_rejection_note CHECK (status <> 'REJECTED' OR nullif(btrim(decision_note), '') IS NOT NULL),
  CONSTRAINT ck_msd_decision_note CHECK (decision_note IS NULL OR char_length(decision_note) <= 500),
  CONSTRAINT ck_msd_four_eyes CHECK (decided_by IS NULL OR decided_by <> declared_by)
);
CREATE UNIQUE INDEX uq_msd_one_pending
  ON maintenance_service_declaration (tenant_id, vehicle_id, plan_code) WHERE status = 'PENDING';
CREATE INDEX ix_msd_vehicle ON maintenance_service_declaration (tenant_id, vehicle_id, plan_code, status, decided_at DESC);
SELECT app.apply_tenant_rls('maintenance_service_declaration', 'SELECT, INSERT, UPDATE');

ALTER TABLE maintenance_due DROP CONSTRAINT ck_md_trigger;
ALTER TABLE maintenance_due ADD CONSTRAINT ck_md_trigger CHECK (trigger_kind IN ('KM','HOURS','DAYS','INITIAL'));
ALTER TABLE maintenance_due DROP CONSTRAINT ck_md_due_detail;
ALTER TABLE maintenance_due ADD CONSTRAINT ck_md_due_detail CHECK (
  (trigger_kind IN ('DAYS','INITIAL') AND due_on IS NOT NULL AND due_meter IS NULL)
  OR
  (trigger_kind IN ('KM','HOURS') AND due_meter IS NOT NULL AND due_meter >= 0 AND due_on IS NULL)
);
"""

DOWNGRADE = r"""
-- Retour arrière destructif (garde guard_destructive) : les échéances « entretien initial » disparaissent.
-- RLS forcée levée le temps de la suppression multi-tenant, puis rétablie.
ALTER TABLE maintenance_due NO FORCE ROW LEVEL SECURITY;
DELETE FROM maintenance_due WHERE trigger_kind = 'INITIAL';
ALTER TABLE maintenance_due FORCE ROW LEVEL SECURITY;
ALTER TABLE maintenance_due DROP CONSTRAINT ck_md_due_detail;
ALTER TABLE maintenance_due ADD CONSTRAINT ck_md_due_detail CHECK (
  (trigger_kind = 'DAYS' AND due_on IS NOT NULL AND due_meter IS NULL)
  OR
  (trigger_kind IN ('KM','HOURS') AND due_meter IS NOT NULL AND due_meter >= 0 AND due_on IS NULL)
);
ALTER TABLE maintenance_due DROP CONSTRAINT ck_md_trigger;
ALTER TABLE maintenance_due ADD CONSTRAINT ck_md_trigger CHECK (trigger_kind IN ('KM','HOURS','DAYS'));
DROP TABLE maintenance_service_declaration;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
