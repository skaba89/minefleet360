"""Matrix and service checks for the dedicated dispatch.readiness.* permissions.

The readiness stream used provisional location permissions (0089/0091) until
this audit-backed lot; these tests pin the real matrix declarations and the
cross-role denials that follow from them.
"""

from uuid import uuid4

import pytest

from app.authz.dependencies import Authorized
from app.authz.matrix import load_matrix
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_report_read import list_readiness_reports
from app.dispatch.mining_review_service import reject_readiness_report
from tests.conftest import Api
from tests.test_mining_review_concurrency import _prepare_review

READINESS_PERMISSIONS = (
    "dispatch.readiness.read",
    "dispatch.readiness.record",
    "dispatch.readiness.reject",
    "dispatch.readiness.approve",
)

EXPECTED_GRANTS = {
    "dispatch.readiness.read": {
        "TENANT_ADMIN": ("TENANT",),
        "DIRECTION": ("TENANT",),
        "OPS_MANAGER": ("TENANT", "SITE"),
        "DISPATCHER": ("SITE",),
        "WORKSHOP_CHIEF": ("TENANT", "SITE"),
        "HSE": ("TENANT", "SITE"),
        "FINANCE": ("TENANT", "SITE"),
        "AUDITOR": ("TENANT",),
    },
    "dispatch.readiness.record": {"OPS_MANAGER": ("TENANT", "SITE"), "DISPATCHER": ("SITE",)},
    "dispatch.readiness.reject": {"OPS_MANAGER": ("TENANT", "SITE"), "HSE": ("TENANT", "SITE")},
    "dispatch.readiness.approve": {"OPS_MANAGER": ("TENANT", "SITE"), "HSE": ("TENANT", "SITE")},
}


def test_matrix_declares_readiness_permissions() -> None:
    matrix = load_matrix()
    for name in READINESS_PERMISSIONS:
        spec = matrix.permissions[name]
        assert spec.site_bound is True
        assert dict(spec.grants) == EXPECTED_GRANTS[name]
        assert spec.routes == ()
        assert "PLATFORM_ADMIN" not in spec.grants


def test_readiness_evaluation_grid() -> None:
    cases = {
        "OPS_MANAGER": {"read", "record", "reject", "approve"},
        "DISPATCHER": {"read", "record"},
        "HSE": {"read", "reject", "approve"},
        "TENANT_ADMIN": {"read"},
        "DIRECTION": {"read"},
        "WORKSHOP_CHIEF": {"read"},
        "FINANCE": {"read"},
        "AUDITOR": {"read"},
        "DRIVER": set(),
        "MECHANIC": set(),
        "STOREKEEPER": set(),
        "FUEL_MANAGER": set(),
        "HR": set(),
    }
    kind = {"TENANT_ADMIN": "CUSTOMER", "DIRECTION": "CUSTOMER", "PLATFORM_ADMIN": "PLATFORM"}.get
    for role, expected in cases.items():
        # SITE-only roles (DISPATCHER, DRIVER) carry a SITE grant; a TENANT grant
        # is outside their allowed scopes and would never match.
        scope_type = "SITE" if role in {"DISPATCHER", "DRIVER"} else "TENANT"
        site = uuid4() if scope_type == "SITE" else None
        principal = Principal(
            uuid4(), uuid4(), kind(role, "CUSTOMER"), uuid4(), (Grant(role, scope_type, site),)
        )
        for name in READINESS_PERMISSIONS:
            scope = evaluate(principal, name)
            assert (scope is not None) == (name.split(".")[2] in expected), (role, name)


def test_dispatcher_reads_reports_but_cannot_reject(api: Api) -> None:
    tenant, site, revision, _, report = _prepare_review(api)
    dispatcher_id = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        dispatcher = Principal(
            dispatcher_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("DISPATCHER", "SITE", site),)
        )
        auth = Authorized(dispatcher, evaluate(dispatcher, "dispatch.readiness.read"), db, SystemClock())
        summaries, _ = list_readiness_reports(auth, site_id=site, revision_id=revision)
        assert any(item.report_id == report for item in summaries)
        with pytest.raises(AppError) as error:
            reject_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Le répartiteur ne rejette pas",
            )
        assert error.value.code == "PERMISSION_DENIED"


def test_platform_principal_is_explicitly_denied(api: Api) -> None:
    tenant, site, revision, _reviewer_id, report = _prepare_review(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        platform = Principal(
            uuid4(), uuid4(), "PLATFORM", uuid4(), (Grant("PLATFORM_ADMIN", "PLATFORM", None),)
        )
        auth = Authorized(platform, evaluate(platform, "dispatch.readiness.reject"), db, SystemClock())
        with pytest.raises(AppError) as error:
            reject_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="La plateforme ne décide pas",
            )
        assert error.value.code == "PERMISSION_DENIED"


def test_stage_role_mismatch_is_denied(api: Api) -> None:
    tenant, site, revision, reviewer_id, report = _prepare_review(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        hse = Principal(reviewer_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("HSE", "SITE", site),))
        auth = Authorized(hse, evaluate(hse, "dispatch.readiness.reject"), db, SystemClock())
        with pytest.raises(AppError) as error:
            reject_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Le rôle HSE ne rejette pas sur l'étape technique",
            )
        assert error.value.code == "PERMISSION_DENIED"
