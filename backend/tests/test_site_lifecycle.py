"""R2 : cycle de vie des sites, ressources actives, confidentialité et concurrence réelle."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.authz.principal import PermissionScope
from app.core.config import get_settings
from app.core.tenancy import set_tenant_context
from app.organization.contracts import active_site_in_scope
from app.organization.models import Site
from tests.conftest import API, Account, Api, TenantFixture


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(get_settings().database_url(), hide_parameters=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _scope() -> PermissionScope:
    return PermissionScope("test.site", True, frozenset(), frozenset())


def _etag(client: TestClient, url: str, headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "If-Match": client.get(url, headers=headers).headers["ETag"]}


def _deactivate(client: TestClient, tenant: TenantFixture, site: str = "S1"):  # type: ignore[no-untyped-def]
    url = f"{API}/sites/{tenant.sites[site]}"
    return client.post(f"{url}/deactivate", headers=_etag(client, url, tenant.admin.headers))


def _category(client: TestClient, tenant: TenantFixture) -> str:
    return client.get(f"{API}/vehicle-categories", headers=tenant.admin.headers).json()[0][
        "vehicle_category_id"
    ]


def _vehicle(client: TestClient, tenant: TenantFixture, site: str = "S1"):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/vehicles",
        headers=tenant.admin.headers,
        json={
            "site_id": str(tenant.sites[site]),
            "vehicle_category_id": _category(client, tenant),
            "fleet_number": f"F-{uuid.uuid4().hex[:10]}",
        },
    )


def _driver(client: TestClient, tenant: TenantFixture, hr: Account, site: str = "S1"):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/drivers",
        headers=hr.headers,
        json={
            "site_id": str(tenant.sites[site]),
            "employee_number": f"E-{uuid.uuid4().hex[:10]}",
            "last_name": "Nom-Fictif-Confidentiel",
            "first_name": "Prénom-Fictif",
        },
    )


def _driver_status(client: TestClient, driver_id: str, hr: Account, body: dict[str, str]):  # type: ignore[no-untyped-def]
    url = f"{API}/drivers/{driver_id}"
    return client.post(f"{url}/status", headers=_etag(client, url, hr.headers), json=body)


def test_site_blockers_are_exact_bounded_and_non_personal(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = api.tenant()
    hr = api.user(tenant, "HR")
    vehicle = _vehicle(client, tenant)
    driver = _driver(client, tenant, hr)
    assert vehicle.status_code == driver.status_code == 201
    site_url = f"{API}/sites/{tenant.sites['S1']}"
    before = client.get(site_url, headers=tenant.admin.headers)
    events_before = client.get(f"{API}/audit-events", headers=tenant.admin.headers).json()["total"]
    monkeypatch.setattr(get_settings(), "blocking_list_max", 1)

    blocked = _deactivate(client, tenant)

    assert (blocked.status_code, blocked.json()["code"]) == (409, "SITE_HAS_ACTIVE_RESOURCES")
    assert blocked.json()["details"] == {
        "total": 2,
        "items": [{"entity_type": "vehicle", "entity_id": vehicle.json()["vehicle_id"]}],
    }
    assert "Nom-Fictif" not in blocked.text and driver.json()["employee_number"] not in blocked.text
    after = client.get(site_url, headers=tenant.admin.headers)
    assert after.json()["status"] == "ACTIVE" and after.headers["ETag"] == before.headers["ETag"]
    assert client.get(f"{API}/audit-events", headers=tenant.admin.headers).json()["total"] == events_before


def test_driver_alone_blocks_but_other_site_and_tenant_do_not(client: TestClient, api: Api) -> None:
    tenant, other = api.tenant(), api.tenant()
    hr = api.user(tenant, "HR")
    driver = _driver(client, tenant, hr)
    assert driver.status_code == _vehicle(client, other).status_code == 201
    blocked = _deactivate(client, tenant)
    assert blocked.json()["details"] == {
        "total": 1,
        "items": [{"entity_type": "driver", "entity_id": driver.json()["driver_id"]}],
    }
    assert _deactivate(client, tenant, "S2").status_code == 200
    clean = api.tenant()
    assert _deactivate(client, clean).status_code == 200
    foreign_url = f"{API}/sites/{other.sites['S1']}/deactivate"
    foreign = client.post(foreign_url, headers={**tenant.admin.headers, "If-Match": '"1"'})
    assert foreign.status_code == 404 and foreign.json()["details"] is None


def test_terminal_resources_allow_deactivation_and_prevent_new_arrivals(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    hr = api.user(tenant, "HR")
    vehicle, driver = _vehicle(client, tenant), _driver(client, tenant, hr)
    assert vehicle.status_code == driver.status_code == 201
    vehicle_id, driver_id = vehicle.json()["vehicle_id"], driver.json()["driver_id"]
    vehicle_url = f"{API}/vehicles/{vehicle_id}"
    retired = client.post(
        f"{vehicle_url}/retire",
        headers=_etag(client, vehicle_url, tenant.admin.headers),
        json={"reason_code": "END_OF_LIFE"},
    )
    assert retired.status_code == 200
    inactive = _driver_status(client, driver_id, hr, {"status": "INACTIVE", "exit_date": "2026-01-01"})
    assert inactive.status_code == 200
    assert _deactivate(client, tenant).status_code == 200
    for response in (_vehicle(client, tenant), _driver(client, tenant, hr)):
        assert (response.status_code, response.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    for body in (
        {"status": "ACTIVE"},
        {"status": "UNAVAILABLE", "unavailability_reason": "LEAVE"},
        {"status": "SUSPENDED", "suspension_reason_code": "HSE_DECISION"},
    ):
        response = _driver_status(client, driver_id, hr, body)
        assert (response.status_code, response.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    events = client.get(
        f"{API}/audit-events", headers=tenant.admin.headers, params={"entity_id": str(tenant.sites["S1"])}
    ).json()["items"]
    assert sum(event["action"] == "site.deactivate" for event in events) == 1
    site_url = f"{API}/sites/{tenant.sites['S1']}"
    assert (
        client.post(
            f"{site_url}/reactivate", headers=_etag(client, site_url, tenant.admin.headers)
        ).status_code
        == 200
    )
    assert _driver_status(client, driver_id, hr, {"status": "ACTIVE"}).status_code == 200


def test_active_resources_cannot_be_transferred_to_inactive_site(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    hr = api.user(tenant, "HR")
    assert _deactivate(client, tenant, "S2").status_code == 200
    vehicle, driver = _vehicle(client, tenant), _driver(client, tenant, hr)
    for entity, response, headers in (
        ("vehicles", vehicle, tenant.admin.headers),
        ("drivers", driver, hr.headers),
    ):
        key = "vehicle_id" if entity == "vehicles" else "driver_id"
        url = f"{API}/{entity}/{response.json()[key]}"
        updated = client.patch(
            url, headers=_etag(client, url, headers), json={"site_id": str(tenant.sites["S2"])}
        )
        assert (updated.status_code, updated.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
        assert client.get(url, headers=headers).json()["site_id"] == str(tenant.sites["S1"])


def test_site_shared_lock_blocks_deactivation_until_resource_commit(
    client: TestClient, api: Api, db_session: Session
) -> None:
    tenant = api.tenant()
    set_tenant_context(db_session, tenant.tenant_id)
    site = active_site_in_scope(db_session, _scope(), tenant.sites["S1"])
    assert site is not None
    engine = create_engine(get_settings().database_url(), hide_parameters=True)
    try:
        with Session(engine) as competing:
            set_tenant_context(competing, tenant.tenant_id)
            competing.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(OperationalError) as exc:
                competing.execute(
                    select(Site).where(Site.site_id == site.site_id).with_for_update(key_share=True)
                )
            assert exc.value.orig is not None and exc.value.orig.sqlstate == "55P03"
            competing.rollback()
        category = _category(client, tenant)
        db_session.execute(
            text(
                "INSERT INTO vehicle (tenant_id, site_id, vehicle_category_id, fleet_number)"
                " VALUES (:tenant, :site, :category, 'CONCURRENT-FICTIVE')"
            ),
            {"tenant": tenant.tenant_id, "site": site.site_id, "category": uuid.UUID(category)},
        )
        db_session.commit()
        assert _deactivate(client, tenant).json()["code"] == "SITE_HAS_ACTIVE_RESOURCES"
    finally:
        engine.dispose()


def test_deactivation_lock_blocks_arrivals_and_refreshes_cached_status(api: Api, db_session: Session) -> None:
    tenant = api.tenant()
    set_tenant_context(db_session, tenant.tenant_id)
    cached = db_session.get(Site, tenant.sites["S1"])
    assert cached is not None and cached.status == "ACTIVE"
    engine = create_engine(get_settings().database_url(), hide_parameters=True)
    try:
        with Session(engine) as competing:
            set_tenant_context(competing, tenant.tenant_id)
            competing.execute(
                text("UPDATE site SET status = 'INACTIVE' WHERE site_id = :site"),
                {"site": tenant.sites["S1"]},
            )
            db_session.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(OperationalError) as exc:
                active_site_in_scope(db_session, _scope(), tenant.sites["S1"])
            assert exc.value.orig is not None and exc.value.orig.sqlstate == "55P03"
            db_session.rollback()
            competing.commit()
        set_tenant_context(db_session, tenant.tenant_id)
        # Recharge le cache puis simule une ancienne valeur pour vérifier populate_existing.
        cached = db_session.get(Site, tenant.sites["S1"])
        assert cached is not None and cached.status == "INACTIVE"
        set_committed_value(cached, "status", "ACTIVE")
        assert active_site_in_scope(db_session, _scope(), tenant.sites["S1"]) is None
        assert cached.status == "INACTIVE"
    finally:
        engine.dispose()
