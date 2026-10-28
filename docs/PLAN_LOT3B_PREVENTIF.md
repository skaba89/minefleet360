# Lot 3b — Maintenance préventive et indicateurs atelier

> Statut : cadrage proposé, **non implémenté**. Branche dédiée, aucune migration ni déploiement exécuté.
> Références : `CLAUDE.md`, `docs/PLAN_LOT3.md`, `docs/LIVRAISON_LOT3A.md`, lots 2c et 3a existants.

## Objectif et périmètre
Compléter les ordres de travail correctifs du lot 3a par des **plans d'entretien préventif** basés sur le temps calendaire, les kilomètres ou les heures moteur, et des indicateurs vérifiables d'exploitation d'atelier. Réutiliser les relevés du lot 2c, les statuts et l'historique des ordres de travail 3a. Ne pas ajouter de gestion de stock, carburant ou GPS dans ce lot.

## Contrats métier à implémenter
1. Un responsable atelier configure un plan pour une catégorie de véhicules ou un véhicule précis, avec seuil km, heures moteur et/ou périodicité en jours ; tout seuil doit être strictement positif. La portée véhicule prime sur la catégorie si les deux existent.
2. La date ou valeur d'échéance est calculée à partir d'un jalon d'entretien **validé**, jamais d'une position GPS ou d'une estimation de kilométrage. Les relevés remis à zéro doivent être traités explicitement ; privilégier un compteur cumulatif corrigé documenté plutôt que soustraire naïvement deux valeurs.
3. À échéance, créer au plus **un ordre préventif ouvert** pour (tenant, véhicule, plan, échéance). Concurrence, relance et double exécution ne doivent pas produire de doublons. Prévoir une clé d'idempotence et une contrainte en base.
4. Utiliser le cycle existant des ordres de travail 3a et la séparation des tâches : exécutant différent du valideur ; immobilisation seulement selon une politique explicite et auditée.
5. Le plan est versionné : un changement de seuil ne réécrit pas rétroactivement les échéances ou les interventions passées. Suspension du plan avec raison obligatoire.
6. Le calcul d'échéance et la génération de demandes ne doivent pas contourner la RLS. Toute création par un job technique nécessite un contexte tenant justifié, contrôlé et audité.
7. L'absence de relevé n'est **pas** équivalente à « aucune maintenance nécessaire ». Afficher « information insuffisante » et les échéances calendaires éventuellement connues.

## Modèle proposé — à confronter au schéma réel
- `maintenance_plan` : tenant, site nullable selon la portée retenue, catégorie/vehicle cible, code, périodicités km/h/jours, version, état, dates de validité, auteurs, version de ligne.
- `maintenance_due` : tenant, plan/version, véhicule, type de déclencheur, jalon de référence, seuil, date d'évaluation, statut, lien vers work_order, clé idempotente. Unique sur la clé métier d'échéance ; conserver l'historique.
- Extension minimale de `work_order` : rattachement facultatif à `maintenance_due` pour les OT `PREVENTIVE`; ne pas modifier la sémantique des OT `CORRECTIVE`.
- Toutes les FK inter-tables tenant-scopées doivent inclure `tenant_id`, RLS forcée, permissions distinctes lecture/configuration/déclenchement. Conserver le modèle d'audit du projet.

**Arbitrages avant DDL :** granularité du plan (tenant/site/catégorie/véhicule), priorisation des seuils simultanés (« premier seuil atteint » recommandé), stratégie de compteur après reset, identifiant de l'événement d'échéance, calcul des intervalles de service, fuseau du site pour le calendrier.

## API et interface — tranche verticale
- Lecture/listage des plans, création, modification versionnée, suspension et réactivation sous permission dédiée.
- Consultation des échéances : à venir, dues, dépassées, données insuffisantes.
- Action de création idempotente d'un OT préventif ; pas d'exécution implicite depuis un GET.
- Page « Préventif » pour le responsable atelier : filtres site/véhicule/statut, plans et échéances, action de planification.
- Fiche véhicule : prochain entretien, base du calcul, relevé utilisé et avertissement sur compteur non fiable.
- États chargement/erreur/vide, permissions UI générées à partir de la matrice serveur.

## KPI — définitions testables
- **Disponibilité technique** : temps `AVAILABLE` / temps total éligible, sur une fenêtre et un parc explicitement définis ; signaler les périodes sans historique.
- **Durée d'immobilisation** : somme des intervalles d'indisponibilité dédupliqués par véhicule (ne pas additionner deux OT qui se chevauchent).
- **MTTR** : durée moyenne de remise en service pour les incidents correctifs clôturés ; définir si les périodes d'attente de pièces sont incluses (défaut proposé : oui).
- **MTBF** : temps opérationnel entre pannes bloquantes successives par véhicule ; ne pas calculer sans au moins deux événements éligibles et des historiques suffisants.
- Tous les KPI portent dates de début/fin, fuseau d'affichage, taille d'échantillon, périmètre et raison si non calculables. Ne jamais inventer de valeur.

## Vérification et critères d'acceptation
1. Tests RLS et IDOR : tenant A et utilisateur hors site ne voient ni ne modifient les plans/échéances du tenant B.
2. Deux travailleurs concurrents déclenchent une échéance : un seul OT créé ; redémarrage sans doublon.
3. Cas limites : reset compteur, relevé retardé, kilométrage aberrant, seuils simultanés, nouveau véhicule, plan suspendu, fermeture d'OT non conforme.
4. Vérification migrations upgrade/downgrade/upgrade sur base contenant les données des lots 2c et 3a, sans pertes.
5. Tests métier des règles de permission et de séparation des tâches ; contrôle du registre d'audit.
6. Vitest, Playwright sur le parcours plan -> échéance -> OT -> validation ; `ruff`, `mypy`, `pytest` et CI verte **à exécuter**.
7. Recette OVH uniquement après revue indépendante de sécurité, sauvegarde et migration contrôlée, avec preuve du commit réellement déployé.

## Découpage de livraison recommandé
- **3b.1** : migration et API plans préventifs, autorisations et tests d'isolation.
- **3b.2** : moteur d'échéances idempotent connecté aux compteurs, OT préventifs et tests concurrents.
- **3b.3** : interfaces plans/échéances et indicateurs atelier avec tests E2E.
- **3b.4** : revue sécurité indépendante, correctifs, rapport de preuves et procédure de recette.

## Hors périmètre et blocages
Stock de pièces, pneus, carburant, géolocalisation, suivi personnel GPS, facturation : lots ultérieurs. Vérifier les règles opérationnelles d'entretien et la documentation des fabricants avec un expert flotte avant exploitation réelle.

Ce document définit le prochain travail ; **aucun test réussi ni fonctionnalité livrée n'est revendiqué dans cette PR**.
