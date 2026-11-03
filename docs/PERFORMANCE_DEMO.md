# Performances mesurées sur les jeux DEMO

État au 3 novembre 2026. **Mesures sur une seule machine de développement** (6 vCPU, 11 Gio de RAM, PostgreSQL
16 + PostGIS en conteneur sur la même machine, API `uvicorn` un seul processus, sans cache ni réglage).
Elles donnent des ordres de grandeur et des tendances, pas une garantie de production. Aucune prise en charge
d'une flotte de 1 000 engins n'est revendiquée tant qu'elle n'a pas été mesurée (voir §4).

Reproduire : `minefleet demo seed --profile <p> --parallel …`, lancer l'API locale, puis
`python scripts/perf_demo.py --accounts <fichier> --label <p> --api http://127.0.0.1:8000`.

## 1. Profils et volumes

| Profil | Période | Engins (dont transport) | Missions | Rotations pesées | Positions GPS | Durée de génération |
|---|---|---|---|---|---|---|
| `qa` | 9 j | 28 (15) | 129 | 286 | 4 914 (9 j, pas 5 min) | 91 s (parallèle, avec migrations et `verify`) |
| `small` | 14 j | 28 (15) | ≈205 | ≈580 | ≈22 000 (14 j, pas 2 min) | ≈ 8 min 30 (séquentiel) |
| `standard` | 90 j | 84 (45) | 4 044 | 15 990 | 65 900 (14 derniers jours, pas 3 min) | 37 min (parallèle) — base 193 Mo |
| `large` | 60 j | 224 (120) | 7 194 | 28 441 | 56 118 (7 derniers jours, pas 5 min) | 61 min (parallèle) — base 290 Mo |

Les deux gros profils passent `demo verify` à 38/38 ; une panne réparée tous les 15 jours (15 OT clôturés en
`standard`, 9 en `large`) alimente la fiabilité et les coûts atelier.

`standard` et `large` limitent l'historique GPS aux derniers jours (`gps_days`) ; missions, pesées, carburant,
atelier et coûts couvrent toute la période, et le compteur kilométrique suit toujours la distance du tracé.
`--parallel` construit une société par processus : volumes identiques au mode séquentiel (vérifié sur `qa` :
289 rotations, 286 pesées, 4 914 positions, 60 distributions dans les deux modes).

## 2. Débit d'écriture des services (profilage du chargement `qa`)

| Opération (service réel, audit compris) | Coût unitaire mesuré |
|---|---|
| Événement de mission (`record_event` : éligibilité, verrou, audit) | ≈ 48 ms |
| Position GPS (passerelle authentifiée : secret, association, séquence, savepoint) | ≈ 19 ms |
| Ouverture de session + chargement des droits par appel | ≈ 5 ms (7 % du total) |

Lecture : un processus enregistre ≈ 20 événements de mission par seconde. Pour une exploitation réelle de
1 000 engins à ≈ 20 événements par jour, la charge moyenne est ≈ 0,2 écriture par seconde : ce n'est pas le
facteur limitant. En revanche, **générer** un long historique par les services prend du temps (§3) ; le
générateur ne contourne volontairement pas les services pour aller plus vite.

## 3. Temps de réponse des écrans clés (compte AUDITOR, société demo-bauxite)

### qa — 10 appels mesurés par route

| Écran / route | p50 (ms) | p95 (ms) | max (ms) | Taille (Kio) |
|---|---:|---:|---:|---:|
| Parc (liste, ≤ 200) | 24 | 30 | 30 | 8 |
| Missions (50) | 52 | 101 | 101 | 47 |
| Indicateurs 7 j | 43 | 52 | 52 | 1 |
| Indicateurs 30 j | 44 | 49 | 49 | 1 |
| Coût complet 30 j | 61 | 84 | 84 | 9 |
| Carburant (tableau de bord) | 38 | 43 | 43 | 4 |
| HSE (synthèse 90 j) | 22 | 33 | 33 | 0 |
| Fiabilité atelier | 26 | 33 | 33 | 5 |
| Dernières positions GPS | 29 | 35 | 35 | 2 |
| Trajet GPS 24 h | 35 | 46 | 46 | 8 |

### standard (36 engins et 25 719 positions pour demo-bauxite) — 15 appels par route

| Écran / route | Statut | p50 (ms) | p95 (ms) | max (ms) | Taille (Kio) |
|---|---|---:|---:|---:|---:|
| Parc (liste, ≤ 200) | 200 | 27 | 29 | 30 | 24 |
| Missions (50) | 200 | 48 | 61 | 103 | 47 |
| Pesées (50) | 200 | 63 | 78 | 81 | 41 |
| Indicateurs 7 j | 200 | 62 | 75 | 90 | 1 |
| Indicateurs 30 j | 200 | 83 | 94 | 96 | 1 |
| Coût complet 30 j | 200 | 126 | 148 | 303 | 25 |
| Carburant (tableau de bord) | 200 | 47 | 55 | 59 | 5 |
| HSE (synthèse 90 j) | 200 | 24 | 29 | 36 | 0 |
| Fiabilité atelier | 200 | 25 | 29 | 31 | 14 |
| Dernières positions GPS | 200 | 27 | 30 | 31 | 5 |
| Trajet GPS 24 h | 200 | 46 | 51 | 51 | 25 |

### large (96 engins et 22 539 positions pour demo-bauxite) — 15 appels par route

| Écran / route | Statut | p50 (ms) | p95 (ms) | max (ms) | Taille (Kio) |
|---|---|---:|---:|---:|---:|
| Parc (liste, ≤ 200) | 200 | 30 | 35 | 38 | 64 |
| Missions (50) | 200 | 70 | 91 | 102 | 48 |
| Pesées (50) | 200 | 98 | 111 | 113 | 41 |
| Indicateurs 7 j | 200 | 90 | 95 | 115 | 1 |
| Indicateurs 30 j | 200 | 133 | 170 | 178 | 1 |
| Coût complet 30 j | 200 | 327 | 493 | 513 | 67 |
| Carburant (tableau de bord) | 200 | 51 | 68 | 72 | 5 |
| HSE (synthèse 90 j) | 200 | 22 | 26 | 29 | 0 |
| Fiabilité atelier | 200 | 33 | 39 | 42 | 36 |
| Dernières positions GPS | 200 | 30 | 37 | 42 | 14 |
| Trajet GPS 24 h | 200 | 45 | 48 | 52 | 12 |

Mesures `standard` et `large` prises avec la correction des dernières positions GPS (#331).

### Constats

| Écran | Évolution qa → standard → large (p50) | Lecture |
|---|---|---|
| Dernières positions GPS | 29 → 75 → — ms **avant** #331 ; 27 → 30 ms **après** | la requête triait tout l'historique de la société ; corrigée (lecture indexée par véhicule, 58 → 2 ms côté SQL) |
| Coût complet 30 j | 61 → 126 → 327 ms **avant** correction ; **197 ms** après (large, voir §3 bis) | la composante pneus était quadratique (chaque pneu × chaque engin) et le comptage des missions terminées lisait tous les événements ; corrigés le 3 novembre |
| Indicateurs 30 j | 44 → 83 → 133 ms | croît avec les rotations de la période ; acceptable à ces volumes |
| Missions, pesées (pagination 50) | 48–98 ms | stable : pagination effective |
| Parc, HSE, fiabilité, carburant, trajet GPS 24 h | 22–51 ms | stables |


### 3 bis. Correction du coût complet (3 novembre 2026, jeu `large`, demo-bauxite)

| Version | Coût complet 30 j p50 / p95 (ms) | Indicateurs 30 j p50 (ms) |
|---|---:|---:|
| main avant correction | 373 / 498 | — |
| main + index seul (migration 0057) | 286 / 445 | 116 |
| **branche (pneus en un passage + index)** | **197 / 350** | **110** |

- **Pneus** : le calcul rejouait l'historique de chaque pneu pour chaque engin de la société
  (pneus × engins × événements). Il est désormais fait en un seul passage par pneu, chaque montage étant attribué
  à son engin (`_km_by_vehicle`). Résultat identique vérifié sur 5 000 historiques aléatoires contre l'ancien
  algorithme, et réponses de l'API identiques sur trois périodes du jeu `large`. Banc isolé à 224 engins et
  1 344 pneus : 752 → 20 ms.
- **Missions terminées** : sans index sur `(event_type, occurred_at)`, PostgreSQL lisait les 54 000 événements de
  la société pour en garder 1 400 (24 → 6 ms avec l'index `ix_me_type_time`, migration 0057, qui sert aussi aux
  indicateurs de pesée).
- Reste : environ 65 ms de SQL répartis entre six requêtes de 3 à 14 ms (compteurs, pesées, carburant,
  historique des pneus), sans requête dominante. L'historique complet des pneus de la société reste chargé à
  chaque appel ; ce sera le prochain levier si les flottes grossissent (valeurs à date pré-calculées par pneu).

## 4. Non mesuré à ce stade

- Flotte de 1 000 engins : le chargement par les services prendrait de l'ordre d'une journée par cette voie ;
  une mesure à cette échelle demandera un chargeur de volume dédié (à concevoir sans contourner RLS ni audit)
  et une machine représentative de la production.
- Ingestion GPS continue de nombreux traceurs en même temps que la consultation, réseau mobile lent, et
  rapports sur des sociétés dépassant le plafond d'export de 5 000 lignes (concurrence et exports : §5).

## 5. Plusieurs utilisateurs simultanés et exports (3 novembre 2026, jeu `large`)

Mesure : `python scripts/perf_load.py --accounts <fichier> --api http://127.0.0.1:8000 --exports`.
API locale lancée **comme en production** (`uvicorn --workers 2`, pool SQLAlchemy par défaut), trois sociétés
DEMO (sessions AUDITOR), 30 s par niveau. Chaque utilisateur simulé enchaîne **sans pause** des écrans tirés au
hasard (listes, positions GPS, tableaux de bord, coût complet occasionnel). Le client de charge tourne sur la même
machine (6 vCPU), et les tests d'un autre projet s'y exécutaient en même temps : chiffres plutôt pessimistes.

| Utilisateurs simultanés sans pause | 2 processus : req/s | p50 / p95 (ms) | 4 processus : req/s | p50 / p95 (ms) |
|---:|---:|---:|---:|---:|
| 1 | 15,6 | 54 / 176 | 12,8 | 60 / 226 |
| 5 | 41,4 | 95 / 346 | 49,6 | 80 / 293 |
| 10 | 44,8 | 179 / 539 | 62,7 | 123 / 422 |
| 20 | 44,1 | 410 / 866 | 66,6 | 245 / 693 |
| 40 | 41,3 | 859 / 1 721 | 63,5 | 544 / 1 258 |

Aucune erreur à aucun niveau. À 40 utilisateurs sans pause (2 processus), l'écran le plus lent reste le coût
complet (p50 1,8 s) ; les listes sont vers 0,7–1 s.

**Lecture**
- Le débit plafonne vers **44 requêtes/s avec 2 processus** dès 10 utilisateurs sans pause ; au-delà, les
  requêtes attendent leur tour et le temps de réponse croît en proportion (pas d'erreur, pas d'effondrement).
- Le facteur limitant est le **calcul Python de l'API** : chaque processus est à ≈ 85 % d'un cœur sous charge, alors
  que PostgreSQL reste léger (≈ 4 % par connexion). Sur une liste de 50 engins, le SQL compte ≈ 11 ms (5 requêtes,
  session et droits compris) sur ≈ 27 ms ; le reste est réparti dans le socle (ORM, validation, sérialisation),
  sans point chaud isolé.
- **Dimensionnement indicatif** : un utilisateur réel ouvre un écran toutes les 10 à 30 s environ ; 44 req/s
  correspondent donc à quelques centaines d'utilisateurs actifs en même temps avec 2 processus. À confirmer sur la
  machine de production, sans autre charge.
- **Levier** : `MF_API_WORKERS` (défaut 2) : 4 processus donnent ≈ +50 % de débit sur cette machine partagée. Chaque
  processus occupe ≈ 170 Mo en charge : au-delà de 3, relever la limite mémoire de l'API (768 Mo).

| Export CSV (pages de 200, plafond 5 000), demo-bauxite | Lignes | Pages | Durée totale | Page la plus lente |
|---|---:|---:|---:|---:|
| Pneus | 290 | 2 | 185 ms | 106 ms |
| Inspections HSE | 118 | 1 | 75 ms | 72 ms |
| Incidents HSE | 2 | 1 | 54 ms | 54 ms |
| Missions (référence : pas d'export à l'écran) | 2 878 | 15 | 1,9 s | 324 ms |

Les exports à l'écran restent sous 0,2 s à ce volume. Une liste de près de 3 000 lignes se parcourt en moins de
2 s ; les pages profondes restent sous 0,35 s.
