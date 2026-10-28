# Livraison — lot 2c (compteurs et documents réglementaires des véhicules)

> Date : 2026-10-28. Cadrage : `PLAN_LOT2.md` §8. Stories : US-2.09, US-2.10 ; décision C-06 (documents bloquants).

## Contenu
- **Migration 0015** : `vehicle_meter_reading` (ajout seul, trigger) et `vehicle_document` (jamais supprimé, retrait motivé), RLS forcée, clés étrangères composites.
- **Relevés de compteur** (`app/fleet/records.py`) :
  - seulement pour les compteurs prévus par la catégorie du véhicule ;
  - ordonnés, sans relevé dans le futur, antidatage borné ;
  - la valeur ne baisse jamais, sauf remise à zéro motivée (compteur remplacé, revenu à zéro, erreur de saisie) ;
  - progression plausible : heures moteur ≤ temps écoulé, kilomètres ≤ 120 km/h × temps écoulé ;
  - relevés d'un véhicule sérialisés par son verrou ; audit de chaque relevé.
- **Documents réglementaires** :
  - types : assurance, visite technique, autorisation de circuler, carte grise, accès au site, autre ;
  - validité dérivée des dates au fuseau du site ;
  - **bloquants par défaut : assurance et visite technique** (C-06, modifiable document par document) ; un document bloquant a obligatoirement une échéance ;
  - document bloquant échu ou retiré sans exemplaire valide du même type : **affectation refusée**, affectation en cours **non conforme**, **départ de mission refusé** ; renouvellement → de nouveau éligible ;
  - retrait pour erreur de saisie : le document est ignoré pour l'éligibilité ;
  - liste des documents échus ou à échéance (alerte), hors documents déjà renouvelés.
- Calcul de validité déplacé dans le socle commun (`app/core/validity.py`), réexporté par `workforce`.
- **Interface** : fiche véhicule avec sections « Compteurs » et « Documents réglementaires » (saisie, retrait), page « Documents à échéance ».
- **Permissions** `fleet.meter.*`, `fleet.document.*` (MATRICE_RBAC §2.3), tests d'autorisation et d'isolation générés (avec un vrai document).

## Réglages (valeurs de développement à valider avec l'atelier)
`MF_METER_BACKDATE_TOLERANCE` (7 jours), `MF_METER_MAX_KMH` (120).

## Vérifications exécutées
- Backend : ruff, format, mypy OK ; `tests/test_vehicle_records.py` (6 scénarios), matrice et isolation ; suite complète **2044 tests**, couverture 93,21 %.
- Migration 0015 appliquée, défaite et réappliquée sur la base locale.
- Frontend : `tsc`, Vitest 19, **Playwright 15** (dont `vehicule-documents.spec.ts`), build, permissions à jour.

## Non fait / suite
- Revue sécurité indépendante du lot 2c.
- Relevés automatiques par télématique (lot 5) ; pièces jointes scannées des documents (stockage objet à justifier).
- Liste des documents **exigés** par catégorie de véhicule (aujourd'hui : exigence née du premier document bloquant enregistré) — à arbitrer avec le client.
