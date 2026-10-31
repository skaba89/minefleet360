# Garde de migration de la recette — lecture seule

Le contrôle HTTPS `/api/v1/ready` atteste une connexion SQL, mais ne garantit pas que le schéma PostgreSQL correspond au code actuellement déployé.

Depuis l'hôte de **recette**, avec la configuration Compose et les secrets staging présents dans `infra/deploy/.env.prod` :

```bash
cd infra/deploy
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  --profile ops run --rm --no-deps migrate python -m app.core.check_schema_revision
```

Le conteneur ponctuel utilise le compte `mf_owner`, nécessaire pour lire l'état de migration. Il ne déclenche **aucune migration** ; il interroge seulement `alembic_version` et compare les révisions obtenues aux têtes Alembic présentes dans l'image. Exit code `0` : toutes les têtes concordent ; exit code `2` : divergence ou connexion impossible.

**Important :** toujours exécuter ce contrôle après le déploiement de l'image ciblée. Une image locale ancienne peut déclarer une tête Alembic obsolète. Ne pas exécuter `alembic upgrade` à titre de vérification. Ne pas exposer les identifiants `mf_owner` au service HTTP ou au compte `minefleet-monitor`.

Une correspondance des révisions n'est pas un audit des contraintes ni une preuve de restauration et ne dispense pas des tests de sauvegarde ou du contrôle des permissions RLS. L'exécution réelle sur staging n'a pas été effectuée dans cette PR.
