# MINEFLEET 360 — interface web

React + TypeScript (Vite), entièrement en français. L'API est servie sous la même origine (proxy Vite en
développement) : le jeton d'accès reste en mémoire, le rafraîchissement passe par un cookie httpOnly
(ADR-003). Aucune donnée n'est stockée dans le navigateur.

## Prérequis
- Node.js ≥ 20.19 (Node 22 LTS recommandé : Node 20 n'est plus maintenu depuis avril 2026 ; la CI utilise 22).
- La pile locale lancée (`scripts/dev-up.ps1`) : API sur `http://localhost:8000`, `MF_ALLOWED_ORIGINS=http://localhost:5173`.

## Commandes
| Commande | Rôle |
|---|---|
| `npm ci` | Installation (versions exactes, `package-lock.json`) |
| `npm run dev` | Serveur de développement sur `http://localhost:5173` |
| `npm run typecheck` | Vérification TypeScript stricte |
| `npm test` | Tests unitaires Vitest (fuseaux, droits d'affichage, connexion) |
| `npm run build` | Typage puis build de production dans `dist/` |
| `npm run gen:api` | Régénère `src/api/schema.d.ts` depuis l'OpenAPI de l'API locale |
| `npm run e2e` | Tests de bout en bout Playwright (voir ci-dessous) |

## Tests de bout en bout
Ils pilotent un vrai navigateur contre l'API locale et créent leurs propres données fictives.
1. Base de développement chargée une fois : `minefleet create-platform-admin` puis
   `minefleet seed-fictif > <fichier hors dépôt>` (sortie = comptes fictifs et mots de passe).
2. `npx playwright install chromium` (première fois).
3. `MF_E2E_ACCOUNTS=<fichier> npm run e2e`.

Parcours couverts : un dispatcher affecte un conducteur puis clôture ; refus d'une affectation inéligible
avec motifs en français ; un utilisateur d'une autre société ne voit rien (UI et API 404).

## Règles
- Libellés français dans `src/lib/labels.ts` ; codes anglais côté API (D-01).
- Dates : UTC dans les échanges, affichage et saisie au fuseau du site (`src/lib/time.ts`, D-23).
- `src/lib/permissions.ts` masque seulement les actions vouées au refus ; le serveur reste seul juge.
  À tenir alignée sur `backend/app/authz/authz_matrix.yaml`.
