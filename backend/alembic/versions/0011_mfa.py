"""Double authentification TOTP (C-03, SEC-04) : secret en attente, anti-rejeu, codes de récupération.

Revision ID: 0011
Revises: 0010

Expansion pure (colonnes nullables ou avec défaut) : compatible avec la version applicative précédente.
Le secret actif reste dans `mfa_secret_encrypted` (0003) ; tous les secrets sont chiffrés (AES-GCM) par
l'application, la base ne voit jamais de clair. Les codes de récupération sont stockés hachés.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE user_account
  ADD COLUMN mfa_pending_secret_encrypted bytea,
  ADD COLUMN mfa_pending_created_at timestamptz,
  ADD COLUMN mfa_last_step bigint,
  ADD COLUMN mfa_enabled_at timestamptz,
  ADD COLUMN mfa_recovery_hashes bytea[] NOT NULL DEFAULT '{}'::bytea[],
  ADD CONSTRAINT ck_user_account_mfa_pending
    CHECK ((mfa_pending_secret_encrypted IS NULL) = (mfa_pending_created_at IS NULL)),
  -- NOT VALID : un compte marqué mfa_enabled avant cette version (refusé partout depuis R3) ne bloque pas
  -- la migration ; la contrainte s'applique à toute nouvelle écriture.
  ADD CONSTRAINT ck_user_account_mfa_enabled_at CHECK (NOT mfa_enabled OR mfa_enabled_at IS NOT NULL) NOT VALID,
  ADD CONSTRAINT ck_user_account_mfa_recovery CHECK (cardinality(mfa_recovery_hashes) <= 10);
"""

DOWNGRADE = r"""
ALTER TABLE user_account
  DROP CONSTRAINT ck_user_account_mfa_recovery,
  DROP CONSTRAINT ck_user_account_mfa_enabled_at,
  DROP CONSTRAINT ck_user_account_mfa_pending,
  DROP COLUMN mfa_recovery_hashes,
  DROP COLUMN mfa_enabled_at,
  DROP COLUMN mfa_last_step,
  DROP COLUMN mfa_pending_created_at,
  DROP COLUMN mfa_pending_secret_encrypted;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
