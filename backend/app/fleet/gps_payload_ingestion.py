"""Frontière bornée pour une passerelle GPS déjà authentifiée.

Le tenant fiable, le secret et le choix d’adaptateur sont fournis séparément
du corps. Ce service ne crée pas de route HTTP et laisse la transaction à son
appelant.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.fleet.gps_gateway_contract import GpsDeviceMessage
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext, accept_gps_device_message
from app.fleet.gps_payload_adapters import (
    DEFAULT_GPS_ADAPTER_ID,
    GPS_PAYLOAD_ADAPTERS,
    MAX_GPS_PAYLOAD_BYTES,
)


def decode_gps_telemetry(
    payload: bytes,
    *,
    adapter_id: str = DEFAULT_GPS_ADAPTER_ID,
) -> GpsDeviceMessage:
    """Décoder avec un adaptateur choisi côté serveur, sans exposer le corps."""
    return GPS_PAYLOAD_ADAPTERS.decode(adapter_id, payload)


def accept_gps_telemetry_payload(
    db: Session,
    *,
    context: TrustedGatewayContext,
    payload: bytes,
    supplied_secret: str,
    received_at: datetime,
    adapter_id: str = DEFAULT_GPS_ADAPTER_ID,
) -> bool:
    """Décoder puis authentifier le traceur et stocker atomiquement.

    True signifie qu’une nouvelle position est insérée dans la transaction
    courante. False signifie refus ou doublon ; ce n’est pas un accusé de
    succès fournisseur. L’appelant décide du commit et de la réponse réseau.

    adapter_id doit provenir de la configuration serveur associée au
    fournisseur. Il ne doit jamais être lu depuis le message du traceur.
    """
    message = decode_gps_telemetry(payload, adapter_id=adapter_id)
    return accept_gps_device_message(
        db,
        context=context,
        message=message,
        supplied_secret=supplied_secret,
        received_at=received_at,
    )
