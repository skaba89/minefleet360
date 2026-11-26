# Plan de cutover VPS — staging (4 étapes, étape ④ verrouillée)

**Date de rédaction : 2026-11-26 · Base : main `82b4ca9` (#542)** · Statut : **en attente d'approbation humaine**
**Objet** : exécuter sur l'hôte staging OVH réel ce qui est prouvé uniquement sur base candidate locale (itération #532-#534 : compare fresh/bootstrapped PASS, admin-check 14 contrôles PASS le 26 nov), puis livrer rc.7 (pesage offline) en recette. Rien de ce document ne touche une production — elle n'existe pas (verdict NO-GO commercial).

**Références à lire avant exécution** : `docs/ops/STAGING_RESET.md` et `STAGING_RESET_PHASE1.md` (scripts), `docs/ops/GPS_STAGING_READONLY_INVENTORY.md` (inventaire lecture seule #533, déjà fait), `docs/ops/ROTATION_SECRETS.md` (secrets), `docs/STAGING_RELEASE_ROLLBACK.md` (retour arrière release), `docs/DEPLOIEMENT_OVH.md` §4 (journalisation) et §8 (copie hors machine).

**Préconditions (toutes obligatoires, vérifier avant l'étape ①)** :

1. **Approbation explicite de l'humain** pour les étapes ①-③ — donnée une fois pour ce plan, référencée dans le journal ;
2. Accès SSH VPS + Docker fonctionnel (`docker compose version`) ;
3. Secrets à jour (rotation vérifiée, `ROTATION_SECRETS.md`) ;
4. Sauvegarde de la base staging fraîche (< 24 h) **et** copiée hors machine (sinon l'étape ① la produit) ;
5. Fenêtre horaire sans recette planifiée ; annonce de la fenêtre dans le journal.

**Critères d'interruption immédiate** (à tout moment, comme `PLAN_EXECUTION_STAGING.md` §4) : tout `compare` PASS→FAIL, tout admin-check < 14/14, toute fuite de secret dans le journal, toute dégradation de la santé rc en service hors fenêtre, toute commande dont la sortie n'est pas comprise avant exécution.

## Étape ① — Cliché et filet de sécurité (~30 min)

1. Noter l'état courant : `docker compose ps`, digests des images en service, `alembic current` côté db (attendu 0072 sur rc.6).
2. Sauvegarde complète de la base staging (`pg_dump -Fc`) + **copie hors machine immédiate** (R1 partiel : premier pas utile même avant le coffre définitif) + checksum enregistré au journal.
3. Marquer les images signées en service (digests) pour un rollback instantané sans rebuild (`STAGING_RELEASE_ROLLBACK.md`).

**Sortie attendue** : dossier daté (cliché SQL + digests + checksums). *Si cette étape échoue : STOP, ne pas passer à ②.*

## Étape ② — build-candidate réel (~45 min)

1. Exécuter `staging-reset.sh build-candidate` : projet Compose **isolé** (préfixe dédié) + volume de données **neuf**, migrations seules (aucune donnée).
2. `staging-reset.py compare --phase fresh` : **PASS exigé** (catalogue structurel identique à la référence, 0 constat).

**Sortie attendue** : candidate neuve au schéma courant, compare fresh PASS au journal. *Échec : STOP, détruire le projet Compose isolé (aucun impact sur la rc en service), diagnostiquer hors hôte.*

## Étape ③ — Bootstrap et contrôles (~30 min)

1. `create-platform-admin` sur la candidate (TOTP réel) ;
2. `staging-reset-admin-check.py` : **14/14 contrôles PASS exigés** (refus 401, enrôlement, montée MFA, 403 route métier pour l'admin plateforme, logout, révocation) ;
3. `staging-reset.py compare --phase bootstrapped` : **PASS exigé** (13 tables référentiels + bootstrap uniquement).

**Sortie attendue** : la preuve #532-#534 reproductible sur l'hôte réel, journalisée. *À ce point, l'agent rend compte et s'arrête : l'étape ④ exige l'approbation dédiée du §4 ci-dessous.*

## Étape ④ — Cutover + bascule rc.7 — **VERROUILLÉE**

> **Cette étape ne s'exécute JAMAIS sans une approbation explicite, fraîche et séparée de l'humain, donnée APRÈS la revue du journal ①-③.** L'approbation des étapes ①-③ ne vaut pas pour ④.

1. **Checklist avant bascule** (tout doit être OUI) :
   - [ ] journal ①-③ complet et revu ;
   - [ ] étape ① fraîche (< 24 h) : cliché + copie hors machine vérifiée ;
   - [ ] `rollback-cutover` répété à blanc (dry-run) et prêt ;
   - [ ] fenêtre horaire confirmée + annonce ;
   - [ ] contenu rc.7 identifié (diff `main@f888194` → `82b4ca9` : fuel offline #541, pesage offline #542, dependabot #535/#537-#539/#540 — pas de migration hors 0072→0077 confirmée par `alembic heads`) ;
   - [ ] CI du head cible 9/9 verte (re-vérifier le run e2e du head avant bascule — flake Android documenté).
2. Bascule : `staging-reset.sh cutover` puis déploiement rc.7 (pipeline `release-images`, images signées avec reçu).
3. Recette post-bascule : santé 200×3, `alembic current` = 0077, smoke offline pesage (créer un ticket en recette via l'interface, vérifier `Idempotency-Replayed` sur un second envoi), moniteur systemd relancé.
4. **Retour arrière** : à la moindre anomalie de la checklist 3 — `staging-reset.sh rollback-cutover` puis retour aux digests marqués en ① (`STAGING_RELEASE_ROLLBACK.md`) ; l'incident est journalisé, aucune nouvelle tentative dans la même fenêtre.

## Journalisation et sortie de session

- Chaque commande exécutée, sa sortie utile, et tout écart sont consignés dans un dossier daté (`work/ops-vps-<date>/` côté agent, copie dans la continuité) — jamais de secret en clair (masquage systématique).
- Critères de sortie : ①-③ PASS journalisés → compte rendu + demande d'approbation ④ ; ④ exécutée → rc.7 en recette + mise à jour de `MINEFLEET360_PROGRESS.md` (§10) et re-classification des lignes 11/12/16/18 de `docs/audit/AUDIT_PHASE_ZERO_2026-11-26.md`.
- Session suivante (après ④ réussi) : installer les timers ST-07 (ligne 13), première exécution R1 complète (ligne 15), A3 cosign + A6 lecture seule (lignes 11-12).
