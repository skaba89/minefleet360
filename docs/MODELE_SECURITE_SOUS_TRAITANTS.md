# Modèle de sécurité sous-traitants — accès externe [Proposé]

> **Statut** : proposition de conception — **aucune décision produit, aucun code, aucune route, aucune permission**. L'ouverture du lot correspondant reste un arbitrage séparé.
> **Date** : 13 novembre 2026.
> **Sources** : `MENACES_ET_CONTROLES.md` T-42 (menace interne **haute**, état LU — « à définir à l'ouverture du lot concerné : tests de matrice contractuelle ; modèle d'accès distinct des rôles internes ») ; contrôle **C-37** « Isolation des tiers : comptes externes séparés, accès contractualisé et limité par objet » ; contrôle C-07 (toute route sous permission déclarée, matrice générée) ; `ROADMAP_85_TO_95.md` S1 ; `REGLES_METIER.md` RM-026, RM-077 ; `MATRICE_RBAC.md`.

## 1. Objet et périmètre

Ce document propose le **modèle d'accès externe** pour le personnel d'une société sous-traitante intervenant sur les sites du donneur d'ordre, dans le respect de C-37 : comptes externes **séparés** des rôles internes, accès **contractualisé** (limité à la durée et à l'objet du contrat) et **limité par objet** (chaque donnée exposée est nommée, jamais un module entier).

Hors périmètre, et volontairement :

- la **facturation sous-traitants** (S1, RM-077) : la roadmap exige « règles et cas de facturation validés avant schéma/API » par entretiens métier — aucune règle de tarification n'est proposée ici ;
- les **conducteurs intérimaires gérés comme des employés** (RM-026) : déjà couverts par les contrôles d'éligibilité existants, sans compte externe ;
- l'**écran conducteur** (C-12, lot 4) et l'idempotence hors ligne (lot 4) : sujets distincts, référencés le cas échéant.

## 2. État existant mobilisé

Ce qui existe et sert de fondation — le modèle n'invente aucun mécanisme nouveau en dehors de ceux listés ici :

- **Rôles** : 13 rôles internes (TA, DIR, OPS, DISP, HR, DRV, WSC, MEC, STK, FUEL, HSE, FIN, AUD) + `PLATFORM_ADMIN` (« — » partout). Portée `SITE` par défaut pour les rôles de terrain. Le précédent `DRIVER` (rôle au catalogue, portée restreinte, cellules « propre » réduites au minimum) est le patron du rôle externe.
- **Cloisonnement** : RLS par `tenant_id` sur toutes les tables métier ; aucune FK inter-tenant ; lecture indirecte gouvernée (précédent revue L2A-R-02 : le nom/identifiant du conducteur d'une mission suit `assignment.vehicle_assignment.read`, pas `dispatch.mission.read`).
- **Sessions** (DB-33) : `auth_session.revoked_at` vérifié en base — retrait de rôle → `403` à la requête suivante ; désactivation de compte ou suspension du tenant → `401`. Effet immédiat, pas de « version de jeton ».
- **MFA** : vérifié par le contrôle A6 du runbook staging (obligatoire pour les comptes d'administration).
- **Contrats** : le domaine `legal-contracts` (#432) gère déjà les contrats juridiques et d'assurance du tenant — y compris ceux passés avec des sous-traitants — comme **données du donneur d'ordre** (FIN É/A, HSE/DIR/OPS/AUD lecture). Il n'existe **aucun compte externe** : T-42 est correctement en état LU.
- **GPS** : aucune position n'est exposée hors des rôles internes ; les agrégats SLO (#438) restent sous `fleet.gps.history` (OPS/HSE/AUD).

## 3. Objets concernés et besoins d'accès (proposition)

Principe directeur (C-37) : l'accès est nommé **objet par objet**. Proposition de besoins, à confirmer à l'ouverture du lot :

| Objet | Besoin proposé pour un compte sous-traitant | Portée | Remarque |
|---|---|---|---|
| Missions/rotations où son organisation est prestataire | Lecture seule, limitée aux missions la concernant | `org` | Suit le patron L2A-R-02 de lecture indirecte minimale |
| Contrats le concernant (`legal-contracts`) | Lecture de **ses** contrats et de leurs documents | `org` | Jamais les contrats d'un autre sous-traitant ni le portefeuille complet |
| Incidents HSE le concernant | Lecture des incidents où son organisation est impliquée | `org` | Le signalement reste interne (rôle HSE) |
| Facturation le concernant | Lecture de ses propres factures émises | `org` | RM-077 (base tonnage mesuré approuvé) — règles à valider par entretiens (S1) |
| Positions GPS / temps réel | **Aucun** au premier lot [Proposé] | — | Données de salariés (D-10) ; revue juridique requise (rang 2 du GO/NO-GO) ; les agrégats éventuels relèveraient d'une décision dédiée |
| Coûts, rentabilité, finance interne | **Aucun** | — | « L (son périmètre) » de FIN reste interne |
| Administration (rôles, comptes, quotas) | **Aucun** | — | `PLATFORM_ADMIN` reste « — » partout ; `TENANT_ADMIN` du donneur d'ordre reste maître des comptes |

## 4. Options d'architecture comparées

| Critère | **A — Tenant lié** (sous-traitant = son propre tenant + partage contractuel d'objets) | **B — Rôle externe dans le tenant du donneur d'ordre** | **C — Portail externe séparé** (app/API dédiée) |
|---|---|---|---|
| Isolation T-42 | Maximale (RLS inchangée, zéro donnée partagée par défaut) | Forte si la portée `org` est appliquée côté données (RLS), pas seulement côté API | Maximale (aucune permission interne partagée) |
| Mécanisme nouveau | Infrastructure de partage inter-tenant (ACL par objet, tables de partage) — la plus grosse surface nouvelle, et la menace T-42 se déplace dans ce mécanisme | Rôle au catalogue + entité « organisation sous-traitante » + niveau de portée `org` | Une seconde application (build, déploiement, conformité) |
| Réversibilité (fin de contrat) | Suppression du lien de partage | Désactivation des comptes de l'organisation → `401` immédiat (DB-33) | Résiliation du portail |
| Audit | Partage à journaliser des deux côtés | Accès externes journalisés avec l'organisation, dans l'audit existant | Journal dédié |
| Coût/délai pour un premier lot | Élevé | **Le plus faible** — réutilise RBAC, RLS, sessions, audit | Élevé (double surface produit) |
| Adapté quand | Un sous-traitant gère **sa propre flotte** (plusieurs clients) | Quelques sous-traitants avec un périmètre contractuel étroit | Grand volume de tiers, usages hétérogènes |

## 5. Modèle recommandé [Proposé] — option B, détaillé

**Recommandation : option B pour le premier lot**, pour l'isolation suffisante au moindre mécanisme nouveau ; l'option A devient l'évolution naturelle si un sous-traitant doit gérer sa propre flotte multi-clients (ce qui n'est pas le besoin d'un pilote minier).

1. **Identité** : comptes **nominatifs individuels** (jamais de compte partagé — traçabilité et RM-026), rattachés à une **organisation sous-traitante** (entité nouvelle côté donneur d'ordre) ; date d'expiration calée sur la fin du contrat ; **MFA obligatoire** (patron A6) ; durée de session courte [Proposé : 4 h].
2. **Autorisation** : un rôle externe unique au catalogue (proposition de nom : `SOUS_TRAITANT`), portée `SITE` affinée par la nouvelle portée `org` ; permissions **objet par objet** selon le tableau §3 ; **aucune route d'écriture** — la matrice générée (ST-01/ST-02) doit montrer zéro méthode mutatrice pour ce rôle, contrôle CI inclus.
3. **Cloisonnement des données** : le filtre `org` est appliqué **au niveau des données** (extension du prédicat RLS), pas seulement dans les requêtes de l'API — un oubli de filtre côté route ne doit pas exposer les données d'un autre sous-traitant. Les lectures indirectes suivent le patron L2A-R-02 (identifiant minimal, pas la fiche complète).
4. **Création et révocation** : créées par `TENANT_ADMIN` du donneur d'ordre, **approbation quatre-yeux** par OPS ou DIR [Proposé] (patron des validations quatre-yeux du dépôt) ; révocation → désactivation → `401` immédiat (T-11/ST-67/ST-68).
5. **Audit et alerte** : chaque accès externe porte l'organisation ; alerte sur volumétrie anormale d'accès externe (runbook §Alerte, éprouvetage rang 5 du GO/NO-GO).
6. **GPS** : non exposé au premier lot (§3) — toute ouverture ultérieure exige l'avis juridique (rang 2) et une décision produit explicite.

## 6. Matrice contractuelle de tests attendus (exigence T-42)

Famille de tests à ajouter à l'ouverture du lot (l'outil de matrice générée ST-02 couvrira le nouveau rôle automatiquement) :

| Réf. | Scénario | Résultat attendu |
|---|---|---|
| ST-42a | Sous-traitant X lit un contrat appartenant à Y | `403` + zéro donnée dans la réponse |
| ST-42b | Sous-traitant X liste les missions sans filtre sur son organisation | Seules les missions le concernant reviennent ; une mission étrangère est invisible (et une requête directe par identifiant → `404`/`403`) |
| ST-42c | Sous-traitant accède à une route d'écriture quelconque | `403` — la matrice générée ne contient aucune cellule d'écriture pour le rôle externe |
| ST-42d | Sous-traitant lit la finance interne ou la rentabilité | `403` |
| ST-42e | Fin de contrat : désactivation des comptes de l'organisation | `401` immédiat (DB-33), jetons invalidés |
| ST-42f | `TENANT_ADMIN` crée/révoque un compte externe | Journalisé ; quatre-yeux exigé ; `PLATFORM_ADMIN` reste hors de portée |
| ST-42g | Tenant étranger (patron du test d'isolation #438) | `403` sans fuite de données — inchangé |
| ST-42h | Requête avec portée `org` falsifiée (paramètre, en-tête, FK) | Le prédicat RLS prime : aucune donnée d'une autre organisation |

## 7. Décisions restantes — aucune n'est prise par ce document

À arbitrer **à l'ouverture du lot**, avec les prérequis de gouvernance existants :

1. Choix d'option (§4) et liste définitive des objets exposés (§3) — arbitrage produit.
2. S1 (facturation) : **entretiens métier avant tout schéma/API**, comme l'exige la roadmap — ce document ne préjuge d'aucune règle de tarification.
3. Revue juridique (rang 2 du GO/NO-GO) : clauses de sous-traitance, responsabilité de traitement (question ouverte §3 de `MENACES_ET_CONTROLES.md`), conditions de preuve (loi L/2016/035/AN et décret du 19 août 2026 pour tout ce qui serait présenté comme opposable), cadre assurances L/2016/034/AN.
4. MFA, durée de session, quatre-yeux sur les comptes externes : paramètres [Proposés] à confirmer.
5. Ouverture éventuelle du GPS aux tiers : jamais sans avis juridique et décision produit explicite (§3, §5.6).

## 8. Traçabilité

- `MENACES_ET_CONTROLES.md` T-42 : la ligne est mise à jour pour pointer vers ce document (proposition, non validée). C-37 et C-07 restent les contrôles de référence.
- `ROADMAP_85_TO_95.md` S1 reste « À faire » (règles métier de facturation par entretiens) — ce document ne le ferme pas.
- `GO_NO_GO.md` : aucun prérequis n'est levé par une proposition non implémentée ; le classement des blocants est inchangé.
