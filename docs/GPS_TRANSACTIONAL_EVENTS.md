# GPS — signal événementiel transactionnel (première étape)

## Ce que livre cette PR

- Chaque **nouvelle** position acceptée venant du téléphone ou d'un traceur inscrit `pg_notify('minefleet_gps_positions', tenant_id)` dans **la transaction d'ingestion**.
- PostgreSQL émet cette notification **au commit uniquement** ; un rollback ne délivre rien. Une télémétrie rejetée ou dupliquée ne notifie pas.
- Le payload est seulement l'UUID de la société ; **jamais** la latitude, la longitude, l'identifiant du véhicule, le numéro de téléphone ou un jeton.
- Le producteur n'ouvre ni connexion de longue durée ni transaction supplémentaire ; les droits des API et la transaction existante restent inchangés.

## Limitations explicites

Le routeur SSE continue à lire un snapshot sous RLS toutes les 3 secondes. **Aucun listener n'est encore branché** dans cette PR, donc aucune réduction mesurée des requêtes SQL, ni amélioration de latence, n'est revendiquée.

`LISTEN/NOTIFY` est un signal éphémère, **pas une file durable** : une reconnexion ne rejoue pas les messages perdus. Les notifications peuvent être regroupées et elles ne remplacent pas une lecture SQL authentifiée. Le prochain lecteur multi-workers devra :

1. ouvrir une connexion PostgreSQL distincte du pool de sessions RLS et maintenir `LISTEN minefleet_gps_positions` avec gestion de la reconnexion ;
2. utiliser le payload uniquement comme **indication** de rafraîchissement : la société est revalidée depuis le jeton, les sites depuis les attributions et toutes les positions sont rechargées sous RLS ;
3. utiliser un snapshot initial complet et un intervalle de revalidation périodique (révocation de session et nouveaux droits), indépendants des notifications ;
4. gérer les notifications reçues pendant le snapshot initial, les coupures de listener, les lots d'événements et les délais de proxy ;
5. tester plusieurs tenants, plusieurs workers, le rollback, les doublons, les transactions longues et le trafic soutenu avant une bascule ;
6. conserver le repli REST côté navigateur et limiter les connexions simultanées par worker.

## Contrôles

- Tests unitaires du contrat de notification sans contenu GPS ;
- CI backend : Ruff, Mypy, Pytest et migrations ;
- CI frontend, Playwright et isolation multi-tenant inchangés ;
- scanners de sécurité Bandit et Gitleaks.

La PR ne réalise **aucune migration SQL**, n'introduit **aucun message broker externe** et n'exécute pas de tests de charge sur la production.
