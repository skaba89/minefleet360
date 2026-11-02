# Livraison HSE-1 — incidents, enquêtes et actions correctives

Branche `feature/hse-incidents`, migration Alembic `0052`. Premier module HSE structuré (roadmap P1 n° 9) :
il remplace l'absence de registre signalée dans `docs/MINING_BUSINESS_GAPS.md` (« Prévention des incidents 25/100 »).

## Périmètre livré

| Élément | Détail |
|---|---|
| Déclaration | site, nature, gravité estimée, date/heure de survenue (heure du site), titre, faits, lieu, engin impliqué (même site), nombre de blessés, arrêt de travail, mesures immédiates |
| Cycle de l'incident | `REPORTED` → `INVESTIGATING` → `CLOSED`, ou `CANCELLED` (motif codé) |
| Enquête | cause racine, synthèse, requalification gravité/nature pendant l'enquête |
| Actions correctives | responsable, échéance, `OPEN` → `DONE` → `VERIFIED`, réouverture motivée, annulation motivée, retard calculé dans le fuseau du site |
| Indicateurs | `GET /hse/summary` : incidents, blessés, arrêts, incidents ouverts, actions en cours/en retard (90 j par défaut) |
| Interface | menu « Sécurité (HSE) » : indicateurs, « mes actions », registre filtrable, fiche incident avec enquête, actions et chronologie |
| Traçabilité | `hse_incident_event` en ajout seul (trigger), audit `hse.*` dans la même transaction, If-Match/ETag |

## Règles métier

1. `occurred_at` ne peut dépasser l'heure serveur de plus de 10 minutes (dérive d'horloge d'un terminal), contrainte doublée en base.
2. Un engin rattaché doit appartenir au site déclaré.
3. Clôture : cause racine renseignée ; toutes les actions `VERIFIED` ou `CANCELLED` ; au moins une action vérifiée si la gravité est `HIGH`/`CRITICAL` ; clôture par une autre personne que le déclarant.
4. Une action n'est déclarée réalisée que par son responsable ; sa vérification est faite par une autre personne (contrainte `verified_by <> completed_by` en base).
5. Responsables éligibles : comptes actifs `OPS_MANAGER`, `DISPATCHER`, `WORKSHOP_CHIEF`, `HSE` sur le site ou toute la société.
6. Annulation d'un incident impossible tant qu'une action non annulée subsiste.
7. Verrous dans l'ordre incident → action pour éviter les interblocages entre clôture et réalisation.

## Autorisations (authz_matrix.yaml)

| Permission | Rôles | Routes |
|---|---|---|
| `hse.incident.read` | DIRECTION (T), OPS_MANAGER, DISPATCHER (S), WORKSHOP_CHIEF, HSE, AUDITOR (T) | registre, fiche, actions, indicateurs |
| `hse.incident.report` | OPS_MANAGER, DISPATCHER (S), WORKSHOP_CHIEF, MECHANIC, FUEL_MANAGER, HSE | déclaration |
| `hse.incident.manage` | HSE | transitions, ajout/vérification/annulation d'actions, responsables éligibles |
| `hse.action.complete` | OPS_MANAGER, DISPATCHER (S), WORKSHOP_CHIEF, HSE | réalisation (et être le responsable) |

`TENANT_ADMIN` (administration technique) n'a pas accès au registre. Un mécanicien ou un responsable carburant
peut déclarer mais ne relit que l'incident qu'il vient de créer (pas de registre : principe du besoin d'en connaître).

## Protection des données

Aucun champ d'identité de victime ni donnée médicale : seulement un nombre de blessés et un indicateur d'arrêt.
Les consignes de saisie le rappellent. Les textes d'enquête ne sont pas recopiés dans le journal d'audit (seuls
les champs modifiés, la gravité et la nature). À valider avec un juriste local avant production : base légale,
durée de conservation et éventuelles obligations de déclaration réglementaire des accidents du travail en Guinée.

## Vérifications exécutées

- `tests/test_hse.py` (8 tests) : cycle complet, séparation des tâches, annulation, validations, portée site,
  isolation inter-tenant (lecture, liste, transition, décision), indicateurs, ajout seul et RLS en base.
- `tests/test_authz_matrix.py` : refus 403 générés pour chaque rôle non autorisé, lectures autorisées, isolation.
- `frontend/src/pages/HsePages.test.tsx` : registre/indicateurs/actions en retard ; déclaration par un mécanicien sans chargement du registre.
- Ruff, mypy, typecheck, Vitest, build ; contrat OpenAPI et permissions UI régénérés.

## Limites et suites

- Pas encore de pièces jointes (photos) : réutiliser le stockage privé + antivirus du module juridique.
- Pas d'inspections planifiées ni de checklists terrain (lot HSE-2) ; pas de taux de fréquence/gravité faute d'heures travaillées.
- Pas de saisie hors ligne : la déclaration est un bon candidat pour l'outbox append-only (lot réseau faible n° 4).
- Pas de notification (e-mail/SMS) des incidents graves ni des actions en retard.
- Parcours Playwright à ajouter (`frontend/e2e/hse.spec.ts`).
