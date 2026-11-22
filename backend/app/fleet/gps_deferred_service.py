"""Ingestion différée interne : aucune route publique ni activation."""

import uuid
from bisect import bisect_left, insort
from datetime import timedelta
from typing import Literal

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.gps_deferred_contract import (
    MAX_SHARE_POINTS,
    DeferredPhoneBatch,
    capture_in_window,
    point_fingerprint,
)
from app.fleet.gps_live_service import _lock_user, _share, _vehicle
from app.fleet.gps_models import FleetGpsPosition

PointStatus = Literal["accepted", "duplicate", "rejected", "conflict"]
MIN_CAPTURE_INTERVAL = timedelta(seconds=5)


def ingest_deferred(
    auth: Authorized, share_id: uuid.UUID, batch: DeferredPhoneBatch
) -> dict[uuid.UUID, PointStatus]:
    """Appel interne après Require(fleet.gps.share). Aucun acquittement avant commit."""
    if auth.scope.permission != "fleet.gps.share":
        raise AppError("PERMISSION_DENIED")
    _lock_user(auth)
    share = _share(auth, share_id)
    now = auth.clock.now()
    if share.auth_session_id != auth.principal.session_id:
        raise AppError("NOT_FOUND")
    if share.stopped_at is not None or not share.started_at <= now < share.expires_at:
        raise AppError("CONFLICT")
    vehicle = _vehicle(auth, share.vehicle_id, sharing=True)
    if vehicle.site_id != share.site_id:
        raise AppError("CONFLICT")

    # Le verrou du partage sérialise live et différé. Ne charge ni coordonnées ni corps JSON.
    rows = auth.db.execute(
        select(
            FleetGpsPosition.client_point_id,
            FleetGpsPosition.client_point_fingerprint,
            FleetGpsPosition.recorded_at,
        ).where(
            FleetGpsPosition.tenant_id == auth.tenant_id,
            FleetGpsPosition.phone_share_id == share_id,
        )
    ).all()
    known = {row.client_point_id: row.client_point_fingerprint for row in rows if row.client_point_id}
    timestamps = sorted(row.recorded_at for row in rows)
    results: dict[uuid.UUID, PointStatus] = {}
    for point in sorted(batch.points, key=lambda item: item.recorded_at):
        point_id = point.client_point_id
        fingerprint = point_fingerprint(point)
        if point_id in known:
            results[point_id] = "duplicate" if known[point_id] == fingerprint else "conflict"
            continue
        in_window = capture_in_window(
            point.recorded_at,
            started_at=share.started_at,
            expires_at=share.expires_at,
            received_at=now,
        )
        if not in_window or len(timestamps) >= MAX_SHARE_POINTS:
            results[point_id] = "rejected"
            continue
        index = bisect_left(timestamps, point.recorded_at)
        neighbors = timestamps[max(0, index - 1) : index + 1]
        if any(abs(point.recorded_at - at) < MIN_CAPTURE_INTERVAL for at in neighbors):
            results[point_id] = "rejected"
            continue

        auth.db.add(
            FleetGpsPosition(
                tenant_id=auth.tenant_id,
                vehicle_id=vehicle.vehicle_id,
                site_id=share.site_id,
                device_id=f"phone:{share_id}",
                source="PHONE",
                phone_share_id=share_id,
                client_point_id=point_id,
                client_point_fingerprint=fingerprint,
                latitude=point.latitude,
                longitude=point.longitude,
                accuracy_m=point.accuracy_m,
                speed_kmh=point.speed_kmh,
                heading_deg=point.heading_deg,
                recorded_at=point.recorded_at,
                received_at=now,
            )
        )
        insort(timestamps, point.recorded_at)
        known[point_id] = fingerprint
        results[point_id] = "accepted"
        # Jamais de recul du dernier relevé ni d'alerte/SSE pour un point différé.
        if share.last_recorded_at is None or share.last_recorded_at < point.recorded_at:
            share.last_recorded_at = point.recorded_at

    auth.db.commit()
    return {point.client_point_id: results[point.client_point_id] for point in batch.points}
