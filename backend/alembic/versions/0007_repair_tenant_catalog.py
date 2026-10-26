"""Répare le catalogue véhicule des tenants créés avant la migration 0005.

Revision ID: 0007
Revises: 0006

La migration 0005 lisait ``tenant`` sous ``mf_owner`` alors que cette table avait déjà FORCE RLS
et aucune policy pour le propriétaire. Elle pouvait donc réussir sans copier le catalogue. Cette
migration accorde une visibilité temporaire strictement limitée au rôle de migration, complète les
lignes manquantes, puis retire les policies dans la même transaction.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE = r"""
SET LOCAL row_security = on;

DO $$
BEGIN
  IF current_user <> 'mf_owner' THEN
    RAISE EXCEPTION 'migration 0007 requires role mf_owner';
  END IF;
END $$;

DROP POLICY IF EXISTS migration_0007_owner_select ON tenant;
DROP POLICY IF EXISTS migration_0007_owner_select ON vehicle_category;
DROP POLICY IF EXISTS migration_0007_owner_insert ON vehicle_category;
DROP POLICY IF EXISTS migration_0007_owner_select ON vehicle_category_license_category;
DROP POLICY IF EXISTS migration_0007_owner_insert ON vehicle_category_license_category;

CREATE POLICY migration_0007_owner_select ON tenant
  FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0007_owner_select ON vehicle_category
  FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0007_owner_insert ON vehicle_category
  FOR INSERT TO mf_owner WITH CHECK (true);
CREATE POLICY migration_0007_owner_select ON vehicle_category_license_category
  FOR SELECT TO mf_owner USING (true);
CREATE POLICY migration_0007_owner_insert ON vehicle_category_license_category
  FOR INSERT TO mf_owner WITH CHECK (true);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM tenant t
    JOIN vehicle_category vc ON vc.tenant_id = t.tenant_id
    JOIN vehicle_category_template template ON template.code = vc.code
    WHERE t.kind = 'CUSTOMER' AND NOT vc.is_system
  ) THEN
    RAISE EXCEPTION 'migration 0007: custom category conflicts with system catalog';
  END IF;
END $$;

INSERT INTO vehicle_category (
  tenant_id, code, label_fr, family, requires_driver, requires_internal_authorization,
  has_odometer, has_hour_meter, is_system
)
SELECT
  t.tenant_id, template.code, template.label_fr, template.family, template.requires_driver,
  template.requires_internal_authorization, template.has_odometer, template.has_hour_meter, true
FROM tenant t
CROSS JOIN vehicle_category_template template
WHERE t.kind = 'CUSTOMER'
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO vehicle_category_license_category (
  tenant_id, vehicle_category_id, license_category_code
)
SELECT vc.tenant_id, vc.vehicle_category_id, required.license_category_code
FROM vehicle_category vc
JOIN tenant t ON t.tenant_id = vc.tenant_id AND t.kind = 'CUSTOMER'
JOIN vehicle_category_template_license required ON required.category_code = vc.code
WHERE vc.is_system
ON CONFLICT (tenant_id, vehicle_category_id, license_category_code) DO NOTHING;

DROP POLICY migration_0007_owner_insert ON vehicle_category_license_category;
DROP POLICY migration_0007_owner_select ON vehicle_category_license_category;
DROP POLICY migration_0007_owner_insert ON vehicle_category;
DROP POLICY migration_0007_owner_select ON vehicle_category;
DROP POLICY migration_0007_owner_select ON tenant;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    # Réparation additive : conserver les catégories devenues des données métier. Revenir à 0006
    # retire seulement le marqueur Alembic; une suppression automatique serait destructive.
    guard_destructive()
