# Carburant — premier parcours de stock

## Parcours livré

1. Un administrateur, responsable des opérations ou responsable carburant crée une cuve rattachée à un site, avec son code, son type (gazole ou essence) et sa capacité en litres.
2. Une réception ajoute une entrée positive au journal. La référence du bon de livraison est unique par cuve. Le verrou de la cuve empêche deux réceptions concurrentes de dépasser sa capacité.
3. Une demande de ravitaillement désigne une cuve, un véhicule, le conducteur actuellement affecté, le volume et, si le véhicule en possède un, le type et la valeur du compteur.
4. La demande réserve immédiatement le volume demandé. Le stock disponible est le solde du journal moins les réservations en attente.
5. Une autre personne approuve ou refuse la demande. L'approbation ajoute la sortie au journal append-only ; le refus libère la réservation. Une personne ne peut pas approuver sa propre demande.

## Intégrité et autorisations

- Les tables sont isolées par tenant via RLS forcée et clés étrangères composites tenant/site.
- Le solde est dérivé des mouvements positifs (réceptions) et négatifs (ravitaillements approuvés) ; aucune colonne de solde modifiable n'est maintenue.
- Les écritures qui affectent une cuve la verrouillent. Les réservations et mouvements sont donc sérialisés pour éviter les stocks négatifs, les doubles sorties et les dépassements de capacité.
- Demandes, décisions et mouvements sont append-only en base. Les opérations importantes sont auditées sans enregistrer le volume ni les données du conducteur dans l'événement d'audit.
- L'accès de lecture est distinct de la gestion des cuves, des réceptions, de la demande et de la décision.

## Périmètre et suites

Cette première tranche couvre les cuves, les réceptions et les demandes approuvées/refusées. Le type de carburant est limité au gazole et à l'essence ; les volumes sont en litres. Les compteurs sont liés au type configuré pour la catégorie du véhicule et les valeurs validées doivent rester monotones entre ravitaillements approuvés.

Les inventaires physiques et corrections de stock, les seuils d'alerte, les analyses de consommation par km/heure, les anomalies de consommation, les achats fournisseurs et l'intégration des pompes sont des étapes distinctes. Les sorties GPS ne sont pas une mesure de carburant.
