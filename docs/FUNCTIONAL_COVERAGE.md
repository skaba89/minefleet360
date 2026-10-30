# Couverture fonctionnelle vérifiée

Référence : `main@3c4bb02`, audit du 30 octobre 2026.

Légende : **complet** signifie qu'un parcours cohérent existe dans le code et les tests ; **partiel** signifie que le socle existe mais ne couvre pas le cycle métier cible ; **absent** signifie qu'aucun module métier exploitable n'a été trouvé.

| Fonction | État | Preuves observées | Reste à faire / validation attendue |
|---|---|---|---|
| Sociétés et sites | Complet | tenant, site, portées, contraintes et RLS | recette pilote multi-sites et import initial |
| Utilisateurs et permissions | Complet | RBAC généré, MFA TOTP, sessions, tests négatifs | vérifier règles de protection de `main` et revue périodique des accès |
| Parc et véhicules | Complet | catégories, documents, compteurs, statuts, API/UI | import réel et règles spécifiques par catégorie d'engin |
| Conducteurs et habilitations | Complet | permis, qualifications, indisponibilités, contraintes | alertes de conformité et parcours RH étendu |
| Affectations | Complet | chevauchements interdits, conducteur/véhicule/site | recette de relève d'équipe en conditions réelles |
| Missions et rotations | Complet | cycle d'état, événements, dispatch, pesées | optimisation de dispatch et mode réseau dégradé |
| Maintenance corrective | Partiel avancé | OT, transitions, mécaniciens, main-d'œuvre, immobilisation | pièces structurées, coûts consolidés, contrôles de sortie atelier |
| Maintenance préventive | Partiel avancé | plans, échéances, compteurs, génération/lecture | calendrier UI complet, MTBF/MTTR, projections de charge |
| Carburant et achats | Partiel avancé | stock append-only, réservations, double validation, inventaires, fournisseurs, commandes, réceptions partielles, pompes | UI pompe/rapprochement, intégration physique et gestion d'anomalie complète |
| Documents réglementaires | Complet pour véhicule | documents immuables, retrait et validité | étendre aux équipements/HSE et stockage documentaire gouverné |
| GPS et géolocalisation | Partiel avancé | ingestion téléphone/traceur, secret révocable, carte temps réel | fournisseur réel, trajets, géofencing, alertes, rétention et consentement |
| Pesées et production | Partiel avancé | tickets, rotations, garde-fous d'intégrité | objectifs de production, rapprochement carrière/client et rendement |
| Pièces détachées | Absent comme stock structuré | notes libres d'OT uniquement | référentiel, magasins, lots, mouvements, réservations, inventaires et valorisation |
| Pneus | Absent comme cycle métier | motif panne/pneu seulement | positions, montages/démontages, usure, réparations, rechapage et coût/km |
| HSE | Absent comme module | rôles/motifs génériques seulement | inspections, incidents, enquêtes, actions, échéances et indicateurs |
| Reporting et tableaux de bord | Partiel | dashboard, indicateurs opérationnels et graphiques | KPI miniers vérifiés, exports, coûts, rentabilité et drill-down |
| Sous-traitants | Partiel faible | type d'emploi/société externe conducteur | contrats, SLA, facturation, accès et performance par prestataire |

## Incohérence de contrat identifiée

Les routes `/api/v1/fuel/pumps`, relevés de compteur et rapprochements existent depuis les PR #119/#120, alors que `frontend/src/api/schema.d.ts` n'avait pas été régénéré. Le chantier actif ajoute un export déterministe et fait échouer la CI si ce contrat dérive à nouveau.
