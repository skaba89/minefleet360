# LIVRAISON SAAS LOT 1 — Catalogue de plans et quotas

**Base : main `2c336ea` (post-PR #417) — Phase 6, lot 1 de la mission de commercialisation.**
Statut : livré, testé en CI. Les lots 2 (abonnements), 3 (facturation) et 4 (support/onboarding) suivent en PR verticales séparées.

## Périmètre livré

Référentiel de l'offre commerciale géré par la plateforme :

- Table `saas_plan` (migration **0065**, additive, sans RLS applicative — donnée de référence plateforme, même statut que `tenant`) : code immuable unique, nom, description, statut, cinq quotas.
- Quotas modélisés : `max_users`, `max_sites`, `max_vehicles`, `max_gps_trackers`, `document_retention_days`. **NULL = illimité.**
- Cycle de vie : `DRAFT` (brouillon) → `ACTIVE` (offert) → `RETIRED` (retiré, **état terminal** — plus modifiable, jamais supprimé ; le référentiel reste consultable pour l'historique et les futurs abonnements).
- API `/platform/saas-plans` réservée à PLATFORM_ADMIN :
  - `POST /platform/saas-plans` — création (201), `billing.plan.create`, audit `billing.plan.create` ;
  - `GET /platform/saas-plans` et `GET /platform/saas-plans/{id}` — consultation (200, ETag), `billing.plan.list` ;
  - `PATCH /platform/saas-plans/{id}` — modification partielle avec `If-Match` obligatoire (200/409 `VERSION_CONFLICT`), `billing.plan.update`, audit `billing.plan.update` avec `before`/`after`.
- Offre candidate semée par la migration (ajustable par PATCH, aucun tarif) :

| Code | Utilisateurs | Sites | Véhicules | Traceurs GPS | Rétention docs |
|---|---|---|---|---|---|
| STARTER | 5 | 1 | 5 | 5 | 90 j |
| BUSINESS | 25 | 5 | 40 | 40 | 365 j |
| MINING_PRO | 100 | 20 | 200 | 250 | 1095 j |
| ENTERPRISE | illimité | illimité | illimité | illimité | illimité |

- UI PLATFORM_ADMIN : page **« Plans SaaS »** (`/plateforme/plans`, menu de l'espace plateforme) — liste des quotas avec mention « Illimité », création, modification (statut `RETIRED` désactivé dans l'interface). Le libellé rappelle qu'aucun tarif ni moyen de paiement n'est géré ici.

## Règles appliquées

- **Pas de tarif, pas de moyen de paiement** : conformément à la règle « pas d'intégration non approuvée », aucun prix ni provider n'est modélisé. La facturation paramétrable (GNF, taxes) est le lot 3, après arbitrage métier.
- **Isolation** : les rôles tenant (TENANT_ADMIN, DIRECTION, …) reçoivent 403 sur toutes les routes `/platform/saas-plans` — méta-données commerciales jamais exposées aux sociétés. Testé (négatif) dans `tests/test_billing_plans.py`.
- **Journalisation** : chaque création/modification produit un événement d'audit côté plateforme (`tenant_id` = tenant plateforme, `entity_type` = `saas_plan`).
- **Anti-dérive** : permissions `billing.plan.create/list/update` déclarées dans `authz_matrix.yaml` (tranche `2a`, seule portée `PLATFORM`) ; `permissions.generated.ts` et `docs/qa/ROLE_PAGE_ACTION_MATRIX.md` régénérés, `--check` verts.

## Limites assumées (prochains lots)

1. **Les quotas ne sont pas encore appliqués** : le catalogue décrit des limites, aucun contrôle d'admission n'existe tant qu'aucune société n'est rattachée à un plan (lot 2 : `tenant_subscription`, essai/activation/renouvellement/suspension, puis application des quotas aux provisioning users/sites/véhicules/traceurs).
2. `code` immuable : un changement de nom de code passe par un nouveau plan + retrait de l'ancien (préserve l'historique des abonnements à venir).
3. La rétention documentaire reste un quota déclaratif jusqu'à ce que le moteur de purge existant s'y abonne (lot 2/3).
4. Suppression volontairement absente : `RETIRED` couvre le retrait d'offre sans casser les références futures.

## Preuves

- Backend : `backend/tests/test_billing_plans.py` — 8 tests (seed des 4 candidats, CRUD, unicité 409, validation 422, ETag/version conflict, RETIRED terminal, 403 rôles tenant, 401 anonyme).
- Frontend : `frontend/src/pages/PlatformPlansPage.test.tsx` — 6 tests (affichage quotas/illimités, masquage sans permission, refus 403, création avec conversion vide→null, PATCH avec If-Match, bouton désactivé sur RETIRED).
- Migration rejouée localement (PostgreSQL 16 + PostGIS) : 4 plans semés, contraintes `ck_saas_plan_status`/`ck_saas_plan_quotas` actives.
- `ruff` (0.17.4) et `mypy` (2.4.1) : zéro erreur sur les fichiers du lot. `tsc --noEmit` : OK. Vitest : 240/240.
