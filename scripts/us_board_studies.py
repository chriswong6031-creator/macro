#!/usr/bin/env python3
"""US Buy Board — the deciding studies (§W6-US Priority 2).

Runs three panel studies that decide the Buy Board 2.0 knobs (US-3):

  1. MAE STUDY (contrarian #1 — the analysis's biggest blind spot). Compares a
     TIMING/bottoming-gated entry cohort vs an ALPHA-ranked entry cohort on forward
     MAE (close-path drawdown) AND forward return. Tests the claim: timing is a
     legitimate RISK-PLACEMENT layer (shallower drawdowns) even with ~0 return edge.
     -> decides whether v2 orders by edge and merely GATES by timing.

  2. PRECISION@k for candidate rank keys (their Q3). The product is a discrete
     BUY classifier, so rank-IC is the wrong yardstick — we measure P(fwd>0 | top-k)
     and top-k mean excess for: residual alpha, short-term reversal (the closest
     harness-testable proxy for the never-validated live `bottoming-alignment` key),
     and composite (equal-weight edge+timing).

  3. DISPERSION-BUCKET CONDITIONING (their D2 — validate-first). Conditions the
     residual-alpha rank-IC / precision on three cross-sectional dispersion states.
     Answers: does the dispersion regime actually modulate selection payoff on OUR legs?

POWER GUARD (mirrors scripts/stock_conviction_phase0.py's doctrine)
-------------------------------------------------------------------
The deep survivorship-clean panel (data/edgar/sue_deep_closes.parquet /
data/breadth/_closes_deep.parquet) and PIT membership are LOCAL-ONLY offline
artifacts — absent from the committed repo (dropped in 031900e7). Without them this
harness runs on the SHALLOW `broad` cache (~3y, 2023-05..latest, current-membership
= survivorship-INFLATED). Every number below is therefore UNPOWERED and
survivorship-biased. It is DIRECTIONAL SHAPE, never a GO. The POWERED anchor is the
committed reports/stock-conviction-phase0.md (deep+PIT 2008-2025, 210 rebalances):
that run tested 11 composites — NONE was the live `bottoming-alignment` key — and the
`entry axis (reversal proxy)` (the closest timing proxy) had NEGATIVE mean IC at every
horizon (21d -0.0027, 63d -0.0034, 126d -0.0088). Best composite regime·PEAD +0.021 IC,
DSR 0.053 << 0.90. Read this study alongside that anchor.

The exact live key `bottoming-alignment` (engine.cycles.mtf_alignment) needs the full
per-name W/3D/D MACD+StochRSI stack; reconstructing it across the panel is out of scope
for one session. We use short-term reversal (rev_st) as the harness-testable timing
proxy and NOTE the gap explicitly — grading the true live key is itself flagged as the
honest first step the audit demanded (open question A1).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from scripts.residual_alpha_phase0 import build_residuals, signal_matrices  # noqa: E402

OUT_JSON = ROOT / "data" / "us_board_ledger" / "studies.json"
BENCH = "SPY"
HORIZONS = [5, 10, 21]
WIN, MINP, FORM, SKIP = 126, 60, 126, 5   # residual betas / momentum formation (matches phase0 spirit)
TOPK = [1, 3, 5, 10, 20]
DECILE = 0.10


def _load():
    closes = _closes("broad").sort_index()
    closes.index = pd.to_datetime(closes.index)
    ypath = ROOT / "data" / "yahoo"
    spy = pd.read_parquet(ypath / f"{BENCH}.parquet")["close"]
    spy.index = pd.to_datetime(spy.index)
    market = spy.reindex(closes.index).ffill().pct_change(fill_method=None)
    ns = _names_sectors()
    tkr_sector = {t: v[1] for t, v in ns.items() if t in closes.columns and v[1]}
    # drop tickers without a sector (residual builder needs it)
    closes = closes[[t for t in closes.columns if t in tkr_sector]]
    return closes, spy, market, tkr_sector


def _sector_ret(sec, cols, R):
    """Equal-weight peer return for a sector (residual builder's sector leg)."""
    sub = R[cols]
    return sub.mean(axis=1)


def _month_ends(index, warmup, horizon):
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc >= warmup and loc + max(HORIZONS) < len(index):
            out.append(d[-1])
    return out


def _fwd_metrics(closes, spy, entry_i, tickers, h):
    """For a set of tickers, entry at NEXT bar close after rebalance date index entry_i,
    horizon h. Returns dict ticker -> (excess_ret, close_path_mae_excess)."""
    idx = closes.index
    e = entry_i + 1  # next-bar entry
    if e + h >= len(idx):
        return {}
    sp = spy.reindex(idx).ffill()
    sp0 = sp.iloc[e]
    out = {}
    for t in tickers:
        ser = closes[t]
        p0 = ser.iloc[e]
        p1 = ser.iloc[e + h]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0 or pd.isna(sp0) or sp0 <= 0:
            continue
        ret = p1 / p0 - 1.0
        spret = sp.iloc[e + h] / sp0 - 1.0
        exc = ret - spret
        worst = 0.0
        for j in range(1, h + 1):
            pj = ser.iloc[e + j]
            spj = sp.iloc[e + j]
            if pd.isna(pj) or pd.isna(spj):
                continue
            worst = min(worst, (pj / p0 - 1.0) - (spj / sp0 - 1.0))
        out[t] = (exc, worst)
    return out


def run(quiet=False):
    closes, spy, market, tkr_sector = _load()
    powered = not _closes("deep").empty  # False here (deep absent)
    R, eps = build_residuals(closes, market, tkr_sector, _sector_ret, WIN, MINP, shrink=0.66)
    sigs = signal_matrices(R, eps, FORM, SKIP)
    alpha = sigs["mom_res"]      # residual momentum = the "alpha" rank leg
    timing = -sigs["rev_st"]     # short-term reversal proxy for bottoming (buy recent losers)
    # equal-weight composite of standardized alpha + timing (edge+timing blend)
    def _xs_z(m):
        return m.sub(m.mean(axis=1), axis=0).div(m.std(axis=1).replace(0, np.nan), axis=0)
    comp = (_xs_z(alpha) + _xs_z(timing)) / 2.0

    grid = _month_ends(R.index, warmup=WIN + FORM + SKIP, horizon=max(HORIZONS))
    idx = closes.index

    # cross-sectional dispersion state per rebalance (tercile of 63d cross-sec return std)
    disp_series = closes.pct_change(63, fill_method=None).std(axis=1)

    # ---- accumulate ----
    keys = {"alpha": alpha, "timing_proxy": timing, "composite": comp}
    # precision@k and rank-IC per key per horizon
    pk_rows = []       # (key, h, board_date, k, hits, n, mean_exc)
    ic_rows = []       # (key, h, board_date, ic)
    # MAE cohorts: top-decile by alpha vs top-decile by timing
    mae_rows = []      # (cohort, h, board_date, ticker, excess, mae)
    # dispersion conditioning
    disp_rows = []     # (key, h, disp_bucket, board_date, ic, topk hits/n)

    disp_terciles = disp_series.reindex([d for d in grid]).dropna()
    if len(disp_terciles) >= 3:
        q1, q2 = disp_terciles.quantile([1/3, 2/3])
    else:
        q1 = q2 = disp_terciles.median() if len(disp_terciles) else 0.0

    for d in grid:
        loc = idx.get_loc(d)
        dv = disp_series.get(d, np.nan)
        dbucket = ("low_disp" if dv <= q1 else "high_disp" if dv > q2 else "mid_disp") if not pd.isna(dv) else "na"
        for h in HORIZONS:
            fwd_all = None
            for kname, kmat in keys.items():
                row = kmat.loc[d].dropna()
                if len(row) < 20:
                    continue
                # rank-IC vs forward excess
                if fwd_all is None:
                    fm = _fwd_metrics(closes, spy, loc, row.index.tolist(), h)
                    fwd_all = fm
                else:
                    fm = _fwd_metrics(closes, spy, loc, row.index.tolist(), h)
                common = [t for t in row.index if t in fm]
                if len(common) < 20:
                    continue
                sig = row.loc[common]
                exc = pd.Series({t: fm[t][0] for t in common})
                ic = sig.rank().corr(exc.rank())
                ic_rows.append((kname, h, d, ic))
                if dbucket != "na":
                    disp_rows.append((kname, h, dbucket, d, ic))
                ranked = sig.sort_values(ascending=False)
                for k in TOPK:
                    top = ranked.head(k).index
                    e = [fm[t][0] for t in top if t in fm]
                    if not e:
                        continue
                    pk_rows.append((kname, h, d, k, int(np.sum(np.array(e) > 0)), len(e), float(np.mean(e))))
            # MAE cohorts (only need alpha vs timing top-decile)
            fm = _fwd_metrics(closes, spy, loc, closes.columns.tolist(), h)
            for cohort, kmat in (("alpha_ranked", alpha), ("timing_gated", timing)):
                row = kmat.loc[d].dropna()
                row = row[[t for t in row.index if t in fm]]
                if len(row) < 20:
                    continue
                n_top = max(int(len(row) * DECILE), 5)
                top = row.sort_values(ascending=False).head(n_top).index
                for t in top:
                    exc, mae = fm[t]
                    mae_rows.append((cohort, h, d, t, exc, mae))

    return _summarize(powered, grid, pk_rows, ic_rows, mae_rows, disp_rows, q1, q2, quiet)


def _summarize(powered, grid, pk_rows, ic_rows, mae_rows, disp_rows, q1, q2, quiet):
    ic = pd.DataFrame(ic_rows, columns=["key", "h", "date", "ic"])
    pk = pd.DataFrame(pk_rows, columns=["key", "h", "date", "k", "hits", "n", "mean_exc"])
    mae = pd.DataFrame(mae_rows, columns=["cohort", "h", "date", "ticker", "excess", "mae"])
    disp = pd.DataFrame(disp_rows, columns=["key", "h", "bucket", "date", "ic"])

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "powered": powered,
        "power_note": (
            "UNPOWERED shallow run (no deep panel / no PIT membership) — survivorship-INFLATED, "
            "DIRECTIONAL ONLY. Powered anchor: reports/stock-conviction-phase0.md (deep+PIT 2008-2025)."
        ),
        "panel": {"n_rebalances": len(grid),
                  "range": [grid[0].date().isoformat(), grid[-1].date().isoformat()] if grid else None,
                  "horizons": HORIZONS, "top_decile": DECILE},
        "the_live_key_gap": (
            "The shipped rank key `bottoming-alignment` (engine.cycles.mtf_alignment) was NEVER fed "
            "to any validation harness — not the deep phase0 run, not this one. Timing here is the "
            "short-term-reversal PROXY. Grading the TRUE live key end-to-end (reconstruct the W/3D/D "
            "stack over history) remains the honest first step (audit open question A1)."),
    }

    # STUDY 1: MAE
    m1 = {}
    for h in HORIZONS:
        hh = mae[mae.h == h]
        blk = {}
        for cohort in ("alpha_ranked", "timing_gated"):
            c = hh[hh.cohort == cohort]
            if c.empty:
                blk[cohort] = {"n": 0}
                continue
            blk[cohort] = {
                "n": int(len(c)),
                "n_rebalances": int(c["date"].nunique()),
                "median_excess": round(float(c["excess"].median()), 5),
                "mean_excess": round(float(c["excess"].mean()), 5),
                "hit_rate": round(float((c["excess"] > 0).mean()), 4),
                "median_mae_close_excess": round(float(c["mae"].median()), 5),
                "mean_mae_close_excess": round(float(c["mae"].mean()), 5),
                "p5_mae": round(float(c["mae"].quantile(0.05)), 5),  # deep-drawdown tail
            }
        # verdict
        a, t = blk.get("alpha_ranked", {}), blk.get("timing_gated", {})
        if a.get("n") and t.get("n"):
            mae_benefit = t["median_mae_close_excess"] - a["median_mae_close_excess"]
            ret_cost = t["median_excess"] - a["median_excess"]
            blk["_verdict"] = {
                "timing_mae_shallower_by": round(mae_benefit, 5),
                "timing_return_delta": round(ret_cost, 5),
                "reading": ("timing cohort has SHALLOWER median close-path drawdown"
                            if mae_benefit > 0 else
                            "timing cohort has DEEPER/equal median close-path drawdown"),
            }
        m1[f"h{h}"] = blk
    out["study1_mae_timing_vs_alpha"] = m1

    # STUDY 2: precision@k + rank-IC per key
    m2 = {}
    for key in ("alpha", "timing_proxy", "composite"):
        kb = {}
        for h in HORIZONS:
            icv = ic[(ic.key == key) & (ic.h == h)]["ic"].dropna()
            pkh = pk[(pk.key == key) & (pk.h == h)]
            base = pkh[pkh.k == pkh.k.max()] if not pkh.empty else pkh  # widest = base rate proxy
            row = {"mean_rank_ic": round(float(icv.mean()), 4) if len(icv) else None,
                   "ic_ir": round(float(icv.mean() / icv.std()), 3) if len(icv) > 2 and icv.std() else None,
                   "n_rebalances": int(icv.shape[0])}
            for k in TOPK:
                g = pkh[pkh.k == k]
                if g.empty:
                    continue
                tot_hits = int(g["hits"].sum())
                tot_n = int(g["n"].sum())
                row[f"P@{k}"] = round(tot_hits / tot_n, 4) if tot_n else None
                row[f"mean_exc@{k}"] = round(float(g["mean_exc"].mean()), 5)
            kb[f"h{h}"] = row
        m2[key] = kb
    # base rate = mean hit across ALL names each rebalance (use the widest top-k as an approx base)
    out["study2_precision_at_k"] = m2

    # STUDY 3: dispersion conditioning (residual alpha)
    m3 = {"dispersion_terciles_63d_std": {"q33": round(float(q1), 5), "q67": round(float(q2), 5)}}
    for key in ("alpha", "timing_proxy"):
        kb = {}
        for h in HORIZONS:
            hb = {}
            for bucket in ("low_disp", "mid_disp", "high_disp"):
                g = disp[(disp.key == key) & (disp.h == h) & (disp.bucket == bucket)]["ic"].dropna()
                pkg = pk[(pk.key == key) & (pk.h == h)]
                # precision@5 conditioned on bucket
                dates_b = set(disp[(disp.bucket == bucket)]["date"])
                pk5 = pkg[(pkg.k == 5) & (pkg.date.isin(dates_b))]
                hb[bucket] = {
                    "mean_ic": round(float(g.mean()), 4) if len(g) else None,
                    "n_rebalances": int(g.shape[0]),
                    "P@5": round(int(pk5["hits"].sum()) / int(pk5["n"].sum()), 4)
                    if not pk5.empty and pk5["n"].sum() else None,
                }
            kb[f"h{h}"] = hb
        m3[key] = kb
    # verdict: does dispersion modulate alpha payoff?
    a21 = m3.get("alpha", {}).get("h21", {})
    ics = [a21.get(b, {}).get("mean_ic") for b in ("low_disp", "mid_disp", "high_disp")]
    ics = [x for x in ics if x is not None]
    m3["_verdict"] = {
        "alpha_ic_spread_across_buckets_h21": round(max(ics) - min(ics), 4) if len(ics) == 3 else None,
        "reading": "compare mean_ic across low/mid/high dispersion buckets — a large monotone "
                   "spread would justify a dispersion-modulated edge floor; a noisy/small spread "
                   "(likely at this n) means DISPLAY-ONLY per the passport rule.",
    }
    out["study3_dispersion_conditioning"] = m3

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str))
    if not quiet:
        print(f"[studies] wrote {OUT_JSON.relative_to(ROOT)} (powered={powered}, "
              f"{len(grid)} rebalances {out['panel']['range']})")
        # headline
        for h in HORIZONS:
            v = m1[f"h{h}"].get("_verdict", {})
            print(f"  MAE h{h}: timing MAE shallower by {v.get('timing_mae_shallower_by')} "
                  f"(ret delta {v.get('timing_return_delta')}) -> {v.get('reading')}")
        for key in ("alpha", "timing_proxy", "composite"):
            r = m2[key]["h21"]
            print(f"  P@k h21 {key}: IC={r.get('mean_rank_ic')} P@1={r.get('P@1')} "
                  f"P@5={r.get('P@5')} P@10={r.get('P@10')}")
        print(f"  dispersion verdict: alpha IC spread across buckets (h21) = "
              f"{m3['_verdict']['alpha_ic_spread_across_buckets_h21']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run(quiet=args.quiet)


if __name__ == "__main__":
    main()
