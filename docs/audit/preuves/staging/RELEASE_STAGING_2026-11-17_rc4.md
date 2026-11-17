# Release staging 0.1.0-rc.4 — 16/17 novembre 2026 — première release avec migrations depuis rc.1

- **Approbation explicite** : propriétaire du projet (« déploie », après demande nommant les migrations 0068 et 0069).
- **Release** : `v0.1.0-rc.4` = `main@f5f4a78` — sous-traitants lot 1 : référentiel (#465) et rattachement des engins
  (#466). Images signées (run `43983408617`) : api `sha256:ab9d2901…866351c6`, web `sha256:268e202f…5436ffc0` ;
  labels vérifiés (révision `f5f4a78`, Alembic `0069`). **Rollback** : rc.3 (`4501f6d`), stratégie
  `application-only-forward-schema` (rc.3 ignore la table `subcontractor` et la colonne nullable).

## Exécution (2026-11-16 23:59:00Z → 23:59:32Z, depuis `/opt/minefleet/infra/deploy`)

| Étape | Résultat |
|---|---|
| `plan` | `PLAN OK` |
| `apply` | sauvegarde préalable, migrations `0068` + `0069`, « database revision matches all Alembic heads », attente de disponibilité, sondes 200, **`RELEASE OK`**, reçu écrit ; api et web en `f5f4a78` |
| Schéma (lecture) | `alembic_version = 0069` ; `subcontractor` RLS + FORCE ; `vehicle.subcontractor_id` présente |
| Phase A `--live` (23:59:42Z, SHA256 `ed9a572d645819b7…`) | **Échecs : 0** · SKIP : 2 (A3 cosign, A6 manuelle) ; `A4 verdict : OK` (nouvelle table couverte) ; `0069` = `0069` ; aucune image créée |
| Moniteur | `failures: 0` (timer toujours désactivé, ST-13) |
| `GET /api/v1/subcontractors` sans jeton | `401` |

Score et verdict inchangés.
