# Revue de sécurité du code — tranche 1a — MINEFLEET 360

> Date : 2026-10-26. Branche `main`. Périmètre : `backend/app` (core, authz, organization, identity, audit), migrations 0001-0004, `authz_matrix.yaml`, `infra/deploy/`, `infra/db/init/`, CI. Les fichiers de la tranche 1b (`0005_fleet.py`, `0006_workforce.py`, `app/fleet`, `app/workforce`) sont **hors périmètre**.
> Auteur : security-engineer. Référentiel de préséance : `DECISIONS_A_ARBITRER.md`.

## 0. Méthode et limites

**Testé (exécuté)** : script d'attaque local (hors dépôt) exécuté dans le conteneur `api` contre une base jetable `minefleet_sec` (créée puis supprimée ; ni `minefleet` ni `minefleet_test` touchées). Deux tenants fictifs, un PLATFORM_ADMIN fictif, comptes HR/DISPATCHER/TENANT_ADMIN. Les migrations ont été appliquées jusqu'à `head` dans cette base jetable (ce qui inclut 0005/0006 de la 1b). Un premier essai à `0004` a échoué parce que le code de la 1b (`create_tenant` appelle `seed_tenant_catalog`) est déjà dans l'arbre de travail : sans lien avec la 1a, non relancé autrement.
Aussi exécuté : `pip-audit` (dans un conteneur éphémère) sur l'environnement installé de l'image dev.
**Non exécuté** : la suite de 674 tests (elle réinitialise `minefleet_test` par downgrade/upgrade et un autre agent l'utilisait en parallèle ; l'arbre contient en plus des migrations 1b en cours). Je ne confirme donc ni ne contredis le chiffre « 674 passent ».
**Lu seulement** : migrations et RLS (analyse du SQL, pas de tentative d'écriture directe en SQL en tant que `mf_app`), concurrence (verrous, rejeu simultané de refresh), Caddy / compose / sauvegardes, CI. Chaque constat ci-dessous indique « testé » ou « lu ».

Timings : médiane de 7 requêtes, client de test en mémoire, machine de dev. Ils montrent un écart reproductible, pas un chiffre réseau.

## 1. Synthèse

| ID | Gravité | Sujet | Statut |
|----|---------|-------|--------|
| SEC-01 | élevée | Dépendances vulnérables (starlette 0.41.3, PyJWT 2.10.1) ; `pip-audit` de la CI échouera | testé (pip-audit) |
| SEC-02 | moyenne | Oracle temporel d'existence de compte (login et reset-request) | testé |
| SEC-03 | moyenne | Verrouillage anonyme d'un compte cible (login) et de sa réinitialisation | testé |
| SEC-04 | moyenne | PLATFORM_ADMIN sans MFA, point d'entrée exposé sur Internet dans la démo | lu |
| SEC-05 | moyenne | Portée SITE non appliquée à `GET /users` (HR de site voit tous les comptes) | testé |
| SEC-06 | moyenne | Inondation du journal d'audit par des 403 (écriture non limitée) | testé |
| SEC-07 | faible | Limiteur en mémoire par processus, 2 workers en démo, IP via `--forwarded-allow-ips *` | lu |
| SEC-08 | faible | Capture d'e-mails : liens à usage unique en clair sur disque, sans garde d'environnement | lu |
| SEC-09 | faible | `reset-credentials` administrateur ne révoque ni sessions ni mot de passe courant | testé |
| SEC-10 | faible | `X-Request-ID` fourni par le client écrit tel quel dans l'audit | testé |
| SEC-11 | faible | FK simples `granted_by` / `revoked_by` / `actor_user_id` ; identifiant du PLATFORM_ADMIN visible dans le tenant client | testé / lu |
| SEC-12 | faible | OpenAPI et `/docs` publics via Caddy ; pas de CSP | testé |
| SEC-13 | faible | CSRF du cookie de refresh : repose sur SameSite=Strict (en-tête Origin absent accepté) ; `MF_ALLOWED_ORIGINS` vide casse le refresh navigateur | testé |
| SEC-14 | faible | Base `minefleet_test` créée aussi dans la démo ; durcissement JWT (iss/aud/kid) | lu |
| SEC-15 | faible | Sauvegardes : non chiffrées, sur la même machine, sans test de restauration ; rétention audit/IP non définie ; pas de tâche de création des partitions d'audit | lu |

Aucun constat critique. Aucune fuite inter-tenant n'a été obtenue (voir section 3).

## 2. Constats

### SEC-01 — Dépendances vulnérables — élevée (testé)
- Fichiers : `backend/pyproject.toml:7` (`fastapi==0.115.6` impose `starlette 0.41.3`), `backend/pyproject.toml:15` (`pyjwt==2.10.1`), `.github/workflows/ci.yml:59` (`pip-audit --skip-editable`).
- Reproduction : `docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps -e MF_ENV=test api sh -c "pip install pip-audit && python -m pip_audit --skip-editable"`. Résultat : `starlette 0.41.3` signalé par sept avis (PYSEC-2026-248, -249, -161, -1941, -1942, -2280, -2281 ; correctifs de 0.47.2 à 1.3.1) ; `pyjwt 2.10.1` signalé (dont PYSEC-2026-120/CVE-2026-32597, `crit` non validé, corrigé en 2.12.0, et plusieurs avis corrigés en 2.13.0) ; `pytest 8.3.4` et `pip` (dev/outillage).
- Impact : starlette est la couche HTTP de l'API exposée sur Internet dans la démo. Je n'ai pas lu le détail de chaque avis starlette ni établi d'exploitabilité ; la gravité est donnée par l'exposition. Côté PyJWT, l'application fixe `algorithms=["HS256"]` et n'utilise ni JWKS ni JWS détaché : les avis PyJWT listés semblent peu exploitables ici (à confirmer en les relisant), mais la mise à niveau est triviale.
- Conséquence directe : l'étape « Audit des dépendances » de la CI échouera dès le premier `push` (la CI n'a pas encore tourné, D-24).
- Correction : relever `fastapi` (starlette corrigé), `pyjwt>=2.13`, `pytest`, puis relancer la suite complète et `pip-audit` ; décider d'une politique (échec CI sur sévérité, délai de mise à jour). Ne pas déployer l'image démo reconstruite sans cela.

### SEC-02 — Oracle temporel d'existence de compte — moyenne (testé)
- Fichiers : `backend/app/identity/auth_service.py:149-175` (le chemin d'échec d'un compte **connu** écrit `failed_login_count`, une ligne d'audit et fait un `commit` ; le chemin « espace inconnu » ou « e-mail inconnu » n'écrit rien) ; `auth_service.py:364-404` et `identity/router.py:183-187` (`reset-request` : émission de jeton, audit, commit et envoi d'e-mail seulement si le compte existe).
- Reproduction (médianes sur 7 essais) : login, espace inconnu 92,7 ms ; espace connu + e-mail inconnu 92,7 ms ; espace connu + compte existant + mauvais mot de passe 108,1 ms (+15 ms, soit +16 %, reproductible sur deux exécutions). `reset-request` : compte existant 20,6 ms ; e-mail inconnu 13,8 ms ; espace inconnu 12,5 ms. Les réponses (401 identique, 202 identique) sont, elles, bien uniformes ; le hachage factice neutralise le coût argon2 mais pas le coût d'écriture.
- Scénario : un attaquant qui connaît le code d'espace (affiché dans les e-mails, URL de l'application) mesure la latence par adresse e-mail et déduit quelles adresses ont un compte. Limité par le limiteur par IP (50 échecs / 15 min) mais suffisant pour trier une liste de 50 adresses par fenêtre. L'e-mail du personnel est une donnée personnelle (D-15).
- Correction : faire le même travail d'écriture dans tous les cas (par exemple toujours écrire l'événement d'audit d'échec, avec `entity_id` nul, y compris pour espace inconnu, dans une transaction détachée), et sortir l'émission du jeton et l'envoi d'e-mail de la requête (tâche de fond après réponse) pour `reset-request`. Ajouter un test de non-régression sur le rapport des latences (seuil large) ou au moins un test de structure (mêmes appels).

### SEC-03 — Verrouillage anonyme d'un compte cible — moyenne (testé)
- Fichiers : `auth_service.py:132-136` (clé `kind:code:email`, 5 échecs, 15 min) ; `auth_service.py:369-374` (la clé par couple (espace, e-mail) du `reset-request` compte **chaque demande**).
- Reproduction : 5 `POST /auth/login` avec un mauvais mot de passe pour `admin@espace`, puis un login avec le **bon** mot de passe → `429 RATE_LIMITED` (observé). De même, 6 `reset-request` pour le même couple → le 6e renvoie `429` (observé), donc le vrai utilisateur ne peut plus demander de réinitialisation pendant 15 min.
- Scénario : un anonyme qui connaît un code d'espace et l'e-mail de l'administrateur (souvent déductible) l'empêche de se connecter en continu (5 requêtes toutes les 15 min). Conséquence aggravée pour le TENANT_ADMIN, seul à pouvoir gérer comptes et rôles.
- Correction : clé de verrouillage composée (couple + IP source) en plus du seuil par couple plus haut, délai progressif plutôt que blocage dur, ou verrouillage qui n'empêche pas l'utilisateur déjà reconnu (appareil/cookie de confiance). Alerter l'administrateur de la plateforme sur les rafales. Pour `reset-request`, ne compter que par IP et appliquer un plafond par couple beaucoup plus élevé.

### SEC-04 — PLATFORM_ADMIN sans MFA, exposé publiquement dans la démo — moyenne (lu)
- Fichiers : `authz_matrix.yaml:239-246` (routes publiques `/auth/platform/login`), `infra/deploy/Caddyfile:12-13` (`reverse_proxy /api/*`, aucune restriction), `DECISIONS_A_ARBITRER.md` C-03 (MFA reporté après le lot 1).
- Le compte de plateforme (création de tenants, suspension, aucun accès aux données métier par construction : vérifié, voir section 3) est protégé par un seul mot de passe, sur un point d'entrée joignable depuis Internet, avec un limiteur en mémoire (SEC-07). Sa compromission permet de créer des tenants et d'y provisionner un administrateur dont on reçoit l'invitation, et de suspendre tous les clients (déni de service).
- Correction : restreindre `/api/v1/auth/platform/*` et `/api/v1/platform/*` par liste d'IP ou accès VPN dans Caddy tant que la MFA n'est pas livrée ; mot de passe long généré ; ne pas créer le compte avant la première démonstration réelle. Livrer la MFA TOTP de C-03 avant tout pilote.

### SEC-05 — Portée SITE non appliquée à la liste des comptes — moyenne (testé)
- Fichiers : `authz_matrix.yaml:125-132` (`identity.user.read`, `site_bound: false`, HR `[TENANT, SITE]`) ; `backend/app/identity/service.py:137-147` (`list_users` ne filtre pas sur `auth.scope`) ; `identity/service.py:150-151` (`get_user` idem).
- Reproduction : un HR attribué au site S1 (portée SITE) appelle `GET /api/v1/users` → `200`, `total = 3` : tous les comptes du tenant, y compris les administrateurs et les comptes d'autres sites, avec nom, statut et dernière connexion (e-mail et téléphone sont bien masqués : vérifié). `GET /users/{id}` d'un compte hors du site → `200` également.
- Écart : D-05 exige `404` pour une ressource hors portée de site. Tant que `site_bound` est faux pour cette permission, la matrice assume la lecture tenant-wide ; si le rôle HR de site doit être réellement limité (MATRICE_RBAC §« HR » à relire : la case est `👁²` sans précision de portée), c'est un écart de conception. Le risque est d'abord la fuite d'annuaire interne et de `last_login_at` (traçabilité du personnel).
- Correction : soit restreindre la permission aux attributions `TENANT` pour HR (retirer `SITE` de la ligne), soit filtrer `list_users` / `get_user` sur les sites de l'utilisateur (comptes ayant une attribution dans ces sites) avec `404` hors portée, et documenter. Ajouter un test généré depuis le YAML pour chaque permission de lecture avec portée SITE.

### SEC-06 — Inondation du journal d'audit par des refus — moyenne (testé)
- Fichiers : `backend/app/authz/dependencies.py:113-129` (chaque 403 appelle `record_detached` : nouvelle session, nouvelle transaction, commit) ; `backend/app/audit/contracts.py:75-90` (si l'écriture d'audit échoue, l'exception est relancée → 500) ; `auth_service.py:163-174` (échec de login d'un compte connu → ligne d'audit).
- Reproduction : un DISPATCHER fait 20 `POST /users` → 20 `403`, le journal du tenant grossit de **20 lignes** (`audit rows grew by 20`). Aucune limite par utilisateur/session. Un jeton valide de rôle faible suffit à écrire sans borne dans le journal du tenant (jusqu'à saturer l'espace disque de la base et noyer les événements utiles), la table n'étant jamais purgée (C-09) et `mf_app` ne pouvant pas supprimer.
- Correction : plafonner les refus audités (par exemple 1 événement agrégé par utilisateur+permission+minute, compteur dans `details`), limiter le débit global des requêtes authentifiées, et ne pas transformer un échec d'écriture d'audit détachée en 500 pour un refus (le refus doit rester un refus). Définir la rétention (C-09) avant production.

### SEC-07 — Limiteur par processus et provenance de l'IP — faible (lu)
- Fichiers : `backend/app/core/ratelimit.py:1-6` (limite connue, QA-32) ; `infra/deploy/docker-compose.demo.yml:42-43` (`--workers 2 --proxy-headers --forwarded-allow-ips "*"`) ; `main.py:45-50` (`request.client.host`).
- Avec 2 workers, chaque processus a ses propres compteurs : le plafond réel est doublé et variable, et un redémarrage remet tout à zéro. `--forwarded-allow-ips "*"` n'est acceptable que parce que le port 8000 n'est pas publié et que Caddy remplace `X-Forwarded-For` par l'adresse réelle (comportement par défaut de Caddy sans `trusted_proxies` : lu dans sa documentation, non testé ici). Si un jour le port 8000 est exposé, l'IP devient forgeable et le limiteur par IP est contourné.
- Correction : un seul worker en démo ou limiteur partagé (Redis/PostgreSQL) avant pilote ; remplacer `*` par l'adresse du réseau Docker de Caddy.

### SEC-08 — Capture d'e-mails : jetons en clair sur disque — faible (lu)
- Fichiers : `backend/app/core/email.py:25-36` (écrit `to`, `subject`, `body` avec le lien `#token=<tenant>.<id>.<secret>` en JSON, permissions par défaut, jamais purgé) ; `main.py:71` (adaptateur par défaut quel que soit `MF_ENV`) ; `infra/deploy/docker-compose.demo.yml:27,51` ; `docs/DEPLOIEMENT_OVH_DEMO.md:32`.
- Dans la démo, toute personne pouvant lire le volume `mail-capture` (hôte, sauvegarde du volume, autre conteneur) obtient des liens d'invitation et de réinitialisation valides (7 jours / 1 h) et peut prendre le compte, y compris le premier TENANT_ADMIN d'un tenant. Aucune garde n'empêche d'utiliser ce port en `MF_ENV=production`.
- Correction : faire échouer le démarrage si `MF_ENV=production` et l'adaptateur de capture ; écrire les fichiers en `0600` ; purger après consommation ou après expiration ; ne jamais inclure le dossier dans une sauvegarde hors machine.

### SEC-09 — Réinitialisation administrateur sans révocation — faible (testé)
- Fichier : `backend/app/identity/service.py:292-315`.
- Reproduction : le TENANT_ADMIN lance `reset-credentials` pour un utilisateur actif ; le jeton d'accès de l'utilisateur reste valide (`GET /me` → 200) et son ancien mot de passe permet toujours de se connecter (200). Les sessions ne sont révoquées qu'à la confirmation (`confirm_password_reset`, qui, elle, révoque : lu).
- Scénario : l'administrateur suspecte une compromission et déclenche la réinitialisation ; l'attaquant garde sa session tant que l'utilisateur légitime n'a pas cliqué sur le lien.
- Correction : proposer une option `revoke_sessions` (par défaut vraie pour cette action administrative) ou exiger `deactivate` pour couper l'accès immédiatement ; documenter le comportement.

### SEC-10 — `X-Request-ID` contrôlé par le client — faible (testé)
- Fichiers : `backend/app/main.py:38-42, 79` ; `audit/contracts.py:143`.
- Reproduction : `GET /health` avec `X-Request-ID: 11111111-1111-4111-8111-111111111111` renvoie la même valeur ; elle est ensuite écrite comme `request_id` dans les événements d'audit. Un utilisateur peut donc choisir ou réutiliser l'identifiant de corrélation (collision avec la requête d'un autre utilisateur, brouillage de l'investigation).
- Correction : générer un identifiant serveur, conserver l'identifiant client dans un champ séparé (`client_request_id`, non fiable).

### SEC-11 — Clés étrangères simples et identifiant de plateforme visible côté client — faible (testé / lu)
- Fichiers : `backend/alembic/versions/0003_identity.py:71-72` (`fk_ura__granted_by`, `fk_ura__revoked_by` référencent `user_account(user_account_id)` sans `tenant_id`) ; `0004_audit.py:41` (`fk_audit_event__actor`) ; `backend/app/organization/service.py:74` (`granted_by=auth.user_id`, utilisateur de la plateforme).
- Lu : au niveau SQL, ces colonnes peuvent référencer un utilisateur d'un autre tenant (les contrôles de FK ignorent la RLS) ; l'API les renseigne uniquement depuis le principal authentifié, donc je n'ai pas de chemin d'exploitation. Défense en profondeur seulement.
- Testé : après `POST /platform/tenants`, `granted_by` de la première attribution du tenant client est l'identifiant du PLATFORM_ADMIN (comparaison vraie), visible par le TENANT_ADMIN via `GET /role-assignments`, et l'événement `tenant.provision` du tenant porte le même `actor_user_id`. Fuite d'un UUID opaque, sans autre donnée.
- Correction : clés composites `(tenant_id, user)` pour `revoked_by` ; pour `granted_by` et l'acteur d'audit, soit les conserver simples et documenter l'exception « acteur plateforme », soit les remplacer par `actor_kind = 'SYSTEM'`/pseudonyme côté tenant.

### SEC-12 — Documentation de l'API publique, pas de CSP — faible (testé)
- Fichiers : `backend/app/main.py:65-66` ; `infra/deploy/Caddyfile:4-14`.
- Reproduction : `GET /api/v1/openapi.json` et `/api/v1/docs` → `200` sans authentification (et via Caddy, `/api/*` est entièrement proxifié). La page `/docs` charge ses ressources depuis un CDN, sans `Content-Security-Policy`. Cela expose la cartographie complète des routes et le `x-permission` de chacune.
- Les en-têtes présents côté application sont `Cache-Control: no-store` et `X-Content-Type-Options: nosniff` ; Caddy ajoute HSTS (sans `includeSubDomains`), `X-Frame-Options`, `Referrer-Policy`.
- Correction : `docs_url=None, openapi_url=None` hors `local/test` (ou protégés) ; ajouter `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` sur les réponses d'API.

### SEC-13 — CSRF du cookie de refresh — faible (testé)
- Fichiers : `backend/app/identity/router.py:53-56, 137-148, 151-162, 63-71`.
- Testé : `Origin: https://evil.example` → `401` ; aucun en-tête `Origin` avec le cookie présent → `200` (refresh accepté). Le cookie est `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` : correct. La protection réelle est donc SameSite=Strict ; l'en-tête `Origin` absent est toléré (clients non navigateur), ce qui est acceptable mais doit être su (une page d'un sous-domaine « same-site » mal sécurisé pourrait déclencher un refresh ou un logout, sans lire la réponse, donc impact faible).
- Fonctionnel : `MF_ALLOWED_ORIGINS` vaut `""` par défaut en démo (`docker-compose.demo.yml:26`) ; avec une liste vide, tout refresh navigateur portant un `Origin` est refusé (`401`). À renseigner avec l'origine publique.
- Correction : documenter ; envisager un en-tête personnalisé obligatoire (`X-Requested-With`) ou la vérification de `Sec-Fetch-Site`.

### SEC-14 — Surface de la démo et durcissement JWT — faible (lu)
- `infra/db/init/00_bootstrap.sh:20` crée aussi `minefleet_test` sur la base de démo (mêmes rôles, jamais utilisée) ; la supprimer en démo.
- `backend/app/core/security.py:253-263` : le jeton d'accès n'a ni `iss`, ni `aud`, ni `kid` (pas de rotation de clé sans invalidation de tous les jetons) ; durée de 15 min et vérification de session en base à chaque requête (révocation immédiate : testé, voir section 3) limitent le risque.

### SEC-15 — Sauvegardes, rétention, partitions — faible (lu)
- `infra/deploy/backup.sh` : dump `pg_dump -Fc` quotidien, 7 exemplaires, sur la même machine que la base, non chiffré, aucun test de restauration documenté, le script tourne avec `-U postgres` (superutilisateur). Le dump contient hachages de mots de passe, IP et agents utilisateur d'audit.
- `backend/alembic/versions/0004_audit.py:92` : `ensure_audit_partitions(12)` n'est appelé qu'à la migration ; aucune tâche ne crée les mois suivants. Au-delà de 12 mois, les événements vont dans la partition `DEFAULT` (l'écriture continue de fonctionner, mais sans partitionnement mensuel, ce qui rend la rétention par détachement de partition impossible). La rétention des IP, agents utilisateur et sessions (C-09) n'est pas implémentée.
- Correction : chiffrer (par exemple `age`/GPG) avant tout transfert, tester la restauration, rôle de sauvegarde dédié en lecture ; planifier `ensure_audit_partitions` (cron applicatif ou opération documentée) ; fixer la durée de conservation avant production.

## 3. Vérifié sans constat

Testé (exécution locale, base jetable) :
- **Isolation inter-tenant (IDOR)** : avec un TENANT_ADMIN du tenant A, `GET`/`PATCH`/`deactivate`/`reset-credentials` d'un utilisateur de B, `GET`/`PATCH` d'un site de B, lecture d'un événement d'audit de B, révocation d'une attribution de B → tous `404 NOT_FOUND`, **identique** à un identifiant aléatoire. Attribution d'un rôle à un utilisateur de B, avec un site de B, avec un site ou utilisateur inexistant → toujours `422 REFERENCE_NOT_FOUND` identique (pas d'oracle d'existence inter-tenant). Filtre d'audit `actor_user_id=<utilisateur de B>` → total 0.
- **Escalade** : auto-attribution → `422 SELF_ROLE_CHANGE_FORBIDDEN` ; attribution ou invitation `PLATFORM_ADMIN` par un TENANT_ADMIN → `422 ROLE_NOT_ASSIGNABLE` ; HR s'attribuant `TENANT_ADMIN` → `403` ; DISPATCHER `PATCH /tenant` → `403` ; champ `tenant_id` dans un corps → `422` (schémas stricts).
- **PLATFORM_ADMIN sans accès métier** : `GET /users`, `/sites`, `/audit-events` avec jeton de plateforme → `403` ; un TENANT_ADMIN sur `/platform/tenants` → `403`.
- **Ordre des codes** : 401 sans jeton ; 403 avant 422 et avant 404 (DISPATCHER sur un corps invalide ou un identifiant inexistant → 403) ; admin : `404` avec `If-Match`, `422 IF_MATCH_REQUIRED` sans.
- **JWT** : mauvaise clé → 401 ; `alg: none` → 401 ; jeton signé avec la bonne clé mais `sid` d'une session d'un autre tenant, ou `tid` d'un autre tenant → 401 (la session est revérifiée en base sous RLS à chaque requête).
- **Cycle de vie** : désactivation d'un utilisateur → son jeton d'accès devient `401` immédiatement ; suspension d'un tenant → ses jetons deviennent `401` immédiatement ; deux logins successifs donnent deux sessions distinctes (pas de fixation).
- **Refresh** : cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` ; origine étrangère refusée (voir SEC-13 pour la nuance).
- **Injection** : code d'espace `x' OR '1'='1` → `401` uniforme ; filtre d'audit `' OR 1=1--` → 0 résultat (aucun SQL construit par concaténation : `grep` des `text(`/f-strings dans `backend/app`, seules des requêtes paramétrées et `set_config`) ; un `display_name` contenant `<script>` est stocké tel quel (l'API renvoie du JSON ; l'échappement est à la charge de l'UI, non évaluée).
- **Masquage** : e-mail et téléphone absents de `GET /users` pour HR (champ absent, pas nul) ; présents pour TENANT_ADMIN ; aucun e-mail dans les `before_data`/`after_data` d'audit du tenant de test.
- **Énumération par réponse** : login (espace inconnu, e-mail inconnu, mot de passe faux) → même `401 INVALID_CREDENTIALS` ; `reset-request` → même `202` (mais voir SEC-02 pour le temps).
- **Limiteur** : 5 échecs → `429 RATE_LIMITED` ; `reset-request` plafonné (voir SEC-03 pour l'effet de bord).

Lu seulement (code et SQL, sans exécution dédiée) :
- **RLS** : `FORCE ROW LEVEL SECURITY` + politique `tenant_id = app.current_tenant_id()` USING/WITH CHECK sur toutes les tables tenant (`apply_tenant_rls`) ; fonction à valeur vide = 0 ligne ; `set_config(..., true)` transactionnel, seul `core/tenancy.py` le pose (test d'architecture présent) ; rôle `mf_app` `NOSUPERUSER NOBYPASSRLS` et contrôle au démarrage (`check_database_role`) ; politique `tenant` : lecture par code de connexion exact limitée à la transaction ; trigger `tg_tenant_guard` empêchant un tenant client de modifier ses champs de gouvernance ; `tenant_id` immuable (trigger).
- **Audit** : `mf_app` n'a que `SELECT, INSERT` sur `audit_event` ; triggers `tg_append_only` sur UPDATE/DELETE/TRUNCATE ; partitions sans droits pour `mf_app` ; données sensibles filtrées (`SENSITIVE_FIELDS`). Absence de chaînage de hash : écart connu (D-16).
- **Jetons à usage unique** : 256 bits, stockés hachés SHA-256 (32 octets contrôlés), comparaison à temps constant, expiration, unicité du jeton ouvert par finalité, révocation à la désactivation et à la réinitialisation ; refresh rotatif avec réutilisation hors fenêtre de grâce → révocation de session et événement d'audit (code lu ; le chemin « rejeu simultané » n'a pas été exercé en concurrence).
- **Mots de passe** : argon2id, hachage factice pour les comptes inconnus, rehash à la connexion, politique de longueur ; changement de mot de passe limité avec révocation des autres sessions.
- **Verrous** : `FOR NO KEY UPDATE` (SQLAlchemy `key_share=True`) et recomptage sous verrou du tenant pour « dernier TENANT_ADMIN » (non testé en concurrence ici).
- **Déploiement** : base non publiée ; `.env.demo` et `backups/` ignorés par Git ; API sans `postgres` ni `mf_owner` ; sauvegardes en `umask 077` ; image Caddy figée ; utilisateur non root dans l'image.
- **Secrets** : aucun secret en dur dans le dépôt (valeurs d'exemple uniquement) ; `MF_JWT_SECRET` ≥ 32 caractères imposé ; je n'ai pas lu `.env`.

## 4. Non couvert

Interface web (absente de la tranche), tests de charge, concurrence (rejeu simultané du refresh, retrait simultané de deux TENANT_ADMIN), configuration réelle du VPS OVH (pare-feu, SSH, mises à jour du système), TLS effectif de Caddy, conformité légale guinéenne (C-08/C-09), exécution de la suite de 674 tests.

## 5. Ordre de correction recommandé

1. SEC-01 (mise à niveau + `pip-audit` vert) avant tout nouveau déploiement de la démo.
2. SEC-04 (restriction d'accès aux routes de plateforme dans Caddy) et SEC-12 (désactiver `/docs` et OpenAPI en démo).
3. SEC-02, SEC-03, SEC-06 (authentification et audit) dans la prochaine tranche de sécurité.
4. SEC-05 : arbitrer la portée de HR (matrice) puis tester.
5. SEC-07 à SEC-15 : planifiés avant pilote ; SEC-08 et SEC-15 avant toute donnée non fictive.
