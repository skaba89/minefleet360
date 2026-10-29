"""Séquence et position GPS partagent une opération SQL annulable."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.fleet.gps_atomic_ingestion import ingest_gps_atomically
from app.fleet.gps_contract import GpsPosition

NOW = datetime(2026, 10, 29, 16, tzinfo=UTC)


def _invoke(db: MagicMock) -> bool:
    return ingest_gps_atomically(
        db,
        tenant_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        position=GpsPosition(uuid.uuid4(), "tracker", 10, -10, NOW),
        supplied_secret="x" * 44,
        received_at=NOW,
        sequence=9,
    )


def test_invalid_position_stops_before_savepoint() -> None:
    db = MagicMock()
    with patch("app.fleet.gps_atomic_ingestion.preflight_gps_ingestion", return_value=False):
        assert not _invoke(db)
    db.begin_nested.assert_not_called()


def test_duplicate_rolls_back_sequence_savepoint() -> None:
    db = MagicMock()
    binding = SimpleNamespace(gps_device_binding_id=uuid.uuid4(), revoked_at=None)
    with (
        patch("app.fleet.gps_atomic_ingestion.preflight_gps_ingestion", return_value=True),
        patch("app.fleet.gps_atomic_ingestion.resolve_gps_binding", return_value=binding),
        patch("app.fleet.gps_atomic_ingestion.advance_gps_sequence", return_value=True),
        patch("app.fleet.gps_atomic_ingestion.persist_validated_gps_position", return_value=False),
    ):
        assert not _invoke(db)
    db.begin_nested.return_value.__enter__.assert_called_once()
    db.begin_nested.return_value.__exit__.assert_called_once()
    assert db.begin_nested.return_value.__exit__.call_args.args[0] is not None


def test_valid_position_keeps_sequence_and_insert() -> None:
    db = MagicMock()
    binding = SimpleNamespace(gps_device_binding_id=uuid.uuid4(), revoked_at=None)
    with (
        patch("app.fleet.gps_atomic_ingestion.preflight_gps_ingestion", return_value=True),
        patch("app.fleet.gps_atomic_ingestion.resolve_gps_binding", return_value=binding),
        patch("app.fleet.gps_atomic_ingestion.advance_gps_sequence", return_value=True),
        patch("app.fleet.gps_atomic_ingestion.persist_validated_gps_position", return_value=True),
    ):
        assert _invoke(db)
    assert db.begin_nested.return_value.__exit__.call_args.args[0] is None
