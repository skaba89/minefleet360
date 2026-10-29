"""GPS complet sur PostgreSQL : JSON, identité, réaffectation et savepoint."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.fleet.gps_device_credentials import fingerprint_device_secret, new_device_secret
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext
from app.fleet.gps_payload_ingestion import accept_gps_telemetry_payload
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_json_to_postgres_preserves_identity_sequence_and_transaction(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    old_vehicle = _vehicle(client, w)
    vehicle = _vehicle(client, w)
    outsider = api.tenant(sites=())
    other_ops = api.user(outsider, "OPS_MANAGER")
    now = datetime.now(UTC)
    active = now - timedelta(minutes=10)
    binding_id = uuid.uuid4()
    secret = new_device_secret()
    device = f"traceur-fictif-{uuid.uuid4().hex[:12]}"
    engine = create_engine(get_settings().database_url())

    def payload(sequence: int, at: datetime) -> bytes:
        return json.dumps(
            {
                "device_id": device,
                "sequence": sequence,
                "latitude": 9.5,
                "longitude": -13.7,
                "recorded_at": at.isoformat(),
                "speed_kmh": 20,
            }
        ).encode()

    def ingest(
        sequence: int,
        at: datetime,
        *,
        tenant: uuid.UUID = w.t.tenant_id,
        context_tenant: uuid.UUID | None = None,
        credential: str = secret,
        commit: bool = True,
    ) -> bool:
        with Session(engine) as db:
            db.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(tenant)})
            result = accept_gps_telemetry_payload(
                db,
                context=TrustedGatewayContext(context_tenant or tenant),
                payload=payload(sequence, at),
                supplied_secret=credential,
                received_at=now,
            )
            if commit:
                db.commit()
            else:
                db.rollback()
            return result

    def state() -> tuple[int, int | None]:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(w.t.tenant_id)})
            count = conn.execute(
                text("SELECT count(*) FROM fleet_gps_position WHERE device_id = :device"), {"device": device}
            ).scalar_one()
            sequence = conn.execute(
                text(
                    "SELECT last_sequence FROM fleet_gps_device_sequence "
                    "WHERE gps_device_binding_id = :binding"
                ),
                {"binding": binding_id},
            ).scalar_one_or_none()
            return count, sequence

    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(w.t.tenant_id)})
            for binding, target, start, revoked in (
                (uuid.uuid4(), old_vehicle, now - timedelta(hours=2), active),
                (binding_id, vehicle, active, None),
            ):
                conn.execute(
                    text(
                        "INSERT INTO fleet_gps_device_binding "
                        "(gps_device_binding_id, tenant_id, vehicle_id, site_id, "
                        "device_id, active_from, revoked_at) "
                        "VALUES (:id, :tenant, :vehicle, :site, :device, :start, :revoked)"
                    ),
                    {
                        "id": binding,
                        "tenant": w.t.tenant_id,
                        "vehicle": target,
                        "site": w.t.sites["S1"],
                        "device": device,
                        "start": start,
                        "revoked": revoked,
                    },
                )
            conn.execute(
                text(
                    "INSERT INTO fleet_gps_device_credential "
                    "(tenant_id, gps_device_binding_id, secret_fingerprint, active_from) "
                    "VALUES (:tenant, :binding, :fingerprint, :start)"
                ),
                {
                    "tenant": w.t.tenant_id,
                    "binding": binding_id,
                    "fingerprint": fingerprint_device_secret(secret),
                    "start": active,
                },
            )
        # Point de l'ancien camion reçu avec les identifiants du nouveau.
        assert not ingest(1, active - timedelta(minutes=1))
        assert state() == (0, None)
        first_time = now - timedelta(minutes=5)
        assert not ingest(1, first_time, credential="x" * 44)
        assert not ingest(1, first_time, tenant=outsider.tenant_id)
        assert not ingest(1, first_time, tenant=outsider.tenant_id, context_tenant=w.t.tenant_id)
        assert not ingest(1, now + timedelta(minutes=3))
        assert state() == (0, None)
        assert ingest(1, first_time)
        assert state() == (1, 1)
        assert not ingest(1, first_time)
        # Un timestamp déjà stocké annule aussi l'avance de séquence 2.
        assert not ingest(2, first_time)
        assert state() == (1, 1)
        assert ingest(2, now - timedelta(minutes=3))
        assert state() == (2, 2)
        # La transaction externe reste responsable de la durabilité.
        third_time = now - timedelta(minutes=2)
        assert ingest(3, third_time, commit=False)
        assert state() == (2, 2)
        assert ingest(3, third_time)
        assert state() == (3, 3)
        positions = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers)
        assert positions.status_code == 200, positions.text
        point = next(item for item in positions.json() if item["vehicle_id"] == vehicle)
        assert point["site_id"] == str(w.t.sites["S1"])
        assert all(item["vehicle_id"] != old_vehicle for item in positions.json())
        foreign = client.get(f"{API}/vehicles/gps/latest", headers=other_ops.headers)
        assert foreign.status_code == 200, foreign.text
        assert foreign.json() == []
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "UPDATE fleet_gps_device_credential SET revoked_at = :at "
                    "WHERE gps_device_binding_id = :binding"
                ),
                {"at": now, "binding": binding_id},
            )
        assert not ingest(4, now - timedelta(minutes=1))
        assert state() == (3, 3)
    finally:
        engine.dispose()
