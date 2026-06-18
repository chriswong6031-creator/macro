"""Phase-0 for the SINGLE-NAME directional model — does the validated real-rate edge
TRANSMIT to single names, OUT-OF-SAMPLE, as a POOLED panel (NOT 1500 per-name fits)?

The honest question (research/NAME_DIRECTION.md): index_direction validated exactly one
robust equity directional driver — real rates (QQQ-med, XLK-med, SMH-long, XLP-long). A
single name's lean, if any, should be its DURATION EXPOSURE to that driver. We test the
ONE channel as ~2 hypotheses (medium 42td, long 189td), pooled across the deep S&P-1500
panel, with every honesty guard the index harness uses — and we expect it to score little
or nothing (Goyal-Welch + Gu-Kelly-Xiu ~0.3-0.4% stock-level OOS-R² ceiling).

Signal (per name, causal):
    dur_i,t    = −beta_i,t   (beta = cov(r_i, Δreal10)/var(Δreal10), lagged 1d), Vasicek-shrunk
    signal_i,t = shrunk(dur_i,t) · rr_leg_t      rr_leg = index_direction real_rate leg (z; high=rates fell)
The shipped lean is r̂ = b·signal (a tilt around each name's OWN drift), so we VALIDATE exactly
that: forecast_i = bench_i + b·signal_i vs bench_i (per-name expanding mean = Goyal-Welch), with
b fit pooled THROUGH ORIGIN on (fwd−bench)~signal, sign-clipped to +.

Three statistics that must AGREE per horizon (unit of inference = the per-DATE cross-section,
never the name×date cells):
  (a) cross-sectional rank-IC track  → ic_summary (HAC-t)             [dispersion ranks right]
  (b) pooled Campbell-Thompson OOS-R² + Clark-West, per-date-aggregated [level accuracy + nested test]
  (c) BEATS a driver-only nested bench (everyone gets the same call, NO beta dispersion) [anti-relabel]
plus a CALIBRATED P(up) (recalibrated Brier skill ≥ −0.01). Then BH-FDR across the 2 horizons.
DSR + block-bootstrap reported as context, never a veto. GO decided on the PIT panel.

Run:
  python3 -m scripts.name_direction_phase0                  # deep panel (survivorship-biased)
  python3 -m scripts.name_direction_phase0 --pit            # + S&P-1500 PIT membership cross-check
  python3 -m scripts.name_direction_phase0 --write-gate     # also write the NAME_DIRECTION gate block
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

from engine import index_direction as idr, name_direction as nd, residual_alpha as ra  # noqa: E402
from engine import validation as V  # noqa: E402
from lib import config  # noqa: E402

STEP = 21                  # monthly rebalance
MIN_TRAIN = 2520           # ~10y before the first OOS prediction
MIN_NAMES = 25             # min cross-section per rebalance date
# FROZEN multiple-testing count for the DSR haircut: the WHOLE single-name screen =
# 2 horizons × 2 sign-variants (natural-sign primary, ReLU reported) ≈ 4. Asserted in tests.
N_TRIALS = 4
DATA, REGIME = Path("data"), Path("data/regime")


def _closes_deep() -> pd.DataFrame:
    p = DATA / "breadth" / "_closes_deep.parquet"
    return pd.read_parquet(p).sort_index() if p.exists() else pd.DataFrame()


def _load_membership() -> pd.DataFrame | None:
    """S&P-1500 point-in-time membership (data/breadth/sp1500_pit_membership.parquet).
    Reduces forward-inclusion bias (a name only counts on dates it was a member); it does
    NOT remove survivorship of delisted names (their closes aren't in the deep panel) — a
    PIT FAIL here is conservative, a deep PASS optimistic."""
    p = DATA / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        return None
    m = pd.read_parquet(p)
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _eligible(membership: pd.DataFrame, d) -> set:
    d = pd.Timestamp(d)
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])


def _spy_close(index: pd.DatetimeIndex) -> pd.Series:
    return pd.read_parquet(DATA / "yahoo" / "SPY.parquet")["close"].dropna()


def build_signal_panel(closes: pd.DataFrame, shrink: float, relu: bool = False) -> pd.DataFrame:
    """date×ticker signal = shrunk(−beta_to_Δreal10) · rr_leg, in the SAME PERCENT units the
    live engine uses (rr_leg is a z-score; the pooled slope carries the % scaling)."""
    real10 = pd.read_parquet(DATA / "fred" / "DFII10.parquet")
    real10 = real10[real10.columns[0]].dropna()
    rr_leg = idr.build_legs(_spy_close(closes.index).astype(float))["real_rate"]
    R = closes.pct_change(fill_method=None)
    d_rr = real10.reindex(closes.index).ffill().diff()
    beta = ra._causal_beta(R, d_rr, nd.NAME_BETA_WIN, nd.NAME_BETA_MINP)
    dur = -beta
    if relu:                          # sensitivity variant: only positive-duration names lean
        dur = dur.clip(lower=0.0)
    dur = ra._shrink(dur, shrink)     # Vasicek toward the cross-sectional mean that day
    rr = rr_leg.reindex(closes.index).ffill()
    return dur.mul(rr, axis=0)


def _month_grid(index, warmup, horizon):
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc >= warmup and loc + horizon < len(index):
            out.append(d[-1])
    return out


def score_horizon(closes, signal, h, *, shrink, membership=None, label=""):
    """Pooled walk-forward at horizon h. Returns the gate-decision dict for this horizon."""
    fwd = closes.pct_change(h, fill_method=None).shift(-h) * 100.0     # PERCENT, matches sigma_h
    vol = (closes.pct_change(fill_method=None).rolling(252, min_periods=126).std()
           * np.sqrt(h) * 100.0).shift(1)                              # causal per-name σ_h (%)
    # per-name Goyal-Welch bench, computed ONCE (expanding mean is cumulative, so a fold's
    # as-of value is just a slice — avoids recomputing an O(T×N) expanding mean per fold).
    bench_full = fwd.expanding(min_periods=60).mean().shift(1)
    grid = _month_grid(closes.index, warmup=MIN_TRAIN, horizon=h)
    if len(grid) < 8:
        return {"error": f"grid too short ({len(grid)})", "scored": False}

    ics = []                                  # per-date cross-sectional rank-IC (dispersion)
    fadj_d, ssef_d, sseb_d = [], [], []       # per-date CW term + SSE (dispersed forecast)
    ssef0_d, sseb0_d = [], []                 # per-date SSE (driver-only nested bench)
    p_all, y_all = [], []                     # pooled calibration pairs
    dates_used, slope_full = [], None

    for i in range(MIN_TRAIN, len(closes) - h, STEP):
        d = closes.index[i]
        train_lbl = closes.index[: i - h + 1]                 # labels fully realized (embargo h)
        # pooled training stack: (signal, fwd, per-name expanding mean bench)
        sig_tr = signal.loc[train_lbl]
        fwd_tr = fwd.loc[train_lbl]
        bench_tr = bench_full.loc[train_lbl]                           # per-name Goyal-Welch, causal
        x = sig_tr.to_numpy().ravel()
        ydm = (fwd_tr - bench_tr).to_numpy().ravel()                   # fwd minus own mean
        m = np.isfinite(x) & np.isfinite(ydm)
        if m.sum() < 2000:
            continue
        xx = x[m]
        denom = float(np.dot(xx, xx))
        b = float(np.dot(xx, ydm[m]) / denom) if denom > 0 else 0.0    # OLS through origin
        if b < 0:                                                       # sign-restrict (+): collapse
            b = 0.0
        slope_full = b                                                  # last fold's slope ≈ full-sample

        # OOS cross-section at d
        sig_d = signal.loc[d]
        fr = fwd.loc[d]
        bench_d = bench_tr.iloc[-1] if len(bench_tr) else pd.Series(dtype=float)  # per-name mean as-of
        elig = None if membership is None else _eligible(membership, d)
        names = sig_d.dropna().index
        if elig is not None:
            names = names.intersection(elig)
        rows = []
        for t in names:
            s_it, r_it = sig_d.get(t), fr.get(t)
            bm = bench_d.get(t) if hasattr(bench_d, "get") else np.nan
            if not (np.isfinite(s_it) and np.isfinite(r_it) and np.isfinite(bm)):
                continue
            rows.append((t, s_it, r_it, bm))
        if len(rows) < MIN_NAMES:
            continue
        _, s_arr, r_arr, b_arr = (np.array(z) for z in zip(*rows))
        f_arr = b_arr + b * s_arr                          # dispersed forecast
        f0_arr = b_arr + b * float(np.mean(s_arr))         # driver-only: same call, NO dispersion
        ics.append(V.rank_ic(pd.Series(s_arr), pd.Series(r_arr)))
        fadj_d.append(float(np.mean((r_arr - b_arr) ** 2 - (r_arr - f_arr) ** 2 + (b_arr - f_arr) ** 2)))
        ssef_d.append(float(np.mean((r_arr - f_arr) ** 2)))
        sseb_d.append(float(np.mean((r_arr - b_arr) ** 2)))
        ssef0_d.append(float(np.mean((r_arr - f0_arr) ** 2)))
        sseb0_d.append(float(np.mean((r_arr - b_arr) ** 2)))
        dates_used.append(d)
        # calibration pairs (pooled)
        sig_h = vol.loc[d]
        for t, s_it, r_it, bm in rows:
            sg = sig_h.get(t)
            if sg and np.isfinite(sg) and sg > 0:
                p_all.append(V._norm_cdf((b * s_it) / sg))
                y_all.append(1.0 if r_it > 0 else 0.0)

    n = len(dates_used)
    if n < 8:
        return {"error": f"too few OOS dates ({n})", "scored": False}
    hac = max(4, int(np.ceil(h / STEP)))
    ics = pd.Series(ics).dropna()
    ic_s = V.ic_summary(ics, periods_per_year=12)
    # pooled OOS-R² (per-date-aggregated SSE) + Clark-West on the per-date adj-term series
    oos_r2 = 1.0 - float(np.sum(ssef_d)) / float(np.sum(sseb_d)) if np.sum(sseb_d) else None
    oos_r2_bench = 1.0 - float(np.sum(ssef0_d)) / float(np.sum(sseb0_d)) if np.sum(sseb0_d) else None
    cw = V.newey_west_tstat(pd.Series(fadj_d), lags=hac)
    cw_t = cw.get("t")
    cw_p = (cw["p"] / 2.0 if (cw_t is not None and cw_t > 0)
            else (1.0 - cw["p"] / 2.0 if cw_t is not None else None))
    # split-half (both halves OOS-R²>0)
    mid = n // 2
    def _r2(a, bb):
        a, bb = np.array(a), np.array(bb)
        return 1.0 - a.sum() / bb.sum() if bb.sum() else None
    h1 = _r2(ssef_d[:mid], sseb_d[:mid]); h2 = _r2(ssef_d[mid:], sseb_d[mid:])
    half_ok = bool(h1 is not None and h2 is not None and h1 > 0 and h2 > 0)
    # calibration
    p_arr, y_arr = np.array(p_all), np.array(y_all)
    br = V.brier_reliability(p_arr, y_arr) if len(p_arr) >= 50 else {}
    pl = V.platt_fit(p_arr, y_arr) if len(p_arr) >= 50 else {}
    base, recal = br.get("base_brier"), pl.get("brier_recal")
    brier_recal = round(1 - recal / base, 3) if (recal is not None and base) else None
    # incremental-content guard: dispersed must beat the driver-only nested bench OOS
    beats_driver = bool(oos_r2 is not None and oos_r2_bench is not None and oos_r2 > oos_r2_bench)
    long_underpowered = bool(h >= 189)         # DFII10 starts 2003 (~23y) → <25y at 189td

    scored = bool(
        oos_r2 is not None and oos_r2 > 0
        and cw_p is not None and cw_p < 0.05
        and ic_s.get("ic_ir") is not None and ic_s["ic_ir"] > 0
        and ic_s.get("t_hac") is not None and ic_s["t_hac"] > 0 and ic_s.get("p_hac", 1) < 0.10
        and half_ok and beats_driver
        and (brier_recal is not None and brier_recal >= -0.01))
    return {
        "scored": scored, "n_oos_dates": n, "median_universe": int(np.median([len(ics)])) if ics is not None else 0,
        "pooled_slope": round(slope_full, 5) if slope_full is not None else None,
        "oos_r2": round(oos_r2, 5) if oos_r2 is not None else None,
        "oos_r2_driver_only": round(oos_r2_bench, 5) if oos_r2_bench is not None else None,
        "beats_driver_only": beats_driver,
        "cw_t": cw_t, "cw_p": round(cw_p, 4) if cw_p is not None else None,
        "ic_ir": ic_s.get("ic_ir"), "mean_ic": ic_s.get("mean_ic"), "ic_t_hac": ic_s.get("t_hac"),
        "ic_p_hac": ic_s.get("p_hac"), "half_r2": [h1, h2], "half_ok": half_ok,
        "brier_skill_recal": brier_recal, "platt": {"a": pl.get("a"), "b": pl.get("b", 0.0)},
        "long_underpowered": long_underpowered, "shrink": shrink,
        "span": f"{dates_used[0].date()}..{dates_used[-1].date()}", "label": label,
    }


def run(closes, *, shrink, membership, tag, relu=False) -> dict:
    signal = build_signal_panel(closes, shrink, relu=relu)
    out = {}
    for hname, h in nd.HORIZONS_TD.items():
        r = score_horizon(closes, signal, h, shrink=shrink, membership=membership,
                          label=f"{tag} {hname}")
        out[hname] = r
        print(f"\n=== {tag} {hname} ({h}td) — {r.get('n_oos_dates','?')} OOS dates "
              f"[{r.get('span','')}] ===")
        if r.get("error"):
            print(f"  skipped — {r['error']}")
            continue
        print(f"  pooled_slope={r['pooled_slope']} OOS-R²={r['oos_r2']} (driver-only {r['oos_r2_driver_only']}, "
              f"beats={r['beats_driver_only']}) CW p={r['cw_p']}")
        print(f"  IC-IR={r['ic_ir']} mean_ic={r['mean_ic']} IC t_HAC={r['ic_t_hac']} p={r['ic_p_hac']} "
              f"| half_ok={r['half_ok']} brier_recal={r['brier_skill_recal']} long_up={r['long_underpowered']} "
              f"-> {'SCORED' if r['scored'] else 'display-only'}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pit", action="store_true", help="also run the S&P-1500 PIT membership cross-check")
    ap.add_argument("--shrink", type=float, default=nd.NAME_SHRINK)
    ap.add_argument("--write-gate", action="store_true", help="write the NAME_DIRECTION gate block (GO on PIT)")
    args = ap.parse_args()

    closes = _closes_deep()
    if closes.empty:
        print("no deep close matrix — run `python3 -m scripts.residual_alpha_fetch` first")
        return 1
    print(f"[panel] DEEP {closes.shape} · {closes.index.min().date()}..{closes.index.max().date()} "
          f"· shrink {args.shrink}")

    deep = run(closes, shrink=args.shrink, membership=None, tag="DEEP")
    relu = run(closes, shrink=args.shrink, membership=None, tag="DEEP-ReLU", relu=True)  # sensitivity
    pit = {}
    if args.pit or args.write_gate:
        membership = _load_membership()
        if membership is None:
            print("no PIT membership (data/breadth/sp1500_pit_membership.parquet) — running deep-only")
        else:
            pit = run(closes, shrink=args.shrink, membership=membership, tag="PIT")

    # GO decision on PIT when available, else deep (clearly flagged). Default scored:false.
    decision = pit if pit else deep
    block = {"_meta": {"n_trials": N_TRIALS, "horizons_td": nd.HORIZONS_TD,
                       "driver": "real_rate", "beta_win": nd.NAME_BETA_WIN, "shrink": args.shrink,
                       "p_up_band": list(nd.NAME_P_BAND),
                       "decision_panel": "PIT (S&P-1500 membership)" if pit else "DEEP (survivorship-biased)",
                       "gate": "pooled OOS-R²>0 & CW q<0.05 & IC-IR HAC>0 & both-halves & beats-driver-only "
                               "& recal-Brier≥−0.01; BH across horizons; DSR/bootstrap=context",
                       "note": "macro-transmission overlay (real_rate); display-only until scored; shared block "
                               "for ALL names; default coin-flip; long horizon underpowered (DFII10 from 2003)"}}
    # BH-FDR across the 2 horizons on the CW p (the family is the 2 horizons of the 1 channel)
    cwps = {hn: decision[hn]["cw_p"] for hn in nd.HORIZONS_TD
            if decision.get(hn, {}).get("cw_p") is not None and not decision[hn].get("error")}
    bh = V.benjamini_hochberg(cwps, alpha=0.05)
    for hname in nd.HORIZONS_TD:
        r = decision.get(hname, {})
        if r.get("error"):
            block[hname] = {"scored": False, "error": r["error"]}
            continue
        q = (bh.get(hname) or {}).get("q")
        scored = bool(r.get("scored") and q is not None and q < 0.05)
        block[hname] = {
            "scored": scored, "pooled_slope": r["pooled_slope"] if scored else None,
            "platt": r["platt"] if scored else None, "p_up_band": list(nd.NAME_P_BAND),
            "oos_r2": r["oos_r2"], "oos_r2_driver_only": r["oos_r2_driver_only"],
            "cw_p": r["cw_p"], "cw_q": q, "ic_ir": r["ic_ir"], "ic_t_hac": r["ic_t_hac"],
            "brier_skill_recal": r["brier_skill_recal"], "beats_driver_only": r["beats_driver_only"],
            "half_ok": r["half_ok"], "long_underpowered": r["long_underpowered"],
            "n_oos_dates": r["n_oos_dates"], "span": r["span"],
            "deep_oos_r2": (deep.get(hname) or {}).get("oos_r2"),
            "relu_oos_r2": (relu.get(hname) or {}).get("oos_r2"),
        }

    _report(deep, pit, relu, block)
    if args.write_gate:
        gpath = REGIME / "anticipation_gate.json"
        full = json.loads(gpath.read_text()) if gpath.exists() else {}
        full["NAME_DIRECTION"] = block
        gpath.write_text(json.dumps(full, indent=2))
        print(f"\n[gate] wrote NAME_DIRECTION block to {gpath}")
    n_scored = sum(1 for hn in nd.HORIZONS_TD if block.get(hn, {}).get("scored"))
    print(f"\nWrote research/NAME_DIRECTION_PHASE0.md · NAME_DIRECTION scored horizons: {n_scored}")
    return 0


def _report(deep, pit, relu, block):
    L = ["# Single-Name Direction — Phase-0 (pooled macro-transmission)", "",
         "Does the validated real-rate edge transmit to single names OOS, as ONE pooled panel "
         "(not 1500 per-name fits)? Signal = shrunk(−beta to Δreal10) · the index_direction real_rate "
         "leg; shipped lean = b·signal (tilt around each name's own drift), validated as exactly that. "
         "Unit of inference = the per-DATE cross-section. A horizon is SCORED only if pooled OOS-R²>0 "
         "AND Clark-West BH-q<0.05 AND IC-IR HAC-t>0 AND both date-halves>0 AND it beats a driver-only "
         "(no-dispersion) bench AND P(up) is calibrated (recal Brier≥−0.01). GO decided on the PIT panel. "
         "DSR/bootstrap are context. Honest prior: this scores little or nothing (Goyal-Welch; "
         "Gu-Kelly-Xiu ~0.3–0.4% stock-level OOS-R² ceiling).", ""]
    def tbl(title, res):
        L.append(f"## {title}")
        L.append("")
        L.append("| horizon | OOS-R² | driver-only | CW p | IC-IR | IC t_HAC | both-halves | recal-Brier | verdict |")
        L.append("|---|--:|--:|--:|--:|--:|:--:|--:|:--:|")
        for hn in nd.HORIZONS_TD:
            r = res.get(hn, {})
            if r.get("error"):
                L.append(f"| {hn} | _skipped: {r['error']}_ | | | | | | | |")
                continue
            L.append(f"| {hn} | {r.get('oos_r2')} | {r.get('oos_r2_driver_only')} | {r.get('cw_p')} "
                     f"| {r.get('ic_ir')} | {r.get('ic_t_hac')} | {'yes' if r.get('half_ok') else 'no'} "
                     f"| {r.get('brier_skill_recal')} | {'**SCORED**' if r.get('scored') else 'display-only'} |")
        L.append("")
    if pit:
        tbl("PIT panel — S&P-1500 membership (decision panel)", pit)
    tbl("DEEP panel — survivorship-biased (power, optimistic)", deep)
    tbl("DEEP ReLU-duration sensitivity (positive-duration names only)", relu)
    scored = [hn for hn in nd.HORIZONS_TD if block.get(hn, {}).get("scored")]
    L += ["## Decision", "",
          f"Scored horizons (after BH across horizons, on the "
          f"{'PIT' if pit else 'DEEP'} panel): **{', '.join(scored) if scored else 'NONE — ships as coin-flip'}**.",
          "", "Every name defaults to the existing coin-flip; the already-validated risk cone is "
          "unaffected. A scored horizon ships a TIGHT (band 0.44–0.58), colored lean labeled a "
          "*validated macro-transmission overlay, not per-name alpha*.", ""]
    Path("research").mkdir(exist_ok=True)
    Path("research/NAME_DIRECTION_PHASE0.md").write_text("\n".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
