"""Les messages de traceur ne déterminent jamais le périmètre tenant."""

import uuid
from datetime import UTC, datetime

from app.fleet.gps_gateway_contract import (
    GpsDeviceMessage,
    TrustedGpsBinding,
    position_from_trusted_binding,
)

NOW = datetime(2026, 10, 29, 17, tzinfo=UTC)


def test_server_binding_supplies_vehicle_identity() -> None:
    vehicle_id = uuid.uuid4()
    binding = TrustedGpsBinding(uuid.uuid4(), uuid.uuid4(), vehicle_id, "gps-01")
    message = GpsDeviceMessage("gps-01", 9.5, -13.7, NOW, 12)
    position = position_from_trusted_binding(binding, message)
    assert position is not None
    assert position.vehicle_id == vehicle_id
    assert position.device_id == "gps-01"


def test_wrong_device_is_rejected() -> None:
    binding = TrustedGpsBinding(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "gps-01")
    message = GpsDeviceMessage("gps-02", 9.5, -13.7, NOW, 12)
    assert position_from_trusted_binding(binding, message) is None


def test_invalid_sequence_is_rejected() -> None:
    binding = TrustedGpsBinding(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "gps-01")
    message = GpsDeviceMessage("gps-01", 9.5, -13.7, NOW, -1)
    assert position_from_trusted_binding(binding, message) is None
