# Plan de remédiation priorisé

État au 26 octobre 2026, base `2e3b803`. Ce document prépare les corrections; aucune correction applicative n'est présentée comme livrée dans le lot d'audit.

## Ordre d'exécution

| Lot | Anomalies | Résultat attendu | Sortie obligatoire |
|---|---|---|---|
| R1 — intégrité migrations | DB-01/02/04 | Catalogue réparé pour tenants existants, URI fiables, upgrade peuplé testé | Migration additive, tests de migration/API/isolation, rapport de vérification |
| R2 — cycle des sites | MET-01 | Un site occupé ne peut être désactivé; pas de course avec création/transfert | Contrats publics, API existante corrigée, tests concurrence et audit |
| R3 — authentification exploitable | SEC-01/02/03/04/05, OPS-01 | Limitation partagée et bornée, transport mail approprié, rejeu complet, statut MFA explicite | Migration si stockage ajouté, tests multiworker, revue sécurité |
| R4 — qualité exploitation | DB-03/05, CI-01/02/04/05, OPS-02, QA-01, DOC-01 | Builds reproductibles, entretien partitions, restauration prouvée, tests purs indépendants | CI/artifacts et procédures vérifiées |
| M1 — première tranche métier/UI | MVP-01 et affectations absentes | Parcours connexion → site → engin → conducteur → affectation | Migration, API, UI, tests unitaires/intégration/E2E/inter-tenant et audit |

Les corrections documentaires et les tests indépendants peuvent accompagner R1. R2 et R3 bloquent toute ouverture pilote. Ne pas attendre le MVP complet pour traiter ces risques.

## Premier lot correctif R1 — prêt à implémenter

### Problème et périmètre

Le catalogue 0005 est copié depuis tenant sous un rôle propriétaire sans policy de lecture, alors que RLS est forcée. Le test actuel repart d'une base vide. R1 ajoute une réparation des données pour les bases déjà en 0006 et une preuve d'upgrade réelle; il ne modifie pas les migrations historiques en place.

Fichiers envisagés :

- `backend/alembic/versions/0007_repair_tenant_catalog.py` (numéro à confirmer après relecture du head avant développement).
- `backend/app/core/config.py` : création structurée de l'URL; `backend/alembic/env.py` seulement si nécessaire pour compatibilité de type, ne jamais afficher l'URL complète.
- `backend/tests/test_migration_upgrade.py` et tests unitaires de configuration dans un répertoire indépendant du conftest d'intégration.
- Documentation livraison R1, règles de migration et ce rapport actualisé.

### Stratégie de données

Migration transactionnelle exécutée par mf_owner : accorder uniquement la visibilité temporaire nécessaire au backfill par une policy propriétaire contrôlée; retirer cette policy dans la même transaction. Restaurer toutes protections en cas de rollback, sans BYPASSRLS permanent. Traiter tenant et tables destination protégées. Insérer uniquement les codes système manquants et associations de permis manquantes, sans écraser les personnalisations. Vérifier les collisions de codes avant d'adopter une sémantique; privilégier un arrêt explicite documenté plutôt qu'une modification silencieuse.

Conserver les catégories ajoutées lors d'un downgrade correctif : aucune suppression de données métier. Respecter le garde de downgrade existant. Documenter cette non-réversibilité des données et la stratégie de retour applicatif. Toute opération destructive reste hors périmètre sans validation.

### Critères d'acceptation

1. Base isolée montée en 0004, tenants synthétiques créés avec rôle applicatif réel, upgrade vers head : catalogue et associations présents pour chaque tenant client concerné.
2. Base déjà en 0006 avec tenants privés de catalogue : réparation; tenant plateforme exclu; personnalisations conservées; aucune duplication.
3. Après migration : FORCE RLS toujours actif, aucune policy temporaire restante, mf_app sans BYPASSRLS, contexte A ne voit/écrit aucune donnée B.
4. Insertion véhicule par API après réparation réussie avec une catégorie de son tenant; catégorie d'un autre tenant refusée.
5. Secrets synthétiques avec caractères réservés : URL app et owner analysées sans modification du mot de passe, de l'hôte ou du nom de base. Aucun secret affiché dans les assertions.
6. Base vide → head toujours valide; upgrade puis réexécution du mécanisme idempotent sans duplication; erreur injectée = rollback atomique.

### Vérification et livraison

Exécuter Ruff/format, mypy, tests purs puis intégration PostgreSQL/PostGIS sous mf_app/mf_owner, suite complète avec couverture, pip-audit et CI. Faire relire sécurité/QA. Rapport obligatoire : commandes, résultats, échecs/blocages, SHA, diff, risques et rollback. Aucun statut « corrigé » avant preuve.

API : endpoints existants, pas de nouveau contrat public nécessaire. Interface : absente actuellement, donc validation UI impossible pour ce correctif de données; le lot M1 doit livrer l'interface exigée avant démonstration métier. R1 n'est pas un MVP vertical complet.

## R2 — préparation détaillée

Étendre `fleet/contracts.py`, créer `workforce/contracts.py`, raccorder `_site_blockers` sans importer les modèles privés entre modules. Retourner total exact et liste bornée sans nom personnel. Harmoniser verrous de site à la désactivation et à la création/transfert d'une ressource; un simple COUNT avant UPDATE ne suffit pas contre les courses.

Tests : véhicule non réformé/conducteur non inactif →409 et audit inchangé; site vide ou ressources terminales →succès et événement unique; autre tenant/site sans effet; deux transactions concurrentes ne peuvent produire un site inactif avec nouvelle ressource active. Aucun changement de schéma attendu si les verrous existants suffisent : migration non applicable à justifier, pas de migration vide artificielle.
