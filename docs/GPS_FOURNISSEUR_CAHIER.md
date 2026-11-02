# Intégration d'un fournisseur de traceurs GPS — éléments à obtenir

Décision déléguée D-DEL-06 (2 novembre 2026) : **aucun adaptateur n'est développé sans la spécification réelle du
fournisseur** (format, authentification, horodatage). Un adaptateur écrit « à l'aveugle » produirait des positions
fausses ou mal datées, ce qui est pire qu'une absence de donnée. Ce document liste ce qu'il faut demander.

## Point d'entrée existant

Les traceurs peuvent déjà envoyer leurs positions à `POST /api/v1/gps/telemetry` (JSON HTTPS, secret par traceur,
révocable, numéro de séquence anti-rejeu ; voir `docs/GPS_INGESTION_BOUNDARY.md`). Si le fournisseur sait **pousser**
ce format (ou un webhook configurable), aucune intégration spécifique n'est nécessaire.

## À obtenir du fournisseur (par écrit)

| Sujet | Questions |
|---|---|
| Mode | Poussée (webhook) ou interrogation de leur API ? Fréquence et volume par traceur ? |
| Format | Schéma exact des messages (champs, unités : degrés décimaux, km/h, mètres), exemples réels anonymisés |
| Horodatage | Heure GNSS ou heure de réception ? Fuseau ? Résolution ? Comportement quand le GPS n'a pas de fix |
| Identité | Identifiant stable du boîtier (IMEI, numéro de série) ; remplacement d'un boîtier |
| Authentification | Secret partagé, signature HMAC, certificat client, liste d'adresses IP sources ? Rotation des secrets |
| Fiabilité | Rejeu des messages après coupure (stockage embarqué) ? Ordre garanti ? Doublons possibles ? |
| Qualité | Précision (HDOP, nombre de satellites), vitesse, cap, état du moteur / contact, compteur kilométrique |
| Événements | Alertes natives (choc, sortie de zone, batterie) : format et sémantique |
| Contrat | Hébergement des données chez le fournisseur, durée de conservation, sous-traitance, réversibilité |
| Environnement de test | Accès à un bac à sable ou à un boîtier de test, avec messages réels |

## Critères d'acceptation de l'adaptateur (quand la spécification sera fournie)

1. Test d'intégration avec des messages réels du bac à sable (format, unités, horodatage, absence de fix).
2. Authentification vérifiée avant toute écriture ; refus journalisé ; secret révocable.
3. Rejeu idempotent (doublons et messages tardifs replacés à leur heure, sans fausse alerte de zone).
4. Isolation par société et par site ; aucun secret du fournisseur dans le dépôt.
5. Essai de charge au volume annoncé et essai terrain sur un engin réel.
