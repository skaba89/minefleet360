"""Registre explicite des décodeurs de charges utiles GPS.

Le choix de l'adaptateur est effectué côté serveur. Un traceur ne peut jamais
sélectionner lui-même son décodeur, son tenant, son site ou son véhicule.
L'enregistrement d'un adaptateur ne constitue pas une certification matérielle.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

from pydantic import ValidationError

from app.core.errors import AppError
from app.fleet.gps_gateway_contract import GpsDeviceMessage
from app.fleet.gps_telemetry_schema import GpsTelemetryIn

DEFAULT_GPS_ADAPTER_ID = "minefleet-json-v1"
MAX_GPS_PAYLOAD_BYTES = 16 * 1024
_ADAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


@dataclass(frozen=True)
class GpsAdapterMetadata:
    """Description versionnée d'un adaptateur, sans promesse de compatibilité."""

    adapter_id: str
    vendor: str
    protocol: str
    version: str
    hardware_certified: bool = False


class GpsPayloadAdapter(Protocol):
    metadata: GpsAdapterMetadata
    max_payload_bytes: int

    def decode(self, payload: bytes) -> GpsDeviceMessage:
        """Décoder un message non fiable vers le contrat normalisé."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("Non-finite JSON constant")


class MineFleetJsonV1Adapter:
    """Contrat JSON HTTPS natif de MineFleet, indépendant d'un constructeur."""

    metadata = GpsAdapterMetadata(
        adapter_id=DEFAULT_GPS_ADAPTER_ID,
        vendor="minefleet",
        protocol="json-https",
        version="1",
    )
    max_payload_bytes = MAX_GPS_PAYLOAD_BYTES

    def decode(self, payload: bytes) -> GpsDeviceMessage:
        try:
            # Pydantic accepte la dernière occurrence d'une clé répétée.
            # L'unicité est donc vérifiée avant la validation stricte du schéma.
            json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            return GpsTelemetryIn.model_validate_json(payload).to_message()
        except (ValueError, UnicodeDecodeError, RecursionError, ValidationError):
            raise AppError("VALIDATION_ERROR", message_fr="Message GPS invalide.") from None


class GpsAdapterRegistry:
    """Registre fermé construit au démarrage, sans chargement dynamique arbitraire."""

    def __init__(self, adapters: tuple[GpsPayloadAdapter, ...]) -> None:
        registered: dict[str, GpsPayloadAdapter] = {}
        for adapter in adapters:
            metadata = adapter.metadata
            if not _ADAPTER_ID.fullmatch(metadata.adapter_id):
                raise ValueError("Invalid GPS adapter identifier")
            if metadata.adapter_id in registered:
                raise ValueError("Duplicate GPS adapter identifier")
            if not 0 < adapter.max_payload_bytes <= 1024 * 1024:
                raise ValueError("Invalid GPS adapter payload limit")
            registered[metadata.adapter_id] = adapter
        if DEFAULT_GPS_ADAPTER_ID not in registered:
            raise ValueError("Default GPS adapter is required")
        self._adapters = registered

    @property
    def metadata(self) -> tuple[GpsAdapterMetadata, ...]:
        return tuple(adapter.metadata for adapter in self._adapters.values())

    def decode(self, adapter_id: str, payload: bytes) -> GpsDeviceMessage:
        adapter = self._adapters.get(adapter_id) if isinstance(adapter_id, str) else None
        if adapter is None:
            raise AppError("VALIDATION_ERROR", message_fr="Adaptateur GPS non pris en charge.")
        if not isinstance(payload, bytes) or not 0 < len(payload) <= adapter.max_payload_bytes:
            raise AppError("VALIDATION_ERROR", message_fr="Message GPS vide ou trop volumineux.")
        return adapter.decode(payload)


GPS_PAYLOAD_ADAPTERS = GpsAdapterRegistry((MineFleetJsonV1Adapter(),))
