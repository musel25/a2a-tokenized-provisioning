"""M6.4 — the dashboard's data path: emit → JSONL → read back, and the app imports.

The Streamlit UI is interactive (needs a browser), so the test covers the crash-safe
event path (the load-bearing part) and that the app module is importable/valid; a human
watches the actual columns via `streamlit run`."""

from __future__ import annotations

from a2a_interfaces import DashboardEvent
from a2a_interfaces.fixtures import WINDOW

from e2e.dashboard import RunLog, read_events


def test_emit_appends_jsonl_and_reads_back(tmp_path):
    log = RunLog(tmp_path / "run1" / "events.jsonl")
    log.emit(WINDOW.start, "fulfill", "chain", "Ada buys ticket #7", {"entitlement_id": 7})
    log.emit(WINDOW.start + 120, "activate", "controller", "checklist passed; 50 Mbps set")
    log.emit(WINDOW.start + 120, "apply_bandwidth", "network", "policer on srl1 e1-1")

    events = read_events(log.path)
    assert [e.step for e in events] == ["fulfill", "activate", "apply_bandwidth"]
    assert [e.trust_domain for e in events] == ["chain", "controller", "network"]
    assert events[0].detail["entitlement_id"] == 7
    assert all(isinstance(e, DashboardEvent) for e in events)


def test_jsonl_is_one_object_per_line(tmp_path):
    # crash-safety: a half-written run is still readable up to the last complete line
    log = RunLog(tmp_path / "run2" / "events.jsonl")
    for i in range(3):
        log.emit(WINDOW.start + i, f"step{i}", "chain", f"line {i}")
    lines = log.path.read_text().splitlines()
    assert len(lines) == 3
    import json

    for line in lines:
        assert json.loads(line)["v"] == 0  # each line is a complete JSON object


def test_app_module_imports():
    # the Streamlit app is valid Python and its helpers work without a browser
    from e2e.dashboard import app

    assert app._newest_run is not None
    assert set(app._ICON) >= {"chain", "controller", "network", "agent"}
