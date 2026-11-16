"""Référentiel des organisations sous-traitantes — lot 1 (option B du modèle de sécurité #442).

Données du DONNEUR D'ORDRE uniquement : aucune colonne de compte externe, aucune donnée nominative
(identité de société, identifiants légaux, statut contractuel). Les comptes externes (portée `org`, prédicat RLS
par organisation) relèvent du lot 2 (docs/MODELE_SECURITE_SOUS_TRAITANTS.md §5).
Migration additive : aucune table existante n'est modifiée.
"""

from app.core.migration_tools import run_sql

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE subcontractor (
  subcontractor_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code text NOT NULL,
  legal_name text NOT NULL,
  registration_number text,
  tax_id text,
  country_code text NOT NULL DEFAULT 'GN',
  status text NOT NULL DEFAULT 'ACTIVE',
  status_reason text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_subcontractor PRIMARY KEY (subcontractor_id),
  CONSTRAINT fk_subcontractor__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_subcontractor_tenant_id UNIQUE (tenant_id, subcontractor_id),
  CONSTRAINT uq_subcontractor_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_subcontractor_code CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_subcontractor_legal_name CHECK (char_length(btrim(legal_name)) BETWEEN 1 AND 240),
  CONSTRAINT ck_subcontractor_registration CHECK (registration_number IS NULL OR char_length(registration_number) BETWEEN 1 AND 64),
  CONSTRAINT ck_subcontractor_tax_id CHECK (tax_id IS NULL OR char_length(tax_id) BETWEEN 1 AND 64),
  CONSTRAINT ck_subcontractor_country CHECK (country_code ~ '^[A-Z]{2}$'),
  CONSTRAINT ck_subcontractor_status CHECK (status IN ('ACTIVE','SUSPENDED','ENDED')),
  -- Suspension ou fin de relation toujours motivée ; un statut actif ne porte pas de motif.
  CONSTRAINT ck_subcontractor_reason CHECK ((status = 'ACTIVE') = (status_reason IS NULL)),
  CONSTRAINT ck_subcontractor_reason_len CHECK (status_reason IS NULL OR char_length(btrim(status_reason)) BETWEEN 3 AND 500),
  CONSTRAINT ck_subcontractor_notes CHECK (notes IS NULL OR char_length(notes) <= 2000),
  CONSTRAINT ck_subcontractor_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('subcontractor', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('subcontractor');
"""

DOWNGRADE = r"""
DROP TABLE subcontractor;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
