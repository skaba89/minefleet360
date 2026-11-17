# Release staging 0.1.0-rc.6 — 17 novembre 2026 — correctif d'un défaut réel (audit de l'objectif SLA)

- **Approbation explicite** : propriétaire du projet (« Déployer rc.6 »).
- **Motif** : rc.5 portait un défaut réel livré par #470 — modifier l'objectif SLA d'un sous-traitant renvoyait une
  erreur 500 (valeur `Decimal` non sérialisable dans l'audit). Corrigé par #473 avec régression.
- **Release** : `v0.1.0-rc.6` = `main@f888194`, **sans migration** (tête `0072`). Images signées (run `44038312490`) :
  api `sha256:527816fe…425d4187`, web `sha256:b6948ffd…c807a2` ; labels vérifiés. **Rollback** : rc.5 (`848625a`).

## Exécution (2026-11-17 07:25:04Z → 07:25:34Z, depuis `/opt/minefleet/infra/deploy`)

| Étape | Résultat |
|---|---|
| `plan` | `PLAN OK` |
| `apply` | sauvegarde préalable, révision base = têtes Alembic (aucune migration), attente de disponibilité, sondes 200, **`RELEASE OK`**, reçu écrit ; api et web en `f888194` |
| Phase A `--live` (07:25:35Z, SHA256 `99551a6c3d83ac25…`) | **Échecs : 0** · SKIP : 2 (A3 cosign, A6 manuelle) ; `A4 verdict : OK` ; `0072` = `0072` ; aucune image créée |
| Moniteur | `failures: 0` (timer toujours désactivé, ST-13) |

Score (86) et verdict inchangés.
