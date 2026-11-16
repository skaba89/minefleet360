# Audit staging lecture seule — 16 novembre 2026 — session interrompue à S1

- **Plan appliqué** : `docs/ops/PLAN_EXECUTION_STAGING.md` (phases A/B, lecture seule).
- **Base de référence** : `main@6d682c4` (PR #448) — CI `ci`, `security-static`, `e2e-isolation` vertes
  (10/10 check-runs `success`, vérifiés par API le 2026-11-16).
- **Hôte** : VPS OVHcloud partagé (nom d'hôte non reproduit), répertoire de déploiement
  `~/minefleet360/infra/deploy`, `.env.prod` présent avec `MF_ENV=staging` (seule cette ligne a été lue ;
  aucun secret affiché ni recopié).
- **Opérateur** : agent Claude Code (session outillée), lecture seule. Aucune commande de mutation.
- **Résultat** : **interruption au point de décision S1** (§3 du plan : « Label de révision API ≠ web ≠ reçu
  → interruption, ne pas poursuivre S2+ »).

## Correction d'un écart documentaire

`docs/audit/COMMERCIAL_READINESS_CURRENT.md` indiquait « VPS OVHcloud / staging : **non accessible** ».
Constat du 16 novembre : l'environnement de l'agent **est** l'hôte staging. L'accès en lecture existe ;
toute mutation reste soumise à approbation explicite.

## S0 — Pré-vol

| Élément | Constat |
|---|---|
| `.env.prod` | présent, `MF_ENV=staging` |
| `MINEFLEET_STAGING_URL` | non défini dans l'environnement de session |
| `docker` / `jq` / `openssl` | présents |
| `cosign` | **absent** de l'hôte → A3 (vérification de signature) impossible en l'état |
| `audit-staging-readonly.sh` | **absent** du répertoire déployé (copie de l'hôte antérieure à #439) |
| `release-state/current.json` | **absent** (aucun reçu de release) |

## S1 — Versions déployées (A1) — sorties horodatées 2026-11-16 UTC

```
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
NAME              IMAGE                             SERVICE   CREATED       STATUS
minefleet-api-1   minefleet-api-candidate:6a4f696   api       10 days ago   Up 10 days
minefleet-db-1    postgis/postgis:16-3.4            db        3 weeks ago   Up 3 weeks (healthy)
minefleet-web-1   minefleet-web-candidate:b8a43a2   web       10 days ago   Up 10 days

docker inspect (labels OCI) :
/minefleet-api-1 rev=<vide> alembic=<vide> started=2026-11-05T20:30:15Z restarts=0
/minefleet-web-1 rev=<vide> alembic=<vide> started=2026-11-05T21:25:23Z restarts=0
```

Analyse (dépôt, hors hôte) :

| Composant | Commit | Date | Retard sur `main` | Tête Alembic du commit |
|---|---|---|---:|---|
| API | `6a4f696` (#368) | 2026-11-05 | 77 commits | `0063_gps_alert_notifications` |
| Web | `b8a43a2` (#370) | 2026-11-05 | 75 commits | `0063_gps_alert_notifications` |
| `main` | `6d682c4` (#448) | 2026-11-16 | — | `0067_saas_invoicing` |

## Anomalies consignées

| # | Anomalie | Gravité | Conséquence |
|---|---|---|---|
| ST-01 | API `6a4f696` ≠ web `b8a43a2` | Bloquant S1 | État non reproductible ; interruption réglementaire du plan |
| ST-02 | Images `*-candidate:<sha>` construites localement, sans labels OCI ni digest GHCR | Bloquant | Chaîne d'approvisionnement signée (#376) non utilisée sur staging ; `cosign verify` impossible |
| ST-03 | Aucun reçu `release-state/current.json` | Bloquant | Déploiement hors `staging-release.sh` ; rollback par digest indisponible |
| ST-04 | Staging 75–77 commits en retard ; schéma 0063 vs 0067 | Majeur | `GET /gps/metrics` (#438), plans/abonnements/facturation SaaS (0065–0067) **absents** de staging ; `scripts/gps/benchmark_metrics.py` inexécutable |
| ST-05 | `cosign` absent de l'hôte | Mineur | À installer (action hôte → approbation) ou vérification depuis un poste tiers |
| ST-06 | Script d'audit #439 absent de l'hôte | Mineur | Copie de dépôt sur l'hôte non synchronisée |

## Séquences non exécutées (volontairement)

S2–S10 non exécutées conformément au §3 du plan. A2 `run --rm migrate` n'aurait de toute façon pas été lancé
dans une session « aucun conteneur démarré » sans accord explicite ; la lecture `SELECT version_num FROM
alembic_version` est l'alternative proposée.

## Effet sur le GO/NO-GO

Aucun blocant levé. Le rang 1 (« phases A/B staging ») passe de « jamais exécuté » à **« exécuté, en échec à
S1 »** : la prochaine action n'est plus l'accès à l'hôte mais une **remise en conformité du déploiement**
(release par digest signé de `main`), qui est une mutation soumise à approbation.

## Commandes préparées (à n'exécuter qu'après approbation écrite)

Phase de remise en conformité (mutation — approbation requise) :

1. Publier les images signées du SHA candidat (workflow `release-images` sur tag), récupérer les digests GHCR.
2. Préparer le manifeste hors dépôt depuis `release-manifest.example.json`, puis :
   `python3 release_manifest.py validate <manifeste>` et `bash staging-release.sh plan <manifeste>` (lecture seule).
3. Sauvegarde préalable (`backup.sh`, < 1 h exigée par `staging-release.sh`), puis `staging-release.sh apply`
   (migrations 0064→0067).

Phase A rejouée après remise en conformité (lecture seule) :

```
cd ~/minefleet360/infra/deploy   # copie synchronisée sur main
export MINEFLEET_STAGING_URL=https://<domaine-staging>
bash audit-staging-readonly.sh --plan
bash audit-staging-readonly.sh --live --out audit-staging-readonly-$(date -u +%Y%m%dT%H%M%SZ).txt
python3 ../../scripts/gps/benchmark_metrics.py --help   # relève SLO GPS une fois /gps/metrics déployé
```
