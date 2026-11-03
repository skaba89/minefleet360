"""Référentiel des sociétés DEMO et des profils de volume.

Tout est fictif : raisons sociales préfixées « DEMO — », e-mails @<code>.example.com, téléphones +224000…,
immatriculations « DEMO-… ». Les régions (Boké, Boffa, Siguiri, Kamsar, Conakry) donnent un contexte
plausible ; aucun site ne correspond à une installation réelle et aucune coordonnée GPS n'est générée ici.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteSpec:
    code: str
    name: str
    site_type: str  # MINE, PORT, DEPOT, WORKSHOP… (contrainte de la table site)


@dataclass(frozen=True)
class FleetLine:
    category: str  # code de vehicle_category
    count: int  # profil small ; multiplié par Profile.fleet_factor
    prefix: str  # numéro de parc : DEMO-<prefix>-NNN
    make: str
    model: str
    payload_kg: int | None
    hauls: bool  # engin de transport affecté aux missions


@dataclass(frozen=True)
class TenantSpec:
    code: str
    legal_name: str
    sites: tuple[SiteSpec, ...]
    material: tuple[str, str]  # code, libellé du matériau transporté
    waste: tuple[str, str]
    fleet: tuple[FleetLine, ...]
    # Charge utile moyenne d'une rotation (kg) et dispersion, pour des pesées plausibles.
    net_kg: tuple[int, int]


TENANTS: tuple[TenantSpec, ...] = (
    TenantSpec(
        code="demo-bauxite",
        legal_name="DEMO — Bauxite Guinée Operations",
        sites=(
            SiteSpec("BOKE-MINE", "Mine fictive de Boké (DEMO)", "MINE"),
            SiteSpec("BOFFA-PORT", "Terminal fictif de Boffa (DEMO)", "PORT"),
        ),
        material=("BAUX", "Bauxite"),
        waste=("STER", "Stérile"),
        fleet=(
            FleetLine("RIGID_DUMP_TRUCK", 6, "CAM", "MarqueDémo", "Tombereau-60", 60_000, True),
            FleetLine("WHEEL_LOADER", 2, "CHG", "MarqueDémo", "Chargeuse-L9", None, False),
            FleetLine("HYDRAULIC_EXCAVATOR", 1, "PEL", "MarqueDémo", "Pelle-E35", None, False),
            FleetLine("MOTOR_GRADER", 1, "NIV", "MarqueDémo", "Niveleuse-G14", None, False),
            FleetLine("LIGHT_VEHICLE", 2, "VL", "MarqueDémo", "Pick-up 4x4", None, False),
        ),
        net_kg=(55_000, 4_000),
    ),
    TenantSpec(
        code="demo-or-hg",
        legal_name="DEMO — Mines Aurifères de Haute-Guinée",
        sites=(SiteSpec("SIGUIRI-MINE", "Mine fictive de Siguiri (DEMO)", "MINE"),),
        material=("MIN-OR", "Minerai aurifère"),
        waste=("STER", "Stérile"),
        fleet=(
            FleetLine("ARTICULATED_DUMP_TRUCK", 4, "CAM", "MarqueDémo", "Articulé-40", 38_000, True),
            FleetLine("HYDRAULIC_EXCAVATOR", 1, "PEL", "MarqueDémo", "Pelle-E30", None, False),
            FleetLine("BULLDOZER", 1, "BUL", "MarqueDémo", "Bouteur-D8", None, False),
            FleetLine("WATER_TANKER", 1, "ARR", "MarqueDémo", "Arroseuse-20", None, False),
            FleetLine("LIGHT_VEHICLE", 1, "VL", "MarqueDémo", "Pick-up 4x4", None, False),
        ),
        net_kg=(36_000, 2_500),
    ),
    TenantSpec(
        code="demo-tlm",
        legal_name="DEMO — Transport & Logistique Minière",
        sites=(
            SiteSpec("KAMSAR-DEPOT", "Dépôt fictif de Kamsar (DEMO)", "DEPOT"),
            SiteSpec("CONAKRY-ATELIER", "Atelier fictif de Conakry (DEMO)", "WORKSHOP"),
        ),
        material=("BAUX", "Bauxite"),
        waste=("REMB", "Remblai"),
        fleet=(
            FleetLine("ROAD_DUMP_TRUCK", 5, "CAM", "MarqueDémo", "Porteur-8x4", 32_000, True),
            FleetLine("FUEL_TANKER", 1, "CIT", "MarqueDémo", "Citerne-25", None, False),
            FleetLine("PERSONNEL_BUS", 1, "BUS", "MarqueDémo", "Bus-30", None, False),
            FleetLine("LIGHT_VEHICLE", 1, "VL", "MarqueDémo", "Pick-up 4x4", None, False),
        ),
        net_kg=(30_000, 2_000),
    ),
)

# Rôles attribués au niveau société (un compte chacun) et par site (un compte par site).
TENANT_ROLES = (
    "DIRECTION",
    "OPS_MANAGER",
    "HR",
    "WORKSHOP_CHIEF",
    "STOREKEEPER",
    "HSE",
    "FINANCE",
    "AUDITOR",
)
SITE_ROLES = ("DISPATCHER", "DRIVER", "MECHANIC", "FUEL_MANAGER")


@dataclass(frozen=True)
class Profile:
    name: str
    days: int  # période simulée, se terminant à la date d'ancrage
    fleet_factor: int
    drivers_per_hauler: int  # conducteurs créés par engin de transport (+ cas négatifs)
    missions_per_hauler_day: int
    rotations_per_mission: tuple[int, int]
    gps_step_minutes: int = 2  # intervalle entre deux positions GPS
    # Historique GPS limité aux N derniers jours (None : toute la période). Missions, pesées, carburant et
    # coûts couvrent toujours toute la période ; le compteur km reste calé sur la distance du tracé.
    gps_days: int | None = None


PROFILES: dict[str, Profile] = {
    # Mode 3 « QA et simulation » : jeu court et rapide pour les tests automatisés (mêmes scénarios).
    "qa": Profile(
        "qa",
        days=9,
        fleet_factor=1,
        drivers_per_hauler=1,
        missions_per_hauler_day=1,
        rotations_per_mission=(2, 3),
        gps_step_minutes=5,
    ),
    "small": Profile(
        "small",
        days=14,
        fleet_factor=1,
        drivers_per_hauler=1,
        missions_per_hauler_day=1,
        rotations_per_mission=(2, 4),
    ),
    "standard": Profile(
        "standard",
        days=90,
        fleet_factor=3,
        drivers_per_hauler=2,
        missions_per_hauler_day=1,
        rotations_per_mission=(3, 5),
        gps_step_minutes=3,
        gps_days=14,
    ),
    "large": Profile(
        "large",
        days=60,
        fleet_factor=8,
        drivers_per_hauler=2,
        missions_per_hauler_day=1,
        rotations_per_mission=(3, 5),
        gps_step_minutes=5,
        gps_days=7,
    ),
}

# Prénoms et noms génériques combinés aléatoirement ; le suffixe « (démo) » rend chaque personne
# reconnaissable comme fictive à l'écran (règle H9 : valeurs sentinelles).
FIRST_NAMES = (
    "Mamadou",
    "Aissatou",
    "Ibrahima",
    "Fatoumata",
    "Alpha",
    "Mariama",
    "Sekou",
    "Kadiatou",
    "Ousmane",
    "Hawa",
    "Abdoulaye",
    "Nènè",
    "Lansana",
    "Djénabou",
    "Moussa",
    "Saran",
)
LAST_NAMES = (
    "Démo-Bah",
    "Démo-Barry",
    "Démo-Camara",
    "Démo-Condé",
    "Démo-Diallo",
    "Démo-Keïta",
    "Démo-Kourouma",
    "Démo-Soumah",
    "Démo-Sylla",
    "Démo-Touré",
)
