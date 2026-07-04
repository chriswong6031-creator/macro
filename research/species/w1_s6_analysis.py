"""W1 S6 phase-0 analysis — failed2 × COILED interaction marginal (OOS baskets).

Prereg: research/species/W1_S6_PREREG.md. Reads the regenerated wave-2 basket
fires (unmodified harness), recomputes the ROTATIONAL primary clean8_21 per fire
via engine.grading.terminal_state (one-grader constants; S6's declared class),
and evaluates the five registered requirements per variant.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
sys.path.insert(0, str(ROOT))

from engine import grading                       # noqa: E402
from engine.validation import benjamini_hochberg  # noqa: E402

FIRES_DIR = Path("/tmp/s6_wave2_baskets")
PANEL_DIR = ROOT / "data" / "baskets" / "ohlcv"
B = 2000
RNG = np.random.default_rng(7)

_close_cache: dict[str, pd.Series] = {}


def _close(tk: str) -> pd.Series | None:
    if tk not in _close_cache:
        fp = PANEL_DIR / f"{tk}.parquet"
        try:
            s = pd.read_parquet(fp)["close"].dropna().sort_index()
            _close_cache[tk] = s
        except Exception:
            _close_cache[tk] = None
    return _close_cache[tk]


def _clean8_21(row) -> dict | None:
    """Rotational terminal state at clean8_21 from the fire's own sig_date
    (grading recomputes the same next-bar fill the harness used)."""
    s = _close(row["ticker"])
    if s is None:
        return None
    ts = grading.terminal_state(
        s, row["sig_date"],
        liftoff_mult=grading.LIFTOFF_8, liftoff_horizon=grading.LIFTOFF_HORIZON_21)
    st = ts.get("state")
    if st is None:
        return None
    st = str(st)
    return {"clean8_21": int(st == "CLEAN_LIFTOFF"),
            "stopped21": int(st == "STOPPED"),
            "dead21": int(st == "DEAD_MONEY")}


def _rates(df: pd.DataFrame) -> dict:
    return {"n": int(len(df)),
            "clean8_21": round(float(df["clean8_21"].mean() * 100), 2) if len(df) else None,
            "stopped21": round(float(df["stopped21"].mean() * 100), 2) if len(df) else None,
            "dead21": round(float(df["dead21"].mean() * 100), 2) if len(df) else None,
            "clean15_126_ctx": (round(float(df["clean15"].mean() * 100), 2)
                                 if "clean15" in df.columns and len(df) else None)}


def _block_boot_p(df: pd.DataFrame) -> tuple[float | None, list | None]:
    """One-sided episode-clustered p for spread>0: circular block bootstrap over
    calendar-month episode blocks of the (failed2, clean8_21) fire rows."""
    df = df.copy()
    df["episode"] = df["sig_date"].dt.to_period("M")
    months = df["episode"].unique()
    if len(months) < 12:
        return None, None
    by_month = {m: df[df["episode"] == m] for m in months}
    spreads = np.empty(B)
    for b in range(B):
        pick = RNG.choice(len(months), size=len(months), replace=True)
        boot = pd.concat([by_month[months[i]] for i in pick])
        t = boot[boot["failed2"] == True]   # noqa: E712
        f = boot[boot["failed2"] == False]  # noqa: E712
        if not len(t) or not len(f):
            spreads[b] = np.nan
            continue
        spreads[b] = t["clean8_21"].mean() - f["clean8_21"].mean()
    spreads = spreads[np.isfinite(spreads)]
    if not len(spreads):
        return None, None
    p_one_sided = float(np.mean(spreads <= 0))
    ci = [round(float(np.percentile(spreads, q)) * 100, 2) for q in (2.5, 97.5)]
    return p_one_sided, ci


def analyze(variant: str) -> dict:
    fp = FIRES_DIR / f"fires_{variant}.parquet"
    fires = pd.read_parquet(fp)
    fires["sig_date"] = pd.to_datetime(fires["sig_date"])
    out: dict = {"variant": variant, "n_fires_total": int(len(fires))}

    # rotational outcomes per fire (cache close series across variants)
    rows = []
    for _, r in fires.iterrows():
        oc = _clean8_21(r)
        if oc is None:
            continue
        d = {"ticker": r["ticker"], "sig_date": r["sig_date"],
             "failed2": bool(r["failed2"]) if pd.notna(r["failed2"]) else None,
             "coiled": bool(r.get("coiled", False)),
             "clean15": r.get("clean15"), **oc}
        rows.append(d)
    df = pd.DataFrame(rows).dropna(subset=["failed2"])
    out["n_fires_graded"] = int(len(df))

    coiled = df[df["coiled"] == True]  # noqa: E712
    t = coiled[coiled["failed2"] == True]   # noqa: E712
    f = coiled[coiled["failed2"] == False]  # noqa: E712
    out["primary_within_COILED"] = {
        "failed2_T": _rates(t), "failed2_F": _rates(f),
        "clean8_21_spread_pp": (round(float(t["clean8_21"].mean()
                                            - f["clean8_21"].mean()) * 100, 2)
                                if len(t) and len(f) else None),
        "n_floor_300_met": bool(len(t) >= 300 and len(f) >= 300),
    }

    # episode-clustered p on the within-COILED spread
    p, ci = _block_boot_p(coiled)
    out["primary_within_COILED"]["p_one_sided_episode_boot"] = p
    out["primary_within_COILED"]["spread_ci95_pp"] = ci

    # both time halves sign-stable
    med = coiled["sig_date"].median()
    halves = {}
    for lbl, sub in (("H1", coiled[coiled["sig_date"] <= med]),
                     ("H2", coiled[coiled["sig_date"] > med])):
        st, sf = (sub[sub["failed2"] == True], sub[sub["failed2"] == False])  # noqa: E712
        halves[lbl] = (round(float(st["clean8_21"].mean() - sf["clean8_21"].mean()) * 100, 2)
                       if len(st) and len(sf) else None)
    out["primary_within_COILED"]["halves_spread_pp"] = halves

    # per-name majority (names with ≥2 fires per side)
    agree = tot = 0
    for tk, sub in coiled.groupby("ticker"):
        st, sf = (sub[sub["failed2"] == True], sub[sub["failed2"] == False])  # noqa: E712
        if len(st) >= 2 and len(sf) >= 2:
            tot += 1
            if st["clean8_21"].mean() > sf["clean8_21"].mean():
                agree += 1
    out["primary_within_COILED"]["per_name_majority"] = (
        {"n_names": tot, "agree_pct": round(100 * agree / tot, 1)} if tot else
        {"n_names": 0, "agree_pct": None})

    # secondary: standalone failed2 on ALL fires (context only)
    ta = df[df["failed2"] == True]   # noqa: E712
    fa = df[df["failed2"] == False]  # noqa: E712
    out["secondary_standalone_ALL"] = {
        "failed2_T": _rates(ta), "failed2_F": _rates(fa),
        "clean8_21_spread_pp": (round(float(ta["clean8_21"].mean()
                                            - fa["clean8_21"].mean()) * 100, 2)
                                if len(ta) and len(fa) else None)}
    return out


def main() -> int:
    results = {v: analyze(v) for v in ("base3d", "m2d_s3d")}
    # BH across the W1 registered family (m=4: S13's 2 trials pad at p=1.0 —
    # conservative; S13's primary was DSR-based, no comparable p)
    pvals = {"s13_t1": 1.0, "s13_t2": 1.0}
    for v in ("base3d", "m2d_s3d"):
        p = results[v]["primary_within_COILED"].get("p_one_sided_episode_boot")
        pvals[f"s6_{v}"] = p if p is not None else 1.0
    results["_bh_family_W1"] = benjamini_hochberg(pvals, alpha=0.10)
    out = Path("/tmp/s6_phase0_out.json")
    out.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, indent=1, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
