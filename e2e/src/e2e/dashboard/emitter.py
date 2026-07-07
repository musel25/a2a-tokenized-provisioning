"""The dashboard's write side: append DashboardEvents as JSONL (M6.4, ADR-003).

Every component that wants to be on the live view calls `emit(...)`; the events land in
`e2e/runs/<ts>/events.jsonl`, one JSON object per line, and the Streamlit app tails it.
Append-only + one-object-per-line is the whole design: crash-safe, tail-friendly, and
readable with `cat` when there's no browser.
"""

from __future__ import annotations

from pathlib import Path

from a2a_interfaces import DashboardEvent


class RunLog:
    """One run's event log. `path` is `e2e/runs/<ts>/events.jsonl`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        ts: int,
        step: str,
        trust_domain: str,
        narration: str,
        detail: dict | None = None,
    ) -> DashboardEvent:
        event = DashboardEvent(
            ts=ts, step=step, trust_domain=trust_domain, narration=narration, detail=detail or {}
        )
        with self.path.open("a") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event


def read_events(path: Path) -> list[DashboardEvent]:
    """Load a run's events (what the dashboard tails; also handy in tests/notebooks)."""
    if not path.exists():
        return []
    return [
        DashboardEvent.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
