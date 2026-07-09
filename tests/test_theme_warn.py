"""tests/test_theme_warn.py — Unit tests for engine/theme_warn.py and lib/warn_fuzzy.py.

Covers:
  1. Fuzzy-map precision: exact match, punctuation tolerance, subsidiary suffixes,
     generic-word false-positive guard, longest-match wins.
  2. Z-score computation on synthetic WARN history.
  3. Store-absent -> honest null + exit 0 (the lethal false-null trap check).
  4. fused_obs_z UNCHANGED assertion: radar.compute_radar() with injected sources
     produces the SAME fused_obs_z values whether warn is wired or not.
  5. Banned-word scan: "validated" must not appear in any user-facing string.
  6. Authority block: may_rank/gate/size/escalate all False, is_context_only True.

All tests are hermetic (no real data; no network).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import tempfile

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.warn_fuzzy import (  # noqa: E402
    load_ticker_map,
    match_ticker,
    _is_generic,
    MIN_PATTERN_LEN,
)
from engine.theme_warn import (  # noqa: E402
    compute_warn_activity,
    _robust_z,
    _basket_warn_metric,
    _load_notices,
    AUTHORITY,
    WARN_WINDOW_DAYS,
    YOY_DAYS,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_ticker_rows(entries: list[tuple[str, str]]) -> list[dict]:
    """Build a minimal ticker_rows list from (pattern, ticker) pairs."""
    return [
        {
            "employer_name_pattern": pat,
            "ticker": tk,
            "valid_from": "1900-01-01",
            "valid_to": "2099-12-31",
            "confidence": "high",
            "notes": "",
        }
        for pat, tk in entries
    ]


def _make_notices_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal notices DataFrame."""
    df = pd.DataFrame(rows)
    if "notice_date" in df.columns:
        df["notice_date"] = pd.to_datetime(df["notice_date"], errors="coerce")
    if "workers" not in df.columns:
        df["workers"] = 0
    if "employer_raw" not in df.columns:
        df["employer_raw"] = ""
    if "state" not in df.columns:
        df["state"] = "CA"
    return df


def _payload(baskets: list[tuple[str, list[str]]]) -> dict:
    """Build a minimal baskets_payload."""
    return {
        "as_of": "2026-07-01",
        "baskets": [
            {"id": bid, "name": bid, "members": [{"symbol": s} for s in members]}
            for bid, members in baskets
        ],
    }


# ---------------------------------------------------------------------------
# Section 1: Fuzzy-map precision
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    """Precision tests for lib.warn_fuzzy.match_ticker."""

    def test_exact_match(self):
        rows = _make_ticker_rows([("intel", "INTC"), ("nvidia", "NVDA")])
        assert match_ticker("Intel Corporation", rows, "2026-01-01") == "INTC"
        assert match_ticker("NVIDIA Inc", rows, "2026-01-01") == "NVDA"

    def test_case_insensitive(self):
        rows = _make_ticker_rows([("boeing", "BA")])
        assert match_ticker("BOEING COMPANY", rows, "2026-01-01") == "BA"
        assert match_ticker("Boeing Co.", rows, "2026-01-01") == "BA"

    def test_punctuation_tolerance(self):
        """Suffix like 'Inc.' stripped before match."""
        rows = _make_ticker_rows([("amazon", "AMZN")])
        # Notice with trailing punctuation / legal suffix
        assert match_ticker("Amazon.com Inc.", rows, "2026-01-01") == "AMZN"
        assert match_ticker("Amazon Services, Inc.", rows, "2026-01-01") == "AMZN"

    def test_subsidiary_suffix(self):
        """Parent pattern should match subsidiary raw names."""
        rows = _make_ticker_rows([("google", "GOOGL")])
        assert match_ticker("Google LLC", rows, "2026-01-01") == "GOOGL"
        assert match_ticker("Google Cloud Services", rows, "2026-01-01") == "GOOGL"

    def test_longest_pattern_wins(self):
        """Among multiple matches, the longest pattern wins (most specific)."""
        rows = _make_ticker_rows([
            ("intel", "INTC"),
            ("intel semiconductor", "INTC_OLD"),  # longer pattern
        ])
        assert match_ticker("Intel Semiconductor Ltd", rows, "2026-01-01") == "INTC_OLD"

    def test_no_false_positive_on_generic_words(self):
        """Generic words like 'systems', 'group', 'international' must not match."""
        rows = _make_ticker_rows([
            ("systems", "FAKE1"),
            ("group", "FAKE2"),
            ("international", "FAKE3"),
            ("corp", "FAKE4"),
        ])
        # No specific pattern -> no match (all generic)
        assert match_ticker("Johnson Controls International Corp", rows, "2026-01-01") is None

    def test_no_match_when_pattern_too_short(self):
        """Patterns shorter than MIN_PATTERN_LEN are skipped."""
        rows = _make_ticker_rows([("ibm", "IBM"), ("ge", "GE")])
        # 'ge' is 2 chars; 'ibm' is 3 chars — both below default MIN_PATTERN_LEN=5
        assert match_ticker("International Business Machines", rows, "2026-01-01") is None
        # 'ge' alone is too short
        assert match_ticker("GE Aviation", rows, "2026-01-01") is None

    def test_validity_window_respected(self):
        """Notice outside validity window is not matched."""
        rows = [
            {
                "employer_name_pattern": "enron",
                "ticker": "ENRN",
                "valid_from": "2000-01-01",
                "valid_to": "2003-12-31",
                "confidence": "high",
                "notes": "",
            }
        ]
        # Within window
        assert match_ticker("Enron Corp", rows, "2001-06-01") == "ENRN"
        # Outside window
        assert match_ticker("Enron Corp", rows, "2004-01-01") is None

    def test_empty_employer_returns_none(self):
        rows = _make_ticker_rows([("intel", "INTC")])
        assert match_ticker("", rows, "2026-01-01") is None
        assert match_ticker("   ", rows, "2026-01-01") is None

    def test_no_rows_returns_none(self):
        assert match_ticker("Intel Corporation", [], "2026-01-01") is None

    def test_is_generic_words(self):
        for word in ["systems", "group", "inc", "corp", "global", "national"]:
            assert _is_generic(word), f"Expected {word!r} to be generic"

    def test_specific_company_not_generic(self):
        assert not _is_generic("microsoft")
        assert not _is_generic("boeing")
        assert not _is_generic("lockheed")


# ---------------------------------------------------------------------------
# Section 2: Z-score computation on synthetic data
# ---------------------------------------------------------------------------

class TestRobustZ:
    """Cross-sectional robust-z on synthetic metrics."""

    def test_monotone_order_preserved(self):
        """Higher metric -> higher z."""
        values = [0.5, 1.0, 2.0, 3.0]
        zs = _robust_z(values)
        for i in range(len(zs) - 1):
            assert zs[i] < zs[i + 1], f"z order wrong at index {i}"

    def test_all_equal_returns_zeros(self):
        zs = _robust_z([5.0, 5.0, 5.0, 5.0])
        assert all(abs(z) < 1e-9 for z in zs)

    def test_winsorise_at_z_clamp(self):
        from engine.theme_warn import Z_CLAMP
        values = [0.0] * 10 + [1000.0]  # extreme outlier
        zs = _robust_z(values)
        assert max(zs) <= Z_CLAMP + 1e-9

    def test_nan_treated_as_absent(self):
        values = [1.0, float("nan"), 2.0, 3.0]
        zs = _robust_z(values)
        assert np.isfinite(zs[0]) and np.isfinite(zs[2]) and np.isfinite(zs[3])
        # nan bucket returns 0.0
        assert zs[1] == 0.0

    def test_single_value_returns_zero(self):
        assert _robust_z([42.0]) == [0.0]

    def test_symmetric_two_values(self):
        zs = _robust_z([0.0, 10.0])
        assert len(zs) == 2
        assert zs[0] < 0 and zs[1] > 0


class TestBasketWarnMetric:
    """Per-basket warn metric on synthetic notices."""

    def _as_of(self):
        return datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_recent_notices_raise_metric(self):
        """Basket with many recent notices and few prior -> positive metric (log(ratio) > 0)."""
        ticker_rows = _make_ticker_rows([("intel", "INTC")])
        # Recent notices (within 90 days of 2026-07-01)
        recent_rows = [
            {"employer_raw": "Intel Corporation", "notice_date": "2026-06-15",
             "workers": 500, "state": "CA"},
            {"employer_raw": "Intel Corporation", "notice_date": "2026-05-20",
             "workers": 300, "state": "OR"},
        ]
        # Prior notices (~1 year ago, 90-day window)
        prior_rows = [
            {"employer_raw": "Intel Corporation", "notice_date": "2025-06-10",
             "workers": 50, "state": "CA"},
        ]
        df = _make_notices_df(recent_rows + prior_rows)
        result = _basket_warn_metric("ai_semiconductors", ["INTC"], df, ticker_rows,
                                     as_of=self._as_of())
        assert result is not None
        assert result["warn_workers_90d"] == 800
        assert result["warn_workers_prior"] == 50
        assert result["warn_yoy_ratio"] > 1.0
        assert result["metric"] > 0.0  # log(>1) = positive
        assert "INTC" in result["matched_tickers"]

    def test_no_match_returns_none(self):
        """If no employer matches any basket member, return None."""
        ticker_rows = _make_ticker_rows([("boeing", "BA")])
        df = _make_notices_df([
            {"employer_raw": "Some Unknown Company LLC", "notice_date": "2026-06-15",
             "workers": 100, "state": "TX"},
        ])
        result = _basket_warn_metric("defense", ["LMT", "NOC"], df, ticker_rows,
                                     as_of=self._as_of())
        assert result is None

    def test_quiet_prior_year_clamps_high(self):
        """Prior window empty + active recent -> ratio clamps to ACCEL_CLAMP ceiling."""
        from engine.theme_warn import ACCEL_CLAMP
        ticker_rows = _make_ticker_rows([("intel", "INTC")])
        recent = [{"employer_raw": "Intel Corp", "notice_date": "2026-06-01",
                   "workers": 1000, "state": "CA"}]
        # No prior notices
        df = _make_notices_df(recent)
        result = _basket_warn_metric("ai_semiconductors", ["INTC"], df, ticker_rows,
                                     as_of=self._as_of())
        assert result is not None
        assert result["warn_yoy_ratio"] == ACCEL_CLAMP[1]


# ---------------------------------------------------------------------------
# Section 3: Store-absent -> honest null + exit 0
# ---------------------------------------------------------------------------

class TestStoreAbsent:
    """When WARN store is missing: returns honest null, never crashes."""

    def test_absent_store_returns_null_for_all_baskets(self, tmp_path, monkeypatch):
        """WARN store absent -> every basket gets warn_z=None; function returns, no exception."""
        # Ensure env var not set
        monkeypatch.delenv("WARN_STORE", raising=False)
        payload = _payload([("defense", ["LMT", "NOC"]), ("ai_semiconductors", ["NVDA"])])
        # Pass a store_path that doesn't exist
        result = compute_warn_activity(payload, store_path=tmp_path / "nonexistent.parquet",
                                       root=tmp_path)
        assert isinstance(result, dict)
        for bid in ["defense", "ai_semiconductors"]:
            assert bid in result
            assert result[bid]["warn_z"] is None
            assert result[bid]["n_matched"] == 0

    def test_store_absent_exit_behavior(self, tmp_path, monkeypatch):
        """Function doesn't raise; caller can safely exit 0."""
        monkeypatch.delenv("WARN_STORE", raising=False)
        payload = _payload([("defense", ["LMT"])])
        try:
            result = compute_warn_activity(payload, store_path=tmp_path / "missing.parquet",
                                           root=tmp_path)
            assert result is not None  # always returns a dict
        except Exception as exc:
            pytest.fail(f"compute_warn_activity raised on absent store: {exc}")

    def test_env_override_respected(self, tmp_path, monkeypatch):
        """WARN_STORE env var pointing to an existing file is used."""
        store = tmp_path / "notices.parquet"
        # Write a minimal parquet
        df = pd.DataFrame({
            "notice_date": pd.to_datetime(["2026-06-15"]),
            "employer_raw": ["Some Corp"],
            "workers": [100],
            "state": ["CA"],
        })
        df.to_parquet(store, index=False)
        monkeypatch.setenv("WARN_STORE", str(store))
        payload = _payload([("defense", ["LMT"])])
        # No match expected (no ticker map) but should NOT raise
        result = compute_warn_activity(payload, root=tmp_path)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Section 4: fused_obs_z UNCHANGED assertion (regression guard)
# ---------------------------------------------------------------------------

class TestFusedObsZUnchanged:
    """CRITICAL FENCE: adding theme_warn must NOT change fused_obs_z values."""

    def _wide(self, spec, n_complete=15):
        """Build wide month x ticker frame for theme_activity."""
        from engine.theme_activity import LAG_MONTHS
        cols = {tk: [b] * (n_complete - 3) + [r] * 3 + [b] * LAG_MONTHS
                for tk, (b, r) in spec.items()}
        idx = pd.date_range(end="2026-05-01", periods=n_complete + LAG_MONTHS, freq="MS")
        return pd.DataFrame(cols, index=idx)

    def test_fused_obs_z_unchanged_after_warn_wiring(self, tmp_path, monkeypatch):
        """fused_obs_z values are bit-identical before and after warn leg is wired."""
        from engine import theme_activity as ta
        from engine.radar import compute_radar

        M = 1e6
        us = self._wide({
            "LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M),  # defense accelerating
        })
        payload = {
            "as_of": "2026-06-19",
            "baskets": [
                {
                    "id": "defense",
                    "name": "Defense",
                    "name_zh": "国防",
                    "members": [{"symbol": "LMT"}, {"symbol": "NOC"}],
                    "perf": {"60d": {"rel": -0.05}},
                }
            ],
        }

        # Compute base theme_activity (no warn)
        ra_base = ta.compute_real_activity(payload, sources_data={"usaspending": us}, news=False)
        base_fused = {bid: v["fused_obs_z"] for bid, v in ra_base.items()}

        # Now call compute_radar with warn wired (store absent -> warn null, fused_obs_z must be same)
        monkeypatch.delenv("WARN_STORE", raising=False)
        radar = compute_radar(
            payload,
            sources_data={"usaspending": us},
            news=False,
            root=tmp_path,  # no data dir -> warn returns null
        )
        if radar is None:
            pytest.skip("Radar returned None (no consensus price read available)")

        for flag in radar.get("flags", []):
            bid = flag["basket"]
            if bid in base_fused:
                assert flag["observable"]["z"] == base_fused[bid], (
                    f"fused_obs_z changed for {bid}: "
                    f"expected {base_fused[bid]} got {flag['observable']['z']}"
                )

    def test_warn_key_is_separate_from_observable(self, tmp_path, monkeypatch):
        """The 'warn' key is sibling to 'observable', never inside it."""
        from engine.radar import compute_radar
        M = 1e6
        us = self._wide({"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)})
        payload = {
            "as_of": "2026-06-19",
            "baskets": [{
                "id": "defense", "name": "Defense", "name_zh": "国防",
                "members": [{"symbol": "LMT"}, {"symbol": "NOC"}],
                "perf": {"60d": {"rel": -0.05}},
            }],
        }
        monkeypatch.delenv("WARN_STORE", raising=False)
        radar = compute_radar(payload, sources_data={"usaspending": us}, news=False, root=tmp_path)
        if radar is None:
            pytest.skip("Radar returned None")
        for flag in radar["flags"]:
            # 'warn' must be a top-level key, not inside 'observable'
            assert "warn" in flag
            assert "warn" not in flag.get("observable", {})
            # 'warn_z' must NOT appear inside 'observable'
            assert "warn_z" not in flag.get("observable", {})


# ---------------------------------------------------------------------------
# Section 5: Banned-word scan
# ---------------------------------------------------------------------------

class TestBannedWords:
    """Ensure 'validated' never appears in user-facing strings from theme_warn."""

    def _collect_strings(self, obj, path="") -> list[tuple[str, str]]:
        """Recursively collect all string values from a dict/list."""
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                results.extend(self._collect_strings(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                results.extend(self._collect_strings(v, f"{path}[{i}]"))
        elif isinstance(obj, str):
            results.append((path, obj))
        return results

    def test_no_validated_in_output(self, tmp_path, monkeypatch):
        """The word 'validated' must not appear in any compute_warn_activity output string."""
        monkeypatch.delenv("WARN_STORE", raising=False)
        payload = _payload([("defense", ["LMT", "NOC"]), ("ai_semiconductors", ["NVDA"])])
        result = compute_warn_activity(payload, store_path=tmp_path / "none.parquet",
                                       root=tmp_path)
        all_strings = self._collect_strings(result)
        for path, val in all_strings:
            assert "validated" not in val.lower(), (
                f"Banned word 'validated' found at {path}: {val!r}"
            )

    def test_no_validated_in_module_strings(self):
        """Scan engine/theme_warn.py source for banned word 'validated'."""
        src = (ROOT / "engine" / "theme_warn.py").read_text(encoding="utf-8")
        # Allow "validated" only in comments (lines starting with #)
        # User-facing strings must never contain it
        non_comment_lines = [
            line for line in src.split("\n")
            if not line.lstrip().startswith("#")
        ]
        for line in non_comment_lines:
            # Only check string literals (simplified: check for the word in quotes)
            if "validated" in line.lower():
                # If it's in a string (between quotes), fail
                import re
                in_string = re.search(r'["\'].*validated.*["\']', line, re.IGNORECASE)
                assert in_string is None, (
                    f"'validated' in user-facing string: {line.strip()!r}"
                )

    def test_no_validated_in_warn_fuzzy(self):
        """lib/warn_fuzzy.py must not contain 'validated' in string literals."""
        src = (ROOT / "lib" / "warn_fuzzy.py").read_text(encoding="utf-8")
        import re
        in_strings = re.findall(r'["\'].*?validated.*?["\']', src, re.IGNORECASE)
        assert not in_strings, f"'validated' found in string literals: {in_strings}"


# ---------------------------------------------------------------------------
# Section 6: Authority block correctness
# ---------------------------------------------------------------------------

class TestAuthority:
    """Authority block must conform to display-tier constraints."""

    def test_authority_constants(self):
        assert AUTHORITY["may_rank"] is False
        assert AUTHORITY["may_gate"] is False
        assert AUTHORITY["may_size"] is False
        assert AUTHORITY["may_escalate"] is False
        assert AUTHORITY["is_context_only"] is True

    def test_each_basket_carries_authority(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WARN_STORE", raising=False)
        payload = _payload([("defense", ["LMT"]), ("nuclear_power", ["CCJ"])])
        result = compute_warn_activity(payload, store_path=tmp_path / "none.parquet",
                                       root=tmp_path)
        for bid, val in result.items():
            assert "authority" in val, f"No authority block for {bid}"
            auth = val["authority"]
            assert auth["may_rank"] is False, f"{bid}: may_rank not False"
            assert auth["may_gate"] is False, f"{bid}: may_gate not False"
            assert auth["is_context_only"] is True, f"{bid}: is_context_only not True"

    def test_warn_key_in_radar_has_may_rank_false(self, tmp_path, monkeypatch):
        """The warn sub-dict in each radar flag must have may_rank=False."""
        from engine.radar import compute_radar
        M = 1e6

        def _wide(spec, n_complete=15):
            from engine.theme_activity import LAG_MONTHS
            cols = {tk: [b] * (n_complete - 3) + [r] * 3 + [b] * LAG_MONTHS
                    for tk, (b, r) in spec.items()}
            idx = pd.date_range(end="2026-05-01", periods=n_complete + LAG_MONTHS, freq="MS")
            return pd.DataFrame(cols, index=idx)

        us = _wide({"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)})
        payload = {
            "as_of": "2026-06-19",
            "baskets": [{
                "id": "defense", "name": "Defense", "name_zh": "国防",
                "members": [{"symbol": "LMT"}, {"symbol": "NOC"}],
                "perf": {"60d": {"rel": -0.05}},
            }],
        }
        monkeypatch.delenv("WARN_STORE", raising=False)
        radar = compute_radar(payload, sources_data={"usaspending": us}, news=False, root=tmp_path)
        if radar is None:
            pytest.skip("Radar returned None")
        for flag in radar["flags"]:
            warn = flag.get("warn")
            if warn:
                assert warn.get("may_rank") is False
                assert warn.get("may_gate") is False
                assert warn.get("is_context_only") is True


# ---------------------------------------------------------------------------
# Section 7: Full pipeline with synthetic store
# ---------------------------------------------------------------------------

class TestEndToEndSynthetic:
    """With a synthetic WARN store and ticker map, verify z values are sensible."""

    def _make_ticker_map_csv(self, path: Path, entries: list[tuple[str, str]]) -> Path:
        csv_path = path / "w2044_warn_ticker_map.csv"
        lines = ["employer_name_pattern,ticker,valid_from,valid_to,confidence,notes"]
        for pat, tk in entries:
            lines.append(f"{pat},{tk},1900-01-01,2099-12-31,high,test")
        csv_path.write_text("\n".join(lines), encoding="utf-8")
        return csv_path

    def _make_parquet_store(self, path: Path, rows: list[dict]) -> Path:
        store_path = path / "notices.parquet"
        df = pd.DataFrame(rows)
        df["notice_date"] = pd.to_datetime(df["notice_date"])
        store_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(store_path, index=False)
        return store_path

    def test_high_activity_basket_gets_positive_z(self, tmp_path):
        """Basket with many recent layoffs vs a quiet prior -> positive warn_z."""
        ticker_map = self._make_ticker_map_csv(tmp_path, [
            ("intel", "INTC"), ("advanced micro devices", "AMD"),
        ])
        # Defense basket: "boeing" -> BA (no recent notices)
        # ai_semiconductors: "intel" -> INTC, "advanced micro devices" -> AMD (lots of recent)
        rows = [
            # ai_semiconductors: heavy recent
            {"employer_raw": "Intel Corporation", "notice_date": "2026-06-15",
             "workers": 1000, "state": "CA"},
            {"employer_raw": "Advanced Micro Devices Inc", "notice_date": "2026-06-10",
             "workers": 500, "state": "CA"},
            # ai_semiconductors: light prior (1 year ago)
            {"employer_raw": "Intel Corporation", "notice_date": "2025-06-15",
             "workers": 50, "state": "CA"},
        ]
        store = self._make_parquet_store(tmp_path, rows)
        payload = _payload([
            ("ai_semiconductors", ["INTC", "AMD"]),
            ("defense", ["LMT", "NOC"]),  # no matches -> null z
        ])
        result = compute_warn_activity(
            payload, store_path=store, ticker_map_path=ticker_map,
            as_of=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        assert "ai_semiconductors" in result
        ai = result["ai_semiconductors"]
        assert ai["warn_z"] is not None
        assert ai["warn_workers_90d"] == 1500
        assert ai["warn_workers_prior"] == 50
        assert ai["warn_yoy_ratio"] > 1.0

        defense = result["defense"]
        assert defense["warn_z"] is None or defense["n_matched"] == 0

    def test_two_baskets_z_order(self, tmp_path):
        """Basket with MORE recent layoffs (vs prior) should have HIGHER warn_z."""
        ticker_map = self._make_ticker_map_csv(tmp_path, [
            ("lockheed martin", "LMT"),
            ("intel", "INTC"),
        ])
        rows = [
            # defense: heavy recent + heavy prior (ratio ~1 -> lower metric)
            {"employer_raw": "Lockheed Martin Corp", "notice_date": "2026-06-15",
             "workers": 100, "state": "TX"},
            {"employer_raw": "Lockheed Martin Corp", "notice_date": "2025-06-15",
             "workers": 90, "state": "TX"},
            # ai_semiconductors: moderate recent + tiny prior (high ratio -> high metric)
            {"employer_raw": "Intel Corp", "notice_date": "2026-06-20",
             "workers": 200, "state": "OR"},
            {"employer_raw": "Intel Corp", "notice_date": "2025-06-20",
             "workers": 10, "state": "OR"},
        ]
        store = self._make_parquet_store(tmp_path, rows)
        payload = _payload([
            ("defense", ["LMT"]),
            ("ai_semiconductors", ["INTC"]),
        ])
        result = compute_warn_activity(
            payload, store_path=store, ticker_map_path=ticker_map,
            as_of=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        ai_z = result["ai_semiconductors"]["warn_z"]
        def_z = result["defense"]["warn_z"]
        assert ai_z is not None and def_z is not None, (
            f"Expected both baskets to have warn_z: ai={ai_z}, def={def_z}"
        )
        assert ai_z > def_z, (
            f"Expected ai_semiconductors (high ratio) > defense (low ratio): "
            f"{ai_z} vs {def_z}"
        )

    def test_coverage_note_bilingual(self, tmp_path, monkeypatch):
        """coverage_note and coverage_note_zh must both be present."""
        monkeypatch.delenv("WARN_STORE", raising=False)
        payload = _payload([("defense", ["LMT"])])
        result = compute_warn_activity(payload, store_path=tmp_path / "none.parquet",
                                       root=tmp_path)
        assert "defense" in result
        assert result["defense"]["coverage_note"] is not None
        assert result["defense"]["coverage_note_zh"] is not None
        # Neither should contain 'validated'
        assert "validated" not in result["defense"]["coverage_note"].lower()
        assert "validated" not in result["defense"]["coverage_note_zh"].lower()
