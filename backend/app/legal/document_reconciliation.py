"""Read-only reconciliation of S3 contract objects against the SQL registry.

No automatic object removal: discrepancies require audited manual review.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentReconciliation:
    orphan_object_keys: tuple[str, ...]
    missing_object_keys: tuple[str, ...]


def reconcile_document_keys(
    *,
    tenant_prefix: str,
    stored_keys: Iterable[str],
    registered_keys: Iterable[str],
) -> DocumentReconciliation:
    """Find discrepancies only within a single validated tenant prefix."""
    if not tenant_prefix.startswith("legal/") or not tenant_prefix.endswith("/"):
        raise ValueError("invalid tenant prefix")
    parts = tenant_prefix.split("/")
    if len(parts) != 3 or not parts[1] or parts[2] != "":
        raise ValueError("tenant prefix must be legal/<tenant>/")
    stored = set(stored_keys)
    registered = set(registered_keys)
    if any(not key.startswith(tenant_prefix) or ".." in key for key in stored | registered):
        raise ValueError("document outside tenant boundary")
    return DocumentReconciliation(
        orphan_object_keys=tuple(sorted(stored - registered)),
        missing_object_keys=tuple(sorted(registered - stored)),
    )
