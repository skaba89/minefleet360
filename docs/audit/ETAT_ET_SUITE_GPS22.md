# Analyse ciblée et suite GPS-22 — 29 octobre 2026

Base inspectée : `936fe801f44e363397f1bd47f6aeed0f9520323d` (fusion PR #95).
Cette revue porte sur l'inventaire du dépôt, les routes et écrans principaux,
la chaîne GPS, la CI et les procédures de déploiement/sauvegarde. Elle ne
constitue ni un audit exhaustif de sécurité ni une validation du VPS déployé.

## État constaté dans le code

| Parcours | Éléments présents | Limite constatée |
| --- | --- | --- |
| Socle | Modules identity, organization, authz et audit ; vérification au démarrage du rôle PostgreSQL ; RBAC et contexte multi-tenant | La CI apporte des preuves automatisées, pas une qualification de production |
| Flotte et personnel | Routes et écrans véhicules, catégories, conducteurs, documents, affectations | Recette de bout en bout à poursuivre sur les rôles et sites réels autorisés |
| Exploitation | Missions, événements, pesées, indicateurs et écrans associés | GPS distinct de la preuve de tonnage |
| Atelier | Cycle OT, plans, échéances, programmation et API de finalisation préventive | La fiche `WorkshopPages.tsx` ne raccorde pas encore la finalisation préventive |
| GPS | Lecture des derniers points, associations/credentials, anti-rejeu, stockage atomique, schéma entrant strict, vue multi-camions | `accept_gps_device_message` reste un service interne ; aucun endpoint d'ingestion fournisseur dans le routeur inspecté |
| Exploitation technique | Compose de production, sauvegarde locale, copie chiffrée hors machine configurable | Activation distante et restauration effective non vérifiées dans cette revue |
| Qualité | CI backend et frontend, migrations peuplées, RLS, types, tests et audits de dépendances | Le workflow indique que Playwright n'est pas exécuté en CI |

L'inventaire ne contient pas de modules applicatifs dédiés au stock de pièces,
au carburant, au HSE ou à la finance. Ces domaines restent dans la vision cible.
Le README racine décrit encore le starter kit : il ne reflète plus l'application.

## Anomalie GPS traitée

Avant GPS-22, `LiveFleetPage.signalState` utilisait uniquement `received_at`.
Le backend accepte des relevés différés jusqu'à 24 heures
(`backend/app/fleet/gps_contract.py`). Un relevé de 10 h reçu à 12 h pouvait
donc afficher « En mouvement » à 12 h, malgré deux heures de retard.

Le calcul partagé utilise désormais `recorded_at` **et** `received_at` :
les deux instants doivent être récents (deux minutes), valides et cohérents
avec la tolérance d'horloge existante de deux minutes. Une vitesse absente
ou invalide donne « Mouvement inconnu » ; une vitesse ancienne est masquée.
La liste, les boutons de la vue relative et la carte individuelle utilisent
le même calcul et la même horloge de présentation.

Le tableau et la carte distinguent l'heure du relevé de sa réception, dans
le fuseau du site fourni par `SiteContext.timezoneOf`.
La carte externe conserve son ouverture explicite par l'utilisateur.

## Vérification

Tests de régression ajoutés : réception différée après coupure, vieillissement
sans nouveau point, dates invalides/futures/incohérentes, bornes de tolérance,
décalages UTC, vitesse inconnue, libellés accessibles et affichage du fuseau.
Le résultat de la CI de la PR reste la preuve de validation complète.

Revue sécurité du diff : changements de présentation uniquement ; mêmes
requêtes, mêmes permissions et même consentement à la carte externe.
Aucune migration ni nouvelle dépendance.

## Suite proposée après fusion

1. Raccorder la finalisation préventive à la fiche OT avec accès aux approbations
   utilisables, erreurs métier explicites et actualisation des échéances.
2. Relier le schéma GPS strict à une passerelle fournisseur authentifiée,
   après définition du transport et de la source fiable du tenant.
3. Exécuter un parcours E2E complet en CI et un exercice de restauration
   dans un environnement jetable autorisé.
4. Actualiser la documentation d'entrée du projet, puis poursuivre les
   modules métier selon les priorités client.

Les seuils GPS restent à calibrer sur le terrain ; cette correction assure
la cohérence avec les seuils déjà utilisés, sans revendiquer du temps réel garanti.
