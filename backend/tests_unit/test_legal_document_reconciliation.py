"""Reconciliation reports anomalies without mutating storage or SQL."""

import pytest

from app.legal.document_reconciliation import reconcile_document_keys


def test_detects_orphan_and_missing_objects() -> None:
    prefix = "legal/tenant-1/"
    result = reconcile_document_keys(
        tenant_prefix=prefix,
        stored_keys=[prefix + "contracts/a/one.pdf", prefix + "contracts/a/orphan.pdf"],
        registered_keys=[prefix + "contracts/a/one.pdf", prefix + "contracts/a/missing.pdf"],
    )
    assert result.orphan_object_keys == (prefix + "contracts/a/orphan.pdf",)
    assert result.missing_object_keys == (prefix + "contracts/a/missing.pdf",)


def test_exact_match_reports_no_anomalies() -> None:
    key = "legal/tenant-1/contracts/a/one.pdf"
    result = reconcile_document_keys(
        tenant_prefix="legal/tenant-1/", stored_keys=[key], registered_keys=[key]
    )
    assert result.orphan_object_keys == ()
    assert result.missing_object_keys == ()


@pytest.mark.parametrize("prefix", ["", "legal/", "legal/tenant", "other/tenant/"])
def test_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        reconcile_document_keys(tenant_prefix=prefix, stored_keys=[], registered_keys=[])


def test_rejects_cross_tenant_keys() -> None:
    with pytest.raises(ValueError, match="outside tenant"):
        reconcile_document_keys(
            tenant_prefix="legal/tenant-1/",
            stored_keys=["legal/tenant-2/contracts/a/doc.pdf"],
            registered_keys=[],
        )
