# État réel du projet

État actualisé au 2 novembre 2026. `main` au commit `cc81f14` (#308) ; seule la PR GPS (#309) reste en revue.
Les constats proviennent du code, des migrations, des tests et des workflows exécutés ; une mention dans une roadmap
n'est pas une preuve de fonctionnement. Les photographies antérieures restent dans l'historique Git.

## État GitHub

| PR | Contenu | État |
|---|---|---|
| #300, #301, #302 | HSE-1, connexion plateforme, fiabilité/coûts maintenance | fusionnées dans `main` |
| #303 | déclaration HSE hors ligne de bout en bout | fusionnée dans `main` |
| #304 | pneumatiques (0053) | fusionnée dans `main` |
| #305, #307, #308 | HSE-2 inspections (0054) et coût complet (0055), arrivés dans `main` par #308 | fusionnées |
| #306 | correctif 404 des achats de carburant | fusionnée dans `main` |
| #309 | GPS avancé : zones, trajets audités, rétention (0056) | ouverte ; base à changer vers `main` |

Production (VPS) : commit `70aeb74`, migration 0051 ; aucune livraison postérieure n'est déployée.

## Périmètre confirmé par le code

| Domaine | État | Preuves principales |
|---|---|---|
| Multi-tenant, sites, utilisateurs, RBAC, MFA, audit | Opérationnel et fortement testé | RLS forcée, matrice générée, tests 403/isolation générés |
| Véhicules, conducteurs, habilitations, affectations | Opérationnel | API, UI, E2E |
| Missions, rotations, pesées | Opérationnel | transitions, événements, E2E |
| Atelier, préventif, fiabilité (MTBF/MTTR) | Opérationnel | #302 |
| Pièces et magasins | Avancé | catalogue, stocks, mouvements, réservations, CMP, réappro, BC brouillon |
| Pneumatiques | Opérationnel | #304, E2E |
| Carburant et achats | Avancé | correctif #306 : création/décision d'achat répondaient 404 |
| HSE | Incidents, hors ligne, inspections, checklists, photos | tests API, UI, E2E |
| Hors ligne | Premier parcours métier réel (déclaration HSE) | E2E Chromium + émulation Android en CI |
| Coût complet par engin | Opérationnel | statuts complet/estimé/partiel/insuffisant |
| GPS | Temps réel en `main` ; zones, trajets audités, rétention en #309 | tests API, charge bornée |
| Contrats et assurances | Socle | registre, documents privés, antivirus |
| Sous-traitants, rentabilité | Absents | — |

## Points d'attention

- Descente de la migration 0031 non sûre lorsque des achats de carburant existent (sans effet en CI/production ;
  gênant pour les bases de développement réutilisées).
- FUEL_MANAGER de portée société ne peut pas lister les sites.
- Essais terrain réels (téléphone Android, réseau mobile, traceurs) non réalisés.
- Durées de conservation (GPS, HSE) et bases légales à valider avec un juriste local avant production.
