"""Colonnes financières facultatives pour la valorisation future des pièces.

Revision ID: 0040
Revises: 0039

Les stocks historiques restent explicitement NON VALORISÉS (NULL), jamais à zéro.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE spare_part_balance
  ADD COLUMN stock_value numeric(20,6),
  ADD COLUMN valuation_currency varchar(3),
  ADD CONSTRAINT ck_part_balance_valuation_pair CHECK (
    (stock_value IS NULL AND valuation_currency IS NULL)
    OR (stock_value IS NOT NULL AND valuation_currency IS NOT NULL
        AND stock_value >= 0 AND valuation_currency ~ '^[A-Z]{3}$')
  );

ALTER TABLE spare_part_movement
  ADD COLUMN unit_cost numeric(20,6),
  ADD COLUMN total_cost numeric(20,6),
  ADD COLUMN valuation_currency varchar(3),
  ADD CONSTRAINT ck_part_movement_valuation_all_or_none CHECK (
    (unit_cost IS NULL AND total_cost IS NULL AND valuation_currency IS NULL)
    OR (unit_cost IS NOT NULL AND total_cost IS NOT NULL
        AND valuation_currency IS NOT NULL
        AND unit_cost >= 0 AND total_cost >= 0
        AND valuation_currency ~ '^[A-Z]{3}$')
  );

COMMENT ON COLUMN spare_part_balance.stock_value IS
  'NULL means historical stock value is unknown; never interpret as zero.';
COMMENT ON COLUMN spare_part_movement.total_cost IS
  'Immutable historical movement valuation, NULL until authoritative cost available.';
"""

DOWNGRADE = r"""
ALTER TABLE spare_part_movement
  DROP CONSTRAINT ck_part_movement_valuation_all_or_none,
  DROP COLUMN valuation_currency,
  DROP COLUMN total_cost,
  DROP COLUMN unit_cost;
ALTER TABLE spare_part_balance
  DROP CONSTRAINT ck_part_balance_valuation_pair,
  DROP COLUMN valuation_currency,
  DROP COLUMN stock_value;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
