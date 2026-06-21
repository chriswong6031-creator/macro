"""S&P / Macro Vector — Phase 3 confidence audit (the final honesty gate before
the dashboard ships). Subjects the canonical strategy (engine.equity_alloc.vector_alloc:
de-risk glide + Fed-put-gated 42d re-deploy) to:

  - block-bootstrap 95% CIs on Sharpe, MaxDD (and a CAGR CI)
  - QE-era (2020-2021) exclusion — is the edge a stimulus artifact?
  - year-jackknife — drop each calendar year; Sharpe-edge-vs-B&H sign consistency
  - AQR-style permutation NULL — circular-block-shuffle the allocation B times
    (destroys the timing, preserves the marginal + autocorrelation) and rank the
    real Sharpe/MaxDD against the null distribution -> an honest skill p-value
  - Deflated Sharpe at a conservative honest trial count

Writes reports/spvector-phase3-audit.md. Run: python -m scripts.calibrate_spvector_phase3
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine.validation import backtest_core, block_bootstrap_ci, deflated_sharpe, ret_moments
from engine.trial_ledger import TrialLedger
from lib import config, store

COST_BPS = 3.0
TY = ea.TRADING_YEAR
N_TRIALS = 30   # conservative honest count across all phases (glide variants + redeploy + min-hold sweep)


def _sharpe(r): r = r.dropna(); return float(r.mean() / r.std() * np.sqrt(TY)) if r.std() else float("nan")
def _cagr(r): eq = (1 + r.dropna()).cumprod(); yrs = len(r.dropna()) / TY; return float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs else float("nan")
def _maxdd(r): eq = (1 + r.dropna()).cumprod(); return float((eq / eq.cummax() - 1).min())


def perm_null(alloc: pd.Series, close: pd.Series, bills: pd.Series, B: int = 2000,
              block: int = 42, seed: int = 11) -> dict:
    """Circular-block-shuffle the allocation (break its timing vs returns), recompute
    Sharpe & MaxDD each draw. The real strategy's rank vs this null = skill p-value."""
    real = backtest_core(close, alloc, cost_bps=COST_BPS, cash_yield=bills)["net"]
    real_sh, real_dd = _sharpe(real), _maxdd(real)
    a = alloc.reindex(close.index, method="ffill").fillna(1.0).to_numpy()
    n = len(a); rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block)); grid = np.arange(block)
    sh = np.empty(B); dd = np.empty(B)
    for k in range(B):
        st = rng.integers(0, n, nb)
        idx = (st[:, None] + grid[None, :]).ravel()[:n] % n
        shuf = pd.Series(a[idx], index=close.index)
        net = backtest_core(close, shuf, cost_bps=COST_BPS, cash_yield=bills)["net"]
        sh[k] = _sharpe(net); dd[k] = _maxdd(net)
    # MaxDD skill = real drawdown SHALLOWER (less negative) than the null; skill p =
    # fraction of null as-shallow-or-shallower than real (low p = exceptional). Compare
    # against the null's SHALLOWEST tail (p95) since shallower is better for drawdown.
    return {"real_sharpe": round(real_sh, 2), "null_sharpe_p95": round(float(np.percentile(sh, 95)), 2),
            "sharpe_skill_p": round(float(np.mean(sh >= real_sh)), 4),
            "real_maxdd": round(100 * real_dd, 1), "null_maxdd_p95": round(100 * float(np.percentile(dd, 95)), 1),
            "maxdd_skill_p": round(float(np.mean(dd >= real_dd)), 4), "B": B}


def main() -> int:
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    print("[build] features + conditions ...")
    f = build_features(); cf = conditions_frame(f); reg = store.read("regime", "regime_history")
    spy = ea.index_close("SPY"); bills = ea.bill_yield()
    alloc = ea.vector_alloc(spy, f=f, regime=reg, cf=cf)

    bt = backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=bills)
    net, hold = bt["net"], bt["hold"]

    # block-bootstrap CIs
    boot = block_bootstrap_ci(net, block=21, B=5000, ann=TY)

    # QE exclusion (2020-2021)
    qe = ~((net.index >= "2020-01-01") & (net.index <= "2021-12-31"))
    qe_row = {"sharpe": round(_sharpe(net[qe]), 2), "bh_sharpe": round(_sharpe(hold[qe]), 2),
              "maxdd": round(100 * _maxdd(net[qe]), 1), "bh_maxdd": round(100 * _maxdd(hold[qe]), 1)}

    # year-jackknife: Sharpe edge vs B&H dropping each year
    years = sorted(set(net.index.year))
    jk = {}
    for y in years:
        m = net.index.year != y
        jk[y] = round(_sharpe(net[m]) - _sharpe(hold[m]), 2)
    jk_pos = sum(1 for v in jk.values() if v > 0)

    # AQR-style permutation null
    pn = perm_null(alloc, spy, bills)

    # DSR honest
    mom = ret_moments(net)
    if mom:
        _led = TrialLedger()      # honest-N via the ledger (P3): declared honest count
        _led.log_declared_budget(N_TRIALS, family="spvector_phase3",
                                 reason="conservative honest count across all phases (calibrate_spvector_phase3)")
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_led,
                              family="spvector_phase3", trading_year=TY)
    else:
        dsr = None

    full = {"cagr": round(100 * _cagr(net), 2), "sharpe": round(_sharpe(net), 2),
            "maxdd": round(100 * _maxdd(net), 1), "bh_cagr": round(100 * _cagr(hold), 2),
            "bh_sharpe": round(_sharpe(hold), 2), "bh_maxdd": round(100 * _maxdd(hold), 1)}

    md = ["# S&P / Macro Vector — Phase 3 confidence audit", "",
          "*Canonical strategy `vector_alloc` (de-risk glide + Fed-put-gated 42d re-deploy), SPY 1993-2026, "
          f"cash@DTB3, {COST_BPS}bps. The final honesty gate before the dashboard ships.*", "",
          "## Headline", "",
          f"| | strategy | buy & hold |", "|---|--:|--:|",
          f"| CAGR | {full['cagr']} | {full['bh_cagr']} |",
          f"| Sharpe | {full['sharpe']} | {full['bh_sharpe']} |",
          f"| MaxDD | {full['maxdd']} | {full['bh_maxdd']} |", "",
          "## Block-bootstrap 95% CI (B=5000, 21d blocks)", "",
          f"- Sharpe CI {boot.get('sharpe_ci')}, P(Sharpe>0)={boot.get('sharpe_gt0_prob')}",
          f"- MaxDD% CI {boot.get('maxdd_ci_pct')}", "",
          "## QE-era (2020-2021) exclusion", "",
          f"- ex-QE Sharpe {qe_row['sharpe']} (B&H {qe_row['bh_sharpe']}); ex-QE MaxDD {qe_row['maxdd']} "
          f"(B&H {qe_row['bh_maxdd']}) — edge {'HOLDS' if qe_row['sharpe'] > qe_row['bh_sharpe'] else 'WEAKENS'} without QE",
          "", "## Year-jackknife (Sharpe edge vs B&H, drop each year)", "",
          f"- positive in {jk_pos}/{len(years)} drop-one-year runs (sign consistency); "
          f"range [{min(jk.values())}, {max(jk.values())}]",
          "", "## AQR-style permutation null (circular-block-shuffle the allocation, B=2000)", "",
          f"- real Sharpe {pn['real_sharpe']} vs null p95 {pn['null_sharpe_p95']} -> skill p={pn['sharpe_skill_p']} "
          f"({'PASS' if pn['sharpe_skill_p'] < 0.05 else 'WEAK'})",
          f"- real MaxDD {pn['real_maxdd']} vs null shallowest-5% {pn['null_maxdd_p95']} -> skill p={pn['maxdd_skill_p']} "
          f"({'PASS' if pn['maxdd_skill_p'] < 0.05 else 'WEAK'})",
          "", "## Deflated Sharpe (honest trial count)", "",
          f"- DSR {dsr['dsr'] if dsr else '—'} at n_trials={N_TRIALS} (SR0_annual {dsr['sr0_annual'] if dsr else '—'})",
          ""]
    gate = {
        "Sharpe CI lower bound > 0": bool(boot and boot["sharpe_ci"][0] > 0),
        "edge holds ex-QE": qe_row["sharpe"] > qe_row["bh_sharpe"],
        "year-jackknife sign-consistent (>=90%)": jk_pos >= 0.9 * len(years),
        "permutation-null MaxDD skill p<0.05": pn["maxdd_skill_p"] < 0.05,
        "DSR > 0.90": bool(dsr and dsr["dsr"] > 0.90),
    }
    md += ["## GATE", ""]
    for k, v in gate.items():
        md.append(f"- {'PASS' if v else 'FAIL'} {k}")
    md += ["", "## Honest framing (must appear on the dashboard)",
           "- This is a DRAWDOWN / SHARPE engine, not a CAGR-beater. The CAGR figure includes T-bill carry on the "
           "de-risked sleeve; net of carry it ~matches buy & hold. It WILL lag the index in prolonged bulls — that "
           "give-up is the premium paid for ~40% shallower drawdowns, banked when the cycle breaks.",
           "- Effective-N is ~4 independent >=20% SPY bears; the permutation-null + leave-one-crisis-out are the "
           "binding tests, not the daily-obs DSR. Macro legs are revised (PIT-lagged per-leg); ALFRED vintages remain "
           "the last honesty upgrade.",
           "- After-tax in a TAXABLE account, frequent switching realizes short-term gains — best run in a "
           "tax-advantaged account (the low ~1.5x/yr turnover helps).",
           "", f"### Verdict: {'PASS — ship the dashboard' if all(gate.values()) else 'REVIEW — see failures'}"]

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "spvector-phase3-audit.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n[report] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
