"""Survey tolerance qualification service and schema integration checks."""

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
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    load_qualified_tolerance,
    propose_tolerance_qualification,
    retire_tolerance_qualification,
)
from tests.conftest import Api


def _manager_scope(tenant, site):
    principal = Principal(
        tenant.admin.user_id,
        tenant.tenant_id,
        "CUSTOMER",
        uuid4(),
        (Grant("OPS_MANAGER", "SITE", site),),
    )
    scope = evaluate(principal, "dispatch.location.manage")
    assert scope is not None
    return principal, scope


def _propose(auth, site, *, responsible=None, tolerance=2.0, **overrides):
    kwargs = dict(
        site_id=site,
        tolerance_m=tolerance,
        survey_source="Topographic campaign 2026-11",
        measurement_method="GNSS RTK",
        instrument_precision_m=0.05,
        surveyed_on=date.today() - timedelta(days=1),
        referential_version="topo-ref-v3",
        justification="Perimeter survey of the haul road network",
        responsible_user_id=responsible or auth.user_id,
    )
    kwargs.update(overrides)
    return propose_tolerance_qualification(auth, **kwargs)


def test_qualification_lifecycle_and_audit(api: Api) -> None:
    tenant = api.tenant()
    site = tenant.sites["S1"]
    approver = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        principal, admin_scope = _manager_scope(tenant, site)
        auth = Authorized(principal, admin_scope, db, SystemClock())
        approver_auth = Authorized(
            replace(principal, user_id=approver.user_id),
            _manager_scope(tenant, site)[1],
            db,
            SystemClock(),
        )

        def propose(subject=auth, requested_site=site, **overrides):
            return _propose(subject, requested_site, **overrides)

        dispatcher = replace(principal, grants=(Grant("DISPATCHER", "SITE", site),))
        with pytest.raises(AppError) as error:
            propose(replace(auth, principal=dispatcher))
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            propose(requested_site=tenant.sites["S2"])
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            propose(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        with pytest.raises(AppError) as error:
            propose(survey_source=" ")
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(measurement_method="x" * 101)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(justification="y" * 501)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(referential_version="")
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(surveyed_on=date.today() + timedelta(days=1))
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(tolerance=-0.5)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            propose(instrument_precision_m=-1)
        assert error.value.code == "VALIDATION_ERROR"
        other = api.tenant()
        with pytest.raises(AppError) as error:
            propose(responsible=other.admin.user_id)
        assert error.value.code == "NOT_FOUND"
        proposed = propose()
        assert (
            db.execute(
                text("SELECT count(*) FROM mining_tolerance_qualification WHERE status = 'PROPOSED'")
            ).scalar_one()
            == 1
        )

        def approve(subject=approver_auth, requested_site=site, qualification=None):
            return approve_tolerance_qualification(
                subject, site_id=requested_site, qualification_id=qualification or proposed
            )

        with pytest.raises(AppError) as error:
            approve(subject=auth)
        assert error.value.code == "SELF_APPROVAL_FORBIDDEN"
        with pytest.raises(AppError) as error:
            approve(qualification=uuid4())
        assert error.value.code == "NOT_FOUND"
        with pytest.raises(AppError) as error:
            approve(requested_site=tenant.sites["S2"])
        assert error.value.code == "PERMISSION_DENIED"
        approved = approve()
        assert approved == proposed
        with pytest.raises(AppError) as error:
            approve()
        assert error.value.code == "CONFLICT"
        audit = text("SELECT count(*) FROM audit_event WHERE entity_id = :id AND action = :action")
        assert (
            db.execute(
                audit, {"id": proposed, "action": "mining_tolerance_qualification.propose"}
            ).scalar_one()
            == 1
        )
        assert (
            db.execute(
                audit, {"id": proposed, "action": "mining_tolerance_qualification.approve"}
            ).scalar_one()
            == 1
        )
        qualified = load_qualified_tolerance(approver_auth, site_id=site, qualification_id=approved)
        assert qualified.tolerance_m == 2.0
        assert qualified.qualification_id == approved
        with pytest.raises(AppError) as error:
            load_qualified_tolerance(approver_auth, site_id=site, qualification_id=uuid4())
        assert error.value.code == "NOT_FOUND"
        assert (
            retire_tolerance_qualification(approver_auth, site_id=site, qualification_id=approved) == approved
        )
        with pytest.raises(AppError) as error:
            load_qualified_tolerance(approver_auth, site_id=site, qualification_id=approved)
        assert error.value.code == "CONFLICT"
        with pytest.raises(AppError) as error:
            retire_tolerance_qualification(approver_auth, site_id=site, qualification_id=approved)
        assert error.value.code == "CONFLICT"
        with pytest.raises(AppError) as error:
            retire_tolerance_qualification(approver_auth, site_id=site, qualification_id=uuid4())
        assert error.value.code == "NOT_FOUND"
        assert (
            db.execute(
                audit, {"id": approved, "action": "mining_tolerance_qualification.retire"}
            ).scalar_one()
            == 1
        )
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(text("SELECT count(*) FROM mining_tolerance_qualification")).scalar_one() == 0
        assert (
            db.execute(
                audit, {"id": proposed, "action": "mining_tolerance_qualification.propose"}
            ).scalar_one()
            == 0
        )


def test_qualification_tenant_isolation(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    site = tenant.sites["S1"]
    approver = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        principal, admin_scope = _manager_scope(tenant, site)
        auth = Authorized(principal, admin_scope, db, SystemClock())
        approver_auth = Authorized(
            replace(principal, user_id=approver.user_id),
            _manager_scope(tenant, site)[1],
            db,
            SystemClock(),
        )
        proposed = _propose(auth, site)
        approve_tolerance_qualification(approver_auth, site_id=site, qualification_id=proposed)
        foreign = replace(
            principal,
            tenant_id=other.tenant_id,
            user_id=other.admin.user_id,
            grants=(Grant("OPS_MANAGER", "SITE", other.sites["S1"]),),
        )
        foreign_auth = Authorized(foreign, _manager_scope(other, other.sites["S1"])[1], db, SystemClock())
        with pytest.raises(AppError) as error:
            load_qualified_tolerance(foreign_auth, site_id=other.sites["S1"], qualification_id=proposed)
        assert error.value.code == "NOT_FOUND"
        with pytest.raises(AppError) as error:
            retire_tolerance_qualification(foreign_auth, site_id=other.sites["S1"], qualification_id=proposed)
        assert error.value.code == "NOT_FOUND"
        db.commit()


def test_qualification_schema_guards(api: Api) -> None:
    """Triggers: immutable survey fields, approval separation, report binding."""
    tenant = api.tenant()
    site = tenant.sites["S1"]
    approver = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        principal, admin_scope = _manager_scope(tenant, site)
        auth = Authorized(principal, admin_scope, db, SystemClock())
        approver_auth = Authorized(
            replace(principal, user_id=approver.user_id),
            _manager_scope(tenant, site)[1],
            db,
            SystemClock(),
        )
        qualification = _propose(auth, site)
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(Exception) as error:
            db.execute(
                text("UPDATE mining_tolerance_qualification SET tolerance_m = 5 WHERE qualification_id = :q"),
                {"q": qualification},
            )
        assert "immutable" in str(error.value)
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(Exception) as error:
            db.execute(
                text(
                    "UPDATE mining_tolerance_qualification SET status = 'APPROVED' "
                    "WHERE qualification_id = :q"
                ),
                {"q": qualification},
            )
        assert "independent approver" in str(error.value)
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert (
            approve_tolerance_qualification(approver_auth, site_id=site, qualification_id=qualification)
            == qualification
        )
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        revision = db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic') RETURNING revision_id"
            ),
            {"t": tenant.tenant_id, "s": site, "r": uuid4()},
        ).scalar_one()
        with pytest.raises(Exception) as error:
            db.execute(
                text(
                    "INSERT INTO mining_readiness_report (tenant_id, site_id, revision_id, "
                    "digest_version, evidence_digest, tolerance_m, findings, actor_user_id, "
                    "tolerance_qualification_id) VALUES (:t, :s, :r, 'mining-readiness-v1', "
                    ":digest, 3, '[]', :actor, :q)"
                ),
                {
                    "t": tenant.tenant_id,
                    "s": site,
                    "r": revision,
                    "digest": "b" * 64,
                    "actor": tenant.admin.user_id,
                    "q": qualification,
                },
            )
        assert "not qualified" in str(error.value)
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        revision = db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic') RETURNING revision_id"
            ),
            {"t": tenant.tenant_id, "s": site, "r": uuid4()},
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO mining_readiness_report (tenant_id, site_id, revision_id, "
                "digest_version, evidence_digest, tolerance_m, findings, actor_user_id) "
                "VALUES (:t, :s, :r, 'mining-readiness-v1', :digest, 2, '[]', :actor)"
            ),
            {
                "t": tenant.tenant_id,
                "s": site,
                "r": revision,
                "digest": "c" * 64,
                "actor": tenant.admin.user_id,
            },
        )
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert (
            db.execute(
                text("SELECT count(*) FROM mining_readiness_report WHERE tolerance_qualification_id IS NULL")
            ).scalar_one()
            == 1
        )
        db.rollback()
