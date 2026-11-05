"""SSE GPS : trames, snapshot complet, révocation et perte d'autorisation."""
import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.authz.principal import Grant, PermissionScope, Principal
from app.core.clock import FrozenClock
from app.fleet import gps_stream_router as stream

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        tenant_kind="CUSTOMER",
        session_id=uuid.uuid4(),
        grants=(Grant("OPS_MANAGER", "TENANT", None),),
    )


def test_sse_frame_does_not_rewrite_json_escapes() -> None:
    payload = r'{"message":"une ligne\nune autre"}'
    assert stream._sse("snapshot", payload) == "event: snapshot\ndata: " + payload + "\n\n"


def test_revoked_session_stops_before_query() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    with (
        patch.object(stream, "new_session") as open_db,
        patch.object(stream, "set_tenant_context"),
        patch.object(stream, "latest_visible_positions") as latest,
    ):
        open_db.return_value.__enter__.return_value = db
        result = stream._authorized_snapshot(principal(), FrozenClock(NOW), None)
    assert result is None
    latest.assert_not_called()


def test_site_permission_revocation_stops_before_position_read() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = SimpleNamespace(mfa_enabled=False, amr=["pwd"])
    site = uuid.uuid4()
    with (
        patch.object(stream, "new_session") as open_db,
        patch.object(stream, "set_tenant_context"),
        patch.object(stream, "load_grants", return_value=()),
        patch.object(
            stream,
            "evaluate",
            return_value=PermissionScope("fleet.vehicle.read", False, frozenset(), frozenset()),
        ),
        patch.object(stream, "latest_visible_positions") as latest,
    ):
        open_db.return_value.__enter__.return_value = db
        result = stream._authorized_snapshot(principal(), FrozenClock(NOW), site)
    assert result is None
    latest.assert_not_called()


def test_valid_snapshot_is_json_array_not_cached_foreign_data() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = SimpleNamespace(mfa_enabled=False, amr=["pwd"])
    position = SimpleNamespace(
        gps_position_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        latitude=10.0,
        longitude=-12.0,
        speed_kmh=20.0,
        heading_deg=90.0,
        accuracy_m=None,
        recorded_at=NOW,
        received_at=NOW,
        source="TRACKER",
    )
    scope = PermissionScope("fleet.vehicle.read", True, frozenset(), frozenset({"OPS_MANAGER"}))
    with (
        patch.object(stream, "new_session") as open_db,
        patch.object(stream, "set_tenant_context"),
        patch.object(stream, "load_grants", return_value=principal().grants),
        patch.object(stream, "evaluate", return_value=scope),
        patch.object(stream, "latest_visible_positions", return_value=[position]),
        patch.object(stream, "active_sources", return_value={position.gps_position_id}),
    ):
        open_db.return_value.__enter__.return_value = db
        result = stream._authorized_snapshot(principal(), FrozenClock(NOW), None)
    assert result is not None
    assert '"latitude":10.0' in result
    assert '"source_active":true' in result
    assert "tenant_id" not in result


def test_stream_sends_snapshot_then_heartbeat() -> None:
    async def run() -> list[str]:
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=False)
        with (
            patch.object(stream, "MAX_TICKS", 2),
            patch.object(stream, "INTERVAL_SECONDS", 0),
            patch.object(stream, "_authorized_snapshot", return_value="[]"),
        ):
            return [frame async for frame in stream._events(request, principal(), FrozenClock(NOW), None)]

    frames = asyncio.run(run())
    assert frames == ["event: snapshot\ndata: []\n\n", ": heartbeat\n\n"]


def test_stream_stops_if_permission_is_revoked() -> None:
    async def run() -> list[str]:
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=False)
        with (
            patch.object(stream, "MAX_TICKS", 3),
            patch.object(stream, "INTERVAL_SECONDS", 0),
            patch.object(stream, "_authorized_snapshot", side_effect=["[]", None]),
        ):
            return [frame async for frame in stream._events(request, principal(), FrozenClock(NOW), None)]

    assert asyncio.run(run()) == [
        "event: snapshot\ndata: []\n\n",
        "event: session-ended\ndata: {}\n\n",
    ]
