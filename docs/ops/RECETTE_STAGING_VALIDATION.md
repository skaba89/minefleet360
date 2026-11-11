# Recette d'exploitation staging — lecture seule, dry-run et exercices préparés

- **Objet** : procédure consolidée de validation d'un environnement de recette (staging) OVHcloud, exécutable
  **sans aucune mutation** (phases A/B) puis, **avec approbation explicite uniquement** (phases C/D), pour
  produire les preuves RPO/RTO, de sauvegarde/restauration isolée et de release→rollback exigées par
  `docs/qa/GO_NO_GO.md` (conditions R1/R2) et `docs/audit/COMMERCIAL_READINESS_CURRENT.md` §4.2/§4.5.
- **Règles** : aucun `apply`, aucun `alembic downgrade`, aucune intervention production, aucune donnée réelle ;
  staging ne porte que des données **fictives** (`minefleet seed-fictif`). Toute étape mutatrice exige une
  approbation consignée (`MF_STAGING_CHANGE_APPROVAL`).
- **Base de rédaction** : `infra/deploy/staging-release.sh`, `check-preproduction.sh`, `verify-restore.sh`,
  `verify-offsite-backup.sh`, `backup.sh`, `upload-offsite-backup.sh`, `probe-all.sh`, `run-alert-monitor.py`,
  `notify-alert-smtp.py`, `docker-compose.prod.yml`/`edge.yml`, `docs/STAGING_RELEASE_ROLLBACK.md`,
  `docs/DEPLOIEMENT_OVH.md`. Toute divergence constatée sur l'hôte prime sur ce document et doit être
  consignée dans le rapport (§R).

## 0. Prérequis et interdits

| Prérequis | Détail |
|---|---|
| Accès hôte staging | shell avec docker compose v2 ; **jamais** root par confort |
| Secrets | `infra/deploy/.env.prod` régulier non symbolique, mode `600`/`400`, contenant exactement `MF_ENV=staging` (le script de release le vérifie) |
| URL recette | `MINEFLEET_STAGING_URL` = origine HTTPS sans chemin ni identifiants (regex imposée par les scripts) |
| Manifeste de release | copie hors dépôt de `release-manifest.example.json`, digests `@sha256:` uniquement |
| Outillage de vérification | `cosign` (signature keyless Sigstore), `jq`, `openssl` |
| Comptes de recette | comptes fictifs pré-créés ; rôles sensibles (TENANT_ADMIN, OPS_MANAGER, DIRECTION, FINANCE, HR, PLATFORM_ADMIN) exigent l'enrôlement MFA si `MF_MFA_ENFORCEMENT=on` — prévoir les secrets TOTP dans le coffre ou mener la recette comptes sur un rôle non assujetti (DISPATCHER, WORKSHOP_CHIEF, MECHANIC, STOREKEEPER, FUEL_MANAGER, HSE, AUDITOR) |

**Interdits pendant les phases A/B** : `staging-release.sh apply|rollback`, `docker compose up/down/pull`,
`backup.sh` (crée un objet), tout `psql` en écriture, toute API mutatrice. Seules les lectures (labels,
catalogues PostgreSQL, sondes, GET API) sont autorisées.

## Phase A — Audit en lecture seule de l'état courant (aucune mutation)

Exécuter depuis `infra/deploy/`, avec le `.env.prod` en place. Consigner chaque sortie horodatée dans le
rapport (§R) ; ne jamais coller de secret ni de donnée opérationnelle dans le rapport.

### A1 — Versions déployées (API / frontend / commit)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps                       # conteneurs attendus
docker inspect --format '{{.Name}} {{index .Config.Labels "org.opencontainers.image.revision"}}' \
  "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q api)" \
  "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q web)"
cat release-state/current.json   # reçu de la dernière release (sans secret)
```

**Attendu** : labels de révision API et web identiques entre eux et au reçu ; si un manifeste candidat est
préparé, sa révision est le `git rev-parse HEAD` validé en CI (3/3 workflows verts).

### A2 — Schéma Alembic

```bash
docker inspect --format '{{index .Config.Labels "com.minefleet.alembic-head"}}' \
  "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q api)"
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile ops run --rm --no-deps migrate \
  python -m app.core.check_schema_revision        # contrôle concordance schéma ↔ image (lecture)
```

**Attendu** : label image = tête Alembic annoncée = révision réellement appliquée en base. Toute divergence
est bloquante pour toute release (l'étape `migrate` de `apply` échouerait ou la fumée finale retomberait en
rollback automatique).

### A3 — Images et signatures

```bash
docker inspect --format '{{index .RepoDigests 0}}' <image-api> <image-web>      # digests réels
cosign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/skaba89/minefleet360/' \
  ghcr.io/skaba89/minefleet360/api@sha256:<digest>
cosign verify-attestation --type https://slsa.dev/provenance/v1 <mêmes options> \
  ghcr.io/skaba89/minefleet360/api@sha256:<digest>
```

**Attendu** : vérifications Cosign/attestation SLSA en succès ; aucun tag flottant (`latest`, `main`)
référencé par le compose courant.

### A4 — Permissions et isolation PostgreSQL (canaries en lecture de catalogue)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db psql -U postgres -d minefleet -tAc "
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('mf_owner','mf_app');
SELECT has_table_privilege('mf_app','app.insurance_policy','INSERT,UPDATE,DELETE');
SELECT has_table_privilege('mf_app','app.legal_contract','INSERT');
SELECT count(*) FROM pg_tables WHERE schemaname='app' AND rowsecurity;"   # tables RLS activées
```

**Attendu** : `mf_owner`/`mf_app` non-superuser, `NOBYPASSRLS` ; privilèges métier attendus (un surplus est
un 403 applicatif manquant, un manque casse des routes) ; nombre de tables `rowsecurity` cohérent avec la
migration de fondation (75 à la rédaction). **Ne jamais exécuter de DDL/DML de vérification** : les
vérifications effectives de cloisonnement (RLS, IDOR) sont faites par la suite de recette sur base jetable,
pas sur staging.

### A5 — HTTPS et configuration Compose

```bash
bash check-preproduction.sh docker-compose.prod.yml            # parse compose, sans secret ni conteneur
MINEFLEET_STAGING_URL="https://recette.example.com" \
  bash check-preproduction.sh docker-compose.prod.yml --live   # sondes /, /api/v1/health, /api/v1/ready
echo | openssl s_client -connect recette.example.com:443 -servername recette.example.com 2>/dev/null \
  | openssl x509 -noout -dates
```

**Attendu** : HTTP 200 sur les trois routes ; certificat valide > 14 jours (sinon renouvellement ACME à
prévoir) ; pas de redirection ni de TLS invalide (les sondes refusent tout contournement de vérification).

### A6 — Comptes et permissions (API, lecture seule)

Pour chaque rôle du jeu fictif : `POST /api/v1/auth/login` puis `GET /api/v1/me`, vérifier les grants et la
portée (TENANT/SITE). **Aucun POST/PUT/DELETE métier** : la vérification fonctionnelle fine est couverte par
la CI (`e2e-isolation`) sur base jetable ; sur staging on vérifie uniquement l'identité, les menus exposés
dans `/me` et la cohérence avec `docs/qa/ROLE_PAGE_ACTION_MATRIX.md`. Vérifier explicitement qu'un rôle non
autorisé reçoit 403 sur une route hors grants et que PLATFORM_ADMIN n'accède à aucune route privée de
société (`GET /api/v1/vehicles` → 403).

### A7 — Routes et surface exposée

```bash
for r in / /api/v1/health /api/v1/ready /connexion; do
  curl -s -o /dev/null -w "%{http_code} $r\n" --proto '=https' "https://recette.example.com$r"; done
curl -s -o /dev/null -w "%{http_code} /docs (doit être 404/401 hors local)\n" --proto '=https' \
  "https://recette.example.com/docs"
```

**Attendu** : 200 sur les routes publiques attendues ; `/docs` et `/openapi.json` **non exposés** (fermés
hors environnement local depuis #374). La fumée publique `frontend/e2e-smoke/login.spec.ts` reste exécutable
en CI ; les suites E2E **mutatrices** restent interdites sur staging (base éphémère uniquement).

### A8 — Logs et santé continue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --since 24h api web 2>&1 \
  | rg -ci "traceback|error" || echo "0 erreur"
MINEFLEET_BASE_URL="https://recette.example.com" bash probe-all.sh   # exit 0 attendu
docker system df && docker compose -f docker-compose.prod.yml --env-file .env.prod stats --no-stream
```

**Attendu** : `probe-all.sh` exit 0 (PostgreSQL, fraîcheur de sauvegarde locale, jobs planifiés, API
externe) ; aucun traceback récent ; espace disque suffisant pour une nouvelle sauvegarde.

## Phase B — Dry-run de release (plan sans mutation)

```bash
python3 release_manifest.py validate /chemin/absolu/release.json    # manifeste candidat
bash staging-release.sh plan /chemin/absolu/release.json            # PLAN OK
```

**Attendu** : `PLAN OK: staging <commit> uses immutable API/web images` puis `PLAN ONLY: no image pulled,
container changed, migration run or backup created`. Le plan valide le manifeste, la concordance des labels
attendus et le parse Compose avec le vrai `.env.prod`. Le plan ne **prouve** ni les signatures ni le
comportement en charge : il prouve que la release est *appliquable* sans surprise structurelle.

## Phase C — Sauvegarde et restauration isolée (avec approbation — produit la preuve R1)

Hors périmètre lecture seule : consigner l'approbation (qui, quand, périmètre) avant exécution.

```bash
time bash backup.sh                                    # pg_dump chiffré horodaté (début de mesure RPO)
MF_BACKUP_DIR=backups MF_BACKUP_MAX_AGE_HOURS=1 bash probe-backup-freshness.sh
bash verify-restore.sh /absolu/minefleet-YYYYMMDDTHHMMSS.dump --api-image <image-api>   # instance jetable isolée
time bash verify-offsite-backup.sh minefleet-YYYYMMDDTHHMMSSZ.dump.gpg --api-image <image-api>
```

**Preuves RPO/RTO à consigner** (définitions opérationnelles) :
- **RPO** = âge maximal de la dernière sauvegarde réputée saine au moment de l'incident simulé
  (horodatage début d'exercice − horodatage du dump restauré) ; cible à figer lors de l'exercice.
- **RTO** = durée `verify-restore.sh` (récupération de l'archive → décryptage → restauration → smoke API)
  jusqu'au premier `GET /api/v1/health` réussi de l'instance restaurée.
- Déposer : `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` (à créer lors du premier exercice réel) avec
  horodatages bruts, tailles, checksums, exit codes et l'objet coffre effectivement utilisé.

## Phase D — Exercice release → rollback (avec approbation — produit la preuve R2)

Séquence complète et preuves attendues : voir `docs/STAGING_RELEASE_ROLLBACK.md` (« Preuves à conserver
pour valider R2 ») : manifeste + digests, SHA des workflows verts, horodatages et durée d'indisponibilité,
tête Alembic avant/après, résultat de la sauvegarde et de la restauration séparée, sondes avant/après
déploiement et après rollback, reçu `release-state/current.json`. Rappel du mécanisme : le rollback est
**applicatif seulement**, le schéma reste à la révision migrée — toute migration déployée doit être
compatible avec l'image de rollback (revue avant apply).

## R — Rapport d'exploitation (modèle)

| Champ | Valeur |
|---|---|
| Date / opérateur / approbateur | … |
| Commit et CI du candidat | … (3/3 workflows verts) |
| Reçu staging avant / après | `release-state/current.json` (révision, digests) |
| A1–A8 | tableaux de sorties horodatées, anomalies éventuelles |
| Plan (dry-run) | sortie intégrale |
| Sauvegarde / restauration | durées, checksums, gates RLS, RPO/RTO mesurés |
| Rollback | sondes avant/après, durée |
| Incidents et actions | … |

Preuves déposées hors dépôt si sensibles, référencées par chemin + SHA256 dans `docs/audit/preuves/staging/`.

## Alerte incident — procédure et éprouvetage

- **Détection** : `probe-all.sh` (exit 0 OK / 2 critique / 3 configuration) ; `run-alert-monitor.py
  --state-dir … --threshold 3` persiste les transitions `ALERT`/`RECOVERED` et retente les remises SMTP
  (at-least-once, jamais de rejet silencieux) ; `notify-alert-smtp.py` envoie ; unités systemd
  `minefleet-monitor.timer` et `minefleet-notify-deliver.timer`.
- **Éprouvetage obligatoire avant pilote** (condition GO n°8) : provoquer un incident réel — ex.
  `docker compose stop api` pendant quelques cycles — et prouver : transition `ALERT` enregistrée, e-mail
  reçu et lisible, retour à la normale → `RECOVERED`, aucune perte d'événement après redémarrage du moniteur.
- **Sévérités** : S1 API/DB inaccessible ou sauvegarde en échec (prise en charge immédiate) ; S2 sonde
  `UNKNOWN` persistante ou jobs planifiés en retard ; S3 observation sans impact utilisateur. Temps cibles
  de prise en charge à **figer lors de l'éprouvetage** et à consigner ici.

## Critères de passage

La phase A/B réussie sans anomalie **ne lève aucun bloquant** : elle autorise seulement à demander
l'approbation des phases C/D. R1 (restauration réelle mesurée) et R2 (release→rollback attesté) restent
non validés tant que les exercices n'ont pas produit leurs preuves ; le verdict `GO_NO_GO.md` n'évolue
pas sur la seule base de ce document.
