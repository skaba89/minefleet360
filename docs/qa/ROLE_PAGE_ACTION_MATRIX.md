# Matrice rôles × menus × routes × permissions (générée)

- Document généré, sans horodatage pour rester déterministe (`--check` en CI).
- Sources de vérité : `backend/app/authz/authz_matrix.yaml` (RBAC machine), `frontend/src/App.tsx` (routes), `frontend/src/components/Layout.tsx` + `frontend/src/pages/AdminPages.tsx` (menus).
- Vérification anti-dérive : `python scripts/generate_role_route_matrix.py --check`.

> **Portée et limites.** Ce document décrit ce que le code *autorise*, pas ce qui est *prouvé fonctionnel* : l'exécution navigateur par rôle est couverte par le workflow CI `e2e-isolation.yml` (jobs `tenant-isolation` et `demo-journeys`) et non par ce document. Une case « visible » signifie que la condition de menu du code est satisfaite par les grants du rôle ; la page peut ensuite renvoyer une erreur métier légitime (403/404).

## 1. Comptes et rôles

| Rôle | Portées autorisées | Type de tenant | Assignable par le client |
|---|---|---|---|
| `PLATFORM_ADMIN` | PLATFORM | PLATFORM | non |
| `TENANT_ADMIN` | TENANT | CUSTOMER | oui |
| `DIRECTION` | TENANT | CUSTOMER | oui |
| `OPS_MANAGER` | TENANT / SITE | CUSTOMER | oui |
| `DISPATCHER` | SITE | CUSTOMER | oui |
| `HR` | TENANT / SITE | CUSTOMER | oui |
| `DRIVER` | SITE | CUSTOMER | oui |
| `WORKSHOP_CHIEF` | TENANT / SITE | CUSTOMER | oui |
| `MECHANIC` | TENANT / SITE | CUSTOMER | oui |
| `STOREKEEPER` | TENANT / SITE | CUSTOMER | oui |
| `FUEL_MANAGER` | TENANT / SITE | CUSTOMER | oui |
| `HSE` | TENANT / SITE | CUSTOMER | oui |
| `FINANCE` | TENANT / SITE | CUSTOMER | oui |
| `AUDITOR` | TENANT | CUSTOMER | oui |

Rôles optionnels : `AUDITOR`.

## 2. Menus visibles par rôle (condition de menu du code × grants YAML)

| Menu | Domaine | `PLATFORM_ADMIN` | `TENANT_ADMIN` | `DIRECTION` | `OPS_MANAGER` | `DISPATCHER` | `HR` | `DRIVER` | `WORKSHOP_CHIEF` | `MECHANIC` | `STOREKEEPER` | `FUEL_MANAGER` | `HSE` | `FINANCE` | `AUDITOR` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [Sociétés clientes](/plateforme/societes) | Plateforme | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [Nouvelle société](/plateforme/nouvelle-societe) | Plateforme | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [État des services](/plateforme/etat) | Plateforme | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [Véhicules](/vehicules) | Flotte | — | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Échéances documents](/vehicules/echeances) | Flotte | — | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Flotte GPS](/flotte-gps) | GPS | — | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| [Zones GPS](/flotte-gps/zones) | GPS | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — | ✓ | — | ✓ |
| [Alertes GPS](/flotte-gps/alertes) | GPS | — | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | ✓ | — | ✓ |
| [Mon partage GPS](/mon-suivi) | GPS | — | ✓ | — | ✓ | ✓ | — | ✓ | — | — | — | — | — | — | — |
| [Conducteurs](/conducteurs) | RH terrain | — | — | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ | ✓ | — | ✓ |
| [Affectations](/affectations) | RH terrain | — | — | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ | ✓ | — | ✓ |
| [Missions](/missions) | Dispatch | — | — | ✓ | ✓ | ✓ | — | — | ✓ | — | — | — | ✓ | ✓ | ✓ |
| [Atelier](/atelier) | Maintenance | — | — | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | — | — | ✓ | — | ✓ |
| [Fiabilité parc](/atelier/fiabilite) | Maintenance | — | — | ✓ | ✓ | — | — | — | ✓ | — | — | — | — | ✓ | ✓ |
| [Maintenance (préventif)](/maintenance) | Maintenance | — | — | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | — | — | — | — | ✓ |
| [Carburant](/carburant) | Carburant | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | ✓ | — | ✓ | ✓ |
| [Pneus](/pneus) | Maintenance | — | — | ✓ | ✓ | — | — | — | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| [Pièces](/pieces) | Maintenance | — | ✓ | ✓ | ✓ | — | — | — | ✓ | — | ✓ | — | — | — | ✓ |
| [Sécurité (HSE)](/hse) | HSE | — | — | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ | — | ✓ |
| [Inspections HSE](/hse/inspections) | HSE | — | — | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ | — | ✓ |
| [Checklists HSE](/hse/checklists) | HSE | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — |
| [Pesées](/pesees) | Dispatch | — | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | ✓ | ✓ | ✓ |
| [Contrats & assurances](/juridique) | Juridique | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | ✓ | ✓ | ✓ |
| [Coût complet](/couts) | Pilotage | — | — | ✓ | ✓ | — | — | — | ✓ | — | — | — | — | ✓ | ✓ |
| [Indicateurs](/indicateurs) | Pilotage | — | — | ✓ | ✓ | ✓ | — | — | — | — | — | — | ✓ | ✓ | ✓ |
| [Administration](/administration) | Administration | — | ✓ | — | ✓ | — | ✓ | — | — | — | — | — | — | — | ✓ |
| [Administration · Sites](/administration/sites) | Administration | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — |
| [Administration · Lieux et matières](/administration/lieux-matieres) | Administration | — | ✓ | — | ✓ | — | — | — | — | — | — | — | — | — | — |
| [Administration · Documents exigés](/administration/documents-exiges) | Administration | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — |
| [Administration · Utilisateurs et rôles](/administration/utilisateurs) | Administration | — | ✓ | — | — | — | ✓ | — | — | — | — | — | — | — | ✓ |
| [Administration · Journal d'audit](/administration/journal) | Administration | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | ✓ |

Pages toujours accessibles à tout compte authentifié : Accueil (`/`), Mon compte · sécurité (`/mon-compte/securite`), déconnexion. L'accueil s'adapte au rôle (vue plateforme, tableau de bord flotte ou liste des rôles du compte). Mes sessions (`/mon-compte/sessions`) exige `identity.session.revoke_own` (accordée aux 14 rôles).

## 3. Routes UI protégées (`frontend/src/App.tsx`)

| Route | Composant | Permission(s) attendue(s) |
|---|---|---|
| `/connexion` | `LoginPage` | publique (non authentifié) |
| `/activation` | `ActivationPage` | publique (non authentifié) |
| `/reinitialisation` | `ResetConfirmPage` | publique (non authentifié) |
| `/mot-de-passe-oublie` | `ResetRequestPage` | publique (non authentifié) |
| `/plateforme/societes` | `PlatformTenantsPage` | `organization.tenant.list` |
| `/plateforme/nouvelle-societe` | `PlatformCreateTenantPage` | `organization.tenant.create` |
| `/plateforme/etat` | `PlatformHealthPage` | `organization.tenant.list` |
| `/vehicules` | `VehiclesPage` | `fleet.vehicle.read` |
| `/flotte-gps` | `LiveFleetPage` | `fleet.vehicle.read` |
| `/flotte-gps/zones` | `GeofencesPage` | `fleet.geofence.read` |
| `/flotte-gps/alertes` | `GpsAlertsPage` | `fleet.gps_alert.read` |
| `/mon-suivi` | `PhoneTrackingPage` | `fleet.gps.share` |
| `/vehicules/echeances` | `DueDocumentsPage` | `fleet.document.read` |
| `/vehicules/:vehicleId` | `VehicleDetailPage` | `fleet.vehicle.read` |
| `/conducteurs` | `DriversPage` | `workforce.driver.read` |
| `/conducteurs/:driverId` | `DriverDetailPage` | `workforce.driver.read` |
| `/affectations` | `AssignmentsPage` | `assignment.vehicle_assignment.read` |
| `/missions` | `MissionsPage` | `dispatch.mission.read` |
| `/missions/:missionId` | `MissionDetailPage` | `dispatch.mission.read` |
| `/atelier` | `WorkshopPage` | `maintenance.work_order.read` |
| `/maintenance` | `PreventivePage` | `maintenance.preventive.read` |
| `/carburant` | `FuelPage` | `fuel.stock.read` ou `fuel.stock.manage` ou `fuel.issue.request` ou `fuel.stocktake.record` ou `fuel.stock.threshold` ou `fuel.purchase.read` ou `fuel.purchase.create` |
| `/pieces` | `PartsPage` | `maintenance.parts.read` |
| `/juridique` | `LegalRegistriesPage` | `legal.contract.read` ou `legal.insurance.read` |
| `/atelier/fiabilite` | `ReliabilityPage` | `maintenance.reliability.read` |
| `/atelier/:workOrderId` | `WorkOrderPage` | `maintenance.work_order.read` |
| `/hse` | `HsePage` | `hse.incident.read` ou `hse.incident.report` ou `hse.inspection.perform` |
| `/hse/inspections` | `HseInspectionsPage` | `hse.inspection.read` ou `hse.inspection.perform` |
| `/hse/inspections/:inspectionId` | `HseInspectionPage` | `hse.inspection.read` ou `hse.inspection.perform` |
| `/hse/checklists` | `ChecklistTemplatesPage` | `hse.checklist.manage` |
| `/hse/:incidentId` | `HseIncidentPage` | `hse.incident.read` ou `hse.incident.report` |
| `/pneus` | `TyresPage` | `maintenance.tyre.read` |
| `/pneus/:tyreId` | `TyrePage` | `maintenance.tyre.read` |
| `/couts` | `CostsPage` | `cost.vehicle.read` |
| `/pesees` | `WeighingsPage` | `dispatch.weighing.read` |
| `/indicateurs` | `IndicatorsPage` | `dispatch.indicators.read` |
| `/mon-compte/securite` | `SecurityPage` | toute session authentifiée |
| `/mon-compte/sessions` | `SessionsPage` | `identity.session.revoke_own` |
| `/administration` | `AdminLayout` | `organization.site.create` ou `identity.user.read` ou `audit.event.read` ou `dispatch.location.manage` ou `dispatch.material.manage` |
| `/administration/sites` | `SitesAdminPage` | `organization.site.create` |
| `/administration/utilisateurs` | `UsersAdminPage` | `identity.user.read` |
| `/administration/journal` | `AuditAdminPage` | `audit.event.read` |
| `/administration/lieux-matieres` | `ReferentialsPage` | `dispatch.location.manage` ou `dispatch.material.manage` |
| `/administration/documents-exiges` | `RequiredDocumentsPage` | `fleet.vehicle_category.manage` |
| `*` | `NotFoundPage` | toute session authentifiée |

Route attrape-tout `*` : page « Page introuvable » (404 UI) dans le shell authentifié ; les routes publiques inconnues sont redirigées vers `/connexion` par la garde `Protected`.

## 4. Permissions API : routes et rôles accordés

| Permission | Tranche | Routes API | Rôles accordés |
|---|---|---|---|
| `organization.tenant.create` | 1a | `POST /platform/tenants` | `PLATFORM_ADMIN` |
| `organization.tenant.suspend` | 1a | `POST /platform/tenants/{tenant_id}/suspend`<br>`POST /platform/tenants/{tenant_id}/reactivate` | `PLATFORM_ADMIN` |
| `organization.tenant.list` | 1a | `GET /platform/tenants`<br>`GET /platform/tenants/{tenant_id}` | `PLATFORM_ADMIN` |
| `organization.tenant.read` | 1a | `GET /tenant` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `DRIVER`, `FINANCE`, `FUEL_MANAGER`, `HR`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `organization.tenant.update` | 1a | `PATCH /tenant` | `TENANT_ADMIN` |
| `organization.site.read` | 1a | `GET /sites`<br>`GET /sites/{site_id}` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `FUEL_MANAGER`, `HR`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `organization.site.create` | 1a | `POST /sites` | `TENANT_ADMIN` |
| `organization.site.update` | 1a | `PATCH /sites/{site_id}` | `TENANT_ADMIN` |
| `organization.site.deactivate` | 1a | `POST /sites/{site_id}/deactivate`<br>`POST /sites/{site_id}/reactivate` | `TENANT_ADMIN` |
| `identity.user.read` | 1a | `GET /users`<br>`GET /users/{user_id}` | `AUDITOR`, `HR`, `TENANT_ADMIN` |
| `identity.user.create` | 1a | `POST /users`<br>`POST /users/{user_id}/resend-invitation` | `TENANT_ADMIN` |
| `identity.user.update` | 1a | `PATCH /users/{user_id}` | `TENANT_ADMIN` |
| `identity.user.deactivate` | 1a | `POST /users/{user_id}/deactivate`<br>`POST /users/{user_id}/reactivate` | `TENANT_ADMIN` |
| `identity.user.reset_credentials` | 1a | `POST /users/{user_id}/reset-credentials` | `TENANT_ADMIN` |
| `identity.user.reset_mfa` | 1c | `POST /users/{user_id}/reset-mfa` | `TENANT_ADMIN` |
| `identity.user.update_self` | 1a | `GET /me`<br>`POST /me/password`<br>`GET /me/mfa`<br>`POST /me/mfa/setup`<br>`POST /me/mfa/confirm`<br>`POST /me/mfa/recovery-codes`<br>`POST /me/mfa/disable` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `DRIVER`, `FINANCE`, `FUEL_MANAGER`, `HR`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `PLATFORM_ADMIN`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `identity.role.read` | 1a | `GET /roles` | `AUDITOR`, `DIRECTION`, `PLATFORM_ADMIN`, `TENANT_ADMIN` |
| `identity.role_assignment.read` | 1a | `GET /role-assignments` | `AUDITOR`, `TENANT_ADMIN` |
| `identity.role_assignment.create` | 1a | `POST /role-assignments` | `TENANT_ADMIN` |
| `identity.role_assignment.revoke` | 1a | `POST /role-assignments/{assignment_id}/revoke` | `TENANT_ADMIN` |
| `identity.session.revoke_own` | 1a | `GET /me/sessions`<br>`POST /me/sessions/revoke-others`<br>`POST /me/sessions/{session_id}/revoke` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `DRIVER`, `FINANCE`, `FUEL_MANAGER`, `HR`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `PLATFORM_ADMIN`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `identity.session.revoke_any` | 1a | `POST /users/{user_id}/sessions/revoke` | `TENANT_ADMIN` |
| `audit.event.read` | 1a | `GET /audit-events`<br>`GET /audit-events/{event_id}` | `AUDITOR`, `TENANT_ADMIN` |
| `fleet.vehicle_category.read` | 1b | `GET /vehicle-categories`<br>`GET /vehicle-categories/{category_id}`<br>`GET /vehicle-categories/{category_id}/required-documents` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `FUEL_MANAGER`, `HR`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `fleet.vehicle.read` | 1b | `GET /vehicles`<br>`GET /vehicles/gps/latest`<br>`GET /vehicles/{vehicle_id}`<br>`GET /vehicles/{vehicle_id}/status-history` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `FUEL_MANAGER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `fleet.vehicle.create` | 1b | `POST /vehicles` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.vehicle.update` | 1b | `PATCH /vehicles/{vehicle_id}` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.vehicle.update_status` | 1b | `POST /vehicles/{vehicle_id}/status` | `DISPATCHER`, `OPS_MANAGER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `fleet.vehicle.deactivate` | 1b | `POST /vehicles/{vehicle_id}/retire` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.meter.read` | 1c | `GET /vehicles/{vehicle_id}/meter-readings` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `FUEL_MANAGER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `fleet.meter.record` | 1c | `POST /vehicles/{vehicle_id}/meter-readings` | `DISPATCHER`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `fleet.document.read` | 1c | `GET /vehicles/{vehicle_id}/documents`<br>`GET /vehicle-documents` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `FUEL_MANAGER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `fleet.document.manage` | 1c | `POST /vehicles/{vehicle_id}/documents`<br>`POST /vehicle-documents/{vehicle_document_id}/withdraw` | `HSE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.vehicle_category.manage` | 1c | `PUT /vehicle-categories/{category_id}/required-documents` | `TENANT_ADMIN` |
| `fleet.meter.reset` | 1c | `POST /vehicles/{vehicle_id}/meter-resets` | `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `workforce.driver.read` | 1b | `GET /drivers`<br>`GET /drivers/{driver_id}` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FUEL_MANAGER`, `HR`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `workforce.driver.create` | 1b | `POST /drivers` | `HR` |
| `workforce.driver.update` | 1b | `PATCH /drivers/{driver_id}` | `HR` |
| `workforce.driver.deactivate` | 1b | `POST /drivers/{driver_id}/status` | `HR` |
| `workforce.driver_license.read` | 1b | `GET /drivers/{driver_id}/licenses`<br>`GET /workforce/expirations` | `AUDITOR`, `DISPATCHER`, `HR`, `HSE`, `OPS_MANAGER` |
| `workforce.driver_license.manage` | 1b | `POST /drivers/{driver_id}/licenses`<br>`PATCH /driver-licenses/{license_id}` | `HR` |
| `workforce.driver_qualification.read` | 1b | `GET /drivers/{driver_id}/qualifications` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HR`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `workforce.driver_qualification.manage` | 1b | `POST /drivers/{driver_id}/qualifications` | `HR` |
| `workforce.driver_qualification.revoke` | 1b | `POST /driver-qualifications/{qualification_id}/revoke` | `HR` |
| `assignment.vehicle_assignment.read` | 1c | `GET /vehicle-assignments`<br>`GET /vehicle-assignments/{vehicle_assignment_id}`<br>`GET /vehicles/{vehicle_id}/assignments`<br>`GET /drivers/{driver_id}/assignments` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FUEL_MANAGER`, `HR`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `assignment.vehicle_assignment.create` | 1c | `POST /vehicle-assignments` | `DISPATCHER`, `OPS_MANAGER` |
| `assignment.vehicle_assignment.update` | 1c | `POST /vehicle-assignments/{vehicle_assignment_id}/activate`<br>`POST /vehicle-assignments/{vehicle_assignment_id}/suspend`<br>`POST /vehicle-assignments/{vehicle_assignment_id}/resume` | `DISPATCHER`, `OPS_MANAGER` |
| `assignment.vehicle_assignment.end` | 1c | `POST /vehicle-assignments/{vehicle_assignment_id}/complete`<br>`POST /vehicle-assignments/{vehicle_assignment_id}/cancel` | `DISPATCHER`, `OPS_MANAGER` |
| `maintenance.parts.manage` | 1c | `POST /parts`<br>`POST /part-stores`<br>`POST /part-replenishments`<br>`POST /parts-purchase-orders`<br>`POST /part-replenishments/{replenishment_id}/submit`<br>`POST /part-replenishments/{replenishment_id}/decision` | `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `maintenance.parts.receive` | 1c | `POST /part-movements/receipts`<br>`POST /part-movements/valued-receipts` | `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.parts.issue` | 1c | `POST /part-movements/issues`<br>`POST /part-movements/valued-issues` | `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.parts.consume` | 1c | `POST /part-reservations/{reservation_id}/consume` | `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.parts.release` | 1c | `POST /part-reservations/{reservation_id}/release` | `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.parts.reserve` | 1c | `POST /part-reservations` | `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.parts.read` | 1c | `GET /parts`<br>`GET /part-stores`<br>`GET /part-balances`<br>`GET /part-movements`<br>`GET /part-reservations`<br>`GET /part-replenishments`<br>`GET /parts-purchase-orders` | `AUDITOR`, `DIRECTION`, `OPS_MANAGER`, `STOREKEEPER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `maintenance.preventive.manage` | later | `POST /preventive-plans`<br>`POST /preventive-plans/{plan_id}/suspend`<br>`POST /preventive-plans/{plan_id}/revise`<br>`POST /preventive-dues/{due_id}/schedule`<br>`POST /work-orders/{work_order_id}/complete-preventive`<br>`GET /work-orders/{work_order_id}/preventive-completion`<br>`POST /preventive-dues/evaluate`<br>`POST /preventive-declarations`<br>`POST /preventive-declarations/{declaration_id}/decide` | `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.preventive.read` | later | `GET /vehicles/{vehicle_id}/preventive-plans`<br>`GET /vehicles/{vehicle_id}/preventive-dues`<br>`GET /vehicles/{vehicle_id}/preventive-status`<br>`GET /preventive-dues`<br>`GET /vehicles/{vehicle_id}/preventive-declarations` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.work_order.read` | 1c | `GET /work-orders`<br>`GET /work-orders/{work_order_id}` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.work_order.request` | 1c | `POST /work-orders` | `DISPATCHER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.work_order.manage` | 1c | `POST /work-orders/{work_order_id}/decision`<br>`GET /maintenance-mechanics` | `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.work_order.execute` | 1c | `POST /work-orders/{work_order_id}/progress`<br>`POST /work-orders/{work_order_id}/labour` | `MECHANIC`, `WORKSHOP_CHIEF` |
| `maintenance.reliability.read` | 1c | `GET /maintenance/reliability` | `AUDITOR`, `DIRECTION`, `FINANCE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `maintenance.tyre.read` | 1c | `GET /tyres`<br>`GET /tyres/stock`<br>`GET /tyres/{tyre_id}` | `AUDITOR`, `DIRECTION`, `FINANCE`, `MECHANIC`, `OPS_MANAGER`, `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.tyre.manage` | 1c | `POST /tyres`<br>`POST /tyres/{tyre_id}/repair`<br>`POST /tyres/{tyre_id}/scrap` | `STOREKEEPER`, `WORKSHOP_CHIEF` |
| `maintenance.tyre.fit` | 1c | `POST /tyres/{tyre_id}/mount`<br>`POST /tyres/{tyre_id}/dismount`<br>`POST /tyres/{tyre_id}/inspections` | `MECHANIC`, `WORKSHOP_CHIEF` |
| `dispatch.location.read` | 1c | `GET /site-locations` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `HSE`, `OPS_MANAGER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `dispatch.location.manage` | 1c | `POST /site-locations`<br>`PATCH /site-locations/{site_location_id}` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `dispatch.material.read` | 1c | `GET /materials` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `HSE`, `OPS_MANAGER`, `TENANT_ADMIN`, `WORKSHOP_CHIEF` |
| `dispatch.material.manage` | 1c | `POST /materials`<br>`PATCH /materials/{material_id}` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `dispatch.mission.read` | 1c | `GET /missions`<br>`GET /missions/{mission_id}` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `dispatch.mission.create` | 1c | `POST /missions` | `DISPATCHER`, `OPS_MANAGER` |
| `dispatch.mission.progress` | 1c | `POST /missions/{mission_id}/events` | `DISPATCHER`, `OPS_MANAGER` |
| `dispatch.weighing.read` | 1c | `GET /weighing-tickets`<br>`GET /weighing-tickets/{weighing_ticket_id}` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `HSE`, `OPS_MANAGER` |
| `dispatch.weighing.record` | 1c | `POST /weighing-tickets` | `DISPATCHER`, `OPS_MANAGER` |
| `dispatch.weighing.approve` | 1c | `POST /weighing-tickets/{weighing_ticket_id}/approve` | `OPS_MANAGER` |
| `dispatch.weighing.correct` | 1c | `POST /weighing-tickets/{weighing_ticket_id}/void`<br>`POST /weighing-tickets/{weighing_ticket_id}/correct` | `OPS_MANAGER` |
| `dispatch.indicators.read` | 1c | `GET /dispatch-indicators` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `FINANCE`, `HSE`, `OPS_MANAGER` |
| `fleet.gps.share` | 1c | `GET /me/gps/vehicles`<br>`POST /me/gps/shares`<br>`POST /me/gps/shares/{share_id}/positions`<br>`POST /me/gps/shares/{share_id}/stop` | `DISPATCHER`, `DRIVER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.gps.manage` | 1c | `GET /vehicles/{vehicle_id}/gps/tracker`<br>`POST /vehicles/{vehicle_id}/gps/tracker`<br>`POST /vehicles/{vehicle_id}/gps/tracker/revoke` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `workforce.driver.link_account` | 1c | `GET /drivers/{driver_id}/gps-account`<br>`POST /drivers/{driver_id}/gps-account` | `TENANT_ADMIN` |
| `fuel.stock.read` | 1c | `GET /fuel/dashboard`<br>`GET /fuel/tanks`<br>`GET /fuel/pumps`<br>`GET /fuel/pumps/{fuel_pump_id}/meter-readings`<br>`GET /fuel/pumps/{fuel_pump_id}/reconciliations`<br>`GET /fuel/issues`<br>`GET /fuel/stocktakes`<br>`GET /fuel/alerts`<br>`GET /fuel/vehicles/{vehicle_id}/consumption` | `AUDITOR`, `DIRECTION`, `FINANCE`, `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.stock.manage` | 1c | `POST /fuel/tanks` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.pump.manage` | 1c | `POST /fuel/pumps`<br>`PUT /fuel/pumps/{fuel_pump_id}/anomaly-tolerance` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.anomaly.read` | 1c | `GET /fuel/anomaly-cases`<br>`GET /fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events` | `AUDITOR`, `DIRECTION`, `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.anomaly.manage` | 1c | `POST /fuel/pumps/{fuel_pump_id}/anomaly-cases`<br>`POST /fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.meter.record` | 1c | `POST /fuel/pumps/{fuel_pump_id}/meter-readings` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.stock.threshold` | 1c | `POST /fuel/tanks/{fuel_tank_id}/threshold` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.alert.acknowledge` | 1c | `POST /fuel/alerts/{fuel_stock_alert_id}/acknowledge` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.purchase.read` | 1c | `GET /fuel/suppliers`<br>`GET /fuel/purchases` | `AUDITOR`, `DIRECTION`, `FINANCE`, `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.supplier.manage` | 1c | `POST /fuel/suppliers` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.purchase.create` | 1c | `POST /fuel/purchases` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.purchase.decide` | 1c | `POST /fuel/purchases/{fuel_purchase_order_id}/decision` | `FINANCE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.purchase.receive` | 1c | `POST /fuel/purchases/{fuel_purchase_order_id}/receipts` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.stock.receive` | 1c | `POST /fuel/tanks/{fuel_tank_id}/receipts` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.stocktake.record` | 1c | `POST /fuel/tanks/{fuel_tank_id}/stocktakes` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.issue.request` | 1c | `POST /fuel/issues` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fuel.issue.decide` | 1c | `POST /fuel/issues/{fuel_issue_id}/decision` | `FUEL_MANAGER`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `legal.contract.create` | 1c | `POST /legal-contracts`<br>`POST /legal-contracts/{contract_id}/documents/preflight`<br>`POST /legal-contracts/{contract_id}/documents` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `legal.contract.read` | 1c | `GET /legal-contracts` | `AUDITOR`, `DIRECTION`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `legal.contract.submit` | 1c | `POST /legal-contracts/{contract_id}/submit` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `legal.contract.review` | 1c | `POST /legal-contracts/{contract_id}/decision`<br>`POST /legal-contracts/{contract_id}/documents/{document_id}/verify`<br>`GET /legal-contracts/storage-reconciliation` | `DIRECTION`, `TENANT_ADMIN` |
| `legal.insurance.create` | 1c | `POST /insurance-policies` | `FINANCE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `legal.insurance.read` | 1c | `GET /insurance-policies`<br>`GET /insurance-policies/expiring` | `AUDITOR`, `DIRECTION`, `FINANCE`, `HSE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `hse.incident.read` | 1c | `GET /hse/incidents`<br>`GET /hse/incidents/{hse_incident_id}`<br>`GET /hse/corrective-actions`<br>`GET /hse/summary` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `hse.incident.report` | 1c | `POST /hse/incidents`<br>`POST /hse/incidents/{hse_incident_id}/evidence` | `DISPATCHER`, `FUEL_MANAGER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `hse.incident.manage` | 1c | `POST /hse/incidents/{hse_incident_id}/transition`<br>`GET /hse/incidents/{hse_incident_id}/action-owners`<br>`POST /hse/incidents/{hse_incident_id}/actions`<br>`POST /hse/corrective-actions/{hse_corrective_action_id}/decision`<br>`GET /hse/inspections/{hse_inspection_id}/action-owners`<br>`POST /hse/inspections/{hse_inspection_id}/actions` | `HSE` |
| `hse.action.complete` | 1c | `POST /hse/corrective-actions/{hse_corrective_action_id}/complete` | `DISPATCHER`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `hse.inspection.read` | 1c | `GET /hse/inspections`<br>`GET /hse/inspections/{hse_inspection_id}`<br>`GET /hse/evidence/{hse_evidence_id}/content` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HSE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `hse.inspection.perform` | 1c | `GET /hse/checklist-templates`<br>`POST /hse/inspections`<br>`POST /hse/inspections/{hse_inspection_id}/evidence` | `DISPATCHER`, `FUEL_MANAGER`, `HSE`, `MECHANIC`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `hse.checklist.manage` | 1c | `POST /hse/checklist-templates`<br>`POST /hse/checklist-templates/{template_id}/deactivate` | `HSE` |
| `cost.vehicle.read` | 1c | `GET /costs/vehicles`<br>`GET /costs/vehicles/{vehicle_id}/history` | `AUDITOR`, `DIRECTION`, `FINANCE`, `OPS_MANAGER`, `WORKSHOP_CHIEF` |
| `cost.labour_rate.manage` | 1c | `GET /costs/labour-rates`<br>`POST /costs/labour-rates` | `DIRECTION`, `FINANCE` |
| `fleet.geofence.read` | 1c | `GET /geofences` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HSE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.geofence.manage` | 1c | `POST /geofences`<br>`POST /geofences/{site_geofence_id}/deactivate` | `HSE`, `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.gps_alert.read` | 1c | `GET /gps/alerts`<br>`GET /sites/{site_id}/gps-policy`<br>`GET /me/alert-notifications`<br>`PUT /me/alert-notifications` | `AUDITOR`, `DIRECTION`, `DISPATCHER`, `HSE`, `OPS_MANAGER` |
| `fleet.gps_alert.manage` | 1c | `POST /gps/alerts/{gps_alert_id}/acknowledge` | `DISPATCHER`, `HSE`, `OPS_MANAGER` |
| `fleet.gps_policy.manage` | 1c | `PUT /sites/{site_id}/gps-policy` | `OPS_MANAGER`, `TENANT_ADMIN` |
| `fleet.gps.history` | 1c | `GET /vehicles/{vehicle_id}/gps/track`<br>`GET /gps/geofence-events` | `AUDITOR`, `HSE`, `OPS_MANAGER` |

## 5. Couverture par rôle

| Rôle | Permissions | Routes API accessibles |
|---|---:|---:|
| `PLATFORM_ADMIN` | 6 | 16 |
| `TENANT_ADMIN` | 65 | 123 |
| `DIRECTION` | 34 | 91 |
| `OPS_MANAGER` | 84 | 176 |
| `DISPATCHER` | 37 | 81 |
| `HR` | 16 | 34 |
| `DRIVER` | 4 | 15 |
| `WORKSHOP_CHIEF` | 40 | 103 |
| `MECHANIC` | 17 | 45 |
| `STOREKEEPER` | 17 | 49 |
| `FUEL_MANAGER` | 28 | 62 |
| `HSE` | 33 | 77 |
| `FINANCE` | 22 | 53 |
| `AUDITOR` | 37 | 95 |

## 6. Anomalies détectées mécaniquement

- Permissions déclarées sans route : aucune.
- Permissions marquées `tranche: later` avec routes implémentées : `maintenance.preventive.manage`, `maintenance.preventive.read`.
- `organization.tenant.list` porte aussi le GET item `/platform/tenants/{{tenant_id}}` (dénommage list/read assumé, documenté dans l'en-tête du YAML).

## 7. Contrats de test associés

- Générés depuis le YAML : `backend/tests/test_authz_matrix.py` (concordance route↔permission, refus 403 audité, portée site) et `frontend/src/lib/permissions.generated.ts` (garde CI `gen_permissions.py --check`).
- Exécution navigateur par rôle : `.github/workflows/e2e-isolation.yml` (9 specs `e2e/`, parcours démo par rôle `e2e-demo/`, smoke public `e2e-smoke/`, hors-ligne `e2e-field/`).
- Toute évolution de la matrice RBAC doit régénérer ce document (`--check` recommandé en CI frontend).

