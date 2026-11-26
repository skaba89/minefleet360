# MINEFLEET360_PROGRESS.md

**Dernière mise à jour : 26 novembre 2026 — itération « phase zéro + P0 staging-reset »**
**Dépôt : skaba89/minefleet360 — main `eb86b9f`** (`ops(staging): reset sécurisé par base candidate neuve… (#532) (#534)`, 25 nov 2026)

> Document de continuité : réutiliser en début de chaque session pour éviter doublons et pertes de contexte. Méthode : chaque affirmation est classée **Vérifié** (exécuté/constaté ici), **Présent non validé** (dans main mais non testé ici), **Partiel**, **Absent**.

---

## 1. Dernier commit analysé

`eb86b9f` — merge #534 (#532), 2026-11-25. Clone local à jour (`git fetch` vérifié). 20+ commits analysés depuis `571f1e3` (#514→#534 : GPS géofences/immobilisations, PMTiles Guinée/France, icônes SVG flotte, prototype mobile Expo #524-#527, durcissement release/rollback #529-#531, inventaire + reset staging #532-#534).

## 2. État des PR et CI

- **PR ouvertes : 0** (vérifié via page `/pulls` le 26 nov). **Fermées : 533** (~65 depuis le 17 nov).
- CI de fusion : verte par construction (protection de branche : fusion uniquement avec CI verte — règle du dépôt) ; **exécution Actions directe non lue dans la sandbox** (API non interrogeable sans token ; à vérifier via `gh` authentifié si besoin).
- ⚠️ **La règle `ignore:` pytest dans `.github/dependabot.yml` est toujours absente de main** (`grep -c ignore:` = 0 sur `eb86b9f`). Risque : re-proposition récurrente de pytest ≥ 9.2.0 (bisect connu du 9 nov). Le patch `0001-chore-ci-ignorer-pytest-9.2.0…patch` (dans `download/`) reste applicable (`git apply --check` OK sur main antérieur ; re-vérifier sur `eb86b9f` avant push).

## 3. Inventaire mesuré (extraction réelle du code, 26 nov)

| Périmètre | Valeur mesurée |
|---|---|
| Modules backend (`app/`) | 19 (assignment, audit, authz, billing, costs, dispatch, finance, fleet, fuel, hse, identity, legal, maintenance, organization, partners, workforce, core, demo, seed) |
| Endpoints API | **216** (`@router.(get|post|put|patch|delete)`) |
| Pages frontend | **95** (`*.tsx` sous `src/pages`) |
| Tests backend | 143 fichiers, ~598 fonctions `test_` top-level (5 733+ tests exécutés en CI selon gouvernance du 17 nov) |
| Specs Playwright | **28** (`frontend/e2e/*.spec.ts`) |
| Migrations Alembic | tête **`0077`** (geofence_dwell_threshold) |
| Rôles référentiels | 14 (`role`), 22 `role_allowed_scope` |
| Tables / FK / politiques RLS / triggers / partitions | 110 / 213 / **92** / 153 / 14 (audit mensuel) |
| Docker Compose prod | 6 services (db, api, clamav, web, migrate, caddy) + volumes dédiés |
| Mobile | `mobile/expo-app` (Expo SDK 58, GPS avant-plan, adaptateur permissions natif) — **prototype** |
| Offline | libs frontend (`offline-scope`, `offlineDrafts`, `offline-sync-state`, `offlineLogout`, `offlineWorkOrderSubmit`) + phase 4 missions/pannes/relevés hors ligne (fusionnées #482-#485) |

## 4. Modules — état par domaine

**Terminés (vérifiés par CI + recettes + staging)** : socle multi-tenant/sites + RBAC + RLS (isolation prouvée : 97 tables RLS+FORCE, liste blanche exacte — audit A4 rc.1) ; flotte/conducteurs/affectations ; missions/rotations ; carburant (cuves, réceptions/sorties, demandes séparées, inventaires, seuils/alertes, mesures/écarts) ; GPS (ingestion JSON idempotente, carte, géofences par site, immobilisations par géofence avec seuil, alertes typées, PMTiles Guinée/France, icônes métiers) ; HSE (inspections, checklist prise de poste, incidents/actions) ; maintenance (OT, préventif, horamètre, MTBF) ; pneumatiques (95 pneus seedés, inspections) ; pesées (577 seedées) ; SaaS (plans/abonnements/facturation/quotas/support — 7 parcours prouvés) ; documents juridiques (empreinte client, quatre-yeux, S3/ClamAV réel) ; contrôle de gestion (budget prévisionnel, écarts site×mois, tarifs contrats transport, revenus) ; staging outillé (release signée + reçu, rollback, **reset par candidat neuf**).

**Partiels** : offline-first (phase 4 faite : missions/pannes/compteurs ; reste carburant/pesage/inspections hors ligne) ; mobile (prototype GPS, pas de build de distribution ni store) ; télématique (ingestion générique + partage navigateur ; **pas d'adaptateurs Teltonika/Queclink/Ruptela/Traccar ni J1939/CAN**) ; BI (KPIs embarqués ; **pas de modèle analytique gouverné ni connecteurs**) ; conformité suivi (A3 cosign : vérification signature sautée sur VPS ; A6 : outillé `audit-a6-accounts.py`, exécution manuelle restante ; ST-07 tâches planifiées non installées ; R1 coffre hors machine absent).

**Absents** : Smart Dispatch moteur d'optimisation + Control Tower consolidé ; ponts-bascules/RFID ; maintenance prédictive/ML (5 produits « MineFleet Intelligence ») ; connecteurs ERP/Kora Finance/Power BI ; offres commerciales Essential/Professional/Mining/Enterprise/Intelligence ; multilingue/multi-pays configurables.

## 5. Preuve exécutée cette itération (P0 — validation #532)

**Objectif** : valider le fonctionnement des scripts `staging-reset` (#532, fusionnés) sur base candidate isolée — sans jamais toucher staging/production.

**Méthode (docker-less, sandbox)** : reconstruction complète d'un environnement local PostgreSQL 17.12 + PostGIS 3.5.2 (paquets Debian trixie extraits sans root), base « live » simulée (migrations `0077` + admin plateforme + seed démo seed=42), base candidate `minefleet_candidate` neuve (migrations seules), copie des 9 tables référentielles par la méthode `\copy` du script officiel, catalogues produits par `staging-reset-catalog.sql`, comparaisons par `staging_reset.py`.

**Résultats (artefacts : `work/reset-validation/`)**
- `compare --phase fresh` : **PASS** — catalogue structurel identique (2742+objets ; 0 écart), données : 0 constat.
- Bootstrap `create-platform-admin` sur candidate : OK (compte créé).
- `compare --phase bootstrapped` : **PASS** — 13 tables non vides = référentiels + bootstrap plateforme uniquement ; 0 constat.
- `staging-reset-admin-check.py enroll` : **PASS — 14 contrôles réels** (refus 401 mauvais mot de passe ; émission TOTP ; confirmation enrôlement ; montée de session en MFA ; 2e connexion exige le 2e facteur ; `/me` ; listage tenants (0 client) ; **403 sur route métier pour l'admin plateforme** ; logout ; révocation du token après logout).
- Compteurs : 110 tables, 213 FK, 92 politiques RLS, 153 triggers, 14 partitions audit.
- Référentiels copiés : alembic_version 1, spatial_ref_sys 8500, license_category_ref 5, role 14, role_allowed_scope 22, saas_plan 4, vehicle_category_template 15, vehicle_category_document_template 44, vehicle_category_template_license 8.

**Non validé ici (présent, VPS-only)** : `staging-reset.sh build-candidate` réel (Compose isolé + volume neuf), `cutover`, `rollback-cutover` — nécessitent Docker sur l'hôte staging ; à exécuter avec autorisation, après `staging-reset-inventory.sh`. Aucune donnée de staging/production n'a été touchée.

**Enseignements méthodologiques** : `pg_dump` refuse les tables membres d'extension (spatial_ref_sys) — la méthode `\copy` du script officiel est la bonne ; l'ordre DELETE/INSERT des référentiels doit respecter les FK (enfants d'abord à la suppression) ; le parseur `staging_reset.py` exige la section `rows` (ne pas filtrer les lignes de catalogue).

## 6. Tests — réussis / échoués / non exécutés

- **Réussis (exécutés ici)** : séquence migrations complète ×2 (0077) ; seed démo déterministe seed=42 ; compare fresh/bootstrapped ; admin-check 14 contrôles ; bootstraps ; sondes santé API.
- **Échoués puis corrigés (outillage local, non produit)** : 3 incidents de mon script de validation (filtre catalogue trop agressif, ordre DELETE FK, filtre `wc|head` SIGPIPE) — le **code produit #532 n'a jamais échoué** ; il a au contraire détecté correctement les violations de phase lors d'un essai antérieur mal étiqueté.
- **Non exécutés cette itération** : suite pytest complète locale (5 733+ tests — exécutée en CI et documentée verte par la gouvernance du 17 nov), 28 specs Playwright, tests de charge GPS/SSE. Prochaine itération : exécution locale `pytest -q` avec base de test dédiée (`MF_CREATE_TEST_DB=true`, SEC-14).

## 7. Score de maturité et verdict (repris, non réinventé)

- **Score officiel : 86/100** (grille imposée, réévaluation du 17 nov, PR #471 « 84 → 86, verdict inchangé »). La grille n'est pas la mienne ; je ne la re-scorte pas sans méthode.
- **Verdict officiel** (`docs/qa/GO_NO_GO.md`) : **NO-GO commercialisation industrialisée ; GO conditionnel pour pilote fermé** — 8 prérequis terrain publiés (`PROTOCOLE_PILOTE.md`) mais **aucun exécuté**.
- Effet de la preuve #532 de cette itération : renforce l'item « exploitation staging » (reset réversible + bootstrap vérifié) ; ne lève aucun des 8 prérequis terrain → **score maintenu à 86, verdict maintenu** jusqu'à réévaluation par la méthode officielle.

## 8. Comparaison avec le marché (qualitative, sans invention)

- **Komatsu Modular DISPATCH / Cat MineStar / Wenco / Hexagon / Pitram** : référence mondiale du dispatch optimisé, télémetrie native constructeur, ML — MineFleet n'a pas encore de moteur d'optimisation ni d'intégration OEM : écart réel majeur sur ce périmètre.
- **Samsara / Geotab / Powerfleet** : télématique multi-constructeurs industrialisée à l'échelle ; MineFleet est au stade ingestion générique + prototype mobile.
- **Différenciateurs réels de MineFleet** : spécialisation exploitation minière africaine francophone (GNF, sites, sous-traitants, contrôle de gestion complet), SaaS multi-tenant avec isolation RLS prouvée, offline-first champ réel, HSE intégré, coût complet par tonne — segment peu couvert par les géants, pertinent pour transporteurs et sous-traitants.
- **AFTECH** : concurrent local potentiel ; analyse détaillée à produire (aucune donnée fiable en ma possession — à investiguer avant toute affirmation).

## 9. Risques et blocages

1. Règle `ignore:` dependabot toujours absente de main (PR récurrente probable au prochain cycle lundi 06:00).
2. Cutover/rollback #532 non prouvés sur l'hôte (docker requis) — à exécuter avec autorisation après inventaire lecture seule.
3. Aucune restauration de sauvegarde sur coffre externe réel (R1) — prérequis GO pilote.
4. A3 cosign sauté sur le VPS ; ST-07 tâches planifiées non installées ; A6 manuelle restante.
5. Aucun prérequis terrain des 8 blocants GO pilote exécuté (juriste, fournisseur traceur certifié, SLO charge, Android réel, réseau mobile guinéen…).
6. Suite pytest/Playwright locale non rejouée dans la sandbox cette itération.

## 10. État DEV / REC / PROD

- **DEV** : sandbox locale reconstruite et validée ici (PG 17.12+PostGIS, API 216 routes, front Vite, seed 42) ; scripts rejouables : `scripts/fetch-pg-debs.sh`, `pg-bootstrap.sh`, `setup-backend.sh`, `validate-staging-reset.sh`.
- **REC (staging OVH)** : rc.6 en service (`main@f888194`, schéma 0072, images signées, reçu), santé 200×3 constatée le 24-25 nov depuis l'extérieur ; moniteur 0 échec ; timer désactivé (ST-13).
- **PROD** : **inexistante** — aucun déploiement, conforme au verdict NO-GO commercial.

## 11. Prochaine action prioritaire

**P0, actionnable immédiatement sans tiers** : sur le VPS, avec autorisation explicite — exécuter `staging-reset-inventory.sh` puis `staging-reset.sh plan` et un **`build-candidate` réel** (projet Compose isolé + volume neuf), suivi de `bootstrap-candidate` et du même `admin-check` — clôturant la seule partie de #532 non encore prouvée en conditions réelles. En parallèle (sans risque) : pousser le patch dependabot `ignore:` pytest. Puis : exécution locale complète pytest + Playwright dans la sandbox, avant d'ouvrir le chantier P1 (offline-first extension carburant/pesage — continuité de la phase 4 déjà fusionnée).
