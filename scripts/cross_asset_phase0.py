"""Cross-Asset TSMOM — Phase-0 honesty gate.

AQR reports a GROSS-of-cost diversified managed-futures Sharpe ~1.8, and TSMOM
efficacy is academically contested (Huang et al. 2020). So before the Cross-Asset
page ships a single number, this subjects our leverage-free TSMOM (engine.
cross_asset_trend.tsmom_alloc) to the same kernel the SP-Vector used:

  - per-asset after-cost (8bps) Sharpe vs buy&hold
  - a DIVERSIFIED equal-weight portfolio (the headline) with:
      • block-bootstrap 95% CI on Sharpe/MaxDD
      • AQR-style circular-block permutation NULL (shuffle each leg's timing) -> skill p
      • Deflated Sharpe at a conservative honest trial count
  - vs an equal-weight long-only buy&hold of the same legs (does trend ADD?)

Writes reports/cross-asset-phase0.md. Run: python -m scripts.cross_asset_phase0
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import cross_asset_trend as cat
from engine.validation import backtest_core, block_bootstrap_ci, deflated_sharpe, ret_moments
from lib import config

TY = 252
COST_BPS = float((config.load().get("cross_asset", {}).get("calibration", {}) or {}).get("cost_bps", 8))
N_TRIALS = 24   # conservative honest trial count (horizon sets × skip × blend variants)


def _sharpe(r):
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(TY)) if len(r) and r.std() else float("nan")


def _maxdd(r):
    eq = (1 + r.dropna()).cumprod()
    return float((eq / eq.cummax() - 1).min()) if len(eq) else float("nan")


def _cagr(r):
    r = r.dropna()
    yrs = len(r) / TY
    return float((1 + r).cumprod().iloc[-1] ** (1 / yrs) - 1) if yrs else float("nan")


def _portfolio_net(uni: dict, cfg: dict, start: str) -> tuple[pd.Series, dict, pd.Series]:
    """Equal-weight TSMOM portfolio net return + per-asset after-cost Sharpe + the
    equal-weight long-only buy&hold benchmark, all on a common date index >= start."""
    nets, holds, per = {}, {}, {}
    for name, price in uni.items():
        p = price[price.index >= start]
        if len(p) < 400:
            continue
        alloc = cat.tsmom_alloc(p, cfg)
        bt = backtest_core(p, alloc, cost_bps=COST_BPS)     # long/short overlay, no cash leg
        nets[name] = bt["net"]
        holds[name] = bt["hold"]
        per[name] = round(_sharpe(bt["net"]), 2)
    port = pd.DataFrame(nets).mean(axis=1).dropna()          # equal-weight across legs
    bh = pd.DataFrame(holds).mean(axis=1).dropna()           # equal-weight long-only
    return port, per, bh


def _perm_null(uni: dict, cfg: dict, start: str, B: int = 1500, block: int = 42, seed: int = 11) -> dict:
    """Circular-block-shuffle each leg's alloc (destroy timing, keep marginal), rebuild
    the equal-weight portfolio B times → the real Sharpe's rank vs the null = skill p."""
    legs = []
    for name, price in uni.items():
        p = price[price.index >= start]
        if len(p) < 400:
            continue
        alloc = cat.tsmom_alloc(p, cfg).reindex(p.index).fillna(0.0).to_numpy()
        legs.append((p, alloc))
    real = pd.DataFrame({i: backtest_core(p, pd.Series(a, index=p.index), cost_bps=COST_BPS)["net"]
                         for i, (p, a) in enumerate(legs)}).mean(axis=1).dropna()
    real_sh = _sharpe(real)
    rng = np.random.default_rng(seed)
    grid = np.arange(block)
    sh = np.empty(B)
    for k in range(B):
        cols = {}
        for i, (p, a) in enumerate(legs):
            n = len(a)
            nb = int(np.ceil(n / block))
            st = rng.integers(0, n, nb)
            idx = (st[:, None] + grid[None, :]).ravel()[:n] % n
            cols[i] = backtest_core(p, pd.Series(a[idx], index=p.index), cost_bps=COST_BPS)["net"]
        sh[k] = _sharpe(pd.DataFrame(cols).mean(axis=1).dropna())
    return {"real_sharpe": round(real_sh, 2),
            "null_sharpe_p95": round(float(np.percentile(sh, 95)), 2),
            "sharpe_skill_p": round(float(np.mean(sh >= real_sh)), 4), "B": B}


def main() -> int:
    cfg = config.load().get("cross_asset", {}) or {}
    start = str((cfg.get("calibration", {}) or {}).get("start_date", "2007-01-01"))
    uni = cat._load_universe(cfg)
    print(f"[cross-asset phase0] {len(uni)} legs from {start}, cost {COST_BPS}bps")

    port, per, bh = _portfolio_net(uni, cfg, start)
    boot = block_bootstrap_ci(port, block=21, B=5000, ann=TY)
    pn = _perm_null(uni, cfg, start)
    mom = ret_moments(port)
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], N_TRIALS, trading_year=TY) if mom else None

    head = {"sharpe": round(_sharpe(port), 2), "cagr": round(100 * _cagr(port), 1),
            "maxdd": round(100 * _maxdd(port), 1), "bh_sharpe": round(_sharpe(bh), 2),
            "bh_cagr": round(100 * _cagr(bh), 1), "bh_maxdd": round(100 * _maxdd(bh), 1)}
    survives = (boot.get("sharpe_ci", [0])[0] > 0 and pn["sharpe_skill_p"] < 0.05
                and dsr and dsr["dsr"] >= 0.90)

    md = ["# Cross-Asset TSMOM — Phase-0 honesty gate", "",
          f"*Leverage-free time-series momentum (avg sign of trailing 3/6/12m return, skip 1w) over "
          f"{len(uni)} keyless cross-asset legs, equal-weight, {start}→, {COST_BPS}bps one-way. "
          f"AQR's gross ~1.8 Sharpe is contested — this is the AFTER-COST number.*", "",
          "## Headline — diversified equal-weight TSMOM vs equal-weight buy&hold", "",
          f"| | TSMOM | Buy&Hold |", "|---|---|---|",
          f"| Sharpe (net) | **{head['sharpe']}** | {head['bh_sharpe']} |",
          f"| CAGR % | {head['cagr']} | {head['bh_cagr']} |",
          f"| MaxDD % | {head['maxdd']} | {head['bh_maxdd']} |", "",
          f"- **Block-bootstrap Sharpe 95% CI:** {boot.get('sharpe_ci')} (P(Sharpe>0)={boot.get('sharpe_gt0_prob')})",
          f"- **MaxDD 95% CI:** {boot.get('maxdd_ci_pct')}%",
          f"- **AQR permutation null:** real Sharpe {pn['real_sharpe']} vs null p95 {pn['null_sharpe_p95']} → "
          f"skill p = **{pn['sharpe_skill_p']}** (B={pn['B']})",
          f"- **Deflated Sharpe:** {dsr['dsr'] if dsr else '—'} at n_trials={N_TRIALS} "
          f"(SR0_annual {dsr['sr0_annual'] if dsr else '—'})", "",
          f"### Verdict: {'SURVIVES — after-cost edge holds under DSR + permutation null' if survives else 'DOES NOT CLEAR the gate — present as a CONTESTED-factor / regime read, not a strategy'}", "",
          "## Per-asset after-cost Sharpe (TSMOM)", "",
          "| asset | TSMOM Sharpe |", "|---|---|"]
    for k, v in sorted(per.items(), key=lambda kv: kv[1], reverse=True):
        md.append(f"| {k} | {v} |")
    md += ["", "## Honesty notes", "",
           "- Net of an 8bps one-way cost on |Δposition|; leverage-free (alloc∈[-1,1]); no vol-targeting leverage.",
           "- The bond leg is a duration-return proxy (−7·Δyield); the dollar leg trends the DXY level.",
           "- DSR n_trials=24 is a conservative upper bound on the horizon/skip/blend variants tried.",
           "- This validates TREND only. Carry & intermarket ratios are current-state context, not backtested.",
           "- Permutation null shuffles each leg's timing independently (circular blocks of 42d), preserving each marginal.",
           "", "*Run: `python -m scripts.cross_asset_phase0`*"]
    out = config.ROOT / "reports" / "cross-asset-phase0.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md))
    print(f"[cross-asset phase0] Sharpe {head['sharpe']} (B&H {head['bh_sharpe']}) | "
          f"skill p {pn['sharpe_skill_p']} | DSR {dsr['dsr'] if dsr else '—'} | "
          f"{'SURVIVES' if survives else 'CONTESTED'} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
