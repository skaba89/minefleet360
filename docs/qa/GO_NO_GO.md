# GO / NO-GO — situation au 11 novembre 2026 (base main avec PR #416 — E2E coûts et réconciliation)

## Verdict

**NO-GO commercialisation industrialisée et déploiement large.**
**GO conditionnel pour préparer un pilote fermé**, sous réserve de respecter les blocages P0 ci-dessous. Aucun pilote terrain, déploiement production, modèle de traceur certifié, avis juridique, restauration d'une sauvegarde opérationnelle/externe ou SLO de charge n'est attesté. La CI prouve uniquement une chaîne synthétique sur infrastructure jetable — ce n'est pas une preuve de fonctionnement en conditions réelles.

Changement depuis le 6 novembre : la **profondeur de vérification** a nettement progressé (recette R1–R10, socle et actions E2E navigateur, remédiations sécurité/DevOps) et **deux bugs réels ont été trouvés et corrigés par ce dispositif** — mais **aucune condition bloquante terrain n'est levée** ; le verdict ne change donc pas.

## Preuves positives disponibles

- Base auditée : `main` avec la PR #416 (E2E navigateur : taux horaires de main-d'œuvre et réconciliation du stockage documentaire en chemin dégradé — approfondissement de preuve, aucun code produit modifié) ; CI `main` vérifiée par API le 2026-11-11 : `ci`, `e2e-isolation`, `security-static` toutes en succès ; PR #400→#415 toutes fusionnées (#412 : réévaluation de maturité avec preuves ; #413 : forme canonique du refus d'accès direct — écart n°2 de la recette UI P0 ; #414 : runbook de recette staging en lecture seule + dry-run ; #415 : E2E zones de site, politique GPS et notifications).
- Exécution locale complète le 2026-11-11 (PostgreSQL 16.10 + PostGIS réel, base `minefleet_test`) : **5 207 tests pytest passés** (harnais RLS/authz inclus — première exécution locale intégrale), Vitest **233/233**, `tsc` strict OK, build OK, ruff/mypy OK, anti-dérive matrice+permissions OK (preuves datées : `docs/audit/preuves/`).
- Recette métier API R1→R10 sur serveur réel, fusionnée en PR vertes (#400–#407) : flotte, habilitations, affectations, missions/pesées, atelier, préventif, carburant, GPS bout en bout, isolation négative (IDOR/429/audit), juridique/assurance, coûts.
- Recette UI : socle d'accès direct 34 routes × 13 rôles + PLATFORM_ADMIN (#408), écarts UI comblés — échéances d'assurance et commandes de pièces (#409) — et 9 specs E2E d'actions métier en CI : correction/annulation de pesée, réapprovisionnement quatre-yeux, acquittement d'alerte GPS, zones de site + politique GPS + notifications (#415), HSE (double regard), contrats (brouillon + refus sans preuve), taux horaires + réconciliation du stockage documentaire en chemin dégradé (#416), tenants plateforme, police d'assurance (#410, #411). Refus d'accès direct harmonisés en forme canonique unique (`<AccessDenied />`, 17 points de refus / 10 fichiers, #413).
- Procédure de recette staging consolidée publiée (`docs/ops/RECETTE_STAGING_VALIDATION.md`) : audit en lecture seule A1–A8, dry-run `plan`, protocoles RPO/RTO et d'éprouvetage des alertes — **l'exécution sur l'hôte réel reste à faire et reste soumise à approbation**.
- Valeur démontrée du dispositif : **2 bugs réels détectés par la recette et corrigés** — RLS post-commit carburant (#403) et `GRANT UPDATE` manquant à `mf_app` sur `spare_part_replenishment` (500 sur submit/decision ; migration additive 0064 + régression, #410).
- Remédiations de l'audit du 9 novembre fusionnées et testées : écran « Mes sessions » + révocations (#375), OpenAPI/docs fermés en production et clé rate-limit dédiée (#374), publication d'images signées CI (Cosign/SLSA/SBOM) + Dependabot actif (#376, bumps #377–#399).
- Les migrations, modules métiers, code GPS, tests, scripts de sauvegarde/restauration, sondes et documentation sont présents dans l'arbre ; la matrice rôles/menus/routes reste générée avec anti-dérive verte.

## Conditions BLOQUANTES avant pilote avec données opérationnelles

| Condition | État prouvé au 11 nov | Preuve à fournir avant décision GO |
|---|---|---|
| Environnement staging isolé et déploiement reproductible | Procédure + rollback par digest prêts ; **runbook de recette consolidé publié** (`docs/ops/RECETTE_STAGING_VALIDATION.md`) ; images signées publiées par CI (#376) ; **apply jamais exécuté** | exécution des phases A/B du runbook sur l'hôte réel (rapport daté), puis C/D avec approbation : checklist readiness, test migration/rollback daté sur staging réel |
| Sauvegarde et restore isolé | Round-trip synthétique automatisé en CI (chiffrement, rclone, checksum, restore, gates RLS) ; **coffre externe réel jamais exercé** | restaurer une sauvegarde staging chiffrée depuis le coffre retenu, vérifier l'API, la récupération de clé et mesurer RPO/RTO |
| Isolation tenant/site dans la configuration de recette | R8 négative (IDOR, 429, audit) verte en CI (#405) ; socle E2E 34 routes × 13 rôles (#408) ; **staging non vérifié** | suite croisée A/B avec rôles et tenant DB applicatif sur la recette réelle |
| Confidentialité GPS/salariés et consentement | contrôles de code documentés, **revue juridique toujours absente** | notice, finalités, accès, rétention, suppression et validation professionnelle |
| Traceur physique ciblé | non certifié (adaptateur unique `minefleet-json-v1`, verrouillé par test) | essai daté du modèle/firmware/protocole exact (`GPS_FOURNISSEUR_CAHIER.md`) |
| Android physique / connectivité faible | essai réel non démontré (émulation Playwright uniquement) | matrice appareil/OS, arrière-plan, réseau simulé puis terrain |
| SLO GPS et capacité | aucun p95/p99 validé | benchmark staging et seuil métier signé |
| Supervision et réponse d'incident | scripts présents et testés en CI, **alertes jamais éprouvées par incident réel** | injection d'incident, alerte reçue/acquittée, exercice documenté |

## Conditions bloquantes avant vente et promesse de service

- Tarification, quota GPS, rétention, support, contrat, SLA et coût de support établis (aucun lot SaaS démarré : 0 table plans/quotas/abonnements/facturation).
- Onboarding client, import et sortie/export testés.
- Politique de confidentialité et conditions validées pour la juridiction ciblée.
- Aucun constat critique/élevé d'un audit de sécurité indépendant restant sans mesure ou acceptation formelle.
- Parcours commerciaux testés avec clients pilotes, sans données simulées confondues avec données terrain.

## Décision à réévaluer

Le statut pourra évoluer vers **GO pilote** à l'issue des preuves ci-dessus, en consignant qui a approuvé, client/site concernés, durée, limites, données collectées, responsables d'incident, critères d'arrêt et plan de suppression. La vente avec engagement de disponibilité nécessite ensuite des mesures réelles et des termes contractuels validés.

## Score de maturité

Score **76/100** sur la grille de `docs/audit/COMMERCIAL_READINESS_CURRENT.md` (révision du 11 novembre 2026, base `2bc1b7d` ; +2 vs 74 — forme canonique du refus d'accès direct testée #413, runbook de recette staging publié ; +8 vs 68 au 9 novembre — remédiations vérifiées #374–#376, recette R1–R10 #400–#407, socle et actions E2E #408–#411). L'ancienne note interne 70/100 (base `089d801`, grille différente) est retirée au profit de cette grille unique. **Le score mesure les capacités et preuves consultables ; il n'infléchit pas le verdict NO-GO** : aucun des 8 prérequis pilotes n'est validé sur le réel.
