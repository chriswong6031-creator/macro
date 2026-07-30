"""build_flow_desk must keep EXPRESS-LANE coverage — the #3515 freeze class.

FD-EXP (2026-07-30).  ``scripts/build_flow_desk.py`` builds site/flow_desk.html,
site/flow_desk.json and site/flowdata/cohorts.json.  It was wired in ``daily.yml``
ONLY, so those artifacts refreshed once a night while BOTH express lanes
(``render.yml`` on a push/dispatch, ``engine-render.yml`` on an ``engine/**`` push)
rebuilt the stores around them and committed the desk unchanged.  Identical class to
``build_flow_leaders`` (#3515) and ``build_research_vault`` (#3487): a page whose
builder lives in one lane while its inputs refresh in three.  An edit to the builder
or ``templates/flow_desk.html.j2`` sat unbaked until the next nightly.

ADMISSION PRECONDITION — the reason this builder was held out of the express lanes
while its options-family siblings went in: ``build()`` upserted committed ``data/``
parquets unconditionally.  #4007 closed that by gating all three write paths on
``COLLECT_LANE=nightly`` (HOUSE-U5).  :func:`test_the_admission_precondition_still_holds`
pins the gate, because deleting it would silently turn every express render back into
a ledger writer — the failure this admission depends on NOT happening.

ORDER matters twice: the desk reads ``site/flow/index.json``, which
``build_options_flow`` rewrites in the same band, so the desk must run AFTER it and
inside the same sequential cluster.

Run: .venv/bin/python -m pytest tests/test_render_flow_desk_scope.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / ".github" / "workflows" / "render.yml").read_text()
ENGINE_RENDER = (ROOT / ".github" / "workflows" / "engine-render.yml").read_text()
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
DAG = (ROOT / "config" / "dag.yml").read_text()

EXPRESS_LANES = {"render.yml": RENDER, "engine-render.yml": ENGINE_RENDER}

MODULE = "scripts.build_flow_desk"
SLUG = "flow_desk"


def _cl_gex(text: str) -> str:
    return text.split("            cl_gex() {", 1)[1].split("\n            }", 1)[0]


def _narrow_gex_case(text: str) -> str:
    return text.split("            gex)\n", 1)[1].split(";;", 1)[0]


# ------------------------------------------------------------------ band membership


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_cl_gex_builds_the_flow_desk(lane):
    assert MODULE in _cl_gex(EXPRESS_LANES[lane]), (
        f"{lane}: build_flow_desk is not a cl_gex member — flow_desk.html/json go back "
        "to refreshing only at the nightly (#3515 freeze class)"
    )


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_flow_desk_runs_after_its_manifest_producer(lane):
    """The desk reads site/flow/index.json, which build_options_flow rewrites in this
    same band — it must read THIS run's manifest, not the previous generation's.
    Mirrors daily.yml's cl_gex order."""
    cl = _cl_gex(EXPRESS_LANES[lane])
    assert cl.index("scripts.build_options_flow") < cl.index(MODULE), (
        f"{lane}: build_flow_desk must run AFTER build_options_flow inside cl_gex"
    )


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_flow_desk_has_order_membership_not_just_band_membership(lane):
    """`ORDER` is what replays a builder's log and raises its rc!=0 ::error — band
    membership without ORDER membership is a builder that runs unwatched (#3487)."""
    order = re.search(r'local ORDER="([^"]+)"', EXPRESS_LANES[lane]).group(1).split()
    assert SLUG in order, f"{lane}: {SLUG} missing from ORDER — it would run unwatched"
    assert order.index("options_flow") < order.index(SLUG), (
        f"{lane}: ORDER should replay {SLUG} after its manifest producer"
    )


# --------------------------------------------------------------- narrow scope=gex


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_narrow_gex_case_also_rebuilds_the_desk(lane):
    """A dispatched scope=gex must not drift from cl_gex — that drift is how the
    narrow case silently refreshes inputs without re-running their consumers."""
    case = _narrow_gex_case(EXPRESS_LANES[lane])
    assert MODULE in case, f"{lane}: narrow gex case never rebuilds flow_desk"
    assert case.index("scripts.build_options_flow") < case.index(MODULE), (
        f"{lane}: narrow gex case must build flow_desk after build_options_flow"
    )


# ------------------------------------------------------------------ the DAG mirror


def test_dag_declares_the_desk_in_both_express_lanes():
    """config/dag.yml is the declared shape check_dag_conformance.py diffs the live
    workflows against; an admission recorded in only one of the two is drift."""
    express_lane_blocks = [
        DAG.split(f"  - workflow: .github/workflows/{wf}\n", 1)[1].split("\n  - workflow:", 1)[0]
        for wf in ("render.yml", "engine-render.yml")
    ]
    for wf, block in zip(("render.yml", "engine-render.yml"), express_lane_blocks):
        cl = block.split("          cl_gex:\n", 1)[1].split("          cl_", 1)[0]
        assert f"- {MODULE}" in cl, f"dag.yml: {wf} lane's cl_gex omits {MODULE}"
        assert cl.index("- scripts.build_options_flow") < cl.index(f"- {MODULE}"), (
            f"dag.yml: {wf} lane must declare {MODULE} after build_options_flow"
        )


# ------------------------------------------------- the precondition for admitting it


def test_the_admission_precondition_still_holds():
    """This builder was deliberately held OUT of the express lanes until its data/
    writes were lane-gated (#4007).  If that gate is ever deleted, express renders
    become ledger writers again — so the admission above stops being safe.  Pin the
    gate here, at the admission, not only in the builder's own suite.
    """
    src = (ROOT / "scripts" / "build_flow_desk.py").read_text()
    assert "from engine.ledger_lane import nightly_advance_enabled" in src, (
        "build_flow_desk lost its lane-gate import — an express render would upsert "
        "data/flows/*.parquet again (HOUSE-U5)"
    )
    assert "if nightly_advance_enabled():" in src, (
        "build_flow_desk's proxy rebuilds are no longer lane-gated"
    )
    cohorts = (ROOT / "engine" / "flow_cohorts.py").read_text()
    assert "nightly_advance_enabled" in cohorts, (
        "engine.flow_cohorts lost its accrual lane gate — an off-nightly run would "
        "append coverage=0 rows to the cohort forward ledgers"
    )


# --------------------------------------------------------------- nightly unchanged


def test_daily_still_builds_the_desk():
    """Gate: admitting the builder to the express lanes must not disturb the nightly,
    which stays the sole advancer of its forward stores."""
    assert MODULE in DAILY, "the flow_desk step vanished from daily.yml"
