# Revue sécurité et QA — tranche 1c, partie serveur (affectations)

> Date : 2026-10-26. Objet : commit `f1710ca` (`backend/app/assignment/`, contrats fleet/workforce, migration `0008_assignment`, `authz_matrix.yaml` `assignment.*`, `errors.py`).
> Revue **interne** (même agent que l'implémentation) : elle ne remplace pas la revue indépendante prévue par CLAUDE.md.

## 1. Modèle de menace (résumé)
| Menace | Contrôle | Preuve |
|---|---|---|
| Lire/modifier une affectation d'une autre société (IDOR) | RLS forcée sur `vehicle_assignment` + recherche puis portée → 404 indiscernable d'un UUID inexistant | Tests générés `test_isolation_*` sur les 9 routes à identifiant ; `test_db_guards_*` (0 ligne sans contexte) |
| Référencer un véhicule/conducteur d'une autre société ou d'un autre site dans le corps | `vehicle_facts`/`driver_facts` sous RLS puis `covers_site` → 422 `REFERENCE_NOT_FOUND` ; FK composites `(tenant_id, id)` en base | `test_us122_a9_a10_references_and_interval` |
| Affectation inter-sites (contournement applicatif) | Motif `ASSIGNMENT_SITE_MISMATCH` + trigger `MF004` | `test_us122_a5_a6_a8_a11_*`, `test_db_guards_*` |
| Double affectation (double clic, concurrence) | Verrous véhicule puis conducteur (FOR NO KEY UPDATE) + `EXCLUDE gist` | `test_us122_a4_*` (2 fils, barrière), `test_us122_a2_a3_a13_*`, insertion SQL directe refusée |
| Élévation de privilège (rôle sans permission) | `Require` avant toute recherche (D-05a), refus 403 audités | Tests générés ST-02 sur toutes les routes × (rôle, portée) |
| Altération de l'historique | Trigger `MF003` (affectation terminée immuable ; véhicule, conducteur, site immuables) ; pas de DELETE | `test_db_guards_*` |
| Changement de statut ou de site masquant une affectation ouverte | `open_assignments` → 409, trigger de site en base | `test_d11_d13_*`, `test_d27_*` |
| Fuite de données personnelles | Audit : identifiants, dates, statuts seulement (pas de nom ni de matricule) ; jamais de n° de permis (réponse, motifs, `eligibility_snapshot`) | `test_us122_a1_*`, `test_us122_a7_*` |
| Injection de champs (`tenant_id`, statut) | Schémas `StrictModel` (`extra=forbid`), statut décidé par le serveur | Tests transverses existants |
| Déni de service par lecture coûteuse | Pagination plafonnée ; filtre `compliance` plafonné (`MF_COMPLIANCE_SCAN_MAX`, 422 au-delà) ; faits chargés en lot (pas de N+1) | Revue de code |
| Erreurs base révélant des détails | Exclusions → 409 métier ; `MF003`/`MF004` → 409 `CONFLICT` ; rien de la requête ni des paramètres dans les logs | Revue de code (`errors.py`) |
| Fuseau / horloge | Instants avec fuseau obligatoires (422 sinon), stockage et réponse en UTC, bornes d'échéance au fuseau du site, horloge injectable | `test_us122_a14_*`, `tests_unit/test_eligibility.py` |

## 2. Constats
| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| SEC1C-01 | Faible | `HR` lit les affectations (matrice §2.5) mais pas les véhicules : il voit `vehicle_id` et `vehicle_fleet_number`, et `/vehicles/{id}/assignments` lui confirme l'existence d'un véhicule de sa portée | **Accepté** : conforme à la matrice, numéro de parc non personnel. À reconsidérer si la matrice change |
| SEC1C-02 | Faible | À la création, le véhicule puis le conducteur sont verrouillés **avant** le contrôle de portée : un utilisateur peut brièvement verrouiller un véhicule d'un autre site de sa société (le temps de la requête) | **Accepté** au lot 1 (même tenant, durée d'une requête, `lock_timeout` 5 s). Correctif possible : lecture sans verrou, contrôle, puis verrou |
| SEC1C-03 | Faible | `valid_from` sans borne haute : une affectation peut réserver un créneau très lointain (ex. 2099) | Ouvert : borne de planification à arbitrer avec l'exploitation (C-11) |
| SEC1C-04 | Info | `audit.action` de la matrice (`vehicle_assignment.update`, `.end`) ne liste pas les actions réellement écrites (`.activate`, `.suspend`, `.resume`, `.complete`, `.cancel`) | Ouvert : le schéma YAML n'accepte qu'une action par permission ; à étendre si un contrôle s'appuie dessus |
| QA1C-01 | Info | Filtre `compliance` évalué en mémoire (D-12) : `total` exact mais coût proportionnel aux affectations actives | Accepté jusqu'au planificateur (lot 2+) |
| QA1C-02 | Info | Pas encore de test E2E ni d'interface : le masquage côté UI est sans objet, l'API seule fait foi | Suite de la tranche 1c |

Aucun constat élevé ou bloquant.

## 3. Vérifications exécutées
- `ruff`, `mypy` strict, `pytest` (1399 passed, couverture 92,9 %), `tests_migrations` (2 passed) ; détail dans `LIVRAISON_TRANCHE_1C.md`.
- Revue de code des points ci-dessus.

## 4. Non couvert
Revue indépendante (agent sécurité distinct), tests de charge, rétention des affectations (C-09), interface web.
