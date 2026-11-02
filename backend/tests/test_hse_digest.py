"""Récapitulatif HSE quotidien par e-mail (docs/LIVRAISON_NOTIFICATIONS.md)."""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cli import main as cli_main
from app.core.config import get_settings
from app.core.db import new_session
from app.core.email import MemoryEmailSender
from app.core.tenancy import set_tenant_context
from app.hse.digest import send_digests
from tests.conftest import API, Account, Api, TenantFixture


def _incident(
    client: TestClient, t: TenantFixture, headers: dict[str, str], site: str, severity: str, title: str
) -> dict:  # type: ignore[type-arg]
    resp = client.post(
        f"{API}/hse/incidents",
        headers=headers,
        json={
            "site_id": str(t.sites[site]),
            "category": "INJURY",
            "severity": severity,
            "title": title,
            "description": "Description confidentielle à ne jamais envoyer par e-mail.",
            "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _action(client: TestClient, hse: Account, incident: dict, owner: Account, due: date) -> dict:  # type: ignore[type-arg]
    resp = client.post(
        f"{API}/hse/incidents/{incident['hse_incident_id']}/actions",
        headers=hse.headers,
        json={
            "title": "Titre d'action à ne pas diffuser",
            "owner_user_id": str(owner.user_id),
            "due_date": due.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _run(t: TenantFixture, *, dry_run: bool) -> tuple[int, MemoryEmailSender]:
    sender = MemoryEmailSender()
    db = new_session()
    try:
        set_tenant_context(db, t.tenant_id)
        count = send_digests(
            db,
            tenant_id=t.tenant_id,
            now=datetime.now(UTC),
            settings=get_settings(),
            sender=sender,
            dry_run=dry_run,
        )
        db.commit()
    finally:
        db.close()
    return count, sender


def test_digest_targets_owners_and_hse_without_free_text(client: TestClient, api: Api) -> None:
    t = api.tenant()
    other = api.tenant()
    hse = api.user(t, "HSE")
    hse_s2 = api.user(t, "HSE", "SITE", "S2")
    owner = api.user(t, "OPS_MANAGER")
    far_owner = api.user(t, "DISPATCHER", "SITE", "S1")
    critical = _incident(client, t, owner.headers, "S1", "CRITICAL", "Blessure grave de M. Fictif")
    high_s2 = _incident(client, t, owner.headers, "S2", "HIGH", "Chute en atelier")
    _incident(client, t, owner.headers, "S1", "LOW", "Faible")
    soon = _action(client, hse, critical, owner, date.today() + timedelta(days=1))
    late = _action(client, hse, critical, owner, date.today())
    _action(client, hse, critical, far_owner, date.today() + timedelta(days=10))  # trop lointaine
    db = new_session()
    try:
        set_tenant_context(db, t.tenant_id)
        db.execute(
            text("UPDATE hse_corrective_action SET due_date = :d WHERE hse_corrective_action_id = :i"),
            {"d": date.today() - timedelta(days=3), "i": late["hse_corrective_action_id"]},
        )
        db.commit()
    finally:
        db.close()
    _incident(client, other, api.user(other, "OPS_MANAGER").headers, "S1", "CRITICAL", "Autre société")

    planned, nothing = _run(t, dry_run=True)
    assert planned == 3 and nothing.outbox == []

    count, sender = _run(t, dry_run=False)
    assert count == 3
    by_recipient = {m.to: m for m in sender.outbox}
    assert set(by_recipient) == {owner.email, hse.email, hse_s2.email}
    owner_mail = by_recipient[owner.email].body
    assert "EN RETARD" in owner_mail and "à échéance proche" in owner_mail
    assert owner_mail.count(critical["reference"]) == 2
    assert (
        critical["reference"] in by_recipient[hse.email].body
        and high_s2["reference"] in by_recipient[hse.email].body
    )
    assert high_s2["reference"] in by_recipient[hse_s2.email].body
    assert critical["reference"] not in by_recipient[hse_s2.email].body  # site S1 hors de sa portée
    for message in sender.outbox:
        assert message.kind == "HSE_DIGEST"
        for secret in (
            "Blessure grave",
            "M. Fictif",
            "Description confidentielle",
            "Titre d'action",
            "Autre société",
        ):
            assert secret not in message.body
    audit = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"action": "hse.digest.sent"}
    ).json()
    assert audit["total"] == 3
    assert soon["status"] == "OPEN"


def test_no_message_when_nothing_to_do(client: TestClient, api: Api) -> None:
    t = api.tenant()
    api.user(t, "HSE")
    count, sender = _run(t, dry_run=False)
    assert count == 0 and sender.outbox == []


def test_cli_dry_run_reports_without_sending(client: TestClient, api: Api, capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli_main(["send-hse-digest", "--dry-run"]) == 0
    assert "Récapitulatifs HSE à envoyer (simulation)" in capsys.readouterr().out


def test_cli_reports_smtp_failure_and_rolls_back_audit(
    client: TestClient, api: Api, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    import app.core.email as email_module

    t = api.tenant()
    api.user(t, "HSE")
    owner = api.user(t, "OPS_MANAGER")
    _incident(client, t, owner.headers, "S1", "CRITICAL", "Panne d'envoi")

    class Broken:
        def send(self, message: object) -> None:
            raise OSError("SMTP indisponible")

    monkeypatch.setattr(email_module, "build_email_sender", lambda _settings: Broken())
    assert cli_main(["send-hse-digest"]) == 1
    assert "sociétés en échec : " in capsys.readouterr().out
    audit = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"action": "hse.digest.sent"}
    ).json()
    assert audit["total"] == 0  # aucun envoi n'est déclaré réussi
