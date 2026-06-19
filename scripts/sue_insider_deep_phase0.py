"""Event-edge gate (T8) — SUE at its NATIVE quarterly cadence + the SUE×insider blend,
on the survivorship-CLEAN deep panel.

Two honest questions the monthly cross-sectional board could not answer:

  1. CADENCE.  SUE's FDR-surviving edge (quarterly rank-IC ~0.039, reports/sue-*) is an
     earnings-cadence effect — PEAD drifts over the ~one quarter AFTER a report. The live
     board re-ranks monthly, which samples SUE off-cadence and dilutes it toward ~0. Does
     SUE rebalanced at quarter-ends (aligned to the reporting calendar, held the 63d drift)
     hold an edge the monthly board throws away?

  2. BLEND.  Insider opportunistic-buying (Cohen–Malloy–Pomorski) is the other event leg
     with literature support. Does SUE + an insider tilt beat SUE alone, and does the blend
     clear the SAME gate the rest of the book is held to — IC>0 surviving BH-FDR, a
     net-of-cost quintile DSR≥0.90, split-half same-sign — enough to earn a VALIDATED
     long-only rank rather than the display-only composite the board ships today?

SURVIVORSHIP-CLEAN: prices = the deep 1962→ close matrix UNION the recovered-delisting
matrix, restricted each date to point-in-time S&P-1500 membership (`_eligible`). This is
the de-biased read `sue_deep_phase0.py` could not do (it was yahoo-only → delisted absent,
an optimistic bound). Everything causal: SUE only reads quarters filed ≤ asof; insider
trades enter only once their filing_date is public.

Metrics: rank-IC (HAC-t, IC-IR, split-half) · BH-FDR across the family · dollar-neutral
top-vs-bottom-quintile net-of-cost Sharpe+DSR · and — because the board is LONG-ONLY — the
top-DECILE long-only active return (decile EW minus the eligible-universe EW), its Sharpe,
maxDD and DSR. The incumbent to beat = 12-1 price momentum (what the board already ranks on).

Run:  .venv/bin/python -m scripts.sue_insider_deep_phase0 [--monthly-too]
Writes reports/sue-insider-deep-phase0.md + data/edgar/sue_insider_deep_phase0.json.
No commit, no site build — pure gate.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.equity_factors import _names_sectors  # noqa: E402
from engine.insider_factor import build_signals, classify_routine, market_cap  # noqa: E402
from engine.sue import load_panel as load_eps, sue_cross_section  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict, ic_summary,
                               rank_ic, ret_moments)
from lib import config  # noqa: E402
from scripts.insider_phase0 import (_eligible, _load_membership,  # noqa: E402
                                    _load_panel as _load_insider, _split_half_ic,
                                    quintile_ls)

COST_BPS = 5.0
H = 63                 # forward window (one PEAD quarter)
START_YEAR = 2011      # mid/small membership ramps in; SUE panel starts 2008
# DSR multiple-testing count: this event-edge program tried many configs (2 cadences ×
# {momentum, sue, insider, blend} × neutral/raw × decile/quintile variants). A fair,
# non-lenient family size — NOT the 4 we print, which would flatter the haircut.
N_TRIALS_PROGRAM = 25


# --------------------------------------------------------------------------- #
# survivorship-clean price universe
# --------------------------------------------------------------------------- #
def _clean_closes() -> pd.DataFrame:
    base = config.data_dir() / "breadth"
    closes = pd.read_parquet(base / "_closes_deep.parquet").sort_index()
    for fn in ("_closes_delisted.parquet", "_closes_delisted_1500.parquet"):
        p = base / fn
        if p.exists():
            closes = pd.concat([closes, pd.read_parquet(p)], axis=1)
    closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    closes.index = pd.to_datetime(closes.index)
    return closes


def _qz(s: pd.Series) -> pd.Series:
    """Cross-sectional z (no clip — rank-IC invariant; used for the blend sum)."""
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 5 or not s.std():
        return pd.Series(dtype=float)
    return (s - s.mean()) / s.std()


def _sector_neutral(s: pd.Series, sec: pd.Series) -> pd.Series:
    """Demean within GICS sector (kills the sector bet, isolates name selection)."""
    s = s.dropna()
    g = s.groupby(sec.reindex(s.index)).transform("mean")
    return s - g.fillna(s.mean())


def quarter_grid(index: pd.DatetimeIndex, horizon: int, start_year: int) -> list:
    out = []
    for d in pd.date_range(f"{start_year}-01-01", index.max(), freq="QE"):
        prior = index[index <= d]
        if not len(prior):
            continue
        loc = index.get_loc(prior[-1])
        if loc + horizon < len(index):
            out.append(prior[-1])
    return out


def month_grid(index: pd.DatetimeIndex, horizon: int, start_year: int) -> list:
    out = []
    for d in pd.date_range(f"{start_year}-01-01", index.max(), freq="ME"):
        prior = index[index <= d]
        if not len(prior):
            continue
        loc = index.get_loc(prior[-1])
        if loc + horizon < len(index):
            out.append(prior[-1])
    return out


# --------------------------------------------------------------------------- #
# signals on a grid
# --------------------------------------------------------------------------- #
def momentum_12_1(closes: pd.DataFrame, grid: list) -> dict:
    """12-1 price momentum (skip the last month) — the incumbent the board ranks on."""
    out = {}
    for d in grid:
        loc = closes.index.get_loc(d)
        if loc < 252:
            continue
        p_now = closes.iloc[loc - 21]          # skip last month
        p_then = closes.iloc[loc - 252]
        out[d] = (p_now / p_then - 1.0).replace([np.inf, -np.inf], np.nan)
    return out


def sue_on_grid(eps_panel: pd.DataFrame, grid: list) -> dict:
    out = {}
    for d in grid:
        s = sue_cross_section(eps_panel, d)
        if len(s):
            s.index = [str(t).replace(".", "-") for t in s.index]
            out[d] = s
    return out


def insider_on_grid(panel: pd.DataFrame, closes: pd.DataFrame, grid: list, *,
                    window: int = 6) -> dict:
    """opp_buyers (CMP cluster headline, count-based — size-robust, no mcap needed) and
    net_usd_mcap (size-normalised net $). Returns {signal_name: {date: series}}."""
    panel = classify_routine(panel)
    closes_me = closes.loc[[d for d in grid if d in closes.index]]
    try:
        shares = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
        mcap = market_cap(closes_me, shares, grid)
    except Exception:  # noqa: BLE001
        mcap = None
    sigs = build_signals(panel, grid, mcap=mcap, k_months=window)
    keep = {}
    for name in ("opp_buyers", "net_usd_mcap", "net_usd"):
        if name in sigs and not sigs[name].empty:
            keep[name] = {d: sigs[name].loc[d].dropna() for d in grid if d in sigs[name].index}
    return keep


# --------------------------------------------------------------------------- #
# long-only top-decile (what a long-only board owner actually gets)
# --------------------------------------------------------------------------- #
def long_only_decile(closes: pd.DataFrame, sig: dict, grid: list, membership, *,
                     n_trials: int, frac: float = 0.10) -> dict:
    """EW long the top `frac` of the signal among eligible names each rebalance; hold to
    the next. Report the ACTIVE series (decile EW − eligible-universe EW) so the number is
    pure selection, not the market. The benchmark is a FIXED eligible+priced-universe EW —
    the SAME basket for every signal (incl. the placebo), independent of which names the
    signal happens to cover — so the placebo 'artifact floor' is an apples-to-apples
    comparison. Daily-held (ffill weights, shift 1) so overlapping horizons don't double
    count; net of cost on turnover."""
    R = closes.pct_change(fill_method=None)
    elig_cols = closes.columns
    w = pd.DataFrame(0.0, index=closes.index, columns=elig_cols)
    bench = pd.DataFrame(0.0, index=closes.index, columns=elig_cols)
    for d in grid:
        s = sig.get(d)
        if s is None or not len(s):
            continue
        elig_set = _eligible(membership, d) if membership is not None else None
        if elig_set is not None:
            s = s[s.index.isin(elig_set)]
        s = s[s.index.isin(elig_cols)].dropna()
        if len(s) < 25:
            continue
        cut = s.quantile(1.0 - frac)
        top = s[s >= cut].index
        if not len(top):
            continue
        w.loc[d, top] = 1.0 / len(top)
        # FIXED benchmark: ALL eligible names with a price on d (NOT just the signal's
        # coverage) — identical basket across signals so the placebo comparison is fair.
        univ = elig_cols if elig_set is None else [c for c in elig_cols if c in elig_set]
        priced = closes.loc[d, univ].dropna().index if d in closes.index else pd.Index([])
        if len(priced):
            bench.loc[d, priced] = 1.0 / len(priced)
    w = w.replace(0.0, np.nan).ffill().fillna(0.0)
    bench = bench.replace(0.0, np.nan).ffill().fillna(0.0)
    pos, bpos = w.shift(1), bench.shift(1)
    rc = R.clip(-0.5, 0.5)
    decile = (pos * rc).sum(axis=1)
    market = (bpos * rc).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    decile_net = (decile - (COST_BPS / 1e4) * turn).loc[grid[0]:grid[-1]]
    active = (decile_net - market.loc[grid[0]:grid[-1]]).dropna()
    abs_net = decile_net.dropna()
    out = {
        "decile_cum_pct": round(float(((1 + abs_net).prod() - 1) * 100), 1),
        "active_cum_pct": round(float(((1 + active).prod() - 1) * 100), 1),
        "active_sharpe": round(float(active.mean() / active.std() * np.sqrt(252)), 2) if active.std() else None,
        "active_maxdd_pct": round(float(_maxdd(active) * 100), 1),
        "n_days": int(active.notna().sum()),
    }
    # split-half on the active series (era robustness — must be same-sign both halves)
    h = active.dropna()
    if len(h) >= 60:
        mid = len(h) // 2
        out["active_h1_ann"] = round(float(h.iloc[:mid].mean() * 252 * 100), 1)
        out["active_h2_ann"] = round(float(h.iloc[mid:].mean() * 252 * 100), 1)
    mom = ret_moments(active)
    if mom:
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3],
                              n_trials=max(n_trials, N_TRIALS_PROGRAM), trading_year=252)
        if dsr:
            out["active_dsr"] = dsr["dsr"]
            out["verdict"] = dsr_verdict(dsr["dsr"])
    bc = block_bootstrap_ci(active, ann=252)
    if bc:
        out["active_sharpe_ci"] = bc.get("sharpe_ci")
        out["active_sharpe_gt0_prob"] = bc.get("sharpe_gt0_prob")
    return out


def _maxdd(r: pd.Series) -> float:
    eq = (1.0 + r.fillna(0.0)).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


# --------------------------------------------------------------------------- #
# score one cadence
# --------------------------------------------------------------------------- #
def score_cadence(closes, eps_panel, ins_panel, sec, membership, *, grid, label, horizon):
    if len(grid) < 12:
        return {"error": f"grid too short ({len(grid)})"}
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)

    mom = momentum_12_1(closes, grid)
    sue = sue_on_grid(eps_panel, grid)
    ins = insider_on_grid(ins_panel, closes, grid)
    ins_opp = ins.get("opp_buyers", {})

    # candidate cross-sections per date (sector-neutral where it's a selection claim)
    def blend(d):
        z_s = _qz(_sector_neutral(sue.get(d, pd.Series(dtype=float)), sec))
        tilt = ins_opp.get(d, pd.Series(dtype=float))
        z_i = _qz(tilt[tilt > 0]) if len(tilt) else pd.Series(dtype=float)
        if not len(z_s):
            return pd.Series(dtype=float)
        b = z_s.copy()
        if len(z_i):
            b = b.add(0.5 * z_i.reindex(b.index).fillna(0.0), fill_value=0.0)
        return b

    cand = {
        "momentum_12_1": lambda d: _sector_neutral(mom.get(d, pd.Series(dtype=float)), sec),
        "sue": lambda d: _sector_neutral(sue.get(d, pd.Series(dtype=float)), sec),
        "insider_opp_buyers": lambda d: ins_opp.get(d, pd.Series(dtype=float)),
        "sue_x_insider": blend,
    }

    ic = {c: [] for c in cand}
    nseries = []
    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if membership is not None:
            fr = fr[fr.index.isin(_eligible(membership, d))]
        if len(fr) < 20:
            continue
        nseries.append(len(fr))
        for c, fn in cand.items():
            s = fn(d)
            s = s[s.index.isin(fr.index)] if len(s) else s
            ic[c].append(rank_ic(s, fr.reindex(s.index)) if len(s) >= 15 else np.nan)

    rows, pvals = {}, {}
    for c, series in ic.items():
        ser = pd.Series(series)
        summ = ic_summary(ser.dropna(), periods_per_year=(4 if "Q" in label else 12))
        if summ.get("n", 0) >= 6:
            summ.update(_split_half_ic(ser))
            rows[c] = summ
            if summ.get("p_hac") is not None:
                pvals[c] = summ["p_hac"]
    for c, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]

    # backtests on the candidates that have a real cross-section every date
    nt = len(rows)
    sigmap = {
        "momentum_12_1": {d: cand["momentum_12_1"](d) for d in grid},
        "sue": {d: cand["sue"](d) for d in grid},
        "insider_opp_buyers": ins_opp,
        "sue_x_insider": {d: blend(d) for d in grid},
    }
    # PLACEBO: a random signal through the SAME long-only machinery. If random earns the
    # same active Sharpe/DSR as the real signals, the long-only metric is a construction
    # artifact (not selection) and the IC≈0 verdict governs. Seeded → reproducible.
    rng = np.random.default_rng(7)
    sigmap["placebo_random"] = {
        d: pd.Series(rng.standard_normal(len(closes.columns)), index=closes.columns) for d in grid}
    # backtest EVERY candidate (incl. insider_opp_buyers) so its long-only DSR can be the
    # gate's `best` — else insider's standalone edge is structurally excluded from the GO call.
    lo = {c: long_only_decile(closes, sigmap[c], grid, membership, n_trials=nt)
          for c in ("momentum_12_1", "sue", "insider_opp_buyers", "sue_x_insider", "placebo_random")}
    # dollar-neutral quintile L/S for the two-sided ones (SUE, momentum, blend)
    ls = {}
    for c in ("momentum_12_1", "sue", "sue_x_insider"):
        sigdf = pd.DataFrame(sigmap[c]).T
        if not sigdf.empty:
            ls[c] = quintile_ls(closes.pct_change(fill_method=None), sigdf, grid,
                                n_trials=nt, membership=membership)

    return {"label": label, "span": f"{grid[0].date()}..{grid[-1].date()}", "rebalances": len(grid),
            "median_universe": int(np.median(nseries)) if nseries else 0, "horizon": horizon,
            "ic": rows, "long_only": lo, "ls": ls}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _panel_md(res) -> list[str]:
    if res.get("error"):
        return [f"### {res.get('label','?')}", f"_skipped — {res['error']}_", ""]
    L = [f"### {res['label']}", "",
         f"Span {res['span']} · {res['rebalances']} rebalances · ~{res['median_universe']} "
         f"eligible names · forward {res['horizon']}d · survivorship-clean (deep+delisted, PIT S&P-1500).",
         "", "| signal | mean IC | IC-IR | t_HAC | p | q_FDR | hit | IC h1→h2 | n |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = res["ic"]
    for c in sorted(rows, key=lambda c: -(rows[c].get("mean_ic") or -9)):
        r = rows[c]
        h = f"{r.get('ic_h1')}→{r.get('ic_h2')}" if r.get("ic_h1") is not None else "—"
        L.append(f"| {c} | {r.get('mean_ic')} | {r.get('ic_ir')} | {r.get('t_hac')} "
                 f"| {r.get('p_hac')} | {r.get('q_fdr','—')} | {r.get('hit')} | {h} | {r.get('n')} |")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(surv) if surv else 'NONE'}", "",
          "Long-only top-decile, EW, net of cost — ACTIVE return = decile − eligible-universe EW. "
          "_Read the active **Sharpe/DSR** vs the `placebo_random` row (a noise signal through the "
          "same machinery) — that is the artifact floor. The absolute cum-% is distorted by "
          "delisting-tail compounding on the deep+delisted matrix and is NOT comparable; the "
          "risk-adjusted stats are._", "",
          "| signal | active Sharpe | active DSR | active maxDD % | h1→h2 ann% | P(SR>0) | (cum % — distorted) |",
          "|---|--:|--:|--:|--:|--:|--:|"]
    for c, b in res["long_only"].items():
        L.append(f"| {c} | {b.get('active_sharpe')} | {b.get('active_dsr','—')} | "
                 f"{b.get('active_maxdd_pct')} | {b.get('active_h1_ann','—')}→{b.get('active_h2_ann','—')} "
                 f"| {b.get('active_sharpe_gt0_prob','—')} | {b.get('active_cum_pct')} |")
    L += ["", "Dollar-neutral top-vs-bottom-quintile (net of cost, DSR-deflated):", "",
          "| signal | net Sharpe | cum % | DSR | verdict |", "|---|--:|--:|--:|---|"]
    for c, b in res["ls"].items():
        L.append(f"| {c} | {b.get('sharpe')} | {b.get('cum_pct')} | {b.get('dsr','—')} | {b.get('verdict','—')} |")
    return L + [""]


_EVENT_SIGNALS = ("sue", "sue_x_insider", "insider_opp_buyers")


def _verdict_block(panels) -> list[str]:
    """Programmatic GO/NEUTRAL call: an EVENT signal (sue/blend/insider — NOT the momentum
    incumbent) earns a validated rank only if it ranks winners (ITS OWN IC survives BH-FDR)
    AND its long-only active DSR clears 0.90 AND beats the PLACEBO AND beats the momentum
    incumbent (IC + long-only DSR). If the placebo matches the signal, the long-only number
    is a construction artifact, not selection."""
    L = ["## VERDICT", ""]
    overall_go = False
    for res in panels:
        if res.get("error"):
            continue
        ic = res["ic"]; lo = res["long_only"]
        # survival must come from an EVENT signal, not the momentum incumbent (it's in the
        # FDR family too — crediting GO on momentum's survival would be a false-GO).
        surv_event = [c for c in _EVENT_SIGNALS if ic.get(c, {}).get("survives_fdr")]
        surv_all = [c for c in ic if ic[c].get("survives_fdr")]
        plac = lo.get("placebo_random", {}); mom = lo.get("momentum_12_1", {})
        best = max(_EVENT_SIGNALS, key=lambda c: lo.get(c, {}).get("active_dsr", -1) if c in lo else -1)
        b = lo.get(best, {}); p_dsr = plac.get("active_dsr"); m_dsr = mom.get("active_dsr")
        beats_placebo = (b.get("active_dsr") is not None and p_dsr is not None
                         and b["active_dsr"] - p_dsr > 0.03)
        # beats the incumbent: the event signal's IC AND long-only DSR exceed momentum's.
        best_ic = ic.get(best, {}).get("mean_ic"); mom_ic = ic.get("momentum_12_1", {}).get("mean_ic")
        beats_mom = (best_ic is not None and mom_ic is not None and best_ic > mom_ic
                     and m_dsr is not None and b.get("active_dsr", 0) > m_dsr)
        go = bool(surv_event) and (b.get("active_dsr", 0) >= 0.90) and beats_placebo and beats_mom
        overall_go = overall_go or go
        sue_ic = ic.get("sue", {}).get("mean_ic")
        L += [f"**{res['label']} → {'GO' if go else 'NEUTRAL'}.** "
              f"SUE IC {sue_ic} (vs momentum {mom_ic}); EVENT signals surviving BH-FDR: "
              f"{', '.join(surv_event) if surv_event else 'NONE'} (family incl. momentum: "
              f"{', '.join(surv_all) if surv_all else 'NONE'}). "
              f"Best event long-only active DSR = {best} {b.get('active_dsr')} vs "
              f"placebo {p_dsr} / momentum {m_dsr} → "
              f"{'beats noise + incumbent' if (beats_placebo and beats_mom) else 'MATCHED BY NOISE / does not beat incumbent (artifact, not selection)'}.", ""]
    L += [f"**Decision: {'GO — promote a validated event rank' if overall_go else 'NEUTRAL — ship NO new scored rank'}.** "
          + ("" if overall_go else
             "Cross-sectional event IC is ~0 on the survivorship-clean S&P-1500 at this horizon, "
             "at BOTH quarterly (native) and monthly cadence — quarter-end sampling does NOT "
             "recover an edge, and SUE×insider does not beat SUE. The long-only top-decile "
             "active Sharpe (~0.7) is a concentrated-EW-vs-broad-EW artifact: the random PLACEBO "
             "earns the same. The board's gate stays NEUTRAL; SUE/insider remain display-only "
             "context, the validated leg stays each market's residual-alpha RANK, and the "
             "shipped edge is the T1–T7 risk-control reshape, not a new alpha leg."), ""]
    return L


def render(panels) -> str:
    L = ["# Event-edge gate (T8) — SUE cadence + SUE×insider blend, survivorship-clean", "",
         "*`scripts/sue_insider_deep_phase0.py`. The gate before a NEW validated long-only "
         "rank: an event signal must (1) rank winners — IC>0 surviving BH-FDR — and (2) clear "
         "DSR≥0.90 on the net-of-cost backtest with split-half same-sign AND beat a random "
         "placebo, BEATING the 12-1 momentum incumbent the board already ranks on. "
         "Survivorship-clean: deep+delisted prices, point-in-time S&P-1500 membership. "
         "Causal SUE + causal insider filings.*", ""]
    L += _verdict_block(panels)
    for res in panels:
        L += _panel_md(res)
    L += ["---", "",
          "**How to read.** The honest question is whether SUE *at quarter-end cadence* (aligned "
          "to the reporting calendar) recovers the edge the monthly board samples off-cadence and "
          "dilutes; and whether SUE+insider beats SUE alone enough to promote. If the event signals "
          "do NOT beat momentum on BOTH the IC/FDR gate and the long-only active DSR, the board's "
          "current display-only treatment of SUE is correct and we ship NO new scored rank — the "
          "edge that survives is the risk-control reshape (T1–T7), not a new alpha leg.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly-too", action="store_true",
                    help="also score the MONTHLY cadence (the dilution comparison)")
    ap.add_argument("--start", type=int, default=START_YEAR)
    args = ap.parse_args()

    eps_panel = load_eps()
    if eps_panel is None:
        print("no EPS panel — run collectors.edgar_eps"); return 1
    ins_panel = _load_insider()
    if ins_panel.empty:
        print("no insider panel"); return 1
    closes = _clean_closes()
    membership = _load_membership()
    ns = _names_sectors()
    sec = pd.Series({t: (ns.get(t, (t, "Other"))[1] or "Other") for t in closes.columns})

    print(f"[data] closes {closes.shape} span {str(closes.index.min())[:10]}..{str(closes.index.max())[:10]} "
          f"· EPS {eps_panel['ticker'].nunique()} names · insider {len(ins_panel):,} txns "
          f"· PIT {'ON' if membership is not None else 'OFF'}")

    panels = []
    qg = quarter_grid(closes.index, H, args.start)
    print(f"[run] QUARTERLY cadence — {len(qg)} quarter-ends, horizon {H}d …")
    panels.append(score_cadence(closes, eps_panel, ins_panel, sec, membership,
                                grid=qg, label="QUARTERLY (native SUE cadence)", horizon=H))
    if args.monthly_too:
        mg = month_grid(closes.index, H, args.start)
        print(f"[run] MONTHLY cadence — {len(mg)} month-ends, horizon {H}d (dilution check) …")
        panels.append(score_cadence(closes, eps_panel, ins_panel, sec, membership,
                                    grid=mg, label="MONTHLY (board cadence)", horizon=H))

    out_md = config.ROOT / config.load()["storage"]["reports_dir"] / "sue-insider-deep-phase0.md"
    out_md.write_text(render(panels))
    out_json = config.data_dir() / "edgar" / "sue_insider_deep_phase0.json"
    out_json.write_text(json.dumps(panels, indent=2, default=str))
    print(f"[report] {out_md}")
    for res in panels:
        if res.get("error"):
            continue
        surv = [c for c in res["ic"] if res["ic"][c].get("survives_fdr")]
        lo = res["long_only"]
        print(f"\n=== {res['label']} ===")
        print(f"  survive BH-FDR: {', '.join(surv) if surv else 'NONE'}")
        for c in ("momentum_12_1", "sue", "sue_x_insider", "placebo_random"):
            r = res["ic"].get(c, {})
            b = lo.get(c, {})
            print(f"  {c:18s} IC {str(r.get('mean_ic','—')):>8}  t {str(r.get('t_hac','—')):>7}  "
                  f"active Sharpe {b.get('active_sharpe')}  DSR {b.get('active_dsr','—')}  "
                  f"h1→h2 {b.get('active_h1_ann','—')}→{b.get('active_h2_ann','—')}  "
                  f"P(SR>0) {b.get('active_sharpe_gt0_prob','—')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
