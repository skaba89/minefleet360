# Matrice RBAC — MINEFLEET 360 (Lot 1)

> Statut : **cadrage (phase 0), révisé après revue croisée** le 2026-10-25. Rien ici n'est implémenté ni testé : le dépôt ne contient aucun code (voir `00_SOCLE_CADRAGE.md` §1).
> Préséance : `DECISIONS_A_ARBITRER.md` > `MODELE_PHYSIQUE_LOT1.md` > ce document. Décisions appliquées ici : **D-01** (énumérations en anglais), **D-05** (codes HTTP), **D-06/D-07** (connexion, tenant plateforme), **D-09** (source de vérité YAML), **D-10** (arbitrages RBAC), **D-11/D-13** (cycle de vie, même site), **D-15** (minimisation), **D-16** (hors lot 1), **D-18** (référentiels), **D-21** (tranches 1a/1b/1c).
> Conventions reprises du socle : hypothèses **H1-H10**, 14 codes de rôles (§3 du socle), modules et entités (§4-5).
> Distinction : **[Fait]** = issu des documents du dépôt ou d'une décision tranchée ; **[Proposé]** = choix de conception de ce document ; **[À valider]** = dépend du client ou d'un juriste (défauts provisoires C-01..C-17).

---

## 1. Modèle d'autorisation

### 1.1 Principes
1. **Permissions fines** nommées `module.ressource.action` (anglais, `snake_case`), ex. `fleet.vehicle.read`, `assignment.vehicle_assignment.create`, `audit.event.read`. Les modules sont ceux du socle ; les ressources sont les entités du socle.
2. **Rôle = ensemble de permissions** (catalogue global `role`, D-18). Un utilisateur reçoit un rôle via `user_role_assignment` avec une **portée** (H7), contrainte en base par `role_allowed_scope` :
   - `PLATFORM` : réservée au tenant plateforme (`kind = 'PLATFORM'`, D-07) ;
   - `TENANT` : tous les sites du tenant ;
   - `SITE` : un site précis (`site_id` obligatoire).
   Un utilisateur peut cumuler plusieurs affectations de portées différentes : la portée dépend de la **permission**, par **union** des affectations actives qui portent cette permission (DB-40).
3. **Deny-by-default** : toute route, toute action, tout champ sensible est refusé tant qu'une permission explicite ne l'autorise pas. Une route sans permission déclarée est un défaut de build (test ST-01 dans `MENACES_ET_CONTROLES.md`).
4. **Autorisation côté serveur uniquement.** Masquer un bouton dans l'UI n'est jamais un contrôle d'accès. Le masquage de champs (§5) est appliqué **dans la couche de sérialisation de l'API** ; une valeur masquée n'est jamais envoyée au navigateur.
5. **Le tenant n'est jamais fourni par le client.** `tenant_id` est déduit de la session authentifiée ; tout `tenant_id` dans un corps, une URL ou un en-tête est rejeté (`422`, schémas `extra="forbid"`, H1, H3).
6. **Décision d'accès — table ordonnée unique (D-05).** Pour une requête de l'utilisateur U sur une permission P (et une ressource R si la route en désigne une), les étapes sont évaluées **dans cet ordre** ; la première qui échoue fixe la réponse :

   | # | Condition d'échec | Code | Corps / remarque |
   |---|-------------------|------|------------------|
   | 1 | Jeton absent, invalide, expiré, session révoquée, compte désactivé, tenant suspendu | **401** | Corps identique quelle que soit la cause (QA-30) |
   | 2 | U n'a **aucune** affectation de rôle active (non expirée, non révoquée) portant P, **toutes portées confondues** | **403** | Évalué **avant** de chercher R : ne révèle ni l'existence de R ni son tenant. Audité (`outcome = DENIED`) |
   | 3 | R inexistante, **ou** d'un autre tenant, **ou** hors portée de site de U pour P, **ou** règle d'objet « propriétaire » non satisfaite | **404** | Corps et en-têtes identiques à « UUID inexistant ». Autre tenant : événement de sécurité en log structuré (pas d'audit tenant) |
   | 4 | Référence dans le corps (`site_id`, `category_id`, `driver_id`…) inexistante, d'un autre tenant ou hors portée | **422** `REFERENCE_NOT_FOUND` | Indiscernable inexistant/étranger |
   | 5 | Format invalide, champ inconnu, règle métier violée (éligibilité, auto-escalade, rôle non attribuable…) | **422** + `code` stable | ex. `DRIVER_LICENSE_EXPIRED`, `SELF_ROLE_CHANGE_FORBIDDEN`, `ROLE_NOT_ASSIGNABLE` |
   | 6 | Conflit d'état : chevauchement, unicité, `row_version` obsolète (`If-Match`), transition refusée (D-11), dernier `TENANT_ADMIN` | **409** + `code` stable | ex. `VEHICLE_ASSIGNMENT_OVERLAP`, `LAST_TENANT_ADMIN` |
   | 7 | Limitation de débit | **429** + `Retry-After` | |

   Conséquences : (a) une affectation de rôle `TENANT` d'un rôle marqué 🔶 **ne porte pas** la permission → étape 2 → **403** ; (b) une affectation `SITE` sur A1 qui porte la permission, appliquée à une ressource de A2 → étape 3 → **404** ; (c) sur un **endpoint de collection**, étape 2 → 403, sinon liste filtrée par portée (jamais 404) ; (d) un utilisateur sans permission reçoit 403 même pour une ressource d'un autre tenant : c'est le même code que pour une ressource de son tenant, aucune fuite. Les `403` sont audités ; les `404` « autre tenant » sont comptés par métrique et journalisés ; leur audit tenant n'est pas fait (pas de saturation du journal par sondage d'UUID, QA-03/QA-10). **Précision [Proposé]** : la formulation de D-05 (« 403 sur une ressource visible ou sur un endpoint de collection ») est lue comme « 403 avant toute recherche de la ressource », ce qui donne un oracle unique.
7. **Effet immédiat des révocations** : retrait de rôle → `403` dès la requête suivante (la session reste valide) ; désactivation de compte, révocation de session ou suspension du tenant → `401`. Mécanisme : `auth_session.revoked_at` vérifié en base, **pas** de « version de jeton » (DB-33).
8. **Séparation des tâches (D-10)** : `TENANT_ADMIN` configure (comptes, rôles, sites, référentiels) et **ne lit aucune donnée personnelle de conducteur** ; `HR` gère les personnes, elle ne gère ni comptes ni rôles ; `HSE` lit sans écrire ; `PLATFORM_ADMIN` n'accède à aucune donnée métier.

### 1.2 Légende de la matrice
| Symbole | Sens |
|---------|------|
| ✅ | Autorisé, dans la portée de l'affectation (`TENANT` ou `SITE`, selon ce que l'administrateur a configuré). |
| 🔶 | Autorisé **uniquement avec une affectation de portée `SITE`** : une affectation `TENANT` de ce rôle ne porte pas la permission (→ 403, étape 2). Sur un autre site que celui de l'affectation → 404 (étape 3). |
| 👁 | **Lecture restreinte** : champs masqués côté serveur (§5). Se combine : 👁🔶. |
| ❌ | Refusé (→ 403). |
| ⏭ | **Lot ultérieur** : la permission n'est pas déclarée dans `authz_matrix.yaml` au lot 1 et aucune route n'existe (§2.7). |
| ¹ … | Voir note numérotée sous le tableau. |

Colonnes (ordre fixe, codes du socle) : **PA** `PLATFORM_ADMIN` · **TA** `TENANT_ADMIN` · **DIR** `DIRECTION` · **OPS** `OPS_MANAGER` · **DISP** `DISPATCHER` · **HR** `HR` · **DRV** `DRIVER` · **WSC** `WORKSHOP_CHIEF` · **MEC** `MECHANIC` · **STK** `STOREKEEPER` · **FUEL** `FUEL_MANAGER` · **HSE** `HSE` · **FIN** `FINANCE` · **AUD** `AUDITOR` (retenu, rôle optionnel en lecture seule, D-10).

**Rôle `DRIVER` au lot 1** : il n'existe ni liaison compte↔conducteur ni écran conducteur (D-16, C-12). Le rôle est au catalogue (portée `SITE` seule) mais **ne porte, au lot 1, que les permissions « propre compte »** (`identity.user.update_self`, `identity.session.revoke_own`, `organization.tenant.read`) ; toutes ses cellules « propre » sont ⏭. [Proposé]

### 1.3 Connexion et identité plateforme (D-06, D-07)
- **Connexion** = *code d'espace de travail* (= `tenant.code`, porté par l'URL ou saisi) + e-mail + mot de passe. E-mail unique **par tenant** (`citext`). Le code d'espace n'est jamais déduit de l'e-mail.
- **Réponse identique** : code d'espace inconnu, e-mail inconnu, mot de passe faux, compte `INVITED`/`DISABLED`, tenant `SUSPENDED`/`ARCHIVED`, compte verrouillé → **un seul** `401` `INVALID_CREDENTIALS` (même corps, mêmes en-têtes, temps de traitement comparable : hachage factice pour un compte inconnu). Le `429` de limitation s'applique au triplet soumis, identiquement pour des identifiants inexistants.
- **Résolution du tenant avant authentification** par code exact, via `app.login_tenant_code` (politique de lecture sur `tenant` limitée à la ligne du code exact), **sans `BYPASSRLS`** (`MODELE_PHYSIQUE_LOT1.md` §6.2).
- **Tenant plateforme réservé** (`kind = 'PLATFORM'`, code `mf-platform`, un seul) : `tenant_id NOT NULL` partout ; `PLATFORM_ADMIN` n'existe que dans ce tenant (portée `PLATFORM`) ; point d'entrée de connexion distinct, code fixé côté serveur ; le code `mf-platform` et une liste de codes réservés sont **refusés à la création d'un tenant client** (`422` `TENANT_CODE_RESERVED`) [Proposé]. Aucune API tenant ne peut attribuer un rôle de portée `PLATFORM` (FK `(role_code, scope_type)` + FK `(tenant_id, tenant_kind)`).

---

## 2. Matrice détaillée — Lot 1

> Source de vérité machine : `authz_matrix.yaml` (créé au lot 1a, format au §7). Ce tableau en est la **vue humaine** ; les tests d'autorisation (ST-02) sont **générés** depuis le YAML. Un test de cohérence compare les deux (§7.4).
> Tranche (D-21) : §2.1, §2.2, §2.6 = **1a** ; §2.3, §2.4 = **1b** ; §2.5 = **1c**.

### 2.1 `organization` (1a)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `organization.tenant.create` | ✅¹ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `organization.tenant.suspend` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `organization.tenant.read` (nom, fuseau, langue) | 👁¹ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `organization.tenant.update` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `organization.site.read` | ❌ | ✅ | ✅ | ✅ | 🔶 | ✅ | 🔶 | 🔶 | 🔶 | 🔶 | 🔶 | ✅ | ✅ | ✅ |
| `organization.site.create` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `organization.site.update` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `organization.site.deactivate` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

¹ `PLATFORM_ADMIN` : `tenant.create` inclut, dans la même transaction auditée, la création du premier `TENANT_ADMIN` invité, des sites initiaux et la **copie des catégories de véhicule et de permis** du référentiel global vers le tenant (D-18) ; il n'y a donc pas de permission `identity.user.create` pour `PA` (QA-18). `tenant.read` pour `PA` : métadonnées de gestion uniquement (identifiant, code, statut, dates, volumétrie agrégée) ; jamais de donnée métier.

### 2.2 `identity` (1a)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `identity.user.read` | ❌ | ✅ | ❌ | ❌ | ❌ | 👁² | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 👁² |
| `identity.user.create` (invitation) | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.user.update` | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.user.deactivate` | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.user.reset_credentials` (déclenchée par l'administrateur) | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.user.reset_mfa` (retrait du second facteur d'un autre compte, D-40) | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.user.update_self` (profil, mot de passe) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `identity.role.read` (catalogue **global**, D-18) | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `identity.role_assignment.read` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `identity.role_assignment.create` | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.role_assignment.revoke` (révocation, pas de suppression physique) | ❌ | ✅³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `identity.session.revoke_own` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `identity.session.revoke_any` (dans le tenant) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

² 👁 sur `user_account` : nom d'affichage, rôle, statut, site ; **masqués** : e-mail, téléphone, adresses IP et agents utilisateurs de session, secrets. Les IP/agents appartiennent à `auth_session` (DB-33), pas au compte.
³ Contraintes anti-escalade obligatoires — voir §4.2.
Les routes de réinitialisation **en libre-service** (`/auth/password/reset-request`, `/reset-confirm`) et d'activation d'invitation sont **publiques** (liste blanche ST-01), sans permission.

### 2.3 `fleet` (1b)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `fleet.vehicle.read` | ❌ | ✅ | ✅ | ✅ | 🔶 | ❌ | ⏭ | 🔶 | 🔶 | 👁🔶⁵ | 🔶 | ✅ | ✅ | ✅ |
| `fleet.vehicle.create` | ❌ | ✅⁴ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.vehicle.update` | ❌ | ✅⁴ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.vehicle.update_status` | ❌ | ✅ | ❌ | ✅ | 🔶 | ❌ | ❌ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.vehicle.deactivate` (passage à `RETIRED`, terminal, C-13) | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.meter.read`, `fleet.document.read` (2c) | ❌ | ✅ | ✅ | ✅ | 🔶 | ❌ | ❌ | 🔶 | 🔶 | 🔶 | 🔶 | ✅ | ✅ | ✅ |
| `fleet.meter.record` (2c) | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ❌ | 🔶 | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.meter.reset` (2c : remise à zéro, D-43) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.document.manage` (2c : ajout, retrait ; documents immuables) | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `fleet.vehicle_category.manage` (2c : documents exigés par catégorie, D-42) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fleet.vehicle_category.read` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `fleet.vehicle_category.manage` | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

⁴ `TENANT_ADMIN` crée/modifie les véhicules (chargement initial du parc, l'import CSV étant hors lot 1, C-16) ; D-10 le laisse gérer les « référentiels » et ne lui retire que les données personnelles de conducteur. [Proposé, à confirmer]
⁵ `STOREKEEPER` : identification technique (marque, modèle, numéro de série) ; masqués : coûts d'acquisition, boîtier GPS, affectation nominative.
Statut : tout passage de `fleet.vehicle.update_status`/`deactivate` vers `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE` ou `RETIRED` est refusé en **409** `VEHICLE_HAS_OPEN_ASSIGNMENTS` tant qu'une affectation `PLANNED`/`ACTIVE` existe (D-11) ; la réponse liste les affectations à clôturer.

### 2.4 `workforce` (1b)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `workforce.driver.read` (matricule, nom, prénom, site, statut, catégories) | ❌ | ❌ | 👁⁷ | 👁⁷ | 👁🔶⁷ | ✅ | ⏭ | 👁🔶⁷ | ❌ | ❌ | 👁🔶⁷ | 👁⁷ | ❌ | 👁⁷ |
| `workforce.driver.read_sensitive` (téléphone ; **seule donnée** concernée au lot 1, D-15) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver.create` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver.update` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver.deactivate` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver_license.read` (catégorie, statut, échéance ; n° absent) | ❌ | ❌ | ❌ | 👁⁹ | 👁🔶⁹ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | 👁⁹ | ❌ | 👁⁹ |
| `workforce.driver_license.read_number` (n° de permis en clair) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver_license.manage` (créer/modifier) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workforce.driver_qualification.read` | ❌ | ❌ | ✅ | ✅ | 🔶 | ✅ | ⏭ | 🔶 | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| `workforce.driver_qualification.manage` (accorder/modifier) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌¹⁰ | ❌ | ❌ |
| `workforce.driver_qualification.revoke` (suspendre/retirer) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌¹⁰ | ❌ | ❌ |

⁷ 👁 `driver` : visibles **matricule, nom, prénom, site de rattachement, statut, catégories d'engins autorisées**. **Masqués (clé absente de la réponse)** : téléphone, n° de permis, motif de suspension. `DISP`, `WSC`, `FUEL` : uniquement les conducteurs de leur site. Pas de date de naissance, adresse, pièce d'identité, aptitude médicale ni motif maladie : **ces données ne sont pas collectées au lot 1** (D-15).
⁹ 👁 `driver_license` : catégorie, **statut de validité dérivé** des dates (`VALID`/`SUSPENDED`/`WITHDRAWN` stocké + « expire bientôt/expiré » dérivé, D-03), date d'échéance. **Le n° de permis est totalement absent** de la réponse pour tout rôle autre que `HR` : pas d'affichage partiel (D-15).
¹⁰ Résolu par D-10 : `HR` écrit conducteurs, permis et habilitations ; `HSE` **lecture seule** (écriture reportée). [Fait]
`TENANT_ADMIN` : **aucune** permission `workforce.*` ni lecture des affectations nominatives (D-10) ; il ne peut donc lire aucun nom, matricule ni téléphone de conducteur.
Statut conducteur : passage en non-`ACTIVE` refusé en **409** `DRIVER_HAS_OPEN_ASSIGNMENTS` tant qu'une affectation `PLANNED`/`ACTIVE` existe (D-11). Le champ `user_account_id` du conducteur **n'est pas écrivable** au lot 1 (liaison ⏭, `422` si fourni).

### 2.5 `assignment` (1c)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `assignment.vehicle_assignment.read` | ❌ | ❌ | ✅ | ✅ | 🔶 | ✅ | ⏭ | 🔶 | ❌ | ❌ | 🔶 | ✅ | ⏭ | ✅ |
| `assignment.vehicle_assignment.create` | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `assignment.vehicle_assignment.update` (avant démarrage) | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `assignment.vehicle_assignment.end` (clôture) | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

Règles (D-04, D-13) : `OPS_MANAGER` en portée `TENANT` ou `SITE` ; `DISPATCHER` **en portée `SITE` uniquement** (D-10). Véhicule, conducteur et affectation sont du **même site** (sinon `422` `ASSIGNMENT_SITE_MISMATCH`) ; pas d'antidatage au-delà de la tolérance configurable (`422` `ASSIGNMENT_BACKDATED`) ; éligibilité stricte, **sans dérogation** (`422` `DRIVER_LICENSE_EXPIRED`, `DRIVER_QUALIFICATION_MISSING`, `VEHICLE_NOT_AVAILABLE`…) ; chevauchement → `409`. `TENANT_ADMIN` : ❌ (D-10, données de conducteur). `FIN` : ⏭ (valorisation de coûts, pseudonymisation reportées avec le module coûts).

### 2.5 bis `dispatch` (lot 2a, `PLAN_LOT2.md` §5)
| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dispatch.location.read`, `dispatch.material.read` | ❌ | ✅ | ✅ | ✅ | 🔶 | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `dispatch.location.manage` | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dispatch.material.manage` (portée société seulement) | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dispatch.mission.read` | ❌ | ❌ | ✅ | ✅ | 🔶 | ❌ | ⏭ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `dispatch.mission.create`, `dispatch.mission.progress` | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dispatch.weighing.read`, `dispatch.indicators.read` (2b) | ❌ | ❌ | ✅ | ✅ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `dispatch.weighing.record` (2b) | ❌ | ❌ | ❌ | ✅ | 🔶 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dispatch.weighing.approve`, `dispatch.weighing.correct` (2b) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

Pesées (2b) : une saisie manuelle dégradée est approuvée par une **autre personne** que celle qui l'a saisie (séparation des tâches, RM-075) ; les réponses de pesée ne contiennent aucune donnée nominative de conducteur.
`TENANT_ADMIN` gère les référentiels mais ne lit pas les missions (données nominatives conducteur, D-10).
Le **nom et l'identifiant du conducteur** d'une mission suivent `assignment.vehicle_assignment.read` sur le site de la mission, pas `dispatch.mission.read` (revue L2A-R-02) : `FINANCE` et un `WORKSHOP_CHIEF` hors de son site lisent la mission avec ces deux champs à `null`. `DRIVER` : sa propre mission au lot 4 (écran conducteur, C-12).

### 2.6 `audit` (1a)
Il n'existe **aucune permission d'écriture, de modification ou de suppression** sur `audit_event` exposée par l'API : l'écriture est un effet interne des autres modules ; le journal est append-only (T-21), partitionné par mois dès la migration 0001 (D-17).

| Permission | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `audit.event.read` (journal du tenant) | ❌ | ✅ | ❌¹¹ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

¹¹ D-10 : lisible par `TENANT_ADMIN` et `AUDITOR` seulement. `DIRECTION` : ❌ par défaut ; un accès restreint aux événements de sécurité reste un point ouvert (§6). `PLATFORM_ADMIN` : ❌.
Le contenu `before_data`/`after_data` ne contient jamais de champ sensible ; seuls les **noms** des champs modifiés sont journalisés (`changed_fields`, T-46).

### 2.7 Permissions retirées du lot 1 — « lot ultérieur » (D-13, D-16)
Aucune de ces permissions n'est déclarée dans `authz_matrix.yaml` au lot 1, aucune route ne l'expose ; ST-01 échoue si une route correspondante apparaît. Les menaces associées restent au registre (`MENACES_ET_CONTROLES.md`), leurs contrôles sont déplacés vers le lot cible.

| Permission(s) | Raison | Lot cible / décision |
|---------------|--------|----------------------|
| `fleet.vehicle.export`, `workforce.driver.export`, `assignment.vehicle_assignment.export`, `audit.event.export` | Exports hors lot 1 (D-16) | Ultérieur ; reprendre la matrice de l'ancienne version : `driver.export` = `HR` seul ; exports audités avec nombre de lignes et finalité |
| `identity.support_access.request`, `.approve`, `.read` ; session de support | Pas d'accès support au lot 1 (D-16, C-10) | Avant pilote |
| `identity.platform_admin.manage` | Pas d'API de gestion des `PLATFORM_ADMIN` : le premier est créé par **commande d'exploitation** (secret fourni par variable d'environnement, jamais en dur) [Proposé] | Ultérieur (double validation) |
| `workforce.driver.link_account` ; routes `/drivers/me`, `/vehicle-assignments/me` ; cellules « propre » de `DRV` | Liaison compte↔conducteur et écran conducteur hors lot 1 (D-16, C-12) | Lot 4 |
| `assignment.vehicle_assignment.override_eligibility` | Dérogation d'éligibilité reportée (D-13) | Ultérieur (justification + audit dédié + notification `HSE`) |
| `audit.integrity.verify` | Chaînage de hash en ligne exclu ; **scellement asynchrone** ultérieur (D-16, DB-20) | Lot 1.x |
| `audit.data_access.read_own` | Dépend de la journalisation des lectures et de la liaison compte↔conducteur | Ultérieur |
| Lecture des affectations par `FIN` (pseudonymisée) | Module coûts absent | Lot 2+ |

---

## 3. Matrice haut niveau — modules futurs (hors Lot 1)

> Indicatif, à détailler à l'ouverture de chaque lot. Légende : **L** lecture · **É** écriture/création · **A** approbation/validation · **—** aucun accès. Pour les rôles de terrain (DISP, WSC, MEC, STK, FUEL, DRV) la portée par défaut est `SITE`. `PLATFORM_ADMIN` : « — » partout. `AUDITOR` : L partout où l'accès est légitime, jamais É. `TA` : « — » pour toute donnée personnelle de salarié (D-10).

| Module | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|--------|----|-----|-----|------|----|-----|-----|-----|-----|------|-----|-----|-----|
| `dispatch` (missions, rotations) | — | L | É A | É | — | L (propre) É (statut) | L | — | — | L | L | L | L |
| `maintenance` (ordres de travail) | — | L | L | L | — | É (signalement panne) | É A | É | L | — | L | L (coûts) | L |
| `inventory` (pièces, pneus) | — | L | L | — | — | — | L É (demande) | É (demande) | É A | L | — | L (valorisation) | L |
| `fuel` (cuves, bons, dotations) | — | L | L | L | — | L (propre) | — | — | — | É A | L | L | L |
| `telematics` (positions GPS) | — | L (agrégé) | L (agrégé) | L (temps réel, site, horaires de service) | — | L (propre) | — | — | — | — | L (événements sécurité) | — | L (accès tracé) |
| `hse` (incidents, contrôles) | — | L | L | L | L | É (signalement) | L | L | — | — | É A | — | L |
| `contracts` (sous-traitants) | — | L | L | — | — | — | — | — | — | — | L | É A | L |
| `finance` (coûts, rentabilité) | — | L | L (son périmètre) | — | — | — | — | — | — | — | — | É A | L |
| `reporting` | — | L | L | L (site) | L (RH) | — | L | — | — | L | L | L | L |

Points de vigilance transverses (détaillés dans `MENACES_ET_CONTROLES.md`) :
- **`telematics`** : historique de positions nominatif = donnée sensible de salarié ; accès au temps réel limité au site et aux horaires de service ; l'historique nominatif exige une finalité et est tracé (T-31). Aucune donnée GPS réelle en développement (C-08).
- **Tonnage** : aucune permission ne permet de saisir un tonnage « mesuré » à partir du GPS (H10) ; seul un rôle d'intégration pont-bascule ou une source approuvée écrit une charge mesurée.
- **Sous-traitants / portail client (Phase 3)** : comptes externes dans un modèle d'accès contractualisé distinct, jamais des rôles internes élargis (T-42).

---

## 4. Règles particulières

### 4.1 `PLATFORM_ADMIN` : aucune donnée métier, aucun accès support au lot 1
- Le `PLATFORM_ADMIN` (éditeur) vit dans le **tenant plateforme** (D-07). Il peut : créer/suspendre un tenant, voir des métadonnées de gestion, gérer la plateforme. Il n'a **aucune** permission sur les entités métier d'un tenant (colonnes « PA » = ❌) : toute tentative → `403` (étape 2 de §1.1.6), auditée.
- **Aucune session de support au lot 1** (D-16, C-10, DB-21) : il n'existe aucun chemin applicatif du `PLATFORM_ADMIN` vers les données métier. Le risque résiduel est l'accès direct à la base par l'exploitation (T-12, contrôles Ops).
- *Conception cible, à reprendre avant le pilote* [Proposé] : session dédiée, justifiée (motif, ticket, périmètre), approuvée par un `TENANT_ADMIN` du tenant, courte (4 h non renouvelable), lecture seule par défaut, `support_session_id` dans chaque événement d'audit, session visible du tenant, expiration côté serveur, aucune donnée RH accessible sauf approbation explicite, aucun export massif. Variante « bris de glace » à deux `PLATFORM_ADMIN` seulement si le contrat le prévoit [À arbitrer].
- MFA TOTP obligatoire pour `PLATFORM_ADMIN` avant le pilote (C-03) ; le premier `PLATFORM_ADMIN` est créé par une commande d'exploitation, le seed de démonstration est un script refusant `ENV=production` et s'exécutant avec le rôle applicatif, non propriétaire (QA-18).

### 4.2 `TENANT_ADMIN` : pas d'auto-escalade, pas de création de `PLATFORM_ADMIN`
Contraintes serveur sur `identity.role_assignment.create/revoke`, `identity.user.update` et dérivés (codes selon D-05) :
1. Un utilisateur **ne peut pas modifier ses propres affectations de rôle** (ni s'ajouter, ni se retirer un rôle) : **422** `SELF_ROLE_CHANGE_FORBIDDEN`, audité en événement de sécurité. Cette règle est évaluée **avant** celle du dernier administrateur.
2. Le rôle `PLATFORM_ADMIN` (portée `PLATFORM`) **n'est pas attribuable** dans un tenant client : **422** `ROLE_NOT_ASSIGNABLE`, audité en événement de sécurité. `GET /roles` renvoie à un `TENANT_ADMIN` uniquement les rôles attribuables dans son tenant (filtrés par `role_allowed_scope` et `tenant_kind`) : `PLATFORM_ADMIN` n'y figure pas, et toute tentative d'attribution directe est refusée comme ci-dessus.
3. Un `TENANT_ADMIN` n'attribue que des rôles du catalogue, **uniquement dans son tenant** et sur des sites de son tenant (clés composites H3) ; site d'un autre tenant → **422** `REFERENCE_NOT_FOUND`.
4. **Dernier `TENANT_ADMIN` actif** : ne peut être ni désactivé ni dégradé par un autre administrateur : **409** `LAST_TENANT_ADMIN`. La reprise en cas de verrouillage relève d'une **procédure d'exploitation tracée hors API** (le `PLATFORM_ADMIN` n'a pas de permission métier) [Proposé].
5. L'attribution de `TENANT_ADMIN` et de `HR` génère un **événement d'audit à criticité élevée** ; l'**alerte de notification** au titulaire existant et la double validation sont reportées (aucun mécanisme de notification au lot 1) [Proposé, à arbitrer].
6. Un `TENANT_ADMIN` **ne lit pas** les données personnelles de conducteur (D-10) : le risque résiduel est qu'il se donne un second compte avec le rôle `HR` ; il est traité par la règle 5 (audit à criticité élevée, revue périodique), la séparation parfaite étant impossible pour un administrateur de tenant. La liaison compte↔conducteur étant hors lot 1, le contournement par auto-liaison n'existe pas.
7. Les champs de session (`tenant_id`, `roles`, `scopes`) viennent du serveur ; le corps de requête ne peut jamais les définir (mass assignment interdit : schémas Pydantic en `extra="forbid"` → **422**).
8. Les révocations (`role_assignment`, `session`) sont des **actions** `POST .../revoke`, jamais des `DELETE` physiques (D-19, QA-26).

### 4.3 `DRIVER` : uniquement ses propres données (lot 4)
*Conception cible ; rien de ceci n'est livré au lot 1 (D-16, C-12).*
- Règle d'objet « propriétaire » : l'accès passe par `driver_id` lié au compte ; aucun paramètre `driver_id` fourni par le client n'est utilisé pour les routes « moi ».
- Un `DRIVER` ne voit ni les autres conducteurs, ni leur position, ni leur classement.
- Il n'a **pas** de permission de collection (`workforce.driver.read`) : `GET /drivers` → **403** ; un objet d'autrui → **404**.
- Au lot 1, un compte `DRIVER` n'ouvre aucune donnée métier : toute route métier → **403**.

### 4.4 Données personnelles : masquage total côté serveur (D-15)
- Téléphone et n° de permis : lisibles par `HR` seul (`read_sensitive`, `read_number`). **Tous les autres rôles** reçoivent le champ **absent de la réponse** (clé non présente, déclarée optionnelle dans OpenAPI) ; pas d'affichage partiel, pas de valeur factice.
- Les valeurs masquées ne sont jamais envoyées au navigateur ni écrites dans les journaux ou l'audit (marqueur « champ modifié » seulement, T-40/T-46).
- Les paramètres de filtre, tri et recherche ne permettent pas de **déduire** une valeur masquée : filtrer ou trier par un champ masqué est refusé en **422** `FIELD_NOT_ALLOWED` pour les rôles non autorisés.
- Pas de date de naissance, adresse, pièce d'identité, aptitude médicale ni motif maladie au lot 1 ; leur ajout est une migration ultérieure conditionnée à l'avis du juriste (C-08).
- Les exports sont hors lot 1 (§2.7).

### 4.5 Autres règles
- **Cloisonnement par site** : un rôle `SITE` ne voit pas les ressources des autres sites, y compris par recherche, comptage ou clé étrangère (T-07) : `404` sur objet, filtrage sur collection.
- **Affectations** : la création vérifie côté serveur que véhicule et conducteur sont dans la portée de l'acteur, du même tenant **et du même site** (D-13), que le conducteur est éligible (permis et habilitation valides à la date de début, conformité **calculée à la lecture**, D-12), qu'aucun chevauchement n'existe (contrainte `EXCLUDE USING gist`, D-04) et qu'il n'y a pas d'antidatage. Horloge **injectable** obligatoire dans le code (D-12, D-23).
- **Entités sans site** : une entité sans `site_id` (ex. référentiel) est traitée comme niveau tenant ; ses droits d'écriture exigent une portée `TENANT`.
- **Concurrence** (D-19) : toute mise à jour exige `If-Match` (ETag = `row_version`) ; absent → **422** `IF_MATCH_REQUIRED` ; obsolète → **409** `ROW_VERSION_STALE`.
- **Référentiels** (D-18) : `role` et `permission` sont un catalogue système global en lecture seule ; catégories de véhicule et de permis sont **copiées par tenant** à la création du tenant ; leur gestion (`vehicle_category.manage`) ne touche que la copie du tenant.

---

## 5. Matrice d'autorisation des données — colonnes sensibles

Légende : **✅** en clair · **👁** restreint (règle précisée) · **❌** absent de la réponse · **⏭** lot ultérieur.
`PA` = ❌ partout (aucun accès support au lot 1). Hors lecture, l'écriture suit la matrice §2.

| Donnée (entité.colonne) | Sensibilité | PA | TA | DIR | OPS | DISP | HR | DRV | WSC | MEC | STK | FUEL | HSE | FIN | AUD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `driver.phone` | Personnelle | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `driver.suspension_reason_code` | Sensible (RH) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `driver.employee_number`, `last_name`, `first_name` | Personnelle (courante) | ❌ | ❌ | 👁 | ✅ | 👁 site | ✅ | ⏭ | 👁 site | ❌ | ❌ | 👁 site | ✅ | ❌ | 👁 |
| `driver.status`, `unavailability_reason` (`LEAVE`/`TRAINING`/`OTHER`), `site_id` | Opérationnelle | ❌ | ❌ | ✅ | ✅ | ✅ site | ✅ | ⏭ | ✅ site | ❌ | ❌ | ✅ site | ✅ | ❌ | ✅ |
| `driver.hire_date`, `exit_date`, `employment_type` | Personnelle (RH) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `driver_license.number` | Personnelle | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `driver_license.category`, `status`, `expires_on` | Opérationnelle | ❌ | ❌ | ❌ | ✅ | ✅ site | ✅ | ⏭ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| `driver_qualification.*` (engin, statut, validité) | Opérationnelle | ❌ | ❌ | ✅ | ✅ | ✅ site | ✅ | ⏭ | ✅ site | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| Date de naissance, adresse, pièce d'identité, aptitude médicale, motif maladie, `notes_hr`, sanctions, scan de permis | Très sensible | **Non collectés au lot 1** (D-15, C-08) ; tout ajout ultérieur : décision juridique préalable et migration dédiée | | | | | | | | | | | | | |
| `user_account.email`, `phone` | Personnelle | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `auth_session.ip_address`, `user_agent` | Technique/perso | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ⏭ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `user_account.password_hash`, secrets MFA, jetons, hachages de refresh | Secret | ❌ **jamais exposé par aucune API** | | | | | | | | | | | | | |
| `vehicle.purchase_cost`, valeur (futur) | Financière | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| `vehicle.gps_device_id` / identifiant boîtier (futur) | Technique | ❌ | ✅ | ❌ | ✅ | ✅ site | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `vehicle.registration_number`, `fleet_number`, modèle, catégorie, statut | Opérationnelle | ❌ | ✅ | ✅ | ✅ | ✅ site | ❌ | ⏭ | ✅ site | ✅ site | 👁 site | ✅ site | ✅ | ✅ | ✅ |
| `vehicle_assignment.driver_id` (identité du conducteur affecté) | Personnelle (courante) | ❌ | ❌ | ✅ | ✅ | ✅ site | ✅ | ⏭ | ✅ site | ❌ | ❌ | ✅ site | ✅ | ⏭ | ✅ |
| `audit_event.actor_user_id`, `action`, `entity_type`, `entity_id`, `outcome`, `occurred_at` | Traçabilité | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `audit_event.ip_address`, `user_agent` | Technique/perso | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `audit_event.changed_fields`, `before_data`, `after_data` | Peut contenir des champs sensibles | ❌ | 👁¹⁵ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 👁¹⁵ |
| Position GPS d'un salarié (futur `telematics`) | Très sensible (T-31) | ❌ | ❌ | agrégé | agrégé | ✅ site, heures de service | ❌ | ⏭ | ❌ | ❌ | ❌ | ❌ | événements sécurité | ❌ | ✅ accès tracé, motivé |

¹⁵ Pour les champs sensibles, l'audit ne stocke que le **nom du champ modifié** (`changed_fields`), jamais la valeur avant/après ; `before_data`/`after_data` ne contiennent aucun champ sensible, secret ni donnée GPS brute (T-40/T-46).

Règles de masquage (côté serveur) :
- **Masquage total** pour le téléphone et le n° de permis : la clé est absente de la réponse pour tout rôle sans la permission `read_sensitive` / `read_number` (D-15). Aucune valeur partielle.
- Le masquage est appliqué par le **sérialiseur** choisi selon la permission effective, avec un test par rôle et par champ sur chaque réponse contenant des données de personne (ST-40 et suivants, générés depuis `field_policies`, §7).
- Les paramètres de tri/filtre/recherche ne permettent pas de **déduire** une valeur masquée (voir §4.4).

---

## 6. Points ouverts restants (défauts provisoires, `DECISIONS_A_ARBITRER.md` partie B)
Tranchés et retirés de la liste : rôle `AUDITOR`, exclusion de `TENANT_ADMIN` des données RH, habilitations (`HR` écrit, `HSE` lit), dérogation d'éligibilité (reportée), affichage partiel du permis (masquage total), source de vérité YAML (retenu).
1. **MFA** (C-03) : TOTP pour `PLATFORM_ADMIN`, `TENANT_ADMIN`, `HR`, `FINANCE` livré après le lot 1 ; avant tout pilote.
2. **Connexion** (C-02) : code d'espace + e-mail acceptable pour les utilisateurs ? SSO/OIDC plus tard.
3. **Double validation** pour l'attribution de `TENANT_ADMIN`/`HR` et **alertes** de notification : reportées, à arbitrer.
4. **Portée imposée `SITE`** pour `HSE` et `FUEL_MANAGER` : la matrice actuelle autorise `HSE` en `TENANT` et `FUEL` en `SITE` seule ; à confirmer.
5. **Lecture réduite du journal d'audit pour `DIRECTION`** (événements de sécurité seulement) : ❌ par défaut.
6. **Accès support** (C-10) et **bris de glace** : avant pilote.
7. **Règle « même site » stricte** (C-04) : stricte au lot 1c.
8. **Écran conducteur et authentification terrain** (C-12) : lot 4.
9. Création de véhicules par `TENANT_ADMIN` (note ⁴) à confirmer ; consultation du journal d'audit elle-même non auditée au lot 1 (à confirmer, QA-10).

---

## 7. Format de `authz_matrix.yaml` (D-09)

> **Proposition** de structure, à créer au lot 1a à `backend/<package>/authz/authz_matrix.yaml` (chemin exact à fixer par l'architecte). Elle est **indépendante du code applicatif** : l'oracle des tests ne doit jamais être déduit des décorateurs de routes (QA-21, risque de test tautologique). Toute modification est relue par `security-engineer` (CODEOWNERS). Aucun fichier n'existe à ce jour ; rien n'a été validé par un schéma ni exécuté.

### 7.1 Structure

```yaml
version: 1
http_policy: D-05                    # la table de décision §1.1.6 est codée dans le harnais, pas ici
scopes: [PLATFORM, TENANT, SITE]

roles:                               # catalogue global (D-18) ; miroir de la table `role`
  TENANT_ADMIN:
    allowed_scopes: [TENANT]
    tenant_kind: CUSTOMER            # PLATFORM_ADMIN : PLATFORM
    assignable_by_tenant: true       # false pour PLATFORM_ADMIN
  DISPATCHER:
    allowed_scopes: [TENANT, SITE]
    tenant_kind: CUSTOMER
    assignable_by_tenant: true
  AUDITOR: { allowed_scopes: [TENANT], tenant_kind: CUSTOMER, assignable_by_tenant: true, optional: true }
  # ... 14 rôles

permissions:
  fleet.vehicle.read:
    tranche: 1b                      # 1a | 1b | 1c | later  (D-21)
    resource: vehicle
    kind: read                       # read | create | update | action
    site_bound: true                 # la ressource porte site_id -> étape 3 (404) applicable
    routes:                          # chemins sans préfixe /api/v1
      - { method: GET, path: /vehicles,        shape: collection, success: 200 }
      - { method: GET, path: /vehicles/{id},   shape: item,       success: 200 }
    audit: { on_success: false, on_denied: true, action: null }
    grants:                          # rôle -> portées d'affectation qui PORTENT la permission
      TENANT_ADMIN:   [TENANT, SITE]
      OPS_MANAGER:    [TENANT, SITE]
      DISPATCHER:     [SITE]         # 🔶
      STOREKEEPER:    [SITE]         # 🔶, champs : voir field_policies
      AUDITOR:        [TENANT]
  assignment.vehicle_assignment.create:
    tranche: 1c
    resource: vehicle_assignment
    kind: create
    site_bound: true
    routes: [ { method: POST, path: /vehicle-assignments, shape: collection, success: 201 } ]
    audit: { on_success: true, on_denied: true, action: vehicle_assignment.create }
    grants: { OPS_MANAGER: [TENANT, SITE], DISPATCHER: [SITE] }
    business_errors: [DRIVER_LICENSE_EXPIRED, VEHICLE_ASSIGNMENT_OVERLAP, ASSIGNMENT_SITE_MISMATCH]
  identity.role_assignment.revoke:
    tranche: 1a
    resource: user_role_assignment
    kind: action
    site_bound: false
    routes: [ { method: POST, path: /role-assignments/{id}/revoke, shape: item, success: 200 } ]
    audit: { on_success: true, on_denied: true, action: role_assignment.revoke, security_event_on: [SELF_ROLE_CHANGE_FORBIDDEN, ROLE_NOT_ASSIGNABLE] }
    grants: { TENANT_ADMIN: [TENANT] }
  fleet.vehicle.export:              # reporté : déclaré seulement pour interdire toute route
    tranche: later
    reason: "D-16 exports hors lot 1"

public_routes:                       # liste blanche ST-01 : aucune permission
  - { method: POST, path: /auth/login }
  - { method: POST, path: /auth/refresh }
  - { method: POST, path: /auth/password/reset-request }
  - { method: POST, path: /auth/password/reset-confirm }
  - { method: POST, path: /auth/invitations/accept }
  - { method: GET,  path: /health }

field_policies:                      # masquage D-15 ; défaut = champ ABSENT sauf listé
  driver:
    permission_for_read: workforce.driver.read
    fields:
      employee_number: { visible: base }
      last_name:       { visible: base }
      phone:           { classification: personal, requires: workforce.driver.read_sensitive, sentinel: "+224000000001" }
      suspension_reason_code: { classification: sensitive_hr, visible_to_roles: [HR, HSE] }
  driver_license:
    permission_for_read: workforce.driver_license.read
    fields:
      category:  { visible: base }
      number:    { classification: personal, requires: workforce.driver_license.read_number, sentinel: "SENT-LIC-0001" }
  vehicle:
    fields:
      purchase_cost: { visible_to_roles: [TENANT_ADMIN, DIRECTION, OPS_MANAGER, FINANCE, AUDITOR] }
    filter_sort_denied_when_masked: true   # -> 422 FIELD_NOT_ALLOWED

global_tables: [role, role_allowed_scope, license_category_ref]   # liste blanche ST-05 (D-18)
```

Règles de lecture : `grants` énumère **seulement** les rôles autorisés (deny-by-default) ; une cellule 🔶 s'écrit `[SITE]`, une cellule ✅ `[TENANT, SITE]` ou `[TENANT]` selon `allowed_scopes` du rôle ; 👁 renvoie à `field_policies`. Un rôle absent de `grants` est ❌. Une permission `tranche: later` n'a ni `routes` ni `grants`.

### 7.2 Règles de génération des tests
1. **ST-01 (inventaire)** : lister les routes FastAPI ; chacune doit référencer une permission existante de tranche ≤ tranche courante, ou figurer dans `public_routes` ; toute route dont la permission est `tranche: later` ou absente fait échouer le build.
2. **ST-02 (matrice)** : pour chaque permission de tranche livrée × route × rôle (14) × profil d'affectation de `{TENANT, SITE sur le site de la ressource, SITE sur un autre site}` compatible avec `allowed_scopes`, générer un cas dont l'oracle est calculé **uniquement** par la table de décision §1.1.6 : rôle absent de `grants` ou portée non listée (🔶 avec `TENANT`) → **403** ; `SITE` sur un autre site, route `item` → **404** ; route `collection` → `success` avec liste filtrée (aucun objet hors site) ; sinon → `success`. Un cas = une réponse attendue.
3. **Isolation (ST-12, ST-20, ST-30…)** : pour chaque route `item` de chaque permission autorisant au moins un rôle, appeler avec un rôle autorisé du tenant A l'identifiant d'un objet du tenant B et celui d'un UUID inexistant ; attendre **404**, corps et en-têtes identiques (utilitaire « réponse équivalente »). Pour chaque route d'écriture : la base reste inchangée.
4. **Masquage (ST-40 et suivants)** : pour chaque champ de `field_policies` × rôle autorisé à lire l'entité : présent ssi la condition `requires`/`visible_to_roles` est vraie ; la valeur `sentinel` ne doit apparaître **nulle part** dans le corps ni dans les logs capturés pour un rôle non autorisé ; filtres et tris sur un champ masqué → **422** `FIELD_NOT_ALLOWED`.
5. **Audit (ST-73)** : pour chaque permission `kind != read`, une opération réussie produit les événements `audit.action` déclarés (par opération métier identifiée) ; chaque 403 produit un événement `DENIED`.
6. **Contrat** : chaque route du schéma OpenAPI porte `x-permission` égal à la clé YAML ; le test compare OpenAPI ↔ YAML ↔ routes (trois sources, un écart = échec). Aucun paramètre `tenant_id` dans les requêtes (ST-06).
7. **Tranche** : le harnais n'exécute que les permissions de tranche ≤ tranche en cours ; les permissions `later` alimentent un test négatif (aucune route).
8. **Canari** : un test volontairement défaillant (filtre de site retiré dans un dépôt de test) doit faire échouer ST-02, pour prouver que les tests ne sont pas tautologiques.

### 7.3 Validation du fichier lui-même
Schéma JSON du YAML (clés autorisées, rôles ∈ catalogue, portées ∈ `allowed_scopes`, codes d'erreur ∈ catalogue d'erreurs) vérifié en CI locale ; permissions nommées `module.ressource.action` ; une même route ne peut apparaître sous deux permissions.

### 7.4 Cohérence document ↔ YAML
Un test (ou script de génération) produit les tableaux de §2 à partir du YAML et échoue si `MATRICE_RBAC.md` diverge [Proposé] ; en cas d'écart, le YAML, relu par la sécurité, fait foi après décision, et la matrice humaine est corrigée (D-09).
