# Positionnement concurrentiel — MineFleet 360

**Recherche documentaire consultée le 5 novembre 2026.** Analyse exploratoire, à vérifier en démo/RFP. Les pages fournisseurs décrivent leurs propres offres; elles ne sont pas des tests indépendants. Pour les acteurs guinéens, les fonctionnalités publiques sont des déclarations commerciales, non une vérification technique.

## Paysage concurrentiel pertinent

| Acteur | Position observée dans les sources publiques | Conséquence produit |
|---|---|---|
| [Samsara](https://www.samsara.com/fr/products/telematics) | Plateforme connectée intégrant GPS, diagnostics, routage, maintenance, carburant, sécurité/vidéo et applications de terrain | Ne pas tenter de répliquer tout le matériel propriétaire. Gagner par les processus métiers miniers locaux, le déploiement flexible et l'intégration progressive |
| [Geotab](https://www.geotab.com/fr/) et [Marketplace](https://marketplace.geotab.com/) | Télématique ouverte, appareils, diagnostics et écosystème d'intégrations/extensions | Prioriser adaptateurs testés et API documentée; l'interopérabilité et le choix du matériel sont des attentes structurantes |
| [Wialon](https://wialon.com/fr/gps-hardware) | Plateforme d'intégrateur avec un large catalogue de matériels; le centre d'aide maintient une liste de dispositifs supportés | Écosystème matériel plus vaste que ce que MineFleet peut certifier à court terme; support modèle par modèle plutôt qu'une revendication générale |
| [Traccar](https://www.traccar.org/devices/) | Serveur GPS ouvert qui annonce de nombreux protocoles de fabricants, dont Teltonika et Queclink | Option à comparer pour accélérer l'ingestion/interopérabilité, mais nécessite analyse de sécurité, exploitation, licence et intégration au modèle métier |
| [Fleetio](https://www.fleetio.com/features) | Logiciel de gestion flotte/maintenance avec carburant, pneus, affectations, historique de localisation, coûts et rapports | Les cycles maintenance/carburant/pneus et les coûts sont des attentes du marché; qualité et facilité d'usage comptent autant que la liste de modules |
| [AFTECH Guinée](https://aftech.africa/fr/guinee-2/) | Offre publique locale déclarant gestion de flotte GPS, carburant, vidéo, atelier, TPMS, déploiement et support en Guinée | L'installation, le support local, les capteurs carburant/pneus et les conditions réseau constituent une concurrence concrète |
| [Flottika](https://flottika.com/gestion-flotte-guinee) | Page publique annonçant suivi GPS, alertes, maintenance et compatibilité multi-traceurs; présente aussi des tarifs en XOF | Les offres d'entrée et le support francophone créent une attente locale; prix et compatibilités sont à confirmer commercialement et par essai |
| [Nabaya Guinée](https://nabayaguinee.com/gestion-de-flottes.html), [Logi4Guinée](https://logiforguinee.com/gestion-exploitation-de-vehicules/) | Prestations locales de gestion de parc, géolocalisation, carburant, maintenance, pilotage et reporting | La concurrence comprend des services gérés, pas uniquement des logiciels; accompagnement et opérations doivent faire partie de la proposition |

Les pages consultées ne permettent pas de confirmer directement disponibilité par région, SLA, couverture modèle/firmware, prix contractuel, qualité réelle de service ou sécurité. Demander une démonstration, une référence client et un devis avant toute comparaison définitive.

## Attentes clients probables à valider avec entretiens

- Visibilité et fraîcheur des véhicules sur des itinéraires/sites réels, avec historique et alertes actionnables.
- Détection de vol/écarts carburant, maintenance préventive, disponibilité et réduction d'immobilisation.
- Matériel installé, SIM et support technique local, intégration aux procédures déjà utilisées.
- Fonctionnement explicite et honnête en zone blanche : traceur qui stocke/rejoue, application qui explique ses limites.
- Simplification des tâches d'atelier, dispatch, magasin et HSE; preuve d'audit, export et contrôle de coûts.
- Utilisation sur mobile, français, support joignable, onboarding et prix compréhensibles.
- Adaptation aux sites multisociétés/multisites et accès cloisonnés.

Ces attentes sont des hypothèses issues des catégories de fonctionnalités visibles dans les sources; elles ne remplacent pas des entretiens documentés auprès de clients cibles.

## Différenciation à tester

1. **Opérations minières réunies** : véhicule→disponibilité→affectation→mission→pesée→atelier/pièces/carburant/HSE, sans prendre une position GPS pour un tonnage.
2. **Interopérabilité maîtrisée** : ingestion normalisée et adaptateurs certifiés un par un; publier une matrice exacte de modèles/firmwares testés.
3. **Contexte réseau local** : cartes régionales auto-hébergées, lecture des positions obsolètes clairement indiquée, synchronisation métier offline documentée et support au choix du traceur.
4. **Action à partir des alertes** : relier une alerte à un responsable, un événement d'exploitation et une intervention, puis mesurer délai et taux de résolution.
5. **Coût total vérifiable** : consolider main-d'œuvre, pièces, pneus et carburant avec règles métier explicites et données sources auditables.

## Positionnement à ne pas revendiquer avant preuve

- « compatible avec tous les Teltonika/Queclink », « temps réel garanti », « fonctionne GPS en arrière-plan sans limite réseau »;
- « meilleur que Samsara/Geotab/Wialon » ou économies chiffrées non démontrées;
- certification terrain, disponibilité 99,x %, restitution GPS complète ou conformité juridique globale;
- tarifs concurrents comme faits, sans devis daté et pays/plan comparable.

## Sources techniques utiles pour le backlog

- [Teltonika Codec](https://wiki.teltonika-gps.com/view/Codec) et [choix Codec 8 vs 8 Extended](https://wiki.teltonika-gps.com/view/Which_data_protocol_to_choose_Codec_8_or_Codec_8_Extended) : formats d'émission distincts et paramètres à versionner.
- [Queclink GV300](https://www.queclink.com/product-detail/gv300) : la page fabricant décrit le protocole propriétaire @Track pour cette famille; ne présume pas du comportement de tous les modèles.
- [Liste d'appareils Traccar](https://www.traccar.org/devices/) : référence communautaire utile pour le repérage des modèles; elle ne certifie pas MineFleet.

## Prochaine étude

Conduire des entretiens et démonstrations comparatives avec 5–8 prospects/utilisateurs, couvrant au moins un exploitant, deux sous-traitants transport/mines, un responsable flotte/atelier et un installateur GPS. Consigner besoins, produits montrés, prix/date/devis, support local, modèles matériels réellement testés et critères d'achat. Aucune taille d'échantillon n'est présentée comme représentative.
