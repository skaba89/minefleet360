"""L'identité GPS vient du binding de la base, pas du message du traceur."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.fleet.gps_authenticated_device import resolve_authenticated_gps_device
from app.fleet.gps_device_credentials import fingerprint_device_secret, new_device_secret

NOW = datetime(2026, 10, 29, 18, tzinfo=UTC)


def test_valid_secret_resolves_server_vehicle_identity() -> None:
    tenant = uuid.uuid4()
    vehicle = uuid.uuid4()
    site = uuid.uuid4()
    secret = new_device_secret()
    binding = SimpleNamespace(tenant_id=tenant, vehicle_id=vehicle, site_id=site, device_id="tracker-01")
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (binding, fingerprint_device_secret(secret))
    result = resolve_authenticated_gps_device(
        db,
        trusted_tenant_id=tenant,
        device_id="tracker-01",
        supplied_secret=secret,
        at=NOW,
    )
    assert result is not None
    assert result.vehicle_id == vehicle
    assert result.site_id == site


def test_wrong_secret_is_denied() -> None:
    db = MagicMock()
    secret = new_device_secret()
    binding = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        device_id="tracker-01",
    )
    db.execute.return_value.one_or_none.return_value = (binding, fingerprint_device_secret(secret))
    result = resolve_authenticated_gps_device(
        db,
        trusted_tenant_id=binding.tenant_id,
        device_id="tracker-01",
        supplied_secret=new_device_secret(),
        at=NOW,
    )
    assert result is None


def test_missing_device_is_denied() -> None:
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = None
    result = resolve_authenticated_gps_device(
        db,
        trusted_tenant_id=uuid.uuid4(),
        device_id="unknown",
        supplied_secret=new_device_secret(),
        at=NOW,
    )
    assert result is None
