// Libellés français des énumérations (D-01 : valeurs anglaises côté API, français dans l'interface).

export const VEHICLE_STATUS: Record<string, string> = {
  AVAILABLE: "Disponible",
  IN_MAINTENANCE: "En maintenance",
  IMMOBILIZED: "Immobilisé",
  OUT_OF_SERVICE: "Hors service",
  RETIRED: "Réformé",
};

export const DRIVER_STATUS: Record<string, string> = {
  ACTIVE: "Actif",
  UNAVAILABLE: "Indisponible",
  SUSPENDED: "Suspendu",
  INACTIVE: "Inactif",
};

export const ASSIGNMENT_STATUS: Record<string, string> = {
  PLANNED: "Planifiée",
  ACTIVE: "Active",
  SUSPENDED: "Suspendue",
  COMPLETED: "Terminée",
  CANCELLED: "Annulée",
};

export const SUSPEND_REASONS: Record<string, string> = {
  BREAKDOWN: "Panne",
  DRIVER_ABSENT: "Conducteur absent",
  SAFETY: "Sécurité",
  WEATHER: "Météo",
  OPERATIONS: "Contrainte d'exploitation",
  OTHER: "Autre",
};

export const END_REASONS: Record<string, string> = {
  END_OF_SHIFT: "Fin de poste",
  BREAKDOWN: "Panne",
  REASSIGNMENT: "Réaffectation",
  NON_COMPLIANCE: "Non-conformité",
  OTHER: "Autre",
};

export const CANCEL_REASONS: Record<string, string> = {
  PLAN_CHANGED: "Planning modifié",
  DRIVER_UNAVAILABLE: "Conducteur indisponible",
  VEHICLE_UNAVAILABLE: "Véhicule indisponible",
  ENTRY_ERROR: "Erreur de saisie",
  OTHER: "Autre",
};

// Motifs d'inéligibilité (D-29), de non-conformité (US-1.25) et avertissements.
export const ISSUES: Record<string, string> = {
  ASSIGNMENT_SITE_MISMATCH: "Véhicule et conducteur ne sont pas sur le même site",
  ASSIGNMENT_BACKDATED: "Début trop ancien (antidatage interdit)",
  DRIVER_NOT_ACTIVE: "Conducteur non actif",
  VEHICLE_NOT_AVAILABLE: "Véhicule non disponible",
  VEHICLE_CATEGORY_WITHOUT_DRIVER: "Cette catégorie d'engin ne se conduit pas",
  DRIVER_LICENSE_MISSING: "Aucun permis enregistré",
  DRIVER_LICENSE_CATEGORY_MISSING: "Catégorie de permis insuffisante",
  DRIVER_LICENSE_EXPIRED: "Permis expiré ou non valide",
  DRIVER_LICENSE_EXPIRES_BEFORE_END: "Le permis expire avant la fin de l'affectation",
  DRIVER_QUALIFICATION_MISSING: "Habilitation de conduite manquante",
  DRIVER_QUALIFICATION_EXPIRED: "Habilitation expirée ou non valide",
  DRIVER_QUALIFICATION_EXPIRES_BEFORE_END: "L'habilitation expire avant la fin de l'affectation",
  LICENSE_EXPIRED: "Permis expiré ou non valide",
  QUALIFICATION_EXPIRED: "Habilitation expirée ou non valide",
  LICENSE_EXPIRING: "Permis bientôt expiré",
  QUALIFICATION_EXPIRING: "Habilitation bientôt expirée",
  NEXT_EXPIRY: "Prochaine échéance",
};

export function label(map: Record<string, string>, code: string | null | undefined): string {
  if (!code) return "—";
  return map[code] ?? code;
}
