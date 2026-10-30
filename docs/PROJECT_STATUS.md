# État réel du projet

Audit arrêté au 30 octobre 2026 sur `main` au commit `3c4bb02231cd530ca72e8ecedc18d1e841819ad8`.
Les constats proviennent du code, des migrations, des tests et des workflows exécutés ; une mention dans une roadmap n'est pas une preuve de fonctionnement.

## État GitHub

- PR #118 fusionnée (`ad09c82`) : parcours E2E d'inventaire carburant.
- PR #119 fusionnée (`01a358d`) : pompes et compteurs cumulés.
- PR #120 fusionnée (`3c4bb02`) : rapprochement compteur de pompe / sorties approuvées.
- Aucune PR ouverte au démarrage de cet audit.
- CI de `main` 41033170043 réussie : Ruff, mypy, migrations, 3 115 tests backend, couverture 89,71 %, audits Python et npm, 55 tests frontend, build et smoke navigateur.
- Workflow E2E d'isolation 41033169734 réussi.
- La protection de branche n'a pas pu être vérifiée : l'intégration GitHub répond `403 Resource not accessible by integration` sur cette ressource.

## Périmètre confirmé par le code

| Domaine | État | Preuves principales |
|---|---|---|
| Multi-tenant, sites, utilisateurs, RBAC, MFA, audit | Opérationnel et fortement testé | RLS PostgreSQL forcée, matrice d'autorisations générée, TOTP, révocation de sessions, journal immuable |
| Véhicules, conducteurs, habilitations, affectations | Opérationnel | modèles, API, migrations, UI et tests d'isolation |
| Missions, rotations, pesées | Opérationnel | transitions métier, événements append-only, contraintes et E2E |
| Atelier et maintenance préventive | Opérationnel avec compléments métier | ordres, mécaniciens, main-d'œuvre, échéances, compteurs ; coûts pièces/MTBF/MTTR incomplets |
| Carburant et achats | Avancé côté backend et UI principale | cuves, réservations, double validation, inventaires, fournisseurs, commandes, livraisons partielles, alertes, pompes et rapprochements |
| GPS temps réel | Socle opérationnel | téléphone, traceur authentifié, position courante et carte ; fournisseur réel, géofencing et historique avancé absents |
| Pièces, magasins et pneus | Non complet | pas de véritable stock/mouvement/traçabilité ; notes libres seulement dans l'atelier |
| HSE | Non complet | rôles et quelques motifs, sans inspections/incidents/actions correctives structurés |
| Rentabilité et coût par équipement | Partiel | données opérationnelles disponibles, agrégation comptable insuffisante |

## Situation de livraison

Le noyau MVP est robuste, mais le dépôt ne prouve pas qu'un environnement pilote exécute le commit courant et la migration Alembic `0033`. La documentation de déploiement disponible décrit un état historique. Aucun exercice de restauration récent, SLO ni tableau de supervision n'est attesté dans le dépôt.

## Chantier actif

`feature/audit-contract-quality-gate` : régénération déterministe des types OpenAPI, contrôle de dérive en CI et mise à jour des documents d'audit. Ce chantier ne modifie ni schéma de base de données ni règle d'autorisation.

Les présents documents d'audit constituent la référence au commit audité ; les audits antérieurs éventuels restent des photographies historiques.
