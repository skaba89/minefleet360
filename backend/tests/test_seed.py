"""US-1.30 — jeu de données fictif : refus en production, contenu fictif, réexécution refusée."""

import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.seed import SeedRefused, seed
from tests.conftest import API


def test_us130_seed_loads_fictitious_data_once(client: TestClient) -> None:
    report = seed()
    assert report.counts == {
        "tenants": 2,
        "sites": 4,
        "users": 16,
        "vehicles": 20,
        "drivers": 16,
        "licenses": 16,
        "qualifications": 16,
    }
    # A2 : uniquement des valeurs sentinelles.
    for workspace, email, _, _ in report.accounts:
        assert email.endswith(f"@{workspace}.example.com")
    with pytest.raises(SeedRefused):  # A4 : réexécution refusée explicitement
        seed()

    workspace, email, _, password = next(a for a in report.accounts if a[2] == "HR")
    login = client.post(
        f"{API}/auth/login", json={"workspace_code": workspace, "email": email, "password": password}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    drivers = client.get(f"{API}/drivers", headers=headers).json()["items"]
    assert all(re.fullmatch(r"Nom-Test-\d\d", d["last_name"]) for d in drivers)
    assert all(d["phone"].startswith("+224000000") for d in drivers)
    expirations = client.get(f"{API}/workforce/expirations", headers=headers).json()
    assert {e["validity"] for e in expirations} == {"EXPIRED", "EXPIRING"}
    tenant = client.get(f"{API}/tenant", headers=headers).json()
    assert tenant["code"] == workspace


def test_us130_seed_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "env", "production")
    with pytest.raises(SeedRefused):
        seed()
