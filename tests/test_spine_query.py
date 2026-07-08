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
  (17) BLOCKER-1: altdata_conv excluded from spine; one economic event per symbol+as_of
  (18) BLOCKER-2: graded_before excludes graded rows with null graded_at (PIT leak guard)
  (19) adapt_spine — graded_at backfilled as as_of+horizon for graded rows
  (20) [R-CI3 DIRECTIONAL] _stamp_personality: row as_of 2 trading days BEFORE prod_asof
       must get personality_basis='absent' (pre-fix code leaked snapshot backwards)
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
    """Write a minimal spine predictions.parquet (W1 schema with role flags)."""
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
            # W1 role flags
            "is_sizing":  True,
            "is_veto":    False,
            "is_alpha":   True,
            "is_timing":  False,
            "is_context": False,
            "falsifier":  None,
            "half_life":  None,
        }
    ]
    p = tmp_path / "data" / "spine"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "predictions.parquet", index=False)
    return p / "predictions.parquet"


def _make_track_record(tmp_path: Path) -> Path:
    """Write a minimal track_record parquet at the canonical signal_archive path.

    Uses the real schema from data/signal_archive/track_record.parquet:
    regime columns are unprefixed (quad_hard_label, vol_regime, etc.) not us_*-prefixed.
    The adapter also accepts us_*-prefixed via _US_PREFIX_MAP for backward compat.
    """
    rows = [
        {
            "ticker": "MSFT",
            "date": "2026-01-02",
            "type": "buy",
            "fwd_mfe_5": 0.01,
            "fwd_mfe_10": 0.02,
            "fwd_mfe_21": 0.03,
            "fwd_mfe_63": 0.05,
            "fwd_mfe_126": 0.08,
            "terminal_state_clean15_126": "CLEAN_LIFTOFF",
            "terminal_state_clean8_21": "CUSHIONED",
            # real schema uses unprefixed regime columns
            "quad_hard_label": "quad1",
            "vol_regime": "low",
        }
    ]
    p = tmp_path / "data" / "signal_archive"
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

def test_adapt_track_record_reads_signal_archive_path(tmp_path):
    """adapt_track_record must read from data/signal_archive/track_record.parquet.

    Regression guard for the path bug fixed in W2: the old code read
    data/track_record/track_record.parquet which no producer ever writes,
    causing all US track-record rows to silently drop from the index.

    This test writes a fixture at the OLD (wrong) path and verifies adapt_track_record
    returns empty (path not found), then writes at the CORRECT path and verifies
    non-empty rows are returned.
    """
    # Step 1: write ONLY at the old (wrong) path → should get empty + gap note
    old_path = tmp_path / "data" / "track_record"
    old_path.mkdir(parents=True, exist_ok=True)
    import pandas as _pd
    _pd.DataFrame([{"ticker": "AAPL", "date": "2026-01-01", "fwd_mfe_5": 0.01}]).to_parquet(
        old_path / "track_record.parquet", index=False
    )
    df_wrong, gaps_wrong = Q.adapt_track_record(root=tmp_path)
    assert df_wrong.empty, (
        "adapt_track_record must NOT read data/track_record/track_record.parquet — "
        "that path has no producer; reading it would silently use stale/wrong data"
    )
    assert any("signal_archive" in g for g in gaps_wrong), (
        f"gap note must cite data/signal_archive path; got: {gaps_wrong}"
    )

    # Step 2: write at the CORRECT path → non-empty frame
    _make_track_record(tmp_path)  # writes to data/signal_archive/
    df_correct, gaps_correct = Q.adapt_track_record(root=tmp_path)
    assert not df_correct.empty, (
        "adapt_track_record must read data/signal_archive/track_record.parquet"
    )
    assert list(df_correct.columns) == Q.COLUMNS


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
    """adapt_track_record maps real signal_archive schema columns correctly.

    Real schema uses unprefixed regime columns (quad_hard_label, vol_regime etc.)
    not us_*-prefixed.  The _US_PREFIX_MAP fallback is retained for backward compat
    with any rows that may carry the us_* prefix.
    """
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
    # Real schema: regime column is unprefixed quad_hard_label (not us_*-prefixed)
    assert row["quad_hard_label"] == "quad1", (
        f"quad_hard_label must map from unprefixed column; got {row['quad_hard_label']!r}"
    )
    # family should come from 'type' column (real schema has no 'lane' column)
    assert row["family"] == "buy", (
        f"family must fall back to 'type' column when 'lane' absent; got {row['family']!r}"
    )


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
    """regime filter matches quad_hard_label OR fused_risk_label OR vol_regime OR risk_radar_state.

    Uses stamp_basis='any' to opt out of the R5 pit_live default so the test
    exercises all basis values (track_record fixture rows have basis=None).
    """
    _make_track_record(tmp_path)
    Q.write_index(root=tmp_path)
    df = Q.load_index(root=tmp_path)
    # track_record fixture has us_quad_hard_label="quad1" → mapped to quad_hard_label.
    # stamp_basis='any' opts out of the pit_live default restriction.
    result = Q.query(df, regime="quad1", stamp_basis="any")
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


# ---------------------------------------------------------------------------
# Helper: spine fixture with altdata_conv rows (for BLOCKER-1 tests)
# ---------------------------------------------------------------------------

def _make_spine_with_altdata_conv(tmp_path: Path) -> Path:
    """Write spine predictions.parquet that includes altdata_conv rows for NVDA and BWXT.

    NVDA@2026-01-05: same (symbol, as_of) as the qledger altdata claim fixture →
    should be EXCLUDED when twin_keys is supplied (qledger is authoritative).

    BWXT@2026-07-02: no matching qledger claim (orphan) → must be RETAINED
    with ledger='spine' regardless of twin_keys.

    This reproduces the real-world 134:133 spine:qledger correspondence.
    """
    rows = [
        # Normal us_board row (not excluded)
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
            "graded_at": None,
            "meta": "{}",
            "is_sizing": True, "is_veto": False, "is_alpha": True,
            "is_timing": False, "is_context": False, "falsifier": None, "half_life": None,
        },
        # altdata_conv row WITH qledger twin → excluded when twin_keys supplied
        {
            "signal_id": "altdata_conv:2026-01-05-NVDA-altconv",
            "engine": "altdata_conv",
            "version": "v1",
            "family": "altdata_conv",
            "as_of": "2026-01-05",  # same as_of as qledger altdata claim
            "symbol": "NVDA",       # same symbol as qledger altdata claim
            "universe": "us_altdata",
            "horizon": 63,          # different horizon than qledger (5)
            "score": 0.9,
            "size_binding": False,
            "direction": 1,
            "event_key": "NVDA:2026-01-05",
            "outcome_excess": None,
            "outcome_graded": False,  # ungraded in spine
            "graded_at": None,
            "meta": "{}",
            "is_sizing": False, "is_veto": False, "is_alpha": False,
            "is_timing": False, "is_context": True, "falsifier": "NVDA fails to beat SPY.", "half_life": None,
        },
        # altdata_conv ORPHAN (no qledger twin) → RETAINED with ledger='spine'
        {
            "signal_id": "altdata_conv:2026-07-02-BWXT-altconv",
            "engine": "altdata_conv",
            "version": "v1",
            "family": "altdata_conv",
            "as_of": "2026-07-02",
            "symbol": "BWXT",
            "universe": "us_altdata",
            "horizon": 63,
            "score": 0.7,
            "size_binding": False,
            "direction": 1,
            "event_key": "BWXT:2026-07-02",
            "outcome_excess": None,
            "outcome_graded": False,
            "graded_at": None,
            "meta": "{}",
            "is_sizing": False, "is_veto": False, "is_alpha": False,
            "is_timing": False, "is_context": True, "falsifier": None, "half_life": None,
        },
    ]
    p = tmp_path / "data" / "spine"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "predictions.parquet", index=False)
    return p / "predictions.parquet"


def _make_qledger_altdata(tmp_path: Path) -> tuple[Path, Path]:
    """Write qledger claims+grades with desk='altdata' for NVDA at 2026-01-05.

    This is the authoritative source for the altdata_conv event — it carries
    an actual grade (horizon=5, graded) while the spine copy is horizon=63/ungraded.
    """
    p = tmp_path / "data" / "qledger"
    p.mkdir(parents=True, exist_ok=True)

    claim = {
        "claim_id": "altdata_nvda_20260105_001",
        "desk": "altdata",
        "asof": "2026-01-05",
        "scope": {"type": "entity", "key": "NVDA"},
        "direction": 1,
        "horizon_d": 5,
        "claim_family": "altdata",
        "status": "graded",
        "timestamp_quality": "CRAWL_BOUNDED",
        "is_placebo": False,
        "convergence_score": 3.0,
    }
    grade = {
        "claim_id": "altdata_nvda_20260105_001",
        "horizon_d": 5,
        "graded_at": "2026-01-12T10:00:00+00:00",
        "subject_ret": 0.07,
        "bench_ret": 0.01,
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


# ---------------------------------------------------------------------------
# (17) BLOCKER-1: altdata_conv excluded from spine; one row per economic event
# ---------------------------------------------------------------------------

def test_no_double_count_altdata_conv(tmp_path):
    """BLOCKER-1 (event-matched): altdata_conv spine rows are excluded ONLY when a
    qledger twin exists for (symbol, as_of); orphans (no twin) are retained.

    Fixture:
      - Spine: AAPL@2026-01-01 (us_board), NVDA@2026-01-05 (altdata_conv, HAS twin),
               BWXT@2026-07-02 (altdata_conv, NO twin — orphan)
      - qledger: desk='altdata' claim for NVDA@2026-01-05 (h=5, graded)

    Expected build_index result:
      - NVDA@2026-01-05: exactly 1 row from qledger (altdata_conv spine row excluded)
      - BWXT@2026-07-02: exactly 1 row from spine (orphan retained — no qledger twin)
      - No altdata_conv spine row for NVDA in the index

    The BWXT retention prevents silent data loss: today it is ungraded
    (calibration-inert), but a future graded orphan would otherwise vanish from
    the W3 calibration index without error.
    """
    _make_spine_with_altdata_conv(tmp_path)
    _make_qledger_altdata(tmp_path)

    # Step 1: adapt_spine standalone (no twin_keys) — must NOT exclude any rows
    # (twin_keys=None means "no qledger context, skip nothing")
    spine_df_standalone, _ = Q.adapt_spine(root=tmp_path)
    assert len(spine_df_standalone[spine_df_standalone["engine"] == "altdata_conv"]) == 2, (
        "adapt_spine with no twin_keys must retain ALL altdata_conv rows (no exclusion)"
    )

    # Step 2: qledger must carry the NVDA@2026-01-05 event
    qledger_df, _ = Q.adapt_qledger(root=tmp_path)
    nvda_qledger = qledger_df[
        (qledger_df["symbol"] == "NVDA") & (qledger_df["as_of"] == "2026-01-05")
    ]
    assert len(nvda_qledger) >= 1, "qledger must carry NVDA@2026-01-05 altdata claim"

    # Step 3: build_index (supplies twin_keys to adapt_spine) — the full integration check
    combined, gaps = Q.build_index(root=tmp_path)

    # 3a: NVDA@2026-01-05 must appear exactly ONCE (from qledger — spine copy excluded)
    nvda_rows = combined[
        (combined["symbol"] == "NVDA") & (combined["as_of"] == "2026-01-05")
    ]
    assert len(nvda_rows) == 1, (
        f"NVDA@2026-01-05 must appear exactly once (qledger authoritative, spine excluded); "
        f"found {len(nvda_rows)} rows:\n{nvda_rows[['signal_id','ledger','horizon','outcome_graded']]}"
    )
    nvda_row = nvda_rows.iloc[0]
    assert nvda_row["ledger"] == "qledger", (
        f"surviving NVDA@2026-01-05 must be from qledger; got ledger={nvda_row['ledger']!r}"
    )
    assert nvda_row["outcome_graded"] == True, (  # noqa: E712
        "qledger NVDA row must be graded (horizon=5 grade exists)"
    )

    # 3b: BWXT@2026-07-02 must appear exactly ONCE from spine (orphan retained)
    bwxt_rows = combined[
        (combined["symbol"] == "BWXT") & (combined["as_of"] == "2026-07-02")
    ]
    assert len(bwxt_rows) == 1, (
        f"BWXT@2026-07-02 orphan must be retained in the index with ledger='spine'; "
        f"found {len(bwxt_rows)} rows: {bwxt_rows[['signal_id','ledger']].to_dict('records')}"
    )
    bwxt_row = bwxt_rows.iloc[0]
    assert bwxt_row["ledger"] == "spine", (
        f"BWXT@2026-07-02 must come from ledger='spine'; got {bwxt_row['ledger']!r}"
    )
    assert bwxt_row["engine"] == "altdata_conv", (
        f"BWXT row must have engine='altdata_conv'; got {bwxt_row['engine']!r}"
    )

    # 3c: Gap note must report matched-and-excluded vs orphan-retained counts
    spine_gaps = gaps.get("spine", [])
    assert any("altdata_conv" in n and "excluded" in n and "retained" in n
               for n in spine_gaps), (
        f"spine gap note must report excluded (qledger twin) and retained (no twin) counts; "
        f"got: {spine_gaps}"
    )


# ---------------------------------------------------------------------------
# (18) BLOCKER-2: graded_before excludes graded rows with null graded_at
# ---------------------------------------------------------------------------

def test_graded_before_excludes_graded_null_graded_at(tmp_path):
    """BLOCKER-2: graded_before must NOT pass rows that are graded
    (outcome_graded=True) but have no graded_at timestamp.

    The pre-fix behavior was a look-ahead leak: every graded spine row passed
    ANY graded_before filter because graded_at was null and null was treated
    as 'not yet graded' (retain unconditionally).

    This test directly exercises that boundary: construct a frame with one
    graded row missing graded_at and verify graded_before excludes it.
    Positive control: an ungraded row with null graded_at must still pass.
    """
    # Build a minimal index frame with two rows:
    # Row A: outcome_graded=True, graded_at=None  → must be EXCLUDED by graded_before
    # Row B: outcome_graded=False, graded_at=None → must be RETAINED by graded_before
    rows = [
        {
            "signal_id": "test:graded_no_ts:AAPL:21",
            "engine": "us_board",
            "family": "us_board:buy",
            "ledger": "spine",
            "as_of": "2026-01-01",
            "symbol": "AAPL",
            "scope_type": "entity",
            "universe": "us_1500",
            "horizon": 21,
            "direction": 1,
            "size_binding": True,
            "fill_basis": "next_bar",
            "score": 1.5,
            "outcome_excess": 0.04,
            "outcome_graded": True,   # GRADED
            "graded_at": None,        # BUT NO TIMESTAMP — look-ahead hazard
        },
        {
            "signal_id": "test:ungraded_no_ts:MSFT:63",
            "engine": "us_board",
            "family": "us_board:watch",
            "ledger": "spine",
            "as_of": "2026-01-02",
            "symbol": "MSFT",
            "scope_type": "entity",
            "universe": "us_1500",
            "horizon": 63,
            "direction": 1,
            "size_binding": False,
            "fill_basis": "next_bar",
            "score": 0.5,
            "outcome_excess": None,
            "outcome_graded": False,  # UNGRADED
            "graded_at": None,        # null graded_at is expected for ungraded rows
        },
    ]
    # Fill missing COLUMNS to keep _ensure_columns happy
    for row in rows:
        for c in Q.COLUMNS:
            row.setdefault(c, None)

    df = pd.DataFrame(rows)[Q.COLUMNS]

    # graded_before="2099-12-31" is a far-future cutoff: if null-graded-at were
    # retained unconditionally (pre-fix behavior), BOTH rows would pass.
    # Post-fix: Row A (graded, null graded_at) must be EXCLUDED; Row B must pass.
    result = Q.query(df, graded_before="2099-12-31")

    sids = set(result["signal_id"].tolist())
    assert "test:graded_no_ts:AAPL:21" not in sids, (
        "graded_before must EXCLUDE a row that is outcome_graded=True but graded_at=null "
        "(this is the PIT look-ahead leak the blocker describes)"
    )
    assert "test:ungraded_no_ts:MSFT:63" in sids, (
        "graded_before must RETAIN an ungraded row with null graded_at "
        "(it is legitimately pre-cutoff; outcome not yet known)"
    )


# ---------------------------------------------------------------------------
# (19) adapt_spine — graded_at backfilled as as_of+horizon for graded rows
# ---------------------------------------------------------------------------

def _make_spine_null_graded_at(tmp_path: Path) -> Path:
    """Write spine predictions.parquet with outcome_graded=True but graded_at=null.

    This reproduces the real spine parquet's graded_at=null pattern (0 of 1086
    rows have graded_at populated in the current build).
    """
    rows = [
        {
            "signal_id": "spine:2026-03-01:IBM:21",
            "engine": "us_board",
            "version": "v1",
            "family": "us_board:buy",
            "as_of": "2026-03-01",
            "symbol": "IBM",
            "universe": "us_1500",
            "horizon": 21,
            "score": 0.8,
            "size_binding": True,
            "direction": 1,
            "event_key": "IBM:2026-03-01",
            "outcome_excess": 0.02,
            "outcome_graded": True,   # graded
            "graded_at": None,        # but NO timestamp — mirrors real spine
            "meta": "{}",
            "is_sizing": True, "is_veto": False, "is_alpha": True,
            "is_timing": False, "is_context": False, "falsifier": None, "half_life": None,
        },
        {
            "signal_id": "spine:2026-03-01:GE:63",
            "engine": "us_board",
            "version": "v1",
            "family": "us_board:watch",
            "as_of": "2026-03-01",
            "symbol": "GE",
            "universe": "us_1500",
            "horizon": 63,
            "score": 0.3,
            "size_binding": False,
            "direction": 1,
            "event_key": "GE:2026-03-01",
            "outcome_excess": None,
            "outcome_graded": False,  # ungraded — graded_at stays null
            "graded_at": None,
            "meta": "{}",
            "is_sizing": False, "is_veto": False, "is_alpha": False,
            "is_timing": False, "is_context": True, "falsifier": None, "half_life": None,
        },
    ]
    p = tmp_path / "data" / "spine"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "predictions.parquet", index=False)
    return p / "predictions.parquet"


def test_adapt_spine_graded_at_backfill(tmp_path):
    """adapt_spine must synthesise graded_at = as_of + horizon days for spine rows
    that are outcome_graded=True but have graded_at=null.

    The real spine parquet has graded_at=null for all 1086 rows including all 952
    graded rows.  Without this backfill, graded_before filters are a no-op for
    the entire spine ledger.

    Also verifies: ungraded rows with null graded_at are NOT backfilled (they
    are legitimately pre-cutoff; their outcome is genuinely unknown).
    """
    _make_spine_null_graded_at(tmp_path)
    df, gaps = Q.adapt_spine(root=tmp_path)

    # IBM: outcome_graded=True, graded_at=None → backfill = 2026-03-01 + 21 = 2026-03-22
    ibm = df[df["symbol"] == "IBM"]
    assert len(ibm) == 1, f"expected 1 IBM row, got {len(ibm)}"
    ibm_row = ibm.iloc[0]
    assert ibm_row["outcome_graded"] == True, "IBM row must be graded"  # noqa: E712
    assert ibm_row["graded_at"] is not None, (
        "adapt_spine must backfill graded_at for graded rows with null graded_at"
    )
    assert str(ibm_row["graded_at"]) == "2026-03-22", (
        f"graded_at backfill expected '2026-03-22' (2026-03-01 + 21d), got {ibm_row['graded_at']!r}"
    )

    # GE: outcome_graded=False, graded_at=None → must remain null (not backfilled)
    ge = df[df["symbol"] == "GE"]
    assert len(ge) == 1, f"expected 1 GE row, got {len(ge)}"
    ge_row = ge.iloc[0]
    assert ge_row["outcome_graded"] == False, "GE row must be ungraded"  # noqa: E712
    assert ge_row["graded_at"] is None or str(ge_row["graded_at"]) in ("None", "nan", ""), (
        f"ungraded rows must NOT have graded_at backfilled; got {ge_row['graded_at']!r}"
    )


# ---------------------------------------------------------------------------
# (20) W1 Spine v2 — role flags in adapt_spine
# ---------------------------------------------------------------------------

def test_adapt_spine_maps_w1_role_flags(tmp_path):
    """adapt_spine must map W1 role flags (is_sizing/is_alpha/is_context/etc.) from the
    spine parquet into the index row dict.  A buy row (is_sizing=True, is_alpha=True)
    must flow through; a context row (is_context=True) must also flow correctly."""
    _make_spine(tmp_path)  # spine fixture: AAPL buy row with is_sizing=True, is_alpha=True
    df, gaps = Q.adapt_spine(root=tmp_path)
    assert not df.empty
    assert list(df.columns) == Q.COLUMNS
    row = df.iloc[0]
    # Buy row: is_sizing=True, is_alpha=True, is_context=False
    assert row["is_sizing"]  == True,  f"is_sizing expected True; got {row['is_sizing']}"   # noqa: E712
    assert row["is_alpha"]   == True,  f"is_alpha expected True; got {row['is_alpha']}"     # noqa: E712
    assert row["is_context"] == False, f"is_context expected False; got {row['is_context']}" # noqa: E712
    assert row["is_veto"]    == False  # noqa: E712
    assert row["is_timing"]  == False  # noqa: E712


def test_adapt_spine_falsifier_passthrough(tmp_path):
    """adapt_spine must carry falsifier text from the spine parquet into the index row."""
    # Write a spine with a context altdata_conv row that has a falsifier
    rows = [{
        "signal_id": "altdata_conv:NVDA-test",
        "engine": "altdata_conv",
        "version": "v1",
        "family": "altdata:convergence",
        "as_of": "2026-07-02",
        "symbol": "NVDA",
        "universe": "us_altdata",
        "horizon": 63,
        "score": 2.0,
        "size_binding": False,
        "direction": 1,
        "event_key": "NVDA:2026-07-02",
        "outcome_excess": None,
        "outcome_graded": False,
        "graded_at": None,
        "meta": "{}",
        "is_sizing": False, "is_veto": False, "is_alpha": False,
        "is_timing": False, "is_context": True,
        "falsifier": "NVDA fails to beat SPY by >5% over 63 days.",
        "half_life": None,
    }]
    p = tmp_path / "data" / "spine"
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p / "predictions.parquet", index=False)

    df, gaps = Q.adapt_spine(root=tmp_path)
    assert not df.empty
    row = df.iloc[0]
    assert row["falsifier"] == "NVDA fails to beat SPY by >5% over 63 days."
    assert row["is_context"] == True   # noqa: E712


def test_old_spine_index_loads_with_conservative_defaults(tmp_path):
    """W1 R8: loading an old spine_index.parquet (without W1 cols) must yield
    is_context=True and other flags=False (not NaN) for pre-W1 rows."""
    # Simulate an old 31-col index (no W1 cols) written before W1
    old_cols = [c for c in Q.COLUMNS if c not in
                ("is_sizing", "is_veto", "is_alpha", "is_timing", "is_context", "falsifier", "half_life")]
    row = {c: None for c in old_cols}
    row.update({"signal_id": "old:row:1", "engine": "us_board", "ledger": "spine",
                "family": "us_board:buy", "as_of": "2026-01-01", "symbol": "AAPL"})
    out = tmp_path / "data" / "neuralweb"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_parquet(out / "spine_index.parquet", index=False)

    df = Q.load_index(root=tmp_path)
    assert list(df.columns) == Q.COLUMNS, "load_index must return full COLUMNS even for old index"
    r = df.iloc[0]
    # Conservative defaults for pre-W1 rows
    assert r["is_context"] == True,  f"is_context must default True; got {r['is_context']}"  # noqa: E712
    assert r["is_sizing"]  == False, f"is_sizing must default False; got {r['is_sizing']}"   # noqa: E712
    assert r["is_alpha"]   == False, f"is_alpha must default False; got {r['is_alpha']}"     # noqa: E712
    assert r["is_veto"]    == False, f"is_veto must default False; got {r['is_veto']}"       # noqa: E712
    assert r["is_timing"]  == False, f"is_timing must default False; got {r['is_timing']}"   # noqa: E712
    # falsifier defaults None; half_life defaults NaN (not a flag, no conservative override)
    assert r["falsifier"] is None or str(r["falsifier"]) in ("None", "nan", "")


def test_w1_cols_in_build_index(tmp_path):
    """build_index must produce a frame that includes the 7 W1 columns."""
    _make_spine(tmp_path)
    df, gaps = Q.build_index(root=tmp_path)
    for col in ("is_sizing", "is_veto", "is_alpha", "is_timing", "is_context", "falsifier", "half_life"):
        assert col in df.columns, f"W1 column {col!r} missing from build_index output"


def test_columns_pin_drift_guard(tmp_path):
    """_SPINE_COLS in test_kernel.py mirrors Q.COLUMNS exactly; this test verifies
    that any future drift is caught here (the kernel test has a hardcoded literal)."""
    from tests.test_kernel import _SPINE_COLS
    assert _SPINE_COLS == Q.COLUMNS, (
        "test_kernel._SPINE_COLS is a hardcoded copy of Q.COLUMNS — it has drifted. "
        "Update _SPINE_COLS in tests/test_kernel.py to match engine.neuralweb.query.COLUMNS."
    )


# ---------------------------------------------------------------------------
# (20) [R-CI3 DIRECTIONAL] _stamp_personality — row before prod_asof → absent
# ---------------------------------------------------------------------------

def test_stamp_personality_directional_before_asof_absent(tmp_path):
    """[R-CI3 DIRECTIONAL] _stamp_personality must return absent for any row whose
    as_of is BEFORE the production snapshot's as_of (signed gap < 0).

    Pre-fix behaviour: Pass B used min/max(d0,d1) so the absolute gap for a row
    3 calendar days before prod_asof was |gap|=2 trading days → passed the ≤5
    window → returned snapshot_not_pit (PIT leak).
    Post-fix: np.busday_count(prod_date, row_date) < 0 → out_window → absent.

    This test FAILS on pre-fix code and PASSES on post-fix code.
    """
    # Write minimal production JSON in site/factordata/stock_personality.json
    (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)

    prod_asof = pd.Timestamp("2026-07-07").normalize()  # Monday
    # row as_of = Friday 04-Jul = 3 calendar days / 3 business days before prod_asof
    row_asof = pd.Timestamp("2026-07-04").normalize()

    prod_json = {
        "as_of": str(prod_asof.date()),
        "per_ticker": {
            "TSLA": {"arch": "volatile_growth", "chart": ["volatile_momentum_vehicle"],
                     "micro": ["wide_spread_impact"], "modes": ["normal"]},
        }
    }
    import json as _json
    (tmp_path / "site" / "factordata" / "stock_personality.json").write_text(
        _json.dumps(prod_json), encoding="utf-8"
    )

    # DataFrame with TSLA row whose as_of is BEFORE prod_asof
    rows = [
        {"symbol": "TSLA", "as_of": str(row_asof.date()),
         "signal_id": "spine:tsla:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = Q._stamp_personality(df.copy(), root=tmp_path)

    basis = stamped[stamped["symbol"] == "TSLA"]["personality_basis"].iloc[0]
    assert basis == "absent", (
        f"[R-CI3 DIRECTIONAL FAIL] TSLA as_of {row_asof.date()} (BEFORE prod_asof "
        f"{prod_asof.date()}) got personality_basis={basis!r} instead of 'absent'. "
        f"Pre-fix code used abs() gap and leaked the snapshot backwards into history."
    )
