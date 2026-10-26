"""Affectations conducteur ↔ véhicule (MODELE_PHYSIQUE_LOT1 §5.7, tranche 1c).

Revision ID: 0008
Revises: 0007

Numérotée 0008 : le numéro 0007 prévu par le modèle physique a été pris par la réparation du catalogue.
La base garantit l'isolation (RLS, FK composites), le non-chevauchement (EXCLUDE gist), l'immuabilité
des affectations terminées et la cohérence de site ; l'éligibilité reste applicative (RM-030).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE vehicle_assignment (
  vehicle_assignment_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  site_id    uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  driver_id  uuid NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_to   timestamptz,
  valid_during tstzrange GENERATED ALWAYS AS (tstzrange(valid_from, valid_to, '[)')) STORED,
  shift_code    text,
  status        text NOT NULL DEFAULT 'PLANNED',
  status_reason text,
  eligibility_snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_vehicle_assignment PRIMARY KEY (vehicle_assignment_id),
  CONSTRAINT fk_va__tenant  FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_va__site    FOREIGN KEY (tenant_id, site_id)    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_va__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_va__driver  FOREIGN KEY (tenant_id, driver_id)  REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT uq_va_tenant_id UNIQUE (tenant_id, vehicle_assignment_id),
  CONSTRAINT ck_va_interval  CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT ck_va_status    CHECK (status IN ('PLANNED','ACTIVE','SUSPENDED','COMPLETED','CANCELLED')),
  CONSTRAINT ck_va_reason    CHECK (status NOT IN ('SUSPENDED','COMPLETED','CANCELLED') OR status_reason IS NOT NULL),
  CONSTRAINT ck_va_completed CHECK (status <> 'COMPLETED' OR valid_to IS NOT NULL),
  CONSTRAINT ck_va_shift     CHECK (shift_code IS NULL OR shift_code ~ '^[A-Z0-9_-]{1,20}$'),
  CONSTRAINT ck_va_snapshot  CHECK (jsonb_typeof(eligibility_snapshot) = 'object'),
  CONSTRAINT ck_va_version   CHECK (row_version >= 1),
  CONSTRAINT ex_va_vehicle_no_overlap EXCLUDE USING gist (vehicle_id WITH =, valid_during WITH &&) WHERE (status <> 'CANCELLED'),
  CONSTRAINT ex_va_driver_no_overlap  EXCLUDE USING gist (driver_id  WITH =, valid_during WITH &&) WHERE (status <> 'CANCELLED')
);
CREATE INDEX ix_va_vehicle_hist ON vehicle_assignment (tenant_id, vehicle_id, valid_from DESC);
CREATE INDEX ix_va_driver_hist  ON vehicle_assignment (tenant_id, driver_id,  valid_from DESC);
CREATE INDEX ix_va_site_status  ON vehicle_assignment (tenant_id, site_id, status);
CREATE INDEX ix_va_open         ON vehicle_assignment (tenant_id, status, valid_from) WHERE status IN ('PLANNED','ACTIVE','SUSPENDED');
SELECT app.apply_tenant_rls('vehicle_assignment', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('vehicle_assignment');

CREATE FUNCTION app.tg_va_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_vehicle_site uuid; v_driver_site uuid;
BEGIN
  IF TG_OP = 'INSERT' THEN
    -- Même site strict (D-13, RM-042) : affectation = site du véhicule = site du conducteur.
    SELECT site_id INTO v_vehicle_site FROM vehicle WHERE tenant_id = NEW.tenant_id AND vehicle_id = NEW.vehicle_id;
    SELECT site_id INTO v_driver_site  FROM driver  WHERE tenant_id = NEW.tenant_id AND driver_id  = NEW.driver_id;
    IF v_vehicle_site IS DISTINCT FROM NEW.site_id OR v_driver_site IS DISTINCT FROM NEW.site_id THEN
      RAISE EXCEPTION 'assignment, vehicle and driver must share the same site' USING ERRCODE = 'MF004';
    END IF;
  ELSE
    IF OLD.status IN ('COMPLETED','CANCELLED') THEN                                  -- RM-040
      RAISE EXCEPTION 'terminal assignment is immutable' USING ERRCODE = 'MF003';
    END IF;
    IF (NEW.vehicle_id, NEW.driver_id, NEW.site_id) IS DISTINCT FROM (OLD.vehicle_id, OLD.driver_id, OLD.site_id) THEN
      RAISE EXCEPTION 'assignment vehicle, driver and site are immutable' USING ERRCODE = 'MF003';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_va_guard BEFORE INSERT OR UPDATE ON vehicle_assignment
  FOR EACH ROW EXECUTE FUNCTION app.tg_va_guard();

-- Changement de site d'un véhicule ou d'un conducteur refusé tant qu'une affectation ouverte existe
-- (D-13, RM-051). SUSPENDED compte : le créneau reste occupé (D-30).
CREATE FUNCTION app.tg_site_change_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.site_id IS DISTINCT FROM OLD.site_id AND EXISTS (
       SELECT 1 FROM vehicle_assignment va
        WHERE va.tenant_id = OLD.tenant_id
          AND ((TG_TABLE_NAME = 'vehicle' AND va.vehicle_id = OLD.vehicle_id)
            OR (TG_TABLE_NAME = 'driver'  AND va.driver_id  = OLD.driver_id))
          AND va.status IN ('PLANNED','ACTIVE','SUSPENDED')) THEN
    RAISE EXCEPTION 'site change refused: open assignment exists' USING ERRCODE = 'MF004';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_vehicle_site_change_guard BEFORE UPDATE OF site_id ON vehicle
  FOR EACH ROW EXECUTE FUNCTION app.tg_site_change_guard();
CREATE TRIGGER tg_driver_site_change_guard BEFORE UPDATE OF site_id ON driver
  FOR EACH ROW EXECUTE FUNCTION app.tg_site_change_guard();
"""

DOWNGRADE = r"""
DROP TRIGGER tg_driver_site_change_guard ON driver;
DROP TRIGGER tg_vehicle_site_change_guard ON vehicle;
DROP FUNCTION app.tg_site_change_guard();
DROP TABLE vehicle_assignment;
DROP FUNCTION app.tg_va_guard();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
