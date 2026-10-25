# Déploiement — environnement de démonstration sur OVH Cloud

> Décision client (2026-10-25) : **démo/recette avec données exclusivement fictives**, sur **un VPS ou une instance Public Cloud OVH créé(e) par le client**, déploiement par SSH. Ce n'est **pas** une production : pas de données réelles tant que MFA, interface, revue sécurité et avis juridique (C-01, C-08, C-09 : hébergement hors de Guinée) ne sont pas réglés.

## 1. À fournir par le client
| Élément | Détail |
|---|---|
| Machine | VPS OVH (ou instance Public Cloud), **Ubuntu 24.04**, 2 vCPU / 4 Go RAM minimum (dimensionnement de démo, non mesuré) |
| Accès SSH | Adresse IP + utilisateur sudo ; **clé publique** du poste de déploiement ajoutée à `~/.ssh/authorized_keys` (pas de mot de passe SSH) |
| Nom de domaine | Ex. `demo.<votre-domaine>` avec un enregistrement DNS **A** vers l'IP du VPS (nécessaire au certificat HTTPS) |
| E-mail ACME | Adresse d'exploitation pour Let's Encrypt |

## 2. Architecture
Une machine, Docker Compose (`infra/deploy/docker-compose.demo.yml`) :
- `caddy` : seul service exposé (80/443), HTTPS automatique, en-têtes de sécurité, proxy `/api/*` ;
- `api` : image `runtime` (Python 3.12, utilisateur non root), `MF_ENV=staging` (downgrade Alembic refusés) ;
- `db` : PostgreSQL 16 + PostGIS, **aucun port publié**, rôles `mf_owner`/`mf_app` créés par `infra/db/init/00_bootstrap.sh`.

## 3. Procédure (exécutée par SSH, chaque étape journalisée)
1. Durcissement : mises à jour, pare-feu `ufw` (22, 80, 443 uniquement), `PasswordAuthentication no`, mises à jour de sécurité automatiques.
2. Installation de Docker Engine + plugin Compose (dépôt officiel Docker).
3. Récupération du code : clone du dépôt privé avec une **clé de déploiement en lecture seule** (GitHub → Settings → Deploy keys), branche `main`.
4. Secrets : création de `infra/deploy/.env.demo` **sur le serveur uniquement** (`openssl rand -hex 32` par secret), droits `600`.
5. `docker compose -f docker-compose.demo.yml --env-file .env.demo up -d --build`.
6. Migrations : `docker compose ... exec api alembic upgrade head`.
7. Premier `PLATFORM_ADMIN` : `MF_BOOTSTRAP_PASSWORD` saisi de façon interactive, puis `minefleet create-platform-admin`.
8. Vérifications : `https://<domaine>/api/v1/health` → 200 ; route protégée sans jeton → 401 ; certificat valide.
9. Sauvegarde : `backup.sh` en cron quotidien (rétention locale 7 jours ; copie hors machine à décider, C-09).

## 4. Limites de la démo (connues)
- Pas d'interface web (tranche 1c) : démonstration via `/api/v1/docs` (OpenAPI) — l'exposer publiquement est un choix à confirmer.
- E-mails **capturés** dans le volume `mail-capture` (aucun envoi réel) : les liens d'invitation se récupèrent par l'exploitant (`docker compose exec api ls /data/mail`).
- Limitation de débit en mémoire par processus (2 workers → seuils effectifs doublés au pire).
- Pas de supervision ni d'alerte ; pas de sauvegarde hors machine.

## 5. Retour arrière
`git checkout <commit précédent>` puis `up -d --build`. Les migrations ne sont **jamais** rétrogradées en `staging` : toute migration future doit être rétrocompatible (expansion/contraction). En dernier recours : restauration du dernier `pg_dump`.
