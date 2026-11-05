# GPS événementiel — vérification PostgreSQL réelle

Ce lot complète la PR #353 par des tests d'intégration, sans modifier les routes ni le fonctionnement du produit.

## Scénarios contrôlés

- `pg_notify` dans une transaction non validée : **aucun message** reçu avant COMMIT ;
- après COMMIT : réception d'un unique message sur le canal `minefleet_gps_positions` avec l'UUID de société uniquement ;
- après ROLLBACK : **aucun message** ;
- deux sociétés abonnées au même worker : signal envoyé à A uniquement, aucune notification à B ;
- connexion LISTEN réelle ouverte puis fermée dans les tests, pas de service réseau externe.

## Sécurité et environnement

Les tests exigent `MF_ENV=test` et une base dont le nom se termine en `_test`. Ils utilisent la base PostgreSQL éphémère initialisée par GitHub Actions. Ils ne créent aucune position GPS et n'exposent aucune coordonnée ni information de véhicule.

Les propriétés RLS, la révocation de session et les restrictions de site restent vérifiées par les tests d'autorisation existants. Cette PR ne démontre pas la latence ni la résilience avec plusieurs serveurs physiques ; ce sont les étapes suivantes sur une recette dédiée, avec mesures CPU, p95 et comportement sous coupure réseau.

Pour exécuter avec la suite existante : `pytest tests/test_gps_postgres_notifications.py -q` depuis `backend/`, après provisionnement de `minefleet_test` par les scripts du dépôt.
