"""Frontière JSON bornée pour une passerelle GPS déjà authentifiée.

Le tenant fiable et le secret sont fournis séparément du corps. Ce service
ne crée pas de route HTTP et laisse la transaction à son appelant.
"""

import json
from datetime import datetime
from typing import Any, NoReturn

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext, accept_gps_device_message
from app.fleet.gps_telemetry_schema import GpsTelemetryIn

MAX_GPS_PAYLOAD_BYTES = 16 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("Non-finite JSON constant")


def decode_gps_telemetry(payload: bytes) -> GpsTelemetryIn:
    """Refuser tout message ambigu ou invalide sans exposer son contenu."""
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_GPS_PAYLOAD_BYTES:
        raise AppError("VALIDATION_ERROR", message_fr="Message GPS vide ou trop volumineux.")
    try:
        # Le parseur Pydantic accepte la dernière occurrence d'une clé répétée.
        # Vérifier l'unicité d'abord, puis conserver ses règles JSON strictes
        # (notamment la date ISO avec fuseau) plutôt qu'une coercition Python.
        json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return GpsTelemetryIn.model_validate_json(payload)
    except (ValueError, UnicodeDecodeError, RecursionError, ValidationError):
        raise AppError("VALIDATION_ERROR", message_fr="Message GPS invalide.") from None


def accept_gps_telemetry_payload(
    db: Session,
    *,
    context: TrustedGatewayContext,
    payload: bytes,
    supplied_secret: str,
    received_at: datetime,
) -> bool:
    """Valider le JSON puis authentifier le traceur et stocker atomiquement.

    True signifie qu'une nouvelle position est insérée dans la transaction
    courante. False signifie refus ou doublon ; ce n'est pas un accusé de
    succès fournisseur. L'appelant décide du commit et de la réponse réseau.
    """
    telemetry = decode_gps_telemetry(payload)
    return accept_gps_device_message(
        db,
        context=context,
        message=telemetry.to_message(),
        supplied_secret=supplied_secret,
        received_at=received_at,
    )
