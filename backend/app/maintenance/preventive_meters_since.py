"""Compteurs actuels d'un plan : jalon validé + hausses des relevés bruts depuis ce jalon.

Règle retenue (docs/PREVENTIVE_DUES.md) : le cumul au jalon vient d'une preuve validée (dernier
entretien déclaré et approuvé, ou clôture d'un OT préventif). On lui ajoute les hausses successives des
relevés enregistrés après le jalon, mesurées entre relevés bruts : un compteur remplacé ou décalé n'est
donc pas confondu avec le cumul. Une **baisse** (remise à zéro, compteur changé, saisie erronée) rend le
compteur non fiable jusqu'à un nouveau jalon validé : aucune échéance n'est alors déduite de ce compteur.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import VehicleMeterReading
from app.maintenance.preventive import CurrentMeters

KIND_KM = "ODOMETER_KM"
KIND_HOURS = "HOUR_METER"


def rise_since(anchor_total: Decimal, before: Decimal | None, after: Iterable[Decimal]) -> Decimal | None:
    """Cumul au jalon + hausses des relevés suivants ; None si un relevé baisse.

    `before` est le dernier relevé brut au plus tard au jalon (référence de l'échelle du compteur) ;
    sans lui, le premier relevé suivant est comparé au cumul déclaré.
    """
    total = anchor_total
    previous = before if before is not None else anchor_total
    for value in after:
        if value < previous:
            return None
        total += value - previous
        previous = value
    return total


def _readings(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, kind: str, anchor_at: datetime, as_of: datetime
) -> tuple[Decimal | None, list[Decimal]]:
    base = select(VehicleMeterReading.value).where(
        VehicleMeterReading.tenant_id == tenant_id,
        VehicleMeterReading.vehicle_id == vehicle_id,
        VehicleMeterReading.meter_kind == kind,
    )
    order = (VehicleMeterReading.read_at, VehicleMeterReading.recorded_at)
    before = db.execute(
        base.where(VehicleMeterReading.read_at <= anchor_at)
        .order_by(VehicleMeterReading.read_at.desc(), VehicleMeterReading.recorded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    after = list(
        db.execute(
            base.where(
                VehicleMeterReading.read_at > anchor_at, VehicleMeterReading.read_at <= as_of
            ).order_by(*order)
        ).scalars()
    )
    return before, after


def meters_since_anchor(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    anchor_at: datetime | None,
    anchor_km: Decimal | None,
    anchor_hours: Decimal | None,
    as_of: datetime,
) -> CurrentMeters:
    """Sans jalon daté ou sans cumul au jalon, le compteur reste inconnu (jamais supposé nul)."""
    values: dict[str, Decimal | None] = {KIND_KM: None, KIND_HOURS: None}
    reliable = {KIND_KM: True, KIND_HOURS: True}
    if anchor_at is not None:
        for kind, anchor_total in ((KIND_KM, anchor_km), (KIND_HOURS, anchor_hours)):
            if anchor_total is None:
                continue
            before, after = _readings(db, tenant_id, vehicle_id, kind, anchor_at, as_of)
            total = rise_since(anchor_total, before, after)
            values[kind] = total
            reliable[kind] = total is not None
    return CurrentMeters(
        cumulative_km=values[KIND_KM],
        cumulative_hours=values[KIND_HOURS],
        km_reliable=reliable[KIND_KM],
        hours_reliable=reliable[KIND_HOURS],
    )
