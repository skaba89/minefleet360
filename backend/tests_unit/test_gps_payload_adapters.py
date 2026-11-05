"""Contrat du registre GPS : sélection serveur, bornes et certification explicite."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.fleet.gps_gateway_contract import GpsDeviceMessage
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext
from app.fleet.gps_payload_adapters import (
    DEFAULT_GPS_ADAPTER_ID,
    GPS_PAYLOAD_ADAPTERS,
    GpsAdapterMetadata,
    GpsAdapterRegistry,
    MineFleetJsonV1Adapter,
)
from app.fleet.gps_payload_ingestion import accept_gps_telemetry_payload

NOW = datetime(2026, 11, 5, 18, tzinfo=UTC)


class _LabAdapter:
    metadata = GpsAdapterMetadata(
        adapter_id="lab-fixture-v1",
        vendor="fixture",
        protocol="test-only",
        version="1",
    )
    max_payload_bytes = 32

    def decode(self, payload: bytes) -> GpsDeviceMessage:
        assert payload == b"fixture"
        return GpsDeviceMessage("tracker-lab", 9.5, -13.7, NOW, 42)


def test_default_registry_has_no_vendor_certification_claim() -> None:
    assert tuple(item.adapter_id for item in GPS_PAYLOAD_ADAPTERS.metadata) == (DEFAULT_GPS_ADAPTER_ID,)
    assert all(not item.hardware_certified for item in GPS_PAYLOAD_ADAPTERS.metadata)
    assert all(item.vendor not in {"teltonika", "queclink"} for item in GPS_PAYLOAD_ADAPTERS.metadata)


def test_registry_refuses_duplicate_or_invalid_adapter_identifiers() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        GpsAdapterRegistry((MineFleetJsonV1Adapter(), MineFleetJsonV1Adapter()))

    invalid = _LabAdapter()
    invalid.metadata = GpsAdapterMetadata("Invalid Adapter", "fixture", "test", "1")
    with pytest.raises(ValueError, match="Invalid"):
        GpsAdapterRegistry((MineFleetJsonV1Adapter(), invalid))


def test_unknown_adapter_is_rejected_without_echoing_payload() -> None:
    marker = "COORDONNEE-SENSIBLE-FICTIVE"
    with pytest.raises(AppError) as caught:
        GPS_PAYLOAD_ADAPTERS.decode("unknown-vendor-v1", marker.encode())
    assert caught.value.code == "VALIDATION_ERROR"
    assert marker not in caught.value.message_fr


def test_adapter_specific_limit_is_enforced_before_decoder() -> None:
    registry = GpsAdapterRegistry((MineFleetJsonV1Adapter(), _LabAdapter()))
    with pytest.raises(AppError) as caught:
        registry.decode("lab-fixture-v1", b"x" * 33)
    assert caught.value.code == "VALIDATION_ERROR"


def test_server_selected_adapter_reuses_authentication_and_atomic_ingestion() -> None:
    registry = GpsAdapterRegistry((MineFleetJsonV1Adapter(), _LabAdapter()))
    context = TrustedGatewayContext(uuid.uuid4())
    db = MagicMock()
    with (
        patch("app.fleet.gps_payload_ingestion.GPS_PAYLOAD_ADAPTERS", registry),
        patch("app.fleet.gps_payload_ingestion.accept_gps_device_message", return_value=True) as accept,
    ):
        assert accept_gps_telemetry_payload(
            db,
            context=context,
            payload=b"fixture",
            supplied_secret="x" * 44,
            received_at=NOW,
            adapter_id="lab-fixture-v1",
        )
    assert accept.call_args.kwargs["message"].device_id == "tracker-lab"
    assert accept.call_args.kwargs["message"].sequence == 42
    assert accept.call_args.kwargs["context"] is context
    db.commit.assert_not_called()
