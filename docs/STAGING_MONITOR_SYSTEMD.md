# Installer la supervision systemd — recette uniquement

Cette livraison fournit **des modèles**, sans installation ou activation automatique sur un serveur. Le processus s'exécute toutes les 5 minutes avec un état local durable et un compte de service non privilégié.

## Prérequis bloquants

La sonde PostgreSQL utilise maintenant `GET /api/v1/ready` sur l'API HTTPS ; la requête SQL `SELECT 1` est exécutée côté serveur avec le rôle applicatif restreint. Le compte `minefleet-monitor` **ne doit jamais** être membre du groupe Docker et n'a besoin d'aucun identifiant PostgreSQL.

Le compte de service doit pouvoir lire les métadonnées du répertoire de sauvegardes, sans modification possible. Ce droit de lecture reste à configurer et vérifier sur staging. La sonde readiness teste la connexion SQL mais ne prouve ni les migrations courantes ni l'isolation multi-tenant. Protéger l'endpoint par les mêmes contrôles de trafic et de disponibilité que l'API.

## Fichiers fournis

- `infra/deploy/systemd/minefleet-monitor.service` : service oneshot, identité dédiée, restrictions système, état dans `/var/lib/minefleet-monitor`.
- `infra/deploy/systemd/minefleet-monitor.timer` : exécution toutes les 5 minutes, avec faible délai aléatoire.
- `infra/deploy/systemd/monitor.env.example` : configuration d'exemple sans secrets réels.

## Procédure une fois les prérequis satisfaits

Sur **un serveur de staging**, après revue de sécurité des accès :

1. Créer l'utilisateur système `minefleet-monitor` sans shell interactif.
2. Installer les deux unités sous `/etc/systemd/system` et la configuration privée sous `/etc/minefleet/monitor.env` (propriétaire root, mode 0600).
3. Valider les unités avec `systemd-analyze verify` et exécuter manuellement le service en recette.
4. Vérifier les résultats via `systemctl status minefleet-monitor.service` et `journalctl -u minefleet-monitor.service` sans afficher de secrets.
5. Simuler des échecs de sondes et SMTP avec valeurs fictives, puis vérifier `ALERT`, `RECOVERED`, la persistance et la réception de notifications.
6. Activer le timer uniquement après validation du fonctionnement et des droits : `sudo systemctl enable --now minefleet-monitor.timer`.

**Attention :** systemd EnvironmentFile expose potentiellement les variables aux processus dotés de privilèges suffisants ; les variables d'environnement ne constituent pas un coffre à secrets. Prévoir une rotation SMTP, des destinataires de test et le traitement des incidents de fuite. Les erreurs d'une sonde ne doivent pas interrompre l'exploitation de l'API.

Aucune de ces commandes n'a été lancée sur un serveur réel dans cette PR.
