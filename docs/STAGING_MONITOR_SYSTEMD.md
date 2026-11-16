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

## Contrôle du répertoire des sauvegardes

Définir `MF_BACKUP_DIR` comme un chemin **absolu** vers les sauvegardes créées par `backup.sh` (dans l'exemple : `/opt/minefleet/infra/deploy/backups`). Vérifier la présence et la lecture par le compte `minefleet-monitor` sans lui octroyer un accès en écriture. La sonde retourne `UNKNOWN` si le répertoire est inaccessible et `CRITICAL` si aucune archive non vide et récente n'existe. Avant activation du timer, exécuter manuellement la sonde sous le compte de service puis contrôler les résultats. La lecture des métadonnées ne suffit pas à démontrer qu'une archive peut être restaurée.

### Procédure retenue (2026-11-16, sans paquet `acl`)

`backup.sh` ne remet plus le répertoire en 700 à chaque passage : il le crée en 700, puis sur un répertoire
existant retire seulement l'accès « autres » et l'écriture de groupe (les archives restent en 600, le groupe
voit les métadonnées, jamais le contenu). Accorder la lecture/traversée au compte de supervision :

```bash
sudo chgrp minefleet-monitor /opt/minefleet/infra/deploy/backups
sudo chmod 750 /opt/minefleet/infra/deploy/backups
sudo -u minefleet-monitor env MF_BACKUP_DIR=/opt/minefleet/infra/deploy/backups \
  bash /opt/minefleet/infra/deploy/probe-backup-freshness.sh   # attendu : OK
```

### Marqueurs de réussite des tâches planifiées

Chaque unité de tâche écrit `/var/lib/minefleet-jobs/<unité>.success` via `ExecStartPost` (exécuté
seulement si la tâche a réussi). Après un redémarrage, systemd efface `ExecMainExitTimestamp` et remet
`Result` à `success` ; `probe-scheduled-jobs.sh` juge alors la fraîcheur sur ce marqueur. Une tâche en échec
n'actualise plus son marqueur : il vieillit et la sonde passe en CRITICAL à l'échéance.
