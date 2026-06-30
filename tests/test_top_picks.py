"""Tests for engine.top_picks — the holistic Top-Picks conviction score.

Covers the validated alpha-led blend weights, the sector-neutral confirmation tilt,
the "missing fundamentals are neutral, never penalised" rule, the entry-axis labels,
and the core design claim: among equal-alpha names, fundamental confirmation lifts the
rank — while a name with no confirmation ranks exactly as alpha alone would.
"""
from pytest import approx

from engine.top_picks import (ALPHA_W, MIN_TILT_LEGS, TILT_W, band,
                              compute_scores, entry_meta)


def _row(ticker, alpha, sector="Tech", **legs):
    r = {"ticker": ticker, "alpha": alpha, "sector": sector}
    r.update(legs)
    return r


# ---- validated weights ------------------------------------------------------

def test_validated_blend_weights():
    # the construction validated in reports/top-picks-phase0.md: alpha-led 0.6 / 0.4
    assert ALPHA_W == 0.6
    assert TILT_W == 0.4
    assert ALPHA_W + TILT_W == approx(1.0)


# ---- band -------------------------------------------------------------------

def test_band_thresholds():
    assert band(1.5) == "strong"
    assert band(0.5) == "leader"
    assert band(0.0) == "mid"
    assert band(-0.5) == "lag"
    assert band(-1.5) == "deeplag"
    assert band(None) == "mid"
    assert band(float("nan")) == "mid"


# ---- entry axis -------------------------------------------------------------

def test_entry_meta_is_trend_context_not_a_buy_call():
    # entry_meta is now (en, zh, css) trend-position CONTEXT — NOT a buy flag. The buy call is
    # the confluence gate (engine/signal_gate); a "pullback" no longer reads "Buy zone".
    en, zh, css = entry_meta("pullback")
    assert en == "Pullback" and css == "tp-pullback"   # constructive context, not "Buy zone"
    en, zh, css = entry_meta("extended")
    assert en == "Extended" and css == "tp-extended"
    assert entry_meta("intact")[0] == "In trend"
    assert entry_meta(None)[0] == "Neutral"            # missing -> neutral
    # the 3-tuple no longer carries a buy_zone boolean (nothing keys "buy" off the trend read)
    assert all(len(entry_meta(t)) == 3 for t in ("pullback", "extended", "intact", "laggard", None))


# ---- compute_scores: structure ---------------------------------------------

def test_no_alpha_names_are_dropped():
    rows = [_row("A", 1.0, profitability=1.0, value=1.0),
            _row("B", None, profitability=2.0, value=2.0)]
    out = compute_scores(rows)
    assert "A" in out and "B" not in out      # nothing to rank without alpha


def test_missing_confirmation_is_neutral_not_penalised():
    # BARE has NO confirmation legs; others do (so the leg columns exist). BARE's tilt
    # must be 0 -> its score is exactly ALPHA_W*alpha, the same ORDER as alpha alone.
    rows = [_row("BARE", 1.0),
            _row("C", 0.5, profitability=1.0, value=1.0),
            _row("D", 0.4, profitability=-1.0, value=-1.0)]
    out = compute_scores(rows)
    assert out["BARE"]["conviction_z"] == 0.0
    assert out["BARE"]["n_legs"] == 0
    assert out["BARE"]["top_score"] == approx(round(ALPHA_W * 1.0, 3))


def test_too_few_legs_is_neutral():
    # one leg present (< MIN_TILT_LEGS) -> conviction forced neutral
    assert MIN_TILT_LEGS == 2
    rows = [_row("A", 1.0, profitability=2.0),
            _row("B", 1.0, profitability=-2.0)]
    out = compute_scores(rows)
    assert out["A"]["conviction_z"] == 0.0 and out["A"]["n_legs"] == 1
    assert out["A"]["top_score"] == approx(round(ALPHA_W * 1.0, 3))


# ---- compute_scores: the core design claim ---------------------------------

def test_confirmation_lifts_equal_alpha_name():
    # two leaders with IDENTICAL alpha; the one with strong positive confirmation
    # (cheap, profitable, insider buying) must outrank the one with weak fundamentals.
    rows = [
        _row("GOOD", 1.0, profitability=2.0, value=1.5, quality=1.0, insider=1.0),
        _row("WEAK", 1.0, profitability=-2.0, value=-1.5, quality=-1.0, insider=-1.0),
    ]
    out = compute_scores(rows)
    assert out["GOOD"]["conviction_z"] > 0 > out["WEAK"]["conviction_z"]
    assert out["GOOD"]["top_score"] > out["WEAK"]["top_score"]
    # alpha stays the dominant leg: the gap is bounded by the 0.4 tilt weight
    assert out["GOOD"]["top_score"] - out["WEAK"]["top_score"] <= TILT_W * 6 + 1e-9


def test_alpha_still_dominates_confirmation():
    # a much higher alpha beats a lower-alpha name even with better confirmation
    rows = [
        _row("HIA", 2.5, profitability=-1.0, value=-1.0),
        _row("LOA", 0.5, profitability=2.0, value=2.0),
    ]
    out = compute_scores(rows)
    assert out["HIA"]["top_score"] > out["LOA"]["top_score"]


# ---- compute_scores: sector neutrality -------------------------------------

def test_confirmation_is_sector_neutral():
    # identical RAW profitability (1.0), but Tech's sector mean is high and Energy's is
    # low -> within-sector the Tech name is BELOW its peers (negative) and the Energy
    # name ABOVE its peers (positive). Sector-neutralisation must flip their tilt signs.
    rows = [
        _row("TECH_MID", 1.0, sector="Tech", profitability=1.0, value=1.0),
        _row("TECH_HI", 1.0, sector="Tech", profitability=3.0, value=3.0),
        _row("TECH_HI2", 1.0, sector="Tech", profitability=3.0, value=3.0),
        _row("ENGY_MID", 1.0, sector="Energy", profitability=1.0, value=1.0),
        _row("ENGY_LO", 1.0, sector="Energy", profitability=-3.0, value=-3.0),
        _row("ENGY_LO2", 1.0, sector="Energy", profitability=-3.0, value=-3.0),
    ]
    out = compute_scores(rows)
    # same raw 1.0, opposite sign once sector-neutralised
    assert out["TECH_MID"]["conviction_z"] < 0 < out["ENGY_MID"]["conviction_z"]


def test_empty_input():
    assert compute_scores([]) == {}
    assert compute_scores([{"ticker": "X"}]) == {}   # no alpha key -> dropped
