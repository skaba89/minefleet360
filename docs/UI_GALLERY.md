# Captures des interfaces MineFleet360

Ce parcours produit **des captures réelles de l'application** ; il ne fabrique pas de maquettes. Il est réservé à la pile de développement locale et aux données `seed-fictif`. Ne jamais lancer avec des comptes réels ni publier les images sans vérification.

## Prérequis

1. Démarrer l'API PostgreSQL de développement et le frontend comme indiqué dans `frontend/README.md`.
2. Créer des données fictives avec `minefleet seed-fictif` et conserver la sortie des comptes dans un fichier **hors du dépôt**.
3. Installer les dépendances frontend : `npm ci`, puis `npx playwright install chromium`.

## Générer la galerie

Depuis `frontend/`, PowerShell :

```powershell
$env:MF_E2E_ACCOUNTS = "C:\\chemin-prive\\comptes-fictifs.txt"
$env:MF_UI_GALLERY = "1"
npm run e2e -- ui-gallery.spec.ts
```

Les images et la galerie HTML `index.html` sont créées localement dans `frontend/artifacts/ui-gallery/` (ignoré par Git). Elles couvrent accueil, véhicules, conducteurs, affectations, missions, GPS, atelier, maintenance, carburant, pièces, juridique, pesées et indicateurs. La capture ne démontre pas à elle seule qu'un parcours métier fonctionne entièrement. Vérifier les pages selon les rôles et tester les actions par Playwright.

**Sécurité :** la configuration Playwright interdit les URL d'API non locales ; le test refuse les espaces autres que `fictif-*`. Aucune capture n'est produite par la CI normale, car `MF_UI_GALLERY` doit être activé explicitement. Ne jamais commiter les captures, les comptes ou les jetons.
