"""`minefleet demo verify` : contrôles de cohérence recalculés depuis les données sources.

Chaque contrôle compare deux chemins indépendants (requête directe vs service applicatif, ou somme des
mouvements vs solde calculé), sous le rôle mf_app et le contexte RLS de la société : rien n'est contourné.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, exists, func, select

from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.tenancy import PLATFORM_TENANT_ID, set_login_tenant_code, set_tenant_context
from app.costs import service as costs
from app.costs.models import LabourRate
from app.demo.catalog import TENANTS
from app.dispatch import weighing
from app.dispatch.models import Rotation, WeighingTicket, WeighingTicketDecision
from app.fleet import gps_history
from app.fleet.gps_models import FleetGpsPosition
from app.fleet.models import Vehicle
from app.fuel.models import FuelIssue, FuelStockMovement, FuelTank
from app.fuel.models import FuelIssueDecision as FuelDecision
from app.fuel.service import _balance
from app.maintenance.models import WorkOrder, WorkOrderLabour
from app.maintenance.tyre_models import Tyre
from app.organization.models import Tenant
from app.seed import _Actor, _user_id

OPEN_WO = ("REQUESTED", "APPROVED", "ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS", "QUALITY_CHECK")


@dataclass
class Check:
    tenant: str
    name: str
    ok: bool
    detail: str


def _tenant(code: str) -> Tenant | None:
    db = new_session()
    try:
        set_login_tenant_code(db, code)
        return db.execute(select(Tenant).where(Tenant.code == code)).scalar_one_or_none()
    finally:
        db.close()


def _demo_tenant_ids() -> dict[str, uuid.UUID]:
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        codes = [t.code for t in TENANTS]
        return dict(
            db.execute(select(Tenant.code, Tenant.tenant_id).where(Tenant.code.in_(codes))).tuples().all()
        )
    finally:
        db.close()


def verify_demo(anchor: date | None = None) -> list[Check]:
    checks: list[Check] = []
    ids = _demo_tenant_ids()
    for spec in TENANTS:
        tenant = _tenant(spec.code)
        if tenant is None:
            checks.append(
                Check(spec.code, "société présente", False, "absente : lancer `minefleet demo seed`")
            )
            continue
        checks.append(Check(spec.code, "société marquée DEMO", tenant.is_demo, f"is_demo={tenant.is_demo}"))
        others = {code: tid for code, tid in ids.items() if code != spec.code}
        checks.extend(_isolation(spec.code, tenant.tenant_id, others))
        checks.extend(_rotations_weighed(spec.code, tenant.tenant_id))
        checks.extend(_tonnage_matches_indicators(spec.code, tenant.tenant_id, anchor))
        checks.extend(_fuel_balances(spec.code, tenant.tenant_id))
        checks.extend(_breakdowns_immobilize(spec.code, tenant.tenant_id))
        checks.extend(_costs_recomputed(spec.code, tenant.tenant_id, anchor))
        checks.extend(_tyres_consistent(spec.code, tenant.tenant_id))
        checks.extend(_gps_matches_rotations(spec.code, tenant.tenant_id, anchor))
    return checks


def _isolation(code: str, tenant_id: uuid.UUID, others: dict[str, uuid.UUID]) -> list[Check]:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        foreign = db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.tenant_id != tenant_id))
        own = db.scalar(select(func.count()).select_from(Vehicle))
        leaked = (
            db.scalar(
                select(func.count())
                .select_from(WeighingTicket)
                .where(WeighingTicket.tenant_id.in_(others.values()))
            )
            if others
            else 0
        )
    finally:
        db.close()
    return [
        Check(
            code,
            "isolation RLS (engins d'autres sociétés invisibles)",
            foreign == 0 and (own or 0) > 0,
            f"visibles={own}, étrangers={foreign}",
        ),
        Check(
            code, "isolation RLS (pesées des autres sociétés DEMO invisibles)", leaked == 0, f"fuite={leaked}"
        ),
    ]


def _rotations_weighed(code: str, tenant_id: uuid.UUID) -> list[Check]:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        voided = select(WeighingTicketDecision.weighing_ticket_id).where(
            WeighingTicketDecision.decision == "VOID"
        )
        live_ticket = exists().where(
            and_(
                WeighingTicket.rotation_id == Rotation.rotation_id,
                WeighingTicket.weighing_ticket_id.not_in(voided),
            )
        )
        completed = db.scalar(
            select(func.count()).select_from(Rotation).where(Rotation.status == "COMPLETED")
        )
        missing = db.scalar(
            select(func.count()).select_from(Rotation).where(Rotation.status == "COMPLETED", ~live_ticket)
        )
    finally:
        db.close()
    return [
        Check(
            code,
            "chaque rotation terminée a une pesée",
            missing == 0 and (completed or 0) > 0,
            f"rotations={completed}, sans pesée={missing}",
        )
    ]


def _tonnage_matches_indicators(code: str, tenant_id: uuid.UUID, anchor: date | None) -> list[Check]:
    end = datetime.combine(anchor or SystemClock().now().date(), time(0, 0), UTC)
    start = end - timedelta(days=7)
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        direct = db.scalar(
            select(func.coalesce(func.sum(WeighingTicket.net_kg), 0))
            .join(Rotation, Rotation.rotation_id == WeighingTicket.rotation_id)
            .where(
                WeighingTicket.source == "WEIGHBRIDGE",
                Rotation.status == "COMPLETED",
                Rotation.unloaded_at >= start,
                Rotation.unloaded_at < end,
            )
        )
    finally:
        db.close()
    ops = _Actor(tenant_id, _user_id(tenant_id, f"ops-manager@{code}.example.com"), "CUSTOMER", SystemClock())
    auth = ops.auth("dispatch.indicators.read")
    try:
        out = weighing.indicators(auth, site_id=None, period_start=start, period_end=end)
    finally:
        auth.db.close()
    via_api = sum(row.measured_net_kg for row in out.rows)
    return [
        Check(
            code,
            "tonnage mesuré = indicateur du service (7 derniers jours)",
            via_api == direct and direct > 0,
            f"pesées={direct} kg, indicateur={via_api} kg",
        )
    ]


def _fuel_balances(code: str, tenant_id: uuid.UUID) -> list[Check]:
    checks = []
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        for tank in db.execute(select(FuelTank)).scalars():
            receipts = db.scalar(
                select(func.coalesce(func.sum(FuelStockMovement.liters), 0)).where(
                    FuelStockMovement.fuel_tank_id == tank.fuel_tank_id,
                    FuelStockMovement.movement_type.in_(("RECEIPT", "STOCKTAKE_IN", "PURCHASE_RECEIPT")),
                )
            )
            issued = db.scalar(
                select(func.coalesce(func.sum(FuelIssue.liters), 0))
                .join(FuelDecision, FuelDecision.fuel_issue_id == FuelIssue.fuel_issue_id)
                .where(FuelIssue.fuel_tank_id == tank.fuel_tank_id, FuelDecision.decision == "APPROVED")
            )
            receipts, issued = Decimal(receipts or 0), Decimal(issued or 0)
            balance = _balance(db, tenant_id, tank.fuel_tank_id)
            ok = balance == receipts - issued and balance >= 0 and balance <= tank.capacity_liters
            checks.append(
                Check(
                    code,
                    f"solde cuve {tank.code} = réceptions − distributions approuvées",
                    ok,
                    f"réceptions={receipts}, distribué={issued}, solde={balance}",
                )
            )
    finally:
        db.close()
    return checks


def _breakdowns_immobilize(code: str, tenant_id: uuid.UUID) -> list[Check]:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        rows = db.execute(
            select(WorkOrder.status, Vehicle.status)
            .join(Vehicle, Vehicle.vehicle_id == WorkOrder.vehicle_id)
            .where(WorkOrder.immobilize.is_(True))
        ).all()
    finally:
        db.close()
    wrong = [
        (wo, v)
        for wo, v in rows
        if (wo in OPEN_WO and v != "IMMOBILIZED") or (wo == "CLOSED" and v == "IMMOBILIZED")
    ]
    return [
        Check(
            code,
            "panne ouverte ⇔ engin immobilisé ; panne clôturée ⇒ engin remis en service",
            not wrong and len(rows) > 0,
            f"OT bloquants={len(rows)}, incohérences={wrong}",
        )
    ]


def _costs_recomputed(code: str, tenant_id: uuid.UUID, anchor: date | None) -> list[Check]:
    """Coût complet servi par le service vs recalcul indépendant de la main-d'œuvre ; carburant valorisé."""
    # Les sorties de magasin sont horodatées par la base à l'exécution réelle (non simulable) : la fenêtre
    # va de 30 jours avant l'ancrage jusqu'à maintenant, pour couvrir un ancrage passé.
    today = SystemClock().now().date()
    start = datetime.combine((anchor or today) - timedelta(days=30), time(0, 0), UTC)
    end = datetime.combine(max(anchor or today, today), time(0, 0), UTC) + timedelta(days=1)
    finance = _Actor(tenant_id, _user_id(tenant_id, f"finance@{code}.example.com"), "CUSTOMER", SystemClock())
    auth = finance.auth("cost.vehicle.read")
    try:
        rows = costs.vehicle_costs(auth, start=start, end=end, site_ids=None)
    finally:
        auth.db.close()
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        rate = db.scalar(select(LabourRate.hourly_rate).where(LabourRate.site_id.is_(None)))
        minutes = dict(
            db.execute(
                select(WorkOrder.vehicle_id, func.sum(WorkOrderLabour.minutes))
                .join(WorkOrderLabour, WorkOrderLabour.work_order_id == WorkOrder.work_order_id)
                # Même fenêtre que le coût servi : seules les minutes saisies dans la période comptent.
                .where(
                    WorkOrderLabour.performed_on >= start.date(), WorkOrderLabour.performed_on < end.date()
                )
                .group_by(WorkOrder.vehicle_id)
            )
            .tuples()
            .all()
        )
    finally:
        db.close()
    haulers = [r for r in rows if r.tonnes > 0]
    unpriced_fuel = [r.fleet_number for r in haulers if r.fuel.status != "ESTIMATED" or not r.fuel.amount]
    labour_gaps = [
        (r.fleet_number, r.labour.amount, Decimal(minutes[r.vehicle_id]) / 60 * Decimal(rate or 0))
        for r in rows
        if r.vehicle_id in minutes
        and (
            r.labour.amount is None
            or r.labour.amount != Decimal(minutes[r.vehicle_id]) / 60 * Decimal(rate or 0)
        )
    ]
    with_parts = [r for r in rows if r.parts.amount]
    return [
        Check(
            code,
            "carburant des engins de transport valorisé (prix des livraisons sur commande)",
            bool(haulers) and not unpriced_fuel,
            f"engins={len(haulers)}, sans prix={unpriced_fuel}",
        ),
        Check(
            code,
            "main-d'œuvre servie = minutes saisies × taux horaire",
            not labour_gaps,
            f"OT avec temps={len(minutes)}, écarts={labour_gaps}",
        ),
        Check(
            code,
            "pièces consommées valorisées sur l'engin réparé",
            bool(with_parts) and all(r.parts.status == "COMPLETE" for r in with_parts),
            f"engins avec pièces={len(with_parts)}",
        ),
    ]


def _tyres_consistent(code: str, tenant_id: uuid.UUID) -> list[Check]:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        mounted = db.execute(
            select(Tyre.vehicle_id, Tyre.position_code).where(Tyre.status == "MOUNTED")
        ).all()
        scrapped_on_vehicle = db.scalar(
            select(func.count())
            .select_from(Tyre)
            .where(Tyre.status == "SCRAPPED", Tyre.vehicle_id.is_not(None))
        )
    finally:
        db.close()
    duplicates = len(mounted) - len(set(mounted))
    return [
        Check(
            code,
            "pneus : une position par pneu monté, aucun pneu réformé sur un engin",
            bool(mounted) and duplicates == 0 and scrapped_on_vehicle == 0,
            f"montés={len(mounted)}, doublons={duplicates}, réformés montés={scrapped_on_vehicle}",
        )
    ]


def _gps_matches_rotations(code: str, tenant_id: uuid.UUID, anchor: date | None) -> list[Check]:
    """Trajet servi par l'application sur une journée : une entrée en zone de chargement par rotation.

    Lecture réelle du trajet (journalisée dans l'audit comme toute consultation d'historique GPS)."""
    day_start = datetime.combine((anchor or SystemClock().now().date()) - timedelta(days=2), time(0, 0), UTC)
    day_end = day_start + timedelta(days=1)
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        positions = db.scalar(select(func.count()).select_from(FleetGpsPosition))
        busiest = db.execute(
            select(Rotation.vehicle_id, func.count())
            .where(
                Rotation.status == "COMPLETED",
                Rotation.loading_started_at >= day_start,
                Rotation.loading_started_at < day_end,
            )
            .group_by(Rotation.vehicle_id)
            .order_by(func.count().desc(), Rotation.vehicle_id)
            .limit(1)
        ).first()
    finally:
        db.close()
    if busiest is None:
        return [
            Check(
                code, "GPS : entrées en zone de chargement = rotations", False, "aucune rotation ce jour-là"
            )
        ]
    vehicle_id, rotations = busiest
    auditor = _Actor(tenant_id, _user_id(tenant_id, f"auditor@{code}.example.com"), "CUSTOMER", SystemClock())
    auth = auditor.auth("fleet.gps.history")
    try:
        track = gps_history.vehicle_track(vehicle_id, auth, "OPERATIONS_REVIEW", day_start, day_end)
    finally:
        auth.db.close()
    entries = sum(
        1 for e in track.geofence_events if e.geofence_kind == "LOADING_AREA" and e.event_type == "ENTER"
    )
    return [
        Check(
            code,
            "GPS : entrées en zone de chargement = rotations terminées (trajet servi par l'application)",
            bool(positions) and entries == rotations and track.distance_km > 0,
            f"positions={positions}, rotations={rotations}, entrées={entries}, "
            f"distance={track.distance_km:.1f} km",
        )
    ]
