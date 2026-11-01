"""Service only reports scoped aggregate document storage anomalies."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.reconciliation_service import summarize_tenant_contract_storage


def test_service_returns_redacted_counts() -> None:
    tenant = uuid.uuid4()
    prefix = f"legal/{tenant}/"
    common = prefix + "contracts/a/common.pdf"
    orphan = prefix + "contracts/a/private-name.pdf"
    db, s3 = MagicMock(), MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [common]
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": common}, {"Key": orphan}],
        "IsTruncated": False,
    }
    report = summarize_tenant_contract_storage(
        authenticated_tenant_id=tenant, s3_client=s3, bucket="private-bucket", db=db
    )
    assert report.orphan_count == 1
    assert report.missing_count == 0
    assert not report.consistent
    assert "private-name" not in str(report)
    assert s3.list_objects_v2.call_args.kwargs["Prefix"] == prefix
    assert db.execute.call_args.args[1]["tenant"] == tenant


def test_zero_tenant_fails_before_queries() -> None:
    s3, db = MagicMock(), MagicMock()
    with pytest.raises(PermissionError):
        summarize_tenant_contract_storage(
            authenticated_tenant_id=uuid.UUID(int=0),
            s3_client=s3,
            bucket="private-bucket",
            db=db,
        )
    s3.list_objects_v2.assert_not_called()
    db.execute.assert_not_called()
