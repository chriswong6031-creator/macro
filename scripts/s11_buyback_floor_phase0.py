"""W5 S11 phase-0 — Buyback-Floor Washout (US quarterly EDGAR × baskets panel).

Pre-registration: research/species/W5_S11_PREREG.md (committed BEFORE this run;
trial family `s11_buyback_floor`, m=2 configs: share_decline ∈ {any_decline (<0),
material_decline (≤ −1%)}).  Everything else is FIXED — any new knob is a new
§8-recorded trial.

Construction (per prereg):
  * Fundamentals: data/edgar/statements_quarterly.parquet (debt columns added
    2026-07-06).  Trigger = realized QoQ share-count decline between consecutive
    ~1-quarter fiscal periods (period_end gap ∈ [60,130] days; Q4 is ~absent in
    EDGAR so QoQ is within-year Q1→Q2 / Q2→Q3 — a coverage bound, printed).
  * PIT fire date = the `filed` date (the only date the share-count AND net-debt
    are public).  Washout arming = engine.coiled.washout_ctx(close[:filed]).
    Fill = first close strictly after `filed` (grading.fill_index next-bar).
  * Debt-funded demotion: a fire with Δnet_debt > 0 (net debt rising concurrent
    with the buyback) is demoted to a context bucket B, excluded from arm A.
  * Panel: data/baskets/ohlcv/{ticker}.parquet (split-adjusted; current-membership
    survivorship bias printed, not fixed).
  * Grade: grading.terminal_state at clean15_126 (positional primary) +
    grading.cushion_incidence (competing-risk cushion @ {5,10,21}).

Three-way partition of washout-at-`filed` fires (per config):
  A  clean fire   = washout ∧ (share decline) ∧ ¬(Δnet_debt > 0)   [primary]
  B  debt-funded  = washout ∧ (share decline) ∧ (Δnet_debt > 0)    [context]
  C  control      = washout ∧ (Δshares ≥ 0)                        [primary control]

Verdict (registered): A vs C at clean15_126 on stop-out (↓) / dead-money (↓) /
cushion-incidence@21 (↑); episode-clustered p (6-month circular block bootstrap,
B=2000) + BH-FDR q≤0.10 (family m=2); Wilson LBs; ≥5pp stop-out spread; n≥300/side;
both halves sign-stable; per-name majority.  Returns printed as context only.

Usage:
  python -m scripts.s11_buyback_floor_phase0
Output: research/species/_s11_phase0_out.json + stdout tables.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import grading                          # noqa: E402
from engine.grading_stats import wilson_ci          # noqa: E402
from engine.validation import benjamini_hochberg    # noqa: E402
from engine.coiled import washout_ctx               # noqa: E402
from engine.trial_ledger import register_trials     # noqa: E402
from lib import config                              # noqa: E402

PANEL_DIR = config.data_dir() / "baskets" / "ohlcv"
EDGAR_STORE = config.data_dir() / "edgar" / "statements_quarterly.parquet"
OUT = Path("research/species/_s11_phase0_out.json")

QOQ_MIN, QOQ_MAX = 60, 130      # consecutive ~1-quarter period_end gap (days)
MATERIAL_THRESH = -0.01         # trial 2: material share decline (≤ −1%)
B_BOOT = 2000
RNG = np.random.default_rng(11)
MIN_EPISODES = 8                # ≥8 half-year blocks for the episode bootstrap
FAMILY = "s11_buyback_floor"
CONFIGS = {"any_decline": 0.0, "material_decline": MATERIAL_THRESH}  # d_shares threshold

_close_cache: dict[str, pd.Series | None] = {}


def _close(tk: str) -> pd.Series | None:
    if tk not in _close_cache:
        fp = PANEL_DIR / f"{tk}.parquet"
        try:
            _close_cache[tk] = pd.read_parquet(fp)["close"].dropna().sort_index()
        except Exception:  # noqa: BLE001
            _close_cache[tk] = None
    return _close_cache[tk]


def _half(ts: pd.Timestamp) -> str:
    """6-calendar-month episode block label (≥126-day forward window per §1.2)."""
    return f"{ts.year}H{1 if ts.month <= 6 else 2}"


def build_events(edgar: pd.DataFrame) -> pd.DataFrame:
    """All washout-at-`filed` transitions, graded once at clean15_126.

    One row per (ticker, consecutive ~1Q transition) where washout_ctx is True at
    the filing date and the fire has matured (126 forward bars).  Threshold-
    independent: config partitioning happens in evaluate().
    """
    edgar = edgar.copy()
    edgar["period_end"] = pd.to_datetime(edgar["period_end"])
    edgar["filed"] = pd.to_datetime(edgar["filed"])
    rows = []
    n_tickers = n_washout = n_matured = 0
    for tk, g in edgar.sort_values("period_end").groupby("ticker"):
        close = _close(tk)
        if close is None or len(close) < 434:      # 308 washout + 126 forward
            continue
        n_tickers += 1
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            prev, cur = g.iloc[i - 1], g.iloc[i]
            gap = (cur["period_end"] - prev["period_end"]).days
            if not (QOQ_MIN <= gap <= QOQ_MAX):
                continue
            s0, s1 = prev["shares"], cur["shares"]
            if pd.isna(s0) or pd.isna(s1) or not s0:
                continue
            filed = cur["filed"]
            if pd.isna(filed) or filed <= close.index[0] or filed >= close.index[-1]:
                continue
            # washout arming as of the filing date (causal; data ≤ filed only)
            if washout_ctx(close.loc[:filed]) is not True:
                continue
            n_washout += 1
            # grade once at clean15_126 (positional primary); next-bar fill from filed
            ts = grading.terminal_state(close, filed, liftoff_mult=grading.LIFTOFF_15,
                                        liftoff_horizon=grading.LIFTOFF_HORIZON_126)
            state = ts.get("state")
            if state is None:                       # unmatured → drop (no look-ahead)
                continue
            n_matured += 1
            d_shares = float(s1) / float(s0) - 1.0
            nd0, nd1 = prev.get("net_debt"), cur.get("net_debt")
            nd_known = pd.notna(nd0) and pd.notna(nd1)
            d_net_debt = (float(nd1) - float(nd0)) if nd_known else np.nan
            rows.append({
                "ticker": tk, "sig_date": filed, "d_shares": d_shares,
                "d_net_debt": d_net_debt, "nd_known": bool(nd_known),
                "state": str(state),
                "stopped": int(str(state) == "STOPPED"),
                "dead": int(str(state) == "DEAD_MONEY"),
                "cushioned": int(str(state) == "CUSHIONED"),
                "clean": int(str(state) == "CLEAN_LIFTOFF"),
                "ret": ts.get("ret_at_read"),
            })
    df = pd.DataFrame(rows)
    print(f"events: {n_tickers} tickers priced, {n_washout} washout-at-filed, "
          f"{n_matured} matured (126d) → {len(df)} graded fires", flush=True)
    return df


def _rates(df: pd.DataFrame) -> dict:
    """Terminal-state rates + Wilson 95% LB/UB on the safety axes."""
    n = len(df)
    if not n:
        return {"n": 0}
    out = {"n": n}
    for axis in ("stopped", "dead", "cushioned", "clean"):
        k = int(df[axis].sum())
        pct = round(100 * k / n, 2)
        w = wilson_ci(k, n)
        out[axis] = pct
        out[f"{axis}_wilson"] = ([round(100 * x, 2) for x in w] if w else None)
    r = df["ret"].dropna().astype(float)
    out["ret_median_pct"] = round(float(r.median()) * 100, 2) if len(r) else None
    out["ret_mean_pct"] = round(float(r.mean()) * 100, 2) if len(r) else None
    return out


def _cushion(df: pd.DataFrame) -> dict:
    """Cumulative cushion incidence (competing-risk) for the arm's fires."""
    pairs = [(_close(tk), sd) for tk, sd in zip(df["ticker"], df["sig_date"])
             if _close(tk) is not None]
    ci = grading.cushion_incidence(pairs, k_days=(5, 10, 21))
    inc = ci.get("cumulative_incidence", {})
    return {f"cushion_inc_{k}": (inc.get(k, {}) or {}).get("incidence_pct")
            for k in (5, 10, 21)} | {"n_gradable": ci.get("n_gradable")}


def _episode_boot(A: pd.DataFrame, C: pd.DataFrame) -> dict:
    """One-sided episode-clustered p for the stop-out spread (C_stop − A_stop > 0).

    Circular block bootstrap over 6-month episode blocks: resample whole half-year
    blocks (carrying all fires in the block together), recompute both arms' stop-out
    rate, take the favourable spread.  Blocks ≥ the 126-day forward window (§1.2).
    """
    a = A[["sig_date", "stopped"]].assign(arm="A")
    c = C[["sig_date", "stopped"]].assign(arm="C")
    d = pd.concat([a, c], ignore_index=True)
    d["ep"] = d["sig_date"].map(_half)
    eps = sorted(d["ep"].unique())
    if len(eps) < MIN_EPISODES:
        return {"p_one_sided": None, "spread_ci95_pp": None, "n_episodes": len(eps),
                "note": f"thin: {len(eps)} < {MIN_EPISODES} episodes"}
    by_ep = {e: d[d["ep"] == e] for e in eps}
    obs = (C["stopped"].mean() - A["stopped"].mean())
    spreads = np.empty(B_BOOT)
    for b in range(B_BOOT):
        pick = RNG.choice(len(eps), size=len(eps), replace=True)
        boot = pd.concat([by_ep[eps[i]] for i in pick])
        aa, cc = boot[boot["arm"] == "A"], boot[boot["arm"] == "C"]
        spreads[b] = (cc["stopped"].mean() - aa["stopped"].mean()) if len(aa) and len(cc) else np.nan
    spreads = spreads[np.isfinite(spreads)]
    if not len(spreads):
        return {"p_one_sided": None, "spread_ci95_pp": None, "n_episodes": len(eps)}
    return {
        "obs_stopout_spread_pp": round(float(obs) * 100, 2),
        "p_one_sided": float(np.mean(spreads <= 0)),
        "spread_ci95_pp": [round(float(np.percentile(spreads, q)) * 100, 2) for q in (2.5, 97.5)],
        "n_episodes": len(eps),
    }


def _halves(A: pd.DataFrame, C: pd.DataFrame) -> dict:
    """Stop-out spread (C−A, pp) in each time half; sign-stable iff both > 0."""
    alld = pd.concat([A["sig_date"], C["sig_date"]])
    med = alld.median()
    out = {}
    for lbl, aa, cc in (("H1", A[A["sig_date"] <= med], C[C["sig_date"] <= med]),
                        ("H2", A[A["sig_date"] > med], C[C["sig_date"] > med])):
        out[lbl] = (round((cc["stopped"].mean() - aa["stopped"].mean()) * 100, 2)
                    if len(aa) and len(cc) else None)
    out["sign_stable"] = bool(out["H1"] is not None and out["H2"] is not None
                              and out["H1"] > 0 and out["H2"] > 0)
    return out


def _per_name_majority(A: pd.DataFrame, C: pd.DataFrame) -> dict:
    """Names with ≥2 fires per side; agree iff A stop-rate < C stop-rate for the name."""
    agree = tot = 0
    a_by = dict(tuple(A.groupby("ticker")))
    c_by = dict(tuple(C.groupby("ticker")))
    for tk in set(a_by) & set(c_by):
        sa, sc = a_by[tk], c_by[tk]
        if len(sa) >= 2 and len(sc) >= 2:
            tot += 1
            if sa["stopped"].mean() < sc["stopped"].mean():
                agree += 1
    return {"n_names": tot, "agree_pct": (round(100 * agree / tot, 1) if tot else None)}


def evaluate(events: pd.DataFrame, cfg: str, thr: float) -> dict:
    """Partition into A/B/C for this config and run the full registered battery."""
    decline = events["d_shares"] <= thr if thr < 0 else events["d_shares"] < 0
    rising_nd = events["nd_known"] & (events["d_net_debt"] > 0)
    A = events[decline & ~rising_nd].copy()                       # clean fire (primary)
    B = events[decline & rising_nd].copy()                        # debt-funded (context)
    C = events[events["d_shares"] >= 0].copy()                    # control (fixed)
    A_conf = events[decline & events["nd_known"] & (events["d_net_debt"] <= 0)].copy()

    rA, rC, rB = _rates(A), _rates(C), _rates(B)
    stop_spread = (round(rC["stopped"] - rA["stopped"], 2)
                   if rA.get("n") and rC.get("n") else None)      # favourable if > 0
    dead_spread = (round(rC["dead"] - rA["dead"], 2)
                   if rA.get("n") and rC.get("n") else None)
    cA, cC = _cushion(A), _cushion(C)
    cush_spread21 = (round((cA["cushion_inc_21"] or 0) - (cC["cushion_inc_21"] or 0), 2)
                     if cA.get("cushion_inc_21") is not None and cC.get("cushion_inc_21") is not None
                     else None)
    boot = _episode_boot(A, C) if len(A) and len(C) else {"p_one_sided": None}
    halves = _halves(A, C) if len(A) and len(C) else {}
    pnm = _per_name_majority(A, C)

    sign_ok = bool(stop_spread is not None and stop_spread > 0
                   and dead_spread is not None and dead_spread > 0
                   and cush_spread21 is not None and cush_spread21 > 0)
    return {
        "config": cfg, "share_decline_thresh": thr,
        "arm_A_clean": rA, "arm_C_control": rC, "arm_B_debtfunded_ctx": rB,
        "arm_A_confirmed_clean_ctx": _rates(A_conf),
        "cushion_A": cA, "cushion_C": cC, "cushion_spread21_pp": cush_spread21,
        "stopout_spread_pp": stop_spread, "deadmoney_spread_pp": dead_spread,
        "episode_boot": boot, "halves": halves, "per_name_majority": pnm,
        "n_floor_300_met": bool(rA.get("n", 0) >= 300 and rC.get("n", 0) >= 300),
        "sign_all_three_axes": sign_ok,
        "spread_ge_5pp": bool(stop_spread is not None and stop_spread >= 5.0),
    }


def main() -> int:
    # Pre-register the declared budget BEFORE any spread is computed (§1.2: m from
    # the trial ledger, cannot be understated).  Idempotent.
    with register_trials(FAMILY, budget=len(CONFIGS),
                         reason="S11 phase-0: share_decline ∈ {any(<0), material(≤−1%)}"):
        edgar = pd.read_parquet(EDGAR_STORE)
        print(f"EDGAR {edgar.shape}, net_debt non-null "
              f"{int(edgar['net_debt'].notna().sum()) if 'net_debt' in edgar else 0}", flush=True)
        events = build_events(edgar)

        results = {}
        for cfg, thr in CONFIGS.items():
            print(f"=== config {cfg} (thr={thr}) ===", flush=True)
            results[cfg] = evaluate(events, cfg, thr)
            print(json.dumps(results[cfg], indent=1, default=str), flush=True)

        # BH-FDR across the S11 registered family (m=2 primary stop-out p-values).
        pvals = {cfg: (results[cfg]["episode_boot"].get("p_one_sided")
                       if results[cfg]["episode_boot"].get("p_one_sided") is not None else 1.0)
                 for cfg in CONFIGS}
        results["_bh_family_s11"] = benjamini_hochberg(pvals, alpha=0.10)
        results["_meta"] = {
            "n_graded_fires": int(len(events)),
            "family": FAMILY, "m_trials": len(CONFIGS),
            "block": "6-calendar-month (≥126d forward window, §1.2)",
        }

    OUT.write_text(json.dumps(results, indent=1, default=str))
    print("\n" + json.dumps(results["_bh_family_s11"], indent=1, default=str))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
