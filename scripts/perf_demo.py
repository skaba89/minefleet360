"""Mesure des temps de réponse des écrans clés sur une base DEMO (API LOCALE uniquement).

Usage :
    python scripts/perf_demo.py --accounts comptes-demo.tsv --label standard [--api http://127.0.0.1:8000]
        [--tenant demo-bauxite] [--runs 15]

Se connecte avec le compte AUDITOR (lecture seule, portée société) de la société choisie, appelle chaque route
après 2 appels d'échauffement, et imprime un tableau Markdown : p50, p95, max (ms) et taille de réponse.
La consultation d'un trajet GPS est journalisée dans l'audit (finalité « Analyse d'exploitation »), comme
dans l'application. Aucune écriture métier. Les chiffres dépendent de la machine : les publier avec elle.
"""

import argparse
import json
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

LOCAL = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")


def request(api: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{api}/api/v1{path}", data=data, method="POST" if body is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def account(path: str, tenant: str, role: str) -> tuple[str, str]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 5 and parts[0] == tenant and parts[1] == role and parts[2] == "-":
                return parts[3], parts[4]
    raise SystemExit(f"compte {role} introuvable pour {tenant}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant", default="demo-bauxite")
    parser.add_argument("--runs", type=int, default=15)
    args = parser.parse_args()
    if not LOCAL.match(args.api):
        raise SystemExit("API locale uniquement")
    email, password = account(args.accounts, args.tenant, "AUDITOR")
    status, raw = request(
        args.api, "/auth/login", body={"workspace_code": args.tenant, "email": email, "password": password}
    )
    if status != 200:
        raise SystemExit(f"connexion refusée ({status})")
    token = json.loads(raw)["access_token"]

    now = datetime.now(UTC).replace(microsecond=0)
    day = now - timedelta(days=2)
    q = urllib.parse.urlencode
    _, vehicles_raw = request(args.api, "/vehicles?" + q({"page_size": 200}), token)
    vehicles = json.loads(vehicles_raw)["items"]
    truck = next(v["vehicle_id"] for v in vehicles if v["fleet_number"].startswith("DEMO-CAM-"))
    routes = [
        ("Parc (liste, ≤ 200)", "/vehicles?" + q({"page_size": 200})),
        ("Missions (50)", "/missions?" + q({"page_size": 50})),
        ("Pesées (50)", "/weighing-tickets?" + q({"page_size": 50})),
        (
            "Indicateurs 7 j",
            "/dispatch-indicators?"
            + q({"period_start": (now - timedelta(days=7)).isoformat(), "period_end": now.isoformat()}),
        ),
        (
            "Indicateurs 30 j",
            "/dispatch-indicators?"
            + q({"period_start": (now - timedelta(days=30)).isoformat(), "period_end": now.isoformat()}),
        ),
        ("Coût complet 30 j", "/costs/vehicles"),
        ("Carburant (tableau de bord)", "/fuel/dashboard"),
        ("HSE (synthèse 90 j)", "/hse/summary?" + q({"days": 90})),
        ("Fiabilité atelier", "/maintenance/reliability"),
        ("Dernières positions GPS", "/vehicles/gps/latest"),
        (
            "Trajet GPS 24 h",
            f"/vehicles/{truck}/gps/track?"
            + q({"purpose": "OPERATIONS_REVIEW", "from": day.isoformat(), "to": (day + timedelta(days=1)).isoformat()}),
        ),
    ]
    print(f"### {args.label} — {args.tenant} ({args.runs} appels mesurés par route)\n")
    print("| Écran / route | Statut | p50 (ms) | p95 (ms) | max (ms) | Taille (Kio) |")
    print("|---|---|---:|---:|---:|---:|")
    for label, path in routes:
        timings: list[float] = []
        status, size = 0, 0
        for i in range(args.runs + 2):
            t0 = time.perf_counter()
            status, body = request(args.api, path, token)
            elapsed = (time.perf_counter() - t0) * 1000
            size = len(body)
            if i >= 2:
                timings.append(elapsed)
            if status != 200:
                break
        if status != 200 or not timings:
            print(f"| {label} | {status} | — | — | — | — |")
            continue
        timings.sort()
        p95 = timings[max(0, round(0.95 * len(timings)) - 1)]
        print(
            f"| {label} | {status} | {statistics.median(timings):.0f} | {p95:.0f} | {timings[-1]:.0f} "
            f"| {size / 1024:.0f} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
