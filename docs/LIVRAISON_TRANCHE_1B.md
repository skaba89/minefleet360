# Livraison — tranche 1b (véhicules, conducteurs, permis, habilitations) et suites des revues 1a

> Date : 2026-10-26. Statut : **développement local terminé** ; revue sécurité/QA indépendante de la 1b à faire. Rien n'est déployé.

## Périmètre livré
| Story | Contenu |
|---|---|
| US-1.11 | Catalogue de référence global (15 catégories, permis requis fictifs « à valider localement », C-07) copié dans chaque tenant à sa création ; tenants existants complétés par la migration 0005 |
| US-1.12 à US-1.15 | Véhicules : unicité normalisée (numéro de parc à vie, immatriculation, série), site/catégorie dans la portée (422 sinon), machine à états (transitions de MODELE_CONCEPTUEL 4.1), motif codifié obligatoire, réforme terminale, historique de statut par trigger, réformés masqués par défaut, recherche d'immatriculation normalisée |
| US-1.16, US-1.17, US-1.21 | Conducteurs : matricule unique, homonyme = avertissement `POSSIBLE_DUPLICATE`, schéma strict (aucune donnée hors lot 1, D-15), masquage serveur par enregistrement, changement de statut avec motif obligatoire |
| US-1.18 à US-1.20 | Permis (renouvellement historisé, numéro jamais exposé hors HR ni audité), habilitations (chevauchement refusé en base), validité **dérivée au fuseau du site** (D-23), catégories autorisées dérivées, liste des échéances par portée |

## Décisions prises pendant la tranche
| ID | Décision |
|---|---|
| D-34 | Réforme possible depuis tout statut non terminal (pas de circuit d'approbation au lot 1) ; transitions manuelles sinon limitées à la machine à états |
| D-35 | Catalogue de catégories = 2 tables **globales** en lecture seule (`vehicle_category_template`, `..._license`), copiées par tenant (D-18) |
| D-36 | Tout paramètre de requête non déclaré → `422 VALIDATION_ERROR`, évalué **après** 401/403 (dans `Require`) |
| D-37 | Masquage **par enregistrement** : un champ restreint n'est visible que via un rôle détenu en portée TENANT ou sur le site de l'enregistrement ; champs restreints jamais valorisés dans l'audit (dérivés de `field_policies`) |
| D-38 | `identity.user.read` pour HR en portée TENANT seulement (SEC-05) |

## Vérifications exécutées (conteneur Python 3.12, PostgreSQL 16 + PostGIS)
- Migrations : `downgrade base → upgrade head`, `downgrade 0004 → upgrade head` : OK.
- `ruff check`, `ruff format --check`, `mypy app` (strict, 52 fichiers) : OK.
- `pytest --cov=app --cov-branch` : **1151 passed**, couverture **91,16 %** (seuil 85 % désormais bloquant en CI et dans `scripts/test.ps1`).
- `pip-audit` : aucune vulnérabilité connue après mise à jour (FastAPI 0.143, starlette 1.7.0 épinglé, PyJWT 2.15.1, SQLAlchemy 2.1.4, pytest 9.1.1, pip 26.2 ; versions publiées avant le 12/10/2026).

## Suites des revues de la tranche 1a
| Constat | Traitement |
|---|---|
| SEC-01 dépendances vulnérables | **Corrigé** (voir ci-dessus) |
| SEC-05 HR portée SITE liste tous les comptes | **Corrigé** (D-38, test) |
| SEC-14 base de test créée sur la démo | **Corrigé** : `MF_CREATE_TEST_DB` (dev/CI uniquement) |
| Revue auto 1b : masquage par union des rôles ; `employment_type` dans l'audit | **Corrigés** (D-37, deux tests de régression) |
| QA1A-01 suite 1a cassée par les tables 1b | **Corrigé** (liste des tables globales) |
| QA1A-02 couverture absente de la CI | **Corrigé** (seuil 85 %) |
| QA1A-06 critères non testés | **Partiel** : US-1.02 A5, US-1.05 A4, US-1.10 A4 ajoutés ; restent US-1.27 A3/A4, US-1.04 A8, US-1.05 A5, US-1.31 A5, US-1.32 A3, US-1.01 A7, US-1.26 A8 |
| QA1A-07 test de concurrence | **Amélioré** (barrière de départ) ; accepte toujours 403 ou 409 selon l'ordonnancement (les deux sont corrects) |
| QA1A-08 mutation du singleton de configuration | **Corrigé** (`monkeypatch`) |
| SEC-02 oracle temporel (≈ 15 ms) | **Accepté provisoirement** : écart dû à l'écriture du compteur d'échecs ; à traiter avec la MFA |
| SEC-03 verrouillage d'un compte par un tiers | **Risque accepté au lot 1** (compromis anti-force brute) ; à revoir avec MFA/CAPTCHA avant pilote |
| SEC-04 PLATFORM_ADMIN sans MFA | Ouvert — **bloquant avant pilote** (C-03) |
| SEC-06 audit des 403 sans limite | Ouvert — limitation/agrégation à concevoir |
| SEC-07, SEC-08, SEC-12, SEC-13 (démo : 2 workers, capture d'e-mails, /docs public, origine absente acceptée) | Acceptés pour la **démo fictive** ; à revoir avant toute donnée réelle |
| SEC-09 `reset-credentials` admin ne révoque pas les sessions | Par conception : la confirmation du lien révoque toutes les sessions |
| SEC-10, SEC-11, SEC-15 | Ouverts, faible gravité (voir `revues/REVUE_SECURITE_TRANCHE_1A.md`) |
| QA1A-03, 04, 05 (alembic check, durcissement CI, amorçage CI) | Ouverts ; la CI n'a toujours pas d'exécution confirmée |

## Non exécuté / limites
- Revue sécurité et QA indépendante de la **tranche 1b** : à lancer.
- Les refus 409 `OPEN_ASSIGNMENTS_EXIST` (D-11, D-13) sont câblés mais la liste est vide jusqu'à la tranche 1c (pas encore d'affectations).
- Aucune interface web ; pas d'E2E.

## Prochaine étape
Tranche 1c : affectations conducteur ↔ véhicule (exclusion de chevauchement en base, éligibilité, activation explicite D-27, suspension D-30), interface web minimale en français, E2E.
