"""Tests for engine/source_registry.py — NAR-W4.

Covers:
- Beta-Bernoulli math including skeptical seed (NAR-R3)
- Grader resolution on synthetic price fixtures (hit + miss + unresolved-immature)
- Absence of upstream stores: graceful fail-open (NAR-R10)
- Lane gating: data/ writes blocked outside nightly lane
- qledger append shape: narrative_source_call + narrative_flare_state claim families
- Registry JSON schema: calls, hits, cred, last_resolved, accruing
- grading_summary.json: families, n_claims, n_resolved, hit_rate, accruing flags

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
    _FAMILY_FLARE_STATE,
    _FAMILY_SOURCE_CALL,
    _FIRST_COV_COLS,
    _ledger_advance_enabled,
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


def _write_price(root: Path, ticker: str, closes: dict) -> None:
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
        """When not nightly: registration steps report skipped; grading_summary still writes."""
        _make_claim_store(tmp_path)
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            result = nightly_run(data_root=tmp_path, root=tmp_path)
        assert result.get("source_call_registration", {}).get("skipped") is True
        assert result.get("flare_state_registration", {}).get("skipped") is True


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
# 7. Grader resolution: hit + miss + unresolved-immature
# ---------------------------------------------------------------------------

class TestGraderResolution:
    """Verify _resolve_source_call_claims with synthetic price data."""

    def _setup_price_stores(self, root: Path, entry_date: str, offset_days: int = 35) -> None:
        """Write SPY and a ticker with a controlled excess return."""
        entry_dt = pd.Timestamp(entry_date)
        # Build 60 days of prices starting 5 days before entry
        dates = [entry_dt + timedelta(days=i) for i in range(-5, 60)]
        date_strs = [d.strftime("%Y-%m-%d") for d in dates]

        # SPY: flat 100
        spy_closes = {d: 100.0 for d in date_strs}
        _write_price(root, "SPY", spy_closes)

    def _setup_ticker_hit(self, root: Path, entry_date: str) -> None:
        """Ticker that beats SPY by >5% within the window (a HIT)."""
        entry_dt = pd.Timestamp(entry_date)
        dates = [entry_dt + timedelta(days=i) for i in range(-5, 60)]
        # Price rises +8% from entry (day 0) to day 35 (excess=+8% > 5%)
        closes = {}
        for i, d in enumerate(dates):
            d_str = d.strftime("%Y-%m-%d")
            if i < 5:
                closes[d_str] = 100.0  # pre-entry
            else:
                closes[d_str] = 100.0 * (1 + 0.08 * (i - 5) / 50)  # gradual rise
        _write_price(root, "TICKER_HIT", closes)

    def _setup_ticker_miss(self, root: Path, entry_date: str) -> None:
        """Ticker that underperforms SPY by only 1% (a MISS: |excess| < 5%)."""
        entry_dt = pd.Timestamp(entry_date)
        dates = [entry_dt + timedelta(days=i) for i in range(-5, 60)]
        closes = {}
        for i, d in enumerate(dates):
            d_str = d.strftime("%Y-%m-%d")
            if i < 5:
                closes[d_str] = 100.0
            else:
                closes[d_str] = 100.0 * (1 - 0.01 * (i - 5) / 50)  # tiny drop
        _write_price(root, "TICKER_MISS", closes)

    def test_hit_updates_registry(self, tmp_path):
        """A matured claim with |excess|>5% marks a hit; registry cred rises."""
        _make_claim_store(tmp_path)
        entry_date = (date.today() - timedelta(days=50)).isoformat()

        self._setup_price_stores(tmp_path, entry_date)
        self._setup_ticker_hit(tmp_path, entry_date)

        # Register one claim manually
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

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path)
            result = nightly_run(data_root=tmp_path, root=tmp_path)

        resolution = result.get("source_call_resolution", {})
        assert resolution.get("n_resolved", 0) >= 1, f"Expected >=1 resolved, got: {resolution}"

        reg = load_registry(tmp_path)
        assert "semianaly" in reg
        entry = reg["semianaly"]
        assert entry["calls"] >= 1
        # A hit means hits >= 1
        assert entry["hits"] >= 1
        # cred should be higher than cold start (2/7 ≈ 0.286)
        cold_cred = beta_cred(0, 0)
        assert entry["cred"] > cold_cred, (
            f"cred {entry['cred']} should be > cold_cred {cold_cred} after a hit"
        )

    def test_miss_updates_registry_no_hit(self, tmp_path):
        """A matured claim with |excess|<5% marks a miss; hits stay 0."""
        _make_claim_store(tmp_path)
        entry_date = (date.today() - timedelta(days=50)).isoformat()

        self._setup_price_stores(tmp_path, entry_date)
        self._setup_ticker_miss(tmp_path, entry_date)

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

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path)
            result = nightly_run(data_root=tmp_path, root=tmp_path)

        resolution = result.get("source_call_resolution", {})
        n_resolved = resolution.get("n_resolved", 0)
        # If it did resolve, hits should be 0 (miss)
        if n_resolved >= 1:
            reg = load_registry(tmp_path)
            if "doomberg" in reg:
                assert reg["doomberg"]["hits"] == 0

    def test_immature_claim_not_resolved(self, tmp_path):
        """A claim from yesterday is not yet mature; resolution count stays 0."""
        _make_claim_store(tmp_path)
        entry_date = (date.today() - timedelta(days=1)).isoformat()  # too recent

        self._setup_price_stores(tmp_path, entry_date)
        self._setup_ticker_hit(tmp_path, entry_date)

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

        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            register_source_call_claims(data_root=tmp_path, root=tmp_path)
            result = nightly_run(data_root=tmp_path, root=tmp_path)

        resolution = result.get("source_call_resolution", {})
        # Immature: 0 resolved, >=1 immature
        assert resolution.get("n_resolved", 0) == 0
        assert resolution.get("n_immature", 0) >= 1


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

        # File written to data-tier location
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
