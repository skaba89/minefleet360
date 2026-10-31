# Roadmap exécutable

Référence actualisée : 31 octobre 2026 sur `main@5782791`. Chaque chantier doit rester dans une PR `feature/...`, avec tests, risques, critères d'acceptation et validation humaine avant fusion.

## P0 — sécurité et fiabilité

| Ordre | Chantier | Livrables | Critères de sortie |
|---:|---|---|---|
| 1 | Contrat backend/frontend | export OpenAPI déterministe, types régénérés, garde CI | la CI détecte toute dérive ; typecheck, tests et build réussissent |
| 2 | DevSecOps et gouvernance | SAST, secrets, SBOM/scan image ; contrôle des règles `main` | aucune alerte critique ; revue/checks requis prouvés |
| 3 | Sauvegarde et restauration | sauvegarde chiffrée, restauration automatisée, runbook | exercice staging chronométré avec RPO/RTO |
| 4 | Observabilité | logs structurés centralisés, métriques, traces, SLO et alertes | incident simulé détecté et diagnostiqué |
| 5 | Déploiement pilote actuel | environnement staging au commit courant, migration `0033` et smoke | preuve du SHA, tête Alembic, healthchecks et rollback |

## P1 — complétude métier

| Ordre | Chantier | Portée incrémentale | Critères de sortie |
|---:|---|---|---|
| 6 | UI pompes carburant | pompes, relevés, rapprochements, anomalies | E2E et permissions site/tenant |
| 7 | Magasins et pièces | référentiel, stock, mouvements, réservations, inventaires | concurrence, valorisation, RLS et OT avec pièces |
| 8 | Pneus | position, montage, usure, réparation, historique et coût/km | traçabilité complète par pneu et véhicule |
| 9 | HSE | inspections, incidents, enquêtes, actions correctives | parcours E2E audité avec échéances |
| 10 | Coûts maintenance | pièces, main-d'œuvre, immobilisation, MTBF/MTTR | KPI réconciliés sur jeux de données contrôlés |
| 11 | GPS industrialisé | adaptateur fournisseur, trajets, géofences, alertes, rétention | test sandbox/réel, rejeu, charge et révocation |
| 12 | Productivité minière | disponibilité, utilisation, tonnes/heure et causes d'attente | indicateurs approuvés par un référent métier |

## P2 — industrialisation et expansion

- Tests de charge GPS, carburant et dispatch avec budgets p95/p99.
- CI/CD multi-environnements, artefacts signés et promotion contrôlée.
- Gestion centralisée et rotation des secrets.
- Mode mobile dégradé et résolution des conflits.
- Équipes/postes, sous-traitants, contrats, coût complet et rentabilité.
- Accessibilité WCAG, revue sécurité externe et tests de reprise après incident.

## Avancement vérifié

- Noyau tenant/RBAC/RLS/MFA/audit : livré et testé.
- Véhicules, conducteurs, affectations, missions, rotations et pesées : livrés et testés.
- Atelier, mécaniciens et maintenance préventive : socle avancé livré.
- Carburant : cuves, réceptions, réservations, double validation, inventaires, alertes, consommation, fournisseurs, achats, livraisons partielles, pompes et rapprochements backend livrés.
- GPS : téléphone, traceur authentifié, position courante et carte livrés ; intégration fournisseur/géofencing à faire.
- Réseau faible : socle PWA statique livré ; idempotence générique en cours ; aucune écriture métier n'est encore annoncée comme synchronisable.

## Plan incrémental réseau faible

| Lot | Portée | Garde-fous / critère de sortie |
|---:|---|---|
| 1 | PWA installable, shell statique, état réseau — **livré par #158** | aucune réponse `/api/` en cache ; build, tests unitaires et smoke navigateur réussis |
| 2 | Idempotence serveur générique — **en cours** | clé liée au tenant/utilisateur et hash du corps ; rejeu identique sans double effet ; contenu différent rejeté |
| 3 | Cache de lecture minimal | IndexedDB cloisonné et purgé à la déconnexion ; aucun jeton ni donnée d'un autre compte |
| 4 | Outbox d'un premier parcours terrain append-only | états local/synchronisé/rejeté visibles ; reprise FIFO ; erreurs 401/403/409/422 explicites |
| 5 | Extension contrôlée aux missions, pannes et constats | tests hors ligne/reconnexion/conflit par parcours et validation sur appareils terrain réels |

## Definition of Done

- Autorisations, isolation tenant/site, audit et erreurs testés négativement.
- Transaction et migration sûres, avec stratégie de retour documentée.
- API et types UI synchronisés ; UI accessible et testée lorsque le chantier est visible.
- Ruff, mypy, pytest/couverture, typecheck, Vitest, build et E2E pertinents réussis.
- Documentation d'exploitation et score de maturité mis à jour.
- Aucune fusion automatique par l'équipe IA : validation explicite du propriétaire requise.
