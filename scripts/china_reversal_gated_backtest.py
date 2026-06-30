"""China reversal FALSIFICATION backtest — does a subsector-STATE gate help?

Pits the validated within-sector short-term reversal (deepest-quintile, the only
A-share cross-sectional effect that survived FDR in reports/china-residual-alpha-deep.md
and reports/china-reversal-phase0.md) under three subsector gates:

  (c) FLAT        — no subsector gate (the baseline / published edge)
  (a) WASHED-OUT  — keep names whose Shenwan sector is beaten-down (state <= 35)
  (b) LEADING     — keep names whose sector is stretched/euphoric (state >= 65)  [the owner's original "gate to leading subsectors" idea]

The point: the synthesis says "invert the gate to washed-out"; the critique says even
that may not beat FLAT, and that conditioning reversal on ANY top-down pass cut Sharpe
0.58->0.34. This script settles it on data — gross AND net-of-cost, full-sample AND the
2015+ Connect-era (the owner's actual investable regime), with HAC-t IC + BH-FDR.

Leak-free: the sector state (engine.china_sector_pathway._position) uses only own-history
percentiles up to date d; the reversal signal and the sector gate are both as-of d, the
forward return is d -> d+21. No look-ahead.

Run (needs the deep panel first):
  .venv/bin/python -m scripts.china_residual_alpha_deep --fetch       # one-time
  .venv/bin/python -m scripts.china_reversal_gated_backtest            # cost=10bps/side
  .venv/bin/python -m scripts.china_reversal_gated_backtest --cost 20
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from engine.china_sector_pathway import _position
from engine.validation import benjamini_hochberg, ic_summary, rank_ic
from lib import config

DEEP = "data/china_search/closes_deep.parquet"
MEMBERS = "data/china_search/members.parquet"
JUNK = "A-share"
WASH_MAX, LEAD_MIN = 35.0, 65.0          # state bands (engine.china_sector_pathway._position)
LO, HI = 0.8, 1.01                       # deepest reversal quintile (matches phase0)
MIN_CAND, MIN_SEL = 15, 4


def _ann_sharpe(e: pd.Series) -> float:
    return float(e.mean() / e.std() * np.sqrt(12)) if e.std() > 0 else 0.0


def _maxdd(e: pd.Series) -> float:
    c = (1 + e).cumprod()
    return float((c / c.cummax() - 1).min())


def ew_sector_indices(closes: pd.DataFrame, sector: pd.Series) -> dict:
    """Equal-weight total-return index per Shenwan sector (mean of available member
    daily returns -> cumprod). Robust to ragged member histories."""
    out = {}
    for sec in sorted(set(sector.values) - {JUNK, "—"}):
        cols = [c for c in sector.index[sector == sec] if c in closes.columns]
        if len(cols) < 3:
            continue
        ew = closes[cols].pct_change(fill_method=None).mean(axis=1, skipna=True)
        out[sec] = (1 + ew.fillna(0)).cumprod()
    return out


def sector_state_gates(closes, sector, grid) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leak-free washed-out / leading boolean gate frames [grid x ticker]. The state for
    sector `sec` as-of date `d` is _position(ew_index[sec] truncated at d)['score']."""
    ewidx = ew_sector_indices(closes, sector)
    score = {sec: {} for sec in ewidx}
    for sec, idx in ewidx.items():
        for d in grid:
            sub = idx.loc[:d].dropna()
            score[sec][d] = (_position(sub) or {}).get("score") if len(sub) >= 260 else None
    wash = pd.DataFrame(False, index=grid, columns=closes.columns)
    lead = pd.DataFrame(False, index=grid, columns=closes.columns)
    for d in grid:
        sc = pd.Series({t: score.get(sector.get(t), {}).get(d) for t in closes.columns}, dtype="float64")
        wash.loc[d] = (sc <= WASH_MAX).values
        lead.loc[d] = (sc >= LEAD_MIN).values
    return wash, lead


def run(signal, fwd, sector, grid, gate, cost_bps: float) -> dict:
    """One variant. Within-sector demeaned reversal, deepest [LO,HI] band, EW long-only,
    excess vs universe mean. Tracks gross + net-of-cost + per-rebalance cross-sectional IC."""
    exc_g, exc_n, ns, ics, prev = [], [], [], [], set()
    for d in grid:
        if d not in fwd.index or d not in signal.index:
            continue
        fr = fwd.loc[d].dropna()
        if len(fr) < 30:
            continue
        s = signal.loc[d]
        sn = s - s.groupby(sector).transform("mean")                  # within-sector demean
        g = gate.loc[d] if gate is not None else pd.Series(True, index=s.index)
        cand = sn[g.reindex(s.index).fillna(False) & sn.notna()].reindex(fr.index).dropna()
        if len(cand) < MIN_CAND:
            continue
        sel = cand[(cand >= cand.quantile(LO)) & (cand <= cand.quantile(min(HI, 1.0)))].index
        if len(sel) < MIN_SEL:
            continue
        gross = float(fr.reindex(sel).mean() - fr.mean())
        turn = len(set(sel) - prev) / len(sel)                        # one-way replaced fraction
        cost = turn * 2.0 * cost_bps / 1e4                            # round-trip on the replaced sleeve
        exc_g.append(gross); exc_n.append(gross - cost); ns.append(len(sel)); prev = set(sel)
        ics.append(rank_ic(cand, fr.reindex(cand.index)))             # reversal IC within the gate
    g, n = pd.Series(exc_g), pd.Series(exc_n)
    if len(g) < 12:
        return {"n": len(g), "error": "too few rebalances"}
    ics = pd.Series([x for x in ics if pd.notna(x)])
    icsum = ic_summary(ics.tolist()) if len(ics) >= 12 else {}
    return {
        "n": len(g), "med_sel": int(np.median(ns)),
        "gross_pct": round(g.mean() * 100, 3), "net_pct": round(n.mean() * 100, 3),
        "gross_sharpe": round(_ann_sharpe(g), 2), "net_sharpe": round(_ann_sharpe(n), 2),
        "maxdd_pct": round(_maxdd(n) * 100, 1), "hit": round(float((n > 0).mean()), 3),
        "ic": round(icsum.get("mean_ic", float("nan")), 4),
        "t_hac": round(icsum.get("t_hac", float("nan")), 2),
        "p_hac": round(icsum.get("p_hac", float("nan")), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=10.0, help="bps per side (round-trip = 2x on replaced)")
    args = ap.parse_args()
    root = config.ROOT
    if not (root / DEEP).exists():
        print("no deep panel — run: .venv/bin/python -m scripts.china_residual_alpha_deep --fetch")
        return 1
    closes = pd.read_parquet(root / DEEP).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    members = pd.read_parquet(root / MEMBERS)
    sector = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})
    sector = sector.reindex(closes.columns).fillna("—")
    closes = closes.loc[:, sector != "—"]
    sector = sector[sector != "—"]

    rev3 = -closes.pct_change(63, fill_method=None)                   # 3-month reversal fuel
    fwd = closes.pct_change(21, fill_method=None).shift(-21)          # forward 21d (leak-free)
    idx = closes.index
    grid = [idx[idx <= me][-1] for me in pd.date_range(idx.min(), idx.max(), freq="ME")
            if (idx <= me).any()]
    grid = sorted(set(grid))
    print(f"panel: {closes.shape[1]} names · {idx.min().date()}..{idx.max().date()} · {len(grid)} month-ends · cost {args.cost}bps/side")
    print("computing leak-free sector washout/leading state ...")
    wash, lead = sector_state_gates(closes, sector, grid)

    eras = {"full": None, "2015+": pd.Timestamp("2015-01-01"), "2021+": pd.Timestamp("2021-01-01")}
    variants = {"FLAT": None, "WASHED-OUT": wash, "LEADING": lead}
    rows, pmap = [], {}
    for ename, start in eras.items():
        eg = [d for d in grid if (start is None or d >= start)]
        for vname, gate in variants.items():
            r = run(rev3, fwd, sector, eg, gate, args.cost)
            r["era"], r["variant"] = ename, vname
            rows.append(r)
            if "p_hac" in r and pd.notna(r["p_hac"]):
                pmap[f"{ename}|{vname}"] = r["p_hac"]
    fdr = benjamini_hochberg(pmap, alpha=0.10)

    hdr = f"{'era':7}{'variant':12}{'n':>4}{'sel':>4}{'gross%':>8}{'net%':>7}{'grSh':>6}{'netSh':>7}{'maxdd':>7}{'hit':>6}{'IC':>7}{'t_hac':>7}{'p_hac':>7}{'FDR✓':>6}"
    print("\n" + hdr); print("-" * len(hdr))
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        if r.get("error"):
            line = f"{r['era']:7}{r['variant']:12}{r['n']:>4}  (too few rebalances)"
        else:
            key = f"{r['era']}|{r['variant']}"
            rej = "yes" if fdr.get(key, {}).get("reject") else "—"
            line = (f"{r['era']:7}{r['variant']:12}{r['n']:>4}{r['med_sel']:>4}{r['gross_pct']:>8}{r['net_pct']:>7}"
                    f"{r['gross_sharpe']:>6}{r['net_sharpe']:>7}{r['maxdd_pct']:>7}{r['hit']:>6}{r['ic']:>7}{r['t_hac']:>7}{r['p_hac']:>7}{rej:>6}")
        print(line); out.append(line)

    rpt = root / "reports" / "china-reversal-gated.md"
    rpt.parent.mkdir(exist_ok=True)
    rpt.write_text(
        "# China reversal — does a subsector-state gate help?\n\n"
        f"3-month within-sector reversal, deepest quintile (LO={LO}). Gross + net-of-cost "
        f"({args.cost}bps/side, round-trip on the replaced sleeve). Leak-free sector state "
        "(engine.china_sector_pathway._position, own-history percentile). FDR=Benjamini-Hochberg "
        "across all era×variant cells (α=0.10).\n\n```\n" + "\n".join(out) + "\n```\n\n"
        "WASHED-OUT = sector state ≤35 (beaten down); LEADING = ≥65 (stretched/euphoric, the "
        "original 'gate to leading subsectors' idea); FLAT = no subsector gate.\n")
    print(f"\nwrote {rpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
