# Fonds cartographiques multi-régions — Guinée + France (optionnel)

Le GPS ne modifie ni les coordonnées des véhicules ni les autorisations. Le fond de carte est constitué exclusivement de PMTiles auto-hébergés. Une position située en Île-de-France ne peut pas afficher de routes si seul `guinee.pmtiles` est installé.

## Fonctionnement
- `/basemap/guinee.pmtiles` et `/basemap/france.pmtiles` sont vérifiés séparément (HEAD).
- Le style MapLibre ajoute une source vectorielle par archive disponible et préfixe les identifiants de couches pour éviter les collisions.
- La carte conserve un fond gris neutre en dehors des régions installées.
- Les marqueurs restent liés aux positions GPS réelles ; le choix de l'archive n'altère pas les coordonnées ni les statuts.
- Aucun appel à un service cartographique tiers lors de l'affichage.
- Les noms de ville/route sont temporairement masqués, faute de glyphes auto-hébergés.

## Préparer la France sur le serveur, après validation et déploiement du frontend
```bash
cd /opt/minefleet
export PATH="$HOME/.local/bin:$PATH"
df -h /opt/minefleet
# L'extraction France peut consommer beaucoup plus de disque que la Guinée.
bash scripts/basemap/build-france.sh /opt/minefleet/infra/deploy/basemap
pmtiles verify /opt/minefleet/infra/deploy/basemap/france.pmtiles
docker exec minefleet-web-1 ls -lh /srv/basemap/france.pmtiles
curl -sSI https://minefleet.51-75-248-4.sslip.io/basemap/france.pmtiles
```
Aucune action automatique sur le VPS. Le montage `MF_BASEMAP_DIR` existant est réutilisé. La Guinée ne doit pas être effacée. Le navigateur devra rafraîchir la page après ajout de l'archive.

## Validation nécessaire
- CI Vitest, TypeScript et sécurité.
- Test réel navigateur avec 2 archives PMTiles, France et Guinée ; image de la région parisienne et du site guinéen.
- Vérifier Range HTTP 206 et aucune erreur MapLibre/PMTiles dans les consoles.
- Vérifier le comportement lorsqu'une des deux archives est absente ou contient des métadonnées invalides.
- Pour une flotte internationale, envisager ensuite un catalogue configurable de pays et une couverture vérifiée selon l'emprise réelle de chaque archive.
