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

## 3. Revue indépendante (agent security-engineer)
Lancée sur la PR, **interrompue** par une limite d'usage de l'API avant son rapport : à relancer ; ce document sera complété. **Ne pas fusionner la PR avant ce rapport.**

## 4. Vérifications exécutées
ruff, mypy strict, `pytest` **1505 passed** (couverture 93,1 %), tests d'authentification avec cookies `Secure`, `tests_migrations`, Vitest 16, Playwright 10.
