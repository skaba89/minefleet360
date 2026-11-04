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

## Tranche 2 : cap et replay de trajet

| Élément | Détail |
|---|---|
| Cap (`heading_deg`, migration 0060) | facultatif, de 0 (inclus, nord) à 360 (exclu), sens horaire. Accepté du traceur (`/gps/telemetry`) et du téléphone (cap du navigateur, transmis seulement s'il est mesuré ; il vaut `null` ou `NaN` à l'arrêt). Validé à l'entrée (hors bornes → 422) et dans le contrat interne. Restitué par les dernières positions et par le trajet. **Jamais calculé par l'API** : un point sans cap reste sans cap |
| Démonstration | le traceur simulé joue le rôle du boîtier : il transmet le cap de son propre déplacement entre deux de ses points (rien au premier point, rien à l'arrêt) |
| Carte en direct | flèche orientée selon le cap mesuré, seulement pour un engin en mouvement ; cap et point cardinal dans le libellé accessible (« cap 92° (E) ») |
| Replay (fiche engin, « Historique de trajet ») | carte du trajet mesuré, **coupé aux interruptions du signal** ; partie déjà parcourue en bleu ; arrêts en orange ; lecture et pause, vitesse ×10 à ×1800, curseur temporel ; heure, vitesse et cap de la dernière mesure |
| Honnêteté du replay | marqueur **plein** sur une mesure ; **pointillé** et annoncé « Entre deux mesures : position estimée pour l'animation, non mesurée » pendant la lecture entre deux mesures consécutives ; **gris** et « Signal interrompu » dans un trou de signal (aucun glissement à travers un trou). L'heure de la dernière mesure reste toujours affichée |
| Accès | inchangé : la consultation exige la finalité et reste journalisée (`fleet.gps.track.read`) |

Vérifié en navigateur réel (même montage que la tranche 1, CSP de production, émetteur de démo) : 31 flèches de cap
sur 31 engins en mouvement ; replay d'un camion de démo : statut « Position mesurée » au départ, puis « Entre deux
mesures… » avec le marqueur en pointillés pendant la lecture à ×10.

## Prochaines tranches

1. Push temps réel (SSE) à la place de l'interrogation, avec la latence de bout en bout mesurée.
2. Alertes : vitesse, entrée et sortie de zone, perte de signal.
3. Regroupement des marqueurs proches en vue d'ensemble (au-delà de quelques centaines d'engins).
4. Comparaison de plusieurs engins et export autorisé d'un trajet.
