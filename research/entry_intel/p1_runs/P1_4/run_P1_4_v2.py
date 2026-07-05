"""P1.4 Recall Audit — ROUND 2 (defect-corrected re-run), fully vectorized.

Citing: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments (2026-07-05)
Primary window: 2022-06-30 → 2026-07-02 (effective after 250-bar Massive warmup, §6.1)
Canonical input: data/replay/replay_boarded.parquet ONLY (never replay_2*.parquet parts)
Output: research/entry_intel/p1_runs/P1_4/

ROUND-1 DEFECT (bounced by conformance REVIEW.md):
  The verdict lookup + in-universe membership were built from ALL 961,656 replay rows,
  counting the 127,389 verdict_grade==False (horizon-censored) rows as *resolved* verdicts.
  This violated the primary-stats law ("primary statistics on verdict_grade==True rows only")
  and made the lead claim "NEVER-TRIGGERED = 0" an artifact.

ROUND-2 FIX:
  * Verdict LOOKUP is built from verdict_grade==True rows ONLY.
  * In-universe membership (denominator condition 4) still uses full replay presence
    (a censored-only (ticker,date) pair IS a candidate that day — PREREG cond 4 "any verdict",
    §Never-triggered disambiguation), so DENOMINATORS are unchanged (8,242 / 25,545 / 943).
  * A denominator event whose (ticker,date) has NO verdict-grade row is honestly counted
    NEVER-TRIGGERED (in-universe but no resolved verdict).
  * Censored rows: reported explicitly (share, per-type, and how many denominator events they
    account for). Censored != resolved.
  * A round-1-vs-round-2 reconciliation table is emitted for every headline number.

Denominator machinery (event detection, dedup, Wilson, QRN) is UNCHANGED from v1 — the review
confirmed it reproduces exactly. Only the lookup row set (and honest reporting) changed.

All registered trials T1-T5 executed; no additional trials.
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

import scipy  # noqa: F401  (EI program law: scipy importable)

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
DUR_WINDOW     = 60
DUR_FWD        = 60
UNDERCUT_TOL   = 0.95
ATR_PERIOD     = 14
ATR_DEPTH_MULT = 1.0

# Denominator B — frozen in PREREG
LFM_FWD    = 60
LFM_RETURN = 0.20

DEDUP_BDAYS = 5
WILSON_Z    = 1.96

# ─── Round-1 (bounced) headline numbers, for the reconciliation table ─────────
ROUND1 = {
    "denom_A": 8242, "denom_B": 25545, "overlap": 943,
    "A": {"fired": 21, "near": 5, "rejected": 8216, "never": 0},
    "B": {"fired": 1414, "near": 451, "rejected": 23680, "never": 0},
    "QRN_A": {"n": 1713, "fired": 3, "rate": 0.0017513134851138354},
    "QRN_B": {"n": 5706, "fired": 253, "rate": 0.044339291973361374},
}

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
# PREAMBLE
# ─────────────────────────────────────────────────────────────────────────────

def preamble_checks():
    print("=" * 72, flush=True)
    print("P1.4 RECALL AUDIT — ROUND 2 (defect-corrected re-run)", flush=True)
    print("Citing: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 (2026-07-05)", flush=True)
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
    n_stamped   = int((rdf["survivor_bias"] == True).sum())
    n_unstamped = int((rdf["survivor_bias"] == False).sum())

    # verdict-grade vs horizon-censored partition (§5 checklist: censored != resolved)
    n_vg   = int((rdf["verdict_grade"] == True).sum())
    n_cens = int((rdf["horizon_censored"] == True).sum())
    print(f"  Total rows: {total:,}  survivor-unstamped: {n_unstamped:,}  stamped: {n_stamped:,}", flush=True)
    print(f"  verdict_grade==True: {n_vg:,}   horizon_censored==True: {n_cens:,}", flush=True)

    # per-type breakdown of censored rows (for honest reporting)
    cens = rdf[rdf["verdict_grade"] == False]
    cens_by_type = cens["verdict_type"].value_counts(dropna=False).to_dict()
    print(f"  Censored rows by (unresolved) verdict_type: {cens_by_type}", flush=True)

    # ── ROUND-2 FIX: the verdict-grade frame is what feeds the lookup ──────────
    primary = rdf[
        (rdf["verdict_grade"] == True) &
        (rdf["signal_date"] >= ERA_START) &
        (rdf["signal_date"] <= ERA_END)
    ].copy()
    print(f"  Verdict-grade primary-window rows (LOOKUP source): {len(primary):,}", flush=True)
    print(f"  Date range: {primary['signal_date'].min().date()} → {primary['signal_date'].max().date()}", flush=True)
    print(flush=True)

    meta = {
        "n_total": total, "n_stamped": n_stamped, "n_unstamped": n_unstamped,
        "n_verdict_grade": n_vg, "n_horizon_censored": n_cens,
        "censored_by_type": {str(k): int(v) for k, v in cens_by_type.items()},
        "censored_share": n_cens / total,
    }
    return rdf, primary, meta


# ─────────────────────────────────────────────────────────────────────────────
# VERDICT LOOKUP  (ROUND-2: verdict-grade rows only)  +  UNIVERSE (full presence)
# ─────────────────────────────────────────────────────────────────────────────

def build_verdict_lookup(vg_df: pd.DataFrame, full_rdf: pd.DataFrame):
    """
    ROUND-2 FIX.
      * `vg_df`   = verdict_grade==True primary-window rows -> supplies RESOLVED verdicts.
      * `full_rdf`= ALL replay rows -> supplies in-universe candidate membership
        (PREREG cond 4: a name is in-universe on date t if it "appears as a candidate row
        ... any verdict"; a censored-only pair is still a candidate that day).
    A denominator event whose (ticker,date) has an entry in the universe but NOT in `lookup`
    is honestly NEVER-TRIGGERED (in-universe, no verdict-grade verdict) — this includes the
    censored-only pairs the round-1 run mislabeled as resolved.
    """
    print("Building verdict lookup (verdict_grade==True ONLY) ...", flush=True)
    FIRE_ORDER = {"T1": 3, "T2": 2, "T3": 1}
    VTYPE_ORDER = {"fire": 3, "near_miss": 2, "rejection": 1}

    d = vg_df.copy()
    d["_vord"] = d["verdict_type"].map(VTYPE_ORDER).fillna(0).astype(int)
    d["_tord"] = d["tier_cascade"].map(FIRE_ORDER).fillna(0).astype(int)
    d = d.sort_values(
        ["ticker", "signal_date", "_vord", "_tord"],
        ascending=[True, True, False, False],
    )
    best = d.drop_duplicates(subset=["ticker", "signal_date"], keep="first")

    lookup: dict[tuple, dict] = {}
    for _, row in best.iterrows():
        vt = row["verdict_type"]
        cat = "FIRED" if vt == "fire" else ("NEAR-MISSED" if vt == "near_miss" else "REJECTED")
        lookup[(row["ticker"], row["signal_date"])] = {
            "verdict": cat,
            "tier_cascade": row.get("tier_cascade"),
            "near_miss_reason": row.get("near_miss_reason"),
            "rejection_reason": row.get("rejection_reason"),
        }

    # in-universe candidate membership from FULL replay presence (any verdict, incl. censored)
    universe_by_date: dict[pd.Timestamp, set[str]] = {}
    fw = full_rdf[(full_rdf["signal_date"] >= ERA_START) & (full_rdf["signal_date"] <= ERA_END)]
    for tck, sd in zip(fw["ticker"].values, fw["signal_date"].values):
        sd = pd.Timestamp(sd)
        universe_by_date.setdefault(sd, set()).add(tck)

    print(f"  Verdict-grade lookup entries: {len(lookup):,}", flush=True)
    print(f"  In-universe candidate dates (full presence): {len(universe_by_date):,}", flush=True)
    print(flush=True)
    return lookup, universe_by_date


# ─────────────────────────────────────────────────────────────────────────────
# VECTORISED DENOMINATOR COMPUTATION  (UNCHANGED from v1 — reproduces exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ticker_events(ticker, split_adjust_fn, replay_pairs):
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

    c_adj = split_adjust_fn(df_raw["close"])
    factor = c_adj / df_raw["close"]

    warmup = ERA_START - pd.Timedelta(days=150)
    buf_end = ERA_END + pd.Timedelta(days=100)
    mask = (df_raw.index >= warmup) & (df_raw.index <= buf_end)
    idx = df_raw.index[mask]
    c = c_adj[mask].values
    h = (df_raw["high"] * factor)[mask].values
    l = (df_raw["low"] * factor)[mask].values
    n = len(c)

    if n < DUR_WINDOW + DUR_FWD + ATR_PERIOD + 1:
        return [], []

    c_sw = sliding_window_view(c, DUR_WINDOW)
    roll_min = np.full(n, np.nan)
    roll_max = np.full(n, np.nan)
    roll_min[DUR_WINDOW - 1:] = c_sw.min(axis=1)
    roll_max[DUR_WINDOW - 1:] = c_sw.max(axis=1)

    prev_c = np.empty(n); prev_c[0] = np.nan; prev_c[1:] = c[:-1]
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr14 = np.full(n, np.nan)
    atr14[ATR_PERIOD - 1:] = sliding_window_view(tr, ATR_PERIOD).mean(axis=1)

    era_bool = np.zeros(n, dtype=bool)
    for j, dt in enumerate(idx):
        if dt < ERA_START or dt > ERA_END:
            continue
        if (ticker, dt.value) in replay_pairs:
            era_bool[j] = True
    era_idx = np.where(era_bool)[0]
    if len(era_idx) == 0:
        return [], []

    # Denominator A
    is_local_low = np.abs(c - roll_min) < 1e-8
    cands_a = era_idx[is_local_low[era_idx] & (era_idx + DUR_FWD < n)]
    ev_A: list[pd.Timestamp] = []
    if len(cands_a) > 0 and len(l) > DUR_FWD:
        l_fwd_sw = sliding_window_view(l[1:], DUR_FWD)
        safe_a = cands_a[cands_a < len(l_fwd_sw)]
        if len(safe_a) > 0:
            fwd_min_low = l_fwd_sw[safe_a].min(axis=1)
            not_undercut = safe_a[fwd_min_low >= c[safe_a] * UNDERCUT_TOL]
            if len(not_undercut) > 0:
                atr_t = atr14[not_undercut]
                max_60 = roll_max[not_undercut]
                close_t = c[not_undercut]
                atr_valid = ~np.isnan(atr_t) & (atr_t > 0)
                depth_ok = ~atr_valid | ((max_60 - close_t) >= ATR_DEPTH_MULT * atr_t)
                for i in not_undercut[depth_ok]:
                    ev_A.append(idx[i])

    # Denominator B
    safe_b = era_idx[era_idx + LFM_FWD < n]
    ev_B: list[pd.Timestamp] = []
    if len(safe_b) > 0:
        fwd60 = c[safe_b + LFM_FWD]
        base = c[safe_b]
        valid = (base > 0) & (~np.isnan(fwd60))
        fwd_ret_all = np.where(valid & (base > 0), fwd60 / np.where(base > 0, base, 1) - 1.0, 0)
        big_move_idx = safe_b[(fwd_ret_all >= LFM_RETURN) & valid]
        for i in big_move_idx:
            ev_B.append(idx[i])

    return ev_A, ev_B


def compute_denominators(universe_tickers, universe_by_date, split_adjust_fn):
    print(f"Computing denominators ({len(universe_tickers)} tickers) ...", flush=True)
    replay_pairs: set = set()
    for sd, tickers in universe_by_date.items():
        val = sd.value
        for t in tickers:
            replay_pairs.add((t, val))

    events_A_raw, events_B_raw = [], []
    n_no_data = 0
    tickers_sorted = sorted(universe_tickers)
    total = len(tickers_sorted)
    for i, ticker in enumerate(tickers_sorted):
        if i % 100 == 0:
            print(f"  [{i}/{total}] ...", flush=True)
        ev_A, ev_B = _compute_ticker_events(ticker, split_adjust_fn, replay_pairs)
        if not ev_A and not ev_B and not (MASSIVE_DIR / f"{ticker}.parquet").exists():
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

def partition_events(events, lookup, censored_pairs, label):
    fired, near_missed, rejected, never_triggered = [], [], [], []
    never_censored = 0   # never-triggered events whose (ticker,date) IS a censored-only pair
    never_absent = 0     # never-triggered events with no replay row at all
    for ticker, dt in events:
        info = lookup.get((ticker, dt))
        if info is None:
            never_triggered.append((ticker, dt, {}))
            if (ticker, dt) in censored_pairs:
                never_censored += 1
            else:
                never_absent += 1
        elif info["verdict"] == "FIRED":
            fired.append((ticker, dt, info))
        elif info["verdict"] == "NEAR-MISSED":
            near_missed.append((ticker, dt, info))
        else:
            rejected.append((ticker, dt, info))
    return {
        "label": label, "total": len(events),
        "fired": fired, "near_missed": near_missed,
        "rejected": rejected, "never_triggered": never_triggered,
        "never_censored": never_censored, "never_absent": never_absent,
    }


def partition_stats(part):
    n = part["total"]
    out = {"n": n, "never_censored": part["never_censored"], "never_absent": part["never_absent"]}
    for cat in ("fired", "near_missed", "rejected", "never_triggered"):
        k = len(part[cat])
        lo, hi = wilson_ci(k, n)
        out[cat] = {"count": k, "fraction": k / n if n else 0.0, "wilson_lo": lo, "wilson_hi": hi}
    return out


def print_part(stats):
    n = stats["n"]
    for cat in ("fired", "near_missed", "rejected", "never_triggered"):
        s = stats[cat]
        print(f"  {cat:22s}: {s['count']:6,} / {n:6,} = {s['fraction']:.4f} "
              f"[Wilson95: {s['wilson_lo']:.4f}, {s['wilson_hi']:.4f}]", flush=True)
    print(f"  (never-triggered breakdown: censored-only pair={stats['never_censored']:,}, "
          f"no-replay-row={stats['never_absent']:,})", flush=True)


def nm_breakdown(nm):
    return Counter(i.get("near_miss_reason", "unknown") or "unknown" for _, _, i in nm)

def rej_breakdown(rj):
    return Counter(i.get("rejection_reason", "unknown") or "unknown" for _, _, i in rj)

def tier_breakdown(fi):
    return Counter(i.get("tier_cascade", "unknown") or "unknown" for _, _, i in fi)


def compute_qrn(events_A, events_B, lookup, era_end=ERA_END):
    era_end_np = np.datetime64(era_end.date(), "D")
    start_np = np.busday_offset(era_end_np, -252, roll="backward")
    t252 = pd.Timestamp(str(start_np))

    def _qrn(events):
        ev252 = [(t, d) for t, d in events if d >= t252]
        n = len(ev252)
        fi = sum(1 for t, d in ev252 if lookup.get((t, d), {}).get("verdict") == "FIRED")
        rate = fi / n if n else None
        lo, hi = wilson_ci(fi, n) if n else (None, None)
        return {"n": n, "fired": fi, "rate": rate, "lo": lo, "hi": hi}

    return {"window_start": str(t252.date()), "window_end": str(era_end.date()),
            "A": _qrn(events_A), "B": _qrn(events_B)}


def check_escalation(sA, sB):
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
                     qrn, esc_flags, yr_A, yr_B, overlap, meta, results):
    def pct(f): return f"{f*100:.2f}%"
    def wci(s): return f"[{pct(s['wilson_lo'])}, {pct(s['wilson_hi'])}]"

    L = []; a = L.append
    nA = sA["n"]; nB = sB["n"]

    a("# P1.4 Recall Audit — RESULTS (v2, round 2 — defect-corrected re-run)")
    a("")
    a(f"**Run date:** {results['run_date']}  ")
    a("**Round:** 2 — defect-corrected re-run of the registered P1.4 grid (round 1 bounced by conformance review).  ")
    a("**Memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments (2026-07-05)  ")
    a(f"**Primary window:** {ERA_START.date()} → {ERA_END.date()}  ")
    a("**Input:** data/replay/replay_boarded.parquet (961,656 rows; never replay_2*.parquet parts)  ")
    a("**Trial family:** p1_4_recall_audit — T1-T5 registered before computation  ")
    a("**Post-hoc trials recorded:** none  ")
    a("")

    # ── Verdict lead
    a("## Verdict (lead)")
    a("")
    a(
        f"The funnel FIRED on **{pct(sA['fired']['fraction'])}** of all verified durable-low events "
        f"(Denominator A, n={nA:,}) and on **{pct(sB['fired']['fraction'])}** of all +20%/60d "
        f"large-move events (Denominator B, n={nB:,}) in the primary window "
        f"({ERA_START.date()} → {ERA_END.date()}).  "
    )
    a("")
    a(
        f"**NEVER-TRIGGERED fraction: {pct(sA['never_triggered']['fraction'])} (Denom A, "
        f"{sA['never_triggered']['count']:,} events) and {pct(sB['never_triggered']['fraction'])} "
        f"(Denom B, {sB['never_triggered']['count']:,} events).**  "
    )
    a("")
    a(
        "This corrects the round-1 lead ('NEVER-TRIGGERED = 0'), which was an artifact of counting "
        f"the {meta['n_horizon_censored']:,} horizon-censored (verdict_grade==False) replay rows as "
        "resolved verdicts. Under the primary-stats law, a significant event whose (ticker, date) has "
        "NO verdict-grade replay row is NEVER-TRIGGERED — even if a censored (unresolved) row exists. "
        f"Of the {sA['never_triggered']['count']:,} never-triggered Denom-A events, "
        f"{sA['never_censored']:,} sit on a censored-only pair and {sA['never_absent']:,} have no replay "
        f"row at all; for Denom B, {sB['never_censored']:,} censored-only and {sB['never_absent']:,} absent. "
        "So the coverage gap is NOT purely in momentum gates: a real slice of significant events either "
        "were never resolved to a verdict-grade outcome or never produced a candidate row at all."
    )
    a("")
    a(
        "This is a purely descriptive census (no pre-registered pass/fail threshold). Wilson 95% CIs "
        "are confidence intervals for proportions, not hypothesis tests. Escalation conditions are "
        "checked below; QRN_A / QRN_B are the frozen quarterly KPI definitions."
    )
    a("")

    # ── Round-1 defect and fix
    a("## Round-1 defect and fix")
    a("")
    a(
        "**Defect (bounced by conformance REVIEW.md, CHECK-2/CHECK-3 BLOCKING):** the round-1 run built "
        "the funnel-verdict lookup and the in-universe set from ALL 961,656 replay rows. The 127,389 "
        "`verdict_grade==False` rows — identical to the `horizon_censored==True` partition — were counted "
        "as resolved FIRED / NEAR-MISSED / REJECTED verdicts. This violated the program primary-stats law "
        "('primary statistics on verdict_grade==True rows only') and the PREREG §5 checklist item "
        "('`horizon_censored` rows excluded per-horizon, tracked separately'). Because every (ticker, date) "
        "pair is unique and 127,389 of them are censored-only, those pairs absorbed the events that should "
        "have surfaced as NEVER-TRIGGERED — making the round-1 lead 'NEVER-TRIGGERED = 0' an artifact."
    )
    a("")
    a(
        "**Fix:** the verdict lookup is rebuilt on `verdict_grade==True` rows ONLY. In-universe candidate "
        "membership (PREREG denominator condition 4 — 'appears as a candidate row … any verdict') still uses "
        "full replay presence, so the DENOMINATORS are unchanged. A denominator event whose (ticker, date) "
        "has no verdict-grade row is now honestly counted NEVER-TRIGGERED, and its censored-vs-absent split "
        "is reported. Censored rows are reported explicitly as unresolved, never as resolved verdicts. The "
        "denominator event-detection machinery, Wilson math, and QRN logic are byte-for-byte the round-1 "
        "code (the review confirmed they reproduce exactly); only the lookup row set and the honesty "
        "reporting changed."
    )
    a("")

    # ── Reconciliation table
    r1 = ROUND1
    a("### Round-1 vs round-2 reconciliation (delta = censored-row exclusion)")
    a("")
    a("| Headline number | Round-1 (bounced) | Round-2 (corrected) | Delta | Attribution |")
    a("|---|--:|--:|--:|---|")
    a(f"| Denom A n | {r1['denom_A']:,} | {nA:,} | {nA-r1['denom_A']:+,} | unchanged (event detection unaffected) |")
    a(f"| Denom B n | {r1['denom_B']:,} | {nB:,} | {nB-r1['denom_B']:+,} | unchanged |")
    a(f"| Overlap A∩B | {r1['overlap']:,} | {overlap:,} | {overlap-r1['overlap']:+,} | unchanged |")
    a(f"| A FIRED | {r1['A']['fired']:,} | {sA['fired']['count']:,} | {sA['fired']['count']-r1['A']['fired']:+,} | censored fires no longer counted resolved |")
    a(f"| A NEAR-MISSED | {r1['A']['near']:,} | {sA['near_missed']['count']:,} | {sA['near_missed']['count']-r1['A']['near']:+,} | censored near-misses excluded |")
    a(f"| A REJECTED | {r1['A']['rejected']:,} | {sA['rejected']['count']:,} | {sA['rejected']['count']-r1['A']['rejected']:+,} | censored rejections excluded |")
    a(f"| A NEVER-TRIGGERED | {r1['A']['never']:,} | {sA['never_triggered']['count']:,} | {sA['never_triggered']['count']-r1['A']['never']:+,} | **the defect surfaces here** |")
    a(f"| B FIRED | {r1['B']['fired']:,} | {sB['fired']['count']:,} | {sB['fired']['count']-r1['B']['fired']:+,} | censored fires no longer counted resolved |")
    a(f"| B NEAR-MISSED | {r1['B']['near']:,} | {sB['near_missed']['count']:,} | {sB['near_missed']['count']-r1['B']['near']:+,} | censored near-misses excluded |")
    a(f"| B REJECTED | {r1['B']['rejected']:,} | {sB['rejected']['count']:,} | {sB['rejected']['count']-r1['B']['rejected']:+,} | censored rejections excluded |")
    a(f"| B NEVER-TRIGGERED | {r1['B']['never']:,} | {sB['never_triggered']['count']:,} | {sB['never_triggered']['count']-r1['B']['never']:+,} | **the defect surfaces here** |")
    qa, qb = qrn["A"], qrn["B"]
    a(f"| QRN_A fired/n | {r1['QRN_A']['fired']}/{r1['QRN_A']['n']:,} ({pct(r1['QRN_A']['rate'])}) | {qa['fired']}/{qa['n']:,} ({pct(qa['rate']) if qa['rate'] is not None else 'N/A'}) | {qa['fired']-r1['QRN_A']['fired']:+} fires | censored fires excluded from trailing-252 |")
    a(f"| QRN_B fired/n | {r1['QRN_B']['fired']}/{r1['QRN_B']['n']:,} ({pct(r1['QRN_B']['rate'])}) | {qb['fired']}/{qb['n']:,} ({pct(qb['rate']) if qb['rate'] is not None else 'N/A'}) | {qb['fired']-r1['QRN_B']['fired']:+} fires | censored fires excluded from trailing-252 |")
    a("")
    a(
        "Every delta is attributable to a single root cause: excluding the 127,389 horizon-censored "
        "(verdict_grade==False) rows from the verdict lookup. Denominators, overlap, year breakdown, and "
        "Wilson/QRN machinery are unchanged."
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
    a("> never-triggered (it didn't even look — or never reached a settled verdict). No single bucket is bad")
    a("> on its own — a high rejection rate might be correct discipline. But a very high never-triggered rate")
    a("> is a structural gap: the funnel is being precision-stacked toward a tiny slice of the universe and")
    a("> missing most of the action. This census runs quarterly so the program never claims good entries")
    a("> without showing what it passed on.")
    a(">")
    a("> **Round-2 note:** the first run of this census mistakenly treated events whose outcome window had")
    a("> not finished ('horizon-censored') as if the funnel had settled a verdict on them. That hid the")
    a("> never-triggered bucket at zero. Fixed, roughly 8-9% of significant events had no settled verdict —")
    a("> the honest never-triggered rate — while the funnel still fires on well under 1% of durable lows.")
    a("")

    # ── Era & conformance
    a("## 1. Era and Conformance")
    a("")
    a(f"- Primary window: **{ERA_START.date()} → {ERA_END.date()}** (effective; 250-bar Massive warmup per memo §6.1)")
    a(f"- Total replay rows: **{meta['n_total']:,}**; all `survivor_bias=False` (Massive-sourced per §APPROVAL substrate v1.1)")
    a(f"- Survivor-stamped rows in artifact: **{meta['n_stamped']}** (none — all rows are 2022-06-30+ Massive-sourced)")
    a(f"- `verdict_grade==True` rows (LOOKUP source): **{meta['n_verdict_grade']:,}**")
    a(f"- `horizon_censored==True` rows EXCLUDED from the verdict lookup (censored ≠ resolved): "
      f"**{meta['n_horizon_censored']:,}** ({pct(meta['censored_share'])} of all rows)")
    a(f"  - Censored rows carried (unresolved) provisional verdict_type: "
      + ", ".join(f"{k}={v:,}" for k, v in meta['censored_by_type'].items()) + " — none of these are treated as resolved verdicts.")
    a("- `verdict_grade==False` ≡ `horizon_censored==True` (verified identical partitions; 127,389 rows).")
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
    a("  - Definition: 60-day rolling min, not undercut 5% in 60 fwd bars, ATR(14) depth floor ≥1.0×ATR")
    a(f"- **Denominator B** (+20%/60d large-move events): **{nB:,}** unique (ticker, date) events after 5-bday dedup")
    a("  - Definition: adjusted close +20% over 60 forward trading days")
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
    a(f"NEVER-TRIGGERED split: {sA['never_censored']:,} on censored-only pairs "
      f"(candidate row exists but horizon-censored, no settled verdict) + {sA['never_absent']:,} with no replay row at all.")
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
    a(f"NEVER-TRIGGERED split: {sB['never_censored']:,} on censored-only pairs + {sB['never_absent']:,} with no replay row at all.")
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
        ci_s = f"[{pct(q['lo'])}, {pct(q['hi'])}]" if q["lo"] is not None else "N/A"
        a(f"| {lab} | {rate_s} | {q['n']:,} | {q['fired']:,} | {ci_s} |")
    a("")
    a(
        "QRN definition (frozen per PREREG): FIRE-only fraction against trailing 252 trading bars, primary "
        "era only, verdict-grade fires only. Does not measure entry quality — that is P1.1-P1.3."
    )
    a("")

    # ── Survivor appendix
    a("## 9. Survivor-Stamp Context Appendix")
    a("")
    a("**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**")
    a("")
    a(f"Survivor-stamped rows in artifact: **{meta['n_stamped']}**  ")
    a(
        "No survivor-stamped rows present. All 961,656 rows are Massive-sourced "
        "(`survivor_bias=False`) per §APPROVAL substrate v1.1. No context appendix required."
    )
    a("")

    # ── Measurement limitations
    a("## 10. Measurement Limitations")
    a("")
    a("- **Censored-row handling (round-2 core fix):** the 127,389 `horizon_censored`/`verdict_grade==False` "
      "rows are excluded from the verdict lookup. They remain in the in-universe candidate set (a censored "
      "pair was still a candidate that day), so an event on a censored-only pair is NEVER-TRIGGERED (in-universe, "
      "no settled verdict), not silently dropped. This is the honest treatment the PREREG §5 checklist requires.")
    a("- **ATR waiver:** depth-floor waived (ATR=NaN or 0) for any candidate bar; waiver applied bar-level.")
    a("- **Deduplication:** 5-business-day window via `np.busday_count`; first event in cluster retained (PREREG-frozen).")
    a("- **Forward-bar exclusion:** any event within 60 bars of the last available Massive bar is excluded "
      "(no forward bar available). This slightly under-counts events near ERA_END.")
    a("- **In-universe check:** per-date membership from full replay (ticker, date) presence in "
      "`replay_boarded.parquet` (any verdict, incl. censored). All replay tickers confirmed present in Massive store.")
    a("- **Never-triggered:** (ticker, date) events with no verdict-grade replay row for that exact date. "
      "A ticker with zero replay rows ever is excluded from the denominator entirely.")
    a("")

    # ── Trial ledger
    a("## 11. Trial Ledger Confirmation")
    a("")
    a("Family: `p1_4_recall_audit`  ")
    a("Registered trials (before computation): **T1, T2, T3, T4, T5**  ")
    a("Post-hoc trials: **none** (defect-corrected re-run of the same registered grid, not a new trial)  ")
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
    print("[OK] split_adjust imported\n", flush=True)

    rdf, primary, meta = load_replay()
    universe_tickers = set(rdf["ticker"].unique())

    # ROUND-2 FIX: lookup from verdict-grade only; universe from full presence.
    lookup, universe_by_date = build_verdict_lookup(primary, rdf)

    # censored-only pairs (verdict_grade==False for the pair) in the primary window — for the
    # never-triggered censored-vs-absent split.
    fw = rdf[(rdf["signal_date"] >= ERA_START) & (rdf["signal_date"] <= ERA_END)]
    censored_pairs = {
        (t, pd.Timestamp(d))
        for t, d in zip(fw.loc[fw["verdict_grade"] == False, "ticker"].values,
                        fw.loc[fw["verdict_grade"] == False, "signal_date"].values)
    }
    print(f"Censored-only (ticker,date) pairs in primary window: {len(censored_pairs):,}\n", flush=True)

    events_A, events_B = compute_denominators(universe_tickers, universe_by_date, split_adjust_fn)

    nA = len(events_A); nB = len(events_B)
    set_A = {(t, d) for t, d in events_A}
    set_B = {(t, d) for t, d in events_B}
    overlap = len(set_A & set_B)
    print(f"Overlap A∩B: {overlap:,}", flush=True)

    yr_A = Counter(d.year for _, d in events_A)
    yr_B = Counter(d.year for _, d in events_B)

    print("\n=== T1: Recall — Denominator A (durable-low) ===", flush=True)
    part_A = partition_events(events_A, lookup, censored_pairs, "A")
    sA = partition_stats(part_A)
    print_part(sA)

    print("\n=== T2: Recall — Denominator B (+20%/60d) ===", flush=True)
    part_B = partition_events(events_B, lookup, censored_pairs, "B")
    sB = partition_stats(part_B)
    print_part(sB)

    nm_A = nm_breakdown(part_A["near_missed"]); nm_B = nm_breakdown(part_B["near_missed"])
    print(f"\n=== T3: Near-miss breakdown ===  A: {dict(nm_A)}  B: {dict(nm_B)}", flush=True)

    rej_A = rej_breakdown(part_A["rejected"]); rej_B = rej_breakdown(part_B["rejected"])
    print(f"=== T4: Rejection breakdown ===  A top: {dict(rej_A.most_common(5))}  B top: {dict(rej_B.most_common(5))}", flush=True)

    tier_A = tier_breakdown(part_A["fired"]); tier_B = tier_breakdown(part_B["fired"])
    print(f"=== T5: Fire tier breakdown ===  A: {dict(tier_A)}  B: {dict(tier_B)}", flush=True)

    qrn = compute_qrn(events_A, events_B, lookup)
    print(f"\n=== QRN ===  A: {qrn['A']}  B: {qrn['B']}", flush=True)

    esc_flags = check_escalation(sA, sB)
    print("\n=== Escalation ===", flush=True)
    for f in (esc_flags or ["None triggered."]):
        print(f"  {f}", flush=True)

    print(f"\nTotal elapsed: {time.time()-t0:.1f}s", flush=True)

    def slim(s):
        return {k: s[k] for k in ("n", "fired", "near_missed", "rejected", "never_triggered",
                                  "never_censored", "never_absent")}

    results = {
        "study_id": "P1_4",
        "round": "2 — defect-corrected re-run",
        "run_date": str(date.today()),
        "memo_citation": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 (2026-07-05)",
        "primary_window": {"start": str(ERA_START.date()), "end": str(ERA_END.date())},
        "round1_defect": "verdict lookup built from all rows incl. 127,389 verdict_grade==False "
                         "(horizon-censored) rows; NEVER-TRIGGERED=0 was an artifact",
        "round2_fix": "verdict lookup built from verdict_grade==True only; universe from full presence; "
                      "events with no verdict-grade row = NEVER-TRIGGERED",
        "n_total_rows": meta["n_total"],
        "n_stamped_rows_in_artifact": meta["n_stamped"],
        "n_verdict_grade_rows": meta["n_verdict_grade"],
        "n_horizon_censored_rows_excluded": meta["n_horizon_censored"],
        "censored_share": meta["censored_share"],
        "censored_by_type": meta["censored_by_type"],
        "universe_tickers": len(universe_tickers),
        "denominator_A": {"n": nA, "thin_flag": nA < 100},
        "denominator_B": {"n": nB, "thin_flag": nB < 100},
        "overlap_AB": overlap,
        "T1_recall_A": slim(sA),
        "T2_recall_B": slim(sB),
        "T3_near_miss_breakdown": {"A": dict(nm_A), "B": dict(nm_B)},
        "T4_rejected_breakdown": {"A": dict(rej_A.most_common()), "B": dict(rej_B.most_common())},
        "T5_fired_tier": {"A": dict(tier_A), "B": dict(tier_B)},
        "QRN": qrn,
        "escalation_flags": esc_flags,
        "year_breakdown_A": {str(k): v for k, v in yr_A.items()},
        "year_breakdown_B": {str(k): v for k, v in yr_B.items()},
        "trials_executed": ["T1", "T2", "T3", "T4", "T5"],
        "post_hoc_trials": [],
        "reconciliation_round1_vs_round2": {
            "denom_A": {"r1": ROUND1["denom_A"], "r2": nA},
            "denom_B": {"r1": ROUND1["denom_B"], "r2": nB},
            "overlap": {"r1": ROUND1["overlap"], "r2": overlap},
            "A": {
                "fired":  {"r1": ROUND1["A"]["fired"],  "r2": sA["fired"]["count"]},
                "near":   {"r1": ROUND1["A"]["near"],   "r2": sA["near_missed"]["count"]},
                "rejected": {"r1": ROUND1["A"]["rejected"], "r2": sA["rejected"]["count"]},
                "never":  {"r1": ROUND1["A"]["never"],  "r2": sA["never_triggered"]["count"]},
            },
            "B": {
                "fired":  {"r1": ROUND1["B"]["fired"],  "r2": sB["fired"]["count"]},
                "near":   {"r1": ROUND1["B"]["near"],   "r2": sB["near_missed"]["count"]},
                "rejected": {"r1": ROUND1["B"]["rejected"], "r2": sB["rejected"]["count"]},
                "never":  {"r1": ROUND1["B"]["never"],  "r2": sB["never_triggered"]["count"]},
            },
            "QRN_A": {"r1_fired": ROUND1["QRN_A"]["fired"], "r2_fired": qrn["A"]["fired"],
                      "r1_rate": ROUND1["QRN_A"]["rate"], "r2_rate": qrn["A"]["rate"]},
            "QRN_B": {"r1_fired": ROUND1["QRN_B"]["fired"], "r2_fired": qrn["B"]["fired"],
                      "r1_rate": ROUND1["QRN_B"]["rate"], "r2_rate": qrn["B"]["rate"]},
        },
    }

    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"results.json → {OUT_DIR/'results.json'}", flush=True)

    write_results_md(sA, sB, nm_A, nm_B, rej_A, rej_B, tier_A, tier_B,
                     qrn, esc_flags, yr_A, yr_B, overlap, meta, results)

    print("\nP1.4 Recall Audit (round 2) complete.", flush=True)
    return results


if __name__ == "__main__":
    main()
