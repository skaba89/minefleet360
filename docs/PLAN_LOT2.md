# Plan du lot 2 — Missions de transport et rotations (`dispatch`)

> Date : 2026-10-27. Statut : **cadrage validé par délégation du client** (D-41 : « je te laisse répondre »). Références : `USER_STORIES.md` lot 2, `MODELE_CONCEPTUEL.md` §4.4, `REGLES_METIER.md` §7 (RM-070 à RM-077), `DECISIONS_A_ARBITRER.md`.

## 1. Découpage
| Tranche | Contenu | Stories |
|---|---|---|
| **2a** | Référentiels **lieux** (points de chargement, de déchargement, pont-bascule) et **matières** ; **missions** rattachées à une affectation ; avancement par **événements immuables** ; **rotations dérivées** (un cycle chargement → déchargement) ; écran dispatcher | US-2.01, 2.02, 2.03, 2.04, 2.08 (lecture) |
| 2b | **Pesées** : ticket immuable, correction par ticket correctif, tonnage mesuré vs estimé, saisie dégradée approuvée ; indicateurs (temps de cycle, rotations, tonnage) | US-2.05, 2.06, 2.08 |
| 2c | Relevés de compteurs ; documents réglementaires des véhicules | US-2.09, 2.10 |
| hors lot | Écran conducteur (US-2.07, dépend de C-12 et du lot 4 hors ligne) ; géorepérage (lot 5) ; facturation sous-traitants | — |

## 2. Tranche 2a — modèle
- `site_location` : lieu d'un site (`code`, `name`, `kind` ∈ `LOADING_POINT`, `DUMP_POINT`, `STOCKPILE`, `CRUSHER`, `WEIGHBRIDGE`, `PORT`, `OTHER`, `status`). Unique `(tenant, site, code)`.
- `material` : matière transportée par tenant (`code`, `name`, `is_waste` : stérile ou minerai, `status`). Unique `(tenant, code)`.
- `mission` : `site_id`, `vehicle_assignment_id` (affectation **du même site**, porte véhicule et conducteur éligibles), `origin_location_id`, `destination_location_id` (≠ origine), `material_id`, `planned_start`, `due_at` (facultatif), `planned_rotations` (facultatif), `status`, `status_reason`, `notes`. Véhicule et conducteur **copiés** de l'affectation (immuables), pour l'historique.
- `mission_event` (**ajout seul**, trigger anti UPDATE/DELETE) : `event_type`, `occurred_at` (heure déclarée), `recorded_at` (heure serveur), `source` (`DISPATCHER` au lot 2a ; `MOBILE` au lot 4 ; `GEOFENCE` au lot 5, toujours « estimé »), `client_event_id` (unique par tenant : déduplication des renvois), `actor_user_id`, `reason`.
- `rotation` (dérivée des événements, jamais saisie) : `mission_id`, `sequence`, `loading_started_at`, `loaded_at`, `unloading_started_at`, `unloaded_at`, `status` (`OPEN`, `COMPLETED`, `ABORTED`). Aucun tonnage en 2a (RM-070, RM-072).

## 3. Cycle de vie (MODELE_CONCEPTUEL §4.4, codes figés)
`PLANNED` → `ASSIGNED` → `EN_ROUTE_EMPTY` → `LOADING` → `EN_ROUTE_LOADED` → `UNLOADING` → (`EN_ROUTE_EMPTY` pour la rotation suivante | `COMPLETED`) ; `SUSPENDED` depuis tout état actif (motif obligatoire) puis reprise vers l'état d'avant ou `CANCELLED` ; `CANCELLED` depuis `PLANNED`, `ASSIGNED`, `SUSPENDED`.
- Une mission est créée `ASSIGNED` (2a : toujours rattachée à une affectation ; `PLANNED` sans affectation viendra avec la planification).
- **Réaffectation** (US-2.03) : une mission `SUSPENDED` peut être rattachée à une autre affectation du même site (autre véhicule/conducteur) ; événement `REASSIGNED`, la rotation ouverte est `ABORTED`.
- Chaque transition = un `mission_event` + mise à jour du statut, **même transaction**, audit.

## 4. Règles métier
| ID | Règle |
|---|---|
| RM-080 | L'affectation rattachée est `PLANNED` ou `ACTIVE`, du même site que la mission ; le départ (`EN_ROUTE_EMPTY`) exige une affectation `ACTIVE` et **conforme** (pas de départ avec permis expiré ou véhicule indisponible). |
| RM-081 | Un véhicule n'a qu'une mission active (hors `PLANNED`/`ASSIGNED`/terminées) à la fois : contrainte en base. |
| RM-082 | Origine ≠ destination ; lieux et matière actifs, du même site/tenant. |
| RM-083 | `occurred_at` : pas dans le futur au-delà de `CLOCK_SKEW_TOLERANCE`, pas avant le dernier événement de la mission (ordre préservé) ; antidatage borné par `ASSIGNMENT_BACKDATE_TOLERANCE` en 2a (déclarations tardives hors ligne : lot 4). |
| RM-084 | `client_event_id` déjà reçu → réponse identique, **aucun doublon** (renvoi après coupure réseau). |
| RM-085 | Mission `COMPLETED`/`CANCELLED` immuable ; aucune modification d'événement ; correction = événement correctif (2b). |
| RM-086 | Une rotation n'est `COMPLETED` qu'au déchargement ; aucune quantité n'y est saisie en 2a. Le tonnage estimé (capacité nominale × rotations) est **libellé « estimé »** et jamais additionné au mesuré (RM-072). |

## 5. Autorisations (à reporter dans `MATRICE_RBAC.md` et `authz_matrix.yaml`)
| Permission | Rôles |
|---|---|
| `dispatch.location.read`, `dispatch.material.read` | rôles opérationnels (DIRECTION, OPS_MANAGER, DISPATCHER site, WORKSHOP_CHIEF site, HSE, FINANCE, AUDITOR, TENANT_ADMIN) |
| `dispatch.location.manage`, `dispatch.material.manage` | TENANT_ADMIN, OPS_MANAGER |
| `dispatch.mission.read` | DIRECTION, OPS_MANAGER, DISPATCHER (site), HSE, FINANCE, AUDITOR, WORKSHOP_CHIEF (site) |
| `dispatch.mission.create`, `dispatch.mission.progress` | OPS_MANAGER, DISPATCHER (site) — DRIVER (sa propre mission) au lot 4 |

## 6. Critères d'acceptation (2a)
1. Création d'une mission sur une affectation du site : 201, statut `ASSIGNED`, audit ; affectation d'un autre site, d'un autre tenant ou hors portée → 422 `REFERENCE_NOT_FOUND`.
2. Toutes les transitions du §3 acceptées dans l'ordre ; toute autre → 409 `MISSION_STATE_INVALID` ; suspension sans motif → 422.
3. Départ refusé (422 `MISSION_NOT_ELIGIBLE`) si l'affectation n'est pas active ou n'est pas conforme.
4. Deux missions actives pour le même véhicule : refusé, y compris en concurrence réelle (contrainte en base).
5. Un même `client_event_id` envoyé deux fois → un seul événement, même réponse.
6. Rotations : deux cycles complets → 2 rotations `COMPLETED` avec horodatages et durées ; suspension en cours de cycle puis réaffectation → rotation `ABORTED`.
7. `mission_event` : UPDATE/DELETE refusés en base ; RLS forcée sur les quatre tables ; tests d'isolation générés depuis la matrice.
8. Interface dispatcher en français : liste filtrable (site, statut), création, boutons d'avancement selon l'état, suspension/reprise/réaffectation, fiche avec chronologie et rotations ; dates au fuseau du site.
9. Aucun champ de tonnage ni de position GPS dans la tranche 2a.
