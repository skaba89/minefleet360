"""Pure PDF gate checks; do not claim antivirus or document authenticity."""

import hashlib

import pytest

from app.legal.document_validation import MAX_PDF_BYTES, inspect_contract_pdf


def test_pdf_content_hash_is_computed_from_bytes() -> None:
    data = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"
    digest, size = inspect_contract_pdf(data)
    assert digest == hashlib.sha256(data).hexdigest()
    assert size == len(data)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not a PDF",
        b"%PDF-1.7\nnot complete",
        b"prefix%PDF-1.7\n%%EOF",
        b"%PDF-1.7\n%%EOF\n" + b"x" * 2048,
    ],
)
def test_rejects_missing_or_invalid_pdf(content: bytes) -> None:
    with pytest.raises(ValueError):
        inspect_contract_pdf(content)


def test_rejects_oversize_pdf() -> None:
    with pytest.raises(ValueError, match="size"):
        inspect_contract_pdf(b"%PDF-1.7\n" + b"x" * MAX_PDF_BYTES + b"%%EOF")
