# Mesure reproductible de charge d'ingestion GPS

Complément de [`GPS_SSE_LOAD_TEST.md`](GPS_SSE_LOAD_TEST.md) : cette sonde mesure la voie montante (`POST /api/v1/gps/telemetry`, contrat `minefleet-json-v1`) — rafale puis phase soutenue — et consolide les métriques serveur `GET /gps/metrics`. Elle ne démontre ni la capacité de production, ni le comportement réseau réel des boîtiers.

## Utilisation uniquement en recette autorisée

Deux modes d'approvisionnement en traceurs :

1. **Traceurs fournis** (recommandé en staging — aucune écriture de configuration) :

```bash
export MF_ENV=staging
export MF_GPS_BENCH_URL=https://staging.example.org
export MF_GPS_BENCH_TRACKERS='DEVICE1=<jeton compositif> DEVICE2=<jeton compositif>'
export MF_GPS_BENCH_TOKEN_READ='<jeton fleet.gps.history pour /gps/metrics>'
python scripts/gps/benchmark_ingest.py --devices 2 --burst-points 10 --sustained-seconds 60
```

2. **Provisioning par la sonde** (base de démonstration uniquement) : `--provision` avec `MF_GPS_BENCH_TOKEN_ADMIN` (jeton portant `fleet.gps.manage`). La sonde n'associe que des véhicules **sans traceur actif** ; `--allow-revoke` (destructeur : révocation d'associations existantes) doit rester réservé à une base de démonstration locale.

Les jetons de provisioning sont déjà préfixés `gps_` : la sonde les transmet tels quels (`Bearer <jeton>`) — la route dépouille `Bearer gps_` et un second préfixe produirait un `401 AUTH_REQUIRED`.

## Garde-fous

- Refus hors localhost sans HTTPS, refus si `MF_ENV=production`, aucune identifiant dans l'URL.
- Limites : 8 traceurs, 100 points en rafale, 300 s soutenues, espacement ≥ 0,5 s.
- Après un provisioning, la sonde attend **3 s** : la prévalidation refuse à juste titre (`409`) tout point antérieur à l'association active (`recorded_at < binding.active_from`, protection anti-réaffectation). Sur une association fraîche, des points émis moins d'une seconde après le provisioning sont donc refusés — comportement correct, constaté et documenté dans [`AUDIT_GPS_2026-11-26.md`](audit/AUDIT_GPS_2026-11-26.md).
- Le rapport n'imprime **aucun** jeton, IMEI ou coordonnée : compteurs, percentiles de latence client, codes d'erreur stables uniquement.

## Lecture du rapport

- `http_204` : positions acceptées ; `http_409` : refus anti-rejeu/dédup/anti-réaffectation (attendus sous rafale) ; `http_429` : limiteurs (par traceur 60/min, par IP 1000/min) ; `other` : toute autre réponse — **zéro toléré**.
- `client_ms_p50/p95/p99` : latence côté client (dépend de l'environnement et du TLS) ; la valeur utile est l'absence de dégradation entre rafale et soutenu.
- `metrics_before/after` : si le jeton de lecture porte `fleet.gps.history` — fraîcheur, `stale_count`, positions en fenêtre, latence d'ingestion p50/p95/p99 (mesure `received_at − recorded_at` : avec un émetteur à offset fixe de 1 s, la constance p50=p95=p99 prouve l'absence de dégradation).

## Qualité et suite

Les tests `scripts/gps/test_benchmark_ingest.py` sont exécutés par la CI `gps-benchmark-tests` sur tout changement de `scripts/gps/**` — sans réseau ni secret. Aucune mesure de charge depuis la CI vers un environnement partagé. Prochaines étapes : exécution signée sur staging (prérequis GO n° 3/6), puis trafic continu (`demo live-feed`) pendant les mesures SSE pour éprouver le flux sous données réellement mouvantes.
