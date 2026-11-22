"""Concurrence et refus du rejeu GPS différé, sur PostgreSQL réel."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.authz.dependencies import Authorized, authenticate
from app.authz.principal import evaluate
from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.fleet.gps_deferred_contract import DeferredPhoneBatch, DeferredPhonePoint
from app.fleet.gps_deferred_service import PointStatus, ingest_deferred
from app.fleet.gps_models import FleetGpsPosition
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def _start(client: TestClient, world: World) -> tuple[uuid.UUID, datetime]:
    vehicle = _vehicle(client, world)
    response = client.post(
        f"{API}/me/gps/shares",
        headers=world.ops.headers,
        json={"vehicle_id": vehicle, "consent": True},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return uuid.UUID(data["phone_share_id"]), datetime.fromisoformat(data["started_at"])


def _batch(start: datetime) -> DeferredPhoneBatch:
    return DeferredPhoneBatch(
        points=[
            DeferredPhonePoint(
                client_point_id=uuid.uuid4(),
                latitude=9.5,
                longitude=-13.7,
                accuracy_m=10,
                recorded_at=start + timedelta(seconds=10),
            )
        ]
    )


def _auth(db: Session, clock: FrozenClock, headers: dict[str, str]) -> Authorized:
    principal = authenticate(db, clock, get_settings(), headers["Authorization"])
    scope = evaluate(principal, "fleet.gps.share")
    assert scope is not None
    return Authorized(principal, scope, db, clock)


def _count(db: Session, tenant_id: uuid.UUID, share_id: uuid.UUID) -> int:
    set_tenant_context(db, tenant_id)
    stmt = select(func.count()).select_from(FleetGpsPosition).where(
        FleetGpsPosition.tenant_id == tenant_id,
        FleetGpsPosition.phone_share_id == share_id,
    )
    return int(db.execute(stmt).scalar_one())


def test_concurrent_replay(client: TestClient, w: World) -> None:  # noqa: F811
    share_id, start = _start(client, w)
    batch = _batch(start)
    barrier = Barrier(2)
    engine = create_engine(get_settings().database_url(), pool_size=2, max_overflow=0)

    def worker() -> PointStatus:
        with Session(engine) as db:
            clock = FrozenClock(start + timedelta(seconds=60))
            auth = _auth(db, clock, w.ops.headers)
            db.execute(text("SET LOCAL statement_timeout = '15s'"))
            barrier.wait(timeout=15)
            return ingest_deferred(auth, share_id, batch)[batch.points[0].client_point_id]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(worker)
            second = executor.submit(worker)
            assert sorted([first.result(timeout=30), second.result(timeout=30)]) == ["accepted", "duplicate"]
        with Session(engine) as db:
            assert _count(db, w.t.tenant_id, share_id) == 1
    finally:
        engine.dispose()


def test_stopped_expired_or_other_session(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    share_id, start = _start(client, w)
    batch = _batch(start)
    clock = FrozenClock(start + timedelta(seconds=60))
    engine = create_engine(get_settings().database_url())
    try:
        # Un autre tenant ne peut pas découvrir un partage même avec la permission GPS.
        other = api.tenant()
        with Session(engine) as db:
            auth = _auth(db, clock, other.admin.headers)
            with pytest.raises(AppError, match="NOT_FOUND"):
                ingest_deferred(auth, share_id, batch)
            db.rollback()
            assert _count(db, other.tenant_id, share_id) == 0

        # Une deuxième session du même compte ne peut pas reprendre l'ancien partage.
        other_headers = api.login(w.t.code, w.ops.email)
        with Session(engine) as db:
            auth = _auth(db, clock, other_headers)
            with pytest.raises(AppError, match="NOT_FOUND"):
                ingest_deferred(auth, share_id, batch)
            db.rollback()
            assert _count(db, w.t.tenant_id, share_id) == 0

        # Simule le franchissement de l'expiration après authentification.
        with Session(engine) as db:
            auth = _auth(db, clock, w.ops.headers)
            clock.set(start + timedelta(hours=12))
            with pytest.raises(AppError, match="CONFLICT"):
                ingest_deferred(auth, share_id, batch)
            db.rollback()
            assert _count(db, w.t.tenant_id, share_id) == 0

        response = client.post(f"{API}/me/gps/shares/{share_id}/stop", headers=w.ops.headers)
        assert response.status_code == 204, response.text
        clock.set(start + timedelta(seconds=60))
        with Session(engine) as db:
            auth = _auth(db, clock, w.ops.headers)
            with pytest.raises(AppError, match="CONFLICT"):
                ingest_deferred(auth, share_id, batch)
            db.rollback()
            assert _count(db, w.t.tenant_id, share_id) == 0
    finally:
        engine.dispose()
