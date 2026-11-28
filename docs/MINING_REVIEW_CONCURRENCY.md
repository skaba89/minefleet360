# Cohérence transactionnelle des décisions de revue minière (ADR)

> Lot dispatch readiness — Phase 3. Statut : implémenté côté décision (rejet),
> `CI_VALIDÉ` ; l'approbation positive reste volontairement indisponible
> (Phase 5) et réutilisera exactement ce mécanisme.

## 1. Objectif

Avant toute décision enregistrée — et surtout avant toute future approbation
positive — les preuves contrôlées doivent correspondre **exactement** à la
version examinée, et la décision doit être écrite alors que les sources qu'elle
décrit sont verrouillées. Un verrou sur le rapport seul ne protège **aucune**
écriture concurrente sur les données sources : le rapport est append-only et
jamais mis à jour.

## 2. Inventaire des risques et mécanisme correspondant

| Risque concurrent | Mécanisme |
| --- | --- |
| Insertion concurrente de nœuds/tronçons | verrou consultatif transactionnel dérivé de la révision (`pg_advisory_xact_lock`, §4) + digest de re-vérification |
| Modification des restrictions / catégories autorisées | idem (lignes scopées révision) + digest |
| Modification des gabarits/pentes (futurs champs de tronçon) | idem — toute donnée entrant dans le digest est couverte |
| Désactivation d'une catégorie d'engin | `FOR SHARE` sur les `vehicle_category` référencées par la révision |
| Modification de la tolérance | champs de qualification **immuables** en base (0091) ; retrait audité ; digest inclut la tolérance |
| Désactivation du site | `FOR SHARE` sur la ligne `site` ; site déjà inactif → snapshot vide → `NOT_FOUND` |
| Création concurrente de décisions | unicité `(report_id, stage)` + `ON CONFLICT … RETURNING` : un gagnant, le perdant reçoit `CONFLICT` (attente réelle sur l'index, testée) |
| Recalcul concurrent des empreintes | la preuve est recalculée **dans** la transaction verrouillée, un énoncé = un instantané (`_SNAPSHOT`) |
| Deadlocks / erreurs de sérialisation | ordre déterministe site → catégories → révision ; aucun participant ne referme un cycle ; `lock_timeout` borne l'attente côté tests, le service n'attrape pas l'erreur (l'appelant peut rejouer) |

## 3. Stratégie (isolation READ COMMITTED)

1. Contrôles d'autorisation et de validation (échec rapide, sans verrous).
2. `lock_review_sources()` : `FOR SHARE` site → `FOR SHARE` catégories
   référencées (triées par id) → verrou consultatif transactionnel sur la
   révision. Ordre fixe, borné (≤ 1 + n_catégories + 1 verrous). Le rôle
   applicatif n'a volontairement pas le privilège UPDATE sur
   `mining_route_revision` (moindre privilège) : tout verrouillage de ligne y
   est donc impossible, d'où le verrou consultatif — sans privilège requis, libéré
   au commit ou au rollback.
3. Lecture du rapport et de l'historique (append-only, sans verrous nécessaires).
4. Contrôles de séparation des devoirs (auto-revue, doublon, indépendance HSE).
5. **Re-vérification des preuves** : `inspect_draft_evidence` recalcule le
   digest dans la même transaction avec la tolérance qualifiée du rapport ;
   divergence → `EVIDENCE_STALE` (409), aucune écriture.
6. `INSERT` décision + `record()` audit **dans la même transaction** ; l'appelant
   possède commit/rollback (rollback = décision et audit disparaissent ensemble,
   testé).

L'appelant qui veut rejouer après une erreur bloquante (`lock_timeout`) refait
l'appel ; le service n'attrape pas les erreurs de verrouillage et ne masque
jamais un conflit par un retry silencieux.

La preuve elle-même reste un instantané d'**un seul énoncé SQL** (`_SNAPSHOT`) :
chaque vérification décrit un état cohérent du graphe, jamais une mosaïque.

## 4. Contrat des futurs écrivains du graphe

Les écrivains applicatifs de `mining_route_node/segment`,
`mining_road_restriction`, `mining_road_allowed_category` n'existent pas encore.
Toute future écriture devra, dans sa transaction :

1. prendre le **même verrou consultatif transactionnel** que les décisions,
   dérivé de la même façon de l'identifiant de révision
   (`pg_advisory_xact_lock` sur les groupes hexadécimaux 1–8 et 25–32 de
   l'UUID — la dérivation est épinglée par un test) ;
2. vérifier le statut `DRAFT` de la révision (et l'`ACTIVE` du site) dans la
   même transaction ;
3. écrire, puis valider.

Ce contrat est la contrepartie du verrou de révision pris par les décisions :
il sérialise toutes les écritures scopées révision, y compris les insertions
(les verrous de lignes existantes ne bloquent pas les phantoms, le verrou
consultatif partagé oui).

## 5. Bornes PostGIS (déjà en place, rappelées ici)

- snapshot borné : nœuds et tronçons `LIMIT 1001`, catégories ≤ 1000 par
  tronçon et ≤ 10 000 au total → `CONFLICT` au-delà ;
- findings plafonnés à 3 000 par rapport ;
- géométries validées en base (`ST_IsValid`, bornes lon/lat) et comparées en
  EWKB ordre d'octet fixe pour un digest stable.

## 6. Limites explicites

- L'approbation positive et l'activation (Phases 5 et 7) doivent réutiliser ce
  schéma et, en plus, re-vérifier l'état **courant** de la qualification de
  tolérance (`APPROVED`, non retirée) au moment de la décision.
- Les tests de concurrence s'exécutent sur PostgreSQL réel (sessions distinctes,
  attente réelle sur l'index unique et `lock_timeout`) : ils prouvent le
  mécanisme transactionnel, pas une charge de production.
- La révocation/suspension et le retour à une version antérieure (Phase 7)
  resteront soumis au même verrou de révision.
