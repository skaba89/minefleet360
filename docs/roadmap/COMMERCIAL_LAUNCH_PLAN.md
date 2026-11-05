# Plan de lancement commercial — MineFleet 360

## Positionnement à tester

Une plateforme opérationnelle de flotte pour transporteurs et sous-traitants miniers en Guinée, reliant parc, conducteurs, dispatch, entretien, pièces, carburant, HSE, coûts et position GPS. Différenciation à prouver par l'intégration de processus dans une même application, l'usage avec connectivité irrégulière, l'accompagnement local et des données minimisées. Aucun avantage de marché n'est encore établi par des clients payants.

Le suivi GPS précis dépend de matériel, couverture opérateur, configuration et consentement. L'application navigateur ne doit pas promettre un suivi en arrière-plan Android/iOS ni un historique offline durable.

## Choix à faire avant la première offre

1. Segment d'entrée : transporteur, sous-traitant minier ou exploitant; acheteur et utilisateur diffèrent.
2. Taille de flotte/sites, période de rétention, fréquence GPS et criticité des alertes.
3. Matériel fourni/acheté par le client; installation, SIM, connectivité et support.
4. Hébergement, sauvegarde, résidence/transfert des données et confidentialité des salariés.
5. Niveau de support, horaires, délais d'intervention et responsabilité pour alertes manquées.
6. Monnaie de facturation, taxes, paiement local et frais d'installation.
7. Coût de l'hébergement, du SMS/e-mail, des cartes (carte actuelle auto-hébergée pour la Guinée), du support et de l'intégration.

## Expériences de marché

| Étape | Travail | Mesure recherchée | Sortie |
|---|---|---|---|
| Découverte | Entretiens séparés avec direction flotte, dispatch, atelier, carburant, HSE, finance et conducteurs | fréquence/douleur, coût actuel, outils, décision d'achat, connectivité | personas et problèmes priorisés; pas de promesse de roadmap |
| Observation | Suivre les processus réels avec accord client, sans données personnelles inutiles | temps de cycle, ressaisies, erreurs de rapprochement | cartographie métier revue par client |
| Prototype | Démo basée sur données synthétiques et captures « simulation » visibles | compréhension, tâches réussies, objections | validation UX et critères pilote |
| Pilote | Durée, véhicules/sites et responsabilités convenus; données minimales | activation, tâches terminées, fraîcheur, incidents, valeur démontrée | compte rendu signé; continuation ou arrêt |
| Commercialisation | Support, SLA, facture, contrat, politique de données, plan de sortie et continuité | conversion, rétention, coût service, marge | GO commercial |

## Offres à étudier (aucun tarif fixé)

| Offre candidate | Client visé | Contenu à tester | Unité de prix à comparer |
|---|---|---|---|
| Starter | petite flotte transport | parc, maintenance, rappel, rapports simples | par véhicule/mois ou palier flotte |
| Business | transporteur/sous-traitant | plusieurs sites, dispatch, carburant, stock et GPS | base société + véhicules actifs + intégrations |
| Mining Pro | sous-traitant/exploitant | opérations de site, HSE, pesée, alertes, multi-sites | site + flotte + options/connecteurs |
| Enterprise | grand groupe | SSO/API, environnements dédiés, intégration, SLA et accompagnement | devis établi sur coûts et engagements |

Ne fixer les quotas ni les prix avant le calcul coût-servi (DB, historique GPS, rétention, sauvegarde, support, SMS, matériel) et un test de volonté de payer. Éviter les prix par véhicule seuls si le coût du support et l'intégration varie fortement.

## Éléments nécessaires à la vente

- Démo isolée avec jeu fictif et bandeau persistant pour données simulées.
- Guide d'onboarding par rôle, modèle d'import, procédure de vérification des données.
- Conditions de service, confidentialité GPS/salariés, conservation et suppression; validation juridique professionnelle par pays.
- Procédure de support, escalade incident, statut de service et communication clients.
- Contrat de service et niveaux mesurés; ne pas promettre SLA sans historique opérationnel.
- Processus de sortie : export client, suppression planifiée, conservation légale et preuve.
- Facturation, renouvellement, suspension graduée et changement d'offre.
- Formations dispatcher, atelier, conducteur, HSE et administrateur.
- RACI matériel : achat, SIM, installation, maintenance, remplacement, certificats et responsabilité des données.
- Cas de démonstration mining : panne, réaffectation, OT, pièces, remise en service et coût; pesée enregistrée séparément de l'estimation GPS.

## KPI d'activation et de valeur

Définir avec les clients avant pilote : jours avant première flotte valide, pourcentage de véhicules avec propriétaire/site, complétion des inspections, délai incident→OT, disponibilité, consommation rapprochée, taux de positions fraîches, faux positifs, alertes vues/actionnées, incidents sync, tâches terminées par rôle et renouvellement. Toute formule doit spécifier la source, fenêtre de temps, exclusions et acteur qui valide.
