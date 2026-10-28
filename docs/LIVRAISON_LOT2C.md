# Livraison — lot 2c (compteurs et documents réglementaires des véhicules)

> Date : 2026-10-28. Cadrage : `PLAN_LOT2.md` §8. Stories : US-2.09, US-2.10. Décisions D-42 (documents exigés par catégorie, tranche C-06) et D-43 (compteurs), prises en tant qu'expert flotte.

## Contenu
- **Migrations 0015 et 0016** (0016 applique les correctifs de la revue, la PR #16 ayant été fusionnée avant ; aucune donnée supprimée, l’ancienne colonne `blocks_assignment` est conservée mais plus lue) :
  - relevés de compteur en ajout seul ;
  - documents immuables (trigger : seul le retrait motivé est possible) ;
  - documents exigés par catégorie (modèle global, puis copie pour chaque client, existants compris) ;
  - RLS forcée et clés étrangères composites.
- **Compteurs** (`app/fleet/records.py`) :
  - relevés ordonnés, jamais en baisse ;
  - progression plausible par catégorie : 60, 100 ou 130 km/h, et heures moteur ≤ temps écoulé ;
  - **remise à zéro** = action distincte réservée à l'exploitation et au chef d'atelier ;
  - auteur du relevé masqué hors administration et audit.
- **Documents** :
  - types : assurance, visite technique, inspection interne, vérification de levage, autorisation de transport, carte grise, accès au site ;
  - échéance obligatoire (sauf carte grise) ; validité dérivée ; alerte à 45 jours ;
  - correction = retrait motivé + nouvel exemplaire ; « erreur de saisie » limitée à 24 h.
- **Documents exigés par catégorie** (D-42), réglables par l'administrateur :
  - document exigé échu, retiré ou pas encore valide → **affectation refusée, affectation en cours non conforme, départ de mission refusé** ;
  - document exigé jamais saisi → avertissement (politique `warn`), puis refus une fois la politique passée à `block`.
- **Interface** :
  - fiche véhicule : compteurs, remise à zéro, documents, documents exigés manquants ;
  - page « Documents à échéance » ;
  - onglet Administration › « Documents exigés ».
- **Permissions** : `fleet.meter.read`, `.record`, `.reset` ; `fleet.document.read`, `.manage` ; `fleet.vehicle_category.manage` (MATRICE_RBAC §2.3). Tests d'autorisation et d'isolation générés.

## Réglages (valeurs de départ, à valider avec l'atelier et l'exploitation)
| Réglage | Valeur |
|---|---|
| `MF_METER_BACKDATE_TOLERANCE` | 7 jours |
| `MF_METER_MAX_KMH` | 120 (catégories propres au client) |
| `MF_DOCUMENT_WARNING_DAYS` | 45 |
| `MF_REQUIRED_DOCUMENTS_POLICY` | `warn`, puis `block` une fois le parc saisi |
| `MF_DOCUMENT_ENTRY_ERROR_WINDOW` | 24 h |

## Vérifications exécutées
- Backend : ruff, format, mypy OK ; `tests/test_vehicle_records.py` (10 scénarios, dont les contournements de la revue), matrice et isolation ; suite complète **2095 tests**, couverture 93,34 %.
- Migrations appliquées, défaites et réappliquées ; passage 0015 → 0016 vérifié avec un document existant (conservé, exigences copiées, document devenu immuable).
- Frontend : `tsc`, Vitest 19, **Playwright 16** (dont `vehicule-documents.spec.ts`), build, permissions à jour.

## Revue sécurité
`docs/revues/REVUE_SECURITE_LOT2C.md` : aucun constat critique ni élevé. Les 11 constats sont corrigés ou acceptés de façon motivée.

## Non fait / suite
- Relevés automatiques par télématique (lot 5) ; relevé à la prise de poste (écran conducteur, lot 4).
- Pièces jointes scannées des documents (stockage objet à justifier).
- Liste légale guinéenne des documents obligatoires : avis juridique local.
