# Modèle physique — Lot 1 (PostgreSQL 16 + PostGIS)

> Statut : **proposition de cadrage (phase 0)**, issue de `docs/revues/REVUE_DATABASE_ARCHITECT.md` (références DB-xx) et **alignée sur `docs/DECISIONS_A_ARBITRER.md`** (D-01..D-24 tranchées, défauts provisoires C-01..C-17), qui prime sur ce document en cas de divergence. **Le DDL ci-dessous est indicatif : il n'a été ni exécuté ni validé syntaxiquement par PostgreSQL.** Aucune base, aucune migration, aucun test n'existe. Les points à confirmer par exécution sont listés en §13.
> Les décisions du lead sont référencées D-xx ; les défauts provisoires en attente du client ou du juriste sont référencés C-xx (anciennes marques **[CLIENT]** remplacées).

## 0. Hypothèses, impacts, critères d'acceptation

**Décisions appliquées** (en plus de H1-H10 du socle)
- P1. Valeurs d'énumération en anglais `UPPER_SNAKE_CASE`, libellés FR dans l'interface (D-01 à D-04).
- P2. Tenant plateforme réservé (`kind = 'PLATFORM'`) : `tenant_id NOT NULL` partout (D-07).
- P3. Connexion = code d'espace de travail + e-mail ; e-mail `citext` unique par tenant ; résolution pré-authentification par code exact, sans `BYPASSRLS` (D-06, DB-05). C-02 ouvert (SSO/OIDC plus tard).
- P4. Pas d'accès support plateforme au lot 1 (D-16, C-10).
- P5. `driver` conservé (pas de `person`) au lot 1 (D-16, C-05).
- P6. Compteurs : `vehicle_meter_reading` **hors lot 1**, livrée avec la première story de compteur (D-16) ; aucune colonne de compteur sur `vehicle`.
- P7. Pas de donnée de santé, date de naissance ni adresse au lot 1 (D-15).
- P8. Pas de chaînage de hash en ligne ; colonnes `prev_hash`/`row_hash` nullables, scellement asynchrone ultérieur (D-16, D-17).
- P9. Identifiants UUID v4 (`gen_random_uuid()`), aucune dépendance UUID v7 (D-20).
- P10. **Pas d'`idempotency_record` au lot 1** (D-14) : les doublons sont empêchés par les contraintes d'unicité et d'exclusion ; la table est reportée au lot 4 (esquisse §11).
- P11. Concurrence optimiste par `row_version` + trigger (D-19) ; aucun `DELETE` pour `mf_app` sur les tables métier.
- P12. Lot 1 découpé en tranches 1a / 1b / 1c (D-21), migrations réparties en conséquence (§8).
- P13. Aucun volume connu : aucun objectif de performance, aucun dimensionnement (C-15 : hypothèse de développement 3 tenants × 3 sites × 200 véhicules).

**Modules impactés** : `organization` (tenant, site), `identity` (compte, rôle, jeton, session), `fleet` (catégorie, véhicule, historique de statut), `workforce` (conducteur, permis, habilitation), `assignment`, `audit`, plus `core` (contexte tenant, horloge injectable). Aussi `infra/` (bootstrap des rôles et extensions) et la configuration Alembic.

**Implications sécurité / tenant** : RLS activée et forcée sur toute table tenant-scopée ; `mf_app` sans propriété, sans `BYPASSRLS`, sans `DELETE` sur les tables métier ; FK composites ; audit en ajout seul ; la RLS **complète** l'autorisation applicative et ne la remplace pas, et ne protège pas d'une application qui fixerait elle-même le contexte (modèle de menace explicite : bug de filtrage).

**Critères d'acceptation du modèle** (vérifiables par les tests du §12) : une requête sans contexte renvoie 0 ligne sans erreur ; aucune FK inter-tenant ne peut être créée ; aucun chevauchement d'affectation (véhicule ou conducteur) ne peut être inséré ; `UPDATE`/`DELETE`/`TRUNCATE` sur `audit_event` sont refusés au rôle applicatif ; chaque table du schéma est soit listée comme globale, soit tenant-scopée avec RLS forcée ; `alembic upgrade head` puis `downgrade base` puis `upgrade head` réussissent sur une base amorcée.

## 1. Inventaire des tables

| Classe | Tables | RLS |
|--------|--------|-----|
| Globale (catalogue système, D-18) | `role`, `role_allowed_scope`, `license_category_ref` | Non ; `SELECT` seul pour `mf_app` |
| Racine de tenant | `tenant` | Politiques dédiées (§6) |
| Tenant-scopée, modifiable | `site`, `user_account`, `user_role_assignment`, `vehicle_category`, `vehicle_category_license_category`, `vehicle`, `driver`, `driver_license`, `driver_qualification`, `vehicle_assignment` | Oui, forcée |
| Tenant-scopée, éphémère | `account_token`, `auth_session` | Oui, forcée ; `DELETE` autorisé (purge) |
| Tenant-scopée, ajout seul | `vehicle_status_history`, `audit_event` (partitionnée) | Oui, forcée ; trigger d'ajout seul |
| **Hors lot 1** (esquisses §5.8 et §11) | `vehicle_meter_reading` (D-16), `idempotency_record` (D-14, lot 4), `vehicle_document`, `support_access_session`, `audit_seal`, `person` | — |

Tranche de livraison (D-21) : **1a** = `tenant`, `site`, tables globales, `user_account`, `user_role_assignment`, `account_token`, `auth_session`, `audit_event` ; **1b** = `vehicle_category` (+ jonction), `vehicle`, `vehicle_status_history`, `driver`, `driver_license`, `driver_qualification` ; **1c** = `vehicle_assignment`.

Écart au socle §5 : +`account_token`, +`auth_session`, +`vehicle_status_history`, +`vehicle_category_license_category`, +`role_allowed_scope`, +`license_category_ref` (pas de `permission`/`role_permission` en base : D-18a). `account_token` remplace l'entité `invitation` de PRD E4.

## 2. Conventions

**Types** : clés `uuid` ; instants `timestamptz` (UTC ; `mf_app` en `timezone = 'UTC'`) ; jours calendaires `date` ; énumérations `text` + `CHECK` (pas d'`ENUM`) ; GNF `bigint` (aucun montant au lot 1) ; e-mail `citext`.

**Valeurs d'énumération** (anglais, `^[A-Z][A-Z0-9_]*$`) :

| Colonne | Valeurs | Libellé FR (catalogue UI) |
|---------|---------|---------------------------|
| `tenant.status` | `ACTIVE`, `SUSPENDED`, `ARCHIVED` | Actif, Suspendu, Archivé |
| `tenant.kind` | `CUSTOMER`, `PLATFORM` | Client, Plateforme |
| `site.status` | `ACTIVE`, `INACTIVE` | Actif, Inactif |
| `site.site_type` | `MINE`, `QUARRY`, `WORKSHOP`, `DEPOT`, `PORT`, `OFFICE` | Mine, Carrière, Atelier, Dépôt, Port, Bureau |
| `user_account.status` | `INVITED`, `ACTIVE`, `DISABLED` | Invité, Actif, Désactivé |
| `vehicle.status` | `AVAILABLE`, `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED` | Disponible, En maintenance, Immobilisé, Hors service, Réformé |
| `driver.status` | `ACTIVE`, `UNAVAILABLE`, `SUSPENDED`, `INACTIVE` | Actif, Indisponible, Suspendu, Inactif |
| `driver.employment_type` | `EMPLOYEE`, `TEMP_AGENCY`, `SUBCONTRACTOR` | Employé, Intérimaire, Sous-traitant |
| `driver.unavailability_reason` | `LEAVE`, `TRAINING`, `OTHER` | Congé, Formation, Autre |
| `driver_license.status` | `VALID`, `SUSPENDED`, `WITHDRAWN` | Valide, Suspendu, Retiré |
| `driver_qualification.status` | `VALID`, `SUSPENDED`, `REVOKED` | Valide, Suspendue, Révoquée |
| `driver_qualification.qualification_type` | `DRIVING_AUTHORIZATION`, `SAFETY_TRAINING`, `OTHER` (pas `MEDICAL_FITNESS`, DB-22) | Habilitation de conduite, Formation sécurité, Autre |
| `vehicle_assignment.status` | `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED` | Planifiée, Active, Suspendue, Terminée, Annulée |
| `vehicle.ownership_type` | `OWNED`, `LEASED`, `SUBCONTRACTED` | Propre, Location, Sous-traitant |
| `vehicle.fuel_type` | `DIESEL`, `PETROL`, `ELECTRIC`, `OTHER` | Gasoil, Essence, Électrique, Autre |
| `audit_event.actor_kind` | `USER`, `SYSTEM`, `PLATFORM_SUPPORT`, `DEVICE_SYNC`, `ANONYMOUS` | |
| `audit_event.outcome` | `SUCCESS`, `DENIED`, `FAILURE` | Succès, Refusé, Échec |
| `account_token.purpose` | `INVITATION`, `PASSWORD_RESET` | Invitation, Réinitialisation |
| `vehicle_category.family` | `HAULAGE`, `LOADING_EXCAVATION`, `EARTHWORKS`, `TANKER`, `PERSONNEL_TRANSPORT`, `LIGHT_VEHICLE`, `SUPPORT_EQUIPMENT` | voir glossaire du dictionnaire §0 |

Le **glossaire unique code → libellé FR** est dans `DICTIONNAIRE_DONNEES.md` §0 ; ce tableau doit rester identique à lui.

**Nommage** (chaque contrainte est nommée explicitement, 63 octets maximum, test de contrôle) : `pk_<table>` ; `uq_<table>_<règle>` ; `fk_<enfant>__<parent>[__<colonne>]` ; `ck_<table>_<règle>` ; `ix_<table>_<colonnes>` ; `ex_<table>_<règle>` ; `tg_<table>_<objet>`. Clé primaire = `<table>_id`. SQLAlchemy : `MetaData(naming_convention=...)` pour `pk/ix/uq/ck/fk`, noms explicites pour `ex_`.

**Colonnes communes** des tables modifiables : `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`, `created_by uuid` et `updated_by uuid` (sans FK, DB-18), `row_version integer NOT NULL DEFAULT 1 CHECK (row_version >= 1)`. `created_at/updated_at/row_version` sont gérés côté serveur (§4, D-19). Pas de `archived_at` (DB-23, l'état terminal est le statut). **Clés primaires** : `uuid` v4, `DEFAULT gen_random_uuid()` sur toute table (D-20) ; le code applicatif peut fournir l'identifiant mais la base reste capable de le générer ; aucune dépendance UUID v7. Toutes les clés primaires `uuid` du §5 portent ce défaut.

**FK** : `ON DELETE RESTRICT ON UPDATE NO ACTION` partout. FK composites `(tenant_id, x_id)` vers `UNIQUE (tenant_id, x_id)` (option non retenue : clé primaire composite `(tenant_id, id)`, qui économiserait un index par table au prix d'un ORM moins naturel ; à revoir si les volumes le justifient).

## 3. Bootstrap (hors Alembic, super-utilisateur) — `infra/db/bootstrap.sql`

```sql
-- Mots de passe : injectés par variables psql (\set / \getenv), jamais dans le dépôt.
CREATE ROLE mf_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'mf_owner_password';
CREATE ROLE mf_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD :'mf_app_password';
-- mf_readonly_report : plus tard (SELECT soumis à la RLS).

CREATE DATABASE minefleet OWNER mf_owner;
\connect minefleet
REVOKE ALL ON DATABASE minefleet FROM PUBLIC;
GRANT CONNECT ON DATABASE minefleet TO mf_app;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE EXTENSION postgis;      -- non "trusted" : super-utilisateur obligatoire
CREATE EXTENSION btree_gist;
CREATE EXTENSION citext;
-- pgcrypto : non installée (inutile en PG16, DB-27).

CREATE SCHEMA app AUTHORIZATION mf_owner;
GRANT USAGE ON SCHEMA public, app TO mf_app;
GRANT SELECT ON spatial_ref_sys TO mf_app;

ALTER ROLE mf_app SET timezone = 'UTC';
ALTER ROLE mf_app SET search_path = public;
-- statement_timeout / idle_in_transaction_session_timeout : valeurs à calibrer (ST-85), non inventées ici.
-- Aucun ALTER DEFAULT PRIVILEGES accordant des droits à mf_app (DB-25).
```

Test de rôle au démarrage de l'API (ADR-002) : `rolsuper = false`, `rolbypassrls = false`, `mf_app` n'est propriétaire d'aucune table.

## 4. Fonctions et triggers génériques (migration 0001)

```sql
-- Contexte : jamais d'erreur sur valeur vide (DB-03).
CREATE FUNCTION app.current_tenant_id() RETURNS uuid
  LANGUAGE sql STABLE PARALLEL SAFE
  AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE FUNCTION app.platform_tenant_id() RETURNS uuid
  LANGUAGE sql IMMUTABLE PARALLEL SAFE
  AS $$ SELECT '00000000-0000-4000-8000-000000000001'::uuid $$;   -- constante fixe, forme UUID v4 (D-20)

CREATE FUNCTION app.is_platform_context() RETURNS boolean
  LANGUAGE sql STABLE PARALLEL SAFE
  AS $$ SELECT app.current_tenant_id() IS NOT DISTINCT FROM app.platform_tenant_id() $$;

-- Horodatage et version optimiste gérés par le serveur (DB-24).
CREATE FUNCTION app.tg_touch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at  := now();
  NEW.row_version := OLD.row_version + 1;
  RETURN NEW;
END $$;

CREATE FUNCTION app.tg_forbid_tenant_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'tenant_id is immutable on %', TG_TABLE_NAME USING ERRCODE = 'MF002';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION app.tg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (% refused)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'MF001';
END $$;

-- Mise en place standard d'une table tenant-scopée : RLS forcée, politique unique, droits, garde.
CREATE FUNCTION app.apply_tenant_rls(p_table regclass, p_grants text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', p_table);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', p_table);
  EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', p_table);
  EXECUTE format($p$CREATE POLICY tenant_isolation ON %s AS PERMISSIVE FOR ALL TO mf_app
                    USING (tenant_id = app.current_tenant_id())
                    WITH CHECK (tenant_id = app.current_tenant_id())$p$, p_table);
  EXECUTE format('REVOKE ALL ON %s FROM PUBLIC', p_table);
  EXECUTE format('GRANT %s ON %s TO mf_app', p_grants, p_table);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_forbid_tenant_change ON %s', p_table);
  EXECUTE format($t$CREATE TRIGGER tg_forbid_tenant_change BEFORE UPDATE OF tenant_id ON %s
                    FOR EACH ROW EXECUTE FUNCTION app.tg_forbid_tenant_change()$t$, p_table);
END $$;

CREATE FUNCTION app.apply_touch(p_table regclass) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('DROP TRIGGER IF EXISTS tg_touch ON %s', p_table);
  EXECUTE format('CREATE TRIGGER tg_touch BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION app.tg_touch()', p_table);
END $$;

REVOKE EXECUTE ON FUNCTION app.apply_tenant_rls(regclass, text), app.apply_touch(regclass) FROM PUBLIC;
```

Codes SQLSTATE personnalisés : `MF001` ajout seul, `MF002` immutabilité, `MF003` affectation figée, `MF004` incohérence ou changement de site interdit.

**Rôle de la RLS (D-08, rappel d'ADR-002)** : la politique utilise `app.current_tenant_id()` (`NULLIF(current_setting('app.tenant_id', true), '')::uuid`) : sans contexte, **0 ligne et aucune erreur**, y compris sur une connexion de pool réutilisée après un `COMMIT` (le paramètre retombe à la chaîne vide). Le contexte est posé par `SET LOCAL` (`set_config(..., true)`) à chaque transaction. Les partitions sont créées avec la RLS forcée (§5.4). La RLS **complète** l'autorisation applicative (rôle, portée site, filtre de repository) et ne la remplace pas ; elle ne protège pas d'une application qui fixerait elle-même un mauvais contexte.

## 5. DDL par migration

Chaque `CREATE TABLE` ci-dessous est suivi de l'appel de mise en place (`SELECT app.apply_tenant_rls(...)`, `app.apply_touch(...)`). Colonnes communes abrégées en `/*C*/` = `created_at, updated_at, created_by, updated_by, row_version` (§2). Les migrations sont regroupées par tranche (D-21) : **1a** = 0001 à 0004, **1b** = 0005 et 0006, **1c** = 0007 (voir §8).

### 5.1 Migration `0001_foundation` (tranche 1a) : fonctions, référentiels globaux, tenant

```sql
CREATE TABLE role (
  role_code      text PRIMARY KEY,
  label_fr       text NOT NULL,
  description_fr text,
  is_optional    boolean NOT NULL DEFAULT false           -- AUDITOR : rôle retenu, optionnel, lecture seule (D-10)
);
CREATE TABLE role_allowed_scope (
  role_code  text NOT NULL REFERENCES role(role_code) ON DELETE RESTRICT,
  scope_type text NOT NULL,
  CONSTRAINT pk_role_allowed_scope PRIMARY KEY (role_code, scope_type),
  CONSTRAINT ck_role_allowed_scope_type CHECK (scope_type IN ('PLATFORM','TENANT','SITE'))
);
-- Pas de tables permission / role_permission au lot 1 (D-18a) : le catalogue des permissions vit uniquement dans
-- authz_matrix.yaml (D-09) ; la base ne porte que role, role_allowed_scope et les affectations.
CREATE TABLE license_category_ref (
  code              text PRIMARY KEY,
  label_fr          text NOT NULL,
  validated_locally boolean NOT NULL DEFAULT false,
  is_active         boolean NOT NULL DEFAULT true
);

CREATE TABLE tenant (
  tenant_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             text NOT NULL,
  kind             text NOT NULL DEFAULT 'CUSTOMER',
  legal_name       text NOT NULL,
  legal_name_norm  text GENERATED ALWAYS AS (lower(regexp_replace(btrim(legal_name), '\s+', ' ', 'g'))) STORED,
  display_name     text NOT NULL,
  status           text NOT NULL DEFAULT 'ACTIVE',
  is_demo          boolean NOT NULL DEFAULT false,
  default_timezone text NOT NULL DEFAULT 'Africa/Conakry',
  default_locale   text NOT NULL DEFAULT 'fr-GN',
  country_code     char(2) NOT NULL DEFAULT 'GN',
  currency_code    char(3) NOT NULL DEFAULT 'GNF',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT uq_tenant_code            UNIQUE (code),
  CONSTRAINT uq_tenant_legal_name_norm UNIQUE (legal_name_norm),
  CONSTRAINT uq_tenant_id_kind         UNIQUE (tenant_id, kind),       -- cible de FK (DB-04)
  CONSTRAINT ck_tenant_code    CHECK (code ~ '^[a-z0-9-]{3,32}$'),
  CONSTRAINT ck_tenant_kind    CHECK (kind IN ('CUSTOMER','PLATFORM')),
  CONSTRAINT ck_tenant_status  CHECK (status IN ('ACTIVE','SUSPENDED','ARCHIVED')),
  CONSTRAINT ck_tenant_tz      CHECK (default_timezone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$'),
  CONSTRAINT ck_tenant_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_tenant_single_platform ON tenant ((true)) WHERE kind = 'PLATFORM';

-- Amorçage AVANT d'activer FORCE RLS (DB-26) : tenant plateforme et référentiels.
INSERT INTO tenant (tenant_id, code, kind, legal_name, display_name)
VALUES (app.platform_tenant_id(), 'mf-platform', 'PLATFORM', 'MINEFLEET 360 (plateforme)', 'Plateforme');

INSERT INTO role (role_code, label_fr, is_optional) VALUES
 ('PLATFORM_ADMIN','Administrateur plateforme',false), ('TENANT_ADMIN','Administrateur de tenant',false),
 ('DIRECTION','Direction générale',false),            ('OPS_MANAGER','Direction des opérations',false),
 ('DISPATCHER','Dispatcher / régulateur',false),      ('HR','Ressources humaines',false),
 ('DRIVER','Conducteur / opérateur d''engin',false),  ('WORKSHOP_CHIEF','Chef d''atelier',false),
 ('MECHANIC','Mécanicien',false),                     ('STOREKEEPER','Magasinier',false),
 ('FUEL_MANAGER','Responsable carburant',false),      ('HSE','Responsable HSE',false),
 ('FINANCE','Finance / contrôle de gestion',false),   ('AUDITOR','Auditeur',true);
INSERT INTO role_allowed_scope (role_code, scope_type) VALUES
 ('PLATFORM_ADMIN','PLATFORM'),
 ('TENANT_ADMIN','TENANT'), ('DIRECTION','TENANT'), ('AUDITOR','TENANT'),
 ('OPS_MANAGER','TENANT'),('OPS_MANAGER','SITE'), ('DISPATCHER','SITE'),   -- DISPATCHER : portée SITE uniquement (D-10)
 ('HR','TENANT'),('HR','SITE'), ('WORKSHOP_CHIEF','TENANT'),('WORKSHOP_CHIEF','SITE'),
 ('MECHANIC','TENANT'),('MECHANIC','SITE'), ('STOREKEEPER','TENANT'),('STOREKEEPER','SITE'),
 ('FUEL_MANAGER','TENANT'),('FUEL_MANAGER','SITE'), ('HSE','TENANT'),('HSE','SITE'),
 ('FINANCE','TENANT'),('FINANCE','SITE'),
 ('DRIVER','SITE');                                   -- aucun écran conducteur au lot 1 (C-12) ; portée SITE (DB-13)
INSERT INTO license_category_ref (code, label_fr) VALUES
 ('A','Motocyclettes'),('B','Véhicules légers'),('C','Poids lourds (porteurs)'),
 ('D','Transport en commun de personnes'),('E','Ensemble avec remorque / semi-remorque');
-- validated_locally = false : référentiel à valider localement (RM-022, C-07) ; valeurs fictives en développement.

-- Droits des référentiels globaux : lecture seule.
REVOKE ALL ON role, role_allowed_scope, license_category_ref FROM PUBLIC;
GRANT SELECT ON role, role_allowed_scope, license_category_ref TO mf_app;

-- tenant : politiques dédiées (§6.1)
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON tenant FOR SELECT TO mf_app USING (
     tenant_id = app.current_tenant_id()
  OR app.is_platform_context()
  OR code = NULLIF(current_setting('app.login_tenant_code', true), ''));
CREATE POLICY tenant_insert ON tenant FOR INSERT TO mf_app WITH CHECK (app.is_platform_context());
CREATE POLICY tenant_update ON tenant FOR UPDATE TO mf_app
  USING (tenant_id = app.current_tenant_id() OR app.is_platform_context())
  WITH CHECK (tenant_id = app.current_tenant_id() OR app.is_platform_context());
REVOKE ALL ON tenant FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON tenant TO mf_app;

CREATE FUNCTION app.tg_tenant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT app.is_platform_context() AND
     (NEW.code, NEW.kind, NEW.status, NEW.is_demo, NEW.legal_name)
       IS DISTINCT FROM (OLD.code, OLD.kind, OLD.status, OLD.is_demo, OLD.legal_name) THEN
    RAISE EXCEPTION 'tenant governance fields require platform context' USING ERRCODE = 'MF002';
  END IF;
  IF NEW.kind IS DISTINCT FROM OLD.kind THEN
    RAISE EXCEPTION 'tenant.kind is immutable' USING ERRCODE = 'MF002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_tenant_guard BEFORE UPDATE ON tenant FOR EACH ROW EXECUTE FUNCTION app.tg_tenant_guard();
SELECT app.apply_touch('tenant');
```

### 5.2 Migration `0002_organization` (tranche 1a) : `site`

```sql
CREATE TABLE site (
  site_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code      text NOT NULL,
  name      text NOT NULL,
  site_type text NOT NULL,
  timezone  text,                                  -- NULL = fuseau du tenant
  location  geography(Point, 4326),
  status    text NOT NULL DEFAULT 'ACTIVE',
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_site__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_site_tenant_site UNIQUE (tenant_id, site_id),
  CONSTRAINT uq_site_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_site_type   CHECK (site_type IN ('MINE','QUARRY','WORKSHOP','DEPOT','PORT','OFFICE')),
  CONSTRAINT ck_site_status CHECK (status IN ('ACTIVE','INACTIVE')),
  CONSTRAINT ck_site_tz     CHECK (timezone IS NULL OR timezone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$'),
  CONSTRAINT ck_site_loc    CHECK (location IS NULL OR NOT (ST_X(location::geometry) = 0 AND ST_Y(location::geometry) = 0)),
  CONSTRAINT ck_site_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('site', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('site');
```

### 5.3 Migration `0003_identity` (tranche 1a)

```sql
CREATE TABLE user_account (
  user_account_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL,
  email                citext NOT NULL,
  display_name         text NOT NULL,
  phone                text,
  password_hash        text,                         -- argon2id ; jamais exposé ni journalisé
  mfa_enabled          boolean NOT NULL DEFAULT false,
  mfa_secret_encrypted bytea,
  status               text NOT NULL DEFAULT 'INVITED',
  failed_login_count   integer NOT NULL DEFAULT 0,
  locked_until         timestamptz,                  -- état "verrouillé" = locked_until > now() (dérivé)
  last_login_at        timestamptz,
  must_change_password boolean NOT NULL DEFAULT true,
  ui_locale            text NOT NULL DEFAULT 'fr-GN',
  anonymized_at        timestamptz,
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_user_account__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_user_account_tenant_user  UNIQUE (tenant_id, user_account_id),
  CONSTRAINT uq_user_account_tenant_email UNIQUE (tenant_id, email),
  CONSTRAINT ck_user_account_status CHECK (status IN ('INVITED','ACTIVE','DISABLED')),
  CONSTRAINT ck_user_account_email  CHECK (position('@' in email::text) > 1),
  CONSTRAINT ck_user_account_phone  CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
  CONSTRAINT ck_user_account_failed CHECK (failed_login_count >= 0),
  CONSTRAINT ck_user_account_mfa    CHECK (NOT mfa_enabled OR mfa_secret_encrypted IS NOT NULL),
  CONSTRAINT ck_user_account_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('user_account', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('user_account');

CREATE TABLE user_role_assignment (
  user_role_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  tenant_kind     text NOT NULL,                     -- dénormalisation contrôlée par FK (DB-04)
  user_account_id uuid NOT NULL,
  role_code       text NOT NULL,
  scope_type      text NOT NULL,
  site_id         uuid,
  valid_from      timestamptz NOT NULL DEFAULT now(),
  valid_to        timestamptz,
  granted_by      uuid NOT NULL,
  revoked_at      timestamptz,
  revoked_by      uuid,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_ura__tenant_kind FOREIGN KEY (tenant_id, tenant_kind) REFERENCES tenant (tenant_id, kind) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__user        FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__site        FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__role_scope  FOREIGN KEY (role_code, scope_type) REFERENCES role_allowed_scope (role_code, scope_type) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__granted_by  FOREIGN KEY (granted_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ura__revoked_by  FOREIGN KEY (revoked_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_ura_scope_site     CHECK ((scope_type = 'SITE') = (site_id IS NOT NULL)),
  CONSTRAINT ck_ura_scope_platform CHECK ((scope_type = 'PLATFORM') = (tenant_kind = 'PLATFORM')),
  CONSTRAINT ck_ura_validity       CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT ck_ura_revocation     CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)),
  CONSTRAINT ck_ura_version        CHECK (row_version >= 1),
  CONSTRAINT ex_ura_no_duplicate EXCLUDE USING gist (
      user_account_id WITH =, role_code WITH =, scope_type WITH =,
      (COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      tstzrange(valid_from, valid_to, '[)') WITH &&)
    WHERE (revoked_at IS NULL)
);
CREATE INDEX ix_ura_tenant_user ON user_role_assignment (tenant_id, user_account_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_ura_tenant_site ON user_role_assignment (tenant_id, site_id) WHERE site_id IS NOT NULL;
SELECT app.apply_tenant_rls('user_role_assignment', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('user_role_assignment');
-- "Dernier TENANT_ADMIN actif" : verrou applicatif (SELECT ... FOR UPDATE) + test ; non exprimable par contrainte.

CREATE TABLE account_token (
  account_token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  user_account_id  uuid NOT NULL,
  purpose          text NOT NULL,
  token_hash       bytea NOT NULL,                   -- SHA-256 d'un secret aléatoire de 256 bits ; jamais le jeton
  expires_at       timestamptz NOT NULL,
  consumed_at      timestamptz,
  revoked_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  created_by       uuid,
  CONSTRAINT fk_account_token__user FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_account_token_hash  UNIQUE (tenant_id, token_hash),
  CONSTRAINT ck_account_token_purpose CHECK (purpose IN ('INVITATION','PASSWORD_RESET')),
  CONSTRAINT ck_account_token_hash    CHECK (octet_length(token_hash) = 32),
  CONSTRAINT ck_account_token_expiry  CHECK (expires_at > created_at)
);
CREATE UNIQUE INDEX uq_account_token_open ON account_token (tenant_id, user_account_id, purpose)
  WHERE consumed_at IS NULL AND revoked_at IS NULL;      -- un seul jeton ouvert par finalité
SELECT app.apply_tenant_rls('account_token', 'SELECT, INSERT, UPDATE, DELETE');

CREATE TABLE auth_session (
  auth_session_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),           -- = session_id du jeton d'accès (ADR-003)
  tenant_id             uuid NOT NULL,
  user_account_id       uuid NOT NULL,
  refresh_hash_current  bytea NOT NULL,
  refresh_hash_previous bytea,                      -- détection de réutilisation + fenêtre de grâce
  rotated_at            timestamptz,
  amr                   text[] NOT NULL DEFAULT '{pwd}',
  ip_address            inet,
  user_agent            text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  last_seen_at          timestamptz NOT NULL DEFAULT now(),
  expires_at            timestamptz NOT NULL,       -- durée absolue : paramètre (non fixée)
  revoked_at            timestamptz,
  revoked_reason        text,
  CONSTRAINT fk_auth_session__user FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_auth_session_refresh UNIQUE (tenant_id, refresh_hash_current),
  CONSTRAINT ck_auth_session_hash CHECK (octet_length(refresh_hash_current) = 32),
  CONSTRAINT ck_auth_session_expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_auth_session_user ON auth_session (tenant_id, user_account_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_auth_session_expiry ON auth_session (expires_at);
SELECT app.apply_tenant_rls('auth_session', 'SELECT, INSERT, UPDATE, DELETE');
-- Limite assumée : seules les deux dernières empreintes sont conservées ; une réutilisation plus ancienne
-- renvoie 401 sans révocation de la famille. Table d'historique de jetons possible plus tard.
```

### 5.4 Migration `0004_audit` (tranche 1a)

Schéma **unique** d'`audit_event`, identique à `DICTIONNAIRE_DONNEES.md` §16 et à ADR-005 (D-17) : écrit dans la même transaction que la mutation, **partitionné par mois dès sa création** (jamais converti après coup : DB-08), `mf_app` en `INSERT`/`SELECT` seulement et trigger anti `UPDATE`/`DELETE`/`TRUNCATE`. Pas de chaînage de hash en ligne (D-16) : `prev_hash`/`row_hash` restent NULL. Le `tenant_id` étant `NOT NULL`, une connexion échouée sur un code d'espace **inconnu** n'écrit pas d'`audit_event` (aucun tenant) : elle est journalisée en log structuré (événement de sécurité, D-05).

```sql
CREATE SEQUENCE audit_event_seq;

CREATE TABLE audit_event (
  audit_event_id     uuid NOT NULL DEFAULT gen_random_uuid(),   -- UUID v4 (D-20) ; l'ordre est porté par audit_seq / occurred_at
  audit_seq          bigint NOT NULL DEFAULT nextval('audit_event_seq'),
  tenant_id          uuid NOT NULL,
  site_id            uuid,
  occurred_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  actor_user_id      uuid,
  actor_kind         text NOT NULL,
  support_session_id uuid,
  action             text NOT NULL,
  entity_type        text NOT NULL,
  entity_id          uuid,
  outcome            text NOT NULL,
  reason             text,
  changed_fields     text[],                        -- noms de champs, sensibles inclus (jamais leurs valeurs)
  before_data        jsonb,                         -- sans champ sensible ni secret ni GPS brut
  after_data         jsonb,
  request_id         uuid,
  ip_address         inet,                          -- donnée personnelle : rétention C-09
  user_agent         text,
  prev_hash          bytea,                         -- scellement asynchrone (DB-20), nullable
  row_hash           bytea,
  CONSTRAINT pk_audit_event PRIMARY KEY (audit_event_id, occurred_at),
  CONSTRAINT fk_audit_event__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_audit_event__actor  FOREIGN KEY (actor_user_id) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_audit_actor_kind CHECK (actor_kind IN ('USER','SYSTEM','PLATFORM_SUPPORT','DEVICE_SYNC','ANONYMOUS')),
  CONSTRAINT ck_audit_actor_ref  CHECK (actor_kind NOT IN ('USER','PLATFORM_SUPPORT') OR actor_user_id IS NOT NULL),
  CONSTRAINT ck_audit_support    CHECK ((actor_kind = 'PLATFORM_SUPPORT') = (support_session_id IS NOT NULL)),
  CONSTRAINT ck_audit_outcome    CHECK (outcome IN ('SUCCESS','DENIED','FAILURE')),
  CONSTRAINT ck_audit_action     CHECK (action ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$')
) PARTITION BY RANGE (occurred_at);

CREATE TABLE audit_event_default PARTITION OF audit_event DEFAULT;   -- doit rester vide (alerte)

CREATE INDEX ix_audit_event_tenant_time   ON audit_event (tenant_id, occurred_at DESC);
CREATE INDEX ix_audit_event_tenant_entity ON audit_event (tenant_id, entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_audit_event_tenant_actor  ON audit_event (tenant_id, actor_user_id, occurred_at DESC) WHERE actor_user_id IS NOT NULL;
CREATE INDEX ix_audit_event_tenant_site   ON audit_event (tenant_id, site_id, occurred_at DESC) WHERE site_id IS NOT NULL;
CREATE INDEX ix_audit_event_tenant_id     ON audit_event (tenant_id, audit_event_id);
CREATE INDEX ix_audit_event_request       ON audit_event (tenant_id, request_id) WHERE request_id IS NOT NULL;

ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_select ON audit_event FOR SELECT TO mf_app USING (tenant_id = app.current_tenant_id());
CREATE POLICY audit_insert ON audit_event FOR INSERT TO mf_app WITH CHECK (tenant_id = app.current_tenant_id());
-- Aucune politique UPDATE/DELETE : refus par la RLS en plus des droits.
REVOKE ALL ON audit_event FROM PUBLIC;
GRANT SELECT, INSERT ON audit_event TO mf_app;
GRANT USAGE ON SEQUENCE audit_event_seq TO mf_app;
CREATE TRIGGER tg_audit_event_append_only BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
CREATE TRIGGER tg_audit_event_no_truncate BEFORE TRUNCATE ON audit_event
  FOR EACH STATEMENT EXECUTE FUNCTION app.tg_append_only();

-- Partitions mensuelles : fonction d'exploitation, exécutée par mf_owner (migration puis tâche planifiée).
CREATE FUNCTION app.ensure_audit_partitions(p_months_ahead integer DEFAULT 12) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE m date; part text; n integer := 0;
BEGIN
  FOR i IN 0..p_months_ahead LOOP
    m := (date_trunc('month', now() AT TIME ZONE 'UTC') + make_interval(months => i))::date;
    part := format('audit_event_y%sm%s', to_char(m, 'YYYY'), to_char(m, 'MM'));
    IF to_regclass(format('public.%I', part)) IS NULL THEN
      EXECUTE format('CREATE TABLE public.%I PARTITION OF public.audit_event FOR VALUES FROM (%L) TO (%L)',
                     part, (m::timestamp AT TIME ZONE 'UTC'), ((m + interval '1 month')::timestamp AT TIME ZONE 'UTC'));
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', part);
      EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', part);
      EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, mf_app', part);   -- DB-25
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION app.ensure_audit_partitions(integer) FROM PUBLIC;
ALTER TABLE audit_event_default ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event_default FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE audit_event_default FROM PUBLIC, mf_app;
SELECT app.ensure_audit_partitions(12);
-- Purge : DETACH PARTITION puis archivage/DROP par mf_owner, sur procédure approuvée ; jamais de DELETE.
```

**`idempotency_record` n'est pas créée au lot 1** (D-14) : pas d'en-tête `Idempotency-Key` ; les doublons de création sont empêchés par les contraintes d'unicité (`uq_*`) et d'exclusion (`ex_*`), mappées en `409` (§7). La table, l'en-tête et les critères d'acceptation associés arrivent avec le mode hors ligne (lot 4) ; esquisse en §11.

### 5.5 Migration `0005_fleet` (tranche 1b)

```sql
CREATE TABLE vehicle_category (
  vehicle_category_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code      text NOT NULL,
  label_fr  text NOT NULL,
  family    text NOT NULL,
  requires_driver                  boolean NOT NULL DEFAULT true,
  requires_internal_authorization  boolean NOT NULL DEFAULT true,
  has_odometer   boolean NOT NULL DEFAULT false,
  has_hour_meter boolean NOT NULL DEFAULT false,
  is_system boolean NOT NULL DEFAULT false,         -- copie du jeu initial ; code immuable
  is_active boolean NOT NULL DEFAULT true,
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_vehicle_category__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_vehicle_category_tenant_id   UNIQUE (tenant_id, vehicle_category_id),
  CONSTRAINT uq_vehicle_category_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_vehicle_category_code   CHECK (code ~ '^[A-Z0-9_]{3,40}$'),
  CONSTRAINT ck_vehicle_category_family CHECK (family IN ('HAULAGE','LOADING_EXCAVATION','EARTHWORKS','TANKER',
                                                          'PERSONNEL_TRANSPORT','LIGHT_VEHICLE','SUPPORT_EQUIPMENT')),
  CONSTRAINT ck_vehicle_category_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('vehicle_category', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('vehicle_category');

CREATE TABLE vehicle_category_license_category (
  tenant_id            uuid NOT NULL,
  vehicle_category_id  uuid NOT NULL,
  license_category_code text NOT NULL REFERENCES license_category_ref (code) ON DELETE RESTRICT,
  CONSTRAINT pk_vcat_license PRIMARY KEY (tenant_id, vehicle_category_id, license_category_code),
  CONSTRAINT fk_vcat_license__category FOREIGN KEY (tenant_id, vehicle_category_id)
    REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT
);
-- DELETE autorisé : configuration, tracée par l'audit ; aucune donnée personnelle.
SELECT app.apply_tenant_rls('vehicle_category_license_category', 'SELECT, INSERT, DELETE');

CREATE TABLE vehicle (
  vehicle_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  site_id             uuid NOT NULL,
  vehicle_category_id uuid NOT NULL,
  fleet_number        text NOT NULL,
  fleet_number_norm   text GENERATED ALWAYS AS (lower(btrim(fleet_number))) STORED,
  registration_number text,
  registration_norm   text GENERATED ALWAYS AS (upper(regexp_replace(registration_number, '[\s\-]', '', 'g'))) STORED,
  serial_number       text,
  serial_key          text GENERATED ALWAYS AS (lower(coalesce(make, '')) || '|' || lower(btrim(serial_number))) STORED,
  make text, model text, model_year smallint,
  ownership_type text NOT NULL DEFAULT 'OWNED',
  fuel_type      text,
  rated_payload_kg integer,                          -- capacité NOMINALE, jamais une mesure (H10)
  status             text NOT NULL DEFAULT 'AVAILABLE',
  status_reason_code text,
  status_changed_at  timestamptz NOT NULL DEFAULT now(),
  commissioned_on  date,
  decommissioned_on date,
  notes text,                                        -- aucune donnée personnelle
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_vehicle__tenant   FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vehicle__site     FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vehicle__category FOREIGN KEY (tenant_id, vehicle_category_id) REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT uq_vehicle_tenant_id           UNIQUE (tenant_id, vehicle_id),
  CONSTRAINT uq_vehicle_tenant_fleet_number UNIQUE (tenant_id, fleet_number_norm),     -- totale : jamais réutilisé (RM-010)
  CONSTRAINT uq_vehicle_tenant_registration UNIQUE (tenant_id, registration_norm),     -- NULL distincts
  CONSTRAINT uq_vehicle_tenant_serial       UNIQUE (tenant_id, serial_key),
  CONSTRAINT ck_vehicle_fleet_number CHECK (fleet_number ~ '^[^\s]{1,30}$'),
  CONSTRAINT ck_vehicle_registration CHECK (registration_number IS NULL OR registration_norm <> ''),
  CONSTRAINT ck_vehicle_status    CHECK (status IN ('AVAILABLE','IN_MAINTENANCE','IMMOBILIZED','OUT_OF_SERVICE','RETIRED')),
  CONSTRAINT ck_vehicle_reason    CHECK (status NOT IN ('IMMOBILIZED','OUT_OF_SERVICE','RETIRED') OR status_reason_code IS NOT NULL),
  CONSTRAINT ck_vehicle_retired   CHECK ((status = 'RETIRED') = (decommissioned_on IS NOT NULL)),
  CONSTRAINT ck_vehicle_ownership CHECK (ownership_type IN ('OWNED','LEASED','SUBCONTRACTED')),
  CONSTRAINT ck_vehicle_fuel      CHECK (fuel_type IS NULL OR fuel_type IN ('DIESEL','PETROL','ELECTRIC','OTHER')),
  CONSTRAINT ck_vehicle_payload   CHECK (rated_payload_kg IS NULL OR rated_payload_kg > 0),
  CONSTRAINT ck_vehicle_year      CHECK (model_year IS NULL OR model_year BETWEEN 1950 AND 2100),
  CONSTRAINT ck_vehicle_version   CHECK (row_version >= 1)
);
CREATE INDEX ix_vehicle_tenant_site_status ON vehicle (tenant_id, site_id, status);
CREATE INDEX ix_vehicle_tenant_category    ON vehicle (tenant_id, vehicle_category_id);
SELECT app.apply_tenant_rls('vehicle', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('vehicle');

CREATE TABLE vehicle_status_history (                 -- ajout seul, alimentée par trigger (DB-16)
  vehicle_status_history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  vehicle_id  uuid NOT NULL,
  from_status text,
  to_status   text NOT NULL,
  reason_code text,
  changed_at  timestamptz NOT NULL,
  changed_by  uuid,
  CONSTRAINT fk_vsh__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT ck_vsh_to CHECK (to_status IN ('AVAILABLE','IN_MAINTENANCE','IMMOBILIZED','OUT_OF_SERVICE','RETIRED'))
);
CREATE INDEX ix_vsh_vehicle_time ON vehicle_status_history (tenant_id, vehicle_id, changed_at DESC);
SELECT app.apply_tenant_rls('vehicle_status_history', 'SELECT, INSERT');
CREATE TRIGGER tg_vsh_append_only BEFORE UPDATE OR DELETE ON vehicle_status_history
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE FUNCTION app.tg_vehicle_status_before() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN NEW.status_changed_at := now(); END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION app.tg_vehicle_status_after() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO vehicle_status_history (tenant_id, vehicle_id, from_status, to_status, reason_code, changed_at, changed_by)
    VALUES (NEW.tenant_id, NEW.vehicle_id, NULL, NEW.status, NEW.status_reason_code, NEW.status_changed_at, NEW.created_by);
  ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO vehicle_status_history (tenant_id, vehicle_id, from_status, to_status, reason_code, changed_at, changed_by)
    VALUES (NEW.tenant_id, NEW.vehicle_id, OLD.status, NEW.status, NEW.status_reason_code, NEW.status_changed_at, NEW.updated_by);
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER tg_vehicle_status_before BEFORE UPDATE ON vehicle FOR EACH ROW EXECUTE FUNCTION app.tg_vehicle_status_before();
CREATE TRIGGER tg_vehicle_status_after  AFTER INSERT OR UPDATE OF status ON vehicle FOR EACH ROW EXECUTE FUNCTION app.tg_vehicle_status_after();
-- Ordre alphabétique des triggers BEFORE : tg_forbid_tenant_change, tg_touch, tg_vehicle_status_before (sans dépendance mutuelle).
-- Les transitions autorisées (machine à états RM-014) restent applicatives ; RETIRED est terminal (D-02, C-13) : aucune réactivation au lot 1.
-- Le refus (409) d'un changement de statut tant qu'une affectation PLANNED/ACTIVE existe (D-11, RM-017) est applicatif (tranche 1c).
```

Jeu initial de `vehicle_category` (copié à la création du tenant ; correspondance des codes, DB-01) :

| Ancien code (dictionnaire) | Code technique | Famille |
|----------------------------|----------------|---------|
| `CAMION_BENNE_ARTICULE` | `ARTICULATED_DUMP_TRUCK` | `HAULAGE` |
| `CAMION_BENNE_RIGIDE` | `RIGID_DUMP_TRUCK` | `HAULAGE` |
| `CAMION_BENNE_ROUTIER` | `ROAD_DUMP_TRUCK` | `HAULAGE` |
| `PELLE_HYDRAULIQUE` | `HYDRAULIC_EXCAVATOR` | `LOADING_EXCAVATION` |
| `CHARGEUSE_SUR_PNEUS` | `WHEEL_LOADER` | `LOADING_EXCAVATION` |
| `BULLDOZER` | `BULLDOZER` | `EARTHWORKS` |
| `NIVELEUSE` | `MOTOR_GRADER` | `EARTHWORKS` |
| `COMPACTEUR` | `COMPACTOR` | `EARTHWORKS` |
| `CITERNE_CARBURANT` | `FUEL_TANKER` | `TANKER` |
| `CITERNE_EAU` | `WATER_TANKER` | `TANKER` |
| `PORTE_ENGINS` | `LOWBED_TRAILER` | `SUPPORT_EQUIPMENT` |
| `CHARIOT_ELEVATEUR` | `FORKLIFT_TELEHANDLER` | `SUPPORT_EQUIPMENT` |
| `VEHICULE_LEGER` | `LIGHT_VEHICLE` | `LIGHT_VEHICLE` |
| `BUS_PERSONNEL` | `PERSONNEL_BUS` | `PERSONNEL_TRANSPORT` |
| `GROUPE_ELECTROGENE` | `GENERATOR_LIGHTING_TOWER` | `SUPPORT_EQUIPMENT` |

Les drapeaux (conducteur, habilitation, compteurs) et les catégories de permis liées (table de jonction) sont ceux du dictionnaire §8, hypothèses à valider avec le client (C-07) ; valeurs fictives en développement.

### 5.6 Migration `0006_workforce` (tranche 1b)

```sql
CREATE TABLE driver (
  driver_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  site_id          uuid NOT NULL,                    -- site de rattachement (ex home_site_id, DB-17)
  user_account_id  uuid,
  employee_number  text NOT NULL,
  last_name        text NOT NULL,
  first_name       text NOT NULL,
  phone            text,
  employment_type  text NOT NULL DEFAULT 'EMPLOYEE',
  external_company_name text,
  hire_date date, exit_date date,
  status                 text NOT NULL DEFAULT 'ACTIVE',
  unavailability_reason  text,
  unavailable_until      date,
  suspension_reason_code text,                       -- visible HR/HSE seulement (masquage applicatif)
  anonymized_at          timestamptz,
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  -- date_of_birth, adresse, pièce d'identité, aptitude médicale : absents du lot 1 (DB-22).
  CONSTRAINT fk_driver__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver__site   FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver__user   FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_driver_tenant_id       UNIQUE (tenant_id, driver_id),
  CONSTRAINT uq_driver_tenant_employee UNIQUE (tenant_id, employee_number),
  CONSTRAINT uq_driver_tenant_user     UNIQUE (tenant_id, user_account_id),          -- 1:1 au plus (RM-027) ; NULL distincts
  CONSTRAINT ck_driver_status   CHECK (status IN ('ACTIVE','UNAVAILABLE','SUSPENDED','INACTIVE')),
  CONSTRAINT ck_driver_employment CHECK (employment_type IN ('EMPLOYEE','TEMP_AGENCY','SUBCONTRACTOR')),
  CONSTRAINT ck_driver_external CHECK (employment_type <> 'SUBCONTRACTOR' OR external_company_name IS NOT NULL),
  CONSTRAINT ck_driver_unavail  CHECK ((status = 'UNAVAILABLE') = (unavailability_reason IS NOT NULL)),
  CONSTRAINT ck_driver_unavail_reason CHECK (unavailability_reason IS NULL OR unavailability_reason IN ('LEAVE','TRAINING','OTHER')),
  CONSTRAINT ck_driver_suspension CHECK ((status = 'SUSPENDED') = (suspension_reason_code IS NOT NULL)),
  CONSTRAINT ck_driver_exit     CHECK ((status = 'INACTIVE') = (exit_date IS NOT NULL)),
  CONSTRAINT ck_driver_dates    CHECK (exit_date IS NULL OR hire_date IS NULL OR exit_date >= hire_date),
  CONSTRAINT ck_driver_phone    CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
  CONSTRAINT ck_driver_version  CHECK (row_version >= 1)
);
CREATE INDEX ix_driver_tenant_site_status ON driver (tenant_id, site_id, status);
CREATE INDEX ix_driver_tenant_name        ON driver (tenant_id, lower(last_name), lower(first_name));
SELECT app.apply_tenant_rls('driver', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('driver');

CREATE TABLE driver_license (
  driver_license_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  driver_id     uuid NOT NULL,
  license_number text NOT NULL,                      -- masqué hors HR ; jamais journalisé ni dans l'audit
  category_code  text NOT NULL REFERENCES license_category_ref (code) ON DELETE RESTRICT,
  issuing_authority text,
  issue_date  date NOT NULL,
  expiry_date date NOT NULL,
  status      text NOT NULL DEFAULT 'VALID',         -- statut administratif ; l'expiration est calculée
  status_note text,
  document_reference text,
  verified_by uuid, verified_at timestamptz,
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_driver_license__driver FOREIGN KEY (tenant_id, driver_id) REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver_license__verified_by FOREIGN KEY (verified_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_driver_license_tenant_id UNIQUE (tenant_id, driver_license_id),
  CONSTRAINT uq_driver_license_issue UNIQUE (tenant_id, driver_id, license_number, category_code, issue_date),  -- DB-11
  CONSTRAINT ck_driver_license_dates  CHECK (expiry_date > issue_date),
  CONSTRAINT ck_driver_license_status CHECK (status IN ('VALID','SUSPENDED','WITHDRAWN')),
  CONSTRAINT ck_driver_license_verif  CHECK ((verified_by IS NULL) = (verified_at IS NULL)),
  CONSTRAINT ck_driver_license_version CHECK (row_version >= 1)
);
CREATE INDEX ix_driver_license_driver ON driver_license (tenant_id, driver_id, category_code, expiry_date DESC);
CREATE INDEX ix_driver_license_expiry ON driver_license (tenant_id, expiry_date) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('driver_license', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('driver_license');

CREATE TABLE driver_qualification (
  driver_qualification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  driver_id  uuid NOT NULL,
  qualification_type  text NOT NULL,
  vehicle_category_id uuid,
  site_id             uuid,                          -- NULL = valable tout le tenant [A] RM-055
  valid_from date NOT NULL,
  valid_to   date,                                   -- NULL = sans échéance (déconseillé), fin incluse
  status     text NOT NULL DEFAULT 'VALID',
  issued_by_name text, reference text, restrictions text,
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_dq__driver   FOREIGN KEY (tenant_id, driver_id) REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dq__category FOREIGN KEY (tenant_id, vehicle_category_id) REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dq__site     FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT uq_dq_tenant_id UNIQUE (tenant_id, driver_qualification_id),
  CONSTRAINT ck_dq_type    CHECK (qualification_type IN ('DRIVING_AUTHORIZATION','SAFETY_TRAINING','OTHER')),
  CONSTRAINT ck_dq_status  CHECK (status IN ('VALID','SUSPENDED','REVOKED')),
  CONSTRAINT ck_dq_category CHECK (qualification_type <> 'DRIVING_AUTHORIZATION' OR vehicle_category_id IS NOT NULL),
  CONSTRAINT ck_dq_dates   CHECK (valid_to IS NULL OR valid_to >= valid_from),
  CONSTRAINT ck_dq_version CHECK (row_version >= 1),
  CONSTRAINT ex_dq_no_overlap EXCLUDE USING gist (                                    -- DB-10
      driver_id WITH =, qualification_type WITH =,
      (COALESCE(vehicle_category_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      (COALESCE(site_id,             '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      daterange(valid_from, valid_to, '[]') WITH &&)
    WHERE (status = 'VALID')
);
CREATE INDEX ix_dq_driver ON driver_qualification (tenant_id, driver_id, valid_to);
CREATE INDEX ix_dq_expiry ON driver_qualification (tenant_id, valid_to) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('driver_qualification', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('driver_qualification');
```

### 5.7 Migration `0007_assignment` (tranche 1c)

```sql
CREATE TABLE vehicle_assignment (
  vehicle_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  site_id    uuid NOT NULL,                           -- site du véhicule à la création, figé (RM-042, RM-052)
  vehicle_id uuid NOT NULL,
  driver_id  uuid NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_to   timestamptz,                             -- exclusive ; NULL = ouverte
  valid_during tstzrange GENERATED ALWAYS AS (tstzrange(valid_from, valid_to, '[)')) STORED,
  shift_code    text,                                 -- informatif (RM-034)
  status        text NOT NULL DEFAULT 'PLANNED',
  status_reason text,
  eligibility_snapshot jsonb NOT NULL,                -- identifiants et dates seulement (DB-41)
  -- Pas de colonne approved_by : ni dérogation d'éligibilité ni antidatage au lot 1 (D-13).
  /*C*/ created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        created_by uuid NOT NULL, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT fk_va__site    FOREIGN KEY (tenant_id, site_id)    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_va__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_va__driver  FOREIGN KEY (tenant_id, driver_id)  REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT uq_va_tenant_id UNIQUE (tenant_id, vehicle_assignment_id),
  CONSTRAINT ck_va_interval CHECK (valid_to IS NULL OR valid_to > valid_from),       -- évite l'intervalle vide (DB-09)
  CONSTRAINT ck_va_status   CHECK (status IN ('PLANNED','ACTIVE','SUSPENDED','COMPLETED','CANCELLED')),
  CONSTRAINT ck_va_reason   CHECK (status NOT IN ('SUSPENDED','COMPLETED','CANCELLED') OR status_reason IS NOT NULL),
  CONSTRAINT ck_va_completed CHECK (status <> 'COMPLETED' OR valid_to IS NOT NULL),  -- fin réelle tronquée
  CONSTRAINT ck_va_snapshot CHECK (jsonb_typeof(eligibility_snapshot) = 'object'),
  CONSTRAINT ck_va_version  CHECK (row_version >= 1),
  CONSTRAINT ex_va_vehicle_no_overlap EXCLUDE USING gist (vehicle_id WITH =, valid_during WITH &&) WHERE (status <> 'CANCELLED'),
  CONSTRAINT ex_va_driver_no_overlap  EXCLUDE USING gist (driver_id  WITH =, valid_during WITH &&) WHERE (status <> 'CANCELLED')
);
CREATE INDEX ix_va_vehicle_hist ON vehicle_assignment (tenant_id, vehicle_id, valid_from DESC);
CREATE INDEX ix_va_driver_hist  ON vehicle_assignment (tenant_id, driver_id,  valid_from DESC);
CREATE INDEX ix_va_site_status  ON vehicle_assignment (tenant_id, site_id, status);
CREATE INDEX ix_va_open         ON vehicle_assignment (tenant_id, status, valid_from) WHERE status IN ('PLANNED','ACTIVE','SUSPENDED');
SELECT app.apply_tenant_rls('vehicle_assignment', 'SELECT, INSERT, UPDATE'); SELECT app.apply_touch('vehicle_assignment');

CREATE FUNCTION app.tg_va_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_vehicle_site uuid; v_driver_site uuid;
BEGIN
  IF TG_OP = 'INSERT' THEN
    -- Même site strict (D-13, RM-042) : affectation = site du véhicule = site de rattachement du conducteur.
    SELECT site_id INTO v_vehicle_site FROM vehicle WHERE tenant_id = NEW.tenant_id AND vehicle_id = NEW.vehicle_id;
    SELECT site_id INTO v_driver_site  FROM driver  WHERE tenant_id = NEW.tenant_id AND driver_id  = NEW.driver_id;
    IF v_vehicle_site IS DISTINCT FROM NEW.site_id OR v_driver_site IS DISTINCT FROM NEW.site_id THEN
      RAISE EXCEPTION 'assignment, vehicle and driver must share the same site' USING ERRCODE = 'MF004';
    END IF;
  ELSE
    IF OLD.status IN ('COMPLETED','CANCELLED') THEN                                  -- RM-040
      RAISE EXCEPTION 'terminal assignment is immutable' USING ERRCODE = 'MF003';
    END IF;
    IF (NEW.vehicle_id, NEW.driver_id, NEW.site_id) IS DISTINCT FROM (OLD.vehicle_id, OLD.driver_id, OLD.site_id) THEN
      RAISE EXCEPTION 'assignment vehicle, driver and site are immutable' USING ERRCODE = 'MF003';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_va_guard BEFORE INSERT OR UPDATE ON vehicle_assignment FOR EACH ROW EXECUTE FUNCTION app.tg_va_guard();

-- Changement de site d'un véhicule ou d'un conducteur : refusé tant qu'une affectation ouverte existe (D-13, RM-051).
-- Triggers posés sur vehicle et driver par cette migration (0007), car ils lisent vehicle_assignment.
CREATE FUNCTION app.tg_site_change_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.site_id IS DISTINCT FROM OLD.site_id AND EXISTS (
       SELECT 1 FROM vehicle_assignment va
        WHERE va.tenant_id = OLD.tenant_id
          AND ((TG_TABLE_NAME = 'vehicle' AND va.vehicle_id = OLD.vehicle_id)
            OR (TG_TABLE_NAME = 'driver'  AND va.driver_id  = OLD.driver_id))
          AND va.status IN ('PLANNED','ACTIVE','SUSPENDED')) THEN
    RAISE EXCEPTION 'site change refused: open assignment exists' USING ERRCODE = 'MF004';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_vehicle_site_change_guard BEFORE UPDATE OF site_id ON vehicle FOR EACH ROW EXECUTE FUNCTION app.tg_site_change_guard();
CREATE TRIGGER tg_driver_site_change_guard  BEFORE UPDATE OF site_id ON driver  FOR EACH ROW EXECUTE FUNCTION app.tg_site_change_guard();
-- Éligibilité (permis, habilitation, statuts), antidatage (valid_from >= now - tolérance configurable, horloge
-- injectable) et refus de changement de statut véhicule/conducteur tant qu'une affectation PLANNED/ACTIVE existe
-- (D-11, 409) : applicatifs (RM-030, RM-041, RM-017, RM-020). La base garde l'isolation, le non-chevauchement,
-- l'immuabilité et la cohérence de site. Aucune dérogation au lot 1 (D-13).
-- Les gardes de site retiennent aussi SUSPENDED (créneau encore occupé) : plus strict que D-11 (écart à confirmer).
```

### 5.8 Esquisse hors lot 1 : `vehicle_meter_reading` (D-16, DB-15)

**Non livrée au lot 1** : la table (et sa migration, numérotée à ce moment-là) arrive avec la **première story qui saisit un compteur**. Aucune colonne de compteur sur `vehicle`. Le DDL ci-dessous est une esquisse non exécutée. Son `client_event_id` ne constitue pas l'idempotence générale du lot 4 (D-14).

```sql
CREATE TABLE vehicle_meter_reading (
  vehicle_meter_reading_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  meter_type text NOT NULL,
  value      numeric(10,1) NOT NULL,
  recorded_at timestamptz NOT NULL,                   -- instant de lecture (ordre métier)
  received_at timestamptz NOT NULL DEFAULT now(),
  source     text NOT NULL,
  kind       text NOT NULL DEFAULT 'READING',
  status     text NOT NULL DEFAULT 'ACCEPTED',
  client_event_id uuid,
  recorded_by uuid,
  correction_of uuid,
  reason text,
  CONSTRAINT fk_vmr__vehicle FOREIGN KEY (tenant_id, vehicle_id) REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_vmr__recorded_by FOREIGN KEY (recorded_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_vmr_tenant_vehicle_id UNIQUE (tenant_id, vehicle_id, vehicle_meter_reading_id),
  CONSTRAINT fk_vmr__correction FOREIGN KEY (tenant_id, vehicle_id, correction_of)
    REFERENCES vehicle_meter_reading (tenant_id, vehicle_id, vehicle_meter_reading_id) ON DELETE RESTRICT,   -- même véhicule (DB-18)
  CONSTRAINT uq_vmr_client_event UNIQUE (tenant_id, vehicle_id, client_event_id),
  CONSTRAINT ck_vmr_type   CHECK (meter_type IN ('ODOMETER_KM','HOUR_METER_H')),
  CONSTRAINT ck_vmr_value  CHECK (value >= 0),
  CONSTRAINT ck_vmr_source CHECK (source IN ('MANUAL','MOBILE_CHECKLIST','CAN_ECU','GPS_DERIVED','IMPORT')),
  CONSTRAINT ck_vmr_kind   CHECK (kind IN ('READING','CORRECTION','METER_REPLACEMENT')),
  CONSTRAINT ck_vmr_status CHECK (status IN ('ACCEPTED','QUARANTINED','REJECTED')),
  CONSTRAINT ck_vmr_correction CHECK ((kind = 'CORRECTION') = (correction_of IS NOT NULL)),
  CONSTRAINT ck_vmr_reason CHECK (kind = 'READING' OR reason IS NOT NULL)
);
CREATE INDEX ix_vmr_current ON vehicle_meter_reading (tenant_id, vehicle_id, meter_type, recorded_at DESC) WHERE status = 'ACCEPTED';
SELECT app.apply_tenant_rls('vehicle_meter_reading', 'SELECT, INSERT');
CREATE TRIGGER tg_vmr_append_only BEFORE UPDATE OR DELETE ON vehicle_meter_reading FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

-- Valeur courante : dernier relevé accepté ; la gestion fine des corrections est à préciser avec la story.
CREATE VIEW vehicle_current_meter WITH (security_invoker = true) AS
SELECT DISTINCT ON (tenant_id, vehicle_id, meter_type) tenant_id, vehicle_id, meter_type, value, recorded_at, source
FROM vehicle_meter_reading WHERE status = 'ACCEPTED'
ORDER BY tenant_id, vehicle_id, meter_type, recorded_at DESC;
GRANT SELECT ON vehicle_current_meter TO mf_app;
```

## 6. RLS, droits et flux d'identité

### 6.1 Matrice par table

| Table | Politique RLS pour `mf_app` | Droits `mf_app` | Garde supplémentaire |
|-------|-----------------------------|-----------------|----------------------|
| `role`, `role_allowed_scope`, `license_category_ref` | aucune (catalogue système global, D-18) | `SELECT` | modification par migration seulement |
| `tenant` | lecture : ligne propre, ou contexte plateforme, ou code exact fourni (`app.login_tenant_code`) ; insertion : contexte plateforme ; mise à jour : ligne propre ou plateforme | `SELECT, INSERT, UPDATE` | `tg_tenant_guard` : champs de gouvernance et `kind` |
| `site`, `user_account`, `user_role_assignment`, `vehicle_category`, `vehicle`, `driver`, `driver_license`, `driver_qualification`, `vehicle_assignment` | `tenant_id = app.current_tenant_id()` (`USING` et `WITH CHECK`) | `SELECT, INSERT, UPDATE` | `tg_forbid_tenant_change`, `tg_touch` ; gardes d'affectation |
| `vehicle_category_license_category` | idem | `SELECT, INSERT, DELETE` | |
| `account_token`, `auth_session` | idem | `SELECT, INSERT, UPDATE, DELETE` | purge des expirés |
| `vehicle_status_history` | idem | `SELECT, INSERT` | `tg_append_only` |
| `audit_event` (+ partitions) | lecture et insertion : tenant courant ; aucune politique `UPDATE/DELETE` | `SELECT, INSERT` + séquence | `tg_audit_event_append_only`, `no_truncate` ; aucun droit sur les partitions |

Aucun `DELETE` sur les tables métier modifiables. `mf_owner` n'est visé par aucune politique (fail-closed) ; il détient les droits DDL, la création de partitions et le détachement.

### 6.2 Flux d'identité sous RLS (DB-05)

1. **Connexion** (D-06) : code d'espace + e-mail + mot de passe. Transaction 1 `set_config('app.login_tenant_code', :code, true)` → lecture de `tenant` par **code exact** uniquement, sans listage et **sans `BYPASSRLS`** (réponse générique si absent ou suspendu) ; transaction 2 (ou suite) `set_config('app.tenant_id', :tenant_id, true)` → recherche du compte `(tenant_id, email)` (`citext`), vérification du mot de passe, création de `auth_session`, audit. Identifiant inconnu et mot de passe faux donnent la même réponse. Un code d'espace inconnu n'écrit pas d'`audit_event` (pas de tenant) : log structuré de sécurité.
2. **Refresh / activation / réinitialisation** : le cookie ou le lien porte `<tenant_id>.<id>.<secret>` ; le préfixe sert seulement à fixer le contexte ; la ligne est retrouvée par `(tenant_id, hash)` sous RLS ; un préfixe erroné donne 0 ligne, donc 401.
3. **Connexion `PLATFORM_ADMIN`** : point d'entrée distinct, code de tenant fixé côté serveur (`mf-platform`).
4. **Provisioning d'un tenant** : une fonction applicative unique, auditée, s'exécute en contexte plateforme, insère `tenant`, puis `set_config('app.tenant_id', <nouveau>, true)` pour insérer les sites, catégories, premier compte et son rôle (`granted_by` = compte plateforme), le tout dans une transaction. Test d'architecture : aucun autre appelant de `set_config('app.tenant_id'…)` hors du gestionnaire de contexte et de cette fonction.
5. **Métriques agrégées plateforme** (RBAC §2.1) : hors lot 1 ; si nécessaire, fonction `SECURITY DEFINER` minimale à compteurs, sous un rôle dédié, revue spécifique.
6. Pool : `SET LOCAL` (via `set_config(..., true)`) par transaction ; `pool_reset_on_return` actif. Une transaction qui oublie le contexte voit 0 ligne (DB-03).

## 7. Erreurs de base → API

| SQLSTATE / nom | Cause | Réponse API proposée |
|----------------|-------|----------------------|
| `23P01` `ex_va_vehicle_no_overlap` | chevauchement véhicule | 409 `VEHICLE_ASSIGNMENT_OVERLAP` |
| `23P01` `ex_va_driver_no_overlap` | chevauchement conducteur | 409 `DRIVER_ASSIGNMENT_OVERLAP` |
| `23P01` `ex_dq_no_overlap` / `ex_ura_no_duplicate` | doublon d'habilitation / de rôle | 409 |
| `23505` (`uq_*`) | unicité | 409 avec champ en cause (sans révéler d'autre tenant) |
| `23503` (`fk_*`) | référence absente ou d'un autre tenant | 422 `REFERENCE_NOT_FOUND` (message identique dans les deux cas, D-05a) |
| `23514` (`ck_*`) | règle de domaine | 422 |
| `MF001`, `MF003`, `MF004`, `MF002` | ajout seul, figé, site, tenant immuable | 409/500 + événement de sécurité si inattendu |
| `42501` (violation RLS / privilège) | bug de contexte ou tentative | 500 + alerte (ne doit jamais arriver en nominal) |

## 8. Stratégie Alembic

- **Ordre** : bootstrap (hors Alembic) → `0001_foundation` → `0002_organization` → `0003_identity` → `0004_audit` → `0005_fleet` → `0006_workforce` → `0007_assignment`. **Découpage par tranche (D-21)** : 1a = 0001 à 0004 (socle : tenant, site, identité, audit, RLS), 1b = 0005 et 0006 (flotte, personnel), 1c = 0007 (affectations) ; chaque tranche est livrée, testée et revue avant la suivante. Aucune migration pour `idempotency_record` (lot 4) ni pour `vehicle_meter_reading` (première story de compteur). Un fichier par module ; l'ordre respecte les FK (audit après identité, affectation après véhicule et conducteur).
- **Exécution** : sous `mf_owner` ; `SET lock_timeout`, `SET statement_timeout` (valeurs à calibrer). La migration 0001 vérifie `postgis`, `btree_gist`, `citext` et échoue sinon.
- **SQL brut** : fonctions, triggers, RLS, exclusions, partitions via `op.execute` ; tables et colonnes via `op.create_table`. Les modèles SQLAlchemy déclarent aussi les contraintes (dont `ExcludeConstraint`, colonnes `Computed`, `postgresql_partition_by`). `env.py` : `naming_convention`, `compare_type=True`, `include_object` ignorant partitions `audit_event_y*`, `audit_event_default` et tables PostGIS.
- **Réversibilité** : chaque migration a un `downgrade` qui supprime ce qu'elle a créé, dans l'ordre inverse ; jamais de `DROP EXTENSION` ; les données de référentiel sont supprimées seulement si non référencées. Les `downgrade` de 0004 et au-delà détruisent des données : refusés par `env.py` hors `MF_ENV ∈ {local, test, ci}` (CLAUDE.md : aucune opération destructive sans approbation).
- **Évolutions futures** (après première mise en service) : expansion/contraction ; `CREATE INDEX CONCURRENTLY` en bloc autocommit ; `NOT NULL` via `CHECK ... NOT VALID` puis `VALIDATE` ; ajout d'exclusion sur table peuplée planifié (verrou).
- **Amorçage de lignes dans une table à RLS forcée** : insérer avant `FORCE`, ou `NO FORCE`/`FORCE` dans la même transaction DDL (§5.1).
- **Vérifications CI** : `upgrade head` sur base amorcée ; `downgrade base` puis `upgrade head` ; `alembic check` (limites : DB-36) ; tests d'introspection DBT-40 à DBT-47 ; contrôle de longueur et de présence de nom pour toute contrainte.
- **Partitions d'audit** : `ensure_audit_partitions` appelée par la migration et par une commande d'exploitation (le lot 1 n'a pas d'ordonnanceur) ; alerte si `audit_event_default` n'est pas vide.

## 9. Données de démonstration fictives (H9, US-1.30)

- **Outil** : commande CLI `seed`, hors Alembic, qui passe par les **services applicatifs** (audit, invariants, règles d'éligibilité réellement exercés). Elle refuse de s'exécuter si `MF_ENV` ∈ {production, staging…} ou si la base contient un tenant client avec `is_demo = false`. Marquage `tenant.is_demo = true` (bandeau « données fictives »).
- **Idempotence** : identifiants dérivés (UUID v5 sur un espace de noms fixe + nom logique) ; un second passage ne duplique rien ou est refusé explicitement (US-1.30 A4).
- **Contenu** : deux tenants fictifs (`demo-minier`, `demo-transport`), chacun avec deux sites (`SITE-A1`, `SITE-A2`…), un compte par rôle utile (dont des portées `SITE`), 15 catégories, une dizaine de véhicules, une dizaine de conducteurs, permis et habilitations aux échéances variées (valide, proche, expirée), affectations passées, actives, planifiées, une annulée. Un compte `PLATFORM_ADMIN` dans le tenant plateforme.
- **Valeurs sentinelles** reconnaissables pour les tests de fuite (ST-40/48/74) : téléphones `+224000000xxx`, noms `Nom-Test-NN`, permis `PERMIS-FICTIF-NNNN`, e-mails `...@exemple.invalid`, IP `192.0.2.0/24`. Aucun nom, numéro, plaque ou position réels.
- **Secrets** : aucun mot de passe en dur ; mot de passe initial fourni par variable d'environnement obligatoire ou généré à l'exécution et affiché une fois ; haché en argon2id.
- **Fixtures de test** : mêmes services ou insertion par `mf_app` avec contexte posé (pas de contournement de la RLS).

## 10. Rétention (paramètres, aucune durée supposée) — C-09, juriste guinéen

| Donnée | Mécanisme |
|--------|-----------|
| `audit_event` | détachement de partitions mensuelles par `mf_owner`, procédure approuvée ; l'adresse IP est une donnée personnelle (si une durée plus courte est exigée : table séparée `audit_event_origin`, à décider) |
| `auth_session`, `account_token` | purge des expirés/révoqués après délai paramétrable (`DELETE` autorisé) |
| `idempotency_record` (lot 4) | purge à `expires_at` quand la table existera |
| `driver` / `user_account` sortis | anonymisation (`anonymized_at`, valeurs remplacées, téléphone/e-mail effacés) après la durée légale ; l'audit ne contient que des identifiants |
| `vehicle_status_history` (et `vehicle_meter_reading` plus tard) | conservation longue (données techniques), sans donnée personnelle sauf identifiant d'auteur |
| Sauvegardes | hors périmètre du modèle (ST-86) |

## 11. Hors lot 1 — esquisses non migrées

```sql
-- vehicle_document (DB-28) : à créer quand le client aura défini les documents bloquants (RM-019).
-- (tenant_id, vehicle_document_id, vehicle_id, document_type, reference, valid_from date, valid_to date,
--  status IN ('VALID','SUSPENDED','REVOKED')) + FK composite vers vehicle ; index (tenant_id, valid_to).

-- support_access_session (DB-21) : si l'accès support est décidé. tenant_id = tenant CIBLE (visible du tenant) ;
-- platform_user_id (FK simple), reason, ticket_ref, scope, approved_by (FK simple), starts_at, expires_at,
-- read_only boolean DEFAULT true, closed_at ; CHECK expires_at > starts_at ; politique : tenant courant ou contexte
-- plateforme. Le contexte support fixe app.tenant_id = tenant cible, sans BYPASSRLS.

-- idempotency_record (D-14, DB-06) : lot 4 (offline), avec l'en-tête Idempotency-Key et les critères associés.
--  (tenant_id, user_account_id, idempotency_key text, request_method, request_path, request_hash bytea,
--   state IN ('IN_PROGRESS','COMPLETED'), response_status, resource_type, resource_id, created_at, expires_at)
--  PK (tenant_id, user_account_id, idempotency_key) ; FK composite vers user_account ; même clé + corps différent => 422 ;
--  pas de corps de réponse stocké (données personnelles, DB-42) ; purge à expires_at (DELETE autorisé) ; RLS forcée.

-- audit_seal (DB-20, D-16, D-17) : (tenant_id, from_seq, to_seq, seal_hash, prev_seal_hash, sealed_at) ; tâche asynchrone
-- ordonnant par audit_seq avec filet de sécurité sur les transactions encore ouvertes ; ancrage externe périodique.

-- vehicle_site_history (DB-17) : si des rapports "parc par site à la date T" sont requis.
-- person (DB-14) : au lot 3 si nécessaire ; driver.person_id nullable puis NOT NULL par migration réversible.
```

## 12. Tests de base de données à écrire (pytest, PostgreSQL réel en conteneur, rôles `mf_app` / `mf_owner`) — aucun n'existe ni n'a été exécuté

**Isolation (RLS)**
- DBT-01 : sans contexte, `SELECT` sur chaque table tenant-scopée → 0 ligne, sans erreur.
- DBT-02 : transaction avec contexte A, `COMMIT`, nouvelle transaction sur la **même connexion** sans contexte → 0 ligne, sans erreur (DB-03).
- DBT-03 : contexte A ne voit rien de B ; `UPDATE`/`DELETE` visant B → 0 ligne affectée.
- DBT-04 : `INSERT` avec `tenant_id` ≠ contexte → violation de politique (`WITH CHECK`).
- DBT-05 : alternance A/B sur une connexion de pool ; requêtes concurrentes de deux tenants.
- DBT-06 : `UPDATE ... SET tenant_id` refusé (`MF002`).
- DBT-07 : lecture de `tenant` par code exact seulement avec `app.login_tenant_code` ; aucun listage ; insertion de tenant refusée hors contexte plateforme ; changement de `status`/`code` refusé hors contexte plateforme.
- DBT-08 : `mf_app` : `rolsuper = false`, `rolbypassrls = false`, propriétaire d'aucune table, aucun `DELETE` sur les tables métier modifiables.

**FK et références**
- DBT-10 : pour chaque FK composite, insertion référençant une ligne d'un autre tenant → `23503` (API : 422 `REFERENCE_NOT_FOUND`).
- DBT-11 : `user_role_assignment` : rôle `TENANT_ADMIN` + portée `PLATFORM` refusé (FK `role_scope`) ; portée `PLATFORM` dans un tenant client refusée (`tenant_kind`) ; portée `SITE` sans `site_id` refusée ; `site_id` d'un autre tenant refusé.
- DBT-12 : `driver.user_account_id` en doublon refusé ; compte d'un autre tenant refusé.
- DBT-13 : (hors lot 1, avec `vehicle_meter_reading`) `correction_of` d'un autre véhicule refusé.
- DBT-14 : `vehicle_category_license_category` : code de permis inconnu refusé.

**Chevauchements et unicités**
- DBT-20 : deux affectations chevauchantes sur le même véhicule → `23P01 ex_va_vehicle_no_overlap` ; idem conducteur.
- DBT-21 : affectations contiguës `[t1,t2)` puis `[t2,t3)` acceptées.
- DBT-22 : affectation `CANCELLED` libère le créneau ; `COMPLETED` le conserve ; `COMPLETED` sans `valid_to` refusée ; `valid_to = valid_from` refusé (intervalle vide).
- DBT-23 : insertions concurrentes (deux connexions) → une seule réussit.
- DBT-24 : habilitations `VALID` chevauchantes refusées **y compris avec `site_id` NULL** ; renouvellement après troncature accepté.
- DBT-27 : changement de `vehicle.site_id` ou `driver.site_id` refusé (`MF004`) tant qu'une affectation `PLANNED`/`ACTIVE`/`SUSPENDED` existe ; création d'une affectation dont le site diffère de celui du véhicule **ou** du conducteur refusée (`MF004`).
- DBT-25 : unicités : numéro de parc (casse/espaces), immatriculation (tirets/espaces), e-mail par tenant (casse), même e-mail dans deux tenants accepté, matricule, code de site ; permis renouvelé avec même numéro et autre `issue_date` accepté.
- DBT-26 : doublon d'attribution de rôle sur périodes chevauchantes refusé ; attribution expirée n'empêche pas la nouvelle.

**Audit et ajout seul**
- DBT-30 : `UPDATE`, `DELETE`, `TRUNCATE` sur `audit_event` par `mf_app` refusés (privilège) ; par super-utilisateur : `UPDATE/DELETE` bloqués par le trigger (`MF001`).
- DBT-31 : `mf_app` ne peut ni lire ni écrire directement une partition ni `audit_event_default` ; `audit_event_default` vide après une journée de tests.
- DBT-32 : `ensure_audit_partitions` idempotente ; insertion à une date sans partition tombe dans `default` (détectée) ; partitions créées avec RLS forcée et droits révoqués.
- DBT-33 : `vehicle_status_history` : `UPDATE/DELETE` refusés ; `vehicle_status_history` alimentée par création, changement de statut et `UPDATE` en masse.
- DBT-34 : contraintes `ck_audit_*` (actor_kind/référence, support, action, outcome).
- DBT-35 : lecture d'audit d'un autre tenant impossible ; insertion avec un autre `tenant_id` refusée.

**Intégrité et concurrence**
- DBT-36 : `row_version` incrémenté par trigger, y compris sur `UPDATE` en masse ; `UPDATE ... WHERE row_version = :v` périmé → 0 ligne.
- DBT-37 : affectation `COMPLETED`/`CANCELLED` immuable (`MF003`) ; `vehicle_id/driver_id/site_id` immuables ; création avec `site_id` ≠ site du véhicule refusée (`MF004`).
- DBT-38 : CHECK de domaine : statuts, motifs requis (véhicule, conducteur), `RETIRED` ⇔ `decommissioned_on`, `rated_payload_kg > 0`, téléphone E.164, `expiry_date > issue_date`.
- DBT-39 : unicité d'un seul tenant `PLATFORM` ; `tenant.kind` immuable.

**Introspection et migrations**
- DBT-40 : toute table de `public` est soit dans la liste globale (`role`, `role_allowed_scope`, `license_category_ref`, `alembic_version`, PostGIS), soit possède `tenant_id uuid NOT NULL`, RLS activée **et forcée**, au moins une politique.
- DBT-41 : toute FK entre tables tenant-scopées inclut `tenant_id`, hors liste d'exceptions explicite (`granted_by`, `revoked_by`, `verified_by`, `actor_user_id` ; `recorded_by` et `approved_by` hors lot 1).
- DBT-42 : chaque contrainte, index, trigger a un nom conforme à la convention et ≤ 63 octets ; aucune contrainte sans nom.
- DBT-43 : aucune clé primaire autre que `uuid` (sauf référentiels textuels) ; toute table modifiable a `row_version` et `tg_touch`.
- DBT-44 : chaque partition d'audit a RLS forcée et aucun droit pour `mf_app`.
- DBT-45 : `upgrade head` → `downgrade base` → `upgrade head` ; aucun `DROP EXTENSION` dans les migrations ; `downgrade` destructif refusé hors `local/test/ci`.
- DBT-46 : extensions requises présentes ; `pgcrypto` absente.
- DBT-47 : `alembic check` sans dérive (partitions et tables PostGIS ignorées).
- DBT-48 : démarrage : contrôle des attributs du rôle `mf_app`.

**Seed et rétention**
- DBT-50 : le seed refuse `MF_ENV=production` ; deuxième exécution idempotente ou refusée ; aucune valeur hors liste sentinelle/fictive ; tenants `is_demo = true`.
- DBT-51 : purge des `auth_session`, `account_token` expirés ; aucun effet sur les non expirés.
- DBT-52 : anonymisation d'un conducteur : champs d'identité remplacés, audit inchangé et lisible.
- DBT-54 : aucune table `idempotency_record` ni `vehicle_meter_reading` après `upgrade head` du lot 1 ; la création en double d'un véhicule (même numéro de parc) ou d'une affectation chevauchante est refusée par contrainte (`23505` / `23P01`).
- DBT-55 : aucune table `permission` / `role_permission` en base (D-18a) ; la concordance route ↔ permission est testée sur `authz_matrix.yaml`.
- DBT-53 : jeton d'invitation : un seul jeton ouvert par compte et finalité ; hachage de 32 octets.

**Performance (observation, non un critère)** : `EXPLAIN` des requêtes de liste et d'historique pour vérifier l'usage des index commençant par `tenant_id` et l'absence d'appel répété de `app.current_tenant_id()` par ligne. Aucun seuil n'est fixé (volumétrie inconnue).

## 13. Limites et points à confirmer par exécution

- Aucun DDL n'a été exécuté. À confirmer en CI sur PostgreSQL 16 : expressions de colonnes générées (`lower`, `upper`, `regexp_replace`, `tstzrange`) acceptées comme immuables ; `uuid` dans une exclusion `btree_gist` ; triggers de ligne `BEFORE` et de `TRUNCATE` sur table partitionnée ; `ON CONFLICT`/clés primaires incluant la colonne de partition ; comportement d'un paramètre personnalisé après la fin de la transaction ; `security_invoker` sur la vue ; `CREATE POLICY ... TO mf_app` combiné à `FORCE` pour `mf_owner`.
- SQLAlchemy / Alembic : la prise en charge de `ExcludeConstraint`, `Computed`, des tables partitionnées et de `version_id_generator=False` avec `eager_defaults` doit être vérifiée au premier vertical slice.
- Les défauts provisoires C-01..C-17 de `DECISIONS_A_ARBITRER.md` ne sont pas tranchés par le client ; ce modèle applique leur valeur par défaut.
- Valeurs de timeouts, durées de session, de jeton, de rétention et seuils d'alerte : non fixées, par choix.
