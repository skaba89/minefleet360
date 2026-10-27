# Livraison — lot 2b (pesées et indicateurs)

> Date : 2026-10-27. Cadrage : `PLAN_LOT2.md` §7. Stories : US-2.05, US-2.06, US-2.08 ; suites de la revue du lot 2a (L2A-R-04, 07, 08).

## Contenu
- **Migration 0014** : `weighing_ticket` et `weighing_ticket_decision` en **ajout seul** (trigger), RLS forcée, clés étrangères composites (rotation, mission, véhicule, pont-bascule du **même site**) ; poids net **calculé par la base** ; numéro unique par pont-bascule ; `mission.client_request_id`.
- **Serveur** (`app/dispatch/weighing.py`) :
  - pesée d'une rotation chargée, au plus une pesée non annulée par rotation (sous verrou) ; renvoi identique sans doublon ;
  - correction = annulation + ticket correctif dans la même transaction ; annulation simple motivée ; tout reste consultable ;
  - saisie manuelle (pont en panne) « à approuver », approuvée par une **autre personne** ;
  - alerte de surcharge (net > capacité nominale × 110 %, valeur à valider) ;
  - indicateurs par site et matière : missions, rotations, cycle moyen, cycles suspects, tonnage **mesuré**, **à approuver** et **estimé** toujours séparés.
- **Missions** : nouveau cycle refusé si l'affectation est close ou échue (L2A-R-07) ; plafond de rotations par mission (L2A-R-04) ; création idempotente par `client_request_id` (L2A-R-08).
- **Interface** : saisie de la pesée depuis la fiche mission (colonne « Pesée » des rotations), page **Pesées** (filtres, approuver, corriger, annuler), page **Indicateurs** (période, mesuré / à approuver / estimé séparés).
- **Permissions** `dispatch.weighing.*`, `dispatch.indicators.read` (MATRICE_RBAC §2.5 bis), tests d'autorisation et d'isolation générés depuis la matrice (avec une vraie pesée).

## Réglages (valeurs de développement à valider avec l'exploitation)
`MF_WEIGHING_BACKDATE_TOLERANCE` (7 jours), `MF_PAYLOAD_ALERT_PERCENT` (110), `MF_MISSION_MAX_ROTATIONS` (100), `MF_ROTATION_MIN_CYCLE` (5 min), `MF_INDICATORS_MAX_PERIOD` (92 jours).

## Vérifications exécutées
- Backend : `scripts/test.ps1` → ruff, format, mypy OK ; **1893 tests**, couverture 92,95 % ; `tests/test_weighing.py` (10 scénarios). Migration 0014 appliquée, défaite et réappliquée sur la base locale.
- Frontend : `tsc`, Vitest 19, **Playwright 14** (dont `pesees.spec.ts` : saisie manuelle, approbation par un autre utilisateur, indicateurs), build, permissions à jour.

## Non fait / suite
- Revue sécurité indépendante du lot 2b.
- Intégration automatique des ponts-bascules (C-14, lot 5) ; « source approuvée » autre que le pont-bascule ; facturation des sous-traitants (RM-077).
- Tranche 2c : relevés de compteurs et documents réglementaires des véhicules.
