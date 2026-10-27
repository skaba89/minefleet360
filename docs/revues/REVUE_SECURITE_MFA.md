# Revue sécurité — double authentification TOTP (PR #8, D-40)

> Date : 2026-10-27. Objet : `backend/app/core/{totp,secretbox,security}.py`, `backend/app/identity/{mfa_service,auth_service,router}.py`, `backend/app/authz/dependencies.py`, migration `0011`, interface (connexion, page Sécurité).

## 1. Revue automatique de commit (outil security-guidance)
| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| MFA-A-01 | Moyenne | `POST /me/mfa/disable` vérifiait le mot de passe avant tout contrôle de limite : un jeton d'accès volé permettait de deviner le mot de passe sans plafond | **Corrigé** : limite vérifiée d'abord ; mot de passe ou code faux → même erreur `INVALID_CREDENTIALS` (pas d'oracle) ; test |
| MFA-A-02 | Moyenne | Le défi de second facteur restait valable 5 min après un changement de mot de passe ; pas de limite par adresse IP sur `/auth/mfa/verify` | **Corrigé** : empreinte du hachage du mot de passe dans le défi (`pwv`), comparée en temps constant ; limiteur `source` (IP) appliqué ; test `test_challenge_is_void_after_password_change` |
| MFA-A-02b | — | Jeton de défi à usage unique (stockage du `jti`) | **Non retenu** : l'anti-rejeu TOTP (pas déjà accepté refusé), l'usage unique des codes de récupération et la limite par compte et par IP couvrent le risque ; un défi réutilisé n'apporte rien sans un nouveau code valide |

## 2. Défaut découvert par la CI
Test `test_login_requires_second_factor_and_refuses_replay` : en CI, le cookie de session est `Secure` (`MF_COOKIE_SECURE` par défaut) et n'était pas renvoyé par le client de test en `http`. Défaut du test seulement (le code se comporte comme attendu) ; corrigé en transmettant le cookie explicitement, et les tests d'authentification sont rejoués localement avec `MF_COOKIE_SECURE=true`.

## 3. Revue indépendante (agent security-engineer distinct, lecture du code)
Aucun constat critique ni élevé. Contournement du second facteur, confusion de jetons, défi d'un autre compte ou tenant, anti-rejeu, chiffrement, IDOR du retrait, CSRF et stockage côté web : vérifiés sans problème. Choix de ne pas stocker le `jti` du défi : **approuvé**.

| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| MFA-R-01 | Moyenne | Enrôlement possible avec la seule session (jeton d'accès volé, ou mot de passe d'un compte sensible non encore enrôlé) : l'attaquant enrôle son téléphone et exclut le titulaire | **Corrigé** : mot de passe exigé pour `POST /me/mfa/setup` (essais limités) ; **e-mail d'alerte** à l'utilisateur à chaque activation, désactivation et retrait par l'administrateur. Résiduel : un attaquant connaissant le mot de passe d'un compte jamais enrôlé peut encore enrôler avant le titulaire, mais celui-ci est prévenu par e-mail ; enrôlement par lien e-mail à envisager avant production |
| MFA-R-02 | Moyenne | Course : des essais parallèles passaient tous le contrôle de limite avant le premier échec enregistré | **Corrigé** : contrôle de limite sous le verrou de ligne de l'utilisateur (vérification à la connexion et confirmation d'enrôlement) ; test à 12 essais simultanés |
| MFA-R-03 | Faible | Codes de récupération hachés SHA-256 sans poivre (≈ 50 bits) : retrouvables par force brute en cas de fuite de la base | **Corrigé** : HMAC-SHA256 avec un poivre dérivé de `MF_MFA_ENCRYPTION_KEY` (hors base) |
| MFA-R-04 | Faible | Retrait du second facteur par l'administrateur sans nouvelle preuve ni notification | **Partiellement corrigé** : la cible est prévenue par e-mail ; exiger un code frais de l'administrateur reste à faire (ouvert) |
| MFA-R-05 | Faible | (a) un détenteur du mot de passe peut bloquer le second facteur du titulaire 15 min ; (b) limiteur IP partagé avec la connexion | (a) **Accepté** (compromis anti-force brute, exige le mot de passe) ; (b) **sans objet** : l'IP vient de `request.client`, réécrite seulement par les proxys de confiance (`--forwarded-allow-ips`, R3) |
| MFA-R-06 | Faible | Un code du pas suivant accepté repousse `last_step` : code courant refusé jusqu'à 60 s | **Accepté** (tolérance de dérive voulue) |
| MFA-R-07 | Faible | Clé validée seulement à l'usage ; pas d'identifiant de clé | **Corrigé** pour la validation (décodage et longueur au démarrage) ; rotation de clé (`key_id`) : ouvert |
| MFA-R-08 | Info | Liste des rôles soumis à l'obligation | **À arbitrer** (C-03) : défaut D-40 conservé |
| MFA-R-09 | Info | Commande `reset-platform-mfa` sans identité de l'exécutant | **Corrigé** : utilisateur système consigné dans le motif d'audit |

## 4. Vérifications exécutées
ruff, mypy strict, `pytest` **1509 passed** (couverture 93 %), tests d'authentification avec cookies `Secure`, `tests_migrations`, Vitest 16, Playwright 10.
