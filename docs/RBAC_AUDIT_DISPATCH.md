# Audit RBAC du domaine dispatch et matrice `dispatch.readiness.*`

> Lot dispatch readiness — Phase 4. Audit de la matrice **réelle**
> (`backend/app/authz/authz_matrix.yaml`, tranche courante `2a`) croisé avec le
> câblage effectif du code, puis introduction des permissions dédiées du flux
> « préparation réseau minier ». Prérequis exigé avant toute nouvelle permission
> dispatch : ce document.

## 1. Méthode

1. Extraction déclarative : les 16 domaines de `authz_matrix.yaml` (144
   permissions) et les 14 rôles réels — validés par `matrix.py` (noms, portées,
   routes uniques, rôles connus).
2. Croisement enforcement : chaque route dispatch est protégée par
   `Require("dispatch.…")` (test ST-01 : correspondance 1:1 matrice ↔ routes,
   OpenAPI `x-permission`) ; les services internes minier (sans route) évaluent
   leurs permissions **dans le service** — 9 points cartographiés.
3. Écart constaté avant correction : le flux readiness (0089, 0091, Phase 3)
   utilisait les permissions **provisoires** `dispatch.location.read` /
   `dispatch.location.manage`, documentées en docstring. Corrigé par ce lot.

## 2. Inventaire réel des permissions dispatch.* (avant ce lot)

| Permission | Rôles attribués | Routes |
| --- | --- | --- |
| `dispatch.location.read` | TENANT_ADMIN, DIRECTION, OPS_MANAGER, DISPATCHER, WORKSHOP_CHIEF, HSE, FINANCE, AUDITOR | GET /site-locations |
| `dispatch.location.manage` | TENANT_ADMIN, OPS_MANAGER | POST/PATCH /site-locations |
| `dispatch.material.read` | idem location.read | GET /materials |
| `dispatch.material.manage` | TENANT_ADMIN, OPS_MANAGER | POST/PATCH /materials |
| `dispatch.mission.read` | DIRECTION, OPS_MANAGER, DISPATCHER, WORKSHOP_CHIEF, HSE, FINANCE, AUDITOR | GET /missions[/{id}] |
| `dispatch.mission.create` | OPS_MANAGER, DISPATCHER | POST /missions |
| `dispatch.mission.progress` | OPS_MANAGER, DISPATCHER | POST /missions/{id}/events |
| `dispatch.weighing.read` | DIRECTION, OPS_MANAGER, DISPATCHER, HSE, FINANCE, AUDITOR | GET /weighing-tickets[/{id}] |
| `dispatch.weighing.record` | OPS_MANAGER, DISPATCHER | POST /weighing-tickets |
| `dispatch.weighing.approve` | OPS_MANAGER | POST …/approve |
| `dispatch.weighing.correct` | OPS_MANAGER | POST …/void, POST …/correct |
| `dispatch.indicators.read` | idem weighing.read | GET /dispatch-indicators |

Constats : le rôle de planification réel est **DISPATCHER** (portée SITE
uniquement — pas de rôle SUPERVISOR dans la matrice) ; la séparation lecture /
action est déjà le standard du domaine (weighing.approve distinct de
weighing.record) ; les rôles DRIVER, MECHANIC, STOREKEEPER, FUEL_MANAGER, HR ne
portent **aucune** permission dispatch.

## 3. Matrice introduite : `dispatch.readiness.*`

| Permission | Rôles | Usage effectif |
| --- | --- | --- |
| `dispatch.readiness.read` | TENANT_ADMIN, DIRECTION, OPS_MANAGER (TENANT+SITE), DISPATCHER, WORKSHOP_CHIEF, HSE, FINANCE, AUDITOR | inspection du brouillon (géodésie, aperçu, clôtures, restrictions), rapports, historique de revue |
| `dispatch.readiness.record` | OPS_MANAGER (TENANT+SITE), DISPATCHER (SITE) | enregistrement des rapports ; proposition et retrait de qualification de tolérance |
| `dispatch.readiness.reject` | OPS_MANAGER (TENANT+SITE), HSE (TENANT+SITE) | rejet motivé TECHNICAL (OPS_MANAGER) ou HSE ; le rôle attendu est revérifié par étape dans le service |
| `dispatch.readiness.approve` | OPS_MANAGER (TENANT+SITE), HSE (TENANT+SITE) | approbation de qualification de tolérance (quatre yeux) et approbation positive du rapport — revue technique OPS_MANAGER puis HSE indépendante (`approve_readiness_report`, Phase 5) |

Justifications ancrées dans l'existant :

- **Lecture** = miroir exact de `dispatch.location.read` : la preuve historique
  est auditable par les mêmes rôles qui lisent les localisations ; aucune
  régression d'accès en lecture.
- **Relevé** : le planificateur réel (DISPATCHER, portée SITE) peut relever ;
  **TENANT_ADMIN est volontairement retiré des écritures** (il ne pouvait les
  faire que via la permission provisoire) — la séparation des pouvoirs
  exigée par la mission prime sur la commodité d'administration.
- **Rejet / approbation** : OPS_MANAGER + HSE, même modèle que weighing.approve
  (record ≠ decide). L'étape TECHNICAL/HSE re-vérifie le rôle dans le service :
  la permission ouvre le domaine, le rôle qualifie l'étape.
- **PLATFORM_ADMIN** : aucun rôle de la matrice dispatch ne lui est attribué et
  son `allowed_scopes` est `[PLATFORM]` (`tenant_kind: PLATFORM`) ; les services
  exigent en plus `tenant_kind == "CUSTOMER"` — interdiction explicite testée.
- **Tenants rivaux** : RLS par tenant (aucun accès inter-tenant possible) +
  portées SITE/TENANT du tenant courant ; isolation testée (ST-01 à ST-02).

## 4. Auto-approbation : invariants en service

1. Rapport : l'acteur de la décision ≠ l'auteur du rapport
   (`SELF_APPROVAL_FORBIDDEN`) — les tests de revue le vérifient.
2. Qualification de tolérance : approbateur ≠ proposeur ≠ responsable du levé.
3. Rejet HSE : exige une revue technique APPROVED préalable par un tiers
   indépendant.
4. Garde database : trigger sur `mining_review_decision` (auteur ≠ acteur,
   indépendance HSE, refus d'APPROVED avec anomalies).

## 5. Câblage effectif après ce lot (9 points)

| Fichier | Point d'évaluation | Permission |
| --- | --- | --- |
| mining_geodesic.py | `require_draft_inspection` | `readiness.read` |
| mining_preview.py | aperçu brouillon | `readiness.read` |
| mining_closure_read.py | clôtures du brouillon | `readiness.read` |
| mining_restriction_read.py | restrictions du brouillon | `readiness.read` |
| mining_report_read.py | lecture rapports | `readiness.read` |
| mining_review_read.py | historique de revue | `readiness.read` |
| mining_report_service.py | enregistrement rapport | `readiness.record` |
| mining_tolerance_service.py | proposition/retrait + approbation | `readiness.record` / `readiness.approve` |
| mining_review_service.py | rejet motivé / approbation positive | `readiness.reject` / `readiness.approve` |

Tests d'épinglage : `backend/tests/test_mining_permissions.py` (déclarations
exactes, grille d'évaluation 13 rôles × 4 permissions, DISPATCHER lit mais ne
rejette pas, PLATFORM_ADMIN refusé, inadéquation rôle/étape refusée) et
`backend/tests/test_mining_approval_service.py` (quatre yeux, indépendance HSE,
qualification courante, concurrence, preuves périmées).

## 6. Priorités et limites

1. Aucune autre permission readiness n'est introduite sans nouveau besoin
   documenté ; `dispatch.readiness.approve` sert ses deux fonctions (qualification
   de tolérance et approbation positive du rapport, Phase 5 livrée) sans
   changement d'attributions.
2. La matrice reste la seule source de vérité : toute évolution passe par
   `authz_matrix.yaml` + tests d'épinglage, jamais par un contournement en
   service.
3. Les permissions provisoires ne subsistent nulle part dans le flux minier ;
   les docstrings documentent désormais les permissions dédiées.
