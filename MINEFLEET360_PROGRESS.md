# MINEFLEET360_PROGRESS.md

**Dernière mise à jour : 26 novembre 2026 (soir) — itération « PR en erreur + P1 offline pesage + audit phase zéro + plan VPS »**
**Dépôt : skaba89/minefleet360 — main `82b4ca9`** (`feat(pesage): tickets de pesée saisis hors ligne… (#542)`, 26 nov 2026 14:46)

> Document de continuité : réutiliser en début de chaque session pour éviter doublons et pertes de contexte. Méthode : chaque affirmation est classée **Vérifié** (exécuté/constaté ici), **Présent non validé** (dans main mais non exécuté ici), **Partiel**, **Absent** — complété par un cinquième état **Bloqué** (prêt, en attente d'une autorisation humaine) ; classification complète dans `docs/audit/AUDIT_PHASE_ZERO_2026-11-26.md`.

---

## 1. Dernier commit analysé

`82b4ca9` — merge #542 (pesage hors ligne), 26 nov 2026 14:46. Clone local neuf à jour (la sandbox a été recyclée en fin d'après-midi : re-clonage depuis origin, aucun artefact produit perdu — le dépôt et `download/` sont les seules sources de vérité). Journées 25-26 nov analysées : #514→#542 (GPS géofences/immobilisations, PMTiles, mobile Expo prototype, durcissement release/rollback, inventaire + reset staging #532-#534, dependabot ignore pytest #535, continuité #536, dependabot groupés #537-#539, flake #540, fuel offline #541, pesage offline #542).

## 2. État des PR et CI

- **PR ouvertes : 0.** Fusionnées le 26 nov : #535 (ignore pytest dependabot), #536 (continuité), #537/#538/#539 (dependabot groupés), #540 (types-pyyaml), #541 (fuel offline), #542 (pesage offline).
- **Incident « PR en erreur » du 26 nov (deux occurrences, même signature)** : job `tenant-isolation` (workflow `e2e-isolation`) rouge à l'étape Playwright « offline HSE field declaration (desktop et Android emulation) » — d'abord sur la PR #540 (13:0x), puis sur main au merge de #540 (run `45831248816`, 13:39). Diagnostic : `types-pyyaml` est un stub de typage dev, inapte à influencer un test navigateur → **flake E2E émulation Android**. Remède appliqué : rejeu des jobs en échec (rerun-failed-jobs) → **9/9 vert à chaque fois**. Le run e2e du head `82b4ca9` (14:46) était en cours à la rédaction ; verdict à confirmer au début de la prochaine session.
- Note d'outillage : le journal complet d'un run E2E est inaccessible via urllib (redirection signée Azure qui retransmet l'en-tête Authorization) ; le nom d'étape en échec (API check-runs) a suffi au diagnostic — utiliser `curl -L` si un contenu de journal est nécessaire.

## 3. Inventaire mesuré (extraction réelle du code, 26 nov soir, sur `82b4ca9`)

| Périmètre | Valeur mesurée |
|---|---|
| Modules backend (`app/`) | 19 (assignment, audit, authz, billing, costs, dispatch, finance, fleet, fuel, hse, identity, legal, maintenance, organization, partners, workforce, core, demo, seed) |
| Endpoints API | **216** (re-mesuré ; les extensions offline n'outillent des routes existantes, n'en créent pas) |
| Pages frontend | **95** (`*.tsx` sous `src/pages`) |
| Tests backend | **152 fichiers / 602 fonctions `test_`** ; suite complète exécutée localement le 26 nov : **6 434 passés + 69 sous-tests, 0 échec, 9 min 15 s** |
| Specs Playwright | **28** (`frontend/e2e/*.spec.ts`) ; vitest frontend : **394/394 verts (85 fichiers)** |
| Migrations Alembic | tête **`0077`** (geofence_dwell_threshold) |
| Rôles référentiels | 14 (`role`), 22 `role_allowed_scope` |
| Tables / FK / politiques RLS / triggers / partitions | 110 / 213 / **92** / 153 / 14 (audit mensuel) |
| Workflows CI | 5 (`ci`, `e2e-isolation`, `security-static`, `gps-benchmark-tests`, `release-images`) + dependabot 5 écosystèmes (règle `ignore:` pytest>=9.2.0 **présente sur main** depuis #535) |
| Docker Compose prod | 6 services (db, api, clamav, web, migrate, caddy) + volumes dédiés |
| Mobile | `mobile/expo-app` (Expo SDK 58, GPS avant-plan) — **prototype** |
| Offline | outbox terrain (`offline-outbox.ts`, Idempotency-Key, purge à la déconnexion, cloisonnement tenant/compte/site) : **HSE incidents + inspections, relevés compteurs, pannes/OT, étapes de mission, sorties carburant (#541), tickets de pesée (#542)** |

## 4. Modules — état par domaine

Classification complète (20 périmètres, 5 états) : **`docs/audit/AUDIT_PHASE_ZERO_2026-11-26.md`**. Synthèse : **9 Vérifié / 2 Présent non validé / 2 Partiel / 5 Absent / 2 Bloqué**.

- **Vérifié (socle et métier)** : multi-tenant + RBAC + RLS (92 politiques, job tenant-isolation vert) ; flotte/affectations/missions/rotations ; pesées (RM-071/073/074 : ajout-seul, net calculé par la base, dédup pont+numéro) ; carburant (cuves, sorties/demandes, seuils/alertes) ; HSE ; maintenance ; pneumatiques ; SaaS facturation ; **offline-first champ complet** (chaîne mission→pesée→carburant, moteur idempotent clé tenant+compte finalisé en transaction, rejeu sans doublon prouvé par tests dédiés).
- **Partiels** : A6 comptes (outillage prêt, exécution manuelle restante) ; ST-07 tâches planifiées (outillées, non installées).
- **Présents non validés** : mobile Expo (prototype, aucun build de distribution) ; release rc.7 (pipeline prêt, non construite au moment de la rédaction).
- **Absents** : réceptions/inventaires carburant hors ligne (écritures de stock — à arbitrer explicitement) ; adaptateurs télématique constructeurs (Teltonika/Queclink/Ruptela/Traccar, J1939/CAN) ; connecteurs ERP/Kora/Power BI ; Smart Dispatch optimisé + MineFleet Intelligence ; offres commerciales ; multilingue.
- **Bloqués (attente autorisation humaine)** : cutover/rollback staging réels sur l'hôte OVH (`docs/ops/PLAN_CUTOVER_VPS.md`, étape ④ verrouillée) ; A3 cosign sur le VPS.

## 5. Preuve exécutée ces itérations (25-26 nov)

1. **P0 non-régression** : environnement local reconstruit (PostgreSQL 17.12 + PostGIS 3.5.2, cluster `C.UTF-8` — la locale `C` cassait `lower()` unicode) ; **suite backend complète 6 434 + 69 sous-tests, 0 échec** ; méthode persistée (`scripts/run-pytest-full.sh`, SEC-14 base dédiée).
2. **#541 fuel offline** (fusionnée 13:07) : Idempotency-Key sur POST `/fuel/issues`, outbox, page carburant offline-aware, OpenAPI régénéré dans la PR, CI 9/9.
3. **#542 pesage offline** (fusionnée 14:46) : Idempotency-Key sur POST `/weighing-tickets` avec finalisation **dans la transaction du ticket sur les deux chemins** (201 créé, 200 renvoi identique RM-074) ; dédup métier RM-074 intacte sans clé ; page mission offline-aware (bascule status 0 avec la même clé) ; tests rejeu/rejet/compte/403 ; vitest 394/394 ; CI 9/9.
4. **Incident flake #540/main** : diagnostic + rejeus verts (voir §2).
5. **Validation #532-#534 sur base candidate locale** (itération précédente) : compare fresh/bootstrapped PASS, admin-check 14 contrôles PASS — le seul reste est l'exécution sur l'hôte réel (plan livré).
6. **Audit phase zéro + plan cutover VPS** : deux documents nouveaux livrés dans cette même PR (classification 5 états ; runbook 4 étapes, étape ④ verrouillée sur approbation).

## 6. Tests — réussis / échoués / non exécutés

- **Réussis** : backend 6 434+69 (26 nov, local, base dédiée) ; vitest 394/394 ; tsc/ruff/format/mypy 0 erreur ; OpenAPI régénéré dans les deux PR de fonctionnalité ; CI de fusion verte par construction (protection de branche) ; rejeus E2E verts après flake.
- **Échoués (puis résolus)** : flake E2E Android ×2 (26 nov) — rejeu vert chaque fois ; code produit jamais en défaut sur ces occurrences.
- **Non exécutés cette itération** : 28 specs Playwright hors CI (émulation locale) ; tests de charge GPS/SSE ; restauration réelle sur coffre externe (R1).

## 7. Score de maturité et verdict (repris, non réinventé)

- **Score officiel : 86/100** (grille imposée, réévaluation du 17 nov, PR #471). La grille n'est pas la mienne ; je ne la re-scorte pas sans méthode.
- **Verdict officiel** (`docs/qa/GO_NO_GO.md`) : **NO-GO commercialisation industrialisée ; GO conditionnel pilote fermé** — les 8 prérequis terrain (`docs/ops/PROTOCOLE_PILOTE.md`) restent **aucun exécuté**.
- Effet des itérations 25-26 nov : chaîne offline-first champ complète (différenciateur renforcé), exploitation staging outillée et prouvée hors hôte, CI dependabot normalisée ; ne lève aucun prérequis terrain → **score maintenu à 86, verdict maintenu**.

## 8. Comparaison avec le marché (qualitative, sans invention)

- **Komatsu Modular DISPATCH / Cat MineStar / Wenco / Hexagon / Pitram** : dispatch optimisé, télémetrie OEM native, ML — MineFleet n'a ni moteur d'optimisation ni intégration OEM : écart réel majeur sur ce périmètre.
- **Samsara / Geotab / Powerfleet** : télématique multi-constructeurs industrialisée ; MineFleet est au stade ingestion générique + prototype mobile.
- **Différenciateurs réels de MineFleet** : spécialisation minière africaine francophone (GNF, sous-traitants, contrôle de gestion complet), SaaS multi-tenant RLS prouvée, **offline-first champ réel désormais complet (mission→pesée→carburant)**, HSE intégré, coût complet par tonne — segment peu couvert par les géants.
- **AFTECH** : analyse détaillée toujours à produire (aucune donnée fiable — à investiguer avant toute affirmation).

## 9. Risques et blocages

1. **Flake E2E Android récurrent** (2 occurrences le 26 nov, rejeu vert) : si récurrence > 2/semaine, ajouter un retry ciblé sur l'étape et un diagnostic d'étape persisté (le remède manuel actuel est documenté en §2).
2. **Cutover staging réel sur l'hôte** : prêt, verrouillé sur approbation (`docs/ops/PLAN_CUTOVER_VPS.md`).
3. R1 (copie hors machine) toujours absente — prérequis GO pilote.
4. A3 cosign sauté sur VPS ; ST-07 non installées ; A6 manuelle restante.
5. Aucun des 8 prérequis terrain GO pilote exécuté (juriste, traceur certifié, SLO charge, Android réel, réseau mobile guinéen…).
6. **Jeton GitHub transmis par chat : à révoquer après la session** (principe ROTATION_SECRETS.md).
7. Sandbox recyclée en cours d'itération : tout artefact non poussé est perdu — pousser tôt, pousser souvent.

## 10. État DEV / REC / PROD

- **DEV** : clone neuf `82b4ca9` + scripts rejouables (`fetch-pg-debs.sh`, `pg-bootstrap.sh`, `setup-backend.sh`, `run-pytest-full.sh`, `validate-staging-reset.sh`, `creer-pr.py`, `diagnostic-ci.py`) ; reconstruisible en ~10 min après recyclage.
- **REC (staging OVH)** : rc.6 en service (`main@f888194`, schéma 0072, images signées, reçu, santé 200×3 constatée) ; moniteur 0 échec ; **le déploiement suit main : après fusion de cette PR, construire rc.7 (étape ④ du plan, verrouillée) pour livrer le pesage offline en recette**.
- **PROD** : **inexistante** — conforme au verdict.

## 11. Prochaine action prioritaire

1. **Approbation humaine du plan `docs/ops/PLAN_CUTOVER_VPS.md`**, puis exécution des étapes ①-③ (cliché, build-candidate réel, bootstrap + admin-check) avec journalisation ; l'étape ④ (cutover + bascule rc.7) reste verrouillée jusqu'à approbation explicite et checklist complète.
2. Surveiller le run e2e du head `82b4ca9` (flake attendu : rejeu si rouge, diagnostic si double rouge).
3. Arbitrage à décider : réceptions/inventaires carburant hors ligne (écritures de stock — règle de réconciliation nécessaire) ou retour au protocole pilote.
4. Révoquer le jeton GitHub transmis par chat.
