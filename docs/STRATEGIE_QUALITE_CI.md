# Stratégie qualité, tests, environnement local et CI — MINEFLEET 360

> Statut : **proposition de cadrage (phase 0)**, rédigée par l'ingénieur QA/DevOps. Date de référence : 2026-10-25.
> **Rien n'est implémenté, exécuté ni mesuré.** Tous les chiffres sont des **cibles proposées** à valider (client, équipe), jamais des résultats. Les versions d'outils sont à épingler et à vérifier à l'initialisation.
> Références : `CLAUDE.md`, `docs/revues/REVUE_QA_DEVOPS.md` (constats QA-xx), `docs/MENACES_ET_CONTROLES.md` (ST-xx), `docs/MATRICE_RBAC.md`, ADR-001 à ADR-005, `docs/INTEGRATION_GPS_OFFLINE.md`.
> Prérequis (Definition of Ready du premier ticket de code) : QA-02, QA-03, QA-04, QA-21 levés (glossaire d'énumérations, table de décision des erreurs, `authz_matrix.yaml`, squelette OpenAPI).

## 1. Exigences non fonctionnelles mesurables (NFR)

Conventions : **[Cible]** = valeur proposée, non mesurée, à confirmer par test de charge ou par le client ; **[Règle]** = exigence binaire vérifiable sans mesure. La volumétrie réelle est inconnue (Q9 du PRD) : le jeu de données de charge ci-dessous est une **hypothèse de test**, pas une prévision.

### 1.1 Performance API

Environnement de mesure : conteneur API 3.12 + PostgreSQL/PostGIS de même version majeure que la cible, ressources fixées et consignées (CPU/RAM du conteneur), mesure en régime établi après échauffement, client de charge sur la même machine ou le même réseau local. Les résultats sur poste Windows/Docker Desktop ne valent pas pour un hébergement futur : à rejouer sur l'hébergement cible.

| Type d'appel | p95 [Cible] | p99 [Cible] | Charge de référence [hypothèse de test] |
|---|---|---|---|
| Lecture d'une ressource (`GET /vehicles/{id}`) | 300 ms | 800 ms | 20 utilisateurs virtuels simultanés par tenant, 3 tenants |
| Liste paginée avec filtre (`GET /vehicles`, `/drivers`, `/vehicle-assignments`) | 500 ms | 1,2 s | idem, jeu de données ci-dessous |
| Écriture simple (création véhicule, conducteur, permis) | 500 ms | 1,2 s | idem |
| Création d'affectation (éligibilité + contrainte d'exclusion + audit) | 700 ms | 1,5 s | idem + 10 créations concurrentes sur le même véhicule |
| Connexion (hachage argon2id calibré) | 1,0 s | 2,0 s | 5 connexions/s ; le coût du hachage est un paramètre de sécurité, pas une variable à optimiser sous cette cible |
| Lecture du journal d'audit (page filtrée) | 800 ms | 2,0 s | table d'audit du jeu de données |
| Endpoint de santé | 100 ms | 300 ms | — |

Jeu de données de charge [hypothèse de test, Q9 à venir] : 3 tenants fictifs ; par tenant 5 sites, 500 véhicules, 800 conducteurs, 2 000 permis/habilitations, 50 000 affectations historiques, 500 000 événements d'audit. À réviser dès que le client pilote fournit sa volumétrie.

Autres règles :
- **[Règle]** Aucune requête métier sans plan indexé sur `tenant_id` en tête (ST-05 étendu : liste des index attendus du dictionnaire §14 vérifiée par introspection). `EXPLAIN` des 10 requêtes les plus fréquentes archivé à chaque lot (relecture manuelle, pas de seuil automatique).
- **[Règle]** Timeout SQL côté serveur appliqué (ST-85) ; aucune requête n'est autorisée à tenir une connexion sans limite.
- **[Cible]** Taux d'erreur 5xx sous charge nominale : 0 sur le scénario de référence ; tout 5xx est un défaut.
- **[Règle]** Le test de charge ne fait pas partie de la porte de PR (trop variable) ; il est exécuté manuellement avant la fin de chaque tranche de lot et en nocturne quand la CI existe. Un dépassement de budget ouvre un ticket, il ne bloque une livraison que s'il dépasse la cible de plus du double (décision de l'équipe à confirmer).

### 1.2 Taille des réponses et pagination

- **[Règle]** Toute liste est paginée : taille par défaut 25, maximum 100 [Cible à arbitrer, QA-25] ; `limit` hors bornes → 422 (comportement unique pour ST-07) ; tri stable avec clé de départage sur l'identifiant.
- **[Règle]** Total : le compteur `total` est calculé dans le périmètre tenant et site de l'appelant (US-1.28 A6).
- **[Cible]** Réponse JSON d'une page de liste ≤ 100 Kio non compressé, ≤ 30 Kio compressé (gzip/brotli activé) ; réponse d'un détail ≤ 20 Kio.
- **[Règle]** Corps de requête plafonné (ST-85) ; aucun export synchrone non borné ; exports futurs bornés ou asynchrones (C-31).
- **[Règle]** Les champs masqués sont absents de la réponse, non vides ni masqués côté client (RBAC §4.4) : vérifié par le test de sérialisation.

### 1.3 Temps de premier affichage sur réseau 3G dégradé

- Profil de test à figer dans la configuration Playwright/Lighthouse : débit descendant ~0,4 à 1,6 Mbit/s, latence aller-retour 150 à 400 ms, perte de paquets optionnelle ; les valeurs exactes dépendent de l'outil (profils « Slow/Fast 3G » du navigateur) et sont **à consigner dans le dépôt**. Aucun profil n'est « le réseau minier » tant qu'aucune mesure terrain n'existe.
- **[Cible]** Écran de connexion et liste des véhicules : contenu utile affiché (premier affichage significatif) en ≤ 5 s sur le profil le plus lent, cache froid ; ≤ 2 s cache chaud.
- **[Cible]** Poids du JavaScript initial ≤ 250 Kio compressé par route principale ; images/polices self-hosted, pas de ressource tierce bloquante ; budget exprimé dans la configuration de build et vérifié en CI (la CI échoue si dépassé).
- **[Règle]** Sur réseau coupé ou lent, le formulaire conserve la saisie et affiche un état d'attente puis une erreur claire (US-1.29 A2) ; test Playwright avec coupure en cours de soumission, sans double création (idempotence ou contrainte d'unicité, QA-09).
- **[Règle]** Écrans principaux (liste véhicules, conducteurs, affectation) sans défilement horizontal aux largeurs de test **360, 768 et 1280 px** (largeurs proposées pour rendre US-1.29 A3 testable).
- **[Cible]** Accessibilité : zéro violation de niveau « serious/critical » détectée par l'analyse automatique (axe) sur les écrans du Lot 1, plus revue manuelle clavier ; l'analyse automatique ne prouve pas la conformité WCAG 2.1 AA (cible hypothèse).

### 1.4 Disponibilité, sauvegarde, reprise

- **[Cible]** Disponibilité mensuelle de l'API de pilote : 99,5 % hors maintenance annoncée — valeur proposée **sans fondement client** ; à confirmer avec l'hébergement choisi (PRD V4). Aucun SLA ne sera promis avant mesure et choix d'hébergement.
- **[Cible]** RPO et RTO : **non fixés** (PRD V4) ; à définir avec le client. En attendant, **[Règle]** : une procédure de sauvegarde/restauration est écrite et testée sur données fictives (ST-86) avant tout pilote, et le temps de restauration réellement mesuré est consigné.
- **[Règle]** Endpoints `/health/live` (processus) et `/health/ready` (base joignable, migrations à jour) ; démarrage refusé en production si configuration non sûre (ST-80/81).
- **[Règle]** Logs JSON avec `request_id`, sans secret ni donnée personnelle brute (ST-48).

### 1.5 Couverture et non-régression

| Mesure | Cible proposée | Remarque |
|---|---|---|
| Couverture de lignes backend (global) | ≥ 80 % | porte bloquante de CI dès la tranche 1a |
| Couverture de branches des modules `authz`, `assignment`, `identity` | ≥ 90 % | critique ; revue du rapport, pas seulement du chiffre |
| Couverture de lignes frontend (`src/features`) | ≥ 70 % | Vitest |
| Couverture d'isolation des routes | **100 %** des routes tenant-owned ont un test inter-tenant et un test hors site | mesurée par inventaire des routes OpenAPI vs tests générés (ST-01/ST-02), pas par couverture de lignes |
| Règles d'affectation | chaque refus du tableau règle → test (PRD §9.1) | table de traçabilité tenue à jour |
| Mutation testing | hors Lot 1 | à envisager sur `authz` et `assignment` si le temps le permet ; pas de dépendance ajoutée sans décision |

Ces seuils sont des planchers : une couverture élevée ne prouve pas la qualité (tests tautologiques, QA §6). Le **cliquet** : le seuil ne peut que monter ; une baisse exige une justification dans la PR.

Zéro régression :
- **[Règle]** Tout défaut corrigé est accompagné d'un test qui **échoue avant** le correctif et réussit après (preuve consignée dans la PR : sortie des deux exécutions).
- **[Règle]** Les tests d'isolation, de matrice d'autorisation, de migration et de contrat sont **rejoués intégralement** à chaque PR (pas de sélection partielle) ; marqueur `regression` pour les tests nés de défauts, jamais ignorés.
- **[Règle]** Aucun test désactivé (`skip`, `xfail`) sans ticket référencé et date de revue ; la CI liste les tests ignorés et échoue si leur nombre augmente sans mise à jour d'un fichier de suivi.
- **[Règle]** Les tests flaky sont mis en quarantaine **avec ticket sous 1 jour ouvré** et réparés ; pas de relance automatique qui masque l'instabilité sur la porte de PR.

### 1.6 Exigences de sécurité vérifiables (rappel, détail dans MENACES)

- **[Règle]** Zéro secret dans le dépôt ou l'historique (ST-81, gitleaks) ; images non root ; aucune vulnérabilité de gravité haute/critique corrigeable non traitée (ST-82, ST-82b scan d'images).
- **[Règle]** `mf_app` : non super-utilisateur, sans `BYPASSRLS`, sans `UPDATE/DELETE` sur `audit_event` (ST-03/71) — vérifié au démarrage des tests d'intégration.
- **[Règle]** Toute écriture produit un événement d'audit (ST-73) ; aucune donnée sensible dans logs et audit (ST-48/74).

## 2. Pyramide de tests et outils

### 2.1 Vue d'ensemble

| Niveau | Objet | Outils | Où | Porte PR |
|---|---|---|---|---|
| Unitaire back | Règles de domaine pures : intervalles `[début, fin)`, éligibilité, normalisation (plaque, matricule), masquage, horloge | pytest | conteneur API, sans base | oui |
| Propriété | Invariants (aucune paire d'intervalles occupants ne se chevauche ; aller-retour fuseau) | `hypothesis` (optionnel, cf. 2.3) | idem | oui si adopté |
| Intégration back | Services + repositories sur PostgreSQL/PostGIS réel : RLS, FK composites, exclusion, rôles DB, transactions, audit | pytest + base PostgreSQL de test (service Docker) | conteneur API + `db` | oui |
| API / composant | Routes FastAPI via client HTTP : authz, codes d'erreur, masquage, idempotence | pytest + `TestClient` (httpx) | idem | oui |
| Isolation tenant | Matrice générée (rôle × portée × tenant × propriété) + IDOR, test RLS direct | pytest paramétré depuis `authz_matrix.yaml` | idem | oui, bloquant |
| Contrat | OpenAPI exporté = fichier versionné ; compatibilité ascendante ; client TS à jour | export OpenAPI, `oasdiff`, génération du client | CI | oui |
| Fuzz de contrat | Aucune 500 sur entrées invalides ; conformité des réponses au schéma | Schemathesis (cf. 2.3) | CI | version courte en PR, complète en nocturne |
| Migration | up/down/up, dérive modèle/migration, introspection (ST-04/05/83), migration de données | pytest + Alembic | CI | oui |
| Front unitaire/composant | Composants, formulaires, garde de routes, états vide/erreur/403/404 | Vitest + Testing Library | Node | oui |
| E2E | Parcours bout en bout contre la pile `docker compose` : login, création véhicule, affectation, refus, coupure réseau | Playwright (Chromium) | CI + local | smoke en PR, complet en nocturne |
| Accessibilité | Analyse automatique + parcours clavier | `@axe-core/playwright` | CI | oui sur écrans du lot |
| Performance | Budgets de latence et de volumétrie | k6 (image Docker) | nocturne / manuel | non |
| Sécurité statique | Lint de sécurité, secrets, dépendances, images | ruff (règles `S`), gitleaks, pip-audit, npm audit, Trivy | CI | oui |

Principe : la majorité des tests s'exécute **dans des conteneurs** (Python 3.12, ADR-004) ; le Python 3.10 du poste ne sert pas à exécuter le projet.

### 2.2 Tests d'isolation tenant générés depuis la matrice RBAC

Objectif : transformer `MATRICE_RBAC.md` en oracle exécutable, de façon que l'**oracle ne soit pas déduit du code testé**.

1. **Source** : `authz_matrix.yaml` (à créer, QA-21) — par permission : module, ressource, action, rôles autorisés avec portée requise (`TENANT`, `SITE`, `SITE_ONLY`), règle d'objet (`owner`), champs masqués, action d'audit, route (`operationId`). Revue obligatoire par `security-engineer` (CODEOWNERS).
2. **Inventaire des routes** : l'OpenAPI exporté porte l'extension `x-permission` ; ST-01 échoue si une route n'a pas de permission ni n'est dans la liste blanche publique (`/auth/login`, `/auth/refresh`, reset, santé).
3. **Fixtures** (§8.1 de MENACES) : tenants A et B, sites A1/A2/B1/B2, un utilisateur par rôle × portée utile, ressources dans chaque tenant et site, valeurs sentinelles, plus : un site à décalage non nul et un site à changement d'heure (QA-22).
4. **Générateur** : pour chaque (route, rôle, portée, cible) il calcule le code attendu avec la **table de décision de QA-03** (401 / 403 sans permission / 404 hors tenant, hors site ou hors propriétaire / 2xx) et vérifie :
   - la réponse (code, corps normalisé, en-têtes) ;
   - l'**équivalence** « ressource étrangère ≡ UUID inexistant » ;
   - l'absence de modification en base après un refus (relecture directe) ;
   - les champs présents/absents selon le rôle ;
   - l'événement d'audit de refus quand la politique l'exige.
5. **Niveaux de défense testés séparément** : (a) la couche applicative avec une RLS désactivée dans une base de test dédiée (prouve que le filtre applicatif seul suffit) ; (b) la RLS seule par SQL direct avec `mf_app` (ST-03) ; (c) les FK composites (ST-04).
6. **Tests canari** (méta-tests) : une suite à part retire volontairement un filtre de tenant d'un repository de test et vérifie que la suite d'isolation **échoue** ; protège contre des tests devenus tautologiques.
7. **Garde de dérive** : un test compare la liste des routes de l'OpenAPI et celle de la matrice ; toute nouvelle route sans entrée échoue le build.

Contrainte d'exécution : toute connexion de test applicative utilise `mf_app` ; une connexion super-utilisateur ou propriétaire contourne la RLS et rendrait les tests non représentatifs (le harnais échoue s'il détecte `rolsuper` ou `rolbypassrls`).

### 2.3 Registre des dépendances de test et d'outillage (à approuver, CLAUDE.md)

| Outil | Rôle | Justification | Alternative écartée | Décision |
|---|---|---|---|---|
| pytest, pytest-cov | Exécution et couverture | Standard (CLAUDE.md) | unittest | Retenu |
| httpx (via `TestClient` FastAPI) | Appels API | Déjà requis par le client de test FastAPI | requests | Retenu |
| Base PostgreSQL/PostGIS en service Docker (compose en local, `services:` en CI) | Fidélité RLS, PostGIS, `btree_gist`, exclusion | Même image qu'en dev ; ADR-004 interdit SQLite | testcontainers | **Retenu** ; testcontainers écarté au Lot 1 car il exige que pytest accède au démon Docker depuis le conteneur de test (montage du socket) — complexité et risque de sécurité inutiles sous Windows. À reconsidérer si les tests tournent sur l'hôte |
| Base de test par modèle (`CREATE DATABASE ... TEMPLATE`) | Rapidité, isolation entre tests | Évite de rejouer les migrations à chaque test | transaction annulée (incompatible avec les tests de concurrence et de RLS multi-transactions) | Retenu |
| pytest-xdist | Parallélisme (une base par worker) | Réduit la durée de CI | exécution séquentielle | Optionnel, à décider selon la durée mesurée |
| `hypothesis` | Propriétés sur intervalles et fuseaux | Les cas limites de `[début, fin)` et de minuit local se prêtent mal à l'énumération manuelle | tests par exemples seulement | **À approuver** (dépendance de dev) |
| Port `Clock` maison | Contrôle du temps | Évite une dépendance (freezegun) et exerce le même code qu'en production | freezegun / time-machine | Retenu |
| import-linter | Frontières de modules | Déjà prévu ADR-001 | revue manuelle | Retenu |
| ruff (lint + format, règles `S` de sécurité) | Lint, format, contrôles de type bandit | Un seul outil ; évite bandit | flake8 + black + bandit | Retenu |
| mypy | Types | ADR-004 | pyright | Retenu |
| Alembic (`alembic check`) | Dérive modèle/migration | Intégré à l'outil de migration | comparaison manuelle | Retenu |
| `pg_dump --schema-only` (déjà dans l'image PostgreSQL) | Comparer le schéma avant/après aller-retour | Aucun ajout | outil tiers | Retenu |
| Schemathesis | Fuzz à partir d'OpenAPI | Détecte les 500 et les écarts schéma/réponse (ST-39), complète les tests écrits | tests manuels de payloads | **À approuver** (dépendance de dev) |
| `oasdiff` (binaire/image Docker, pas de dépendance applicative) | Détection de rupture d'API | Évite les ruptures silencieuses (contrat versionné) | diff texte du JSON | **À approuver** |
| openapi-typescript | Client TS typé | Prévu ADR-004 ; test de dérive en CI | écriture manuelle | Retenu |
| Vitest + Testing Library | Tests front | CLAUDE.md | Jest | Retenu |
| MSW | Simulation d'API en test composant | Couche réseau réaliste et rejouable (coupures, 409) | mocks de `fetch` ad hoc | À approuver |
| Playwright (Chromium seul en PR) | E2E, réseau coupé/lent, horloge | CLAUDE.md ; émulation hors ligne et horloge intégrées | Cypress | Retenu |
| `@axe-core/playwright` | Accessibilité automatique | Détecte une partie des violations | revue manuelle seule | À approuver |
| k6 (image Docker, aucune installation) | Charge | Seuils exprimés en code, exécution conteneurisée | Locust (Python) | À approuver ; Locust acceptable si l'équipe préfère rester en Python |
| gitleaks (binaire/image) | Secrets sur dépôt et historique | ST-81 | revue manuelle | Retenu |
| pip-audit, npm audit | Dépendances | ST-82 | — | Retenu |
| Trivy et hadolint | Images et Dockerfile | Supply chain (C-32) | — | À approuver |
| pre-commit (cadre) | Crochets locaux identiques à la CI | Détecte tôt ; fonctionne avec le Python 3.10 local | scripts maison | À approuver |

Règle : aucun ajout au-delà de ce registre sans mise à jour de ce tableau et validation de l'équipe (pas de dépendance spéculative).

### 2.4 Tests de migration (Alembic)

1. **up / down / up** sur base vierge : `upgrade head` → introspection (ST-04/05) → `downgrade base` → vérifier que le schéma est vide (hors extensions et rôles créés par `infra/`) → `upgrade head` → comparaison du schéma avec la première montée (`pg_dump --schema-only` normalisé).
2. **Dérive** : `alembic check` échoue si les modèles diffèrent des migrations.
3. **Pas de pas-à-pas fragile** : pour chaque révision, `upgrade` puis `downgrade -1` puis `upgrade` ; une révision non réversible doit déclarer sa stratégie (script de documentation + marqueur lu par le test) et être validée explicitement (CLAUDE.md : migration irréversible = approbation).
4. **Migrations de données** : base peuplée de données fictives avant la révision, assertions après (comptes, intégrité des FK composites, absence de ligne sans `tenant_id`).
5. **Propriétés vérifiées après chaque migration** (ST-05) : `tenant_id NOT NULL`, RLS activée et forcée sur toute table métier (liste blanche explicite des tables globales, QA-17), absence de FK simple entre tables métier, privilèges de `mf_app` (pas de `UPDATE/DELETE/TRUNCATE` sur `audit_event`), index attendus.
6. **Concurrence** : une migration qui verrouille longuement une table est signalée en revue ; pas de mesure automatique au Lot 1.
7. **Rôles** : les migrations s'exécutent avec `mf_owner` ; l'application et les tests applicatifs avec `mf_app`.

### 2.5 Tests de contrat OpenAPI

- Le fichier `openapi.json` exporté est **versionné** ; la CI régénère l'export et échoue s'il diffère du fichier commité (dérive).
- `oasdiff` compare avec `main` : tout changement cassant (champ requis ajouté, énumération restreinte, route supprimée) échoue sans label explicite de version majeure.
- Le client TypeScript généré est régénéré et comparé (dérive).
- Règles de forme vérifiées sur le schéma : aucun identifiant entier, aucun paramètre `tenant_id` en entrée (ST-06), `extra="forbid"` sur les entrées, schéma d'erreur unique, `x-permission` présent partout.
- Schemathesis : exécution courte en PR (profil réduit, graine fixe), complète en nocturne ; exigence minimale « aucune réponse 5xx, toute réponse conforme au schéma ».
- Tests de rétro-compatibilité des champs masqués : la réponse d'un rôle restreint est un sous-ensemble valide du schéma (champs optionnels).

### 2.6 Scénarios de panne : GPS hors ligne, horloge, rejeu

Ces tests concernent les lots 4 et 5 ; le **socle** (idempotence, double horodatage, quarantaine, horloge injectable) doit exister dès le Lot 1 pour ne pas être refait. Aucun n'est écrit ni exécuté. L'adaptateur simulé (INTEGRATION §1.1) est l'unique source de défauts : il offre des **options d'injection** pour chaque ligne ci-dessous.

| Scénario | Injection | Assertion | Niveau | ST |
|---|---|---|---|---|
| Doublon (même clé) | rejeu du même lot N fois | un seul enregistrement, compteur de doublons, réponse partielle correcte | intégration | ST-91 |
| Doublon à contenu différent (même instant, même appareil) | deux mesures au même `device_time` | distinction par empreinte du contenu (si pas de `seq`), aucune perte | intégration | ST-91 |
| Événement tardif | `received_at − device_time` > seuil | stocké, drapeau `late`, état et géofences recalculés, pas d'alerte « temps réel » | intégration | — |
| Hors ordre | position plus ancienne que la dernière connue | insérée à sa place, dernière position inchangée | intégration | — |
| Décalage d'horloge appareil | offset configurable | drapeau `clock_skew_suspect`, deux horodatages conservés, `device_time` non écrasé | unitaire + intégration | ST-92 |
| Horodatage futur | `device_time` > `received_at` + tolérance | quarantaine avec motif ; jamais utilisé pour droits ou audit | intégration | ST-92 |
| Coordonnées invalides | latitude > 90, NaN, (0,0), précision absente | quarantaine, brut conservé, aucune géofence calculée | unitaire + intégration | ST-93 |
| Saut improbable | deux points trop éloignés | drapeau `suspect_jump`, exclu des distances | unitaire | — |
| Silence réseau appareil | aucun paquet puis rafale | état `no_signal`, aucune interpolation, rafale traitée comme tardive | intégration | — |
| Appareil d'un autre tenant | clé de A pour un véhicule de B | `404` (D-05a : ressource hors tenant), rien d'écrit | API | ST-90 |
| Rejeu de commande hors ligne | même `Idempotency-Key`, même corps | réponse mémorisée, un seul effet | API | ST-98 |
| Même clé, corps différent | idem | 422 | API | ST-98 |
| Session expirée pendant la file | jeton expiré, puis reconnexion | rejeu après authentification ; acteur = session, jamais le payload | e2e | ST-97/98 |
| Droits retirés entre-temps | rôle révoqué pendant la période hors ligne | action rejetée en « à corriger », jamais supprimée silencieusement | e2e | ST-98 |
| Conflit de version | `If-Match` périmé | 409 + état serveur ; fusion proposée | API + e2e | — |
| Appareil perdu | session révoquée côté serveur | stockage local vidé, synchronisation refusée (401) | e2e | ST-97 |
| Géofence : va-et-vient | points oscillant autour d'une frontière | hystérésis, pas d'événements en rafale | unitaire | — |
| Recalcul idempotent | données tardives dans une fenêtre déjà calculée | mêmes événements après recalcul, trace de l'opération | intégration | — |
| Tonnage depuis GPS | recherche de chemin d'écriture | aucun ; `source_type` obligatoire | statique + intégration | ST-94 |

Outils : horloge applicative injectée côté serveur ; côté navigateur, émulation hors ligne et horloge contrôlable de Playwright ; coupures en cours de requête et ralentissement via le protocole du navigateur. Les seuils (retard, tolérance, saut, hystérésis) sont des **paramètres** : les tests lisent la configuration (QA-14).

### 2.7 Tests spécifiques à surveiller

- Concurrence (ST-53) : N transactions réelles sur la même ligne, y compris sur deux connexions distinctes ; résultat attendu « exactement une réussit ».
- Pool de connexions : alternance A/B sur la même connexion, pas de fuite de `app.tenant_id` (ST-03).
- Authentification : rejeu, vol de refresh, période de grâce (QA-27), jeton altéré (ST-62 à ST-68), tenant suspendu (QA-30).
- Journaux : recherche des valeurs sentinelles dans tous les logs capturés (ST-48).
- Fuseaux (QA-22) : au moins un site à décalage non nul et un site à changement d'heure dans chaque test de date.

## 3. Environnement de développement local

Contraintes constatées : Windows 11, Docker 29.5.3 opérationnel, Python 3.10.11 local (cible 3.12 en conteneur), Node 20.19 local, absence de `psql`, `uv`, `pnpm`, et — constaté lors de la revue — de `make` et `gh`, avec `core.autocrlf=true`. **Principe : tout s'exécute dans Docker ; aucun outil n'est requis sur l'hôte hormis Docker et Git.**

### 3.1 Composition (`docker compose`, à créer lors de l'initialisation du monorepo)

| Service | Image / build | Rôle | Remarques |
|---|---|---|---|
| `db` | image PostGIS 16 officielle, **tag épinglé** (à vérifier à l'init) | PostgreSQL 16 + PostGIS | volume nommé ; port publié seulement sur `127.0.0.1` ; scripts d'initialisation de `infra/db/init/` : rôles `mf_owner` et `mf_app`, extensions `postgis` et `btree_gist` (et `citext` si retenu), bases `mf_dev` et `mf_test` |
| `api` | build `backend/` (Python 3.12-slim, utilisateur non root) | FastAPI | rechargement à chaud ; sur Docker Desktop/Windows activer le sondage de fichiers si les événements de volume ne sont pas fiables |
| `web` | build `frontend/` (Node, utilisateur non root) | Vite | proxy vers `api` ; build de production testé séparément |
| `mailpit` (profil optionnel) | image officielle | Capture d'e-mails d'invitation (US-1.04) | à n'activer que si l'envoi réel d'e-mails est retenu ; n'envoie rien à l'extérieur |
| `tools` (profil optionnel) | image Python 3.12 du projet | Lint, types, tests, migrations, k6, gitleaks | évite toute installation sur l'hôte |

- **Santé** : `healthcheck` sur `db` et `api` ; `api` démarre après `db` sain ; `web` après `api`.
- **Limites** : ressources du conteneur documentées pour que les mesures de §1.1 soient reproductibles.
- **Rôles de base de données** : `mf_owner` n'est utilisé que par Alembic ; l'API et les tests se connectent avec `mf_app` (ADR-002). Les scripts d'initialisation ne s'exécutent qu'à la première création du volume : la procédure `reset-db` (suppression du volume, **destructive, locale uniquement**) est documentée avec garde-fou (refus si l'environnement n'est pas `local`) et n'est lancée que par l'utilisateur.
- **Aucun** service payant, aucun appel sortant vers un fournisseur GPS ou de messagerie réel.

### 3.2 Variables d'environnement

- Fichier `.env.example` versionné, **sans secret** : valeurs `CHANGE_ME` explicites, URL de base de données avec marqueurs, `ENV=local`, `TZ`/fuseau par défaut `Africa/Conakry`, durées et seuils (clés de configuration de QA-14), `CORS_ALLOWED_ORIGINS` explicite (pas de `*`).
- `.env` non versionné (ignoré par Git) ; un script d'initialisation local génère des secrets aléatoires pour la base et la clé de signature, à usage de développement uniquement.
- L'application refuse de démarrer si `ENV=production` avec secret par défaut, `debug` actif ou clé vide (ST-81).
- Variables lues via `pydantic-settings` (ADR-004), validées au démarrage ; aucune variable contenant un secret n'est journalisée.
- La CI n'a besoin d'aucun secret de dépôt au Lot 1 : les mots de passe de base sont générés par exécution.

### 3.3 Commandes : compatibles Windows sans `make`

Principe : une **liste unique de commandes `docker compose`** documentée dans le README du dépôt, enveloppée de deux façons équivalentes — un `Makefile` (pour Linux, CI, WSL) et un jeu de scripts PowerShell dans `scripts/` (pour Windows) ; les deux ne font qu'appeler `docker compose run ...`. Aucune logique propre au Makefile. `just`/`task` sont écartés pour ne pas ajouter un binaire.

| Action | Contenu |
|---|---|
| `up` / `down` | démarrer / arrêter la pile |
| `lint` | ruff check + format --check, mypy, import-linter, ESLint, tsc |
| `test` | tests back (unitaire + intégration), puis tests front |
| `test-isolation` | suite d'isolation et de matrice seule (retour rapide) |
| `migrate` | `alembic upgrade head` avec `mf_owner` |
| `migration-check` | up/down/up + dérive |
| `contract` | export OpenAPI, diff, régénération du client |
| `e2e` | Playwright contre la pile compose |
| `audit` | pip-audit, npm audit, gitleaks |
| `build` | construction des images (sans pousser) |
| `seed` | données fictives (refus si `ENV=production`, ST-84) |
| `reset-db` | suppression du volume local (destructif, local, confirmation interactive) |

- **Fins de ligne** (QA-28) : `.gitattributes` avec `eol=lf` pour `*.sh`, `*.sql`, `Dockerfile*`, `*.yml`, `*.yaml`, `*.py`, `*.ts`, `*.json` ; un test de CI échoue si un CRLF apparaît dans ces fichiers.
- **Crochets locaux** (pre-commit, s'ils sont approuvés) : ruff, détection de secrets, vérification des fins de ligne, message de commit conventionnel.
- Le Python 3.10 de l'hôte n'est pas utilisé ; `requires-python >=3.12` empêche une installation accidentelle.

### 3.4 Données fictives

- Générées par un script reproductible (graine fixe), identifiées comme fictives : domaines d'e-mail réservés (`.invalid`), numéros de téléphone fictifs, immatriculations et numéros de permis à préfixe explicite (ex. `PERMIS-FICTIF-`), noms génériques (`Nom-Test`), coordonnées issues d'itinéraires synthétiques — **aucune trace réelle** (H9, RM-086).
- Deux jeux : « démonstration » (2 tenants, quelques sites, scénarios d'isolation visibles) et « test » (fixtures A/B/rôles/sentinelles, plus volumétrie de charge). Un test vérifie l'absence d'e-mail ou de téléphone hors des domaines/plages fictifs réservés.
- Le seed s'exécute avec le rôle applicatif, jamais avec le propriétaire, et refuse `ENV=production` (QA-18).

## 4. Pipeline CI cible (GitHub Actions) — à créer plus tard

> Aucun fichier de workflow n'est créé par cette mission. Le choix d'hébergement du dépôt reste à décider (QA-23). La même suite doit être exécutable localement (§3.3) : la CI n'est que le second exécutant.

### 4.1 Déclencheurs et règles générales

- `pull_request` vers `main` (portes bloquantes) ; `push` sur `main` (rejeu complet) ; `schedule` nocturne (charge, fuzz complet, e2e complet, audits) ; `workflow_dispatch` manuel.
- Permissions du jeton réduites à `contents: read` par défaut ; élargissement par tâche et justifié.
- Actions tierces **épinglées par empreinte de commit** (pas de tag mobile) et mises à jour surveillées ; délais d'expiration (`timeout-minutes`) sur chaque tâche ; `concurrency` pour annuler les exécutions obsolètes.
- Pas de secret de dépôt au Lot 1 ; pas de déploiement : **aucune tâche de livraison continue** (CLAUDE.md : aucun déploiement sans approbation explicite).
- Caches de dépendances indexés sur les fichiers de verrouillage ; lockfiles obligatoires (ST-82).
- Les sorties de test (rapports de couverture, JUnit, rapports Playwright, `openapi.json`) sont publiées comme artefacts.

### 4.2 Tâches et portes

| Tâche | Contenu | Bloquante en PR |
|---|---|---|
| `lint-back` | `ruff check` (dont règles `S`), `ruff format --check`, `mypy`, `import-linter`, test d'architecture (SQL hors dépôts, routes sans `TenantContext`) | oui |
| `lint-front` | ESLint (dont `no-restricted-imports` ADR-001), `tsc --noEmit`, vérification de format | oui |
| `test-back` | unitaire + API ; couverture avec seuils §1.5 | oui |
| `test-integration` | PostgreSQL/PostGIS en service ; rôles `mf_owner`/`mf_app` ; RLS, FK composites, exclusion, concurrence, audit ; **suite d'isolation et de matrice complète** | oui |
| `migrations` | up/down/up, dérive `alembic check`, introspection (ST-04/05/83), migrations de données | oui |
| `contract` | export OpenAPI = fichier versionné ; `oasdiff` ; client TS à jour ; Schemathesis profil court | oui |
| `test-front` | Vitest, couverture | oui |
| `e2e-smoke` | pile compose, Playwright Chromium : login, isolation visible, création + affectation, refus, coupure réseau | oui |
| `a11y` | axe sur les écrans du Lot 1 | oui (violations sérieuses/critiques) |
| `security-deps` | `pip-audit`, `npm audit --omit=dev` au niveau « high » ; échec sur vulnérabilité haute/critique non acceptée par une dérogation écrite et datée | oui |
| `security-secrets` | gitleaks sur la plage de commits de la PR (et historique complet en nocturne) | oui |
| `build-images` | construction `api` et `web` sans publication ; hadolint ; Trivy (gravité haute/critique corrigeable) ; contrôle utilisateur non root ; démarrage et `/health/ready` | oui |
| `eol-check` | absence de CRLF dans les fichiers sensibles | oui |
| `nightly-load` | k6 avec seuils §1.1 | non (ouvre un ticket) |
| `nightly-full` | Schemathesis complet, e2e complet (Chromium + autre moteur à décider), audit d'historique | non (ouvre un ticket) |

Porte globale : la fusion exige que **toutes** les tâches bloquantes réussissent (statuts requis) ; aucun contournement administrateur sans trace écrite. Le seuil de couverture ne baisse pas (cliquet).

### 4.3 Livraison et retour arrière (documentés, non exécutés)

- Les images sont étiquetées par l'empreinte du commit et par version sémantique ; aucune image `latest` utilisée en production.
- **Retour arrière applicatif** : redéploiement de l'image précédente (étiquette connue) ; condition : les migrations appliquées sont rétro-compatibles avec N−1.
- **Migrations** : stratégie *expand / contract* — ajout rétro-compatible, bascule applicative, suppression différée dans une version ultérieure ; `downgrade` est un outil de développement et de test, **pas** la procédure de production par défaut ; toute opération destructive ou irréversible exige une approbation explicite et une sauvegarde vérifiée préalable.
- **Données** : restauration depuis sauvegarde testée (ST-86) ; temps réel mesuré consigné ; jamais de restauration qui mélange des tenants.
- **Configuration** : variables versionnées par environnement ; retour à la configuration précédente documenté.
- Chaque lot produit une fiche « retour arrière » dans la PR de livraison (version précédente, migrations en jeu, risques, vérifications post-retour). Aucun déploiement ni migration en production n'est lancé sans approbation explicite de l'utilisateur.

## 5. Definition of Done

### 5.1 DoD commune (toute PR)

- [ ] Périmètre conforme à la story ; critères d'acceptation sans alternative ouverte (QA-15) ; décisions liées consignées.
- [ ] Tests ajoutés : unitaires, intégration, API ; test **négatif** pour chaque règle bloquante ; test d'isolation inter-tenant **et** hors-site pour chaque route tenant-owned ; test de masquage si la réponse porte des données de personne.
- [ ] Toutes les portes bloquantes de §4.2 vertes **ou** blocage explicitement rapporté (jamais « CI verte » sans exécution).
- [ ] Migration Alembic : revue, réversible ou stratégie documentée, test up/down/up, aucune opération destructive non approuvée.
- [ ] OpenAPI régénéré, diff de contrat revu, client TS à jour.
- [ ] Audit : événement par mutation (et refus selon la politique), sans donnée sensible ; logs structurés sans PII.
- [ ] Documentation mise à jour (ADR, dictionnaire, matrice, README) ; variables d'environnement documentées dans `.env.example`.
- [ ] Aucune nouvelle dépendance hors registre §2.3 ; audit des dépendances passé.
- [ ] Pas de secret ; gitleaks vert.
- [ ] Description de PR : ce qui a été exécuté (commandes et sorties réelles), ce qui ne l'a pas été, risques résiduels, plan de retour arrière.
- [ ] Revue par un autre contributeur ; revue `security-engineer` pour `authz_matrix.yaml`, authentification, RLS, audit, migrations.

### 5.2 DoD par lot

| Lot | Critères supplémentaires |
|---|---|
| **1a Socle** | Harnais d'isolation (fixtures A/B, générateur de matrice, tests canari) opérationnel ; ST-01 à ST-09 et ST-10 à ST-29 retenus pour la tranche passent ; `mf_app` vérifié (`rolsuper`, `rolbypassrls`, privilèges d'audit) ; CI locale équivalente documentée ; décisions QA-01 à QA-04 appliquées |
| **1b Référentiels** | ST-30 à ST-49 passent (masquage par rôle sur chaque réponse contenant des données de personne, aucune valeur sentinelle dans logs ni audit) ; unicités normalisées (plaque, parc, matricule) testées ; fixtures multi-fuseaux pour les dates de permis |
| **1c Affectations + UI** | Matrice « règle d'affectation → test » complète (chevauchement véhicule, chevauchement conducteur, conducteur inactif, non habilité, véhicule indisponible, site différent, bornes `[début, fin)`) ; concurrence réelle (ST-53) ; job de conformité exécuté avec horloge figée ; UI : états vide/chargement/erreur/403/404/409/422, largeurs 360/768/1280, axe sans violation sérieuse, parcours clavier, coupure réseau sans perte de saisie ; démonstration sur deux tenants fictifs ; revue sécurité + QA de fin de lot (CLAUDE.md) |
| **2 Missions** | Tonnage mesuré uniquement avec source et ticket immuable (RM-071/073/074) ; correction par événement correctif ; aucun chemin GPS → tonnage ; libellés « estimé »/« mesuré » testés |
| **3 Ordres de travail** | Machine d'états testée (transitions autorisées et refusées) ; véhicule en maintenance non affectable ; durées d'immobilisation calculées depuis les transitions horodatées (RM-092) |
| **4 Checklist hors ligne** | Scénarios du §2.6 pour la file hors ligne (doublon, session expirée, droits retirés, conflit 409, appareil perdu) en e2e réseau coupé ; stockage local sans donnée RH sensible, purgé à la déconnexion (ST-97) ; budgets de §1.3 mesurés sur appareil réel de milieu de gamme (à définir) |
| **5 GPS simulé** | Tous les scénarios dégradés du tableau 1.3 d'INTEGRATION avec assertions ; authentification d'appareil par tenant (ST-90) ; purge/anonymisation testée (ST-96) ; accès aux positions limité et audité (ST-95) ; aucun GPS réel |
| **6 Dashboard** | Chaque indicateur affiche définition, source et statut (mesuré/estimé/saisi) ; portée `SITE` respectée (US-6.07) ; requêtes agrégées dans les budgets de §1.1 ; aucune fuite par agrégat inter-tenant |

## 6. Stratégie de branches, commits, versions

- **Branche principale `main`** (renommer `master` avant le premier commit, QA-23), **protégée** dès qu'un dépôt hébergé existe : pas de poussée directe, fusion par pull request, statuts de CI requis (§4.2), branche à jour avant fusion, historique linéaire (fusion par *squash* ou *rebase*), suppression de la branche après fusion. Si le plan d'hébergement ne permet pas la protection technique, la règle est appliquée par discipline et vérifiée en revue (à indiquer dans la décision d'hébergement).
- **Branches courtes** : `feat/<module>-<sujet>`, `fix/…`, `docs/…`, `chore/…`, `test/…` ; durée de vie de quelques jours ; une PR = une tranche verticale **petite** (CLAUDE.md : petits incréments).
- **Revue** : une approbation minimale ; `CODEOWNERS` imposant la revue `security-engineer` sur `authz_matrix.yaml`, `backend/alembic/`, `infra/`, authentification et audit. Pour un contributeur unique : auto-revue sur la liste de §5.1 et exécution locale complète documentée.
- **Commits conventionnels** : `type(scope): sujet` avec types `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `security`, et `scope` = module (`identity`, `fleet`, `workforce`, `assignment`, `audit`, `organization`, `infra`, `web`). Corps en français, changement cassant signalé par `!` et `BREAKING CHANGE:`. Vérification par crochet local et par une tâche de CI sans dépendance supplémentaire (expression régulière) ; les lignes d'attribution requises par l'outil de génération s'ajoutent en pied de message.
- **Pas de commit** de secrets, de données réelles, de fichiers générés volumineux ; `.gitignore` et gitleaks.
- **Versionnement** : SemVer `0.y.z` tant que le produit n'est pas en production (changement cassant → `y`) ; étiquettes `vX.Y.Z` annotées sur `main` ; API préfixée `/api/v1`, une rupture de contrat crée `/api/v2` en parallèle (détectée par `oasdiff`) ; journal des modifications tenu à partir des commits conventionnels (outil de génération optionnel, non ajouté d'office).
- **Correctifs urgents** : branche `fix/` depuis l'étiquette de production, PR avec test de non-régression, nouvelle étiquette patch ; aucune exception à la porte de CI.
- **Étiquettes** et branches de publication protégées contre la suppression.

## 7. Statut de vérification

| Élément | État |
|---|---|
| Ce document | **Rédigé**, non relu par l'équipe ni validé par le client |
| Valeurs de §1 (latences, tailles, couverture, disponibilité, budgets 3G) | **Cibles proposées, aucune mesure** (aucun code, aucune volumétrie) |
| Outils du §2.3 | **Aucun installé, aucun exécuté**, versions non vérifiées |
| Pile `docker compose`, Makefile/scripts, workflows | **N'existent pas** |
| Docker 29.5.3 présent ; `make` et `gh` absents du PATH de Git Bash ; `core.autocrlf=true` ; branche `master` sans commit | **Constatés** par commandes lors de cette mission |
| Tous les ST-xx de `MENACES_ET_CONTROLES.md` | **À écrire**, aucun n'a été exécuté |

## 8. Prochaines étapes recommandées (petites tranches)

1. Arbitrer les décisions de `REVUE_QA_DEVOPS.md` §7 (au minimum 1 à 5 et 11).
2. Produire les artefacts de la Definition of Ready (QA-21).
3. Initialiser le monorepo : squelette `backend/`, `frontend/`, `infra/`, `.gitattributes`, `.env.example`, compose, scripts Windows, crochets locaux — **sans fonctionnalité**, avec un test de santé et le harnais d'isolation vide mais exécutable.
4. Exécuter localement la chaîne complète (lint, test, migrations, e2e de santé) et rapporter les sorties réelles avant de créer les workflows CI.
5. Créer les workflows lorsque le dépôt hébergé est décidé ; activer d'abord les portes `lint`, `test-integration`, `migrations`, puis `contract`, `e2e-smoke`, `security-*`.

## 9. Traçabilité des tests de sécurité (ST-xx) vers les tranches

Statut : **proposition**, à confirmer après QA-19 ; « conditionnel » = dépend d'un arbitrage de périmètre.

| Tranche | Tests ST | Remarques |
|---|---|---|
| Transverse 1a | ST-01 à ST-09 | ST-02 dépend de QA-03/04/21 ; ST-08 dépend de QA-32 |
| 1a organisation / identité | ST-10 à ST-15, ST-20 à ST-27, ST-29, ST-29b, ST-60 à ST-69 | ST-60 dépend de QA-01 ; ST-23/24 de QA-07 ; ST-62 de QA-27 |
| 1a audit | ST-70, ST-71, ST-73, ST-74, ST-77 | ST-72 (chaînage) conditionnel ; ST-75 (export) conditionnel ; ST-76 conditionnel |
| 1a support plateforme | ST-28 | conditionnel : Q26 indique « non au Lot 1 » |
| 1b fleet | ST-30 à ST-34, ST-36 à ST-39 | ST-35 (export) conditionnel |
| 1b workforce | ST-40 à ST-43, ST-46 à ST-49 | ST-44 (export) et ST-45 (liaison de compte) conditionnels ; ST-47 dépend de QA-04 (`HSE`) |
| 1c assignment | ST-50 à ST-56, ST-58 | ST-52 dépend de QA-06 ; ST-57 (export) conditionnel |
| Configuration / chaîne | ST-80 à ST-85 | ST-86 (restauration) : exercice Ops hors pytest |
| Lots 4-5 | ST-90 à ST-98 | socle d'idempotence et d'horloge préparé dès 1a |

Fin du document.
