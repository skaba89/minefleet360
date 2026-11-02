# Décisions prises par délégation (2 novembre 2026)

Le propriétaire a délégué les arbitrages en attente (« je te laisse faire en respectant l'ordre de priorité »).
Chaque décision retient l'option la plus prudente, est réversible et est livrée dans une PR distincte pour revue.

| Réf. | Sujet | Décision | Pourquoi | Livraison |
|---|---|---|---|---|
| D-DEL-01 | Notifications (MATRICE_RBAC §6 point 3) | Récapitulatif HSE **quotidien par e-mail**, seulement s'il y a une action due, sans texte libre ni nom ; pas de SMS ni d'alerte instantanée | utile sans exposer de données sensibles par messagerie ; volume maîtrisé ; réutilise le canal e-mail existant | `LIVRAISON_NOTIFICATIONS.md` |
| D-DEL-02 | Portée du responsable carburant (MATRICE_RBAC §6 point 4) | **Rôle de site uniquement** ; attributions société existantes conservées, nouvelles refusées ; `/roles` aligné | toutes ses permissions carburant étaient déjà de portée site ; élargir le carburant à la société aurait accru les droits | PR #316 |
| D-DEL-03 | Pneus et stock de pièces | **Le registre individuel des pneus fait foi pour leur stock** ; aucun mouvement automatique dans le magasin ; article du catalogue « à l'unité » ; synthèse de stock | évite double comptage et valorisation divergente ; pas de second référentiel | PR #317, `LIVRAISON_PNEUS.md` |
| D-DEL-04 | Saisie hors ligne des inspections | **Reportée** jusqu'à l'essai terrain réussi du premier parcours hors ligne sur téléphone Android réel | condition explicite de la mission ; une inspection hors ligne multiplie les cas de conflit (modèle archivé, photos) | — |
| D-DEL-05 | Immobilisation après inspection non conforme | **Pas d'immobilisation automatique** ; avertissement et signalement de panne bloquante pré-rempli, confirmé par l'utilisateur, via le circuit atelier (D-44) | un faux positif ou une erreur de saisie ne doit pas arrêter un engin ; l'immobilisation garde ses règles et son audit | `LIVRAISON_HSE2.md` |
| D-DEL-06 | Fournisseur de traceurs GPS | **Aucun adaptateur sans spécification réelle** ; cahier des éléments à obtenir | un adaptateur « à l'aveugle » produirait des positions fausses ou mal datées | `GPS_FOURNISSEUR_CAHIER.md` |
