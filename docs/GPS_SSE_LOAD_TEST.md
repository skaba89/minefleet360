# Mesure reproductible de concurrence du flux GPS SSE

Objectif : mesurer la réception initiale du flux SSE et son comportement en saturation après les PR #348–#350. Cette sonde **ne démontre ni le push événementiel, ni la latence ingestion→écran, ni une capacité de production**.

## Utilisation uniquement en recette autorisée

```bash
export MF_ENV=staging
export MF_GPS_BENCH_URL=https://staging.example.org
export MF_GPS_BENCH_TOKEN='<jeton éphémère lecture GPS>'
python scripts/gps/benchmark_stream.py --concurrency 5 --hold-seconds 5
python scripts/gps/benchmark_stream.py --concurrency 32 --hold-seconds 5
python scripts/gps/benchmark_stream.py --concurrency 40 --hold-seconds 5
```

Le plafond existant est **32 connexions par worker**. Un 429 peut être normal lorsque le plafond est atteint. Plusieurs workers peuvent distribuer ces connexions : 40 connexions au niveau du proxy ne garantissent donc pas un 429. Les connexions sont ouvertes avec un jeton limité et des données de recette, jamais un jeton d'administration.

La sonde refuse HTTP hors localhost, les identifiants dans l'URL et l'exécution quand `MF_ENV=production`. La limite est de 64 connexions, tenues au plus 15 secondes. Elle n'exporte **aucune position, aucun identifiant de véhicule, aucune réponse brute**. Les champs rapportés sont : réponses 200/429/401/403, erreurs, percentiles du premier octet de trame, nombre de snapshots et heartbeats.

**Attention** : le retour 200 avec un snapshot ne prouve pas une diffusion immédiatement après ingestion. Les mesures p95 sont des latences côté client et dépendent de l'environnement, du TLS et du proxy. Les horloges ne sont pas synchronisées avec les boîtiers réels.

## Qualité et suite

Les tests unitaires `scripts/gps/test_benchmark_stream.py` sont lancés avec la CI `gps-benchmark-tests` sur les changements de `scripts/gps/**`. N'effectuer aucune mesure de charge depuis la CI sur un environnement partagé.

Prochain chantier : décider et implémenter une notification transmise entre workers (par ex. PostgreSQL LISTEN/NOTIFY, après mesure des volumes) avec snapshot SQL soumis à autorisation RLS, périodicité de revalidation et rattrapage après interruption. Le score audité ne change pas sans preuve supplémentaire.
