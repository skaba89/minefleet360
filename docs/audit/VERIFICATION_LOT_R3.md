# Lot R3 — authentification, sessions et emails

Base : main `85921bd6f0c242f7884712cec220f0d350ecf7d5`. Date :26 octobre 2026. Aucun déploiement réalisé dans ce lot.

## Corrections

| Référence audit | Modification | Preuve prévue |
|---|---|---|
| SEC-01/02 | Compteurs partagés PostgreSQL, clés HMAC, aucune allocation à la lecture, écritures atomiques, purge des expirées et plafond10000 clés par namespace | Deux applications et redémarrage, enregistrements concurrents, capacité et expiration, droits DB |
| SEC-03 | SMTP TLS configurable; capture refusée en production, fichiers privés0600 et répertoire0700, purge des UUID expirés sans suivre les symlinks | Tests purs avec mocks SMTP et répertoires temporaires |
| SEC-04 | Historique des refresh consommés, reconnaissance après plusieurs rotations, grâce limitée au précédent, révocation auditée au plafond1024 | Rejeu ancien, grâce, session legacy, plafond, cookie tenant falsifié |
| SEC-05 | Refus des comptes marqués MFA à la connexion/refresh et sur les accès protégés | Tests API sans second facteur fictivement déclaré opérationnel |
| Revue R3 | Réponse anonyme202 constante même sur échec SMTP; transport en tâche de fond après réponse, erreur journalisée sans PII | Compte connu/inconnu avec transport en panne |

## Architecture et migrations

`0008` crée la table globale technique `app.auth_failure_bucket`, sans accès direct mf_app/PUBLIC. Deux fonctions SECURITY DEFINER, search_path fixé et paramètres validés, fournissent lecture/enregistrement et reset d'une seule empreinte. L'horloge PostgreSQL fait autorité, pas une date choisie par l'appelant. Les verrous transactionnels par namespace sérialisent les écritures et le contrôle du plafond. Le pool du limiteur est distinct du pool métier; les échecs survivent au rollback de la requête401. La méthode de nettoyage globale existe uniquement pour le harnais MF_ENV=test/base*_test avec connexion propriétaire absente du runtime API.

`0009` ajoute le tableau d'empreintes consommées à auth_session, borné par contrainte DB à1024. Les policies tenant existantes restent applicables à la ligne de session. Aucune empreinte n'est oubliée pour libérer de la place : le plafond révoque explicitement la session. Les sessions antérieures à la migration gardent leur dernier jeton précédent, intégré à l'historique à la rotation suivante. Les jetons plus anciens déjà oubliés avant cette migration ne peuvent pas être reconstruits rétroactivement.

Les downgrades restent protégés hors local/test/ci. Le retour à l'ancien code laisse les colonnes/tables supplémentaires mais réintroduit ses protections plus faibles; éviter un retour applicatif automatique sur les anciennes versions de sécurité. Le déploiement doit exécuter les migrations avant l'API nouvelle version.

## Contrats et limites

Aucune nouvelle route ni permission métier. Les formats de cookies et access tokens restent compatibles. Les erreurs publiques ne contiennent ni email/IP en clair, ni secret SMTP, ni jeton. Aucun frontend n'existe encore : l'interface complète des parcours reste dans M1, pas une interface MFA inventée.

La limitation protège le partage entre workers et conserve tous les échecs enregistrés. Vérification et enregistrement sont deux opérations : elle ne garantit pas une limite stricte de tentatives simultanées déjà en vol. La table est bornée; la purge physique arrive au prochain enregistrement. Le nettoyage des anciennes sessions et captures sans nouvel envoi reste à planifier. SMTP utilise le réseau seulement lors de l'envoi; les tests utilisent exclusivement des mocks. Aucun fournisseur réel n'a été contacté. Le reset en tâche de fond n'est pas une file durable et ne possède pas de retry automatique.

## Vérification locale

Ruff lint/format réussis; mypy app réussi sur 54 fichiers; 20 tests unitaires email/configuration réussis. Compilation réussie et chaîne Alembic vérifiée : `0009 (head)`. Docker/PostgreSQL absents localement; les validations réelles DB ci-dessous ont été exécutées en CI.

Revue sécurité spécialisée effectuée. Deux recommandations appliquées avant publication : suppression de la date choisie par le rôle applicatif dans les fonctions de purge, et suppression du différentiel202/500 sur reset anonyme en cas de panne SMTP.

## Résultats CI PostgreSQL/PostGIS vérifiés

[Run 40352366169](https://github.com/skaba89/minefleet360/actions/runs/40352366169), job `121675580756`, commit applicatif `c870fd1a666aab9ca39cb67a418c342714c9cf81` : terminé avec succès. Journaux consultés :

| Vérification | Résultat |
|---|---|
| Ruff lint / format | Réussis, 81 fichiers conformes |
| mypy app | Réussi, 54 fichiers |
| Upgrade depuis 0004 peuplée vers head | 2 tests réussis |
| Suite applicative complète | 1205 tests réussis en 91,11 secondes |
| Couverture | 93 % |
| Audit des dépendances | Aucune vulnérabilité connue |

Les 15 nouveaux tests d'intégration authentification/refresh et les 17 nouveaux cas unitaires email sont inclus dans les 1205 tests. Deux instances FastAPI successives, les enregistrements concurrents, les accès DB interdits, le plafond/expiration, le MFA refusé, le reset en panne et les rejeux ont donc été exercés réellement sur PostgreSQL/PostGIS.

Le transport capture repose sur les primitives POSIX/Linux utilisées par les conteneurs cibles. Les clés HMAC sont des empreintes pseudonymisées et restent soumises à la politique de conservation; elles ne doivent pas être considérées comme une anonymisation irréversible.

Statut : **implémenté et vérifié en CI**, proposé dans la [PR #5](https://github.com/skaba89/minefleet360/pull/5). Ce complément de rapport est postérieur au SHA applicatif testé. Aucun déploiement ni fusion automatique.
