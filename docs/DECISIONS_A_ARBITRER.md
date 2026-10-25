# Décisions — tranchées et à arbitrer — MINEFLEET 360

> Date : 2026-10-25. Issu de la revue croisée (`docs/revues/REVUE_QA_DEVOPS.md` QA-01..32, `docs/revues/REVUE_DATABASE_ARCHITECT.md` DB-01..42).
> Partie A : décisions **techniques tranchées par le lead** (réversibles, appliquées à la documentation). Partie B : décisions **à arbitrer par le client / le juriste** — chaque ligne porte une **valeur par défaut provisoire** utilisée tant que l'arbitrage n'est pas rendu.
> En cas de divergence entre documents, l'ordre de préséance est : ce fichier > `MODELE_PHYSIQUE_LOT1.md` > `MATRICE_RBAC.md` > `REGLES_METIER.md` > `DICTIONNAIRE_DONNEES.md` > `USER_STORIES.md` > `PRD_MVP.md` > autres.

## A. Décisions techniques tranchées

| ID | Décision | Résout |
|----|----------|--------|
| D-01 | **Valeurs d'énumération en anglais `UPPER_SNAKE_CASE`**, libellés français uniquement dans l'UI (fichier i18n). Glossaire unique dans `DICTIONNAIRE_DONNEES.md`. | QA-02, DB-01 |
| D-02 | **Statut véhicule** (stocké) : `AVAILABLE`, `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED` (terminal). « En exploitation » est **dérivé** (affectation active), jamais stocké. Historique dans `vehicle_status_history` (trigger). | QA-02, DB-01, DB-16 |
| D-03 | **Statut conducteur** : `ACTIVE`, `UNAVAILABLE`, `SUSPENDED`, `INACTIVE`. Validité permis/habilitation **dérivée** des dates (jamais stockée). | QA-02, DB-02 |
| D-04 | **Statut affectation** : `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED`. Exclusion de chevauchement `EXCLUDE USING gist` sur `[valid_from, valid_to)` hors `CANCELLED`, côté véhicule et côté conducteur ; `CHECK (valid_to > valid_from)`. | QA-05, DB-02, DB-09 |
| D-05 | **Table des codes HTTP** (unique, à reprendre dans toutes les stories et tests) : `401` non authentifié ; `404` ressource hors tenant **ou** hors portée site de l'utilisateur (non-divulgation) ; `403` permission manquante sur une ressource visible ou sur un endpoint de collection ; `422` validation de format **ou** règle métier violée (corps d'erreur avec `code` stable, ex. `DRIVER_LICENSE_EXPIRED`) ; `409` conflit d'état : chevauchement, unicité, `row_version` obsolète. Les `403` sont audités ; les `404` sur identifiant d'un autre tenant sont journalisés comme événement de sécurité (log structuré, pas audit tenant). | QA-03 |
| D-06 | **Connexion** = code d'espace de travail (tenant, porté par l'URL ou saisi) + e-mail + mot de passe. E-mail unique **par tenant** (`citext`). Identifiant inconnu et mot de passe faux → même réponse. Résolution pré-auth du tenant par code exact selon DB-05, **sans BYPASSRLS**. | QA-01, DB-05, DB-07 |
| D-07 | **Tenant plateforme réservé** (`kind = 'PLATFORM'`) ; `tenant_id NOT NULL` partout ; `PLATFORM_ADMIN` dans ce tenant uniquement. | DB-04 |
| D-08 | **RLS** via fonction `app.current_tenant_id()` utilisant `NULLIF(current_setting('app.tenant_id', true), '')::uuid` → 0 ligne sans contexte, jamais d'erreur sur connexion de pool réutilisée. `SET LOCAL` par transaction. Partitions créées avec RLS forcée. | DB-03, DB-25, DB-26 |
| D-09 | **Source de vérité des permissions** : `MATRICE_RBAC.md` (humain) + `backend/.../authz_matrix.yaml` (machine, créé au lot 1a) ; les tests d'autorisation et d'isolation sont **générés** depuis le YAML ; un test vérifie que toute route déclare une permission. | QA-04, QA-21 |
| D-10 | **Arbitrages RBAC provisoires** : `TENANT_ADMIN` gère comptes/rôles/sites/référentiels mais **ne lit pas** les données personnelles conducteur ; `HR` écrit conducteurs, permis, habilitations ; `HSE` lit (écriture reportée) ; `DISPATCHER` et `OPS_MANAGER` créent/clôturent les affectations, `DISPATCHER` en portée **SITE** uniquement ; journal d'audit lisible par `TENANT_ADMIN` et `AUDITOR` ; `PLATFORM_ADMIN` sans accès aux données métier. `AUDITOR` est retenu (rôle optionnel, lecture seule). | QA-04 |
| D-11 | **Cycle de vie (Q17)** : passer un véhicule en `IN_MAINTENANCE`/`IMMOBILIZED`/`OUT_OF_SERVICE`/`RETIRED`, ou un conducteur en non-`ACTIVE`, **est refusé (409)** tant qu'une affectation `PLANNED`/`ACTIVE` existe ; la réponse liste les affectations à clôturer. Simple, explicite, auditable. | QA-05 |
| D-12 | **Expiration en cours d'affectation** : au lot 1, la **conformité est calculée à la lecture** (drapeau dérivé « non conforme » + motif), sans job planifié. La transition automatique vers `SUSPENDED` arrive avec le planificateur (lot 2+). **Horloge injectable** obligatoire dans le code dès le lot 1. | QA-05, QA-08 |
| D-13 | **Pas d'antidatage** au lot 1 (`valid_from ≥ now − tolérance configurable`). **Même site obligatoire** véhicule/conducteur/affectation ; transfert de site d'un conducteur ou véhicule refusé s'il a une affectation ouverte. Dérogation d'éligibilité **reportée**. | QA-05, QA-06, DB-17 |
| D-14 | **Idempotence** (`Idempotency-Key`, `idempotency_record`) **reportée au lot 4** (offline). Au lot 1, les doublons sont empêchés par contraintes d'unicité et d'exclusion. Critères correspondants retirés du lot 1. | QA-09 |
| D-15 | **Minimisation** : pas de date de naissance, d'aptitude médicale ni de motif maladie au lot 1. Téléphone et n° de permis = données personnelles, visibles par `HR` seulement ; **masquage total** pour les autres rôles, côté serveur. | QA-11, DB-22 |
| D-16 | **Hors lot 1** : exports, accès support plateforme, liaison compte↔conducteur et écran conducteur, chaînage de hash (scellement asynchrone ultérieur), relevés de compteurs (`vehicle_meter_reading` livrée avec la 1re story compteur), documents réglementaires véhicule, `person` générique (`driver` conservé, migration non destructive plus tard). | QA-19, DB-14, DB-15, DB-20, DB-21, DB-28 |
| D-17 | **Audit** : `audit_event` unique (schéma ADR-005 aligné sur le modèle physique), écrit dans la même transaction, **partitionné par mois dès la migration 0001**, `mf_app` = INSERT/SELECT seulement + trigger anti UPDATE/DELETE. | QA-10, DB-08, DB-19 |
| D-18 | **Référentiels** : `role` et `permission` = catalogue système global en lecture seule (pas une donnée tenant) ; catégories de véhicule et de permis = **copie par tenant** à la création, via table de jonction catégorie↔permis requis. | QA-17, DB-12, DB-13 |
| D-19 | **Concurrence optimiste** : colonne `row_version` (trigger), en-tête `If-Match`/ETag, `409` si obsolète. Pas de suppression physique pour `mf_app` sur les tables métier ; archivage par statut. | DB-23, DB-24 |
| D-20 | **Identifiants** : UUID v4 (`gen_random_uuid()` natif PG16) ; pas de dépendance UUID v7. | DB-27, C12 |
| D-21 | **Lot 1 découpé** en 1a (socle : repo, compose, CI locale, tenant/site, auth, rôles, audit, RLS), 1b (véhicules, conducteurs, permis, habilitations), 1c (affectations + UI minimale + E2E). Voir `PLAN_LOT1.md`. | QA-20 |
| D-22 | **Outillage** : base de test = service PostgreSQL/PostGIS Docker (pas testcontainers) ; Python 3.12 en conteneur ; npm ; scripts PowerShell/npm au lieu de `make` ; `.gitattributes` `eol=lf`. Dépendances de test lot 1 limitées à pytest, httpx, pytest-cov, Vitest, Testing Library, Playwright, ruff, mypy ; `hypothesis`, Schemathesis, k6, oasdiff, Trivy, MSW, axe **reportées** et à justifier au cas par cas. | QA-12, QA-23 |
| D-23 | **Tests fuseau horaire** : fixtures multi-fuseaux obligatoires (Conakry étant UTC+0, un bug de fuseau serait invisible). Formatage nombres/GNF via un utilitaire unique basé sur `Intl` `fr-FR`. | QA-22, UQ6 |
| D-24 | **Git** : branche `master` renommée `main` au premier commit ; commits conventionnels ; CI GitHub Actions écrite mais **non exécutée** tant qu'aucun dépôt distant n'est choisi. | QA-23 |

### Précisions post-correction (2026-10-25)
| ID | Précision |
|----|-----------|
| D-05a | Ordre d'évaluation unique : `401` → `403` si **aucune** attribution de rôle de l'utilisateur ne porte la permission (évalué **avant** toute recherche de ressource, donc sans oracle d'existence) → `404` si ressource hors tenant/portée → `422` → `409` → `429`. Erreur FK `23503` → `422 REFERENCE_NOT_FOUND`. |
| D-05b | Modifier ses propres rôles → `422 SELF_ROLE_CHANGE_FORBIDDEN` (évalué avant `409 LAST_TENANT_ADMIN`). Les stories et tests antérieurs contraires sont à aligner. |
| D-18a | Le **catalogue des permissions** vit uniquement dans `authz_matrix.yaml` (versionné, revu en PR) ; pas de tables `permission`/`role_permission` en base au lot 1. La base porte `role` (catalogue global) et `user_role_assignment`. |
| D-25 | `FINANCE` sans lecture des affectations au lot 1 ; `DRIVER` attribuable mais sans permission métier au lot 1 ; premier `PLATFORM_ADMIN` créé par commande d'exploitation (pas d'API) ; révocations via `POST …/revoke`. |
| D-27 | Sans planificateur au lot 1, `PLANNED` → `ACTIVE` est une **action explicite** (prise de poste) qui **revérifie l'éligibilité** à la date courante (RM-031) ; `ACTIVE` → `COMPLETED` par clôture explicite. L'UI affiche un indicateur **dérivé** « activation en retard » / « fin dépassée » calculé avec l'horloge injectable. Passage automatique : ADR « Planification et horloge » à rédiger avant le lot 2. |
| D-30 | `ACTIVE` → `SUSPENDED` (et retour) au lot 1 : **action manuelle motivée** (`OPS_MANAGER`, `DISPATCHER` portée site), auditée ; `SUSPENDED` occupe toujours le créneau et bloque les changements de site. |
| D-28 | Envoi d'e-mails (invitations, réinitialisation) via un **port `EmailSender`** ; en développement, adaptateur de capture locale (fichier/log, jamais d'envoi réel). Fournisseur réel = décision client (C-01). Interdiction d'auto-désactivation de son propre compte (`422`). |
| D-29 | Inéligibilité d'affectation : **un seul code** `422 ASSIGNMENT_NOT_ELIGIBLE` avec `reasons[]` listant **tous** les motifs (`DRIVER_NOT_ACTIVE`, `DRIVER_LICENSE_EXPIRED`, `DRIVER_LICENSE_CATEGORY_MISSING`, `DRIVER_QUALIFICATION_MISSING`, `VEHICLE_NOT_AVAILABLE`, `ASSIGNMENT_SITE_MISMATCH`, `ASSIGNMENT_BACKDATED`). Les codes `IF_MATCH_REQUIRED` (428 → retenu en `422` pour simplicité client), `OPEN_ASSIGNMENTS_EXIST` et `SITE_HAS_ACTIVE_RESOURCES` (`409`) sont entérinés. |
| D-26 | Les codes d'erreur métier forment un **catalogue unique** (`backend/app/core/errors.py` + section OpenAPI) créé en tranche 1a ; tout code utilisé dans un document y est reporté ou supprimé. |

## B. Décisions à arbitrer (client / juriste)

| ID | Question | Défaut provisoire | Bloque |
|----|----------|-------------------|--------|
| C-01 | Hébergement (pays, fournisseur), résidence des données, transfert hors Guinée | Développement local uniquement ; aucun cloud | Mise en production, sauvegardes, accès support |
| C-02 | Connexion : code d'espace + e-mail (D-06) acceptable pour les utilisateurs ? SSO/OIDC requis ? | Oui code + e-mail ; OIDC plus tard | Lot 1a |
| C-03 | MFA obligatoire pour quels rôles et par quel canal ? | TOTP pour `PLATFORM_ADMIN`, `TENANT_ADMIN`, `HR`, `FINANCE` — livré après lot 1 | Avant pilote |
| C-04 | Règle « même site » stricte (D-13) ou dérogation `OPS_MANAGER` ? | Stricte | Lot 1c |
| C-05 | Mécaniciens/magasiniers = mêmes dossiers personne que conducteurs ? | Non au lot 1 (`driver` seul) | Lot 3 |
| C-06 | Documents véhicule bloquant l'affectation (assurance, visite technique…) | Aucun au lot 1 | Lot 2 |
| C-07 | Catégories de permis guinéens et durées de validité ; engins hors route : permis d'État requis ? | Catégories marquées « à valider localement » | Éligibilité (lot 1b) — valeur fictive en dev |
| C-08 | Données personnelles autorisées (date de naissance, aptitude médicale), base légale, information des salariés, géolocalisation (plages, usage disciplinaire) | Exclues (D-15) ; aucune donnée GPS réelle | Lots 2, 5 |
| C-09 | Durées de rétention : audit, IP, sessions, GPS brut/normalisé | Aucune purge en dev ; valeurs à fixer par le juriste | Mise en production |
| C-10 | Accès support plateforme : approbation tenant, durée max, lecture seule | Pas d'accès support au lot 1 | Pilote |
| C-11 | Rythme de postes (2x12h, 3x8h), planning récurrent, binôme | Affectations contiguës manuelles | Lot 2 |
| C-12 | Écran conducteur au lot 1 ? Authentification terrain (PIN, QR, téléphones partagés) ? | Non au lot 1 | Lot 4 |
| C-13 | Réutilisation d'une immatriculation après réforme ; réactivation d'un véhicule `RETIRED` | Numéro de parc unique à vie par tenant ; immatriculation nullable (engins) ; `RETIRED` terminal | Lot 1b |
| C-14 | Fournisseur GPS, protocole, fréquence ; pont-bascule (format ticket, mode secours) | Adaptateur simulé uniquement | Lot 5 |
| C-15 | Client pilote, volumétrie cible (tenants, sites, véhicules, utilisateurs) | Hypothèse dev : 3 tenants fictifs × 3 sites × 200 véhicules | Tests de charge |
| C-16 | Import CSV initial du parc et du personnel | Hors lot 1 | Lot 2 |
| C-17 | Hébergement du dépôt Git (GitHub, GitLab…) et activation de la CI distante | Dépôt local | Lot 1a (CI distante) |
