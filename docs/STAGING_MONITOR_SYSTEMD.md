# Installer la supervision systemd — recette uniquement

Cette livraison fournit **des modèles**, sans installation ou activation automatique sur un serveur. Le processus s'exécute toutes les 5 minutes avec un état local durable et un compte de service non privilégié.

## Prérequis bloquants

Le contrôle `probe-database.sh` existant invoque `docker compose exec`. **Un compte autorisé à utiliser le socket Docker dispose de privilèges proches de root.** Pour cette raison, ne pas ajouter `minefleet-monitor` au groupe `docker` ni accorder des droits sur `/var/run/docker.sock` uniquement pour faire fonctionner la sonde. L'installation reste **bloquée** tant que ce contrôle n'est pas remplacé par une sonde SQL utilisant un accès à privilèges minimaux, ou par un superviseur dédié avec configuration validée.

Le compte de service devra aussi avoir lecture du répertoire local de sauvegarde, sans accès en écriture à ces fichiers. Ne pas contourner cette limite avec des permissions trop larges.

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
