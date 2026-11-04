# Audit exécutif — MineFleet 360

4 novembre 2026, `main@000ee08`. Synthèse des audits détaillés du même dossier.

## En une phrase

Le **cœur opérationnel** (parc, affectations, missions, pesées, atelier, carburant, coûts, HSE) est solide, sécurisé et
bien testé. Les **écarts visibles** pour un client sont le GPS en carte temps réel, la commercialisation SaaS et le
fonctionnement hors ligne en dehors du HSE.

## Chiffres vérifiés

| Indicateur | Valeur |
|---|---|
| Score de maturité (grille de la mission) | **62/100** (`PRODUCT_READINESS_SCORE.md`) |
| Modules backend / routes / permissions | 16 / 222 / 115 |
| Migrations Alembic | 58 |
| Tests backend | 4 941 passés, couverture 91 % |
| Tests frontend | 180 Vitest, 17 specs Playwright |
| CI | 5 jobs verts sur `main`, **tous obligatoires depuis le 4 novembre** (avant : seuls `backend` et `frontend`) |
| Performance mesurée | ~44 req/s avec 2 processus (jeu `large`), aucune erreur jusqu'à 40 utilisateurs simultanés |

## Forces

1. Isolation multi-tenant garantie **en base** (RLS forcée) et testée par un job CI obligatoire.
2. Traçabilité : audit systématique, séparation des tâches imposée par des contraintes.
3. Couverture métier minière rare : pesées, rotations, coût complet par engin, HSE terrain hors ligne.
4. Données de démonstration reproductibles jusqu'à 224 engins.

## Écarts prioritaires

| Priorité | Écart | Chantier |
|---|---|---|
| **P0** | Pas de carte interactive des engins en mouvement, pas de replay, pas de cap ni d'alerte de vitesse | Phase 2 — GPS temps réel (premier chantier) |
| **P0 avant production** | Avis juridique guinéen (hébergement, conservation), fournisseur e-mail, destination de sauvegarde | décisions client |
| P1 | Hors ligne limité au HSE | missions, maintenance et carburant hors ligne |
| P1 | Aucune facturation ni onboarding autonome | Phase 5 |
| P1 | CSP, SAST, scan de secrets | Phase 1 (sécurité) |
| P2 | Anglais, thème sombre, design system | Phase 5 |

## Limites de cet audit

- Aucun essai avec de vrais utilisateurs, aucun test d'intrusion, aucune instance de production.
- Le benchmark concurrentiel fait l'objet d'un document distinct (`docs/COMPETITIVE_BENCHMARK.md`), fondé sur des
  sources publiques datées.
