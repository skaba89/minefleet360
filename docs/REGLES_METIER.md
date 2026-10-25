# Règles métier et invariants — MINEFLEET 360

> Statut : **provisoire** (phase 0), mis à jour après la revue croisée. Préséance : `DECISIONS_A_ARBITRER.md` (D-01..D-24, défauts provisoires C-01..C-17) > `MODELE_PHYSIQUE_LOT1.md` > `MATRICE_RBAC.md` > ce document. Modèle : `docs/MODELE_CONCEPTUEL.md`. Données : `docs/DICTIONNAIRE_DONNEES.md` (glossaire des statuts).
> Les valeurs de statut sont en anglais `UPPER_SNAKE_CASE` (D-01) ; les libellés français sont dans le glossaire du dictionnaire. Aucune valeur chiffrée d'exploitation n'est avancée : les seuils sont des **paramètres à définir avec le client**.

## 0. Comment lire ce document

Chaque règle est numérotée `RM-xxx`, porte une **nature**, un **niveau d'application** et une **tranche** de livraison :

| Nature | Sens | Poids |
|--------|------|-------|
| **V** — Fait vérifié | Imposé par `CLAUDE.md`, le socle de cadrage, les skills du dépôt ou une décision D-xx. Vérifié dans les documents, pas sur le terrain. | Non négociable sans arbitrage explicite |
| **H** — Pratique courante (hypothèse) | Usage répandu supposé dans le secteur minier/transport, ou choix de conception raisonnable. Non confirmé par le client. | Appliquer par défaut, rendre configurable si possible |
| **A** — À valider | Dépend du client, d'un fournisseur (GPS, pont-bascule) ou d'un juriste guinéen. | Ne pas coder en dur ; implémenter derrière un paramètre ou différer |

| Application | Sens |
|-------------|------|
| **DB** | Contrainte garantie par PostgreSQL (CHECK, FK composite, EXCLUDE, trigger) |
| **APP** | Contrôle applicatif (service de domaine), testé |
| **JOB** | Traitement planifié — **aucun planificateur au lot 1** (D-12) |

| Tranche | Sens (D-21) |
|---------|-------------|
| **1a** | Socle : tenant/site, identité, rôles, audit, RLS |
| **1b** | Véhicules, conducteurs, permis, habilitations |
| **1c** | Affectations, UI minimale, E2E |
| **Lot N** | Hors lot 1 ; lot indiqué d'après `ROADMAP.md` / `PLAN_LOT1.md` ; « ultérieur » si non planifié |

Principe : toute règle **bloquante** touchant l'isolation ou les chevauchements doit avoir une défense en **DB** en plus de l'APP.

---

## 1. Isolation, autorisation, traçabilité

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-001 | Toute lecture/écriture d'une entité métier est filtrée par `tenant_id` déduit de la session, jamais d'un paramètre client. Pour un rôle à portée `SITE`, filtrée aussi par `site_id`. | V (H1, CLAUDE.md) | APP + DB (RLS en défense en profondeur) | 1a |
| RM-002 | Les références entre entités métier sont des FK composites `(tenant_id, id)` : une référence inter-tenant est impossible en base. Exceptions listées : colonnes d'acteur (`granted_by`, `revoked_by`, `verified_by`, `actor_user_id`). | V (H3) | DB | 1a (étendue en 1b, 1c) |
| RM-003 | Codes de réponse (D-05) : ressource d'un autre tenant **ou** hors portée site → `404` (indistinguable de « introuvable ») ; permission manquante sur une ressource visible ou un endpoint de collection → `403`. Les `403` sont auditées (`audit_event`, `outcome=DENIED`) ; les `404` sur identifiant d'un autre tenant sont journalisées comme événement de sécurité (log structuré, **pas** dans l'audit du tenant). | V (D-05) | APP | 1a |
| RM-004 | Toute mutation (création, modification, changement de statut, attribution de rôle) et toute décision d'autorisation refusée (`403`) crée un `audit_event` (acteur, avant/après sans champ sensible, motif, requête) dans la même transaction. | V (CLAUDE.md, D-17) | APP | 1a |
| RM-005 | Horodatages stockés en UTC (`timestamptz`) ; affichage dans le fuseau du site (défaut `Africa/Conakry`, UTC+0 sans changement d'heure). L'horloge est **injectable** dans le code ; les tests utilisent des fuseaux non nuls (D-12, D-23). | V (H4, D-23) | DB + APP | 1a |
| RM-006 | Pas de suppression physique des entités métier : `mf_app` n'a aucun `DELETE` sur les tables métier ; archivage par **statut** (pas de colonne `archived_at`) ; `audit_event` et `vehicle_status_history` en ajout seul. Exceptions : tables éphémères (`account_token`, `auth_session`) purgées. | V (D-19) | DB + APP | 1a |
| RM-007 | Un `PLATFORM_ADMIN` n'a aucun accès aux données métier d'un tenant. **Aucun accès support plateforme au lot 1** ; ultérieurement, tout accès support sera motivé, limité dans le temps, journalisé (`actor_kind=PLATFORM_SUPPORT`) et soumis à approbation du tenant (C-10). | V (D-10, D-16) | APP | 1a (absence d'accès) ; support : pilote |
| RM-008 | Le rôle `DRIVER` ne lit que ses propres données. **Aucun écran ni parcours conducteur au lot 1** (C-12) ; la règle sera appliquée avec l'application conducteur. | H | APP | Lot 4 |
| RM-009 | Minimisation (D-15) : un dispatcher voit pour un conducteur **« éligible / non éligible »** et la prochaine échéance, mais ni le numéro de permis, ni le téléphone, ni les motifs de suspension. Le numéro de permis et le téléphone sont visibles de `HR` **seulement** ; le motif de suspension de `HR` et `HSE` (lecture) ; `TENANT_ADMIN` ne lit pas les données personnelles du conducteur (D-10). Masquage **côté serveur** (sérialiseur par rôle), pas seulement en UI. | V (D-10, D-15) ; base légale **A** | APP | 1b |

## 2. Véhicule / engin

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-010 | Le numéro de parc est unique par tenant, comparé sans casse ni espaces de bord, et **unique à vie** : jamais réutilisé, même `RETIRED` (unicité totale, non partielle). | V (C-13 défaut, DB-23) | DB | 1b |
| RM-011 | L'immatriculation, nullable (engin hors route), est unique par tenant après normalisation (casse, espaces, tirets) ; non réutilisable après réforme (défaut C-13). | H ; exigence légale d'immatriculation **A** | DB | 1b |
| RM-012 | Le numéro de série, s'il est présent, est unique par `(tenant, constructeur normalisé, série normalisée)`. | H | DB | 1b |
| RM-013 | Un véhicule appartient à une catégorie active du même tenant ; changer de catégorie quand des affectations ou habilitations existent exige de réévaluer l'éligibilité des affectations futures. | H | APP | 1b (réévaluation : 1c) |
| RM-014 | Le statut ne change que par une transition listée dans la machine à états (`MODELE_CONCEPTUEL.md` 4.1), avec motif, acteur, `audit_event` et ligne de `vehicle_status_history` (trigger). | V (D-02) | APP + DB (historique) | 1b |
| RM-015 | `RETIRED` est **terminal** : plus aucun changement de statut, d'affectation ou de compteur. Pas de réactivation au lot 1 (défaut C-13). Réforme soumise à approbation : qui approuve est **A**. | V (D-02, C-13) ; approbation **A** | APP | 1b |
| RM-016 | « En exploitation » n'est **pas** un statut stocké : il est déduit d'une affectation `ACTIVE` (plus tard : mission en cours). | V (D-02) | APP | 1c |
| RM-017 | Passer un véhicule en `IN_MAINTENANCE`, `IMMOBILIZED`, `OUT_OF_SERVICE` ou `RETIRED` est **refusé (`409`)** tant qu'une affectation `PLANNED` ou `ACTIVE` existe ; la réponse liste les affectations à clôturer (D-11). Aucune suspension automatique. Motif obligatoire pour `IMMOBILIZED`, `OUT_OF_SERVICE`, `RETIRED`. | V (D-11) | APP | 1c |
| RM-018 | La capacité nominale (`rated_payload_kg`) est une donnée de catalogue et n'est jamais présentée comme tonnage transporté. | V (H10) | APP + UI | 1b |
| RM-019 | Les documents réglementaires du véhicule (assurance, contrôle technique, visite) sont **hors modèle lot 1** ; s'ils sont requis pour affecter, ils entreront dans l'éligibilité véhicule. Risque accepté en attendant (défaut C-06 : aucun document bloquant). | **A** (C-06) | — | Lot 2 |

## 3. Conducteur, permis, habilitation

La validité d'un permis ou d'une habilitation est **dérivée des dates** et du statut administratif, jamais stockée (D-03). Au lot 1, la **conformité est calculée à la lecture** (D-12).

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-020 | Seul un conducteur `ACTIVE` peut recevoir ou conserver une affectation `PLANNED`/`ACTIVE`. `UNAVAILABLE`, `SUSPENDED`, `INACTIVE` le rendent inéligible. Passer le conducteur en non-`ACTIVE` est **refusé (`409`)** tant qu'une affectation `PLANNED`/`ACTIVE` existe (D-11). | V (D-03, D-11) | APP | 1c |
| RM-021 | Un permis est valable de `issue_date` au dernier jour `expiry_date` **inclus**, interprété dans le fuseau du site d'exploitation. Instant d'expiration = début du jour suivant, heure locale du site, converti en UTC. | H | APP | 1b |
| RM-022 | La catégorie de permis exigée dépend de la catégorie d'engin (table de jonction `vehicle_category_license_category`). Aucune ligne = « pas de permis d'État exigé » : **ne pas supposer** cette dérogation avant validation. Catégories de permis « à valider localement » (défaut C-07 : valeurs fictives en dev). | **A** (juriste + client, C-07) | APP | 1b |
| RM-023 | Pour les catégories marquées `requires_internal_authorization`, une habilitation `DRIVING_AUTHORIZATION` de la catégorie correspondante est obligatoire. | H ; formalités **A** | APP | 1b |
| RM-024 | Un permis ou une habilitation n'est pris en compte que si `status = VALID` **et** la date d'évaluation est dans `[valid_from, valid_to]` (permis : `[issue_date, expiry_date]`). `SUSPENDED`, `WITHDRAWN`, `REVOKED` priment sur les dates. L'état `VALID`/`EXPIRING`/`EXPIRED` est calculé à la lecture. | V (D-03) | APP | 1b |
| RM-025 | **Aptitude médicale : non collectée au lot 1** (pas de type `MEDICAL_FITNESS`, pas de date de naissance, pas de motif maladie — D-15). Une éventuelle information « apte jusqu'à » est une migration ultérieure soumise à l'avis du juriste (C-08). | V (D-15) ; obligation légale et secret médical **A** | — | Lot 2 (sous réserve C-08) |
| RM-026 | Les conducteurs sous-traitants/intérimaires sont soumis aux mêmes contrôles d'éligibilité que les employés. | H | APP | 1c |
| RM-027 | Un conducteur peut exister sans compte utilisateur ; le lien conducteur↔compte est 1:1 au plus (contrainte en base). La **liaison et l'écran conducteur sont hors lot 1** (D-16). | V (H6, D-16) | DB | Colonne 1b ; usage lot 4 |
| RM-028 | Pas de collecte de numéro de pièce d'identité, photo, adresse, date de naissance ou donnée de santé au lot 1. | V (D-15) ; extension **A** (C-08) | — | 1b |
| RM-029 | Un permis non vérifié contre l'original (`verified_at IS NULL`) ne rend pas le conducteur éligible pour une affectation `ACTIVE` (paramétrable). | H ; **A** | APP | 1c |

## 4. Affectation conducteur ↔ véhicule

L'affectation est un intervalle `[valid_from, valid_to)` (fin exclue, NULL = ouverte). Statuts : `PLANNED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED` (D-04).

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-030 | **Éligibilité à la création** : (a) véhicule du tenant, statut `AVAILABLE`, catégorie `requires_driver` ; (b) conducteur du tenant, `ACTIVE` ; (c) permis valide pour une catégorie admise (RM-022) couvrant l'intervalle ; (d) habilitation valide pour la catégorie du véhicule couvrant l'intervalle (RM-023) ; (e) aucun chevauchement (RM-032, RM-033) ; (f) **même site strict** : véhicule, conducteur et affectation partagent le même `site_id` (RM-042) ; (g) pas d'antidatage (RM-041). Échec : `422` avec code stable et liste des motifs (ex. `DRIVER_LICENSE_EXPIRED`). L'ancien critère « aptitude médicale » est **supprimé** (RM-025). | V (D-13, D-15) pour (f)(g) ; H pour la composition | APP | 1c |
| RM-031 | **Revérification à l'activation** (`PLANNED` → `ACTIVE`) : l'éligibilité est réévaluée à la date courante ; échec = refus de l'activation avec motifs. Au lot 1, l'activation est une **action explicite** ; le passage automatique à l'heure de début et la revérification quotidienne relèvent du planificateur (lot 2+, D-12). | V (D-12) pour le report ; H | APP (JOB : lot 2+) | 1c ; JOB lot 2+ |
| RM-032 | **Un véhicule n'a qu'une affectation occupante à un instant donné** : exclusion `gist` sur `valid_during` pour toute affectation `status <> 'CANCELLED'` (une affectation `COMPLETED` conserve son créneau ; sa fin est tronquée à l'instant réel, `valid_to` obligatoire). `409 VEHICLE_ASSIGNMENT_OVERLAP`. | V (D-04) | DB | 1c |
| RM-033 | **Un conducteur ne conduit qu'un seul véhicule à un instant donné** : même règle côté conducteur. `409 DRIVER_ASSIGNMENT_OVERLAP`. | V (D-04) | DB | 1c |
| RM-034 | **Plusieurs conducteurs par véhicule : oui, en séquence, jamais simultanés.** En rotation 2x12h ou 3x8h, chaque poste est une affectation distincte aux bornes contiguës (`valid_to` du poste n = `valid_from` du poste n+1, grâce à la borne exclue). `shift_code` est informatif. Affectations contiguës **manuelles** au lot 1 (défaut C-11) ; planning récurrent : lot 2. | H ; modèle de planning et durée légale **A** (C-11) | DB + APP | 1c ; planning lot 2 |
| RM-035 | Le « binôme » (deux personnes dans l'engin) n'est pas modélisé au lot 1. | **A** | — | Ultérieur |
| RM-036 | **Expiration d'un permis ou d'une habilitation pendant une affectation** : au lot 1, aucune transition automatique. La **conformité est dérivée à la lecture** : l'affectation est présentée avec un drapeau « non conforme » et son motif (`LICENSE_EXPIRED`, `QUALIFICATION_EXPIRED`) dès l'instant d'expiration (RM-021), et figure dans la liste des échéances (US-1.20). Aucune modification rétroactive de l'historique. Aucune nouvelle affectation n'est acceptée pour ce conducteur. La **transition automatique vers `SUSPENDED`**, l'événement d'audit système et les alertes poussées (dispatcher, `HR`, `HSE`) sont **reportés au planificateur** (lot 2+). Une mission déjà en route n'est jamais interrompue automatiquement : non-conformité signalée pour traitement humain. | V (D-12) ; conséquences juridiques **A** | APP (lecture) ; JOB lot 2+ | 1c ; JOB lot 2+ |
| RM-037 | Seuil d'état `EXPIRING` (nombre de jours avant échéance) **configurable par tenant** ; valeur par défaut à définir avec le client. Au lot 1, il pilote l'affichage dérivé et la liste des échéances, sans alerte poussée. | H ; valeur **A** | APP (JOB alertes : lot 2+) | 1b |
| RM-038 | Les changements de statut du véhicule qui rendraient une affectation `PLANNED`/`ACTIVE` caduque sont **refusés** (RM-017, `409`). L'opérateur clôture ou annule d'abord les affectations listées (`COMPLETED`/`CANCELLED`). Le retour à `AVAILABLE` ne réactive aucune affectation. | V (D-11) | APP | 1c |
| RM-039 | Conducteur `UNAVAILABLE`, `SUSPENDED` ou `INACTIVE` : même principe, changement **refusé (`409`)** tant qu'une affectation `PLANNED`/`ACTIVE` existe (RM-020). Aucune clôture automatique à la date de sortie. | V (D-11) | APP | 1c |
| RM-040 | Une affectation `COMPLETED`/`CANCELLED` est immuable (trigger). `vehicle_id`, `driver_id`, `site_id` ne changent jamais après création. Modifier la fin d'une affectation `ACTIVE` est une opération tracée ; l'allonger ré-applique RM-030. Concurrence optimiste `If-Match` (D-19). | V (D-19) ; H | DB + APP | 1c |
| RM-041 | **Pas d'antidatage** : `valid_from ≥ now − tolérance configurable` (tolérance à fixer, aucune valeur supposée). **Pas de dérogation au lot 1** (ni permission dédiée, ni approbation, ni colonne `approved_by`). Une déclaration tardive après coupure réseau relève du lot 4 (offline). | V (D-13) | APP | 1c |
| RM-042 | **Même site strict** : l'affectation porte le `site_id` du véhicule à la création et le conserve ; le conducteur doit avoir ce même site de rattachement (`driver.site_id`). Pas de dérogation `OPS_MANAGER` au lot 1 (défaut C-04). Un trigger garantit l'égalité des sites véhicule/affectation en base. | V (D-13) ; C-04 | DB + APP | 1c |
| RM-043 | Contrôle du temps de repos / fatigue : hors lot 1, paramétrable et validé avec le client et un juriste. | **A** | — | Ultérieur |

## 5. Site et transfert inter-sites

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-050 | Un véhicule ou un conducteur ne change **jamais de tenant**. Un engin vendu ou transféré à une autre entité est réformé (`RETIRED`) puis recréé côté destinataire. | V (isolation, H1) | APP + DB | 1b |
| RM-051 | Le changement de site d'un véhicule ou d'un conducteur dans le **même tenant** est une opération explicite, tracée, **refusée (`409`) si une affectation `PLANNED`/`ACTIVE` existe** (D-13) ; trigger de garde en base. Le « transfert » complet (date d'effet, compteurs à l'instant du transfert, mission en cours) est reporté avec les compteurs et les missions. | V (D-13) | DB + APP | 1b (garde : 1c) ; transfert complet lot 2+ |
| RM-052 | L'historique n'est pas réécrit : les affectations passées gardent leur `site_id` d'origine ; les rapports par site utilisent le site de l'événement, pas le site courant. Une table d'historique de site n'est pas créée au lot 1. | H | APP | 1c |
| RM-053 | Autorisation : l'acteur doit détenir un rôle autorisé sur le site source **et** le site destination (portée `TENANT`, ou `SITE` sur les deux). | H (H7) | APP | 1b |
| RM-054 | Les compteurs sont inchangés par un transfert (RM-060 et suivants s'appliquent normalement). | H | APP | Avec les compteurs |
| RM-055 | Changement de site de rattachement d'un conducteur : ses habilitations restent valables sauf si elles sont propres à un site (`driver_qualification.site_id`). Une habilitation est-elle valable tous sites du tenant ? | H ; **A** | APP | 1b |

## 6. Compteurs (odomètre km, horamètre h) — **lot ultérieur** (D-16)

`vehicle_meter_reading` est livrée avec la **première story de compteur** ; aucune colonne de compteur n'existe sur `vehicle`. Ces règles sont conservées pour verrouiller le futur modèle ; aucune n'est testée ni livrée au lot 1. Valeurs de provenance : `MANUAL`, `MOBILE_CHECKLIST`, `CAN_ECU`, `GPS_DERIVED`, `IMPORT` ; natures de relevé : `READING`, `CORRECTION`, `METER_REPLACEMENT` ; statuts de relevé : `ACCEPTED`, `QUARANTINED`, `REJECTED`.

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-060 | Deux compteurs distincts : odomètre (km) et horamètre (h). Leur pertinence dépend de la catégorie (`has_odometer`, `has_hour_meter`) ; une valeur est refusée pour un compteur non pertinent. | H | APP | Ultérieur (1re story compteur) |
| RM-061 | **Monotonie** : un nouveau relevé doit être ≥ au dernier relevé accepté dont le `recorded_at` est antérieur, et ≤ au suivant. Un relevé qui viole l'ordre est mis en **quarantaine**. | H | APP | Ultérieur |
| RM-062 | **Correction** : seule une opération `CORRECTION` peut abaisser une valeur ; motif, rôle autorisé, nouvel enregistrement référençant l'ancien (qui reste conservé), `audit_event` avant/après. | H | APP | Ultérieur |
| RM-063 | Chaque relevé porte sa **provenance** et son horodatage de lecture ; la valeur « courante » (vue) indique source et date. | V (skill fleet-management) | APP | Ultérieur |
| RM-064 | `CAN_ECU` et relevé humain contrôlé priment sur `GPS_DERIVED` ; un `GPS_DERIVED` n'écrase jamais une valeur d'une autre source (GPS imprécis). | H ; **V** pour la réserve sur le GPS | APP | Ultérieur |
| RM-065 | **Remplacement d'un compteur** : événement `METER_REPLACEMENT` motivé ; continuité du cumul par un décalage enregistré. | H | APP | Ultérieur |
| RM-066 | Relevés hors ligne tardifs : ordonnés par `recorded_at` ; idempotence par `client_event_id` (et `Idempotency-Key`, **lot 4**, D-14) ; doublon rejeté sans erreur. | V (CLAUDE.md) | APP | Lot 4 |
| RM-067 | Plausibilité : écart maximal par unité de temps (par catégorie) **paramétrable** ; au-delà, quarantaine. Aucune valeur par défaut inventée. | H ; valeurs **A** | APP | Ultérieur |
| RM-068 | `recorded_at` dans le futur au-delà de la tolérance de dérive d'horloge : relevé rejeté ou en quarantaine. | V (principe) ; valeur **A** | APP | Ultérieur |
| RM-069 | Un compteur douteux ou en quarantaine ne déclenche pas d'OT automatique. | H | APP | Lot 3 |

## 7. Tonnage : estimé vs mesuré (futurs lots Dispatch/Pesée, rappel des invariants)

Au lot 1, **aucun tonnage n'est enregistré**. Ces règles verrouillent le modèle futur (**tranche : lot 5** pour l'intégration pont-bascule, C-14 ; invariants RM-070 et RM-072 applicables dès la première mission).

| ID | Règle | Nature | Appli. |
|----|-------|--------|--------|
| RM-070 | Le GPS n'est **jamais** une preuve de tonnage ni de chargement/déchargement effectif. | V (H10, CLAUDE.md) | APP |
| RM-071 | Un tonnage **mesuré** provient d'un ticket de pont-bascule (poids brut, tare, net, en kg entiers) ou d'une source approuvée. Le ticket est immuable (pont-bascule, numéro, véhicule, horodatage, source). | V (principe) ; format **A** | APP + DB |
| RM-072 | Un tonnage **estimé** est libellé « estimé », stocké séparément, jamais additionné silencieusement à du mesuré. | H | APP + UI |
| RM-073 | Correction d'une pesée : annulation (ticket référençant l'original) puis nouveau ticket ; jamais de modification. | H | DB + APP |
| RM-074 | Un ticket est unique par `(tenant_id, weighbridge_id, ticket_number)` ; un envoi hors ligne tardif ne crée pas de doublon. | V (skill) | DB |
| RM-075 | Pont-bascule en panne : saisie manuelle dégradée (`source=MANUAL_DEGRADED`) avec justificatif et approbation ; exclue des agrégats « mesuré approuvé » tant qu'elle n'est pas approuvée. | H ; **A** | APP |
| RM-076 | Poids net anormal vs capacité nominale : alerte HSE ; seuil paramétrable, aucune tolérance fixée ici. | H ; valeur **A** | APP |
| RM-077 | Facturation sous-traitants : basée sur le tonnage **mesuré approuvé** par défaut ; toute autre base doit être contractuelle. | H ; **A** | APP |

## 8. GPS : mesures non fiables par nature (futur lot Télématique, rappel des invariants — lot 5)

| ID | Règle | Nature | Appli. |
|----|-------|--------|--------|
| RM-080 | Une position n'est acceptée que si latitude ∈ [-90, 90], longitude ∈ [-180, 180], valeurs finies. (0, 0) est suspect. Une position hors emprise plausible est marquée suspecte, non supprimée. | V (CLAUDE.md) | APP |
| RM-081 | Chaque position stocke l'heure de l'appareil (`recorded_at`) **et** l'heure de réception (`received_at`). Ordre par `recorded_at` ; dérive d'horloge au-delà d'une tolérance **paramétrable** : qualité déclassée. | V (CLAUDE.md) ; valeur **A** | APP |
| RM-082 | La précision déclarée est stockée. Une position imprécise ne déclenche pas à elle seule une entrée/sortie de géorepérage (hystérésis). | H | APP |
| RM-083 | Ingestion hors ligne et tardive : idempotente, tolérante au désordre ; un lot tardif ne réécrit pas un événement dérivé validé. | V (principe) | APP |
| RM-084 | Une trace GPS n'est ni preuve de présence, ni preuve de conformité, ni base de sanction sans validation humaine. | H ; cadre légal **A** | APP + processus |
| RM-085 | Données GPS de salariés : base légale, information, finalités, durée de conservation et droits d'accès à définir avant production (C-08, C-09) ; collecte limitée aux heures de service et aux engins de l'entreprise. | V (CLAUDE.md) ; contenu **A** | politique |
| RM-086 | Aucune donnée GPS réelle de salariés dans les démos et les tests. | V (H9, C-08) | processus |
| RM-087 | La distance/vitesse GPS est dérivée et indicative ; elle ne renseigne pas l'odomètre officiel (RM-064). | H | APP |

## 9. Maintenance et statut véhicule (lien lot Maintenance)

| ID | Règle | Nature | Appli. | Tranche |
|----|-------|--------|--------|---------|
| RM-090 | Au lot 1, le changement de statut véhicule est **manuel** (rôles en RBAC : `OPS_MANAGER`, `WORKSHOP_CHIEF`), soumis à RM-017. Dès le lot Maintenance, `IN_MAINTENANCE` ↔ `AVAILABLE` suit l'ordre de travail. | H | APP | 1b ; lot 3 |
| RM-091 | La remise en service après intervention exige le contrôle qualité et la validation d'un rôle habilité (`WORKSHOP_CHIEF`). | V (skill workshop-maintenance) | APP | Lot 3 |
| RM-092 | La durée d'immobilisation est calculée à partir de `vehicle_status_history` (transitions horodatées par trigger, collectées dès 1b), pas d'une saisie libre. | V (skill) | APP | Table : 1b ; usage : lot 3 |

---

## 10. Récapitulatif par nature

| Nature | Règles |
|--------|--------|
| **V — Fait vérifié** | RM-001 à 007, 009, 010, 014 à 018, 020, 024, 027, 028, 032, 033, 038 à 042, 050, 063, 066, 070, 086 ; (partiellement) 071, 074, 080, 081, 083, 085, 091, 092 |
| **H — Pratique courante / hypothèse** | RM-008, 011 à 013, 021, 023, 026, 029, 030 (composition), 031, 034, 037, 051 à 054, 060 à 062, 064, 065, 067, 069, 072, 073, 075 à 077, 082, 084, 087, 090 |
| **A — À valider (client / juriste guinéen / fournisseur)** | RM-011 (exigence légale), 015 (approbation), 019, 022, 025, 035, 036 (conséquences), 043, 055, 067 (valeurs), 068 (valeur), 071 (format), 075 à 077, 081 (valeur), 084, 085 |

Le tableau est une aide de lecture ; la colonne « Nature » de chaque règle fait foi.

## 11. Points ouverts et leur traitement

Les questions de la revue ont été tranchées par `DECISIONS_A_ARBITRER.md` ; les défauts provisoires s'appliquent tant que le client ou le juriste n'a pas arbitré. Ils **ne doivent pas** être codés comme des faits définitifs.

| # | Point (ancienne numérotation) | Traitement |
|---|-------------------------------|-----------|
| 1 | Catégories de permis guinéennes, durées, engins hors route (RM-022) | **Ouvert** C-07 ; catégories « à valider localement », valeurs fictives en dev |
| 2, 3 | Géolocalisation de salariés ; données de santé (RM-084/085, RM-025) | **Ouvert** C-08 ; données exclues au lot 1 (D-15), aucune donnée GPS réelle |
| 4 | Conséquences d'un permis expiré en cours de mission | **Ouvert** (juriste) ; au lot 1 : conformité dérivée, aucun arrêt automatique (D-12) |
| 5 | Temps de travail, repos, rotations (RM-034, RM-043) | **Ouvert** C-11 ; affectations contiguës manuelles |
| 6 | Conservation légale de l'audit et des données RH | **Ouvert** C-09 ; aucune purge en dev |
| 7 | Rythme de postes, planning récurrent | **Ouvert** C-11 (lot 2) |
| 8 | Habilitation valable tous sites ou par site (RM-055) | **Ouvert** ; colonne `site_id` nullable (NULL = tenant) |
| 9 | Documents véhicule bloquants (RM-019) | **Ouvert** C-06 ; aucun au lot 1 |
| 10 | Qui approuve réforme, correction de compteur, antidatage | Antidatage et dérogation : **tranché**, supprimés du lot 1 (D-13) ; approbation de réforme : **ouvert** |
| 11 | Compteurs CAN ou relevé humain | Reporté avec les compteurs (D-16) |
| 12 | Binôme / co-conducteur (RM-035) | **Ouvert**, hors lot 1 |
| 13 | Même e-mail dans deux tenants | **Tranché** D-06 : e-mail unique par tenant (`citext`), connexion par code d'espace + e-mail |
| 14 | `person` vs `driver` | **Tranché** provisoirement : `driver` conservé (C-05, D-16) |
| 15, 16 | Fournisseur GPS, pont-bascule | **Ouvert** C-14 ; adaptateur simulé uniquement |
