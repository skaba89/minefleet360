# MineFleet360 Mobile — premier lot de sécurité du GPS natif

Cette arborescence prépare une **application compagnon Android/iOS distincte**.
Elle ne contient **pas encore** d'application installable, de tâche de localisation
native, de transmission réseau ni de stockage local : aucune collecte n'est activée.

Le contrôleur pur `src/backgroundGpsGate.mjs` impose un blocage par défaut avant
chaque future acquisition GPS et chaque envoi. La CI du frontend vérifie sa
politique par `node --test ../mobile/tests/*.test.mjs`.

## Trois décisions explicites

- `allow` : consentement, authentification, véhicule autorisé, session valide,
  permissions de localisation avant-plan/arrière-plan, et réseau disponible ;
  **le code ne collecte pas de point**.
- `suspend` : absence de réseau ; dans ce premier lot, suspendre la collecte
  (aucun coffre-fort chiffré natif encore installé). Une éventuelle file antérieure
  n'est pas purgée automatiquement à cause d'une seule panne réseau.
- `stop` : révocation, absence de consentement ou de permission, expiration,
  désactivation du partage ou perte d'autorisation. Le futur adaptateur natif
  devra arrêter sa tâche et effacer la file chiffrée.

La validité du partage et les permissions doivent être recontrôlées lors de la
reconnexion ; le résultat local ne constitue **jamais** une autorisation serveur.

## Prochains incréments sans casser le partage web existant

1. Créer une véritable application React Native / Expo, avec écran de consentement
   explicite, connexion sécurisée, sélection de véhicule et démarrage/arrêt manuel.
2. Définir une tâche native de localisation au niveau global de l'application,
   à permissions OS vérifiées, et une notification Android de collecte en cours.
   Pour iOS, activer uniquement le mode de fond réellement nécessaire.
3. Brancher les données sur le partage GPS existant avec authentification de
   compte, et vérifier les statuts d'acceptation. Aucun secret GPS global dans
   le binaire ou les journaux.
4. Ajouter un stockage chiffré borné, avec session, expiration, révocation et
   rejeu idempotent du contrat différé existant. N'activer que si le backend
   correspondant est disponible et autorisé.
5. Tester sur de vrais Android/iPhone : écran verrouillé, permissions révoquées,
   expiration, changement de conducteur/site/tenant, perte réseau, batterie,
   reprise, arrêt explicite et protection des données.

Références internes :
`docs/GPS_BACKGROUND_TRACKING_ARCHITECTURE.md`,
`backend/app/fleet/gps_deferred_contract.py`,
`frontend/src/lib/phoneGpsDeferredProtocol.ts`.

Le GPS de la page web et les traceurs physiques continuent à fonctionner
indépendamment de ce prototype. Aucune migration ni déploiement VPS ne sont requis.
