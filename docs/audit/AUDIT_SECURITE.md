# Audit sécurité

Commit `2e3b803`, 26 octobre 2026. Revue statique spécialisée et reproduction en mémoire du limiteur. Tests DB existants vérifiés dans la CI du même SHA; aucun nouveau test de pénétration externe ni exploitation sur des données réelles.

## Menaces et contrôles

| Menace | Contrôle codé | Limite de vérification |
|---|---|---|
| IDOR entre tenants | FORCE RLS, USING/WITH CHECK, contexte transactionnel; FK composites | CI existante; étendre aux nouveaux modules et migrations peuplées |
| Élévation tenant/site | Principal relu en DB, matrice serveur, scopes et masquage par enregistrement | Revue de code et tests générés; conserver contrôles métier spécifiques |
| Session révoquée | Session/utilisateur/tenant relus, rôles actifs relus | Ancien refresh au-delà d'une rotation non reconnu comme rejeu |
| Vol de mot de passe/token | Argon2id, secrets opaques, cookies HttpOnly/Secure/SameSite Strict | MFA absent; transport email provisoire |
| Altération audit | Écriture transactionnelle, droits append-only et RLS | Pas de scellement cryptographique externe |
| Fuite par exceptions | SQLAlchemy hide_parameters, erreurs normalisées | Configuration des logs PostgreSQL en exploitation à contrôler séparément |

## Anomalies

| ID | Gravité | Fichier et preuve | Impact | Correction proposée |
|---|---|---|---|---|
| SEC-01 | Haute | core/ratelimit.py:18-33 : état mémoire; infra/deploy/docker-compose.demo.yml lance déjà 2 workers | Compteurs indépendants et réinitialisés aux redémarrages, anti-bruteforce affaibli | Stockage partagé atomique avec expiration; tester plusieurs workers et redémarrage |
| SEC-02 | Moyenne | core/ratelimit.py:21-29 : defaultdict crée une clé à chaque lecture, aucune éviction globale | Croissance mémoire sous cardinalité élevée | Ne pas allouer à la lecture, TTL/éviction et limite de cardinalité |
| SEC-03 | Haute avant production | main.py:73 sélectionne FileCaptureEmailSender par défaut; core/email.py:31-34 écrit destinataire et liens secrets sans permissions explicites ni rétention | Captures persistantes de liens d'activation/reset, transport non productif | Transport réel configurable; refuser capture en production, fichiers privés et purge pour démo |
| SEC-04 | Moyenne | identity/auth_service.py:227-259 ne reconnaît que refresh courant/précédent | Après T0→T1→T2, rejeu T0 refusé mais sans révocation de famille/audit annoncé | Historique des empreintes consommées jusqu'à expiration de famille; test après plusieurs rotations |
| SEC-05 | Moyenne, capacité absente | identity/models.py:40; auth_service.py:149-155 sans second facteur | Colonne MFA pouvant donner une assurance erronée si activée administrativement | Ne pas annoncer MFA; refuser comptes marqués MFA tant que challenge absent, puis implémenter enrôlement/récupération |

Chemins applicatifs relatifs à `backend/app/`. SEC-04 ne signifie pas qu'un ancien token obtient un accès : le problème est la détection/révocation incomplète.

Reproduction ciblée du spécialiste : après 5 échecs, limiteur A bloque et limiteur B autorise la même clé. 1001 clés restent stockées après expiration. Ces résultats démontrent le défaut local; ils ne remplacent pas un test multiworker HTTP.

## Matrice exigée pour chaque lot

Pour chaque route créée : anonyme 401; rôle insuffisant 403; objet A demandé depuis B inaccessible; références imbriquées B refusées; restriction de site; masquage des données RH; absence de contexte DB; tentative d'écriture tenant différent; réutilisation de connexion après rollback; audit sans PII libre; événements invalides/dupliqués. Tester les droits DB avec `mf_app`, jamais en substituant le superutilisateur.

Aucune fuite inter-tenant prouvée durant cet audit. Cette absence de preuve ne constitue pas une validation exhaustive. Pas de secret réel recherché/affiché dans les comptes connectés; fichiers de configuration et exemples inspectés sans exposition de secrets.
