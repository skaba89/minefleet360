"""Tests d'orchestration des gardes de réception GPS."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.fleet.gps_contract import GpsPosition
from app.fleet.gps_ingestion_preflight import preflight_gps_ingestion

NOW = datetime(2026, 10, 29, 16, tzinfo=UTC)


def test_reject_invalid_position_without_database_lookup() -> None:
    db = MagicMock()
    point = GpsPosition(uuid.uuid4(), "tracker", 200, 0, NOW)
    with patch("app.fleet.gps_ingestion_preflight.resolve_gps_binding") as lookup:
        assert not preflight_gps_ingestion(
            db, tenant_id=uuid.uuid4(), site_id=uuid.uuid4(),
            position=point, supplied_secret="x" * 44, received_at=NOW
        )
        lookup.assert_not_called()


def test_reject_missing_binding_without_secret_check() -> None:
    point = GpsPosition(uuid.uuid4(), "tracker", 10, -10, NOW)
    with patch("app.fleet.gps_ingestion_preflight.resolve_gps_binding", return_value=None):
        with patch("app.fleet.gps_ingestion_preflight.verify_persisted_gps_credential") as verify:
            assert not preflight_gps_ingestion(
                MagicMock(), tenant_id=uuid.uuid4(), site_id=uuid.uuid4(),
                position=point, supplied_secret="x" * 44, received_at=NOW
            )
            verify.assert_not_called()


def test_valid_binding_requires_credential() -> None:
    point = GpsPosition(uuid.uuid4(), "tracker", 10, -10, NOW)
    binding = SimpleNamespace(gps_device_binding_id=uuid.uuid4(), revoked_at=None)
    with patch("app.fleet.gps_ingestion_preflight.resolve_gps_binding", return_value=binding):
        with patch("app.fleet.gps_ingestion_preflight.verify_persisted_gps_credential", return_value=True) as verify:
            assert preflight_gps_ingestion(
                MagicMock(), tenant_id=uuid.uuid4(), site_id=uuid.uuid4(),
                position=point, supplied_secret="x" * 44, received_at=NOW
            )
            verify.assert_called_once()
