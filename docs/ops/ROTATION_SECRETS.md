# Rotation des secrets — recette et production

Procédure d'exploitation (phase 6). Elle s'applique au serveur qui porte `infra/deploy/.env.prod` (droits 600,
jamais commité). **Toute rotation sur un serveur est une intervention sensible** : accord préalable du
responsable, fenêtre annoncée, sauvegarde fraîche vérifiée (`probe-backup-freshness.sh`).

Règles communes :

- générer chaque nouvelle valeur **sur le serveur** (`openssl rand -hex 32`, ou la commande indiquée), ne jamais la
  coller dans un ticket, un chat ou un journal ; ne jamais afficher `.env.prod` (`grep`, `cat`, `docker compose
  config` sont interdits sur ce fichier) ;
- conserver l'ancienne valeur dans le coffre externe jusqu'à la fin de la vérification (retour arrière) ;
- toutes les commandes sont limitées au projet Compose `minefleet` (serveur partagé) ;
- après chaque rotation : `bash audit-staging-readonly.sh --live` (0 échec attendu) et consigner la date, le
  secret concerné (nom seulement) et l'opérateur dans le registre d'exploitation.

## Inventaire

| Secret | Usage | Effet d'une rotation | Fréquence recommandée |
|---|---|---|---|
| `MF_JWT_SECRET` | signature des jetons d'accès (15 min) et des défis MFA (5 min) | jetons d'accès et défis en cours invalidés ; les sessions se renouvellent seules (le cookie de rafraîchissement n'en dépend pas) ; un défi MFA en cours est à recommencer | 6 mois, et immédiatement en cas de fuite |
| `MF_RATE_LIMIT_KEY` | HMAC des compteurs de limitation d'authentification | compteurs de tentatives remis à zéro | 6 mois |
| `MF_APP_PASSWORD` | rôle PostgreSQL `mf_app` (API, tâches) | redémarrage de l'API et des tâches | 6 mois |
| `MF_OWNER_PASSWORD` | rôle `mf_owner` (migrations, purges) | aucun effet utilisateur ; prochaine migration avec la nouvelle valeur | 6 mois |
| `POSTGRES_PASSWORD` | super-utilisateur PostgreSQL (exploitation) | aucun effet applicatif | 6 mois |
| `MF_MFA_ENCRYPTION_KEY` | chiffrement des secrets TOTP, poivre des codes de récupération | **rotation en deux temps** (ci-dessous) : sans elle, tous les seconds facteurs deviennent inutilisables | 12 mois, et immédiatement en cas de fuite |
| `MF_SMTP_PASSWORD`, clés de stockage objet, phrase de chiffrement hors site | services externes | renouveler d'abord chez le fournisseur, puis ici | selon le fournisseur |

## Rotation simple (`MF_JWT_SECRET`, `MF_RATE_LIMIT_KEY`)

1. Générer la valeur sur le serveur et remplacer la ligne dans `.env.prod` avec un éditeur (pas de `sed -i` qui
   laisserait une copie dans l'historique du shell).
2. `docker compose -p minefleet -f docker-compose.prod.yml [-f docker-compose.edge.yml] up -d api`
   (et les services de tâches qui portent la variable).
3. Vérifier `/api/v1/ready`, une connexion réelle, puis l'audit en lecture seule.
4. Retour arrière : remettre l'ancienne valeur et relancer les mêmes services.

## Mots de passe des rôles PostgreSQL (`MF_APP_PASSWORD`, `MF_OWNER_PASSWORD`)

Le rôle garde l'ancien mot de passe jusqu'à `ALTER ROLE` : on change d'abord la base, puis la configuration, puis
on redémarre, pour une coupure de quelques secondes seulement.

1. Générer la valeur. La passer à `psql` par l'entrée standard (jamais en argument de commande, visible dans
   `ps`) : `\password mf_app` dans une session `docker compose -p minefleet exec db psql -U postgres`.
2. Mettre à jour `.env.prod`, puis `up -d api` (et les tâches) pour `mf_app` ; rien à redémarrer pour `mf_owner`.
3. Vérifier `/api/v1/ready` et l'audit (contrôle des rôles `mf_owner`/`mf_app` non super-utilisateurs).
4. Retour arrière : `\password` avec l'ancienne valeur, puis l'ancienne valeur dans `.env.prod`.

## Clé de chiffrement MFA (`MF_MFA_ENCRYPTION_KEY`) — deux temps

L'application accepte une **ancienne clé en lecture seule** (`MF_MFA_ENCRYPTION_KEY_PREVIOUS`) : tout ce qui a été
chiffré avant reste lisible, tout ce qui est chiffré après l'est par la nouvelle clé.

1. **Ouvrir la rotation** : dans `.env.prod`, copier la clé actuelle dans `MF_MFA_ENCRYPTION_KEY_PREVIOUS`, puis
   remplacer `MF_MFA_ENCRYPTION_KEY` par une nouvelle clé
   (`python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`). Sauvegarder les
   deux dans le coffre. Redémarrer l'API et les tâches. Les seconds facteurs et les codes de récupération
   continuent de fonctionner.
2. **Rechiffrer** : `docker compose -p minefleet … run --rm --no-deps api minefleet reseal-mfa-secrets` (simulation,
   comptes seulement), puis la même commande avec `--apply`. Chaque société modifiée reçoit un événement d'audit
   `security.mfa_key_rotated` (nombre de secrets rechiffrés, jamais de valeur). Code de sortie 3 : des secrets
   sont illisibles par les deux clés (valeur altérée ou clé perdue) ; les comptes concernés passent par la
   réinitialisation du second facteur.
3. **Codes de récupération** : ils sont hachés avec un poivre dérivé de la clé et ne peuvent pas être rechiffrés.
   Tant que `MF_MFA_ENCRYPTION_KEY_PREVIOUS` est en place, les anciens codes restent valables. Demander aux
   utilisateurs de régénérer leurs codes (le nombre de comptes concernés est affiché par la commande), puis
   fixer une date de fin.
4. **Fermer la rotation** : vider `MF_MFA_ENCRYPTION_KEY_PREVIOUS`, redémarrer, vérifier une connexion avec second
   facteur. Les codes de récupération non régénérés ne valent plus : le compte passe par la réinitialisation.
5. **Retour arrière** avant la fermeture : remettre l'ancienne clé en `MF_MFA_ENCRYPTION_KEY` et la nouvelle en
   `MF_MFA_ENCRYPTION_KEY_PREVIOUS` ; tout reste lisible.

Ce mécanisme est couvert par `backend/tests/test_mfa_key_rotation.py` : accès conservé pendant la rotation,
rechiffrement en simulation puis appliqué, lecture avec la seule nouvelle clé, codes anciens refusés après la
fermeture, refus d'une ancienne clé identique à la nouvelle.

## Non couvert

- Aucune rotation n'a encore été **exécutée** sur la recette : à faire avec accord, puis consigner la preuve.
- Pas de coffre de secrets centralisé (Vault ou équivalent) : la phase 6 le prévoit ; ce document reste la
  procédure tant qu'il n'existe pas.
- Pas de rotation automatique ni d'alerte d'ancienneté des secrets.
