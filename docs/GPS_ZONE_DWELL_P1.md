# Lot GPS P1 — immobilisation prolongée dans une géofence

## Portée de cette PR

Premier incrément sans changement de schéma, de route HTTP, de notification ou du moteur
d'ingestion : fonction pure `gps_zone_dwell.py` et tests. **Aucune alerte d'immobilisation
n'est encore produite en production.**

## Contrat préalable indispensable à toute activation

1. Charger exclusivement des mesures GPS acceptées d'un même véhicule et d'un même tenant,
   triées par `recorded_at`, contrôlées sous RLS.
2. Vérifier avec PostGIS que chaque mesure considérée appartient à la même géofence active
   et à son site. Un changement de zone réinitialise le segment, même si le véhicule
   reste immobile.
3. Distinguer la dernière période d'immobilisation sans extrapoler au-delà de la dernière
   mesure. Une période sans GPS ou une vitesse absente n'est **pas** une immobilisation
   prouvée.
4. Un déplacement, un écart GPS supérieur au rayon, une interruption entre positions ou
   une mesure hors ordre remet le calcul à zéro.
5. Les zones de chargement et de déchargement peuvent représenter des arrêts métier
   normaux : aucun seuil d'alerte par défaut, politique explicite par zone obligatoire.
6. Réutiliser l'outbox existante et l'anti-avalanche, uniquement après une migration
   additive et les tests nécessaires ; ne jamais envoyer depuis l'ingestion elle-même.

## Étapes à réaliser dans une PR distincte

- Paramétrer la durée par géofence et préserver son historique et son audit.
- Ajouter une migration additive pour `ZONE_DWELL` avec index d'unicité sur l'alerte
  active par véhicule et géofence, sans collision avec les autres types.
- Construire le moteur de détection transactionnel avec garde anti-doublons.
- Clore les alertes à la sortie ou reprise du mouvement ; définir le comportement
  exact sur perte de signal et zones désactivées.
- Ajouter à l'API et au frontend le type d'alerte, les informations de zone et la durée
  prouvée ; synchroniser les schémas générés.
- Ajouter les scénarios tests API/PostGIS : zones chevauchantes, premier point, timestamps
  identiques, positions tardives, arrêts intermittents, hors-ligne, données incertaines,
  permissions par site et isolation inter-tenant.
- Mesurer la latence, les faux positifs et la livraison effective des notifications sur
  des trajets terrain avant activation.

## Sécurité de déploiement

Pas de migration ni de changement de comportement dans cette PR. Activation future
uniquement après tests automatiques, recette métier et validation explicite.
