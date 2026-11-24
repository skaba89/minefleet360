# Release et rollback contrôlés de la recette

## Portée

Procédure de déploiement reproductible de **staging uniquement**. Elle ne donne aucune autorisation de production. Le script refuse tout manifeste dont `environment` diffère de `staging` et tout fichier de secrets qui ne contient pas exactement `MF_ENV=staging`.

Le rollback est **applicatif** : API et interface reviennent à des images antérieures, le schéma PostgreSQL reste à la révision migrée. Aucun `alembic downgrade` n'est jamais exécuté. Chaque migration déployée doit donc avoir été revue comme compatible avec l'API de rollback ; cette revue est référencée dans le manifeste (`schema_compatibility_review`).

## Invariants garantis par `infra/deploy/staging-release.sh`

| Invariant | Mécanisme | Test |
|---|---|---|
| PostgreSQL jamais démarré, arrêté, recréé ni rétrogradé | aucun `up db`, `down`, `stop`, `rm`, `prune` ; API/web remplacées par `up -d --no-deps --no-build --pull never api web` ; identité du conteneur (`Id` + `StartedAt`) comparée avant/après | `test_apply_backs_up_migrates_and_replaces_only_apps`, `test_recreated_postgres_is_detected`, `test_script_contains_no_destructive_database_command` |
| Base saine et volume attendu avant toute action | conteneur `db` unique, `running` + `healthy`, données sur le volume nommé `minefleet_db-data` (surchargeable par `MF_EXPECTED_DB_VOLUME`) | `test_unhealthy_or_foreign_database_is_refused_before_backup` |
| Révision Alembic contrôlée | lecture seule de `alembic_version` avant/après ; `check_schema_revision` après migration ; une révision inconnue bloque | `test_rollback_refuses_unknown_database_revision` |
| Volume de messagerie, réseaux, ports, sécurité, PMTiles | `runtime_guard.py` compare la configuration Compose planifiée et les conteneurs recréés à ceux en service (montages, réseaux, ports publiés, `cap_drop`, `security_opt`, `read_only`, `tmpfs`) ; montage `/srv/basemap` obligatoirement en lecture seule ; liste des `*.pmtiles` identique avant/après | `test_planned_runtime_drift_is_refused`, `test_runtime_drift_after_replacement_is_detected`, `RuntimeGuardTests` |
| Sauvegarde avant intervention, sans suppression | `backup.sh` + `probe-backup-freshness.sh` (≤ 1 h) avant `apply` et avant tout rollback explicite ; `MF_BACKUP_SKIP_RETENTION=1` : aucune purge locale ni distante pendant une release | `test_release_never_deletes_existing_backups` |
| Provenance | Cosign + attestation SLSA v1 vérifiées pour **les quatre** images (cible et rollback) dès `plan`, identité limitée au workflow `release-images.yml` sur `main` ou un tag `v*` | `test_plan_is_read_only_and_verifies_every_signed_image`, `test_unsigned_rollback_image_blocks_the_release_before_any_mutation` |
| Vérification métier au-delà des sondes | `business-smoke.py` après chaque remplacement : SPA et assets, deux PMTiles (France, Guinée) en requête Range, connexion (MFA TOTP), lectures `me`, sites, véhicules, catégories, missions, géofences, alertes et positions GPS | `test_business_failure_triggers_rollback_to_distinct_api_and_web` |

## Images signées (chemin officiel)

Le workflow CI `release-images` (tag `v*.*.*` ou déclenchement manuel) publie `ghcr.io/skaba89/minefleet360/api` et `…/web`, avec provenance SLSA `mode=max`, SBOM, signature Cosign keyless et attestation SLSA v1 signée. Les labels `org.opencontainers.image.revision` et `com.minefleet.alembic-head` sont posés au build. Le manifeste officiel n'accepte **que** ces deux dépôts, par digest.

Le script exige `cosign` sur l'hôte pour `plan`, `apply` et `rollback` ; il n'existe aucune option pour contourner cette vérification.

## Manifeste officiel (`schema_version: 2`)

Copier `infra/deploy/release-manifest.example.json` hors du dépôt et remplacer toutes les valeurs. Le rollback décrit **séparément** l'API et l'interface, chacune avec son commit, car elles peuvent provenir de builds différents :

- `rollback.api` : `release_commit`, `image`, `migration_head` (tête Alembic de l'image de rollback, jamais plus récente que la cible) ;
- `rollback.web` : `release_commit`, `image` ;
- `database_strategy` : `application-only-forward-schema` (obligatoire) ;
- `schema_compatibility_review` : référence de la revue de compatibilité.

Le validateur refuse : version 1, tag mutable, dépôt autre que GHCR MineFleet, rollback incomplet (API ou web absent, tête Alembic absente, revue absente), composant de rollback identique à la cible (commit ou image), tête de rollback plus récente que la cible, clés inconnues ou dupliquées. Les reçus v1 déjà présents dans `release-state/current.json` restent lisibles par `run-scheduled-job.sh` uniquement (`emit-release-env`) ; ils ne peuvent piloter ni release ni rollback.

## Mécanisme de secours : images locales exactes (non signées)

Quand une image de rollback n'existe pas dans GHCR (cas du web `b35dcd6`, construit localement), le chemin officiel ne peut pas l'exprimer. Le secours est **séparé** :

- manifeste distinct `kind: local-fallback-rollback`, `provenance: local-archive-unsigned` (exemple : `infra/deploy/release-fallback.example.json`), jamais accepté par `plan`/`apply`/`rollback` ;
- pour chaque composant : commit, `image_id` (valeur de `docker image inspect --format '{{.Id}}'` sur l'hôte), archive `docker save` absolue et son SHA256 ;
- avant toute action : SHA256 de l'archive, présence de l'`image_id` dans l'archive (`manifest.json` en magasin classique, `index.json` en magasin containerd), labels de commit et de tête Alembic ;
- l'image est retaguée uniquement `minefleet-local-fallback/<api|web>:<commit>` : aucun nom de registre, aucune présentation comme artefact GHCR ; une archive portant un tag de registre n'est **pas** chargée (l'image déjà présente localement reste utilisable) ;
- approbation dédiée : `rollback-fallback:<commit-api>:<commit-web>` ;
- mêmes garde-fous PostgreSQL, sauvegarde, runtime, PMTiles et smoke métier que le chemin signé.

## Préalables sur l'hôte staging

1. `cosign` installé (vérification hors ligne de la transparence Sigstore incluse).
2. `infra/deploy/.env.prod` : fichier régulier, mode `600`/`400`, `MF_ENV=staging`.
3. Compte **fictif** `OPS_MANAGER` dédié au smoke, enrôlé en MFA ; fichier hors dépôt, mode `600` :
   `MF_SMOKE_WORKSPACE=…`, `MF_SMOKE_EMAIL=…`, `MF_SMOKE_PASSWORD=…`, `MF_SMOKE_TOTP_SECRET=…`.
4. Exécuter depuis le dépôt déployé `/opt/minefleet/infra/deploy` : un autre emplacement changerait la source du montage PMTiles et `plan` le refuse.

## Commandes

```bash
cd /opt/minefleet/infra/deploy
export MINEFLEET_STAGING_URL="https://<origine-staging>"
export MF_SMOKE_CREDENTIALS_FILE="/chemin/absolu/smoke.env"

# 1. Plan (lecture seule : signatures, base, runtime, PMTiles ; rien n'est tiré ni modifié)
./staging-release.sh plan /chemin/absolu/release.json
./staging-release.sh plan-fallback /chemin/absolu/fallback.json

# 2. Application
MF_STAGING_CHANGE_APPROVAL="apply:<release_commit>" \
  ./staging-release.sh apply /chemin/absolu/release.json

# 3a. Rollback signé (images GHCR du manifeste)
MF_STAGING_CHANGE_APPROVAL="rollback:<release_commit>" \
  ./staging-release.sh rollback /chemin/absolu/release.json

# 3b. Rollback de secours (archives locales exactes, NON signées)
MF_STAGING_CHANGE_APPROVAL="rollback-fallback:<commit_api>:<commit_web>" \
  ./staging-release.sh rollback-fallback /chemin/absolu/fallback.json
```

Déroulé de `apply` : préflight complet → sonde HTTPS → sauvegarde vérifiée → téléchargement et contrôle des labels de la cible **et** des images de rollback → `alembic upgrade head` → `check_schema_revision` → remplacement API/web seules → disponibilité, sondes HTTPS, smoke métier, identité PostgreSQL, révision, runtime, PMTiles, image effectivement en service → reçu. En cas d'échec après migration, rollback signé automatique vers les images déjà vérifiées, schéma conservé.

## Limites connues

- Après un rollback explicite, `release-state/current.json` désigne toujours la version annulée : les tâches planifiées (`run-scheduled-job.sh`) utilisent cette image. Suspendre les timers ou redéployer avant de les relancer.
- Le smoke métier est en lecture seule sur le staging ; les écritures sur le schéma avancé ont été prouvées sur copie isolée (`docs/audit/preuves/staging/REPETITION_ISOLEE_2026-11-24_aab109e.md`).
- Une archive de secours n'est pas une release : sans signature, son intégrité ne repose que sur le SHA256 consigné et l'identifiant d'image.
