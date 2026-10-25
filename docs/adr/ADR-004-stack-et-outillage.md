# ADR-004 — Stack technique et outillage

- **Statut** : Proposé
- **Date** : 2026-10-25
- **Références** : `CLAUDE.md` (stack cible), `docs/00_SOCLE_CADRAGE.md` (H8, §1)

## 1. Contexte
Poste local constaté : Python 3.10.11, Node 20.19, Docker 29 ; **pas** de `psql`, `uv`, `pnpm`. Les versions exactes ci-dessous sont des **cibles** à confirmer à l'initialisation (vérifier la compatibilité et les dates de fin de support au moment du verrouillage ; non vérifié ici).

## 2. Décision par composant

| Domaine | Choix | Justification |
|---|---|---|
| Python | **3.12 dans Docker** (image officielle `python:3.12-slim`, version mineure épinglée) | Voir 2.1 |
| API | FastAPI + Pydantic 2 | Contrat OpenAPI natif |
| ORM / migrations | SQLAlchemy 2.x (style 2.0, typé), Alembic | Discipline de migration (CLAUDE.md) |
| Driver | psycopg 3 (ou asyncpg à arbitrer) | Sync vs async : démarrer en **sync** (simplicité, `SET LOCAL` par transaction plus sûr), async si mesure le justifie |
| Base | PostgreSQL 16 + PostGIS (image `postgis/postgis:16-*`, version épinglée) | H8 ; géofences |
| Frontend | React + TypeScript (strict) + Vite | CLAUDE.md |
| Tests web | Vitest (+ Testing Library), Playwright (e2e) | CLAUDE.md |
| Tests API | pytest, base PostgreSQL réelle en conteneur (pas de SQLite) pour RLS/PostGIS | Fidélité |
| Qualité | ruff (lint + format), mypy (strict progressif), ESLint, tsc | Contrôles CI |
| Gestionnaire Python | pip + `pip-tools`/lockfile **ou** `uv` dans Docker | `uv` absent localement : le conteneur évite l'installation locale |
| Gestionnaire Node | npm (livré avec Node 20) avec lockfile ; pnpm optionnel | Éviter une installation non indispensable |
| Local | `docker compose` : `db`, `api`, `web` (+ `mailpit` éventuel) | Reproductibilité |
| Contrat API | OpenAPI généré par FastAPI, exporté en fichier versionné ; client TypeScript typé généré (ex. openapi-typescript) ; test de dérive en CI | Pas de contrat écrit à la main |
| i18n | Français par défaut ; catalogue de messages (ex. i18next) ; formats `fr-GN`/`fr-FR`, GNF sans décimales (H5), fuseau d'affichage par site (H4) | CLAUDE.md |
| Logs | JSON structuré (stdout), `request_id`, `tenant_id`, `user_id`, niveau ; aucun secret ni donnée personnelle brute | Observabilité |
| CI | GitHub Actions : lint, types, tests, vérification migrations, scan de dépendances (`pip-audit`, `npm audit`), contrôle de dérive OpenAPI, import-linter | **Workflow non créé** dans cette mission |
| Dépendances de sécurité | `argon2-cffi`, `PyJWT`/`authlib` (à arbitrer) | ADR-003 |

### 2.1 Python 3.12 (Docker) vs 3.10 (local)
| Critère | 3.10 local | 3.12 Docker |
|---|---|---|
| Disponibilité | Déjà installé | Image officielle |
| Support | Fin de support en octobre 2026 (à confirmer sur le calendrier officiel) | Support restant plus long |
| Typage / perf | Moins de confort (génériques, messages d'erreur) | Meilleur ; syntaxe de types moderne |
| Parité dev/CI/prod | Divergence si prod est en conteneur | Identique partout |
**Recommandation** : exécuter tout (API, tests, migrations) **dans Docker en 3.12** ; le Python 3.10 local ne sert pas à exécuter le projet. Le code vise `requires-python >=3.12`. Option de repli : 3.11 si une dépendance bloquait (à constater, pas supposé).

## 3. Conventions
- Configuration par variables d'environnement (`pydantic-settings`), fichiers `.env.example` sans secret ; aucun secret versionné.
- Images conteneur : utilisateur non root, versions épinglées, pas de service payant provisionné.
- Migrations : un fichier Alembic par changement, réversibles ou stratégie documentée ; vérification CI = `upgrade head` sur base vide + `downgrade` quand possible + détection de dérive modèle/migration.
- Environnements : `local` (compose), recette/production **non définis** (aucun déploiement sans approbation).
- Horodatage UTC en base ; conversion à l'affichage uniquement.
- Observabilité minimale lot 1 : logs JSON, `request_id` propagé, endpoint de santé ; métriques/traces (OpenTelemetry) reportées tant que non justifiées.

## 4. Conséquences
- (+) Environnement reproductible sans installer psql/uv/pnpm ; contrat API typé de bout en bout.
- (−) Dépendance forte à Docker sur les postes (déjà présent) ; performance des volumes Docker sous Windows à surveiller.
- (−) Génération du client TS ajoute une étape de build à maintenir.
- Alternatives écartées : GraphQL (complexité), ORM alternatifs, Redis/Celery au lot 1 (H8).

## 5. Points à valider
- Versions exactes (patch) à épingler à l'initialisation après vérification des publications.
- Sync vs async pour l'accès base ; choix de la bibliothèque JWT.
- Hébergement cible (cloud/local) et exigences de résidence des données (hors périmètre, aucune provision payante sans accord).
- Convention de locale pour la Guinée (`fr-GN`) : disponibilité effective dans `Intl` à tester.
- Rien n'a été installé, construit ni exécuté.
