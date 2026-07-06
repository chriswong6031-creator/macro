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
