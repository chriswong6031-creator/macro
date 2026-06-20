"""P0 KILL-TEST (throwaway) — does the paper's textbook five-tier composite beat
the hand-tuned `composite_state` heuristic, out-of-sample, in BOTH halves?

Decision rule (from the design's P0 gate): the textbook composite, mapped to a
continuous exposure and run through the EXISTING backtest core at the configured
crypto cost, must beat the heuristic's documented **post-2021 net Sharpe of 0.65**
(and ideally win both halves). If it does NOT, STOP — do not build a live-sizing
composite; ship only the deterministic correctness fixes + a display-only scorecard.

This is deliberately a-priori: every factor is oriented by sign/economics only
(NO fitting to forward returns), scored to {-2..+2} from rolling-z with FIXED
cutoffs, weighted by the paper's tier weights, renormalized over present factors.
Revised (not PIT) FRED data is used here — that is UPWARD-biased for the macro
legs, so failing on revised data is a *decisive* kill (PIT can only be worse).

Run: python -m scripts.btc_regime_killtest
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import backtest_core  # noqa: E402
from lib import config  # noqa: E402

TRADING_YEAR = 365
SIGNALS_PARQUET = "data/vector/signals.parquet"

# Heuristic exposure map (identical to scripts.calibrate_vector._HEUR_EXPOSURE).
_HEUR_EXPOSURE = {"RISK-OFF": 0.0, "DISTRIBUTE": 0.25, "NEUTRAL": 0.5,
                  "RISK-ON": 0.75, "ACCUMULATE": 1.0}

# ---- a-priori scoring primitives ------------------------------------------- #
Z_WINDOW = 365
# the only tunable knobs in the whole composite — enumerated for the machine
# n_trials dry-count (every entry is ONE explored choice the DSR must deflate for):
CHOICE_LEDGER = [
    "z_window=365",
    "z_cut_+1.5->+2", "z_cut_+0.5->+1", "z_cut_-0.5->-1", "z_cut_-1.5->-2",
    "slope_lookback=20d",
    "trend_ma200d", "trend_ma200w=1400d", "trend_slope_lookback=20d",
    "hivix_credit_deepen@z>0.5",
    "expo_knot_10", "expo_knot_35", "expo_knot_65", "expo_knot_90",
    "expo_out_0.0/0.25/0.55/0.90/1.0",
    "min_factors_present=6",
]


def zc(s: pd.Series, n: int = Z_WINDOW) -> pd.Series:
    m = s.rolling(n, min_periods=max(60, n // 4))
    return (s - m.mean()) / m.std().replace(0, np.nan)


def score_z(z: pd.Series) -> pd.Series:
    """rolling-z -> {-2,-1,0,+1,+2} with FIXED a-priori cutoffs (un-oriented)."""
    out = pd.Series(np.nan, index=z.index)
    ok = z.notna()
    out[ok] = 0.0
    out[z > 0.5] = 1.0
    out[z > 1.5] = 2.0
    out[z < -0.5] = -1.0
    out[z < -1.5] = -2.0
    return out


def lvl_chg(level: pd.Series, want: int, already_z: bool = False, k: int = 20) -> pd.Series:
    """Average a LEVEL sub-score and a SLOPE (change) sub-score, then round and
    orient by `want`. Captures the paper's 'expanding-but-decelerating = +1 not +2'
    nuance for free (level + / slope - averages toward the middle)."""
    z_level = level if already_z else zc(level)
    lvl = score_z(z_level)
    chg = score_z(zc(level.diff(k)))
    raw = (lvl + chg) / 2.0
    return (want * raw).round()


def build_textbook_composite(df: pd.DataFrame) -> pd.DataFrame:
    """The paper's §3 five-tier composite, a-priori oriented, from existing columns.
    T3 (yield-curve regime, Fed path) is ABSENT in this parquet -> renormalized away
    per the design. Returns a frame with per-factor scores + index + exposure."""
    close = df["close"]
    sc = pd.DataFrame(index=df.index)

    # --- Tier 1: liquidity ---
    sc["t1_netliq"] = lvl_chg(df["net_liq_roc"], want=+1)          # w3
    sc["t1_m2"] = lvl_chg(df["global_m2_yoy"], want=+1)            # w2
    # --- Tier 2: rates / dollar ---
    sc["t2_real10y"] = lvl_chg(df["real_yield"], want=-1)         # w3
    sc["t2_dxy"] = lvl_chg(df["dxy"], want=-1)                    # w2
    # --- Tier 3: curve / Fed --- ABSENT (renormalized)
    # --- Tier 4: equity / VIX (state-switch aware) ---
    vix_s = -score_z(zc(df["vix"]))                               # high vix = bearish
    hy_s = -score_z(zc(df["hy_oas"]))                             # widening credit = bearish
    hivix = zc(df["vix"]) > 0.5
    t4 = vix_s.copy()
    # credit accelerant only bites in the high-vix regime (Lee EFM 2026)
    t4 = t4.where(~hivix, np.minimum(vix_s, hy_s))
    sc["t4_equity_vix"] = t4.round()                              # w2
    # --- Tier 5: crypto-native ---
    sc["t5_etf"] = lvl_chg(df["etf_flow_z"], want=+1, already_z=True)   # w3
    sc["t5_stbl"] = lvl_chg(df["stbl_growth_z"], want=+1, already_z=True)  # w1
    # trend vs 200D AND 200W with slope sign (the paper's trend axis, NOT extension)
    ma200 = close.rolling(200, min_periods=120).mean()
    ma200w = close.rolling(1400, min_periods=600).mean()
    ext_z = zc(close / ma200 - 1)
    slope = ma200.pct_change(20)
    tr = score_z(ext_z)
    tr = tr.where(slope >= 0, tr.clip(upper=0))   # falling 200d: cap positive
    tr = tr.where(slope <= 0, tr.clip(lower=0))    # rising 200d: cap negative
    tr = tr.mask((close < ma200w) & (slope < 0), -2)  # below down-sloping 200w = max bearish
    sc["t5_trend"] = tr                                            # w3
    sc["t5_onchain"] = (-score_z(zc(df["mvrv_z"]))).round()        # w2 (cheap=+, rich=-)

    weights = {"t1_netliq": 3, "t1_m2": 2, "t2_real10y": 3, "t2_dxy": 2,
               "t4_equity_vix": 2, "t5_etf": 3, "t5_stbl": 1, "t5_trend": 3,
               "t5_onchain": 2}
    w = pd.Series(weights)
    S = sc[list(weights)]
    present = S.notna()
    composite = (S.fillna(0) * w).sum(axis=1)
    wpresent = (present * w).sum(axis=1)
    idx = 50 + 50 * composite / (2 * wpresent)
    idx = idx.where(present.sum(axis=1) >= 6)  # need >=6 factors live
    sc["composite"] = composite
    sc["w_present"] = wpresent
    sc["index"] = idx.clip(0, 100)
    sc["exposure"] = exposure_map(sc["index"])
    return sc


def exposure_map(index: pd.Series) -> pd.Series:
    """Piecewise-linear, a-priori knots (design §6). NOT an ECDF (no fit)."""
    x = index.to_numpy(dtype=float)
    knots_x = [0, 10, 35, 65, 90, 100]
    knots_y = [0.0, 0.0, 0.25, 0.55, 0.90, 1.0]
    y = np.interp(x, knots_x, knots_y, left=0.0, right=1.0)
    out = pd.Series(y, index=index.index)
    out[index.isna()] = np.nan
    return out


# ---- backtest plumbing (matches calibrate_vector.ensemble_promotion) -------- #
def net_sharpe(close: pd.Series, expo: pd.Series, idx, cost_bps: float) -> float:
    e = expo.reindex(idx).ffill()
    c = close.reindex(idx)
    net = backtest_core(c, e, cost_bps=cost_bps)["net"].dropna()
    sd = net.std()
    return round(float(net.mean() / sd * np.sqrt(TRADING_YEAR)), 2) if sd else float("nan")


def main() -> int:
    cal = config.load()["vector"]["calibration"]
    cost_bps = float(cal.get("cost_bps", 10))
    start, split = cal["start_date"], cal["split_date"]
    horizons = cal["forward_days"]
    embargo = int(max(horizons))

    df = pd.read_parquet(SIGNALS_PARQUET).loc[start:].copy()
    close = df["close"]
    sc = build_textbook_composite(df)

    # exposures, lagged 1d (no look-ahead; close-based signals act on shift(1))
    expo_textbook = sc["exposure"].shift(1)
    expo_heur = df["composite_state"].map(_HEUR_EXPOSURE).shift(1)

    _pre = df.index[df.index < split]
    halves = {
        "full": df.index,
        "pre": _pre[:-embargo] if len(_pre) > embargo else _pre,
        "post": df.index[df.index >= split],
    }

    rows = {}
    for name, e in {"textbook_composite": expo_textbook, "heuristic": expo_heur}.items():
        rows[name] = {h: net_sharpe(close, e, idx, cost_bps) for h, idx in halves.items()}

    print("=" * 70)
    print("P0 KILL-TEST — textbook five-tier composite vs heuristic composite_state")
    print(f"span {df.index.min().date()}..{df.index.max().date()}  rows={len(df)}  "
          f"split={split}  cost={cost_bps}bps  (embargo {embargo}d)")
    print("=" * 70)
    print(f"{'strategy':22s} {'full':>8s} {'pre':>8s} {'post':>8s}")
    for name, r in rows.items():
        print(f"{name:22s} {r['full']:8.2f} {r['pre']:8.2f} {r['post']:8.2f}")
    print("-" * 70)

    tb, hu = rows["textbook_composite"], rows["heuristic"]
    legs = ["pre", "post"]
    beats_both = all(tb[h] > hu[h] for h in legs)
    beats_bar = tb["post"] > 0.65
    n_present = int(sc[[c for c in sc.columns if c.startswith(("t1", "t2", "t4", "t5"))]]
                    .notna().any().sum())
    print(f"factors live: {n_present}/9 (T3 curve/Fed absent in this parquet, renormalized)")
    print(f"machine n_trials dry-count: {len(CHOICE_LEDGER)} a-priori choices")
    print(f"  -> {', '.join(CHOICE_LEDGER)}")
    print("-" * 70)
    print(f"beats heuristic in BOTH halves? {beats_both}")
    print(f"clears the 0.65 post-2021 bar?   {beats_bar}  (textbook post = {tb['post']})")
    verdict = ("PROCEED — composite shows OOS edge; build the live-sizing path"
               if (beats_both and beats_bar) else
               "KILL — composite does NOT beat the heuristic; ship fixes + DISPLAY-ONLY scorecard")
    print("=" * 70)
    print(f"VERDICT: {verdict}")
    print("=" * 70)

    # exposure-map robustness: report a continuous linear map too (sanity, not a 2nd trial)
    expo_lin = (sc["index"] / 100.0).shift(1)
    lin = {h: net_sharpe(close, expo_lin, idx, cost_bps) for h, idx in halves.items()}
    print(f"(sanity) linear index/100 exposure: full={lin['full']} pre={lin['pre']} post={lin['post']}")

    # current readout sanity
    last = sc.dropna(subset=["index"]).iloc[-1]
    print(f"(current) {df.index[-1].date()}: index={last['index']:.0f} "
          f"exposure={last['exposure']:.2f}  scores=" +
          ", ".join(f"{k}={last[k]:+.0f}" for k in
                    ["t1_netliq", "t1_m2", "t2_real10y", "t2_dxy", "t4_equity_vix",
                     "t5_etf", "t5_stbl", "t5_trend", "t5_onchain"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
