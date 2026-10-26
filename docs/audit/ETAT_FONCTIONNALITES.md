# État des fonctionnalités

Référence : commit `2e3b803`, 26 octobre 2026. « Codé » signifie modèles/services/routes vérifiables; la CI existante valide son périmètre de tests, pas tous les scénarios futurs.

| Domaine | Réalisation constatée | État et limites |
|---|---|---|
| Tenants/sites | organization/models.py, service.py, router.py; migrations 0001/0002 | Codé : provisioning, édition, suspension/réactivation. Garde de désactivation site incomplète |
| Utilisateurs/identité | identity/models.py, auth_service.py, service.py, routers; 0003 | Codé : invitation, activation, connexion, refresh, logout, reset, mot de passe et désactivation |
| Rôles/permissions | authz/matrix.py, dependencies.py, principal.py, authz_matrix.yaml | Codé : rôles et attributions tenant/site, contrôle serveur et masquage |
| Audit | audit/contracts.py, models.py, router.py; 0004 | Codé : journal transactionnel append-only, lecture. Chaîne cryptographique absente malgré colonnes prévues |
| Flotte | fleet/models.py, router.py, schemas.py, service.py; 0005 | Codé : catalogue, véhicules/engins, transitions, réforme, historique. Pas de GPS réel |
| Conducteurs | workforce/models.py, router.py, service.py; 0006 | Codé : dossiers, permis, habilitations, échéances et validité selon fuseau du site |
| Affectations | fleet/service.py:64-70 et workforce/service.py:55-58 | Absent : fonctions de blocage vides, aucun modèle/API d'affectation |
| Missions/rotations | Aucun module applicatif ni migration dédiée | Absent |
| Atelier/OT/mécaniciens | Rôles seulement dans la matrice | Absent; un rôle MECHANIC n'est pas un dossier mécanicien |
| Tableau de bord | Aucun agrégat métier ni interface | Absent |
| Frontend | Aucun package.json, JSX/TSX ou application web | Absent; OpenAPI n'est pas une interface d'exploitation |
| MFA | Colonnes identity/models.py:40 et 0003 | Prévu, pas de challenge/enrôlement fonctionnel |
| GPS/offline, carburant, pièces, HSE, finance | Documentation cible | Non implémenté |

## Preuves de tests existantes

`tests/test_auth.py`, `test_identity.py`, `test_authz_matrix.py`, `test_database.py`, `test_organization_audit.py`, `test_fleet_workforce.py`, `test_architecture.py`. La CI du snapshot exécute 1162 tests; aucune suite Vitest/Playwright ni E2E navigateur n'existe. Les tests générés de permissions contribuent fortement au nombre total : ne pas assimiler ce nombre à 1162 parcours métier distincts.

## Écart à la vision

PRODUCT_VISION.md demande une chaîne panne → suspension/réaffectation → OT → diagnostic → pièces → remise en service → coûts. Cette chaîne est impossible aujourd'hui. ROADMAP.md phase 1 est partiellement couverte par le socle et les référentiels. PLAN_LOT1.md prévoit déjà une tranche 1c affectations + interface; la poursuivre après les corrections prioritaires.

Point métier à trancher avant terrain : habilitation à lever `SAFETY_BAN` (authz_matrix.yaml, règle vehicle.change_status; LIVRAISON_TRANCHE_1B.md:68). Éviter qu'une permission de dispatch générale autorise une levée d'interdiction de sécurité sans règle HSE explicite.
