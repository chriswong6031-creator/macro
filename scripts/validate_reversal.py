"""Reversal salvage — does residual + turnover-conditioned short-term reversal survive
NET OF COST? (N4 — the last open selection-alpha thread.)

Prior (research/MAGICAL_SIGNALS_ROADMAP.md): naive 1-month reversal is a NET-OF-COST
MIRAGE — a strong GROSS t on a survivor panel that goes -2..-8%/yr net on the true
non-survivor universe (delisted blow-ups punish "buy the loser"). The form the
literature says survives is RESIDUAL (idiosyncratic, beta/sector-stripped) reversal,
which is concentrated in HIGH-TURNOVER names — exactly where trading cost is highest.
This tests that form, net of realistic cost, and conditions it on liquidity.

DATA HONESTY: no delisting-recovered (non-survivor) price panel exists locally, so this
runs on the SURVIVORSHIP-BIASED large-cap panel (``data/stocks``). That bias is GENEROUS
to reversal — it omits the dead losers that crush naive "buy the loser" — so a net-of-cost
FAILURE here is CONCLUSIVE: reversal fails a fortiori on the true non-survivor universe.
A net-of-cost PASS here would be necessary-but-not-sufficient (it would need a non-survivor
confirm before earning even a small entry tilt). Strict GO bar.

Method (leak-free, point-in-time): monthly rebalance, signal = reversed trailing-21d
return; three forms — raw, beta-residual (idiosyncratic), and beta-residual within the
TOP liquidity tercile (the only tradeable slice). Forward 21d rank-IC + IC-IR/HAC-t,
net-of-cost top-minus-bottom-quintile spread (Sharpe + HAC-t + ledgered DSR) at 10bps and
20bps/side, effective breadth. GO/NO-GO.

Run: PYTHONPATH=. python -m scripts.validate_reversal [--cost-bps 10]
"""
from __future__ import annotations

import argparse
import json
import glob
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import composite_score  # noqa: E402
from engine.validation import (  # noqa: E402
    deflated_sharpe, ic_summary, newey_west_tstat, rank_ic, ret_moments,
)
from lib import config  # noqa: E402


# --- panel loaders (self-contained; see reports/reversal-salvage-phase0.md) ----------
def _deep_panel() -> pd.DataFrame:
    """Wide [date x ticker] close panel from the locally-cached per-name parquets."""
    cols = {}
    for f in glob.glob(str(config.data_dir() / "stocks" / "*.parquet")):
        t = os.path.basename(f)[:-8]
        try:
            df = pd.read_parquet(f)
            if "close" in df.columns:
                cols[t] = df["close"]
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame(cols).sort_index()


def _sector_map(tickers) -> pd.Series:
    """Current GICS sector per ticker (from the live factor table) — sector rarely changes,
    so using the latest label to neutralize over history is the standard approximation."""
    from engine.equity_factors import _closes, compute_factors
    try:
        bc = _closes("broad")
        tab = pd.DataFrame(compute_factors(asof=bc.index[-1], universe="broad")["table"])
        sec = tab.set_index("ticker")["sector"]
    except Exception:  # noqa: BLE001
        sec = pd.Series(dtype=object)
    return sec.reindex(tickers).fillna("—")

LOOKBACK = 21          # reversal formation window (trailing ~1 month)
FWD = 21               # forward holding window (~1 month)
BETA_WIN = 120         # trailing window for the market-beta residualization


def month_grid(panel: pd.DataFrame) -> list:
    """~Monthly rebalance dates (last trading day of each month) with room for fwd + lookback."""
    idx = panel.index
    out = []
    for m in pd.date_range(idx.min(), idx.max(), freq="ME"):
        d = idx[idx <= m]
        if len(d) and idx.get_loc(d[-1]) >= max(LOOKBACK, BETA_WIN) and idx.get_loc(d[-1]) + FWD < len(idx):
            out.append(d[-1])
    return out


def _quintile_spread(sig: pd.Series, fwd: pd.Series, q: float = 0.2):
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 20:
        return None, None
    n = max(int(len(j) * q), 1)
    s = j.sort_values("s")
    return float(s.tail(n)["f"].mean() - s.head(n)["f"].mean()), set(s.tail(n).index)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost-bps", type=float, default=10.0, help="one-way cost (large-cap generous)")
    args = ap.parse_args()

    panel = _deep_panel()
    if panel.shape[1] < 30:
        print(f"deep panel too thin ({panel.shape[1]} names)")
        return 1
    sectors = _sector_map(panel.columns)
    rets = panel.pct_change(fill_method=None)
    mkt = rets.mean(axis=1)                                     # equal-weight market proxy
    fwd_ret = panel.pct_change(FWD, fill_method=None).shift(-FWD)
    # trailing dollar-volume for the liquidity (turnover) conditioning
    dollar_vol = None
    try:
        vols = {}
        import glob, os
        for f in glob.glob(str(config.data_dir() / "stocks" / "*.parquet")):
            t = os.path.basename(f)[:-8]
            df = pd.read_parquet(f)
            if "volume" in df.columns:
                vols[t] = (df["close"] * df["volume"])
        dollar_vol = pd.DataFrame(vols).reindex(panel.index).rolling(LOOKBACK).mean()
    except Exception as e:  # noqa: BLE001
        print(f"dollar-volume unavailable ({e}) — liquidity tercile skipped")

    grid = month_grid(panel)
    if len(grid) < 12:
        print(f"grid too short ({len(grid)})")
        return 1

    SIGS = ["reversal_raw", "reversal_resid", "reversal_resid_liquid"]
    per_ic = {s: [] for s in SIGS}
    spreads = {s: {"g": [], "c10": [], "c20": []} for s in SIGS}
    prev_long = {s: None for s in SIGS}
    n_names = []

    for d in grid:
        i = panel.index.get_loc(d)
        ret_lb = panel.iloc[i] / panel.iloc[i - LOOKBACK] - 1.0          # trailing 21d return
        # market-beta residual of the formation return (strip the systematic part)
        win = rets.iloc[i - BETA_WIN:i]
        mw = mkt.iloc[i - BETA_WIN:i]
        var_m = float(mw.var())
        beta = win.apply(lambda c: c.cov(mw) / var_m if var_m > 0 else np.nan)
        mkt_lb = mkt.iloc[i - LOOKBACK:i].add(1).prod() - 1.0
        resid_lb = ret_lb - beta * mkt_lb                               # idiosyncratic formation move
        # signals = REVERSED formation return, sector-neutral z (long losers / short winners)
        raw_z = composite_score._winsor_z_by_sector((-ret_lb), sectors)
        res_z = composite_score._winsor_z_by_sector((-resid_lb), sectors)
        fr = fwd_ret.loc[d] if d in fwd_ret.index else None
        if fr is None:
            continue
        liq_mask = None
        if dollar_vol is not None and d in dollar_vol.index:
            dv = dollar_vol.loc[d].dropna()
            if len(dv) >= 30:
                liq_mask = dv >= dv.quantile(2 / 3)                     # top liquidity tercile (tradeable)
        sig = {"reversal_raw": raw_z, "reversal_resid": res_z,
               "reversal_resid_liquid": res_z.where(liq_mask) if liq_mask is not None else pd.Series(dtype=float)}
        n_names.append(int(res_z.notna().sum()))
        for s in SIGS:
            ss = sig[s]
            if ss is None or ss.dropna().empty:
                continue
            per_ic[s].append(rank_ic(ss, fr))
            sp, longs = _quintile_spread(ss, fr)
            if sp is None:
                continue
            turn = 1.0 if prev_long[s] is None else 1.0 - len(longs & prev_long[s]) / max(len(longs), 1)
            spreads[s]["g"].append(sp)
            spreads[s]["c10"].append(sp - turn * 2 * 10.0 / 1e4)
            spreads[s]["c20"].append(sp - turn * 2 * 20.0 / 1e4)
            prev_long[s] = longs

    ppy = 12
    ic_rows, spread_rows = {}, {}
    led = _ledger()
    for s in SIGS:
        ic_rows[s] = ic_summary(pd.Series(per_ic[s]).dropna(), periods_per_year=ppy)
        row = {}
        for tag, key in (("gross", "g"), ("net_10bps", "c10"), ("net_20bps", "c20")):
            r = pd.Series(spreads[s][key]).dropna()
            nw = newey_west_tstat(r, lags=3)
            mom = ret_moments(r)
            dsr = None
            if mom is not None:
                dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=led, family="reversal_validation")
            row[tag] = {"ann_pct": round(float(r.mean()) * ppy * 100, 2) if len(r) else None,
                        "sharpe_ann": round(mom[0] * np.sqrt(ppy), 3) if mom else None,
                        "t_hac": nw["t"], "dsr": (dsr or {}).get("dsr"), "n": int(len(r))}
        spread_rows[s] = row

    eff = int(np.median(n_names)) if n_names else 0
    # ---- strict GO bar: the TRADEABLE residual form must be net-positive & significant ----
    liq = ic_rows.get("reversal_resid_liquid", {})
    liq_net = spread_rows.get("reversal_resid_liquid", {}).get("net_10bps", {})
    go = bool((liq.get("t_hac") or 0) >= 2.0 and (liq_net.get("t_hac") or 0) >= 2.0
              and (liq_net.get("ann_pct") or -1) > 0 and (liq_net.get("dsr") or 0) >= 0.95)
    verdict = "GO" if go else "NO-GO"
    reasons = []
    if (liq_net.get("ann_pct") or -1) <= 0:
        reasons.append(f"tradeable (liquid) residual reversal is net-NEGATIVE after 10bps "
                       f"({liq_net.get('ann_pct')}%/yr) — the mirage: gross edge is eaten by turnover cost")
    if (liq.get("t_hac") or 0) < 2.0:
        reasons.append(f"liquid residual reversal IC not significant (HAC-t {liq.get('t_hac')})")

    report = {
        "verdict": verdict,
        "decision": ("Reversal earns a small ENTRY tilt (pending a non-survivor confirm)." if go else
                     "CLOSE THE BOOK on reversal as selection alpha — it is a net-of-cost mirage."),
        "reasons": reasons,
        "lookback_d": LOOKBACK, "fwd_d": FWD, "rebalance": "monthly",
        "span": f"{grid[0].date()}..{grid[-1].date()}", "rebalances": len(grid),
        "effective_breadth": eff, "ic": ic_rows, "net_of_cost_spread": spread_rows,
        "leak_free": True, "survivorship_biased": True,
        "price_span": f"{panel.index.min().date()}..{panel.index.max().date()}",
        "caveat": ("No non-survivor price panel locally → run on the SURVIVORSHIP-BIASED large-cap "
                   "panel (~%d names), which is GENEROUS to reversal (omits delisted blow-ups). A "
                   "net-of-cost failure here is therefore CONCLUSIVE; a pass would need a non-survivor "
                   "confirm before any tilt. Costs: 10/20 bps per side on realized turnover." % panel.shape[1]),
    }
    (config.data_dir() / "edgar" / "reversal_validation.json").write_text(
        json.dumps(report, indent=2, default=str))
    _write_md(report)

    print(f"\n=== Reversal validation (leak-free, survivor large-cap) — {report['span']}, "
          f"{len(grid)} monthly rebalances, fwd {FWD}d, ~{eff} names ===")
    print(f"{'signal':24s} {'meanIC':>7} {'IC-IR':>6} {'t_HAC':>6} {'grossSh':>7} "
          f"{'net10Sh':>7} {'net10t':>6} {'net10%/y':>8}")
    for s in SIGS:
        r = ic_rows[s]
        sp = spread_rows[s]
        print(f"{s:24s} {str(r.get('mean_ic')):>7} {str(r.get('ic_ir')):>6} {str(r.get('t_hac')):>6} "
              f"{str(sp['gross'].get('sharpe_ann')):>7} {str(sp['net_10bps'].get('sharpe_ann')):>7} "
              f"{str(sp['net_10bps'].get('t_hac')):>6} {str(sp['net_10bps'].get('ann_pct')):>8}")
    print(f"\n>>> {verdict}: {report['decision']}")
    for r in reasons:
        print(f"    - {r}")
    return 0


def _ledger():
    import tempfile
    from engine.trial_ledger import TrialLedger
    path = Path(tempfile.gettempdir()) / "_reversal_validation_ledger.jsonl"
    if path.exists():
        path.unlink()
    led = TrialLedger(path=path, family="reversal_validation")
    # forms tried × cost grid — the honest selection count for the DSR haircut
    led.log_grid([{"form": f, "cost": c} for f in ("raw", "resid", "resid_liquid")
                  for c in (0, 10, 20)], family="reversal_validation")
    return led


def _write_md(rep: dict) -> None:
    L = ["# Reversal salvage — does residual + turnover-conditioned reversal survive net of cost?",
         "", f"**Verdict: {rep['verdict']}.** {rep['decision']}", ""]
    for r in rep.get("reasons", []):
        L.append(f"- {r}")
    L += ["",
          f"Span {rep['span']} · {rep['rebalances']} monthly rebalances · formation "
          f"{rep['lookback_d']}d → forward {rep['fwd_d']}d · ~{rep['effective_breadth']} names · "
          "leak-free, point-in-time.", "",
          "| signal | mean IC | IC-IR | t_HAC | gross Sharpe | net@10 Sharpe | net@10 t_HAC | net@10 %/yr | net@10 DSR |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for s in ("reversal_raw", "reversal_resid", "reversal_resid_liquid"):
        r = rep["ic"][s]
        sp = rep["net_of_cost_spread"][s]
        n10 = sp["net_10bps"]
        L.append(f"| {s} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('t_hac')} | "
                 f"{sp['gross'].get('sharpe_ann')} | {n10.get('sharpe_ann')} | {n10.get('t_hac')} | "
                 f"{n10.get('ann_pct')} | {n10.get('dsr')} |")
    L += ["",
          "`reversal_resid_liquid` = beta-residual reversal in the TOP dollar-volume tercile (the only "
          "tradeable slice) — the form the literature claims survives. The gross→net columns show where "
          "turnover cost lands.", "", f"> {rep['caveat']}"]
    Path(config.load()["storage"]["reports_dir"], "reversal-salvage-phase0.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
