# Livraison — fiabilité et coûts de maintenance par engin

Branche `feature/maintenance-reliability` (empilée sur `feature/hse-incidents`), sans migration.
Roadmap P1 n° 10 : le coût pièces par OT était calculé (`parts_cost_reader.py`) mais exposé par aucune route,
et MTBF/MTTR/disponibilité n'existaient pas.

## API

`GET /maintenance/reliability?site_id=&from=&to=` — permission `maintenance.reliability.read`
(DIRECTION T, OPS_MANAGER, WORKSHOP_CHIEF, FINANCE, AUDITOR T). Période par défaut : 90 jours jusqu'à maintenant ;
`to` est borné à maintenant ; période maximale 366 jours ; `from >= to` → 422 `END_BEFORE_START`.

## Définitions (période P)

| Indicateur | Calcul |
|---|---|
| Pannes | OT correctifs signalés dans P, hors rejetés/annulés |
| Immobilisation | union par engin des intervalles [signalement si panne bloquante, sinon début d'intervention ; clôture ou maintenant], découpés sur P — sans double comptage |
| Durée de service (par engin) | P bornée par la mise en service (début du jour, heure du site) et la réforme (fin du jour) ; engin hors service sur toute P **et** sans OT : omis ; OT hors des dates de service : durée P retenue et `service_dates_conflict = true` |
| Disponibilité | (durée de service − immobilisation) / durée de service ; immobilisation bornée à la durée de service |
| MTBF | (durée de service − immobilisation) / pannes ; vide sans panne |
| Totaux du parc | somme des durées de service réelles (`totals.service_hours`), et non « durée P × nombre d'engins » |
| MTTR (délai de remise en service) | moyenne (clôture − signalement) des OT correctifs clôturés dans P |
| Main-d'œuvre, pièces | OT (correctifs et préventifs) clôturés dans P ; pièces = sorties valorisées liées à l'OT ; `parts_cost_complete=false` si une sortie n'est pas valorisée (affiché « ≥ ») ; devises multiples → coût non agrégé |

Les engins réformés n'apparaissent que s'ils ont un OT dans la période. Un engin sans OT est « disponible selon
l'atelier » : ce n'est pas une mesure d'utilisation terrain (heures moteur, GPS), qui reste à construire.

## Interface

Menu « Fiabilité parc » (`/atelier/fiabilite`) : synthèse du parc, tableau par engin trié du moins disponible au
plus disponible, sélection de période.

## Vérifications

- `tests/test_maintenance_reliability.py` : union d'intervalles, jeu contrôlé (2 pannes, 15 h d'immobilisation,
  disponibilité 85 %, MTTR 12,5 h, MTBF 42,5 h, 1,5 h de main-d'œuvre), chevauchements, OT hors période,
  portée site, refus inter-tenant, validations de période ; tests d'autorisation générés.
- `frontend/src/pages/ReliabilityPage.test.tsx`.

## Limites

- ~~Durée de P identique pour tous les engins~~ — **levée le 16 novembre 2026** : durée de service par engin
  (`commissioned_on` / `decommissioned_on`, heure du site), test `test_reliability_uses_each_vehicle_service_window`.
  Un engin réformé (`RETIRED`) sans OT dans P reste omis, comme avant.
- Indicateurs rapportés au temps calendaire de service, pas aux heures de fonctionnement : MTBF « par heure moteur »
  et taux d'utilisation à partir des relevés de compteur horaire = tranche suivante.
- Pas encore de coût carburant ni de pneus : le « coût complet par engin » (P2) agrégera carburant + pièces +
  main-d'œuvre valorisée (taux horaire à définir) + pneus.
