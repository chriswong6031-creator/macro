"""Contract tests for engine/group_pulse.py — the `group_pulse.v1` frozen shape.

Covers:
  (1)  A GOLDEN object assembled through the real code path validates clean, and
       carries exactly the frozen key set at every level.
  (2)  MUTANTS fail: an unknown key, a share that arrives without its n, an
       activity_basis that does not partition activity_n, an off-ladder arc state,
       a rewritten null_disclosure, a wrong schema/authority string.
  (3)  The coverage floors REFUSE: below ARC_MIN_COVERED, and below
       ARC_MIN_COVERED_FRACTION, the arc state is `insufficient_coverage` and the
       hole is printed in coverage_warnings — never filled in.
  (4)  The arc ladder is first-match-wins, rung by rung.
  (5)  engine.coiled.washout_ctx_detail is a pure extraction: the bool projection
       equals the pre-extraction washout_ctx on every input class, including the
       None (too-short / unusable) cases.
  (6)  The activity legs: return-leg-only, volume-leg-only, and the basis counts
       that partition activity_n.
  (7)  engine.group_flow.sign_agreement — the leg added to the existing organ.
  (8)  Authority: context_only, every may_* false, and no banned vocabulary
       (the CI-guarded word "validated", or ignition language) in the module.

Frozen-fixture law: every assertion here runs on a synthetic panel built in-test.
NOTHING in this file reads the live member store — a replay over live data asserts
about TODAY and rots the day the tape moves.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from engine import coiled
from engine import group_pulse as GP
from engine.group_flow import sign_agreement


# ---------------------------------------------------------------------------
# Fixture builders (frozen — no live store, no clock, no network)
# ---------------------------------------------------------------------------

SESSIONS = 420
END = pd.Timestamp("2026-06-30")


def _idx(n: int = SESSIONS) -> pd.DatetimeIndex:
    return pd.bdate_range(end=END, periods=n)


def _walk(idx: pd.DatetimeIndex, seed: int, drift: float = 0.0004,
          vol: float = 0.012, start: float = 100.0) -> pd.Series:
    """A deterministic random walk — noise is required, not decorative: a perfectly
    flat series has zero rolling std, so its activity z-score is NaN and the member
    reads UNCOVERED rather than quiet."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, len(idx))
    return pd.Series(start * np.cumprod(1.0 + r), index=idx, dtype="float64")


def _vol_series(idx: pd.DatetimeIndex, seed: int, base: float = 1_000_000.0) -> pd.Series:
    rng = np.random.default_rng(seed + 9_000)
    return pd.Series(base * (1.0 + rng.normal(0.0, 0.05, len(idx))),
                     index=idx, dtype="float64")


def _panel(tickers: list[str], idx: pd.DatetimeIndex, *, seed0: int = 11,
           spike: dict[str, float] | None = None,
           vol_spike: dict[str, float] | None = None,
           no_volume: tuple[str, ...] = (),
           short: dict[str, int] | None = None):
    """Build a member panel through the REAL build_member_panel.

    `spike[t]` multiplies the LAST close (a big move -> the return leg fires);
    `vol_spike[t]` multiplies the LAST volume (the volume leg fires);
    `no_volume` drops a member's volume entirely (return leg only);
    `short[t]` truncates a member to its last N sessions (an uncovered member).
    """
    spike, vol_spike, short = spike or {}, vol_spike or {}, short or {}
    cl, vo = {}, {}
    for i, t in enumerate(tickers):
        c = _walk(idx, seed0 + i)
        if t in spike:
            c.iloc[-1] = c.iloc[-2] * spike[t]
        v = _vol_series(idx, seed0 + i)
        if t in vol_spike:
            v.iloc[-1] = v.iloc[-1] * vol_spike[t]
        if t in short:
            c, v = c.tail(short[t]), v.tail(short[t])
        cl[t] = c
        if t not in no_volume:
            vo[t] = v
    closes = pd.concat(cl, axis=1).sort_index()
    volumes = (pd.concat(vo, axis=1).reindex(index=closes.index, columns=closes.columns)
               if vo else pd.DataFrame(np.nan, index=closes.index, columns=closes.columns))
    bench = _walk(idx, 7_777, drift=0.0003, vol=0.008, start=400.0)
    return GP.build_member_panel(closes, volumes, bench), bench


def _basket(tickers: list[str], added: str = "2020-01-01") -> dict:
    return {"name": "Test Basket",
            "members": [{"ticker": t, "added": added, "removed": None} for t in tickers]}


def _assemble(basket_id: str, basket: dict, panel: dict, *,
              washouts: dict | None = None, stages: dict | None = None) -> dict:
    as_of = panel["index"].max()
    frames = GP.basket_frames(basket, panel, as_of)
    eps = GP.episodes_from_series(
        basket_id, list(frames["daily"].index),
        frames["daily"]["activity_share"].tolist(),
        frames["daily"]["activity_n"].tolist(), frames["members_by_day"])
    if washouts is None:
        washouts = GP.member_washouts(panel["closes"])
    if stages is None:
        stages = {t: 2 for t in panel["closes"].columns}
    return GP.basket_pulse(basket_id, basket, panel, as_of, washouts, stages,
                           "2026-06-30T00:00:00+00:00", frames, eps)


@pytest.fixture(scope="module")
def golden() -> dict:
    tk = [f"M{i:02d}" for i in range(10)]
    idx = _idx()
    panel, _ = _panel(tk, idx, spike={"M00": 1.22, "M01": 0.80, "M02": 1.18},
                      vol_spike={"M03": 4.0, "M04": 5.0}, no_volume=("M05",))
    obj = _assemble("test_basket", _basket(tk), panel)
    assert obj is not None
    return obj


# ---------------------------------------------------------------------------
# (1) the golden object
# ---------------------------------------------------------------------------

def test_golden_object_validates(golden):
    assert GP.validate_pulse(golden) == []


def test_golden_carries_the_frozen_key_set(golden):
    assert set(golden) == {
        "schema", "authority", "generated_at", "basket_id", "as_of",
        "n_members", "n_covered", "participation", "direction", "arc",
        "episode", "coverage_warnings"}
    assert set(golden["participation"]) == {
        "activity_share", "activity_n", "trend_share_50d", "trend_share_200d",
        "activity_basis"}
    assert set(golden["participation"]["activity_basis"]) == {"ret_only", "ret_and_volume"}
    assert set(golden["direction"]) == {
        "agreement_pct", "sign", "median_move_spy_adj", "cohesion", "leader",
        "strongest", "weakest"}
    assert set(golden["arc"]) == {
        "state", "washed_out_share", "washed_out_n", "reclaimed_20d_share",
        "capitulation_median_age_d", "stage2_share", "stage4_share",
        "drawdown_pctile_own_history", "null_disclosure"}
    assert set(golden["episode"]) == {
        "active_now", "current_start", "sessions_active", "state_change"}


def test_golden_is_context_only_and_json_safe(golden):
    import json
    assert golden["schema"] == GP.SCHEMA
    assert golden["authority"] == "context_only"
    assert golden["arc"]["null_disclosure"] == "oracle_p8"
    json.loads(json.dumps(golden))          # no NaN / no non-serialisable value


def test_validate_payload_checks_the_key_matches_its_object(golden):
    assert GP.validate_payload({"test_basket": golden}) == []
    errs = GP.validate_payload({"other_id": golden})
    assert any("basket_id does not match its key" in e for e in errs)


# ---------------------------------------------------------------------------
# (2) mutants must fail
# ---------------------------------------------------------------------------

def test_unknown_top_level_key_is_a_violation(golden):
    mutant = {**golden, "conviction_score": 0.8}
    errs = GP.validate_pulse(mutant)
    assert any("unknown key" in e for e in errs), errs


def test_unknown_nested_key_is_a_violation(golden):
    mutant = {**golden, "arc": {**golden["arc"], "heat": 3}}
    errs = GP.validate_pulse(mutant)
    assert any("arc: unknown key" in e for e in errs), errs


def test_share_without_its_n_is_a_violation(golden):
    part = {k: v for k, v in golden["participation"].items() if k != "activity_n"}
    errs = GP.validate_pulse({**golden, "participation": part})
    assert any("missing key" in e for e in errs), errs

    arc = {k: v for k, v in golden["arc"].items() if k != "washed_out_n"}
    errs = GP.validate_pulse({**golden, "arc": arc})
    assert any("missing key" in e for e in errs), errs


def test_share_present_with_a_non_integer_n_is_a_violation(golden):
    arc = {**golden["arc"], "washed_out_share": 0.5, "washed_out_n": None}
    errs = GP.validate_pulse({**golden, "arc": arc})
    assert any("without washed_out_n" in e for e in errs), errs


def test_activity_basis_must_partition_activity_n(golden):
    part = {**golden["participation"],
            "activity_basis": {"ret_only": 99, "ret_and_volume": 99}}
    errs = GP.validate_pulse({**golden, "participation": part})
    assert any("must partition activity_n" in e for e in errs), errs


def test_off_ladder_arc_state_is_a_violation(golden):
    errs = GP.validate_pulse({**golden, "arc": {**golden["arc"], "state": "bottoming"}})
    assert any("arc.state must be one of" in e for e in errs), errs


def test_rewritten_null_disclosure_is_a_violation(golden):
    errs = GP.validate_pulse({**golden, "arc": {**golden["arc"], "null_disclosure": ""}})
    assert any("null_disclosure" in e for e in errs), errs


@pytest.mark.parametrize("field,bad", [("schema", "group_pulse.v2"),
                                       ("authority", "scored")])
def test_schema_and_authority_are_frozen(golden, field, bad):
    errs = GP.validate_pulse({**golden, field: bad})
    assert errs, f"mutating {field} must be a violation"


def test_off_enum_sign_and_state_change_are_violations(golden):
    errs = GP.validate_pulse({**golden, "direction": {**golden["direction"], "sign": "bull"}})
    assert any("direction.sign" in e for e in errs), errs
    errs = GP.validate_pulse({**golden, "episode": {**golden["episode"],
                                                    "state_change": "igniting"}})
    assert any("state_change" in e for e in errs), errs


def test_n_covered_cannot_exceed_n_members(golden):
    errs = GP.validate_pulse({**golden, "n_covered": golden["n_members"] + 1})
    assert any("cannot exceed" in e for e in errs), errs


# ---------------------------------------------------------------------------
# (3) coverage floors REFUSE
# ---------------------------------------------------------------------------

def test_below_min_covered_refuses():
    tk = [f"S{i:02d}" for i in range(4)]
    panel, _ = _panel(tk, _idx())
    obj = _assemble("thin", _basket(tk), panel)
    assert obj["n_covered"] == 4 < GP.ARC_MIN_COVERED
    assert obj["arc"]["state"] == "insufficient_coverage"
    assert "below_coverage_floor" in obj["coverage_warnings"]


def test_below_covered_fraction_refuses():
    """10 live members, 4 with a usable tape: 0.4 < 0.6 floor -> refusal, and the
    hole is PRINTED (members_without_tape) rather than divided away."""
    have = [f"H{i:02d}" for i in range(4)]
    ghosts = [f"G{i:02d}" for i in range(6)]
    panel, _ = _panel(have, _idx())
    obj = _assemble("holey", _basket(have + ghosts), panel)
    assert obj["n_members"] == 10
    assert obj["n_covered"] == 4
    assert obj["arc"]["state"] == "insufficient_coverage"
    assert "members_without_tape:6" in obj["coverage_warnings"]
    assert "below_coverage_floor" in obj["coverage_warnings"]


def test_short_history_member_is_live_but_not_covered():
    """A 10-session IPO is LIVE and NOT covered — it is neither counted as
    participating nor quietly dropped from n_members."""
    tk = [f"M{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx(), short={"M07": 10})
    obj = _assemble("ipo", _basket(tk), panel)
    assert obj["n_members"] == 8
    assert obj["n_covered"] == 7
    assert "members_without_activity_read:1" in obj["coverage_warnings"]


def test_coverage_requires_the_FULL_63_session_window():
    """The pin on the one place this plane deviates from an imported convention.

    `group_flow._causal_z` supplies the math with min_periods = window // 3, so a
    40-session member HAS a non-null z — computed against 40 samples while the
    contract promises 63. Coverage requires the window the definition claims; a
    thinner member is live and UNKNOWN, never scored against a stub distribution.
    """
    tk = [f"M{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx(), short={"M07": 40})
    as_of = panel["index"].max()
    assert pd.notna(panel["activity_z"].at[as_of, "M07"])   # the z exists...
    assert bool(panel["covered"].at[as_of, "M07"]) is False  # ...coverage does not
    assert bool(panel["active"].at[as_of, "M07"]) is False
    assert GP.ACTIVITY_LOOKBACK_D == 63

    obj = _assemble("thinwindow", _basket(tk), panel)
    assert obj["n_members"] == 8 and obj["n_covered"] == 7


# ---------------------------------------------------------------------------
# (4) the arc ladder, rung by rung (first match wins)
# ---------------------------------------------------------------------------

def _state(**kw) -> str:
    base = dict(n_covered=10, n_members=10, washed_share=0.0, median_age=None,
                reclaimed=None, stage2=None, stage4=None, trend50=None)
    base.update(kw)
    return GP._arc_state(base["n_covered"], base["n_members"], base["washed_share"],
                         base["median_age"], base["reclaimed"], base["stage2"],
                         base["stage4"], base["trend50"])


def test_ladder_rung_1_washout_in_progress():
    assert _state(washed_share=0.6, median_age=3, reclaimed=0.9) == "washout_in_progress"


def test_ladder_rung_2_awaiting_reclaim():
    assert _state(washed_share=0.6, median_age=20,
                  reclaimed=0.2) == "washout_complete_awaiting_reclaim"


def test_ladder_rung_3_turning():
    assert _state(washed_share=0.6, median_age=20, reclaimed=0.7) == "turning"


def test_ladder_rung_4_advancing():
    assert _state(stage2=0.7, trend50=0.8) == "advancing"


def test_ladder_rung_5_distributing():
    assert _state(stage4=0.5, trend50=0.2) == "distributing"


def test_ladder_rung_6_quiet():
    assert _state(washed_share=0.1, stage2=0.1, stage4=0.1, trend50=0.5) == "quiet"


def test_ladder_first_match_wins_over_a_later_rung():
    """A washed-out group that also looks stage-2/advancing prints the WASHOUT rung —
    the ladder is ordered, not scored, so rung 1 beats rung 4."""
    assert _state(washed_share=0.9, median_age=2, stage2=0.9,
                  trend50=0.9) == "washout_in_progress"


def test_floors_are_checked_before_every_rung():
    assert _state(n_covered=4, washed_share=0.9, median_age=1) == "insufficient_coverage"
    assert _state(n_covered=6, n_members=20, washed_share=0.9,
                  median_age=1) == "insufficient_coverage"


def test_null_legs_never_fabricate_a_rung():
    """Nulls print as nulls: with no stage read and no washout read the ladder falls
    through to `quiet`, it does not guess a state."""
    assert _state(washed_share=None, stage2=None, stage4=None, trend50=None) == "quiet"


# ---------------------------------------------------------------------------
# (5) coiled.washout_ctx_detail is a pure extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,shape", [(120, "short"), (400, "walk"), (400, "crash"),
                                     (400, "rally"), (500, "crash")])
def test_washout_ctx_detail_matches_bool(n, shape):
    idx = pd.bdate_range(end=END, periods=n)
    s = _walk(idx, 42, drift=0.0, vol=0.01)
    if shape == "crash":
        s.iloc[-80:] = s.iloc[-81] * np.linspace(1.0, 0.55, 80)
    elif shape == "rally":
        s.iloc[-80:] = s.iloc[-81] * np.linspace(1.0, 1.45, 80)
    bool_form = coiled.washout_ctx(s)
    detail = coiled.washout_ctx_detail(s)
    if detail is None:
        assert bool_form is None
    else:
        assert bool_form is detail["washed_out"]
        assert detail["trough_date"] in s.index
        assert detail["sessions_since_trough"] >= 0
        assert detail["drawdown_at_trough"] <= 0.0


def test_washout_ctx_detail_locates_the_trough():
    """The whole point of the detail form: it hands back WHERE the low was, so an
    arc can age a capitulation. A crash that bottoms 20 sessions before the end
    must report ~20, not merely True."""
    idx = pd.bdate_range(end=END, periods=500)
    s = _walk(idx, 5, drift=0.0, vol=0.004)
    s.iloc[-120:-20] = s.iloc[-121] * np.linspace(1.0, 0.5, 100)
    s.iloc[-20:] = s.iloc[-21] * np.linspace(1.0, 1.15, 20)
    d = coiled.washout_ctx_detail(s)
    assert d is not None and d["washed_out"] is True
    assert d["sessions_since_trough"] == 20
    assert d["trough_date"] == s.index[-21]


def test_washout_ctx_detail_none_on_short_history():
    idx = pd.bdate_range(end=END, periods=100)
    assert coiled.washout_ctx_detail(_walk(idx, 3)) is None
    assert coiled.washout_ctx(_walk(idx, 3)) is None


def test_washout_ctx_never_raises_on_junk():
    assert coiled.washout_ctx_detail(pd.Series(dtype="float64")) is None
    assert coiled.washout_ctx(pd.Series(dtype="float64")) is None


# ---------------------------------------------------------------------------
# (6) activity legs + basis partition
# ---------------------------------------------------------------------------

def test_return_leg_fires_without_volume():
    tk = [f"R{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx(), spike={"R00": 1.30}, no_volume=tuple(tk))
    as_of = panel["index"].max()
    assert bool(panel["active"].at[as_of, "R00"]) is True
    assert bool(panel["vol_leg"].at[as_of, "R00"]) is False
    obj = _assemble("retonly", _basket(tk), panel)
    assert obj["participation"]["activity_basis"]["ret_and_volume"] == 0
    assert obj["participation"]["activity_basis"]["ret_only"] == obj["participation"]["activity_n"]


def test_volume_leg_fires_without_an_unusual_move():
    tk = [f"V{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx(), vol_spike={"V00": 6.0})
    as_of = panel["index"].max()
    assert float(panel["vol_ratio"].at[as_of, "V00"]) >= GP.ACTIVITY_VOL_MULT
    assert bool(panel["active"].at[as_of, "V00"]) is True


def test_activity_basis_partitions_active_members(golden):
    b = golden["participation"]["activity_basis"]
    assert b["ret_only"] + b["ret_and_volume"] == golden["participation"]["activity_n"]


def test_activity_share_divides_by_n_covered(golden):
    share = golden["participation"]["activity_share"]
    assert share == pytest.approx(golden["participation"]["activity_n"] / golden["n_covered"],
                                  abs=1e-4)


def test_thresholds_are_pinned_to_their_v1_literals():
    assert (GP.ACTIVITY_LOOKBACK_D, GP.ACTIVITY_Z_MIN, GP.ACTIVITY_VOL_MULT) == (63, 1.5, 1.5)
    assert (GP.TREND_MA_FAST, GP.TREND_MA_SLOW, GP.RECLAIM_MA) == (50, 200, 20)
    assert (GP.ARC_MIN_COVERED, GP.ARC_MIN_COVERED_FRACTION) == (5, 0.6)
    assert (GP.EPISODE_ENTER_SHARE, GP.EPISODE_EXIT_SHARE) == (0.5, 0.35)
    assert (GP.EPISODE_MIN_ACTIVE, GP.EPISODE_MAX_GAP, GP.EPISODE_CLOSE_AFTER) == (3, 2, 3)


# ---------------------------------------------------------------------------
# (7) the leg added to engine/group_flow.py
# ---------------------------------------------------------------------------

def test_sign_agreement_unanimous():
    a = sign_agreement(pd.Series({"A": 0.01, "B": 0.02, "C": 0.03}))
    assert a == {"agreement_pct": 1.0, "net": 3, "n": 3, "n_up": 3, "n_down": 0, "n_flat": 0}


def test_sign_agreement_split():
    a = sign_agreement(pd.Series({"A": 0.01, "B": -0.02, "C": 0.03, "D": -0.01}))
    assert a["agreement_pct"] == 0.0 and a["net"] == 0 and a["n"] == 4


def test_sign_agreement_counts_a_flat_member_in_the_denominator():
    """A member that did not pick a side is a member, not an absent member."""
    a = sign_agreement(pd.Series({"A": 0.01, "B": 0.01, "C": 0.0, "D": 0.0}))
    assert a["n"] == 4 and a["net"] == 2 and a["agreement_pct"] == pytest.approx(0.5)
    assert a["n_flat"] == 2


def test_sign_agreement_drops_nan_and_survives_empty():
    a = sign_agreement(pd.Series({"A": 0.01, "B": np.nan}))
    assert a["n"] == 1
    assert sign_agreement(pd.Series(dtype="float64")) == {
        "agreement_pct": 0.0, "net": 0, "n": 0, "n_up": 0, "n_down": 0, "n_flat": 0}


def test_direction_sign_is_mixed_below_the_agreement_bar(golden):
    d = golden["direction"]
    if d["agreement_pct"] < GP.SIGN_AGREEMENT_MIN:
        assert d["sign"] == "mixed"


def test_no_active_members_reads_mixed_at_zero_agreement():
    """A basket where nothing moved: agreement is 0.0 over an empty set and the label
    is `mixed` — not a coin-flip direction on an empty cross-section."""
    tk = [f"Q{i:02d}" for i in range(8)]
    idx = _idx()
    panel, _ = _panel(tk, idx)
    as_of = panel["index"].max()
    panel["active"].loc[as_of, :] = False
    obj = _assemble("quiet", _basket(tk), panel)
    assert obj["participation"]["activity_n"] == 0
    assert obj["direction"]["agreement_pct"] == 0.0
    assert obj["direction"]["sign"] == "mixed"
    assert obj["direction"]["leader"] is None


# ---------------------------------------------------------------------------
# (8) authority + banned vocabulary
# ---------------------------------------------------------------------------

def test_authority_block_is_context_only():
    assert GP.AUTHORITY["tier"] == "display"
    assert GP.AUTHORITY["authority"] == "context_only"
    for k in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert GP.AUTHORITY[k] is False, k


def test_module_carries_no_banned_vocabulary():
    from pathlib import Path
    src = Path(GP.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bvalidated\b", src, re.I), "the word 'validated' is CI-guarded"
    assert not re.search(r"ignit(e|ed|ing|ion)", src, re.I), "no ignition vocabulary"


def test_module_declares_no_scoring_authority():
    """The assembler must not import a ranker/gate/sizer — organ-cluster extension,
    not a new scorer (R-TIL-9)."""
    from pathlib import Path
    src = Path(GP.__file__).read_text(encoding="utf-8")
    for banned in ("basket_score", "theme_scoring", "confluence_tiers", "alert_triage"):
        assert f"import {banned}" not in src and f"from engine.{banned}" not in src


# ---------------------------------------------------------------------------
# (9) wiring — an organ nothing calls is an organ that ships dark
# ---------------------------------------------------------------------------

def _build_baskets_src() -> str:
    from pathlib import Path
    p = Path(GP.__file__).resolve().parent.parent / "scripts" / "build_baskets.py"
    return p.read_text(encoding="utf-8")


def test_the_nightly_builder_calls_group_pulse():
    src = _build_baskets_src()
    assert "from engine.group_pulse import run" in src, \
        "group_pulse is not wired into scripts/build_baskets.py — it would ship dark"


def test_the_hook_sits_after_the_basket_level_producers():
    """Membership + the member tape must be fresh before this reads them, which is
    exactly why the hook sits after the flow lens rather than at the top of main()."""
    src = _build_baskets_src()
    assert src.index("from engine.group_flow import compute_group_flows") < \
        src.index("from engine.group_pulse import run")


def test_the_hook_can_never_break_the_nightly():
    """Additive law: the whole call sits in its own try/except and annotates with a
    BARE print at column 0 (a logger would prefix the record and GitHub would drop
    the annotation silently)."""
    src = _build_baskets_src()
    block = src[src.index("from engine.group_pulse import run"):]
    block = block[:block.index("\n    # ", 10)] if "\n    # " in block[10:] else block
    assert "except Exception as _gp_exc" in block
    ann = [ln for ln in block.splitlines() if "group-pulse" in ln and "::warning" in ln]
    assert ann, "the failure path must annotate"
    assert ann[0].lstrip().startswith(('print(f"::warning', 'print("::warning')), ann[0]


def test_the_ledger_gate_uses_the_shared_house_definition():
    """The lane gate must be engine.ledger_lane's single definition, never a local
    re-implementation that can drift from the other nightly ledgers."""
    from pathlib import Path
    src = Path(GP.__file__).read_text(encoding="utf-8")
    assert "from engine.ledger_lane import nightly_advance_enabled" in src
    # The module must not sniff the environment itself — a second reader of the
    # sentinel is a second definition, and the two drift the day one lane changes.
    assert not re.search(r"os\.environ|os\.getenv|getenv\(", src), \
        "the gate must be read through ledger_lane, not by sniffing the env here"


# ---------------------------------------------------------------------------
# (10) the episode block — an open episode inside its grace window
# ---------------------------------------------------------------------------


def test_an_inactive_session_inside_the_grace_window_keeps_its_start_date():
    """`active_now: false` carrying a `current_start` is the CONTRACT, not a contradiction.

    EPISODE_MAX_GAP (2) lets an open episode survive a couple of inactive sessions, so
    "the episode has not closed, but the basket is not participating today" is a real
    state — and a state with a start date, because the episode it belongs to is still
    the open one.  The 2026-08-10 competitive audit read the pair as an inconsistency
    (F-9d) and proposed nulling `current_start` whenever `active_now` is false.  That
    would delete the only record of WHICH episode is open, and would leave
    `sessions_active` — read from the very same open row — printing a positive count
    against no start date: a worse contradiction than the one it set out to remove.
    Pinned here so the "fix" cannot be applied by a later wave reading that audit.
    """
    tk = [f"M{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx())
    basket = _basket(tk)
    as_of = panel["index"].max()
    frames = GP.basket_frames(basket, panel, as_of)
    sessions = list(frames["daily"].index)
    # An OPEN episode whose last ACTIVE session is two before as_of: inside the grace
    # window, so it has not closed, while today itself reads inactive.
    start, last_active = sessions[-6], sessions[-3]
    eps = [{"episode_id": f"grace:{start:%Y-%m-%d}", "closed": False,
            "start_date": f"{start:%Y-%m-%d}", "end_date": f"{last_active:%Y-%m-%d}",
            "sessions_active": 4}]
    obj = GP.basket_pulse("grace", basket, panel, as_of,
                          GP.member_washouts(panel["closes"]),
                          {t: 2 for t in panel["closes"].columns},
                          "2026-06-30T00:00:00+00:00", frames, eps)
    episode = obj["episode"]
    assert episode["active_now"] is False, "as_of is not an active session of the episode"
    assert episode["current_start"] == f"{start:%Y-%m-%d}", \
        "the open episode lost its start date — see the docstring before 'fixing' this"
    assert episode["sessions_active"] == 4
    # and the pair is LEGAL: the contract validator does not treat it as a violation
    assert GP.validate_pulse(obj) == []
