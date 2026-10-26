# Déploiement sur OVH Cloud — environnement réel (recette puis production)

> Décision client (2026-10-26) : **pas de démo jetable**, mais le **vrai projet** déployé avec une configuration de production, alimenté pour l'instant de **données exclusivement fictives** pour les tests. Les données réelles n'arrivent qu'après levée des bloquants du §5.

## 1. Environnements
| `MF_ENV` | Usage | Données | Commande `seed-fictif` |
|---|---|---|---|
| `staging` (recette) | Tests fonctionnels, recette client, formation | **Fictives** (`minefleet seed-fictif`), tenants marqués `is_demo` | Autorisée |
| `production` | Exploitation réelle | Réelles | **Refusée** (US-1.30 A3) |

Même image, même `docker-compose.prod.yml`, même durcissement : seule la variable `MF_ENV` et le contenu changent. Recommandation : deux machines distinctes (recette et production) le moment venu, pour ne jamais mélanger données fictives et réelles.

## 2. À fournir par le client
| Élément | Détail |
|---|---|
| Machine | VPS ou instance Public Cloud OVH, **Ubuntu 24.04**, 2 vCPU / 4 Go RAM minimum pour la recette (dimensionnement non mesuré) |
| Accès SSH | IP + utilisateur sudo ; clé publique du poste de déploiement dans `~/.ssh/authorized_keys` (pas de mot de passe SSH) |
| Nom de domaine | Ex. `recette.<domaine>` : enregistrement DNS **A** vers l'IP (certificat HTTPS) |
| E-mail ACME | Adresse d'exploitation pour Let's Encrypt |

## 3. Architecture (une machine)
Deux variantes, même image et même base :
- **machine dédiée** : le service `caddy` du projet (profil `standalone-proxy`) publie 80/443 ;
- **serveur partagé** (cas du VPS actuel, qui héberge d'autres applications) : `docker-compose.edge.yml` attache la seule API au réseau Docker externe `edge` (alias `minefleet-api`) ; le proxy commun du serveur publie 80/443 et sert `vps-proxy-minefleet.caddy`. L'API est aussi publiée sur `127.0.0.1:8200` pour les vérifications par tunnel SSH.

Services :
- `caddy` (machine dédiée) ou proxy commun : seul point exposé (80/443), HTTPS automatique, en-têtes de sécurité, proxy `/api/*`.
- `api` : image `runtime` non root ; ne reçoit que `MF_APP_PASSWORD` et `MF_JWT_SECRET` (moindre privilège).
- `migrate` : tâche ponctuelle, seule à recevoir le secret `mf_owner`.
- `db` : PostgreSQL 16 + PostGIS, **aucun port publié**, nom d'hôte unique `minefleet-db` ; pas de base de test (`MF_CREATE_TEST_DB` absent).
- Limites mémoire : API 768 Mo, base 1 Go (serveur partagé).
- `MF_FORWARDED_ALLOW_IPS` : seuls ces pairs (IP/CIDR) peuvent transmettre `X-Forwarded-For` (sinon usurpation d'IP possible : limitation de débit, audit). Machine dédiée : sous-réseau du projet ; serveur partagé : sous-réseau `edge` (risque résiduel : les autres conteneurs de `edge`, qui sont vos propres applications ; à restreindre à l'IP du proxy si elle est fixée).

## 4. Procédure (SSH, chaque étape journalisée)
1. Durcissement : mises à jour, `ufw` (22, 80, 443), `PasswordAuthentication no`, mises à jour de sécurité automatiques.
2. Docker Engine + plugin Compose (dépôt officiel).
3. Code : `git archive <commit> | ssh … tar -x` depuis le poste de déploiement (aucun identifiant GitHub sur le serveur), ou clone avec une **clé de déploiement en lecture seule**. Le commit déployé est noté dans `DEPLOYED_COMMIT`.
4. `infra/deploy/.env.prod` créé **sur le serveur** (secrets `openssl rand -hex 32`, droits `600`), `MF_ENV=staging`.
5. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build db api caddy`.
6. `docker compose ... run --rm migrate`.
7. Premier `PLATFORM_ADMIN` (`MF_BOOTSTRAP_PASSWORD` saisi de façon interactive) : `minefleet create-platform-admin`.
8. **Recette** : `minefleet seed-fictif >> comptes-recette.txt` (fichier `600` sur le serveur, jamais affiché dans un terminal partagé) → 2 sociétés fictives, 4 sites (dont 2 en UTC+1), 16 comptes (un par rôle et par société), 20 véhicules, 16 conducteurs, permis (valides, proches de l'échéance, expirés), habilitations. Les mots de passe sont affichés **une seule fois** à transmettre aux testeurs par un canal sûr.
9. Vérifications : `/api/v1/health` → 200, route protégée sans jeton → 401, certificat valide, connexion d'un compte fictif.
10. Sauvegarde : `backup.sh` en cron quotidien.

## 5. Conditions avant tout passage en production (données réelles)
| Bloquant | Référence |
|---|---|
| MFA (TOTP) pour `PLATFORM_ADMIN`, `TENANT_ADMIN`, `HR`, `FINANCE` | C-03, SEC-04 |
| Avis juridique guinéen : base légale, hébergement hors Guinée, durées de conservation | C-01, C-08, C-09 |
| Sauvegardes chiffrées hors machine + test de restauration | SEC-15 |
| Limitation de débit partagée (pas en mémoire) et supervision/alertes | SEC-07, QA-32 |
| Envoi d'e-mails réel (fournisseur) au lieu de la capture locale | D-28, SEC-08 |
| Interface web et tests E2E (tranche 1c), revue sécurité finale | PLAN_LOT1 |
| Machine dédiée à la production, distincte de la recette | §1 |

## 6. Retour arrière
`git checkout <commit précédent>` puis `up -d --build`. Aucune migration n'est rétrogradée hors `local/test/ci` : toute migration doit rester rétrocompatible (expansion/contraction). Dernier recours : restauration du dernier `pg_dump`.

## 7. Recette déployée (2026-10-26)
| Élément | Valeur |
|---|---|
| Serveur | VPS OVH `vps-235d8499.vps.ovh.net` (51.75.248.4), Ubuntu 26.04, **partagé** avec gestion-scolaire-pro, Kora et Kora Finance |
| Variante | Serveur partagé (`docker-compose.edge.yml`), `MF_ENV=staging`, répertoire `~/minefleet360` |
| Adresse | `https://minefleet.51-75-248-4.sslip.io` (pas de nom de domaine : nom sslip.io dérivé de l'IP, comme Kora) ; API sous `/api/v1/` (santé : `/api/v1/health`) |
| Données | Fictives : 2 sociétés, 4 sites, 18 comptes (dont l'administrateur plateforme), 20 véhicules, 16 conducteurs, permis et habilitations |
| Comptes | `~/minefleet360/infra/deploy/comptes-recette.txt` (`600`) : à récupérer puis supprimer |

Vérifié sur le serveur (via `127.0.0.1:8200`) : migrations à `0007` (head) ; `/health` 200 ; route protégée sans jeton 401 ; mauvais mot de passe 401 ; connexion d'un compte fictif 200 ; chaque société ne voit que ses 10 véhicules ; véhicule d'une autre société 404 ; compte d'une société refusé sur l'espace de l'autre 401 ; masquage des champs RH (téléphone, contrat…) pour OPS_MANAGER, visibles pour HR ; paramètre inconnu 422 ; DISPATCHER refusé en création de véhicule 403 ; sauvegarde `pg_dump` (fichier `600`, dossier `700`).

**Reste à faire par l'exploitant** (actions refusées à l'agent : configuration d'un autre projet et tâche planifiée persistante) :
1. ~~Exposition HTTPS~~ — **fait le 2026-10-26** : site copié dans `~/vps-proxy/sites/minefleet.caddy`, proxy commun rechargé, certificat Let's Encrypt obtenu ; `https://minefleet.51-75-248-4.sslip.io/api/v1/health` 200 depuis l'extérieur, autres sites du proxy toujours servis.
2. ~~Sauvegarde quotidienne~~ — **fait le 2026-10-26** : crontab de `ubuntu` = `17 2 * * * $HOME/minefleet360/infra/deploy/backup.sh >> $HOME/minefleet360/infra/deploy/backup.log 2>&1` (script testé en environnement minimal ; rétention locale 7 fichiers).
3. Copie hors machine chiffrée des sauvegardes (§5).
