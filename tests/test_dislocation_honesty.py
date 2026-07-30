"""Dislocation Gate-1 honesty invariants (engine/dislocation.py).

These pin the fixes for four proven defects, all found by adversarial audit
2026-07-29. Each test names the defect it guards so a regression reads as a
deliberate decision rather than an accident.

1. FAIL-OPEN DEGRADE. The docstring claimed "a missing input degrades to
   verdict=unknown"; in fact a missing or stale Sahm / breakeven read as "leg not
   firing" -> put-present -> buyable_washout, i.e. a data outage produced the
   PERMISSIVE verdict. Now: per-leg staleness budget against each leg's own last
   stamp, `put_state="unknown"` + a `stale_inputs` list on breach, and
   `verdict="unknown"` whenever the verdict would otherwise have been decided by
   the unreadable leg.
2. ROUNDED DISPLAY VALUE RE-TESTED AS A GATE. `vrp_pctile` ships rounded to 2dp,
   so 0.9027 serialized as 0.9 and any consumer re-testing `> 0.90` saw the
   trigger as NOT firing (the live page printed "stress triggers firing" over an
   empty chip row). `inputs.triggers` is the authoritative list and
   `vrp_pctile_raw` carries 4dp.
3. UNSCOPED EVIDENCE. The [+0.3, +6.3] bootstrap CI was measured on the research
   composite (VIX>30 | dd<=-12% | VRP>0.90) which EXCLUDES backwardation, yet it
   was attached to any firing. `evidence_scope` scopes it to what actually fired.
4. GATE-2 "no_signal" READ AS AN IMPLIED GO. "rely on Gate-1" turned an armed
   state into an entry cue; the confirm study covers backwardation episodes only.

No network, no disk writes.

Run as a plain script:  python tests/test_dislocation_honesty.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dislocation as dz  # noqa: E402

_IDX = pd.bdate_range("2024-01-01", "2026-07-29")
_N = len(_IDX)

# A VRP-only firing with both master-switch legs healthy: the live 2026-07-29 shape.
_COND_FIRING = {"risk_appetite": {"vrp_pctile": 0.90271},
                "capitulation": {"active": True, "strong": False,
                                 "signals_firing": ["VRP extreme"]}}
_COND_CALM = {"risk_appetite": {"vrp_pctile": 0.50}, "capitulation": {}}


def _frame(**overrides) -> pd.DataFrame:
    """Synthetic feature frame: rising SPY (no drawdown), calm VIX, contango,
    healthy Sahm and breakeven. Overrides replace a whole column."""
    f = pd.DataFrame(index=_IDX)
    f["SPY"] = np.linspace(400.0, 500.0, _N)
    f["vix"] = 20.7
    f["vix_high"] = 20.9
    f["vix_ratio"] = 0.961          # contango — no backwardation
    f["sahm"] = 0.07                # well under the 0.50 trigger
    f["breakeven_10y"] = 2.24       # under the 2.5% cutoff
    for k, v in overrides.items():
        f[k] = v
    return f


# --------------------------------------------------------------------------- #
# 1. the fail-open degrade
# --------------------------------------------------------------------------- #

def test_baseline_healthy_legs_still_rule():
    """Control: with both legs fresh the gate still rules, so the guard below is
    proving something about staleness and not just refusing everything."""
    s = dz.snapshot(_frame(), _COND_FIRING)
    assert s["verdict"] == "buyable_washout"
    assert s["put_state"] == "put-present"
    assert s["put_state_reliable"] is True
    assert s["stale_inputs"] == []
    assert s["fed_put"] is True


def test_absent_sahm_yields_unknown_not_buyable():
    """DEFECT 1: an absent Sahm used to read as 'no recession' -> buyable_washout."""
    s = dz.snapshot(_frame(sahm=np.nan), _COND_FIRING)
    assert s["verdict"] == "unknown", "absent Sahm must not produce the permissive verdict"
    assert s["put_state"] == "unknown"
    assert s["put_state_reliable"] is False
    assert s["fed_put"] is None, "fed_put must not assert True on an unreadable switch"
    assert any(x.startswith("sahm: absent") for x in s["stale_inputs"])
    assert "unreadable" in s["headline"]


def test_absent_breakeven_yields_unknown_not_buyable():
    s = dz.snapshot(_frame(breakeven_10y=np.nan), _COND_FIRING)
    assert s["verdict"] == "unknown"
    assert s["put_state"] == "unknown"
    assert any(x.startswith("breakeven_10y: absent") for x in s["stale_inputs"])


def test_stale_breakeven_beyond_budget_yields_unknown():
    """A leg that has gone dark past its budget is unreadable even though the last
    carried value is still numerically present."""
    f = _frame()
    f.loc[f.index[-30:], "breakeven_10y"] = np.nan       # 30bd dark, budget 5bd
    s = dz.snapshot(f, _COND_FIRING)
    assert s["verdict"] == "unknown"
    assert s["put_state"] == "unknown"
    msg = "".join(s["stale_inputs"])
    assert "breakeven_10y" in msg and "business days stale" in msg


def test_breakeven_within_budget_still_rules():
    """The budget must not fire on ordinary weekend/holiday gaps."""
    f = _frame()
    f.loc[f.index[-3:], "breakeven_10y"] = np.nan        # 3bd dark, budget 5bd
    s = dz.snapshot(f, _COND_FIRING)
    assert s["verdict"] == "buyable_washout"
    assert s["stale_inputs"] == []


def test_sahm_budget_tolerates_its_monthly_cadence():
    """Sahm is a monthly reference-month series with a ~6-week publication lag; a
    normal vintage (~42bd old) must NOT trip the 70bd budget, while a two-month
    outage must."""
    ok = dz.snapshot(_frame(), _COND_FIRING)
    assert ok["inputs"]["sahm_stale_bd"] is not None
    assert ok["stale_inputs"] == []

    f = _frame()
    f.loc[f.index[-90:], "sahm"] = np.nan                # 90bd > 70bd budget
    bad = dz.snapshot(f, _COND_FIRING)
    assert bad["verdict"] == "unknown"
    assert any(x.startswith("sahm:") for x in bad["stale_inputs"])


def test_calm_verdict_survives_dead_legs():
    """`calm` is decided purely by the stress-trigger OR (VIX / drawdown / VRP /
    term structure) and never consults either put leg, so nulling the verdict on a
    calm day would replace a correct read with a null. put_state still degrades."""
    f = _frame(sahm=np.nan, breakeven_10y=np.nan)
    s = dz.snapshot(f, _COND_CALM)
    assert s["dislocation_active"] is False
    assert s["verdict"] == "calm"
    assert s["put_state"] == "unknown"
    assert s["put_state_reliable"] is False


def test_no_price_data_degrades_without_asserting_a_put_state():
    """The earliest bail-out must carry the same honesty keys, or a consumer deriving
    `put_absent = put_state == "put-absent"` reads an empty payload as put-present."""
    s = dz.snapshot(pd.DataFrame(index=_IDX), None)
    assert s["verdict"] == "unknown"
    assert s["put_state"] == "unknown"
    assert s["put_state_reliable"] is False
    assert s["fed_put"] is None
    assert s["dislocation_active"] is False
    assert s["stale_inputs"]


def test_stale_guard_does_not_flip_a_put_absent_read():
    """The guard nulls a verdict; it must never manufacture one. A genuine
    recession trigger with fresh legs still reads stand_aside."""
    s = dz.snapshot(_frame(sahm=0.80), _COND_FIRING)
    assert s["verdict"] == "stand_aside"
    assert s["put_state"] == "put-absent"
    assert s["put_state_reliable"] is True


# --------------------------------------------------------------------------- #
# 2. the rounded-display-value trap + vintages
# --------------------------------------------------------------------------- #

def test_vrp_raw_is_unrounded_and_triggers_are_authoritative():
    """DEFECT 2: `vrp_pctile` rounds 0.9027 -> 0.9, which is NOT > 0.90. The engine's
    own trigger list must show the firing, and the raw key must keep the precision a
    re-test would need."""
    s = dz.snapshot(_frame(), _COND_FIRING)
    inp = s["inputs"]
    assert inp["vrp_pctile"] == 0.9, "display value is expected to round to 2dp"
    assert not (inp["vrp_pctile"] > 0.90), "re-testing the display value fails — the trap"
    assert inp["vrp_pctile_raw"] == 0.9027
    assert inp["vrp_pctile_raw"] > 0.90
    assert inp["triggers"] == ["VRP extreme"], "the authoritative list must show the firing"
    assert inp["trigger_keys"] == ["vrp_extreme"]
    assert set(inp["trigger_keys"]) <= set(dz.TRIGGER_KEYS)


def test_trigger_keys_track_triggers_one_for_one():
    """The display list and the stable-slug list must stay in lockstep and in the
    canonical TRIGGER_KEYS order. The VIX leg is deliberately left calm: the
    thin-quote sanitizer can legitimately suppress a high VIX by cross-checking the
    front VX future, and that store read is not this test's subject."""
    f = _frame(vix_ratio=1.05)                                   # backwardation
    f["SPY"] = np.concatenate([np.linspace(400.0, 500.0, _N - 40),
                               np.linspace(500.0, 400.0, 40)])   # ~-20% drawdown
    s = dz.snapshot(f, _COND_FIRING)                             # + VRP extreme
    inp = s["inputs"]
    assert len(inp["triggers"]) == len(inp["trigger_keys"]) == 3
    assert inp["trigger_keys"] == ["drawdown", "vrp_extreme", "backwardation"]
    order = {k: i for i, k in enumerate(dz.TRIGGER_KEYS)}
    assert inp["trigger_keys"] == sorted(inp["trigger_keys"], key=order.__getitem__)
    assert "drawdown 20%" in inp["triggers"][0], "display string carries the reading"


def test_master_switch_subreadings_carry_their_own_vintage():
    """Sahm's stamp is its reference month, not the frame's asof — the frame ffills it
    for 70 business days, so stamping off the frame would re-date it as a same-day read."""
    s = dz.snapshot(_frame(), _COND_FIRING)
    inp = s["inputs"]
    for k in ("sahm_asof", "breakeven_asof"):
        assert inp[k] is None or len(inp[k]) == 10, f"{k} must be an ISO date"
    assert inp["sahm_asof_basis"] in ("source", "carried", "absent")
    assert inp["breakeven_asof_basis"] in ("source", "carried", "absent")
    if inp["sahm_asof_basis"] == "source":
        # a monthly series read on a daily frame is necessarily older than today
        assert inp["sahm_stale_bd"] is not None and inp["sahm_stale_bd"] > 0
        assert inp["sahm_asof"] < s["asof"]


# --------------------------------------------------------------------------- #
# 3. evidence scoped to what actually fired
# --------------------------------------------------------------------------- #

def test_evidence_scope_covers_composite_triggers():
    sc = dz.evidence_scope(["vrp_extreme"])
    assert sc["coverage"] == "covered"
    assert sc["not_covered_by_ci"] == []


def test_evidence_scope_refuses_a_backwardation_only_firing():
    """DEFECT 3: backwardation is NOT in the composite the CI was measured on, and was
    separately measured to show no put-present/absent separation."""
    sc = dz.evidence_scope(["backwardation"])
    assert sc["coverage"] == "uncovered"
    assert sc["covered_by_ci"] == [] and sc["not_covered_by_ci"] == ["backwardation"]
    assert "does NOT cover it" in sc["note"]


def test_evidence_scope_partial_when_mixed():
    sc = dz.evidence_scope(["vix_panic", "backwardation"])
    assert sc["coverage"] == "partial"
    assert sc["covered_by_ci"] == ["vix_panic"]
    assert sc["not_covered_by_ci"] == ["backwardation"]


def test_evidence_scope_flags_the_looser_dip():
    """The engine fires at -10% while the composite CI was measured at -12%."""
    sc = dz.evidence_scope(["drawdown"], dd_pct=-10.5)
    assert "−12%" in sc["note"] and "just outside the studied set" in sc["note"]
    deep = dz.evidence_scope(["drawdown"], dd_pct=-18.0)
    assert "just outside the studied set" not in deep["note"]


def test_snapshot_attaches_the_scope_for_the_live_firing():
    s = dz.snapshot(_frame(), _COND_FIRING)
    assert s["evidence_scope"]["coverage"] == "covered"
    s2 = dz.snapshot(_frame(vix_ratio=1.05), _COND_CALM)
    assert s2["inputs"]["trigger_keys"] == ["backwardation"]
    assert s2["evidence_scope"]["coverage"] == "uncovered"


def test_evidence_caveat_names_the_actual_misses():
    """The old caveat claimed the gate caught the 2000/2008/2022 knife. The
    declustered replay shows it refused 2008 but printed buyable in 2000 and 2022."""
    cav = dz.EVIDENCE["caveat"]
    assert "2008" in cav and "2022" in cav
    assert "0.02pp" in cav
    assert "whole edge" not in cav


# --------------------------------------------------------------------------- #
# 4. Gate-2 no_signal is not an implied go
# --------------------------------------------------------------------------- #

def test_gate2_no_signal_does_not_imply_an_entry():
    """DEFECT 4: 'No backwardation to un-invert — rely on Gate-1' read as a go."""
    s = dz.snapshot(_frame(), _COND_FIRING)
    g2 = s["gate2"]
    assert g2["state"] == "no_signal"
    assert "rely on Gate-1" not in g2["label"]
    assert "Do NOT treat Gate-1 alone as an entry signal" in g2["label"]
    assert "backwardation episodes only" in g2["label"]
    assert g2.get("label_zh"), "bilingual law: the reworded label needs its ZH pair"


def test_gate2_carries_distance_to_backwardation():
    s = dz.snapshot(_frame(), _COND_FIRING)
    g2 = s["gate2"]
    assert g2["vix_term"] == 0.961
    assert g2["backwardation_ratio"] == 1.0
    assert abs(g2["distance_to_backwardation"] - 0.039) < 1e-9


def test_gate2_dormant_also_reports_the_distance():
    s = dz.snapshot(_frame(), _COND_CALM)
    assert s["gate2"]["state"] == "dormant"
    assert s["gate2"]["distance_to_backwardation"] is not None


# --------------------------------------------------------------------------- #
# the policy-divergence leg (buyable_washout can coexist with a hawkish Fed)
# --------------------------------------------------------------------------- #

def test_policy_divergence_states_the_test_not_a_policy_conclusion():
    s = dz.snapshot(_frame(), _COND_FIRING)
    assert "inflation not blocking easing" not in s["headline"], (
        "the leg tests a breakeven level; it cannot conclude what the Fed will do")
    assert "10y breakeven 2.24% < 2.5%" in s["headline"]

    dz.attach_policy_divergence(s, {"stance": "hawkish"})
    pd_ = s["policy_divergence"]
    assert pd_ is not None and pd_["stance"] == "hawkish"
    assert "HAWKISH" in pd_["note"] and pd_["note_zh"]
    assert pd_["is_context_only"] is True


def test_policy_divergence_absent_when_stance_agrees_or_missing():
    for stance in (None, {}, {"stance": "dovish"}, {"stance": "neutral"}):
        s = dz.snapshot(_frame(), _COND_FIRING)
        dz.attach_policy_divergence(s, stance)
        assert s["policy_divergence"] is None


def test_policy_divergence_never_raises_and_never_moves_the_verdict():
    s = dz.snapshot(_frame(), _COND_FIRING)
    before = s["verdict"], s["put_state"], s["fed_put"]
    dz.attach_policy_divergence(s, {"stance": "hawkish"})
    assert (s["verdict"], s["put_state"], s["fed_put"]) == before
    assert dz.attach_policy_divergence(None, {"stance": "hawkish"}) is None
    assert dz.attach_policy_divergence("not a dict", None) == "not a dict"


# --------------------------------------------------------------------------- #
# the corrected degrade docstring must stay corrected
# --------------------------------------------------------------------------- #

def test_module_docstring_no_longer_claims_a_universal_unknown_degrade():
    doc = dz.__doc__ or ""
    assert 'a missing input degrades to verdict="unknown"' not in doc.replace("\n", " ")
    assert "DEGRADE CONTRACT" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
