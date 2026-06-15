"""Setup-score — Phase 0 honest validation (research/US_STANDOUT_SETUP_SCORE.md §6).

The "Top setups" board ranks by the setup score (engine/setups.py):

    setup = 0.7·alpha_z  +  urgency_tilt + eq_dir_tilt + entry_tilt
            └ selection ┘     └────────── timing ──────────────┘

It claims a *confluence re-rank* of an already-validated alpha cross-section — NOT a
new edge. This harness measures whether that re-rank actually helps forward returns,
or is cosmetic, by comparing four cross-sectional signals point-in-time:

    alpha       sector-neutral residual-IR z          the validated context leg = BASELINE
    alpha+rev   alpha + mean-reversion entry overlay  (pullback/extended from rev pctile)
    timing      cycle urgency + eq_dir + entry only   (no alpha — does timing predict alone?)
    setup       the shipped setup score (all legs)    0.7·alpha + timing

Point-in-time + survivorship-clean: the deep S&P-500 panel with PIT membership and
folded-in delisted names (the same machinery validated in residual-alpha Phase 0),
production residual-alpha windows (252/252/21, shrink 0.66), monthly rebalance. The
cycle leg (engine.cycles.analyze, causal close[:d]) is the expensive part and is
CACHED to a parquet keyed by (date, ticker) — cycle state is horizon-independent, so
one cache serves every horizon and re-run.

Verdict gate: to justify the re-rank, `setup` must beat `alpha` on BOTH mean rank-IC
AND quintile long/short Sharpe. If it doesn't, the honest call is to downgrade the UI
framing from "ranked by setup conviction" to "an ordering aid, not a measured
improvement" — and the cards/board still stand on the (separately validated) alpha and
cycle legs.
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

from engine.cycles import analyze  # noqa: E402
from engine.equity_factors import _names_sectors, _winsor_z  # noqa: E402
from engine.residual_alpha import _entry  # noqa: E402
from engine.setups import US_ALPHA_WEIGHT, timing_tilt  # noqa: E402
from engine.validation import ic_summary, rank_ic  # noqa: E402
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, _yahoo_ret, build_residuals,
    ew_peer, month_grid, quintile_ls)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("setup_phase0")

# production residual-alpha windows (engine.residual_alpha._defaults) — validate the
# SHIPPED signal, not a re-tuned one
WIN, FORM, SKIP, SHRINK, CAP = 252, 252, 21, 0.66, 3.0
MIN_HISTORY = 300                       # engine.cycles.analyze needs ~this many bars


def _cycle_cache_path() -> Path:
    return config.data_dir() / "regime" / "setup_phase0_cycle_cache.parquet"


def cycle_states(closes: pd.DataFrame, grid: list, eligible_by_date: dict) -> dict:
    """{(date_str, ticker): (urgency, eq_dir)} from a causal analyze(close[:d]).
    Cached to parquet — cycle state is horizon-independent, so one sweep serves every
    horizon/re-run. Only (date,ticker) pairs not already cached are computed."""
    cache: dict[tuple[str, str], tuple] = {}
    cp = _cycle_cache_path()
    if cp.exists():
        try:
            df = pd.read_parquet(cp)
            for r in df.itertuples(index=False):
                cache[(r.date, r.ticker)] = (r.urgency or None, r.eq_dir or None)
            log.info("cycle cache: %d states loaded", len(cache))
        except Exception as e:  # noqa: BLE001
            log.warning("cycle cache unreadable (%s) — recomputing", e)
    todo = [(d, t) for d in grid for t in eligible_by_date[d]
            if (str(d.date()), t) not in cache]
    log.info("cycle states: %d cached, %d to compute (~%.0f min)",
             len(cache), len(todo), len(todo) * 0.027 / 60)
    done = 0
    for d, t in todo:
        key = (str(d.date()), t)
        try:
            s = closes[t].loc[:d].dropna()
            if len(s) < MIN_HISTORY:
                cache[key] = (None, None)
            else:
                lad = (analyze(s) or {}).get("ladder") or {}
                cache[key] = ((lad.get("entry") or {}).get("urgency"), lad.get("eq_dir"))
        except Exception:  # noqa: BLE001 — one bad ticker must not kill the sweep
            cache[key] = (None, None)
        done += 1
        if done % 5000 == 0:
            log.info("  cycle states: %d/%d", done, len(todo))
    # persist (atomic-ish): full rewrite of the merged cache
    rows = [{"date": k[0], "ticker": k[1], "urgency": v[0], "eq_dir": v[1]}
            for k, v in cache.items()]
    try:
        cp.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(cp, index=False)
    except Exception as e:  # noqa: BLE001
        log.warning("cycle cache write failed (%s)", e)
    return cache


def build_signal_panels(closes, market, tkr_sector, grid, cache):
    """Per-grid-date cross-sections for each signal → date×ticker matrices
    (alpha, alpha+rev, timing, setup), all on the SAME eligible set per date."""
    R, eps = build_residuals(closes, market, tkr_sector, ew_peer,
                             WIN, max(WIN // 2, 40), SHRINK)
    ir = (eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).mean()
          / eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).std())
    rev = R.rolling(SKIP, min_periods=max(SKIP // 2, 5)).sum()
    sec = pd.Series(tkr_sector)

    panels = {k: {} for k in ("alpha", "alpha_rev", "timing", "setup")}
    for d in grid:
        if d not in ir.index:
            continue
        row = ir.loc[d].dropna()
        if len(row) < 20:
            continue
        s = sec.reindex(row.index)
        # shipped alpha_z: within-sector demean, winsorised z
        az = _winsor_z(row - row.groupby(s).transform("mean"), CAP).dropna()
        if len(az) < 20:
            continue
        revp = rev.loc[d].reindex(az.index).rank(pct=True) * 100.0
        a_only, a_rev, tim, setup = {}, {}, {}, {}
        for t in az.index:
            zt = float(az[t])
            ent = _entry(zt, float(revp[t]) if pd.notna(revp[t]) else None)
            urg, eqd = cache.get((str(d.date()), t), (None, None))
            ttilt = timing_tilt(urg, eqd, ent)              # full timing leg
            etilt = timing_tilt(None, None, ent)            # entry overlay only
            a_only[t] = zt
            a_rev[t] = zt + etilt
            tim[t] = ttilt
            setup[t] = US_ALPHA_WEIGHT * zt + ttilt
        panels["alpha"][d] = pd.Series(a_only)
        panels["alpha_rev"][d] = pd.Series(a_rev)
        panels["timing"][d] = pd.Series(tim)
        panels["setup"][d] = pd.Series(setup)
    cols = R.columns
    mats = {k: pd.DataFrame(v).T.reindex(columns=cols) for k, v in panels.items()}
    return R, mats


def evaluate(R, mats, closes, grid, horizon, membership):
    """Mean rank-IC (+HAC t/p) and quintile L/S (Sharpe/DSR) per signal at one horizon."""
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    out = {}
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
            if len(common) < 10:
                continue
            ics.append(rank_ic(s[common], fr[common]))
        summ = ic_summary(pd.Series(ics).dropna(), periods_per_year=12)
        ls = quintile_ls(R, sig, grid, horizon, n_trials=4, membership=membership)
        out[name] = {"ic": summ, "ls": ls}
    return out


def render(results, span, n_reb, n_uni) -> str:
    L = ["# Setup-score — Phase 0 validation\n",
         f"*Survivorship-clean deep S&P-500 panel · PIT membership · {span} · "
         f"{n_reb} monthly rebalances · ~{n_uni} names/date · residual-alpha windows "
         f"{WIN}/{FORM}/{SKIP} shrink {SHRINK}.*\n",
         "Does the **setup score** (selection × timing) rank forward returns better "
         "than its legs? `alpha` = the validated sector-neutral residual-momentum "
         "context leg (baseline); `setup` adds the cycle-timing + reversal overlay.\n"]
    order = ["alpha", "alpha_rev", "timing", "setup"]
    lbl = {"alpha": "alpha (baseline)", "alpha_rev": "alpha + reversal overlay",
           "timing": "timing only (no alpha)", "setup": "setup (shipped)"}
    for h, res in results.items():
        L.append(f"\n## Forward horizon: {h} trading days\n")
        L.append("| signal | mean IC | IC-IR | HAC t | p | L/S Sharpe | DSR verdict |")
        L.append("|---|--:|--:|--:|--:|--:|---|")
        for k in order:
            ic, ls = res[k]["ic"], res[k]["ls"]
            n = ic.get("n", 0)
            L.append(f"| {lbl[k]} | {ic.get('mean_ic', float('nan')):+.4f} | "
                     f"{ic.get('ic_ir', float('nan')):+.2f} | "
                     f"{ic.get('t_hac', float('nan')):+.2f} | "
                     f"{ic.get('p_hac', float('nan')):.3f} | "
                     f"{ls.get('sharpe')} | {ls.get('verdict', '—')} |" if n >= 6
                     else f"| {lbl[k]} | n/a | | | | {ls.get('sharpe')} | {ls.get('verdict','—')} |")
    # verdict on the primary horizon (first)
    h0 = next(iter(results))
    r = results[h0]
    a_ic = r["alpha"]["ic"].get("mean_ic", 0) or 0
    s_ic = r["setup"]["ic"].get("mean_ic", 0) or 0
    a_sh = r["alpha"]["ls"].get("sharpe") or 0
    s_sh = r["setup"]["ls"].get("sharpe") or 0
    ic_win = s_ic > a_ic
    sh_win = s_sh > a_sh
    L.append(f"\n## Verdict (primary horizon {h0}d)\n")
    L.append(f"- setup mean IC {s_ic:+.4f} vs alpha {a_ic:+.4f} → "
             f"**{'setup wins' if ic_win else 'no IC gain'}**")
    L.append(f"- setup L/S Sharpe {s_sh} vs alpha {a_sh} → "
             f"**{'setup wins' if sh_win else 'no Sharpe gain'}**")
    if ic_win and sh_win:
        L.append("\n**GO — the confluence re-rank is justified**: the timing leg lifts "
                 "both the cross-sectional IC and the long/short Sharpe above the "
                 "alpha-only baseline. The 'ranked by setup conviction' framing is earned.")
    elif ic_win or sh_win:
        L.append("\n**MIXED** — the setup score improves one axis but not the other. "
                 "Keep it as the board's ordering but soften the UI claim; the edge is "
                 "the alpha + cycle legs, the blend is a tie-aware refinement.")
    else:
        L.append("\n**NEUTRAL / cosmetic** — the timing tilt does not lift forward IC or "
                 "Sharpe over alpha alone. HONEST CALL: downgrade the UI from 'ranked by "
                 "setup conviction' to 'an ordering aid', and lean on the separately "
                 "validated alpha (context) and cycle (calibrated timing) legs. No edge "
                 "is claimed that isn't there.")
    # is the timing leg informative at all?
    t_ic = r["timing"]["ic"].get("mean_ic", 0) or 0
    L.append(f"\n- *Diagnostic:* timing-only mean IC {t_ic:+.4f} "
             f"({'positive — cycle timing carries some forward signal' if t_ic > 0 else 'flat/negative — cycle timing is risk-placement, not return-prediction (matches its calibration)'}).")
    ar_ic = r["alpha_rev"]["ic"].get("mean_ic", 0) or 0
    L.append(f"- *Diagnostic:* alpha+reversal mean IC {ar_ic:+.4f} vs alpha {a_ic:+.4f} "
             f"({'reversal overlay helps' if ar_ic > a_ic else 'reversal overlay neutral/hurts at this horizon'}).")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10,
                    help="restrict the rebalance grid to the last N years (cycle-compute budget)")
    ap.add_argument("--horizons", type=str, default="21,63",
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
    delp = config.data_dir() / "breadth" / "_closes_delisted.parquet"
    if delp.exists():
        closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
        closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s != "—" else "Other") for t, s in tkr_sector.items()}
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

    cache = cycle_states(closes, grid, eligible_by_date)
    R2, mats = build_signal_panels(closes, spy, tkr_sector, grid, cache)
    results = {h: evaluate(R2, mats, closes, grid, h, membership) for h in horizons}

    span = f"{grid[0].date()}..{grid[-1].date()}"
    n_uni = int(np.median([len(v) for v in eligible_by_date.values()]))
    report = render(results, span, len(grid), n_uni)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "setup-score-phase0.md"
    out.write_text(report)
    print("\n" + report)
    print(f"[report] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
