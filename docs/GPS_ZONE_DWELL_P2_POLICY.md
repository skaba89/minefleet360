# Lot GPS P2 — politique explicite d'immobilisation par géofence

Cette PR ajoute exclusivement un **contrôle métier pur**, sans modification de la base,
des endpoints, de l'ingestion GPS ou des notifications.

## Règles appliquées

- Aucune durée configurée pour la géofence = **aucune alerte éligible**.
- Géofence inactive = aucune alerte éligible.
- Le dernier point mesuré doit encore appartenir à la géofence active.
- Durée minimale autorisée : 1 à 1440 minutes. Durée calculée uniquement sur les
  mesures reçues et ordonnées ; aucune extrapolation à partir de l'heure actuelle.
- La sortie de la zone, sa réentrée, le déplacement, une vitesse inconnue et un
  intervalle GPS trop long remettent à zéro le segment mesuré.
- Les géofences qui se chevauchent sont évaluées indépendamment.
- Les zones de chargement/déchargement peuvent nécessiter des durées spécifiques :
  ne pas activer une politique implicite par type de zone.

## Restant avant l'activation effective

1. Ajouter un paramétrage administrateur par géofence avec audit, historisation
   et validations tenant/site RLS.
2. Intégrer le calcul aux points GPS acceptés, avec les appartenances PostGIS
   déterminées et autorisées pour chaque position et un traitement transactionnel.
3. Étendre le schéma d'alertes avec une migration additive, un index anti-doublons
   adapté à chaque couple véhicule/géofence, et les types d'alerte frontend/API.
4. Gérer ouverture et clôture sur mouvement, sortie, désactivation de zone,
   mesures tardives et absence de signal.
5. Réutiliser le système de notifications existant uniquement après tests de
   non-régression, permissions et scénarios de terrain.

La fonction ne déclare pas qu'une alerte a été envoyée, créée ou clôturée :
`eligible` décrit uniquement si les preuves mesurées atteignent la politique
explicite. Rien n'est activé automatiquement en recette ou production.
