# GPS push — tranche 0 : référence REST mesurable

## État du 5 novembre 2026

Base `main@d5e563858ab371b960f4906e9fdb28e10d7c2a26`, après fusion #346.
La page `LiveFleetPage.tsx` actualise `/vehicles/gps/latest` toutes les **15 secondes**.
La lecture emploie `Require("fleet.vehicle.read")`, une session PostgreSQL sous contexte RLS,
et un filtre de site. Le jeton d'accès frontend est en mémoire (pas dans une URL).
**Le push SSE/WebSocket n'est pas encore livré par cette tranche.**

## Livré dans cette PR

- `scripts/gps/benchmark_latest.py` : mesure de latence HTTP p50/p95/max avec taille
  des réponses et nombre d'échecs, sans exporter coordonnées ou identifiants.
- `scripts/gps/test_benchmark_latest.py` : tests isolés (sans réseau).
- `.github/workflows/gps-benchmark-tests.yml` : validation Python automatisée.

### Commande (recette uniquement)

```bash
export MF_GPS_BENCH_URL=https://recette.exemple.org
export MF_GPS_BENCH_TOKEN='<jeton court de lecture GPS>'
python scripts/gps/benchmark_latest.py --samples 40 --interval 2
python -m unittest discover -s scripts/gps -p 'test_*.py' -v
```

Ne jamais enregistrer les variables d'environnement contenant le jeton dans une PR,
une capture d'écran ni un rapport. Utiliser un compte limité à la lecture du site de
recette. Le script refuse HTTP non chiffré hors localhost. Ne pas lancer contre la
production sans fenêtre de test autorisée.

**Limites :** mesure de la seule latence `GET`; pas de latence ingestion→navigateur,
ni charge multi-clients, ni streaming, ni preuve de performance de bout en bout.
L'âge des mesures depuis `recorded_at` dépend de la synchronisation des horloges ;
le rapport n'utilise que le temps HTTP pour ses percentiles.

## Décision d'architecture à valider avant le code SSE

1. Comparer SSE (sens serveur→navigateur) à WebSocket (bidirectionnel non requis
   pour les lectures) avec la politique de proxy, authentification et contraintes
   du monolithe. SSE est le candidat par défaut, pas une validation définitive.
2. Un EventSource natif ne permet pas de passer un `Authorization: Bearer` ;
   **ne jamais mettre le jeton dans une URL**. Étudier un fetch de streaming
   authentifié par le client existant ou un mécanisme de cookie approprié avec
   protections CSRF, CORS et renouvellement de session.
3. Revalider l'autorisation et l'état de session régulièrement pendant une
   connexion longue ; les accès révoqués ne doivent pas continuer à recevoir
   des positions. Filtrer au niveau SQL et RLS, jamais seulement côté navigateur.
4. Ne pas laisser une transaction DB ouverte pendant une attente SSE.
   Prévoir une nouvelle session courte et un contexte tenant correct par lecture.
5. Définir la reprise avec curseur monotone ou un snapshot initial complet
   lorsqu'une reconnexion crée un trou : ne pas promettre un replay d'événements
   non stockés. Distinguer état actuel et événements historiques.
6. Limiter connexions, débit, taille des événements et nombres de véhicules ;
   heartbeats, déconnexion et backpressure ; mesurer les coûts CPU/DB.
7. Prévoir un repli polling 15 s en cas d'indisponibilité du streaming.
8. Tester deux sociétés, sites restreints, rôle sans droit, révocation de
   session, changement de site, rotation du jeton, déconnexion, reconnexion,
   faible réseau, plusieurs workers et surcharge.
9. Mesurer ingestion→affichage avec horloges et identifiants de corrélation
   sans publier les coordonnées personnelles.

## Conditions d'acceptation de la prochaine PR

- Nouveau flux authentifié, tenant/site-scope, sans jeton dans l'URL.
- Snapshot initial + mises à jour, ancien signal signalé honnêtement.
- Reconnexion et fallback testés ; aucune perte silencieuse déclarée.
- Résultats mesurés contre la référence REST et sous charge.
- Ruff, mypy, pytest, Vitest, build, tests d'isolation et E2E pertinents verts.
- Aucune fusion sans validation humaine.

## Score

Score initial de maturité 62/100, inchangé : le benchmark seul ne démontre
aucun gain de fonctionnalité commerciale. Recalcul après tests et preuves.
