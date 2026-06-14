"""Tests for engine.setups — the shared selection×timing setup score.

Covers the timing tilts, the US-vs-China alpha weighting, the buy/laggard
ranking gates, and a PARITY lock that the shared score reproduces China's prior
inline ``_setup_score`` (so the refactor cannot silently move the shipped board).
"""
from pytest import approx

from engine.setups import (
    CN_ALPHA_WEIGHT,
    US_ALPHA_WEIGHT,
    rank_setups,
    setup_score,
    timing_tilt,
)


def _rec(az, *, entry=None, urgency=None, eq_dir=None, ticker="T", name="N",
         sector="Tech", sector_rank=1, sector_n=10, state="FRESH BUY",
         label="BUY ZONE"):
    """A minimal rec shaped like build_*_library passes in."""
    alpha = None if az is None else {"alpha": az, "entry": entry,
                                     "sector_rank": sector_rank, "sector_n": sector_n}
    return {"ticker": ticker, "name": name, "sector": sector, "alpha": alpha,
            "ladder": {"entry": {"urgency": urgency}, "eq_dir": eq_dir,
                       "state": state, "label": label, "dir": "up"}}


# ---- timing_tilt ------------------------------------------------------------

def test_timing_tilt_components():
    assert timing_tilt("now", None, None) == 0.9
    assert timing_tilt("imminent", None, None) == 0.9
    assert timing_tilt("soon", None, None) == 0.45
    assert timing_tilt("exit", None, None) == -0.9
    assert timing_tilt("avoid", None, None) == -0.9
    assert timing_tilt(None, "up", None) == 0.35
    assert timing_tilt(None, "down", None) == -0.35
    assert timing_tilt(None, None, "pullback") == 0.7
    assert timing_tilt(None, None, "extended") == -0.7
    assert timing_tilt(None, None, None) == 0.0
    # additive across legs
    assert timing_tilt("now", "up", "pullback") == 0.9 + 0.35 + 0.7


def test_timing_tilt_unknown_values_are_zero():
    assert timing_tilt("whoknows", "sideways", "mystery") == 0.0


# ---- setup_score ------------------------------------------------------------

def test_setup_score_none_without_residual():
    assert setup_score(_rec(None), alpha_weight=US_ALPHA_WEIGHT) is None
    # explicit empty alpha dict -> no residual -> None
    assert setup_score({"alpha": {}, "ladder": {}}, alpha_weight=0.7) is None


def test_setup_score_us_strong_leader_fresh_pullback():
    sc = setup_score(_rec(2.0, entry="pullback", urgency="now", eq_dir="up"),
                     alpha_weight=US_ALPHA_WEIGHT)
    assert sc is not None
    score, row = sc
    assert score == 0.7 * 2.0 + (0.9 + 0.35 + 0.7)   # 3.35
    assert row["setup"] == 3.35
    assert row["alpha"] == 2.0 and row["alpha_entry"] == "pullback"
    assert row["sector_rank"] == 1 and row["sector_n"] == 10


def test_setup_score_extended_leader_penalised():
    # a just-spiked leader with no cycle entry scores far below the pullback case
    pull = setup_score(_rec(1.0, entry="pullback", urgency="now", eq_dir="up"),
                       alpha_weight=US_ALPHA_WEIGHT)[0]
    ext = setup_score(_rec(1.0, entry="extended", urgency=None, eq_dir="up"),
                      alpha_weight=US_ALPHA_WEIGHT)[0]
    assert pull > ext
    assert ext == 0.7 * 1.0 + (0.0 + 0.35 - 0.7)      # 0.35


def test_us_weight_leads_more_than_china():
    # same name: the US (alpha-led) score weights the residual more than China
    r = _rec(2.0, entry="intact", urgency="soon", eq_dir="up")
    us = setup_score(r, alpha_weight=US_ALPHA_WEIGHT)[0]
    cn = setup_score(r, alpha_weight=CN_ALPHA_WEIGHT)[0]
    assert us > cn
    assert us - cn == approx((US_ALPHA_WEIGHT - CN_ALPHA_WEIGHT) * 2.0)


# ---- rank_setups ------------------------------------------------------------

def test_rank_setups_buy_and_laggard_gates():
    cands = [
        setup_score(_rec(2.0, entry="pullback", urgency="now", eq_dir="up", ticker="A"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(0.6, entry="intact", urgency="soon", eq_dir="up", ticker="B"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(0.1, urgency=None, ticker="C"), alpha_weight=US_ALPHA_WEIGHT),    # neither buy nor laggard
        setup_score(_rec(-0.5, urgency="exit", eq_dir="down", ticker="D"), alpha_weight=US_ALPHA_WEIGHT),
        setup_score(_rec(-1.4, urgency="exit", eq_dir="down", ticker="E"), alpha_weight=US_ALPHA_WEIGHT),
    ]
    out = rank_setups(cands)
    buys = [r["ticker"] for r in out["buy"]]
    lags = [r["ticker"] for r in out["laggards"]]
    # buys = alpha>=0.5, ranked by setup desc -> A (strong+fresh) before B
    assert buys == ["A", "B"]
    # the middling 0.1-alpha name is in NEITHER list
    assert "C" not in buys and "C" not in lags
    # laggards = alpha<=-0.3, ranked by setup asc -> most negative first
    assert lags == ["E", "D"]


def test_rank_setups_respects_caps():
    cands = [setup_score(_rec(1.0 + i * 0.01, entry="pullback", urgency="now",
                              eq_dir="up", ticker=f"T{i}"),
                         alpha_weight=US_ALPHA_WEIGHT) for i in range(30)]
    out = rank_setups(cands, n_buy=12, n_lag=6)
    assert len(out["buy"]) == 12
    assert len(out["laggards"]) == 0   # none are laggards


def test_rank_setups_as_of_passthrough():
    out = rank_setups([], as_of="2026-06-14")
    assert out == {"as_of": "2026-06-14", "buy": [], "laggards": []}


# ---- China parity lock ------------------------------------------------------

def _china_old_setup_score(rec):
    """Verbatim copy of the prior inline scripts/build_china_library._setup_score
    (pre-refactor). The shared engine MUST reproduce this with alpha_weight=0.35."""
    a = rec.get("alpha") or {}
    az = a.get("alpha")
    if az is None:
        return None
    lad = rec.get("ladder") or {}
    entry = lad.get("entry") or {}
    urg, eqdir, ae = entry.get("urgency"), lad.get("eq_dir"), a.get("entry")
    timing = 0.0
    if urg in ("now", "imminent"):
        timing += 0.9
    elif urg == "soon":
        timing += 0.45
    elif urg in ("exit", "avoid"):
        timing -= 0.9
    if eqdir == "up":
        timing += 0.35
    elif eqdir == "down":
        timing -= 0.35
    if ae == "pullback":
        timing += 0.7
    elif ae == "extended":
        timing -= 0.7
    score = 0.35 * az + timing
    row = {"ticker": rec["ticker"], "name": rec["name"], "sector": rec.get("sector"),
           "alpha": az, "alpha_entry": ae, "state": lad.get("state"),
           "label": lad.get("label"), "label_zh": lad.get("label_zh"),
           "urgency": urg, "dir": lad.get("dir"), "eq_dir": eqdir,
           "sector_rank": a.get("sector_rank"), "sector_n": a.get("sector_n"),
           "setup": round(score, 2)}
    return score, row


def test_china_parity():
    cases = [
        _rec(2.0, entry="pullback", urgency="now", eq_dir="up"),
        _rec(1.2, entry="extended", urgency="exit", eq_dir="down"),
        _rec(-0.8, entry="laggard", urgency="soon", eq_dir=None),
        _rec(0.0, entry="neutral", urgency=None, eq_dir="up"),
        _rec(-2.5, entry=None, urgency="avoid", eq_dir="down"),
    ]
    for rec in cases:
        rec["ladder"]["label_zh"] = "中文"   # exercise the label_zh passthrough
        old = _china_old_setup_score(rec)
        new = setup_score(rec, alpha_weight=CN_ALPHA_WEIGHT)
        assert old is not None and new is not None
        assert old[0] == new[0]
        assert old[1] == new[1]
