# Immobilisation en géofence — stockage désactivé par défaut (migration 0077)

## Ce qui est livré

La colonne nullable `site_geofence.dwell_threshold_minutes` permet de stocker
une durée explicite propre à chaque zone, comprise entre **1 et 1440 minutes**.
`NULL` signifie **désactivé** : toutes les zones existantes conservent donc
leur comportement actuel à l'installation de la migration.

Le moteur d'ingestion GPS, les alertes, notifications, permissions, routages
et composants frontend ne changent pas. Aucun seuil n'est imposé à une zone
de chargement, déchargement, atelier ou autre.

La table préexistante conserve ses règles RLS, ses clés tenant/site,
et ses triggers d'audit/touch. Une API permettant à un administrateur autorisé
de configurer le seuil avec audit de changement reste à réaliser séparément.

## Contrôles obligatoires avant utilisation

1. Test de migration sur base isolée et données existantes ; vérifier que toutes
   les géofences historiques ont un seuil `NULL`.
2. Vérifier la contrainte : `0`, `1441` et valeurs négatives rejetées.
3. Créer un endpoint authentifié avec permission `fleet.gps_policy.manage`,
   contrôle du site et de la société, et audit explicite avant d'autoriser les écritures.
4. Ne jamais exposer une mise à jour directe SQL par un utilisateur métier.
5. Ne pas activer les alertes : il manque encore les requêtes PostGIS par
   mesure, anti-doublons, ouverture/clôture et notifications contrôlées.
6. N'autoriser un déploiement que dans la filière de recette avec sauvegarde,
   migration contrôlée et rollback d'application documenté.

La PR ajoute uniquement le support de stockage et les tests du contrat
de migration : **pas de déploiement automatique sur le VPS**.
