"""La revue interne respecte la permission et la portée site."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_approval_evidence import ApprovalEvidence
from app.maintenance.preventive_review_authorized import review_meter_evidence


NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _auth(permission: str, *, within_site: bool = True) -> SimpleNamespace:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(site_id=uuid.uuid4())
    return SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope=SimpleNamespace(permission=permission, covers_site=lambda _: within_site),
    )


def test_review_denies_wrong_permission_before_db_access() -> None:
    auth = _auth("maintenance.preventive.read")
    with pytest.raises(AppError) as exc:
        review_meter_evidence(auth, uuid.uuid4(), ApprovalEvidence(None, None, "", False), as_of=NOW)
    assert exc.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()


def test_review_denies_foreign_site_without_audit() -> None:
    auth = _auth("maintenance.preventive.manage", within_site=False)
    with patch("app.maintenance.preventive_review_authorized.record_reconciliation_review") as record:
        with pytest.raises(AppError) as exc:
            review_meter_evidence(auth, uuid.uuid4(), ApprovalEvidence(None, None, "", False), as_of=NOW)
    assert exc.value.code == "NOT_FOUND"
    record.assert_not_called()


def test_review_passes_authenticated_actor_and_scoped_site() -> None:
    auth = _auth("maintenance.preventive.manage")
    vehicle_id = uuid.uuid4()
    evidence = ApprovalEvidence(auth.user_id, NOW, "CERT-1", False)
    with patch(
        "app.maintenance.preventive_review_authorized.record_reconciliation_review",
        return_value=True,
    ) as record:
        assert review_meter_evidence(auth, vehicle_id, evidence, as_of=NOW) is True
    assert record.call_args.kwargs["tenant_id"] == auth.tenant_id
    assert record.call_args.kwargs["actor_id"] == auth.user_id
    assert record.call_args.kwargs["vehicle_id"] == vehicle_id
    auth.db.commit.assert_not_called()
