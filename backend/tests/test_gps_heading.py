"""Cap mesuré (0060) : transmis par l'équipement, validé, restitué tel quel ; jamais calculé par l'API."""

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.demo.gps import bearing_deg
from app.fleet.gps_contract import GpsPosition, valid_gps_position
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_simulated_tracker_bearing() -> None:
    assert bearing_deg(None, 10.0, -12.0) is None
    assert bearing_deg((10.0, -12.0), 10.0, -12.0) is None  # immobile : aucun cap transmis
    assert bearing_deg((10.0, -12.0), 10.01, -12.0) == 0.0  # vers le nord
    assert bearing_deg((10.0, -12.0), 10.0, -11.99) == 90.0  # vers l'est
    assert bearing_deg((10.0, -12.0), 9.99, -12.0) == 180.0
    assert 269.9 <= (bearing_deg((10.0, -12.0), 10.0, -12.01) or 0) < 360


def test_contract_rejects_out_of_range_heading() -> None:
    now = datetime.now(UTC)
    base = {
        "vehicle_id": uuid.uuid4(),
        "device_id": "d",
        "latitude": 10.0,
        "longitude": -12.0,
        "recorded_at": now,
    }
    assert valid_gps_position(GpsPosition(**base, heading_deg=359.9), received_at=now)  # type: ignore[arg-type]
    for bad in (360.0, -1.0, float("nan")):
        assert not valid_gps_position(GpsPosition(**base, heading_deg=bad), received_at=now)  # type: ignore[arg-type]


def test_tracker_heading_is_stored_and_returned_in_latest_and_track(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    device = "fictif-" + uuid.uuid4().hex
    token = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Pas avant l'activation du traceur (GPS-23) : horodatages postérieurs au provisionnement.
    now = datetime.now(UTC)
    body = {"device_id": device, "latitude": 10.0, "longitude": -12.0, "speed_kmh": 30.0}

    for sequence, heading in ((1, 360), (2, -5), (3, "45")):
        refused = client.post(
            f"{API}/gps/telemetry",
            headers=headers,
            json={**body, "sequence": sequence, "heading_deg": heading, "recorded_at": now.isoformat()},
        )
        assert refused.status_code == 422, (heading, refused.text)
    first = client.post(
        f"{API}/gps/telemetry",
        headers=headers,
        json={
            **body,
            "sequence": 10,
            "heading_deg": 359.9,
            "recorded_at": now.isoformat(),
        },
    )
    assert first.status_code == 204, first.text
    # Équipement qui ne mesure pas le cap : champ absent, rien n'est déduit.
    second = client.post(
        f"{API}/gps/telemetry",
        headers=headers,
        json={
            **body,
            "sequence": 11,
            "latitude": 10.001,
            "recorded_at": (now + timedelta(seconds=1)).isoformat(),
        },
    )
    assert second.status_code == 204, second.text

    time.sleep(1.2)  # le second point (horodaté +1 s) doit être passé pour figurer dans le trajet
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    row = next(p for p in latest if p["vehicle_id"] == vehicle)
    assert row["heading_deg"] is None  # dernier point sans cap : jamais recalculé depuis le précédent

    track = client.get(
        f"{API}/vehicles/{vehicle}/gps/track",
        headers=w.ops.headers,
        params={
            "purpose": "OPERATIONS_REVIEW",
            "from": (now - timedelta(minutes=5)).isoformat(),
            "to": (now + timedelta(minutes=1)).isoformat(),
        },
    )
    assert track.status_code == 200, track.text
    assert [p["heading_deg"] for p in track.json()["points"]] == [359.9, None]


def test_phone_heading_is_validated_and_returned(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    share = client.post(
        f"{API}/me/gps/shares", headers=w.ops.headers, json={"vehicle_id": vehicle, "consent": True}
    ).json()["phone_share_id"]
    path = f"{API}/me/gps/shares/{share}/positions"
    point = {
        "latitude": 9.5,
        "longitude": -13.7,
        "accuracy_m": 8.0,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    assert client.post(path, headers=w.ops.headers, json={**point, "heading_deg": 361.0}).status_code == 422
    accepted = client.post(
        path, headers=w.ops.headers, json={**point, "heading_deg": 90.5, "speed_kmh": 12.0}
    )
    assert accepted.status_code == 204, accepted.text
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    assert next(p for p in latest if p["vehicle_id"] == vehicle)["heading_deg"] == 90.5
