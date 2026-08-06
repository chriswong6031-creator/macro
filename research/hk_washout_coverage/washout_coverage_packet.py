"""Measure HK washout_watch lane coverage against the cycle ladder's BOTTOM WATCH cohort.

Emits the receipts behind research/ADJUDICATION_20260805_HK_WASHOUT_WATCH_LADDER_COVERAGE.md:
every count, share, per-date cohort roster, and option cost the packet quotes.

KNOWN LIMIT, stated rather than papered over: per-day rescue counts read the RSI organ only
(`in_reclaim_zone`), because historical per-date state for the other five confluence organs is
not reconstructable from committed artifacts -- the southbound store holds only the current
cross-section.  Those counts are therefore LOWER bounds on who would render, and cannot support
a claim that a given name would NOT render.  For the newest snapshot, where all six organs are
readable, `summary.latest_cohort_all_organ_confluence` measures the full confluence instead.

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
    """What dist_200dma WOULD be, as a FRACTION.

    Production always reads None: the builder derives dist_200dma from
    ``rec["tech"]["ma200"]`` (scripts/build_hk_library.py:1195) and nothing emits that key.
    The producer -- engine.stock_technicals.snapshot() -- publishes the same quantity as
    ``pct_vs_200dma``, but in PERCENT units ((px/ref - 1) * 100).

    UNITS ARE LOAD-BEARING.  PCT_BELOW_200DMA_THRESH is -0.12, a fraction.  Reading
    ``pct_vs_200dma`` without dividing by 100 makes the test ``-15.8 <= -0.12`` -- true for
    anything more than 0.12% below trend.  This returns the FRACTION, matching the threshold.
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
        # Option B admits EVERY cohort name as a candidate, so its lane delta is the cohort
        # members not already in washout_watch -- which includes names visible in some OTHER
        # lane (buy/watch/laggards/...).  Lanes overlap; "in no lane at all" is a strictly
        # smaller set and is the wrong denominator for the cost of the change.
        cohort_elsewhere = [t for t in cohort
                            if t not in lanes["washout_watch"] and t in lane_union]
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

        # Sorted: `lanes[...]` is a set, so insertion order varies run to run and an
        # unsorted dict would make this artifact produce a phantom git diff every time.
        # Full cohort roster with lane membership -- the receipt behind the packet's per-date
        # tables, including the names that ARE placed (which invisible_detail omits by design).
        name_by = {r["ticker"]: r.get("name") for r in sb["modes"]["all"]}
        cohort_detail = [{
            "ticker": t,
            "name": name_by.get(t),
            "rsi": rsi_asof(t, as_of),
            "lanes": sorted(L for L in LANES if t in lanes[L]),
        } for t in sorted(cohort)]

        label_mix: dict[str, int] = {}
        for t in sorted(lanes["washout_watch"]):
            label_mix[cyc.get(t) or "?"] = label_mix.get(cyc.get(t) or "?", 0) + 1
        label_mix = dict(sorted(label_mix.items()))

        per_day.append({
            "as_of": as_of,
            "universe": len(cyc),
            "washout_watch_size": len(lanes["washout_watch"]),
            "lane_label_mix": label_mix,
            "bottom_watch_cohort": len(cohort),
            "cohort_detail": cohort_detail,
            "bottom_watch_in_washout_watch": len([t for t in cohort if t in lanes["washout_watch"]]),
            "bottom_watch_visible_elsewhere_only": len(cohort_elsewhere),
            "bottom_watch_visible_elsewhere_detail": sorted(cohort_elsewhere),
            "option_b_lane_delta": len(cohort) - len([t for t in cohort if t in lanes["washout_watch"]]),
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
    elsewhere_days = sum(d["bottom_watch_visible_elsewhere_only"] for d in per_day)
    optb_delta = sum(d["option_b_lane_delta"] for d in per_day)
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
        "bottom_watch_visible_elsewhere_only_name_days": elsewhere_days,
        # Option B's real lane delta: cohort members not already in washout_watch.  Larger than
        # the "in no lane at all" count, because the lanes overlap.
        "option_b_lane_delta_name_days": optb_delta,
        "mean_lane_size_option_b_full_delta": round((lane_days + optb_delta) / days, 1),
        # LOWER bound -- RSI organ only.  See latest_cohort_all_organ_confluence.
        "invisible_in_reclaim_zone": rescuable,
        "invisible_outside_reclaim_zone": invis_days - rescuable,
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

    # Option-cost census on the newest snapshot: how many names each candidacy route would
    # admit board-wide.  Option C's cost is NOT the count of BOTTOM WATCH names it rescues --
    # the -12% route selects on price alone and pulls in names the ladder never flagged.
    as_of, sb, st = snaps[0]
    cyc = {r["ticker"]: r.get("cycle") for r in sb["modes"]["all"]}
    in_lane = {r["ticker"] for r in (st.get("washout_watch") or [])}
    band_a, deep_c, naive_c, deep_labels = [], [], 0, {}
    for t in sorted(cyc):
        r = rsi_asof(t, as_of)
        if r is not None and 40 < r <= 50:
            band_a.append(t)
        d = dist_200dma_asof(t, as_of)
        if d is not None:
            if d <= ww.PCT_BELOW_200DMA_THRESH:
                deep_c.append(t)
                deep_labels[cyc[t] or "?"] = deep_labels.get(cyc[t] or "?", 0) + 1
            # The unit trap: comparing the PERCENT form against the fractional threshold.
            if d * 100.0 <= ww.PCT_BELOW_200DMA_THRESH:
                naive_c += 1
    summary["option_costs_latest_snapshot"] = {
        "as_of": as_of,
        "universe": len(cyc),
        "lane_size_now": len(in_lane),
        "option_a_rsi_band_40_50": len(band_a),
        "option_a_new": len([t for t in band_a if t not in in_lane]),
        "option_b_new": sum(1 for d in per_day if d["as_of"] == as_of
                            for _ in range(d["bottom_watch_invisible"])),
        "option_c_deep_below_200dma": len(deep_c),
        "option_c_new": len([t for t in deep_c if t not in in_lane]),
        "option_c_labels": dict(sorted(deep_labels.items())),
        "option_c_naive_unit_bug_admits": naive_c,
    }

    # ---- Full-organ confluence for the LATEST cohort -------------------------------------
    # The per-day `in_reclaim_zone` flag reads ONE organ (RSI).  A name Option B admits renders
    # if ANY of the six organs fires, so RSI alone yields a LOWER bound on who is rescued and
    # cannot support a claim that a given name would NOT appear.  Here we read all six for the
    # newest snapshot, using the engine's own reader functions against the committed organ
    # artifacts, so the packet's rescue claim rests on measurement rather than one proxy.
    organ_detail = []
    try:
        fd = REPO / "site" / "factordata"
        organs = {}
        for key, fname in (("adr_bridge", "hk_adr_bridge.json"), ("cbbc", "hk_cbbc.json"),
                           ("narrative", "hk_narrative.json"), ("filing_bus", "hk_filing_bus.json")):
            try:
                organs[key] = json.loads((fd / fname).read_text())
            except Exception:
                pass
        try:
            from engine import hk_southbound_stocks as _sb
            organs["southbound"] = _sb.signal(tickers=list(cyc))
        except Exception:
            pass
        adr, cbbc = ww._read_adr_signals(organs), ww._read_cbbc_signals(organs)
        filing, narr = ww._read_filing_signals(organs), ww._read_narrative_signals(organs)
        sbm = ww._read_southbound_signals(organs)
        for t in sorted(t for t, v in cyc.items() if v == BOTTOM_WATCH_LABEL):
            r = rsi_asof(t, as_of)
            entry = {"ticker": t, "rsi": r,
                     "in_washout_watch": t in in_lane,
                     "in_any_lane": any(t in s for s in _lane_map(st).values())}
            cnt, sigs, veto = ww._confluence_for(t, {"rsi": r}, adr, cbbc, filing, narr,
                                                 sbm, organs, as_of)
            entry.update(confluence_count=cnt, confluence_signals=sigs, dilution_veto=veto,
                         # What Option B would produce for this name.
                         would_render=bool(cnt >= ww.CONFLUENCE_WATCH and not veto))
            organ_detail.append(entry)
    except Exception as e:  # noqa: BLE001 -- a missing organ artifact must not void the packet
        organ_detail = [{"error": f"{type(e).__name__}: {e}"}]
    summary["latest_cohort_all_organ_confluence"] = organ_detail

    out = {"summary": summary, "per_day": per_day, "validation": validation}
    dest = Path(__file__).with_name("washout_coverage_results.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"\nwrote {dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    # Script-run only: at module level this mutes the process-global
    # warnings filter for every importer (tests/test_no_module_level_logging_disable).
    warnings.filterwarnings("ignore")
    raise SystemExit(main())
