"""tests/test_macro_snapshot.py — R5 PR-C: macro snapshot registry tests (§6.4).

Hermetic fixtures via tmp_path.  No live data reads.

Coverage:
  (1)  build_snapshot — all sources present → expected label domains in snapshot
  (2)  build_snapshot — single source absent → fail-open, other domains populated
  (3)  _context_id — hash stability: same labels → same id; labels differ → ids differ
  (4)  write_ledger — same-asof replace on re-run (idempotent ledger rows)
  (5)  write_transitions — same-asof replace: re-run drops today rows, re-derives
  (6)  write_transitions — transition only when prev != current value
  (7)  build_snapshot — recession_risk taken VERBATIM from transmission.yield_curve.recession.risk
  (8)  build_snapshot — forex date in display format "Jul 05, 2026" → parsed to ISO
  (9)  main() — hash stability on second call (second call same id as first)
  (10) adapt_macro_context — zero rows when ledger.parquet absent (fail-open)
  (11) adapt_macro_context — correct column mapping from ledger.parquet
  (12) _market_for_row — routing table spot-checks (§6.3)
  (13) _stamp_macro_context — backward merge_asof stamps macro_context_id on spine rows
  (14) query — macro_context_id filter
  (15) query — stamp_basis filter
  (16) query — regime= default restricts to pit_live; stamp_basis='any' includes all
  (17) Max-asof join-key law: spine row dated D2 does NOT receive snapshot asof=D3
  (18) track_record rows via _stamp_macro_context get basis 'recomputed_history'
  (19) End-to-end transitions keys: from_value/to_value → _compose_macro_deltas emits from/to
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — minimal JSON fixtures
# ---------------------------------------------------------------------------

def _write_regime(tmp_path: Path, quad: str = "Q1") -> None:
    """Write data/regime/latest.json with minimal required fields matching real schema."""
    p = tmp_path / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "quad": quad,
        "transition_state": "STABLE",
        "asof": "2026-07-05",
        # cross_asset_confirm is a dict in the real schema
        "cross_asset_confirm": {"verdict": "agree", "confidence": "high"},
        # regime_vector has fused_risk_label, vol_regime, etc. nested inside
        "regime_vector": {
            "fused_risk_label": "risk-on",
            "vol_regime": "normal",
            "risk_radar_state": "neutral",
            "rate_pressure": None,
        },
    }
    (p / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_market_state(tmp_path: Path) -> None:
    """Write data/market_state/latest.json."""
    p = tmp_path / "data" / "market_state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        json.dumps({"verdict": "RISK_ON"}), encoding="utf-8"
    )


def _write_transmission(tmp_path: Path, recession_risk: str = "low") -> None:
    """Write data/transmission/latest.json with yield_curve block."""
    p = tmp_path / "data" / "transmission"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "yield_curve": {
            "recession": {"risk": recession_risk},
            "regime": {"key": "bull_flattener"},
        }
    }
    (p / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_forex(tmp_path: Path, date_str: str = "2026-07-05") -> None:
    """Write data/forex/latest.json; date_str may be ISO or display format."""
    p = tmp_path / "data" / "forex"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date_str,
        "regime": "US growth premium",
        "risk": "risk-on",
    }
    (p / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_bonds(tmp_path: Path) -> None:
    p = tmp_path / "data" / "bonds"
    p.mkdir(parents=True, exist_ok=True)
    (p / "bond_health.json").write_text(
        json.dumps({"regime": "healthy", "ig_spread": 1.1}), encoding="utf-8"
    )


def _write_commodity(tmp_path: Path) -> None:
    p = tmp_path / "data" / "commodity"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        json.dumps({"date": "2026-07-05", "regime": "range-bound", "signal": "neutral"}),
        encoding="utf-8",
    )


def _write_china_regime(tmp_path: Path, quad: str = "Q3") -> None:
    p = tmp_path / "data" / "china_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        json.dumps({"quad": quad, "risk_state": "Risk-on"}), encoding="utf-8"
    )


def _write_hk_regime(tmp_path: Path, quad: str = "Q4") -> None:
    p = tmp_path / "data" / "hk_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        json.dumps({"quad": quad, "risk_state": "Risk-off"}), encoding="utf-8"
    )


def _write_canada_regime(tmp_path: Path, quad: str = "Q1") -> None:
    p = tmp_path / "data" / "canada_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        json.dumps({"quad": quad, "risk_state": "Risk-on"}), encoding="utf-8"
    )


def _write_dispersion(tmp_path: Path) -> None:
    p = tmp_path / "data" / "dispersion"
    p.mkdir(parents=True, exist_ok=True)
    (p / "regime.json").write_text(
        json.dumps({"state": "expanding", "label": "high_dispersion"}), encoding="utf-8"
    )


def _write_all_sources(tmp_path: Path) -> None:
    """Write all standard source fixtures into tmp_path."""
    _write_regime(tmp_path)
    _write_market_state(tmp_path)
    _write_transmission(tmp_path)
    _write_forex(tmp_path)
    _write_bonds(tmp_path)
    _write_commodity(tmp_path)
    _write_china_regime(tmp_path)
    _write_hk_regime(tmp_path)
    _write_canada_regime(tmp_path)
    _write_dispersion(tmp_path)


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

import scripts.build_macro_snapshot as BMS  # noqa: E402


# ---------------------------------------------------------------------------
# (1) build_snapshot — all sources present → expected label domains
# ---------------------------------------------------------------------------

def test_build_snapshot_all_sources(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    assert "asof" in snap
    assert "macro_context_id" in snap
    labels = snap.get("labels", {})
    # At minimum us and transmission domains should be present
    assert "us" in labels, f"Expected 'us' domain in labels, got: {list(labels.keys())}"
    assert "transmission" in labels, f"Expected 'transmission' in labels"
    assert len(snap["macro_context_id"]) == 16, "context_id must be 16-char sha256 prefix"


# ---------------------------------------------------------------------------
# (2) build_snapshot — single source absent → fail-open
# ---------------------------------------------------------------------------

def test_build_snapshot_missing_source_fail_open(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)
    # Remove forex source — should not raise, other domains populated
    (tmp_path / "data" / "forex" / "latest.json").unlink()
    snap = BMS.build_snapshot(root=tmp_path)
    # Must return a dict with at least asof and macro_context_id
    assert "asof" in snap
    assert "macro_context_id" in snap
    # us domain must still be present
    assert "us" in snap.get("labels", {})


# ---------------------------------------------------------------------------
# (3) _context_id — hash stability
# ---------------------------------------------------------------------------

def test_context_id_stability() -> None:
    labels = {"us": {"quad": "Q1"}, "market": {"verdict": "RISK_ON"}}
    id1 = BMS._context_id(labels)
    id2 = BMS._context_id(labels)
    assert id1 == id2, "Same labels must produce same context_id"
    assert len(id1) == 16

    labels2 = {"us": {"quad": "Q2"}, "market": {"verdict": "RISK_ON"}}
    id3 = BMS._context_id(labels2)
    assert id1 != id3, "Different labels must produce different context_id"


def test_context_id_key_order_invariant() -> None:
    """Label key insertion order must not affect context_id (canonical sort)."""
    labels_a = {"b": {"x": 1}, "a": {"y": 2}}
    labels_b = {"a": {"y": 2}, "b": {"x": 1}}
    assert BMS._context_id(labels_a) == BMS._context_id(labels_b)


# ---------------------------------------------------------------------------
# (4) write_ledger — same-asof replace on re-run
# ---------------------------------------------------------------------------

def test_write_ledger_same_asof_replace(tmp_path: Path) -> None:
    """Re-running write_ledger for the same asof must NOT duplicate rows."""
    _write_all_sources(tmp_path)
    snap1 = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    BMS.write_ledger(snap1, out_dir)
    ledger_path = out_dir / "ledger.parquet"
    df1 = pd.read_parquet(ledger_path)
    row_count_first = len(df1)

    # Re-run with same snapshot — row count must not increase
    BMS.write_ledger(snap1, out_dir)
    df2 = pd.read_parquet(ledger_path)
    assert len(df2) == row_count_first, (
        f"Same-asof replace failed: first write={row_count_first}, second write={len(df2)}"
    )


# ---------------------------------------------------------------------------
# (5) write_transitions — same-asof replace on re-run
# ---------------------------------------------------------------------------

def test_write_transitions_same_asof_replace(tmp_path: Path) -> None:
    """Re-running write_transitions for the same asof must NOT duplicate transition lines."""
    _write_all_sources(tmp_path)
    snap1 = BMS.build_snapshot(root=tmp_path)
    # Shift snap1 to "today", build a "prior" snapshot from changed sources
    _write_regime(tmp_path, quad="Q2")
    prior_snap = BMS.build_snapshot(root=tmp_path)
    prior_snap["asof"] = "2026-07-04"
    # Restore original regime
    _write_regime(tmp_path, quad="Q1")
    snap1 = BMS.build_snapshot(root=tmp_path)

    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Write today snap first, then prior (write_ledger accumulates both asofs)
    full_ledger = BMS.write_ledger(snap1, out_dir)
    full_ledger = BMS.write_ledger(prior_snap, out_dir)

    BMS.write_transitions(snap1, full_ledger, out_dir)
    trans_path = out_dir / "transitions.jsonl"
    if trans_path.exists():
        lines1 = [l for l in trans_path.read_text(encoding="utf-8").strip().splitlines() if l]
        count1 = len(lines1)
        # Re-run same day — count must not change
        BMS.write_transitions(snap1, full_ledger, out_dir)
        lines2 = [l for l in trans_path.read_text(encoding="utf-8").strip().splitlines() if l]
        count2 = len(lines2)
        assert count2 == count1, f"same-asof replace failed on transitions: {count1} vs {count2}"


# ---------------------------------------------------------------------------
# (6) write_transitions — only transitions when prev != current
# ---------------------------------------------------------------------------

def test_write_transitions_only_on_change(tmp_path: Path) -> None:
    """No transition line should be written when labels are identical to the prior day."""
    _write_all_sources(tmp_path)
    snap_today = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_ledger = BMS.write_ledger(snap_today, out_dir)

    # Write an IDENTICAL snapshot but for yesterday's date
    import copy
    prior_snap = copy.deepcopy(snap_today)
    prior_snap["asof"] = "2026-07-04"
    full_ledger = BMS.write_ledger(prior_snap, out_dir)

    BMS.write_transitions(snap_today, full_ledger, out_dir)
    trans_path = out_dir / "transitions.jsonl"
    if trans_path.exists():
        lines = [l for l in trans_path.read_text(encoding="utf-8").strip().splitlines() if l]
        today_asof = snap_today["asof"]
        today_transitions = [
            l for l in lines
            if json.loads(l).get("asof") == today_asof
        ]
        assert len(today_transitions) == 0, (
            f"Expected no transitions when labels identical but got {len(today_transitions)}"
        )


# ---------------------------------------------------------------------------
# (7) recession_risk verbatim from transmission.yield_curve.recession.risk
# ---------------------------------------------------------------------------

def test_recession_risk_verbatim(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)
    # Override with a non-default value
    _write_transmission(tmp_path, recession_risk="elevated")
    snap = BMS.build_snapshot(root=tmp_path)
    labels = snap.get("labels", {})
    # recession_risk must appear VERBATIM in the transmission domain
    transmission_labels = labels.get("transmission", {})
    assert transmission_labels.get("recession_risk") == "elevated", (
        f"recession_risk must be verbatim from source, got: {transmission_labels}"
    )


# ---------------------------------------------------------------------------
# (8) forex date in display format → parsed to ISO
# ---------------------------------------------------------------------------

def test_forex_display_date_parsed(tmp_path: Path) -> None:
    """Date 'Jul 05, 2026' must be normalised to '2026-07-05' in the snapshot."""
    _write_all_sources(tmp_path)
    # Write forex with display-format date
    _write_forex(tmp_path, date_str="Jul 05, 2026")
    snap = BMS.build_snapshot(root=tmp_path)
    labels = snap.get("labels", {})
    fx_labels = labels.get("fx", {})
    if "date" in fx_labels:
        assert fx_labels["date"] == "2026-07-05", (
            f"Expected ISO date '2026-07-05', got: {fx_labels['date']}"
        )
    # The asof of the snapshot itself must be a valid ISO date
    asof = snap.get("asof", "")
    assert len(asof) == 10 and asof[4] == "-" and asof[7] == "-", (
        f"Snapshot asof not ISO: {asof!r}"
    )


# ---------------------------------------------------------------------------
# (9) main() — hash stability (second call same id as first)
# ---------------------------------------------------------------------------

def test_main_hash_stability(tmp_path: Path) -> None:
    """Two successive calls to build_snapshot must return the same macro_context_id."""
    _write_all_sources(tmp_path)
    snap1 = BMS.build_snapshot(root=tmp_path)
    snap2 = BMS.build_snapshot(root=tmp_path)
    assert snap1["macro_context_id"] == snap2["macro_context_id"], (
        "macro_context_id must be stable across two identical calls"
    )


# ---------------------------------------------------------------------------
# (10) adapt_macro_context — zero rows when ledger.parquet absent (fail-open)
# ---------------------------------------------------------------------------

def test_adapt_macro_context_absent_ledger(tmp_path: Path) -> None:
    from engine.neuralweb.query import adapt_macro_context
    df, gaps = adapt_macro_context(root=tmp_path)
    assert df.empty, "Expected empty frame when ledger.parquet absent"
    assert any("absent" in g.lower() or "zero rows" in g.lower() for g in gaps), (
        f"Expected gap note about absent ledger, got: {gaps}"
    )


# ---------------------------------------------------------------------------
# (11) adapt_macro_context — correct column mapping from ledger.parquet
# ---------------------------------------------------------------------------

def test_adapt_macro_context_column_mapping(tmp_path: Path) -> None:
    """Write a minimal ledger.parquet and check adapt_macro_context output columns."""
    from engine.neuralweb.query import adapt_macro_context, COLUMNS

    _write_all_sources(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    BMS.write_ledger(snap, out_dir)

    df, gaps = adapt_macro_context(root=tmp_path)
    assert not df.empty, f"Expected rows from valid ledger.parquet; gaps={gaps}"

    # Every COLUMNS entry must be present
    for col in COLUMNS:
        assert col in df.columns, f"Missing column {col!r} in adapt_macro_context output"

    # Contract checks
    assert (df["ledger"] == "macro_context").all(), "ledger must be 'macro_context'"
    assert (df["scope_type"] == "macro").all(), "scope_type must be 'macro'"
    assert (df["is_context"] == True).all(), "is_context must be True"  # noqa: E712
    assert (df["regime_stamp_basis"] == "pit_live").all(), "regime_stamp_basis must be 'pit_live'"
    assert (df["market"].isna()).all(), "market must be None for macro rows"

    # signal_id format: 'macro_context:{asof}:{domain}'
    for sid in df["signal_id"]:
        parts = sid.split(":")
        assert parts[0] == "macro_context", f"Bad signal_id prefix: {sid!r}"
        assert len(parts) >= 3, f"signal_id too short: {sid!r}"


# ---------------------------------------------------------------------------
# (12) _market_for_row — routing table spot-checks (§6.3)
# ---------------------------------------------------------------------------

def test_market_routing() -> None:
    from engine.neuralweb.query import _market_for_row

    assert _market_for_row("board_hk", "0700.HK") == "HK"
    assert _market_for_row("board_ca", "SHOP.TO") == "CA"
    assert _market_for_row("board_cn", "300725.SZ") == "CN"
    assert _market_for_row("track_record", "AAPL") == "US"
    assert _market_for_row("spine", "MSFT") == "US"
    assert _market_for_row("options_entry", "SPY") == "US"
    assert _market_for_row("qledger", "AAPL") == "US"
    assert _market_for_row("qledger", "300725.SS") == "CN"
    assert _market_for_row("qledger", "300725.SZ") == "CN"
    assert _market_for_row("qledger", "0700.HK") == "HK"
    assert _market_for_row("macro_context", None) is None
    assert _market_for_row("cortex_attention", "SPY") is None
    assert _market_for_row(None, None) is None


# ---------------------------------------------------------------------------
# (13) _stamp_macro_context — backward merge_asof stamps on spine rows
# ---------------------------------------------------------------------------

def test_stamp_macro_context_backward_join(tmp_path: Path) -> None:
    """Rows at or after macro snapshot asof must receive macro_context_id."""
    from engine.neuralweb.query import _stamp_macro_context, COLUMNS

    # Write a macro snapshot
    _write_all_sources(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    snap["asof"] = "2026-07-01"
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    BMS.write_ledger(snap, out_dir)

    # Build a test combined frame
    rows = [
        {"signal_id": "s1", "as_of": "2026-07-01", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
        {"signal_id": "s2", "as_of": "2026-07-05", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
        # Before snapshot — should stay None
        {"signal_id": "s3", "as_of": "2026-06-30", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
    ]
    combined = pd.DataFrame(rows)
    # Add all COLUMNS with None defaults
    for col in COLUMNS:
        if col not in combined.columns:
            combined[col] = None

    result = _stamp_macro_context(combined, root=tmp_path)

    # Rows on/after 2026-07-01 get stamped
    r1 = result[result["signal_id"] == "s1"].iloc[0]
    r2 = result[result["signal_id"] == "s2"].iloc[0]
    r3 = result[result["signal_id"] == "s3"].iloc[0]

    assert r1["macro_context_id"] == snap["macro_context_id"], "Row on snapshot asof must be stamped"
    assert r2["macro_context_id"] == snap["macro_context_id"], "Row after snapshot asof must be stamped"
    assert r3["macro_context_id"] is None or str(r3["macro_context_id"]) == "None", (
        "Row before snapshot asof must stay None"
    )


# ---------------------------------------------------------------------------
# (14) query — macro_context_id filter
# ---------------------------------------------------------------------------

def test_query_macro_context_id_filter(tmp_path: Path) -> None:
    """query(macro_context_id=X) must return only rows with that id."""
    from engine.neuralweb.query import query, COLUMNS

    id_a = "abcd1234abcd1234"
    id_b = "ffff0000ffff0000"
    rows = [
        {"signal_id": "r1", "macro_context_id": id_a},
        {"signal_id": "r2", "macro_context_id": id_b},
        {"signal_id": "r3", "macro_context_id": id_a},
    ]
    df = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    result = query(df=df, macro_context_id=id_a)
    assert len(result) == 2
    assert set(result["signal_id"]) == {"r1", "r3"}


# ---------------------------------------------------------------------------
# (15) query — stamp_basis filter
# ---------------------------------------------------------------------------

def test_query_stamp_basis_filter(tmp_path: Path) -> None:
    """query(stamp_basis='pit_live') must return only rows with regime_stamp_basis='pit_live'."""
    from engine.neuralweb.query import query, COLUMNS

    rows = [
        {"signal_id": "r1", "regime_stamp_basis": "pit_live"},
        {"signal_id": "r2", "regime_stamp_basis": "recomputed_history"},
        {"signal_id": "r3", "regime_stamp_basis": "pit_live"},
    ]
    df = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    result = query(df=df, stamp_basis="pit_live")
    assert len(result) == 2
    assert set(result["signal_id"]) == {"r1", "r3"}

    result_hist = query(df=df, stamp_basis="recomputed_history")
    assert len(result_hist) == 1
    assert result_hist.iloc[0]["signal_id"] == "r2"


# ---------------------------------------------------------------------------
# (16) query — regime= default restricts to pit_live; stamp_basis='any' includes all
# ---------------------------------------------------------------------------

def test_query_regime_default_pit_live() -> None:
    """regime=X with no stamp_basis → only pit_live rows returned.
    stamp_basis='any' → all rows regardless of basis.
    stamp_basis='recomputed_history' → only recomputed_history rows.
    """
    from engine.neuralweb.query import query, COLUMNS

    rows = [
        {"signal_id": "live", "quad_hard_label": "Q1", "regime_stamp_basis": "pit_live"},
        {"signal_id": "hist", "quad_hard_label": "Q1", "regime_stamp_basis": "recomputed_history"},
        {"signal_id": "none", "quad_hard_label": "Q1", "regime_stamp_basis": None},
    ]
    df = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Default (stamp_basis=None) + regime= → only pit_live
    result_default = query(df=df, regime="Q1")
    assert set(result_default["signal_id"]) == {"live"}, (
        f"regime= default must restrict to pit_live, got: {list(result_default['signal_id'])}"
    )

    # stamp_basis='any' + regime= → all rows matching regime label
    result_any = query(df=df, regime="Q1", stamp_basis="any")
    assert set(result_any["signal_id"]) == {"live", "hist", "none"}, (
        f"stamp_basis='any' must include all basis values, got: {list(result_any['signal_id'])}"
    )

    # Explicit stamp_basis='recomputed_history' + regime= → only recomputed_history
    result_hist = query(df=df, regime="Q1", stamp_basis="recomputed_history")
    assert set(result_hist["signal_id"]) == {"hist"}, (
        f"stamp_basis='recomputed_history' must restrict to that basis, got: {list(result_hist['signal_id'])}"
    )


# ---------------------------------------------------------------------------
# (17) Max-asof join-key law: spine row dated D2 must not receive snapshot asof=D3
# ---------------------------------------------------------------------------

def test_stamp_macro_context_max_asof_law(tmp_path: Path) -> None:
    """A spine row at D2 must NOT receive a macro snapshot whose asof is D3 > D2.

    Max-asof join-key law: the backward merge_asof only binds a snapshot to a
    spine row when snapshot_asof <= spine_row_as_of.  Source A at D1 and source B
    at D3 produce snapshot_asof=D3.  A spine row at D2 must receive the D1
    snapshot (or nothing if D1 is the only prior snapshot), not the D3 snapshot.
    """
    from engine.neuralweb.query import _stamp_macro_context, COLUMNS

    # Write two snapshots: one at D1, one at D3
    _write_all_sources(tmp_path)
    snap_d1 = BMS.build_snapshot(root=tmp_path)
    snap_d1 = dict(snap_d1)
    snap_d1["asof"] = "2026-07-01"
    snap_d1["macro_context_id"] = "aaaa0000aaaa0000"

    snap_d3 = dict(snap_d1)
    snap_d3["asof"] = "2026-07-03"
    snap_d3["macro_context_id"] = "bbbb1111bbbb1111"

    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    BMS.write_ledger(snap_d1, out_dir)
    BMS.write_ledger(snap_d3, out_dir)

    # Spine row at D2 (between D1 and D3)
    rows = [
        {"signal_id": "at_d1", "as_of": "2026-07-01", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
        {"signal_id": "at_d2", "as_of": "2026-07-02", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
        {"signal_id": "at_d3", "as_of": "2026-07-03", "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
    ]
    combined = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in combined.columns:
            combined[col] = None

    result = _stamp_macro_context(combined, root=tmp_path)

    r_d1 = result[result["signal_id"] == "at_d1"].iloc[0]
    r_d2 = result[result["signal_id"] == "at_d2"].iloc[0]
    r_d3 = result[result["signal_id"] == "at_d3"].iloc[0]

    assert r_d1["macro_context_id"] == "aaaa0000aaaa0000", "D1 row must get D1 snapshot"
    assert r_d2["macro_context_id"] == "aaaa0000aaaa0000", (
        "D2 row must get D1 snapshot, NOT the D3 snapshot (max-asof join-key law)"
    )
    assert r_d3["macro_context_id"] == "bbbb1111bbbb1111", "D3 row must get D3 snapshot"


# ---------------------------------------------------------------------------
# (18) track_record rows via _stamp_macro_context → basis 'recomputed_history'
# ---------------------------------------------------------------------------

def test_stamp_macro_context_track_record_basis(tmp_path: Path) -> None:
    """Rows from the track_record ledger must receive 'recomputed_history' basis,
    not 'pit_live', when stamped via _stamp_macro_context.
    """
    from engine.neuralweb.query import _stamp_macro_context, COLUMNS

    _write_all_sources(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    snap = dict(snap)
    snap["asof"] = "2026-07-01"

    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    BMS.write_ledger(snap, out_dir)

    rows = [
        {"signal_id": "tr1", "ledger": "track_record", "as_of": "2026-07-05",
         "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
        {"signal_id": "ql1", "ledger": "qledger", "as_of": "2026-07-05",
         "macro_context_id": None, "macro_context_asof": None, "regime_stamp_basis": None},
    ]
    combined = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in combined.columns:
            combined[col] = None

    result = _stamp_macro_context(combined, root=tmp_path)

    tr_row = result[result["signal_id"] == "tr1"].iloc[0]
    ql_row = result[result["signal_id"] == "ql1"].iloc[0]

    assert tr_row["regime_stamp_basis"] == "recomputed_history", (
        f"track_record row must get 'recomputed_history', got: {tr_row['regime_stamp_basis']!r}"
    )
    assert ql_row["regime_stamp_basis"] == "pit_live", (
        f"qledger row must get 'pit_live', got: {ql_row['regime_stamp_basis']!r}"
    )


# ---------------------------------------------------------------------------
# (19) End-to-end transitions keys: from_value/to_value → _compose_macro_deltas from/to
# ---------------------------------------------------------------------------

def test_compose_macro_deltas_key_mapping(tmp_path: Path) -> None:
    """write_transitions writes from_value/to_value; _compose_macro_deltas must
    map these to consumer-facing 'from'/'to' keys in the lobe records.
    """
    import json as _json
    from engine.neuralweb.world_state import _compose_macro_deltas

    # Write a transitions.jsonl with from_value/to_value keys (producer format)
    trans_dir = tmp_path / "data" / "macro_snapshots"
    trans_dir.mkdir(parents=True, exist_ok=True)
    trans_path = trans_dir / "transitions.jsonl"

    # Use today's date so it falls within the 14-day window
    import datetime as _dt
    today = _dt.date.today().isoformat()
    record = {
        "asof": today,
        "domain": "us",
        "field": "us_quad",
        "from_value": "Q1",
        "to_value": "Q2",
        "macro_context_id": "test1234test1234",
    }
    trans_path.write_text(_json.dumps(record) + "\n", encoding="utf-8")

    lobe = _compose_macro_deltas(root=tmp_path)
    transitions = lobe.get("transitions") or []
    assert len(transitions) >= 1, f"Expected at least one transition record, got: {transitions}"
    tr = transitions[0]
    assert tr.get("from") == "Q1", (
        f"Consumer key 'from' must be populated from 'from_value'; got: {tr!r}"
    )
    assert tr.get("to") == "Q2", (
        f"Consumer key 'to' must be populated from 'to_value'; got: {tr!r}"
    )


# ---------------------------------------------------------------------------
# (20) commodity favored list → joined string; stringified list → same
# ---------------------------------------------------------------------------

def test_commodity_favored_list_join(tmp_path: Path) -> None:
    """commodity_favored ['Gold', 'Copper'] must become 'Gold, Copper' (not the repr string)."""
    _write_all_sources(tmp_path)
    # Write commodity with a list for favored
    p = tmp_path / "data" / "commodity"
    p.mkdir(parents=True, exist_ok=True)
    import json as _json
    (p / "latest.json").write_text(
        _json.dumps({"date": "2026-07-05", "regime": "range-bound", "favored": ["Gold", "Copper"]}),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    comm = snap["labels"].get("commodity", {})
    assert comm.get("commodity_favored") == "Gold, Copper", (
        f"List favored must be joined as 'Gold, Copper', got: {comm.get('commodity_favored')!r}"
    )


def test_commodity_favored_stringified_list(tmp_path: Path) -> None:
    """commodity_favored as stringified "['Gold', 'Copper']" must also produce 'Gold, Copper'."""
    _write_all_sources(tmp_path)
    p = tmp_path / "data" / "commodity"
    p.mkdir(parents=True, exist_ok=True)
    import json as _json
    (p / "latest.json").write_text(
        _json.dumps({"date": "2026-07-05", "regime": "range-bound",
                     "favored": "['Gold', 'Copper']"}),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    comm = snap["labels"].get("commodity", {})
    assert comm.get("commodity_favored") == "Gold, Copper", (
        f"Stringified list must be parsed and joined, got: {comm.get('commodity_favored')!r}"
    )


# ---------------------------------------------------------------------------
# (21) new us/bonds/fx/china/hk/canada labels present when source data has them
# ---------------------------------------------------------------------------

def _write_regime_v11(tmp_path: Path) -> None:
    """Write regime/latest.json with v1.1 fields populated."""
    p = tmp_path / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    import json as _json
    payload = {
        "quad": "Q1",
        "transition_state": "STABLE",
        "asof": "2026-07-05",
        "cross_asset_confirm": {"verdict": "agree"},
        "regime_vector": {
            "fused_risk_label": "risk-on",
            "vol_regime": "normal",
            "risk_radar_state": "neutral",
            "rate_pressure": None,
        },
        "business_cycle": {"phase": {"label": "recovery"}},
        "liquidity_quality": {"label": "stress-expansion"},
        "liquidity_overlay": "expanding",
        "froth_fragility": {"band": "watch"},
        "dislocation": {"verdict": "calm"},
        "market_gamma": {"regime": "short"},
        "market_drivers": {"repricing_coherence": {"state": "QUIET"}},
        "vol_regime": {"ts_slope_state": "contango", "vrp_state": "normal"},
    }
    (p / "latest.json").write_text(_json.dumps(payload), encoding="utf-8")


def test_new_us_labels_present(tmp_path: Path) -> None:
    """v1.1 us labels must be extracted when present."""
    _write_all_sources(tmp_path)
    _write_regime_v11(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    us = snap["labels"].get("us", {})
    assert us.get("us_business_cycle_phase") == "recovery", f"Got: {us.get('us_business_cycle_phase')!r}"
    assert us.get("us_liquidity_quality") == "stress-expansion", f"Got: {us.get('us_liquidity_quality')!r}"
    assert us.get("us_liquidity_overlay") == "expanding", f"Got: {us.get('us_liquidity_overlay')!r}"
    assert us.get("us_froth_band") == "watch", f"Got: {us.get('us_froth_band')!r}"
    assert us.get("us_dislocation") == "calm", f"Got: {us.get('us_dislocation')!r}"
    assert us.get("us_gamma_regime") == "short", f"Got: {us.get('us_gamma_regime')!r}"
    assert us.get("us_repricing_state") == "QUIET", f"Got: {us.get('us_repricing_state')!r}"
    assert us.get("us_vol_ts_state") == "contango", f"Got: {us.get('us_vol_ts_state')!r}"
    assert us.get("us_vrp_state") == "normal", f"Got: {us.get('us_vrp_state')!r}"


def test_new_us_labels_absent_fail_open(tmp_path: Path) -> None:
    """v1.1 us labels must be None when source keys absent (fail-open)."""
    _write_all_sources(tmp_path)
    # _write_regime (from _write_all_sources) has no v1.1 keys
    snap = BMS.build_snapshot(root=tmp_path)
    us = snap["labels"].get("us", {})
    # These keys should exist but be None
    assert us.get("us_business_cycle_phase") is None, f"Expected None, got {us.get('us_business_cycle_phase')!r}"
    assert us.get("us_froth_band") is None, f"Expected None, got {us.get('us_froth_band')!r}"


def test_new_bonds_labels_present(tmp_path: Path) -> None:
    """v1.1 bond labels must be extracted when bond_compass present."""
    _write_all_sources(tmp_path)
    import json as _json
    p = tmp_path / "data" / "bonds"
    p.mkdir(parents=True, exist_ok=True)
    (p / "bond_health.json").write_text(
        _json.dumps({
            "health_label": "healthy",
            "cycle_phase": "mid",
            "bond_compass": {
                "duration": {"bucket": "lean_long"},
                "curve_trade": {"lean": "steepener"},
            },
        }),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    bonds = snap["labels"].get("bonds", {})
    assert bonds.get("bond_duration_bucket") == "lean_long", f"Got: {bonds.get('bond_duration_bucket')!r}"
    assert bonds.get("bond_curve_lean") == "steepener", f"Got: {bonds.get('bond_curve_lean')!r}"


def test_new_fx_label_present(tmp_path: Path) -> None:
    """v1.1 fx_regime_radar must be extracted from forex.regime_radar.dominant."""
    _write_all_sources(tmp_path)
    import json as _json
    p = tmp_path / "data" / "forex"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        _json.dumps({
            "date": "2026-07-05",
            "regime": "US growth premium",
            "risk": "risk-on",
            "regime_radar": {"dominant": "em_crisis_capital_flight"},
        }),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    fx = snap["labels"].get("fx", {})
    assert fx.get("fx_regime_radar") == "em_crisis_capital_flight", f"Got: {fx.get('fx_regime_radar')!r}"


def test_new_fx_label_absent(tmp_path: Path) -> None:
    """fx_regime_radar must be None when regime_radar key absent."""
    _write_all_sources(tmp_path)
    snap = BMS.build_snapshot(root=tmp_path)
    fx = snap["labels"].get("fx", {})
    assert fx.get("fx_regime_radar") is None, f"Expected None, got {fx.get('fx_regime_radar')!r}"


def test_new_china_labels(tmp_path: Path) -> None:
    """v1.1 china labels must be extracted: china_property_regime, china_fe_band."""
    _write_all_sources(tmp_path)
    import json as _json
    p = tmp_path / "data" / "china_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        _json.dumps({
            "quad": "Q3",
            "property": {"regime": "Deep contraction (easing)"},
            "fear_euphoria": {"band": "Neutral"},
        }),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    china = snap["labels"].get("china", {})
    assert china.get("china_property_regime") == "Deep contraction (easing)", f"Got: {china.get('china_property_regime')!r}"
    assert china.get("china_fe_band") == "Neutral", f"Got: {china.get('china_fe_band')!r}"


def test_new_hk_label(tmp_path: Path) -> None:
    """v1.1 hk_peg_state must be extracted."""
    _write_all_sources(tmp_path)
    import json as _json
    p = tmp_path / "data" / "hk_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        _json.dumps({"quad": "Q4", "risk_state": "Risk-off", "peg_state": "weak-side (outflow)"}),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    hk = snap["labels"].get("hk", {})
    assert hk.get("hk_peg_state") == "weak-side (outflow)", f"Got: {hk.get('hk_peg_state')!r}"


def test_new_canada_labels(tmp_path: Path) -> None:
    """v1.1 canada_overlay_state and canada_cycle_tag must be extracted."""
    _write_all_sources(tmp_path)
    import json as _json
    p = tmp_path / "data" / "canada_regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(
        _json.dumps({
            "quad": "Q1",
            "cycle_tag": "late",
            "overlay": {"state": "Neutral"},
        }),
        encoding="utf-8",
    )
    snap = BMS.build_snapshot(root=tmp_path)
    ca = snap["labels"].get("canada", {})
    assert ca.get("canada_overlay_state") == "Neutral", f"Got: {ca.get('canada_overlay_state')!r}"
    assert ca.get("canada_cycle_tag") == "late", f"Got: {ca.get('canada_cycle_tag')!r}"


# ---------------------------------------------------------------------------
# (22) intl extractor: tmp parquet fixture → labels + ledger domain "intl"
# ---------------------------------------------------------------------------

def _write_intl_parquets(tmp_path: Path, countries: list[str] | None = None) -> None:
    """Write minimal intl_regime parquets for given countries (default AU, EZ)."""
    import pandas as pd
    import datetime

    countries = countries or ["AU", "EZ"]
    p = tmp_path / "data" / "intl_regime"
    p.mkdir(parents=True, exist_ok=True)

    for i, cc in enumerate(countries):
        dates = pd.date_range("2026-07-08", periods=3, freq="D")
        quads = ["Q2", "Q3", f"Q{(i % 4) + 1}"]
        df = pd.DataFrame({"quad": quads}, index=dates)
        df.to_parquet(p / f"{cc}_history.parquet")


def test_intl_extractor_labels(tmp_path: Path) -> None:
    """_extract_intl should read last row quad from each parquet."""
    import pandas as pd

    p = tmp_path / "data" / "intl_regime"
    p.mkdir(parents=True, exist_ok=True)

    # Write AU parquet: last row quad = Q1
    dates = pd.date_range("2026-07-08", periods=2, freq="D")
    df_au = pd.DataFrame({"quad": ["Q3", "Q1"]}, index=dates)
    df_au.to_parquet(p / "AU_history.parquet")

    # Write EZ parquet: last row quad = Q4
    df_ez = pd.DataFrame({"quad": ["Q2", "Q4"]}, index=dates)
    df_ez.to_parquet(p / "EZ_history.parquet")

    intl_labels, source_asofs, gaps = BMS._extract_intl(tmp_path / "data")
    assert intl_labels["intl"]["intl_au_quad"] == "Q1", f"Got: {intl_labels['intl']['intl_au_quad']!r}"
    assert intl_labels["intl"]["intl_ez_quad"] == "Q4", f"Got: {intl_labels['intl']['intl_ez_quad']!r}"

    # Source asofs should contain dates
    assert "data/intl_regime/AU_history.parquet" in source_asofs
    assert source_asofs["data/intl_regime/AU_history.parquet"] == "2026-07-09"


def test_intl_extractor_missing_file(tmp_path: Path) -> None:
    """Missing intl parquet must fail-open: None label + gap note."""
    # No intl_regime directory at all
    intl_labels, source_asofs, gaps = BMS._extract_intl(tmp_path / "data")
    assert intl_labels["intl"].get("intl_au_quad") is None
    assert any("AU" in g for g in gaps), f"Expected gap note for AU: {gaps}"


def test_intl_ledger_domain(tmp_path: Path) -> None:
    """After build_snapshot with intl parquets, ledger must have domain='intl' rows."""
    _write_all_sources(tmp_path)
    _write_intl_parquets(tmp_path, ["AU", "EZ"])

    snap = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = BMS.write_ledger(snap, out_dir)

    intl_rows = ledger[ledger["domain"] == "intl"]
    assert len(intl_rows) >= 2, f"Expected at least 2 intl ledger rows, got: {len(intl_rows)}"
    assert "intl_au_quad" in intl_rows["field"].values
    assert "intl_ez_quad" in intl_rows["field"].values


# ---------------------------------------------------------------------------
# (23) birth-suppression: new field → no transition; null-prior → transition
# ---------------------------------------------------------------------------

def test_birth_suppression_no_transition(tmp_path: Path) -> None:
    """A field that did NOT exist in prior ledger must NOT emit a transition."""
    _write_all_sources(tmp_path)
    snap_today = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_ledger = BMS.write_ledger(snap_today, out_dir)

    # Write a prior snapshot WITHOUT the field we want to test
    import copy
    prior_snap = copy.deepcopy(snap_today)
    prior_snap["asof"] = "2026-07-04"
    # Remove us_business_cycle_phase from prior to simulate it being a new field
    prior_labels = prior_snap["labels"]
    if "us" in prior_labels:
        prior_labels["us"].pop("us_business_cycle_phase", None)
        prior_labels["us"].pop("us_liquidity_quality", None)
    prior_snap["macro_context_id"] = BMS._context_id(prior_labels)
    full_ledger = BMS.write_ledger(prior_snap, out_dir)

    BMS.write_transitions(snap_today, full_ledger, out_dir)
    trans_path = out_dir / "transitions.jsonl"
    today_asof = snap_today["asof"]
    if trans_path.exists():
        lines = [l for l in trans_path.read_text(encoding="utf-8").splitlines() if l]
        today_births = [
            json.loads(l) for l in lines
            if json.loads(l).get("asof") == today_asof
            and json.loads(l).get("field") in ("us_business_cycle_phase", "us_liquidity_quality")
        ]
        assert len(today_births) == 0, (
            f"Birth-suppression failed: emitted {len(today_births)} transitions for new fields: {today_births}"
        )


def test_null_prior_transition_emitted(tmp_path: Path) -> None:
    """A field that existed in prior with explicit null → transition IS emitted when value changes."""
    _write_all_sources(tmp_path)
    _write_regime_v11(tmp_path)
    snap_today = BMS.build_snapshot(root=tmp_path)
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_ledger = BMS.write_ledger(snap_today, out_dir)

    # Write prior with us_business_cycle_phase = None (key exists, value null)
    import copy
    prior_snap = copy.deepcopy(snap_today)
    prior_snap["asof"] = "2026-07-04"
    if "us" in prior_snap["labels"]:
        prior_snap["labels"]["us"]["us_business_cycle_phase"] = None
    prior_snap["macro_context_id"] = BMS._context_id(prior_snap["labels"])
    full_ledger = BMS.write_ledger(prior_snap, out_dir)

    BMS.write_transitions(snap_today, full_ledger, out_dir)
    trans_path = out_dir / "transitions.jsonl"
    today_asof = snap_today["asof"]
    today_bcp_val = snap_today["labels"].get("us", {}).get("us_business_cycle_phase")

    if today_bcp_val is not None and trans_path.exists():
        lines = [l for l in trans_path.read_text(encoding="utf-8").splitlines() if l]
        null_to_val = [
            json.loads(l) for l in lines
            if json.loads(l).get("asof") == today_asof
            and json.loads(l).get("field") == "us_business_cycle_phase"
            and json.loads(l).get("from_value") is None
        ]
        assert len(null_to_val) >= 1, (
            f"Expected a transition from null to '{today_bcp_val}' but found none"
        )


# ---------------------------------------------------------------------------
# (24) NaN in source value normalizes to None
# ---------------------------------------------------------------------------

def test_nan_source_value_normalizes_to_none(tmp_path: Path) -> None:
    """A float NaN from a source field must become None, never the string 'nan'."""
    import math
    # Test _norm_str directly
    assert BMS._norm_str(float("nan")) is None, "float NaN must normalize to None"
    assert BMS._norm_str(None) is None
    assert BMS._norm_str("nan") is None
    assert BMS._norm_str("None") is None
    assert BMS._norm_str("") is None
    # A real string must pass through
    assert BMS._norm_str("recovery") == "recovery"
    assert BMS._norm_str("Q1") == "Q1"
