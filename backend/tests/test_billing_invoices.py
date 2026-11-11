"""Lot 3 commercialisation SaaS — facturation paramétrable sans activation de paiement.

Couvre : création (lignes fournies ou préremplies depuis le tarif du plan), numérotation
plateforme atomique (MF-<année>-<numéro>), montants GNF figés à la création (une modification
ultérieure du plan ne change pas une facture émise), cycle DRAFT → ISSUED → VOIDED (terminal),
conflits de version, indiscernabilité inter-tenant (404), refus des rôles non autorisés,
statut effectif d'un essai expiré calculé à la lecture (aucune écriture en base).
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from tests.conftest import API, Api


def _priced_plan_id(client: TestClient, api: Api, price: int | None = 15_000_000) -> str:
    body: dict[str, object] = {
        "code": f"INV_{uuid.uuid4().hex[:8].upper()}",
        "name": "Plan Facturé",
        "status": "ACTIVE",
    }
    if price is not None:
        body["price_monthly_gnf"] = price
        body["billing_period"] = "MONTHLY"
    plan = client.post(f"{API}/platform/saas-plans", headers=api.platform(), json=body)
    assert plan.status_code == 201, plan.text
    return plan.json()["plan_id"]


def _active_subscription(client: TestClient, api: Api, tenant_id: str, plan_id: str) -> dict:
    created = client.post(
        f"{API}/platform/tenants/{tenant_id}/subscriptions",
        headers=api.platform(),
        json={"plan_id": plan_id},
    )
    assert created.status_code == 201, created.text
    return created.json()


def _invoice_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "tax_rate_bp": 1800,
        "lines": [
            {
                "description": "Abonnement MineFleet 360 — mensuel",
                "quantity": 1,
                "unit_price_gnf": 15_000_000,
            },
            {"description": "Frais de mise en service", "quantity": 2, "unit_price_gnf": 250_000},
        ],
    }
    body.update(overrides)
    return body


def test_create_invoice_amounts_and_numbering(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    first = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=platform, json=_invoice_body()
    )
    assert first.status_code == 201, first.text
    invoice = first.json()
    assert invoice["status"] == "DRAFT" and invoice["currency"] == "GNF"
    year = datetime.now(UTC).year
    assert invoice["number"].startswith(f"MF-{year}-")
    # 1 × 15 000 000 + 2 × 250 000 = 15 500 000 ; taxe 18 % = 2 790 000 (arrondi au franc).
    assert invoice["subtotal_gnf"] == 15_500_000
    assert invoice["tax_gnf"] == 2_790_000
    assert invoice["total_gnf"] == 18_290_000

    second = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=platform, json=_invoice_body()
    )
    assert second.status_code == 201
    assert second.json()["number"] != invoice["number"]

    detail = client.get(
        f"{API}/platform/tenants/{t.tenant_id}/invoices/{invoice['invoice_id']}", headers=platform
    )
    assert detail.status_code == 200, detail.text
    lines = detail.json()["lines"]
    assert [line["amount_gnf"] for line in lines] == [15_000_000, 500_000]
    assert detail.headers["ETag"] == f'"{invoice["row_version"]}"'


def test_invoice_from_priced_plan_and_tenant_read(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _priced_plan_id(client, api, price=12_000_000)
    subscription = _active_subscription(client, api, str(t.tenant_id), plan_id)
    created = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={"subscription_id": subscription["subscription_id"], "tax_rate_bp": 0},
    )
    assert created.status_code == 201, created.text
    assert created.json()["total_gnf"] == 12_000_000  # ligne préremplie depuis le tarif du plan

    # Lecture par la société : SES factures seulement, détail compris.
    own = client.get(f"{API}/tenant/invoices", headers=t.admin.headers)
    assert own.status_code == 200 and own.json()["total"] == 1
    assert own.json()["items"][0]["invoice_id"] == created.json()["invoice_id"]
    own_detail = client.get(f"{API}/tenant/invoices/{created.json()['invoice_id']}", headers=t.admin.headers)
    assert own_detail.status_code == 200
    assert own_detail.json()["lines"][0]["description"].startswith("Abonnement MineFleet 360")


def test_unpriced_plan_requires_explicit_lines(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _priced_plan_id(client, api, price=None)
    subscription = _active_subscription(client, api, str(t.tenant_id), plan_id)
    resp = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={"subscription_id": subscription["subscription_id"]},
    )
    assert (resp.status_code, resp.json()["code"]) == (422, "PLAN_NOT_PRICED")
    empty = client.post(f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=platform, json={})
    assert (empty.status_code, empty.json()["code"]) == (422, "INVOICE_LINES_REQUIRED")


def test_amounts_frozen_after_plan_price_change(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _priced_plan_id(client, api, price=10_000_000)
    subscription = _active_subscription(client, api, str(t.tenant_id), plan_id)
    created = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={"subscription_id": subscription["subscription_id"]},
    )
    assert created.status_code == 201
    # Une facture est un document figé : la modification du tarif du plan ne la change pas.
    patched = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"1"'},
        json={"price_monthly_gnf": 99_000_000},
    )
    assert patched.status_code == 200, patched.text
    own = client.get(f"{API}/tenant/invoices/{created.json()['invoice_id']}", headers=t.admin.headers)
    assert own.json()["total_gnf"] == 10_000_000


def test_issue_then_void_terminal(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    invoice = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=platform, json=_invoice_body()
    ).json()
    base = f"{API}/platform/tenants/{t.tenant_id}/invoices/{invoice['invoice_id']}"

    conflict = client.post(f"{base}/issue", headers={**platform, "If-Match": '"999"'})
    assert (conflict.status_code, conflict.json()["code"]) == (409, "VERSION_CONFLICT")

    issued = client.post(f"{base}/issue", headers={**platform, "If-Match": '"1"'})
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED"
    assert issued.json()["issued_at"] is not None

    reissue = client.post(f"{base}/issue", headers={**platform, "If-Match": issued.headers["ETag"]})
    assert (reissue.status_code, reissue.json()["code"]) == (409, "STATE_TRANSITION_INVALID")

    no_reason = client.post(f"{base}/void", headers={**platform, "If-Match": issued.headers["ETag"]}, json={})
    assert no_reason.status_code == 422

    voided = client.post(
        f"{base}/void",
        headers={**platform, "If-Match": issued.headers["ETag"]},
        json={"reason": "Erreur de saisie — émise deux fois"},
    )
    assert voided.status_code == 200 and voided.json()["status"] == "VOIDED"
    assert voided.json()["voided_at"] is not None

    # VOIDED est terminal : plus aucune transition, quelle que soit la version fournie.
    terminal = client.post(f"{base}/issue", headers={**platform, "If-Match": voided.headers["ETag"]})
    assert (terminal.status_code, terminal.json()["code"]) == (409, "STATE_TRANSITION_INVALID")


def test_invoice_from_cancelled_subscription(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    plan_id = _priced_plan_id(client, api)
    subscription = _active_subscription(client, api, str(t.tenant_id), plan_id)
    cancelled = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{subscription['subscription_id']}/cancel",
        headers={**platform, "If-Match": '"1"'},
        json={"reason": "Société résilie son abonnement"},
    )
    assert cancelled.status_code == 200
    resp = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={"subscription_id": subscription["subscription_id"]},
    )
    assert (resp.status_code, resp.json()["code"]) == (422, "SUBSCRIPTION_CANCELLED")


def test_cross_tenant_invoice_is_indistinguishable_from_missing(client: TestClient, api: Api) -> None:
    a, b = api.tenant(), api.tenant()
    platform = api.platform()
    invoice = client.post(
        f"{API}/platform/tenants/{a.tenant_id}/invoices", headers=platform, json=_invoice_body()
    ).json()
    foreign = client.get(f"{API}/tenant/invoices/{invoice['invoice_id']}", headers=b.admin.headers)
    missing = client.get(f"{API}/tenant/invoices/{uuid.uuid4()}", headers=b.admin.headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"] == "NOT_FOUND"


def test_read_permissions_per_role(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    invoice = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=platform, json=_invoice_body()
    ).json()
    allowed = {role: api.user(t, role) for role in ("TENANT_ADMIN", "DIRECTION", "FINANCE", "AUDITOR")}
    for role, account in allowed.items():
        listing = client.get(f"{API}/tenant/invoices", headers=account.headers)
        assert listing.status_code == 200, (role, listing.text)
        assert listing.json()["total"] == 1
        detail = client.get(f"{API}/tenant/invoices/{invoice['invoice_id']}", headers=account.headers)
        assert detail.status_code == 200, (role, detail.text)
    denied = {
        "OPS_MANAGER": api.user(t, "OPS_MANAGER"),
        "HR": api.user(t, "HR"),
        "WORKSHOP_CHIEF": api.user(t, "WORKSHOP_CHIEF"),
    }
    for role, account in denied.items():
        refused = client.get(f"{API}/tenant/invoices", headers=account.headers)
        assert (refused.status_code, refused.json()["code"]) == (403, "PERMISSION_DENIED"), role
    # Les routes plateforme restent réservées à la plateforme, y compris en lecture.
    tenant_admin = allowed["TENANT_ADMIN"]
    platform_refused = client.get(
        f"{API}/platform/tenants/{t.tenant_id}/invoices", headers=tenant_admin.headers
    )
    assert (platform_refused.status_code, platform_refused.json()["code"]) == (403, "PERMISSION_DENIED")


def test_unknown_tenant_is_404(client: TestClient, api: Api) -> None:
    resp = client.post(
        f"{API}/platform/tenants/{uuid.uuid4()}/invoices", headers=api.platform(), json=_invoice_body()
    )
    assert (resp.status_code, resp.json()["code"]) == (404, "NOT_FOUND")


@pytest.fixture()
def _past_trial_engine() -> Engine:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        engine.dispose()


def test_expired_trial_is_effective_status_without_write(
    client: TestClient, api: Api, _past_trial_engine: Engine
) -> None:
    t = api.tenant()
    plan_id = _priced_plan_id(client, api)
    subscription = _active_subscription(
        client, api, str(t.tenant_id), plan_id
    )  # ACTIVE direct, remplacé ensuite par un essai expiré
    del subscription
    trial = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers=api.platform(),
        json={"plan_id": plan_id, "trial_days": 7},
    )
    assert trial.status_code == 201, trial.text
    sub_id = trial.json()["subscription_id"]

    # L'essai est rendu échue en base (aucune API de retournement temporel volontaire) :
    # created_at est antidaté en cohérence avec la contrainte ck_ts_trial_ends (essai postérieur
    # à la création) — l'API de lecture ne doit voir QUE le statut effectif changer.
    with _past_trial_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
        conn.execute(
            text(
                "UPDATE tenant_subscription SET trial_ends_at = now() - interval '1 day',"
                " created_at = now() - interval '8 days' WHERE subscription_id = :s"
            ),
            {"s": sub_id},
        )
        conn.commit()

    own = client.get(f"{API}/tenant/subscription", headers=t.admin.headers)
    assert own.status_code == 200
    body = own.json()
    assert body["status"] == "TRIAL" and body["effective_status"] == "EXPIRED"

    platform = api.platform()
    history = client.get(f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform)
    assert history.status_code == 200
    target = next(item for item in history.json()["items"] if item["subscription_id"] == sub_id)
    assert target["status"] == "TRIAL" and target["effective_status"] == "EXPIRED"

    # L'essai expiré reste transitionnable (le statut stocké n'a pas été altéré) : activation OK.
    # row_version a progressé (tg_touch incrémente à chaque UPDATE, y compris l'antidatage ci-dessus).
    activated = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{sub_id}/activate",
        headers={**platform, "If-Match": f'"{target["row_version"]}"'},
    )
    assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE"
    after = client.get(f"{API}/tenant/subscription", headers=t.admin.headers).json()
    assert after["effective_status"] == "ACTIVE"


def test_trial_expiry_refreshed_plan_pricing_visible(client: TestClient, api: Api) -> None:
    """Le tarif du plan est visible dans la vue société (paramétrage lot 3)."""
    t = api.tenant()
    plan_id = _priced_plan_id(client, api, price=7_500_000)
    _active_subscription(client, api, str(t.tenant_id), plan_id)
    own = client.get(f"{API}/tenant/subscription", headers=t.admin.headers)
    assert own.status_code == 200
    assert own.json()["plan"]["price_monthly_gnf"] == 7_500_000
    assert own.json()["plan"]["billing_period"] == "MONTHLY"
