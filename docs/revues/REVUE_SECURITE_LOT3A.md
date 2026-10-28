# Revue sécurité — lot 3a : pannes, ordres de travail, remise en service (PR #19)

> Date : 2026-10-28. Objet : `backend/app/maintenance/*`, migration `0017`, contrats `fleet` (statut piloté par l'atelier), `dispatch` (suspension des missions), `identity` (mécaniciens), `authz_matrix.yaml` (`maintenance.work_order.*`), page web Atelier.

## 1. Revue automatique des commits
| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| L3A-A-01 | Moyenne | Remise en service : seul l'assigné **actuel** était exclu (réassignation après les travaux) | **Corrigé** : exclusion de toute personne ayant agi (voir L3A-R-01) |
| L3A-A-02 | Moyenne | Auteurs de la mise en attente, des modifications du compte rendu et des saisies de temps pour autrui non exclus | **Corrigé** : modification du compte rendu tracée (événement `NOTED`), tous ces auteurs exclus |

## 2. Revue indépendante (agent security-engineer distinct, lecture du code)
| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| L3A-R-01 | Haute | Séparation des tâches contournable (chef d'atelier qui exécute l'OT d'un autre puis valide ; réassignation à un complice) | **Corrigé** : refus de la remise en service par l'assigné, les assignés successifs, les auteurs de début, attente, reprise, fin, modification du compte rendu, et les auteurs ou bénéficiaires d'une saisie de temps ; tests de plusieurs scénarios |
| L3A-R-02 | Moyenne | Course : remise à disposition pendant qu'un autre OT immobilise le véhicule | **Corrigé** : verrou du véhicule **avant** le comptage des OT, à la clôture comme à la création (ordre unique OT → véhicule → missions) |
| L3A-R-03 | Moyenne | Un rôle sans `fleet.vehicle.update_status` (mécanicien, HSE) peut immobiliser via un signalement | **Accepté (D-44)** : la sécurité prime. Chaque immobilisation est auditée au nom de son auteur, l'OT est numéroté, et un rejet libère le véhicule (R-04). Limitation de débit à envisager si un abus est constaté en exploitation |
| L3A-R-04 | Moyenne | Véhicule laissé immobilisé après rejet ou annulation d'une panne bloquante | **Corrigé** : libération si rien d'autre ne le retient ; test (reprise de la mission ensuite possible) |
| L3A-R-05 | Moyenne | La clôture écrasait une immobilisation posée pour une autre raison (accident, interdiction HSE) | **Corrigé** : seule une immobilisation « panne » ou un statut « en maintenance » est levé ; test |
| L3A-R-06 | Moyenne | Motif effacé en « attente de pièces » par une note ou une réassignation (blocage) | **Corrigé** : le motif ne change qu'avec l'état ; test |
| L3A-R-07 | Moyenne | Compte rendu modifiable pendant le contrôle, sans trace | **Corrigé** : figé pendant le contrôle ; chaque modification écrit l'événement `NOTED` |
| L3A-R-08 | Moyenne | Chaîne des assignés non reconstituable | **Corrigé** : `work_order_event.subject_user_id` (FK composite) ; audit avec l'assigné précédent ; test |
| L3A-R-09 | Moyenne | Véhicule déplacé de site : effets de bord hors portée | **Corrigé** : véhicule revérifié (même site que l'OT, dans la portée) avant tout effet ; test |
| L3A-R-10 | Basse | Verrou du compteur tenu longtemps | **Corrigé** : numéro attribué en dernier |
| L3A-R-11 | Basse | Temps passé sans plafond | **Corrigé** : 24 h par mécanicien et par jour, tous OT confondus ; test. Idempotence (double clic) : **accepté**, une erreur se signale au chef d'atelier (pas de suppression, ajout seul) |
| L3A-R-12 | Basse | Texte libre et données personnelles | **Accepté** avec consigne affichée ; description vide normalisée |
| L3A-R-13 | Basse | Noms des mécaniciens visibles de tous les lecteurs | **Corrigé** : noms (assigné, acteurs, temps passé) réservés à l'atelier, à l'exploitation qui décide et à l'audit ; test |
| L3A-R-14 | Basse | Deux horloges pour la chronologie | **Corrigé** : `occurred_at` pris sur l'horloge injectable |
| L3A-R-15 | Basse | Mission rattachée sans contrôle de site | **Corrigé** : même véhicule **et** même site |
| L3A-R-16 | Basse | Reprise d'une mission sur véhicule immobilisé | **Vérifié** : refusée (`MISSION_NOT_ELIGIBLE`, véhicule non disponible) ; test |

## 3. Vérifications exécutées (2026-10-28)
- Serveur : ruff, format, mypy OK ; **2243 tests**, couverture 93,65 % ; `tests/test_maintenance.py` porté à 8 scénarios.
- Migration `0017` appliquée, défaite et réappliquée sur les bases locales.
- Interface : `tsc`, Playwright 17, build.

## 4. Non vérifié
- Concurrence réelle (deux clôtures ou une clôture et un signalement simultanés) : raisonnement sur l'ordre des verrous, pas de test parallèle.
- Conformité guinéenne de la visibilité nominative du temps passé : avis juridique local.
