"""Draft-only route preview, never a vehicle authorization or dispatch recommendation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.dispatch.mining_closure_read import load_closures
from app.dispatch.mining_closures import Closure, GraphSegment, available_roads
from app.dispatch.mining_routes import MiningRoute, RoadSegment, shortest_mining_route


def preview_draft_route(
    auth: Authorized,
    *,
    site_id: UUID,
    revision_id: UUID,
    origin_id: UUID,
    destination_id: UUID,
    departure: datetime,
    horizon: datetime,
) -> MiningRoute | None:
    """Preview topology and reference durations, not vehicle-specific feasibility.

    The closure reader enforces authorization and rejects incomplete results.
    Read closures after segments as well, so closures added during the graph read
    are considered. This remains a preview, not an atomic operational snapshot.
    """
    load_closures(auth, site_id, revision_id)
    params = {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id}
    rows = auth.db.execute(
        text(
            "SELECT segment_id, origin_id, destination_id, distance_m, duration_seconds "
            "FROM mining_route_segment "
            "WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision "
            "ORDER BY segment_id LIMIT 1001"
        ),
        params,
    ).all()
    if len(rows) > 1000:
        raise AppError("CONFLICT")
    segments = [
        GraphSegment(
            row.segment_id,
            revision_id,
            RoadSegment(
                auth.tenant_id,
                site_id,
                row.origin_id,
                row.destination_id,
                row.distance_m,
                row.duration_seconds,
                True,
            ),
        )
        for row in rows
    ]
    closures = [
        Closure(auth.tenant_id, site_id, revision_id, row.segment_id, row.starts_at, row.ends_at)
        for row in load_closures(auth, site_id, revision_id)
    ]
    roads = available_roads(
        segments,
        closures,
        tenant_id=auth.tenant_id,
        site_id=site_id,
        revision_id=revision_id,
        departure=departure,
        horizon=horizon,
    )
    result = shortest_mining_route(
        roads, tenant_id=auth.tenant_id, site_id=site_id, origin_id=origin_id, destination_id=destination_id
    )
    if result is not None and result.duration_seconds > (horizon - departure).total_seconds():
        return None
    return result
