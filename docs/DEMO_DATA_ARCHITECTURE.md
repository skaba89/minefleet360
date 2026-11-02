# Architecture des données de démonstration (DEMO)

État au 2 novembre 2026 — lots 1 (socle), 2 (coûts valorisés, atelier, pneus, inspections) et 3 (GPS, zones) :
profils `small` (démonstration) et `qa` (tests automatisés). Les profils `standard` et `large` sont déclarés mais
leur volume et leurs performances n'ont pas encore été mesurés (lot suivant).

## 1. Objectif et principes

Permettre d'ouvrir MineFleet 360 sur une base peuplée de données **réellement insérées** et servies par les API
et les écrans existants, sans aucun chiffre codé en dur dans l'interface.

| Exigence | Mise en œuvre |
|---|---|
| Passer par les règles métier | Chaque objet est créé par le **service applicatif** (`app.*.service`), sous l'identité du compte DEMO qui porte la permission dans `authz_matrix.yaml`. Aucun `INSERT` direct, RLS jamais désactivée, rôle `mf_app`. |
| Historique crédible | Horloge simulée (`FrozenClock`) avancée événement par événement : les bornes d'antidatage (RM-083), l'éligibilité des affectations, les échéances et les quatre yeux s'appliquent comme en exploitation. |
| Déterminisme | `--seed` + `--anchor` ⇒ mêmes engins, conducteurs, missions, pesées, carburant, chronologie. Une graine dérivée par société : ajouter une société ne change pas les autres. Les identifiants techniques (UUID) et les **mots de passe** ne sont pas déterministes (aléa cryptographique). |
| Idempotence | À la maille de la société : une société DEMO déjà présente est ignorée, aucune écriture. |
| Données fictives reconnaissables | Raisons sociales « DEMO — … », sites « (DEMO) », e-mails `@demo-*.example.com`, téléphones `+224000…`, numéros de parc et permis `DEMO-…`, noms `Démo-…`. Aucune coordonnée GPS générée dans ce lot. |

## 2. Commandes

```
minefleet demo seed --profile small --seed 42 [--anchor 2026-10-01] --credentials-out /chemin/comptes-demo.tsv
minefleet demo verify [--anchor 2026-10-01]
minefleet demo reset-credentials --tenant demo-bauxite --credentials-out /chemin/nouveaux-comptes.tsv
```

- `seed` : charge les sociétés absentes ; écrit les identifiants dans un **nouveau** fichier créé en mode 600
  (refus si le fichier existe) ; n'affiche jamais un mot de passe dans le terminal.
- `verify` : contrôles recalculés depuis les données sources (§5). Code de sortie 1 au premier écart.
- `reset-credentials` : régénère les mots de passe d'une société DEMO (sessions fermées, action auditée
  `user.password_reset`). Utile quand le fichier d'identifiants a été supprimé après transmission.

En conteneur : `docker compose … run --rm api minefleet demo seed …` avec un volume monté pour le fichier.

## 3. Garde-fous (impossibilité technique hors base DEMO)

`app/demo/guards.py`, appelé par `seed` et `reset-credentials` :

1. refus si `MF_ENV=production` ;
2. refus si la base contient **un seul** tenant client non marqué `is_demo` (vrai client, recette partagée) —
   indépendamment de la configuration.

`reset-credentials` n'accepte en outre qu'un code du catalogue DEMO et vérifie `is_demo` en base.

### Réinitialisation complète des données

Le rôle applicatif `mf_app` n'a **pas** le droit `DELETE` sur les tables métier (choix de sécurité du socle) ;
aucune commande ne contourne cette règle. La remise à zéro d'une démo se fait donc en **recréant la base de
l'instance de démonstration** (migrations puis `demo seed`), jamais par suppression ligne à ligne. Une commande
`demo reset --tenant … --confirm` exécutée avec le propriétaire du schéma reste possible mais n'est pas livrée :
elle demande une décision explicite (droit destructif, journalisation, double confirmation).

## 4. Contenu du profil `small` (graine 42)

| Élément | Volume | Détail |
|---|---:|---|
| Sociétés | 3 | DEMO — Bauxite Guinée Operations (Boké, Boffa) ; DEMO — Mines Aurifères de Haute-Guinée (Siguiri) ; DEMO — Transport & Logistique Minière (Kamsar, Conakry) |
| Sites | 5 | mine, terminal portuaire, dépôt, atelier |
| Comptes | 47 | les 13 rôles client de la matrice ; rôles de site (DISPATCHER, DRIVER, MECHANIC, FUEL_MANAGER) un par site |
| Engins | 28 | tombereaux, articulés, porteurs routiers, chargeuses, pelles, niveleuse, bouteur, citerne, arroseuse, bus, VL |
| Conducteurs | 21 | permis et autorisations de conduite ; 2 cas négatifs par société (permis expiré, permis proche échéance) |
| Affectations | 15 | une par engin de transport, poste `JOUR` |
| Profil `qa` | 9 jours | mêmes scénarios, rotations 2 à 3, GPS toutes les 5 min — tests automatisés |
| Missions / rotations / pesées | ≈205 / ≈560 / ≈560 | 14 jours, 2 à 4 rotations par mission, pesées pont-bascule |
| Activité du jour J | 6 en cours, 3 planifiées | missions en chargement, route chargée, déchargement, démarrées 2 h 30 avant l'exécution (ou 08:00 pour un ancrage passé) — seule partie qui dépend de l'heure d'exécution |
| Carburant | 5 cuves, 10 achats, ≈100 distributions | bons de commande chiffrés en GNF (responsable carburant) approuvés par la finance puis livrés, bornés par la capacité ; distributions demandées par le responsable carburant, approuvées par le responsable des opérations (quatre yeux) |
| Compteurs | ≈420 relevés | km et heures moteur en fin de poste, progression plausible (RM-103) |
| Atelier | 6 OT, taux horaire | une panne clôturée (approbation, assignation, pièces réservées puis consommées, 3 h de main-d'œuvre, contrôle qualité) et une panne ouverte par société ; taux société 85 000 GNF/h |
| Pièces | 6 références, 1 magasin par site | réceptions valorisées (GNF) ; sorties valorisées au CMP sur l'OT |
| Pneus | ≈95 pneus, ≈180 inspections | 6 pneus par engin de transport, 2 tournées d'inspection (usure, pression, compteurs) ; un pneu usé déposé, réformé et remplacé par un pneu neuf |
| Préventif | 15 plans | un plan « ENTRETIEN-A » par engin de transport (250 h ou 10 000 km, et 90 jours) ; **aucune échéance** (voir §10) |
| GPS | 15 traceurs, 25 zones, ≈22 000 positions | une position toutes les 2 min calée sur les événements de chaque rotation (parc → chargement → déchargement → retour) ; compteur km = distance du tracé |
| HSE | 6 incidents, 65 inspections | un presque-accident enquêté, action corrective réalisée puis vérifiée, incident clos ; un incident critique ouvert ; checklist « avant poste » quotidienne, dont une non conforme (freins, point critique) |

Volumes indicatifs : ils dépendent de la graine et de la date d'ancrage ; la sortie de `seed` donne les valeurs exactes.
Contrôle de déterminisme effectué : deux bases vierges chargées avec la graine 42 et le même ancrage donnent les mêmes
volumes historiques (558 rotations, 555 pesées, 97 distributions de carburant).

## 5. Contrôles de `demo verify`

Pour chaque société, sous le contexte RLS de la société :

- société présente et marquée `is_demo` ;
- isolation : aucun engin ni pesée d'une autre société visible ;
- chaque rotation terminée porte une pesée non annulée ;
- tonnage mesuré des 7 derniers jours : somme directe des pesées = indicateur servi par `dispatch.weighing.indicators` ;
- solde de chaque cuve = réceptions − distributions approuvées, compris entre 0 et la capacité ;
- OT bloquant ouvert ⇔ engin immobilisé ; OT clôturé ⇒ engin remis en service ;
- coût complet servi par `costs.vehicle_costs` : carburant des engins de transport valorisé (statut « Estimé ») ;
  main-d'œuvre = minutes saisies × taux horaire (recalcul indépendant) ; pièces consommées valorisées ;
- pneus : une seule position par pneu monté, aucun pneu réformé resté sur un engin ;
- GPS : sur une journée complète, le trajet servi par l'application (`vehicle_track`) compte autant d'entrées en
  aire de chargement que de rotations terminées de l'engin (lecture journalisée dans l'audit, finalité
  « Analyse d'exploitation »).

Les sorties de magasin sont horodatées par la base à l'exécution réelle (non simulable) : avec un ancrage passé,
elles apparaissent à la date d'exécution. Le contrôle des coûts couvre donc de « ancrage − 30 j » à aujourd'hui.

## 6. Instance de démonstration

Une instance dédiée (base, secrets, stockage, URL séparés de la production) est **requise** : les garde-fous
refusent une base qui contient de vrais clients. Elle n'est **pas** provisionnée par ce lot (décision humaine :
coût, domaine, sauvegardes). Points à arbitrer :

- `MF_ENV=staging` ; base et secrets propres ; URL distincte ;
- double authentification : DIRECTION, OPS_MANAGER, TENANT_ADMIN, HR, FINANCE doivent l'enrôler à la première
  connexion (`MF_MFA_ENFORCEMENT=enroll`). Pour une démonstration commerciale, `off` sur l'instance DEMO
  uniquement est envisageable — à décider, jamais en production ;
- le fichier d'identifiants est à transmettre par canal sûr puis supprimer.

## 7. Hypothèses de valorisation (fictives)

| Élément | Valeur de démonstration | Remarque |
|---|---|---|
| Gazole | 12 400 à 13 200 GNF/L selon la livraison | prix tiré par bon de commande |
| Main-d'œuvre | 85 000 GNF/h (taux société) | saisi par la finance |
| Pièces | 290 000 à 1 980 000 GNF l'unité | 6 références |
| Pneus neufs | 5,2 M (315/80R22.5) à 168 M GNF (24.00R35) | seuls les pneus achetés pendant la période sont valorisés |

Ordres de grandeur plausibles, **à remplacer par les valeurs d'un client** ; aucun n'est présenté comme un prix
de marché. Les pneus montés au départ sont une reprise d'inventaire sans prix d'achat connu : leur composante
reste « Données insuffisantes » plutôt qu'un coût inventé.

### Constat sur la méthode d'estimation des pneus (décision produit à prendre)

Le coût pneu d'une période vaut km de la période × (prix d'achat ÷ km mesurés depuis le premier événement du
pneu). Un pneu neuf monté pendant la période voit donc **tout son prix imputé** sur les premiers kilomètres :
sur la démo, DEMO-CAM-001 porte 168 M GNF de pneu pour 664 km (≈ 290 000 GNF/km contre ≈ 40 000 pour les autres
camions). Les données sont exactes ; c'est la méthode qui surpondère le début de vie. Piste : amortir à l'usure
de bande (prix × usure mesurée ÷ usure utile), ou sur une durée de vie attendue paramétrée. Non modifié ici.

## 8. GPS : choix et limites

- **Coordonnées fictives** : centres de sites placés dans la région annoncée (Boké, Boffa, Siguiri, Kamsar,
  Conakry) mais décalés de plusieurs kilomètres ; ils ne représentent aucune installation réelle.
- **Chaîne d'ingestion** : « passerelle authentifiée » (GPS-23, `accept_gps_telemetry_payload`) — JSON strict,
  secret du traceur, association, anti-rejeu par séquence, bornes temporelles. Le limiteur anti-saturation de
  l'API traceur (60 points par minute réelle et par traceur) est propre aux appareils isolés : il n'est ni
  désactivé ni contourné, mais il rendrait impossible le rejeu d'un historique.
- **Flux en direct pendant une présentation** : `minefleet demo live-feed [--api-url http://127.0.0.1:8000]
  [--interval 15] [--duration 60]`. Refusé hors base DEMO et vers une API non locale. Renouvelle le traceur de
  chaque engin de transport DEMO disponible (révocation + provisionnement audités : les secrets ne sont jamais
  stockés), puis envoie une position par engin et par intervalle par la **vraie API traceur**
  (`POST /api/v1/gps/telemetry`), comme un boîtier. Il ne produit **que des positions** (aller-retour aire de
  chargement ↔ aire de déchargement) : aucune mission, pesée ni événement n'est inventé. Un engin immobilisé
  n'émet pas. Vérifié : 204 positions envoyées en 3 minutes, toutes acceptées ; flotte GPS « En mouvement ».
- **Bandeau** : `/me` expose `is_demo` ; l'interface affiche en permanence « Espace de démonstration : sociétés,
  personnes et opérations fictives ; les positions GPS peuvent être simulées », et la flotte GPS ne prétend plus
  qu'« aucune simulation n'est affichée » sur un espace DEMO. Les sociétés du jeu `seed-fictif`, marquées
  `is_demo`, affichent aussi ce bandeau.
- **Durée** : le profil `small` prend environ 8 minutes (≈22 000 positions) ; le profil `qa` (9 jours, une
  position toutes les 5 minutes) environ 3 minutes, utilisé par les tests automatisés.

## 9. Parcours navigateur automatisés

`frontend/e2e-demo/` + `playwright.demo.config.ts` : un parcours par rôle sur le profil `qa` (lecture seule),
exécuté en CI par le job `demo-journeys` (base éphémère, `demo seed` puis `demo verify`, identifiants dans un
fichier 600 supprimé en fin de job). En local, sur une pile locale uniquement :

```
MF_API_URL=http://localhost:8000 MF_DEMO_ACCOUNTS=/chemin/comptes-demo.tsv \
  npx playwright test --config=playwright.demo.config.ts
```

L'API doit tourner avec `MF_COOKIE_SECURE=false` (HTTP local) et `MF_MFA_ENFORCEMENT=off` (comptes sans
téléphone), comme les autres E2E du projet ; jamais contre une instance partagée.

## 10. Constat : moteur d'échéances préventives non branché

Le produit sait créer, réviser et suspendre des plans, et planifier puis finaliser une échéance existante
(`/preventive-dues/{id}/schedule`, `/work-orders/{id}/complete-preventive`). Mais **aucune route, commande ni
tâche n'enregistre d'échéance** : `persist_due` n'est appelé que par les tests, conformément à
`docs/PREVENTIVE_OT_TRANSACTION.md` (« ne pas activer d'automatisation » avant transaction atomique échéance + OT,
tests de concurrence et compte technique). L'écran d'un engin affiche donc toujours « Aucune échéance
préventive », quels que soient les compteurs.

La démo **ne fabrique pas** d'échéances en appelant directement ce service : elle montrerait une fonctionnalité
que l'application ne produit pas seule. Brancher le moteur (déclenchement à la demande par le chef d'atelier ou
tâche planifiée, transaction atomique, compte technique) est une évolution produit à décider.

## 11. Hors périmètre (prochains lots)

Contrats et documents, parcours hors ligne, échéances préventives (§10), bons de
commande de pièces, profils `standard`/`large` mesurés, mode « démonstration commerciale » guidé, parcours navigateur en écriture (actions) sur les données DEMO.
