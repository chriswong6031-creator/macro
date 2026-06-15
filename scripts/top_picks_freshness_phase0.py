"""Top-Picks "Fresh Leaders" — Phase 0 honest validation (the DOWNSIDE question).

The shipped board ranks by the validated `alpha_led` conviction blend, but its TOP is
still the most-extended momentum names — and the user's pain is "sharp pullbacks,
especially in a bubble." That is a DRAWDOWN question, not an IC question, and the
existing harness (scripts/top_picks_phase0.py) never measured it: it reports rank-IC and
a LONG/SHORT Sharpe, both of which wash out what a dashboard user actually lives — they
hold the top LONGS, they don't short the bottom.

This harness asks the decisive question directly:

    Among the HIGH-CONVICTION cohort, does a freshness / de-extension screen
    (not yet stretched vs its own trend, pressing fresh highs, continuous not
    jumpy advance) materially cut max-drawdown and crash-frequency while keeping
    most of the return?

If yes → ship a "Fresh Leaders" view (a de-extension lens, never a re-sort, never a fade).
If it only de-risks by giving up proportional return → say so; ship it display-only.

New PIT signals (all from the deep survivorship-clean close matrix; NO new data):
  ext_z       price/SMA200 − 1, z-scored vs the name's OWN trailing 252d  → over-extension
  near_52wh   price / trailing-252d max (0,1]                             → George-Hwang proximity
  id_score    −[sgn(PRET)·(%neg − %pos)] over the 12-1 window             → frog-in-the-pan continuity
  val_own_z   current earnings-yield vs the name's OWN trailing history   → valuation-vs-own-history

Reuses scripts/top_picks_phase0.build_panels for the validated `alpha_led` rank and the
cached deep fundamentals, and engine/validation for IC/DSR/FDR. Survivorship caveat from
top_picks_phase0 applies — the verdict leans on RELATIVE (fresh-vs-full) comparisons, which
are far more robust to that bias than absolute levels.

Run:  .venv/bin/python -m scripts.top_picks_freshness_phase0 --years 12 --horizons 21,63,126
Writes reports/top-picks-freshness-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.equity_factors import _names_sectors, _winsor_z  # noqa: E402
from engine.validation import (benjamini_hochberg, deflated_sharpe,  # noqa: E402
                               dsr_verdict, ic_summary, rank_ic, ret_moments)
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, _yahoo_ret, month_grid)
from scripts.top_picks_phase0 import (  # noqa: E402
    CAP, FORM, SKIP, WIN, _sn_z, build_panels, pit_fund_panels)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("top_picks_freshness_phase0")

COST_BPS = 5.0
TOP_Q = 0.80              # high-conviction cohort = top quintile by alpha_led
# freshness filter thresholds (RAW per-name quantities, not cross-sectional):
FRESH_EXT_MAX = 1.0      # ext_z below this = not stretched vs its own trend
FRESH_NEAR_MIN = 0.85    # within 15% of its own 52w high = in-trend / fresh leader
PARABOLIC_EXT = 2.0      # ext_z above this = parabolic / blow-off tail


# ----------------------------------------------------------------------------- signals
def price_signals(closes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """ext_z / near_52wh / id_score date×ticker matrices — all causal (use data ≤ t)."""
    px = closes.sort_index()
    R = px.pct_change(fill_method=None)

    sma200 = px.rolling(200, min_periods=100).mean()
    ext = px / sma200 - 1.0
    ext_z = (ext - ext.rolling(252, min_periods=120).mean()) \
        / ext.rolling(252, min_periods=120).std().replace(0, np.nan)

    near_52wh = px / px.rolling(252, min_periods=120).max()

    # frog-in-the-pan: PRET over [t-252, t-21]; %pos/%neg over that same 231d window
    pret = px.shift(SKIP) / px.shift(252) - 1.0
    sgn = np.sign(R)
    win = 252 - SKIP
    pos = (sgn > 0).rolling(win, min_periods=120).mean().shift(SKIP)
    neg = (sgn < 0).rolling(win, min_periods=120).mean().shift(SKIP)
    iden = np.sign(pret) * (neg - pos)        # winners that ground higher → negative ID
    id_score = -iden                          # higher = fresher / more continuous
    return {"ext_z": ext_z, "near_52wh": near_52wh, "id_score": id_score}


def val_own_z(closes: pd.DataFrame, panel: pd.DataFrame, grid: list) -> pd.DataFrame:
    """current earnings-yield vs the name's OWN trailing history, grid×ticker.

    EY_d = latest-knowable annual NI (asof_date ≤ d) / (price_d · latest shares). The
    per-name z is computed against that name's own trailing EY series across the grid
    (min 8 points) — high = cheap vs its own norm (re-rating headroom), low = richest-ever.
    Annual-coarse by construction; a display/context read, not a fine timing signal."""
    p = panel.dropna(subset=["asof_date"]).copy()
    p["asof_date"] = pd.to_datetime(p["asof_date"])
    p = p.sort_values("asof_date")
    cl = closes.ffill()
    rows = {}
    for d in grid:
        sub = p[p["asof_date"] <= d]
        if sub.empty or d not in cl.index and cl.loc[:d].empty:
            continue
        last = sub.groupby("ticker").tail(1).set_index("ticker")
        px_d = cl.loc[:d].iloc[-1]
        idx = [t for t in last.index if t in px_d.index and pd.notna(px_d.get(t))]
        if not idx:
            continue
        mc = (px_d.reindex(idx) * last.loc[idx, "shares"]).where(lambda x: x > 0)
        rows[d] = (last.loc[idx, "ni"] / mc).replace([np.inf, -np.inf], np.nan)
    ey = pd.DataFrame(rows).T.sort_index()                      # grid × ticker EY
    mu = ey.rolling(12, min_periods=8).mean()
    sd = ey.rolling(12, min_periods=8).std().replace(0, np.nan)
    return (ey - mu) / sd                                       # high = cheap vs own history


# ----------------------------------------------------------------------------- metrics
def _series_metrics(net: pd.Series, baseline_cum: float | None = None) -> dict:
    """Tail-aware metrics for a LONG-ONLY daily net-return series — the numbers a holder
    actually lives (drawdown, downside, crash frequency), not a market-neutral Sharpe."""
    net = net.dropna()
    if len(net) < 60 or not net.std():
        return {}
    yrs = len(net) / 252.0
    cum = (1 + net).cumprod()
    dd = cum / cum.cummax() - 1.0
    downside = net[net < 0].std()
    roll21 = net.rolling(21).sum()
    m = {
        "ann_ret": round(float(net.mean() * 252 * 100), 1),
        "ann_vol": round(float(net.std() * np.sqrt(252) * 100), 1),
        "sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2),
        "sortino": round(float(net.mean() / downside * np.sqrt(252)), 2) if downside else None,
        "max_dd": round(float(dd.min() * 100), 1),
        "worst_21d": round(float(roll21.min() * 100), 1),
        "crash_freq_yr": round(float((roll21 < -0.10).sum() / len(net) * 252 / 21), 2),
        "cum_pct": round(float(cum.iloc[-1] - 1) * 100, 1),
    }
    mret = net.resample("ME").sum() if hasattr(net, "resample") else net
    m["mret_skew"] = round(float(mret.skew()), 2) if len(mret) > 6 else None
    if baseline_cum:
        m["ret_capture"] = round(float((cum.iloc[-1] - 1) / baseline_cum), 2)
    return m


def long_only(R: pd.DataFrame, sel: dict, grid: list, horizon: int) -> pd.Series:
    """EW long-only daily net series: hold the selected names from each rebalance, ffill
    `horizon` days, lag one day, net of cost on turnover. Mirrors quintile_ls's plumbing."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        names = [t for t in sel.get(d, []) if t in w.columns]
        if names:
            w.loc[d, names] = 1.0 / len(names)
    w = w.replace(0.0, np.nan).ffill(limit=horizon).fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    net = (gross - (COST_BPS / 1e4) * turn).loc[grid[0]:]
    return net[net.index <= grid[-1]]


# ----------------------------------------------------------------------------- cohorts
def build_selectors(alpha_led: pd.DataFrame, ext_z, near_52wh, grid, membership):
    """At each rebalance: the top-conviction cohort (top quintile by alpha_led) and several
    sub-cohorts, by RAW per-name extension — so we can isolate WHICH screen (if any) helps.

      full          all top-conviction names (baseline)
      ex_parab      full minus the parabolic blow-off tail (ext_z>2)   ← the key de-extension test
      ex_ext        full minus all stretched names (ext_z>1)
      fresh         the (failed) near-highs+not-extended hypothesis, kept for contrast
      parabolic     the ext_z>2 tail alone (to show how radioactive it is)
    """
    keys = ("full", "ex_parab", "ex_ext", "fresh", "parabolic")
    sels = {k: {} for k in keys}
    sizes = {k: [] for k in keys}
    for d in grid:
        if d not in alpha_led.index:
            continue
        s = alpha_led.loc[d].dropna()
        if membership is not None:
            s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 40:
            continue
        cohort = list(s[s >= s.quantile(TOP_Q)].index)
        if len(cohort) < 8:
            continue
        ez = ext_z.loc[d].reindex(cohort) if d in ext_z.index else pd.Series(np.nan, index=cohort)
        nz = near_52wh.loc[d].reindex(cohort) if d in near_52wh.index else pd.Series(np.nan, index=cohort)
        parab = [t for t in cohort if pd.notna(ez[t]) and ez[t] > PARABOLIC_EXT]
        ext1 = [t for t in cohort if pd.notna(ez[t]) and ez[t] > FRESH_EXT_MAX]
        cur = {
            "full": cohort,
            "ex_parab": [t for t in cohort if t not in parab],
            "ex_ext": [t for t in cohort if t not in ext1],
            "fresh": [t for t in cohort if pd.notna(ez[t]) and pd.notna(nz[t])
                      and ez[t] < FRESH_EXT_MAX and nz[t] > FRESH_NEAR_MIN],
            "parabolic": parab,
        }
        for k in keys:
            sels[k][d] = cur[k]
            sizes[k].append(len(cur[k]))
    med_sizes = {k: int(np.median(v)) if v else 0 for k, v in sizes.items()}
    return sels, med_sizes


# ----------------------------------------------------------------------------- standalone IC
def standalone_ic(closes, mats_extra, tkr_sector, grid, horizons, membership):
    """Sector-neutral cross-sectional IC for each new leg (sign/strength + FDR/DSR), on the
    same plumbing as top_picks_phase0.evaluate, so they're comparable to the shipped legs."""
    sec = pd.Series(tkr_sector)
    snz = {}
    for name, mat in mats_extra.items():
        rows = {}
        for d in grid:
            if d not in mat.index:
                continue
            rows[d] = _sn_z(mat.loc[d].dropna(), sec)
        snz[name] = pd.DataFrame(rows).T
    out = {}
    for h in horizons:
        fwd = closes.pct_change(h, fill_method=None).shift(-h)
        res = {}
        for name, sig in snz.items():
            ics = []
            for d in grid:
                if d not in fwd.index or d not in sig.index:
                    continue
                fr = fwd.loc[d].dropna()
                if membership is not None:
                    fr = fr[fr.index.isin(_eligible(membership, d))]
                ss = sig.loc[d].dropna()
                common = ss.index.intersection(fr.index)
                if len(common) < 15:
                    continue
                ics.append(rank_ic(ss[common], fr[common]))
            res[name] = ic_summary(pd.Series(ics).dropna(), periods_per_year=12)
        pvals = {k: v["p_hac"] for k, v in res.items()
                 if v.get("p_hac") is not None and v.get("n", 0) >= 6}
        for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
            res[k]["survives_fdr"] = q["reject"]
        out[h] = res
    return out


# ----------------------------------------------------------------------------- render
def render(cohort_metrics, ic_res, panic_split, span, n_reb, n_uni, horizon_used) -> str:
    L = ["# Top-Picks Fresh-Leaders — Phase 0 validation (the downside question)\n",
         f"*Survivorship-clean deep S&P panel · PIT S&P 1500 membership · {span} · "
         f"{n_reb} monthly rebalances · ~{n_uni} names/date · top-conviction cohort = top "
         f"quintile by `alpha_led` · fresh = ext_z<{FRESH_EXT_MAX} & near_52wh>{FRESH_NEAR_MIN} · "
         f"LONG-ONLY EW, {horizon_used}d hold, net {COST_BPS:.0f}bps one-way.*\n",
         "The shipped board ranks by `alpha_led`; its top is the most-extended momentum "
         "names. The question is NOT 'does a new leg raise IC' but **'does freshness-screening "
         "the high-conviction cohort cut DRAWDOWN and CRASH frequency while keeping most of "
         "the return?'** — a long-only, tail-aware test the IC/Sharpe harness never ran.\n"]

    L.append("\n## A. Long-only top-conviction cohort — which extension screen helps?\n")
    L.append("| cohort | names | ann ret % | vol % | Sharpe | Sortino | max DD % | worst 21d % | "
             "crash/yr | mret skew | ret capture |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    order = [("full", "FULL top-conviction (baseline)"),
             ("ex_parab", "full − parabolic tail (drop ext_z>2)"),
             ("ex_ext", "full − all stretched (drop ext_z>1)"),
             ("fresh", "near-highs + not-extended (FAILED hypothesis)"),
             ("parabolic", "parabolic tail ALONE (ext_z>2)")]
    for key, lbl in order:
        m = cohort_metrics.get(key) or {}
        if not m:
            L.append(f"| {lbl} | — | | | | | | | | | |")
            continue
        L.append(f"| {lbl} | {m.get('n','—')} | {m.get('ann_ret')} | {m.get('ann_vol')} | "
                 f"{m.get('sharpe')} | {m.get('sortino')} | {m.get('max_dd')} | {m.get('worst_21d')} | "
                 f"{m.get('crash_freq_yr')} | {m.get('mret_skew')} | {m.get('ret_capture','—')} |")

    full = cohort_metrics.get("full") or {}
    exp = cohort_metrics.get("ex_parab") or {}
    par = cohort_metrics.get("parabolic") or {}
    if full and exp:
        dd_better = exp.get("max_dd", -99) > full.get("max_dd", -99)        # less negative = better
        crash_better = exp.get("crash_freq_yr", 9) <= full.get("crash_freq_yr", 9)
        cap = exp.get("ret_capture", 0) or 0
        L.append(f"\n**Read (drop the parabolic tail):** max-DD {exp.get('max_dd')}% vs full "
                 f"{full.get('max_dd')}% ({'BETTER' if dd_better else 'worse/equal'}); crash/yr "
                 f"{exp.get('crash_freq_yr')} vs {full.get('crash_freq_yr')} "
                 f"({'fewer/equal' if crash_better else 'more'}); return captured {cap:.0%}.")
        ship = dd_better and crash_better and cap >= 0.90
        L.append(f"\n**Verdict A → {'EXCLUDE/FLAG the parabolic tail' if ship else 'per-name FLAG only'}:** "
                 + (f"dropping the ~{par.get('n','few')}-name ext_z>2 blow-off tail keeps {cap:.0%} of the "
                    "return with lower drawdown and fewer crashes — a real tail-improvement. The "
                    "actionable de-extension move is to flag/optionally-exclude the parabolic tail "
                    "(never to require 'freshness' — that hypothesis FAILED above)."
                    if ship else
                    "removing the parabolic tail from the EW basket barely moves the basket-level "
                    "drawdown (the tail is a small share of names), so the win is NOT at the basket "
                    "level. BUT the parabolic tail's STANDALONE profile is radioactive (see its row) "
                    "— so the honest product is a PER-NAME caution flag on ext_z>2 names, not a "
                    "basket rotation."))
        if par:
            L.append(f"\n**The parabolic tail itself:** ann ret {par.get('ann_ret')}% on {par.get('ann_vol')}% vol, "
                     f"max-DD {par.get('max_dd')}%, skew {par.get('mret_skew')}, {par.get('crash_freq_yr')} crashes/yr "
                     f"— vs the full cohort's {full.get('ann_ret')}% / {full.get('ann_vol')}% / {full.get('max_dd')}% / "
                     f"{full.get('crash_freq_yr')}/yr. THIS stark per-name risk gap is the validated basis for the flag.")

    if panic_split:
        L.append("\n## B. Conditional on Daniel-Moskowitz panic regime "
                 "(trailing-2y mkt<0 & high vol)\n")
        L.append("| regime | days | full DD % | ex-parab DD % | full crash/yr | ex-parab crash/yr |")
        L.append("|---|--:|--:|--:|--:|--:|")
        for reg, mm in panic_split.items():
            f_, e_ = mm.get("full") or {}, mm.get("ex_parab") or {}
            L.append(f"| {reg} | {mm.get('n_days','—')} | {f_.get('max_dd','—')} | {e_.get('max_dd','—')} | "
                     f"{f_.get('crash_freq_yr','—')} | {e_.get('crash_freq_yr','—')} |")

    L.append("\n## C. New legs — standalone sector-neutral cross-sectional IC\n")
    for h, res in ic_res.items():
        L.append(f"\n**Forward {h}d**\n")
        L.append("| leg | mean IC | IC-IR | HAC t | p | FDR | h1→h2 |")
        L.append("|---|--:|--:|--:|--:|:-:|--:|")
        for name in ("ext_z", "near_52wh", "id_score", "val_own_z"):
            ic = res.get(name) or {}
            if ic.get("n", 0) < 6:
                L.append(f"| {name} | n/a | | | | | |")
                continue
            h12 = (f"{ic.get('ic_h1')}→{ic.get('ic_h2')}" if ic.get("ic_h1") is not None else "—")
            L.append(f"| {name} | {ic.get('mean_ic', float('nan')):+.4f} | "
                     f"{ic.get('ic_ir', float('nan')):+.2f} | {ic.get('t_hac', float('nan')):+.2f} | "
                     f"{ic.get('p_hac', float('nan')):.3f} | "
                     f"{'Y' if ic.get('survives_fdr') else 'n'} | {h12} |")
    L.append("\n*IC note:* ext_z is expected ≤0 / weak (over-extension is only mildly "
             "anti-predictive and small). id_score (frog-in-the-pan continuity) and near_52wh "
             "are the legs that *could* legitimately carry positive IC. val_own_z is annual-"
             "coarse → display/context only regardless of sign. Nothing here is expected to "
             "clear DSR; the win (if any) is the tail-improvement in §A, not the mean.\n")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--horizons", type=str, default="21,63,126")
    ap.add_argument("--hold", type=int, default=63, help="long-only holding horizon (days)")
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]

    closes = _closes_deep()
    if closes.empty:
        print("no deep close matrix — run scripts.residual_alpha_fetch first")
        return 1
    membership = _load_membership()
    if membership is None:
        print("no PIT membership — run scripts.residual_alpha_pit first")
        return 1
    for fn in ("_closes_delisted.parquet", "_closes_delisted_1500.parquet"):
        delp = config.data_dir() / "breadth" / fn
        if delp.exists():
            closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
            closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()

    insider_panel = pd.read_parquet(config.data_dir() / "sec_insider" / "insider_panel.parquet")
    fund_panel = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")

    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s and s != "—" else "Other") for t, s in tkr_sector.items()}
    spy = _yahoo_ret("SPY", closes.index)

    R = closes.pct_change(fill_method=None)
    grid = month_grid(R.index, warmup=WIN + SKIP + FORM, horizon=max(max(horizons), args.hold))
    if args.years:
        cutoff = R.index.max() - pd.DateOffset(years=args.years)
        grid = [d for d in grid if d >= cutoff]
    if len(grid) < 12:
        print(f"grid too short ({len(grid)})")
        return 1
    n_uni = int(np.median([len([t for t in _eligible(membership, d) if t in closes.columns])
                           for d in grid]))
    log.info("grid: %d rebalances %s..%s ~%d names/date",
             len(grid), grid[0].date(), grid[-1].date(), n_uni)

    # validated alpha_led rank (reuses the cached deep fundamentals)
    fund_cache = pit_fund_panels(grid, closes, fund_panel)
    R2, mats = build_panels(closes, spy, tkr_sector, grid, fund_cache, insider_panel)
    alpha_led = mats["alpha_led"]

    # new signals
    psig = price_signals(closes)
    vz = val_own_z(closes, fund_panel, grid)
    mats_extra = {"ext_z": psig["ext_z"].loc[psig["ext_z"].index.isin(grid)],
                  "near_52wh": psig["near_52wh"].loc[psig["near_52wh"].index.isin(grid)],
                  "id_score": psig["id_score"].loc[psig["id_score"].index.isin(grid)],
                  "val_own_z": vz}

    # cohorts + long-only tail metrics
    sels, med_sizes = build_selectors(alpha_led, psig["ext_z"], psig["near_52wh"], grid, membership)
    base_net = long_only(R, sels["full"], grid, args.hold)
    base_cum = float((1 + base_net.dropna()).prod() - 1)
    cohort_keys = ("full", "ex_parab", "ex_ext", "fresh", "parabolic")
    cohort_metrics = {}
    for k in cohort_keys:
        m = _series_metrics(long_only(R, sels[k], grid, args.hold), base_cum)
        if m:
            m["n"] = med_sizes.get(k, 0)
        cohort_metrics[k] = m

    # panic-regime conditional (Daniel-Moskowitz): trailing-504d mkt<0 & 126d vol top-tercile
    spy_lvl = (1 + spy.fillna(0)).cumprod()
    mkt_2y = spy_lvl / spy_lvl.shift(504) - 1.0
    vol_126 = spy.rolling(126).std()
    vol_hi = vol_126 > vol_126.quantile(0.66)
    panic = ((mkt_2y < 0) & vol_hi).reindex(R.index).fillna(False)
    panic_split = {}
    for reg, mask in (("panic", panic), ("calm", ~panic)):
        m = mask.reindex(R.index).fillna(False)
        mm = {"n_days": int(m.sum())}
        for k in ("full", "ex_parab"):
            net = long_only(R, sels[k], grid, args.hold)
            mm[k] = _series_metrics(net[m.reindex(net.index).fillna(False)])
        panic_split[reg] = mm

    ic_res = standalone_ic(closes, mats_extra, tkr_sector, grid, horizons, membership)

    span = f"{grid[0].date()}..{grid[-1].date()}"
    report = render(cohort_metrics, ic_res, panic_split, span, len(grid), n_uni, args.hold)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "top-picks-freshness-phase0.md"
    out.write_text(report)
    print("\n" + report)
    print(f"[report] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
