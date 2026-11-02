# Scénarios de démonstration

Chaque scénario indique les données initiales (créées par `minefleet demo seed --profile small`), les actions à
exécuter à l'écran et le résultat attendu. Comptes : fichier d'identifiants produit par `seed` ou
`reset-credentials` (voir DEMO_USER_GUIDE.md). Société par défaut : `demo-bauxite`.

Les scénarios marqués « à venir » dépendent de données non générées dans ce lot.

| # | Scénario | Compte | Données initiales | Actions | Résultat attendu |
|---|---|---|---|---|---|
| S0 | Activité du jour | dispatcher.boke-mine | missions du jour J | Missions (« En cours seulement ») | Engins en chargement, route chargée, déchargement ; une mission planifiée |
| S1 | Consulter le parc | ops-manager | 12 engins `DEMO-*` | Parc → filtrer « Immobilisé » | Un tombereau immobilisé par la panne ouverte du dernier jour |
| S2 | Affecter un conducteur | dispatcher.boke-mine | conducteur au permis expiré | Affectations → nouvelle affectation avec ce conducteur | Refus motivé `DRIVER_LICENSE_EXPIRED` |
| S3 | Suivre une mission et ses rotations | dispatcher.boke-mine | missions des 14 derniers jours | Missions → ouvrir une mission terminée | Chronologie départ / chargement / déchargement, 2 à 4 rotations pesées |
| S4 | Mission bloquée | dispatcher.boke-mine | mission suspendue `ROAD_BLOCKED` (dernier jour) | Reprendre la mission | Passage SUSPENDED → reprise de l'état antérieur, événement tracé |
| S5 | Pesée en mode dégradé | ops-manager | pesée manuelle `WEIGHBRIDGE_DOWN` en attente | Pesées → approuver | Le tonnage passe de « en attente » à « mesuré » dans les indicateurs |
| S6 | Indicateurs de production | direction | ≈550 pesées | Indicateurs, période 7 jours | Tonnage mesuré identique à `demo verify` |
| S7 | Ravitaillement carburant | fuel-manager.boke-mine puis ops-manager | cuve `CUVE-GO-1` | Demander une distribution, l'approuver avec l'autre compte | Solde de cuve diminué ; le demandeur ne peut pas approuver sa propre demande |
| S8 | Panne et ordre de travail | workshop-chief, mechanic.boke-mine | OT ouvert sur engin immobilisé | Approuver, assigner, démarrer, saisir le temps, soumettre, contrôle qualité | OT clôturé, engin remis en service, coût main-d'œuvre visible |
| S9 | Incident HSE et action corrective | hse | incident critique ouvert | Ouvrir l'enquête, ajouter une action, la réaliser (ops-manager), la vérifier, clore | Clôture impossible tant que l'action n'est pas vérifiée (`HSE_ACTIONS_PENDING`) |
| S10 | Rôles et permissions | driver.boke-mine | — | Tenter d'ouvrir le parc | Accès refusé (403) |
| S11 | Isolation entre sociétés | ops-manager de demo-bauxite | — | Se connecter sur l'espace `demo-tlm` | Connexion refusée |
| S12 | Coût complet par engin | finance | carburant acheté sur commande, pièces, main-d'œuvre, pneus | Coût complet, 30 jours | Carburant « Estimé » sur chaque camion ; pièces et main-d'œuvre sur l'engin réparé ; pneus « Données insuffisantes » (reprise d'inventaire sans prix), sauf l'engin au pneu neuf acheté (voir le constat de méthode, DEMO_DATA_ARCHITECTURE §7) ; coûts par km, heure, tonne |
| S15 | Achat de carburant | fuel-manager.boke-mine puis finance | fournisseur fictif | Créer un bon de commande, l'approuver (finance), réceptionner | Stock de cuve augmenté ; le prix alimente le coût carburant estimé |
| S16 | Pneus | workshop-chief, mechanic.boke-mine | 6 pneus par camion, un pneu réformé | Pneus → filtrer « Mis au rebut » ; inspecter un pneu monté | Historique de pose/dépose ; usure et pression enregistrées |
| S17 | Inspection avant poste non conforme | dispatcher.boke-mine | checklist « avant poste » ; inspection freins non conforme (jour 5) | HSE → Inspections → filtrer « Non conforme » | Point critique en défaut, engin désigné |
| S13 | Géolocalisation et zones | auditor (ou ops-manager) | traceurs, zones, positions des rotations | Véhicules → DEMO-CAM-002 → Historique de trajet, finalité « Analyse d'exploitation », veille | Tracé, distance, entrée/sortie de l'aire de chargement puis entrée en aire de déchargement et arrêt du signal (mission bloquée) ; consultation journalisée |
| S14 | Hors ligne, préventif | — | à venir | — | — |

État de vérification de ce lot :

- S10 et S11 : vérifiés automatiquement sur les données DEMO (`backend/tests/test_demo_seed.py`) ;
- S7 (quatre yeux) et S9 (`HSE_ACTIONS_PENDING`) : règles rencontrées et respectées par le générateur ;
- S2, S4, S5, S8 : règles couvertes par les tests de modules existants, pas encore rejouées sur les données DEMO ;
- S0, S6, S12, S13, S16 (stock), S17 (liste), la flotte GPS, les zones et le tableau de bord : vérifiés à l'écran (captures locales, navigateur automatisé) ;
- S1, S3, S15 : résultat attendu **non encore vérifié à l'écran** — un E2E Playwright sur la base DEMO
  est prévu au lot suivant.
