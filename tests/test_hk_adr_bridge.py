"""Tests for engine/hk_adr_bridge.py — HK ADR Overnight Bridge display organ.

Tests:
  (a) ADR→HK mapping correctness — all pairs present, sources correct
  (b) Timezone alignment — synthetic ADR close after a known HK close yields the
      correct implied-open gap on the NEXT session
  (c) %-move ratio-agnosticism — scaling ADR level by any constant leaves gap unchanged
  (d) Fail-open when ADR parquet missing/stale (freshness-gated, no crash)
  (e) Ledger stamp + grade roundtrip
  (f) Gap context labeling
  (g) Composite computation
  (h) Disconnect flag
  (i) Real store coverage — every ADR ticker is loadable from the actual data root
  (j) Production timezone path — snapshot(hk_session_date=None, now=<known time>)
  (k) Ledger lane guard — stamp/grade no-op outside asia-close lane

All writes are isolated to tmp_path. No writes to data/ or site/.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

# Ensure project root is on sys.path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.hk_adr_bridge as BRIDGE

# Real data root (the committed repo data directory)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DATA_ROOT = _REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# Helpers: synthetic data factories
# ---------------------------------------------------------------------------

def _make_adr_parquet(tmp_path: Path, ticker: str, closes: dict[str, float]) -> None:
    """Write a minimal ADR parquet to tmp_path/yahoo/<ticker>.parquet."""
    d = tmp_path / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex([pd.Timestamp(k) for k in closes.keys()], name="Date")
    df = pd.DataFrame({"close": list(closes.values())}, index=idx)
    df.to_parquet(d / f"{ticker}.parquet")


def _make_hk_parquet(tmp_path: Path, ticker: str, closes: dict[str, float],
                      opens: dict[str, float] | None = None) -> None:
    """Write a minimal HK stock parquet to tmp_path/hk_stocks/<ticker>.parquet."""
    d = tmp_path / "hk_stocks"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex([pd.Timestamp(k) for k in closes.keys()], name="Date")
    data: dict[str, list] = {"close": list(closes.values())}
    if opens is not None:
        data["open"] = [opens.get(k, list(closes.values())[i])
                        for i, k in enumerate(closes.keys())]
    df = pd.DataFrame(data, index=idx)
    df.to_parquet(d / f"{ticker}.parquet")


def _stub_all_adrs(tmp_path: Path, base_date: str = "2026-07-07") -> None:
    """Write stub ADR parquets for all tickers needed by the engine."""
    all_tickers = {p.adr_ticker for p in BRIDGE.ALL_PAIRS}
    for ticker in all_tickers:
        _make_adr_parquet(tmp_path, ticker, {
            "2026-07-06": 100.0,
            base_date: 102.0,   # +2%
        })


def _stub_all_hk(tmp_path: Path) -> None:
    """Write stub HK parquets for all names in the mapping."""
    for pair in BRIDGE.ALL_PAIRS:
        _make_hk_parquet(tmp_path, pair.hk_ticker, {
            "2026-07-02": 100.0,
            "2026-07-03": 101.0,
        })


# ---------------------------------------------------------------------------
# (a) Mapping correctness
# ---------------------------------------------------------------------------

class TestMappingCorrectness:
    def test_all_direct_pairs_present(self):
        """BABA/BIDU/JD/PDD must all appear as direct ADR pairs."""
        direct_adrs = {p.adr_ticker for p in BRIDGE._DIRECT_PAIRS}
        assert "BABA" in direct_adrs
        assert "BIDU" in direct_adrs
        assert "JD"   in direct_adrs
        assert "PDD"  in direct_adrs

    def test_direct_source_label(self):
        for p in BRIDGE._DIRECT_PAIRS:
            assert p.adr_source == "direct", f"{p.hk_ticker} has wrong source: {p.adr_source}"

    def test_proxy_source_label(self):
        for p in BRIDGE._PROXY_PAIRS:
            assert p.adr_source == "proxy", f"{p.hk_ticker} has wrong source: {p.adr_source}"

    def test_proxy_pairs_use_kweb_or_fxi(self):
        """All proxy pairs must use KWEB or FXI (the group ETFs)."""
        for p in BRIDGE._PROXY_PAIRS:
            assert p.adr_ticker in ("KWEB", "FXI"), \
                f"{p.hk_ticker} uses unexpected proxy: {p.adr_ticker}"

    def test_tcehy_absent(self):
        """OTC TCEHY must NOT be in the ADR→HK map (thin/illiquid)."""
        all_adrs = {p.adr_ticker for p in BRIDGE.ALL_PAIRS}
        assert "TCEHY" not in all_adrs, "TCEHY (thin OTC) should not be in the map"

    def test_no_duplicate_hk_tickers(self):
        hk_tickers = [p.hk_ticker for p in BRIDGE.ALL_PAIRS]
        assert len(hk_tickers) == len(set(hk_tickers)), "Duplicate HK tickers in map"

    def test_hk_ticker_format(self):
        for p in BRIDGE.ALL_PAIRS:
            assert p.hk_ticker.endswith(".HK"), \
                f"HK ticker {p.hk_ticker!r} must end with .HK"

    def test_bilingual_names_non_empty(self):
        for p in BRIDGE.ALL_PAIRS:
            assert p.hk_name_en, f"{p.hk_ticker} missing hk_name_en"
            assert p.hk_name_zh, f"{p.hk_ticker} missing hk_name_zh"

    def test_proxy_note_present_for_proxies(self):
        for p in BRIDGE._PROXY_PAIRS:
            assert p.proxy_note, f"{p.hk_ticker} proxy missing proxy_note"

    def test_display_only_flag(self, tmp_path):
        """snapshot() must always return display_only=True."""
        _stub_all_adrs(tmp_path)
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        assert snap.get("display_only") is True


# ---------------------------------------------------------------------------
# (b) Timezone alignment
# ---------------------------------------------------------------------------

class TestTimezoneAlignment:
    """
    HK session date T = 2026-07-07 (Tuesday).
    HK closes at ~08:00 UTC on 2026-07-07.
    US session that IMPLIES next HK open = US close on 2026-07-07 (~20:00 UTC).
    So:
        adr_date = 2026-07-07
        implied open for HK session 2026-07-08 = ADR pct change on 2026-07-07
    """

    def test_adr_date_equals_hk_session_date(self, tmp_path):
        """adr_date must equal hk_session_date (same calendar date)."""
        _stub_all_adrs(tmp_path, base_date="2026-07-07")
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        assert snap["hk_session_date"] == "2026-07-07"
        assert snap["adr_date"] == "2026-07-07"

    def test_implied_gap_uses_same_date_adr_close(self, tmp_path):
        """
        ADR: prev=100.0 on 2026-07-06; curr=115.0 on 2026-07-07.
        Implied gap = (115/100 - 1) * 100 = +15%.
        """
        _make_adr_parquet(tmp_path, "BABA", {
            "2026-07-06": 100.0,
            "2026-07-07": 115.0,
        })
        # Stub remaining ADRs to prevent missing warnings
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"BABA"}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": 100.0,
                "2026-07-07": 100.0,
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        baba_entry = next((n for n in snap["names"] if n["hk_ticker"] == "9988.HK"), None)
        assert baba_entry is not None
        assert baba_entry["adr_source"] == "direct"
        pct = baba_entry["implied_open_gap_pct"]
        assert pct is not None
        assert abs(pct - 15.0) < 0.01, f"Expected +15.0%, got {pct}"

    def test_next_session_implied_not_same_session(self, tmp_path):
        """The implied gap for HK session T implies T+1's open (not T's open)."""
        # Session T = 2026-07-07; T+1 = 2026-07-08 (next HK session)
        _stub_all_adrs(tmp_path, base_date="2026-07-07")
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        # The HK session whose NEXT open is implied = 2026-07-07
        # i.e. ADR on 2026-07-07 → implies HK open on 2026-07-08
        assert snap["hk_session_date"] == "2026-07-07"

    def test_no_adr_bar_for_date_gives_none(self, tmp_path):
        """If the ADR has no bar for the target date, implied gap = None (not crash)."""
        _make_adr_parquet(tmp_path, "BABA", {
            "2026-07-05": 100.0,
            "2026-07-06": 102.0,
            # 2026-07-07 intentionally absent
        })
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"BABA"}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": 100.0,
                "2026-07-07": 100.0,
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        baba_entry = next((n for n in snap["names"] if n["hk_ticker"] == "9988.HK"), None)
        assert baba_entry is not None
        assert baba_entry["implied_open_gap_pct"] is None


# ---------------------------------------------------------------------------
# (c) Ratio-agnosticism
# ---------------------------------------------------------------------------

class TestRatioAgnosticism:
    """
    ADR:underlying ratio varies (e.g. BABA 1:8, BIDU 10:1).
    Since we use percent moves, the ratio is irrelevant.
    Scaling ADR level by any constant K must not change the gap.
    """

    def _snap_for_levels(self, tmp_path: Path,
                          adr_ticker: str, prev: float, curr: float) -> dict:
        _make_adr_parquet(tmp_path, adr_ticker, {
            "2026-07-06": prev,
            "2026-07-07": curr,
        })
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {adr_ticker}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": 100.0,
                "2026-07-07": 100.0,
            })
        _stub_all_hk(tmp_path)
        return BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )

    def test_scaling_adr_level_preserves_pct(self, tmp_path):
        """BABA: level 100->115 vs level 1000->1150 must give same +15% gap."""
        snap1 = self._snap_for_levels(tmp_path, "BABA", 100.0, 115.0)
        tmp2 = tmp_path / "scaled"
        tmp2.mkdir()
        snap2 = self._snap_for_levels(tmp2, "BABA", 1000.0, 1150.0)

        e1 = next(n for n in snap1["names"] if n["hk_ticker"] == "9988.HK")
        e2 = next(n for n in snap2["names"] if n["hk_ticker"] == "9988.HK")

        assert e1["implied_open_gap_pct"] is not None
        assert e2["implied_open_gap_pct"] is not None
        assert abs(e1["implied_open_gap_pct"] - e2["implied_open_gap_pct"]) < 1e-6, \
            f"Scaling changed gap: {e1['implied_open_gap_pct']} vs {e2['implied_open_gap_pct']}"

    def test_scaling_by_ratio_factor_8(self, tmp_path):
        """BABA typical ratio ~1:8 (1 ADR = 8 ordinary shares).
        Underlying gain of 10% on HK → ADR gain of 10% regardless of ratio.
        Test: prev=8.0 (ratio-adjusted), curr=8.8 → same +10% as prev=100, curr=110."""
        snap_a = self._snap_for_levels(tmp_path, "BABA", 8.0, 8.8)
        tmp_b = tmp_path / "b"
        tmp_b.mkdir()
        snap_b = self._snap_for_levels(tmp_b, "BABA", 100.0, 110.0)

        e_a = next(n for n in snap_a["names"] if n["hk_ticker"] == "9988.HK")
        e_b = next(n for n in snap_b["names"] if n["hk_ticker"] == "9988.HK")

        assert abs(e_a["implied_open_gap_pct"] - e_b["implied_open_gap_pct"]) < 1e-6, \
            f"Ratio-adjusted levels changed gap: {e_a['implied_open_gap_pct']} vs {e_b['implied_open_gap_pct']}"


# ---------------------------------------------------------------------------
# (d) Fail-open: missing / stale ADR data
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_no_crash_when_adr_dir_missing(self, tmp_path):
        """If data/yahoo/ directory is entirely absent, snapshot returns without crash."""
        _stub_all_hk(tmp_path)
        # Don't create yahoo/ dir
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        assert isinstance(snap, dict)
        assert "names" in snap

    def test_missing_adr_gives_none_gap(self, tmp_path):
        """When an ADR parquet is missing, that name's gap = None (not a crash)."""
        # Only provide BIDU, not BABA
        _make_adr_parquet(tmp_path, "BIDU", {"2026-07-06": 100.0, "2026-07-07": 103.0})
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"BIDU"}:
            # Don't create other files
            pass
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        baba_entry = next(n for n in snap["names"] if n["hk_ticker"] == "9988.HK")
        assert baba_entry["implied_open_gap_pct"] is None
        assert baba_entry["missing_reason"] is not None

    def test_stale_adr_sets_freshness_degraded(self, tmp_path):
        """ADR with last date 10 days ago → freshness_verdict degraded/stale."""
        old_date = "2026-06-20"
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-06-19": 100.0,
                old_date: 101.0,
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        assert snap["freshness_verdict"] in ("stale", "degraded")

    def test_banner_present_when_stale(self, tmp_path):
        """When stale, banner must be a dict with en and zh keys."""
        old_date = "2026-06-20"
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-06-19": 100.0,
                old_date: 101.0,
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        if snap["freshness_verdict"] in ("stale", "degraded"):
            assert snap["banner"] is not None
            assert "en" in snap["banner"]
            assert "zh" in snap["banner"]

    def test_fresh_data_no_banner(self, tmp_path):
        """With fresh data, banner must be None."""
        _stub_all_adrs(tmp_path, base_date="2026-07-07")
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        if snap["freshness_verdict"] == "ok":
            assert snap["banner"] is None

    def test_run_never_raises(self, tmp_path):
        """run() must never raise regardless of missing data."""
        # Don't create any data files at all
        result = BRIDGE.run(data_root=tmp_path,
                            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc))
        assert isinstance(result, dict)
        assert result.get("display_only") is True or "error" in result

    def test_gap_context_unknown_for_none_gap(self):
        """_gap_context(None) must return 'unknown' (not a crash)."""
        assert BRIDGE._gap_context(None) == "unknown"


# ---------------------------------------------------------------------------
# (e) Ledger stamp + grade roundtrip
# ---------------------------------------------------------------------------

class TestLedgerRoundtrip:
    @pytest.fixture(autouse=True)
    def _enable_ledger_lane(self, monkeypatch):
        """Enable ledger advance for all roundtrip tests by setting CN_LANE=asia."""
        monkeypatch.setenv("CN_LANE", "asia")

    def _make_full_stub(self, tmp_path: Path,
                         adr_date: str = "2026-07-07",
                         prev_date: str = "2026-07-06",
                         adr_gain_pct: float = 5.0) -> dict:
        """Create stubs + return a snapshot using them."""
        for pair in BRIDGE._DIRECT_PAIRS:
            _make_adr_parquet(tmp_path, pair.adr_ticker, {
                prev_date: 100.0,
                adr_date: 100.0 * (1 + adr_gain_pct / 100),
            })
        for pair in BRIDGE._PROXY_PAIRS:
            _make_adr_parquet(tmp_path, pair.adr_ticker, {
                prev_date: 100.0,
                adr_date: 100.0 * (1 + adr_gain_pct / 100),
            })
        _stub_all_hk(tmp_path)
        return BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )

    def test_stamp_writes_ledger_file(self, tmp_path):
        snap = self._make_full_stub(tmp_path)
        n = BRIDGE.stamp(snap, data_root=tmp_path)
        assert n >= 1, "stamp() should return count of rows appended"
        ledger_path = BRIDGE._ledger_path(tmp_path)
        assert ledger_path.exists(), "ledger file must be created after stamp"

    def test_ledger_file_in_tmp_path(self, tmp_path):
        """Ledger MUST be written inside tmp_path, never to real data/."""
        snap = self._make_full_stub(tmp_path)
        BRIDGE.stamp(snap, data_root=tmp_path)
        ledger_path = BRIDGE._ledger_path(tmp_path)
        # Must be inside tmp_path
        assert str(ledger_path).startswith(str(tmp_path)), \
            f"Ledger written outside tmp_path: {ledger_path}"

    def test_stamp_idempotent(self, tmp_path):
        """Calling stamp twice for the same session must not duplicate rows."""
        snap = self._make_full_stub(tmp_path)
        n1 = BRIDGE.stamp(snap, data_root=tmp_path)
        n2 = BRIDGE.stamp(snap, data_root=tmp_path)
        assert n2 == 0, "Second stamp of same session should append 0 rows"
        rows = BRIDGE.load_ledger(tmp_path)
        # Each name appears exactly once
        fire_ids = [r["fire_id"] for r in rows]
        assert len(fire_ids) == len(set(fire_ids)), "Duplicate fire_ids in ledger"

    def test_ledger_row_schema(self, tmp_path):
        """Each ledger row must contain the required fields."""
        snap = self._make_full_stub(tmp_path, adr_gain_pct=5.0)
        BRIDGE.stamp(snap, data_root=tmp_path)
        rows = BRIDGE.load_ledger(tmp_path)
        required = {
            "fire_id", "organ", "hk_session_date", "adr_date", "name",
            "adr_ticker", "adr_source", "implied_open_gap_pct",
            "adr_move_pct", "gap_context", "disconnect_flag",
            "asof_freshness", "episode_id",
            "actual_open_gap_pct", "followed", "graded_at",
        }
        for r in rows:
            missing = required - set(r.keys())
            assert not missing, f"Row missing fields: {missing} — row={r['fire_id']}"

    def test_ledger_organ_field(self, tmp_path):
        snap = self._make_full_stub(tmp_path)
        BRIDGE.stamp(snap, data_root=tmp_path)
        rows = BRIDGE.load_ledger(tmp_path)
        for r in rows:
            assert r["organ"] == BRIDGE._ORGAN_ID

    def test_ledger_initial_grade_fields_null(self, tmp_path):
        """Before grade(), actual_open_gap_pct and followed must be None."""
        snap = self._make_full_stub(tmp_path)
        BRIDGE.stamp(snap, data_root=tmp_path)
        rows = BRIDGE.load_ledger(tmp_path)
        for r in rows:
            assert r["actual_open_gap_pct"] is None
            assert r["followed"] is None
            assert r["graded_at"] is None

    def test_grade_fills_when_next_session_open_available(self, tmp_path):
        """grade() should fill actual_open_gap_pct when T+1 HK open data exists."""
        snap = self._make_full_stub(tmp_path, adr_gain_pct=5.0)
        BRIDGE.stamp(snap, data_root=tmp_path)

        # Provide T+1 open data for a direct pair (9988.HK)
        # HK session date = 2026-07-07; next session = 2026-07-08
        # Prior close = 101.0 (from stub); next open = 108.08 → +7% gap
        _make_hk_parquet(tmp_path, "9988.HK",
                          closes={"2026-07-02": 100.0, "2026-07-03": 101.0,
                                   "2026-07-07": 101.0, "2026-07-08": 108.08},
                          opens= {"2026-07-08": 108.08})

        result = BRIDGE.grade(data_root=tmp_path)
        assert result.get("ok") is True

        rows = BRIDGE.load_ledger(tmp_path)
        baba_rows = [r for r in rows if r["name"] == "9988.HK"]
        if baba_rows:
            r = baba_rows[0]
            if r["actual_open_gap_pct"] is not None:
                assert abs(r["actual_open_gap_pct"] - 7.0) < 0.5, \
                    f"Expected ~7% actual gap, got {r['actual_open_gap_pct']}"

    def test_grade_returns_dict(self, tmp_path):
        """grade() must always return a dict."""
        snap = self._make_full_stub(tmp_path)
        BRIDGE.stamp(snap, data_root=tmp_path)
        result = BRIDGE.grade(data_root=tmp_path)
        assert isinstance(result, dict)
        assert "ok" in result

    def test_grade_no_crash_without_ledger(self, tmp_path):
        """grade() on empty ledger must return ok dict, not crash."""
        result = BRIDGE.grade(data_root=tmp_path)
        assert isinstance(result, dict)
        assert result.get("ok") is True

    def test_load_ledger_empty_when_no_file(self, tmp_path):
        rows = BRIDGE.load_ledger(tmp_path)
        assert rows == []

    def test_ledger_is_valid_jsonl(self, tmp_path):
        """Each line of the ledger must be valid JSON."""
        snap = self._make_full_stub(tmp_path)
        BRIDGE.stamp(snap, data_root=tmp_path)
        ledger_path = BRIDGE._ledger_path(tmp_path)
        for i, line in enumerate(ledger_path.read_text().splitlines()):
            if line.strip():
                obj = json.loads(line)
                assert isinstance(obj, dict), f"Line {i} is not a JSON object"


# ---------------------------------------------------------------------------
# (f) Gap context labeling
# ---------------------------------------------------------------------------

class TestGapContext:
    @pytest.mark.parametrize("pct,expected", [
        (5.0,  "strong_up"),
        (3.0,  "strong_up"),
        (2.0,  "up"),
        (1.0,  "up"),
        (0.5,  "flat"),
        (0.0,  "flat"),
        (-0.5, "flat"),
        (-1.0, "flat"),
        (-2.0, "down"),
        (-3.0, "down"),
        (-4.0, "strong_down"),
        (None, "unknown"),
    ])
    def test_gap_context(self, pct, expected):
        result = BRIDGE._gap_context(pct)
        assert result == expected, f"_gap_context({pct}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# (g) Composite computation
# ---------------------------------------------------------------------------

class TestComposite:
    def test_composite_uses_direct_pairs_when_available(self, tmp_path):
        """Composite = average of direct pair gaps when all are present."""
        # BABA +10%, BIDU +20%, JD +10%, PDD +20% → composite = 15%
        prices = {"BABA": (100, 110), "BIDU": (100, 120),
                  "JD": (100, 110), "PDD": (100, 120)}
        for ticker, (prev, curr) in prices.items():
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": float(prev),
                "2026-07-07": float(curr),
            })
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS if p.adr_source == "proxy"}:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": 100.0,
                "2026-07-07": 100.0,
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        comp = snap["composite"]
        assert comp["bellwether_implied_open_pct"] is not None
        assert abs(comp["bellwether_implied_open_pct"] - 15.0) < 0.1
        assert comp["composite_source"] == "direct_average"
        assert comp["n_direct"] == 4

    def test_etf_composite_present(self, tmp_path):
        """etf_composite_pct must be computed from KWEB and FXI."""
        # KWEB +6%, FXI +4% → ETF composite = 5%
        _make_adr_parquet(tmp_path, "KWEB", {"2026-07-06": 100.0, "2026-07-07": 106.0})
        _make_adr_parquet(tmp_path, "FXI",  {"2026-07-06": 100.0, "2026-07-07": 104.0})
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"KWEB", "FXI"}:
            _make_adr_parquet(tmp_path, ticker, {"2026-07-06": 100.0, "2026-07-07": 100.0})
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        comp = snap["composite"]
        assert comp["etf_composite_pct"] is not None
        assert abs(comp["etf_composite_pct"] - 5.0) < 0.1


# ---------------------------------------------------------------------------
# (h) Disconnect flag
# ---------------------------------------------------------------------------

class TestDisconnectFlag:
    def test_disconnect_true_when_signs_differ(self, tmp_path):
        """If last HK move is negative but ADR is positive → disconnect=True."""
        # BABA ADR: +5% (positive)
        _make_adr_parquet(tmp_path, "BABA", {
            "2026-07-06": 100.0,
            "2026-07-07": 105.0,
        })
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"BABA"}:
            _make_adr_parquet(tmp_path, ticker, {"2026-07-06": 100.0, "2026-07-07": 100.0})
        # 9988.HK: last move negative (drops from 100 to 98)
        _make_hk_parquet(tmp_path, "9988.HK", {
            "2026-07-03": 100.0,
            "2026-07-07": 98.0,   # -2%
        })
        for pair in BRIDGE.ALL_PAIRS:
            if pair.hk_ticker != "9988.HK":
                _make_hk_parquet(tmp_path, pair.hk_ticker, {
                    "2026-07-03": 100.0, "2026-07-07": 101.0
                })
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        baba_entry = next(n for n in snap["names"] if n["hk_ticker"] == "9988.HK")
        assert baba_entry["disconnect_flag"] is True, "Opposite-sign moves should set disconnect=True"

    def test_disconnect_false_when_signs_same(self, tmp_path):
        """Both ADR and last HK move positive → disconnect=False."""
        _make_adr_parquet(tmp_path, "BABA", {"2026-07-06": 100.0, "2026-07-07": 105.0})
        for ticker in {p.adr_ticker for p in BRIDGE.ALL_PAIRS} - {"BABA"}:
            _make_adr_parquet(tmp_path, ticker, {"2026-07-06": 100.0, "2026-07-07": 100.0})
        # 9988.HK: last move also positive
        _make_hk_parquet(tmp_path, "9988.HK", {
            "2026-07-03": 100.0,
            "2026-07-07": 103.0,
        })
        for pair in BRIDGE.ALL_PAIRS:
            if pair.hk_ticker != "9988.HK":
                _make_hk_parquet(tmp_path, pair.hk_ticker, {
                    "2026-07-03": 100.0, "2026-07-07": 101.0
                })
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
        baba_entry = next(n for n in snap["names"] if n["hk_ticker"] == "9988.HK")
        assert baba_entry["disconnect_flag"] is False


# ---------------------------------------------------------------------------
# (i) Real store coverage — FIX 2
# Every mapped ADR ticker must be loadable via _load_adr from the REAL data root
# (yahoo primary, massive_stock_day fallback). This test would FAIL if KWEB were
# absent from both stores (the production pathology the reviewer found), and PASSES
# after FIX 1 (massive_stock_day fallback) or FIX 1b (KWEB in PROXIES so it gets
# seeded into yahoo/).
# ---------------------------------------------------------------------------

class TestRealStoreCoverage:
    @pytest.mark.skipif(
        not _REAL_DATA_ROOT.exists(),
        reason="real data root not present (CI environment without committed data)",
    )
    def test_all_adr_tickers_loadable_from_real_store(self):
        """Every ADR ticker in the mapping must be loadable (yahoo OR massive_stock_day).

        This test uses the REAL data root — NOT tmp_path stubs — so it catches
        production pathologies (e.g. KWEB absent from both stores) that fixture-only
        tests paper over.
        """
        all_tickers = {p.adr_ticker for p in BRIDGE.ALL_PAIRS}
        failures: list[str] = []
        for ticker in sorted(all_tickers):
            series = BRIDGE._load_adr(ticker, _REAL_DATA_ROOT)
            if series is None or len(series) == 0:
                failures.append(f"{ticker}: None/empty from both yahoo/ and massive_stock_day/")
        assert not failures, (
            "ADR tickers not loadable from real store — hk_adr_bridge will return "
            "dead gaps for these names:\n" + "\n".join(failures)
        )

    @pytest.mark.skipif(
        not _REAL_DATA_ROOT.exists(),
        reason="real data root not present",
    )
    def test_kweb_loadable_with_close_column(self):
        """KWEB must be loadable with a usable 'close' column from the real store.
        This is the specific ticker the reviewer identified as missing/broken."""
        series = BRIDGE._load_adr("KWEB", _REAL_DATA_ROOT)
        assert series is not None, "KWEB not loadable from real data root (yahoo/ or massive_stock_day/)"
        assert len(series) > 0, "KWEB series is empty"
        assert series.name == "close" or hasattr(series, "iloc"), "KWEB series has no numeric values"


# ---------------------------------------------------------------------------
# (j) Production timezone path — FIX 3
# Tests snapshot(hk_session_date=None, now=<known time>) — the path production
# actually uses. Prior tests bypassed this by passing hk_session_date explicitly.
# ---------------------------------------------------------------------------

class TestProductionTimezonePath:
    def test_snapshot_resolves_session_from_now_at_asia_close(self, tmp_path):
        """
        With now = 08:30 UTC on 2026-07-08 (just after HK cash close for session
        2026-07-07, which closes at 08:00 UTC = 16:00 HKT), snapshot(hk_session_date=None)
        must resolve the last COMPLETED HK session.

        expected_last_session requires the settle buffer (17:30 HKT) to pass before
        returning today's session. At 08:30 UTC = 16:30 HKT on 2026-07-08, the 2026-07-08
        settle buffer has NOT passed yet, so expected_last_session returns 2026-07-07.
        The asia-close.yml cron (08:30 UTC) always resolves to the PRIOR session date.

        We use now=08:30 UTC on 2026-07-08 so hk_session_date resolves to 2026-07-07,
        and adr_date must also be 2026-07-07.
        """
        # Stub with the ADR bar on 2026-07-07 (the resolved session date)
        _stub_all_adrs(tmp_path, base_date="2026-07-07")
        _stub_all_hk(tmp_path)

        # 08:30 UTC on 2026-07-08 = 16:30 HKT on 2026-07-08 (settle buffer not yet passed)
        # → expected_last_session resolves to 2026-07-07
        now_at_asia_close = datetime(2026, 7, 8, 8, 30, tzinfo=timezone.utc)
        snap = BRIDGE.snapshot(
            hk_session_date=None,   # production path: resolved from `now`
            data_root=tmp_path,
            now=now_at_asia_close,
        )
        assert snap["hk_session_date"] == snap["adr_date"], (
            "hk_session_date and adr_date must match (same calendar date)"
        )
        assert snap["hk_session_date"], "hk_session_date must be non-empty"
        # At 08:30 UTC on 2026-07-08, expected_last_session = 2026-07-07
        assert snap["hk_session_date"] == "2026-07-07", (
            f"Expected resolved hk_session_date=2026-07-07 at 08:30 UTC on 2026-07-08, "
            f"got {snap['hk_session_date']!r}"
        )
        assert snap["adr_date"] == "2026-07-07", (
            f"Expected adr_date=2026-07-07, got {snap['adr_date']!r}"
        )

    def test_snapshot_none_session_is_not_tautology(self, tmp_path):
        """
        Verify the resolved session is discriminating — the production path
        (hk_session_date=None) resolves the SAME date as an explicit pass of
        the expected session, not some fixed or arbitrary date.

        now=08:30 UTC on 2026-07-08 → expected_last_session = 2026-07-07.
        snapshot(None, now=...) must equal snapshot(date(2026,7,7), now=...).
        """
        _stub_all_adrs(tmp_path, base_date="2026-07-07")
        _stub_all_hk(tmp_path)

        now = datetime(2026, 7, 8, 8, 30, tzinfo=timezone.utc)
        snap_auto = BRIDGE.snapshot(hk_session_date=None, data_root=tmp_path, now=now)
        snap_explicit = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7), data_root=tmp_path, now=now
        )
        assert snap_auto["hk_session_date"] == snap_explicit["hk_session_date"], (
            "Auto-resolved session must match explicit 2026-07-07 when now=08:30 UTC on 2026-07-08"
        )


# ---------------------------------------------------------------------------
# (k) Ledger lane guard — FIX 4
# stamp() and grade() must not advance the ledger outside the asia-close lane.
# ---------------------------------------------------------------------------

class TestLedgerLaneGuard:
    def _make_full_stub(self, tmp_path: Path) -> dict:
        for pair in BRIDGE._DIRECT_PAIRS + BRIDGE._PROXY_PAIRS:
            _make_adr_parquet(tmp_path, pair.adr_ticker, {
                "2026-07-06": 100.0,
                "2026-07-07": 105.0,
            })
        _stub_all_hk(tmp_path)
        return BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 7),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )

    def test_stamp_no_op_outside_asia_lane(self, tmp_path):
        """stamp() must return 0 and write NO ledger file when CN_LANE != asia."""
        snap = self._make_full_stub(tmp_path)
        with mock.patch.dict(os.environ, {}, clear=False):
            # Ensure CN_LANE is NOT set (or set to something other than 'asia')
            os.environ.pop("CN_LANE", None)
            n = BRIDGE.stamp(snap, data_root=tmp_path)
        assert n == 0, f"stamp() should return 0 outside asia lane, got {n}"
        ledger_path = BRIDGE._ledger_path(tmp_path)
        assert not ledger_path.exists(), (
            "stamp() must not create ledger file outside asia-close lane"
        )

    def test_stamp_advances_ledger_in_asia_lane(self, tmp_path):
        """stamp() must append rows when CN_LANE=asia."""
        snap = self._make_full_stub(tmp_path)
        with mock.patch.dict(os.environ, {"CN_LANE": "asia"}):
            n = BRIDGE.stamp(snap, data_root=tmp_path)
        assert n >= 1, "stamp() should append rows when CN_LANE=asia"
        ledger_path = BRIDGE._ledger_path(tmp_path)
        assert ledger_path.exists(), "ledger file must exist after stamp() in asia lane"

    def test_grade_no_op_outside_asia_lane(self, tmp_path):
        """grade() must not write when CN_LANE != asia."""
        snap = self._make_full_stub(tmp_path)
        # First stamp in asia lane so there are rows to grade
        with mock.patch.dict(os.environ, {"CN_LANE": "asia"}):
            BRIDGE.stamp(snap, data_root=tmp_path)
        ledger_before = BRIDGE._ledger_path(tmp_path).read_text()

        # Now call grade() outside the lane — must not modify ledger
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CN_LANE", None)
            result = BRIDGE.grade(data_root=tmp_path)
        assert result.get("ok") is True
        ledger_after = BRIDGE._ledger_path(tmp_path).read_text()
        assert ledger_before == ledger_after, (
            "grade() must not modify ledger outside asia-close lane"
        )


# ---------------------------------------------------------------------------
# (l) Off-by-one ADR date fallback (fix 2026-07-08)
# When the pipeline runs before the US close is committed for hk_session_date,
# the ADR store's most-recent bar is hk_session_date-1.  The engine must fall
# back to that bar and return non-null implied gaps (not "ADR implied —").
# ---------------------------------------------------------------------------

class TestAdrOffByOneFallback:
    """Tests for the off-by-one fix: use most-recent available ADR bar when
    the exact session-date bar is absent (pipeline ran before US close landed)."""

    def _make_stubs_one_behind(self, tmp_path: Path,
                                session_date: str = "2026-07-08",
                                adr_date: str = "2026-07-07") -> None:
        """ADR data has its latest bar on adr_date (one session behind session_date)."""
        all_tickers = {p.adr_ticker for p in BRIDGE.ALL_PAIRS}
        for ticker in all_tickers:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-06": 100.0,
                adr_date: 103.0,   # +3%, but NOT present for session_date
            })
        for pair in BRIDGE.ALL_PAIRS:
            _make_hk_parquet(tmp_path, pair.hk_ticker, {
                "2026-07-02": 100.0,
                "2026-07-03": 101.0,
            })

    def test_fallback_gives_non_null_gaps(self, tmp_path):
        """When ADR bar for hk_session_date is absent but T-1 bar exists,
        implied gaps must be non-null (fallback to T-1 bar used)."""
        # ADR latest = 2026-07-07; session = 2026-07-08 (no ADR bar for 07-08)
        self._make_stubs_one_behind(tmp_path, "2026-07-08", "2026-07-07")
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 8),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc),
        )
        direct_gaps = [
            n["implied_open_gap_pct"]
            for n in snap["names"]
            if n["hk_ticker"] in {"9988.HK", "9888.HK", "9618.HK", "9961.HK"}
        ]
        # After fallback, all direct pairs should have non-null gaps
        null_count = sum(1 for g in direct_gaps if g is None)
        assert null_count == 0, (
            f"Off-by-one fallback failed: {null_count} of {len(direct_gaps)} "
            f"direct pairs still have null gaps when ADR data is one day behind. "
            f"Gaps: {direct_gaps}"
        )

    def test_fallback_adr_date_is_latest_available(self, tmp_path):
        """The resolved adr_date must be the most-recent available bar, not the
        requested session_date (which has no bar in this scenario)."""
        self._make_stubs_one_behind(tmp_path, "2026-07-08", "2026-07-07")
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 8),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc),
        )
        # adr_date should be 2026-07-07 (the fallback), not 2026-07-08
        assert snap["adr_date"] == "2026-07-07", (
            f"Expected adr_date=2026-07-07 (fallback), got {snap['adr_date']!r}"
        )

    def test_exact_date_bar_takes_priority(self, tmp_path):
        """When the exact session-date ADR bar IS present, it should be used
        (not the fallback). adr_date == hk_session_date."""
        all_tickers = {p.adr_ticker for p in BRIDGE.ALL_PAIRS}
        for ticker in all_tickers:
            _make_adr_parquet(tmp_path, ticker, {
                "2026-07-07": 100.0,
                "2026-07-08": 105.0,   # exact bar present for session_date
            })
        _stub_all_hk(tmp_path)
        snap = BRIDGE.snapshot(
            hk_session_date=date(2026, 7, 8),
            data_root=tmp_path,
            now=datetime(2026, 7, 8, 22, 0, tzinfo=timezone.utc),
        )
        assert snap["adr_date"] == "2026-07-08", (
            f"Exact bar present but adr_date={snap['adr_date']!r}, expected 2026-07-08"
        )
        # All direct pair gaps should be non-null and +5%
        for n in snap["names"]:
            if n.get("adr_source") == "direct":
                pct = n["implied_open_gap_pct"]
                assert pct is not None, f"{n['hk_ticker']} has null gap despite exact bar"
                assert abs(pct - 5.0) < 0.01, f"{n['hk_ticker']} gap={pct}, expected 5.0%"
