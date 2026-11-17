"""Contrôle A6 (comptes et permissions, lecture seule) contre un faux serveur API local, sans réseau."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_a6", ROOT / "infra/deploy/audit-a6-accounts.py")
assert SPEC and SPEC.loader
audit_a6 = importlib.util.module_from_spec(SPEC)
sys.modules["audit_a6"] = audit_a6  # requis par les dataclasses du script (annotations différées)
SPEC.loader.exec_module(audit_a6)

PASSWORD = "MotDePasse-Fictif-123"


class FakeApi:
    """Comptes fictifs : e-mail → (grants, mfa_enabled, mfa_required, statut de la route hors droits)."""

    def __init__(self) -> None:
        self.accounts: dict[str, dict] = {}  # type: ignore[type-arg]
        self.logouts: list[str] = []
        self.writes: list[str] = []


def _handler(api: FakeApi):  # type: ignore[no-untyped-def]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def _send(self, status: int, body: object | None = None) -> None:
            raw = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _account(self) -> dict | None:  # type: ignore[type-arg]
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            return api.accounts.get(token.removeprefix("jeton-"))

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/v1/auth/login":
                account = api.accounts.get(body.get("email"))
                if account is None or body.get("password") != PASSWORD or not body.get("workspace_code"):
                    return self._send(401, {"code": "INVALID_CREDENTIALS"})
                if account["mfa_required"]:
                    return self._send(
                        200, {"mfa_required": True, "mfa_token": "defi-" + body["email"], "expires_in": 300}
                    )
                return self._send(200, {"access_token": "jeton-" + body["email"], "expires_in": 900})
            if self.path == "/api/v1/auth/logout":
                api.logouts.append(self.headers.get("Authorization") or "")
                return self._send(204)
            api.writes.append(self.path)
            return self._send(404)

        def do_GET(self) -> None:
            account = self._account()
            if account is None:
                return self._send(401)
            if self.path == "/api/v1/me":
                return self._send(200, {"grants": account["grants"], "mfa_enabled": account["mfa_enabled"]})
            if self.path in ("/api/v1/platform/tenants", "/api/v1/vehicles"):
                return self._send(account["denied_status"])
            return self._send(404)

    return Handler


class AuditA6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeApi()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self.api))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tmp = Path(tempfile.mkdtemp())

    def add(self, email: str, role: str, scope: str, *, mfa_enabled: bool = False, mfa_required: bool = False,
            denied_status: int = 403) -> None:  # fmt: skip
        self.api.accounts[email] = {
            "grants": [{"role_code": role, "scope_type": scope, "site_id": None}],
            "mfa_enabled": mfa_enabled,
            "mfa_required": mfa_required,
            "denied_status": denied_status,
        }

    def accounts_file(self, rows: list[tuple[str, str, str, str]], mode: int = 0o600) -> str:
        path = self.tmp / "comptes.tsv"
        path.write_text(
            "# rôle\tportée\tespace\te-mail\tmot de passe\n"
            + "".join(f"{role}\t{scope}\t{ws}\t{email}\t{PASSWORD}\n" for role, scope, ws, email in rows)
        )
        path.chmod(mode)
        return str(path)

    def run_audit(
        self, path: str, *extra: str, url: str | None = None, env: str = "staging"
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        previous = {k: os.environ.get(k) for k in ("MF_A6_URL", "MF_ENV")}
        os.environ["MF_A6_URL"] = url or self.url
        os.environ["MF_ENV"] = env
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = audit_a6.main([path, *extra])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return code, out.getvalue(), err.getvalue()

    def test_nominal_roles_are_verified_without_leaking_secrets(self) -> None:
        self.add("admin@exemple.test", "TENANT_ADMIN", "TENANT", mfa_enabled=True)
        self.add("dispatch@exemple.test", "DISPATCHER", "SITE")
        self.add("plateforme@exemple.test", "PLATFORM_ADMIN", "PLATFORM", mfa_enabled=True)
        path = self.accounts_file(
            [
                ("TENANT_ADMIN", "TENANT", "demo-bauxite", "admin@exemple.test"),
                ("DISPATCHER", "SITE", "demo-bauxite", "dispatch@exemple.test"),
                ("PLATFORM_ADMIN", "PLATFORM", "mf-platform", "plateforme@exemple.test"),
            ]
        )
        code, out, _ = self.run_audit(path)
        self.assertEqual(code, 0, out)
        self.assertIn("écarts : 0", out)
        self.assertIn("OK (403 sur /vehicles)", out)  # PLATFORM_ADMIN sans accès aux données d'une société
        self.assertIn("OK (403 sur /platform/tenants)", out)
        self.assertNotIn(PASSWORD, out)
        self.assertNotIn("jeton-", out)
        self.assertEqual(len(self.api.logouts), 3)  # aucune session laissée ouverte
        self.assertEqual(self.api.writes, [])  # aucune écriture métier

    def test_admin_without_mfa_and_route_not_denied_are_reported(self) -> None:
        self.add("admin@exemple.test", "TENANT_ADMIN", "TENANT", mfa_enabled=False)
        self.add("fuite@exemple.test", "OPS_MANAGER", "TENANT", denied_status=200)
        path = self.accounts_file(
            [
                ("TENANT_ADMIN", "TENANT", "demo-bauxite", "admin@exemple.test"),
                ("OPS_MANAGER", "TENANT", "demo-bauxite", "fuite@exemple.test"),
            ]
        )
        code, out, _ = self.run_audit(path)
        self.assertEqual(code, 2)
        self.assertIn("MFA non activé sur un compte d'administration", out)
        self.assertIn("ÉCART (HTTP 200 sur /platform/tenants)", out)
        self.assertIn("écarts : 2", out)

    def test_wrong_role_and_mfa_without_interaction_are_reported(self) -> None:
        self.add("hse@exemple.test", "HSE", "TENANT")
        self.add("mfa@exemple.test", "TENANT_ADMIN", "TENANT", mfa_enabled=True, mfa_required=True)
        path = self.accounts_file(
            [
                ("FINANCE", "TENANT", "demo-bauxite", "hse@exemple.test"),  # rôle attendu absent des grants
                ("TENANT_ADMIN", "TENANT", "demo-bauxite", "mfa@exemple.test"),
            ]
        )
        code, out, _ = self.run_audit(path, "--non-interactive")
        self.assertEqual(code, 2)
        self.assertIn("ÉCART (rôle ou portée absent)", out)
        self.assertIn("NON VÉRIFIÉ (MFA requis, mode non interactif)", out)

    def test_configuration_is_refused_before_any_request(self) -> None:
        self.add("admin@exemple.test", "TENANT_ADMIN", "TENANT", mfa_enabled=True)
        row = [("TENANT_ADMIN", "TENANT", "demo-bauxite", "admin@exemple.test")]
        self.assertEqual(self.run_audit(self.accounts_file(row, mode=0o644))[0], 3)  # secrets lisibles
        self.assertEqual(self.run_audit(self.accounts_file(row), url="http://staging.example.org")[0], 3)
        self.assertEqual(self.run_audit(self.accounts_file(row), url=self.url + "/api")[0], 3)
        self.assertEqual(self.run_audit(self.accounts_file(row), env="production")[0], 3)
        bad_platform = [("PLATFORM_ADMIN", "TENANT", "mf-platform", "admin@exemple.test")]
        self.assertEqual(self.run_audit(self.accounts_file(bad_platform))[0], 3)
        self.assertEqual(self.api.logouts, [])  # aucune requête n'a été émise


if __name__ == "__main__":
    unittest.main()
