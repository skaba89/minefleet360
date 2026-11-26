# Preuve — sonde d'ingestion versionnée, exécution locale (2026-11-26)

**Objet** : première exécution de `scripts/gps/benchmark_ingest.py` (v1.0) contre le serveur local réel (uvicorn 1 worker, PostgreSQL 17.12 + PostGIS, base seedée `demo seed --profile small --seed 42`). Aucun staging ni production touchés ; provisioning avec `--allow-revoke` sur la base de démonstration locale uniquement.

## Résultats (3 traceurs synthétiques)

| Phase | Points | 204 | 409 | 429 | other | Débit accepté | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|
| Rafale (10 pts/traceur, 0,6 s) | 30 | **30** | 0 | 0 | 0 | 4,64 pts/s | 39,4 ms | 61,6 ms | 62,6 ms |
| Soutenu (45 s, 2,5 s) | 54 | **54** | 0 | 0 | 0 | 1,18 pts/s | 35,5 ms | 59,5 ms | 64,0 ms |

`GET /gps/metrics` : positions en fenêtre 92 → 176 ; latence d'ingestion p50=p95=p99=1,0 s (offset émetteur volontaire de 1 s — la constance prouve l'absence de dégradation) ; `stale_count` stable à 3 (véhicules seedés non alimentés pendant la mesure).

## Analyse fine des 409 constatés le 26 nov (résolue)

L'expérience contrôlée sur un traceur fraîchement provisionné (10 points antérieurs au provisioning, puis 10 points à `now − 1 s` espacés de 0,6 s) prouve :

1. Les points dont `recorded_at < binding.active_from` sont refusés `409 CONFLICT` — protection **anti-réaffectation** (`gps_ingestion_preflight.py:41`), conforme à `GPS_INGESTION_BOUNDARY.md` (« un point relevé avant la nouvelle association ne doit pas être attribué au nouveau camion ») ;
2. Les refus n'avancent pas le compteur de séquence (savepoint annulé, dernière séquence en base inchangée) ;
3. Dès que `recorded_at > active_from`, tous les points sont acceptés (8/8 consécutifs).

Les 12 refus de la première campagne étaient donc **un artefact de la sonde ad hoc** (offset `−1 s` + rafale émise moins d'une seconde après le provisioning de 6 traceurs), pas un défaut serveur. La sonde versionnée corrige l'artefact (attente de 3 s post-provisioning) et la relance produit **0 refus**.

## Note d'implémentation

Le jeton de provisioning est retourné **déjà préfixé `gps_`** ; l'en-tête correct est `Bearer <jeton>` (la route dépouille `Bearer gps_`). Un double préfixe (`Bearer gps_gps_…`) produit un `401 AUTH_REQUIRED` — le contrat strict du jeton composite rejette la valeur transformée. Un test unitaire (`test_authorization_uses_provisioning_token_without_second_prefix`) verrouille ce comportement de la sonde.

## Suite

Exécution signée sur staging (prérequis GO n° 3/6), trafic continu pendant les mesures, puis harnais contractuel d'adaptateurs (phase 2/3 du plan `AUDIT_GPS_2026-11-26.md`).
