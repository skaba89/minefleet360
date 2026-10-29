"""Frontière GPS : corps non fiable, erreurs neutres et délégation sans commit."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext
from app.fleet.gps_payload_ingestion import (
    MAX_GPS_PAYLOAD_BYTES,
    accept_gps_telemetry_payload,
    decode_gps_telemetry,
)

NOW = datetime(2026, 10, 29, 19, tzinfo=UTC)
BODY = {
    "device_id": "traceur-fictif",
    "latitude": 9.5,
    "longitude": -13.7,
    "recorded_at": NOW.isoformat(),
    "sequence": 1,
}


@pytest.mark.parametrize("field", ["tenant_id", "vehicle_id", "site_id", "secret", "supplied_secret"])
def test_payload_identity_and_secret_are_never_trusted(field: str) -> None:
    marker = "DONNEE-PRIVEE-FICTIVE"
    with pytest.raises(AppError) as caught:
        decode_gps_telemetry(json.dumps({**BODY, field: marker}).encode())
    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.details is None
    assert marker not in caught.value.message_fr


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b" " * (MAX_GPS_PAYLOAD_BYTES + 1),
        b'{"device_id":"traceur-a","device_id":"traceur-b"}',
        b'{"latitude":NaN}',
        b'{"latitude":Infinity}',
        b"[" * 2000 + b"0" + b"]" * 2000,
    ],
)
def test_invalid_message_never_reaches_authentication_or_database(payload: bytes) -> None:
    db = MagicMock()
    with patch("app.fleet.gps_payload_ingestion.accept_gps_device_message") as accept:
        with pytest.raises(AppError) as caught:
            accept_gps_telemetry_payload(
                db,
                context=TrustedGatewayContext(uuid.uuid4()),
                payload=payload,
                supplied_secret="x" * 44,
                received_at=NOW,
            )
        assert caught.value.code == "VALIDATION_ERROR"
        accept.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sequence", True),
        ("sequence", "1"),
        ("sequence", -1),
        ("sequence", 9223372036854775808),
        ("latitude", "9.5"),
        ("latitude", 91),
        ("longitude", -181),
        ("recorded_at", "2026-10-29T19:00:00"),
        ("device_id", " traceur-fictif "),
    ],
)
def test_schema_remains_strict_after_json_decoding(field: str, value: object) -> None:
    with pytest.raises(AppError):
        decode_gps_telemetry(json.dumps({**BODY, field: value}).encode())


def test_valid_json_uses_only_separate_trusted_context_and_preserves_caller_transaction() -> None:
    db = MagicMock()
    context = TrustedGatewayContext(uuid.uuid4())
    with patch("app.fleet.gps_payload_ingestion.accept_gps_device_message", return_value=True) as accept:
        assert accept_gps_telemetry_payload(
            db,
            context=context,
            payload=json.dumps(BODY).encode(),
            supplied_secret="x" * 44,
            received_at=NOW,
        )
    args = accept.call_args
    assert args.args == (db,)
    assert args.kwargs["context"] is context
    assert args.kwargs["message"].recorded_at == NOW
    assert args.kwargs["message"].sequence == 1
    assert args.kwargs["supplied_secret"] == "x" * 44
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_refusal_is_not_transformed_into_success() -> None:
    with patch("app.fleet.gps_payload_ingestion.accept_gps_device_message", return_value=False):
        assert not accept_gps_telemetry_payload(
            MagicMock(),
            context=TrustedGatewayContext(uuid.uuid4()),
            payload=json.dumps(BODY).encode(),
            supplied_secret="x" * 44,
            received_at=NOW,
        )
