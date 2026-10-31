# État réel du projet

État actualisé au 31 octobre 2026 sur `main` au commit `5782791edb897e43499fe03ec78eb4474ab45aef`.
Les constats proviennent du code, des migrations, des tests et des workflows exécutés ; une mention dans une roadmap n'est pas une preuve de fonctionnement.

## État GitHub

- PR #157 fusionnée (`be9fc8c`) : tableau de bord carburant React, tests unitaires et parcours E2E enrichi.
- PR #158 fusionnée (`5782791`) : shell PWA, cache statique strictement hors API, indicateur réseau et smoke de rechargement hors ligne.
- Aucune PR ouverte au démarrage du socle d'idempotence serveur.
- CI de la PR #158 réussie : backend, frontend, audit des dépendances, build, smoke navigateur et E2E d'isolation.
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
| Mode réseau dégradé | En cours | shell PWA livré ; socle d'idempotence transactionnelle développé dans `feature/offline-idempotency-core` ; cache métier et synchronisation d'un parcours restent absents |
| Pièces, magasins et pneus | Non complet | pas de véritable stock/mouvement/traçabilité ; notes libres seulement dans l'atelier |
| HSE | Non complet | rôles et quelques motifs, sans inspections/incidents/actions correctives structurés |
| Rentabilité et coût par équipement | Partiel | données opérationnelles disponibles, agrégation comptable insuffisante |

## Situation de livraison

Le noyau MVP est robuste, mais le dépôt ne prouve pas qu'un environnement pilote exécute le commit courant et la migration Alembic `0038`. La documentation de déploiement disponible décrit un état historique. Aucun exercice de restauration récent, SLO ni tableau de supervision n'est attesté dans le dépôt.

## Chantier actif

`feature/offline-idempotency-core` : fondation serveur pour les rejeux après coupure — clé limitée au tenant et à
l'utilisateur, empreinte de la requête sans conservation du corps, réservation concurrente et référence de rejeu
dans la même transaction que la mutation. Cette tranche ne rend encore aucune route métier synchronisable : le
premier parcours append-only et son outbox IndexedDB feront l'objet d'une PR distincte.

Les présents documents d'audit constituent la référence au commit audité ; les audits antérieurs éventuels restent des photographies historiques.
