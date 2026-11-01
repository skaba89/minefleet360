"""Private object storage contract for contract PDFs.

Provider adapters must ensure encryption, private access, server-side credentials
and fail-closed retrieval. This module does not deploy a storage provider.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    content: bytes


class PrivateObjectStore(Protocol):
    """Minimal port; never expose signed/public URLs to unauthorized callers."""

    def put(self, *, key: str, content: bytes) -> None: ...

    def get(self, *, key: str) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


def persist_contract_pdf(store: PrivateObjectStore, *, key: str, payload: bytes) -> StoredObject:
    """Persist validated PDF bytes, then verify the object read back matches."""
    from app.legal.document_validation import inspect_contract_pdf

    expected_hash, _ = inspect_contract_pdf(payload)
    if not key.startswith("legal/") or not key.endswith(".pdf") or ".." in key:
        raise ValueError("invalid private object key")
    store.put(key=key, content=payload)
    retrieved = store.get(key=key)
    stored_hash, _ = inspect_contract_pdf(retrieved)
    if stored_hash != expected_hash:
        raise ValueError("stored document integrity mismatch")
    return StoredObject(key=key, content=retrieved)
