# Remise à zéro sécurisée du staging (#532) — runbook opérateur

> **Staging uniquement.** Aucune étape ne s'exécute sans l'approbation exacte affichée par l'étape précédente. Rien ne touche la base en service avant `cutover`, et `cutover` n'est jamais lancé sans autorisation explicite de l'opérateur.

Outil : `infra/deploy/staging-reset.sh` (+ `staging-reset-catalog.sql`, `staging_reset.py`, `staging-reset-admin-check.py`). Inventaire préalable en lecture seule : `staging-reset-inventory.sh` (#533, `STAGING_RESET_PHASE1.md`).

## 1. Choix de l'approche

| Critère | Nettoyage transactionnel de la base active | **Nouvelle base candidate (retenue)** |
|---|---|---|
| Écritures sur la base en service | `DELETE` sur ~100 tables dans l'ordre des 241 FK | **aucune** avant la bascule |
| `audit_event` (14 partitions) | triggers *append-only* et *no-truncate* : impossible sans les désactiver — interdit | partitions neuves créées par la migration 0004 |
| RLS forcée | suppression par tenant sous `mf_owner` ou contournement — interdit | sans objet |
| Exhaustivité | dépend d'une liste à maintenir ; une table oubliée garde des données | **par construction** : la base ne contient que ce que créent les migrations, vérifié table par table |
| Séquences, index, statistiques | restent dans l'état antérieur | neufs |
| Référentiels (9 tables) | conservés en place | recréés par les migrations puis **recopiés à l'identique** si leur empreinte diffère (cas `saas_plan` : UUID et dates de création) |
| Retour arrière | restauration de dump (minutes à heures, risque) | **re-pointage sur l'ancien volume, intact** ; preuve d'égalité automatique |
| Durée d'indisponibilité | longue (suppression + VACUUM) | ~40 s mesurées en labo |

Le nettoyage transactionnel exigerait de désactiver les triggers d'audit et de contourner la RLS sur la base active : il est écarté.

## 2. Principe

1. `plan` (défaut) : lecture seule, identité de la cible et approbations à utiliser.
2. `build-candidate` : projet Compose isolé `minefleet-reset-<horodatage>` (réseau propre, **volume neuf** `…_db-data`, aucun port publié), initialisation PostgreSQL par `infra/db/init` (rôles `mf_owner`/`mf_app` avec les mêmes mots de passe), `alembic upgrade head` **avec l'image API en service**, `check_schema_revision`, copie des référentiels différents, comparaison complète avec la base en service.
3. `bootstrap-candidate` : `minefleet create-platform-admin` sur la candidate, refus du double bootstrap, puis vérifications HTTP réelles sur une API temporaire du réseau privé (mot de passe erroné, MFA, permissions, révocation).
4. `cutover` : sauvegarde, gel vérifié, re-vérification de la candidate, `MF_DB_VOLUME` pointé sur le volume candidat, recréation du **seul** conteneur `db`, contrôles et connexion réelle du nouvel administrateur ; retour arrière automatique en cas d'échec.
5. `rollback-cutover` : re-pointage sur l'ancien volume et **preuve** d'identité avec l'état avant bascule.

Contrôles de comparaison (`staging_reset.py`) : extensions, rôles SQL, schémas, 110 tables, colonnes, 213 contraintes FK de tables mères (+ 28 portées par les partitions d'audit = 241), index, 153 triggers non internes, 92 politiques RLS, drapeaux RLS/FORCE, droits, séquences, fonctions, vues ; partitions `audit_event` (DEFAULT + mois courant, RLS forcée) ; 9 référentiels identiques ligne à ligne (empreinte MD5 du texte trié) ; aucune ligne d'un tenant autre que la plateforme ; aucune table globale non référentielle non vide ; tenant plateforme `…0001` actif.

Garde-fous : refus si `.env.prod` n'a pas exactement `MF_ENV=staging` ou n'est pas en 600/400 ; `MF_RESET_EXPECTED_HOST` doit égaler le nom de l'hôte ; conteneur `minefleet-db-1` du projet `minefleet`, sain, sur le volume attendu ; approbations liées à l'ID du conteneur et au nom du projet candidat ; Compose doit résoudre le volume candidat **avant** tout `up` (jamais deux PostgreSQL sur le même volume) ; aucun `DROP DATABASE`, `TRUNCATE`, `DELETE` sur la base en service, `compose down`, suppression de volume, désactivation de trigger ou de RLS (test statique). Arrêt immédiat à la première incohérence ; la candidate est alors arrêtée.

Journal de preuves sans secret : `infra/deploy/release-state/reset/<candidat>/` (700) — `evidence.log`, catalogues, rapports JSON, copie 600 de `.env.prod` avant chaque bascule.

## 3. Conséquences analysées

| Élément | Après bascule | Preuve |
|---|---|---|
| Sessions et jetons d'accès | rejetés : chaque requête exige une `auth_session` active en base (`authz/dependencies.py`) | labo : ancien jeton → 401, ancien mot de passe → 401 |
| Jetons de compte (invitations, réinitialisations) | inexistants dans la nouvelle base | catalogue : `account_token` = 0 |
| Traceurs GPS | rejetés : jeton composite vérifié contre `fleet_gps_device_binding` (`gps_tracker_ingest.py`) | `fleet_gps_device_*` = 0 |
| Outbox hors ligne des navigateurs (PWA) | non rejouée : entrées rangées par `tenantId` + `userId` (`offline-outbox.ts`) ; les nouveaux comptes ont de nouveaux UUID | revue de code ; vider les navigateurs de recette recommandé |
| Files / caches | aucun Redis ni broker dans `docker-compose.prod.yml` ; limiteurs en base (`app.auth_failure_bucket`) | catalogue |
| E-mails capturés (`minefleet_mail-capture`) | anciens messages conservés au plus `MF_MAIL_CAPTURE_TTL_SECONDS` (24 h) ; leurs liens sont morts (jetons absents) | à laisser expirer |
| Stockage documentaire objet | **à vérifier** : si `MF_LEGAL_OBJECT_STORAGE_ENABLED=true`, les objets des anciens tenants restent dans le bucket (orphelins) | hors outil ; décision opérateur |
| Sauvegardes et ancien volume | conservés (aucune suppression) ; contiennent les anciennes données fictives | politique de rétention inchangée |
| Secret JWT | rotation **non requise** (sessions en base) ; possible par la procédure `ROTATION_SECRETS.md` | — |

## 4. Procédure (VPS, `/opt/minefleet/infra/deploy`, dépôt à jour sur `main`)

```bash
export MF_RESET_EXPECTED_HOST="$(hostname)"
./staging-reset.sh                                   # 1. plan : noter l'approbation affichée
MF_RESET_APPROVAL=build-candidate:<id-db>:minefleet_db-data ./staging-reset.sh build-candidate
```

Bootstrap (mot de passe dans un fichier 600 d'une ligne, jamais en argument ni à l'écran ; le fichier de sortie, créé en 600, reçoit le secret TOTP et les 10 codes de récupération) :

```bash
install -m 600 /dev/null ~/minefleet-release/admin.password && nano ~/minefleet-release/admin.password
export MF_RESET_ADMIN_EMAIL=<adresse> MF_RESET_ADMIN_NAME="<nom>" \
       MF_RESET_ADMIN_PASSWORD_FILE=/home/ubuntu/minefleet-release/admin.password \
       MF_RESET_ADMIN_SECRETS_OUT=/home/ubuntu/minefleet-release/admin.secrets.json
MF_RESET_APPROVAL=bootstrap-candidate:<candidat> ./staging-reset.sh bootstrap-candidate <candidat>
```

Fenêtre de maintenance — **uniquement après autorisation explicite** :

```bash
sudo systemctl stop minefleet-notify-deliver.timer minefleet-gps-signal-sweep.timer \
  minefleet-preventive-evaluate.timer minefleet-hse-digest.timer
# couper les producteurs GPS de terrain (applications, simulateurs) le temps de la fenêtre
export MINEFLEET_STAGING_URL=https://<origine-staging>
MF_RESET_APPROVAL=cutover:<candidat>:<id-db> ./staging-reset.sh cutover <candidat>
```

Après `CUTOVER OK` : se connecter en administrateur plateforme (MFA), recréer les sociétés et comptes fictifs étape par étape, nouveau compte de smoke (`smoke.env`), vider le stockage local des navigateurs de recette, puis relancer les timers.

Retour arrière (base précédente intacte) :

```bash
MF_RESET_APPROVAL=rollback-cutover:<candidat> ./staging-reset.sh rollback-cutover <candidat>
```

Si le retour arrière lui-même échouait : `MF_DB_VOLUME=minefleet_db-data` dans `.env.prod` (copie disponible dans le répertoire d'état), puis `docker compose -f docker-compose.prod.yml -f docker-compose.edge.yml --env-file .env.prod up -d --no-deps --no-build db` et `start api` ; en dernier recours, restauration du dump pris par `cutover` via `verify-restore.sh` sur copie isolée d'abord.

Nettoyage ultérieur (décision opérateur, hors outil) : les volumes et réseaux `minefleet-reset-*` non retenus ne sont jamais supprimés automatiquement.

## 5. Récupération administrateur

- Perte du second facteur : `minefleet reset-platform-mfa --email <adresse>` (existant, audité, sessions fermées).
- Perte du mot de passe : la réinitialisation anonyme des comptes plateforme reste désactivée (`auth_service.request_password_reset`). Sur la **candidate** (avant bascule), refaire un `build-candidate` + `bootstrap-candidate`. Après bascule, aucune commande ne remplace un mot de passe plateforme : conserver le fichier de mot de passe et `admin.secrets.json` hors serveur (coffre), comme la clé MFA.

## 6. GO / NO-GO

GO pour `cutover` seulement si : `build-candidate` et `bootstrap-candidate` OK **sur le VPS** ; sauvegarde du jour restaurée avec `verify-restore.sh` ; producteurs GPS et timers arrêtés ; stockage objet vérifié ; secrets administrateur mis en coffre ; **autorisation explicite écrite de l'opérateur**.
