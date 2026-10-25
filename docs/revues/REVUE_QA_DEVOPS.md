# Revue critique QA / DevOps de la phase de cadrage — MINEFLEET 360

> Statut : **revue documentaire (phase 0)**, rédigée par l'ingénieur QA/DevOps. Date de référence : 2026-10-25.
> Périmètre lu : `CLAUDE.md`, `docs/00_SOCLE_CADRAGE.md`, `PRD_MVP.md`, `USER_STORIES.md`, `MODELE_CONCEPTUEL.md`, `DICTIONNAIRE_DONNEES.md`, `REGLES_METIER.md`, `MATRICE_RBAC.md`, `MENACES_ET_CONTROLES.md`, `INTEGRATION_GPS_OFFLINE.md`, `ARCHITECTURE.md`, `PRODUCT_VISION.md`, `ROADMAP.md`, `adr/ADR-001` à `ADR-005`, `PARCOURS_UTILISATEURS.md` (lu partiellement, par recherche ciblée : il est en cours d'écriture), skills `test-quality` et `delivery-review`.
> Stratégie qualité, NFR, CI, DoD : voir `docs/STRATEGIE_QUALITE_CI.md`.

## 0. Ce qui a été fait et ce qui ne l'a pas été

| Élément | État |
|---|---|
| Lecture croisée des documents ci-dessus | **Fait** (relecture humaine/LLM, pas d'outil de cohérence automatique) |
| Constats d'environnement : `make` et `gh` absents du PATH de Git Bash, `core.autocrlf=true`, Docker 29.5.3 présent, branche `master` sans commit | **Vérifié** par commandes lors de cette revue |
| Exécution de tests, de linters, de builds, de Docker compose | **Non fait** : il n'existe aucun code, aucune configuration |
| Exhaustivité de la comparaison des documents | **Non garantie** : les écarts listés sont ceux trouvés ; d'autres peuvent subsister, notamment dans les parties de `MENACES_ET_CONTROLES.md` §7 (conformité) et `DICTIONNAIRE_DONNEES.md` §6 non relues ligne à ligne |
| Parcours utilisateurs | Relu par mots-clés seulement ; le document évolue encore |

Gravité : **bloquant** = les tests du Lot 1 ne peuvent pas être écrits de façon univoque, ou une règle de sécurité est contradictoire, tant que ce point n'est pas arbitré ; **majeur** = un critère d'acceptation est faux, incomplet ou non testable, avec risque de rework ou de faille ; **mineur** = nettoyage ou précision, sans risque immédiat.

## 1. Synthèse

- 32 constats : **5 bloquants** (QA-01 à QA-05), **18 majeurs** (QA-06 à QA-23), **9 mineurs** (QA-24 à QA-32).
- Cause racine dominante : les documents ont été rédigés en parallèle sur le même socle mais **sans glossaire d'énumérations ni table de décision des codes HTTP**. Il en résulte trois vocabulaires de statuts (EN dans les stories, FR dans le dictionnaire et les règles), des réponses 403/404 qui varient d'un document à l'autre et une matrice d'autorisation des stories (§0.2) qui diverge de `MATRICE_RBAC.md`.
- Les tests d'isolation « générés depuis la matrice » (ST-02) sont la meilleure idée du plan de sécurité, mais ils supposent un fichier `authz_matrix.yaml` **qui n'existe pas** et une règle 403/404 **non tranchée**. Tant que QA-03, QA-04 et QA-21 ne sont pas levés, ST-02 est un test sans oracle.
- Le Lot 1 est large pour une petite équipe (QA-20) ; un découpage en trois tranches verticales est proposé.
- Rien n'a été implémenté : toutes les corrections ci-dessous portent sur des documents.

## 2. Tableau des constats

| ID | Gravité | Sujet | Fichiers principaux |
|---|---|---|---|
| QA-01 | Bloquant | Résolution du tenant à la connexion + RLS avant authentification | `DICTIONNAIRE_DONNEES.md` §3, `USER_STORIES.md` US-1.08, `adr/ADR-002`, `adr/ADR-003` |
| QA-02 | Bloquant | Trois vocabulaires de statuts incompatibles | `USER_STORIES.md` §0.3, `DICTIONNAIRE_DONNEES.md`, `REGLES_METIER.md`, `MODELE_CONCEPTUEL.md` §4 |
| QA-03 | Bloquant | Règle 403 / 404 / 422 non univoque | `USER_STORIES.md` CT-1, `MATRICE_RBAC.md` §1.1, `adr/ADR-002` §3.5, `REGLES_METIER.md` RM-003, `MENACES_ET_CONTROLES.md` ST-xx |
| QA-04 | Bloquant | Matrice d'autorisation des stories vs `MATRICE_RBAC.md` | `USER_STORIES.md` §0.2, `MATRICE_RBAC.md` §2 |
| QA-05 | Bloquant | Cycle de vie de l'affectation : refus vs suspension automatique | `USER_STORIES.md` US-1.14/1.21/1.22/1.25, `REGLES_METIER.md` RM-017/031/036/038/039/051, `DICTIONNAIRE_DONNEES.md` §11 |
| QA-06 | Majeur | Dérogation d'éligibilité et antidatage | `MATRICE_RBAC.md` §2.5, `USER_STORIES.md` US-1.22 R8, `REGLES_METIER.md` RM-041, ST-52 |
| QA-07 | Majeur | Dernier admin, auto-modification de rôle | `USER_STORIES.md` US-1.06/1.07, `MATRICE_RBAC.md` §4.2, ST-23/24 |
| QA-08 | Majeur | Transitions dépendant du temps sans planificateur ni horloge injectable | `REGLES_METIER.md` RM-031/036, `USER_STORIES.md` US-1.25, `adr/ADR-001`, `adr/ADR-004` |
| QA-09 | Majeur | Idempotence exigée au Lot 1, absente du modèle | `USER_STORIES.md` US-1.12 A8, US-1.22 A15, `DICTIONNAIRE_DONNEES.md`, `INTEGRATION_GPS_OFFLINE.md` §2.1 |
| QA-10 | Majeur | Contrat d'audit : colonnes, refus, contenu avant/après | `adr/ADR-005`, `DICTIONNAIRE_DONNEES.md` §13, `USER_STORIES.md` CT-2/US-1.27, `REGLES_METIER.md` RM-003/004, `MATRICE_RBAC.md` §5 |
| QA-11 | Majeur | Données personnelles du conducteur divergentes | `DICTIONNAIRE_DONNEES.md` §8, `PRD_MVP.md` §8, `MATRICE_RBAC.md` §5, `REGLES_METIER.md` RM-028 |
| QA-12 | Majeur | Statut et éligibilité du permis / de l'habilitation | `USER_STORIES.md` US-1.18/1.19/1.22, `DICTIONNAIRE_DONNEES.md` §9-10, `REGLES_METIER.md` RM-024/029 |
| QA-13 | Majeur | Éligibilité sur intervalle ouvert | `USER_STORIES.md` US-1.22 R5/A8, RM-030(c) |
| QA-14 | Majeur | Paramètres d'acceptation non fixés (tolérances, seuils, N) | US-1.05/1.08/1.20/1.23, RM-037/067/068, Q21/Q22 |
| QA-15 | Majeur | Critères non testables ou alternatifs | voir §4 |
| QA-16 | Majeur | Questions ouvertes qui bloquent des critères | `USER_STORIES.md` §3, `PRD_MVP.md` §14 |
| QA-17 | Majeur | Référentiels globaux vs « toute table métier a `tenant_id` » ; catégories de véhicule sans story | `DICTIONNAIRE_DONNEES.md` §4/6, ST-05, US-1.11 |
| QA-18 | Majeur | Amorçage de la plateforme (1er `PLATFORM_ADMIN`, seed) | `MATRICE_RBAC.md` §2.2/4.1, `USER_STORIES.md` US-1.01/1.30, `adr/ADR-002` §3.4 |
| QA-19 | Majeur | Périmètre Lot 1 : le plan de tests couvre des fonctions sans story | RBAC export/link-account/support, ST-28/35/44/45/57/72/75/76 |
| QA-20 | Majeur | Faisabilité du Lot 1 (taille, risques techniques) | `PRD_MVP.md` §6, ADR-001 à 005 |
| QA-21 | Majeur | Artefacts de test absents (matrice YAML, contrat API, catalogue d'erreurs, DECISIONS) | `MATRICE_RBAC.md` §2, `00_SOCLE_CADRAGE.md` §2, `ARCHITECTURE.md` §5 |
| QA-22 | Majeur | Fuseau par défaut à décalage nul : les bugs de fuseau seraient invisibles | H4, RM-005/021, US-1.18 A8, US-1.22 A16 |
| QA-23 | Majeur | Pas de dépôt distant : CI, protection de branche et branche `main` impossibles en l'état | `00_SOCLE_CADRAGE.md` §1, `adr/ADR-004` |
| QA-24 | Mineur | Mécanisme de concurrence optimiste non spécifié | CT-4, `DICTIONNAIRE_DONNEES.md` `row_version`, `INTEGRATION_GPS_OFFLINE.md` §2.5 |
| QA-25 | Mineur | Pagination, tri, format d'erreur non définis | US-1.13 A1, CT-3, ST-07 |
| QA-26 | Mineur | Nommage : permissions, actions d'audit, clés primaires, routes | RBAC, ADR-005, DICTIONNAIRE, ST-xx |
| QA-27 | Mineur | Rotation du refresh (période de grâce) vs ST-62 ; cookies `Secure` en local | `adr/ADR-003` §3.3, ST-62 |
| QA-28 | Mineur | Poste Windows : `make` absent, fins de ligne, Python 3.10 local | `adr/ADR-004`, environnement |
| QA-29 | Mineur | UUID v7 « si disponible » | H2 |
| QA-30 | Mineur | Code HTTP pour tenant suspendu / jeton valide mais droits retirés | US-1.02, ST-63/67/68 |
| QA-31 | Mineur | Numérotation des questions en collision | `PRD_MVP.md` §14, `USER_STORIES.md` §3, `REGLES_METIER.md` §11 |
| QA-32 | Mineur | Limitation de débit sans Redis | C-31, ST-08, H8 |

## 3. Détail des constats

### Bloquants

**QA-01 — Résolution du tenant à la connexion et RLS avant authentification** (Bloquant)
- Constat : `user_account.email` est unique **par tenant** (`DICTIONNAIRE_DONNEES.md` §3 : `UNIQUE (tenant_id, email)`), mais US-1.08 et ADR-003 prévoient une connexion par **e-mail + mot de passe seul**, sans sélecteur de tenant. Si deux tenants ont le même e-mail (Q16 propose « un compte = un tenant », sans l'inscrire en contrainte), la connexion est ambiguë. Par ailleurs, ADR-002 §3.1 fait refuser toute ligne à la RLS quand `app.tenant_id` est absent : la recherche du compte **avant** l'authentification (donc sans contexte) retourne 0 ligne, et les comptes plateforme (`tenant_id` NULL) ne satisfont jamais `tenant_id = current_setting(...)`.
- Impact tests : ST-60 (indiscernabilité des réponses de connexion), ST-03 (RLS), US-1.08 A1-A4 ne sont pas écrivables ; risque de contournement de la RLS par un rôle trop puissant pour « faire marcher » le login.
- Correction proposée : arbitrer (a) e-mail **globalement unique** pour les comptes non plateforme (contrainte d'unicité sur `citext`, indépendante du tenant) ou (b) identifiant de tenant saisi à la connexion (en tension avec C-40 anti-énumération). Spécifier le chemin de recherche pré-authentification (fonction `SECURITY DEFINER` limitée, ou politique RLS dédiée sur les colonnes strictement nécessaires) et les politiques RLS des tables à `tenant_id` NULL (`user_account` plateforme, `audit_event` plateforme). Ajouter un test ST dédié « login sous `mf_app` avec RLS forcée ».

**QA-02 — Vocabulaires de statuts incompatibles** (Bloquant)
- Constat :
  - véhicule : `ACTIVE / IN_MAINTENANCE / OUT_OF_SERVICE / RETIRED` (US §0.3, PRD E1) vs `DISPONIBLE / EN_MAINTENANCE / IMMOBILISE / HORS_SERVICE / REFORME` (dictionnaire, MODELE §4.1, RM-014/015) — le nombre de valeurs diffère (4 vs 5) ;
  - conducteur : `ACTIVE / INACTIVE` vs `ACTIF / INDISPONIBLE / SUSPENDU / INACTIF` ;
  - affectation : `PLANNED / ACTIVE / CLOSED` vs `PLANIFIEE / ACTIVE / SUSPENDUE / TERMINEE / ANNULEE` ;
  - compte : `INVITED / ACTIVE / DISABLED` vs `INVITE / ACTIF / VERROUILLE / DESACTIVE` ; tenant : `ACTIVE / SUSPENDED` vs `ACTIF / SUSPENDU / ARCHIVE` ;
  - permis : `VALID / EXPIRING / EXPIRED` (dérivé, US-1.18) vs `VALIDE / SUSPENDU / RETIRE` (stocké, dictionnaire) ;
  - codes d'erreur des stories en anglais (`VEHICLE_ASSIGNMENT_OVERLAP`, `DRIVER_NOT_QUALIFIED`) alors que les valeurs stockées sont en français ; `outcome` d'audit `SUCCES/REFUSE/ECHEC`.
- Impact tests : les enums OpenAPI, les `CHECK` SQL, les fixtures et les assertions ne peuvent pas être écrits ; le test de contrat échouera dès la première implémentation choisie.
- Correction proposée : un **glossaire d'énumérations unique** (`docs/GLOSSAIRE_ENUMS.md`, puis constantes générées dans le code) avec : code technique stocké (anglais ou français, un seul choix), libellé français d'affichage, transitions autorisées. Recommandation QA : **codes techniques en anglais** (cohérent avec « identifiants techniques en anglais » du socle et avec les codes d'erreur déjà en anglais) et libellés français côté interface ; aligner les 4 documents. Distinguer explicitement statut **stocké** et statut **dérivé** (`EXPIRING`, « en exploitation »).

**QA-03 — Règle 403 / 404 / 422 non univoque** (Bloquant)
- Constat :
  - CT-1 : autre tenant **ou site hors portée** → 404 ; absence de droit sur une ressource visible → 403 ; marqué *(proposition)*, alors que RBAC §1.1.6, ADR-002 §3.5 et RM-003 le présentent comme acquis.
  - RBAC §1.1.6 : l'étape 1 donne 404 pour un autre tenant, mais les étapes 2 à 4 (permission absente, portée non couverte, règle d'objet) se terminent par « refus » sans code ; ST-02 attend « 2xx ou 403 » y compris pour une portée `SITE` non couverte (alors que CT-1 et ST-36/49 attendent 404).
  - Alternatives écrites dans les critères : US-1.12 A4 « 404 (site) / refus », US-1.16 A3 « 404/refus », US-1.22 A11 « 404/403 », US-1.04 A3 « 422 (… = 404 sémantique) », RBAC §4.3 « 404/403 ou liste vide », ST-22 « 404/422 », ST-24 « 409/403 », ST-32 « 422/404 », ST-42 « 404/403 ».
  - Identifiant de ressource étrangère **dans le corps** : 422 (US-1.12 A5) ou 404 (US-1.22 A10) ?
  - RM-003 impose en plus que ces refus soient **audités** (`outcome=REFUSE`) ; CT-2 et US-1.27 A2 ne parlent que des écritures refusées ; RBAC ne cite que les « ressources sensibles ».
- Impact tests : l'« utilitaire de réponse équivalente » (§8.1 de MENACES) et ST-02 n'ont pas d'oracle ; un développeur peut renvoyer 403 pour un site hors portée et satisfaire une lecture du document.
- Correction proposée : adopter une **table de décision ordonnée**, à inscrire dans RBAC §1.1 et reprise par les ADR/stories :
  1. non authentifié ou jeton invalide → 401 ;
  2. l'utilisateur ne possède **aucune** affectation de rôle active portant la permission (indépendamment de la portée et de l'existence de la ressource) → 403 ;
  3. ressource inexistante, d'un autre tenant, hors portée de site, ou échec de la règle d'objet « propriétaire » → 404 identique (corps, en-têtes) ;
  4. référence à une ressource inexistante/étrangère dans le corps → 422 avec code unique `REFERENCE_INTROUVABLE` (indiscernable inexistant/étranger) ;
  5. conflit d'état ou de version → 409 ; validation → 422 ; limitation → 429.
  Préciser l'audit : tout refus 403 est audité ; les 404 « cross-tenant » sont comptés par métrique et journal technique, et audités **avec échantillonnage ou plafond** pour éviter le déni de service par le journal (voir QA-10). Réécrire ST-02, ST-22, ST-24, ST-32, ST-42 avec un code unique.

**QA-04 — Matrice des stories vs `MATRICE_RBAC.md`** (Bloquant)
- Constat (écarts relevés, list non exhaustive) :

| Objet | `USER_STORIES.md` §0.2 / stories | `MATRICE_RBAC.md` / `DICTIONNAIRE` |
|---|---|---|
| `TENANT_ADMIN` et conducteurs | `driver` : C R* U A ; `driver_license`/`qualification` : C R U | tous ❌ (séparation des tâches §1.1.8, §4.2.6) |
| N° de permis lisible | `HR` et `TENANT_ADMIN` (§0.2 note, US-1.17, PRD §8, PARCOURS) | `HR` seul (+ titulaire) ; `TENANT_ADMIN` ❌ |
| Écriture de permis | US-1.18 A7 : `HR`/`TENANT_ADMIN` | `HR` seul (`driver_license.manage`) |
| `HSE` et habilitations | US-1.19 A5 : lecture seule, 403 en écriture (Q23) | `driver_qualification.manage/revoke` ✅ pour `HSE` (note 10, ST-47) |
| `HR` lit les véhicules | `vehicle` : R ; mais US-1.13 ne le liste pas | `fleet.vehicle.read` ❌ pour `HR` |
| `TENANT_ADMIN` et affectations | `vehicle_assignment` : C R U | create/update/end ❌ (lecture seule) |
| `DISPATCHER` | affectation C R U ; « portée `SITE` ou `TENANT` » (H7) | 🔶 : permission **uniquement** avec portée `SITE` ; une attribution `TENANT` ne la confère pas |
| Statut véhicule | `OPS_MANAGER` seul (US-1.14) | `update_status` aussi pour `DISPATCHER` 🔶 et `WORKSHOP_CHIEF` 🔶 |
| Audit : `HSE` | non | dictionnaire §13 : lecture `HSE` ; RBAC : ❌ |
| Audit : `PLATFORM_ADMIN` | US-1.26 A9 : voit les événements de plateforme | `audit.event.read` ❌ pour `PA` |
| `tenant.read` | `DISPATCHER`, `HR`, `HSE` : « — » | ✅ pour tous les rôles |
| Catégories de véhicule | lecture seule dans les stories | `manage` pour `TENANT_ADMIN` et `OPS_MANAGER`, sans story |
| `DRIVER` | `Rs` au Lot 1 (A10 PRD : « sans écran conducteur ») | routes `me`, ST-42/54 |

- Impact tests : ST-02, généré depuis la matrice, attendrait des résultats opposés selon le document pris pour source ; une partie des critères d'acceptation des stories deviendrait fausse.
- Correction proposée : désigner **une seule source de vérité** (recommandation : `MATRICE_RBAC.md` §2 puis `authz_matrix.yaml`, cf. QA-21), supprimer le §0.2 des stories au profit d'un renvoi, et corriger les critères concernés. Les écarts portant sur `HSE` (Q23), `TENANT_ADMIN`/RH (QA-11) et `DISPATCHER` TENANT (🔶) sont des **décisions** à arbitrer (voir §7), pas des corrections de forme.

**QA-05 — Cycle de vie de l'affectation : refus vs suspension automatique** (Bloquant)
- Constat :
  - véhicule hors service avec affectation active : US-1.14 A2 « refusée **ou** signalée non conforme selon arbitrage » ; RM-017/038 : les affectations passent `SUSPENDUE` automatiquement ;
  - désactivation d'un conducteur avec affectation : US-1.21 A2 « refus 409 **ou** clôture assistée » ; RM-039 : affectations `TERMINEE` à la date de sortie ;
  - expiration d'un permis : US-1.25 « marquée *non conforme*, jamais clôturée automatiquement » (un drapeau) ; RM-036 / MODELE §4.3 : statut `SUSPENDUE` avec motif ;
  - chevauchement : US-1.22 R3 considère `PLANNED`/`ACTIVE` ; le dictionnaire (contrainte `EXCLUDE`) et RM-032 incluent `SUSPENDUE` ;
  - changement de site : US-1.14 A3 et US-1.17 A5 refusent (409) ; RM-051 définit un **transfert** qui termine les affectations occupantes ;
  - antidatage : US-1.22 R8 le permet (motif + `OPS_MANAGER`/`TENANT_ADMIN`) ; RM-041 l'interdit sauf permission dédiée **et approbation** (`approved_by` au dictionnaire) ;
  - annulation d'une affectation `PLANNED` : « `CLOSED` avec motif d'annulation » (US-1.23 A5) vs statut `ANNULEE` distinct ; RM-040 rend `TERMINEE`/`ANNULEE` immuables alors que US-1.23 A9 parle d'« événement correctif ».
- Impact tests : la règle d'affectation est le cœur du Lot 1 (PRD O3, indicateurs 9.1 « chaque règle refusée a un test ») ; la matrice règle → test de PRD §9.1 ne peut pas être dressée.
- Correction proposée : arbitrer Q17 **maintenant** (la proposition par défaut « refus pour action volontaire, marquage pour expiration automatique » est testable), puis réécrire US-1.14/1.21/1.25 pour correspondre à un seul modèle d'états (le modèle à 5 états du dictionnaire est le plus complet). Produire un tableau « événement déclencheur × statut de l'affectation × résultat » servant d'oracle. Aligner R3 sur l'ensemble des statuts occupants.

### Majeurs

**QA-06 — Dérogation d'éligibilité et antidatage** (Majeur)
- Constat : RBAC §2.5 définit `override_eligibility` (`OPS_MANAGER`, justification, audit, **notification `HSE`**) et ST-52 attend `201` avec dérogation ; US-1.22 rend R5/A7/A8 **bloquants sans exception** (422) et n'a aucune story de dérogation ; Q1 laisse ouverte la dérogation de site ; il n'existe aucun mécanisme de notification au Lot 1 (pas de service d'e-mail défini, `mailpit` « éventuel »). RM-041/`approved_by` demandent une approbation distincte, absente de RBAC.
- Impact : ST-52 et T-45 (menace Haute) n'ont pas de story ; risque d'implémenter une dérogation silencieuse.
- Correction : soit retirer la dérogation du Lot 1 (recommandé : report, refus strict, test négatif), soit ajouter une story avec critères (rôle, motif obligatoire, audit dédié, notification = événement visible dans une liste, pas d'e-mail).

**QA-07 — Dernier admin et auto-modification** (Majeur)
- Constat : US-1.06 A5 prévoit « me le retirer si je suis le dernier » → 409 et A9 refuse l'auto-escalade ; RBAC §4.2.1 interdit **toute** modification de ses propres affectations (même retrait) ; ST-23 attend 403, ST-24 « 409/403 » ; RBAC §4.2.4 renvoie la reprise à une « procédure plateforme tracée » alors que `PLATFORM_ADMIN` n'a aucune permission d'identité sur un tenant (RBAC §2.2) et qu'aucun parcours n'est défini.
- Correction : un code par cas (auto-modification → 403 ; dernier `TENANT_ADMIN` → 409), spécifier la procédure de reprise (qui, avec quelle permission, quel audit) ou la déclarer hors Lot 1.

**QA-08 — Transitions dépendantes du temps** (Majeur)
- Constat : RM-031/036/037, US-1.25 A4 et US-1.18 supposent une évaluation périodique (« JOB ») et une transition `PLANIFIEE → ACTIVE` ; H8/ADR-004 excluent Redis/worker, et aucun ADR ne choisit le mécanisme (tâche dans le processus API, cron conteneur, `pg_cron`, calcul à la lecture). Aucun document ne définit une **horloge injectable**.
- Impact : tests de bornes (expiration à minuit local, PLANNED→ACTIVE) irréalisables sans contrôle du temps ; tests de concurrence du job (doublons d'alerte, US-1.25 A4) non définis.
- Correction : ADR court « Planification et horloge » : port `Clock` injecté dans les services, point d'entrée de job exécutable en test avec horloge figée (`python -m app.jobs.evaluate_assignments --now ...` ou appel direct), statut **calculé à la lecture** pour tout ce qui est purement fonction du temps, job uniquement pour produire les événements/alertes ; verrou pour l'idempotence.

**QA-09 — Idempotence exigée au Lot 1 mais non modélisée** (Majeur)
- Constat : US-1.12 A8 et US-1.22 A15 exigent une « clé d'idempotence » sur les créations ; US-1.08 A6 « sans double création de session » ; l'en-tête `Idempotency-Key` et la table `idempotency_record` ne sont décrits que dans `INTEGRATION_GPS_OFFLINE.md` §2.1 (lots hors ligne) ; ni la liste des entités du socle §5, ni le dictionnaire, ni les propositions E1-E7 ne l'incluent.
- Impact : critères non vérifiables ; décision de portée (quelles routes ? durée de rétention des clés ? réponse sur même clé/corps différent = 422).
- Correction : ajouter l'entité et la liste des routes concernées, ou retirer ces deux critères du Lot 1 (ils sont naturellement couverts par les contraintes d'unicité pour les véhicules, et par l'exclusion pour les affectations).

**QA-10 — Contrat d'audit** (Majeur)
- Constat : ADR-005 (`actor_kind` : `user/system/platform_support/device_sync`, pas de colonne `outcome`, `before/after` « champs modifiés uniquement ») vs dictionnaire (`actor_type` : `USER/SYSTEM/PLATFORM_SUPPORT`, `outcome` `SUCCES/REFUSE/ECHEC`, `before_data/after_data` masqués) vs RBAC §5 note 15 (pas de valeurs avant/après pour les champs sensibles, marqueur « modifié ») vs CT-2 (« avant/après sans donnée sensible »). Dictionnaire §13 : lecture pour `HSE`, RBAC : ❌. ADR-005 prévoit le chaînage de hash « si le client l'exige », ST-72 le suppose acquis.
- Autres points : (i) refus audités = RM-003 (tous) vs CT-2 (écritures) vs RBAC (ressources sensibles) ; (ii) lire le journal génère un événement (US-1.26 A8) : une requête GET écrit en base — conflit avec un éventuel pool/transaction en lecture seule ; (iii) ST-73 « exactement 1 événement par mutation » est faux pour les flux d'authentification (plusieurs événements) et pour les opérations composites ; (iv) le sondage massif d'UUID étrangers peut saturer la table d'audit (T-37).
- Correction : fixer un schéma d'audit unique (colonnes, énumérations), une politique « quels refus sont audités », définir le chaînage comme optionnel et rendre ST-72 conditionnel, préciser que « exactement un événement » s'entend par **opération métier** identifiée.

**QA-11 — Données personnelles du conducteur** (Majeur)
- Constat : le dictionnaire §8 contient `date_of_birth` et `phone` ; PRD §8 dit « pas de date de naissance, adresse, photo au Lot 1 sauf besoin démontré », US-1.16 A4 n'exclut que photo et adresse, RM-028 exclut pièce d'identité/photo/santé ; RBAC §5 traite `driver.address`, pièce d'identité, `notes_hr`, sanctions, `document_scan` qui n'existent pas au dictionnaire. Les fixtures « valeurs sentinelles » de ST-40/46/48 visent donc des colonnes soit inexistantes soit contraires à la minimisation.
- Correction : arrêter la liste des colonnes du Lot 1 (recommandation : retirer `date_of_birth`, garder `phone` si un besoin est démontré) ; limiter les sentinelles du plan de tests aux colonnes réelles ; aligner RBAC §5.

**QA-12 — Statut et éligibilité du permis / de l'habilitation** (Majeur)
- Constat : le statut du permis est **dérivé** `VALID/EXPIRING/EXPIRED` dans US-1.18 mais **stocké** `VALIDE/SUSPENDU/RETIRE` + dates dans le dictionnaire/RM-024 ; US-1.22 R5 exige « `VALID` » sans dire si `EXPIRING` est éligible ; l'habilitation n'a pas de statut dans les stories (le dictionnaire en a un) ; la vérification du permis (`verified_at`, RM-029) conditionne l'éligibilité « paramétrable » sans valeur par défaut dans les stories ; un permis multi-catégories = plusieurs lignes (dictionnaire) vs « un permis avec une catégorie » (US-1.18), et la clé de doublon diffère (US : catégorie + numéro ; dictionnaire : conducteur + numéro + catégorie).
- Correction : table de décision d'éligibilité (statut stocké × dates × vérification × catégorie requise) avec cas limites, en paramètres de test ; trancher `EXPIRING` = éligible avec avertissement.

**QA-13 — Éligibilité sur intervalle ouvert** (Majeur)
- Constat : R5 : intervalle ouvert → valable « à la date de début, avec avertissement » ; A8 : refus si le permis expire **avant la fin prévue** ; RM-030(c) : permis « couvrant l'intervalle » ; RM-031 : réévaluation quotidienne. Ces textes ne disent pas ce qu'il advient d'une affectation ouverte dont le permis expire dans trois mois (acceptée, puis suspendue par le job).
- Correction : énoncer la règle (acceptée avec avertissement + suspension automatique à l'échéance, cf. RM-036) et ajouter les cas de test aux bornes (échéance = fin de l'intervalle, = début, = début + 1 s).

**QA-14 — Paramètres d'acceptation non fixés** (Majeur)
- Constat : tolérance de clôture « ≤ maintenant (+ tolérance) » (US-1.23 A1/A4), seuil `EXPIRING` (US-1.18/1.20, Q21), « N » tentatives (US-1.05 A5, 1.08 A3), durées d'invitation/session/jeton (Q22, ADR-003), tolérance de dérive d'horloge (RM-068, RM-081), écarts maximaux de compteur (RM-067).
- Correction : ne pas inventer de valeur, mais **nommer les clés de configuration**, leur type et leur domaine, et imposer que les tests lisent la valeur de configuration (jamais un nombre en dur). Les valeurs par défaut de démonstration sont à arbitrer (§7).

**QA-15 — Critères non testables ou alternatifs** (Majeur) — voir le tableau par story du §4.

**QA-16 — Questions ouvertes qui bloquent des critères** (Majeur)
- Constat : sont bloquantes pour le Lot 1 : Q1 (site), Q2 (catégories), Q3 (mapping permis/habilitation), Q4 (écran `DRIVER`), Q6/Q22 (MFA, mots de passe, N, durées), Q7 (lecture de l'audit), Q10/Q15 (antidatage, séparation `DISPATCHER`/`OPS_MANAGER`), Q12 (unicité sur archivés/engins sans plaque), Q16 (e-mail multi-tenant), Q17 (refus vs suspension), Q18 (réactivation `RETIRED`), Q19 (journalisation des lectures), Q20 (visibilité inter-sites). Les propositions par défaut existent pour la plupart (US §3) mais ne sont pas arbitrées.
- Correction : une réunion d'arbitrage avant le premier ticket de code ; consigner les réponses dans `DECISIONS_A_ARBITRER.md` (cité par le socle et `ARCHITECTURE.md`, absent du dépôt).

**QA-17 — Référentiels globaux et catégories de véhicule** (Majeur)
- Constat : `role` et `license_category_ref` sont **globaux sans `tenant_id`** (dictionnaire §4 et §9), ce qui contredit ST-05 (« toute table métier a `tenant_id NOT NULL`, RLS forcée ») et l'objectif ST-06 ; `vehicle_category` est « par tenant » au dictionnaire alors que Q2 est ouverte ; aucune story ne crée ou ne gère les catégories (pourtant `manage` dans RBAC), ni ne les alimente à la création d'un tenant (US-1.01) ; US-1.11 A3 « aucune catégorie → message d'état vide » masque ce trou.
- Correction : liste blanche explicite des tables globales (lecture seule pour `mf_app`, alimentées par migration) dans ST-05 ; trancher Q2 ; ajouter l'initialisation des catégories par tenant (copie du référentiel) à US-1.01 ou une story de gestion.

**QA-18 — Amorçage de la plateforme** (Majeur)
- Constat : le premier `PLATFORM_ADMIN` n'a pas de procédure de création (RBAC §4.1 : « espace d'identité séparé » ; ni API de tenant, ni migration) ; `identity.user.create` et `role_assignment.create` sont ❌ pour `PA` alors que US-1.01 A1 émet l'invitation du premier `TENANT_ADMIN` ; le seed (US-1.30) est attribué à un `PLATFORM_ADMIN` qui n'a, par US-1.01 A5, aucun accès métier — le seed doit donc être un **script d'exploitation**, pas une fonction d'API ; ST-84 teste « le script de seed » avec `ENV=production`.
- Correction : décrire (a) la commande de création du premier `PLATFORM_ADMIN` (CLI, secret fourni par variable d'environnement, jamais en dur), (b) la permission technique `organization.tenant.create` incluant l'invitation initiale, (c) le seed comme CLI refusant `ENV=production` et exécuté avec le rôle applicatif (pas `mf_owner`).

**QA-19 — Périmètre du Lot 1 vs plan de tests** (Majeur)
- Constat : le plan ST couvre des fonctions sans story ni décision de périmètre : exports (`fleet.vehicle.export`, `driver.export`, `vehicle_assignment.export`, `audit.event.export`, ST-35/44/57/75) ; liaison compte↔conducteur (`link-account`, ST-45) alors que Q4/A10 disent « pas d'écran conducteur » ; accès support (ST-28, RBAC §4.1) alors que Q26 dit « Non au Lot 1 » et que US-1.01 A5 refuse l'accès ; vérification d'intégrité de l'audit (ST-72) ; journal d'accès du titulaire (ST-76, `audit.data_access.read_own`) ; limitation de débit (ST-08) ; `reset-credentials` pour l'administrateur (RBAC) vs réinitialisation en libre-service (US-1.10, sans permission nommée dans RBAC).
- Correction : marquer chaque ST « Lot 1 / conditionnel / reporté » dans un tableau de traçabilité (voir `STRATEGIE_QUALITE_CI.md` §9), et reporter les routes non retenues pour qu'elles ne soient pas implémentées « par défaut ».

**QA-20 — Faisabilité du Lot 1** (Majeur)
- Constat (jugement QA, aucun chiffrage d'effort inventé) : 30 stories, ~12 entités, RLS forcée + FK composites + contraintes d'exclusion, rotation de refresh avec détection de réutilisation et période de grâce, invitations (e-mail), jobs d'échéance, audit transactionnel avec chaînage optionnel, UI française accessible, tests générés depuis une matrice, ~98 tests de sécurité identifiés. Les risques techniques cumulés sont concentrés sur : auth (ADR-003), RLS + pool de connexions (T-06), exclusion `gist` (btree_gist), horloge (QA-08), masquage de champs par sérialiseur (ST-40).
- Correction proposée — trois tranches verticales livrables et testables :
  - **1a — socle** : tenant, site, comptes, rôles/portées, login/logout/refresh, audit, harnais d'isolation (fixtures A/B, ST-01 à ST-09, ST-10 à ST-29), CI minimale ;
  - **1b — référentiels** : catégories, véhicules, conducteurs, permis, habilitations, masquage (ST-30 à ST-49) ;
  - **1c — affectations et UI** : affectations, éligibilité, job de conformité, interface (ST-50 à ST-58), accessibilité, démonstration.
  Une revue sécurité et QA a lieu à la fin de chaque tranche (CLAUDE.md).

**QA-21 — Artefacts de test manquants** (Majeur)
- Constat : `authz_matrix.yaml` (RBAC §2, MENACES décision 10) non créé ni arbitré ; chemins d'API « attendus » seulement (MENACES §8 en-tête) ; aucun catalogue de codes d'erreur ; `DECISIONS_A_ARBITRER.md` cité (socle §2, ARCHITECTURE §5, PRD §12) mais absent ; `PARCOURS_UTILISATEURS.md` en cours.
- Correction : produire dans l'ordre (1) glossaire d'énumérations, (2) table de décision d'erreurs, (3) `authz_matrix.yaml`, (4) contrat OpenAPI squelette (routes + `x-permission`), (5) `DECISIONS_A_ARBITRER.md`. Ces 5 artefacts constituent la **Definition of Ready** du premier ticket de code.

**QA-22 — Fuseau par défaut à décalage nul** (Majeur)
- Constat : `Africa/Conakry` est UTC+0 sans heure d'été (H4). Toute confusion entre UTC et heure locale, tout oubli de conversion, passe inaperçu avec le jeu de données par défaut. Or le fuseau est configurable par site (US-1.03 A1) et la limite de minuit pour l'expiration d'un permis (US-1.18 A8, RM-021) est un cas limite explicite.
- Correction : les fixtures de test incluent **systématiquement** au moins un site à décalage fixe non nul (ex. UTC+1) et un site à changement d'heure (ex. un fuseau européen) ; aucun test de fuseau ne s'appuie seulement sur `Africa/Conakry`. Test de propriété : conversion locale → UTC → locale idempotente.

**QA-23 — Pas de dépôt distant, CI et protection de branche impossibles** (Majeur)
- Constat : pas de remote, aucun commit, branche `master` alors que `main` est attendue (socle §1, PRD §12). La CI GitHub Actions (ADR-004) et la « branche protégée » supposent un dépôt hébergé, dont le choix (compte, visibilité, plan, quota de minutes, disponibilité des règles de protection pour un dépôt privé) est une décision d'hébergement/coût **non prise** ; `gh` n'est pas installé.
- Correction : décision d'arbitrage (§7) ; en attendant, la même suite de vérifications doit pouvoir s'exécuter **localement** via `docker compose` (voir `STRATEGIE_QUALITE_CI.md` §3-4), afin que la CI ne soit qu'un second exécutant. Renommer `master` en `main` avant le premier commit (opération sans risque tant qu'il n'y a pas de commit, mais à faire par le propriétaire du dépôt).

### Mineurs

- **QA-24 — Concurrence optimiste** : CT-4 « exige la version courante » mais le support (corps `version`, `If-Match`/ETag) n'est pas défini ; le dictionnaire a `row_version`, `INTEGRATION_GPS_OFFLINE` §2.5 utilise `If-Match`. Préciser aussi le code si la version est absente (422 ou 428). Correction : un mécanisme, un code, un test paramétré sur toutes les routes de mise à jour.
- **QA-25 — Pagination et format d'erreur** : US-1.13 A1 « paginés, total correct » sans taille par défaut ni maximum ; ST-07 « borné ou 422 » (deux comportements) ; CT-3 « format normalisé » sans schéma. Correction : fixer pagination (type curseur ou offset, défaut, maximum, tri stable avec clé de départage) et schéma d'erreur (champs `code`, `message_fr`, `details`, `request_id`).
- **QA-26 — Nommage** : permissions `fleet.vehicle.deactivate` (RBAC) vs « archiver/RETIRED » (US-1.15) vs `REFORME` ; actions d'audit `vehicle.create` (ADR-005) / `vehicle.status.change` (dictionnaire) / permission `fleet.vehicle.create` ; clés primaires `site_id` (dictionnaire) vs `(tenant_id, id)` (H3, ADR-001/002) ; routes `end` vs « clôturer » ; `DELETE /role-assignments/{id}` et `DELETE /sessions/{id}` (ST-23/26/29b) alors que CT-6 interdit toute suppression physique (il s'agit de révocations : à nommer comme tel) ; ADR-002 §3.5 teste « suppression » sur chaque endpoint alors qu'aucun n'existe. Correction : une table de correspondance permission ↔ action d'audit ↔ route dans `authz_matrix.yaml`.
- **QA-27 — Authentification** : ADR-003 §3.3 prévoit une **période de grâce** (rejeu unique du refresh précédent avec le même identifiant de requête) tandis que ST-62 exige la révocation de la famille à toute réutilisation ; il faut deux tests (rejeu dans la grâce : accepté une fois ; rejeu hors grâce ou deuxième rejeu : famille révoquée). Les cookies `Secure` exigent HTTPS : à `http://localhost` les navigateurs de la famille Chromium l'acceptent, mais pas un accès par adresse réseau depuis une tablette ; risque d'e2e non représentatifs. Correction : spécifier la durée de grâce (paramètre) et le comportement attendu de l'e2e local.
- **QA-28 — Poste de développement Windows** : `make` introuvable dans le PATH de Git Bash lors de cette revue ; `gh` absent ; `core.autocrlf=true` : les scripts `.sh`, entrypoints, SQL d'initialisation passeraient en CRLF et échoueraient dans les conteneurs Linux (`bad interpreter`, erreurs de shebang) ; Python 3.10 local ≠ 3.12 cible (ADR-004). Correction : `.gitattributes` forçant `eol=lf` pour `*.sh`, `*.sql`, `Dockerfile*`, `*.yml` ; tout exécuter dans les conteneurs ; ne pas dépendre de `make` (voir stratégie §3).
- **QA-29 — UUID v7** : H2 dit « v7 si disponible » ; la bibliothèque standard Python 3.12 ne fournit pas v7 (à vérifier au moment de l'implémentation). Correction : décider v4 (par défaut, sans dépendance) ou une bibliothèque justifiée ; les tests ne doivent jamais supposer un ordre d'identifiants.
- **QA-30 — Codes de session** : jeton valide mais tenant suspendu (US-1.02 A1) ou rôle retiré (ST-67 : 403 ; ST-68 : 401) — préciser quel cas donne 401 (identité invalide) ou 403 (droits insuffisants) et que le message ne révèle pas la cause (US-1.02 A2).
- **QA-31 — Numérotation** : « Q1-Q15 » du PRD, « Q16-Q26 » des stories, 16 points numérotés 1-16 dans `REGLES_METIER.md` §11 et références croisées « Q5 » (PRD) / « Q26 » (stories) pour la même question de support. Correction : un registre unique de décisions `D-nn`.
- **QA-32 — Limitation de débit sans Redis** : C-31/ST-08 exigent une limitation par IP, compte et tenant avec équité entre tenants ; H8 exclut Redis. Une limitation en mémoire est fausse avec plusieurs processus. Correction : préciser le mécanisme du Lot 1 (par processus, documenté comme limite, ou table en base) et tester ce qui est réellement garanti.

## 4. Testabilité des stories du Lot 1

Légende : **T** = testable tel quel ; **T\*** = testable après la correction citée ; **À clarifier** = ambigu, plusieurs comportements valides ; **NT** = non testable en l'état ; **Contr.** = contredit un autre document. « Critères posant problème » ne liste que les critères en défaut ; les autres sont considérés testables, sans que cela signifie qu'ils soient exacts.

| Story | Verdict | Critères posant problème | Correction |
|---|---|---|---|
| US-1.01 Créer un tenant | T\* | A5 vs Q26/ST-28 (accès support) ; A1 invitation sans mécanisme d'envoi | QA-18, QA-19 |
| US-1.02 Suspendre | T\* | A1 « refusées/révoquées » (deux comportements) ; code HTTP d'une session déjà ouverte | QA-30 ; trancher « révoquées » |
| US-1.03 Sites | T | A4 « liste des blocages (nombre seulement) » : préciser le format | — |
| US-1.04 Inviter | Contr. | A3 « 422 (… = 404 sémantique) » ; A6 échec d'envoi sans service d'e-mail défini ; A7 dépend de Q16 | QA-01, QA-03 |
| US-1.05 Activer | À clarifier | A3 politique de mot de passe (Q6), A5 « N » | QA-14 |
| US-1.06 Rôles | Contr. | A5/A9 vs RBAC §4.2.1 (auto-retrait) ; A8 « à confirmer » ; A2 | QA-03, QA-07 |
| US-1.07 Désactiver | T\* | A2 vs ST-24 « 409/403 » | QA-07 |
| US-1.08 Connexion | Contr. | A1-A4 sans règle de résolution du tenant ; A7 « algorithme à valider » (non testable comme critère de story) ; A8 dépend de Q6 | QA-01 ; déplacer A7 en ST |
| US-1.09 Déconnexion | À clarifier | A2 « données en cache local » : aucun cache n'existe au Lot 1 (PWA = Lot 4) | Préciser ce qui est mis en cache (stockage de session ?) |
| US-1.10 Réinitialiser | T\* | permission non nommée dans RBAC (`reset_credentials` est l'action admin) | QA-19, QA-26 |
| US-1.11 Catégories | À clarifier | A1 « portée selon Q2 » ; A2 | QA-17 |
| US-1.12 Créer véhicule | À clarifier | A3 (Q12) ; A4 « 404 / refus » ; A5 vs US-1.22 A10 (422 vs 404) ; A8 idempotence | QA-03, QA-09, QA-16 |
| US-1.13 Lister | Contr. | liste de rôles sans `HR`/`FINANCE` alors que la matrice les autorise en lecture ; A1 pas de taille de page ; A6 « ignoré **ou** rejeté » | QA-04, QA-25 ; choisir « rejeté 422 » (testable) |
| US-1.14 Modifier / statut | NT | A2 « refusée **ou** signalée » ; A5 « refus **ou** autorisation » ; A3 vs RM-051 | QA-05, Q17, Q18 |
| US-1.15 Archiver | À clarifier | A3 « réversible selon Q18 » ; nom (`RETIRED`/`REFORME`/`deactivate`) | QA-02, QA-26 |
| US-1.16 Créer conducteur | À clarifier | A3 « 404/refus » ; A6 « avertissement non bloquant » sans critère de similarité | Définir la règle de doublon (ex. même nom normalisé, même site) ou retirer |
| US-1.17 Consulter/modifier conducteur | Contr. | A1 / note §0.2 : `TENANT_ADMIN` lit le n° de permis (RBAC : non) ; A7 renvoie à Q19 | QA-04, QA-16 |
| US-1.18 Permis | À clarifier | statut dérivé vs stocké ; A4 clé de doublon ; A7 `TENANT_ADMIN` ; A8 « proposition » | QA-12, QA-22 |
| US-1.19 Habilitation | Contr. | A5 `HSE` 403 vs RBAC `HSE` autorisé ; pas de statut d'habilitation | QA-04, QA-12 |
| US-1.20 Expirations | À clarifier | A1 seuil par défaut non arbitré ; A2 renvoie à US-1.25 | QA-14 |
| US-1.21 Désactiver conducteur | NT | A2 « refus 409 **ou** clôture assistée » | QA-05 |
| US-1.22 Affecter | À clarifier | R5/A8 (intervalle ouvert), R8/A13 « 403/422 », A9 « ou dérogation selon Q1 », A11 « 404/403 », A16 « tolérance documentée » sans valeur ; A4 (concurrence) testable seulement avec contrainte en base | QA-03, QA-05, QA-06, QA-13, QA-14 |
| US-1.23 Clôturer | À clarifier | A1/A4 « tolérance », « ou programmation d'une fin prévue » ; A5 statut `CLOSED` vs `ANNULEE` ; A9 « événement correctif » sans story | QA-05, QA-14 |
| US-1.24 Historique | À clarifier | A4 « masquée ou partiellement visible selon arbitrage » (Q20) ; A5 dépend de Q4 ; A2 « instant » : borne inclusive/exclusive | QA-16 ; ajouter test `[début, fin)` |
| US-1.25 Non conformité | Contr. | drapeau « non conforme » vs statut `SUSPENDUE` (RM-036) ; aucun état défini | QA-05, QA-08 |
| US-1.26 Audit | Contr. | A1 filtre « acteur » et pagination ; A5 portée `SITE` du rôle d'audit (Q7) ; A9 vs RBAC `PA` ❌ ; mention d'« export » (A2) sans story | QA-04, QA-10, QA-19 |
| US-1.27 Journalisation | À clarifier | A1 « stories 01-25 » (identifiants abrégés) ; A2 refus 403 seulement vs RM-003 ; A3 testable (panne simulée) | QA-10 |
| US-1.28 Isolation | T\* | A6 « suggestions » (aucune route de suggestion n'existe) ; A7 CI inexistante ; « exports » sans story | QA-19, QA-23 |
| US-1.29 UI | NT en partie | A2 « connexion lente » (profil non défini) ; A3 « sans défilement horizontal » (largeur non définie) ; A4 « contrastes suffisants » (WCAG AA est une hypothèse) ; A6/A7 | Définir profils réseau et largeurs d'écran (voir stratégie §1-2) |
| US-1.30 Données de démo | T\* | A2 « aucun nom réel » : non automatisable sauf liste d'exclusion et domaines/numéros réservés ; A3 « environnement de production » : définir le signal (`ENV`) ; acteur `PLATFORM_ADMIN` incohérent (QA-18) | QA-18 |

Constats transverses sur les critères :
- Les « Given/When/Then » mélangent souvent plusieurs comportements (« 404/403 »). Règle de rédaction proposée : **un seul code HTTP et un seul code d'erreur par critère** ; si l'arbitrage manque, le critère est marqué *(à arbitrer)* et exclu du périmètre de test automatique jusqu'à décision.
- Les critères « audité » ne précisent ni l'action ni les champs ; ils deviennent testables dès que `authz_matrix.yaml` porte l'action d'audit (QA-26).
- Les parcours (`PARCOURS_UTILISATEURS.md`) reprennent des messages 403/422 « clairs » (ex. antidatage R8 : « message 403/422 ») : même ambiguïté qu'en QA-03.

## 5. Écarts entre documents — tableau récapitulatif

| Sujet | Document A | Document B | Écart | Constat |
|---|---|---|---|---|
| Hors périmètre de site | CT-1 : 404 | RBAC §1.1.6 étape 3 : « refus » ; ST-02 : 403 | 404 vs 403 | QA-03 |
| Dernier admin | US-1.06 A5 : 409 | ST-23 : 403 ; ST-24 : 409/403 | codes | QA-07 |
| Permissions | US §0.2 | RBAC §2 | 13 écarts | QA-04 |
| Statuts | US §0.3 | dictionnaire §1-11 | vocabulaire | QA-02 |
| Affectation et véhicule HS | US-1.14 A2 | RM-017/038 | refus vs suspension | QA-05 |
| Antidatage | US-1.22 R8 | RM-041 | approbation | QA-05, QA-06 |
| Dérogation | RBAC §2.5, ST-52 | US-1.22 (bloquant) | existence | QA-06 |
| Audit : colonnes | ADR-005 | dictionnaire §13 | `actor_kind`/`actor_type`, `outcome` | QA-10 |
| Audit : lecteurs | dictionnaire (`HSE`) | RBAC (❌) | rôle | QA-04 |
| E-mail unique | dictionnaire (par tenant) | US-1.08 / ADR-003 (login sans tenant) | ambiguïté | QA-01 |
| Données conducteur | dictionnaire (`date_of_birth`) | PRD §8, RM-028 | minimisation | QA-11 |
| Idempotence | US-1.12, 1.22 | dictionnaire, socle | entité absente | QA-09 |
| Sites | US-1.14 A3 (refus) | RM-051 (transfert) | opération | QA-05 |
| Accès support | RBAC §4.1, ST-28 | US Q26, US-1.01 A5 | Lot 1 ou non | QA-19 |
| Chaînage d'audit | ADR-005 (optionnel) | ST-72, C-16 | obligatoire ou non | QA-10 |
| Tables globales | dictionnaire (`role`, `license_category_ref`) | ST-05 | `tenant_id` | QA-17 |
| Écran `DRIVER` | PRD A10 (aucun) | RBAC (`me`), US-1.24 A5 | périmètre | QA-19 |
| Fuseau | H4 (UTC+0) | US-1.18 A8 (minuit local) | cas limite invisible | QA-22 |
| Rotation du refresh | ADR-003 (grâce) | ST-62 (strict) | cas de test | QA-27 |

## 6. Risques de faisabilité du Lot 1 (synthèse)

| Risque | Source | Probabilité / impact (jugement qualitatif) | Mitigation |
|---|---|---|---|
| Fuite inter-tenant par oubli de filtre ou RLS contournée (propriétaire, pool de connexions) | ADR-002, T-06 | Faible-moyenne / critique | Tests ST-03/04/05 sous `mf_app` uniquement ; refus de démarrage si `mf_app` super-utilisateur ; revue de chaque dépôt (repository) |
| Tests d'autorisation tautologiques (l'oracle est lu dans le code) | ST-02 | Moyenne / élevée | Matrice YAML indépendante du code, revue par `security-engineer` ; test canari qui retire volontairement un filtre |
| Contrainte d'exclusion et concurrence mal testées | RM-032/033, ST-53 | Moyenne / élevée | Test à N transactions réellement concurrentes sur base PostgreSQL réelle (pas SQLite, ADR-004) ; extension `btree_gist` dans le script d'initialisation |
| Rotation du refresh : fenêtre de grâce mal réglée | ADR-003 | Moyenne / élevée | Tests de rejeu, d'horloge et de réponse perdue ; revue sécurité |
| Masquage de champs par sérialiseur incomplet | RBAC §5 | Moyenne / élevée | Valeurs sentinelles + recherche dans réponses, logs et audit (ST-40/48/74) |
| Dérive des fuseaux | QA-22 | Moyenne / moyenne | Fixtures multi-fuseaux, horloge injectable |
| Étendue du Lot 1 | QA-20 | Élevée / élevée | Découpage 1a/1b/1c, DoR (QA-21) |
| Exécution sous Windows/Docker (fins de ligne, volumes, performances) | QA-28, ADR-004 | Moyenne / faible-moyenne | `.gitattributes`, tests dans les conteneurs, surveillance du temps d'exécution |
| CI non exécutable faute de dépôt hébergé | QA-23 | Élevée (état actuel) / moyenne | Exécution locale équivalente par `docker compose` ; décision d'hébergement |
| Dépendances supplémentaires non justifiées (CLAUDE.md : pas de dépendance spéculative) | ADR-001, 004 | Moyenne / faible | Registre des dépendances de test avec justification (stratégie §2.3) |

## 7. Décisions à arbitrer (ordonnées par blocage)

1. **Tenant à la connexion** : e-mail globalement unique (recommandé : plus simple, compatible anti-énumération) ou identifiant de tenant à la connexion ? Et forme du chemin pré-authentification vis-à-vis de la RLS (QA-01).
2. **Table de décision 401/403/404/422/409** (QA-03) et politique d'audit des refus.
3. **Glossaire d'énumérations** : codes anglais ou français ; trois vocabulaires à fusionner (QA-02).
4. **Source de vérité des permissions** : `MATRICE_RBAC.md` + `authz_matrix.yaml` ; arbitrer `TENANT_ADMIN` vs données RH, `HSE` écrit les habilitations, `DISPATCHER` de portée `TENANT` (🔶) (QA-04).
5. **Q17** (refus vs suspension automatique) et statut de l'affectation à 5 états ; dérogation d'éligibilité au Lot 1 ou reportée (QA-05, QA-06).
6. **Mécanisme de planification et horloge** (QA-08).
7. **Idempotence au Lot 1** : entité `idempotency_record` ou retrait des critères (QA-09).
8. **Colonnes personnelles du conducteur au Lot 1** (QA-11) et valeurs de configuration par défaut (QA-14).
9. **Périmètre exact** : exports, liaison de compte, accès support, chaînage d'audit, journal d'accès du titulaire (QA-19).
10. **Découpage du Lot 1 en 1a/1b/1c** (QA-20).
11. **Hébergement du dépôt** (fournisseur, visibilité, plan) et renommage `main` ; politique de revue quand l'équipe est d'une personne (QA-23).
12. **Dépendances de test à approuver** (stratégie §2.3) : `hypothesis`, `schemathesis`, `oasdiff` (binaire/conteneur), `pytest-xdist`, `import-linter` (déjà ADR-001).

## 8. Ce qui reste hors de portée de cette revue

- Aucune validation de la conformité juridique guinéenne (rétention, géolocalisation, données de santé) : relève du conseil juridique local (CLAUDE.md).
- Aucune validation métier du mapping permis ↔ catégorie d'engin (Q3, RM-022) : relève d'un expert du secteur.
- Aucune mesure de performance : le projet n'a ni code ni volumétrie (Q9) ; les budgets de `STRATEGIE_QUALITE_CI.md` sont des **cibles proposées**.
- Les menaces des lots 2 à 6 (GPS, hors ligne) ne sont évaluées qu'au niveau du plan de tests de `STRATEGIE_QUALITE_CI.md` §2.6.
