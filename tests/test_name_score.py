"""Market-aware per-name POTENTIAL score (engine/name_score) + the multi-market grader.

Pins the cross-market design: the trigger gates the tier in EVERY market (front-running),
fuel sizes within it, and the per-market edge blend PRESERVES each market's validated
selection edge (US event edge; CN/HK none) without ever overriding the timing gate.
"""
import pandas as pd

from engine import name_score as ns
from engine import name_score_grader as gr


def _rec(state, *, off_high=-28.0, vs200=-10.0, rsi=52.0, entry="buy_now", ticker="T"):
    return {"ticker": ticker,
            "ladder": {"state": state, "label": state.title(), "entry": {"urgency": "now"}},
            "tech": {"off_52w_high_pct": off_high, "pct_vs_200dma": vs200, "rsi14": rsi},
            "entry_signal": {"status": entry},
            "anticipation": {"anticipation_index": 55.0,
                             "horizons": {"medium": {"mfe_med": 7.0, "dd_avg": -8.0}}}}


# --- the US edge blend (preserve validated alpha) -------------------------------
def test_us_edge_blend_boosts_and_trims():
    base = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=0.0)
    boosted = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=1.6)   # insider buying
    against = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=-1.6)  # insider selling
    assert boosted["score"] > base["score"] > against["score"]
    assert boosted["components"]["edge"] > 1.0 and against["components"]["edge"] < 1.0


def test_cn_and_hk_ignore_edge():
    # CN reversal edge lives in the washout/cycle; HK has no validated name edge -> edge_mult=1
    for mkt in ("CN", "HK"):
        a = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=2.5)
        b = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=-2.5)
        assert a["score"] == b["score"]
        assert a["components"]["edge"] == 1.0


def test_ca_blend_is_lighter_than_us():
    z = 2.0
    us = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=z)["components"]["edge"]
    ca = ns.potential_score(_rec("FRESH BUY"), market="CA", edge_z=z)["components"]["edge"]
    assert 1.0 < ca < us                       # CA momentum prior weighted less than the US event edge


# --- the trigger gate dominates the edge in EVERY market (front-running) ---------
def test_declining_name_gated_out_despite_strong_edge():
    # the AAPL-in-DECLINE case: a great edge can't make a falling name a buy.
    p = ns.potential_score(_rec("DECLINE", off_high=-12.0, vs200=2.0, entry="hold"),
                           market="US", edge_z=2.0)
    assert p["score"] <= 5 and p["tier"] == "no_setup"


def test_washed_out_turning_is_primed_all_markets():
    for mkt in ("US", "CN", "HK", "CA", "INTL"):
        p = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=0.3)
        assert p["tier"] in ("primed", "setting_up") and p["band"] in ("high", "constructive")


def test_bounce_wait_scores_exactly_as_legacy_extended():
    """The COUNTERTREND BOUNCE wording split (entry_signal 'bounce_wait', formerly
    'extended') must move NO published score: the 0.50 confirm weight is kept
    deliberately, and an unmapped key would silently default to 1.0 and double it."""
    assert ns._ENTRY_CONFIRM["bounce_wait"] == ns._ENTRY_CONFIRM["extended"] == 0.50
    bounce = ns.potential_score(_rec("COUNTERTREND BOUNCE", entry="bounce_wait"),
                                market="CN", edge_z=0.0)
    legacy = ns.potential_score(_rec("COUNTERTREND BOUNCE", entry="extended"),
                                market="CN", edge_z=0.0)
    assert bounce["score"] == legacy["score"]


# --- the ORCL 2026-07 flatline: a flat constant is a REGIME, not a stuck input ---
def test_deep_washout_decline_is_flat_saturation_not_frozen():
    """Chip 2026-08-03 (MAG7 postmortem §2 / us_calls row): ORCL printed score=0
    fuel=1.000 trigger=0.000 for 29 straight ledger stamps (23 trading sessions,
    2026-06-29 → 07-30) while crashing −55%…−61% off its high. Re-measured: that
    flat constant is the DESIGNED saturation zone —
    both fuel legs clip at their caps (−35% off-high / −20% vs-200dma) and DECLINE
    gates the trigger to exactly 0 — with a live, moving feed (7 names shared the
    regime). Pin the zone AND the exit: the session the ladder leaves DECLINE the
    printed trigger must move (ORCL 07-31: 0.00 → 0.15)."""
    knife = ns.potential_score(_rec("DECLINE", off_high=-55.0, vs200=-27.0, entry="hold"),
                               market="US", edge_z=0.0)
    assert knife["score"] == 0 and knife["tier"] == "no_setup"
    assert knife["components"]["fuel"] == 1.0      # both legs saturated at the caps
    assert knife["components"]["trigger"] == 0.0   # DECLINE gates to exactly 0
    bounce = ns.potential_score(
        _rec("COUNTERTREND BOUNCE", off_high=-60.0, vs200=-29.0, entry="bounce_wait"),
        market="US", edge_z=0.0)
    assert bounce["components"]["trigger"] == 0.15  # 0.30 × bounce_wait 0.50 — the 07-31 print
    assert bounce["score"] > 0


# --- the multi-market grader ----------------------------------------------------
def test_grader_market_paths_and_keep_first(tmp_path, monkeypatch):
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    us = [{"ticker": "AAPL", "score": 80, "tier": "primed", "fuel": 0.7, "trigger": 1.0, "level": 200.0}]
    assert gr.append_name_calls(us, market="US", asof="2026-06-28") == 1
    assert gr.append_name_calls([{**us[0], "score": 1}], market="US", asof="2026-06-28") == 1  # keep-first
    # US writes to the name_score/<mkt> path; CN keeps its legacy china_name_score path
    assert (tmp_path / "name_score" / "us_calls.parquet").exists()
    gr.append_name_calls([{"ticker": "600030.SS", "score": 70, "tier": "watch",
                           "fuel": 0.5, "trigger": 0.5, "level": 27.0}], market="CN", asof="2026-06-28")
    assert (tmp_path / "china_name_score" / "calls.parquet").exists()
    df = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    assert int(df.iloc[0]["score"]) == 80                # original not overwritten
    assert gr.grade("US")["available"] is True
    assert gr.grade("HK")["available"] is False          # nothing logged for HK


def test_grader_refuses_frozen_feed_calls(tmp_path, monkeypatch):
    """SATS 2026-06/07: its price store died 2026-06-18 but the nightly scan kept
    stamping byte-identical 'calls' into the PIT ledger daily (33 fictional rows).
    A call whose own last bar lags the ledger stamp by more than the closure-safe
    window is a dead-feed echo — refused at admission. Callers that pass no
    bar_asof stay un-gated, and bar_asof itself is never persisted."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    calls = [
        {"ticker": "FRESH", "score": 10, "tier": "watch", "fuel": 0.5, "trigger": 0.2,
         "level": 50.0, "bar_asof": "2026-07-31"},   # Fri bar on a Mon stamp (lag 3) — kept
        {"ticker": "EDGE", "score": 10, "tier": "watch", "fuel": 0.5, "trigger": 0.2,
         "level": 50.0, "bar_asof": "2026-07-27"},   # exactly 7d — kept (closure-safe)
        {"ticker": "DEAD", "score": 0, "tier": "no_setup", "fuel": 0.4, "trigger": 0.0,
         "level": 109.17, "bar_asof": "2026-06-18"},  # the SATS shape — refused
        {"ticker": "LEGACY", "score": 10, "tier": "watch", "fuel": 0.5, "trigger": 0.2,
         "level": 50.0},                             # no bar_asof — un-gated
    ]
    n = gr.append_name_calls(calls, market="US", asof="2026-08-03")
    df = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    assert n == 3 and sorted(df["ticker"]) == ["EDGE", "FRESH", "LEGACY"]
    assert "bar_asof" not in df.columns              # ledger schema unchanged


def test_grader_gate_never_dark_silently(tmp_path, monkeypatch, caplog):
    """An unusable bar_asof (NaT / garbage / future clock anomaly) must keep the
    call (fail-open — a format drift may never silently delete ledger coverage)
    but must SURFACE: the gate going dark is itself a warned condition."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    calls = [
        {"ticker": "NATBAR", "score": 5, "tier": "watch", "fuel": 0.5, "trigger": 0.1,
         "level": 10.0, "bar_asof": pd.NaT},         # NaT — kept, warned
        {"ticker": "GARBAGE", "score": 5, "tier": "watch", "fuel": 0.5, "trigger": 0.1,
         "level": 10.0, "bar_asof": ["not-a-date"]},  # unparseable — kept, warned
        {"ticker": "FUTURE", "score": 5, "tier": "watch", "fuel": 0.5, "trigger": 0.1,
         "level": 10.0, "bar_asof": "2026-08-20"},   # bar after stamp — kept, warned
    ]
    import logging
    with caplog.at_level(logging.WARNING, logger="engine.name_score_grader"):
        n = gr.append_name_calls(calls, market="US", asof="2026-08-03")
    df = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    assert n == 3 and sorted(df["ticker"]) == ["FUTURE", "GARBAGE", "NATBAR"]
    assert any("gate DARK" in r.message for r in caplog.records)


def test_us_emitter_passes_bar_asof():
    """Producer half of the frozen-feed gate (mutation-proof: without this, the
    single `bar_asof` token in the builder's call assembly could be deleted and
    every test would stay green while the gate went permanently dark)."""
    from scripts import build_stock_library as bsl
    rec = {"asof": "2026-08-01", "tech": {"price": 42.5},
           "conviction": {"potential": {"call": {"ticker": "T", "score": 55,
                                                 "tier": "setting_up", "fuel": 0.6,
                                                 "trigger": 0.9}}}}
    bare = {"asof": "2026-08-01", "conviction": {}}          # no potential — skipped
    calls = bsl._collect_potential_calls([("t", rec), ("b", bare)])
    assert len(calls) == 1
    assert calls[0]["bar_asof"] == "2026-08-01" and calls[0]["level"] == 42.5
    assert calls[0]["ticker"] == "T" and calls[0]["score"] == 55


# --- grade()-side quarantine: pre-gate frozen echoes never reach measurement -----
def test_grade_quarantines_frozen_echo_runs(tmp_path, monkeypatch):
    """98 fabricated rows (18 buy-tier, e.g. QCOM `setting_up` 63 off a 24d-stale
    store) predate the admission gate. If the store later heals/backfills, grading
    would credit real forward returns to fabricated calls. A byte-identical level
    run older than the closure-safe window is excluded from measurement — the PIT
    ledger itself is never mutated — and the count is PRINTED (disclosure law)."""
    dates = [f"2026-07-{d:02d}" for d in range(1, 13)]
    frozen = pd.DataFrame({"date": dates, "ticker": "FRZ", "score": 63,
                           "tier": "setting_up", "fuel": 0.5, "trigger": 0.9,
                           "level": 108.42})                  # 12 stamps, one level
    weekend = pd.DataFrame({"date": ["2026-07-10", "2026-07-11", "2026-07-12"],
                            "ticker": "WKND", "score": 10, "tier": "watch",
                            "fuel": 0.5, "trigger": 0.2, "level": 55.0})  # Fri..Sun
    kept, n = gr._drop_frozen_echoes(pd.concat([frozen, weekend], ignore_index=True))
    # FRZ run starts 07-01: stamps 07-09..07-12 sit >7d deep — 4 echoes; WKND intact
    assert n == 4
    assert (kept[kept.ticker == "FRZ"]["date"].max() == "2026-07-08"
            and len(kept[kept.ticker == "WKND"]) == 3)
    # NaN levels never quarantine
    nan_rows = pd.DataFrame({"date": dates, "ticker": "NOLVL", "score": 1,
                             "tier": "watch", "fuel": 0.1, "trigger": 0.1,
                             "level": float("nan")})
    _, n2 = gr._drop_frozen_echoes(nan_rows)
    assert n2 == 0
    # end-to-end: grade() prints the exclusion count
    p = tmp_path / "name_score"
    p.mkdir(parents=True)
    pd.concat([frozen, weekend], ignore_index=True).to_parquet(p / "us_calls.parquet",
                                                               index=False)
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    out = gr.grade("US")
    assert out["available"] is True and out["n_frozen_excluded"] == 4
    assert out["n_calls"] == 11                    # 15 rows − 4 quarantined
