"""Top-Picks composite — Phase 0 honest validation.

THE QUESTION the "Alpha leaders" revamp turns on: does a HOLISTIC multi-factor
*conviction* composite rank US forward returns better than the residual-momentum leg
the board ranks by today? And — separately — does folding a mean-reversion / entry tilt
INTO the rank help (the China construction) or hurt (US momentum continues)?

This decides the design:
  * if a composite beats `alpha` on BOTH mean rank-IC AND quintile L/S Sharpe → rank the
    new "Top Picks" board by that composite (a measured upgrade over alpha-alone);
  * else → keep the alpha rank, show the other legs as *conviction context*, and put
    entry-timing on a SEPARATE axis (the honest US analog of China's folded reversal —
    because, unlike A-shares, US extended leaders keep running, so a reversal tilt in the
    RANK dilutes it; see reports/setup-score-phase0.md).

Legs (all point-in-time / leak-free, sector-neutralised within GICS, winsor-z per date):
  alpha       residual-momentum IR z                   the validated context leg = BASELINE
  value       PIT value z (EY+BP+SP+CFOy)               engine.equity_factors, asof=d
  quality     PIT quality z (ROE − accruals − leverage)
  profit      PIT gross profitability z (Novy-Marx)
  lowvol      PIT low-vol z (the low-vol anomaly)
  insider     net insider $ / mktcap (Form-4 PIT)       FDR survivor in mid-cap (insider-phase0)
  streversal  21d short-term reversal (−1m return)      the ENTRY leg, tested standalone

Composites:
  conviction       EW z-mean of {alpha,value,quality,profit,lowvol,insider} — NO timing
  alpha_led        0.6·alpha + 0.4·mean(value,quality,profit,lowvol,insider)
  conviction_rev   conviction + a reversal entry tilt   (does folding US reversal in help?)

Data: deep survivorship-clean S&P panel (1962→) + PIT S&P 1500 membership + recovered
delistings + EDGAR PIT fundamentals + the Form-4 panel — ALL cached on disk, no network.
Per-date PIT factor tables are cached to a parquet (one sweep serves every horizon/re-run).

Run:  .venv/bin/python -m scripts.top_picks_phase0 --years 12 --horizons 21,63,126
Writes reports/top-picks-phase0.md. No commit, no site build — pure harness.
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
from engine.insider_factor import build_signals, classify_routine, market_cap  # noqa: E402
from engine.validation import (benjamini_hochberg, deflated_sharpe,  # noqa: E402
                               dsr_verdict, ic_summary, rank_ic, ret_moments)
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, _yahoo_ret, build_residuals,
    ew_peer, month_grid)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("top_picks_phase0")

# production residual-alpha windows (engine.residual_alpha._defaults) — validate the
# SHIPPED selection leg, not a re-tuned one.
WIN, FORM, SKIP, SHRINK, CAP = 252, 252, 21, 0.66, 3.0
COST_BPS = 5.0                            # single-name one-way, charged on quintile turnover
INSIDER_WINDOW_M = 6                      # trailing Form-4 filing window (insider-phase0 default)

# the conviction legs (no timing) and the per-leg source. `streversal` is held out as the
# entry leg; the fundamental legs come from compute_factors(asof)["table"].
FUND_LEGS = ["value", "quality", "profitability", "low_vol"]
CONVICTION_LEGS = ["alpha", "value", "quality", "profitability", "low_vol", "insider"]


def _fund_cache_path() -> Path:
    return config.data_dir() / "regime" / "top_picks_phase0_fund_deep_cache.parquet"


def pit_fund_panels(grid: list, closes: pd.DataFrame, panel: pd.DataFrame) -> dict:
    """{date_str: DataFrame[ticker × {value,quality,profitability,low_vol}]} computed
    DIRECTLY on the deep close matrix + the leak-free EDGAR fundamentals panel (the same
    factor maths as engine.equity_factors.compute_factors, but on deep history instead of
    its shallow ~3y price cache — so the fundamental legs get a real 2014→ test, not a
    2023+ stub). PIT: at each date only the latest filing with asof_date ≤ d is used, and
    the price/vol are truncated to d. Cached to parquet (horizon-independent)."""
    cache: dict[str, pd.DataFrame] = {}
    cp = _fund_cache_path()
    if cp.exists():
        try:
            df = pd.read_parquet(cp)
            for ds, sub in df.groupby("date"):
                cache[ds] = sub.set_index("ticker")[FUND_LEGS]
            log.info("deep fund cache: %d dates loaded", len(cache))
        except Exception as e:  # noqa: BLE001
            log.warning("deep fund cache unreadable (%s) — recomputing", e)
    todo = [d for d in grid if str(d.date()) not in cache]
    log.info("PIT deep fundamentals: %d cached, %d to compute", len(cache), len(todo))

    p = panel.dropna(subset=["asof_date"]).copy()
    p["asof_date"] = pd.to_datetime(p["asof_date"])
    p = p.sort_values("asof_date")
    rets = closes.pct_change(fill_method=None)

    for i, d in enumerate(todo):
        ds = str(d.date())
        sub = p[p["asof_date"] <= d]
        cl = closes.loc[:d]
        if sub.empty or cl.empty:
            cache[ds] = pd.DataFrame()
            continue
        last = sub.groupby("ticker").tail(1).set_index("ticker")
        px_d = cl.ffill().iloc[-1]
        idx = [t for t in last.index if t in px_d.index and pd.notna(px_d.get(t))]
        if len(idx) < 30:
            cache[ds] = pd.DataFrame()
            continue
        last = last.loc[idx]
        price = px_d.reindex(idx)
        mc = (price * last["shares"]).where(lambda x: x > 0)
        avg_assets = (last["assets"] + last["assets_prior"]) / 2.0
        ey, bp = last["ni"] / mc, last["equity"] / mc
        sp, cfoy = last["revenue"] / mc, last["cfo"] / mc
        value = pd.concat([_winsor_z(ey, CAP), _winsor_z(bp, CAP),
                           _winsor_z(sp, CAP), _winsor_z(cfoy, CAP)], axis=1).mean(axis=1)
        profit = _winsor_z(last["gross_profit"] / last["assets"], CAP)
        roe = _winsor_z(last["ni"] / last["equity"].where(last["equity"] > 0), CAP)
        accr = _winsor_z((last["ni"] - last["cfo"]) / avg_assets, CAP)
        lev = _winsor_z(last["debt_lt"] / last["assets"], CAP)
        quality = pd.concat([roe, -accr, -lev], axis=1).mean(axis=1)
        sub_r = rets.loc[:d].tail(252)
        vol = sub_r.std() * np.sqrt(252)
        vol[sub_r.count() < 120] = np.nan
        low_vol = (-vol).reindex(idx)
        cache[ds] = pd.DataFrame({"value": value, "quality": quality,
                                  "profitability": profit, "low_vol": low_vol})
        if (i + 1) % 20 == 0:
            log.info("  PIT deep fundamentals: %d/%d", i + 1, len(todo))
    # persist the merged cache (full rewrite)
    try:
        allrows = []
        for ds, tbl in cache.items():
            if tbl is None or tbl.empty:
                continue
            r = tbl.reset_index().rename(columns={"index": "ticker"})
            r.insert(0, "date", ds)
            allrows.append(r)
        if allrows:
            cp.parent.mkdir(parents=True, exist_ok=True)
            pd.concat(allrows, ignore_index=True).to_parquet(cp, index=False)
    except Exception as e:  # noqa: BLE001
        log.warning("deep fund cache write failed (%s)", e)
    return cache


def _sn_z(s: pd.Series, sec: pd.Series, cap: float = CAP) -> pd.Series:
    """Sector-neutral winsor-z: within-GICS demean then winsorised cross-sectional z,
    so every leg is on the SAME unit-variance, sector-neutral scale before blending."""
    s = s.dropna()
    if len(s) < 10:
        return pd.Series(dtype=float)
    sec_a = sec.reindex(s.index)
    dem = s - s.groupby(sec_a).transform("mean")
    return _winsor_z(dem, cap).dropna()


def build_panels(closes, market, tkr_sector, grid, fund_cache, insider_panel):
    """Per-grid-date sector-neutral cross-sections for every leg + the composites,
    all on the common eligible set per date → {signal: date×ticker matrix}."""
    sec = pd.Series(tkr_sector)
    # --- selection: residual-momentum IR z + short reversal -------------------
    R, eps = build_residuals(closes, market, tkr_sector, ew_peer,
                             WIN, max(WIN // 2, 40), SHRINK)
    ir = (eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).mean()
          / eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).std())
    rev_raw = R.rolling(SKIP, min_periods=max(SKIP // 2, 5)).sum()    # 21d return; reversal = −this

    # --- insider net $ / mktcap (PIT, sector-neutral) -------------------------
    closes_me = closes.loc[[d for d in grid if d in closes.index]]
    shares_panel = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    mcap = market_cap(closes_me, shares_panel, grid)
    ins_sigs = build_signals(classify_routine(insider_panel), grid, mcap=mcap,
                             k_months=INSIDER_WINDOW_M)
    ins_mcap = ins_sigs.get("net_usd_mcap")

    legs = ["alpha", "value", "quality", "profitability", "low_vol", "insider", "streversal"]
    comps = ["conviction", "alpha_led", "conviction_rev"]
    panels = {k: {} for k in legs + comps}

    for d in grid:
        if d not in ir.index:
            continue
        row = ir.loc[d].dropna()
        if len(row) < 25:
            continue
        az = _sn_z(row, sec)                                   # sector-neutral residual z
        if len(az) < 25:
            continue
        idx = az.index
        leg_z: dict[str, pd.Series] = {"alpha": az}
        # short reversal = −(21d return), sector-neutral
        leg_z["streversal"] = _sn_z(-rev_raw.loc[d].reindex(idx), sec)
        # PIT fundamentals
        ftbl = fund_cache.get(str(d.date()))
        for leg in FUND_LEGS:
            col = ftbl[leg] if (ftbl is not None and not ftbl.empty and leg in ftbl.columns) \
                else pd.Series(dtype=float)
            leg_z[leg] = _sn_z(col.reindex(idx), sec)
        # insider
        ins = ins_mcap.loc[d].reindex(idx) if (ins_mcap is not None and d in ins_mcap.index) \
            else pd.Series(dtype=float)
        leg_z["insider"] = _sn_z(ins, sec)

        # assemble — reindex every leg to the alpha universe; missing legs → 0 (neutral)
        Z = pd.DataFrame({k: v.reindex(idx) for k, v in leg_z.items()})
        conv = Z[CONVICTION_LEGS].mean(axis=1, skipna=True)    # EW z-mean, NO timing
        others = Z[["value", "quality", "profitability", "low_vol", "insider"]].mean(axis=1, skipna=True)
        alpha_led = 0.6 * Z["alpha"] + 0.4 * others.fillna(0.0)
        conv_rev = conv + 0.5 * Z["streversal"].fillna(0.0)    # fold reversal in (China-style)

        for leg in legs:
            panels[leg][d] = Z[leg].dropna()
        panels["conviction"][d] = conv.dropna()
        panels["alpha_led"][d] = alpha_led.dropna()
        panels["conviction_rev"][d] = conv_rev.dropna()

    cols = R.columns
    mats = {k: pd.DataFrame(v).T.reindex(columns=cols) for k, v in panels.items()}
    return R, mats


def quintile_ls(R, sig, grid, horizon, n_trials, membership=None):
    """Long top-quintile / short bottom-quintile, EW, monthly rebalance, net of cost."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        s = sig.loc[d].dropna() if d in sig.index else pd.Series(dtype=float)
        if membership is not None:
            s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 25:
            continue
        hi, lo = s.quantile(0.8), s.quantile(0.2)
        top, bot = s[s >= hi].index, s[s <= lo].index
        if len(top) and len(bot) and hi > lo:
            w.loc[d, top] = 1.0 / len(top)
            w.loc[d, bot] = -1.0 / len(bot)
    w = w.replace(0.0, np.nan).ffill(limit=horizon).fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    net = (gross - (COST_BPS / 1e4) * turn).loc[grid[0]:]
    net = net[net.index <= grid[-1]]
    mom = ret_moments(net)
    out = {"sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2) if net.std() else None,
           "cum_pct": round(float(((1 + net).prod() - 1) * 100), 1)}
    if mom:
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=max(n_trials, 1),
                              trading_year=252)
        if dsr:
            out["dsr"] = dsr["dsr"]
            out["verdict"] = dsr_verdict(dsr["dsr"])
    return out


def _split_half(per_date_ic: pd.Series) -> dict:
    s = per_date_ic.dropna()
    if len(s) < 12:
        return {}
    mid = len(s) // 2
    return {"ic_h1": round(float(s.iloc[:mid].mean()), 4),
            "ic_h2": round(float(s.iloc[mid:].mean()), 4)}


def evaluate(R, mats, closes, grid, horizon, membership):
    """Mean rank-IC (+HAC t/p, split-half) and quintile L/S (Sharpe/DSR) per signal."""
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    out = {}
    n_trials = len(mats)
    for name, sig in mats.items():
        ics = []
        for d in grid:
            if d not in fwd.index or d not in sig.index:
                continue
            fr = fwd.loc[d].dropna()
            if membership is not None:
                fr = fr[fr.index.isin(_eligible(membership, d))]
            s = sig.loc[d].dropna()
            common = s.index.intersection(fr.index)
            if len(common) < 15:
                continue
            ics.append(rank_ic(s[common], fr[common]))
        ser = pd.Series(ics).dropna()
        summ = ic_summary(ser, periods_per_year=12)
        summ.update(_split_half(ser))
        ls = quintile_ls(R, sig, grid, horizon, n_trials=n_trials, membership=membership)
        out[name] = {"ic": summ, "ls": ls}
    # BH-FDR across the leg family at this horizon
    pvals = {k: v["ic"]["p_hac"] for k, v in out.items()
             if v["ic"].get("p_hac") is not None and v["ic"].get("n", 0) >= 6}
    for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
        out[k]["ic"]["q_fdr"] = q["q"]
        out[k]["ic"]["survives_fdr"] = q["reject"]
    return out


ORDER = ["alpha", "conviction", "alpha_led", "conviction_rev", "streversal",
         "value", "quality", "profitability", "low_vol", "insider"]
LBL = {"alpha": "alpha (BASELINE — today's rank)", "conviction": "conviction composite",
       "alpha_led": "alpha-led composite (0.6α+0.4)", "conviction_rev": "conviction + reversal tilt",
       "streversal": "short reversal (entry leg)", "value": "value", "quality": "quality",
       "profitability": "profitability", "low_vol": "low-vol", "insider": "insider net/mcap"}


def render(results, span, n_reb, n_uni) -> str:
    L = ["# Top-Picks composite — Phase 0 validation\n",
         f"*Survivorship-clean deep S&P panel · PIT S&P 1500 membership · {span} · "
         f"{n_reb} monthly rebalances · ~{n_uni} names/date · residual windows "
         f"{WIN}/{FORM}/{SKIP} shrink {SHRINK} · insider {INSIDER_WINDOW_M}mo filings · "
         f"L/S net of {COST_BPS:.0f}bps one-way.*\n",
         "Does a holistic multi-factor **conviction** composite rank forward returns better "
         "than the residual-momentum `alpha` leg the board ranks by today? And does folding a "
         "mean-reversion/entry tilt INTO the rank help (China) or hurt (US momentum continues)? "
         "Legs are sector-neutral winsor-z; composites are z-means of those legs.\n"]
    for h, res in results.items():
        L.append(f"\n## Forward horizon: {h} trading days\n")
        L.append("| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |")
        L.append("|---|--:|--:|--:|--:|--:|--:|--:|---|")
        for k in ORDER:
            if k not in res:
                continue
            ic, ls = res[k]["ic"], res[k]["ls"]
            n = ic.get("n", 0)
            h12 = (f"{ic.get('ic_h1')}→{ic.get('ic_h2')}" if ic.get("ic_h1") is not None else "—")
            if n >= 6:
                L.append(f"| {LBL[k]} | {ic.get('mean_ic', float('nan')):+.4f} | "
                         f"{ic.get('ic_ir', float('nan')):+.2f} | {ic.get('t_hac', float('nan')):+.2f} | "
                         f"{ic.get('p_hac', float('nan')):.3f} | {ic.get('q_fdr', '—')} | {h12} | "
                         f"{ls.get('sharpe')} | {ls.get('verdict', '—')} |")
            else:
                L.append(f"| {LBL[k]} | n/a | | | | | | {ls.get('sharpe')} | {ls.get('verdict', '—')} |")
    # verdict on the primary horizon (first)
    h0 = next(iter(results))
    r = results[h0]
    a_ic = r["alpha"]["ic"].get("mean_ic", 0) or 0
    a_sh = r["alpha"]["ls"].get("sharpe") or 0
    L.append(f"\n## Verdict (primary horizon {h0}d)\n")
    L.append(f"Baseline `alpha`: mean IC {a_ic:+.4f}, L/S Sharpe {a_sh}.\n")
    best = None
    for k in ("conviction", "alpha_led"):
        c_ic = r[k]["ic"].get("mean_ic", 0) or 0
        c_sh = r[k]["ls"].get("sharpe") or 0
        ic_win, sh_win = c_ic > a_ic, c_sh > a_sh
        verdict = ("BEATS on both" if ic_win and sh_win else
                   "beats on one axis" if ic_win or sh_win else "no improvement")
        L.append(f"- **{LBL[k]}**: IC {c_ic:+.4f} ({'+' if ic_win else '−'} vs alpha), "
                 f"Sharpe {c_sh} ({'+' if sh_win else '−'} vs alpha) → **{verdict}**")
        if ic_win and sh_win and best is None:
            best = k
    rev_ic = r["conviction_rev"]["ic"].get("mean_ic", 0) or 0
    conv_ic = r["conviction"]["ic"].get("mean_ic", 0) or 0
    L.append(f"- *Reversal tilt diagnostic:* conviction+reversal IC {rev_ic:+.4f} vs conviction "
             f"{conv_ic:+.4f} → folding US reversal into the rank "
             f"{'HELPS' if rev_ic > conv_ic else 'HURTS/neutral (US leaders continue — entry belongs on a separate axis)'}.")
    if best:
        L.append(f"\n**GO — rank Top Picks by the {LBL[best]}**: it beats alpha-alone on both the "
                 "cross-sectional IC and the long/short Sharpe, so the holistic blend is a measured "
                 "upgrade, not cosmetic. Entry-timing still rides a separate axis (the reversal tilt "
                 "does not belong in the US rank).")
    else:
        L.append("\n**NEUTRAL — keep the alpha rank, add the legs as conviction CONTEXT.** No "
                 "composite beats alpha-alone on both axes here, so don't claim a blend edge that "
                 "isn't there. The honest upgrade is: rank by the validated alpha, surface the other "
                 "legs as a per-name conviction read, and put entry-timing (pullback/extended) on a "
                 "SEPARATE axis — the US analog of China's folded reversal, since US leaders continue.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=12,
                    help="restrict the rebalance grid to the last N years")
    ap.add_argument("--horizons", type=str, default="21,63,126",
                    help="comma-separated forward-return horizons (trading days)")
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

    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s and s != "—" else "Other") for t, s in tkr_sector.items()}
    spy = _yahoo_ret("SPY", closes.index)

    R = closes.pct_change(fill_method=None)
    grid = month_grid(R.index, warmup=WIN + SKIP + FORM, horizon=max(horizons))
    if args.years:
        cutoff = R.index.max() - pd.DateOffset(years=args.years)
        grid = [d for d in grid if d >= cutoff]
    if len(grid) < 12:
        print(f"grid too short ({len(grid)})")
        return 1
    eligible_by_date = {d: [t for t in _eligible(membership, d) if t in closes.columns]
                        for d in grid}
    log.info("grid: %d monthly rebalances %s..%s · ~%d names/date",
             len(grid), grid[0].date(), grid[-1].date(),
             int(np.median([len(v) for v in eligible_by_date.values()])))

    fund_panel = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    fund_cache = pit_fund_panels(grid, closes, fund_panel)
    R2, mats = build_panels(closes, spy, tkr_sector, grid, fund_cache, insider_panel)
    results = {h: evaluate(R2, mats, closes, grid, h, membership) for h in horizons}

    span = f"{grid[0].date()}..{grid[-1].date()}"
    n_uni = int(np.median([len(v) for v in eligible_by_date.values()]))
    report = render(results, span, len(grid), n_uni)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "top-picks-phase0.md"
    out.write_text(report)
    print("\n" + report)
    print(f"[report] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
