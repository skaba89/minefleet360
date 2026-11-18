"""Le conducteur réalise sa checklist « Prise de poste », et rien d'autre (décision du 18 novembre 2026)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_hse_inspections import (  # noqa: F401  (fixtures w, storage)
    JPEG,
    MemoryStore,
    World,
    _inspect,
    _template,
    _upload,
    storage,
    w,
)


def test_driver_performs_only_pre_shift_on_own_site(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    driver = api.user(w.t, "DRIVER", "SITE", "S1")
    pre_shift = _template(client, w, f"PDP-{uuid.uuid4().hex[:6]}", target="PRE_SHIFT").json()
    vehicle_check = _template(client, w, f"VEH-{uuid.uuid4().hex[:6]}", target="VEHICLE").json()

    listed = client.get(f"{API}/hse/checklist-templates", headers=driver.headers)
    assert listed.status_code == 200, listed.text
    assert {t["target_type"] for t in listed.json()} == {"PRE_SHIFT"}
    ids = {t["hse_checklist_template_id"] for t in listed.json()}
    assert pre_shift["hse_checklist_template_id"] in ids
    assert vehicle_check["hse_checklist_template_id"] not in ids

    done = _inspect(client, w, pre_shift, headers=driver.headers, vehicle_id=None)
    assert done.status_code == 201, done.text
    assert done.json()["performed_by"] == str(driver.user_id)
    # Hors prise de poste : indiscernable d'un modèle inexistant.
    other = _inspect(client, w, vehicle_check, headers=driver.headers)
    assert (other.status_code, other.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    # Autre site : refusé.
    elsewhere = _inspect(
        client, w, pre_shift, headers=driver.headers, vehicle_id=None, site_id=str(w.t.sites["S2"])
    )
    assert (elsewhere.status_code, elsewhere.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    # Aucune lecture des inspections (les siennes comprises) : le conducteur n'a pas hse.inspection.read.
    assert client.get(f"{API}/hse/inspections", headers=driver.headers).status_code == 403
    inspection_id = done.json()["hse_inspection_id"]
    assert client.get(f"{API}/hse/inspections/{inspection_id}", headers=driver.headers).status_code == 403


def test_driver_evidence_only_on_own_inspection(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
    storage: MemoryStore,  # noqa: F811
) -> None:
    driver = api.user(w.t, "DRIVER", "SITE", "S1")
    pre_shift = _template(client, w, f"PDE-{uuid.uuid4().hex[:6]}", target="PRE_SHIFT").json()
    mine = _inspect(client, w, pre_shift, headers=driver.headers, vehicle_id=None).json()
    theirs = _inspect(client, w, pre_shift, vehicle_id=None).json()  # réalisée par le mécanicien du site
    assert _upload(client, driver.headers, mine["hse_inspection_id"], JPEG, "image/jpeg").status_code == 201
    refused = _upload(client, driver.headers, theirs["hse_inspection_id"], JPEG, "image/jpeg")
    assert refused.status_code == 404
