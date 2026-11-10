# Recette métier bout en bout — 10 scénarios

Référence : `docs/PRODUCT_VISION.md` (processus transversal, personas) et `docs/ROADMAP.md` (avancement vérifié).
Chaque scénario est un parcours **multi-modules** joué par des rôles distincts, vérifié automatiquement
dans `backend/tests/recette/` (exécuté par la CI sur PostgreSQL+PostGIS réel, base `minefleet_test`).
Les scénarios ne supposent aucune donnée préexistante : chaque test crée ses tenants fictifs (codes uniques).

## Exécution

```bash
# Local (docker requis, scripts/preview-up.sh) : MF_ENV=test, base *_test
pytest -q backend/tests/recette
# CI : collecté automatiquement par le job backend (testpaths: tests, tests_unit)
```

## Vue d'ensemble

| # | Scénario | Modules couverts | Acteurs principaux | Statut |
|---|---|---|---|---|
| R1 | Onboarding d'un tenant multi-sites et RBAC | identity, organization, authz | plateforme, admin tenant, 8 rôles métiers | ✅ implémenté |
| R2 | Référentiel flotte et habilitations | fleet, workforce, assignment | admin, RH | ✅ implémenté |
| R3 | Mission de transport et pesées pont bascule | dispatch (missions, pesées) | dispatcher, ops, chef atelier | ✅ implémenté |
| R4 | Parcours panne transversal (vision §Processus) | dispatch, maintenance, magasin, costs | conducteur, dispatcher, chef atelier, mécanicien, magasinier | ✅ implémenté |
| R5 | Maintenance préventive (échéances km/h) | maintenance | chef atelier, mécanicien | ✅ implémenté |
| R6 | Carburant bout en bout (cuve→pompe→rapprochement) | fuel | responsable carburant, pompiste | ✅ implémenté |
| R7 | GPS : ingestion, position courante, alertes | fleet/gps | plateforme technique, dispatcher | ✅ implémenté |
| R8 | Isolation tenant et sécurité négative (IDOR) | authz, audit, ratelimit | comptes de deux tenants | ✅ implémenté |
| R9 | Contrats, documents et assurance | legal | admin, finance | ✅ implémenté |
| R10 | Consolidation des coûts et rentabilité | costs | finance, ops | ✅ implémenté |

## Détail des scénarios

### R1 — Onboarding d'un tenant multi-sites et RBAC
- **Acteurs** : admin plateforme, admin tenant, OPS_MANAGER, HR, DISPATCHER (portée site), WORKSHOP_CHIEF,
  MECHANIC, STOREKEEPER, HSE, FINANCE, AUDITOR.
- **Parcours** : création du tenant par la plateforme → activation de l'admin (invitation par e-mail) →
  création des sites (S1 mine, S2) → invitation et activation des comptes de chaque rôle
  (portée TENANT, DISPATCHER portée SITE) → chaque compte consulte `/me`.
- **Critères d'acceptation** : tous les comptes sont actifs et authentifiés ; `/me` répond 200 pour chaque
  rôle ; un DISPATCHER ne peut pas créer un référentiel global (`POST /materials` → 403) ; les codes
  de tenant/sites sont uniques ; aucune donnée réelle (jeux fictifs uniquement).

### R2 — Référentiel flotte et habilitations
- **Acteurs** : admin (véhicules), RH (conducteurs), dispatcher (affectations).
- **Parcours** : catégories de véhicules → véhicules par site (numéro de flotte unique) → conducteurs
  avec permis (dates d'expiration) et habilitations par catégorie → affectation véhicule-conducteur
  planifiée → tentatives d'affectation non qualifiées.
- **Critères d'acceptation** : une affectation exige un permis valide et l'habilitation de la catégorie ;
  un permis expiré ou une habilitation manquante est refusé (`eligibility`) ; l'affectation ouverte bloque
  la prise de poste concurrente selon la politique `assignment_safety_policy`.

### R3 — Mission de transport et pesées pont bascule
- **Acteurs** : dispatcher (saisie pesée), OPS_MANAGER (saisie et approbation), admin (référentiels).
- **Parcours** : lieux (fosse → verse), matériau, affectation active → mission (2 rotations planifiées) →
  cycle `DEPARTED → ARRIVED_LOADING → LOADED → pesée → ARRIVED_UNLOADING → UNLOADED` ×2 → `COMPLETED`.
  Rotation 2 pesée en mode dégradé (`MANUAL_DEGRADED`, pont en panne) : mise en attente
  `PENDING_APPROVAL`, auto-approbation interdite (422), approbation par un second OPS_MANAGER.
- **Critères d'acceptation** : ticket `WEIGHBRIDGE` → `VALID`, `net_kg` cohérent ; saisie dégradée exige
  une double validation par une autre personne (décision tracée avec `decided_by`) ; la mission ne se
  clôture qu'après ses rotations ; le tonnage vient exclusivement du pont bascule (jamais du GPS).

### R4 — Parcours panne transversal (vision produit)
- **Acteurs** : dispatcher, chef d'atelier, mécanicien, magasinier, OPS_MANAGER.
- **Parcours** : mission en cours → panne signalée → mission `SUSPENDED` → réaffectation (`REASSIGNED`)
  sur véhicule de substitution → ordre de travail créé par le chef d'atelier → diagnostic mécanicien →
  réservation puis sortie de pièces par le magasinier → remise en service → consolidation des coûts
  (pièces + main-d'œuvre) et de l'immobilisation.
- **Critères d'acceptation** : la mission suspendue ne peut pas être clôturée sans réaffectation ;
  l'OT suit son cycle de statuts ; les pièces réservées ne sont pas vendables ailleurs ;
  les coûts apparaissent dans `/costs/vehicles/{id}` ; chaque transition est auditée.

### R5 — Maintenance préventive
- **Acteurs** : chef d'atelier, mécanicien, admin.
- **Parcours** : plan préventif kilométrique/horaire sur un véhicule → relevés de compteur
  (`meter-readings`) → évaluation des échéances (`preventive-dues/evaluate`) → OT planifié et exécuté →
  suspension/revision de plan le cas échéant.
- **Critères d'acceptation** : l'échéance se déclenche au seuil ; le même relevé rejoué (idempotence)
  ne double pas l'échéance ; les déclarations de réalisation passent par la double décision prévue.

### R6 — Carburant bout en bout
- **Acteurs** : responsable carburant, OPS_MANAGER (double validation), admin.
- **Parcours** : cuves et seuils → fournisseurs et achats (livraison partielle) → réceptions de stock →
  réservations → pompes et relevés → rapprochements → anomalies (écart, seuil) et acquittement →
  dashboard de consommation.
- **Critères d'acceptation** : le stock de cuve est cohérent (réceptions − sorties) ; une sortie non
  réserved est refusée ou tracée selon la règle ; les écarts déclenchent une alerte acquittable ;
  le dashboard sépare mesuré / estimé / en attente comme pour les pesées.

### R7 — GPS : ingestion, position courante et alertes
- **Acteurs** : traceur authentifié / téléphone (adaptateur simulé), dispatcher, admin.
- **Parcours** : ingestion de positions (avec cap et horodatage) → position courante `/vehicles/gps/latest`
  → perte de signal (batterie/réseau) → alertes (dépassement, hors ligne) et notifications → historique.
- **Critères d'acceptation** : rejet des coordonnées invalides et des horloges décalées au-delà de la
  tolérance ; la position courante reflète le dernier point valide ; la perte de signal génère l'alerte
  prévue ; aucune donnée GPS n'est présentée comme tonnage mesuré.

### R8 — Isolation tenant et sécurité négative (IDOR)
- **Acteurs** : deux tenants, comptes de rôle identique, AUDITOR.
- **Parcours** : tenant A et tenant B créés par la plateforme → chaque compte tente de lire/modifier les
  ressources de l'autre (véhicules, missions, pesées, documents) par identifiant direct → tentatives
  au-delà du quota d'authentification → consultation de l'audit.
- **Critères d'acceptation** : tout accès cross-tenant répond 403/404 sans fuite de contenu ; les échecs
  d'authentification sont limités (429) par compte et par source ; les événements d'audit portent le
  contexte (compte, tenant, action) ; aucun ID interne n'est devinable.

### R9 — Contrats, documents et assurance
- **Acteurs** : admin tenant, finance.
- **Parcours** : création d'un contrat → prévol des documents (preflight) → dépôt → vérification →
  soumission → décision → police d'assurance associée (échéances).
- **Critères d'acceptation** : un contrat incomplet ne peut pas être soumis ; la vérification des
  documents repère les fichiers non conformes ; la réconciliation du stockage légal est cohérente ;
  les échéances d'assurance remontent dans les expirations.

### R10 — Consolidation des coûts et rentabilité
- **Acteurs** : finance, OPS_MANAGER.
- **Parcours** : à partir des scénarios R3-R6 : pièces consommées, main-d'œuvre (taux horaires),
  carburant, immobilisation → historique de coûts par véhicule → indicateurs par période.
- **Critères d'acceptation** : les coûts sont réconciliés avec les mouvements d'origine (aucun coût
  sans pièce/heure/tarif sourcé) ; la devise est le GNF ; les périodes sont bornées en UTC avec
  affichage explicite ; les totaux dashboard = somme des lignes détaillées.

## Règles transverses (tous scénarios)

- Données exclusivement fictives ; pas d'information personnelle réelle.
- Tonnnage mesuré uniquement par pont bascule ou source agréée — le GPS n'est jamais une preuve de charge.
- Horodatage stocké en UTC, affichage avec fuseau explicite ; monnaie GNF.
- Chaque écriture passe par l'autorisation du rôle et laisse une trace d'audit ; les lectures et écritures
  sont cloisonnées par tenant et par site (RLS).
- Aucune fusion automatique par l'équipe IA : validation explicite du propriétaire requise.
