"""LSR-P0 reopeners — close the three testable escape hatches the phase-0 left open.

`research/LIQUIDITY_SHOCK_REVERSAL_PHASE0.md` §4 named four reopeners. This script
answers the ones our data can answer, so the kill's scope stops being a promise and
becomes a measurement. Reopener #1 (tape-grade signed order flow) is not here and
cannot be — it is blocked on an entitlement, not on effort.

  R2  A RICHER INFORMATION FIREWALL. Savor (2012) used ANALYST REPORTS, not 8-Ks.
      If our 8-K-only firewall was the reason the separation vanished, a revisions-
      based firewall should restore it. COVERAGE-BLOCKED, and this script prints the
      number rather than hand-waving it: data/revisions/history.parquet starts
      2026-06-16, so only ~0.7% of the event tape has a revisions read at all.
  R3  THE ILLIQUID TAIL. The phase-0 floor was $5 / $5m ADV, and the literature puts
      short-horizon reversal in small, illiquid, high-turnover names. This rebuilds
      the panel at $2 / $250k and re-measures — the tail is where the effect should
      be biggest and where cost is worst, so both halves are reported.
  R4  MARKET-LIQUIDITY REGIME. Nagel (2012) ties short-horizon reversal returns to
      compensation for liquidity provision, which spikes when VIX spikes. The
      phase-0 never conditioned on the aggregate regime; this partitions every
      contrast by the VIX 252-day percentile at t0 (FRED VIXCLS).

Everything reuses the phase-0's frozen definitions and its date-clustered inference
by import — no second copy of the trigger, the residual basis, or the bootstrap.

Run: PYTHONPATH=. python -m scripts.research_lsr_reopeners [--panel-cache DIR]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import config  # noqa: E402
from scripts.research_liquidity_shock_reversal import (  # noqa: E402
    FWD_HORIZONS,
    break_even_bps,
    build_panel,
    date_block_ci,
    derive,
    harvest_events,
    news_flags,
)

log = logging.getLogger("lsr-reopen")

TAIL_MIN_PRICE = 2.0
TAIL_MIN_ADV = 2.5e5


def _arm(ev: pd.DataFrame, h: int) -> pd.Series:
    return ev.groupby("date")[f"fwd{h}"].mean()


def _contrast(ev: pd.DataFrame, h: int) -> dict:
    """No-news minus news, computed WITHIN date so the tape cancels exactly."""
    diff = (_arm(ev[~ev["news"]], h) - _arm(ev[ev["news"]], h)).dropna()
    ci = date_block_ci(diff)
    return {"mean_pct": 100 * ci["mean"], "lo_pct": 100 * ci["lo"], "hi_pct": 100 * ci["hi"],
            "n_dates": ci["n"], "excludes_zero": bool(ci["lo"] > 0 or ci["hi"] < 0)}


# ── R2 ───────────────────────────────────────────────────────────────────────
def reopener_r2(ev: pd.DataFrame, data_dir: Path) -> dict:
    """Can an analyst-revision firewall be built at all on this tape? (No.)"""
    p = data_dir / "revisions" / "history.parquet"
    if not p.exists():
        return {"verdict": "UNANSWERABLE", "reason": "data/revisions/history.parquet absent"}
    rev = pd.read_parquet(p)
    rev["date"] = pd.to_datetime(rev["date"])
    lo, hi = rev["date"].min(), rev["date"].max()
    inside = ev[(ev["date"] >= lo) & (ev["date"] <= hi)]
    return {
        "verdict": "COVERAGE-BLOCKED",
        "revisions_span": [str(lo.date()), str(hi.date())],
        "revisions_names": int(rev["ticker"].nunique()),
        "events_total": len(ev),
        "events_inside_window": len(inside),
        "coverage_rate": len(inside) / max(len(ev), 1),
        "dates_inside_window": int(inside["date"].nunique()),
        "note": ("Savor's own information proxy cannot be tested here: the revisions "
                 "store is a forward accrual that began 2026-06-16, while the shock "
                 "tape runs from 2021-09. It stays an OPEN reopener with a named "
                 "clock, not a null — first answerable once the store has a few years."),
    }


# ── R3 ───────────────────────────────────────────────────────────────────────
def reopener_r3(cache: Path, massive: Path, data_dir: Path) -> dict:
    """Rebuild at the illiquid floor and re-measure the whole verdict there."""
    panel = build_panel(cache, massive, min_price=TAIL_MIN_PRICE, min_adv=TAIL_MIN_ADV)
    d = derive(panel, data_dir, min_price=TAIL_MIN_PRICE, min_adv_event=TAIL_MIN_ADV)
    ev = news_flags(harvest_events(d), data_dir)
    cov = ev[ev["cov_earn8k"]]

    # unconditional reversal in the genuinely illiquid slice
    cum, elig, dv = d["cum"], d["eligible"], d["dv_med"]
    q = dv.rank(axis=1, pct=True)
    sig = -(cum - cum.shift(1))
    uncond = []
    for hz in (1, 5):
        fwd = cum.shift(-hz) - cum
        for tname, lo, hi in (("bottom_decile", 0.0, 0.1), ("bottom_tercile", 0.0, 1 / 3)):
            m = elig & (q >= lo) & (q < hi) & sig.notna() & fwd.notna()
            s, fv = sig.where(m), fwd.where(m)
            pr = s.rank(axis=1, pct=True)
            sp = (fv.where(pr >= 0.9).mean(axis=1) - fv.where(pr <= 0.1).mean(axis=1)) \
                .where(m.sum(axis=1) >= 30)
            ci = date_block_ci(sp)
            icci = date_block_ci(s.corrwith(fv, axis=1, method="spearman"))
            uncond.append({"horizon_d": hz, "slice": tname,
                           "decile_spread_pct": 100 * ci["mean"],
                           "lo_pct": 100 * ci["lo"], "hi_pct": 100 * ci["hi"],
                           # canonical helper, NOT a re-derivation: computing this inline
                           # once already produced a 100x-too-small break-even here
                           "break_even_bps_per_leg": break_even_bps(100 * ci["mean"]),
                           "rank_ic": icci["mean"], "ic_lo": icci["lo"], "ic_hi": icci["hi"]})

    return {
        "floor": {"min_price": TAIL_MIN_PRICE, "min_adv_usd": TAIL_MIN_ADV},
        "universe_names": int(panel["close"].shape[1]),
        "events_total": len(ev),
        "events_8k_covered": len(cov),
        "8k_coverage_rate": float(ev["cov_earn8k"].mean()),
        "news_contrast_down": {h: _contrast(cov[cov["side"] == "down"], h) for h in FWD_HORIZONS},
        "unconditional_reversal": uncond,
    }


# ── R4 ───────────────────────────────────────────────────────────────────────
def reopener_r4(ev: pd.DataFrame, data_dir: Path) -> dict:
    """Partition every contrast by the VIX 252d percentile at t0 (Nagel 2012)."""
    p = data_dir / "fred" / "VIXCLS.parquet"
    if not p.exists():
        return {"verdict": "UNANSWERABLE", "reason": "data/fred/VIXCLS.parquet absent"}
    vix = pd.read_parquet(p)
    col = vix.columns[0] if len(vix.columns) else None
    v = vix[col].astype(float).dropna()
    v.index = pd.to_datetime(v.index)
    pct = v.rolling(252, min_periods=120).rank(pct=True)

    ev = ev.copy()
    ev["vix"] = ev["date"].map(v.reindex(ev["date"].unique()).ffill())
    ev["vix_pct"] = ev["date"].map(pct.reindex(ev["date"].unique()).ffill())
    ev = ev[ev["vix_pct"].notna()]

    out = {"vix_span": [str(v.index.min().date()), str(v.index.max().date())],
           "events_with_vix": len(ev), "buckets": []}
    cov = ev[ev["cov_earn8k"]]
    for name, lo, hi in (("calm_p0_50", 0.0, 0.5), ("elevated_p50_80", 0.5, 0.8),
                         ("stressed_p80_100", 0.8, 1.01)):
        b = cov[(cov["vix_pct"] >= lo) & (cov["vix_pct"] < hi)]
        dn = b[b["side"] == "down"]
        row = {"bucket": name, "n_events": len(b), "n_down": len(dn),
               "median_vix": float(b["vix"].median()) if len(b) else None,
               "contrast_down": {h: _contrast(dn, h) for h in (3, 5, 10)},
               "no_news_down": {}}
        for h in (3, 5, 10):
            ci = date_block_ci(_arm(dn[~dn["news"]], h))
            row["no_news_down"][h] = {"mean_pct": 100 * ci["mean"], "lo_pct": 100 * ci["lo"],
                                      "hi_pct": 100 * ci["hi"], "n_dates": ci["n"]}
        out["buckets"].append(row)

    # The no-news arm shows a Nagel-shaped gradient across the buckets. Eyeballing three
    # overlapping intervals is the WRONG test for that (it is far too lenient), so measure
    # the calm-minus-stressed difference DIRECTLY, paired within date where both exist and
    # unpaired otherwise — a gradient nobody tested is a hypothesis, not a finding.
    dn = cov[cov["side"] == "down"]
    dn = dn[~dn["news"]]
    calm = dn[dn["vix_pct"] < 0.5]
    stressed = dn[dn["vix_pct"] >= 0.8]
    out["no_news_calm_minus_stressed"] = {}
    for h in (3, 5, 10):
        a = date_block_ci(_arm(calm, h))
        b = date_block_ci(_arm(stressed, h))
        # dates are disjoint by construction (a date sits in one VIX bucket), so this is a
        # two-sample difference of date-clustered means, not a paired one
        pooled = np.sqrt(((a["hi"] - a["lo"]) / 3.92) ** 2 + ((b["hi"] - b["lo"]) / 3.92) ** 2)
        delta = a["mean"] - b["mean"]
        out["no_news_calm_minus_stressed"][h] = {
            "delta_pct": 100 * delta,
            "lo_pct": 100 * (delta - 1.96 * pooled),
            "hi_pct": 100 * (delta + 1.96 * pooled),
            "excludes_zero": bool(abs(delta) > 1.96 * pooled),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel-cache", default=None)
    ap.add_argument("--tail-cache", default=None)
    ap.add_argument("--massive-dir", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    data_dir = Path(config.data_dir())
    massive = Path(args.massive_dir) if args.massive_dir else data_dir / "massive_stock_day"
    cache = Path(args.panel_cache) if args.panel_cache else data_dir / "research" / "lsr_p0_panel"
    tail = Path(args.tail_cache) if args.tail_cache else data_dir / "research" / "lsr_p0_panel_tail"
    if not massive.exists() or not any(massive.glob("*.parquet")):
        print(f"::warning title=lsr-reopeners::massive_stock_day absent at {massive}", flush=True)
        return 1

    panel = build_panel(cache, massive)
    d = derive(panel, data_dir)
    ev = news_flags(harvest_events(d), data_dir)

    report = {
        "study": "LSR-P0 reopeners (R2 firewall / R3 illiquid tail / R4 VIX regime)",
        "parent": "research/LIQUIDITY_SHOCK_REVERSAL_PHASE0.md",
        "R2_richer_firewall": reopener_r2(ev, data_dir),
        "R4_vix_regime": reopener_r4(ev, data_dir),
        "R3_illiquid_tail": reopener_r3(tail, massive, data_dir),
        "R1_tape_grade": {
            "verdict": "BLOCKED — ENTITLEMENT",
            "note": ("signed order imbalance / price-impact-per-signed-dollar / true spread "
                     "need massive.com trades_v1 + quotes_v1, both 403. Not a modelling "
                     "gap and not closeable by more analysis."),
        },
    }
    out = Path(args.out) if args.out else data_dir / "research" / "lsr_reopeners_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    log.info("lsr-reopen: wrote %s", out)

    r4 = report["R4_vix_regime"]
    if "buckets" in r4:
        sig = sum(1 for b in r4["buckets"] for c in b["contrast_down"].values() if c["excludes_zero"])
        log.info("lsr-reopen: R4 separation %d/9 stress-bucket contrasts exclude zero", sig)
    r3 = report["R3_illiquid_tail"]
    if "news_contrast_down" in r3:
        sig3 = sum(1 for c in r3["news_contrast_down"].values() if c["excludes_zero"])
        log.info("lsr-reopen: R3 tail universe %d names, separation %d/%d contrasts",
                 r3["universe_names"], sig3, len(r3["news_contrast_down"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
