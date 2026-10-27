# Livraison — lot 2a (missions de transport et rotations)

> Date : 2026-10-27. Cadrage : `PLAN_LOT2.md`. Stories : US-2.01 à US-2.04, US-2.08 (lecture).

## Contenu
- **Migration 0012** : `site_location`, `material`, `mission`, `mission_event` (ajout seul), `rotation` (dérivée). RLS forcée, clés étrangères composites, lieux du **même site** que la mission garantis par la base, une seule mission **en cours** par véhicule et par conducteur (index uniques partiels). Aucun champ de tonnage ni de position GPS (RM-070, RM-072).
- **Serveur** (`app/dispatch`) : lieux et matières ; mission créée « Affectée » sur une affectation du site ; avancement par événements (départ, arrivée au chargement, chargé, arrivée au déchargement, déchargé, terminée) ; rotations dérivées avec durée de cycle ; suspension motivée, reprise à l'étape d'avant, réaffectation à un autre véhicule (cycle en cours interrompu), annulation motivée ; départ refusé si l'affectation n'est pas active et conforme (RM-080) ; renvoi idempotent par `client_event_id` (RM-084) ; heure déclarée bornée et ordonnée (RM-083) ; audit de chaque étape.
- **Interface** : menu « Missions » (liste, création, fiche avec étapes, rotations, chronologie), onglet Administration › « Lieux et matières ». Un même identifiant d'événement est réutilisé tant qu'un envoi n'a pas abouti (pas de doublon sur double clic ou coupure réseau).
- **Permissions** `dispatch.*` (matrice §2.5 bis), tests d'autorisation et d'isolation générés.

## Vérifications exécutées
- Backend : ruff, mypy strict, **1730 tests** (couverture 92,7 %), dont `tests/test_dispatch.py` (10 scénarios : référentiels, références refusées, cycle complet à deux rotations, transitions invalides, départ non conforme, véhicule déjà en mission, renvoi sans doublon, panne et réaffectation, heure bornée, portée site et immuabilité en base).
- Frontend : `tsc`, Vitest 16, **Playwright 12** (dont création de lieux et matière, mission conduite jusqu'à la clôture, lecture seule).

## Non fait / suite
- Revue sécurité indépendante du lot 2a.
- Tranche 2b : pesées (tickets immuables, correction, mesuré vs estimé, saisie dégradée approuvée) et indicateurs ; tranche 2c : compteurs et documents.
- Missions `PLANNED` sans affectation (planification) ; déclarations tardives hors ligne (lot 4).
