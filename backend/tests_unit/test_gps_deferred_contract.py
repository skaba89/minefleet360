"""Tests du contrat de lot GPS différé avant intégration API et PostgreSQL."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.fleet.gps_deferred_contract import (
    MAX_DEFERRED_BYTES,
    MAX_DEFERRED_POINTS,
    capture_in_window,
    decode_deferred_batch,
    point_fingerprint,
)

NOW = datetime(2026, 11, 22, 8, tzinfo=UTC)


def point() -> dict[str, object]:
    return {
        "client_point_id": str(uuid.uuid4()),
        "recorded_at": NOW.isoformat(),
        "latitude": 9.5,
        "longitude": -13.7,
        "accuracy_m": 12,
    }


def decode(points: list[dict[str, object]]) -> str:
    return point_fingerprint(decode_deferred_batch(json.dumps({"points": points}).encode()).points[0])


def test_normalized_fingerprint() -> None:
    original = point()
    equivalent = {**original, "recorded_at": "2026-11-22T09:00:00+01:00", "accuracy_m": 12.0}
    assert decode([original]) == decode([equivalent])
    assert decode([original]) != decode([{**original, "latitude": 9.6}])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "other"),
        ("vehicle_id", "other"),
        ("site_id", "other"),
        ("user_id", "other"),
        ("token", "untrusted"),
        ("latitude", 91),
        ("longitude", -181),
        ("accuracy_m", -1),
        ("latitude", float("nan")),
        ("recorded_at", "2026-11-22T08:00:00"),
        ("recorded_at", 1795334400),
        ("client_point_id", "invalid"),
    ],
)
def test_invalid_points(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="Lot GPS invalide"):
        decode([{**point(), field: value}])


def test_bounds_and_duplicate_ids() -> None:
    decode([point() for _ in range(MAX_DEFERRED_POINTS)])
    repeated = point()
    for points in ([], [repeated, repeated], [point() for _ in range(MAX_DEFERRED_POINTS + 1)]):
        with pytest.raises(ValueError, match="Lot GPS invalide"):
            decode(points)
    with pytest.raises(ValueError, match="Taille"):
        decode_deferred_batch(b" " * (MAX_DEFERRED_BYTES + 1))


@pytest.mark.parametrize("raw", [b"", b"{", b'{"points":[],"points":[]}', b'{"points":[],"tenant_id":"x"}'])
def test_invalid_envelope(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_deferred_batch(raw)


def test_capture_window() -> None:
    start = NOW - timedelta(hours=10)
    end = NOW + timedelta(hours=2)

    def allowed(recorded: datetime) -> bool:
        return capture_in_window(recorded, started_at=start, expires_at=end, received_at=NOW)

    assert allowed(NOW - timedelta(minutes=5))
    assert allowed(start)
    assert not allowed(start - timedelta(seconds=1))
    assert allowed(NOW + timedelta(seconds=5))
    assert not allowed(NOW + timedelta(seconds=6))
    assert not allowed(NOW.replace(tzinfo=None))
    assert not capture_in_window(NOW, started_at=start, expires_at=NOW, received_at=NOW)
    assert not capture_in_window(
        NOW - timedelta(hours=13),
        started_at=NOW - timedelta(hours=14),
        expires_at=end,
        received_at=NOW,
    )
