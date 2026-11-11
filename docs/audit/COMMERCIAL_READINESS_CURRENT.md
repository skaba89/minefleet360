# Readiness commerciale — état courant

**Base auditée :** `main@e36ab33178f9e8ec8cf2f82f3b09735e5dd10ea6` (PR #411 fusionnée, 2026-11-11).
**Audit exécuté :** 11 novembre 2026 — exécutions locales complètes (PostgreSQL 16.10 + PostGIS disponibles) **et** CI GitHub vérifiée via API authentifiée.
**Statut du document :** courant ; remplace la révision du 8–9 novembre 2026 (base `9c69f44`, 68/100) comme référence de décision.
**Verdict :** **NO-GO commercial maintenu — GO conditionnel pilote maintenu** (aucun prérequis terrain du `GO_NO_GO.md` n'est levé). Score de maturité : **74/100** (grille imposée), en progression de +6 sur des éléments **vérifiés** (remédiations #374–#376, recette R1–R10 #400–#407, socle E2E navigateur #408, écarts UI #409, actions E2E + correctif GRANT #410–#411) — pas sur une validation terrain ou opérationnelle.

> **Règle de lecture.** Ce document ne mélange jamais preuve statique (le code existe et est testé), preuve d'exécution (testé ici ou en CI sur infrastructure jetable) et preuve d'exploitation (validé sur environnement réel). Un test CI n'est **pas** une preuve de fonctionnement en conditions réelles. Une inconnue reste explicitement inconnue (§6). Le score est un outil de pilotage interne, jamais une promesse commerciale.

---

## 1. Méthode

| Source | Périmètre | Fiabilité |
|---|---|---|
| Lecture de code (backend 221 fichiers `app/`, frontend, `infra/`, `scripts/`, `.github/`) | architecture, sécurité, RBAC, RLS, CI | élevée |
| Exécution locale complète (sandbox Linux, PostgreSQL 16.10 + PostGIS, Python 3.12 / Node 22) | lint, types, **suite intégrée complète (5 207 tests)**, Vitest, build | élevée |
| CI GitHub (`ci.yml`, `e2e-isolation.yml`, `security-static.yml`, `release-images.yml`, `gps-benchmark-tests.yml`) — vérifiée le 2026-11-11 via API authentifiée | gates de fusion, E2E navigateur sur base éphémère | élevée (infrastructure **jetable** : ne prouve pas l'exploitation réelle) |
| Documents de gouvernance datés (`docs/qa/`, `docs/audit/`, `docs/ops/`) | historique des audits, verdicts | moyenne (non reproductible ici) |
| VPS OVHcloud / staging | exploitation réelle | **non accessible** — inconnue §6.2 |

Hors périmètre de cet audit : matériel GPS réel, Android physique, réseau mobile guinéen réel, données de production, exercice de restauration sur coffre externe réel.

Différence majeure avec la révision précédente : la suite intégrée backend (harnais RLS/authz sur PostgreSQL réel) est **désormais exécutée localement de bout en bout** (5 207 tests, contre 360 unitaires seuls au 9 novembre), et l'état CI est **vérifié** (l'inconnue §6.1 de la révision précédente est levée).

## 2. Preuves d'exécution locale et CI (audit exécuté sur `e36ab33`, révisé jusqu'à `2bc1b7d`)

**Révisions post-exécution (vérifiées, aucune re-exécution requise — pas de code produit concerné) :** PR #412
(documentation d'audit et GO/NO-GO) et PR #413 (forme canonique du refus d'accès direct, `<AccessDenied />`,
17 points de refus / 10 fichiers, Vitest mis à jour) ; CI `main@2bc1b7d` vérifiée par API le 2026-11-11 :
`ci` 11 min 54 s ✅, `e2e-isolation` 5 min 24 s ✅, `security-static` 18 s ✅. Le runbook de recette staging
(`docs/ops/RECETTE_STAGING_VALIDATION.md`) est publié après cette exécution : procédure pure, aucune
exécution terrain.

| Contrôle | Résultat | Périmètre |
|---|---|---|
| `ruff check .` + `ruff format --check .` | 0 erreur, 469 fichiers formatés | backend complet |
| `mypy app` | Succès, 221 fichiers | backend |
| `pytest -q -x` (MF_ENV=test, base `minefleet_test`) | **5 207 passés**, 43 avertissements, 7 min 25 s | **suite intégrée complète** (RLS, authz, concurrence, migrations) |
| `npx tsc --noEmit` | OK (strict) | frontend |
| Vitest | **233/233** (56 fichiers) — +10 depuis la révision précédente (223) | frontend |
| `npm run build` | OK, bundle 4,9 Mo | frontend |
| `generate_role_route_matrix.py --check` + `gen_permissions.py --check` | « matrice à jour » ×2 | anti-dérive RBAC/menus |
| CI `main` sur `e36ab33` | `ci` 7 min 56 s ✅, `e2e-isolation` 5 min 27 s ✅, `security-static` 16 s ✅ | vérifiée par API le 2026-11-11 |
| PR #400 → #411 | **12/12 fusionnées** (recette R1–R10, socle UI E2E, écarts UI, actions E2E) | chaque PR avec ses 3 workflows verts |

Extraits datés : `docs/audit/preuves/` (pytest.txt, vitest.txt, typecheck.txt, build.txt, anti_derive.txt, ruff.txt, format.txt, mypy.txt).

**Bugs réels trouvés et corrigés par la chaîne de recette depuis le dernier audit** (valeur démontrée du dispositif) :
1. RLS post-commit sur le cycle carburant — corrigé par PR #403 (tranche R6).
2. `GRANT UPDATE` manquant à `mf_app` sur `spare_part_replenishment` → **500** sur submit/decision pour tout le monde (régression 0042/0044 jamais couverte par les 403 seuls) — migration additive 0064 + test de régression PR #410 ; les specs E2E navigateur l'ont révélé sur un serveur réel.

## 3. Tableau de bord de maturité (grille imposée)

| Domaine | Pondération | Score (9 nov) | Score (11 nov) | Justification synthétique |
|---|---:|---:|---:|---|
| Sécurité et isolation | 20 | 16 | **17** | RLS forcée sur 75 tables, RBAC machine (118 permissions / 232 routes) testé deny-by-default, MFA chiffré, refresh rotatif anti-rejeu, audit append-only. **Nouveau depuis le 9 nov** : écran « Mes sessions » + révocations `identity.session.revoke_own/any` (#375, 7 tests d'intégration + 3 Vitest), OpenAPI/docs fermés en production (#374, +7 tests), clé HMAC rate-limit dédiée du secret JWT (#374, +6 tests), tranche R8 (IDOR, 429, audit) verte. Restent : audit indépendant, avis juridique, rotation de secrets outillée. |
| Fiabilité et résilience | 20 | 13 | **14** | Restauration chiffrée testée en CI avec gates RLS fail-closed ; release/rollback par digest immuables ; **images de release signées Cosign + SLSA + SBOM publiées par CI** (#376). La recette a **prouvé sa capacité à attraper 2 bugs réels** (#403, #410) — le dispositif de vérification fonctionne. Restent non mesurés : RPO/RTO sur coffre externe réel, exercice release→rollback sur staging, éprouvetage des alertes par incident réel. |
| Fonctionnalités métier | 20 | 15 | **16** | Périmètre inchangé (79 tables / 232 routes) mais **profondeur de preuve accrue** : 10 tranches de recette API R1–R10 sur serveur réel (#400–#407) et **7 specs E2E navigateur d'actions métier** en CI (correction/annulation de pesée, réappro quatre-yeux, acquittement GPS, HSE double regard, contrats, tenants plateforme, police d'assurance #410/#411). Toujours : aucun traceur certifié, offline limité à HSE/OT, cycle documentaire juridique bloqué par harnais S3/ClamAV. |
| UX/UI et offline | 15 | 11 | **13** | **Nouveau** : socle E2E d'accès direct 34 routes × 13 rôles — « jamais Page introuvable ni Erreur inattendue » (#408), pages 404 dédiées (#374), 2 écarts UI comblés avec tests (échéances d'assurance, commandes d'achat #409), AUDITOR vérifié lecture seule en E2E (#411), Vitest 233. **Révision du 11 nov (base 2bc1b7d)** : les deux formes de refus d'accès direct sont harmonisées en une forme canonique unique testée (`<AccessDenied />`, 17 points / 10 fichiers, écart n°2 résolu #413). Toujours : offline HSE/OT uniquement, Android physique jamais testé, recherche globale absente. |
| Exploitation DevOps/SRE | 15 | 11 | **14** | **Nouveau** : workflow `release-images` (GHCR + Cosign keyless + provenance SLSA mode=max + SBOM) — le build/push d'images n'est plus manuel (#376) ; **Dependabot actif et démontré** (20+ PR fusionnées : pip groupé, npm groupé, actions ×, caddy, node, gitleaks v3 — #377–#399). **Révision du 11 nov** : runbook SRE de recette staging consolidé et versionné (`docs/ops/RECETTE_STAGING_VALIDATION.md` — audit lecture seule A1–A8, dry-run, protocoles RPO/RTO, éprouvetage des alertes) ; l'exécution sur l'hôte réel reste la preuve attendue. Restent : publication de couverture, métriques/SLO continus, exercice d'alerte réel. |
| Commercialisation SaaS | 10 | 2 | **2** | Aucun changement : espace PLATFORM_ADMIN (sociétés, suspension, santé) + provisioning tenant transactionnel restent le seul actif. 0 table/endpoint plans, quotas, abonnements, facturation, support, onboarding, réversibilité. |
| **Total** | **100** | **68** | **76** | Progression entièrement adossée à des preuves vérifiables (§2 et §4) ; aucun point pour une validation terrain ou opérationnelle, toujours absente. |

**Décision correspondante :** le gain +8 (puis +2 sur la révision `2bc1b7d`) mesure la **qualité et la profondeur de vérification du produit**, pas une maturité opérationnelle. Le verdict du `GO_NO_GO.md` est donc inchangé : GO pilote conditionnel (8 prérequis tous non levés), GO commercial impossible avant le chantier SaaS (§4.6) et les validations réelles.

## 4. Analyse par domaine

### 4.1 Sécurité et isolation — 17/20

**Prouvé (statique + exécution locale + CI) :** RLS activée **et forcée** sur 75 tables (`0001_foundation.py`), `mf_app` non-superuser/non-BYPASSRLS vérifié au démarrage et après restauration ; contexte tenant en un seul module transactionnel (whitelist fermée, `test_architecture.py`) ; RBAC deny-by-default généré du YAML vers les tests (concordance route↔permission, refus 403 audité, portée site, objets étrangers en 404) ; refresh rotatif anti-rejeu ; MFA TOTP chiffré AES-256-GCM à enrôlement forcé pour les rôles sensibles ; cookies HttpOnly/SameSite=Strict avec vérification d'Origin ; argon2id ; limiteurs persistés avec clé HMAC dédiée (`MF_RATE_LIMIT_KEY`, #374) ; journal append-only partitionné ; Gitleaks v3 + Bandit (high/high) en CI.

**Corrigés/ajoutés depuis le 9 nov (tous testés, CI verte) :** écran « Mes sessions » avec révocation de ses propres sessions, des autres sessions et révocation administrative TENANT_ADMIN — permissions `identity.session.revoke_own/any` implémentées, indiscernabilité 404 hors tenant (#375) ; `/openapi.json` et `/docs` fermés en production (#374) ; tranche R8 de recette négative (IDOR inter-tenant, 429, traçabilité audit) verte sur serveur réel (#405) ; Dependabot actif sur pip/npm/docker/actions (#376, bumps #377–#399 dont caddy 2.11.9).

**Partiel / à traiter (P1) :** rotation de secrets non outillée.

**Absent / risque (inchangé) :** aucun audit de sécurité indépendant (bloquant commercial) ; revue juridique géolocalisation/données salariés en Guinée non engagée (bloquant pilote).

### 4.2 Fiabilité et résilience — 14/20

**Prouvé :** job CI `backup-restore` (dump → GPG → rclone → checksum → restauration isolée → smoke) ; `verify-restore.sh` avec gates RLS fail-closed ; release staging exige une sauvegarde < 1 h et rollback applicatif automatique ; sondes + alertes SMTP crash-safe (11 suites ops) ; **images de release signées et publiées par CI** (Cosign keyless, SLSA mode=max, SBOM — #376) avec manifestes n'acceptant que des digests ; **la recette a détecté et permis de corriger 2 défauts réels** (RLS post-commit #403 ; GRANT UPDATE manquant → 500 sur le réapprovisionnement #410, migration additive 0064 + régression).

**Partiel / absent (inchangé, bloquants GO pilote) :** restauration jamais exécutée depuis un coffre **externe réel** ; RPO/RTO jamais mesurés ; alertes jamais éprouvées par incident réel ; pas de métriques continues ; exercice release→rollback non attesté sur staging isolé ; pas de healthcheck Docker `api`/`web` (les sondes applicatives compensent partiellement).

**Tests nécessaires :** exercice R1 réel avec mesure RPO/RTO ; injection d'incident d'alerte ; `staging-release.sh` dry-run puis apply sur staging (lecture seule d'abord — règle « pas d'apply sans approbation »).

### 4.3 Fonctionnalités métier — 16/20

**Prouvé :** 79 tables / 232 routes couvrant parc, affectations, missions/pesées (corrections, annulations, quatre-yeux), GMAO corrective + préventive, pièces (CMP, réservations concurrentes, réappro avec décision séparée, BC depuis demande approuvée), pneus, carburant (double validation, anomalies), HSE (incidents, actions correctives double regard, inspections), RH terrain, coûts complets, contrats/assurances/échéances, indicateurs, fiabilité. La règle « la GPS n'est jamais une preuve de tonnage » reste appliquée et testée.

**Nouveau depuis le 9 nov :** recette API R1–R10 sur serveur réel (#400–#407) ; 7 specs E2E navigateur d'actions en CI (#408 socle, #410 actions, #411 assurance) — les actions critiques sont désormais prouvées **depuis l'interface**, pas seulement par l'API ; onglets UI comblés (#409).

**Partiel (inchangé) :** GPS temps réel complet (carte, géofences, alertes, SSE) mais registre d'adaptateurs limité à `minefleet-json-v1`, **aucun matériel certifié** (verrouillé par test) ; offline limité à la déclaration HSE + notes d'OT ; cycle documentaire juridique (dépôt→vérification→soumission→décision) impossible en E2E sans harnais S3/ClamAV (écart documenté `RECETTE_UI_P0.md` §4) ; réconciliation stockage légal, gabarits de checklist, géofences (création/désactivation), politique GPS, partages téléphone et actions de coûts restent sans spec E2E dédiée.

**Absent (inchangé) :** couche SaaS commerciale (§4.6), exports Excel/PDF avancés, IA.

### 4.4 UX/UI et offline — 13/15

**Prouvé :** interface 100 % française, GNF, fuseaux, états standardisés avec `request_id`, pagination/filtres, responsive E2E (360 px, cibles ≥ 44 px), MFA bloquant ; **garde-fou E2E d'accès direct : 34 routes × 13 rôles ne montrent ni « Page introuvable » ni « Erreur inattendue » et jamais de donnée non autorisée** (#408) ; page 404 dédiée (#374) ; échéances d'assurance et commandes d'achat accessibles depuis l'UI avec tests Vitest et E2E (#409, #411) ; AUDITOR vérifié sans formulaire de création (#411) ; offline HSE idempotent éprouvé (build prod, desktop + Pixel 7 émulé).

**Révision du 11 nov (base `2bc1b7d`) — écart n°2 résolu (#413) :** les refus d'accès direct par
pré-contrôle utilisent une forme canonique unique (`<AccessDenied />` — « Vous n'avez pas accès à cette
page. », `role="alert"`) sur 17 points de refus de 10 fichiers de pages ; convention documentée (page non
couverte → « …cette page » ; donnée d'une page autorisée → « …cette information » sur 403 serveur) ; tests
Vitest mis à jour, socle E2E d'accès direct inchangé et vert.

**Partiel / absent (inchangé) :** inspections HSE hors ligne (arbitrage produit en attente) ; tampon GPS téléphone volatile (assumé) ; **Android physique jamais testé** ; recherche globale absente.

### 4.5 Exploitation DevOps/SRE — 14/15

**Prouvé :** `ci.yml` (ruff/mypy, migrations peuplées, pytest + RLS `--cov-fail-under=85`, pip-audit, contrat OpenAPI diff, anti-dérive ×2, npm audit, build, smoke) ; `e2e-isolation.yml` (isolation tenant, parcours démo par rôle, actions métier navigateur) ; `security-static.yml` ; **`release-images.yml` : build + push GHCR + Cosign keyless + SLSA mode=max + SBOM** (#376) ; **Dependabot actif et effectif** (groupes pip/npm, actions, caddy, node — 20+ fusions) ; scripts ops durcis ; 5 timers systemd ; images non-root avec labels (commit + tête Alembic).

**Révision du 11 nov :** runbook SRE de recette staging consolidé et versionné
(`docs/ops/RECETTE_STAGING_VALIDATION.md`) : prérequis/interdits, audit lecture seule A1–A8 (versions,
Alembic, images/signatures, canaries RLS, HTTPS, comptes, routes, logs), dry-run `plan`, protocoles RPO/RTO
et d'éprouvetage des alertes, modèle de rapport. **La procédure est publiée, pas exécutée** : aucune preuve
terrain n'en découle.

**Absent (reste) :** publication de la couverture de tests ; métriques/SLO continus (Prometheus…) ; exécution réelle du runbook (phases A–D) et exercice d'alerte réel.

### 4.6 Commercialisation SaaS — 2/10

**Prouvé (inchangé) :** espace PLATFORM_ADMIN distinct (sociétés, suspension/réactivation, santé) ; provisioning tenant transactionnel ; connexion plateforme à MFA ; seeds de démo refusés en production.

**Absent (0 table, 0 endpoint — inchangé) :** plans et quotas, abonnements (essai/activation/renouvellement/suspension), facturation (factures, avoirs, taxes, exports), tooling support, onboarding guidé, réversibilité client, SLA. Aucun moyen de paiement intégré (conforme à la règle « pas d'intégration non approuvée »).

**Conséquence :** GO commercial structurellement impossible avant les lots SaaS 1→4 de la mission, à lancer après (ou en préparation neutralisée du) GO pilote ; aucun tarif avant coût-servi et entretiens clients.

## 5. Matrice comptes/rôles/menus/routes

La matrice (14 rôles × 31 menus × routes UI × 118 permissions × 232 routes API) reste générée mécaniquement (`docs/qa/ROLE_PAGE_ACTION_MATRIX.md`, anti-dérive `--check` vert le 2026-11-11). Le socle E2E #408 vérifie désormais **en navigateur** l'accès direct 34 routes × 13 rôles et l'isolement de PLATFORM_ADMIN. Écart connu assumé : tranches `maintenance.preventive.*` marquées `later` dans le YAML alors qu'implémentées (harmonisation à faire).

## 6. Inconnues explicites (restent inconnues)

1. ~~État CI du HEAD~~ **levée** : CI vérifiée par API le 2026-11-11 — `main@e36ab33` : 3/3 workflows verts ; PR #400→#411 toutes fusionnées.
2. **Staging OVHcloud** : non accessible depuis cet environnement (état réel des conteneurs, révision Alembic, volumes, proxy partagé à revérifier sur place ; tout `apply` exige une approbation explicite).
3. **Matériel GPS** : aucun modèle/firmware certifié ; compatibilités annoncées interdites par test.
4. **Android physique et réseau guinéen réel** : jamais testés (l'émulation Playwright n'est pas une preuve terrain).
5. **RPO/RTO réels** : non mesurés (coffre externe jamais exercé).
6. **Conformité juridique** : aucun avis professionnel (juriste guinéen requis).

## 7. Priorisation des prochains travaux

**P0 (bloquants GO pilote — inchangés, exigent l'accès staging/coffre/matériel) :** coffre externe réel + RPO/RTO mesurés ; exercice staging release→rollback→vérifications (R2) ; isolation A/B en recette réelle ; revue juridique ; essai traceur physique (protocole `GPS_FOURNISSEUR_CAHIER.md`) ; essai Android réel ; SLO GPS p95/p99 ; éprouvetage des alertes par incident.

**P1 (chantiers de code autorisés dans cet environnement, dans l'ordre) :**
1. ~~Harmoniser les deux formes de refus d'accès direct~~ **fait** — PR #413 (`<AccessDenied />` canonique, 17 points / 10 fichiers, Vitest + socle E2E verts).
2. Étendre les specs E2E d'actions restantes : réconciliation stockage légal, gabarits de checklist HSE, géofences (création/désactivation), politique GPS + notifications, partages téléphone, échéances documents (cas métier), préventif, fiabilité atelier, commandes de pièces (E2E au-delà de Vitest), actions de coûts.
3. Harnais S3/ClamAV pour le cycle documentaire juridique en E2E (écart n°1, seul écart ouvert de `RECETTE_UI_P0.md` §4).
4. ~~Procédure de validation staging en lecture seule + dry-run~~ **fait** — `docs/ops/RECETTE_STAGING_VALIDATION.md` (l'exécution des phases A–D sur l'hôte réel exige un accès staging et, pour C/D, une approbation explicite).
5. Rejouer `MATURITY_SCORECARD.md`, recalibrer `FUNCTIONAL_COVERAGE.md`, harmoniser les tranches `later` du YAML.
6. Étendre l'offline aux inspections HSE (après arbitrage produit).

**P2 (préparation SaaS, sans moyen de paiement ni tarif) :** conception plans/quotas (Starter, Business, Mining Pro, Enterprise **candidats**), schéma abonnements, facturation paramétrable (GNF, taxes), support/onboarding — migrations et tests d'abord, PR verticales séparées.

## 8. Registre des documents exigés

| Document | État |
|---|---|
| `docs/audit/COMMERCIAL_READINESS_CURRENT.md` | **mis à jour** (présente révision, base `2bc1b7d`, score 76/100) |
| `docs/qa/GO_NO_GO.md` | **mis à jour** (11 novembre 2026, verdict inchangé, preuves actualisées) |
| `docs/ops/RECETTE_STAGING_VALIDATION.md` | **créé** — runbook staging lecture seule + dry-run + protocoles RPO/RTO/éprouvetage ; exécution réelle à faire |
| `docs/qa/ROLE_PAGE_ACTION_MATRIX.md` | généré, anti-dérive vert |
| `docs/qa/RECETTE_UI_P0.md` | à jour (écart n°2 résolu par #413 ; reste l'écart n°1 : harnais S3/ClamAV) |
| `docs/audit/preuves/` | **rafraîchi** (pytest 5 207, vitest 233, tsc, build, anti-dérive, ruff, format, mypy — datés 2026-11-11) |
| `docs/qa/REGRESSION_EVIDENCE.md` | absent — à créer lors du premier exercice de non-régression formel sur staging |
| `docs/security/OPEN_RISKS.md` | absent — risques dispersés (SEC-01/02, REL-01, GPS-01/02, OFF-01, OPS-01/02) |
| `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` | absent — après exercice R1 réel |
| `docs/product/COMMERCIAL_OFFERS.md` | absent — offres candidates sans tarifs (`COMMERCIAL_LAUNCH_PLAN.md`) |
| `docs/product/PILOT_ACCEPTANCE.md` | absent — `CRITERES_GO_PILOTE.md` + `INDUSTRIAL_ACCEPTANCE_TESTS.md` (scénarios non exécutés) |
