# MINEFLEET 360 — API (tranche 1a)

FastAPI + SQLAlchemy 2 + PostgreSQL 16/PostGIS, monolithe modulaire (`docs/adr/ADR-001`).
Tout s'exécute en conteneur (Python 3.12) ; le Python local n'est pas utilisé.

## Démarrer (Windows, PowerShell)
```powershell
scripts\dev-up.ps1          # génère .env (secrets aléatoires, jamais commité) et lance db + api
scripts\migrate.ps1         # alembic upgrade head (rôle mf_owner)
$env:MF_BOOTSTRAP_PASSWORD = '<mot de passe fort>'
docker compose --env-file .env -f infra/docker-compose.yml exec -e MF_BOOTSTRAP_PASSWORD api `
    minefleet create-platform-admin --email admin@example.com --name "Admin plateforme"
scripts\test.ps1            # ruff, mypy, pytest sur la base minefleet_test
```
API : http://localhost:8000/api/v1/docs — e-mails capturés dans `backend/var/mail/` (aucun envoi réel).

## Modules
| Module | Contenu 1a |
|---|---|
| `core` | configuration, contexte tenant (RLS), horloge injectable, erreurs (catalogue D-26), sécurité |
| `authz` | `authz_matrix.yaml` (source des permissions), `Require(...)`, portées TENANT/SITE |
| `organization` | tenants (plateforme), tenant courant, sites |
| `identity` | connexion, refresh rotatif, invitations, réinitialisation, utilisateurs, rôles |
| `audit` | journal append-only partitionné, lecture filtrée |

## Règles
- Chaque route déclare une permission (`Require`) présente dans `authz_matrix.yaml` ; un test l'impose.
- Le contexte tenant n'est posé que par `app/core/tenancy.py` ; sans contexte, la base renvoie 0 ligne.
- Aucune suppression physique ; mises à jour avec `If-Match` ; audit dans la même transaction.
