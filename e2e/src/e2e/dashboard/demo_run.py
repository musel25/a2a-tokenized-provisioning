"""Generate a demo run's events.jsonl — the epilogue as DashboardEvents, so the
dashboard is watchable end to end without a full live stack (M6.4 acceptance).

  uv run python -m e2e.dashboard.demo_run   → e2e/runs/demo/events.jsonl
"""

from __future__ import annotations

from pathlib import Path

from a2a_interfaces.fixtures import WINDOW

from .emitter import RunLog

# (offset from window start, step, trust_domain, narration) — the canonical lifecycle.
_SCRIPT = [
    (-1680, "discover", "agent", "Ada's agent needs 50 Mbps hostA→hostB"),
    (-1680, "quote", "agent", "Bell's agent signs an offer: 50 Mbps / 10 TOK"),
    (-1680, "decide", "agent", "Ada's agent accepts — price within budget"),
    (-1680, "fulfill", "chain", "ticket #7 → Ada, 10 TOK → Bell, atomic"),
    (120, "challenge", "controller", "controller issues a single-use nonce"),
    (120, "activate", "controller", "checklist passed: owner, window, not revoked"),
    (120, "apply_bandwidth", "network", "gNMI Set: policer 50,000 kbps on srl1 e1-1"),
    (3000, "revoke", "chain", "Bell revokes #7 — the flag flips on-chain"),
    (3000, "teardown", "controller", "watcher observed Revoked(7) → tear down"),
    (3000, "teardown", "network", "gNMI Delete: policer gone; throughput returns"),
]


def main() -> None:
    path = Path(__file__).resolve().parents[4] / "e2e" / "runs" / "demo" / "events.jsonl"
    path.unlink(missing_ok=True)
    log = RunLog(path)
    for offset, step, domain, narration in _SCRIPT:
        log.emit(WINDOW.start + offset, step, domain, narration)
    print(f"wrote {len(_SCRIPT)} events → {path}")


if __name__ == "__main__":
    main()
