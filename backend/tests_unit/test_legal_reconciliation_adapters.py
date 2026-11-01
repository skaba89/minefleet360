"""S3 pagination and tenant SQL boundaries for read-only document reconciliation."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.reconciliation_adapters import reconcile_tenant_contract_objects


def test_paginated_s3_reconciliation_is_tenant_scoped() -> None:
    tenant = uuid.uuid4()
    prefix = f"legal/{tenant}/"
    common = prefix + "contracts/a/common.pdf"
    orphan = prefix + "contracts/a/orphan.pdf"
    missing = prefix + "contracts/a/missing.pdf"
    s3 = MagicMock()
    s3.list_objects_v2.side_effect = [
        {"Contents": [{"Key": common}], "IsTruncated": True, "NextContinuationToken": "next"},
        {"Contents": [{"Key": orphan}], "IsTruncated": False},
    ]
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [common, missing]
    result = reconcile_tenant_contract_objects(tenant_id=tenant, s3_client=s3, bucket="private-legal", db=db)
    assert result.orphan_object_keys == (orphan,)
    assert result.missing_object_keys == (missing,)
    assert s3.list_objects_v2.call_count == 2
    assert s3.list_objects_v2.call_args_list[1].kwargs["ContinuationToken"] == "next"
    statement = str(db.execute.call_args.args[0])
    assert "tenant_id = :tenant" in statement
    assert db.execute.call_args.args[1]["tenant"] == tenant


def test_cross_tenant_s3_result_fails_before_sql() -> None:
    s3, db = MagicMock(), MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "legal/other/contracts/x/file.pdf"}],
        "IsTruncated": False,
    }
    with pytest.raises(ValueError, match="out-of-scope"):
        reconcile_tenant_contract_objects(tenant_id=uuid.uuid4(), s3_client=s3, bucket="private-legal", db=db)
    db.execute.assert_not_called()


def test_invalid_pagination_token_fails_closed() -> None:
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {"IsTruncated": True}
    with pytest.raises(ValueError, match="continuation"):
        reconcile_tenant_contract_objects(
            tenant_id=uuid.uuid4(), s3_client=s3, bucket="private-legal", db=MagicMock()
        )
