"""build_options_command must render at the CLOSE — the #3515 freeze class again.

2026-08-07: site/options.html showed a "SESSION CLOSED 2026-08-05" header on the
evening of Friday 2026-08-07. Nothing about the data was wrong. closing-bell.yml's
cl_gex band had refreshed every options store the lane owns — site/flow_desk.json,
whose `asof` IS that header, had already advanced to 2026-08-06 — but the lane
never ran build_options_command, so site/options.html stayed the render taken at
13:14 PDT, hours BEFORE the close, and kept reporting the previous session while
its own inputs had moved on.

Exactly the class this repo has now hit four times: a page whose builder lives in
one lane while its inputs refresh in more (build_flow_leaders #3515,
build_research_vault #3487, build_flow_desk FD-EXP #4007).

ADMISSION PRECONDITION — build_options_command is admissible to a non-nightly lane
because it is a pure re-serialisation: `write_page(site/options.html)` is its ONLY
write path, it reads data/ and never writes it, and it appends to no ledger. There
is no COLLECT_LANE gate to preserve because there is nothing to gate.
:func:`test_the_admission_precondition_still_holds` pins that, because a future
data/ write would silently turn every close render into a ledger writer.

ORDER matters: the page re-serialises stores that cl_gex writes (build_flow_desk,
build_options_screener), so it must run AFTER the band `wait` barrier — which is
precisely why daily.yml keeps it as a serial step rather than a band member.

Run: .venv/bin/python -m pytest tests/test_options_command_close_scope.py -q
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSING_BELL = (ROOT / ".github" / "workflows" / "closing-bell.yml").read_text()
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
BUILDER = (ROOT / "scripts" / "build_options_command.py").read_text()

MODULE = "scripts.build_options_command"


def test_the_close_lane_renders_the_options_workspace():
    """Without this the page reports a session its own inputs have moved past."""
    assert MODULE in CLOSING_BELL, (
        "closing-bell.yml never renders options.html — its cl_gex band refreshes "
        "flow_desk/options_screener and the page goes stale against them, which is "
        "the 2026-08-07 '08-05 close shown on 08-07' defect"
    )


def test_it_runs_after_the_band_barrier_not_inside_the_band():
    """cl_gex writes the stores this page re-serialises, so a band member could
    read the previous generation's. daily.yml keeps it serial for this reason."""
    assert CLOSING_BELL.index("cl_markets & cl_gex &") < CLOSING_BELL.index(MODULE), (
        "build_options_command must run AFTER the cl_gex band barrier"
    )


def test_it_is_non_fatal_so_a_render_failure_never_breaks_the_close_deploy():
    """Mirrors daily.yml: the last committed options.html stands instead."""
    line = next(l for l in CLOSING_BELL.splitlines() if MODULE in l)
    assert "||" in line, f"build_options_command must be non-fatal in the close lane: {line!r}"


def test_daily_and_close_agree_on_the_invocation():
    """Drift between lanes is how one of them silently stops matching the other."""
    daily_line = next(l for l in DAILY.splitlines() if MODULE in l and l.strip().startswith("run:"))
    close_line = next(l for l in CLOSING_BELL.splitlines() if MODULE in l and l.strip().startswith("run:"))
    assert daily_line.strip() == close_line.strip()


def test_the_admission_precondition_still_holds():
    """A pure re-serialiser stays admissible; a ledger writer would not.

    Deleting this guard is how a close render silently starts advancing ledgers.
    """
    assert "write_page(out_path, html)" in BUILDER, (
        "write_page is meant to be the ONLY write path for build_options_command"
    )
    for forbidden in ("to_parquet", "ledger", "nightly_advance"):
        assert forbidden not in BUILDER, (
            f"build_options_command now references {forbidden!r} — if it writes "
            "ledgers it is no longer admissible to the close lane un-gated"
        )
