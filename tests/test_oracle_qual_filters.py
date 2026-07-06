"""OTA W7 — Qualitative Filter Registry + PIT Stamping + Accrual tests.

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory:
(A) registry_valid_load     — three seed filters load cleanly, all fields present
(B) registry_lane_law       — unknown lane annotates + excludes from load result
(C) registry_budget_cap     — 6 active filters triggers loud annotation
(D) stamp_idempotency       — rerun same night produces no dup rows (keep-first)
(E) stamp_null_honest       — missing source artifact → value=null, loud WARNING, never false
(F) q3_tape_touch           — tape-touch predicate: ±3 sessions, node match, direction, schema_note skip
(G) q3_tape_no_match        — tape row outside ±3 session window → false
(H) q2_riskoff_true         — market_state verdict != RISK_OFF → filter true
(I) q2_riskoff_false        — market_state verdict == RISK_OFF → filter false
(J) q2_highvix_true         — vix_pctile >= 0.6 → filter true
(K) q2_highvix_false        — vix_pctile < 0.6 → filter false
(L) accrual_math            — synthetic ledger+stamps fixture; Wilson LB computed; n>=15 triggers re-eval line
(M) accrual_no_validated    — "validated" word absent from accrual output (hard ban)
(N) template_smoke          — oracle_turn_desk.json with qual_filters_true + qual_accrual_note fields round-trips JSON
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
    from engine.oracle.qual_filters import load_registry
    with caplog.at_level(logging.ERROR):
        rows = load_registry(data_dir)
    # All rows loaded but error logged
    assert len(rows) == 6  # 3 seed + 3 extra
    assert any("budget cap" in m for m in caplog.messages)


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

    # Build 20 matured window_open rows in turn_desk_ledger.jsonl
    # 16 with filter=True (12 wins, 4 losses) → WR21 = 12/16 = 0.75
    # 4 with filter=False (2 wins, 2 losses) → WR21 = 0.5
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = oracle_dir / "turn_desk_ledger.jsonl"
    stamps_path = oracle_dir / "qual_filter_stamps.jsonl"

    import random
    random.seed(42)

    ledger_rows = []
    stamp_rows = []
    for i in range(20):
        fire_date = _DATES[i]
        window_key = f"XLK::a15::{fire_date}"
        is_filter_true = (i < 16)
        win = (i < 12) if is_filter_true else (i % 2 == 0)

        ledger_rows.append({
            "kind": "window_open",
            "key": window_key,
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
