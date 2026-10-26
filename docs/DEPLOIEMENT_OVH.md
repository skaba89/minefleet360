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
- `caddy` : seul service exposé (80/443), HTTPS automatique, en-têtes de sécurité, proxy `/api/*`.
- `api` : image `runtime` non root ; ne reçoit que `MF_APP_PASSWORD` et `MF_JWT_SECRET` (moindre privilège).
- `migrate` : tâche ponctuelle, seule à recevoir le secret `mf_owner`.
- `db` : PostgreSQL 16 + PostGIS, **aucun port publié** ; pas de base de test (`MF_CREATE_TEST_DB` absent).

## 4. Procédure (SSH, chaque étape journalisée)
1. Durcissement : mises à jour, `ufw` (22, 80, 443), `PasswordAuthentication no`, mises à jour de sécurité automatiques.
2. Docker Engine + plugin Compose (dépôt officiel).
3. Clone du dépôt privé avec une **clé de déploiement en lecture seule**, branche `main`.
4. `infra/deploy/.env.prod` créé **sur le serveur** (secrets `openssl rand -hex 32`, droits `600`), `MF_ENV=staging`.
5. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build db api caddy`.
6. `docker compose ... run --rm migrate`.
7. Premier `PLATFORM_ADMIN` (`MF_BOOTSTRAP_PASSWORD` saisi de façon interactive) : `minefleet create-platform-admin`.
8. **Recette** : `minefleet seed-fictif` → 2 sociétés fictives, 4 sites (dont 2 en UTC+1), 16 comptes (un par rôle et par société), 20 véhicules, 16 conducteurs, permis (valides, proches de l'échéance, expirés), habilitations. Les mots de passe sont affichés **une seule fois** à transmettre aux testeurs par un canal sûr.
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
