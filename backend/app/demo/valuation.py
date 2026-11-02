"""Lot 2 du générateur DEMO : coûts valorisés et atelier complet.

- carburant acheté sur bon de commande chiffré (GNF), approuvé par la finance (quatre yeux), réceptionné ;
- taux horaire de main-d'œuvre société ; relevés quotidiens des compteurs (km et heures) ;
- magasin de pièces valorisé ; pièces réservées puis consommées sur l'ordre de travail ;
- pneus individualisés montés et inspectés ; un pneu usé déposé, réformé et remplacé par un pneu neuf acheté ;
- checklist HSE « avant poste » et inspections quotidiennes, dont une non conforme sur un point critique.

Prix et taux : HYPOTHÈSES FICTIVES de démonstration (ordres de grandeur plausibles en GNF), à remplacer
par les valeurs réelles d'un client. Les pneus montés au départ sont une reprise d'inventaire SANS prix
d'achat connu : leur coût n'est pas inventé (composante « Partiel ») ; seuls les pneus achetés pendant la
période sont valorisés.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.core.clock import FrozenClock
from app.costs import router as costs_router
from app.demo.runtime import call, route
from app.fleet import records
from app.fleet.schemas import MeterReadingCreate
from app.fuel import service as fuel
from app.fuel.schemas import PurchaseCreate, PurchaseDecisionCreate, PurchaseReceiptCreate, SupplierCreate
from app.hse import inspections as hse_inspections
from app.maintenance import parts_router
from app.maintenance import router as maintenance_router
from app.maintenance import tyre_service as tyres
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate

if TYPE_CHECKING:
    import random

    from app.demo.catalog import Profile, TenantSpec
    from app.demo.generator import DemoReport
    from app.seed import _Actor

LABOUR_RATE_GNF = Decimal("85000.00")
FUEL_PRICE_GNF = (12_400, 13_200)  # par litre, tiré par livraison
# code, libellé, prix unitaire GNF, quantité initiale par magasin
PARTS = (
    ("FLEX-HYD-01", "Flexible hydraulique de levage", "1450000", "6"),
    ("HUILE-HYD-20L", "Huile hydraulique (bidon 20 L)", "620000", "20"),
    ("FILT-GO-01", "Filtre à gazole", "350000", "24"),
    ("FILT-HUILE-01", "Filtre à huile moteur", "290000", "24"),
    ("PLAQ-FREIN-01", "Jeu de plaquettes de frein", "1980000", "8"),
    ("COURROIE-01", "Courroie d'alternateur", "410000", "10"),
)
TYRE_SIZE = {
    "RIGID_DUMP_TRUCK": ("24.00R35", Decimal("62.0"), "DRIVE"),
    "ARTICULATED_DUMP_TRUCK": ("23.5R25", Decimal("48.0"), "ALL_POSITION"),
    "ROAD_DUMP_TRUCK": ("315/80R22.5", Decimal("18.0"), "DRIVE"),
}
TYRE_PRICE_GNF = {"24.00R35": "168000000", "23.5R25": "64000000", "315/80R22.5": "5200000"}
POSITIONS = ("AV-G", "AV-D", "AR-G-INT", "AR-G-EXT", "AR-D-INT", "AR-D-EXT")
CHECKLIST = (
    ("freins", "Freins de service et de parc efficaces", True),
    ("eclairage", "Feux, gyrophare et avertisseur de recul", True),
    ("pneus", "Pneus sans coupure ni sous-gonflage visible", False),
    ("fuites", "Absence de fuite (gazole, huile, hydraulique)", False),
    ("extincteur", "Extincteur présent et vérifié", True),
    ("ceinture", "Ceinture de sécurité en bon état", True),
)


class ValuationMixin:
    """Méthodes ajoutées au constructeur de société DEMO (attributs fournis par _TenantBuilder)."""

    if TYPE_CHECKING:
        spec: TenantSpec
        profile: Profile
        rng: random.Random
        clock: FrozenClock
        start: datetime
        report: DemoReport
        site_ids: dict[str, uuid.UUID]
        haulers: list[dict[str, Any]]
        tanks: dict[str, uuid.UUID]
        fuel_level: dict[str, Decimal]
        capacity: Decimal

        def actor(self, role: str, site: str | None = None) -> _Actor: ...
        def at(self, moment: datetime) -> datetime: ...

    suppliers: dict[str, uuid.UUID]
    stores: dict[str, uuid.UUID]
    parts: dict[str, uuid.UUID]
    checklist_id: uuid.UUID
    po_seq: int

    # --- socle --------------------------------------------------------------------------------------
    def valuation_setup(self) -> None:
        self.suppliers, self.stores, self.parts, self.po_seq = {}, {}, {}, 0
        self._labour_rate()
        self._meters_baseline()
        self._parts_catalog()
        self._tyres_initial()
        self._checklist()
        self._preventive_plans()

    def _labour_rate(self) -> None:
        call(
            self.actor("FINANCE"),
            "cost.labour_rate.manage",
            lambda auth: costs_router.create_labour_rate(
                costs_router.LabourRateIn(
                    hourly_rate=LABOUR_RATE_GNF,
                    currency="GNF",
                    valid_from=self.start.date() - timedelta(days=30),
                ),
                auth,
            ),
        )
        self.report.add("labour_rates")

    def _meters_baseline(self) -> None:
        moment = self.start + timedelta(hours=1, minutes=30)
        for hauler in self.haulers:
            hauler.setdefault("km", Decimal(self.rng.randint(30_000, 220_000)))
            self._read_meters(hauler, moment)

    def _read_meters(self, hauler: dict[str, Any], moment: datetime) -> None:
        self.at(moment)
        actor = self.actor("DISPATCHER", hauler["site"])
        for kind, value in (("ODOMETER_KM", hauler["km"]), ("HOUR_METER", hauler["meter"])):
            call(
                actor,
                "fleet.meter.record",
                records.record_reading,
                hauler["vehicle_id"],
                MeterReadingCreate(meter_kind=kind, value=value, read_at=moment),
            )
            self.report.add("meter_readings")

    def daily_meters(self, hauler: dict[str, Any], day: date) -> None:
        """Fin de poste : relevés après les missions du jour (progression plausible, jamais en baisse)."""
        self._read_meters(hauler, datetime.combine(day, time(18, 30), UTC))

    # --- carburant valorisé --------------------------------------------------------------------------
    def purchase_fuel(self, site: str, moment: datetime, liters: Decimal) -> None:
        """Commande chiffrée → approbation finance → livraison, bornée par la place libre de la cuve."""
        liters = min(liters, (self.capacity - self.fuel_level[site]) // 1000 * 1000)
        if liters < 5000:
            return
        manager = self.actor("FUEL_MANAGER", site)
        if site not in self.suppliers:
            self.at(moment - timedelta(hours=21))
            supplier = call(
                manager,
                "fuel.supplier.manage",
                fuel.create_supplier,
                SupplierCreate(
                    site_id=self.site_ids[site], code="FOURN-GO-1", name="Pétrolier fictif (DEMO)"
                ),
            )
            self.suppliers[site] = supplier.fuel_supplier_id
        self.po_seq += 1
        ordered = self.at(moment - timedelta(hours=20))
        order = call(
            manager,
            "fuel.purchase.create",
            fuel.create_purchase,
            PurchaseCreate(
                fuel_supplier_id=self.suppliers[site],
                fuel_tank_id=self.tanks[site],
                reference=f"BC-DEMO-{self.po_seq:05d}",
                quantity_liters=liters,
                unit_price=Decimal(self.rng.randint(*FUEL_PRICE_GNF)),
                currency="GNF",
                ordered_at=ordered,
            ),
        )
        order_id = order["fuel_purchase_order_id"]
        self.at(ordered + timedelta(hours=2))
        call(
            self.actor("FINANCE"),
            "fuel.purchase.decide",
            fuel.decide_purchase,
            order_id,
            PurchaseDecisionCreate(decision="APPROVED"),
        )
        self.at(moment)
        call(
            manager,
            "fuel.purchase.receive",
            fuel.receive_purchase,
            order_id,
            PurchaseReceiptCreate(
                liters=liters, delivery_reference=f"BL-DEMO-{self.po_seq:05d}", occurred_at=moment
            ),
        )
        self.fuel_level[site] += liters
        self.report.add("fuel_purchases")

    # --- pièces ---------------------------------------------------------------------------------------
    def _parts_catalog(self) -> None:
        keeper = self.actor("STOREKEEPER")
        self.at(self.start + timedelta(hours=2, minutes=30))
        for code, name, _, _ in PARTS:
            part = route(
                keeper,
                "maintenance.parts.manage",
                parts_router.create_part,
                parts_router.PartCreate(code=code, name=name),
            )
            self.parts[code] = part.spare_part_id
            self.report.add("spare_parts")
        for site in self.spec.sites:
            store = route(
                keeper,
                "maintenance.parts.manage",
                parts_router.create_part_store,
                parts_router.StoreCreate(
                    site_id=self.site_ids[site.code], code=f"MAG-{site.code}", name="Magasin principal"
                ),
            )
            self.stores[site.code] = store.spare_part_store_id
            for code, _, price, quantity in PARTS:
                route(
                    keeper,
                    "maintenance.parts.receive",
                    parts_router.receive_valued_part,
                    parts_router.ValuedPartReceiptIn(
                        spare_part_store_id=store.spare_part_store_id,
                        spare_part_id=self.parts[code],
                        quantity=Decimal(quantity),
                        unit_cost=Decimal(price),
                        currency="GNF",
                        reference=f"BL-PIECES-{site.code}-{code}",
                    ),
                )
                self.report.add("part_receipts")

    def consume_parts(self, work_order_id: uuid.UUID, site: str, items: tuple[tuple[str, str], ...]) -> None:
        """Réservation sur l'OT puis consommation (sortie de magasin valorisée au CMP)."""
        chief = self.actor("WORKSHOP_CHIEF")
        for code, quantity in items:
            reservation = route(
                chief,
                "maintenance.parts.reserve",
                parts_router.reserve_part,
                parts_router.PartReservationIn(
                    work_order_id=work_order_id,
                    spare_part_store_id=self.stores[site],
                    spare_part_id=self.parts[code],
                    quantity=Decimal(quantity),
                    reference=f"RES-{code}",
                ),
            )
            route(
                chief,
                "maintenance.parts.consume",
                parts_router.consume_part_reservation,
                reservation.spare_part_reservation_id,
            )
            self.report.add("part_issues")

    # --- pneus ------------------------------------------------------------------------------------------
    def _new_tyre(self, site: str, category: str, serial: str, *, priced: bool) -> tuple[uuid.UUID, int]:
        size, tread, cat = TYRE_SIZE[category]
        tyre = call(
            self.actor("STOREKEEPER"),
            "maintenance.tyre.manage",
            tyres.create_tyre,
            tyres.TyreCreate(
                site_id=self.site_ids[site],
                serial_number=serial,
                brand="MarqueDémo",
                model="Chantier-E4",
                size=size,
                category=cat,
                purchase_cost=Decimal(TYRE_PRICE_GNF[size]) if priced else None,
                currency="GNF" if priced else None,
                initial_tread_mm=tread,
                scrap_tread_mm=Decimal("6.0") if tread > 30 else Decimal("3.0"),
                nominal_pressure_kpa=700 if tread > 30 else 850,
            ),
        )
        self.report.add("tyres")
        return tyre.tyre_id, tyre.row_version

    def _tyres_initial(self) -> None:
        self.at(self.start + timedelta(hours=3))
        chief = self.actor("WORKSHOP_CHIEF")
        n = 0
        for hauler in self.haulers:
            hauler["tyres"] = {}
            for position in POSITIONS:
                n += 1
                tyre_id, version = self._new_tyre(
                    hauler["site"],
                    hauler["category"],
                    f"DEMO-PN-{self.spec.code[5:9].upper()}-{n:05d}",
                    priced=False,
                )
                mounted = call(
                    chief,
                    "maintenance.tyre.fit",
                    tyres.mount,
                    tyre_id,
                    tyres.TyreMount(
                        vehicle_id=hauler["vehicle_id"],
                        position_code=position,
                        odometer_km=hauler["km"],
                        hour_meter=hauler["meter"],
                    ),
                    version,
                )
                hauler["tyres"][position] = {
                    "id": tyre_id,
                    "version": mounted.row_version,
                    "tread": TYRE_SIZE[hauler["category"]][1] - Decimal(self.rng.randint(10, 30)),
                }
                self.report.add("tyres_mounted")
        self.spares: dict[str, list[tuple[uuid.UUID, int]]] = {}
        for site in self.spec.sites:
            categories = {h["category"] for h in self.haulers if h["site"] == site.code}
            for category in sorted(categories):
                n += 1
                self.spares.setdefault(site.code, []).append(
                    self._new_tyre(
                        site.code, category, f"DEMO-PN-{self.spec.code[5:9].upper()}-{n:05d}", priced=True
                    )
                )

    def inspect_tyres(self, day: date) -> None:
        """Tournée d'inspection : usure mesurée, compteurs relevés (base de l'estimation au km)."""
        moment = datetime.combine(day, time(17, 0), UTC)
        for hauler in self.haulers:
            if hauler.get("down_until") and hauler["down_until"] > day:
                continue
            mechanic = self.actor("MECHANIC", hauler["site"])
            for state in hauler["tyres"].values():
                self.at(moment)
                state["tread"] = max(Decimal("1.0"), state["tread"] - Decimal(self.rng.randint(5, 25)) / 10)
                out = call(
                    mechanic,
                    "maintenance.tyre.fit",
                    tyres.inspect,
                    state["id"],
                    tyres.TyreInspection(
                        tread_mm=state["tread"],
                        pressure_kpa=self.rng.randint(640, 760)
                        if state["tread"] > 30
                        else self.rng.randint(780, 900),
                        odometer_km=hauler["km"],
                        hour_meter=hauler["meter"],
                    ),
                    state["version"],
                )
                state["version"] = out.row_version
                self.report.add("tyre_inspections")
                moment += timedelta(minutes=2)

    def replace_worn_tyre(self, day: date) -> None:
        """Pneu usé à la limite : dépose (usure), réforme, montage d'un pneu neuf acheté (valorisé)."""
        hauler = next((h for h in self.haulers if self.spares.get(h["site"])), None)
        if hauler is None:
            return
        position = "AR-G-EXT"
        state = hauler["tyres"][position]
        scrap_limit = Decimal("6.0") if TYRE_SIZE[hauler["category"]][1] > 30 else Decimal("3.0")
        chief = self.actor("WORKSHOP_CHIEF")
        moment = self.at(datetime.combine(day, time(16, 0), UTC))
        out = call(
            chief,
            "maintenance.tyre.fit",
            tyres.dismount,
            state["id"],
            tyres.TyreDismount(
                reason_code="WEAR", tread_mm=scrap_limit, odometer_km=hauler["km"], hour_meter=hauler["meter"]
            ),
            state["version"],
        )
        self.at(moment + timedelta(minutes=30))
        call(
            self.actor("STOREKEEPER"),
            "maintenance.tyre.manage",
            tyres.scrap,
            state["id"],
            tyres.TyreScrap(
                reason_code="WORN_OUT", tread_mm=scrap_limit, note="Usure à la limite de réforme."
            ),
            out.row_version,
        )
        self.report.add("tyres_scrapped")
        spare_id, spare_version = self.spares[hauler["site"]].pop(0)
        self.at(moment + timedelta(minutes=50))
        mounted = call(
            chief,
            "maintenance.tyre.fit",
            tyres.mount,
            spare_id,
            tyres.TyreMount(
                vehicle_id=hauler["vehicle_id"],
                position_code=position,
                odometer_km=hauler["km"],
                hour_meter=hauler["meter"],
            ),
            spare_version,
        )
        hauler["tyres"][position] = {
            "id": spare_id,
            "version": mounted.row_version,
            "tread": TYRE_SIZE[hauler["category"]][1],
        }
        self.report.add("tyres_mounted")

    # --- préventif ----------------------------------------------------------------------------------
    def _preventive_plans(self) -> None:
        """Plan d'entretien par engin de transport (heures + calendrier ; km pour les porteurs routiers).

        Seuls les plans sont créés : la génération automatique des échéances n'est pas activée dans le produit
        (docs/PREVENTIVE_OT_TRANSACTION.md) ; la démo ne fabrique donc aucune échéance."""
        chief = self.actor("WORKSHOP_CHIEF")
        for hauler in self.haulers:
            road = hauler["category"] == "ROAD_DUMP_TRUCK"
            route(
                chief,
                "maintenance.preventive.manage",
                maintenance_router.create_preventive_plan,
                PreventivePlanCreate(
                    vehicle_id=hauler["vehicle_id"],
                    code="ENTRETIEN-A",
                    km_interval=Decimal("10000") if road else None,
                    hours_interval=None if road else Decimal("250"),
                    days_interval=90,
                ),
            )
            self.report.add("preventive_plans")

    # --- inspections HSE ----------------------------------------------------------------------------
    def _checklist(self) -> None:
        template = route(
            self.actor("HSE"),
            "hse.checklist.manage",
            hse_inspections.create_template,
            hse_inspections.TemplateCreate(
                code="AVANT-POSTE-ENGIN",
                name="Contrôle avant poste — engin de transport",
                target_type="VEHICLE",
                items=[
                    hse_inspections.ChecklistItem(key=k, label=label, critical=c) for k, label, c in CHECKLIST
                ],
            ),
        )
        self.checklist_id = template.hse_checklist_template_id
        self.report.add("hse_checklists")

    def pre_shift_inspection(self, hauler: dict[str, Any], day: date, *, failing: str | None = None) -> None:
        moment = self.at(datetime.combine(day, time(5, 40), UTC) + timedelta(minutes=self.rng.randint(0, 15)))
        answers = [
            hse_inspections.AnswerIn(
                item_key=key,
                result="NON_COMPLIANT" if key == failing else "COMPLIANT",
                comment="Course de pédale anormale, engin consigné." if key == failing else None,
            )
            for key, _, _ in CHECKLIST
        ]
        route(
            self.actor("DISPATCHER", hauler["site"]),
            "hse.inspection.perform",
            hse_inspections.create_inspection,
            hse_inspections.InspectionCreate(
                site_id=self.site_ids[hauler["site"]],
                hse_checklist_template_id=self.checklist_id,
                vehicle_id=hauler["vehicle_id"],
                performed_at=moment,
                answers=answers,
            ),
        )
        self.report.add("hse_inspections")
        if failing:
            self.report.add("hse_inspections_non_compliant")
