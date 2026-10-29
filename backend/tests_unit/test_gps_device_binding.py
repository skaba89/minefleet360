"""Rattachement GPS : protections contre l'usurpation de camion."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.fleet.gps_device_binding import GpsDeviceBinding, device_matches_binding

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def test_binding_matches_only_authorized_vehicle_and_site() -> None:
    binding = GpsDeviceBinding(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "unit-1", NOW)
    kwargs = {
        "tenant_id": binding.tenant_id,
        "vehicle_id": binding.vehicle_id,
        "site_id": binding.site_id,
        "device_id": binding.device_id,
        "recorded_at": NOW,
    }
    assert device_matches_binding(binding, **kwargs)
    assert not device_matches_binding(binding, **{**kwargs, "vehicle_id": uuid.uuid4()})
    assert not device_matches_binding(binding, **{**kwargs, "site_id": uuid.uuid4()})
    assert not device_matches_binding(binding, **{**kwargs, "tenant_id": uuid.uuid4()})
    assert not device_matches_binding(binding, **{**kwargs, "device_id": "unit-2"})


def test_binding_rejects_revocation_and_invalid_time() -> None:
    binding = GpsDeviceBinding(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "unit-1", NOW)
    kwargs = {
        "tenant_id": binding.tenant_id,
        "vehicle_id": binding.vehicle_id,
        "site_id": binding.site_id,
        "device_id": binding.device_id,
        "recorded_at": NOW,
    }
    assert not device_matches_binding(replace(binding, revoked_at=NOW), **kwargs)
    assert not device_matches_binding(binding, **{**kwargs, "recorded_at": NOW - timedelta(seconds=1)})
    assert not device_matches_binding(binding, **{**kwargs, "recorded_at": NOW.replace(tzinfo=None)})
    assert not device_matches_binding(binding, **{**kwargs, "device_id": " unit-1"})
