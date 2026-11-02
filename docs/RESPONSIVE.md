# Interface responsive (téléphone, tablette, poste)

Mis à jour le 2 novembre 2026. Règles appliquées par `frontend/src/styles.css` et **vérifiées automatiquement** par
`frontend/e2e/responsive.spec.ts` (workflow `e2e-isolation`).

## Formats contrôlés

| Format | Largeur | Contrôles |
|---|---|---|
| Téléphone d'entrée de gamme | 360 px | pas de défilement horizontal de la page ; aucun élément interactif hors écran ; commandes, champs et liens de menu ≥ 44 px ; champs en 16 px (pas de zoom automatique iOS) |
| Tablette | 768 px | pas de défilement horizontal de la page ; aucun élément interactif hors écran |

Écrans couverts : 31 routes (exploitation, HSE, administration, finance), menu déplié, 6 formulaires ouverts
(déclaration d'incident, inspection, panne, modèle de checklist, zone GPS, site) et 5 fiches détaillées.

## Règles de mise en page (≤ 700 px)

- Cibles tactiles d'au moins **44 px** (usage terrain, éventuellement avec des gants), y compris pagination,
  « Se déconnecter » et boutons de menu.
- Champs en **16 px** ; cases à cocher agrandies (22 px).
- Formulaires sur une colonne, boutons d'action en pleine largeur.
- Tableaux : défilement horizontal **dans leur cadre**, ombre indiquant le contenu masqué, **première colonne
  figée** (identifiant de la ligne toujours visible).
- Tableaux structurellement larges (grilles de cases à cocher) : classe `.table-scroll` à toutes les largeurs.

## Reste à faire

- Essai sur appareils réels (Android d'entrée de gamme, plein soleil, gants) : la validation est automatisée et
  émulée.
- Vue « cartes » pour les listes les plus consultées sur le terrain si les essais montrent que le défilement
  horizontal gêne.
