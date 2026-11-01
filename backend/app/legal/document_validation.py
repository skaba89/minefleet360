"""Server-side primitives for future private contract PDF ingestion.

PDF structure checks are a first gate, not antivirus scanning or content trust.
No document is marked verified by this module.
"""

import hashlib

MAX_PDF_BYTES = 25 * 1024 * 1024


def inspect_contract_pdf(payload: bytes) -> tuple[str, int]:
    """Reject unsupported inputs and return a SHA-256 calculated from file bytes."""
    if not payload or len(payload) > MAX_PDF_BYTES:
        raise ValueError("invalid document size")
    if not payload.startswith(b"%PDF-"):
        raise ValueError("document is not a PDF")
    if b"%%EOF" not in payload[-2048:]:
        raise ValueError("incomplete PDF document")
    return hashlib.sha256(payload).hexdigest(), len(payload)
