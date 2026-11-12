"""Lot 2b commercialisation SaaS — application des quotas au provisionnement.

Couvre : refus 422 QUOTA_EXCEEDED à la borne pour les quatre quotas provisionnés
(utilisateurs, sites, véhicules, traceurs GPS), libération de place (désactivation
d'utilisateur, réforme de véhicule, révocation de traceur), quotas illimités (NULL),
absence d'abonnement (aucune borne), essai soumis aux bornes, abonnement annulé
(borne levée), détail du refus (champ, limite, usage) et société inconnue côté
plateforme inchangée.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _plan_with_quota(client: TestClient, api: Api, **quotas: int | None) -> str:
    body: dict[str, object] = {
        "code": f"QUO_{uuid.uuid4().hex[:8].upper()}",
        "name": "Plan Quotas",
        "status": "ACTIVE",
        **quotas,
    }
    plan = client.post(f"{API}/platform/saas-plans", headers=api.platform(), json=body)
    assert plan.status_code == 201, plan.text
    return plan.json()["plan_id"]


def _subscribe(client: TestClient, api: Api, tenant_id: str, plan_id: str) -> None:
    created = client.post(
        f"{API}/platform/tenants/{tenant_id}/subscriptions", headers=api.platform(), json={"plan_id": plan_id}
    )
    assert created.status_code == 201, created.text


def _exceeded(resp_json: dict) -> dict:  # type: ignore[type-arg]
    details = resp_json.get("details") or []
    return details[0] if details else {}


def test_user_quota_blocks_invitation_and_deactivation_frees(client: TestClient, api: Api) -> None:
    # La société est créée avec son admin (1 utilisateur consommé) : borne 2.
    t = api.tenant(sites=())
    plan_id = _plan_with_quota(client, api, max_users=2)
    _subscribe(client, api, str(t.tenant_id), plan_id)

    invited = client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": f"ops.{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Nom-Test OPS",
            "role_code": "OPS_MANAGER",
            "scope_type": "TENANT",
        },
    )
    assert invited.status_code == 201, invited.text

    refused = client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": f"hr.{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Nom-Test HR",
            "role_code": "HR",
            "scope_type": "TENANT",
        },
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED"), refused.text
    detail = _exceeded(refused.json())
    assert detail["field"] == "max_users" and detail["limit"] == 2 and detail["usage"] == 2

    # La désactivation du second utilisateur libère la place.
    deactivated = client.post(
        f"{API}/users/{invited.json()['user_account_id']}/deactivate",
        headers={**t.admin.headers, "If-Match": '"1"'},
    )
    assert deactivated.status_code == 200, deactivated.text
    again = client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": f"aud.{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Nom-Test AUD",
            "role_code": "AUDITOR",
            "scope_type": "TENANT",
        },
    )
    assert again.status_code == 201, again.text


def test_site_quota_blocks_second_site(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan_with_quota(client, api, max_sites=1)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    refused = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S2", "name": "Site S2", "site_type": "MINE"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED")
    assert _exceeded(refused.json())["field"] == "max_sites"


def test_vehicle_quota_blocks_and_reform_frees(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan_with_quota(client, api, max_vehicles=1)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0]

    def _create(fleet: str) -> object:
        return client.post(
            f"{API}/vehicles",
            headers=t.admin.headers,
            json={
                "site_id": str(t.sites["S1"]),
                "vehicle_category_id": category["vehicle_category_id"],
                "fleet_number": fleet,
            },
        )

    first = _create("QUO-001")
    assert first.status_code == 201, first.text
    refused = _create("QUO-002")
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED")

    # La réforme libère la place (les véhicules RETIRED ne consomment pas de quota).
    retired = client.post(
        f"{API}/vehicles/{first.json()['vehicle_id']}/retire",
        headers={**t.admin.headers, "If-Match": '"1"'},
        json={"reason_code": "END_OF_LIFE"},
    )
    assert retired.status_code == 200, retired.text
    again = _create("QUO-003")
    assert again.status_code == 201, again.text


def test_gps_tracker_quota_blocks_binding(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan_with_quota(client, api, max_gps_trackers=1)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0]

    def _vehicle(fleet: str) -> dict:  # type: ignore[type-arg]
        created = client.post(
            f"{API}/vehicles",
            headers=t.admin.headers,
            json={
                "site_id": str(t.sites["S1"]),
                "vehicle_category_id": category["vehicle_category_id"],
                "fleet_number": fleet,
            },
        )
        assert created.status_code == 201, created.text
        return created.json()

    first, second = _vehicle("QUO-T1"), _vehicle("QUO-T2")
    bound = client.post(
        f"{API}/vehicles/{first['vehicle_id']}/gps/tracker",
        headers=t.admin.headers,
        json={"device_id": "gps-quo-0001"},
    )
    assert bound.status_code == 201, bound.text
    refused = client.post(
        f"{API}/vehicles/{second['vehicle_id']}/gps/tracker",
        headers=t.admin.headers,
        json={"device_id": "gps-quo-0002"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED")

    # La révocation libère la place.
    revoked = client.post(f"{API}/vehicles/{first['vehicle_id']}/gps/tracker/revoke", headers=t.admin.headers)
    assert revoked.status_code == 204, revoked.text
    again = client.post(
        f"{API}/vehicles/{second['vehicle_id']}/gps/tracker",
        headers=t.admin.headers,
        json={"device_id": "gps-quo-0003"},
    )
    assert again.status_code == 201, again.text


def test_null_quota_is_unlimited(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1", "S2", "S3"))
    plan_id = _plan_with_quota(client, api, max_sites=None, max_users=None)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    fourth = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S4", "name": "Site S4", "site_type": "MINE"},
    )
    assert fourth.status_code == 201, fourth.text


def test_no_subscription_means_no_quota(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1", "S2"))
    extra = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S3", "name": "Site S3", "site_type": "MINE"},
    )
    assert extra.status_code == 201, extra.text


def test_trial_enforces_quota_and_cancellation_lifts_it(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    platform = api.platform()
    plan_id = _plan_with_quota(client, api, max_sites=1)
    trial = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers=platform,
        json={"plan_id": plan_id, "trial_days": 14},
    )
    assert trial.status_code == 201 and trial.json()["status"] == "TRIAL"
    refused = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S2", "name": "Site S2", "site_type": "MINE"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED")

    # L'annulation de l'abonnement (terminal) lève la borne.
    cancelled = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{trial.json()['subscription_id']}/cancel",
        headers={**platform, "If-Match": '"1"'},
        json={"reason": "Fin de l'essai sans activation"},
    )
    assert cancelled.status_code == 200
    allowed = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S2", "name": "Site S2", "site_type": "MINE"},
    )
    assert allowed.status_code == 201, allowed.text


def test_quota_message_is_french_and_explicit(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan_with_quota(client, api, max_sites=1)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    refused = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S2", "name": "Site S2", "site_type": "MINE"},
    )
    message = refused.json()["message_fr"]
    assert "formule" in message and "libérez" in message
