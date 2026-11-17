# Release staging 0.1.0-rc.5 — 17 novembre 2026 — sous-traitants lot 1 complet

- **Approbation explicite** : propriétaire du projet (« Déployer rc.5 », choix nommant les migrations 0070, 0071, 0072).
- **Release** : `v0.1.0-rc.5` = `main@848625a` — rattachement des contrats (#468) et des conducteurs (#469), SLA et
  performance mesurée (#470). Images signées (run `44031896074`) : api `sha256:8f6c3c5a…30dfd915`,
  web `sha256:a9007a76…c798b82f` ; labels vérifiés (révision `848625a`, Alembic `0072`).
  **Rollback** : rc.4 (`f5f4a78`), stratégie `application-only-forward-schema`.

## Exécution (2026-11-17 06:33:52Z → 06:34:26Z, depuis `/opt/minefleet/infra/deploy`)

| Étape | Résultat |
|---|---|
| `plan` | `PLAN OK` |
| `apply` | sauvegarde préalable, migrations `0070` + `0071` + `0072`, « database revision matches all Alembic heads », attente de disponibilité, sondes 200, **`RELEASE OK`**, reçu écrit ; api et web en `848625a` |
| Schéma (lecture) | `alembic_version = 0072` ; colonnes `legal_contract.subcontractor_id`, `driver.subcontractor_id`, `subcontractor.availability_target_percent` présentes |
| Phase A `--live` (06:34:37Z, SHA256 `3736bdc33678e517…`) | **Échecs : 0** · SKIP : 2 (A3 cosign, A6 manuelle) ; `A4 verdict : OK` ; `0072` = `0072` ; aucune image créée |
| Moniteur | `failures: 0` (timer toujours désactivé, ST-13) |
| `GET /api/v1/subcontractors/performance` sans jeton | `401` |

Score (86) et verdict inchangés.
