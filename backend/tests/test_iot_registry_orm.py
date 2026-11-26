"""Exercise ORM mappings against the migrated PostgreSQL schema."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

from app.core.db import new_session
from app.iot.models import IoTGateway, IoTManufacturer, IoTSensor
from app.iot.schemas import (
    GatewayCreate,
    GatewayOut,
    ManufacturerCreate,
    ManufacturerOut,
    SensorCreate,
    SensorOut,
)
from tests.conftest import Api


def test_registry_orm_roundtrip(api: Api) -> None:
    tenant = api.tenant()
    with new_session() as session:
        session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant.tenant_id)})
        manufacturer = IoTManufacturer(tenant_id=tenant.tenant_id, name="Fictitious OEM")
        session.add(manufacturer)
        session.flush()
        gateway = IoTGateway(
            tenant_id=tenant.tenant_id,
            **GatewayCreate(
                site_id=tenant.sites["S1"],
                manufacturer_id=manufacturer.manufacturer_id,
                external_id="demo-gateway",
                model="Demo",
                source_kind="SIMULATED",
            ).model_dump(),
        )
        session.add(gateway)
        session.flush()
        sensor = IoTSensor(
            tenant_id=tenant.tenant_id,
            site_id=gateway.site_id,
            source_kind=gateway.source_kind,
            **SensorCreate(
                gateway_id=gateway.gateway_id,
                manufacturer_id=manufacturer.manufacturer_id,
                external_id="demo-sensor",
                model="Demo",
                sensor_kind="TPMS",
            ).model_dump(),
        )
        session.add(sensor)
        session.flush()
        assert ManufacturerOut.model_validate(manufacturer).name == "Fictitious OEM"
        assert GatewayOut.model_validate(gateway).status == "REGISTERED"
        assert SensorOut.model_validate(sensor).source_kind == "SIMULATED"
        assert session.scalar(select(IoTSensor).where(IoTSensor.sensor_id == sensor.sensor_id)) is sensor
        session.rollback()


def test_registry_contracts_reject_server_fields() -> None:
    assert ManufacturerCreate(name="  Demo  ").name == "Demo"
    for name in (" ", "x" * 121, "a\x00b"):
        with pytest.raises(ValidationError):
            ManufacturerCreate(name=name)
    payload = {
        "gateway_id": str(uuid.uuid4()),
        "manufacturer_id": str(uuid.uuid4()),
        "external_id": "s1",
        "model": "Demo",
        "sensor_kind": "TPMS",
    }
    assert SensorCreate.model_validate(payload).sensor_kind == "TPMS"
    for field, value in (
        ("tenant_id", str(uuid.uuid4())),
        ("site_id", str(uuid.uuid4())),
        ("source_kind", "PHYSICAL"),
        ("status", "RETIRED"),
        ("sensor_kind", "INVALID"),
    ):
        with pytest.raises(ValidationError):
            SensorCreate.model_validate({**payload, field: value})
