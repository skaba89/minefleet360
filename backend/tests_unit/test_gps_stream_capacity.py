"""Capacité SSE : refus avant HTTP 200 et libération fiable des places."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.fleet import gps_stream_router as stream


def _auth():
    return SimpleNamespace(
        principal=MagicMock(),
        clock=MagicMock(),
        scope=SimpleNamespace(covers_site=lambda site: True),
        db=MagicMock(),
    )


def test_stream_refuses_when_worker_is_full() -> None:
    async def run() -> None:
        slots = asyncio.BoundedSemaphore(1)
        await slots.acquire()
        with patch.object(stream, "_stream_slots", slots):
            with pytest.raises(AppError) as error:
                await stream.gps_stream(MagicMock(), _auth(), uuid.uuid4())
            assert error.value.code == "RATE_LIMITED"
            assert error.value.headers["Retry-After"] == "3"
            assert slots.locked()

    asyncio.run(run())


def test_stream_releases_after_normal_end() -> None:
    async def run() -> None:
        slots = asyncio.BoundedSemaphore(1)

        async def events(*args):
            yield stream._sse("snapshot", "[]")

        with (
            patch.object(stream, "_stream_slots", slots),
            patch.object(stream, "_events", events),
        ):
            response = await stream.gps_stream(MagicMock(), _auth(), None)
            assert slots.locked()
            frames = [chunk async for chunk in response.body_iterator]
            assert frames == ["event: snapshot\ndata: []\n\n"]
            assert not slots.locked()

    asyncio.run(run())


def test_stream_releases_after_source_failure() -> None:
    async def run() -> None:
        slots = asyncio.BoundedSemaphore(1)

        async def events(*args):
            yield stream._sse("snapshot", "[]")
            raise RuntimeError("erreur de flux simulée")

        with (
            patch.object(stream, "_stream_slots", slots),
            patch.object(stream, "_events", events),
        ):
            response = await stream.gps_stream(MagicMock(), _auth(), None)
            with pytest.raises(RuntimeError):
                async for _ in response.body_iterator:
                    pass
            assert not slots.locked()

    asyncio.run(run())


def test_stream_releases_on_client_cancel() -> None:
    async def run() -> None:
        slots = asyncio.BoundedSemaphore(1)

        async def events(*args):
            yield stream._sse("snapshot", "[]")
            await asyncio.sleep(3600)

        with (
            patch.object(stream, "_stream_slots", slots),
            patch.object(stream, "_events", events),
        ):
            response = await stream.gps_stream(MagicMock(), _auth(), None)
            iterator = response.body_iterator
            assert await anext(iterator) == "event: snapshot\ndata: []\n\n"
            await iterator.aclose()
            assert not slots.locked()

    asyncio.run(run())
