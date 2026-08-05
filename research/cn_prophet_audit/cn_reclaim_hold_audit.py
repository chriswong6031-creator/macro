"""CN edition of the veto-leg audit — the RECLAIM-AND-HOLD family, CN's PRIMARY buy blocker.

MEASUREMENT INSTRUMENT, not a signal.  Direct mirror of
research/cn_prophet_audit/cn_divergence_veto_audit.py (same window, same fills/outcomes
conventions, same funnel-decomposition discipline, same pre-registered keep rule), which
itself mirrors research/signal_engine/veto_leg_audit.py.  Production code paths over
committed stores, frozen results committed next to the script.

WHY THIS LEG, AND WHY NOW.  The divergence audit measured the CN buy filter's funnel and
found the divergence veto is NOT the board's primary blocker: it refuses 743 fires while
the reclaim-and-hold family refuses **2,684** (its ``ADMITTED_FAILED_OTHER_LEG`` counter).
Three independent receipts point at this family:

  1. The operator's gold-miner case 002155.SZ (湖南黄金, −44% off its 252d high inside a
     ``cn_gold`` basket reading phase=Recovery / osc_slope=+12.9 / narrative HOT).  Its
     shipped ``gate_reason`` names the divergence veto, but the divergence audit's
     counterfactual showed that removing that leg leaves the name **still blocked —
     ``failed reclaim-and-hold``**.  This family is the actual binding blocker.
  2. research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §2.7: of the 17
     never-eligible top-150 era runners, **8** carry
     ``buy blocked by filter: counter-trend, no 200-reclaim/hold`` and 2 more carry
     ``failed reclaim-and-hold`` — 10 of 17.  §2.7 calls this cohort "the continuation/
     rotation shape the family structurally cannot admit" and R4 proposes a continuation
     door for it.
  3. HK removed its sibling leg after measurement (#4470 / e337d95f312, operator ruling
     2026-08-03) — the SAME ``reclaim_veto`` parameter this script uses as its
     counterfactual.  CN's has never been measured.

NOT A PROMOTION.  In-sample, motivating-only, one window, one market.  The verdict language
is "the leg earns / fails its keep on this window" and it feeds a prereg + ratification —
NEVER a hot removal.  Nothing here changes a shipped gate.

────────────────────────────────────────────────────────────────────────────────
THE FAMILY, AS PRODUCTION IMPLEMENTS IT (re-derived, not approximated)
────────────────────────────────────────────────────────────────────────────────
engine/signal_quality.py:178 ``_buy_filter(i, sig, bear, n, *, reclaim_veto=True)``.  After
the divergence veto returns (lines 208-209) the ENTIRE remainder of the function is this
family — there is no third leg::

    212  held = bool(c.iloc[i + 1] > c.iloc[i])
    213  below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    214  if below and wkdn:                                   # the COUNTER-TREND branch
    215      if reclaim_veto:
    218          reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
    219          ok = held and reclaim
    220          return ok, (... else "counter-trend, no 200-reclaim/hold")
    224      return held, (... else "failed next-bar hold")    # reclaim_veto=False (HK)
    225  return held, (... else "failed reclaim-and-hold")     # the MAIN path

``above200`` (engine/signal_quality.py:99) is the 3B close over the 200-DAY rolling mean of
the daily close; ``w_bull`` (:97) is the W-FRI RSI-MACD >= its signal, shifted one week.

It decomposes into exactly TWO sub-legs, and this script audits each AND the family:

  R — the RECLAIM requirement (:214-220).  A name that is BOTH below its 200-day average
      AND weekly-down must additionally close back above that average at bar i+1 or i+2.
      This is the leg HK deleted.
  H — the next-bar HOLD confirmation (:212, consumed at :219 and :225).  Every fire needs
      close[i+1] > close[i].  Kept on both HK policies.

SEPARABILITY (determined the way the divergence audit determined it):

  R is CLEANLY SEPARABLE BY A PRODUCTION PARAMETER.  Its counterfactual is the shipped call
  ``_buy_filter(i, sig, bear, n, reclaim_veto=False)`` — engine/signal_gate.py:155 exposes
  it, scripts/build_hk_library.py ships it, tests/test_hk_reclaim_veto_policy.py:46-59 pins
  the exact flip this script counts, and :83-90 pins that the non-counter-trend branches are
  IDENTICAL under both policies.  No reimplementation.

  H is NOT separable by any production parameter — no shipped caller can turn it off.  Its
  counterfactual is therefore a 6-line re-derivation (``_cf_filter`` below).  A mirrored
  re-derivation is worthless unless something can SEE it drift, so it is **parity-gated on
  100% of in-window fires**: ``_cf_filter(hold=True, reclaim=True)`` must equal production's
  ``reclaim_veto=True`` and ``_cf_filter(hold=True, reclaim=False)`` must equal production's
  ``reclaim_veto=False``, event for event.  Any mismatch fails P0-B and the run refuses to
  print a leg-H or family number.

  The FAMILY's counterfactual is ``_cf_filter(hold=False, reclaim=False)`` = admit every
  non-divergence-vetoed fire, i.e. the whole tail of ``_buy_filter`` deleted.

REASON-STRING AMBIGUITY (measured, not assumed).  Neither shipped string identifies which
sub-leg refused:
  * ``"counter-trend, no 200-reclaim/hold"`` is printed whenever the counter-trend branch
    refuses — whether ``held`` failed, ``reclaim`` failed, or both.
  * ``"failed reclaim-and-hold"`` is the MAIN-path string, where **no reclaim is tested at
    all** — only ``held``.  The string mis-names its own condition.
This script counts both decompositions so board copy that names one blocking reason knows
what it is and is not saying.  (Same family of defect as the divergence audit's first-match
finding; naming it is display-tier work, out of scope here.)

CN runs this family CLOSE-ONLY on the DEFAULT reclaim_veto=True path:
scripts/build_china_library.py:1960 ``sig_verdict[ticker] = signal_gate.gate(ticker, close)``
→ engine/signal_gate.py:155 ``gate(..., reclaim_veto: bool = True)`` → ``analyze(ticker,
daily_close)`` with **no daily_high/daily_low**, so ``signal_frame`` takes the ``h3 = l3 =
s3`` branch.  This instrument reproduces that exactly.

────────────────────────────────────────────────────────────────────────────────
DESIGN (pre-registered; nothing below was chosen after seeing a result)
────────────────────────────────────────────────────────────────────────────────
PANEL      data/china_stocks/*.parquet, names with >= MIN_BARS daily bars, every series
           truncated at GRADE_ASOF first (frozen replay — the stores accrue a bar nightly).
WINDOW     a fire counts iff its ANCHOR date falls in [WIN_START, WIN_END].  Identical to
           the divergence audit: 2025-08-01 … 2026-07-31.
FIRE       the production buy event ``CB[i] or revBuy[i]`` — the ``is_buy`` test analyze()
           uses at engine/signal_quality.py:267.

CELLS      per ¬bear fire (a divergence-vetoed fire never reaches this family, so it is
           excluded from the population and accounted separately under upstream masking):

             prod_ok    = _buy_filter(i, sig, bear, n, reclaim_veto=True)    # shipped
             cf_noR_ok  = _buy_filter(i, sig, bear, n, reclaim_veto=False)   # R removed
             cf_noH_ok  = _cf_filter(i, sig, bear, n, hold=False, reclaim=True)
             cf_noF_ok  = _cf_filter(i, sig, bear, n, hold=False, reclaim=False)

             ADMITTED         prod_take                      ← today's takes (the control)
             RECLAIM_ADMIT    ¬prod_take ∧ cf_noR_take       ← R's decision set
             HOLD_ADMIT       ¬prod_take ∧ cf_noH_take ∧ ¬cf_noR_take   ← H's decision set
             BLOCKED_BY_BOTH  ¬prod_take ∧ ¬cf_noR_take ∧ ¬cf_noH_take  ← neither alone
             FAMILY_ADMIT     = RECLAIM_ADMIT ⊎ HOLD_ADMIT ⊎ BLOCKED_BY_BOTH

           RECLAIM_ADMIT and HOLD_ADMIT are provably disjoint (both true would require
           held ∧ reclaim, which is a take); the code asserts it anyway.  Each decision
           cell vs ADMITTED is apples-to-apples: every OTHER leg passes on both sides and
           the only difference is the audited leg's state.

ANCHOR     ⚠ MARKER-DATE GRADING IS FORBIDDEN (engine/signal_quality.py:198-206; CN-1
           §W6-CN).  ``_buy_filter`` reads bars i+1 / i+2 — for THIS family that is the
           whole mechanism (``held`` is bar i+1, ``reclaim`` is bars i+1/i+2) — so the
           anchor is the LAST DAILY SESSION OF 3B BAR i+2, the first close at which the
           label is knowable.  ``resample("3B")`` labels buckets on the LEFT edge, so the
           anchor is resolved through an explicit bucket→last-daily-date map, never by
           reading a bar label as a close date.
           Leak note specific to this family: because ``held``/``reclaim`` are pure
           functions of bars i+1/i+2 and nothing later, the i+2 anchor is exactly tight —
           no earlier anchor can know the label and no later one is needed.

RULER      house CN convention (engine/china_standout_track.py ``_t1_fill`` / ``_fwd_excess``,
           the same functions the divergence audit pinned): entry = T+1 **HL2** after the
           anchor close; **locked-limit T+1 bars (high==low==close) EXCLUDED, never
           fabricated**; outcome = CSI300-relative (510300.SS) forward excess at H=10 / 21.
           The production open-preferring fill is carried as a sensitivity.

METRICS    n · win% (excess > 0) with Wilson 95% CI · median/mean excess · MAE-tail p10 ·
           catastrophic share (ABSOLUTE return <= -15%).
           PLUS one metric the divergence audit did not carry: **MFE-p90** (the 90th
           percentile of the best intrabar excursion from fill).  It is REPORTED ONLY and
           is NOT part of the keep rule — the rule stays byte-identical to the divergence
           audit's.  It is here because the HK removal's own postmortem records a retraction
           on this exact leg family: "endpoint excess is the wrong lens for a bounce", and
           the deep-washout population this family blocks is precisely where an
           endpoint-only read misleads.  MAE-p10 without its complement is a one-directional
           read of a two-sided path.

DEDUP      within-cell, 5 trading sessions per name (the veto_leg_audit.py convention).
           The family cell is deduped on its OWN coarse partition (ADMITTED / FAMILY_ADMIT)
           rather than reusing the fine one — otherwise a name could contribute one
           RECLAIM_ADMIT and one HOLD_ADMIT event five days apart and inflate the family.

KEEP RULE (PRE-REGISTERED — byte-identical to the divergence audit's, which mirrors
research/signal_engine/VETO_LEG_AUDIT.md's ">= +3pp on the verdict metric" and the HK
removal's return-leg + risk-leg pairing, HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 G6:
mean excess with a zero-crossing CI, 60d MAE, and P(excess<-20%) reported together):

    A blocking leg EARNS ITS KEEP on a cell iff, on that cell,
      (R) RETURN leg: win%(<leg>_ADMIT) <= win%(ADMITTED) - KEEP_MARGIN_PP, or
      (K) RISK   leg: catastrophic%(<leg>_ADMIT) >= catastrophic%(ADMITTED) + KEEP_MARGIN_PP,
                      or MAE-p10(<leg>_ADMIT) <= MAE-p10(ADMITTED) - KEEP_MARGIN_PP,
    on a cell with n >= MIN_CELL_N on BOTH sides.  Clearing EITHER leg = EARNS.  Clearing
    NEITHER = FAILS its keep on this window.  n below the floor = UNDECIDED (printed, never
    read as a pass).  KEEP_MARGIN_PP = 3.0 (house constant).

    Reported alongside (a stricter read of the same rule, NOT a rule change): whether the
    blocked cell's Wilson CI EXCLUDES the return-leg keep bar.  A FAILS whose CI straddles
    the bar is "no measurable protection", not "proven harmful".

    THE HK BAR, FOR CALIBRATION.  HK deleted leg R with a measurement that did NOT clear
    this bar in the leg's favour and did not clear it against the leg either: the unblocked
    cohort earned ~0 excess vs HSI (mean +0.55%/20d, CI crossing zero) but carried DEEPER
    drawdown (median 60d MAE -9.0% vs -7.4%; P(excess<-20%) 5.8% -> 7.9%) — i.e. HK's own
    numbers show a risk-leg cost to removal.  The removal shipped on an operator ruling as a
    product bet on an ungradeable regime, explicitly "a bet on that regime, not a finding
    about it".  Precedent for MEASURING; not precedent for removing on a null.

STRATIFIERS (all point-in-time; every one declares its own coverage)
    * basket cycle state at fire — reconstructed through the PRODUCTION path
      (engine.baskets_china.compute_china_baskets → engine.china_sector_cycles._basket_series
      → engine.sector_cycles._record_core) on the series TRUNCATED at each weekly stamp,
      exactly as the divergence audit does it.  P0-A gate: the reconstruction must reproduce
      the shipped 2026-08-03 ``cn_gold`` read (Recovery / pos 13.5 / osc_slope 12.9,
      data/china_sector_cycles/forward_log.parquet) before any cycle cell is printed.
      Cell "Recovery+/Trough+" = phase in {Recovery, Trough} AND osc_slope > 0.
    * dd_from_high tercile — 252-session drawdown at the anchor close, terciles cut on the
      pooled fire population.
    * MA50 side — daily close vs its 50-session mean at the anchor close.
    * trail_63 SIGN — the CONTINUATION cell.  trail_63 = close[d0]/close[d0-63] - 1, the
      same convention as research/cn_prophet_audit/v1_runner_coverage_audit.py:88.  A name
      with trail_63 > 0 that the family refuses is an UPTRENDING name blocked by a
      counter-trend rule — the §2.7 cohort's shape and the continuation-door evidence.  The
      per-cell trail_63 distribution is printed alongside, because §2.7's actual cohort sits
      at median trail_63 = -11.2% (shallow, not positive), so the sign split is a STRICTER
      continuation definition than §2.7's and must not be read as that cohort's cell.
    * narrative level — engine.china_narrative_tags.narrative_heat on the closes panel
      truncated at the same weekly stamp (carried for structural parity with the divergence
      audit; coverage is thin and every cell is expected UNDECIDED).
    * half-split robustness — first vs second half of the window by anchor date.  The
      divergence audit's headline verdict INVERTED across this split; the same caution
      applies to every verdict below until a forward cohort settles it.

LIMITATIONS (also restated in the MD)
    One year, one market, in-sample, no out-of-sample holdout.  Basket membership is
    hindsight-curated (engine/baskets_china.py module docstring says so) — the cycle and
    narrative stratifiers inherit that.  H=21 cannot mature for fires anchored after roughly
    2026-07-02, so the H=21 cells are smaller and end-loaded.  Name-clustered dependence is
    not modelled; name concentration is reported instead.  The absolute win rates are the raw
    signal_gate fire population, NOT the Prophet board (which layers rank, tier, liquidity,
    extension and featured gates downstream and whose ledger reads very differently).

Run from repo root:  python3 research/cn_prophet_audit/cn_reclaim_hold_audit.py
                     python3 research/cn_prophet_audit/cn_reclaim_hold_audit.py --quick
Outputs: research/cn_prophet_audit/cn_reclaim_hold_results.json (frozen)
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
from engine import signal_gate
from engine import signal_quality as sq

# ── frozen-replay pins (identical to cn_divergence_veto_audit.py) ─────────────
GRADE_ASOF = pd.Timestamp("2026-08-04")   # last bar in the committed stores at build time
WIN_START = pd.Timestamp("2025-08-01")
WIN_END = pd.Timestamp("2026-07-31")
MIN_BARS = 250
HORIZONS = (10, 21)
BENCH = "510300.SS"
DEDUP_SESSIONS = 5
CATASTROPHIC_PP = -15.0                   # ABSOLUTE return <= -15%
KEEP_MARGIN_PP = 3.0                      # house constant (VETO_LEG_AUDIT.md)
MIN_CELL_N = 100                          # below this a cell is UNDECIDED, never a pass
MA50_LEN = 50
TRAIL63_LEN = 63

# P0-A — the shipped cn_gold cycle read this instrument must reproduce
P0_CYCLE = {"basket": "cn_gold", "date": "2026-08-03",
            "phase": "Recovery", "pos": 13.5, "osc_slope": 12.9}

# Cross-check pins: the divergence audit's frozen funnel over the SAME window/panel.
# This script recomputes the same quantities from the other side of the same filter, so a
# mismatch means one of the two instruments drifted.
DIVERGENCE_AUDIT_PINS = {
    "source": "research/cn_prophet_audit/cn_divergence_veto_results.json "
              "(branch claude/cn-divergence-veto-audit, PR #4576)",
    "fires_in_window": 5157,
    "vetoed_gross": 743,
    "vetoed_blocked_anyway": 575,
    "vetoed_admit": 168,
    "admitted": 1730,
    "admitted_failed_other_leg": 2684,   # ← the family's gross block count, this study
}

CASE_TICKER = "002155.SZ"
CASE_DATE = pd.Timestamp("2026-08-03")
# §2.7 never-eligible era runners whose last_reason is the counter-trend string, read from
# research/cn_prophet_audit/v1_runner_coverage_results.json (frozen 2026-08-03).  603087.SS
# is the featured receipt: it is the only one of the eight with a POSITIVE 21-day trail
# (+8.6%) — the literal continuation shape.
S27_ERA = ("2026-06-30", "2026-07-29")
S27_FEATURED = "603087.SS"

OUT = Path(__file__).parent / "cn_reclaim_hold_results.json"
DATA = ROOT / "data"


# ── the leg-H / family counterfactual, parity-gated against production ────────
def _cf_filter(i, sig, bear, n, *, hold: bool, reclaim: bool):
    """``_buy_filter`` with either sub-leg of the reclaim-and-hold family switched OFF.

    A line-for-line mirror of engine/signal_quality.py:207-225 with two switches:
    ``hold`` enforces the next-bar confirmation (:212) and ``reclaim`` enforces the
    counter-trend 200-day reclaim (:218).  ``hold=True, reclaim=True`` reproduces
    production's ``reclaim_veto=True``; ``hold=True, reclaim=False`` reproduces
    ``reclaim_veto=False``.  P0-B checks BOTH of those on every in-window fire, so this
    mirror cannot drift from production unnoticed — a mirrored counterfactual that nothing
    can see fail is worthless.

    Returns (take: bool|None, reason) with production's own reason strings where the branch
    is production's; the switched branches get explicit synthetic labels so no counterfactual
    number is ever mistaken for a shipped one."""
    c, a = sig["close"], sig["above200"]
    if bear:
        return False, "veto: bearish divergence"
    if i + 1 >= n:
        return None, "pending confirmation"
    held = bool(c.iloc[i + 1] > c.iloc[i]) if hold else True
    below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    if below and wkdn:
        if reclaim:
            if i + 2 >= n:
                return None, "pending confirmation"
            rc = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
            ok = held and rc
            return ok, ("reclaimed 200 & held" if ok
                        else ("counter-trend, no 200-reclaim/hold" if hold
                              else "cf: counter-trend, no 200-reclaim (hold leg OFF)"))
        if hold:
            return held, ("held confirmation (counter-trend)" if held else "failed next-bar hold")
        return True, "cf: counter-trend admitted (both family legs OFF)"
    if hold:
        return held, ("held confirmation" if held else "failed reclaim-and-hold")
    return True, "cf: main-path admitted (hold leg OFF)"


# ── small stats helpers (identical to the divergence audit) ───────────────────
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
    mfe = [float(e[f"mfe{h}"]) for e in rows if e.get(f"mfe{h}") is not None]
    tr63 = [float(e["trail63_pct"]) for e in rows if e.get("trail63_pct") is not None]
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
        # MFE = the complement of MAE, REPORTED ONLY (never in the keep rule).  A bounce
        # population read on endpoint excess alone is the retraction the HK postmortem
        # records; peak-after-entry is the other half of the same path.
        "mfe_p90_pct": _pct(mfe, 90),
        "mfe_median_pct": _pct(mfe, 50),
        "catastrophic_pct": _f(100.0 * cat / n) if n else None,
        "top5_name_share_pct": _f(100.0 * top5 / n) if n else None,
        "median_trail63_pct": _pct(tr63, 50),
        "median_dd_from_high_pct": _pct(
            [float(e["dd_from_high_pct"]) for e in rows
             if e.get("dd_from_high_pct") is not None], 50),
    }


def keep_verdict(blocked: dict, adm: dict) -> dict:
    """Apply the PRE-REGISTERED keep rule to one (<leg>_ADMIT, ADMITTED) cell pair."""
    if (not blocked or not adm or blocked["n"] < MIN_CELL_N or adm["n"] < MIN_CELL_N):
        d = None
        if (blocked and adm and blocked.get("win_pct") is not None
                and adm.get("win_pct") is not None):
            d = _f(blocked["win_pct"] - adm["win_pct"])
        return {"verdict": "UNDECIDED",
                "why": f"n below the {MIN_CELL_N} floor "
                       f"(blocked={(blocked or {}).get('n', 0)}, "
                       f"admitted={(adm or {}).get('n', 0)})",
                "d_win_pp": d}
    d_win = blocked["win_pct"] - adm["win_pct"]                                  # neg = blocked worse
    d_cat = (blocked["catastrophic_pct"] or 0.0) - (adm["catastrophic_pct"] or 0.0)  # pos = blocked worse
    d_mae = (blocked["mae_p10_pct"] or 0.0) - (adm["mae_p10_pct"] or 0.0)        # neg = blocked worse
    r_leg = d_win <= -KEEP_MARGIN_PP
    k_leg = (d_cat >= KEEP_MARGIN_PP) or (d_mae <= -KEEP_MARGIN_PP)
    # Reporting strengthening (NOT a rule change): does the blocked cell's Wilson 95% CI
    # EXCLUDE the return-leg keep bar (admitted win% - 3pp)?  If the CI lies entirely above
    # the bar, the data rule OUT the protective reading at 95%; if it straddles the bar, the
    # point estimate fails but the interval cannot exclude protection.
    bar = adm["win_pct"] - KEEP_MARGIN_PP
    lo = (blocked.get("win_ci95") or [None, None])[0]
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


# ── panel loading (identical to the divergence audit) ─────────────────────────
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

    Mirrors engine/china_standout_track.py ``_t1_fill`` for the locked-limit test (T+1
    printed high == low == close is unfillable and MUST be excluded, not fabricated); the
    fill itself is forced to (high+low)/2 rather than the production open-preference."""
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
    high = pd.to_numeric(df["high"], errors="coerce")
    highf = high[high.index > d0]
    bslice = bench[bench.index > d0]
    prod_fill = t1_fill_production(df, d0)
    out: dict = {"fill": _f(fill, 4), "t1": str(t1.date()), "locked": False}
    for h in HORIZONS:
        if len(fwd) <= h or len(bslice) <= h:
            out[f"exc{h}"] = out[f"abs{h}"] = out[f"mae{h}"] = None
            out[f"mfe{h}"] = out[f"excp{h}"] = None
            continue
        name_ret = 100.0 * (float(fwd.iloc[h]) / fill - 1.0)
        bench_ret = 100.0 * (float(bslice.iloc[h]) / float(bslice.iloc[0]) - 1.0)
        out[f"abs{h}"] = _f(name_ret)
        out[f"exc{h}"] = _f(name_ret - bench_ret)
        seg = lowf.iloc[: h + 1].dropna()
        out[f"mae{h}"] = _f(100.0 * (float(seg.min()) / fill - 1.0)) if len(seg) else None
        segh = highf.iloc[: h + 1].dropna()
        out[f"mfe{h}"] = _f(100.0 * (float(segh.max()) / fill - 1.0)) if len(segh) else None
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
    roll_high = close.rolling(252, min_periods=60).max()
    ma50 = close.rolling(MA50_LEN, min_periods=MA50_LEN).mean()
    trail63 = close / close.shift(TRAIL63_LEN) - 1.0

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
        cf_noR_ok, cf_noR_reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=False)
        cf_noH_ok, _ = _cf_filter(i, sig, bear, n, hold=False, reclaim=True)
        cf_noF_ok, _ = _cf_filter(i, sig, bear, n, hold=False, reclaim=False)
        # ── P0-B parity gate: the re-derivation must equal production on BOTH branches
        # production can express, for every single fire — the FULL (take, reason) tuple, not
        # just the boolean, so a reason-string drift is caught too.  Asserted in main().
        par_on = _cf_filter(i, sig, bear, n, hold=True, reclaim=True)
        par_off = _cf_filter(i, sig, bear, n, hold=True, reclaim=False)
        diag["parity_checked"] += 1
        if par_on != (prod_ok, prod_reason):
            diag["parity_mismatch_reclaim_on"] += 1
        if par_off != (cf_noR_ok, cf_noR_reason):
            diag["parity_mismatch_reclaim_off"] += 1

        # `== True` / bool(), never `is True` — a numpy scalar is not the True singleton.
        prod_take = (prod_ok is not None) and bool(prod_ok)
        noR_take = (cf_noR_ok is not None) and bool(cf_noR_ok)
        noH_take = (cf_noH_ok is not None) and bool(cf_noH_ok)
        noF_take = (cf_noF_ok is not None) and bool(cf_noF_ok)
        if prod_ok is None:
            # structurally unreachable: the anchor already required i+2 < n, so neither
            # `pending` branch of _buy_filter can be taken.  Counted so a future change to
            # the anchor cannot silently reclassify a pending as a block.
            diag["pending_unreachable_violation"] += 1
            continue

        if bear:
            # A divergence-vetoed fire never REACHES this family in production.  It is
            # excluded from the population and accounted here so the two audits compose:
            # this is the divergence audit's VETOED_BLOCKED_ANYWAY / VETOED_ADMIT split
            # recomputed from the other side of the same filter.
            diag["bear_fires_excluded"] += 1
            fam_would_also_block, _ = _cf_filter(i, sig, False, n, hold=True, reclaim=True)
            if not ((fam_would_also_block is not None) and bool(fam_would_also_block)):
                diag["bear_fires_family_would_also_block"] += 1
            else:
                diag["bear_fires_family_would_admit"] += 1
            continue

        # branch/condition decomposition, for the reason-string ambiguity count.  Recomputed
        # from the SAME frame production reads (engine/signal_quality.py:212-218), and
        # cross-checked against the counterfactuals: `held` must equal cf_noR_take, because
        # reclaim_veto=False reduces the filter to exactly the hold test.
        held = bool(sig["close"].iloc[i + 1] > sig["close"].iloc[i])
        if held != noR_take:
            diag["held_recompute_violation"] += 1
        below = not bool(sig["above200"].iloc[i])
        wkdn = not bool(sig["w_bull"].iloc[i])
        counter_trend = bool(below and wkdn)
        reclaimed = bool(sig["above200"].iloc[i + 1]) or bool(sig["above200"].iloc[i + 2])

        if not noF_take:
            # the family counterfactual admits every non-bear fire by construction
            diag["family_cf_not_admitting_violation"] += 1

        if prod_take:
            cell = "ADMITTED"
        elif noR_take:
            cell = "RECLAIM_ADMIT"
        elif noH_take:
            cell = "HOLD_ADMIT"
        else:
            cell = "BLOCKED_BY_BOTH"
        if noR_take and noH_take and not prod_take:
            diag["disjointness_violation"] += 1
        diag[cell] += 1
        # per-leg GROSS fire counts (the leg's test was applied and refused)
        if counter_trend and not reclaimed:
            diag["RECLAIM_GROSS"] += 1
            if not held:
                diag["RECLAIM_BLOCKED_ANYWAY"] += 1
        if not held:
            diag["HOLD_GROSS"] += 1
            if counter_trend and not reclaimed:
                diag["HOLD_BLOCKED_ANYWAY"] += 1
        if not prod_take:
            diag["FAMILY_GROSS"] += 1
            diag[f"reason::{prod_reason}"] += 1
            diag[f"reason_by_cell::{prod_reason}::{cell}"] += 1

        oc = outcomes(df, d0, bench)
        if oc is None:
            diag["unfillable_no_t1"] += 1
            continue
        if oc.get("locked"):
            diag["unfillable_locked_limit"] += 1
            continue
        dd = m50 = t63 = None
        if d0 in roll_high.index and pd.notna(roll_high.get(d0)) and float(roll_high.get(d0)):
            dd = _f(100.0 * (float(close.loc[d0]) / float(roll_high.loc[d0]) - 1.0))
        if d0 in ma50.index and pd.notna(ma50.get(d0)) and float(ma50.get(d0)):
            m50 = _f(100.0 * (float(close.loc[d0]) / float(ma50.loc[d0]) - 1.0))
        if d0 in trail63.index and pd.notna(trail63.get(d0)):
            t63 = _f(100.0 * float(trail63.loc[d0]))
        ev = {"ticker": ticker, "cell": cell,
              "fam_cell": "ADMITTED" if cell == "ADMITTED" else "FAMILY_ADMIT",
              "anchor": str(d0.date()),
              "bar_label": str(pd.Timestamp(anchor_label).date()),
              "signal_bar": str(pd.Timestamp(sig.index[i]).date()),
              "prod_reason": prod_reason, "cf_reclaim_off_reason": cf_noR_reason,
              "counter_trend_branch": counter_trend, "held": held, "reclaimed": reclaimed,
              "dd_from_high_pct": dd, "ma50_gap_pct": m50, "trail63_pct": t63}
        ev.update(oc)
        events.append(ev)
    return events, diag


def dedup(events: list[dict], key: str) -> list[dict]:
    """Within-CELL, 5-trading-session dedup per name (veto_leg_audit.py convention).

    ``key`` selects the partition: "cell" for the fine 4-way split (sub-leg cells) and
    "fam_cell" for the coarse ADMITTED/FAMILY_ADMIT split.  The family MUST be deduped on
    its own partition — deduping on the fine one would let a name contribute one
    RECLAIM_ADMIT and one HOLD_ADMIT five days apart and inflate the family cell.

    Cross-cell dedup is deliberately NOT applied — it would let one cell's fire density
    suppress the other's, which is the comparison being made."""
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in events:
        by[(e["ticker"], e[key])].append(e)
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


# ── stratifier reconstruction (verbatim from the divergence audit) ────────────
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
    """P0-A gate — the reconstruction must reproduce the SHIPPED cn_gold read at the EXACT
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
    return {k: pd.DataFrame(v).sort_values("date").reset_index(drop=True)
            for k, v in rows.items() if v}


def _asof(df: pd.DataFrame | None, d: pd.Timestamp, col: str):
    if df is None or not len(df):
        return None
    m = df[df["date"] <= d]
    return m.iloc[-1][col] if len(m) else None


def stamp_stratifiers(events: list[dict], cycle_tape: dict, narr_tape: dict,
                      tick2basket: dict) -> None:
    """Attach basket / cycle / narrative / MA50 / trail-63 context to each event, PIT."""
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
        m50 = e.get("ma50_gap_pct")
        e["ma50_side"] = ("unmapped" if m50 is None
                          else ("above MA50" if float(m50) > 0 else "below MA50"))
        t63 = e.get("trail63_pct")
        e["trail63_sign"] = ("unmapped" if t63 is None
                             else ("UP (trail_63 > 0)" if float(t63) > 0
                                   else "DOWN (trail_63 <= 0)"))


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


def strat_block(events: list[dict], key: str, blocked_cell: str, cell_key: str = "cell") -> dict:
    """<blocked_cell> vs ADMITTED at every level of ``key``, both horizons."""
    out: dict = {}
    for lvl in sorted({str(e.get(key)) for e in events}):
        sub = [e for e in events if str(e.get(key)) == lvl]
        blk = [e for e in sub if e[cell_key] == blocked_cell]
        adm = [e for e in sub if e[cell_key] == "ADMITTED"]
        cell: dict = {}
        for h in HORIZONS:
            b, a = summarise(blk, h), summarise(adm, h)
            cell[f"H{h}"] = {"blocked": b, "admitted": a, "keep": keep_verdict(b, a)}
        out[lvl] = cell
    return out


# ── case receipts ────────────────────────────────────────────────────────────
def case_receipt_002155() -> dict:
    """Decompose 002155.SZ's SECOND blocker — the one the divergence audit surfaced.

    In production this name never reaches the family: the divergence veto fires first.  It
    enters this study only through the COMPOSED counterfactual (divergence removed, then the
    family evaluated), which is exactly what the divergence audit reported as
    ``counterfactual_veto_removed = failed reclaim-and-hold``.  This receipt says WHICH
    sub-leg that is."""
    rec: dict = {"ticker": CASE_TICKER, "board_date": str(CASE_DATE.date()),
                 "enters_this_study_only_via": "the composed counterfactual — in production "
                                               "the divergence veto fires FIRST, so the "
                                               "reclaim-and-hold family is never reached"}
    df = _price_frame(DATA / "china_stocks" / f"{CASE_TICKER}.parquet")
    if df is None:
        rec["error"] = "price frame unavailable"
        return rec
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    close = close[close.index <= CASE_DATE]          # PIT: the board saw only up to 08-03
    sig = sq.signal_frame(close).dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    n = len(sig)
    hi = sq._swing_highs(sig["high"])
    macd = sig["macd"]
    buys = [i for i in range(n) if bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])]
    if not buys:
        rec["error"] = "no buy marker"
        return rec
    i = buys[-1]
    bear = bool(sq._bear_div(i, sig["high"], macd, hi))
    prod_ok, prod_reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=True)
    # composed counterfactual: divergence OFF, then each family variant
    nodiv_ok, nodiv_reason = sq._buy_filter(i, sig, False, n, reclaim_veto=True)
    nodiv_noR_ok, nodiv_noR_reason = sq._buy_filter(i, sig, False, n, reclaim_veto=False)
    nodiv_noH_ok, _ = _cf_filter(i, sig, False, n, hold=False, reclaim=True)
    nodiv_noF_ok, _ = _cf_filter(i, sig, False, n, hold=False, reclaim=False)
    held = bool(sig["close"].iloc[i + 1] > sig["close"].iloc[i]) if i + 1 < n else None
    below = not bool(sig["above200"].iloc[i])
    wkdn = not bool(sig["w_bull"].iloc[i])
    reclaimed = (bool(sig["above200"].iloc[i + 1]) or bool(sig["above200"].iloc[i + 2])
                 if i + 2 < n else None)
    rec.update({
        "last_buy_bar_label": str(pd.Timestamp(sig.index[i]).date()),
        "production_verdict": {"take": None if prod_ok is None else bool(prod_ok),
                               "reason": prod_reason},
        "gate_reason_rendered": "buy blocked by filter: " + str(prod_reason),
        "bear_div": bear,
        "composed_cf_divergence_removed": {
            "take": None if nodiv_ok is None else bool(nodiv_ok), "reason": nodiv_reason},
        "composed_cf_divergence_and_RECLAIM_removed": {
            "take": None if nodiv_noR_ok is None else bool(nodiv_noR_ok),
            "reason": nodiv_noR_reason},
        "composed_cf_divergence_and_HOLD_removed": {
            "take": None if nodiv_noH_ok is None else bool(nodiv_noH_ok)},
        "composed_cf_divergence_and_WHOLE_FAMILY_removed": {
            "take": None if nodiv_noF_ok is None else bool(nodiv_noF_ok)},
        "branch": {"below_200dma": below, "weekly_down": wkdn,
                   "counter_trend_branch": bool(below and wkdn),
                   "held_next_bar": held, "reclaimed_within_2_bars": reclaimed},
        "binding_sub_leg": None,
        "dd_from_252d_high_pct": _f(100.0 * (
            float(close.iloc[-1])
            / float(close.rolling(252, min_periods=60).max().iloc[-1]) - 1.0)),
        "close_only": True,
    })
    if bool(below and wkdn):
        if held is False and reclaimed is False:
            rec["binding_sub_leg"] = "BOTH (counter-trend branch: no hold AND no reclaim)"
        elif held is False:
            rec["binding_sub_leg"] = "HOLD (counter-trend branch)"
        elif reclaimed is False:
            rec["binding_sub_leg"] = "RECLAIM (counter-trend branch)"
    elif held is False:
        rec["binding_sub_leg"] = (
            "HOLD (MAIN path — the string 'failed reclaim-and-hold' is printed here but NO "
            "reclaim is tested on this path; only the next-bar hold)")
    cand = DATA / "china_prophet_rank" / "candidates.parquet"
    if cand.exists():
        c = pd.read_parquet(cand)
        m = c[(c["ticker"] == CASE_TICKER)
              & (c["stamp_date"].astype(str) == str(CASE_DATE.date()))]
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


def case_receipt_s27(quick: bool) -> dict:
    """The §2.7 never-eligible cohort, replayed through the PRODUCTION cascade.

    For each never-eligible top-150 era runner whose frozen ``last_reason`` is the
    counter-trend string, re-run ``signal_gate.gate()`` on every era board date under BOTH
    policies (``reclaim_veto=True`` = shipped, ``False`` = the HK policy) with the series
    truncated at that date, and record whether the looser policy would have produced an
    eligible cascade verdict on >= 1 era date.  This is the CN analogue of HK's "6 of 9
    witness July markers flip block->take" receipt, and it is a production-path
    counterfactual — no reimplementation."""
    res: dict = {"era": list(S27_ERA), "featured": S27_FEATURED,
                 "source": "research/cn_prophet_audit/v1_runner_coverage_results.json "
                           "(never_eligible, last_reason = 'buy blocked by filter: "
                           "counter-trend, no 200-reclaim/hold')",
                 "method": "engine.signal_gate.gate(ticker, close_truncated_at_date) under "
                           "reclaim_veto=True (shipped) and False (the HK policy), on every "
                           "V1 era board date"}
    cov = Path(__file__).parent / "v1_runner_coverage_results.json"
    if not cov.exists():
        res["error"] = "v1_runner_coverage_results.json missing"
        return res
    runners = json.loads(cov.read_text()).get("runners") or []
    cohort = [r for r in runners
              if r.get("status") == "never_eligible"
              and "counter-trend" in str(r.get("last_reason"))]
    try:
        board = pd.read_parquet(DATA / "china_standout_track" / "board.parquet")
        board = board[board["board_definition"] == "legacy"]
        era_dates = sorted({str(d) for d in board["date"]
                            if S27_ERA[0] <= str(d) <= S27_ERA[1]})
    except Exception as e:  # noqa: BLE001 — the receipt degrades, the study does not
        res["error"] = f"board.parquet unreadable: {e}"
        return res
    if quick:
        era_dates = era_dates[:4]
    res["era_board_dates"] = len(era_dates)
    rows = []
    for r in cohort:
        t = r["ticker"]
        df = _price_frame(DATA / "china_stocks" / f"{t}.parquet")
        if df is None:
            rows.append({"ticker": t, "error": "price frame unavailable"})
            continue
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        strict_days = loose_days = 0
        first_loose = None
        reasons_strict: Counter = Counter()
        reasons_loose: Counter = Counter()
        for ds in era_dates:
            cs = close[close.index <= pd.Timestamp(ds)]
            if len(cs) < MIN_BARS:
                continue
            vs = signal_gate.gate(t, cs, reclaim_veto=True)
            vl = signal_gate.gate(t, cs, reclaim_veto=False)
            # bool(...) — never `is True`; the verdict dict carries plain Python bools but
            # an identity test would silently zero the count if that ever changed.
            if bool(vs.get("eligible")):
                strict_days += 1
            reasons_strict[str(vs.get("reason"))] += 1
            if bool(vl.get("eligible")):
                loose_days += 1
                if first_loose is None:
                    first_loose = ds
            reasons_loose[str(vl.get("reason"))] += 1
        rows.append({
            "ticker": t,
            "era_ret_pct": _f(100.0 * float(r["era_ret"])) if r.get("era_ret") is not None else None,
            "trail_21_at_start_pct": _f(100.0 * float(r["trail_21_at_start"]))
            if r.get("trail_21_at_start") is not None else None,
            "trail_63_at_start_pct": _f(100.0 * float(r["trail_63_at_start"]))
            if r.get("trail_63_at_start") is not None else None,
            "dd_from_high_at_start_pct": _f(100.0 * float(r["dd_from_high_at_start"]))
            if r.get("dd_from_high_at_start") is not None else None,
            "frozen_last_reason": r.get("last_reason"),
            "eligible_days_reclaim_veto_TRUE": strict_days,
            "eligible_days_reclaim_veto_FALSE": loose_days,
            "first_eligible_under_hk_policy": first_loose,
            "flips_to_eligible_if_RECLAIM_removed": bool(loose_days > 0 and strict_days == 0),
            "top_reason_shipped": reasons_strict.most_common(1)[0][0] if reasons_strict else None,
            "top_reason_hk_policy": reasons_loose.most_common(1)[0][0] if reasons_loose else None,
        })
    flips = [r for r in rows if r.get("flips_to_eligible_if_RECLAIM_removed")]
    res["cohort_n"] = len(rows)
    res["n_flipping_to_eligible_if_RECLAIM_removed"] = len(flips)
    res["flipping_tickers"] = [r["ticker"] for r in flips]
    res["median_era_ret_pct_of_flippers"] = _pct(
        [r["era_ret_pct"] for r in flips if r.get("era_ret_pct") is not None], 50)
    res["rows"] = rows
    res["reading"] = ("a name that flips is one the RECLAIM sub-leg alone kept off the board; "
                      "a name that does not flip was refused by the HOLD leg or by a "
                      "downstream cascade gate, and no reclaim change would have surfaced it")
    res["SELECTION_WARNING"] = (
        "THIS COHORT IS SELECTED ON WINNERS BY CONSTRUCTION — it is the top-150 names by era "
        "return. It can show that the family blocked N winners; it CANNOT show what the "
        "family's block rate is worth, because the losers it also blocked are not in this "
        "list at all. This is the same defect the HK removal's postmortem records about its "
        "own `vetoed` display lane ('never cite the vetoed lane as evidence about the veto'). "
        "The unselected evidence is the headline VETOED-vs-ADMITTED comparison above; this "
        "receipt is a mechanism illustration and a decomposition of WHICH sub-leg bound, "
        "nothing more.")
    return res


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

    # ── P0-B: the leg-H / family re-derivation must equal production, event for event ──
    p0b = {
        "pass": bool(diag["parity_mismatch_reclaim_on"] == 0
                     and diag["parity_mismatch_reclaim_off"] == 0
                     and diag["parity_checked"] > 0),
        "fires_checked": int(diag["parity_checked"]),
        "mismatch_vs_production_reclaim_veto_true": int(diag["parity_mismatch_reclaim_on"]),
        "mismatch_vs_production_reclaim_veto_false": int(diag["parity_mismatch_reclaim_off"]),
        "what_it_pins": "_cf_filter(hold=True, reclaim=True) == _buy_filter(reclaim_veto=True) "
                        "AND _cf_filter(hold=True, reclaim=False) == "
                        "_buy_filter(reclaim_veto=False), on every in-window fire — so the "
                        "hold-OFF and family-OFF branches cannot have drifted from "
                        "engine/signal_quality.py unnoticed",
        "other_invariants": {
            "pending_unreachable_violation": int(diag["pending_unreachable_violation"]),
            "disjointness_violation": int(diag["disjointness_violation"]),
            "family_cf_not_admitting_violation": int(diag["family_cf_not_admitting_violation"]),
            "held_recompute_violation": int(diag["held_recompute_violation"]),
        },
    }
    p0b["pass"] = bool(p0b["pass"] and not any(p0b["other_invariants"].values()))
    print(f"P0-B parity gate: {'PASS' if p0b['pass'] else 'FAIL'} "
          f"({p0b['fires_checked']} fires, "
          f"{p0b['mismatch_vs_production_reclaim_veto_true']}/"
          f"{p0b['mismatch_vs_production_reclaim_veto_false']} mismatches)", flush=True)
    if not p0b["pass"]:
        print("::error title=cn-reclaim-hold-audit-parity::"
              "the leg-H counterfactual drifted from production; no leg-H or family number "
              "may be read from this run", flush=True)

    raw_counts = {c: sum(1 for e in events if e["cell"] == c)
                  for c in ("ADMITTED", "RECLAIM_ADMIT", "HOLD_ADMIT", "BLOCKED_BY_BOTH")}
    ev_fine = dedup(events, "cell")
    ev_fam = dedup(events, "fam_cell")
    print(f"dedup({DEDUP_SESSIONS}d): fine {len(ev_fine)} / family {len(ev_fam)} events "
          f"({time.time()-t_start:.0f}s)", flush=True)

    # ── stratifier tapes ────────────────────────────────────────────────────
    chart = (bc.compute_china_baskets() or {}).get("chart") or {}
    stamps = weekly_stamps(chart.get("dates") or [])
    cycle_tape = build_cycle_tape(chart, stamps, args.quick)
    print(f"cycle tape: {len(cycle_tape)} baskets x {len(stamps)} weekly stamps "
          f"({time.time()-t_start:.0f}s)", flush=True)
    p0 = check_p0_cycle(chart, cycle_tape)
    print(f"P0-A cycle gate: {'PASS' if p0['pass'] else 'FAIL'} "
          f"reconstructed={p0['reconstructed']} shipped={p0['shipped']} "
          f"| weekly tape vs shipped log: {p0['weekly_tape_vs_shipped_log']}", flush=True)
    narr_tape = build_narrative_tape(stamps, args.quick)
    print(f"narrative tape: {len(narr_tape)} baskets ({time.time()-t_start:.0f}s)", flush=True)

    memb = bc._membership() or {}
    t2b = pit_basket_of(memb)
    for pool in (ev_fine, ev_fam):
        stamp_stratifiers(pool, cycle_tape, narr_tape, t2b)
        tercile_cut(pool)
        for e in pool:
            e["half"] = ("H1 2025-08..2026-01"
                         if pd.Timestamp(e["anchor"]) < pd.Timestamp("2026-02-01")
                         else "H2 2026-02..2026-07")

    adm = [e for e in ev_fine if e["cell"] == "ADMITTED"]
    rec_admit = [e for e in ev_fine if e["cell"] == "RECLAIM_ADMIT"]
    hold_admit = [e for e in ev_fine if e["cell"] == "HOLD_ADMIT"]
    both_blk = [e for e in ev_fine if e["cell"] == "BLOCKED_BY_BOTH"]
    fam_admit = [e for e in ev_fam if e["fam_cell"] == "FAMILY_ADMIT"]
    fam_adm_ctrl = [e for e in ev_fam if e["fam_cell"] == "ADMITTED"]

    # ── funnel: what each leg actually costs ────────────────────────────────
    fires = max(int(diag["fires_in_window"]), 1)
    takes = max(int(diag["ADMITTED"]), 1)
    marginal = {
        "fires_in_window": int(diag["fires_in_window"]),
        "divergence_vetoed_upstream_excluded": int(diag["bear_fires_excluded"]),
        "population_reaching_this_family": int(diag["fires_in_window"] - diag["bear_fires_excluded"]),
        "takes_today": int(diag["ADMITTED"]),
        "FAMILY": {
            "gross_blocks": int(diag["FAMILY_GROSS"]),
            "pct_of_fires": _f(100.0 * diag["FAMILY_GROSS"] / fires),
            "blocked_anyway_by_a_later_leg": 0,
            "blocked_anyway_note": "0 BY CONSTRUCTION — this family IS the entire tail of "
                                   "_buy_filter; nothing downstream of it exists inside the "
                                   "filter. The masking runs the other way (see "
                                   "upstream_masking_by_divergence) and downstream board "
                                   "gates (rank/tier/liquidity/freshness) are outside this "
                                   "instrument's scope.",
            "decision_set_newly_admitted": int(diag["FAMILY_GROSS"]),
            "extra_takes_pct_if_leg_removed": _f(100.0 * diag["FAMILY_GROSS"] / takes),
        },
        "RECLAIM": {
            "gross_blocks": int(diag["RECLAIM_GROSS"]),
            "pct_of_fires": _f(100.0 * diag["RECLAIM_GROSS"] / fires),
            "blocked_anyway_by_the_HOLD_leg": int(diag["RECLAIM_BLOCKED_ANYWAY"]),
            "blocked_anyway_pct": _f(100.0 * diag["RECLAIM_BLOCKED_ANYWAY"]
                                     / max(int(diag["RECLAIM_GROSS"]), 1)),
            "decision_set_newly_admitted": int(diag["RECLAIM_ADMIT"]),
            "decision_set_pct_of_gross": _f(100.0 * diag["RECLAIM_ADMIT"]
                                            / max(int(diag["RECLAIM_GROSS"]), 1)),
            "extra_takes_pct_if_leg_removed": _f(100.0 * diag["RECLAIM_ADMIT"] / takes),
        },
        "HOLD": {
            "gross_blocks": int(diag["HOLD_GROSS"]),
            "pct_of_fires": _f(100.0 * diag["HOLD_GROSS"] / fires),
            "blocked_anyway_by_the_RECLAIM_leg": int(diag["HOLD_BLOCKED_ANYWAY"]),
            "blocked_anyway_pct": _f(100.0 * diag["HOLD_BLOCKED_ANYWAY"]
                                     / max(int(diag["HOLD_GROSS"]), 1)),
            "decision_set_newly_admitted": int(diag["HOLD_ADMIT"]),
            "decision_set_pct_of_gross": _f(100.0 * diag["HOLD_ADMIT"]
                                            / max(int(diag["HOLD_GROSS"]), 1)),
            "extra_takes_pct_if_leg_removed": _f(100.0 * diag["HOLD_ADMIT"] / takes),
        },
        "BLOCKED_BY_BOTH": int(diag["BLOCKED_BY_BOTH"]),
        "partition_check": {
            "RECLAIM_ADMIT + HOLD_ADMIT + BLOCKED_BY_BOTH": int(
                diag["RECLAIM_ADMIT"] + diag["HOLD_ADMIT"] + diag["BLOCKED_BY_BOTH"]),
            "FAMILY_GROSS": int(diag["FAMILY_GROSS"]),
            "equal": bool(diag["RECLAIM_ADMIT"] + diag["HOLD_ADMIT"] + diag["BLOCKED_BY_BOTH"]
                          == diag["FAMILY_GROSS"]),
        },
    }

    upstream = {
        "divergence_vetoed_fires": int(diag["bear_fires_excluded"]),
        "…that this family would ALSO block": int(diag["bear_fires_family_would_also_block"]),
        "…that this family would admit (the divergence audit's decision set)":
            int(diag["bear_fires_family_would_admit"]),
        "reading": "the divergence veto masks this family upstream, not the other way round; "
                   "these two numbers ARE the divergence audit's VETOED_BLOCKED_ANYWAY / "
                   "VETOED_ADMIT split, recomputed here from the opposite side of the same "
                   "filter, so they cross-check the two instruments against each other",
    }
    cross = {
        "pins": DIVERGENCE_AUDIT_PINS,
        "this_run": {
            "fires_in_window": int(diag["fires_in_window"]),
            "vetoed_gross": int(diag["bear_fires_excluded"]),
            "vetoed_blocked_anyway": int(diag["bear_fires_family_would_also_block"]),
            "vetoed_admit": int(diag["bear_fires_family_would_admit"]),
            "admitted": int(diag["ADMITTED"]),
            "admitted_failed_other_leg": int(diag["FAMILY_GROSS"]),
        },
    }
    cross["all_match"] = bool(not args.quick and all(
        cross["this_run"][k] == DIVERGENCE_AUDIT_PINS[k] for k in cross["this_run"]))

    # ── reason-string decomposition (the ambiguity, counted) ─────────────────
    reason_counts = {k.split("::", 1)[1]: int(v) for k, v in diag.items()
                     if k.startswith("reason::")}
    reason_by_cell: dict[str, dict[str, int]] = defaultdict(dict)
    for k, v in diag.items():
        if k.startswith("reason_by_cell::"):
            _, rsn, cll = k.split("::", 2)
            reason_by_cell[rsn][cll] = int(v)
    reason_block = {
        "gross_blocks_by_shipped_reason_string": reason_counts,
        "shipped_reason_string_by_decision_cell": dict(reason_by_cell),
        "finding": "neither shipped string identifies which sub-leg refused. "
                   "'counter-trend, no 200-reclaim/hold' is printed for a failed hold, a "
                   "failed reclaim, or both; 'failed reclaim-and-hold' is the MAIN-path "
                   "string where NO reclaim is tested at all — only the next-bar hold. Board "
                   "copy naming one blocking reason inherits both ambiguities.",
    }

    # ── headlines ───────────────────────────────────────────────────────────
    headline: dict = {}
    for label, pool, ctrl in (("FAMILY", fam_admit, fam_adm_ctrl),
                              ("RECLAIM", rec_admit, adm),
                              ("HOLD", hold_admit, adm),
                              ("BLOCKED_BY_BOTH", both_blk, adm)):
        blk: dict = {}
        for h in HORIZONS:
            b, a = summarise(pool, h), summarise(ctrl, h)
            blk[f"H{h}"] = {"blocked": b, "admitted": a, "keep": keep_verdict(b, a)}
        headline[label] = blk

    # fill-convention sensitivity: production open-preferring fill vs the pinned HL2
    sens: dict = {}
    for h in HORIZONS:
        for label, pool in (("FAMILY_ADMIT", fam_admit), ("RECLAIM_ADMIT", rec_admit),
                            ("HOLD_ADMIT", hold_admit), ("ADMITTED", adm)):
            rows = [e for e in pool if e.get(f"excp{h}") is not None]
            sens[f"H{h}_{label}"] = {
                "n": len(rows),
                "win_pct_hl2": _f(100.0 * sum(1 for e in rows if e[f"exc{h}"] > 0) / len(rows))
                if rows else None,
                "win_pct_prod_open": _f(100.0 * sum(1 for e in rows if e[f"excp{h}"] > 0) / len(rows))
                if rows else None,
                "median_excess_hl2": _pct([e[f"exc{h}"] for e in rows], 50),
                "median_excess_prod_open": _pct([e[f"excp{h}"] for e in rows], 50),
            }

    # cycle composition — does the family land DISPROPORTIONATELY on early-Recovery names?
    def _comp(pool: list[dict]) -> dict:
        mapped = [e for e in pool if e["cycle_cell"] != "unmapped"]
        rec = [e for e in mapped if e["cycle_cell"] == "Recovery+/Trough+"]
        return {"n_total": len(pool), "n_mapped": len(mapped),
                "mapped_coverage_pct": _f(100.0 * len(mapped) / len(pool)) if pool else None,
                "n_recovery_plus": len(rec),
                "recovery_plus_share_of_mapped_pct":
                    _f(100.0 * len(rec) / len(mapped)) if mapped else None}
    composition = {"family_admit": _comp(fam_admit), "reclaim_admit": _comp(rec_admit),
                   "hold_admit": _comp(hold_admit), "admitted": _comp(adm),
                   "reading": "if the family systematically blocked early-Recovery reclaims, "
                              "its Recovery+/Trough+ share would EXCEED the admitted cell's"}

    strat_keys = ("cycle_cell", "dd_tercile", "ma50_side", "trail63_sign",
                  "narrative_level", "half")
    strat = {
        "FAMILY": {k: strat_block(ev_fam, k, "FAMILY_ADMIT", cell_key="fam_cell")
                   for k in strat_keys},
        "RECLAIM": {k: strat_block(ev_fine, k, "RECLAIM_ADMIT") for k in strat_keys},
        "HOLD": {k: strat_block(ev_fine, k, "HOLD_ADMIT") for k in strat_keys},
    }

    # the CONTINUATION cell, called out on its own because it is the §2.7 evidence
    continuation = {
        "definition": "trail_63 > 0 at the anchor close (close[d0]/close[d0-63] - 1), the "
                      "v1_runner_coverage_audit.py:88 convention — an UPTRENDING name that "
                      "the family refuses",
        "caveat": "§2.7's actual never-eligible cohort sits at MEDIAN trail_63 = -11.2% "
                  "(shallow, not positive), so this sign split is a STRICTER continuation "
                  "definition than that cohort's; per-cell trail_63 medians are printed in "
                  "every summarise() block so the two are not conflated",
        "RECLAIM": strat["RECLAIM"]["trail63_sign"],
        "HOLD": strat["HOLD"]["trail63_sign"],
        "FAMILY": strat["FAMILY"]["trail63_sign"],
    }

    results = {
        "instrument": "research/cn_prophet_audit/cn_reclaim_hold_audit.py",
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "IN-SAMPLE, MOTIVATING-ONLY — no promotion, no gate change",
        "mirrors": "research/cn_prophet_audit/cn_divergence_veto_audit.py (same window, "
                   "panel, anchor, fill, metrics, keep rule and funnel discipline)",
        "family": {
            "name": "reclaim-and-hold",
            "shipped_reason_strings": ["counter-trend, no 200-reclaim/hold",
                                       "failed reclaim-and-hold"],
            "implementation": "engine/signal_quality.py:178 _buy_filter — the entire tail "
                              "after the divergence veto (lines 212-225)",
            "sub_leg_RECLAIM": {
                "condition": "engine/signal_quality.py:214-220 — a name BOTH below its "
                             "200-day average (above200 False, :99) AND weekly-down (w_bull "
                             "False, :97) must close back above the 200-day average at bar "
                             "i+1 or i+2 (`reclaim = a[i+1] or a[i+2]`, :218)",
                "separable": True,
                "counterfactual": "_buy_filter(i, sig, bear, n, reclaim_veto=False) — a "
                                  "PRODUCTION call (engine/signal_gate.py:155 exposes it, "
                                  "scripts/build_hk_library.py ships it, "
                                  "tests/test_hk_reclaim_veto_policy.py:46-59 pins the flip "
                                  "and :83-90 pins branch-identity off the counter-trend "
                                  "path). No reimplementation.",
                "precedent": "HK deleted this leg — PR #4470 / commit e337d95f312, operator "
                             "ruling 2026-08-03, era stamp hk_prophet_v1 -> v2",
            },
            "sub_leg_HOLD": {
                "condition": "engine/signal_quality.py:212 `held = close[i+1] > close[i]`, "
                             "consumed at :219 (`ok = held and reclaim`) and :225 (`return "
                             "held`)",
                "separable": False,
                "counterfactual": "_cf_filter(..., hold=False) — a 6-line re-derivation, "
                                  "because no shipped caller can switch this leg off. "
                                  "PARITY-GATED on 100% of in-window fires (P0-B).",
                "precedent": "HK KEPT this leg on both policies (the #4470 commit message "
                             "and HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 G6 both "
                             "say so explicitly)",
            },
            "cn_call_site": "scripts/build_china_library.py:1960 signal_gate.gate(ticker, "
                            "close) -> engine/signal_gate.py:155 gate(..., "
                            "reclaim_veto=True) [DEFAULT] -> analyze(ticker, daily_close) "
                            "with NO high/low (close-only)",
        },
        "design": {
            "window": [str(WIN_START.date()), str(WIN_END.date())],
            "grade_asof": str(GRADE_ASOF.date()), "min_bars": MIN_BARS,
            "horizons": list(HORIZONS), "benchmark": BENCH,
            "fill": "T+1 HL2, locked-limit (T+1 high==low==close) EXCLUDED",
            "anchor": "last daily session of 3B bar i+2 — the first close at which the label "
                      "is knowable; marker-date grading is forbidden "
                      "(engine/signal_quality.py:198-206)",
            "dedup": f"within-cell, {DEDUP_SESSIONS} trading sessions per name; the family "
                     f"cell is deduped on its OWN coarse partition",
            "keep_rule": {
                "margin_pp": KEEP_MARGIN_PP, "min_cell_n": MIN_CELL_N,
                "return_leg": "win%(<leg>_ADMIT) <= win%(ADMITTED) - 3pp",
                "risk_leg": "catastrophic%(<leg>_ADMIT) >= catastrophic%(ADMITTED) + 3pp "
                            "OR MAE-p10(<leg>_ADMIT) <= MAE-p10(ADMITTED) - 3pp",
                "earns_iff": "either leg passes on a cell with n >= 100 on BOTH sides",
                "precedent": "research/signal_engine/VETO_LEG_AUDIT.md (>= +3pp on the "
                             "verdict metric); HK removal keep pairing in "
                             "research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 G6",
                "hk_measured_bar": "HK's own removal did NOT clear this bar in either "
                                   "direction: unblocked cohort mean +0.55%/20d with a "
                                   "zero-crossing CI, median 60d MAE -9.0% vs -7.4%, "
                                   "P(excess<-20%) 5.8% -> 7.9%. It shipped as an operator "
                                   "product bet on an ungradeable regime, explicitly 'a bet "
                                   "on that regime, not a finding about it'.",
            },
            "catastrophic_def": f"ABSOLUTE return <= {CATASTROPHIC_PP}%",
            "mfe_note": "mfe_p90_pct / mfe_median_pct are REPORTED ONLY and are NOT inputs "
                        "to the keep rule (which stays byte-identical to the divergence "
                        "audit's). They are carried because the HK removal postmortem "
                        "records a retraction on this exact leg family — 'endpoint excess is "
                        "the wrong lens for a bounce' — and MAE without MFE is a "
                        "one-directional read of a two-sided path.",
        },
        "p0b_counterfactual_parity_gate": p0b,
        "p0a_cycle_reconstruction_gate": p0,
        "diagnostics": {k: int(v) for k, v in sorted(diag.items())
                        if not k.startswith(("reason::", "reason_by_cell::"))},
        "raw_event_counts_pre_dedup": raw_counts,
        "deduped_event_counts": {
            "fine": {"ADMITTED": len(adm), "RECLAIM_ADMIT": len(rec_admit),
                     "HOLD_ADMIT": len(hold_admit), "BLOCKED_BY_BOTH": len(both_blk)},
            "family": {"ADMITTED": len(fam_adm_ctrl), "FAMILY_ADMIT": len(fam_admit)},
        },
        "leg_marginal_cost": marginal,
        "upstream_masking_by_divergence": upstream,
        "cross_check_vs_divergence_audit": cross,
        "reason_string_decomposition": reason_block,
        "cycle_cell_composition": composition,
        "headline": headline,
        "fill_convention_sensitivity": sens,
        "continuation_cell": continuation,
        "strat": strat,
        "case_receipt_002155": case_receipt_002155(),
        "case_receipt_s27_never_eligible": case_receipt_s27(args.quick),
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
                          "p0b": p0b, "p0a": p0,
                          "leg_marginal_cost": marginal,
                          "cross_check": cross,
                          "headline": headline}, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
