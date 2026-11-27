from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.errors import AppError
from app.dispatch import mining_restriction_read

TENANT, SITE, REV, SEG, CATEGORY = (UUID(int=i) for i in range(1, 6))


@pytest.fixture
def auth(monkeypatch):
    auth = MagicMock()
    auth.tenant_id = TENANT
    auth.principal.tenant_kind = "CUSTOMER"
    auth.principal.mfa_enrollment_pending = False
    scope = MagicMock()
    scope.covers_site.return_value = True
    monkeypatch.setattr(mining_restriction_read, "evaluate", lambda *_: scope)
    auth.db.execute.return_value.all.return_value = [
        SimpleNamespace(
            segment_id=SEG,
            categories=[CATEGORY],
            max_gross_mass_kg=40000,
            max_speed_kmh=30,
            max_height_mm=None,
            max_width_mm=None,
            max_length_mm=None,
            uphill_permille=None,
            downhill_permille=None,
        )
    ]
    return auth


def load(auth):
    return mining_restriction_read.load_draft_restrictions(auth, site_id=SITE, revision_id=REV)


def test_scoped_snapshot_preserves_unknown_values(auth):
    result = load(auth)
    assert len(result) == 1
    rule = result[0]
    assert rule.tenant_id == TENANT
    assert rule.site_id == SITE
    assert rule.revision_id == REV
    assert rule.segment_id == SEG
    assert rule.allowed_categories == frozenset({CATEGORY})
    assert rule.max_height_mm is None
    assert rule.uphill_permille is None
    assert auth.db.execute.call_count == 1
    assert auth.db.execute.call_args.args[1] == {"tenant": TENANT, "site": SITE, "revision": REV}


def test_empty_allowlist_stays_empty(auth):
    auth.db.execute.return_value.all.return_value[0].categories = []
    assert load(auth)[0].allowed_categories == frozenset()


def test_empty_revision_and_missing_revision_are_distinct(auth):
    auth.db.execute.return_value.all.return_value = [SimpleNamespace(segment_id=None, categories=[])]
    assert load(auth) == []
    auth.db.execute.return_value.all.return_value = []
    with pytest.raises(AppError) as error:
        load(auth)
    assert error.value.code == "NOT_FOUND"


def test_scope_denial_before_query(auth, monkeypatch):
    monkeypatch.setattr(mining_restriction_read, "evaluate", lambda *_: None)
    with pytest.raises(AppError) as error:
        load(auth)
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()


def test_mfa_denial_before_query(auth):
    auth.principal.mfa_enrollment_pending = True
    with pytest.raises(AppError) as error:
        load(auth)
    assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
    auth.db.execute.assert_not_called()


def test_overflow_rejected(auth):
    row = auth.db.execute.return_value.all.return_value[0]
    auth.db.execute.return_value.all.return_value = [row] * 1001
    with pytest.raises(AppError) as error:
        load(auth)
    assert error.value.code == "CONFLICT"
    row.categories = [UUID(int=i) for i in range(1001)]
    auth.db.execute.return_value.all.return_value = [row]
    with pytest.raises(AppError) as error:
        load(auth)
    assert error.value.code == "CONFLICT"
