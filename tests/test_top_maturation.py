"""Truth tests for engine.top_maturation — synthetic store only, deterministic, fast.

The load-bearing ones are the state machine and the leg DIRECTIONS: every leg is a
one-sided cut against a frozen threshold, and a flipped inequality would fire the
whole board the wrong way while every render test still passed. The analog tests
pin the three properties the surface's honesty rests on — determinism, same-name
exclusion, and an episode-level N that is allowed to be embarrassingly small.

Nothing here reads the real store, the real library, or the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine import top_anatomy as ta  # noqa: E402
from engine import top_maturation as tm  # noqa: E402
from scripts import build_top_maturation as btm  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# builders
# ══════════════════════════════════════════════════════════════════════════════
def _thresholds() -> dict:
    return {
        "vintage_utc": "2026-08-10T00:00:00Z", "track": "W",
        "window_start": "2021-07-06", "window_end": "2026-07-02",
        "fell_back_hard_drawdown_pct": 20, "fell_back_hard_horizon_td": 63,
        "thresholds": {
            "rs_peak_lag_p90": 26.0, "rs_decel_p10": -0.0109,
            "effort_result_p10": -0.202, "updown_volume_p10": 0.898,
            "vol_asymmetry_p90": 1.28, "late_verticality_p90": 0.565,
            "episode_age_p90": 92.0,
        },
    }


def _detail(**kw) -> dict:
    """A `_name_detail`-shaped dict with every tip input present and sane."""
    c = pd.Series(np.linspace(100.0, 160.0, 200),
                  index=pd.bdate_range("2025-01-01", periods=200))
    base = {
        "_close": c, "rs_left_frac": 0.82, "vol_vs_3m": 0.34,
        "updown_below_one_21": 12, "below_50d_streak": 0,
        "below_50d_first_stretch": True, "episode_left_censored": False,
        "episode_start": "2025-03-04", "episode_high_date": "2026-06-18",
        "episode_high": 160.0, "ep_open_dip_depth": 0.08,
        "ep_sessions_since_peak": 9, "ep_typical_reclaim": 6.0,
        "ep_typical_pullback": 0.06,
    }
    base.update(kw)
    return base


def _feats(**kw) -> dict:
    """A feature row on which NO leg fires."""
    base = {
        "A1_r21": 0.05, "A3_r126": 0.62, "A2_r63": 0.30,
        "A7_late_gain_share": 0.20, "C2_rv21_over_rv63": 1.05,
        "C3_semivol_ratio63": 1.00, "D3_updown_dvol_ratio21": 1.40,
        "D4_ppe_chg21": 0.01, "E3f_rs_peak_lag": 2.0, "E5f_rs_decel": 0.004,
        "F1_episode_age": 40.0, "F2_drawdown_in_episode": -0.01,
        ta.F5_UNRECLAIMED_COL: False,
    }
    base.update(kw)
    return base


def _fire(feat_kw=None, det_kw=None, lib_age=None):
    legs, fired, age_leg = tm._fire_legs(
        _feats(**(feat_kw or {})), _detail(**(det_kw or {})), _thresholds(),
        lib_age if lib_age is not None else np.arange(200.0))
    return legs, fired, age_leg


def _library(n: int = 600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ep = np.repeat(np.arange(n // 3), 3)[:n]
    return pd.DataFrame({
        "ticker": [f"T{e % 90:02d}" for e in ep],
        "segment": [f"T{e % 90:02d}" for e in ep],
        "date": pd.date_range("2022-01-03", periods=n, freq="B"),
        "episode_id": [f"E{e}" for e in ep],
        "episode_outcome": np.where(ep % 3 == 0, "TOPPED", "SURVIVED"),
        "race_label": np.where(ep % 4 == 0, "TOPPED", "CONTINUED"),
        "r126": rng.normal(0.8, 0.3, n).astype("float32"),
        "r63": rng.normal(0.3, 0.2, n).astype("float32"),
        "late_gain_share": rng.uniform(0.05, 0.9, n).astype("float32"),
        "episode_age": rng.uniform(5, 250, n).astype("float32"),
        "rv_ratio": rng.uniform(0.6, 1.9, n).astype("float32"),
        "drawdown_in_episode": (-rng.uniform(0, 0.3, n)).astype("float32"),
        "remaining_upside": rng.uniform(-0.1, 0.6, n).astype("float32"),
        "post_peak_dd_126": (-rng.uniform(0.05, 0.5, n)).astype("float32"),
        "fell_back_hard_63": rng.random(n) < 0.35,
        "track": "W",
    })


def _store(root: Path, *, n_names: int = 26, n_bars: int = 700,
           winners: tuple[str, ...] = ("AAA", "BBB"),
           unlisted_winner: str = "ZZETN", membership: bool = False) -> Path:
    """A synthetic `massive_stock_day` + the house metadata beside it.

    `membership=True` adds the three board-membership fixtures. They are OPT-IN
    because they change the universe the equal-weight median index is cut from,
    and every other test in this file reads legs that are measured against it.
    """
    d = root / tm.STORE_REL
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2024-01-01", periods=n_bars)
    names = [f"N{i:02d}" for i in range(n_names)] + list(winners) + [unlisted_winner]
    names.append("CCC")                     # the maturing winner (see below)
    if membership:
        names += ["DBRK", "DFLT", "DOLD"]
    for k, tk in enumerate(names):
        vol = np.full(n_bars, 900_000.0 + 1000 * k)
        if tk == "DBRK":
            # RECENTLY EXT, and it qualifies as `breaking`: the same ramp, then a
            # 12-session 2%/day slide. It leaves the band ~6 sessions ago (the
            # close drops under 0.90x its 252-day max), which is the FIRST moment
            # a >10% give-back is measurable at all — and by today it is ~21%
            # off its own high and several sessions under its 50-day line.
            base = np.full(n_bars, 10.0)
            e = n_bars - 12
            base[300:e] = 10.0 * (1.006 ** np.arange(e - 300, dtype=float))
            base[e:] = base[e - 1] * (0.98 ** np.arange(1, n_bars - e + 1, dtype=float))
        elif tk == "DFLT":
            # RECENTLY EXT, and it does NOT qualify: it left the band through the
            # OTHER door. The ramp stops and the name drifts gently sideways at
            # its own high, so the six-month gain matures back under +50% ~9
            # sessions ago while the price never gives anything back. Nothing is
            # broken here, so nothing is shown — it drops off the board.
            base = np.full(n_bars, 10.0)
            e = n_bars - 69
            base[300:e] = 10.0 * (1.006 ** np.arange(e - 300, dtype=float))
            base[e:] = base[e - 1] * (1.0002 ** np.arange(1, n_bars - e + 1, dtype=float))
        elif tk == "DOLD":
            # Last EXT day ~52 sessions back: a name that would read as `breaking`
            # on every leg (a third off its high, far under its 50-day line) but
            # has been gone too long to be this board's business.
            base = np.full(n_bars, 10.0)
            e = n_bars - 70
            base[300:e] = 10.0 * (1.006 ** np.arange(e - 300, dtype=float))
            base[e:] = base[e - 1] * (0.994 ** np.arange(1, n_bars - e + 1, dtype=float))
        elif tk == "CCC":
            # Still EXT — six-month gain well over +50%, close inside 10% of its
            # 252-day high — but the last 40 sessions grind lower on heavy
            # down-day volume. This is the row the leg pipeline has to notice.
            base = np.full(n_bars, 10.0)
            ramp = np.arange(n_bars - 300 - 40, dtype=float)
            base[300:n_bars - 40] = 10.0 * (1.006 ** ramp)
            top = base[n_bars - 41]
            drift = np.arange(40, dtype=float)
            base[n_bars - 40:] = top * (1.0 - 0.0022 * drift) * (
                1.0 + 0.004 * ((-1.0) ** drift))
            down = np.r_[False, np.diff(base) < 0]
            vol = np.where(down, vol * 4.0, vol * 0.6)
        elif tk in winners or tk == unlisted_winner:
            base = np.full(n_bars, 10.0)
            ramp = np.arange(n_bars - 300, dtype=float)
            base[300:] = 10.0 * (1.006 ** ramp)
        else:
            base = 20.0 + 0.35 * np.sin(np.arange(n_bars) / 11.0 + k)
        px = pd.DataFrame({
            "open": base, "high": base * 1.01, "low": base * 0.99, "close": base,
            "volume": vol,
        }, index=idx)
        px.index.name = "date"
        px.to_parquet(d / f"{tk}.parquet")

    (root / "universe").mkdir(parents=True, exist_ok=True)
    listed = [t for t in names if t != unlisted_winner]
    pd.DataFrame({"ticker": listed, "group": "sp500",
                  "name": [f"{t} Corp" for t in listed],
                  "sector": "Information Technology",
                  "active": True}).to_parquet(root / "universe" / "membership.parquet")

    (root / "baskets").mkdir(parents=True, exist_ok=True)
    (root / "baskets" / "membership.json").write_text(json.dumps({"baskets": {
        "ai_semis": {"name": "AI Semiconductors", "name_zh": "人工智能半导体",
                     "members": [{"ticker": t, "removed": None} for t in winners]},
        "us_sector_tech": {"name": "Technology", "name_zh": "科技",
                           "members": [{"ticker": t, "removed": None} for t in names]},
        "cn_solar": {"name": "CN Solar", "members": [{"ticker": "600001", "removed": None}]},
    }}))

    (root / "top_anatomy").mkdir(parents=True, exist_ok=True)
    _library().to_parquet(root / "top_anatomy" / "library.parquet", index=False)
    (root / "top_anatomy" / "thresholds.json").write_text(json.dumps(_thresholds()))
    return root


@pytest.fixture()
def quiet_lane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


# ══════════════════════════════════════════════════════════════════════════════
# the state machine
# ══════════════════════════════════════════════════════════════════════════════
def test_state_truth_table():
    assert tm.classify([]) == "extended_healthy"
    assert tm.classify(["rs_decel"]) == "extended_watch"
    assert tm.classify(["rs_decel", "vol_asymmetry"]) == "extended_watch"
    assert tm.classify(["rs_decel", "vol_asymmetry", "effort_result"]) == "thinning"
    assert tm.classify(["below_50d", "drawdown_from_high"]) == "breaking"


def test_breaking_requires_the_structural_pair_not_a_leg_count():
    """Five oscillator legs is `thinning`; the terminal state needs STRUCTURE."""
    five = ["rs_peak_lag", "rs_decel", "effort_result", "updown_volume", "vol_asymmetry"]
    assert tm.classify(five) == "thinning"
    assert tm.classify([*five, "below_50d"]) == "thinning"
    assert tm.classify([*five, "drawdown_from_high"]) == "thinning"
    assert tm.classify(["below_50d", "drawdown_from_high"]) == "breaking"


def test_episode_age_never_counts_toward_a_state():
    assert "episode_age" not in tm.COUNTING_LEGS
    assert tm.classify(["episode_age"]) == "extended_healthy"
    assert tm.classify(["episode_age", "rs_decel"]) == "extended_watch"
    assert tm.classify(["episode_age", "rs_decel", "vol_asymmetry"]) == "extended_watch"


def test_default_window_covers_the_library_age_distribution():
    """`F1_episode_age` is a kNN dimension: the nightly must not clip what the
    library did not. Library maximum observed episode age = 332 sessions."""
    observable = tm.PANEL_TRAILING_SESSIONS - ta.MIN_PRIOR_SESSIONS - 1
    assert observable >= 332, (
        f"a {tm.PANEL_TRAILING_SESSIONS}-bar window sees only {observable} sessions of "
        f"episode and would left-censor the library's own age range")


def test_leg_order_is_the_frozen_key_order():
    assert tm.LEG_ORDER[0] == "rs_peak_lag" and tm.LEG_ORDER[-1] == "episode_age"
    assert len(tm.LEG_ORDER) == 10 and len(tm.COUNTING_LEGS) == 9


# ══════════════════════════════════════════════════════════════════════════════
# leg threshold DIRECTION
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("key,feature,fires,quiet", [
    ("rs_peak_lag", "E3f_rs_peak_lag", 40.0, 2.0),          # P90: fires HIGH
    ("rs_decel", "E5f_rs_decel", -0.05, 0.004),             # P10: fires LOW
    ("effort_result", "D4_ppe_chg21", -0.9, 0.01),          # P10: fires LOW
    ("updown_volume", "D3_updown_dvol_ratio21", 0.4, 1.40),  # P10: fires LOW
    ("vol_asymmetry", "C3_semivol_ratio63", 1.9, 1.00),     # P90: fires HIGH
    ("late_verticality", "A7_late_gain_share", 0.80, 0.20),  # P90: fires HIGH
])
def test_leg_threshold_direction(key, feature, fires, quiet):
    assert key in _fire({feature: fires})[1], f"{key} did not fire on the firing side"
    assert key not in _fire({feature: quiet})[1], f"{key} fired on the quiet side"


def test_leg_never_fires_on_a_null_feature():
    for feature in ("E3f_rs_peak_lag", "E5f_rs_decel", "D4_ppe_chg21",
                    "D3_updown_dvol_ratio21", "C3_semivol_ratio63",
                    "A7_late_gain_share"):
        assert _fire({feature: np.nan})[1] == []


def test_every_leg_goes_dark_without_frozen_thresholds():
    legs, fired, age = tm._fire_legs(
        _feats(E3f_rs_peak_lag=99.0, E5f_rs_decel=-9.0, D4_ppe_chg21=-9.0,
               D3_updown_dvol_ratio21=0.01, C3_semivol_ratio63=9.0,
               A7_late_gain_share=0.99),
        _detail(), {}, np.arange(200.0))
    assert fired == [] and age is None


def test_structural_legs_read_their_own_inputs_not_a_threshold():
    assert "below_50d" in _fire(det_kw={"below_50d_streak": 4})[1]
    assert "below_50d" not in _fire(det_kw={"below_50d_streak": 2})[1]
    assert "drawdown_from_high" in _fire({"F2_drawdown_in_episode": -0.18})[1]
    assert "drawdown_from_high" not in _fire({"F2_drawdown_in_episode": -0.05})[1]
    assert "dip_unreclaimed" in _fire({ta.F5_UNRECLAIMED_COL: True})[1]


def test_legs_render_in_the_frozen_key_order_and_cap_at_three():
    legs, fired, _ = _fire({
        "C3_semivol_ratio63": 1.9, "E3f_rs_peak_lag": 40.0, "A7_late_gain_share": 0.80,
        "D3_updown_dvol_ratio21": 0.4})
    keys = [g["key"] for g in legs]
    assert keys == sorted(keys, key=tm.LEG_ORDER.index)
    assert keys[:3] == ["rs_peak_lag", "updown_volume", "vol_asymmetry"]
    assert len(fired) == 4          # the state machine still sees all four


def test_breaking_row_leads_with_its_own_evidence_and_never_truncates_it():
    """§4.3 amendment: the VIAV shape — a terminal row with four legs firing.

    Under the pure frozen order this rendered `rs_peak_lag · updown_volume ·
    below_50d` and the give-back that MADE it terminal fell off the end. The two
    state-defining legs now lead, and the last slot fills from the frozen order.
    """
    legs, fired, _ = _fire({
        "E3f_rs_peak_lag": 40.0, "D3_updown_dvol_ratio21": 0.4,
        "F2_drawdown_in_episode": -0.21}, {"below_50d_streak": 7})
    assert tm.classify(fired) == "breaking"
    keys = [g["key"] for g in tm.order_legs(legs, "breaking")[:tm.MAX_LEGS]]
    assert keys[:2] == ["below_50d", "drawdown_from_high"]
    assert "drawdown_from_high" in keys                  # the ruling, in one line
    # the remaining slot fills by the FROZEN order, not by firing order
    assert keys[2] == "rs_peak_lag"
    assert len(keys) == tm.MAX_LEGS


def test_leg_reordering_applies_to_breaking_only():
    legs, fired, _ = _fire({
        "E3f_rs_peak_lag": 40.0, "D3_updown_dvol_ratio21": 0.4,
        "C3_semivol_ratio63": 1.9}, {"below_50d_streak": 7})
    state = tm.classify(fired)
    assert state == "thinning"                           # no give-back -> not terminal
    keys = [g["key"] for g in tm.order_legs(legs, state)]
    assert keys == sorted(keys, key=tm.LEG_ORDER.index)  # frozen order, untouched
    # and the amendment never invents a leg that did not fire
    assert "drawdown_from_high" not in keys


def test_leg_reordering_is_display_only_and_leaves_the_state_machine_alone():
    """The amendment must not become a taxonomy change by the back door."""
    legs, fired, _ = _fire({"F2_drawdown_in_episode": -0.21}, {"below_50d_streak": 7})
    before = tm.classify(fired)
    reordered = tm.order_legs(legs, before)
    assert tm.classify([g["key"] for g in reordered]) == before == "breaking"
    # same legs, same content — only the sequence moved
    assert sorted(g["key"] for g in reordered) == sorted(g["key"] for g in legs)
    assert all(g in legs for g in reordered)


def test_tip_is_omitted_rather_than_printing_a_false_sentence():
    """A negative volume ratio cannot render "running −4% above its average"."""
    legs, fired, _ = _fire({"D4_ppe_chg21": -0.9}, {"vol_vs_3m": -0.04})
    assert "effort_result" in fired                     # the state math is untouched
    leg = next(g for g in legs if g["key"] == "effort_result")
    assert "tip_en" not in leg
    assert leg["words_en"] == "more volume, less progress"

    legs, _, _ = _fire({"D4_ppe_chg21": -0.9}, {"vol_vs_3m": 0.34})
    leg = next(g for g in legs if g["key"] == "effort_result")
    assert "34% above its own three-month average" in leg["tip_en"]

    # "the first such stretch in this run" must be true when it is printed
    legs, _, _ = _fire(det_kw={"below_50d_streak": 4, "below_50d_first_stretch": False})
    assert "tip_en" not in next(g for g in legs if g["key"] == "below_50d")


def test_leg_copy_carries_both_languages_and_no_slugs():
    legs, _, _ = _fire({"E3f_rs_peak_lag": 40.0, "D3_updown_dvol_ratio21": 0.4})
    for g in legs:
        assert g["words_en"] and g["words_zh"]
        assert g["key"] not in g["words_en"] and g["key"] not in g["words_zh"]
        assert len(g["words_en"].split()) <= 6


def test_episode_age_is_suppressed_when_the_window_left_censors_it():
    _, _, age = _fire({"F1_episode_age": 150.0})
    assert age is not None and age["key"] == "episode_age"
    _, _, age = _fire({"F1_episode_age": 150.0}, {"episode_left_censored": True})
    assert age is None


# ══════════════════════════════════════════════════════════════════════════════
# analog memory
# ══════════════════════════════════════════════════════════════════════════════
def _vec(lib, i=0):
    return lib["X"][i]


def test_analog_is_deterministic():
    lib = tm._library_arrays(_library())
    a = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    b = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    assert a == b and a is not None


def test_analog_excludes_every_segment_of_the_same_base_ticker():
    df = _library()
    lib = tm._library_arrays(df)
    target = df["ticker"].iloc[0]
    # the exact library row is the nearest neighbour of itself; excluding the
    # ticker must change the answer, and must never return one of its episodes
    with_self = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    without = tm._analog(_vec(lib), lib, target, 20, "W")
    assert without is not None and with_self != without


def test_analog_n_is_episode_level_never_day_level():
    df = _library(n=90)                    # 30 episodes x 3 days
    lib = tm._library_arrays(df)
    a = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    assert a["n"] <= tm.KNN_K
    assert a["n"] <= df["episode_id"].nunique()
    assert 0 <= a["topped_63td"] <= a["n"]


def test_thin_library_reports_the_honest_small_n():
    df = _library(n=9)                     # 3 episodes only
    lib = tm._library_arrays(df)
    a = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    assert a["n"] < tm.THIN_ANALOG_N       # the template prints the thin-record card
    assert a["n"] == df["episode_id"].nunique()


def test_analog_is_none_when_a_matching_dimension_is_missing():
    lib = tm._library_arrays(_library())
    v = _vec(lib).copy()
    v[2] = np.nan
    assert tm._analog(v, lib, "NOPE", 20, "W") is None


def test_analog_arms_never_contradict_their_own_sentence():
    """`median_further_gain` describes the runs that CARRIED ON; a non-positive
    median would render "carried on — a typical further gain of −3%"."""
    df = _library()
    df["remaining_upside"] = -0.2         # every neighbour lost ground
    lib = tm._library_arrays(df)
    a = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    assert a["median_further_gain"] is None

    df = _library()
    df["fell_back_hard_63"] = False       # nobody fell back -> no drop to report
    lib = tm._library_arrays(df)
    a = tm._analog(_vec(lib), lib, "NOPE", 20, "W")
    assert a["topped_63td"] == 0 and a["median_drop_from_high"] is None


# ══════════════════════════════════════════════════════════════════════════════
# the forward log
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    return [{"asof": "2026-08-10", "ticker": "AAA", "segment": "AAA",
             "state": "thinning", "legs": ["rs_decel"], "r126": 0.6, "r21": 0.02,
             "dd_from_high": -0.11, "analog_n": 41, "analog_topped": 14}]


def test_ledger_lane_gate_blocks_every_lane_but_nightly(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "render")
    assert tm.ledger_lane_armed() is False
    assert tm.append_forward_log(_rows(), tmp_path) == 0
    assert not (tmp_path / tm.LOG_REL).exists()

    monkeypatch.delenv("COLLECT_LANE")
    assert tm.append_forward_log(_rows(), tmp_path) == 0

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert tm.ledger_lane_armed() is True
    assert tm.append_forward_log(_rows(), tmp_path) == 1


def test_ledger_is_idempotent_by_asof_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert tm.append_forward_log(_rows(), tmp_path) == 1
    assert tm.append_forward_log(_rows(), tmp_path) == 0        # same key -> no row

    changed = _rows()
    changed[0]["state"] = "breaking"                            # first writer wins
    assert tm.append_forward_log(changed, tmp_path) == 0

    nxt = _rows()
    nxt[0]["asof"] = "2026-08-11"
    assert tm.append_forward_log(nxt, tmp_path) == 1

    lines = (tmp_path / tm.LOG_REL).read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["state"] == "thinning"
    assert set(first) >= {"asof", "ticker", "segment", "state", "legs", "r126", "r21",
                          "dd_from_high", "analog_n", "analog_topped"}
    assert first["legs"] == ["rs_decel"]                        # KEYS only, no copy


# ══════════════════════════════════════════════════════════════════════════════
# end to end on a synthetic store
# ══════════════════════════════════════════════════════════════════════════════
def test_end_to_end_builds_a_board(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None,
                                 trailing=420, log=lambda m: None)
    assert ctx["schema"] == tm.SCHEMA and ctx["null_state"] is False
    assert ctx["extended_n"] == sum(len(v) for v in ctx["states"].values())
    assert ctx["extended_n"] >= 2
    seen = {r["ticker"] for v in ctx["states"].values() for r in v}
    assert {"AAA", "BBB"} <= seen

    row = next(r for v in ctx["states"].values() for r in v)
    assert row["name"].endswith("Corp")
    assert row["href"] is None                       # no shipped page -> no dead link
    assert 3 <= len(row["spark"]) <= tm.SPARK_POINTS
    assert row["episode_high"] is not None


def test_maturing_name_fires_legs_through_the_real_feature_frame(tmp_path, quiet_lane):
    """End to end: a still-EXT name grinding lower on heavy down-day volume must
    come out of `feature_library` -> `_fire_legs` with legs on it. This is the one
    test that would catch a feature-column name drifting away from a leg rule."""
    root = _store(tmp_path / "data")
    ctx, _ = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    row = next((r for v in ctx["states"].values() for r in v if r["ticker"] == "CCC"), None)
    assert row is not None, "the maturing fixture did not reach the board"
    assert row["state"] in ("extended_watch", "thinning", "breaking")
    keys = [g["key"] for g in row["legs"]]
    assert "updown_volume" in keys
    assert keys == sorted(keys, key=tm.LEG_ORDER.index) and len(keys) <= tm.MAX_LEGS
    tip = next(g for g in row["legs"] if g["key"] == "updown_volume")["tip_en"]
    assert "of the last 21 sessions" in tip and "{" not in tip
    # the healthy names must NOT have picked legs up in the same pass
    assert all(not r["legs"] for r in ctx["states"]["extended_healthy"])


def test_instrument_filter_keeps_exchange_traded_products_off_the_board(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    seen = {r["ticker"] for v in ctx["states"].values() for r in v}
    assert "ZZETN" not in seen
    assert "ZZETN" in diag["excluded_instruments"]
    assert diag["n_excluded_non_stock_instruments"] == 1
    # the printed screen count is POST-intersection, never the raw file count
    assert ctx["universe_n"] == diag["n_screened_post_intersection"]
    assert ctx["universe_n"] < diag["n_source_files"]


def test_theme_counts_drop_sector_aggregates_and_non_us_baskets(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    ctx, _ = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    labels = {t["basket"] for t in ctx["theme_counts"]}
    assert "AI Semiconductors" in labels
    assert "Technology" not in labels and "CN Solar" not in labels
    for t in ctx["theme_counts"]:
        assert t["extended"] >= t["watch"] + t["thinning"] + t["breaking"]


def test_rows_are_sorted_by_trailing_gain_inside_every_group(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    ctx, _ = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    for rows in ctx["states"].values():
        got = [r["r126"] for r in rows if r["r126"] is not None]
        assert got == sorted(got, reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# board membership — the breaking-only rule for recently-EXT names
#
# Operator ruling: a name is a candidate iff it printed >=1 EXT day in the
# trailing MEMBERSHIP_WINDOW_SESSIONS. Currently EXT -> the full state machine.
# Recently EXT -> eligible for `breaking` and nothing else; if it does not
# qualify it drops off, because none of the other three states is true of a name
# that has already left the band.
#
# All four run end to end through the real masks, episodes and feature frame:
# the rule is only worth anything if it survives the machinery it sits inside.
# ══════════════════════════════════════════════════════════════════════════════
def _board(ctx) -> dict[str, str]:
    return {r["ticker"]: r["state"] for v in ctx["states"].values() for r in v}


def test_recently_extended_name_that_breaks_is_shown_as_breaking(tmp_path, quiet_lane):
    """(a) It left the band ~6 sessions ago giving back ~21% and losing its
    50-day line. That give-back is unmeasurable WHILE a name is inside the band
    (EXT pins the close within 10% of its 252-day max), so this row existing at
    all is the whole point of the ruling."""
    root = _store(tmp_path / "data", membership=True)
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    board = _board(ctx)
    assert board.get("DBRK") == "breaking"
    assert diag["n_off_band_on_board"] >= 1
    # the structural pair really fired — read from the LEDGER's uncapped `fired`,
    # because the row's rendered `legs` are the frozen key order capped at three
    # and `below_50d`/`drawdown_from_high` sit last in that order.
    led = next(r for r in diag["ledger_rows"] if r["ticker"] == "DBRK")
    assert {"below_50d", "drawdown_from_high"} <= set(led["fired"]), led["fired"]
    assert led["off_band"] is True
    row = next(r for r in ctx["states"]["breaking"] if r["ticker"] == "DBRK")
    keys = [g["key"] for g in row["legs"]]
    # §4.3 amendment, end to end: the terminal row SHOWS what made it terminal
    assert len(keys) <= tm.MAX_LEGS
    assert keys[:2] == ["below_50d", "drawdown_from_high"]
    # the give-back is real and carries its own words, not a borrowed number
    assert row["episode_high"] is not None and row["spark"]
    assert row["episode_high"] > row["spark"][-1]


def test_recently_extended_name_that_does_not_break_drops_off_the_board(tmp_path,
                                                                       quiet_lane):
    """(b) DFLT left the band through the other door — its six-month gain matured
    back under the trigger while the price sat at its own high. Nothing about it
    is worn, so no group is true of it and it is shown nowhere."""
    root = _store(tmp_path / "data", membership=True)
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    assert "DFLT" not in _board(ctx)
    assert diag["n_off_band_dropped"] >= 1
    # it was a CANDIDATE (so this is the rule dropping it, not the window)
    assert diag["n_off_band_candidates"] == (diag["n_off_band_on_board"]
                                             + diag["n_off_band_dropped"])
    # and it is nowhere in the forward log either — a dropped name is not graded
    assert all(r["ticker"] != "DFLT" for r in diag["ledger_rows"])


def test_currently_extended_names_run_the_full_state_machine_unchanged(tmp_path,
                                                                      quiet_lane):
    """(c) The breaking-only filter applies to the off-band arm ONLY. Every name
    still inside the band reaches the board, in whatever state its legs give it."""
    root = _store(tmp_path / "data", membership=True)
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    board = _board(ctx)
    # not one currently-EXT candidate was filtered out
    assert ctx["extended_n"] - diag["n_off_band_on_board"] == diag["n_current_ext_candidates"]
    # ...and they occupy the non-terminal groups exactly as before the ruling
    assert board.get("AAA") == "extended_healthy"
    assert board.get("CCC") in ("extended_watch", "thinning", "breaking")
    assert any(s != "breaking" for tk, s in board.items() if tk in ("AAA", "BBB", "CCC"))
    # the off-band arm never borrows a currently-EXT name's F2: a name inside the
    # band carries no locally-derived drawdown at all.
    assert "f2_off_band" not in _detail()


def test_name_whose_last_extended_day_is_outside_the_window_is_absent(tmp_path,
                                                                     quiet_lane,
                                                                     monkeypatch):
    """(d) DOLD is a third off its high and far under its 50-day line — it reads
    as `breaking` on every leg. It is absent purely because its last EXT day is
    ~52 sessions back. Widening the window is what brings it in, which is the
    proof that the window, not the state, is doing the excluding."""
    root = _store(tmp_path / "data", membership=True)
    ctx, diag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    assert "DOLD" not in _board(ctx)
    assert diag["membership_window_sessions"] == tm.MEMBERSHIP_WINDOW_SESSIONS == 21
    assert diag["n_off_band_candidates"] == 2          # DBRK + DFLT; DOLD is not one

    monkeypatch.setattr(tm, "MEMBERSHIP_WINDOW_SESSIONS", 120)
    wide, wdiag = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    assert _board(wide).get("DOLD") == "breaking"
    assert wdiag["n_off_band_candidates"] == 3


def test_payload_carries_the_standing_law_and_the_leg_scoping(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    ctx, _ = tm.build_context(root, out_root=root, repo_root=None, log=lambda m: None)
    law = ctx["_STANDING_LAW"]
    for phrase in ("DISPLAY TIER", "AVOID-not-SHORT", "history, not forecasts",
                   "NO MODEL", "updown_volume", "gauntlet"):
        assert phrase in law
    prov = ctx["_LEGS_PROVENANCE"]
    assert prov["watch_leg"] == "updown_volume"
    assert prov["model"] is None and prov["probabilities"] is False
    assert tm.null_context("boom")["_STANDING_LAW"] == law


# ══════════════════════════════════════════════════════════════════════════════
# split-repair: the leading-gap bfill carries no look-ahead
#
# `_repair_tail` builds the cumulative split factor as `close / _split_adjust(close)`
# and then `.ffill().bfill()`. The bfill is flagged by
# tests/test_no_lookahead.py and allowlisted at `engine/top_maturation.py:266`; the
# allowlist entry cites THESE tests, so the exemption rests on a measurement rather
# than on a claim in a comment.
# ══════════════════════════════════════════════════════════════════════════════
def _split_bars(n=300, lead_nan=10, split_at=200, ratio=4.0):
    """Bars with a LEADING unpriced gap and a 4:1 split partway through."""
    idx = pd.bdate_range("2024-01-01", periods=n)
    raw = np.full(n, 50.0) + np.arange(n) * 0.05
    raw[split_at:] = raw[split_at:] / ratio          # as-printed post-split prints
    close = pd.Series(raw, index=idx)
    close.iloc[:lead_nan] = np.nan                   # not yet trading
    vol = pd.Series(1_000_000.0, index=idx)
    vol.iloc[:lead_nan] = np.nan
    return pd.DataFrame({"close": close, "volume": vol})


def test_leading_gap_bfill_rows_never_survive_into_the_panel():
    """The bfilled region is exactly the region that gets dropped.

    `factor` is NaN precisely where `close` is NaN, so every row ffill/bfill
    touches has a NaN `close` — and the frame ends with `.dropna(subset=['close'])`.
    A fill that only ever paints rows that are then deleted cannot leak anything.
    """
    bars = _split_bars()
    out = tm._repair_tail(bars, trailing=400)
    assert out is not None and not out.empty
    first_priced = bars["close"].first_valid_index()
    assert out.index.min() == first_priced
    assert len(out) == int(bars["close"].notna().sum())


def test_leading_gap_prefix_parity_bfill_changes_nothing_downstream():
    """Prepending unpriced rows must change NO retained value.

    The look-ahead question is whether the first valid bar's factor, propagated
    backwards, can bend anything a trailing read can see. Truncating the input to
    the first priced bar removes the bfill's entire domain; if the bfill carried
    future information into the retained region, these two frames would differ.
    """
    bars = _split_bars()
    truncated = bars.loc[bars["close"].first_valid_index():]
    a = tm._repair_tail(bars, trailing=400)
    b = tm._repair_tail(truncated, trailing=400)
    assert a is not None and b is not None
    pd.testing.assert_frame_equal(a, b)
    # ...including the split-day flag, which is the one column read off the
    # FILLED factor series rather than off `close`.
    assert bool(a["split_day"].iloc[0]) is False
    assert int(a["split_day"].sum()) == int(b["split_day"].sum()) == 1


def test_split_repair_is_load_bearing_no_fabricated_crash_at_the_split():
    """Dropping the repair would fabricate a split-sized crash — the thing the
    repair exists to prevent. Pins WHY the factor is applied at all."""
    bars = _split_bars()
    out = tm._repair_tail(bars, trailing=400)
    r = (out["close"] / out["close"].shift(1) - 1.0).dropna()
    assert r.min() > -0.10, f"repaired series still shows a split-sized drop: {r.min()}"
    raw_r = (bars["close"] / bars["close"].shift(1) - 1.0).dropna()
    assert raw_r.min() < -0.70          # the as-printed tape does show the -75% step


def test_panel_cache_round_trips_and_the_second_read_is_warm(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    cache = root / tm.PANEL_CACHE_REL
    p1, d1 = tm.build_panel(root, cache_dir=cache, log=lambda m: None)
    assert d1["n_cache_hits"] == 0 and d1["n_files_read"] > 0
    p2, d2 = tm.build_panel(root, cache_dir=cache, log=lambda m: None)
    assert d2["n_cache_hits"] == d1["n_tickers_kept"] and d2["n_files_read"] == 0
    pd.testing.assert_frame_equal(p1["close"], p2["close"])
    # a trailing-window change must invalidate rather than mix two geometries
    _, d3 = tm.build_panel(root, cache_dir=cache, trailing=300, log=lambda m: None)
    assert d3["n_cache_hits"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# the CLI: fail-open
# ══════════════════════════════════════════════════════════════════════════════
def test_cli_fails_open_to_a_null_artifact_when_the_store_is_missing(tmp_path, quiet_lane,
                                                                     capsys):
    out = tmp_path / "out"
    (out / "top_maturation").mkdir(parents=True)
    rc = btm.main(["--root", str(out), "--data-root", str(tmp_path / "nothing")])
    assert rc == 0
    art = json.loads((out / tm.LATEST_REL).read_text())
    assert art["null_state"] is True and art["null_reason"]
    assert art["_STANDING_LAW"] == tm.STANDING_LAW
    assert art["states"] == {"extended_healthy": [], "extended_watch": [],
                             "thinning": [], "breaking": []}
    line = capsys.readouterr().out
    assert "::warning title=top-maturation::" in line
    assert line[line.index("::warning"):].startswith("::warning")


def test_cli_fails_open_when_the_us_stock_metadata_is_absent(tmp_path, quiet_lane):
    """No metadata means the board cannot tell a company from an ETP: it says so."""
    root = _store(tmp_path / "data")
    (root / "universe" / "membership.parquet").unlink()
    out = tmp_path / "out"
    rc = btm.main(["--root", str(out), "--data-root", str(root)])
    assert rc == 0
    art = json.loads((out / tm.LATEST_REL).read_text())
    assert art["null_state"] is True
    assert "metadata" in art["null_reason"]


def test_cli_writes_a_board_and_stamps_its_vintage(tmp_path, quiet_lane):
    root = _store(tmp_path / "data")
    out = tmp_path / "out"
    assert btm.main(["--root", str(out), "--data-root", str(root)]) == 0
    art = json.loads((out / tm.LATEST_REL).read_text())
    assert art["null_state"] is False and art["extended_n"] >= 2
    assert art["_vintage"]["generated_utc"].endswith("Z")
    assert art["_vintage"]["library_vintage"] == _thresholds()["vintage_utc"]
    assert art["_diagnostics"]["n_excluded_non_stock_instruments"] == 1
    assert not (out / tm.LOG_REL).exists()      # off-lane: the ledger never advanced


def test_cli_advances_the_ledger_only_on_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    root = _store(tmp_path / "data")
    out = tmp_path / "out"
    assert btm.main(["--root", str(out), "--data-root", str(root)]) == 0
    rows = [json.loads(x) for x in (out / tm.LOG_REL).read_text().strip().split("\n")]
    assert rows and {"asof", "ticker", "state", "legs"} <= set(rows[0])
    assert btm.main(["--root", str(out), "--data-root", str(root)]) == 0
    again = (out / tm.LOG_REL).read_text().strip().split("\n")
    assert len(again) == len(rows)              # idempotent across re-runs
