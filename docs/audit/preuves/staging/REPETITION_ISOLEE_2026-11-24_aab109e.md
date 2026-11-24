# Répétition isolée release/rollback `aab109e` — 24 novembre 2026

- **Nature** : répétition sur **copie isolée**, aucun accès au VPS ni au staging actif. Démon Docker dédié (Docker-in-Docker 29.10, magasin d'images containerd) sur un poste de développement ; secrets générés pour l'occasion, données exclusivement fictives (`minefleet seed-fictif`), proxy HTTPS commun simulé par Caddy (`tls internal`, routage identique à `vps-proxy-minefleet.caddy`), réseau externe `edge`.
- **Code testé** : branche `ops/staging-release-rollback-hardening` (base `aab109e`).
- **Ce que la répétition ne prouve pas** : le comportement du VPS réel (version Docker, magasin d'images, archives TAR réelles, fonds PMTiles réels, volumétrie).

## État initial reproduit (identique au staging déclaré)

| Élément | Valeur |
|---|---|
| API | `ghcr.io/skaba89/minefleet360/api@sha256:d1f6a6d3…eabe0` (`6422258`, signée) |
| Web | build local de `b35dcd6` (absent de GHCR), label de révision `b35dcd66…` |
| Schéma | `0076` |
| Volumes / réseaux | `minefleet_db-data`, `minefleet_mail-capture` ; `edge`, `minefleet_default` |
| Fonds | `infra/deploy/basemap/{france,guinee}.pmtiles` (substituts PMTiles v3), montage `ro` |
| Archives de secours | `docker save` par identifiant : api `8b11cc98…`, web `2bff87eb…` (SHA256), `RepoTags: null` |

## Images vérifiées (Cosign + attestation SLSA v1, identité `release-images.yml@refs/heads/main|tags/v*`)

| Rôle | Référence | Résultat |
|---|---|---|
| Cible API `aab109e` | `api@sha256:c5b1d216…74990` | signature + SLSA OK |
| Cible web `aab109e` | `web@sha256:7ac4919e…5ed5ed` | signature + SLSA OK |
| Rollback API `6422258` | `api@sha256:d1f6a6d3…eabe0` | signature + SLSA OK |
| Rollback web signé `6422258` | `web@sha256:14c60ea9…a8a4f` | signature + SLSA OK |
| Web `b35dcd6` | absent de GHCR (`sha-b35dcd6` inexistant) | **secours local uniquement** |

## Séquence exécutée

| # | Action (UTC) | Résultat observé |
|---|---|---|
| 0 | smoke métier sur l'état initial | 11 contrôles OK (après enrôlement MFA du compte fictif `OPS_MANAGER`) |
| 1 | `plan` puis `plan-fallback` | `PLAN OK` ×2 ; 4 images vérifiées ; base `healthy` sur `minefleet_db-data` ; révision `0076` ; runtime planifié = runtime en service ; PMTiles listés |
| 2 | `apply` 21:45:44Z → 21:47:15Z | sauvegarde vérifiée ; images cible et rollback tirées et labels contrôlés ; `0076 → 0077` ; `check_schema_revision` OK ; smoke HTTPS + métier OK ; `PostgreSQL untouched (8bd116a4b188), revision 0077` ; `RELEASE OK` |
| 2b | écriture avec la nouvelle API | géofence créée, listée, désactivée |
| 2c | SQL sur la copie | `dwell_threshold_minutes = 15` sur les géofences existantes (ligne « ère 0077 ») |
| 3 | `rollback` signé 21:48:11Z → 21:48:48Z | API `6422258` + web `6422258` ; smoke métier OK ; révision **0077 conservée** ; même conteneur PostgreSQL ; `ROLLBACK OK (signed GHCR images)` |
| 3b | écriture avec l'**ancienne API sur 0077** | géofence créée, listée (y compris la ligne où la colonne 0077 est renseignée), désactivée ; missions lues |
| 4 | `apply` à nouveau | `RELEASE OK`, migration sans objet, PostgreSQL inchangé |
| 5 | image web `b35dcd6` retirée du démon, puis `rollback-fallback` 21:50:06Z → 21:50:33Z | archives : SHA256 et identifiant OK ; web rechargé depuis le TAR ; tags `minefleet-local-fallback/api:6422258…`, `minefleet-local-fallback/web:b35dcd66…` (aucun nom GHCR) ; smoke métier OK ; `ROLLBACK OK (UNSIGNED local fallback images)` |
| 5b | écriture avec l'ancienne version exacte (`6422258` / `b35dcd6`) sur 0077 | géofence créée, listée, désactivée |

## Preuves finales

- Conteneur PostgreSQL `8bd116a4b188…`, `StartedAt 2026-11-24T21:41:04Z`, `healthy`, **0 redémarrage** du début à la fin.
- Révision Alembic finale `0077` (jamais rétrogradée).
- Volumes : `minefleet_db-data`, `minefleet_mail-capture` uniquement ; montage `/srv/basemap` `rw=false` sur la même source.
- Sauvegardes : 4 dumps créés (21:46, 21:48, 21:49, 21:50), **aucun supprimé**.
- Journaux (SHA256 tronqués) : plan-fallback `154d649d…`, apply `53970009…`, rollback signé `01c8da44…`, re-apply `62d33832…`, rollback de secours `8d802c53…`.

## Constats issus de la répétition (corrigés dans la branche)

1. Le compte `TENANT_ADMIN` ne peut pas servir au smoke (MFA obligatoire, pas de lecture des missions) : compte `OPS_MANAGER` fictif enrôlé en MFA requis.
2. Un code TOTP n'est accepté qu'une fois : le smoke attend la fenêtre suivante une seule fois (release puis rollback automatique rapprochés).
3. Les listes paginées refusent `limit` (paramètre `page_size`).
4. Magasin containerd : l'identifiant d'image est le digest d'index ; le contrôle d'archive accepte `manifest.json` (classique) ou `index.json` (containerd).

Non exercé en réel : le rollback **automatique** après échec post-release (couvert par les tests automatisés `test_business_failure_triggers_rollback_to_distinct_api_and_web` et `test_apply_rolls_back_when_api_never_becomes_ready`).
