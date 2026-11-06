# Vérification d'une restauration PostgreSQL — MineFleet 360

## Objectif
Le contrôle `pg_restore --list` du script `backup.sh` vérifie la lisibilité du catalogue, **pas** la capacité à restaurer les données. Le script `verify-restore.sh` effectue une restauration isolée, sans utiliser la base applicative en cours d'exploitation.

## Prérequis
- Linux avec Bash et Docker fonctionnel.
- Archive `pg_dump -Fc` produite par le script de sauvegarde ; conserver le fichier en dehors du dépôt.
- Espace disque suffisant pour une copie temporaire de la base. Le script peut être long pour les grandes archives.
- Images Docker PostGIS 16.3.4 disponibles ; l'hôte doit avoir accès à l'image avant exécution en mode déconnecté.

## Vérifier une archive sur une machine de recette

```bash
bash infra/deploy/verify-restore.sh /chemin/absolu/minefleet-20261031T120000Z.dump

# Optionnel : vérifier aussi une image backend déjà construite.
bash infra/deploy/verify-restore.sh /chemin/absolu/minefleet-20261031T120000Z.dump \
  --api-image minefleet-api:version-testee
```

Ce script :
1. refuse une archive absente ou vide ;
2. lance un conteneur temporaire `postgis/postgis:16-3.4`, sans réseau et sans volume PostgreSQL persistant ;
3. crée dans le conteneur jetable les rôles `mf_owner` et `mf_app` avec `NOLOGIN` et sans privilège de contournement RLS (les rôles de cluster ne sont pas contenus dans un dump de base) ;
4. restaure réellement l'archive avec ses propriétaires et ACL dans `minefleet_restore_check`, avec `--exit-on-error` ;
5. vérifie le nombre de tables et la présence d'`alembic_version` ;
6. vérifie que `tenant` appartient à `mf_owner`, que RLS est activée et forcée, qu'une politique cible `mf_app`, que ce rôle ne voit aucun tenant sans contexte et qu'il peut lire le tenant plateforme avec le contexte autorisé ;
7. avec `--api-image`, place PostgreSQL et l'image backend sur un réseau Docker interne sans port publié, active temporairement `mf_app` avec un secret aléatoire, démarre l'API avec un système de fichiers en lecture seule et vérifie `/api/v1/health` et `/api/v1/ready` ;
8. détruit les conteneurs, le réseau privé et les secrets éphémères en sortie, succès ou échec.

La restauration contient potentiellement des données sensibles **en clair dans le stockage temporaire du conteneur**. Exécuter exclusivement sur un hôte de confiance chiffré et sécurisé, jamais sur un poste partagé. N'utiliser de données réelles en recette que dans le cadre des autorisations et mesures de sécurité applicables.

## Vérifier une copie hors machine chiffrée

La configuration `offsite.env` n'est jamais exécutée comme du shell. Elle accepte uniquement les trois clés documentées, exige un remote rclone nommé, un chemin absolu de phrase secrète et une rétention de 1 à 3650 jours. Les fichiers de configuration et de phrase secrète doivent être réguliers, non symboliques et en mode `400` ou `600`.

Après une sauvegarde réussie, le coffre contient seulement :

- `minefleet-YYYYMMDDTHHMMSSZ.dump.gpg` ;
- `minefleet-YYYYMMDDTHHMMSSZ.dump.gpg.sha256`.

Le dump en clair n'est jamais envoyé. Pour effectuer l'aller-retour complet sur une machine isolée autorisée :

```bash
export MF_OFFSITE_CONFIG_FILE=/opt/minefleet/infra/deploy/offsite.env
export MF_OFFSITE_RESTORE_TMPDIR=/volume-chiffre/temp-restore
bash infra/deploy/verify-offsite-backup.sh \
  minefleet-20261106T070000Z.dump.gpg \
  --api-image ghcr.io/exemple/minefleet-api@sha256:DIGEST
```

Le script télécharge un nom canonique exact, vérifie le SHA-256 du chiffré, déchiffre dans un répertoire temporaire en mode privé, appelle `verify-restore.sh`, puis supprime le chiffré, le checksum et le dump temporaire. La sortie donne la durée observée de l'exercice, sans la transformer en engagement contractuel.

## Ce que ces contrôles ne prouvent pas
- Sans l'option `--api-image`, que le service API démarre. Avec cette option, le démarrage et la connexion DB sont vérifiés, mais pas les tâches planifiées, les parcours authentifiés ni les intégrations externes.
- Qu'un remote OVH/S3/SFTP opérationnel, ses identifiants, sa politique d'accès et sa rétention ont été configurés ou testés : la CI utilise un remote rclone local jetable.
- Que les objectifs RPO/RTO contractuels sont atteints.
- Qu'une restauration sur un nouveau VPS fonctionne, ni que les clés MFA/JWT sont disponibles.
- Que des migrations postérieures à la sauvegarde sont réconciliées.

## Prochaine étape P0
Sur un environnement **staging séparé**, restaurer une sauvegarde distante, exécuter un parcours authentifié avec un compte de recette, mesurer le temps d'exécution et documenter la date du dernier backup vérifié, le résultat, le RPO et le RTO. Ne jamais restaurer vers la base de production active.


## Vérification automatisée dans la CI

Le job backend de `.github/workflows/ci.yml` produit, avec le superutilisateur du service PostgreSQL éphémère, une archive custom de la base fictive `minefleet_test` après les migrations et tests. Il la transmet comme artefact synthétique à très courte rétention. Un job dépendant sur un runner GitHub Actions neuf chiffre l'archive avec GPG et une phrase aléatoire éphémère, la transfère par rclone dans un coffre local jetable, vérifie l'absence de dump clair dans ce coffre, télécharge le chiffré et son checksum, déchiffre, restaure, puis construit/démarre l'étage runtime du backend sur un réseau Docker interne sans port publié. Le job échoue si le transport, l'intégrité, le déchiffrement, la restauration complète, les propriétaires, les ACL, RLS, le démarrage de l'image API ou sa readiness DB échouent.

Cette vérification automatise un aller-retour PostgreSQL et cryptographique avec les données synthétiques de CI. Les secrets n'existent que dans les fichiers privés du runner jetable. Elle ne teste pas un fournisseur distant réel, la rotation/récupération des clés, la fréquence planifiée, les objectifs RPO/RTO, les secrets d'un hôte client ni une sauvegarde de staging ou production.
