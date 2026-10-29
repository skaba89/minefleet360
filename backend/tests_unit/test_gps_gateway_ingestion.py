"""Tests de la chaîne interne GPS : aucune identité de camion déclarée."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.fleet.gps_gateway_contract import GpsDeviceMessage, TrustedGpsBinding
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext, accept_gps_device_message

NOW = datetime(2026, 10, 29, 19, tzinfo=UTC)


def _message() -> GpsDeviceMessage:
    return GpsDeviceMessage("tracker-01", 9.5, -13.7, NOW, 8)


def test_unknown_device_never_reaches_position_storage() -> None:
    with (
        patch("app.fleet.gps_gateway_ingestion.resolve_authenticated_gps_device", return_value=None),
        patch("app.fleet.gps_gateway_ingestion.ingest_gps_atomically") as write,
    ):
        assert not accept_gps_device_message(
            MagicMock(),
            context=TrustedGatewayContext(uuid.uuid4()),
            message=_message(),
            supplied_secret="x" * 44,
            received_at=NOW,
        )
        write.assert_not_called()


def test_authenticated_device_uses_only_server_vehicle_identity() -> None:
    tenant = uuid.uuid4()
    vehicle = uuid.uuid4()
    binding = TrustedGpsBinding(tenant, uuid.uuid4(), vehicle, "tracker-01")
    with (
        patch("app.fleet.gps_gateway_ingestion.resolve_authenticated_gps_device", return_value=binding),
        patch("app.fleet.gps_gateway_ingestion.ingest_gps_atomically", return_value=True) as write,
    ):
        assert accept_gps_device_message(
            MagicMock(),
            context=TrustedGatewayContext(tenant),
            message=_message(),
            supplied_secret="x" * 44,
            received_at=NOW,
        )
        assert write.call_args.kwargs["position"].vehicle_id == vehicle
        assert write.call_args.kwargs["sequence"] == 8


def test_cross_tenant_binding_is_rejected_before_write() -> None:
    tenant = uuid.uuid4()
    binding = TrustedGpsBinding(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "tracker-01")
    with (
        patch("app.fleet.gps_gateway_ingestion.resolve_authenticated_gps_device", return_value=binding),
        patch("app.fleet.gps_gateway_ingestion.ingest_gps_atomically") as write,
    ):
        assert not accept_gps_device_message(
            MagicMock(),
            context=TrustedGatewayContext(tenant),
            message=_message(),
            supplied_secret="x" * 44,
            received_at=NOW,
        )
        write.assert_not_called()
