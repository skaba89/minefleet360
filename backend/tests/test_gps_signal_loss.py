"""Perte de signal GPS (0062) : balayage `minefleet sweep-gps-signal`, fermeture à la position suivante."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.cli import main
from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, _vehicle_status, w  # noqa: F401


def _tracker(client: TestClient, w: World, vehicle: str) -> tuple[str, str]:  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    token = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    ).json()["token"]
    return device, token


def _old_position(w: World, vehicle: str, device: str, minutes_ago: int) -> datetime:  # noqa: F811
    """Position ancienne écrite en base (l'API refuse les mesures antérieures à l'activation du traceur)."""
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "INSERT INTO fleet_gps_position (tenant_id, vehicle_id, site_id, device_id, latitude, "
                    "longitude, speed_kmh, recorded_at, received_at) "
                    "VALUES (:t, :v, :s, :d, 10.0, -12.0, 0, :at, :at)"
                ),
                {"t": w.t.tenant_id, "v": vehicle, "s": w.t.sites["S1"], "d": device, "at": at},
            )
    finally:
        engine.dispose()
    return at


def _lost(client: TestClient, w: World) -> list[dict]:  # type: ignore[type-arg]  # noqa: F811
    resp = client.get(
        f"{API}/gps/alerts", headers=w.ops.headers, params={"kind": "SIGNAL_LOST", "page_size": 50}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]  # type: ignore[no-any-return]


def test_sweep_flags_only_silent_available_tracked_vehicles_once(client: TestClient, w: World) -> None:  # noqa: F811
    site = str(w.t.sites["S1"])
    silent, recent, maintenance, untracked = (_vehicle(client, w) for _ in range(4))
    devices = {v: _tracker(client, w, v) for v in (silent, recent, maintenance)}
    last = _old_position(w, silent, devices[silent][0], 30)
    _old_position(w, recent, devices[recent][0], 2)
    _old_position(w, maintenance, devices[maintenance][0], 30)
    _old_position(w, untracked, "aucun-traceur", 30)
    assert _vehicle_status(client, w, maintenance, "IN_MAINTENANCE").status_code == 200

    assert main(["sweep-gps-signal"]) == 0
    assert _lost(client, w) == []  # aucun délai réglé : pas de surveillance

    policy = client.put(
        f"{API}/sites/{site}/gps-policy", headers=w.ops.headers, json={"signal_loss_minutes": 10}
    )
    assert policy.status_code == 200 and policy.json()["signal_loss_minutes"] == 10
    assert main(["sweep-gps-signal"]) == 0
    assert main(["sweep-gps-signal"]) == 0  # rejeu : toujours une seule alerte
    (alert,) = _lost(client, w)
    assert alert["vehicle_id"] == silent and alert["closed_at"] is None
    assert datetime.fromisoformat(alert["last_measured_at"]) == last
    assert datetime.fromisoformat(alert["opened_at"]) > last

    # Le signal revient : la position suivante ferme l'alerte.
    device, token = devices[silent]
    back = client.post(
        f"{API}/gps/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "device_id": device,
            "sequence": 1,
            "latitude": 10.0,
            "longitude": -12.0,
            "recorded_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        },
    )
    assert back.status_code == 204, back.text
    (closed,) = _lost(client, w)
    assert closed["closed_at"] is not None
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"page_size": 200}).json()[
        "items"
    ]
    sweeps = [e for e in events if e["action"] == "fleet.gps.signal_loss.sweep"]
    assert len(sweeps) == 1 and sweeps[0]["actor_kind"] == "SYSTEM"


def test_signal_loss_delay_bounds(client: TestClient, w: World) -> None:  # noqa: F811
    url = f"{API}/sites/{w.t.sites['S1']}/gps-policy"
    for bad in (4, 1441, "10"):
        assert client.put(url, headers=w.ops.headers, json={"signal_loss_minutes": bad}).status_code == 422
    both = client.put(
        url, headers=w.ops.headers, json={"speed_limit_kmh": 40, "signal_loss_minutes": 15}
    ).json()
    assert (both["speed_limit_kmh"], both["signal_loss_minutes"]) == ("40.0", 15)
