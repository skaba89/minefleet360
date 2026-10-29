"""Validation des données GPS avant toute future ingestion."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.fleet.gps_contract import GpsPosition, valid_gps_position

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _position() -> GpsPosition:
    return GpsPosition(
        vehicle_id=uuid.uuid4(),
        device_id="gps-unit-1",
        latitude=9.6412,
        longitude=-13.5784,
        recorded_at=NOW,
        speed_kmh=42.0,
        accuracy_m=5.0,
    )


def test_accepts_valid_position() -> None:
    assert valid_gps_position(_position(), received_at=NOW)


@pytest.mark.parametrize(
    ("changes"),
    [
        {"latitude": 91.0},
        {"latitude": float("nan")},
        {"longitude": -181.0},
        {"speed_kmh": -1.0},
        {"speed_kmh": float("inf")},
        {"accuracy_m": -2.0},
        {"device_id": "  "},
        {"vehicle_id": uuid.UUID(int=0)},
        {"recorded_at": NOW + timedelta(minutes=3)},
        {"recorded_at": NOW - timedelta(hours=25)},
        {"recorded_at": NOW.replace(tzinfo=None)},
    ],
)
def test_rejects_invalid_positions(changes: dict[str, object]) -> None:
    assert not valid_gps_position(replace(_position(), **changes), received_at=NOW)


def test_rejects_naive_reception_time() -> None:
    assert not valid_gps_position(_position(), received_at=NOW.replace(tzinfo=None))
