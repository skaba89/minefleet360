# Preuve — benchmarks GPS réels en local (2026-11-26)

**Environnement** : sandbox, PostgreSQL 17.12 + PostGIS 3.5.2 (locale C.UTF-8), API uvicorn **1 worker** (sans TLS ni proxy), base seedée `demo seed --profile small --seed 42` : 22 348 positions GPS, 15 traceurs, 25 geofences, 28 véhicules (3 sociétés — isolation multi-tenant observée : TENANT_ADMIN/OPS_MANAGER ne voient que les 12 véhicules de leur société). Comptes démo OPS_MANAGER et TENANT_ADMIN **enrôlés MFA via l'API** (setup → confirm TOTP RFC 6238 → challenge → verify) — le flux réel d'enrôlement obligatoire a été éprouvé. 6 traceurs provisionnés par le flux `fleet.gps.manage` légitime (révocation puis re-provisionnement, base démo locale uniquement). Aucun staging ni production touchés.

**Outil** : `scripts/gps/benchmark_stream.py`, `benchmark_latest.py`, `/gps/metrics`, sonde d'ingestion dédiée (non versionnée, protocole reproduit dans `AUDIT_GPS_2026-11-26.md` §3).

## Résultats

### SSE (`benchmark_stream.py --timeout 20`)

| Concurrency | 200 | 429 | erreurs | first_frame p50 | p95 |
|---|---|---|---|---|---|
| 5 (×3 exécutions) | 5/5 | 0 | 0 | 50,1 / 59,2 / 66,4 ms | 51,2 / 61,7 / 67,9 ms |
| 32 (×3 exécutions) | 32/32 | 0 | 0 | 304,2 / 332,5 / 516,7 ms | 403,2 / 399,9 / 594,6 ms |
| 40 | 32 | **8** | 0 | 330–437 ms | 444–528 ms |

Le plafond 32 connexions/worker se comporte exactement comme documenté : au-delà, `429 + Retry-After`, zéro erreur protocolaire.

### Lecture dernière position (`benchmark_latest.py --samples 20`)

p50 **11,1 ms** / p95 **13,3 ms** / p99 **14,1 ms** / max 14,1 ms.

### Ingestion (6 traceurs, contrat `minefleet-json-v1`)

- **Rafale** (10 pts/traceur, 0,6 s d'espacement, ~10 req/s) : **48×204, 12×409, 0 autre** en 7 s — le garde-fou anti-rejeu/dédup refuse activement sous rafale rapide (analyse fine des 12 refus : à instrumenter en phase 2).
- **Soutenu** (24 pts/traceur, 2,5 s d'espacement, 60,9 s) : **144/144 acceptés**, latence client p50 **22,4 ms**, p95 **79,4 ms**, 2,36 pts/s (limite par traceur 60/min).
- **`/gps/metrics` avant/après** : positions en fenêtre 0 → **192** ; **stale_count 6 → 0** ; fraîcheur p50 60 795 s → **3,7 s** ; latence d'ingestion p50=p95=p99=1,0 s (offset émetteur volontaire de 1 s — la mesure utile est l'absence de dégradation et la fraîcheur).

## Bug trouvé et corrigé (première exécution réelle du benchmark)

À `--timeout` 10 s (défaut) < heartbeat/revalidation serveur **15 s** (`INTERVAL_SECONDS`, `gps_stream_router.py:36`), toute connexion sur flux inactif se terminait en `TimeoutError` et le handler réseau **jetait les mesures déjà collectées** (status=0, first_frame perdu) — 100 % des connexions en échec apparent. Avant correction, reproductible : 8/8 connexions `status=0`, `errors=8`, aucune mesure.

Après correction (`observe()` conserve first_frame/snapshots/heartbeats et incrémente failures ; docstring documentant la contrainte) : même scénario → `http_200=8, first_frame p50 97,3 ms, snapshots 8, first_frame_missing=0`. Test unitaire ajouté : `test_timeout_during_hold_preserves_measurements` — suite `scripts/gps` : **10/10 verts**.

## Limites

1 worker sans TLS/proxy, 6 traceurs actifs, sandbox — baseline locale, pas un SLO staging. L'exécution signée sur staging (avec trafic continu via `demo live-feed`) reste requise (prérequis GO n° 3/6, plan phase 5).
