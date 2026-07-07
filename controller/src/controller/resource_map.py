"""The resource map's edge: YAML file → typed dict (ADR-005).

This is the ONE place in the whole system where a `resourceId` meets a device name.
The file format is docs/03 §5's example; the loader is deliberately strict — an entry
that is neither `kind: path` nor `kind: node` is a config error worth crashing on at
startup, not a runtime surprise.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from a2a_interfaces import ResolvedNode, ResolvedPath

DEFAULT_MAP = Path(__file__).parent / "resource_map.yaml"


def load_resource_map(path: Path | None = None) -> dict[bytes, ResolvedPath | ResolvedNode]:
    entries = yaml.safe_load((path or DEFAULT_MAP).read_text()) or {}
    resource_map: dict[bytes, ResolvedPath | ResolvedNode] = {}
    for resource_hex, spec in entries.items():
        key = bytes.fromhex(resource_hex.removeprefix("0x"))
        kind = spec.get("kind")
        if kind == "path":
            resource_map[key] = ResolvedPath(
                device=spec["device"],
                ingress_if=spec["ingress_if"],
                egress_if=spec["egress_if"],
            )
        elif kind == "node":
            resource_map[key] = ResolvedNode(device=spec["device"])
        else:
            raise ValueError(f"resource {resource_hex}: unknown kind {kind!r} (path | node)")
    return resource_map
