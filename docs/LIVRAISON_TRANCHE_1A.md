# Livraison — tranche 1a (socle technique et sécuritaire)

> Date : 2026-10-25. Statut : **développement local terminé, revue sécurité/QA indépendante à faire**. Rien n'est déployé.

## Périmètre livré
| Story | Contenu | Vérifié par |
|---|---|---|
| US-1.01, US-1.02 | Création de tenant (premier `TENANT_ADMIN` invité, transaction unique, audit plateforme + tenant), suspension/réactivation avec révocation immédiate des sessions | `test_organization_audit.py`, `test_auth.py` |
| US-1.03 | Sites : création, modification (`If-Match`), désactivation/réactivation, unicité par tenant, fuseau IANA | `test_organization_audit.py` |
| US-1.04 à US-1.07, US-1.31 | Invitation, activation, rôles avec portée TENANT/SITE, union des attributions, refus d'auto-modification (422 audité), protection du dernier administrateur (verrou + recomptage, testé en concurrence), désactivation | `test_identity.py` |
| US-1.08 à US-1.10 | Connexion code d'espace + e-mail (401 identique dans 7 cas), limitation de débit, refresh rotatif avec détection de rejeu, déconnexion, réinitialisation | `test_auth.py` |
| US-1.26, US-1.27 | Journal append-only partitionné par mois, lecture `TENANT_ADMIN`/`AUDITOR`, une écriture = un événement, aucune valeur personnelle | `test_organization_audit.py`, `test_database.py` |
| US-1.28 | Isolation : RLS forcée, FK composites, 404 indiscernable, `tenant_id` client refusé | `test_database.py`, `test_authz_matrix.py` |
| US-1.32 | Commande `minefleet create-platform-admin` (secret par variable d'environnement, refus si déjà présent) | `test_organization_audit.py` |

## Vérifications exécutées (sorties réelles, conteneur Python 3.12, PostgreSQL 16 + PostGIS 3.4)
- `alembic upgrade head` puis `downgrade base` puis `upgrade head` : OK (base `minefleet_test`) ; `upgrade head` sur la base de dev : OK.
- `ruff check` : « All checks passed! » ; `ruff format --check` : OK ; `mypy app` (strict) : « no issues found in 39 source files ».
- `pytest` : **672 passed** (35 s). Dont 619 tests générés depuis `authz_matrix.yaml` : inventaire route ↔ permission, 505 refus 403, 95 lectures autorisées, 12 cas d'isolation inter-tenant.
- Test de mutation manuel : ignorer la portée dans le moteur d'autorisation → 8 échecs ; retirer le filtre de site → 1 échec (les tests générés ne sont pas tautologiques).
- Test de concurrence (révocation croisée de deux administrateurs) : 5 exécutions consécutives stables.
- API locale : `/api/v1/health` → 200, route protégée sans jeton → 401.

## Non exécuté / limites connues
- **CI GitHub Actions** écrite mais jamais exécutée (premier push en attente d'authentification GitHub sur ce poste). Le script d'amorçage n'a pas été testé avec `PGHOST` distant (cas CI).
- `pip-audit`, scan de secrets et images de production : non exécutés.
- Aucune interface web (les écrans des stories 1a seront livrés avec la tranche 1c, cf. PLAN_LOT1).
- Limitation de débit **en mémoire par processus** (perdue au redémarrage, non partagée entre instances).
- Pas de MFA (C-03, avant pilote) ; durées de jetons et politique de mot de passe = valeurs de développement provisoires (`app/core/config.py`).
- Catégories de véhicule/permis copiées par tenant : reportées à la tranche 1b (tables créées en 1b).
- `LAST_TENANT_ADMIN` n'est atteignable qu'en concurrence (un administrateur actif ne peut pas se retirer lui-même) : testé uniquement par le test de concurrence.
- Fixtures e-mail en `@example.com` (le validateur refuse `.invalid` prévu au MODELE_PHYSIQUE §9).

## Écarts documentés
D-31 (deux niveaux de limitation), D-32 (`FOR NO KEY UPDATE` + `lock_timeout` : corrige un interblocage réel trouvé par les tests), D-33 (`organization.tenant.list`, `DRIVER` sans lecture de site, `TENANT_CODE_RESERVED`). `MATRICE_RBAC.md` doit être alignée sur `authz_matrix.yaml` pour ces points.

## Prochaine étape recommandée
Revue `security-engineer` + `qa-devops-engineer` de la tranche 1a, puis tranche 1b (véhicules, conducteurs, permis, habilitations).
