# Score de maturité produit — base de départ

Mesure du 4 novembre 2026 sur `main@000ee08` (après #336). Elle remplace, pour le pilotage, le score de
`docs/MATURITY_SCORECARD.md` (70,3/100 du 30 octobre), calculé avec une autre grille et devenu périmé : il notait
par exemple pièces/pneus à 20 et HSE à 25, alors que ces modules ont été livrés depuis.

**Règle** : seul ce qui est prouvé dans le dépôt (code, migrations, tests exécutés, CI) rapporte des points. Ce qui
n'a pas été vérifié est marqué *non vérifié* et ne rapporte rien. Aucun essai avec de vrais utilisateurs n'a eu
lieu : la note ne couvre que la maturité technique et fonctionnelle observable.

## Score global : 62/100

| Domaine (grille de la mission) | Points | Note | Principales preuves | Ce qui manque pour progresser |
|---|---:|---:|---|---|
| Fonctionnalités métier | 20 | **14** | 16 modules backend, 222 routes sous 115 permissions ; parc, conducteurs, affectations, missions, pesées, OT, préventif (plans, dernier entretien, échéances), carburant complet, pneus, pièces et achats, HSE, coût complet, documents | batteries, portail sous-traitants, contrats et garanties, planning atelier, tableaux de bord par rôle |
| GPS et télématique | 15 | **7** | ingestion authentifiée traceur et téléphone, séquences, positions tardives, dernières positions, trajet avec arrêts, trous et distance, géofences et événements, purge de rétention, simulateur de démo | **pas de carte interactive multi-engins**, pas de replay animé, pas de cap, pas d'alerte de vitesse ni de notification temps réel, aucun fournisseur réel intégré |
| Qualité et tests | 15 | **12** | 4 941 tests backend (couverture 91 %), 180 tests Vitest, 17 specs Playwright (4 suites), 5 jobs CI obligatoires verts, test de downgrade des migrations sur base remplie | tests d'accessibilité automatisés, tests de charge en CI, DAST |
| Sécurité et multi-tenancy | 15 | **12** | RLS forcée sur les tables métier, rôle applicatif sans DELETE, tests d'isolation (35 fichiers) et job CI `tenant-isolation`, MFA, audit, limitation des échecs de connexion, `pip-audit` et `npm audit` | SAST, scan de secrets, DAST ; le job `tenant-isolation` n'est **pas obligatoire** sur `main` (vérifié par l'API GitHub) ; avis juridique guinéen (hébergement, conservation) **bloquant** pour la production |
| UX/UI et mobile hors ligne | 10 | **5** | responsive vérifié (360 et 768 px), PWA avec service worker, HSE hors ligne avec file de synchronisation idempotente | anglais, thème sombre, design system documenté ; hors ligne limité au HSE (missions, maintenance et carburant ne fonctionnent pas hors ligne) |
| Architecture et performance | 10 | **6** | monolithe modulaire, mesures publiées (`PERFORMANCE_DEMO.md` : ~44 req/s avec 2 processus, coût complet 373 → 197 ms) | temps réel par push (le rafraîchissement se fait par interrogation toutes les 15 s), partitionnement des positions GPS, observabilité (traces, métriques) |
| SaaS et exploitation | 10 | **4** | création de sociétés par la plateforme, déploiement de recette OVH, sondes de santé, sauvegardes chiffrées hors machine (optionnelles), vérification de restauration | abonnements, quotas, facturation, onboarding autonome, portail client, production réelle |
| Documentation et commercialisation | 5 | **2** | documentation technique abondante (décisions, livraisons, revues de sécurité) | benchmark, vision commerciale, guide de démo commercial, tarification |
| **Total** | **100** | **62** | | |

## Lecture

- Le **cœur opérationnel** (parc → affectation → mission → pesée → atelier → coûts) est solide et bien testé.
- Le **GPS** est l'écart le plus visible pour un client : les données sont là (positions, vitesses, arrêts), mais
  l'utilisateur ne voit pas les engins bouger sur une carte. C'est le premier chantier P0 retenu
  (`ROADMAP_2026_2027.md`).
- La **commercialisation** (facturation, onboarding) et la **production** (avis juridique, fournisseur e-mail,
  sauvegardes) restent à faire.

## Suivi

Le score sera recalculé avec la même grille à la fin de chaque phase. Chaque point gagné devra citer sa preuve : PR,
test ou mesure.
