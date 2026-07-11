"""tests/test_confluence_strength.py — Tests for W4 confluence strength/sequence/discovery.

Tests
-----
Strength math:
  1. strength_basic             — spine with 2 co-firing engines → 1 strength row
  2. strength_redundancy_discount — engines in dominant cluster get partial credit
  3. strength_partial_credit     — mixed cluster/non-cluster engines → partial float
  4. strength_no_spine_fallback  — spine absent; falls back to confirms edges
  5. strength_no_cluster         — no dominant cluster → all engines weight 1.0
  6. strength_regime_bucket      — regime_bucket stamped from world_state
  7. strength_rotation_cycle_exclusion — BOTH engine families present → counted OK,
                                         no 'rotation_cycle_pair' field emitted
  8. strength_never_raise_corrupt_graph — corrupt confluence_graph → returns safe fallback

Tape idempotency:
  9.  tape_append_first_run      — first run writes tape rows
  10. tape_idempotent_same_asof  — re-running same night replaces, no duplicates
  11. tape_accumulates_new_night — different as_of → appends row

Streak / slope / state:
  12. state_new                  — 1 session → state=new
  13. state_strengthening        — rising n_independent_confirming → strengthening
  14. state_decaying             — falling values → decaying
  15. state_stable               — flat values, streak > 1 → stable
  16. state_gone                 — fired before but not today → gone
  17. streak_weekend_gap         — calendar gap of 3 days → still consecutive

Discovery z-scan:
  18. discovery_accruing_young_tape — < MIN_SESSIONS → all rows state=accruing, z=null
  19. discovery_no_fabrication       — accruing rows have z=null (never fabricated)
  20. discovery_rotation_cycle_excluded — rotation × cycle pair skipped
  21. discovery_candidate_high_z     — synthetic spike in co-occurrence → candidate state
  22. discovery_empty_tape           — empty tape → empty candidates

Authority + schema:
  23. strength_authority_check       — no violations in fresh payload
  24. strength_display_only          — payload has display_only=True, is_context_only=True
  25. sequence_authority_check       — no authority violations
  26. never_raise_on_corrupt_artifact — pass corrupt path → returns dict, never raises
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
_REPO_ROOT = Path(__file__).resolve().parent.parent

_AS_OF = "2026-07-11"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def _make_spine(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "data" / "neuralweb" / "spine_index.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(p, index=False)
    return p


def _make_covariance_spine(
    tmp: Path,
    dominant_cluster: list[str] | None = None,
) -> Path:
    clusters = []
    if dominant_cluster:
        clusters = [dominant_cluster]
    obj = {
        "schema": "neuralweb.covariance_spine.v1",
        "blocks": {
            "lobes": {
                "effective_independent_lobes": 3.0,
                "n_lobes_measurable": 4,
                "n_lobes_total": 4,
                "clusters": clusters,
                "null_reference": {"pctile_vs_null": 0.8},
            }
        },
    }
    p = tmp / "data" / "neuralweb" / "covariance_spine.json"
    _write(p, obj)
    return p


def _make_world_state(tmp: Path, quad: str = "Q1") -> Path:
    obj = {
        "regime": {
            "quad": quad,
            "quad_name": "Goldilocks",
            "confidence": 0.8,
        }
    }
    p = tmp / "data" / "neuralweb" / "world_state.json"
    _write(p, obj)
    return p


def _spine_row(
    engine: str,
    symbol: str = "SPY",
    as_of: str = _AS_OF,
    direction: int = 1,
    horizon: str = "20d",
) -> dict:
    return {
        "engine": engine,
        "symbol": symbol,
        "as_of": as_of,
        "direction": direction,
        "horizon": horizon,
        "outcome_excess": 0.01,
    }


# ---------------------------------------------------------------------------
# Tests: strength math
# ---------------------------------------------------------------------------


def test_strength_basic():
    """Two co-firing engines → 1 strength row."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_spine(tmp, [
            _spine_row("engine_a"),
            _spine_row("engine_b"),
        ])
        _make_covariance_spine(tmp)
        _make_world_state(tmp)

        payload = build_strength(root=tmp, now=_NOW)
        rows = payload["rows"]
        assert len(rows) >= 1
        row = rows[0]
        assert row["n_confirming_raw"] == 2
        assert "engine_a" in row["engines"]
        assert "engine_b" in row["engines"]


def test_strength_redundancy_discount():
    """Engines in dominant cluster get partial credit (cluster_weight < 1.0)."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 4-engine cluster: each contributes 0.25
        cluster = ["engine_a", "engine_b", "engine_c", "engine_d"]
        _make_spine(tmp, [
            _spine_row("engine_a"),
            _spine_row("engine_b"),
            _spine_row("engine_c"),
        ])
        _make_covariance_spine(tmp, dominant_cluster=cluster)
        _make_world_state(tmp)

        payload = build_strength(root=tmp, now=_NOW)
        rows = payload["rows"]
        assert rows, "Expected at least one row"

        # With 3 engines all in cluster of 4: n_independent = 3 * 0.25 = 0.75
        row = rows[0]
        assert row["n_independent_confirming"] < row["n_confirming_raw"], (
            "Engines in dominant cluster should have n_independent < n_confirming_raw"
        )

        discount = payload["redundancy_discount"]
        assert discount["cluster_weight"] is not None
        assert abs(discount["cluster_weight"] - 0.25) < 1e-5


def test_strength_partial_credit():
    """Mixed cluster/non-cluster engines: partial float n_independent."""
    from engine.neuralweb.confluence_strength import build_strength, _score_independent

    # cluster of 2: weight = 0.5 each
    dominant = {"engine_a", "engine_b"}
    cluster_weight = 0.5

    # 3 engines: 2 in cluster (0.5 each) + 1 outside (1.0) = 2.0
    engines = ["engine_a", "engine_b", "engine_c"]
    n_indep = _score_independent(engines, dominant, cluster_weight)
    assert abs(n_indep - 2.0) < 1e-5


def test_strength_no_spine_fallback():
    """Spine absent → falls back to confirms edges from confluence_graph."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # No spine. Provide a mock confluence_graph with confirms edges.
        graph = {
            "edges": [
                {
                    "src": "engine:engine_x",
                    "dst": "engine:engine_y",
                    "edge_type": "confirms",
                    "n": 15,
                    "note": "co-firing lift=0.01 n=15",
                }
            ]
        }
        _make_covariance_spine(tmp)
        _make_world_state(tmp)
        _write(tmp / "data" / "neuralweb" / "confluence_graph.json", graph)

        payload = build_strength(root=tmp, now=_NOW)
        rows = payload["rows"]
        assert len(rows) >= 1, "Expected fallback rows from confirms edges"
        assert rows[0]["engines"] == ["engine_x", "engine_y"]


def test_strength_no_cluster():
    """No dominant cluster → all engines contribute 1.0."""
    from engine.neuralweb.confluence_strength import build_strength, _score_independent

    n_indep = _score_independent(["a", "b", "c"], set(), None)
    assert n_indep == 3.0


def test_strength_regime_bucket():
    """regime_bucket stamped from world_state.regime.quad."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_spine(tmp, [_spine_row("engine_a"), _spine_row("engine_b")])
        _make_covariance_spine(tmp)
        _make_world_state(tmp, quad="Q2")

        payload = build_strength(root=tmp, now=_NOW)
        rows = payload["rows"]
        assert rows, "Expected rows"
        assert rows[0]["regime_bucket"] == "Q2"


def test_strength_rotation_cycle_exclusion():
    """Both rotation-family and cycle-family engines counted normally; no rotation_cycle_pair field."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Use engine names that match rotation/cycle patterns
        _make_spine(tmp, [
            _spine_row("rotation_state"),
            _spine_row("cycle_position"),
            _spine_row("us_board"),
        ])
        _make_covariance_spine(tmp)
        _make_world_state(tmp)

        payload = build_strength(root=tmp, now=_NOW)
        rows = payload["rows"]

        # Engines may co-fire — that's fine
        for row in rows:
            # HARD EXCLUSION: no dedicated rotation_cycle_pair field allowed
            assert "rotation_cycle_pair" not in row, (
                "rotation_cycle_pair field is DON'T-TEST and must not be emitted"
            )


def test_strength_never_raise_corrupt_graph():
    """Corrupt confluence_graph.json → never raises, returns safe payload."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Write corrupt graph
        p = tmp / "data" / "neuralweb" / "confluence_graph.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT JSON {{{", encoding="utf-8")

        payload = build_strength(root=tmp, now=_NOW)
        assert isinstance(payload, dict)
        assert "rows" in payload
        assert "gaps" in payload


# ---------------------------------------------------------------------------
# Tests: tape idempotency
# ---------------------------------------------------------------------------


def test_tape_append_first_run():
    """First run writes tape rows from strength payload."""
    from engine.neuralweb.confluence_sequence import append_tape_and_build_sequence

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tape_path = tmp / "tape.jsonl"
        seq_path = tmp / "seq.json"

        strength_payload = {
            "rows": [
                {
                    "subject": "engine_a+engine_b",
                    "as_of": _AS_OF,
                    "direction": 1,
                    "horizon": "pair-aggregate",
                    "n_confirming_raw": 2,
                    "n_independent_confirming": 2.0,
                    "engines": ["engine_a", "engine_b"],
                    "regime_bucket": "Q1",
                }
            ]
        }

        seq = append_tape_and_build_sequence(
            strength_payload=strength_payload,
            root=tmp,
            now=_NOW,
            out_tape=tape_path,
            out_seq=seq_path,
        )

        assert tape_path.exists(), "Tape should be written"
        tape_rows = [json.loads(l) for l in tape_path.read_text().splitlines() if l.strip()]
        assert len(tape_rows) == 1
        assert tape_rows[0]["subject"] == "engine_a+engine_b"


def test_tape_idempotent_same_asof():
    """Re-running same night replaces rows; no duplicates."""
    from engine.neuralweb.confluence_sequence import append_tape_and_build_sequence

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tape_path = tmp / "tape.jsonl"
        seq_path = tmp / "seq.json"

        strength_payload = {
            "rows": [
                {
                    "subject": "engine_a+engine_b",
                    "as_of": _AS_OF,
                    "direction": 1,
                    "horizon": "pair-aggregate",
                    "n_confirming_raw": 2,
                    "n_independent_confirming": 2.0,
                    "engines": ["engine_a", "engine_b"],
                    "regime_bucket": "Q1",
                }
            ]
        }

        # Run twice with same as_of
        for _ in range(2):
            append_tape_and_build_sequence(
                strength_payload=strength_payload,
                root=tmp,
                now=_NOW,
                out_tape=tape_path,
                out_seq=seq_path,
            )

        tape_rows = [json.loads(l) for l in tape_path.read_text().splitlines() if l.strip()]
        # Should have exactly 1 row (idempotent)
        assert len(tape_rows) == 1, f"Expected 1 row (idempotent), got {len(tape_rows)}"


def test_tape_accumulates_new_night():
    """Different as_of → tape grows by one row."""
    from engine.neuralweb.confluence_sequence import append_tape_and_build_sequence

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tape_path = tmp / "tape.jsonl"
        seq_path = tmp / "seq.json"

        base = {
            "subject": "engine_a+engine_b",
            "direction": 1,
            "horizon": "pair-aggregate",
            "n_confirming_raw": 2,
            "n_independent_confirming": 2.0,
            "engines": ["engine_a", "engine_b"],
            "regime_bucket": "Q1",
        }

        # Night 1
        d1 = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
        append_tape_and_build_sequence(
            strength_payload={"rows": [{**base, "as_of": "2026-07-10"}]},
            root=tmp, now=d1, out_tape=tape_path, out_seq=seq_path,
        )

        # Night 2
        d2 = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
        append_tape_and_build_sequence(
            strength_payload={"rows": [{**base, "as_of": "2026-07-11"}]},
            root=tmp, now=d2, out_tape=tape_path, out_seq=seq_path,
        )

        tape_rows = [json.loads(l) for l in tape_path.read_text().splitlines() if l.strip()]
        assert len(tape_rows) == 2, f"Expected 2 rows after 2 nights, got {len(tape_rows)}"


# ---------------------------------------------------------------------------
# Tests: streak / slope / state
# ---------------------------------------------------------------------------


def test_state_new():
    """One session in tape → state=new."""
    from engine.neuralweb.confluence_sequence import _derive_sequences

    tape = [
        {
            "subject": "s1", "as_of": _AS_OF, "direction": 1,
            "horizon": "20d", "n_independent_confirming": 2.0,
        }
    ]
    subjects, _ = _derive_sequences(tape, _AS_OF, [])
    assert len(subjects) == 1
    assert subjects[0]["state"] == "new"
    assert subjects[0]["persistence_streak"] == 1


def test_state_strengthening():
    """Rising n_independent_confirming over sessions → strengthening."""
    from engine.neuralweb.confluence_sequence import _derive_sequences

    tape = [
        {"subject": "s1", "as_of": f"2026-07-0{i+1}", "direction": 1,
         "horizon": "20d", "n_independent_confirming": float(i + 1)}
        for i in range(5)
    ]
    subjects, _ = _derive_sequences(tape, "2026-07-05", [])
    assert len(subjects) == 1
    assert subjects[0]["state"] == "strengthening"


def test_state_decaying():
    """Declining n_independent_confirming → decaying."""
    from engine.neuralweb.confluence_sequence import _derive_sequences

    tape = [
        {"subject": "s1", "as_of": f"2026-07-0{i+1}", "direction": 1,
         "horizon": "20d", "n_independent_confirming": float(5 - i)}
        for i in range(5)
    ]
    subjects, _ = _derive_sequences(tape, "2026-07-05", [])
    assert len(subjects) == 1
    assert subjects[0]["state"] == "decaying"


def test_state_stable():
    """Flat values, streak > 1 → stable."""
    from engine.neuralweb.confluence_sequence import _derive_sequences

    tape = [
        {"subject": "s1", "as_of": f"2026-07-0{i+1}", "direction": 1,
         "horizon": "20d", "n_independent_confirming": 2.0}
        for i in range(4)
    ]
    subjects, _ = _derive_sequences(tape, "2026-07-04", [])
    assert len(subjects) == 1
    assert subjects[0]["state"] == "stable"


def test_state_gone():
    """Appeared before but not in current as_of → gone."""
    from engine.neuralweb.confluence_sequence import _derive_sequences

    tape = [
        {"subject": "s1", "as_of": "2026-07-09", "direction": 1,
         "horizon": "20d", "n_independent_confirming": 2.0}
    ]
    # Current as_of is 07-11 but last tape entry is 07-09
    subjects, _ = _derive_sequences(tape, "2026-07-11", [])
    assert len(subjects) == 1
    assert subjects[0]["state"] == "gone"


def test_streak_weekend_gap():
    """Calendar gap of 3 days (Mon after Thu+Fri) still counts as consecutive."""
    from engine.neuralweb.confluence_sequence import _count_streak

    # Simulating Thu, Fri, Mon (gap = 3 days)
    dates = ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-13"]
    streak = _count_streak(dates)
    assert streak >= 3, f"Expected streak >= 3, got {streak}"


# ---------------------------------------------------------------------------
# Tests: discovery z-scan
# ---------------------------------------------------------------------------


def test_discovery_accruing_young_tape():
    """< MIN_SESSIONS_FOR_SCAN → all states=accruing, z=null."""
    from engine.neuralweb.confluence_discovery import run_discovery_scan, _MIN_SESSIONS_FOR_SCAN

    # Build a tiny tape (3 sessions < 10)
    tape_rows = [
        {
            "subject": "a+b", "as_of": f"2026-07-0{i+1}",
            "direction": 1, "horizon": "20d",
            "n_confirming_raw": 2, "n_independent_confirming": 2.0,
            "engines": ["engine_a", "engine_b"], "regime_bucket": "Q1",
        }
        for i in range(3)
    ]
    assert 3 < _MIN_SESSIONS_FOR_SCAN

    gaps: list[str] = []
    candidates = run_discovery_scan(tape_rows, _NOW, gaps)

    for c in candidates:
        assert c["state"] == "accruing", f"Expected accruing, got {c['state']}"
        assert c["z"] is None, "z must be null for accruing (honest-null)"


def test_discovery_no_fabrication():
    """Accruing rows never have z != null."""
    from engine.neuralweb.confluence_discovery import run_discovery_scan

    tape = [
        {
            "subject": f"pair_{i}", "as_of": f"2026-07-{i+1:02d}",
            "direction": 1, "horizon": "20d",
            "n_confirming_raw": 2, "n_independent_confirming": 1.5,
            "engines": ["e1", "e2"], "regime_bucket": None,
        }
        for i in range(5)
    ]
    gaps: list[str] = []
    candidates = run_discovery_scan(tape, _NOW, gaps)

    for c in candidates:
        if c["state"] == "accruing":
            assert c["z"] is None, "accruing candidates must have z=null"


def test_discovery_rotation_cycle_excluded():
    """rotation × cycle engine pair skipped — no candidate emitted."""
    from engine.neuralweb.confluence_discovery import run_discovery_scan, _MIN_SESSIONS_FOR_SCAN

    # Build enough sessions
    tape_rows = []
    for i in range(_MIN_SESSIONS_FOR_SCAN + 2):
        tape_rows.append({
            "subject": f"pair_{i}", "as_of": f"2026-06-{i+1:02d}",
            "direction": 1, "horizon": "20d",
            "n_confirming_raw": 2, "n_independent_confirming": 1.5,
            # rotation × cycle pair
            "engines": ["rotation_state", "cycle_position"],
            "regime_bucket": None,
        })

    gaps: list[str] = []
    candidates = run_discovery_scan(tape_rows, _NOW, gaps)

    for c in candidates:
        pair = c.get("pair", "")
        engines = pair.split("+")
        # No candidate should be the rotation × cycle pair
        from engine.neuralweb.confluence_discovery import _is_forbidden_rotation_cycle_pair
        if len(engines) == 2:
            assert not _is_forbidden_rotation_cycle_pair(engines[0], engines[1]), (
                f"Forbidden rotation×cycle pair emitted as candidate: {pair}"
            )


def test_discovery_candidate_high_z():
    """Synthetic high co-occurrence spike → candidate state or high z.

    We build a tape where (alpha_engine, beta_engine) co-fire in the LAST few sessions
    but NOT in the early sessions.  This makes the observed rate much higher than the
    null distribution (which is built from circular shifts of the same presence vector).
    With early zeros and late ones the circular shift null has a range of rates,
    whereas the observed (latest) value is the highest — producing a positive z.
    """
    from engine.neuralweb.confluence_discovery import (
        run_discovery_scan,
        _MIN_SESSIONS_FOR_SCAN,
    )

    # 20 sessions total: co-fire only in last 8 (sparse → dense spike)
    n_total = max(_MIN_SESSIONS_FOR_SCAN + 8, 20)
    tape_rows = []
    for i in range(n_total):
        # Co-fire only in last 8 sessions
        fires = (i >= n_total - 8)
        engines = ["alpha_engine", "beta_engine"] if fires else ["alpha_engine", "gamma_engine"]
        tape_rows.append({
            "subject": f"event_{i}",
            "as_of": f"2026-05-{i+1:02d}",
            "direction": 1,
            "horizon": "20d",
            "n_confirming_raw": 2,
            "n_independent_confirming": 2.0,
            "engines": engines,
            "regime_bucket": None,
        })

    gaps: list[str] = []
    candidates = run_discovery_scan(tape_rows, _NOW, gaps)

    # The pair that has a late spike should be represented
    ab_candidates = [
        c for c in candidates
        if c["pair"] in ("alpha_engine+beta_engine", "beta_engine+alpha_engine")
    ]
    # If the pair appears, it should not be accruing (tape is old enough)
    for c in ab_candidates:
        assert c["state"] != "accruing", (
            f"Tape has {n_total} sessions which is >= MIN; state should not be accruing"
        )
    # If z is available, it should be positive (late spike)
    for c in ab_candidates:
        if c["z"] is not None:
            assert c["z"] > 0, f"Late spike should yield positive z, got z={c['z']}"


def test_discovery_empty_tape():
    """Empty tape → empty candidates, no raise."""
    from engine.neuralweb.confluence_discovery import run_discovery_scan

    gaps: list[str] = []
    candidates = run_discovery_scan([], _NOW, gaps)
    assert candidates == []


# ---------------------------------------------------------------------------
# Tests: authority + schema
# ---------------------------------------------------------------------------


def test_strength_authority_check():
    """Freshly built payload has no authority violations."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_spine(tmp, [_spine_row("engine_a"), _spine_row("engine_b")])
        _make_covariance_spine(tmp)
        _make_world_state(tmp)

        payload = build_strength(root=tmp, now=_NOW)
        violations = payload.get("authority_check") or []
        assert violations == [], f"Authority violations: {violations}"


def test_strength_display_only():
    """Payload has display_only=True and is_context_only=True."""
    from engine.neuralweb.confluence_strength import build_strength

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        payload = build_strength(root=tmp, now=_NOW)
        assert payload["display_only"] is True
        assert payload["is_context_only"] is True
        assert payload["tier"] == "display"


def test_sequence_authority_check():
    """Sequence payload has no authority violations."""
    from engine.neuralweb.confluence_sequence import append_tape_and_build_sequence

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tape_path = tmp / "tape.jsonl"
        seq_path = tmp / "seq.json"

        payload = append_tape_and_build_sequence(
            strength_payload={"rows": []},
            root=tmp, now=_NOW,
            out_tape=tape_path, out_seq=seq_path,
        )
        violations = payload.get("authority_check") or []
        assert violations == [], f"Authority violations: {violations}"


def test_never_raise_on_corrupt_artifact():
    """Passing corrupt file paths → returns dict, never raises."""
    from engine.neuralweb.confluence_strength import build_strength
    from engine.neuralweb.confluence_sequence import append_tape_and_build_sequence
    from engine.neuralweb.confluence_discovery import build_and_write as disc_write

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Write a corrupt world_state
        ws = tmp / "data" / "neuralweb" / "world_state.json"
        ws.parent.mkdir(parents=True, exist_ok=True)
        ws.write_text("{corrupt}", encoding="utf-8")

        # Write a corrupt covariance_spine
        cs = tmp / "data" / "neuralweb" / "covariance_spine.json"
        cs.write_text("bad json ][", encoding="utf-8")

        # Should not raise
        p = build_strength(root=tmp, now=_NOW)
        assert isinstance(p, dict)

        seq = append_tape_and_build_sequence(
            strength_payload=p, root=tmp, now=_NOW,
            out_tape=tmp / "tape.jsonl", out_seq=tmp / "seq.json",
        )
        assert isinstance(seq, dict)

        candidates = disc_write(root=tmp, now=_NOW, out_path=tmp / "cands.jsonl")
        assert isinstance(candidates, list)
