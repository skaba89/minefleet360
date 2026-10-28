// FICHIER GÉNÉRÉ par scripts/gen_permissions.py depuis backend/app/authz/authz_matrix.yaml.
// Ne pas modifier à la main : relancer le script après tout changement de la matrice.
export const GRANTS = {
  "assignment.vehicle_assignment.create": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "assignment.vehicle_assignment.end": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "assignment.vehicle_assignment.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FUEL_MANAGER": [
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "assignment.vehicle_assignment.update": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "audit.event.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "dispatch.indicators.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.location.manage": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "dispatch.location.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.material.manage": {
    "OPS_MANAGER": [
      "TENANT"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "dispatch.material.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.mission.create": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.mission.progress": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.mission.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.weighing.approve": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.weighing.correct": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.weighing.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "dispatch.weighing.record": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "fleet.vehicle.create": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "fleet.vehicle.deactivate": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "fleet.vehicle.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "FUEL_MANAGER": [
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "MECHANIC": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "STOREKEEPER": [
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "fleet.vehicle.update": {
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "fleet.vehicle.update_status": {
    "DISPATCHER": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "fleet.vehicle_category.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "FUEL_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "MECHANIC": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "STOREKEEPER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "identity.role.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "PLATFORM_ADMIN": [
      "PLATFORM"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.role_assignment.create": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.role_assignment.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.role_assignment.revoke": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.session.revoke_any": {},
  "identity.session.revoke_own": {},
  "identity.user.create": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.deactivate": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "HR": [
      "TENANT"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.reset_credentials": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.reset_mfa": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.update": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "identity.user.update_self": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "DRIVER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "FUEL_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "MECHANIC": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "PLATFORM_ADMIN": [
      "PLATFORM"
    ],
    "STOREKEEPER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "organization.site.create": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "organization.site.deactivate": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "organization.site.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "FUEL_MANAGER": [
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "MECHANIC": [
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "STOREKEEPER": [
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "organization.site.update": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "organization.tenant.create": {
    "PLATFORM_ADMIN": [
      "PLATFORM"
    ]
  },
  "organization.tenant.list": {
    "PLATFORM_ADMIN": [
      "PLATFORM"
    ]
  },
  "organization.tenant.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "DRIVER": [
      "SITE"
    ],
    "FINANCE": [
      "TENANT",
      "SITE"
    ],
    "FUEL_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "MECHANIC": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "STOREKEEPER": [
      "TENANT",
      "SITE"
    ],
    "TENANT_ADMIN": [
      "TENANT"
    ],
    "WORKSHOP_CHIEF": [
      "TENANT",
      "SITE"
    ]
  },
  "organization.tenant.suspend": {
    "PLATFORM_ADMIN": [
      "PLATFORM"
    ]
  },
  "organization.tenant.update": {
    "TENANT_ADMIN": [
      "TENANT"
    ]
  },
  "workforce.driver.create": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver.deactivate": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "FUEL_MANAGER": [
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "workforce.driver.update": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver_license.manage": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver_license.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver_qualification.manage": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  },
  "workforce.driver_qualification.read": {
    "AUDITOR": [
      "TENANT"
    ],
    "DIRECTION": [
      "TENANT"
    ],
    "DISPATCHER": [
      "SITE"
    ],
    "HR": [
      "TENANT",
      "SITE"
    ],
    "HSE": [
      "TENANT",
      "SITE"
    ],
    "OPS_MANAGER": [
      "TENANT",
      "SITE"
    ],
    "WORKSHOP_CHIEF": [
      "SITE"
    ]
  },
  "workforce.driver_qualification.revoke": {
    "HR": [
      "TENANT",
      "SITE"
    ]
  }
} as const satisfies Record<string, Record<string, readonly string[]>>;

export type Permission = keyof typeof GRANTS;
