"""tests/test_risk_core_js.py — the WRI book-structure math (templates/risk_core.js).

risk_core.js is a pure, DOM-free ES5 module (masterplan §7). We exercise it the
way the browser does: shell `node` over the module with a synthetic
factor_betas.json-shaped fixture and a weights map, and assert the §7 sanity
anchors hold:

  - 20-name pure-idio equal book      -> ENB ≈ 20
  - single-factor book (all-one bet)  -> ENB -> 1
  - a hedge position                  -> negative MCTR share
  - > 40% of book dollars unmodeled   -> the verdict abstains

plus structural invariants (factor shares sum to ~1, MCTR shares sum to ~1, twin
clustering at ρ ≥ 0.70, stress-lens availability gating, clamp disclosure).

Node is available on the CI runners and dev Macs; the suite skips loudly when it
is not (mirrors tests/test_check_inline_js.py). No network, no build, no site/.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

MODULE = Path(__file__).resolve().parents[1] / "templates" / "risk_core.js"


def _run(js_body: str, data: dict, extra: dict | None = None) -> dict:
    """Load risk_core.js under node, inject `DATA` (+ any `extra` globals as JSON),
    run `js_body`, and parse the single JSON object it prints on stdout."""
    payload = {"DATA": data}
    payload.update(extra or {})
    globs = "\n".join(
        "var %s = %s;" % (k, json.dumps(v)) for k, v in payload.items()
    )
    script = textwrap.dedent(
        """
        var RiskCore = require(%(mod)s);
        %(globs)s
        function OUT(o){ process.stdout.write(JSON.stringify(o)); }
        %(body)s
        """
    ) % {"mod": json.dumps(str(MODULE)), "globs": globs, "body": js_body}
    res = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# Fixture builders — factor_betas.json-shaped (9 factors, nested cov dict)
# ---------------------------------------------------------------------------
FACTORS = [
    {"key": "mkt"}, {"key": "growth"}, {"key": "size"}, {"key": "rates"},
    {"key": "usd"}, {"key": "oil"}, {"key": "china"}, {"key": "btc"}, {"key": "gold"},
]
FKEYS = [f["key"] for f in FACTORS]


def _diag_cov(var_by_key: dict) -> dict:
    """Nested-dict factor covariance {k -> {j -> cov}}, diagonal only."""
    return {a: {b: (var_by_key.get(a, 0.0) if a == b else 0.0) for b in FKEYS} for a in FKEYS}


def _zero_betas() -> dict:
    return {k: 0.0 for k in FKEYS}


def _pure_idio_data(n: int, idio_vol: float = 0.30) -> dict:
    """n names with ZERO factor loadings (all risk idiosyncratic) + a real (but
    irrelevant, since betas are 0) factor cov. Each name is its own bet."""
    betas = {}
    for i in range(n):
        b = _zero_betas()
        b["idio_vol"] = idio_vol
        betas["N%02d" % i] = b
    # nonzero factor variances so the model is well-formed; betas=0 => no factor risk
    cov = _diag_cov({k: 0.02 for k in FKEYS})
    return {"factors": FACTORS, "factor_cov": cov, "betas": betas}


def _single_factor_data(n: int) -> dict:
    """n names ALL loading 1.0 on growth only, with NO idio vol -> one bet."""
    betas = {}
    for i in range(n):
        b = _zero_betas()
        b["growth"] = 1.0
        b["idio_vol"] = 0.0
        betas["G%02d" % i] = b
    cov = _diag_cov({"growth": 0.05})  # only growth carries variance
    return {"factors": FACTORS, "factor_cov": cov, "betas": betas}


def _hedge_data() -> dict:
    """3 names load +1 on growth, one loads -1 (moves against the book) -> the
    contrarian name must carry a NEGATIVE MCTR share."""
    betas = {}
    for t in ("A", "B", "C"):
        b = _zero_betas(); b["growth"] = 1.0; b["idio_vol"] = 0.10; betas[t] = b
    h = _zero_betas(); h["growth"] = -1.0; h["idio_vol"] = 0.10; betas["HEDGE"] = h
    cov = _diag_cov({"growth": 0.05})
    return {"factors": FACTORS, "factor_cov": cov, "betas": betas}


def _twin_data() -> dict:
    """Two names on growth (twins), one on oil (independent)."""
    betas = {}
    for t in ("TW1", "TW2"):
        b = _zero_betas(); b["growth"] = 1.2; b["idio_vol"] = 0.05; betas[t] = b
    o = _zero_betas(); o["oil"] = 1.0; o["idio_vol"] = 0.05; betas["OILY"] = o
    cov = _diag_cov({"growth": 0.05, "oil": 0.20})
    return {"factors": FACTORS, "factor_cov": cov, "betas": betas}


def _eqw(tickers) -> dict:
    return {t: 1.0 for t in tickers}


# ===========================================================================
# §7 SANITY ANCHORS
# ===========================================================================
@needs_node
def test_enb_pure_idio_equal_book_approx_n():
    """20 uncorrelated equal-weight names -> ENB ≈ 20 (the free-lunch ceiling)."""
    data = _pure_idio_data(20)
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); OUT({ok:r.ok, enb:r.enb, "
        "held:r.held.length, idioTot:r.idioShareTotal, fsum:Object.keys(r.factorShare)"
        ".reduce(function(a,k){return a+r.factorShare[k];},0)});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["ok"] is True
    assert out["held"] == 20
    assert out["enb"] == pytest.approx(20, abs=0.2), out
    assert out["idioTot"] == pytest.approx(1.0, abs=1e-6)   # all risk is idio
    assert out["fsum"] == pytest.approx(0.0, abs=1e-9)      # no factor risk


@needs_node
def test_enb_single_factor_book_goes_to_one():
    """8 names all = the same single-factor bet, no idio -> ENB -> 1."""
    data = _single_factor_data(8)
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); OUT({ok:r.ok, enb:r.enb, "
        "top:r.topFactor, topShare:r.topFactorShare, state:RiskCore.enbState(r.enb)});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["ok"] is True
    assert out["enb"] == pytest.approx(1.0, abs=1e-6), out
    assert out["top"] == "growth"
    assert out["topShare"] == pytest.approx(1.0, abs=1e-9)
    assert out["state"] == "one"


@needs_node
def test_hedge_position_has_negative_mctr_share():
    """A name loading opposite the book carries a negative risk contribution
    (share sums still to 1 across positions)."""
    data = _hedge_data()
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); "
        "var sum=0; r.held.forEach(function(t){sum+=r.mctrShare[t];}); "
        "OUT({ok:r.ok, hedge:r.mctrShare['HEDGE'], a:r.mctrShare['A'], sum:sum});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["ok"] is True
    assert out["hedge"] < 0, f"hedge MCTR share must be negative: {out}"
    assert out["a"] > 0
    assert out["sum"] == pytest.approx(1.0, abs=1e-6), out   # Euler additivity


@needs_node
def test_abstain_when_unmodeled_dollars_exceed_40pct():
    """A book that is >40% unmodeled dollars must abstain (no false state)."""
    data = _twin_data()  # TW1/TW2/OILY are modeled
    # 3 modeled names at $10 each ($30) + one unmodeled future at $80 -> 72.7% unmodeled
    wmap = {"TW1": 10.0, "TW2": 10.0, "OILY": 10.0, "GC=F": 80.0}
    out = _run(
        "var c = RiskCore.coverage(DATA, W); OUT({abstain:c.abstain, "
        "unfrac:c.unmodeledFrac, unmodeled:c.unmodeled, modeled:c.modeled});",
        data, {"W": wmap},
    )
    assert out["abstain"] is True, out
    assert out["unfrac"] == pytest.approx(80.0 / 110.0, abs=1e-6)
    assert out["unmodeled"] == ["GC=F"]
    assert sorted(out["modeled"]) == ["OILY", "TW1", "TW2"]


# ===========================================================================
# Structural invariants
# ===========================================================================
@needs_node
def test_factor_and_mctr_shares_sum_to_one_on_mixed_book():
    data = _twin_data()
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); "
        "var fs=r.idioShareTotal; r.keys.forEach(function(k){fs+=r.factorShare[k];}); "
        "var ms=0; r.held.forEach(function(t){ms+=r.mctrShare[t];}); "
        "OUT({ok:r.ok, factorPlusIdio:fs, mctrSum:ms, enb:r.enb});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["ok"] is True
    assert out["factorPlusIdio"] == pytest.approx(1.0, abs=1e-6), out
    assert out["mctrSum"] == pytest.approx(1.0, abs=1e-6), out
    assert out["enb"] > 1.0  # a mixed book is more than one bet


@needs_node
def test_twins_cluster_at_070_threshold():
    """The two growth names form one cluster; the oil name stands alone."""
    data = _twin_data()
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); "
        "var big = r.clusters.map(function(c){return c.members.slice().sort();}); "
        "OUT({ok:r.ok, clusters:big, pairs:r.twinPairs.map(function(p){return "
        "[p.a,p.b,Math.round(p.rho*100)/100];})});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["ok"] is True
    # exactly one 2-member cluster {TW1,TW2} and one singleton {OILY}
    sizes = sorted(len(c) for c in out["clusters"])
    assert sizes == [1, 2], out
    twin = [c for c in out["clusters"] if len(c) == 2][0]
    assert twin == ["TW1", "TW2"], out
    # TW1~TW2 correlation is the only ≥0.70 pair
    assert len(out["pairs"]) == 1 and out["pairs"][0][2] >= 0.70, out


@needs_node
def test_thin_book_under_two_modeled_names_is_not_ok():
    data = _twin_data()
    out = _run(
        "var r = RiskCore.book(DATA, W, 'calm'); OUT({ok:r.ok, reason:r.reason});",
        data, {"W": {"TW1": 10.0, "GC=F": 90.0}},   # only 1 modeled name
    )
    assert out["ok"] is False
    assert out["reason"] == "thin"


# ===========================================================================
# Stress lens gating (W1 emit block may be absent locally)
# ===========================================================================
@needs_node
def test_stress_unavailable_when_no_stress_block():
    data = _twin_data()  # no factor_cov_stress
    out = _run(
        "OUT({avail:RiskCore.stressAvailable(DATA), "
        "readLens:RiskCore.read(DATA, W).defaultLens, "
        "hasStress:RiskCore.read(DATA, W).hasStress});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["avail"] is False
    assert out["hasStress"] is False
    assert out["readLens"] == "calm"   # falls back to calm; UI hides the toggle


@needs_node
def test_stress_meta_available_false_forces_calm_even_with_block():
    data = _twin_data()
    data["factor_cov_stress"] = _diag_cov({"growth": 0.09, "oil": 0.30})
    data["stress_meta"] = {"available": False}   # explicit off-switch
    out = _run("OUT({avail:RiskCore.stressAvailable(DATA)});", data)
    assert out["avail"] is False


@needs_node
def test_stress_lens_reads_when_block_present_and_diverges():
    """With a stress cov that lifts growth co-movement, the growth-heavy book's
    stress ENB should be ≤ its calm ENB (co-movement concentrates risk)."""
    data = _twin_data()
    # stress: growth variance up sharply (names move together harder in selloffs)
    data["factor_cov_stress"] = _diag_cov({"growth": 0.20, "oil": 0.20})
    out = _run(
        "var R = RiskCore.read(DATA, W); "
        "OUT({avail:R.hasStress, lens:R.defaultLens, calmEnb:R.calm.enb, "
        "stressEnb:R.stress?R.stress.enb:null});",
        data, {"W": _eqw(list(data["betas"].keys()))},
    )
    assert out["avail"] is True
    assert out["lens"] == "stress"           # default leads with stress (WRI-R7)
    assert out["stressEnb"] is not None
    assert out["stressEnb"] <= out["calmEnb"] + 1e-9, out


@needs_node
def test_no_model_returns_not_ok():
    out = _run("OUT(RiskCore.book(DATA, {}, 'calm'));", {"factors": FACTORS})
    assert out["ok"] is False
    assert out["reason"] == "no-model"


# ===========================================================================
# whatIf — the W4 pre-trade diagnostic (WRI-R3, operator-signed NWP-U18)
# ===========================================================================
# The user proposes ONE candidate; whatIf() prints the SAME descriptive stats
# for the hypothetical book (before/after book() results) — pure composition of
# book(), no new estimator, no advice. These lock the three properties the brief
# names: delta symmetry (removing the candidate restores before), unmodeled ->
# honest null, hedge candidate -> negative contribution.
@needs_node
def test_whatif_removing_candidate_restores_before():
    """Delta symmetry: dollars<=0 (or absent ticker) => after === before, exactly.
    The 'after' book must be byte-identical to 'before' on the reads the surface
    prints (ENB, top-factor share, held set)."""
    data = _twin_data()
    W = _eqw(list(data["betas"].keys()))
    out = _run(
        # dollars=0 must be a no-op; also an absent ticker is a no-op.
        "var a = RiskCore.whatIf(DATA, W, 'OILY', 0, 'calm'); "
        "var b = RiskCore.whatIf(DATA, W, 'NOPE', 5000, 'calm'); "
        "OUT({"
        "  zeroSame: (a.after.enb===a.before.enb && a.after.topFactorShare===a.before.topFactorShare "
        "             && a.after.held.length===a.before.held.length), "
        "  zeroModeledCand: a.modeled, "                      # OILY is modeled...
        "  zeroDollars: a.dollars, "                          # ...but 0 dollars => no-op
        "  absentSame: (b.after.enb===b.before.enb && b.after.held.length===b.before.held.length), "
        "  absentModeled: b.modeled"                          # NOPE is not in the model
        "});",
        data, {"W": W},
    )
    assert out["zeroSame"] is True, out
    assert out["zeroModeledCand"] is True     # candidate IS modeled
    assert out["zeroDollars"] == 0            # but proposed size is 0 -> after==before
    assert out["absentSame"] is True, out
    assert out["absentModeled"] is False


@needs_node
def test_whatif_unmodeled_candidate_is_honest_null():
    """A candidate absent from the factor model never fabricates numbers: after
    === before, modeled:false, and the candidate carries no invented role."""
    data = _twin_data()  # TW1/TW2/OILY modeled; GC=F is not
    W = _eqw(list(data["betas"].keys()))
    out = _run(
        "var r = RiskCore.whatIf(DATA, W, 'GC=F', 12000, 'calm'); "
        "OUT({ok:r.ok, modeled:r.modeled, "
        "sameEnb:(r.after.enb===r.before.enb), "
        "sameHeld:(r.after.held.length===r.before.held.length), "
        "candShare:r.candidate.mctrShare, candFactor:r.candidate.topFactor, "
        "candTwins:r.candidate.twinWith.length});",
        data, {"W": W},
    )
    assert out["ok"] is True
    assert out["modeled"] is False, out
    assert out["sameEnb"] is True, out        # unmodeled dollars can't move the factor math
    assert out["sameHeld"] is True, out
    assert out["candShare"] is None           # no invented contribution
    assert out["candFactor"] is None
    assert out["candTwins"] == 0


@needs_node
def test_whatif_hedge_candidate_has_negative_contribution():
    """Proposing a candidate that loads OPPOSITE the book carries a negative MCTR
    share in the after-book (the 'would lean against the rest of the book' case)."""
    # book is 3 growth-longs; the candidate loads -1 on growth (a hedge). Dollar
    # sizes are COMPARABLE ($10k book names, $10k candidate) so the hedge isn't
    # swamped and the after-book stays net-long growth.
    betas = {}
    for t in ("A", "B", "C"):
        b = _zero_betas(); b["growth"] = 1.0; b["idio_vol"] = 0.10; betas[t] = b
    h = _zero_betas(); h["growth"] = -1.0; h["idio_vol"] = 0.10; betas["SH"] = h
    data = {"factors": FACTORS, "factor_cov": _diag_cov({"growth": 0.05}), "betas": betas}
    W = {"A": 10000.0, "B": 10000.0, "C": 10000.0}   # candidate SH is NOT in the current book
    out = _run(
        "var r = RiskCore.whatIf(DATA, W, 'SH', 10000, 'calm'); "
        "OUT({modeled:r.modeled, hedge:r.candidate.hedge, "
        "candShare:r.candidate.mctrShare, rank:r.candidate.rank, "
        "beforeHeld:r.before.held.length, afterHeld:r.after.held.length});",
        data, {"W": W},
    )
    assert out["modeled"] is True
    assert out["hedge"] is True, out
    assert out["candShare"] < 0, out          # negative risk contribution
    assert out["beforeHeld"] == 3 and out["afterHeld"] == 4   # candidate joined the book
    assert out["rank"] >= 1                    # it has a rank in the after-book


@needs_node
def test_whatif_modeled_add_shifts_enb_and_factor_share():
    """Adding an INDEPENDENT modeled name (oil) to a growth-only book should raise
    ENB (more independent bets) and lower the top factor's share — the descriptive
    delta the surface prints. Adding a same-factor name concentrates instead."""
    data = _twin_data()  # TW1/TW2 = growth twins, OILY = oil
    Wg = {"TW1": 10000.0, "TW2": 10000.0}  # book is two growth twins (one bet)
    out = _run(
        # add a COMPARABLY-sized independent oil name -> more diversified
        "var ind = RiskCore.whatIf(DATA, W, 'OILY', 10000, 'calm'); "
        # add another growth name (clone of TW1's loadings) -> more concentrated
        "OUT({"
        "  beforeEnb: ind.before.enb, afterEnbIndep: ind.after.enb, "
        "  beforeTop: ind.before.topFactor, beforeTopShare: ind.before.topFactorShare, "
        "  afterTopShareIndep: ind.after.topFactorShare, "
        "  candFactor: ind.candidate.topFactor, candRank: ind.candidate.rank"
        "});",
        data, {"W": Wg},
    )
    assert out["beforeTop"] == "growth"
    # an independent oil name raises the effective bet count and dilutes growth's share
    assert out["afterEnbIndep"] > out["beforeEnb"], out
    assert out["afterTopShareIndep"] < out["beforeTopShare"], out
    assert out["candFactor"] == "oil", out     # the candidate is driven by oil
    assert out["candRank"] >= 1


@needs_node
def test_whatif_respects_stress_lens():
    """The what-if is computed under the SAME lens the surface shows: a stress cov
    that lifts growth co-movement makes the after-book's stress ENB <= its calm ENB
    for the same proposed candidate."""
    data = _twin_data()
    # stress lifts growth co-movement 4x (0.05->0.20) while oil is unchanged, so a
    # growth-heavy after-book concentrates harder in selloffs.
    data["factor_cov_stress"] = _diag_cov({"growth": 0.20, "oil": 0.20})
    Wg = {"TW1": 10000.0, "TW2": 10000.0}
    out = _run(
        "var calm = RiskCore.whatIf(DATA, W, 'OILY', 10000, 'calm'); "
        "var stress = RiskCore.whatIf(DATA, W, 'OILY', 10000, 'stress'); "
        "OUT({calmLens:calm.lens, stressLens:stress.lens, "
        "calmAfterEnb:calm.after.enb, stressAfterEnb:stress.after.enb});",
        data, {"W": Wg},
    )
    assert out["calmLens"] == "calm"
    assert out["stressLens"] == "stress"       # honored the requested lens (block present)
    assert out["stressAfterEnb"] <= out["calmAfterEnb"] + 1e-9, out


@needs_node
def test_whatif_stress_request_falls_back_to_calm_without_block():
    """Asking for the stress lens when no stress cov ships must silently fall back
    to calm (never crash) — the UI only shows the toggle when stress is available."""
    data = _twin_data()  # no factor_cov_stress
    Wg = _eqw(["TW1", "TW2"])
    out = _run(
        "var r = RiskCore.whatIf(DATA, W, 'OILY', 10000, 'stress'); "
        "OUT({lens:r.lens, ok:r.ok, afterOk:r.after.ok});",
        data, {"W": Wg},
    )
    assert out["ok"] is True
    assert out["lens"] == "calm", out          # fell back
    assert out["afterOk"] is True


# ===========================================================================
# factorBets — the patch-bay PICTURE grouping (by dominant factor)
# ===========================================================================
@needs_node
def test_factor_bets_groups_shared_factor_names_and_splits_idio():
    """Two names dominated by growth group into one bet; an oil name and an
    idio-dominated name each form their own bet."""
    betas = {}
    for t in ("G1", "G2"):
        b = _zero_betas(); b["growth"] = 1.5; b["idio_vol"] = 0.05; betas[t] = b   # growth-dominant
    o = _zero_betas(); o["oil"] = 1.2; o["idio_vol"] = 0.05; betas["OILY"] = o     # oil-dominant
    idio = _zero_betas(); idio["mkt"] = 0.1; idio["idio_vol"] = 0.60; betas["LONE"] = idio  # idio-dominant
    data = {"factors": FACTORS, "factor_cov": _diag_cov({"growth": 0.06, "oil": 0.20, "mkt": 0.016}), "betas": betas}
    out = _run(
        "var b = RiskCore.book(DATA, W, 'calm'); var bets = RiskCore.factorBets(b, 0.25); "
        "OUT({n:bets.length, groups:bets.map(function(g){return {factor:g.factor, "
        "members:g.members.slice().sort()};})});",
        data, {"W": _eqw(list(betas.keys()))},
    )
    # growth bet {G1,G2}, oil bet {OILY}, and LONE as its own idio bet
    facs = {}
    for g in out["groups"]:
        facs[g["factor"] or "idio"] = g["members"]
    assert facs.get("growth") == ["G1", "G2"], out
    assert facs.get("oil") == ["OILY"], out
    # LONE (60% idio) is NOT lumped into any factor bet
    assert ["LONE"] in [g["members"] for g in out["groups"]], out
    assert out["n"] == 3, out
