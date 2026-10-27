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
  SAFETY_STOP: "Arrêt pour raison de sécurité (automatique)",
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
  ASSIGNMENT_NOT_ACTIVE: "Affectation pas encore active (prise de poste à faire)",
  ASSIGNMENT_ENDED: "Affectation terminée",
  ASSIGNMENT_SITE_MISMATCH: "Véhicule et conducteur ne sont pas sur le même site",
  ASSIGNMENT_BACKDATED: "Début trop ancien (antidatage interdit)",
  ASSIGNMENT_TOO_FAR_AHEAD: "Début trop lointain (au-delà de l'horizon de planification)",
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

// --- Parc ----------------------------------------------------------------------------------------------

export const VEHICLE_REASONS: Record<string, string> = {
  BREAKDOWN: "Panne",
  ACCIDENT: "Accident",
  DOCUMENT_EXPIRED: "Document expiré",
  AWAITING_PARTS: "En attente de pièces",
  SAFETY_BAN: "Interdiction de sécurité",
  PREVENTIVE_MAINTENANCE: "Maintenance préventive",
  RECEPTION_IN_PROGRESS: "Réception en cours",
  END_OF_LIFE: "Fin de vie",
  TOTAL_LOSS: "Perte totale",
  SOLD: "Vendu",
  OTHER: "Autre",
};

export const OWNERSHIP: Record<string, string> = {
  OWNED: "En propre",
  LEASED: "En location",
  SUBCONTRACTED: "Sous-traité",
};

export const FUEL: Record<string, string> = {
  DIESEL: "Gazole",
  PETROL: "Essence",
  ELECTRIC: "Électrique",
  OTHER: "Autre",
};

// --- Personnel -----------------------------------------------------------------------------------------

export const EMPLOYMENT: Record<string, string> = {
  EMPLOYEE: "Salarié",
  TEMP_AGENCY: "Intérimaire",
  SUBCONTRACTOR: "Sous-traitant",
};

export const UNAVAILABILITY_REASONS: Record<string, string> = {
  LEAVE: "Congé",
  TRAINING: "Formation",
  OTHER: "Autre",
};

export const SUSPENSION_REASONS: Record<string, string> = {
  HSE_DECISION: "Décision HSE",
  INVESTIGATION: "Enquête en cours",
  LICENSE_ISSUE: "Problème de permis",
  OTHER: "Autre",
};

export const QUALIFICATION_TYPES: Record<string, string> = {
  DRIVING_AUTHORIZATION: "Habilitation de conduite",
  SAFETY_TRAINING: "Formation sécurité",
  OTHER: "Autre",
};

export const DOCUMENT_STATUS: Record<string, string> = {
  VALID: "Valide",
  SUSPENDED: "Suspendu",
  WITHDRAWN: "Retiré",
  REVOKED: "Révoqué",
};

// Validité DÉRIVÉE des dates et du statut (D-03), calculée par le serveur.
export const VALIDITY: Record<string, string> = {
  VALID: "Valide",
  EXPIRING: "Expire bientôt",
  EXPIRED: "Expiré",
  NOT_YET_VALID: "Pas encore valide",
  SUSPENDED: "Suspendu",
  WITHDRAWN: "Retiré",
  REVOKED: "Révoqué",
};

export const VALIDITY_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  VALID: "ok",
  EXPIRING: "warn",
  EXPIRED: "bad",
  NOT_YET_VALID: "neutral",
  SUSPENDED: "bad",
  WITHDRAWN: "bad",
  REVOKED: "bad",
};

// --- Dispatch (lot 2a) --------------------------------------------------------------------------------

export const MISSION_STATUS: Record<string, string> = {
  PLANNED: "Planifiée",
  ASSIGNED: "Affectée",
  EN_ROUTE_EMPTY: "En route à vide",
  LOADING: "En chargement",
  EN_ROUTE_LOADED: "En route chargé",
  UNLOADING: "En déchargement",
  SUSPENDED: "Suspendue",
  COMPLETED: "Terminée",
  CANCELLED: "Annulée",
};

export const MISSION_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  PLANNED: "neutral",
  ASSIGNED: "neutral",
  EN_ROUTE_EMPTY: "ok",
  LOADING: "ok",
  EN_ROUTE_LOADED: "ok",
  UNLOADING: "ok",
  SUSPENDED: "warn",
  COMPLETED: "neutral",
  CANCELLED: "neutral",
};

// Libellé de l'action qui déclenche l'événement (boutons) et de l'événement lui-même (chronologie).
export const MISSION_EVENTS: Record<string, string> = {
  CREATED: "Mission créée",
  DEPARTED: "Départ",
  ARRIVED_LOADING: "Arrivée au chargement",
  LOADED: "Chargement terminé",
  ARRIVED_UNLOADING: "Arrivée au déchargement",
  UNLOADED: "Déchargé, rotation suivante",
  COMPLETED: "Mission terminée",
  SUSPENDED: "Suspension",
  RESUMED: "Reprise",
  REASSIGNED: "Réaffectation",
  CANCELLED: "Annulation",
};

export const MISSION_REASONS: Record<string, string> = {
  BREAKDOWN: "Panne",
  HSE_STOP: "Arrêt HSE",
  WEATHER: "Météo",
  ROAD_BLOCKED: "Piste coupée",
  DRIVER_UNAVAILABLE: "Conducteur indisponible",
  PLAN_CHANGED: "Planning modifié",
  ENTRY_ERROR: "Erreur de saisie",
  OTHER: "Autre",
};

export const LOCATION_KINDS: Record<string, string> = {
  LOADING_POINT: "Point de chargement",
  DUMP_POINT: "Point de déchargement",
  STOCKPILE: "Stock",
  CRUSHER: "Concasseur",
  WEIGHBRIDGE: "Pont-bascule",
  PORT: "Port",
  OTHER: "Autre",
};

export const ROTATION_STATUS: Record<string, string> = {
  OPEN: "En cours",
  COMPLETED: "Terminée",
  ABORTED: "Interrompue",
};

/** Durée en heures et minutes (cycle de rotation). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

// --- Pesées (lot 2b) -----------------------------------------------------------------------------------

export const WEIGHING_SOURCE: Record<string, string> = {
  WEIGHBRIDGE: "Pont-bascule",
  MANUAL_DEGRADED: "Saisie manuelle (pont en panne)",
};

export const WEIGHING_STATUS: Record<string, string> = {
  VALID: "Valide",
  PENDING_APPROVAL: "À approuver",
  VOIDED: "Annulée",
};

export const WEIGHING_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  VALID: "ok",
  PENDING_APPROVAL: "warn",
  VOIDED: "neutral",
};

export const DEGRADED_REASONS: Record<string, string> = {
  WEIGHBRIDGE_DOWN: "Pont-bascule en panne",
  POWER_OUTAGE: "Coupure de courant",
  CALIBRATION: "Étalonnage en cours",
  NETWORK_DOWN: "Réseau indisponible",
  OTHER: "Autre",
};

export const VOID_REASONS: Record<string, string> = {
  ENTRY_ERROR: "Erreur de saisie",
  WRONG_ROTATION: "Mauvaise rotation",
  WRONG_VEHICLE: "Mauvais véhicule",
  DUPLICATE: "Doublon",
  CALIBRATION_ISSUE: "Pont mal étalonné",
  OTHER: "Autre",
};

/** Masse en tonnes (affichage) à partir de kilogrammes entiers (stockage). */
export function formatTonnes(kg: number | null | undefined): string {
  if (kg === null || kg === undefined) return "—";
  return `${(kg / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`;
}
