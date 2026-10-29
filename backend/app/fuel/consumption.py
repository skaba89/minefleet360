"""Calcul de la consommation entre pleins complets confirmés."""

import uuid
from collections import defaultdict
from decimal import Decimal
from statistics import median

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import PageParams
from app.fleet.models import Vehicle
from app.fuel.models import FuelIssue, FuelIssueDecision, FuelTank

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
RATE_PRECISION = Decimal("0.001")
ANOMALY_MULTIPLIER = Decimal("1.5")
BASELINE_INTERVALS = 5
MINIMUM_COMPARISONS = 3


def vehicle_consumption(
    auth: Authorized,
    vehicle_id: uuid.UUID,
    page: PageParams,
    *,
    meter_kind: str | None,
) -> tuple[list[dict[str, object]], int]:
    vehicle = auth.db.scalar(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == vehicle_id)
    )
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")

    stmt = (
        select(FuelIssue, FuelTank.fuel_type)
        .join(
            FuelTank,
            (FuelTank.tenant_id == FuelIssue.tenant_id) & (FuelTank.fuel_tank_id == FuelIssue.fuel_tank_id),
        )
        .join(
            FuelIssueDecision,
            (FuelIssueDecision.tenant_id == FuelIssue.tenant_id)
            & (FuelIssueDecision.fuel_issue_id == FuelIssue.fuel_issue_id),
        )
        .where(
            FuelIssue.tenant_id == auth.tenant_id,
            FuelIssue.vehicle_id == vehicle_id,
            FuelIssueDecision.decision == "APPROVED",
        )
    )
    rows = list(
        auth.db.execute(stmt.order_by(FuelIssue.meter_kind, FuelIssue.requested_at, FuelIssue.fuel_issue_id))
    )

    by_meter: dict[str, list[tuple[FuelIssue, str]]] = defaultdict(list)
    for issue, fuel_type in rows:
        for kind in ("ODOMETER", "HOUR_METER"):
            by_meter[kind].append((issue, fuel_type))

    intervals: list[dict[str, object]] = []
    for kind, events in by_meter.items():
        previous_full: FuelIssue | None = None
        active_context: tuple[uuid.UUID, str] | None = None
        liters_since_full = ZERO
        prior_rates: list[Decimal] = []
        for issue, fuel_type in events:
            if issue.meter_kind not in (None, kind):
                previous_full = None
                liters_since_full = ZERO
                prior_rates = []
                continue
            context = (issue.site_id, fuel_type)
            if context != active_context:
                previous_full = None
                liters_since_full = ZERO
                prior_rates = []
                active_context = context
            if issue.meter_kind is None:
                if previous_full is not None:
                    liters_since_full += issue.liters
                continue
            if previous_full is None:
                if issue.full_tank:
                    previous_full = issue
                continue

            liters_since_full += issue.liters
            if not issue.full_tank:
                continue

            start_value = previous_full.meter_value or ZERO
            end_value = issue.meter_value or ZERO
            meter_delta = end_value - start_value
            if meter_delta > ZERO and liters_since_full > ZERO:
                rate = (
                    liters_since_full * ONE_HUNDRED / meter_delta
                    if kind == "ODOMETER"
                    else liters_since_full / meter_delta
                ).quantize(RATE_PRECISION)
                comparison_rates = prior_rates[-BASELINE_INTERVALS:]
                comparison_rate = (
                    Decimal(median(comparison_rates)).quantize(RATE_PRECISION)
                    if len(comparison_rates) >= MINIMUM_COMPARISONS
                    else None
                )
                if auth.scope.covers_site(issue.site_id):
                    intervals.append(
                        {
                            "fuel_issue_id": issue.fuel_issue_id,
                            "vehicle_id": vehicle.vehicle_id,
                            "vehicle_fleet_number": vehicle.fleet_number,
                            "site_id": issue.site_id,
                            "fuel_type": fuel_type,
                            "meter_kind": kind,
                            "interval_start_at": previous_full.requested_at,
                            "interval_end_at": issue.requested_at,
                            "start_meter_value": start_value,
                            "end_meter_value": end_value,
                            "meter_delta": meter_delta,
                            "fuel_liters": liters_since_full,
                            "rate_liters_per_unit": rate,
                            "comparison_median_rate": comparison_rate,
                            "comparison_interval_count": len(comparison_rates),
                            "is_anomaly": comparison_rate is not None
                            and rate > comparison_rate * ANOMALY_MULTIPLIER,
                        }
                    )
                prior_rates.append(rate)
            previous_full = issue
            liters_since_full = ZERO

    if meter_kind is not None:
        intervals = [row for row in intervals if row["meter_kind"] == meter_kind]
    intervals.sort(key=lambda row: (row["interval_end_at"], row["fuel_issue_id"]), reverse=True)
    total = len(intervals)
    return intervals[page.offset : page.offset + page.page_size], total
