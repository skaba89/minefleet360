#!/usr/bin/env python3
"""Contrôle A6 de la recette staging (RECETTE_STAGING_VALIDATION.md) : comptes et permissions, lecture seule.

Pour chaque compte FICTIF du fichier fourni par l'opérateur (hors dépôt, droits 600) :
  1. POST /api/v1/auth/login (second facteur demandé de façon interactive si le compte l'exige) ;
  2. GET /api/v1/me : le rôle et la portée attendus figurent dans les grants ;
  3. route hors droits → 403 : `GET /platform/tenants` (compte de société), `GET /vehicles` (PLATFORM_ADMIN) ;
  4. comptes d'administration (TENANT_ADMIN, PLATFORM_ADMIN) : MFA activé ;
  5. POST /api/v1/auth/logout (aucune session laissée ouverte).
Aucune écriture métier. Jamais de mot de passe, de jeton ni de code affiché ou journalisé.

Fichier de comptes (TSV, une ligne par compte, `#` = commentaire) :
  RÔLE<TAB>PORTÉE<TAB>ESPACE<TAB>E-MAIL<TAB>MOT_DE_PASSE
  (PORTÉE : TENANT, SITE ou PLATFORM ; ESPACE = code de l'espace, `mf-platform` pour PLATFORM_ADMIN)

Usage : MF_A6_URL=https://staging.example.org python3 audit-a6-accounts.py comptes.tsv [--non-interactive]
Codes de sortie : 0 aucun écart · 2 au moins un écart · 3 configuration.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

ADMIN_ROLES = frozenset({"TENANT_ADMIN", "PLATFORM_ADMIN"})
TIMEOUT_S = 15


@dataclass(frozen=True)
class Account:
    role: str
    scope: str
    workspace: str
    email: str
    password: str


@dataclass
class Result:
    role: str
    scope: str
    login: str = "—"
    grants: str = "—"
    denied: str = "—"
    mfa: str = "—"

    @property
    def ok(self) -> bool:
        return all(v.startswith("OK") for v in (self.login, self.grants, self.denied, self.mfa))


class ConfigError(Exception):
    pass


def validate_base_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ConfigError("MF_A6_URL : origine seule, sans chemin, identifiants, query ni fragment")
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise ConfigError("MF_A6_URL : HTTPS obligatoire (HTTP accepté pour localhost seulement)")
    return f"{parsed.scheme}://{parsed.netloc}"


def load_accounts(path: str) -> list[Account]:
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError as exc:
        raise ConfigError(f"fichier de comptes illisible : {path}") from exc
    if mode & 0o077:
        raise ConfigError("fichier de comptes : droits 600 exigés (secrets de recette)")
    accounts = []
    with open(path, encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                raise ConfigError(f"ligne {number} : 5 colonnes séparées par des tabulations attendues")
            role, scope, workspace, email = (p.strip() for p in parts[:4])
            password = parts[4]
            if scope not in ("TENANT", "SITE", "PLATFORM"):
                raise ConfigError(f"ligne {number} : portée inconnue")
            if (role == "PLATFORM_ADMIN") != (scope == "PLATFORM"):
                raise ConfigError(f"ligne {number} : PLATFORM_ADMIN ⇔ portée PLATFORM")
            if not workspace:
                raise ConfigError(f"ligne {number} : espace de travail manquant")
            accounts.append(Account(role, scope, workspace, email, password))
    if not accounts:
        raise ConfigError("aucun compte dans le fichier")
    return accounts


def _request(base: str, method: str, path: str, token: str | None = None, body: object | None = None):  # type: ignore[no-untyped-def]
    data = json.dumps(body).encode("utf-8") if body is not None else None
    # Origine validée par validate_base_url (https, ou http pour localhost seulement) : aucun autre schéma.
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method)  # noqa: S310
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (origine validée)
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _login(base: str, account: Account, interactive: bool) -> tuple[str | None, str]:
    body = {"workspace_code": account.workspace, "email": account.email, "password": account.password}
    status, payload = _request(base, "POST", "/auth/login", body=body)
    if status != 200 or not isinstance(payload, dict):
        return None, f"ÉCHEC (HTTP {status})"
    if payload.get("mfa_required"):
        if not interactive:
            return None, "NON VÉRIFIÉ (MFA requis, mode non interactif)"
        code = getpass.getpass(f"Code MFA pour le compte {account.role} ({account.scope}) : ").strip()
        status, payload = _request(
            base, "POST", "/auth/mfa/verify", body={"mfa_token": payload.get("mfa_token"), "code": code}
        )
        if status != 200 or not isinstance(payload, dict):
            return None, f"ÉCHEC MFA (HTTP {status})"
        token = payload.get("access_token")
        return (token, "OK (MFA)") if isinstance(token, str) else (None, "ÉCHEC (réponse MFA incomplète)")
    token = payload.get("access_token")
    return (token, "OK") if isinstance(token, str) else (None, "ÉCHEC (réponse incomplète)")


def check(base: str, account: Account, interactive: bool) -> Result:
    result = Result(account.role, account.scope)
    token, result.login = _login(base, account, interactive)
    if token is None:
        return result
    try:
        status, me = _request(base, "GET", "/me", token)
        if status != 200 or not isinstance(me, dict):
            result.grants = f"ÉCHEC (/me HTTP {status})"
        else:
            grants = {(g.get("role_code"), g.get("scope_type")) for g in me.get("grants", [])}
            expected = (account.role, account.scope)
            result.grants = "OK" if expected in grants else "ÉCART (rôle ou portée absent)"
            if account.role in ADMIN_ROLES:
                missing = "ÉCART (MFA non activé sur un compte d'administration)"
                result.mfa = "OK" if me.get("mfa_enabled") else missing
            else:
                result.mfa = "OK (non exigé)" if not me.get("mfa_enabled") else "OK (activé)"
        probe = "/vehicles" if account.role == "PLATFORM_ADMIN" else "/platform/tenants"
        status, _ = _request(base, "GET", probe, token)
        result.denied = f"OK (403 sur {probe})" if status == 403 else f"ÉCART (HTTP {status} sur {probe})"
    finally:
        _request(base, "POST", "/auth/logout", token)
    return result


def report(results: list[Result]) -> str:
    lines = [
        "| Rôle | Portée | Connexion | Grants /me | Route hors droits | MFA |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.role} | {r.scope} | {r.login} | {r.grants} | {r.denied} | {r.mfa} |")
    failures = sum(1 for r in results if not r.ok)
    lines.append("")
    lines.append(f"Comptes contrôlés : {len(results)} · écarts : {failures}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôle A6 (comptes et permissions) en lecture seule")
    parser.add_argument("accounts", help="fichier TSV des comptes fictifs (droits 600, hors dépôt)")
    parser.add_argument("--non-interactive", action="store_true", help="ne jamais demander de code MFA")
    args = parser.parse_args(argv)
    if os.environ.get("MF_ENV") == "production":
        print("CONFIG : contrôle de recette uniquement, refusé en production", file=sys.stderr)
        return 3
    try:
        base = validate_base_url(os.environ.get("MF_A6_URL", ""))
        accounts = load_accounts(args.accounts)
    except ConfigError as exc:
        print(f"CONFIG : {exc}", file=sys.stderr)
        return 3
    results = [check(base, a, not args.non_interactive) for a in accounts]
    print(report(results))
    return 0 if all(r.ok for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
