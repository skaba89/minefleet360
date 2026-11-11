"""Catalogue de plans SaaS (lot 1 commercialisation) — table `saas_plan` + offre candidate.

Revision ID: 0065
Revises: 0064

- `saas_plan` : donnée de référence PLATEFORME (pas de tenant_id, donc hors RLS applicative,
  exactement comme `tenant` en 0001) ; quatre plans candidats sont semés (Starter, Business,
  Mining Pro, Enterprise) — ajustables ensuite via PATCH /platform/saas-plans/{id}.
- NULL dans une colonne de quota = illimité. Le passage à RETIRED (terminal) est géré par
  l'API, jamais par DELETE : le référentiel reste joignable pour l'historique (lot 2).
- Aucun prix, aucun moyen de paiement : la tarification n'est pas modélisée avant arbitrage
  (règle « pas d'intégration non approuvée »). L'attachement plan↔société est le lot 2.
"""

from app.core.migration_tools import run_sql

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE saas_plan (
  plan_id uuid NOT NULL DEFAULT gen_random_uuid(),
  code text NOT NULL,
  name text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'DRAFT',
  max_users integer,
  max_sites integer,
  max_vehicles integer,
  max_gps_trackers integer,
  document_retention_days integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_saas_plan PRIMARY KEY (plan_id),
  CONSTRAINT uq_saas_plan_code UNIQUE (code),
  CONSTRAINT ck_saas_plan_status CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED')),
  CONSTRAINT ck_saas_plan_quotas CHECK (
    (max_users IS NULL OR max_users BETWEEN 1 AND 100000)
    AND (max_sites IS NULL OR max_sites BETWEEN 1 AND 10000)
    AND (max_vehicles IS NULL OR max_vehicles BETWEEN 1 AND 100000)
    AND (max_gps_trackers IS NULL OR max_gps_trackers BETWEEN 1 AND 100000)
    AND (document_retention_days IS NULL OR document_retention_days BETWEEN 30 AND 3650)
  )
);
CREATE INDEX ix_saas_plan_status ON saas_plan (status);
GRANT SELECT, INSERT, UPDATE ON saas_plan TO mf_app;
SELECT app.apply_touch('saas_plan');

-- Offre candidate (ajustable par PATCH ; pas de tarif à ce stade — lot 3).
INSERT INTO saas_plan (code, name, description, status, max_users, max_sites, max_vehicles, max_gps_trackers, document_retention_days) VALUES
  ('STARTER',    'Starter',      'Petites flottes — démarrage suivi, un site.',                          'ACTIVE', 5,   1,   5,   5,   90),
  ('BUSINESS',   'Business',     'Flottes multi-sites — suivi quotidien et préventif.',                  'ACTIVE', 25,  5,   40,  40,  365),
  ('MINING_PRO', 'Mining Pro',   'Opérations minières étendues — GPS intensif et échéances longues.',    'ACTIVE', 100, 20,  200, 250, 1095),
  ('ENTERPRISE', 'Enterprise',   'Grands comptes — quotas illimités, rétention à définir au contrat.',   'ACTIVE', NULL, NULL, NULL, NULL, NULL);
"""

DOWNGRADE = r"""
DROP TABLE saas_plan;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
