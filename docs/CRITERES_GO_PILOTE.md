# MineFleet 360 — critères de sortie avant pilote minier

Ce document est une **liste de preuves à obtenir**, pas une attestation de conformité. Ne pas déployer en production à partir de la seule réussite de la CI.

## 1. Valorisation des stocks et coûts de maintenance (P0 métier)

État audité sur main au 2026-10-30 : `spare_part_balance` contient `on_hand` et `reserved` (Numeric 16,3), et `spare_part_movement` contient quantité, type et référence, **sans prix unitaire ni devise**. Un coût fiable ne peut donc pas être calculé à partir de ces seules tables.

- Faire valider par le métier : méthode de valorisation (CMP mobile, FIFO, prix standard), devise de référence, arrondis, taxes/frais, changements de prix, avoirs, dates d'effet.
- Ajouter une migration non destructive et une écriture atomique des coûts aux réceptions et consommations ; ne jamais recalculer rétroactivement un coût historique à partir d'un prix actuel.
- Relier chaque consommation à un OT par une clé explicite et contrôlée, plutôt que d'inférer un coût depuis une référence libre.
- Calculer le coût des pièces consommées par OT, puis ajouter main-d'œuvre et sous-traitance avec sources vérifiables.
- Tester stocks valorisés, retours, annulations, multi-devise et isolation tenant/site.

**Critère d'acceptation :** rapprochement entre valeur d'ouverture + entrées valorisées − sorties valorisées et valeur de clôture, avec écarts expliqués et tests reproductibles.

## 2. Charge et concurrence (P0 technique)

- Exécuter des tests sur un vrai PostgreSQL de recette, pas SQLite ni uniquement des mocks.
- Deux sorties concurrentes contre une disponibilité insuffisante : jamais de stock négatif ; une seule réussite si la quantité ne permet qu'une sortie.
- Consommation contre libération de la même réservation : une seule transition d'ACTIVE ; solde et ledger cohérents.
- Doublon de référence en course : une seule écriture métier.
- Tester les scopes tenant/site distincts et l'absence de données transverses.
- Définir avec l'exploitation des objectifs p95, erreurs, débit GPS, RPO/RTO et durée de charge. Publier l'environnement, la volumétrie et les résultats bruts.

**Critère d'acceptation :** invariants comptables et de stocks respectés sous concurrence, sans erreur serveur inexpliquée.

## 3. Préproduction et supervision (P0 exploitation)

La configuration existante est `infra/deploy/docker-compose.prod.yml` et le script de sauvegarde est `infra/deploy/backup.sh`. Leur présence ne prouve pas qu'une restauration fonctionne.

Exécution du contrôle statique, **sans démarrer de conteneurs** :

```bash
bash infra/deploy/check-preproduction.sh
```

Vérification HTTPS d'une URL de **recette** uniquement :

```bash
MINEFLEET_STAGING_URL=https://staging.exemple.tld bash infra/deploy/check-preproduction.sh infra/deploy/docker-compose.prod.yml --live
```

Le script refuse une URL HTTP et ne désactive pas la validation TLS. Il ne lit ni n'affiche les secrets réels.

Avant GO pilote :

- Environnement staging isolé des données réelles, migration `alembic upgrade head` exécutée avec compte approprié.
- Sauvegarde externalisée et **restauration testée** sur un environnement séparé.
- Métriques de disponibilité API, latence, erreurs 5xx, saturation PostgreSQL, espace disque, files d'événements et fraîcheur GPS ; seuils d'alerte et responsable d'astreinte.
- Vérification TLS, rotation des secrets, droits minimaux, journaux sans données sensibles, rétention, export des traces.
- Simulation d'incident avec reprise applicative et base, puis procédure de rollback documentée.
- Rapport GO / NO-GO signé incluant les résultats réels des tests de concurrence et métier.

**Critère d'acceptation :** preuves horodatées et reproductibles de restauration, alerting testé et retour arrière. Un échec bloque le GO.
