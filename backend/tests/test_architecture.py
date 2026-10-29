"""Règles d'architecture vérifiées statiquement (ADR-001, ADR-002, D-12)."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


def _sources() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in APP.rglob("*.py")]


def test_only_tenancy_module_sets_tenant_context() -> None:
    offenders = [
        str(p.relative_to(APP))
        for p, src in _sources()
        if "set_config('app.tenant_id'" in src and p.name != "tenancy.py"
    ]
    assert offenders == []


def test_set_tenant_context_callers_are_known() -> None:
    # cli.py et seed.py : commandes d'exploitation (amorçage plateforme, jeu fictif de recette).
    allowed = {
        "tenancy.py",
        "dependencies.py",
        "auth_service.py",
        "mfa_service.py",  # seconde étape de connexion : tenant porté par le jeton de défi signé
        "service.py",
        "contracts.py",
        "cli.py",
        "seed.py",
        "gps_tracker_ingest.py",  # sélecteur tenant d'un jeton GPS opaque, secret vérifié avant écriture
    }
    callers = {p.name for p, src in _sources() if "set_tenant_context(" in src and p.name != "tenancy.py"}
    assert callers <= allowed, callers - allowed
    organization = (APP / "organization" / "service.py").read_text(encoding="utf-8")
    # Seuls le provisioning et la suspension de tenant changent de contexte (MODELE_PHYSIQUE §6.2).
    assert organization.count("set_tenant_context(") == 2


def test_business_code_uses_injectable_clock() -> None:
    pattern = re.compile(r"datetime\.(now|utcnow)\(")
    offenders = [
        str(p.relative_to(APP)) for p, src in _sources() if pattern.search(src) and p.name != "clock.py"
    ]
    assert offenders == []


def test_no_raw_delete_statements_on_business_tables() -> None:
    offenders = [str(p.relative_to(APP)) for p, src in _sources() if re.search(r"\bdelete\(", src)]
    assert offenders == []
