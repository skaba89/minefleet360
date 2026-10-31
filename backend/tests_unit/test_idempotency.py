import uuid

import pytest

from app.core.errors import AppError
from app.core.idempotency import request_fingerprint, validate_idempotency_key


def test_request_fingerprint_is_stable_and_scoped_to_operation() -> None:
    body = b'{"occurred_at":"2026-10-31T08:00:00Z","event":"START"}'
    first = request_fingerprint("post", "/missions/{mission_id}/events", body)

    assert len(first) == 32
    assert first == request_fingerprint("POST", "/missions/{mission_id}/events", body)
    assert first != request_fingerprint("POST", "/work-orders/{work_order_id}/notes", body)
    assert first != request_fingerprint("POST", "/missions/{mission_id}/events", body + b" ")


@pytest.mark.parametrize(
    "value",
    [str(uuid.uuid4()), "device-12:event_42", "sync.2026-10-31"],
)
def test_idempotency_key_accepts_only_bounded_opaque_values(value: str) -> None:
    assert validate_idempotency_key(value) == value


@pytest.mark.parametrize("value", ["", " espace", "clé-accentuée", "x" * 129, "line\nbreak"])
def test_idempotency_key_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(AppError) as caught:
        validate_idempotency_key(value)
    assert caught.value.code == "VALIDATION_ERROR"
