# Registre des risques ouverts — MineFleet360

Revue documentaire du 22 novembre 2026, base main@76850401ce97df81ab9815bffaf51f6ac492d56f. Complète le [GO/NO-GO](../qa/GO_NO_GO.md) et le [constat de reprise](../audit/REPRISE_2026-11-22.md) ; ne remplace pas leurs décisions. Aucune preuve terrain nouvelle. Dernier score officiel connu : 86/100 (17 novembre), non recalculé.

## Registre priorisé

Les responsables ci-dessous sont des rôles proposés, pas des personnes désignées. Tous les risques restent ouverts jusqu'à validation de leur preuve de clôture.

| ID | Risque | Priorité | Dernier constat | Responsable proposé | Preuve de clôture |
|---|---|---|---|---|---|
| R01 | Dérive REC et migration | P0 | Dernier reçu rc.6 / schéma 0072 le 17 nov ; état actuel inconnu | Exploitation | Audit réel, version et schéma rapprochés, release/rollback approuvés et prouvés |
| R02 | Perte de données / restauration | P0 | RPO/RTO coffre externe non démontrés | Exploitation | Restauration isolée chronométrée, intégrité et seuils validés |
| R03 | Fuite inter-tenant | P0 | Contrôles et E2E synthétiques ; recette réelle à confirmer | Sécurité / QA | Recette croisée A/B sur REC, refus et traces expurgées |
| R04 | Confidentialité GPS conducteurs | P0 | Validation juridique absente | Produit / juriste | Avis professionnel, finalités, accès, rétention, information approuvés |
| R05 | Traceurs incompatibles | P0 | Aucun modèle/firmware certifié | Télématique | Qualification banc et terrain par modèle |
| R06 | GPS indisponible en réseau faible | P0 | Références différées #489–506 ; Android natif non réalisé | Mobile / QA | Qualification physique D2/D3, réseau dégradé, séparation live/historique |
| R07 | Latence GPS ou capacité insuffisante | P0 | Outils de mesure livrés, seuils réels non signés | SRE / Produit | Benchmarks staging, p95/p99 et seuils métier approuvés |
| R08 | Incident non détecté | P0 | Dernier reçu : timer désactivé ; état actuel inconnu | SRE | Supervision effective, alerte reçue et exercice documenté |
| R09 | Instabilité des E2E terrain | P1 | #507 : timeout HSE Android, relance verte ; récurrence connue | QA / Frontend | Diagnostic reproductible et correction de cause, sans suppression de tests |
| R10 | Offre commercialement non viable | P0 commercial | Tarif/contrat/SLA non approuvés | Direction / Produit | Coût-servi, entretiens clients, offre et SLA validés |
| R11 | Régression sur migrations et modules récents | P0 avant release | Lots #478–487 non attestés sur REC | QA / Exploitation | Recette finance, MFA, offline et migrations sur release exacte |

## Actions sans accès terrain

- R09 : isoler l'instabilité du démarrage HSE et conserver des diagnostics expurgés, sans jets d'authentification ni coordonnées.
- R06 : utiliser le dossier [qualification Android](../qa/GPS_ANDROID_PHYSICAL_QUALIFICATION.md) pour demander l'inventaire P1/P2 ; ne pas démarrer D2-b avant autorisation.
- R05 : préparer la demande technique fournisseur selon le protocole de qualification déjà publié.
- R10 : utiliser le protocole de validation facturation existant ; ne pas inventer de prix.

## Actions nécessitant une décision / accès

- Priorité immédiate : audit REC lecture seule puis rapprochement migrations ; aucun apply sans accord.
- Restauration externe et exercice de supervision avec environnement isolé et accord distinct.
- Juriste, fournisseur de traceur, deux Android physiques ; preuve datée et synthétique jusqu'à autorisation de pilote.
- Validation commerciale par les responsables avant toute contractualisation.

## Règle de décision

Tout P0 ouvert empêche la décision correspondante de passage. GO préparation de pilote fermé uniquement, NO-GO commercial généralisé. La clôture exige date, environnement, commit, résultat, preuve expurgée et approbateur ; un test CI vert ou un document nouveau ne suffit pas pour clore un risque terrain. Ne pas publier de secrets ni données personnelles.
