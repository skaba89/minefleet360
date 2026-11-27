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
        "100, :duration, 'Synthetic survey')"
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
            conn.execute(segment, road)
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "wkt": "LINESTRING(-13.499 9.5,-13.5 9.5)"})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "wkt": "LINESTRING(-13.5 9.5,-13.498 9.5)"})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "duration": 0})
            with rejected(conn, "23514"):
                conn.execute(segment, {**road, "destination": a})
            with rejected(conn, "42501"):
                conn.execute(text("UPDATE mining_route_revision SET status = 'APPROVED'"))
            with rejected(conn, "42501"):
                conn.execute(text("DELETE FROM mining_route_segment"))

        with engine.begin() as conn:
            conn.execute(context, {"t": str(second.tenant_id)})
            assert conn.execute(text("SELECT count(*) FROM mining_route_revision")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_route_node")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM mining_route_segment")).scalar_one() == 0
            with rejected(conn, "23503"):
                conn.execute(
                    node,
                    {**params, "t": second.tenant_id, "site": second.sites["S1"], "wkt": "POINT(-13.5 9.5)"},
                )
    finally:
        engine.dispose()
