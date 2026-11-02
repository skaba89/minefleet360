"""Sous-commandes `minefleet demo …` (voir docs/DEMO_DATA_ARCHITECTURE.md)."""

import argparse
import sys
from datetime import date

from app.demo.catalog import PROFILES, TENANTS
from app.demo.guards import DemoRefused


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    demo = sub.add_parser("demo", help="environnement de démonstration (base dédiée uniquement)")
    actions = demo.add_subparsers(dest="demo_command", required=True)
    seed = actions.add_parser("seed")
    seed.add_argument("--profile", choices=sorted(PROFILES), default="small")
    seed.add_argument("--seed", type=int, default=42)
    seed.add_argument("--anchor", type=date.fromisoformat, default=None, help="date de fin AAAA-MM-JJ")
    seed.add_argument("--credentials-out", required=True, help="nouveau fichier (créé en 600)")
    verify = actions.add_parser("verify")
    verify.add_argument("--anchor", type=date.fromisoformat, default=None)
    reset = actions.add_parser("reset-credentials")
    reset.add_argument("--tenant", required=True, choices=[t.code for t in TENANTS])
    reset.add_argument("--credentials-out", required=True)


def run(args: argparse.Namespace) -> int:
    try:
        if args.demo_command == "seed":
            return _seed(args)
        if args.demo_command == "verify":
            return _verify(args)
        if args.demo_command == "reset-credentials":
            return _reset(args)
    except DemoRefused as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return 3
    return 1


def _seed(args: argparse.Namespace) -> int:
    from app.demo.credentials import ensure_new_file, write_credentials
    from app.demo.generator import seed_demo

    ensure_new_file(args.credentials_out)
    report = seed_demo(profile=args.profile, seed=args.seed, anchor=args.anchor)
    if report.skipped:
        print("Déjà présentes (inchangées) :", ", ".join(report.skipped))
    print(f"Profil {report.profile}, graine {report.seed}, ancrage {report.anchor}")
    print("Objets créés :", ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items())) or "aucun")
    if report.credentials:
        n = write_credentials(args.credentials_out, report.credentials)
        print(f"{n} identifiants écrits dans {args.credentials_out} (600) — non affichés ici.")
    return 0


def _verify(args: argparse.Namespace) -> int:
    from app.demo.verify import verify_demo

    checks = verify_demo(args.anchor)
    for c in checks:
        print(f"[{'OK' if c.ok else 'ÉCHEC'}] {c.tenant:14} {c.name} — {c.detail}")
    failed = sum(not c.ok for c in checks)
    print(f"{len(checks) - failed}/{len(checks)} contrôles réussis")
    return 1 if failed else 0


def _reset(args: argparse.Namespace) -> int:
    from app.demo.credentials import ensure_new_file, reset_credentials, write_credentials

    ensure_new_file(args.credentials_out)
    creds = reset_credentials(args.tenant)
    n = write_credentials(args.credentials_out, creds)
    print(f"{n} mots de passe régénérés pour {args.tenant} ; écrits dans {args.credentials_out} (600).")
    return 0
