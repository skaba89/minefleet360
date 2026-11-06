# Matrice des écarts fonctionnels — base `089d801`

Photo du dépôt le 6 novembre 2026, après fusion de la PR #372 et ajout du lot candidat de sauvegarde chiffrée. « Présent dans le code » signifie que des routes, pages, modèles, migrations ou tests existent; cela ne vaut pas preuve d'exploitation sur des données ni d'acceptation métier.

| Domaine | État du code observé | Limites prouvées / non vérifiées | Prochain critère |
|---|---|---|---|
| Multi-tenant et sites | Sociétés, sites, utilisateurs, rôles, MFA, audit et politique RLS présents | CI d'isolation verte; test client indépendant et audit externe absents | Recette croisée multi-tenant sur staging |
| Parc / conducteurs / affectations | Modules opérationnels présents | Imports client, doublons, habilitations réelles et intégrations RH à valider | Import test rapproché et parcours terrain |
| Dispatch, missions, rotations, pesées | Modules et indicateurs présents | Connecteur réel de pont-bascule et concurrence en charge inconnus | Test de double affectation et rapprochement métier |
| Maintenance corrective/préventive | OT, échéances, compteurs, main-d'œuvre et fiabilité présents | Valeurs de MTBF/MTTR à valider avec historique réel; atelier pilote absent | Parcours panne→remise en service et audit des temps/coûts |
| Pièces et approvisionnement | Catalogue, mouvements, réservation, valorisation/réapprovisionnement et commandes présents | Inventaires physiques et intégration d'achat non établis | Inventaire en environnement pilote, écart expliqué |
| Pneus | Cycle et positions documentés/implémentés selon matrice existante | Méthode de coût, durée de vie et usure à valider métier | Réconcilier un cycle réel sans extrapoler données manquantes |
| Carburant | Stocks, pompes, consommations/anomalies, achats documentés | Capteurs, pompe ou RFID physiques non vérifiés | Connecteur fournisseur testé par protocole documenté |
| HSE | Incidents, inspections et synchronisation hors ligne couverts par le code et specs existants | Utilisation physique et validation réglementaire locale absentes | Test terrain HSE hors ligne avec suppression/révocation |
| GPS téléphone | Partage consenti, positions, carte et tampon volatile de reprise | Pas d'historique durable offline; navigateur peut suspendre le suivi | Tests sur Android réel, écran verrouillé, permission retirée et réseau interrompu |
| GPS traceurs | Endpoint ingestion/authentification/normalisation et couches cartographiques présentes | Aucun modèle/firmware certifié par test matériel confirmé | Premier couple modèle+firmware et protocole de certification |
| GPS carte et trajets | Carte MapLibre multi-engins, direction, historique/replay et état des signaux introduits par #340/#341 | Mise à jour visuelle ne prouve pas une position intermédiaire mesurée; pas de validation terrain | Comparer heure/coordonnée affichées à l'échantillon reçu |
| Alertes GPS | Vitesse, zones, perte de signal planifiée et notifications selon #342–#345 | délais et canaux opérationnels réels non validés | Tester entrée/sortie, dedup, fermeture, retard d'échantillon et notification |
| Flux GPS | SSE authentifié, PostgreSQL LISTEN/NOTIFY, file bornée/reprise et backoff selon #348–#359 | notification non durable; plafonds par worker; p95/p99 et multi-machine non mesurés | Benchmark contrôlé avec injection de panne en staging |
| Offline métier | Briques outbox/verrou/idempotence et parcours HSE existent | Les modules mission, maintenance et carburant ne sont pas attestés offline de bout en bout | Étendre après validation des besoins, un parcours par PR |
| Analytics | Indicateurs d'exploitation, coût véhicule, exports CSV présents selon docs | Dashboards par rôle, exports PDF/Excel et analytics contractuels à confirmer | Liste KPI signée par persona; source et formule vérifiables |
| Sous-traitants et SLA | Pas de parcours complet prouvé | Registre client, prestations, contrat/SLA, coûts et facturation à construire/valider | Modèle métier validé avant code |
| Onboarding et abonnements | Administration plateforme et création de tenant existent | Onboarding autonome, offres, quotas, billing et renouvellement non démontrés | Prototype onboarding + devis pilote, sans tarification arbitraire |
| Support et contrats client | Documentation technique présente | Tickets, astreinte, SLA et contrats de vente absents/non vérifiés | Processus d'incident et contrat examinés professionnellement |
| Infrastructure et CD | Compose et scripts d'exploitation existent; workflows CI actifs | Environnements isolés, image livrable, CD, rollback et déploiement de production non vérifiés | Déployer staging à partir d'un environnement vide |
| Restauration / supervision | Chaîne CI synthétique : chiffrement, rclone local, checksum, téléchargement, déchiffrement, restore, propriétaires/ACL/RLS, image backend et `mf_app` | Fournisseur distant réel, reprise staging, récupération des clés, RPO/RTO, métriques et alertes non prouvés | Restaurer un backup staging depuis le coffre externe retenu, chronométrer puis injecter une alerte |
| Appareils et télématique | contrat d'ingestion extensible | Teltonika/Queclink documentés dans le marché; MineFleet n'a pas de certification matérielle établie | POC de modèle, firmware et réseau exacts |
| Internationalisation | UI française, paramètres locaux dans la vision | i18n, monnaies et règles juridictionnelles internationales à construire | Définir premier marché et langues avant implémentation |

## État du suivi

| Chantier | Statut |
|---|---|
| Référence HEAD et vérification des contrôles jusqu'à la PR #372 | Fusionnée; CI, E2E isolation et scans vérifiés |
| Round-trip chiffré sur remote rclone local et démarrage API | En cours dans ce lot; ne vaut pas test d'un fournisseur externe |
| Restauration staging depuis coffre externe, RPO/RTO et alerting | À faire |
| Pilote traceur et Android en réseau dégradé | À faire |
| Revue conformité locale et traitement GPS/salariés | À faire |
| SaaS onboarding, contrats, support, billing | À faire |
