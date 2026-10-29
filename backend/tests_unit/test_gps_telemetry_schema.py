"""Un traceur ne peut pas s'attribuer un autre véhicule ou tenant."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.fleet.gps_telemetry_schema import GpsTelemetryIn

NOW = datetime(2026, 10, 29, 19, tzinfo=UTC)


def payload() -> dict[str, object]:
    return {
        "device_id": "tracker-01",
        "latitude": 9.5,
        "longitude": -13.7,
        "recorded_at": NOW,
        "sequence": 5,
    }


def test_valid_payload_converts_to_domain_message() -> None:
    message = GpsTelemetryIn.model_validate(payload()).to_message()
    assert message.device_id == "tracker-01"
    assert message.sequence == 5


@pytest.mark.parametrize("field", ["tenant_id", "site_id", "vehicle_id", "supplied_secret"])
def test_forbid_identity_and_secret_fields(field: str) -> None:
    data = payload()
    data[field] = "untrusted"
    with pytest.raises(ValidationError):
        GpsTelemetryIn.model_validate(data)


@pytest.mark.parametrize("value", [-1, True, 9223372036854775808])
def test_reject_invalid_sequence(value: object) -> None:
    data = payload()
    data["sequence"] = value
    with pytest.raises(ValidationError):
        GpsTelemetryIn.model_validate(data)


def test_reject_naive_timestamp() -> None:
    data = payload()
    data["recorded_at"] = NOW.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        GpsTelemetryIn.model_validate(data)
