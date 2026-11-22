"""Recette PostgreSQL du service interne de rattrapage GPS."""

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.authz.dependencies import Authorized, authenticate
from app.authz.principal import evaluate
from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.core.tenancy import set_tenant_context
from app.fleet.gps_deferred_contract import DeferredPhoneBatch, DeferredPhonePoint
from app.fleet.gps_deferred_service import ingest_deferred
from app.fleet.gps_models import FleetGpsPosition
from app.fleet.gps_phone_models import FleetGpsPhoneShare
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_deferred_transaction(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    response = client.post(
        f"{API}/me/gps/shares",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "consent": True},
    )
    assert response.status_code == 201, response.text
    share_id = uuid.UUID(response.json()["phone_share_id"])
    start = datetime.fromisoformat(response.json()["started_at"])
    clock = FrozenClock(start + timedelta(seconds=60))
    settings = get_settings()
    engine = create_engine(settings.database_url())
    try:
        with Session(engine) as db:
            principal = authenticate(db, clock, settings, w.ops.headers["Authorization"])
            scope = evaluate(principal, "fleet.gps.share")
            assert scope is not None
            auth = Authorized(principal, scope, db, clock)

            def point(seconds: int) -> DeferredPhonePoint:
                return DeferredPhonePoint(
                    client_point_id=uuid.uuid4(),
                    latitude=9.5,
                    longitude=-13.7,
                    accuracy_m=10,
                    recorded_at=start + timedelta(seconds=seconds),
                )

            first, last, collision = point(10), point(30), point(31)
            batch = DeferredPhoneBatch(points=[last, first, collision])
            assert ingest_deferred(auth, share_id, batch) == {
                last.client_point_id: "accepted",
                first.client_point_id: "accepted",
                collision.client_point_id: "rejected",
            }
            set_tenant_context(db, auth.tenant_id)
            changed = first.model_copy(update={"latitude": 9.6})
            historical = point(20)
            batch = DeferredPhoneBatch(points=[last, changed, historical])
            assert ingest_deferred(auth, share_id, batch) == {
                last.client_point_id: "duplicate",
                first.client_point_id: "conflict",
                historical.client_point_id: "accepted",
            }
            set_tenant_context(db, auth.tenant_id)
            share = db.get(FleetGpsPhoneShare, share_id)
            assert share is not None
            assert share.last_recorded_at == last.recorded_at
            rows = db.scalars(
                select(FleetGpsPosition).where(
                    FleetGpsPosition.tenant_id == auth.tenant_id,
                    FleetGpsPosition.phone_share_id == share_id,
                )
            ).all()
            assert len(rows) == 3
            assert {row.client_point_id for row in rows} == {
                first.client_point_id,
                last.client_point_id,
                historical.client_point_id,
            }
    finally:
        engine.dispose()
