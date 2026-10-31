# Supervision HTTP — MineFleet 360

## Contrôle passif de l'application

Un endpoint `GET /api/v1/health` existe déjà. Le script `infra/deploy/probe-health.sh` effectue un contrôle HTTPS en lecture seule. Il exige HTTP 200, ne suit pas les redirections, et n'enregistre ni corps de réponse ni jeton. Un résultat non nul doit être traité comme une alerte par le système de supervision.

```bash
MINEFLEET_BASE_URL=https://minefleet.example.org bash infra/deploy/probe-health.sh
```

Codes de sortie : `0` = OK ; `2` = critique ou configuration invalide ; `3` = prérequis absent. Prévoir un contrôle à la minute depuis **un hôte externe** et configurer au minimum une alerte après trois échecs consécutifs, puis une notification de rétablissement. Le système de notification et ses destinataires restent à configurer par l'exploitant. Éviter d'alerter sur un seul échec réseau isolé.

## Limites et prochaines vérifications

La réponse HTTP de `/health` est une sonde de disponibilité **de l'API**, pas une preuve que PostgreSQL fonctionne, que les migrations sont courantes ou que le service respecte un SLO. Ajouter une sonde de préparation vérifiant la base avec un accès non privilégié, puis superviser les sauvegardes, la réplication externe, la saturation disque, l'expiration TLS, les erreurs 5xx et les délais p95/p99. Aucun mot de passe ou URL contenant un token ne doit figurer dans les logs de monitoring. Un essai de panne simulée et de notification est requis avant le pilote.

## Contrôle PostgreSQL depuis l'hôte Docker

```bash
bash infra/deploy/probe-database.sh
```

La sonde vérifie d'abord `pg_isready`, puis un véritable `SELECT 1` sur la base `minefleet`. Elle utilise le conteneur Docker local, sans publier de port et sans afficher de secret. Exécuter avec les droits Docker appropriés, uniquement sur l'hôte de déploiement : **l'accès au socket Docker donne des privilèges élevés**. L'absence de `.env.prod` ou des prérequis produit le code `3`, une indisponibilité SQL le code `2`, un succès le code `0`.

Cette sonde ne vérifie pas la fraîcheur de la sauvegarde, les permissions de l'utilisateur applicatif `mf_app`, les migrations, ni la performance sous charge. Pour l'alerte de disponibilité, corréler la sonde externe HTTP avec la sonde SQL interne : API OK + DB KO doit être traité comme un incident critique de base, tandis que HTTP KO + DB OK oriente vers le réseau, le proxy ou l'API.
