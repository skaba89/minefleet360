"""Hub LISTEN : isolation entre sociétés, coalescence et nettoyage."""

import asyncio
import uuid
from unittest.mock import patch

from app.fleet.gps_notification_listener import GpsNotificationHub


def test_notifies_only_matching_tenant_and_coalesces() -> None:
    async def scenario() -> None:
        hub = GpsNotificationHub()

        async def inactive() -> None:
            await asyncio.Event().wait()

        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        with patch.object(hub, "_listen", side_effect=inactive):
            async with hub.subscribe(tenant_a) as a, hub.subscribe(tenant_b) as b:
                hub._broadcast(tenant_a)
                hub._broadcast(tenant_a)
                assert a.qsize() == 1
                assert b.empty()
                a.get_nowait()
                hub._broadcast(tenant_b)
                assert a.empty()
                assert b.qsize() == 1
        assert hub._task is None
        assert not hub._subscribers

    asyncio.run(scenario())


def test_disconnected_listener_wakes_all_for_full_snapshot() -> None:
    async def scenario() -> None:
        hub = GpsNotificationHub()

        async def inactive() -> None:
            await asyncio.Event().wait()

        with patch.object(hub, "_listen", side_effect=inactive):
            async with hub.subscribe(uuid.uuid4()) as a, hub.subscribe(uuid.uuid4()) as b:
                hub._wake_all()
                assert a.qsize() == 1
                assert b.qsize() == 1

    asyncio.run(scenario())
