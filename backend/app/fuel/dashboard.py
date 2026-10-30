"""Agrégats opérationnels du tableau de bord carburant, bornés au tenant et aux sites autorisés."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, func, select, true
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.fuel.models import (
    FuelIssue,
    FuelPumpAnomalyCase,
    FuelPumpAnomalyEvent,
    FuelStockAlert,
    FuelStockMovement,
    FuelStocktake,
)
from app.organization.models import Site

ZERO = Decimal("0")
TWO_DECIMALS = Decimal("0.01")
MAX_PERIOD = timedelta(days=366)


def _site_condition(
    column: InstrumentedAttribute[uuid.UUID], auth: Authorized, site_id: uuid.UUID | None
) -> ColumnElement[bool]:
    if site_id is not None:
        return column == site_id
    if auth.scope.tenant_wide:
        return true()
    return column.in_(auth.scope.site_ids)


def _validate_site(auth: Authorized, site_id: uuid.UUID | None) -> None:
    if site_id is None:
        return
    if not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    existing = auth.db.scalar(
        select(Site.site_id).where(Site.tenant_id == auth.tenant_id, Site.site_id == site_id)
    )
    if existing is None:
        raise AppError("NOT_FOUND")


def _period(auth: Authorized, from_at: datetime | None, to_at: datetime | None) -> tuple[datetime, datetime]:
    end = to_at or auth.clock.now()
    start = from_at or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None or start >= end or end - start > MAX_PERIOD:
        raise AppError("VALIDATION_ERROR")
    return start, end


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or ZERO))


def fuel_dashboard(
    auth: Authorized,
    *,
    site_id: uuid.UUID | None,
    from_at: datetime | None,
    to_at: datetime | None,
) -> dict[str, object]:
    """Construit les KPI à partir du journal de stock et des dossiers d'anomalie persistés."""
    start, end = _period(auth, from_at, to_at)
    _validate_site(auth, site_id)
    movement_scope = _site_condition(FuelStockMovement.site_id, auth, site_id)

    movement_totals = auth.db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (FuelStockMovement.movement_type == "ISSUE", FuelStockMovement.liters),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            FuelStockMovement.movement_type.in_(("RECEIPT", "PURCHASE_RECEIPT")),
                            FuelStockMovement.liters,
                        ),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
        ).where(
            FuelStockMovement.tenant_id == auth.tenant_id,
            movement_scope,
            FuelStockMovement.occurred_at >= start,
            FuelStockMovement.occurred_at < end,
        )
    ).one()

    stocktake_variance = auth.db.execute(
        select(func.coalesce(func.sum(FuelStocktake.delta_liters), ZERO)).where(
            FuelStocktake.tenant_id == auth.tenant_id,
            _site_condition(FuelStocktake.site_id, auth, site_id),
            FuelStocktake.occurred_at >= start,
            FuelStocktake.occurred_at < end,
        )
    ).scalar_one()

    ranked_events = (
        select(
            FuelPumpAnomalyEvent.fuel_pump_anomaly_case_id.label("case_id"),
            FuelPumpAnomalyEvent.event_type,
            FuelPumpAnomalyEvent.occurred_at,
            func.row_number()
            .over(
                partition_by=FuelPumpAnomalyEvent.fuel_pump_anomaly_case_id,
                order_by=(
                    FuelPumpAnomalyEvent.occurred_at.desc(),
                    FuelPumpAnomalyEvent.fuel_pump_anomaly_event_id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(FuelPumpAnomalyEvent.tenant_id == auth.tenant_id)
        .subquery()
    )
    latest_events = (
        select(
            ranked_events.c.case_id,
            ranked_events.c.event_type,
            ranked_events.c.occurred_at,
        )
        .where(ranked_events.c.row_number == 1)
        .subquery()
    )
    current_status = func.coalesce(latest_events.c.event_type, "OPEN")
    closed_in_period = and_(
        current_status == "CLOSED",
        latest_events.c.occurred_at >= start,
        latest_events.c.occurred_at < end,
    )
    anomaly_metrics = auth.db.execute(
        select(
            func.count().filter(current_status != "CLOSED"),
            func.count().filter(closed_in_period),
            func.avg(
                func.extract("epoch", latest_events.c.occurred_at - FuelPumpAnomalyCase.created_at) / 3600
            ).filter(closed_in_period),
            func.coalesce(
                func.sum(func.abs(FuelPumpAnomalyCase.variance_liters)).filter(
                    FuelPumpAnomalyCase.created_at >= start,
                    FuelPumpAnomalyCase.created_at < end,
                ),
                ZERO,
            ),
        )
        .select_from(FuelPumpAnomalyCase)
        .outerjoin(
            latest_events,
            latest_events.c.case_id == FuelPumpAnomalyCase.fuel_pump_anomaly_case_id,
        )
        .where(
            FuelPumpAnomalyCase.tenant_id == auth.tenant_id,
            _site_condition(FuelPumpAnomalyCase.site_id, auth, site_id),
        )
    ).one()

    alert_metrics = auth.db.execute(
        select(
            func.count(),
            func.count().filter(FuelStockAlert.acknowledged_at.is_(None)),
        ).where(
            FuelStockAlert.tenant_id == auth.tenant_id,
            _site_condition(FuelStockAlert.site_id, auth, site_id),
            FuelStockAlert.resolved_at.is_(None),
        )
    ).one()

    vehicle_rows = auth.db.execute(
        select(
            FuelIssue.vehicle_id,
            Vehicle.fleet_number,
            FuelIssue.site_id,
            func.sum(FuelStockMovement.liters).label("liters"),
        )
        .join(
            FuelIssue,
            (FuelIssue.tenant_id == FuelStockMovement.tenant_id)
            & (FuelIssue.fuel_issue_id == FuelStockMovement.fuel_issue_id),
        )
        .join(
            Vehicle,
            (Vehicle.tenant_id == FuelIssue.tenant_id) & (Vehicle.vehicle_id == FuelIssue.vehicle_id),
        )
        .where(
            FuelStockMovement.tenant_id == auth.tenant_id,
            movement_scope,
            FuelStockMovement.movement_type == "ISSUE",
            FuelStockMovement.occurred_at >= start,
            FuelStockMovement.occurred_at < end,
        )
        .group_by(FuelIssue.vehicle_id, Vehicle.fleet_number, FuelIssue.site_id)
        .order_by(func.sum(FuelStockMovement.liters).desc(), Vehicle.fleet_number)
        .limit(10)
    ).all()

    site_rows = auth.db.execute(
        select(
            FuelStockMovement.site_id,
            Site.code,
            Site.name,
            func.sum(FuelStockMovement.liters).label("liters"),
        )
        .join(
            Site,
            (Site.tenant_id == FuelStockMovement.tenant_id) & (Site.site_id == FuelStockMovement.site_id),
        )
        .where(
            FuelStockMovement.tenant_id == auth.tenant_id,
            movement_scope,
            FuelStockMovement.movement_type == "ISSUE",
            FuelStockMovement.occurred_at >= start,
            FuelStockMovement.occurred_at < end,
        )
        .group_by(FuelStockMovement.site_id, Site.code, Site.name)
        .order_by(func.sum(FuelStockMovement.liters).desc(), Site.code)
    ).all()

    day_bucket = cast(func.timezone("UTC", FuelStockMovement.occurred_at), Date)
    trend_rows = auth.db.execute(
        select(
            day_bucket.label("day"),
            func.coalesce(
                func.sum(
                    case(
                        (FuelStockMovement.movement_type == "ISSUE", FuelStockMovement.liters),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ).label("distributed"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            FuelStockMovement.movement_type.in_(("RECEIPT", "PURCHASE_RECEIPT")),
                            FuelStockMovement.liters,
                        ),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ).label("received"),
        )
        .where(
            FuelStockMovement.tenant_id == auth.tenant_id,
            movement_scope,
            FuelStockMovement.occurred_at >= start,
            FuelStockMovement.occurred_at < end,
        )
        .group_by(day_bucket)
        .order_by(day_bucket)
    ).all()
    trends_by_day = {row.day: row for row in trend_rows}
    daily_trend: list[dict[str, object]] = []
    cursor: date = start.date()
    last_day = (end - timedelta(microseconds=1)).date()
    while cursor <= last_day:
        row = trends_by_day.get(cursor)
        daily_trend.append(
            {
                "day": cursor,
                "distributed_liters": _decimal(row.distributed if row else None),
                "received_liters": _decimal(row.received if row else None),
            }
        )
        cursor += timedelta(days=1)

    average_resolution = anomaly_metrics[2]
    return {
        "period_start": start,
        "period_end": end,
        "distributed_liters": _decimal(movement_totals[0]),
        "received_liters": _decimal(movement_totals[1]),
        "stocktake_variance_liters": _decimal(stocktake_variance),
        "qualified_anomaly_variance_liters": _decimal(anomaly_metrics[3]),
        "open_anomaly_cases": int(anomaly_metrics[0]),
        "closed_anomaly_cases": int(anomaly_metrics[1]),
        "average_resolution_hours": (
            _decimal(average_resolution).quantize(TWO_DECIMALS) if average_resolution is not None else None
        ),
        "active_stock_alerts": int(alert_metrics[0]),
        "unacknowledged_stock_alerts": int(alert_metrics[1]),
        "vehicle_consumption": [
            {
                "vehicle_id": row.vehicle_id,
                "vehicle_fleet_number": row.fleet_number,
                "site_id": row.site_id,
                "liters": _decimal(row.liters),
            }
            for row in vehicle_rows
        ],
        "site_consumption": [
            {
                "site_id": row.site_id,
                "site_code": row.code,
                "site_name": row.name,
                "liters": _decimal(row.liters),
            }
            for row in site_rows
        ],
        "daily_trend": daily_trend,
    }
