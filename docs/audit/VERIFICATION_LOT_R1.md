# Vérification du lot R1 — intégrité des migrations

Date : 26 octobre 2026. Branche : `audit/2026-10-26-mvp-remediation`. Base : `2e3b803`.

## Résultat livré

- Migration additive `0007` : réparation des catégories système et associations de permis manquantes pour les tenants clients préexistants.
- Policies RLS temporaires limitées à `mf_owner` et aux commandes SELECT/INSERT requises, retirées dans la transaction.
- Collision entre code système et catégorie personnalisée : arrêt explicite et rollback intégral.
- Downgrade conservateur : la révision peut revenir à `0006` en test/local, les données réparées restent en place.
- URL PostgreSQL construite avec `sqlalchemy.engine.URL.create`, y compris pour les mots de passe contenant des caractères réservés.
- Tests unitaires hors DB et test d'upgrade destructif isolé avant la suite applicative.

## Vérifications exécutées localement

| Commande | Résultat |
|---|---|
| `ruff check .` | Réussi |
| `ruff format --check .` | Réussi, 72 fichiers conformes |
| `mypy app` | Réussi, 52 fichiers |
| `pytest -q -p no:warnings tests_unit` | 3 réussis |
| `alembic heads` avec configuration synthétique | `0007 (head)` |
| `python -m compileall -q app alembic tests_migrations tests_unit` | Réussi |
| `git diff --check` | Réussi |

Le test `tests_migrations` et la suite PostgreSQL/PostGIS ne sont pas exécutables dans l'environnement local actuel : aucun serveur PostgreSQL ni moteur Docker n'y est disponible. Ils ont été exécutés en CI sur le `main` `b19c825d504ec158fc633024a5b8993bf7b31d01` : [run 40296704419](https://github.com/skaba89/minefleet360/actions/runs/40296704419), job 121484406259, succès. Journaux vérifiés : **2 tests de migration réussis, 1167 tests applicatifs réussis, couverture 92 %, aucune vulnérabilité connue**.

Le premier run R1 sur `f507942` avait validé les deux migrations mais échoué sur `test_owner_database_url_requires_owner_secret`, qui héritait du secret propriétaire CI. Le commit `f1c92ef` a rendu ce test hermétique avec suppression temporaire de la variable d'environnement. Cette correction fait partie du main vérifié ci-dessus.

## Couverture du test de migration

Le test dédié reconstruit une base en `0004`, insère deux tenants et deux sites avec `mf_app`, monte en `0006` et démontre le catalogue vide produit par le défaut 0005. Il vérifie ensuite la réparation 0007, les liens de permis, la conservation d'une catégorie système personnalisée, l'insertion d'un véhicule, le refus d'une catégorie étrangère, les policies permanentes, FORCE RLS, l'invisibilité A→B et l'idempotence `0007 → 0006 → 0007`.

Un second scénario injecte une catégorie personnalisée portant un code système. L'upgrade doit échouer, laisser Alembic en `0006`, ne conserver aucune policy temporaire et n'insérer aucune donnée partielle.

## Revues spécialisées

Revues base, sécurité et QA effectuées sur le diff. Aucun point bloquant statique. Les améliorations proposées ont été intégrées : policies temporaires réduites à SELECT/INSERT et assertions renforcées après réussite comme après rollback.

## Risques résiduels

- Le type de l'exception PostgreSQL du scénario de collision est confirmé par les deux tests de migration réussis en CI.
- La migration modifie les données de référence de chaque tenant client; effectuer une sauvegarde vérifiée et un inventaire des collisions avant toute exécution hors environnement de test.
- R1 ne corrige pas encore la garde de désactivation des sites (R2), l'anti-bruteforce partagé ni le transport email (R3).

Statut : **R1 fusionné et vérifié sur PostgreSQL/PostGIS en CI**. Aucun déploiement réalisé par cet audit.
