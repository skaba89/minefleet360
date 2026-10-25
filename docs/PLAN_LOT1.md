# Plan du lot de développement vertical n°1 — MINEFLEET 360

> Statut : **proposé, en attente d'accord**. Aucun code n'est écrit tant que ce plan n'est pas validé.
> Périmètre : tenant + site + utilisateurs/rôles + véhicule + conducteur + affectation, avec isolation inter-tenant testée, journal d'audit et interface minimaliste en français.
> Références : `DECISIONS_A_ARBITRER.md` (fait foi), `USER_STORIES.md` (US-1.xx), `MATRICE_RBAC.md`, `MODELE_PHYSIQUE_LOT1.md`, `STRATEGIE_QUALITE_CI.md`, `MENACES_ET_CONTROLES.md` §8.

## 1. Découpage en trois tranches (D-21)

Chaque tranche est livrable, testée et revue (sécurité + QA) avant la suivante.

### Tranche 1a — Socle technique et sécuritaire
| Élément | Contenu |
|---|---|
| Dépôt | Branche `master` (sans commit) renommée `main`, premier commit = documentation de cadrage, `.gitignore`, `.gitattributes` (`eol=lf`), `.editorconfig`, `README` dev |
| Infra locale | `infra/docker-compose.yml` : `db` (PostgreSQL 16 + PostGIS, image officielle `postgis/postgis`), `api` (Python 3.12), `web` (Node 20) ; `infra/db/bootstrap.sql` (rôles `mf_owner`/`mf_app`, extensions) ; `.env.example` **sans secret** |
| Backend | `backend/` FastAPI : config Pydantic Settings, logs JSON + `request_id`, horloge injectable, gestion d'erreurs selon D-05, dépendance contexte tenant (`SET LOCAL app.tenant_id`), moteur d'autorisation lisant `authz_matrix.yaml` |
| Modules | `organization` (tenant, site), `identity` (comptes, rôles, sessions, jetons d'invitation), `audit` |
| Migrations | Alembic `0001_foundation` → `0004_audit` (selon `MODELE_PHYSIQUE_LOT1.md`, sans `idempotency_record`) |
| Auth | Connexion code d'espace + e-mail + mot de passe (argon2id), JWT d'accès court + refresh rotatif httpOnly, déconnexion, verrouillage progressif |
| Outillage | ruff, mypy, pytest, scripts `scripts/*.ps1` + scripts npm ; workflow `.github/workflows/ci.yml` écrit **mais non exécuté** (pas de dépôt distant) |
| Seed | Commande `seed-demo` : 2 tenants fictifs + plateforme, sites, comptes — mots de passe générés à l'exécution, jamais commités |

### Tranche 1b — Référentiels flotte et personnel
| Élément | Contenu |
|---|---|
| Modules | `fleet` (vehicle, vehicle_category par tenant, vehicle_status_history), `workforce` (driver, driver_license, driver_qualification) |
| Migrations | `0005_fleet`, `0006_workforce` |
| Règles | Numéro de parc unique à vie par tenant ; statuts D-02/D-03 ; masquage serveur des données personnelles (D-15) ; `row_version` + `If-Match` (D-19) |

### Tranche 1c — Affectations et interface
| Élément | Contenu |
|---|---|
| Module | `assignment` (vehicle_assignment) |
| Migration | `0007_assignment` (EXCLUDE gist véhicule + conducteur, `btree_gist`) |
| Règles | Éligibilité (conducteur `ACTIVE`, permis + habilitation valides sur l'intervalle, véhicule `AVAILABLE`, même site), pas d'antidatage, refus 409 des changements de statut bloquants (D-11), conformité dérivée (D-12), activation explicite avec revérification (D-27), suspension manuelle motivée (D-30) |
| Frontend | `frontend/` React + TS + Vite : connexion, sélecteur de site, listes/fiches véhicules, conducteurs, affectations, utilisateurs/rôles, journal d'audit ; libellés FR, dates JJ/MM/AAAA, fuseau `Africa/Conakry` ; états vide/chargement/erreur/403/404 ; client API typé généré depuis l'OpenAPI |
| E2E | Playwright : parcours dispatcher (créer et clôturer une affectation), refus d'affectation inéligible, utilisateur d'un autre tenant ne voit rien |

## 2. Critères d'acceptation globaux du lot 1
1. Toute route API déclare une permission ; un test échoue si une route n'en déclare pas.
2. Tests d'isolation **générés** depuis `authz_matrix.yaml` : pour chaque ressource et chaque action (lecture, liste, création, modification, changement de statut), un utilisateur du tenant B reçoit `404` sur un objet du tenant A, et aucune FK ne peut référencer un objet d'un autre tenant (vérifié aussi en base).
3. RLS : une connexion `mf_app` sans contexte tenant lit **0 ligne** de chaque table métier.
4. Chaque mutation produit exactement un `audit_event` dans la même transaction ; `UPDATE`/`DELETE` sur `audit_event` échouent pour `mf_app`.
5. Chevauchement d'affectation refusé (`409`) par la base même si le contrôle applicatif est contourné ; tests de concurrence (deux créations simultanées).
6. Migrations `upgrade → downgrade → upgrade` passent sur base vide.
7. Données personnelles masquées pour les rôles non-HR dans **la réponse API** (pas seulement l'UI).
8. Tests fuseau avec fixtures non-UTC (D-23).
9. UI en français, navigable au clavier, contrastes AA vérifiés manuellement (outil automatique reporté).
10. Rapport de fin de tranche : commandes exécutées, sorties réelles, ce qui n'a **pas** été exécuté.

## 3. Matrice d'autorisation des données (résumé lot 1 — détail `MATRICE_RBAC.md`)
| Ressource | Lecture | Écriture | Portée |
|---|---|---|---|
| tenant | `PLATFORM_ADMIN` (méta uniquement), `TENANT_ADMIN` (le sien) | `PLATFORM_ADMIN` (création) | plateforme / tenant |
| site | tous rôles du tenant | `TENANT_ADMIN` | tenant |
| comptes, rôles | `TENANT_ADMIN` | `TENANT_ADMIN` (pas d'auto-escalade, dernier admin protégé) | tenant |
| véhicule | rôles opérationnels | `OPS_MANAGER`, `TENANT_ADMIN` (statut : `OPS_MANAGER`, `WORKSHOP_CHIEF`) | site/tenant |
| conducteur, permis, habilitations | `HR` (complet), opérationnels (masqué) | `HR` | site/tenant |
| affectation | rôles opérationnels | `DISPATCHER` (site), `OPS_MANAGER` | site/tenant |
| journal d'audit | `TENANT_ADMIN`, `AUDITOR` | personne | tenant |

## 4. Fichiers qui seront créés (aucun fichier existant modifié hors `docs/`)
```
.gitignore  .gitattributes  .editorconfig  .env.example
infra/docker-compose.yml  infra/db/bootstrap.sql
backend/pyproject.toml  backend/Dockerfile  backend/alembic.ini  backend/alembic/...
backend/app/{core,organization,identity,audit,fleet,workforce,assignment}/...
backend/app/authz/authz_matrix.yaml
backend/tests/{unit,integration,isolation,db}/...
frontend/package.json  frontend/vite.config.ts  frontend/src/...  frontend/e2e/...
scripts/*.ps1   .github/workflows/ci.yml (non exécuté)
```

## 5. Dépendances proposées (à approuver)
- **Backend** : fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy 2, psycopg 3, alembic, argon2-cffi, pyjwt, pyyaml, structlog (ou logging JSON standard). Tests/qualité : pytest, pytest-cov, httpx, ruff, mypy.
- **Frontend** : react, react-dom, react-router, @tanstack/react-query, openapi-typescript (génération de types). Tests : vitest, @testing-library/react, playwright.
- Aucune dépendance payante, aucun service externe.

## 6. Vérification
- `scripts/test.ps1` lance : ruff, mypy, pytest (base PostgreSQL du compose), tests d'isolation générés, tests de migration ; `npm run lint && npm run typecheck && npm test` ; Playwright sur la pile locale.
- Revue `security-engineer` puis `qa-devops-engineer` après chaque tranche ; constats bloquants corrigés avant la tranche suivante.

## 7. Hors périmètre du lot 1 (rappel D-14, D-16)
Missions, ordres de travail, GPS, offline/idempotence, exports, accès support plateforme, écran conducteur, compteurs, documents véhicule, MFA (avant pilote), chaînage de hash, CI distante, tout déploiement.

## 8. Risques
| Risque | Mitigation |
|---|---|
| Complexité RLS + pool de connexions | `SET LOCAL` par transaction, tests « 0 ligne sans contexte » dès 1a |
| DDL non validé (écrit sans exécution) | Les migrations 1a sont les premières à tourner sur PostgreSQL réel ; écarts reportés dans le modèle physique |
| Python 3.10 local ≠ 3.12 cible | Exécution exclusivement en conteneur |
| Catégories de permis guinéens non validées (C-07) | Valeurs fictives marquées « à valider localement » |
| Pas de CI distante (C-17) | CI exécutée localement par script ; workflow prêt |
