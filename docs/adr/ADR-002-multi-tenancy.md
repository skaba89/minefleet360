# ADR-002 — Stratégie multi-tenant et propagation du contexte

- **Statut** : Proposé (mis à jour après la revue croisée ; aligné sur `docs/DECISIONS_A_ARBITRER.md`, qui prime en cas de divergence)
- **Date** : 2026-10-25
- **Références** : `docs/00_SOCLE_CADRAGE.md` (H1, H2, H3, H7), `docs/DECISIONS_A_ARBITRER.md` (D-06, D-07, D-08, D-10, D-16, D-17), `docs/MODELE_PHYSIQUE_LOT1.md` (§4, §6), `docs/revues/REVUE_DATABASE_ARCHITECT.md` (DB-03, DB-04, DB-05, DB-25, DB-26, DB-40), `CLAUDE.md`, skill `security-review`

## 1. Contexte
La plateforme sert plusieurs entreprises (tenants) ayant chacune plusieurs sites. Une fuite inter-tenant est le risque n°1 (données RH, GPS, coûts). Il faut une isolation vérifiable, peu coûteuse à exploiter, avec accès support exceptionnel et tracé.

## 2. Options

| Critère | A. Base + schéma partagés (`tenant_id`) + RLS | B. Schéma PostgreSQL par tenant | C. Base par tenant |
|---|---|---|---|
| Isolation | Logique (application + RLS + FK composites) | Plus forte (search_path) mais erreurs de configuration possibles | Maximale |
| Migrations | Une seule exécution | N exécutions, dérive de schémas possible | N exécutions, orchestration lourde |
| Coût / ops | Le plus bas | Moyen (catalogue gonflé, sauvegardes par schéma) | Élevé (connexions, supervision) |
| Reporting plateforme | Simple | Requêtes multi-schémas | Très difficile |
| Onboarding tenant | Insertion de lignes | Création de schéma + migrations | Provisionnement de base (service payant éventuel) |
| Résidence / exigence contractuelle forte | Non satisfaisante seule | Partielle | Satisfaisante |
| Risque principal | Oubli de filtre -> fuite (atténué par RLS + tests) | Dérive, outillage | Coût |

## 3. Décision
**Option A (H1)** : base partagée, schéma partagé, `tenant_id uuid NOT NULL` sur toute table tenant-scopée **sans exception** (D-07 : les comptes et événements de plateforme appartiennent au **tenant plateforme réservé**, `tenant.kind = 'PLATFORM'`, un seul, code `mf-platform`), avec trois barrières cumulées :
1. **Autorisation applicative** (service) : rôle + portée (H7) vérifiés pour chaque opération.
2. **Filtre explicite** `tenant_id` dans chaque requête du repository.
3. **RLS PostgreSQL** en défense en profondeur (jamais en remplacement de l'autorisation applicative) + **FK composites `(tenant_id, id)`** (H3) rendant une référence inter-tenant impossible. La RLS protège contre les **défauts de l'application** (filtre oublié, requête brute), pas contre une application compromise qui fixerait elle-même le contexte : modèle de menace explicite.

Tables globales sans `tenant_id` et sans RLS (catalogue système en lecture seule pour `mf_app`, D-18) : `role`, `role_allowed_scope`, `license_category_ref` (le catalogue des permissions vit dans `authz_matrix.yaml`, pas en base : D-18a). `tenant` est sa propre racine (politiques dédiées, §3.6).

Une migration vers B ou C reste possible pour un client exigeant (point à valider), car tout accès passe par un contexte tenant unique.

### 3.1 Propagation du contexte tenant
```mermaid
sequenceDiagram
  participant C as Client
  participant R as Router FastAPI
  participant D as Dépendance get_tenant_context
  participant DB as PostgreSQL
  C->>R: Requête + jeton/session
  R->>D: Authentifier, résoudre tenant_id, rôles, sites
  D->>DB: BEGIN; SELECT set_config('app.tenant_id', :tid, true)
  Note over D,DB: équivalent SET LOCAL, limité à la transaction
  R->>DB: Requêtes du service (filtre tenant_id + RLS)
  DB-->>R: Lignes du tenant uniquement
  R->>DB: COMMIT (le réglage disparaît)
```
- Le `tenant_id` provient **uniquement** de l'identité authentifiée (jeton/session), **jamais** d'un paramètre, en-tête ou corps fourni par le client.
- Dépendance FastAPI `TenantContext(tenant_id, user_id, roles, site_scope, request_id)` injectée dans tous les routers métier ; un test d'architecture vérifie qu'aucune route métier ne s'en passe (allowlist explicite : login, santé).
- `SET LOCAL app.tenant_id` est exécuté au début de chaque transaction (via `set_config(..., true)` pour paramétrage sûr). Avec un pool de connexions, `LOCAL` garantit l'absence de fuite entre requêtes ; `pool_reset_on_return` reste actif.
- **Fonction de contexte (D-08)** : `app.current_tenant_id()` = `NULLIF(current_setting('app.tenant_id', true), '')::uuid`. Correction de la version initiale de cet ADR : après un `set_config(..., true)`, le paramètre personnalisé **retombe à la chaîne vide** (et non à NULL) à la fin de la transaction ; sur une connexion de pool réutilisée sans nouveau contexte, `''::uuid` aurait levé une **erreur**. Avec `NULLIF`, l'absence de contexte donne `NULL`, donc **0 ligne et jamais d'erreur**.
- Politique type : `USING (tenant_id = app.current_tenant_id()) WITH CHECK (tenant_id = app.current_tenant_id())`, `TO mf_app`, avec `ENABLE` et `FORCE ROW LEVEL SECURITY` sur chaque table. Les partitions (ex. `audit_event`) sont créées par une fonction unique avec RLS forcée et sans aucun droit pour `mf_app` ou `PUBLIC` : un accès direct à une partition contournerait sinon les politiques du parent (DB-25).
- `tenant_id` est immuable (trigger `tg_forbid_tenant_change`).
- Tâches de fond : le contexte est passé explicitement au job (`tenant_id` dans le message) et réappliqué par la même fabrique de transaction.

### 3.1 bis Connexion pré-authentification (D-06, DB-05)
La connexion, l'activation d'invitation, la réinitialisation de mot de passe et le refresh doivent **trouver** le compte ou la session avant que le tenant soit établi par le jeton. Sans `BYPASSRLS` :
1. **Connexion** = code d'espace de travail (`tenant.code`, porté par l'URL ou saisi) + e-mail + mot de passe ; e-mail `citext` **unique par tenant**. La requête de résolution fixe `set_config('app.login_tenant_code', :code, true)` ; une politique de lecture sur `tenant` ne révèle que la ligne dont le **code exact** est fourni (aucun listage). Puis le contexte `app.tenant_id` est posé et le compte est cherché sous RLS. Identifiant inconnu et mot de passe faux donnent la même réponse ; tenant `SUSPENDED` : refus générique.
2. **Refresh, activation, réinitialisation** : le cookie ou le lien porte `<tenant_id>.<id>.<secret>` ; le préfixe ne sert qu'à fixer le contexte, l'autorité reste le secret haché retrouvé sous RLS ; préfixe erroné = 0 ligne = 401.
3. **Connexion `PLATFORM_ADMIN`** : point d'entrée distinct dont le code d'espace est fixé côté serveur (`mf-platform`).
4. **Création d'un tenant** : une **fonction applicative unique**, auditée, s'exécute en contexte plateforme (insertion de `tenant` autorisée seulement dans ce contexte, trigger de garde sur `code`, `kind`, `status`, `is_demo`), puis change le contexte vers le nouveau tenant dans la même transaction pour amorcer ses lignes. Un test d'architecture vérifie qu'aucun autre code n'appelle `set_config('app.tenant_id', ...)` en dehors du gestionnaire de contexte et de cette fonction.

### 3.2 Rôles de base de données
| Rôle | Usage | Droits |
|---|---|---|
| `mf_owner` | Propriétaire du schéma, exécute Alembic | DDL ; **n'est pas utilisé par l'application** |
| `mf_app` | Connexion de l'API | `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, DML sur tables métier uniquement ; **aucun `DELETE`** sur les tables métier (D-19) ; **pas** `UPDATE/DELETE/TRUNCATE` sur `audit_event` (ADR-005) |
| `mf_readonly_report` (plus tard) | Reporting | `SELECT`, soumis à RLS |
- Le propriétaire d'une table contourne la RLS sauf `FORCE ROW LEVEL SECURITY` ; l'app ne se connecte donc jamais comme propriétaire. Les politiques ne ciblent que `mf_app` : avec `FORCE`, `mf_owner` ne voit aucune ligne métier par défaut (fail-closed, DB-26). Les migrations qui amorcent des lignes (tenant plateforme, référentiels) les insèrent **avant** d'activer `FORCE`, ou basculent `NO FORCE`/`FORCE` dans la même transaction DDL.
- Création des rôles et des extensions (`postgis`, `btree_gist`, `citext`) par script `infra/db/bootstrap.sql` exécuté par un super-utilisateur, hors Alembic (mots de passe via variables d'environnement/secret store, jamais dans le dépôt).
- Un test d'intégration vérifie au démarrage : `rolsuper = false`, `rolbypassrls = false` pour `mf_app`.

### 3.3 Portée site (H7)
- Chaque affectation de rôle porte une portée `TENANT` ou `SITE(site_id)`. Le contexte contient l'ensemble des `site_id` autorisés.
- Les tables dépendantes d'un site portent `site_id` ; le repository ajoute `site_id IN (:sites)` quand la portée est `SITE`. La RLS ne porte que sur le tenant : la portée site est vérifiée en application, plus fine et testable. **Confirmé** (DB-40) : un même utilisateur cumule des rôles de portées différentes (union par permission) ; la portée dépend de la permission et ne se réduit pas à un réglage de session unique. Un hors-portée site donne `404` (D-05). `DISPATCHER` n'existe qu'en portée `SITE` (D-10).

### 3.4 Accès support `PLATFORM_ADMIN`
- **Lot 1 : aucun accès support** (D-16, C-10). Le `PLATFORM_ADMIN` appartient au tenant plateforme, **n'a aucun accès aux données métier** d'un tenant (D-10) et ne peut créer ou suspendre que des tenants et en lire les métadonnées de gestion. Les politiques RLS n'ont donc pas de cas particulier de support à tester.
- Ultérieurement (pilote) : **session de support** explicite (table `support_access_session`, esquissée dans le modèle physique) : tenant ciblé, motif obligatoire, durée limitée, lecture seule par défaut, approbation du tenant. Chaque ouverture, requête significative et clôture généreraient un `audit_event` avec `actor_kind = PLATFORM_SUPPORT`, visible du tenant. Le contexte support positionnerait `app.tenant_id` du tenant ciblé ; aucun rôle DB `BYPASSRLS` ne serait créé pour le support.
- Les opérations de plateforme (création de tenant) passent par le chemin dédié et audité du §3.1 bis.

### 3.5 Tests obligatoires
- Jeux de données de 2 tenants fictifs ; pour **chaque** endpoint : lecture/modification d'un ID du tenant B avec un jeton du tenant A -> 404 (pas 403, pour ne pas confirmer l'existence ; D-05). Ces `404` sont journalisés comme événements de sécurité (log structuré, pas audit du tenant).
- Test RLS direct en SQL avec `mf_app` sans variable de session (0 ligne, sans erreur) et avec mauvais tenant.
- Test « transaction 1 avec contexte, `COMMIT`, transaction 2 sur la **même connexion** sans contexte -> 0 ligne, sans erreur » (D-08).
- Test que `mf_app` ne lit ni n'écrit directement une partition d'audit, et que `mf_owner` ne voit aucune ligne métier.
- Test des FK composites (insertion inter-tenant rejetée).
- Test de non-fuite du contexte entre deux requêtes successives sur la même connexion poolée.

### 3.6 Politiques de la table `tenant`
Lecture : ligne propre (`tenant_id = app.current_tenant_id()`), ou contexte plateforme (`app.is_platform_context()`), ou code exact fourni via `app.login_tenant_code` ; insertion : contexte plateforme seulement ; mise à jour : ligne propre ou contexte plateforme, avec un trigger de garde interdisant à un contexte client de modifier `code`, `kind`, `status`, `is_demo`, `legal_name` (et à tous de modifier `kind`). Le tenant plateforme est exclu des listes de tenants clients (filtre `kind`). Détail du DDL : `MODELE_PHYSIQUE_LOT1.md` §5.1 et §6. Rien de cela n'a été exécuté.

## 4. Conséquences
- (+) Coût et opérations minimaux, migrations uniques, isolation vérifiable à trois niveaux.
- (−) Une requête SQL brute non filtrée ne dépend que de la RLS : interdiction du SQL brut hors repository (contrôle import-linter/revue).
- (−) Overhead de `set_config` par transaction et risque de plans de requête dégradés : index commençant par `tenant_id`; non mesuré à ce stade.
- (−) Les jobs d'administration cross-tenant (corrections de données transverses) ne passent ni par `mf_app` ni par un contournement de la RLS : tenant par tenant en posant le contexte, ou rôle d'exploitation nominatif temporaire avec `BYPASSRLS` accordé avec approbation explicite (CLAUDE.md). `mf_owner` est soumis à `FORCE` et ne lit pas les lignes métier par défaut.

## 5. Points à valider
- Besoin client d'isolation renforcée (schéma/base dédiée) ou d'exigences contractuelles de localisation des données.
- Politique d'accès support (approbation préalable du tenant, durée maximale) : défaut provisoire C-10 = pas d'accès support au lot 1.
- Hébergement et résidence des données (C-01) : développement local uniquement pour l'instant.
- Avis juridique local sur l'hébergement et l'accès éditeur aux données du personnel.
- Rien n'a été testé : les politiques RLS et les rôles sont des spécifications.
