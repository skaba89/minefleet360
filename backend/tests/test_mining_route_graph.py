"""Integration checks for the draft-only PostGIS graph."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import Api


@contextmanager
def rejected(conn: Connection, code: str) -> Iterator[None]:
    with pytest.raises(DBAPIError) as error:
        with conn.begin_nested():
            yield
    assert getattr(error.value.orig, "sqlstate", None) == code


def test_draft_graph_constraints_and_rls(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    context = text("SELECT set_config('app.tenant_id', :t, true)")
    revision = text(
        "INSERT INTO mining_route_revision (tenant_id, site_id, version, provenance) "
        "VALUES (:t, :site, 1, 'Synthetic survey') RETURNING revision_id"
    )
    node = text(
        "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, position, provenance) "
        "VALUES (:t, :site, :rev, ST_GeomFromText(:wkt, 4326), 'Synthetic survey') RETURNING node_id"
    )
    segment = text(
        "INSERT INTO mining_route_segment (tenant_id, site_id, revision_id, origin_id, destination_id, "
        "path, distance_m, duration_seconds, provenance) "
        "VALUES (:t, :site, :rev, :origin, :destination, ST_GeomFromText(:wkt, 4326), "
        "100, :duration, 'Synthetic survey') RETURNING segment_id"
    )
    try:
        with engine.begin() as conn:
            conn.execute(context, {"t": str(first.tenant_id)})
            scope = {"t": first.tenant_id, "site": first.sites["S1"]}
            rev = conn.execute(revision, scope).scalar_one()
            with rejected(conn, "23505"):
                conn.execute(revision, scope)
            with rejected(conn, "42501"):
                conn.execute(revision, {"t": second.tenant_id, "site": second.sites["S1"]})
            params = {**scope, "rev": rev}
            a = conn.execute(node, {**params, "wkt": "POINT(-13.5 9.5)"}).scalar_one()
            b = conn.execute(node, {**params, "wkt": "POINT(-13.499 9.5)"}).scalar_one()
            with rejected(conn, "23514"):
                conn.execute(node, {**params, "wkt": "POINT(-13.5 95)"})
            with rejected(conn, "23503"):
                conn.execute(node, {**params, "site": first.sites["S2"], "wkt": "POINT(-13.5 9.5)"})
            road = {
                **params,
                "origin": a,
                "destination": b,
                "wkt": "LINESTRING(-13.5 9.5,-13.499 9.5)",
                "duration": 30,
            }
            segment_id = conn.execute(segment, road).scalar_one()
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "wkt": "LINESTRING(-13.499 9.5,-13.5 9.5)"})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "wkt": "LINESTRING(-13.5 9.5,-13.498 9.5)"})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "duration": 0})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "destination": a})
            restriction = text(
                "INSERT INTO mining_road_restriction "
                "(tenant_id, site_id, revision_id, segment_id, max_gross_mass_kg, max_speed_kmh, provenance) "
                "VALUES (:t, :site, :rev, :segment, :mass, 30, 'Survey')"
            )
            policy_params = {**params, "segment": segment_id, "mass": 40000}
            with rejected(conn, "23514"):
                conn.execute(restriction, {**policy_params, "mass": 0})
            dimensions = text(
                "INSERT INTO mining_road_restriction "
                "(tenant_id, site_id, revision_id, segment_id, max_gross_mass_kg, max_speed_kmh, "
                "provenance, max_height_mm, max_width_mm, max_length_mm) "
                "VALUES (:t, :site, :rev, :segment, :mass, 30, 'Survey', :height, :width, :length)"
            )
            with rejected(conn, "23514"):
                conn.execute(dimensions, {**policy_params, "height": 4000, "width": None, "length": 12000})
            with rejected(conn, "23514"):
                conn.execute(dimensions, {**policy_params, "height": 0, "width": 3000, "length": 12000})
            conn.execute(dimensions, {**policy_params, "height": 4000, "width": 3000, "length": 12000})
            assert (
                conn.execute(
                    text("SELECT max_height_mm FROM mining_road_restriction WHERE segment_id = :segment"),
                    policy_params,
                ).scalar_one()
                == 4000
            )
            with rejected(conn, "23505"):
                conn.execute(restriction, policy_params)
            with rejected(conn, "23503"):
                conn.execute(restriction, {**policy_params, "site": first.sites["S2"]})
            with rejected(conn, "42501"):
                conn.execute(restriction, {**policy_params, "t": second.tenant_id})
            category = conn.execute(
                text("SELECT vehicle_category_id FROM vehicle_category WHERE tenant_id = :t LIMIT 1"),
                scope,
            ).scalar_one()
            allow = text(
                "INSERT INTO mining_road_allowed_category "
                "(tenant_id, site_id, revision_id, segment_id, vehicle_category_id) "
                "VALUES (:t, :site, :rev, :segment, :category)"
            )
            conn.execute(allow, {**policy_params, "category": category})
            with rejected(conn, "23505"):
                conn.execute(allow, {**policy_params, "category": category})
            with rejected(conn, "42501"):
                conn.execute(text("UPDATE mining_road_restriction SET max_speed_kmh = 100"))
            with rejected(conn, "42501"):
                conn.execute(text("DELETE FROM mining_road_allowed_category"))
            closure = text(
                "INSERT INTO mining_route_closure "
                "(tenant_id, site_id, revision_id, segment_id, starts_at, ends_at, reason) "
                "VALUES (:t, :site, :rev, :segment, now(), now() + interval '1 hour', 'Test closure')"
            )
            closure_params = {**params, "segment": segment_id}
            conn.execute(closure, closure_params)
            with rejected(conn, "23514"):
                conn.execute(
                    text(
                        "INSERT INTO mining_route_closure "
                        "(tenant_id, site_id, revision_id, segment_id, starts_at, ends_at, reason) "
                        "VALUES (:t, :site, :rev, :segment, now(), now(), 'Invalid interval')"
                    ),
                    closure_params,
                )
            with rejected(conn, "23503"):
                conn.execute(closure, {**closure_params, "site": first.sites["S2"]})
            with rejected(conn, "42501"):
                conn.execute(closure, {**closure_params, "t": second.tenant_id})
            with rejected(conn, "42501"):
                conn.execute(text("DELETE FROM mining_route_closure"))
            with rejected(conn, "42501"):
                conn.execute(text("UPDATE mining_route_revision SET status = 'APPROVED'"))
            with rejected(conn, "42501"):
                conn.execute(text("DELETE FROM mining_route_segment"))

        with engine.begin() as conn:
            conn.execute(context, {"t": str(second.tenant_id)})
            assert conn.execute(text("SELECT count(*) FROM mining_route_revision")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_route_node")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_route_segment")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_route_closure")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_road_restriction")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_road_allowed_category")).scalar_one() == 0
            with rejected(conn, "23503"):
                conn.execute(
                    node,
                    {**params, "t": second.tenant_id, "site": second.sites["S1"], "wkt": "POINT(-13.5 9.5)"},
                )
    finally:
        engine.dispose()
