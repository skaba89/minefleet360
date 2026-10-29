"""Séquences GPS : refus des rejouements et validation des bornes."""

import uuid
from unittest.mock import MagicMock

from app.fleet.gps_sequence import advance_gps_sequence


def test_new_sequence_accepted() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = 7
    assert advance_gps_sequence(
        db, tenant_id=uuid.uuid4(), binding_id=uuid.uuid4(), sequence=7
    )
    db.execute.assert_called_once()


def test_replay_rejected() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    assert not advance_gps_sequence(
        db, tenant_id=uuid.uuid4(), binding_id=uuid.uuid4(), sequence=7
    )


def test_invalid_sequences_do_not_write() -> None:
    for value in (-1, True, 2**63, "4"):
        db = MagicMock()
        assert not advance_gps_sequence(
            db, tenant_id=uuid.uuid4(), binding_id=uuid.uuid4(), sequence=value
        )
        db.execute.assert_not_called()
