# Socle de cadrage commun — MINEFLEET 360

> Statut : **provisoire** (phase 0). Ce document fixe les conventions partagées par tous les livrables de cadrage afin d'éviter les incohérences entre documents. Toute divergence doit être signalée et arbitrée, pas contournée silencieusement.
>
> **Mise à jour post-revue (2026-10-25)** : les décisions de `DECISIONS_A_ARBITRER.md` (D-01..D-24) **priment** sur ce socle. Changements principaux : énumérations en anglais (D-01..D-04), tenant plateforme réservé et `tenant_id NOT NULL` (D-07), connexion par code d'espace + e-mail (D-06), UUID v4 (D-20), rôle `AUDITOR` retenu (D-10), entités ajoutées au lot 1 : `account_token`, `auth_session`, `vehicle_status_history`, jonction catégorie↔permis requis ; reportées : `vehicle_meter_reading`, `idempotency_record` (D-14, D-16).

## 1. État constaté du dépôt (2026-10-25)
- Aucun code applicatif, aucun commit Git (branche `master` vide ; la branche principale attendue est `main`).
- Contenu : `CLAUDE.md`, `README.md`, `PROMPT_LANCEMENT_CLAUDE.md`, `docs/PRODUCT_VISION.md`, `docs/ROADMAP.md`, 8 agents (`.claude/agents/`), 8 skills (`.claude/skills/`).
- Poste de développement : Python 3.10.11, Node 20.19, Docker 29 opérationnel ; pas de `psql`, `uv` ni `pnpm` installés.

## 2. Hypothèses structurantes (à confirmer — voir `DECISIONS_A_ARBITRER.md`)
| # | Hypothèse | Justification |
|---|-----------|---------------|
| H1 | Multi-tenant **base partagée, schéma partagé**, colonne `tenant_id` sur toute table métier ; **RLS PostgreSQL en défense en profondeur**, jamais en remplacement de l'autorisation applicative. | Simplicité opérationnelle, coût, migrations uniques. |
| H2 | Identifiants **UUID** v4 (`gen_random_uuid()`, D-20) ; jamais d'ID séquentiel exposé. | Limite l'énumération / IDOR. |
| H3 | Clés étrangères **composites `(tenant_id, id)`** entre tables métier. | Rend impossible en base une référence inter-tenant. |
| H4 | Horodatages `timestamptz` stockés en **UTC** ; fuseau d'affichage par défaut `Africa/Conakry` (UTC+0, sans heure d'été), configurable par site. | Exigence CLAUDE.md. |
| H5 | Monnaie **GNF**, stockée en entier (`bigint`, pas de décimales). | Le GNF n'a pas de subdivision usuelle. |
| H6 | Le **compte utilisateur** (login) est distinct de la **personne/salarié** (conducteur, mécanicien). Un conducteur peut exister sans compte. | Skill hr-workforce ; tous les conducteurs n'ont pas de smartphone. |
| H7 | Rôles attribués avec une **portée** : `TENANT` (tous sites) ou `SITE` (un site donné). | Multi-site. |
| H8 | Monolithe modulaire FastAPI + React/TS ; PostgreSQL 16 + PostGIS ; pas de Redis ni de stockage objet au lot 1. | CLAUDE.md, pas de dépendance spéculative. |
| H9 | Données de démonstration **exclusivement fictives** ; aucune donnée GPS réelle de salariés. | CLAUDE.md. |
| H10 | Le GPS n'est **jamais** une preuve de tonnage ; seul un pont-bascule ou une source approuvée fournit un tonnage mesuré. | CLAUDE.md. |

## 3. Codes de rôles (référence unique)
| Code | Persona (FR) |
|------|--------------|
| `PLATFORM_ADMIN` | Administrateur plateforme (éditeur ; hors tenant, accès support tracé et limité) |
| `TENANT_ADMIN` | Administrateur de tenant |
| `DIRECTION` | Direction générale |
| `OPS_MANAGER` | Direction des opérations |
| `DISPATCHER` | Dispatcher / régulateur |
| `HR` | Ressources humaines |
| `DRIVER` | Conducteur / opérateur d'engin |
| `WORKSHOP_CHIEF` | Chef d'atelier |
| `MECHANIC` | Mécanicien |
| `STOREKEEPER` | Magasinier |
| `FUEL_MANAGER` | Responsable carburant |
| `HSE` | Responsable HSE |
| `FINANCE` | Finance / contrôle de gestion |
| `AUDITOR` | Auditeur (lecture seule, *proposé* — à arbitrer) |

## 4. Modules du monolithe (noms techniques)
`identity` (comptes, sessions, rôles), `organization` (tenants, sites), `fleet` (véhicules/engins), `workforce` (personnes, permis, habilitations), `assignment` (affectations conducteur↔véhicule), `audit` (journal), puis plus tard `dispatch`, `maintenance`, `inventory`, `fuel`, `telematics` (GPS), `hse`, `contracts`, `finance`, `reporting`.

## 5. Entités du lot 1 (noms techniques)
`tenant`, `site`, `user_account`, `role` (référentiel), `user_role_assignment`, `vehicle`, `vehicle_category` (référentiel), `driver` (personne), `driver_license`, `driver_qualification` (habilitation engin), `vehicle_assignment` (intervalle de validité), `audit_event` (append-only).

## 6. Conventions documentaires
- Langue : français ; identifiants techniques en anglais `snake_case`.
- Diagrammes : Mermaid dans le Markdown.
- Chaque document distingue **faits vérifiés**, **hypothèses** et **points à valider** (juridique Guinée, fournisseurs GPS, client).
- Aucune métrique, tonnage, ROI ou résultat de test inventé.
