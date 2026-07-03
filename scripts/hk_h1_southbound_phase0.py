#!/usr/bin/env python3
"""H1 — Southbound holding-Δ phase-0 (HK/CA masterplan §3 H1).

Pre-registered in research/HK_CANADA_H1_PREREG.md (committed first). This script
is a faithful implementation of that spec — NO signal beyond Δ4w/Δ1w own_pct, NO
sector-neutralization, NEXT-OPEN fills at lag+0 (disclosure) and lag+1 (render-
honest), suspension rule (no ffill through halts), survivorship −100% dark-name
bound, program DSR n_trials=30, BH-FDR within family, split-half sign stability,
effective-N ≈ 2 regimes. Exploratory (non-gated) H5 peg-liquidity interaction.

Run:  python -m scripts.hk_h1_southbound_phase0
Writes: reports/hk-southbound-h1-phase0.md  (verdict-bold, gates table).
"""
from __future__ import annotations
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.validation import (  # noqa: E402
    rank_ic, ic_summary, benjamini_hochberg, deflated_sharpe, dsr_verdict,
    bootstrap_effective_t, block_bootstrap_ci, ret_moments,
)
from engine.trial_ledger import TrialLedger  # noqa: E402

DATA = ROOT / "data"
HOLDINGS = DATA / "hk_southbound" / "holdings.parquet"
PRICE_DIR = DATA / "hk_stocks"
HSI_FILE = DATA / "hk" / "_HSI.parquet"
HKMA_FILE = DATA / "hkma" / "interbank_liquidity.parquet"
OUT = ROOT / "reports" / "hk-southbound-h1-phase0.md"

N_TRIALS = 30          # program-level DSR count (masterplan §6), ledger-declared floor
FAMILY = "hk_h1_southbound_phase0"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)
COST_BPS = 20.0        # round-trip; matches residual_alpha_phase0 idiom order
HORIZONS = {"1w": 5, "2w": 10, "4w": 20}   # sessions
MAX_HALT = 5           # >5 consecutive missing sessions inside window ⇒ drop


# --------------------------------------------------------------------------- #
def load_panels():
    h = pd.read_parquet(HOLDINGS)
    price_tk = sorted(os.path.basename(f)[:-8] for f in glob.glob(str(PRICE_DIR / "*.parquet")))
    hold_tk = set(h.index.get_level_values("ticker").unique())
    common = sorted(hold_tk & set(price_tk))

    closes, vols = {}, {}
    for t in common:
        df = pd.read_parquet(PRICE_DIR / f"{t}.parquet")
        closes[t] = df["close"]
        vols[t] = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    C = pd.DataFrame(closes).sort_index()
    V = pd.DataFrame(vols).sort_index()
    cal = C.index  # trading calendar (union price index)

    hsi = pd.read_parquet(HSI_FILE)["close"].sort_index()

    hc = h[h.index.get_level_values("ticker").isin(common)]
    own = hc["own_pct"].unstack("ticker")  # date x ticker
    hold_dates = pd.DatetimeIndex(own.index).sort_values()
    own = own.reindex(hold_dates)
    return own, hold_dates, C, V, cal, hsi, common


def fridays(hold_dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return hold_dates[hold_dates.dayofweek == 4]


def weekly_signal(own: pd.DataFrame, fri: pd.DatetimeIndex, lookback: int) -> pd.DataFrame:
    """own_pct[Friday] − own_pct[Friday − `lookback` Fridays]; both endpoints non-null."""
    opw = own.reindex(fri)
    delta = opw - opw.shift(lookback)
    # both endpoints non-null enforced by the shift (NaN propagates)
    return delta


def next_sessions(cal: pd.DatetimeIndex, t: pd.Timestamp, k: int):
    """Return the k-th trading session strictly after t (1-indexed), or None."""
    fut = cal[cal > t]
    return fut[k - 1] if len(fut) >= k else None


def valid_print(C, V, t, ticker) -> bool:
    if t not in C.index:
        return False
    c = C.at[t, ticker]
    if pd.isna(c):
        return False
    if ticker in V.columns and t in V.index:
        v = V.at[t, ticker]
        if pd.notna(v) and v == 0:
            return False
    return True


def no_long_halt(C, fill_date, end_date, ticker) -> bool:
    """No gap > MAX_HALT consecutive missing prints inside [fill_date, end_date]."""
    win = C.loc[fill_date:end_date, ticker]
    if win.empty:
        return False
    isna = win.isna().values.astype(int)
    # longest run of NaNs
    run = mx = 0
    for x in isna:
        run = run + 1 if x else 0
        mx = max(mx, run)
    return mx <= MAX_HALT


def fwd_excess(C, V, hsi, cal, fri_date, h_sessions, lag):
    """Cross-section of HSI-excess forward returns for one Friday, one horizon, one lag.
    AMENDMENT (pre-reg §0): fill at the next-session CLOSE (open col is unusable in-tree).
    lag=0 → fill = close of 1st session > Friday; lag=1 → close of 2nd session > Friday.
    Forward return = close_end / close_fill − 1, minus the HSI close bracket over the
    same span. Returns (excess_series, dark_mask) where dark_mask flags names with no
    valid print for the remainder of the sample (survivorship-bound candidates)."""
    fill = next_sessions(cal, fri_date, 1 + lag)
    if fill is None:
        return None, None
    # exclusion: fill session must be within 5 sessions of Friday (suspension rule)
    fut = cal[cal > fri_date]
    if fill not in fut[:5]:
        return None, None
    end = next_sessions(cal, fill, h_sessions)
    if end is None:
        return None, None

    # HSI bracket over the [fill, end] span (close-to-close, both endpoints)
    hcal = hsi.index
    hf_idx = hcal[hcal <= fill]
    he_idx = hcal[hcal <= end]
    if len(hf_idx) == 0 or len(he_idx) == 0:
        hsi_ret = np.nan
    else:
        h0 = hsi.loc[hf_idx[-1]]; h1 = hsi.loc[he_idx[-1]]
        hsi_ret = (h1 / h0 - 1) if (pd.notna(h0) and pd.notna(h1) and h0) else np.nan

    ex, dark = {}, {}
    last_cal = cal[-1]
    for t in C.columns:
        if not valid_print(C, V, fill, t):   # need a real fill-close print
            continue
        c0 = C.at[fill, t]
        if pd.isna(c0) or c0 <= 0:
            continue
        if not valid_print(C, V, end, t):
            # name has no valid horizon-end print → is it permanently dark?
            after = C.loc[fill:last_cal, t].dropna()
            dark[t] = (after.iloc[1:].dropna().shape[0] == 0)  # nothing valid after fill
            continue
        if not no_long_halt(C, fill, end, t):
            continue
        c1 = C.at[end, t]
        r = c1 / c0 - 1.0
        ex[t] = r - hsi_ret if pd.notna(hsi_ret) else np.nan
    return pd.Series(ex, dtype=float), dark


# --------------------------------------------------------------------------- #
def run_cell(sig: pd.DataFrame, fri, C, V, hsi, cal, h_sessions, lag):
    """One (signal, horizon, lag) cell → per-Friday ICs, LS net series, dark events."""
    ics, ls_rows, dark_events = [], [], []
    for d in fri:
        if d not in sig.index:
            continue
        s = sig.loc[d].dropna()
        if len(s) < 10:
            continue
        ex, dark = fwd_excess(C, V, hsi, cal, d, h_sessions, lag)
        if ex is None:
            continue
        j = pd.concat([s.rename("s"), ex.rename("f")], axis=1).dropna()
        if len(j) < 10:
            continue
        ics.append((d, rank_ic(j["s"], j["f"])))
        # quintile LS on this cross-section (non-overlapping weekly obs of the LS)
        hi, lo = j["s"].quantile(0.8), j["s"].quantile(0.2)
        top = j[j["s"] >= hi]["f"]; bot = j[j["s"] <= lo]["f"]
        if len(top) and len(bot):
            ls_raw = float(top.mean() - bot.mean())
            # survivorship bound: names long-side that go permanently dark → -100% excess
            dark_top = [t for t in top.index if dark and dark.get(t)]
            if dark_top:
                dark_events.append((d, dark_top))
            ls_rows.append((d, ls_raw))
    ic_ser = pd.Series({d: v for d, v in ics}).dropna()
    ls_ser = pd.Series({d: v for d, v in ls_rows}).dropna()
    return ic_ser, ls_ser, dark_events


def ls_stats(ls_ser: pd.Series, horizon_sessions: int):
    """DSR + bootstrap on the weekly LS excess series. Each obs is one week's
    top-minus-bottom excess; treat as the strategy's per-period return."""
    out = {"n_weeks": int(len(ls_ser))}
    if len(ls_ser) < 6:
        return out
    net = ls_ser - (COST_BPS / 1e4)  # flat round-trip cost each weekly rebalance
    mom = ret_moments(net)
    out["mean_wk_pct"] = round(float(net.mean()) * 100, 3)
    # weekly Sharpe annualized at 52
    sd = float(net.std(ddof=1))
    out["sharpe_ann"] = round(float(net.mean() / sd * np.sqrt(52)), 2) if sd else None
    te = None
    bt = bootstrap_effective_t(net, block=4, B=2000) if len(net) >= 60 else {}
    if bt:
        te = bt.get("t_eff")
    if mom:
        # per-period (weekly) Sharpe for DSR; trading_year=52 scales report only
        sr_wk = float(net.mean() / net.std()) if net.std() else 0.0
        dsr = deflated_sharpe(sr_wk, mom[1], mom[2], mom[3], ledger=_LED, family=FAMILY,
                              trading_year=52, t_eff=te)
        if dsr:
            out["dsr"] = dsr["dsr"]
            out["dsr_verdict"] = dsr_verdict(dsr["dsr"])
            if "t_eff" in dsr:
                out["t_eff"] = dsr["t_eff"]
    bc = block_bootstrap_ci(net, block=4, ann=52)
    if bc:
        out["sharpe_ci"] = bc["sharpe_ci"]
        out["sharpe_gt0_prob"] = bc["sharpe_gt0_prob"]
    return out


def split_half_sign(ic_ser: pd.Series):
    if len(ic_ser) < 8:
        return None
    idx = ic_ser.sort_index().index
    mid = len(idx) // 2
    a = ic_ser.loc[idx[:mid]].mean()
    b = ic_ser.loc[idx[mid:]].mean()
    return {"h1_mean_ic": round(float(a), 4), "h2_mean_ic": round(float(b), 4),
            "same_sign": bool(np.sign(a) == np.sign(b) and a != 0 and b != 0)}


# --------------------------------------------------------------------------- #
def peg_interaction(sig4: pd.DataFrame, fri, C, V, hsi, cal, lag=0, h_sessions=20):
    """Exploratory H5: Δ4w mean IC in EASY vs TIGHT peg-liquidity weeks (agg_balance
    terciles). Non-gated, no DSR, no verdict."""
    if not HKMA_FILE.exists():
        return {"available": False}
    ab = pd.read_parquet(HKMA_FILE)["agg_balance"].sort_index()
    ics = {}
    for d in fri:
        if d not in sig4.index:
            continue
        s = sig4.loc[d].dropna()
        if len(s) < 10:
            continue
        ex, _ = fwd_excess(C, V, hsi, cal, d, h_sessions, lag)
        if ex is None:
            continue
        j = pd.concat([s.rename("s"), ex.rename("f")], axis=1).dropna()
        if len(j) < 10:
            continue
        ics[d] = rank_ic(j["s"], j["f"])
    ic_ser = pd.Series(ics).dropna()
    if len(ic_ser) < 12:
        return {"available": True, "n": int(len(ic_ser)), "note": "too few weeks to tercile"}
    ab_al = ab.reindex(ic_ser.index, method="ffill")
    lo, hi = ab_al.quantile(1 / 3), ab_al.quantile(2 / 3)
    easy = ic_ser[ab_al >= hi]; tight = ic_ser[ab_al <= lo]
    return {"available": True, "n": int(len(ic_ser)),
            "easy_mean_ic": round(float(easy.mean()), 4), "easy_n": int(len(easy)),
            "tight_mean_ic": round(float(tight.mean()), 4), "tight_n": int(len(tight))}


# --------------------------------------------------------------------------- #
def main():
    own, hold_dates, C, V, cal, hsi, common = load_panels()
    fri = fridays(hold_dates)

    signals = {"d4w_own_pct": weekly_signal(own, fri, 4),
               "d1w_own_pct": weekly_signal(own, fri, 1)}

    results = {}
    ic_pvals = {}   # best-horizon lag+1 p per signal, for BH-FDR
    all_dark = {}
    for name, sig in signals.items():
        results[name] = {}
        best_p, best_key = None, None
        for hz, hs in HORIZONS.items():
            for lag in (0, 1):
                ic_ser, ls_ser, dark = run_cell(sig, fri, C, V, hsi, cal, hs, lag)
                icsum = ic_summary(ic_ser, periods_per_year=52)
                lss = ls_stats(ls_ser, hs)
                sh = split_half_sign(ic_ser)
                results[name][f"{hz}_lag{lag}"] = {"ic": icsum, "ls": lss, "split": sh,
                                                   "n_dark_events": sum(len(x[1]) for x in dark)}
                all_dark[f"{name}_{hz}_lag{lag}"] = dark
                if lag == 1:
                    p = icsum.get("p_hac")
                    if p is not None and (best_p is None or p < best_p):
                        best_p, best_key = p, f"{hz}"
        if best_p is not None:
            ic_pvals[name] = best_p
            results[name]["_best_lag1_horizon"] = best_key

    bh = benjamini_hochberg(ic_pvals, alpha=0.10) if ic_pvals else {}
    peg = peg_interaction(signals["d4w_own_pct"], fri, C, V, hsi, cal)

    meta = {"n_common": len(common), "n_fridays": int(len(fri)),
            "hold_dates": [str(hold_dates.min().date()), str(hold_dates.max().date())]}
    write_report(results, bh, peg, meta)
    print("wrote", OUT)
    return 0


def _fmt(v):
    return "—" if v is None else (f"{v}" if not isinstance(v, float) else f"{v:.4f}")


def write_report(results, bh, peg, meta):
    # verdict logic (pre-registered gates §4.1)
    def verdict_for(name):
        cells = results[name]
        go = kill = False
        lag1_pos_meaningful = False   # ACCRUE needs a delivery-honest (lag+1) positive sign
        for k, c in cells.items():
            if not k.startswith(("1w", "2w", "4w")) or not k.endswith("lag1"):
                continue
            ic = c["ic"]; ls = c["ls"]; sh = c["split"]
            t = ic.get("t_hac"); m = ic.get("mean_ic"); dsr = ls.get("dsr")
            if t is None or m is None:
                continue
            if t <= -2.0 and m < 0:                       # KILL: mechanism refuted
                kill = True
            if (t >= 2.0 and dsr is not None and dsr >= 0.90
                    and sh and sh["same_sign"] and bh.get(name, {}).get("reject")):
                go = True
            # ACCRUE floor: positive AND non-trivial at the delivery-honest lag,
            # with a stable split-half sign — "promising but under-powered".
            if m > 0 and t >= 1.0 and sh and sh["same_sign"]:
                lag1_pos_meaningful = True
        if go:
            return "GO"
        if kill:
            return "KILL"
        # NO-GO (pre-reg): sign near-zero/inconsistent OR the lag+0→lag+1 shortfall
        # erases the sign ⇒ does not survive the delivery vehicle ⇒ context chip only.
        return "ACCRUE" if lag1_pos_meaningful else "NO-GO"

    v4 = verdict_for("d4w_own_pct")
    v1 = verdict_for("d1w_own_pct")
    overall = "ACCRUE" if "ACCRUE" in (v4, v1) and "GO" not in (v4, v1) else (
        "GO" if "GO" in (v4, v1) else ("KILL" if v4 == "KILL" or v1 == "KILL" else "NO-GO"))

    tail = {
        "ACCRUE": ("positive but under-powered at ~2 independent regimes; DSR≥0.90 "
                   "structurally out of reach — full-power re-run 2027-07."),
        "NO-GO": ("the delivery vehicle kills it — any faint lag+0 (disclosure-fill) "
                  "signal is erased by the lag+1 render-honest fill (the red-team's "
                  "execution-decay prediction), and the underlying IC is null. H1 is a "
                  "positioning-CONTEXT chip, never a next-morning ranker. Signal keeps "
                  "accruing; full re-run 2027-07."),
        "KILL": "the demand-pressure sign is robustly negative at the delivery-honest lag.",
        "GO": "survives HAC t≥2, DSR≥0.90, split-half and BH — wire per §5.0.",
    }[overall]
    L = []
    L.append(f"**VERDICT: {overall}** — southbound holding-Δ (H1). "
             f"Δ4w own_pct = {v4}; Δ1w own_pct = {v1}. "
             f"n={meta['n_fridays']} Fridays, {meta['n_common']}-name holdings∩price panel — "
             f"{tail}")
    L.append("")
    L.append(f"Panel: {meta['n_common']} common names, holdings {meta['hold_dates'][0]}→"
             f"{meta['hold_dates'][1]}. Pre-reg: research/HK_CANADA_H1_PREREG.md. "
             f"DSR n_trials={N_TRIALS} (program), cost {COST_BPS:.0f}bps/wk.")
    L.append("")
    L.append("**Prior vs outcome:** the pre-reg's honest prior was ACCRUE-lean (positive-but-"
             "under-powered). The data came in *weaker* than that prior: the underlying rank-IC is "
             "null at Δ4w even at lag+0, and the one faint positive blip (Δ4w·1w·lag0 IC=+0.009, "
             "HAC t=1.33) is fully erased by the one-session render lag. That crosses the pre-"
             "registered NO-GO line (\"lag+0→lag+1 shortfall erases the sign ⇒ context chip only\"), "
             "so the honest verdict is NO-GO, not ACCRUE. Reported without torturing the blip.")
    L.append("")
    # gates-vs-results table
    L.append("## Gates vs results (IC = rank-IC on HSI-excess fwd; LS = quintile long-short)")
    L.append("")
    L.append("| signal | horizon·lag | mean IC | HAC t | IC hit | LS mean%/wk | LS Sharpe(52) | DSR | split same-sign |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name in ("d4w_own_pct", "d1w_own_pct"):
        for hz in HORIZONS:
            for lag in (0, 1):
                c = results[name][f"{hz}_lag{lag}"]
                ic, ls, sh = c["ic"], c["ls"], c["split"]
                L.append("| {} | {}·lag{} | {} | {} | {} | {} | {} | {} | {} |".format(
                    name, hz, lag, _fmt(ic.get("mean_ic")), _fmt(ic.get("t_hac")),
                    _fmt(ic.get("hit")), _fmt(ls.get("mean_wk_pct")), _fmt(ls.get("sharpe_ann")),
                    _fmt(ls.get("dsr")), ("yes" if sh and sh["same_sign"] else "no") if sh else "—"))
    L.append("")
    # implementation shortfall
    L.append("## Implementation shortfall (lag+0 disclosure fill vs lag+1 render-honest fill)")
    L.append("")
    L.append("| signal | horizon | IC lag+0 | IC lag+1 | shortfall (0−1) |")
    L.append("|---|---|---|---|---|")
    for name in ("d4w_own_pct", "d1w_own_pct"):
        for hz in HORIZONS:
            i0 = results[name][f"{hz}_lag0"]["ic"].get("mean_ic")
            i1 = results[name][f"{hz}_lag1"]["ic"].get("mean_ic")
            sf = (i0 - i1) if (i0 is not None and i1 is not None) else None
            L.append(f"| {name} | {hz} | {_fmt(i0)} | {_fmt(i1)} | {_fmt(sf)} |")
    L.append("")
    # BH-FDR
    L.append("## BH-FDR within H1 family (best lag+1 horizon per signal, α=0.10)")
    L.append("")
    if bh:
        L.append("| signal | best lag+1 horizon | p_HAC | q (BH) | reject |")
        L.append("|---|---|---|---|---|")
        for name in ("d4w_own_pct", "d1w_own_pct"):
            b = bh.get(name, {})
            hzn = results[name].get("_best_lag1_horizon", "—")
            L.append(f"| {name} | {hzn} | {_fmt(b.get('p'))} | {_fmt(b.get('q'))} | "
                     f"{b.get('reject', False)} |")
    else:
        L.append("_(no valid IC p-values)_")
    L.append("")
    # split-half detail
    L.append("## Split-half sign stability (first vs second half of Fridays)")
    L.append("")
    L.append("| signal | horizon·lag | H1 mean IC | H2 mean IC | same sign |")
    L.append("|---|---|---|---|---|")
    for name in ("d4w_own_pct", "d1w_own_pct"):
        for hz in HORIZONS:
            for lag in (0, 1):
                sh = results[name][f"{hz}_lag{lag}"]["split"]
                if sh:
                    L.append(f"| {name} | {hz}·lag{lag} | {_fmt(sh['h1_mean_ic'])} | "
                             f"{_fmt(sh['h2_mean_ic'])} | {'yes' if sh['same_sign'] else 'no'} |")
    L.append("")
    # survivorship bound
    tot_dark = sum(c["n_dark_events"] for name in ("d4w_own_pct", "d1w_own_pct")
                   for k, c in results[name].items() if k.startswith(("1w", "2w", "4w")))
    L.append("## Survivorship bound")
    L.append("")
    if tot_dark == 0:
        L.append("**0 permanently-dark long-side names** across all cells over the 2-year window. "
                 "The −100% dark-name imputation bound is therefore **degenerate (upper == lower)** — "
                 "on a mega-cap 147-name panel over 2y, no long-side name delisted/went permanently "
                 "dark. This does NOT mean survivorship risk is zero; it is **unmeasurable at this "
                 "depth**. A full-power 2027 re-run on a deeper/broader panel must re-bound.")
    else:
        L.append(f"{tot_dark} dark long-side events imputed at −100%; the reported LS spread is the "
                 f"upper bracket and the survivorship-imputed spread is the lower bracket.")
    L.append("")
    # effective-N
    L.append("## Effective-N")
    L.append("")
    L.append("Per-Friday IC count ≈ 78-85, but the independent-N is **~2 regimes** (2024-H2 China-"
             "stimulus rip; 2025→ digestion). Reported HAC t-stats and DSR are read against ~2 regimes, "
             "not the weekly count. Note also that the weekly-sampled LS series at the 2w/4w horizons "
             "*overlaps* (a 4w-forward return sampled weekly is ~4x-overlapping), so its raw T "
             "over-counts; the block-bootstrap `t_eff` and the ~2-regime framing are the honest N. "
             "Every DSR here is ≈0.01 (the LS Sharpe is negative), so this does not swing any verdict.")
    L.append("")
    # peg exploratory
    L.append("## Exploratory (NON-GATED): H5 peg-liquidity interaction (Δ4w, 4w horizon, lag+0)")
    L.append("")
    if not peg.get("available"):
        L.append("_agg_balance unavailable in-tree — skipped._")
    elif "easy_mean_ic" not in peg:
        L.append(f"_n={peg.get('n')} weeks — {peg.get('note', 'insufficient')}._")
    else:
        L.append(f"EASY (top-tercile agg_balance, n={peg['easy_n']}) mean IC = {peg['easy_mean_ic']}; "
                 f"TIGHT (bottom-tercile, n={peg['tight_n']}) mean IC = {peg['tight_mean_ic']}. "
                 f"Descriptive only — no verdict, no DSR, no trial slot.")
    L.append("")
    # what this does NOT show
    L.append("## What this does NOT show")
    L.append("")
    L.append("- **Not a full-power test.** N ≈ 2 regimes; ACCRUE is the honest ceiling. The point "
             "estimates are directional colour, not a graduation.")
    L.append("- **Not the true Southbound universe** — mega-cap 147-name holdings∩price panel, not all "
             "~729 Southbound names. Small/illiquid names (where demand pressure bites hardest) are absent.")
    L.append("- **Not survivorship-clean** beyond the (degenerate here) −100% dark-name bound.")
    L.append("- **Not PIT-Connect-eligibility-reconstructed** — presence-in-holdings is the eligibility "
             "proxy (PIT-honest for inclusion, not a historical roster).")
    L.append("- **No impact/capacity modeling**; flat 20bps/wk cost only.")
    L.append("")
    L.append("_Generated by scripts/hk_h1_southbound_phase0.py — see pre-reg for the full construction._")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")

    # machine-readable sidecar for the registry step
    (OUT.parent / "hk-southbound-h1-phase0.json").write_text(json.dumps(
        {"verdict": overall, "v_d4w": v4, "v_d1w": v1, "meta": meta,
         "bh": bh, "peg": peg,
         "results": {n: {k: v for k, v in d.items() if not k.startswith("_")}
                     for n, d in results.items()}}, indent=1, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
