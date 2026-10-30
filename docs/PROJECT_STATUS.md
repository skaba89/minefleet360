# État réel du projet

État actualisé au 30 octobre 2026 sur `main` au commit `be9fc8c3f766049a16290f5d4276af82dfc23408`.
Les constats proviennent du code, des migrations, des tests et des workflows exécutés ; une mention dans une roadmap n'est pas une preuve de fonctionnement.

## État GitHub

- PR #156 fusionnée (`9ba93f0`) : synthèse API du tableau de bord carburant.
- PR #157 fusionnée (`be9fc8c`) : tableau de bord carburant React, tests unitaires et parcours E2E enrichi.
- Aucune PR ouverte au démarrage du chantier hors ligne.
- CI de la PR #157 réussie : Ruff, mypy, migrations, 3 479 tests backend, couverture 89,83 %, audit npm, 57 tests frontend, build et smoke navigateur.
- Workflow E2E d'isolation de la PR #157 réussi, scénario carburant enrichi inclus.
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
| Mode réseau dégradé | En cours | shell PWA et indicateur réseau dans `feature/offline-app-shell` ; cache métier, idempotence et synchronisation des écritures absents |
| Pièces, magasins et pneus | Non complet | pas de véritable stock/mouvement/traçabilité ; notes libres seulement dans l'atelier |
| HSE | Non complet | rôles et quelques motifs, sans inspections/incidents/actions correctives structurés |
| Rentabilité et coût par équipement | Partiel | données opérationnelles disponibles, agrégation comptable insuffisante |

## Situation de livraison

Le noyau MVP est robuste, mais le dépôt ne prouve pas qu'un environnement pilote exécute le commit courant et la migration Alembic `0033`. La documentation de déploiement disponible décrit un état historique. Aucun exercice de restauration récent, SLO ni tableau de supervision n'est attesté dans le dépôt.

## Chantier actif

`feature/offline-app-shell` : première tranche adaptée aux réseaux faibles — manifeste installable, cache statique,
indicateur de connectivité et limites affichées. Les réponses API ne sont pas mises en cache et les mutations ne
sont pas rejouées tant que l'idempotence serveur, le cloisonnement local et la résolution des conflits ne sont pas livrés.

Les présents documents d'audit constituent la référence au commit audité ; les audits antérieurs éventuels restent des photographies historiques.
