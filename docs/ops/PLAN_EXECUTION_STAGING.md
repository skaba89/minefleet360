# Plan d'exécution staging OVHcloud — session lecture seule (phases A/B)

- **Objet** : plan d'exécution concrétisé d'UNE session de recette staging, limitée aux **phases A/B**
  (audit en lecture seule + dry-run de release) du runbook `docs/ops/RECETTE_STAGING_VALIDATION.md`.
  Ce plan ne duplique pas le runbook : il en séquence les étapes, fixe les artefacts, le budget de temps
  et les critères d'interruption, pour produire le rapport daté exigé par `docs/qa/GO_NO_GO.md`
  (condition bloquante n° 1) sans aucune modification de l'hôte.
- **Interdits inchangés** : aucun `apply`, aucun conteneur démarré/arrêté, aucune écriture base, aucune
  intervention sur les autres applications hébergées sur le VPS, aucun `docker compose down -v`. Les
  phases C/D (sauvegarde/restauration, release → rollback) restent hors de ce plan et exigent une
  approbation explicite consignée.
- **Principe de non-nuisance** : le VPS est partagé. Toute commande est bornée au projet
  (`docker compose -f docker-compose.prod.yml --env-file .env.prod …`) ; jamais `docker` global
  inspectant les conteneurs d'autres projets ; jamais de ressource système modifiée.

## 1. Découpage de la session (budget indicatif : 2 h 30, interruptions immédiates si critère §4)

| Séquence | Contenu (référence runbook) | Durée cible | Artefacts produits |
|---|---|---:|---|
| S0 | Pré-vol : accès, `.env.prod` (mode, `MF_ENV=staging`), `MINEFLEET_STAGING_URL`, outils (`cosign`, `jq`, `openssl`) | 15 min | checklist S0 cochée |
| S1 | A1 versions déployées + reçu `release-state/current.json` | 15 min | sorties horodatées, comparaison GitHub |
| S2 | A2 schéma Alembic (label image + `check_schema_revision`) | 10 min | révision constatée vs `alembic/versions` |
| S3 | A3 images : digests, `cosign verify` + attestation SLSA | 20 min | sorties cosign datées |
| S4 | A4 canaries PostgreSQL (catalogue uniquement) | 15 min | rôles, privilèges, comptage RLS |
| S5 | A5 HTTPS + `check-preproduction.sh` (statique puis `--live`) | 15 min | codes HTTP, dates de certificat |
| S6 | A6 comptes fictifs : login + `/me` (lecture seule) | 20 min | tableau rôles × grants constatés |
| S7 | A7 surface exposée (routes publiques, `/docs` fermé) | 10 min | codes HTTP par route |
| S8 | A8 logs 24 h, `probe-all.sh`, `docker system df`, stats | 15 min | comptage erreurs, exit probes |
| S9 | B dry-run : `release_manifest.py validate` + `staging-release.sh plan` sur un manifeste candidat préparé hors dépôt | 15 min | sortie `PLAN OK` intégrale |
| S10 | Rédaction du rapport (modèle §R du runbook), dépôt des preuves | 20 min | rapport daté + preuves |

## 2. Préparation préalable (hors hôte, avant S0)

1. **Candidat de release** : choisir le SHA de `main` à auditer (CI 3/3 verte vérifiée par API) ; préparer
   le manifeste depuis `release-manifest.example.json` **hors du dépôt** avec les digests GHCR réels de ce
   SHA (workflow `release-images` sur tag, ou images construites et publiées au registre retenu) — la
   phase B n'applique rien : elle prouve seulement que la release est *appliquable* sans surprise.
2. **Comptes fictifs** : confirmer la liste des comptes de recette et leur mode MFA (voir prérequis du
   runbook §0) ; aucune donnée réelle ne transite.
3. **Zone de rapport** : préparer le répertoire de preuves horodaté (`docs/audit/preuves/staging/`,
   dépôt des sorties brutes hors dépôt si sensibles, référencées par chemin + SHA256).
4. **Fenêtre et personnes** : opérateur identifié, propriétaire de l'hôte informé du créneau (courtoisie
   de cohabitation, aucune action de son côté requise pour A/B).

## 3. Points de décision pendant la session

| Constat | Décision |
|---|---|
| Label de révision API ≠ web ≠ reçu (S1) | **Interruption** : divergence d'état ; consigner, ne pas poursuivre S2+ |
| Tête Alembic ≠ révision en base (S2) | **Interruption** : toute release serait en échec ; consigner |
| `cosign verify` en échec (S3) | **Interruption** : chaîne d'approvisionnement non prouvée ; consigner |
| Privilège surplus/manquant sur `mf_app` (S4) | **Interruption** : dérive de droits ; consigner, ouvrir un ticket correctif |
| Sonde `--live` non 200 / certificat < 14 jours (S5) | Consigner (anomalie S2/S3) et poursuivre les lectures ; prévoir renouvellement |
| `probe-all.sh` exit 2 (S8) | Consigner l'incident, poursuivre si lecture seule possible ; l'incident alimente le rapport |
| `plan` en échec (S9) | Consigner la sortie intégrale : le manifeste/état n'est pas appliquable — résultat valide en soi |

## 4. Critères d'interruption immédiate de la session

- Toute commande retourne une erreur suggérant un état incohérent de l'hôte (disque saturé, conteneur en
  redémarrage en boucle) : **stop**, ne rien réparer sur l'hôte pendant la session de lecture seule.
- Découverte d'un secret exposé (log, reçu, étiquette) : stop, consigner hors dépôt, rotation à planifier
  hors session — ne jamais recopier le secret dans le rapport.
- Tout doute sur l'impact d'une commande sur un autre projet hébergé : stop et demander validation.

## 5. Résultats attendus et portée

- Une session A/B **réussie sans anomalie** produit : rapport daté complété (§R), sorties horodatées
  A1–A8, sortie `PLAN OK` — et autorise à **demander l'approbation** des phases C/D (preuves R1/R2).
- Elle **ne lève aucun bloquant** du `GO_NO_GO.md` par elle-même : R1 (restauration réelle mesurée) et
  R2 (release → rollback attesté) restent non validés tant que C/D n'ont pas été exécutés avec approbation.
- Toute anomalie constatée alimente la matrice des blocants de `docs/audit/COMMERCIAL_READINESS_CURRENT.md`
  (colonne « Action suivante ») au lieu d'être corrigée en direct sur l'hôte.
