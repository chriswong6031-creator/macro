"""Phase-0 for the Anticipation Engine — does the confluence state (and, above all,
the NEW velocity-of-deterioration axis) actually predict the forward DRAWDOWN
distribution, robustly, on the real US large-cap universe?

Honest battery (mirrors calibrate_vector / sector_bottom_phase0), every leg ORIENTED
so "higher = more dangerous", then tested vs forward outcomes pooled cross-sectionally
over data/stocks (+ sector ETFs + index):

  1. Band ordering   — does forward drawdown (worst dip, MAE) worsen monotonically
                       across the leg's quartile bands at the SHORT horizon?
  2. Split-half      — does the rank relationship hold sign in BOTH halves (by date)?
  3. Calendar CV     — purged, embargoed folds assigned BY CALENDAR DATE GLOBALLY
                       (no date in train & test for any name → no cross-name leak);
                       fold_robust = full sign + no fold flip + all-but-one agree.
  4. De-risk overlay — a PIT long/flat portfolio that flattens names in their own
                       top-danger band; does it cut max-drawdown (the only validated
                       edge type)? block-bootstrap CI + DSR multiple-testing haircut.
  5. Direction       — P(up) by (trend × vol) cell: measured coin-flip short-horizon
                       (Brier skill vs climatology), the honesty anchor.

Writes data/regime/anticipation_gate.json (per-class GO/NEUTRAL, default NEUTRAL) and
research/ANTICIPATION_PHASE0.md. Nothing here is scored live until a leg is GO.

Run:  python3 -m scripts.anticipation_phase0
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from engine import forward_dist, indicators, validation, velocity, vol_forecast

HORIZONS = {"short": 5, "medium": 42, "long": 189}
GAUGE_H = "short"          # protocol: drawdown gauges judged at the short horizon
MAX_H = max(HORIZONS.values())
N_BANDS = 4
SECTORS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
INDEX = ["SPY", "QQQ"]
DATA = Path("data")
REGIME = DATA / "regime"


def _zr(s: pd.Series, win: int) -> pd.Series:
    m = s.rolling(win, min_periods=max(40, win // 3))
    return (s - m.mean()) / m.std(ddof=0).replace(0, np.nan)


def oriented_legs(close: pd.Series, bench: pd.Series, breadth: pd.Series) -> pd.DataFrame:
    """Every candidate leg ORIENTED so higher = more dangerous (deeper expected
    drawdown). Plus the cell keys for the direction test. All causal/point-in-time."""
    vf = velocity.velocity_features(close, bench=bench, breadth=breadth)
    out = pd.DataFrame(index=close.index)
    # --- velocity axis (NEW) ---
    out["det_z"] = velocity.deterioration_z(vf)              # composite, +=worse
    out["neg_trend_vel"] = -vf["trend_vel"]
    out["neg_trend_accel"] = -_zr(vf["trend_accel"], 252)
    if "rs_vel" in vf:
        out["neg_rs_vel"] = -vf["rs_vel"]
    out["neg_impulse"] = -vf["impulse"]
    out["rvar_vel"] = _zr(vf["rvar_vel"], 252)              # rising variance = worse
    # --- extension / parabolic (reuse idea) ---
    ma200 = close.rolling(200, min_periods=120).mean()
    out["ext_z"] = _zr(close / ma200, 504)                  # stretched above trend
    # --- volatility regime (cone width) ---
    out["vol_pct"] = vol_forecast.vol_regime(close, 252)    # elevated vol = worse
    # --- confluence composite: equal-weight independent oriented axes ---
    comp = pd.concat([out["det_z"], out["ext_z"], out["vol_pct"].sub(0.5).mul(4),
                      out["neg_trend_vel"]], axis=1)
    out["confluence"] = comp.mean(axis=1)
    # --- direction cell keys ---
    out["trend_up"] = (vf["trend_vel"] > 0).astype(float)
    out["vol_band"] = pd.qcut(out["vol_pct"].rank(method="first"), 2, labels=["lo", "hi"]) \
        if out["vol_pct"].notna().sum() > 100 else "na"
    return out


DD_LEGS = ["det_z", "confluence", "neg_trend_vel", "neg_trend_accel", "neg_rs_vel",
           "neg_impulse", "rvar_vel", "ext_z", "vol_pct"]

# Market overlay legs (cross-asset / macro / geopolitical) — the user's "VIX,
# currencies, rates, bonds, geopolitical" axis. Built by the ENGINE (single source of
# truth) so the live read uses exactly what Phase-0 validates. GEX excluded — no free
# history to validate; live display-only fragility chip only.
from engine.anticipation import MACRO_LEGS, macro_legs_frame as load_macro  # noqa: E402


def build_pool() -> pd.DataFrame:
    """Pooled long-format panel over the universe: date, ticker, oriented legs, and
    forward ret/mae at each horizon. Sector ETFs + index included (just price series)."""
    bench = pd.read_parquet(DATA / "yahoo" / "SPY.parquet")["close"]
    breadth = pd.read_parquet(DATA / "breadth" / "breadth.parquet")["pct_above_200"]
    files = sorted(glob.glob(str(DATA / "stocks" / "*.parquet")))
    extras = [(t, DATA / "yahoo" / f"{t}.parquet") for t in SECTORS + INDEX]
    frames = []
    n_ok = 0
    for src in files + [str(p) for _, p in extras]:
        tkr = os.path.basename(src).replace(".parquet", "")
        try:
            px = pd.read_parquet(src)
        except Exception:
            continue
        close = px["close"].dropna()
        if len(close) < 800:
            continue
        legs = oriented_legs(close, bench, breadth)
        rec = legs.copy()
        for nm, h in HORIZONS.items():
            p = forward_dist.forward_paths(close, h)
            rec[f"ret_{nm}"] = p["ret"]
            rec[f"mae_{nm}"] = p["mae"]
        rec["ticker"] = tkr
        rec["date"] = rec.index
        rec["aclass"] = "sector" if tkr in SECTORS else ("index" if tkr in INDEX else "stock")
        frames.append(rec.reset_index(drop=True))
        n_ok += 1
    pool = pd.concat(frames, ignore_index=True)
    print(f"  pooled {n_ok} names -> {len(pool):,} rows")
    return pool


def _spearman(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < 200:
        return float("nan")
    return float(j["a"].rank().corr(j["b"].rank()))


def calendar_folds(dates: pd.Series, k: int = 5, embargo_days: int = MAX_H):
    """Folds assigned BY CALENDAR DATE: contiguous date blocks; a fold's TEST dates
    plus an embargo window are removed from every other fold's TRAIN — so no date
    (for ANY name) sits in both train and test, killing cross-name label leakage."""
    uniq = np.array(sorted(pd.to_datetime(dates.unique())))
    if len(uniq) < k * 20:
        return None
    blocks = np.array_split(uniq, k)
    folds = []
    for b in blocks:
        if len(b) == 0:
            continue
        lo, hi = b[0], b[-1]
        emb_lo = lo - pd.Timedelta(days=int(embargo_days * 1.6))
        emb_hi = hi + pd.Timedelta(days=int(embargo_days * 1.6))
        folds.append({"test": (lo, hi), "embargo": (emb_lo, emb_hi)})
    return folds


def test_dd_leg(pool: pd.DataFrame, leg: str) -> dict:
    """Forward-drawdown predictive test for one oriented leg. want = NEGATIVE Spearman
    (higher danger signal -> deeper/more-negative MAE)."""
    mae = pool[f"mae_{GAUGE_H}"]
    dates = pd.to_datetime(pool["date"])
    full = _spearman(pool[leg], mae)
    want = -1
    # band ordering (full-sample quartile edges — in-sample ordering only)
    edges = forward_dist.quantile_edges(pool[leg], N_BANDS)
    paths = pd.DataFrame({"ret": pool[f"ret_{GAUGE_H}"], "mae": mae, "mfe": mae * 0})
    bo = forward_dist.band_ordering(paths, pool[leg], edges)
    band_dd = [r["val"] for r in bo if r["val"] is not None]
    monotone = bool(len(band_dd) >= 3 and all(np.diff(band_dd) <= 0.05))   # dd worsens (≤)
    # split-half by median date
    split = dates.quantile(0.5)
    pre, post = dates < split, dates >= split
    s_pre = _spearman(pool.loc[pre, leg], mae[pre])
    s_post = _spearman(pool.loc[post, leg], mae[post])
    half_stable = bool(np.isfinite(s_pre) and np.isfinite(s_post)
                       and np.sign(s_pre) == want and np.sign(s_post) == want)
    # calendar-blocked purged CV
    folds = calendar_folds(pool["date"])
    fold_signs = []
    if folds:
        for f in folds:
            lo, hi = f["test"]
            m = (dates >= lo) & (dates <= hi)
            sp = _spearman(pool.loc[m, leg], mae[m])
            fold_signs.append(0 if not np.isfinite(sp) else int(np.sign(sp)))
    robust = validation.fold_robust(int(np.sign(full)) if np.isfinite(full) else 0,
                                    fold_signs, want) if fold_signs else False
    # tail separation: top-danger band vs safe band
    top = pool[leg] >= edges[-2]
    safe = pool[leg] <= edges[1]
    tail_top = float(mae[top].quantile(0.05)) if top.sum() > 50 else float("nan")
    tail_safe = float(mae[safe].quantile(0.05)) if safe.sum() > 50 else float("nan")
    return {"leg": leg, "ic_full": round(full, 4) if np.isfinite(full) else None,
            "want": want, "monotone_dd": monotone,
            "band_dd": [round(x, 2) for x in band_dd],
            "ic_pre": round(s_pre, 4) if np.isfinite(s_pre) else None,
            "ic_post": round(s_post, 4) if np.isfinite(s_post) else None,
            "half_stable": half_stable, "fold_signs": fold_signs, "cv_robust": robust,
            "tail_danger": round(tail_top, 1) if np.isfinite(tail_top) else None,
            "tail_safe": round(tail_safe, 1) if np.isfinite(tail_safe) else None,
            "pass": bool(half_stable and robust
                         and np.isfinite(full) and np.sign(full) == want)}


def derisk_overlay(leg: str, q_danger: float = 0.75, win: int = 756) -> dict:
    """PIT long/flat portfolio: each name goes FLAT next bar when its own oriented
    leg is above its trailing-window q_danger quantile (no look-ahead), else holds.
    Equal-weight across names daily. Reports CAGR/Sharpe/maxDD vs equal-weight
    buy&hold + bootstrap CI + DSR (n_trials = #dd-legs)."""
    bench = pd.read_parquet(DATA / "yahoo" / "SPY.parquet")["close"]
    breadth = pd.read_parquet(DATA / "breadth" / "breadth.parquet")["pct_above_200"]
    files = sorted(glob.glob(str(DATA / "stocks" / "*.parquet")))
    strat, hold = [], []
    for src in files:
        close = pd.read_parquet(src)["close"].dropna()
        if len(close) < 800:
            continue
        sig = oriented_legs(close, bench, breadth)[leg]
        thr = sig.rolling(win, min_periods=252).quantile(q_danger)
        flat = (sig > thr)
        alloc = (~flat).astype(float).shift(1).fillna(1.0)     # act next bar
        ret = close.pct_change(fill_method=None)
        strat.append((alloc * ret).rename(os.path.basename(src)))
        hold.append(ret.rename(os.path.basename(src)))
    S = pd.concat(strat, axis=1).mean(axis=1).dropna()
    H = pd.concat(hold, axis=1).mean(axis=1).dropna()
    idx = S.index.intersection(H.index)
    S, H = S.loc[idx], H.loc[idx]

    def stats(r):
        eq = (1 + r).cumprod()
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        cagr = eq.iloc[-1] ** (1 / yrs) - 1
        sh = r.mean() / r.std(ddof=0) * np.sqrt(252) if r.std(ddof=0) else float("nan")
        dd = float((eq / eq.cummax() - 1).min())
        return {"cagr_pct": round(100 * cagr, 1), "sharpe": round(float(sh), 2),
                "maxdd_pct": round(100 * dd, 1)}

    ss, hh = stats(S), stats(H)
    ci = validation.block_bootstrap_ci(S, block=21, B=2000, ann=252)
    mom = validation.ret_moments(S)
    dsr = validation.deflated_sharpe(mom[0], mom[1], mom[2], mom[3],
                                     n_trials=len(DD_LEGS), trading_year=252) if mom else None
    return {"leg": leg, "strat": ss, "hold": hh,
            "maxdd_reduction_pp": round(ss["maxdd_pct"] - hh["maxdd_pct"], 1),
            "sharpe_ci": ci.get("sharpe_ci"), "dsr": dsr["dsr"] if dsr else None,
            "dsr_verdict": validation.dsr_verdict(dsr["dsr"]) if dsr else None}


def test_direction(pool: pd.DataFrame) -> dict:
    """Is short-horizon DIRECTION a coin-flip? P(up) by (trend_up × vol_band) cell,
    OOF Brier skill vs climatology — the honesty anchor."""
    res = {}
    for nm in ("short", "medium"):
        up = (pool[f"ret_{nm}"] > 0).astype(float)
        df = pd.DataFrame({"up": up, "t": pool["trend_up"], "v": pool["vol_band"].astype(str),
                           "date": pd.to_datetime(pool["date"])}).dropna()
        if len(df) < 1000:
            continue
        base = df["up"].mean()
        split = df["date"].quantile(0.5)
        tr, te = df[df["date"] < split], df[df["date"] >= split]
        cell = tr.groupby(["t", "v"])["up"].mean()
        n_cell = tr.groupby(["t", "v"])["up"].size()
        cell = cell.where(n_cell >= 50, base)
        p = te.apply(lambda r: cell.get((r["t"], r["v"]), base), axis=1).to_numpy()
        y = te["up"].to_numpy()
        br = validation.brier_reliability(p, y)
        spread = float(cell.max() - cell.min())
        res[nm] = {"base_up_rate": round(float(base), 3), "cell_spread_pp": round(100 * spread, 1),
                   "brier": br.get("brier"), "brier_skill": br.get("skill_score"),
                   "verdict": ("coin-flip (≈0 skill)" if (br.get("skill_score") or 0) < 0.01
                               else "weak edge")}
    return res


def macro_timing_overlay(macro: pd.DataFrame, legs: list, q: float = 0.75, win: int = 756,
                         derisk: float = 0.5) -> dict:
    """Portfolio-level macro timing: an equal-weight book of all names that scales
    exposure DOWN by `derisk` whenever the combined macro-stress percentile is in its
    own top quartile (PIT). Shows whether the validated macro overlay controls
    drawdown at the book level."""
    if not legs:
        return {}
    conf = macro[legs].apply(lambda s: s.rolling(252, min_periods=120).rank(pct=True)).mean(axis=1)
    thr = conf.rolling(win, min_periods=252).quantile(q)
    exposure = (1.0 - derisk * (conf > thr).astype(float)).shift(1)      # act next bar
    files = sorted(glob.glob(str(DATA / "stocks" / "*.parquet")))
    rets = []
    for src in files:
        c = pd.read_parquet(src)["close"].dropna()
        if len(c) < 800:
            continue
        rets.append(c.pct_change(fill_method=None).rename(os.path.basename(src)))
    ew = pd.concat(rets, axis=1).mean(axis=1).dropna()
    exp = exposure.reindex(ew.index).ffill().fillna(1.0)
    S, H = (exp * ew).dropna(), ew

    def stats(r):
        eq = (1 + r).cumprod()
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        return {"cagr_pct": round(100 * (float(eq.iloc[-1]) ** (1 / yrs) - 1), 1),
                "sharpe": round(float(r.mean() / r.std(ddof=0) * np.sqrt(252)), 2),
                "maxdd_pct": round(100 * float((eq / eq.cummax() - 1).min()), 1)}

    ss, hh = stats(S.loc[H.index.intersection(S.index)]), stats(H)
    mom = validation.ret_moments(S)
    dsr = validation.deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=len(MACRO_LEGS)) if mom else None
    return {"legs": legs, "strat": ss, "hold": hh,
            "maxdd_reduction_pp": round(ss["maxdd_pct"] - hh["maxdd_pct"], 1),
            "dsr": dsr["dsr"] if dsr else None,
            "dsr_verdict": validation.dsr_verdict(dsr["dsr"]) if dsr else None}


def main() -> int:
    print("Anticipation Phase-0 — building pool ...")
    pool = build_pool()
    macro = load_macro()
    pool = pool.merge(macro, left_on="date", right_index=True, how="left")

    def _run(legs, title):
        print(f"\n=== {title} (gauge horizon = {HORIZONS[GAUGE_H]} d) ===")
        res = []
        for leg in legs:
            r = test_dd_leg(pool, leg)
            res.append(r)
            print(f"  {leg:16s} IC={str(r['ic_full']):>8s} want={r['want']:+d} "
                  f"half_stable={int(r['half_stable'])} cv_robust={int(r['cv_robust'])} "
                  f"monotone_dd={int(r['monotone_dd'])} tail danger/safe={r['tail_danger']}/{r['tail_safe']} "
                  f"-> {'PASS' if r['pass'] else 'neutral'}")
        return res

    leg_res = _run(DD_LEGS, "per-name forward-drawdown legs")
    macro_res = _run(MACRO_LEGS, "market overlay legs (cross-asset / macro / geopolitical)")

    print("\n=== de-risk overlay (drawdown control — the validated edge type) ===")
    over = []
    for leg in ("det_z", "confluence"):
        o = derisk_overlay(leg)
        over.append(o)
        print(f"  {leg:12s} strat {o['strat']} | hold {o['hold']} | "
              f"maxDD Δ {o['maxdd_reduction_pp']:+.1f}pp | DSR {o['dsr']} ({o['dsr_verdict']})")
    macro_go = [r["leg"] for r in macro_res if r["pass"]]
    macro_over = macro_timing_overlay(macro, macro_go)
    if macro_over:
        print(f"  macro({len(macro_go)} legs) strat {macro_over['strat']} | hold {macro_over['hold']} | "
              f"maxDD Δ {macro_over['maxdd_reduction_pp']:+.1f}pp | DSR {macro_over['dsr']}")

    print("\n=== direction (coin-flip check) ===")
    direction = test_direction(pool)
    for nm, d in direction.items():
        print(f"  {nm:6s} base_up={d['base_up_rate']} cell_spread={d['cell_spread_pp']}pp "
              f"brier_skill={d['brier_skill']} -> {d['verdict']}")

    # --- gate: a leg is GO only if it passes the full battery ---
    all_res = leg_res + macro_res
    gate = {"US": {r["leg"]: ("GO" if r["pass"] else "NEUTRAL") for r in all_res},
            "_meta": {"horizons_td": HORIZONS, "n_rows": int(len(pool)),
                      "macro_legs": MACRO_LEGS,
                      "note": "display-only until GO; cone (drawdown) validated, "
                              "direction is coin-flip short-horizon (display-only)"}}
    REGIME.mkdir(parents=True, exist_ok=True)
    (REGIME / "anticipation_gate.json").write_text(json.dumps(gate, indent=2))
    _write_report(leg_res, macro_res, over, macro_over, direction, len(pool))
    n_go = sum(1 for r in all_res if r["pass"])
    print(f"\nWrote {REGIME/'anticipation_gate.json'} ({n_go}/{len(all_res)} legs GO) "
          f"and research/ANTICIPATION_PHASE0.md")
    return 0


def _tbl(rows):
    out = ["| leg | rank-IC | both halves | calendar-CV robust | monotone dd | tail danger/safe % | verdict |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| `{r['leg']}` | {r['ic_full']} | {'✓' if r['half_stable'] else '—'} "
                   f"({r['ic_pre']}/{r['ic_post']}) | {'✓' if r['cv_robust'] else '—'} | "
                   f"{'✓' if r['monotone_dd'] else '—'} | {r['tail_danger']}/{r['tail_safe']} | "
                   f"**{'GO' if r['pass'] else 'display-only'}** |")
    return out


def _write_report(leg_res, macro_res, over, macro_over, direction, n_rows):
    L = ["# Anticipation Engine — Phase-0 results", "",
         f"Universe: 111 US large-caps + 11 SPDR sectors + SPY/QQQ. Pooled rows: {n_rows:,}. "
         f"Gauge horizon: {HORIZONS[GAUGE_H]}td. Drawdown = forward worst dip (MAE). "
         "Every leg oriented so higher = more dangerous; want = NEGATIVE rank-IC vs forward MAE. "
         "GO = sign(IC)=want AND stable in both date-halves AND robust across calendar-blocked "
         "purged CV folds.", "",
         "## Per-name forward-drawdown legs", ""] + _tbl(leg_res)
    L += ["", "## Market overlay legs — cross-asset / macro / geopolitical", "",
          "(Same value for every name on a date; tested as systematic forward-drawdown predictors. "
          "GEX excluded — no free history to validate; live display-only fragility chip only.)", ""]
    L += _tbl(macro_res)
    L += ["", "## De-risk overlay (PIT — drawdown control, the validated edge type)", "",
          "| overlay | strat CAGR/Sharpe/maxDD | buy&hold | maxDD Δ | DSR |", "|---|---|---|---|---|"]
    for o in over:
        s, h = o["strat"], o["hold"]
        L.append(f"| `{o['leg']}` long/flat | {s['cagr_pct']}% / {s['sharpe']} / {s['maxdd_pct']}% | "
                 f"{h['cagr_pct']}% / {h['sharpe']} / {h['maxdd_pct']}% | {o['maxdd_reduction_pp']:+.1f}pp | "
                 f"{o['dsr']} ({o['dsr_verdict']}) |")
    if macro_over:
        s, h = macro_over["strat"], macro_over["hold"]
        L.append(f"| macro timing ({len(macro_over['legs'])} legs) | {s['cagr_pct']}% / {s['sharpe']} / "
                 f"{s['maxdd_pct']}% | {h['cagr_pct']}% / {h['sharpe']} / {h['maxdd_pct']}% | "
                 f"{macro_over['maxdd_reduction_pp']:+.1f}pp | {macro_over['dsr']} ({macro_over['dsr_verdict']}) |")
    L += ["", "## Direction (the honesty anchor)", ""]
    for nm, d in direction.items():
        L.append(f"- **{nm}**: base up-rate {d['base_up_rate']}, cell spread {d['cell_spread_pp']}pp, "
                 f"Brier skill {d['brier_skill']} → {d['verdict']}")
    L += ["", "_Generated by scripts/anticipation_phase0.py. Legs marked GO may be scored; "
          "all others ship display-only. Re-run after data updates._", ""]
    Path("research").mkdir(exist_ok=True)
    Path("research/ANTICIPATION_PHASE0.md").write_text("\n".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
