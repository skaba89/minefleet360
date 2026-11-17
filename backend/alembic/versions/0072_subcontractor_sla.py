"""Objectif de disponibilité (SLA) d'un sous-traitant (lot 1, tranche 3).

Additive : colonne nullable sur `subcontractor`, bornée à [0, 100] avec deux décimales. Valeur contractuelle
saisie par le donneur d'ordre ; la mesure reste calculée (aucune valeur déclarée par le sous-traitant).
"""

from app.core.migration_tools import run_sql

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE subcontractor
  ADD COLUMN availability_target_percent numeric(5,2),
  ADD CONSTRAINT ck_subcontractor_availability_target
    CHECK (availability_target_percent IS NULL OR availability_target_percent BETWEEN 0 AND 100);
"""

DOWNGRADE = r"""
ALTER TABLE subcontractor
  DROP CONSTRAINT ck_subcontractor_availability_target,
  DROP COLUMN availability_target_percent;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
