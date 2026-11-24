#!/usr/bin/env python3
"""Read-only guards protecting PostgreSQL and the application runtime during a release.

The release replaces only the API and web containers. These checks prove, without ever
printing environment variables or secrets, that:

* the PostgreSQL container is the expected, running, healthy one, backed by the expected
  named volume, and that it is the very same container (ID and start time) afterwards;
* the planned API/web containers keep the mounts (mail volume, read-only PMTiles basemap),
  networks, published ports and security settings of the running ones;
* the recreated API/web containers still have them.

Inputs are ``docker inspect`` / ``docker compose config --format json`` documents; only the
non-secret fields listed below are ever read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

APP_SERVICES = ("api", "web")
DB_DATA_PATH = "/var/lib/postgresql/data"
PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"
FIELDS = ("mounts", "networks", "ports", "cap_drop", "security_opt", "read_only", "tmpfs")


class GuardError(ValueError):
    """The runtime does not match what a safe application-only change requires."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GuardError(f"cannot read {path.name}") from error


def _ports_from_inspect(bindings: dict[str, Any] | None) -> list[str]:
    result = []
    for container_port, hosts in (bindings or {}).items():
        for host in hosts or []:
            result.append(f"{host.get('HostIp') or '0.0.0.0'}:{host.get('HostPort')}->{container_port}")
    return sorted(result)


def normalize_container(container: dict[str, Any]) -> dict[str, Any]:
    host = container.get("HostConfig") or {}
    mounts = []
    for mount in container.get("Mounts") or []:
        kind = mount.get("Type")
        source = mount.get("Name") if kind == "volume" else mount.get("Source")
        mounts.append(f"{kind}:{source}->{mount.get('Destination')}:{'rw' if mount.get('RW') else 'ro'}")
    networks = (container.get("NetworkSettings") or {}).get("Networks") or {}
    return {
        "mounts": sorted(mounts),
        "networks": sorted(networks),
        "ports": _ports_from_inspect(host.get("PortBindings")),
        "cap_drop": sorted(host.get("CapDrop") or []),
        "security_opt": sorted(host.get("SecurityOpt") or []),
        "read_only": bool(host.get("ReadonlyRootfs")),
        "tmpfs": sorted((host.get("Tmpfs") or {}).keys()),
    }


def normalize_compose_service(config: dict[str, Any], service: str) -> dict[str, Any]:
    spec = (config.get("services") or {}).get(service)
    if not isinstance(spec, dict):
        raise GuardError(f"compose service {service} is missing")
    volumes_top = config.get("volumes") or {}
    networks_top = config.get("networks") or {}
    mounts = []
    for volume in spec.get("volumes") or []:
        kind = volume.get("type")
        source = volume.get("source")
        if kind == "volume":
            source = (volumes_top.get(source) or {}).get("name") or source
        rw = "ro" if volume.get("read_only") else "rw"
        mounts.append(f"{kind}:{source}->{volume.get('target')}:{rw}")
    networks = sorted(
        (networks_top.get(name) or {}).get("name") or name for name in (spec.get("networks") or {})
    )
    ports = sorted(
        f"{port.get('host_ip') or '0.0.0.0'}:{port.get('published')}"
        f"->{port.get('target')}/{port.get('protocol') or 'tcp'}"
        for port in spec.get("ports") or []
    )
    tmpfs = spec.get("tmpfs") or []
    if isinstance(tmpfs, str):
        tmpfs = [tmpfs]
    return {
        "mounts": sorted(mounts),
        "networks": networks,
        "ports": ports,
        "cap_drop": sorted(spec.get("cap_drop") or []),
        "security_opt": sorted(spec.get("security_opt") or []),
        "read_only": bool(spec.get("read_only")),
        "tmpfs": sorted(entry.split(":", 1)[0] for entry in tmpfs),
    }


def snapshot(inspect: Any, project: str) -> dict[str, dict[str, Any]]:
    if not isinstance(inspect, list):
        raise GuardError("docker inspect output must be a list")
    result: dict[str, dict[str, Any]] = {}
    for container in inspect:
        labels = (container.get("Config") or {}).get("Labels") or {}
        if labels.get(PROJECT_LABEL) != project:
            raise GuardError("container does not belong to the expected compose project")
        service = labels.get(SERVICE_LABEL)
        if service in result:
            raise GuardError(f"several running containers for service {service}")
        result[service] = normalize_container(container)
    missing = set(APP_SERVICES) - result.keys()
    if missing:
        raise GuardError(f"running application containers missing: {sorted(missing)}")
    return result


def differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    problems = []
    for service in APP_SERVICES:
        for field in FIELDS:
            if (before.get(service) or {}).get(field) != (after.get(service) or {}).get(field):
                problems.append(
                    f"{service}.{field}: {before.get(service, {}).get(field)!r} -> "
                    f"{after.get(service, {}).get(field)!r}"
                )
    return problems


def check_invariants(state: dict[str, Any], expected_basemap: str | None) -> list[str]:
    """Properties that must hold whatever the previous runtime looked like."""
    problems = []
    web = state.get("web") or {}
    api = state.get("api") or {}
    basemap = [m for m in web.get("mounts", []) if m.split("->", 1)[-1].startswith("/srv/basemap:")]
    if len(basemap) != 1 or not basemap[0].endswith(":ro") or not basemap[0].startswith("bind:"):
        problems.append("web must mount exactly one read-only bind on /srv/basemap")
    elif expected_basemap and not basemap[0].startswith(f"bind:{expected_basemap}->"):
        problems.append("web basemap mount source differs from the expected PMTiles directory")
    if not any(m.endswith("->/data/mail:rw") and m.startswith("volume:") for m in api.get("mounts", [])):
        problems.append("api must keep its named mail volume on /data/mail")
    if not web.get("read_only") or "ALL" not in web.get("cap_drop", []):
        problems.append("web must stay read-only with all capabilities dropped")
    if not any(opt.startswith("no-new-privileges") for opt in web.get("security_opt", [])):
        problems.append("web must keep no-new-privileges")
    return problems


def check_database(inspect: Any, project: str, expected_volume: str) -> tuple[str, str]:
    if not isinstance(inspect, list) or len(inspect) != 1:
        raise GuardError("exactly one PostgreSQL container must be running")
    container = inspect[0]
    labels = (container.get("Config") or {}).get("Labels") or {}
    if labels.get(PROJECT_LABEL) != project or labels.get(SERVICE_LABEL) != "db":
        raise GuardError("PostgreSQL container does not belong to the expected project")
    state = container.get("State") or {}
    if state.get("Status") != "running" or (state.get("Health") or {}).get("Status") != "healthy":
        raise GuardError("PostgreSQL container is not running and healthy")
    data = [m for m in container.get("Mounts") or [] if m.get("Destination") == DB_DATA_PATH]
    if len(data) != 1 or data[0].get("Type") != "volume" or data[0].get("Name") != expected_volume:
        raise GuardError("PostgreSQL data directory is not the expected named volume")
    return str(container.get("Id")), str(state.get("StartedAt"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    db = sub.add_parser("database")
    db.add_argument("inspect", type=Path)
    db.add_argument("--project", required=True)
    db.add_argument("--volume", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("inspect", type=Path)
    snap.add_argument("--project", required=True)
    expected = sub.add_parser("expected")
    expected.add_argument("compose_config", type=Path)
    compare = sub.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--basemap")
    args = parser.parse_args(argv)
    try:
        if args.command == "database":
            container_id, started = check_database(_load(args.inspect), args.project, args.volume)
            print(f"{container_id} {started}")
        elif args.command == "snapshot":
            json.dump(snapshot(_load(args.inspect), args.project), sys.stdout, sort_keys=True)
        elif args.command == "expected":
            config = _load(args.compose_config)
            json.dump(
                {service: normalize_compose_service(config, service) for service in APP_SERVICES},
                sys.stdout,
                sort_keys=True,
            )
        else:
            before, after = _load(args.before), _load(args.after)
            problems = differences(before, after) + check_invariants(after, args.basemap)
            if problems:
                for problem in problems:
                    print(f"FAIL: runtime drift {problem}", file=sys.stderr)
                return 1
            print("OK: API/web mounts, networks, ports and security settings preserved")
    except GuardError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
