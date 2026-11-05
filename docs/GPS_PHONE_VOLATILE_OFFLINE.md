# GPS téléphone — tampon provisoire en mémoire (réseau intermittent)

Cette tranche répond aux pertes brèves de connectivité lorsque le conducteur garde explicitement sa page « Mon partage GPS » ouverte et a accepté le suivi.

## Fonctionnement et limites

- Chaque relevé valide est placé en **mémoire JavaScript uniquement**, pas en IndexedDB, localStorage ni service worker.
- La file conserve **12 positions maximum**, uniquement des positions enregistrées depuis moins de **100 secondes** (marge sous la fenêtre serveur de 2 minutes).
- La file est triée par `recorded_at`. Quand le réseau revient, **un seul point est envoyé à chaque cycle d'environ 10 secondes**, afin de respecter la limite serveur de 5 secondes entre insertions. Un envoi HTTP confirmé retire son point.
- Les points périmés, invalides et déjà présents sont ignorés ; un conflit HTTP 409 ne déclenche pas de rejeu infini.
- L'arrêt explicite, la fermeture de la page et le démarrage d'un nouveau partage purgent le tampon.
- Une révocation de session ou une interdiction (401, 403, 404) arrête la collecte ; aucune donnée n'est envoyée avec une autre session.
- L'absence d'accusé de réception peut créer un doublon : l'API valide les horodatages et refuse les doublons/conflits. Ce tampon ne garantit pas une livraison exactement une fois.

## Garanties et limitations honnêtes

La mémoire du navigateur **n'est pas un stockage fiable** : verrouillage de l'écran, rechargement, fermeture d'onglet ou suspension par le système peuvent perdre tous les points. En cas de panne réseau longue, les anciens points sont abandonnés. La détection `navigator.onLine` ne prouve pas que l'API est joignable ; les erreurs réseau restent possibles.

Ce n'est **pas** un GPS professionnel en arrière-plan, ni une synchronisation persistante chiffrée. Le déploiement de véritables traces GPS offline durables nécessite une conception séparée, explicite et testée (consentement, chiffrement local, suppression sur déconnexion, sécurité multi-compte, politique RGPD, quotas, rattrapage/idempotence).

## Vérification

- `src/lib/phoneGpsMemoryBuffer.test.ts` : plafond, ordre, expiration, validation et purge.
- `src/pages/PhoneTrackingPage.test.tsx` : acquisition temporaire sans envoi hors ligne et arrêt.
- Tests serveur existants : contrôle des sessions, du périmètre, des horodatages, doublons et fréquence des envois.

Aucune modification du modèle SQL ou des autorisations, aucun changement de déploiement production.
