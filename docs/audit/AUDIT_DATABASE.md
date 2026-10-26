# Audit base de données

Commit `2e3b803`, 26 octobre 2026. PostgreSQL 16/PostGIS cible; revue des six migrations et mappings SQLAlchemy. Exécution locale des migrations bloquée faute de serveur; CI du snapshot réussie sur base neuve.

## Architecture constatée

Chaîne linéaire `0001 foundation → 0002 organization → 0003 identity → 0004 audit → 0005 fleet → 0006 workforce`. Bootstrap séparé : extensions PostGIS, btree_gist, citext; propriétaire `mf_owner` non superutilisateur/NOBYPASSRLS, applicatif `mf_app` sans contournement RLS. Downgrades refusés hors local/test/ci.

Les modèles ORM assurent l'accès applicatif; les migrations SQL portent des garanties supplémentaires : FK composites tenant/objet, exclusions temporelles, contraintes d'état/dates, colonnes générées, triggers de version et historique. Contexte tenant transactionnel via `set_config(..., true)`, rollback au retour des sessions. Les écritures métier et audit partagent la transaction.

## Anomalies

| ID | Gravité | Fichier et preuve | Impact | Correction proposée |
|---|---|---|---|---|
| DB-01 | Haute | 0005_fleet.py:92-100 lit tenant; 0001_foundation.py:169-178 FORCE RLS/policies mf_app; bootstrap.sh:12 mf_owner NOBYPASSRLS | Backfill catalogue des tenants préexistants invisible sous mf_owner, migration susceptible de réussir sans catégories | Migration corrective additive/idempotente; accès propriétaire temporaire encadré et protections rétablies dans transaction; tester upgrade 0004 peuplée |
| DB-02 | Moyenne | app/core/config.py:66-75 concatène mot de passe dans URI | Caractères réservés @/:#% mal interprétés, connexion impossible ou hôte mal analysé | URL.create SQLAlchemy; tests sur secrets synthétiques pour app et owner, y compris chemin Alembic |
| DB-03 | Moyenne | 0004_audit.py:70-92 crée 12 mois de partitions; aucun entretien CLI/runtime trouvé | DEFAULT grossit après horizon; création de partitions peut échouer si plage déjà présente dans DEFAULT | Commande propriétaire d'entretien, calendrier et procédure transactionnelle de redistribution; politique de rétention |
| DB-04 | Moyenne | tests/conftest.py:37-38 downgrade base/upgrade head sur base vide | Absence de validation d'upgrade avec données, notamment DB-01 | Test dédié snapshot 0004 peuplé → head, données conservées, catalogue et protections contrôlés |
| DB-05 | Faible | alembic/env.py:17 sans target_metadata, organization/models.py sans location | Autogénération/check de dérive non exploitable tel quel | Déclarer SQL source de vérité + assertions catalogue; compléter ORM avant autogénération |

Chemins migrations relatifs à `backend/alembic/versions/`; bootstrap = `infra/db/init/00_bootstrap.sh`. DB-01 est établi par lecture combinée des rôles et politiques; reproduction sur base peuplée encore requise. Ne pas corriger seulement la migration historique : les bases déjà montées en 0006 doivent être réparées.

## Vérifications à ajouter

Comparer tables/index/contraintes/RLS/privilèges aux catalogues PostgreSQL; refuser tout privilège permanent de contournement pour mf_app. Vérifier upgrade avec tenants actifs/suspendus et catégories personnalisées, idempotence de réparation, reprise après interruption, concurrence sur changements de statut et affectations. Tester sauvegarde puis restauration isolée avec contrôles d'intégrité et isolation.

L'audit est append-only pour l'application, mais les colonnes prev_hash/row_hash ne prouvent pas une chaîne cryptographique. Ne pas annoncer une preuve d'inaltérabilité complète. La partition DEFAULT évite une panne immédiate à expiration de l'horizon; DB-03 est une dette d'exploitation.
