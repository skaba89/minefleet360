# Preuves de performance GPS

Ce protocole complète le scénario `GPS-06` sans transformer une mesure synthétique en SLO contractuel. Les scripts n'enregistrent ni jeton, ni coordonnée, ni identifiant de véhicule. Ils produisent des échantillons individuels expurgés afin de recalculer p50, p95 et p99.

## Préconditions

- environnement staging isolé et autorisé, jamais la production ;
- jeu de véhicules synthétiques et compte de lecture limité au tenant/site d'essai ;
- horloges synchronisées ;
- volumes, fréquence d'émission, concurrence et seuils décidés avec les utilisateurs métiers avant le test ;
- supervision CPU, RAM, connexions PostgreSQL et pool applicatif active séparément.

Les secrets sont fournis uniquement par variables d'environnement et ne doivent apparaître ni dans la ligne de commande, ni dans le fichier de résultat.

## Lecture REST de la dernière position

```bash
export MF_ENV=staging
export MF_GPS_BENCH_URL=https://staging.example.org
export MF_GPS_BENCH_TOKEN=REDACTED
python scripts/gps/benchmark_latest.py \
  --samples 100 --interval 0.5 --timeout 10 \
  > /chemin/securise/gps-latest.json
```

Le rapport contient le taux de succès/échec, les latences HTTP p50/p95/p99/max, le nombre maximal de positions observées et les mesures individuelles expurgées. Il ne mesure pas la latence ingestion→affichage.

## Connexions SSE et reconnexions

```bash
export MF_ENV=staging
export MF_GPS_BENCH_URL=https://staging.example.org
export MF_GPS_BENCH_TOKEN=REDACTED
python scripts/gps/benchmark_stream.py \
  --concurrency 10 --rounds 3 --reconnect-delay 2 \
  --hold-seconds 10 --timeout 15 \
  > /chemin/securise/gps-stream.json
```

Chaque round recrée toutes les connexions. Le rapport contient les tentatives totales, les reconnexions, HTTP 200/429/401/403, erreurs, trames initiales absentes, p50/p95/p99 du premier frame, snapshots, heartbeats et échantillons individuels expurgés. HTTP 429 est compté séparément comme saturation attendue, pas comme succès.

## Conservation des résultats

Avant de versionner un résultat réel :

1. vérifier que le JSON ne contient aucun jeton, URL interne sensible, coordonnée, identifiant de véhicule, nom de personne ou donnée client ;
2. ajouter commit testé, date UTC, environnement pseudonymisé, configuration de charge et versions d'image ;
3. joindre les séries CPU/RAM/DB, les événements perdus/dupliqués/hors ordre et le temps ingestion→UI provenant des autres instruments ;
4. consigner toute panne ou modification de configuration pendant l'essai ;
5. faire relire le fichier avant dépôt sous `docs/qa/evidence/gps/`.

Aucun résultat fictif ne doit être ajouté pour remplir ce répertoire. Une exécution CI des tests unitaires prouve seulement le calcul, l'expurgation et les garde-fous des scripts.

## Critère de décision

Le rapport doit conserver les valeurs brutes et comparer les résultats aux seuils convenus, sans modifier ceux-ci après l'essai. Un verdict GPS nécessite aussi le taux d'événements perdus, la consommation des ressources, les connexions PostgreSQL, la reprise après panne DB/worker et une mesure ingestion→affichage. Le p99 du premier frame SSE ou de l'appel REST ne remplace aucune de ces mesures.
