"""Contraintes SQL et RLS du futur canal GPS différé (aucun endpoint activé)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_deferred_identity_constraints_and_rls(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    response = client.post(
        f"{API}/me/gps/shares",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "consent": True},
    )
    assert response.status_code == 201, response.text
    share = response.json()["phone_share_id"]
    other = api.tenant()
    now = datetime.now(UTC)
    params = {
        "tenant": str(w.t.tenant_id),
        "vehicle": vehicle,
        "site": str(w.t.sites["S1"]),
        "device": f"phone:{share}",
        "share": share,
        "source": "PHONE",
        "point": str(uuid.uuid4()),
        "fingerprint": "a" * 64,
        "at": now,
    }
    insert = text(
        "INSERT INTO fleet_gps_position (tenant_id, vehicle_id, site_id, device_id, "
        "phone_share_id, source, client_point_id, client_point_fingerprint, latitude, longitude, recorded_at) "
        "VALUES (:tenant, :vehicle, :site, :device, :share, :source, :point, :fingerprint, 9.5, -13.7, :at)"
    )
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": params["tenant"]})
            conn.execute(insert, params)
            for changes in (
                {"at": now + timedelta(seconds=10)},
                {"point": None, "at": now + timedelta(seconds=20)},
                {"point": str(uuid.uuid4()), "fingerprint": None, "at": now + timedelta(seconds=30)},
                {
                    "point": str(uuid.uuid4()),
                    "fingerprint": "invalid",
                    "at": now + timedelta(seconds=40),
                },
                {
                    "point": str(uuid.uuid4()),
                    "source": "TRACKER",
                    "share": None,
                    "at": now + timedelta(seconds=50),
                },
            ):
                with pytest.raises(IntegrityError), conn.begin_nested():
                    conn.execute(insert, {**params, **changes})
            # Position live historique, sans métadonnées de rejeu.
            conn.execute(
                insert,
                {**params, "point": None, "fingerprint": None, "at": now + timedelta(seconds=60)},
            )
            assert conn.execute(
                text("SELECT count(*) FROM fleet_gps_position WHERE phone_share_id = :share"), {"share": share}
            ).scalar_one() == 2
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(other.tenant_id)})
            assert conn.execute(
                text("SELECT count(*) FROM fleet_gps_position WHERE phone_share_id = :share"), {"share": share}
            ).scalar_one() == 0
    finally:
        engine.dispose()
