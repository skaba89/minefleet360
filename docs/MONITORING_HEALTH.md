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

## Détection des incidents récurrents

`infra/deploy/alert-state.py` exécute la sonde consolidée, conserve un compteur dans un fichier local (mode 0600) et produit les transitions `PENDING`, `ALERT`, `ALERT_ACTIVE`, `RECOVERED`, `OK`. Trois échecs consécutifs sont nécessaires par défaut avant une nouvelle alerte ; une réussite confirme le rétablissement. Une exécution concurrente est sérialisée par verrou de fichier.

```bash
MINEFLEET_BASE_URL=https://minefleet.example.org \
python3 infra/deploy/alert-state.py \
  --state-file /var/lib/minefleet-monitor/health-state.json --threshold 3
```

**Ce programme n'envoie aucune notification** : l'intégrer à un superviseur qui relève les événements `ALERT` et `RECOVERED` (sans afficher de secrets). L'exploitant doit installer le cron/systemd timer, configurer un canal d'alerte et tester un incident fictif. Ne pas placer le fichier d'état dans un répertoire accessible publiquement. Une instance dédiée de supervision est préférable pour éviter une panne commune avec l'application.

## Envoi d'une notification SMTP (adaptateur)

Le programme `infra/deploy/notify-alert-smtp.py` envoie un événement explicite `ALERT` ou `RECOVERED` avec SMTP STARTTLS. Il exige les variables `MF_ALERT_SMTP_HOST`, `MF_ALERT_SMTP_USERNAME`, `MF_ALERT_SMTP_PASSWORD`, `MF_ALERT_EMAIL_FROM`, `MF_ALERT_EMAIL_TO`, `MF_ALERT_INSTANCE` (et éventuellement `MF_ALERT_SMTP_PORT`, 587 par défaut). Conserver les identifiants hors du dépôt dans un gestionnaire de secrets ; privilégier une identité technique dédiée.

```bash
python3 infra/deploy/notify-alert-smtp.py ALERT
python3 infra/deploy/notify-alert-smtp.py RECOVERED
```

L'adaptateur ne transmet que des messages génériques et n'insère pas les diagnostics des sondes. Il ne fournit **ni ordonnanceur, ni couplage automatique avec alert-state.py, ni file de livraison persistante**. Une connexion SMTP acceptée ne garantit pas la réception. Avant tout pilote, installer un superviseur qui invoque l'adaptateur uniquement sur transition, gère les tentatives de livraison échouées sans perdre les alertes, et teste les destinataires et le rétablissement. Les variables d'environnement ne doivent pas être enregistrées dans les logs.

## Exécution intégrée avec reprise des notifications

`run-alert-monitor.py` relie `alert-state.py` à l'adaptateur SMTP et conserve les événements à envoyer dans une file JSON, sous verrou exclusif. Une panne SMTP conserve l'événement pour une prochaine exécution, et les événements sont délivrés dans l'ordre. Exemple pour une exécution périodique par systemd timer :

```bash
MINEFLEET_BASE_URL=https://minefleet.example.org \
python3 infra/deploy/run-alert-monitor.py \
  --state-dir /var/lib/minefleet-monitor --threshold 3
```

Les variables `MF_ALERT_SMTP_*` et `MF_ALERT_EMAIL_*` sont nécessaires pour envoyer des emails. Le répertoire d'état doit être réservé au compte technique de supervision (droits `0700`) ; les fichiers sont créés avec les droits `0600`. **Ne jamais exécuter deux ordonnanceurs différents sur le même état**. Tester une panne simulée et la reprise SMTP en staging avant d'activer les notifications opérationnelles.

La livraison est *au moins une fois* : une interruption après acceptation SMTP et avant la suppression de la file peut provoquer un doublon. Une interruption entre l'enregistrement d'une transition et sa mise en file peut aussi nécessiter une réconciliation manuelle des événements. Il n'y a pas encore de supervision externe, de preuves de réception effective des emails, ni de mécanisme automatique de résorption des erreurs persistantes.

## Journal d'alertes atomique (PR suivante à #207)

Une transition `ALERT` ou `RECOVERED` est désormais enregistrée **dans le même fichier d'état que la liste `pending_notifications`**, sous un même verrou et avant d'afficher l'événement. L'orchestrateur utilise directement cette liste pour l'envoi et n'a plus besoin d'un second enregistrement du message : une interruption entre les deux opérations ne peut donc plus faire disparaître l'alerte.

**Migration :** avant d'activer cette version sur un serveur où `pending-notifications.json` existe, arrêter le service de monitoring, sauvegarder les deux fichiers d'état et examiner les notifications encore présentes dans l'ancienne file. Les transférer ou les traiter manuellement avant de démarrer le nouveau script. Ne pas supprimer automatiquement une file contenant des messages non traités.

Le risque de doublon après acceptation SMTP demeure. L'écriture d'un fichier JSON en place reste vulnérable à une coupure système au milieu d'une écriture ; des tests de résistance sur la durabilité et une stratégie de récupération de fichier corrompu restent nécessaires.
