# GPS — Validation du fan-out entre plusieurs workers

Cette tranche complète les tests transactionnels de la PR #354 : elle **simule deux workers indépendants** en lançant deux instances `GpsNotificationHub`, chacune disposant de sa connexion `LISTEN` à une base PostgreSQL réelle de test.

## Scénarios de non-régression

1. Deux workers abonnés à la même société sont tous deux réveillés après un COMMIT.
2. Un abonné d'une autre société, hébergé sur l'un de ces workers, n'est pas réveillé.
3. Un ROLLBACK ne réveille aucun worker.
4. Plusieurs `pg_notify` identiques dans une transaction n'imposent pas de réceptions non bornées ; chaque abonnement garde sa file de taille 1.
5. Les connexions et tâches de listener sont fermées après la désinscription.

La suite fonctionne sur `MF_ENV=test` et `*_test` uniquement. Aucun traceur réel, aucun service de production, aucune coordonnée GPS ni jeton d'accès ne sont utilisés.

**Limite :** deux hubs dans le même processus vérifient le protocole de propagation entre deux connexions indépendantes, pas le comportement de deux processus OS ou de plusieurs machines. Ce dernier point, ainsi que le p95 entre ingestion et affichage, doit être mesuré sur un environnement de recette dédié avant d'annoncer une capacité de production.

Commande ciblée, une fois la base de test préparée : `cd backend && pytest tests/test_gps_postgres_notifications.py -q`.
