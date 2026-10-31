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
```

Ce script :
1. refuse une archive absente ou vide ;
2. lance un conteneur temporaire `postgis/postgis:16-3.4`, sans réseau et sans volume PostgreSQL persistant ;
3. restaure réellement l'archive dans la base temporaire `minefleet_restore_check` avec `--exit-on-error` ;
4. vérifie qu'au moins dix tables applicatives sont présentes et que `alembic_version` existe ;
5. détruit le conteneur temporaire en sortie, succès ou échec.

La restauration contient potentiellement des données sensibles **en clair dans le stockage temporaire du conteneur**. Exécuter exclusivement sur un hôte de confiance chiffré et sécurisé, jamais sur un poste partagé. N'utiliser de données réelles en recette que dans le cadre des autorisations et mesures de sécurité applicables.

## Ce que ce contrôle ne prouve pas
- Que le service API démarre avec les droits RLS et les secrets corrects.
- Que les sauvegardes distantes sont déchiffrables (décrypter dans un répertoire temporaire sécurisé puis utiliser le script).
- Que les objectifs RPO/RTO contractuels sont atteints.
- Qu'une restauration sur un nouveau VPS fonctionne, ni que les clés MFA/JWT sont disponibles.
- Que des migrations postérieures à la sauvegarde sont réconciliées.

## Prochaine étape P0
Sur un environnement **staging séparé**, mesurer le temps d'exécution, tester la restauration et le démarrage API avec un compte de recette, documenter la date du dernier backup vérifié, le résultat, le RPO et le RTO. Ne jamais restaurer vers la base de production active.
