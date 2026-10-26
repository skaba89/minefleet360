# Revue QA de la tranche 1a — MINEFLEET 360

Auteur : ingénieur QA/DevOps. Date : 2026-10-26. Périmètre : code, tests, CI, scripts, migrations de la tranche 1a (US-1.01 à 1.10, 1.26, 1.27, 1.28, 1.31, 1.32). Les fichiers 1b en cours (`backend/alembic/versions/0005_fleet.py`, `0006_workforce.py`, `backend/app/fleet`, `backend/app/workforce`) sont hors périmètre ; leurs effets sur les mesures sont signalés (QA1A-01).

Aucun fichier autre que celui-ci n'a été modifié.

## 1. Commandes réellement exécutées et résultats

| Commande (dans le conteneur `api`, base `minefleet_test`) | Résultat observé |
|---|---|
| `pytest -q -p no:warnings .` (1re exécution, avant l'apparition des fichiers 1b) | `674 passed in 60.14s` |
| `pytest -q -p no:warnings --cov=app --cov-branch --cov-report=term-missing .` (2e exécution, avec 0005/0006 présents) | `1 failed, 673 passed in 68.83s` ; échec : `tests/test_database.py::test_dbt40_every_table_is_global_or_tenant_scoped_with_forced_rls` (tables `vehicle_category_template` et une autre table 1b sans RLS forcée/tenant) |
| `ruff check .` | 1 erreur : E501 dans une migration 1b (`INSERT INTO vehicle_category_license_category ...`), ligne trop longue. Le fichier de config ignore E501 sous `alembic/**` : voir QA1A-01 |
| `ruff format --check .` | `59 files already formatted` |
| `mypy app` | `Success: no issues found in 45 source files` |

Non exécuté : `pip-audit` (réseau), build d'image Docker de la CI, workflow GitHub Actions (jamais exécuté), scripts PowerShell `dev-up.ps1` / `migrate.ps1` / `test.ps1` (lecture seule), test de migration avec données, tests de charge.

### Couverture de code mesurée (pytest-cov 6.0.0, 2e exécution, avec fichiers 1b présents)

- Total toutes sources : **87 %** (2024 instructions, 208 non couvertes ; 320 branches, 66 branches partielles) ; lignes seules : 89,7 %.
- Hors `app/fleet` (0 %, 67 instructions, code 1b sans test) : lignes seules ≈ **92,8 %** (1816 / 1957). C'est le chiffre représentatif de la 1a.
- Seuil STRATEGIE_QUALITE_CI §1.5 : ≥ 80 % global (atteint) ; branches ≥ 90 % sur `authz` et `identity`. Branches/lignes par module : `authz/matrix.py` 84 %, `authz/principal.py` 86 % (lignes 26, 48, 68-71 non couvertes), `authz/dependencies.py` 96 %, `identity/service.py` 88 % (lignes 197-218, 295-315 non couvertes), `identity/auth_service.py` 94 %. Le seuil de 90 % de branches n'est donc pas démontré pour `authz` (matrix 84 %, principal 86 %) ni pour `identity/service.py` (88 %). Les chiffres par module incluent lignes et branches combinées (`--cov-branch`).
- Modules faibles : `app/cli.py` 63 % (lignes 27-29, 80-92, 96), `app/core/clock.py` 59 %, `app/core/errors.py` 72 %, `app/organization/service.py` 75 % (nombreux chemins d'erreur et de suspension), `app/audit/contracts.py` 88 %.
- Le chiffre n'est pas une preuve de qualité (voir §3).

## 2. Constats QA1A-xx

### Bloquants

**QA1A-01 — Les tests de la tranche 1a ne passent plus sur l'arbre de travail courant à cause des migrations 1b non commitées (bloquant pour toute fusion, hors périmètre à corriger ici).**
`backend/tests/conftest.py:37-38` rejoue `downgrade base` puis `upgrade head` : tout fichier Alembic ajouté entre dans la suite 1a. Avec 0005/0006, `test_dbt40` (`backend/tests/test_database.py:56-74`) échoue et `ruff check` signale un E501 dans la migration 0005 (la config `pyproject.toml:51-53` ne l'ignore que pour `alembic/**`, le chemin réellement linté est donc à vérifier : l'erreur apparaît malgré tout). Risque : CI rouge, 1a non livrable seule. Correction : l'équipe 1b doit soit classer les tables de référence globales (`vehicle_category_template`, `license_category_ref`) dans `GLOBAL_TABLES` (`test_database.py:22`) de façon motivée, soit leur appliquer la RLS ; corriger la ligne trop longue ; ne pas fusionner 1b sans ces correctifs. Gravité conservée : tant que ce n'est pas réglé, la barrière « 1a verte » n'est pas reproductible.

**QA1A-02 — La CI n'a jamais été exécutée et ne mesure pas la couverture ; la barrière de couverture annoncée (≥ 80 %, STRATEGIE §1.5) n'existe pas.**
`.github/workflows/ci.yml:56-57` lance `pytest -q -p no:warnings` sans `--cov` ni `--cov-fail-under`, alors que `pytest-cov==6.0.0` est déjà dans `pyproject.toml:23`. Correction : `pytest -q -p no:warnings --cov=app --cov-branch --cov-fail-under=80 --cov-report=xml` et publier le rapport en artefact. Risque : régression de couverture silencieuse (cliquet non appliqué).

### Majeurs

**QA1A-03 — Aucune vérification de dérive de migration ni de cycle up/down/up avec données.**
La seule exécution de `downgrade base`/`upgrade head` est la fixture `conftest.py:37-38`, sur base vide. Pas de `alembic check` (modèles vs schéma), pas de test que chaque `downgrade()` d'une révision est réversible individuellement, pas de migration avec données. Les rollbacks documentés (STRATEGIE §4.3) ne sont donc pas prouvés. Correction : test `alembic upgrade head` → `downgrade -1` → `upgrade head` pour chaque révision, plus `alembic check` en CI ; ajouter ces étapes à `ci.yml`. Non testé aujourd'hui.

**QA1A-04 — Écarts CI vs STRATEGIE_QUALITE_CI.md §4.1/4.2.**
`ci.yml` n'a ni `concurrency` (§4.1), ni actions épinglées par empreinte de commit (`ci.yml:34-35` : `actions/checkout@v4`, `setup-python@v5`, tags mobiles), ni gitleaks, ni build d'image/hadolint/Trivy, ni `alembic check`, ni contrôle OpenAPI exporté vs fichier versionné (contrat), ni import-linter, ni tâche CRLF (`eol-check`). Une seule tâche monolithique : une panne de lint masque les résultats de tests. Correction : découper en jobs `lint-back`, `test-integration`, `migrations`, `build-images`, `security-deps`, `security-secrets`. D-24 indique que la CI distante dépend d'un dépôt non choisi : l'écart doit au moins figurer dans LIVRAISON_TRANCHE_1A.md comme non couvert.

**QA1A-05 — Fragilité de l'amorçage CI avec `PGHOST` distant (`ci.yml:45-50`, `infra/db/init/00_bootstrap.sh`).**
(a) Le script s'appuie sur le client `psql` du runner : présent sur `ubuntu-24.04` mais non garanti ni épinglé ; aucune installation explicite. (b) Pas de `pg_isready` explicite ; on dépend du `--health-cmd` du service, qui valide avant les étapes (acceptable, mais non vérifié). (c) Script non idempotent (`CREATE ROLE` sans `IF NOT EXISTS`, `CREATE DATABASE`), donc impossible à rejouer sur un service persistant ; correct pour un service éphémère mais fragile en reprise d'étape. (d) Les mots de passe sont injectés via `-v owner_pw=…` : visibles dans la liste des processus du runner ; risque faible sur runner éphémère, à documenter. (e) Les variables `MF_OWNER_PASSWORD` etc. sont écrites dans `$GITHUB_ENV` avant masquage ; GitHub ne masque pas des valeurs écrites ainsi : ajouter `echo "::add-mask::$v"`. (f) Aucune des étapes n'a été exécutée : non testé.

**QA1A-06 — Couverture des critères d'acceptation incomplète (voir §3) : plusieurs critères de sécurité n'ont aucun test.**
Principaux manques : US-1.27 A3 (rollback si l'audit échoue), US-1.27 A4 (logs structurés sans secret), US-1.04 A8 (échec d'envoi d'e-mail), US-1.05 A5 (limite sur jetons invalides), US-1.08 A3 par source IP et audit du verrouillage, US-1.10 A4 (limite des demandes de réinitialisation), US-1.31 A5 (criticité élevée vérifiée), US-1.32 A1/A3 (pas de secret dans logs/audit ; rôle `mf_app`), US-1.01 A7 (atomicité) et A5 (refus audité).

**QA1A-07 — Test de concurrence US-1.31 A4 faible et potentiellement flaky (`backend/tests/test_identity.py:157-181`).**
Deux threads sur le même `TestClient` session-scope partagé (non garanti thread-safe), pas de barrière de synchronisation : les deux requêtes peuvent s'exécuter séquentiellement, auquel cas le test passe sans exercer le verrou. L'assertion `sorted(results.values())[1] in (403, 409)` accepte aussi 403 (perte de droit) et masque l'absence de 409 `LAST_TENANT_ADMIN`. Correction : `threading.Barrier(2)` avant l'appel, un client par thread, boucler N fois, et accepter exactement `{200, 409}`.

**QA1A-08 — État global muté dans un test (`backend/tests/test_auth.py:180-186`).**
`settings.refresh_grace_period = grace * 0` modifie le singleton `get_settings()` ; le `finally` restaure, mais un test parallèle (pytest-xdist, non utilisé aujourd'hui) casserait. Préférer `monkeypatch.setattr` ou une horloge injectable (déjà prévue par `app/core/clock.py`, couverte à 59 % seulement). Le même singleton `client`/`api` de session partage la plateforme et le cache `_platform` (conftest) : dépendance d'ordre implicite si l'admin plateforme est suspendu ou son jeton révoqué.

### Mineurs

**QA1A-09 — Tests tautologiques ou de portée étroite.**
- `test_architecture.py:22-28` : `organization.count("set_tenant_context(") == 2` est un compteur de chaînes fragile (casse au premier refactor légitime) ; `test_no_raw_delete_statements` (l.39-41) ne détecte que `delete(` en minuscule, pas `DELETE FROM` en SQL brut.
- `test_auth.py:282-285` (nom « expired_or_forged ») ne teste ni jeton expiré, ni jeton forgé correctement signé ; seulement trois en-têtes invalides.
- `test_organization_audit.py:385-390` : un 405 n'est vérifié que pour trois méthodes sur une route ; ne prouve pas l'absence de route d'écriture (couvert en revanche par ST-01).
- `test_database.py:105-110` : `dbt01` ne vérifie le zéro ligne qu'après création d'un tenant, correct, mais sans contexte vide explicite pour `tenant` (table lisible via `app.login_tenant_code`).

**QA1A-10 — Données partagées et non nettoyées.** `conftest.py:1-6` : aucune suppression entre tests (conception voulue : `mf_app` sans DELETE). Conséquence : `test_isolation_*` utilisent `total` d'audit d'un tenant dédié (OK) mais la base grossit à chaque session ; la fixture `database` détruit tout au début uniquement. Pas de flakiness observée sur deux exécutions complètes (une seule exécution a réussi intégralement : 674 ; la 2e a eu un seul échec attribuable à 1b). Stabilité sur N exécutions non mesurée.

**QA1A-11 — Scripts Windows (`scripts/*.ps1`) non testés.** `scripts/test.ps1` utilise `docker compose exec api` (exige la pile démarrée) alors que la commande de référence utilise `run --rm --no-deps` : divergence ; `test.ps1` n'exécute ni la couverture ni les migrations ; `dev-up.ps1:11-17` écrit `.env` sans vérifier la fin de ligne ni les droits ; `migrate.ps1` et `test.ps1` n'ont pas de garde `$LASTEXITCODE` pour `migrate`. `PGHOST`/CRLF : `.gitattributes` existe mais aucune vérification `eol-check` en CI. Aucun script n'a été exécuté dans cette revue.

**QA1A-12 — Pas de `.dockerignore` racine ni analyse d'image.** `backend/.dockerignore` existe ; le Dockerfile exécute `USER mf` (bien) mais aucune vérification `HEALTHCHECK`/`/health/ready` dans les tests ni en CI. Build d'image CI non vérifié.

**QA1A-13 — Écart de dépendances.** `pip-audit==2.7.3` est installé sans lockfile (STRATEGIE §4.1 : « lockfiles obligatoires ») ; les dépendances sont épinglées dans `pyproject.toml` mais pas leurs transitives ; le cache pip est indexé sur `pyproject.toml` (acceptable à défaut de lockfile).

## 3. Couverture des critères d'acceptation (stories 1a)

Légende : OK = test existant qui vérifie le critère ; PARTIEL = vérifié en partie ; MANQUANT = aucun test ; N/A 1b = dépend d'entités de la tranche 1b.

| Story / critère | Test | Statut |
|---|---|---|
| US-1.01 A1 (201, copie catalogue, invitation, audit, transaction) | `conftest.Api.tenant`, `test_us127_*` | PARTIEL : copie du catalogue (D-18) non vérifiée (N/A 1b) |
| US-1.01 A2, A3 | `test_us101_duplicates_and_reserved_codes` | OK |
| US-1.01 A4 | idem (code hors format) | PARTIEL : e-mail invalide, champs manquants, erreurs par champ non testés |
| US-1.01 A5 (403 + audit) | matrice ST-02 + `test_st02_denials_are_audited` | PARTIEL : audit du refus vérifié seulement pour `audit.event.read` |
| US-1.01 A6 | `test_us101_a6_platform_admin_has_no_business_access` | OK |
| US-1.01 A7 (atomicité) | — | MANQUANT |
| US-1.32 A1 | `conftest.database` (création) | PARTIEL : audit écrit et absence de secret dans log/audit non vérifiés |
| US-1.32 A2 | `test_us132_platform_admin_bootstrap_refused_twice` | OK (code de sortie 3) |
| US-1.32 A3 (rôle `mf_app`) | — | MANQUANT |
| US-1.32 A4 | `test_us108_a2`, `test_us104_role_and_scope_rules` (PLATFORM_ADMIN refusé) | OK |
| US-1.02 A1 | `test_us102_suspension_revokes_existing_sessions` | OK |
| US-1.02 A2 | `test_us108_a2` (tenant suspendu) | PARTIEL : audit de l'événement non vérifié |
| US-1.02 A3 | matrice ST-02 | OK |
| US-1.02 A4 | `test_us102_*` (reconnexion) | OK |
| US-1.02 A5 (suspendre le tenant plateforme) | — | MANQUANT |
| US-1.03 A1 | `test_us103_site_update_*`, fixture | PARTIEL : fuseau par défaut `Africa/Conakry` non assertionné |
| US-1.03 A2 | `test_us103_sites_unique_per_tenant_and_validation` | PARTIEL : le même code dans T2 est testé avec un code différent (`S1x`), pas avec le même code |
| US-1.03 A3 | idem | OK |
| US-1.03 A4 | — | N/A 1b (véhicules/conducteurs) |
| US-1.03 A5 | matrice ST-02 (OPS_MANAGER, HR) | OK |
| US-1.03 A6 | isolation générée | OK |
| US-1.03 A7 | `test_ct4_*` sur `/users` | PARTIEL : `If-Match` sur sites non testé |
| US-1.04 A1 | `test_us104_invite_creates_invited_account_and_audits` | PARTIEL : jeton non logué et non listé non vérifiés ; expiration `INVITATION_TTL` non testée |
| US-1.04 A2 | `test_us104_duplicate_email_same_tenant_is_409_case_insensitive` | OK |
| US-1.04 A3 | `test_us108_a4_*` | OK (aucune divulgation non vérifiée) |
| US-1.04 A4 | `test_isolation_foreign_reference_in_body_is_422`, `role_and_scope_rules` | OK |
| US-1.04 A5, A6 | `test_us104_role_and_scope_rules` | OK |
| US-1.04 A7 | matrice ST-02 | OK |
| US-1.04 A8 (échec d'envoi) | — | MANQUANT |
| US-1.05 A1 | `test_us105_*`, `Api.activate` | PARTIEL : audit non vérifié |
| US-1.05 A2 | `test_us105_*` (réutilisé, falsifié, tenant étranger) | PARTIEL : jeton expiré réel non testé |
| US-1.05 A3 | `test_us105_*` | OK |
| US-1.05 A4 (tenant suspendu) | — | MANQUANT |
| US-1.05 A5 (429) | — | MANQUANT |
| US-1.06 A1 | `test_us106_a3_*`, fixture `world` | PARTIEL (A2 N/A 1b) |
| US-1.06 A3 | `test_us106_a3_grants_are_union_of_assignments` | OK |
| US-1.06 A4 | matrice ST-02 (POST d'affectation) | N/A 1b |
| US-1.06 A5 | `test_us106_a5_duplicate_assignment_is_409` | OK |
| US-1.06 A6 | matrice ST-02 | OK (audit non vérifié) |
| US-1.06 A7 | isolation générée | OK |
| US-1.06 A8 | `test_us106_a8_*`, `test_us107_*` | OK |
| US-1.06 A9 | `test_us104_role_and_scope_rules` (PLATFORM_ADMIN) | PARTIEL : via invitation seulement, pas via `POST /role-assignments` |
| US-1.31 A1 | `test_us131_a1_*` | OK |
| US-1.31 A2 | `test_us131_admin_can_remove_another_admin_*` | PARTIEL : le 409 `LAST_TENANT_ADMIN` n'est jamais observé |
| US-1.31 A3 | idem | PARTIEL (même raison) |
| US-1.31 A4 | `test_us131_a4_*` | PARTIEL, voir QA1A-07 |
| US-1.31 A5 (criticité élevée) | — | MANQUANT (le code existe : `identity/service.py:185,396`) |
| US-1.31 A6 | — | non testable (procédure d'exploitation) |
| US-1.07 A1, A5 | `test_us107_*` | OK |
| US-1.07 A2 | — | MANQUANT directement (voir A2/A3 de 1.31) |
| US-1.07 A3 | `test_us131_admin_can_remove_another_admin_*` | OK |
| US-1.07 A4 | isolation générée | OK |
| US-1.07 A6 | matrice ST-02 | OK |
| US-1.08 A1 | `test_login_success_sets_httponly_refresh_cookie` | PARTIEL : audit de la connexion non vérifié |
| US-1.08 A2 | `test_us108_a2_identical_401_for_all_failure_causes` | OK (le plus solide : sept cas, corps identiques) |
| US-1.08 A3 | `test_us108_a3_rate_limited_after_max_failures` | PARTIEL : limite par source, durée de verrouillage, audit non testés |
| US-1.08 A4 | `test_us108_a4_*` | OK |
| US-1.08 A5 | `test_expired_or_forged_access_token_is_401` | PARTIEL : session expirée réelle non testée |
| US-1.08 A6 (UI) / A7 | — | hors 1a (UI) / sans objet |
| US-1.09 A1, A3 | `test_us109_*` | OK |
| US-1.09 A2 (UI), A4 (audit) | — | A2 hors 1a ; A4 MANQUANT |
| US-1.10 A1 | `test_us110_password_reset_flow_revokes_sessions` | PARTIEL : même corps testé, mais pas le cas compte `DISABLED`/tenant suspendu |
| US-1.10 A2 | idem | OK (audit non vérifié) |
| US-1.10 A3 | idem (réutilisation) | PARTIEL : expiré/inconnu non testés |
| US-1.10 A4 (429) | — | MANQUANT |
| US-1.26 A1 | `test_us126_*`, `world` | PARTIEL : filtres période/acteur/type/site et pagination `page_size` non vérifiés ; fuseau d'affichage non testé |
| US-1.26 A2, A3 | `test_us126_audit_readable_by_admin_and_auditor_only`, matrice | OK |
| US-1.26 A4 | isolation générée, `test_isolation_lists_never_include_other_tenant` | OK |
| US-1.26 A5 | matrice | OK |
| US-1.26 A6 | `test_dbt30_*`, `test_dbt44_*`, `test_us126_no_write_route_on_audit` | OK (trigger vérifié) |
| US-1.26 A7 | `test_us126_a7_*` | PARTIEL : numéro de permis N/A 1b ; jeton hors audit non vérifié |
| US-1.26 A8 | — | MANQUANT |
| US-1.26 A9 | `test_us101_a6_*` | OK |
| US-1.27 A1 | `test_us127_each_write_produces_exactly_one_business_event` | PARTIEL : un seul endpoint (site.create) ; pas de balayage de toutes les écritures |
| US-1.27 A2 | `test_st02_denials_are_audited` | PARTIEL : refus audité pour une seule route ; log de sécurité 404 non testé |
| US-1.27 A3 | `test_us127_a3_failed_write_leaves_no_trace` | PARTIEL : teste l'échec métier, pas l'échec d'audit |
| US-1.27 A4 | — | MANQUANT |
| US-1.28 A1, A2 | `test_isolation_foreign_object_is_indistinguishable_from_missing` | OK pour les routes 1a |
| US-1.28 A2 (corps) | `test_isolation_foreign_reference_in_body_is_422` | PARTIEL : une seule route |
| US-1.28 A3 | `test_isolation_tenant_id_in_body_is_rejected` | PARTIEL : une seule route |
| US-1.28 A4 | `test_dbt10_*` | OK |
| US-1.28 A5 | `test_dbt01_*`, `test_dbt02_*` | OK |
| US-1.28 A6 | `test_isolation_lists_never_include_other_tenant` | PARTIEL : le `total` n'est pas comparé ; compteurs et recherches absents |
| US-1.28 A7 | génération depuis `authz_matrix.yaml` | OK localement ; CI distante non exécutée |

## 4. Points positifs vérifiés

Les tests s'exécutent sur PostgreSQL réel avec le rôle `mf_app` non propriétaire (`test_dbt08`), la RLS forcée est inventoriée automatiquement (`test_dbt40`), les trois suites ST-01/ST-02/isolation sont générées depuis la matrice (aucun oracle écrit à la main), l'indiscernabilité 404 (objet étranger vs inexistant) est testée par comparaison de corps, les données de test sont fictives (`example.com`, `+224000000…`). 674 tests passés avant l'arrivée de 1b ; lint, format et mypy propres sur le code 1a.

## 5. Tests manquants priorisés

P0 (sécurité, avant pilote) :
1. US-1.27 A3 : l'échec d'écriture d'audit annule l'écriture métier (injecter une erreur dans `audit/contracts.py`).
2. US-1.31 A2/A3 : provoquer réellement le 409 `LAST_TENANT_ADMIN` (via concurrence déterministe ou état construit par le propriétaire) ; durcir QA1A-07.
3. US-1.05 A5 et US-1.10 A4 : limitation sur jetons invalides et demandes de réinitialisation ; US-1.08 A3 par source.
4. US-1.01 A7 / US-1.32 A3 : atomicité de création de tenant ; la commande d'amorçage utilise `mf_app`.
5. Test de migration up/down/up par révision et `alembic check` (QA1A-03).

P1 :
6. US-1.27 A1 : balayage de toutes les routes d'écriture 1a, exactement un `audit_event` par opération réussie.
7. US-1.04 A8 (échec d'envoi) et A1 (jeton absent des logs et des listes) ; US-1.27 A4 (logs structurés sans secret, présence de `request_id`).
8. US-1.05 A4, jeton expiré (horloge injectée), US-1.08 A5 session expirée.
9. US-1.31 A5 (criticité élevée), US-1.02 A5 (garde tenant plateforme), US-1.06 A9 via `POST /role-assignments`.
10. US-1.26 A1 : filtres et pagination ; A8 log technique de consultation.
11. US-1.28 A2/A3 : généraliser aux corps de toutes les routes d'écriture ; A6 total et recherches.

P2 : If-Match sur sites, fuseau par défaut `Africa/Conakry`, US-1.03 A2 avec même code dans T2, test CLI d'amorçage (couverture `cli.py` 63 %), `errors.py` et `clock.py`.

Faults GPS hors ligne, tests de contrat OpenAPI exporté, E2E Playwright, charge : hors 1a, **non testés et non couverts**.

## 6. Recommandations de suite

1. Faire passer la CI localement puis distante : ajouter couverture avec seuil, `alembic check`, build d'image, gitleaks.
2. Régler le conflit 1b/`test_dbt40` avant toute fusion de 1b ; ne pas modifier le test 1a sans motivation écrite.
3. Convertir les tests de concurrence en tests déterministes avec barrière.
4. Mettre à jour LIVRAISON_TRANCHE_1A.md : indiquer le chiffre de couverture réel (87 % brut, 92,8 % hors `app/fleet`) et la liste des critères non testés ci-dessus.
