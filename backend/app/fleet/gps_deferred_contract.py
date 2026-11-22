"""Validation pure du futur rattrapage GPS téléphone, sans exposer de route ni écrire en base."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.fleet.gps_live_schemas import PhonePointIn

MAX_DEFERRED_POINTS = 100
MAX_DEFERRED_BYTES = 64 * 1024
MAX_SHARE_POINTS = 4320
MAX_DEFERRED_AGE = timedelta(hours=12)
FUTURE_TOLERANCE = timedelta(seconds=5)


class DeferredPhonePoint(PhonePointIn):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    client_point_id: uuid.UUID

    @field_validator("recorded_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        # Les valeurs numériques (epoch) ne font pas partie du contrat mobile.
        if not isinstance(value, (str, datetime)) or (isinstance(value, str) and "T" not in value):
            raise ValueError("Horodatage ISO 8601 avec fuseau requis")
        return value


class DeferredPhoneBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    points: list[DeferredPhonePoint] = Field(min_length=1, max_length=MAX_DEFERRED_POINTS)

    @model_validator(mode="after")
    def unique_point_ids(self) -> Self:
        # Une réponse ne doit pas contenir deux statuts ambigus pour un même ID.
        if len({point.client_point_id for point in self.points}) != len(self.points):
            raise ValueError("Identifiants de relevé répétés dans le lot")
        return self


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Champ JSON répété")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Constante JSON non finie")


def decode_deferred_batch(payload: bytes) -> DeferredPhoneBatch:
    """Borne avant parsing ; ne jamais journaliser le corps ni les détails de validation."""
    if not 0 < len(payload) <= MAX_DEFERRED_BYTES:
        raise ValueError("Taille du lot GPS invalide")
    try:
        data = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return DeferredPhoneBatch.model_validate(data)
    except (ValueError, RecursionError):
        # Le futur endpoint doit retourner un code générique, jamais les coordonnées rejetées.
        raise ValueError("Lot GPS invalide") from None


def point_fingerprint(point: DeferredPhonePoint) -> str:
    """Empreinte du contenu normalisé, indépendamment du format JSON et du fuseau équivalent."""
    content = point.model_dump(exclude={"client_point_id"})
    content["recorded_at"] = point.recorded_at.astimezone(UTC).isoformat()
    # -0.0 et 0.0 représentent la même mesure normalisée.
    normalized = {
        key: 0.0 if isinstance(value, float) and value == 0 else value for key, value in content.items()
    }
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capture_in_window(
    recorded_at: datetime, *, started_at: datetime, expires_at: datetime, received_at: datetime
) -> bool:
    """Fenêtre stricte ; ne vaut pas contrôle d'autorisation, de quota ni de cadence."""
    if any(value.utcoffset() is None for value in (recorded_at, started_at, expires_at, received_at)):
        return False
    if not started_at <= received_at < expires_at:
        return False
    return (
        max(started_at, received_at - MAX_DEFERRED_AGE)
        <= recorded_at
        <= min(expires_at, received_at + FUTURE_TOLERANCE)
    )
