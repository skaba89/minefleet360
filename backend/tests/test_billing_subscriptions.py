"""Lot 2 commercialisation SaaS — abonnements tenant↔plan (routes plateforme et /tenant/subscription).

Couvre : création (essai daté ou activation directe), unicité de l'abonnement vivant
(l'ancien est annulé, historique conservé), transitions du cycle de vie avec conflits
de version, renouvellement manuel, lecture par la société de SON abonnement (RLS),
refus des rôles non autorisés et indiscernabilité inter-tenant (404).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _sub_body(plan_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"plan_id": plan_id, "notes": "Abonnement de test"}
    body.update(overrides)
    return body


def _active_plan_id(client: TestClient, api: Api) -> str:
    plan = client.post(
        f"{API}/platform/saas-plans",
        headers=api.platform(),
        json={"code": f"SUB_{uuid.uuid4().hex[:8].upper()}", "name": "Plan Abonnements", "status": "ACTIVE"},
    )
    assert plan.status_code == 201, plan.text
    return plan.json()["plan_id"]


def test_trial_then_activate_and_tenant_read(client: TestClient, api: Api) -> None:
    t = api.tenant()
    plan_id = _active_plan_id(client, api)
    created = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers={**api.platform(), "If-Match": '"1"'},
        json=_sub_body(plan_id, trial_days=30),
    )
    assert created.status_code == 201, created.text
    sub = created.json()
    assert sub["status"] == "TRIAL" and sub["plan_name"] == "Plan Abonnements"
    assert sub["plan_code"].startswith("SUB_")
    assert sub["trial_ends_at"] is not None and sub["suspended_at"] is None

    # Lecture par la société : son abonnement + quotas du plan.
    own = client.get(f"{API}/tenant/subscription", headers=t.admin.headers)
    assert own.status_code == 200, own.text
    body = own.json()
    assert body["subscription_id"] == sub["subscription_id"] and body["status"] == "TRIAL"
    assert body["plan"]["code"] == sub["plan_code"]
    assert body["plan"]["max_users"] is not None or body["plan"]["max_users"] is None  # schéma stable

    activate = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{sub['subscription_id']}/activate",
        headers={**api.platform(), "If-Match": '"1"'},
    )
    assert activate.status_code == 200 and activate.json()["status"] == "ACTIVE"
    own2 = client.get(f"{API}/tenant/subscription", headers=t.admin.headers)
    assert own2.json()["status"] == "ACTIVE"


def test_create_requires_active_plan(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    draft = client.post(
        f"{API}/platform/saas-plans",
        headers=platform,
        json={"code": f"DRAFT_{uuid.uuid4().hex[:8].upper()}", "name": "Plan Brouillon"},
    )
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT"
    resp = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers=platform,
        json=_sub_body(draft.json()["plan_id"]),
    )
    assert (resp.status_code, resp.json()["code"]) == (422, "PLAN_NOT_ACTIVE")


def test_single_live_subscription_with_history(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    first_plan = _active_plan_id(client, api)
    second_plan = _active_plan_id(client, api)
    first = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json=_sub_body(first_plan)
    )
    assert first.status_code == 201
    second = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json=_sub_body(second_plan)
    )
    assert second.status_code == 201
    history = client.get(f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform).json()
    assert history["total"] == 2
    statuses = {item["subscription_id"]: item["status"] for item in history["items"]}
    assert statuses[first.json()["subscription_id"]] == "CANCELLED"
    assert statuses[second.json()["subscription_id"]] == "ACTIVE"
    # L'abonnement vu par la société est le nouveau.
    assert (
        client.get(f"{API}/tenant/subscription", headers=t.admin.headers).json()["plan"]["plan_id"]
        == second_plan
    )


def test_lifecycle_transitions_and_conflicts(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _active_plan_id(client, api)
    sub = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json=_sub_body(plan_id)
    ).json()
    base = f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{sub['subscription_id']}"

    bad = client.post(f"{base}/activate", headers={**platform, "If-Match": '"1"'})
    assert (bad.status_code, bad.json()["code"]) == (409, "STATE_TRANSITION_INVALID")

    no_reason = client.post(f"{base}/suspend", headers={**platform, "If-Match": '"1"'}, json={})
    assert no_reason.status_code == 422  # motif requis (3 caractères minimum)

    suspended = client.post(
        f"{base}/suspend", headers={**platform, "If-Match": '"1"'}, json={"reason": "Impayé constaté"}
    )
    assert suspended.status_code == 200 and suspended.json()["status"] == "SUSPENDED"
    assert suspended.json()["suspension_reason"] == "Impayé constaté"

    stale = client.post(f"{base}/reactivate", headers={**platform, "If-Match": '"1"'})
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")

    reactivated = client.post(f"{base}/reactivate", headers={**platform, "If-Match": '"2"'})
    assert reactivated.status_code == 200 and reactivated.json()["status"] == "ACTIVE"
    assert reactivated.json()["suspension_reason"] is None

    cancelled = client.post(
        f"{base}/cancel",
        headers={**platform, "If-Match": f'"{reactivated.json()["row_version"]}"'},
        json={"reason": "Résiliation demandée par le client"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"

    # Plus d'abonnement vivant : la société reçoit un 404 neutre.
    assert client.get(f"{API}/tenant/subscription", headers=t.admin.headers).status_code == 404


def test_renew_extends_period(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _active_plan_id(client, api)
    sub = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json=_sub_body(plan_id)
    ).json()
    renewed = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{sub['subscription_id']}/renew",
        headers={**platform, "If-Match": '"1"'},
        json={"period_ends_at": (datetime.now(UTC) + timedelta(days=365)).isoformat()},
    )
    assert renewed.status_code == 200 and renewed.json()["period_ends_at"] is not None
    assert renewed.json()["row_version"] == 2


def test_tenant_roles_cannot_manage_subscriptions(client: TestClient, api: Api) -> None:
    t = api.tenant()
    plan_id = _active_plan_id(client, api)
    base = f"{API}/platform/tenants/{t.tenant_id}/subscriptions"
    assert client.post(base, headers=t.admin.headers, json=_sub_body(plan_id)).status_code == 403
    assert client.get(base, headers=t.admin.headers).status_code == 403
    assert (
        client.post(
            f"{base}/{uuid.uuid4()}/suspend",
            headers={**t.admin.headers, "If-Match": '"1"'},
            json={"reason": "x"},
        ).status_code
        == 403
    )


def test_tenant_read_permissions(client: TestClient, api: Api) -> None:
    t = api.tenant()
    plan_id = _active_plan_id(client, api)
    assert (
        client.post(
            f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
            headers=api.platform(),
            json=_sub_body(plan_id),
        ).status_code
        == 201
    )
    allowed = ("TENANT_ADMIN", "DIRECTION", "FINANCE", "AUDITOR")
    denied = ("OPS_MANAGER", "HR", "DISPATCHER", "WORKSHOP_CHIEF", "STOREKEEPER", "FUEL_MANAGER", "HSE")
    for role in allowed:
        account = api.user(t, role)
        resp = client.get(f"{API}/tenant/subscription", headers=account.headers)
        assert resp.status_code == 200, (role, resp.text)
    for role in denied:
        scope = "SITE" if role in {"DISPATCHER"} else "TENANT"
        account = api.user(t, role, scope, "S1" if scope == "SITE" else None)
        resp = client.get(f"{API}/tenant/subscription", headers=account.headers)
        assert resp.status_code == 403, (role, resp.status_code)


def test_cross_tenant_subscription_is_404(client: TestClient, api: Api) -> None:
    a, b = api.tenant(), api.tenant()
    platform = api.platform()
    plan_id = _active_plan_id(client, api)
    sub = client.post(
        f"{API}/platform/tenants/{a.tenant_id}/subscriptions", headers=platform, json=_sub_body(plan_id)
    ).json()
    # Identifiant réel mais tenant du chemin différent : indiscernable d'un objet inexistant.
    wrong = client.post(
        f"{API}/platform/tenants/{b.tenant_id}/subscriptions/{sub['subscription_id']}/activate",
        headers={**platform, "If-Match": '"1"'},
    )
    assert wrong.status_code == 404 and wrong.json()["code"] == "NOT_FOUND"
    # Et la société B ne voit pas l'abonnement de A (RLS) :
    assert client.get(f"{API}/tenant/subscription", headers=b.admin.headers).status_code == 404


def test_unknown_tenant_is_404(client: TestClient, api: Api) -> None:
    plan_id = _active_plan_id(client, api)
    resp = client.post(
        f"{API}/platform/tenants/{uuid.uuid4()}/subscriptions",
        headers=api.platform(),
        json=_sub_body(plan_id),
    )
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"
