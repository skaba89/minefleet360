# Preuve — SSE sous trafic continu d'ingestion (2026-11-26)

**Objet** : exécution locale de l'étape « trafic continu pendant les mesures SSE » (phase 2 du plan `AUDIT_GPS_2026-11-26.md`). Deux émetteurs simultanés contre le serveur réel local (uvicorn 1 worker, base seedée) :

1. **`minefleet demo live-feed`** — `--interval 5 --duration 3` (3 minutes) : 9 traceurs renouvelés par les services, puis émission par la **vraie API traceur** (`POST /api/v1/gps/telemetry`, jetons compositifs, limites et anti-rejeu actifs) ;
2. **`scripts/gps/benchmark_stream.py`** — `--concurrency 5 --hold-seconds 12 --rounds 4` lancé après 12 s de préchauffage, pendant l'émission.

## Résultats

| Mesure | Valeur |
|---|---|
| Positions émises par live-feed | **315 / 315 acceptées, 0 refus, 0 erreur** (9 traceurs, intervalle 5 s) |
| Connexions SSE | **20/20 en 200**, 0 erreur, 0 rate-limit, 0 échec de connexion |
| Première trame | p50 **55,7 ms** · p95 **71,9 ms** · p99 **76,5 ms** |
| Trame initiale manquante | **0** (le snapshot d'ouverture est toujours arrivé) |
| Mises à jour diffusées en direct | **120 snapshots** reçus (6 par flux) — les positions mouvantes arrivent pendant la tenue des flux |
| Heartbeats | 19 |

**Comparaison avec la référence sans trafic** (`BENCHMARK_LOCAL_2026-11-26.md`, 5 connexions, hold 5 s) : premier événement p50 66,4 → 55,7 ms (bruit client), p99 67,9 → 76,5 ms (+8,6 ms sous charge réelle), **aucune dégradation fonctionnelle** : zéro erreur, zéro trame manquante, diffusion des mises à jour confirmée sur les 20 flux.

## Ce que cela prouve — et ne prouve pas

- Le chemin complet **ingestion → notification → diffusion SSE** fonctionne sous données réellement mouvantes avec les garde-fous actifs (aucun contournement, jetons compositifs réels) ;
- La tenue simultanée de flux et l'ingestion n'entraînent ni erreur, ni perte de snapshot d'ouverture ;
- **Ne prouve pas** la capacité de production (1 worker, boucle locale), ni les latences réseau réelles, ni le comportement multi-workers (notification entre workers encore à décider, voir `GPS_SSE_LOAD_TEST.md`).

## Reproduire (base de démonstration locale uniquement)

```bash
minefleet demo live-feed --api-url http://127.0.0.1:8000 --interval 5 --duration 3 &
MF_GPS_BENCH_URL=http://127.0.0.1:8000 MF_GPS_BENCH_TOKEN=<jeton fleet.gps.history> \
  python scripts/gps/benchmark_stream.py --concurrency 5 --hold-seconds 12 --rounds 4
```

Garde-fous respectés : live-feed refuse toute base non DEMO et toute émission hors boucle locale ; la sonde refusait `--hold-seconds 30` (> 15 s) et l'intervalle `2 s` (< 5 s) — limites volontaires de l'outillage, non contournées.
