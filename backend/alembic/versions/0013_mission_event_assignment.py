"""Événements de mission : affectation en vigueur après chaque événement (revue L2A-R-01).

Revision ID: 0013
Revises: 0012

Une réaffectation remplace le véhicule et le conducteur d'une mission ; la chronologie immuable doit dire
qui roulait à chaque étape. Les événements existants reçoivent l'affectation actuelle de leur mission
(exacte tant qu'aucune réaffectation n'a eu lieu, ce qui est le cas de toute base antérieure au correctif).
Comme en 0007, une visibilité temporaire limitée au rôle de migration permet ce complément sous FORCE RLS ;
le trigger d'ajout seul n'est suspendu que le temps de cette mise à jour, dans la même transaction.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UPGRADE = r"""
SET LOCAL row_security = on;

DO $$
BEGIN
  IF current_user <> 'mf_owner' THEN
    RAISE EXCEPTION 'migration 0013 requires role mf_owner';
  END IF;
END $$;

ALTER TABLE mission_event ADD COLUMN vehicle_assignment_id uuid;

CREATE POLICY migration_0013_owner_select ON mission FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0013_owner_select ON mission_event FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0013_owner_update ON mission_event FOR UPDATE TO mf_owner USING (true) WITH CHECK (true);
ALTER TABLE mission_event DISABLE TRIGGER tg_mission_event_append_only;

UPDATE mission_event e
   SET vehicle_assignment_id = m.vehicle_assignment_id
  FROM mission m
 WHERE m.tenant_id = e.tenant_id AND m.mission_id = e.mission_id;

ALTER TABLE mission_event ENABLE TRIGGER tg_mission_event_append_only;
DROP POLICY migration_0013_owner_update ON mission_event;
DROP POLICY migration_0013_owner_select ON mission_event;
DROP POLICY migration_0013_owner_select ON mission;

ALTER TABLE mission_event ALTER COLUMN vehicle_assignment_id SET NOT NULL;
ALTER TABLE mission_event ADD CONSTRAINT fk_me__assignment FOREIGN KEY (tenant_id, vehicle_assignment_id)
  REFERENCES vehicle_assignment (tenant_id, vehicle_assignment_id) ON DELETE RESTRICT;
"""

DOWNGRADE = r"""
ALTER TABLE mission_event DROP CONSTRAINT fk_me__assignment;
ALTER TABLE mission_event DROP COLUMN vehicle_assignment_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
