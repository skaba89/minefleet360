# Dictionnaire de données — Lot 1

> Statut : **provisoire** (phase 0), mis à jour après la revue croisée. Préséance en cas de divergence : `DECISIONS_A_ARBITRER.md` (D-01..D-24) > `MODELE_PHYSIQUE_LOT1.md` > `MATRICE_RBAC.md` > `REGLES_METIER.md` > ce dictionnaire. Schéma : `docs/MODELE_CONCEPTUEL.md`. Règles : `docs/REGLES_METIER.md`.
> **Tous les exemples sont fictifs** (domaine `.invalid`, numéros inexistants). Aucune donnée réelle de salarié. Les types sont des types PostgreSQL 16 ; ce document ne remplace pas la migration Alembic, il en est la spécification. Rien n'a été exécuté.
> Tranches de livraison (D-21) : **1a** socle (tenant, site, identité, audit), **1b** flotte et personnel, **1c** affectations. Chaque table indique sa tranche.

## 0. Légendes, conventions, glossaire

**Sensibilité**

| Niveau | Définition | Exemples |
|--------|-----------|----------|
| `public` | Divulgable hors tenant sans dommage | Libellés de référentiel de rôles |
| `interne` | Donnée d'entreprise, visible aux seuls utilisateurs du tenant selon rôle | Numéro de parc, catégorie |
| `personnel` | Se rapporte à une personne identifiable (**à valider** au regard du droit guinéen, C-08) | Nom, téléphone, e-mail, numéro de permis, adresse IP |
| `sensible` | Risque élevé en cas de fuite ou d'usage abusif : secrets, discipline | Hash de mot de passe, secret MFA, motif de suspension |

**Sources de fiabilité** : **[V]** fait vérifié (CLAUDE.md / socle), **[H]** hypothèse, **[A]** à valider (client, fournisseur, juriste guinéen).

**Colonnes communes** des tables **modifiables** (non répétées ci-dessous) : `created_at`, `updated_at` (`timestamptz NOT NULL DEFAULT now()`, UTC), `created_by`, `updated_by` (`uuid`, **sans FK**, NULL = système ; la traçabilité est portée par l'audit), `row_version` (`integer NOT NULL DEFAULT 1`, **incrémenté par trigger** `BEFORE UPDATE` ; ETag faible `W/"<row_version>"`, en-tête `If-Match`, `409` si obsolète — D-19). Il n'y a **pas** de colonne `archived_at` : l'état terminal est le statut (`RETIRED`, `INACTIVE`, `DISABLED`, `ARCHIVED`, `CANCELLED`) ou `is_active` pour les référentiels sans machine d'états (DB-23). Les tables d'ajout seul (`audit_event`, `vehicle_status_history`) et éphémères (`account_token`, `auth_session`) n'ont ni `updated_at` ni `row_version`.

**Conventions**
- Clés primaires `uuid` **v4**, `DEFAULT gen_random_uuid()` (natif PostgreSQL 16) ; aucune dépendance UUID v7 (D-20). Nommage `<table>_id`.
- `tenant_id uuid NOT NULL` sur toute table tenant-scopée, **sans exception** : les comptes et événements de plateforme appartiennent au tenant plateforme réservé (`tenant.kind = 'PLATFORM'`, D-07). Seuls `role`, `role_allowed_scope`, `license_category_ref` sont globaux (catalogue système en lecture seule, D-18).
- FK composites `(tenant_id, <id>)` entre tables métier (chaque table déclare `UNIQUE (tenant_id, <pk>)`). **Exceptions explicites** (FK simples vers `user_account(user_account_id)`) : `granted_by`, `revoked_by`, `verified_by`, `actor_user_id`. `created_by`/`updated_by` n'ont pas de FK. Toutes les FK sont `ON DELETE RESTRICT`.
- Énumérations en `text` + `CHECK` (pas d'`ENUM` PostgreSQL), **valeurs en anglais `UPPER_SNAKE_CASE`** (D-01). Libellés français uniquement dans l'interface (fichier i18n) ; aucun libellé n'est stocké dans une colonne de statut.
- Pas de suppression physique des tables métier pour `mf_app` ; unicités **totales** (non partielles) : un numéro de parc n'est jamais réutilisé (C-13).
- Valeurs dynamiques (`now()`, `CURRENT_DATE`) interdites dans les `CHECK` (DB-31) : contrôles datés = applicatifs.

### Glossaire unique : code d'énumération → libellé français (D-01 à D-04)

| Colonne | Code | Libellé FR |
|---------|------|-----------|
| `tenant.status` | `ACTIVE` / `SUSPENDED` / `ARCHIVED` | Actif / Suspendu / Archivé |
| `tenant.kind` | `CUSTOMER` / `PLATFORM` | Client / Plateforme |
| `site.status` | `ACTIVE` / `INACTIVE` | Actif / Inactif |
| `site.site_type` | `MINE`, `QUARRY`, `WORKSHOP`, `DEPOT`, `PORT`, `OFFICE` | Mine, Carrière, Atelier, Dépôt, Port, Bureau |
| `user_account.status` | `INVITED` / `ACTIVE` / `DISABLED` | Invité / Actif / Désactivé (« verrouillé » = dérivé de `locked_until`, jamais stocké) |
| `role_allowed_scope.scope_type`, `user_role_assignment.scope_type` | `PLATFORM`, `TENANT`, `SITE` | Plateforme, Tenant, Site |
| `account_token.purpose` | `INVITATION`, `PASSWORD_RESET` | Invitation, Réinitialisation de mot de passe |
| `vehicle.status` (D-02) | `AVAILABLE` | Disponible |
| | `IN_MAINTENANCE` | En maintenance |
| | `IMMOBILIZED` | Immobilisé |
| | `OUT_OF_SERVICE` | Hors service |
| | `RETIRED` (terminal) | Réformé |
| (dérivé, jamais stocké) | « libre » / « en exploitation » | Libre / En exploitation (déduit d'une affectation `ACTIVE`) |
| `vehicle.ownership_type` | `OWNED`, `LEASED`, `SUBCONTRACTED` | Propre, Location, Sous-traitant |
| `vehicle.fuel_type` | `DIESEL`, `PETROL`, `ELECTRIC`, `OTHER` | Gasoil, Essence, Électrique, Autre |
| `vehicle_category.family` | `HAULAGE`, `LOADING_EXCAVATION`, `EARTHWORKS`, `TANKER`, `PERSONNEL_TRANSPORT`, `LIGHT_VEHICLE`, `SUPPORT_EQUIPMENT` | Transport de matériaux, Chargement/excavation, Terrassement/entretien, Citerne, Transport de personnel, Véhicule léger, Matériel support |
| `driver.status` (D-03) | `ACTIVE` / `UNAVAILABLE` / `SUSPENDED` / `INACTIVE` | Actif / Indisponible / Suspendu / Inactif |
| `driver.employment_type` | `EMPLOYEE`, `TEMP_AGENCY`, `SUBCONTRACTOR` | Employé, Intérimaire, Sous-traitant |
| `driver.unavailability_reason` | `LEAVE`, `TRAINING`, `OTHER` | Congé, Formation, Autre (aucun motif de santé, D-15) |
| `driver_license.status` | `VALID` / `SUSPENDED` / `WITHDRAWN` | Valide / Suspendu / Retiré (statut **administratif** ; l'expiration est dérivée) |
| état dérivé du permis / de l'habilitation | `VALID` / `EXPIRING` / `EXPIRED` | Valide / Bientôt expiré / Expiré (calculé à la lecture, jamais stocké, D-03, D-12) |
| `driver_qualification.qualification_type` | `DRIVING_AUTHORIZATION`, `SAFETY_TRAINING`, `OTHER` | Habilitation de conduite, Formation sécurité, Autre |
| `driver_qualification.status` | `VALID` / `SUSPENDED` / `REVOKED` | Valide / Suspendue / Révoquée |
| `vehicle_assignment.status` (D-04) | `PLANNED` / `ACTIVE` / `SUSPENDED` / `COMPLETED` / `CANCELLED` | Planifiée / Active / Suspendue / Terminée / Annulée |
| `audit_event.actor_kind` | `USER`, `SYSTEM`, `PLATFORM_SUPPORT`, `DEVICE_SYNC`, `ANONYMOUS` | Utilisateur, Système, Support plateforme, Synchro appareil, Anonyme |
| `audit_event.outcome` | `SUCCESS` / `DENIED` / `FAILURE` | Succès / Refusé / Échec |

Un code publié ne se renomme que par migration. Les codes d'erreur API (`DRIVER_LICENSE_EXPIRED`, etc.) et la table des codes HTTP sont fixés par D-05.

---

## 1. `tenant` (tranche 1a)

Organisation cliente, ou tenant plateforme réservé (un seul, `kind = 'PLATFORM'`, code `mf-platform`, créé par la migration 0001). `tenant_id` est la clé de la ligne. Création réservée au contexte plateforme (`PLATFORM_ADMIN`), champs d'affichage modifiables par `TENANT_ADMIN`, champs de gouvernance (`code`, `kind`, `status`, `is_demo`, `legal_name`) modifiables en contexte plateforme seulement (trigger de garde).

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `tenant_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, kind)` (cible de FK) | Identifiant | | interne |
| `code` | `text` | NON | UNIQUE global, `^[a-z0-9-]{3,32}$` | **Code d'espace de travail** servant à la connexion (D-06), porté par l'URL ou saisi | `demo-minier` | interne |
| `kind` | `text` | NON | CHECK `CUSTOMER`, `PLATFORM` ; immuable ; un seul `PLATFORM` (index unique partiel) | Type de tenant | `CUSTOMER` | interne |
| `legal_name` | `text` | NON | longueur 1-200 | Raison sociale | `Société Minière Démo SA` | interne |
| `legal_name_norm` | `text` | NON | colonne générée (minuscules, espaces réduits) ; **UNIQUE** | Unicité du nom insensible à la casse et aux espaces (US-1.01) | | interne |
| `display_name` | `text` | NON | | Nom affiché | `Minière Démo` | interne |
| `status` | `text` | NON | CHECK `ACTIVE`, `SUSPENDED`, `ARCHIVED` | Un tenant `SUSPENDED` refuse toute connexion utilisateur | `ACTIVE` | interne |
| `is_demo` | `boolean` | NON | défaut `false` | Tenant fictif (bandeau « données fictives ») ; chargement interdit en production | `true` | interne |
| `default_timezone` | `text` | NON | syntaxe IANA ; validité vérifiée par l'application ; défaut `Africa/Conakry` | Fuseau d'affichage par défaut **[V]** (H4) | `Africa/Conakry` | interne |
| `default_locale` | `text` | NON | défaut `fr-GN` **[H]** | Langue d'interface | `fr-GN` | interne |
| `country_code` | `char(2)` | NON | défaut `GN` | Pays d'exploitation | `GN` | interne |
| `currency_code` | `char(3)` | NON | défaut `GNF` | Monnaie, montants en `bigint` **[V]** (H5) | `GNF` | interne |

RLS : lecture de la ligne propre, ou contexte plateforme, ou code exact fourni via `app.login_tenant_code` (pas de listage) — D-06, voir `MODELE_PHYSIQUE_LOT1.md` §6. Le tenant plateforme est exclu des listes de tenants clients (filtre `kind`). Pas de plan commercial au lot 1.

## 2. `site` (tranche 1a)

Lieu d'exploitation d'un tenant.

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `site_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, site_id)` | Identifiant | | interne |
| `tenant_id` | `uuid` | NON | FK `tenant` | Propriétaire | | interne |
| `code` | `text` | NON | `UNIQUE (tenant_id, code)` | Code court du site | `SITE-A` | interne |
| `name` | `text` | NON | | Nom | `Site de démonstration A` | interne |
| `site_type` | `text` | NON | CHECK `MINE`, `QUARRY`, `WORKSHOP`, `DEPOT`, `PORT`, `OFFICE` **[H]** | Nature du site | `MINE` | interne |
| `timezone` | `text` | OUI | syntaxe IANA ; NULL = fuseau du tenant | Fuseau d'affichage du site | `Africa/Conakry` | interne |
| `location` | `geography(Point,4326)` | OUI | ni (0,0) ; plages lon/lat validées par l'application avant conversion | Centre approximatif (PostGIS, sans index spatial au lot 1) | fictif | interne |
| `status` | `text` | NON | CHECK `ACTIVE`, `INACTIVE` | | `ACTIVE` | interne |

## 3. `user_account` (tranche 1a)

Compte de connexion, distinct de la personne (conducteur) **[V]** (H6). Appartient toujours à un tenant (le compte `PLATFORM_ADMIN` appartient au tenant plateforme).

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `user_account_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, user_account_id)` | Identifiant | | interne |
| `tenant_id` | `uuid` | NON | FK `tenant` | Tenant du compte | | interne |
| `email` | `citext` | NON | **`UNIQUE (tenant_id, email)`** (insensible à la casse) ; format validé | Identifiant de connexion avec le code d'espace (D-06) ; un même e-mail peut exister dans deux tenants | `exploitation01@exemple.invalid` | personnel |
| `display_name` | `text` | NON | | Nom affiché | `Utilisateur Test 01` | personnel |
| `phone` | `text` | OUI | E.164 | Téléphone ; visible `HR` seulement, masquage serveur sinon (D-15) | `+224000000001` | personnel |
| `password_hash` | `text` | OUI | argon2id **[H]** ; jamais journalisé ni exposé | NULL tant que le compte est `INVITED` | (hash) | sensible |
| `mfa_enabled` | `boolean` | NON | défaut `false` ; exige `mfa_secret_encrypted` | MFA activé ; **livrée après le lot 1** (C-03), colonne présente | `false` | interne |
| `mfa_secret_encrypted` | `bytea` | OUI | chiffré applicativement | Secret TOTP | (chiffré) | sensible |
| `status` | `text` | NON | CHECK `INVITED`, `ACTIVE`, `DISABLED` | Cycle de vie du compte | `ACTIVE` | interne |
| `failed_login_count` | `integer` | NON | ≥ 0 | Échecs consécutifs (anti force brute) | `0` | interne |
| `locked_until` | `timestamptz` | OUI | | Fin de verrouillage temporaire ; l'état « verrouillé » est **dérivé** (`locked_until > now()`), jamais un statut | | interne |
| `last_login_at` | `timestamptz` | OUI | | Dernière connexion réussie (IP et agent : sur `auth_session`) | | personnel |
| `must_change_password` | `boolean` | NON | défaut `true` | | | interne |
| `ui_locale` | `text` | NON | défaut `fr-GN` | | | interne |
| `anonymized_at` | `timestamptz` | OUI | | Anonymisation (droit d'effacement) : identité remplacée par un marqueur | | interne |

Notes : un compte `DISABLED` ne se supprime pas. Il n'existe pas de `token_version` : la révocation passe par `auth_session.revoked_at` (DB-33). Le champ `is_platform_account` est supprimé (DB-04). Connexion : code d'espace exact + e-mail + mot de passe ; identifiant inconnu et mot de passe faux donnent la même réponse (D-06).

## 4. Référentiels globaux : `role`, `role_allowed_scope` (tranche 1a)

Catalogue **système**, sans `tenant_id`, alimenté par migration, **lecture seule** pour `mf_app` (D-18). **Le catalogue des permissions n'est pas en base au lot 1** (D-18a) : il vit uniquement dans `authz_matrix.yaml` (D-09, créé au lot 1a), lisible par l'humain dans `MATRICE_RBAC.md` ; pas de tables `permission`/`role_permission`.

**`role`**

| Colonne | Type | Null | Contrainte | Description FR | Exemple | Sensibilité |
|---------|------|------|-----------|----------------|---------|-------------|
| `role_code` | `text` | NON | PK (pas de `CHECK` sur la liste : la FK suffit) | Code stable | `DISPATCHER` | public |
| `label_fr` | `text` | NON | | Libellé | `Dispatcher / régulateur` | public |
| `description_fr` | `text` | OUI | | Rôle | | public |
| `is_optional` | `boolean` | NON | défaut `false` | `true` pour `AUDITOR` : rôle **retenu** mais optionnel, lecture seule (D-10) | `true` | public |

Valeurs : `PLATFORM_ADMIN`, `TENANT_ADMIN`, `DIRECTION`, `AUDITOR`, `OPS_MANAGER`, `DISPATCHER`, `HR`, `WORKSHOP_CHIEF`, `MECHANIC`, `STOREKEEPER`, `FUEL_MANAGER`, `HSE`, `FINANCE`, `DRIVER`.

**`role_allowed_scope`** : `(role_code FK, scope_type ∈ PLATFORM|TENANT|SITE)`, PK composite. `PLATFORM_ADMIN` → `{PLATFORM}` ; `TENANT_ADMIN`, `DIRECTION`, `AUDITOR` → `{TENANT}` ; `DISPATCHER` → `{SITE}` seulement (D-10) ; `DRIVER` → `{SITE}` (aucun écran conducteur au lot 1, C-12) ; autres rôles → `{TENANT, SITE}`. Remplace le tableau `allowed_scopes` (non contraignable).

**Permissions** : voir `authz_matrix.yaml` (convention `<domaine>.<ressource>.<action>`, ex. `fleet.vehicle.read`) ; un test vérifie que toute route déclare une permission (D-09).

## 5. `user_role_assignment` (tranche 1a)

Attribution d'un rôle à un compte avec une portée **[V]** (H7).

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `user_role_assignment_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, user_role_assignment_id)` | | | interne |
| `tenant_id` | `uuid` | NON | | | | interne |
| `tenant_kind` | `text` | NON | FK `(tenant_id, tenant_kind)` → `tenant(tenant_id, kind)` | Dénormalisation contrôlée : porte la règle « portée `PLATFORM` ⇔ tenant plateforme » (DB-04) | `CUSTOMER` | interne |
| `user_account_id` | `uuid` | NON | FK composite `(tenant_id, user_account_id)` | Bénéficiaire | | interne |
| `role_code` | `text` | NON | FK composite `(role_code, scope_type)` → `role_allowed_scope` | | `DISPATCHER` | interne |
| `scope_type` | `text` | NON | `PLATFORM`, `TENANT`, `SITE` ; `(scope_type='SITE') = (site_id IS NOT NULL)` ; `(scope_type='PLATFORM') = (tenant_kind='PLATFORM')` | | `SITE` | interne |
| `site_id` | `uuid` | OUI | FK composite `(tenant_id, site_id)` | | | interne |
| `valid_from` | `timestamptz` | NON | défaut `now()` | | | interne |
| `valid_to` | `timestamptz` | OUI | `CHECK valid_to > valid_from` | Fin d'attribution (NULL = sans fin) | | interne |
| `granted_by` | `uuid` | NON | FK **simple** `user_account(user_account_id)` | Auteur (peut être un compte plateforme lors du provisioning) | | interne |
| `revoked_at`, `revoked_by` | `timestamptz`, `uuid` | OUI | FK simple ; renseignés ensemble | Révocation | | interne |

Unicité : contrainte d'exclusion `ex_ura_no_duplicate` (même compte, rôle, portée, `COALESCE(site_id, uuid nul)` sur périodes chevauchantes, hors révoquées). On ne peut ni s'attribuer soi-même un rôle supérieur, ni retirer le dernier `TENANT_ADMIN` actif (verrou applicatif + test) **[H]**. Chaque attribution/révocation crée un `audit_event`.

## 6. `account_token` (tranche 1a, éphémère)

Jeton à usage unique d'invitation ou de réinitialisation de mot de passe. Remplace l'entité `invitation` (DB-06).

| Colonne | Type | Null | Contrainte | Description FR | Sensibilité |
|---------|------|------|-----------|----------------|-------------|
| `account_token_id` | `uuid` | NON | PK | | interne |
| `tenant_id`, `user_account_id` | `uuid` | NON | FK composite vers `user_account` | | interne |
| `purpose` | `text` | NON | CHECK `INVITATION`, `PASSWORD_RESET` | Finalité | interne |
| `token_hash` | `bytea` | NON | `octet_length = 32` ; `UNIQUE (tenant_id, token_hash)` | SHA-256 d'un secret aléatoire de 256 bits ; **jamais le jeton lui-même** | sensible |
| `expires_at` | `timestamptz` | NON | `> created_at` ; durée = paramètre (non fixée) | | interne |
| `consumed_at`, `revoked_at` | `timestamptz` | OUI | | Usage unique / révocation | interne |
| `created_at`, `created_by` | | | | | interne |

Un seul jeton ouvert par `(compte, finalité)` (index unique partiel). Le lien transmis porte `<tenant_id>.<id>.<secret>` : le préfixe ne sert qu'à fixer le contexte, le secret haché reste l'autorité. Purge des expirés : `DELETE` autorisé (seule exception avec `auth_session`).

## 7. `auth_session` (tranche 1a, éphémère)

Une ligne par session ; porte la rotation du refresh et la révocation (ADR-003).

| Colonne | Type | Null | Contrainte | Description FR | Sensibilité |
|---------|------|------|-----------|----------------|-------------|
| `auth_session_id` | `uuid` | NON | PK ; = `session_id` du jeton d'accès | | interne |
| `tenant_id`, `user_account_id` | `uuid` | NON | FK composite | | interne |
| `refresh_hash_current` | `bytea` | NON | 32 octets ; `UNIQUE (tenant_id, refresh_hash_current)` | Empreinte du refresh courant | sensible |
| `refresh_hash_previous`, `rotated_at` | `bytea`, `timestamptz` | OUI | | Détection de réutilisation et fenêtre de grâce | sensible |
| `amr` | `text[]` | NON | défaut `{pwd}` | Méthodes d'authentification | interne |
| `ip_address`, `user_agent` | `inet`, `text` | OUI | | Origine (donnée personnelle ; rétention C-09) | personnel |
| `created_at`, `last_seen_at`, `expires_at` | `timestamptz` | NON | `expires_at > created_at` ; durée absolue = paramètre | | interne |
| `revoked_at`, `revoked_reason` | | OUI | | Révocation serveur (déconnexion, désactivation) | interne |

## 8. `vehicle_category` (tranche 1b ; référentiel **par tenant**) et jonction

Catégories d'engins **copiées par tenant** à la création du tenant depuis un jeu système versionné dans le code (D-18). Le tenant peut en ajouter ou désactiver ; le code d'une catégorie `is_system` est immuable.

| Colonne | Type | Null | Contrainte | Description FR | Exemple | Sensibilité |
|---------|------|------|-----------|----------------|---------|-------------|
| `vehicle_category_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, vehicle_category_id)` | | | interne |
| `tenant_id` | `uuid` | NON | FK | | | interne |
| `code` | `text` | NON | `UNIQUE (tenant_id, code)`, `^[A-Z0-9_]{3,40}$` | Code technique stable (anglais) | `RIGID_DUMP_TRUCK` | interne |
| `label_fr` | `text` | NON | | | `Camion-benne rigide (tombereau)` | interne |
| `family` | `text` | NON | CHECK (glossaire §0) | Famille d'usage | `HAULAGE` | interne |
| `requires_driver` | `boolean` | NON | | `false` pour matériel sans conducteur : exclu des affectations | `true` | interne |
| `requires_internal_authorization` | `boolean` | NON | | Habilitation interne d'engin exigée (RM-023) | `true` | interne |
| `has_odometer`, `has_hour_meter` | `boolean` | NON | | Compteurs pertinents (relevés : lot ultérieur) | `true` | interne |
| `is_system` | `boolean` | NON | défaut `false` | Copie du jeu initial ; code ni modifié ni supprimé | `true` | interne |
| `is_active` | `boolean` | NON | défaut `true` | | | interne |

**`vehicle_category_license_category`** (jonction, remplace le tableau `required_license_category_codes`) : `(tenant_id, vehicle_category_id, license_category_code)`, PK composite ; FK composite vers `vehicle_category`, FK vers `license_category_ref(code)`. Aucune ligne = pas de permis d'État exigé **[A]** (à ne pas supposer, RM-022). `DELETE` autorisé (configuration, tracée par l'audit).

### Jeu initial proposé (**[H]** pratique des sites miniers ; valeurs à valider avec le client, C-07)

| Code | Libellé FR | Famille | Conducteur | Habilitation interne | Compteurs |
|------|-----------|---------|-----------|----------------------|-----------|
| `ARTICULATED_DUMP_TRUCK` | Camion-benne articulé | `HAULAGE` | oui | oui | km + h |
| `RIGID_DUMP_TRUCK` | Camion-benne rigide (tombereau) | `HAULAGE` | oui | oui | km + h |
| `ROAD_DUMP_TRUCK` | Camion-benne routier (porteur ou semi) | `HAULAGE` | oui | oui | km + h |
| `HYDRAULIC_EXCAVATOR` | Pelle hydraulique | `LOADING_EXCAVATION` | oui | oui | h |
| `WHEEL_LOADER` | Chargeuse sur pneus | `LOADING_EXCAVATION` | oui | oui | h |
| `BULLDOZER` | Bulldozer | `EARTHWORKS` | oui | oui | h |
| `MOTOR_GRADER` | Niveleuse | `EARTHWORKS` | oui | oui | h |
| `COMPACTOR` | Compacteur | `EARTHWORKS` | oui | oui | h |
| `FUEL_TANKER` | Camion-citerne carburant | `TANKER` | oui | oui (+ matières dangereuses **[A]**) | km + h |
| `WATER_TANKER` | Camion-citerne d'arrosage de pistes | `TANKER` | oui | oui | km + h |
| `LOWBED_TRAILER` | Porte-engins (semi-remorque surbaissée) | `SUPPORT_EQUIPMENT` | oui | oui | km |
| `FORKLIFT_TELEHANDLER` | Chariot élévateur / télescopique | `SUPPORT_EQUIPMENT` | oui | oui | h |
| `LIGHT_VEHICLE` | Véhicule léger (pick-up, 4x4) | `LIGHT_VEHICLE` | oui | non **[A]** | km |
| `PERSONNEL_BUS` | Bus de transport de personnel | `PERSONNEL_TRANSPORT` | oui | oui | km |
| `GENERATOR_LIGHTING_TOWER` | Groupe électrogène / tour d'éclairage | `SUPPORT_EQUIPMENT` | non | non | h |

Proposition de départ, **pas un fait vérifié** du secteur guinéen ; les équivalences de permis par catégorie sont **[A]**.

## 9. `vehicle` (tranche 1b)

Véhicule ou engin. Un engin cédé à un autre tenant n'existe pas : on réforme puis on recrée (RM-050).

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `vehicle_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, vehicle_id)` | | | interne |
| `tenant_id` | `uuid` | NON | FK | | | interne |
| `site_id` | `uuid` | NON | FK composite `(tenant_id, site_id)` | Site courant (uniforme avec `driver.site_id`) | | interne |
| `vehicle_category_id` | `uuid` | NON | FK composite ; catégorie active à la création | | | interne |
| `fleet_number` | `text` | NON | `^[^\s]{1,30}$` | Numéro de parc (identifiant métier interne) | `DT-001` | interne |
| `fleet_number_norm` | `text` | NON | colonne générée `lower(btrim(...))` ; **`UNIQUE (tenant_id, fleet_number_norm)` totale** | Jamais réutilisé, même `RETIRED` (RM-010, C-13) | | interne |
| `registration_number` | `text` | OUI | | Immatriculation ; NULL pour engin hors route non immatriculé (C-13) | `TEST-0001` | interne |
| `registration_norm` | `text` | OUI | générée (majuscules, sans espaces ni tirets) ; `UNIQUE (tenant_id, registration_norm)` (NULL distincts) ; non vide après normalisation | | | interne |
| `serial_number`, `make` | `text` | OUI | `serial_key` généré = constructeur normalisé `|` série normalisée ; `UNIQUE (tenant_id, serial_key)` | N° de série constructeur / châssis | `SN-FICTIF-0001` | interne |
| `model` | `text` | OUI | | Modèle | `ModeleTest 40` | interne |
| `model_year` | `smallint` | OUI | 1950 ≤ année ≤ 2100 (borne statique) | | `2019` | interne |
| `ownership_type` | `text` | NON | CHECK `OWNED`, `LEASED`, `SUBCONTRACTED` | Le lien vers sous-traitant/contrat vient avec le lot Contrats | `OWNED` | interne |
| `fuel_type` | `text` | OUI | CHECK `DIESEL`, `PETROL`, `ELECTRIC`, `OTHER` | | `DIESEL` | interne |
| `rated_payload_kg` | `integer` | OUI | > 0 | **Capacité nominale constructeur**, **jamais une mesure de charge** **[V]** (H10) | valeur fictive | interne |
| `status` | `text` | NON | CHECK `AVAILABLE`, `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED` (D-02) | Statut stocké ; « en exploitation » est dérivé (RM-016) | `AVAILABLE` | interne |
| `status_reason_code` | `text` | OUI | requis si `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED` | Motif (ex. `BREAKDOWN`, `ACCIDENT`, `DOCUMENT_EXPIRED`, `AWAITING_PARTS`) | `BREAKDOWN` | interne |
| `status_changed_at` | `timestamptz` | NON | positionné par trigger | Dernier changement (UTC) | | interne |
| `commissioned_on`, `decommissioned_on` | `date` | OUI | `(status='RETIRED') = (decommissioned_on IS NOT NULL)` | Mise en parc / réforme | | interne |
| `notes` | `text` | OUI | ≤ 2000 ; **pas de donnée personnelle** | | | interne |

**Plus aucune colonne de compteur** (odomètre/horamètre) sur `vehicle` : la valeur courante sera une vue sur `vehicle_meter_reading`, livrée avec la première story de compteur (D-16, §15). `RETIRED` est terminal (C-13). `site_id` ne change que par une opération explicite, **refusée si une affectation `PLANNED`/`ACTIVE` existe** (D-13, trigger de garde).

## 10. `vehicle_status_history` (tranche 1b, ajout seul)

Historique des changements de statut, alimenté par **trigger** sur `vehicle` (création, changement, `UPDATE` en masse) — D-02, DB-16. Base du calcul de durée d'immobilisation (RM-092).

| Colonne | Type | Null | Contrainte | Description FR |
|---------|------|------|-----------|----------------|
| `vehicle_status_history_id` | `uuid` | NON | PK `DEFAULT gen_random_uuid()` | |
| `tenant_id`, `vehicle_id` | `uuid` | NON | FK composite `(tenant_id, vehicle_id)` | |
| `from_status` | `text` | OUI | NULL à la création | |
| `to_status` | `text` | NON | CHECK des 5 statuts | |
| `reason_code` | `text` | OUI | | |
| `changed_at` | `timestamptz` | NON | | UTC |
| `changed_by` | `uuid` | OUI | sans FK | |

`UPDATE`/`DELETE`/`TRUNCATE` refusés (trigger `MF001`). Index `(tenant_id, vehicle_id, changed_at DESC)`. Un historique de site (`vehicle_site_history`) n'est pas créé au lot 1 (DB-17).

## 11. `driver` (tranche 1b)

Personne conductrice / opératrice (profil `workforce`). Un conducteur n'a pas forcément de compte **[V]** (H6). Au lot 1, `driver` est conservé (pas de `person`, D-16, C-05).

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `driver_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, driver_id)` | | | interne |
| `tenant_id` | `uuid` | NON | FK | | | interne |
| `site_id` | `uuid` | NON | FK composite | **Site de rattachement** (renommé depuis `home_site_id`, DB-17) | | interne |
| `user_account_id` | `uuid` | OUI | FK composite ; `UNIQUE (tenant_id, user_account_id)` | Compte lié, 1:1 au plus. Colonne présente, **liaison et écran conducteur hors lot 1** (D-16) | | interne |
| `employee_number` | `text` | NON | `UNIQUE (tenant_id, employee_number)` | Matricule interne | `MAT-0001` | personnel |
| `last_name`, `first_name` | `text` | NON | | Nom, prénom | `Nom-Test` | personnel |
| `phone` | `text` | OUI | E.164 | Contact ; **visible `HR` seulement, masquage serveur total pour les autres rôles** (D-15) | `+224000000002` | personnel |
| `employment_type` | `text` | NON | CHECK `EMPLOYEE`, `TEMP_AGENCY`, `SUBCONTRACTOR` | | `EMPLOYEE` | personnel |
| `external_company_name` | `text` | OUI | requis si `SUBCONTRACTOR` | Libellé libre provisoire | `Transport Démo SARL` | interne |
| `hire_date`, `exit_date` | `date` | OUI | `exit_date ≥ hire_date` ; `(status='INACTIVE') = (exit_date IS NOT NULL)` | Embauche / sortie | | personnel |
| `status` | `text` | NON | CHECK `ACTIVE`, `UNAVAILABLE`, `SUSPENDED`, `INACTIVE` (D-03) | Situation administrative, pas l'aptitude | `ACTIVE` | personnel |
| `unavailability_reason` | `text` | OUI | `(status='UNAVAILABLE') = (… IS NOT NULL)` ; `LEAVE`, `TRAINING`, `OTHER` | Motif générique, **aucun motif de santé** (D-15) | `LEAVE` | personnel |
| `unavailable_until` | `date` | OUI | | Retour prévu | | personnel |
| `suspension_reason_code` | `text` | OUI | `(status='SUSPENDED') = (… IS NOT NULL)` | Code de motif (pas de texte libre) ; visible `HR` et `HSE` seulement | `HSE_DECISION` | sensible |
| `anonymized_at` | `timestamptz` | OUI | | Anonymisation (identité remplacée, téléphone effacé) | | interne |

**Minimisation (D-15)** : le lot 1 ne stocke **ni date de naissance, ni aptitude médicale, ni motif maladie, ni adresse, ni pièce d'identité, ni photo**. Leur ajout est une migration ultérieure conditionnée à l'avis du juriste (C-08). Les garde-fous d'exposition sont dans `MATRICE_RBAC.md` ; `TENANT_ADMIN` ne lit pas les données personnelles conducteur (D-10). Passer un conducteur en non-`ACTIVE` est refusé (409) tant qu'une affectation `PLANNED`/`ACTIVE` existe (D-11).

## 12. `driver_license` et `license_category_ref` (tranche 1b)

Permis de conduire délivré par l'État. Une ligne par couple (conducteur, catégorie) ; un permis multi-catégories produit plusieurs lignes de même `license_number`.

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `driver_license_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, driver_license_id)` | | | interne |
| `tenant_id`, `driver_id` | `uuid` | NON | FK composite vers `driver` | | | interne |
| `license_number` | `text` | NON | | N° de permis ; **visible `HR` seulement**, masquage serveur total sinon (D-15) ; jamais journalisé | `PERMIS-FICTIF-0001` | personnel |
| `category_code` | `text` | NON | FK `license_category_ref(code)` ; **`UNIQUE (tenant_id, driver_id, license_number, category_code, issue_date)`** | Catégorie ; l'`issue_date` dans l'unicité conserve l'historique d'un renouvellement | `C` | personnel |
| `issuing_authority` | `text` | OUI | | | `Autorité Test` | personnel |
| `issue_date` | `date` | NON | ≤ date du jour : contrôle **applicatif** | Délivrance | `2020-01-15` | personnel |
| `expiry_date` | `date` | NON | `> issue_date` | Dernier jour de validité **inclus**, fuseau du site (RM-021) | `2030-01-14` | personnel |
| `status` | `text` | NON | CHECK `VALID`, `SUSPENDED`, `WITHDRAWN` | Statut **administratif** ; prime sur les dates. L'expiration est **dérivée à la lecture** (`VALID`/`EXPIRING`/`EXPIRED`, seuil `EXPIRING` configurable par tenant) | `VALID` | sensible |
| `status_note` | `text` | OUI | | Référence de décision, sans détail judiciaire | | sensible |
| `document_reference` | `text` | OUI | | Référence du justificatif papier (pas d'image au lot 1) | `CLASSEUR-A12` | interne |
| `verified_by`, `verified_at` | `uuid`, `timestamptz` | OUI | FK simple ; renseignés ensemble | Qui a vérifié l'original | | interne |

Index `(tenant_id, expiry_date) WHERE status='VALID'` pour la liste des échéances du tenant (US-1.20). L'exigence de vérification pour l'affectation `ACTIVE` est une règle applicative paramétrable (RM-029, **[A]**).

**`license_category_ref`** (global, **à valider localement**, C-07) : `code` PK, `label_fr`, `validated_locally boolean` (défaut `false`), `is_active`. Valeurs de départ : `A` Motocyclettes ; `B` Véhicules légers ; `C` Poids lourds (porteurs) ; `D` Transport en commun de personnes ; `E` Ensemble avec remorque/semi-remorque — **toutes « à valider localement »** (hypothèse de nomenclature [H] ; ni catégories exactes, ni durées, ni équivalence engins hors route vérifiées). Aucune règle d'éligibilité n'est définitive tant que le référentiel n'est pas validé ; valeurs fictives en développement.

## 13. `driver_qualification` (tranche 1b)

Habilitation interne de conduite d'une catégorie d'engin et autres qualifications à validité bornée.

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `driver_qualification_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, driver_qualification_id)` | | | interne |
| `tenant_id`, `driver_id` | `uuid` | NON | FK composite | | | interne |
| `qualification_type` | `text` | NON | CHECK `DRIVING_AUTHORIZATION`, `SAFETY_TRAINING`, `OTHER` | Nature. **`MEDICAL_FITNESS` absent** (D-15) | `DRIVING_AUTHORIZATION` | interne |
| `vehicle_category_id` | `uuid` | OUI | FK composite ; **requis** si `DRIVING_AUTHORIZATION` | Catégorie visée | | interne |
| `site_id` | `uuid` | OUI | FK composite | NULL = valable tout le tenant (**[A]** RM-055) | | interne |
| `valid_from` | `date` | NON | | | | interne |
| `valid_to` | `date` | OUI | `≥ valid_from` ; NULL = sans échéance (déconseillé pour la conduite) | Fin incluse | | interne |
| `status` | `text` | NON | CHECK `VALID`, `SUSPENDED`, `REVOKED` | Prime sur les dates | `VALID` | interne |
| `issued_by_name`, `reference`, `restrictions` | `text` | OUI | | Formateur, n° de certificat, restrictions courtes | `HAB-0001` | personnel |

Exclusion `ex_dq_no_overlap` : pas de chevauchement de deux lignes `VALID` de même `(driver, type, COALESCE(vehicle_category_id), COALESCE(site_id))` sur `daterange(valid_from, valid_to, '[]')` — les `COALESCE` évitent le contournement par NULL (DB-10). Renouvellement anticipé : raccourcir `valid_to` de l'ancienne ligne dans la même transaction (audit). Index `(tenant_id, valid_to) WHERE status='VALID'`. **Aucune donnée médicale** : l'aptitude médicale n'est pas stockée au lot 1 (C-08).

## 14. `vehicle_assignment` (tranche 1c)

Affectation d'un conducteur à un véhicule sur un intervalle `[valid_from, valid_to)`.

| Colonne | Type | Null | Contrainte | Description FR | Exemple fictif | Sensibilité |
|---------|------|------|-----------|----------------|----------------|-------------|
| `vehicle_assignment_id` | `uuid` | NON | PK ; `UNIQUE (tenant_id, vehicle_assignment_id)` | | | interne |
| `tenant_id` | `uuid` | NON | FK | | | interne |
| `site_id` | `uuid` | NON | FK composite ; trigger : égal au site du véhicule **et** du conducteur à la création (D-13) | Site d'exploitation, **figé** | | interne |
| `vehicle_id`, `driver_id` | `uuid` | NON | FK composites ; immuables après création | | | interne / personnel |
| `valid_from` | `timestamptz` | NON | UTC, inclus ; **pas d'antidatage** : `≥ now − tolérance configurable` (contrôle applicatif, D-13) | | `2026-11-01T06:00:00Z` | interne |
| `valid_to` | `timestamptz` | OUI | `> valid_from` ; exclue ; NULL = ouverte ; **obligatoire si `COMPLETED`** (fin réelle) | | | interne |
| `valid_during` | `tstzrange` | NON | générée `tstzrange(valid_from, valid_to, '[)')` | Pour l'exclusion | | interne |
| `shift_code` | `text` | OUI | texte libre du tenant | Poste informatif (RM-034) | `JOUR` | interne |
| `status` | `text` | NON | CHECK `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED` (D-04) | | `PLANNED` | interne |
| `status_reason` | `text` | OUI | requis pour `SUSPENDED`, `COMPLETED`, `CANCELLED` | Code motif (ex. `LICENSE_EXPIRED`, `VEHICLE_IMMOBILIZED`, `TRANSFER`, `NORMAL_END`) | `NORMAL_END` | interne |
| `eligibility_snapshot` | `jsonb` | NON | `jsonb_typeof = 'object'` | Photo du contrôle : **identifiants et dates seulement** (jamais n° de permis ni motif), date d'évaluation | | personnel |
| `created_by` | `uuid` | NON | sans FK | | | interne |

**Il n'y a pas de colonne `approved_by`** : dérogation d'éligibilité et d'antidatage reportées (D-13). Exclusions (extension `btree_gist`) : `ex_va_vehicle_no_overlap (vehicle_id WITH =, valid_during WITH &&)` et `ex_va_driver_no_overlap (driver_id WITH =, valid_during WITH &&)`, toutes deux `WHERE status <> 'CANCELLED'` (D-04) ; `tenant_id` n'y figure pas (UUID global). `COMPLETED` et `CANCELLED` sont immuables (trigger `MF003`). Éligibilité applicative (RM-030) ; conformité **dérivée à la lecture** (D-12).

## 15. Tables des lots ultérieurs (non créées au lot 1)

| Table | Lot | Décision | Remarque |
|-------|-----|----------|----------|
| `idempotency_record` | **lot 4** (offline) | D-14 | Au lot 1, les doublons sont empêchés par les contraintes d'unicité et d'exclusion ; aucune `Idempotency-Key` au lot 1. Esquisse dans `MODELE_PHYSIQUE_LOT1.md` §11 |
| `vehicle_meter_reading` | avec la **première story de compteur** | D-16 | Sources en anglais (`MANUAL`, `MOBILE_CHECKLIST`, `CAN_ECU`, `GPS_DERIVED`, `IMPORT`) ; types `ODOMETER_KM`, `HOUR_METER_H` ; natures `READING`, `CORRECTION`, `METER_REPLACEMENT` ; append-only ; valeur courante par vue, aucune colonne sur `vehicle`. Esquisse en `MODELE_PHYSIQUE_LOT1.md` §5.8. GPS dérivé : jamais écrasant (RM-064) |
| `vehicle_document` | lot 2 (C-06) | D-16 | Documents véhicule bloquants inconnus |
| `support_access_session` | pilote (C-10) | D-16 | Pas d'accès support plateforme au lot 1 |
| `audit_seal` | après lot 1 | D-16, D-17 | Scellement asynchrone (chaînage de hash reporté) |
| `person` | lot 3 (C-05) | D-16 | Migration non destructive, `driver.person_id` |
| `vehicle_site_history` | lot 2/6 | DB-17 | Si rapports « parc par site à la date T » |

## 16. `audit_event` (tranche 1a, ajout seul, partitionné)

Schéma **unique**, identique à `MODELE_PHYSIQUE_LOT1.md` §5.4 et à ADR-005. **Fait vérifié** : audit events exigés par CLAUDE.md. Écrit dans la **même transaction** que la mutation (hors événements d'authentification et refus, en transaction propre).

| Colonne | Type | Null | Contrainte | Description FR | Sensibilité |
|---------|------|------|-----------|----------------|-------------|
| `audit_event_id` | `uuid` | NON | `DEFAULT gen_random_uuid()` ; PK `(audit_event_id, occurred_at)` | Identifiant (la clé inclut la colonne de partition) | interne |
| `audit_seq` | `bigint` | NON | séquence | Ordre d'insertion (pour le scellement futur) | interne |
| `tenant_id` | `uuid` | NON | FK `tenant` | Tenant ; les événements de plateforme appartiennent au tenant plateforme | interne |
| `site_id` | `uuid` | OUI | | Site concerné | interne |
| `occurred_at` | `timestamptz` | NON | défaut `clock_timestamp()` ; **clé de partition mensuelle** | Instant (UTC, horloge serveur) | interne |
| `actor_user_id` | `uuid` | OUI | FK simple | NULL si système ou anonyme | personnel |
| `actor_kind` | `text` | NON | CHECK `USER`, `SYSTEM`, `PLATFORM_SUPPORT`, `DEVICE_SYNC`, `ANONYMOUS` | `ANONYMOUS` : connexion échouée d'un compte inconnu | interne |
| `support_session_id` | `uuid` | OUI | `(actor_kind='PLATFORM_SUPPORT') = (… IS NOT NULL)` | Hors lot 1 (pas d'accès support) | interne |
| `action` | `text` | NON | motif `<entité>.<verbe>` snake_case avec point (`assignment.create`, `auth.login_failed`) ; liste fermée côté application | | interne |
| `entity_type`, `entity_id` | `text`, `uuid` | NON / OUI | | Objet concerné | interne |
| `outcome` | `text` | NON | CHECK `SUCCESS`, `DENIED`, `FAILURE` | Les refus d'autorisation (403) sont journalisés | interne |
| `reason` | `text` | OUI | | Motif saisi | interne |
| `changed_fields` | `text[]` | OUI | | **Noms** des champs modifiés, sensibles inclus, jamais leurs valeurs | interne |
| `before_data`, `after_data` | `jsonb` | OUI | **aucun champ sensible**, secret, n° de permis, téléphone ni GPS brut | États avant/après | personnel |
| `request_id` | `uuid` | OUI | | Corrélation avec les logs | interne |
| `ip_address`, `user_agent` | `inet`, `text` | OUI | | Origine (donnée personnelle ; rétention C-09) | personnel |
| `prev_hash`, `row_hash` | `bytea` | OUI | **nullables, non renseignées au lot 1** | Réservées au scellement asynchrone ultérieur (D-16, D-17) ; **pas de chaînage en ligne** | interne |

Protection (D-17) : `mf_app` = `INSERT`/`SELECT` seulement ; trigger bloquant `UPDATE`/`DELETE`/`TRUNCATE` (`MF001`) ; RLS ; partitions **mensuelles dès la création de la table**, partition `DEFAULT` maintenue vide, chaque partition créée par la fonction d'exploitation avec RLS forcée et aucun droit pour `mf_app`. Lecture : `TENANT_ADMIN`, `AUDITOR` (D-10), toujours filtrée par tenant. Les `404` sur identifiant d'un autre tenant ne sont **pas** des événements d'audit tenant : ce sont des événements de sécurité en log structuré (D-05). Durée de conservation : **[A]** (C-09).

---

## 17. Index et performances (indicatif)

- Tous les index composites commencent par `tenant_id` **[H]**.
- `vehicle(tenant_id, site_id, status)`, `driver(tenant_id, site_id, status)`, `driver_license(tenant_id, driver_id, category_code, expiry_date DESC)` et `(tenant_id, expiry_date) WHERE status='VALID'`, `driver_qualification(tenant_id, driver_id, valid_to)` et `(tenant_id, valid_to) WHERE status='VALID'`, `vehicle_assignment(tenant_id, vehicle_id, valid_from DESC)` / `(tenant_id, driver_id, valid_from DESC)` / `(tenant_id, site_id, status)`, `vehicle_status_history(tenant_id, vehicle_id, changed_at DESC)`, `audit_event(tenant_id, occurred_at DESC)`, `(tenant_id, entity_type, entity_id, occurred_at DESC)`, `(tenant_id, actor_user_id, occurred_at DESC)`, `(tenant_id, site_id, occurred_at DESC)`.
- Pagination à clé stable `(tenant_id, …, id)`. Aucun volume ni objectif de performance n'est fixé (donnée non disponible ; hypothèse de développement C-15).

## 18. Non couvert au lot 1 (pour mémoire)

Documents réglementaires du véhicule (assurance, contrôle technique) : non modélisés (C-06, `vehicle_document` au lot 2) ; risque accepté tant que la décision n'est pas prise. Mécaniciens et autres personnels : voir `person` (C-05). Données de santé, date de naissance, adresse : exclues (D-15, C-08). Exports, accès support, liaison compte↔conducteur : hors lot 1 (D-16).
