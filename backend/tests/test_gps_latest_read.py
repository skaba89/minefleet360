"""Dernières positions GPS : la lecture indexée par véhicule rend exactement ce que rendait l'ancienne
requête par fonction de fenêtre (référence conservée ici), sans lire tout l'historique."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

# Ancienne requête (fonction de fenêtre sur toutes les positions de la société) : référence de comportement.
REFERENCE = text(
    """
    WITH ranked AS (
      SELECT gps_position_id,
             row_number() OVER (PARTITION BY vehicle_id
                                ORDER BY recorded_at DESC, received_at DESC, gps_position_id DESC) AS rn
      FROM fleet_gps_position
      WHERE tenant_id = :tenant AND recorded_at <= :bound
    )
    SELECT p.vehicle_id, p.recorded_at
    FROM fleet_gps_position p
    JOIN vehicle v ON v.tenant_id = p.tenant_id AND v.vehicle_id = p.vehicle_id AND v.site_id = p.site_id
    JOIN ranked r ON r.gps_position_id = p.gps_position_id
    WHERE r.rn = 1 AND p.tenant_id = :tenant
    """
)


def _tracker(client: TestClient, w: World, vehicle: str) -> tuple[str, str]:  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    created = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    )
    assert created.status_code == 201, created.text
    return device, created.json()["token"]


def _send(client: TestClient, device: str, token: str, sequence: int, at: datetime, lat: float) -> None:
    resp = client.post(
        f"{API}/gps/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "device_id": device,
            "latitude": lat,
            "longitude": -13.7,
            "accuracy_m": 8.0,
            "recorded_at": at.isoformat(),
            "sequence": sequence,
        },
    )
    assert resp.status_code == 204, resp.text


def test_latest_positions_match_reference_and_skip_moved_vehicle(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    vehicles = [_vehicle(client, w) for _ in range(3)]
    for vehicle in vehicles:
        device, token = _tracker(client, w, vehicle)
        start = datetime.now(UTC)  # jamais avant l'activation du traceur (refus anti-attribution)
        for seq in (1, 2, 3):
            _send(client, device, token, seq, start + timedelta(seconds=seq), 9.5 + seq / 1000)
    # Le troisième engin change de site : sa dernière position (relevée sur l'ancien site) n'est plus montrée.
    moved = vehicles[2]
    client.post(f"{API}/vehicles/{moved}/gps/tracker/revoke", headers=w.ops.headers)
    current = client.get(f"{API}/vehicles/{moved}", headers=w.t.admin.headers)
    patched = client.patch(
        f"{API}/vehicles/{moved}",
        headers={**w.t.admin.headers, "If-Match": current.headers["ETag"]},
        json={"site_id": str(w.t.sites["S2"])},
    )
    assert patched.status_code == 200, patched.text

    served = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers)
    assert served.status_code == 200, served.text
    by_vehicle = {p["vehicle_id"]: p for p in served.json()}
    assert set(vehicles[:2]) <= set(by_vehicle) and moved not in by_vehicle
    for vehicle in vehicles[:2]:  # la plus récente des trois positions
        assert abs(by_vehicle[vehicle]["latitude"] - 9.503) < 1e-9

    db = new_session()
    try:
        set_tenant_context(db, w.t.tenant_id)
        bound = datetime.now(UTC) + timedelta(minutes=2)
        reference = {
            (str(v), at) for v, at in db.execute(REFERENCE, {"tenant": w.t.tenant_id, "bound": bound})
        }
    finally:
        db.close()
    assert {(p["vehicle_id"], datetime.fromisoformat(p["recorded_at"])) for p in served.json()} == reference
