# Audit de sécurité — état vérifié

État au 4 novembre 2026, `main@000ee08`. Il complète `AUDIT_SECURITE.md` et les revues de `docs/revues/`, sans
les remplacer.

## Contrôles en place (vérifiés dans le code et la CI)

| Contrôle | Preuve |
|---|---|
| Isolation multi-tenant | RLS **forcée** sur toutes les tables métier, y compris pour le propriétaire ; contexte transactionnel posé par un seul module (`core/tenancy.py`, test d'architecture) ; filtres `tenant_id` explicites en plus |
| Rôle applicatif minimal | `mf_app` sans DELETE ; le secret `mf_owner` est réservé à la tâche de migration |
| Autorisation par objet et par site | `Require(permission)` + `covers_site` avant chaque lecture ou écriture ; 404 hors portée (pas de fuite d'existence) |
| Séparation des tâches | contraintes en base (`ck_msd_four_eyes`, remise en service par une autre personne que le mécanicien, approbation des saisies dégradées) |
| Authentification | jeton d'accès de 15 min, rotation des sessions, MFA obligatoire pour les rôles sensibles (D-41), limitation des échecs de connexion |
| Audit | événement à chaque écriture métier ; accès aux trajets GPS journalisés avec finalité |
| En-têtes HTTP (proxy Caddy) | HSTS, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` |
| Dépendances | `pip-audit` et `npm audit --audit-level=high` bloquants en CI |
| Exports | neutralisation des formules dans les CSV |
| Migrations | downgrades refusés hors local/test/CI ; test statique des reprises de données sous RLS (#334) |

## Écarts

| Priorité | Écart | Risque | Action proposée |
|---|---|---|---|
| ~~P0~~ **corrigé le 4 novembre** | Protection de `main` : seuls `backend` et `frontend` étaient obligatoires. Sur décision du propriétaire, les 5 jobs le sont désormais (`backend`, `frontend`, `tenant-isolation`, `browser-smoke`, `demo-journeys`), vérifié par l'API GitHub. Restent : aucune revue exigée, règles non appliquées aux administrateurs | fusion possible sans revue | revue obligatoire à envisager quand l'équipe comptera plusieurs relecteurs |
| P0 avant production | Hébergement hors Guinée et durées de conservation non validés juridiquement (C-01, C-08, C-09) | non-conformité | avis d'un juriste guinéen (bloquant, déjà noté dans D-41) |
| P1 | Pas de `Content-Security-Policy` | XSS amplifiée si une injection apparaît | CSP stricte (scripts du même domaine), testée sur la recette |
| P1 | Pas de SAST ni de scan de secrets en CI | régression non détectée | `bandit` ou `semgrep` (Python), `gitleaks` ; bloquants sur les nouveaux constats |
| P1 | Limitation de débit limitée aux échecs de connexion | épuisement sous forte charge (mesuré : ~44 req/s avec 2 processus) | limite par session et par IP au proxy, alertes |
| P2 | Pas de DAST | failles d'exécution non vues | ZAP baseline sur la recette, hors données réelles |
| P2 | Pas de traces ni de métriques de sécurité centralisées | détection tardive | journaux structurés vers un collecteur, alertes sur 401/403 anormaux |

## Non vérifié dans cet audit

- Configuration réelle du serveur de recette (pare-feu, mises à jour, accès SSH) : relève de l'exploitation.
- Robustesse des sauvegardes hors machine : la destination n'est pas encore choisie par le client.
- Test d'intrusion externe : aucun réalisé.
