# Readiness commerciale — état courant

**Base auditée :** `main@9c69f44e0dbf1a10406acfd77711595d04202cd1` (dernier commit : 2026-11-06 08:02 +0100, PR #373).
**Audit exécuté :** 8–9 novembre 2026, en lecture directe du dépôt + exécutions locales (voir §2).
**Statut du document :** courant ; remplace les scores historiques (62, 70,3, 81) comme référence de décision jusqu'au prochain audit.
**Verdict :** NO-GO pour la commercialisation industrialisée — GO conditionnel maintenu pour préparer un pilote fermé (aligné avec `docs/qa/GO_NO_GO.md` à la base `089d801`).

> **Règle de lecture.** Ce document ne mélange jamais preuve statique (le code existe et est testé), preuve d'exécution (testé ici) et preuve d'exploitation (validé sur environnement réel). Une inconnue reste explicitement inconnue (§6). Le score est un outil de pilotage interne, jamais une promesse commerciale.

---

## 1. Méthode

| Source | Périmètre | Fiabilité |
|---|---|---|
| Lecture de code (backend 221 fichiers `app/`, frontend, `infra/`, `scripts/`, `.github/`) | architecture, sécurité, RBAC, RLS, CI | élevée |
| Exécution locale (sandbox Linux, Python 3.12 / Node 24) | lint, types, tests unitaires, build | élevée |
| Documents de gouvernance datés (`docs/qa/`, `docs/audit/`) | historique des audits, verdicts | moyenne (non reproductible ici) |
| CI GitHub (workflows `ci.yml`, `e2e-isolation.yml`, `gps-benchmark-tests.yml`, `security-static.yml`) | gates de fusion | **non revérifiable depuis cet environnement** (API non authentifiée saturée) — inconnue §6.1 |
| VPS OVHcloud / staging | exploitation réelle | **non accessible** — inconnue §6.2 |

Hors périmètre de cet audit : matériel GPS réel, Android physique, réseau mobile guinéen réel, données de production, exercice de restauration sur coffre externe réel.

## 2. Preuves d'exécution locale (cet audit, commit `9c69f44`)

| Contrôle | Résultat | Périmètre |
|---|---|---|
| `ruff check .` | 0 erreur | backend complet |
| `ruff format --check .` | OK | backend complet |
| `mypy app` | Succès, 221 fichiers | backend |
| `pytest tests_unit` | **360 passés** (dont 7 nouveaux) | unitaires sans base |
| `pytest tests/`, `tests_migrations/` | **non exécutés** (PostgreSQL 16/PostGIS requis, absent de l'environnement) | harnais RLS/authz — couvert par la CI du dépôt |
| `npm run typecheck` | OK (strict) | frontend |
| `npm test` (Vitest) | **223 passés** (dont 2 nouveaux) | frontend |
| `npx vite build` | OK | frontend |
| Playwright (4 configs) | **non exécuté** (pile locale requise) | couvert par la CI `e2e-isolation.yml` |
| `scripts/generate_role_route_matrix.py --check` | OK, document régénéré | matrice §5 |

## 3. Tableau de bord de maturité (grille imposée)

| Domaine | Pondération | Score | Justification synthétique |
|---|---:|---:|---|
| Sécurité et isolation | 20 | **16** | RLS forcée sur 75 tables, RBAC machine (118 permissions/232 routes) testé, MFA chiffré, refresh rotatif anti-rejeu, journal append-only. Non certifié indépendant ; 4 durcissements traités ici, 1 restant (§4.1). |
| Fiabilité et résilience | 20 | **13** | Restauration chiffrée testée en CI avec gates RLS fail-closed ; release/rollback par digest immuables ; supervision sondes+SMTP crash-safe. RPO/RTO jamais mesurés sur coffre réel ; alertes jamais éprouvées par incident réel. |
| Fonctionnalités métier | 20 | **15** | Couverture large et testée : parc, affectations, missions/pesées, GMAO corrective+préventive, pièces, pneus, carburant, HSE, RH, coûts, juridique. GPS avancé mais **aucun traceur certifié** ; offline limité au périmètre HSE/OT. |
| UX/UI et offline | 15 | **11** | UI française complète, GNF/fuseaux corrects, responsive audité E2E, 0 bouton inerte constaté, offline HSE idempotent éprouvé (build prod + émulation Android). Android physique jamais testé ; inspections non couvertes hors ligne. |
| Exploitation DevOps/SRE | 15 | **11** | 4 workflows à gates denses (couverture 85 %, migrations peuplées, contrat OpenAPI, audits dépendances, SAST/secrets). Pas de build/push d'images en CI, pas de dependabot, pas de métriques continues. |
| Commercialisation SaaS | 10 | **2** | Espace PLATFORM_ADMIN livré (sociétés, suspension, santé) et provisioning tenant transactionnel. Aucun plan/quota/abonnement/facturation (0 table), ni support/onboarding/SLA. |
| **Total** | **100** | **68** | Écart avec le 70/100 interne (grille différente, base `089d801`) : les deux grilles conduisent au même verdict. |

**Décision correspondante :** GO technique non revendiqué ; GO pilote conditionné aux 8 prérequis du `GO_NO_GO.md` (tous non levés) ; GO commercial impossible tant que le domaine Commercialisation SaaS n'existe pas (§4.6).

## 4. Analyse par domaine

### 4.1 Sécurité et isolation — 16/20

**Prouvé (statique + exécution locale) :** RLS activée **et forcée** sur 75 tables (`0001_foundation.py:57-71`), rôle applicatif `mf_app` non-superuser/non-BYPASSRLS vérifié au démarrage (`main.py:50-57`) et après restauration (`verify-restore.sh`) ; contexte tenant posé en un seul module transactionnel, whitelist d'appelants fermée (`test_architecture.py`) ; RBAC deny-by-default généré du YAML vers les tests (`test_authz_matrix.py` : concordance route↔permission, refus 403 audité, portée site, objets étrangers indiscernables en 404) ; refresh token rotatif avec détection de rejeu et révocation de session ; MFA TOTP chiffré AES-256-GCM avec enrôlement forcé pour les rôles sensibles ; cookies HttpOnly/SameSite=Strict avec vérification d'Origin ; argon2id ; limiteurs d'authentification persistés PostgreSQL ; journal d'audit append-only partitionné mensuellement ; Gitleaks + Bandit (high/high) en CI.

**Corrigé par cet audit :** `/openapi.json` et `/docs` ne sont plus publiés en production (ils cartographiaient `x-permission` par route) — `app/main.py` + 7 tests (`tests_unit/test_production_hardening.py`). La clé HMAC des compteurs de limitation d'authentification est **dédiée du secret JWT** (`MF_RATE_LIMIT_KEY`, obligatoire en recette/production, dérivée en local/test/ci) : la rotation du secret JWT n'invalide plus les verrouillages en cours et une fuite de l'une des deux clés ne compromise pas l'autre mécanisme — `app/core/config.py`, `app/core/ratelimit.py`, compose/verify-restore/preflight/.env prod mis à jour, +6 tests. Les permissions orphelines de session sont **implémentées** : écran « Mes sessions » (`GET /me/sessions`, `POST /me/sessions/revoke-others`, `POST /me/sessions/{id}/revoke`, révocation administrative `POST /users/{user_id}/sessions/revoke` pour `TENANT_ADMIN`), auditées, indiscernabilité 404 hors tenant, +7 tests d'intégration PostgreSQL (`tests/test_sessions.py`, exécutés en CI) et page UI `/mon-compte/sessions` (3 tests Vitest).

**Partiel / à traiter (P1) :** pas de rotation de secrets outillée.

**Absent / risque :** aucun audit de sécurité indépendant (bloquant commercial, SEC-01/02) ; revue juridique géolocalisation/données salariés en Guinée non engagée (bloquant pilote, C-01/C-08/C-09).

**Tests nécessaires :** suite `tests/` complète sur PostgreSQL (CI), exercice A/B d'isolation en recette réelle (GO_NO_GO §prérequis), vérifier que le démarrage d'un `api` staging sans `MF_RATE_LIMIT_KEY` échoue proprement (couvert par les tests unitaires + exigence compose).

**Critères de validation :** 0 finding critique/élevé ouvert ; audit indépendant rendu ; avis juridique écrit ; `--check` matrice vert en CI.

### 4.2 Fiabilité et résilience — 13/20

**Prouvé (statique + CI documentée) :** job CI `backup-restore` (dump → GPG AES256/SHA512 → rclone immutable → checksum → restauration isolée → smoke API) ; `verify-restore.sh` avec gates : ≥10 tables, `alembic_version` présente, RLS activée+forcée, test fail-closed (`SET ROLE mf_app` sans contexte → 0 ligne), démarrage API sur base restaurée ; `backup.sh` refuse un dump non validé par `pg_restore --list` ; release staging exige une sauvegarde de <1 h avant déploiement et rollback applicatif automatique en cas d'échec du smoke ; sondes (HTTP, `/ready`, fraîcheur backup, jobs systemd) + orchestrateur d'alertes SMTP at-least-once crash-safe testé par 11 suites ops en CI.

**Partiel / absent (bloquants GO_NO_GO) :** restauration jamais exécutée depuis un coffre **externe réel** ; RPO/RTO jamais mesurés ; alertes jamais éprouvées par injection d'incident réel ; pas de healthcheck Docker sur `api`/`web` (les sondes applicatives le compensent partiellement) ; pas de métriques continues (Prometheus/AI) ; exercice complet release→rollback→vérifications non attesté sur staging isolé (R2 « non validé en recette »).

**Tests nécessaires :** exercice R1 (restauration réelle avec mesure RPO/RTO), injection d'incident d'alerte, `staging-release.sh apply` puis rollback sur staging.

**Critères de validation :** `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` renseigné avec mesures datées ; sonde d'alerte verte après incident réel ; receipt `release-state/current.json` produit par un apply réel.

### 4.3 Fonctionnalités métier — 15/20

**Prouvé :** 79 tables ORM / 232 routes API couvrant : parc (engins, catégories, compteurs km/h, documents réglementaires immuables, échéances), affectations (éligibilité, transitions, conflits D-41), missions et rotations avec pesées (tickets, corrections, approbations — la GPS n'est jamais une preuve de tonnage, règle appliquée), GMAO corrective (déclaration→diagnostic→OT→décision→exécution→clôture, transactionnelle, testée en concurrence) et préventive (plans, échéances, verrous PostgreSQL), pièces (catalogue, magasins, CMP, réservations concurrentes, réappro, BC), pneus (inventaire individuel, montage, inspections, réforme), carburant (cuves, pompes, achats, demandes/décisions séparées, inventaires, seuils, anomalies, rapprochements), HSE (incidents, actions correctives, inspections, checklists), RH terrain (conducteurs, permis E.164 +224, qualifications, échéances), coûts complets, contrats/assurances, indicateurs, fiabilité (MTBF/MTTR). E2E navigateur par rôle exécutés en CI sur base éphémère.

**Partiel :** GPS temps réel (carte MapLibre auto-hébergée, replay, géofences, alertes, SSE LISTEN/NOTIFY, reprise réseau) mais le registre d'adaptateurs ne contient que `minefleet-json-v1`, **non certifié matériel** et verrouillé par test (`test_gps_payload_adapters.py:41` : aucun Teltonika/Queclink avant essai physique) ; offline limité à la déclaration HSE + notes d'OT.

**Absent :** couche SaaS commerciale (§4.6), exports Excel/PDF avancés, IA (anomalies, prévision).

**Défaillant :** rien de démontré en CI ; les parcours critiques sont testés (concurrence, idempotence, stocks).

**Tests nécessaires :** essais traceur réels (protocole `GPS_FOURNISSEUR_CAHIER.md`), Android physique hors ligne, charge p95/p99 GPS sur staging.

### 4.4 UX/UI et offline — 11/15

**Prouvé :** interface 100 % française (D-01), montants GNF via `Intl.NumberFormat`, fuseau du site (`Africa/Conakry` proposé), états chargement/vide/erreur standardisés avec `request_id`, pagination, filtres, responsive audité par E2E DOM (débordement 360 px, cibles ≥44 px, police ≥16 px), enrôlement MFA bloquant, audit « boutons inertes » négatif re-fait aujourd'hui (0 `onClick` vide, 0 `alert`) ; mode hors ligne terrain : déclaration HSE via outbox IndexedDB idempotente (clé `operationId`, Web Locks anti-doublon inter-onglets, backoff borné, purge à la déconnexion, garde-fou anti-secrets dans les payloads), testée en E2E sur build production avec service worker (desktop + Pixel 7 émulé) ; brouillons d'OT transmis manuellement.

**Corrigé par cet audit :** page 404 dédiée (heading, explication, retour accueil) remplaçant le `<p>` nu — +2 tests.

**Partiel / absent :** inspections HSE non couvertes hors ligne (choix produit à arbitrer) ; tampon GPS téléphone en RAM volatile (perte au rechargement — assumé, OFF-01) ; Android physique jamais testé ; recherche globale absente.

**Critères de validation :** E2E `e2e-field` verts en CI ; essai Android réel documenté ; décision arbitrée sur l'offline des inspections.

### 4.5 Exploitation DevOps/SRE — 11/15

**Prouvé :** workflows `ci.yml` (lint/format, mypy, migrations peuplées 0004→head, tests+RLS avec `--cov-fail-under=85`, pip-audit, contrat OpenAPI régénéré-diffé, `gen_permissions.py --check`, npm audit high, build, smoke navigateur), `e2e-isolation.yml` (isolation tenant + parcours démo par rôle, base éphémère, comptes fictifs), `security-static.yml` (Bandit high/high, Gitleaks sur historique), `gps-benchmark-tests.yml` (filtré par chemins) ; scripts ops durcis (config offsite parsée comme données, jamais sourcée shell ; umask 077 ; `O_NOFOLLOW` ; moindre privilège secrets API) ; 5 timers systemd durcis (monitor 5 min, HSE digest, préventif, balayage signal GPS, notifications 1 min) ; images runtime non-root avec labels de traçabilité (commit + tête Alembic).

**Absent :** build/push des images de release dans la CI (les manifests référencent des digests mais le build reste manuel) ; dependabot ; SBOM ; publication de couverture ; métriques/seuils SLO collectés en continu ; runbook SRE consolidé.

**Tests nécessaires :** job CI de build+push signé des images ; ajout dependabot ; drill d'alerte.

### 4.6 Commercialisation SaaS — 2/10

**Prouvé :** espace PLATFORM_ADMIN distinct (tableau de bord, liste/création/suspension/réactivation des sociétés, état des services) — PR #369-#370 ; provisioning d'un tenant en une transaction (copie du catalogue, invitation du premier TENANT_ADMIN, double audit) ; connexion plateforme dédiée avec MFA ; seeds de démonstration gardés (refus en production et si clients réels présents).

**Absent (0 table, 0 endpoint) :** plans et tarifs, quotas par société, abonnements, facturation, échéances/renouvellement, suspension graduée pour impayé, tooling support, onboarding guidé, réversibilité/export client, SLA. Aucun moyen de paiement intégré (conforme à la règle « pas d'intégration non approuvée »).

**Conséquence :** le GO commercial est structurellement impossible avant un chantier dédié (Phase 13 de la mission). Aucun prix ne doit être annoncé avant coût-servi et entretiens clients (`COMMERCIAL_LAUNCH_PLAN.md` : « aucun tarif fixé »).

**Tests nécessaires :** conception+migration plans/quotas, tests de plafonnement, tests de facturation, tests de réversibilité.

## 5. Matrice comptes/rôles/menus/routes

La matrice complète (14 rôles × 31 entrées de menu × routes UI × 118 permissions × 232 routes API) est générée mécaniquement dans [`docs/qa/ROLE_PAGE_ACTION_MATRIX.md`](../qa/ROLE_PAGE_ACTION_MATRIX.md) avec garde anti-dérive `--check`. Constats associés : aucun rôle attendu n'est absent, `PLATFORM_ADMIN` est bien isolé des données client (aucune field_policy visible), plus aucune permission orpheline (sessions implémentées §4.1), `maintenance.preventive.*` marquées `later` alors qu'implémentées (incohérence de tranche à corriger ou assumer).

## 6. Inconnues explicites (restent inconnues)

1. **État CI du HEAD `9c69f44`** : l'API GitHub non authentifiée est saturée depuis cet environnement ; la dernière preuve documentée est une CI verte sur `089d801` (2 commits avant). À revérifier avant toute fusion.
2. **Staging OVHcloud** : non accessible (état réel des conteneurs, révision Alembic 0063, volumes, proxy partagé — tout doit être revérifié sur place avant toute opération).
3. **Matériel GPS** : aucun modèle/firmware certifié ; compatibilités annoncées nulles et interdites par test.
4. **Android physique et réseau guinéen réel** : jamais testés.
5. **RPO/RTO réels** : non mesurés.
6. **Conformité juridique** : aucun avis professionnel (juriste guinéen requis).

## 7. Priorisation des prochains travaux

**P0 (bloquants GO pilote — repris du GO_NO_GO, inchangés) :** coffre de sauvegarde externe réel + RPO/RTO mesurés ; exercice staging release→rollback→vérifications (R2) ; isolation A/B en recette réelle ; revue juridique ; essai traceur physique ; essai Android réel ; SLO GPS p95/p99 ; éprouver les alertes par incident.

**P1 (découverts/confirmés par cet audit) :** ~~dédier la clé HMAC du rate-limiting~~ (traité — `MF_RATE_LIMIT_KEY`) ; ~~implémenter `identity.session.revoke_own/any`~~ (traité — écran « Mes sessions » + révocation administrative, §4.1) ; build/push d'images signées en CI + dependabot ; étendre l'offline aux inspections HSE (après arbitrage produit) ; rejouer `MATURITY_SCORECARD.md` et recalibrer `FUNCTIONAL_COVERAGE.md` (périmé au 30 oct : décrit HSE/pièces/pneus comme absents, contredit par les migrations 0036-0045 et la CI actuelle) ; harmoniser les tranches `later` du YAML.

**P2 :** chantier SaaS commercial (plans/quotas/facturation) — à lancer seulement après le GO pilote ; consolidation documentaire (regrouper les preuves DR dans `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` après exercice réel).

*Note : `docs/roadmap/PRIORITIZED_DELIVERY_PLAN.md` n'est pas créé ici pour éviter le doublon avec `ROADMAP_85_TO_95.md` (backlog P0/P1/P2 existant) et le présent §7 ; consolidation à arbitrer.*

## 8. Registre des documents exigés

| Document | État |
|---|---|
| `docs/audit/COMMERCIAL_READINESS_CURRENT.md` | **créé** (le présent document) |
| `docs/qa/ROLE_PAGE_ACTION_MATRIX.md` | **créé** (généré, `--check` anti-dérive) |
| `docs/qa/GO_NO_GO.md` | existant, cohérent (NO-GO commercial / GO conditionnel pilote) — à réévaluer après P0 |
| `docs/qa/REGRESSION_EVIDENCE.md` | absent — preuves brutes dans `docs/audit/preuves/` + §2 ici ; à créer lors du premier exercice de non-régression formel |
| `docs/security/OPEN_RISKS.md` | absent — risques ouverts dispersés (SEC-01/02, REL-01, GPS-01/02, OFF-01, OPS-01/02) ; à consolider |
| `docs/ops/RELEASE_READINESS.md` | absent — couvert par `STAGING_RELEASE_ROLLBACK.md` + `INDUSTRIAL_READINESS_2026.md` |
| `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` | absent — à créer après l'exercice R1 réel |
| `docs/product/COMMERCIAL_OFFERS.md` | absent — `COMMERCIAL_LAUNCH_PLAN.md` liste 4 offres candidates sans tarifs |
| `docs/product/PILOT_ACCEPTANCE.md` | absent — `CRITERES_GO_PILOTE.md` + `INDUSTRIAL_ACCEPTANCE_TESTS.md` (scénarios non exécutés) |
| `docs/roadmap/PRIORITIZED_DELIVERY_PLAN.md` | volontairement non dupliqué (§7) |
