"""Générateur DEMO : chargement par les services, cohérence recalculée, isolation, droits, garde-fous."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.cli import main
from app.core.config import get_settings
from app.demo import credentials, generator, guards
from app.demo.catalog import SITE_ROLES, TENANT_ROLES, TENANTS
from app.demo.guards import DemoRefused
from app.demo.verify import verify_demo
from tests.conftest import API, Api

ANCHOR = date(2026, 10, 1)


@contextmanager
def dedicated_database() -> Iterator[None]:
    """La base de test partagée contient les tenants non DEMO des autres tests : le verrou « base dédiée »
    est vérifié à part (test_refused_*) et neutralisé seulement le temps d'un appel."""
    mp = pytest.MonkeyPatch()
    mp.setattr(guards, "non_demo_customer_tenants", lambda: [])
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def demo(database: None) -> generator.DemoReport:
    with dedicated_database():
        return generator.seed_demo(profile="qa", seed=42, anchor=ANCHOR)


def test_qa_profile_covers_every_role_and_module(demo: generator.DemoReport) -> None:
    c = demo.counts
    assert c["tenants"] == 3 and c["sites"] == 5
    per_tenant_users = {t.code: 1 + len(TENANT_ROLES) + len(t.sites) * len(SITE_ROLES) for t in TENANTS}
    assert c["users"] == sum(per_tenant_users.values())
    roles = {(cred.tenant, cred.role) for cred in demo.credentials}
    for spec in TENANTS:  # les 13 rôles client de la matrice, sans rôle inventé
        assert {r for t, r in roles if t == spec.code} == {"TENANT_ADMIN", *TENANT_ROLES, *SITE_ROLES}
    for key in (
        "vehicles",
        "drivers",
        "assignments",
        "missions",
        "rotations",
        "weighings",
        "fuel_issues",
        "work_orders_closed",
        "work_orders_open",
        "hse_incidents",
        "hse_actions",
    ):
        assert c.get(key, 0) > 0, key
    # Scénarios négatifs présents : panne ouverte, mission bloquée, pesée en attente, incident critique.
    assert c["work_orders_open"] == c["missions_suspended"] == c["weighings_pending"] == 3
    assert c["hse_incidents_open"] == 3
    # Lot 2 : coûts valorisés, compteurs, pièces sur OT, pneus, inspections HSE (dont une non conforme).
    for key in (
        "fuel_purchases",
        "labour_rates",
        "meter_readings",
        "part_receipts",
        "part_issues",
        "tyres",
        "tyre_inspections",
        "tyres_scrapped",
        "hse_checklists",
        "hse_inspections",
    ):
        assert c.get(key, 0) > 0, key
    # Lot 3 : traceurs, zones et positions GPS calées sur les rotations.
    assert c["gps_trackers"] == c["assignments"] and c["geofences"] == 5 * c["sites"]
    assert c["gps_positions"] > 1000
    assert c["hse_inspections_non_compliant"] == 3 and "fuel_receipts" not in c
    # Jour J : des missions en cours et planifiées (la liste « en cours » n'est pas vide à l'ouverture).
    assert c["missions_live"] > 0 and c["missions_planned"] == 3
    # Les mots de passe ne dérivent pas de la graine (jamais reproductibles) et sont tous distincts.
    passwords = [cred.password for cred in demo.credentials]
    assert len(set(passwords)) == len(passwords)


def test_verify_recomputes_every_indicator(demo: generator.DemoReport) -> None:
    checks = verify_demo(ANCHOR)
    failed = [c for c in checks if not c.ok]
    assert not failed, failed
    names = {c.name for c in checks}
    assert any("isolation" in n for n in names) and any("tonnage" in n for n in names)
    assert any("main-d'œuvre" in n for n in names) and any("pneus" in n for n in names)
    assert any(n.startswith("GPS") for n in names)
    assert len({c.tenant for c in checks}) == 3


def test_reseed_is_idempotent(demo: generator.DemoReport) -> None:
    with dedicated_database():
        again = generator.seed_demo(profile="qa", seed=42, anchor=ANCHOR)
    assert sorted(again.skipped) == sorted(t.code for t in TENANTS)
    assert again.counts == {} and again.credentials == []


def test_demo_accounts_use_real_api_and_real_permissions(
    demo: generator.DemoReport, client: TestClient
) -> None:
    api = Api(client, None)  # type: ignore[arg-type]
    creds = {(c.tenant, c.role, c.site): c for c in demo.credentials}
    ops = creds[("demo-bauxite", "OPS_MANAGER", None)]
    headers = api.login("demo-bauxite", ops.email, ops.password)
    vehicles = client.get(f"{API}/vehicles", headers=headers, params={"page_size": 100})
    assert vehicles.status_code == 200
    numbers = {v["fleet_number"] for v in vehicles.json()["items"]}
    assert "DEMO-CAM-001" in numbers and all(n.startswith("DEMO-") for n in numbers)
    missions = client.get(f"{API}/missions", headers=headers, params={"page_size": 5})
    assert missions.status_code == 200 and missions.json()["items"]
    # Le conducteur n'a pas accès au parc ; le compte d'une société est refusé dans une autre.
    driver = creds[("demo-bauxite", "DRIVER", "BOKE-MINE")]
    assert (
        client.get(
            f"{API}/vehicles", headers=api.login("demo-bauxite", driver.email, driver.password)
        ).status_code
        == 403
    )
    refused = client.post(
        f"{API}/auth/login", json={"workspace_code": "demo-tlm", "email": ops.email, "password": ops.password}
    )
    assert refused.status_code == 401


def test_reset_credentials_rotates_demo_passwords_only(
    demo: generator.DemoReport, client: TestClient, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    old = next(c for c in demo.credentials if c.tenant == "demo-tlm" and c.role == "HSE")
    with dedicated_database():
        fresh = {c.email: c for c in credentials.reset_credentials("demo-tlm")}
    assert old.email in fresh and fresh[old.email].password != old.password
    login = lambda pwd: client.post(  # noqa: E731
        f"{API}/auth/login", json={"workspace_code": "demo-tlm", "email": old.email, "password": pwd}
    )
    assert login(old.password).status_code == 401
    assert login(fresh[old.email].password).status_code == 200
    with dedicated_database(), pytest.raises(DemoRefused):
        credentials.reset_credentials("fictif-minier")


def test_credentials_file_is_private_and_never_overwritten(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = str(tmp_path / "comptes.tsv")
    rows = [generator.Credential("demo-tlm", "HSE", None, "hse@demo-tlm.example.com", "Demo-x")]
    assert credentials.write_credentials(path, rows) == 1
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with pytest.raises(FileExistsError):
        credentials.write_credentials(path, rows)
    with pytest.raises(DemoRefused):
        credentials.ensure_new_file(path)


def test_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"env": "production"})
    with pytest.raises(DemoRefused, match="production"):
        generator.seed_demo(settings=settings)


def test_refused_when_database_holds_a_non_demo_customer(api: Api) -> None:
    api.tenant(sites=("S1",))  # un vrai client (is_demo = false) suffit à interdire toute commande DEMO
    assert guards.non_demo_customer_tenants()
    with pytest.raises(DemoRefused, match="non DEMO"):
        generator.seed_demo()
    with pytest.raises(DemoRefused):
        credentials.reset_credentials("demo-tlm")


def test_cli_verify_and_refusal(
    demo: generator.DemoReport, api: Api, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:  # type: ignore[no-untyped-def]
    assert main(["demo", "verify", "--anchor", ANCHOR.isoformat()]) == 0  # lecture seule : pas de verrou
    assert "contrôles réussis" in capsys.readouterr().out
    api.tenant(sites=("S1",))
    out = str(tmp_path / "c.tsv")
    assert main(["demo", "seed", "--profile", "qa", "--credentials-out", out]) == 3
    assert not os.path.exists(out)
