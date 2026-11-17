"""Rattachement d'un conducteur sous-traitant au référentiel (lot 1, tranche 2c) : donnée RH, HR seul."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Account, Api, TenantFixture


def _subcontractor(client: TestClient, t: TenantFixture, *, ended: bool = False) -> str:
    created = client.post(
        f"{API}/subcontractors",
        headers=t.admin.headers,
        json={"code": f"ST-{uuid.uuid4().hex[:6].upper()}", "legal_name": "Transports Fictifs SARL"},
    )
    assert created.status_code == 201, created.text
    item = created.json()
    if ended:
        resp = client.patch(
            f"{API}/subcontractors/{item['subcontractor_id']}",
            headers={**t.admin.headers, "If-Match": f'"{item["row_version"]}"'},
            json={"status": "ENDED", "status_reason": "Fin de la relation"},
        )
        assert resp.status_code == 200, resp.text
    return str(item["subcontractor_id"])


def _driver(client: TestClient, t: TenantFixture, hr: Account, **extra: object):  # type: ignore[no-untyped-def]
    body = {
        "site_id": str(t.sites["S1"]),
        "employee_number": f"M-{uuid.uuid4().hex[:6]}",
        "last_name": "Nom-Test",
        "first_name": "Prénom",
        "employment_type": "SUBCONTRACTOR",
        "external_company_name": "Transports Fictifs SARL",
        **extra,
    }
    return client.post(f"{API}/drivers", headers=hr.headers, json=body)


def _patch(client: TestClient, hr: Account, driver: dict, **body: object):  # type: ignore[no-untyped-def,type-arg]
    url = f"{API}/drivers/{driver['driver_id']}"
    version = client.get(url, headers=hr.headers).headers["ETag"]
    return client.patch(url, headers={**hr.headers, "If-Match": version}, json=body)


def test_driver_link_is_hr_only_and_never_logged_as_a_value(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR", "SITE", "S1")  # lit le référentiel en portée SITE
    assert client.get(f"{API}/subcontractors", headers=hr.headers).status_code == 200
    partner = _subcontractor(client, t)
    created = _driver(client, t, hr, subcontractor_id=partner)
    assert created.status_code == 201, created.text
    driver = created.json()
    assert driver["subcontractor_id"] == partner
    # Donnée RH : absente des vues des autres rôles (même politique que external_company_name).
    url = f"{API}/drivers/{driver['driver_id']}"
    for role, scope, site in (
        ("DISPATCHER", "SITE", "S1"),
        ("OPS_MANAGER", "TENANT", None),
        ("AUDITOR", "TENANT", None),
    ):
        raw = client.get(url, headers=api.user(t, role, scope, site).headers).text
        assert '"subcontractor_id"' not in raw and partner not in raw, role
    # Statut d'emploi changé sans détacher : refusé ; détachement explicite : accepté, journalisé sans valeur.
    silent = _patch(client, hr, driver, employment_type="EMPLOYEE")
    assert silent.status_code == 422 and silent.json()["details"][0]["type"] == "must_clear"
    detached = _patch(client, hr, driver, employment_type="EMPLOYEE", subcontractor_id=None)
    assert detached.status_code == 200, detached.text
    assert detached.json()["subcontractor_id"] is None
    audit = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"entity_id": driver["driver_id"]}
    ).json()["items"]
    update = next(e for e in audit if e["action"] == "driver.update")
    assert "subcontractor_id" in update["changed_fields"]
    assert partner not in str(audit)  # la valeur du rattachement n'est jamais journalisée


def test_driver_subcontractor_link_is_validated(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    hr = api.user(t, "HR")
    partner = _subcontractor(client, t)
    employee = _driver(
        client, t, hr, employment_type="EMPLOYEE", external_company_name=None, subcontractor_id=partner
    )
    assert employee.status_code == 422 and employee.json()["details"][0]["type"] == "employment_mismatch"
    for missing in (str(uuid.uuid4()), _subcontractor(client, other)):  # inconnu ou d'un autre tenant
        refused = _driver(client, t, hr, subcontractor_id=missing)
        assert (refused.status_code, refused.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    ended = _driver(client, t, hr, subcontractor_id=_subcontractor(client, t, ended=True))
    assert ended.status_code == 422 and ended.json()["details"][0]["type"] == "not_active"
    # Conducteur sous-traitant sans rattachement : toujours permis (pas de reprise automatique).
    plain = _driver(client, t, hr)
    assert plain.status_code == 201 and plain.json()["subcontractor_id"] is None
