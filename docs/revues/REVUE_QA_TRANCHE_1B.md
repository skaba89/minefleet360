# Revue QA de la tranche 1b — MINEFLEET 360

Auteur : ingénieur QA/DevOps. Date : 2026-10-26. Périmètre : `backend/app/fleet`, `backend/app/workforce`, migrations `0005_fleet.py` et `0006_workforce.py`, `backend/tests/test_fleet_workforce.py`, extension 1b de `backend/tests/test_authz_matrix.py` (commits f7ad86f et 6544deb). Référentiels : `docs/USER_STORIES.md` (US-1.11 à US-1.21), `docs/LIVRAISON_TRANCHE_1B.md`, `docs/STRATEGIE_QUALITE_CI.md`. Les constats de `REVUE_QA_TRANCHE_1A.md` ne sont pas répétés (QA1A-03, 04, 05, 10 restent ouverts et s'appliquent aussi à la 1b).

Seul ce fichier a été écrit. Aucun code ni test n'a été modifié ; `.env` n'a pas été lu (il n'est passé qu'en argument `--env-file` à `docker compose`).

## 1. Commandes réellement exécutées et résultats

| Commande | Résultat observé |
|---|---|
| Création d'une base jetable via le conteneur `db` (utilisateur postgres du conteneur) : `CREATE DATABASE minefleet_qa_test OWNER mf_owner`, puis REVOKE/GRANT, extensions `postgis`, `btree_gist`, `citext`, schéma `app`, copie des GRANT de `infra/db/init/00_bootstrap.sh` | Succès |
| `docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps -e MF_ENV=test -e MF_DB_NAME=minefleet_qa_test api pytest -q -p no:warnings --cov=app --cov-branch --cov-report=term-missing` (le code de l'arbre de travail est monté par `../backend:/app`) | **1151 passed in 103.83s**, couverture totale **91 %** (2830 instructions, 179 non couvertes ; 462 branches, 84 partielles) |
| `DROP DATABASE minefleet_qa_test` puis `SELECT datname FROM pg_database` | Base supprimée ; restent `minefleet`, `minefleet_sec`, `minefleet_test`, `postgres`, `template0/1` (aucune base d'un autre agent touchée) |
| Dans le conteneur `api` : `ruff check .` ; `ruff format --check .` ; `mypy app` | `All checks passed!` ; `69 files already formatted` ; `Success: no issues found in 52 source files` |

Écart par rapport à la consigne : la base a été nommée **`minefleet_qa_test`** et non `minefleet_qa`, car `backend/tests/conftest.py:26-29` fait `pytest.exit(..., returncode=2)` si le nom de base ne se termine pas par `_test` (garde voulue, voir QA1B-15). Le nom `minefleet_qa` n'a pas été essayé.

Non exécuté : `pip-audit`, build d'image Docker / hadolint / Trivy, `alembic check`, cycle upgrade/downgrade **avec données** (aucune migration rejouée sur base peuplée), CI distante (jamais exécutée), tests de charge, répétition de la suite pour mesurer la flakiness (une seule exécution complète : stabilité sur N exécutions non mesurée), scripts `.ps1`.

## 2. Couverture réelle des modules 1b (exécution du §1)

| Fichier | Instr. | Non couvertes | Branches / partielles | Couv. (lignes+branches) | Lignes non couvertes |
|---|---|---|---|---|---|
| `app/fleet/service.py` | 147 | 25 | 52 / 7 | **78 %** | 73-74, 155, 157, 159, 166, 227-255, 317 |
| `app/workforce/service.py` | 235 | 31 | 66 / 18 | **82 %** | 61-62, 72, 94->83, 204, 206, 208-209, 227, 229, 272, 276, 309, 325, 402, 410-433, 456, 503, 536, 559->exit, 598 |
| `app/workforce/validity.py` | 18 | 0 | 10 / 0 | 100 % | — |
| `app/fleet/{router,models,schemas,contracts}.py` | 190 | 0 | 2 / 0 | 100 % | — |
| `app/workforce/{router,models}.py` | 115 | 0 | 0 | 100 % | — |
| `app/workforce/schemas.py` | 125 | 2 | 6 / 2 | 97 % | 122, 124 |

Lecture : les routeurs, modèles et schémas sont à 100 % parce que la matrice d'autorisation appelle toutes les routes (réponses 403/404/200 en lecture), pas parce que la logique est testée. La couverture des **services** est de 78 % et 82 %, nettement sous la moyenne globale de 91 %, et le seuil CI de 85 % (global) masque ce retard (QA1B-14). Lignes seules sur les deux services : fleet 83,0 % ((147-25)/147), workforce 86,8 % ((235-31)/235). Ensemble des deux paquets : 830 instructions, 58 non couvertes (93,0 % en lignes). Les lignes non couvertes correspondent à des comportements métier précis, pas à du code mort :

- `fleet/service.py:227-255` : **le chemin heureux entier de `update_vehicle`** (PATCH réussi, audit avant/après, `row_version`) n'est exécuté par aucun test ;
- `workforce/service.py:410-433` : **tout `update_license`** (PATCH d'un permis, dont le passage à `SUSPENDED`/`WITHDRAWN`) ;
- `workforce/service.py:598` : la branche **habilitations** de la liste des échéances ;
- `fleet/service.py:73-74` et `workforce/service.py:61-62` : la levée de `OPEN_ASSIGNMENTS_EXIST` ;
- `workforce/service.py:309, 325, 503, 227-229, 456` : transition de statut identique, `exit_date < hire_date`, révocation d'une habilitation non `VALID`, sous-traitant sans société, site d'habilitation hors portée ;
- filtres de liste (`fleet/service.py:155-166`, `workforce/service.py:204-209`).

Branches/lignes hors 1b observées en passant (déjà connues ou liées) : `core/migration_tools.py` 58 % (la branche de refus de `guard_destructive`, lignes 16-18, n'est jamais exercée), `core/clock.py` 59 % (`FrozenClock` jamais utilisé par un test d'API).

## 3. Couverture des critères d'acceptation (US-1.11 à US-1.21)

Légende : **Test** = un test vérifie le critère ; **Partiel** = une partie seulement (précisée) ; **Manquant** = aucun test ; **N/A** = hors périmètre de la 1b (1c) ou exclu par la story. « Matrice » = test généré de `test_authz_matrix.py` (ST-02 refus 403, lectures autorisées, isolation inter-tenant 404 pour les routes `item`).

Bilan sur 69 critères évalués : **19 Test, 36 Partiel, 14 Manquant**.

| Story | Critère | Statut | Test existant / lacune |
|---|---|---|---|
| 1.11 | A1 liste, libellés FR, permis requis | Partiel | `test_us111_catalog_copied_at_tenant_creation` (15 catégories, 2 mappings permis sur 8, libellés FR non vérifiés) |
| 1.11 | A2 catégorie d'un autre tenant → 404 | Test | même test + matrice (isolation) |
| 1.11 | A3 copie vide / créée à la création | Partiel | création testée (15) ; état vide / anomalie non testé |
| 1.12 | A1 création 201, AVAILABLE, audit, 1re ligne d'historique | Partiel | `test_us112_create_vehicle_and_uniqueness`, `..._references_and_permissions` (OPS SITE S1 → 201) ; événement d'audit non vérifié |
| 1.12 | A2 immatriculation dupliquée, y compris RETIRED, normalisée, autre tenant OK | Partiel | normalisation et autre tenant testés (l.75, 78) ; cas RETIRED absent |
| 1.12 | A3 numéro de parc dupliqué, y compris RETIRED | Partiel | insensible à la casse testé (l.74) ; cas RETIRED absent |
| 1.12 | A4 sans plaque OK, sinon 422 | Partiel | création sans plaque implicite (fixture) ; fleet_number absent/vide → 422 non testé |
| 1.12 | A5 site hors portée / autre tenant → 422 | Partiel | S2 hors portée testé (l.88) ; site d'un autre tenant absent |
| 1.12 | A6 catégorie inexistante / autre tenant → 422 | Test | l.89 (catégorie étrangère) |
| 1.12 | A7 HR/DISPATCHER/DRIVER → 403 audité | Partiel | HR (l.94, code non vérifié) ; autres rôles via matrice ; audit du refus : test générique 1a seulement |
| 1.12 | A8 champs invalides → 422 par champ | Partiel | `model_year=1800` seul (l.95-96, code et champ non vérifiés) |
| 1.12 | A9 soumission répétée → 409 | Partiel | doublon séquentiel ; pas de test concurrent |
| 1.13 | A1 liste paginée dans la portée, total | Partiel | `test_us113_site_scoped_dispatcher` ; aucune pagination multi-pages |
| 1.13 | A2 recherche immatriculation limitée tenant/portée | Partiel | `test_us113_registration_search_is_normalized` ; limitation tenant/portée non assertée |
| 1.13 | A3 UUID autre tenant / autre site → 404 | Test | l.159 + matrice |
| 1.13 | A4 état vide | Manquant | — |
| 1.13 | A5 filtre invalide ou inconnu → 422 | Partiel | paramètre inconnu testé (`test_ct9...`) ; valeur d'énumération invalide (`status=FOO`), UUID mal formé absents |
| 1.13 | A6 `tenant_id` fourni → 422 | Test | `test_ct9_unknown_or_tenant_query_parameters_rejected` |
| 1.13 | A7 HR → 403 | Test | matrice (ST-02) |
| 1.13 | A8 disponibilité dérivée | Manquant | champ absent de `VehicleOut`, aucun test (à rattacher à 1c) |
| 1.14 | A1 PATCH avec `If-Match`, audit avant/après, `row_version` | **Manquant** | `service.py:227-255` jamais exécuté |
| 1.14 | A2 409 `OPEN_ASSIGNMENTS_EXIST` + liste | Manquant | `open_assignments` est un stub (`fleet/service.py:61-67`) ; non testable sans `monkeypatch` |
| 1.14 | A3 motif obligatoire (IMMOBILIZED, OUT_OF_SERVICE, RETIRED) | Partiel | IMMOBILIZED seul (l.103-106) ; OUT_OF_SERVICE et RETIRED sans motif absents |
| 1.14 | A4 changement de site avec affectation → 409 | Manquant | idem A2 |
| 1.14 | A5 RETIRED terminal → 422 | Test | `test_us115_retire_is_terminal_and_hidden_by_default` (l.138-143) |
| 1.14 | A6 `VERSION_CONFLICT` / `IF_MATCH_REQUIRED` | Partiel | `VERSION_CONFLICT` sur `/status` seulement (l.123-126) ; `IF_MATCH_REQUIRED` et PATCH absents |
| 1.14 | A7 autre tenant/site → 404, rôle sans écriture → 403 | Partiel | DISPATCHER S1 : 404 sur véhicule S2, 403 sur PATCH (l.159-165) ; WORKSHOP_CHIEF et OPS SITE hors site absents |
| 1.14 | A8 immatriculation en conflit à la modification → 409 | Manquant | — |
| 1.14 | A9 historique par trigger (ancien, nouveau, motif, auteur) | Partiel | seule la séquence `to_status` est vérifiée, et de façon aveugle à l'ordre (QA1B-05) |
| 1.15 | A1 réforme avec motif, masqué par défaut, filtre, audit | Partiel | masquage/`include_retired` OK ; audit et exclusion des choix d'affectation non vérifiés |
| 1.15 | A2 affectation ouverte → 409 | Manquant | stub (cf. 1.14 A2) |
| 1.15 | A3 réactivation refusée | Test | l.138-141 |
| 1.16 | A1 création HR TENANT/SITE, 201, ACTIVE, audit | Partiel | `test_us116_create_driver_rules`, HR SITE (l.247-248) ; audit non vérifié |
| 1.16 | A2 matricule dupliqué → 409 | Test | l.195-196 |
| 1.16 | A3 site hors portée / autre tenant → 422 | Partiel | uniquement à la **mise à jour** (`test_us117_site_change_needs_scope`) ; création et site d'un autre tenant absents |
| 1.16 | A4 champs hors liste → 422 | Partiel | `date_of_birth` seul sur 6 champs interdits (adresse, photo, pièce d'identité, aptitude médicale, motif de maladie) |
| 1.16 | A5 autres rôles → 403 audité | Test | TENANT_ADMIN (l.199) + matrice pour DISPATCHER/OPS_MANAGER/DRIVER |
| 1.16 | A6 homonyme → `POSSIBLE_DUPLICATE` | Test | l.191-194 (casse et accents) |
| 1.16 | A7 démo fictive | N/A | — |
| 1.17 | A1 HR voit tout | Test | `test_us117_masking_by_role` |
| 1.17 | A2 rôles non HR sans téléphone, sentinelle | Partiel | DISPATCHER, OPS_MANAGER, AUDITOR sur le GET unitaire ; DIRECTION, HSE absents ; **liste `/drivers` jamais testée sous masquage** ; jeu de clés exact non assertionné |
| 1.17 | A3 autre tenant / hors site → 404 ; TENANT_ADMIN → 403 | Partiel | TENANT_ADMIN 403 fiche (l.218), liste via matrice, autre tenant via matrice ; hors site (même tenant) absent |
| 1.17 | A4 `If-Match` obsolète | Manquant | pour les conducteurs |
| 1.17 | A5 changement de site + affectation → 409 | Manquant | stub |
| 1.17 | A6 audit sans valeur sensible | Partiel | `test_restricted_driver_fields_never_valued_in_audit` (employment_type, hire_date) ; marqueur « modifié » du téléphone non vérifié |
| 1.17 | A7 filtre/tri sur le téléphone refusé | Manquant | repose sur D-36 (paramètre inconnu) sans test pour `/drivers` |
| 1.17 | A8 journalisation des lectures sensibles | N/A | exclue (Q19) |
| 1.18 | A1 permis, une ligne par catégorie, validité dérivée | Partiel | VALID/EXPIRED testés ; EXPIRING via API non testé pour un permis ; audit non vérifié |
| 1.18 | A2 expiration ≤ délivrance → 422 | Partiel | égalité testée (l.276-279) ; antérieure absente ; code/champ non vérifiés |
| 1.18 | A3 permis déjà expiré → 201, EXPIRED | Test | l.269-270 |
| 1.18 | A4 doublon → `DUPLICATE_LICENSE` | Test | l.271 |
| 1.18 | A5 renouvellement, historique, plus récent valide | Partiel | 2e permis créé et VALID ; conservation de l'ancien et usage du plus récent pour l'éligibilité non assertés |
| 1.18 | A6 numéro absent des vues non HR, des logs, de l'audit | Partiel | OPS_MANAGER et audit testés (l.287-290) ; DISPATCHER/HSE/AUDITOR, `document_reference`, `status_note`, **logs** non testés |
| 1.18 | A7 rôle non HR → 403 ; autre tenant/hors site → 404 | Partiel | OPS_MANAGER 403 ; TENANT_ADMIN et autre tenant via matrice ; hors site absent |
| 1.18 | A8 bornes au fuseau du site, horloge injectée | Partiel | fonction pure paramétrée (l.358-378) ; câblage API du fuseau du site non testé (QA1B-07) |
| 1.19 | A1 habilitation 201, VALID, audité | Test | l.306-307 (audit non vérifié) |
| 1.19 | A2 habilitation expirée sans éligibilité | Partiel | REVOKED exclu des catégories autorisées (l.323-325) ; cas EXPIRED via API absent |
| 1.19 | A3 catégorie inconnue → 422 | Test | l.326-329 (UUID aléatoire ; catégorie d'un autre tenant absente) |
| 1.19 | A4 chevauchement → `DUPLICATE_QUALIFICATION` | Test | l.308-309 (adjacence et période ouverte absentes) |
| 1.19 | A5 HSE écriture → 403 | Test | l.310-312 |
| 1.19 | A6 autre tenant / hors site → 404 | Partiel | autre tenant via matrice ; hors site absent |
| 1.19 | A7 mapping fictif « à valider localement » | Manquant | marqueur présent seulement en commentaire de migration |
| 1.20 | A1 EXPIRING/EXPIRED, triés, limités à la portée | Partiel | `test_us120_expirations_listed_within_scope` : un permis EXPIRING ; ni EXPIRED, ni tri, ni portée SITE, ni habilitation |
| 1.20 | A2 mise en évidence via conformité 1c | N/A | 1c |
| 1.20 | A3 état vide | Manquant | — |
| 1.20 | A4 aucun accès inter-tenant | Test | l.332-352 (l'autre tenant a une échéance, seule la sienne est vue) |
| 1.20 | A5 rôle sans lecture → 403 | Test | matrice |
| 1.21 | A1 passage INACTIVE avec motif, audit | Partiel | `test_us121_status_change_requires_reason` ; audit non vérifié ; « motif » = `exit_date` (voir QA1B-10) |
| 1.21 | A2 affectation ouverte → 409 | Manquant | stub |
| 1.21 | A3 statut sans motif → 422 | Partiel | INACTIVE seul ; UNAVAILABLE et SUSPENDED absents |
| 1.21 | A4 réactivation : permis/habilitations expirés restent inéligibles | Manquant | — |
| 1.21 | A5 autre tenant/hors site → 404 ; rôle non autorisé → 403 | Partiel | matrice ; hors site absent |

## 4. Constats QA1B-xx

Gravité : **Majeur** = critère ou risque de sécurité/isolation insuffisamment prouvé, à corriger avant la revue 1c ; **Moyen** ; **Mineur**. Aucun constat bloquant : la suite est verte (1151) et les gates lint/types passent.

### Majeurs

**QA1B-01 — Aucun test au niveau base pour les tables 1b (RLS, FK composites, ajout seul, exclusion, CHECK, triggers).**
`backend/tests/test_database.py:119-162, 198-235` n'exerce que `site` et `user_role_assignment` ; seul `test_dbt40` (l.57) touche les tables 1b, et de façon structurelle (RLS forcée présente). Non testé avec `mf_app` et un contexte tenant : lecture/écriture croisée sur `vehicle`, `driver`, `driver_license`, `driver_qualification` ; rejet par FK composite d'une catégorie ou d'un site d'un autre tenant (`fk_vehicle__category`, `fk_dq__category`, `fk_driver__site`) ; `vehicle_status_history` en ajout seul (`tg_vsh_append_only`, pas de GRANT UPDATE/DELETE) ; contrainte d'exclusion `ex_dq_no_overlap` (périodes adjacentes, période ouverte `valid_to NULL`, statut non `VALID` exclu) ; CHECK `ck_vehicle_retired`, `ck_vehicle_reason`, `ck_driver_unavail/suspension/exit` ; trigger d'historique (auteur, motif, une ligne par changement de statut seulement) ; `registration_norm`/`fleet_number_norm`/`serial_key` générées. Risque : une régression de migration ou une politique RLS mal posée sur une table 1b ne serait détectée que si elle casse un parcours API. Correction : ajouter `test_dbt03_dbt04`-like paramétrés sur les tables 1b (`SELECT count(*)` croisé = 0, `UPDATE` = 0 ligne, `INSERT` étranger = 42501), un `test_dbt10` par FK composite, un test de l'historique en ajout seul, un test de l'exclusion.

**QA1B-02 — Le chemin heureux de la modification d'un véhicule et la modification d'un permis ne sont exercés par aucun test.**
`backend/app/fleet/service.py:227-255` (`update_vehicle` : validation des champs obligatoires nuls, contrôle de portée du nouveau site, changement de catégorie, snapshot avant/après, `changed_fields`) et `backend/app/workforce/service.py:410-433` (`update_license` : `PATCH /driver-licenses/{id}`, change `status` en `SUSPENDED`/`WITHDRAWN`, ce qui modifie l'éligibilité). Les seuls PATCH véhicule des tests sont refusés (403, l.165) ou rejetés (réformé, l.142) ; le PATCH de la matrice (`test_authz_matrix.py:26, 37`) est atteint seulement en 403/404. Critères touchés : US-1.14 A1, A4, A8 ; US-1.18 (modification) ; `row_version` non vérifiée. Risque : audit avant/après et unicité à la modification non protégés ; `setattr` sur `fields` (service.py:238-239) accepte tout champ du schéma sans garde supplémentaire. Correction : tests `test_us114_patch_*` (200 + audit `before_data/after_data` + `row_version`+1 + ETag ; conflit d'immatriculation → 409 `DUPLICATE_REGISTRATION` ; champ `null` interdit → 422 ; site hors portée → 422 ; catégorie étrangère → 422) et `test_us118_license_patch_*` (suspension → `validity == "SUSPENDED"` et sortie de la liste des échéances ; numéro non journalisé ; `If-Match`).

**QA1B-03 — Isolation par site (IDOR intra-tenant) quasi non testée pour conducteurs, permis, habilitations, historique et échéances ; les droits d'écriture ne sont jamais testés en positif dans la matrice.**
`test_authz_matrix.py` : `_item_routes()` (l.252-261) teste l'isolation **inter-tenant** avec des personas de portée `TENANT` du tenant B ; `world` (l.66-131) place tous les objets sur S1 et `test_st02_granted_reads_succeed_within_scope` (l.222-238) n'utilise que S1, donc aucun objet d'un **autre site du même tenant** n'est jamais interrogé par un rôle `SITE`. Seul le véhicule a un test hors-site (`test_us113_site_scoped_dispatcher`). Pour les conducteurs : GET/PATCH/status, `/licenses`, `/qualifications`, `/driver-licenses/{id}`, `/driver-qualifications/{id}/revoke`, `/vehicles/{id}/status-history` et la liste des échéances (`workforce/service.py:527-537`, filtrée par `Driver.site_id`) ne sont pas vérifiés hors site. En écriture, `_allowed_reads` se limite aux GET (l.227-229) : aucun test positif pour `OPS_MANAGER/SITE`, `HR/SITE`, `WORKSHOP_CHIEF/SITE` créant ou modifiant sur S1, ni leur 404 sur S2. Le code utilise correctement `covers_site` (`fleet/service.py:134`, `workforce/service.py:191`), mais rien n'empêche une régression (ex. nouveau service oubliant `driver_in_scope`). Correction : ajouter un objet S2 dans `world`, un test paramétré « persona SITE S1 × route item × objet S2 → 404 identique à un UUID inconnu, sans audit » (même forme que `test_isolation_foreign_object...`), et un test de succès d'écriture pour chaque `(rôle, portée)` autorisé en écriture sur S1.

**QA1B-04 — La liste des échéances (US-1.20) est faiblement testée et deux choix de conception divergent de la story.**
Test : `test_fleet_workforce.py:332-352` — horloge réelle (`datetime.now(UTC)`, l.338), un seul permis à +5 jours, assertion `len(items) == 1 and validity == "EXPIRING"`. Ne vérifient pas : EXPIRED, tri par date, portée SITE, habilitations (`workforce/service.py:598` jamais exécuté), paramètre `within_days`, bornes. Conception : (a) la story demande `EXPIRY_WARNING_DAYS` **par tenant** ; le code lit un singleton global (`get_settings().expiry_warning_days`, `workforce/router.py:167`) — acceptable tant que Q21 reste ouverte, à consigner ; (b) `expirations()` (`workforce/service.py:574-589`) liste tout permis `VALID` dont `expiry_date <= horizon` **sans borne basse** : un permis expiré depuis des années, y compris celui remplacé par un renouvellement (US-1.18 A5), reste affiché `EXPIRED` indéfiniment, ce qui noie la liste d'action des RH ; (c) aucune pagination (`list[ExpirationItem]`). Correction : écarter les éléments remplacés par un document plus récent valide de même (conducteur, catégorie) ou borner par une fenêtre ; pagination (CT-9) ; tests déterministes avec horloge injectée (voir QA1B-06).

**QA1B-05 — Assertion aveugle à l'ordre de l'historique de statut.**
`test_fleet_workforce.py:121-122` compare `[h["to_status"] ...]` à `["AVAILABLE", "IMMOBILIZED", "AVAILABLE"]`, une **séquence palindromique**, alors que `fleet/service.py:183` trie `changed_at DESC` (le premier élément est le plus récent). Un tri ascendant ou descendant passerait aussi, et les motifs, les auteurs (`changed_by`) et les transitions `from_status` ne sont pas vérifiés pour ces lignes (seul le cas de création, l.82). Correction : séquence non palindromique (AVAILABLE → IMMOBILIZED → IN_MAINTENANCE) avec assertion de l'ordre voulu, des couples `(from, to)`, de `reason_code` et de `changed_by == admin`.

### Moyens

**QA1B-06 — Dépendance à l'horloge réelle et tests non déterministes pour les échéances ; bombes à retardement de dates.**
`FrozenClock` existe (`app/core/clock.py:16`) et l'application lit `request.app.state.clock` (`authz/dependencies.py:49-51`), mais aucune fixture ne l'injecte (`core/clock.py` couvert à 59 %). Conséquences : `test_us120` (l.338) calcule `soon` avec l'horloge du test pendant que l'application utilise la sienne (écart de minuit UTC négligeable à +5 jours, mais aucune borne n'est testable) ; `decommissioned_on` (`test_us115`, l.137) est seulement `is not None` ; les bornes d'expiration par l'API et la sortie `EXPIRING`/`EXPIRED` ne peuvent pas être rejouées. Dates fixes futures : `test_us119` utilise `valid_to 2030-12-31` (l.304) puis exige `authorized_category_ids == [category]` (l.313) — échec garanti à partir du 2031-01-01 ; `test_us118` exige `VALID` pour un permis expirant en 2035 (l.273-275) ; les données de la matrice (`test_authz_matrix.py:34-35`) n'ont pas d'assertion de validité, donc sans risque. Correction : fixture `frozen_clock` (par exemple `client.app.state.clock = FrozenClock(...)` avec restauration, ou `create_app(clock=...)`) ; dates calculées par rapport à l'horloge figée.

**QA1B-07 — La règle D-23 (fuseau du site) n'est prouvée que sur la fonction pure, pas sur le câblage.**
`test_d23_validity_boundaries_depend_on_site_timezone` (l.358-378) valide `derive_validity`. Aucun test ne crée un site à décalage non nul puis lit un permis/une habilitation/une échéance via l'API : une régression qui passerait `UTC` au lieu de `site_timezone` dans `_license_out` (`workforce/service.py:137`), `_qualification_out` (163), `_authorized_categories` (85-92) ou `expirations` (550) laisserait tous les tests verts (les sites des fixtures prennent le fuseau par défaut du tenant). Cas de bornes manquants dans la fonction pure : l'instant exact J+1 00:00:00 local à UTC+1 (23:00:00 UTC), `valid_until == today + warning_days` et `+1`, `warning_days=0`, `valid_from == today`, `valid_until=None`. Risque latent : `now.astimezone(tz)` (`validity.py:26`) interprète un `datetime` **naïf** dans le fuseau de la machine ; aucune garde ni test. Correction : tests API avec un site `Africa/Lagos` (US-1.18 A8 : « même instant UTC vu depuis un site UTC+0 et un site UTC+1 ») et horloge figée ; garde `if now.tzinfo is None: raise ValueError`.

**QA1B-08 — Assertions faibles : statut HTTP seul, sans code d'erreur ni audit.**
`test_fleet_workforce.py` : l.94 (HR → 403), l.96 (`model_year=1800` → 422 sans champ), l.165 (DISPATCHER PATCH → 403), l.279 (permis `expiry == issue` → 422), l.288 (OPS POST permis → 403), l.311 (HSE écriture → 403), l.172 correct (code vérifié) pour comparaison. Les exigences « audité » des refus (US-1.12 A7, US-1.16 A5, US-1.18 A7) ne sont couvertes que par le test générique `test_st02_denials_audited` (une seule route). Les créations ne vérifient pas l'événement d'audit (US-1.12 A1, US-1.16 A1, US-1.18 A1, US-1.19 A1, US-1.15 A1, US-1.21 A1). Correction : helper `assert_error(resp, status, code)` et `assert_audited(client, tenant, action, entity_id)` ; vérifier au moins un événement `DENIED` par module 1b.

**QA1B-09 — Tests de masquage incomplets (US-1.17 A2, US-1.18 A6) et champ potentiellement sensible hors politique.**
Seul `GET /drivers/{id}` est testé sous masquage (l.203-222) ; la **liste** `/drivers` (même fonction `drivers_out`, mais autre chemin, `workforce/router.py:35-44`) ne l'est pas. Rôles non testés : DIRECTION et HSE (qui, par `field_policies`, voit `suspension_reason_code`, non testé), DISPATCHER/HSE/AUDITOR pour les permis. L'assertion `'"phone"' not in raw` est correcte mais ne vérifie ni le jeu de clés exact de la story (matricule, nom, prénom, site, statut, catégories) ni l'absence de `suspension_reason_code`, `employment_type`, `external_company_name`, `exit_date`. Le numéro de permis est testé absent de l'audit mais **pas des logs** (US-1.18 A6) : aucun test `caplog` ni capture de la sortie structurée. Constat de conception à confirmer par la sécurité : `unavailability_reason` (LEAVE/TRAINING/OTHER) et `unavailable_until` ne figurent pas dans `field_policies` (`authz_matrix.yaml:419-425`) et sont donc visibles pour tout lecteur ; non contraire à D-15 tel que rédigé, mais un congé est une donnée RH. Correction : test d'égalité exacte des clés par rôle sur fiche **et** liste ; test `caplog` sur création de permis et sur erreur 422 de permis.

**QA1B-10 — Règles de statut : couverture partielle, stub `OPEN_ASSIGNMENTS_EXIST` non testé, écart « motif » conducteur.**
(a) La machine à états (`fleet/service.py:26-32`) n'est testée que sur 4 transitions ; pas de table exhaustive 5×5 (transitions valides et invalides, motif requis par cible, `status_reason_code` effacé en retour à AVAILABLE : un seul cas, l.120). (b) `open_assignments` retourne `[]` en 1b (`fleet/service.py:61-67`, `workforce/service.py:52-55`) : le contrat de réponse 409 (`details.total`, `details.items` tronqué à `blocking_list_max`) n'est testé par rien alors qu'un `monkeypatch` de `open_assignments` le permettrait dès maintenant (US-1.14 A2/A4, 1.15 A2, 1.17 A5, 1.21 A2 : 5 critères « Manquant » uniquement pour cette raison). (c) Pour un conducteur, le « motif obligatoire » de l'`INACTIVE` (US-1.21 A1/A3) est implémenté comme `exit_date` obligatoire (`workforce/service.py:310-316`), ce qui diffère du libellé de la story (code de motif) ; à trancher ou à documenter. (d) `change_driver_status` affecte l'objet avant de valider `exit_date >= hire_date` (l.319-325) : correct grâce au rollback de session, mais fragile ; chemin non testé (l.325). (e) `STATE_TRANSITION_INVALID` pour statut identique (l.309) et révocation d'une habilitation déjà révoquée (l.503) non testés. Correction : tests paramétrés de la machine à états ; test de contrat 409 avec `monkeypatch` ; décision sur le motif d'INACTIVE.

**QA1B-11 — Migration 0005 : le chemin « copie du catalogue pour les tenants existants » n'est jamais exécuté, et il n'existe aucun mécanisme d'évolution du catalogue.**
`0005_fleet.py:92-100` copie le catalogue pour `tenant.kind = 'CUSTOMER'` avant d'activer la RLS forcée. Les tests rejouent `downgrade base` puis `upgrade head` sur base **vide** (`conftest.py:37-38`) : les deux `INSERT ... SELECT` s'exécutent sur zéro tenant, donc aucune ligne copiée n'est jamais vérifiée (jointure `vehicle_category_template_license`, `is_system = true`, unicité `(tenant_id, code)`, absence de copie pour le tenant plateforme). Non testé non plus : migration 0004 → 0005 avec un tenant existant ; équivalence entre la copie de migration et `seed_tenant_catalog` (`fleet/contracts.py:11-36`) qui duplique le SQL ; ajout futur d'une 16e catégorie (aucune migration de données prévue : les tenants existants ne la recevraient pas, D-35 / D-18). Correction : test de migration `alembic upgrade 0004` → insertion d'un tenant CUSTOMER et d'un tenant PLATFORM par le propriétaire → `upgrade 0005` → comparaison catalogue du tenant vs `seed_tenant_catalog` pour un tenant neuf ; documenter la procédure d'évolution du catalogue (migration de données qui copie les nouvelles lignes pour tous les tenants).

**QA1B-12 — Downgrades 0005/0006 : destructifs, non testés avec données, rollback non documenté pour la 1b.**
`0005_fleet.py:191-209` et `0006_workforce.py:124-137` suppriment les tables et leurs données (véhicules, historique, conducteurs, permis, habilitations). Seule protection : `guard_destructive()` selon l'environnement (`core/migration_tools.py:16-18`, branche de refus non testée, 58 %). Aucune étape « sauvegarde vérifiée avant » ni indication de rollback applicatif (retour à l'image précédente, la base 1b restant compatible avec le code 1a car purement additive) n'est écrite dans `LIVRAISON_TRANCHE_1B.md`. Contrôles de cohérence du `downgrade` : ordre correct (historique avant véhicule, fonctions de trigger supprimées après les tables) ; `DROP FUNCTION app.tg_vehicle_status_*` n'est pas conditionnel ; `0005` supprime des tables globales alimentées par la migration (cohérent). Non vérifié : `upgrade → downgrade -1 → upgrade` **par révision** avec comparaison de schéma (QA1A-03 toujours ouvert), et idempotence en cas d'échec partiel (SQL exécuté en bloc par `run_sql`, la transactionnalité DDL de PostgreSQL protège, non démontrée). Correction : écrire le rollback 1b (restauration depuis sauvegarde, pas de downgrade en production, expand/contract), ajouter le test de cycle par révision et un test unitaire du refus de `guard_destructive`.

**QA1B-13 — Contrat d'API et conformité aux conventions : non couverts par un test.**
Aucun test ne gèle le schéma OpenAPI 1b (QA1A-04 : pas d'export versionné) ; l'ETag n'est pas renvoyé par `POST /drivers/{id}/licenses`, `PATCH /driver-licenses/{id}`, `POST .../revoke` ni par `GET /drivers/{id}/licenses` (`workforce/router.py:98-158`), alors que le PATCH exige `If-Match` : le client doit reconstruire `"<row_version>"` à partir du corps. Une violation de CHECK en base est renvoyée en 422 avec le nom de la contrainte dans `details` (`core/errors.py:153-158`, p. ex. `ck_driver_dates` après un PATCH de `hire_date`), ce qui expose des noms internes : mineur, mais non testé. Correction : test de contrat ETag/If-Match sur toutes les routes mutantes 1b ; test `hire_date` postérieure à `exit_date` à la modification.

### Mineurs

**QA1B-14 — Le seuil de couverture CI (85 % global) ne protège pas les services 1b.**
`fleet/service.py` 78 % et `workforce/service.py` 82 % passent sous le seuil global parce que le reste du code est à plus de 95 %. STRATEGIE §1.5 vise des seuils par module sensible. Correction : `[tool.coverage.report]` avec `fail_under` global et un contrôle par fichier (`coverage report --include='app/fleet/service.py,app/workforce/service.py,app/authz/*,app/identity/*' --fail-under=90`) ; le pas immédiat est de couvrir QA1B-02, 04, 10.

**QA1B-15 — Isolation de l'environnement de test : garde du nom de base et base partagée.**
`conftest.py:26-29` impose le suffixe `_test` (bonne garde) mais `downgrade base` à chaque session détruit toutes les données : deux agents ou développeurs lançant la suite sur `minefleet_test` simultanément se corrompent mutuellement. La procédure de cette revue (base jetable `minefleet_qa_test` via `MF_DB_NAME`) fonctionne mais n'est pas documentée. Correction : documenter dans `STRATEGIE_QUALITE_CI.md` / `scripts/test.ps1` un paramètre pour une base jetable par exécution (suffixe aléatoire `_test`), et un verrou consultatif PostgreSQL (`pg_advisory_lock`) dans la fixture `database` pour échouer proprement en cas d'exécution concurrente.

**QA1B-16 — Qualité de structure des tests 1b.**
(a) `_category()` (l.20-22) rappelle l'API de liste à chaque véhicule créé (N appels HTTP inutiles) ; (b) l.124 et l.319 codent `If-Match: '"1"'` en dur : ces tests dépendent de la valeur initiale de `row_version` (couplage fragile avec les triggers de `row_version`) ; (c) `fleet_number` aléatoire de 6 hex (probabilité de collision négligeable, mais pas nulle sur des milliers de tests partageant le tenant de la matrice) ; (d) `test_us111` exige `len(cats) == 15` : le test casse à l'ajout légitime d'une catégorie, alors qu'il devrait comparer au contenu de `vehicle_category_template` ; (e) les données persistent entre tests (QA1A-10). Non flaky observé : une seule exécution complète, 1151 verts ; la stabilité sur N exécutions reste non mesurée.

**QA1B-17 — Catalogue : anomalie de copie non détectée.**
`seed_tenant_catalog` (`fleet/contracts.py:33-36`) retourne un `rowcount` que l'appelant (`organization/service.py:63`) n'utilise pas : une copie vide ne lève aucune erreur (US-1.11 A3 la qualifie d'anomalie). Pas de test de l'atomicité (échec de la création d'administrateur après la copie → rollback du tenant et de ses catégories). Correction : `assert created == count(template)` et test de rollback.

## 5. Tests manquants priorisés

**P1 (avant la revue de la tranche 1c)**
1. `test_dbt_*_1b` : RLS croisée, FK composites inter-tenant, historique en ajout seul, exclusion `ex_dq_no_overlap` (adjacence, période ouverte), CHECK `ck_vehicle_retired`/`reason`/`driver_*` (QA1B-01).
2. `test_us114_patch_vehicle_*` : succès + audit avant/après + `row_version` + ETag, conflit d'immatriculation, null interdit, site/catégorie hors portée ou étrangers (QA1B-02).
3. `test_us118_license_patch_*` : suspension/retrait → éligibilité et échéances, `If-Match` (QA1B-02).
4. IDOR intra-tenant : objet S2 dans `world`, 404 identique pour tout rôle `SITE` S1 sur toutes les routes item 1b ; écritures positives par `(rôle, portée)` (QA1B-03).
5. Fixture d'horloge figée + `test_us120_*` complet (EXPIRING, EXPIRED, tri, portée SITE, habilitation, `within_days`, vide) et tests API D-23 avec un site UTC+1 (QA1B-04, 06, 07).
6. Contrat 409 `OPEN_ASSIGNMENTS_EXIST` par `monkeypatch` de `open_assignments` pour véhicule (statut, site, réforme) et conducteur (statut, site) (QA1B-10).
7. Test de migration 0004 → 0005 avec tenants existants et équivalence avec `seed_tenant_catalog` (QA1B-11).

**P2**
8. Table exhaustive des transitions véhicule et des transitions conducteur (motifs, effacement des champs, `exit_date < hire_date`, statut identique, révocation répétée) (QA1B-10).
9. Masquage : jeu de clés exact par rôle sur fiche et liste ; permis par rôle ; `caplog` sans numéro de permis ni téléphone (QA1B-09).
10. Historique de statut non palindromique avec motif/auteur (QA1B-05) ; helper `assert_error`/`assert_audited` appliqué aux assertions faibles (QA1B-08).
11. Doublons contre un véhicule `RETIRED` (US-1.12 A2/A3), `fleet_number` absent → 422, site d'un autre tenant, doublon concurrent (deux threads avec barrière, comme le test 1a amélioré), `IF_MATCH_REQUIRED` sur les routes 1b.
12. Pagination multi-pages et états vides pour `/vehicles` et `/drivers` ; valeurs de filtre invalides (US-1.13 A4/A5).
13. Rollback documenté et test du cycle upgrade/downgrade -1/upgrade par révision + refus de `guard_destructive` (QA1B-12).

**P3**
14. Contrat : ETag sur toutes les routes mutantes, gel du schéma OpenAPI 1b, absence de nom de contrainte dans les erreurs (QA1B-13).
15. Seuils de couverture par module (QA1B-14), base de test jetable/verrou (QA1B-15), nettoyage de structure (QA1B-16), contrôle du `rowcount` du catalogue (QA1B-17).

## 6. Distinction testé / non testé

**Testé** (exécuté dans cette revue, 1151 verts, ruff/format/mypy verts) : création et unicité normalisée des véhicules, portée de site à la création, machine à états principale et historique, réforme terminale et masquage par défaut, recherche normalisée, création/homonyme/matricule des conducteurs, masquage du téléphone par rôle et par site d'enregistrement (GET unitaire), absence de valeurs sensibles dans l'audit, permis (expiré à la saisie, doublon, numéro absent hors HR), habilitations (chevauchement, HSE en lecture seule, catégories autorisées), borne de validité D-23 sur la fonction pure, matrice 403/404 générée pour toutes les routes 1b, copie du catalogue à la création d'un tenant.

**Non testé** : tout ce qui est listé « Manquant » au §3 ; les migrations sur base peuplée et le downgrade avec données ; le câblage API du fuseau de site ; la durée de vie de la suite (flakiness sur N exécutions) ; `pip-audit`, build d'image et CI distante ; comportements dépendant de la tranche 1c (affectations réelles, éligibilité, conformité dérivée).
