"""CN edition of the veto-leg audit — the BEARISH-DIVERGENCE leg of the buy filter.

MEASUREMENT INSTRUMENT, not a signal.  Mirrors research/signal_engine/veto_leg_audit.py
(the not-topped veto study) and research/cn_prophet_audit/v1_loser_audit.py: production
code paths over committed stores, frozen results committed next to the script, pre-
registered keep rule stated before any number is printed.

MOTIVATING CASE (operator-surfaced 2026-08-04).  湖南黄金 002155.SZ sits −44% off its 252d
high inside the ``cn_gold`` basket while that basket reads phase=Recovery / osc_slope=+12.9
(the strongest measured ex-ante state) with narrative HOT — and its buy is refused with
``gate_reason = "buy blocked by filter: veto: bearish divergence"`` on every stamped board
date in data/china_prophet_rank/candidates.parquet (2026-07-30 … 2026-08-04).  HK removed
its 200dma-reclaim veto after measurement (#4470, 2026-08-03) and its own masterplan named
the divergence leg as the next lever.  The CN divergence leg has never been measured on CN
data.  This script measures it.

NOT A PROMOTION.  In-sample, motivating-only, one window, one market.  The verdict language
is "the leg earns / fails its keep on this window" and it feeds a prereg + ratification —
NEVER a hot removal.  Nothing here changes a shipped gate.

────────────────────────────────────────────────────────────────────────────────
THE LEG, AS PRODUCTION IMPLEMENTS IT (re-derived, not approximated)
────────────────────────────────────────────────────────────────────────────────
engine/signal_quality.py:178  ``_buy_filter(i, sig, bear, n, *, reclaim_veto=True)`` opens
with the divergence test, BEFORE anything else and unconditional on ``reclaim_veto``::

    if bear:
        return False, "veto: bearish divergence"

``bear`` is supplied by the caller, engine/signal_quality.py:238 (inside ``analyze``)::

    ok, reason = _buy_filter(i, sig, _bear_div(i, sig["high"], macd, hi), n,
                             reclaim_veto=reclaim_veto)

engine/signal_quality.py:164 ``_swing_highs(s, w=2)``  — index h is a swing high iff
``v[h] == v[h-2:h+3].max()``.
engine/signal_quality.py:169 ``_bear_div(i, price, macd, hi, look=12)``::

    rh = [h for h in hi if i - look < h <= i]
    return len(rh) >= 2 and pv[rh[-1]] > pv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]

i.e. **the last two confirmed swing highs inside the trailing 12-bar window print a HIGHER
price high against a LOWER RSI-MACD high.**  Everything is on the 3-business-day resample
(``signal_frame``: ``daily_close.resample("3B")``), so ``look=12`` ≈ 36 calendar business
days and one bar ≈ 3 sessions.

CN runs this leg CLOSE-ONLY and on the DEFAULT reclaim_veto=True path:
scripts/build_china_library.py:1960  ``sig_verdict[ticker] = signal_gate.gate(ticker, close)``
→ engine/signal_gate.py:155 ``gate(..., reclaim_veto: bool = True)`` → ``analyze(ticker,
daily_close, reclaim_veto=reclaim_veto)`` with **no daily_high/daily_low**, so
``signal_frame`` takes the ``h3 = l3 = s3`` branch and ``_bear_div``'s ``price`` is the 3D
CLOSE, not an intrabar high.  This instrument reproduces that exactly (close-only).

ENTANGLEMENT: NONE.  The leg is cleanly separable — it is the first statement of
``_buy_filter`` and returns before the reclaim/hold branches are reached, so removing it is
exactly ``_buy_filter(i, sig, False, n, reclaim_veto=True)``.  tests/test_hk_reclaim_veto_
policy.py:77-79 independently pins that the divergence veto is orthogonal to the
``reclaim_veto`` flag.  We therefore audit the leg STANDALONE, and the counterfactual is a
production call, not a reimplementation.

────────────────────────────────────────────────────────────────────────────────
DESIGN (pre-registered; nothing below was chosen after seeing a result)
────────────────────────────────────────────────────────────────────────────────
PANEL      data/china_stocks/*.parquet, names with >= MIN_BARS daily bars.  Every series is
           truncated at GRADE_ASOF first (frozen replay — the stores accrue a bar nightly).
WINDOW     a fire counts iff its ANCHOR date (below) falls in [WIN_START, WIN_END].

FIRE       the production buy event: ``CB[i] or revBuy[i]`` on the 3B signal frame — the
           same ``is_buy`` test analyze() uses at engine/signal_quality.py:236.

CELLS      per fire, with ``bear`` = ``_bear_div(...)`` and the production filter run twice,
           once as production sees it and once with the divergence leg removed:

             prod_ok = _buy_filter(i, sig, bear,  n, reclaim_veto=True)   # shipped
             cf_ok   = _buy_filter(i, sig, False, n, reclaim_veto=True)   # veto removed

             VETOED          bear ∧ fire                       (what the leg refuses today)
             VETOED_ADMIT    bear ∧ fire ∧ cf_ok is True       ← the DECISION SET: exactly
                             the fires that removing the leg would newly admit
             ADMITTED        ¬bear ∧ fire ∧ prod_ok is True    ← today's takes

           VETOED_ADMIT vs ADMITTED is the only apples-to-apples pair: on both sides every
           non-divergence leg of the filter says take, and the ONLY difference is the
           divergence state.  VETOED (all) is reported as the gross block count.

ANCHOR     ⚠ MARKER-DATE GRADING IS FORBIDDEN (engine/signal_quality.py:190-201; CN-1 §W6-CN).
           ``_buy_filter`` reads bars i+1 / i+2, and ``_swing_highs(w=2)`` confirms a high at
           index h only at h+2.  Both are covered by anchoring on the LAST DAILY SESSION OF
           3B BAR i+2 — the first close at which the label is knowable.  Proven leak-free
           for the divergence leg: ``_bear_div`` filters ``h <= i``, and every h <= i is
           confirmed by i+2, so the full-series ``hi`` list yields the same ``rh`` a
           point-in-time recomputation would.  ``resample("3B")`` labels buckets on the LEFT
           edge, so the anchor is resolved through an explicit bucket→last-daily-date map,
           never by reading the bar label as a close date.

RULER      house CN convention (engine/china_standout_track.py:742 ``_t1_fill`` /:775
           ``_fwd_excess``): entry = T+1 **HL2** ((high+low)/2) after the anchor close;
           **locked-limit T+1 bars (high==low==close) are EXCLUDED, never fabricated**;
           outcome = CSI300-relative (510300.SS) forward excess at H=10 and H=21 sessions.
           The production helper prefers a true T+1 open when the column exists; the brief
           pins HL2, so HL2 is primary and the open-preferring production fill is carried as
           a sensitivity (``fill_convention_sensitivity`` in the JSON).

METRICS    n · win% (excess > 0) with Wilson 95% CI · median/mean excess · MAE-tail p10
           (10th percentile of the worst intrabar drawdown from fill over the horizon —
           the deep-tail, not the median) · catastrophic share (ABSOLUTE return <= -15%).

DEDUP      within-cell, 5 trading sessions per name (the veto_leg_audit.py convention).
           Cross-cell dedup is deliberately NOT applied: it would let one cell's fire
           density suppress the other's.  Raw undeduped counts are printed as diagnostics.

KEEP RULE (PRE-REGISTERED — mirrors research/signal_engine/VETO_LEG_AUDIT.md's ">= +3pp on
the verdict metric" and the HK removal's return-leg + risk-leg pairing):

    The bearish-divergence veto EARNS ITS KEEP on a cell iff, on that cell,
      (R) RETURN leg: win%(VETOED_ADMIT) <= win%(ADMITTED) - KEEP_MARGIN_PP, or
      (K) RISK   leg: catastrophic%(VETOED_ADMIT) >= catastrophic%(ADMITTED) + KEEP_MARGIN_PP,
                      or MAE-p10(VETOED_ADMIT) <= MAE-p10(ADMITTED) - KEEP_MARGIN_PP,
    on a cell with n >= MIN_CELL_N on BOTH sides.  Clearing EITHER leg = EARNS.
    Clearing NEITHER = FAILS its keep on this window.  n below the floor = UNDECIDED
    (printed, never read as a pass).  KEEP_MARGIN_PP = 3.0 (house constant).

STRATIFIERS (all point-in-time; every one of them declares its own coverage)
    * basket cycle state at fire — reconstructed through the PRODUCTION path
      (engine.baskets_china.compute_china_baskets → engine.china_sector_cycles._basket_series
      → engine.sector_cycles._record_core) on the series TRUNCATED at the stamp date.  P0
      gate: the reconstruction must reproduce the shipped 2026-08-03 cn_gold read
      (Recovery / pos 13.5 / osc_slope 12.9, data/china_sector_cycles/forward_log.parquet)
      before any cycle cell is printed.  Stamped WEEKLY (last session of each week) and
      matched to the last stamp <= the fire anchor — no basket cycle history exists before
      2026-06-26 (forward_log), so this is a reconstruction, and weekly keeps it inside the
      render budget; phase and a 22-bar osc_slope are both week-scale states.
      Cell "Recovery+/Trough+" = phase in {Recovery, Trough} AND osc_slope > 0.
    * dd_from_high tercile — 252-session drawdown at the anchor close, terciles cut on the
      pooled fire population.
    * narrative level — engine.china_narrative_tags.narrative_heat on the closes panel
      truncated at the same weekly stamp (HOT / WARMING / none, the production thresholds).
    * half-split robustness — first vs second half of the window by anchor date.

LIMITATIONS (also restated in the MD)
    One year, one market, in-sample, no out-of-sample holdout.  Basket membership is
    hindsight-curated (engine/baskets_china.py module docstring says so) — the cycle and
    narrative stratifiers inherit that.  H=21 cannot mature for fires anchored after roughly
    2026-07-02, so the H=21 cells are smaller and end-loaded.  Name-clustered dependence is
    not modelled; name concentration is reported instead.

Run from repo root:  python3 research/cn_prophet_audit/cn_divergence_veto_audit.py
                     python3 research/cn_prophet_audit/cn_divergence_veto_audit.py --quick
Outputs: research/cn_prophet_audit/cn_divergence_veto_results.json (frozen)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import baskets_china as bc
from engine import china_narrative_tags as cnt
from engine import china_sector_cycles as csc
from engine import sector_cycles as sc
from engine import signal_quality as sq

# ── frozen-replay pins ───────────────────────────────────────────────────────
GRADE_ASOF = pd.Timestamp("2026-08-04")   # last bar in the committed stores at build time
WIN_START = pd.Timestamp("2025-08-01")
WIN_END = pd.Timestamp("2026-07-31")
MIN_BARS = 250                            # brief: >=250-bar names
HORIZONS = (10, 21)
BENCH = "510300.SS"
DEDUP_SESSIONS = 5
CATASTROPHIC_PP = -15.0                   # ABSOLUTE return <= -15%
KEEP_MARGIN_PP = 3.0                      # house constant (VETO_LEG_AUDIT.md)
MIN_CELL_N = 100                          # below this a cell is UNDECIDED, never a pass

# P0 gate — the shipped cn_gold cycle read this instrument must reproduce
P0_CYCLE = {"basket": "cn_gold", "date": "2026-08-03",
            "phase": "Recovery", "pos": 13.5, "osc_slope": 12.9}
CASE_TICKER = "002155.SZ"
CASE_DATE = pd.Timestamp("2026-08-03")

OUT = Path(__file__).parent / "cn_divergence_veto_results.json"
DATA = ROOT / "data"


# ── small stats helpers ──────────────────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion, in percent."""
    if n <= 0:
        return None, None
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100.0 * (c - h), 2), round(100.0 * (c + h), 2)


def _f(x, nd: int = 2):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else round(v, nd)


def _pct(vals: list[float], q: float):
    return _f(np.percentile(vals, q)) if vals else None


def summarise(events: list[dict], h: int) -> dict:
    """Cell statistics at one horizon.  ``bool(...)``/``== True`` only — never ``is True``
    (a numpy scalar is never the ``True`` singleton, and an identity test would silently
    zero every count)."""
    rows = [e for e in events if e.get(f"exc{h}") is not None]
    exc = [float(e[f"exc{h}"]) for e in rows]
    absr = [float(e[f"abs{h}"]) for e in rows]
    mae = [float(e[f"mae{h}"]) for e in rows if e.get(f"mae{h}") is not None]
    n = len(exc)
    wins = sum(1 for v in exc if v > 0)
    cat = sum(1 for v in absr if v <= CATASTROPHIC_PP)
    lo, hi = wilson(wins, n)
    names = Counter(e["ticker"] for e in rows)
    top5 = sum(c for _, c in names.most_common(5))
    return {
        "n": n,
        "n_names": len(names),
        "win_pct": _f(100.0 * wins / n) if n else None,
        "win_ci95": [lo, hi],
        "median_excess_pct": _pct(exc, 50),
        "mean_excess_pct": _f(np.mean(exc)) if exc else None,
        "median_abs_pct": _pct(absr, 50),
        "mae_p10_pct": _pct(mae, 10),
        "mae_median_pct": _pct(mae, 50),
        "catastrophic_pct": _f(100.0 * cat / n) if n else None,
        "top5_name_share_pct": _f(100.0 * top5 / n) if n else None,
    }


def keep_verdict(vet: dict, adm: dict) -> dict:
    """Apply the PRE-REGISTERED keep rule to one (VETOED_ADMIT, ADMITTED) cell pair."""
    if not vet or not adm or vet["n"] < MIN_CELL_N or adm["n"] < MIN_CELL_N:
        return {"verdict": "UNDECIDED",
                "why": f"n below the {MIN_CELL_N} floor "
                       f"(vetoed_admit={vet.get('n') if vet else 0}, admitted={adm.get('n') if adm else 0})",
                "d_win_pp": _f((vet or {}).get("win_pct", 0) - (adm or {}).get("win_pct", 0))
                if vet and adm and vet.get("win_pct") is not None and adm.get("win_pct") is not None else None}
    d_win = vet["win_pct"] - adm["win_pct"]                     # negative = vetoed worse
    d_cat = (vet["catastrophic_pct"] or 0.0) - (adm["catastrophic_pct"] or 0.0)  # positive = vetoed worse
    d_mae = ((vet["mae_p10_pct"] or 0.0) - (adm["mae_p10_pct"] or 0.0))          # negative = vetoed worse
    r_leg = d_win <= -KEEP_MARGIN_PP
    k_leg = (d_cat >= KEEP_MARGIN_PP) or (d_mae <= -KEEP_MARGIN_PP)
    # Reporting strengthening (NOT a rule change): does the vetoed cell's Wilson 95% CI
    # EXCLUDE the return-leg keep bar (admitted win% - 3pp)?  If the CI lies entirely above
    # the bar, the data rule OUT the protective reading at 95%; if it straddles the bar, the
    # point estimate fails but the interval cannot exclude protection.  Stated both ways so a
    # FAILS verdict is never read as stronger than the interval supports.
    bar = adm["win_pct"] - KEEP_MARGIN_PP
    lo = (vet.get("win_ci95") or [None, None])[0]
    ci_excl = bool(lo is not None and lo > bar)
    return {
        "verdict": "EARNS" if (r_leg or k_leg) else "FAILS",
        "return_leg_pass": bool(r_leg),
        "risk_leg_pass": bool(k_leg),
        "return_keep_bar_win_pct": _f(bar),
        "ci_excludes_keep_bar": ci_excl,
        "d_win_pp": _f(d_win),
        "d_catastrophic_pp": _f(d_cat),
        "d_mae_p10_pp": _f(d_mae),
        "why": (f"win {d_win:+.1f}pp, catastrophic {d_cat:+.1f}pp, MAE-p10 {d_mae:+.1f}pp "
                f"vs the +/-{KEEP_MARGIN_PP}pp bar"),
    }


# ── panel loading ────────────────────────────────────────────────────────────
def _price_frame(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001 — a corrupt store file is skipped, never fatal
        return None
    if "close" not in df.columns:
        return None
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[df.index <= GRADE_ASOF]
    return df if len(df) >= MIN_BARS else None


def bench_close() -> pd.Series:
    df = pd.read_parquet(DATA / "china" / f"{BENCH}.parquet")
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    return s[s.index <= GRADE_ASOF]


def bucket_end_map(close: pd.Series) -> pd.Series:
    """3B bucket LEFT-EDGE label -> the LAST DAILY DATE inside that bucket.

    ``signal_frame`` resamples with ``resample("3B")``, whose index labels the LEFT edge of
    each bucket (memory: marker-date-is-a-bucket-left-edge).  A 3B bar is only complete at
    the last daily session inside it, so this map is what turns 'signal bar i+2' into 'the
    first daily close at which the label was knowable'."""
    idx = pd.Series(close.index, index=close.index)
    return idx.resample("3B").last().dropna()


def t1_fill_hl2(df: pd.DataFrame, d0: pd.Timestamp):
    """(fill, locked, t1_date) using the T+1 **HL2** convention the brief pins.

    Mirrors engine/china_standout_track.py:742 ``_t1_fill`` for the locked-limit test
    (T+1 printed high == low == close is unfillable and MUST be excluded, not fabricated);
    the fill itself is forced to (high+low)/2 rather than the production open-preference."""
    after = df.index[df.index > d0]
    if len(after) == 0:
        return None, False, None
    t1 = after[0]
    row = df.loc[t1]
    hi, lo, cl = row.get("high"), row.get("low"), row.get("close")
    if not (pd.notna(hi) and pd.notna(lo)):
        return None, False, t1
    locked = bool(pd.notna(cl) and float(hi) == float(lo) == float(cl))
    return (float(hi) + float(lo)) / 2.0, locked, t1


def t1_fill_production(df: pd.DataFrame, d0: pd.Timestamp):
    """The production fill (open when the column exists, else HL2) — sensitivity only."""
    after = df.index[df.index > d0]
    if len(after) == 0:
        return None
    row = df.loc[after[0]]
    op = row.get("open") if "open" in df.columns else None
    if op is not None and pd.notna(op):
        return float(op)
    hi, lo = row.get("high"), row.get("low")
    if pd.notna(hi) and pd.notna(lo):
        return (float(hi) + float(lo)) / 2.0
    return None


def outcomes(df: pd.DataFrame, d0: pd.Timestamp, bench: pd.Series) -> dict | None:
    """T+1 HL2 fill, CSI300-relative excess + absolute + MAE at each horizon.

    Returns None when the fire is unfillable (no T+1 bar, or T+1 locked limit)."""
    fill, locked, t1 = t1_fill_hl2(df, d0)
    if fill is None or locked or not fill:
        return {"locked": bool(locked)} if locked else None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    fwd = close[close.index > d0]
    low = pd.to_numeric(df["low"], errors="coerce")
    lowf = low[low.index > d0]
    bslice = bench[bench.index > d0]
    prod_fill = t1_fill_production(df, d0)
    out: dict = {"fill": _f(fill, 4), "t1": str(t1.date()), "locked": False}
    for h in HORIZONS:
        if len(fwd) <= h or len(bslice) <= h:
            out[f"exc{h}"] = out[f"abs{h}"] = out[f"mae{h}"] = out[f"excp{h}"] = None
            continue
        name_ret = 100.0 * (float(fwd.iloc[h]) / fill - 1.0)
        bench_ret = 100.0 * (float(bslice.iloc[h]) / float(bslice.iloc[0]) - 1.0)
        out[f"abs{h}"] = _f(name_ret)
        out[f"exc{h}"] = _f(name_ret - bench_ret)
        seg = lowf.iloc[: h + 1].dropna()
        out[f"mae{h}"] = _f(100.0 * (float(seg.min()) / fill - 1.0)) if len(seg) else None
        out[f"excp{h}"] = (_f(100.0 * (float(fwd.iloc[h]) / prod_fill - 1.0) - bench_ret)
                           if prod_fill else None)
    return out


# ── the replay ───────────────────────────────────────────────────────────────
def scan_name(ticker: str, df: pd.DataFrame, bench: pd.Series) -> tuple[list[dict], Counter]:
    """Replay one name.  Returns (events, per-leg fire-count diagnostics)."""
    diag: Counter = Counter()
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < MIN_BARS:
        return [], diag
    # PRODUCTION-FAITHFUL: close-only, exactly as scripts/build_china_library.py:1960 calls
    # signal_gate.gate(ticker, close) -> analyze(ticker, daily_close) with no high/low.
    sig = sq.signal_frame(close)
    if sig.empty:
        return [], diag
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return [], diag
    n = len(sig)
    macd = sig["macd"]
    hi = sq._swing_highs(sig["high"])
    endmap = bucket_end_map(close)
    cb, revbuy = sig["CB"], sig["revBuy"]
    hh = pd.to_numeric(df["close"], errors="coerce").dropna()
    roll_high = hh.rolling(252, min_periods=60).max()

    events: list[dict] = []
    for i in range(n):
        if not (bool(cb.iloc[i]) or bool(revbuy.iloc[i])):
            continue
        diag["fires_raw"] += 1
        if i + 2 >= n:
            diag["fires_unconfirmable"] += 1
            continue
        anchor_label = sig.index[i + 2]
        d0 = endmap.get(anchor_label)
        if d0 is None or pd.isna(d0):
            diag["fires_no_anchor"] += 1
            continue
        d0 = pd.Timestamp(d0)
        if not (WIN_START <= d0 <= WIN_END):
            continue
        diag["fires_in_window"] += 1

        bear = bool(sq._bear_div(i, sig["high"], macd, hi))
        prod_ok, prod_reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=True)
        cf_ok, cf_reason = sq._buy_filter(i, sig, False, n, reclaim_veto=True)
        # `== True` / bool(), never `is True` — a numpy scalar is not the True singleton.
        prod_take = (prod_ok is not None) and bool(prod_ok)
        cf_take = (cf_ok is not None) and bool(cf_ok)

        if bear:
            diag["vetoed"] += 1
            cell = "VETOED_ADMIT" if cf_take else "VETOED_BLOCKED_ANYWAY"
            diag[cell] += 1
        else:
            diag["not_vetoed"] += 1
            if not prod_take:
                diag["ADMITTED_FAILED_OTHER_LEG"] += 1
                continue
            cell = "ADMITTED"
            diag["ADMITTED"] += 1
        if cell == "VETOED_BLOCKED_ANYWAY":
            continue   # counted, but not comparable: another leg refuses it too

        oc = outcomes(df, d0, bench)
        if oc is None:
            diag["unfillable_no_t1"] += 1
            continue
        if oc.get("locked"):
            diag["unfillable_locked_limit"] += 1
            continue
        dd = None
        if d0 in roll_high.index and pd.notna(roll_high.get(d0)) and float(roll_high.get(d0)):
            dd = _f(100.0 * (float(hh.loc[d0]) / float(roll_high.loc[d0]) - 1.0))
        ev = {"ticker": ticker, "cell": cell, "anchor": str(d0.date()),
              "bar_label": str(pd.Timestamp(anchor_label).date()),
              "signal_bar": str(pd.Timestamp(sig.index[i]).date()),
              "bear": bear, "prod_reason": prod_reason, "cf_reason": cf_reason,
              "dd_from_high_pct": dd}
        ev.update(oc)
        events.append(ev)
    return events, diag


def dedup(events: list[dict]) -> list[dict]:
    """Within-CELL, 5-trading-session dedup per name (veto_leg_audit.py convention).

    Cross-cell dedup is deliberately NOT applied — it would let one cell's fire density
    suppress the other's, which is the comparison being made."""
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in events:
        by[(e["ticker"], e["cell"])].append(e)
    kept: list[dict] = []
    for evs in by.values():
        last = None
        for e in sorted(evs, key=lambda x: x["anchor"]):
            d = pd.Timestamp(e["anchor"])
            if last is not None and len(pd.bdate_range(last, d)) - 1 < DEDUP_SESSIONS:
                continue
            kept.append(e)
            last = d
    return sorted(kept, key=lambda x: (x["anchor"], x["ticker"]))


# ── stratifier reconstruction ────────────────────────────────────────────────
def weekly_stamps(chart_dates: list[str]) -> list[pd.Timestamp]:
    s = pd.Series(1, index=pd.to_datetime(chart_dates))
    s = s[(s.index >= WIN_START - pd.Timedelta(days=14)) & (s.index <= GRADE_ASOF)]
    return [pd.Timestamp(d) for d in s.resample("W").apply(
        lambda x: x.index[-1] if len(x) else pd.NaT).dropna()]


def build_cycle_tape(chart: dict, stamps: list[pd.Timestamp], quick: bool) -> dict:
    """{basket_id: DataFrame[date, phase, pos, osc_slope]} reconstructed PIT.

    Production path: engine.china_sector_cycles._basket_series (the same equal-weight level
    series the baskets_china page renders) -> engine.sector_cycles._record_core with the
    series TRUNCATED at each stamp."""
    tape: dict[str, pd.DataFrame] = {}
    ids = list((chart.get("baskets") or {}).keys())
    if quick:
        # always keep the P0 basket so the reconstruction gate is exercised in quick mode
        ids = ([P0_CYCLE["basket"]] if P0_CYCLE["basket"] in ids else []) + ids[:2]
    for bid in ids:
        s = csc._basket_series(bid, chart)
        if s is None:
            continue
        rows = []
        for st in stamps:
            ss = s[s.index <= st]
            if len(ss) < 300:
                continue
            try:
                # win_start mirrors engine/china_sector_cycles.py:250 exactly
                core = sc._record_core(ss, ss.index[-1] - pd.DateOffset(years=sc.WINDOW_YEARS),
                                       ss.index[-1],
                                       pct=max(csc.CN_ZZ_PCT, sc._zz_pct_for(ss)))
            except Exception:  # noqa: BLE001 — a thin stamp is skipped, never fatal
                core = None
            if not core or not core.get("now"):
                continue
            now = core["now"]
            rows.append({"date": pd.Timestamp(st), "phase": now.get("phase"),
                         "pos": now.get("pos"), "osc_slope": now.get("osc_slope")})
        if rows:
            tape[bid] = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return tape


def _cycle_at(chart: dict, bid: str, asof: pd.Timestamp) -> dict | None:
    """One PIT basket cycle read through the production path, series truncated at ``asof``."""
    s = csc._basket_series(bid, chart)
    if s is None:
        return None
    ss = s[s.index <= asof]
    if len(ss) < 300:
        return None
    try:
        core = sc._record_core(ss, ss.index[-1] - pd.DateOffset(years=sc.WINDOW_YEARS),
                               ss.index[-1],
                               pct=max(csc.CN_ZZ_PCT, sc._zz_pct_for(ss)))
    except Exception as e:  # noqa: BLE001 — a thin series is skipped, never fatal
        print(f"  cycle read {bid}@{asof.date()} failed: {e}", flush=True)
        return None
    now = (core or {}).get("now") or {}
    return {"phase": now.get("phase"), "pos": _f(now.get("pos"), 1),
            "osc_slope": _f(now.get("osc_slope"), 1)} if now else None


def _shipped_cycle_log() -> pd.DataFrame | None:
    fl = DATA / "china_sector_cycles" / "forward_log.parquet"
    if not fl.exists():
        return None
    f = pd.read_parquet(fl)
    f["date"] = pd.to_datetime(f["date"])
    return f[f["kind"] == "basket"]


def check_p0_cycle(chart: dict, tape: dict) -> dict:
    """P0 gate — the reconstruction must reproduce the SHIPPED cn_gold read at the EXACT
    motivating date before any cycle cell is printed.  Truth = the production artifact
    data/china_sector_cycles/forward_log.parquet, not the brief's prose.

    Secondary: the WEEKLY stamping used by the stratifier is checked against every shipped
    (basket, date) pair it coincides with — a tape that reproduces one date but drifts on
    the rest would be a false pass."""
    want_d = pd.Timestamp(P0_CYCLE["date"])
    got = _cycle_at(chart, P0_CYCLE["basket"], want_d)
    log = _shipped_cycle_log()
    shipped = None
    if log is not None:
        m = log[(log["id"] == "b-" + P0_CYCLE["basket"]) & (log["date"] == want_d)]
        if len(m):
            r = m.iloc[0]
            shipped = {"phase": r["phase"], "pos": _f(r["pos"], 1),
                       "osc_slope": _f(r["osc_slope"], 1)}
    ok = bool(got and shipped and got["phase"] == shipped["phase"]
              and got["osc_slope"] is not None and shipped["osc_slope"] is not None
              and abs(got["osc_slope"] - shipped["osc_slope"]) <= 0.2)

    agree = {"pairs": 0, "phase_match": 0, "phase_match_pct": None, "median_abs_d_osc": None}
    if log is not None and tape:
        dslopes, matched, pairs = [], 0, 0
        for bid, df in tape.items():
            sub = log[log["id"] == "b-" + bid]
            if not len(sub):
                continue
            for _, row in df.iterrows():
                m = sub[sub["date"] == row["date"]]
                if not len(m):
                    continue
                pairs += 1
                r = m.iloc[0]
                if str(r["phase"]) == str(row["phase"]):
                    matched += 1
                if pd.notna(r["osc_slope"]) and row["osc_slope"] is not None:
                    dslopes.append(abs(float(r["osc_slope"]) - float(row["osc_slope"])))
        agree = {"pairs": pairs, "phase_match": matched,
                 "phase_match_pct": _f(100.0 * matched / pairs) if pairs else None,
                 "median_abs_d_osc": _pct(dslopes, 50)}
    return {"pass": ok, "target_date": str(want_d.date()),
            "reconstructed": got, "shipped": shipped,
            "expected_from_brief": {k: P0_CYCLE[k] for k in ("phase", "pos", "osc_slope")},
            "weekly_tape_vs_shipped_log": agree,
            "note": "shipped truth = data/china_sector_cycles/forward_log.parquet "
                    "(kind=basket); it only covers 2026-06-26+, which is why the "
                    "stratifier tape is a reconstruction at all"}


def pit_basket_of(membership: dict) -> dict[str, list[tuple[str, pd.Timestamp, pd.Timestamp | None]]]:
    """ticker -> [(basket_id, added, removed)] from the curated membership roster."""
    out: dict[str, list] = defaultdict(list)
    for bid, val in (membership.get("baskets") or {}).items():
        for m in (val.get("members") or []):
            t = m.get("ticker")
            if not t:
                continue
            out[t].append((bid, pd.Timestamp(m.get("added") or "1990-01-01"),
                           pd.Timestamp(m["removed"]) if m.get("removed") else None))
    return out


def build_narrative_tape(stamps: list[pd.Timestamp], quick: bool) -> dict:
    """{basket_id: DataFrame[date, level, rel20, breadth]} — production narrative_heat over
    the closes panel truncated at each weekly stamp (no historical store exists)."""
    if quick:
        stamps = stamps[-6:]
    closes = bc._closes()
    memb = bc._membership()
    if closes is None or memb is None:
        return {}
    try:
        bench_df = pd.read_parquet(DATA / "china" / f"{BENCH}.parquet")
        bench_s = pd.to_numeric(bench_df["close"], errors="coerce").dropna().sort_index()
    except Exception:  # noqa: BLE001
        bench_s = None
    rows: dict[str, list] = defaultdict(list)
    for st in stamps:
        c = closes[closes.index <= st]
        b = bench_s[bench_s.index <= st] if bench_s is not None else None
        if len(c) < 30:
            continue
        try:
            heat = cnt.narrative_heat(c, memb.get("baskets"), None, b)
        except Exception as e:  # noqa: BLE001 — a thin stamp is skipped, never fatal
            print(f"  narrative stamp {st.date()} skipped: {e}", flush=True)
            continue
        for bid, rec in (heat or {}).items():
            rows[bid].append({"date": pd.Timestamp(st), "level": rec.get("level"),
                              "rel20": rec.get("rel20"), "breadth": rec.get("breadth")})
    return {k: pd.DataFrame(v).sort_values("date").reset_index(drop=True) for k, v in rows.items() if v}


def _asof(df: pd.DataFrame | None, d: pd.Timestamp, col: str):
    if df is None or not len(df):
        return None
    m = df[df["date"] <= d]
    return m.iloc[-1][col] if len(m) else None


def stamp_stratifiers(events: list[dict], cycle_tape: dict, narr_tape: dict,
                      tick2basket: dict) -> None:
    """Attach basket / cycle / narrative context to each event, PIT."""
    for e in events:
        d = pd.Timestamp(e["anchor"])
        bids = [b for (b, add, rem) in tick2basket.get(e["ticker"], [])
                if add <= d and (rem is None or rem > d)]
        e["baskets"] = bids
        e["n_baskets"] = len(bids)
        bid = bids[0] if bids else None
        e["basket"] = bid
        ph = _asof(cycle_tape.get(bid), d, "phase") if bid else None
        sl = _asof(cycle_tape.get(bid), d, "osc_slope") if bid else None
        e["cycle_phase"] = ph
        e["cycle_osc_slope"] = _f(sl, 1)
        if ph is None or sl is None:
            e["cycle_cell"] = "unmapped"
        elif ph in ("Recovery", "Trough") and float(sl) > 0:
            e["cycle_cell"] = "Recovery+/Trough+"
        else:
            e["cycle_cell"] = "other"
        lv = _asof(narr_tape.get(bid), d, "level") if bid else None
        e["narrative_level"] = lv if lv else ("none" if bid else "unmapped")


def tercile_cut(events: list[dict]) -> None:
    vals = [e["dd_from_high_pct"] for e in events if e.get("dd_from_high_pct") is not None]
    if len(vals) < 30:
        for e in events:
            e["dd_tercile"] = "unmapped"
        return
    q1, q2 = np.percentile(vals, [33.3333, 66.6667])
    for e in events:
        v = e.get("dd_from_high_pct")
        if v is None:
            e["dd_tercile"] = "unmapped"
        elif v <= q1:
            e["dd_tercile"] = f"T1 deepest (<= {q1:.1f}%)"
        elif v <= q2:
            e["dd_tercile"] = f"T2 mid ({q1:.1f}..{q2:.1f}%)"
        else:
            e["dd_tercile"] = f"T3 shallowest (> {q2:.1f}%)"


def strat_block(events: list[dict], key: str) -> dict:
    out: dict = {}
    for lvl in sorted({str(e.get(key)) for e in events}):
        sub = [e for e in events if str(e.get(key)) == lvl]
        vet = [e for e in sub if e["cell"] == "VETOED_ADMIT"]
        adm = [e for e in sub if e["cell"] == "ADMITTED"]
        cell: dict = {}
        for h in HORIZONS:
            v, a = summarise(vet, h), summarise(adm, h)
            cell[f"H{h}"] = {"vetoed_admit": v, "admitted": a, "keep": keep_verdict(v, a)}
        out[lvl] = cell
    return out


# ── case receipt ─────────────────────────────────────────────────────────────
def case_receipt(bench: pd.Series) -> dict:
    """Reproduce the 002155.SZ 2026-08-03 veto from the production code paths."""
    df = _price_frame(DATA / "china_stocks" / f"{CASE_TICKER}.parquet")
    rec: dict = {"ticker": CASE_TICKER, "board_date": str(CASE_DATE.date())}
    if df is None:
        rec["error"] = "price frame unavailable"
        return rec
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    close = close[close.index <= CASE_DATE]          # PIT: the board saw only up to 08-03
    sig = sq.signal_frame(close).dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    n = len(sig)
    hi = sq._swing_highs(sig["high"])
    macd = sig["macd"]
    # the LAST buy bar at or before the board date — what verdict() reads as `last marker`
    buys = [i for i in range(n) if bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])]
    if not buys:
        rec["error"] = "no buy marker"
        return rec
    i = buys[-1]
    bear = bool(sq._bear_div(i, sig["high"], macd, hi))
    ok, reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=True)
    cf_ok, cf_reason = sq._buy_filter(i, sig, False, n, reclaim_veto=True)
    rh = [h for h in hi if i - 12 < h <= i]
    pv, mv = sig["high"].to_numpy(), macd.to_numpy()
    rec.update({
        "last_buy_bar_label": str(pd.Timestamp(sig.index[i]).date()),
        "bear_div": bear,
        "production_verdict": {"take": None if ok is None else bool(ok), "reason": reason},
        "gate_reason_rendered": "buy blocked by filter: " + str(reason),
        "counterfactual_veto_removed": {"take": None if cf_ok is None else bool(cf_ok),
                                        "reason": cf_reason},
        "swing_highs_in_look12": [str(pd.Timestamp(sig.index[h]).date()) for h in rh],
        "price_at_swings": [_f(pv[h], 3) for h in rh],
        "macd_at_swings": [_f(mv[h], 5) for h in rh],
        "dd_from_252d_high_pct": _f(100.0 * (float(close.iloc[-1])
                                             / float(close.rolling(252, min_periods=60).max().iloc[-1]) - 1.0)),
        "removing_the_leg_would_unblock_this_name":
            bool(cf_ok is not None and bool(cf_ok)),
        "cell": ("VETOED_ADMIT (in the decision set)" if (cf_ok is not None and bool(cf_ok))
                 else "VETOED_BLOCKED_ANYWAY (another leg refuses it too — NOT in the "
                      "decision set; the divergence string is merely the FIRST leg to fire)"),
        "close_only": True,
        "note": ("price leg reads the 3D CLOSE (h3==l3==s3) because CN calls "
                 "signal_gate.gate(ticker, close) with no high/low — "
                 "scripts/build_china_library.py:1960"),
    })
    # shipped board row, for the receipt to be checkable against the artifact
    cand = DATA / "china_prophet_rank" / "candidates.parquet"
    if cand.exists():
        c = pd.read_parquet(cand)
        m = c[(c["ticker"] == CASE_TICKER) & (c["stamp_date"].astype(str) == str(CASE_DATE.date()))]
        if len(m):
            r = m.iloc[0]
            rec["shipped_board_row"] = {
                "gate_reason": r.get("gate_reason"), "buyable": bool(r.get("buyable")),
                "off_high": _f(r.get("off_high")), "narrative_level": r.get("narrative_level"),
                "signal_bar_asof": str(r.get("signal_bar_asof")),
                "board_definition": r.get("board_definition"),
            }
            rec["reproduces_shipped_gate_reason"] = bool(
                str(r.get("gate_reason", "")).strip() == rec["gate_reason_rendered"].strip())
    return rec


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smoke run over 120 names")
    args = ap.parse_args()
    t_start = time.time()

    bench = bench_close()
    files = sorted((DATA / "china_stocks").glob("*.parquet"))
    if args.quick:
        files = files[:120]
    print(f"panel: {len(files)} candidate files; window "
          f"{WIN_START.date()}..{WIN_END.date()}; grade asof {GRADE_ASOF.date()}", flush=True)

    events: list[dict] = []
    diag: Counter = Counter()
    n_names = 0
    for k, p in enumerate(files):
        df = _price_frame(p)
        if df is None:
            diag["names_skipped_thin"] += 1
            continue
        n_names += 1
        evs, d = scan_name(p.stem, df, bench)
        events.extend(evs)
        diag.update(d)
        if (k + 1) % 400 == 0:
            print(f"  ... {k+1}/{len(files)} files, {len(events)} events "
                  f"({time.time()-t_start:.0f}s)", flush=True)
    diag["names_scanned"] = n_names
    print(f"scan done: {n_names} names, {len(events)} raw comparable events "
          f"({time.time()-t_start:.0f}s)", flush=True)

    raw_counts = {c: sum(1 for e in events if e["cell"] == c)
                  for c in ("VETOED_ADMIT", "ADMITTED")}
    events = dedup(events)
    print(f"dedup({DEDUP_SESSIONS}d): {len(events)} events "
          f"({time.time()-t_start:.0f}s)", flush=True)

    # ── stratifier tapes ────────────────────────────────────────────────────
    chart = (bc.compute_china_baskets() or {}).get("chart") or {}
    stamps = weekly_stamps(chart.get("dates") or [])
    cycle_tape = build_cycle_tape(chart, stamps, args.quick)
    print(f"cycle tape: {len(cycle_tape)} baskets x {len(stamps)} weekly stamps "
          f"({time.time()-t_start:.0f}s)", flush=True)
    p0 = check_p0_cycle(chart, cycle_tape)
    print(f"P0 cycle gate: {'PASS' if p0['pass'] else 'FAIL'} "
          f"reconstructed={p0['reconstructed']} shipped={p0['shipped']} "
          f"| weekly tape vs shipped log: {p0['weekly_tape_vs_shipped_log']}", flush=True)
    narr_tape = build_narrative_tape(stamps, args.quick)
    print(f"narrative tape: {len(narr_tape)} baskets ({time.time()-t_start:.0f}s)", flush=True)

    memb = bc._membership() or {}
    stamp_stratifiers(events, cycle_tape, narr_tape, pit_basket_of(memb))
    tercile_cut(events)
    for e in events:
        e["half"] = ("H1 2025-08..2026-01" if pd.Timestamp(e["anchor"]) < pd.Timestamp("2026-02-01")
                     else "H2 2026-02..2026-07")

    vet = [e for e in events if e["cell"] == "VETOED_ADMIT"]
    adm = [e for e in events if e["cell"] == "ADMITTED"]

    # Composition — the operator's question in its own right: does the veto land
    # DISPROPORTIONATELY on early-Recovery reclaims?  Shares are over the MAPPED subset only
    # (a fire whose name is in no curated basket has no cycle read at all).
    def _comp(pool: list[dict]) -> dict:
        mapped = [e for e in pool if e["cycle_cell"] != "unmapped"]
        rec = [e for e in mapped if e["cycle_cell"] == "Recovery+/Trough+"]
        return {"n_total": len(pool), "n_mapped": len(mapped),
                "mapped_coverage_pct": _f(100.0 * len(mapped) / len(pool)) if pool else None,
                "n_recovery_plus": len(rec),
                "recovery_plus_share_of_mapped_pct":
                    _f(100.0 * len(rec) / len(mapped)) if mapped else None}
    composition = {"vetoed_admit": _comp(vet), "admitted": _comp(adm),
                   "reading": "if the veto systematically blocked early-Recovery reclaims, "
                              "its Recovery+/Trough+ share would EXCEED the admitted cell's"}

    # What the leg actually costs in breadth
    marginal = {
        "fires_in_window": int(diag["fires_in_window"]),
        "vetoed_gross": int(diag["vetoed"]),
        "vetoed_pct_of_fires": _f(100.0 * diag["vetoed"] / max(diag["fires_in_window"], 1)),
        "vetoed_that_another_leg_blocks_anyway": int(diag["VETOED_BLOCKED_ANYWAY"]),
        "decision_set_newly_admitted": int(diag["VETOED_ADMIT"]),
        "decision_set_pct_of_vetoed": _f(100.0 * diag["VETOED_ADMIT"] / max(diag["vetoed"], 1)),
        "takes_today": int(diag["ADMITTED"]),
        "extra_takes_pct_if_leg_removed":
            _f(100.0 * diag["VETOED_ADMIT"] / max(diag["ADMITTED"], 1)),
    }

    headline: dict = {}
    for h in HORIZONS:
        v, a = summarise(vet, h), summarise(adm, h)
        headline[f"H{h}"] = {"vetoed_admit": v, "admitted": a, "keep": keep_verdict(v, a)}

    # fill-convention sensitivity: the production open-preferring fill vs the pinned HL2
    sens: dict = {}
    for h in HORIZONS:
        for label, pool in (("vetoed_admit", vet), ("admitted", adm)):
            rows = [e for e in pool if e.get(f"excp{h}") is not None]
            sens[f"H{h}_{label}"] = {
                "n": len(rows),
                "win_pct_hl2": _f(100.0 * sum(1 for e in rows if e[f"exc{h}"] > 0) / len(rows)) if rows else None,
                "win_pct_prod_open": _f(100.0 * sum(1 for e in rows if e[f"excp{h}"] > 0) / len(rows)) if rows else None,
                "median_excess_hl2": _pct([e[f"exc{h}"] for e in rows], 50),
                "median_excess_prod_open": _pct([e[f"excp{h}"] for e in rows], 50),
            }

    results = {
        "instrument": "research/cn_prophet_audit/cn_divergence_veto_audit.py",
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "IN-SAMPLE, MOTIVATING-ONLY — no promotion, no gate change",
        "leg": {
            "name": "bearish divergence veto",
            "implementation": "engine/signal_quality.py:178 _buy_filter -> "
                              "`if bear: return False, 'veto: bearish divergence'` (line 208-209)",
            "condition_source": "engine/signal_quality.py:169 _bear_div(i, price, macd, hi, look=12) "
                                "over engine/signal_quality.py:164 _swing_highs(s, w=2)",
            "condition": "the last two confirmed swing highs within the trailing 12 bars of the "
                         "3B frame print a HIGHER price high against a LOWER RSI-MACD high",
            "cn_call_site": "scripts/build_china_library.py:1960 signal_gate.gate(ticker, close) "
                            "-> engine/signal_gate.py:155 gate(..., reclaim_veto=True) [DEFAULT] "
                            "-> analyze(ticker, daily_close) with NO high/low (close-only)",
            "entangled": False,
            "entanglement_note": "the veto is the FIRST statement of _buy_filter and returns before "
                                 "the reclaim/hold branches, so the counterfactual is the production "
                                 "call _buy_filter(i, sig, False, n, reclaim_veto=True) — no "
                                 "reimplementation, no shared state. tests/test_hk_reclaim_veto_"
                                 "policy.py:77-79 independently pins its orthogonality to reclaim_veto.",
        },
        "design": {
            "window": [str(WIN_START.date()), str(WIN_END.date())],
            "grade_asof": str(GRADE_ASOF.date()), "min_bars": MIN_BARS,
            "horizons": list(HORIZONS), "benchmark": BENCH,
            "fill": "T+1 HL2, locked-limit (T+1 high==low==close) EXCLUDED",
            "anchor": "last daily session of 3B bar i+2 — the first close at which the label "
                      "is knowable; marker-date grading is forbidden "
                      "(engine/signal_quality.py:190-201)",
            "dedup": f"within-cell, {DEDUP_SESSIONS} trading sessions per name",
            "keep_rule": {
                "margin_pp": KEEP_MARGIN_PP, "min_cell_n": MIN_CELL_N,
                "return_leg": "win%(VETOED_ADMIT) <= win%(ADMITTED) - 3pp",
                "risk_leg": "catastrophic%(VETOED_ADMIT) >= catastrophic%(ADMITTED) + 3pp "
                            "OR MAE-p10(VETOED_ADMIT) <= MAE-p10(ADMITTED) - 3pp",
                "earns_iff": "either leg passes on a cell with n >= 100 on BOTH sides",
                "precedent": "research/signal_engine/VETO_LEG_AUDIT.md (>= +3pp on the verdict "
                             "metric); HK removal keep pairing in "
                             "research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 G6",
            },
            "catastrophic_def": f"ABSOLUTE return <= {CATASTROPHIC_PP}%",
        },
        "diagnostics": {k: int(v) for k, v in sorted(diag.items())},
        "raw_event_counts_pre_dedup": raw_counts,
        "deduped_event_counts": {"VETOED_ADMIT": len(vet), "ADMITTED": len(adm)},
        "p0_cycle_reconstruction_gate": p0,
        "veto_marginal_cost": marginal,
        "cycle_cell_composition": composition,
        "headline": headline,
        "fill_convention_sensitivity": sens,
        "strat_cycle_cell": strat_block(events, "cycle_cell"),
        "strat_dd_tercile": strat_block(events, "dd_tercile"),
        "strat_narrative_level": strat_block(events, "narrative_level"),
        "strat_half": strat_block(events, "half"),
        "case_receipt_002155": case_receipt(bench),
        "runtime_sec": None,
        "quick": bool(args.quick),
    }
    results["runtime_sec"] = round(time.time() - t_start, 1)
    if not args.quick:
        OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str) + "\n")
        print(f"wrote {OUT} ({results['runtime_sec']}s)", flush=True)
    else:
        print(json.dumps({"diagnostics": results["diagnostics"],
                          "counts": results["deduped_event_counts"],
                          "veto_marginal_cost": marginal,
        "cycle_cell_composition": composition,
        "headline": headline, "p0": p0}, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
