# Audit phase zéro — classification à 5 états (2026-11-26)

**Périmètre** : tout le produit MineFleet360, classé à un instant T (commit `82b4ca9`, 26 nov 2026 14:46) selon une nomenclature à 5 états, avec preuve et prochain pas pour chaque ligne. Cet audit ne réinvente ni le score (86/100, grille officielle du 17 nov) ni le verdict (NO-GO commercial / GO conditionnel pilote fermé, `docs/qa/GO_NO_GO.md`) ; il sert de base factuelle unique avant la prochaine décision.

**Nomenclature** :

| État | Définition |
|---|---|
| **Vérifié** | Exécuté/constaté avec preuve datée ici (CI verte, tests, recette, staging, sondes) |
| **Présent non validé** | Existe dans main ou déployé, mais jamais exécuté devant l'auditeur |
| **Partiel** | Une partie vérifiée, une partie manquante ou non exécutée |
| **Absent** | N'existe pas dans le produit |
| **Bloqué** | Prêt et exécutable, mais en attente d'une autorisation humaine ou d'un accès externe |

## 1. Classification

| # | Périmètre | État | Preuve (datée) | Prochain pas |
|---|---|---|---|---|
| 1 | Socle multi-tenant, RBAC, RLS | **Vérifié** | 92 politiques RLS/FORCE ; job CI `tenant-isolation` vert 9/9 (#542, 26 nov) ; revues sécurité lots 1A→3A (`docs/revues/`) | Maintenir l'audit mensuel des compteurs (110 tables / 213 FK / 92 RLS / 153 triggers) |
| 2 | Métier cœur (flotte, affectations, missions/rotations, pesées, carburant, HSE, maintenance, pneumatiques) | **Vérifié** | Suite backend complète 6 434 + 69 sous-tests, 0 échec (26 nov, local, base dédiée SEC-14) ; vitest 394/394 ; 28 specs Playwright en CI ; `demo-journeys` verts | Rien — périmètre stabilisé |
| 3 | Offline-first champ (missions/étapes, HSE, compteurs, pannes/OT, carburant, pesée) | **Vérifié** | Chaîne complète fusionnée : #482-#485 (phase 4), #541 (sorties carburant, 26 nov 13:07), #542 (tickets de pesée, 26 nov 14:46) ; moteur idempotent (clé tenant+compte, finalisation en transaction, rejeu sans doublon) prouvé par tests dédiés (`test_fuel_issue_offline.py`, `test_weighing_offline.py`) | Rien — chaîne mission→pesée→carburant fermée |
| 4 | Réceptions / inventaires carburant hors ligne | **Absent** | Aucune règle d'outbox pour les écritures de stock (`offline-outbox.ts` : liste d'endpoints append-only) — choix délibéré : réconciliation de stock nécessaire avant ouverture | Arbitrage explicité (décision produit) : ouvrir avec règle de réconciliation ou maintenir en ligne |
| 5 | GPS ingestion / carte / géofences / immobilisations / PMTiles / icônes | **Vérifié** | #514→#534 (24-25 nov) ; ingestion JSON idempotente ; PMTiles Guinée/France ; workflow `gps-benchmark-tests` dédié | Benchmark de charge GPS/SSE toujours non exécuté en conditions réelles |
| 6 | Adaptateurs télématique constructeurs (Teltonika/Queclink/Ruptela/Traccar, J1939/CAN) | **Absent** | Aucun code d'adaptateur dans main ; `docs/GPS_FOURNISSEUR_CAHIER.md` préparatoire | Choix fournisseur certifié (prérequis GO pilote n° 2) |
| 7 | Mobile Expo (GPS avant-plan, permissions natives) | **Présent non validé** | `mobile/expo-app` SDK 58 fusionné (#524-#527) ; aucun build de distribution ni test sur Android réel | Test sur Android réel (prérequis GO pilote n° 4) |
| 8 | SaaS facturation (plans, abonnements, quotas, support) | **Vérifié** | 7 parcours prouvés (recette du 17 nov) ; modules billing/organization en main | Rien |
| 9 | Connecteurs externes (ERP, Kora Finance, Power BI) | **Absent** | Aucun connecteur en main | Hors périmètre pilote fermé ; à planifier après GO |
| 10 | Sécurité applicative (MFA TOTP, quatre-yeux, ClamAV réel, S3, SAST + secret scanning) | **Vérifié** | `admin-check` 14 contrôles PASS (26 nov, base candidate) ; jobs `security-static` verts sur chaque merge ; documents légaux ClamAV réels | Rotation du jeton GitHub transmis par chat (immédiat) |
| 11 | A3 cosign (vérification signature binaire) sur le VPS | **Bloqué** | Sautée lors des sessions VPS précédentes ; `legal-contract-document-security.md` décrit l'outillage | Session VPS avec approbation — à coupler au plan cutover (étape ①) |
| 12 | A6 comptes (outillage `audit-a6-accounts.py`) | **Partiel** | Script fusionné et relu ; exécution manuelle jamais faite sur staging | Exécuter en lecture seule lors de la session VPS |
| 13 | ST-07 tâches planifiées (timers systemd) | **Partiel** | Outillage documenté (`STAGING_MONITOR_SYSTEMD.md`) ; timers désactivés (ST-13) pour stabilité rc | Installer après cutover réussi (étape ④+1) |
| 14 | Sauvegardes automatisées + restauration (job CI) | **Vérifié** | Job CI `backup-restore` vert sur #542 (26 nov) ; `RESTORE_VERIFICATION.md` | Rien — mais voir n° 15 |
| 15 | R1 — copie de sauvegarde hors machine (coffre externe réel) | **Absent** | `docs/DEPLOIEMENT_OVH.md` §8 (D-41) et `PROTOCOLE_RESTAURATION_EXTERNE.md` prêts ; aucune exécution réelle | Prérequis GO pilote ; première exécution après cutover |
| 16 | Reset staging réel sur l'hôte (build-candidate → bootstrap → cutover → rollback) | **Bloqué** | Prouvé sur base candidate locale (26 nov : compare fresh/bootstrapped PASS, admin-check 14 contrôles PASS) ; scripts #532-#534 fusionnés ; inventaire lecture seule #533 fait | **`docs/ops/PLAN_CUTOVER_VPS.md` — approbation puis étapes ①-③ ; ④ verrouillée** |
| 17 | REC rc.6 en service (staging OVH) | **Vérifié** | `main@f888194`, schéma 0072, images signées avec reçu, santé 200×3 constatée (24-25 nov), moniteur 0 échec | Vérifier santé après chaque advance de main |
| 18 | Release rc.7 (livre le pesage offline en recette) | **Présent non validé** | Pipeline `release-images` prêt (rc.6 construite par ce chemin) ; rc.7 non construite à l'instant T | Construire/rc.7 puis recette — inclus à l'étape ④ du plan |
| 19 | Dispatch optimisé, MineFleet Intelligence (ML), offres commerciales, multilingue | **Absent** | Vérdict NO-GO commercial l'assume explicitement | Hors périmètre pilote fermé |
| 20 | Gouvernance documentaire (règles métier, user stories, critères GO, continuité) | **Vérifié** | `docs/` : REGLES_METIER, USER_STORIES, CRITERES_GO_PILOTE, QUALITE_AVANT_PR, STRATEGIE_QUALITE_CI ; continuité tenue par itération depuis #536 | Maintenir la discipline « pousser tôt » (sandbox recyclable) |

## 2. Synthèse

**Comptage : 9 Vérifié · 2 Présent non validé · 2 Partiel · 5 Absent · 2 Bloqué (20 périmètres).**

- Le socle et le métier (lignes 1-3, 5, 8, 10, 14, 17, 20) sont prouvés et stabilisés ; l'itération 25-26 nov a fermé la chaîne offline-first champ (ligne 3) et normalisé l'outillage CI (dependabot, non-régression locale).
- Les lignes 11, 12, 13, 16 forment un **même paquet d'exécution** : une session VPS avec approbation traite 11+12+16 d'un coup, puis 13 après cutover — c'est l'objet de `docs/ops/PLAN_CUTOVER_VPS.md`.
- Les Absents (4, 6, 9, 15, 19) se séparent en : décision produit (4), prérequis pilote (6, 15), hors périmètre pilote (9, 19).
- Risque transversal non classé : **flake E2E Android** (2 occurrences le 26 nov, rejeu vert à chaque fois — `MINEFLEET360_PROGRESS.md` §2/§9) ; mitigation à décider si récurrence.

## 3. Décisions attendues de l'humain (aucune exécutable par l'agent seul)

1. **Approuver** `docs/ops/PLAN_CUTOVER_VPS.md` (débloque lignes 11, 12, 16 ; l'étape ④ reste individuellement verrouillée).
2. **Arbitrer** la ligne 4 (réceptions/inventaires hors ligne : oui avec réconciliation / non jusqu'au pilote).
3. **Décider** la mitigation du flake E2E (retry ciblé + diagnostics d'étape) si troisième occurrence.
4. **Révoquer** le jeton GitHub transmis par chat.

## 4. Méthode et limites

Classification faite le 26 nov 2026 sur `82b4ca9` à partir : de la CI du dépôt (check-runs API), de la suite complète locale (6 434 + 69 sous-tests), des preuves documentées dans `MINEFLEET360_PROGRESS.md` et des documents sous `docs/`. Aucune affirmation n'est déduite d'un nom de fichier sans exécution ou lecture associée ; les états évoluent — re-classer à chaque itération plutôt que d'hériter.
