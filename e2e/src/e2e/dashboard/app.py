"""The live-run dashboard (M6.4, ADR-003): three trust-domain columns + a stepper.

Streamlit tails the newest `e2e/runs/<ts>/events.jsonl` and lays it out the way the
epilogue reads: a narration line at the top (the story, literally), then three columns —
**chain**, **controller**, **network** — because the whole point of the architecture is
*which trust domain did what*. Agent events (the two judgment slots) get their own tint.

Run:  uv run --group demo streamlit run e2e/src/e2e/dashboard/app.py
(auto-refreshes; point it at a run with `?run=<ts>` or it picks the newest.)
"""

from __future__ import annotations

from pathlib import Path

from e2e.dashboard.emitter import read_events

RUNS = Path(__file__).resolve().parents[4] / "e2e" / "runs"
_COLUMNS = ["chain", "controller", "network"]
_ICON = {"chain": "⛓️", "controller": "🚪", "network": "🤲", "agent": "🧠"}


def _newest_run() -> Path | None:
    if not RUNS.exists():
        return None
    candidates = sorted(RUNS.glob("*/events.jsonl"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="a2a live run", layout="wide")
    st.title("a2a tokenized provisioning — live run")

    run = _newest_run()
    if run is None:
        st.info("No runs yet. Start one; events append to e2e/runs/<ts>/events.jsonl.")
        return

    events = read_events(run)
    st.caption(f"run {run.parent.name} · {len(events)} events")
    if events:
        st.subheader(events[-1].narration)  # the current step, in words

    columns = st.columns(len(_COLUMNS))
    for column, domain in zip(columns, _COLUMNS, strict=True):
        column.markdown(f"### {_ICON[domain]} {domain}")
        for event in events:
            if event.trust_domain == domain:
                column.markdown(f"**{event.step}** — {event.narration}")

    agent_events = [e for e in events if e.trust_domain == "agent"]
    if agent_events:
        st.markdown("### 🧠 agent judgment (the two LLM slots)")
        for event in agent_events:
            st.markdown(f"**{event.step}** — {event.narration}")

    st.button("refresh")  # manual refresh; ADR-003's step-through mode


if __name__ == "__main__":
    main()
