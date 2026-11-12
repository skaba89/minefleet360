# Readiness commerciale — état courant

**Base auditée :** `main@980b713` (PR #428 fusionnée — fix(saas) : anti-dépassement de quota sous concurrence + tests du cycle de vie quotas/factures, 2026-11-12).
**Audit exécuté :** 12 novembre 2026 — exécutions locales complètes (PostgreSQL 16.10 + PostGIS disponibles) **et** CI GitHub vérifiée via API authentifiée.
**Statut du document :** courant ; remplace la révision du 12 novembre 2026 (base `8d7301b`/PR #426, 82/100) et les révisions antérieures comme référence de décision.
**Verdict :** **NO-GO commercial maintenu — GO conditionnel pilote maintenu** (aucun prérequis terrain du `GO_NO_GO.md` n'est levé ; le tarif n'est pas approuvé). Score de maturité : **83/100** (grille imposée) — 74 à la base `e36ab33` (#412), 77 avec le harnais documentaire (#417), 80 avec les lots SaaS 1→3 (#418–#420), 81 avec les 4 lots complets (#422, #423), 82 avec la preuve navigateur du cycle commercial de bout en bout et 4 défauts d'interface corrigés (#426), **83 avec le défaut réel de course sur les bornes de quota trouvé par l'audit et corrigé + 7 parcours de cycle de vie prouvés (#428)** — en progression de +15 depuis le 9 novembre, entièrement sur des éléments **vérifiés** (code, tests, CI), jamais sur une validation terrain ou opérationnelle.

> **Règle de lecture.** Ce document ne mélange jamais preuve statique (le code existe et est testé), preuve d'exécution (testé ici ou en CI sur infrastructure jetable) et preuve d'exploitation (validé sur environnement réel). Un test CI n'est **pas** une preuve de fonctionnement en conditions réelles. Une inconnue reste explicitement inconnue (§6). Le score est un outil de pilotage interne, jamais une promesse commerciale.

---

## 1. Méthode

| Source | Périmètre | Fiabilité |
|---|---|---|
| Lecture de code (backend 221 fichiers `app/`, frontend, `infra/`, `scripts/`, `.github/`) | architecture, sécurité, RBAC, RLS, CI | élevée |
| Exécution locale complète (sandbox Linux, PostgreSQL 16.10 + PostGIS, Python 3.12 / Node 22) | lint, types, **suite intégrée complète (5 733 tests à la révision #428)**, Vitest, build | élevée |
| CI GitHub (`ci.yml`, `e2e-isolation.yml`, `security-static.yml`, `release-images.yml`, `gps-benchmark-tests.yml`) — vérifiée le 2026-11-11 via API authentifiée | gates de fusion, E2E navigateur sur base éphémère | élevée (infrastructure **jetable** : ne prouve pas l'exploitation réelle) |
| Documents de gouvernance datés (`docs/qa/`, `docs/audit/`, `docs/ops/`) | historique des audits, verdicts | moyenne (non reproductible ici) |
| VPS OVHcloud / staging | exploitation réelle | **non accessible** — inconnue §6.2 |

Hors périmètre de cet audit : matériel GPS réel, Android physique, réseau mobile guinéen réel, données de production, exercice de restauration sur coffre externe réel.

Différence majeure avec la révision précédente : la suite intégrée backend (harnais RLS/authz sur PostgreSQL réel) est **désormais exécutée localement de bout en bout** (5 207 tests, contre 360 unitaires seuls au 9 novembre), et l'état CI est **vérifié** (l'inconnue §6.1 de la révision précédente est levée).

## 2. Preuves d'exécution locale et CI (audit exécuté sur `e36ab33`, révisé jusqu'à la PR #417)

**Révisions post-exécution (vérifiées, aucune re-exécution requise — pas de code produit concerné) :** PR #412
(documentation d'audit et GO/NO-GO), PR #413 (forme canonique du refus d'accès direct, `<AccessDenied />`,
17 points de refus / 10 fichiers, Vitest mis à jour), PR #415 (extension E2E navigateur : zones de site
et politique GPS + notifications — spec `e2e/gps-zones-policy.spec.ts`), PR #416 (extension E2E navigateur :
taux horaires de main-d'œuvre et réconciliation du stockage documentaire en chemin dégradé — spec
`e2e/costs-reconciliation.spec.ts`) et PR #417 (harnais E2E S3/ClamAV — faux serveur S3 HTTPS et faux clamd
INSTREAM dans `scripts/dev/` + API éphémère dédiée dans `e2e-isolation.yml` + spec
`e2e/legal-document-cycle.spec.ts` qui joue le cycle documentaire complet sur serveur réel : dépôt, scan
EICAR refusé, vérification DIRECTION, soumission, décision UI, réconciliation nominale — aucune
modification du code produit) ; CI `main` vérifiée par API au moment des fusions. Le runbook de recette
staging (`docs/ops/RECETTE_STAGING_VALIDATION.md`, PR #414) est publié après cette exécution : procédure pure,
aucune exécution terrain. PR #425 : protocole de pilote fermé documenté (aucun code).

**Révision du 12 novembre après midi (base `8d7301b`, PR #426) — preuve d'exécution nouvelle :** la spec
E2E `frontend/e2e/saas-lifecycle.spec.ts` joue **depuis le navigateur** le cycle commercial complet — plan
tarifé et borné créé en UI, société provisionnée, abonnement essai puis activation, facture préremplie
depuis le tarif du plan puis émission (détail figé vérifié), vue support plateforme, checklist de
démarrage vérifiée aux jalons **1/5 → 2/5 → 5/5**, refus `QUOTA_EXCEEDED` affiché à la borne `max_sites`,
lecture société `/abonnement` + `/factures`, **export réversibilité téléchargé et vérifié en contenu**
(aucun attribut d'authentification). Exécutée localement (1/1, 19,8 s) **et en CI** (job `tenant-isolation`,
4 min 59 s). La recette a **révélé et permis de corriger 4 défauts d'interface réels** : le formulaire des
plans n'exposait ni tarif mensuel GNF ni période (le cycle « plan tarifé → facture préremplie » était
impossible depuis l'UI) ; libellés d'état anglais ou d'accord faux sur le formulaire de facture (`ACTIVE`
brut) et la vue support (statuts d'abonnement au féminin, statuts de facture bruts). Vitest 260/260,
`tsc` strict OK, build OK, anti-dérive ×2 verte.

**Révision du 12 novembre soir (base `980b713`, PR #428) — défaut réel trouvé et corrigé :** l'audit du code
d'application des quotas (Phase 2 de la mission) a révélé un **défaut de course « lire puis écrire »** dans
`ensure_quota` : deux provisionnements concurrents disposant d'un seul emplacement restant pouvaient passer le
contrôle ensemble et porter l'usage au-delà de la borne du plan. Correctif : verrou consultatif de transaction
`pg_advisory_xact_lock` à clé déterministe (société, champ), pris avant la lecture de la borne et libéré au
commit avec l'écriture qu'il protège — les 4 sites d'appel l'invitent avant toute écriture (aucun interblocage
possible). **7 tests nouveaux** (`backend/tests/test_billing_lifecycle.py`) prouvent les parcours de cycle de
vie exigés par la Phase 2 : changement d'offre inférieure avec ressources supérieures au nouveau quota
(**aucune suppression automatique**, création suivante refusée à la borne, retour d'offre supérieure sans
restauration, historique conservé), suspension (borne maintenue) et réactivation (borne effective), essai
expiré (statut effectif `EXPIRED` — borne appliquée, aucune purge), **course réelle PostgreSQL** (2 créations
concurrentes, borne 1 → exactement `[201, 422]`), numérotation de factures sous concurrence (2 numéros
`MF-…` distincts), arrondi de taxe demi-unité supérieure et immutabilité d'une facture finalisée (aucune
route de modification, `VOIDED` terminal). Suite intégrée complète rejouée localement : **5 733 passés** en
8 min 05 s ; CI de la PR **9/9 verte** (`backend` 11 min 29 s avec couverture ≥ 85, `tenant-isolation`
5 min 13 s, `demo-journeys` 7 min 53 s). Aucune migration, aucun changement de contrat d'API.

| Contrôle | Résultat | Périmètre |
|---|---|---|
| `ruff check .` + `ruff format --check .` | 0 erreur, 469 fichiers formatés | backend complet |
| `mypy app` | Succès, 221 fichiers | backend |
| `pytest -q -x` (MF_ENV=test, base `minefleet_test`) | **5 733 passés** (révision #428, 8 min 05 s), 43 avertissements — 5 207 à la révision #426 | **suite intégrée complète** (RLS, authz, concurrence, migrations) |
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
3. Défaut de course « lire puis écrire » sur l'application des quotas — deux provisionnements concurrents pouvaient franchir la borne du plan (jamais couvert par les tests existants, tous séquentiels) — trouvé par l'audit du code, corrigé par verrou consultatif de transaction (société, champ) + test de régression par course PostgreSQL réelle (PR #428).

## 3. Tableau de bord de maturité (grille imposée)

| Domaine | Pondération | Score (9 nov) | Score (12 nov, #426) | Score (12 nov, #428) | Justification synthétique |
|---|---:|---:|---:|---:|---|
| Sécurité et isolation | 20 | 16 | **17** | **17** | RLS forcée sur 75 tables, RBAC machine (118 permissions / 232 routes) testé deny-by-default, MFA chiffré, refresh rotatif anti-rejeu, audit append-only. **Nouveau depuis le 9 nov** : écran « Mes sessions » + révocations `identity.session.revoke_own/any` (#375, 7 tests d'intégration + 3 Vitest), OpenAPI/docs fermés en production (#374, +7 tests), clé HMAC rate-limit dédiée du secret JWT (#374, +6 tests), tranche R8 (IDOR, 429, audit) verte. Restent : audit indépendant, avis juridique, rotation de secrets outillée. |
| Fiabilité et résilience | 20 | 13 | **14** | **14** | Restauration chiffrée testée en CI avec gates RLS fail-closed ; release/rollback par digest immuables ; **images de release signées Cosign + SLSA + SBOM publiées par CI** (#376). La recette a **prouvé sa capacité à attraper 2 bugs réels** (#403, #410) — le dispositif de vérification fonctionne. Restent non mesurés : RPO/RTO sur coffre externe réel, exercice release→rollback sur staging, éprouvetage des alertes par incident réel. |
| Fonctionnalités métier | 20 | 15 | **17** | **17** | Périmètre inchangé (79 tables / 232 routes) mais **profondeur de preuve accrue** : 10 tranches de recette API R1–R10 sur serveur réel (#400–#407), **10 specs E2E navigateur d'actions métier** en CI (correction/annulation de pesée, réappro quatre-yeux, acquittement GPS, zones/politique GPS/notifications, HSE double regard, contrats, tenants plateforme, police d'assurance, taux horaires, **cycle documentaire juridique complet sur harnais S3/ClamAV — dépôt, scan EICAR refusé, vérification, soumission, décision, réconciliation nominale**, #410/#411/#415/#416/#417). Le cycle documentaire n'est plus bloqué côté serveur ; reste l'exposition UI du dépôt/vérification/soumission. Toujours : aucun traceur certifié, offline limité à HSE/OT. |
| UX/UI et offline | 15 | 11 | **13** | **13** | **Nouveau** : socle E2E d'accès direct 34 routes × 13 rôles — « jamais Page introuvable ni Erreur inattendue » (#408), pages 404 dédiées (#374), 2 écarts UI comblés avec tests (échéances d'assurance, commandes d'achat #409), AUDITOR vérifié lecture seule en E2E (#411), Vitest 233. **Révision du 11 nov (base 2bc1b7d)** : les deux formes de refus d'accès direct sont harmonisées en une forme canonique unique testée (`<AccessDenied />`, 17 points / 10 fichiers, écart n°2 résolu #413). Toujours : offline HSE/OT uniquement, Android physique jamais testé, recherche globale absente. |
| Exploitation DevOps/SRE | 15 | 11 | **14** | **14** | **Nouveau** : workflow `release-images` (GHCR + Cosign keyless + provenance SLSA mode=max + SBOM) — le build/push d'images n'est plus manuel (#376) ; **Dependabot actif et démontré** (20+ PR fusionnées : pip groupé, npm groupé, actions ×, caddy, node, gitleaks v3 — #377–#399). **Révision du 11 nov** : runbook SRE de recette staging consolidé et versionné (`docs/ops/RECETTE_STAGING_VALIDATION.md` — audit lecture seule A1–A8, dry-run, protocoles RPO/RTO, éprouvetage des alertes) ; l'exécution sur l'hôte réel reste la preuve attendue. Restent : publication de couverture, métriques/SLO continus, exercice d'alerte réel. |
| Commercialisation SaaS | 10 | 2 | **7** | **8** | **Produit SaaS complet (4 lots sur 4 + lot 2b), sans moyen de paiement ni tarif approuvé** : référentiel plans/quotas plateforme avec API + UI `/plateforme/plans` (#418) ; cycle de vie abonnement TRIAL→ACTIVE→SUSPENDED↔/CANCELLED avec essai daté, historique plateforme et page société `/abonnement` (#419) ; facturation paramétrable DRAFT→ISSUED→VOIDED en GNF avec taxe en points de base, numérotation plateforme atomique `MF-<année>-<numéro>`, montants figés, lignes immuables, API société en lecture seule, UI `/plateforme/facturation` + `/factures`, statut effectif d'essai expiré calculé à la lecture (#420) ; **quotas appliqués au provisionnement** — 4 points de contrôle (POST /users, /sites, /vehicles, /vehicles/{id}/gps/tracker), refus 422 `QUOTA_EXCEEDED` détaillé, désactivation/réforme/révocation libèrent la place (#422) ; **outillage support** — vue consolidée d'exploitation d'un compte (`/platform/tenants/{id}/overview` : usage vs limites, abonnement avec statut effectif, comptes utilisateurs, factures récentes, UI `/plateforme/support`) ; **parcours client guidé** — checklist de démarrage calculée depuis l'état réel (aucune persistance), UI `/demarrage` ; **réversibilité** — export JSON journalisé sans aucun secret, réservé TENANT_ADMIN, bouton sur `/abonnement` (#423). **Nouveau (#426) : le cycle commercial est prouvé de bout en bout depuis le navigateur** (plan tarifé → société → abonnement → facture émise → support → onboarding 5/5 → quota appliqué à la borne → export réversibilité vérifié en contenu), exécuté en CI, avec **4 défauts d'interface révélés et corrigés** (dont l'absence de saisie du tarif du plan, bloquante du cycle depuis l'UI). 127 permissions / 255 routes, suite 5 733 pytest / 260 Vitest. **Nouveau (#428) : les bornes de quota sont désormais contraignantes même sous opérations concurrentes** — défaut réel de course « lire puis écrire » trouvé par l'audit et corrigé par verrou consultatif (société, champ) ; **7 parcours de cycle de vie prouvés par tests** (downgrade sans suppression automatique + retour d'offre supérieure + historique conservé, suspension avec borne maintenue, réactivation avec borne effective, essai expiré avec borne appliquée et aucune purge, course PostgreSQL réelle (2 créations concurrentes pour 1 emplacement → exactement un succès et un refus 422), numérotation de factures concurrente unique, arrondi de taxe demi-unité supérieure, immutabilité d'une facture finalisée sans aucune route de modification). **Reste (aucun code) :** tarif approuvé (arbitrage métier coût-servi + entretiens), suivi de règlement « payé » et export PDF éventuels (arbitrage expert-comptable), SLA/contrat (juridique), validations réelles. |
| **Total** | **100** | **68** | **82** | **83** | Progression entièrement adossée à des preuves vérifiables (§2 et §4) ; aucun point pour une validation terrain ou opérationnelle, toujours absente. Le +1 du 12 novembre après midi (#426) récompense la profondeur de preuve (cycle commercial navigateur en CI) et 4 défauts réels corrigés — pas un document de plus. Le +1 du 12 novembre soir (#428) récompense un défaut réel d'application des bornes trouvé par l'audit et corrigé, avec course PostgreSQL de régression — toujours aucun point terrain. |

**Décision correspondante :** le gain +8 (puis +3 sur les révisions du 11 novembre : #413/#414, #417, puis +3 sur les lots SaaS 1→3 : #418–#420, puis +1 sur la clôture des 4 lots : #422, #423, puis +1 sur la preuve navigateur du cycle commercial : #426, puis +1 sur la correction du défaut réel de course des bornes de quota : #428) mesure la **qualité et la profondeur de vérification du produit**, pas une maturité opérationnelle. Le verdict du `GO_NO_GO.md` est donc inchangé : GO pilote conditionnel (8 prérequis tous non levés) ; le GO commercial n'est plus structurellement impossible (le produit SaaS est complet côté logiciel) mais reste bloqué sur le tarif approuvé, le contrat/SLA et les validations réelles (§4.6) — aucun de ces trois restes n'est un chantier de code.

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

### 4.3 Fonctionnalités métier — 17/20

**Prouvé :** 79 tables / 232 routes couvrant parc, affectations, missions/pesées (corrections, annulations, quatre-yeux), GMAO corrective + préventive, pièces (CMP, réservations concurrentes, réappro avec décision séparée, BC depuis demande approuvée), pneus, carburant (double validation, anomalies), HSE (incidents, actions correctives double regard, inspections), RH terrain, coûts complets, contrats/assurances/échéances, indicateurs, fiabilité. La règle « la GPS n'est jamais une preuve de tonnage » reste appliquée et testée.

**Nouveau depuis le 9 nov :** recette API R1–R10 sur serveur réel (#400–#407) ; 10 specs E2E navigateur d'actions en CI (#408 socle, #410 actions, #411 assurance, #415 zones/politique/notifications, #416 coûts/réconciliation dégradée, #417 cycle documentaire complet sur harnais) — les actions critiques sont désormais prouvées **depuis l'interface**, pas seulement par l'API ; onglets UI comblés (#409).

**Partiel (inchangé) :** GPS temps réel complet (carte, géofences, alertes, SSE) mais registre d'adaptateurs limité à `minefleet-json-v1`, **aucun matériel certifié** (verrouillé par test) ; offline limité à la déclaration HSE + notes d'OT ; **le cycle documentaire juridique est désormais prouvé sur serveur réel** (harnais S3/ClamAV, #417) mais ses actions de dépôt/vérification/soumission restent à exposer dans `/juridique` ; réconciliation stockage légal couverte sur ses deux chemins (dégradé #416, nominal #417), gabarits de checklist, partages téléphone et échéances documents (cas métier) restent sans spec E2E dédiée.

**Absent (inchangé) :** exports Excel/PDF avancés, IA. *(La couche SaaS commerciale est désormais partiellement couverte — voir §4.6.)*

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

### 4.6 Commercialisation SaaS — 8/10

**Prouvé (4 lots + lot 2b, vérifiés par tests et anti-dérive) :**
- **Lot 1 — plans/quotas (#418)** : `saas_plan` (référentiel plateforme, hors RLS), 5 quotas (users, sites, véhicules, traceurs GPS, rétention docs ; NULL = illimité), API `/platform/saas-plans` (POST/GET/ETag/PATCH If-Match, code immuable, RETIRED terminal, 403 garanti pour tout rôle tenant), UI `/plateforme/plans`.
- **Lot 2 — abonnements (#419)** : `tenant_subscription` RLS, un seul abonnement vivant par société (index unique partiel), TRIAL→ACTIVE→SUSPENDED↔/CANCELLED, souscription plateforme avec bascule de contexte RLS, historique paginé, lecture société `/tenant/subscription` (TENANT_ADMIN/DIRECTION/FINANCE/AUDITOR), UI `/plateforme/abonnements` + `/abonnement`.
- **Lot 3 — facturation paramétrable (#420)** : `billing_invoice` + `billing_invoice_line` (RLS, lignes immuables, `montant = quantité × prix` vérifié en base), tarif mensuel GNF paramétrable du plan, taxe en points de base, numérotation plateforme atomique `MF-<année>-<numéro>`, cycle DRAFT→ISSUED→VOIDED (terminal), montants figés (un changement de tarif ne modifie pas une facture émise — testé), API société lecture seule (`/tenant/invoices`), UI `/plateforme/facturation` + `/factures`, statut effectif d'essai expiré calculé à la lecture (aucun scheduler) ; 3 nouveaux codes d'erreur au catalogue.
- **Lot 2b — quotas appliqués au provisionnement (#422)** : les limites du plan sont réellement contraignantes — 4 points de contrôle avant écriture (`POST /users`, `/sites`, `/vehicles`, `/vehicles/{id}/gps/tracker`), refus 422 `QUOTA_EXCEEDED` avec détail `{field, limit, usage}` ; les comptes désactivés, véhicules réformés et traceurs révoqués libèrent la place (testé) ; sans abonnement vivant ni tarif NULL aucune régression (zéro refus pour la plateforme et les sociétés de démonstration).
- **Lot 4 — support/onboarding/réversibilité (#423)**, aucune migration : vue support consolidée plateforme (`GET /platform/tenants/{id}/overview` — usage vs limites, abonnement avec statut effectif, comptes utilisateurs, 5 dernières factures ; permission `organization.tenant.support` ; UI `/plateforme/support`) ; parcours de démarrage guidé (`GET /tenant/onboarding` — 5 étapes calculées depuis l'état réel, rien à cocher, progression 20 % → 100 % testée par actions réelles ; UI `/demarrage`) ; réversibilité (`GET /tenant/export` — JSON complet journalisé `tenant.export`, sans aucun attribut d'authentification — testé, réservé TENANT_ADMIN, téléchargement authentifié sur `/abonnement`).

**Toujours conforme à la règle « pas d'intégration non approuvée » :** aucun moyen de paiement, aucun provider, aucun encaissement — la facture est un document interne de traçabilité, le règlement se gère hors application.

**Absent (reste avant GO commercial — aucun des trois restes n'est un chantier de code) :** tarification approuvée (le tarif est un paramètre saisi, pas une offre validée par coût-servi + entretiens clients) ; suivi de règlement (« payé ») et export PDF éventuels (arbitrage expert-comptable) ; SLA/contrat (juridique) ; aucune validation pilote.

**Conséquence :** le produit SaaS est **complet côté logiciel** (4 lots sur 4, quotas réellement appliqués, outillage support, onboarding et réversibilité livrés et testés) et **le cycle complet est désormais prouvé depuis l'interface navigateur en CI** (#426) — le GO commercial n'est plus structurellement impossible et n'attend plus de fonctionnalité, mais trois décisions non techniques (tarif approuvé, contrat/SLA, arbitrage règlement/PDF) et les validations réelles du `GO_NO_GO.md`.

**Révision du 12 novembre soir (#428) :** l'application des bornes est désormais **sûre sous concurrence** (défaut de course corrigé et prouvé par une course PostgreSQL réelle) et les parcours de **changement d'offre, suspension/réactivation et expiration** sont prouvés par tests — les 7 variants listés au §7 (P1 item 7 de la révision précédente) sont couverts côté pytest, sans aucune suppression automatique de données lors d'un changement d'offre (règle respectée et testée). Les avoirs restent **hors périmètre documenté** (VOIDED terminal sert d'annulation) et l'export comptable reste subordonné à l'arbitrage expert-comptable — aucun des deux n'est un chantier de code à ce stade.

## 5. Matrice comptes/rôles/menus/routes

La matrice (14 rôles × menus × routes UI × 127 permissions × 255 routes API) reste générée mécaniquement (`docs/qa/ROLE_PAGE_ACTION_MATRIX.md`, anti-dérive `--check` vert le 2026-11-12). Le socle E2E #408 vérifie désormais **en navigateur** l'accès direct 34 routes × 13 rôles et l'isolement de PLATFORM_ADMIN. Écart connu assumé : tranches `maintenance.preventive.*` marquées `later` dans le YAML alors qu'implémentées (harmonisation à faire).

## 5bis. Matrice des écarts de validation (phase 1 de la feuille de route)

Statuts : ✅ prouvé ; ⚠️ partiel ; ❌ absent ; INCONNU non évaluable depuis cet environnement. « Staging » désigne le VPS OVHcloud (jamais accessible) ; « Terrain » désigne matériel réel Guinée ; « Commercial » désigne l'offre validée (tarif, contrat, SLA).

| Fonctionnalité | Code présent | CI | E2E | Staging | Terrain | Commercial | Risque | Action suivante |
|---|---|---|---|---|---|---|---|---|
| Cycle SaaS complet (plan→société→abonnement→facture→support→onboarding→quota→export) | ✅ | ✅ (pytest 5 733, cycle de vie inclus #428) | ✅ navigateur (#426) | ❌ | ❌ | ❌ tarif/contrat | faible (logiciel) ; élevé (offre) | exécuter la même séquence sur staging avec données fictives (après phases A/B) |
| Quotas appliqués au provisionnement | ✅ | ✅ refus UI à la borne (#426) ; **concurrence sérialisée, course réelle `[201, 422]` (#428)** | ✅ refus UI à la borne (#426) | ❌ | ❌ | ❌ | faible | constat terrain au pilote (protocole §3) |
| Isolation multi-tenant (RLS/RBAC/IDOR) | ✅ | ✅ (5 726 pytest + E2E 34×13) | ✅ | ❌ | ❌ | ✅ (exigence produit) | élevé si dérive | suite croisée A/B sur la recette réelle (GO n° 3) |
| GPS temps réel (carte, SSE, zones, alertes) | ✅ | ✅ (recette GPS bout en bout) | ✅ | ❌ | ❌ INCONNU (aucun traceur) | ❌ | élevé | essai traceur physique (`docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`) puis SLO p95/p99 |
| Offline-first (HSE/OT) | ✅ | ✅ (build prod émulé) | ⚠️ émulateur | ❌ | ❌ INCONNU | — | moyen | essai Android réel (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`) ; extension offline inspections (arbitrage produit) |
| Sauvegarde/restauration | ✅ | ✅ round-trip synthétique | — | ❌ INCONNU (coffre externe jamais exercé) | — | ❌ SLA | élevé | exercice R1 (`docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md`) avec RPO/RTO |
| Release/rollback staging | ✅ | ✅ (plan + images signées) | — | ❌ INCONNU (apply jamais exécuté) | — | — | élevé | phases A/B lecture seule (`docs/ops/PLAN_EXECUTION_STAGING.md`) puis C/D avec approbation |
| Supervision/alertes | ✅ | ✅ (11 suites ops) | — | ❌ INCONNU | — | ❌ SLA | moyen | éprouvetage par incident réel (runbook §Alerte) |
| Juridique GPS/salariés | ⚠️ contrôles de code | — | — | ❌ | ❌ | ❌ | **bloquant pilote** | revue par un professionnel du droit guinéen (hors code) |
| Tarification/contrat/SLA | ⚠️ tarif = paramètre | — | — | — | — | ❌ | **bloquant commercial** | coût-servi + entretiens + validation juridique (hors code) |

Lecture : la colonne CI/E2E mesure la profondeur de preuve **logicielle** ; aucune validation staging/terrain n'est comptabilisée car jamais exécutée — les verdicts du `GO_NO_GO.md` en découlent inchangés.

## 6. Inconnues explicites (restent inconnues)

1. ~~État CI du HEAD~~ **levée** : CI vérifiée par API le 2026-11-11 — `main@e36ab33` : 3/3 workflows verts ; PR #400→#411 toutes fusionnées.
2. **Staging OVHcloud** : non accessible depuis cet environnement (état réel des conteneurs, révision Alembic, volumes, proxy partagé à revérifier sur place ; tout `apply` exige une approbation explicite). Le **plan d'exécution lecture seule** est publié (`docs/ops/PLAN_EXECUTION_STAGING.md`) : il séquence les phases A/B, artefacts et critères d'interruption — l'exécution reste à faire.
3. **Matériel GPS** : aucun modèle/firmware certifié ; compatibilités annoncées interdites par test. Le **protocole d'essai physique** est publié (`docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`) : banc L1–L9, mesures terrain T1–T10, matrice de qualification par modèle.
4. **Android physique et réseau guinéen réel** : jamais testés (l'émulation Playwright n'est pas une preuve terrain). Le **protocole d'essai Android** est publié (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`) : matrice 2 appareils × 10 scénarios.
5. **RPO/RTO réels** : non mesurés (coffre externe jamais exercé). Le **protocole de restauration externe** est publié (`docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md`) : 14 contrôles, incidents simulés, modèle de preuve R1.
6. **Conformité juridique** : aucun avis professionnel (juriste guinéen requis).

## 7. Priorisation des prochains travaux

**P0 (bloquants GO pilote — inchangés, exigent l'accès staging/coffre/matériel ; protocoles désormais prêts) :** coffre externe réel + RPO/RTO mesurés (`docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md`) ; exercice staging release→rollback→vérifications (R2) — phases A/B préparées par `docs/ops/PLAN_EXECUTION_STAGING.md` ; isolation A/B en recette réelle ; revue juridique ; essai traceur physique (`docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`) ; essai Android réel (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`) ; SLO GPS p95/p99 ; éprouvetage des alertes par incident (runbook staging §Alerte).

**P1 (chantiers de code autorisés dans cet environnement, dans l'ordre) :**
1. ~~Harmoniser les deux formes de refus d'accès direct~~ **fait** — PR #413 (`<AccessDenied />` canonique, 17 points / 10 fichiers, Vitest + socle E2E verts).
2. Étendre les specs E2E d'actions restantes : ~~réconciliation stockage légal~~ **fait en chemin dégradé** (PR #416, `e2e/costs-reconciliation.spec.ts` — 503 annoncé sans stockage privé ; le chemin nominal dépend du harnais S3, item 3), gabarits de checklist HSE, ~~géofences (création/désactivation), politique GPS + notifications~~ **fait** (PR #415, `e2e/gps-zones-policy.spec.ts`), partages téléphone, échéances documents (cas métier), préventif, fiabilité atelier, commandes de pièces (E2E au-delà de Vitest), ~~actions de coûts~~ **fait** (PR #416 — taux horaires, seule action en écriture de `/couts`).
3. ~~Harnais S3/ClamAV pour le cycle documentaire juridique en E2E~~ **fait** — PR #417 (`scripts/dev/fake_s3.py` + `fake_clamd.py`, API :8001 dédiée dans `e2e-isolation.yml`, spec `e2e/legal-document-cycle.spec.ts` verte localement) ; **reste l'exposition UI** du dépôt/vérification/soumission dans `/juridique` (écart restant de `RECETTE_UI_P0.md` §4).
4. ~~Procédure de validation staging en lecture seule + dry-run~~ **fait** — `docs/ops/RECETTE_STAGING_VALIDATION.md` (l'exécution des phases A–D sur l'hôte réel exige un accès staging et, pour C/D, une approbation explicite).
5. Rejouer `MATURITY_SCORECARD.md`, recalibrer `FUNCTIONAL_COVERAGE.md`, harmoniser les tranches `later` du YAML.
6. Étendre l'offline aux inspections HSE (après arbitrage produit).
7. ~~Parcours plateforme restants sans E2E dédié : changement d'abonnement (upgrade/downgrade avec ressources existantes supérieures au nouveau quota), suspension/réactivation d'abonnement~~ **fait côté pytest** — PR #428 (7 tests `backend/tests/test_billing_lifecycle.py` : downgrade **sans aucune suppression automatique** + retour d'offre supérieure + historique conservé, suspension avec borne maintenue, réactivation avec borne effective, essai expiré avec borne appliquée, course PostgreSQL réelle `[201, 422]`, numérotation concurrente unique, arrondi de taxe, immutabilité d'une facture finalisée) ; le chemin nominal complet reste joué en E2E navigateur (#426). **Avoirs : hors périmètre documenté** (VOIDED terminal sert d'annulation) et **export comptable** : subordonné à l'arbitrage expert-comptable — aucun des deux n'est un chantier de code à ce stade.

**P2 (préparation SaaS, sans moyen de paiement ni tarif) :** ~~plans/quotas~~ **fait** (PR #418), ~~schéma abonnements~~ **fait** (PR #419), ~~facturation paramétrable (GNF, taxes)~~ **fait** (PR #420), ~~application des quotas au provisionnement (lot 2b)~~ **fait** (PR #422), ~~support/onboarding/réversibilité (lot 4)~~ **fait** (PR #423) ; **reste** : suivi de règlement et export PDF éventuels (après arbitrage) — PR verticales séparées.

## 8. Registre des documents exigés

| Document | État |
|---|---|
| `docs/audit/COMMERCIAL_READINESS_CURRENT.md` | **mis à jour** (présente révision, base PR #428, score 83/100, matrice des écarts §5bis) |
| `docs/qa/GO_NO_GO.md` | **mis à jour** (12 novembre 2026 soir — verdict inchangé, preuves PR #428, classement des blocants inchangé) |
| `docs/ops/RECETTE_STAGING_VALIDATION.md` | à jour (runbook staging lecture seule + dry-run + protocoles RPO/RTO/éprouvetage) ; exécution réelle à faire |
| `docs/ops/PLAN_EXECUTION_STAGING.md` | **créé** (#427) — plan d'exécution séquencé des phases A/B lecture seule (S0–S10, artefacts, critères d'interruption) |
| `docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md` | **créé** (#427) — protocole d'exercice R1 (14 contrôles, incidents simulés, preuve datée) |
| `docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md` | **créé** (#427) — banc L1–L9, terrain T1–T10, matrice de qualification par modèle |
| `docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md` | **créé** (#427) — 2 appareils × 10 scénarios, mesures et limites consignées |
| `docs/ops/PROTOCOLE_PILOTE.md` | à jour (2026-11-12) — exécution conditionnée aux 8 prérequis terrain |
| `docs/qa/ROLE_PAGE_ACTION_MATRIX.md` | généré, anti-dérive vert |
| `docs/qa/RECETTE_UI_P0.md` | à jour (écart n°1 reformulé : cycle documentaire prouvé sur harnais #417, reste l'UI du dépôt/vérification/soumission ; écart n°2 résolu par #413) |
| `docs/audit/preuves/` | **rafraîchi** (pytest 5 207, vitest 233, tsc, build, anti-dérive, ruff, format, mypy — datés 2026-11-11) |
| `docs/qa/REGRESSION_EVIDENCE.md` | absent — à créer lors du premier exercice de non-régression formel sur staging |
| `docs/security/OPEN_RISKS.md` | absent — risques dispersés (SEC-01/02, REL-01, GPS-01/02, OFF-01, OPS-01/02) |
| `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` | absent — après exercice R1 réel |
| `docs/product/COMMERCIAL_OFFERS.md` | absent — offres candidates sans tarifs (`COMMERCIAL_LAUNCH_PLAN.md`) |
| `docs/product/PILOT_ACCEPTANCE.md` | absent — `CRITERES_GO_PILOTE.md` + `INDUSTRIAL_ACCEPTANCE_TESTS.md` (scénarios non exécutés) |
