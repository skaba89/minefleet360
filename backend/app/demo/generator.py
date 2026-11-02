"""Générateur DEMO : `minefleet demo seed --profile small --seed 42`.

Principes (docs/DEMO_DATA_ARCHITECTURE.md) :
- chaque objet est créé par le SERVICE applicatif, sous l'identité du compte DEMO qui porte la permission
  (matrice d'autorisations réelle) : aucun INSERT direct, aucune désactivation de RLS ;
- l'historique est simulé avec une horloge figée que l'on avance (FrozenClock) : les contrôles d'antidatage,
  d'échéance et d'éligibilité s'appliquent comme en exploitation ;
- déterministe : même graine + même date d'ancrage = mêmes objets, mêmes valeurs, même chronologie ;
- idempotent à la maille de la société : une société DEMO déjà présente est ignorée (aucune écriture).
"""

import random
import secrets
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from app.assignment import service as assignment
from app.assignment.schemas import AssignmentCreate
from app.authz.dependencies import Authorized, load_grants
from app.authz.principal import Principal, evaluate
from app.core.clock import Clock, FrozenClock, SystemClock
from app.core.config import Settings, get_settings
from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.demo.catalog import FIRST_NAMES, LAST_NAMES, PROFILES, SITE_ROLES, TENANT_ROLES, Profile, TenantSpec
from app.demo.catalog import TENANTS as CATALOG
from app.demo.guards import ensure_demo_database
from app.dispatch import service as dispatch
from app.dispatch import weighing
from app.dispatch.schemas import (
    LocationCreate,
    MaterialCreate,
    MissionCreate,
    MissionEventCreate,
    WeighingCreate,
)
from app.fleet import service as fleet
from app.fleet.schemas import VehicleCreate
from app.fuel import service as fuel
from app.fuel.schemas import DecisionCreate, IssueCreate, ReceiptCreate, TankCreate
from app.hse import service as hse
from app.hse.schemas import ActionComplete, ActionCreate, ActionDecisionIn, IncidentCreate, IncidentTransition
from app.identity import service as identity
from app.identity.schemas import UserInvite
from app.maintenance import service as maintenance
from app.maintenance.schemas import LabourCreate, WorkOrderCreate, WorkOrderDecision, WorkOrderProgress
from app.organization import service as organization
from app.organization.schemas import SiteCreate, TenantCreate
from app.seed import (
    SeedRefused,
    _activate,
    _Actor,
    _already_loaded,
    _category_ids,
    _mark_fictitious,
    _platform_admin,
    _user_id,
)
from app.workforce import service as workforce
from app.workforce.schemas import DriverCreate, LicenseCreate, QualificationCreate

# Catégorie de permis exigée par catégorie d'engin (référentiel de la migration 0001/0004).
LICENSE_FOR = {"LIGHT_VEHICLE": "B", "PERSONNEL_BUS": "D"}


@dataclass
class Credential:
    tenant: str
    role: str
    site: str | None
    email: str
    password: str


@dataclass
class _MissionState:
    id: uuid.UUID
    version: int
    t: datetime


@dataclass
class DemoReport:
    profile: str
    seed: int
    anchor: date
    skipped: list[str] = field(default_factory=list)
    credentials: list[Credential] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


class _PlatformActor(_Actor):
    """PLATFORM_ADMIN réel : son rôle date d'aujourd'hui, ses droits sont lus à l'heure réelle ; les objets
    qu'il crée sont horodatés par l'horloge simulée."""

    def __init__(self, base: _Actor, clock: Clock) -> None:
        super().__init__(base.tenant_id, base.user_id, base.tenant_kind, clock)

    def auth(self, permission: str) -> Authorized:
        db = new_session()
        set_tenant_context(db, self.tenant_id)
        principal = Principal(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            tenant_kind=self.tenant_kind,
            session_id=uuid.uuid4(),
            grants=load_grants(db, self.user_id, SystemClock()),
        )
        scope = evaluate(principal, permission)
        if scope is None:
            db.close()
            raise SeedRefused(f"le compte plateforme n'a pas la permission {permission}")
        return Authorized(principal, scope, db, self.clock)


def _password() -> str:
    # Aléa cryptographique, indépendant de la graine : un mot de passe n'est jamais reproductible.
    return "Demo-" + secrets.token_urlsafe(14)


@contextmanager
def _as(actor: _Actor, permission: str) -> Iterator[Authorized]:
    auth = actor.auth(permission)
    try:
        yield auth
    finally:
        auth.db.close()


def _call[T](actor: _Actor, permission: str, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with _as(actor, permission) as auth:
        return fn(auth, *args, **kwargs)


class _TenantBuilder:
    """Construit UNE société DEMO et son historique simulé."""

    def __init__(
        self,
        spec: TenantSpec,
        profile: Profile,
        rng: random.Random,
        clock: FrozenClock,
        start: datetime,
        settings: Settings,
        report: DemoReport,
    ) -> None:
        self.spec, self.profile, self.rng, self.clock = spec, profile, rng, clock
        self.start, self.settings, self.report = start, settings, report
        self.site_ids: dict[str, uuid.UUID] = {}
        self.actors: dict[tuple[str, str | None], _Actor] = {}
        self.user_ids: dict[tuple[str, str | None], uuid.UUID] = {}
        self.haulers: list[dict[str, Any]] = []
        self.tanks: dict[str, uuid.UUID] = {}
        self.fuel_level: dict[str, Decimal] = {}
        self.capacity = Decimal("120000")
        self.locations: dict[str, dict[str, uuid.UUID]] = {}
        self.materials: dict[str, uuid.UUID] = {}
        self.ticket_seq = 0

    # --- utilitaires ---------------------------------------------------------------------------------
    def at(self, moment: datetime) -> datetime:
        self.clock.set(moment)
        return moment

    def actor(self, role: str, site: str | None = None) -> _Actor:
        return self.actors[(role, site)]

    def person(self) -> tuple[str, str]:
        return self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)

    # --- socle : société, sites, comptes -------------------------------------------------------------
    def build(self, platform: _Actor) -> None:
        self.at(self.start)
        code = self.spec.code
        admin_email = f"admin@{code}.example.com"
        tenant, message = _call(
            platform,
            "organization.tenant.create",
            organization.create_tenant,
            TenantCreate(
                code=code,
                legal_name=self.spec.legal_name,
                display_name=self.spec.legal_name,
                admin_email=admin_email,
                admin_display_name="Administrateur (démo)",
            ),
            self.settings,
        )
        self.tenant_id = tenant.tenant_id
        password = _password()
        _activate(message, password, self.clock, self.settings)
        _mark_fictitious(tenant.tenant_id)
        self.report.credentials.append(Credential(code, "TENANT_ADMIN", None, admin_email, password))
        self.report.add("tenants")
        self.report.add("users")
        admin = _Actor(tenant.tenant_id, _user_id(tenant.tenant_id, admin_email), "CUSTOMER", self.clock)
        self.actors[("TENANT_ADMIN", None)] = admin

        for site in self.spec.sites:
            created = _call(
                admin,
                "organization.site.create",
                organization.create_site,
                SiteCreate(code=site.code, name=site.name, site_type=site.site_type),
            )
            self.site_ids[site.code] = created.site_id
            self.report.add("sites")

        for role in TENANT_ROLES:
            self._invite(admin, role, None)
        for site in self.spec.sites:
            for role in SITE_ROLES:
                self._invite(admin, role, site.code)

        self._references()
        self._fleet()
        self._workforce_and_assignments()
        self._fuel_setup()

    def _invite(self, admin: _Actor, role: str, site: str | None) -> None:
        code = self.spec.code
        local = role.lower().replace("_", "-") + (f".{site.lower()}" if site else "")
        email = f"{local}@{code}.example.com"
        first, last = self.person()
        _, message = _call(
            admin,
            "identity.user.create",
            identity.invite_user,
            UserInvite(
                email=email,
                display_name=f"{first} {last}",
                role_code=role,
                scope_type="SITE" if site else "TENANT",
                site_id=self.site_ids[site] if site else None,
            ),
            self.settings,
        )
        password = _password()
        _activate(message, password, self.clock, self.settings)
        user_id = _user_id(self.tenant_id, email)
        self.actors[(role, site)] = _Actor(self.tenant_id, user_id, "CUSTOMER", self.clock)
        self.user_ids[(role, site)] = user_id
        self.report.credentials.append(Credential(code, role, site, email, password))
        self.report.add("users")

    def _references(self) -> None:
        ops = self.actor("OPS_MANAGER")
        for mat_code, label, waste in (
            (*self.spec.material, False),
            (*self.spec.waste, True),
        ):
            material = _call(
                ops,
                "dispatch.material.manage",
                dispatch.create_material,
                MaterialCreate(code=mat_code, name=label, is_waste=waste),
            )
            self.materials[mat_code] = material.material_id
        for site in self.spec.sites:
            sid = self.site_ids[site.code]
            dump_kind = "PORT" if site.site_type == "PORT" else "STOCKPILE"
            points = {}
            for key, loc_code, name, kind in (
                ("load", "CHARG-1", "Front de chargement 1", "LOADING_POINT"),
                ("dump", "DECH-1", "Zone de déchargement 1", dump_kind),
                ("bridge", "PONT-1", "Pont-bascule 1", "WEIGHBRIDGE"),
            ):
                loc = _call(
                    ops,
                    "dispatch.location.manage",
                    dispatch.create_location,
                    LocationCreate(site_id=sid, code=loc_code, name=name, kind=kind),
                )
                points[key] = loc.site_location_id
                self.report.add("locations")
            self.locations[site.code] = points

    def _fleet(self) -> None:
        ops = self.actor("OPS_MANAGER")
        categories = _category_ids(self.tenant_id)
        sites = [s.code for s in self.spec.sites]
        for line in self.spec.fleet:
            for n in range(1, line.count * self.profile.fleet_factor + 1):
                site = sites[(n - 1) % len(sites)]
                fleet_number = f"DEMO-{line.prefix}-{n:03d}"
                vehicle = _call(
                    ops,
                    "fleet.vehicle.create",
                    fleet.create_vehicle,
                    VehicleCreate(
                        site_id=self.site_ids[site],
                        vehicle_category_id=categories[line.category],
                        fleet_number=fleet_number,
                        registration_number=f"DEMO-{self.rng.randint(1000, 9999)}-{line.prefix}",
                        make=line.make,
                        model=line.model,
                        model_year=self.rng.randint(2018, 2025),
                        rated_payload_kg=line.payload_kg,
                        commissioned_on=self.start.date() - timedelta(days=self.rng.randint(200, 1500)),
                        notes="Engin fictif de démonstration.",
                    ),
                )
                self.report.add("vehicles")
                if line.hauls:
                    self.haulers.append(
                        {
                            "vehicle_id": vehicle.vehicle_id,
                            "fleet_number": fleet_number,
                            "site": site,
                            "category": line.category,
                            "category_id": categories[line.category],
                            "meter": Decimal(self.rng.randint(4_000, 18_000)),
                        }
                    )

    def _new_driver(
        self, site: str, number: int, expiry: date, category_id: uuid.UUID, license_cat: str
    ) -> uuid.UUID:
        hr = self.actor("HR")
        first, last = self.person()
        driver, _ = _call(
            hr,
            "workforce.driver.create",
            workforce.create_driver,
            DriverCreate(
                site_id=self.site_ids[site],
                employee_number=f"DEMO-MAT-{number:04d}",
                last_name=last,
                first_name=first,
                phone=f"+224000{self.rng.randint(100000, 999999)}",
                hire_date=self.start.date() - timedelta(days=self.rng.randint(90, 2000)),
            ),
        )
        _call(
            hr,
            "workforce.driver_license.manage",
            workforce.create_license,
            driver.driver_id,
            LicenseCreate(
                license_number=f"DEMO-PERMIS-{number:05d}",
                category_code=license_cat,
                issue_date=self.start.date() - timedelta(days=1500),
                expiry_date=expiry,
            ),
        )
        _call(
            hr,
            "workforce.driver_qualification.manage",
            workforce.create_qualification,
            driver.driver_id,
            QualificationCreate(
                qualification_type="DRIVING_AUTHORIZATION",
                vehicle_category_id=category_id,
                valid_from=self.start.date() - timedelta(days=365),
                valid_to=self.start.date() + timedelta(days=900),
            ),
        )
        self.report.add("drivers")
        return driver.driver_id

    def _workforce_and_assignments(self) -> None:
        number = 0
        horizon = self.start.date() + timedelta(days=self.profile.days + 1500)
        for hauler in self.haulers:
            license_cat = LICENSE_FOR.get(hauler["category"], "C")
            for k in range(self.profile.drivers_per_hauler):
                number += 1
                driver_id = self._new_driver(
                    hauler["site"], number, horizon, hauler["category_id"], license_cat
                )
                if k == 0:
                    hauler["driver_id"] = driver_id
        # Cas négatifs : permis expiré (non affectable) et permis proche de l'échéance (alerte).
        site0 = self.spec.sites[0].code
        cat = self.haulers[0]["category_id"]
        anchor = self.start.date() + timedelta(days=self.profile.days)
        self._new_driver(site0, number + 1, anchor - timedelta(days=20), cat, "C")
        self._new_driver(site0, number + 2, anchor + timedelta(days=12), cat, "C")

        self.at(self.start + timedelta(hours=1))
        for hauler in self.haulers:
            dispatcher = self.actor("DISPATCHER", hauler["site"])
            created = _call(
                dispatcher,
                "assignment.vehicle_assignment.create",
                assignment.create_assignment,
                AssignmentCreate(
                    vehicle_id=hauler["vehicle_id"],
                    driver_id=hauler["driver_id"],
                    valid_from=self.start + timedelta(hours=1),
                    shift_code="JOUR",
                ),
            )
            if created.status == "PLANNED":  # D-27 : déjà ACTIVE si la prise de poste est immédiate
                created = _call(
                    dispatcher,
                    "assignment.vehicle_assignment.update",
                    assignment.activate_assignment,
                    created.vehicle_assignment_id,
                    created.row_version,
                )
            hauler["assignment_id"] = created.vehicle_assignment_id
            self.report.add("assignments")

    def _fuel_setup(self) -> None:
        for site in self.spec.sites:
            manager = self.actor("FUEL_MANAGER", site.code)
            tank = _call(
                manager,
                "fuel.stock.manage",
                fuel.create_tank,
                TankCreate(
                    site_id=self.site_ids[site.code],
                    code="CUVE-GO-1",
                    fuel_type="DIESEL",
                    capacity_liters=self.capacity,
                    low_stock_threshold_liters=Decimal("15000"),
                ),
            )
            self.tanks[site.code] = tank.fuel_tank_id
            self.fuel_level[site.code] = Decimal(0)
            self.report.add("fuel_tanks")
            self._receive(site.code, self.start + timedelta(hours=2), Decimal("90000"))

    def _receive(self, site: str, moment: datetime, liters: Decimal) -> None:
        """Livraison bornée par la place disponible dans la cuve (règle : pas de débordement)."""
        liters = min(liters, (self.capacity - self.fuel_level[site]) // 1000 * 1000)
        if liters < 5000:
            return
        self.at(moment)
        manager = self.actor("FUEL_MANAGER", site)
        _call(
            manager,
            "fuel.stock.receive",
            fuel.receive,
            self.tanks[site],
            ReceiptCreate(
                liters=liters, reference=f"BL-DEMO-{self.rng.randint(10000, 99999)}", occurred_at=moment
            ),
        )
        self.fuel_level[site] += liters
        self.report.add("fuel_receipts")

    # --- historique simulé ---------------------------------------------------------------------------
    def simulate(self) -> None:
        days = self.profile.days
        breakdown_day = days // 2
        for d in range(1, days):
            day = (self.start + timedelta(days=d)).date()
            for index, hauler in enumerate(self.haulers):
                if hauler.get("down_until") and hauler["down_until"] > day:
                    continue
                for m in range(self.profile.missions_per_hauler_day):
                    self._mission(hauler, day, m, suspend=(d == days - 1 and index == 1 and m == 0))
                if (d + index) % 2 == 0:
                    self._refuel(hauler, day)
            if d == 3:
                self._hse_closed_incident(day)
            if d == breakdown_day:
                self._closed_breakdown(self.haulers[0], day)
            if d % 7 == 0:
                for site in self.spec.sites:
                    self._receive(site.code, datetime.combine(day, time(5, 0), UTC), Decimal("40000"))
        last = (self.start + timedelta(days=days - 1)).date()
        self._open_breakdown(self.haulers[-1], last)
        self._hse_open_incident(last)

    # --- jour J : activité en cours à l'ouverture de la démo -----------------------------------------
    LIVE_STEPS = (
        ("DEPARTED", "ARRIVED_LOADING"),
        ("DEPARTED", "ARRIVED_LOADING", "LOADED"),
        ("DEPARTED", "ARRIVED_LOADING", "LOADED", "ARRIVED_UNLOADING"),
    )

    def live_day(self, live_start: datetime) -> None:
        """Missions en cours (chargement, route chargée, déchargement) et une mission planifiée.

        Exclut l'engin en panne ouverte et celui dont la mission est suspendue (scénarios négatifs)."""
        blocked = {0 if len(self.haulers) < 2 else 1, len(self.haulers) - 1}
        eligible = [h for i, h in enumerate(self.haulers) if i not in blocked]
        for n, hauler in enumerate(eligible):
            begin = live_start + timedelta(minutes=7 * n)
            if n == len(eligible) - 1 and n > 0:
                self._start_mission(hauler, begin + timedelta(hours=4), steps=())
                self.report.add("missions_planned")
            else:
                self._start_mission(hauler, begin, steps=self.LIVE_STEPS[n % len(self.LIVE_STEPS)])
                self.report.add("missions_live")

    def _start_mission(self, hauler: dict[str, Any], begin: datetime, *, steps: tuple[str, ...]) -> None:
        site = hauler["site"]
        points = self.locations[site]
        dispatcher = self.actor("DISPATCHER", site)
        self.at(min(begin, self.clock.now()) if not steps else begin - timedelta(minutes=20))
        mission = _call(
            dispatcher,
            "dispatch.mission.create",
            dispatch.create_mission,
            MissionCreate(
                vehicle_assignment_id=hauler["assignment_id"],
                origin_location_id=points["load"],
                destination_location_id=points["dump"],
                material_id=self.materials[self.spec.material[0]],
                planned_start=begin,
                due_at=begin + timedelta(hours=10),
                planned_rotations=self.rng.randint(*self.profile.rotations_per_mission),
            ),
        )
        self.report.add("missions")
        t, version = begin, mission.row_version
        for kind in steps:
            t += timedelta(minutes=self.rng.randint(8, 20))
            self.at(t + timedelta(seconds=5))
            version = _call(
                dispatcher,
                "dispatch.mission.progress",
                dispatch.record_event,
                mission.mission_id,
                MissionEventCreate(event_type=kind, occurred_at=t),
                version,
            ).row_version

    def _mission(self, hauler: dict[str, Any], day: date, slot: int, *, suspend: bool) -> None:
        site = hauler["site"]
        points = self.locations[site]
        dispatcher = self.actor("DISPATCHER", site)
        begin = datetime.combine(day, time(6 + 6 * slot, 0), UTC) + timedelta(minutes=self.rng.randint(0, 40))
        lo, hi = self.profile.rotations_per_mission
        rotations = self.rng.randint(lo, hi)
        self.at(begin - timedelta(minutes=30))
        mission = _call(
            dispatcher,
            "dispatch.mission.create",
            dispatch.create_mission,
            MissionCreate(
                vehicle_assignment_id=hauler["assignment_id"],
                origin_location_id=points["load"],
                destination_location_id=points["dump"],
                material_id=self.materials[self.spec.material[0]],
                planned_start=begin,
                due_at=begin + timedelta(hours=10),
                planned_rotations=rotations,
            ),
        )
        self.report.add("missions")
        state = _MissionState(mission.mission_id, mission.row_version, begin)

        def event(kind: str, minutes: int, **extra: Any) -> None:
            state.t += timedelta(minutes=minutes)
            self.at(state.t + timedelta(seconds=5))
            out = _call(
                dispatcher,
                "dispatch.mission.progress",
                dispatch.record_event,
                state.id,
                MissionEventCreate(event_type=kind, occurred_at=state.t, **extra),
                state.version,
            )
            state.version = out.row_version

        event("DEPARTED", 0)
        for r in range(rotations):
            event("ARRIVED_LOADING", self.rng.randint(12, 25))
            event("LOADED", self.rng.randint(6, 15))
            event("ARRIVED_UNLOADING", self.rng.randint(20, 45))
            event("UNLOADED", self.rng.randint(4, 10))
            self.report.add("rotations")
            self._weigh(state.id, dispatcher, state.t, degraded=(suspend and r == 0))
            if suspend:
                event("SUSPENDED", 10, reason_code="ROAD_BLOCKED")
                self.report.add("missions_suspended")
                return
        event("COMPLETED", self.rng.randint(10, 30))
        hauler["meter"] += Decimal(self.rng.randint(6, 11))

    def _weigh(self, mission_id: uuid.UUID, dispatcher: _Actor, moment: datetime, *, degraded: bool) -> None:
        with _as(dispatcher, "dispatch.mission.read") as auth:
            detail = dispatch.missions_out(auth, [dispatch.mission_in_scope(auth, mission_id)], detail=True)[
                0
            ]
        rotation = (detail.rotations or [])[-1]
        site = next(code for code, sid in self.site_ids.items() if sid == detail.site_id)
        self.ticket_seq += 1
        mean, spread = self.spec.net_kg
        tare = self.rng.randint(25_000, 32_000)
        net = max(1_000, int(self.rng.gauss(mean, spread)))
        weighed_at = moment - timedelta(minutes=2)
        self.at(moment + timedelta(seconds=20))
        _call(
            dispatcher,
            "dispatch.weighing.record",
            weighing.record_ticket,
            WeighingCreate(
                rotation_id=rotation.rotation_id,
                weighbridge_location_id=self.locations[site]["bridge"],
                ticket_number=f"DEMO-TK-{self.ticket_seq:06d}",
                source="MANUAL_DEGRADED" if degraded else "WEIGHBRIDGE",
                degraded_reason="WEIGHBRIDGE_DOWN" if degraded else None,
                weighed_at=weighed_at,
                gross_kg=tare + net,
                tare_kg=tare,
            ),
        )
        self.report.add("weighings_pending" if degraded else "weighings")

    def _refuel(self, hauler: dict[str, Any], day: date) -> None:
        site = hauler["site"]
        manager = self.actor("FUEL_MANAGER", site)
        liters = Decimal(self.rng.randint(180, 420))
        if self.fuel_level[site] < liters:
            return
        moment = self.at(datetime.combine(day, time(19, 0), UTC) + timedelta(minutes=self.rng.randint(0, 50)))
        issue = _call(
            manager,
            "fuel.issue.request",
            fuel.create_issue,
            IssueCreate(
                fuel_tank_id=self.tanks[site],
                vehicle_id=hauler["vehicle_id"],
                driver_id=hauler["driver_id"],
                liters=liters,
                meter_kind="HOUR_METER",
                meter_value=hauler["meter"],
                full_tank=True,
                requested_at=moment,
            ),
        )
        self.at(moment + timedelta(minutes=3))
        _call(
            self.actor("OPS_MANAGER"),
            "fuel.issue.decide",
            fuel.decide_issue,
            issue.fuel_issue_id,
            DecisionCreate(decision="APPROVED"),
        )
        self.fuel_level[site] -= liters
        self.report.add("fuel_issues")

    # --- atelier : panne clôturée et panne ouverte ---------------------------------------------------
    def _breakdown(
        self, hauler: dict[str, Any], moment: datetime, symptom: str
    ) -> tuple[uuid.UUID, int, str]:
        site = hauler["site"]
        self.at(moment)
        order = _call(
            self.actor("DISPATCHER", site),
            "maintenance.work_order.request",
            maintenance.create_work_order,
            WorkOrderCreate(
                vehicle_id=hauler["vehicle_id"],
                symptom_code=symptom,
                priority="HIGH",
                description="Panne simulée (démonstration) : remontée par le conducteur en fin de poste.",
                immobilize=True,
            ),
        )
        self.report.add("work_orders")
        return order.work_order_id, order.row_version, site

    def _closed_breakdown(self, hauler: dict[str, Any], day: date) -> None:
        moment = datetime.combine(day, time(20, 30), UTC)
        wo_id, version, site = self._breakdown(hauler, moment, "HYDRAULICS")
        chief = self.actor("WORKSHOP_CHIEF")
        mechanic_id = self.user_ids[("MECHANIC", site)]
        mechanic = self.actor("MECHANIC", site)

        def decide(body: WorkOrderDecision, minutes: int) -> None:
            nonlocal version
            self.at(self.clock.now() + timedelta(minutes=minutes))
            version = _call(
                chief, "maintenance.work_order.manage", maintenance.decide, wo_id, body, version
            ).row_version

        def progress(body: WorkOrderProgress, minutes: int) -> None:
            nonlocal version
            self.at(self.clock.now() + timedelta(minutes=minutes))
            version = _call(
                mechanic, "maintenance.work_order.execute", maintenance.progress, wo_id, body, version
            ).row_version

        decide(WorkOrderDecision(action="APPROVE"), 15)
        decide(WorkOrderDecision(action="ASSIGN", assigned_to=mechanic_id), 5)
        progress(WorkOrderProgress(action="START", diagnosis="Fuite sur flexible hydraulique de levage."), 40)
        self.at(self.clock.now() + timedelta(minutes=10))
        version = _call(
            mechanic,
            "maintenance.work_order.execute",
            maintenance.add_labour,
            wo_id,
            LabourCreate(minutes=180, performed_on=self.clock.now().date()),
        ).row_version
        progress(
            WorkOrderProgress(action="SUBMIT", work_done="Flexible remplacé, essais de levage conformes."),
            200,
        )
        decide(WorkOrderDecision(action="QC_PASS"), 30)
        hauler["down_until"] = day + timedelta(days=1)
        self.report.add("work_orders_closed")

    def _open_breakdown(self, hauler: dict[str, Any], day: date) -> None:
        self._breakdown(hauler, datetime.combine(day, time(21, 0), UTC), "ENGINE")
        self.report.add("work_orders_open")

    # --- HSE ---------------------------------------------------------------------------------------------
    def _hse_closed_incident(self, day: date) -> None:
        site = self.spec.sites[0].code
        moment = datetime.combine(day, time(10, 15), UTC)
        self.at(moment + timedelta(minutes=20))
        hse_actor = self.actor("HSE")
        incident = _call(
            self.actor("DISPATCHER", site),
            "hse.incident.report",
            hse.report_incident,
            IncidentCreate(
                site_id=self.site_ids[site],
                category="NEAR_MISS",
                severity="MEDIUM",
                title="Presque-accident au croisement de la piste principale",
                description="Croisement à faible distance entre un tombereau chargé et un véhicule léger.",
                occurred_at=moment,
                location_note="Piste principale, croisement nord",
            ),
        )
        self.report.add("hse_incidents")
        version = incident.row_version
        self.at(self.clock.now() + timedelta(hours=1))
        version = _call(
            hse_actor,
            "hse.incident.manage",
            hse.transition,
            incident.hse_incident_id,
            IncidentTransition(action="START_INVESTIGATION"),
            version,
        ).row_version
        self.at(self.clock.now() + timedelta(minutes=30))
        action = _call(
            hse_actor,
            "hse.incident.manage",
            hse.add_action,
            incident.hse_incident_id,
            ActionCreate(
                title="Installer un panneau STOP et un miroir au croisement",
                owner_user_id=self.user_ids[("OPS_MANAGER", None)],
                due_date=day + timedelta(days=5),
            ),
        )
        self.at(self.clock.now() + timedelta(days=2))
        done = _call(
            self.actor("OPS_MANAGER"),
            "hse.action.complete",
            hse.complete_action,
            action.hse_corrective_action_id,
            ActionComplete(completion_note="Panneau STOP et miroir convexe installés, photo au dossier."),
            action.row_version,
        )
        self.at(self.clock.now() + timedelta(hours=3))
        _call(
            hse_actor,
            "hse.incident.manage",
            hse.decide_action,
            action.hse_corrective_action_id,
            ActionDecisionIn(action="VERIFY"),
            done.row_version,
        )
        self.at(self.clock.now() + timedelta(hours=2))
        _call(
            hse_actor,
            "hse.incident.manage",
            hse.transition,
            incident.hse_incident_id,
            IncidentTransition(
                action="CLOSE",
                root_cause="Visibilité réduite au croisement, absence de signalisation.",
                investigation_summary="Signalisation installée ; rappel des règles de priorité au briefing.",
            ),
            version,
        )
        self.report.add("hse_actions")

    def _hse_open_incident(self, day: date) -> None:
        site = self.spec.sites[0].code
        moment = datetime.combine(day, time(14, 40), UTC)
        self.at(moment + timedelta(minutes=15))
        _call(
            self.actor("HSE"),
            "hse.incident.report",
            hse.report_incident,
            IncidentCreate(
                site_id=self.site_ids[site],
                category="VEHICLE_COLLISION",
                severity="CRITICAL",
                title="Collision d'engin contre un merlon de sécurité",
                description="Tombereau ayant heurté le merlon en bordure de rampe ; arrêté, pas de blessé.",
                occurred_at=moment,
                vehicle_id=self.haulers[0]["vehicle_id"],
            ),
        )
        self.report.add("hse_incidents")
        self.report.add("hse_incidents_open")


def seed_demo(
    *, profile: str = "small", seed: int = 42, anchor: date | None = None, settings: Settings | None = None
) -> DemoReport:
    settings = settings or get_settings()
    ensure_demo_database(settings)
    if profile not in PROFILES:
        raise ValueError(f"profil inconnu : {profile} (attendus : {', '.join(PROFILES)})")
    prof = PROFILES[profile]
    real_now = SystemClock().now()
    anchor = anchor or real_now.date()
    # Jour J : activité « en cours » démarrée 2 h 30 avant l'exécution (ou à 08:00 pour un ancrage passé),
    # toujours dans le passé réel. Seule partie de la chronologie qui dépend de l'heure d'exécution.
    live_start = (
        real_now - timedelta(minutes=150)
        if anchor == real_now.date()
        else datetime.combine(anchor, time(8, 0), UTC)
    )
    report = DemoReport(profile=profile, seed=seed, anchor=anchor)
    start = datetime.combine(anchor - timedelta(days=prof.days), time(4, 0), UTC)
    clock = FrozenClock(start)
    platform = _PlatformActor(_platform_admin(clock), clock)
    for index, spec in enumerate(CATALOG):
        if _already_loaded(spec.code):
            report.skipped.append(spec.code)
            continue
        # Une graine dérivée par société : ajouter une société ne modifie pas les données des autres.
        rng = random.Random(f"{seed}:{index}:{spec.code}")  # noqa: S311 (données de démo, pas de secret)
        builder = _TenantBuilder(spec, prof, rng, clock, start, settings, report)
        builder.build(platform)
        builder.simulate()
        builder.live_day(live_start)
    return report
