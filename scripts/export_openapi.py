"""Exporte le contrat OpenAPI sans démarrer de serveur ni ouvrir de connexion DB."""

import argparse
import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.dumps(
        create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True
    )
    args.output.write_text(f"{document}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
