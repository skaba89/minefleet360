from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.dispatch.smart_eta import RouteEstimate, usable_eta

TENANT = UUID(int=1)
SITE = UUID(int=2)
VEHICLE = UUID(int=3)
DESTINATION = UUID(int=4)
NOW = datetime(2026, 11, 26, tzinfo=UTC)
ESTIMATE = RouteEstimate(TENANT, SITE, VEHICLE, DESTINATION, NOW - timedelta(seconds=30), NOW, NOW, 1000, 120)


def eta(estimate: RouteEstimate) -> int | None:
    return usable_eta(
        estimate,
        tenant_id=TENANT,
        site_id=SITE,
        vehicle_id=VEHICLE,
        destination_id=DESTINATION,
        now=NOW,
    )


def test_valid_route() -> None:
    assert eta(ESTIMATE) == 120
    assert eta(replace(ESTIMATE, distance_m=0, duration_seconds=0)) == 0


@pytest.mark.parametrize(
    "estimate",
    [
        replace(ESTIMATE, tenant_id=UUID(int=99)),
        replace(ESTIMATE, site_id=UUID(int=99)),
        replace(ESTIMATE, vehicle_id=UUID(int=99)),
        replace(ESTIMATE, destination_id=UUID(int=99)),
        replace(ESTIMATE, position_recorded_at=NOW - timedelta(minutes=3)),
        replace(ESTIMATE, calculated_at=NOW + timedelta(seconds=1)),
        replace(ESTIMATE, position_received_at=NOW - timedelta(seconds=40)),
        replace(ESTIMATE, position_recorded_at=NOW.replace(tzinfo=None)),
        replace(ESTIMATE, distance_m=-1),
        replace(ESTIMATE, duration_seconds=-1),
        replace(ESTIMATE, duration_seconds=0),
    ],
)
def test_invalid_route(estimate: RouteEstimate) -> None:
    assert eta(estimate) is None
