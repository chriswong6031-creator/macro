"""Measure HK washout_watch lane coverage against the cycle ladder's BOTTOM WATCH cohort.

Reproduces every number in research/ADJUDICATION_20260805_HK_WASHOUT_WATCH_LADDER_COVERAGE.md.

    python3 research/hk_washout_coverage/washout_coverage_packet.py

Reads committed board snapshots out of git history (site/factordata/hk_scoreboard.json +
hk_standouts.json, one per as_of) and recomputes RSI from data/hk_stocks/<ticker>.parquet
with the SAME engine.stock_technicals.snapshot() the nightly builder uses.  The recompute is
self-validating: it asserts agreement with the RSI published on each snapshot's washout_watch
rows, so a drifted method fails loudly instead of producing plausible numbers.

DISPLAY-TIER MEASUREMENT ONLY.  Computes no signal, writes no ledger, touches no board.
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from engine import stock_technicals  # noqa: E402
from engine import hk_washout_watch as ww  # noqa: E402

SCOREBOARD = "site/factordata/hk_scoreboard.json"
STANDOUTS = "site/factordata/hk_standouts.json"
LANES = ["buy", "watch", "laggards", "leaders", "ran", "vetoed", "washout_watch"]
BOTTOM_WATCH_LABEL = "NEARING A LOW"
N_SNAPSHOTS = 10


def _show(rev: str, path: str):
    try:
        raw = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
        return json.loads(raw)
    except Exception:
        return None


def _snapshots(n: int = N_SNAPSHOTS) -> list[tuple[str, dict, dict]]:
    """One (as_of, scoreboard, standouts) per distinct board date, newest first."""
    revs = subprocess.run(["git", "log", "--format=%h", "-40", "--", SCOREBOARD],
                          cwd=REPO, capture_output=True, text=True).stdout.split()
    out, seen = [], set()
    for rev in revs:
        sb = _show(rev, SCOREBOARD)
        if not sb or not sb.get("as_of") or sb["as_of"] in seen:
            continue
        st = _show(rev, STANDOUTS)
        if not st:
            continue
        seen.add(sb["as_of"])
        out.append((sb["as_of"], sb, st))
        if len(out) >= n:
            break
    return out


def rsi_asof(ticker: str, as_of: str) -> float | None:
    """RSI-14 as the builder computes it, truncated to the snapshot's as_of date."""
    p = REPO / "data" / "hk_stocks" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        close = pd.read_parquet(p)["close"].dropna()
        close = close[close.index <= pd.Timestamp(as_of)]
        if len(close) < 70:
            return None
        return stock_technicals.snapshot(close).get("rsi14")
    except Exception:
        return None


def dist_200dma_asof(ticker: str, as_of: str) -> float | None:
    """What dist_200dma WOULD be if anything produced it.

    Production always reads None here: the builder derives dist_200dma from
    ``rec["tech"]["ma200"]`` (scripts/build_hk_library.py), and no HK producer writes
    that key -- engine/hk_inputs.py computes a 200d mean but publishes only the boolean
    ``above_200d_trend``.  This recomputes the intended value so the packet can measure
    what the dead criterion would have caught.
    """
    p = REPO / "data" / "hk_stocks" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        close = pd.read_parquet(p)["close"].dropna()
        close = close[close.index <= pd.Timestamp(as_of)]
        if len(close) < 200:
            return None
        return round(float(close.iloc[-1]) / float(close.iloc[-200:].mean()) - 1.0, 4)
    except Exception:
        return None


def _lane_map(st: dict) -> dict[str, set]:
    return {L: {r.get("ticker") for r in (st.get(L) or []) if isinstance(r, dict)}
            for L in LANES}


def main() -> int:
    snaps = _snapshots()
    if not snaps:
        print("no committed board snapshots found", file=sys.stderr)
        return 1

    per_day, validation = [], []
    for as_of, sb, st in snaps:
        cyc = {r["ticker"]: r.get("cycle") for r in sb["modes"]["all"]}
        lanes = _lane_map(st)
        lane_union = set().union(*lanes.values())
        watch_rows = st.get("washout_watch") or []

        # Self-validation: our recompute must reproduce the published RSI.
        matched = total = 0
        for r in watch_rows:
            pub, mine = r.get("rsi"), rsi_asof(r["ticker"], as_of)
            if pub is None:
                continue
            total += 1
            matched += int(mine is not None and abs(round(mine) - round(pub)) <= 1)
        validation.append({"as_of": as_of, "matched": matched, "total": total})

        cohort = [t for t, v in cyc.items() if v == BOTTOM_WATCH_LABEL]
        invisible = []
        for t in cohort:
            if t in lane_union:
                continue
            r = rsi_asof(t, as_of)
            d200 = dist_200dma_asof(t, as_of)
            invisible.append({
                "ticker": t,
                "rsi": r,
                "dist_200dma_would_be": d200,
                # The criterion the module DESIGNED to catch deep-decline names, and
                # which has never been able to fire in production.
                "deep_below_200dma": bool(
                    d200 is not None and d200 <= ww.PCT_BELOW_200DMA_THRESH),
                # Candidacy hinges on RSI<=40 (dist_200dma is structurally None; the
                # ladder label carries no DECLINE/FALL/BEAR keyword). A name inside the
                # RSI_RECLAIM zone would earn a confluence signal if it could be admitted.
                "in_reclaim_zone": bool(
                    r is not None
                    and ww.RSI_RECLAIM_MIN <= r <= ww.RSI_RECLAIM_MAX
                ),
                "oversold_candidate": bool(r is not None and r <= ww.RSI_OVERSOLD),
            })

        label_mix: dict[str, int] = {}
        for t in lanes["washout_watch"]:
            label_mix[cyc.get(t) or "?"] = label_mix.get(cyc.get(t) or "?", 0) + 1

        per_day.append({
            "as_of": as_of,
            "universe": len(cyc),
            "washout_watch_size": len(lanes["washout_watch"]),
            "lane_label_mix": label_mix,
            "bottom_watch_cohort": len(cohort),
            "bottom_watch_invisible": len(invisible),
            "invisible_detail": invisible,
            "dist_200dma_nonnull_rows": sum(
                1 for r in watch_rows if r.get("dist_200dma") is not None),
            "washout_rows": len(watch_rows),
        })

    v_ok = sum(d["matched"] for d in validation)
    v_all = sum(d["total"] for d in validation)
    if v_all and v_ok != v_all:
        print(f"RSI RECOMPUTE VALIDATION FAILED: {v_ok}/{v_all} — numbers below are untrustworthy",
              file=sys.stderr)

    days = len(per_day)
    lane_days = sum(d["washout_watch_size"] for d in per_day)
    nah = sum(d["lane_label_mix"].get("NEARING A HIGH", 0) for d in per_day)
    nal = sum(d["lane_label_mix"].get(BOTTOM_WATCH_LABEL, 0) for d in per_day)
    cohort_days = sum(d["bottom_watch_cohort"] for d in per_day)
    invis_days = sum(d["bottom_watch_invisible"] for d in per_day)
    rescuable = sum(1 for d in per_day for i in d["invisible_detail"] if i["in_reclaim_zone"])
    deep200 = sum(1 for d in per_day for i in d["invisible_detail"] if i["deep_below_200dma"])

    summary = {
        "snapshots": days,
        "date_range": [per_day[-1]["as_of"], per_day[0]["as_of"]],
        "rsi_recompute_validation": f"{v_ok}/{v_all}",
        "washout_watch_name_days": lane_days,
        "lane_pct_nearing_a_high": round(100 * nah / lane_days, 1) if lane_days else None,
        "lane_pct_nearing_a_low": round(100 * nal / lane_days, 1) if lane_days else None,
        "bottom_watch_name_days": cohort_days,
        "bottom_watch_invisible_name_days": invis_days,
        "bottom_watch_invisible_pct": round(100 * invis_days / cohort_days, 1) if cohort_days else None,
        "invisible_in_reclaim_zone": rescuable,
        "invisible_not_rescuable_by_rsi": invis_days - rescuable,
        "invisible_deep_below_200dma": deep200,
        "invisible_deep_below_200dma_pct": round(100 * deep200 / invis_days, 1) if invis_days else None,
        "dist_200dma_nonnull_rows_total": sum(d["dist_200dma_nonnull_rows"] for d in per_day),
        "washout_rows_total": sum(d["washout_rows"] for d in per_day),
        "mean_lane_size_now": round(lane_days / days, 1),
        "mean_lane_size_option_b": round((lane_days + invis_days) / days, 1),
        "thresholds": {
            "RSI_OVERSOLD": ww.RSI_OVERSOLD,
            "RSI_RECLAIM_MIN": ww.RSI_RECLAIM_MIN,
            "RSI_RECLAIM_MAX": ww.RSI_RECLAIM_MAX,
            "PCT_BELOW_200DMA_THRESH": ww.PCT_BELOW_200DMA_THRESH,
            "CONFLUENCE_WATCH": ww.CONFLUENCE_WATCH,
        },
    }

    out = {"summary": summary, "per_day": per_day, "validation": validation}
    dest = Path(__file__).with_name("washout_coverage_results.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"\nwrote {dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
