# MineFleet360 Conducteur — prototype Expo SDK 58

Première application mobile native autonome sous `mobile/expo-app/`.
Elle ne remplace **pas** le site web `/mon-suivi` ni le suivi traceur.

## Fonction disponible

L'écran « Mon suivi GPS » demande une permission **avant-plan** puis effectue
**une seule** lecture GPS lorsque l'utilisateur appuie sur « Tester le GPS de ce téléphone ».
Il affiche le succès du capteur et l'heure du relevé ; il n'affiche, n'envoie,
n'enregistre et ne journalise pas les coordonnées.

Le partage métier est désactivé : aucune session d'utilisateur/vehicule n'est
encore validée, aucune tâche arrière-plan n'est déclarée ou activée et aucun
envoi à l'API MineFleet360 n'est effectué.

## Amorçage sur poste de développement (hors VPS)

Pré-requis : Node.js compatible SDK 58, Android Studio ou Xcode/macOS pour le
build local, ou EAS Build sur un environnement approuvé.

```bash
cd mobile/expo-app
npm install
npx expo install --fix
npx expo install --check
npx expo start --dev-client
```

Après génération de la configuration native, créer un **development build**
pour Android/iOS. Le dépôt ne contient pas de package-lock pour ce nouveau
prototype : la CI principale exécute uniquement les tests du contrat
dans `mobile/tests/`, elle **ne valide pas encore un APK/IPA installable**.
Ne pas déployer ce prototype en production.

## Mesures de sécurité explicites

- `expo-location` est déclaré avec suivi background Android/iOS **désactivé**.
- Aucune collecte périodique ni transmission n'est déclenchée par le prototype.
- Il faudra, avant activation métier, une authentification avec token court,
  un choix de véhicule autorisé, un consentement enregistré côté serveur, une
  tâche native déclarée au niveau global, un coffre local chiffré et une purge
  au retrait de consentement.
- Le futur adaptateur `../src/expoLocationAdapter.mjs` existe mais **n'est pas
  branché à cette application**.
- Tester toute permission d'arrière-plan et la reprise d'activité sur appareils
  physiques Android/iOS, avec les règles de chaque OS.

Documentation SDK : https://docs.expo.dev/versions/v58.0.0/sdk/location/
