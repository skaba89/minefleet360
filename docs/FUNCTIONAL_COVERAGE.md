# Couverture fonctionnelle vérifiée

Référence : `main@c34d322` (PR #435), recalibrage du 12 novembre 2026 (P1 item 5) — état antérieur : audit du 30 octobre 2026 sur `main@3c4bb02`.

Légende : **complet** signifie qu'un parcours cohérent existe dans le code et les tests ; **partiel** signifie que le socle existe mais ne couvre pas le cycle métier cible ; **absent** signifie qu'aucun module métier exploitable n'a été trouvé. « Complet » et « partiel avancé » restent des preuves de **code et de tests** : aucune ligne ne vaut validation terrain (matériel, Android physique, données réelles).

| Fonction | État | Preuves observées | Reste à faire / validation attendue |
|---|---|---|---|
| Sociétés et sites | Complet | tenant, site, portées, contraintes et RLS | recette pilote multi-sites et import initial |
| Utilisateurs et permissions | Complet | RBAC généré, MFA TOTP, sessions révocables, tests négatifs ; socle E2E d'accès direct 34 routes × 13 rôles (#408) | vérifier règles de protection de `main` et revue périodique des accès |
| Parc et véhicules | Complet | catégories, documents, compteurs, statuts, API/UI | import réel et règles spécifiques par catégorie d'engin |
| Conducteurs et habilitations | Complet | permis, qualifications, indisponibilités, contraintes | alertes de conformité et parcours RH étendu |
| Affectations | Complet | chevauchements interdits, conducteur/véhicule/site | recette de relève d'équipe en conditions réelles |
| Missions et rotations | Complet | cycle d'état, événements, dispatch, pesées | optimisation de dispatch et mode réseau dégradé (hors HSE) |
| Maintenance corrective | Partiel avancé | OT, transitions, mécaniciens, main-d'œuvre, immobilisation ; pièces structurées liées aux OT | MTBF/MTTR réconciliés, contrôles de sortie atelier |
| Maintenance préventive | Partiel avancé | plans, échéances, compteurs, génération/lecture ; déclarations, révision avec historique conservé et suspension motivée prouvés depuis l'UI (#430) | calendrier UI complet, projections de charge |
| Carburant et achats | Partiel avancé | stock append-only, réservations, double validation, inventaires, fournisseurs, commandes, réceptions partielles, pompes | UI pompe/rapprochement, intégration physique et gestion d'anomalie complète |
| Documents réglementaires | Complet véhicule + cycle documentaire gouverné | documents immuables, retrait et validité ; dépôt de justificatif à empreinte SHA-256 calculée au client, scan antivirus (EICAR refusé), vérification quatre-yeux et soumission conditionnée dans `/juridique` (#432), prouvé navigateur sur harnais S3/ClamAV | étendre aux équipements/HSE |
| GPS et géolocalisation | Complet côté logiciel | ingestion authentifiée téléphone/traceur, secret révocable, carte live multi-engins, trajets/replay, cap, géofences, alertes, notification, SSE événementiel PostgreSQL, repli/reconnexion (#340–#359 ; docs/GPS_*) | fournisseur réel certifié (essai matériel), rétention et consentement (revue juridique), Android physique |
| Pesées et production | Partiel avancé | tickets, rotations, garde-fous d'intégrité | objectifs de production, rapprochement carrière/client et rendement |
| Pièces détachées | Partiel avancé | CMP, magasins, mouvements, réservations concurrentes, réapprovisionnement à décision séparée quatre-yeux, valorisation (`VALORISATION_STOCKS.md`) ; échéances et commandes depuis l'UI (#409, #430) | inventaires pièces réels, import magasin initial, rattachement complet au coût par engin |
| Pneus | Partiel avancé | tables `tyre`/`tyre_event` (migration 0053), montages/démontages, usure, coût intégré au coût complet (#304, `LIVRAISON_PNEUS.md`) | mesures d'usure terrain réelles, rechapage |
| HSE | Partiel avancé | incidents, enquêtes, actions correctives (migration 0052) ; inspections, checklists, non-conformités, preuves photo (migration 0054) ; double regard prouvé E2E ; déclaration d'incident hors ligne de bout en bout (#411, `LIVRAISON_HSE1/2.md`, `LIVRAISON_OFFLINE_HSE.md`) | Android physique et réseau mobile réel, inspections hors ligne étendues (après arbitrage produit) |
| Reporting et tableaux de bord | Partiel avancé | dashboard, indicateurs opérationnels, coût complet par engin (migration 0055 : carburant + pièces + main-d'œuvre valorisée + pneumatiques), KPI fiabilité alimentés par l'OT immobilisant (#430) | rentabilité/marge, exports vérifiés, drill-down |
| Sous-traitants | Partiel faible | type d'emploi/société externe conducteur | contrats, SLA, facturation, accès et performance par prestataire |

## Suivi de la cohérence de contrat

L'incohérence identifiée le 30 octobre (routes `/api/v1/fuel/pumps` présentes alors que `frontend/src/api/schema.d.ts` n'avait pas été régénéré) est **résolue** : la CI exporte l'OpenAPI de façon déterministe, régénère `schema.d.ts` et fait échouer le job sur toute dérive (`ci.yml` : `scripts/export_openapi.py` puis `git diff --exit-code -- src/api/schema.d.ts`), complétée par la fermeture d'OpenAPI et des docs en production (#374). La garde est verte à chaque PR vérifiée depuis.
