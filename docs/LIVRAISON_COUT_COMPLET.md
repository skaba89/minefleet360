# Livraison — coût complet par engin

Branche `feature/vehicle-total-cost` (empilée sur `feature/hse-inspections`), migration `0055` (taux horaires de
main-d'œuvre, en ajout seul). Exploite la fiabilité (#302) et les pneus (#304).

## Principe : aucun chiffre inventé

**Coût complet = carburant + pièces + main-d'œuvre valorisée + pneumatiques.** Chaque composante et chaque total
portent un statut affiché :

| Statut | Signification |
|---|---|
| Complet | montant entièrement issu de valeurs enregistrées |
| Estimé | montant calculé par une méthode d'imputation documentée (carburant, pneus) |
| Partiel (minimum) | une partie des éléments n'est pas valorisée ; le montant est un minimum |
| Données insuffisantes | activité constatée sans valeur exploitable ; aucun montant n'est fourni et les éléments manquants sont listés |

Plusieurs devises dans un même total ⇒ « Données insuffisantes » (pas de conversion sans taux documenté).

## Méthodes

| Composante | Source et méthode |
|---|---|
| Carburant (estimé) | litres des sorties **approuvées** de la période × prix moyen pondéré des **livraisons sur commande** de la même cuve jusqu'à la fin de la période. Les réceptions de cuve sans commande ne portent pas de prix : sans livraison sur commande, « Données insuffisantes » |
| Pièces | sorties de magasin liées aux OT de l'engin, enregistrées dans la période (valorisation CMP existante) ; sortie non valorisée ⇒ partiel |
| Main-d'œuvre | minutes saisies sur les OT × taux horaire en vigueur à la date (taux du site, sinon de la société). **Aucun taux n'existait** : nouvelle table `maintenance_labour_rate`, saisie par la finance |
| Pneus (estimé) | km parcourus par chaque pneu sur l'engin dans la période (relevés des événements du pneu, montage par montage) × coût au km du pneu à date (achat + réparations / km mesurés) |

Dénominateurs : km et heures = somme des hausses entre relevés successifs de la période (une baisse — remplacement
de compteur — n'est pas comptée) ; tonnes = pesées valides (hors annulées et saisies dégradées non approuvées) ;
missions = missions terminées dans la période. Un coût unitaire n'est affiché que si le total n'est pas
« Données insuffisantes » et le dénominateur est positif.

## API et autorisations

| Route | Permission | Rôles |
|---|---|---|
| `GET /costs/vehicles?site_id&from&to` (30 j par défaut, 366 j max) | `cost.vehicle.read` | DIRECTION (T), OPS_MANAGER, WORKSHOP_CHIEF, FINANCE, AUDITOR (T) |
| `GET /costs/vehicles/{id}/history?months=1..24` (mois civils UTC) | `cost.vehicle.read` | idem |
| `GET`/`POST /costs/labour-rates` | `cost.labour_rate.manage` | DIRECTION (T), FINANCE ; taux société réservé à une portée société |

Réponse : composantes, total, statut, éléments manquants, km/heures/tonnes/missions, coûts au km/heure/tonne/mission,
totaux par site ; classement du plus coûteux au moins coûteux (« Données insuffisantes » en fin de liste).

## Interface

Menu « Coût complet » : période, tableau classé avec statut par composante et éléments manquants, coûts unitaires,
totaux par site, évolution sur 6 mois d'un engin, gestion des taux horaires (finance).

## Défaut corrigé en chemin (PR séparée #306, reportée ici)

`POST /fuel/purchases` et la décision d'achat répondaient **404 après avoir réussi** (réponse construite après le
commit, contexte tenant perdu). Sans ce correctif, aucune livraison sur commande n'aurait pu être enregistrée
proprement depuis l'interface, donc aucun prix de carburant.

## Vérifications

- `tests/test_costs.py` : jeu contrôlé (carburant à 12 000 GNF/L → 1 200 000 estimé ; 2 pièces à 150 000 ; 2 h à
  50 000/h ; total 1 600 000, coût par km ou par heure), taux manquant et carburant sans prix ⇒ insuffisant avec
  éléments manquants, devises mélangées jamais additionnées, portée site / inter-tenant / permissions / validations,
  pneus estimés au km, unicité des taux.
- Tests d'autorisation générés ; Vitest `CostsPage.test.tsx`.

## Limites

- « Autres coûts admissibles » (assurances, location, amortissement de l'engin, péages) non modélisés : à cadrer avec
  la finance avant d'ajouter des sources.
- Le kilométrage d'un montage de pneu antérieur au premier relevé de la période n'est pas compté (prudent).
- Pas d'export CSV/PDF ; historique en mois civils UTC (pas dans le fuseau du site).
