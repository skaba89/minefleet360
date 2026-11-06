# MineFleet 360 — audit de préparation industrielle

**État observé : 6 novembre 2026, base `main`, commit `089d8019dc67524ceb7420d42426e2c4921cc566`, complétée par le lot candidat de sauvegarde hors machine.**
Périmètre : arbre GitHub, migrations, tests, workflows CI, PR fusionnées et documentation versionnée. Il s'agit d'un audit documentaire du dépôt et des preuves GitHub disponibles, pas d'un audit de pénétration, d'une recette client ou d'une certification.

## Conclusion exécutive

MineFleet 360 est un produit logiciel avancé avec un socle métier large et des fonctions GPS récemment renforcées. La base inclut la PR [#372](https://github.com/skaba89/minefleet360/pull/372), qui ajoute un déploiement staging par images immuables et un rollback applicatif contrôlé. Le lot candidat suivant durcit la sauvegarde hors machine et étend la CI à un aller-retour synthétique GPG/rclone/checksum avant restauration, démarrage sous `mf_app` et sondes `/health` et `/ready`.

**Maturité dépôt : 70/100**, calculée avec la grille ci-dessous. Cette mesure n'est pas un score de production. L'estimation 81/100 citée auparavant est conservée comme estimation historique non certifiée et ne remplace pas cette note. Le score détaillé précédent de 62/100 (PR #338, 4 novembre) précède les PR GPS #340–#359 et est devenu obsolète pour cette capacité.

**Décision actuelle : NO-GO pour une commercialisation annoncée comme prête à l'emploi industriel et pour un déploiement national.** Un pilote technique encadré peut être préparé après sécurisation des conditions P0. Aucun déploiement de production, test matériel réel, restauration d'une sauvegarde distante ou d'une base opérationnelle, mesure de charge en environnement représentatif, revue juridique locale ou validation client n'est démontré par les preuves examinées.

## Références et méthode reproductible

- Base : [commit 089d801](https://github.com/skaba89/minefleet360/commit/089d8019dc67524ceb7420d42426e2c4921cc566), fusion de la [PR #372](https://github.com/skaba89/minefleet360/pull/372). La PR #364 avait introduit la restauration synthétique; le présent lot ajoute la prévalidation cryptographique et de transport.
- PR les plus pertinentes : [#340 carte MapLibre](https://github.com/skaba89/minefleet360/pull/340), [#341 cap et replay](https://github.com/skaba89/minefleet360/pull/341), [#342 alertes GPS](https://github.com/skaba89/minefleet360/pull/342), [#345 notifications](https://github.com/skaba89/minefleet360/pull/345), [#348–#350 SSE et limites](https://github.com/skaba89/minefleet360/pull/348), [#353–#355 LISTEN/NOTIFY](https://github.com/skaba89/minefleet360/pull/353), [#356–#359 reprise réseau et résilience](https://github.com/skaba89/minefleet360/pull/356).
- CI du HEAD : exécutions Actions `ci`, `e2e-isolation` et `security-static` en succès. Cela confirme les jobs définis dans le dépôt, pas l'exploitation réelle.
- Inventaire du HEAD : 63 migrations Alembic, 171 chemins/fichiers sous les répertoires de tests backend selon l'arbre Git, 4 workflows GitHub Actions. Ce décompte est un inventaire de chemins, pas un nombre de tests.
- Les anciens rapports restent utiles pour leur contexte mais leurs constats ne sont pas attribués au HEAD sans relecture du code. En particulier `docs/audit/FEATURE_MATRIX.md`, `AUDIT_SECURITE.md`, `AUDIT_CICD.md` et `PRODUCT_READINESS_SCORE.md` contiennent des références datées antérieures aux changements récents.

### Grille de notation

Chaque domaine reçoit une note entière de 0 à 5 selon les preuves, puis est converti au poids indiqué : `poids × note / 5`. Les notes ne récompensent pas une fonctionnalité seulement annoncée. CI verte soutient la qualité du code, mais ne remplace pas une recette terrain. Les points d'un domaine sont plafonnés au poids.

| Domaine | Poids | Note / 5 | Points | Motif vérifiable |
|---|---:|---:|---:|---|
| Fonctionnalités métier | 20 | 3,5 | 14 | Modules organisation, flotte, identité, dispatch, atelier, pièces, pneus, carburant, HSE, coûts et contrats présents; processus fournisseur, rentabilité complète des sous-traitants et parcours commerciaux incomplets ou non établis. |
| GPS et télématique | 15 | 4 | 12 | Carte multi-engins, historique/replay, cap, géofences, alertes et SSE événementiel présents dans les PR fusionnées; modèle matériel réel et SLA de latence non validés. |
| Qualité et tests | 15 | 4 | 12 | CI backend/frontend, navigateur, isolation, dépendances et contrôles migration présents; aucun essai bout en bout avec équipements et utilisateurs pilotes prouvé ici. |
| Sécurité et isolation | 15 | 4 | 12 | RLS, RBAC, MFA, tests d'isolation et scans statiques dans le dépôt et CI; absence de rapport de pentest indépendant, de DAST et de preuve d'incident/restauration réelle. |
| UX, mobile et hors ligne | 10 | 3 | 6 | PWA, parcours HSE offline et tampon GPS volatil documentés/testés; pas de synchronisation GPS durable sécurisée ni de validation Android en arrière-plan. |
| Architecture et performance | 10 | 3,5 | 7 | Monolithe modulaire et SSE avec limites/reprise; pas de latences ingestion-écran ou capacité multi-machine mesurées sur staging représentatif. |
| SaaS et exploitation | 10 | 2 | 4 | Scripts, supervision, release/rollback et round-trip CI synthétique existent; coffre externe/staging, RPO/RTO, abonnements et onboarding autonome non prouvés. |
| Documentation et commercialisation | 5 | 3 | 3 | Documentation métier et benchmark existent; tarifs, contrat/SLA commercial, support opérationnel et validation des besoins clients restent à établir. |
| **Total** | **100** |  | **70** | **Dépôt avancé; industrialisation et preuves terrain insuffisantes.** |

Recalculer avec les mêmes poids et la même règle à chaque jalon. Une note n'augmente qu'avec des preuves ajoutées, datées et liées à un commit, une exécution de test ou une recette signée. Les lacunes explicitement non vérifiées ne rapportent aucun point.

## Matrice de préparation et critères d'acceptation

| Fonctionnalité / capacité | État | Preuves consultées | Risques / inconnues | Correction ou preuve suivante | Priorité | Critères d'acceptation |
|---|---|---|---|---|---|---|
| Organisations, sites, utilisateurs, RBAC, RLS | Implémentée et testée en CI | `organization`, `identity`, `authz`, migrations; workflow `e2e-isolation` vert au HEAD | Aucun test externe indépendant; pas de rapport de recette inter-clients signé | Rejouer les parcours positifs/négatifs sur staging avec deux tenants et deux sites | P0 pilote | Tests croisés A→B refusés pour chaque route sensible; journaux sans fuite; preuve attachée |
| Parc, conducteurs, affectations | Implémenté, validation terrain absente | Modules `fleet`, `workforce`, `assignment`; tests E2E documentés | Données réelles, import et gouvernance des doublons inconnus | Préparer import pilote réversible et jeux fictifs d'abord | P1 | Import échantillon rapproché, erreurs exportables et annulation vérifiée |
| Missions, dispatch, rotations, pesées | Implémenté, validation métier absente | `dispatch`, pesées, événements et tests associés | Concurrence d'affectation et intégration pont-bascule non prouvées | Recette dispatcher avec utilisateurs et cas de conflit | P1 | Pas de double affectation; chaque pesée garde source, acteur et correction auditée; GPS n'est jamais assimilé à un tonnage |
| Maintenance, pièces, pneus, carburant, HSE | Modules avancés; rapprochement physique absent | Migrations 0017–0055 et parcours associés; documentation HSE/offline | Inventaire physique, coûts réels, connecteurs pompe et validation HSE locale non prouvés | Exécuter un scénario complet sur données de pilote autorisées | P1 | Panne→OT→pièces→intervention→validation→remise en service; écarts rapprochés; stock jamais négatif sans décision explicite |
| GPS téléphone | Implémenté avec partage explicitement consenti; limité | PR #357/#358; `docs/GPS_PHONE_VOLATILE_OFFLINE.md` | Tampon RAM perdu à suspension/fermeture; pas de suivi arrière-plan garanti | Tester sur appareils cibles, consentement/retrait, verrouillage écran et réseau perturbé | P0 pilote | Collecte interrompue à expiration/révocation; aucune revendication d'historique durable; traces de test sans coordonnées réelles |
| GPS traceurs physiques | Ingestion normalisée authentifiée, compatibilité matérielle non certifiée | Modules `gps_gateway_*`; cahier fournisseur | Pas de modèle Teltonika/Queclink réel testé et certifié | Protocole de laboratoire par modèle/firmware et adaptateur versionné | P0 pilote | Connexion appareil, authentification, doublon, données hors ordre, rejeu, révocation et pertes prouvés par capture de tests synthétiques et matériel pilote |
| Carte, historique, replay, alertes | Implémenté et testé selon PR | PR #340–#345; docs GPS | État actuel des couches visuelles/alertes doit être retesté sur staging; pas de SLA mesuré | Scénarios d'acceptation carte et alertes sur flotte fictive | P1 | état « frais/obsolète/sans signal » explicite; cap, heures et vitesse liés aux mesures; alertes dédupliquées |
| GPS SSE événementiel | Implémenté, résilience CI vérifiée; capacité opérationnelle inconnue | PR #348–#359, LISTEN/NOTIFY, backoff; CI HEAD verte | Limites par processus; NOTIFY non durable; multi-machine et latence ingestion-écran inconnues | Benchmark multi-processus avec panne contrôlée sur staging | P0 pilote | p95/p99 décidés avec métiers; perte, retard, reprise, DB/CPU/RAM et reconnexion mesurés; rattrapage REST validé |
| Mode offline métier | HSE partiel/présent; GPS téléphone volatil; autres parcours à confirmer | `hseOfflineSync`, outbox tests, `docs/OFFLINE_FIELD_ACCEPTANCE.md` | Pas de validation Android physique ni de persistance GPS approuvée | Faire un pilote HSE offline d'abord; cadrer le chiffrement avant tout stockage GPS durable | P1 | événements idempotents et chronologiques, conflits résolus, expiration/limites testées, retrait droits purge locale |
| Sécurité applicative | Contrôles dans le dépôt et scans statiques en CI | RLS/RBAC, workflow `security-static`, dépendances CI | Pentest indépendant, DAST, revue juridique et opérationnelle non attestés | Revue de sécurité indépendante avant données réelles sensibles | P0 pilote | aucun P0/P1 ouvert sans acceptation formelle; plan de correction et rapports reproductibles |
| CI/CD et migrations | CI vérifiée sur la base; CD production non établi | `.github/workflows/*.yml`; #372; test migration peuplé présent | Publication/signature des images et déploiement staging réel à rejouer depuis zéro | Publier images par digest puis exercice staging/rollback | P1 | promotion reproductible, migration compatible, rollback documenté testé sur copie |
| Sauvegarde et restauration | Round-trip synthétique comprenant chiffrement, transport rclone local, checksum, restauration et démarrage API; exercice externe/staging absent | `backup.sh`, `upload-offsite-backup.sh`, `verify-offsite-backup.sh`, `verify-restore.sh`, workflow `backup-restore` | fournisseur distant, clés opérationnelles/récupération, RPO/RTO et restauration staging non démontrés | Configurer le coffre externe retenu puis restaurer sur environnement staging isolé | P0 avant pilote réel | archive chiffrée externe lisible, restauration complète, contrôles d'intégrité, démarrage API, récupération de clé et chronométrage RPO/RTO signés |
| SaaS commercial | Partiel | vision, modules plateforme, benchmark public | abonnement, limites, factures, support et contrats commerciaux non établis | Entretiens clients/coûts hébergement/support avant choix des prix | P1 avant vente | offre testée avec coûts connus; onboarding et suspension sans perte illicite de données |
| Conformité et vie privée | Non validée professionnellement | consentement de partage, rétention GPS configurable, documentation sécurité | règles locales/pays de vente et traitement des données salariés à valider | Cartographie données et avis professionnel pays par pays | P0 avant données réelles/vente | base légale, notices, conservation, export/suppression, sous-traitants et transferts documentés et approuvés |

## Lots de travail ordonnés

1. **P0 — Baseline fiable** : mise à jour faite après #372 et le lot de sauvegarde; les matrices distinguent les preuves synthétiques CI d'une vraie reprise opérationnelle sur staging.
2. **P0 — Validation staging opérationnelle** : restaurer une sauvegarde distante de staging, valider l'API, la supervision/les alertes, le déploiement contrôlé et les SLI/SLO provisoires.
3. **P0 — Pilote GPS encadré** : appareils précis, autorisation/consentement, scénarios réseau, mesure de latence/capacité et procédure de révocation.
4. **P1 — Offline Android** : après revue de chiffrement et cycle de vie, synchronisation append-only/idempotente sur parcours HSE puis panne/inspection.
5. **P1 — Complétude métier** : contrats de sous-traitance, SLA, coûts par prestation, rapprochement pièces/carburant/pneus, rapports métier.
6. **P1 — Lancement commercial** : onboarding client, support, conditions, facturation et tarification fondée sur entretiens et coûts.
7. **P2 — Internationalisation et expansion** : i18n, monnaies/pays, capacités et conformité par marché.

Le suivi d'exécution est dans `docs/roadmap/ROADMAP_85_TO_95.md`. Une PR fusionnée reste distincte de la recette et de la validation terrain.
