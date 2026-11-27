from dataclasses import replace
from unittest.mock import patch
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
from app.dispatch.mining_readiness_snapshot import inspect_draft_evidence, inspect_draft_readiness
from tests.conftest import Api


def test_readiness_snapshot_scope_and_limits(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    site = tenant.sites["S1"]
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        params = {"t": tenant.tenant_id, "s": site, "r": uuid4()}
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Survey fixture')"
            ),
            params,
        )
        principal = Principal(
            tenant.admin.user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("DISPATCHER", "SITE", site),)
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())

        def inspect(subject=auth, requested_site=site, tolerance=1.0):
            return inspect_draft_readiness(
                subject, site_id=requested_site, revision_id=params["r"], tolerance_m=tolerance
            )

        with patch.object(db, "execute", wraps=db.execute) as execute:
            assert inspect() == (ReadinessFinding("EMPTY_GRAPH"),)
            assert execute.call_count == 1
            for value in (-1.0, float("nan"), float("inf")):
                with pytest.raises(ValueError):
                    inspect(tolerance=value)
            with pytest.raises(AppError) as failure:
                inspect(requested_site=tenant.sites["S2"])
            assert failure.value.code == "PERMISSION_DENIED"
            with pytest.raises(AppError) as failure:
                inspect(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
            assert failure.value.code == "MFA_ENROLLMENT_REQUIRED"
            assert execute.call_count == 1

        insert_nodes = text(
            "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, position, provenance) "
            "SELECT :t, :s, :r, ST_SetSRID(ST_Point(1, 1), 4326), 'Survey fixture' "
            "FROM generate_series(1, :count)"
        )
        db.execute(insert_nodes, {**params, "count": 1000})
        assert set(inspect()) == {ReadinessFinding("EMPTY_GRAPH"), ReadinessFinding("ISOLATED_NODE")}
        db.execute(insert_nodes, {**params, "count": 1})
        with pytest.raises(AppError) as failure:
            inspect()
        assert failure.value.code == "CONFLICT"
        db.commit()

        for subject, requested_site in ((tenant, tenant.sites["S2"]), (other, other.sites["S1"])):
            set_tenant_context(db, subject.tenant_id)
            permitted = replace(
                principal,
                tenant_id=subject.tenant_id,
                user_id=subject.admin.user_id,
                grants=(Grant("DISPATCHER", "SITE", requested_site),),
            )
            with pytest.raises(AppError) as failure:
                inspect(replace(auth, principal=permitted), requested_site=requested_site)
            assert failure.value.code == "NOT_FOUND"


def test_readiness_complete_evidence_and_missing_category(api: Api) -> None:
    tenant = api.tenant()
    site = tenant.sites["S1"]
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        params = {"t": tenant.tenant_id, "s": site, "r": uuid4()}
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic survey')"
            ),
            params,
        )
        for key, longitude in (("a", -13.5), ("b", -13.499)):
            params[key] = uuid4()
            db.execute(
                text(
                    "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, node_id, "
                    "position, provenance) VALUES (:t, :s, :r, :node, "
                    "ST_SetSRID(ST_Point(:lon, 9.5), 4326), 'Synthetic survey')"
                ),
                {**params, "node": params[key], "lon": longitude},
            )
        params["segment"] = uuid4()
        db.execute(
            text(
                "INSERT INTO mining_route_segment (tenant_id, site_id, revision_id, segment_id, "
                "origin_id, destination_id, path, distance_m, duration_seconds, provenance) "
                "SELECT :t, :s, :r, :segment, a.node_id, b.node_id, ST_MakeLine(a.position,b.position), "
                "110, 20, 'Synthetic survey' FROM mining_route_node a, mining_route_node b "
                "WHERE a.node_id = :a AND b.node_id = :b"
            ),
            params,
        )
        principal = Principal(
            tenant.admin.user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("DISPATCHER", "SITE", site),)
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())

        def inspect(tolerance: float = 2.0):
            return inspect_draft_readiness(auth, site_id=site, revision_id=params["r"], tolerance_m=tolerance)

        def evidence(tolerance: float = 2.0):
            return inspect_draft_evidence(auth, site_id=site, revision_id=params["r"], tolerance_m=tolerance)

        initial = evidence()
        assert initial.digest_version == "mining-readiness-v1"
        assert len(initial.digest) == 64
        assert initial == evidence()
        assert inspect() == (ReadinessFinding("MISSING_RESTRICTION", params["segment"]),)
        db.execute(
            text(
                "INSERT INTO mining_road_restriction "
                "(tenant_id, site_id, revision_id, segment_id, max_gross_mass_kg, max_speed_kmh, "
                "max_height_mm, max_width_mm, max_length_mm, uphill_permille, downhill_permille, provenance) "
                "VALUES (:t, :s, :r, :segment, 40000, 30, 4500, 3500, 13000, 80, 60, 'Synthetic survey')"
            ),
            params,
        )
        incomplete = evidence()
        assert incomplete.digest != initial.digest
        assert inspect() == (ReadinessFinding("INCOMPLETE_RESTRICTION", params["segment"]),)
        category = db.execute(
            text(
                "SELECT vehicle_category_id FROM vehicle_category WHERE tenant_id = :t AND is_active "
                "ORDER BY vehicle_category_id LIMIT 1"
            ),
            params,
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO mining_road_allowed_category "
                "(tenant_id, site_id, revision_id, segment_id, vehicle_category_id) "
                "VALUES (:t, :s, :r, :segment, :category)"
            ),
            {**params, "category": category},
        )
        complete = evidence()
        assert complete.digest != incomplete.digest
        assert complete == evidence()
        assert complete.findings == ()
        assert evidence(3.0).digest != complete.digest
        assert inspect() == ()
        assert inspect(0.0) == (ReadinessFinding("MISSING_OR_FAILED_LENGTH_CHECK", params["segment"]),)
