/** Fleet pictograms are derived from the existing vehicle category catalog.
 * No new field in the database: changing a category updates its icon everywhere.
 * The status colour is independent of the type pictogram.
 */
export interface FleetCategoryIdentity {
  code: string;
  family?: string;
  label_fr?: string;
}

export function vehicleTypeIcon(category: FleetCategoryIdentity | null | undefined): string {
  if (!category) return "🚗";
  const code = category.code.toUpperCase();
  if (/EXCAVATOR|BACKHOE|PELLE/.test(code)) return "🚜";
  if (/BULLDOZER|DOZER|GRADER|TRACTOR|WHEEL_LOADER|LOADER|FORKLIFT|COMPACTOR/.test(code)) return "🚜";
  if (/BUS|MINIBUS|COACH/.test(code)) return "🚌";
  if (/MOTORCYCLE|MOTO|SCOOTER/.test(code)) return "🏍️";
  if (/AMBULANCE|EMERGENCY/.test(code)) return "🚑";
  if (/CRANE|LEVAGE/.test(code)) return "🏗️";
  if (/DUMP|TRUCK|TANKER|TIPPER|HAUL|TRACTOR_TRAILER|LORRY/.test(code)) return "🚚";
  if (/VAN|PICKUP|PICK_UP|LIGHT_VEHICLE|SUV|CAR|SEDAN|VEHICULE_LEGER/.test(code)) return "🚙";
  const family = (category.family ?? "").toUpperCase();
  if (/MINING|EARTHMOV|CONSTRUCTION|ENGIN/.test(family)) return "🚜";
  if (/TRANSPORT|HAUL|HEAVY|TRUCK/.test(family)) return "🚚";
  if (/PASSENGER|PERSONNEL|BUS/.test(family)) return "🚌";
  return "🚗";
}
