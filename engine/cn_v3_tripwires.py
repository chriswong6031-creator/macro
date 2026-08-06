"""China Prophet V3 auto-tripwire specifications (G0.8 scaffolding).

CONTRACT
    This module is DATA, not a grader.  It declares the three comparisons the
    ratified V3 slate must be watched on, each with its cohort definition, its
    threshold, and the action a breach triggers.  The nightly CN loser+miss
    telemetry engine (masterplan §5 W0, ``engine/cn_prophet_audit.py``) is the
    consumer: it computes each comparison from the accrued forward ledger, writes
    the outcome into ``data/cn_prophet_audit/latest.json``, and — on a breach —
    emits a line-start ``::warning`` plus the named revert proposal.

    Nothing here reads a file, imports a dependency, or holds state.  It is
    deliberately dependency-free so the telemetry engine, a test, or an ad-hoc
    research script can all import it without dragging in pandas.

WHY IT EXISTS
    G0.8 (masterplan §0, added 2026-08-04) requires every operator-ratified direct
    wiring to ship with (a) parallel shadow grading of the displaced definition,
    (b) a NAMED auto-tripwire with its threshold and revert action, and (c) a clean
    single-commit revert path.  ``china_board_rank.v2_shadow_featured`` is (a);
    this module is (b); the single R1-R3 commit is (c).

READING THE SPECS
    ``direction`` states which side the tripwire expects to be BETTER.  A breach is
    the measured comparison going the other way by at least ``threshold`` once
    ``min_matured`` episodes have matured — never before.  ``min_matured`` is a
    floor on the SMALLER cohort: a 60-episode v3 shelf raced against 4 shadow rows
    is not a race, and reporting it as one would be the more dangerous failure.
    None of these thresholds is a promise; they are alarms that route a decision to
    the operator, and only the operator's read reverts a ratified wiring.
"""
from __future__ import annotations

from typing import Any

# The comparison cohorts are keyed on ledger columns the board store already
# carries: ``board_definition`` (append_board), ``lane`` + ``lane_reasons``
# (partition_board_rows), and the ``theme_timing`` component inside ``prophet``.
TRIPWIRES: tuple[dict[str, Any], ...] = (
    {
        "id": "cn_v3_vs_v2_shadow_winrate",
        "slate_item": "R1",
        "title": "V3 prime-window shelf vs the displaced v2 shadow shelf",
        "metric": "win_rate_pct",
        "treatment": {
            "label": "v3_featured",
            "board_definition": "cn_prophet_v3",
            "lane": "featured",
        },
        "control": {
            "label": "v2_shadow_featured",
            "board_definition": "cn_prophet_v2_shadow",
            "lane": "featured",
        },
        "direction": "treatment_higher",
        "threshold": 5.0,
        "threshold_unit": "pp",
        "min_matured": 60,
        "action": (
            "emit ::warning cn-v3-shelf-trails-shadow and propose reverting R1 "
            "(_FEATURED_ENTRY_STATUSES + _ENTRY_VALUE) to the operator"
        ),
        "evidence": "masterplan §2.3 (featured-like win 60.5% vs 78.5% excluded)",
    },
    {
        "id": "cn_v3_theme_timing_strata",
        "slate_item": "R2",
        "title": "theme_timing 1.0 bucket vs the 0.25 non-member bucket",
        "metric": "loser_rate_pct",
        "treatment": {
            "label": "theme_timing_1_0",
            "board_definition": "cn_prophet_v3",
            "theme_timing": 1.0,
        },
        "control": {
            "label": "theme_timing_0_25",
            "board_definition": "cn_prophet_v3",
            "theme_timing": 0.25,
        },
        # Loser rate is a cost, so the favoured side is the LOWER one.
        "direction": "treatment_lower",
        "threshold": 0.0,
        "threshold_unit": "pp",
        "min_matured": 60,
        "action": (
            "emit ::warning cn-v3-theme-timing-inverted and propose reverting R2 "
            "(SCORE_WEIGHTS theme_timing -> 0) to the operator"
        ),
        "evidence": (
            "masterplan §2.10 (basket member 13.1% loser rate vs 36.2% non-member; "
            "Trough+ 3.6%)"
        ),
    },
    {
        "id": "cn_v3_relay_late_demote",
        "slate_item": "R3",
        "title": "relay-late names demoted out of featured vs the featured shelf that kept them out",
        "metric": "median_excess_pct",
        "treatment": {
            "label": "relay_late_demoted",
            "board_definition": "cn_prophet_v3",
            "lane": "more_actionable",
            "lane_reason": "relay_late",
        },
        "control": {
            "label": "v3_featured",
            "board_definition": "cn_prophet_v3",
            "lane": "featured",
        },
        # The demotion is wrong if the names it moved BEAT the shelf it protected.
        "direction": "control_higher",
        "threshold": 0.0,
        "threshold_unit": "pp",
        "min_matured": 60,
        "action": (
            "emit ::warning cn-v3-relay-late-outperforms and propose reverting R3 "
            "(relay_late guard in _featured_shortfalls) to the operator"
        ),
        "evidence": (
            "PR #4506 ignition/relay study (n=406 positioned chase events): "
            "early <=1 −1.17pp/46.0% win, mid 2-3 −2.61pp/42.3%, "
            "late >=4 −5.32pp/36.0%; H=21 late −8.36pp/31.3%. The in-era §2.9 "
            "theme split it replaces was REFUTED at 12-month scale "
            "(chase x HOT −2.04pp vs chase x no-theme −1.51pp, n=7,816)."
        ),
    },
)


def tripwire_specs() -> tuple[dict[str, Any], ...]:
    """Return the three V3 tripwire specs as plain data.

    A tuple of dicts, safe to serialise straight into the W0 nightly artifact.
    Callers must not mutate the returned dicts in place — treat them as frozen.
    """
    return TRIPWIRES


def tripwire_by_id(tripwire_id: str) -> dict[str, Any] | None:
    """Return one spec by its ``id``, or ``None`` when the id is unknown."""
    for spec in TRIPWIRES:
        if spec["id"] == tripwire_id:
            return spec
    return None
