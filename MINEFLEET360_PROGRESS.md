# MINEFLEET360_PROGRESS.md

**Dernière mise à jour : 27 novembre 2026 — itération « diagnostic flake #572 + drapeaux qualité GPS §1.3 + dispatch minier en flux »**
**Dépôt : skaba89/minefleet360 — main `c2ed25d3`** (`feat(fleet): référentiel versionné des profils techniques miniers (#592)`, 27 nov 2026)

> Document de continuité : réutiliser en début de chaque session pour éviter doublons et pertes de contexte. Méthode : chaque affirmation est classée **Vérifié** (exécuté/constaté ici), **Présent non validé** (dans main mais non exécuté ici), **Partiel**, **Absent** — complété par un cinquième état **Bloqué** (prêt, en attente d'une autorisation humaine) ; classification complète dans `docs/audit/AUDIT_PHASE_ZERO_2026-11-26.md`.

---

## 1. Dernier commit analysé

`c2ed25d3` — merge #592 (référentiel versionné des profils techniques miniers), 27 nov 2026. Clone local neuf à jour (sandbox recyclée : re-clonage + venv refaits, aucun artefact produit perdu — le dépôt et `download/` sont les seules sources de vérité). Journées 26-27 nov analysées : #545→#547 (benchmark GPS, harnais contractuel, SSE sous trafic), #562 (phase 2 GPS close + simulateur §1.3), #572 (dispatch, flake diagnostiqué), #575 (drapeaux qualité GPS), #578→#592 (dispatch minier : traçabilité tronçons, restrictions de circulation et dimensionnelles, gabarits, pentes directionnelles, prévisualisations, profils techniques versionnés).

## 2. État des PR et CI

- **PR ouverte : 1** — #591 « contrôle technique préalable des réseaux miniers », **9/9 verte** (`d41c76a8`), en attente de fusion humaine.
- **main `c2ed25d3` : 9/9 verte** (backend, tenant-isolation, demo-journeys, ops-monitoring, frontend, browser-smoke, SAST, secret scanning, backup-restore) — vérifié par API GitHub le 27 nov.
- **Incident « PR en erreur » du 27 nov** : job `tenant-isolation` rouge sur #572 — test e2e `hse-inspection-offline.spec.ts:154` (chromium) en timeout 30 s sur un bouton après `reload()` hors ligne. Croisement : même job déjà rouge sur `main@5daf68f0` sur un AUTRE test (`hse-offline.spec.ts:138`), repassé sans correctif entre-jeu → **flake e2e hors-ligne chromium**, code dispatch non impliqué. Le job a été repris (rerun 403 « already running » : déjà en reprise) et est **revenu success** : #572 9/9 puis fusionnée. Journal complet téléchargé via `curl -L` (le contournement de la redirection Azure du 26 nov a fonctionné). Diagnostic consigné sur la PR ([commentaire](https://github.com/skaba89/minefleet360/pull/572#issuecomment-7216377067)) avec suggestion de stabilisation (attendre l'élément avec `expect(...).toBeVisible()` tolérant après reload au lieu d'un `click()` strict à 30 s).
- Bilan flake cumulé : **4 occurrences en 2 jours** (26 nov Android ×2, 27 nov chromium ×2) — seuil de récurrence défini en §9 du 26 nov **atteint** : le remède outillé (retry ciblé + diagnostic d'étape persisté) est en backlog au flux propriétaire.

## 3. Inventaire mesuré (extraction réelle du code, 27 nov, sur `c2ed25d3`)

| Périmètre | Valeur mesurée (méthode) |
|---|---|
| Modules backend (`app/`) | **23** (ls) — 19 au 26 nov : +dispatch étendu, fleet profils techniques, iot |
| Routes (@router décorateurs) | **222** (grep) — méthode ≠ OpenAPI (216 le 26 nov) ; extensions dispatch d'hier+aujourd'hui |
| Tests backend | **165 fichiers / 648 fonctions `test_`** (find/grep) — 152/602 au 26 nov |
| Specs Playwright | `frontend/e2e/*.spec.ts` : 28 au 26 nov (non re-mesuré) ; `e2e-field/` : **5 specs = 28 tests terrain** (comptés dans les logs CI) |
| Migrations Alembic | tête **`0088`** (mining_vehicle_profile) — 0077 au 26 nov ; 0084 = drapeaux qualité GPS |
| Rôles / RBAC | 14 rôles / 22 scopes au 26 nov (non re-mesuré) |
| Tables / RLS / triggers | 110 / 92 / 153 au 26 nov (non re-mesuré) |
| Workflows CI | 5 + dependabot 5 écosystèmes (au 26 nov, inchangé à connaissance) |
| Docker Compose prod | 6 services (au 26 nov, inchangé à connaissance) |
| Offline champ | outbox + Idempotency-Key : HSE incidents+inspections, relevés, pannes/OT, missions, carburant, pesée (inchangé ; suites offline e2e-field vertes en CI) |

Suite backend complète en local : **non exécutée le 27 nov** (pas de PostgreSQL dans le sandbox recyclé ; la validation DB est la charge de la CI, verte).

## 4. Modules — état par domaine

Classification complète (20 périmètres, 5 états) : **`docs/audit/AUDIT_PHASE_ZERO_2026-11-26.md`** (réévaluer à la prochaine passe de grille). Changements depuis le 26 nov :

- **Vérifié (nouveau)** : **drapeaux de qualité GPS §1.3** `late`/`clock_skew_suspect` évalués à l'ingestion, seuils configurables, 4 scénarios par vraie API avec attente réelle (#575, 0084) ; **simulateur service-level §1.3** 5 scénarios (#562) ; **harnais contractuel d'adaptateurs** 13 tests (#546).
- **Présent non validé (nouveau, terrain)** : **dispatch minier réseau** — fermetures de pistes, restrictions directionnelles/dimensionnelles, gabarits, pentes, prévisualisation d'itinéraires, profils techniques versionnés (#569→#592) : en CI verte, aucune validation terrain.
- **Écarts GPS restants (§1.3/§1.5)** : recalcul des états après tardif ; quarantaine de l'horodatage futur ; conservation brute `telematics_raw_event` (rétention : avis juriste requis).

## 5. Preuve exécutée ce 27 nov

1. **Sync double** (matin + après-midi) : main 9/9 ×2, aucune PR en erreur à l'instant vérifié.
2. **Diagnostic flake #572 complet** : logs job récupérés (curl -L), croisement avec l'échec main@5daf68f0, reprise auto confirmée, retour 9/9, commentaire de diagnostic posté sur la PR — code dispatch innocenté.
3. **#575 drapeaux qualité** (fusionnée le 27 nov) : réglages `gps_late_threshold_seconds`/`gps_clock_skew_tolerance_seconds` bornés, colonnes 0084, calcul dans la transaction d'ingestion, 4 scénarios API attente réelle, CI 9/9 ; distinction documentée avec `negative_skew_count` de `/gps/metrics`.
4. **Inventaire re-mesuré** (§3) et **document de continuité mis à jour** (ce fichier, via PR).

## 6. Tests — réussis / échoués / non exécutés

- **Réussis** : CI 9/9 sur main `c2ed25d3` et #591 ; suites offline e2e-field 28/28 (dans CI #575) ; ruff 0 erreur (5 fichiers #575) ; harnais contractuel 13/13 ; réglages Settings vérifiés par lecture (10 s/2 s en test).
- **Échoués (puis résolus)** : flake e2e chromium hors-ligne sur #572 (job repris, 9/9) — cf. §2.
- **Non exécutés** : suite backend complète locale (sandbox sans PostgreSQL) ; 28 specs Playwright hors CI ; tests de charge GPS/SSE ; restauration sur coffre externe (R1).

## 7. Score de maturité et verdict (repris, non réinventé)

- **Score officiel : 86/100** (grille imposée, réévaluation du 17 nov, PR #471). Grilles annexes datées : 75,5/100 maturité métier interne (`docs/MATURITY_SCORECARD.md`, 13 nov) ; 84/100 préparation commerciale (`docs/audit/COMMERCIAL_READINESS_CURRENT.md`, 13 nov). Pas de nouvelle passe de grille depuis — ne pas citer ces chiffres sans leur date.
- **Verdict officiel** (`docs/qa/GO_NO_GO.md`) : **NO-GO commercialisation industrialisée ; GO conditionnel pilote fermé** — les 8 prérequis terrain restent **aucun exécuté**.
- Effet de l'itération 27 nov : traçabilité de fraîchette GPS renforcée (drapeaux requêtables), dispatch minier enrichi en CI, flake outillé en diagnostic — ne lève aucun prérequis terrain → **score maintenu à 86, verdict maintenu**.

## 8. Comparaison avec le marché (qualitative, sans invention)

- Inchangé vs le 26 nov : pas de moteur d'optimisation ni d'intégration OEM face à Komatsu/Cat/Wenco/Hexagon/Pitram ; pas de télématique multi-constructeurs industrialisée face à Samsara/Geotab/Powerfleet.
- Différenciateur renforcé : la fraîchette réelle des positions devient requêtable (`late IS NOT TRUE`) avec horodatages jamais corrigés — argument terrain pour la connectivité intermittente des mines (souterrain, zones blanches), démontré par tests à attente réelle.
- AFTECH : toujours sans données fiables — à investiguer avant toute affirmation.

## 9. Risques et blocages

1. **Flake e2e hors-ligne : seuil de récurrence atteint** (4 en 2 jours, Android + chromium) — appliquer le remède outillé prévu : retry ciblé sur l'étape e2e + diagnostic d'étape persisté (le manuel est documenté en §2).
2. **Cutover staging réel** : prêt, verrouillé sur approbation (`docs/ops/PLAN_CUTOVER_VPS.md`) ; **le VPS `~/minefleet360` n'est pas un dépôt git** — plan d'alignement en 4 étapes prêt, étape ④ verrouillée.
3. R1 (copie hors machine) toujours absente — prérequis GO pilote.
4. A3 cosign sauté sur VPS ; ST-07 non installées ; A6 manuelle restante.
5. Aucun des 8 prérequis terrain GO pilote exécuté.
6. **Jeton GitHub transmis par chat : à révoquer après la session** (principe ROTATION_SECRETS.md).
7. **Rétention du futur ledger brut §1.5 : avis juriste requis** avant implémentation (chantier suivant du §1.3).

## 10. État DEV / REC / PROD

- **DEV** : clone neuf `c2ed25d3` + venv refaits (27 nov) ; reconstruisible en ~10 min après recyclage (scripts persistés).
- **REC (staging OVH)** : rc.6 en service ; **staging opérationnel** (état rapporté par la session de déploiement du 27 nov) : `https://minefleet.51-75-248-4.sslip.io` health 200 via Caddy, admin plateforme créé, seed démo validé (26 contrôles, données 100 % virtuelles, seed 42), `staging-reset.sh` sur main, validation sur base candidate isolée (#532). **Suivre main : après fusion de #591, construire la rc suivante (étape ④ du plan, verrouillée)**.
- **PROD** : **inexistante** — conforme au verdict.

## 11. Prochaine action prioritaire

1. **Fusion de #591** (9/9, prête) — puis construire la rc suivante (étape ④ du plan cutover, après approbation).
2. **Approbation humaine** des étapes ①-④ du plan VPS (`docs/ops/PLAN_CUTOVER_VPS.md`) ; aligner `~/minefleet360` sur git selon le plan en 4 étapes.
3. **Moi, à la fusion de #591** : tranche suivante du §1.3 — **conservation brute `telematics_raw_event`** (ledger d'ingestion avec issue de traitement, rétention courte par défaut, purge tracée ; prépare la quarantaine de l'horodatage futur ; bornée par l'avis juriste sur la rétention).
4. Stabilisation du flake e2e hors-ligne (retry ciblé + diagnostic persisté) — à coordonner avec le flux dispatch propriétaire des specs.
5. Arbitrage restant : réceptions/inventaires carburant hors ligne (écritures de stock) ou retour au protocole pilote.
6. **Révoquer le jeton GitHub transmis par chat.**
