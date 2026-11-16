# Release staging 0.1.0-rc.3 — 16 novembre 2026

- **Approbation** : propriétaire du projet, 2026-11-16 (« rc.3 sur staging »).
- **Release** : `v0.1.0-rc.3` = `main@4501f6d` — chantier fiabilité : durée de service par engin (#461), utilisation
  et MTBF en heures moteur (#462), productivité en tonnes mesurées par heure moteur soumise à
  `dispatch.indicators.read` (#463). Aucune migration (tête `0067`).
- **Images** signées (run `43927994238`) : api `sha256:cee97a14…0fd9f15b`, web `sha256:0bf49497…389146713` ;
  labels vérifiés (révision `4501f6d`, Alembic `0067`). **Rollback** : rc.2 (`4b953ee`).

## Exécution

| Étape | Résultat |
|---|---|
| `staging-release.sh plan` | `PLAN OK` |
| `staging-release.sh apply` (18:23:58Z → 18:24:28Z) | `RELEASE OK` — attente de disponibilité, sondes 200, reçu écrit ; api et web en `4501f6d` |
| Phase A `--live` (18:24:29Z, SHA256 `d0e2c744e3dda151…`) | **Échecs : 0** · SKIP : 2 (A3 cosign absent, A6 manuelle) ; `A4 verdict : OK` ; `0067` = `0067` ; aucune image créée |
| Moniteur (compte de service) | `failures: 0` (timer toujours désactivé, ST-13) |
| `GET /api/v1/maintenance/reliability` sans jeton | `401` |

Score et verdict inchangés : aucune preuve terrain nouvelle (les indicateurs restent à valider métier sur données réelles).
