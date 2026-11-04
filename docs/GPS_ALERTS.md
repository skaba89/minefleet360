# Alertes GPS

État au 4 novembre 2026 : troisième tranche du chantier P0 GPS (`docs/ROADMAP_2026_2027.md`, `docs/GPS_LIVE_MAP.md`).

## Règles (choix par défaut, réglables)

| Alerte | Déclenchement | Fin |
|---|---|---|
| Excès de vitesse (`OVERSPEED`) | vitesse **mesurée** strictement supérieure à la limite du site | première mesure revenue au plus à la limite (ou limite retirée) ; la vitesse maximale atteinte est retenue |
| Entrée en zone interdite (`RESTRICTED_ZONE_ENTRY`) | la mesure est dans une zone active de type « Zone interdite » et la mesure précédente n'y était pas | ponctuelle |
| Sortie de la limite du site (`SITE_BOUNDARY_EXIT`) | la mesure précédente était dans la zone « Limite de site », la nouvelle n'y est plus | ponctuelle |

- **Sans limite de vitesse** pour un site (réglage par défaut) : aucune alerte de vitesse. Le responsable
  d'exploitation la fixe sur la page « Alertes GPS » (1 à 250 km/h, au dixième).
- Seule la **mesure la plus récente** d'un engin fait évoluer ses alertes : une position reçue en retard est gardée
  dans l'historique, mais n'ouvre ni ne ferme rien (pas d'alerte qui clignote quand un traceur vide sa mémoire).
- Une mesure **sans vitesse** ne change rien à l'alerte de vitesse : rien n'est supposé.
- Pas d'alerte de zone sur le premier point d'un engin : son état précédent est inconnu.
- Les alertes sont calculées **à l'ingestion**, dans la même transaction que la position, pour les traceurs comme
  pour les téléphones. Aucune route d'API ne crée d'alerte.

## Données et accès

| Élément | Détail |
|---|---|
| Migration 0061 | `site_gps_policy` (limite par site), `gps_alert` (une alerte de vitesse ouverte au plus par engin : index unique partiel). RLS forcée, clés étrangères avec `tenant_id` |
| `fleet.gps_alert.read` | `GET /gps/alerts` (site, type, non prises en compte, paginé) et `GET /sites/{id}/gps-policy` : DIRECTION, OPS_MANAGER, DISPATCHER (site), HSE, AUDITOR |
| `fleet.gps_alert.manage` | `POST /gps/alerts/{id}/acknowledge` (remarque facultative, une seule fois) : OPS_MANAGER, DISPATCHER (site), HSE |
| `fleet.gps_policy.manage` | `PUT /sites/{id}/gps-policy` : TENANT_ADMIN, OPS_MANAGER |
| Audit | `fleet.gps.alert.acknowledge` (avec la remarque), `fleet.gps.policy.update` (avant / après) |
| Vie privée | les alertes de vitesse décrivent un comportement de conduite : permissions dédiées, portée site, aucune notification externe dans cette tranche |

## Interface

- Page **Alertes GPS** (menu, sous « Zones GPS ») : alertes non prises en compte par défaut, engin, type, détail
  mesuré (« 21.6 km/h au maximum pour 15.0 km/h autorisés », nom de la zone), début, fin ou « En cours »,
  prise en compte avec remarque. La vitesse limite du site s'affiche quand un site est sélectionné.
- Panneau **À traiter** : « N alerte(s) GPS à prendre en compte ».
- Menu : un lien parent n'est plus surligné quand une de ses sous-pages a son propre lien (Flotte GPS / Alertes
  GPS, Atelier / Fiabilité parc).

## Vérifications

- Tests API (`test_gps_alerts.py`) :
  - ouverture, vitesse maximale et fermeture d'une alerte ;
  - position tardive sans effet ;
  - mesure sans vitesse ;
  - limite retirée ;
  - entrée en zone interdite et sortie de site ;
  - prise en compte unique et auditée ;
  - refus 403, 404 (autre site, autre société) et 422 (bornes) ;
  - téléphone.
- Matrice d'autorisations : les 3 nouvelles permissions sont exercées automatiquement (refus, isolation).
- Démonstration (jeu `large`, émetteur simulé, limite de 15 km/h sur les deux sites de demo-bauxite) :
  - 1 287 positions acceptées, 0 refusée ;
  - **33 alertes de vitesse** (31 en cours, 2 closes, pointe à 21,6 km/h), uniquement pour la société réglée ;
  - avec une limite de 30 km/h, aucune alerte : le simulateur ne dépasse pas 21,6 km/h ;
  - en navigateur : 33 lignes, une prise en compte avec remarque la retire de la liste, panneau « À traiter » à jour.

## Pas encore fait

1. **Perte de signal** : demande une tâche planifiée (comme la tâche quotidienne du préventif) ; prochaine tranche.
2. **Notifications** par e-mail, SMS ou push : à brancher sur le fournisseur choisi par le client (D-41).
3. Limites de vitesse par zone, plages horaires autorisées, utilisation hors horaires.
4. Marqueur d'alerte sur la carte en direct.
