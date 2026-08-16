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


# --- store date key = the board's session, never the host clock -------------------
# DSC:NAME-SCORE-HAS-TWO-DISAGREEING-MEMORIES: until 2026-08-14 the US append was
# stamped pd.Timestamp.utcnow().date() at append time. The nightly's library band
# runs after 00:00 UTC, so session D's calls landed under calendar D+1 (plus Sat/Sun
# echo stamps from weekend lanes) and the store agreed with the published board on
# only 22-29% of names same-date — measured board(D) ≡ store(D+1), level match 1.000.
def test_us_name_score_stamp_is_board_session_not_wall_clock():
    from scripts import build_stock_library as bsl
    # the session anchor wins verbatim, regardless of what the host clock says
    assert bsl._name_score_asof("2026-08-13") == ("2026-08-13", True)
    # absent/corrupt anchor: loud wall-clock fallback, still an ISO date, and the
    # rows are marked session_keyed=False. Both calls sit INSIDE the before/after
    # clock bracket so a UTC-midnight crossing cannot flake the assertion.
    before = str(pd.Timestamp.utcnow().date())
    out_none = bsl._name_score_asof(None)
    out_bad = bsl._name_score_asof("not-a-date")
    after = str(pd.Timestamp.utcnow().date())
    assert out_none[0] in (before, after) and out_none[1] is False
    assert out_bad[0] in (before, after) and out_bad[1] is False


def test_us_store_stamp_wired_to_session_asof():
    """Wiring pin (mutation-proof): the single call-site line could be reverted to
    the wall-clock stamp and every behavioral test would stay green while the two
    memories of name_score diverged again. Pin the source, not just the helper."""
    from pathlib import Path
    from scripts import build_stock_library as bsl
    src = Path(bsl.__file__).read_text()
    us_append = src.index('append_name_calls(_calls, market="US", asof=_asof')
    stamp = src.rindex("_asof, _session_keyed = _name_score_asof(alpha_asof)", 0, us_append)
    # the session stamp is what feeds THIS append (no wall-clock stamp in between)
    assert "utcnow" not in src[stamp:us_append]


def test_sibling_store_stamps_use_session_anchor():
    """HK/CA/INTL shared the same wall-clock stamp defect; each append now passes
    its own session anchor with utcnow demoted to the fallback, and persists the
    session_keyed flag so a fallback row is marked in the store itself."""
    from pathlib import Path
    import scripts.build_stock_library as bsl
    root = Path(bsl.__file__).resolve().parent
    pins = {
        "build_hk_library.py": ['asof=str(as_of) if as_of else',
                                'session_keyed=bool(as_of)'],
        "build_canada_library.py": ['asof=str(_ca_asof) if _ca_asof else',
                                    'session_keyed=bool(_ca_asof)'],
        "build_intl_library.py": ['asof=_intl_asof, session_keyed=_intl_sk'],
    }
    for fname, want in pins.items():
        src = (root / fname).read_text()
        for pin in want:
            assert pin in src, f"{fname}: name-score append lost its session anchor ({pin})"
        # no append passes a bare wall-clock stamp any more
        assert "asof=str(pd.Timestamp.utcnow().date())" not in src, fname


def test_intl_session_anchor_resolves_without_alpha_as_of():
    """Adversarial review D1 (PR #5674): compute_intl_alpha carries NO as_of key, so
    an `(alpha or {}).get("as_of")` anchor is ALWAYS None and a text pin on that
    expression is vacuous. The INTL anchor must genuinely resolve — from the library
    tip (max per-rec asof) — and only mark session_keyed=False when nothing does."""
    from scripts.build_intl_library import _intl_session_asof
    # the real alpha shape: per_ticker/markets/n, no as_of anywhere
    alpha = {"per_ticker": {"X": {}}, "markets": {}, "n": 1}
    to_write = [("a", {"asof": "2026-08-12"}), ("b", {"asof": "2026-08-13"}),
                ("c", {"asof": None}), ("d", {})]
    assert _intl_session_asof(alpha, to_write) == ("2026-08-13", True)
    # a future alpha as_of, if one ever appears, outranks the tip
    assert _intl_session_asof({"as_of": "2026-08-11"}, to_write) == ("2026-08-11", True)
    # nothing resolves -> wall-clock, marked as such
    before = str(pd.Timestamp.utcnow().date())
    out = _intl_session_asof(None, [("x", {})])
    after = str(pd.Timestamp.utcnow().date())
    assert out[0] in (before, after) and out[1] is False


def test_append_persists_session_keyed_and_unions_legacy_rows(tmp_path, monkeypatch):
    """The cutover marker: post-fix rows carry session_keyed True/False; rows written
    before the column existed read back as null (the wall-clock era). Consumers must
    partition on this before comparing forward metrics across 2026-08-14 (the fill
    convention moved one session — adversarial review D3/D5, PR #5674)."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    # a legacy store WITHOUT the column (pre-cutover shape)
    legacy = pd.DataFrame({"date": ["2026-08-01"], "ticker": ["OLD"], "score": [5],
                           "tier": ["watch"], "fuel": [0.1], "trigger": [0.1],
                           "level": [10.0]})
    (tmp_path / "name_score").mkdir()
    legacy.to_parquet(tmp_path / "name_score" / "us_calls.parquet", index=False)
    call = [{"ticker": "NEW", "score": 50, "tier": "watch", "fuel": 0.5,
             "trigger": 0.5, "level": 20.0}]
    assert gr.append_name_calls(call, market="US", asof="2026-08-14") == 2
    assert gr.append_name_calls([{**call[0], "ticker": "WC"}], market="US",
                                asof="2026-08-15", session_keyed=False) == 3
    df = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    by = df.set_index("ticker")["session_keyed"]
    assert bool(by["NEW"]) is True and bool(by["WC"]) is False
    assert pd.isna(by["OLD"])                     # pre-cutover era stays null


def test_stamp_gap_cadence_uses_trailing_window(tmp_path, monkeypatch):
    """Adversarial review D2 (PR #5674): the store's HISTORY contains Sat/Sun stamps
    from the wall-clock era, but post-cutover the ledger is weekday-cadence. An
    all-history dow set would flag every future weekend as a PIT gap forever,
    saturating stamp_gap_dates[:14] until a real missed weekday could never surface.
    Cadence must come from the trailing window so the dead era ages out."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    sdir = tmp_path / "stocks"
    sdir.mkdir(parents=True)
    bars = pd.date_range("2026-06-01", periods=120, freq="D")
    pd.DataFrame({"close": [100.0 + 0.1 * j for j in range(len(bars))]},
                 index=bars).to_parquet(sdir / "T1.parquet")
    # wall-clock era: two weekend stamps; then > _GAP_DOW_WINDOW weekday stamps
    # (Mon-Fri over 4+ weeks) spanning several weekends, with ONE weekday missing.
    era_wall = ["2026-06-06", "2026-06-07"]                      # Sat, Sun
    weekdays = [str(d.date()) for d in pd.date_range("2026-06-08", "2026-07-03", freq="B")]
    missing = weekdays.pop(8)                                    # one real PIT gap
    rows = [{"date": d, "ticker": "T1", "score": 10, "tier": "watch", "fuel": 0.5,
             "trigger": 0.2, "level": 100.0 + i}                 # levels vary — no echoes
            for i, d in enumerate(era_wall + weekdays)]
    (tmp_path / "name_score").mkdir()
    pd.DataFrame(rows).to_parquet(tmp_path / "name_score" / "us_calls.parquet", index=False)
    out = gr.grade("US")
    assert out["available"] is True
    gaps = set(out["stamp_gap_dates"])
    assert missing in gaps                                       # real weekday gap surfaces
    # no weekend inside the scan range is counted once the trailing window is weekday-only
    assert not any(pd.Timestamp(g).dayofweek >= 5 for g in gaps), gaps


def test_producer_relationship_store_row_equals_published_potential(tmp_path, monkeypatch):
    """The intended end-to-end relationship the divergence receipt asked for: the
    store row for (session, ticker) carries the SAME score the board publishes,
    under the SAME date key the snapshot fossil uses (wide["as_of"])."""
    from scripts import build_stock_library as bsl
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    session = "2026-08-13"
    pot = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=1.0)
    rec = {"asof": session, "tech": {"price": 42.5}, "conviction": {"potential": pot}}
    calls = bsl._collect_potential_calls([("t", rec)])
    stamp, keyed = bsl._name_score_asof(session)
    assert gr.append_name_calls(calls, market="US", asof=stamp, session_keyed=keyed) == 1
    stored = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    assert stored["date"].tolist() == [session]          # session key, not run date
    assert int(stored["score"].iloc[0]) == pot["score"]  # published == stored
    assert bool(stored["session_keyed"].iloc[0]) is True # cutover marker persisted


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


# --- us_calls ledger-integrity disclosures (2026-08-03 adjudication follow-up) ----
def test_append_discloses_universe_shrink_without_blocking(tmp_path, monkeypatch, capsys):
    """2026-07-25: the weekly lane stamped 1,704 US names between 2,966-name nightly
    stamps (its runner restored no russell cache) and nothing surfaced — keep-FIRST
    PIT makes such a stamp permanently thin. An adjacent-stamp collapse (>20%) is
    disclosed as a line-start GitHub annotation at the write; admission is NEVER
    refused for coverage (a thin stamp still beats a missing one)."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)

    def batch(n, off=0):
        return [{"ticker": f"T{i:03d}", "score": 10, "tier": "watch", "fuel": 0.5,
                 "trigger": 0.2, "level": 50.0 + i + off} for i in range(n)]

    assert gr.append_name_calls(batch(40), market="US", asof="2026-07-22") == 40
    capsys.readouterr()
    # collapse 40 -> 20: disclosed, and every row still lands (no coverage gate)
    assert gr.append_name_calls(batch(20, off=100), market="US", asof="2026-07-25") == 60
    out = capsys.readouterr().out
    line = next((ln for ln in out.splitlines() if "universe shrink" in ln), "")
    assert line.startswith("::warning")            # annotation law: bare line-start print
    assert "admits 20 names vs 40 on 2026-07-22" in line
    # recovery and ordinary drift never warn (36 vs 40 = -10%, inside the band)
    gr.append_name_calls(batch(40, off=200), market="US", asof="2026-07-26")
    gr.append_name_calls(batch(36, off=300), market="US", asof="2026-07-27")
    assert "universe shrink" not in capsys.readouterr().out
    # same-day re-run of the thin stamp: first write already disclosed — silent
    gr.append_name_calls(batch(20, off=400), market="US", asof="2026-07-25")
    assert "universe shrink" not in capsys.readouterr().out
    # a young/tiny ledger (prev stamp under the floor) never warns
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path / "young")
    gr.append_name_calls(batch(10), market="HK", asof="2026-07-22")
    gr.append_name_calls(batch(3, off=50), market="HK", asof="2026-07-23")
    assert "universe shrink" not in capsys.readouterr().out


def test_universe_missing_or_unreadable_source_annotates(tmp_path, monkeypatch, capsys):
    """universe() used to skip a missing/corrupt breadth source group with a
    logger-only warning — invisible in Actions (the repo annotation law: GitHub
    silently drops logger-prefixed ::warning lines). The skip must be a bare
    line-start annotation so a lane assembling a shrunken universe says so."""
    from scripts import build_stock_library as bsl
    monkeypatch.setattr(bsl.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bsl.config, "load", lambda: {
        "yahoo": {"tickers": {"sectors": [], "extras": []}}, "stock_search": {}})
    # breadth present-but-corrupt (both files exist, unreadable); other three absent
    bdir = tmp_path / "breadth"
    bdir.mkdir()
    (bdir / "_closes_cache.parquet").write_bytes(b"not a parquet")
    (bdir / "constituents.parquet").write_bytes(b"also not a parquet")
    out_universe = bsl.universe()
    assert out_universe == []
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::warning")]
    unreadable = [ln for ln in lines if "universe source unreadable" in ln and "breadth" in ln]
    missing = [ln for ln in lines if "universe source missing" in ln]
    assert len(unreadable) == 1
    assert len(missing) == 3            # smallcap_breadth, midcap_breadth, russell_breadth
    assert all(ln.startswith("::warning") for ln in lines)


def test_grade_discloses_ic_cross_section_and_pit_stamp_gaps(tmp_path, monkeypatch):
    """The rank-IC denominators must be self-disclosing: per-date graded cross-section
    (today bounded by the deep-store subset, so a thin display stamp moves nothing —
    if store coverage ever widens, min << max is the tell) and PIT stamp gaps (US
    2026-07-13/23/24 vanished with the wedged nightlies and can never be backfilled).
    Gap detection is cadence-aware: only weekdays this ledger has stamped count, so
    the weekday-only CN ledger never miscounts weekends."""
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    sdir = tmp_path / "stocks"
    sdir.mkdir(parents=True)
    bars = pd.date_range("2026-06-25", periods=45, freq="D")
    for i, t in enumerate(["G1", "G2", "G3", "G4", "G5"]):
        pd.DataFrame({"close": [100.0 + 10 * i + 0.1 * j for j in range(len(bars))]},
                     index=bars).to_parquet(sdir / f"{t}.parquet")
    # stamps Wed 07-01, Thu 07-02, Thu 07-09 -> stamped weekdays {Wed, Thu}: the
    # missing Wed 07-08 is a PIT gap; the interior Fri..Tue are not (never-stamped dows)
    rows = []
    for di, d in enumerate(("2026-07-01", "2026-07-02", "2026-07-09")):
        for i, t in enumerate(["G1", "G2", "G3", "G4", "G5"]):
            rows.append({"date": d, "ticker": t, "score": 10 + 10 * i, "tier": "watch",
                         "fuel": 0.5, "trigger": 0.2,
                         "level": 100.0 + i + 0.31 * di})   # levels vary — no echo runs
    (tmp_path / "name_score").mkdir()
    pd.DataFrame(rows).to_parquet(tmp_path / "name_score" / "us_calls.parquet", index=False)
    out = gr.grade("US")
    assert out["available"] is True
    assert out["n_stamp_gaps"] == 1 and out["stamp_gap_dates"] == ["2026-07-08"]
    h21 = out["by_horizon"]["21d"]
    assert h21["n_ic_dates"] == 3
    assert h21["ic_cross_section"] == {"min": 5, "median": 5, "max": 5}
