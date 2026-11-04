# Alertes GPS

État au 4 novembre 2026 : troisième tranche du chantier P0 GPS (`docs/ROADMAP_2026_2027.md`, `docs/GPS_LIVE_MAP.md`).

## Règles (choix par défaut, réglables)

| Alerte | Déclenchement | Fin |
|---|---|---|
| Excès de vitesse (`OVERSPEED`) | vitesse **mesurée** strictement supérieure à la limite du site | première mesure revenue au plus à la limite (ou limite retirée) ; la vitesse maximale atteinte est retenue |
| Entrée en zone interdite (`RESTRICTED_ZONE_ENTRY`) | la mesure est dans une zone active de type « Zone interdite » et la mesure précédente n'y était pas | ponctuelle |
| Sortie de la limite du site (`SITE_BOUNDARY_EXIT`) | la mesure précédente était dans la zone « Limite de site », la nouvelle n'y est plus | ponctuelle |
| Perte de signal (`SIGNAL_LOST`, migration 0062) | balayage planifié toutes les 5 min : engin **disponible**, équipé d'un **traceur actif**, sans position mesurée depuis plus que le délai du site | première position reçue ensuite, même tardive (fin au plus tôt à l'instant de détection) |

- **Sans délai de perte de signal** (réglage par défaut) : pas de surveillance. Délai de 5 à 1 440 min. Les engins
  en maintenance, immobilisés ou hors service (qui peuvent être éteints) et ceux qui n'ont jamais émis ne sont pas
  surveillés. Commande `minefleet sweep-gps-signal` (acteur `SYSTEM`, une alerte ouverte au plus par engin), timer
  `minefleet-gps-signal-sweep` ; la sonde `probe-scheduled-jobs.sh` alerte si le balayage n'a pas tourné depuis
  1 h (`minefleet-gps-signal-sweep:1`).
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

1. **Fournisseur SMS** à choisir par le client (service payant) ; push mobile.
2. Limites de vitesse par zone, plages horaires autorisées, utilisation hors horaires.
3. Marqueur d'alerte sur la carte en direct.

## Perte de signal : vérifications

- Tests API (`test_gps_signal_loss.py`) avec la vraie commande :
  - pas de surveillance sans délai ;
  - seul l'engin disponible, à traceur actif et silencieux est signalé ; pas l'engin récent, ni celui en maintenance, ni celui sans traceur ;
  - rejeu sans doublon ;
  - dernière mesure conservée ;
  - fermeture à la position suivante ;
  - audit `SYSTEM` ;
  - bornes 5 à 1 440, et refus d'une chaîne.
- Sonde : délai propre à une tâche (`unité:heures`), 6 tests avec un faux `systemctl`.
- Démonstration (jeu `large`, émetteur arrêté, délai de 10 min sur demo-bauxite) :
  - **47 alertes en 1,7 s**, exactement les 47 engins disponibles à traceur actif (l'engin immobilisé est exclu), rien pour les autres sociétés ;
  - rejeu : 0 ;
  - émetteur relancé 1 min : les 47 alertes se ferment ;
  - réglage remis à vide ensuite.

## Notifications e-mail et SMS (migration 0063)

Décision du client (4 novembre 2026) : **les deux canaux, au choix de chaque utilisateur.**

| Élément | Détail |
|---|---|
| Choix personnel | page Alertes GPS, section « Mes notifications » : e-mail, SMS, les deux, ou aucun (**défaut : aucun**). Le numéro de mobile (format international E.164, ex. `+224…`) est saisi par l'utilisateur lui-même ; il n'est jamais copié dans l'audit. Routes `GET` / `PUT /me/alert-notifications` (permission `fleet.gps_alert.read`) |
| Destinataires | comptes actifs dont un rôle en vigueur donne la lecture des alertes sur le site de l'alerte (ou toute la société), et qui ont choisi au moins un canal |
| Mise en file | à la création de l'alerte (vitesse, zones, perte de signal), **dans la même transaction** (`notification_outbox`), jamais d'envoi pendant l'ingestion GPS |
| Anti-avalanche | (1) au plus une notification par destinataire, canal, engin et type d'alerte toutes les **30 minutes** ; (2) à la livraison, **un seul message par destinataire et par canal** regroupe tout ce qui est en attente : l'e-mail détaille jusqu'à 20 alertes, le SMS résume par type en moins de 160 caractères (« 33 alertes GPS (33 excès de vitesse). lien ») |
| Livraison | `minefleet deliver-notifications` chaque minute (timer `minefleet-notify-deliver`, exécuté dans le conteneur API déjà démarré), acteur `SYSTEM`, audit `fleet.gps.alert.notify` (canal, type, résultat ; ni adresse, ni numéro, ni contenu) |
| Contenu | type, engin, site, heure du site, vitesse maximale et limite le cas échéant, lien vers la page Alertes GPS ; **aucune coordonnée** |
| Échecs | erreur de transport : nouvel essai (5 au plus) ; SMS sans fournisseur : `FAILED` / `SMS_PROVIDER_NOT_CONFIGURED`, et l'écran prévient l'utilisateur |
| SMS | **aucun fournisseur payant branché** : `MF_SMS_BACKEND=capture` en développement et en recette (fichiers privés, comme les e-mails), `disabled` en production tant que le client n'a pas choisi. Un fournisseur s'ajoute comme une implémentation de `SmsSender` |
| Supervision | `minefleet-notify-deliver:1` dans `MF_SCHEDULED_UNITS` |

### Vérifié sur la démonstration

Jeu `large`, limite de 15 km/h sur demo-bauxite, un responsable d'exploitation abonné par e-mail et par SMS
(numéro fictif), émetteur pendant 1 min : **33 alertes** produisent 33 notifications en file par canal. La vraie
commande `minefleet deliver-notifications` (capture locale) envoie **1 e-mail et 1 SMS** en 2,6 s ; un deuxième
passage n'envoie rien. Le premier essai, avant regroupement, aurait envoyé 33 SMS et produit un texte de 724
caractères : c'est ce qui a motivé le regroupement et le résumé SMS. Réglages et préférences remis à vide ensuite.
