"""Tests for W3 Event Intelligence — scripts/backtest_event_priors.py.

Test plan (from design review):
1. PIT unit tests per loader (assert correct date field used).
2. Survivorship test: delisted ticker imputed as CAR=0, not silently dropped.
3. Null-print test: K<floor -> insufficient=True -> _prior_str never "" or a number.
4. Schema-compat test: old v1 JSON loads via _prior_for with new fields=None.
5. numpy-scalar json test: np.int64 values round-trip cleanly (qledger hazard).
6. Synapse/doc: artifact count matches (covered by test_signal_bus_doc.py).
7. Staging test: every persisted path under data/special_situations/ (B3 guard).
8. is_context_only test: every emitted prior JSON has is_context_only=True.
9. DSR ledger test: declared N >= number of (type x anchor x horizon) cells computed.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Locate repo root and import modules under test
# ---------------------------------------------------------------------------
_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import scripts.backtest_event_priors as bep
from scripts.build_special_situations import _prior_str
from engine.special_situations import _prior_for


# ---------------------------------------------------------------------------
# 1. PIT unit tests per loader
# ---------------------------------------------------------------------------

class TestPITAnchors:
    """Assert each loader uses the correct public-knowledge date field."""

    def test_clinicaltrials_phase3_anchor_is_first_post(self, tmp_path, monkeypatch):
        """Phase-3 start events must use first_post, not last_update."""
        ct = pd.DataFrame([{
            "ticker": "MRNA",
            "nct": "NCT99999",
            "title": "Test Phase 3 Study",
            "status": "RECRUITING",
            "phases": "PHASE3",
            "first_post": "2024-03-15",
            "last_update": "2025-01-01",
            "why_stopped": None,
            "is_halt": False,
            "_first_seen": "2024-03-15",
        }])
        ct_parquet = tmp_path / "trials.parquet"
        ct.to_parquet(ct_parquet)
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "clinicaltrials").mkdir(exist_ok=True)
            ct.to_parquet(tmp_path / "clinicaltrials" / "trials.parquet")
            events = bep.load_clinicaltrials()
        phase3_events = [(t, d, s) for t, d, s in events if s == "phase3_start"]
        assert any(e[0] == "MRNA" and e[1] == "2024-03-15" for e in phase3_events), (
            f"Phase-3 start should anchor to first_post='2024-03-15', got: {phase3_events}"
        )
        # must NOT use last_update for phase3_start
        assert not any(e[0] == "MRNA" and e[1] == "2025-01-01" for e in phase3_events), (
            "Phase-3 start incorrectly using last_update instead of first_post"
        )

    def test_clinicaltrials_halt_events_excluded_m5(self, tmp_path):
        """M5 fix: halt events must NOT be emitted by load_clinicaltrials().

        last_update is the latest administrative record touch on ClinicalTrials.gov,
        NOT the halt-disclosure date. Emitting halt events with this anchor produces
        mis-aligned CAR windows. load_clinicaltrials() must return no halt-subtype
        events until a real halt-disclosure date is available.
        """
        ct = pd.DataFrame([{
            "ticker": "AGEN",
            "nct": "NCT88888",
            "title": "Halted Trial",
            "status": "TERMINATED",
            "phases": "PHASE3",
            "first_post": "2022-01-01",
            "last_update": "2024-06-30",
            "why_stopped": "Safety",
            "is_halt": True,
            "_first_seen": "2024-06-30",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "clinicaltrials").mkdir(exist_ok=True)
            ct.to_parquet(tmp_path / "clinicaltrials" / "trials.parquet")
            events = bep.load_clinicaltrials()
        halt_events = [(t, d, s) for t, d, s in events if s == "halt"]
        assert len(halt_events) == 0, (
            f"M5: halt events must not be emitted (last_update != disclosure date); "
            f"got: {halt_events}"
        )

    def test_openfda_anchor_is_status_date_yyyymmdd(self, tmp_path):
        """openfda status_date is YYYYMMDD format — must parse correctly."""
        fda = pd.DataFrame([{
            "ticker": "PFE",
            "sponsor": "PFIZER",
            "application_number": "NDA999",
            "submission_type": "SUPPL",
            "class_code": "EFFICACY",
            "status_date": "20240315",  # YYYYMMDD
            "kind": "approval",
            "drug_name": "TESTDRUG",
            "_first_seen": "2024-03-20",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "openfda").mkdir(exist_ok=True)
            fda.to_parquet(tmp_path / "openfda" / "approvals.parquet")
            events = bep.load_openfda()
        assert any(t == "PFE" and d == "2024-03-15" for t, d, s in events), (
            f"openfda should parse YYYYMMDD '20240315' -> '2024-03-15', got: {events}"
        )

    def test_sp_index_changes_anchor_is_announce_not_effective(self, tmp_path):
        """S&P index changes must use announce_date, NOT effective_date (M4 fix)."""
        sp = pd.DataFrame([{
            "ticker": "NVDA",
            "index": "sp500",
            "action": "addition",
            "effective_date": "2024-06-24",  # must NOT be used
            "announce_date": "2024-06-18",   # must be used (PIT)
            "company": "NVIDIA Corp",
            "announce_url": "https://example.com",
            "_seen": "2024-06-18",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "sp_index_changes").mkdir(exist_ok=True)
            sp.to_parquet(tmp_path / "sp_index_changes" / "changes.parquet")
            events = bep.load_sp_index_changes()
        assert any(t == "NVDA" and d == "2024-06-18" for t, d, s in events), (
            f"S&P changes should anchor to announce_date='2024-06-18', got: {events}"
        )
        assert not any(t == "NVDA" and d == "2024-06-24" for t, d, s in events), (
            "S&P changes incorrectly using effective_date instead of announce_date"
        )

    def test_ipo_lockup_uses_priced_date_plus_lockup_days(self, tmp_path):
        """IPO lockup expiry = priced_date + lockup_days from prospectus."""
        # lockup: RDDT priced 2024-03-21, lockup 180d -> expiry 2024-09-17
        lockups = pd.DataFrame(
            [{"cik": 123, "form": "424B4", "filing_date": "2024-03-21",
              "lockup_days": 180.0, "source": "424B4 prospectus", "as_of": "2024-03-25"}],
            index=pd.Index(["RDDT"], name="ticker")
        )
        cal = pd.DataFrame([{
            "ticker": "RDDT", "company": "Reddit Inc", "exchange": "NYSE",
            "status": "priced", "offer_price": 34.0, "range_low": 31.0,
            "range_high": 34.0, "range_mid": 32.5, "shares": 1e7,
            "offer_value_usd": 3.4e8, "priced_date": "2024-03-21",
            "expected_date": None, "filed_date": "2023-12-22", "withdraw_date": None,
            "is_spac": False, "as_of": "2024-03-25", "marketed_low": None, "marketed_high": None,
        }])
        cal.index = pd.Index(["deal-1"], name="deal_id")
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "ipo").mkdir(exist_ok=True)
            lockups.to_parquet(tmp_path / "ipo" / "lockups.parquet")
            cal.to_parquet(tmp_path / "ipo" / "calendar.parquet")
            events = bep.load_ipo_lockup()
        # 2024-03-21 + 180d = 2024-09-17
        expected_expiry = str((pd.Timestamp("2024-03-21") + pd.Timedelta(days=180)).date())
        assert any(t == "RDDT" and d == expected_expiry for t, d, s in events), (
            f"IPO lockup expiry should be {expected_expiry}, got events: {events}"
        )


# ---------------------------------------------------------------------------
# 2. Survivorship test
# ---------------------------------------------------------------------------

class TestSurvivorship:
    """Delisted/absent tickers must be imputed as CAR=0, not silently dropped."""

    def _make_closes(self) -> pd.DataFrame:
        dates = pd.bdate_range("2024-01-01", periods=100)
        return pd.DataFrame({"SPY": np.cumprod(1 + np.random.normal(0.0003, 0.01, len(dates)))},
                            index=dates)

    def test_absent_ticker_counted_in_n_imputed_zero(self):
        """A ticker not in the closes panel must increase n_imputed_zero, not be silently dropped."""
        closes = self._make_closes()
        spy = closes["SPY"]
        events = [
            ("SPY", pd.Timestamp("2024-03-01"), "test"),  # studiable (self-loop, but present)
            ("DELISTED_XYZ", pd.Timestamp("2024-03-01"), "test"),  # absent -> imputed
        ]
        result = bep.aggregate_episodes(
            [(t, ts) for t, ts, _ in events], closes, spy, h=20, event_type="test"
        )
        assert result.get("n_imputed_zero", 0) >= 1, (
            f"Absent ticker DELISTED_XYZ must be counted in n_imputed_zero, got: {result}"
        )

    def test_absent_ticker_not_dropped_from_n_count(self):
        """Total event count must include ALL tickers, not only studiable ones."""
        closes = self._make_closes()
        spy = closes["SPY"]
        events: list[tuple[str, pd.Timestamp]] = [
            ("DELISTED_A", pd.Timestamp("2024-03-01")),
            ("DELISTED_B", pd.Timestamp("2024-04-01")),
        ]
        result = bep.aggregate_episodes(events, closes, spy, h=20, event_type="test")
        # With both absent, n_imputed_zero should be 2, n_studiable=0
        assert result.get("n_imputed_zero", 0) == 2, (
            f"Both absent tickers should be in n_imputed_zero=2, got: {result}"
        )
        assert result.get("n_studiable", -1) == 0, (
            f"n_studiable should be 0 when no tickers are in panel, got: {result}"
        )


# ---------------------------------------------------------------------------
# 3. Null-print test (m1 fix)
# ---------------------------------------------------------------------------

class TestNullPrint:
    """Sub-floor priors must display 'insufficient history (n=K)', never '' or a number."""

    def test_insufficient_prior_prints_not_empty(self):
        """_prior_str({'insufficient': True, 'n': 3}) must return a non-empty string."""
        p = {"insufficient": True, "n": 3, "scope": "test"}
        result = _prior_str(p)
        assert result != "", "_prior_str must not return '' for insufficient prior"
        assert "insufficient" in result.lower() or "n=3" in result, (
            f"Expected 'insufficient history' in string, got: {result!r}"
        )

    def test_insufficient_prior_never_a_number(self):
        """_prior_str for insufficient prior must not look like a number."""
        p = {"insufficient": True, "n": 7, "scope": "clinicaltrials"}
        result = _prior_str(p)
        # must not start with a digit or sign followed only by digits/decimals
        import re
        assert not re.match(r'^[+\-]?\d+\.?\d*%?\s*win', result), (
            f"_prior_str for insufficient prior looks like a numeric win-rate: {result!r}"
        )

    def test_none_prior_returns_empty(self):
        """_prior_str(None) should return '' (no prior at all — display suppressed)."""
        assert _prior_str(None) == ""

    def test_sufficient_prior_returns_hist_string(self):
        """A prior with n >= floor and win_20d_pct should render normally."""
        p = {"n": 12, "win_20d_pct": 65.0, "med_ret_20d_pct": 3.2, "scope": "test"}
        result = _prior_str(p)
        assert result.startswith("hist"), f"Expected 'hist ...' prefix, got: {result!r}"
        assert "65%" in result or "65" in result, f"Expected win rate in string: {result!r}"


# ---------------------------------------------------------------------------
# 4. Schema-compat test (M3 fix — v1 JSON loads with new fields = None)
# ---------------------------------------------------------------------------

class TestSchemaCompat:
    """Old v1 prior JSON must load without crash; new fields default to None."""

    def _old_v1_prior(self):
        return {
            "category": "Acquisitions",
            "stage": "announced",
            "n": 20,
            "win_20d_pct": 58.0,
            "med_ret_20d_pct": 2.1,
            "med_ret_60d_pct": 4.5,
            # v2 fields NOT present in old schema
        }

    def test_prior_for_with_old_schema_no_crash(self):
        """_prior_for must tolerate old-schema dicts (v2 fields absent -> None)."""
        p = self._old_v1_prior()
        stage_p = {("Acquisitions", "announced"): p}
        cat_p = {}
        result = _prior_for("Acquisitions", "announced", stage_p, cat_p)
        assert result is not None, "Old-schema prior should not return None for sufficient n"
        # New fields must be None, not raise KeyError
        assert result.get("max_dd_20d_pct") is None
        assert result.get("pre_drift_pct") is None
        assert result.get("hac_t_20d") is None
        assert result.get("ci90_20d") is None

    def test_prior_str_with_v2_fields_renders_drawdown(self):
        """_prior_str should include drawdown and pre-drift when v2 fields present."""
        p = {
            "n": 15, "win_20d_pct": 60.0, "med_ret_20d_pct": 2.5,
            "max_dd_20d_pct": -4.5, "pre_drift_pct": 1.2, "scope": "Acquisitions"
        }
        result = _prior_str(p)
        assert "dd" in result, f"Expected 'dd' in v2 prior string, got: {result!r}"
        assert "pre" in result, f"Expected 'pre' in v2 prior string, got: {result!r}"


# ---------------------------------------------------------------------------
# 5. numpy-scalar json test (qledger hazard guard)
# ---------------------------------------------------------------------------

class TestNumpyScalarJson:
    """_num() must convert numpy scalars to Python natives for json.dumps safety."""

    def test_numpy_int64_via_num(self):
        v = np.int64(42)
        result = bep._num(v)
        assert isinstance(result, float), f"Expected float, got {type(result)}: {result}"
        assert result == 42.0

    def test_numpy_float32_via_num(self):
        v = np.float32(3.14)
        result = bep._num(v)
        assert isinstance(result, float), f"Expected float, got {type(result)}: {result}"

    def test_nan_via_num_is_none(self):
        assert bep._num(float("nan")) is None
        assert bep._num(np.nan) is None

    def test_inf_via_num_is_none(self):
        assert bep._num(float("inf")) is None
        assert bep._num(float("-inf")) is None

    def test_none_via_num_is_none(self):
        assert bep._num(None) is None

    def test_prior_dict_is_json_serializable(self):
        """A prior dict with numpy scalars must survive json.dumps via _num."""
        data = {
            "n_studiable": np.int64(10),
            "med_excess_pct": np.float64(2.5),
            "hac_t": np.float32(1.9),
        }
        cleaned = {k: bep._num(v) for k, v in data.items()}
        # must not raise
        serialized = json.dumps(cleaned)
        loaded = json.loads(serialized)
        assert loaded["n_studiable"] == 10.0
        assert abs(loaded["med_excess_pct"] - 2.5) < 0.001


# ---------------------------------------------------------------------------
# 7. Staging test (B3 guard: all written paths under data/special_situations/)
# ---------------------------------------------------------------------------

class TestStagingPaths:
    """Every persisted event-prior JSON must live under data/special_situations/
    so the workflow 'git add data/special_situations' covers it (B3 fix)."""

    def test_out_dir_is_under_special_situations(self):
        out_dir = bep._OUT_DIR
        # must be a subdirectory of data/special_situations
        parts = out_dir.parts
        assert "special_situations" in parts, (
            f"_OUT_DIR must be under data/special_situations/, got: {out_dir}"
        )
        # and must be the event_priors subdirectory
        assert out_dir.name == "event_priors", (
            f"_OUT_DIR should be named 'event_priors', got: {out_dir.name}"
        )


# ---------------------------------------------------------------------------
# 8. is_context_only test
# ---------------------------------------------------------------------------

class TestIsContextOnly:
    """Every emitted prior JSON must carry is_context_only=True."""

    def test_compute_prior_has_is_context_only(self):
        """compute_prior_for_type must set is_context_only=True."""
        result = bep.compute_prior_for_type("test", [], pd.DataFrame(), None)
        assert result.get("is_context_only") is True, (
            f"is_context_only must be True, got: {result.get('is_context_only')}"
        )

    def test_gov_contract_stub_has_is_context_only(self):
        result = bep._gov_contract_stub()
        assert result.get("is_context_only") is True

    def test_null_reason_prior_has_is_context_only(self):
        result = bep.compute_prior_for_type(
            "test_null", [], pd.DataFrame(), None, null_reason="No data."
        )
        assert result.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 9. DSR ledger test: declared N >= actual trial count
# ---------------------------------------------------------------------------

class TestDSRLedger:
    """N_TRIALS must be >= number of (event_type x anchor x horizon) cells actually tested."""

    def test_declared_n_exceeds_max_possible_trials(self):
        """Active event-types × 3 horizons must be covered by N_TRIALS budget.

        Active types (3): clinicaltrials (phase3_start only), openfda, ipo_lockup.
        Gated types (null-print, 0 DSR trials): sp_index_changes (K<floor),
          earnings (M4: asof_date=period_end+60d placeholder), gov_contract (M1).
        Halt subtype excluded from clinicaltrials (M5: last_update not disclosure date).
        N_TRIALS=20 is a declared budget that must be >= the active trial count.
        """
        # 3 active types × 3 horizons = 9 minimum; N_TRIALS=20 is padded for future
        active_types = 3  # clinicaltrials(phase3_start), openfda, ipo_lockup
        n_horizons = len(bep.HORIZONS)
        min_trials = active_types * n_horizons
        assert bep.N_TRIALS >= min_trials, (
            f"N_TRIALS={bep.N_TRIALS} must be >= {min_trials} "
            f"({active_types} types × {n_horizons} horizons)"
        )

    def test_n_trials_is_positive_int(self):
        assert isinstance(bep.N_TRIALS, int) and bep.N_TRIALS > 0

    def test_event_floor_matches_hincl(self):
        """EVENT_FLOOR must match hincl's K>=8 minimum for NW t-stat."""
        assert bep.EVENT_FLOOR == 8, (
            f"EVENT_FLOOR should be 8 (matches hincl NW K>=8), got {bep.EVENT_FLOOR}"
        )


# ---------------------------------------------------------------------------
# 10. M4 / M5 gate tests
# ---------------------------------------------------------------------------

def _synthetic_8k_panel(tmp_path, rows):
    """Write an earnings_8k_dates.parquet with `rows` = list of dicts."""
    import pandas as pd
    (tmp_path / "edgar").mkdir(exist_ok=True, parents=True)
    pd.DataFrame(rows).to_parquet(tmp_path / "edgar" / "earnings_8k_dates.parquet")


def _flat_closes(dates, tickers, start=100.0):
    """Close panel with a deterministic 0.1%/day ramp so vol60 is finite and > 0."""
    import numpy as np
    import pandas as pd
    n = len(dates)
    data = {}
    for k, t in enumerate(tickers):
        # small alternating wiggle keeps rolling std strictly positive
        wig = np.where(np.arange(n) % 2 == 0, 1.0, 0.995)
        data[t] = start * np.cumprod(np.full(n, 1.001)) * wig
    return pd.DataFrame(data, index=pd.DatetimeIndex(dates))


class TestM4EarningsAnchor:
    """M4 RE-ENABLED: earnings priors are anchored on real Item-2.02 acceptance times.

    These tests pin the NEW contract. The old test asserted `load_earnings_events()`
    returns [] unconditionally; that gate named its own unblock ("EDGAR 8-K filing
    timestamps"), which data/edgar/earnings_8k_dates.parquet now supplies. The gate on
    eps_quarterly.asof_date is NOT relaxed — see test_asof_date_is_never_read.
    """

    def test_absent_store_still_null_prints(self, tmp_path):
        """No 8-K store -> [] -> the caller emits an honest null-print (unchanged law)."""
        closes = _flat_closes(pd.bdate_range("2020-01-01", periods=200), ["AAPL"])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            assert bep.load_earnings_events(closes, None) == []

    def test_asof_date_is_never_read(self, tmp_path):
        """The synthetic eps_quarterly.asof_date must remain unused as an anchor.

        A period_end+60d placeholder present on disk must not produce a single event.
        """
        import pandas as pd
        (tmp_path / "edgar").mkdir(exist_ok=True, parents=True)
        pd.DataFrame([{"ticker": "AAPL", "asof_date": "2020-03-31",
                       "period_end": "2020-01-31", "eps_q": 1.5}]).to_parquet(
            tmp_path / "edgar" / "eps_quarterly.parquet")
        closes = _flat_closes(pd.bdate_range("2020-01-01", periods=200), ["AAPL"])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            # only eps_quarterly on disk, no 8-K store
            assert bep.load_earnings_events(closes, None) == []

    def test_afterhours_filing_prices_on_the_next_session(self):
        """A 20:15 UTC (16:15 ET) acceptance is after the close -> day0 = NEXT session."""
        cal = pd.DatetimeIndex(["2024-05-01", "2024-05-02", "2024-05-03"])
        d0 = bep.earnings_day0(pd.Timestamp("2024-05-01"),
                               "2024-05-01T20:15:00.000Z", cal)
        assert d0 == pd.Timestamp("2024-05-02"), (
            "after-the-close 8-K must be priced by the next session, not the filing day")
        assert bep.earnings_session_rule("2024-05-01T20:15:00.000Z") == "afterhours"

    def test_premarket_filing_prices_same_session(self):
        """An 11:00 UTC (07:00 ET) acceptance is pre-open -> day0 = the filing session."""
        cal = pd.DatetimeIndex(["2024-05-01", "2024-05-02", "2024-05-03"])
        d0 = bep.earnings_day0(pd.Timestamp("2024-05-01"),
                               "2024-05-01T11:00:00.000Z", cal)
        assert d0 == pd.Timestamp("2024-05-01")
        assert bep.earnings_session_rule("2024-05-01T11:00:00.000Z") == "premarket"

    def test_intraday_filing_is_tagged_not_silently_pooled(self):
        """A 14:00 ET filing is only partially priced that day and must be separable."""
        assert bep.earnings_session_rule("2024-05-01T18:00:00.000Z") == "intraday"

    def test_unusable_acceptance_timestamp_drops_the_event(self):
        cal = pd.DatetimeIndex(["2024-05-01", "2024-05-02"])
        assert bep.earnings_day0(pd.Timestamp("2024-05-01"), "", cal) is None
        assert bep.earnings_day0(pd.Timestamp("2024-05-01"), "not-a-date", cal) is None
        assert bep.earnings_session_rule("") is None

    def test_reaction_bands_are_half_open_and_ordered(self):
        """Bands are left-closed/right-open [lo, hi) so a boundary value is unambiguous."""
        assert bep.reaction_band(3.0) == "reaction_strong_up"
        assert bep.reaction_band(2.0) == "reaction_strong_up"     # lower edge included
        assert bep.reaction_band(1.9) == "reaction_up"
        assert bep.reaction_band(0.5) == "reaction_up"            # lower edge included
        assert bep.reaction_band(0.49) == "reaction_flat"
        assert bep.reaction_band(0.0) == "reaction_flat"
        assert bep.reaction_band(-0.5) == "reaction_flat"         # [-0.5, 0.5) -> flat
        assert bep.reaction_band(-0.51) == "reaction_down"
        assert bep.reaction_band(-2.0) == "reaction_down"         # [-2.0, -0.5) -> down
        assert bep.reaction_band(-2.01) == "reaction_strong_down"
        assert bep.reaction_band(-9.0) == "reaction_strong_down"
        assert bep.reaction_band(float("nan")) is None
        assert bep.reaction_band(None) is None

    def test_reaction_bands_partition_the_line(self):
        """No gaps, no overlaps: every finite value gets exactly one band."""
        import numpy as np
        for z in np.linspace(-25, 25, 2001):
            assert bep.reaction_band(float(z)) is not None, f"{z} fell through every band"
        names = [n for n, _, _ in bep._REACTION_BANDS]
        assert len(names) == len(set(names)), "duplicate band name"

    def test_subtype_conditioning_is_known_at_day0_close(self, tmp_path):
        """NO LOOK-AHEAD: r0z uses only day0 and earlier, and CAR starts at day0 close.

        Mutating prices strictly AFTER day0 must not change the assigned subtype. If it
        did, the band would be leaking the very return the prior measures.
        """
        import numpy as np
        dates = pd.bdate_range("2020-01-01", periods=200)
        closes = _flat_closes(dates, ["AAPL", "SPY"])
        day0 = dates[120]
        _synthetic_8k_panel(tmp_path, [{
            "ticker": "AAPL", "cik": 1,
            "filing_date": str(day0.date()),
            "acceptance_datetime": f"{day0.date()}T11:00:00.000Z",
            "items": "2.02",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            base = bep.load_earnings_events(closes, closes["SPY"])
            future = closes.copy()
            future.iloc[121:, future.columns.get_loc("AAPL")] *= 3.0
            after = bep.load_earnings_events(future, future["SPY"])
        assert base and after, "fixture must produce an event on both runs"
        assert base[0] == after[0], (
            f"subtype/date changed when only POST-day0 prices moved — look-ahead leak: "
            f"{base[0]} -> {after[0]}")

    def test_events_carry_day0_not_raw_filing_date(self, tmp_path):
        """An after-hours event must be emitted at day0, never at the filing date."""
        dates = pd.bdate_range("2020-01-01", periods=200)
        closes = _flat_closes(dates, ["AAPL", "SPY"])
        fd = dates[120]
        _synthetic_8k_panel(tmp_path, [{
            "ticker": "AAPL", "cik": 1,
            "filing_date": str(fd.date()),
            "acceptance_datetime": f"{fd.date()}T21:05:00.000Z",   # 17:05 ET
            "items": "2.02",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            ev = bep.load_earnings_events(closes, closes["SPY"])
        assert ev, "after-hours event should still be emitted"
        assert ev[0][1] == str(dates[121].date()), (
            f"after-hours filing must be anchored on the NEXT session; got {ev[0][1]}")

    def test_unpriced_ticker_is_skipped_not_crashed(self, tmp_path):
        dates = pd.bdate_range("2020-01-01", periods=200)
        closes = _flat_closes(dates, ["AAPL", "SPY"])
        _synthetic_8k_panel(tmp_path, [{
            "ticker": "ZZZZ", "cik": 9,
            "filing_date": str(dates[120].date()),
            "acceptance_datetime": f"{dates[120].date()}T11:00:00.000Z",
            "items": "2.02",
        }])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            assert bep.load_earnings_events(closes, closes["SPY"]) == []


class TestDeepClosesSplice:
    """_deep_closes must EXTEND history without altering any existing breadth value."""

    def test_breadth_values_win_on_the_overlap(self, tmp_path):
        """A splice that changed an overlapping cell would manufacture a fake return."""
        import numpy as np
        dates = pd.bdate_range("2024-01-01", periods=30)
        breadth = _flat_closes(dates, ["AAPL"])
        (tmp_path / "stocks").mkdir(parents=True, exist_ok=True)
        deep_dates = pd.bdate_range("2020-01-01", periods=1100)
        deep = _flat_closes(deep_dates, ["AAPL"], start=7.0)   # deliberately different level
        deep[["close"]] = deep[["AAPL"]]
        deep[["close"]].to_parquet(tmp_path / "stocks" / "AAPL.parquet")
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            out = bep._deep_closes(breadth)
        assert out.index.min() < dates.min(), "history must extend backwards"
        overlap = breadth.index.intersection(out.index)
        assert np.allclose(out.loc[overlap, "AAPL"].values,
                           breadth.loc[overlap, "AAPL"].values), (
            "breadth values must be preserved byte-for-byte on the overlap")

    def test_absent_deep_store_returns_input_unchanged(self, tmp_path):
        dates = pd.bdate_range("2024-01-01", periods=10)
        breadth = _flat_closes(dates, ["AAPL"])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            out = bep._deep_closes(breadth)
        assert out.equals(breadth)


class TestM4M5Gates:
    """Halt (M5) must null-print until a real disclosure date is wired."""

    def test_compute_prior_earnings_null_reason_insufficient(self):
        """M4 fix: earnings prior must carry insufficient=True when no events."""
        import pandas as pd
        result = bep.compute_prior_for_type(
            "earnings", [], pd.DataFrame(), None,
            null_reason="asof_date is period_end+60d placeholder, not real PIT.",
        )
        assert result.get("insufficient") is True
        assert result.get("is_context_only") is True
        assert result.get("null_reason") is not None

    def test_load_clinicaltrials_no_halt_subtype(self, tmp_path):
        """M5 fix: even with is_halt=True rows, no halt-subtype events are emitted."""
        import pandas as pd
        ct = pd.DataFrame([
            {
                "ticker": "AGEN",
                "nct": "NCT11111",
                "title": "Phase 3 Halted",
                "status": "TERMINATED",
                "phases": "PHASE3",
                "first_post": "2023-01-01",
                "last_update": "2024-05-01",
                "why_stopped": "Safety concern",
                "is_halt": True,
                "_first_seen": "2024-05-01",
            },
            {
                "ticker": "MRNA",
                "nct": "NCT22222",
                "title": "Phase 3 Active",
                "status": "RECRUITING",
                "phases": "PHASE3",
                "first_post": "2023-06-15",
                "last_update": "2024-01-01",
                "why_stopped": None,
                "is_halt": False,
                "_first_seen": "2023-06-15",
            },
        ])
        with patch.object(bep.config, "data_dir", return_value=tmp_path):
            (tmp_path / "clinicaltrials").mkdir(exist_ok=True)
            ct.to_parquet(tmp_path / "clinicaltrials" / "trials.parquet")
            events = bep.load_clinicaltrials()
        halt_events = [e for e in events if e[2] == "halt"]
        phase3_events = [e for e in events if e[2] == "phase3_start"]
        assert len(halt_events) == 0, (
            f"M5: halt subtype must not be emitted; got: {halt_events}"
        )
        # Phase-3 start for non-halted MRNA should still be emitted
        assert any(e[0] == "MRNA" for e in phase3_events), (
            f"Phase-3 start for non-halted trial should still emit; got: {phase3_events}"
        )
