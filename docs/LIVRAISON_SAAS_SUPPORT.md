# Livraison — lot 4 commercialisation SaaS : support, onboarding, réversibilité

> Date : 2026-11-12. Branche : `feature/saas-lot4-support`. Base : `main` après le lot 2b (PR #422).

## Contenu

Le lot 4 clôt les 4 lots de commercialisation : il dote la plateforme de son **outillage
support**, la société d'un **parcours de démarrage guidé** et les deux parties d'une
**réversibilité contractuelle**. Aucune migration de base de données (tout est calculé à la
lecture, zéro changement de schéma, zéro perte possible).

### 1. Outillage support — `GET /platform/tenants/{tenant_id}/overview`

Vue consolidée d'exploitation d'un compte client, calculée à la lecture, réservée à
`PLATFORM_ADMIN` (nouvelle permission `organization.tenant.support`) :

- **Société** : nom, code, statut (ACTIVE/SUSPENDED).
- **Abonnement courant** (le plus récent) : plan, statut stocké et **statut effectif**
  (un essai daté échu s'affiche « Essai expiré » sans écrire en base — règle du lot 3),
  fin de période.
- **Usage réel face aux limites du plan** : utilisateurs, sites, véhicules, traceurs GPS
  (mêmes compteurs que l'application des quotas du lot 2b — `usage_counts`) ; `NULL` =
  illimité.
- **Comptes utilisateurs** : actifs / en attente d'invitation / désactivés.
- **5 dernières factures** : numéro, statut, total GNF.

UI `/plateforme/support` (menu « Support société ») : choix de la société, affichage
consolidé. Lecture pure : aucun audit, aucune écriture.

### 2. Parcours client guidé — `GET /tenant/onboarding`

Checklist de démarrage de la société, **calculée depuis l'état réel** (aucun état à
maintenir en base, rien à cocher manuellement) :

| Étape | Objectif | Source |
|---|---|---|
| Essai ou abonnement actif | ≥ 1 abonnement vivant (TRIAL/ACTIVE/SUSPENDED) | `tenant_subscription` |
| Votre équipe est invitée | ≥ 2 utilisateurs actifs | compteur quotas `max_users` |
| Vos sites sont créés | ≥ 1 site | compteur quotas `max_sites` |
| Votre flotte est enregistrée | ≥ 1 véhicule non réformé | compteur quotas `max_vehicles` |
| Vos véhicules sont équipés | ≥ 1 traceur GPS lié | compteur quotas `max_gps_trackers` |

Réponse : étapes (`key`, libellé, aide, count/target, done), `done_count`, `total`,
`progress_percent`. Rattachée à la permission existante `organization.tenant.read`
(tous les rôles tenant la consultent — compteurs agrégés de leur propre société, RLS).
UI `/demarrage` (menu « Démarrage ») : barre de progression (`role=progressbar`), étapes
cochées automatiquement.

### 3. Réversibilité — `GET /tenant/export`

Export JSON des données de la société, réservé à `TENANT_ADMIN`
(nouvelle permission `organization.tenant.export`, **journalisé** `tenant.export`) :

- Sections : `tenant`, `sites`, `users` (email, nom, statut, rôles actifs),
  `vehicles`, `subscriptions`, `invoices` (+ lignes).
- `format_version: 1` et `exported_at` pour la traçabilité du format.
- **Aucun secret** : jamais de hachage de mot de passe, de secret/chiffre MFA, de codes de
  récupération ni de jeton ; comptes anonymisés exclus.
- Téléchargement authentifié (`Content-Disposition: attachment`, nom
  `export-minefleet-<code>-<AAAAMMJJ>.json`) — bouton « Exporter les données (JSON) »
  dans la section Réversibilité de la page `/abonnement`.

## Permissions et routes

- 2 permissions nouvelles (`organization.tenant.support`, `organization.tenant.export`),
  1 route ajoutée à `organization.tenant.read` (`/tenant/onboarding`) → **127 permissions /
  255 routes** au total (référence `main` après lot 2b : 125 / 252).
- Matrice `authz_matrix.yaml`, `MATRICE_RBAC.md` §2.1 et générateurs anti-dérive à jour.

## Vérifications exécutées

- Backend : ruff + format + **mypy strict** propres ; **9 tests pytest dédiés**
  (`tests/test_organization_support.py` : vue support avec quotas et statut effectif d'essai
  échu via antidatage, société inconnue 404, refus TENANT_ADMIN sur la route plateforme,
  progression d'onboarding 20 % → 100 % après actions réelles, lecture par DIRECTION,
  export complet sans aucun attribut d'authentification, journalisation via
  `/audit-events`, refus DIRECTION sur l'export) ; suites connexes vertes
  (matrice RBAC/isolation, database, billing lots 1-3).
- Frontend : `tsc --noEmit` OK ; **4 tests Vitest dédiés** (checklist et refus d'accès,
  vue support consolidée et refus d'accès) ; suite complète **260 tests** ; build OK ;
  `schema.d.ts` et permissions générées régénérés.

## Non fait / suite

- Suivi de règlement (« payé ») et export PDF de facture : après arbitrage expert-comptable
  (série par société), reste hors lots (décision du 11 novembre).
- L'export couvre les domaines cœur (organisation, flotte, abonnement, facturation) ; les
  domaines opérationnels détaillés (missions, pesées, HSE…) restent exportables via
  l'API/CSV existants — un export « tout domaine » complet est une évolution, pas un
  prérequis GO/NO-GO.
- La réactivation d'un essai expiré reste une décision plateforme (`activate`), aucune
  automatique.
