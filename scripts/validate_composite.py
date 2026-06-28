"""Honest net-of-cost forward-IC validation of the decorrelated COMPOSITE (N3 gate).

The standout board surfaces ``engine.composite_score`` (momentum + value + quality +
profitability + revisions, sector-neutral, equal-weight) as CONTEXT beside the
conviction verdict. This script is the honesty gate that decides whether it has earned
the right to DRIVE selection / feed sizing, or must stay context-only.

The decisive question is NOT "do fundamentals predict?" — the committed 14y leak-free
factor scorecard (``reports/factor-ic-scorecard.md``, ~1154 names) already answered that:
the fundamental composite IC ≈ 0 (``composite`` -0.007, ``composite_orth`` +0.002, t≈0.1,
fails FDR); only payout marginally survives. The OPEN question is whether N1's composite
— which folds in the one robustly-positive leg, MOMENTUM — beats momentum ALONE, net of
cost. By the Fundamental Law, equal-weighting a real-edge leg with ~0-IC legs DILUTES
IC-IR unless the added legs carry independent edge; this measures whether they do.

Method (leak-free, point-in-time):
  * Deep close panel from ``data/stocks/*.parquet`` (large-caps, history to the 1960s-80s).
  * Fundamentals from the EDGAR PIT panel (``data/edgar/fundamentals_panel.parquet``),
    each rebalance reading only filings with ``asof_date <= d`` (no look-ahead).
  * Per quarterly rebalance: momentum (12-1), value (book/price), quality (gross
    profitability), profitability (CFO/assets) → ``composite_score.build`` (the SAME
    production sector-neutral z + equal-weight) → forward 63d rank-IC vs each signal.
  * Aggregate: IC-IR + Newey-West HAC-t + BH-FDR (the repo factor-scorecard standard),
    the INCREMENTAL IC of composite over momentum (paired HAC-t on the per-date IC diff),
    a net-of-cost top-minus-bottom-quintile spread (Sharpe + HAC-t + ledgered DSR), and
    effective breadth (median names/rebalance, n rebalances).

Caveats (in the report): breadth is limited to the ~114 locally-cached large-caps (the
wide deep panel ``sue_deep_closes.parquet`` is an offline CI artifact) — a CONSERVATIVE
read (mega-caps are the hardest to rank); yahoo prices are survivorship-biased (delisted
names absent → an OPTIMISTIC bound). The committed 14y scorecard is the wider companion.

Run: PYTHONPATH=. python -m scripts.validate_composite [--horizon 63] [--start 2011]
"""
from __future__ import annotations

import argparse
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
    benjamini_hochberg, ic_summary, newey_west_tstat, rank_ic, ret_moments,
    deflated_sharpe,
)
from lib import config  # noqa: E402

COST_BPS = 20.0   # one-way trading cost per name (bps); round-trip applied to turnover


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
    """Current GICS sector per ticker (from the live factor table) — sector rarely
    changes, so using the latest label to neutralize over history is the standard
    approximation (the committed scorecard does the same)."""
    from engine.equity_factors import _closes, compute_factors
    try:
        bc = _closes("broad")
        tab = pd.DataFrame(compute_factors(asof=bc.index[-1], universe="broad")["table"])
        sec = tab.set_index("ticker")["sector"]
    except Exception:  # noqa: BLE001
        sec = pd.Series(dtype=object)
    return sec.reindex(tickers).fillna("—")


def _funds_asof(fp: pd.DataFrame, d: pd.Timestamp) -> pd.DataFrame | None:
    """The most recent EDGAR filing KNOWN by date d (asof_date <= d), one row/ticker."""
    sub = fp[fp["asof_date"] <= d]
    if sub.empty:
        return None
    return sub.sort_values("asof_date").groupby("ticker").tail(1).set_index("ticker")


def _legs_for(panel: pd.DataFrame, fp: pd.DataFrame, d: pd.Timestamp) -> pd.DataFrame | None:
    """Raw leg values knowable at d: momentum (12-1), value (book/price), quality
    (gross profitability), profitability (CFO/assets). All point-in-time."""
    idx = panel.index
    i = idx.get_loc(d)
    if i < 252:
        return None
    px_now = panel.iloc[i]
    mom = panel.iloc[i - 21] / panel.iloc[i - 252] - 1.0      # 12-1 momentum (skip last month)
    f = _funds_asof(fp, d)
    if f is None:
        return None
    legs = pd.DataFrame(index=panel.columns)
    legs["momentum"] = mom
    shares = pd.to_numeric(f.get("shares"), errors="coerce")
    mktcap = (px_now * shares).reindex(legs.index)
    equity = pd.to_numeric(f.get("equity"), errors="coerce").reindex(legs.index)
    assets = pd.to_numeric(f.get("assets"), errors="coerce").reindex(legs.index)
    gp = pd.to_numeric(f.get("gross_profit"), errors="coerce").reindex(legs.index)
    cfo = pd.to_numeric(f.get("cfo"), errors="coerce").reindex(legs.index)
    ni = pd.to_numeric(f.get("ni"), errors="coerce").reindex(legs.index)
    revenue = pd.to_numeric(f.get("revenue"), errors="coerce").reindex(legs.index)
    mc = mktcap.where(mktcap > 0)
    legs["value"] = (equity / mc)                              # book-to-price (higher = cheaper)
    qual = gp / assets.where(assets > 0)                       # Novy-Marx gross profitability
    qual = qual.fillna(ni / equity.where(equity > 0))          # fallback ROE
    legs["quality"] = qual
    prof = cfo / assets.where(assets > 0)                      # cash profitability
    prof = prof.fillna(ni / revenue.where(revenue > 0))        # fallback net margin
    legs["profitability"] = prof
    return legs


def quarter_grid(panel: pd.DataFrame, start_year: int, horizon: int) -> list:
    idx = panel.index
    out = []
    for q in pd.date_range(f"{start_year}-03-31", idx.max(), freq="QE"):
        d = idx[idx <= q]
        if len(d) and idx.get_loc(d[-1]) + horizon < len(idx):
            out.append(d[-1])
    return out


def _quintile_spread(sig: pd.Series, fwd: pd.Series, q: float = 0.2):
    """Top-minus-bottom quintile equal-weight forward return + the long set (for turnover)."""
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 20:
        return None, None
    n = max(int(len(j) * q), 1)
    s = j.sort_values("s")
    longs, shorts = s.tail(n), s.head(n)
    return float(longs["f"].mean() - shorts["f"].mean()), set(longs.index)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--start", type=int, default=2011)
    args = ap.parse_args()

    panel = _deep_panel()
    if panel.shape[1] < 30:
        print(f"deep panel too thin ({panel.shape[1]} names) — need data/stocks/*.parquet")
        return 1
    sectors = _sector_map(panel.columns)
    fp = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    fp["asof_date"] = pd.to_datetime(fp["asof_date"])
    fwd = panel.pct_change(args.horizon, fill_method=None).shift(-args.horizon)

    grid = quarter_grid(panel, args.start, args.horizon)
    if len(grid) < 6:
        print(f"grid too short ({len(grid)})")
        return 1

    SIGNALS = ["momentum", "fundamentals", "composite"]
    per_ic = {s: [] for s in SIGNALS}
    ic_diff = []                       # per-date IC_composite - IC_momentum (incremental)
    spreads = {s: [] for s in SIGNALS}
    turnover = {s: [] for s in SIGNALS}
    prev_long = {s: None for s in SIGNALS}
    n_names = []

    for d in grid:
        legs = _legs_for(panel, fp, d)
        if legs is None:
            continue
        fr = fwd.loc[d] if d in fwd.index else None
        if fr is None:
            continue
        # production sector-neutral z + equal-weight composite (the SAME engine code)
        full = composite_score.build(legs, sectors,
                                     use_legs=("momentum", "value", "quality", "profitability"))
        if full.empty or "momentum_z" not in full.columns:
            continue
        fund = composite_score.build(legs[["value", "quality", "profitability"]], sectors,
                                     use_legs=("value", "quality", "profitability"))
        sig = {"momentum": full["momentum_z"],
               "fundamentals": fund["composite"] if not fund.empty else pd.Series(dtype=float),
               "composite": full["composite"]}
        n_names.append(int(sig["composite"].notna().sum()))
        ics_d = {}
        for s in SIGNALS:
            ic = rank_ic(sig[s], fr)
            per_ic[s].append(ic)
            ics_d[s] = ic
            sp, longs = _quintile_spread(sig[s], fr)
            if sp is not None:
                cost = 0.0
                if prev_long[s] is not None and longs:
                    churn = 1.0 - len(longs & prev_long[s]) / max(len(longs), 1)
                    cost = churn * 2.0 * COST_BPS / 1e4          # round-trip on the changed fraction
                spreads[s].append(sp - cost)
                turnover[s].append(cost * 1e4 / (2.0 * COST_BPS) if COST_BPS else 0.0)
                prev_long[s] = longs
        if np.isfinite(ics_d.get("composite", np.nan)) and np.isfinite(ics_d.get("momentum", np.nan)):
            ic_diff.append(ics_d["composite"] - ics_d["momentum"])

    # ---- aggregate ----
    ppy = 4
    ic_rows, pvals = {}, {}
    for s in SIGNALS:
        summ = ic_summary(pd.Series(per_ic[s]).dropna(), periods_per_year=ppy)
        ic_rows[s] = summ
        if summ.get("p_hac") is not None:
            pvals[s] = summ["p_hac"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for s, q in fdr.items():
        ic_rows[s]["q_fdr"] = q["q"]
        ic_rows[s]["survives_fdr"] = q["reject"]

    incr = newey_west_tstat(pd.Series(ic_diff).dropna(), lags=2)   # composite − momentum IC

    # net-of-cost quintile spread Sharpe + ledgered DSR per signal
    spread_rows = {}
    led = _ledger()
    for s in SIGNALS:
        r = pd.Series(spreads[s]).dropna()
        nw = newey_west_tstat(r, lags=2)
        mom = ret_moments(r)
        dsr = None
        if mom is not None:
            sr, sk, ku, T = mom
            dsr = deflated_sharpe(sr, sk, ku, T, ledger=led, family="composite_validation")
        spread_rows[s] = {
            "mean_per_reb": round(float(r.mean()), 4) if len(r) else None,
            "ann_pct": round(float(r.mean()) * ppy * 100, 2) if len(r) else None,
            "sharpe_per_reb": round(mom[0], 3) if mom else None,
            "sharpe_ann": round(mom[0] * np.sqrt(ppy), 3) if mom else None,
            "t_hac": nw["t"], "p_hac": nw["p"], "n": int(len(r)),
            "avg_turnover": round(float(np.mean(turnover[s])), 3) if turnover[s] else None,
            "dsr": (dsr or {}).get("dsr"),
        }

    eff_breadth = int(np.median(n_names)) if n_names else 0

    # ---- GO / NO-GO ----
    cz = ic_rows.get("composite", {})
    mz = ic_rows.get("momentum", {})
    composite_t = cz.get("t_hac")
    mom_t = mz.get("t_hac")
    incr_t = incr.get("t")
    composite_beats_mom = (incr.get("mean") or 0) > 0 and (incr_t or 0) >= 1.5
    composite_clears = (composite_t or 0) >= 2.0 and cz.get("survives_fdr")
    net_positive = (spread_rows.get("composite", {}).get("t_hac") or 0) >= 2.0
    go = bool(composite_clears and composite_beats_mom and net_positive)
    verdict = "GO" if go else "NO-GO"
    reason = []
    if not composite_beats_mom:
        reason.append(f"composite does NOT reliably beat momentum-alone (incremental IC "
                      f"mean {incr.get('mean')}, HAC-t {incr_t})")
    if not composite_clears:
        reason.append(f"composite IC-IR not significant net of FDR (HAC-t {composite_t}, "
                      f"q_fdr {cz.get('q_fdr')})")
    if not net_positive:
        reason.append("net-of-cost long-short spread not significant")

    report = {
        "verdict": verdict,
        "decision": ("Composite may DRIVE selection / feed sizing." if go else
                     "Composite stays CONTEXT-ONLY — never drives selection or sizing."),
        "reasons": reason,
        "horizon_d": args.horizon, "rebalances": len(grid),
        "span": f"{grid[0].date()}..{grid[-1].date()}",
        "effective_breadth": eff_breadth, "effective_n_rebalances": cz.get("n"),
        "ic": ic_rows,
        "incremental_composite_minus_momentum": incr,
        "net_of_cost_spread": spread_rows,
        "leak_free": True, "survivorship_biased": True,
        "price_span": f"{panel.index.min().date()}..{panel.index.max().date()}",
        "cost_bps_one_way": COST_BPS,
        "caveat": ("Breadth limited to the ~%d locally-cached large-caps (the wide deep panel "
                   "is an offline CI artifact) — a CONSERVATIVE read (mega-caps are hardest to "
                   "rank). Yahoo prices are survivorship-biased (delisted absent → optimistic). "
                   "The committed 14y factor scorecard (~1154 names) is the wider companion: it "
                   "already shows the fundamental composite IC ≈ 0." % panel.shape[1]),
    }
    outdir = config.data_dir() / "edgar"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "composite_validation.json").write_text(json.dumps(report, indent=2, default=str))
    _write_md(report)

    print(f"\n=== Composite validation (leak-free, deep large-cap) — {report['span']}, "
          f"{report['effective_n_rebalances']} quarterly rebalances, fwd {args.horizon}d, "
          f"~{eff_breadth} names ===")
    print(f"{'signal':14s} {'meanIC':>7} {'IC-IR':>6} {'ICIRann':>8} {'t_HAC':>6} {'qFDR':>6} "
          f"{'netSharpe':>9} {'spr_t':>6}")
    for s in SIGNALS:
        r = ic_rows[s]
        sp = spread_rows[s]
        print(f"{s:14s} {r.get('mean_ic'):>7} {r.get('ic_ir'):>6} {r.get('ic_ir_ann'):>8} "
              f"{str(r.get('t_hac')):>6} {str(r.get('q_fdr','-')):>6} "
              f"{str(sp.get('sharpe_ann')):>9} {str(sp.get('t_hac')):>6}")
    print(f"\nIncremental (composite − momentum) IC: mean {incr.get('mean')}, HAC-t {incr_t}")
    print(f"\n>>> {verdict}: {report['decision']}")
    for r in reason:
        print(f"    - {r}")
    return 0


def _ledger():
    """An ephemeral trial ledger for the honest DSR N (3 signal variants tried) — kept
    out of the production ledger AND the repo tree (system temp) so this validation never
    inflates a real family's count nor gets swept into the daily `git add data/`."""
    import tempfile
    from engine.trial_ledger import TrialLedger
    path = Path(tempfile.gettempdir()) / "_composite_validation_ledger.jsonl"
    if path.exists():
        path.unlink()
    led = TrialLedger(path=path, family="composite_validation")
    led.log_grid([{"signal": s} for s in ("momentum", "fundamentals", "composite")],
                 family="composite_validation")
    return led


def _write_md(rep: dict) -> None:
    L = ["# Composite validation — does the decorrelated composite earn the right to drive selection?",
         "",
         f"**Verdict: {rep['verdict']}.** {rep['decision']}", ""]
    if rep.get("reasons"):
        for r in rep["reasons"]:
            L.append(f"- {r}")
        L.append("")
    L += [f"Span {rep['span']} · {rep['effective_n_rebalances']} quarterly rebalances · "
          f"forward {rep['horizon_d']}d · ~{rep['effective_breadth']} names · leak-free, "
          f"point-in-time · net of {rep['cost_bps_one_way']}bps/side.", "",
          "| signal | mean IC | IC-IR | IC-IR ann | t_HAC | q_FDR | net Sharpe (ann) | spread t_HAC | DSR |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for s in ("momentum", "fundamentals", "composite"):
        r = rep["ic"][s]
        sp = rep["net_of_cost_spread"][s]
        L.append(f"| {s} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('ic_ir_ann')} | "
                 f"{r.get('t_hac')} | {r.get('q_fdr','—')} | {sp.get('sharpe_ann')} | "
                 f"{sp.get('t_hac')} | {sp.get('dsr')} |")
    inc = rep["incremental_composite_minus_momentum"]
    L += ["",
          f"**Incremental IC (composite − momentum):** mean {inc.get('mean')}, "
          f"HAC-t {inc.get('t')}, n {inc.get('n')}. "
          "By the Fundamental Law, a composite only beats its best leg when the added legs "
          "carry INDEPENDENT positive edge; a non-positive incremental t means the fundamental "
          "legs dilute rather than add.", "",
          f"> {rep['caveat']}"]
    Path(config.load()["storage"]["reports_dir"], "composite-validation-phase0.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
