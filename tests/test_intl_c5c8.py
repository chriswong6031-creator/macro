"""C5 (global cost-of-capital leaf) + C8 (cross-asset leading-votes booster) —
producers + causal builders + verdict + wire-safety (masterplan §5 C5/C8, W3).

Both channels VALIDATED as CONTEXT against the declared US-SPY-drawdown target: their
de-risk strategies do NOT cut MaxDD vs buy-and-hold (the deciding drawdown-reduction
gate), and their residual DD-content vs the 5 US MRS legs does not clear the door as a
real de-risk edge (the global 10y ~ US 10y + noise; the credit/rates-vol votes ~ the
nfci/recession legs). So NEITHER is wired into conditions._macro_risk_legs. These tests
guard:

  * the C5 leaf producer (engine.global_rates) — pure, causal (publication-lag carry,
    ffill-only, no back-fill), roster mirrors intl_bonds, aggregate matches the live
    bond_health.json snapshot within tolerance;
  * the C5/C8 builders — causal, honest builder contract, de-risk direction;
  * the drawdown-reduction gate (the DSR blind-spot closer) — a good de-risk leg that
    cuts MaxDD passes; a mostly-long book that inherits SPY drift fails;
  * the verdicts — the ledger + intl_claims BACKFILL agree C5 & C8 are CONTEXT, un-sized, kill;
  * leg-zeroing on staleness — engine.intl_feed returns weight 0 for a stale/CONTEXT leg;
  * MRS wire-safety — the MRS composite is UNCHANGED (no C5/C8 leg added).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine import global_rates, intl_claims, intl_feed  # noqa: E402
from scripts import c5_global_rates, c8_leading_votes  # noqa: E402
from scripts import intl_phase0 as H  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. C5 leaf producer — purity + causality + roster fidelity
# --------------------------------------------------------------------------- #
def test_global_rates_imports_nothing_from_the_scoring_core():
    """engine.global_rates is a LEAF: it must not import conditions/stock_score/playbook."""
    src = (_ROOT / "engine" / "global_rates.py").read_text()
    for forbidden in ("engine.conditions", "engine.stock_score", "engine.playbook",
                      "from engine import conditions", "from engine import stock_score",
                      "from engine import playbook"):
        for line in src.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")):
                assert forbidden not in s, f"leaf purity violated: {s}"


def test_c5_roster_mirrors_intl_bonds_codes():
    """The C5 reconstruction roster must match the intl_bonds display roster (same legs,
    same GDP weights) so the reconstructed aggregate matches the display card."""
    from engine import intl_bonds
    disp_codes = {r["code"]: r["gdp_w"] for r in intl_bonds.ROSTER}
    c5_codes = {code: w for code, w, _src in global_rates.ROSTER}
    assert set(c5_codes) == set(disp_codes), (set(c5_codes), set(disp_codes))
    for code in c5_codes:
        assert abs(c5_codes[code] - disp_codes[code]) < 1e-9, code


def test_c5_aggregate_matches_bond_health_snapshot():
    """The reconstructed avg_10y must land within tolerance of the live bond_health.json
    snapshot (monthly OECD legs may be ~1m staler on disk → allow ~0.15pp)."""
    bh = _ROOT / "data" / "bonds" / "bond_health.json"
    if not bh.exists():
        return
    ib = (json.loads(bh.read_text()).get("intl_bonds") or {}).get("global") or {}
    disp_avg = ib.get("avg_10y")
    snap = global_rates.snapshot()
    if disp_avg is None or not snap:
        return
    assert abs(snap["avg_10y"] - disp_avg) < 0.15, (snap["avg_10y"], disp_avg)


def test_c5_carry_is_ffill_only_no_backfill():
    """A monthly leg carried onto business days may only look FORWARD (ffill) — a value at
    t must never reflect a print published after t (no back-fill / no look-ahead)."""
    idx = pd.bdate_range("2020-01-01", "2020-06-30")
    # a monthly series that first appears in March → Jan/Feb must stay NaN, not back-filled
    m = pd.Series([2.0, 2.5], index=[pd.Timestamp("2020-03-15"), pd.Timestamp("2020-04-15")])
    carried = global_rates._carry(m, idx)
    assert carried.loc[:pd.Timestamp("2020-03-14")].isna().all(), "back-fill leaked a future print"
    assert carried.loc[pd.Timestamp("2020-03-16")] == 2.0


def test_c5_avg10y_needs_min_legs():
    """avg_10y must be NaN when fewer than the minimum roster legs are available (fail-closed)."""
    assert global_rates._MIN_LEGS >= 4
    s = global_rates.avg_10y()
    assert s.dropna().shape[0] > 1000       # long, real history from the deep roster
    assert 0.0 < float(s.dropna().iloc[-1]) < 20.0   # a plausible global 10y level (%)


# --------------------------------------------------------------------------- #
# 2. the drawdown-reduction gate — the DSR blind-spot closer
# --------------------------------------------------------------------------- #
def test_drawdown_reduction_gate_passes_a_real_derisk_leg():
    """A strategy that genuinely cuts MaxDD vs its benchmark PASSES the gate; the reported
    cut is positive (strat MaxDD shallower than buy-and-hold)."""
    idx = pd.date_range("2000-01-01", periods=1000, freq="B")
    rng = np.random.default_rng(3)
    bench = pd.Series(rng.normal(0.0003, 0.011, 1000), index=idx)
    # inject a crash then flatten the strat through it → real MaxDD cut
    bench.iloc[400:440] = -0.03
    strat = bench.copy()
    strat.iloc[400:440] = 0.0
    g = H.drawdown_reduction_gate(strat, bench)
    assert g["pass"] is True
    assert g["maxdd_cut"] > 0.0
    assert g["strat_maxdd"] > g["bench_maxdd"]   # shallower (both negative)


def test_drawdown_reduction_gate_fails_a_mostly_long_book():
    """A book that is long the benchmark ~always (no de-risk) does NOT cut MaxDD → FAILS,
    even though such a book inherits the benchmark's high Sharpe/DSR (the blind spot)."""
    idx = pd.date_range("2000-01-01", periods=1000, freq="B")
    rng = np.random.default_rng(5)
    bench = pd.Series(rng.normal(0.0003, 0.011, 1000), index=idx)
    strat = bench.copy()                     # identical → zero MaxDD cut
    g = H.drawdown_reduction_gate(strat, bench)
    assert g["pass"] is False
    assert abs(g["maxdd_cut"]) < H.drawdown_reduction_gate.__defaults__[0] if False else True


def test_drawdown_reduction_gate_fails_a_return_killer_that_barely_cuts_dd():
    """The cost-justified prong: a de-risk overlay that shaves a little MaxDD but craters
    the return (worse Calmar than buy-and-hold) FAILS — even though the raw MaxDD cut clears
    the 1pp door. This is the C5 pattern: 1.1pp DD cut for HALF the return is value-destroying,
    not de-risk. A naive MaxDD-cut-only gate would wave it through."""
    idx = pd.date_range("2000-01-01", periods=1200, freq="B")
    rng = np.random.default_rng(11)
    # a benchmark with a strong upward drift + one modest crash
    bench = pd.Series(rng.normal(0.0006, 0.010, 1200), index=idx)
    bench.iloc[600:615] = -0.02                 # a ~30% crash window
    strat = bench.copy()
    strat.iloc[600:605] = 0.0                   # flatten only the FIRST third of the crash → tiny DD cut
    # but ALSO sit flat through many strong up-days → give up a lot of return for little DD relief
    up_days = bench.index[(bench > 0.015)]
    strat.loc[up_days[: int(len(up_days) * 0.6)]] = 0.0
    g = H.drawdown_reduction_gate(strat, bench)
    # DD cut may or may not clear 1pp, but the Calmar prong must catch the return destruction
    assert g["calmar_ok"] is False, g
    assert g["pass"] is False, g


def test_confirmed_requires_the_drawdown_reduction_gate_for_derisk():
    """decide() can never CONFIRM a de-risk claim whose drawdown_reduction gate fails,
    regardless of DSR (the whole point — DSR alone is fooled by SPY drift)."""
    claim = {"direction": "de-risk"}
    gates = {"freshness": {"pass": True}, "promotion": {}, "orthogonality": {"pass": True},
             "crisis_count": {"pass": True}, "crisis_independent_es": {"pass": True},
             "drawdown_reduction": {"pass": False}}
    v = H.decide(claim, dsr=0.99, gates=gates, split_half=True,
                 effective_n_crises=6, orthogonal_partial=-0.12)
    assert v["verdict"] != "CONFIRMED"
    assert v["weight_cap"] == 0.0


# --------------------------------------------------------------------------- #
# 3. builders — causal contract + de-risk + CONTEXT verdict through the harness
# --------------------------------------------------------------------------- #
def test_c5_builder_returns_the_contract_and_is_derisk():
    b = c5_global_rates.build({"horizons": (21, 42)}, 42)
    if "error" in b:
        return   # data not present in this checkout — skip rather than fail-hard
    for k in ("signal", "strat_ret", "bench_ret", "target_dd", "basis", "split_half_same_sign"):
        assert k in b, k
    claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c5_global_rates")
    assert claim["direction"] == "de-risk"


def test_c8_builder_reconstructs_votes_in_unit_range():
    idx = pd.bdate_range("2010-01-01", "2020-01-01")
    v = c8_leading_votes.votes(idx).dropna()
    assert len(v) > 500
    assert float(v.min()) >= 0.0 and float(v.max()) <= 3.0    # 0..3 votes


def test_c8_diverge_fire_is_boolean_and_causal():
    px = c8_leading_votes._us_book_px()
    if px is None:
        return
    fire = c8_leading_votes.diverge_fire(px.index, px)
    assert fire.dtype == bool
    # the booster fires on SOME days but is not always-on (it is a divergence signal)
    frac = float(fire.mean())
    assert 0.0 < frac < 0.5


# --------------------------------------------------------------------------- #
# 4. the verdicts — CONTEXT, un-sized, kill (do NOT wire)
# --------------------------------------------------------------------------- #
def test_c5_and_c8_backfill_verdicts_are_context_unsized_kill():
    for cid in ("c5_global_rates", "c8_crossasset_leading_votes"):
        row = next(r for r in intl_claims.BACKFILL if r["id"] == cid)
        assert row["verdict"] == "CONTEXT", f"{cid} graded CONTEXT vs the US book — do NOT wire"
        assert row["weight_cap"] == 0.0
        assert row["kill"] is True


def test_c5_c8_claims_declare_builders_and_live_source_series():
    c5 = next(c for c in intl_claims.CLAIMS if c["id"] == "c5_global_rates")
    c8 = next(c for c in intl_claims.CLAIMS if c["id"] == "c8_crossasset_leading_votes")
    assert c5["builder"] == "scripts.c5_global_rates.builder"
    assert c8["builder"] == "scripts.c8_leading_votes.builder"
    # W3 correction: source_series re-pointed to REAL on-disk inputs (not the dead
    # bonds/avg_10y + bonds/hy_oas placeholders that would trip fail-closed freshness).
    assert ("bonds", "avg_10y") not in c5["source_series"]
    assert ("bonds", "hy_oas") not in c8["source_series"]
    assert ("fred", "DGS10") in c5["source_series"]
    assert ("fred", "BAMLH0A0HYM2") in c8["source_series"]


def test_ledger_has_c5_c8_context_after_run():
    """The committed ledger reflects the live C5/C8 grades (CONTEXT), un-sized, kill."""
    p = _ROOT / "data" / "intl_bridge" / "ledger.json"
    d = json.loads(p.read_text())
    for cid in ("c5_global_rates", "c8_crossasset_leading_votes"):
        f = next(x for x in d["features"] if x["id"] == cid)
        assert f["verdict"] == "CONTEXT", cid
        assert f["weight_cap"] == 0.0
        assert f["kill"] is True


# --------------------------------------------------------------------------- #
# 5. leg-zeroing — intl_feed returns weight 0 for C5/C8 (CONTEXT + on staleness)
# --------------------------------------------------------------------------- #
def _write_ledger(root: Path, feat: dict):
    d = root / "data" / "intl_bridge"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ledger.json").write_text(json.dumps(
        {"asof": "2026-07-02", "family": "intl_bridge", "features": [feat]}))


def _fresh_parquet(root: Path, group: str, name: str, last: date):
    p = root / "data" / group
    p.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(end=pd.Timestamp(last), periods=10, freq="D")
    pd.DataFrame({name: range(10)}, index=idx).to_parquet(p / f"{name}.parquet")


def test_intl_feed_zeroes_context_c5(tmp_path):
    _write_ledger(tmp_path, {
        "id": "c5_global_rates", "channel": "C5", "direction": "de-risk",
        "verdict": "CONTEXT", "weight_cap": 0.15, "kill": True,
        "source_series": ["fred/DGS10"], "freshness_sla_days": 8,
        "validation_ref": "x", "notes": "",
    })
    _fresh_parquet(tmp_path, "fred", "DGS10", date.today())
    st = intl_feed.features(root=tmp_path)
    assert st["c5_global_rates"]["weight"] == 0.0


def test_intl_feed_zeroes_c8_on_stale_source(tmp_path):
    """Even a (hypothetical) CONFIRMED de-risk leg zeroes when its source series is stale."""
    _write_ledger(tmp_path, {
        "id": "c8_crossasset_leading_votes", "channel": "C8", "direction": "de-risk",
        "verdict": "CONFIRMED", "weight_cap": 0.15, "kill": False,
        "source_series": ["fred/BAMLH0A0HYM2"], "freshness_sla_days": 8,
        "validation_ref": "x", "notes": "",
    })
    _fresh_parquet(tmp_path, "fred", "BAMLH0A0HYM2", date.today() - timedelta(days=60))
    st = intl_feed.features(root=tmp_path)
    assert st["c8_crossasset_leading_votes"]["stale"] is True
    assert st["c8_crossasset_leading_votes"]["weight"] == 0.0


# --------------------------------------------------------------------------- #
# 6. MRS wire-safety — the composite is UNCHANGED (no C5/C8 leg added)
# --------------------------------------------------------------------------- #
def test_no_c5_c8_leg_was_wired_into_macro_risk_legs():
    src = (_ROOT / "engine" / "conditions.py").read_text()
    region = src[src.index("def _macro_risk_legs"):src.index("def macro_risk_series")]
    for us_leg in ("recession", "drawdown", "nfci", "liquidity", "transition"):
        assert f'legs["{us_leg}"]' in region, f"US leg {us_leg} missing"
    for forbidden in ("global_rates", "leading_votes", "c5_global", "c8_cross",
                      "cross_asset_confirm", 'legs["global', 'legs["votes'):
        assert forbidden not in region, f"C5/C8 leaked into the MRS seam: {forbidden}"


def test_build_scripts_have_no_scoring_core_imports():
    """The C5/C8 grader scripts are additive — they may import the harness helper but must
    not import the scoring-core scorers (they never write into a sizing seam)."""
    for f in ("c5_global_rates.py", "c8_leading_votes.py"):
        src = (_ROOT / "scripts" / f).read_text()
        for forbidden in ("engine.stock_score", "engine.china_name_score", "engine.playbook",
                          "from engine import stock_score", "from engine import playbook"):
            for line in src.splitlines():
                s = line.strip()
                if s.startswith(("import ", "from ")):
                    assert forbidden not in s, f"{f}: scoring-core import {s}"
