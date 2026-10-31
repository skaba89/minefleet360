import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.core.db import new_session
from app.core.errors import AppError
from app.core.idempotency import IdempotencyRecord, claim, complete
from app.core.tenancy import set_tenant_context
from tests.conftest import Api


def _claim_and_complete(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    key: str,
    resource_id: uuid.UUID,
    now: datetime,
) -> str:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        owned = claim(
            db,
            tenant_id=tenant_id,
            user_account_id=user_id,
            key=key,
            method="POST",
            path="/offline/test-events",
            body=b'{"value":42}',
            now=now,
        )
        if owned.is_replay:
            assert owned.replay is not None and owned.replay.resource_id == resource_id
            db.rollback()
            return "replay"
        time.sleep(0.15)
        complete(
            db,
            owned,
            response_status=201,
            resource_type="test_event",
            resource_id=resource_id,
            completed_at=now,
        )
        db.commit()
        return "owner"
    finally:
        db.close()


def test_claim_replays_same_request_and_rejects_different_content(api: Api) -> None:
    tenant = api.tenant(sites=())
    key = str(uuid.uuid4())
    resource_id = uuid.uuid4()
    now = api.client.app.state.clock.now()  # type: ignore[attr-defined]

    assert _claim_and_complete(tenant.tenant_id, tenant.admin.user_id, key, resource_id, now) == "owner"
    assert _claim_and_complete(tenant.tenant_id, tenant.admin.user_id, key, resource_id, now) == "replay"

    db = new_session()
    try:
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(AppError) as caught:
            claim(
                db,
                tenant_id=tenant.tenant_id,
                user_account_id=tenant.admin.user_id,
                key=key,
                method="POST",
                path="/offline/test-events",
                body=b'{"value":43}',
                now=now,
            )
        assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"
    finally:
        db.rollback()
        db.close()


def test_same_key_is_isolated_by_tenant_and_user(api: Api) -> None:
    first, second = api.tenant(sites=()), api.tenant(sites=())
    colleague = api.user(first, "OPS_MANAGER")
    key = str(uuid.uuid4())
    now = api.client.app.state.clock.now()  # type: ignore[attr-defined]

    for tenant_id, user_id in (
        (first.tenant_id, first.admin.user_id),
        (first.tenant_id, colleague.user_id),
        (second.tenant_id, second.admin.user_id),
    ):
        assert _claim_and_complete(tenant_id, user_id, key, uuid.uuid4(), now) == "owner"

    db = new_session()
    try:
        set_tenant_context(db, first.tenant_id)
        assert (
            db.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.idempotency_key == key)
            )
            == 2
        )
        db.rollback()
        set_tenant_context(db, second.tenant_id)
        assert (
            db.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.idempotency_key == key)
            )
            == 1
        )
    finally:
        db.rollback()
        db.close()


def test_concurrent_claim_has_exactly_one_owner(api: Api) -> None:
    tenant = api.tenant(sites=())
    key = str(uuid.uuid4())
    resource_id = uuid.uuid4()
    now = api.client.app.state.clock.now()  # type: ignore[attr-defined]
    barrier = Barrier(2)

    def run() -> str:
        barrier.wait()
        return _claim_and_complete(tenant.tenant_id, tenant.admin.user_id, key, resource_id, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(run), pool.submit(run))]

    assert sorted(results) == ["owner", "replay"]
    db = new_session()
    try:
        set_tenant_context(db, tenant.tenant_id)
        total = db.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_account_id == tenant.admin.user_id,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        assert total == 1
    finally:
        db.rollback()
        db.close()


def test_active_record_cannot_be_deleted_but_expired_record_can(api: Api) -> None:
    tenant = api.tenant(sites=())
    now = api.client.app.state.clock.now()  # type: ignore[attr-defined]
    db = new_session()
    try:
        set_tenant_context(db, tenant.tenant_id)
        active = claim(
            db,
            tenant_id=tenant.tenant_id,
            user_account_id=tenant.admin.user_id,
            key=str(uuid.uuid4()),
            method="POST",
            path="/offline/test-events",
            body=b"{}",
            now=now,
        )
        complete(
            db,
            active,
            response_status=201,
            resource_type="test_event",
            resource_id=uuid.uuid4(),
            completed_at=now,
        )
        expired = IdempotencyRecord(
            tenant_id=tenant.tenant_id,
            user_account_id=tenant.admin.user_id,
            idempotency_key=str(uuid.uuid4()),
            request_method="POST",
            request_path="/offline/test-events",
            request_hash=b"x" * 32,
            state="IN_PROGRESS",
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
        db.add(expired)
        db.commit()

        set_tenant_context(db, tenant.tenant_id)
        assert db.query(IdempotencyRecord).filter_by(idempotency_key=active.key).delete() == 0
        assert db.query(IdempotencyRecord).filter_by(idempotency_key=expired.idempotency_key).delete() == 1
        db.rollback()
    finally:
        db.close()
