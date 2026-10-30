# Roadmap — ordre d'exécution

## Phase 0 — cadrage et fondations
- Cartographier processus, personas, risques, limites produit et concurrence.
- Produire ADR architecture, ERD, matrice RBAC, parcours utilisateurs et critères d'acceptation.
- Initialiser monorepo, backend/frontend, CI, migrations et jeux de données fictifs.

## Phase 1 — MVP utilisable (viser une première démonstration)
- Tenant/site, rôles, auth, audit.
- Gestion véhicules/engins; dossier conducteur et permis/habilitations.
- Affectation conducteur ↔ véhicule, missions et rotation.
- Ordres de travail, mécaniciens, états véhicule.
- Ingestion GPS via adaptateur mock puis intégration fournisseur à valider.
- Dashboard direction exploitation et dispatcher.

## Phase 2 — excellence opérationnelle
- Carburant, stock pièces, pneus, achats, maintenance périodique, HSE, application mobile offline.
- Intégrations GPS, pesée, ERP comptable; alertes et reporting.

### Avancement carburant
- Premier parcours livré en PR : cuves par site, réceptions journalisées, demandes de ravitaillement avec réservation et approbation à deux personnes.
- Inventaires physiques et corrections append-only livrés ; les seuils bas sont configurables et signalés dans l'interface.
- Consommation par km/heure et signalement des écarts livrés : calcul entre pleins complets approuvés, ravitaillements partiels cumulés, comparaison à la médiane historique après trois périodes comparables.
- À poursuivre : notifications de seuil, achats et intégration des pompes.

## Phase 3 — enterprise et institutions
- Sous-traitants, contrats, rentabilité complète, portail client et reporting institutionnel à accès contractualisé.
- Analytique avancée sous réserve de données suffisantes.

## Definition of Done
- API et UI testées, cas d'erreur traités, autorisations tenant/site vérifiées.
- Migration réversible ou stratégie sûre; validation des données.
- Logging/audit, conformité UX et accessibilité, docs mises à jour.
- CI verte si exécutée; sinon rapport explicite des blocages.

