# Audit ciblé — Atelier, ordres de travail et pièces détachées

Date : 2026-10-30. Source : code de la branche `main`, sans exécution locale des tests.

## 1. Existant vérifié

| Fonction | Preuve dans le code | État |
| --- | --- | --- |
| Signalement d'une panne | `maintenance/router.py` : `POST /work-orders` | Implémenté |
| Décision / affectation | `POST /work-orders/{id}/decision` ; `DECISIONS` dans `maintenance/service.py` | Implémenté |
| Exécution / diagnostic | `POST /work-orders/{id}/progress` ; `PROGRESS` | Implémenté |
| Attente des pièces | Transition `AWAIT_PARTS` vers `AWAITING_PARTS` | **Statut seulement**, aucun mouvement de stock vérifié |
| Main-d'œuvre | `POST /work-orders/{id}/labour`, `WorkOrderLabour` | Implémenté |
| Contrôle qualité / clôture | `QC_PASS` / `QC_FAIL`, séparation entre exécutant et valideur | Implémenté |
| Impacts sur l'exploitation | Immobilisation, suspension des missions, remise à disposition conditionnelle | Implémenté |
| Maintenance préventive | Plans, échéances, planification, clôture dédiée | Implémenté |
| Parcours UI atelier | `WorkshopPages.tsx`, routes `/atelier`, `/atelier/:workOrderId` | Présent |
| Tests métier | `backend/tests/test_maintenance.py` et famille `test_preventive_*.py` | Présents |

**Attention :** une route, une page ou un test existant ne certifie pas un parcours métier exhaustif. Aucun test local ni démonstration navigateur n'a été exécuté dans cette revue.

## 2. Risques et écarts

### P0 — Validations préproduction

1. Vérifier avec données réalistes l'enchaînement panne bloquante → immobilisation → suspension des missions → contrôle qualité → remise en service.
2. Confirmer les droits de lecture et d'écriture sur plusieurs sites et tenants, notamment sur les champs nominatifs de main-d'œuvre.
3. Vérifier la concurrence `If-Match`, l'idempotence des opérations sensibles et la restauration des données d'atelier.

### P1 — Manque fonctionnel majeur : pièces détachées

Le code examiné fournit `parts_note` et `AWAITING_PARTS`, mais pas de sous-système de stock de pièces complet vérifié, relié aux ordres de travail.

**Tranche 1 — catalogue et stock :** références, désignation, unité, magasin par site, stock physique, seuil minimum, séparation tenant/site, migrations RLS, API, tests.

**Tranche 2 — mouvements :** réception, sortie, ajustement et transferts ; transactions atomiques, contrôle de stock non négatif, clé d'idempotence, journal append-only et audit.

**Tranche 3 — intégration atelier :** réservation pour un OT, consommation effective, retour de pièces non utilisées, coûts par OT et historique chronologique, refus des opérations après clôture.

**Tranche 4 — interface :** consultation stock, demandes depuis l'OT, validation, alertes de rupture et E2E multi-sites.

### P1 — Couverture de coûts

- Valoriser les pièces et la main-d'œuvre sans mélanger des devises.
- Exposer le coût d'intervention et le coût cumulé par véhicule, avec tests de calcul et d'accès.

### P2 — Pneumatiques

- Gérer pneus individuels, positions, montage/démontage, permutations, réformes et coût par kilomètre.
- Lier les interventions aux ordres de travail existants au lieu de créer un cycle parallèle.

## 3. PR de développement proposée après validation de cet audit

**`feature/parts-catalog-stock-foundation`**

Périmètre minimal :
- Tables `part`, `part_store`, `part_stock_balance` ou modèle équivalent cohérent avec les conventions existantes.
- Contraintes tenant/site, RLS et index de référence uniques au bon périmètre.
- API autorisées de lecture du catalogue et du stock, avec pagination et filtres.
- Tests PostgreSQL (isolation tenant/site, contraintes et migrations), Ruff, mypy, OpenAPI.
- Première interface de lecture uniquement si les API sont stables.

**Hors périmètre de cette première tranche :** mouvement de sortie, valorisation, achat, réservation et mutation d'OT. Ces sujets exigeront des PR séparées.

## 4. Conditions de validation

Chaque PR doit passer `ci` et `e2e-isolation` ; conserver la matrice de permissions et les types OpenAPI synchronisés. Aucune auto-approbation ni auto-fusion.
