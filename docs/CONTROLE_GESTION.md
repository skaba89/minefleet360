# Contrôle de gestion et rentabilité minière

## Décisions financières (17 novembre 2026, propriétaire du projet)

| Sujet | Décision | Conséquence |
|---|---|---|
| Base des revenus | **Par contrat** : chaque contrat client ou de transport porte son mode de tarification (tonne **mesurée**, heure moteur, km ou forfait) ; revenu = tarif × quantité **mesurée** (pesées valides, horamètre, odomètre) | les revenus et marges ne seront calculés qu'à partir de quantités mesurées, jamais estimées (RM-071) |
| Coût d'un engin sous-traité | **Prix payé au prestataire + coûts internes supportés** (carburant délivré, pièces, main-d'œuvre), chaque composante affichée séparément | aucune double comptabilisation ; le prix payé dépend de la facturation prestataire (finalisation sous-traitants) |
| Budget prévisionnel | **Site × mois × composante** (carburant, pièces, main-d'œuvre, pneumatiques) | écarts calculés par composante contre le coût complet réel |

Principes permanents : aucune conversion de devise sans taux documenté ; tout montant porte un statut (complet,
estimé, partiel, insuffisant) ; chaque saisie financière est journalisée.

## Existant réutilisé (ne pas recréer)

Coût complet par engin — carburant estimé, pièces, main-d'œuvre valorisée, pneumatiques — avec coûts au km, à
l'heure, à la tonne mesurée et à la mission, totaux par site et historique (`docs/LIVRAISON_COUT_COMPLET.md`).

## Tranche 1 — Budget prévisionnel et écarts

- Migration additive `0073` : table `cost_budget` en **ajout seul** (déclencheur `tg_append_only`, RLS
  `SELECT, INSERT`) ; chaque révision est une nouvelle version, la plus récente fait foi.
- `POST /costs/budgets` (`cost.budget.manage` : DIRECTION, FINANCE tenant ou site) ; audit `cost.budget.create`.
- `GET /costs/budget-variance?site_id&from&to` (`cost.budget.read` : DIRECTION, OPS_MANAGER, FINANCE, AUDITOR ;
  12 mois au plus, 6 par défaut) : par site × mois × composante, budget (dernière version), réel (coût complet agrégé
  avec le statut le moins favorable), écart en montant et en pourcentage **seulement dans la même devise**, motif
  sinon (aucun budget, mois à venir, réel indisponible, devises différentes).
- Interface : section « Budget et écarts » de la page Coût complet, saisie réservée, export CSV.

## Tranche 2a — Tarifs des contrats de transport

- Réutilise le registre juridique existant : un tarif ne s'applique qu'à un contrat `TRANSPORT` **approuvé**
  (circuit quatre-yeux), sur un site couvert par l'appelant. Aucune nouvelle entité « contrat ».
- Migration additive `0074` : table `contract_tariff` en **ajout seul** ; modes `TONNE` (tonne mesurée),
  `HOUR` (heure moteur), `KM`, `MISSION` (forfait) ; prix > 0, devise ISO ; une version par date d'effet ; la
  version en vigueur à une date est la plus récente dont `valid_from` ≤ date.
- `POST /contract-tariffs` (`finance.tariff.manage` : DIRECTION, FINANCE) audité `finance.tariff.create` ;
  `GET /contract-tariffs` et `GET /contract-tariffs/contracts` (`finance.tariff.read` : DIRECTION, OPS_MANAGER,
  FINANCE, AUDITOR) — la finance voit les contrats facturables sans accès au registre juridique.
- Interface : section « Tarifs des contrats de transport » de la page Coût complet.

## Tranche 2b — Rattachement des missions à un contrat

- Migration additive `0075` : colonne facultative `mission.contract_id` (clé étrangère composite tenant).
- À la création d'une mission, contrat `TRANSPORT` **approuvé** du **même site** que l'affectation ; sinon
  `REFERENCE_NOT_FOUND` (autre site, autre tenant, inexistant) ou `not_billable`. Le renvoi hors ligne compare
  aussi le contrat (contrat différent → conflit). Audit `mission.create` enrichi du contrat.
- `GET /dispatch/billable-contracts` (permission de création de mission) : contrats rattachables des sites
  couverts. Formulaire de mission : sélecteur facultatif ; détail de mission : référence du contrat.

## Tranches suivantes

3. Revenus par mission, rotation et contrat ; marges brute et opérationnelle par site, engin et contrat.
4. Coût du parc sous-traité (prix payé + coûts internes) et comparaison parc propre / sous-traité — après la
   facturation prestataire.
5. Exports Excel/PDF des tableaux financiers (le CSV est disponible).
