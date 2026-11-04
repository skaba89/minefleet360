# Carte GPS temps réel des engins

État au 4 novembre 2026 : première tranche du chantier P0 « GPS temps réel » (`docs/ROADMAP_2026_2027.md`).

## Ce qui est livré

| Élément | Détail |
|---|---|
| Carte interactive (page « Flotte GPS ») | MapLibre GL 6.15 (licence BSD), à la place du schéma SVG et de l'iframe OpenStreetMap (qui envoyait la position consultée à un serveur tiers) |
| Engins | un marqueur par engin, à sa **dernière position mesurée** ; couleur selon l'état du signal (en mouvement, à l'arrêt, vitesse inconnue, signal ancien), identique à la liste ; points compacts en vue d'ensemble, étiquette au zoom 11 et plus, au survol, au focus et pour l'engin sélectionné |
| Accessibilité | chaque marqueur est un vrai bouton dont le libellé donne l'engin, l'état, la vitesse et l'heure de mesure ; cible de 24 px ; animations désactivées si l'utilisateur réduit les mouvements |
| Mouvement | actualisation toutes les 15 s (comme avant). Entre deux mesures, le marqueur **glisse** visuellement en 0,8 s puis s'arrête exactement sur la nouvelle mesure. Aucune position intermédiaire n'est enregistrée ni présentée comme mesurée ; l'heure affichée est toujours celle de la mesure |
| Positions invalides | latitude ou longitude hors bornes : engin non placé sur la carte (il reste dans la liste) |
| Zones | géofences actives des sites (permission `fleet.geofence.read`) |
| Sans WebGL | message explicite ; la liste et le tableau restent à jour |

## Fond de carte auto-hébergé (décision du 4 novembre 2026)

- Fichier `guinee.pmtiles` : extrait OpenStreetMap de la Guinée (données sous licence ODbL, attribution affichée),
  produit par `scripts/basemap/build-guinee.sh` à partir du build quotidien de Protomaps (lecture par plages : seule
  la zone de la Guinée est téléchargée).
- Servi par le conteneur web sous `/basemap/` (volume `MF_BASEMAP_DIR` monté en lecture seule, cache d'un jour,
  requêtes Range natives de Caddy). **Aucune requête de carte ne part vers un tiers.**
- Sans le fichier (développement, CI, serveur pas encore équipé) : fond neutre avec les zones des sites, et la
  mention « Fond de carte non installé sur ce serveur ».
- Les couches de texte du fond (noms de lieux) sont écartées pour l'instant : elles exigeraient d'héberger aussi des
  polices. Les engins sont étiquetés par des marqueurs HTML.
- **Reste à faire par l'exploitant** : installer l'outil `pmtiles` (somme de contrôle vérifiée) et lancer le
  script. L'exécution de cet outil n'a pas été autorisée dans la session de développement : le rendu avec le fond
  réel **n'a donc pas encore été vérifié**.

## Sécurité

- CSP du conteneur web : `worker-src 'self'` (le worker MapLibre est servi depuis l'application, sans `blob:`),
  `img-src` complété de `blob:`, `frame-src 'none'` (plus aucune iframe externe).
- Aucune nouvelle route d'API ; mêmes permissions qu'avant (`fleet.vehicle.read` pour la page, `fleet.geofence.read`
  pour les zones), isolation par société et par site inchangée.

## Vérifications

- Vitest : `FleetMap.test.tsx` (position mesurée, libellé accessible, déplacement sur la nouvelle mesure, position
  invalide ignorée, engin retiré, sélection, zones, fond présent ou absent) et `basemap.test.ts` (détection du
  fichier, style sans couche de texte).
- Navigateur réel (Chromium, image Playwright) : interface construite et servie par Caddy **avec la CSP de
  production**, API locale sur le jeu de démo `large` (demo-bauxite) et émetteur GPS simulé. Résultat : 48 engins
  affichés ; 12 à 14 marqueurs déplacés en 22 s ; rendu WebGL actif ; **aucune violation de CSP** ; aucun
  défilement horizontal à 360 px. Les seules erreurs de console attendues : 401 (tentative de rafraîchissement de
  session avant connexion) et 404 (fond de carte absent).

## Prochaines tranches

1. Cap et direction (stocker le cap envoyé par le boîtier ; ne jamais le calculer et le présenter comme mesuré).
2. Replay d'un trajet sur la carte (lecture, pause, vitesse ×1 à ×16, arrêts et trous de signal visibles).
3. Push temps réel (SSE) à la place de l'interrogation, avec la latence de bout en bout mesurée.
4. Alertes : vitesse, entrée et sortie de zone, perte de signal.
5. Regroupement des marqueurs proches en vue d'ensemble (au-delà de quelques centaines d'engins).
