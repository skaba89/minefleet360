# Audit technique

Référence : `main@3c4bb02`, 30 octobre 2026.

## Périmètre inspecté

- Backend FastAPI/SQLAlchemy : 137 fichiers Python, 108 routes API observées.
- Base PostgreSQL/PostGIS : 33 migrations, tête `0033`, 96 classes de modèles.
- Frontend React/TypeScript : 55 fichiers TS/TSX, 34 pages/tests et 10 scénarios E2E.
- Qualité : Ruff, mypy strict, pytest, Vitest, Vite, Playwright et audits de dépendances dans GitHub Actions.
- Sécurité : matrice RBAC, RLS, contexte tenant, MFA, journalisation et ingestion GPS.

## Résultats exécutés sur `main`

| Contrôle | Résultat vérifié |
|---|---|
| CI backend | Réussie, run 41033170043 |
| Tests de migrations | 2 réussis |
| Tests backend | 3 115 réussis en 230,77 s |
| Couverture backend | 89,71 %, seuil 85 % respecté |
| Ruff / mypy | Réussis |
| `pip-audit` | Aucune vulnérabilité connue |
| Frontend | typecheck, 55 tests, build et `npm audit` réussis |
| Smoke navigateur | Réussi |
| E2E isolation | Réussi, run 41033169734 |

## Architecture et sécurité

Points forts : séparation modulaire, migrations versionnées, transactions SQLAlchemy explicites, contraintes d'intégrité au niveau PostgreSQL, événements immuables, secrets de test éphémères et RLS forcée. Le contexte tenant PostgreSQL est centralisé et testé ; aucune extension de ce mécanisme n'est autorisée hors composants dédiés.

MFA TOTP, verrouillage, révocation de sessions et limitation partagée en PostgreSQL sont présents. L'ingestion traceur repose sur un identifiant et un secret révocable ; les tests couvrent rejeu, portée tenant et remplacement de secret.

## Cinq risques prioritaires

| Priorité | Risque et preuve | Impact | Action corrective | Critère de validation |
|---|---|---|---|---|
| R1 | Déploiement et reprise non prouvés : documentation d'environnement historique, tête actuelle `0033`, aucun exercice de restauration récent | perte de données ou échec de migration en pilote | pipeline staging, sauvegarde chiffrée, restauration automatisée et runbook | restauration chronométrée d'un dump, migration `base -> 0033`, preuves archivées et RPO/RTO mesurés |
| R2 | Dérive API/UI : routes pompes fusionnées mais types frontend absents | régression silencieuse et fonctionnalités backend inaccessibles | export OpenAPI déterministe et garde CI | modification d'une route sans régénération fait échouer la CI ; typecheck/build passent après régénération |
| R3 | Pièces/pneus/HSE sans cycle structuré | coûts incomplets, traçabilité et conformité insuffisantes | modèles, RLS, journal de mouvements et parcours métier incrémentaux | tests de stock concurrent, isolation, audit et E2E des cycles critiques |
| R4 | GPS non industrialisé : pas d'intégration fournisseur, géofencing ni historique de trajet complet | suivi terrain incomplet et alertes peu exploitables | interface fournisseur, file d'ingestion idempotente, rétention, géofences | test avec traceur réel/sandbox, charge, rejeu, révocation et alertes bout en bout |
| R5 | Gouvernance DevSecOps incomplète : deux workflows seulement ; pas de SAST, détection de secrets, SBOM/scan image ; protection de branche inaccessible à l'audit | vulnérabilité ou changement non contrôlé | workflow sécurité et vérification administrative des règles de branche | scans bloquants sans alerte critique, checks requis et revue obligatoire vérifiés par API autorisée |

## Migrations et transactions

Les migrations sont séquentielles et la CI teste un upgrade peuplé depuis `0004`. Les règles fortes sont généralement portées par contraintes, triggers, exclusions et verrous. Ce niveau est satisfaisant pour le code, mais il manque un test reproductible de sauvegarde/restauration et une validation de migration sur une copie anonymisée de données réalistes.

## Observabilité, performance et résilience

La journalisation applicative et l'audit métier existent, mais aucune preuve de collecte centralisée, métriques, traces, SLO, alerting ou astreinte n'est disponible. Aucun budget de performance ni test de charge GPS/dispatch n'est versionné. Ces éléments empêchent de qualifier le produit de SaaS industrialisé.

## Correctif engagé

Le script `scripts/export_openapi.py` exporte le schéma sans serveur ni connexion DB. La CI régénère `frontend/src/api/schema.d.ts` et compare le résultat versionné. Le schéma est trié pour garantir la stabilité du diff.
