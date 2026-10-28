"""Atelier : correctifs de la revue sécurité du lot 3a (L3A-R-08, revue automatique).

Revision ID: 0018
Revises: 0017

La PR #19 a été fusionnée avec la migration 0017 d'origine : celle-ci reste inchangée.
- `work_order_event.subject_user_id` : personne visée par l'événement (mécanicien assigné), pour
  reconstituer la chaîne des assignés et exclure chacun de la remise en service.
- `work_order.immobilized_vehicle` : l'OT a lui-même immobilisé le véhicule au signalement ; seul un tel
  OT peut lever cette immobilisation en cas de rejet ou d'annulation (aucune levée d'une immobilisation
  posée par quelqu'un d'autre).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE work_order_event ADD COLUMN subject_user_id uuid;
ALTER TABLE work_order_event ADD CONSTRAINT fk_woe__subject FOREIGN KEY (tenant_id, subject_user_id)
  REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT;
ALTER TABLE work_order ADD COLUMN immobilized_vehicle boolean NOT NULL DEFAULT false;
"""

DOWNGRADE = r"""
ALTER TABLE work_order DROP COLUMN immobilized_vehicle;
ALTER TABLE work_order_event DROP CONSTRAINT fk_woe__subject;
ALTER TABLE work_order_event DROP COLUMN subject_user_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
