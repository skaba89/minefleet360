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

## Tranches suivantes (lot 1)

2. Rattachements : engins `SUBCONTRACTED`, conducteurs sous-traitants et contrats `SUBCONTRACTOR` reliés au
   référentiel (reprise des valeurs texte existantes à décider).
3. SLA et performance par sous-traitant (disponibilité, rotations, tonnage **mesuré**), vus par le donneur d'ordre.

Lot 2 (comptes externes) : non ouvert — voir les décisions restantes du modèle de sécurité.
