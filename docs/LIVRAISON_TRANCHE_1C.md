# Livraison — tranche 1c (affectations conducteur ↔ véhicule, interface web)

> Date : 2026-10-26. Périmètre : US-1.22 à US-1.25, prise de poste (D-27), suspension/reprise (D-30), branchement des refus D-11/D-13.
> **Hors de cette livraison** : jeu fictif d'affectations (US-1.30), revue sécurité et QA indépendante, écrans d'administration (utilisateurs, rôles, sites, journal d'audit) et de saisie (véhicules, conducteurs, permis).

## Contenu
| Élément | Détail |
|---|---|
| Migration | `0008_assignment` (le n° 0007 est pris par la réparation du catalogue) : table `vehicle_assignment` conforme à `MODELE_PHYSIQUE_LOT1.md` §5.7, RLS forcée, FK composites, `EXCLUDE gist` véhicule et conducteur, gardes `MF003` (immuabilité) et `MF004` (même site, changement de site) ; `ck_va_shift` ajouté (format du code de poste) |
| Module | `backend/app/assignment/` : `models`, `schemas`, `eligibility` (fonction pure), `service`, `router`, `contracts` |
| Contrats | `fleet/contracts.vehicle_facts`, nouveau `workforce/contracts.driver_facts` (ADR-001 : l'affectation n'importe aucun modèle d'un autre module) ; `assignment/contracts.open_assignments` remplace les fonctions vides des services flotte et personnel |
| Permissions | `assignment.vehicle_assignment.read/create/update/end` dans `authz_matrix.yaml` (grants de `MATRICE_RBAC.md` §2.5) ; `tranche_courante: 1c` |
| Erreurs | `ASSIGNMENT_NOT_ELIGIBLE` (422, `details.reasons[]`), `VEHICLE_ASSIGNMENT_OVERLAP`, `DRIVER_ASSIGNMENT_OVERLAP`, `ASSIGNMENT_STATE_INVALID` (409), `END_BEFORE_START`, `END_IN_FUTURE` (422) ; `MF003`/`MF004` → 409 `CONFLICT` |
| Configuration | `MF_ASSIGNMENT_BACKDATE_TOLERANCE` (15 min), `MF_ASSIGNMENT_END_FUTURE_TOLERANCE` (5 min), `MF_CLOCK_SKEW_TOLERANCE` (5 min), `MF_COMPLIANCE_SCAN_MAX` (2000) — valeurs de développement à arbitrer (Q21, Q22) |

## Routes (`/api/v1`)
| Méthode | Route | Permission |
|---|---|---|
| GET | `/vehicle-assignments` (filtres `site_id`, `vehicle_id`, `driver_id`, `status`, `at`, `compliance`) | read |
| GET | `/vehicle-assignments/{id}`, `/vehicles/{id}/assignments`, `/drivers/{id}/assignments` | read |
| POST | `/vehicle-assignments` | create |
| POST | `/vehicle-assignments/{id}/activate`, `/suspend`, `/resume` | update |
| POST | `/vehicle-assignments/{id}/complete`, `/cancel` | end |

## Hypothèses retenues (à valider)
1. **Code d'inéligibilité unique** : `DECISIONS_A_ARBITRER.md` D-29 prime sur `USER_STORIES.md` §0.4. `DRIVER_NOT_ACTIVE`, `VEHICLE_NOT_AVAILABLE`, `ASSIGNMENT_SITE_MISMATCH`, `ASSIGNMENT_BACKDATED` et les motifs permis/habilitation sont des **motifs** de `ASSIGNMENT_NOT_ELIGIBLE`, pas des codes HTTP distincts. Motifs ajoutés : `DRIVER_LICENSE_MISSING`, `DRIVER_LICENSE_EXPIRES_BEFORE_END`, `DRIVER_QUALIFICATION_EXPIRED`, `DRIVER_QUALIFICATION_EXPIRES_BEFORE_END`, `VEHICLE_CATEGORY_WITHOUT_DRIVER`.
2. **Permis** : un permis valide de **l'une** des catégories exigées par la catégorie d'engin suffit. Catégorie sans permis exigé au catalogue (pelle, bulldozer…) : seule l'habilitation interne est contrôlée. Le catalogue reste fictif (C-07).
3. **Habilitation** : `DRIVING_AUTHORIZATION` de la catégorie du véhicule, sans site ou du site du véhicule.
4. **Permission `update`** porte la prise de poste, la suspension et la reprise (mêmes rôles que la matrice). Pas de modification des dates d'une affectation planifiée : annuler puis recréer.
5. **Création** : statut `ACTIVE` si le début est passé ou dans la tolérance d'horloge, sinon `PLANNED`. **Prise de poste** refusée avant le début (`NOT_YET_STARTED`) ou après la fin prévue (`ALREADY_ENDED`).
6. **Clôture** : la fin réelle ne peut pas dépasser la fin prévue (pas de prolongation au lot 1, `VALIDATION_ERROR` `after_planned_end`) ; motif par défaut `END_OF_SHIFT`.
7. **`SUSPENDED` bloque** les changements de statut et de site comme `PLANNED`/`ACTIVE` (plus strict que D-11, cohérent avec D-30 et le trigger de site).
8. **Conformité** : calculée pour `ACTIVE` uniquement ; le filtre `compliance` est évalué en mémoire sur au plus `MF_COMPLIANCE_SCAN_MAX` affectations actives (au-delà : 422), en attendant le planificateur (lot 2+).
9. **Réponse enrichie** : numéro de parc, nom affiché et matricule du conducteur (les rôles qui lisent les affectations lisent aussi conducteurs et véhicules) ; jamais de n° de permis ni de nom dans l'audit.

## Vérifications exécutées (conteneur `api`, base `minefleet_test`)
- `ruff check`, `ruff format --check`, `mypy app` (strict) : OK.
- `pytest` (tests + tests_unit) : **1399 passed**, couverture **92,9 %** (module `assignment` : 89 à 100 %).
- `pytest tests_migrations` (montée d'une base 0004 peuplée vers head) : 2 passed.
- Cycle `downgrade base → upgrade head` exécuté au démarrage de chaque session de test.
- Tests ajoutés : `tests/test_assignment.py` (création, chevauchements, concurrence réelle à deux fils, motifs D-29, fuseau UTC+1, clôture/annulation, If-Match, D-27, D-30, D-11/D-13, historique à l'instant, portée site, conformité, gardes en base) ; `tests_unit/test_eligibility.py` (bornes au fuseau du site, bascule de conformité avec horloge explicite) ; matrice générée étendue aux nouvelles routes (refus 403, lectures autorisées, isolation inter-tenant).
- Le test à bouchon `test_d11_open_assignments_block_status_and_site_changes` est remplacé par un test sur de vraies affectations.

## Interface web (`frontend/`)
| Élément | Détail |
|---|---|
| Pile | React 19, React Router 8, TanStack Query 5, Vite 8, TypeScript 5.9 (strict) ; types d'API générés par `openapi-typescript` ; tests Vitest 4 + Testing Library + jsdom 29, E2E Playwright 1.64. Versions exactes (`package-lock.json`) |
| Sécurité | Jeton d'accès en mémoire seulement, rafraîchissement par cookie httpOnly, API sous la même origine (proxy) ; cache vidé à la déconnexion ; actions masquées selon les rôles, le serveur restant seul juge |
| Écrans | Connexion (restauration de session), accueil (rôles), sélecteur de site, listes véhicules et conducteurs (filtres, pagination), affectations (filtres statut et conformité, création au fuseau du site, prise de poste, suspension, reprise, clôture, annulation avec motifs) ; états chargement / vide / erreur / 403 / 404 ; motifs d'erreur en français |
| Choix de versions | TypeScript 7 écarté (sans API JavaScript : incompatible avec `openapi-typescript`) ; Vitest 5 et jsdom 30 écartés (exigent Node 22, le poste local est en Node 20.19). La CI frontend utilise Node 22 |
| Vérifications | `tsc --noEmit` OK ; Vitest **10 passed** ; `vite build` OK (99 ko gzip) ; `npm audit --omit=dev` : 0 vulnérabilité ; Playwright **3 passed** contre la pile locale (affecter puis clôturer, refus d'inéligibilité avec motifs, cloisonnement entre sociétés) |
| Bug trouvé par l'E2E | La recherche de conducteurs envoyait `search` au lieu de `q` (422) : corrigé |

## Non exécuté / reste à faire
- Revues **sécurité** et **QA** indépendantes de cette tranche (CLAUDE.md).
- E2E dans la CI (exige de monter API + base + seed) ; audit d'accessibilité outillé (reporté par D-22, contrôle manuel à faire).
- Paramètres de requête non typés dans le client (`get(path, query)`) : c'est ce qui a laissé passer le bug `search`/`q` ; à typer depuis `schema.d.ts`.
- Affectations dans `minefleet seed-fictif` pour la recette.
- Déploiement sur le VPS de recette : non fait (migration 0008 à appliquer avec la procédure de `DEPLOIEMENT_OVH.md`).
- Mise à jour de `MATRICE_RBAC.md` §2.5 et `USER_STORIES.md` (US-1.33, US-1.34) avec les hypothèses ci-dessus.
