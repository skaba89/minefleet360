#!/usr/bin/env python3
"""Read-only business smoke for a staging release or rollback (beyond health probes).

Logs in with a FICTITIOUS staging account and exercises essential read paths of the
running API/web pair: session, sites, fleet, dispatch, GPS geofences/alerts/positions,
the SPA shell and both PMTiles basemaps (France, Guinée). Only GET requests are issued
after the login; no business data is created or changed.

Credentials come from MF_SMOKE_CREDENTIALS_FILE (mode 600/400, KEY=VALUE lines):
MF_SMOKE_WORKSPACE, MF_SMOKE_EMAIL, MF_SMOKE_PASSWORD and, if MFA is enforced for that
account, MF_SMOKE_TOTP_SECRET (base32). Nothing secret is ever printed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import ssl
import stat
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TIMEOUT = 15
BASEMAPS = ("guinee.pmtiles", "france.pmtiles")
READ_PATHS = (
    "/api/v1/me",
    "/api/v1/sites?page_size=5",
    "/api/v1/vehicles?page_size=5",
    "/api/v1/vehicle-categories",
    "/api/v1/missions?page_size=5",
    "/api/v1/geofences",
    "/api/v1/gps/alerts?page_size=5",
    "/api/v1/vehicles/gps/latest",
)


class SmokeError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None


_OPENER = urllib.request.build_opener(
    _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
)


def load_credentials(path: str) -> dict[str, str]:
    file = Path(path)
    if not file.is_absolute() or file.is_symlink() or not file.is_file():
        raise SmokeError("credentials file must be an absolute regular file")
    if stat.S_IMODE(file.stat().st_mode) not in (0o600, 0o400):
        raise SmokeError("credentials file must be mode 600 or 400")
    values: dict[str, str] = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    for key in ("MF_SMOKE_WORKSPACE", "MF_SMOKE_EMAIL", "MF_SMOKE_PASSWORD"):
        if not values.get(key):
            raise SmokeError(f"{key} missing from credentials file")
    return values


def totp(secret: str, now: float | None = None) -> str:
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if now is None else now) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def request(
    base: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="GET" if body is None else "POST")
    req.add_header("Accept", "application/json")
    req.add_header("Origin", base)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as response:
            return response.status, response.read(512 * 1024), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096), dict(error.headers or {})
    except (urllib.error.URLError, OSError) as error:
        raise SmokeError(f"{path} unreachable") from error


def login(base: str, credentials: dict[str, str]) -> str:
    status, body, _ = request(
        base,
        "/api/v1/auth/login",
        body={
            "workspace_code": credentials["MF_SMOKE_WORKSPACE"],
            "email": credentials["MF_SMOKE_EMAIL"],
            "password": credentials["MF_SMOKE_PASSWORD"],
        },
    )
    if status != 200:
        raise SmokeError(f"login returned HTTP {status}")
    payload = json.loads(body)
    if payload.get("mfa_required"):
        secret = credentials.get("MF_SMOKE_TOTP_SECRET")
        if not secret:
            raise SmokeError("account requires MFA and MF_SMOKE_TOTP_SECRET is absent")
        status, body, _ = request(
            base,
            "/api/v1/auth/mfa/verify",
            body={"mfa_token": payload["mfa_token"], "code": totp(secret)},
        )
        if status == 401:
            # A TOTP code is accepted once: a smoke repeated within the same 30 s window
            # (release then automatic rollback) must wait for the next code, once.
            time.sleep(31 - time.time() % 30)
            status, body, _ = request(
                base,
                "/api/v1/auth/mfa/verify",
                body={"mfa_token": payload["mfa_token"], "code": totp(secret)},
            )
        if status != 200:
            raise SmokeError(f"MFA verification returned HTTP {status}")
        payload = json.loads(body)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise SmokeError("login did not return an access token")
    return token


def run(base: str, credentials: dict[str, str]) -> list[str]:
    results = []
    status, body, _ = request(base, "/")
    if status != 200 or b'<div id="root"' not in body:
        raise SmokeError(f"SPA shell returned HTTP {status} or no application root")
    asset = re.search(rb'src="(/assets/[^"]+\.js)"', body)
    if not asset:
        raise SmokeError("SPA shell does not reference a versioned script")
    status, _, _ = request(base, asset.group(1).decode())
    if status != 200:
        raise SmokeError(f"SPA script returned HTTP {status}")
    results.append("web shell and versioned assets")
    for name in BASEMAPS:
        status, chunk, _ = request(base, f"/basemap/{name}", headers={"Range": "bytes=0-6"})
        if status != 206 or not chunk.startswith(b"PMTiles"):
            raise SmokeError(f"basemap {name} not served as PMTiles (HTTP {status})")
    results.append("PMTiles basemaps " + ", ".join(BASEMAPS))
    token = login(base, credentials)
    results.append("login")
    for path in READ_PATHS:
        status, body, _ = request(base, path, token=token)
        if status != 200:
            raise SmokeError(f"GET {path.split('?')[0]} returned HTTP {status}")
        json.loads(body)
        results.append(path.split("?")[0])
    return results


def main() -> int:
    base = os.environ.get("MINEFLEET_STAGING_URL", "").rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9._:-]+", base):
        print("FAIL: MINEFLEET_STAGING_URL must be a credential-free HTTPS origin", file=sys.stderr)
        return 2
    try:
        credentials = load_credentials(os.environ.get("MF_SMOKE_CREDENTIALS_FILE", ""))
        checked = run(base, credentials)
    except (SmokeError, ValueError) as error:
        print(f"FAIL: business smoke: {error}", file=sys.stderr)
        return 1
    print(f"OK: business smoke ({len(checked)} checks): " + "; ".join(checked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
