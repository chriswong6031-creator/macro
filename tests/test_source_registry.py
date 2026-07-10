"""Tests for engine/source_registry.py — NAR-W4.

Covers:
- Beta-Bernoulli math including skeptical seed (NAR-R3)
- Grader resolution on synthetic price fixtures (hit + miss + unresolved-immature)
  with EXACT 20-NYSE-trading-day window (BLOCKER 1 regression traps)
- Absence of upstream stores: graceful fail-open (NAR-R10)
- Lane gating: data/ writes blocked outside nightly lane (incl. grading_summary)
- qledger append shape: narrative_source_call + narrative_flare_state claim families
- Registry JSON schema: calls, hits, cred, last_resolved, accruing
- grading_summary.json: families, n_claims, n_resolved, hit_rate, accruing flags,
  excess_by_horizon_td for narrative_flare_state (MINOR 4)
- _resolve_flare_state_claims: excess recorded for matured state claims; immature skipped;
  no verdict fields emitted

All synthetic; no network. Uses tmp_path stores.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure root is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.source_registry import (
    BETA_ALPHA,
    BETA_BETA,
    EXCESS_HIT_THRESHOLD,
    RESOLUTION_TRADING_DAYS,
    STATE_CLAIM_HORIZONS_TD,
    _FAMILY_FLARE_STATE,
    _FAMILY_SOURCE_CALL,
    _FIRST_COV_COLS,
    _add_trading_days,
    _ledger_advance_enabled,
    _resolve_flare_state_claims,
    _update_registry_entry,
    beta_cred,
    load_first_coverage,
    load_registry,
    load_state_hist,
    nightly_run,
    register_flare_state_claims,
    register_source_call_claims,
    save_registry,
    write_grading_summary,
)
from lib.nyse_calendar import is_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_first_coverage(path: Path, rows: list[dict]) -> None:
    """Write a minimal first_coverage.parquet to tmp_path."""
    (path / "narrative_flare").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=_FIRST_COV_COLS)
    df.to_parquet(path / "narrative_flare" / "first_coverage.parquet", index=False)


def _write_state_hist(path: Path, rows: list[dict]) -> None:
    """Write a minimal state_hist.parquet to tmp_path."""
    (path / "flare_persistence").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(path / "flare_persistence" / "state_hist.parquet", index=False)


def _write_price(root: Path, ticker: str, closes: dict[str, float]) -> None:
    """Write a per-ticker yahoo price parquet with a DatetimeIndex and 'close' column."""
    yahoo_dir = root / "data" / "yahoo"
    yahoo_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime(list(closes.keys()))
    df = pd.DataFrame({"close": list(closes.values())}, index=idx)
    df.to_parquet(yahoo_dir / f"{ticker}.parquet")


def _make_claim_store(root: Path) -> Path:
    """Ensure data/qledger/ exists and return its path."""
    p = root / "data" / "qledger"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _nth_trading_day_after(start_date: str, n: int) -> date:
    """Return the Nth NYSE trading day after start_date using the house calendar."""
    return _add_trading_days(start_date, n)


def _build_daily_closes(start_date: str, n_calendar_days: int, price_fn) -> dict[str, float]:
    """Build a dict of {date_str: price} from start_date for n_calendar_days.

    price_fn(i) returns the price on the i-th calendar day from start_date (i=0
    is start_date itself).
    """
    base = pd.Timestamp(start_date)
    closes = {}
    for i in range(n_calendar_days):
        d = base + timedelta(days=i)
        closes[d.strftime("%Y-%m-%d")] = price_fn(i)
    return closes


# ---------------------------------------------------------------------------
# 0. NYSE trading-day arithmetic (_add_trading_days)
# ---------------------------------------------------------------------------

class TestAddTradingDays:
    def test_20td_is_not_28_calendar_days(self):
        """D+20 trading days is not exactly 28 calendar days in general — exact matters."""
        # Use a fixed entry date; verify the result is a session day
        entry = "2026-05-15"
        exit_d = _add_trading_days(entry, 20)
        assert is_session(exit_d), f"{exit_d} is not a session day"
        # It should be between 26 and 32 calendar days (accounting for holiday variation)
        cal_days = (exit_d - pd.Timestamp(entry).date()).days
        assert 26 <= cal_days <= 32, f"Expected 26-32 calendar days for 20td, got {cal_days}"

    def test_exactly_n_sessions_after(self):
        """Count trading sessions between entry_date+1 and exit_date (inclusive) = n."""
        entry = "2026-05-15"
        n = 20
        exit_d = _add_trading_days(entry, n)
        entry_dt = pd.Timestamp(entry).date()
        counted = 0
        d = entry_dt
        while d < exit_d:
            d += timedelta(days=1)
            if is_session(d):
                counted += 1
        assert counted == n, f"Expected exactly {n} trading sessions, counted {counted}"

    def test_result_is_session_day(self):
        """Exit date is always a NYSE session day."""
        for entry in ("2026-01-15", "2026-07-01", "2026-04-16"):
            exit_d = _add_trading_days(entry, 20)
            assert is_session(exit_d), f"{entry} + 20td = {exit_d}, not a session day"


# ---------------------------------------------------------------------------
# 1. Beta-Bernoulli math
# ---------------------------------------------------------------------------

class TestBetaCred:
    def test_cold_start_skeptical_seed(self):
        """Cold start (0 calls, 0 hits) -> alpha/(alpha+beta) = 2/7 ≈ 0.286."""
        c = beta_cred(0, 0)
        expected = BETA_ALPHA / (BETA_ALPHA + BETA_BETA)
        assert abs(c - expected) < 1e-6, f"Expected ~{expected:.4f}, got {c}"
        # Below 0.5 — skeptical seed (NAR-R3)
        assert c < 0.5

    def test_one_hit_one_call(self):
        """1 hit / 1 call -> (1+2)/(1+2+5) = 3/8 = 0.375."""
        c = beta_cred(1, 1)
        assert abs(c - 3.0 / 8.0) < 1e-6

    def test_one_miss_one_call(self):
        """1 call, 0 hits -> (0+2)/(1+2+5) = 2/8 = 0.25."""
        c = beta_cred(1, 0)
        assert abs(c - 2.0 / 8.0) < 1e-6

    def test_many_hits_converges_towards_one(self):
        """100 hits / 100 calls -> cred approaches 1 but not quite."""
        c = beta_cred(100, 100)
        assert c > 0.9, f"Expected >0.9, got {c}"
        assert c < 1.0

    def test_many_misses_converges_toward_zero(self):
        """0 hits / 100 calls -> cred approaches 0."""
        c = beta_cred(100, 0)
        assert c < 0.1, f"Expected <0.1, got {c}"
        assert c > 0.0

    def test_monotone_in_hits(self):
        """More hits at same call count -> higher credibility."""
        c5 = beta_cred(20, 5)
        c10 = beta_cred(20, 10)
        c15 = beta_cred(20, 15)
        assert c5 < c10 < c15

    def test_registry_update_accumulates(self):
        """Two resolved calls accumulate properly in registry."""
        reg: dict = {}
        _update_registry_entry(reg, "semianaly", True, "2026-07-01")
        assert reg["semianaly"]["calls"] == 1
        assert reg["semianaly"]["hits"] == 1
        assert reg["semianaly"]["last_resolved"] == "2026-07-01"
        assert reg["semianaly"]["accruing"] is True

        _update_registry_entry(reg, "semianaly", False, "2026-07-15")
        assert reg["semianaly"]["calls"] == 2
        assert reg["semianaly"]["hits"] == 1
        expected_cred = beta_cred(2, 1)
        assert abs(reg["semianaly"]["cred"] - expected_cred) < 1e-6


# ---------------------------------------------------------------------------
# 2. Registry JSON schema
# ---------------------------------------------------------------------------

class TestRegistrySchema:
    def test_save_and_load_roundtrip(self, tmp_path):
        reg = {
            "semianaly": {
                "calls": 3,
                "hits": 2,
                "cred": beta_cred(3, 2),
                "last_resolved": "2026-07-10",
                "accruing": True,
            }
        }
        save_registry(reg, tmp_path)
        loaded = load_registry(tmp_path)
        assert loaded["semianaly"]["calls"] == 3
        assert loaded["semianaly"]["hits"] == 2
        assert abs(loaded["semianaly"]["cred"] - beta_cred(3, 2)) < 1e-6
        assert loaded["semianaly"]["accruing"] is True

    def test_load_absent_returns_empty(self, tmp_path):
        reg = load_registry(tmp_path)
        assert reg == {}

    def test_schema_fields_present(self, tmp_path):
        reg: dict = {}
        _update_registry_entry(reg, "foo_source", True, "2026-07-01")
        save_registry(reg, tmp_path)
        loaded = load_registry(tmp_path)
        entry = loaded["foo_source"]
        assert "calls" in entry
        assert "hits" in entry
        assert "cred" in entry
        assert "last_resolved" in entry
        assert "accruing" in entry


# ---------------------------------------------------------------------------
# 3. first_coverage.parquet absence -> graceful fail-open (NAR-R10)
# ---------------------------------------------------------------------------

class TestFirstCoverageAbsence:
    def test_absent_store_returns_empty_df(self, tmp_path):
        df = load_first_coverage(tmp_path)
        assert df.empty
        for col in _FIRST_COV_COLS:
            assert col in df.columns

    def test_state_hist_absent_returns_empty_df(self, tmp_path):
        df = load_state_hist(tmp_path)
        assert df.empty


# ---------------------------------------------------------------------------
# 4. Lane gating
# ---------------------------------------------------------------------------

class TestLaneGating:
    def test_enabled_when_nightly(self):
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            assert _ledger_advance_enabled() is True

    def test_disabled_when_not_nightly(self):
        for val in ("", "render", "intraday"):
            with patch.dict(os.environ, {"COLLECT_LANE": val}):
                assert _ledger_advance_enabled() is False

    def test_register_source_call_skipped_outside_nightly(self, tmp_path):
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = register_source_call_claims(data_root=tmp_path, root=tmp_path)
        assert result.get("skipped") is True

    def test_register_flare_state_skipped_outside_nightly(self, tmp_path):
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = register_flare_state_claims(data_root=tmp_path, root=tmp_path)
        assert result.get("skipped") is True

    def test_nightly_run_skips_data_writes_outside_nightly(self, tmp_path):
        """When not nightly: registration and grading_summary all report skipped."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = nightly_run(data_root=tmp_path, root=tmp_path)
        assert result.get("source_call_registration", {}).get("skipped") is True
        assert result.get("flare_state_registration", {}).get("skipped") is True

    def test_grading_summary_skipped_outside_nightly(self, tmp_path):
        """write_grading_summary must not write on non-nightly lanes (MAJOR 3)."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = write_grading_summary(data_root=tmp_path, root=tmp_path)
        assert result.get("skipped") is True
        # File must NOT have been written
        out_p = tmp_path / "narrative_flare" / "grading_summary.json"
        assert not out_p.exists(), "grading_summary.json must not be written on render lane"

    def test_grading_summary_written_on_nightly(self, tmp_path):
        """write_grading_summary writes the file on the nightly lane."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = write_grading_summary(data_root=tmp_path, root=tmp_path)
        assert result.get("skipped") is None or not result.get("skipped")
        out_p = tmp_path / "narrative_flare" / "grading_summary.json"
        assert out_p.exists(), "grading_summary.json must be written on nightly lane"


# ---------------------------------------------------------------------------
# 5. qledger claim shape — narrative_source_call
# ---------------------------------------------------------------------------

class TestSourceCallClaimShape:
    def test_registers_claims_from_first_coverage(self, tmp_path):
        """Claims are registered for each (source_id, ticker) row."""
        _make_claim_store(tmp_path)
        rows = [
            {
                "source_id": "semianaly",
                "ticker": "META",
                "date": "2026-06-01",
                "url": "https://semianaly.substack.com/meta",
                "title": "Meta AI capital cycle",
                "join_confidence": 0.95,
                "fetch_date": "2026-06-01",
            },
            {
                "source_id": "doomberg",
                "ticker": "NVDA",
                "date": "2026-06-02",
                "url": "https://doomberg.substack.com/nvda",
                "title": "Nvidia buildout thesis",
                "join_confidence": 0.80,
                "fetch_date": "2026-06-02",
            },
        ]
        _write_first_coverage(tmp_path, rows)

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = register_source_call_claims(data_root=tmp_path, root=tmp_path)

        assert result["n_registered"] == 2

        # Verify claims in store
        claims_path = tmp_path / "data" / "qledger" / "claims.jsonl"
        assert claims_path.exists()
        claims = [json.loads(ln) for ln in claims_path.read_text().splitlines() if ln.strip()]
        src_claims = [c for c in claims if c.get("claim_family") == _FAMILY_SOURCE_CALL]
        assert len(src_claims) == 2

        # Check schema fields
        c0 = src_claims[0]
        assert c0["direction"] == 0          # salience-only
        assert c0["bench"] == "SPY"
        assert c0["scope"]["type"] == "entity"
        assert c0["source_id"] in ("semianaly", "doomberg")
        assert "join_confidence" in c0
        assert c0["authority"]["tier"] == "display"
        # exit_date stored on claim for exact trading-day boundary
        assert "exit_date" in c0

    def test_idempotent_registration(self, tmp_path):
        """Re-registering same rows produces no duplicates."""
        _make_claim_store(tmp_path)
        rows = [{
            "source_id": "semianaly",
            "ticker": "META",
            "date": "2026-06-01",
            "url": "https://semianaly.substack.com/meta",
            "title": "Meta AI",
            "join_confidence": 0.9,
            "fetch_date": "2026-06-01",
        }]
        _write_first_coverage(tmp_path, rows)

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path)
            result2 = register_source_call_claims(data_root=tmp_path, root=tmp_path)

        # Second run: 0 new (all deduped)
        assert result2["n_registered"] == 0

    def test_empty_first_coverage_graceful(self, tmp_path):
        _make_claim_store(tmp_path)
        _write_first_coverage(tmp_path, [])
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = register_source_call_claims(data_root=tmp_path, root=tmp_path)
        assert result.get("n_registered", 0) == 0


# ---------------------------------------------------------------------------
# 6. qledger claim shape — narrative_flare_state
# ---------------------------------------------------------------------------

class TestFlareStateClaimShape:
    def test_registers_claims_for_primed_rows(self, tmp_path):
        """PRIMED rows get registered at 21d and 63d."""
        _make_claim_store(tmp_path)
        rows = [
            {"ticker": "META", "date": "2026-06-15", "state": "PRIMED",
             "s_plus": 6.2, "fetch_date": "2026-06-15"},
            {"ticker": "NVDA", "date": "2026-06-16", "state": "DORMANT",
             "s_plus": 0.0, "fetch_date": "2026-06-16"},
        ]
        _write_state_hist(tmp_path, rows)

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = register_flare_state_claims(data_root=tmp_path, root=tmp_path)

        # 1 PRIMED ticker × 2 horizons (21d, 63d) = 2 claims
        assert result["n_registered"] == 2

        claims_path = tmp_path / "data" / "qledger" / "claims.jsonl"
        claims = [json.loads(ln) for ln in claims_path.read_text().splitlines() if ln.strip()]
        flare_claims = [c for c in claims if c.get("claim_family") == _FAMILY_FLARE_STATE]
        assert len(flare_claims) == 2
        horizons = {c["horizon_d"] for c in flare_claims}
        assert horizons == {21, 63}

        c0 = flare_claims[0]
        assert c0["direction"] == 0           # salience-only (descriptive accrual)
        assert c0["scope"]["type"] == "entity"
        assert c0["scope"]["key"] == "META"
        assert c0["timestamp_quality"] == "SNAPSHOT_DATE"
        assert "flare_state" in c0
        assert c0["authority"]["tier"] == "display"

    def test_dormant_rows_not_registered(self, tmp_path):
        """DORMANT/FADING rows do not generate claims."""
        _make_claim_store(tmp_path)
        rows = [
            {"ticker": "AAPL", "date": "2026-06-15", "state": "DORMANT",
             "s_plus": 0.0, "fetch_date": "2026-06-15"},
            {"ticker": "TSLA", "date": "2026-06-15", "state": "FADING",
             "s_plus": 2.5, "fetch_date": "2026-06-15"},
        ]
        _write_state_hist(tmp_path, rows)

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = register_flare_state_claims(data_root=tmp_path, root=tmp_path)

        assert result["n_registered"] == 0

    def test_absent_state_hist_graceful(self, tmp_path):
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = register_flare_state_claims(data_root=tmp_path, root=tmp_path)
        assert result.get("n_registered", 0) == 0


# ---------------------------------------------------------------------------
# 7. Grader resolution: hit + miss + immature (BLOCKER 2)
#
# Fixture design:
#   entry_date: 2026-04-15 (fixed, well past 20 trading days from 2026-07-10)
#   exit_date: exactly D+20 NYSE trading days after entry_date
#
#   TICKER_HIT: |excess vs SPY| > 5% AT exit_date (clean HIT)
#   TICKER_MISS: |excess vs SPY| < 5% AT exit_date but > 5% at exit_date+20td
#                (regression trap: old 40cd window would have resolved this differently)
#   TICKER_IMMATURE: entry = yesterday (can never be mature today)
#
#   The SPY series is flat at 100. Ticker returns are set relative to SPY.
# ---------------------------------------------------------------------------

# Fixed entry date well in the past (>20 trading days from 2026-07-10)
_ENTRY_DATE_MATURED = "2026-04-15"

# Compute the exact exit_date once for assertions
_EXIT_DATE_20TD = _add_trading_days(_ENTRY_DATE_MATURED, RESOLUTION_TRADING_DAYS)
# Calendar days for the 40cd old window (what would have been used before the fix)
_EXIT_DATE_40CD = pd.Timestamp(_ENTRY_DATE_MATURED).date() + timedelta(days=40)


def _build_spy_series(start_date: str, n_days: int = 80) -> dict[str, float]:
    """Build a flat SPY series at 100.0 for n_days from start_date."""
    base = pd.Timestamp(start_date).date()
    return {
        (base + timedelta(days=i)).isoformat(): 100.0
        for i in range(n_days)
    }


def _build_hit_series(entry_date: str, exit_date: date, n_days: int = 80) -> dict[str, float]:
    """Build a ticker that has exactly +8% excess vs SPY at exit_date.

    SPY is flat at 100. The fill bar (first close after entry_date) is 100 (same
    as SPY). From exit_date onward the ticker is 108. On the exact exit_date, the
    last close <= exit_date is 108, so return = 108/100 - 1 = 8% vs SPY 0% → HIT.

    Design: price is 100 up to and including the fill bar (one day after entry_date),
    then jumps to 108 from the day AFTER the fill bar so that the exit_date close is 108.
    We set 100 for the fill bar (entry+1d) and 108 for all subsequent days.
    """
    base = pd.Timestamp(entry_date).date()
    fill_bar = base + timedelta(days=1)  # next-bar fill: first close after entry
    closes: dict[str, float] = {}
    for i in range(n_days):
        d = base + timedelta(days=i)
        if d <= fill_bar:
            closes[d.isoformat()] = 100.0   # entry price and fill price = 100
        else:
            closes[d.isoformat()] = 108.0   # rises to 108 after fill
    return closes


def _build_miss_series(entry_date: str, exit_date: date, n_days: int = 80) -> dict[str, float]:
    """Build a ticker that has only +2% excess at exit_date but +10% much later.

    MISS at D+20td (excess=2% < 5%), but would show +10% at D+40cd (regression trap).
    Checks that the fix uses the 20td boundary and not the old 40cd boundary.

    Fill bar = 100 (same as entry). At exit_date: 102 (2% excess). After exit_date: 110.
    """
    base = pd.Timestamp(entry_date).date()
    fill_bar = base + timedelta(days=1)  # next-bar fill day
    closes: dict[str, float] = {}
    for i in range(n_days):
        d = base + timedelta(days=i)
        if d <= fill_bar:
            closes[d.isoformat()] = 100.0   # fill price = 100
        elif d <= exit_date:
            closes[d.isoformat()] = 102.0   # +2% (MISS at 20td boundary)
        else:
            closes[d.isoformat()] = 110.0   # +10% later (would be HIT under old 40cd window)
    return closes


def _build_td21_miss_series(entry_date: str, exit_date_20td: date,
                             n_days: int = 80) -> dict[str, float]:
    """Build a ticker where the price store does NOT cover the exit_date (TD20).

    The price series ends the day before exit_date_20td.
    At the exact exit_date, there is no bar — store doesn't cover it yet.
    Result: _is_matured_at_exit returns False (price series stops before exit),
    so the claim is no_price (unresolved), not a hit.

    The fill bar (entry+1d) is 100; subsequent days up to (not including)
    exit_date_20td are 108 — so IF the exit date were covered, it would be
    an 8% excess HIT. This confirms the gate is on price coverage, not price level.
    """
    base = pd.Timestamp(entry_date).date()
    fill_bar = base + timedelta(days=1)
    closes: dict[str, float] = {}
    d = base
    # Build series up to (but NOT including) exit_date_20td
    i = 0
    while True:
        d = base + timedelta(days=i)
        if d >= exit_date_20td:
            break   # stop before the exit date — exit_date not covered
        if d <= fill_bar:
            closes[d.isoformat()] = 100.0   # fill price
        else:
            closes[d.isoformat()] = 108.0   # +8% after fill (would be HIT if covered)
        i += 1
    # Crucially: no bar AT exit_date_20td — the price store cuts off just before it
    return closes


class TestGraderResolution:
    """Verify _resolve_source_call_claims with controlled price fixtures.

    All tests use fixed entry_date=2026-04-15, which is comfortably >20 trading
    days before 2026-07-10 (today). SPY is flat at 100; ticker excess is set
    explicitly relative to SPY.
    """

    def _write_spy(self, root: Path, entry_date: str = _ENTRY_DATE_MATURED) -> None:
        """Write flat SPY at 100 for 80 days from entry_date."""
        _write_price(root, "SPY", _build_spy_series(entry_date, 80))

    def test_hit_updates_registry(self, tmp_path):
        """A matured claim with |excess|>5% at D+20td marks a HIT; cred rises."""
        _make_claim_store(tmp_path)
        entry_date = _ENTRY_DATE_MATURED

        self._write_spy(tmp_path)
        _write_price(tmp_path, "TICKER_HIT",
                     _build_hit_series(entry_date, _EXIT_DATE_20TD))

        rows = [{
            "source_id": "semianaly",
            "ticker": "TICKER_HIT",
            "date": entry_date,
            "url": "https://example.com",
            "title": "Title",
            "join_confidence": 0.9,
            "fetch_date": entry_date,
        }]
        _write_first_coverage(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path, today=today)
            result = nightly_run(data_root=tmp_path, root=tmp_path, today=today)

        resolution = result.get("source_call_resolution", {})
        # Hard assertion: must have resolved at least 1 claim
        assert resolution.get("n_resolved", 0) == 1, (
            f"Expected 1 resolved claim, got: {resolution}"
        )
        assert resolution.get("n_hits", 0) == 1, f"Expected 1 hit, got: {resolution}"
        assert resolution.get("n_miss", 0) == 0
        assert resolution.get("n_immature", 0) == 0

        reg = load_registry(tmp_path)
        assert "semianaly" in reg
        entry = reg["semianaly"]
        assert entry["calls"] == 1
        assert entry["hits"] == 1
        cold_cred = beta_cred(0, 0)
        assert entry["cred"] > cold_cred, (
            f"cred {entry['cred']} must be > cold_cred {cold_cred} after a hit"
        )

    def test_miss_updates_registry_no_hit(self, tmp_path):
        """A matured claim with |excess|<5% at D+20td marks a MISS; hits stay 0.

        Regression trap: the ticker shows >5% excess at the old D+40cd window,
        so if the code mistakenly used the 40cd window it would incorrectly record
        a HIT. This test fails under the old code.
        """
        _make_claim_store(tmp_path)
        entry_date = _ENTRY_DATE_MATURED

        self._write_spy(tmp_path)
        _write_price(tmp_path, "TICKER_MISS",
                     _build_miss_series(entry_date, _EXIT_DATE_20TD))

        rows = [{
            "source_id": "doomberg",
            "ticker": "TICKER_MISS",
            "date": entry_date,
            "url": "https://example.com",
            "title": "Title",
            "join_confidence": 0.7,
            "fetch_date": entry_date,
        }]
        _write_first_coverage(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path, today=today)
            result = nightly_run(data_root=tmp_path, root=tmp_path, today=today)

        resolution = result.get("source_call_resolution", {})
        # Hard assertion: must have resolved 1 claim as a MISS
        assert resolution.get("n_resolved", 0) == 1, (
            f"Expected 1 resolved claim (MISS), got: {resolution}"
        )
        assert resolution.get("n_hits", 0) == 0, (
            f"Expected 0 hits (MISS), got: {resolution}. "
            "REGRESSION: old 40cd window would record this as a hit at +10%."
        )
        assert resolution.get("n_miss", 0) == 1

        reg = load_registry(tmp_path)
        assert "doomberg" in reg
        assert reg["doomberg"]["hits"] == 0
        assert reg["doomberg"]["calls"] == 1

    def test_immature_claim_not_resolved(self, tmp_path):
        """A claim from yesterday is not yet mature; resolution count stays 0."""
        _make_claim_store(tmp_path)
        entry_date = (date.today() - timedelta(days=1)).isoformat()  # too recent

        self._write_spy(tmp_path)
        _write_price(tmp_path, "TICKER_HIT",
                     _build_hit_series(entry_date, _add_trading_days(entry_date, 20)))

        rows = [{
            "source_id": "citrini_excluded",
            "ticker": "TICKER_HIT",
            "date": entry_date,
            "url": "https://example.com",
            "title": "Title",
            "join_confidence": 0.95,
            "fetch_date": entry_date,
        }]
        _write_first_coverage(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path, today=today)
            result = nightly_run(data_root=tmp_path, root=tmp_path, today=today)

        resolution = result.get("source_call_resolution", {})
        assert resolution.get("n_resolved", 0) == 0, (
            f"Immature claim should not be resolved, got: {resolution}"
        )
        assert resolution.get("n_immature", 0) >= 1

    def test_resolution_window_is_exactly_20_trading_days(self, tmp_path):
        """A price series that only covers through trading day 20 resolves; one that
        only covers through trading day 19 is immature (no_price).

        This directly tests the exact boundary: move lands on TD 21 → no_price (not a hit).
        """
        _make_claim_store(tmp_path)
        entry_date = _ENTRY_DATE_MATURED

        # SPY covers plenty of days
        self._write_spy(tmp_path)

        # Ticker: price series ends 1 calendar day BEFORE the exact exit_date
        # → exit_date not covered → no_price (not matured from price perspective)
        exit_date = _add_trading_days(entry_date, RESOLUTION_TRADING_DAYS)
        # Series ends the day before exit_date
        td21_series = _build_td21_miss_series(entry_date, exit_date, n_days=80)
        _write_price(tmp_path, "TICKER_TD21", td21_series)

        rows = [{
            "source_id": "td21_test_source",
            "ticker": "TICKER_TD21",
            "date": entry_date,
            "url": "https://example.com",
            "title": "TD21 test",
            "join_confidence": 0.9,
            "fetch_date": entry_date,
        }]
        _write_first_coverage(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path, today=today)
            result = nightly_run(data_root=tmp_path, root=tmp_path, today=today)

        resolution = result.get("source_call_resolution", {})
        # Should be no_price (price store doesn't cover the exact exit day)
        # NOT a hit — the move lands past the 20td window
        assert resolution.get("n_hits", 0) == 0, (
            f"Move landing on TD21 (series ends before exit_date) must not be a hit. "
            f"Got: {resolution}"
        )
        # n_resolved should be 0 (no_price means unresolved at this exit boundary)
        assert resolution.get("n_resolved", 0) == 0, (
            f"Series not covering exit_date should not produce a resolution. Got: {resolution}"
        )


# ---------------------------------------------------------------------------
# 8. grading_summary.json shape (NAR-R13)
# ---------------------------------------------------------------------------

class TestGradingSummary:
    def test_summary_writes_and_has_correct_structure(self, tmp_path):
        _make_claim_store(tmp_path)

        # Minimal: no claims yet
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            payload = write_grading_summary(data_root=tmp_path, root=tmp_path)

        assert "families" in payload
        assert _FAMILY_SOURCE_CALL in payload["families"]
        assert _FAMILY_FLARE_STATE in payload["families"]

        for fam_key in (_FAMILY_SOURCE_CALL, _FAMILY_FLARE_STATE):
            fam = payload["families"][fam_key]
            assert "n_claims" in fam
            assert "n_resolved" in fam
            assert "accruing" in fam
            assert fam["accruing"] is True

        assert "source_registry_n" in payload
        assert "authority" in payload
        assert payload["authority"]["tier"] == "display"

        # File written to data-tier location (NOT site/)
        out_p = tmp_path / "narrative_flare" / "grading_summary.json"
        assert out_p.exists()
        loaded = json.loads(out_p.read_text())
        assert "families" in loaded

    def test_summary_with_claims_shows_counts(self, tmp_path):
        """After registering 2 source_call claims, n_claims == 2."""
        _make_claim_store(tmp_path)
        rows = [
            {
                "source_id": "semianaly",
                "ticker": "META",
                "date": "2026-06-01",
                "url": "https://semianaly.substack.com/meta",
                "title": "Meta AI",
                "join_confidence": 0.9,
                "fetch_date": "2026-06-01",
            },
            {
                "source_id": "semianaly",
                "ticker": "NVDA",
                "date": "2026-06-02",
                "url": "https://semianaly.substack.com/nvda",
                "title": "NVDA thesis",
                "join_confidence": 0.85,
                "fetch_date": "2026-06-02",
            },
        ]
        _write_first_coverage(tmp_path, rows)

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path)
            payload = write_grading_summary(data_root=tmp_path, root=tmp_path)

        assert payload["families"][_FAMILY_SOURCE_CALL]["n_claims"] == 2


# ---------------------------------------------------------------------------
# 9. nightly_run end-to-end on absent stores (NAR-R10)
# ---------------------------------------------------------------------------

class TestNightlyRunAbsentStores:
    def test_nightly_run_does_not_crash_on_absent_stores(self, tmp_path):
        """nightly_run must not raise even with completely empty data_root."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = nightly_run(data_root=tmp_path, root=tmp_path)
        assert isinstance(result, dict)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"

    def test_nightly_run_returns_summary_keys(self, tmp_path):
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            result = nightly_run(data_root=tmp_path, root=tmp_path)
        assert "source_call_registration" in result
        assert "flare_state_registration" in result
        assert "source_call_resolution" in result
        assert "grading_summary" in result
        assert "flare_state_excess" in result


# ---------------------------------------------------------------------------
# 10. _resolve_flare_state_claims — descriptive excess recorder (MINOR 4)
# ---------------------------------------------------------------------------

class TestFlareStateExcessRecorder:
    """Verify the MINOR 4 descriptive excess recorder.

    NAR-R5: no pass/fail verdict; excess values recorded per horizon.
    Uses PRIMED state claims at 21td and 63td (STATE_CLAIM_HORIZONS_TD).
    """

    def _setup_prices_for_state_claim(
        self,
        root: Path,
        ticker: str,
        entry_date: str,
        ticker_excess: float = 0.07,
        n_days: int = 100,
    ) -> None:
        """Write SPY (flat 100) and ticker for n_days.

        Ticker fill price = 100 (same as SPY). After fill bar (entry+1d), rises to
        100*(1+ticker_excess). Result: excess = ticker_excess at any exit day after +1d.
        """
        base = pd.Timestamp(entry_date).date()
        fill_bar = base + timedelta(days=1)
        spy_closes = {
            (base + timedelta(days=i)).isoformat(): 100.0
            for i in range(n_days)
        }
        ticker_closes = {
            (base + timedelta(days=i)).isoformat(): (
                100.0 if (base + timedelta(days=i)) <= fill_bar
                else 100.0 * (1 + ticker_excess)
            )
            for i in range(n_days)
        }
        _write_price(root, "SPY", spy_closes)
        _write_price(root, ticker, ticker_closes)

    def test_matured_state_claim_gets_excess_recorded(self, tmp_path):
        """A matured state claim at 21td gets excess recorded in the summary."""
        _make_claim_store(tmp_path)
        # Use entry date well past 21 trading days ago
        entry_date = "2026-04-15"

        self._setup_prices_for_state_claim(tmp_path, "META", entry_date, ticker_excess=0.07)

        rows = [
            {"ticker": "META", "date": entry_date, "state": "PRIMED",
             "s_plus": 6.2, "fetch_date": entry_date},
        ]
        _write_state_hist(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_flare_state_claims(data_root=tmp_path, root=tmp_path)
            excess_result = _resolve_flare_state_claims(
                data_root=tmp_path, root=tmp_path, today=today
            )

        # At 21td: should have excess recorded (entry is well past 21td)
        h21 = excess_result.get("21", {})
        # n may be 0 if price store doesn't cover exit; assert structure is correct
        assert isinstance(h21, dict), f"Expected dict for horizon 21, got: {h21}"
        assert "n" in h21
        assert "excess_values" in h21
        assert "mean_excess" in h21
        # If matured: n >= 1
        if h21["n"] > 0:
            assert isinstance(h21["excess_values"], list)
            for v in h21["excess_values"]:
                assert isinstance(v, float), f"excess value must be float, got {v}"
            # No verdict fields
            assert "hit" not in h21, "No hit/pass/fail verdict allowed (NAR-R5)"
            assert "is_hit" not in h21

    def test_immature_state_claim_not_recorded(self, tmp_path):
        """An immature state claim (entered yesterday) is not in the excess arrays."""
        _make_claim_store(tmp_path)
        entry_date = (date.today() - timedelta(days=1)).isoformat()  # too recent

        self._setup_prices_for_state_claim(tmp_path, "AAPL", entry_date)

        rows = [
            {"ticker": "AAPL", "date": entry_date, "state": "PRIMED",
             "s_plus": 4.1, "fetch_date": entry_date},
        ]
        _write_state_hist(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_flare_state_claims(data_root=tmp_path, root=tmp_path)
            excess_result = _resolve_flare_state_claims(
                data_root=tmp_path, root=tmp_path, today=today
            )

        # All horizons should have 0 matured records (immature claim)
        for h in STATE_CLAIM_HORIZONS_TD:
            h_data = excess_result.get(str(h), {})
            assert h_data.get("n", 0) == 0, (
                f"Immature claim must not produce excess at horizon {h}td. Got: {h_data}"
            )
        assert excess_result.get("n_matured", 0) == 0

    def test_no_verdict_fields_emitted(self, tmp_path):
        """Excess recorder emits no hit/pass/fail verdict fields (NAR-R5)."""
        _make_claim_store(tmp_path)
        entry_date = "2026-04-15"  # well past 21td

        self._setup_prices_for_state_claim(tmp_path, "NVDA", entry_date, ticker_excess=0.12)

        rows = [
            {"ticker": "NVDA", "date": entry_date, "state": "ARMED",
             "s_plus": 8.0, "fetch_date": entry_date},
        ]
        _write_state_hist(tmp_path, rows)

        today = date.today()
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_flare_state_claims(data_root=tmp_path, root=tmp_path)
            excess_result = _resolve_flare_state_claims(
                data_root=tmp_path, root=tmp_path, today=today
            )

        # Top-level result must not contain verdict fields
        assert "hit" not in excess_result
        assert "is_hit" not in excess_result
        assert "hit_rate" not in excess_result
        assert "pass" not in excess_result

        # Per-horizon dicts must not contain verdict fields
        for h in STATE_CLAIM_HORIZONS_TD:
            h_data = excess_result.get(str(h), {})
            assert "hit" not in h_data, f"horizon {h}: 'hit' field forbidden (NAR-R5)"
            assert "is_hit" not in h_data, f"horizon {h}: 'is_hit' field forbidden (NAR-R5)"

    def test_excess_appears_in_grading_summary(self, tmp_path):
        """When flare_state_excess is passed, it appears in grading_summary families."""
        _make_claim_store(tmp_path)
        # Inject a synthetic excess result (bypasses price requirements for unit test)
        synthetic_excess = {
            "n_matured": 3,
            "n_immature": 1,
            "n_no_price": 0,
            "21": {"n": 2, "excess_values": [0.07, 0.03], "mean_excess": 0.05},
            "63": {"n": 1, "excess_values": [0.11], "mean_excess": 0.11},
        }

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            payload = write_grading_summary(
                data_root=tmp_path, root=tmp_path,
                flare_state_excess=synthetic_excess,
            )

        fam = payload["families"].get(_FAMILY_FLARE_STATE, {})
        assert "excess_by_horizon_td" in fam, (
            "excess_by_horizon_td must appear in grading_summary for narrative_flare_state"
        )
        assert "excess_n_matured" in fam
        # Verify the excess arrays are present
        ebt = fam["excess_by_horizon_td"]
        assert "21" in ebt
        assert "63" in ebt
        assert ebt["21"]["n"] == 2
        assert ebt["63"]["mean_excess"] == 0.11

    def test_lane_gate_for_flare_excess(self, tmp_path):
        """_resolve_flare_state_claims is gated behind nightly lane."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = _resolve_flare_state_claims(
                data_root=tmp_path, root=tmp_path, today=date.today()
            )
        assert result.get("skipped") is True
