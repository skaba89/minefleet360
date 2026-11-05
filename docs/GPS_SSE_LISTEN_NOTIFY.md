# GPS SSE — abonnement transactionnel inter-workers

## Livraison

La PR #352 émet déjà une notification `minefleet_gps_positions` dans la transaction d'ingestion des traceurs et téléphones. Cette tranche ajoute un **abonné par processus FastAPI** :

- une connexion PostgreSQL spécifique `LISTEN`, en autocommit, distincte des sessions RLS ;
- une file bornée (1 réveil maximum) par client, filtrée par UUID de société ;
- un snapshot complet immédiatement après l'abonnement, et à chaque notification de la société concernée ;
- une relecture au maximum toutes les 15 secondes même sans notification, indispensable pour la révocation d'autorisations et les notifications perdues ;
- fermeture du listener lorsque le dernier abonné se déconnecte ;
- redémarrage après perte de connexion DB, avec réveil de tous les abonnés pour rattrapage ;
- délai progressif de reconnexion PostgreSQL (2, 4, 8, 16, puis 30 secondes maximum), remis à zéro après un LISTEN réussi ;
- aucune coordonnée, vitesse, identifiant de véhicule ni jeton conservé dans le bus.

## Sécurité

Le UUID reçu d'un NOTIFY **ne donne jamais accès aux données**. Chaque relecture du snapshot réexécute les validations d'identité, de session, du tenant, du site et des permissions puis la requête de positions sous RLS. L'API renvoie `session-ended` lorsque les droits sont révoqués.

Les notifications `LISTEN/NOTIFY` ne sont **pas durables**. Au lancement du flux, un snapshot complet est envoyé. En cas de panne du listener, le repli périodique de 15 secondes conserve le fonctionnement, mais la fréquence maximale de rafraîchissement baisse. La durée d'un flux reste plafonnée à 60 secondes ; le navigateur reconnecte après fermeture normale.

## Vérifications nécessaires avant pilote

- CI Ruff/Mypy/Pytest, Vitest, Playwright, isolation multi-tenant, Bandit/Gitleaks ;
- tests d'intégration sur PostgreSQL réel : émission uniquement au COMMIT, rollback sans signal, plusieurs workers, reconnect listener et transfert de véhicules entre sites ;
- mesures avec `scripts/gps/benchmark_stream.py` : latence après ingestion, CPU, nombre de requêtes SQL pour 1/10/32 clients, taux de reconnexion et refus 429 ;
- supervision du listener, limites DB et proxy, et essais de coupures réseau réelles sur appareils.

**Ce n'est pas encore une garantie temps réel ni un SLA de latence mesuré.** Le mécanisme privilégie la sûreté des droits d'accès et le rattrapage à l'absence totale de polling.


## Vérification de résilience du listener (PR suivante)

Un test d'intégration simule un premier refus de connexion Psycopg, puis établit
une vraie connexion `LISTEN` à PostgreSQL de test et vérifie que la notification
suivant un `COMMIT` parvient au bon abonné. Un test unitaire vérifie les bornes
du backoff. Ces vérifications n'arrêtent pas réellement le serveur PostgreSQL et
ne constituent pas un exercice de panne réseau multi-machine.
