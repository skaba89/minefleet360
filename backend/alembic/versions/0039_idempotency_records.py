"""Socle d'idempotence des commandes synchronisées hors ligne.

Revision ID: 0039
Revises: 0038
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE idempotency_record (
  tenant_id uuid NOT NULL,
  user_account_id uuid NOT NULL,
  idempotency_key text NOT NULL,
  request_method text NOT NULL,
  request_path text NOT NULL,
  request_hash bytea NOT NULL,
  state text NOT NULL DEFAULT 'IN_PROGRESS',
  response_status smallint,
  resource_type text,
  resource_id uuid,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  expires_at timestamptz NOT NULL,
  CONSTRAINT pk_idempotency_record PRIMARY KEY (tenant_id, user_account_id, idempotency_key),
  CONSTRAINT fk_idempotency_record__user_account
    FOREIGN KEY (tenant_id, user_account_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_idempotency_record_key CHECK (
    idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
  ),
  CONSTRAINT ck_idempotency_record_method CHECK (request_method IN ('POST', 'PUT', 'PATCH')),
  CONSTRAINT ck_idempotency_record_path CHECK (
    char_length(request_path) BETWEEN 1 AND 300 AND left(request_path, 1) = '/'
  ),
  CONSTRAINT ck_idempotency_record_hash CHECK (octet_length(request_hash) = 32),
  CONSTRAINT ck_idempotency_record_state CHECK (state IN ('IN_PROGRESS', 'COMPLETED')),
  CONSTRAINT ck_idempotency_record_expiry CHECK (expires_at > created_at),
  CONSTRAINT ck_idempotency_record_completion CHECK (
    (state = 'IN_PROGRESS' AND response_status IS NULL AND resource_type IS NULL
      AND resource_id IS NULL AND completed_at IS NULL)
    OR
    (state = 'COMPLETED' AND response_status BETWEEN 200 AND 299
      AND resource_type ~ '^[a-z][a-z0-9_]{0,63}$'
      AND resource_id IS NOT NULL AND completed_at IS NOT NULL)
  )
);
CREATE INDEX ix_idempotency_record_expiry
  ON idempotency_record (tenant_id, expires_at);

ALTER TABLE idempotency_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_record FORCE ROW LEVEL SECURITY;
CREATE POLICY idempotency_record_select ON idempotency_record FOR SELECT TO mf_app
  USING (tenant_id = app.current_tenant_id());
CREATE POLICY idempotency_record_insert ON idempotency_record FOR INSERT TO mf_app
  WITH CHECK (tenant_id = app.current_tenant_id());
CREATE POLICY idempotency_record_update ON idempotency_record FOR UPDATE TO mf_app
  USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());
CREATE POLICY idempotency_record_delete_expired ON idempotency_record FOR DELETE TO mf_app
  USING (tenant_id = app.current_tenant_id() AND expires_at <= now());
REVOKE ALL ON idempotency_record FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON idempotency_record TO mf_app;

CREATE FUNCTION app.tg_idempotency_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state = 'COMPLETED' THEN
    RAISE EXCEPTION 'completed idempotency record is immutable' USING ERRCODE = 'MF001';
  END IF;
  IF (NEW.tenant_id, NEW.user_account_id, NEW.idempotency_key, NEW.request_method,
      NEW.request_path, NEW.request_hash, NEW.created_at, NEW.expires_at)
     IS DISTINCT FROM
     (OLD.tenant_id, OLD.user_account_id, OLD.idempotency_key, OLD.request_method,
      OLD.request_path, OLD.request_hash, OLD.created_at, OLD.expires_at) THEN
    RAISE EXCEPTION 'idempotency identity is immutable' USING ERRCODE = 'MF002';
  END IF;
  IF NEW.state <> 'COMPLETED' THEN
    RAISE EXCEPTION 'invalid idempotency transition' USING ERRCODE = 'MF003';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_idempotency_transition
  BEFORE UPDATE ON idempotency_record
  FOR EACH ROW EXECUTE FUNCTION app.tg_idempotency_transition();
"""

DOWNGRADE = r"""
DROP TABLE idempotency_record;
DROP FUNCTION app.tg_idempotency_transition();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
