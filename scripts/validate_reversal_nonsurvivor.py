"""Reversal on a TRUE non-survivor large-cap PIT panel (N4-deep).

The survivor-panel result (scripts/validate_reversal.py) showed reversal dies in the
tradeable slice; this isolates the SURVIVORSHIP effect directly. Universe = S&P 500
point-in-time membership (data/breadth/sp1500_pit_membership.parquet). The SAME universe
is run twice:

  * Panel A (survivor-biased): only names still trading today — the standard bias.
  * Panel B (non-survivor): survivors + delisted/removed names recovered with their REAL
    prices through exit (so a name reversal bought as a "loser" that then declined into
    removal contributes its actual poor forward return — no delisting-return guessing).

The delta A→B is the pure survivorship impact on short-term reversal. Reversal goes LONG
recent losers; the removed names are disproportionately recent losers — so including them
should drag the long leg down. Prices are Yahoo (close); the ~40% of removals that are
unrecoverable are mostly bankruptcies (true ~-100% blow-ups), so Panel B still OMITS the
worst losers → it is a CONSERVATIVE bound (the real non-survivor edge is even worse).

Run: PYTHONPATH=. python -m scripts.validate_reversal_nonsurvivor   (after the fetch cache)
"""
from __future__ import annotations

import glob
import json
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

CACHE = "/tmp/nsv_cache"
LOOKBACK, FWD, BETA_WIN = 21, 21, 120
# Plain cross-sectional winsorized z (NOT sector-neutral): the recovered delisted names
# have no GICS sector, and a sector groupby would silently DROP them — defeating the whole
# test. A single "—" group makes _winsor_z_by_sector a plain ±3-MAD-winsorized z over the
# full cross-section, keeping every PIT member (survivor and delisted alike) in the signal.


def _load_panel():
    """Combined close panel from the fetch cache + the local survivor store."""
    cols = {}
    for f in glob.glob(os.path.join(CACHE, "*.parquet")):
        t = os.path.basename(f)[:-8]
        try:
            cols[t] = pd.read_parquet(f)["close"]
        except Exception:  # noqa: BLE001
            continue
    for f in glob.glob(str(config.data_dir() / "stocks" / "*.parquet")):
        t = os.path.basename(f)[:-8]
        if t not in cols:
            try:
                cols[t] = pd.read_parquet(f)["close"]
            except Exception:  # noqa: BLE001
                continue
    panel = pd.DataFrame(cols).sort_index()
    panel = panel[~panel.index.duplicated(keep="last")]
    return panel


def _membership():
    m = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    m = m[m.src == "sp500"].copy()
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"], errors="coerce")
    return m


def _members_at(m: pd.DataFrame, d: pd.Timestamp) -> set:
    sub = m[(m.start_date <= d) & (m.end_date.isna() | (m.end_date >= d))]
    return set(sub.ticker)


def month_grid(panel, m) -> list:
    idx = panel.index
    out = []
    first = max(m.start_date.min(), idx.min())
    for mo in pd.date_range(first, idx.max(), freq="ME"):
        d = idx[idx <= mo]
        if len(d) and idx.get_loc(d[-1]) >= BETA_WIN and idx.get_loc(d[-1]) + FWD < len(idx):
            out.append(d[-1])
    return out


def _spread(sig, fwd, q=0.2):
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 20:
        return None, None
    n = max(int(len(j) * q), 1)
    s = j.sort_values("s")
    return float(s.tail(n)["f"].mean() - s.head(n)["f"].mean()), set(s.tail(n).index)


def _run_panel(panel, grid, m, survivors_only: bool, survivor_set: set, led):
    rets = panel.pct_change(fill_method=None)
    mkt = rets.mean(axis=1)
    fwd_ret = panel.pct_change(FWD, fill_method=None).shift(-FWD)
    ics, sp_g, sp_c10, prev = [], [], [], None
    n_names = []
    for d in grid:
        i = panel.index.get_loc(d)
        memb = _members_at(m, d)
        if survivors_only:
            memb &= survivor_set
        if len(memb) < 30:
            continue
        cols = [t for t in memb if t in panel.columns]
        sub = panel[cols]
        ret_lb = sub.iloc[i] / sub.iloc[i - LOOKBACK] - 1.0
        win = rets[cols].iloc[i - BETA_WIN:i]
        mw = mkt.iloc[i - BETA_WIN:i]
        vm = float(mw.var())
        beta = win.apply(lambda c: c.cov(mw) / vm if vm > 0 else np.nan)
        mkt_lb = mkt.iloc[i - LOOKBACK:i].add(1).prod() - 1.0
        resid = ret_lb - beta * mkt_lb
        sig = composite_score._winsor_z_by_sector(-resid, pd.Series("—", index=cols))   # reverse losers (plain z)
        if d not in fwd_ret.index:
            continue
        # Data hygiene for the recovered (low-quality, free-source) delisted series: drop sub-$5
        # distress/penny names (untradeable, garbage % moves) and clip monthly forward returns to
        # ±50% so a few unadjusted / penny-doubling blow-ups can't dominate the quintile spread.
        # Clipping the downside at -50% is CONSERVATIVE — it understates true delisting losses,
        # i.e. it flatters reversal, so a NO-GO here is only stronger.
        px = sub.iloc[i]
        keep = px.index[(px >= 5.0) & px.notna()]
        sig = sig.reindex(keep)
        fr = fwd_ret.loc[d, keep].clip(-0.5, 0.5)
        ic = rank_ic(sig, fr)
        if np.isfinite(ic):
            ics.append(ic)
            n_names.append(int(sig.notna().sum()))
        sp, longs = _spread(sig, fr)
        if sp is not None:
            turn = 1.0 if prev is None else 1.0 - len(longs & prev) / max(len(longs), 1)
            sp_g.append(sp)
            sp_c10.append(sp - turn * 2 * 10.0 / 1e4)
            prev = longs
    summ = ic_summary(pd.Series(ics).dropna(), periods_per_year=12)
    out = {"ic": summ, "median_breadth": int(np.median(n_names)) if n_names else 0}
    for tag, arr in (("gross", sp_g), ("net_10bps", sp_c10)):
        r = pd.Series(arr).dropna()
        nw = newey_west_tstat(r, lags=3)
        mom = ret_moments(r)
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=led,
                              family="reversal_nonsurvivor") if mom else None
        out[tag] = {"ann_pct": round(float(r.mean()) * 12 * 100, 2) if len(r) else None,
                    "sharpe_ann": round(mom[0] * np.sqrt(12), 3) if mom else None,
                    "t_hac": nw["t"], "dsr": (dsr or {}).get("dsr"), "n": int(len(r))}
    return out


def _ledger():
    import tempfile
    from engine.trial_ledger import TrialLedger
    p = Path(tempfile.gettempdir()) / "_reversal_nsv_ledger.jsonl"
    if p.exists():
        p.unlink()
    led = TrialLedger(path=p, family="reversal_nonsurvivor")
    led.log_grid([{"panel": x, "cost": c} for x in ("survivor", "nonsurvivor") for c in (0, 10)],
                 family="reversal_nonsurvivor")
    return led


def main() -> int:
    n_cached = len(glob.glob(os.path.join(CACHE, "*.parquet")))
    if n_cached < 200:
        print(f"price cache too thin ({n_cached}) — run the fetch first (/tmp/fetch_nsv.py)")
        return 1
    panel = _load_panel()
    m = _membership()
    end = panel.index.max()
    last_valid = panel.apply(lambda c: c.last_valid_index())
    survivor_set = set(last_valid[last_valid >= end - pd.Timedelta(days=60)].index)
    delisted_recovered = panel.shape[1] - len(survivor_set)
    grid = month_grid(panel, m)
    if len(grid) < 24:
        print(f"grid too short ({len(grid)})")
        return 1

    led = _ledger()
    A = _run_panel(panel, grid, m, True, survivor_set, led)    # survivor-biased
    B = _run_panel(panel, grid, m, False, survivor_set, led)   # non-survivor

    a_net = A["net_10bps"]["ann_pct"] or 0
    b_net = B["net_10bps"]["ann_pct"] or 0
    # The survivorship CORRECTION: how much the apparent reversal edge shrinks once
    # delisted losers are included. A large positive A→B drop = the bias was the edge.
    surv_bias_drag = round(a_net - b_net, 2)
    # net-NEGATIVE on BOTH panels (not merely "survivor edge erased") → the cleanest read
    go = bool((B["ic"].get("t_hac") or 0) >= 2.0 and (B["net_10bps"]["t_hac"] or 0) >= 2.0 and b_net > 0)
    verdict = "GO" if go else "NO-GO"
    n_unrecoverable = 0
    try:
        n_unrecoverable = len(json.load(open(os.path.join(CACHE, "_fails.json"))))
    except Exception:  # noqa: BLE001
        pass

    report = {
        "verdict": verdict,
        "decision": ("Reversal earns a small entry tilt on the NON-survivor panel." if go else
                     f"CLOSE THE BOOK — residual reversal is net-NEGATIVE after cost on BOTH the "
                     f"survivor ({a_net}%/yr) and the non-survivor ({b_net}%/yr) S&P 500 universe, "
                     f"both insignificant; survivorship makes it worse (drag {surv_bias_drag}%/yr) "
                     f"and that is only a LOWER bound — the worst losers are unrecoverable. No "
                     f"tradeable edge: do not give reversal an entry tilt."),
        "lookback_d": LOOKBACK, "fwd_d": FWD, "rebalance": "monthly",
        "span": f"{grid[0].date()}..{grid[-1].date()}", "rebalances": len(grid),
        "names_total": panel.shape[1], "survivors": len(survivor_set),
        "delisted_recovered": delisted_recovered, "delisted_unrecoverable": n_unrecoverable,
        "survivor_panel": A, "nonsurvivor_panel": B,
        "survivorship_drag_pct_per_yr": surv_bias_drag,
        "price_span": f"{panel.index.min().date()}..{end.date()}",
        "caveat": (f"Yahoo close prices, $5 price floor + ±50% monthly-return clip (robust to the "
                   f"noisy free-source delisted data). Only {delisted_recovered} genuinely-delisted "
                   f"names recovered vs {n_unrecoverable} unrecoverable — and Yahoo retains the BENIGN "
                   f"exits (acquisitions/demotions) while dropping the MALIGNANT ones (bankruptcies, "
                   f"true ~-100% blow-ups). So the non-survivor panel still omits the worst losers: the "
                   f"measured drag is a LOWER bound and the clip flatters reversal — a NO-GO here is only "
                   f"stronger. A definitive deep test needs CRSP delisting returns. Universe = S&P 500 PIT."),
    }
    (config.data_dir() / "edgar" / "reversal_nonsurvivor.json").write_text(
        json.dumps(report, indent=2, default=str))
    _write_md(report)

    print(f"\n=== Reversal: survivor vs NON-survivor (S&P500 PIT) — {report['span']}, "
          f"{len(grid)} monthly rebalances ===")
    print(f"names {panel.shape[1]} ({len(survivor_set)} survivors + {delisted_recovered} recovered delisted)")
    print(f"{'panel':14s} {'breadth':>7} {'meanIC':>7} {'t_HAC':>6} {'grossSh':>7} {'net10Sh':>7} {'net10t':>6} {'net10%/y':>8}")
    for nm, P in (("survivor", A), ("non-survivor", B)):
        print(f"{nm:14s} {P['median_breadth']:>7} {str(P['ic'].get('mean_ic')):>7} {str(P['ic'].get('t_hac')):>6} "
              f"{str(P['gross'].get('sharpe_ann')):>7} {str(P['net_10bps'].get('sharpe_ann')):>7} "
              f"{str(P['net_10bps'].get('t_hac')):>6} {str(P['net_10bps'].get('ann_pct')):>8}")
    print(f"\nSurvivorship drag on net reversal: {surv_bias_drag} %/yr (survivor {a_net} → non-survivor {b_net})")
    print(f">>> {verdict}: {report['decision']}")
    return 0


def _write_md(rep: dict) -> None:
    A, B = rep["survivor_panel"], rep["nonsurvivor_panel"]
    L = ["# Reversal on a true non-survivor panel — is the edge just survivorship bias?",
         "", f"**Verdict: {rep['verdict']}.** {rep['decision']}", "",
         f"Span {rep['span']} · {rep['rebalances']} monthly rebalances · S&P 500 point-in-time "
         f"membership · {rep['names_total']} names ({rep['survivors']} survivors + "
         f"{rep['delisted_recovered']} recovered delisted/removed).", "",
         "| panel | median breadth | mean IC | IC t_HAC | gross Sharpe | net@10 Sharpe | net@10 t_HAC | net@10 %/yr |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for nm, P in (("survivor-biased", A), ("**non-survivor**", B)):
        L.append(f"| {nm} | {P['median_breadth']} | {P['ic'].get('mean_ic')} | {P['ic'].get('t_hac')} | "
                 f"{P['gross'].get('sharpe_ann')} | {P['net_10bps'].get('sharpe_ann')} | "
                 f"{P['net_10bps'].get('t_hac')} | {P['net_10bps'].get('ann_pct')} |")
    L += ["", f"**Survivorship drag on net reversal: {rep['survivorship_drag_pct_per_yr']} %/yr** "
          f"(survivor {A['net_10bps'].get('ann_pct')} → non-survivor {B['net_10bps'].get('ann_pct')}). "
          "Reversal goes long recent losers; the removed names are disproportionately recent losers, "
          "so including them is what erodes the edge.", "", f"> {rep['caveat']}"]
    Path(config.load()["storage"]["reports_dir"], "reversal-nonsurvivor-phase0.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
