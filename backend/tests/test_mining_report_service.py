"""Historical technical report service integration checks."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_readiness import ReadinessFinding
from app.dispatch.mining_report_service import record_draft_readiness
from tests.conftest import Api


def test_record_draft_report(api: Api) -> None:
    tenant = api.tenant()
    site = tenant.sites["S1"]
    revision = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic')"
            ),
            {"t": tenant.tenant_id, "s": site, "r": revision},
        )
        principal = Principal(
            tenant.admin.user_id,
            tenant.tenant_id,
            "CUSTOMER",
            uuid4(),
            (Grant("OPS_MANAGER", "SITE", site),),
        )
        scope = evaluate(principal, "dispatch.location.manage")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())

        def save(subject=auth, requested_site=site):
            return record_draft_readiness(
                subject, site_id=requested_site, revision_id=revision, tolerance_m=2
            )

        dispatcher = replace(principal, grants=(Grant("DISPATCHER", "SITE", site),))
        with pytest.raises(AppError) as error:
            save(replace(auth, principal=dispatcher))
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            save(requested_site=tenant.sites["S2"])
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            save(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 0
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        result = save()
        assert result.evidence.findings == (ReadinessFinding("EMPTY_GRAPH"),)
        report = db.execute(
            text(
                "SELECT evidence_digest, findings, actor_user_id FROM mining_readiness_report "
                "WHERE report_id = :report"
            ),
            {"report": result.report_id},
        ).one()
        assert report.evidence_digest == result.evidence.digest
        assert report.findings == [{"code": "EMPTY_GRAPH", "segment_id": None}]
        assert report.actor_user_id == tenant.admin.user_id
        audit = text(
            "SELECT count(*) FROM audit_event WHERE action = 'mining_readiness_report.create' "
            "AND entity_id = :report"
        )
        assert db.execute(audit, {"report": result.report_id}).scalar_one() == 1
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 0
        assert db.execute(audit, {"report": result.report_id}).scalar_one() == 0
        committed = save()
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 1
        assert db.execute(audit, {"report": committed.report_id}).scalar_one() == 1
