"""Non-régression : le précontrôle précède toute écriture GPS."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.fleet.gps_contract import GpsPosition
from app.fleet.gps_position_write import persist_validated_gps_position

NOW = datetime(2026, 10, 29, 16, tzinfo=UTC)


def test_denied_position_is_not_written() -> None:
    db = MagicMock()
    point = GpsPosition(uuid.uuid4(), "tracker-01", 10, -10, NOW)
    with patch(
        "app.fleet.gps_position_write.preflight_gps_ingestion", return_value=False
    ):
        result = persist_validated_gps_position(
            db,
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            position=point,
            supplied_secret="x" * 44,
            received_at=NOW,
        )
    assert not result
    db.execute.assert_not_called()


def test_duplicate_returns_false_without_failure() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    point = GpsPosition(uuid.uuid4(), "tracker-01", 10, -10, NOW)
    with patch(
        "app.fleet.gps_position_write.preflight_gps_ingestion", return_value=True
    ):
        result = persist_validated_gps_position(
            db,
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            position=point,
            supplied_secret="x" * 44,
            received_at=NOW,
        )
    assert not result
    db.execute.assert_called_once()


def test_first_position_returns_true() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid.uuid4()
    point = GpsPosition(uuid.uuid4(), "tracker-01", 10, -10, NOW)
    with patch(
        "app.fleet.gps_position_write.preflight_gps_ingestion", return_value=True
    ):
        result = persist_validated_gps_position(
            db,
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            position=point,
            supplied_secret="x" * 44,
            received_at=NOW,
        )
    assert result
    db.execute.assert_called_once()
