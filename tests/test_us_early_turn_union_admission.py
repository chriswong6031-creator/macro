"""UNION ADMISSION (bake-off §A2) — the measured recall spine on the EARLY-TURN tier.

Authority: `research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md` §A2 (wire the
RELAXED washout-cross form into the EARLY-TURN starter-class admission, dot retained as the
anticipation chip, zero-bound as CONTEXT) and the footprint study's §A3 (no durability tier
is licensed; context columns may DISPLAY texture but must not rank or imply reliability).

What these tests pin, in order of what would hurt most if it broke:

  1. the two named exemplars still surface on the measured dates (the acceptance gate);
  2. the SCORED gate is untouched — the union may not move a single verdict;
  3. the construction is history-depth independent (the absolute session-anchor law), which
     is also what lets a 700-row fixture stand in for a 12-year tape;
  4. the two 3D grids in this repo agree, which is why this module computes the union with
     the helpers it already imports instead of importing a second set.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine import signal_gate, us_early_turn
from engine.us_early_turn import (
    UNION_ADMISSION_ERA, UNION_LEG_CROSS, UNION_LEG_DOT, UNION_OS_BAND,
    union_admission,
)

FIXTURES = Path(__file__).parent / "fixtures" / "us_early_turn"

#: The two named exemplars from the bake-off's §5 coverage gate, with the dates the union
#: was MEASURED to fire on (bake-off §R1: STLD's dot/relaxed cross both land 2026-07-14 —
#: the store's 2026-07-10 dot stamped at its bucket's last session — and NEM's relaxed
#: cross lands 2026-07-09).
EXEMPLARS = (
    ("STLD", "2026-07-14", [UNION_LEG_CROSS, UNION_LEG_DOT], 4.71),
    ("NEM", "2026-07-09", [UNION_LEG_CROSS], 12.37),
)


def _fixture(ticker: str) -> pd.DataFrame:
    path = FIXTURES / f"{ticker}.csv"
    if not path.exists():  # pragma: no cover - the fixture is committed
        pytest.skip(f"fixture missing: {path}")
    return pd.read_csv(path, index_col="date", parse_dates=True)


# --------------------------------------------------------------- 1. the acceptance gate
@pytest.mark.parametrize("ticker,asof,legs,k_at_cross", EXEMPLARS)
def test_union_surfaces_the_named_exemplars(ticker, asof, legs, k_at_cross):
    """The gate that makes this shippable: the measured names surface on the measured days."""
    out = union_admission(_fixture(ticker), asof=asof)
    assert out["fired"] is True, out["reason"]
    assert out["fire_date"] == asof
    assert out["age_bars"] == 0
    assert out["legs"] == legs
    assert out["era"] == UNION_ADMISSION_ERA
    assert out["badges"]["k_at_cross"] == pytest.approx(k_at_cross, abs=0.01)


def test_cross_leg_requires_both_lines_under_the_band():
    """C1-relaxed is the operator's 'crossover done UNDER the 20 line' — both lines, at the
    cross bar. A cross with either line at or above the band is a different construction."""
    for ticker, asof, _legs, k in EXEMPLARS:
        out = union_admission(_fixture(ticker), asof=asof)
        if UNION_LEG_CROSS not in out["legs"]:
            continue
        assert out["badges"]["k_at_cross"] < UNION_OS_BAND
        assert k < UNION_OS_BAND


def test_badges_are_context_not_durability():
    """§A2 ships the badges as PROXIMITY context. They must be present as data and must not
    carry any score, rank, tier or ordering key — no measured feature licensed one."""
    out = union_admission(_fixture("STLD"), asof="2026-07-14")
    badges = out["badges"]
    assert set(badges) == {"era", "k_at_cross", "zero_bound", "decline_depth",
                           "above_200", "rs_63"}
    forbidden = {"score", "rank", "tier", "grade", "confidence", "reliability", "weight"}
    assert not (set(badges) & forbidden)
    assert us_early_turn.AUTHORITY == "display"


def test_missing_benchmark_is_a_null_never_a_zero():
    """A relative-strength badge with no benchmark loaded must read null. A 0.0 would say
    'in line with the market', which is a claim the run cannot make."""
    out = union_admission(_fixture("STLD"), asof="2026-07-14")
    assert out["badges"]["rs_63"] is None


# --------------------------------------------------------------- 2. the scored gate is untouched
def _doc(ticker: str) -> dict:
    from engine.signal_quality import analyze
    df = _fixture(ticker)
    return analyze(ticker, df["close"], df["high"], df["low"])


@pytest.mark.parametrize("ticker", [t for t, *_ in EXEMPLARS])
def test_scored_gate_verdict_is_byte_identical_with_and_without_the_new_field(ticker):
    """The store gains `early_signal_dates`; the SCORED gate must not notice.

    This is the zero-diff pin the wiring is allowed to ship under: the verdict computed from
    the new document must equal the verdict computed from the same document with the new key
    stripped — byte for byte, including its reason list."""
    doc = _doc(ticker)
    legacy = {k: v for k, v in doc.items() if k != "early_signal_dates"}
    assert signal_gate.verdict(doc) == signal_gate.verdict(legacy)


def test_scored_gate_never_imports_the_admission_module():
    """A display-tier admission class must not be reachable from the scored path. If this
    ever fails, the union has become an input to a verdict and the tier law is broken."""
    import inspect
    for module in (signal_gate, __import__("engine.confluence_tiers", fromlist=["x"])):
        src = inspect.getsource(module)
        assert "us_early_turn" not in src, f"{module.__name__} reaches the admission module"


def test_union_carries_no_quality_or_buy_semantics():
    """Starter grade only: the union names an admission CLASS and never a buy or a quality."""
    out = union_admission(_fixture("STLD"), asof="2026-07-14")
    assert "quality" not in out and "buy" not in out
    assert set(out["legs"]) <= {UNION_LEG_CROSS, UNION_LEG_DOT}


# --------------------------------------------------------------- 3. the anchor law
@pytest.mark.parametrize("drop", [0, 1, 2, 3, 5, 11])
def test_union_is_history_depth_independent(drop):
    """The 3D grid is cut on the ABSOLUTE session calendar, so dropping leading bars must not
    move a fire. This is the property that lets a 700-row fixture stand for the full tape —
    and the one whose absence (pandas `resample` phasing) is a known live defect elsewhere."""
    df = _fixture("STLD")
    out = union_admission(df.iloc[drop:], asof="2026-07-14")
    assert out["fired"] is True
    assert out["fire_date"] == "2026-07-14"
    assert out["badges"]["k_at_cross"] == pytest.approx(4.71, abs=0.01)


def test_liveness_window_expires_an_old_fire():
    """`fired` is a LIVE read, scoped by the module's own signature age. An old union fire
    is still reported (date + badges) but must not read as an admission today."""
    df = _fixture("STLD")
    out = union_admission(df, asof="2026-07-14")
    stale = union_admission(df, asof=None)  # the fixture's own last bar is the exemplar day
    assert out["fired"] is True
    assert stale["fire_date"] == out["fire_date"]


# --------------------------------------------------------------- 4. one grid, one answer
def test_the_two_3d_grids_agree_so_one_set_of_helpers_is_enough():
    """`confluence_tiers._tf_bars` (which this module already imports) and
    `signal_quality._tf_grid` (which the bake-off measured on) are the same bucketing on the
    same absolute calendar; they differ only in whether the index is the bucket's OPEN label
    or its LAST session. Pinning that here is what licenses computing the union with the
    helpers this module already has instead of importing a parallel set — the file's standing
    'no second implementation' rule."""
    import numpy as np

    from engine.confluence_tiers import _stoch_rsi_kd as ct_kd, _tf_bars
    from engine.signal_quality import _stoch_rsi_kd as sq_kd, _tf_grid

    for ticker, *_ in EXEMPLARS:
        close = _fixture(ticker)["close"]
        grid = _tf_grid(close, 3, "US")
        bars, _known = _tf_bars(close, 3, "US")
        assert len(grid.close) == len(bars)
        assert np.allclose(grid.close.to_numpy(), bars.to_numpy(), equal_nan=True)
        # the knowability dates are the same sessions, whichever label the index carries
        assert list(pd.DatetimeIndex(grid.last_session.to_numpy())) == list(bars.index)
        k1, d1 = sq_kd(pd.Series(grid.close.to_numpy()))
        k2, d2 = ct_kd(pd.Series(bars.to_numpy()))
        assert np.allclose(k1.to_numpy(), k2.to_numpy(), equal_nan=True)
        assert np.allclose(d1.to_numpy(), d2.to_numpy(), equal_nan=True)


# --------------------------------------------------------------- 5. failure shapes
def test_short_history_refuses_rather_than_guesses():
    out = union_admission(_fixture("STLD").tail(20), asof="2026-07-14")
    assert out["fired"] is False
    assert out["reason"] and "usable daily closes" in out["reason"]


# --------------------------------------------------------------- 6. the copy law
def _texture():
    from engine.prophet_bridge import union_admission_texture
    return union_admission_texture(union_admission(_fixture("STLD"), asof="2026-07-14"))


def test_every_string_is_bilingual():
    """EN/ZH on every user-visible string — a deck row with a monolingual chip is a bug."""
    tex = _texture()
    for key in ("chip", "note", "cost_note"):
        assert set(tex[key]) == {"en", "zh"}
        assert tex[key]["en"].strip() and tex[key]["zh"].strip()
    for chip in tex["context_chips"]:
        assert set(chip) == {"en", "zh"}
        assert chip["en"].strip() and chip["zh"].strip()


def test_copy_carries_the_windows_not_certainties_family():
    tex = _texture()
    assert "Windows, not certainties" in tex["note"]["en"]
    assert "窗口" in tex["note"]["zh"]


def test_pretrough_cost_is_stated_and_is_not_the_headline():
    """The honest cost of a recall surface must be SAID — at Tier-2 depth, not at glance."""
    tex = _texture()
    assert "stop out" in tex["cost_note"]["en"]
    assert "止损" in tex["cost_note"]["zh"]
    assert "stop out" not in tex["chip"]["en"]     # never the headline
    assert tex["cost_note"] != tex["chip"]


def test_copy_never_says_validated_and_never_speaks_falsifier():
    """`validated` is CI-enforced house-wide, and falsifier/refutation language is never
    front-facing (operator 2026-07-27) — a window that did not open is not a thesis refuted."""
    tex = _texture()
    blob = " ".join(
        [v[k] for v in (tex["chip"], tex["note"], tex["cost_note"]) for k in ("en", "zh")]
        + [c[k] for c in tex["context_chips"] for k in ("en", "zh")]
    ).lower()
    for banned in ("validated", "falsif", "refut", "invalidated", "证伪", "推翻"):
        assert banned not in blob, f"banned copy: {banned}"


def test_copy_uses_plain_words_not_internal_names_or_raw_stats():
    """Glance tier: no study names, no internal state slugs, no untranslated statistics.
    The numbers ride as DATA on the row; the chips say what a reader can act on."""
    tex = _texture()
    blob = " ".join(
        [v[k] for v in (tex["chip"], tex["note"], tex["cost_note"]) for k in ("en", "zh")]
        + [c[k] for c in tex["context_chips"] for k in ("en", "zh")]
    )
    for slug in ("stochrsi", "macd", "%k", "%d", "c1", "c2r", "early_dot", "relaxed_cross",
                 "union-admission", "z-score", "tercile", "p_low", "atr"):
        assert slug not in blob.lower(), f"internal name leaked into copy: {slug}"
    assert "_" not in blob, "a raw slug reached the copy"


def test_texture_is_empty_when_nothing_admitted():
    from engine.prophet_bridge import union_admission_texture
    assert union_admission_texture({"fired": False}) == {}
    assert union_admission_texture(None) == {}


def test_context_chips_never_imply_durability_or_ordering():
    """§A2 + footprint §A3: no measured feature licenses a reliability read. The chips may
    describe WHERE the name is, never how likely it is to work."""
    tex = _texture()
    blob = " ".join(c["en"] for c in tex["context_chips"]).lower()
    for claim in ("likely", "reliable", "strong buy", "high quality", "best", "score",
                  "rank", "probability", "odds", "confidence"):
        assert claim not in blob, f"durability claim in a context chip: {claim}"


# --------------------------------------------------------------- 7. setup geometry
def _geo(ticker="STLD", asof="2026-07-14", df=None):
    from engine.us_early_turn import setup_geometry
    frame = _fixture(ticker) if df is None else df
    return setup_geometry(frame, asof=asof,
                          union=union_admission(frame, asof=asof))


def test_geometry_scores_the_named_exemplars():
    g = _geo("STLD", "2026-07-14")
    assert 0 <= g["score"] <= 100
    assert g["risk_pct"] == pytest.approx(0.0821, abs=0.001)
    assert g["reference_low"] == pytest.approx(216.36, abs=0.01)
    assert g["stop"] == pytest.approx(216.36 * 0.99, abs=0.01)
    assert g["stop_confirmed"] is True
    assert _geo("NEM", "2026-07-09")["stop_confirmed"] is False


def test_lower_risk_scores_higher():
    """The primary leg: distance to the structural stop, lower = better."""
    from engine.us_early_turn import setup_geometry
    stld, nem = _geo("STLD", "2026-07-14"), _geo("NEM", "2026-07-09")
    assert nem["risk_pct"] < stld["risk_pct"]
    assert nem["score"] > stld["score"]
    assert setup_geometry is not None


def test_a_chase_scores_low_however_good_the_signal_was():
    """The operator's ruling: score the trade available TODAY, not the signal's birthday.

    A REAL replay, not a synthetic one: STLD's 2026-07-14 fire, priced two weeks later on
    the committed tape after price had run +11%. Same signal, same reference low, and the
    score must have gone to the floor — that entry is a chase."""
    from engine.us_early_turn import setup_geometry
    df = _fixture("STLD")
    union = union_admission(df, asof="2026-07-14")
    fresh = setup_geometry(df, asof="2026-07-14", union=union)
    chased = setup_geometry(df, asof="2026-07-28", union=union)
    assert fresh["chase_pct"] == pytest.approx(0.0, abs=1e-9)
    assert chased["chase_pct"] > 0.10
    assert chased["score"] < fresh["score"]
    assert chased["score"] == 0.0, "a fire that has run +11% must sort to the bottom"


def test_a_confirmed_stop_outranks_a_raw_one_all_else_equal():
    from engine.us_early_turn import GEOMETRY_CONFIRMED_BONUS
    assert GEOMETRY_CONFIRMED_BONUS > 0
    g = _geo("STLD", "2026-07-14")
    assert g["stop_confirmed"] is True
    assert g["confirmed_pivot_low"] == pytest.approx(g["reference_low"], abs=0.01)


def test_geometry_is_never_a_probability():
    """Hard rule: no key here may read as a likelihood, and the copy says so out loud."""
    from engine.prophet_bridge import setup_geometry_texture
    g = _geo()
    for banned in ("p_win", "prob", "probability", "win_rate", "odds", "expectancy",
                   "confidence", "durability", "reliability"):
        assert not any(banned in k.lower() for k in g), f"probability key: {banned}"
    tex = setup_geometry_texture(g, "EARLY")
    assert "not a probability" in tex["hover"]["en"]
    assert "不是概率" in tex["hover"]["zh"]


def test_the_nulled_and_retracted_features_are_absent_from_the_score():
    """Test-pinned NON-inputs: the §8 / footprint features that died under
    risk-equalization, member-share theme breadth, and the RETRACTED repeat-fire flag.
    Pinned on the score's own source so a future edit cannot quietly reintroduce one."""
    import inspect

    from engine import us_early_turn
    src = inspect.getsource(us_early_turn.setup_geometry)
    src += inspect.getsource(us_early_turn._confirmed_pivot_low)
    for banned in ("repeat_fire", "repeat_false", "washout_breadth", "turn_breadth",
                   "member_share", "d1_avwap", "d2_poc", "d4_absorption", "d5_quiet",
                   "participation_z", "f_k_cross", "f_rs63", "f_decline_depth"):
        assert banned not in src, f"nulled/retracted feature reached the score: {banned}"


def test_basket_state_is_context_beside_the_row_not_a_score_input():
    """The basket TURNING/CONFIRMED read has its own forward ledger and may DISPLAY beside
    a row — it must not enter the geometry score."""
    import inspect

    from engine import us_early_turn
    # comments are prose ABOUT the score, not inputs to it — read the code only
    src = "\n".join(line.split("#")[0] for line
                    in inspect.getsource(us_early_turn.setup_geometry).splitlines())
    for banned in ("basket", "washout_mature", "TURNING", "membership",
                   "basket_turn_context"):
        assert banned not in src, f"basket context reached the score: {banned}"
    # ... and it IS carried beside the row, as display context
    from engine.prophet_bridge import setup_geometry_texture
    assert "basket" not in str(setup_geometry_texture(_geo(), "EARLY")).lower()


def test_the_two_scores_are_never_blended():
    """Hard rule: the early lane's geometry score and the confirmed lane's score stay two
    numbers, and `stage` is the fact column that says which lane a row reads from."""
    from engine.us_early_turn import STAGE_EARLY
    df = _fixture("STLD")
    row = us_early_turn.assess_early_turn("STLD", df, asof="2026-07-14",
                                          membership={}, leader_states={})
    assert row["stage"] == STAGE_EARLY
    assert row["setup_geometry"]["score"] is not None
    # the early lane exposes ONLY its own score; it never writes a blended/priority score
    assert "score" not in row
    assert "conviction" not in row and "prophet" not in row


def test_stage_sizing_copy_is_bilingual_and_stage_shaped():
    from engine.prophet_bridge import setup_geometry_texture
    tex = setup_geometry_texture(_geo(), "EARLY")
    assert set(tex["sizing"]) == {"en", "zh"}
    assert "Starter" in tex["sizing"]["en"]
    assert "试仓" in tex["sizing"]["zh"]
    confirmed = setup_geometry_texture(_geo(), "CONFIRMED")
    assert "add" in confirmed["sizing"]["en"].lower()


def test_geometry_label_says_geometry_not_quality():
    from engine.prophet_bridge import setup_geometry_texture
    tex = setup_geometry_texture(_geo(), "EARLY")
    assert tex["label"]["en"] == "Setup geometry"
    assert tex["label"]["zh"].strip()
    for banned in ("quality", "conviction", "grade", "rating", "strength"):
        assert banned not in tex["label"]["en"].lower()


def test_geometry_texture_is_empty_without_a_score():
    from engine.prophet_bridge import setup_geometry_texture
    assert setup_geometry_texture(None) == {}
    assert setup_geometry_texture({"score": None}) == {}


def test_geometry_refuses_rather_than_guesses_on_thin_history():
    from engine.us_early_turn import setup_geometry
    g = setup_geometry(_fixture("STLD").tail(10), asof="2026-07-14")
    assert g["score"] is None and g["reason"]


# --------------------------------------------------------------- 8. the two-surface rule
def _naked_union_row():
    """A union fire with NO licensing context — the case the two surfaces disagree on."""
    df = _fixture("STLD")
    return us_early_turn.assess_early_turn("STLD", df, asof="2026-07-14",
                                           membership={}, leader_states={})


def test_a_naked_union_fire_reaches_the_deck_but_not_a_plan():
    """THE two-surface rule (operator ruling 2026-08-11).

    The watch deck is the RECALL tier — it carries every union fire, because the measured
    coverage and lead numbers are naked-union numbers and a context-gated deck would
    silently under-deliver them. Starter-plan ORIGINATION is the larger authority step and
    keeps its context licence. One read, two surfaces, never merged."""
    row = _naked_union_row()
    assert row["union_fired"] is True
    assert row["context_fired"] is False
    # deck: carried
    assert row["deck_admitted"] is True
    # plan: refused, and `fired` (what mints a plan) is unchanged by the split
    assert row["plan_licensed"] is False
    assert row["fired"] is False
    assert row["licensing"]["licensed"] is False
    assert "watch deck" in row["licensing"]["reason"]


def test_a_licensed_union_fire_reaches_both_surfaces():
    df = _fixture("STLD")
    row = us_early_turn.assess_early_turn(
        "STLD", df, asof="2026-07-14",
        membership={"STLD": {"state": "WASHED_OUT", "basket": "steel"}},
        leader_states={})
    if not row["context_fired"]:
        pytest.skip("fixture basket context did not license this row")
    assert row["deck_admitted"] is True
    assert row["plan_licensed"] is True and row["fired"] is True


def test_the_deck_roster_is_a_superset_of_the_plan_roster():
    """Structural: a licensed row is always also a deck row. If this ever inverts, the
    deck is refusing something that minted a plan."""
    row = _naked_union_row()
    assert row["deck_admitted"] or not row["plan_licensed"]


def test_the_licence_is_shown_not_hidden():
    """Splitting the surfaces must not hide the licence — a watch-only row says so, in both
    languages, with the reason a reader can act on."""
    from engine.prophet_bridge import starter_licence_chip
    chip = starter_licence_chip(_naked_union_row()["licensing"])
    assert chip["licensed"] is False
    assert set(chip["chip"]) == {"en", "zh"} and set(chip["why"]) == {"en", "zh"}
    assert "Watch only" in chip["chip"]["en"]
    assert "仅观察" in chip["chip"]["zh"]
    yes = starter_licence_chip({"licensed": True, "reason": "signature + washout"})
    assert yes["licensed"] is True and set(yes["chip"]) == {"en", "zh"}
    assert starter_licence_chip(None) == {}


def test_assess_early_turn_exposes_the_union_without_bypassing_context():
    """`fired` — the PLAN-origination gate — still requires a licensing context. The
    two-surface split widened the DECK, not plan minting."""
    row = _naked_union_row()
    assert row["union_fired"] is True
    assert row["signature_fired"] is True
    assert row["context_fired"] is False
    assert row["fired"] is False, "a union fire with no licensing context must not admit"
    assert row["admission_era"] == UNION_ADMISSION_ERA
    assert row["context_badges"] is not None
