"""Contrôles de transport GPS différé sans activation de route."""

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi import Request
from starlette.types import Message

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.fleet.gps_deferred_contract import MAX_DEFERRED_BYTES
from app.fleet.gps_deferred_transport import read_deferred_batch


def _request(
    chunks: list[bytes],
    *,
    content_type: bytes = b"application/json",
    encoding: bytes = b"identity",
) -> Request:
    messages: Iterator[Message] = iter(
        [
            {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
            for i, chunk in enumerate(chunks)
        ]
    )

    async def receive() -> Message:
        return next(messages)

    return Request(
        {
            "type": "http",
            "headers": [(b"content-type", content_type), (b"content-encoding", encoding)],
        },
        receive,
    )


def _settings(*, enabled: bool) -> Settings:
    return get_settings().model_copy(update={"gps_deferred_enabled": enabled})


def test_gate_disabled_by_default() -> None:
    assert Settings.model_fields["gps_deferred_enabled"].default is False
    with pytest.raises(AppError, match="NOT_FOUND"):
        asyncio.run(read_deferred_batch(_request([b"invalid"]), _settings(enabled=False)))


def test_transport_accepts_fragmented_json() -> None:
    point_id = uuid.uuid4()
    raw = json.dumps(
        {
            "points": [
                {
                    "client_point_id": str(point_id),
                    "recorded_at": "2026-11-22T08:00:00Z",
                    "latitude": 9.5,
                    "longitude": -13.7,
                    "accuracy_m": 10,
                }
            ]
        }
    ).encode()
    request = _request([raw[:40], raw[40:]], content_type=b"application/json; charset=utf-8")
    batch = asyncio.run(read_deferred_batch(request, _settings(enabled=True)))
    assert batch.points[0].client_point_id == point_id


@pytest.mark.parametrize(
    ("chunks", "content_type", "encoding"),
    [
        ([b"{}"], b"text/plain", b"identity"),
        ([b"{}"], b"application/json", b"gzip"),
        ([b" " * MAX_DEFERRED_BYTES, b"x"], b"application/json", b"identity"),
        ([b"invalid"], b"application/json", b"identity"),
        ([b'{"points":[],"points":[]}'], b"application/json", b"identity"),
    ],
)
def test_transport_rejects_invalid_payload(chunks: list[bytes], content_type: bytes, encoding: bytes) -> None:
    request = _request(chunks, content_type=content_type, encoding=encoding)
    with pytest.raises(AppError, match="VALIDATION_ERROR") as exc:
        asyncio.run(read_deferred_batch(request, _settings(enabled=True)))
    assert exc.value.details is None
