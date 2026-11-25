#!/usr/bin/env python3
"""Real login checks of the bootstrapped PLATFORM_ADMIN (staging-reset, #532). Stdlib only.

  enroll <base-url>  first login, MFA enrolment, second login with TOTP, permissions, logout
                     revocation, wrong password; prints the TOTP secret and recovery codes on
                     STDOUT ONLY (the caller redirects them to a new 600 file), progress on stderr.
  login <base-url>   login + TOTP verification + /me with an enrolled account (post-cutover).

Inputs (environment): MF_CHECK_EMAIL, MF_CHECK_PASSWORD, MF_CHECK_ORIGIN and, for `login`,
MF_CHECK_TOTP_SECRET. Nothing secret is written to stderr.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 15


class CheckError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def totp(secret: str, at: float | None = None) -> str:
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def next_window() -> None:
    time.sleep(31 - time.time() % 30)


class Client:
    def __init__(self, base: str, origin: str) -> None:
        self.base = base.rstrip("/")
        self.origin = origin
        context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def call(self, method: str, path: str, body: dict | None = None, token: str | None = None,
             cookie: str | None = None) -> tuple[int, dict, dict]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Origin", self.origin)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        if cookie:
            request.add_header("Cookie", cookie)
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                raw, status, headers = response.read(), response.status, response.headers
        except urllib.error.HTTPError as error:
            raw, status, headers = error.read(), error.code, error.headers
        except (urllib.error.URLError, OSError) as error:
            raise CheckError(f"{method} {path} unreachable") from error
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        return status, payload, {"set-cookie": headers.get_all("Set-Cookie") or []}

    def login(self, email: str, password: str) -> tuple[int, dict, str]:
        status, payload, headers = self.call(
            "POST", "/api/v1/auth/platform/login", {"email": email, "password": password}
        )
        cookie = "; ".join(c.split(";", 1)[0] for c in headers["set-cookie"])
        return status, payload, cookie


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)
    log(f"OK: {message}")


def enroll(client: Client, email: str, password: str) -> dict:
    status, _, _ = client.login(email, password + "-wrong")
    expect(status == 401, "wrong password refused (401)")
    status, payload, _ = client.login(email, password)
    expect(status == 200 and "access_token" in payload, "first platform login (password)")
    token = payload["access_token"]
    status, setup, _ = client.call("POST", "/api/v1/me/mfa/setup", {"password": password}, token)
    expect(status == 200 and setup.get("secret"), "MFA setup issued a TOTP secret")
    secret = setup["secret"]
    status, codes, _ = client.call("POST", "/api/v1/me/mfa/confirm", {"code": totp(secret)}, token)
    expect(status == 200, "MFA enrolment confirmed with a TOTP code")
    # confirm_setup upgrades the enrolling session to amr=[pwd, otp] (mfa_service.py).
    status, _, _ = client.call("GET", "/api/v1/me", token=token)
    expect(status == 200, "enrolling session upgraded to MFA after confirmation")

    next_window()
    status, challenge, cookie = client.login(email, password)
    expect(status == 200 and challenge.get("mfa_required"), "second login requires the second factor")
    status, verified, headers = client.call(
        "POST", "/api/v1/auth/mfa/verify", {"mfa_token": challenge["mfa_token"], "code": totp(secret)}
    )
    expect(status == 200 and "access_token" in verified, "TOTP verification opens a session")
    token = verified["access_token"]
    cookie = "; ".join(c.split(";", 1)[0] for c in headers["set-cookie"]) or cookie
    status, me, _ = client.call("GET", "/api/v1/me", token=token)
    expect(status == 200 and me.get("email") == email.lower(), "GET /me returns the new admin only")
    status, tenants, _ = client.call("GET", "/api/v1/platform/tenants", token=token)
    expect(status == 200, "PLATFORM_ADMIN can list tenants")
    items = tenants.get("items", tenants if isinstance(tenants, list) else [])
    expect(all(t.get("kind", "PLATFORM") == "PLATFORM" for t in items) if items else True,
           f"no client tenant exists ({len(items)} tenant(s) listed)")
    status, _, _ = client.call("GET", "/api/v1/sites", token=token)
    expect(status in (403, 404), f"tenant business route refused to the platform admin ({status})")
    status, _, _ = client.call("POST", "/api/v1/auth/logout", {}, token, cookie=cookie)
    expect(status == 204, "logout accepted")
    status, _, _ = client.call("GET", "/api/v1/me", token=token)
    expect(status == 401, "access token revoked after logout (401)")
    return {"totp_secret": secret, "recovery_codes": codes.get("codes") or codes.get("recovery_codes")}


def login_only(client: Client, email: str, password: str, secret: str) -> None:
    status, challenge, _ = client.login(email, password)
    expect(status == 200 and challenge.get("mfa_required"), "platform login requires the second factor")
    status, verified, _ = client.call(
        "POST", "/api/v1/auth/mfa/verify", {"mfa_token": challenge["mfa_token"], "code": totp(secret)}
    )
    if status == 401:
        next_window()
        status, challenge, _ = client.login(email, password)
        status, verified, _ = client.call(
            "POST", "/api/v1/auth/mfa/verify", {"mfa_token": challenge["mfa_token"], "code": totp(secret)}
        )
    expect(status == 200 and "access_token" in verified, "TOTP verification opens a session")
    status, me, _ = client.call("GET", "/api/v1/me", token=verified["access_token"])
    expect(status == 200 and me.get("email") == email.lower(), "GET /me returns the bootstrapped admin")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"enroll", "login"}:
        log("usage: staging-reset-admin-check.py enroll|login <base-url>")
        return 2
    try:
        email = os.environ["MF_CHECK_EMAIL"]
        password = os.environ["MF_CHECK_PASSWORD"]
        client = Client(sys.argv[2], os.environ["MF_CHECK_ORIGIN"])
        if sys.argv[1] == "enroll":
            secrets = enroll(client, email, password)
            sys.stdout.write(json.dumps(secrets) + "\n")
        else:
            login_only(client, email, password, os.environ["MF_CHECK_TOTP_SECRET"])
    except KeyError as error:
        log(f"FAIL: missing input {error.args[0]}")
        return 2
    except CheckError as error:
        log(f"FAIL: {error}")
        return 1
    log("OK: platform admin checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
