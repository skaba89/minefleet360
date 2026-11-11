# LIVRAISON SAAS LOT 3 — Facturation paramétrable (sans activation de paiement)

**Base : main `0dfedba` (post-PR #419 — lot 2 abonnements). Phase 6, lot 3 de la mission de commercialisation.**
Statut : livré, testé (5 645 tests pytest, 256 tests Vitest, ruff/mypy/tsc propres).

Règle respectée : **aucun moyen de paiement, aucun provider, aucun encaissement**. La facture est un
document interne de traçabilité ; le règlement se gère hors application tant qu'aucun paiement n'est
approuvé (règle « pas d'intégration non approuvée »).

## Périmètre livré

### Modèle (migration 0067, additive)

- `saas_plan` : deux colonnes de tarification paramétrable — `price_monthly_gnf` (entier GNF,
  NULL = plan non tarifé) et `billing_period` (`MONTHLY`/`ANNUAL`). Contraintes CHECK ; le PATCH
  plan permet de fixer ou remettre à NULL (non tarifé) comme pour les quotas.
- `billing_invoice_sequence` : compteur de numérotation par année (table plateforme, hors RLS
  applicative comme `saas_plan`). Incrémentation atomique en base (`INSERT … ON CONFLICT …
  UPDATE … RETURNING`).
- `billing_invoice` (RLS applicative classique) : `number` lisible `MF-<année>-<numéro sur 5`
  (unique), cycle **DRAFT → ISSUED → VOIDED** (VOIDED terminal), devise `GNF` figée, taxe en
  **points de base** (0–10 000, 1 800 = 18 %), période facturée optionnelle, montants figés à la
  création (`subtotal_gnf`, `tax_gnf`, `total_gnf` en BIGINT — CHECK `total = subtotal + tax`),
  horodatages d'émission/annulation + motif d'annulation (3–500 caractères). Contraintes
  `(status ⇔ timestamps)` en base.
- `billing_invoice_line` : lignes immuables (GRANT `SELECT, INSERT` uniquement), position
  séquentielle unique par facture (1–50), `amount = quantity × unit_price` vérifié par CHECK en
  base, tenant_id NOT NULL + RLS.

### API

Gestion plateforme (PLATFORM_ADMIN, permission `billing.invoice.manage`, bascule RLS par le
tenant_id du chemin — même pattern que les abonnements) :

- `POST /platform/tenants/{tenant_id}/invoices` — création DRAFT : lignes fournies, ou préremplies
  depuis le tarif du plan si `subscription_id` est fourni sans lignes (422 `PLAN_NOT_PRICED` si le
  plan n'a pas de tarif ; 422 `SUBSCRIPTION_CANCELLED` si l'abonnement est annulé ; 422
  `INVOICE_LINES_REQUIRED` sans abonnement ni ligne) ;
- `GET /platform/tenants/{tenant_id}/invoices` — historique paginé (filtre `?status=`) ;
- `GET /platform/tenants/{tenant_id}/invoices/{invoice_id}` — détail avec lignes (ETag) ;
- `POST .../{invoice_id}/issue` — DRAFT → ISSUED, document figé (If-Match obligatoire) ;
- `POST .../{invoice_id}/void` — annulation motivée, terminal (If-Match).

Lecture société (RLS naturelle, permission `billing.invoice.read` → TENANT_ADMIN, DIRECTION,
FINANCE, AUDITOR) : `GET /tenant/invoices` (paginé) et `GET /tenant/invoices/{invoice_id}` (détail).
Une facture d'une autre société est indiscernable d'une facture inexistante (404 neutre — testé).
Aucune route d'encaissement n'existe.

### Statut effectif de l'essai (décision lot 3 : calcul à la lecture)

- `effective_status` ajouté aux vues abonnement (plateforme et société) : un essai daté échue
  s'affiche **EXPIRED** sans aucune écriture en base — le statut stocké reste TRIAL et la
  transition (activation, suspension, annulation) reste disponible. Aucun scheduler, aucune
  écriture implicite (réponse à la limite 2 du lot 2).
- UI : les deux pages d'abonnement affichent le statut effectif (« Essai expiré ») à côté du
  statut enregistré.

### UI

- Page plateforme **« Facturation »** (`/plateforme/facturation`) : sélection d'une société,
  historique (numéro, statut, période, total GNF), création (société + abonnement facultatif +
  taxe en points de base + lignes de saisie libre), émission/annulation contextuelles avec
  If-Match et motif, détail des lignes au clic sur le numéro (table avec sous-total, taxe, total).
- Page société **« Factures »** (`/factures`, menu principal pour les rôles autorisés) : liste et
  détail en lecture seule, libellé explicite « le règlement se gère avec l'équipe MineFleet 360 :
  aucun moyen de paiement n'est intégré ».
- Montants affichés au format GNF (`17 700 000 GNF`).

## Règles appliquées

- **RLS d'abord** : la plateforme ne touche une facture qu'après `set_tenant_context(tenant_id)`
  dérivé du chemin ; la lecture société passe par la RLS naturelle.
- **Audit** : `billing.invoice.create/issue/void` écrits dans la société cible avec before/after.
- **Anti-dérive** : `billing.invoice.manage` (portée PLATFORM seule) et `billing.invoice.read`
  (TENANT_ADMIN/DIRECTION/FINANCE/AUDITOR, portée TENANT) déclarées dans `authz_matrix.yaml`
  (tranche 2a) ; `permissions.generated.ts`, `schema.d.ts` et `ROLE_PAGE_ACTION_MATRIX.md`
  régénérés, `--check` verts.
- **Montants** : calculs en entiers (GNF n'a pas de subdivision) ; taxe arrondie à l'unité la plus
  proche ; une facture créée depuis le tarif d'un plan n'est PAS modifiée par un changement
  ultérieur du tarif (montants figés — testé).

## Limites assumées (prochains lots)

1. **Quotas non appliqués au provisionnement** (lot 2b, inchangé).
2. Pas de relance/échéancier de règlement : la facture ISSUED n'a pas de suivi « payée » — le
   règlement reste hors application (ouvrable au lot 4 si un processus de suivi est approuvé).
3. La numérotation est séquentielle par année civile plateforme (pas de série par société) —
   suffisant pour le pilote, à arbitrer avec l'expert-comptable avant la mise en production.
4. Pas de PDF imprimable : la facture est consultable dans l'application (le lot 4 support/
   onboarding peut ajouter une exportation).

## Preuves

- Backend : `backend/tests/test_billing_invoices.py` — 11 tests (montants+numérotation, facture
  depuis plan tarifé + lecture société, plan non tarifé 422, montants figés après changement de
  tarif, cycle issue/void terminal + conflits, abonnement annulé 422, cross-tenant 404, permissions
  par rôle, société inconnue 404, essai expiré = statut effectif sans écriture + activation possible,
  tarif visible côté société).
- Matrice générée et isolation : `test_authz_matrix.py` (ST01/ST02 exercés sur les 5 nouvelles
  routes, facture du monde RBAC) et `test_database.py` (DBT40 : `billing_invoice`/`billing_invoice_line`
  RLS forcée, DBT01 : zéro ligne hors contexte) verts.
- Suite complète locale : **5 645 tests pytest passés** (PostgreSQL 16 + PostGIS réel, base
  `minefleet_test`), ruff + mypy propres.
- Frontend : `PlatformInvoicesPage.test.tsx` (6 tests) + `TenantInvoicesPage.test.tsx` (3 tests) ;
  Vitest **256/256**, `tsc --noEmit` OK.
- Migration rejouée localement (downgrade/upgrade 0066 ↔ 0067) : CHECK, index unique, policy RLS
  et triggers présents.
