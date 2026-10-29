"""Opérations de stock carburant avec réservations sous verrou de cuve."""

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.assignment.models import VehicleAssignment
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import PageParams
from app.fleet.models import Vehicle, VehicleCategory
from app.fuel.models import FuelIssue, FuelIssueDecision, FuelStockMovement, FuelTank
from app.fuel.schemas import DecisionCreate, IssueCreate, ReceiptCreate, TankCreate
from app.workforce.models import Driver

Issue = FuelIssue
Decision = FuelIssueDecision
Movement = FuelStockMovement
Tank = FuelTank
ZERO = Decimal("0")


def _audit(auth: Authorized, action: str, entity_id: uuid.UUID, site_id: uuid.UUID) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action=action,
        entity_type="fuel",
        entity_id=entity_id,
        site_id=site_id,
    )


def _in_scope(auth: Authorized, site_id: uuid.UUID) -> bool:
    return auth.scope.covers_site(site_id)


def _tank(auth: Authorized, tank_id: uuid.UUID, *, lock: bool = False) -> Tank:
    stmt = select(Tank).where(Tank.tenant_id == auth.tenant_id, Tank.fuel_tank_id == tank_id)
    if lock:
        stmt = stmt.with_for_update()
    tank = auth.db.scalar(stmt)
    if tank is None or not _in_scope(auth, tank.site_id):
        raise AppError("NOT_FOUND")
    return tank


def _balance(db: Session, tenant_id: uuid.UUID, tank_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case((Movement.movement_type == "RECEIPT", Movement.liters), else_=-Movement.liters)
                ),
                ZERO,
            )
        ).where(Movement.tenant_id == tenant_id, Movement.fuel_tank_id == tank_id)
    )
    return Decimal(value or ZERO)


def _reserved(db: Session, tenant_id: uuid.UUID, tank_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(Issue.liters), ZERO))
        .outerjoin(
            Decision,
            (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
        )
        .where(
            Issue.tenant_id == tenant_id,
            Issue.fuel_tank_id == tank_id,
            Decision.fuel_issue_decision_id.is_(None),
        )
    )
    return Decimal(value or ZERO)


def list_tanks(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None
) -> tuple[list[dict[str, object]], int]:
    stmt = select(Tank).where(Tank.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Tank.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Tank.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    tanks = list(
        auth.db.scalars(
            stmt.order_by(Tank.site_id, Tank.code, Tank.fuel_tank_id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    )
    out: list[dict[str, object]] = []
    for tank in tanks:
        balance = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id)
        reserved = _reserved(auth.db, auth.tenant_id, tank.fuel_tank_id)
        out.append(
            {
                "fuel_tank_id": tank.fuel_tank_id,
                "site_id": tank.site_id,
                "code": tank.code,
                "fuel_type": tank.fuel_type,
                "capacity_liters": tank.capacity_liters,
                "balance_liters": balance,
                "reserved_liters": reserved,
                "available_liters": balance - reserved,
            }
        )
    return out, total


def create_tank(auth: Authorized, body: TankCreate) -> Tank:
    if not _in_scope(auth, body.site_id):
        raise AppError("NOT_FOUND")
    tank = Tank(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        code=body.code,
        fuel_type=body.fuel_type,
        capacity_liters=body.capacity_liters,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    auth.db.add(tank)
    auth.db.flush()
    _audit(auth, "fuel.tank.create", tank.fuel_tank_id, tank.site_id)
    auth.db.commit()
    return tank


def receive(auth: Authorized, tank_id: uuid.UUID, body: ReceiptCreate) -> Movement:
    tank = _tank(auth, tank_id, lock=True)
    if body.occurred_at > auth.clock.now() + timedelta(seconds=5):
        raise AppError("VALIDATION_ERROR")
    if _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) + body.liters > tank.capacity_liters:
        raise AppError("CONFLICT")
    movement = Movement(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_tank_id=tank.fuel_tank_id,
        movement_type="RECEIPT",
        liters=body.liters,
        reference=body.reference,
        occurred_at=body.occurred_at,
        recorded_by=auth.user_id,
    )
    auth.db.add(movement)
    auth.db.flush()
    _audit(auth, "fuel.stock.receive", movement.fuel_stock_movement_id, tank.site_id)
    auth.db.commit()
    return movement


def _validate_vehicle_and_driver(auth: Authorized, body: IssueCreate, tank: Tank) -> tuple[Vehicle, Driver]:
    vehicle = auth.db.scalar(
        select(Vehicle)
        .where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == body.vehicle_id,
            Vehicle.site_id == tank.site_id,
        )
        .with_for_update()
    )
    if vehicle is None or vehicle.status == "RETIRED":
        raise AppError("NOT_FOUND")
    if vehicle.fuel_type in {"DIESEL", "PETROL"} and vehicle.fuel_type != tank.fuel_type:
        raise AppError("CONFLICT")
    driver = auth.db.scalar(
        select(Driver).where(
            Driver.tenant_id == auth.tenant_id,
            Driver.driver_id == body.driver_id,
            Driver.site_id == tank.site_id,
            Driver.status == "ACTIVE",
        )
    )
    now = auth.clock.now()
    assignment = auth.db.scalar(
        select(VehicleAssignment.vehicle_assignment_id)
        .where(
            VehicleAssignment.tenant_id == auth.tenant_id,
            VehicleAssignment.vehicle_id == body.vehicle_id,
            VehicleAssignment.driver_id == body.driver_id,
            VehicleAssignment.site_id == tank.site_id,
            VehicleAssignment.status == "ACTIVE",
            VehicleAssignment.valid_from <= now,
            or_(VehicleAssignment.valid_to.is_(None), VehicleAssignment.valid_to > now),
        )
        .limit(1)
    )
    if driver is None or assignment is None:
        raise AppError("CONFLICT")
    category = auth.db.get(VehicleCategory, vehicle.vehicle_category_id)
    allowed = set()
    if category and category.has_odometer:
        allowed.add("ODOMETER")
    if category and category.has_hour_meter:
        allowed.add("HOUR_METER")
    if allowed and (body.meter_kind not in allowed or body.meter_value is None):
        raise AppError("VALIDATION_ERROR")
    if not allowed and (body.meter_kind is not None or body.meter_value is not None):
        raise AppError("VALIDATION_ERROR")
    if body.meter_kind is not None and body.meter_value is not None:
        previous = auth.db.scalar(
            select(Issue)
            .outerjoin(
                Decision,
                (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
            )
            .where(
                Issue.tenant_id == auth.tenant_id,
                Issue.vehicle_id == body.vehicle_id,
                Issue.meter_kind == body.meter_kind,
                Decision.decision == "APPROVED",
            )
            .order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
            .limit(1)
        )
        if previous and (
            body.meter_value < (previous.meter_value or ZERO) or body.requested_at < previous.requested_at
        ):
            raise AppError("CONFLICT")
    return vehicle, driver


def create_issue(auth: Authorized, body: IssueCreate) -> Issue:
    tank = _tank(auth, body.fuel_tank_id, lock=True)
    now = auth.clock.now()
    if body.requested_at > now + timedelta(seconds=5) or body.requested_at < now - timedelta(hours=24):
        raise AppError("VALIDATION_ERROR")
    _validate_vehicle_and_driver(auth, body, tank)
    available = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) - _reserved(
        auth.db, auth.tenant_id, tank.fuel_tank_id
    )
    if body.liters > available:
        raise AppError("CONFLICT")
    issue = Issue(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_tank_id=tank.fuel_tank_id,
        vehicle_id=body.vehicle_id,
        driver_id=body.driver_id,
        liters=body.liters,
        meter_kind=body.meter_kind,
        meter_value=body.meter_value,
        requested_at=body.requested_at,
        requested_by=auth.user_id,
    )
    auth.db.add(issue)
    auth.db.flush()
    _audit(auth, "fuel.issue.request", issue.fuel_issue_id, issue.site_id)
    auth.db.commit()
    return issue


def decide_issue(auth: Authorized, issue_id: uuid.UUID, body: DecisionCreate) -> Issue:
    issue = auth.db.scalar(
        select(Issue)
        .where(Issue.tenant_id == auth.tenant_id, Issue.fuel_issue_id == issue_id)
        .with_for_update()
    )
    if issue is None or not _in_scope(auth, issue.site_id):
        raise AppError("NOT_FOUND")
    if issue.requested_by == auth.user_id:
        raise AppError("CONFLICT")
    if auth.db.scalar(
        select(Decision.fuel_issue_decision_id).where(
            Decision.tenant_id == auth.tenant_id, Decision.fuel_issue_id == issue_id
        )
    ):
        raise AppError("CONFLICT")
    tank = _tank(auth, issue.fuel_tank_id, lock=True)
    if body.decision == "APPROVED":
        if _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) < issue.liters:
            raise AppError("CONFLICT")
        if issue.meter_kind is not None and issue.meter_value is not None:
            latest = auth.db.scalar(
                select(Issue)
                .outerjoin(
                    Decision,
                    (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
                )
                .where(
                    Issue.tenant_id == auth.tenant_id,
                    Issue.vehicle_id == issue.vehicle_id,
                    Issue.meter_kind == issue.meter_kind,
                    Decision.decision == "APPROVED",
                )
                .order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
                .limit(1)
            )
            if latest and (
                issue.meter_value < (latest.meter_value or ZERO) or issue.requested_at < latest.requested_at
            ):
                raise AppError("CONFLICT")
        auth.db.add(
            Movement(
                tenant_id=auth.tenant_id,
                site_id=issue.site_id,
                fuel_tank_id=issue.fuel_tank_id,
                movement_type="ISSUE",
                liters=issue.liters,
                fuel_issue_id=issue.fuel_issue_id,
                occurred_at=issue.requested_at,
                recorded_by=auth.user_id,
            )
        )
    decision = Decision(
        tenant_id=auth.tenant_id,
        fuel_issue_id=issue.fuel_issue_id,
        decision=body.decision,
        reason_code=body.reason_code,
        decided_by=auth.user_id,
    )
    auth.db.add(decision)
    auth.db.flush()
    _audit(auth, "fuel.issue.decide", issue.fuel_issue_id, issue.site_id)
    auth.db.commit()
    return issue


def list_issues(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None, status: str | None
) -> tuple[list[dict[str, object]], int]:
    stmt = (
        select(Issue, Tank.code, Tank.fuel_type, Vehicle.fleet_number, Decision)
        .join(Tank, (Tank.tenant_id == Issue.tenant_id) & (Tank.fuel_tank_id == Issue.fuel_tank_id))
        .join(Vehicle, (Vehicle.tenant_id == Issue.tenant_id) & (Vehicle.vehicle_id == Issue.vehicle_id))
        .outerjoin(
            Decision,
            (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
        )
        .where(Issue.tenant_id == auth.tenant_id)
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Issue.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Issue.site_id == site_id)
    if status == "PENDING_APPROVAL":
        stmt = stmt.where(Decision.fuel_issue_decision_id.is_(None))
    elif status == "APPROVED":
        stmt = stmt.where(Decision.decision == "APPROVED")
    elif status == "REJECTED":
        stmt = stmt.where(Decision.decision == "REJECTED")
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.execute(
        stmt.order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return (
        [
            {
                "fuel_issue_id": issue.fuel_issue_id,
                "site_id": issue.site_id,
                "fuel_tank_id": issue.fuel_tank_id,
                "tank_code": tank_code,
                "fuel_type": fuel_type,
                "vehicle_id": issue.vehicle_id,
                "vehicle_fleet_number": fleet_number,
                "driver_id": issue.driver_id,
                "liters": issue.liters,
                "meter_kind": issue.meter_kind,
                "meter_value": issue.meter_value,
                "requested_at": issue.requested_at,
                "requested_by": issue.requested_by,
                "status": decision.decision if decision else "PENDING_APPROVAL",
                "decided_by": decision.decided_by if decision else None,
                "decided_at": decision.decided_at if decision else None,
                "reason_code": decision.reason_code if decision else None,
            }
            for issue, tank_code, fuel_type, fleet_number, decision in rows
        ],
        total,
    )


def issue_output(auth: Authorized, issue: Issue) -> dict[str, object]:
    tank = auth.db.scalar(
        select(Tank).where(Tank.tenant_id == auth.tenant_id, Tank.fuel_tank_id == issue.fuel_tank_id)
    )
    vehicle = auth.db.scalar(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == issue.vehicle_id)
    )
    decision = auth.db.scalar(
        select(Decision).where(
            Decision.tenant_id == auth.tenant_id, Decision.fuel_issue_id == issue.fuel_issue_id
        )
    )
    return {
        "fuel_issue_id": issue.fuel_issue_id,
        "site_id": issue.site_id,
        "fuel_tank_id": issue.fuel_tank_id,
        "tank_code": tank.code if tank else "?",
        "fuel_type": tank.fuel_type if tank else "DIESEL",
        "vehicle_id": issue.vehicle_id,
        "vehicle_fleet_number": vehicle.fleet_number if vehicle else "?",
        "driver_id": issue.driver_id,
        "liters": issue.liters,
        "meter_kind": issue.meter_kind,
        "meter_value": issue.meter_value,
        "requested_at": issue.requested_at,
        "requested_by": issue.requested_by,
        "status": decision.decision if decision else "PENDING_APPROVAL",
        "decided_by": decision.decided_by if decision else None,
        "decided_at": decision.decided_at if decision else None,
        "reason_code": decision.reason_code if decision else None,
    }
