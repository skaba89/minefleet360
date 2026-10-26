# Lot R2 — intégrité du cycle de vie des sites

Base : `main` `b19c825d504ec158fc633024a5b8993bf7b31d01`. Date : 26 octobre 2026.

## Problème et comportement livré

Le contrôle `_site_blockers` était un stub qui retournait toujours une liste vide. L'API pouvait donc désactiver un site qui contenait des véhicules et conducteurs actifs. Les créations et transferts ne vérifiaient pas non plus que le site était actif.

Le contrôle appelle maintenant les contrats publics flotte et personnel. Un véhicule non réformé ou un conducteur non inactif bloque la désactivation avec `409 SITE_HAS_ACTIVE_RESOURCES`. Le total couvre les deux types de ressources; la liste est bornée par `blocking_list_max` et contient uniquement type d'objet et UUID. Aucun nom, matricule ou texte libre n'y figure.

Les créations et transferts d'engins/conducteurs exigent un site actif dans la portée autorisée. Toute transition conducteur vers un statut différent de `INACTIVE` exige également un site actif. Le refus utilise l'erreur existante `422 REFERENCE_NOT_FOUND` sans distinguer site inactif, étranger ou hors portée.

## Concurrence et isolation

Le contrat `active_site_in_scope` prend un verrou PostgreSQL `FOR SHARE`, conservé jusqu'au commit/rollback métier. Il entre en conflit avec le `FOR NO KEY UPDATE` utilisé par la désactivation. Si une arrivée gagne, sa ressource est visible avant le contrôle de désactivation; si la désactivation gagne, l'arrivée attend puis relit le statut inactif et échoue. `populate_existing=True` rafraîchit également les instances présentes dans le cache SQLAlchemy.

Les contrats de blocage lisent les ressources sans verrou de ligne, évitant un cycle site→ressource face aux mises à jour ressource→site. Les requêtes restent soumises à FORCE RLS. Cette garantie concerne les chemins applicatifs : des écritures SQL directes utilisant mf_app peuvent contourner les contrats; aucune contrainte de schéma universelle n'est ajoutée dans ce lot.

Dans chaque module, total et liste sont calculés par la même requête avec COUNT OVER. Les deux modules sont lus successivement sous READ COMMITTED : un départ concurrent peut rendre le refus conservateur, mais aucune arrivée active ne peut dépasser le verrou du site. Le total est la somme des comptages réels, sans être réduit à la longueur de la liste affichée.

## Fichiers et compatibilité

`organization/contracts.py`, `organization/service.py`, `fleet/contracts.py`, `fleet/service.py`, nouveau `workforce/contracts.py`, `workforce/service.py` et `tests/test_site_lifecycle.py`. Les modules consomment uniquement les contrats publics des autres modules, pas leurs modèles privés.

Migration : non applicable, aucun changement de schéma. API : routes et codes existants; détails du 409 désormais réellement renseignés. Interface : aucun frontend n'existe encore sur cette base; les écrans de ce parcours restent dans M1. Audit : le refus ne modifie ni le site ni son audit; une désactivation réussie produit l'événement existant une seule fois.

## Tests ajoutés et vérifications

- Total exact, liste bornée, absence de PII, statut/ETag/audit inchangés après refus.
- Véhicule seul, conducteur seul, ressources d'un autre site ou tenant et appel avec UUID étranger.
- Ressources terminales autorisées, créations/transferts/réactivations refusés sur site inactif, reprise après réactivation du site.
- Deux sessions PostgreSQL : verrou d'arrivée empêchant la désactivation; verrou de désactivation empêchant l'arrivée; résultat après commit et rafraîchissement d'un cache ORM périmé. Les conflits utilisent un lock_timeout court, sans attente arbitraire ni thread.

Local : Ruff et format réussis, mypy réussi sur 54 fichiers, 3 tests unitaires réussis. PostgreSQL et Docker absents localement : les nouveaux tests métier/concurrence nécessitent la CI réelle. Revue spécialisée sécurité/QA effectuée : aucun bloquant statique; la recommandation de calculer total et liste dans la même requête par module a été intégrée.

Statut : **implémenté, validation PostgreSQL CI en attente**. Aucun déploiement ni fusion automatique.
