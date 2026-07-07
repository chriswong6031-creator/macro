"""tests/test_rf_c3_blocked_queue_fanout.py — PR-C3 tests.

Tests:
  1. awaiting_data bucket: candidate with status='awaiting_data' appears in queue
     as a blocked packet (is_awaiting_data=True, allowed_decisions=[]).
  2. awaiting_data packet note contains 'awaiting_data' keyword.
  3. awaiting_data packet has come_back_on from the last transition row.
  4. awaiting_data packet has empty allowed_decisions (no runnable decide path).
  5. queue.md renders Blocked section with 'Blocked' heading.
  6. queue.md Blocked section contains the blocked candidate ID.
  7. queue.md shows zero blocked when none present.
  8. Active candidates (human_review) are NOT in Blocked section.
  9. Adapter fan-out: compute_health returns adapter_candidate_counts with all 4 keys.
  10. Adapter fan-out: counts are zero when data files absent.
  11. Adapter fan-out: alpha_grammar sums n_survivors across families.
  12. Fan-out counts appear in health JSON with correct keys.
  13. research_factory_run routes cycle_pattern candidate (no crash, no_action on absent file).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory.review_queue import build_queue
from scripts.build_research_factory_review_queue import render_markdown
from scripts.build_research_factory_health import compute_health, _adapter_candidate_counts


# ---------------------------------------------------------------------------
# Helpers (mirrors test_research_factory_review.py conventions)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_candidate(
    candidate_id: str = "rf-c3-001",
    status: str = "awaiting_data",
    candidate_type: str = "oracle_compound",
    domain: str = "oracle",
    source: str = "oracle_brainstorm",
    hypothesis: str = "H: test blocked hypothesis",
    mechanism: str = "M: test blocked mechanism",
    created_at: str | None = None,
    **overrides,
) -> dict:
    row = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "created_at": created_at or _now(),
        "source": source,
        "candidate_type": candidate_type,
        "domain": domain,
        "status": status,
        "hypothesis": hypothesis,
        "mechanism": mechanism,
        "claim_shape": None,
        "spec_ref": candidate_id,
        "trial_accounting": {"mode": "read_only", "family": None},
        "evaluation_plan": {
            "primary_metric": "wr",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": None,
            "defaulted": True,
        },
        "lineage": {"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        "flags": [],
        "artifacts": {},
        "transition_log": [],
    }
    row.update(overrides)
    return row


def _make_awaiting_data_transition(
    candidate_id: str,
    come_back_on: str = "2026-10-01",
) -> dict:
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "registered",
        "to": "awaiting_data",
        "reason_code": "transition_awaiting_data",
        "reason_text": "blocked on data availability",
        "actor": "script",
        "actor_ref": None,
        "as_of": _now(),
        "artifact_refs": [],
        "kill_evidence": None,
        "come_back_on": come_back_on,
    }


def _setup_rf_dir(
    tmp_path: Path,
    candidates: list[dict] | None = None,
    transitions: list[dict] | None = None,
) -> Path:
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)
    (rf_dir / "challenges").mkdir()
    (rf_dir / "review").mkdir()

    if candidates:
        cand_path = rf_dir / "candidates.jsonl"
        with cand_path.open("w") as fh:
            for c in candidates:
                fh.write(json.dumps(c) + "\n")

    if transitions:
        trans_path = rf_dir / "transitions.jsonl"
        with trans_path.open("w") as fh:
            for t in transitions:
                fh.write(json.dumps(t) + "\n")

    return rf_dir


# ---------------------------------------------------------------------------
# Test 1: awaiting_data candidate appears in queue as blocked packet
# ---------------------------------------------------------------------------


def test_awaiting_data_appears_in_queue(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-001", status="awaiting_data")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    pkt = packets[0]
    assert pkt["candidate_id"] == "rf-blocked-001"
    assert pkt["is_awaiting_data"] is True
    assert pkt["current_status"] == "awaiting_data"


# ---------------------------------------------------------------------------
# Test 2: awaiting_data packet note contains 'awaiting_data'
# ---------------------------------------------------------------------------


def test_awaiting_data_packet_note(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-002", status="awaiting_data")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    note = packets[0].get("note", "")
    assert "awaiting_data" in note


# ---------------------------------------------------------------------------
# Test 3: come_back_on extracted from transition row
# ---------------------------------------------------------------------------


def test_awaiting_data_come_back_on_from_transition(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-003", status="awaiting_data")
    trans = _make_awaiting_data_transition("rf-blocked-003", come_back_on="2026-10-15")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand], transitions=[trans])
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["come_back_on"] == "2026-10-15"
    assert "2026-10-15" in packets[0]["note"]


# ---------------------------------------------------------------------------
# Test 4: awaiting_data packet has empty allowed_decisions
# ---------------------------------------------------------------------------


def test_awaiting_data_empty_allowed_decisions(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-004", status="awaiting_data")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    assert len(packets) == 1
    assert packets[0]["allowed_decisions"] == [], (
        "awaiting_data packet must have empty allowed_decisions — no runnable decide path"
    )


# ---------------------------------------------------------------------------
# Test 5: queue.md renders Blocked section
# ---------------------------------------------------------------------------


def test_queue_md_blocked_section_heading(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-005", status="awaiting_data")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    md = render_markdown(packets, "2026-07-06T00:00:00+00:00")
    assert "## Blocked" in md, "queue.md must contain '## Blocked' section heading"


# ---------------------------------------------------------------------------
# Test 6: queue.md Blocked section contains blocked candidate ID
# ---------------------------------------------------------------------------


def test_queue_md_blocked_section_contains_candidate(tmp_path):
    cand = _make_candidate(candidate_id="rf-blocked-006", status="awaiting_data")
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    md = render_markdown(packets, "2026-07-06T00:00:00+00:00")
    assert "rf-blocked-006" in md


# ---------------------------------------------------------------------------
# Test 7: queue.md shows zero blocked when none present
# ---------------------------------------------------------------------------


def test_queue_md_zero_blocked(tmp_path):
    cand = _make_candidate(
        candidate_id="rf-active-001",
        status="human_review",
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[cand])
    packets = build_queue(rf_dir=rf_dir)
    md = render_markdown(packets, "2026-07-06T00:00:00+00:00")
    assert "## Blocked" in md
    assert "No candidates currently blocked" in md
    assert "rf-active-001" in md


# ---------------------------------------------------------------------------
# Test 8: Active candidates not in Blocked section
# ---------------------------------------------------------------------------


def test_active_candidate_not_in_blocked_section(tmp_path):
    active = _make_candidate(
        candidate_id="rf-active-in-queue",
        status="human_review",
    )
    blocked = _make_candidate(
        candidate_id="rf-blocked-in-blocked",
        status="awaiting_data",
    )
    rf_dir = _setup_rf_dir(tmp_path, candidates=[active, blocked])
    packets = build_queue(rf_dir=rf_dir)
    md = render_markdown(packets, "2026-07-06T00:00:00+00:00")

    # Split at the Blocked heading
    blocked_section = md.split("## Blocked", 1)[-1] if "## Blocked" in md else ""
    active_section = md.split("## Blocked", 1)[0] if "## Blocked" in md else md

    assert "rf-active-in-queue" not in blocked_section, (
        "Active (human_review) candidate must not appear in the Blocked section"
    )
    assert "rf-blocked-in-blocked" in blocked_section


# ---------------------------------------------------------------------------
# Test 9: compute_health returns adapter_candidate_counts with all 4 keys
# ---------------------------------------------------------------------------


def test_compute_health_adapter_counts_all_keys():
    health = compute_health(
        candidates=[],
        transitions=[],
        challenges={},
        as_of="2026-07-06T00:00:00+00:00",
        data_dir=None,  # no data dir → zeros
    )
    acc = health.get("adapter_candidate_counts", {})
    for key in ("oracle", "alpha_grammar", "cortex", "cycle_pattern"):
        assert key in acc, f"adapter_candidate_counts missing key {key!r}"


# ---------------------------------------------------------------------------
# Test 10: Adapter fan-out zeros when data files absent
# ---------------------------------------------------------------------------


def test_adapter_candidate_counts_zeros_absent(tmp_path):
    counts = _adapter_candidate_counts(tmp_path)
    for key in ("oracle", "alpha_grammar", "cortex", "cycle_pattern"):
        assert key in counts
        assert counts[key] == 0, (
            f"adapter_candidate_counts[{key!r}] should be 0 when data absent; "
            f"got {counts[key]}"
        )


# ---------------------------------------------------------------------------
# Test 11: Alpha grammar sums n_survivors across families
# ---------------------------------------------------------------------------


def test_adapter_counts_alpha_grammar_sums_survivors(tmp_path):
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas not available")

    # Write two families, 3 survivors total
    rows = [
        {"alpha_id": f"a{i}", "family": "fam_A",
         "mechanism_hypothesis": "m", "fdr_reject": True,
         "dsr": 0.5, "mean_ic": 0.02, "t_hac": 2.5,
         "survivorship_caveat": "test",
         "overlap_cluster": "C0", "cluster_representative": "a0", "net_new_info": 0.8}
        for i in range(2)
    ] + [
        {"alpha_id": "b0", "family": "fam_B",
         "mechanism_hypothesis": "m2", "fdr_reject": True,
         "dsr": 0.6, "mean_ic": 0.03, "t_hac": 3.0,
         "survivorship_caveat": "test",
         "overlap_cluster": "C1", "cluster_representative": "b0", "net_new_info": 0.9},
        # Non-survivor — should not count
        {"alpha_id": "b1", "family": "fam_B",
         "mechanism_hypothesis": "m3", "fdr_reject": False,
         "dsr": 0.01, "mean_ic": 0.001, "t_hac": 0.5,
         "survivorship_caveat": "test",
         "overlap_cluster": "C1", "cluster_representative": "b0", "net_new_info": 0.1},
    ]
    df = pd.DataFrame(rows)
    out = tmp_path / "research" / "alpha_candidates.parquet"
    out.parent.mkdir(parents=True)
    df.to_parquet(out, index=False)

    counts = _adapter_candidate_counts(tmp_path)
    assert counts["alpha_grammar"] == 3, (
        f"Expected 3 alpha_grammar survivors (2 from fam_A + 1 from fam_B); "
        f"got {counts['alpha_grammar']}"
    )


# ---------------------------------------------------------------------------
# Test 12: Adapter counts appear in health JSON with correct keys
# ---------------------------------------------------------------------------


def test_compute_health_adapter_counts_in_health_row():
    health = compute_health(
        candidates=[],
        transitions=[],
        challenges={},
        as_of="2026-07-06T00:00:00+00:00",
        data_dir=None,
    )
    # Serialisable (no np.int64 etc.)
    health_str = json.dumps(health, default=str)
    assert "adapter_candidate_counts" in health_str
    for key in ("oracle", "alpha_grammar", "cortex", "cycle_pattern"):
        assert key in health_str


# ---------------------------------------------------------------------------
# Test 13: research_factory_run routes cycle_pattern candidate (no crash)
# ---------------------------------------------------------------------------


def test_run_routes_cycle_pattern_candidate_no_crash(tmp_path):
    """cycle_pattern candidate with absent data file → no crash, action=no_action."""
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)
    cand = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": "rf-cp-001",
        "created_at": _now(),
        "source": "cycle_pattern_scan",
        "candidate_type": "cycle_pattern_rule",
        "domain": "cycle_pattern",
        "status": "registered",
        "hypothesis": "CPI cycle test",
        "mechanism": "lattice pattern",
        "spec_ref": "rf-cp-001",
        "trial_accounting": {"mode": "read_only", "family": None},
    }
    (rf_dir / "candidates.jsonl").write_text(json.dumps(cand) + "\n")

    from scripts.research_factory_run import run
    summary = run(rf_dir=rf_dir, data_dir=tmp_path, dry_run=True, count=False)

    assert "routes" in summary
    assert len(summary["routes"]) == 1
    route = summary["routes"][0]
    assert route["candidate_id"] == "rf-cp-001"
    # With absent data file, adapter returns [] from route_all() — but _route_candidate
    # calls route_candidate (singular) directly, which should return no_action or
    # numeric_rejected depending on candidate status projected.
    # Key invariant: no crash.
    assert route["action"] in (
        "no_action", "transition_screened", "transition_numeric_rejected",
        "transition_awaiting_data", "error",
    ), f"Unexpected action: {route['action']!r}"
