# Guide d'utilisation de la démonstration

## Pour l'exploitant (préparer une démo)

Prérequis : une **base dédiée** à la démonstration (aucun vrai client), migrations à jour, un PLATFORM_ADMIN
créé (`minefleet create-platform-admin`). Les commandes sont refusées sur toute autre base.

```
minefleet demo seed --profile small --seed 42 --credentials-out /srv/demo/comptes-demo.tsv
minefleet demo verify
```

Le fichier d'identifiants (mode 600) contient, par ligne : société, rôle, site, e-mail, mot de passe.
Le transmettre par un canal sûr, puis le supprimer. Mot de passe perdu :

```
minefleet demo reset-credentials --tenant demo-bauxite --credentials-out /srv/demo/comptes-bauxite.tsv
```

Pendant une présentation, pour voir des camions « En mouvement » sur la flotte GPS (à lancer à côté de l'API,
par exemple dans son conteneur ; Ctrl+C pour arrêter) :

```
minefleet demo live-feed --api-url http://127.0.0.1:8000 --interval 15 --duration 60
```

## Pour le testeur (se connecter)

1. Ouvrir l'URL de l'instance de démonstration.
2. Espace : le code de la société (`demo-bauxite`, `demo-or-hg` ou `demo-tlm`).
3. E-mail et mot de passe du fichier d'identifiants.
4. Comptes DIRECTION, OPS_MANAGER, TENANT_ADMIN, HR et FINANCE : si l'instance impose la double authentification,
   scanner le QR code avec une application d'authentification sur téléphone (le lien `otpauth://` ne s'ouvre pas
   dans un navigateur d'ordinateur). Les autres rôles se connectent directement.

| Rôle | E-mail (exemple pour demo-bauxite) | Ce qu'il montre |
|---|---|---|
| TENANT_ADMIN | `admin@demo-bauxite.example.com` | utilisateurs, sites, paramétrage |
| DIRECTION | `direction@…` | vue d'ensemble, indicateurs |
| OPS_MANAGER | `ops-manager@…` | parc, missions, approbations carburant, pesées dégradées |
| DISPATCHER | `dispatcher.boke-mine@…` | affectations et missions du site |
| DRIVER | `driver.boke-mine@…` | droits limités à son compte |
| WORKSHOP_CHIEF / MECHANIC | `workshop-chief@…`, `mechanic.boke-mine@…` | ordres de travail |
| FUEL_MANAGER | `fuel-manager.boke-mine@…` | cuves, distributions |
| HSE | `hse@…` | incidents, actions correctives |
| FINANCE / AUDITOR | `finance@…`, `auditor@…` | coût complet, taux horaire, approbation des achats de carburant ; consultation |
| HR / STOREKEEPER | `hr@…`, `storekeeper@…` | conducteurs ; magasin de pièces et stock de pneus |

Les scénarios guidés sont dans DEMO_SCENARIOS.md. Toutes les personnes, sociétés et opérations sont fictives.
