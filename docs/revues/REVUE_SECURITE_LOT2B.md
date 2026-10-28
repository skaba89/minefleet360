# Revue sécurité — lot 2b : pesées et indicateurs (PR #15)

> Date : 2026-10-28. Objet : `backend/app/dispatch/weighing.py`, `router.py`, `schemas.py`, `service.py` (création de mission idempotente, nouveau cycle), migration `0014_weighing`, `authz_matrix.yaml` (`dispatch.weighing.*`, `dispatch.indicators.read`), pages web Pesées, Indicateurs et fiche mission.

## 1. Revue indépendante (agent security-engineer distinct, lecture du code)
Aucun constat critique ni élevé. Vérifiés sans problème : portée et IDOR (rotation, mission, ticket, pont-bascule, site), réponses uniformes hors portée, RLS forcée et droits `SELECT, INSERT` seuls sur les deux tables, immuabilité (triggers), net calculé par la base, approbation impossible après annulation, décisions uniques, ordre de verrouillage des corrections, validation des entrées, séparation mesuré / à approuver / estimé, aucune donnée GPS ni nominative, interface sans injection HTML.

| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| L2B-R-01 | Moyenne | L'unicité du numéro ne couvrait que les tickets d'origine : deux correctifs pouvaient porter le même numéro, et le même ticket physique être compté deux fois | **Corrigé** : un numéro ne peut être porté que par une pesée **non annulée** du pont, correctifs compris. Contrôle applicatif doublé d'un **trigger** en base (`uq_wt_live_number`, verrou consultatif sur le numéro) ; test `test_live_ticket_numbers_stay_unique_through_corrections` |
| L2B-R-02 | Moyenne | La source est déclarative : une saisie « pont-bascule » est valide sans approbation, et une saisie dégradée pouvait devenir « pont-bascule » par correction | **Corrigé en partie** : une correction ne peut plus faire passer une saisie dégradée en « pont-bascule » (il faut l'annuler et saisir le vrai ticket, ou la faire approuver) ; test `test_degraded_entry_cannot_be_laundered`. **Risque résiduel accepté** jusqu'à l'intégration des ponts-bascules (C-14, lot 5) : une saisie « pont-bascule » reste une déclaration, tracée (auteur, heure d'enregistrement, valeurs dans l'audit) et contrôlable sur pièce (numéro de ticket papier) |
| L2B-R-03 | Faible | La séparation des tâches ne visait que l'auteur du dernier correctif | **Corrigé** : refus d'approbation par toute personne ayant saisi ou décidé sur la chaîne des correctifs ; test |
| L2B-R-04 | Faible | « Une pesée non annulée par rotation » garantie seulement par le code | **Corrigé** : trigger en base (`uq_wt_live_rotation`) sous verrou de la rotation ; test `test_database_guards_live_tickets` |
| L2B-R-05 | Faible | Cohérence ticket / rotation / mission / site / véhicule non imposée par la base | **Corrigé** : même trigger (`ck_wt_rotation_consistency`) ; test |
| L2B-R-06 | Faible | Verrou de la rotation pris avant le contrôle de portée | **Corrigé** : lecture et contrôle de portée d'abord, verrou ensuite (état relu sous verrou) |
| L2B-R-07 | Faible | Le renvoi de création de mission ne comparait que l'affectation | **Corrigé** : toutes les valeurs significatives comparées, sinon `CONFLICT` ; test. Course simultanée de deux renvois : `CONFLICT` pour le second (accepté) |
| L2B-R-08 | Faible | Un renvoi identique tardif était refusé (délai de saisie) ; le motif de saisie dégradée n'était pas comparé | **Corrigé** : rejeu reconnu avant les contrôles de délai et d'état, toutes les valeurs comparées ; test |
| L2B-R-09 | Faible | Correction non idempotente après coupure réseau | **Corrigé** : un renvoi identique rend le même correctif (200) ; test |
| L2B-R-10 | Faible | Traçabilité incomplète (annulation implicite de l'original, valeurs saisies, action déclarée) | **Corrigé** : `weighing_ticket.void` écrit sur l'original lors d'une correction ; création et correction tracent numéro, pont, brut, tare, heure, rotation (avant/après) ; approbateur dans l'audit ; matrice alignée |
| L2B-R-11 | Faible | Sous-requête des indicateurs non bornée à la période | **Corrigé** : limitée aux rotations terminées de la période. Mesure de performance sur gros volume : à faire avant production |
| L2B-R-12 | Faible | Rétro-datation illimitée des corrections | **Corrigé** : bornée à 92 jours (`MF_WEIGHING_CORRECTION_BACKDATE_TOLERANCE`) ; anciennes et nouvelles valeurs tracées |
| L2B-R-13 | Faible (interface) | La fiche mission pouvait tronquer la liste et proposer une saisie à tort | **Corrigé** : filtre `live_only` (pesées non annulées seulement) |
| L2B-R-14 | Info | Identifiants techniques des auteurs (`recorded_by`, `decided_by`) visibles des lecteurs | **Accepté** : identifiants opaques, sans nom ; à confirmer avec le conseil juridique (conformité guinéenne) |

## 2. Vérifications exécutées (2026-10-28)
- Serveur : `scripts/test.ps1` → ruff, format, mypy OK ; **1898 tests passés**, couverture 93,11 % ; `tests/test_weighing.py` porté à 15 scénarios.
- Migration `0014` appliquée, défaite et réappliquée deux fois sur la base locale (données fictives).
- Interface : `tsc`, Vitest 19, Playwright 14, build, permissions à jour.

## 3. Non vérifié
- Concurrence réelle (saisies ou corrections simultanées) : raisonnement sur les verrous et le trigger, pas de test parallèle.
- Performance des indicateurs sur un gros volume (`EXPLAIN ANALYZE`).
- Conformité légale guinéenne (traçabilité nominative, conservation) : avis juridique local requis avant production.
