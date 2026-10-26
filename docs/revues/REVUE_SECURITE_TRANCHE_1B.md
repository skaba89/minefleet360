# Revue de sécurité du code — tranche 1b — MINEFLEET 360

> Date : 2026-10-26. Branche `main`, commits `f7ad86f` (lot 1b) et `6544deb` (suites des revues 1a et revue automatique 1b).
> Périmètre : `backend/app/fleet/*`, `backend/app/workforce/*`, `backend/app/organization/contracts.py`, migrations `0005_fleet.py` et `0006_workforce.py`, modifications de `backend/app/authz/*` (`authz_matrix.yaml` sections fleet/workforce et `field_policies`, `principal.py` masquage par enregistrement, `dependencies.py` `reject_unknown_query`).
> Référentiels : `DECISIONS_A_ARBITRER.md` (D-10, D-11, D-13, D-15, D-18), `MATRICE_RBAC.md` §2.3, §2.4, §5, `LIVRAISON_TRANCHE_1B.md`. Les constats de `REVUE_SECURITE_TRANCHE_1A.md` ne sont pas répétés.
> Auteur : security-engineer.

## 0. Méthode et limites

**Testé (exécuté)** : scripts d'attaque locaux (hors dépôt, dans le répertoire temporaire de la session, copiés dans le conteneur `api` puis supprimés) exécutés contre une base jetable `minefleet_sec` (créée par le conteneur `db` avec l'utilisateur `postgres`, propriétaire `mf_owner`, extensions postgis/btree_gist/citext, schéma `app`, droits `mf_app`, migrée à `0006`, **puis supprimée** ; `minefleet` et `minefleet_test` n'ont pas été touchées). Deux tenants fictifs A et B (sites S1, S2), comptes HR (tenant, S1, S2), HR S1 + DIRECTION, OPS_MANAGER S1, DISPATCHER S1, WORKSHOP_CHIEF S1, MECHANIC S1, HSE, DIRECTION, AUDITOR, FINANCE, TENANT_ADMIN. Valeurs sentinelles fictives uniquement. Les requêtes HTTP passent par le `TestClient` de l'application ; les tests au niveau base passent par une session `mf_app` (même rôle que l'API).
**Non exécuté** : la suite pytest du dépôt (elle réinitialise `minefleet_test`), `ruff`, `mypy`, `pip-audit`. Je ne confirme donc pas les chiffres de `LIVRAISON_TRANCHE_1B.md`. Le front-end n'est pas évalué (échappement des champs libres à la charge de l'UI).
**Lu seulement** : concurrence au-delà du cas de verrou testé en §2 SEC1B-01, sauvegardes, rétention, CI.
Chaque constat indique « testé » ou « lu ».

## 1. Synthèse

| ID | Gravité | Sujet | Statut |
|----|---------|-------|--------|
| SEC1B-01 | élevée | Un octet NUL (ou toute erreur base) → `500` et **paramètres SQL (téléphone, noms, n° de permis) écrits en clair dans les logs** ; `lock_timeout` → `500` | testé |
| SEC1B-02 | moyenne | L'audit expose nom, prénom et matricule des conducteurs au `TENANT_ADMIN`, contre D-10 | testé |
| SEC1B-03 | moyenne | `restrictions` / `issued_by_name` / `reference` des habilitations : texte libre non masqué (D-15 : pas de donnée médicale), lisible par 7 rôles | testé |
| SEC1B-04 | faible | `vehicle.notes` (texte libre) copié en clair dans l'audit et lisible par tous les lecteurs de véhicule | testé |
| SEC1B-05 | faible | Levée d'une immobilisation `SAFETY_BAN` par `DISPATCHER` / `WORKSHOP_CHIEF` ; permis `WITHDRAWN` → `VALID` sans garde ; suspension conducteur levée sans HSE | testé |
| SEC1B-06 | faible | Oracle d'existence inter-sites par les `409` d'unicité (matricule, immatriculation, n° de parc, série) | testé |
| SEC1B-07 | faible | Intégrité des données : matricule sensible à la casse, n° de permis partageable entre conducteurs, dates absurdes (0001, 9999) | testé |
| SEC1B-08 | faible | `GET /vehicles/{id}/status-history` expose `changed_by` à tous les lecteurs de véhicule (MATRICE §5 : réservé TA / AUDITOR) | testé |
| SEC1B-09 | faible | `mf_app` garde `INSERT` sur `vehicle_status_history` (historique falsifiable) et `UPDATE` large sur `vehicle_category` | testé |
| SEC1B-10 | faible | Habilitation `site_id` NULL (« tous sites ») accordable par un HR de portée SITE ; `authorized_category_ids` ignore statut du conducteur et site | testé / lu |
| SEC1B-11 | faible | `/workforce/expirations` non paginé, N+1 sur les fuseaux, détection d'homonyme en mémoire : abus de ressources | lu |

Aucun constat critique. **Aucune fuite inter-tenant ni inter-site n'a été obtenue** (section 3). Les contrôles de masquage, de portée SITE, de minimisation et de machine à états décrits dans les documents sont effectifs côté API.

## 2. Constats

### SEC1B-01 — Octet NUL : `500` et paramètres SQL en clair dans les logs — élevée (testé)

- **Fichiers** : `backend/app/core/errors.py:174-194` (gestionnaire `_unexpected` : `logger.exception` journalise l'exception SQLAlchemy complète, qui contient `[SQL: …] [parameters: …]`) ; `backend/app/core/db.py:32-37` (`create_engine` sans `hide_parameters=True`) ; absence de garde NUL dans `backend/app/workforce/schemas.py` (lignes 22-36, 55-70, 85-92, 112-120) et `backend/app/fleet/schemas.py` (lignes 43-70) ; `backend/app/workforce/service.py:207-213` (paramètre `q`).
- **Scénario** (utilisateur HR authentifié, base jetable) :
  1. `POST /api/v1/drivers` avec `{"site_id": …, "employee_number": "LOG1", "last_name": "a\u0000b", "first_name": "Prenom-SENTINELLE", "phone": "+224699999999"}` → `500 INTERNAL_ERROR`.
  2. Dans les logs de l'API, l'événement `unhandled_error` contient `DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes [SQL: INSERT INTO driver …] [parameters: …]` avec le **téléphone**, le prénom et le nom en clair (recherche de `699999999` et `SENTINELLE` : présents).
  3. Même résultat avec `POST /drivers/{id}/licenses` et `license_number: "LICSENTINEL\u0000"` : le **numéro de permis** est dans les logs.
  4. NUL aussi dans `vehicle.notes`, `make`, `registration_number`, `external_company_name`, `status_note`, `restrictions` : tous `500`. `GET /drivers?q=%00` (octet NUL réel) : `500`.
  5. Variante sans NUL : verrou tenu par une autre transaction (`SELECT … FOR UPDATE` sur la ligne conducteur), puis `PATCH /drivers/{id}` → attente de 5 s puis `500 INTERNAL_ERROR` (`LockNotAvailable`), alors que le commentaire de `config.py:45` annonce « 409/500 » et que ce cas est de la concurrence normale.
- **Impact** : viole US-1.18 A6 (« numéro de permis absent des logs »), D-15 (téléphone = donnée personnelle) et la règle de `core/logging.py` (« ne jamais journaliser de PII brute »). Déclenchement trivial par tout rédacteur ; **tout** `DBAPIError` non mappé (interblocage, timeout de verrou, erreur de donnée, échec de sérialisation) produit la même fuite, y compris pour des données saisies par d'autres utilisateurs. Bruit d'alerte (500) et déni de service ciblé sur une ligne verrouillée.
- **Correction proposée** : (1) `create_engine(..., hide_parameters=True)` ; (2) dans `_unexpected` et `integrity_error_unmapped`, journaliser `type(exc).__name__`, le `sqlstate` et `str(exc.orig)` sans la requête ni les paramètres (`exc.statement`/`exc.params` jamais) ; (3) mapper `DataError` (sqlstate `22xxx`) → `422 VALIDATION_ERROR`, `OperationalError` `55P03`/`40001`/`40P01` → `409`/`503` avec `Retry-After` ; (4) refuser `\x00` dès la validation (`StrictModel` : validateur de chaîne commun, et contrainte de motif sur les paramètres `q`, `registration_number`, `fleet_number`) ; (5) test de régression : NUL dans chaque champ texte → `422`, et aucun `[parameters:` dans la sortie de log.

### SEC1B-02 — L'audit expose l'identité des conducteurs au `TENANT_ADMIN` — moyenne (testé)

- **Fichiers** : `backend/app/workforce/service.py:244-258` (`driver.create` : `after.employee_number`), `:278-292` (`driver.update` : `before`/`after` avec `last_name`, `first_name`, `site_id`) ; `MATRICE_RBAC.md` §2.4 (« `TENANT_ADMIN` : **aucune** permission `workforce.*` … il ne peut donc lire aucun nom, matricule ni téléphone de conducteur », D-10) ; `field_policies.driver` ne couvre pas ces champs.
- **Scénario** : HR crée un conducteur puis `PATCH {"last_name":"Camara-Sentinelle","first_name":"Mamadi-Sentinelle"}`. Le `TENANT_ADMIN` du même tenant appelle `GET /api/v1/audit-events?entity_type=driver&page_size=200` : la réponse contient `Camara-Sentinelle`, `Mamadi-Sentinelle` et le matricule (`before_data`/`after_data`). Téléphone, n° de permis, motif de suspension : **absents** (bien).
- **Impact** : contournement de D-10 par un canal latéral ; le `TENANT_ADMIN` (qui ne doit pas voir les données de conducteurs) obtient les identités. L'AUDITOR, lui, a `workforce.driver.read` : sans écart.
- **Correction proposée** : ne pas écrire de nom ni de matricule dans `before_data`/`after_data` (identifier par `entity_id` et `changed_fields`), ou ajouter `last_name`, `first_name`, `employee_number` à la liste des champs dont la valeur n'est jamais auditée (`restricted_fields`). Test : après création/mise à jour d'un conducteur, aucune valeur de nom ou de matricule dans `GET /audit-events` côté `TENANT_ADMIN`.

### SEC1B-03 — Habilitations : texte libre non masqué, risque de donnée médicale — moyenne (testé)

- **Fichiers** : `backend/app/workforce/schemas.py:115-117, 142-144` (`issued_by_name`, `reference`, `restrictions` ≤ 300 caractères, libres) ; `backend/app/workforce/service.py:157-180` (renvoyés sans `mask`) ; `backend/app/authz/authz_matrix.yaml:376-388, 415-432` (aucune entrée `field_policies.driver_qualification`) ; `DICTIONNAIRE_DONNEES.md` (classe ces colonnes « personnel » : « restrictions courtes »).
- **Scénario** : `GET /drivers/{id}/qualifications` avec DIRECTION, DISPATCHER (site) et WORKSHOP_CHIEF (site) renvoie les clés `issued_by_name`, `reference`, `restrictions` (testé ; idem OPS_MANAGER, HR, HSE, AUDITOR d'après la matrice). Un HR saisit « port de lunettes correctrices obligatoire » : c'est de fait une donnée d'aptitude médicale, que D-15 exclut du lot 1 (« pas d'aptitude médicale ni de motif maladie »).
- **Impact** : collecte et diffusion large de données de santé potentielles, sans contrôle. Même risque pour `license.status_note` (masqué HR seul, mais libre) et `driver.external_company_name`.
- **Correction proposée** : remplacer `restrictions` par une liste de codes (ex. `DAYLIGHT_ONLY`, `SITE_ONLY`, `ESCORT_REQUIRED`) ; sinon masquer `restrictions`/`issued_by_name`/`reference` à HR + HSE via `field_policies`, réduire la longueur (≤ 80) et avertir dans l'UI de ne saisir aucune donnée de santé. Ajouter l'entité à `field_policies` pour que le test généré (§7.2 de la matrice) la couvre.

### SEC1B-04 — `vehicle.notes` dans l'audit et visible de tous les lecteurs — faible (testé)

- **Fichiers** : `backend/app/fleet/service.py:237, 251` (`_snapshot(vehicle, fields)` avec `fields` issus du corps : inclut `notes` et `serial_number`) ; `backend/app/audit/contracts.py:27-34` (`SENSITIVE_FIELDS` ne contient pas `notes`) ; `backend/app/fleet/schemas.py:55, 70, 100`.
- **Scénario** : `PATCH /vehicles/{id}` avec `{"notes":"Conducteur habituel: Camara Mamadi tel 622000000"}` → le texte (nom et téléphone) apparaît dans `before_data`/`after_data` de `GET /audit-events` (TENANT_ADMIN) ; `GET /vehicles/{id}` le renvoie aussi à MECHANIC, FINANCE, etc. (testé).
- **Impact** : une donnée de conducteur saisie dans un champ libre de véhicule contourne le masquage téléphone/identité et l'audit « sans valeur sensible ».
- **Correction proposée** : exclure `notes` des valeurs auditées (nom du champ dans `changed_fields` seulement) ; réduire à 300 caractères et mettre un avertissement UI ; à terme restreindre `notes` aux rôles de gestion de parc.

### SEC1B-05 — Garde-fous métier faibles sur les levées de blocage — faible (testé)

- **Fichiers** : `backend/app/fleet/service.py:26-33, 258-290` ; `backend/app/authz/authz_matrix.yaml` (`fleet.vehicle.update_status` : DISPATCHER, WORKSHOP_CHIEF de site) ; `backend/app/workforce/service.py:300-342, 405-433`.
- **Scénario** : (a) WORKSHOP_CHIEF immobilise un véhicule (`IMMOBILIZED`, `SAFETY_BAN`) ; un DISPATCHER du site le repasse `AVAILABLE` (200) : le motif est effacé de la ligne (`status_reason_code = NULL`), seuls l'historique et l'audit gardent la trace ; HSE n'intervient pas. (b) `PATCH /driver-licenses/{id}` `{"status":"WITHDRAWN"}` puis `{"status":"VALID"}` → 200 : un permis retiré redevient valide sans motif ni second acteur (aucune machine à états côté permis). (c) HR repasse un conducteur `SUSPENDED` (`HSE_DECISION`) à `ACTIVE` sans référence de décision, `INACTIVE` → `ACTIVE` accepté.
- **Impact** : rôle opérationnel pouvant lever un blocage de sécurité décidé par un autre ; la traçabilité existe mais le contrôle préventif manque. Gravité faible tant que l'éligibilité (tranche 1c) n'est pas consommée.
- **Correction proposée** : interdire la sortie de `IMMOBILIZED` avec `SAFETY_BAN` aux seuls OPS_MANAGER/TENANT_ADMIN (ou exiger un motif de levée), exiger `reason`/référence pour `WITHDRAWN`/`SUSPENDED` → `VALID` et pour `SUSPENDED` → `ACTIVE`, auditer le motif de levée. À arbitrer (nouvelle décision D-xx) avant la 1c.

### SEC1B-06 — Oracle d'existence inter-sites par les `409` d'unicité — faible (testé)

- **Fichiers** : `backend/app/core/errors.py:82-94` ; contraintes `uq_driver_tenant_employee`, `uq_vehicle_tenant_fleet_number`, `uq_vehicle_tenant_registration`, `uq_vehicle_tenant_serial` (unicité par **tenant**, pas par site).
- **Scénario** : HR de portée S1 `POST /drivers` avec le matricule d'un conducteur de S2 → `409 DUPLICATE_EMPLOYEE_NUMBER` ; OPS_MANAGER S1 crée un véhicule avec l'immatriculation d'un véhicule de S2 → `409 DUPLICATE_REGISTRATION`, alors que `GET /vehicles?registration_number=…` renvoie `total: 0` (testé). Même mécanisme pour n° de parc et n° de série.
- **Impact** : un rédacteur limité à un site apprend l'existence d'objets hors de sa portée (l'identifiant interne n'est pas divulgué). Le périmètre de la fuite est le tenant, donc faible ; cela contredit la règle « hors portée = comme inexistant » de §1.1 de la matrice.
- **Correction proposée** : accepter et documenter (unicité par tenant voulue), ou, pour un rédacteur dont la portée ne couvre pas le tenant entier, renvoyer le même `409` sans distinguer le champ. À consigner dans la matrice comme écart assumé.

### SEC1B-07 — Intégrité des données de personnel — faible (testé)

- **Fichiers** : `backend/alembic/versions/0006_workforce.py:39` (`uq_driver_tenant_employee` sur la valeur brute), `:77` (`uq_driver_license_issue` inclut `driver_id`) ; `backend/app/workforce/schemas.py:22-40, 55-70, 112-120` (aucune borne de dates).
- **Scénario** : matricule `M-1` puis `m-1` → 2 conducteurs distincts (201 ×2) ; le même numéro de permis `SHARED-LIC-9` sur deux conducteurs → 201 ×2 ; `hire_date: 0001-01-01`, `expiry_date: 9999-12-31`, habilitation `valid_from 0001-01-01` / `valid_to 9999-12-31` acceptés ; permis délivré en 2090 accepté ; `PATCH {}` sur un permis incrémente `row_version` et écrit un événement d'audit sans changement.
- **Impact** : confusion d'identité (matricules homonymes), fraude non détectée (un permis pour deux personnes), échéances artificielles qui masquent les alertes d'expiration (`valid_to` en 9999). Pas d'atteinte à la confidentialité.
- **Correction proposée** : clé d'unicité sur `upper(employee_number)` (colonne générée comme `fleet_number_norm`) ; unicité `(tenant_id, category_code, license_number)` parmi les permis `VALID` ou avertissement `POSSIBLE_DUPLICATE_LICENSE` ; bornes (`hire_date`, `issue_date` ≤ aujourd'hui + tolérance ; `expiry_date` ≤ issue_date + 15 ans configurable) ; refuser un `PATCH` vide.

### SEC1B-08 — `changed_by` exposé dans l'historique de statut — faible (testé)

- **Fichiers** : `backend/app/fleet/schemas.py:105-111`, `backend/app/fleet/router.py:78-85` (permission `fleet.vehicle.read`) ; `MATRICE_RBAC.md` §5 (`audit_event.actor_user_id` : ✅ seulement TA et AUDITOR).
- **Scénario** : un MECHANIC de S1 appelle `GET /vehicles/{id}/status-history` → chaque ligne contient `changed_by` = identifiant du compte qui a modifié le statut (testé).
- **Impact** : l'identité (UUID) des acteurs est visible à des rôles qui n'y ont pas droit selon la matrice ; faible car l'UUID ne se résout pas sans `identity.user.read`.
- **Correction proposée** : omettre `changed_by` sauf pour les rôles détenant `audit.event.read` (ou le retirer du schéma et l'obtenir via l'audit).

### SEC1B-09 — Droits `mf_app` plus larges que nécessaire — faible (testé)

- **Fichiers** : `backend/alembic/versions/0005_fleet.py:102-104, 167` (`apply_tenant_rls('vehicle_status_history','SELECT, INSERT')`, `vehicle_category` `SELECT, INSERT, UPDATE`) ; commentaire `models.py` : « alimentée par trigger (DB-16) : jamais écrite par l'application ».
- **Scénario** (session `mf_app`, contexte tenant A) : `INSERT INTO vehicle_status_history (…)` avec `from_status/to_status` arbitraires pour un véhicule de A → réussit (rowcount 1) ; l'historique n'est donc plus une preuve. `UPDATE vehicle_category SET label_fr='hack'` touche les 15 catégories du tenant (aucune route n'existe, `fleet.vehicle_category.manage` est vide). `UPDATE vehicle SET row_version=1` accepté. En revanche `UPDATE`/`DELETE` de l'historique, `INSERT/UPDATE/DELETE` sur les tables de catalogue globales, `DELETE` de conducteur/véhicule/audit, `TRUNCATE`, `CREATE TABLE` : refusés.
- **Impact** : uniquement exploitable après compromission de l'application (injection SQL, code malveillant) ; défense en profondeur absente pour l'historique.
- **Correction proposée** : retirer `INSERT` de `mf_app` sur `vehicle_status_history` et rendre `tg_vehicle_status_after` `SECURITY DEFINER` (propriétaire `mf_owner`, `SET search_path`, `tenant_id` pris sur `NEW`) ; restreindre `UPDATE` de `vehicle_category` aux colonnes utiles quand `manage` sera livrée (`GRANT UPDATE (is_active, label_fr)`).

### SEC1B-10 — Habilitation « tous sites » et éligibilité calculée sans contexte — faible (testé / lu)

- **Fichiers** : `backend/app/workforce/service.py:455-456` (le site n'est contrôlé que s'il est fourni) ; `:68-96` (`_authorized_categories` n'examine ni `driver.status` ni `qualification.site_id`) ; `0006_workforce.py:111-116`.
- **Scénario** : HR de portée S1 `POST /drivers/{id}/qualifications` `{"qualification_type":"SAFETY_TRAINING","valid_from":"2024-01-01"}` → `201` avec `site_id: null` (valable « tout le tenant », RM-055 resté ouvert) ; un HR de site accorde donc une habilitation à portée tenant (testé). `GET /drivers` affiche `authorized_category_ids` même pour un conducteur `SUSPENDED`/`INACTIVE` (lu).
- **Impact** : devient une élévation de portée quand la 1c consommera l'éligibilité ; aujourd'hui informatif.
- **Correction proposée** : pour un rédacteur de portée SITE, forcer `site_id` = site du conducteur (refuser NULL) ; trancher RM-055 avant la 1c ; faire dépendre `authorized_category_ids` du statut du conducteur et du site de l'habilitation.

### SEC1B-11 — `/workforce/expirations` et listes : abus de ressources — faible (lu)

- **Fichiers** : `backend/app/workforce/service.py:527-607` (tous les conducteurs de la portée chargés, `IN (…)` non borné, aucune pagination), `:131-155, 348-355` (`site_timezone` requêté par permis), `:231-237` (homonymes : tous les conducteurs du site chargés en mémoire) ; `backend/app/workforce/router.py:161-168`.
- **Impact** : coût linéaire en nombre de conducteurs par appel (un seul rôle à portée tenant suffit) ; pas de limitation de débit authentifiée au niveau API. Négligeable au volume du pilote, à corriger avant montée en charge.
- **Correction proposée** : jointure SQL unique avec `LIMIT`/pagination ; fuseau chargé une fois par site ; détection d'homonyme par requête (`WHERE lower(unaccent(...))`).

## 3. Vérifié sans constat

**Testé (exécuté, base jetable)**

- **IDOR inter-tenant** : avec les jetons du tenant B (HR et TENANT_ADMIN) sur les identifiants du tenant A : `GET`/`PATCH`/`POST status` conducteur, `GET`/`POST` `/drivers/{id}/licenses`, `PATCH /driver-licenses/{id}`, `GET`/`POST` `/drivers/{id}/qualifications`, `POST /driver-qualifications/{id}/revoke`, `GET`/`PATCH`/`POST status`/`POST retire`/`GET status-history` véhicule, `GET /vehicle-categories/{id}` → tous `404 NOT_FOUND`, corps identique à un identifiant aléatoire (même `code` et `message_fr` ; seul `request_id` diffère). Le `404` précède la vérification de version (`If-Match: "1"` volontairement faux).
- **Références inter-tenant dans les corps** : site d'un autre tenant (création et déplacement de véhicule, création de conducteur, habilitation), catégorie d'un autre tenant ou inexistante (véhicule, habilitation), catégorie de permis inconnue → toujours `422 REFERENCE_NOT_FOUND` (aucune différence entre « existe ailleurs » et « n'existe pas »).
- **Portée SITE** : HR S1 sur objets S2 : conducteur (GET, PATCH, status), permis (GET, POST, PATCH), habilitations (GET, POST, revoke) → `404` ; OPS S1 sur véhicule S2 (GET, PATCH, status, retire, history) → `404` ; création en S2 → `422` ; déplacement de S1 vers S2 par un rédacteur sans portée S2 → `422` ; `?site_id=<S2>` → liste vide ; listes limitées à S1 ; habilitation avec `site_id` = S2 par HR S1 → `422`.
- **Masquage (D-15)** : sur `GET /drivers` (liste) pour DIRECTION, DISPATCHER S1, HSE, AUDITOR, WSC S1, OPS S1 : `phone`, `employment_type`, `external_company_name`, `hire_date`, `exit_date` **absents** ; `suspension_reason_code` présent seulement pour HSE et HR (conforme à `field_policies`) ; HR S1 voit tout pour S1 et rien pour S2 (404) ; **utilisateur HR S1 + DIRECTION tenant** : champs sensibles présents pour les conducteurs de S1, **absents pour ceux de S2** dans la liste et le détail (masquage par enregistrement effectif). Permis : `license_number`, `document_reference`, `status_note` absents pour OPS, DISPATCHER, HSE, AUDITOR ; présents pour HR ; `403` pour DIRECTION et WSC. Valeurs sentinelles (`+224600000111`, n° de permis, `NOTE-SENSIBLE-XYZ`, `INVESTIGATION`) introuvables dans les réponses des rôles non autorisés.
- **`/workforce/expirations`** : seules les clés `kind, item_id, driver_id, employee_number, driver_name, site_id, label, expires_on, validity` ; aucun téléphone ni numéro de permis ; filtré par portée (DISPATCHER S1 et HR S1 voient S1 seul) ; `403` pour DIRECTION et WSC ; `within_days` = -1, 366, `abc`, paramètre inconnu → `422`.
- **Audit** : aucun téléphone, n° de permis, `status_note`, motif de suspension dans `GET /audit-events` (TENANT_ADMIN) ; `changed_fields` ne porte que les noms des champs sensibles ; `UPDATE`/`DELETE` d'`audit_event` refusés pour `mf_app`. (Exceptions : SEC1B-02 et SEC1B-04.)
- **Minimisation D-15 / affectation de masse** : `birth_date`, `medical_fitness`, `address`, `user_account_id`, `status`, `tenant_id`, `anonymized_at`, `row_version`, `created_by`, `suspension_reason_code`, `exit_date`, `unavailability_reason` sur création/`PATCH` conducteur ; `status`, `status: null`, `decommissioned_on`, `status_reason_code`, `status_changed_at`, `fleet_number`, `row_version`, `created_by`, `gps_device_id`, `tenant_id` sur `PATCH`/création véhicule ; `verified_by`, `status`, `driver_id`, `tenant_id` à la création de permis ; `expiry_date`, `license_number`, `category_code`, `verified_by` en `PATCH` permis ; champs en trop à la révocation → tous `422` (schémas `extra="forbid"`).
- **Machine à états véhicule** : `AVAILABLE`→`RETIRED` par `/status` → `422` (hors `Literal`) ; `AVAILABLE`→`AVAILABLE`, `OUT_OF_SERVICE`→`AVAILABLE` → `422 VEHICLE_STATUS_TRANSITION_INVALID` ; motif obligatoire pour `IMMOBILIZED`/`OUT_OF_SERVICE` ; réforme terminale (nouvelle réforme, `PATCH`, `/status` sur un réformé → `422`) ; `PATCH` sans `If-Match` → `422 IF_MATCH_REQUIRED`, version périmée → `409` ; historique complet et ordonné ; numéro de parc d'un réformé non réutilisable (`409`).
- **Machine à états conducteur** : `ACTIVE`→`ACTIVE` → `409` ; motif obligatoire (`SUSPENDED`, `UNAVAILABLE`, `INACTIVE`) ; `exit_date` < `hire_date` → `422` ; `PATCH hire_date` incohérent avec `exit_date` → `422` ; contrainte `ck_driver_external` → `422` sans nom de contrainte exposé. Pas de contournement du statut par `PATCH`.
- **Chevauchement d'habilitations** : deux `VALID` chevauchantes → `409 DUPLICATE_QUALIFICATION`.
- **Paramètres de requête (`reject_unknown_query`)** : `tenant_id` ou tout paramètre inconnu → `422 unknown_parameter` sur liste et détail ; sans jeton → `401` ; sans droit → `403` (ordre D-05a conservé) ; alias `status` accepté, `status_filter` refusé ; `page=0`, `page_size=0/201/-1`, `status=foo`, UUID invalide → `422`.
- **Recherche et injection** : `q` et `registration_number`/`fleet_number` avec `%`, `_`, `\`, `' OR 1=1 --`, `[a-z]`, `;SELECT pg_sleep(5)` → `200`, aucun résultat anormal, pas d'erreur (requêtes paramétrées ; `%` et `_` agissent comme jokers LIKE sur `q`, sans conséquence de sécurité, la portée étant appliquée avant). Immatriculation normalisée en recherche exacte. (Exception : octet NUL, SEC1B-01.)
- **Catalogue global (D-18)** : `mf_app` a `SELECT` seul sur `vehicle_category_template`, `vehicle_category_template_license`, `license_category_ref` (`INSERT`/`UPDATE`/`DELETE` → `42501`) ; aucun droit `PUBLIC` ; catalogue copié par tenant (15 catégories) ; aucune route de modification de catégorie (`PATCH`/`POST`/`DELETE` → `405`).
- **RLS / triggers / contraintes des nouvelles tables** : RLS activée et forcée sur `vehicle`, `vehicle_category`, `vehicle_category_license_category`, `vehicle_status_history`, `driver`, `driver_license`, `driver_qualification` (politique `tenant_id = app.current_tenant_id()` en `USING` et `WITH CHECK`) ; sans contexte ou avec le contexte d'un autre tenant : 0 ligne ; `INSERT` d'un conducteur avec `tenant_id` d'un autre tenant → `42501` ; clés étrangères composites : site, catégorie ou conducteur d'un autre tenant → `23503` ; `UPDATE tenant_id` → `MF002` (immuable) ; mise à jour d'une ligne du tenant B sous contexte A → 0 ligne ; `UPDATE`/`DELETE` de `vehicle_status_history` → `42501` ; `DELETE`/`TRUNCATE` sur conducteur/véhicule refusés ; contraintes `ck_vehicle_status`, `ck_vehicle_retired` actives. (Exception : SEC1B-09.)
- **Droits applicatifs** : `CREATE TABLE` dans `public` refusé ; `mf_app` sans `DELETE` sur les tables de la 1b.

**Lu seulement**

- `site_in_scope` (`organization/contracts.py`) : site résolu sous RLS puis `covers_site` ; `None` → `422` ; cohérent avec les tests ci-dessus.
- `PermissionScope.roles_for_site` / `masked_fields` (`authz/principal.py`) : un rôle de portée SITE ne compte que pour son site ; pour une entité sans site, seules les attributions TENANT comptent.
- Verrous `FOR KEY SHARE` posés avant le contrôle de portée sur permis et habilitations (`_license_in_scope`, `revoke_qualification`) : verrou faible, sans effet de fuite ; seul le délai de verrou (SEC1B-01) en est une conséquence.
- Absence de `text(` construit par concaténation dans `fleet/` et `workforce/` (seule `seed_tenant_catalog` utilise `text()` avec paramètre lié).

## 4. Non couvert

- Interface (échappement des champs libres, affichage du masquage), exports (hors lot 1, D-16), accès support plateforme.
- Rétention et anonymisation des conducteurs : `anonymized_at` existe mais aucune route ni tâche n'anonymise ; durée de conservation des conducteurs sortis (`INACTIVE`) non définie (C-08, à valider avec un conseil local avant la production).
- Tests de charge (SEC1B-11), concurrence de masse, sauvegardes/restauration des nouvelles tables.
- Suite pytest, `ruff`, `mypy`, `pip-audit` (non exécutés par cette revue).
- Éligibilité et affectations (tranche 1c) : `open_assignments` renvoie une liste vide en 1b (D-11, D-13 non testables) ; à revoir à la livraison de la 1c (en particulier SEC1B-05, SEC1B-10).

## 5. Ordre de correction recommandé

1. **SEC1B-01** (logs avec données personnelles, 500 évitable) avant toute donnée réelle ; test de régression NUL + absence de `[parameters:`.
2. **SEC1B-02** et **SEC1B-04** (audit : aucune valeur de nom, matricule, note libre).
3. **SEC1B-03** (champs libres des habilitations, D-15) ; décision sur la liste de codes de restrictions.
4. **SEC1B-05**, **SEC1B-10** : à arbitrer (garde-fous de levée, portée « tous sites ») avant la tranche 1c.
5. **SEC1B-07**, **SEC1B-08**, **SEC1B-09**, **SEC1B-06**, **SEC1B-11** : durcissement, au fil de l'eau.
