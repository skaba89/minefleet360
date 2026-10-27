"""Dispatch (lot 2a) : lieux, matières, missions, événements immuables, rotations dérivées.

Revision ID: 0012
Revises: 0011

Voir docs/PLAN_LOT2.md. Aucune colonne de tonnage ni de position GPS (RM-070, RM-072) : les pesées
arrivent en 2b. La base garantit l'isolation (RLS, FK composites), l'immuabilité des événements, l'unicité
des renvois (`client_event_id`) et une seule mission en cours par véhicule et par conducteur (RM-081).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE site_location (
  site_location_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id   uuid NOT NULL,
  code      text NOT NULL,
  name      text NOT NULL,
  kind      text NOT NULL,
  status    text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_site_location PRIMARY KEY (site_location_id),
  CONSTRAINT fk_sl__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT uq_sl_tenant_id UNIQUE (tenant_id, site_location_id),
  CONSTRAINT uq_sl_site_code UNIQUE (tenant_id, site_id, code),
  CONSTRAINT uq_sl_site_id   UNIQUE (tenant_id, site_id, site_location_id),  -- cible des FK « même site »
  CONSTRAINT ck_sl_code   CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_sl_kind   CHECK (kind IN ('LOADING_POINT','DUMP_POINT','STOCKPILE','CRUSHER','WEIGHBRIDGE','PORT','OTHER')),
  CONSTRAINT ck_sl_status CHECK (status IN ('ACTIVE','INACTIVE')),
  CONSTRAINT ck_sl_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('site_location', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('site_location');

CREATE TABLE material (
  material_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code      text NOT NULL,
  name      text NOT NULL,
  is_waste  boolean NOT NULL DEFAULT false,
  status    text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_material PRIMARY KEY (material_id),
  CONSTRAINT fk_material__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_material_tenant_id UNIQUE (tenant_id, material_id),
  CONSTRAINT uq_material_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_material_code   CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_material_status CHECK (status IN ('ACTIVE','INACTIVE')),
  CONSTRAINT ck_material_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('material', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('material');

CREATE TABLE mission (
  mission_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  site_id    uuid NOT NULL,
  vehicle_assignment_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  driver_id  uuid NOT NULL,
  origin_location_id      uuid NOT NULL,
  destination_location_id uuid NOT NULL,
  material_id uuid NOT NULL,
  planned_start timestamptz NOT NULL,
  due_at        timestamptz,
  planned_rotations integer,
  status        text NOT NULL DEFAULT 'ASSIGNED',
  status_before_suspension text,
  status_reason text,
  notes         text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_mission PRIMARY KEY (mission_id),
  CONSTRAINT fk_mission__site        FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mission__assignment  FOREIGN KEY (tenant_id, vehicle_assignment_id) REFERENCES vehicle_assignment (tenant_id, vehicle_assignment_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mission__vehicle     FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mission__driver      FOREIGN KEY (tenant_id, driver_id) REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  -- Lieux du MÊME site que la mission (RM-082), garanti par la base.
  CONSTRAINT fk_mission__origin      FOREIGN KEY (tenant_id, site_id, origin_location_id) REFERENCES site_location (tenant_id, site_id, site_location_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mission__destination FOREIGN KEY (tenant_id, site_id, destination_location_id) REFERENCES site_location (tenant_id, site_id, site_location_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mission__material    FOREIGN KEY (tenant_id, material_id) REFERENCES material (tenant_id, material_id) ON DELETE RESTRICT,
  CONSTRAINT uq_mission_tenant_id UNIQUE (tenant_id, mission_id),
  CONSTRAINT ck_mission_places   CHECK (origin_location_id <> destination_location_id),
  CONSTRAINT ck_mission_due      CHECK (due_at IS NULL OR due_at > planned_start),
  CONSTRAINT ck_mission_rotations CHECK (planned_rotations IS NULL OR planned_rotations BETWEEN 1 AND 500),
  CONSTRAINT ck_mission_status   CHECK (status IN ('PLANNED','ASSIGNED','EN_ROUTE_EMPTY','LOADING','EN_ROUTE_LOADED',
                                                    'UNLOADING','SUSPENDED','COMPLETED','CANCELLED')),
  CONSTRAINT ck_mission_reason   CHECK (status NOT IN ('SUSPENDED','CANCELLED') OR status_reason IS NOT NULL),
  CONSTRAINT ck_mission_suspended CHECK ((status = 'SUSPENDED') = (status_before_suspension IS NOT NULL)),
  CONSTRAINT ck_mission_notes    CHECK (notes IS NULL OR length(notes) <= 1000),
  CONSTRAINT ck_mission_version  CHECK (row_version >= 1)
);
-- RM-081 : une seule mission EN COURS (en route, chargement, déchargement) par véhicule et par conducteur.
CREATE UNIQUE INDEX uq_mission_vehicle_running ON mission (tenant_id, vehicle_id)
  WHERE status IN ('EN_ROUTE_EMPTY','LOADING','EN_ROUTE_LOADED','UNLOADING');
CREATE UNIQUE INDEX uq_mission_driver_running ON mission (tenant_id, driver_id)
  WHERE status IN ('EN_ROUTE_EMPTY','LOADING','EN_ROUTE_LOADED','UNLOADING');
CREATE INDEX ix_mission_site_status ON mission (tenant_id, site_id, status, planned_start DESC);
CREATE INDEX ix_mission_vehicle ON mission (tenant_id, vehicle_id, planned_start DESC);
SELECT app.apply_tenant_rls('mission', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('mission');

-- Événements d'avancement : AJOUT SEUL (correction = événement correctif, jamais de modification).
CREATE TABLE mission_event (
  mission_event_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  mission_id uuid NOT NULL,
  event_type text NOT NULL,
  from_status text,
  to_status   text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  source      text NOT NULL DEFAULT 'DISPATCHER',
  client_event_id uuid,
  actor_user_id uuid,
  reason      text,
  CONSTRAINT pk_mission_event PRIMARY KEY (mission_event_id),
  CONSTRAINT fk_me__mission FOREIGN KEY (tenant_id, mission_id) REFERENCES mission (tenant_id, mission_id) ON DELETE RESTRICT,
  CONSTRAINT uq_me_client_event UNIQUE (tenant_id, client_event_id),
  CONSTRAINT ck_me_type   CHECK (event_type IN ('CREATED','DEPARTED','ARRIVED_LOADING','LOADED','ARRIVED_UNLOADING',
                                                'UNLOADED','COMPLETED','SUSPENDED','RESUMED','REASSIGNED','CANCELLED')),
  CONSTRAINT ck_me_source CHECK (source IN ('DISPATCHER','MOBILE','GEOFENCE','SYSTEM'))
);
CREATE INDEX ix_me_mission ON mission_event (tenant_id, mission_id, occurred_at, recorded_at);
SELECT app.apply_tenant_rls('mission_event', 'SELECT, INSERT');
CREATE TRIGGER tg_mission_event_append_only BEFORE UPDATE OR DELETE ON mission_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

-- Rotation : cycle chargement → déchargement, DÉRIVÉ des événements (jamais saisi, aucun tonnage en 2a).
CREATE TABLE rotation (
  rotation_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  mission_id uuid NOT NULL,
  sequence   integer NOT NULL,
  vehicle_id uuid NOT NULL,
  driver_id  uuid NOT NULL,
  loading_started_at   timestamptz NOT NULL,
  loaded_at            timestamptz,
  unloading_started_at timestamptz,
  unloaded_at          timestamptz,
  status     text NOT NULL DEFAULT 'OPEN',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_rotation PRIMARY KEY (rotation_id),
  CONSTRAINT fk_rotation__mission FOREIGN KEY (tenant_id, mission_id) REFERENCES mission (tenant_id, mission_id) ON DELETE RESTRICT,
  CONSTRAINT uq_rotation_sequence UNIQUE (tenant_id, mission_id, sequence),
  CONSTRAINT ck_rotation_status CHECK (status IN ('OPEN','COMPLETED','ABORTED')),
  CONSTRAINT ck_rotation_order  CHECK (
    (loaded_at IS NULL OR loaded_at >= loading_started_at)
    AND (unloading_started_at IS NULL OR (loaded_at IS NOT NULL AND unloading_started_at >= loaded_at))
    AND (unloaded_at IS NULL OR (unloading_started_at IS NOT NULL AND unloaded_at >= unloading_started_at))),
  CONSTRAINT ck_rotation_completed CHECK (status <> 'COMPLETED' OR unloaded_at IS NOT NULL),
  CONSTRAINT ck_rotation_sequence CHECK (sequence >= 1),
  CONSTRAINT ck_rotation_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_rotation_open ON rotation (tenant_id, mission_id) WHERE status = 'OPEN';
SELECT app.apply_tenant_rls('rotation', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('rotation');
"""

DOWNGRADE = r"""
DROP TABLE rotation;
DROP TABLE mission_event;
DROP TABLE mission;
DROP TABLE material;
DROP TABLE site_location;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
