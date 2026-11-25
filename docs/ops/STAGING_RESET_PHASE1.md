# Staging reset — phase 1 (inventaire uniquement)

Issue: #532.

## Périmètre

La première phase fournit un inventaire **en lecture seule** des tables, clés étrangères, partitions, politiques RLS et comptes du staging. Elle ne fournit **aucune commande de nettoyage**. L'inventaire ne prouve ni le succès d'un reset ni le re-bootstrap de l'administrateur.

## Préconditions

- Uniquement sur le VPS MineFleet qui héberge le conteneur `minefleet-db-1`.
- `/opt/minefleet/infra/deploy/.env.prod` contient explicitement `MF_ENV=staging`.
- Un opérateur autorisé dispose d'un accès Docker local.
- Une sauvegarde actuelle a été restaurée avec succès via `infra/deploy/verify-restore.sh`.

## Utilisation

```bash
cd /home/ubuntu/minefleet360-audit
bash infra/deploy/staging-reset-inventory.sh > /home/ubuntu/minefleet-backups/staging-reset-inventory.txt
chmod 600 /home/ubuntu/minefleet-backups/staging-reset-inventory.txt
```

La sortie contient uniquement des métadonnées de structure, des compteurs et des contraintes. Elle peut néanmoins révéler les noms internes de tables et l'organisation de la base. Ne pas la publier sans revue.

`MF_DEPLOY_DIR` permet de définir un autre emplacement du fichier d'environnement staging. Le conteneur autorisé reste strictement `minefleet-db-1`.

## Étapes suivantes — NON IMPLÉMENTÉES

1. Auditer migrations, données de référence et clés étrangères pour construire une classification de suppression exhaustive.
2. Créer un reset explicitement réservé au staging, d'abord en dry-run, avec confirmation et garanties de récupération.
3. Tester effacement, migration, re-bootstrap, connexion et MFA sur une restauration isolée persistante, pas sur la base active.
4. Vérifier l'état des flux GPS et de la messagerie; planifier la fenêtre de maintenance et la reprise.
5. Exiger des preuves automatisées avant tout GO de suppression réelle.

**Interdits :** `docker compose down -v`, `docker volume rm`, `TRUNCATE ... CASCADE` global, modification d'une autre application, réinitialisation implicite du staging actif.

## Validation statique

```bash
bash -n infra/deploy/staging-reset-inventory.sh
```

La CI doit vérifier le script et ses gardes avant fusion. Ne pas prétendre que l'inventaire a été exécuté sur le VPS tant que l'opérateur ne fournit pas la sortie.
