"""Unified Conviction Profile — Phase 0 honest gate (research/STOCK_CONVICTION_DESIGN.md).

THE QUESTION the cross-market **Conviction Profile** turns on: does the holistic
multi-AXIS conviction composite rank forward returns BETTER than the validated leg
each board already ranks by — well enough to actually re-order the SHIPPED board?

This is the harder sibling of ``top_picks_phase0`` (which tested a flat factor blend).
Here we assemble the *four conviction axes* the engine displays —

  selection  the market's validated selection leg   = the BASELINE the board ranks by
             (US/CA residual-alpha IR z · CN reversal · HK relative strength)
  entry      cycle / reversal entry proxy            (short-term reversal, sector-neutral)
  tailwind   sector-level tilt                       (NOT tested as a picker — declared)
  quality    orthogonal factor composite + SUE proxy (engine.factor_orthogonal)

— into a Löwdin-orthogonalized composite ACROSS axes, and ask whether that composite
beats the selection baseline on BOTH mean rank-IC AND the quintile L/S Sharpe at a
PRE-REGISTERED primary horizon (63d; 21/126 secondary). The honesty contract:

  * GATE GO  only if the composite beats the baseline on BOTH axes at 63d AND the
             split-half IC is same-sign (no half-sample flip).
  * else     NEUTRAL → display-only.

What the gate currently governs (CONSERVATIVE BY DESIGN): the per-market verdict is
persisted to ``data/regime/stock_conviction_gate.json`` (``{"US":"NEUTRAL", ...}``) and
the build reads it to set the per-name **trust tier / calibration framing** (GO →
``trust_tier`` reads "composite cleared Phase-0", uncalibrated flag clears). The board
**RANK itself always stays the market's validated leg** (US/CA residual alpha, CN
reversal-led setup, HK relative strength) — promoting the SHIPPED sort key to the
composite is a deliberately DEFERRED future step that must be wired explicitly (a guarded
``rank_by='conviction'`` switch) and is intentionally NOT automatic, so a stale or
false-GO artifact can never silently re-order a board. A transient failure leaves the
prior gate file in place (we only overwrite on a clean run).

POWER GUARD. The deep survivorship-clean panel + PIT membership are what make a GO
trustworthy; on the shallow ~3y live cache (no delistings, no PIT membership) the test
is UNDERPOWERED and survivorship-INFLATED. So when the deep data is absent we run a
shallow diagnostic for the report but DEFAULT EVERY MARKET TO NEUTRAL — the build will
never flip a rank on powerless local data. Only a deep+PIT run can earn a GO.

Run:  .venv/bin/python scripts/stock_conviction_phase0.py --years 3
      .venv/bin/python -m scripts.stock_conviction_phase0 --years 12 --horizons 63,21,126
Writes reports/stock-conviction-phase0.md + data/regime/stock_conviction_gate.json.
No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")   # rolling betas on truncated history emit benign warnings

from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from engine.factor_orthogonal import orthogonal_composite, overlap_diagnostics  # noqa: E402
from engine.validation import (benjamini_hochberg, deflated_sharpe,  # noqa: E402
                               dsr_verdict, ic_summary, rank_ic, ret_moments)
from lib import config  # noqa: E402
from scripts.residual_alpha_phase0 import (  # noqa: E402
    _closes_deep, _eligible, _load_membership, _yahoo_ret, build_residuals,
    ew_peer, month_grid)
from scripts.top_picks_phase0 import (  # noqa: E402
    FUND_LEGS, SHRINK, _sn_z, pit_fund_panels)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("stock_conviction_phase0")

# Validate the SHIPPED selection leg (engine.residual_alpha defaults), not a re-tuned one.
WIN, FORM, SKIP = 252, 252, 21
COST_BPS = 5.0                     # single-name one-way, charged on quintile turnover

# pre-registered horizons: 63d is PRIMARY (the conviction display horizon), 21/126 secondary.
PRIMARY_H = 63

# every market the engine profiles; the gate JSON carries one verdict per market.
MARKETS = ("US", "CN", "HK", "CA")

# the axes we assemble + the cross-axis composites we try. n_trials for the DSR is
# composites × horizons (the family we actually screened).
AXES = ["selection", "entry", "tailwind", "quality"]
# v2: the EDGE composite is the validated EVENT core the board actually ranks by when the
# gate is GO. Tested here as the pure sector-neutral SUE leg (the FDR survivor) — a
# CONSERVATIVE lower bound on the live EDGE, which also folds insider + revisions.
COMPOSITES = ["edge", "conviction_orth", "conviction_ew", "selection_led"]


def _fmt(v, spec: str) -> str:
    """Format a possibly-None metric for the report table ('—' when absent). The
    Newey-West t/p are None until n>=8, so a short shallow grid leaves them blank."""
    return format(v, spec) if isinstance(v, (int, float)) else "—"


# --------------------------------------------------------------------------- #
# per-(date,ticker) parquet cache for the quality axis legs (one sweep serves
# every horizon / re-run) — reuses top_picks_phase0's pit_fund_panels cache shape.
# --------------------------------------------------------------------------- #
def _quality_cache_path() -> Path:
    return config.data_dir() / "regime" / "stock_conviction_phase0_quality_cache.parquet"


def _sue_proxy(panel: pd.DataFrame, grid: list) -> dict[str, pd.Series]:
    """A leak-free SUE stand-in: standardized YoY net-income surprise per name, asof
    the latest filing ≤ d. The shipped quality axis folds the validated SUE leg; here
    we proxy it from the PIT fundamentals panel (ni vs ni_prior) so the harness needs
    no separate earnings feed. Cached to a (date,ticker) parquet (horizon-free, one
    sweep serves every re-run). {date_str: Series[ticker -> raw surprise]}."""
    cache: dict[str, pd.Series] = {}
    cp = _quality_cache_path()
    if cp.exists():
        try:
            df = pd.read_parquet(cp)
            for ds, sub in df.groupby("date"):
                cache[ds] = sub.set_index("ticker")["sue"].dropna()
        except Exception as e:  # noqa: BLE001
            log.warning("SUE-proxy cache unreadable (%s) — recomputing", e)
    todo = [d for d in grid if str(d.date()) not in cache]
    p = panel.dropna(subset=["asof_date"]).copy()
    p["asof_date"] = pd.to_datetime(p["asof_date"])
    p = p.sort_values("asof_date")
    for d in todo:
        sub = p[p["asof_date"] <= d]
        if sub.empty:
            continue
        last = sub.groupby("ticker").tail(1).set_index("ticker")
        prior = last["ni_prior"].abs().replace(0, np.nan)
        sue = (last["ni"] - last["ni_prior"]) / prior
        cache[str(d.date())] = sue.dropna()
    try:                                            # persist the merged (date,ticker) cache
        rows = []
        for ds, s in cache.items():
            if s is None or s.empty:
                continue
            r = s.rename("sue").reset_index().rename(columns={"index": "ticker"})
            r.insert(0, "date", ds)
            rows.append(r)
        if rows:
            cp.parent.mkdir(parents=True, exist_ok=True)
            pd.concat(rows, ignore_index=True).to_parquet(cp, index=False)
    except Exception as e:  # noqa: BLE001
        log.warning("SUE-proxy cache write failed (%s)", e)
    return cache


def build_axis_panels(closes, market, tkr_sector, grid, fund_cache, sue_cache):
    """Assemble each conviction AXIS as a sector-neutral winsor-z date×ticker matrix,
    then the cross-axis composites → {signal: date×ticker matrix}.

      selection : residual-momentum IR z (the validated US/CA leg = baseline)
      entry     : short-term reversal proxy (−21d return), sector-neutral
      tailwind  : declared sector-level tilt (sector EW residual) — NOT a picker, but
                  carried so the report shows it adds ~no cross-sectional rank content
      quality   : Löwdin-orthogonal composite of {value,quality,profitability,low_vol}
                  + the SUE proxy (engine.factor_orthogonal across the legs)
    """
    sec = pd.Series(tkr_sector)
    R, eps = build_residuals(closes, market, tkr_sector, ew_peer,
                             WIN, max(WIN // 2, 40), SHRINK)
    ir = (eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).mean()
          / eps.shift(SKIP).rolling(FORM, min_periods=max(FORM // 2, 20)).std())
    rev_raw = R.rolling(SKIP, min_periods=max(SKIP // 2, 5)).sum()        # 21d return; entry = −this
    # sector EW residual tailwind: how the name's sector is doing beyond the market,
    # broadcast to each member (a declared sector tilt, deliberately NOT name-specific).
    sec_tw = pd.DataFrame(index=R.index, columns=R.columns, dtype=float)
    for s in sorted(set(tkr_sector.values())):
        cols = [t for t in R.columns if tkr_sector.get(t) == s]
        if not cols:
            continue
        srs = eps[cols].rolling(FORM, min_periods=max(FORM // 2, 20)).mean().mean(axis=1)
        for c in cols:
            sec_tw[c] = srs

    panels: dict[str, dict] = {k: {} for k in AXES + COMPOSITES}
    for d in grid:
        if d not in ir.index:
            continue
        row = ir.loc[d].dropna()
        if len(row) < 25:
            continue
        sel = _sn_z(row, sec)                                  # selection = sector-neutral IR z
        if len(sel) < 25:
            continue
        idx = sel.index

        entry = _sn_z(-rev_raw.loc[d].reindex(idx), sec)       # reversal entry proxy
        tw = _sn_z(sec_tw.loc[d].reindex(idx), sec) if d in sec_tw.index else pd.Series(dtype=float)

        # --- quality: orthogonal composite over the fundamental legs + SUE proxy ----
        ftbl = fund_cache.get(str(d.date()))
        qlegs = {}
        for leg in FUND_LEGS:
            col = (ftbl[leg] if (ftbl is not None and not ftbl.empty and leg in ftbl.columns)
                   else pd.Series(dtype=float))
            qlegs[leg] = _sn_z(col.reindex(idx), sec)
        sue_d = sue_cache.get(str(d.date()))
        qlegs["sue"] = _sn_z(sue_d.reindex(idx), sec) if sue_d is not None else pd.Series(dtype=float)
        Q = pd.DataFrame({k: v.reindex(idx) for k, v in qlegs.items()})
        # Löwdin-orthogonal equal-RISK blend across the quality legs (decorrelates the
        # value/quality/profit overlap the same way the engine's quality axis intends).
        quality = orthogonal_composite(Q, min_legs=2).reindex(idx)

        # --- assemble the axis frame + the cross-axis composites --------------------
        A = pd.DataFrame({"selection": sel, "entry": entry,
                          "tailwind": tw.reindex(idx), "quality": quality})
        # orthogonal composite ACROSS the four axes (the honest equal-risk roll-up the
        # engine displays); EW mean as a transparent comparison; selection-led as the
        # "tilt the baseline" variant. tailwind is a declared sector tilt — kept OUT of
        # the cross-axis composites (it is not a within-sector picker), shown standalone.
        core = A[["selection", "entry", "quality"]]
        conv_orth = orthogonal_composite(core, min_legs=2).reindex(idx)
        conv_ew = core.mean(axis=1, skipna=True)
        sel_led = 0.6 * A["selection"] + 0.4 * A[["entry", "quality"]].mean(axis=1, skipna=True).fillna(0.0)

        for k in AXES:
            panels[k][d] = A[k].dropna()
        # v2 EDGE = the validated event core (SUE), the leg the board ranks by when GO.
        edge = qlegs.get("sue")
        if edge is not None and not edge.dropna().empty:
            panels["edge"][d] = edge.dropna()
        panels["conviction_orth"][d] = conv_orth.dropna()
        panels["conviction_ew"][d] = conv_ew.dropna()
        panels["selection_led"][d] = sel_led.dropna()

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
    """Mean rank-IC (+HAC t/p, split-half) and quintile L/S (Sharpe/DSR) per signal.
    n_trials for the DSR = the family we screened (composites × horizons)."""
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    out = {}
    n_trials = len(COMPOSITES) * 3                          # composites × the 3 horizons tried
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
    pvals = {k: v["ic"]["p_hac"] for k, v in out.items()
             if v["ic"].get("p_hac") is not None and v["ic"].get("n", 0) >= 6}
    for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
        out[k]["ic"]["q_fdr"] = q["q"]
        out[k]["ic"]["survives_fdr"] = q["reject"]
    return out


# --------------------------------------------------------------------------- #
# the GATE: GO only if a composite beats the selection baseline on BOTH axes at the
# primary horizon AND split-half IC is same-sign.
# --------------------------------------------------------------------------- #
def decide_gate(results: dict, powered: bool) -> tuple[str, str | None, list[str]]:
    """Return (verdict, winning_composite, notes). On unpowered (shallow) runs the
    verdict is forced NEUTRAL regardless of the diagnostic numbers — we never flip a
    rank on survivorship-inflated, underpowered local data."""
    notes: list[str] = []
    if PRIMARY_H not in results:
        return "NEUTRAL", None, [f"primary horizon {PRIMARY_H}d not evaluated"]
    r = results[PRIMARY_H]
    if "selection" not in r:
        return "NEUTRAL", None, ["no selection baseline at primary horizon"]
    base_ic = r["selection"]["ic"].get("mean_ic", 0) or 0
    base_sh = r["selection"]["ls"].get("sharpe") or 0
    best = None
    for k in ("edge", "conviction_orth", "conviction_ew", "selection_led"):
        if k not in r:
            continue
        c_ic = r[k]["ic"].get("mean_ic", 0) or 0
        c_sh = r[k]["ls"].get("sharpe") or 0
        h1, h2 = r[k]["ic"].get("ic_h1"), r[k]["ic"].get("ic_h2")
        same_sign = (h1 is not None and h2 is not None and np.sign(h1) == np.sign(h2) and h1 != 0)
        ic_win, sh_win = c_ic > base_ic, c_sh > base_sh
        if ic_win and sh_win and same_sign:
            notes.append(f"{k}: beats baseline on BOTH axes ({c_ic:+.4f} IC vs {base_ic:+.4f}, "
                         f"Sharpe {c_sh} vs {base_sh}) and split-half same-sign ({h1}→{h2})")
            if best is None:
                best = k
        else:
            why = []
            if not ic_win:
                why.append("IC≤baseline")
            if not sh_win:
                why.append("Sharpe≤baseline")
            if not same_sign:
                why.append("split-half flips/zero")
            notes.append(f"{k}: NO — {', '.join(why)}")
    if not powered:
        notes.insert(0, "UNPOWERED shallow run (no deep panel / no PIT membership) — "
                     "gate FORCED to display-only regardless of the diagnostic above")
        return "NEUTRAL", best, notes
    if best is not None:
        return "GO", best, notes
    return "NEUTRAL", None, notes


ORDER = ["selection", "edge", "conviction_orth", "conviction_ew", "selection_led",
         "entry", "quality", "tailwind"]
LBL = {"selection": "selection (BASELINE — residual momentum, the v1 rank)",
       "edge": "EDGE (v2 — validated event core: SUE; live also folds insider + revisions)",
       "conviction_orth": "conviction composite (orthogonal across axes)",
       "conviction_ew": "conviction composite (equal-weight)",
       "selection_led": "selection-led blend (0.6 sel + 0.4 entry/quality)",
       "entry": "entry axis (reversal proxy)", "quality": "quality axis (orth factors + SUE)",
       "tailwind": "tailwind axis (sector tilt — declared, not a picker)"}


def render(market_results: dict, gates: dict, span: str, n_reb: int, n_uni: int,
           powered: bool, horizons: list) -> str:
    L = ["# Unified Conviction Profile — Phase 0 gate\n",
         f"*{'DEEP survivorship-clean panel + PIT membership' if powered else 'SHALLOW ~3y live cache (NO deep panel, NO PIT membership — UNDERPOWERED, survivorship-inflated)'} · "
         f"{span} · {n_reb} monthly rebalances · ~{n_uni} names/date · residual windows "
         f"{WIN}/{FORM}/{SKIP} shrink {SHRINK} · primary horizon {PRIMARY_H}d · L/S net of "
         f"{COST_BPS:.0f}bps one-way.*\n",
         "Does the holistic four-AXIS **conviction** composite rank forward returns better "
         "than the validated **selection** leg each board ranks by today — well enough to "
         "actually re-order the SHIPPED board? Axes are sector-neutral winsor-z; the composite "
         "is a Löwdin-orthogonal (equal-risk) blend across axes. The tailwind axis is a declared "
         "sector tilt, shown standalone, never folded into the cross-axis rank.\n",
         "**Gate:** a market earns `GO` (board re-ranked by the composite) only if a composite "
         f"beats selection on BOTH mean rank-IC AND quintile L/S Sharpe at {PRIMARY_H}d AND the "
         "split-half IC is same-sign. Otherwise `NEUTRAL` (display-only; the board keeps the "
         "validated rank and the composite rides as the per-name profile).\n"]
    if not powered:
        L.append("> **POWER GUARD ACTIVE.** The deep survivorship-clean matrix "
                 "(`data/breadth/_closes_deep.parquet`) and PIT membership "
                 "(`data/breadth/sp500_pit_membership.parquet`) are absent locally, so this is "
                 "a shallow diagnostic only. Every market's gate is FORCED to `NEUTRAL` — the "
                 "build will never flip a rank on powerless data. Run "
                 "`scripts.residual_alpha_fetch` + `scripts.residual_alpha_pit` for a real GO test.\n")

    for mkt, results in market_results.items():
        L.append(f"\n## Market: {mkt} — gate: **{gates[mkt]['gate']}**\n")
        if results is None:
            L.append(f"_skipped — {gates[mkt]['notes'][0] if gates[mkt]['notes'] else 'no data'}_\n")
            continue
        for h in horizons:
            if h not in results:
                continue
            res = results[h]
            tag = " (PRIMARY)" if h == PRIMARY_H else ""
            L.append(f"\n### Forward horizon: {h} trading days{tag}\n")
            L.append("| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |")
            L.append("|---|--:|--:|--:|--:|--:|--:|--:|---|")
            for k in ORDER:
                if k not in res:
                    continue
                ic, ls = res[k]["ic"], res[k]["ls"]
                n = ic.get("n", 0)
                h12 = (f"{ic.get('ic_h1')}→{ic.get('ic_h2')}" if ic.get("ic_h1") is not None else "—")
                if n >= 6:
                    # the HAC t/p need n>=8; on a short shallow grid they can be None even
                    # though mean IC is defined — format each field defensively.
                    L.append(f"| {LBL[k]} | {_fmt(ic.get('mean_ic'), '+.4f')} | "
                             f"{_fmt(ic.get('ic_ir'), '+.2f')} | {_fmt(ic.get('t_hac'), '+.2f')} | "
                             f"{_fmt(ic.get('p_hac'), '.3f')} | {ic.get('q_fdr', '—')} | {h12} | "
                             f"{ls.get('sharpe')} | {ls.get('verdict', '—')} |")
                else:
                    L.append(f"| {LBL[k]} | n/a | | | | | | {ls.get('sharpe')} | {ls.get('verdict', '—')} |")
        L.append(f"\n**{mkt} verdict ({PRIMARY_H}d):**")
        for note in gates[mkt]["notes"]:
            L.append(f"- {note}")
        if gates[mkt]["gate"] == "GO":
            L.append(f"\n**GO — rank the {mkt} board by `{LBL.get(gates[mkt]['winner'], gates[mkt]['winner'])}`.** "
                     "It beats the validated selection leg on both the cross-sectional IC and the "
                     "long/short Sharpe with a same-sign split-half — a measured upgrade, not cosmetic.")
        else:
            L.append(f"\n**NEUTRAL — keep the {mkt} board on its validated selection rank.** "
                     "The conviction composite rides as the displayed per-name profile/verdict "
                     "(the honest product is a readable profile, not a re-order claimed without "
                     "the power to back it).")

    L.append("\n---\n")
    L.append("**How to read.** `selection` is the baseline the board ships today. A composite must "
             f"beat it on BOTH IC and Sharpe at {PRIMARY_H}d *and* not flip sign across halves to earn "
             "a GO. The orthogonal composite decorrelates the axes (so it is not just re-weighted "
             "selection); the EW and selection-led variants bound the design space. The DSR deflates "
             "for the whole family screened (composites × horizons). On a shallow local run the gate "
             "is display-only by construction — only the deep + PIT panel can earn a re-rank.")
    return "\n".join(L) + "\n"


def _gate_path() -> Path:
    return config.data_dir() / "regime" / "stock_conviction_gate.json"


def write_gate(gates: dict, powered: bool, span: str) -> Path:
    """Persist {market: verdict} the build reads to decide the rank. Atomic-ish single
    write; only called on a clean run so a transient failure leaves the prior file."""
    p = _gate_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {m: gates[m]["gate"] for m in MARKETS}
    payload["_meta"] = {"powered": powered, "span": span, "primary_horizon": PRIMARY_H,
                        "winner": {m: gates[m].get("winner") for m in MARKETS},
                        "note": ("deep+PIT run" if powered else
                                 "shallow run — all gates forced NEUTRAL (display-only)")}
    p.write_text(json.dumps(payload, indent=2))
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=12,
                    help="restrict the rebalance grid to the last N years")
    ap.add_argument("--horizons", type=str, default="63,21,126",
                    help="comma-separated forward-return horizons; first is the primary gate horizon")
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    if PRIMARY_H not in horizons:
        horizons = [PRIMARY_H] + horizons

    # --- data: prefer the deep survivorship-clean panel + PIT membership; degrade -----
    deep = _closes_deep()
    membership = _load_membership()
    powered = (not deep.empty) and (membership is not None)
    if powered:
        closes = deep
        for fn in ("_closes_delisted.parquet", "_closes_delisted_1500.parquet"):
            delp = config.data_dir() / "breadth" / fn
            if delp.exists():
                closes = pd.concat([closes, pd.read_parquet(delp)], axis=1)
                closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
        log.info("DEEP panel: %d names · PIT membership loaded", closes.shape[1])
    else:
        print("deep data unavailable — shallow run, gate defaults to display-only")
        closes = _closes()                                 # ~3y live breadth cache
        membership = None
        if closes.empty:
            # nothing to even diagnose — still write a NEUTRAL gate + a stub report so the
            # build always has a present file, and exit 0 (never break the build).
            log.warning("no shallow close matrix either — writing NEUTRAL gate stub")
            gates = {m: {"gate": "NEUTRAL", "winner": None,
                         "notes": ["no close matrix available at all — NEUTRAL stub"]}
                     for m in MARKETS}
            gp = write_gate(gates, powered=False, span="n/a")
            rep = ("# Unified Conviction Profile — Phase 0 gate\n\n"
                   "No close matrix available locally — every market gate defaults to "
                   "NEUTRAL (display-only). Run the breadth collectors / "
                   "`scripts.residual_alpha_fetch` for a real test.\n")
            out = config.ROOT / config.load()["storage"]["reports_dir"] / "stock-conviction-phase0.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rep)
            print(f"[gate] {gp}\n[report] {out}")
            return 0

    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    tkr_sector = {t: (s if s and s != "—" else "Other") for t, s in tkr_sector.items()}
    spy = _yahoo_ret("SPY", closes.index)

    R = closes.pct_change(fill_method=None)
    grid = month_grid(R.index, warmup=WIN + SKIP + FORM, horizon=max(horizons))
    if args.years:
        cutoff = R.index.max() - pd.DateOffset(years=args.years)
        grid = [d for d in grid if d >= cutoff]

    if len(grid) < 6:
        # too few rebalances to say anything — NEUTRAL everywhere, but still a clean run.
        log.warning("grid too short (%d) — writing NEUTRAL gate, shallow report", len(grid))
        gates = {m: {"gate": "NEUTRAL", "winner": None,
                     "notes": [f"grid too short ({len(grid)} rebalances) — NEUTRAL"]}
                 for m in MARKETS}
        gp = write_gate(gates, powered=powered,
                        span=(f"{grid[0].date()}..{grid[-1].date()}" if grid else "n/a"))
        rep = render({m: None for m in MARKETS}, gates,
                     span=(f"{grid[0].date()}..{grid[-1].date()}" if grid else "n/a"),
                     n_reb=len(grid), n_uni=0, powered=powered, horizons=horizons)
        out = config.ROOT / config.load()["storage"]["reports_dir"] / "stock-conviction-phase0.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep)
        print(f"[gate] {gp}\n[report] {out}")
        return 0

    log.info("grid: %d monthly rebalances %s..%s", len(grid), grid[0].date(), grid[-1].date())

    # PIT fundamentals (deep) + SUE. Prefer the REAL validated SUE (engine.sue, the FDR
    # survivor: point-in-time standardized unexpected earnings vs the seasonal expectation
    # from the quarterly EPS panel) — the crude ni-YoY _sue_proxy understates it badly. Fall
    # back to the proxy only if the EPS panel is absent.
    fund_panel = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    fund_cache = pit_fund_panels(grid, closes, fund_panel)
    try:
        from engine import sue as _sue
        eps_panel = _sue.load_panel()
        if eps_panel is not None and not eps_panel.empty:
            sue_cache = {str(d.date()): _sue.sue_cross_section(eps_panel, d) for d in grid}
            log.info("SUE: REAL validated SUE from the quarterly EPS panel (%d names latest)",
                     int(sum(1 for s in sue_cache.values() if s is not None and not s.empty)))
        else:
            sue_cache = _sue_proxy(fund_panel, grid)
            log.warning("SUE: EPS panel empty — falling back to the ni-YoY proxy")
    except Exception as e:  # noqa: BLE001
        log.warning("SUE: real-SUE path failed (%s) — using the ni-YoY proxy", e)
        sue_cache = _sue_proxy(fund_panel, grid)

    # The axis construction (residual alpha, fundamentals, factor maths) is the US/CA
    # equity panel. CN/HK have NO deep survivorship panel in this repo, so the harness
    # can only POWER the US/CA construction here; CN/HK are reported as NOT-TESTED and
    # default to NEUTRAL (their shipped trust tier is already display-only by design —
    # CN reversal-context, HK no-edge screen — so a GO there would need their own panel).
    R2, mats = build_axis_panels(closes, spy, tkr_sector, grid, fund_cache, sue_cache)
    diag = overlap_diagnostics(
        pd.concat([mats[k].stack().rename(k) for k in AXES if not mats[k].empty], axis=1)
    ) if all(not mats[k].empty for k in AXES) else {}
    results = {h: evaluate(R2, mats, closes, grid, h, membership) for h in horizons}

    market_results: dict = {}
    gates: dict = {}
    span = f"{grid[0].date()}..{grid[-1].date()}"
    eligible_by_date = ({d: [t for t in _eligible(membership, d) if t in closes.columns] for d in grid}
                        if membership is not None
                        else {d: list(closes.columns) for d in grid})
    n_uni = int(np.median([len(v) for v in eligible_by_date.values()])) if eligible_by_date else 0

    for mkt in MARKETS:
        if mkt in ("US", "CA"):
            # US/CA share the residual-alpha selection construction tested here.
            market_results[mkt] = results
            verdict, winner, notes = decide_gate(results, powered)
            gates[mkt] = {"gate": verdict, "winner": winner, "notes": notes}
        else:
            # CN/HK: no deep panel in-repo to power this construction → NOT TESTED, NEUTRAL.
            market_results[mkt] = None
            gates[mkt] = {"gate": "NEUTRAL", "winner": None,
                          "notes": [f"{mkt} not tested here (no deep survivorship panel for this "
                                    "market in-repo) — gate NEUTRAL / display-only, matching the "
                                    "shipped trust tier (CN reversal-context · HK no-edge screen)"]}

    if diag:
        log.info("axis overlap: mean|corr| raw %s → orth %s · VIF %s",
                 diag.get("mean_abs_corr_raw"), diag.get("mean_abs_corr_orth"), diag.get("vif"))

    report = render(market_results, gates, span, len(grid), n_uni, powered, horizons)
    if diag:
        report += ("\n## Axis overlap diagnostic (US/CA panel)\n\n"
                   f"- mean |cross-axis corr| raw → orth: **{diag.get('mean_abs_corr_raw')}** → "
                   f"**{diag.get('mean_abs_corr_orth')}**\n- VIF: {diag.get('vif')}\n")
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "stock-conviction-phase0.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    gp = write_gate(gates, powered, span)
    print("\n" + report)
    print(f"[gate] {gp}")
    print(f"[report] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
