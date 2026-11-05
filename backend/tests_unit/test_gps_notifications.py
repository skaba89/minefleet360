"""Contrat de notification : transaction, périmètre et absence de données GPS."""

import uuid
from unittest.mock import MagicMock

from app.fleet.gps_notifications import GPS_NOTIFICATION_CHANNEL, notify_gps_position


def test_notification_staged_in_current_transaction_without_commit() -> None:
    tenant_id = uuid.uuid4()
    db = MagicMock()
    notify_gps_position(db, tenant_id)
    db.execute.assert_called_once()
    statement, parameters = db.execute.call_args.args
    assert str(statement) == "SELECT pg_notify(:channel, :payload)"
    assert parameters == {"channel": GPS_NOTIFICATION_CHANNEL, "payload": str(tenant_id)}
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_notification_payload_contains_no_position_or_vehicle_details() -> None:
    db = MagicMock()
    tenant_id = uuid.uuid4()
    notify_gps_position(db, tenant_id)
    parameters = db.execute.call_args.args[1]
    assert set(parameters) == {"channel", "payload"}
    assert len(parameters["payload"]) == 36
    assert GPS_NOTIFICATION_CHANNEL == "minefleet_gps_positions"
