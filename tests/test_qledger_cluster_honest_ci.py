"""Unit tests for the cluster-honest Wilson CI fix in engine/qledger.py.

Covers:
  * _aggregate: wilson_ci_low is computed on n_dates (date clusters), not n_obs.
    With 3 dates × 10 obs/date the result must equal wilson_ci_low(hits_cluster, 3),
    not wilson_ci_low(hits_obs, 30).
  * promotion_check: same cluster-honest convention.
  * Regression: n_dates==0 or graded_hits==0 → ci_low is None (no division by zero).

These tests are directly runnable without live data: synthetic prices from the
shared fixture in test_qledger.py are reproduced inline for hermeticity.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q


# --------------------------------------------------------------------------- #
# synthetic price layer (mirrors test_qledger._mk_series)
# --------------------------------------------------------------------------- #

def _mk_series(start: str, days: int, start_px: float, drift: float) -> pd.Series:
    idx = pd.bdate_range(start=start, periods=days)
    vals = [start_px * (1.0 + drift) ** i for i in range(days)]
    return pd.Series(vals, index=idx)


@pytest.fixture
def prices(monkeypatch):
    """Synthetic price store: CARR beats SPY strongly (positive excess)."""
    store = {
        "CARR": _mk_series("2026-01-01", 120, 100.0, 0.010),
        "SPY":  _mk_series("2026-01-01", 120, 400.0, 0.002),
        "XLI":  _mk_series("2026-01-01", 120, 100.0, 0.004),
    }

    def _series(ticker, root):
        return store.get(ticker)

    monkeypatch.setattr("engine.ai_desk._close_series", _series)
    return store


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _seed_multi_obs_per_date(tmp_path, prices, asofs, obs_per_date=10,
                             desk="altdata", direction=1,
                             ticker="CARR", sector="Industrials"):
    """Register `obs_per_date` claims per asof (different salt → different claim_id).
    All directional, all expected to hit (CARR > SPY).
    """
    grades_p = tmp_path.joinpath(*q._GRADES_FILE)
    grades_p.parent.mkdir(parents=True, exist_ok=True)
    for a in asofs:
        for i in range(obs_per_date):
            c = q.make_claim(desk=desk, asof=a, scope_type="entity", scope_key=ticker,
                             direction=direction, horizon_d=21,
                             timestamp_quality="CRAWL_BOUNDED", sector=sector,
                             claim_family=desk)
            c["salt"] = f"{a}-{i}"
            stored = q.register(c, root=tmp_path)
            rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
            with grades_p.open("a") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# _aggregate: cluster-honest CI
# --------------------------------------------------------------------------- #

class TestAggregateClusterHonestCI:
    """wilson_ci_low in the track record must equal wilson on n_dates, not n_obs."""

    def test_ci_uses_n_dates_not_n_obs(self, prices, tmp_path):
        """3 dates × 10 obs/date = 30 obs, but CI must be on n=3."""
        asofs = ["2026-02-02", "2026-02-09", "2026-02-16"]
        _seed_multi_obs_per_date(tmp_path, prices, asofs, obs_per_date=10)
        tr = q.compute_track_record(tmp_path)
        cell = tr["by_desk"]["altdata"]["21"]

        n_obs = cell["n_obs"]
        n_dates = cell["n_dates"]
        assert n_obs == 30, f"expected 30 obs, got {n_obs}"
        assert n_dates == 3, f"expected 3 date clusters, got {n_dates}"

        # hit_rate should be 1.0 (all hits: CARR beats SPY on every date)
        hit_rate = cell["hit_rate"]
        assert hit_rate == 1.0, f"expected 1.0 hit_rate, got {hit_rate}"

        # Cluster-honest LB: wilson(hits_cluster=3, n=3)
        expected_lb = q.wilson_ci_low(3, 3)
        # Anti-conservative (wrong) LB on raw n: wilson(30, 30) — must NOT equal this
        wrong_lb = q.wilson_ci_low(30, 30)

        ci_low = cell["wilson_ci_low"]
        assert ci_low is not None, "ci_low should not be None"
        assert abs(ci_low - expected_lb) < 1e-5, (
            f"CI lower bound {ci_low:.6f} should equal cluster-honest "
            f"wilson(3,3)={expected_lb:.6f}, not obs-inflated wilson(30,30)={wrong_lb:.6f}"
        )
        # Explicitly confirm the inflated value is NOT used
        assert abs(ci_low - wrong_lb) > 0.01, (
            f"CI lower bound {ci_low:.6f} must differ from obs-inflated {wrong_lb:.6f}"
        )

    def test_partial_hit_rate_projects_correctly(self, prices, tmp_path):
        """2 hit dates out of 3, 10 obs each (20 of 30 obs hit) → cluster_hits=2."""
        # We need a mix of hits and misses at the date level. Use direction=-1 on
        # one date so those obs lose (CARR > SPY so direction=-1 → miss).
        grades_p = tmp_path.joinpath(*q._GRADES_FILE)
        grades_p.parent.mkdir(parents=True, exist_ok=True)

        # 2 dates with direction=+1 (CARR > SPY → hit)
        for a in ["2026-02-02", "2026-02-09"]:
            for i in range(10):
                c = q.make_claim(desk="altdata", asof=a, scope_type="entity",
                                 scope_key="CARR", direction=1, horizon_d=21,
                                 timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                                 claim_family="altdata")
                c["salt"] = f"hit-{a}-{i}"
                stored = q.register(c, root=tmp_path)
                rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
                with grades_p.open("a") as fh:
                    for r in rows:
                        fh.write(json.dumps(r) + "\n")

        # 1 date with direction=-1 (CARR > SPY but direction is DOWN → miss)
        for i in range(10):
            c = q.make_claim(desk="altdata", asof="2026-02-16", scope_type="entity",
                             scope_key="CARR", direction=-1, horizon_d=21,
                             timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                             claim_family="altdata")
            c["salt"] = f"miss-2026-02-16-{i}"
            stored = q.register(c, root=tmp_path)
            rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
            with grades_p.open("a") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")

        tr = q.compute_track_record(tmp_path)
        cell = tr["by_desk"]["altdata"]["21"]

        assert cell["n_obs"] == 30
        assert cell["n_dates"] == 3

        # Expected: hit_rate = 20/30 = 0.6667; cluster projection: round(0.6667*3) = 2
        hit_rate = cell["hit_rate"]
        assert hit_rate is not None
        cluster_hits = int(round(hit_rate * 3))
        expected_lb = q.wilson_ci_low(cluster_hits, 3)
        ci_low = cell["wilson_ci_low"]
        assert ci_low is not None
        assert abs(ci_low - expected_lb) < 1e-5, (
            f"CI={ci_low:.6f} expected={expected_lb:.6f} for cluster_hits={cluster_hits}/3"
        )

    def test_n_dates_zero_gives_none(self, prices, tmp_path):
        """No claims → n_dates=0 → ci_low must be None (no ZeroDivisionError)."""
        tr = q.compute_track_record(tmp_path)
        # No claims at all: by_desk should be empty, nothing to assert ci on
        assert tr["by_desk"] == {}

    def test_no_directional_hits_gives_none(self, prices, tmp_path):
        """graded_hits=0 (no hit/miss data) → ci_low must be None."""
        # Register a claim with direction=0 (salience only, no directional grading).
        # But qledger validation requires direction in {-1, 0, 1} and salience claims
        # still record hit=None in grades → graded_hits stays 0.
        grades_p = tmp_path.joinpath(*q._GRADES_FILE)
        grades_p.parent.mkdir(parents=True, exist_ok=True)
        c = q.make_claim(desk="altdata", asof="2026-02-02", scope_type="entity",
                         scope_key="CARR", direction=0, horizon_d=21,
                         timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                         claim_family="altdata")
        c["salt"] = "salience"
        stored = q.register(c, root=tmp_path)
        rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
        with grades_p.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        tr = q.compute_track_record(tmp_path)
        # Salience-only claim: graded_hits=0 → ci_low must be None
        cell = tr["by_desk"].get("altdata", {}).get("21", {})
        assert cell.get("wilson_ci_low") is None, (
            f"Expected None for salience-only (direction=0) claim, got {cell.get('wilson_ci_low')}"
        )


# --------------------------------------------------------------------------- #
# promotion_check: cluster-honest CI
# --------------------------------------------------------------------------- #

class TestPromotionCheckClusterHonestCI:
    """promotion_check wilson_ci_low must use independent date clusters."""

    def test_promotion_ci_uses_n_dates(self, prices, tmp_path):
        """25+ dates × 10 obs/date: promotion_check CI must use n_dates, not n_obs."""
        asofs = [d.date().isoformat() for d in pd.bdate_range("2026-02-02", periods=25)]
        _seed_multi_obs_per_date(tmp_path, prices, asofs, obs_per_date=10,
                                 desk="altdata", direction=1)
        result = q.promotion_check("altdata", horizon=21, root=tmp_path)

        assert result.n_dates == 25, f"expected n_dates=25, got {result.n_dates}"
        # hit_rate should be ~1.0 → cluster projection: hits_cluster ≈ 25
        # CI on n=25 is much lower than on n=250
        ci_n25 = q.wilson_ci_low(25, 25)
        ci_n250 = q.wilson_ci_low(250, 250)
        ci_low = result.wilson_ci_low
        assert ci_low is not None
        assert abs(ci_low - ci_n25) < 1e-5, (
            f"promotion_check CI={ci_low:.6f} should equal cluster-honest "
            f"wilson(25,25)={ci_n25:.6f}, not obs-inflated wilson(250,250)={ci_n250:.6f}"
        )
        assert abs(ci_low - ci_n250) > 0.05, (
            f"CI {ci_low:.6f} should differ substantially from obs-inflated {ci_n250:.6f}"
        )

    def test_promotion_no_dates_gives_none_ci(self, prices, tmp_path):
        """No claims → promotion_check must return ci_low=None, not error."""
        result = q.promotion_check("altdata", horizon=21, root=tmp_path)
        assert result.wilson_ci_low is None
        assert not result.eligible

    def test_promotion_zero_graded_hits_gives_none_ci(self, prices, tmp_path):
        """Salience-only family (direction=0) → graded_hits=0 → ci_low=None."""
        asofs = [d.date().isoformat() for d in pd.bdate_range("2026-02-02", periods=30)]
        grades_p = tmp_path.joinpath(*q._GRADES_FILE)
        grades_p.parent.mkdir(parents=True, exist_ok=True)
        for a in asofs:
            c = q.make_claim(desk="altdata", asof=a, scope_type="entity",
                             scope_key="CARR", direction=0, horizon_d=21,
                             timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                             claim_family="altdata")
            c["salt"] = a
            stored = q.register(c, root=tmp_path)
            rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
            with grades_p.open("a") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
        result = q.promotion_check("altdata", horizon=21, root=tmp_path)
        assert result.wilson_ci_low is None, (
            f"Expected None for salience-only family, got {result.wilson_ci_low}"
        )
