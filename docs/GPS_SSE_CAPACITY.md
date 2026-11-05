# GPS SSE — Limites de connexions (5 novembre 2026)

Cette tranche complète la PR #348 : elle **n'ajoute pas encore de bus événementiel**.

## Limite de capacité

- 32 connexions SSE simultanées au maximum **par processus API**.
- Une connexion dépassant ce plafond reçoit HTTP 429 et `Retry-After: 3` avant tout début de streaming.
- Le quota est restitué à la fin normale, après erreur ou à l'annulation du générateur.
- Le flux garde la vérification RLS des droits, la durée courte et le snapshot complet existants.
- Le client reste compatible avec le mode de secours REST à 15 secondes.

Cette protection est **locale à chaque worker**, pas globale à toutes les répliques : 4 workers peuvent donc accepter jusqu'à 128 connexions. Elle n'empêche pas une connexion unique de lire plusieurs centaines de véhicules ni ne remplace un contrôle de débit partagé.

## Mesures et exploitation avant pilote

- Exécuter le benchmark REST de `scripts/gps/benchmark_latest.py` sur une recette autorisée.
- Relever sur un environnement équipé la consommation CPU/PostgreSQL et les latences pour 1, 10 et 32 abonnés par worker.
- Vérifier les réponses 429, les reconnexions et le retour au polling avec des scénarios Playwright.
- Régler le nombre de workers et les limites d'entrée du reverse proxy ; maintenir l'authentification Bearer en en-tête.
- Préparer ensuite une architecture de publication d'événements (PostgreSQL LISTEN/NOTIFY avec lecture de rattrapage, ou broker selon l'exigence multi-workers) plutôt qu'une requête SQL toutes les 3 secondes par abonné.

## Limitations

Ce code ne prouve aucune capacité de production de 1000 véhicules : ni métriques sous charge, ni test matériel, ni garantie de consommation DB. Le score de référence 62/100 reste inchangé sans nouveau protocole d'audit.
