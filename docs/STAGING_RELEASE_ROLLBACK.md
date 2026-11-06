# Release et rollback contrôlés de la recette

## Portée

Cette procédure prépare un déploiement reproductible de **staging uniquement**. Elle ne donne aucune autorisation de production et ne prouve pas qu'une répétition réelle a été exécutée. Le script refuse tout manifeste dont `environment` diffère de `staging`.

Le mécanisme traite le rollback applicatif : API et interface reviennent aux images précédentes, tandis que le schéma PostgreSQL reste à la révision migrée. Aucun `alembic downgrade` n'est exécuté. Chaque migration déployée doit donc avoir été revue comme compatible avec la version applicative de rollback.

## Construction des images

Construire l'API et l'interface depuis le même commit Git complet, puis publier les images dans un registre privé ou contrôlé :

```bash
release_commit="$(git rev-parse HEAD)"
docker build --target runtime --build-arg MF_RELEASE_COMMIT="$release_commit" \
  --build-arg MF_MIGRATION_HEAD="0063" \
  -t "REGISTRY/minefleet-api:$release_commit" backend
docker build --target runtime --build-arg MF_RELEASE_COMMIT="$release_commit" \
  -t "REGISTRY/minefleet-web:$release_commit" frontend
```

Après publication, récupérer les digests attribués par le registre. Le manifeste accepte uniquement `registry/repository@sha256:<digest>`, jamais `latest`, `main` ou un tag seul. Le label OCI `org.opencontainers.image.revision` de chaque image doit correspondre au commit du manifeste. L'image API porte aussi `com.minefleet.alembic-head`, qui doit correspondre à `migration_head`. Le script vérifie ces labels après le téléchargement.

La signature d'image, la provenance SLSA et la publication automatique ne sont pas encore livrées par ce lot.

## Manifeste

Copier `infra/deploy/release-manifest.example.json` hors du dépôt, puis remplacer toutes les valeurs d'exemple. Le manifeste contient :

- le commit et la tête Alembic attendus ;
- les digests API/web de la nouvelle version ;
- les digests API/web de rollback ;
- la variante `edge` ou `standalone` ;
- la stratégie obligatoire `application-only-forward-schema`.

Il ne doit contenir aucun mot de passe, token, URL avec identifiants, coordonnée GPS ou donnée client.

Validation locale en lecture seule :

```bash
python3 infra/deploy/release_manifest.py validate /chemin/absolu/release.json
```

## Plan sans mutation

Sur l'hôte staging, `infra/deploy/.env.prod` doit être un fichier régulier non symbolique, en mode `600` ou `400`, avec `MF_ENV=staging` et les secrets existants.

```bash
cd infra/deploy
./staging-release.sh plan /chemin/absolu/release.json
```

Le mode `plan` valide le manifeste et la configuration Compose. Il ne télécharge aucune image, ne démarre aucun conteneur, ne crée aucune sauvegarde et n'exécute aucune migration.

## Application sur staging

Après revue de la CI du commit, des migrations, du manifeste et de la compatibilité du rollback :

```bash
export MINEFLEET_STAGING_URL="https://recette.example.com"
export MF_STAGING_CHANGE_APPROVAL="apply:<commit-complet-du-manifeste>"
./staging-release.sh apply /chemin/absolu/release.json
unset MF_STAGING_CHANGE_APPROVAL
```

Le script :

1. vérifie que la recette répond avant intervention ;
2. crée et contrôle une nouvelle sauvegarde PostgreSQL locale ;
3. télécharge les images par digest et vérifie leur label de commit ;
4. exécute `alembic upgrade head` avec l'image API ciblée ;
5. vérifie la concordance entre le schéma et l'image ;
6. recrée API/web sans build local ;
7. vérifie `/`, `/api/v1/health` et `/api/v1/ready` en HTTPS ;
8. conserve un reçu sans secret dans `infra/deploy/release-state/current.json`.

En cas d'échec du smoke final, le script tente immédiatement le rollback applicatif déclaré dans le manifeste. La base n'est jamais rétrogradée.

## Rollback explicite

```bash
export MINEFLEET_STAGING_URL="https://recette.example.com"
export MF_STAGING_CHANGE_APPROVAL="rollback:<commit-cible-du-manifeste>"
./staging-release.sh rollback /chemin/absolu/release.json
unset MF_STAGING_CHANGE_APPROVAL
```

Le rollback télécharge et vérifie les anciennes images, recrée uniquement API/web et répète les sondes HTTPS. Il ne touche ni aux volumes, ni à PostgreSQL, ni aux migrations.

## Preuves à conserver pour valider R2

- manifeste utilisé et digests du registre ;
- SHA des workflows verts ;
- heure de début/fin et durée d'indisponibilité observée ;
- tête Alembic avant/après ;
- résultat de la sauvegarde et de la restauration séparée ;
- résultat des sondes avant déploiement, après déploiement et après rollback ;
- reçu de staging et compte rendu d'incident si une étape a échoué.

Tant que la séquence `apply → vérifications → rollback → vérifications` n'a pas été exécutée sur un staging isolé, R2 reste **non validé en recette** et le score industriel ne doit pas augmenter.
