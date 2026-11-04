# Matrice des fonctionnalités — état vérifié

État au 4 novembre 2026, `main@000ee08`. Classement (mission, §2) :
**1** fonctionnelle et testée · **2** fonctionnelle avec limitations · **3** partielle · **4** présente mais défaillante ·
**5** absente · **6** obsolète ou à remplacer.

« Testée » = tests automatisés exécutés en CI (pytest, Vitest, Playwright). Aucune fonction n'a encore été validée
par des utilisateurs réels.

## Socle SaaS et sécurité

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| Sociétés, sites, utilisateurs, rôles (RBAC par site) | 1 | `organization`, `identity`, `authz_matrix.yaml` (115 permissions), tests d'isolation |
| MFA (TOTP), sessions, réinitialisation | 1 | `mfa_service`, `test_mfa*`, spec `mfa.spec.ts` |
| Isolation multi-tenant (RLS forcée) | 1 | migrations `apply_tenant_rls`, job CI `tenant-isolation` |
| Journal d'audit | 1 | `audit.contracts.record` dans chaque écriture métier |
| Abonnements, quotas, facturation | 5 | aucun module |
| Onboarding autonome, portail client | 5 | création de société par l'administrateur plateforme uniquement |
| Anglais (i18n) | 5 | interface en français seulement |
| Thème sombre | 5 | — |

## Flotte, conducteurs, opérations

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| Parc (catégories, statuts, transferts, documents réglementaires) | 1 | `fleet`, spec `vehicule-documents.spec.ts` |
| Conducteurs, permis, habilitations | 1 | `workforce`, éligibilité d'affectation |
| Affectations engin/conducteur | 1 | `assignment`, spec `affectations.spec.ts` |
| Missions, rotations, événements | 1 | `dispatch`, spec `missions.spec.ts` |
| Pesées (pont-bascule, saisie dégradée approuvée) | 1 | `dispatch/weighing.py`, spec `pesees.spec.ts` |
| Indicateurs d'exploitation (tonnes, rotations, cycles) | 2 | `dispatch-indicators` ; pas de tableaux de bord par rôle |
| Temps de conduite et repos, score conducteur | 5 | — |
| Sous-traitants (portail, contrats) | 5 | — |
| Engins loués | 3 | statut de propriété au parc ; pas de contrat de location |

## GPS et télématique

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| Ingestion traceur authentifiée (secret, séquence, positions tardives) | 1 | `gps_gateway_ingestion`, `gps_tracker_ingest` |
| Partage de position par téléphone (consentement, arrêt) | 1 | `/me/gps/shares` |
| Dernières positions, fraîcheur du signal | 1 | `/vehicles/gps/latest` (lecture indexée, #331) |
| Trajet : distance, arrêts, trous, points tardifs | 1 | `/vehicles/{id}/gps/track`, accès journalisé avec finalité |
| Géofences et événements d'entrée/sortie | 2 | `gps_history.py` ; événements calculés à la lecture, sans alerte |
| Simulateur de positions (démo) | 1 | `minefleet demo live-feed` |
| **Carte interactive multi-engins** | 5 | rafraîchissement par liste toutes les 15 s ; carte OpenStreetMap intégrée (iframe) d'un seul engin |
| **Replay animé d'un trajet** | 5 | tracé SVG statique sans fond de carte |
| Cap / direction | 5 | non stocké |
| Alertes (vitesse, géofence, perte de signal, hors horaires) | 5 | aucune règle ni notification |
| Fournisseur GPS réel, OBD-II, CAN | 5 | contrat d'adaptateur documenté (`GPS_FOURNISSEUR_CAHIER.md`) ; aucun fournisseur branché |

## Maintenance, stock, carburant, HSE

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| OT correctifs (immobilisation, séparation des tâches, main-d'œuvre) | 1 | spec `atelier.spec.ts` |
| Plans préventifs et dernier entretien validé | 1 | #336 |
| Finalisation sans approbation de compteur | 3 | #337 en revue |
| Évaluation et liste des échéances | 3 | tranche B2 en cours ; tâche quotidienne absente |
| Fiabilité (MTBF/MTTR) | 2 | `reliability.py` ; dépend de l'historique |
| Maintenance prédictive | 5 | — |
| Planning atelier | 5 | — |
| Pièces : stock, réapprovisionnement, commandes, réceptions valorisées | 1 | `parts_*`, `purchase_order_router` |
| Pneus (montage, usure, coût au km) | 2 | spec `pneus.spec.ts` ; la méthode de coût impute tout le prix au pneu neuf (décision ouverte) |
| Batteries | 5 | — |
| Codes-barres / QR | 5 | — |
| Carburant : cuves, pompes, distributions, achats, anomalies | 1 | `fuel`, specs `carburant` et `fuel-anomalies` |
| Coût complet par engin (carburant, pièces, main-d'œuvre, pneus) | 1 | `costs` (#333) |
| HSE : incidents, actions correctives, inspections, digest e-mail | 1 | `hse`, spec `hse-inspections.spec.ts` |
| HSE hors ligne | 1 | `HseOffline.tsx`, spec `e2e-field/hse-offline.spec.ts` |

## Analytics, IA, mobile

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| Exports CSV (≤ 5 000 lignes) | 1 | `lib/csv.ts` (neutralisation des formules) |
| Exports PDF / Excel, rapports planifiés | 5 | — |
| Tableaux de bord par rôle | 3 | tableau de bord flotte et carburant ; direction, maintenance et HSE partiels |
| Copilot IA | 5 | — |
| PWA installable | 2 | `sw.js`, `lib/pwa.ts` |
| Hors ligne : missions, maintenance, carburant | 5 | seul le HSE fonctionne hors ligne |
| Application conducteur dédiée | 3 | partage GPS et saisie terrain dans la PWA |

## Exploitation

| Fonction | Classe | Preuve / limite |
|---|:-:|---|
| Déploiement de recette (OVH, proxy commun) | 2 | `DEPLOIEMENT_OVH.md` ; instance de recette uniquement |
| Sauvegardes chiffrées hors machine, vérification de restauration | 2 | `backup.sh`, `verify-restore.sh` ; destination à choisir par le client |
| Supervision (sondes, alertes e-mail) | 2 | `probe-*.sh`, `run-alert-monitor.py` ; pas de métriques ni de traces |
| Données de démonstration (profils small à large) | 1 | `minefleet demo seed/verify` 38/38 |
