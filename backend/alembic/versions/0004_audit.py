"""Journal d'audit append-only partitionné par mois (MODELE_PHYSIQUE_LOT1 §5.4, ADR-005, D-17).

Revision ID: 0004
Revises: 0003
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE SEQUENCE audit_event_seq;

CREATE TABLE audit_event (
  audit_event_id     uuid NOT NULL DEFAULT gen_random_uuid(),
  audit_seq          bigint NOT NULL DEFAULT nextval('audit_event_seq'),
  tenant_id          uuid NOT NULL,
  site_id            uuid,
  occurred_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  actor_user_id      uuid,
  actor_kind         text NOT NULL,
  support_session_id uuid,
  action             text NOT NULL,
  entity_type        text NOT NULL,
  entity_id          uuid,
  outcome            text NOT NULL,
  reason             text,
  changed_fields     text[],
  before_data        jsonb,
  after_data         jsonb,
  request_id         uuid,
  ip_address         inet,
  user_agent         text,
  prev_hash          bytea,
  row_hash           bytea,
  CONSTRAINT pk_audit_event PRIMARY KEY (audit_event_id, occurred_at),
  CONSTRAINT fk_audit_event__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_audit_event__actor  FOREIGN KEY (actor_user_id) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_audit_actor_kind CHECK (actor_kind IN ('USER','SYSTEM','PLATFORM_SUPPORT','DEVICE_SYNC','ANONYMOUS')),
  CONSTRAINT ck_audit_actor_ref  CHECK (actor_kind NOT IN ('USER','PLATFORM_SUPPORT') OR actor_user_id IS NOT NULL),
  CONSTRAINT ck_audit_support    CHECK ((actor_kind = 'PLATFORM_SUPPORT') = (support_session_id IS NOT NULL)),
  CONSTRAINT ck_audit_outcome    CHECK (outcome IN ('SUCCESS','DENIED','FAILURE')),
  CONSTRAINT ck_audit_action     CHECK (action ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')
) PARTITION BY RANGE (occurred_at);

CREATE TABLE audit_event_default PARTITION OF audit_event DEFAULT;

CREATE INDEX ix_audit_event_tenant_time   ON audit_event (tenant_id, occurred_at DESC);
CREATE INDEX ix_audit_event_tenant_entity ON audit_event (tenant_id, entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_audit_event_tenant_actor  ON audit_event (tenant_id, actor_user_id, occurred_at DESC) WHERE actor_user_id IS NOT NULL;
CREATE INDEX ix_audit_event_tenant_site   ON audit_event (tenant_id, site_id, occurred_at DESC) WHERE site_id IS NOT NULL;
CREATE INDEX ix_audit_event_tenant_id     ON audit_event (tenant_id, audit_event_id);
CREATE INDEX ix_audit_event_request       ON audit_event (tenant_id, request_id) WHERE request_id IS NOT NULL;

ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_select ON audit_event FOR SELECT TO mf_app USING (tenant_id = app.current_tenant_id());
CREATE POLICY audit_insert ON audit_event FOR INSERT TO mf_app WITH CHECK (tenant_id = app.current_tenant_id());
REVOKE ALL ON audit_event FROM PUBLIC;
GRANT SELECT, INSERT ON audit_event TO mf_app;
GRANT USAGE ON SEQUENCE audit_event_seq TO mf_app;
CREATE TRIGGER tg_audit_event_append_only BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
CREATE TRIGGER tg_audit_event_no_truncate BEFORE TRUNCATE ON audit_event
  FOR EACH STATEMENT EXECUTE FUNCTION app.tg_append_only();

CREATE FUNCTION app.ensure_audit_partitions(p_months_ahead integer DEFAULT 12) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE m date; part text; n integer := 0;
BEGIN
  FOR i IN 0..p_months_ahead LOOP
    m := (date_trunc('month', now() AT TIME ZONE 'UTC') + make_interval(months => i))::date;
    part := format('audit_event_y%sm%s', to_char(m, 'YYYY'), to_char(m, 'MM'));
    IF to_regclass(format('public.%I', part)) IS NULL THEN
      EXECUTE format('CREATE TABLE public.%I PARTITION OF public.audit_event FOR VALUES FROM (%L) TO (%L)',
                     part, (m::timestamp AT TIME ZONE 'UTC'), ((m + interval '1 month')::timestamp AT TIME ZONE 'UTC'));
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', part);
      EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', part);
      EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, mf_app', part);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION app.ensure_audit_partitions(integer) FROM PUBLIC;
ALTER TABLE audit_event_default ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event_default FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE audit_event_default FROM PUBLIC, mf_app;
SELECT app.ensure_audit_partitions(12);
"""

DOWNGRADE = r"""
DROP TABLE audit_event;
DROP FUNCTION app.ensure_audit_partitions(integer);
DROP SEQUENCE audit_event_seq;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
