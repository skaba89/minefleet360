"""Compteurs d'authentification globaux non personnels, accessibles par fonctions bornées.

Revision ID: 0008
Revises: 0007
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE app.auth_failure_bucket (
  namespace text NOT NULL CHECK (namespace IN ('login', 'source', 'tokens')),
  key_hash text NOT NULL CHECK (key_hash ~ '^[a-f0-9]{64}$'),
  failures timestamptz[] NOT NULL,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (namespace, key_hash),
  CHECK (cardinality(failures) BETWEEN 1 AND 1000)
);
CREATE INDEX ix_auth_failure_expiry ON app.auth_failure_bucket (namespace, expires_at);
REVOKE ALL ON app.auth_failure_bucket FROM PUBLIC, mf_app;

CREATE FUNCTION app.auth_limit(
  p_namespace text, p_key text, p_maximum integer, p_window integer, p_operation text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
DECLARE
  kept timestamptz[];
  bucket_count integer;
  current_instant timestamptz;
BEGIN
  IF p_namespace IS NULL OR p_namespace NOT IN ('login', 'source', 'tokens')
     OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$'
     OR p_maximum IS NULL OR p_maximum NOT BETWEEN 1 AND 1000
     OR p_window IS NULL OR p_window NOT BETWEEN 1 AND 86400
     OR p_operation IS NULL OR p_operation NOT IN ('check', 'record') THEN
    RAISE EXCEPTION 'invalid auth limiter parameters' USING ERRCODE = '22023';
  END IF;
  IF p_operation = 'record' THEN
    PERFORM pg_advisory_xact_lock(872360, hashtext(p_namespace));
  END IF;
  -- L'appelant ne choisit jamais l'horloge qui décide de la purge des compteurs partagés.
  current_instant := clock_timestamp();
  IF p_operation = 'record' THEN
    DELETE FROM app.auth_failure_bucket WHERE namespace = p_namespace AND expires_at <= current_instant;
  END IF;
  SELECT ARRAY(SELECT stamp FROM unnest(b.failures) stamp
               WHERE stamp > current_instant - make_interval(secs => p_window))
    INTO kept FROM app.auth_failure_bucket b
    WHERE namespace = p_namespace AND key_hash = p_key;
  IF kept IS NULL THEN
    SELECT count(*) INTO bucket_count FROM app.auth_failure_bucket
      WHERE namespace = p_namespace AND expires_at > current_instant;
    -- Refus conservateur des nouvelles clés au plafond, sans évincer les compteurs actifs.
    IF bucket_count >= 10000 THEN RETURN true; END IF;
    kept := ARRAY[]::timestamptz[];
  END IF;
  IF p_operation = 'record' THEN
    SELECT array_agg(stamp ORDER BY stamp DESC) INTO kept FROM (
      SELECT stamp FROM unnest(array_append(kept, current_instant)) stamp
      ORDER BY stamp DESC LIMIT p_maximum
    ) recent;
    INSERT INTO app.auth_failure_bucket(namespace, key_hash, failures, expires_at)
      VALUES (p_namespace, p_key, kept, kept[1] + make_interval(secs => p_window))
    ON CONFLICT (namespace, key_hash) DO UPDATE
      SET failures = EXCLUDED.failures, expires_at = EXCLUDED.expires_at;
  END IF;
  RETURN cardinality(kept) >= p_maximum;
END $$;
REVOKE ALL ON FUNCTION app.auth_limit(text, text, integer, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.auth_limit(text, text, integer, integer, text) TO mf_app;

CREATE FUNCTION app.auth_limit_reset(p_namespace text, p_key text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
BEGIN
  IF p_namespace IS NULL OR p_namespace NOT IN ('login', 'source', 'tokens')
     OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'invalid auth limiter parameters' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(872360, hashtext(p_namespace));
  DELETE FROM app.auth_failure_bucket WHERE namespace = p_namespace AND key_hash = p_key;
END $$;
REVOKE ALL ON FUNCTION app.auth_limit_reset(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.auth_limit_reset(text, text) TO mf_app;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(
        "DROP FUNCTION app.auth_limit_reset(text, text);"
        "DROP FUNCTION app.auth_limit(text, text, integer, integer, text);"
        "DROP TABLE app.auth_failure_bucket;"
    )
