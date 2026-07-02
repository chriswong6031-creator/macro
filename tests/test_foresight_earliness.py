"""engine.foresight_earliness — attention-gap earliness engine (Q3).

Tests:
  (a) axis with no input drops out and weights renormalize (score ≠ base·defaults)
  (b) earliness rank-percentile ordering correct on synthetic 3-theme fixture
  (c) missing leg shrinks denominator (2-leg theme vs 4-leg theme both valid)
  (d) never reads n_analysts
  (e) underpricing no longer equals 1−0.9·breadth (regression: different attention → different underpricing)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import foresight_earliness as fe
from engine import foresight_score as fs


# ---------------------------------------------------------------------------
# (a) Score: absent axis drops out and weights renormalize — score ≠ base·defaults
# ---------------------------------------------------------------------------

def test_absent_axis_drops_out_score_not_defaults():
    """With no live input, score is None-safe (timing always has a value, so not 0).
    Critically: magnitude=None, pricing_power=None must NOT contribute 0.4/0.5 to the sum."""
    fs.reset_caches()
    row = {
        "theme": "test_theme",
        "stage": "WATCH",
        "bottleneck_band": None,   # no physical read → bottleneck axis None, cap fires
        "bottleneck_text_only": False,
        "tightness": None,
        "ppi_yoy_latest": None,
        "bottleneck_regime": False,
        "demand_band": None,
        "demand_strength": None,
        "capex_yoy": None,       # magnitude axis: no input → None → drops out
        "divergence_share": None,
        "revision_breadth": None,
        "revision_level": None,
        "broadening_state": None,
        "est_drift_90d": None,
        "guidance_band": None,
        "n_altdata_leading": 0,
        "entry_ready": False,
    }
    # inject a known earliness value (bypasses disk)
    row["_earliness"] = 0.7

    s = fs.score_row(row)
    # timing always available (returns 0.4 for WATCH), underpricing from earliness → 0.7
    # magnitude None, acceleration None (no demand_band, no broadening_state, no regime),
    # bottleneck None, pricing_power None, purity None
    assert s["n_axes_live"] < 7, f"Expected < 7 live axes, got {s['n_axes_live']}"
    assert s["axes"]["magnitude"] is None, "magnitude with no input must be None"
    assert s["axes"]["pricing_power"] is None, "pricing_power with no input must be None"
    # score must not be the old 37-50 band from 0.4 defaults — with only timing+underpricing
    # live the score will be different from what 7-axis-all-defaults would give
    assert s["score"] <= 50.0, "text-only cap must bind"


def test_weights_renormalize_over_live_axes():
    """Renormalized weighted sum over live axes only — different from full-7-axis sum."""
    fs.reset_caches()
    row_partial = {
        "theme": "partial",
        "stage": "WATCH",
        "bottleneck_band": None,
        "bottleneck_text_only": False,
        "tightness": None,
        "ppi_yoy_latest": None,
        "bottleneck_regime": False,
        "demand_band": "ACCELERATING",
        "demand_strength": "direct",
        "capex_yoy": 69.0,
        "divergence_share": 0.5,
        "revision_breadth": None,
        "revision_level": "FLAT_LOW",
        "broadening_state": "FLAT_LOW",
        "est_drift_90d": None,
        "guidance_band": None,
        "n_altdata_leading": 0,
        "entry_ready": False,
        "_earliness": 0.8,
    }
    s = fs.score_row(row_partial)
    assert s["n_axes_live"] >= 3, "Should have at least timing, acceleration, underpricing"
    # verify bottleneck is None (AWAITING)
    assert s["axes"]["bottleneck"] is None
    # verify score is capped at 50
    assert s["score"] <= 50.0


# ---------------------------------------------------------------------------
# (b) Earliness rank-percentile ordering on a 3-theme fixture
# ---------------------------------------------------------------------------

def test_earliness_rank_percentile_ordering():
    """3-theme fixture: least-attended theme gets earliness closest to 1.0."""
    themes_cfg = {
        "quiet": {"tickers": ["A"]},   # will have no/low attention
        "medium": {"tickers": ["B"]},
        "loud": {"tickers": ["C"]},    # will have most attention
    }

    # Patch all legs to return controlled values
    def _cov(members):
        return {"quiet": 1.0, "medium": 3.0, "loud": 10.0}

    def _news(keys):
        return {"quiet": 5.0, "medium": 20.0, "loud": 50.0}

    def _own(members):
        return {"quiet": 0.0, "medium": 1.0, "loud": 3.0}

    def _tape(members):
        return {"quiet": 0.1, "medium": 0.5, "loud": 0.95}

    import engine.foresight_earliness as fe_mod
    orig_cov = fe_mod._leg_coverage_arrival
    orig_news = fe_mod._leg_news_flow
    orig_own = fe_mod._leg_ownership_breadth
    orig_tape = fe_mod._leg_tape_extension
    try:
        fe_mod._leg_coverage_arrival = _cov
        fe_mod._leg_news_flow = _news
        fe_mod._leg_ownership_breadth = _own
        fe_mod._leg_tape_extension = _tape
        result = fe.compute_foresight_earliness(themes_cfg=themes_cfg, write_log=False)
    finally:
        fe_mod._leg_coverage_arrival = orig_cov
        fe_mod._leg_news_flow = orig_news
        fe_mod._leg_ownership_breadth = orig_own
        fe_mod._leg_tape_extension = orig_tape

    assert result is not None
    themes_out = result["themes"]
    assert themes_out["quiet"]["earliness"] > themes_out["medium"]["earliness"], \
        "quiet theme must be earlier than medium"
    assert themes_out["medium"]["earliness"] > themes_out["loud"]["earliness"], \
        "medium theme must be earlier than loud"
    assert themes_out["loud"]["earliness"] < themes_out["quiet"]["earliness"], \
        "loud theme must be latest"


# ---------------------------------------------------------------------------
# (c) Missing leg shrinks denominator — both 2-leg and 4-leg themes are valid
# ---------------------------------------------------------------------------

def test_missing_leg_shrinks_denominator():
    """A theme with only 2 live legs and one with 4 live legs both produce valid earliness."""
    themes_cfg = {
        "two_legs": {"tickers": ["X"]},
        "four_legs": {"tickers": ["Y"]},
    }

    # Two-leg theme: only news + tape available
    def _cov_partial(members):
        return {"two_legs": None, "four_legs": 5.0}

    def _news_partial(keys):
        return {"two_legs": 20.0, "four_legs": 20.0}

    def _own_partial(members):
        return {"two_legs": None, "four_legs": 2.0}

    def _tape_partial(members):
        return {"two_legs": 0.8, "four_legs": 0.8}

    import engine.foresight_earliness as fe_mod
    orig_cov = fe_mod._leg_coverage_arrival
    orig_news = fe_mod._leg_news_flow
    orig_own = fe_mod._leg_ownership_breadth
    orig_tape = fe_mod._leg_tape_extension
    try:
        fe_mod._leg_coverage_arrival = _cov_partial
        fe_mod._leg_news_flow = _news_partial
        fe_mod._leg_ownership_breadth = _own_partial
        fe_mod._leg_tape_extension = _tape_partial
        result = fe.compute_foresight_earliness(themes_cfg=themes_cfg, write_log=False)
    finally:
        fe_mod._leg_coverage_arrival = orig_cov
        fe_mod._leg_news_flow = orig_news
        fe_mod._leg_ownership_breadth = orig_own
        fe_mod._leg_tape_extension = orig_tape

    assert result is not None
    t = result["themes"]
    # both themes must produce valid earliness
    assert t["two_legs"]["earliness"] is not None, "2-leg theme must produce earliness"
    assert t["four_legs"]["earliness"] is not None, "4-leg theme must produce earliness"
    assert t["two_legs"]["n_legs_live"] == 2
    assert t["four_legs"]["n_legs_live"] == 4
    # legs show availability correctly
    assert t["two_legs"]["legs"]["coverage_arrival"]["available"] is False
    assert t["two_legs"]["legs"]["news_flow"]["available"] is True


# ---------------------------------------------------------------------------
# (d) Never reads n_analysts
# ---------------------------------------------------------------------------

def test_never_reads_n_analysts(tmp_path):
    """coverage_arrival leg must return None when only n_analysts present (no n_covering)."""
    # Write a parquet with n_analysts but no n_covering — leg must be absent
    import pandas as pd
    df = pd.DataFrame({"n_analysts": [5.0, 3.0]}, index=["AAPL", "MSFT"])
    p = tmp_path / "revisions" / "latest.parquet"
    p.parent.mkdir(parents=True)
    df.to_parquet(p)

    import engine.foresight_earliness as fe_mod
    from lib import config as cfg_mod
    orig_data_dir = cfg_mod.data_dir

    try:
        cfg_mod.data_dir = lambda: tmp_path
        result = fe_mod._leg_coverage_arrival({"test_theme": ["AAPL", "MSFT"]})
    finally:
        cfg_mod.data_dir = orig_data_dir

    # With no n_covering column, leg must return None — never use n_analysts
    assert result.get("test_theme") is None, \
        "coverage_arrival must return None when only n_analysts present (no n_covering)"


def test_never_reads_n_analysts_with_n_covering(tmp_path):
    """coverage_arrival leg reads n_covering when present, not n_analysts."""
    import pandas as pd
    df = pd.DataFrame({"n_analysts": [5.0, 3.0], "n_covering": [10.0, 8.0]},
                      index=["AAPL", "MSFT"])
    p = tmp_path / "revisions" / "latest.parquet"
    p.parent.mkdir(parents=True)
    df.to_parquet(p)

    import engine.foresight_earliness as fe_mod
    from lib import config as cfg_mod
    orig_data_dir = cfg_mod.data_dir

    try:
        cfg_mod.data_dir = lambda: tmp_path
        result = fe_mod._leg_coverage_arrival({"test_theme": ["AAPL", "MSFT"]})
    finally:
        cfg_mod.data_dir = orig_data_dir

    # Should read n_covering (mean of 10.0 and 8.0 = 9.0), NOT n_analysts
    assert result.get("test_theme") == pytest.approx(9.0), \
        "coverage_arrival must read n_covering, not n_analysts"


# ---------------------------------------------------------------------------
# (e) Underpricing no longer equals 1−0.9·breadth — regression test
# ---------------------------------------------------------------------------

def test_underpricing_not_circular_with_breadth():
    """Feed identical breadth, different earliness → different underpricing (de-circularized).
    OLD: underpricing = 1 - 0.9 * breadth (same breadth → same underpricing, always).
    NEW: underpricing = earliness (different attention → different underpricing)."""
    fs.reset_caches()

    base_row = {
        "theme": "test",
        "stage": "WATCH",
        "bottleneck_band": None,
        "bottleneck_text_only": False,
        "tightness": None,
        "ppi_yoy_latest": None,
        "bottleneck_regime": False,
        "demand_band": None,
        "demand_strength": None,
        "capex_yoy": None,
        "divergence_share": None,
        "revision_breadth": 0.3,   # IDENTICAL breadth for both rows
        "revision_level": "POSITIVE",
        "broadening_state": "FLAT_LOW",
        "est_drift_90d": None,
        "guidance_band": None,
        "n_altdata_leading": 0,
        "entry_ready": False,
    }

    # Row 1: high earliness (less attention)
    row_early = dict(base_row, _earliness=0.9)
    # Row 2: low earliness (more attention) — same breadth
    row_late = dict(base_row, _earliness=0.1)

    s_early = fs.score_row(row_early)
    s_late = fs.score_row(row_late)

    up_early = s_early["axes"]["underpricing"]
    up_late = s_late["axes"]["underpricing"]

    assert up_early is not None and up_late is not None, \
        "underpricing axis must be present when earliness is injected"
    assert up_early > up_late, (
        f"Same breadth ({base_row['revision_breadth']}) but different earliness must yield "
        f"different underpricing: early={up_early} must > late={up_late}. "
        "If underpricing still equals 1−0.9·breadth, this test catches the regression."
    )


def test_underpricing_fallback_to_revision_level_not_breadth():
    """When earliness is unavailable (None), fallback uses revision_level NOT revision_breadth."""
    fs.reset_caches()

    row = {
        "theme": "test",
        "stage": "WATCH",
        "bottleneck_band": None,
        "bottleneck_text_only": False,
        "tightness": None,
        "ppi_yoy_latest": None,
        "bottleneck_regime": False,
        "demand_band": None,
        "demand_strength": None,
        "capex_yoy": None,
        "divergence_share": None,
        "revision_breadth": 0.9,   # would give very low underpricing under old formula
        "revision_level": "FLAT_LOW",  # FLAT_LOW → 0.80 under new fallback
        "broadening_state": None,
        "est_drift_90d": None,
        "guidance_band": None,
        "n_altdata_leading": 0,
        "entry_ready": False,
        "_earliness": None,   # explicitly absent
    }
    s = fs.score_row(row)
    up = s["axes"]["underpricing"]
    # Fallback FLAT_LOW → 0.80. Old formula: 1 - 0.9 * 0.9 = 0.19. Very different.
    assert up is not None
    assert up >= 0.75, (
        f"FLAT_LOW level with no earliness should yield ~0.80 underpricing (new fallback), "
        f"not 0.19 (old 1-0.9*breadth formula). Got {up}"
    )


# ---------------------------------------------------------------------------
# Log deduplication
# ---------------------------------------------------------------------------

def test_earliness_log_deduplication(tmp_path, monkeypatch):
    """Multiple runs on the same date produce only one row per (theme, asof)."""
    import engine.foresight_earliness as fe_mod
    from lib import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    (tmp_path / "foresight").mkdir(parents=True)

    themes_cfg = {"alpha": {"tickers": ["A"]}, "beta": {"tickers": ["B"]}}

    # patch all legs to simple values
    def _all_none(arg):
        return {k: None for k in (arg if isinstance(arg, dict) else arg)}

    monkeypatch.setattr(fe_mod, "_leg_coverage_arrival", _all_none)
    monkeypatch.setattr(fe_mod, "_leg_news_flow", lambda keys: {k: None for k in keys})
    monkeypatch.setattr(fe_mod, "_leg_ownership_breadth", _all_none)
    monkeypatch.setattr(fe_mod, "_leg_tape_extension", _all_none)

    fe.compute_foresight_earliness(themes_cfg=themes_cfg, write_log=True)
    fe.compute_foresight_earliness(themes_cfg=themes_cfg, write_log=True)  # re-run same day

    p = tmp_path / "foresight" / "earliness_log.jsonl"
    assert p.exists()
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    themes_logged = [r["theme"] for r in rows]
    # each theme appears exactly once despite two runs
    assert themes_logged.count("alpha") == 1, "alpha must appear exactly once (dedup)"
    assert themes_logged.count("beta") == 1, "beta must appear exactly once (dedup)"
