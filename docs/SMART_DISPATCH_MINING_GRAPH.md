# Smart Dispatch — contrat du référentiel cartographique minier

Statut : proposition à qualifier, pas une migration appliquée. Dépendance au solveur PR #559 après validation. Ne pas réserver de numéro Alembic avant synchronisation de main (travaux IoT parallèles).

## Modèle cible

Réutiliser site_location comme référentiel métier des chargements, déchargements, stocks et ponts-bascules. Ne pas dupliquer ces objets. Le modèle actuel ne porte pas de coordonnées. Ajouter un rattachement facultatif et versionné à un nœud cartographique approuvé, sans modifier les anciennes missions.

- mining_route_revision : tenant, site, version, état DRAFT/APPROVED/RETIRED, provenance du relevé, date de validité, auteur et approbateur distincts. Une seule version approuvée courante par site. Publication transactionnelle.
- mining_route_node : tenant, site, révision, identifiant, geometry(Point,4326), précision et provenance. Liaison facultative à site_location.
- mining_route_segment : tenant, site, révision, origine et destination, geometry(LineString,4326), longueur mesurée en mètres, durée de référence positive en secondes, sens explicite, restrictions et provenance. Pas de boucle sur soi.
- mining_route_closure : tenant, site, segment, intervalle temporel, motif HSE, auteur, audit. Fermeture active prioritaire sur tout calcul de route.

FK composites tenant/site/révision ; RLS forcée selon les conventions existantes ; permissions lecture cartographique, gestion brouillon, approbation et fermeture distinctes. Contrôler également les portées site au service. Index GiST sur géométries, B-tree sur les clés de périmètre, index des fermetures actives. Longueur géodésique via geography, jamais en degrés. Géométries valides, non vides, SRID 4326 et extrémités cohérentes avec les nœuds, tolérance à qualifier sur le terrain.

## Sélection d'un graphe

Le serveur choisit la révision approuvée courante pour le tenant et site authentifiés. Exclure les restrictions inconnues, les segments fermés et les classes de véhicule non autorisées. En cas de données contradictoires, refuser le trajet. Ne pas accepter un graphe transmis par le navigateur. Borner la taille du graphe et le temps de calcul ; retourner un résultat indisponible explicite plutôt qu'un itinéraire partiel.

## Raccordement GPS

Réutiliser la lecture GPS existante sous permission fleet.vehicle.read et la sélection autorisée des affectations. Vérifier fraîcheur, précision, provenance et site courant. Projeter sur une piste autorisée uniquement si le rapprochement est non ambigu, dans une tolérance configurée et validée. Ne jamais assimiler la distance à vol d'oiseau à un itinéraire. Un véhicule hors graphe reçoit un ETA indisponible. Les points simulés ne constituent pas une qualification terrain.

La durée de référence dépend du profil véhicule, de la charge, du sens et des conditions de piste. Aucun calcul ne doit inciter au dépassement d'une limitation de vitesse. La durée et la distance doivent provenir du trajet autorisé complet, y compris le raccordement du véhicule. Conserver la provenance, la révision et l'instant du calcul ; revérifier les fermetures et l'éligibilité lors de la validation humaine. Pas d'affectation automatique.

## Gates avant mise en service

1. Inventaire migrations, contraintes site_location, conventions PostGIS et permissions.
2. Migration additive et tests upgrade/downgrade en base isolée ; aucune donnée réelle par défaut.
3. Tests PostgreSQL RLS, FK inter-sites/inter-tenants, publication concurrente, géométries invalides, fermeture et restrictions.
4. Tests service et API (401/403/404, pagination, limites, absence de fuite), UI cartographique et non-régression GPS/dispatch.
5. Essais terrain : relevés approuvés, restrictions réelles, erreur ETA mesurée par profil et trajet, validation responsable exploitation/HSE.
6. Activation explicite par site, désactivée par défaut ; plan de désactivation et rollback testé.

Aucune promesse d'ETA précis ou de navigation sécurisée avant ces preuves. Cette note ne constitue pas un référentiel opérationnel.

## Prévalidation d’un brouillon

Le service interne `inspect_draft_readiness` lit la révision DRAFT d’un site actif avec la permission
`dispatch.location.read`. Une instruction PostgreSQL rassemble les nœuds, les tronçons, les longueurs
sphéroïdales PostGIS, les restrictions et les catégories actives. La tolérance de levé en mètres est
explicite, finie et positive ou nulle. Une révision vide produit un constat distinct d’une révision
introuvable. Un dépassement de capacité interrompt la lecture avant toute conclusion partielle
(1 000 nœuds, 1 000 tronçons, 1 000 catégories actives par tronçon, 10 000 associations au total).

Les constats décrivent les données visibles au début de la lecture. Une modification validée après cet
instant impose une nouvelle inspection. Le service interne
`capture_draft_report` conserve la révision, l’auteur, l’instant PostgreSQL de la lecture, la tolérance,
la version du validateur, ses entrées et ses constats. Il exige aussi la permission
`dispatch.location.manage` sur le site. Le rapport et l’événement `dispatch.draft.inspect` sont
écrits dans la transaction de l’appelant. Deux captures simultanées avec le même acteur,
les mêmes entrées, la même tolérance et la même version renvoient le même identifiant.

L’empreinte SHA-256 porte sur les entrées effectivement évaluées par ce validateur. L’approbation
d’une révision devra également couvrir les relevés, les géométries, la provenance et les conditions
opérationnelles qui dépassent le périmètre de cette inspection. Les décisions humaines technique et HSE
restent à implémenter.
