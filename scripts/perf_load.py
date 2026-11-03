"""Charge concurrente et exports paginés sur une base DEMO (API LOCALE uniquement, lecture seule).

Usage :
    python scripts/perf_load.py --accounts comptes-demo.tsv [--api http://127.0.0.1:8000]
        [--levels 1,5,10,20,40] [--duration 30] [--exports]

Ouvre une session AUDITOR (lecture seule, portée société) par société DEMO du fichier, puis, pour chaque
niveau de concurrence, fait tourner N utilisateurs simulés pendant `--duration` secondes : chacun enchaîne
sans pause des écrans tirés au hasard dans un mélange réaliste (listes, tableaux de bord, coût complet), en
alternant les sociétés. Imprime en Markdown le débit, les temps de réponse et les erreurs par niveau, puis le
temps de chaque écran au niveau le plus élevé. `--exports` mesure ensuite les exports CSV tels que le
navigateur les fait (pages de 200 lignes jusqu'à 5 000). Aucune écriture métier (pas de trajet GPS, qui serait
journalisé). Les chiffres dépendent de la machine : les publier avec elle.
"""

import argparse
import json
import random
import statistics
import threading
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from perf_demo import LOCAL, request

q = urllib.parse.urlencode


def _mix() -> list[tuple[str, str, int]]:
    """(écran, route, poids) : les listes et tableaux de bord dominent, le coût complet reste occasionnel."""
    now = datetime.now(UTC).replace(microsecond=0)
    period = {"period_start": (now - timedelta(days=7)).isoformat(), "period_end": now.isoformat()}
    return [
        ("Parc (liste)", "/vehicles?" + q({"page_size": 50}), 4),
        ("Missions (50)", "/missions?" + q({"page_size": 50}), 4),
        ("Pesées (50)", "/weighing-tickets?" + q({"page_size": 50}), 3),
        ("Indicateurs 7 j", "/dispatch-indicators?" + q(period), 2),
        ("Dernières positions GPS", "/vehicles/gps/latest", 4),
        ("Carburant (tableau de bord)", "/fuel/dashboard", 2),
        ("HSE (synthèse 90 j)", "/hse/summary?" + q({"days": 90}), 1),
        ("Fiabilité atelier", "/maintenance/reliability", 1),
        ("Coût complet 30 j", "/costs/vehicles", 1),
    ]


def sessions(path: str, api: str) -> list[str]:
    tokens = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 5 and parts[1] == "AUDITOR" and parts[2] == "-":
                body = {"workspace_code": parts[0], "email": parts[3], "password": parts[4]}
                status, raw = request(api, "/auth/login", body=body)
                if status != 200:
                    raise SystemExit(f"connexion refusée pour {parts[0]} ({status})")
                tokens.append(json.loads(raw)["access_token"])
    if not tokens:
        raise SystemExit("aucun compte AUDITOR dans le fichier")
    return tokens


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def run_level(
    api: str, tokens: list[str], users: int, duration: float, mix: list[tuple[str, str, int]]
) -> dict:
    labels = [m[0] for m in mix]
    paths = {m[0]: m[1] for m in mix}
    weights = [m[2] for m in mix]
    samples: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    lock = threading.Lock()
    stop_at = time.perf_counter() + duration

    def user(index: int) -> None:
        rnd = random.Random(index)  # noqa: S311 — tirage d'écrans, pas de sécurité
        token = tokens[index % len(tokens)]
        while time.perf_counter() < stop_at:
            label = rnd.choices(labels, weights)[0]
            start = time.perf_counter()
            status, _ = request(api, paths[label], token)
            elapsed = (time.perf_counter() - start) * 1000
            with lock:
                samples[label].append(elapsed)
                if status != 200:
                    errors[str(status)] += 1

    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=users) as pool:
        list(pool.map(user, range(users)))
    wall = time.perf_counter() - began
    every = [v for values in samples.values() for v in values]
    return {"users": users, "wall": wall, "all": every, "by_route": samples, "errors": dict(errors)}


def export_pages(api: str, token: str, path: str) -> tuple[int, int, float, float]:
    """Comme fetchAllPages : pages de 200, arrêt à 5 000 lignes ou à la dernière page."""
    rows, pages, slowest = 0, 0, 0.0
    started = time.perf_counter()
    total = None
    while rows < min(total if total is not None else 10**9, 5000):
        pages += 1
        sep = "&" if "?" in path else "?"
        t0 = time.perf_counter()
        status, raw = request(api, f"{path}{sep}" + q({"page": pages, "page_size": 200}), token)
        slowest = max(slowest, (time.perf_counter() - t0) * 1000)
        if status != 200:
            raise SystemExit(f"export {path} : statut {status}")
        body = json.loads(raw)
        total = body["total"]
        rows += len(body["items"])
        if len(body["items"]) < 200:
            break
    return rows, pages, (time.perf_counter() - started) * 1000, slowest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--levels", default="1,5,10,20,40")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--exports", action="store_true")
    args = parser.parse_args()
    if not LOCAL.match(args.api):
        raise SystemExit("API locale uniquement")
    tokens = sessions(args.accounts, args.api)
    mix = _mix()
    levels = [int(x) for x in args.levels.split(",")]
    print(f"### Charge concurrente — {len(tokens)} sociétés, {args.duration:.0f} s par niveau\n")
    print("| Utilisateurs simultanés | Requêtes/s | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Erreurs |")
    print("|---:|---:|---:|---:|---:|---:|---|")
    last = None
    for users in levels:
        r = run_level(args.api, tokens, users, args.duration, mix)
        values = r["all"]
        errors = ", ".join(f"{k} × {v}" for k, v in sorted(r["errors"].items())) or "aucune"
        print(
            f"| {users} | {len(values) / r['wall']:.1f} | {statistics.median(values):.0f} "
            f"| {pct(values, 0.95):.0f} | {pct(values, 0.99):.0f} | {max(values):.0f} | {errors} |",
            flush=True,
        )
        last = r
    if last is not None:
        print(f"\n#### Par écran à {last['users']} utilisateurs simultanés\n")
        print("| Écran | Appels | p50 (ms) | p95 (ms) |")
        print("|---|---:|---:|---:|")
        for label, _, _ in mix:
            values = last["by_route"].get(label, [])
            if values:
                p50, p95 = statistics.median(values), pct(values, 0.95)
                print(f"| {label} | {len(values)} | {p50:.0f} | {p95:.0f} |")
    if args.exports:
        print("\n### Exports CSV (pages de 200 lignes, plafond 5 000), première société\n")
        print("| Export | Lignes | Pages | Durée totale (ms) | Page la plus lente (ms) |")
        print("|---|---:|---:|---:|---:|")
        for label, path in (
            ("Pneus", "/tyres"),
            ("Inspections HSE", "/hse/inspections"),
            ("Incidents HSE", "/hse/incidents"),
            ("Missions (référence, sans export UI)", "/missions"),
        ):
            rows, pages, total_ms, slowest = export_pages(args.api, tokens[0], path)
            print(f"| {label} | {rows} | {pages} | {total_ms:.0f} | {slowest:.0f} |", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
