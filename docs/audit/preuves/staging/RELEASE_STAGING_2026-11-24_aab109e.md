# Release staging `aab109e` — 24 novembre 2026 — préparation et incident de procédure

Code d'exploitation déployé sur le VPS : `/opt/minefleet` détaché sur `main@bbbb55e` (auparavant `v0.1.0-rc.7`).

## État constaté avant intervention (lecture seule)

- PostgreSQL `b3943b56cef2…` (démarré 2026-11-22T21:14:55Z), `healthy`, volume `minefleet_db-data`, révision `0076`.
- API `ghcr.io/skaba89/minefleet360/api@sha256:3b54142d…` (révision `6422258`, Alembic `0076`) — **différente** du tag `sha-6422258` actuel (`d1f6a6d3…`, autre construction du même commit) ; signature et SLSA vérifiées.
- Web `minefleet-web-gps:b35dcd6678b4` (`42ba8454…`), construit localement, absent de GHCR.
- Archives exactes : `~/minefleet-backups/rollback-images/{api,web}-before-aab109e1.tar`, SHA256 `25762645…` / `5f84080a…`, tags locaux sans registre.
- Web `b35dcd6` signé publié par `release-images` (run `45501106482`, après #530) : `web@sha256:12299700…4421c7`, tag `sha-b35dcd6`, signature + SLSA + label vérifiés.

## `plan` et `plan-fallback` (≈ 22:40Z)

Tous deux `PLAN OK` : quatre images signées et attestées (cible `c5b1…`/`7ac4…`, rollback `3b54…`/`1229…`), base saine sur le volume attendu, révision `0076`, runtime planifié = runtime en service, PMTiles `france` (4 764 795 268 o) et `guinee` (142 978 055 o) ; archives de secours conformes.

## Incident : `rollback` exécuté à la place d'`apply` (22:43Z)

- `rollback` lancé alors que le fichier de smoke métier était incomplet.
- Effectué : préflight complet, sauvegarde vérifiée (7 → 8 dumps, aucune suppression), remplacement **API/web seuls** : API identique (`3b54…`, conteneur recréé), web `b35dcd6` signé (`1229…`) au lieu du build local `42ba…` (même commit).
- Échec : `FAIL: business smoke: MF_SMOKE_WORKSPACE missing from credentials file` ; pas de `ROLLBACK OK`, contrôles postérieurs non exécutés par le script.
- Vérification manuelle immédiate : même conteneur PostgreSQL (`b3943b56cef2…`, 0 redémarrage), révision `0076`, volume de messagerie, réseaux `edge` + `minefleet_default`, port `127.0.0.1:8200`, basemap `rw=false`, rootfs web en lecture seule, `cap_drop ALL`, deux PMTiles servis, timers actifs.
- Impact : aucun sur les données ni le schéma ; le web tourne sur une construction signée du même commit.
- Correctif : contenu du fichier de smoke contrôlé **avant** toute mutation ; `apply` exécute le smoke métier sur la version en service avant la sauvegarde.

**Release `aab109e` non appliquée** à la date de ce document.
