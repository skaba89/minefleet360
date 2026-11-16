# Release staging 0.1.0-rc.2 — 16 novembre 2026 — phase A sans échec

- **Approbation** : propriétaire du projet, 2026-11-16 (« rc.2 sur staging »).
- **Release** : `v0.1.0-rc.2` = `main@4b953ee` (phase 3 hors ligne #457–#459, supervision #452–#456).
  Images GHCR signées (Cosign keyless + SLSA, run `43904322909`) — api `sha256:e3bd4485…fde8756b`,
  web `sha256:89094e42…26505852ee` ; labels vérifiés (révision `4b953ee`, Alembic `0067`).
- **Rollback** : rc.1 (`5dfe305`), stratégie `application-only-forward-schema`. Aucune migration.

## Apply (2026-11-16 16:11:32Z → 16:11:59Z, depuis `/opt/minefleet/infra/deploy`)

`PLAN OK` puis `RELEASE OK` : sonde préalable 200, sauvegarde locale fraîche, révision base = têtes Alembic,
`api`/`web` recréés, attente de disponibilité (#450) puis sondes 200, reçu écrit. Les trois conteneurs dépendent
désormais de `/opt` (consolidation ST-08 terminée). Le répertoire des sauvegardes est resté en
`ubuntu:minefleet-monitor 750` après le `backup.sh` de la release (**ST-12 confirmé sur l'hôte**).

## Phase A rejouée (16:12:08Z, rapport brut hors dépôt, SHA256 `23330890e7031cf9…`)

| Contrôle | Résultat |
|---|---|
| A1 versions, A2 schéma (`0067` = `0067`, aucun conteneur ni image créé), A4 (`A4 verdict : OK`), A5 HTTPS, A7 surface | **OK** |
| A8 santé : PostgreSQL, fraîcheur des sauvegardes, **tâches planifiées**, API HTTPS | **OK** (première fois) |
| A3 cosign / A6 comptes + MFA | SKIP (cosign absent de l'hôte ; A6 manuelle) |
| **Synthèse** | **Échecs : 0** · SKIP : 2 |

Moniteur exécuté sous son compte de service : `failures: 0`. Timer du moniteur toujours désactivé (ST-13 : SMTP).

## Constats ouverts

ST-05 (`cosign` sur l'hôte), ST-09 (copie hors machine), ST-10 (relève SLO GPS — jeton), ST-13 (SMTP), A6 (manuelle).
ST-07, ST-08, ST-11, ST-12 : **levés**.

## Effet sur le GO/NO-GO

Rang 1 (phases A/B) : phase B `PLAN OK` et phase A **sans échec** ; seule A6 (manuelle, comptes du coffre + MFA)
empêche de le déclarer levé. Aucun autre blocant levé. Score et verdict inchangés.
