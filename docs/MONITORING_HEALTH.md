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

## Fraîcheur des sauvegardes locales PostgreSQL

```bash
MF_BACKUP_MAX_AGE_HOURS=26 bash infra/deploy/probe-backup-freshness.sh
```

La sonde est en lecture seule : elle recherche les fichiers locaux non vides `backups/minefleet-*.dump` et contrôle l'horodatage de modification du plus récent. Valeur par défaut : 26 heures pour des sauvegardes quotidiennes, à adapter à l'ordonnancement. Codes de sortie : `0` fraîcheur conforme, `2` aucune archive valide ou archive trop ancienne, `3` erreur de configuration ou d'horloge.

**Limites :** un fichier récent peut être corrompu. La fraîcheur locale ne prouve ni copie hors site, ni déchiffrement, ni restauration. Exécuter périodiquement `verify-restore.sh` sur une machine de confiance et ajouter la supervision du transfert distant ; créer une alerte si la sonde retourne un code non nul. Ne jamais consigner le contenu des archives.

## Vue consolidée des contrôles P0

Depuis l'hôte de déploiement (avec droits Docker), lancer :

```bash
MINEFLEET_BASE_URL=https://minefleet.example.org bash infra/deploy/probe-all.sh
```

Le script `probe-all.sh` exécute trois contrôles **en lecture seule** : PostgreSQL, fraîcheur des sauvegardes locales et disponibilité HTTPS externe. Il fournit une ligne de statut par contrôle sans relayer les détails internes ou les secrets. Retour `0` si tous les contrôles sont verts, `2` si au moins un est critique, et `3` en cas de configuration manquante ou contrôle indéterminé. L'absence d'URL HTTPS est volontairement classée UNKNOWN, pas OK.

Cette consolidation ne configure ni planification ni notifications. Pour une exploitation pilote, intégrer le script au système de supervision (exécution avec identité technique à privilèges restreints), déclencher une alerte après plusieurs échecs consécutifs, et tester le canal d'escalade. L'accès au socket Docker reste hautement privilégié ; ne pas exposer ce script par une API web.
