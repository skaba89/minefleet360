# Contrôle en lecture seule de la recette GPS MineFleet360

Objectif : comparer les conteneurs réellement actifs, leurs **labels de commit**, la
révision Alembic installée et les endpoints HTTPS à la branche `main`. Ce contrôle
n'applique **aucune migration**, ne tire aucune image et ne redémarre rien.

## Préconditions

- Exécution sur le VPS OVH disposant du dépôt, depuis n'importe quel répertoire.
- Docker Compose et accès à l'installation staging existante.
- `infra/deploy/.env.prod` contenant exactement `MF_ENV=staging`.
- Réseau Docker `edge` et configuration correspondant à l'installation
  actuelle. Si le staging utilise une configuration différente, adapter la
  procédure après inspection, plutôt que forcer un redéploiement.

## Commandes

```bash
cd /home/ubuntu/minefleet360
git fetch origin main
# Ne pas exécuter un script non encore fusionné depuis main.
# Après fusion de la PR de cet outil, mettre à jour une copie du dépôt
# de travail sans écraser les modifications locales.
git status --short
git rev-parse HEAD
MF_EXPECTED_MAIN_SHA="$(git rev-parse origin/main)" \
  MINEFLEET_STAGING_URL="https://minefleet.51-75-248-4.sslip.io" \
  bash infra/deploy/inspect-staging-gps.sh
```

Les commandes supposent que le dépôt local contient déjà le script : le
`git fetch` seul ne le place pas dans le répertoire de travail. Après fusion,
mettre le script à disposition dans une copie propre de `main` ou appliquer
la procédure de synchronisation autorisée par l'exploitant. **Ne pas faire
`git reset --hard` ou un `pull` automatique sur le répertoire VPS.**

## Interprétation

- `git revision` du conteneur **n'est pas** `git rev-parse HEAD` :
  l'image peut être plus ancienne que le dépôt. Un label absent signifie
  version non attestée (ne pas supposer une correspondance).
- `migration_head_image` est une étiquette d'image ; la ligne
  `Révision(s) en base` est une lecture SQL séparée. Pour ce lot,
  la tête attendue dans le dépôt est `0077`.
- Si la base n'est pas accessible, l'outil le signale : **ne pas** la migrer
  automatiquement pour éliminer l'avertissement.
- HTTP 200 sur les trois routes de santé et le sprite ne prouve ni
  la présence de positions GPS actualisées ni une recette mobile physique.
- Comparer les révisions des conteneurs API et web avec le commit GitHub
  de référence avant d'envisager une mise à niveau. Les migrations sont
  uniquement appliquées via le processus signé et approuvé, avec sauvegarde
  et compatibilité du rollback prouvées.
- Le script n'écrit pas de fichier de rapport : collecter la sortie
  manuellement après revue, sans données personnelles ni secrets.

## Bloquants avant tout déploiement

1. CI verte sur la révision cible.
2. Images API/web signées et immuables du même commit, labels vérifiés.
3. Étude de compatibilité de la migration 0077 avec les anciennes images
   si un rollback applicatif sans downgrade est envisagé.
4. Sauvegarde et restauration isolée prouvées.
5. Compte rendu du plan `staging-release.sh plan`, puis validation humaine
   explicite de la mise en recette.

Se référer à `docs/STAGING_RELEASE_ROLLBACK.md` pour la procédure
existante. **Ne jamais assimiler cet inventaire à un GO production.**
