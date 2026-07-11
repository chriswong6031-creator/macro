"""tests/test_news_event_ledger.py — W4: PIT event ledger + calibration tests.

Coverage:
  1. keep-first: double-ingest → first_seen_utc unchanged, no duplicate rows
  2. grading math vs hand-computed fixture prices (SPY-relative; bullish/bearish sign)
  3. Wilson interval vs hand-computed known value
  4. Contract-shape validation of the emitted artifact
  5. Numpy-native-cast: json.dumps succeeds with NO default= fallback on a
     calibration dict built from a real parquet round-trip
  6. Degrade paths: missing parquet, missing price data → valid empty artifact, no exception
  7. Full news suite import smoke-tests
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_headline(title="Nvidia launches new AI chip", domain="reuters.com",
                   event_type="product_launch", direction="bullish",
                   tickers=None, seendate="2026-01-02T09:00:00+00:00",
                   reason=None) -> dict:
    """Build a minimal headline dict suitable for event ledger tests."""
    h: dict = {
        "title": title,
        "domain": domain,
        "seendate": seendate,
        "source_tier": 1,
        "theme": "Technology",
        "novelty_z": 1.2,
        "event": {
            "event_type": event_type,
            "direction": direction,
        },
    }
    if tickers is not None:
        h["tickers"] = tickers
    if reason is not None:
        h["reason"] = reason
    return h


def _write_parquet_prices(tmpdir: Path, prices: dict[str, dict[str, float]]) -> None:
    """Write per-ticker price parquets into data/yahoo/<ticker>.parquet.
    prices = {ticker: {"2026-01-02": 100.0, "2026-01-09": 110.0, ...}}
    """
    import pandas as pd
    yahoo_dir = tmpdir / "data" / "yahoo"
    yahoo_dir.mkdir(parents=True, exist_ok=True)
    for ticker, series_dict in prices.items():
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in sorted(series_dict.keys())], tz="UTC")
        vals = [series_dict[d] for d in sorted(series_dict.keys())]
        df = pd.DataFrame({"close": vals}, index=idx)
        df.to_parquet(yahoo_dir / f"{ticker}.parquet")


# --------------------------------------------------------------------------- #
# 1. keep-first: double-ingest
# --------------------------------------------------------------------------- #
class TestKeepFirst:
    def test_double_ingest_no_dup_rows(self, tmp_path):
        from engine.news_event_ledger import persist_kept_events, load_event_log

        h = _make_headline(tickers=["NVDA"])
        # First ingest
        n1 = persist_kept_events([h], asof_utc="2026-01-02T10:00:00+00:00", root=tmp_path)
        assert n1 == 1

        # Second ingest — same headline, different asof_utc
        n2 = persist_kept_events([h], asof_utc="2026-01-03T10:00:00+00:00", root=tmp_path)
        assert n2 == 0, "Second ingest of same event_id must return 0 new rows"

        df = load_event_log(tmp_path)
        assert df is not None
        assert len(df) == 1, "Must have exactly 1 row after double-ingest"

    def test_first_seen_utc_unchanged(self, tmp_path):
        from engine.news_event_ledger import persist_kept_events, load_event_log

        h = _make_headline(tickers=["MSFT"])
        first_ts = "2026-01-02T08:00:00+00:00"
        persist_kept_events([h], asof_utc=first_ts, root=tmp_path)
        persist_kept_events([h], asof_utc="2026-01-05T08:00:00+00:00", root=tmp_path)

        df = load_event_log(tmp_path)
        assert str(df.iloc[0]["first_seen_utc"]) == first_ts, \
            "first_seen_utc must not be overwritten by re-ingest"

    def test_events_without_event_type_skipped(self, tmp_path):
        from engine.news_event_ledger import persist_kept_events, load_event_log

        h_no_event = {"title": "Random headline", "domain": "bbc.com", "seendate": "2026-01-02"}
        h_with_event = _make_headline(tickers=["AAPL"])
        n = persist_kept_events([h_no_event, h_with_event],
                                asof_utc="2026-01-02T10:00:00+00:00", root=tmp_path)
        assert n == 1, "Only headline with event_type should be persisted"
        df = load_event_log(tmp_path)
        assert len(df) == 1


# --------------------------------------------------------------------------- #
# 1b. source_tier string regression — was crashing int('stock_wire')
# --------------------------------------------------------------------------- #
class TestSourceTierString:
    """Regression: persist_kept_events must not crash when source_tier is a string
    label (e.g. 'stock_wire', 'tier1', 'quality', 'official').  Before the fix,
    `int('stock_wire')` raised ValueError inside the degrade wrapper and the
    event_log parquet was NEVER written.
    """

    def test_stock_wire_persists_rows(self, tmp_path):
        """A headline with source_tier='stock_wire' must persist and create the parquet."""
        from engine.news_event_ledger import persist_kept_events, load_event_log

        # Realistic headline shape matching what the news engines emit
        h = {
            "title": "Apple reports record iPhone sales in Q4",
            "domain": "reuters.com",
            "seendate": "2026-07-10T09:00:00+00:00",
            "source_tier": "stock_wire",   # string label — the historic crash vector
            "theme": "Technology",
            "novelty_z": 0.8,
            "tickers": ["AAPL"],
            "event": {
                "event_type": "earnings_release",
                "direction": "bullish",
            },
        }
        n = persist_kept_events([h], asof_utc="2026-07-10T12:00:00+00:00", root=tmp_path)
        assert n == 1, f"Expected 1 row persisted, got {n}"

        parquet_path = tmp_path / "data" / "news" / "event_log.parquet"
        assert parquet_path.exists(), "event_log.parquet must be created"

        df = load_event_log(tmp_path)
        assert df is not None and len(df) == 1
        assert str(df.iloc[0]["source_tier"]) == "stock_wire"

    def test_other_string_tier_labels(self, tmp_path):
        """All string tier labels ('tier1', 'quality', 'official') must persist cleanly."""
        from engine.news_event_ledger import persist_kept_events, load_event_log

        tiers = ["tier1", "quality", "official"]
        headlines = [
            {
                "title": f"Headline for tier {tier}",
                "domain": f"{tier}.com",
                "seendate": f"2026-07-10T0{i+9}:00:00+00:00",
                "source_tier": tier,
                "event": {"event_type": "macro_release", "direction": "informational"},
            }
            for i, tier in enumerate(tiers)
        ]
        n = persist_kept_events(headlines, asof_utc="2026-07-10T12:00:00+00:00", root=tmp_path)
        assert n == 3, f"Expected 3 rows persisted, got {n}"
        df = load_event_log(tmp_path)
        assert df is not None and len(df) == 3

    def test_missing_source_tier_falls_back_to_empty_string(self, tmp_path):
        """Headlines with no source_tier at all should persist with source_tier=''."""
        from engine.news_event_ledger import persist_kept_events, load_event_log

        h = _make_headline(tickers=["MSFT"])
        h.pop("source_tier", None)   # ensure it's absent
        n = persist_kept_events([h], asof_utc="2026-07-10T12:00:00+00:00", root=tmp_path)
        assert n == 1
        df = load_event_log(tmp_path)
        assert str(df.iloc[0]["source_tier"]) == ""


# --------------------------------------------------------------------------- #
# 2. grading math vs hand-computed fixture prices
# --------------------------------------------------------------------------- #
class TestGradingMath:
    """Hand-computed expected values to verify the grading arithmetic."""

    def _build_fixture_prices(self, tmpdir: Path) -> dict:
        """Build SPY + NVDA price series covering both 5d and 21d horizons.

        Setup:
          entry_date = 2026-01-02
          fill_ts = first close STRICTLY AFTER 2026-01-02 = 2026-01-05

          5d horizon → exit ≤ 2026-01-05 + 5d = 2026-01-10
            last bar ≤ 2026-01-10: NVDA=108.0 (2026-01-09), SPY=402.0 (2026-01-09)
            NVDA 5d ret: 108/100-1 = 0.08
            SPY  5d ret: 402/400-1 = 0.005
            SPY-relative 5d: 0.08 - 0.005 = 0.075

          21d horizon → exit ≤ 2026-01-05 + 21d = 2026-01-26
            last bar ≤ 2026-01-26: NVDA=115.0 (2026-01-26), SPY=404.0 (2026-01-26)
            NVDA 21d ret: 115/100-1 = 0.15
            SPY  21d ret: 404/400-1 = 0.01
            SPY-relative 21d: 0.15 - 0.01 = 0.14
        """
        prices = {
            "NVDA": {
                "2026-01-05": 100.0,
                "2026-01-09": 108.0,
                "2026-01-12": 112.0,
                "2026-01-26": 115.0,
            },
            "SPY": {
                "2026-01-05": 400.0,
                "2026-01-09": 402.0,
                "2026-01-12": 403.0,
                "2026-01-26": 404.0,
            },
        }
        _write_parquet_prices(tmpdir, prices)
        return prices

    def test_fwd_ret_relative_5d(self, tmp_path):
        from scripts.grade_news_events import _fwd_ret_relative
        self._build_fixture_prices(tmp_path)
        r5 = _fwd_ret_relative("NVDA", "SPY", tmp_path, "2026-01-02", 5)
        # NVDA fill=2026-01-05 @ 100; exit <= 2026-01-10 → 2026-01-09 @ 108
        # SPY  fill=2026-01-05 @ 400; exit <= 2026-01-10 → 2026-01-09 @ 402
        expected = round(108/100 - 1 - (402/400 - 1), 6)  # 0.08 - 0.005 = 0.075
        assert r5 is not None
        assert abs(r5 - expected) < 1e-5, f"5d relative return {r5} != {expected}"

    def test_fwd_ret_relative_21d(self, tmp_path):
        from scripts.grade_news_events import _fwd_ret_relative
        self._build_fixture_prices(tmp_path)
        r21 = _fwd_ret_relative("NVDA", "SPY", tmp_path, "2026-01-02", 21)
        # exit ≤ 2026-01-05 + 21d = 2026-01-26 → 2026-01-12 is the last bar
        expected = round(115/100 - 1 - (404/400 - 1), 6)  # 0.15 - 0.01 = 0.14
        assert r21 is not None
        assert abs(r21 - expected) < 1e-5, f"21d relative return {r21} != {expected}"

    def test_bullish_hit_when_positive(self, tmp_path):
        from scripts.grade_news_events import _fwd_ret_relative
        self._build_fixture_prices(tmp_path)
        r5 = _fwd_ret_relative("NVDA", "SPY", tmp_path, "2026-01-02", 5)
        assert r5 > 0, "NVDA outperformed SPY → bullish event should count as hit"

    def test_bearish_hit_sign_convention(self, tmp_path):
        """Bearish: negative SPY-relative return counts as a hit.

        entry_date = 2026-01-02
        fill_ts = 2026-01-05 (first bar AFTER 2026-01-02)
        5d exit ≤ 2026-01-10 → 2026-01-09
        BA:  92/100 - 1 = -0.08; SPY: 402/400 - 1 = 0.005; excess = -0.085 < 0 = hit
        """
        prices = {
            "BA": {
                "2026-01-05": 100.0,
                "2026-01-09": 92.0,   # -8%
                "2026-01-12": 90.0,   # ensure series extends past exit
            },
            "SPY": {
                "2026-01-05": 400.0,
                "2026-01-09": 402.0,  # +0.5%
                "2026-01-12": 403.0,
            },
        }
        _write_parquet_prices(tmp_path, prices)
        from scripts.grade_news_events import _fwd_ret_relative
        r5 = _fwd_ret_relative("BA", "SPY", tmp_path, "2026-01-02", 5)
        # BA: 92/100 - 1 = -0.08; SPY: 402/400 - 1 = 0.005; excess = -0.085
        assert r5 is not None
        assert r5 < 0, "bearish event should have negative relative return = hit"

    def test_not_matured_returns_none(self, tmp_path):
        """When exit day not covered yet, return None (not matured)."""
        prices = {
            "AAPL": {"2026-01-05": 170.0},   # only one bar — exit not covered
            "SPY":  {"2026-01-05": 400.0},
        }
        _write_parquet_prices(tmp_path, prices)
        from scripts.grade_news_events import _fwd_ret_relative
        r5 = _fwd_ret_relative("AAPL", "SPY", tmp_path, "2026-01-02", 5)
        assert r5 is None, "Return must be None when exit day not in series"

    def test_missing_price_returns_none(self, tmp_path):
        from scripts.grade_news_events import _fwd_ret_relative
        # No price files in tmp_path at all
        r5 = _fwd_ret_relative("NONEXISTENT", "SPY", tmp_path, "2026-01-02", 5)
        assert r5 is None


# --------------------------------------------------------------------------- #
# 3. Wilson interval vs hand-computed known value
# --------------------------------------------------------------------------- #
class TestWilsonCI:
    def test_known_value(self):
        """Wilson 95% CI for 7 hits out of 10 trials.

        Manual: phat=0.7, z=1.96, z2=3.8416, denom=1+z2/10=1.38416
        centre = (0.7 + z2/20) / 1  = (0.7 + 0.19208) / 1.38416
        We compute the lower bound and compare to a high-precision reference.
        """
        from scripts.grade_news_events import _wilson_ci
        low, high = _wilson_ci(7, 10)
        assert low is not None and high is not None

        # Manual computation
        phat = 0.7
        z = 1.96
        z2 = z * z
        n = 10
        denom = 1.0 + z2 / n
        centre = phat + z2 / (2 * n)
        margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
        expected_low = (centre - margin) / denom
        expected_high = (centre + margin) / denom

        assert abs(low - round(expected_low, 6)) < 1e-5, f"wilson_low {low} != {expected_low}"
        assert abs(high - round(expected_high, 6)) < 1e-5, f"wilson_high {high} != {expected_high}"

    def test_zero_n_returns_none(self):
        from scripts.grade_news_events import _wilson_ci
        low, high = _wilson_ci(0, 0)
        assert low is None and high is None

    def test_all_hits(self):
        from scripts.grade_news_events import _wilson_ci
        low, high = _wilson_ci(10, 10)
        assert high is not None and high <= 1.0 and low > 0.5

    def test_no_hits(self):
        from scripts.grade_news_events import _wilson_ci
        low, high = _wilson_ci(0, 10)
        assert low is not None and low < 0.5


# --------------------------------------------------------------------------- #
# 4. Contract-shape validation
# --------------------------------------------------------------------------- #
class TestContractShape:
    """Verify the artifact always matches the pinned calibration.v1 contract."""

    def _assert_valid_contract(self, artifact: dict) -> None:
        assert artifact.get("schema") == "news_event_calibration.v1"
        assert artifact.get("is_context_only") is True
        assert isinstance(artifact.get("asof"), str) and len(artifact["asof"]) == 10
        assert isinstance(artifact.get("n_events_logged"), int)
        assert isinstance(artifact.get("n_events_graded"), int)
        assert isinstance(artifact.get("classes"), list)
        ra = artifact.get("reject_audit")
        assert isinstance(ra, dict)
        assert isinstance(ra.get("n_sampled"), int)
        assert isinstance(ra.get("n_graded"), int)
        assert isinstance(ra.get("classes"), list)

    def _assert_class_row_shape(self, c: dict) -> None:
        required = ["event_type", "direction", "n", "n_graded",
                    "hit_5d", "hit_21d", "avg_rel_5d", "avg_rel_21d",
                    "wilson_low_5d", "wilson_high_5d", "verdict"]
        for k in required:
            assert k in c, f"Class row missing key: {k}"
        assert c["verdict"] in ("insufficient", "candidate", "no_edge", "context_only")

    def test_empty_event_log_valid_artifact(self, tmp_path):
        from scripts.grade_news_events import build_calibration
        artifact = build_calibration(root=tmp_path)
        self._assert_valid_contract(artifact)
        assert artifact["n_events_logged"] == 0
        assert artifact["n_events_graded"] == 0
        assert artifact["classes"] == []

    def test_day1_all_insufficient(self, tmp_path):
        """On day 1, all events have n_graded < 30 → verdict = insufficient."""
        import pandas as pd
        from engine.news_event_ledger import persist_kept_events
        from scripts.grade_news_events import build_calibration

        h = _make_headline(tickers=["NVDA"])
        persist_kept_events([h], asof_utc="2026-01-02T10:00:00+00:00", root=tmp_path)
        artifact = build_calibration(root=tmp_path)

        self._assert_valid_contract(artifact)
        for c in artifact["classes"]:
            self._assert_class_row_shape(c)
            assert c["verdict"] == "insufficient", \
                f"Day-1 verdict must be insufficient, got {c['verdict']}"

    def test_verdict_candidate(self, tmp_path):
        """Simulate enough graded events so verdict=candidate for a bullish class."""
        from scripts.grade_news_events import _verdict
        # 28 graded, wilson_low > 0.50 only when hits/n is very high; use 30 graded, 27 hits
        low, high = __import__("scripts.grade_news_events", fromlist=["_wilson_ci"])._wilson_ci(27, 30)
        assert low is not None and low > 0.50
        verdict = _verdict(30, low, high)
        assert verdict == "candidate"

    def test_verdict_no_edge(self, tmp_path):
        from scripts.grade_news_events import _verdict, _wilson_ci
        # 30 graded, 3 hits → wilson_high < 0.50
        low, high = _wilson_ci(3, 30)
        assert high is not None and high < 0.50
        assert _verdict(30, low, high) == "no_edge"

    def test_verdict_insufficient_below_30(self):
        from scripts.grade_news_events import _verdict, _wilson_ci
        low, high = _wilson_ci(15, 29)
        assert _verdict(29, low, high) == "insufficient"

    def test_verdict_context_only(self):
        from scripts.grade_news_events import _verdict, _wilson_ci
        # 30 graded, 15 hits → CI straddles 0.50
        low, high = _wilson_ci(15, 30)
        assert _verdict(30, low, high) == "context_only"


# --------------------------------------------------------------------------- #
# 5. Numpy-native-cast test (the known prod bug pattern)
# --------------------------------------------------------------------------- #
class TestNumpyCast:
    """json.dumps on a calibration dict built from a parquet round-trip must
    succeed with NO default= fallback.  A numpy scalar that leaks through would
    raise TypeError — the same silent-zeroing bug that hit qledger claims.jsonl.
    """

    def test_json_dumps_no_default_after_parquet_round_trip(self, tmp_path):
        import numpy as np
        import pandas as pd
        from engine.news_event_ledger import persist_kept_events, load_event_log
        from scripts.grade_news_events import build_calibration

        # Write a headline with numpy-typed fields to simulate parquet round-trip
        h = _make_headline(tickers=["AAPL"])
        h["source_tier"] = np.int64(1)   # numpy scalar in the input
        h["novelty_z"] = np.float64(1.5)

        persist_kept_events([h], asof_utc="2026-01-02T10:00:00+00:00", root=tmp_path)
        df = load_event_log(tmp_path)
        assert df is not None

        # The artifact builder must cast everything back to native Python types
        artifact = build_calibration(root=tmp_path)

        # This MUST NOT need default= to succeed
        text = json.dumps(artifact)  # raises TypeError if any numpy scalar leaks
        parsed = json.loads(text)
        assert parsed["schema"] == "news_event_calibration.v1"
        assert isinstance(parsed["n_events_logged"], int)

    def test_cast_class_row_handles_numpy(self):
        """_cast_class_row must convert numpy scalars to native Python types."""
        import numpy as np
        from scripts.grade_news_events import _cast_class_row
        row = {
            "event_type": "guidance_cut",
            "direction": "bearish",
            "n": np.int64(5),
            "n_graded": np.int64(5),
            "hit_5d": np.float64(0.6),
            "hit_21d": np.float64(0.5),
            "avg_rel_5d": np.float64(-0.02),
            "avg_rel_21d": np.float64(-0.03),
            "wilson_low_5d": np.float64(0.23),
            "wilson_high_5d": np.float64(0.88),
            "verdict": "insufficient",
        }
        cast = _cast_class_row(row)
        text = json.dumps(cast)  # must not raise
        parsed = json.loads(text)
        assert isinstance(parsed["n"], int)
        assert isinstance(parsed["hit_5d"], float)

    def test_cast_reject_audit_handles_numpy(self):
        """_cast_reject_audit must also convert numpy scalars."""
        import numpy as np
        from scripts.grade_news_events import _cast_reject_audit
        ra = {
            "n_sampled": np.int64(50),
            "n_graded": np.int64(10),
            "classes": [
                {"reason": "stock_pick_roundup",
                 "n_graded": np.int64(10),
                 "avg_rel_21d": np.float64(0.005),
                 "note": "test"},
            ],
        }
        cast = _cast_reject_audit(ra)
        text = json.dumps(cast)  # must not raise
        parsed = json.loads(text)
        assert isinstance(parsed["n_sampled"], int)
        assert isinstance(parsed["classes"][0]["n_graded"], int)


# --------------------------------------------------------------------------- #
# 6. Degrade paths
# --------------------------------------------------------------------------- #
class TestDegradePaths:
    def test_missing_parquet_returns_valid_empty_artifact(self, tmp_path):
        """When event_log.parquet is absent, build_calibration returns valid empty artifact."""
        from scripts.grade_news_events import build_calibration
        artifact = build_calibration(root=tmp_path)
        # Must be contract-valid even with no data
        assert artifact["schema"] == "news_event_calibration.v1"
        assert artifact["n_events_logged"] == 0
        assert artifact["classes"] == []
        assert artifact["is_context_only"] is True
        # Must be JSON-serializable
        json.dumps(artifact)

    def test_missing_price_data_no_exception(self, tmp_path):
        """Events with tickers but no price parquets → n_graded=0, no exception."""
        from engine.news_event_ledger import persist_kept_events
        from scripts.grade_news_events import build_calibration

        h = _make_headline(tickers=["FICTITIOUS_TICKER"])
        persist_kept_events([h], asof_utc="2026-01-02T10:00:00+00:00", root=tmp_path)

        artifact = build_calibration(root=tmp_path)
        assert artifact["n_events_graded"] == 0
        for c in artifact["classes"]:
            assert c["n_graded"] == 0
            assert c["verdict"] == "insufficient"
        json.dumps(artifact)  # serializable

    def test_persist_kept_events_no_crash_on_bad_input(self, tmp_path):
        """persist_kept_events should not raise on malformed input."""
        from engine.news_event_ledger import persist_kept_events
        # None headline, missing fields
        result = persist_kept_events([None, {}, {"title": ""}], root=tmp_path)
        assert result == 0

    def test_persist_reject_sample_no_crash_on_empty(self, tmp_path):
        from engine.news_event_ledger import persist_reject_sample
        result = persist_reject_sample({}, root=tmp_path)
        assert result == 0

    def test_emit_calibration_writes_file(self, tmp_path):
        from scripts.grade_news_events import emit_calibration
        artifact = emit_calibration(root=tmp_path)
        out = tmp_path / "site" / "news" / "calibration.json"
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert parsed["schema"] == "news_event_calibration.v1"

    def test_reject_sample_keep_first(self, tmp_path):
        """Double-ingest of the same rejected headline keeps exactly one row."""
        from engine.news_event_ledger import persist_reject_sample, load_reject_sample
        h = {"title": "Top 5 dividend stocks", "domain": "fool.com",
             "seendate": "2026-01-02", "reason": "stock_pick_roundup"}
        n1 = persist_reject_sample({"macro": [h]}, asof_utc="2026-01-02T10:00:00+00:00",
                                   root=tmp_path)
        assert n1 == 1
        n2 = persist_reject_sample({"macro": [h]}, asof_utc="2026-01-03T10:00:00+00:00",
                                   root=tmp_path)
        assert n2 == 0
        df = load_reject_sample(tmp_path)
        assert len(df) == 1


# --------------------------------------------------------------------------- #
# 7. Full news suite import smoke-tests
# --------------------------------------------------------------------------- #
class TestImportSmoke:
    def test_news_event_ledger_imports(self):
        import engine.news_event_ledger as nel  # noqa: F401
        assert nel.is_context_only is True

    def test_grade_news_events_imports(self):
        from scripts.grade_news_events import (  # noqa: F401
            build_calibration,
            emit_calibration,
            _wilson_ci,
            _verdict,
            _fwd_ret_relative,
            SCHEMA,
        )
        assert SCHEMA == "news_event_calibration.v1"

    def test_news_common_imports(self):
        from engine import news_common as nc  # noqa: F401
        assert hasattr(nc, "event_id")
        assert hasattr(nc, "low_value_reason")

    def test_news_events_imports(self):
        from engine.news_events import classify_event, extract_numbers  # noqa: F401

    def test_build_news_imports(self):
        # Should import without executing — guard against accidental side-effects
        import scripts.build_news  # noqa: F401
