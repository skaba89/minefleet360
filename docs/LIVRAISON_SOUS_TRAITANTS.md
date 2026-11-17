# Livraison — sous-traitants, lot 1 (option B, sans compte externe)

Décision : `docs/MODELE_SECURITE_SOUS_TRAITANTS.md` (16 novembre 2026). Le lot 1 structure ce qui existait en texte
libre (`vehicle.ownership_type = SUBCONTRACTED`, `driver.external_company_name`, `legal_contract.counterparty_name`)
sans ouvrir le moindre accès externe.

## Tranche 1 — référentiel des organisations sous-traitantes

- **Table** `subcontractor` (migration additive `0068`) : code unique par tenant, raison sociale, RCCM et NIF
  facultatifs, pays ISO (défaut `GN`), statut `ACTIVE` / `SUSPENDED` / `ENDED` avec **motif obligatoire hors
  ACTIVE** (contrainte `ck_subcontractor_reason`), notes. RLS tenant (`SELECT, INSERT, UPDATE` — pas de suppression),
  `row_version` + `If-Match`. **Aucune donnée nominative** (pas de contact personnel) ni colonne de compte.
- **API** : `GET /subcontractors` (filtre `status`), `POST /subcontractors`, `PATCH /subcontractors/{id}` ; audit
  `subcontractor.create`, `subcontractor.update`, `subcontractor.status_change` (motif dans l'événement).
- **Autorisation** (matrice générée) :

| Permission | Rôles (portée TENANT) |
|---|---|
| `partner.subcontractor.read` | TENANT_ADMIN, DIRECTION, OPS_MANAGER, FINANCE, HSE, AUDITOR |
| `partner.subcontractor.manage` | TENANT_ADMIN, OPS_MANAGER |

  Aucun rôle de terrain (DISPATCHER, DRIVER, MECHANIC…) ni WORKSHOP_CHIEF ; aucun accès plateforme.
- **Interface** : Administration → « Sous-traitants » (lecture ; création, modification et changement de statut
  motivé pour les gestionnaires). Conséquence voulue : DIRECTION, HSE et FINANCE voient désormais le menu
  Administration, réduit à cet onglet.

## Vérifications

- Backend `tests/test_subcontractors.py` : cycle de vie et audit, validations (code en double → 409
  `DUPLICATE_SUBCONTRACTOR_CODE`, motif, champ inconnu, `tenant_id` dans le corps), verrouillage optimiste, isolation
  inter-tenant (404), refus des rôles non autorisés ; tests d'autorisation générés (ST-01/ST-02) étendus.
- Vitest `SubcontractorsPage.test.tsx` ; E2E administration (onglets de l'auditeur) et accès direct par URL des
  13 rôles étendus à `/administration/sous-traitants`.

## Tranche 2a — rattachement des engins

- Migration additive `0069` : `vehicle.subcontractor_id` (nullable), clé étrangère composite même tenant,
  contrainte `ck_vehicle_subcontractor` (rattachement seulement pour un engin `SUBCONTRACTED`), index partiel.
- Règles de service : engin non sous-traité → 422 `ownership_mismatch` ; sous-traitant inconnu ou d'un autre tenant →
  422 `REFERENCE_NOT_FOUND` (indiscernables) ; **nouveau** rattachement à un sous-traitant non actif → 422
  `not_active` ; un rattachement existant reste valable si le sous-traitant est suspendu ou terminé ensuite ;
  changement de propriété sans détachement explicite → 422 `must_clear` (jamais de modification silencieuse).
  `subcontractor_id` est dans l'instantané d'audit `vehicle.create` / `vehicle.update`.
- **Aucune reprise automatique** du texte libre existant : chaque rattachement est un acte explicite et journalisé.
- Autorisation : `partner.subcontractor.read` accordée aussi à OPS_MANAGER en portée SITE (il gère les engins de
  son site ; le référentiel n'est lié à aucun site — précédent des référentiels dispatch).
- Interface : choix « Sous-traitant (référentiel) » dans la création et la modification d'un engin sous-traité
  (actifs + sous-traitant actuel), mention sur la fiche ; masqué sans droit de lecture du référentiel.

## Tranche 2b — rattachement des contrats de sous-traitance

- Migration additive `0070` : `legal_contract.subcontractor_id` (nullable), clé étrangère composite même tenant,
  contrainte `ck_legal_contract_subcontractor` (rattachement seulement pour un contrat `SUBCONTRACTOR`), index
  partiel.
- Rattachement **à la création du brouillon uniquement** : le contrat est un document juridique dont la
  modification reste limitée au circuit de soumission existant (0048) ; aucun nouveau chemin de mise à jour.
  Règles : type incompatible → 422 ; sous-traitant inconnu ou d'un autre tenant → 422 `REFERENCE_NOT_FOUND` ;
  sous-traitant non actif → 422 `not_active`. Les contrats existants restent sans rattachement (aucune reprise
  automatique de `counterparty_name`).
- Autorisation inchangée : les créateurs de contrats (TENANT_ADMIN, OPS_MANAGER tenant ou site) lisent déjà le
  référentiel (#466).
- Interface (Juridique) : pour un contrat de sous-traitance, choix « Sous-traitant (référentiel) » ; la contrepartie
  est pré-remplie avec la raison sociale si elle est vide.

## Tranches suivantes (lot 1)

2c. Conducteurs sous-traitants (`employment_type = SUBCONTRACTOR`) reliés au référentiel.
3. SLA et performance par sous-traitant (disponibilité, rotations, tonnage **mesuré**), vus par le donneur d'ordre.

Lot 2 (comptes externes) : non ouvert — voir les décisions restantes du modèle de sécurité.
