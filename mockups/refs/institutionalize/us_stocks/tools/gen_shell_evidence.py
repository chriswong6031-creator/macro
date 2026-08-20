#!/usr/bin/env python3
"""P-MP1-SHELL §11 evidence renderer — the SHIPPED shell, not the mockup.

Unlike gen_fixture.py/capture.py in this directory (which build the FROZEN
mockup's board-data.js), this script renders the REAL production template,
templates/dashboard.html.j2, against the REAL committed payload
(site/prophet/index.json + site/factordata/us_standouts.json + setups.json)
using the same synthetic vm scaffolding tests/test_dashboard_template_render.py
uses for everything this repo has no other real producer for.

Usage (from the repo root):
    python3 mockups/refs/institutionalize/us_stocks/tools/gen_shell_evidence.py <state> <out_dir>

States:
    default             real payload, unfiltered
    empty               synthetic: plans=[] (§10 empty state)
    loading             synthetic: us_prophet_book=None (§10 loading state)
    error               synthetic: us_prophet_book_error=True (§10 error state)
    watch-absent        synthetic: intake.early_turn_watch key removed
    overtime-synth      synthetic: one real 'entered' row relabelled 'overtime'
                         (N3 — zero real Overtime rows on a given night)
    watch-row-synth     synthetic: one real 'ready' row relabelled 'watch',
                         both source fields cleared (N3 — zero real Watch rows)

Writes <out_dir>/<state>.html plus copies of the static assets the page
needs (theme.css, theme.js, tier_preview.{css,js}, stocktable.js, etc.) so
the output can be served standalone (python3 -m http.server <out_dir>)
without touching the repo's own site/ tree — see CLAUDE.md's MM_DATA_GUARD:
tests/sessions must never write real data/ or site/, and an evidence
render is not exempt.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # tools/ -> us_stocks -> institutionalize -> refs -> mockups -> ROOT
sys.path.insert(0, str(ROOT))

ASSETS = [
    "theme.css", "theme.js", "tier_preview.js", "tier_preview.css",
    "nav_market.js", "live.js", "stocktable.js", "chart_i18n.js", "charts.js",
    "dashboard-icons.css", "dashboard-icons.js", "release_publications_live.js",
    "risk_state_live.js", "tablesort.js", "timemachine.js",
    "apple-touch-icon.png", "favicon.svg",
]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    state, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    from tests.test_dashboard_template_render import _base_vm, _env
    from scripts.build_site import _us_prophet_episode_map

    vm = _base_vm()
    idx = json.loads((ROOT / "site" / "prophet" / "index.json").read_text())
    su = json.loads((ROOT / "site" / "factordata" / "us_standouts.json").read_text())
    setups = json.loads((ROOT / "site" / "factordata" / "setups.json").read_text())
    vm["us_standouts"] = su
    vm["top_setups"] = setups
    vm["life_gate"] = None
    vm["us_prophet_book_error"] = False

    if state == "default" or state == "watch-zero-synth":
        vm["us_prophet_book"] = idx
        vm["us_prophet_episodes"] = _us_prophet_episode_map(idx.get("plans") or [])
    elif state == "empty":
        book = dict(idx)
        book["plans"] = []
        book["lifecycle_counts"] = {k: 0 for k in
                                     ("watch", "ready", "entered", "delivering",
                                      "overtime", "invalidated", "resolved")}
        book["lifecycle_live_total"] = 0
        book["lifecycle_grand_total"] = 0
        vm["us_prophet_book"] = book
        vm["us_prophet_episodes"] = {}
    elif state == "loading":
        vm["us_prophet_book"] = None
        vm["us_prophet_episodes"] = {}
    elif state == "error":
        vm["us_prophet_book"] = None
        vm["us_prophet_episodes"] = {}
        vm["us_prophet_book_error"] = True
    elif state == "watch-absent":
        book = dict(idx)
        book["intake"] = {k: v for k, v in (idx.get("intake") or {}).items()
                           if k != "early_turn_watch"}
        vm["us_prophet_book"] = book
        vm["us_prophet_episodes"] = _us_prophet_episode_map(idx.get("plans") or [])
    elif state in ("overtime-synth", "watch-row-synth"):
        book = json.loads(json.dumps(idx))
        donor_state = "entered" if state == "overtime-synth" else "ready"
        target_state = "overtime" if state == "overtime-synth" else "watch"
        donor = next(p for p in book["plans"] if p.get("lifecycle_state") == donor_state)
        donor["lifecycle_state"] = target_state
        donor["id"] = donor["id"] + f"-{target_state.upper()}-SYNTH"
        if state == "watch-row-synth":
            donor["entry_status"] = None
            donor["board_read"] = None
        book["plans"].insert(0, donor)
        counts = dict(book["lifecycle_counts"])
        counts[target_state] = counts.get(target_state, 0) + 1
        book["lifecycle_counts"] = counts
        book["lifecycle_grand_total"] = book.get("lifecycle_grand_total", 0) + 1
        book["lifecycle_live_total"] = book.get("lifecycle_live_total", 0) + 1
        vm["us_prophet_book"] = book
        vm["us_prophet_episodes"] = _us_prophet_episode_map(book.get("plans") or [])
    else:
        raise SystemExit(f"unknown state {state!r}")

    html = _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")
    (out_dir / f"{state}.html").write_text(html)
    print(f"wrote {out_dir / (state + '.html')} ({len(html)} bytes, state={state})")

    for asset in ASSETS:
        src = ROOT / "site" / asset
        if src.exists():
            shutil.copy(src, out_dir / asset)


if __name__ == "__main__":
    main()
