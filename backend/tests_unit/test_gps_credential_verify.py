"""Une empreinte persistée ne valide que le bon traceur actif."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.fleet.gps_credential_verify import verify_persisted_gps_credential
from app.fleet.gps_device_credentials import fingerprint_device_secret, new_device_secret

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def test_valid_stored_secret_and_wrong_secret() -> None:
    db = MagicMock()
    secret = new_device_secret()
    credential = SimpleNamespace(secret_fingerprint=fingerprint_device_secret(secret))
    db.execute.return_value.scalar_one_or_none.return_value = credential
    options = {"tenant_id": uuid.uuid4(), "binding_id": uuid.uuid4(), "at": NOW}
    assert verify_persisted_gps_credential(db, supplied_secret=secret, **options)
    assert not verify_persisted_gps_credential(db, supplied_secret=new_device_secret(), **options)


def test_missing_credential_rejected() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    assert not verify_persisted_gps_credential(
        db, tenant_id=uuid.uuid4(), binding_id=uuid.uuid4(), supplied_secret=new_device_secret(), at=NOW
    )


def test_invalid_time_rejected_before_query() -> None:
    db = MagicMock()
    assert not verify_persisted_gps_credential(
        db,
        tenant_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        supplied_secret=new_device_secret(),
        at=NOW.replace(tzinfo=None),
    )
    db.execute.assert_not_called()
