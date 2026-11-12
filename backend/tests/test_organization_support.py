"""Lot 4 commercialisation SaaS — support plateforme, onboarding, réversibilité.

Couvre : vue support consolidée plateforme (GET /platform/tenants/{id}/overview — usage vs
quotas, abonnement courant avec statut effectif, utilisateurs, factures récentes), parcours
de démarrage de la société (GET /tenant/onboarding — étapes calculées à la lecture depuis
l'état réel, aucune persistance), export de réversibilité (GET /tenant/export — JSON complet
journalisé, sans aucun attribut d'authentification).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from tests.conftest import API, Api


@pytest.fixture()
def _backdate_engine() -> Engine:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        engine.dispose()


def _plan_with_quota(client: TestClient, api: Api, **quotas: int | None) -> str:
    body: dict[str, object] = {
        "code": f"SUP_{uuid.uuid4().hex[:8].upper()}",
        "name": "Plan Support",
        "status": "ACTIVE",
        **quotas,
    }
    plan = client.post(f"{API}/platform/saas-plans", headers=api.platform(), json=body)
    assert plan.status_code == 201, plan.text
    return plan.json()["plan_id"]


def _create_vehicle(client: TestClient, admin_headers: dict[str, str], site_id: str, fleet: str) -> dict:
    category = client.get(f"{API}/vehicle-categories", headers=admin_headers).json()[0]
    created = client.post(
        f"{API}/vehicles",
        headers=admin_headers,
        json={
            "site_id": site_id,
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": fleet,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _overview(client: TestClient, api: Api, tenant_id: str) -> dict:
    resp = client.get(f"{API}/platform/tenants/{tenant_id}/overview", headers=api.platform())
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_platform_overview_aggregates(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _plan_with_quota(
        client, api, max_users=10, max_sites=5, max_vehicles=8, max_gps_trackers=4
    )
    created_sub = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json={"plan_id": plan_id}
    )
    assert created_sub.status_code == 201, created_sub.text
    invoice = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={
            "tax_rate_bp": 0,
            "lines": [{"description": "Mise en service", "quantity": 1, "unit_price_gnf": 5_000_000}],
        },
    )
    assert invoice.status_code == 201, invoice.text

    overview = _overview(client, api, str(t.tenant_id))
    assert overview["tenant"]["tenant_id"] == str(t.tenant_id)
    assert overview["tenant"]["status"] == "ACTIVE"
    subscription = overview["subscription"]
    assert subscription is not None
    assert subscription["status"] == "ACTIVE" and subscription["effective_status"] == "ACTIVE"
    assert subscription["plan"]["code"].startswith("SUP_")
    assert subscription["plan"]["max_vehicles"] == 8
    usage = {row["field"]: row for row in overview["usage"]}
    assert usage["max_users"]["usage"] == 1 and usage["max_users"]["limit"] == 10
    assert usage["max_sites"]["usage"] == 2 and usage["max_sites"]["limit"] == 5
    assert usage["max_vehicles"]["usage"] == 0 and usage["max_vehicles"]["limit"] == 8
    assert usage["max_gps_trackers"]["usage"] == 0
    assert overview["users"]["active"] == 1 and overview["users"]["invited"] == 0
    assert [inv["number"] for inv in overview["invoices"]] == [invoice.json()["number"]]
    assert overview["invoices"][0]["total_gnf"] == 5_000_000


def test_platform_overview_without_subscription_and_quota_free(client: TestClient, api: Api) -> None:
    t = api.tenant()
    overview = _overview(client, api, str(t.tenant_id))
    assert overview["subscription"] is None
    # Sans plan, aucune limite n'est bornée (NULL = illimité) mais l'usage reste compté.
    usage = {row["field"]: row for row in overview["usage"]}
    assert usage["max_sites"]["usage"] == 2 and usage["max_sites"]["limit"] is None
    assert usage["max_users"]["usage"] == 1


def test_platform_overview_trial_expired_effective_status(
    client: TestClient, api: Api, _backdate_engine: Engine
) -> None:
    """Un essai daté échu s'affiche EXPIRED dans la vue support (statut stocké inchangé)."""
    t = api.tenant()
    platform = api.platform()
    plan_id = _plan_with_quota(client, api)
    trial = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers=platform,
        json={"plan_id": plan_id, "trial_days": 7},
    )
    assert trial.status_code == 201, trial.text
    sub_id = trial.json()["subscription_id"]

    # L'essai est rendu échu en base (created_at antidaté en cohérence avec la contrainte
    # ck_ts_trial_ends) — la vue support ne doit voir QUE le statut effectif changer.
    with _backdate_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
        conn.execute(
            text(
                "UPDATE tenant_subscription SET trial_ends_at = now() - interval '1 day',"
                " created_at = now() - interval '8 days' WHERE subscription_id = :s"
            ),
            {"s": sub_id},
        )
        conn.commit()

    overview = _overview(client, api, str(t.tenant_id))
    assert overview["subscription"] is not None
    assert overview["subscription"]["status"] == "TRIAL"
    assert overview["subscription"]["effective_status"] == "EXPIRED"


def test_platform_overview_unknown_tenant_404(client: TestClient, api: Api) -> None:
    resp = client.get(f"{API}/platform/tenants/{uuid.uuid4()}/overview", headers=api.platform())
    assert (resp.status_code, resp.json()["code"]) == (404, "NOT_FOUND")


def test_platform_overview_role_guard(client: TestClient, api: Api) -> None:
    t = api.tenant()
    resp = client.get(f"{API}/platform/tenants/{t.tenant_id}/overview", headers=t.admin.headers)
    assert (resp.status_code, resp.json()["code"]) == (403, "PERMISSION_DENIED")


def test_onboarding_checklist_progress(client: TestClient, api: Api) -> None:
    t = api.tenant()  # le conftest crée 2 sites et 1 administrateur actif
    headers = t.admin.headers

    def _checklist() -> dict:
        resp = client.get(f"{API}/tenant/onboarding", headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    initial = _checklist()
    steps = {step["key"]: step for step in initial["steps"]}
    assert set(steps) == {"subscription", "users", "sites", "vehicles", "gps_trackers"}
    assert steps["sites"]["done"] and steps["sites"]["count"] == 2
    assert not steps["users"]["done"] and steps["users"]["count"] == 1 and steps["users"]["target"] == 2
    assert not steps["subscription"]["done"] and not steps["vehicles"]["done"]
    assert initial["done_count"] == 1 and initial["progress_percent"] == 20

    # La progression suit l'état réel : abonnement vivant, deuxième utilisateur, véhicule, traceur.
    platform = api.platform()
    plan_id = _plan_with_quota(client, api)
    subscribed = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform, json={"plan_id": plan_id}
    )
    assert subscribed.status_code == 201, subscribed.text
    colleague = api.user(t, "OPS_MANAGER", scope="TENANT")
    assert colleague.headers
    vehicle = _create_vehicle(client, headers, str(t.sites["S1"]), "SUP-001")
    bound = client.post(
        f"{API}/vehicles/{vehicle['vehicle_id']}/gps/tracker",
        headers=headers,
        json={"device_id": "gps-sup-0001"},
    )
    assert bound.status_code == 201, bound.text

    final = _checklist()
    assert final["done_count"] == 5 and final["progress_percent"] == 100
    assert all(step["done"] for step in final["steps"])


def test_onboarding_readable_by_other_tenant_roles(client: TestClient, api: Api) -> None:
    t = api.tenant()
    direction = api.user(t, "DIRECTION")
    resp = client.get(f"{API}/tenant/onboarding", headers=direction.headers)
    assert resp.status_code == 200 and resp.json()["total"] == 5


def test_export_contains_data_without_secrets(client: TestClient, api: Api) -> None:
    t = api.tenant()
    headers = t.admin.headers
    vehicle = _create_vehicle(client, headers, str(t.sites["S1"]), "SUP-EXP-01")
    invoice = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=api.platform(),
        json={
            "tax_rate_bp": 1800,
            "lines": [{"description": "Abonnement mensuel", "quantity": 1, "unit_price_gnf": 9_000_000}],
        },
    )
    assert invoice.status_code == 201, invoice.text

    exported = client.get(f"{API}/tenant/export", headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.headers["Content-Type"].startswith("application/json")
    assert "attachment" in exported.headers["Content-Disposition"]
    assert f"export-minefleet-{t.code}-" in exported.headers["Content-Disposition"]
    payload = exported.json()
    assert payload["format_version"] == 1
    assert payload["tenant"]["code"] == t.code
    assert {site["code"] for site in payload["sites"]} == {"S1", "S2"}
    assert [user["email"] for user in payload["users"]] == [t.admin.email]
    assert payload["users"][0]["roles"] == ["TENANT_ADMIN"]
    assert [v["fleet_number"] for v in payload["vehicles"]] == ["SUP-EXP-01"]
    assert payload["vehicles"][0]["vehicle_id"] == vehicle["vehicle_id"]
    assert [inv["number"] for inv in payload["invoices"]] == [invoice.json()["number"]]
    assert payload["invoices"][0]["lines"][0]["description"] == "Abonnement mensuel"
    # Aucun attribut d'authentification ni secret dans l'export.
    raw = exported.text
    for forbidden in ("password_hash", "mfa_secret", "mfa_recovery", "token", "argon"):
        assert forbidden not in raw, forbidden


def test_export_journalise_et_role_guard(client: TestClient, api: Api) -> None:
    t = api.tenant()
    first = client.get(f"{API}/tenant/export", headers=t.admin.headers)
    assert first.status_code == 200
    events = client.get(f"{API}/audit-events", headers=t.admin.headers).json()["items"]
    assert any(event["action"] == "tenant.export" for event in events)

    # Réversibilité : décision réservée à l'administrateur de la société.
    direction = api.user(t, "DIRECTION")
    refused = client.get(f"{API}/tenant/export", headers=direction.headers)
    assert (refused.status_code, refused.json()["code"]) == (403, "PERMISSION_DENIED")
