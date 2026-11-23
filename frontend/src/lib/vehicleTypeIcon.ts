/** SVG silhouettes are stored as same-origin symbols in /fleet-icons.svg.
 * The existing vehicle_category_id remains the sole source of truth.
 */
export interface FleetCategoryIdentity {
  code: string;
  family?: string;
  label_fr?: string;
}

export type FleetIconName =
  | "dump-truck" | "articulated-truck" | "road-truck" | "tanker" | "excavator"
  | "loader" | "bulldozer" | "grader" | "bus" | "pickup" | "motorcycle"
  | "crane" | "van" | "fleet";

export function vehicleTypeIcon(category: FleetCategoryIdentity | null | undefined): FleetIconName {
  if (!category) return "fleet";
  const code = category.code.toUpperCase();
  if (/ARTICULATED_DUMP|ARTICULATED_TRUCK/.test(code)) return "articulated-truck";
  if (/RIGID_DUMP|MINING_DUMP|HAUL_TRUCK/.test(code)) return "dump-truck";
  if (/ROAD_DUMP|TIPPER/.test(code)) return "road-truck";
  if (/FUEL_TANKER|WATER_TANKER|TANKER|CISTERN/.test(code)) return "tanker";
  if (/EXCAVATOR|BACKHOE|PELLE/.test(code)) return "excavator";
  if (/WHEEL_LOADER|FRONT_LOADER|LOADER|FORKLIFT/.test(code)) return "loader";
  if (/BULLDOZER|DOZER|COMPACTOR/.test(code)) return "bulldozer";
  if (/MOTOR_GRADER|GRADER/.test(code)) return "grader";
  if (/CRANE|LEVAGE/.test(code)) return "crane";
  if (/BUS|MINIBUS|COACH/.test(code)) return "bus";
  if (/MOTORCYCLE|MOTO|SCOOTER/.test(code)) return "motorcycle";
  if (/PICKUP|PICK_UP|LIGHT_VEHICLE|SUV|CAR|SEDAN|VEHICULE_LEGER/.test(code)) return "pickup";
  if (/VAN|MINIVAN/.test(code)) return "van";
  if (/DUMP/.test(code)) return "dump-truck";
  if (/TRUCK|LORRY|TRAILER|TRACTOR/.test(code)) return "road-truck";
  const family = (category.family ?? "").toUpperCase();
  if (/MINING|EARTHMOV|CONSTRUCTION|ENGIN/.test(family)) return "loader";
  if (/TRANSPORT|HAUL|HEAVY|TRUCK/.test(family)) return "road-truck";
  if (/PASSENGER|PERSONNEL|BUS/.test(family)) return "bus";
  return "fleet";
}

/** Only trusted IDs from the fixed union are interpolated (never from user input). */
export function fleetIconHref(icon: FleetIconName): string {
  return `/fleet-icons.svg#${icon}`;
}
