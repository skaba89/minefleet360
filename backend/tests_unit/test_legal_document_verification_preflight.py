"""Trusted preflight must fail closed before touching private storage."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.document_verification_preflight import load_authorized_verification_context


def kwargs() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "contract_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "actor_user_id": uuid.uuid4(),
        "review_permission_granted": True,
        "tenant_wide": True,
        "accessible_site_ids": frozenset(),
    }


def test_authorized_preflight_reads_trusted_ownership() -> None:
    db = MagicMock()
    values = kwargs()
    db.execute.return_value.first.return_value = (
        values["tenant_id"],
        uuid.uuid4(),
        "DRAFT",
        uuid.uuid4(),
    )
    result = load_authorized_verification_context(db, **values)
    assert result is not None
    assert result.authenticated_tenant_id == values["tenant_id"]
    statement = str(db.execute.call_args.args[0])
    assert "d.status = 'PENDING'" in statement
    assert "FOR UPDATE OF c, d" in statement
    assert db.execute.call_args.args[1]["tenant"] == values["tenant_id"]


def test_missing_permission_does_not_query_database() -> None:
    db = MagicMock()
    values = kwargs()
    values["review_permission_granted"] = False
    assert load_authorized_verification_context(db, **values) is None
    db.execute.assert_not_called()


@pytest.mark.parametrize("case", ["foreign_tenant", "self_review", "other_site", "submitted", "missing"])
def test_preflight_rejects_untrusted_or_invalid_document(case: str) -> None:
    db = MagicMock()
    values = kwargs()
    if case == "missing":
        db.execute.return_value.first.return_value = None
    else:
        row_tenant = uuid.uuid4() if case == "foreign_tenant" else values["tenant_id"]
        uploader = values["actor_user_id"] if case == "self_review" else uuid.uuid4()
        db.execute.return_value.first.return_value = (
            row_tenant,
            uuid.uuid4(),
            "PENDING_REVIEW" if case == "submitted" else "DRAFT",
            uploader,
        )
    if case == "other_site":
        values["tenant_wide"] = False
    assert load_authorized_verification_context(db, **values) is None


def test_zero_actor_does_not_query_database() -> None:
    db = MagicMock()
    values = kwargs()
    values["actor_user_id"] = uuid.UUID(int=0)
    assert load_authorized_verification_context(db, **values) is None
    db.execute.assert_not_called()
