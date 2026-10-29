# Finalisation préventive depuis l'atelier

## Parcours

Après le contrôle qualité conforme d'un OT de type PREVENTIVE, la fiche
atelier propose « Finaliser l'échéance préventive » aux personnes possédant
`maintenance.preventive.manage` sur le site de l'OT.

La lecture `GET /work-orders/{work_order_id}/preventive-completion` présente
le plan rattaché à l'échéance (y compris sa version historique suspendue),
la clôture et les preuves requises. Pour chaque compteur requis, elle montre
soit le total déjà figé, soit au plus 25 approbations utilisables, triées de
la plus récente à la plus ancienne. Aucun nom d'approbateur ni référence
documentaire libre n'est exposé dans cette réponse.

Les choix portent sur le même tenant, véhicule, site et type de compteur.
Une approbation postérieure à la clôture, un cumul hors limites ou une
approbation suivie d'un relevé brut avant la clôture ne sont pas proposés.
Les relevés postérieurs à la clôture ne changent pas cette preuve historique.

Le choix est explicite et une confirmation est demandée. Le POST existant
`/work-orders/{work_order_id}/complete-preventive` reste l'autorité : il
revérifie les preuves et termine l'échéance dans sa transaction.
Les preuves déjà figées ne sont pas renvoyées comme nouvelles approbations.

Un plan uniquement calendaire se finalise sans compteur. Un compteur requis
sans approbation bloque le formulaire : le dossier de réconciliation doit
être examiné. Ce parcours ne crée ni n'antidate une approbation.

## Rejeux et erreurs

Un rejeu accepté affiche « déjà finalisée ». Après succès, les caches de
l'échéance véhicule et du dossier de finalisation sont actualisés.
Un conflit redemande la confirmation et recharge les choix ; le formulaire
conserve les messages métier et la référence d'erreur de l'API.
Le verrou d'envoi côté interface empêche deux soumissions simultanées.

L'action ne change ni le contrôle qualité acquis ni la disponibilité du
véhicule. Elle finalise l'échéance préventive liée et ses preuves.

## Vérification

- API/PostgreSQL : sélection des approbations, exclusion des preuves hors
  véhicule/site/date, relevé plus récent, compteurs multiples, preuve figée,
  refus sans preuve, finalisation puis rejeu, 401/403/404 et tenant imposé refusé.
- Autorisations : la route est déclarée dans la matrice et bénéficie des
  contrôles générés de rôles et d'isolation.
- Interface : garde de permission/état, plan calendaire, choix explicite,
  absence de preuve, total figé nul, conflit, rejeu et double soumission.
- Ruff/format, typage, build et suites habituelles exécutés par la CI.

Aucune migration, nouvelle dépendance ou création automatique d'approbation.
