# Écarts métier minier

Référence : `main@3c4bb02`, 30 octobre 2026.

MineFleet 360 couvre déjà le noyau flotte/dispatch/atelier/carburant et peut soutenir une démonstration réaliste. Il ne couvre pas encore la chaîne économique et HSE complète d'une exploitation minière.

| Capacité cible | Maturité | Écart déterminant | Prochaine preuve attendue |
|---|---:|---|---|
| Opérations quotidiennes | 82/100 | planning d'équipe et mode déconnecté incomplets | clôture de poste et reprise après perte réseau en E2E |
| Dispatching et transport | 82/100 | optimisation et gestion d'exception limitées | scénario multi-engins, changement de conducteur et véhicule indisponible |
| Gestion des équipements | 85/100 | profondeur variable selon catégorie | référentiels réels chargeuse/camion/excavatrice validés par métier |
| Productivité et disponibilité | 65/100 | disponibilité, rendement et causes d'attente non consolidés | KPI disponibilité physique, utilisation et tonnes/heure réconciliés |
| Maintenance des engins | 78/100 | pièces/coûts/fiabilité incomplets | OT avec pièces, coût, immobilisation, MTBF et MTTR |
| Approvisionnements | 72/100 | carburant avancé, pièces absentes | demande-achat-réception-stock-sortie avec valorisation |
| Coût par équipement | 40/100 | pas de grand livre de coût unifié | carburant + maintenance + pneus + main-d'œuvre par engin/période |
| Gestion des équipes | 55/100 | roster/pointage/compétences opérationnelles limités | équipe/poste, absences, relève et habilitation obligatoire |
| Prévention des incidents | 25/100 | pas de module HSE structuré | inspection, incident, enquête et action corrective traçables |
| Sous-traitants | 20/100 | identité externe sans contrats/SLA | contrat, flotte, conducteurs, SLA et facturation isolés |
| Rentabilité des opérations | 20/100 | revenus, contrats et marges absents | marge par mission/site/client et rapprochement financier |

## Priorités métier recommandées

1. Stocks de pièces et pneus, car ils conditionnent coûts atelier et disponibilité.
2. HSE, indispensable avant un pilote minier en production.
3. Coût par équipement, en agrégeant carburant, pièces, pneus et main-d'œuvre.
4. GPS fournisseur, trajets, géofencing et alertes opérationnelles.
5. Équipes, sous-traitants et rentabilité une fois les données sources fiables.

## Contraintes guinéennes à valider sur le terrain

- connectivité intermittente et synchronisation différée ;
- consommation en GNF et pratiques locales d'achat/livraison ;
- qualité des référentiels engins, compteurs et numéros de série ;
- processus HSE propres aux exploitants et sous-traitants ;
- conservation et base légale des données de géolocalisation des conducteurs.

Ces éléments sont des hypothèses de validation produit et non des fonctionnalités déclarées terminées.
