# Livraison — gestion des pneumatiques

Branche `feature/tyre-management`, migration Alembic `0053` (additive : tables `tyre` et `tyre_event`).
Roadmap P1 n° 8 : « pneus absents comme cycle métier » (`docs/MINING_BUSINESS_GAPS.md`).

## Périmètre

| Élément | Détail |
|---|---|
| Référentiel | pneu individuel : marque + n° de série (unique par société, insensible à la casse), modèle, dimension, catégorie (directeur, moteur, remorque, toutes positions), site de rattachement, lien facultatif vers un article du **catalogue de pièces** (pas de second référentiel), coût d'achat et devise, sculpture neuve et limite de rebut, pression nominale |
| Montage / démontage | engin du même site, position codée (`AV-G`, `AR-D-EXT`…), au moins un compteur de l'engin (km ou heures), OT lié facultatif (même engin), motif de démontage |
| Contrôles | profondeur de sculpture, pression, compteurs si monté, observation |
| Réparation / rechapage | envoi, retour réparé ou rechapé (nouvelle sculpture, compteur de rechapages), coût dans la devise du pneu |
| Rebut | depuis le stock ou la réparation, motif codé |
| Historique | `tyre_event` en ajout seul (trigger) + audit `maintenance.tyre.*` |
| Coûts | coût total = achat + réparations + rechapages ; coût au km et à l'heure sur les distances/heures **mesurées** pendant les montages |
| Alertes | sculpture à la limite, sculpture < limite + 3 mm, pression hors ±10 %, pneu monté non contrôlé depuis 30 jours |
| Interface | menu « Pneus » (liste filtrable, alertes), fiche pneu (actions selon rôle et état, coûts, historique), section « Pneus montés » sur la fiche engin |

## Règles et garde-fous

- Une position d'engin ne porte qu'un pneu : contrôle applicatif + **index unique partiel** (montages concurrents :
  un seul réussit, l'autre reçoit `409 TYRE_POSITION_OCCUPIED`).
- Concurrence par If-Match et verrou de ligne sur le pneu ; verrou de l'engin pendant le montage.
- Un relevé pendant un montage ne peut pas être inférieur au relevé de montage (`TYRE_METER_DECREASED`).
- Pas d'agrégat multidevise : un coût de réparation dans une autre devise que l'achat est refusé ; sans coût d'achat,
  le coût total est « Données insuffisantes ».
- Aucune extrapolation : sans relevé d'heures, pas de coût horaire ; un montage sans relevé ultérieur ne compte pas.

## Autorisations

| Permission | Rôles | Usage |
|---|---|---|
| `maintenance.tyre.read` | DIRECTION (T), OPS_MANAGER, WORKSHOP_CHIEF, MECHANIC, STOREKEEPER, FINANCE, AUDITOR (T) | liste, fiche |
| `maintenance.tyre.manage` | WORKSHOP_CHIEF, STOREKEEPER | enregistrement, réparation/rechapage, rebut |
| `maintenance.tyre.fit` | WORKSHOP_CHIEF, MECHANIC | montage, démontage, contrôle |

**Élargissements à valider en revue sécurité** (lacune révélée par l'E2E : un chef d'atelier de portée société ne
pouvait ni lister les engins ni les sites, donc ni monter un pneu ni choisir son site) :
- `fleet.vehicle.read` (et, par l'ancre YAML partagée, `fleet.meter.read` et `fleet.document.read`) :
  WORKSHOP_CHIEF et MECHANIC passent de `[SITE]` à `[TENANT, SITE]` ;
- `organization.site.read` : WORKSHOP_CHIEF, MECHANIC et STOREKEEPER passent de `[SITE]` à `[TENANT, SITE]`.
Ces rôles de portée société lisaient déjà tous les OT de la société. FUEL_MANAGER de portée société présente la même
lacune sur les sites ; non modifié ici.

## Vérifications

- `tests/test_tyres.py` : cycle complet avec coût/km, rechapage, refus de devise, historique, conflit de version ;
  règles (doublon de série, position occupée, engin d'un autre site, OT étranger, position mal formée) ; **montages
  concurrents** sur une position ; portée site et isolation inter-tenant ; permissions ; alertes et filtre ; ajout seul ;
  calculs purs d'usage et d'alertes.
- Tests d'autorisation générés (403 par rôle, lectures autorisées, isolation) étendus aux routes `/tyres`.
- Vitest `TyresPages.test.tsx` ; Playwright `e2e/pneus.spec.ts` (création, montage, contrôle, fiche engin,
  démontage) ajouté au workflow `e2e-isolation`.

## Limites

- **Décision déléguée D-DEL-03 (2 novembre 2026)** : le **registre individuel des pneus fait foi pour leur stock**.
  Aucun mouvement automatique dans le magasin de pièces (pas de double comptage ni de valorisation divergente :
  le coût d'un pneu est porté par le pneu lui-même). L'article du catalogue sert de référence d'achat ; il doit être
  compté à l'unité (`EACH`). Synthèse `GET /tyres/stock` (en stock / montés / en réparation, par site, dimension,
  modèle et article ; pneus au rebut exclus) affichée dans l'écran « Pneus ». Ne pas réceptionner en parallèle les
  mêmes pneus dans le magasin de pièces.
- Pas de plan de positions par catégorie d'engin (positions saisies librement selon un format contrôlé).
- Les coûts pneus ne sont pas encore agrégés dans l'écran « Fiabilité parc » : prévu dans le chantier D (coût complet).
