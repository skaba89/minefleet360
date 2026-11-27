from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_readiness_report import capture_draft_report
from tests.conftest import Api


def test_capture_report_concurrency_audit_and_isolation(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    site = tenant.sites["S1"]
    revision = uuid4()
    principal = Principal(
        tenant.admin.user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("OPS_MANAGER", "SITE", site),)
    )
    scope = evaluate(principal, "dispatch.location.manage")
    assert scope is not None
    params = {"t": tenant.tenant_id, "s": site, "r": revision}
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic survey')"
            ),
            params,
        )
        db.commit()

    barrier = Barrier(2)

    def inspect():
        with new_session() as db:
            set_tenant_context(db, tenant.tenant_id)
            auth = Authorized(principal, scope, db, SystemClock())
            barrier.wait(timeout=10)
            result = capture_draft_report(auth, site_id=site, revision_id=revision, tolerance_m=1)
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(inspect) for _ in range(2)]
        first, repeated = [f.result(timeout=20) for f in futures]
    assert first == repeated

    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        auth = Authorized(principal, scope, db, SystemClock())
        select_report = text(
            "SELECT evidence, findings, inspected_by, tolerance_m, inspected_at, "
            "validator_version FROM mining_draft_inspection_report WHERE report_id = :id"
        )
        original = db.execute(select_report, {"id": first}).one()
        assert original.evidence == []
        assert original.findings == [{"code": "EMPTY_GRAPH", "segment_id": None}]
        assert (original.inspected_by, original.tolerance_m, original.validator_version) == (
            auth.user_id,
            1,
            1,
        )
        assert original.inspected_at.tzinfo is not None
        count_audit = text(
            "SELECT count(*) FROM audit_event WHERE entity_id = :id AND "
            "action = 'dispatch.draft.inspect' AND actor_user_id = :actor AND site_id = :site"
        )
        assert db.execute(count_audit, {"id": first, "actor": auth.user_id, "site": site}).scalar_one() == 1

        for subject, target in (
            (principal, tenant.sites["S2"]),
            (replace(principal, grants=(Grant("DISPATCHER", "SITE", site),)), site),
        ):
            with pytest.raises(AppError) as denied:
                capture_draft_report(
                    replace(auth, principal=subject), site_id=target, revision_id=revision, tolerance_m=1
                )
            assert denied.value.code == "PERMISSION_DENIED"

        node = db.execute(
            text(
                "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, position, "
                "provenance) VALUES (:t, :s, :r, ST_SetSRID(ST_Point(1,1),4326), 'Survey') "
                "RETURNING node_id"
            ),
            params,
        ).scalar_one()
        second = capture_draft_report(auth, site_id=site, revision_id=revision, tolerance_m=1)
        assert second != first
        revised = db.execute(select_report, {"id": second}).one()
        assert [item["node_id"] for item in revised.evidence] == [str(node)]
        assert {item["code"] for item in revised.findings} == {"ISOLATED_NODE", "EMPTY_GRAPH"}
        assert db.execute(select_report, {"id": first}).one() == original
        assert (
            db.execute(
                text(
                    "SELECT has_table_privilege(current_user, 'mining_draft_inspection_report', "
                    "'UPDATE') OR has_table_privilege(current_user, "
                    "'mining_draft_inspection_report', 'DELETE')"
                )
            ).scalar_one()
            is False
        )
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        third = capture_draft_report(auth, site_id=site, revision_id=revision, tolerance_m=2)
        assert third not in (first, second)
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(select_report, {"id": third}).first() is None
        assert db.execute(count_audit, {"id": third, "actor": auth.user_id, "site": site}).scalar_one() == 0
        set_tenant_context(db, other.tenant_id)
        assert db.execute(select_report, {"id": first}).first() is None
