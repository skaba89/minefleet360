# Protocole d'exercice de restauration depuis le coffre externe — preuve R1

- **Objet** : protocole d'exécution de la campagne « sauvegarde → coffre externe → restauration réelle »,
  pour produire la preuve datée de **récupération réelle des données et de remise en service sur
  environnement isolé** exigée par `docs/qa/GO_NO_GO.md` (condition n° 2), `docs/ops/RECETTE_STAGING_VALIDATION.md`
  (phase C) et `docs/ops/PROTOCOLE_PILOTE.md` (prérequis 2). Le round-trip synthétique de CI prouve la
  mécanique ; seul cet exercice prouve l'exploitation.
- **Règle d'or** : la restauration se fait **toujours** dans un environnement isolé jetable (instance
  Docker temporaire). Elle ne remplace **jamais** la base staging ou production active, ne touche ni aux
  volumes ni au conteneur `db` en place, et ne réalise aucun `alembic downgrade`.
- **Outillage existant** (aucun développement requis) : `infra/deploy/backup.sh`,
  `upload-offsite-backup.sh`, `verify-offsite-backup.sh` (téléchargement + authentification + décryptage +
  restauration isolée), `offsite-common.sh` (configuration hors dépôt `offsite.env`), `probe-backup-freshness.sh`,
  `verify-restore.sh` (gates RLS fail-closed).

## 0. Conditions préalables

| # | Prérequis | Preuve |
|---|---|---|
| P1 | Coffre externe retenu et configuré hors dépôt (`offsite.env` régulier, mode 600/400, jamais commité) | configuration vérifiée par `offsite-common.sh` |
| P2 | Clé de chiffrement GPG disponible, récupérable indépendamment de l'hôte (coffre), et **testée sur un autre poste** | empreinte de clé + essai de décryptage hors hôte |
| P3 | Approbation explicite consignée pour l'exercice (phase C = mutation sur instance jetable uniquement) | approbateur, date, périmètre |
| P4 | Image API du SHA audité disponible localement (pour le smoke de l'instance restaurée) | digest de l'image |
| P5 | Espace disque suffisant pour l'archive + l'instance restaurée (constaté par `docker system df` et `df -h`) | sorties horodatées |

## 1. Séquence d'exercice (les 14 contrôles de la campagne)

| # | Contrôle | Commande / procédure | Preuve produite |
|---|---|---|---|
| 1 | Sauvegarde PostgreSQL opérationnelle | `time bash backup.sh` | exit 0, dump chiffré horodaté, taille |
| 2 | Chiffrement | le dump est produit `.dump.gpg` ; vérifier la présence du destinataire attendu (sans afficher la clé) | métadonnées GPG horodatées |
| 3 | Transfert externe | `bash upload-offsite-backup.sh <archive>` | exit 0, objet visible dans le coffre |
| 4 | Contrôle d'intégrité | checksum SHA256 local vs coffre (si le coffre l'expose) ; sinon re-téléchargement comparé | checksums horodatés |
| 5 | Conservation | constater la rétention du coffre (politique, nombre d'objets, purge) | capture de configuration (sans secret) |
| 6 | Téléchargement depuis le coffre | première étape de `verify-offsite-backup.sh <objet>` | journal de téléchargement |
| 7 | Décryptage | réalisé par le script (clé P2) | archive `.dump` en clair dans le répertoire temporaire privé |
| 8 | Restauration sur environnement isolé | suite du script : instance PostgreSQL jetable, chargement du dump | exit 0 de la restauration |
| 9 | Contrôle du schéma | tête Alembic de l'instance restaurée = tête attendue (comparé à `alembic/versions`) | sortie `alembic current` horodatée |
| 10 | Contrôle RLS | gates RLS fail-closed de `verify-restore.sh` (rôles non-superuser, `NOBYPASSRLS`, cloisonnement) | sortie des gates |
| 11 | Démarrage API | smoke de l'instance restaurée (`--api-image`) : `/api/v1/health`, `/api/v1/ready` | premier GET health réussi (horodaté) |
| 12 | Mesure RPO/RTO | **RPO** = horodatage début d'exercice − horodatage du dump restauré ; **RTO** = durée étapes 6 → 11 (téléchargement → health OK) | valeurs brutes + cibles figées |
| 13 | Vérification des alertes | `MF_BACKUP_DIR=… MF_BACKUP_MAX_AGE_HOURS=1 bash probe-backup-freshness.sh` puis, sur incident simulé (ex. archive manquante), transition ALERT du moniteur | exit codes + journal moniteur |
| 14 | Procédure de reprise | consigner dans le rapport la séquence reproductible (ordre, durées, responsabilités) qui devient le réflexe d'incident | section reprise du rapport |

## 2. Incidents simulés complémentaires (au moins un par campagne)

Pour éprouver la détection, pas seulement la restauration :

1. **Archive absente du coffre** : `verify-offsite-backup.sh` sur un objet inexistant → échec propre,
   sonde/coffre cohérente, incident consigné.
2. **Archive corrompue** : altérer une copie (un octet) → le checksum/décryptage échoue, rien ne démarre.
3. **Clé absente** : exercer sans la clé GPG → message clair, aucune restauration partielle.

Chaque incident simulé est joué **hors** de la séquence nominale (après l'étape 14), sur la même instance
jetable, et consigné avec son exit code et le comportement observé.

## 3. Rapport d'exercice (modèle — alimente `docs/ops/DISASTER_RECOVERY_EVIDENCE.md` à créer)

| Champ | Contenu |
|---|---|
| Date, opérateur, approbateur | … |
| Environnement source (staging/…) et objet restauré | … |
| Coffre utilisé (type, objet, checksums) — sans secret | … |
| Étapes 1–14 : horodatages bruts, durées, exit codes | … |
| **RPO mesuré / cible** ; **RTO mesuré / cible** | … |
| Gates RLS et schéma : résultats | … |
| Incidents simulés : comportements constatés | … |
| Écarts et actions correctives (PR/tickets) | … |
| Décision : preuve R1 acquise (oui/non) — périmètre exact | … |

**Critère de fin de la campagne** : un rapport daté complet, avec RPO/RTO mesurés sur un environnement
isolé réel, alimentant `docs/audit/COMMERCIAL_READINESS_CURRENT.md` (§ inconnues n° 5) et la condition n° 2
du `GO_NO_GO.md`. Un échec à une étape produit malgré tout un rapport : il documente l'écart à corriger
avant nouvelle campagne — jamais une « réussite partielle ».
