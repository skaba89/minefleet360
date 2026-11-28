"""Integration checks for historical rejection and transactional audit."""

from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_report_service import record_draft_readiness
from app.dispatch.mining_review_read import load_review_history
from app.dispatch.mining_review_service import reject_readiness_report
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    propose_tolerance_qualification,
)
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
        author_principal = Principal(
            tenant.admin.user_id,
            tenant.tenant_id,
            "CUSTOMER",
            uuid4(),
            (Grant("OPS_MANAGER", "SITE", site),),
        )
        author_scope = evaluate(author_principal, "dispatch.location.manage")
        assert author_scope is not None
        author_auth = Authorized(author_principal, author_scope, db, SystemClock())
        reviewer_scope = evaluate(
            replace(author_principal, user_id=reviewer.user_id), "dispatch.location.manage"
        )
        assert reviewer_scope is not None
        reviewer_auth = Authorized(
            replace(author_principal, user_id=reviewer.user_id), reviewer_scope, db, SystemClock()
        )
        qualification = propose_tolerance_qualification(
            author_auth,
            site_id=site,
            tolerance_m=2.0,
            survey_source="Topographic campaign 2026-11",
            measurement_method="GNSS RTK",
            instrument_precision_m=0.05,
            surveyed_on=date.today() - timedelta(days=1),
            referential_version="topo-ref-v3",
            justification="Perimeter survey of the haul road network",
            responsible_user_id=author_auth.user_id,
        )
        assert (
            approve_tolerance_qualification(reviewer_auth, site_id=site, qualification_id=qualification)
            == qualification
        )
        report = record_draft_readiness(
            author_auth,
            site_id=site,
            revision_id=revision,
            tolerance_m=2.0,
            tolerance_qualification_id=qualification,
        ).report_id
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
