"""Unit tests for private storage read-back integrity checks."""

import pytest

from app.legal.private_storage import persist_contract_pdf

PDF = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"


class MemoryStore:
    def __init__(self, *, corrupt: bool = False) -> None:
        self.items: dict[str, bytes] = {}
        self.corrupt = corrupt

    def put(self, *, key: str, content: bytes) -> None:
        self.items[key] = content

    def get(self, *, key: str) -> bytes:
        value = self.items[key]
        return value + b"modified" if self.corrupt else value

    def delete(self, *, key: str) -> None:
        self.items.pop(key, None)


def test_private_write_readback_success() -> None:
    store = MemoryStore()
    result = persist_contract_pdf(store, key="legal/tenant/contracts/contract/file.pdf", payload=PDF)
    assert result.content == PDF
    assert result.key in store.items


def test_readback_detects_tampering() -> None:
    store = MemoryStore(corrupt=True)
    with pytest.raises(ValueError, match="integrity"):
        persist_contract_pdf(store, key="legal/tenant/contracts/contract/file.pdf", payload=PDF)


@pytest.mark.parametrize("key", ["../file.pdf", "public/file.pdf", "legal/../file.pdf"])
def test_rejects_unscoped_keys(key: str) -> None:
    with pytest.raises(ValueError, match="key"):
        persist_contract_pdf(MemoryStore(), key=key, payload=PDF)
