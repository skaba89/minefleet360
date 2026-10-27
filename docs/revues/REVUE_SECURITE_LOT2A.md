# Revue sécurité — lot 2a : missions de transport et rotations (PR #13, correctifs PR suivante)

> Date : 2026-10-27. Objet : `backend/app/dispatch/*`, migration `0012_dispatch`, `assignment/contracts.py` (`running_blockers`), `authz_matrix.yaml` (`dispatch.*`), `errors.py`, pages web Missions, Détail de mission et Lieux et matières.

## 1. Revue indépendante (agent security-engineer distinct, lecture du code)
Aucun constat critique ni élevé. Vérifiés sans problème : isolation des tenants (RLS sur les 5 tables, clés étrangères composites), lieux limités au site de la mission, portée site (même 404 qu'une ligne inexistante), une mission en cours par véhicule et par conducteur (index uniques partiels), machine à états, événements en ajout seul, bornes de `occurred_at`, aucun tonnage ni GPS, injection, échappement côté web.

| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| L2A-R-01 | Moyenne | La réaffectation remplaçait véhicule, conducteur et affectation sans trace dans la chronologie ni dans l'audit | **Corrigé** : chaque événement porte l'affectation en vigueur (`mission_event.vehicle_assignment_id`, clé étrangère composite, migration `0013` qui complète les événements existants) ; l'audit `mission.reassigned` consigne avant/après de `vehicle_assignment_id`, `vehicle_id`, `driver_id` ; test `test_reassignment_is_traceable` |
| L2A-R-02 | Moyenne | Nom du conducteur renvoyé à FINANCE et au chef d'atelier (portée société), alors que l'API des affectations le leur refuse (D-10) | **Corrigé** : `driver_id` et `driver_display_name` à `null` sans `assignment.vehicle_assignment.read` sur le site ; documenté dans MATRICE_RBAC §2.5 bis ; test `test_driver_name_follows_assignment_read_rights` |
| L2A-R-03 | Faible à moyenne | Conformité et fin d'affectation évaluées à l'heure déclarée : un départ antidaté passait après l'échéance | **Corrigé** : contrôles à l'heure serveur, l'heure déclarée ne sert qu'à la chronologie ; test `test_departure_checks_use_server_time`. Résiduel accepté : la fenêtre d'antidatage de 15 min reste utilisable pour la chronologie (saisie différée sur le terrain) ; `recorded_at` garde l'heure réelle d'enregistrement |
| L2A-R-04 | Faible | Rotations sans durée minimale ni plafond ; détail de mission non paginé | **Ouvert, lot 2b** : durée minimale paramétrable, plafond (`planned_rotations`), indicateur de cohérence, pagination du détail. Détectable aujourd'hui par l'audit et `recorded_at` |
| L2A-R-05 | Faible | Un `client_event_id` d'une autre mission du tenant était reconnu (409 distinct) | **Corrigé** : recherche limitée à la mission demandée, après le contrôle de portée ; un identifiant pris ailleurs échoue sur la contrainte d'unicité en `CONFLICT` ordinaire ; test |
| L2A-R-06 | Faible | Deux renvois simultanés du même événement : le second recevait `VERSION_CONFLICT` au lieu du rejeu | **Corrigé** : recherche du renvoi sous le verrou de la mission, avant le contrôle de version |
| L2A-R-07 | Faible | Fermer une affectation (fin, politique `close` D-41) ne suspend pas la mission en cours | **Ouvert, lot 2b** : suspension automatique (événement `SYSTEM`). D'ici là, la reprise et le départ re-contrôlent l'éligibilité |
| L2A-R-08 | Faible | Création de mission non idempotente (doublon après coupure réseau) | **Ouvert, lot 2b** : `client_request_id` optionnel. Les doublons ne peuvent pas rouler en même temps (RM-081) et s'annulent |
| L2A-R-09 | Faible | Listes de lieux et de matières non paginées | **Accepté** : volumes faibles, accès authentifié ; plafond à ajouter si un client dépasse quelques centaines de lieux |
| L2A-R-10 | Info | `notes` en texte libre visible de tous les lecteurs | **Accepté** avec consigne : aucune donnée personnelle dans les notes (à rappeler dans le guide utilisateur) |
| L2A-R-11 | Info | Avancement silencieux si la rotation ouverte manquait | **Corrigé** : erreur interne explicite (état incohérent) |
| L2A-R-12 | Info | Action d'audit déclarée `mission.progress`, écrite `mission.<événement>` | **Documenté** dans `authz_matrix.yaml` |

## 2. Vérifications exécutées (2026-10-27)
- Serveur : `scripts/test.ps1` → ruff, format, mypy OK ; **1734 tests passés**, couverture 92,75 %. Migration `0013` vérifiée sur la base locale de développement (fictive) : événements créés en 0012 complétés, politiques temporaires retirées, trigger d'ajout seul réactif (modification refusée).
- Interface : `tsc` OK, Vitest 16/16, Playwright 12/12 (dont `missions.spec.ts`), build OK ; types API régénérés.

## 3. Non vérifié
- Concurrence réelle de deux renvois simultanés (raisonnement sur le verrou, pas de test parallèle).
- Conformité guinéenne des données conducteur : avis juridique local requis avant production.
