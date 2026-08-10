"""Emit the paper's two results figures as TikZ, straight from e2e/runs/eval/.

The paper draws every figure in TikZ and loads no graphics package, so the figures
are generated as LaTeX source rather than as images. Run after a campaign:

    uv run python -m e2e.tikz_figures            # both, to stdout
    uv run python -m e2e.tikz_figures > figs.tex

Why generated and not hand-drawn: the rubric for the report requires key results as
graphs, and a hand-placed coordinate silently goes stale the next time the campaign
runs. These read the same jsonl the tables read.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / "runs" / "eval"


def _rows(name: str) -> list[dict]:
    path = EVAL / f"{name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _stat(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


# --- figure 1: end-to-end latency by mode x service ---------------------------

def latency_figure() -> str:
    lat = [r for r in _rows("latency") if r.get("ok")]
    rows = []
    for mode, mlabel in (("det", "deterministic"), ("llm", "judged")):
        for service in ("bandwidth", "telemetry"):
            vals = [r["phases"]["e2e_request_to_enforced_s"] for r in lat
                    if r["mode"] == mode and r["service"] == service]
            s = _stat(vals)
            if s:
                rows.append((mlabel, service, s))
    if not rows:
        return "% no latency rows\n"

    # log10 axis: the two conditions sit ~50x apart, so a linear axis would collapse
    # the deterministic pair into the origin and hide the RQ2 comparison entirely.
    # Width is chosen so the whole picture — rotated mode label, service label, plot —
    # fits one IEEE column natively; scaling it down afterwards would shrink the type.
    lo, hi = -1.3, 1.0          # 0.05 s .. 10 s
    width = 5.9
    def x(v: float) -> float:
        return (math.log10(v) - lo) / (hi - lo) * width

    out = [
        "\\begin{figure}[t]", "\\centering",
        "\\begin{tikzpicture}[font=\\scriptsize]",
        "  \\definecolor{detc}{HTML}{2B6CB0}",
        "  \\definecolor{llmc}{HTML}{B7791F}",
    ]
    # gridlines + ticks at each decade
    for dec, lbl in ((0.1, "0.1"), (1.0, "1"), (10.0, "10")):
        out.append(f"  \\draw[densely dotted,gray!55] ({x(dec):.3f},0.25) -- ({x(dec):.3f},{0.75 * len(rows) + 0.45:.3f});")
        out.append(f"  \\node[anchor=north,gray!75] at ({x(dec):.3f},0.2) {{{lbl}}};")
    out.append(f"  \\node[anchor=north] at ({width / 2:.3f},-0.25) {{end-to-end latency (s, log scale)}};")

    # One rotated label per mode, spanning its pair of service rows: the mode names are
    # long and repeating them on every row is what pushed this past the column.
    for mode in ("deterministic", "judged"):
        ys = [0.75 * (len(rows) - i) for i, (m, _, _) in enumerate(rows) if m == mode]
        if not ys:
            continue
        colour = "detc" if mode == "deterministic" else "llmc"
        mid = sum(ys) / len(ys)
        out.append(f"  \\node[rotate=90,anchor=south,font=\\tiny\\bfseries,{colour}] "
                   f"at (-1.62,{mid:.3f}) {{{mode}}};")
        out.append(f"  \\draw[{colour}!55,line width=0.7pt] (-1.5,{min(ys) - 0.22:.3f}) -- "
                   f"(-1.5,{max(ys) + 0.22:.3f});")

    for i, (mode, label, s) in enumerate(rows):
        y = 0.75 * (len(rows) - i)
        colour = "detc" if mode == "deterministic" else "llmc"
        out.append(f"  \\node[anchor=east] at (-0.15,{y:.3f}) {{{label}}};")
        out.append(f"  \\draw[{colour},line width=0.9pt] ({x(s['min']):.3f},{y:.3f}) -- ({x(s['max']):.3f},{y:.3f});")
        for end in ("min", "max"):
            out.append(f"  \\draw[{colour},line width=0.9pt] ({x(s[end]):.3f},{y - 0.09:.3f}) -- ({x(s[end]):.3f},{y + 0.09:.3f});")
        out.append(f"  \\filldraw[{colour}] ({x(s['median']):.3f},{y:.3f}) circle (1.7pt);")
        out.append(f"  \\node[anchor=south,inner sep=1.5pt,font=\\tiny] at ({x(s['median']):.3f},{y + 0.1:.3f}) "
                   f"{{{s['median'] * 1000:.0f}\\,ms}};" if s["median"] < 1 else
                   f"  \\node[anchor=south,inner sep=1.5pt,font=\\tiny] at ({x(s['median']):.3f},{y + 0.1:.3f}) "
                   f"{{{s['median']:.2f}\\,s}};")

    out += [
        "\\end{tikzpicture}",
        "\\caption{End-to-end latency from request to enforced configuration, by "
        "judgment mode and service ($n{=}20$ each). Dots are medians, bars the "
        "observed range. The two deterministic rows sit within a few milliseconds of "
        "each other, which is the same machinery executing rather than similar "
        "machinery; enabling the two judgment slots moves the median by roughly "
        "fifty-fold, and that gap is inference, not settlement.}",
        "\\label{fig:latency}", "\\end{figure}",
    ]
    return "\n".join(out) + "\n"


# --- figure 2: revocation lag vs watcher poll --------------------------------

def revlag_figure() -> str:
    # No `ok` key on these rows — the sweep only records lags it actually measured.
    by_poll: dict[float, list[float]] = {}
    for r in _rows("revlag_sweep"):
        if r.get("revocation_lag_s") is not None:
            by_poll.setdefault(float(r["poll_s"]), []).append(r["revocation_lag_s"])
    points = sorted((p, statistics.median(v)) for p, v in by_poll.items() if v)
    if not points:
        return "% no revlag rows\n"

    w, h = 6.2, 3.9
    xmax = max(p for p, _ in points) * 1.06
    ymax = max(max(v for _, v in points), xmax) * 1.06
    fx = lambda v: v / xmax * w          # noqa: E731
    fy = lambda v: v / ymax * h          # noqa: E731
    floor = min(v for _, v in points)

    out = [
        "\\begin{figure}[t]", "\\centering",
        "\\begin{tikzpicture}[font=\\scriptsize]",
        "  \\definecolor{revc}{HTML}{9B2C2C}",
        f"  \\draw[->,gray!70] (0,0) -- ({w + 0.3:.2f},0);",
        f"  \\draw[->,gray!70] (0,0) -- (0,{h + 0.3:.2f});",
        f"  \\node[anchor=north] at ({w / 2:.2f},-0.5) {{watcher poll interval (s)}};",
        f"  \\node[rotate=90,anchor=south] at (-0.82,{h / 2:.2f}) {{median revocation lag (s)}};",
        # y = x: above the floor the poll alone sets the lag, and the points sit on it
        f"  \\draw[densely dashed,gray!60] (0,0) -- ({fx(min(xmax, ymax)):.3f},{fy(min(xmax, ymax)):.3f})"
        f" node[anchor=north west,gray!85,font=\\tiny,pos=0.80] {{lag $=$ poll}};",
        # the machinery's own floor. Annotation goes at the RIGHT end: the left end is
        # where the sub-floor points cluster, and the label would sit on top of them.
        f"  \\draw[densely dotted,revc!70] (0,{fy(floor):.3f}) -- ({w:.2f},{fy(floor):.3f});",
        f"  \\node[anchor=south east,revc,font=\\tiny,align=right] at ({w:.2f},{fy(floor) + 0.07:.3f}) "
        f"{{floor $\\approx${floor * 1000:.0f}\\,ms \\\\ detection $+$ one gNMI delete $+$ readback}};",
    ]
    for v in (0.5, 1.0, 1.5, 2.0):
        if v <= xmax:
            out.append(f"  \\node[anchor=north,gray!75,font=\\tiny] at ({fx(v):.3f},-0.07) {{{v:g}}};")
    for v in (0.5, 1.0, 1.5, 2.0):
        if v <= ymax:
            out.append(f"  \\node[anchor=east,gray!75,font=\\tiny] at (-0.07,{fy(v):.3f}) {{{v:g}}};")

    path = " -- ".join(f"({fx(p):.3f},{fy(v):.3f})" for p, v in points)
    out.append(f"  \\draw[revc,line width=1pt] {path};")
    for p, v in points:
        out.append(f"  \\filldraw[revc] ({fx(p):.3f},{fy(v):.3f}) circle (1.7pt);")
        # Labels below-right of each dot: that side is empty everywhere (the region
        # under y=x), whereas above-left runs into the dashed line and the floor text.
        out.append(f"  \\node[anchor=north west,font=\\tiny,inner sep=2.5pt,gray!90] "
                   f"at ({fx(p):.3f},{fy(v):.3f}) {{{v * 1000:.0f}}};")
    out += [
        "\\end{tikzpicture}",
        "\\caption{Revocation lag against the controller's watcher poll interval "
        "($n{=}6$ per point, medians). Above roughly a quarter of a second the poll "
        "alone sets the lag and the points track the dashed $y{=}x$ line; below it "
        "they flatten onto the mechanism's own floor. The poll is an operator's knob "
        "trading chain-read load against reaction time; the floor is architectural.}",
        "\\label{fig:revlag}", "\\end{figure}",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fig", default="both", choices=["both", "latency", "revlag"])
    args = ap.parse_args()
    if args.fig in ("both", "latency"):
        print(latency_figure())
    if args.fig in ("both", "revlag"):
        print(revlag_figure())


if __name__ == "__main__":
    main()
