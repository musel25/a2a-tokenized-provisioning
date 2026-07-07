"""Lab-free coverage for the evaluation harness (docs/09). The latency/expiry/adversarial
experiments need Anvil + the live lab and are exercised by running the campaign; these two
paths — the isolated predicate microbenchmark and the summary reducer — need neither, so
they guard the harness against bit-rot in CI."""

from __future__ import annotations

import json


def test_predicate_microbenchmark_times_all_outcomes(tmp_path):
    from e2e.experiments import exp_predicate

    rows = exp_predicate(tmp_path)
    outcomes = {r["outcome"] for r in rows}
    assert outcomes == {"allow", "E_NOT_OWNER", "E_NOT_STARTED", "E_EXPIRED",
                        "E_REVOKED", "E_SCOPE", "E_CONFLICT"}
    # a pure comparison chain is nanoseconds — assert the order of magnitude the report cites
    assert all(0 < r["ns_per_call"] < 5000 for r in rows), rows
    assert (tmp_path / "predicate.jsonl").exists()


def test_stats_p95_is_not_the_max_at_n20():
    """Regression for the audited bug: int(0.95*20)=19 made p95 == max. Nearest-rank must
    land strictly below the maximum for a strictly increasing sample."""
    from e2e.experiments import _stats

    s = _stats([float(i) for i in range(20)])  # 0..19
    assert s["max"] == 19.0
    assert s["p95_nearest_rank"] < s["max"], s


def test_summarize_reduces_partial_data(tmp_path):
    from e2e.experiments import summarize

    (tmp_path / "predicate.jsonl").write_text(
        json.dumps({"exp": "predicate", "outcome": "allow", "ns_per_call": 90.0}) + "\n")
    (tmp_path / "adversarial.jsonl").write_text(
        json.dumps({"exp": "adversarial", "attack": "x", "rejected": True,
                    "layer": "controller", "code": "E_EXPIRED"}) + "\n")
    summary = summarize(tmp_path)  # must not raise on missing latency/llm/etc.
    assert summary["predicate"]["allow"] == 90.0
    assert summary["adversarial"]["rejected"] == 1
    assert (tmp_path / "summary.json").exists()
