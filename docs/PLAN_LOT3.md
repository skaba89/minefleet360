# Plan du lot 3 — Ateliers et maintenance (`maintenance`)

> Date : 2026-10-28. Statut : **cadrage par l'expert flotte** (délégation du client). Références : `USER_STORIES.md` lot 3, `MODELE_CONCEPTUEL.md` §4.1 et §4.5, `REGLES_METIER.md` §9, D-41 (statuts de sécurité).

## 1. Découpage
| Tranche | Contenu | Stories |
|---|---|---|
| **3a** | **Signalement de panne** (avec immobilisation et suspension de la mission en cours), **ordre de travail** de bout en bout (approbation, mécanicien, intervention, attente de pièces, contrôle qualité), **remise en service** validée par une autre personne que le mécanicien, temps passé, date prévue de remise en service | US-3.01 à US-3.06, US-3.08 |
| 3b | **Entretien préventif** par plans (heures moteur, kilomètres, jours) déclenché par les relevés de compteur ; **indicateurs atelier** (disponibilité, durée d'immobilisation, MTTR, MTBF) | US-3.07, préventif |
| plus tard | Pièces et stock (consommation par ligne d'OT, double consommation interdite) : lot Magasin | — |

## 2. Tranche 3a — modèle (migration `0017_maintenance`)
- `work_order` : numéro lisible par tenant (`OT-000123`, compteur verrouillé), site et véhicule, `kind` (`CORRECTIVE` ; `PREVENTIVE` en 3b), `priority` (`CRITICAL`, `HIGH`, `NORMAL`, `LOW`), `symptom_code` (codé), `description` (technique, sans donnée personnelle), mission liée (facultative), `immobilize` (panne bloquante), `status`, motif codé, mécanicien assigné, `expected_ready_at`, `diagnosis`, `work_done`, `parts_note`, horodatages d'approbation, de début, de contrôle et de clôture, auteurs, `row_version`.
- `work_order_event` (**ajout seul**) : chaque transition (acteur, motif, heure) — base des durées (3b) et de la traçabilité.
- `work_order_labour` (**ajout seul**) : temps passé par mécanicien (minutes, jour, note technique).
- `maintenance_counter` : dernier numéro d'OT par tenant.

## 3. Cycle de vie (MODELE_CONCEPTUEL §4.5, codes figés)
`REQUESTED` → `APPROVED` → `ASSIGNED` → `IN_PROGRESS` ⇄ `AWAITING_PARTS` → `QUALITY_CHECK` → `CLOSED` (ou retour `IN_PROGRESS` si non conforme) ; `REJECTED` depuis `REQUESTED` ; `CANCELLED` depuis `REQUESTED`, `APPROVED`, `ASSIGNED`.

### Effets sur le véhicule et l'exploitation (décisions d'expert, D-44)
| Moment | Effet |
|---|---|
| Signalement avec **panne bloquante** | Véhicule `AVAILABLE` → `IMMOBILIZED` (motif de la panne) ; **mission en cours suspendue** (motif « Panne », source système) ; politique D-41 appliquée aux affectations |
| **Début d'intervention** | Véhicule → `IN_MAINTENANCE` |
| **Clôture** après contrôle qualité conforme | Véhicule → `AVAILABLE` **seulement si aucun autre OT ouvert ne le garde à l'atelier** (en cours, attente de pièces, contrôle) |
| Rejet, annulation d'une panne bloquante | Véhicule `AVAILABLE` si aucun autre OT ne le retient (revue L3A-R-04) ; une immobilisation posée pour une autre raison n'est jamais levée |

## 4. Règles
| ID | Règle |
|---|---|
| RM-110 | Véhicule du tenant, dans la portée, non réformé ; mission liée du même véhicule. |
| RM-111 | Transitions strictes (§3) ; motif codé obligatoire pour rejet, annulation, attente de pièces et contrôle non conforme. |
| RM-112 | Le mécanicien assigné a le rôle `MECHANIC` (ou `WORKSHOP_CHIEF`) sur le site du véhicule (ou toute la société), compte actif. |
| RM-113 | Seul le mécanicien assigné (ou le chef d'atelier) démarre, met en attente, reprend, déclare terminé et saisit du temps. |
| RM-114 | **Remise en service** : la clôture (contrôle conforme) est faite par une personne qui n'a **pas agi** sur l'intervention (assignés successifs, exécution, compte rendu, temps passé) ; le compte rendu est figé pendant le contrôle. |
| RM-115 | Temps passé : minutes entières (1 à 960 par saisie, 24 h au plus par mécanicien et par jour), jour non futur, ajout seul ; un OT clôturé n'accepte plus de temps. |
| RM-116 | Événements et temps en ajout seul ; concurrence par `If-Match` ; audit de chaque transition. |

## 5. Autorisations
| Permission | Rôles |
|---|---|
| `maintenance.work_order.read` | DIRECTION, OPS_MANAGER, DISPATCHER (site), WORKSHOP_CHIEF, MECHANIC (site), HSE, AUDITOR |
| `maintenance.work_order.request` (signaler) | OPS_MANAGER, DISPATCHER (site), WORKSHOP_CHIEF, MECHANIC (site), HSE |
| `maintenance.work_order.manage` (approuver, rejeter, assigner, annuler, contrôle qualité) | WORKSHOP_CHIEF, OPS_MANAGER |
| `maintenance.work_order.execute` (intervention, temps) | WORKSHOP_CHIEF, MECHANIC (site) |

## 6. Critères d'acceptation (3a)
1. Signalement d'une panne bloquante : OT `REQUESTED` numéroté, véhicule immobilisé, mission en cours suspendue avec un événement système, audit.
2. Cycle complet jusqu'à la clôture : véhicule `IN_MAINTENANCE` au début, `AVAILABLE` à la clôture ; un second OT ouvert empêche la remise à disposition.
3. Transitions interdites → 409 ; motif manquant → 422 ; mécanicien sans rôle sur le site → 422 ; un autre mécanicien que l'assigné → 403/409 ; clôture par le mécanicien assigné → 422.
4. Événements et temps en ajout seul (UPDATE/DELETE refusés en base), RLS forcée, isolation générée depuis la matrice.
5. Interface : page « Atelier » (liste, signalement), fiche OT (actions selon rôle et état, temps passé, chronologie), date prévue de remise en service visible du dispatcher.
