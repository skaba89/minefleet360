# Audit staging lecture seule — 16 novembre 2026 — après release rc.1 (phase A complète)

- **Release en place** : `v0.1.0-rc.1` = `main@5dfe305`, appliquée le 2026-11-16 à 12:33:16Z → 12:33:38Z par
  `staging-release.sh apply` avec l'outillage corrigé (#450) — sortie « RELEASE OK », reçu
  `release-state/current.json` écrit (SHA256 `629325d3…313cb0`). Le premier apply (12:18Z) et son incident sont
  décrits dans `RELEASE_STAGING_2026-11-16_rc1.md`.
- **Audit** : `audit-staging-readonly.sh --live` (outillage `main@3d9536c`), 2026-11-16 12:33:49Z, rapport brut
  conservé hors dépôt (SHA256 `fd0bb90d…7529f2f`). Résultat brut : 2 échecs, 2 SKIP — analysés ci-dessous.

## Résultats A1–A8

| Contrôle | Résultat | Constat |
|---|---|---|
| A1 versions | **OK** | API et web labellisés `5dfe305…` ; reçu identique au manifeste (release + rollback rc.0) |
| A2 schéma | **OK** | label Alembic `0067` ; `check_schema_revision` : révision base = têtes Alembic |
| A3 images | OK / **SKIP** | images épinglées par digest GHCR ; `cosign` absent de l'hôte → signature vérifiée seulement par l'auto-contrôle du workflow `release-images` (runs `43856008413`, `43857467172`) |
| A4 PostgreSQL | **ÉCHEC script → OK après correction** | le script interrogeait `app.insurance_policy` ; les tables sont dans `public`. Requête corrigée (cette PR) rejouée : `mf_owner`/`mf_app` non-superuser et NOBYPASSRLS ; `insurance_policy` INSERT seul (conforme à 0046) ; 97 tables RLS + FORCE ; aucune RLS sans FORCE ; tables hors RLS = exactement `GLOBAL_TABLES` → **A4 verdict : OK** |
| A5 HTTPS | **OK** | sondes `--live` 200 ; certificat valide du 2026-10-26 au 2027-01-24 |
| A6 comptes/MFA | **SKIP** | manuelle par conception (comptes fictifs du coffre + MFA) — non exécutée |
| A7 surface | **OK** | `/`, `/health`, `/ready`, `/connexion` 200 ; `/docs` et `/openapi.json` renvoient l'application web (documentation API non exposée) |
| A8 santé | **ÉCHEC → partiel** | erreurs API/web 24 h : 0 ; ressources : api 219 Mio/768, db 89 Mio/1 Gio. `probe-all.sh` : sauvegarde « CRITICAL » car le répertoire par défaut du dossier de release est vide → **OK** avec `MF_BACKUP_DIR` pointant les sauvegardes réelles ; **tâches planifiées : UNKNOWN — aucune unité systemd MineFleet installée** |

## Constats ouverts

| # | Constat | Gravité | Action |
|---|---|---|---|
| ST-07 | Aucune unité systemd installée : `minefleet-hse-digest`, `-preventive-evaluate`, `-gps-signal-sweep`, `-notify-deliver`, `-monitor` ne tournent pas sur staging | **Majeur** | installer les unités de `infra/deploy/systemd` (mutation hôte → approbation) ; sans cela, le rang 5 (éprouvetage des alertes) est inexécutable |
| ST-08 | Deux répertoires de déploiement (ancien : `.env.prod`, sauvegardes, cron ; nouveau : outillage de release + copie 600 de `.env.prod`) | Moyen | consolider sur un seul répertoire ; repointer le cron ; supprimer la copie de secrets en trop (approbation) |
| ST-05 | `cosign` absent de l'hôte | Mineur | installation (approbation) ou vérification depuis un poste tiers |
| ST-09 | Copie hors machine non configurée (`offsite.env` absent) | **Bloquant R1** | inchangé — rang 3 du GO/NO-GO |
| ST-10 | Relève SLO GPS non exécutée : `/api/v1/gps/metrics` présente (401 sans jeton) mais aucun jeton de recette disponible pour l'agent | Moyen | jeton d'un compte fictif `fleet.gps.history`, puis `benchmark_metrics.py` |

ST-01 à ST-04 et ST-06 (audit S1 du matin) sont **levés** par la release rc.1.

## Effet sur le GO/NO-GO

- Rang 1 (phases A/B) : **phase B exécutée** (`PLAN OK`) et **phase A exécutée** sans écart de fond hors A6
  (manuelle) et ST-07. Le rang n'est pas entièrement levé : A6 non exécutée.
- R2 (release → rollback) : bascule réelle des images et migration 0064→0067 exercées ; le rollback automatique
  s'est déclenché (sur un faux négatif d'outillage, corrigé par #450). Un exercice de rollback **volontaire**,
  avec reçu, reste à faire pour attester R2.
- Aucun autre blocant levé. Score inchangé.
