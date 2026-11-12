# GO / NO-GO — situation au 12 novembre 2026 (base main avec PR #426 — E2E du cycle SaaS complet + correctifs UI)

## Verdict

**NO-GO commercialisation industrialisée et déploiement large.**
**GO conditionnel pour préparer un pilote fermé**, sous réserve de respecter les blocages P0 ci-dessous. Aucun pilote terrain, déploiement production, modèle de traceur certifié, avis juridique, restauration d'une sauvegarde opérationnelle/externe ou SLO de charge n'est attesté. La CI prouve uniquement une chaîne synthétique sur infrastructure jetable — ce n'est pas une preuve de fonctionnement en conditions réelles.

Changement depuis la révision du matin : **le cycle commercial SaaS est désormais prouvé de bout en bout depuis l'interface navigateur, en CI** (PR #426 — plan tarifé et borné créé en UI, société, abonnement essai→actif, facture préremplie depuis le tarif du plan puis émise, vue support, checklist de démarrage 1/5→5/5, refus `QUOTA_EXCEEDED` à la borne, export réversibilité vérifié en contenu) et la recette a **révélé 4 défauts d'interface réels, corrigés** (dont l'absence de saisie du tarif du plan, bloquante du cycle depuis l'UI). Les **protocoles d'exécution des 8 prérequis terrain sont publiés** (staging lecture seule, restauration externe, traceur physique, Android réel) — aucun n'est encore **exécuté** ; le verdict ne change donc pas.

## Preuves positives disponibles

- Base auditée : `main` avec la PR #426 (E2E du cycle SaaS complet + correctifs UI : spec `frontend/e2e/saas-lifecycle.spec.ts` exécutée en CI dans le job `tenant-isolation` ; formulaire des plans exposant désormais tarif mensuel GNF et période ; libellés d'état corrigés sur le formulaire de facture et la vue support) ; CI `main` et PR vérifiées par API le 2026-11-12 : 9/9 contrôles verts sur la PR, fusion en squash `8d7301b`.
- Produit SaaS complet côté logiciel (4 lots sur 4 : plans/quotas #418, abonnements #419, facturation paramétrable sans activation de paiement #420, support/onboarding/réversibilité #423 — plus le lot 2b quotas appliqués au provisionnement #422 ; aucun moyen de paiement, conformément à la règle « pas d'intégration non approuvée ») — 127 permissions / 255 routes, anti-dérive verte.
- Exécution locale et CI le 2026-11-12 (PostgreSQL 16.10 + PostGIS réel, base `minefleet_test`) : **5 726 tests pytest passés** en CI, Vitest **260/260** (dont 2 assertions nouvelles tarif plans / statut facture support), `tsc` strict OK, build OK, ruff/mypy OK, anti-dérive matrice+permissions OK.
- Recette métier API R1→R10 sur serveur réel, fusionnée en PR vertes (#400–#407) : flotte, habilitations, affectations, missions/pesées, atelier, préventif, carburant, GPS bout en bout, isolation négative (IDOR/429/audit), juridique/assurance, coûts.
- Recette UI : socle d'accès direct 34 routes × 13 rôles + PLATFORM_ADMIN (#408) et **11 specs E2E d'actions métier** en CI, dont désormais **le cycle commercial SaaS complet** (#426) et le cycle juridique documentaire sur harnais S3/ClamAV (#417).
- Valeur démontrée du dispositif : **6 bugs/défauts réels détectés par la recette et corrigés** — RLS post-commit carburant (#403), `GRANT UPDATE` manquant → 500 sur le réapprovisionnement (#410), et les 4 défauts d'interface du cycle SaaS (#426 : champs tarif du plan absents, `ACTIVE` brut, statuts d'abonnement au féminin, statuts de facture bruts).
- **Protocoles d'exécution des prérequis terrain publiés** (12 novembre, sans exécution) : plan d'exécution staging lecture seule (`docs/ops/PLAN_EXECUTION_STAGING.md`), protocole de restauration externe R1 (`docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md`), protocole d'essai traceur physique (`docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`), protocole d'essai Android réel (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`).
- Procédure de recette staging consolidée publiée (`docs/ops/RECETTE_STAGING_VALIDATION.md`) et protocole de pilote fermé (`docs/ops/PROTOCOLE_PILOTE.md`) — **l'exécution sur l'hôte réel reste à faire et reste soumise à approbation**.

## Conditions BLOQUANTES avant pilote avec données opérationnelles

| Condition | État prouvé au 12 nov (après-midi) | Preuve à fournir avant décision GO |
|---|---|---|
| Environnement staging isolé et déploiement reproductible | Procédure + rollback par digest prêts ; runbook de recette consolidé (`docs/ops/RECETTE_STAGING_VALIDATION.md`) ; **plan d'exécution lecture seule publié** (`docs/ops/PLAN_EXECUTION_STAGING.md`) ; images signées publiées par CI (#376) ; **apply jamais exécuté** | exécution des phases A/B du plan sur l'hôte réel (rapport daté), puis C/D avec approbation : checklist readiness, test migration/rollback daté sur staging réel |
| Sauvegarde et restore isolé | Round-trip synthétique automatisé en CI (chiffrement, rclone, checksum, restore, gates RLS) ; **protocole d'exercice publié** (`docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md`) ; **coffre externe réel jamais exercé** | restaurer une sauvegarde staging chiffrée depuis le coffre retenu selon le protocole (14 contrôles), vérifier l'API, la récupération de clé et mesurer RPO/RTO |
| Isolation tenant/site dans la configuration de recette | R8 négative (IDOR, 429, audit) verte en CI (#405) ; socle E2E 34 routes × 13 rôles (#408) ; **staging non vérifié** | suite croisée A/B avec rôles et tenant DB applicatif sur la recette réelle |
| Confidentialité GPS/salariés et consentement | contrôles de code documentés, **revue juridique toujours absente** | notice, finalités, accès, rétention, suppression et validation professionnelle |
| Traceur physique ciblé | non certifié (adaptateur unique `minefleet-json-v1`, verrouillé par test) ; **protocole d'essai publié** (`docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`) | essai daté du modèle/firmware/protocole exact selon le protocole (banc L1–L9, terrain T1–T10) + rapport de qualification |
| Android physique / connectivité faible | essai réel non démontré (émulation Playwright uniquement) ; **protocole d'essai publié** (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`) | matrice 2 appareils × 10 scénarios exécutée, arrière-plan, réseau faible puis terrain |
| SLO GPS et capacité | aucun p95/p99 validé | benchmark staging et seuil métier signé |
| Supervision et réponse d'incident | scripts présents et testés en CI, **alertes jamais éprouvées par incident réel** | injection d'incident, alerte reçue/acquittée, exercice documenté |

## Classement des blocants GO pilote (criticité × actionnabilité)

**Criticité** : C1 = arrête le pilote s'il n'est pas levé avant J0 ; C2 = dégrade fortement le pilote ou la preuve ; C3 = délai acceptable si planifié. **Actionnabilité** : A = actionnable immédiatement (protocole prêt, reste l'accès/l'exécution) ; B = dépend d'un tiers (fournisseur, juriste, client) ; C = dépend d'une approbation explicite (mutation hôte/coffre).

| Rang | Blocant | Criticité | Actionnabilité | Premier pas concret | Outil prêt |
|---|---|---|---|---|---|
| 1 | Phases A/B staging lecture seule | C1 | **A** (accès hôte requis) | session S0–S10 du plan d'exécution | `docs/ops/PLAN_EXECUTION_STAGING.md` |
| 2 | Revue juridique GPS/données salariés | C1 | **B** (juriste guinéen) | désigner un cabinet, fournir les finalités/rétentions produit | `docs/ops/PROTOCOLE_PILOTE.md` §5 |
| 3 | Restauration externe R1 (RPO/RTO) | C1 | **C** (approbation + coffre) | exercice 14 contrôles sur instance isolée | `docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md` |
| 4 | Isolation A/B en recette réelle | C1 | **C** (après rang 1) | suite croisée 2 sociétés fictives + 1 pilote | runbook staging (A6 + recette) |
| 5 | Éprouvetage des alertes | C2 | **C** (après rang 1) | injection d'incident `docker compose stop api` (runbook §Alerte) | runbook staging |
| 6 | SLO GPS p95/p99 | C2 | **C** (après rangs 1 et 7) | benchmark staging, seuils signés | `docs/GPS_SSE_CAPACITY.md` |
| 7 | Traceur physique certifié | C2 | **B** (fournisseur + SIM) | commande d'un boîtier d'essai, banc L1–L9 | `docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md` |
| 8 | Android physique / réseau faible | C3 | **A** (2 appareils suffisants) | campagne 10 scénarios sur 2 appareils | `docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md` |

Lecture : les rangs 1, 3 et 8 sont **actionnables sans tiers** (accès/approbation seuls) ; les rangs 2 et 7 peuvent démarrer **en parallèle** dès aujourd'hui (désignation juriste, demande fournisseur). Aucun rang ne bloque la poursuite des chantiers de code P1 — mais aucun GO pilote ne peut être prononcé tant que les C1 ne sont pas levés avec preuves datées.

## Conditions bloquantes avant vente et promesse de service

- Tarification, quota GPS, rétention, support, contrat, SLA et coût de support établis. **État actualisé : le produit SaaS est complet côté logiciel** (plans/quotas #418, abonnements #419, facturation paramétrable #420, quotas appliqués au provisionnement #422, support/onboarding/réversibilité #423) **mais** les tarifs restent des paramètres non approuvés (arbitrage coût-servi + entretiens clients à faire), le suivi de règlement « payé » et l'export PDF restent à arbitrer (expert-comptable), et aucun SLA/contrat n'existe — trois restes non techniques, aucun chantier de code.
- Onboarding client, import et sortie/export testés. **État actualisé : le cycle complet est désormais prouvé depuis l'interface en CI (#426 — création jusqu'à l'export réversibilité vérifié en contenu) mais n'a jamais été exercé avec un client réel ni sur staging.**
- Politique de confidentialité et conditions validées pour la juridiction ciblée.
- Aucun constat critique/élevé d'un audit de sécurité indépendant restant sans mesure ou acceptation formelle.
- Parcours commerciaux testés avec clients pilotes, sans données simulées confondues avec données terrain.

## Décision à réévaluer

Le statut pourra évoluer vers **GO pilote** à l'issue des preuves ci-dessus, en consignant qui a approuvé, client/site concernés, durée, limites, données collectées, responsables d'incident, critères d'arrêt et plan de suppression — le **protocole de pilote fermé** (`docs/ops/PROTOCOLE_PILOTE.md`, 2026-11-12) structure désormais ces consignations : scénarios obligatoires, RACI, critères de succès mesurables, critères d'arrêt et plan de suppression. La vente avec engagement de disponibilité nécessite ensuite des mesures réelles et des termes contractuels validés.

## Score de maturité

Score **82/100** sur la grille de `docs/audit/COMMERCIAL_READINESS_CURRENT.md` (révision du 12 novembre 2026, base PR #426 ; +1 vs 81 — preuve navigateur du cycle commercial de bout en bout en CI et 4 défauts d'interface révélés puis corrigés, Commercialisation SaaS 6→7/10 ; +14 vs 68 au 9 novembre). **Le score mesure les capacités et preuves consultables ; il n'infléchit pas le verdict NO-GO** : aucun des 8 prérequis pilotes n'est validé sur le réel et aucune condition de vente n'est remplie (tarif non approuvé, contrat/SLA absent — restes non techniques, aucun chantier de code).
