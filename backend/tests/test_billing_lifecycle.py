"""Cycle de vie des quotas et des factures — vérifications des parcours SaaS complets.

Complète les lots SaaS existants (Phase 2 de la mission) : changement d'offre avec des
ressources existantes supérieures au nouveau quota (aucune suppression automatique),
suspension/réactivation de l'abonnement (borne maintenue), essai expiré (borne effective
maintenue), opérations concurrentes (deux provisionnements ne peuvent pas franchir la
borne ensemble), unicité de la numérotation de factures sous concurrence, arrondi de la
taxe et absence de toute route de modification d'une facture finalisée.
"""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from tests.conftest import API, Api

# --- Fabriques locales --------------------------------------------------------------------------------


def _plan(client: TestClient, api: Api, **fields: object) -> str:
    body: dict[str, object] = {
        "code": f"LCV_{uuid.uuid4().hex[:8].upper()}",
        "name": "Plan Cycle de vie",
        "status": "ACTIVE",
        **fields,
    }
    plan = client.post(f"{API}/platform/saas-plans", headers=api.platform(), json=body)
    assert plan.status_code == 201, plan.text
    return plan.json()["plan_id"]


def _subscribe(client: TestClient, api: Api, tenant_id: str, plan_id: str) -> dict:  # type: ignore[type-arg]
    created = client.post(
        f"{API}/platform/tenants/{tenant_id}/subscriptions",
        headers=api.platform(),
        json={"plan_id": plan_id},
    )
    assert created.status_code == 201, created.text
    return created.json()


def _category(client: TestClient, t: object) -> dict:  # type: ignore[type-arg]
    return client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0]  # type: ignore[attr-defined]


def _vehicle(client: TestClient, t: object, category: dict, fleet: str):  # type: ignore[type-arg]
    return client.post(
        f"{API}/vehicles",
        headers=t.admin.headers,  # type: ignore[attr-defined]
        json={
            "site_id": str(t.sites["S1"]),  # type: ignore[attr-defined]
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": fleet,
        },
    )


# --- Changement d'offre : aucune suppression automatique des ressources existantes ---------------------


def test_downgrade_keeps_resources_and_blocks_new_ones(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    platform = api.platform()
    large = _plan(client, api)  # aucun quota véhicule : illimité
    _subscribe(client, api, str(t.tenant_id), large)
    category = _category(client, t)
    for fleet in ("LCV-D1", "LCV-D2", "LCV-D3"):
        assert _vehicle(client, t, category, fleet).status_code == 201

    # Passage à une offre inférieure (borne 2) : l'abonnement précédent est remplacé, l'historique conservé.
    small = _plan(client, api, max_vehicles=2)
    replaced = _subscribe(client, api, str(t.tenant_id), small)
    assert replaced["status"] == "ACTIVE"

    # Aucune suppression automatique : les trois véhicules restent lisibles et exploitables.
    listed = client.get(f"{API}/vehicles", headers=t.admin.headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 3

    refused = _vehicle(client, t, category, "LCV-D4")
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED"), refused.text
    detail = refused.json()["details"][0]
    assert (detail["field"], detail["limit"], detail["usage"]) == ("max_vehicles", 2, 3)

    # Retour à une offre supérieure : la création redevient possible, aucune donnée à restaurer.
    _subscribe(client, api, str(t.tenant_id), large)
    assert _vehicle(client, t, category, "LCV-D4").status_code == 201

    history = client.get(f"{API}/platform/tenants/{t.tenant_id}/subscriptions", headers=platform)
    assert history.status_code == 200, history.text
    statuses = [item["status"] for item in history.json()["items"]]
    assert statuses.count("CANCELLED") == 2 and statuses.count("ACTIVE") == 1


# --- Suspension / réactivation : la borne reste effective ---------------------------------------------


def test_suspension_keeps_quota_and_reactivation_resumes(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    platform = api.platform()
    plan_id = _plan(client, api, max_vehicles=1)
    subscription = _subscribe(client, api, str(t.tenant_id), plan_id)
    category = _category(client, t)
    assert _vehicle(client, t, category, "LCV-S1").status_code == 201

    suspended = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{subscription['subscription_id']}/suspend",
        headers={**platform, "If-Match": f'"{subscription["row_version"]}"'},
        json={"reason": "Suspension de test"},
    )
    assert suspended.status_code == 200, suspended.text

    # SUSPENDED reste un abonnement vivant : la borne du plan s'applique encore (aucun contournement).
    refused = _vehicle(client, t, category, "LCV-S2")
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED")

    reactivated = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions/{subscription['subscription_id']}/reactivate",
        headers={**platform, "If-Match": f'"{suspended.json()["row_version"]}"'},
        json={"reason": "Réactivation de test"},
    )
    assert reactivated.status_code == 200 and reactivated.json()["status"] == "ACTIVE"

    # Usage inchangé (1 = borne 1) : la borne s'applique toujours après réactivation.
    still_refused = _vehicle(client, t, category, "LCV-S3")
    assert (still_refused.status_code, still_refused.json()["code"]) == (422, "QUOTA_EXCEEDED")


# --- Essai expiré : la borne effective reste appliquée -------------------------------------------------


@pytest.fixture()
def _past_trial_engine() -> Iterator[Engine]:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        engine.dispose()


def test_expired_trial_keeps_quota_enforced(client: TestClient, api: Api, _past_trial_engine: Engine) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan(client, api, max_sites=1)
    trial = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/subscriptions",
        headers=api.platform(),
        json={"plan_id": plan_id, "trial_days": 7},
    )
    assert trial.status_code == 201, trial.text

    # L'essai est rendu échu en base (antidatage cohérent avec ck_ts_trial_ends), comme dans le lot 3 :
    # aucune API de retournement temporel volontaire.
    with _past_trial_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
        conn.execute(
            text(
                "UPDATE tenant_subscription SET trial_ends_at = now() - interval '1 day',"
                " created_at = now() - interval '8 days' WHERE subscription_id = :s"
            ),
            {"s": trial.json()["subscription_id"]},
        )
        conn.commit()

    own = client.get(f"{API}/tenant/subscription", headers=t.admin.headers)
    assert own.status_code == 200, own.text
    assert own.json()["status"] == "TRIAL" and own.json()["effective_status"] == "EXPIRED"

    # Un essai expiré reste vivant pour l'application des quotas : la borne s'applique encore.
    refused = client.post(
        f"{API}/sites",
        headers=t.admin.headers,
        json={"code": "S2", "name": "Site S2", "site_type": "MINE"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "QUOTA_EXCEEDED"), refused.text
    detail = refused.json()["details"][0]
    assert (detail["field"], detail["limit"], detail["usage"]) == ("max_sites", 1, 1)

    # Aucune purge ni suppression automatique des données existantes.
    listed = client.get(f"{API}/sites", headers=t.admin.headers)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1


# --- Opérations concurrentes : la borne ne peut pas être franchie --------------------------------------


def test_concurrent_creation_cannot_exceed_vehicle_quota(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("S1",))
    plan_id = _plan(client, api, max_vehicles=1)
    _subscribe(client, api, str(t.tenant_id), plan_id)
    category = _category(client, t)
    barrier = Barrier(2)

    def create(fleet: str) -> int:
        barrier.wait(timeout=10)
        return _vehicle(client, t, category, fleet).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(create, ("LCV-R1", "LCV-R2")))
    assert sorted(codes) == [201, 422], codes

    listed = client.get(f"{API}/vehicles", headers=t.admin.headers)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1


# --- Facturation : numérotation concurrente, arrondi de taxe, immutabilité -----------------------------


def test_concurrent_invoice_creation_numbers_are_unique(client: TestClient, api: Api) -> None:
    t = api.tenant()
    plan_id = _plan(client, api, price_monthly_gnf=7_500_000)
    subscription = _subscribe(client, api, str(t.tenant_id), plan_id)
    platform = api.platform()
    barrier = Barrier(2)

    def create(_: None) -> object:
        barrier.wait(timeout=10)
        return client.post(
            f"{API}/platform/tenants/{t.tenant_id}/invoices",
            headers=platform,
            json={"subscription_id": subscription["subscription_id"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (None, None)))
    assert all(result.status_code == 201 for result in results), [r.text for r in results]
    numbers = [result.json()["number"] for result in results]
    assert len(set(numbers)) == 2, numbers  # incrémentation atomique : aucune collision
    assert all(number.startswith("MF-") for number in numbers)


def test_invoice_tax_rounding_half_up(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()

    def create(tax_rate_bp: int, unit_price_gnf: int) -> dict:  # type: ignore[type-arg]
        resp = client.post(
            f"{API}/platform/tenants/{t.tenant_id}/invoices",
            headers=platform,
            json={
                "tax_rate_bp": tax_rate_bp,
                "lines": [
                    {
                        "description": "Abonnement MineFleet 360 (test arrondi)",
                        "quantity": 1,
                        "unit_price_gnf": unit_price_gnf,
                    }
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    # 0,01 % de 5 000 GNF = 0,5 GNF : arrondi à l'unité la plus proche avec demi-unité vers le haut.
    half = create(1, 5_000)
    assert (half["subtotal_gnf"], half["tax_gnf"], half["total_gnf"]) == (5_000, 1, 5_001)

    # 0,01 % de 1 000 GNF = 0,1 GNF : arrondi vers le bas.
    down = create(1, 1_000)
    assert (down["subtotal_gnf"], down["tax_gnf"], down["total_gnf"]) == (1_000, 0, 1_000)

    # 100 % : taxe exacte, aucun écart d'arrondi.
    full = create(10_000, 2_500_000)
    assert (full["subtotal_gnf"], full["tax_gnf"], full["total_gnf"]) == (2_500_000, 2_500_000, 5_000_000)


def test_finalized_invoice_has_no_modification_endpoint(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    created = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices",
        headers=platform,
        json={
            "tax_rate_bp": 1_800,
            "lines": [
                {
                    "description": "Abonnement MineFleet 360 (test immutabilité)",
                    "quantity": 1,
                    "unit_price_gnf": 7_500_000,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["invoice_id"]
    issued = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/invoices/{invoice_id}/issue",
        headers={**platform, "If-Match": '"1"'},
    )
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED", issued.text

    # Une facture finalisée n'a aucune route de modification : PATCH/PUT/DELETE sont hors surface API,
    # les lignes et les montants figés ne sont altérables par aucun appel.
    base = f"{API}/platform/tenants/{t.tenant_id}/invoices/{invoice_id}"
    assert client.patch(base, headers=platform, json={"status": "DRAFT"}).status_code == 405
    assert client.put(base, headers=platform, json={"status": "DRAFT"}).status_code == 405
    assert client.delete(base, headers=platform).status_code == 405

    # VOIDED reste terminal : aucun retour arrière possible après annulation.
    voided = client.post(
        f"{base}/void",
        headers={**platform, "If-Match": f'"{issued.json()["row_version"]}"'},
        json={"reason": "Annulation de test"},
    )
    assert voided.status_code == 200 and voided.json()["status"] == "VOIDED", voided.text
    reissue = client.post(
        f"{base}/issue", headers={**platform, "If-Match": f'"{voided.json()["row_version"]}"'}
    )
    assert (reissue.status_code, reissue.json()["code"]) == (409, "STATE_TRANSITION_INVALID")
