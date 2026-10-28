# Livraison — lot 3a (ateliers : pannes, ordres de travail, remise en service)

> Date : 2026-10-28. Cadrage : `PLAN_LOT3.md`. Stories : US-3.01 à US-3.06, US-3.08. Décision D-44 (l'atelier pilote le statut du véhicule), prise en tant qu'expert flotte.

## Contenu
- **Migration 0017** (réversible) :
  - `work_order` : numéro lisible par client (`OT-000123`, compteur atomique) ;
  - `work_order_event` et `work_order_labour` en ajout seul (trigger) ;
  - RLS forcée et clés étrangères composites (véhicule, mission, mécanicien, site).
- **Service** (`app/maintenance`) :
  - **cycle de vie** : signalement, approbation (avec date prévue de remise en service), assignation à un mécanicien (rôle vérifié sur le site), début, attente de pièces, reprise, travaux terminés, contrôle qualité (conforme ou non), clôture ; rejet et annulation motivés ;
  - **effets sur l'exploitation (D-44)** :
    - une panne bloquante **immobilise le véhicule et suspend sa mission en cours** (événement système) ;
    - le début d'intervention passe le véhicule **en maintenance** ;
    - la clôture le remet **disponible** si aucun autre ordre de travail ne le retient ;
  - **séparation des tâches** : seul le mécanicien assigné (ou un chef d'atelier) intervient ; la remise en service est validée par **une autre personne** ;
  - **temps passé** par mécanicien, en ajout seul ; compte rendu (diagnostic, travaux, pièces) obligatoire avant le contrôle ;
  - audit de chaque transition et concurrence par `If-Match`.
- **Contrats entre modules** :
  - parc : changement de statut piloté par l'atelier, avec les mêmes règles que le changement manuel ;
  - missions : suspension des missions en cours ;
  - comptes : mécaniciens d'un site.
- **Interface** : menu **Atelier** (liste filtrable, « Signaler une panne ») et fiche de l'ordre de travail (actions selon le rôle et l'état, compte rendu, temps passé, chronologie).
- **Permissions** `maintenance.work_order.*` (MATRICE_RBAC §2.5 ter) ; tests d'autorisation et d'isolation générés, avec un vrai ordre de travail.

## Vérifications exécutées
- Backend : ruff, format, mypy OK ; **2239 tests**, couverture 93,52 %, dont `tests/test_maintenance.py` (4 scénarios) :
  - cycle complet avec panne bloquante et mission suspendue ;
  - auto-validation refusée et second ordre de travail qui retient le véhicule ;
  - actions interdites ;
  - numérotation, portée site et ajout seul.
- Migration 0017 appliquée, défaite et réappliquée sur la base locale.
- Frontend : `tsc`, Vitest 19, **Playwright 17** (dont `atelier.spec.ts` : signalement par le dispatcher, intervention par le chef d'atelier, refus de son auto-validation, remise en service par l'exploitation), build, permissions à jour.

## Non fait / suite
- Revue sécurité indépendante du lot 3a.
- Tranche 3b : entretien préventif déclenché par les compteurs, indicateurs atelier (disponibilité, immobilisation, MTTR, MTBF).
- Pièces et stock (lot Magasin) ; signalement par le conducteur (lot 4).
