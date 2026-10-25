# Revue croisée — Database architect (cadrage, Lot 1)

> Statut : **revue de cadrage (phase 0)**. Lecture seule des documents ; aucun SQL, aucune migration, aucune base n'a été exécuté. Tout ce qui est écrit ici est une analyse ou une proposition, **non testée**.
> Documents lus : `CLAUDE.md`, `00_SOCLE_CADRAGE.md`, `PRD_MVP.md`, `USER_STORIES.md`, `MODELE_CONCEPTUEL.md`, `DICTIONNAIRE_DONNEES.md`, `REGLES_METIER.md`, `MATRICE_RBAC.md`, `MENACES_ET_CONTROLES.md`, `ADR-001` à `ADR-005`, `INTEGRATION_GPS_OFFLINE.md`, `ARCHITECTURE.md`, `PARCOURS_UTILISATEURS.md` (parties touchant au modèle de données : S01-S19).
> Livrable associé : `docs/MODELE_PHYSIQUE_LOT1.md` (modèle cible intégrant ces corrections).
> Gravité : **Bloquant** = la migration 0001 (ou l'isolation / l'intégrité) ne peut pas être écrite correctement sans arbitrage ; **Majeur** = à corriger avant la migration de la table concernée ; **Mineur** = à corriger avant la fin du lot 1.
> Les identifiants techniques sont en anglais (socle §6). Les « Fichiers » désignent les documents revus.

## 0. Synthèse

| ID | Gravité | Sujet |
|----|---------|-------|
| DB-01 | Bloquant | Langue des valeurs d'énumération et statuts véhicule (PRD/US vs modèle) |
| DB-02 | Bloquant | Statuts divergents des autres entités (tenant, compte, conducteur, affectation, permis) |
| DB-03 | Bloquant | Politique RLS `current_setting(...)::uuid` : erreur sur valeur vide après réutilisation de connexion |
| DB-04 | Bloquant | `tenant_id` NULL pour la plateforme : FK composites contournées, unicités et RLS fragiles |
| DB-05 | Bloquant | Tables d'identité vs RLS : connexion, refresh, provisioning de tenant, vues plateforme |
| DB-06 | Bloquant | Entités manquantes au lot 1 : jetons d'invitation/réinitialisation, sessions, idempotence |
| DB-07 | Bloquant | Unicité de l'e-mail et identifiant de connexion (dictionnaire vs US-1.08 / S01) |
| DB-08 | Bloquant | `audit_event` : partitionnement, clé primaire et rétention incompatibles avec l'ajout seul |
| DB-09 | Majeur | Contrainte d'exclusion des affectations : statuts, intervalle vide, troncature de `valid_to` |
| DB-10 | Majeur | Exclusion des habilitations : NULL contourne la contrainte ; renouvellement |
| DB-11 | Majeur | Permis : unicité bloquant l'historique de renouvellement ; statut stocké vs dérivé |
| DB-12 | Majeur | `vehicle_category` : tableau de codes de permis non contraignable ; portée global/tenant (Q2) |
| DB-13 | Majeur | Référentiel `role` : CHECK sur 14 codes, `allowed_scopes` en tableau |
| DB-14 | Majeur | `driver` vs `person` générique |
| DB-15 | Majeur | `vehicle_meter_reading` : décision, doublon avec les colonnes du véhicule, aucune user story |
| DB-16 | Majeur | Pas d'historique des changements de statut du véhicule (RM-092, durée d'immobilisation) |
| DB-17 | Majeur | `site_id` sur `vehicle` / `driver` : nommage, cohérence avec l'affectation, historique de transfert |
| DB-18 | Majeur | Clés étrangères composites incomplètes (colonnes acteur, `correction_of`, audit) |
| DB-19 | Majeur | `audit_event` : schémas divergents entre ADR-005, dictionnaire, RBAC et menaces |
| DB-20 | Majeur | Chaîne de hachage en ligne : sérialisation des écritures ; statut incohérent entre documents |
| DB-21 | Majeur | Accès support `PLATFORM_ADMIN` : lot 1 ou non (RBAC/MENACES vs PRD/US) |
| DB-22 | Majeur | Minimisation : aptitude médicale, date de naissance, `ARRET_MALADIE`, adresse/pièce d'identité |
| DB-23 | Majeur | Suppression logique : `archived_at` vs `status` ; anonymisation vs ajout seul |
| DB-24 | Majeur | Concurrence optimiste : mécanisme `row_version` / ETag non défini |
| DB-25 | Majeur | Partitions : privilèges et RLS contournables par accès direct à la partition |
| DB-26 | Majeur | `FORCE ROW LEVEL SECURITY` vs `mf_owner` (migrations, jobs transverses, fixtures) |
| DB-27 | Majeur | Extensions et bootstrap : PostGIS non « trusted », `citext` non listée, `pgcrypto` inutile |
| DB-28 | Majeur | Documents réglementaires du véhicule (assurance, visite technique) |
| DB-29 | Mineur | Index manquants ou inadaptés |
| DB-30 | Mineur | Normalisation numéro de parc / immatriculation / série |
| DB-31 | Mineur | CHECK non déterministes (`now()`, `CURRENT_DATE`) |
| DB-32 | Mineur | Types temporels : dates vs instants, bornes d'intervalle, fuseau de session |
| DB-33 | Mineur | `user_account` : `LOCKED` stocké et dérivé, champs IP/agent, `token_version` |
| DB-34 | Mineur | Conventions de nommage (clés, codes référentiels, actions d'audit, contraintes) |
| DB-35 | Mineur | Tests d'introspection ST-04/ST-05 : exceptions à lister |
| DB-36 | Mineur | Alembic : l'autogénération ne voit ni RLS, ni triggers, ni EXCLUDE, ni partitions |
| DB-37 | Mineur | `tenant` : drapeau « fictif », unicité du nom, type de tenant |
| DB-38 | Mineur | `site.location` (PostGIS) : validation et utilité au lot 1 |
| DB-39 | Mineur | UUID v7 vs v4 (dépendance) |
| DB-40 | Mineur | Portée site hors RLS : confirmation d'ADR-002 §3.3 |
| DB-41 | Mineur | `eligibility_snapshot` : contenu et sensibilité |
| DB-42 | Mineur | Rétention des tables éphémères (sessions, jetons, idempotence) |

Total : 8 bloquants, 20 majeurs, 14 mineurs.

Points conformes confirmés : séparation compte/personne (H6) ; FK composites `(tenant_id, id)` (H3) ; rôle applicatif non propriétaire, sans `BYPASSRLS` ; `FORCE ROW LEVEL SECURITY` ; énumérations en `text` + `CHECK` plutôt qu'`ENUM` PostgreSQL ; audit dans la même transaction (ADR-005) ; GNF entier ; aucune donnée GPS dans le tonnage.

---

## 1. Bloquants

### DB-01 — Langue des valeurs d'énumération et statuts du véhicule
- **Fichiers** : `PRD_MVP.md` §13 E1 ; `USER_STORIES.md` §0.3, US-1.12, 1.14, 1.15, 1.22 (R2, A6) ; `MODELE_CONCEPTUEL.md` §4.1 ; `DICTIONNAIRE_DONNEES.md` §7 ; `REGLES_METIER.md` RM-014 à RM-017, RM-030 ; `PARCOURS_UTILISATEURS.md` S10.
- **Constat** : trois vocabulaires coexistent. PRD/US : `ACTIVE`, `IN_MAINTENANCE`, `OUT_OF_SERVICE`, `RETIRED` (4 valeurs, pas d'immobilisation). Modèle/dictionnaire/règles : `DISPONIBLE`, `EN_MAINTENANCE`, `IMMOBILISE`, `HORS_SERVICE`, `REFORME` (5 valeurs, en français). Le socle impose des identifiants techniques en anglais et le modèle lui-même dit « codes stables en MAJUSCULES (libellés FR côté interface) ». Les codes d'erreur des US (`VEHICLE_NOT_AVAILABLE`, `DRIVER_NOT_QUALIFIED`) et les rôles sont déjà en anglais. `ACTIVE` pour un véhicule reproduit l'ambiguïté que le modèle a justement levée (`EN_SERVICE` : réceptionné ou en exploitation ?) et ne couvre pas `IMMOBILISE`, que RM-017 et le processus panne → OT exigent.
- **Décision recommandée** : **valeurs d'énumération techniques en anglais, `UPPER_SNAKE_CASE`**, libellés français uniquement dans le catalogue i18n de l'interface (ADR-004). Justification : (1) cohérence avec le socle §6 et avec les rôles, modules, permissions et codes d'erreur ; (2) un seul vocabulaire base / API / OpenAPI / client TypeScript / tests ; une API qui renverrait `"status": "IMMOBILISE"` mélangerait les langues ; (3) pas d'accents ni de risque d'encodage dans les `CHECK`, les index et les exports ; (4) le français reste la langue de l'utilisateur sans coûter une migration le jour où une autre langue est ajoutée ; (5) inconvénient accepté : un analyste SQL lit des codes anglais, compensé par un glossaire (code → libellé FR) dans le dictionnaire. On ne stocke jamais de libellé dans une colonne de statut. Un code publié ne se renomme que par migration.
- **Statut véhicule retenu (5 valeurs du modèle, traduites)** : `AVAILABLE` (DISPONIBLE), `IN_MAINTENANCE` (EN_MAINTENANCE), `IMMOBILIZED` (IMMOBILISE), `OUT_OF_SERVICE` (HORS_SERVICE), `RETIRED` (REFORME, terminal). « En exploitation » reste **dérivé** (affectation `ACTIVE`), jamais stocké (RM-016). Mise en garde d'usage : `AVAILABLE` est une disponibilité technique/administrative ; la disponibilité pour affecter = `AVAILABLE` **et** aucune affectation chevauchante. L'UI doit nommer le sous-état dérivé « Libre » / « En exploitation » pour éviter la confusion.
- **Correction** : `PRD_MVP.md` E1 et `USER_STORIES.md` §0.3 reprennent les 5 valeurs ci-dessus ; `MODELE_CONCEPTUEL.md` §4.1 et `DICTIONNAIRE_DONNEES.md` §7 traduisent les codes ; ajouter au dictionnaire un glossaire code → libellé FR. Les codes de `vehicle_category` (ex. `CAMION_BENNE_RIGIDE`) sont aussi des identifiants techniques : les traduire (correspondance dans `MODELE_PHYSIQUE_LOT1.md` §5.5). `shift_code` reste une valeur libre du tenant (non énumérée).

### DB-02 — Statuts divergents des autres entités
- **Fichiers** : `USER_STORIES.md` §0.3 ; `DICTIONNAIRE_DONNEES.md` §1, 2, 3, 8, 9, 10, 11 ; `MODELE_CONCEPTUEL.md` §4.2, 4.3 ; `PARCOURS_UTILISATEURS.md` S05, S07.
- **Constat** : tenant `ACTIF/SUSPENDU/ARCHIVE` vs `ACTIVE/SUSPENDED` ; compte `INVITE/ACTIF/VERROUILLE/DESACTIVE` vs `INVITED/ACTIVE/DISABLED` ; conducteur 4 états vs `ACTIVE/INACTIVE` ; affectation `PLANIFIEE/ACTIVE/SUSPENDUE/TERMINEE/ANNULEE` vs `PLANNED/ACTIVE/CLOSED` (qui fusionne fin normale et annulation, alors que US-1.23 A5 annule via `CLOSED`) ; permis `VALIDE/SUSPENDU/RETIRE` vs statut dérivé `VALID/EXPIRING/EXPIRED`.
- **Décision** : retenir la richesse du modèle, en anglais :
  tenant `ACTIVE | SUSPENDED | ARCHIVED` ; site `ACTIVE | INACTIVE` ; compte `INVITED | ACTIVE | DISABLED` ; conducteur `ACTIVE | UNAVAILABLE | SUSPENDED | INACTIVE` ; affectation `PLANNED | ACTIVE | SUSPENDED | COMPLETED | CANCELLED` ; permis (statut administratif stocké) `VALID | SUSPENDED | WITHDRAWN` ; habilitation `VALID | SUSPENDED | REVOKED` ; audit `outcome` `SUCCESS | DENIED | FAILURE`. `VERROUILLE` est retiré du statut du compte (voir DB-33). L'état d'expiration d'un permis (`VALID/EXPIRING/EXPIRED`) est **calculé** (vue/API), jamais stocké (DB-11).
- **Correction** : `USER_STORIES.md` §0.3 et US-1.14/1.22/1.23 (utiliser `COMPLETED`/`CANCELLED`) ; `PARCOURS_UTILISATEURS.md` S07 (`DISABLED`, pas de statut « verrouillé » stocké).

### DB-03 — Politique RLS : `current_setting('app.tenant_id', true)::uuid`
- **Fichiers** : `ADR-002` §3.1 (politique type) ; `MENACES_ET_CONTROLES.md` ST-03 ; `USER_STORIES.md` US-1.28 A5.
- **Constat** : ADR-002 affirme que, sans variable, `current_setting(..., true)` vaut NULL et que la politique « refuse tout ». Vrai sur une connexion neuve. Après un `set_config(..., true)` dans une transaction, le paramètre personnalisé existe pour la session et **retombe à la chaîne vide** (et non NULL) à la fin de la transaction. Sur une connexion de pool réutilisée sans nouveau contexte, `''::uuid` lève une **erreur** (syntaxe uuid invalide) au lieu de retourner 0 ligne. Le comportement reste « fermé », mais ST-03 (« absent → zéro ligne ») est faux dans le cas réaliste du pool, et une erreur 500 masque l'origine du défaut.
- **Correction** : fonction `app.current_tenant_id()` = `NULLIF(current_setting('app.tenant_id', true), '')::uuid`, utilisée dans toutes les politiques (voir `MODELE_PHYSIQUE_LOT1.md` §4). Ajouter le test « transaction 1 avec contexte, commit, transaction 2 sur la même connexion sans contexte → 0 ligne, sans erreur ». Compléter `pool_reset_on_return` côté SQLAlchemy.

### DB-04 — `tenant_id` NULL pour les comptes et événements plateforme
- **Fichiers** : `MODELE_CONCEPTUEL.md` §1 (exceptions), `user_account`, `user_role_assignment`, `audit_event` ; `DICTIONNAIRE_DONNEES.md` §3, 5, 13 ; `MATRICE_RBAC.md` §4.1 ; `00_SOCLE_CADRAGE.md` H3.
- **Constat** : `tenant_id` nullable sur trois tables crée quatre défauts. (1) Une FK composite `(tenant_id, user_account_id)` avec `tenant_id` NULL n'est **pas vérifiée** (MATCH SIMPLE) : une attribution de portée `PLATFORM` peut référencer un compte inexistant. (2) `UNIQUE (tenant_id, email)` ne détecte aucun doublon entre comptes plateforme (NULL distincts) : il faut un index partiel séparé (le dictionnaire le sait mais seulement pour l'e-mail). (3) Les politiques RLS doivent traiter NULL à part ; une erreur d'`OR tenant_id IS NULL` ouvre une fuite. (4) Le contrôle « un tenant ne peut jamais détenir une portée `PLATFORM` » (T-08, RBAC §4.2) est applicatif seulement.
- **Correction recommandée** : **tenant plateforme réservé** (« pseudo-tenant » `kind = 'PLATFORM'`, UUID fixe, un seul, code `mf-platform`). `tenant_id` devient `NOT NULL` partout (H3 respecté sans exception), les FK composites fonctionnent, la RLS est uniforme, l'e-mail est unique par `(tenant_id, email)` sans index spécial. Le contrôle « portée `PLATFORM` ⇔ tenant plateforme » devient déclaratif via `user_role_assignment.tenant_kind` + FK `(tenant_id, tenant_kind)` → `tenant(tenant_id, kind)` + `CHECK`. Risque assumé : le pseudo-tenant doit être exclu des listes de tenants clients (filtre `kind`) ; `RBAC §4.1` (« espace d'identité plateforme séparé ») reste vrai logiquement. Supprimer `user_account.is_platform_account`.

### DB-05 — Tables d'identité et RLS : flux pré-authentification
- **Fichiers** : `ADR-002` §3.1, §3.4 ; `ADR-003` §3 ; `USER_STORIES.md` US-1.01, 1.05, 1.08, 1.10 ; `MENACES_ET_CONTROLES.md` C-40.
- **Constat** : ADR-002 suppose que `app.tenant_id` est connu avant toute requête, car issu du jeton. Mais la connexion, l'activation d'invitation, la réinitialisation de mot de passe et le refresh de jeton **cherchent** le compte ou la session avant que le tenant soit établi. Il faut aussi : la création de tenant par `PLATFORM_ADMIN` (insertion de lignes dans le nouveau tenant depuis le contexte plateforme), la liste des tenants pour la plateforme, et des métriques agrégées (RBAC §2.1 note 1). Le document ne dit pas comment, et la RLS stricte bloque tous ces cas.
- **Correction** (détail en `MODELE_PHYSIQUE_LOT1.md` §6) : (a) résolution du tenant par son **code** via une politique de lecture sur `tenant` conditionnée à un réglage de transaction `app.login_tenant_code` (ne divulgue que la ligne dont le code exact est fourni, pas de listage) ; (b) jetons de rafraîchissement, d'invitation et de réinitialisation portent le préfixe `<tenant_id>.` utilisé uniquement pour fixer le contexte, le secret haché restant l'autorité ; (c) provisioning : une seule fonction applicative, auditée, change le contexte en cours de transaction du tenant plateforme vers le nouveau tenant (test d'architecture : aucun autre appelant de `set_config('app.tenant_id')`) ; (d) politique `tenant` : lecture/écriture de la ligne propre, plus toutes les lignes en contexte plateforme ; l'insertion de tenant est réservée au contexte plateforme (trigger de garde sur `status`, `code`, `kind`, `is_demo`) ; (e) pas de `BYPASSRLS`. Rappel de modèle de menace à inscrire dans ADR-002 : la RLS protège contre les **défauts de l'application** (filtre oublié), pas contre une application compromise qui fixerait elle-même le contexte.

### DB-06 — Entités manquantes pour que le lot 1 soit réalisable
- **Fichiers** : `00_SOCLE_CADRAGE.md` §5 ; `DICTIONNAIRE_DONNEES.md` §3 (« hors dictionnaire lot 1 ») ; `PRD_MVP.md` §13 E4, E6 ; `USER_STORIES.md` US-1.04, 1.05, 1.08, 1.09, 1.10, 1.12 A8, 1.22 A15 ; `ADR-003` §3 (`auth_session`) ; `INTEGRATION_GPS_OFFLINE.md` §2.1 (`idempotency_record`) ; `MENACES_ET_CONTROLES.md` C-13.
- **Constat** : les stories du lot 1 exigent invitation à jeton unique, réinitialisation, sessions révocables avec rotation de refresh, déconnexion serveur, et clé d'idempotence sur les créations. Aucune de ces tables n'est dans le socle (12 entités) ni dans le dictionnaire.
- **Correction** : ajouter trois tables tenant-scopées : `account_token` (finalité `INVITATION` | `PASSWORD_RESET`, hash SHA-256 d'un secret à forte entropie, expiration, consommation/révocation ; remplace l'entité `invitation` de E4 par une table commune, car l'invitation ne porte rien d'autre qu'un jeton : le compte `INVITED` et ses rôles existent déjà) ; `auth_session` (une ligne par session, `refresh_hash_current` / `refresh_hash_previous` pour la rotation et la détection de réutilisation avec fenêtre de grâce ADR-003 §3.3, `amr`, IP, agent, expirations, révocation) ; `idempotency_record` (clé, hash de requête, état, référence de ressource créée, expiration). Mettre à jour le socle §5 (de 12 à 15 entités métier, plus `vehicle_status_history` DB-16 et la table de jonction DB-12).

### DB-07 — Unicité de l'e-mail et identifiant de connexion
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §1 (`tenant.code` « sert à la connexion »), §3 ; `MODELE_CONCEPTUEL.md` (`user_account.email UK unique par tenant`) ; `USER_STORIES.md` US-1.04 A2/A7, US-1.08, Q16 ; `PARCOURS_UTILISATEURS.md` S01 (« pas de sélecteur de tenant (le tenant vient du compte, Q16) ») ; `REGLES_METIER.md` §11 point 13 ; `MENACES_ET_CONTROLES.md` T-16, T-43, C-40.
- **Constat** : contradiction. Le dictionnaire rend l'e-mail unique **par tenant** et prévoit un code de tenant pour la connexion ; US-1.08 et S01 connectent par **e-mail seul**. Un e-mail seul n'identifie le tenant que si l'e-mail est unique **globalement**. Or l'unicité globale rend US-1.04 A2 (« 409 sans révéler d'information sur d'autres tenants ») impossible : l'invitation d'un e-mail déjà présent ailleurs produirait un conflit observable, c'est-à-dire une énumération inter-tenant (T-16, T-43). Elle interdit aussi le consultant ou l'auditeur externe présent dans deux tenants (REGLES §11.13).
- **Recommandation** : e-mail **unique par tenant** (`UNIQUE (tenant_id, email)`, `email citext`), connexion = **identifiant d'espace de travail + e-mail + mot de passe**. L'identifiant d'espace est le `tenant.code` ; pour ne pas ajouter un champ, il peut être porté par l'URL (sous-domaine ou chemin `/t/<code>`) et pré-rempli. La première version reste « un compte = un tenant par e-mail » (Q16) sans révéler d'information inter-tenant. À défaut, si le client refuse tout identifiant d'espace, la seule alternative cohérente est l'unicité globale **avec** réponse d'invitation identique en cas de succès ou de conflit externe (envoi d'un message neutre) : plus coûteux et fuit par canaux auxiliaires. **Décision client** (voir §3).
- **Correction** : `USER_STORIES.md` US-1.08 et `PARCOURS_UTILISATEURS.md` S01 à aligner ; dictionnaire inchangé sur l'unicité mais préciser le mode de résolution du tenant.

### DB-08 — `audit_event` : partitionnement, clé primaire, rétention
- **Fichiers** : `ADR-005` §3.1 (« partitionnement envisageable plus tard »), §3.3 (purge « partition détachée ») ; `DICTIONNAIRE_DONNEES.md` §13 (PK `audit_event_id`) ; `MENACES_ET_CONTROLES.md` C-26, §9.
- **Constat** : la table est en ajout seul (trigger bloquant `DELETE`) et la rétention doit passer par le détachement de partitions. Sans partitionnement, aucune purge n'est possible sans lever la protection. Or **convertir une table existante en table partitionnée n'est pas une opération en place** (copie complète). De plus, sur une table partitionnée, la clé primaire et toute contrainte d'unicité doivent inclure la colonne de partition : `PRIMARY KEY (audit_event_id)` du dictionnaire est invalide.
- **Correction** : partitionner **dès la migration initiale** par mois sur `occurred_at` (`PARTITION BY RANGE`), `PRIMARY KEY (audit_event_id, occurred_at)`, partition `DEFAULT` maintenue vide, création des partitions futures par une fonction d'exploitation. Renoncer à toute unicité sur `client_event_id` dans `audit_event` (l'idempotence est portée par `idempotency_record`). Recherche par identifiant : sonde d'index par partition `(tenant_id, audit_event_id)` ; un UUID v7 permet d'ajouter l'intervalle de temps pour élaguer les partitions.

---

## 2. Majeurs

### DB-09 — Contrainte d'exclusion des affectations
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §11 ; `MODELE_CONCEPTUEL.md` §4.3 ; `REGLES_METIER.md` RM-032, RM-033, RM-040 ; `USER_STORIES.md` US-1.22 R3/R4.
- **Constats et corrections** :
  1. `WHERE status IN ('PLANIFIEE','ACTIVE','SUSPENDUE')` exclut `TERMINEE` de la contrainte : deux affectations terminées pourraient se chevaucher, ce qui représenterait deux conducteurs au volant du même engin au même moment dans l'historique. Remplacer par `WHERE status <> 'CANCELLED'` (seule une annulation libère le créneau) et exiger que la clôture **tronque `valid_to` à l'instant réel de fin** (`CHECK status <> 'COMPLETED' OR valid_to IS NOT NULL`). Sinon une affectation terminée tôt mais gardant sa fin planifiée bloquerait la suivante (US-1.23 A7).
  2. Un intervalle `[t, t)` est **vide** : il ne chevauche rien et échappe à la contrainte. Le `CHECK valid_to > valid_from` est donc indispensable (il l'est déjà pour l'affectation ; l'exiger aussi pour `user_role_assignment`).
  3. `tenant_id WITH =` dans l'exclusion est redondant (`vehicle_id` est un UUID global) et alourdit l'index GiST : l'omettre.
  4. Noms de contraintes distincts pour le véhicule et le conducteur (`ex_vehicle_assignment_vehicle`, `ex_vehicle_assignment_driver`) : l'API les mappe vers `VEHICLE_ASSIGNMENT_OVERLAP` / `DRIVER_ASSIGNMENT_OVERLAP` à partir du SQLSTATE `23P01` et du nom de contrainte.
  5. Les affectations `COMPLETED`/`CANCELLED` sont immuables (RM-040) : trigger de garde ; `vehicle_id`, `driver_id`, `site_id` jamais modifiables après création.

### DB-10 — Exclusion des habilitations
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §10 (« contrainte d'exclusion `daterange` ») ; `USER_STORIES.md` US-1.19 A4.
- **Constat** : l'exclusion sur `(driver, qualification_type, vehicle_category_id, site_id)` est sans effet quand `site_id` ou `vehicle_category_id` est NULL (NULL = NULL n'est pas vrai en GiST). Les cas les plus courants (habilitation valable tout le tenant, `site_id` NULL) ne seraient pas protégés.
- **Correction** : utiliser `COALESCE(site_id, '00000000-0000-0000-0000-000000000000')` (idem catégorie) dans l'exclusion, `daterange(valid_from, valid_to, '[]')`, `WHERE status = 'VALID'`. Conséquence métier à documenter : un renouvellement anticipé ne peut pas chevaucher l'ancienne ligne ; la procédure est de raccourcir `valid_to` de l'ancienne dans la même transaction (tracé en audit).

### DB-11 — Permis : unicité et statut
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §9 ; `USER_STORIES.md` US-1.18 A1, A4, A5 ; `REGLES_METIER.md` RM-024.
- **Constat** : `UNIQUE (tenant_id, driver_id, license_number, category_code)` empêche de conserver l'historique d'un renouvellement quand le numéro est conservé (US-1.18 A5 le veut). Par ailleurs `status = VALIDE` stocké peut rester vrai alors que la date est dépassée : le nom induit en erreur.
- **Correction** : unicité sur `(tenant_id, driver_id, license_number, category_code, issue_date)`. Statut stocké = statut **administratif** (`VALID | SUSPENDED | WITHDRAWN`) ; l'état d'expiration est calculé (vue `driver_license_state` ou API) avec le seuil `EXPIRING` configurable par tenant (Q21). Index `(tenant_id, expiry_date)` pour US-1.20 (DB-29).

### DB-12 — `vehicle_category` : permis requis et portée
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §6 (`required_license_category_codes text[]`) ; `PRD_MVP.md` A7, Q2, E2 ; `USER_STORIES.md` US-1.11 A2.
- **Constats** : (1) une FK ne peut pas porter sur les éléments d'un tableau : « éléments dans `license_category_ref.code` » n'est pas garanti par la base. Remplacer par une table de jonction `vehicle_category_license_category (tenant_id, vehicle_category_id, license_category_code)` avec FK composite et FK vers le référentiel. (2) Q2 (global, tenant, mixte) : le dictionnaire a déjà tranché « copie par tenant ». **Confirmer** cette option : elle est la seule compatible avec les FK composites H3 et avec des drapeaux propres au tenant (`requires_driver`, `has_hour_meter`). Ajouter `is_system boolean` (le code d'une catégorie système n'est ni modifié ni supprimé) ; le jeu initial est une constante versionnée du code, copiée dans la transaction de création du tenant. Coût : une évolution des catégories système exige une migration de données sur tous les tenants (acceptable). (3) Retirer `archived_at` au profit de `is_active` (DB-23).

### DB-13 — Référentiel `role`
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §4, §5 ; `MATRICE_RBAC.md` §4.2.
- **Constats** : `CHECK` « parmi les 14 codes » sur la clé primaire est redondant avec la clé étrangère et force une migration à chaque nouveau rôle (la même migration ajoute de toute façon la ligne). `allowed_scopes text[]` et « scope ∈ allowed_scopes (applicatif + trigger) » : même limite que DB-12.
- **Correction** : table `role_allowed_scope (role_code, scope_type)` et FK composite `(role_code, scope_type)` depuis `user_role_assignment` : aucune trigger. Combinée à DB-04, aucun tenant client ne peut détenir un rôle de portée `PLATFORM`. Trancher les portées de `DRIVER` (le dictionnaire hésite entre `{TENANT,SITE}` et `{SITE}`) : recommandation `{SITE}`, le conducteur n'agissant que sur ses propres objets (RBAC §4.3).

### DB-14 — `driver` vs `person`
- **Fichiers** : `MODELE_CONCEPTUEL.md` §2 (risque de modélisation) ; `REGLES_METIER.md` §11 point 14 ; `DICTIONNAIRE_DONNEES.md` §8 ; `MATRICE_RBAC.md` §2.4.
- **Analyse** : `driver` mêle des attributs de **personne/salarié** (matricule, nom, téléphone, emploi, entrée/sortie) et de **conduite** (statut de conduite, permis, habilitations, affectations). Les mécaniciens arrivent au lot 3, les magasiniers après le MVP ; rien ne dit qu'ils partagent le dossier du conducteur. Séparer maintenant ajoute une table, une jointure et de nombreuses retouches de documents (RBAC, US) sans besoin établi (CLAUDE.md : pas de module spéculatif).
- **Recommandation** : conserver `driver` au lot 1, **sous réserve** que le client confirme au plus tard avant la migration 0005 que mécaniciens et magasiniers ne sont pas des conducteurs (Q14). Chemin de sortie non destructif prévu : au lot 3, créer `person`, ajouter `driver.person_id` (nullable, rempli puis `NOT NULL`), déplacer les colonnes d'identité par migration réversible. Un renommage de table est une opération de métadonnées bon marché ; le coût réel est dans l'API et les documents. Si la réponse du client est « oui, les mêmes personnes » : introduire `person` dès 0005. **Décision client.**

### DB-15 — `vehicle_meter_reading`
- **Fichiers** : `MODELE_CONCEPTUEL.md` §2 (notes), `DICTIONNAIRE_DONNEES.md` §7, §12 ; `REGLES_METIER.md` RM-060 à RM-069 ; `USER_STORIES.md` (aucune story de compteur au lot 1).
- **Constats** : (1) le dictionnaire place six colonnes de cache (valeur, date, source × 2 compteurs) sur `vehicle` **et** propose la table : deux sources de vérité, que RM-016 reproche justement à `EN_SERVICE`. (2) Aucune story du lot 1 ne saisit un compteur, alors que RM-060 à 069 sont dans le périmètre rédigé. (3) `CORRECTION` figure à la fois dans `source` et dans `kind` : redondant. (4) `correction_of` est une FK simple (DB-18).
- **Décision recommandée** : **adopter la table** (monotonie, idempotence `client_event_id`, corrections tracées et provenance ne se tiennent pas avec une valeur courante) mais la **livrer avec la première story qui saisit un compteur** (checklist, lot 4, ou une story « relevé manuel » ajoutée au lot 1 si le client la veut). Le modèle physique la fournit comme migration optionnelle 0008. **Aucune colonne de compteur sur `vehicle`** : la valeur courante est une vue (`vehicle_current_meter`, dernier relevé accepté non remplacé). Retirer `CORRECTION` des valeurs de `source`. **Décision client** : compteur saisi dès le lot 1 ou non.

### DB-16 — Historique de statut du véhicule
- **Fichiers** : `REGLES_METIER.md` RM-014, RM-017, RM-092 ; `DICTIONNAIRE_DONNEES.md` §7 (`status_changed_at` seul) ; `ADR-005`.
- **Constat** : RM-092 impose de calculer les durées d'immobilisation « à partir des transitions horodatées ». Le modèle ne garde que la dernière date de changement ; reconstruire le reste depuis les JSON `before/after` d'`audit_event` est fragile et couplé à la rétention et à la pseudonymisation de l'audit. Les changements de statut sont manuels dès le lot 1 : les données manquantes à partir du lot 3 seraient irrécupérables.
- **Correction** : table `vehicle_status_history` en ajout seul, alimentée par un trigger sur `vehicle` (pas de dépendance à la discipline applicative), dès le lot 1.

### DB-17 — `site_id` sur `vehicle` et `driver`
- **Fichiers** : `PRD_MVP.md` E5 ; `USER_STORIES.md` (note finale) ; `MODELE_CONCEPTUEL.md` ; `DICTIONNAIRE_DONNEES.md` §7, §8, §11 ; `REGLES_METIER.md` RM-042, RM-051, RM-052 ; `ADR-002` §3.3.
- **Constats et corrections** :
  1. **Confirmer** `vehicle.site_id` (obligatoire) et le site de rattachement du conducteur (obligatoire) : nécessaires à la portée `SITE` (H7), à RM-042, à US-1.12/1.16.
  2. **Nommage** : le dictionnaire nomme `driver.home_site_id` alors que le reste du modèle et ADR-002 §3.3 (« les tables dépendantes d'un site portent `site_id` ; le repository ajoute `site_id IN (:sites)` ») reposent sur une colonne uniforme. Renommer `driver.home_site_id` en `driver.site_id` (sémantique documentée : site de rattachement) ; sinon le filtre de portée générique, les tests générés (ST-02) et les helpers SQL ont une exception.
  3. **Cohérence de l'affectation** : `vehicle_assignment.site_id = vehicle.site_id` à la création (dictionnaire §11) est annoncé « trigger/applicatif ». Une FK `(tenant_id, vehicle_id, site_id)` serait fausse : elle bloquerait tout transfert de site tant qu'il existe de l'historique. Utiliser un trigger `BEFORE INSERT` simple (égalité de site seulement ; la règle conducteur/véhicule même site, assouplie par Q1, reste applicative).
  4. **Historique de transfert** (RM-051/052) : le site figé dans l'affectation et l'audit suffisent au lot 1. Si des rapports « parc par site à la date T » sont requis, `vehicle_status_history` ne couvre pas le site : prévoir une table `vehicle_site_history` au lot 2/6 (non créée maintenant).

### DB-18 — Clés étrangères composites incomplètes
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §0 (colonnes communes), §5 (`granted_by`, `revoked_by`), §9 (`verified_by`), §11 (`approved_by`), §12 (`correction_of`), §13 (`actor_user_id`) ; `MENACES_ET_CONTROLES.md` ST-04.
- **Constat** : les colonnes d'auteur sont des FK « simples » ou non typées. Une FK composite `(tenant_id, auteur)` est **fausse** quand l'auteur est un compte plateforme agissant dans un tenant (création du premier `TENANT_ADMIN`, session de support, événement d'audit). `correction_of` doit rester sur le même véhicule. ST-04 affirme « toute FK entre tables portant `tenant_id` inclut `tenant_id` » : fausse sans liste d'exceptions.
- **Règle proposée** : (a) `created_by` / `updated_by` : `uuid` sans FK (traçabilité = audit ; pas de verrou de FK sur chaque écriture) ; (b) `granted_by`, `revoked_by`, `approved_by`, `verified_by`, `actor_user_id` : FK **simple** vers `user_account(user_account_id)` (UUID global) ; (c) toutes les autres références entre tables métier : FK composite ; (d) `correction_of` : FK composite `(tenant_id, vehicle_id, correction_of)` vers `vehicle_meter_reading` ; (e) ST-04 liste explicitement les colonnes d'exception de (b). Toutes les FK portent `ON DELETE RESTRICT` explicite. Note : les vérifications d'intégrité référentielle ne sont pas soumises à la RLS ; une FK composite fonctionne donc entre tables sous RLS.

### DB-19 — Schémas d'`audit_event` divergents
- **Fichiers** : `ADR-005` §3.1 ; `DICTIONNAIRE_DONNEES.md` §13 ; `MATRICE_RBAC.md` §5 note 15 ; `MENACES_ET_CONTROLES.md` C-16, C-18, T-46.
- **Constat** : `id` vs `audit_event_id` ; `actor_kind` (valeurs minuscules, 4 valeurs dont `device_sync`) vs `actor_type` (majuscules, 3 valeurs) ; `outcome`, `reason` seulement au dictionnaire ; `user_agent`, `client_event_id` seulement à l'ADR ; `support_session_id` exigé par RBAC §4.1 et C-18 mais absent des deux ; `before`/`after`/`before_data`/`after_data`/`changes` ; le dictionnaire dit « champs sensibles masqués » alors que RBAC et T-46 disent « marqueur de champ modifié, jamais la valeur ». Actions : `auth.login.failed` vs `auth.login_failed`.
- **Correction** : un schéma unique (`MODELE_PHYSIQUE_LOT1.md` §5.4) : `audit_event_id`, `actor_kind ∈ USER | SYSTEM | PLATFORM_SUPPORT | DEVICE_SYNC | ANONYMOUS` (anonyme pour une connexion échouée d'un compte inconnu), `support_session_id`, `outcome ∈ SUCCESS | DENIED | FAILURE`, `reason`, `changed_fields text[]` (noms de champs, y compris sensibles), `before_data` / `after_data` **sans aucun champ sensible**. Convention d'action `<entité>.<verbe>` en `snake_case` avec point (`auth.login_failed`), validée par `CHECK` sur le motif, liste fermée côté application (test), pas côté base.

### DB-20 — Chaîne de hachage
- **Fichiers** : `ADR-005` §3.2 point 4 (« éventuel », « à activer si le client l'exige ») ; `MENACES_ET_CONTROLES.md` C-16, ST-72 (au plan du lot 1) ; `MATRICE_RBAC.md` §2.6 (`audit.integrity.verify`).
- **Constat** : incohérence de statut (optionnelle vs exigée au lot 1). Techniquement, une chaîne par tenant calculée **dans la transaction métier** exige un verrou consultatif par tenant tenu jusqu'au COMMIT : chaque écriture métier d'un tenant est sérialisée derrière l'audit, ce qui dégrade le débit et augmente le risque d'interblocage. De plus `now()` est l'heure de début de transaction, pas l'ordre de validation ; un ordre fiable exige le verrou.
- **Recommandation** : au lot 1, **ne pas chaîner en ligne**. Défense du lot 1 : droits sans `UPDATE/DELETE/TRUNCATE`, trigger, RLS, partitions inaccessibles. Colonnes `prev_hash` / `row_hash` conservées, nullables. Intégrité cryptographique par **scellement asynchrone** (table `audit_seal`, lot 1.x) : tâche hors chemin d'écriture hachant par lots ordonnés par une séquence, avec ancrage externe périodique. Requalifier ST-72 et `audit.integrity.verify` en « lot 1.x ». Si le client exige la chaîne en ligne au lot 1, accepter et mesurer la sérialisation (aucune mesure disponible à ce stade). **Décision client.**

### DB-21 — Accès support `PLATFORM_ADMIN`
- **Fichiers** : `MATRICE_RBAC.md` §2.2 (`support_access.*`), §4.1 ; `MENACES_ET_CONTROLES.md` ST-28, T-12 (lot L1) ; `PRD_MVP.md` Q5 ; `USER_STORIES.md` Q26 (« Non au lot 1 »), US-1.01 A5 ; `ADR-002` §3.4.
- **Constat** : RBAC et menaces planifient des sessions de support au lot 1 ; PRD/US les excluent. La table `support_access_session` en dépend.
- **Recommandation** : **pas d'accès support au lot 1** (le plus sûr : aucun chemin du `PLATFORM_ADMIN` vers les données métier). Les politiques RLS n'ont alors pas de cas particulier à tester. La table est spécifiée dans `MODELE_PHYSIQUE_LOT1.md` §11 pour ne pas bloquer la suite. Requalifier ST-28 en lot 1.x. **Décision client.**

### DB-22 — Minimisation des données du conducteur
- **Fichiers** : `PRD_MVP.md` §8 (« pas de date de naissance, adresse, photo au lot 1 ») ; `DICTIONNAIRE_DONNEES.md` §8 (`date_of_birth`), §10 (`APTITUDE_MEDICALE`), §8 (`unavailability_reason = ARRET_MALADIE`) ; `REGLES_METIER.md` RM-025, RM-028 ; `MATRICE_RBAC.md` §5 (`driver.address`, pièce d'identité, « aptitude médicale non collectée au lot 1 »).
- **Constat** : trois contradictions touchant des données potentiellement soumises à un régime particulier. Le PRD exclut la date de naissance, le dictionnaire la prévoit (facultative). RBAC dit l'aptitude médicale non collectée ; le dictionnaire et RM-025 la modélisent (« apte jusqu'à »). Le motif `ARRET_MALADIE` révèle un état de santé, classé « sensible » mais visible comme motif.
- **Correction** : le modèle physique du lot 1 **ne contient pas** `date_of_birth`, ni le type `APTITUDE_MEDICALE`, ni `ARRET_MALADIE` (motifs : `LEAVE | TRAINING | OTHER`). Leur ajout est une migration ultérieure conditionnée à l'avis du juriste guinéen (RM-025, CLAUDE.md). RM-030 (e) et la contrainte d'âge disparaissent du lot 1. Les colonnes `driver.address`, `notes_hr`, pièce d'identité citées par RBAC §5 n'existent pas au lot 1 (cohérent avec RM-028) : le préciser dans RBAC.

### DB-23 — Suppression logique, archivage, anonymisation
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §0 (`archived_at` commun) ; `REGLES_METIER.md` RM-006, RM-010 ; `USER_STORIES.md` CT-6, US-1.15 ; `MENACES_ET_CONTROLES.md` C-26, C-27.
- **Constat** : `archived_at` est une colonne commune, mais presque toutes les entités ont déjà un état terminal (`RETIRED`, `INACTIVE`, `DISABLED`, `ARCHIVED`, `INACTIVE`, `CANCELLED`). Deux sources pour « archivé » (statut + date) divergent forcément. Ensuite, le droit d'effacement (C-27) exige une anonymisation, mais les colonnes d'identité sont `NOT NULL` et l'audit est en ajout seul.
- **Correction** : (1) retirer `archived_at` des colonnes communes ; l'état terminal est le statut (US-1.15 « archiver » = `RETIRED`) ; les référentiels sans machine d'états utilisent `is_active`. (2) Les unicités sont **totales** (non partielles) : un numéro de parc n'est jamais réutilisé (RM-010, réponse à PRD Q12 sur le numéro de parc ; l'immatriculation suit la même règle par défaut, à confirmer). (3) `anonymized_at` sur `driver` et `user_account` ; l'anonymisation remplace les valeurs par un marqueur et efface téléphone/e-mail ; l'audit ne contient que des identifiants (aucune identité à pseudonymiser). (4) `mf_app` n'a **aucun `DELETE`** sur les tables métier (exceptions : tables éphémères, DB-42).

### DB-24 — Concurrence optimiste
- **Fichiers** : `DICTIONNAIRE_DONNEES.md` §0 (`row_version`) ; `USER_STORIES.md` CT-4 ; `PRD_MVP.md` §8 ; `INTEGRATION_GPS_OFFLINE.md` §2.3 (`If-Match`/ETag).
- **Constat** : « incrémenté à chaque mise à jour » sans dire par qui. Si c'est l'application, un `UPDATE` en masse (tâche RM-031, suspension d'affectations par RM-038) ou un oubli contourne le contrôle.
- **Correction** : un trigger `BEFORE UPDATE` fixe `updated_at = now()` et `row_version = OLD.row_version + 1` sur toute table portant ces colonnes ; SQLAlchemy utilise `version_id_col` avec `version_id_generator=False` et `eager_defaults` (compteur géré côté serveur) ; l'API expose l'ETag faible `W/"<row_version>"` et attend `If-Match`. Les tables d'ajout seul (audit, historiques, relevés) n'ont ni `row_version` ni `updated_at`. Un `UPDATE ... WHERE row_version = :v` affectant 0 ligne → 409.

### DB-25 — Partitions : accès direct
- **Fichiers** : `ADR-005` §3.2 ; `ADR-002` §3.2 ; `MENACES_ET_CONTROLES.md` ST-71.
- **Constat** : les privilèges et les politiques RLS du parent ne s'appliquent pas à un accès direct à une partition ; une partition créée plus tard peut hériter de droits par défaut ou d'une RLS non activée et exposer toutes les lignes (tous tenants) à `mf_app`.
- **Correction** : aucun `ALTER DEFAULT PRIVILEGES` accordant des droits à `mf_app` ; chaque partition (dont `DEFAULT`) est créée par une fonction unique qui active et force la RLS et révoque tout droit à `PUBLIC` et `mf_app` ; test : `mf_app` ne peut pas lire une partition directement ; test d'introspection sur toutes les partitions.

### DB-26 — `FORCE ROW LEVEL SECURITY` et `mf_owner`
- **Fichiers** : `ADR-002` §3.2, §4 (« jobs cross-tenant avec `mf_owner` ») ; `MENACES_ET_CONTROLES.md` C-35.
- **Constat** : avec `FORCE`, le propriétaire est soumis aux politiques ; sans politique applicable, il voit 0 ligne. Les migrations de données, la création de la ligne du tenant plateforme et les fixtures de test échouent ou sont silencieusement vides. L'ADR suppose l'inverse.
- **Correction** : (a) les politiques ne ciblent que `mf_app` ; `mf_owner` ne lit ni n'écrit les lignes métier par défaut (fail-closed) ; (b) une migration qui amorce des lignes les insère **avant** d'activer `FORCE`, ou bascule `NO FORCE`/`FORCE` dans la même transaction DDL ; (c) les corrections de données transverses se font tenant par tenant en posant le contexte, ou par un rôle d'exploitation nominatif temporaire `BYPASSRLS` accordé avec approbation (CLAUDE.md) ; (d) les fixtures de test passent par `mf_app` avec contexte ; le test « le trigger bloque aussi un super-utilisateur » utilise la connexion super-utilisateur du conteneur de CI.

### DB-27 — Extensions et bootstrap
- **Fichiers** : `ADR-004` §2 ; `ADR-002` §3.2 (création des rôles par script `infra/`) ; `DICTIONNAIRE_DONNEES.md` §3 (`citext`), §11 (`btree_gist`).
- **Constats** : `postgis` n'est pas une extension « trusted » : `CREATE EXTENSION` exige un super-utilisateur et **ne peut pas** être exécuté par Alembic sous `mf_owner`. `btree_gist` et `citext` sont installables sans super-utilisateur à partir de PostgreSQL 13 mais seront créées au même endroit pour cohérence. `citext` est utilisée par le dictionnaire mais absente de toute liste d'extensions. `pgcrypto` n'est pas nécessaire : `gen_random_uuid()` et `sha256()` sont natifs en PostgreSQL 16, et les hachages de mots de passe et jetons sont calculés par l'application.
- **Correction** : un script de bootstrap (`infra/db/`, hors Alembic, exécuté par un super-utilisateur) crée rôles, base, extensions `postgis`, `btree_gist`, `citext`, schéma `app`. La migration 0001 **vérifie** la présence des extensions et échoue avec un message clair. Aucun `DROP EXTENSION` dans un `downgrade`. Ne pas installer `pgcrypto`.

### DB-28 — Documents réglementaires du véhicule
- **Fichiers** : `REGLES_METIER.md` RM-019, §11 point 9 ; `DICTIONNAIRE_DONNEES.md` §15 ; skill `fleet-management` (« eligibility rules for licence/inspection ») ; `USER_STORIES.md` US-1.22.
- **Constat** : la skill de domaine cite l'inspection comme règle d'éligibilité ; le modèle l'écarte sans décision. Risque : affecter un engin sans visite valide.
- **Recommandation** : **ne pas créer la table au lot 1** (documents bloquants inconnus du client, RM-019 : « à valider »), mais figer son modèle pour que le service d'éligibilité reste extensible : `vehicle_document` (type, référence, `valid_from`, `valid_to`, statut ; esquisse en `MODELE_PHYSIQUE_LOT1.md` §11). L'éligibilité véhicule du lot 1 se limite au statut. Consigner dans le PRD que l'affectation d'un véhicule sans contrôle documentaire est un risque accepté tant que la décision n'est pas prise. **Décision client.**

---

## 3. Mineurs

- **DB-29 — Index.** Dictionnaire §14 incomplet : (a) US-1.20 liste toutes les échéances du tenant → index `driver_license(tenant_id, expiry_date)` (le dictionnaire n'a que `(tenant_id, driver_id, expiry_date)`), idem `driver_qualification(tenant_id, valid_to)` ; (b) historique d'affectation : `(tenant_id, vehicle_id, valid_from DESC)` et `(tenant_id, driver_id, valid_from DESC)` ; l'index GiST de l'exclusion sert « qui conduisait à l'instant t » ; (c) audit : ajouter `(tenant_id, actor_user_id, occurred_at DESC)` et `(tenant_id, site_id, occurred_at DESC)` (US-1.26 A5, portée site) ; (d) index sur les colonnes enfant des FK composites usuelles ; (e) pagination à clé stable `(tenant_id, …, id)` (US-1.24 A6). La recherche par sous-chaîne d'immatriculation n'est pas spécifiée : n'ajouter `pg_trgm` qu'à la demande.
- **DB-30 — Normalisation.** Le dictionnaire normalise l'immatriculation en « majuscules sans espaces », les US en « casse, espaces, tirets » (US-1.12 A2). Retenir les trois (casse, espaces, tirets), via colonnes générées stockées `fleet_number_norm`, `registration_norm` (plus stables sous Alembic que des index d'expression) ; interdire la chaîne vide après normalisation. Le numéro de série n'est pas unique entre constructeurs : unicité sur `(tenant, constructeur normalisé, série normalisée)` pour éviter de faux conflits.
- **DB-31 — CHECK non déterministes.** « âge ≥ 18 ans à la création », « `issue_date` ≤ date du jour », « année ≤ année courante + 1 » reposent sur `now()` : à ne pas mettre en `CHECK` (la restauration revalide les données avec une autre date). Les contrôles dynamiques sont applicatifs ; en base, bornes statiques (année entre 1950 et 2100).
- **DB-32 — Types temporels.** Permis et habilitations en `date` (jour inclus, fuseau du site, RM-021) ; affectations en instants `timestamptz` `[)` (PRD §8) : mélange voulu, à documenter. Fixer `ALTER ROLE mf_app SET timezone = 'UTC'`. `site.timezone` : le `CHECK` ne peut valider un nom IANA qu'en syntaxe ; la validité est applicative (zoneinfo). `audit_event.occurred_at` : `clock_timestamp()` (ordre intra-transaction) plutôt que `now()`. Colonne générée `valid_during tstzrange` conservée (requêtes « à l'instant t ») ; vérifier à l'exécution que le constructeur de plage est accepté en colonne générée.
- **DB-33 — `user_account`.** `VERROUILLE` stocké double `locked_until` : état dérivé, retirer du statut. RBAC §5 cite `last_login_ip` et `user_agent` absents du dictionnaire : les porter par `auth_session` (par session) ; `last_login_at` reste sur le compte. RBAC §1.1.7 et C-10 parlent de « version de jeton » alors qu'ADR-003 prévoit `session_id` vérifié en base : retenir `auth_session.revoked_at`, abandonner `token_version`.
- **DB-34 — Nommage.** Clés primaires `<table>_id` partout (le modèle conceptuel a `assignment_id`, `reading_id`, l'ADR-005 `id`). Contraintes toujours nommées : `pk_`, `uq_`, `fk_`, `ck_`, `ix_`, `ex_`, `tg_` (≤ 63 octets, test). Conventions complètes : `MODELE_PHYSIQUE_LOT1.md` §2.
- **DB-35 — ST-04 / ST-05.** Listes blanches à écrire : tables globales (`role`, `role_allowed_scope`, `license_category_ref`, `alembic_version`), tables PostGIS (`spatial_ref_sys`), `tenant` (sa propre racine), partitions d'audit, colonnes d'acteur de DB-18.
- **DB-36 — Alembic.** `alembic check` ne détecte ni RLS, ni fonctions, ni triggers, ni exclusions mal décrites, et verrait les partitions comme des tables inconnues à supprimer. Prévoir `include_object` pour les ignorer, et compenser par les tests d'introspection (DBT-40 et suivants). Les contraintes d'exclusion sont aussi déclarées dans les modèles SQLAlchemy (`ExcludeConstraint`).
- **DB-37 — `tenant`.** Ajouter `kind` (DB-04) et `is_demo` (US-1.30 A1/A3 : « identifiés comme fictifs », chargement interdit en production). US-1.01 A2 exige l'unicité du **nom** insensible à la casse et aux espaces : le dictionnaire n'a que l'unicité du `code` ; ajouter `legal_name_norm` unique.
- **DB-38 — `site.location`.** Un `geography` borne déjà les coordonnées (coercition, parfois silencieuse) : la validation des plages est applicative avant conversion ; garder le contrôle « ni (0,0) ». PostGIS n'est utile qu'au lot 5 : l'extension est requise dès 0001 parce que la colonne existe et parce que ADR-004 impose l'image PostGIS. Pas d'index spatial au lot 1.
- **DB-39 — UUID.** H2 « v7 si disponible » : Python 3.12 n'a pas d'UUID v7 en bibliothèque standard ; une dépendance serait nécessaire. Recommandation : v7 pour `audit_event` (élagage de partitions, localité d'index), v4 acceptable ailleurs ; trancher l'ajout de dépendance (CLAUDE.md). Valeur par défaut SQL `gen_random_uuid()` uniquement pour les scripts d'exploitation.
- **DB-40 — Portée site hors RLS.** ADR-002 §3.3 demandait revalidation. **Confirmé** : un même utilisateur cumule des rôles de portées différentes (US-1.06 A3, union par permission) ; la portée dépend de la permission, pas de l'utilisateur, et ne se réduit pas à un réglage de session unique. Elle reste applicative, testée par ST-02/ST-36.
- **DB-41 — `eligibility_snapshot`.** Marqué « personnel » : se limiter aux identifiants et dates (jamais de numéro de permis ni de motif de suspension), `CHECK jsonb_typeof = 'object'`.
- **DB-42 — Rétention des tables éphémères.** Aucune politique pour `auth_session`, `account_token`, `idempotency_record`. Prévoir une durée de conservation paramétrable (valeurs à fixer, aucune supposée) et un `DELETE` limité à ces tables (seules exceptions à DB-23). `idempotency_record` ne stocke que l'état et la référence de ressource, pas le corps de réponse (données personnelles) ; l'API reconstruit la réponse par lecture.

---

## 4. Décisions à arbitrer par le client (ou le product owner)

| # | Décision | Ma recommandation | Bloque |
|---|----------|-------------------|--------|
| C1 | Identifiant de connexion : espace de travail + e-mail, ou e-mail seul (DB-07) | Espace (code, via URL) + e-mail ; e-mail unique par tenant | Migration identité |
| C2 | Mécaniciens/magasiniers = mêmes personnes que les conducteurs ? (DB-14, Q14) | Garder `driver` au lot 1 ; `person` au lot 3 si non | Migration workforce |
| C3 | Saisie de compteur dès le lot 1 ? (DB-15) | Non ; table à livrer avec la première story de compteur | Migration optionnelle |
| C4 | Documents véhicule bloquant l'affectation (assurance, visite) (DB-28, RM-019) | À définir ; table non créée au lot 1 | Éligibilité véhicule |
| C5 | Aptitude médicale, date de naissance, motif maladie (DB-22) | Exclus du lot 1, avis juriste guinéen | Migration workforce |
| C6 | Accès support `PLATFORM_ADMIN` au lot 1 ? (DB-21) | Non | Tests ST-28 |
| C7 | Chaîne de hachage en ligne ou scellement asynchrone ; ancrage externe (DB-20) | Scellement asynchrone, lot 1.x | ST-72 |
| C8 | Durées de rétention : audit, adresses IP, sessions, jetons, historiques (DB-08, DB-42) | À fixer avec le juriste ; paramètres, pas de valeur supposée | Exploitation |
| C9 | Règle « même site » stricte ou dérogation (Q1) | Applicative ; sans impact sur le schéma | Trigger de site |
| C10 | Immatriculation réutilisable après réforme ? (Q12) | Non (unicité totale) | Contraintes |
| C11 | Portée de `DRIVER` : `SITE` seul (DB-13) | `SITE` | Référentiel `role` |
| C12 | Dépendance UUID v7 (DB-39) | v7 pour l'audit seulement | Outillage |
| C13 | Rétablissement d'un véhicule `RETIRED` et qui l'approuve (Q18, RM-015) | Action exceptionnelle à double contrôle, hors trigger | Machine d'états |

## 5. Ce qui n'a pas été fait

- Aucun SQL n'a été exécuté ni validé syntaxiquement ; plusieurs points reposent sur ma connaissance de PostgreSQL 16 et doivent être confirmés par exécution en CI : constructeur de plage dans une colonne générée, `lower`/`regexp_replace` en colonne générée, `uuid` dans une exclusion `btree_gist`, triggers de ligne `BEFORE` sur table partitionnée, comportement du paramètre personnalisé après la fin de la transaction (DB-03).
- Aucune volumétrie n'est connue (PRD Q9) : aucune recommandation d'index ou de partition ne repose sur une mesure.
- Rien n'a été modifié dans les documents existants ; les corrections proposées sont à reporter par leurs propriétaires.
