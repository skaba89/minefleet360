# Release staging 0.1.0-rc.1 — 16 novembre 2026 — apply exécuté, rollback automatique déclenché

- **Approbation** : propriétaire du projet, 2026-11-16 (fusion #449, tag + images signées, dry-run, apply complet).
- **Manifeste** (hors dépôt, 600) : release `5dfe305` (tag `v0.1.0-rc.1`), rollback `6d682c4` (tag `v0.1.0-rc.0`),
  variante `edge`, `migration_head=0067`, stratégie `application-only-forward-schema`.
- **Images** (GHCR, Cosign keyless + SLSA, workflow `release-images`) :
  - rc.1 api `sha256:1c886570…efc65c`, web `sha256:65feefd6…6e48e5c` — labels vérifiés (révision `5dfe305`, Alembic `0067`).
  - rc.0 api `sha256:5413d349…dd0cf33`, web `sha256:f376fd75…bd74da` — labels vérifiés (révision `6d682c4`, Alembic `0067`).
- **Outils** : copie de `main@5dfe305` dans un répertoire de release distinct ; aucun répertoire existant écrasé.

## Préalables corrigés pendant le dry-run

| Constat | Action |
|---|---|
| `plan` en échec : `MF_RATE_LIMIT_KEY` absent de `.env.prod` (obligatoire depuis le 5 nov) — seule variable obligatoire manquante sur 9 | sauvegarde du fichier (600), ajout d'une clé générée `openssl rand -hex 32`, jamais affichée → `PLAN OK` |
| `backup.sh` lit `.env.prod` dans son propre répertoire (ignore `MF_STAGING_SECRETS_FILE`) | copie 600 du fichier de secrets dans le répertoire de release |
| Empreintes compose : `db`, `api`, `web` seraient recréés | accepté (volume `minefleet_db-data` conservé) |

## Déroulé de l'apply (2026-11-16 12:18:52Z → 12:19:33Z)

1. Sonde `--live` préalable : 200 sur `/`, `/api/v1/health`, `/api/v1/ready`.
2. Sauvegarde PostgreSQL locale lisible (`pg_restore --list`) ; copie hors machine **non configurée**.
3. Pull des images par digest, contrôle des labels révision + Alembic : OK.
4. `db` recréé (sain), migrations `0064 → 0067` appliquées, `check_schema_revision` : **« database revision matches all Alembic heads »**.
5. `api`/`web` rc.1 démarrés → sonde immédiate : `/` 200, **`/api/v1/health` 502** → rollback automatique.
6. `api`/`web` rc.0 démarrés → sonde immédiate : **502** → « CRITICAL: automatic application rollback also failed », exit 1.
7. Constat manuel 6 s plus tard : rc.0 servi, `/`, `/health`, `/ready` = 200, `/api/v1/gps/metrics` = 401 (route présente).

## Analyse

Cause racine : `staging-release.sh` sondait l'API **immédiatement après `up -d`**, avant la fin du démarrage
d'uvicorn ; le proxy edge répond 502 pendant cette fenêtre. Ni la release ni l'image n'étaient fautives.
Correctif (cette PR) : attente bornée de `/api/v1/ready` (défaut 120 s, intervalle 3 s, bornes validées avant
toute mutation) avant la sonde inchangée, en release comme en rollback ; 4 tests de non-régression qui
échouent sans le correctif.

## État de staging à l'issue

| Élément | État |
|---|---|
| Applications | rc.0 (`6d682c4`, images signées par digest) — code identique à rc.1 hors documentation |
| Schéma | `0067` (tête de `main`) |
| Reçu `release-state/current.json` | **non écrit** (script terminé en échec) |
| Preuve R2 (release → rollback) | **partielle** : migration et bascule d'images réelles exercées ; la sonde de fin a échoué pour un défaut d'outillage, désormais corrigé et testé |

## Suite

Après fusion du correctif : rejouer `staging-release.sh apply` (même manifeste) avec l'outillage corrigé pour
obtenir rc.1 + reçu, puis phase A complète (A1–A8) et relève `benchmark_metrics.py`.
