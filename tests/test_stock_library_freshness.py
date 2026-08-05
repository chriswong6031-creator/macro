"""Scan-side feed-freshness demotion (scripts/build_stock_library.py::_feed_freshness /
_apply_feed_demotion) — research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md
rulings R1/R2.

A full rec whose own `asof` lags the library's own max tip by more than the SAME
7-calendar-day law the ledger admission gate already enforces
(engine.name_score_grader._MAX_BAR_LAG_DAYS) loses scoring authority but keeps its
page — CTRA/TPH/TCNNF/CWEN-A were frozen for weeks and still stamped as live
authority before this gate existed. No network; every rec here is a hand-built dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_score as ss  # noqa: E402
from engine import stock_view as sv  # noqa: E402
from scripts import build_stock_library as bsl  # noqa: E402


def _full(ticker: str, asof: str, *, score: int = 55) -> dict:
    """A minimal FULL rec — enough for _feed_freshness + _apply_feed_demotion +
    _collect_potential_calls to all operate on it."""
    return {
        "ticker": ticker,
        "asof": asof,
        "tech": {"price": 42.5},
        "conviction": {"potential": {
            "score": score, "tier": "setting_up",
            "call": {"ticker": ticker, "score": score, "tier": "setting_up",
                     "fuel": 0.6, "trigger": 0.9},
        }},
    }


def _limited(ticker: str, asof: str) -> dict:
    return {"ticker": ticker, "asof": asof, "limited": True, "ladder": {"state": "LIMITED"}}


# ---------------------------------------------------------------------------
# _feed_freshness
# ---------------------------------------------------------------------------

def test_seven_days_kept_eight_days_demoted():
    """The boundary is STRICT >7 — exactly 7 calendar days behind stays live (the
    real NYSE-calendar worst case, per _MAX_BAR_LAG_DAYS's own docstring), 8 demotes."""
    recs = [
        _full("LIB", "2026-08-05"),   # sets the library tip
        _full("SEVEN", "2026-07-29"),  # exactly 7 days behind -> kept
        _full("EIGHT", "2026-07-28"),  # 8 days behind -> demoted
    ]
    # pad with fresh recs so the single demotion stays under the 20% breaker
    recs += [_full(f"FRESH{i}", "2026-08-05") for i in range(6)]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert "SEVEN" not in demoted
    assert demoted == {"EIGHT": 8}
    assert n_dark == 0


def test_crypto_led_max_tip_is_the_reference():
    """A 24/7 crypto tip a couple of days ahead of the equity pack becomes lib_asof —
    equities on the same weekday close then read as (correctly) a bit behind it,
    but still well inside the 7-day window."""
    recs = [
        _full("BTC-USD", "2026-08-05"),   # weekend tip, leads the pack
        _full("AAPL", "2026-08-03"),      # Friday close, 2 days behind -> kept
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}
    assert n_dark == 0


def test_unparseable_asof_is_fail_open_and_counted_dark():
    recs = [
        _full("LIB", "2026-08-05"),
        {**_full("GARBAGE", "not-a-date")},
        {**_full("MISSING", None)},
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert "GARBAGE" not in demoted and "MISSING" not in demoted
    assert n_dark == 2


def test_limited_recs_are_never_considered():
    """A LIMITED rec has no comparable asof depth (R1 invariant I4) — it must never
    move lib_asof and must never itself demote, however stale its own asof is."""
    recs = [
        _full("LIB", "2026-08-05"),
        _limited("BRANDNEW", "2020-01-01"),   # wildly "behind" but exempt
        None,                                  # a failed _one_task() entry
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}
    assert n_dark == 0


def test_circuit_breaker_disarms_above_20pct_and_warns(capsys):
    """21 full recs, 5 demoted (5/21 = 23.8% > 20%) -> gate disarms, empty map, and
    the disarm is disclosed with a bare ::warning naming the fraction (CSP-R1: a
    universe-wide freeze reads as a collector outage, not per-name staleness)."""
    recs = [_full("LIB", "2026-08-05")]
    for i in range(15):
        recs.append(_full(f"FRESH{i}", "2026-08-04"))   # 1 day behind -> kept
    for i in range(5):
        recs.append(_full(f"STALE{i}", "2026-07-20"))   # 16 days behind -> would demote
    assert len(recs) == 21
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}, "breaker must return an EMPTY map, never a partial one"
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert lines, "circuit breaker must print a bare ::warning"
    assert any("warning" in ln and "disarm" in ln.lower() for ln in lines)
    assert any("5/21" in ln for ln in lines) and any("24%" in ln for ln in lines)


def test_circuit_breaker_stays_armed_at_exactly_20pct():
    """20/100 demoting is AT the threshold, not over it — `> 0.20` must not trip
    on equality (an off-by-one here would disarm the gate one name early forever)."""
    recs = [_full("LIB", "2026-08-05")]
    for i in range(80):
        recs.append(_full(f"FRESH{i}", "2026-08-04"))
    for i in range(20):
        recs.append(_full(f"STALE{i}", "2026-07-20"))
    _, demoted, _ = bsl._feed_freshness(recs)
    assert len(demoted) == 20


# ---------------------------------------------------------------------------
# _apply_feed_demotion
# ---------------------------------------------------------------------------

def test_apply_feed_demotion_sets_feed_stale_and_strips_potential():
    rec = _full("CTRA", "2026-05-07")
    bsl._apply_feed_demotion(rec, 90, "2026-08-05")
    assert rec["feed_stale"] == {"behind_days": 90, "lib_asof": "2026-08-05"}
    assert "potential" not in rec["conviction"]
    # the rest of the rec (page-facing chips) is untouched (I1)
    assert rec["tech"]["price"] == 42.5
    assert rec["ticker"] == "CTRA"


def test_demoted_rec_yields_no_potential_calls():
    """I3: after demotion, _collect_potential_calls must emit nothing for the name —
    the grader's own bar_asof gate is only the SECOND line of defense."""
    rec = _full("TPH", "2026-05-13")
    bsl._apply_feed_demotion(rec, 84, "2026-08-05")
    live = _full("FRESH", "2026-08-05")
    calls = bsl._collect_potential_calls([("tph", rec), ("fresh", live)])
    tickers = {c["ticker"] for c in calls}
    assert "TPH" not in tickers
    assert "FRESH" in tickers


# ---------------------------------------------------------------------------
# B2 — adversarial-review fix: conviction.score must ALSO be cleared, or a demoted
# name renders a scale-mixed NN/100 "board rank" gauge next to the "not scored"
# banner (attach_panel_scores never touches it — the name is excluded from
# `profiles`). Verified through the REAL conviction_profile + build_view pipeline,
# not a fabricated conv shape, so a schema drift in either engine still catches this.
# ---------------------------------------------------------------------------

def test_apply_feed_demotion_clears_conviction_score():
    rec = _full("CTRA", "2026-05-07")
    bsl._apply_feed_demotion(rec, 90, "2026-08-05")
    assert rec["conviction"]["score"] is None


def _profiled_rec(**over) -> dict:
    """A rec run through the REAL engine.stock_score.conviction_profile pipeline —
    mirrors tests/test_stock_view.py's own fixture pattern, so `conv` has the true
    production shape (not a hand-picked subset that could hide a schema drift)."""
    base = {"ticker": "T", "name": "Test", "alpha": 1.4,
            "ladder": {"state": "RALLY ON", "label": "Uptrend",
                       "entry": {"tag": "HOLD", "urgency": "hold"}},
            "tech": {"above200": True, "pct_vs_200dma": 8.0, "rsi14": 55.0}}
    base.update(over)
    base["conviction"] = ss.conviction_profile(base, "US")
    return base


def test_demoted_rec_suppresses_score_gauge_and_rank_note_in_view():
    """B2 end-to-end: run a rec through the real conviction engine, apply the exact
    same demotion the build does, then verify build_view's decision carries no score
    and no rank_note (server side — this is what stockview.js's null-score guards
    ultimately consume) while the ACT-NOW lane (action/timing) survives untouched —
    a demoted name still gets a full page, just no numeric rank claim."""
    rec = _profiled_rec()
    assert rec["conviction"]["score"] is not None   # sanity: a live name HAS a score
    bsl._apply_feed_demotion(rec, 42, "2026-08-05")
    view = sv.build_view(rec, "US")
    d = view["decision"]
    assert d["score"] is None
    assert d["rank_note"] is None and d["rank_note_zh"] is None
    # not the close-only fallback — the ACT-NOW lane (buy-frame verb) still renders,
    # only the NAME lane's numeric rank claim is suppressed.
    assert d["action"] is not None


def test_live_rec_still_gets_score_gauge_and_rank_note():
    """Control: an ordinary (non-demoted) rec is unaffected by the B2 guard."""
    rec = _profiled_rec()
    view = sv.build_view(rec, "US")
    d = view["decision"]
    assert d["score"] is not None
    assert d["rank_note"] == "board rank" and d["rank_note_zh"] == "板内排名"


# ---------------------------------------------------------------------------
# B1 — adversarial-review fix: sig_verdict/cand are populated EARLIER in the main()
# loop than the profiles/entry_sig/risk_sig demotion branch, so a demoted ticker
# leaked into site/factordata/signal_gate.json (the discovery board's PRIMARY buy
# gate), the ran lane (us_board_rank.build_ran_rows iterates sig_verdict's keys
# directly), and setups.json's "Top setups" strip (via `cand`) despite already
# being excluded from every OTHER board. Full main() needs the whole nightly data
# surface to run, so this is a direct unit of the extracted predicate PLUS a
# source-level pin that both real call sites actually use it (the "however you
# structured it" unit — see _authority_admits' docstring for the two call sites).
# ---------------------------------------------------------------------------

def test_authority_admits_excludes_demoted_admits_everyone_else():
    demote_map = {"CTRA": 90, "TPH": 84}
    assert bsl._authority_admits("CTRA", demote_map) is False
    assert bsl._authority_admits("TPH", demote_map) is False
    assert bsl._authority_admits("AAPL", demote_map) is True
    assert bsl._authority_admits("AAPL", {}) is True


def test_sig_verdict_and_cand_population_gated_by_authority_admits():
    """Source-level regression pin: both leak sites (sig_verdict[ticker] = ...,
    cand.append(sc)) must be directly preceded by an `if _authority_admits(ticker,
    _demote_map):` guard — not just protected later via profiles/entry_sig/risk_sig,
    which does NOT stop either of these two collections from admitting a demoted
    name (that was exactly the adversarial-review finding: B1)."""
    lines = Path(bsl.__file__).read_text().splitlines()

    def _immediately_guarded(needle: str) -> bool:
        for i, ln in enumerate(lines):
            if needle in ln:
                j = i - 1
                while j >= 0 and (not lines[j].strip() or lines[j].strip().startswith("#")):
                    j -= 1
                # polarity-pinned: `if not _authority_admits(...)` must NOT pass
                return j >= 0 and lines[j].strip().startswith(
                    "if _authority_admits(ticker, _demote_map)")
        raise AssertionError(f"{needle!r} not found in {bsl.__file__}")

    assert _immediately_guarded("sig_verdict[ticker] = signal_gate.gate(ticker, close)")
    assert _immediately_guarded("cand.append(sc)")


# ---------------------------------------------------------------------------
# B3 — the gate must never abort the nightly build.
# ---------------------------------------------------------------------------

def test_feed_freshness_tz_aware_asof_does_not_raise():
    """A tz-aware asof string (e.g. carrying '+00:00') would TypeError at max()/
    subtraction against tz-naive peers without the tz-normalize fix — the whole
    nightly build would abort. Must not raise, and must classify sanely."""
    recs = [
        _full("LIB", "2026-08-05"),
        _full("TZAWARE", "2026-08-05T00:00:00+00:00"),
        _full("STALETZ", "2026-07-20T00:00:00+00:00"),
    ]
    # pad with fresh recs so the single demotion stays under the 20% breaker
    recs += [_full(f"FRESH{i}", "2026-08-05") for i in range(10)]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)   # must not raise
    assert lib_asof == "2026-08-05"
    assert n_dark == 0
    assert "TZAWARE" not in demoted
    assert demoted == {"STALETZ": 16}


def test_feed_freshness_gate_call_in_main_is_wrapped_fail_open():
    """B3(b) source-level regression pin (a re-implementation of the guard inside the
    test body would stay green if main()'s wrapper were deleted — mirrored-guard trap):
    the ONE `_feed_freshness(recs)` call site in main() must sit inside a try whose
    except prints the crashed-gate ::warning and resets to (None, {}, 0) — fail-open,
    never aborting the nightly build."""
    src = Path(bsl.__file__).read_text()
    call = src.index("_lib_asof, _demote_map, _n_dark = _feed_freshness(recs)")
    # fail-open defaults + try: open just before the call; the except recovers after it
    # (tuple unpack is atomic, so a raise leaves the pre-try (None, {}, 0) in place)
    before, after = src[max(0, call - 700):call], src[call:call + 2500]
    assert "_lib_asof, _demote_map, _n_dark = None, {}, 0" in before, \
        "fail-open defaults before the try wrapper are gone"
    assert "try:" in before, "the _feed_freshness(recs) call in main() lost its try wrapper"
    assert "except Exception" in after
    assert "::warning title=stock-library freshness gate crashed::" in after


# ---------------------------------------------------------------------------
# M1 — self-relative wall-clock blindness backstop (build_stock_library side).
# ---------------------------------------------------------------------------

def test_lib_tip_wall_clock_warning_fires_on_old_tip():
    warning = bsl._lib_tip_wall_clock_warning("2020-01-01")
    assert warning is not None
    assert warning.startswith("::warning title=stock-library tip stale::")
    assert "2020-01-01" in warning


def test_lib_tip_wall_clock_warning_silent_on_fresh_tip():
    today = str(pd.Timestamp.utcnow().tz_localize(None).date())
    assert bsl._lib_tip_wall_clock_warning(today) is None


def test_lib_tip_wall_clock_warning_silent_on_none_or_garbage():
    assert bsl._lib_tip_wall_clock_warning(None) is None
    assert bsl._lib_tip_wall_clock_warning("not-a-date") is None


# ---------------------------------------------------------------------------
# M2 — breaker denominator must be the ASSESSABLE population (parsed asof), not
# `full` (which dark recs pad). The reviewer's named failure scenario: a run that
# is 30% dark and 25%-of-PARSED frozen must trip the breaker — under the old
# len(full) denominator it would NOT have (18/100 = 18% < 20%).
# ---------------------------------------------------------------------------

def test_breaker_denominator_is_parsed_not_full():
    recs = [_full("LIB", "2026-08-05")]
    recs += [_full(f"FRESH{i}", "2026-08-04") for i in range(51)]   # fresh, parsed
    recs += [_full(f"STALE{i}", "2026-07-01") for i in range(18)]   # 35d behind -> demote
    recs += [{**_full(f"DARK{i}", "2026-08-05"), "asof": "not-a-date"} for i in range(30)]
    assert len(recs) == 100
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert n_dark == 30
    parsed_n = 100 - 30   # 70
    assert 18 / parsed_n > 0.20            # would trip under the NEW (parsed) denominator
    assert 18 / 100 < 0.20                 # would NOT have tripped under the OLD (full) one
    assert demoted == {}, "breaker must trip using len(parsed), not len(full)"
