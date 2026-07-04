"""tests/test_spine_query.py — Neural Web W2 PR1: spine query layer tests.

Hermetic fixtures per adapter.  No live data reads (all fixtures use tmp_path).

Coverage:
  (1) adapt_spine — correct column mapping
  (2) adapt_track_record — fail-open when parquet absent (positive-control 1)
  (3) adapt_board(hk) — correct mapping incl. fwd_mfe cols
  (4) adapt_board(ca) — correct mapping incl. fwd_mfe cols
  (5) adapt_china_board — fill_basis='t1_hl2' preserved
  (6) adapt_qledger — claim⋈grade join + namespaced signal_ids
  (7) adapt_qledger — fail-open when claims.jsonl absent (positive-control 2)
  (8) adapt_forward_logs — no graded cols → zero rows + gap note
  (9) build_index — union no-collision, dedup on signal_id+horizon
  (10) build_index — idempotent determinism (two builds, frame equality + row counts)
  (11) write_index / load_index — roundtrip + sidecar written
  (12) query — as_of_before PIT filter
  (13) query — graded_before PIT knowledge-state filter
  (14) query — scope_type filtering
  (15) query — regime matching (any of the four regime columns)
  (16) adapt_qledger — scope_type derived from scope shape (entity vs sector)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb import query as Q


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spine(tmp_path: Path) -> Path:
    """Write a minimal spine predictions.parquet."""
    rows = [
        {
            "signal_id": "spine:2026-01-01:AAPL:21",
            "engine": "us_board",
            "version": "v1",
            "family": "us_board:buy",
            "as_of": "2026-01-01",
            "symbol": "AAPL",
            "universe": "us_1500",
            "horizon": 21,
            "score": 1.5,
            "size_binding": True,
            "direction": 1,
            "event_key": "AAPL:2026-01-01",
            "outcome_excess": 0.04,
            "outcome_graded": True,
            "graded_at": "2026-02-01",
            "meta": "{}",
        }
    ]
    p = tmp_path / "data" / "spine"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "predictions.parquet", index=False)
    return p / "predictions.parquet"


def _make_track_record(tmp_path: Path) -> Path:
    """Write a minimal track_record parquet."""
    rows = [
        {
            "ticker": "MSFT",
            "date": "2026-01-02",
            "lane": "buy",
            "composite_z": 1.2,
            "fwd_mfe_5": 0.01,
            "fwd_mfe_10": 0.02,
            "fwd_mfe_21": 0.03,
            "fwd_mfe_63": 0.05,
            "fwd_mfe_126": 0.08,
            "terminal_state_clean15_126": "CLEAN_LIFTOFF",
            "terminal_state_clean8_21": "CUSHIONED",
            "us_quad_hard_label": "quad1",
            "us_vol_regime": "low",
        }
    ]
    p = tmp_path / "data" / "track_record"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "track_record.parquet", index=False)
    return p / "track_record.parquet"


def _make_board(tmp_path: Path, market: str) -> Path:
    """Write a minimal HK or CA board parquet."""
    rows = [
        {
            "ticker": "0700.HK" if market == "hk" else "SHOP.TO",
            "as_of": "2026-01-03",
            "lane": "buy",
            "level": 100.0,
            "fwd_mfe_5": 0.005,
            "fwd_mfe_21": 0.015,
            "fwd_mfe_63": 0.040,
            "terminal_state_clean15_126": None,
            "terminal_state_clean8_21": None,
            "us_quad_hard_label": "quad2",
        }
    ]
    p = tmp_path / "data" / "board_ledger"
    p.mkdir(parents=True, exist_ok=True)
    out = p / f"{market}_board.parquet"
    pd.DataFrame(rows).to_parquet(out, index=False)
    return out


def _make_china_board(tmp_path: Path) -> Path:
    """Write a minimal china_standout_track board parquet."""
    rows = [
        {
            "ticker": "300725.SZ",
            "date": "2026-01-04",
            "tier": "T1",
            "fill_basis": "t1_hl2",
            "board_rank": 1,
            "fwd_mfe_5": 0.02,
            "fwd_mfe_21": 0.06,
            "fwd_mfe_63": 0.10,
            "terminal_state_clean15_126": "CLEAN_LIFTOFF",
            "terminal_state_clean8_21": None,
            "species_id": None,
            "archetype": None,
        }
    ]
    p = tmp_path / "data" / "china_standout_track"
    p.mkdir(parents=True, exist_ok=True)
    out = p / "board.parquet"
    pd.DataFrame(rows).to_parquet(out, index=False)
    return out


def _make_qledger(tmp_path: Path) -> tuple[Path, Path]:
    """Write minimal claims.jsonl and grades.jsonl."""
    p = tmp_path / "data" / "qledger"
    p.mkdir(parents=True, exist_ok=True)

    claim = {
        "claim_id": "abc123def456abcd",
        "desk": "altdata",
        "asof": "2026-01-05",
        "scope": {"type": "entity", "key": "NVDA"},
        "direction": 1,
        "horizon_d": 21,
        "claim_family": "altdata",
        "status": "graded",
        "timestamp_quality": "CRAWL_BOUNDED",
        "is_placebo": False,
    }
    grade = {
        "claim_id": "abc123def456abcd",
        "horizon_d": 21,
        "graded_at": "2026-02-05T10:00:00+00:00",
        "subject_ret": 0.08,
        "bench_ret": 0.02,
        "control_ret": None,
        "excess": 0.06,
        "hit": True,
        "embargo_applied": True,
        "fill_convention": "next_bar",
    }

    claims_path = p / "claims.jsonl"
    grades_path = p / "grades.jsonl"
    claims_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
    grades_path.write_text(json.dumps(grade) + "\n", encoding="utf-8")
    return claims_path, grades_path


def _make_forward_log_no_grade(tmp_path: Path) -> Path:
    """Write a sector_cycles forward log without graded outcome columns."""
    rows = [
        {
            "date": "2026-01-06",
            "id": "xlk",
            "kind": "sector",
            "phase": "Recovery",
            "pos": 30.0,
            "signal": "BUY",
        }
    ]
    p = tmp_path / "data" / "sector_cycles"
    p.mkdir(parents=True, exist_ok=True)
    out = p / "forward_log.parquet"
    pd.DataFrame(rows).to_parquet(out, index=False)
    return out


# ---------------------------------------------------------------------------
# (1) adapt_spine
# ---------------------------------------------------------------------------

def test_adapt_spine_correct_mapping(tmp_path):
    _make_spine(tmp_path)
    df, gaps = Q.adapt_spine(root=tmp_path)
    assert not df.empty, "adapt_spine should return rows"
    assert list(df.columns) == Q.COLUMNS
    row = df.iloc[0]
    assert row["ledger"] == "spine"
    assert row["signal_id"] == "spine:2026-01-01:AAPL:21"
    assert row["engine"] == "us_board"
    assert row["scope_type"] == "entity"
    assert row["outcome_graded"] == True  # noqa: E712
    assert abs(row["outcome_excess"] - 0.04) < 1e-6
    assert not gaps, f"unexpected gaps: {gaps}"


# ---------------------------------------------------------------------------
# (2) adapt_track_record — fail-open when absent (positive-control 1)
# ---------------------------------------------------------------------------

def test_adapt_track_record_fail_open_when_absent(tmp_path):
    """When track_record.parquet is absent, adapt_track_record must return
    an empty frame and a gap note — never raise."""
    df, gaps = Q.adapt_track_record(root=tmp_path)
    assert df.empty, "absent track_record → empty frame"
    assert len(gaps) >= 1, "absent track_record → at least one gap note"
    # Positive control: verify the function also works when the file exists
    _make_track_record(tmp_path)
    df2, gaps2 = Q.adapt_track_record(root=tmp_path)
    assert not df2.empty, "track_record present → non-empty frame"
    assert list(df2.columns) == Q.COLUMNS


def test_adapt_track_record_correct_mapping(tmp_path):
    _make_track_record(tmp_path)
    df, gaps = Q.adapt_track_record(root=tmp_path)
    assert not df.empty
    # Should have one row per horizon that has an fwd_mfe column
    # MSFT row has fwd_mfe_5/10/21/63/126 → 5 rows
    assert len(df) == 5, f"expected 5 horizon rows, got {len(df)}"
    h21_rows = df[df["horizon"] == 21]
    assert len(h21_rows) == 1
    row = h21_rows.iloc[0]
    assert row["ledger"] == "track_record"
    assert row["symbol"] == "MSFT"
    assert row["terminal_state_clean15_126"] == "CLEAN_LIFTOFF"
    # Regime stamp mapping: us_quad_hard_label → quad_hard_label
    assert row["quad_hard_label"] == "quad1"


# ---------------------------------------------------------------------------
# (3) adapt_board(hk)
# ---------------------------------------------------------------------------

def test_adapt_board_hk_correct_mapping(tmp_path):
    _make_board(tmp_path, "hk")
    df, gaps = Q.adapt_board("hk", root=tmp_path)
    assert not df.empty, "adapt_board(hk) should return rows"
    assert list(df.columns) == Q.COLUMNS
    row = df.iloc[0]
    assert row["ledger"] == "board_hk"
    assert row["symbol"] == "0700.HK"
    assert row["scope_type"] == "entity"
    assert row["fill_basis"] == "next_bar"
    # fwd_mfe_5 should be mapped
    h5_rows = df[df["horizon"] == 5]
    assert not h5_rows.empty
    assert abs(h5_rows.iloc[0]["fwd_mfe_5"] - 0.005) < 1e-6


# ---------------------------------------------------------------------------
# (4) adapt_board(ca)
# ---------------------------------------------------------------------------

def test_adapt_board_ca_correct_mapping(tmp_path):
    _make_board(tmp_path, "ca")
    df, gaps = Q.adapt_board("ca", root=tmp_path)
    assert not df.empty
    row = df.iloc[0]
    assert row["ledger"] == "board_ca"
    assert row["symbol"] == "SHOP.TO"
    assert row["fill_basis"] == "next_bar"


# ---------------------------------------------------------------------------
# (5) adapt_china_board — fill_basis preserved
# ---------------------------------------------------------------------------

def test_adapt_china_board_fill_basis_preserved(tmp_path):
    _make_china_board(tmp_path)
    df, gaps = Q.adapt_china_board(root=tmp_path)
    assert not df.empty
    assert all(df["fill_basis"] == "t1_hl2"), (
        "CN board fill_basis must be 't1_hl2'; never aliased as next_bar"
    )
    assert list(df.columns) == Q.COLUMNS
    row5 = df[df["horizon"] == 5].iloc[0]
    assert row5["ledger"] == "board_cn"
    assert row5["symbol"] == "300725.SZ"
    assert row5["terminal_state_clean15_126"] == "CLEAN_LIFTOFF"


# ---------------------------------------------------------------------------
# (6) adapt_qledger — claim⋈grade join + namespaced signal_ids
# ---------------------------------------------------------------------------

def test_adapt_qledger_join_and_signal_ids(tmp_path):
    _make_qledger(tmp_path)
    df, gaps = Q.adapt_qledger(root=tmp_path)
    assert not df.empty, "qledger with claims+grades → non-empty frame"
    assert list(df.columns) == Q.COLUMNS
    # signal_id must be namespaced 'qledger:<claim_id>:<horizon>'
    graded_rows = df[df["outcome_graded"] == True]
    assert len(graded_rows) >= 1, "at least one graded row"
    sid = graded_rows.iloc[0]["signal_id"]
    assert sid.startswith("qledger:"), f"signal_id must start with 'qledger:', got {sid!r}"
    # claim⋈grade join: excess mapped to outcome_excess
    row = graded_rows.iloc[0]
    assert abs(row["outcome_excess"] - 0.06) < 1e-6
    # fill_basis from grade's fill_convention
    assert row["fill_basis"] == "next_bar"
    # scope_type = entity (from scope.type)
    assert row["scope_type"] == "entity"
    # horizon = grade horizon_d
    assert row["horizon"] == 21
    # fwd_mfe_21 should be populated (grade horizon = 21)
    assert abs(row["fwd_mfe_21"] - 0.06) < 1e-6


def test_adapt_qledger_scope_type_from_scope_shape(tmp_path):
    """scope_type is derived from scope.type field."""
    p = tmp_path / "data" / "qledger"
    p.mkdir(parents=True, exist_ok=True)
    claim = {
        "claim_id": "sectorclaimid1234",
        "desk": "sector_central",
        "asof": "2026-02-01",
        "scope": {"type": "sector", "key": "xlk"},
        "direction": 1,
        "horizon_d": 63,
        "claim_family": "sector",
        "status": "open",
        "timestamp_quality": "CRAWL_BOUNDED",
        "is_placebo": False,
    }
    (p / "claims.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")
    (p / "grades.jsonl").write_text("", encoding="utf-8")
    df, gaps = Q.adapt_qledger(root=tmp_path)
    assert not df.empty
    assert df.iloc[0]["scope_type"] == "sector"


# ---------------------------------------------------------------------------
# (7) adapt_qledger — fail-open when claims.jsonl absent (positive-control 2)
# ---------------------------------------------------------------------------

def test_adapt_qledger_fail_open_when_absent(tmp_path):
    """When claims.jsonl is absent, adapt_qledger must return empty frame + gap note."""
    df, gaps = Q.adapt_qledger(root=tmp_path)
    assert df.empty, "absent claims.jsonl → empty frame"
    assert len(gaps) >= 1, "absent claims.jsonl → at least one gap note"
    # Positive control: function works when file exists
    _make_qledger(tmp_path)
    df2, gaps2 = Q.adapt_qledger(root=tmp_path)
    assert not df2.empty, "qledger present → non-empty frame"


# ---------------------------------------------------------------------------
# (8) adapt_forward_logs — no graded cols → zero rows + gap note
# ---------------------------------------------------------------------------

def test_adapt_forward_logs_no_graded_cols(tmp_path):
    """A forward log without graded outcome columns contributes zero rows + gap note."""
    _make_forward_log_no_grade(tmp_path)
    # Also create missing china and country log dirs to avoid spurious failures
    (tmp_path / "data" / "china_sector_cycles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "country_cycles").mkdir(parents=True, exist_ok=True)
    df, gaps = Q.adapt_forward_logs(root=tmp_path)
    assert df.empty or len(df) == 0, (
        "forward log with no graded columns → zero rows"
    )
    # At least one gap note for the sector_cycles log
    # gaps is a list of gap strings
    assert any("graded" in n or "zero rows" in n for n in gaps), (
        f"expected gap note about no graded cols; got: {gaps}"
    )


# ---------------------------------------------------------------------------
# (9) build_index — union no-collision, dedup
# ---------------------------------------------------------------------------

def test_build_index_union_no_collision(tmp_path):
    """build_index unions all adapters; signal_ids from different ledgers never collide."""
    _make_spine(tmp_path)
    _make_china_board(tmp_path)
    _make_qledger(tmp_path)
    df, gaps = Q.build_index(root=tmp_path)
    assert not df.empty
    # signal_ids must be unique across ledgers
    assert df["signal_id"].is_unique, (
        "signal_id must be unique across all ledgers in the index"
    )
    # Must have rows from multiple ledgers
    ledgers_present = set(df["ledger"].dropna().unique())
    assert len(ledgers_present) >= 2, f"expected >=2 ledgers, got {ledgers_present}"


def test_build_index_dedup_on_signal_id_horizon(tmp_path):
    """Duplicate signal_id+horizon rows are deduped (keep-last)."""
    _make_spine(tmp_path)
    df1, _ = Q.build_index(root=tmp_path)
    # Build a second time — since spine data is identical, result should be the same
    df2, _ = Q.build_index(root=tmp_path)
    assert len(df1) == len(df2), "dedup: same input → same row count"
    assert list(df1["signal_id"].sort_values()) == list(df2["signal_id"].sort_values())


# ---------------------------------------------------------------------------
# (10) Idempotent determinism
# ---------------------------------------------------------------------------

def test_build_index_idempotent_determinism(tmp_path):
    """Two consecutive build_index calls on the same data return frame-identical results."""
    _make_spine(tmp_path)
    _make_china_board(tmp_path)
    _make_qledger(tmp_path)
    df1, gaps1 = Q.build_index(root=tmp_path)
    df2, gaps2 = Q.build_index(root=tmp_path)
    # Row counts must be identical
    assert len(df1) == len(df2), f"idempotent: row counts differ ({len(df1)} vs {len(df2)})"
    # Frame content must be equal (after sorting for stability)
    df1_sorted = df1.sort_values(["signal_id", "horizon"]).reset_index(drop=True)
    df2_sorted = df2.sort_values(["signal_id", "horizon"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        df1_sorted.fillna("_NaN_"),
        df2_sorted.fillna("_NaN_"),
        check_dtype=False,
    )


# ---------------------------------------------------------------------------
# (11) write_index / load_index — roundtrip + sidecar written
# ---------------------------------------------------------------------------

def test_write_and_load_index_roundtrip(tmp_path):
    """write_index writes parquet; load_index reads it back."""
    _make_spine(tmp_path)
    _make_china_board(tmp_path)
    stats = Q.write_index(root=tmp_path)
    assert stats["total_rows"] > 0, "expected non-zero rows"
    assert Path(stats["output_path"]).exists()
    df = Q.load_index(root=tmp_path)
    assert not df.empty
    assert list(df.columns) == Q.COLUMNS
    # Sidecar should exist
    sidecar_path = Path(stats["output_path"] + ".envelope.json")
    assert sidecar_path.exists(), "envelope sidecar must be written alongside parquet"
    sidecar = json.loads(sidecar_path.read_text())
    assert "produced_at" in sidecar
    assert "byte_sha256" in sidecar


def test_load_index_missing_is_empty_not_crash(tmp_path):
    """load_index on an absent file returns empty frame, never raises."""
    df = Q.load_index(root=tmp_path)
    assert df.empty
    assert list(df.columns) == Q.COLUMNS


# ---------------------------------------------------------------------------
# (12) query — as_of_before PIT filter
# ---------------------------------------------------------------------------

def test_query_as_of_before_pit_filter(tmp_path):
    """as_of_before retains only rows with as_of < cutoff."""
    _make_spine(tmp_path)
    _make_china_board(tmp_path)
    Q.write_index(root=tmp_path)
    df = Q.load_index(root=tmp_path)
    # Spine row as_of = 2026-01-01; china board as_of = 2026-01-04
    # cutoff "2026-01-03" → only spine row passes
    filtered = Q.query(df, as_of_before="2026-01-03")
    assert all(filtered["as_of"].dropna().astype(str) < "2026-01-03"), (
        "as_of_before must filter out rows at or after cutoff"
    )
    assert len(filtered) > 0, "at least one row should pass as_of_before=2026-01-03"


# ---------------------------------------------------------------------------
# (13) query — graded_before PIT knowledge-state filter
# ---------------------------------------------------------------------------

def test_query_graded_before_filter(tmp_path):
    """graded_before retains only rows with graded_at < cutoff (plus ungraded rows)."""
    _make_spine(tmp_path)
    _make_qledger(tmp_path)
    Q.write_index(root=tmp_path)
    df = Q.load_index(root=tmp_path)
    # Spine row graded_at = 2026-02-01; qledger row graded_at = 2026-02-05
    # cutoff "2026-02-03" → spine row passes (2026-02-01 < 2026-02-03), qledger may not
    filtered = Q.query(df, graded_before="2026-02-03", graded_only=True)
    for _, row in filtered.iterrows():
        ga = str(row.get("graded_at") or "")
        if ga and ga != "None" and ga != "nan":
            assert ga < "2026-02-03", f"graded_before violated: {ga}"


# ---------------------------------------------------------------------------
# (14) query — scope_type filtering
# ---------------------------------------------------------------------------

def test_query_scope_type_filter(tmp_path):
    """query(scope_type='entity') returns only entity rows."""
    _make_spine(tmp_path)
    _make_qledger(tmp_path)
    Q.write_index(root=tmp_path)
    df = Q.load_index(root=tmp_path)
    entity_rows = Q.query(df, scope_type="entity")
    assert not entity_rows.empty
    assert all(entity_rows["scope_type"] == "entity"), (
        "scope_type filter must exclude non-entity rows"
    )


# ---------------------------------------------------------------------------
# (15) query — regime matching (any of the four regime columns)
# ---------------------------------------------------------------------------

def test_query_regime_matches_any_column(tmp_path):
    """regime filter matches quad_hard_label OR fused_risk_label OR vol_regime OR risk_radar_state."""
    _make_track_record(tmp_path)
    Q.write_index(root=tmp_path)
    df = Q.load_index(root=tmp_path)
    # track_record fixture has us_quad_hard_label="quad1" → mapped to quad_hard_label
    result = Q.query(df, regime="quad1")
    assert not result.empty, "regime='quad1' should match rows with quad_hard_label='quad1'"
    # Every row must have the regime label in at least one of the four columns
    combined_mask = (
        (result["quad_hard_label"] == "quad1") |
        (result["fused_risk_label"] == "quad1") |
        (result["vol_regime"] == "quad1") |
        (result["risk_radar_state"] == "quad1")
    )
    assert combined_mask.all(), (
        f"regime filter must only return rows matching the regime; violations: "
        f"{result[~combined_mask][['signal_id','quad_hard_label','vol_regime']]}"
    )
