# Industrial IoT — fondation du référentiel
Base f8c7263a71757beeaac558e2f318fa6aff3cf14d. Arborescence Git récursive : 1212 entrées, non tronquée. Dernière migration numérotée observée 0077; vérifier la tête Alembic en CI. Aucun fichier métier dédié IoT/TPMS/Wheel Safety identifié par nom hormis l'ADR; cela ne garantit pas l'absence de code sous un autre nom. Tests pneus, GPS gateway, ingestion, alertes, notifications, différé et isolation déjà présents.
 
## Tranche 0078
Trois tables additives : fabricant par tenant, passerelle par site, capteur par passerelle. RLS via helper existant; FK composites empêchent les liens inter-tenant et les capteurs d'un site ou d'une provenance différents de leur passerelle. Le fabricant du capteur peut différer de celui de la passerelle. Pas de données initiales ni de permissions API, pas de credential, pas de télémétrie. Accès applicatif SQL limité à SELECT/INSERT; retrait et mise à jour réservés à une tranche ultérieure avec autorisation et audit. PHYSICAL ne signifie ni connecté ni certifié. Aucun matériel réel activé.
 
## Gates avant exposition
- Vérifier upgrade de 0077 à 0078 et chaîne unique; downgrade uniquement base jetable autorisée.
- Tester insertion valide, doublon fabricant normalisé, doublon appareil, références inter-tenant, incohérence site/provenance, refus UPDATE/DELETE du rôle applicatif, visibilité RLS et absence de données initiales.
- Ajouter modèles ORM, services, matrice RBAC, tests API par site et audit avant toute route accessible. RLS tenant n'est pas un substitut au filtrage site.
- Concevoir affectations temporelles véhicule/position/pneu, sans modifier tyre_event ni GPS.
- Ne pas déployer en production. Aucun test exécuté localement lors de cette rédaction; résultats CI et tests SQL dédiés requis avant utilisation.
