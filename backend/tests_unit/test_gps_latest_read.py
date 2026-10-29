"""Contrôles de lecture GPS : permission, horodatage et périmètre."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.fleet.gps_latest_read import latest_visible_positions

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _auth(
    permission: str = "fleet.vehicle.read", allowed_site: uuid.UUID | None = None
) -> SimpleNamespace:
    db = MagicMock()
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(
            permission=permission,
            covers_site=lambda site: site == allowed_site,
        ),
    )


def test_wrong_permission_rejected_before_query() -> None:
    auth = _auth("fleet.vehicle.update")
    with pytest.raises(AppError) as error:
        latest_visible_positions(auth, as_of=NOW)
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()


def test_naive_time_rejected() -> None:
    auth = _auth()
    with pytest.raises(AppError) as error:
        latest_visible_positions(auth, as_of=NOW.replace(tzinfo=None))
    assert error.value.code == "VALIDATION_ERROR"
    auth.db.execute.assert_not_called()


def test_filter_does_not_expose_foreign_site_position() -> None:
    site = uuid.uuid4()
    foreign_site = uuid.uuid4()
    auth = _auth(allowed_site=site)
    visible = SimpleNamespace(site_id=site)
    foreign = SimpleNamespace(site_id=foreign_site)
    auth.db.execute.return_value.scalars.return_value.all.return_value = [foreign, visible]
    assert latest_visible_positions(auth, as_of=NOW) == [visible]
    assert latest_visible_positions(auth, as_of=NOW, site_id=str(foreign_site)) == []
