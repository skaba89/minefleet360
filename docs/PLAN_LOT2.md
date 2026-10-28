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

## 7. Tranche 2b — pesées et indicateurs (cadrage délégué, 2026-10-27)

### 7.1 Modèle (migration `0014_weighing`)
- **Pont-bascule** = lieu du site de type `WEIGHBRIDGE` (référentiel 2a, pas de nouvelle table).
- `weighing_ticket` (**ajout seul**, trigger) : site, mission, **rotation**, véhicule (copié de la rotation), pont-bascule, `ticket_number`, `source` ∈ `WEIGHBRIDGE` | `MANUAL_DEGRADED`, `weighed_at`, `gross_kg` et `tare_kg` (kg entiers), `net_kg` **calculé par la base** (brut − tare), capacité nominale du véhicule au moment de la pesée, indicateur de surcharge, motif codé de saisie dégradée, `replaces_ticket_id` (ticket correctif), `recorded_by`, `recorded_at`.
- `weighing_ticket_decision` (**ajout seul**) : `APPROVED` (saisie dégradée) ou `VOIDED` (annulation, motif obligatoire), une seule de chaque par ticket.
- Statut **dérivé** : `VOIDED` si annulé ; sinon `PENDING_APPROVAL` pour une saisie dégradée non approuvée ; sinon `VALID`.
- `mission.client_request_id` (création de mission idempotente, revue L2A-R-08).

### 7.2 Règles
| ID | Règle |
|---|---|
| RM-090 | Un ticket se rattache à une rotation **chargée** (`OPEN` avec `loaded_at`, ou `COMPLETED`) d'une mission du site ; pont-bascule actif du **même site**. |
| RM-091 | Au plus **un ticket non annulé par rotation** (contrôle sous verrou de la rotation). |
| RM-092 | Brut > tare > 0, brut ≤ 500 000 kg ; net calculé par la base, jamais saisi. |
| RM-093 | `weighed_at` : pas dans le futur (tolérance d'horloge), pas avant le chargement, antidatage borné par `MF_WEIGHING_BACKDATE_TOLERANCE` (7 jours : saisie de tickets papier). |
| RM-074 | Unicité `(tenant, pont-bascule, numéro)` pour les tickets d'origine ; **renvoi identique → même ticket (200)**, numéro réutilisé avec d'autres valeurs → 409 `DUPLICATE_TICKET_NUMBER`. |
| RM-073 | Correction = annulation + nouveau ticket `replaces_ticket_id` dans la même transaction (le numéro peut être conservé) ; jamais de modification. |
| RM-075 | Saisie dégradée : motif codé obligatoire ; comptée à part (« en attente ») tant qu'elle n'est pas **approuvée par une autre personne** que celle qui l'a saisie (422 `SELF_APPROVAL_FORBIDDEN`). |
| RM-076 | Surcharge : net > capacité nominale × `MF_PAYLOAD_ALERT_PERCENT` % (110 par défaut, **à valider**) → ticket marqué, filtrable (HSE). |
| RM-072 | Indicateurs : **mesuré** (tickets valides), **en attente** (dégradés non approuvés) et **estimé** (capacité nominale × rotations sans aucune pesée) toujours séparés, jamais additionnés. |
| L2A-R-04 | Plafond de rotations par mission (`MF_MISSION_MAX_ROTATIONS`, 100) ; cycles plus courts que `MF_ROTATION_MIN_CYCLE` (5 min) comptés comme « cycles suspects » dans les indicateurs. |
| L2A-R-07 | Nouveau cycle (`ARRIVED_LOADING`) refusé si l'affectation n'est plus active ou est échue ; le cycle en cours peut se terminer, puis suspension et réaffectation. |

### 7.3 Autorisations
| Permission | Rôles |
|---|---|
| `dispatch.weighing.read` | DIRECTION, OPS_MANAGER, DISPATCHER (site), HSE, FINANCE, AUDITOR |
| `dispatch.weighing.record` | OPS_MANAGER, DISPATCHER (site) |
| `dispatch.weighing.approve` | OPS_MANAGER |
| `dispatch.weighing.correct` (annuler, corriger) | OPS_MANAGER |
| `dispatch.indicators.read` | DIRECTION, OPS_MANAGER, DISPATCHER (site), HSE, FINANCE, AUDITOR |

### 7.4 Critères d'acceptation (2b)
1. Pesée au pont-bascule sur une rotation chargée : 201, net calculé, audit ; rotation non chargée, annulée, d'un autre site ou hors portée → 409/422 sans fuite.
2. Second ticket sur la même rotation → 409 ; renvoi identique → même ticket ; numéro réutilisé autrement → 409.
3. Ticket : UPDATE/DELETE refusés en base ; RLS forcée ; tests d'isolation générés depuis la matrice.
4. Correction : l'original passe `VOIDED`, le nouveau référence l'original, les deux restent consultables.
5. Saisie dégradée : exclue du mesuré jusqu'à approbation par une autre personne ; auto-approbation refusée.
6. Indicateurs par site et matière sur une période (92 jours max) : mesuré, en attente et estimé séparés ; aucune donnée GPS.
7. Interface : saisie depuis la fiche mission, page Pesées (filtres, approbation, annulation, correction), page Indicateurs.

## 8. Tranche 2c — compteurs et documents des véhicules (cadrage délégué, 2026-10-28)

### 8.1 Modèle (migration `0015_vehicle_meters_documents`)
- `vehicle_meter_reading` (**ajout seul**) : véhicule, site (copié), `meter_kind` ∈ `ODOMETER_KM` | `HOUR_METER`, `value` (dixième), `read_at`, `source` (`MANUAL` ; télématique au lot 5), `reset_reason` (remise à zéro motivée), `recorded_by`, `recorded_at`.
- `vehicle_document` : véhicule, `doc_type` ∈ `INSURANCE`, `TECHNICAL_INSPECTION`, `ROAD_PERMIT`, `REGISTRATION`, `SITE_ACCESS_PERMIT`, `OTHER`, `reference` (sans donnée personnelle), `issuer`, `valid_from`, `valid_until`, `status` (`VALID` | `WITHDRAWN`), **`blocks_assignment`** (décision C-06 prise document par document ; par défaut vrai pour l'assurance et la visite technique), `row_version`. Validité **dérivée** des dates comme pour les permis (D-03).

### 8.2 Règles
| ID | Règle |
|---|---|
| RM-100 | Compteur seulement si la catégorie du véhicule l'a (`has_odometer`, `has_hour_meter`) ; véhicule non réformé. |
| RM-101 | Relevés ordonnés : `read_at` jamais avant le dernier relevé du même compteur, pas dans le futur (tolérance d'horloge), antidatage borné (`MF_METER_BACKDATE_TOLERANCE`, 7 jours). |
| RM-102 | Valeur jamais inférieure au relevé précédent, sauf **remise à zéro motivée** (`METER_REPLACED`, `ROLLOVER`, `ENTRY_ERROR`), tracée. |
| RM-103 | Progression plausible : heures moteur ≤ temps écoulé (+ 5 %), kilomètres ≤ `MF_METER_MAX_KMH` (120) × heures écoulées ; sinon refus (fraude ou erreur de saisie). |
| RM-104 | Pour chaque type de document dont au moins un exemplaire est **bloquant**, le véhicule doit avoir un exemplaire valide : sinon l'affectation est refusée (`VEHICLE_DOCUMENT_EXPIRED`, `VEHICLE_DOCUMENT_EXPIRES_BEFORE_END`) et une affectation en cours devient **non conforme** (départ refusé). Échéance proche : avertissement. |
| RM-105 | Un document ne se supprime pas : il est **retiré** (motif tracé) ou remplacé par un nouvel exemplaire. |

### 8.3 Autorisations
| Permission | Rôles |
|---|---|
| `fleet.meter.read`, `fleet.document.read` | lecteurs des véhicules (`fleet.vehicle.read`) |
| `fleet.meter.record` | OPS_MANAGER, DISPATCHER (site), WORKSHOP_CHIEF (site), MECHANIC (site) |
| `fleet.document.manage` | TENANT_ADMIN, OPS_MANAGER, HSE |

### 8.4 Critères d'acceptation (2c)
1. Relevé accepté dans l'ordre et en progression plausible ; valeur en baisse sans motif, relevé antérieur au dernier, progression impossible, compteur absent de la catégorie → 422.
2. Relevés en ajout seul (UPDATE/DELETE refusés en base), RLS forcée, isolation testée depuis la matrice.
3. Document bloquant expiré : affectation refusée, affectation en cours non conforme et départ de mission refusé ; renouvellement → de nouveau éligible.
4. Document non bloquant expiré : simple alerte ; retrait d'un document tracé dans l'audit.
5. Interface : fiche véhicule avec relevés (saisie) et documents (ajout, retrait, échéances) ; liste des documents à échéance.
