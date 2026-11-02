# Livraison — GPS avancé : zones, trajets, alertes de zone, immobilisations, rétention

Branche `feature/gps-geofencing` (empilée sur `feature/vehicle-total-cost`), migration `0056`.
Roadmap P1 n° 11 « GPS industrialisé ».

## Périmètre

| Élément | Détail |
|---|---|
| Zones (géofences) | polygone PostGIS (`geography`, WGS 84) par site : limite de site, chargement, déchargement, atelier, station carburant, zone interdite ; validité géométrique et surface vraisemblable (100 m² à 2 000 km²) contrôlées **en base** ; désactivation, jamais de suppression |
| Historique de trajet | `GET /vehicles/{id}/gps/track` : fenêtre de 24 h maximum, 5 000 points maximum (signalé si tronqué), distance mesurée, interruptions de réception (> 10 min), immobilisations (≥ 15 min dans un rayon de 50 m), points tardifs (reçus > 5 min après l'enregistrement), points écartés, statut du signal (récent ≤ 2 min, ancien ≤ 30 min, perdu) |
| Entrées / sorties de zones | calculées sur l'historique (PostGIS `ST_Covers`) pour un engin ou pour tout un site (`GET /gps/geofence-events`) ; recalcul à partir des positions ordonnées par heure d'enregistrement : **un message en retard est replacé à sa place**, sans fausse alerte |
| Qualité des données | positions imprécises (> 100 m) et sauts physiquement impossibles (> 150 km/h) exclus de la distance et des transitions ; aucune interpolation : un trou reste un trou |
| Rétention | `minefleet purge-gps [--days N] [--apply]` (simulation par défaut ; `MF_GPS_RETENTION_DAYS`, 180 j par défaut, 7 j minimum imposés en base) ; seule voie de suppression des positions, par la fonction `app.purge_gps_positions` réservée au propriétaire du schéma |
| Interface | menu « Zones GPS » (liste, création par sommets « latitude, longitude », désactivation) ; panneau « Historique de trajet » sur la fiche engin (finalité, synthèse, tracé schématique sans fond de carte tiers) |

## Protection des données de localisation

- `fleet.gps.history` : OPS_MANAGER, HSE, AUDITOR (T). **Pas de dispatcher** (temps réel uniquement) ni de direction.
- **Finalité obligatoire** à chaque consultation (enquête incident, analyse d'exploitation, diagnostic, sûreté, litige
  client) ; chaque lecture écrit un événement d'audit (`fleet.gps.track.read`, `fleet.gps.geofence_events.read`)
  avec la finalité et la période.
- Les positions restent en ajout seul pour l'application : le rôle applicatif ne peut ni modifier, ni supprimer, ni
  appeler la fonction de purge (testé).
- La durée de conservation (180 j par défaut) est une **proposition** à valider avec un juriste local.
- Le partage de position par navigateur n'est pas un suivi continu en arrière-plan : les interruptions sont
  montrées telles quelles.

## Autorisations

| Permission | Rôles |
|---|---|
| `fleet.geofence.read` | TENANT_ADMIN (T), DIRECTION (T), OPS_MANAGER, DISPATCHER (S), HSE, AUDITOR (T) |
| `fleet.geofence.manage` | TENANT_ADMIN (T), OPS_MANAGER, HSE |
| `fleet.gps.history` | OPS_MANAGER, HSE, AUDITOR (T) |

## Vérifications

- `tests/test_gps_advanced.py` : validation des zones (doublon, polygone croisé, surface minuscule, coordonnées hors
  limites, droits, isolation) ; trajet synthétique avec entrée/sortie, arrêt de 20 min, trou de 42 min, point
  imprécis et saut écartés, message tardif, audit avec finalité, flux par site, désactivation de zone ; règles
  d'accès (dispatcher refusé, finalité manquante ou inconnue, fenêtre > 24 h, portée site, autre tenant) ; charge
  bornée à 5 000 points (troncature signalée, temps mesuré) ; purge réservée au propriétaire, borne de 7 jours,
  simulation puis suppression, ajout seul maintenu pour l'application.
- Tests d'autorisation générés (les routes à paramètres obligatoires reçoivent `purpose`/`site_id`).
- Vitest `GpsHistory.test.tsx`.

## Limites

- **Intégration d'un fournisseur de traceurs** non réalisée : elle exige la spécification réelle du fournisseur
  (format, authentification, horodatage). Le point d'entrée authentifié existant (`/gps/telemetry`) et le contrat de
  passerelle restent la frontière (`docs/GPS_INGESTION_BOUNDARY.md`).
- Alertes calculées à la demande (pas de notification poussée ni d'historisation des événements de zone).
- Pas de fond de carte pour le tracé (le fond OSM intégré ne permet pas de tracer une ligne) ; tracé schématique.
- La purge lève brièvement la RLS forcée de la table (verrou exclusif) : à planifier hors des heures de pointe.
- Les mesures de charge locales ne remplacent pas un test sur volume réel en recette.
