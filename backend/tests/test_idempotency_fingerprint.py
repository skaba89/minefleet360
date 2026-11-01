"""Tests unitaires des garde-fous d'idempotence, sans accès base."""
import pytest

from app.core.errors import AppError
from app.core.idempotency import request_fingerprint, validate_idempotency_key


@pytest.mark.parametrize(
    "key",
    [
        "offline-event-123",
        "550e8400-e29b-41d4-a716-446655440000",
        "A",
        "k" * 128,
        "abc.def:123_456",
    ],
)
def test_idempotency_key_accepts_valid_opaque_keys(key: str) -> None:
    assert validate_idempotency_key(key) == key


@pytest.mark.parametrize(
    "key",
    [
        "",
        " key",
        "key ",
        "key/123",
        "key\nsecond",
        "évenement",
        "x" * 129,
        "-starts-with-dash",
    ],
)
def test_idempotency_key_rejects_unsafe_values(key: str) -> None:
    with pytest.raises(AppError) as raised:
        validate_idempotency_key(key)
    assert raised.value.code == "VALIDATION_ERROR"


def test_fingerprint_is_deterministic_and_sensitive_to_request() -> None:
    original = request_fingerprint("POST", "/api/v1/events", b'{"value":1}')
    assert original == request_fingerprint("post", "/api/v1/events", b'{"value":1}')
    assert len(original) == 32

    assert original != request_fingerprint("PUT", "/api/v1/events", b'{"value":1}')
    assert original != request_fingerprint("POST", "/api/v1/events/other", b'{"value":1}')
    assert original != request_fingerprint("POST", "/api/v1/events", b'{"value":2}')


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/events"),
        ("DELETE", "/api/v1/events"),
        ("POST", "api/v1/events"),
        ("POST", "/" + "x" * 300),
    ],
)
def test_fingerprint_rejects_unsupported_method_or_path(method: str, path: str) -> None:
    with pytest.raises(ValueError):
        request_fingerprint(method, path, b"{}")
