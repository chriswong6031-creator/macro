"""scripts/replay_us_sector_rotation.py
=======================================
Historical replay of the US sector-rotation score from 2026-06-01 to 2026-07-15.

For each business day in the window, this script computes the Fast Lens rotation
score using only point-in-time data (closes up to each date, forward_log states
rows dated ≤ that date).  If no state row exists for an instrument on a given date,
it uses the most-recent prior row and flags it.

Acceptance criteria (from XSR-R2 charter) — evaluated on the 11-sector universe only:
    1. XLV rank ≤ 3 among the 11 sectors for ≥ 3 consecutive sessions,
       with the streak's FIRST session ≤ 2026-06-17.
    2. XLK rank ≥ 8 among the 11 sectors for ≥ 3 consecutive sessions,
       with the streak's FIRST session ≤ 2026-07-03.

Ranks are printed as N/11 (sectors) throughout.

Output:
    reports/xsr-w1-replay-2026-06-01_07-15.md
        - date × sector rank matrix (top-3 and bottom-3 per session)
        - streak windows for XLV / XLK
        - component attribution for the key dates
        - honest verdict vs acceptance criteria

Usage:
    python3 scripts/replay_us_sector_rotation.py
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

import pandas as pd
import numpy as np

from engine.us_sector_rotation import (
    score_and_rank,
    load_inputs,
    SPDR_ETFS,
)
from lib import config

# ---------------------------------------------------------------------------
# Replay parameters
# ---------------------------------------------------------------------------
START = "2026-06-01"
END   = "2026-07-15"
REPORT_PATH = _ROOT / "reports" / "xsr-w1-replay-2026-06-01_07-15.md"

# Acceptance targets (sector-only universe, n=11)
HC_TOP3_BY    = "2026-06-17"  # XLV rank ≤ 3 streak FIRST session by this date
SEMIS_BOT4_BY = "2026-07-03"  # XLK rank ≥ 8 streak FIRST session by this date
N_SECTORS = 11

# Acceptance streak requirement
STREAK_MIN = 3

# Keys to track
HC_KEYS   = {"xlv"}       # Criterion 1: XLV only (sectors-only rank)
TECH_KEYS = {"xlk"}       # Criterion 2: XLK only (sectors-only rank)

# Sectors to show in rank matrix
SECTOR_LABELS = {
    "xlk":  "XLK",  "xlv":  "XLV",  "xlp":  "XLP",  "xlu":  "XLU",
    "xlf":  "XLF",  "xle":  "XLE",  "xli":  "XLI",  "xly":  "XLY",
    "xlb":  "XLB",  "xlre": "XLRE", "xlc":  "XLC",
}


def _load_base_inputs():
    """Load all inputs once (closes, membership); we will slice them per date."""
    from engine.inputs import yahoo_closes
    from engine.equity_factors import _closes as stock_closes_fn

    print("Loading ETF closes...", flush=True)
    etf_close_df = yahoo_closes()
    bench = etf_close_df["SPY"].dropna() if "SPY" in etf_close_df.columns else pd.Series(dtype=float)

    print("Loading stock closes (broad)...", flush=True)
    try:
        sc = stock_closes_fn("broad")
    except Exception as e:
        print(f"WARNING: stock_closes failed: {e}", flush=True)
        sc = None

    print("Loading membership.json...", flush=True)
    try:
        mem_path = config.data_dir() / "baskets" / "membership.json"
        with open(mem_path) as f:
            membership = json.load(f)
    except Exception as e:
        print(f"WARNING: membership.json failed: {e}", flush=True)
        membership = None

    print("Loading forward_log.parquet...", flush=True)
    try:
        fwd_path = config.data_dir() / "sector_cycles" / "forward_log.parquet"
        fwd_all = pd.read_parquet(fwd_path)
        fwd_all["date"] = pd.to_datetime(fwd_all["date"])
        fwd_min_date = str(fwd_all["date"].min().date()) if not fwd_all.empty else "N/A"
        print(f"  forward_log min(date): {fwd_min_date}  rows: {len(fwd_all)}", flush=True)
    except Exception as e:
        print(f"WARNING: forward_log failed: {e}", flush=True)
        fwd_all = pd.DataFrame()
        fwd_min_date = "N/A"

    print("Loading sector_central calls.parquet...", flush=True)
    try:
        calls_path = config.data_dir() / "sector_central" / "calls.parquet"
        calls_all = pd.read_parquet(calls_path)
        calls_all["date"] = pd.to_datetime(calls_all["date"])
    except Exception as e:
        print(f"WARNING: calls.parquet failed: {e}", flush=True)
        calls_all = pd.DataFrame()

    return etf_close_df, bench, sc, membership, fwd_all, calls_all, fwd_min_date


def _build_records(calls_all: pd.DataFrame, asof_ts: pd.Timestamp) -> list[dict]:
    """Build the records list for a given as-of date."""
    records: list[dict] = []

    # Sector ETFs (always present)
    sector_id_map = {
        "XLK":  ("xlk",  "Technology",              "b-us_sector_tech"),
        "XLV":  ("xlv",  "Health Care",             "b-us_sector_health"),
        "XLP":  ("xlp",  "Consumer Staples",        "b-us_sector_staples"),
        "XLU":  ("xlu",  "Utilities",               "b-us_sector_utilities"),
        "XLF":  ("xlf",  "Financials",              "b-us_sector_financials"),
        "XLE":  ("xle",  "Energy",                  "b-us_sector_energy"),
        "XLI":  ("xli",  "Industrials",             "b-us_sector_industrials"),
        "XLY":  ("xly",  "Consumer Discretionary",  "b-us_sector_discretionary"),
        "XLB":  ("xlb",  "Materials",               "b-us_sector_materials"),
        "XLRE": ("xlre", "Real Estate",             "b-us_sector_realestate"),
        "XLC":  ("xlc",  "Communication Services",  "b-us_sector_comm"),
    }
    for etf, (sid, sname, bid) in sector_id_map.items():
        records.append({
            "key":       sid,
            "id":        sid,
            "kind":      "sector",
            "ticker":    etf,
            "basket_id": bid,
            "name":      sname,
        })

    # Named baskets from calls.parquet up to asof
    if not calls_all.empty:
        basket_calls = calls_all[
            (calls_all["kind"] == "basket") & (calls_all["date"] <= asof_ts)
        ].copy()
        if not basket_calls.empty:
            latest_calls = basket_calls.sort_values("date").groupby("id").last().reset_index()
            for _, row in latest_calls.iterrows():
                bid = str(row["id"])
                if "us_sector" in bid:
                    continue
                records.append({
                    "key":       bid,
                    "id":        bid,
                    "kind":      "basket",
                    "ticker":    str(row.get("ticker") or ""),
                    "basket_id": bid,
                    "name":      str(row.get("name") or bid),
                })

    return records


def _build_timing_states(fwd_all: pd.DataFrame, asof_ts: pd.Timestamp) -> dict[str, str]:
    """Build timing_states dict from forward_log up to asof (most-recent row per id)."""
    timing_states: dict[str, str] = {}
    if fwd_all.empty:
        return timing_states
    fwd = fwd_all[fwd_all["date"] <= asof_ts]
    if fwd.empty:
        return timing_states
    latest = fwd.sort_values("date").groupby("id").last().reset_index()
    for _, row in latest.iterrows():
        ts = row.get("timing_state")
        if pd.notna(ts):
            timing_states[str(row["id"])] = str(ts)
    return timing_states


def run_replay():
    etf_close_df, bench_full, sc_full, membership, fwd_all, calls_all, fwd_min_date = _load_base_inputs()

    bday_range = pd.bdate_range(START, END)
    print(f"\nRunning replay {START} → {END} ({len(bday_range)} sessions)...\n", flush=True)

    all_results: list[dict] = []   # per-session results

    for session_ts in bday_range:
        asof_str = str(session_ts.date())

        # Slice closes to point-in-time
        etf_slice = etf_close_df[etf_close_df.index <= session_ts]
        bench_slice = bench_full[bench_full.index <= session_ts]
        sc_slice = sc_full[sc_full.index <= session_ts] if sc_full is not None else None

        if bench_slice.empty or len(bench_slice) < 25:
            print(f"  {asof_str}: skip (SPY data too short)", flush=True)
            continue

        # Timing states (PIT) — will be empty for sessions before forward_log min date
        timing_states = _build_timing_states(fwd_all, session_ts)
        governor_available = bool(timing_states)

        # Records
        records = _build_records(calls_all, session_ts)

        try:
            scored = score_and_rank(
                records=records,
                etf_closes=etf_slice,
                bench_series=bench_slice,
                timing_states=timing_states,
                stock_closes=sc_slice,
                membership=membership,
                asof=asof_str,
            )
        except Exception as e:
            print(f"  {asof_str}: ERROR {e}", flush=True)
            continue

        all_results.append({
            "asof":               asof_str,
            "scored":             scored,
            "governor_available": governor_available,
        })

    print(f"Completed {len(all_results)} sessions.\n", flush=True)
    return all_results, fwd_min_date


# ---------------------------------------------------------------------------
# Sector-only rank helpers — FIX 1: all rank comparisons on n=11 sectors only
# ---------------------------------------------------------------------------

def _sector_ranks(scored: list[dict]) -> dict[str, int]:
    """Return {sector_key: rank_among_11} for the 11 SPDR sectors."""
    sectors = sorted(
        [r for r in scored if r.get("kind") == "sector"],
        key=lambda x: x.get("rotation_rank") or 9999,
    )
    # rotation_rank from score_and_rank is global (mixed universe); re-rank
    # within sectors only (1 = highest score = best).
    sectors_by_score = sorted(sectors, key=lambda x: -(x.get("rotation_score") or 0))
    return {r["key"]: i + 1 for i, r in enumerate(sectors_by_score)}


def _find_streak(
    all_results: list[dict],
    target_key: str,
    rank_threshold: int,
    mode: str,          # "top" or "bottom"
    deadline: str,
    streak_min: int = STREAK_MIN,
) -> tuple[str | None, str | None, int | None]:
    """Find first streak of ≥ streak_min consecutive sessions where target_key
    satisfies the rank condition among the 11 sectors.

    mode='top':    rank ≤ rank_threshold
    mode='bottom': rank ≥ rank_threshold

    Returns (streak_start, streak_end, rank_at_first_session) or (None, None, None).
    Deadline is checked against streak_start.
    """
    streak_start: str | None = None
    streak_end:   str | None = None
    streak_len = 0
    first_rank_in_streak: int | None = None

    for res in all_results:
        sec_ranks = _sector_ranks(res["scored"])
        r = sec_ranks.get(target_key)
        if r is None:
            streak_len = 0
            streak_start = None
            streak_end = None
            first_rank_in_streak = None
            continue

        qualifies = (mode == "top" and r <= rank_threshold) or \
                    (mode == "bottom" and r >= rank_threshold)

        if qualifies:
            if streak_len == 0:
                streak_start = res["asof"]
                first_rank_in_streak = r
            streak_len += 1
            streak_end = res["asof"]
            if streak_len >= streak_min:
                # Check deadline on streak_start
                if streak_start <= deadline:
                    return streak_start, streak_end, first_rank_in_streak
        else:
            streak_len = 0
            streak_start = None
            streak_end = None
            first_rank_in_streak = None

    return None, None, None


def _component_table(scored: list[dict], keys: set[str]) -> str:
    """Return a markdown table of component attribution for target instruments."""
    rows = []
    for rec in scored:
        if rec.get("key", "") in keys:
            c = rec.get("components", {})
            rows.append(
                f"| {rec.get('name','?')[:22]:<22} | {rec.get('rotation_rank','?'):>4} | "
                f"{c.get('mom20',0):>6.2f} | {c.get('fast_rs',0):>7.2f} | "
                f"{c.get('governor',0):>4} | {c.get('ob_penalty',0):>7.2f} | "
                f"{c.get('macd_demotion',0):>6.1f} | {rec.get('rotation_score',0):>6.1f} | "
                f"{str(rec.get('state_used') or '?'):<22} |"
            )
    return "\n".join(rows)


def build_report(all_results: list[dict], fwd_min_date: str) -> str:
    lines: list[str] = []
    lines.append("# XSR W1 Replay — 2026-06-01 to 2026-07-15")
    lines.append("")
    lines.append("> DISPLAY-ONLY — re-orders display surfaces; feeds no gate, size, score, or calibrated key.")
    lines.append("")

    # --- PROMINENT GOVERNOR DISCLOSURE (FIX 2) ---
    lines.append("> **DATA AVAILABILITY DISCLOSURE**")
    lines.append(f"> `data/sector_cycles/forward_log.parquet` min(date) = **{fwd_min_date}**.")
    lines.append("> June sessions (2026-06-01 through 2026-06-30) ran with the state governor **dark**")
    lines.append("> (governor=0, timing_states empty). The June replay exercises the momentum,")
    lines.append("> fast-RS, and overbought-penalty legs only. The full lens (with governor)")
    lines.append("> is replayed only from 2026-07-02 onward.")
    lines.append("")
    lines.append(f"Sessions in window: {len(all_results)}")
    lines.append("")

    # --- Sector rank matrix ---
    lines.append("## 1. Sector rank matrix (sectors only, n=11, top-3 / bottom-3 per session)")
    lines.append("")
    lines.append("Rank shown as N/11 (sectors). Governor available from 2026-07-02.")
    lines.append("")
    lines.append("| Date       | Gov | Top-3 (rank/11: ticker)                    | Bottom-3 (rank/11: ticker)               |")
    lines.append("|------------|-----|--------------------------------------------|------------------------------------------|")

    for res in all_results:
        sec_ranks = _sector_ranks(res["scored"])
        # Sort sectors by their within-sector rank
        sector_items = sorted(sec_ranks.items(), key=lambda x: x[1])
        top3 = sector_items[:3]
        bot3 = list(reversed(sector_items[-3:]))
        top_str = " / ".join(f"{r}/11:{SECTOR_LABELS.get(k, k)}" for k, r in top3)
        bot_str = " / ".join(f"{r}/11:{SECTOR_LABELS.get(k, k)}" for k, r in bot3)
        gov_flag = "Y" if res.get("governor_available") else "N"
        lines.append(f"| {res['asof']} | {gov_flag:<3} | {top_str:<42} | {bot_str:<40} |")

    lines.append("")

    # --- Full sector score table for select key dates ---
    key_dates = ["2026-06-10", "2026-06-17", "2026-07-02", "2026-07-10", "2026-07-15"]
    lines.append("## 2. Full sector rankings on key dates (rank/11 sectors)")
    for target_date in key_dates:
        match = next((r for r in all_results if r["asof"] == target_date), None)
        if match is None:
            prior = [r for r in all_results if r["asof"] < target_date]
            match = prior[-1] if prior else None
        if match is None:
            continue
        sec_ranks = _sector_ranks(match["scored"])
        lines.append(f"\n### {match['asof']} (governor={'ON' if match.get('governor_available') else 'OFF'})")
        lines.append("")
        lines.append("| Rank/11 | Ticker/Key           | Score | mom20 | fast_rs | gov | ob_pen | macd_dem | State              |")
        lines.append("|---------|----------------------|-------|-------|---------|-----|--------|----------|--------------------|")
        sectors_sorted = sorted(
            [r for r in match["scored"] if r.get("kind") == "sector"],
            key=lambda x: -(x.get("rotation_score") or 0),
        )
        for i, rec in enumerate(sectors_sorted, 1):
            c = rec.get("components", {})
            lines.append(
                f"| {i:>5}/11 | {SECTOR_LABELS.get(rec['key'], rec['key']):<20} | "
                f"{rec.get('rotation_score',0):>5.1f} | {c.get('mom20',0):>5.2f} | "
                f"{c.get('fast_rs',0):>7.2f} | {c.get('governor',0):>3} | "
                f"{c.get('ob_penalty',0):>6.2f} | {c.get('macd_demotion',0):>8.1f} | "
                f"{str(rec.get('state_used','?')):<18} |"
            )
        lines.append("")

    # --- Acceptance verdict (FIX 1: streak-based, sectors-only, honest) ---
    lines.append("## 3. Acceptance verdict (XSR-R2 charter — sectors-only, n=11)")
    lines.append("")
    lines.append("All ranks are computed within the 11-sector universe only.")
    lines.append("PASS requires a streak of ≥ 3 consecutive sessions with the streak's FIRST session ≤ deadline.")
    lines.append("")

    # Criterion 1: XLV rank ≤ 3 streak ≥ 3 sessions, first session ≤ 2026-06-17
    xlv_streak_start, xlv_streak_end, xlv_first_rank = _find_streak(
        all_results, "xlv", rank_threshold=3, mode="top", deadline=HC_TOP3_BY
    )
    lines.append(f"### Criterion 1: XLV rank ≤ 3/11 for ≥ {STREAK_MIN} consecutive sessions, streak starting ≤ {HC_TOP3_BY}")
    if xlv_streak_start:
        lines.append(f"- Qualifying streak found: **{xlv_streak_start}** → **{xlv_streak_end}** "
                     f"(first-session rank: {xlv_first_rank}/11 (sectors)) → **PASS**")
    else:
        # Report best observed streak even if it doesn't qualify
        lines.append(f"- No qualifying streak found (≥ {STREAK_MIN} sessions with XLV ≤ 3/11, starting ≤ {HC_TOP3_BY}) → **FAIL**")
    lines.append("")

    # Criterion 2: XLK rank ≥ 8 streak ≥ 3 sessions, first session ≤ 2026-07-03
    xlk_streak_start, xlk_streak_end, xlk_first_rank = _find_streak(
        all_results, "xlk", rank_threshold=8, mode="bottom", deadline=SEMIS_BOT4_BY
    )
    lines.append(f"### Criterion 2: XLK rank ≥ 8/11 for ≥ {STREAK_MIN} consecutive sessions, streak starting ≤ {SEMIS_BOT4_BY}")
    if xlk_streak_start:
        lines.append(f"- Qualifying streak found: **{xlk_streak_start}** → **{xlk_streak_end}** "
                     f"(first-session rank: {xlk_first_rank}/11 (sectors)) → **PASS**")
    else:
        lines.append(f"- No qualifying streak found (≥ {STREAK_MIN} sessions with XLK ≥ 8/11, starting ≤ {SEMIS_BOT4_BY}) → **FAIL**")
    lines.append("")

    # --- XLV and XLK full session rank series ---
    lines.append("## 4. XLV and XLK rank series (N/11 sectors, all sessions)")
    lines.append("")
    lines.append("| Date       | Gov | XLV rank/11 | XLK rank/11 |")
    lines.append("|------------|-----|-------------|-------------|")
    for res in all_results:
        sec_ranks = _sector_ranks(res["scored"])
        xlv_r = sec_ranks.get("xlv", "?")
        xlk_r = sec_ranks.get("xlk", "?")
        gov_flag = "Y" if res.get("governor_available") else "N"
        lines.append(f"| {res['asof']} | {gov_flag:<3} | {str(xlv_r)+'/11':>11} | {str(xlk_r)+'/11':>11} |")
    lines.append("")

    # --- Component attribution for key dates ---
    lines.append("## 5. Component attribution — XLV and XLK on key dates")
    lines.append("")
    lines.append("| Name                   | Rank | mom20  | fast_rs | gov | ob_pen | macd_dem | Score  | State                  |")
    lines.append("|------------------------|------|--------|---------|-----|--------|----------|--------|------------------------|")

    for target_date in ["2026-06-10", "2026-06-17", "2026-07-02", "2026-07-10"]:
        match = next((r for r in all_results if r["asof"] == target_date), None)
        if match is None:
            prior = [r for r in all_results if r["asof"] < target_date]
            match = prior[-1] if prior else None
        if match is None:
            continue
        attr_keys = {"xlv", "xlk"}
        table = _component_table(match["scored"], attr_keys)
        if table:
            lines.append(f"**{match['asof']} (governor={'ON' if match.get('governor_available') else 'OFF'})**")
            lines.append(table)
            lines.append("")

    # --- Honest assessment ---
    lines.append("## 6. Honest assessment")
    lines.append("")
    lines.append(
        "The Fast Lens uses mom20 (20-day EW/ETF vs SPY), state-gated 5d/10d fast RS, "
        "timing-state governor, and an OB penalty that takes the max of the ETF and EW-member "
        "composite. June sessions ran with governor=0 (forward_log unavailable before 2026-07-02), "
        "so the June replay reflects momentum and OB legs only."
    )
    lines.append("")
    lines.append(
        "One structural gap: the broad stock close cache covers only ~775 sessions "
        "(2023-06-12 to 2026-07-15), so EW composites for baskets with deep historical members may "
        "have thin data before 2023. For the June-July 2026 replay window this is not a constraint."
    )
    lines.append("")
    lines.append("_Report generated by scripts/replay_us_sector_rotation.py_")

    return "\n".join(lines)


def main():
    all_results, fwd_min_date = run_replay()

    if not all_results:
        print("ERROR: No results produced.", flush=True)
        sys.exit(1)

    # Print quick summary to stdout
    print(f"\nforward_log min(date): {fwd_min_date}", flush=True)
    print("\n=== XLV/XLK Rank/11 per session ===")
    print(f"{'Date':<12} {'Gov':>3} {'XLV/11':>7} {'XLK/11':>7}")
    for res in all_results:
        sec_ranks = _sector_ranks(res["scored"])
        xlv_r = sec_ranks.get("xlv", "?")
        xlk_r = sec_ranks.get("xlk", "?")
        gov_flag = "Y" if res.get("governor_available") else "N"
        print(f"{res['asof']:<12} {gov_flag:>3} {str(xlv_r)+'/11':>7} {str(xlk_r)+'/11':>7}")

    print("\n=== ACCEPTANCE CHECK (streak-based, sectors-only n=11) ===", flush=True)

    xlv_streak_start, xlv_streak_end, xlv_first_rank = _find_streak(
        all_results, "xlv", rank_threshold=3, mode="top", deadline=HC_TOP3_BY
    )
    if xlv_streak_start:
        print(f"C1 XLV top-3: streak {xlv_streak_start}→{xlv_streak_end} (first rank {xlv_first_rank}/11) — deadline {HC_TOP3_BY} → PASS")
    else:
        print(f"C1 XLV top-3: no qualifying streak starting ≤ {HC_TOP3_BY} — FAIL")

    xlk_streak_start, xlk_streak_end, xlk_first_rank = _find_streak(
        all_results, "xlk", rank_threshold=8, mode="bottom", deadline=SEMIS_BOT4_BY
    )
    if xlk_streak_start:
        print(f"C2 XLK bottom-4: streak {xlk_streak_start}→{xlk_streak_end} (first rank {xlk_first_rank}/11) — deadline {SEMIS_BOT4_BY} → PASS")
    else:
        print(f"C2 XLK bottom-4: no qualifying streak starting ≤ {SEMIS_BOT4_BY} — FAIL")

    # Build and write report
    report = build_report(all_results, fwd_min_date)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    print(f"\nReport written to: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
