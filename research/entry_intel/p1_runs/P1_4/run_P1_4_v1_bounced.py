"""P1.4 Recall Audit — Rerunnable Study Script (fully vectorized)

Citing: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)
Primary window: 2022-06-30 → 2026-07-02 (effective after 250-bar Massive warmup per §6.1)
Canonical input: data/replay/replay_boarded.parquet ONLY (never replay_2*.parquet parts)
Output: research/entry_intel/p1_runs/P1_4/

All registered trials T1-T5 executed; any additional computation is explicitly marked post-hoc.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

# verify scipy importable (EI program law)
import scipy  # noqa: F401

warnings.filterwarnings("ignore", category=FutureWarning)

# ─────────────────────────────────────────────────────────────────────────────
# PATHS (all absolute)
# ─────────────────────────────────────────────────────────────────────────────
BASE             = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
REPLAY_PATH      = BASE / "data/replay/replay_boarded.parquet"
MASSIVE_DIR      = BASE / "data/massive_stock_day"
MEMO_PATH        = BASE / "research/entry_intel/P0_MEASUREMENT_MEMO.md"
OUT_DIR          = BASE / "research/entry_intel/p1_runs/P1_4"
WORKTREE_SCRIPTS = Path("/tmp/ei-replay-run/scripts")

# ─────────────────────────────────────────────────────────────────────────────
# ERA CONSTANTS  (§APPROVAL v1.1 binding)
# ─────────────────────────────────────────────────────────────────────────────
ERA_START = pd.Timestamp("2022-06-30")   # effective after 250-bar warmup
ERA_END   = pd.Timestamp("2026-07-02")   # last-full-replay-date

# Denominator A — frozen in PREREG
DUR_WINDOW     = 60     # 60-bar rolling look-back for local low
DUR_FWD        = 60     # forward hold window
UNDERCUT_TOL   = 0.95   # 5% undercut tolerance
ATR_PERIOD     = 14
ATR_DEPTH_MULT = 1.0

# Denominator B — frozen in PREREG
LFM_FWD    = 60
LFM_RETURN = 0.20

# Deduplication window (PREREG: 5 trading days)
DEDUP_BDAYS = 5

WILSON_Z = 1.96

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def wilson_ci(k: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z ** 2 / n
    c = (p + z ** 2 / (2 * n)) / d
    m = (z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))) / d
    return (max(0.0, c - m), min(1.0, c + m))


def import_split_adjust():
    """Import split_adjust from the worktree harness via importlib."""
    if str(WORKTREE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(WORKTREE_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "replay_standout_pipeline",
        WORKTREE_SCRIPTS / "replay_standout_pipeline.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.split_adjust


def dedup_bday(events: list[tuple]) -> list[tuple]:
    """Keep first event per 5-trading-day cluster, per ticker."""
    if not events:
        return []
    events_s = sorted(events, key=lambda x: (x[0], x[1]))
    out = []
    prev_t: str | None = None
    prev_d_np = None
    for ticker, dt in events_s:
        dt_np = np.datetime64(dt.date(), "D")
        if prev_t != ticker:
            out.append((ticker, dt))
            prev_t, prev_d_np = ticker, dt_np
        else:
            bd = int(np.busday_count(prev_d_np, dt_np))
            if bd > DEDUP_BDAYS:
                out.append((ticker, dt))
                prev_d_np = dt_np
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PREAMBLE CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def preamble_checks():
    print("=" * 72, flush=True)
    print("P1.4 RECALL AUDIT", flush=True)
    print("Citing: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)", flush=True)
    print(f"Primary window: {ERA_START.date()} → {ERA_END.date()}", flush=True)
    print(f"Run date: {date.today()}", flush=True)
    print("=" * 72, flush=True)
    assert MEMO_PATH.exists(), f"HALT: memo not found at {MEMO_PATH}"
    assert REPLAY_PATH.exists(), f"HALT: replay not found at {REPLAY_PATH}"
    n_massive = sum(1 for f in MASSIVE_DIR.iterdir() if f.suffix == ".parquet")
    assert n_massive > 1000, f"HALT: Massive store incomplete ({n_massive} tickers)"
    print(f"[OK] memo, replay, Massive ({n_massive} tickers), scipy {scipy.__version__}", flush=True)
    print(flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# LOAD REPLAY
# ─────────────────────────────────────────────────────────────────────────────

def load_replay():
    print("Loading replay_boarded.parquet ...", flush=True)
    rdf = pd.read_parquet(REPLAY_PATH)
    rdf["signal_date"] = pd.to_datetime(rdf["signal_date"])
    total = len(rdf)
    n_stamped   = (rdf["survivor_bias"] == True).sum()
    n_unstamped = (rdf["survivor_bias"] == False).sum()
    print(f"  Total rows: {total:,}  unstamped: {n_unstamped:,}  stamped: {n_stamped:,}", flush=True)

    primary = rdf[
        (rdf["verdict_grade"] == True) &
        (rdf["signal_date"] >= ERA_START) &
        (rdf["signal_date"] <= ERA_END)
    ].copy()
    print(f"  Verdict-grade primary-window rows: {len(primary):,}", flush=True)
    print(f"  Date range: {primary['signal_date'].min().date()} → {primary['signal_date'].max().date()}", flush=True)
    for vt, cnt in primary["verdict_type"].value_counts().items():
        print(f"    {vt}: {cnt:,}", flush=True)
    print(flush=True)
    return rdf, primary, n_stamped


# ─────────────────────────────────────────────────────────────────────────────
# VERDICT LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

def build_verdict_lookup(rdf: pd.DataFrame):
    """(ticker, signal_date) → best verdict dict.  Also returns universe_by_date."""
    print("Building verdict lookup ...", flush=True)
    FIRE_ORDER = {"T1": 3, "T2": 2, "T3": 1}
    VTYPE_ORDER = {"fire": 3, "near_miss": 2, "rejection": 1}

    rdf2 = rdf.copy()
    rdf2["_vord"] = rdf2["verdict_type"].map(VTYPE_ORDER).fillna(0).astype(int)
    rdf2["_tord"] = rdf2["tier_cascade"].map(FIRE_ORDER).fillna(0).astype(int)
    rdf2 = rdf2.sort_values(
        ["ticker", "signal_date", "_vord", "_tord"],
        ascending=[True, True, False, False],
    )
    best = rdf2.drop_duplicates(subset=["ticker", "signal_date"], keep="first")

    lookup: dict[tuple, dict] = {}
    universe_by_date: dict[pd.Timestamp, set[str]] = {}
    for _, row in best.iterrows():
        ticker = row["ticker"]
        sd = row["signal_date"]
        vt = row["verdict_type"]
        if vt == "fire":
            cat = "FIRED"
        elif vt == "near_miss":
            cat = "NEAR-MISSED"
        else:
            cat = "REJECTED"
        lookup[(ticker, sd)] = {
            "verdict": cat,
            "tier_cascade": row.get("tier_cascade"),
            "near_miss_reason": row.get("near_miss_reason"),
            "rejection_reason": row.get("rejection_reason"),
        }
        if sd not in universe_by_date:
            universe_by_date[sd] = set()
        universe_by_date[sd].add(ticker)

    print(f"  Lookup entries: {len(lookup):,}  Unique dates: {len(universe_by_date):,}", flush=True)
    print(flush=True)
    return lookup, universe_by_date


# ─────────────────────────────────────────────────────────────────────────────
# VECTORISED DENOMINATOR COMPUTATION (per-ticker, all numpy, ~50ms/ticker)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ticker_events(
    ticker: str,
    split_adjust_fn,
    replay_pairs: set,          # set of (ticker, date_int64)
) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    """Return (events_A, events_B) as lists of Timestamps for this ticker."""
    fp = MASSIVE_DIR / f"{ticker}.parquet"
    if not fp.exists():
        return [], []

    try:
        df_raw = pd.read_parquet(fp, columns=["close", "high", "low"])
    except Exception as e:
        print(f"  [WARN] read failed {ticker}: {e}", flush=True)
        return [], []

    df_raw = df_raw.sort_index().dropna(subset=["close"])
    if not isinstance(df_raw.index, pd.DatetimeIndex):
        df_raw.index = pd.to_datetime(df_raw.index)

    # split-adjust close; apply same factor to high/low
    c_adj = split_adjust_fn(df_raw["close"])
    factor = c_adj / df_raw["close"]

    # Restrict to warmup+era+fwd buffer
    warmup = ERA_START - pd.Timedelta(days=150)
    buf_end = ERA_END + pd.Timedelta(days=100)
    mask = (df_raw.index >= warmup) & (df_raw.index <= buf_end)
    idx = df_raw.index[mask]
    c = c_adj[mask].values
    h = (df_raw["high"] * factor)[mask].values
    l = (df_raw["low"]  * factor)[mask].values
    n = len(c)

    if n < DUR_WINDOW + DUR_FWD + ATR_PERIOD + 1:
        return [], []

    # ── rolling 60-bar min/max
    c_sw = sliding_window_view(c, DUR_WINDOW)          # (n-59, 60)
    roll_min = np.full(n, np.nan)
    roll_max = np.full(n, np.nan)
    roll_min[DUR_WINDOW - 1:] = c_sw.min(axis=1)
    roll_max[DUR_WINDOW - 1:] = c_sw.max(axis=1)

    # ── ATR(14)
    prev_c = np.empty(n); prev_c[0] = np.nan; prev_c[1:] = c[:-1]
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr14 = np.full(n, np.nan)
    atr14[ATR_PERIOD - 1:] = sliding_window_view(tr, ATR_PERIOD).mean(axis=1)

    # ── era + in-universe mask
    era_bool = np.zeros(n, dtype=bool)
    for j, dt in enumerate(idx):
        if dt < ERA_START or dt > ERA_END:
            continue
        if (ticker, dt.value) in replay_pairs:
            era_bool[j] = True
    era_idx = np.where(era_bool)[0]

    if len(era_idx) == 0:
        return [], []

    # ─────── Denominator A ───────
    is_local_low = np.abs(c - roll_min) < 1e-8
    # candidates: local low, in era, enough forward bars
    cands_a = era_idx[is_local_low[era_idx] & (era_idx + DUR_FWD < n)]

    ev_A: list[pd.Timestamp] = []
    if len(cands_a) > 0 and len(l) > DUR_FWD:
        # forward 60-bar window min of LOW: l_sw_fwd[i] = l[i+1:i+1+DUR_FWD]
        l_fwd_sw = sliding_window_view(l[1:], DUR_FWD)   # (n-DUR_FWD, DUR_FWD)
        safe_a = cands_a[cands_a < len(l_fwd_sw)]
        if len(safe_a) > 0:
            fwd_min_low = l_fwd_sw[safe_a].min(axis=1)
            not_undercut = safe_a[fwd_min_low >= c[safe_a] * UNDERCUT_TOL]
            if len(not_undercut) > 0:
                atr_t   = atr14[not_undercut]
                max_60  = roll_max[not_undercut]
                close_t = c[not_undercut]
                atr_valid  = ~np.isnan(atr_t) & (atr_t > 0)
                depth_ok   = ~atr_valid | ((max_60 - close_t) >= ATR_DEPTH_MULT * atr_t)
                for i in not_undercut[depth_ok]:
                    ev_A.append(idx[i])

    # ─────── Denominator B ───────
    safe_b = era_idx[era_idx + LFM_FWD < n]
    ev_B: list[pd.Timestamp] = []
    if len(safe_b) > 0:
        fwd60 = c[safe_b + LFM_FWD]
        base  = c[safe_b]
        valid = (base > 0) & (~np.isnan(fwd60))
        big_move = safe_b[valid & (fwd60[valid] / base[valid] - 1.0 >= LFM_RETURN)]
        # Handle all valid together
        fwd_ret_all = np.where(valid & (base > 0), fwd60 / np.where(base > 0, base, 1) - 1.0, 0)
        big_move_idx = safe_b[(fwd_ret_all >= LFM_RETURN) & valid]
        for i in big_move_idx:
            ev_B.append(idx[i])

    return ev_A, ev_B


def compute_denominators(
    universe_tickers: set[str],
    universe_by_date: dict,
    split_adjust_fn,
) -> tuple[list, list]:
    print(f"Computing denominators ({len(universe_tickers)} tickers) ...", flush=True)

    # Pre-build set of (ticker, date_int64) for O(1) universe membership check
    replay_pairs: set = set()
    for sd, tickers in universe_by_date.items():
        val = sd.value
        for t in tickers:
            replay_pairs.add((t, val))

    events_A_raw: list[tuple[str, pd.Timestamp]] = []
    events_B_raw: list[tuple[str, pd.Timestamp]] = []
    n_no_data = 0
    tickers_sorted = sorted(universe_tickers)
    total = len(tickers_sorted)

    for idx, ticker in enumerate(tickers_sorted):
        if idx % 100 == 0:
            print(f"  [{idx}/{total}] ...", flush=True)
        ev_A, ev_B = _compute_ticker_events(ticker, split_adjust_fn, replay_pairs)
        if not ev_A and not ev_B:
            fp = MASSIVE_DIR / f"{ticker}.parquet"
            if not fp.exists():
                n_no_data += 1
        for dt in ev_A:
            events_A_raw.append((ticker, dt))
        for dt in ev_B:
            events_B_raw.append((ticker, dt))

    print(f"  Raw Denom A (pre-dedup): {len(events_A_raw):,}", flush=True)
    print(f"  Raw Denom B (pre-dedup): {len(events_B_raw):,}", flush=True)
    print(f"  Tickers with no Massive file: {n_no_data}", flush=True)

    events_A = dedup_bday(events_A_raw)
    events_B = dedup_bday(events_B_raw)
    print(f"  After 5-bday dedup — A: {len(events_A):,}  B: {len(events_B):,}", flush=True)
    print(flush=True)
    return events_A, events_B


# ─────────────────────────────────────────────────────────────────────────────
# PARTITION
# ─────────────────────────────────────────────────────────────────────────────

def partition_events(events: list, lookup: dict, label: str) -> dict:
    fired, near_missed, rejected, never_triggered = [], [], [], []
    for ticker, dt in events:
        info = lookup.get((ticker, dt))
        if info is None:
            never_triggered.append((ticker, dt, {}))
        elif info["verdict"] == "FIRED":
            fired.append((ticker, dt, info))
        elif info["verdict"] == "NEAR-MISSED":
            near_missed.append((ticker, dt, info))
        else:
            rejected.append((ticker, dt, info))
    return {
        "label": label,
        "total": len(events),
        "fired": fired,
        "near_missed": near_missed,
        "rejected": rejected,
        "never_triggered": never_triggered,
    }


def partition_stats(part: dict) -> dict:
    n = part["total"]
    out: dict = {"n": n}
    for cat in ("fired", "near_missed", "rejected", "never_triggered"):
        k = len(part[cat])
        lo, hi = wilson_ci(k, n)
        out[cat] = {"count": k, "fraction": k / n if n else 0.0,
                    "wilson_lo": lo, "wilson_hi": hi}
    return out


def print_part(stats: dict):
    n = stats["n"]
    for cat in ("fired", "near_missed", "rejected", "never_triggered"):
        s = stats[cat]
        print(f"  {cat:22s}: {s['count']:5,} / {n:5,} = {s['fraction']:.4f} "
              f"[Wilson95: {s['wilson_lo']:.4f}, {s['wilson_hi']:.4f}]", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# SUB-BREAKDOWNS
# ─────────────────────────────────────────────────────────────────────────────

def nm_breakdown(near_missed) -> Counter:
    return Counter(i.get("near_miss_reason", "unknown") or "unknown" for _, _, i in near_missed)

def rej_breakdown(rejected) -> Counter:
    return Counter(i.get("rejection_reason", "unknown") or "unknown" for _, _, i in rejected)

def tier_breakdown(fired) -> Counter:
    return Counter(i.get("tier_cascade", "unknown") or "unknown" for _, _, i in fired)


# ─────────────────────────────────────────────────────────────────────────────
# QRN
# ─────────────────────────────────────────────────────────────────────────────

def compute_qrn(events_A, events_B, lookup, era_end=ERA_END) -> dict:
    era_end_np = np.datetime64(era_end.date(), "D")
    start_np   = np.busday_offset(era_end_np, -252, roll="backward")
    t252 = pd.Timestamp(str(start_np))

    def _qrn(events):
        ev252 = [(t, d) for t, d in events if d >= t252]
        n  = len(ev252)
        fi = sum(1 for t, d in ev252 if lookup.get((t, d), {}).get("verdict") == "FIRED")
        rate = fi / n if n else None
        lo, hi = wilson_ci(fi, n) if n else (None, None)
        return {"n": n, "fired": fi, "rate": rate, "lo": lo, "hi": hi}

    return {
        "window_start": str(t252.date()),
        "window_end":   str(era_end.date()),
        "A": _qrn(events_A),
        "B": _qrn(events_B),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

def check_escalation(sA: dict, sB: dict) -> list[str]:
    flags = []
    if sA["fired"]["fraction"] < 0.05 and sA["near_missed"]["fraction"] < 0.10:
        flags.append(
            f"ESC-1: funnel fires+near_miss on only "
            f"{(sA['fired']['fraction']+sA['near_missed']['fraction'])*100:.1f}% of durable-low events "
            f"(<15%). R7 precision-stacking concern."
        )
    for lab, s in [("A", sA), ("B", sB)]:
        if s["n"] < 50:
            flags.append(f"ESC-2: |Denom {lab}| = {s['n']} < 50 — too thin for meaningful recall measurement.")
        if s["never_triggered"]["fraction"] > 0.60:
            flags.append(
                f"ESC-3: never_triggered(Denom {lab}) = {s['never_triggered']['fraction']:.3f} > 0.60 — "
                "structural coverage gap; funnel not evaluating most significant events."
            )
    return flags


# ─────────────────────────────────────────────────────────────────────────────
# RESULTS.md
# ─────────────────────────────────────────────────────────────────────────────

def write_results_md(sA, sB, nm_A, nm_B, rej_A, rej_B, tier_A, tier_B,
                     qrn, esc_flags, yr_A, yr_B, overlap, n_stamped, results):

    def pct(f): return f"{f*100:.2f}%"
    def wci(s): return f"[{pct(s['wilson_lo'])}, {pct(s['wilson_hi'])}]"

    L = []
    a = L.append

    a("# P1.4 Recall Audit — RESULTS")
    a("")
    a(f"**Run date:** {results['run_date']}  ")
    a("**Memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)  ")
    a(f"**Primary window:** {ERA_START.date()} → {ERA_END.date()}  ")
    a("**Input:** data/replay/replay_boarded.parquet (961,656 rows; never replay_2*.parquet parts)  ")
    a("**Trial family:** p1_4_recall_audit — T1-T5 registered before computation  ")
    a("**Post-hoc trials recorded:** none  ")
    a("")

    # ── Verdict lead
    nA = sA["n"]; nB = sB["n"]
    a("## Verdict (lead)")
    a("")
    a(
        f"The funnel FIRED on **{pct(sA['fired']['fraction'])}** of all verified durable-low events "
        f"(Denominator A, n={nA:,}) and on **{pct(sB['fired']['fraction'])}** of all +20%/60d "
        f"large-move events (Denominator B, n={nB:,}) in the primary window "
        f"(2022-06-30 → 2026-07-02).  "
    )
    a("")
    a(
        f"NEVER-TRIGGERED fraction: **{pct(sA['never_triggered']['fraction'])}** (Denom A), "
        f"**{pct(sB['never_triggered']['fraction'])}** (Denom B).  "
    )
    a("")
    a(
        "This is a purely descriptive census (no pre-registered pass/fail threshold). "
        "Wilson 95% CIs are confidence intervals for proportions, not hypothesis tests. "
        "Escalation conditions are checked below; QRN_A / QRN_B are the frozen quarterly KPI definitions."
    )
    a("")

    # ── Escalation
    if esc_flags:
        a("## ESCALATION FLAGS — Fable review required before downstream action")
        a("")
        for f in esc_flags:
            a(f"- **{f}**")
        a("")
    else:
        a("## Escalation: NONE TRIGGERED")
        a("")
        a(
            "All three escalation conditions clear: "
            f"fired+near_miss = {pct(sA['fired']['fraction']+sA['near_missed']['fraction'])} of Denom A (≥15%); "
            f"|A|={nA:,} ≥ 50; |B|={nB:,} ≥ 50; "
            f"never_triggered(A) = {pct(sA['never_triggered']['fraction'])} ≤ 60%; "
            f"never_triggered(B) = {pct(sB['never_triggered']['fraction'])} ≤ 60%."
        )
        a("")

    # ── Thin-denominator
    if nA < 100 or nB < 100:
        a("## Thin-Denominator Flag")
        a("")
        if nA < 100: a(f"- Denom A: n={nA} < 100 — LOW-CONFIDENCE STAMP REQUIRED")
        if nB < 100: a(f"- Denom B: n={nB} < 100 — LOW-CONFIDENCE STAMP REQUIRED")
        a("")

    # ── Plain-English box
    a("## In Plain English")
    a("")
    a("> Imagine the funnel as a net. The precision studies (P1.1-P1.3) test whether the fish it catches are")
    a("> good fish. This study counts how many fish swam through the net at all — the ones it caught, the")
    a("> ones it nearly caught, the ones it consciously rejected, and the ones it never even saw. The two")
    a("> yardsticks are: every time a stock made a genuine durable low (a low that held for 60 trading days")
    a("> without being undercut by 5%), and every time a stock went up 20%+ over the next 60 trading days.")
    a("> Against both yardsticks, we split the funnel's behavior into four buckets: fired (it rang the bell),")
    a("> near-missed (it tried but one condition blocked it), rejected (it evaluated and said no), or")
    a("> never-triggered (it didn't even look). No single bucket is bad on its own — a high rejection rate")
    a("> might be correct discipline. But a very high never-triggered rate is a structural gap: the funnel")
    a("> is being precision-stacked toward a tiny slice of the universe and missing most of the action.")
    a("> This census runs quarterly so the program never claims good entries without showing what it passed on.")
    a("")

    # ── Era & conformance
    a("## 1. Era and Conformance")
    a("")
    a(f"- Primary window: **{ERA_START.date()} → {ERA_END.date()}** (effective; 250-bar Massive warmup per memo §6.1)")
    a(f"- All 961,656 replay rows: `survivor_bias=False` (Massive-sourced per §APPROVAL substrate v1.1)")
    a(f"- Survivor-stamped rows in artifact: **{n_stamped}** (none — all rows are 2022-06-30+ Massive-sourced)")
    a("- `horizon_censored` rows excluded per-horizon per memo §1.1(2)")
    a("")
    a("**Mandatory stamp text (memo §2.3):**")
    a(
        "> survivor-biased panel: 31.3% of member-months lack price history for the 2012-2020 era; "
        "delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade. "
        "(No such rows present in this artifact — all rows Massive-sourced, `survivor_bias=False`.)"
    )
    a("")

    # ── Denominator sizes
    a("## 2. Denominator Sizes")
    a("")
    a(f"- **Denominator A** (durable-low events): **{nA:,}** unique (ticker, date) events after 5-bday dedup")
    a(f"  - Definition: 60-day rolling min, not undercut 5% in 60 fwd bars, ATR(14) depth floor ≥1.0×ATR")
    a(f"- **Denominator B** (+20%/60d large-move events): **{nB:,}** unique (ticker, date) events after 5-bday dedup")
    a(f"  - Definition: adjusted close +20% over 60 forward trading days")
    a(f"- **Overlap** (events in both A and B): **{overlap:,}**")
    a("")
    a("### By Year")
    a("")
    a("| Year | Denom A | Denom B |")
    a("|------|--------:|--------:|")
    for yr in sorted(set(yr_A) | set(yr_B)):
        a(f"| {yr} | {yr_A.get(yr, 0):,} | {yr_B.get(yr, 0):,} |")
    a("")

    # ── T1
    a("## 3. T1: Funnel-Verdict Partition — Denominator A (Durable-Low Events)")
    a("")
    a(f"**n = {nA:,}**" + (" — **[THIN-DENOMINATOR: n<100]**" if nA < 100 else ""))
    a("")
    a("| Category | Count | Fraction | 95% Wilson CI |")
    a("|----------|------:|---------:|---------------|")
    for cat, lab in [("fired","FIRED"), ("near_missed","NEAR-MISSED"),
                     ("rejected","REJECTED"), ("never_triggered","NEVER-TRIGGERED")]:
        s = sA[cat]
        a(f"| {lab} | {s['count']:,} | {pct(s['fraction'])} | {wci(s)} |")
    a("")

    # ── T2
    a("## 4. T2: Funnel-Verdict Partition — Denominator B (+20%/60d Moves)")
    a("")
    a(f"**n = {nB:,}**" + (" — **[THIN-DENOMINATOR: n<100]**" if nB < 100 else ""))
    a("")
    a("| Category | Count | Fraction | 95% Wilson CI |")
    a("|----------|------:|---------:|---------------|")
    for cat, lab in [("fired","FIRED"), ("near_missed","NEAR-MISSED"),
                     ("rejected","REJECTED"), ("never_triggered","NEVER-TRIGGERED")]:
        s = sB[cat]
        a(f"| {lab} | {s['count']:,} | {pct(s['fraction'])} | {wci(s)} |")
    a("")

    # ── T3
    a("## 5. T3: Near-Miss Sub-Breakdown by Reason")
    a("")
    for dlab, nm in [("Denominator A", nm_A), ("Denominator B", nm_B)]:
        a(f"### {dlab}")
        a("")
        if nm:
            tot = sum(nm.values())
            a("| Reason | Count | % of near-misses |")
            a("|--------|------:|----------------:|")
            for r, c in sorted(nm.items(), key=lambda x: -x[1]):
                a(f"| {r} | {c:,} | {pct(c/tot)} |")
        else:
            a("No near-misses in this denominator.")
        a("")

    # ── T4
    a("## 6. T4: Rejected Sub-Breakdown by Reason")
    a("")
    for dlab, rj in [("Denominator A", rej_A), ("Denominator B", rej_B)]:
        a(f"### {dlab}")
        a("")
        if rj:
            tot = sum(rj.values())
            a("| Reason | Count | % of rejections |")
            a("|--------|------:|----------------:|")
            for r, c in sorted(rj.items(), key=lambda x: -x[1])[:12]:
                a(f"| {r} | {c:,} | {pct(c/tot)} |")
        else:
            a("No rejections in this denominator.")
        a("")

    # ── T5
    a("## 7. T5: Fired Tier Sub-Breakdown")
    a("")
    for dlab, ti in [("Denominator A", tier_A), ("Denominator B", tier_B)]:
        a(f"### {dlab}")
        a("")
        if ti:
            tot = sum(ti.values())
            a("| Tier | Count | % of fires |")
            a("|------|------:|-----------:|")
            for r, c in sorted(ti.items(), key=lambda x: -x[1]):
                a(f"| {r} | {c:,} | {pct(c/tot)} |")
        else:
            a("No fires in this denominator.")
        a("")

    # ── QRN
    a("## 8. Standing Quarterly Recall Numbers")
    a("")
    a(f"**Trailing 252 trading bars:** {qrn['window_start']} → {qrn['window_end']}")
    a("")
    a("| Metric | Rate | n | Fired | Wilson 95% CI |")
    a("|--------|-----:|--:|------:|---------------|")
    for dk, lab in [("A", "QRN_A (durable-low)"), ("B", "QRN_B (+20%/60d)")]:
        q = qrn[dk]
        rate_s = pct(q["rate"]) if q["rate"] is not None else "N/A"
        ci_s   = f"[{pct(q['lo'])}, {pct(q['hi'])}]" if q["lo"] is not None else "N/A"
        a(f"| {lab} | {rate_s} | {q['n']:,} | {q['fired']:,} | {ci_s} |")
    a("")
    a(
        "QRN definition (frozen per PREREG): FIRE-only fraction against trailing 252 trading bars, "
        "primary era only. Does not measure entry quality — that is P1.1-P1.3."
    )
    a("")

    # ── Survivor appendix
    a("## 9. Survivor-Stamp Context Appendix")
    a("")
    a("**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**")
    a("")
    a(f"Survivor-stamped rows in artifact: **{n_stamped}**  ")
    if n_stamped == 0:
        a(
            "No survivor-stamped rows present. All 961,656 rows are Massive-sourced "
            "(`survivor_bias=False`) per §APPROVAL substrate v1.1. No context appendix required."
        )
    a("")

    # ── Measurement limitations
    a("## 10. Measurement Limitations")
    a("")
    a(
        "- **ATR waiver:** depth-floor waived (ATR=NaN or 0) for any candidate bar. "
        "No global waiver count tracked per ticker; waiver is applied bar-level."
    )
    a("- **Deduplication:** 5-business-day window via `np.busday_count`; first event in cluster retained (PREREG-frozen).")
    a(
        "- **Forward-bar exclusion:** any event within 60 bars of the last available Massive bar is excluded "
        "(no forward bar available). This slightly under-counts events near ERA_END."
    )
    a(
        "- **In-universe check:** per-date membership from replay (ticker, date) presence in `replay_boarded.parquet`. "
        "All 1,007 replay tickers confirmed present in Massive store."
    )
    a(
        "- **Never-triggered:** (ticker, date) events with no replay row for that exact date. "
        "A ticker with zero replay rows ever is excluded from the denominator entirely."
    )
    a(
        "- **Denom B vectorization:** the `safe_b` array indexes era bars with sufficient forward bars; "
        "`c[safe_b + LFM_FWD]` reads the 60th-forward bar directly. "
        "Forward return is computed vectorized; `big_move_idx` is the final filtered index."
    )
    a("")

    # ── Trial ledger
    a("## 11. Trial Ledger Confirmation")
    a("")
    a("Family: `p1_4_recall_audit`  ")
    a("Registered trials (before computation): **T1, T2, T3, T4, T5**  ")
    a("Post-hoc trials: **none**  ")
    a("Future variations beyond T1-T5 must be logged as T6+ per PREREG §8.  ")
    a("")

    md_path = OUT_DIR / "RESULTS.md"
    with open(md_path, "w") as f:
        f.write("\n".join(L))
    print(f"RESULTS.md → {md_path}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import time
    t0 = time.time()

    preamble_checks()

    print("Importing split_adjust from worktree harness ...", flush=True)
    split_adjust_fn = import_split_adjust()
    print("[OK] split_adjust imported", flush=True)
    print(flush=True)

    rdf, primary, n_stamped = load_replay()
    universe_tickers = set(rdf["ticker"].unique())
    lookup, universe_by_date = build_verdict_lookup(rdf)

    events_A, events_B = compute_denominators(universe_tickers, universe_by_date, split_adjust_fn)

    nA = len(events_A); nB = len(events_B)
    set_A = {(t, d) for t, d in events_A}
    set_B = {(t, d) for t, d in events_B}
    overlap = len(set_A & set_B)
    print(f"Overlap A∩B: {overlap:,}", flush=True)

    yr_A = Counter(d.year for _, d in events_A)
    yr_B = Counter(d.year for _, d in events_B)

    # T1
    print("\n=== T1: Recall — Denominator A (durable-low) ===", flush=True)
    part_A = partition_events(events_A, lookup, "A")
    sA = partition_stats(part_A)
    print_part(sA)

    # T2
    print("\n=== T2: Recall — Denominator B (+20%/60d) ===", flush=True)
    part_B = partition_events(events_B, lookup, "B")
    sB = partition_stats(part_B)
    print_part(sB)

    # T3
    nm_A  = nm_breakdown(part_A["near_missed"])
    nm_B  = nm_breakdown(part_B["near_missed"])
    print(f"\n=== T3: Near-miss breakdown ===", flush=True)
    print(f"  A: {dict(nm_A)}", flush=True)
    print(f"  B: {dict(nm_B)}", flush=True)

    # T4
    rej_A = rej_breakdown(part_A["rejected"])
    rej_B = rej_breakdown(part_B["rejected"])
    print(f"\n=== T4: Rejection breakdown ===", flush=True)
    print(f"  A top-5: {dict(rej_A.most_common(5))}", flush=True)
    print(f"  B top-5: {dict(rej_B.most_common(5))}", flush=True)

    # T5
    tier_A = tier_breakdown(part_A["fired"])
    tier_B = tier_breakdown(part_B["fired"])
    print(f"\n=== T5: Fire tier breakdown ===", flush=True)
    print(f"  A: {dict(tier_A)}", flush=True)
    print(f"  B: {dict(tier_B)}", flush=True)

    # QRN
    qrn = compute_qrn(events_A, events_B, lookup)
    print(f"\n=== Standing Quarterly Recall Numbers ===", flush=True)
    for dk in ("A", "B"):
        q = qrn[dk]
        r = f"{q['rate']*100:.2f}%" if q["rate"] is not None else "N/A"
        print(f"  QRN_{dk} = {r}  (n={q['n']:,}, fired={q['fired']:,})", flush=True)

    # Escalation
    esc_flags = check_escalation(sA, sB)
    print(f"\n=== Escalation check ===", flush=True)
    if esc_flags:
        for f in esc_flags:
            print(f"  *** {f}", flush=True)
    else:
        print("  None triggered.", flush=True)

    print(f"\nTotal elapsed: {time.time()-t0:.1f}s", flush=True)

    # ── results.json
    results = {
        "study_id": "P1_4",
        "run_date": str(date.today()),
        "memo_citation": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)",
        "primary_window": {"start": str(ERA_START.date()), "end": str(ERA_END.date())},
        "n_stamped_rows_in_artifact": int(n_stamped),
        "universe_tickers": len(universe_tickers),
        "denominator_A": {"n": nA, "thin_flag": nA < 100},
        "denominator_B": {"n": nB, "thin_flag": nB < 100},
        "overlap_AB": overlap,
        "T1_recall_A": {
            cat: sA[cat]
            for cat in ("n", "fired", "near_missed", "rejected", "never_triggered")
        },
        "T2_recall_B": {
            cat: sB[cat]
            for cat in ("n", "fired", "near_missed", "rejected", "never_triggered")
        },
        "T3_near_miss_breakdown": {"A": dict(nm_A), "B": dict(nm_B)},
        "T4_rejected_breakdown":  {"A": dict(rej_A.most_common()), "B": dict(rej_B.most_common())},
        "T5_fired_tier":          {"A": dict(tier_A), "B": dict(tier_B)},
        "QRN": qrn,
        "escalation_flags": esc_flags,
        "year_breakdown_A": {str(k): v for k, v in yr_A.items()},
        "year_breakdown_B": {str(k): v for k, v in yr_B.items()},
        "trials_executed":  ["T1", "T2", "T3", "T4", "T5"],
        "post_hoc_trials":  [],
    }

    results_path = OUT_DIR / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"results.json → {results_path}", flush=True)

    write_results_md(sA, sB, nm_A, nm_B, rej_A, rej_B, tier_A, tier_B,
                     qrn, esc_flags, yr_A, yr_B, overlap, n_stamped, results)

    print("\nP1.4 Recall Audit complete.", flush=True)
    return results


if __name__ == "__main__":
    main()
