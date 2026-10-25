# User stories — MINEFLEET 360 (Lot 1 détaillé, Lots 2-6 haut niveau)

> Statut : **brouillon de cadrage, révisé après la revue croisée** (QA-01..32, DB-01..42). Rien n'est implémenté ni testé.
> Préséance en cas de divergence : `DECISIONS_A_ARBITRER.md` (D-01..D-24, défauts provisoires C-01..C-17) > `MODELE_PHYSIQUE_LOT1.md` > `MATRICE_RBAC.md` > `REGLES_METIER.md` > `DICTIONNAIRE_DONNEES.md` > ce document > `PRD_MVP.md`.
> Rôles, entités et hypothèses H1–H10 : `docs/00_SOCLE_CADRAGE.md`. Contexte produit et lots : `docs/PRD_MVP.md`.
> Priorités : **M** = Must, **S** = Should, **C** = Could.
> Règle de rédaction (QA-15) : **un seul code HTTP et un seul code d'erreur stable par critère d'erreur** (cet oracle unique est testable tel quel). Un critère marqué *(à arbitrer)* est exclu des tests automatiques tant que la décision n'est pas rendue.
> Chaque story Lot 1 indique sa **tranche** (D-21) : **1a** socle, **1b** référentiels (véhicules, conducteurs), **1c** affectations, UI minimale et E2E.

## 0. Conventions transversales du Lot 1

### 0.1 Règles applicables à toutes les stories
- **CT-1 Isolation et codes de refus (D-05, table unique, évaluée dans cet ordre)** :

| Ordre | Situation | HTTP | Code d'erreur |
|-------|-----------|------|---------------|
| 1 | Non authentifié, jeton invalide/expiré/révoqué | 401 | `AUTH_REQUIRED` |
| 2 | L'utilisateur n'a **aucune** attribution de rôle active portant la permission (endpoint de collection ou ressource visible) | 403 | `PERMISSION_DENIED` |
| 3 | Ressource inexistante, d'un autre tenant, **hors portée de site** de l'utilisateur, ou refusée par la règle d'objet « propriétaire » | 404 | `NOT_FOUND` (corps et en-têtes identiques dans tous ces cas) |
| 4 | Identifiant de ressource **dans le corps** inexistant, étranger au tenant ou hors portée | 422 | `REFERENCE_NOT_FOUND` (indiscernable inexistant/étranger) |
| 5 | Validation de format, ou règle métier violée | 422 | `VALIDATION_ERROR` (format) ou code métier stable (ex. `DRIVER_LICENSE_EXPIRED`) |
| 6 | Conflit d'état : chevauchement, unicité, `row_version` obsolète, blocage par ressources ouvertes | 409 | code stable (voir 0.4) |
| 7 | Limitation de débit | 429 | `RATE_LIMITED` |

  Ordre D-05a : le `403` est évalué **avant toute recherche de la ressource** (aucun oracle d'existence) ; une erreur de clé étrangère (`23503`) est traduite en 422 `REFERENCE_NOT_FOUND`. Les `403` sont **audités**. Les `404` sur identifiant d'un autre tenant sont journalisés comme événement de sécurité (log structuré), pas comme événement d'audit du tenant. Tout `tenant_id` fourni par le client (corps, URL, en-tête) est **rejeté 422 `VALIDATION_ERROR`** (schémas stricts), jamais utilisé.
- **CT-2 Audit (D-17)** : toute écriture réussie produit un `audit_event` écrit dans la **même transaction** (qui, rôle, tenant, site, action, type et id de ressource, avant/après sans donnée sensible : marqueur « modifié » pour les champs sensibles, horodatage UTC, identifiant de corrélation). Tout refus `403` produit un événement d'audit de refus. « Exactement un événement » s'entend **par opération métier** identifiée (les flux d'authentification peuvent en produire plusieurs). Pas de chaînage de hash au Lot 1 (D-16).
- **CT-3 Erreurs** : corps normalisé `{code, message_fr, details, request_id}`, messages en français, aucun détail technique ni indice d'existence d'une ressource hors périmètre.
- **CT-4 Concurrence (D-19)** : toute mise à jour exige `If-Match` (ETag dérivé de `row_version`). En-tête absent : **422 `IF_MATCH_REQUIRED`**. Version obsolète : **409 `VERSION_CONFLICT`**, aucune modification.
- **CT-5 Temps (D-23)** : horodatages stockés en UTC ; affichage `Africa/Conakry` par défaut ou fuseau du site. Le code utilise une **horloge injectable** (D-12). Les tests de fuseau utilisent obligatoirement au moins un site à décalage non nul (ex. `Africa/Lagos`, UTC+1), car Conakry est UTC+0.
- **CT-6 Pas de suppression physique** de véhicule, conducteur, affectation, utilisateur, site : désactivation/archivage par statut, historique conservé. Les révocations (attribution de rôle, session) sont des actions `POST …/revoke`, jamais des `DELETE` (D-25). Aucune route `DELETE` métier n'existe ; `mf_app` n'a pas le droit `DELETE` sur les tables métier (D-19).
- **CT-7 Identifiants** : UUID v4 uniquement dans les URL et réponses (D-20) ; les tests ne supposent aucun ordre d'identifiants.
- **CT-8 Données fictives** : tous les exemples et jeux de test sont fictifs (H9).
- **CT-9 Pagination et tri** : toute liste est paginée avec tri stable (clé de départage). Taille par défaut et maximale lues en configuration ; taille > maximum : **422 `VALIDATION_ERROR`**. Un paramètre de filtre inconnu ou invalide : 422 `VALIDATION_ERROR`.
- **CT-10 Autorisation** : la source de vérité est `MATRICE_RBAC.md` puis `authz_matrix.yaml` (créé en 1a, D-09). **Aucune matrice d'autorisation n'est dupliquée dans ce document** ; les stories citent les permissions `module.ressource.action`. Les tests d'autorisation et d'isolation sont générés depuis le YAML ; un test vérifie que toute route déclare une permission.
- **CT-11 Minimisation (D-15)** : pas de date de naissance, d'aptitude médicale, de motif maladie, d'adresse, de pièce d'identité ni de photo au Lot 1. Le téléphone et le numéro de permis sont des données personnelles lisibles par `HR` seulement ; **masquage total** (champ absent de la réponse) pour tous les autres rôles, appliqué par le sérialiseur côté serveur ; un filtre ou tri sur une valeur masquée est refusé (422 `VALIDATION_ERROR`).

### 0.2 Autorisation (renvoi)
Les droits par rôle et par portée sont définis **exclusivement** dans `docs/MATRICE_RBAC.md` (§2 et §5), complétés par les arbitrages D-10 (voir synthèse ci-dessous). L'ancienne matrice de ce document est supprimée (QA-04).

Arbitrages D-10 applicables aux critères : `TENANT_ADMIN` gère comptes, rôles, sites, référentiels mais **ne lit pas** les données personnelles des conducteurs (ni n° de permis, ni téléphone) ; `HR` écrit conducteurs, permis, habilitations ; `HSE` **lit** (écriture des habilitations reportée) ; `DISPATCHER` et `OPS_MANAGER` créent et clôturent les affectations, `DISPATCHER` uniquement avec une attribution de portée `SITE` (une attribution `TENANT` ne lui confère pas la permission) ; le journal d'audit est lisible par `TENANT_ADMIN` et `AUDITOR` ; `PLATFORM_ADMIN` n'a aucun accès aux données métier ; `FINANCE` n'a pas la lecture des affectations au lot 1 et `DRIVER` n'a aucune permission métier au lot 1 — il est attribuable mais ne porte que les permissions « propre compte » (D-25) ; `AUDITOR` est retenu (rôle optionnel, lecture seule).
`MATRICE_RBAC.md` a été réalignée sur D-10/D-25 ; en cas de doute sur une cellule, la matrice (puis `authz_matrix.yaml`) fait foi.

### 0.3 États (D-01 à D-04 ; codes anglais, libellés français dans l'UI)
| Entité | Codes stockés | Libellés FR (UI) |
|--------|---------------|------------------|
| `tenant.status` | `ACTIVE`, `SUSPENDED` (`ARCHIVED` réservé, hors story) | Actif, Suspendu |
| `user_account.status` | `INVITED`, `ACTIVE`, `DISABLED` | Invité, Actif, Désactivé |
| `site.status` | `ACTIVE`, `INACTIVE` | Actif, Inactif |
| `vehicle.status` (D-02) | `AVAILABLE`, `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED` (terminal) | Disponible, En maintenance, Immobilisé, Hors service, Réformé |
| `driver.status` (D-03) | `ACTIVE`, `UNAVAILABLE`, `SUSPENDED`, `INACTIVE` | Actif, Indisponible, Suspendu, Inactif |
| `driver_license.status` (stocké) | `VALID`, `SUSPENDED`, `WITHDRAWN` | Valide, Suspendu, Retiré |
| `driver_qualification.status` (stocké) | `VALID`, `SUSPENDED`, `REVOKED` | Valide, Suspendue, Révoquée |
| `vehicle_assignment.status` (D-04) | `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED` | Planifiée, Active, Suspendue, Terminée, Annulée |

Dérivés, **jamais stockés** : « en exploitation » d'un véhicule (affectation active) ; validité d'un permis/habilitation (`VALID`, `EXPIRING`, `EXPIRED` calculée depuis les dates, la date du jour au fuseau du site, et le statut stocké qui prime) ; conformité d'une affectation (`COMPLIANT` / `NON_COMPLIANT` + motifs, D-12). `EXPIRING` est **éligible avec avertissement**. Validité d'une date d'expiration : valable jusqu'à la fin de la journée d'expiration au fuseau du site (l'instant limite exclusif est le début du jour suivant, heure locale du site).
Passage `PLANNED` → `ACTIVE` (D-27) : **action explicite** de prise de poste qui revérifie l'éligibilité à la date courante (refus `422 ASSIGNMENT_NOT_ELIGIBLE` avec `reasons[]`) ; `ACTIVE` → `COMPLETED` par clôture explicite. Indicateurs **dérivés** « activation en retard » / « fin dépassée » calculés avec l'horloge injectée. Stories **US-1.33** (activer une affectation) et **US-1.34** (suspendre/reprendre) à détailler au début de la tranche 1c.
Au Lot 1, la transition automatique vers `SUSPENDED` n'existe pas (planificateur au lot 2+, D-12) : `SUSPENDED` n'est atteint que par **action manuelle motivée et auditée** (D-30, US-1.34) ; il reste pris en compte dans les contraintes de chevauchement et bloque les changements de site.

### 0.4 Catalogue des codes d'erreur métier cités (à reporter dans le catalogue unique `backend/app/core/errors.py` + OpenAPI, créé en 1a — D-26 ; tout code absent du catalogue est supprimé)
- 401 : `AUTH_REQUIRED`, `INVALID_CREDENTIALS` (connexion).
- 403 : `PERMISSION_DENIED`.
- 404 : `NOT_FOUND`.
- 409 : `VERSION_CONFLICT`, `DUPLICATE_WORKSPACE_CODE`, `DUPLICATE_TENANT_NAME`, `DUPLICATE_SITE_CODE`, `DUPLICATE_EMAIL`, `DUPLICATE_ROLE_ASSIGNMENT`, `DUPLICATE_REGISTRATION`, `DUPLICATE_FLEET_NUMBER`, `DUPLICATE_EMPLOYEE_NUMBER`, `DUPLICATE_LICENSE`, `DUPLICATE_QUALIFICATION`, `LAST_TENANT_ADMIN`, `OPEN_ASSIGNMENTS_EXIST` (avec liste des affectations), `SITE_HAS_ACTIVE_RESOURCES` (avec liste), `ASSIGNMENT_STATE_INVALID`, `VEHICLE_ASSIGNMENT_OVERLAP`, `DRIVER_ASSIGNMENT_OVERLAP`.
- 422 : `VALIDATION_ERROR`, `SELF_ROLE_CHANGE_FORBIDDEN`, `IF_MATCH_REQUIRED`, `REFERENCE_NOT_FOUND`, `ROLE_NOT_ASSIGNABLE`, `SCOPE_NOT_ALLOWED_FOR_ROLE`, `VEHICLE_STATUS_TRANSITION_INVALID`, `STATUS_REASON_REQUIRED`, `ASSIGNMENT_SITE_MISMATCH`, `DRIVER_NOT_ACTIVE`, `VEHICLE_NOT_AVAILABLE`, `ASSIGNMENT_BACKDATED`, `DRIVER_NOT_QUALIFIED` (avec `reasons[]` : `LICENSE_MISSING`, `LICENSE_EXPIRED`, `LICENSE_CATEGORY_INSUFFICIENT`, `LICENSE_EXPIRES_BEFORE_END`, `QUALIFICATION_MISSING`, `QUALIFICATION_EXPIRED`), `END_BEFORE_START`, `END_IN_FUTURE`, `PASSWORD_POLICY_VIOLATION`, `TOKEN_INVALID`.
- 429 : `RATE_LIMITED`.

Ordre d'évaluation de la création d'affectation (premier échec renvoyé, sauf `DRIVER_NOT_QUALIFIED` qui liste tous ses motifs) : format → `REFERENCE_NOT_FOUND` → `ASSIGNMENT_SITE_MISMATCH` → `DRIVER_NOT_ACTIVE` → `VEHICLE_NOT_AVAILABLE` → `ASSIGNMENT_BACKDATED` → `END_BEFORE_START` → `DRIVER_NOT_QUALIFIED` → `VEHICLE_ASSIGNMENT_OVERLAP` → `DRIVER_ASSIGNMENT_OVERLAP`.

### 0.5 Paramètres de configuration (les tests lisent la configuration, jamais un nombre en dur — QA-14)
`LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_DURATION`, `INVITATION_TTL`, `RESET_TOKEN_TTL`, `PASSWORD_POLICY` (longueur minimale, etc.), `EXPIRY_WARNING_DAYS` (par tenant), `ASSIGNMENT_BACKDATE_TOLERANCE` (D-13), `ASSIGNMENT_END_FUTURE_TOLERANCE`, `CLOCK_SKEW_TOLERANCE`, `PAGE_SIZE_DEFAULT`, `PAGE_SIZE_MAX`, `BLOCKING_LIST_MAX`. Valeurs par défaut de démonstration à arbitrer (Q21, Q22) ; elles ne sont pas inventées ici.

### 0.6 Hors Lot 1 (D-14, D-16) — aucune route ni écran « par défaut »
Exports (véhicules, conducteurs, affectations, audit), accès support plateforme, liaison compte utilisateur ↔ conducteur et écran conducteur (`DRIVER` sans accès au Lot 1), compteurs kilométriques/horaires, documents réglementaires de véhicule (assurance, visite technique), chaînage de hash de l'audit, `person` générique, dérogation d'éligibilité, dérogation de site, antidatage au-delà de la tolérance, job de conformité/suspension automatique, **idempotence (`Idempotency-Key`) reportée au lot 4**, import CSV (C-16), gestion (création/modification) des catégories par le tenant, lecture du journal par `DIRECTION`.

---

## 1. Lot 1 — stories détaillées

### Thème A — Tenant, sites, amorçage

#### US-1.01 — Créer un tenant (M) — tranche 1a
Permission : `organization.tenant.create` (`PLATFORM_ADMIN` seul).
En tant que `PLATFORM_ADMIN`, je veux créer un tenant avec son code d'espace de travail et son premier `TENANT_ADMIN`, afin d'ouvrir un espace client isolé.
- **A1** Given je suis `PLATFORM_ADMIN` connecté, When je crée un tenant avec nom valide, code d'espace valide (`^[a-z0-9-]{3,32}$`) et e-mail du premier administrateur, Then 201 : tenant `ACTIVE`, UUID, **copie par tenant** des catégories de véhicule et de permis du catalogue de référence (D-18, valeurs marquées « à valider localement », C-07), une invitation `TENANT_ADMIN` de portée `TENANT` émise, un `audit_event` écrit, le tout dans une seule transaction.
- **A2** Given un tenant de même nom (insensible à la casse et aux espaces) existe, When je crée, Then 409 `DUPLICATE_TENANT_NAME`, aucune création.
- **A3** Given le code d'espace existe déjà (ou est le code réservé du tenant plateforme), When je crée, Then 409 `DUPLICATE_WORKSPACE_CODE`, aucune création.
- **A4** Given des champs obligatoires manquants, un e-mail invalide ou un code d'espace hors format, When je soumets, Then 422 `VALIDATION_ERROR` avec erreurs par champ, aucune création.
- **A5** Given je suis un utilisateur non `PLATFORM_ADMIN` (ex. `TENANT_ADMIN`), When j'appelle la création, Then 403 `PERMISSION_DENIED` et un événement de refus est audité.
- **A6** Given je suis `PLATFORM_ADMIN`, When j'appelle un endpoint de lecture métier d'un tenant (véhicules, conducteurs, affectations), Then 403 `PERMISSION_DENIED` (aucun accès métier, D-10 ; support reporté, C-10/D-16).
- **A7** Given une erreur après écriture partielle, Then aucune donnée partielle ne subsiste (transaction atomique).

#### US-1.32 — Amorcer la plateforme : premier `PLATFORM_ADMIN` (M) — tranche 1a *(nouvelle, QA-18)*
En tant qu'opérateur de la plateforme, je veux créer le premier `PLATFORM_ADMIN` par une commande d'exploitation, afin de pouvoir créer des tenants sans compte pré-existant.
- **A1** Given le tenant plateforme réservé (D-07) existe après migration, When j'exécute la commande CLI de création du premier `PLATFORM_ADMIN` avec l'e-mail en argument et le secret initial fourni par variable d'environnement, Then le compte est créé dans le tenant plateforme et un événement d'audit est écrit ; aucun secret n'est présent dans le code, les logs ni l'audit.
- **A2** Given un `PLATFORM_ADMIN` existe déjà, When je relance la commande, Then elle est refusée avec un message explicite et un code de sortie non nul (une promotion ultérieure suit la règle de double validation de `MATRICE_RBAC.md` §2.2 note 4, hors Lot 1 sauf arbitrage).
- **A3** Given la commande s'exécute, Then elle utilise le rôle applicatif (`mf_app`), jamais le propriétaire du schéma (`mf_owner`).
- **A4** Given l'API tenant, Then aucune route ne permet de créer ou de promouvoir un `PLATFORM_ADMIN` : tentative d'attribution du rôle par un tenant → voir US-1.06 A4.

#### US-1.02 — Suspendre / réactiver un tenant (S) — tranche 1a
Permission : `organization.tenant.suspend` (`PLATFORM_ADMIN` seul).
En tant que `PLATFORM_ADMIN`, je veux suspendre un tenant, afin de bloquer l'accès en cas d'impayé ou d'incident, sans supprimer ses données.
- **A1** Given un tenant `ACTIVE`, When je le suspends avec un motif, Then le tenant passe `SUSPENDED`, **toutes les sessions de ses utilisateurs sont révoquées** (tout appel avec un jeton antérieur : 401 `AUTH_REQUIRED`), les données sont conservées, un `audit_event` est écrit.
- **A2** Given un tenant `SUSPENDED`, When un de ses utilisateurs tente de se connecter, Then 401 `INVALID_CREDENTIALS` (réponse identique à un mauvais mot de passe) et l'événement est audité.
- **A3** Given je suis `TENANT_ADMIN`, When j'appelle la suspension, Then 403 `PERMISSION_DENIED`.
- **A4** Given je réactive le tenant, Then les utilisateurs `ACTIVE` peuvent se reconnecter ; événement audité.
- **A5** Given le tenant plateforme réservé, When j'essaie de le suspendre, Then 422 `VALIDATION_ERROR` *(garde-fou proposé)*.

#### US-1.03 — Gérer les sites (M) — tranche 1a
Permissions : `organization.site.create/update/deactivate` (`TENANT_ADMIN` seul) ; `organization.site.read` selon la matrice.
En tant que `TENANT_ADMIN`, je veux créer, modifier et désactiver des sites, afin de refléter l'organisation physique et de borner les droits.
- **A1** Given je suis `TENANT_ADMIN` du tenant T1, When je crée un site avec nom et code uniques dans T1 et un fuseau IANA valide (défaut `Africa/Conakry`), Then 201, UUID, audité.
- **A2** Given un site de code identique existe dans T1, When je crée, Then 409 `DUPLICATE_SITE_CODE`. Given le même code existe dans T2, Then la création dans T1 réussit.
- **A3** Given un fuseau IANA invalide, When je soumets, Then 422 `VALIDATION_ERROR`.
- **A4** Given un site possède des véhicules ou conducteurs non archivés/inactifs, When je le désactive, Then 409 `SITE_HAS_ACTIVE_RESOURCES` dont le corps contient la liste des ressources bloquantes (type, UUID, libellé, plafonnée à `BLOCKING_LIST_MAX`, avec le total), aucune modification.
- **A5** Given je suis `OPS_MANAGER` ou `HR`, When je tente de créer ou modifier un site, Then 403 `PERMISSION_DENIED`.
- **A6** Given un site du tenant T2, When je le lis ou le modifie par UUID avec mon compte T1, Then 404 `NOT_FOUND`, aucune modification.
- **A7** Given une modification avec `If-Match` obsolète, Then 409 `VERSION_CONFLICT` ; sans `If-Match`, 422 `IF_MATCH_REQUIRED`.

### Thème B — Utilisateurs, rôles, authentification

#### US-1.04 — Inviter un utilisateur (M) — tranche 1a
Permission : `identity.user.create` et `identity.role_assignment.create` (`TENANT_ADMIN`).
En tant que `TENANT_ADMIN`, je veux inviter une personne par e-mail avec un rôle et une portée, afin qu'elle accède au système sans partager de mot de passe.
- **A1** Given je suis `TENANT_ADMIN`, When j'invite un e-mail valide avec un rôle du catalogue attribuable et une portée `TENANT` ou `SITE` (site de mon tenant), Then 201 : compte `INVITED`, jeton d'invitation à usage unique et expiration `INVITATION_TTL`, action auditée ; le jeton n'est jamais journalisé en clair ni renvoyé par une API de liste. L'envoi passe par un port d'e-mail (en développement : capture locale, rien n'est envoyé à l'extérieur).
- **A2** Given l'e-mail existe déjà **dans mon tenant** (comparaison insensible à la casse), When j'invite, Then 409 `DUPLICATE_EMAIL`.
- **A3** Given l'e-mail existe dans **un autre tenant**, When j'invite, Then 201 : un compte distinct est créé dans mon tenant (e-mail unique par tenant, D-06) ; aucune information sur l'autre tenant n'est divulguée.
- **A4** Given une portée `SITE` sans site, When je soumets, Then 422 `VALIDATION_ERROR`. Given un site inexistant ou d'un autre tenant, Then 422 `REFERENCE_NOT_FOUND`.
- **A5** Given un rôle `PLATFORM_ADMIN` ou tout rôle absent du catalogue attribuable par un tenant, When je soumets, Then 422 `ROLE_NOT_ASSIGNABLE` et un événement de sécurité est audité.
- **A6** Given une portée non autorisée pour le rôle (ex. `DISPATCHER` en portée `TENANT`, D-10), When je soumets, Then 422 `SCOPE_NOT_ALLOWED_FOR_ROLE`.
- **A7** Given je ne suis pas `TENANT_ADMIN` (ex. `HR`), When j'invite, Then 403 `PERMISSION_DENIED`, audité.
- **A8** Given l'envoi du message échoue, Then l'invitation reste `INVITED`, l'erreur est tracée dans le log structuré, un renvoi est possible, aucune fuite du jeton.

#### US-1.05 — Activer son compte via invitation (M) — tranche 1a
En tant qu'invité, je veux définir mon mot de passe via le lien d'invitation, afin d'activer mon compte.
- **A1** Given un jeton valide non expiré, When je définis un mot de passe conforme à `PASSWORD_POLICY`, Then le compte passe `ACTIVE`, le jeton est invalidé (usage unique), l'événement est audité.
- **A2** Given un jeton expiré, déjà utilisé ou inconnu, When je l'utilise, Then 422 `TOKEN_INVALID` (réponse unique pour les trois cas).
- **A3** Given un mot de passe non conforme, When je soumets, Then 422 `PASSWORD_POLICY_VIOLATION` avec les règles en français.
- **A4** Given le tenant est `SUSPENDED`, When j'active, Then 422 `TOKEN_INVALID` (aucune divulgation de la cause).
- **A5** Given plus de `LOGIN_MAX_FAILURES` jetons invalides consécutifs depuis la même source, Then 429 `RATE_LIMITED`. Mécanisme du Lot 1 : limitation par processus ou en base, limite documentée (QA-32) ; les tests vérifient ce qui est réellement garanti.

#### US-1.06 — Attribuer, modifier et retirer un rôle avec portée (M) — tranche 1a
Permissions : `identity.role_assignment.create` et `identity.role_assignment.revoke` (`TENANT_ADMIN` ; la révocation est `POST /role-assignments/{id}/revoke`, D-25). Les protections du dernier administrateur et de l'auto-modification sont dans US-1.31.
En tant que `TENANT_ADMIN`, je veux gérer les rôles d'un utilisateur par portée `TENANT` ou `SITE`, afin d'appliquer le moindre privilège.
- **A1** Given un utilisateur du tenant, When j'ajoute le rôle `DISPATCHER` de portée `SITE` (site S1), Then il agit uniquement sur S1 pour ce rôle ; audité.
- **A2** Given un utilisateur a `DISPATCHER` de portée `SITE` S1, When il lit un véhicule de S2 (permission `fleet.vehicle.read` couverte par S1 uniquement), Then 404 `NOT_FOUND`.
- **A3** Given l'utilisateur cumule `HR` (`TENANT`) et `DISPATCHER` (`SITE` S1), Then ses droits sont l'union des attributions, chacune évaluée avec sa portée.
- **A4** Given l'utilisateur n'a que `DISPATCHER` de portée `TENANT` (cas refusé à l'attribution par US-1.04 A6, ou hérité), When il appelle `POST` d'affectation, Then 403 `PERMISSION_DENIED` (la permission est conférée par la portée `SITE` uniquement).
- **A5** Given une attribution identique existe, When je l'ajoute, Then 409 `DUPLICATE_ROLE_ASSIGNMENT`.
- **A6** Given je suis `HR` ou `OPS_MANAGER`, When je modifie un rôle, Then 403 `PERMISSION_DENIED`, audité.
- **A7** Given un utilisateur d'un autre tenant, When je modifie ses rôles par UUID, Then 404 `NOT_FOUND`.
- **A8** Given un rôle retiré, When l'utilisateur réutilise un jeton de session émis avant, Then les droits sont réévalués côté serveur à chaque requête : l'appel à une route nécessitant la permission retirée renvoie 403 `PERMISSION_DENIED` (compte désactivé : 401 `AUTH_REQUIRED`).
- **A9** Given je tente d'attribuer le rôle `PLATFORM_ADMIN`, Then 422 `ROLE_NOT_ASSIGNABLE`, événement de sécurité audité.

#### US-1.31 — Protéger les comptes `TENANT_ADMIN` : auto-modification et dernier administrateur (M) — tranche 1a *(nouvelle, QA-07)*
Règle : `MATRICE_RBAC.md` §4.2. Un code HTTP par cas.
En tant que propriétaire du produit, je veux empêcher l'auto-escalade et le verrouillage d'un tenant, afin de garantir la séparation des pouvoirs et la continuité d'administration.
- **A1** Given je suis `TENANT_ADMIN`, When je tente d'ajouter ou de retirer **une de mes propres** attributions de rôle, Then 422 `SELF_ROLE_CHANGE_FORBIDDEN` et un événement de sécurité est audité (il faut un autre `TENANT_ADMIN`). *Évaluée avant A2 : D-05b.*
- **A2** Given je modifie l'attribution d'un autre utilisateur et qu'elle est celle du **dernier `TENANT_ADMIN` actif** du tenant, When je la retire, Then 409 `LAST_TENANT_ADMIN`, aucune modification.
- **A3** Given un utilisateur est le dernier `TENANT_ADMIN` actif, When un autre administrateur tente de le désactiver, Then 409 `LAST_TENANT_ADMIN` (voir US-1.07).
- **A4** Given deux `TENANT_ADMIN` retirent simultanément l'attribution l'un de l'autre, Then au plus une réussit, le tenant garde au moins un `TENANT_ADMIN` actif (test de concurrence ; verrou/contrainte en base).
- **A5** Given l'attribution de `TENANT_ADMIN` ou de `HR`, Then un événement d'audit à criticité élevée est écrit (la notification/double validation relève de l'arbitrage `MATRICE_RBAC.md` §6.3, hors Lot 1).
- **A6** Given le tenant n'a plus de `TENANT_ADMIN` actif (état atteint hors API, ex. incident), Then la reprise n'est **pas** une fonction d'API du Lot 1 (`PLATFORM_ADMIN` n'a aucune permission d'identité sur un tenant) ; une procédure d'exploitation tracée est à spécifier avant pilote *(à arbitrer)*.

#### US-1.07 — Désactiver / réactiver un utilisateur (M) — tranche 1a
Permission : `identity.user.deactivate` (`TENANT_ADMIN`) ; révocation des sessions via `POST …/revoke` (D-25).
En tant que `TENANT_ADMIN`, je veux désactiver un compte, afin de couper l'accès d'une personne partie sans perdre l'historique.
- **A1** Given un utilisateur `ACTIVE`, When je le désactive, Then statut `DISABLED`, ses sessions sont révoquées (appel avec ancien jeton : 401 `AUTH_REQUIRED`), il ne peut plus se connecter, ses actions passées restent attribuées dans l'audit.
- **A2** Given c'est le dernier `TENANT_ADMIN` actif, Then 409 `LAST_TENANT_ADMIN` (US-1.31 A3).
- **A3** Given je tente de désactiver mon propre compte, Then 422 `SELF_ROLE_CHANGE_FORBIDDEN` *(extension proposée de la règle d'auto-modification ; à confirmer)*.
- **A4** Given un utilisateur d'un autre tenant, Then 404 `NOT_FOUND`.
- **A5** Given je réactive, Then le compte redevient `ACTIVE` avec ses attributions précédentes ; audité.
- **A6** Given un non-admin appelle l'action, Then 403 `PERMISSION_DENIED`.

#### US-1.08 — Se connecter (M) — tranche 1a
En tant qu'utilisateur actif, je veux me connecter avec le **code d'espace de travail**, mon **e-mail** et mon mot de passe (D-06), afin d'accéder aux fonctions autorisées par mes rôles.
- **A1** Given un compte `ACTIVE` d'un tenant `ACTIVE`, When je saisis un code d'espace, un e-mail et un mot de passe corrects, Then une session est ouverte, l'interface n'affiche que les fonctions autorisées par mes rôles et ma portée, l'événement est audité. Le code d'espace peut être porté par l'URL ou saisi.
- **A2** Given un code d'espace inconnu, **ou** un e-mail inconnu dans ce tenant, **ou** un mot de passe erroné, **ou** un compte `INVITED`/`DISABLED`, **ou** un tenant `SUSPENDED`, When je me connecte, Then 401 `INVALID_CREDENTIALS` avec un corps et un message strictement identiques dans les cinq cas (pas d'énumération de tenants ni de comptes).
- **A3** Given `LOGIN_MAX_FAILURES` échecs consécutifs sur le couple (code d'espace, e-mail) ou depuis une même source, Then 429 `RATE_LIMITED` pendant `LOGIN_LOCKOUT_DURATION` ; l'événement est audité (mécanisme et limites : voir US-1.05 A5).
- **A4** Given le même e-mail existe dans deux tenants, When je me connecte avec le code d'espace du tenant A, Then la session est celle du compte du tenant A uniquement.
- **A5** Given une session expirée, When j'appelle l'API, Then 401 `AUTH_REQUIRED` et l'UI propose de se reconnecter sans perdre la saisie en cours.
- **A6** Given une connexion lente ou coupée pendant la soumission, Then l'UI affiche un état d'attente puis une erreur claire ; une seule session est ouverte par soumission réussie.
- **A7** Given la politique MFA (C-03 : TOTP pour `PLATFORM_ADMIN`, `TENANT_ADMIN`, `HR`, `FINANCE`, livrée **après** le Lot 1), Then aucun critère MFA n'est exigé au Lot 1.
- **Exigences de conception (vérifiées en revue sécurité, pas des critères de story)** : hachage de mot de passe validé par `security-engineer`, mots de passe jamais journalisés, résolution pré-authentification du tenant par code exact sans `BYPASSRLS` (D-06, DB-05).

#### US-1.09 — Se déconnecter (M) — tranche 1a
En tant qu'utilisateur connecté, je veux me déconnecter, afin de protéger mon compte sur un poste partagé.
- **A1** Given une session active, When je me déconnecte, Then la session et les jetons de rafraîchissement sont révoqués côté serveur et un appel réutilisant l'ancien jeton reçoit 401 `AUTH_REQUIRED`.
- **A2** Given je me déconnecte, Then aucun jeton ni donnée métier n'est conservé dans le stockage du navigateur (stockage de session, stockage local, mémoire applicative) et la navigation « page précédente » ne réaffiche pas de données métier. (Aucun cache hors ligne n'existe au Lot 1 ; la purge d'un cache PWA relève du lot 4.)
- **A3** Given une session déjà expirée, When je me déconnecte, Then 204 sans erreur bloquante.
- **A4** Given l'événement, Then il est audité.

#### US-1.10 — Réinitialiser son mot de passe (S) — tranche 1a
Route publique documentée (permission pré-authentification propre, à ajouter à `authz_matrix.yaml` ; `identity.user.reset_credentials` désigne l'action administrateur, distincte).
En tant qu'utilisateur, je veux réinitialiser mon mot de passe oublié avec mon code d'espace et mon e-mail, afin de retrouver l'accès sans intervention de l'éditeur.
- **A1** Given un code d'espace et un e-mail saisis, When je demande la réinitialisation, Then la réponse est identique (202, même corps, même message) que le couple existe ou non ; un lien à usage unique (`RESET_TOKEN_TTL`) est envoyé si le compte est `ACTIVE` d'un tenant `ACTIVE`.
- **A2** Given un lien valide, When je définis un nouveau mot de passe conforme, Then toutes les sessions antérieures sont révoquées et l'action est auditée.
- **A3** Given un lien expiré, déjà utilisé ou inconnu, Then 422 `TOKEN_INVALID`.
- **A4** Given des demandes répétées, Then 429 `RATE_LIMITED` au-delà de la limite configurée.

### Thème C — Véhicules (catégories, parc)

#### US-1.11 — Consulter les catégories de véhicule (M) — tranche 1b
Permission : `fleet.vehicle_category.read` (tous les rôles).
En tant qu'utilisateur du tenant, je veux voir les catégories de véhicule de mon tenant, afin de classer correctement mes engins.
- **A1** Given je suis connecté, When j'ouvre la liste, Then je vois les catégories **copiées pour mon tenant à sa création** (D-18), libellés français, avec les catégories de permis requises (table de jonction catégorie↔permis).
- **A2** Given une catégorie d'un autre tenant, When j'y accède par UUID, Then 404 `NOT_FOUND`.
- **A3** Given un tenant dont la copie est vide (anomalie), Then état vide avec message d'orientation ; ce cas ne peut pas se produire pour un tenant créé par US-1.01 (test de création).
- **Hors Lot 1** : création/modification de catégories par le tenant (`fleet.vehicle_category.manage` reportée, aucune story).

#### US-1.12 — Créer un véhicule (M) — tranche 1b
Permission : `fleet.vehicle.create` (`TENANT_ADMIN`, `OPS_MANAGER`).
En tant que `OPS_MANAGER` (ou `TENANT_ADMIN`), je veux enregistrer un véhicule ou engin avec sa catégorie, son immatriculation éventuelle, son numéro de parc et son site, afin de constituer le référentiel du parc.
- **A1** Given je suis `OPS_MANAGER` de portée `SITE` S1, When je crée un véhicule sur S1 avec catégorie valide du tenant, numéro de parc unique et (si fournie) immatriculation unique, Then 201, statut `AVAILABLE`, UUID, audité, première ligne de `vehicle_status_history`.
- **A2** Given l'immatriculation existe déjà dans mon tenant, y compris sur un véhicule `RETIRED` (comparaison normalisée : casse, espaces, tirets), When je crée, Then 409 `DUPLICATE_REGISTRATION` ; la même valeur dans un autre tenant est acceptée. *(Unicité sur archivés : hypothèse prudente, C-13 ne tranchant que le numéro de parc.)*
- **A3** Given le numéro de parc existe déjà dans mon tenant, y compris sur un véhicule `RETIRED` (unique à vie, C-13), Then 409 `DUPLICATE_FLEET_NUMBER`.
- **A4** Given un engin sans plaque, When l'immatriculation est vide, Then 201 si le numéro de parc est renseigné ; sinon 422 `VALIDATION_ERROR`.
- **A5** Given je vise un site S2 hors de ma portée ou d'un autre tenant, When je crée, Then 422 `REFERENCE_NOT_FOUND`, aucune création.
- **A6** Given une catégorie inexistante ou d'un autre tenant, Then 422 `REFERENCE_NOT_FOUND`.
- **A7** Given je suis `HR`, `DISPATCHER` ou `DRIVER`, When je tente de créer, Then 403 `PERMISSION_DENIED`, audité.
- **A8** Given des champs invalides (longueurs, caractères, année absurde si saisie), Then 422 `VALIDATION_ERROR` par champ.
- **A9** Given une soumission répétée suite à une coupure réseau (pas d'idempotence au Lot 1, D-14), Then la seconde reçoit 409 `DUPLICATE_FLEET_NUMBER` ; un seul véhicule existe.

#### US-1.13 — Lister et consulter les véhicules (M) — tranche 1b
Permission : `fleet.vehicle.read` (selon `MATRICE_RBAC.md` §2.3 : notamment `TENANT_ADMIN`, `DIRECTION`, `OPS_MANAGER`, `DISPATCHER` (site), `HSE`, `FINANCE`, `AUDITOR`, et `WORKSHOP_CHIEF`/`MECHANIC` (site) ; `HR` n'a pas la lecture ; `DRIVER` : non au Lot 1).
En tant qu'utilisateur autorisé, je veux rechercher et filtrer les véhicules (site, catégorie, statut, immatriculation), afin de trouver rapidement un engin.
- **A1** Given mon rôle a la lecture et ma portée est S1, When je liste, Then seuls les véhicules de S1 apparaissent, paginés (CT-9), avec total correct.
- **A2** Given une recherche par immatriculation, Then les résultats sont limités à mon tenant et à ma portée.
- **A3** Given un UUID de véhicule d'un autre tenant ou d'un site hors portée, When je le consulte, Then 404 `NOT_FOUND`.
- **A4** Given aucun résultat, Then un état vide explicite s'affiche.
- **A5** Given un paramètre de filtre invalide ou inconnu, Then 422 `VALIDATION_ERROR`.
- **A6** Given un paramètre `tenant_id` fourni par le client, Then 422 `VALIDATION_ERROR` (CT-1).
- **A7** Given je suis `HR` (sans permission de lecture des véhicules), When j'appelle la liste, Then 403 `PERMISSION_DENIED`.
- **A8** Given la disponibilité « en exploitation », Then elle est un champ **dérivé** de l'affectation active, jamais un statut stocké (D-02).

#### US-1.14 — Modifier un véhicule et changer son statut (M) — tranche 1b
Permissions : `fleet.vehicle.update` (`TENANT_ADMIN`, `OPS_MANAGER`) ; `fleet.vehicle.update_status` (`TENANT_ADMIN`, `OPS_MANAGER`, et `DISPATCHER`/`WORKSHOP_CHIEF` avec portée `SITE`).
En tant qu'acteur autorisé, je veux modifier les attributs d'un véhicule et son statut, afin de refléter son état réel.
- **A1** Given un véhicule de mon périmètre, When je modifie catégorie, site ou attributs avec `If-Match`, Then enregistré, audité (avant/après), `row_version` incrémentée.
- **A2** Given je passe le statut à `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE` ou `RETIRED` alors qu'une affectation `PLANNED` ou `ACTIVE` existe (D-11), Then 409 `OPEN_ASSIGNMENTS_EXIST` avec la liste des affectations à clôturer, statut inchangé.
- **A3** Given je passe le statut à `IMMOBILIZED`, `OUT_OF_SERVICE` ou `RETIRED` sans code de motif, Then 422 `STATUS_REASON_REQUIRED`.
- **A4** Given je change le **site** d'un véhicule ayant une affectation `PLANNED` ou `ACTIVE` (D-13), Then 409 `OPEN_ASSIGNMENTS_EXIST` avec liste.
- **A5** Given un véhicule `RETIRED`, When je tente un autre statut (statut terminal, C-13), Then 422 `VEHICLE_STATUS_TRANSITION_INVALID`.
- **A6** Given une version obsolète, Then 409 `VERSION_CONFLICT` ; sans `If-Match`, 422 `IF_MATCH_REQUIRED`.
- **A7** Given un véhicule d'un autre tenant ou hors de ma portée, Then 404 `NOT_FOUND` ; un rôle sans droit d'écriture sur une ressource visible, Then 403 `PERMISSION_DENIED`.
- **A8** Given une immatriculation en conflit avec un autre véhicule du tenant, Then 409 `DUPLICATE_REGISTRATION`.
- **A9** Given chaque changement de statut, Then une ligne est ajoutée à `vehicle_status_history` (alimentée par trigger) avec l'ancien statut, le nouveau, le motif, l'auteur.

#### US-1.15 — Réformer (archiver) un véhicule (S) — tranche 1b
Permission : `fleet.vehicle.deactivate` (`TENANT_ADMIN`, `OPS_MANAGER`).
En tant que `OPS_MANAGER`, je veux retirer un véhicule du parc actif sans perdre son historique, afin de garder un référentiel propre.
- **A1** Given un véhicule sans affectation `PLANNED`/`ACTIVE`, When je le passe `RETIRED` avec motif, Then il disparaît des listes par défaut et des choix d'affectation mais reste consultable via filtre ; audité.
- **A2** Given une affectation `PLANNED`/`ACTIVE`, Then 409 `OPEN_ASSIGNMENTS_EXIST` avec liste (D-11).
- **A3** Given un véhicule `RETIRED`, When je tente de le réactiver, Then 422 `VEHICLE_STATUS_TRANSITION_INVALID` (terminal, C-13 ; la réactivation est hors Lot 1).

### Thème D — Conducteurs, permis, habilitations

#### US-1.16 — Créer un conducteur (M) — tranche 1b
Permission : `workforce.driver.create` (`HR` seul).
En tant que `HR`, je veux créer le dossier d'un conducteur rattaché à un site, afin de constituer le référentiel du personnel roulant. Aucun compte utilisateur n'est requis ni lié au Lot 1 (H6, D-16).
- **A1** Given je suis `HR` de portée `TENANT` ou `SITE` S1, When je crée un conducteur avec matricule unique dans le tenant, nom, prénom, site (et téléphone facultatif), Then 201, statut `ACTIVE`, audité.
- **A2** Given le matricule existe déjà dans le tenant, Then 409 `DUPLICATE_EMPLOYEE_NUMBER`.
- **A3** Given un site hors de ma portée ou d'un autre tenant, Then 422 `REFERENCE_NOT_FOUND`, aucune création.
- **A4** Given un champ hors liste du Lot 1 (date de naissance, adresse, photo, pièce d'identité, aptitude médicale, motif de maladie — D-15), When je le fournis, Then 422 `VALIDATION_ERROR` (schéma strict).
- **A5** Given je suis `DISPATCHER`, `OPS_MANAGER`, `TENANT_ADMIN`, `DRIVER`, Then 403 `PERMISSION_DENIED`, audité.
- **A6** Given un conducteur de même nom et prénom normalisés (casse, accents, espaces) sur le même site existe, When je crée, Then 201 avec un avertissement `POSSIBLE_DUPLICATE` dans la réponse (non bloquant, règle de similarité définie ici) ; le matricule unique reste la seule contrainte bloquante.
- **A7** Given des données de démonstration, Then elles sont fictives (H9).

#### US-1.17 — Consulter et modifier un conducteur (M) — tranche 1b
Permissions : `workforce.driver.read` (vue masquée), `workforce.driver.read_sensitive`, `workforce.driver.update` (`HR`).
En tant que `HR`, je veux consulter et corriger un dossier conducteur ; en tant que rôle autorisé, consulter l'identité professionnelle, afin d'affecter les bonnes personnes tout en protégeant les données personnelles.
- **A1** Given je suis `HR`, When j'ouvre un conducteur de mon périmètre, Then je vois toutes les données du dossier Lot 1, y compris le téléphone.
- **A2** Given je suis `DISPATCHER` (site), `OPS_MANAGER`, `DIRECTION`, `HSE` ou `AUDITOR`, When j'ouvre le même conducteur, Then la réponse contient matricule, nom, prénom, site, statut et catégories autorisées ; le **téléphone est absent** de la réponse (masquage total, D-15, vérifié par valeur sentinelle).
- **A3** Given un conducteur d'un autre tenant ou d'un site hors portée, Then 404 `NOT_FOUND`. Given je suis `TENANT_ADMIN` (aucune permission `workforce.driver.read`, D-10), Then 403 `PERMISSION_DENIED` sur la liste comme sur la fiche.
- **A4** Given une modification avec `If-Match` obsolète, Then 409 `VERSION_CONFLICT`.
- **A5** Given un changement de site avec affectation `PLANNED`/`ACTIVE` (D-13), Then 409 `OPEN_ASSIGNMENTS_EXIST` avec liste.
- **A6** Given une modification, Then audit sans valeur sensible en clair (marqueur « modifié » pour le téléphone).
- **A7** Given un filtre ou tri sur le téléphone par un rôle non `HR`, Then 422 `VALIDATION_ERROR`.
- **A8** Given la journalisation de la lecture du téléphone/numéro de permis en clair par `HR` *(Q19, à arbitrer ; défaut : tracée dans le journal technique structuré, pas d'écriture d'audit lors d'un GET)*, Then exclue des tests automatiques tant que Q19 n'est pas tranchée.

#### US-1.18 — Enregistrer un permis de conduire (M) — tranche 1b
Permissions : `workforce.driver_license.manage` (`HR` seul), `workforce.driver_license.read` (`HR` ; vue sans numéro pour `OPS_MANAGER`, `DISPATCHER` site, `HSE`, `AUDITOR` ; `TENANT_ADMIN` : non), `workforce.driver_license.read_number` (`HR` seul au Lot 1).
En tant que `HR`, je veux enregistrer le permis d'un conducteur (catégorie, numéro, délivrance, expiration), afin de vérifier l'éligibilité à l'affectation.
- **A1** Given un conducteur de mon périmètre, When j'ajoute un permis (une ligne par catégorie) avec expiration postérieure à la délivrance, Then 201, statut stocké `VALID`, audité ; la validité dérivée (`VALID`, `EXPIRING` si l'échéance est dans `EXPIRY_WARNING_DAYS`, `EXPIRED`) est calculée avec la date du jour au fuseau du site.
- **A2** Given une expiration antérieure ou égale à la délivrance, Then 422 `VALIDATION_ERROR`.
- **A3** Given un permis déjà expiré à la saisie, Then 201 (historique), validité dérivée `EXPIRED`, aucune éligibilité.
- **A4** Given un doublon (même conducteur, numéro et catégorie), Then 409 `DUPLICATE_LICENSE`.
- **A5** Given un renouvellement, When j'ajoute un nouveau permis, Then l'ancien reste historisé et le plus récent valide sert à l'éligibilité.
- **A6** Given le numéro de permis, Then il est absent de toute réponse destinée à un rôle sans `read_number`, absent des logs et de l'audit (marqueur « modifié »).
- **A7** Given un rôle autre que `HR` (dont `TENANT_ADMIN`), Then 403 `PERMISSION_DENIED` ; un conducteur d'un autre tenant ou hors portée, Then 404 `NOT_FOUND`.
- **A8** Given une expiration au jour J, Then (fuseau du site à décalage non nul, D-23) le permis est `VALID`/`EXPIRING` jusqu'au début du jour J+1 local du site (exclu) puis `EXPIRED` ; bornes testées avec horloge injectée : J 23:59:59 local, J+1 00:00:00 local, et le même instant UTC vu depuis un site UTC+0 et un site UTC+1.

#### US-1.19 — Enregistrer une habilitation engin (M) — tranche 1b
Permissions : `workforce.driver_qualification.manage/revoke` (`HR` seul au Lot 1, D-10), `workforce.driver_qualification.read` (`DIRECTION`, `OPS_MANAGER`, `DISPATCHER` site, `HR`, `WORKSHOP_CHIEF` site, `HSE`, `AUDITOR` ; `TENANT_ADMIN` : non).
En tant que `HR`, je veux enregistrer les habilitations par catégorie d'engin avec leur expiration, afin de n'affecter que des personnes habilitées.
- **A1** Given un conducteur de mon périmètre, When j'ajoute une `driver_qualification` pour une catégorie de véhicule avec validité et expiration, Then 201, statut stocké `VALID`, audité.
- **A2** Given une habilitation expirée, Then elle n'ouvre aucune éligibilité (dérivée `EXPIRED`), reste visible en historique.
- **A3** Given une catégorie inconnue du référentiel du tenant, Then 422 `REFERENCE_NOT_FOUND`.
- **A4** Given une habilitation `VALID` qui se chevauche pour le même (conducteur, catégorie), Then 409 `DUPLICATE_QUALIFICATION`.
- **A5** Given je suis `HSE`, When je tente d'écrire, Then 403 `PERMISSION_DENIED` (lecture seule au Lot 1, D-10 ; écriture HSE reportée).
- **A6** Given un conducteur d'un autre tenant ou hors portée, Then 404 `NOT_FOUND`.
- **A7** Given le mapping catégorie de véhicule → permis/habilitation requis, Then il provient de données fictives de développement marquées « à valider localement » (C-07).

#### US-1.20 — Voir les expirations à venir (S) — tranche 1b
En tant que `HR`, je veux la liste des permis et habilitations expirant bientôt ou expirés, afin d'anticiper les renouvellements.
- **A1** Given `EXPIRY_WARNING_DAYS` (par tenant), When j'ouvre la liste, Then je vois les éléments dont la validité dérivée est `EXPIRING` ou `EXPIRED`, triés par date, limités à ma portée.
- **A2** Given un élément expiré lié à une affectation `ACTIVE`, Then il est mis en évidence via la conformité dérivée de US-1.25.
- **A3** Given aucun élément, Then état vide.
- **A4** Given un autre tenant, Then ses données n'apparaissent jamais (test inter-tenant).
- **A5** Given un rôle sans permission de lecture des permis, Then 403 `PERMISSION_DENIED`.

#### US-1.21 — Changer le statut d'un conducteur (désactiver / réactiver) (M) — tranche 1b
Permission : `workforce.driver.deactivate` (`HR` seul).
En tant que `HR`, je veux passer un conducteur en `UNAVAILABLE`, `SUSPENDED` ou `INACTIVE` (ou le réactiver), afin d'empêcher toute nouvelle affectation en conservant l'historique.
- **A1** Given un conducteur `ACTIVE` sans affectation `PLANNED`/`ACTIVE`, When je le passe `INACTIVE` (motif obligatoire), Then statut mis à jour, absent des choix d'affectation, historique conservé, audité.
- **A2** Given une affectation `PLANNED` ou `ACTIVE` (D-11), When je passe le conducteur à un statut autre que `ACTIVE`, Then 409 `OPEN_ASSIGNMENTS_EXIST` avec la liste des affectations à clôturer, statut inchangé.
- **A3** Given un statut sans motif, Then 422 `STATUS_REASON_REQUIRED`.
- **A4** Given une réactivation (`ACTIVE`), Then permis et habilitations expirés restent inéligibles (dérivé des dates).
- **A5** Given un autre tenant ou hors portée, Then 404 `NOT_FOUND` ; un rôle non autorisé, Then 403 `PERMISSION_DENIED`.
- **Hors Lot 1** : liaison compte↔conducteur ; la désactivation d'un conducteur n'a aucun effet sur un compte utilisateur.

### Thème E — Affectations

#### US-1.22 — Affecter un conducteur à un véhicule (M) — tranche 1c
Permission : `assignment.vehicle_assignment.create` (`OPS_MANAGER` ; `DISPATCHER` avec portée `SITE` uniquement). `TENANT_ADMIN`, `HR`, `HSE`, `DRIVER`, `MECHANIC`, `FINANCE` : 403.
En tant que `DISPATCHER` (site) ou `OPS_MANAGER`, je veux affecter un conducteur à un véhicule sur une période, afin de savoir qui conduit quoi et d'empêcher les affectations invalides.
- **Règles métier** (toutes bloquantes ; ordre d'évaluation en 0.4) :
  - R1 Le conducteur est `ACTIVE`.
  - R2 Le véhicule est `AVAILABLE`.
  - R3 Même site obligatoire pour véhicule, conducteur et affectation ; **aucune dérogation** (D-13, C-04 provisoire).
  - R4 Aucun chevauchement pour le véhicule ni pour le conducteur : intervalle semi-ouvert `[valid_from, valid_to)` ; les affectations de statut `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED` comptent, seules les `CANCELLED` sont exclues (D-04) ; une affectation peut commencer exactement à la fin d'une autre. La garantie est une **contrainte d'exclusion en base**.
  - R5 Éligibilité : le conducteur a un permis de catégorie suffisante et une habilitation pour la catégorie du véhicule, de validité dérivée `VALID` ou `EXPIRING` (le second avec avertissement dans la réponse), et valables sur **tout l'intervalle si la fin est fournie** (fin ≤ début du jour suivant l'expiration, au fuseau du site). Si l'intervalle est **ouvert** : valables à l'instant de début, avec avertissement indiquant la prochaine échéance ; l'affectation devient ensuite « non conforme » à la lecture (US-1.25), sans suspension automatique au Lot 1.
  - R6 `valid_from` obligatoire ; `valid_to` facultatif mais strictement postérieur.
  - R7 **Pas d'antidatage** (D-13) : `valid_from ≥ maintenant − ASSIGNMENT_BACKDATE_TOLERANCE` (horloge serveur) ; aucune dérogation ni motif ne l'autorise au Lot 1.
- **A1** Given conducteur et véhicule éligibles sur le site S1 dans ma portée, When je crée l'affectation avec dates valides, Then 201, statut `PLANNED` (début futur) ou `ACTIVE`, audité avec les deux identifiants ; la réponse porte la conformité dérivée `COMPLIANT`.
- **A2** Given le véhicule a une affectation qui chevauche, Then 409 `VEHICLE_ASSIGNMENT_OVERLAP`, message français, sans donnée hors périmètre.
- **A3** Given le conducteur a une affectation qui chevauche (et pas le véhicule), Then 409 `DRIVER_ASSIGNMENT_OVERLAP`.
- **A4** Given deux requêtes réellement concurrentes créent des affectations chevauchantes pour le même véhicule, Then exactement une réussit (201), l'autre reçoit 409 `VEHICLE_ASSIGNMENT_OVERLAP` (contrainte en base, test sur PostgreSQL réel).
- **A5** Given le conducteur n'est pas `ACTIVE`, Then 422 `DRIVER_NOT_ACTIVE`.
- **A6** Given le véhicule est `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE` ou `RETIRED`, Then 422 `VEHICLE_NOT_AVAILABLE`.
- **A7** Given permis absent/expiré/de catégorie insuffisante, ou habilitation absente/expirée, ou permis expirant avant la fin fournie, Then 422 `DRIVER_NOT_QUALIFIED` avec `reasons[]` (codes en 0.4, date d'expiration pour les motifs d'expiration, jamais le numéro de permis).
- **A8** Given conducteur et véhicule de sites différents, Then 422 `ASSIGNMENT_SITE_MISMATCH`.
- **A9** Given un conducteur ou un véhicule d'un autre tenant ou hors de ma portée, référencé dans le corps, When je soumets, Then 422 `REFERENCE_NOT_FOUND`, aucune affectation ; la clé étrangère composite empêche aussi la création directe en base (H3).
- **A10** Given `valid_to ≤ valid_from`, Then 422 `END_BEFORE_START`.
- **A11** Given `valid_from` antérieur à `maintenant − ASSIGNMENT_BACKDATE_TOLERANCE`, Then 422 `ASSIGNMENT_BACKDATED`.
- **A12** Given je suis `HR`, `HSE`, `DRIVER`, `MECHANIC`, `TENANT_ADMIN`, ou `DISPATCHER` sans attribution `SITE`, Then 403 `PERMISSION_DENIED`, audité.
- **A13** Given une soumission répétée (double clic, renvoi après coupure ; pas d'idempotence au Lot 1, D-14), Then la seconde reçoit 409 `VEHICLE_ASSIGNMENT_OVERLAP` ; une seule affectation existe ; l'UI désactive le bouton pendant l'envoi.
- **A14** Given l'heure saisie dans le fuseau du site (test avec un site à décalage non nul), Then elle est stockée en UTC et l'affichage est cohérent ; la tolérance d'horloge client est `CLOCK_SKEW_TOLERANCE`, le serveur fait foi.

#### US-1.23 — Clôturer ou annuler une affectation (M) — tranche 1c
Permission : `assignment.vehicle_assignment.end` (`OPS_MANAGER` ; `DISPATCHER` portée `SITE`).
En tant que `DISPATCHER` (site) ou `OPS_MANAGER`, je veux clôturer une affectation en cours ou annuler une affectation planifiée, afin de libérer le conducteur et le véhicule.
- **A1** Given une affectation `ACTIVE` dans ma portée, When je la clôture avec une date de fin ≥ son début et ≤ maintenant + `ASSIGNMENT_END_FUTURE_TOLERANCE`, Then 200, statut `COMPLETED`, `valid_to` renseigné (fin réelle tronquée), ressources disponibles à partir de cet instant, audité.
- **A2** Given une affectation `COMPLETED` ou `CANCELLED`, When je la clôture ou l'annule, Then 409 `ASSIGNMENT_STATE_INVALID`.
- **A3** Given une date de fin antérieure au début, Then 422 `END_BEFORE_START`.
- **A4** Given une date de fin au-delà de la tolérance dans le futur, Then 422 `END_IN_FUTURE` (aucune « fin programmée » au Lot 1).
- **A5** Given une affectation `PLANNED`, When je l'annule avec motif, Then 200, statut `CANCELLED`, ressources libérées immédiatement ; sans motif, 422 `STATUS_REASON_REQUIRED`.
- **A6** Given j'essaie d'annuler une affectation `ACTIVE` (ou de clôturer une `PLANNED`), Then 409 `ASSIGNMENT_STATE_INVALID`.
- **A7** Given une affectation d'un autre tenant ou hors portée, Then 404 `NOT_FOUND` ; un rôle sans la permission, Then 403 `PERMISSION_DENIED`.
- **A8** Given une clôture à l'instant T puis une nouvelle affectation du même véhicule commençant à T, Then la nouvelle est acceptée (intervalle semi-ouvert).
- **A9** Given une version obsolète, Then 409 `VERSION_CONFLICT`.
- **A10** Given une affectation `COMPLETED` ou `CANCELLED`, Then elle est immuable (aucune route de modification) ; l'« événement correctif » est hors Lot 1.

#### US-1.24 — Consulter les affectations et l'historique (M) — tranche 1c
Permission : `assignment.vehicle_assignment.read` (selon la matrice : `DIRECTION`, `OPS_MANAGER`, `DISPATCHER` (site), `HR`, `HSE`, `AUDITOR`, `WORKSHOP_CHIEF` (site) ; `TENANT_ADMIN`, `FINANCE` et `DRIVER` : non au Lot 1, D-25).
En tant que rôle autorisé, je veux voir les affectations en cours et l'historique par véhicule ou conducteur, afin de savoir qui conduisait quoi à un instant donné.
- **A1** Given un véhicule de ma portée, When je consulte son historique, Then les affectations sont triées (tri stable, CT-9), avec dates affichées au fuseau du site.
- **A2** Given un instant donné, When je demande « qui conduisait ce véhicule », Then j'obtiens l'unique affectation non `CANCELLED` dont `[valid_from, valid_to)` contient l'instant, ou une liste vide ; test des bornes : à `valid_from` inclus, à `valid_to` exclu.
- **A3** Given un conducteur ou véhicule d'un autre tenant ou hors portée, Then 404 `NOT_FOUND`.
- **A4** Given une portée `SITE`, Then seules les affectations de mes sites sont visibles ; comme véhicule, conducteur et affectation partagent le même site (D-13), il n'existe pas de cas d'affectation inter-sites (Q20 sans objet).
- **A5** Given je suis `TENANT_ADMIN`, `FINANCE` ou `DRIVER`, When j'appelle la liste ou l'historique des affectations, Then 403 `PERMISSION_DENIED` (la pseudonymisation pour `FINANCE` est reportée avec le module coûts).
- **A6** Given une liste volumineuse, Then pagination et tri stables (CT-9).
- **Hors Lot 1** : « mes affectations » pour un `DRIVER` (aucun écran ni compte conducteur, D-16).

#### US-1.25 — Voir la conformité d'une affectation (dérivée) (S) — tranche 1c
En tant que `DISPATCHER` (site), `OPS_MANAGER` ou `HR`, je veux voir si une affectation active est devenue non conforme (permis ou habilitation expiré, statut conducteur ou véhicule incompatible), afin de réagir sans blocage silencieux.
- **A1** Given une affectation `ACTIVE`, When je la lis, Then la réponse contient un champ **calculé à la lecture** `compliance` = `COMPLIANT` ou `NON_COMPLIANT` avec `reasons[]` (`LICENSE_EXPIRED`, `QUALIFICATION_EXPIRED`, `DRIVER_NOT_ACTIVE`, `VEHICLE_NOT_AVAILABLE`) ; **aucun statut stocké n'est modifié, aucun job n'est exécuté** (D-12).
- **A2** Given un permis qui atteint son échéance (instant limite franchi avec l'horloge injectée), Then la lecture suivante renvoie `NON_COMPLIANT` avec `LICENSE_EXPIRED`, l'affectation reste `ACTIVE` et n'est pas clôturée automatiquement.
- **A3** Given une affectation `NON_COMPLIANT`, When je la consulte, Then je peux la clôturer (US-1.23) ; la liste des affectations accepte le filtre `compliance=NON_COMPLIANT`.
- **A4** Given un tenant différent, Then jamais d'effet croisé (test inter-tenant).
- **A5** Given un permis `EXPIRING`, Then `COMPLIANT` avec avertissement.
- **A6** Given les statuts `PLANNED`, `COMPLETED`, `CANCELLED`, Then `compliance` n'est pas calculée (champ absent).
- **Hors Lot 1** : transition automatique vers `SUSPENDED`, alertes planifiées et idempotence de job (lot 2+, planificateur).

### Thème F — Audit et transverse

#### US-1.26 — Consulter le journal d'audit (M) — tranche 1a
Permission : `audit.event.read` (`TENANT_ADMIN`, `AUDITOR` — D-10).
En tant que `TENANT_ADMIN` ou `AUDITOR`, je veux consulter et filtrer le journal d'audit de mon tenant, afin de tracer qui a fait quoi et quand.
- **A1** Given je suis `TENANT_ADMIN`, When j'ouvre le journal, Then je vois les événements de mon tenant, paginés (CT-9), filtrables par période, acteur, action, type de ressource, site, avec horodatage affiché au fuseau configuré.
- **A2** Given je suis `AUDITOR`, Then lecture seule ; l'export est hors Lot 1 (D-16).
- **A3** Given je suis `HR`, `DISPATCHER`, `DIRECTION`, `DRIVER` ou tout autre rôle, Then 403 `PERMISSION_DENIED`, audité.
- **A4** Given un événement d'un autre tenant, When j'en demande l'UUID, Then 404 `NOT_FOUND` ; la liste ne contient jamais d'événement d'un autre tenant.
- **A5** Given la portée du rôle d'audit, Then portée `TENANT` uniquement au Lot 1 *(hypothèse ; portée `SITE` du journal non retenue)*.
- **A6** Given un événement, Then il est immuable : aucune route de modification ou de suppression, `mf_app` n'a que `INSERT`/`SELECT` sur `audit_event`, un trigger refuse `UPDATE`/`DELETE` (D-17) ; la table est partitionnée par mois dès la migration 0001.
- **A7** Given des données sensibles (numéro de permis, téléphone, mot de passe, jeton), Then elles n'apparaissent jamais en clair dans le journal (marqueur « modifié »).
- **A8** Given la consultation du journal, Then elle est tracée dans le log technique structuré (pas d'écriture d'audit lors d'un GET, QA-10) *(hypothèse)*.
- **A9** Given je suis `PLATFORM_ADMIN`, When j'appelle la lecture du journal, Then 403 `PERMISSION_DENIED` (`audit.event.read` ❌ pour `PLATFORM_ADMIN`) ; la consultation des événements de plateforme (création/suspension de tenant) n'a **pas** d'API au Lot 1 *(à arbitrer)*.

#### US-1.27 — Journalisation systématique des écritures (M, transverse) — tranches 1a à 1c
En tant qu'`AUDITOR`, je veux que chaque action métier soit tracée, afin de garantir la traçabilité.
- **A1** Given n'importe quelle écriture réussie des stories US-1.01 à US-1.32, Then exactement un `audit_event` par opération métier existe, avec acteur, tenant, ressource, action (nom issu de `authz_matrix.yaml`), heure UTC.
- **A2** Given un refus 403, Then un événement de refus est écrit (tous les refus 403, CT-1) ; un 404 sur identifiant d'un autre tenant produit un log de sécurité structuré et un compteur, pas d'événement d'audit tenant.
- **A3** Given l'écriture métier réussit mais l'audit échoue, Then l'ensemble est annulé (transaction commune, audit obligatoire).
- **A4** Given les journaux techniques, Then ils sont structurés avec identifiant de corrélation et ne contiennent aucun secret ni donnée personnelle brute.

#### US-1.28 — Isolation inter-tenant (M, transverse) — tranches 1a à 1c
En tant que `TENANT_ADMIN`, je veux la garantie qu'aucune donnée de mon tenant n'est accessible à un autre tenant, afin d'avoir confiance dans la plateforme.
- **A1** Given deux tenants T1 et T2 avec données, When un utilisateur T1 appelle chaque endpoint de lecture avec des UUID de T2, Then 404 `NOT_FOUND` et jamais de contenu.
- **A2** Given chaque endpoint d'écriture, When un utilisateur T1 cible une ressource de T2 dans l'URL, Then 404 `NOT_FOUND` et aucune modification en base ; dans le corps, 422 `REFERENCE_NOT_FOUND`.
- **A3** Given un `tenant_id` dans la requête, Then 422 `VALIDATION_ERROR`.
- **A4** Given une tentative de créer directement en base une référence inter-tenant, Then la clé étrangère composite la rejette.
- **A5** Given une requête sans contexte de tenant (RLS, D-08), Then zéro ligne retournée, jamais d'erreur sur connexion de pool réutilisée.
- **A6** Given listes, compteurs et recherches, Then ils n'incluent jamais de données d'un autre tenant (pas de fuite par le total).
- **A7** Given ces tests, Then ils sont générés depuis `authz_matrix.yaml` (D-09), s'exécutent par la CI locale en conteneurs et bloquent la livraison ; la CI distante dépend de C-17 (non exécutée tant qu'aucun dépôt distant n'est choisi, D-24). Rien n'a encore été exécuté.
- **Hors Lot 1** : exports et suggestions n'existent pas.

#### US-1.29 — Interface web minimale en français (M, transverse) — chaque écran livré avec la tranche de sa story ; accessibilité et E2E clôturés en 1c
En tant qu'utilisateur, je veux une interface web simple en français, adaptée à mes droits et à une connexion lente, afin d'utiliser les fonctions du Lot 1.
- **A1** Given je suis connecté, Then la navigation n'affiche que les écrans autorisés par mes rôles et ma portée ; l'API reste l'autorité (masquer un bouton n'est jamais la seule protection).
- **A2** Given une connexion lente ou coupée (profils réseau consignés dans la configuration Playwright, `STRATEGIE_QUALITE_CI.md` §1.3), When j'enregistre un formulaire, Then un état de chargement s'affiche et, en cas d'échec, un message clair avec conservation de la saisie.
- **A3** Given les largeurs de test 360, 768 et 1280 px, Then les écrans principaux (liste véhicules, conducteurs, affectation) n'ont aucun défilement horizontal.
- **A4** Given l'accessibilité (cible WCAG 2.1 AA, hypothèse), Then navigation clavier complète, libellés associés aux champs, messages d'erreur annoncés ; aucune violation sérieuse du contrôle automatisé retenu.
- **A5** Given les formats, Then dates `jj/mm/aaaa` et heures 24 h au fuseau du site ; nombres/GNF via **un utilitaire unique** basé sur `Intl` `fr-FR` (D-23) ; aucun montant au Lot 1.
- **A6** Given une liste vide, une erreur 401/403/404/409/422/429 ou 5xx, Then un message français dédié s'affiche selon le code (table CT-1), sans détail technique.
- **A7** Given un utilisateur non autorisé sur une URL directe, Then la page affichée correspond au code reçu : « introuvable » pour 404, « accès refusé » pour 403.
- **A8** Given l'écran de connexion, Then il comporte les champs code d'espace, e-mail, mot de passe (D-06).
- **Hors Lot 1** : écran conducteur (C-12).

#### US-1.30 — Jeu de données de démonstration fictif (S) — tranche 1c
Commande d'exploitation (CLI), **pas une fonction d'API** (QA-18) ; elle n'est liée à aucun rôle applicatif.
En tant qu'opérateur, je veux charger un jeu de données fictif pour démontrer l'isolation, afin de présenter le produit sans données réelles.
- **A1** Given l'environnement de démonstration, When j'exécute la commande, Then deux tenants fictifs, plusieurs sites (dont un site à décalage UTC non nul pour les tests de fuseau), véhicules, conducteurs, permis, habilitations et affectations sont créés par les mêmes services que l'API, identifiés comme fictifs.
- **A2** Given le jeu de données, Then aucun nom, numéro ou position GPS réel n'y figure (H9) ; contrôle automatisé par liste d'exclusion et domaines/numéros réservés.
- **A3** Given `ENV=production`, Then la commande est refusée (code de sortie non nul) ; le signal est la variable `ENV`.
- **A4** Given une réexécution, Then elle est refusée explicitement ou idempotente (un seul comportement retenu à l'implémentation, testé).
- **A5** Given la commande, Then elle s'exécute avec le rôle applicatif `mf_app` (jamais `mf_owner`) et les actions sont auditées.

---

## 2. Lots 2 à 6 — stories de haut niveau (sans critères détaillés)

Les critères détaillés seront rédigés avant le démarrage de chaque lot, après revue des enseignements du lot précédent. Les identifiants sont provisoires. Reportés des lots antérieurs par D-14/D-16 : idempotence des écritures (lot 4), transition automatique `SUSPENDED` et job de conformité (planificateur, lot 2+), exports, accès support, liaison compte↔conducteur et écran conducteur (lot 4, C-12), relevés de compteurs et documents réglementaires de véhicule (lot 2, C-06), import CSV (lot 2, C-16).

### Lot 2 — Missions et rotations (`dispatch`)
- **US-2.01** En tant que `DISPATCHER`, je veux créer une mission de transport (origine, destination, matière, véhicule affecté, échéance), afin de planifier l'exploitation.
- **US-2.02** En tant que `DISPATCHER`, je veux suivre le cycle de vie d'une mission (planifiée, affectée, en route, chargement, déchargement, terminée, annulée), afin de piloter en temps réel.
- **US-2.03** En tant que `DISPATCHER`, je veux réaffecter ou suspendre une mission quand un véhicule tombe en panne, afin de limiter l'arrêt.
- **US-2.04** En tant que `DISPATCHER`/`OPS_MANAGER`, je veux enregistrer une rotation (cycle chargement-transport-déchargement) avec horodatages, afin de mesurer les temps de cycle.
- **US-2.05** En tant que `OPS_MANAGER`, je veux saisir une pesée avec sa source (pont-bascule ou source approuvée), afin de distinguer un tonnage mesuré d'une estimation ; le GPS n'est jamais une source de tonnage (H10).
- **US-2.06** En tant que `OPS_MANAGER`, je veux corriger une pesée par un événement correctif tracé, afin de conserver l'historique.
- **US-2.07** En tant que `DRIVER`, je veux voir ma mission du jour, afin de savoir quoi faire (sous réserve de la décision C-12 sur l'écran conducteur et l'authentification terrain).
- **US-2.08** En tant que `DIRECTION`, je veux consulter les missions et rotations par site et période, afin de suivre l'activité.
- **US-2.09** En tant que `OPS_MANAGER`, je veux enregistrer des relevés de compteur (kilométrique/horaire) d'un véhicule, afin de suivre l'usage (livraison de `vehicle_meter_reading` avec cette story, D-16).
- **US-2.10** En tant que `OPS_MANAGER`, je veux enregistrer les documents réglementaires d'un véhicule et décider s'ils bloquent l'affectation, afin de respecter la conformité (C-06).

### Lot 3 — Ordres de travail (`maintenance`)
- **US-3.01** En tant que `DRIVER` ou `DISPATCHER`, je veux signaler une panne sur un véhicule, afin de déclencher une prise en charge.
- **US-3.02** En tant que `WORKSHOP_CHIEF`, je veux créer et approuver un ordre de travail, afin d'organiser les interventions.
- **US-3.03** En tant que `WORKSHOP_CHIEF`, je veux assigner un mécanicien, afin de répartir la charge.
- **US-3.04** En tant que `MECHANIC`, je veux consigner diagnostic, constats et temps passé, afin de documenter l'intervention.
- **US-3.05** En tant que `WORKSHOP_CHIEF`, je veux contrôler la qualité et clôturer un OT (remise en service), afin que le véhicule redevienne disponible (`AVAILABLE`).
- **US-3.06** En tant que `DISPATCHER`, je veux voir l'état d'immobilisation et la date prévue de remise en service, afin de replanifier.
- **US-3.07** En tant que `OPS_MANAGER`, je veux mesurer les durées d'immobilisation par véhicule, afin d'identifier les points faibles.
- **US-3.08** En tant que `TENANT_ADMIN`, je veux qu'un véhicule en maintenance soit exclu des affectations et missions, afin d'éviter les erreurs (le refus d'affectation existe déjà au Lot 1 : `VEHICLE_NOT_AVAILABLE`).

### Lot 4 — Checklist mobile hors ligne (PWA)
- **US-4.01** En tant que `DRIVER`, je veux remplir une checklist pré-départ sur téléphone sans réseau, afin de ne pas être bloqué sur site.
- **US-4.02** En tant que `DRIVER`, je veux que ma saisie se synchronise automatiquement au retour du réseau, avec état visible (en attente, envoyé, en échec), afin de ne rien perdre.
- **US-4.03** En tant que `DRIVER`, je veux signaler un défaut critique depuis la checklist, afin de déclencher une demande d'OT (lot 3).
- **US-4.04** En tant que `HSE`, je veux consulter les checklists par véhicule et par période, afin de contrôler leur réalisation.
- **US-4.05** En tant que `TENANT_ADMIN`, je veux paramétrer les modèles de checklist par catégorie de véhicule, afin d'adapter les contrôles.
- **US-4.06** En tant que `DISPATCHER`, je veux voir si la checklist du jour est faite avant le départ, afin d'éviter les départs sans contrôle.
- **US-4.07** En tant que système, je veux gérer doublons, mises à jour tardives et écarts d'horloge à la synchronisation, afin de garantir l'intégrité (introduit `Idempotency-Key` et `idempotency_record`, D-14).
- **US-4.08** En tant que `DRIVER`, je veux que les données stockées localement soient protégées et purgées à la déconnexion, afin de protéger la confidentialité sur téléphone partagé.
- **US-4.09** En tant que `HR`, je veux lier un compte utilisateur à un conducteur, et en tant que `DRIVER` m'authentifier sur le terrain (PIN, QR ou téléphone partagé : C-12), afin d'accéder à mes données propres.

### Lot 5 — GPS via adaptateur simulé (`telematics`)
- **US-5.01** En tant que `TENANT_ADMIN`, je veux associer un traceur (simulé) à un véhicule, afin de recevoir ses événements.
- **US-5.02** En tant que système, je veux ingérer des événements de position via un adaptateur simulé, avec validation des coordonnées, déduplication et tolérance aux événements tardifs.
- **US-5.03** En tant que `DISPATCHER`, je veux voir la dernière position connue d'un véhicule et son ancienneté, afin de piloter.
- **US-5.04** En tant que `OPS_MANAGER`, je veux définir des géofences par site, afin de détecter entrée/sortie de zone (événements marqués comme estimés).
- **US-5.05** En tant que `TENANT_ADMIN`, je veux définir la durée de conservation des positions, afin de respecter les politiques de rétention (à valider juridiquement, C-08, C-09).
- **US-5.06** En tant que `AUDITOR`, je veux voir l'historique des accès aux données de position, afin de contrôler leur usage.
- **US-5.07** En tant qu'opérateur, je veux que l'environnement de démonstration n'utilise que des trajets simulés, afin de ne jamais exposer de données réelles.

### Lot 6 — Dashboard opérationnel (`reporting`)
- **US-6.01** En tant que `DIRECTION`, je veux voir la disponibilité du parc et l'activité par site, afin de piloter globalement.
- **US-6.02** En tant que `DISPATCHER`, je veux voir missions du jour, véhicules disponibles et alertes, afin de réguler.
- **US-6.03** En tant que `OPS_MANAGER`, je veux voir immobilisations et OT ouverts, afin d'arbitrer les priorités.
- **US-6.04** En tant que `HR`/`HSE`, je veux voir les expirations de permis et habilitations à venir, afin d'agir.
- **US-6.05** En tant que tout utilisateur, je veux que chaque indicateur affiche sa source et son statut (mesuré, estimé, saisi), afin d'éviter les mauvaises interprétations.
- **US-6.06** En tant que `FINANCE`, je veux consulter les durées d'immobilisation et d'utilisation (sans coûts au MVP), afin de préparer l'analyse de coûts (post-MVP).
- **US-6.07** En tant qu'utilisateur à portée `SITE`, je veux que le dashboard se limite à mes sites, afin de respecter le moindre privilège.
- **US-6.08** En tant que rôle autorisé, je veux exporter certaines listes (véhicules, conducteurs, affectations, audit) avec journalisation du nombre de lignes et de la finalité (exports reportés, D-16).

---

## 3. Traçabilité des tranches du Lot 1 (D-21)

| Tranche | Contenu | Stories |
|---------|---------|---------|
| **1a — socle** | Repo, compose, CI locale, tenant/site, auth, rôles, audit, RLS, harnais d'isolation, amorçage plateforme | US-1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08, 1.09, 1.10, 1.26, 1.31, 1.32 ; US-1.27 et 1.28 (harnais, étendus à chaque tranche) |
| **1b — référentiels** | Catégories, véhicules, conducteurs, permis, habilitations, masquage | US-1.11 à 1.21 (+ extension de US-1.27/1.28) |
| **1c — affectations, UI, E2E** | Affectations, éligibilité, conformité dérivée, UI minimale complète, accessibilité, démonstration | US-1.22 à 1.25, 1.30 ; US-1.29 (clôture) ; extension de US-1.27/1.28 |

Une revue sécurité et une revue QA ont lieu à la fin de chaque tranche (CLAUDE.md).

## 4. Questions ouvertes

Registre des questions Q1–Q15 (PRD) et Q16–Q26 (ci-dessous). Les décisions `D-nn` et défauts provisoires `C-nn` de `DECISIONS_A_ARBITRER.md` priment. Statut : **Résolue** (décision technique tranchée) ; **Résolue (défaut provisoire)** (valeur provisoire, à confirmer par le client/juriste) ; **Ouverte**.

| ID | Question | Story concernée | Statut |
|----|----------|-----------------|--------|
| Q1–Q15 | Voir `PRD_MVP.md` §14 (statut de chacune y est détaillé) | — | — |
| Q16 | Un même e-mail peut-il appartenir à plusieurs tenants ? | US-1.04, 1.08 | **Résolue** (D-06) : oui, un compte distinct par tenant, e-mail unique par tenant |
| Q17 | Véhicule hors service ou conducteur désactivé avec affectation active ? | US-1.14, 1.21, 1.25 | **Résolue** (D-11, D-12) : refus 409 avec liste ; expiration = conformité dérivée « non conforme » |
| Q18 | Un véhicule `RETIRED` peut-il être réactivé ? | US-1.14, 1.15 | **Résolue (défaut provisoire)** (C-13, D-02) : non, `RETIRED` terminal |
| Q19 | Journaliser les **lectures** de données sensibles (numéro de permis, téléphone) ? | US-1.17 | **Ouverte** : défaut = log technique structuré sans écriture d'audit sur GET ; exclue des tests automatiques |
| Q20 | Visibilité d'une affectation inter-sites pour un rôle `SITE` ? | US-1.24 | **Résolue** (D-13) : sans objet, même site obligatoire |
| Q21 | Seuil de préavis d'expiration par défaut et paramétrage | US-1.18, 1.20 | **Ouverte** : paramètre `EXPIRY_WARNING_DAYS` par tenant, valeur par défaut à arbitrer avec le client |
| Q22 | Durée d'invitation, politique de mot de passe, seuils de verrouillage (N) | US-1.04, 1.05, 1.08 | **Ouverte** : clés nommées en 0.5, valeurs par `security-engineer` ; MFA reportée après Lot 1 (C-03) |
| Q23 | `HSE` écrit-il les habilitations ? | US-1.19 | **Résolue** (D-10) : lecture seule, écriture reportée |
| Q24 | Types d'habilitations requis et sources réglementaires | US-1.19, PRD Q3 | **Ouverte** (C-07) : valeurs fictives marquées « à valider localement » |
| Q25 | Plusieurs véhicules le même jour par conducteur ? | US-1.22 | **Résolue (défaut provisoire)** (C-11) : affectations contiguës manuelles non chevauchantes, pas de notion de poste |
| Q26 | Accès support de `PLATFORM_ADMIN` aux données d'un tenant ? | US-1.01 | **Résolue (défaut provisoire)** (C-10, D-16) : aucun accès support au Lot 1 |

Nouvelles hypothèses introduites lors de cette révision, à confirmer : interdiction d'auto-désactivation (US-1.07 A3) ; unicité de l'immatriculation y compris sur véhicules `RETIRED` (US-1.12 A2) ; portée `TENANT` seule du journal d'audit (US-1.26 A5) ; code 422 `IF_MATCH_REQUIRED` pour `If-Match` absent (CT-4) ; code 422 `REFERENCE_NOT_FOUND` pour une référence étrangère dans le corps (CT-1, proposition QA-03 ; D-05 ne le précise pas) ; code 422 `ROLE_NOT_ASSIGNABLE` (MATRICE_RBAC §4.2.2 mentionnait 400/403).

Écarts au socle proposés (non appliqués) : voir `docs/PRD_MVP.md`, section 13 (E1–E7, révisés) ; l'entité `invitation` est remplacée par `account_token` (`MODELE_PHYSIQUE_LOT1.md`), `idempotency_record` est retirée du Lot 1 (D-14).
