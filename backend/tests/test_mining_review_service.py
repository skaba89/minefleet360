"""Integration checks for historical rejection and transactional audit."""

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
from app.dispatch.mining_review_read import load_review_history
from app.dispatch.mining_review_service import reject_readiness_report
from tests.conftest import Api


def test_rejection_and_audit(api: Api) -> None:
    tenant = api.tenant()
    reviewer = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
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
        report = db.execute(
            text(
                "INSERT INTO mining_readiness_report "
                "(tenant_id, site_id, revision_id, actor_user_id, digest_version, "
                "evidence_digest, tolerance_m, findings) "
                "VALUES (:t, :s, :r, :author, 'mining-readiness-v1', :digest, 2, '[]') "
                "RETURNING report_id"
            ),
            {
                "t": tenant.tenant_id,
                "s": site,
                "r": revision,
                "author": tenant.admin.user_id,
                "digest": "a" * 64,
            },
        ).scalar_one()
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        principal = Principal(
            reviewer.user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("OPS_MANAGER", "SITE", site),)
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())

        def reject(subject=auth, reason="Survey incomplete"):
            return reject_readiness_report(
                subject,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason=reason,
            )

        with pytest.raises(AppError) as error:
            reject(reason=" ")
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            reject(replace(auth, principal=replace(principal, user_id=tenant.admin.user_id)))
        assert error.value.code == "SELF_APPROVAL_FORBIDDEN"
        dispatcher = replace(principal, grants=(Grant("DISPATCHER", "SITE", site),))
        with pytest.raises(AppError) as error:
            reject(replace(auth, principal=dispatcher))
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            reject(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        audit = text(
            "SELECT count(*) FROM audit_event WHERE action = 'mining_review_decision.reject' "
            "AND entity_id = :id"
        )
        decision = reject()
        history = load_review_history(auth, site_id=site, revision_id=revision, report_id=report)
        assert history.decisions[0].decision == "REJECTED"
        assert history.decisions[0].reason == "Survey incomplete"
        assert db.execute(audit, {"id": decision}).scalar_one() == 1
        with pytest.raises(AppError) as error:
            reject()
        assert error.value.code == "CONFLICT"
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert load_review_history(auth, site_id=site, revision_id=revision, report_id=report).decisions == ()
        assert db.execute(audit, {"id": decision}).scalar_one() == 0
        committed = reject()
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(audit, {"id": committed}).scalar_one() == 1
