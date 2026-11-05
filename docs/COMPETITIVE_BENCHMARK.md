> **Lecture de prudence :** comparatif consulté le 4 novembre 2026, prix tiers indicatifs, sans tests directs. Plusieurs affirmations sur l'absence de fonctions GPS sont périmées depuis les PR #340–#359. Pour le positionnement et les acteurs régionaux consultés le 5 novembre, voir [COMPETITIVE_POSITIONING.md](product/COMPETITIVE_POSITIONING.md). Les prix et offres restent à confirmer auprès des éditeurs.

# Benchmark concurrentiel

Recherche du 4 novembre 2026 à partir de sources publiques (liens en fin de document). **Avertissement** : la plupart
des éditeurs ne publient pas leurs prix ; les chiffres viennent souvent de sites tiers, parfois de concurrents, et se
contredisent. Ils donnent des ordres de grandeur, pas des tarifs contractuels. Rien n'a été testé directement dans
les produits cités.

## 1. Paysage

| Acteur | Catégorie | Prix public | Ordre de grandeur (source tierce sauf mention) | Points forts observés | Limites observées |
|---|---|---|---|---|---|
| Samsara | télématique + flotte (US) | non | ~27 à 50 $/véhicule/mois, boîtier ~99 à 148 $, engagement souvent 36 mois | plateforme unique, dashcams IA | contrats longs ; prix opaque |
| Geotab | télématique ouverte, revendeurs | non | ~15 à 45 $/véhicule/mois selon le plan et le revendeur ; boîtier GO payant | écosystème (Marketplace), données ouvertes | gamme réorganisée en 2024, prix très variables |
| Wialon (Gurtam) | plateforme télématique pour intégrateurs | non | sur devis (via partenaires) | 3,6 M d'objets connectés revendiqués, très nombreux boîtiers supportés, présence en Afrique | dépend du partenaire local ; maintenance et opérations minières peu couvertes |
| GPSWOX | logiciel GPS en marque blanche, auto-hébergeable | partiel | hébergé ~99 à 290 $/mois selon le nombre d'objets ; licence auto-hébergée ~6 990 $ (une seule source) | faible coût, auto-hébergement | suivi GPS surtout ; peu de maintenance ou de métier |
| Fleetio | maintenance de flotte (SaaS) | oui | ~4 à 10 $/actif/mois, essai 14 jours (page éditeur) | maintenance, carburant, intégrations télématiques | pas de télématique propre ; coût élevé pour de grandes flottes selon des avis |
| MaintainX | GMAO mobile | oui | 0 / 20 / 65 $ par utilisateur et par mois (annuel), Entreprise sur devis | mobile simple, demandeurs gratuits | prix par utilisateur ; périmètre du hors ligne selon le plan peu clair |
| MiX Telematics, Cartrack (Ctrack) | télématique (Afrique du Sud) | non | sur devis | forte base en Afrique australe et de l'Est ; offres mines (dashcams, transport de postes) | peu d'éléments publics sur l'Afrique de l'Ouest |
| Hexagon (HxGN MineOperate) | gestion de flotte minière (haut de gamme) | non | sur devis | optimisation de la haulage, guidage, anticollision ; communications pair à pair face aux réseaux faibles | réservé aux grandes mines ; coût et intégration lourds |
| Modular Mining (DISPATCH) | dispatch minier | non | sur devis | affectation automatique des camions, vitesse, pneus | même segment haut de gamme que Hexagon |
| Frotcom (distributeur à Conakry) | télématique | non | sur devis | **présence locale vérifiée** (bureau au Kaloum) | rien de public sur le métier minier |

Non couverts faute de temps ou de sources dans cette passe : Verizon Connect, Motive, Webfleet, Caterpillar
MineStar, Komatsu, Epiroc, Deswik, IBM Maximo, SAP EAM, Odoo, UpKeep. Ils seront ajoutés en citant leurs sources.

## 2. Ce que révèle le paysage

1. **Deux mondes séparés** : la télématique (Samsara, Geotab, Wialon) d'un côté, la maintenance (Fleetio,
   MaintainX) de l'autre, reliées par des intégrations. Les systèmes miniers (Hexagon, Modular) couvrent le
   dispatch mais visent les très grandes mines.
2. **Prix opaques et contrats longs** chez les leaders de la télématique ; les outils de maintenance publient leurs
   prix, par actif ou par utilisateur.
3. **Afrique de l'Ouest peu servie de façon visible** : en Guinée, on trouve des distributeurs de télématique
   (Frotcom) et des acteurs locaux de géolocalisation, mais rien de public qui combine flotte, atelier, carburant,
   pesées et HSE pour le minier.

## 3. Opportunités pour MineFleet 360

| Catégorie | Opportunité | État dans MineFleet 360 |
|---|---|---|
| Indispensable | carte temps réel, replay, vitesse et cap, alertes (vitesse, géofence, perte de signal) | **absent** : premier chantier P0 |
| Indispensable | compatibilité multi-boîtiers via des adaptateurs (à la manière de Wialon) | contrat d'adaptateur prêt, aucun fournisseur branché |
| Indispensable | application terrain hors ligne (inspections, OT, carburant) | HSE seulement |
| Mal résolu par les concurrents | un seul outil pour la télématique, l'atelier, le carburant, les pesées et le HSE, sans intégrations coûteuses | **déjà le cas** : c'est le cœur du produit |
| Mal résolu | réseaux faibles : file de synchronisation idempotente, positions tardives acceptées | ingestion tolérante (séquences, positions tardives) ; hors ligne HSE |
| Mal résolu | prix et engagements opaques | tarification publique par engin, sans engagement long (à définir, phase 5) |
| Différenciation | coût par tonne et par engin rapproché des **pesées** (le GPS ne prouve pas le tonnage) | coût complet livré ; rapprochement par poste à faire |
| Différenciation | contrôles de conformité guinéens (documents, habilitations, conservation des données) | documents réglementaires livrés ; avis juridique en attente |
| Différenciation | traçabilité forte (séparation des tâches, audit) attendue par les grands groupes miniers | livré |

## Sources (consultées le 4 novembre 2026)

- Samsara : [tech.co, revue](https://tech.co/fleet-management/samsara-fleet-management-review), [CostBench](https://costbench.com/software/fleet-management/samsara/), [SpotSaaS](https://www.spotsaas.com/blog/samsara-pricing)
- Geotab : [CostBench](https://costbench.com/software/fleet-management/geotab/), [tech.co, revue](https://tech.co/fleet-management/geotab-review-fleet-management), [Geotab, comparatif des plans](https://supporttest.geotab.com/mygeotab/doc/rate-plan-features)
- Wialon : [Capterra](https://www.capterra.com.au/software/126594/wialon), [Electronic Specifier, 3,6 M d'objets](https://www.electronicspecifier.com/news/securex-roundup-wialon-reach-record-3-6-million-tracked-vehicles/), [SaaSRat](https://saasrat.com/products/wialon)
- GPSWOX : [Capterra](https://www.capterra.com/p/140913/GPSWOX/pricing/), [Fitgap](https://us.fitgap.com/products/gpswox), [Software Advice](https://www.softwareadvice.com/fleet-management/gpswox-profile/)
- Fleetio : [page tarifs de l'éditeur](https://www.fleetio.com/pricing), [CostBench](https://www.costbench.com/software/fleet-management/fleetio/), [GetApp, avis](https://www.getapp.com/fleet-management-software/a/fleetio)
- MaintainX : [Fabrico, guide tarifaire 2026](https://www.fabrico.io/blog/maintainx-pricing-guide-2026/), [Software Advice](https://www.softwareadvice.com/cmms/maintainx-profile/)
- MiX Telematics, Cartrack : [Cartrack, offre mines](https://landing.cartrack.co.za/?p=18032), [Creamer Media, Ctrack et Optix 2024](https://newsletter.en.creamermedia.com/article/revolutionising-mining-operations-with-ctracks-advanced-fleet-management-ecosystem-2024-07-26), [étude de cas Unitrans](https://www.casestudies.com/company/mix-telematics/case-study/unitrans-agriculture-mining-services-customer-case-study)
- Hexagon : [HxGN MineOperate Fleet Management](https://hexagon.com/products/product-groups/hxgn-mineoperate/fleet-management), [OP Pro](https://hexagon.com/products/hexagon-op-pro), [Dynamic Haulage](https://miningmagazine.com/fleets/news/1331435/hxgn-dynamic-haulage-released)
- Guinée : [Frotcom Guinée](https://www.frotcom.com/fr-FR/contacts/guinee), [Le360 Afrique, start-up guinéenne](https://afrique.le360.ma/societe/guinee-on-ne-pourra-plus-voler-un-vehicule-sans-que-le-proprietaire-ne-le-sache-en-temps-reel_WC3IGGHMTFDRJNOSSBEYRDOE6M/), [Go Africa Online, SECURIS](https://www.goafricaonline.com/gn/361456-securis-geolocalisation-conakry-guinee)
