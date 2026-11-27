"""Exercise the real bounded preview query using PostgreSQL and PostGIS."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_geodesic import inspect_draft_lengths
from app.dispatch.mining_preview import preview_draft_route
from app.dispatch.mining_restrictions import VehicleProfile
from app.dispatch.mining_routes import MiningRoute
from tests.conftest import Api


def test_preview_postgis_and_isolation(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    site = first.sites["S1"]
    departure = datetime(2026, 11, 27, tzinfo=UTC)
    with new_session() as db:
        set_tenant_context(db, first.tenant_id)
        params = {"t": first.tenant_id, "site": site}
        revision = db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, version, provenance) "
                "VALUES (:t, :site, 1, 'Synthetic test') RETURNING revision_id"
            ),
            params,
        ).scalar_one()
        params["rev"] = revision
        nodes = []
        for wkt in ("POINT(-13.5 9.5)", "POINT(-13.499 9.5)", "POINT(-13.498 9.5)"):
            nodes.append(
                db.execute(
                    text(
                        "INSERT INTO mining_route_node "
                        "(tenant_id, site_id, revision_id, position, provenance) "
                        "VALUES (:t, :site, :rev, ST_GeomFromText(:wkt, 4326), 'Test') RETURNING node_id"
                    ),
                    {**params, "wkt": wkt},
                ).scalar_one()
            )
        a, b, c = nodes
        direct = None
        segment_ids = []
        for origin, destination, duration in ((a, c, 10), (a, b, 20), (b, c, 20)):
            segment = db.execute(
                text(
                    "INSERT INTO mining_route_segment (tenant_id, site_id, revision_id, origin_id, "
                    "destination_id, path, distance_m, duration_seconds, provenance) "
                    "SELECT :t, :site, :rev, o.node_id, d.node_id, ST_MakeLine(o.position, d.position), "
                    "100, :duration, 'Test' FROM mining_route_node o, mining_route_node d "
                    "WHERE o.node_id = :origin AND d.node_id = :destination RETURNING segment_id"
                ),
                {**params, "origin": origin, "destination": destination, "duration": duration},
            ).scalar_one()
            segment_ids.append(segment)
            if origin == a and destination == c:
                direct = segment
        assert direct is not None
        db.commit()

        def preview(tenant, grant_site, requested_site, vehicle=None):
            principal = Principal(
                user_id=tenant.admin.user_id,
                tenant_id=tenant.tenant_id,
                tenant_kind="CUSTOMER",
                session_id=uuid.uuid4(),
                grants=(Grant("DISPATCHER", "SITE", grant_site),),
            )
            scope = evaluate(principal, "dispatch.location.read")
            assert scope is not None
            set_tenant_context(db, tenant.tenant_id)
            return preview_draft_route(
                Authorized(principal, scope, db, SystemClock()),
                site_id=requested_site,
                revision_id=revision,
                origin_id=a,
                destination_id=c,
                departure=departure,
                horizon=departure + timedelta(minutes=1),
                vehicle=vehicle,
            )

        assert preview(first, site, site) == MiningRoute((a, c), 100, 10, (direct,))
        principal = Principal(
            user_id=first.admin.user_id,
            tenant_id=first.tenant_id,
            tenant_kind="CUSTOMER",
            session_id=uuid.uuid4(),
            grants=(Grant("DISPATCHER", "SITE", site),),
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())
        findings = inspect_draft_lengths(auth, site_id=site, revision_id=revision, tolerance_m=15)
        assert len(findings) == 3
        for finding in findings:
            if finding.segment_id == direct:
                assert 210 < finding.measured_m < 230
                assert not finding.within_tolerance
            else:
                assert 105 < finding.measured_m < 115
                assert finding.within_tolerance
        with pytest.raises(ValueError):
            inspect_draft_lengths(auth, site_id=site, revision_id=revision, tolerance_m=-1)
        with pytest.raises(AppError) as error:
            inspect_draft_lengths(auth, site_id=site, revision_id=uuid.uuid4(), tolerance_m=15)
        assert error.value.code == "NOT_FOUND"
        db.commit()
        # Persist policies independently; no implicit permission for unknown roads.
        with new_session() as writer:
            set_tenant_context(writer, first.tenant_id)
            category = writer.execute(
                text(
                    "SELECT vehicle_category_id FROM vehicle_category "
                    "WHERE tenant_id = :t AND is_active LIMIT 1"
                ),
                params,
            ).scalar_one()
            for segment_id in segment_ids:
                policy = {**params, "segment": segment_id, "category": category}
                writer.execute(
                    text(
                        "INSERT INTO mining_road_restriction "
                        "(tenant_id, site_id, revision_id, segment_id, max_gross_mass_kg, "
                        "max_speed_kmh, provenance, max_height_mm, max_width_mm, max_length_mm, "
                        "uphill_permille, downhill_permille) "
                        "VALUES (:t, :site, :rev, :segment, 40000, 30, 'Test', 4500, 3500, 13000, 80, 60)"
                    ),
                    policy,
                )
                writer.execute(
                    text(
                        "INSERT INTO mining_road_allowed_category "
                        "(tenant_id, site_id, revision_id, segment_id, vehicle_category_id) "
                        "VALUES (:t, :site, :rev, :segment, :category)"
                    ),
                    policy,
                )
            writer.commit()
        vehicle = VehicleProfile(first.tenant_id, site, category, 40000, 4000, 3000, 12000, 100, 80)
        assert preview(first, site, site, vehicle) == MiningRoute((a, c), 100, 12, (direct,))
        unknown = VehicleProfile(first.tenant_id, site, category, 40000)
        assert preview(first, site, site, unknown) is None
        overweight = VehicleProfile(first.tenant_id, site, category, 40001, 4000, 3000, 12000, 100, 80)
        assert preview(first, site, site, overweight) is None
        db.commit()
        # A closure committed by an independent session must be seen by the next preview.
        with new_session() as writer:
            set_tenant_context(writer, first.tenant_id)
            writer.execute(
                text(
                    "INSERT INTO mining_route_closure "
                    "(tenant_id, site_id, revision_id, segment_id, starts_at, reason) "
                    "VALUES (:t, :site, :rev, :segment, :start, 'Test closure')"
                ),
                {**params, "segment": direct, "start": departure},
            )
            writer.commit()
        assert preview(first, site, site) == MiningRoute((a, b, c), 200, 40, tuple(segment_ids[1:]))
        assert preview(first, site, site, vehicle) == MiningRoute((a, b, c), 200, 40, tuple(segment_ids[1:]))
        with pytest.raises(AppError) as error:
            preview(first, first.sites["S2"], site)
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            preview(first, first.sites["S2"], first.sites["S2"])
        assert error.value.code == "NOT_FOUND"
        with pytest.raises(AppError) as error:
            preview(second, second.sites["S1"], second.sites["S1"])
        assert error.value.code == "NOT_FOUND"
