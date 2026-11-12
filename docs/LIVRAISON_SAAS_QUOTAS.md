# LIVRAISON SAAS LOT 2b — Application des quotas au provisionnement

**Base : main `b90d035` (post-PR #421 — gouvernance post-lot 3). Phase 6, lot 2b de la mission de commercialisation.**
Statut : livré, testé (suite complète pytest relancée, ruff/mypy/tsc propres, Vitest ciblé vert).

Cette livraison comble la limite n°1 laissée par les lots 1 et 2 (« les quotas ne sont pas encore
appliqués au provisionnement ») : les bornes affichées dans `/abonnement` sont désormais **réelles**.

## Périmètre livré

### Module `app/billing/quotas.py`

- `ensure_quota(auth, field)` : évalué **avant** chaque écriture de provisionnement. Un abonnement
  **vivant** (TRIAL, ACTIVE, SUSPENDED) borne la création ; **sans abonnement vivant** ou avec un
  quota **NULL** (= illimité), aucun refus — la plateforme et les sociétés sans abonnement continuent
  de fonctionner sans régression.
- Refus : **422 `QUOTA_EXCEEDED`** avec détail `{field, limit, usage}` et message français explicite
  (« La limite de votre formule est atteinte : changez de formule ou libérez de la place. ») —
  nouveau code au catalogue d'erreurs.
- Compteurs d'usage (cohérents avec les règles métier existantes) :
  - `max_users` : comptes INVITED + ACTIVE (les **désactivés** libèrent la place ; anonymisés exclus) ;
  - `max_sites` : tous les sites du tenant ;
  - `max_vehicles` : véhicules **non réformés** (RETIRED ne consomme pas — US-1.15) ;
  - `max_gps_trackers` : liaisons de traceurs **non révoquées** (révoquer libère la place).
- Non couvert en 2b : `document_retention_days` — appliqué par les purges automatiques (chantier
  séparé, noté dans les limites).

### Points d'application (4 provisionnements)

1. `POST /users` (invitation) → `max_users` ;
2. `POST /sites` → `max_sites` ;
3. `POST /vehicles` → `max_vehicles` ;
4. `POST /vehicles/{vehicle_id}/gps/tracker` → `max_gps_trackers` (les liaisons `phone:` incluses).

### UI

- Page `/abonnement` : le texte d'information annonce désormais que **les limites sont appliquées**
  (création refusée au-delà, avec libération de place par désactivation/réforme/révocation) —
  en remplacement de l'ancien libellé « à mesure de leur mise en service ».

## Règles appliquées

- **Aucun changement de schéma** (migration 0065 inchangée), aucune nouvelle permission, aucune
  route nouvelle : l'anti-dérive (`gen_permissions.py --check`, `generate_role_route_matrix.py
  --check`) et le contrat OpenAPI restent verts sans régénération.
- L'évaluation a lieu dans le contexte RLS de la société appelante (les tables lues sont
  tenant-scopées) ; l'abonnement vivant le plus récent fixe la borne.
- Les bornes s'appliquent aussi pendant un **essai** (TRIAL) ; l'annulation de l'abonnement (terminal)
  **lève** la borne — testé.

## Preuves

- Backend : `backend/tests/test_billing_quotas.py` — 8 tests :
  1. quota utilisateurs : 2e invitation refusée (détail field/limit/usage), désactivation libère ;
  2. quota sites : 2e site refusé ;
  3. quota véhicules : 2e véhicule refusé, réforme libère ;
  4. quota traceurs GPS : 2e liaison refusée, révocation libère ;
  5. quota NULL = illimité ;
  6. sans abonnement = aucune borne ;
  7. l'essai applique la borne, l'annulation la lève ;
  8. message français explicite.
- Suites connexes relancées vertes : matrice RBAC + isolation (`test_authz_matrix.py`,
  `test_database.py`), billing (lots 1–3), identité, organisation, flotte, GPS live/avancé.
- Frontend : `tsc --noEmit` OK ; Vitest ciblé vert (pages abonnements).
- Contrat OpenAPI : export + comparaison `git diff` = inchangé (vérifié localement comme en CI).

## Limites assumées (prochains lots)

1. `document_retention_days` : l'application effective passe par la commande de purge GPS
   (`minefleet purge-gps`) — à câbler avec la rétention documentaire (chantier séparé).
2. Pas de compteur temps réel dans l'UI (l'usage s'affiche via les listes existantes).
3. Le refus de provisionnement n'est pas audité en événement dédié (il s'agit d'un 422 de validation,
   pas d'un refus d'autorisation).
