# ADR-003 — Authentification et sessions

- **Statut** : Proposé
- **Date** : 2026-10-25
- **Références** : `docs/00_SOCLE_CADRAGE.md` (H6, H7), skill `security-review`

## 1. Contexte
Utilisateurs : bureaux (web) et terrain (mobile/PWA, réseau faible ou intermittent, appareils partagés possibles). Beaucoup de conducteurs n'ont pas de compte (H6). Il faut une solution simple pour le MVP, sans service tiers payant, qui ne bloque pas une évolution vers SSO/MFA.

## 2. Options

| Critère | A. JWT d'accès court + refresh rotatif | B. Session serveur, cookie httpOnly | C. OIDC externe (Keycloak, etc.) |
|---|---|---|---|
| Complexité MVP | Moyenne (rotation, détection de réutilisation) | Faible | Élevée (service à héberger, thèmes FR, ops) |
| Révocation immédiate | Partielle (jeton court + liste de refresh) | Immédiate | Selon config |
| Web (XSS/CSRF) | Stockage du jeton à gérer (XSS si localStorage) | httpOnly + SameSite ; CSRF à traiter | Idem A/B selon client |
| Mobile / PWA / réseau faible | Bon : stateless, tolère les coupures | Cookie OK en PWA, mais dépend du navigateur | Bon, mais redirections lourdes en réseau faible |
| Offline | Le jeton expire hors ligne : file d'attente à rejouer à la reconnexion | Idem | Idem |
| SSO entreprise / MFA | À construire | À construire | Natif |
| Dépendance / coût | Aucune | Aucune (table de sessions en base) | Service supplémentaire à exploiter |

## 3. Décision (recommandation MVP)
**Option A modifiée, avec refresh en cookie** : 
- **Jeton d'accès** JWT court (durée à arbitrer, ordre de grandeur quelques minutes à un quart d'heure), signé asymétriquement ou HMAC fort, contenant `sub`, `tenant_id`, `jti`, `session_id`, sans données sensibles. Conservé **en mémoire** côté web (pas de localStorage).
- **Refresh token** opaque, aléatoire, **rotatif à usage unique**, stocké haché en base (`auth_session`), livré en cookie `HttpOnly; Secure; SameSite=Lax/Strict`, chemin restreint à l'endpoint de refresh. Réutilisation d'un refresh déjà consommé -> révocation de toute la famille de session + audit.
- **Rôles et portées lus en base** à chaque requête sensible (ou cache court) plutôt que figés dans le jeton, pour qu'un retrait de rôle prenne effet rapidement.
- **Protection CSRF** : l'API n'accepte l'authentification que par en-tête `Authorization` ; seul l'endpoint de refresh utilise le cookie (SameSite + vérification d'`Origin`).
- Si l'équipe préfère la simplicité maximale côté web, l'option B reste acceptable pour le web seul ; le choix A est retenu pour l'homogénéité web/mobile/PWA.
- **OIDC (C)** : non retenu au MVP ; l'architecture isole l'authentification dans le module `identity` derrière un port `AuthProvider` pour brancher OIDC plus tard (SSO client grand compte).

### 3.1 Mots de passe
- **argon2id** (bibliothèque `argon2-cffi`), paramètres mémoire/temps/parallélisme calibrés sur l'environnement cible et revus périodiquement (valeurs à mesurer, aucune valeur supposée ici) ; sel unique géré par la bibliothèque ; rehash transparent si paramètres obsolètes.
- Politique : longueur minimale privilégiée à la complexité, vérification contre une liste de mots de passe courants, pas de rotation forcée périodique sans incident.
- Limitation de débit et verrouillage progressif par compte et par IP ; messages d'erreur génériques (pas d'énumération de comptes) ; journalisation des échecs (sans mot de passe).
- Comptes créés par invitation/jeton à usage unique, pas de mot de passe initial partagé. Aucun secret en dur.

### 3.2 MFA (ultérieure)
TOTP (RFC 6238) en premier, obligatoire pour `PLATFORM_ADMIN` et `TENANT_ADMIN` dès sa disponibilité ; codes de secours ; WebAuthn envisageable ensuite. SMS écarté par défaut (fiabilité et coût réseau à valider localement). Le modèle `auth_session` prévoit déjà un niveau d'assurance (`amr`).

### 3.3 Contraintes réseau faible / mobile
- Rotation du refresh **tolérante aux coupures** : fenêtre de grâce courte (réponse de refresh perdue) permettant de rejouer le refresh précédent une fois avec le même identifiant de requête, sans déclencher la détection de vol.
- Jetons d'accès renouvelés en arrière-plan avant expiration ; en cas d'échec réseau, la saisie reste en file locale (voir `docs/INTEGRATION_GPS_OFFLINE.md`) et n'est rejouée qu'avec un jeton valide ; l'identité de l'auteur est celle de la session, vérifiée à la synchronisation.
- Durée de vie maximale de session mobile à arbitrer (équilibre sécurité / confort terrain) ; déconnexion à distance depuis l'administration en cas de perte de l'appareil.
- Appareils partagés : accès par PIN local envisageable plus tard, jamais sans compte serveur ; hors périmètre MVP.
- Payloads d'authentification minimaux, compression activée, pas de redirections multiples.

## 4. Conséquences
- (+) Aucune dépendance externe ; adapté web et mobile ; révocation par famille de sessions.
- (−) Implémentation sensible (rotation, réutilisation, cookies) : nécessite revue sécurité et tests dédiés (rejeu, vol de refresh, expiration, horloge).
- (−) Le jeton court ne s'invalide pas instantanément : compensé par durée courte et vérification des rôles en base.
- Audit : connexion, échec, refresh anormal, révocation, changement de mot de passe sont des événements d'audit (ADR-005).

## 5. Points à valider
- Durées de vie des jetons et de session mobile.
- Exigence client de SSO (Microsoft Entra, Google) ou OIDC dès le lot 1.
- Politique MFA et canal (TOTP vs autre) selon équipement terrain.
- Hébergement : cookies `Secure` imposent HTTPS de bout en bout, y compris en recette.
- Rien n'a été implémenté ni testé.
