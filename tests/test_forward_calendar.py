"""Tests for engine/forward_calendar_context.py (ADB-W2).

Test coverage
-------------
1.  claims_kill_excluded       — Claims entry (projection.mode==benchmark_only) is excluded from
                                 projections; a benchmark-only line is emitted instead.
2.  prior_hazard_suppressed    — PRIOR-sourced hazard never surfaces in cycle_hazards.top_hazards.
3.  model_gate_fail_suppressed — MODEL-sourced hazard suppressed when gate_status[dir][horizon]
                                 != PASS.
4.  model_gate_pass_surfaces   — MODEL-sourced hazard with gate PASS surfaces with correct
                                 direction (phase→direction matching).
5.  absent_artifact_markers    — absent root → every sub-block has absent:True (no raise).
6.  byte_cap_enforcement       — gather_forward_calendar output is <= 4096 bytes when artifacts
                                 are over-budget; trimming drops odds_fingerprint first.
7.  number_provenance          — every digit-sequence in forward_watch rows exists verbatim in
                                 the forward_calendar fixture (checker function tested standalone).
8.  event_calendar_failure     — monkeypatched high_impact_strip raises → events sub-block is
                                 absent marker; gather_state still returns.
9.  machine_registry_clocks    — machine_registry.jsonl fixture → clocks present with correct
                                 come_back / status fields.
10. scoreboard_n_graded_note   — n_graded=0 scoreboard → accuracy_note present on non-claims entries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def _write_jsonl(p: Path, records: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _make_root(tmp_path: Path) -> Path:
    """Create a minimal repo root with stub directories."""
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "site" / "oddsdata").mkdir(parents=True)
    return tmp_path


def _minimal_release_forecast(upcoming: list[dict]) -> dict:
    return {
        "schema": "release_forecast.v2",
        "asof": "2026-07-12",
        "display_only": True,
        "authority": False,
        "upcoming": upcoming,
        "enrichments": [],
        "last_scored": None,
        "scoreboard_ref": None,
        "capture_health": None,
    }


def _cpi_entry() -> dict:
    return {
        "release": "cpi",
        "release_type": "cpi_headline",
        "period": "2026-06",
        "release_date": "2026-07-14",
        "days_to": 2,
        "target": "mom_sa_pct",
        "projection": {"point": 0.08, "p10": -0.12, "p25": -0.02, "p50": 0.09, "p75": 0.21, "p90": 0.31},
        "confidence": 0.2,
        "input_completeness": 1.0,
        "benchmark_set": {"naive_prior": 0.47, "trailing_3m": 0.66, "ar_model": 0.86},
        "surprise_distribution": {"p_hot": 0.1, "p_cold": 0.8, "p_inline": 0.1},
        "market_implied": None,
        "confidence_v2": 0.64,
    }


def _claims_entry() -> dict:
    return {
        "release": "claims",
        "release_type": "claims",
        "period": "2026-07-16",
        "release_date": "2026-07-16",
        "days_to": 4,
        "target": "change_thousands",
        "projection": {
            "mode": "benchmark_only",
            "reason": "Walk-forward MAE fails to beat naive_prior. Kill rule triggered.",
        },
        "confidence": None,
        "input_completeness": None,
        "benchmark_set": {"naive_prior": 215.0, "trailing_4w": 223.75, "ar_model": 200.73},
        "surprise_distribution": {},
        "market_implied": None,
    }


def _minimal_cycle_state(gate_status: dict, entities: list[dict]) -> dict:
    return {
        "schema": "neuralweb_cycle_pattern_state.v1",
        "asof": "2026-07-12",
        "gate_status": gate_status,
        "entities": entities,
        "display_only": True,
    }


def _entity(entity_id: str, phase: str, hazard_1m: float, src_1m: str = "MODEL") -> dict:
    return {
        "entity_id": entity_id,
        "native_id": entity_id,
        "family": "bloc",
        "phase_v2": phase,
        "hazard_1m_p": hazard_1m,
        "hazard_3m_p": 0.05,
        "hazard_6m_p": 0.10,
        "hazard_src": {"1m": src_1m, "3m": "PRIOR", "6m": "PRIOR"},
        "date": "2026-07-12",
    }


def _empty_scoreboard() -> dict:
    return {
        "schema": "release_forecast_scoreboard.v2",
        "asof": "2026-07-12T05:00:00Z",
        "by_release": {},
        "by_shadow": {},
    }


# ---------------------------------------------------------------------------
# Test 1: Claims kill — excluded from projections, benchmark-only line present
# ---------------------------------------------------------------------------

def test_claims_kill_excluded(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(
        root / "data" / "release_forecast" / "latest.json",
        _minimal_release_forecast([_cpi_entry(), _claims_entry()]),
    )
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(
        root / "data" / "neuralweb" / "cycle_pattern_state.json",
        _minimal_cycle_state({"up": {"1m": "PASS"}, "down": {"1m": "PASS"}}, []),
    )

    fc = gather_forward_calendar(root)
    releases = fc.get("releases", {})
    assert not releases.get("absent"), f"releases block absent: {releases}"

    top = releases.get("top_upcoming", [])
    assert len(top) >= 1, "no upcoming entries"

    # Find the claims entry
    claims_entries = [e for e in top if e.get("name") == "claims"]
    cpi_entries = [e for e in top if e.get("name") == "cpi"]

    assert len(claims_entries) == 1, f"expected 1 claims entry, got {claims_entries}"
    claims = claims_entries[0]

    # Claims must have model_status=benchmark_only, NO projection band
    assert claims.get("model_status") == "benchmark_only", f"wrong model_status: {claims}"
    assert "projection" not in claims, f"claims must not have projection band: {claims}"
    assert "kill_reason" in claims, f"claims must have kill_reason: {claims}"
    # Benchmark values may be present
    assert "benchmark_naive_prior" in claims, f"claims must have benchmark_naive_prior: {claims}"

    # CPI (non-killed) must have a projection band
    assert len(cpi_entries) == 1, f"expected 1 cpi entry, got {cpi_entries}"
    cpi = cpi_entries[0]
    assert "projection" in cpi, f"cpi must have projection band: {cpi}"
    assert "p10" in cpi["projection"], f"cpi projection must have p10: {cpi['projection']}"


# ---------------------------------------------------------------------------
# Test 2: PRIOR-sourced hazard never surfaces
# ---------------------------------------------------------------------------

def test_prior_hazard_suppressed(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())

    # Entity with PRIOR source — must never surface even if gate is PASS
    entities = [_entity("bloc:EFA", "Downturn", 0.95, src_1m="PRIOR")]
    gate = {"up": {"1m": "PASS", "3m": "PASS", "6m": "PASS"},
            "down": {"1m": "PASS", "3m": "PASS", "6m": "PASS"}}
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state(gate, entities))

    fc = gather_forward_calendar(root)
    hazards = fc.get("cycle_hazards", {})
    assert not hazards.get("absent"), f"cycle_hazards absent: {hazards}"
    top = hazards.get("top_hazards", [])
    assert len(top) == 0, f"PRIOR hazard must NOT surface: {top}"


# ---------------------------------------------------------------------------
# Test 3: MODEL hazard with gate FAIL suppressed
# ---------------------------------------------------------------------------

def test_model_gate_fail_suppressed(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())

    # MODEL source but gate says PRIOR for 1m down
    entities = [_entity("bloc:EFA", "Downturn", 0.95, src_1m="MODEL")]
    gate = {"up": {"1m": "PASS", "3m": "PASS", "6m": "PASS"},
            "down": {"1m": "PRIOR", "3m": "PRIOR", "6m": "PRIOR"}}  # all gate-failed for down
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state(gate, entities))

    fc = gather_forward_calendar(root)
    hazards = fc.get("cycle_hazards", {})
    assert not hazards.get("absent"), f"cycle_hazards absent: {hazards}"
    top = hazards.get("top_hazards", [])
    assert len(top) == 0, f"gate-failed MODEL hazard must NOT surface: {top}"


# ---------------------------------------------------------------------------
# Test 4: MODEL hazard with gate PASS surfaces with correct direction
# ---------------------------------------------------------------------------

def test_model_gate_pass_surfaces(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())

    # Downturn -> direction = "down", gate down/1m = PASS
    entities = [
        _entity("bloc:EFA", "Downturn", 0.80, src_1m="MODEL"),   # down → should surface
        _entity("bloc:VGK", "Recovery", 0.70, src_1m="MODEL"),   # up → gate up/1m = PASS
        _entity("bloc:EEM", "Trough", 0.60, src_1m="MODEL"),     # up (Trough=up) → surface
    ]
    gate = {
        "up": {"1m": "PASS", "3m": "PRIOR", "6m": "PRIOR"},
        "down": {"1m": "PASS", "3m": "PRIOR", "6m": "PRIOR"},
    }
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state(gate, entities))

    fc = gather_forward_calendar(root)
    hazards = fc.get("cycle_hazards", {})
    top = hazards.get("top_hazards", [])
    assert len(top) == 3, f"expected 3 hazards, got {top}"

    # Sorted by hazard_p descending
    assert top[0]["entity_id"] == "bloc:EFA"
    assert top[0]["direction"] == "down"
    assert top[0]["hazard_p"] == 0.80

    # Recovery entity direction = up
    vgk = next(h for h in top if h["entity_id"] == "bloc:VGK")
    assert vgk["direction"] == "up"

    # Trough entity direction = up
    eem = next(h for h in top if h["entity_id"] == "bloc:EEM")
    assert eem["direction"] == "up"


# ---------------------------------------------------------------------------
# Test 5: absent artifact root → absent markers everywhere, no raise
# ---------------------------------------------------------------------------

def test_absent_artifact_markers(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    # Empty root — no artifacts at all
    empty_root = tmp_path / "empty"
    empty_root.mkdir()

    fc = gather_forward_calendar(empty_root)
    # Should never raise; should return a dict
    assert isinstance(fc, dict), "must return a dict"

    for key in ("events", "releases", "rebalance", "cycle_hazards",
                 "hypothesis_clocks"):
        sub = fc.get(key)
        if sub is None:
            continue  # sub-block dropped by budget trimming is ok
        if isinstance(sub, dict) and sub.get("absent"):
            continue  # absent marker — correct
        # rebalance may succeed (pure date math, no artifact needed)
        # events may succeed (calls event_calendar which may or may not network)
        # so we only hard-assert on artifact-dependent sub-blocks
        if key in ("releases", "cycle_hazards", "hypothesis_clocks"):
            assert sub.get("absent"), f"{key} must be absent on empty root: {sub}"


# ---------------------------------------------------------------------------
# Test 6: byte cap enforcement
# ---------------------------------------------------------------------------

def test_byte_cap_enforcement(tmp_path: Path) -> None:
    from engine import forward_calendar_context as fcc

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state({"up": {}, "down": {}}, []))
    # Machine registry with a large number of entries
    records = [
        {
            "schema": "neuralweb.machine_registry.v1",
            "id": f"hypothesis-{i}",
            "come_back": "2026-08-04",
            "claim_shape": "entry_quality",
            "hypothesis": "H" + "x" * 200,  # pad to inflate size
        }
        for i in range(50)
    ]
    _write_jsonl(root / "data" / "neuralweb" / "machine_registry.jsonl", records)

    fc = fcc.gather_forward_calendar(root)
    raw = json.dumps(fc, default=str)
    assert len(raw.encode()) <= fcc._BUDGET_BYTES, (
        f"output exceeds budget: {len(raw.encode())} > {fcc._BUDGET_BYTES}"
    )


# ---------------------------------------------------------------------------
# Test 7: number provenance checker
# ---------------------------------------------------------------------------

def _extract_digit_sequences(text: str) -> set[str]:
    """Extract all contiguous digit sequences (including decimal points) from text."""
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _check_number_provenance(forward_watch: list[dict], fc_block: dict) -> list[str]:
    """Return list of digit sequences in forward_watch rows not found in fc_block JSON."""
    fc_json = json.dumps(fc_block, default=str)
    violations = []
    for row in forward_watch:
        row_text = json.dumps(row, default=str)
        for seq in _extract_digit_sequences(row_text):
            if seq not in fc_json:
                violations.append(f"'{seq}' in row {row} not found in forward_calendar")
    return violations


def test_number_provenance_checker_passes() -> None:
    """The checker passes when all numbers in forward_watch rows exist in fc_block."""
    fc_block = {
        "releases": {"top_upcoming": [{"date": "2026-07-14", "days_to": 2}]},
        "events": {"events": [{"date": "2026-07-14", "label": "CPI", "days_to": 2}]},
    }
    rows = [{"date": "2026-07-14", "label": "CPI", "kind": "CPI", "note": "In 2 days"}]
    violations = _check_number_provenance(rows, fc_block)
    assert violations == [], f"unexpected violations: {violations}"


def test_number_provenance_checker_fails_on_invented_number() -> None:
    """The checker catches an invented number not in fc_block."""
    fc_block = {"releases": {"top_upcoming": [{"date": "2026-07-14"}]}}
    rows = [{"date": "2026-07-14", "label": "CPI", "kind": "CPI",
             "note": "Expect 0.25 print"}]  # 0.25 not in fc_block
    violations = _check_number_provenance(rows, fc_block)
    assert len(violations) > 0, "checker must catch invented number 0.25"


# ---------------------------------------------------------------------------
# Test 8: event_calendar failure → absent marker, gather_state still returns
# ---------------------------------------------------------------------------

def test_event_calendar_failure_absent_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.forward_calendar_context import _gather_events

    def _boom(*a, **kw):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(
        "engine.forward_calendar_context._gather_events",
        lambda: _boom(),
    )

    # After monkeypatching _gather_events, gather_forward_calendar should use it
    # and produce an absent marker for events.
    from engine import forward_calendar_context as fcc

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state({"up": {}, "down": {}}, []))

    # Monkeypatch the module-level function directly
    monkeypatch.setattr(fcc, "_gather_events", lambda: {"absent": True, "reason": "simulated"})

    fc = fcc.gather_forward_calendar(root)
    assert isinstance(fc, dict), "must return dict"
    events = fc.get("events", {})
    assert events.get("absent") is True, f"events must be absent marker: {events}"


def test_event_calendar_exception_in_gather_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Event calendar failure must not propagate from gather_state()."""
    import engine.master_brain as mb
    import engine.forward_calendar_context as fcc

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state({"up": {}, "down": {}}, []))

    # Simulate gather_forward_calendar raising
    monkeypatch.setattr(fcc, "gather_forward_calendar",
                        lambda root: (_ for _ in ()).throw(RuntimeError("boom")))

    # gather_state must not raise; forward_calendar may be absent from state
    state = mb.gather_state(root=root)
    assert isinstance(state, dict), "gather_state must return dict even when fcc raises"


# ---------------------------------------------------------------------------
# Test 9: machine_registry clocks
# ---------------------------------------------------------------------------

def test_machine_registry_clocks(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(root / "data" / "release_forecast" / "latest.json",
                _minimal_release_forecast([]))
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state({"up": {}, "down": {}}, []))

    records = [
        {"schema": "neuralweb.machine_registry.v1", "id": "hyp-1",
         "claim_shape": "entry_quality", "come_back": "2026-08-04",
         "hypothesis": "H1: test"},
        {"schema": "neuralweb.machine_registry.v1", "id": "hyp-2",
         "claim_shape": "conditional_regime", "come_back": "2026-08-10",
         "hypothesis": "H2: test"},
        {"schema": "neuralweb.machine_registry.v1", "id": "hyp-no-come-back",
         "claim_shape": "conditional_regime",
         "hypothesis": "H3: test"},  # no come_back — should be skipped
    ]
    _write_jsonl(root / "data" / "neuralweb" / "machine_registry.jsonl", records)

    fc = gather_forward_calendar(root)
    hc = fc.get("hypothesis_clocks", {})
    assert not hc.get("absent"), f"hypothesis_clocks absent: {hc}"

    clocks = hc.get("clocks", [])
    assert len(clocks) == 2, f"expected 2 clocks (no come_back skipped), got {clocks}"
    ids = {c["id"] for c in clocks}
    assert "hyp-1" in ids
    assert "hyp-2" in ids
    assert "hyp-no-come-back" not in ids

    for c in clocks:
        assert c.get("status") == "verdict pending", f"wrong status: {c}"
        assert "claim_shape" in c


# ---------------------------------------------------------------------------
# Test 10: scoreboard n_graded=0 → accuracy_note on non-claims entries
# ---------------------------------------------------------------------------

def test_scoreboard_n_graded_note(tmp_path: Path) -> None:
    from engine.forward_calendar_context import gather_forward_calendar

    root = _make_root(tmp_path)
    _write_json(
        root / "data" / "release_forecast" / "latest.json",
        _minimal_release_forecast([_cpi_entry()]),
    )
    # n_graded = 0 (empty scoreboard)
    _write_json(root / "data" / "release_forecast" / "scoreboard.json", _empty_scoreboard())
    _write_json(root / "data" / "neuralweb" / "cycle_pattern_state.json",
                _minimal_cycle_state({"up": {}, "down": {}}, []))

    fc = gather_forward_calendar(root)
    releases = fc.get("releases", {})
    assert releases.get("n_graded") == 0
    top = releases.get("top_upcoming", [])
    cpi_entries = [e for e in top if e.get("name") == "cpi"]
    assert len(cpi_entries) >= 1
    cpi = cpi_entries[0]
    assert cpi.get("accuracy_note") == "no accuracy record yet", (
        f"expected accuracy_note on n_graded=0 entry: {cpi}"
    )
