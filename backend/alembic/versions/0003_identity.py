"""Identité : comptes, attributions de rôle, jetons, sessions (MODELE_PHYSIQUE_LOT1 §5.3).

Revision ID: 0003
Revises: 0002
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE user_account (
  user_account_id      uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL,
  email                citext NOT NULL,
  display_name         text NOT NULL,
  phone                text,
  password_hash        text,
  mfa_enabled          boolean NOT NULL DEFAULT false,
  mfa_secret_encrypted bytea,
  status               text NOT NULL DEFAULT 'INVITED',
  failed_login_count   integer NOT NULL DEFAULT 0,
  locked_until         timestamptz,
  last_login_at        timestamptz,
  must_change_password boolean NOT NULL DEFAULT true,
  ui_locale            text NOT NULL DEFAULT 'fr-GN',
  anonymized_at        timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_user_account PRIMARY KEY (user_account_id),
  CONSTRAINT fk_user_account__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_user_account_tenant_user  UNIQUE (tenant_id, user_account_id),
  CONSTRAINT uq_user_account_tenant_email UNIQUE (tenant_id, email),
  CONSTRAINT ck_user_account_status CHECK (status IN ('INVITED','ACTIVE','DISABLED')),
  CONSTRAINT ck_user_account_email  CHECK (position('@' in email::text) > 1),
  CONSTRAINT ck_user_account_phone  CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
  CONSTRAINT ck_user_account_failed CHECK (failed_login_count >= 0),
  CONSTRAINT ck_user_account_mfa    CHECK (NOT mfa_enabled OR mfa_secret_encrypted IS NOT NULL),
  CONSTRAINT ck_user_account_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('user_account', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('user_account');

CREATE TABLE user_role_assignment (
  user_role_assignment_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  tenant_kind     text NOT NULL,
  user_account_id uuid NOT NULL,
  role_code       text NOT NULL,
  scope_type      text NOT NULL,
  site_id         uuid,
  valid_from      timestamptz NOT NULL DEFAULT now(),
  valid_to        timestamptz,
  granted_by      uuid NOT NULL,
  revoked_at      timestamptz,
  revoked_by      uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_user_role_assignment PRIMARY KEY (user_role_assignment_id),
  CONSTRAINT fk_ura__tenant_kind FOREIGN KEY (tenant_id, tenant_kind) REFERENCES tenant (tenant_id, kind) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__user        FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__site        FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__role_scope  FOREIGN KEY (role_code, scope_type) REFERENCES role_allowed_scope (role_code, scope_type) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__granted_by  FOREIGN KEY (granted_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__revoked_by  FOREIGN KEY (revoked_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_ura_scope_site     CHECK ((scope_type = 'SITE') = (site_id IS NOT NULL)),
  CONSTRAINT ck_ura_scope_platform CHECK ((scope_type = 'PLATFORM') = (tenant_kind = 'PLATFORM')),
  CONSTRAINT ck_ura_validity       CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT ck_ura_revocation     CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)),
  CONSTRAINT ck_ura_version        CHECK (row_version >= 1),
  CONSTRAINT ex_ura_no_duplicate EXCLUDE USING gist (
      user_account_id WITH =, role_code WITH =, scope_type WITH =,
      (COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      tstzrange(valid_from, valid_to, '[)') WITH &&)
    WHERE (revoked_at IS NULL)
);
CREATE INDEX ix_ura_tenant_user ON user_role_assignment (tenant_id, user_account_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_ura_tenant_site ON user_role_assignment (tenant_id, site_id) WHERE site_id IS NOT NULL;
SELECT app.apply_tenant_rls('user_role_assignment', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('user_role_assignment');

CREATE TABLE account_token (
  account_token_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  user_account_id  uuid NOT NULL,
  purpose          text NOT NULL,
  token_hash       bytea NOT NULL,
  expires_at       timestamptz NOT NULL,
  consumed_at      timestamptz,
  revoked_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  CONSTRAINT pk_account_token PRIMARY KEY (account_token_id),
  CONSTRAINT fk_account_token__user FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_account_token_hash  UNIQUE (tenant_id, token_hash),
  CONSTRAINT ck_account_token_purpose CHECK (purpose IN ('INVITATION','PASSWORD_RESET')),
  CONSTRAINT ck_account_token_hash    CHECK (octet_length(token_hash) = 32),
  CONSTRAINT ck_account_token_expiry  CHECK (expires_at > created_at)
);
CREATE UNIQUE INDEX uq_account_token_open ON account_token (tenant_id, user_account_id, purpose)
  WHERE consumed_at IS NULL AND revoked_at IS NULL;
SELECT app.apply_tenant_rls('account_token', 'SELECT, INSERT, UPDATE, DELETE');

CREATE TABLE auth_session (
  auth_session_id       uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL,
  user_account_id       uuid NOT NULL,
  refresh_hash_current  bytea NOT NULL,
  refresh_hash_previous bytea,
  rotated_at            timestamptz,
  amr                   text[] NOT NULL DEFAULT '{pwd}',
  ip_address            inet,
  user_agent            text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  last_seen_at          timestamptz NOT NULL DEFAULT now(),
  expires_at            timestamptz NOT NULL,
  revoked_at            timestamptz,
  revoked_reason        text,
  CONSTRAINT pk_auth_session PRIMARY KEY (auth_session_id),
  CONSTRAINT fk_auth_session__user FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_auth_session_refresh UNIQUE (tenant_id, refresh_hash_current),
  CONSTRAINT ck_auth_session_hash CHECK (octet_length(refresh_hash_current) = 32),
  CONSTRAINT ck_auth_session_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_auth_session_user ON auth_session (tenant_id, user_account_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_auth_session_expiry ON auth_session (expires_at);
SELECT app.apply_tenant_rls('auth_session', 'SELECT, INSERT, UPDATE, DELETE');
"""

DOWNGRADE = r"""
DROP TABLE auth_session;
DROP TABLE account_token;
DROP TABLE user_role_assignment;
DROP TABLE user_account;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
