"""Transport borné du futur endpoint GPS différé, non exposé."""

from anyio import fail_after
from fastapi import Request
from starlette.requests import ClientDisconnect

from app.core.config import Settings
from app.core.errors import AppError
from app.fleet.gps_deferred_contract import MAX_DEFERRED_BYTES, DeferredPhoneBatch, decode_deferred_batch


async def read_deferred_batch(request: Request, settings: Settings) -> DeferredPhoneBatch:
    """À appeler après authentification, avant les verrous métier."""
    if not settings.gps_deferred_enabled:
        raise AppError("NOT_FOUND")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise AppError("VALIDATION_ERROR")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise AppError("VALIDATION_ERROR")
    payload = bytearray()
    try:
        with fail_after(10):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > MAX_DEFERRED_BYTES:
                    raise AppError("VALIDATION_ERROR")
                payload.extend(chunk)
    except (TimeoutError, ClientDisconnect):
        raise AppError("VALIDATION_ERROR") from None
    try:
        return decode_deferred_batch(bytes(payload))
    except ValueError:
        raise AppError("VALIDATION_ERROR") from None
