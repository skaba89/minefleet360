# Score de maturité

Audit indépendant du 30 octobre 2026, basé sur `main@3c4bb02` (70,3/100), **rejoué le 12 novembre 2026 sur `main@c34d322` (PR #435)** avec la grille, la méthode et les poids inchangés. Le calcul du rejeu est reproductible : `python3 scripts/replay_maturity_scorecard.py` vérifie que la colonne du 30 octobre retombe exactement sur 73,4 / 56,7 / 76,5 → 70,3 avant d'imprimer les agrégats courants.

## Méthode (inchangée)

Chaque capacité est notée de 0 à 100 à partir des preuves dans le code, les migrations, l'UI et les tests exécutés. Les moyennes de catégorie sont arithmétiques. Le score global applique les poids suivants : fonctionnel 40 %, métier minier 25 %, technique 35 %.

`Score global (12 nov) = 80,5 × 0,40 + 63,0 × 0,25 + 78,8 × 0,35 = 75,5/100`.

Le rejeu porte exclusivement sur des preuves de **code, migrations, UI et tests** postérieures au 30 octobre ; aucune ligne n'intègre de validation terrain (matériel, Android physique, réseau réel, données de production), qui reste absente.

## Fonctionnel — 80,5/100 (73,4 au 30 octobre)

| Capacité | 30 oct | 12 nov | Preuve nouvelle depuis le 30 octobre |
|---|---:|---:|---|
| Sociétés et sites | 92 | 92 | — |
| Utilisateurs et permissions | 91 | 91 | — |
| Parc et véhicules | 88 | 88 | — |
| Conducteurs et habilitations | 86 | 86 | — |
| Affectations | 84 | 84 | — |
| Missions et rotations | 82 | 82 | — |
| Maintenance corrective/préventive | 78 | 83 | pièces structurées (CMP, réservations concurrentes, réappro quatre-yeux), préventif complété (déclarations, révision avec historique, suspension) et prouvé depuis l'UI (#430) |
| Carburant et achats | 83 | 83 | — |
| Documents réglementaires | 84 | 86 | cycle documentaire gouverné dans `/juridique` : empreinte SHA-256 au client, scan, vérification quatre-yeux, soumission conditionnée (#432), prouvé navigateur sur harnais S3/ClamAV |
| GPS et géolocalisation | 75 | 85 | trajets/replay, cap, géofences, alertes, notification, SSE événementiel PostgreSQL, repli/reconnexion (#340–#359) — matériel toujours non certifié |
| Pesées et production | 82 | 82 | — |
| Pièces et pneus | 20 | 58 | stock structuré : CMP, magasins, mouvements, réservations, réappro à décision séparée, valorisation ; pneus montages/démontages/usure/coût (migrations 0053+, #304) |
| HSE | 25 | 62 | incidents/enquêtes/actions correctives (0052), inspections/checklists/non-conformités/preuves photo (0054), double regard prouvé E2E, déclaration hors ligne de bout en bout |
| Reporting/tableaux de bord | 58 | 65 | coût complet par engin (0055 : carburant + pièces + main-d'œuvre valorisée + pneumatiques), KPI fiabilité alimentés par l'OT immobilisant (#430) ; marge/revenus toujours absents |

## Métier minier — 63,0/100 (56,7 au 30 octobre)

| Capacité | 30 oct | 12 nov | Preuve nouvelle depuis le 30 octobre |
|---|---:|---:|---|
| Opérations quotidiennes | 82 | 84 | déclaration d'incident HSE hors ligne : première écriture métier synchronisable de bout en bout |
| Dispatching et transport | 82 | 82 | — |
| Gestion des équipements | 85 | 85 | — |
| Productivité/disponibilité | 65 | 65 | — |
| Maintenance des engins | 78 | 82 | préventif complet (plans/échéances/déclarations) et pièces structurées rattachées aux OT |
| Approvisionnements | 72 | 78 | cycle purchase-to-stock pièces : réapprovisionnement à décision séparée quatre-yeux, commandes depuis l'UI (#409, #430) |
| Coût par équipement | 40 | 60 | coût complet unifié par engin/période (`LIVRAISON_COUT_COMPLET.md`, migration 0055) |
| Gestion des équipes | 55 | 55 | — |
| Prévention des incidents | 25 | 62 | module HSE structuré complet côté code et tests (HSE-1, HSE-2, offline, double regard E2E) |
| Sous-traitants | 20 | 20 | — |
| Rentabilité des opérations | 20 | 20 | — |

## Technique — 78,8/100 (76,5 au 30 octobre)

| Capacité | 30 oct | 12 nov | Preuve nouvelle depuis le 30 octobre |
|---|---:|---:|---|
| Architecture | 86 | 86 | — |
| Qualité du code | 84 | 85 | anti-dérive matrice+permissions verte à chaque PR, ruff/mypy strict, double contrôle de contrat OpenAPI en CI |
| Base de données | 88 | 89 | 67 migrations additives disciplinées (33 au 30 octobre), RLS forcée sur 75 tables |
| Sécurité | 87 | 88 | sessions révocables avec audit (#375), OpenAPI et docs fermés en production, clé HMAC rate-limit dédiée (#374) |
| Isolation multi-tenant | 92 | 93 | 25 spécifications E2E tenant-isolation exécutées dans le navigateur |
| Tests automatisés | 89 | 91 | 5 733 tests pytest sur PostgreSQL 16.10 + PostGIS réel, 260 Vitest, recette API R1–R10 |
| CI/CD | 78 | 82 | images de release signées Cosign + provenance SLSA + SBOM (#376), Dependabot actif et démontré (#377–#399) |
| Performance | 70 | 71 | workflow de benchmark GPS ajouté ; p95/p99 jamais mesurés sur environnement réel |
| Sauvegarde/restauration | 58 | 64 | round-trip de restauration chiffrée automatisé en CI avec gardes RLS fail-closed ; coffre externe réel toujours absent |
| Observabilité | 52 | 56 | surveillance de santé et runbook de recette staging versionné ; alertes non éprouvées par incident réel |
| Interface utilisateur | 78 | 82 | forme canonique unique du refus d'accès (#413), pages 404 dédiées (#374), socle E2E 34 routes × 13 rôles (#408) |
| Déploiement | 68 | 71 | images de publication par digest immuables, procédure release/rollback documentée |
| Résilience | 64 | 66 | rejeu de synchronisation à 5 s après réponse perdue (#434), idempotence du parcours hors ligne |

## Relation avec la grille imposée et verdict

Ce rejeu est un outil de pilotage interne sur la grille d'origine à trois axes ; il **ne remplace pas** la grille imposée de préparation commerciale (`docs/audit/COMMERCIAL_READINESS_CURRENT.md`, 84/100 au 12 novembre), qui reste la référence de décision. Les deux grilles mesurent des choses différentes : celle-ci la profondeur métier par capacité, celle-là la préparation à la commercialisation. Le verdict de gouvernance est inchangé : **NO-GO commercialisation industrialisée, GO conditionnel pour un pilote fermé** — la progression des deux grilles repose entièrement sur des preuves consultables (code, tests, CI), jamais sur une validation terrain ou opérationnelle, et aucun des 8 prérequis terrain du `docs/qa/GO_NO_GO.md` n'est exécuté.

## Seuils de décision

- **70,3/100 (30 octobre)** : fondations solides, pas encore pilote minier complet.
- **75,5/100 (12 novembre, rejeu)** : les lacunes de code majeures (pièces, pneus, HSE, coûts) sont comblées côté logiciel ; la distance aux seuils suivants est désormais dominée par les validations terrain, plus par le code.
- **80/100 MVP consolidé** : réconcilier coûts, MTBF/MTTR et disponibilité sur données réelles.
- **85/100 pilote exploitable** : GPS réel certifié, observabilité éprouvée, restauration sur coffre externe, validation terrain.
- **90/100 SaaS industrialisé** : CD multi-env, DR, charge, SLO et gouvernance éprouvés.
- **95/100 maturité élevée** : preuves sur plusieurs exploitations, sans présumer le résultat.
