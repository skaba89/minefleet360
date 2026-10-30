# Score de maturité

Audit indépendant du 30 octobre 2026, basé sur `main@3c4bb02`.

## Méthode

Chaque capacité est notée de 0 à 100 à partir des preuves dans le code, les migrations, l'UI et les tests exécutés. Les moyennes de catégorie sont arithmétiques. Le score global applique les poids suivants : fonctionnel 40 %, métier minier 25 %, technique 35 %.

`Score global = 73,4 × 0,40 + 56,7 × 0,25 + 76,5 × 0,35 = 70,3/100`.

Le résultat proche de l'ancienne référence de 70 est une coïncidence : il a été recalculé capacité par capacité. Le noyau MVP est plus mature que 70, mais le périmètre cible complet est pénalisé par HSE, pièces/pneus, rentabilité et industrialisation.

## Fonctionnel — 73,4/100

| Capacité | Score | Preuve / lacune principale | Action et critère de validation |
|---|---:|---|---|
| Sociétés et sites | 92 | modèles, API, RLS et tests ; recette réelle manquante | import/recette multi-sites sans fuite tenant |
| Utilisateurs et permissions | 91 | RBAC, MFA, sessions, audit ; gouvernance GitHub non prouvée | revue d'accès et checks de branche attestés |
| Parc et véhicules | 88 | cycle riche et documents ; import terrain à valider | données réelles validées et E2E par catégorie |
| Conducteurs et habilitations | 86 | permis/qualifications ; alertes conformité limitées | blocage automatique testé sur habilitation expirée |
| Affectations | 84 | exclusions et E2E ; relève complexe à éprouver | scénario de poste concurrent réussi |
| Missions et rotations | 82 | états/événements/pesées ; optimisation absente | E2E d'exception et reprise réseau |
| Maintenance corrective/préventive | 78 | OT, mécaniciens, échéances ; coûts/fiabilité incomplets | OT chiffré et KPI MTBF/MTTR réconciliés |
| Carburant et achats | 83 | cycle très avancé ; UI pompes à finir | pompe réelle/sandbox et rapprochement visible |
| Documents réglementaires | 84 | véhicule robuste ; périmètre incomplet | alertes et conformité multi-entités |
| GPS et géolocalisation | 75 | téléphone/traceur/live ; intégration réelle absente | test fournisseur + trajets + géofence |
| Pesées et production | 82 | pesées cohérentes ; plan de production absent | tonnes/heure et rapprochement de poste |
| Pièces et pneus | 20 | pas de stock structuré | cycle stock et pneu complet avec audit |
| HSE | 25 | pas de module métier | inspection -> incident -> action E2E |
| Reporting/tableaux de bord | 58 | UI/KPI de base ; coûts/rentabilité incomplets | KPI métier sourcés et exports vérifiés |

## Métier minier — 56,7/100

| Capacité | Score | Preuve / lacune principale | Action et critère de validation |
|---|---:|---|---|
| Opérations quotidiennes | 82 | missions/rotations solides ; poste offline incomplet | clôture de poste E2E |
| Dispatching et transport | 82 | affectations/missions ; optimisation limitée | scénario multi-engins avec exceptions |
| Gestion des équipements | 85 | parc et compteurs riches | validation de référentiels miniers réels |
| Productivité/disponibilité | 65 | données disponibles, agrégation limitée | KPI disponibilité et utilisation réconciliés |
| Maintenance des engins | 78 | atelier/préventif présents | pièces, coûts, MTBF/MTTR |
| Approvisionnements | 72 | carburant/achats, pas de magasin pièces | cycle purchase-to-stock pièces |
| Coût par équipement | 40 | sources partielles, pas de coût unifié | grand livre par engin/période |
| Gestion des équipes | 55 | conducteurs/mécaniciens, roster limité | poste/équipe/relève complets |
| Prévention des incidents | 25 | HSE structuré absent | inspection et action corrective auditées |
| Sous-traitants | 20 | société externe seulement | contrats/SLA/facturation |
| Rentabilité des opérations | 20 | marge/revenus absents | marge par mission/site/client |

## Technique — 76,5/100

| Capacité | Score | Preuve / lacune principale | Action et critère de validation |
|---|---:|---|---|
| Architecture | 86 | monorepo modulaire et limites tenant | ADR à jour et contrôle de dépendances |
| Qualité du code | 84 | Ruff/mypy/types/tests | dette mesurée et aucune dérive de contrat |
| Base de données | 88 | PostGIS, contraintes, 33 migrations | restauration et migration sur copie réaliste |
| Sécurité | 87 | MFA, RBAC, secrets, audit | SAST/secrets/SBOM et revue externe |
| Isolation multi-tenant | 92 | RLS forcée et tests négatifs | test continu et revue de chaque nouvelle table |
| Tests automatisés | 89 | 3 115 backend, 55 frontend, E2E | charge, résilience et nouveaux modules |
| CI/CD | 78 | CI/E2E robustes ; CD multi-env absent | promotion signée dev/staging/prod |
| Performance | 70 | pagination/index/contraintes ; charge non mesurée | budgets p95 et tests GPS/dispatch |
| Sauvegarde/restauration | 58 | scripts/docs partiels ; exercice absent | restauration réussie avec RPO/RTO |
| Observabilité | 52 | logs/audit, pas de supervision prouvée | métriques/traces/SLO/alertes actives |
| Interface utilisateur | 78 | React responsive et tests ; modules incomplets | accessibilité et parcours terrain testés |
| Déploiement | 68 | conteneurs/docs ; état pilote courant non prouvé | commit/migration courant déployés et smoke |
| Résilience | 64 | intégrité/transactions ; DR/offline incomplets | tests de panne DB/réseau et runbook |

## Seuils de décision

- **70,3/100 actuel** : fondations solides, pas encore pilote minier complet.
- **80/100 MVP consolidé** : fermer R1/R2/R5 et livrer pièces minimum + HSE minimum.
- **85/100 pilote exploitable** : GPS réel, observabilité, restauration, coûts et validation terrain.
- **90/100 SaaS industrialisé** : CD multi-env, DR, charge, SLO et gouvernance éprouvés.
- **95/100 maturité élevée** : preuves sur plusieurs exploitations, sans présumer le résultat.
