"""Notifications des alertes GPS par e-mail et/ou SMS, au choix de chaque utilisateur.

Revision ID: 0063
Revises: 0062

- `user_alert_notification` : préférences personnelles (e-mail, SMS, numéro au format E.164). Rien n'est envoyé
  par défaut ; le SMS exige un numéro saisi par l'utilisateur lui-même.
- `notification_outbox` : une ligne par destinataire, canal et alerte, écrite dans la transaction de l'alerte,
  livrée ensuite par la tâche `minefleet deliver-notifications` (jamais pendant l'ingestion GPS). Unicité par
  (destinataire, canal, alerte) ; anti-avalanche appliqué à l'écriture (docs/GPS_ALERTS.md).
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE user_alert_notification (
  tenant_id uuid NOT NULL,
  user_account_id uuid NOT NULL,
  email_enabled boolean NOT NULL DEFAULT false,
  sms_enabled boolean NOT NULL DEFAULT false,
  phone_e164 text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_user_alert_notification PRIMARY KEY (tenant_id, user_account_id),
  CONSTRAINT fk_uan__user FOREIGN KEY (tenant_id, user_account_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_uan_phone CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT ck_uan_sms_phone CHECK (NOT sms_enabled OR phone_e164 IS NOT NULL)
);
SELECT app.apply_tenant_rls('user_alert_notification', 'SELECT, INSERT, UPDATE');

CREATE TABLE notification_outbox (
  notification_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  user_account_id uuid NOT NULL,
  channel text NOT NULL,
  gps_alert_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  attempts integer NOT NULL DEFAULT 0,
  last_error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  CONSTRAINT pk_notification_outbox PRIMARY KEY (notification_id),
  CONSTRAINT uq_no_recipient_alert UNIQUE (tenant_id, user_account_id, channel, gps_alert_id),
  CONSTRAINT fk_no__user FOREIGN KEY (tenant_id, user_account_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_no__alert FOREIGN KEY (tenant_id, gps_alert_id)
    REFERENCES gps_alert (tenant_id, gps_alert_id) ON DELETE RESTRICT,
  CONSTRAINT ck_no_channel CHECK (channel IN ('EMAIL','SMS')),
  CONSTRAINT ck_no_status CHECK (status IN ('PENDING','SENT','FAILED')),
  CONSTRAINT ck_no_attempts CHECK (attempts BETWEEN 0 AND 10),
  CONSTRAINT ck_no_sent CHECK ((status = 'SENT') = (sent_at IS NOT NULL)),
  CONSTRAINT ck_no_error CHECK (last_error_code IS NULL OR last_error_code ~ '^[A-Z_]{1,40}$')
);
CREATE INDEX ix_no_pending ON notification_outbox (tenant_id, created_at) WHERE status = 'PENDING';
CREATE INDEX ix_no_recent ON notification_outbox (tenant_id, user_account_id, channel, created_at DESC);
SELECT app.apply_tenant_rls('notification_outbox', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE notification_outbox;
DROP TABLE user_alert_notification;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
