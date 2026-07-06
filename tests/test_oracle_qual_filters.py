"""OTA W7 — Qualitative Filter Registry + PIT Stamping + Accrual tests.

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory:
(A) registry_valid_load              — three seed filters load cleanly, all fields present
(B) registry_lane_law                — unknown lane annotates + excludes from load result
(C) registry_budget_cap              — 6 active filters triggers annotation; active_filters returns ≤5
(D) stamp_idempotency                — rerun same night produces no dup rows (keep-first)
(E) stamp_null_honest                — missing source artifact → value=null, loud WARNING, never false
(F) q3_tape_touch                    — tape-touch predicate: ±3 sessions, node match, direction, schema_note skip
(G) q3_tape_no_match                 — tape row outside ±3 session window → false
(H) q2_riskoff_true                  — market_state verdict != RISK_OFF → filter true
(I) q2_riskoff_false                 — market_state verdict == RISK_OFF → filter false
(J) q2_highvix_true                  — vix_pctile >= 0.6 → filter true
(K) q2_highvix_false                 — vix_pctile < 0.6 → filter false
(L) accrual_math                     — synthetic member_fire ledger+stamps fixture; Wilson LB computed; n>=15 re-eval
(M) accrual_no_validated             — "validated" word absent from accrual output (hard ban)
(N) template_smoke                   — oracle_turn_desk.json with qual_filters_true + qual_accrual_note round-trips JSON
(O) q2_highvix_nan_is_null           — NaN vix_pctile (numpy.float64) stamps null, not false (null-honest law)
(P) registry_q1_requires_pit_law     — Q1 filter without PIT-law citation in notes is rejected
(Q) retire_to_add                    — retiring a filter and adding a replacement stays within budget
(R) stamp_only_latest_fire           — only the latest fire date per armed entry is stamped (no retro-stamp)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEED_REGISTRY = [
    {
        "id": "F-Q2-RISKOFF",
        "lane": "Q2",
        "description_en": "Market state is NOT risk-off at window open",
        "description_zh": "窗口开启时市场状态非避险",
        "source_artifact": "data/market_state/latest.json",
        "predicate": {"field": "verdict", "op": "ne", "value": "RISK_OFF"},
        "registered_at": "2026-07-06",
        "registered_by": "ota-w7",
        "status": "accruing",
        "fdr_family": "ota_qual",
        "notes": "test seed",
    },
    {
        "id": "F-Q2-HIGHVIX",
        "lane": "Q2",
        "description_en": "VIX percentile >= 0.6",
        "description_zh": "VIX百分位>=0.6",
        "source_artifact": "data/oracle/panel_s.parquet",
        "predicate": {"field": "vix_pctile", "op": "ge", "value": 0.6},
        "registered_at": "2026-07-06",
        "registered_by": "ota-w7",
        "status": "accruing",
        "fdr_family": "ota_qual",
        "notes": "test seed",
    },
    {
        "id": "F-Q3-TAPE",
        "lane": "Q3",
        "description_en": "Operator tape touch on armed node within +/-3 sessions",
        "description_zh": "运营商标注该板块±3交易日",
        "source_artifact": "data/oracle/operator_tape.jsonl",
        "predicate": {"field": "nodes", "op": "tape_touch", "within_sessions": 3},
        "registered_at": "2026-07-06",
        "registered_by": "ota-w7",
        "status": "accruing",
        "fdr_family": "ota_qual",
        "notes": "test seed",
    },
]


def _data_dir(tmp_path: Path) -> Path:
    """Return the data_dir (repo_root/data) for test fixtures.

    The evaluators resolve source_artifact via data_dir.parent (repo root),
    so we simulate the real layout: tmp_path = repo_root, data_dir = tmp_path/data.
    """
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_registry(tmp_path: Path, rows: list[dict]) -> Path:
    """Write registry.jsonl under data_dir (= tmp_path/data)."""
    data_dir = _data_dir(tmp_path)
    reg_dir = data_dir / "oracle" / "qual_filters"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg_path = reg_dir / "registry.jsonl"
    reg_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return data_dir


def _make_panel_parquet(tmp_path: Path, nodes: list[str], dates: list[str],
                         vix_vals: list[float]) -> None:
    """Build a minimal panel_s.parquet with vix_pctile column.

    source_artifact = "data/oracle/panel_s.parquet" (repo-relative).
    data_dir.parent / "data/oracle/panel_s.parquet" = tmp_path / "data/oracle/panel_s.parquet"
    """
    oracle_dir = tmp_path / "data" / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for node in nodes:
        for i, d in enumerate(dates):
            rows.append({"node": node, "date": pd.Timestamp(d),
                          "vix_pctile": vix_vals[i % len(vix_vals)]})
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_s.parquet")


def _make_market_state(tmp_path: Path, verdict: str) -> None:
    """Write market_state/latest.json at repo-root-relative path.

    source_artifact = "data/market_state/latest.json" (repo-relative).
    data_dir.parent / "data/market_state/latest.json" = tmp_path / "data/market_state/latest.json"
    """
    ms_dir = tmp_path / "data" / "market_state"
    ms_dir.mkdir(parents=True, exist_ok=True)
    (ms_dir / "latest.json").write_text(json.dumps({"verdict": verdict, "asof": "2026-07-01"}))


def _make_operator_tape(tmp_path: Path, rows: list[dict]) -> None:
    """Write operator_tape.jsonl at repo-root-relative path.

    source_artifact = "data/oracle/operator_tape.jsonl" (repo-relative).
    """
    oracle_dir = tmp_path / "data" / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    tape_path = oracle_dir / "operator_tape.jsonl"
    lines = [json.dumps({"type": "schema_note", "note": "header"})]
    lines.extend(json.dumps(r) for r in rows)
    tape_path.write_text("\n".join(lines) + "\n")


# Session calendar for tests
_DATES = [f"2026-0{m}-{d:02d}" for m in [5, 6] for d in range(1, 29)][:40]


# ---------------------------------------------------------------------------
# (A) Registry valid load
# ---------------------------------------------------------------------------

def test_registry_valid_load(tmp_path):
    data_dir = _write_registry(tmp_path, _SEED_REGISTRY)
    from engine.oracle.qual_filters import load_registry
    rows = load_registry(data_dir)
    assert len(rows) == 3
    ids = {r["id"] for r in rows}
    assert ids == {"F-Q2-RISKOFF", "F-Q2-HIGHVIX", "F-Q3-TAPE"}


# ---------------------------------------------------------------------------
# (B) Registry lane law
# ---------------------------------------------------------------------------

def test_registry_lane_law(tmp_path, caplog):
    bad_row = {**_SEED_REGISTRY[0], "id": "F-Q9-BAD", "lane": "Q9"}
    data_dir = _write_registry(tmp_path, [*_SEED_REGISTRY, bad_row])
    from engine.oracle.qual_filters import load_registry
    with caplog.at_level(logging.ERROR):
        rows = load_registry(data_dir)
    # The bad row is excluded
    assert all(r["id"] != "F-Q9-BAD" for r in rows)


# ---------------------------------------------------------------------------
# (C) Budget cap — 6 active triggers loud annotation
# ---------------------------------------------------------------------------

def test_registry_budget_cap(tmp_path, caplog):
    extra_rows = []
    for i in range(3):
        extra_rows.append({
            **_SEED_REGISTRY[0],
            "id": f"F-Q2-EXTRA{i}",
            "lane": "Q2",
            "status": "accruing",
        })
    data_dir = _write_registry(tmp_path, [*_SEED_REGISTRY, *extra_rows])
    from engine.oracle.qual_filters import load_registry, active_filters
    with caplog.at_level(logging.ERROR):
        rows = load_registry(data_dir)
    # All rows are returned by load_registry (retired filters must keep their history),
    # but active_filters() must reject the over-budget 6th filter.
    assert len(rows) == 6  # 3 seed + 3 extra (all parsed)
    assert any("budget cap" in m for m in caplog.messages)
    # Budget enforcement: only MAX_ACTIVE (5) filters are returned as active
    active = active_filters(rows)
    assert len(active) == 5, f"Expected 5 active filters after cap; got {len(active)}"


# ---------------------------------------------------------------------------
# (D) Stamp idempotency — rerun same night = no dup rows
# ---------------------------------------------------------------------------

def test_stamp_idempotency(tmp_path):
    data_dir = _write_registry(tmp_path, _SEED_REGISTRY)
    # Provide a market_state so F-Q2-RISKOFF evaluates (not null)
    _make_market_state(tmp_path, "NEUTRAL")
    # Provide panel with vix_pctile
    _make_panel_parquet(tmp_path, ["XLK"], _DATES[:10], [0.7] * 10)
    # Provide operator tape (empty, no matches)
    _make_operator_tape(tmp_path, [])

    from engine.oracle.qual_filters import stamp_window_open

    armed = [{"node": "XLK", "fire_dates": [_DATES[5]]}]
    all_dates = _DATES[:20]

    # First run
    n1 = stamp_window_open(armed, _DATES[9], data_dir, all_dates)
    stamps_path = data_dir / "oracle" / "qual_filter_stamps.jsonl"
    lines_after_run1 = [l for l in stamps_path.read_text().splitlines() if l.strip()]

    # Second run — same armed set
    n2 = stamp_window_open(armed, _DATES[9], data_dir, all_dates)
    lines_after_run2 = [l for l in stamps_path.read_text().splitlines() if l.strip()]

    assert n2 == 0, "Second run must write zero new rows (keep-first)"
    assert len(lines_after_run1) == len(lines_after_run2), "Row count must not change on rerun"


# ---------------------------------------------------------------------------
# (E) Stamp null-honest — missing source artifact → value=null, not false
# ---------------------------------------------------------------------------

def test_stamp_null_honest(tmp_path, caplog):
    """F-Q2-RISKOFF stamps null when market_state/latest.json is absent."""
    # Write only F-Q2-RISKOFF (no other sources needed for this test)
    data_dir = _write_registry(tmp_path, [_SEED_REGISTRY[0]])
    # Do NOT create data/market_state/latest.json

    from engine.oracle.qual_filters import stamp_window_open

    armed = [{"node": "XLK", "fire_dates": [_DATES[5]]}]
    all_dates = _DATES[:20]

    with caplog.at_level(logging.WARNING):
        stamp_window_open(armed, _DATES[9], data_dir, all_dates)

    stamps_path = data_dir / "oracle" / "qual_filter_stamps.jsonl"
    assert stamps_path.exists()
    for line in stamps_path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            assert row["value"] is None, "Missing source must produce null stamp, not false"

    assert any("stamp=null" in m or "missing" in m.lower() for m in caplog.messages)


# ---------------------------------------------------------------------------
# (F) Q3 tape-touch — node match, ±3 sessions, direction in, schema_note skip
# ---------------------------------------------------------------------------

def test_q3_tape_touch_match(tmp_path):
    data_dir = _write_registry(tmp_path, [_SEED_REGISTRY[2]])  # F-Q3-TAPE only
    fire_date = _DATES[10]  # position 10 in _DATES

    # Tape row: same node, direction=in, pit_stamp = fire_date (position 10 = within 3)
    tape_row = {
        "id": "tape::test", "type": "operator_tape",
        "pit_stamp": fire_date + "T12:00:00Z",
        "nodes": ["XLK"],
        "direction": "in",
        "note": "test note",
    }
    _make_operator_tape(tmp_path, [tape_row])

    from engine.oracle.qual_filters import _eval_q3_tape
    filt = _SEED_REGISTRY[2]
    result = _eval_q3_tape(filt, "XLK", fire_date, data_dir, _DATES[:30])
    assert result is True


# ---------------------------------------------------------------------------
# (G) Q3 tape — tape row outside ±3 session window → false
# ---------------------------------------------------------------------------

def test_q3_tape_outside_window(tmp_path):
    data_dir = _write_registry(tmp_path, [_SEED_REGISTRY[2]])
    fire_date = _DATES[10]

    # Tape row 10 sessions away (outside ±3)
    tape_row = {
        "id": "tape::test2", "type": "operator_tape",
        "pit_stamp": _DATES[20] + "T12:00:00Z",
        "nodes": ["XLK"],
        "direction": "in",
        "note": "test note 2",
    }
    _make_operator_tape(tmp_path, [tape_row])

    from engine.oracle.qual_filters import _eval_q3_tape
    filt = _SEED_REGISTRY[2]
    result = _eval_q3_tape(filt, "XLK", fire_date, data_dir, _DATES[:30])
    assert result is False


# ---------------------------------------------------------------------------
# (H) Q2-RISKOFF true — verdict != RISK_OFF
# ---------------------------------------------------------------------------

def test_q2_riskoff_true(tmp_path):
    data_dir = _data_dir(tmp_path)
    _make_market_state(tmp_path, "NEUTRAL")
    from engine.oracle.qual_filters import _eval_q2_riskoff
    filt = _SEED_REGISTRY[0]
    assert _eval_q2_riskoff(filt, _DATES[5], data_dir) is True


# ---------------------------------------------------------------------------
# (I) Q2-RISKOFF false — verdict == RISK_OFF
# ---------------------------------------------------------------------------

def test_q2_riskoff_false(tmp_path):
    data_dir = _data_dir(tmp_path)
    _make_market_state(tmp_path, "RISK_OFF")
    from engine.oracle.qual_filters import _eval_q2_riskoff
    filt = _SEED_REGISTRY[0]
    assert _eval_q2_riskoff(filt, _DATES[5], data_dir) is False


# ---------------------------------------------------------------------------
# (J) Q2-HIGHVIX true — vix_pctile >= 0.6
# ---------------------------------------------------------------------------

def test_q2_highvix_true(tmp_path):
    data_dir = _data_dir(tmp_path)
    dates = _DATES[:10]
    _make_panel_parquet(tmp_path, ["XLK"], dates, [0.75] * 10)
    from engine.oracle.qual_filters import _eval_q2_highvix
    filt = _SEED_REGISTRY[1]
    result = _eval_q2_highvix(filt, "XLK", dates[5], data_dir)
    assert result is True


# ---------------------------------------------------------------------------
# (K) Q2-HIGHVIX false — vix_pctile < 0.6
# ---------------------------------------------------------------------------

def test_q2_highvix_false(tmp_path):
    data_dir = _data_dir(tmp_path)
    dates = _DATES[:10]
    _make_panel_parquet(tmp_path, ["XLK"], dates, [0.35] * 10)
    from engine.oracle.qual_filters import _eval_q2_highvix
    filt = _SEED_REGISTRY[1]
    result = _eval_q2_highvix(filt, "XLK", dates[5], data_dir)
    assert result is False


# ---------------------------------------------------------------------------
# (L) Accrual math — synthetic ledger+stamps; n>=15 triggers re-eval line
# ---------------------------------------------------------------------------

def test_accrual_math(tmp_path):
    # Write registry
    data_dir = _write_registry(tmp_path, [_SEED_REGISTRY[0]])  # F-Q2-RISKOFF only

    # Build 20 windows.  Each window has ONE member_fire row (kind=member_fire)
    # with fwd_ret_21 populated — this is what _grade_turn_desk_ledger produces.
    # window_open rows never carry fwd_ret_21 (grading skips them).
    #   16 windows with filter=True (12 wins, 4 losses) → WR21 = 12/16 = 0.75
    #   4 windows with filter=False (2 wins, 2 losses)  → WR21 = 0.5
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = oracle_dir / "turn_desk_ledger.jsonl"
    stamps_path = oracle_dir / "qual_filter_stamps.jsonl"

    ledger_rows = []
    stamp_rows = []
    for i in range(20):
        fire_date = _DATES[i]
        window_key = f"XLK::a15::{fire_date}"
        is_filter_true = (i < 16)
        win = (i < 12) if is_filter_true else (i % 2 == 0)

        # window_open row — no fwd_ret_21 (mirrors real pipeline)
        ledger_rows.append({
            "kind": "window_open",
            "key": window_key,
            "node": "XLK",
            "fire_date": fire_date,
            "pit_stamp": fire_date,
            "outcome_mature": False,
            "fwd_ret_21": None,
        })
        # member_fire row — graded with fwd_ret_21 (mirrors real pipeline)
        ledger_rows.append({
            "kind": "member_fire",
            "key": f"{window_key}::AAPL",
            "window_key": window_key,
            "ticker": "AAPL",
            "node": "XLK",
            "fire_date": fire_date,
            "pit_stamp": fire_date,
            "outcome_mature": True,
            "fwd_ret_21": 0.05 if win else -0.03,
        })
        stamp_rows.append({
            "key": f"{window_key}::F-Q2-RISKOFF",
            "window_key": window_key,
            "filter_id": "F-Q2-RISKOFF",
            "value": is_filter_true,
            "stamped_asof": fire_date,
        })

    ledger_path.write_text("\n".join(json.dumps(r) for r in ledger_rows) + "\n")
    stamps_path.write_text("\n".join(json.dumps(r) for r in stamp_rows) + "\n")

    from engine.oracle.qual_filters import build_accrual_report
    report = build_accrual_report(data_dir)

    pf = report["per_filter"]["F-Q2-RISKOFF"]
    ft = pf["filter_true"]
    ff = pf["filter_false"]

    assert ft["n"] == 16
    assert abs(ft["wr21"] - 0.75) < 0.01
    assert ft["wilson_lb"] is not None and ft["wilson_lb"] >= 0.0
    assert ff["n"] == 4

    # n_true=16 >= 15 → re_evaluation_eligible key present
    assert "re_evaluation_eligible" in pf
    assert "ota_qual" in pf["re_evaluation_eligible"]


# ---------------------------------------------------------------------------
# (M) Accrual no "validated" word
# ---------------------------------------------------------------------------

def test_accrual_no_validated(tmp_path):
    data_dir = _write_registry(tmp_path, _SEED_REGISTRY)
    from engine.oracle.qual_filters import build_accrual_report
    report = build_accrual_report(data_dir)
    raw = json.dumps(report)
    assert "validated" not in raw, f"Found banned word 'validated' in accrual output"


# ---------------------------------------------------------------------------
# (N) Template smoke — qual fields survive JSON round-trip
# ---------------------------------------------------------------------------

def test_template_smoke():
    """oracle_turn_desk.json payload with qual_filters_true + qual_accrual_note is valid JSON."""
    payload = {
        "schema": "oracle_turn_desk.v1",
        "asof": "2026-07-06",
        "member_fires_asof": "2026-07-06",
        "qual_accrual_note": "Qualitative filters accruing: F-Q2-RISKOFF n=3; F-Q2-HIGHVIX n=2",
        "armed": [
            {
                "node": "XLK",
                "name_en": "Information Technology",
                "name_zh": "信息技术",
                "fire_dates": ["2026-07-01"],
                "window_end": "2026-07-15",
                "sessions_remaining": 7,
                "member_fires": [],
                "qual_filters_true": ["F-Q2-HIGHVIX"],
            }
        ],
        "base_rates": {},
        "promotion_clock": {"windows_accrued": 3, "windows_required": 15},
        "disclaimers": ["DISPLAY-WITH-EDGE"],
    }
    serialized = json.dumps(payload)
    recovered = json.loads(serialized)
    assert recovered["armed"][0]["qual_filters_true"] == ["F-Q2-HIGHVIX"]
    assert recovered["qual_accrual_note"].startswith("Qualitative filters")


# ---------------------------------------------------------------------------
# (O) NaN vix_pctile must produce null stamp, not false
# ---------------------------------------------------------------------------

def test_q2_highvix_nan_is_null(tmp_path, caplog):
    """F-Q2-HIGHVIX with NaN vix_pctile must stamp null (null-honest law).

    Reproduces the numpy.float64 type-name bug: the old guard checked
    type(val).__name__ == 'float' but numpy gives 'float64', so NaN
    fell through to float(nan) >= 0.6 which evaluates to False.
    """
    import numpy as np
    data_dir = _data_dir(tmp_path)
    dates = _DATES[:10]

    # Build panel with NaN vix_pctile
    oracle_dir = tmp_path / "data" / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "node": "XLV",
            "date": pd.Timestamp(d),
            # Use numpy NaN (the real parquet path produces numpy.float64)
            "vix_pctile": np.nan,
        })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_s.parquet")

    from engine.oracle.qual_filters import _eval_q2_highvix
    filt = _SEED_REGISTRY[1]
    with caplog.at_level(logging.WARNING):
        result = _eval_q2_highvix(filt, "XLV", dates[5], data_dir)

    assert result is None, (
        f"NaN vix_pctile must stamp null (got {result!r}); "
        f"type-name bug: numpy.float64.__name__=='float64', not 'float'"
    )
    assert any("NaN" in m or "stamp=null" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# (P) Q1 lane law — registration without PIT-law citation is rejected
# ---------------------------------------------------------------------------

def test_registry_q1_requires_pit_law_citation(tmp_path, caplog):
    """A Q1 filter without 'pit_law' in notes must be rejected at load time."""
    q1_row_bad = {
        **_SEED_REGISTRY[0],
        "id": "F-Q1-NOCITATATION",
        "lane": "Q1",
        "notes": "archival text feature, no citation here",
    }
    q1_row_good = {
        **_SEED_REGISTRY[0],
        "id": "F-Q1-WITHCITATION",
        "lane": "Q1",
        "notes": "pit_law: data/archive/sentiment_snapshot.parquet (as-of-t computed nightly)",
    }
    data_dir = _write_registry(tmp_path, [*_SEED_REGISTRY, q1_row_bad, q1_row_good])
    from engine.oracle.qual_filters import load_registry
    with caplog.at_level(logging.ERROR):
        rows = load_registry(data_dir)

    ids = {r["id"] for r in rows}
    assert "F-Q1-NOCITATATION" not in ids, "Q1 without PIT-law citation must be excluded"
    assert "F-Q1-WITHCITATION" in ids, "Q1 with PIT-law citation must be accepted"
    assert any("pit" in m.lower() or "Q1" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# (Q) Retire-to-add — retiring a filter then adding a replacement works
# ---------------------------------------------------------------------------

def test_retire_to_add(tmp_path, caplog):
    """Retiring a filter (status=retired) and adding a replacement stays within budget."""
    # Start with all 5 budget slots filled + one retired
    retired_row = {
        **_SEED_REGISTRY[0],
        "id": "F-Q2-RETIRED",
        "status": "retired",
    }
    extra_rows = []
    for i in range(2):  # 3 seed + 2 extra = 5 active (budget full)
        extra_rows.append({
            **_SEED_REGISTRY[0],
            "id": f"F-Q2-ACTIVE{i}",
            "status": "accruing",
        })
    new_row = {
        **_SEED_REGISTRY[0],
        "id": "F-Q2-NEW",
        "status": "accruing",
    }
    # 3 seed + 2 extra = 5 active + 1 retired + 1 new = budget stays at 5+1 but
    # retired doesn't count → only 6 accruing → over budget.
    # Correct retire-to-add: retire one of the extras, add new one.
    extra_rows[1]["status"] = "retired"  # retire slot to make room
    data_dir = _write_registry(tmp_path, [*_SEED_REGISTRY, *extra_rows, retired_row, new_row])
    from engine.oracle.qual_filters import load_registry, active_filters
    with caplog.at_level(logging.ERROR):
        rows = load_registry(data_dir)
    active = active_filters(rows)
    # retired rows (2) don't count; 3 seed + 1 extra (accruing) + 1 new = 5 active
    assert len(active) == 5, f"Retire-to-add should keep budget at 5; got {len(active)}"
    retired_ids = {r["id"] for r in rows if r.get("status") == "retired"}
    assert "F-Q2-RETIRED" in retired_ids
    assert "F-Q2-ACTIVE1" in retired_ids


# ---------------------------------------------------------------------------
# (R) Retro-stamp prevention — only latest fire per window gets stamped
# ---------------------------------------------------------------------------

def test_stamp_only_latest_fire(tmp_path):
    """stamp_window_open must stamp ONLY the latest fire date per armed entry.

    Stamping all historical fire_dates would retro-stamp pre-existing windows
    from before go-live (spec §5 prohibition).
    """
    data_dir = _write_registry(tmp_path, [_SEED_REGISTRY[0]])  # F-Q2-RISKOFF
    _make_market_state(tmp_path, "NEUTRAL")

    from engine.oracle.qual_filters import stamp_window_open

    # Armed entry with 3 historical fire dates — only the latest must be stamped
    all_fires = [_DATES[2], _DATES[5], _DATES[10]]
    latest = _DATES[10]
    armed = [{"node": "XLK", "fire_dates": all_fires}]
    all_dates = _DATES[:20]

    n = stamp_window_open(armed, _DATES[15], data_dir, all_dates)
    assert n == 1, f"Expected 1 stamp (latest fire only); got {n}"

    stamps_path = data_dir / "oracle" / "qual_filter_stamps.jsonl"
    stamped_windows = []
    for line in stamps_path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            stamped_windows.append(row.get("window_key", ""))

    assert all(latest in wk for wk in stamped_windows), (
        f"Only the latest fire {latest!r} should be stamped; got {stamped_windows}"
    )
    # Confirm old fire dates are not stamped
    old_fires = [_DATES[2], _DATES[5]]
    for wk in stamped_windows:
        for old in old_fires:
            assert old not in wk, f"Old fire date {old!r} was retro-stamped: {wk}"
