# LIVRAISON SAAS LOT 2 — Abonnements tenant↔plan

**Base : main `76e03e8` (post-PR #418 — lot 1 plans/quotas). Phase 6, lot 2 de la mission de commercialisation.**
Statut : livré, testé (5 480 tests pytest, 247 tests Vitest, ruff/mypy/tsc propres). Les quotas ne sont **pas encore appliqués** au provisionnement — c'est le lot 2b ; la facturation paramétrable est le lot 3.

## Périmètre livré

### Modèle (migration 0066, additive)

- Table `tenant_subscription` RLS-applicative classique (tenant_id NOT NULL, policy `tenant_isolation`, trigger `tg_touch` pour `row_version`/`updated_at`, trigger `tg_forbid_tenant_change`) : une société ne lit que SES abonnements.
- **Un seul abonnement vivant par société** : index unique partiel `uq_ts_tenant_current` sur `WHERE status IN ('TRIAL','ACTIVE','SUSPENDED')`. Souscrire un nouvel abonnement annule l'ancien (motif « Remplacé par un nouvel abonnement »), l'historique complet est conservé.
- Cycle de vie : `TRIAL` → `ACTIVE` → `SUSPENDED` (↔ réactivation) ; `CANCELLED` **terminal** (libère le créneau de l'index unique). Contraintes en base : `suspended_at`/`cancelled_at` présents si et seulement si le statut correspond, motif de suspension de 3 à 500 caractères, dates d'essai/période postérieures à la création.
- Pas de prix, pas de paiement : `period_ends_at` est informatif (renouvellement manuel) ; la facturation paramétrable (GNF, taxes) reste au lot 3 après arbitrage.

### API

Gestion plateforme (PLATFORM_ADMIN, permission `billing.subscription.manage`, tenant_id dans le chemin pour la bascule de contexte RLS — même pattern que `/platform/tenants/{tenant_id}/suspend`) :

- `POST /platform/tenants/{tenant_id}/subscriptions` — souscription : `{plan_id, trial_days?, period_ends_at?, notes?}` → `TRIAL` (essai daté 1-365 j) ou `ACTIVE` ; 422 `PLAN_NOT_ACTIVE` si le plan n'est pas actif ; 404 `NOT_FOUND` si la société n'existe pas.
- `GET /platform/tenants/{tenant_id}/subscriptions` — historique paginé (filtre `?status=`).
- `POST .../{subscription_id}/activate` — essai → actif.
- `POST .../{subscription_id}/suspend` — motif obligatoire.
- `POST .../{subscription_id}/reactivate` — suspension → actif (motif effacé).
- `POST .../{subscription_id}/cancel` — terminal.
- `POST .../{subscription_id}/renew` — `{period_ends_at}` renouvelle la période.

Toutes les écritures exigent `If-Match` (409 `VERSION_CONFLICT` en cas d'écart) et sont auditées dans la société cible (`billing.subscription.create/cancel/active/suspended/cancelled/renew`). Un `subscription_id` d'une autre société dans le chemin est **indiscernable d'un identifiant inexistant** (404) — testé.

Lecture société (RLS naturelle, `GET /tenant/subscription`, permission `billing.subscription.read` → TENANT_ADMIN, DIRECTION, FINANCE, AUDITOR) : statut, échéances et **quotas du plan souscrit** ; 404 neutre si aucun abonnement vivant.

### UI

- Page plateforme **« Abonnements »** (`/plateforme/abonnements`) : sélection d'une société, historique (plan, statut, fin d'essai, fin de période, motif), souscription (choix société/plan actif, mode essai daté ou activation directe), actions contextuelles par statut (Activer / Suspendre / Réactiver / Annuler / Renouveler) avec motif et If-Match.
- Page société **« Abonnement »** (`/abonnement`, menu principal pour les rôles autorisés) : formule souscrite, statut, échéances, quotas (« Illimité » pour les plans sans borne). Libellé explicite : le renouvellement se gère avec l'équipe MineFleet 360 ; l'application des limites au provisionnement se met en service progressivement.

## Règles appliquées

- **RLS d'abord** : la plateforme ne touche une ligne d'abonnement qu'après `set_tenant_context(tenant_id)` dérivé du chemin (la table `tenant` est sans RLS) ; l'appartenance est de toute façon revérifiée (`tenant_id` dans le WHERE) — un cross-tenant renvoie 404 identique à un objet manquant.
- **Audit** : chaque transition écrite dans la société cible avec `before`/`after` (les horodatages sont sérialisés ISO en `after_data`).
- **Anti-dérive** : `billing.subscription.manage` (portée PLATFORM seule) et `billing.subscription.read` (TENANT_ADMIN/DIRECTION/FINANCE/AUDITOR à portée TENANT) déclarées dans `authz_matrix.yaml` (tranche 2a) ; `permissions.generated.ts`, `schema.d.ts` et `ROLE_PAGE_ACTION_MATRIX.md` régénérés, `--check` verts.

## Limites assumées (prochains lots)

1. **Quotas non appliqués** : le provisionnement (utilisateurs, sites, véhicules, traceurs GPS) ne consulte pas encore l'abonnement — lot 2b, avec tests de refus au-delà des limites.
2. Pas d'expiration automatique de l'essai : `trial_ends_at` est affiché mais ne bascule pas le statut tout seul (aucun scheduler en lot 2 ; décision à prendre au lot 3 avec la facturation : sweep ou calcul à la lecture).
3. Renouvellement manuel plateforme ; la facturation (lot 3) automatisera le cycle période → facture.
4. La suspension d'abonnement ne révoque pas les sessions (contrairement à la suspension de société, qui reste l'outil d'urgence) — comportement documenté dans l'UI.

## Preuves

- Backend : `backend/tests/test_billing_subscriptions.py` — 9 tests (essai+activation+lecture société, plan inactif 422, unicité vivant+historique, transitions+conflits de version+404 neutre après annulation, renouvellement, 403 gestion tenant, lecture par rôles autorisés/refusés, cross-tenant 404, société inconnue 404).
- Matrice générée et isolation : `test_authz_matrix.py` et `test_database.py` verts (le monde RBAC crée un abonnement ; `tenant_subscription` est couverte par DBT40 comme table tenant-scopée avec RLS forcée).
- Suite complète locale : **5 480 tests pytest passés** (PostgreSQL 16 + PostGIS réel, base `minefleet_test`).
- Frontend : `PlatformSubscriptionsPage.test.tsx` (5 tests) + `TenantSubscriptionPage.test.tsx` (2 tests) ; Vitest **247/247**, `tsc --noEmit` OK.
- Migration rejouée localement (downgrade/upgrade) : `tg_touch` et `tg_forbid_tenant_change` présents, policy RLS active.
