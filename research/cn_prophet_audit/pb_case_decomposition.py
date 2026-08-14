#!/usr/bin/env python3
"""CN LIMIT-MOVE ALPHA — P-B: case decomposition of the 300363-class first-board winners.

    TZ=UTC python3 research/cn_prophet_audit/pb_case_decomposition.py

AUTHORITY: `none_research_display_only`.  Nothing in this file or its receipts ranks,
sizes, gates, alerts or trades.  This instrument COUNTS, ORDERS and DISTRIBUTES.  It
computes no lift, no t-statistic, no interval, no null, no comparison against any
non-winner baseline, and no selection-skill claim of any kind — by charter (program home
`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md` sec.3, the P-B row), because a
decomposition of winners has NO CONTROL ARM.  The comparison arm is an inferential study
that must be PREREGISTERED; it is logged in the ore ledger below and is not smuggled in
here by dividing two numbers.

STOP-SHIP compliance: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` governs.  This instrument
cites no withdrawn artifact and no W1-W3 construction or number.  A grep-verified receipt
of that fact is emitted with every run (`verify.stop_ship_reference_scan`).

===============================================================================
THE QUESTION (operator thesis, program home sec.1)
===============================================================================
For winners of the 300363 class — names that print a FIRST limit board out of a washout
state — WHICH footprints were present, in what ORDER did they arm, and at what LEAD TIMES
before the board?

This is an ANATOMY, not a test.  Every number below describes the winners and only the
winners.  See `does_not_establish`.

-------------------------------------------------------------------------------
1. THE COHORT — a FIRST-BOARD event out of a washout state
-------------------------------------------------------------------------------
Re-derived directly from `data/china_stocks_raw` through W-P0's own tolerant detector and
its own COLD rule, reached by IMPORT rather than by re-implementation (see THE PIN).

    EVENT     a bar E with W-P0's tolerant limit-up close (`lu`, W-P0 L986:
              close >= round(prev_close * (1 + w), 2) * (1 - 0.002))
    EVE       the name's PREVIOUS panel session, E-1.  Every state in this file is read
              at the EVE, so nothing is measured on the board bar itself.
    COLD      W-P0's own `cold` flag AT THE EVE (W-P0 L990).  cold[E-1] means no tolerant
              board in (E-1)-19 .. (E-1), which is exactly E-20 .. E-1 — "no tolerant
              board in the prior 20 sessions".  This is what makes the event a genuine
              0 -> 1 IGNITION rather than a re-board, and it is W-P0's sec.5 lemma
              instantiated at H = 1.
    STEP RULE the EVE -> EVENT pair must sit inside W-P0's own closure-tolerant step gap
              (MAX_STEP_GAP_DAYS = 21 calendar days, W-P0 L354), so a name resuming after
              a long suspension is never credited with a year-old "eve".

The panel is W-P0's own `build_panel()` over W-P0's own window (2011-01-01 -> 2026-08-07),
so a "session" throughout this file means a LIVE, in-window bar on that name's own axis
(W-P0's live-bar law: finite positive prev-close, outside the IPO window, not an
ex-dividend jump, volume > 0 — suspension placeholders are not sessions).

PARTITION, at the EVE (W-P0's own dd250 bands, L1209, left-open / right-closed):
    d1_m20_m35   -35% <  dd250 <= -20%
    d2_m35_m50   -50% <  dd250 <= -35%
    d3_le_m50            dd250 <= -50%
Events with dd250 > -20% (`d0_gt_m20`) and events whose dd250 is not yet measurable
(`na` — fewer than DD_MINP = 200 bars of history) are OUT OF COHORT.  Their counts are
reported ONCE as context and they enter no other table.

BOARDS ARE NEVER POOLED (W-P0 sec.2 / the target-class law).  Every table is keyed on
W-P0's `board_key`: `main`, `chinext10` (SZ 300x/301x BEFORE 2020-08-24), `chinext20`
(ON/AFTER — the band transition splits ChiNext into two POPULATIONS), `star`.  The
ChiNext regime split is therefore respected by construction, and main-board and ChiNext
never share a cell.

ERAS: W-P0's own ERA_BOUNDS (L387), keyed on the EVENT year.  Eve and event share a year
except across a New-Year boundary; the event's year is used and this sentence is the
disclosure.

-------------------------------------------------------------------------------
2. THE FOOTPRINTS — eight booleans, every one a direct reading of a W-P0 column
-------------------------------------------------------------------------------
Nothing here is a new indicator.  Each footprint is a threshold ALREADY defined by W-P0,
read off the column W-P0 produced:

    dd_le_m20           dd250 <= -20%                       (S2 depth, shallow cut)
    dd_le_m35           dd250 <= -35%                       (S2 depth, deep cut)
    under_ma200         close < SMA(close, 200)             (S3)
    confluence_long     the Terminal oracle's 3D long state (S1, `s1_3d_long`)
    cb_recent           3D crossover-buy within 2 3D bars   (S1, `s1_3d_cb_recent`)
    sector_deep35_ge40  40%+ of the name's sector members 35%+ off their own 250-session
                        highs, leave-one-out                (S4, `sect35_band` in
                        {s2_40_60, s3_gt60})
    quiet_base          20-bar realised-vol rank in the bottom third (S5a, `base_flag`)
    volz_gt1            volume z-score of the bar > 1       (S5a, `volz_band` in
                        {v2_1_2, v3_gt2})

The BANDED forms (`dd_band`, `below_band`, `dur_band`, `sect35_band`, `volz_band`) are
reported as PRESENCE distributions at the eve; the eight booleans above are what the
arming timeline is computed on, because an arming needs a false -> true transition.

CORE-4, pre-registered before any number was read, as the operator's four named footprint
families (program home sec.1): dd_le_m20 (washout depth), under_ma200 (basing),
confluence_long (terminal confluence), sector_deep35_ge40 (sector-wide washout).  The
"complete order" tables run on the CORE-4 because an 8-way signature is sparse to the
point of being a list of singletons; the full 8-way signature counts are in the JSON.

-------------------------------------------------------------------------------
3. ARMING — the definition, pinned
-------------------------------------------------------------------------------
Over a lookback of ARMING_LOOKBACK = 60 sessions ending AT THE EVE (positions
E-60 .. E-1 on the name's own session axis):

    ARMED       the footprint is TRUE at the eve.  A footprint false at the eve has no
                arming and is counted as `not armed`, never as a zero lead.
    ARMING      the START OF THE FINAL TRUE-RUN ending at the eve — i.e. the most recent
                session on which the footprint transitioned false -> true AND remained
                true through the eve.  IF A FOOTPRINT OSCILLATES, THE ARMING IS THE START
                OF THE FINAL RUN, NOT THE FIRST TIME IT WAS EVER TRUE.  Implemented as
                `run_start = eve_pos - streak_lengths(f)[eve_pos] + 1` on W-P0's own
                `streak_lengths` helper (W-P0 L535), and probed directly by
                `verify.arming_is_final_true_run`.
    LEAD        sessions from the arming session to the BOARD session, E - run_start.
                A footprint that armed exactly at the eve has LEAD = 1.  Uncensored leads
                are therefore in [1, 59].
    CENSORED    the true-run reaches the first position of the lookback window, so the
                arming may be older than the window can see.  Reported as `>=60`, never
                as 60, and never dropped.

ELIGIBILITY: an event enters the arming tables only when at least ARMING_LOOKBACK full
sessions precede its eve on that name's axis.  Events nearer the left edge of the panel
would produce a censoring bound BELOW 60, which would corrupt the quantile ordering, so
they are EXCLUDED and their count is printed.  They remain in the cohort and presence
tables.

QUANTILES UNDER CENSORING.  Censored leads are >= 60 and every uncensored lead is <= 59,
so the censored observations are exactly the top of the sorted order.  Quantiles use the
NEAREST-RANK rule on the full armed set with the censored block at the top: a quantile
that lands inside the uncensored part is an exact session count; one that lands in the
censored block is reported as `>=60`.  Nothing is imputed and no censored value is
dropped to make a median printable.

PRECEDENCE UNDER CENSORING.  For a pair (A, B) both armed at the eve: if exactly one is
censored, that one armed strictly earlier and the pair IS resolved; if BOTH are censored
their relative order is unknowable from a 60-session window and the pair is counted as
UNRESOLVED, never as a tie and never as a coin flip.  Equal uncensored leads are counted
as SAME-SESSION and are excluded from the strict-precedence denominator, which is printed
beside every rate.

-------------------------------------------------------------------------------
4. THE PIN (no third re-derivation of the oracle math)
-------------------------------------------------------------------------------
Every footprint, band, era boundary, the tolerant detector, the cold rule and the run-
length helper are IMPORTED from `research/cn_prophet_audit/washout_onset_w1.py` (W-P0).
The module is IMPORT-SAFE: it guards execution behind `if __name__ == "__main__"`
(W-P0 L2285) and does no work at import beyond constant binding and an existence check on
its input stores.  Nothing is copied and nothing is re-derived.  Pinned symbols and their
W-P0 source lines (`pin.w1_sha256` fixes the exact file this ran against, and
`verify.pin_line_numbers_resolve` fails if any pinned line stops holding its symbol):

    LIMIT_CLOSE_TOL          L353    the 0.002 tolerant cushion
    MAX_STEP_GAP_DAYS        L354    the closure-tolerant eve -> event step rule
    COLD_LOOKBACK_K          L357    K=20 no-board lookback defining a COLD bar
    DD_LOOKBACK / DD_MINP    L371    250-session high behind the drawdown footprint
    MA_LEN / MA_MINP         L372    the 200DMA footprint
    RV_LEN / RV_RANK_LOOKBACK L373   the quiet-base footprint
    ERA_BOUNDS               L387    the era boundaries, used verbatim
    SURVIVORSHIP_STAMP       L401    inherited verbatim — see INHERITED LIMITS
    streak_lengths()         L535    the run-length helper the arming rule is built on
    era_of()                 L584    year -> era
    _git()                   L591    vintage stamping helper
    confluence_states()      L823    S1 — the Terminal confluence transcription
    process_ticker()         L947    per-name bars -> lu / cold / dd250 / band inputs
    w1_min_history_gate      L948    `len(df) < 400` — the gate that declines to measure
    tolerant_detector        L986    the tolerant limit-up close itself
    cold_rule                L990    the K=20 cold flag itself
    build_panel()            L1088   the full-cross-section loop over china_stocks_raw
    _band()                  L1154   the left-open / right-closed band convention
    attach_conditioners()    L1173   S4 sector breadth + the bands
    dd_band                  L1209   the dd250 partition this cohort is banded on
    below_band               L1214   the below-200DMA duration bands
    sect35_band              L1217   the sector-washout breadth bands
    volz_band                L1219   the volume z-score bands
    base_flag                L1221   the quiet-base flag

-------------------------------------------------------------------------------
5. INHERITED LIMITS (they travel with the pin; restating them is not optional)
-------------------------------------------------------------------------------
* SURVIVORSHIP.  The footprint plane is W-P0's curated large-cap survivor slice.
  Delisted names are ABSENT, so every event here is an event on a name that LIVED.
  Nothing in this file extrapolates to small caps in either direction.
* BACK-ADJUSTED BASIS.  `china_stocks_raw` is back-adjusted OHLCV (W-P0's BASIS NOTE,
  L49).  Adjustment preserves returns, so every drawdown, moving average, volume z-score
  and indicator here is unaffected; only the round-to-tick limit PRICE is, and W-P0's
  0.002 tolerance is the cushion for exactly that.  The residual is MEASURED, not
  assumed, in `verify.detector_vs_zt_pool`.
* CURRENT SECTOR MEMBERSHIP.  S4 breadth applies TODAY's sector map to 15 years of
  history (W-P0's own stamped caveat).  It is not a point-in-time sector statistic.

-------------------------------------------------------------------------------
6. DETERMINISM
-------------------------------------------------------------------------------
Run as `TZ=UTC python3 research/cn_prophet_audit/pb_case_decomposition.py` from the repo
root.  No wall-clock, no runtime, no hostname and no locale-dependent ordering enters
either receipt: two consecutive runs at the same commit produce BYTE-IDENTICAL output.
The artifact date is a FROZEN CONSTANT (`ARTIFACT_DATE`), never `now()`.  Store vintage
is stamped from git at write time and every stamp must be an ancestor of the build head
or the instrument refuses to write (the A4 provenance guard).

-------------------------------------------------------------------------------
AMENDMENTS (post-first-number changes; "none" means the pre-registration held)
-------------------------------------------------------------------------------
Listed in `amendments` in both receipts and in the writeup's Amendments section.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "research" / "cn_prophet_audit"
W1_PATH = OUT_DIR / "washout_onset_w1.py"

# FROZEN. The UTC date this artifact was built. Never computed from the clock — a
# `now()` here would make consecutive runs differ and break the determinism contract.
ARTIFACT_DATE = "2026-08-13"

OUT_JSON = OUT_DIR / f"PB_CASE_DECOMPOSITION_{ARTIFACT_DATE}.json"
OUT_MD = OUT_DIR / f"PB_CASE_DECOMPOSITION_{ARTIFACT_DATE}.md"

RAW_DIR = REPO / "data" / "china_stocks_raw"
ZT_P = REPO / "data" / "china_zt_pool" / "pool.parquet"

# ── frozen parameters of THIS decomposition ───────────────────────────────────

ARMING_LOOKBACK = 60            # sessions of lookback ending AT THE EVE
COHORT_BANDS = ("d1_m20_m35", "d2_m35_m50", "d3_le_m50")
OUT_OF_COHORT_BANDS = ("d0_gt_m20", "na")
BOARD_ORDER = ("main", "chinext10", "chinext20", "star")
TOP_SIGNATURES = 6              # signatures printed per board in the writeup

WORKED_EXAMPLE_TICKER = "300363.SZ"
WORKED_EXAMPLE_BOARD_DATE = pd.Timestamp("2026-08-07")
WORKED_EXAMPLE_TAIL = 20        # sessions of the eve-anchored footprint tape printed

AUTHORITY = "none_research_display_only"
TIER_STAMP = ("display / audit tier — counts, orders and distributions of WINNERS only; "
              "not a promotion, not a gate, not a ranker, not a sizing input; no lift, "
              "no t-statistic, no interval and no selection-skill claim is quoted "
              "anywhere in this artifact")

# ── the footprints (every one a direct reading of a W-P0-produced column) ─────

FOOTPRINTS = OrderedDict([
    ("dd_le_m20", ("dd250 <= -20% off the 250-session high (W-P0 S2, shallow cut)",
                   "DD20")),
    ("dd_le_m35", ("dd250 <= -35% off the 250-session high (W-P0 S2, deep cut)", "DD35")),
    ("under_ma200", ("close below the 200DMA (W-P0 S3, `under_ma`)", "MA200")),
    ("confluence_long", ("the Terminal oracle's 3D long state (W-P0 S1, `s1_3d_long`)",
                         "CONF")),
    ("cb_recent", ("3D crossover-buy within 2 3D bars (W-P0 S1, `s1_3d_cb_recent`)",
                   "CB")),
    ("sector_deep35_ge40", ("40%+ of the name's sector members 35%+ off their own "
                            "250-session highs, leave-one-out (W-P0 S4)", "SECT")),
    ("quiet_base", ("20-bar realised-vol rank in the bottom third (W-P0 S5a, "
                    "`base_flag`)", "QB")),
    ("volz_gt1", ("volume z-score of the bar > 1 (W-P0 S5a, `volz_band` above v1)",
                  "VZ")),
])
FKEYS = tuple(FOOTPRINTS)
FSHORT = {k: v[1] for k, v in FOOTPRINTS.items()}

# Pre-registered before any number was read: the operator's four named footprint families.
CORE4 = ("dd_le_m20", "under_ma200", "confluence_long", "sector_deep35_ge40")

# Bands reported as PRESENCE distributions at the eve (W-P0's own band columns).
BAND_COLS = OrderedDict([
    ("dd_band", "washout depth at the eve (the cohort partition itself)"),
    ("below_band", "consecutive sessions below the 200DMA at the eve"),
    ("dur_band", "sessions since the last new 250-session high at the eve"),
    ("sect35_band", "share of sector members 35%+ off their own highs, leave-one-out"),
    ("volz_band", "volume z-score band of the eve bar"),
])

# ── STOP-SHIP token scan ──────────────────────────────────────────────────────
# ASSEMBLED FROM FRAGMENTS ON PURPOSE: this instrument scans its OWN source text for these
# tokens, so writing them as literals would guarantee a false positive and make the check
# useless. No full token ever appears verbatim in this file.
_WAVES = ("1", "2", "3")
_ADJ, _LEG, _LIM, _TAPE = "adjusted", "legal", "limit", "tape"
WITHDRAWN_TOKENS = tuple(
    [f"cn_limit_alpha_w{i}" for i in _WAVES]
    + [f"limit_alpha_w{i}" for i in _WAVES]
    + [f"W{i}_RESULTS" for i in _WAVES]
    + [f"cn_limit_washout_w{i}" for i in _WAVES]
    + [f"{_ADJ}_{_TAPE}_{_LEG}_{_LIM}", f"{_LEG}_{_LIM}_on_{_ADJ}"]
)

# The pin, as (symbol -> (W-P0 line, the token that must appear on it)).
PIN_SYMBOLS = OrderedDict([
    ("LIMIT_CLOSE_TOL", (353, "LIMIT_CLOSE_TOL")),
    ("MAX_STEP_GAP_DAYS", (354, "MAX_STEP_GAP_DAYS")),
    ("COLD_LOOKBACK_K", (357, "COLD_LOOKBACK_K")),
    ("DD_LOOKBACK/DD_MINP", (371, "DD_LOOKBACK")),
    ("MA_LEN/MA_MINP", (372, "MA_LEN")),
    ("RV_LEN/RV_RANK_LOOKBACK", (373, "RV_LEN")),
    ("ERA_BOUNDS", (387, "ERA_BOUNDS")),
    ("SURVIVORSHIP_STAMP", (401, "SURVIVORSHIP_STAMP")),
    ("streak_lengths", (535, "def streak_lengths")),
    ("era_of", (584, "def era_of")),
    ("_git", (591, "def _git")),
    ("confluence_states", (823, "def confluence_states")),
    ("process_ticker", (947, "def process_ticker")),
    ("w1_min_history_gate", (948, "len(df) < 400")),
    ("tolerant_detector", (986, "LIMIT_CLOSE_TOL")),
    ("cold_rule", (990, "cold = live")),
    ("build_panel", (1088, "def build_panel")),
    ("_band", (1154, "def _band")),
    ("attach_conditioners", (1173, "def attach_conditioners")),
    ("dd_band", (1209, "dd_band")),
    ("below_band", (1214, "below_band")),
    ("sect35_band", (1217, "sect35_band")),
    ("volz_band", (1219, "volz_band")),
    ("base_flag", (1221, "base_flag")),
    ("import_safe_guard", (2285, '__name__ == "__main__"')),
])


def stop_ship_scan(texts: dict):
    """Scan named surfaces for withdrawn-artifact references. Returns (passed, detail)."""
    hits = {}
    for name, txt in texts.items():
        low = txt.lower()
        found = sorted({t for t in WITHDRAWN_TOKENS if t.lower() in low})
        if found:
            hits[name] = found
    return (not hits), {"hits": hits, "tokens_scanned": len(WITHDRAWN_TOKENS),
                        "surfaces": sorted(texts)}


# ── W-P0 import (THE PIN) ─────────────────────────────────────────────────────


def load_w1():
    """Import W-P0 by path. Returns (module, sha256)."""
    if not W1_PATH.exists():
        raise SystemExit(
            f"MISSING PIN SOURCE: {W1_PATH}\n"
            "P-B imports every footprint definition from W-P0 and re-derives none of "
            "them. Run this on a checkout of main where that file is tracked.")
    sha = hashlib.sha256(W1_PATH.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("_pb_w1", W1_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pb_w1"] = mod
    spec.loader.exec_module(mod)
    return mod, sha


def _r(x, nd=4):
    if x is None:
        return None
    x = float(x)
    if not np.isfinite(x):
        return None
    return round(x, nd)


def _git(*args: str) -> str:
    """Vintage helper — same shape as W-P0 L591."""
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNAVAILABLE"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return _r(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    return o


# ── stage 1 — the footprint plane (imported W-P0 math, unchanged) ─────────────


def build_footprint_panel(w1):
    """W-P0's own panel over W-P0's own window. No footprint math is re-implemented."""
    panel, pmeta = w1.build_panel()
    panel, cmeta = w1.attach_conditioners(panel, None)
    panel = panel.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)
    pmeta = dict(pmeta)
    pmeta["sector_coverage_pct"] = cmeta.get("sector_coverage_pct")
    pmeta["panel_rows"] = int(len(panel))
    pmeta["panel_sessions"] = int(panel["date"].nunique())
    pmeta["panel_names"] = int(panel["ticker"].nunique())
    return panel, pmeta


def derive_footprints(panel: pd.DataFrame) -> pd.DataFrame:
    """The eight booleans. Every one is a direct reading of a W-P0-produced column."""
    dd = panel["dd250"].to_numpy(np.float64)
    sect = panel["sect35_band"].to_numpy()
    volz = panel["volz_band"].to_numpy()
    panel["dd_le_m20"] = np.isfinite(dd) & (dd <= -0.20)
    panel["dd_le_m35"] = np.isfinite(dd) & (dd <= -0.35)
    panel["under_ma200"] = panel["under_ma"].to_numpy(bool)
    panel["confluence_long"] = panel["s1_3d_long"].to_numpy(bool)
    panel["cb_recent"] = panel["s1_3d_cb_recent"].to_numpy(bool)
    panel["sector_deep35_ge40"] = np.isin(sect, ("s2_40_60", "s3_gt60"))
    panel["quiet_base"] = panel["base_flag"].to_numpy(bool)
    panel["volz_gt1"] = np.isin(volz, ("v2_1_2", "v3_gt2"))
    return panel


# ── stage 2 — the cohort ──────────────────────────────────────────────────────

EVE_STATE_COLS = ["dd250", "dd_band", "dur_band", "below_band", "sect35_band",
                  "volz_band", "sect_deep35_pct", "sector"] + list(FKEYS)


def extract_events(panel: pd.DataFrame, w1) -> pd.DataFrame:
    """First-board events: a tolerant board whose EVE was COLD.

    Reads ONLY W-P0's own `lu` (L986) and `cold` (L990) columns — this is an index scan
    over an already-computed detector output, never a second detector.
    """
    idx_map = panel.groupby("ticker", sort=True).indices
    lu_all = panel["lu"].to_numpy(bool)
    cold_all = panel["cold"].to_numpy(bool)
    day_all = panel["date"].to_numpy().astype("datetime64[D]").astype(np.int64)

    r_evt, r_eve, p_evt, gaps = [], [], [], []
    for t in sorted(idx_map):
        gi = np.sort(idx_map[t])
        e = np.flatnonzero(lu_all[gi])
        e = e[e >= 1]
        if e.size == 0:
            continue
        v = e - 1
        gap = day_all[gi[e]] - day_all[gi[v]]
        ok = cold_all[gi[v]] & (gap <= w1.MAX_STEP_GAP_DAYS)
        if not ok.any():
            continue
        e, v, gap = e[ok], v[ok], gap[ok]
        r_evt.append(gi[e])
        r_eve.append(gi[v])
        p_evt.append(e)
        gaps.append(gap)

    if not r_evt:
        return pd.DataFrame()
    r_evt = np.concatenate(r_evt)
    r_eve = np.concatenate(r_eve)
    p_evt = np.concatenate(p_evt)
    gaps = np.concatenate(gaps)

    ev = pd.DataFrame({
        "ticker": panel["ticker"].to_numpy()[r_evt],
        "board_key": panel["board_key"].to_numpy()[r_evt],
        "event_date": panel["date"].to_numpy()[r_evt],
        "eve_date": panel["date"].to_numpy()[r_eve],
        "eve_to_event_calendar_days": gaps.astype(np.int32),
        "evt_pos": p_evt.astype(np.int64),
        "row_eve": r_eve,
    })
    for c in EVE_STATE_COLS:
        ev[c] = panel[c].to_numpy()[r_eve]
    ev["era"] = pd.Series(pd.DatetimeIndex(ev["event_date"]).year).map(w1.era_of).to_numpy()
    ev["in_cohort"] = np.isin(ev["dd_band"].astype(str).to_numpy(), COHORT_BANDS)
    ev["arming_eligible"] = ev["evt_pos"].to_numpy() >= ARMING_LOOKBACK
    return ev.sort_values(["event_date", "ticker"], kind="mergesort").reset_index(drop=True)


# ── stage 3 — the arming timeline ─────────────────────────────────────────────


def compute_armings(panel: pd.DataFrame, ev: pd.DataFrame, w1):
    """Per event x footprint: armed at the eve, the arming lead, and censoring.

    ARMING = the START OF THE FINAL TRUE-RUN ending at the eve.  If a footprint
    oscillates inside the window, the arming is the start of the LAST run, not the first
    time the footprint was ever true.  `run_start = eve_pos - streak[eve_pos] + 1` where
    `streak` is W-P0's own run-length helper (L535) — so the definition is one line and
    `verify.arming_is_final_true_run` probes it directly on synthetic oscillators.

    LEAD = event_pos - run_start  (armed exactly at the eve -> 1).
    CENSORED = the run reaches the first position of the 60-session window, so the true
    arming may predate what the window can see; reported as `>=60`, never as 60.
    """
    n, nf = len(ev), len(FKEYS)
    armed = np.zeros((n, nf), dtype=bool)
    lead = np.zeros((n, nf), dtype=np.int32)
    cens = np.zeros((n, nf), dtype=bool)
    if n == 0:
        return armed, lead, cens

    idx_map = panel.groupby("ticker", sort=True).indices
    cols = {k: panel[k].to_numpy(bool) for k in FKEYS}
    ev_by_ticker = ev.groupby("ticker", sort=True).indices
    evt_pos_all = ev["evt_pos"].to_numpy()

    for t in sorted(ev_by_ticker):
        rows = np.sort(ev_by_ticker[t])
        gi = np.sort(idx_map[t])
        e = evt_pos_all[rows]
        eve = e - 1
        for j, k in enumerate(FKEYS):
            f = cols[k][gi]
            st = w1.streak_lengths(f)
            on = f[eve]
            s = eve - st[eve] + 1
            armed[rows, j] = on
            lead[rows, j] = np.where(on, e - s, 0)
            cens[rows, j] = on & (s <= (e - ARMING_LOOKBACK))
    return armed, lead, cens


def arming_frame(ev: pd.DataFrame, armed, lead, cens) -> pd.DataFrame:
    """Tidy long frame over ARMING-ELIGIBLE COHORT events only."""
    keep = np.flatnonzero(ev["in_cohort"].to_numpy() & ev["arming_eligible"].to_numpy())
    n = keep.size
    reps = len(FKEYS)
    out = pd.DataFrame({
        "event_id": np.repeat(keep, reps),
        "ticker": np.repeat(ev["ticker"].to_numpy()[keep], reps),
        "board_key": np.repeat(ev["board_key"].to_numpy()[keep], reps),
        "era": np.repeat(ev["era"].to_numpy()[keep], reps),
        "dd_band": np.repeat(ev["dd_band"].astype(str).to_numpy()[keep], reps),
        "event_date": np.repeat(ev["event_date"].to_numpy()[keep], reps),
        "footprint": np.tile(np.array(FKEYS, dtype=object), n),
        "armed": armed[keep].reshape(-1),
        "lead": lead[keep].reshape(-1),
        "censored": cens[keep].reshape(-1),
    })
    return out


# ── stage 4 — aggregation helpers ─────────────────────────────────────────────


def honest_n(frame: pd.DataFrame, date_col="event_date") -> dict:
    return {"events": int(len(frame)),
            "names": int(frame["ticker"].nunique()) if len(frame) else 0,
            "sessions": int(pd.Series(frame[date_col]).nunique()) if len(frame) else 0}


def censored_quantiles(leads: np.ndarray, censored: np.ndarray) -> dict:
    """Nearest-rank quantiles with the censored block sorted to the TOP.

    Every uncensored lead is <= ARMING_LOOKBACK - 1 and every censored one is
    >= ARMING_LOOKBACK, so the censored observations ARE the top of the order and a
    quantile landing inside them is honestly `>=60` rather than an imputed number.
    """
    n = int(leads.size)
    if n == 0:
        return {"q1": None, "median": None, "q3": None, "n_armed": 0,
                "n_censored": 0, "censored_pct": None}
    unc = np.sort(leads[~censored])
    n_c = int(n - unc.size)
    out = {}
    for name, q in (("q1", 0.25), ("median", 0.5), ("q3", 0.75)):
        i = max(0, math.ceil(q * n) - 1)
        out[name] = (int(unc[i]) if i < unc.size else f">={ARMING_LOOKBACK}")
    out["n_armed"] = n
    out["n_censored"] = n_c
    out["censored_pct"] = _r(100.0 * n_c / n, 2)
    return out


def _fmt_q(v):
    """Writeup rendering only. The JSON keeps the machine-readable `>=60` string."""
    if v is None:
        return "—"
    return f"≥{ARMING_LOOKBACK}" if isinstance(v, str) else f"{v}"


def lead_table(arm: pd.DataFrame, group_cols) -> "OrderedDict":
    """Lead-time distribution per footprint inside every group. Honest-N on every cell."""
    out: "OrderedDict[str, dict]" = OrderedDict()
    if not len(arm):
        return out
    for key, g in arm.groupby(group_cols, sort=True, observed=True):
        label = key if isinstance(key, str) else "|".join(str(x) for x in key)
        cell = OrderedDict()
        n_events = int(g["event_id"].nunique())
        n_names = int(g["ticker"].nunique())
        n_sess = int(pd.Series(g["event_date"]).nunique())
        for f in FKEYS:
            sub = g[g["footprint"] == f]
            a = sub[sub["armed"]]
            q = censored_quantiles(a["lead"].to_numpy(np.int64),
                                   a["censored"].to_numpy(bool))
            q["armed_pct"] = _r(100.0 * len(a) / max(len(sub), 1), 2)
            q["n_events_in_group"] = int(len(sub))
            cell[f] = q
        out[label] = {"honest_n": {"events": n_events, "names": n_names,
                                   "sessions": n_sess},
                      "footprints": cell}
    return out


def signature_of(armed_row, lead_row, cens_row, keys) -> str:
    """Arming-order signature over `keys`, censoring-aware.

    Censored footprints armed earlier than any uncensored one but their MUTUAL order is
    unknowable from the window, so they form a single leading tied group `{...}>=60`.
    Uncensored footprints follow in DESCENDING lead (earliest arming first); equal leads
    are a braced same-session group.  Names inside a group are sorted alphabetically so
    the signature is deterministic.
    """
    idx = {k: FKEYS.index(k) for k in keys}
    cens_grp = sorted(k for k in keys if armed_row[idx[k]] and cens_row[idx[k]])
    unc = [(int(lead_row[idx[k]]), k) for k in keys
           if armed_row[idx[k]] and not cens_row[idx[k]]]
    parts = []
    if cens_grp:
        body = ",".join(FSHORT[k] for k in cens_grp)
        parts.append(("{" + body + "}" if len(cens_grp) > 1 else body)
                     + f">={ARMING_LOOKBACK}")
    for ld in sorted({x[0] for x in unc}, reverse=True):
        grp = sorted(k for l, k in unc if l == ld)
        body = ",".join(FSHORT[k] for k in grp)
        parts.append(("{" + body + "}" if len(grp) > 1 else body) + f"({ld})")
    return " > ".join(parts) if parts else "(none armed)"


def order_signatures(ev: pd.DataFrame, armed, lead, cens, keys, group_cols):
    """Most frequent complete arming orders, per group, over events where ALL `keys` armed."""
    mask = ev["in_cohort"].to_numpy() & ev["arming_eligible"].to_numpy()
    kidx = [FKEYS.index(k) for k in keys]
    all_armed = armed[:, kidx].all(axis=1) & mask
    out: "OrderedDict[str, dict]" = OrderedDict()
    sub = ev[all_armed]
    if not len(sub):
        return out
    rows = np.flatnonzero(all_armed)
    sig = np.array([signature_of(armed[i], lead[i], cens[i], keys) for i in rows],
                   dtype=object)
    sub = sub.assign(_sig=sig)
    denom = ev[mask]
    for key, g in sub.groupby(group_cols, sort=True, observed=True):
        label = key if isinstance(key, str) else "|".join(str(x) for x in key)
        cnt = Counter(g["_sig"].tolist())
        d = denom
        for col, val in zip(([group_cols] if isinstance(group_cols, str) else group_cols),
                            ([key] if isinstance(key, str) else key)):
            d = d[d[col].astype(str) == str(val)]
        out[label] = {
            "events_all_keys_armed": int(len(g)),
            "events_in_group": int(len(d)),
            "share_all_keys_armed_pct": _r(100.0 * len(g) / max(len(d), 1), 2),
            "names": int(g["ticker"].nunique()),
            "sessions": int(pd.Series(g["event_date"]).nunique()),
            "distinct_signatures": int(len(cnt)),
            "top": [{"signature": s, "events": int(c),
                     "pct_of_all_armed": _r(100.0 * c / len(g), 2)}
                    for s, c in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
                    [:TOP_SIGNATURES]],
        }
    return out


def pairwise_precedence(ev: pd.DataFrame, armed, lead, cens, group_cols):
    """For every footprint pair: which armed first, among events where BOTH armed.

    Censoring: exactly one censored -> that one armed strictly earlier (RESOLVED); both
    censored -> UNRESOLVED (never a tie, never a coin flip); equal uncensored leads ->
    SAME-SESSION, excluded from the strict-precedence denominator which is printed.
    """
    mask = ev["in_cohort"].to_numpy() & ev["arming_eligible"].to_numpy()
    gvals = ev[list(group_cols)].astype(str).agg("|".join, axis=1).to_numpy() \
        if not isinstance(group_cols, str) else ev[group_cols].astype(str).to_numpy()
    out: "OrderedDict[str, dict]" = OrderedDict()
    for label in sorted(set(gvals[mask])):
        sel = mask & (gvals == label)
        rows = np.flatnonzero(sel)
        cell = OrderedDict()
        for ai in range(len(FKEYS)):
            for bi in range(ai + 1, len(FKEYS)):
                a, b = FKEYS[ai], FKEYS[bi]
                both = rows[armed[rows, ai] & armed[rows, bi]]
                if both.size == 0:
                    continue
                ca, cb = cens[both, ai], cens[both, bi]
                la, lb = lead[both, ai].astype(np.int64), lead[both, bi].astype(np.int64)
                unresolved = ca & cb
                a_first = (ca & ~cb) | (~ca & ~cb & (la > lb))
                b_first = (cb & ~ca) | (~ca & ~cb & (lb > la))
                same = (~ca & ~cb & (la == lb))
                strict = int(a_first.sum() + b_first.sum())
                cell[f"{a}|{b}"] = {
                    "n_both_armed": int(both.size),
                    "n_unresolved_both_censored": int(unresolved.sum()),
                    "n_same_session": int(same.sum()),
                    "n_a_first": int(a_first.sum()), "n_b_first": int(b_first.sum()),
                    "pct_a_before_b": _r(100.0 * a_first.sum() / strict, 2)
                    if strict else None,
                    "strict_denominator": strict,
                }
        out[label] = cell
    return out


def presence_tables(ev: pd.DataFrame, group_cols) -> "OrderedDict":
    """Footprint presence AT THE EVE — boolean shares plus every band distribution."""
    coh = ev[ev["in_cohort"].to_numpy()]
    out: "OrderedDict[str, dict]" = OrderedDict()
    if not len(coh):
        return out
    for key, g in coh.groupby(group_cols, sort=True, observed=True):
        label = key if isinstance(key, str) else "|".join(str(x) for x in key)
        shares = OrderedDict(
            (f, {"n_true": int(g[f].sum()),
                 "share_pct": _r(100.0 * float(g[f].mean()), 2)}) for f in FKEYS)
        bands = OrderedDict()
        for col in BAND_COLS:
            vc = g[col].astype(str).value_counts()
            bands[col] = OrderedDict(
                (str(k), {"n": int(v), "share_pct": _r(100.0 * v / len(g), 2)})
                for k, v in sorted(vc.items(), key=lambda kv: (-kv[1], str(kv[0]))))
        out[label] = {"honest_n": honest_n(g), "footprint_shares": shares,
                      "band_distributions": bands}
    return out


def cohort_tables(ev: pd.DataFrame) -> dict:
    """Cohort counts, plus the ONE-TIME out-of-cohort context count."""
    coh = ev[ev["in_cohort"].to_numpy()]
    ooc = ev[~ev["in_cohort"].to_numpy()]
    by_band = OrderedDict()
    for b in OUT_OF_COHORT_BANDS:
        g = ooc[ooc["dd_band"].astype(str) == b]
        by_band[b] = honest_n(g)
    per_board = OrderedDict()
    for bk in BOARD_ORDER:
        g = coh[coh["board_key"] == bk]
        cell = {"total": honest_n(g), "by_dd_band": OrderedDict(), "by_era": OrderedDict(),
                "arming_eligible": honest_n(g[g["arming_eligible"].to_numpy()]),
                "arming_ineligible_short_lookback": int(
                    (~g["arming_eligible"].to_numpy()).sum())}
        for b in COHORT_BANDS:
            cell["by_dd_band"][b] = honest_n(g[g["dd_band"].astype(str) == b])
        for era, ge in g.groupby("era", sort=True, observed=True):
            cell["by_era"][str(era)] = {
                **honest_n(ge),
                "by_dd_band": OrderedDict(
                    (b, int((ge["dd_band"].astype(str) == b).sum()))
                    for b in COHORT_BANDS)}
        per_board[bk] = cell
    return {
        "all_first_board_events": honest_n(ev),
        "in_cohort": honest_n(coh),
        "out_of_cohort_context_only": {
            "note": ("Reported ONCE as context. These events enter no other table in "
                     "this artifact: the cohort is the washout class, and a first board "
                     "printed from a shallower drawdown is a different physical object."),
            "total": honest_n(ooc), "by_band": by_band},
        "per_board": per_board,
        "board_pooling_law": ("boards are NEVER pooled; `chinext10` (pre 2020-08-24) and "
                              "`chinext20` (on/after) are two POPULATIONS and share no "
                              "cell with each other or with main / star"),
    }


# ── stage 5 — the worked example ──────────────────────────────────────────────


def worked_example(panel: pd.DataFrame, ev: pd.DataFrame, armed, lead, cens) -> dict:
    t, d = WORKED_EXAMPLE_TICKER, WORKED_EXAMPLE_BOARD_DATE
    hit = np.flatnonzero((ev["ticker"].to_numpy() == t)
                         & (ev["event_date"].to_numpy() == d.to_datetime64()))
    if hit.size == 0:
        return {"status": "NOT A COHORT EVENT IN THIS RUN",
                "ticker": t, "board_date": str(d.date()),
                "why": ("the event is absent from the extracted first-board set — this "
                        "is reported, never patched around")}
    i = int(hit[0])
    row = ev.iloc[i]
    tl = OrderedDict()
    gi = np.sort(panel.groupby("ticker", sort=True).indices[t])
    dates = panel["date"].to_numpy()[gi]
    e = int(row["evt_pos"])
    for j, k in enumerate(FKEYS):
        on = bool(armed[i, j])
        rec = {"at_eve": on, "armed": on,
               "lead_sessions": (f">={ARMING_LOOKBACK}" if (on and cens[i, j])
                                 else (int(lead[i, j]) if on else None)),
               "censored_at_lookback_edge": bool(cens[i, j]),
               "arming_session": None}
        if on and not cens[i, j]:
            rec["arming_session"] = str(pd.Timestamp(dates[e - int(lead[i, j])]).date())
        tl[k] = rec
    lo = max(0, e - WORKED_EXAMPLE_TAIL)
    tape = []
    for p in range(lo, e + 1):
        r = {"date": str(pd.Timestamp(dates[p]).date()),
             "is_eve": bool(p == e - 1), "is_board": bool(p == e)}
        for k in FKEYS:
            r[FSHORT[k]] = bool(panel[k].to_numpy()[gi[p]])
        tape.append(r)
    return {
        "status": "IN COHORT",
        "ticker": t, "board_date": str(d.date()),
        "eve_date": str(pd.Timestamp(row["eve_date"]).date()),
        "board_key": str(row["board_key"]), "era": str(row["era"]),
        "sector": str(row["sector"]),
        "eve_state": {
            "dd250": _r(row["dd250"]), "dd_band": str(row["dd_band"]),
            "dur_band": str(row["dur_band"]), "below_band": str(row["below_band"]),
            "sect35_band": str(row["sect35_band"]),
            "sect_deep35_pct": _r(row["sect_deep35_pct"], 2),
            "volz_band": str(row["volz_band"]),
        },
        "arming_timeline": tl,
        "core4_signature": signature_of(armed[i], lead[i], cens[i], CORE4),
        "full_signature": signature_of(armed[i], lead[i], cens[i], FKEYS),
        "footprint_tape_last_sessions": tape,
        "arming_eligible": bool(row["arming_eligible"]),
        "eve_to_event_calendar_days": int(row["eve_to_event_calendar_days"]),
        "claims_stamp": ("PIT / EVENT FACTS ONLY. No price level, no return, no "
                         "expectancy and no outcome magnitude is quoted for this case in "
                         "any form. The earlier case-study exhibit's price and return "
                         "claims remain withdrawn under their own stamp and no number "
                         "from it is cited here."),
    }


# ── stage 6 — verify battery (every check carries a mutation probe) ───────────


def _probe(fn, mutate, label):
    """Run `fn` on mutated input; the check is a defect unless the mutation is DETECTED."""
    try:
        passed, _ = fn(mutate())
    except Exception as exc:  # noqa: BLE001
        return {"mutation": label, "detected": True, "via": f"raised {type(exc).__name__}"}
    return {"mutation": label, "detected": (not passed), "via": "check returned failure"}


def _sub_panel(w1, tickers, mutate=None) -> pd.DataFrame:
    """A W-P0 panel restricted to `tickers`, optionally over mutated raw bars.

    Replicates `build_panel`'s own sequence (process_ticker -> sector map ->
    attach_conditioners) on a subset so the no-lookahead check can rebuild the whole
    pipeline — INCLUDING the cross-sectional sector-breadth footprint — cheaply. The
    sub-panel's breadth values differ from the full panel's by construction; the check
    asserts INVARIANCE under corruption, not equality with the full panel.
    """
    sector_map, _ = w1.load_sector_map()
    st_set, _ = w1.load_st_cohort()
    frames = []
    for t in tickers:
        if t in st_set:
            continue
        p = RAW_DIR / f"{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if mutate is not None:
            df = mutate(df)
        out, _ = w1.process_ticker(t, df, w1._board_from_ticker(t))
        if out is not None and len(out):
            frames.append(out)
    panel = pd.concat(frames, ignore_index=True)
    panel["sector"] = panel["ticker"].map(sector_map).fillna("UNKNOWN")
    panel, _ = w1.attach_conditioners(panel, None)
    panel = panel.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)
    return derive_footprints(panel)


def _eve_anchors(w1, sub: pd.DataFrame, cut: pd.Timestamp):
    """(ticker, eve_date) anchors of every cohort event whose EVE is at/before `cut`.

    The anchor set is fixed by the UNCORRUPTED panel on purpose.  What the no-lookahead
    check tests is the EVE-ANCHORED STATE — the footprints and the armings, which is
    exactly what this artifact reports — not whether the board itself still happened.  A
    corruption that starts after the eve necessarily rewrites the board bar, so
    re-extracting the event set from the corrupted panel would compare a different set of
    events and report a change that is the corruption doing its job, not a leak.  (That
    was this check's first-draft defect: it filtered on `eve_date <= cut` while letting
    the EVENT bar sit past the cut, and reported a single spurious change for the one
    anchor whose board bar the corruption had erased.)
    """
    ev = extract_events(sub, w1)
    if not len(ev):
        return []
    ev = ev[pd.DatetimeIndex(ev["eve_date"]) <= cut]
    return sorted({(str(t), pd.Timestamp(d))
                   for t, d in zip(ev["ticker"], ev["eve_date"])})


def _anchor_fingerprint(w1, sub: pd.DataFrame, anchors):
    """Armings recomputed AT FIXED (ticker, eve_date) anchors on whatever panel is given.

    `compute_armings` needs only `evt_pos`, and every quantity it derives is a function of
    `eve_pos = evt_pos - 1`, so an anchor can be evaluated without a board existing at
    that position in the panel being measured.  That is what makes the invariance
    comparison well-posed under a corruption that erases boards.
    """
    idx_map = sub.groupby("ticker", sort=True).indices
    dates_all = sub["date"].to_numpy()
    rows, missing = [], []
    for t, d in anchors:
        gi = idx_map.get(t)
        if gi is None:
            missing.append(f"{t}@{d.date()}")
            continue
        gi = np.sort(gi)
        dts = dates_all[gi]
        p = int(np.searchsorted(dts, d.to_datetime64(), "left"))
        if p >= gi.size or dts[p] != d.to_datetime64():
            missing.append(f"{t}@{d.date()}")
            continue
        rows.append((t, d, p))
    if not rows:
        return {}, missing
    fake = pd.DataFrame({"ticker": [r[0] for r in rows],
                         "evt_pos": np.array([r[2] + 1 for r in rows], dtype=np.int64)})
    armed, lead, cens = compute_armings(sub, fake, w1)
    fp = {}
    for i, (t, d, _p) in enumerate(rows):
        fp[f"{t}@{d.date()}"] = "|".join(
            f"{k}:{int(armed[i, j])}:{int(lead[i, j])}:{int(cens[i, j])}"
            for j, k in enumerate(FKEYS))
    return fp, missing


def verify_battery(w1, w1_sha, panel, ev, armed, lead, cens, arm, cohort,
                   presence, lead_tabs, order_tabs) -> dict:
    checks: "OrderedDict[str, dict]" = OrderedDict()
    ev_ticker = ev["ticker"].to_numpy()
    ev_date = ev["event_date"].to_numpy()

    # ── (a) NO LOOKAHEAD ──────────────────────────────────────────────────────
    # Corrupting bars strictly AFTER each event's eve must change ZERO armings and ZERO
    # footprints at/before the eve. The probe corrupts the PAST instead, which MUST move
    # them — that is what proves this check can see a failure (W-P0's L1734 pattern).
    sample = sorted(p.stem for p in sorted(RAW_DIR.glob("*.parquet"))[::28])[:64]
    CUTS = (pd.Timestamp("2015-01-05"), pd.Timestamp("2019-01-02"),
            pd.Timestamp("2022-01-04"))
    CUT = CUTS[-1]                       # the cut the PAST-slab probe runs against
    PAST_SLAB_START = pd.Timestamp("2020-01-02")
    base_sub = _sub_panel(w1, sample)

    def _mutator(after: bool, cut: pd.Timestamp = CUT):
        """Scale one contiguous price slab by 1.35 — after the cut, or inside the past.

        THE PROBE HAS TO MOVE A SCALE-INVARIANT SERIES.  Every footprint here is a RATIO
        (a drawdown, an MA cross, an RSI, a realised-vol rank), so scaling a name's WHOLE
        pre-cut history by a constant would leave all eight footprints bit-identical and
        the probe would read `not detected` for the wrong reason.  The past arm therefore
        scales a two-year SLAB inside the pre-cut history, which moves the return path
        across both of its edges and so moves the footprints themselves.  Both arms are
        the same operation — one contiguous slab, one factor — differing only in whether
        the slab lies after the eve or before it.
        """
        def _m(df):
            d = df.copy()
            sel = (d.index > cut) if after else \
                ((d.index > PAST_SLAB_START) & (d.index <= cut))
            d.loc[sel, ["open", "high", "low", "close"]] = \
                d.loc[sel, ["open", "high", "low", "close"]] * 1.35
            return d
        return _m

    def _one_cut(cut, direction):
        """Corrupt one slab, then re-read the EVE-ANCHORED state and the pre-cut cells."""
        anchors = _eve_anchors(w1, base_sub, cut)
        base_fp, _ = _anchor_fingerprint(w1, base_sub, anchors)
        base_pre = base_sub[base_sub["date"] <= cut][
            ["ticker", "date"] + list(FKEYS)].reset_index(drop=True)
        sub = _sub_panel(w1, sample, mutate=_mutator(after=(direction == "future"),
                                                     cut=cut))
        fp, missing = _anchor_fingerprint(w1, sub, anchors)
        pre = sub[sub["date"] <= cut][
            ["ticker", "date"] + list(FKEYS)].reset_index(drop=True)
        changed = sum(1 for k, v in base_fp.items() if fp.get(k) != v) + len(missing)
        if len(pre) == len(base_pre):
            foot = int(sum(int((base_pre[c].to_numpy() != pre[c].to_numpy()).sum())
                           for c in FKEYS))
        else:
            foot = -1                 # row-count divergence is itself a change
        # The STRICTEST witnesses: anchors whose eve is the LAST session at/before the
        # cut on their own axis, so the corruption starts the VERY NEXT session — the
        # literal "bars strictly after the eve" case.
        last_at_cut = 0
        idx_map = base_sub.groupby("ticker", sort=True).indices
        dts_all = base_sub["date"].to_numpy()
        for t, d in anchors:
            gi = np.sort(idx_map[t])
            dts = dts_all[gi]
            p = int(np.searchsorted(dts, d.to_datetime64(), "left"))
            if p + 1 >= gi.size or dts[p + 1] > cut.to_datetime64():
                last_at_cut += 1
        return {"cut": str(cut.date()), "anchors": len(anchors),
                "anchors_missing_after_corruption": len(missing),
                "armings_changed": changed, "pre_cut_footprint_cells_changed": foot,
                "pre_cut_rows_compared": int(len(base_pre)),
                "anchors_with_corruption_starting_the_next_session": last_at_cut}

    def _nolook(direction):
        per_cut = [_one_cut(c, direction) for c in
                   (CUTS if direction == "future" else (CUT,))]
        bad = sum(1 for r in per_cut
                  if r["armings_changed"] or r["pre_cut_footprint_cells_changed"])
        return (bad == 0), {
            "direction_corrupted": direction,
            "cuts": [str(c.date()) for c in CUTS] if direction == "future"
            else [str(CUT.date())],
            "past_slab": [str(PAST_SLAB_START.date()), str(CUT.date())],
            "prices_scaled_by": 1.35, "tickers_sampled": len(sample),
            "per_cut": per_cut, "cuts_with_any_change": bad,
            "why": ("every footprint and every arming is read AT THE EVE, so no bar after "
                    "the cut may move one. Run at three cuts spanning the history so each "
                    "anchor is tested against corruption of the entire tape after it; the "
                    "`anchors_with_corruption_starting_the_next_session` column counts the "
                    "anchors for which the corruption begins on the very next session, "
                    "which is the literal 'strictly after the eve' case."),
        }
    ok, det = _nolook("future")
    checks["no_lookahead_armings_and_footprints"] = {
        "why": ("gate 2(a) — the whole decomposition is read at the eve, so a bar strictly "
                "after the eve must not move a single footprint or arming"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(_nolook, lambda: "past",
                                 "scale a two-year slab INSIDE the pre-cut history "
                                 "instead of the post-cut tail (must move the armings "
                                 "and the pre-cut footprints)"),
    }

    # ── (b) COLD-WINDOW PROBE ─────────────────────────────────────────────────
    # Planting a tolerant board INSIDE a cohort event's prior 20 sessions must EJECT the
    # event. The probe plants the same board OUTSIDE that window, where it must NOT eject
    # — proving the check is keyed to the cold window itself and not to "any mutation".
    coh_ev = ev[ev["in_cohort"].to_numpy()]
    probe_t = probe_d = None
    if len(coh_ev):
        cand = coh_ev[coh_ev["evt_pos"].to_numpy() >= 120]
        cand = cand if len(cand) else coh_ev
        cand = cand.sort_values(["ticker", "event_date"], kind="mergesort")
        probe_t = str(cand["ticker"].iloc[0])
        probe_d = pd.Timestamp(cand["event_date"].iloc[0])

    def _plant(offset_sessions):
        """Plant a tolerant board `offset_sessions` before the event; return ejection.

        The plant touches ONE bar's close/high (and forces positive volume so the bar is
        LIVE by W-P0's own law). Changing close[p] moves only bar p+1's prev-close, so the
        cascade is one bar wide and never reaches the event bar itself at either offset.
        """
        raw = pd.read_parquet(RAW_DIR / f"{probe_t}.parquet").sort_index()
        board = w1._board_from_ticker(probe_t)
        pos = int(pd.DatetimeIndex(raw.index).searchsorted(probe_d, "left"))
        p = pos - offset_sessions
        d = raw.copy()
        w = float(w1.limit_width_for_date(board, pd.Timestamp(raw.index[p])))
        prev = float(d["close"].iloc[p - 1])
        lim = round(prev * (1.0 + w), 2)
        d.iloc[p, d.columns.get_loc("close")] = lim
        d.iloc[p, d.columns.get_loc("high")] = max(lim, float(d["high"].iloc[p]))
        d.iloc[p, d.columns.get_loc("volume")] = max(1.0, float(d["volume"].iloc[p]))
        out, _ = w1.process_ticker(probe_t, d, board)
        out["sector"] = "PROBE"
        out2, _ = w1.attach_conditioners(out, None)
        out2 = derive_footprints(out2.sort_values(["ticker", "date"], kind="mergesort")
                                 .reset_index(drop=True))
        ev2 = extract_events(out2, w1)
        still = bool(len(ev2) and (pd.DatetimeIndex(ev2["event_date"])
                                   == probe_d).any())
        return still, {"planted_offset_sessions": offset_sessions,
                       "event_still_in_first_board_set": still}

    def _cold(offset):
        if probe_t is None:
            return False, {"status": "no cohort event available to probe"}
        still, d = _plant(offset)
        d.update({"probe_ticker": probe_t, "probe_event_date": str(probe_d.date()),
                  "cold_lookback_K": int(w1.COLD_LOOKBACK_K),
                  "rule": ("a board planted INSIDE the prior-20 window must eject the "
                           "event; one planted OUTSIDE it must not")})
        return (not still), d
    ok, det = _cold(5)
    checks["cold_window_ejects_a_planted_board"] = {
        "why": ("gate 2(b) — the cohort's coldness must be enforced by the prior-20 "
                "window, not merely asserted by it"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _cold, lambda: 25,
            "plant the same board 25 sessions back — OUTSIDE the prior-20 window, where "
            "the event must survive (so the check returns failure)"),
    }

    # ── (c) DETECTOR RECALL vs the vendor pool, where coverage overlaps ────────
    zt = pd.read_parquet(ZT_P, columns=["ticker", "date"])
    zt["date"] = pd.to_datetime(zt["date"])
    shared = sorted(set(zt["date"].unique()) & set(panel["date"].unique()))
    P = panel[panel["date"].isin(shared)]
    Z = zt[zt["date"].isin(shared)]
    univ = set(zip(P["ticker"], P["date"]))
    zin = set(zip(Z["ticker"], Z["date"])) & univ

    def _det(lu_flags):
        det_set = set(zip(P["ticker"][lu_flags], P["date"][lu_flags]))
        agree_ = zin & det_set
        miss_ = zin - det_set
        recall = (len(agree_) / len(zin)) if zin else 0.0
        return (recall >= 0.99), {
            "shared_dates": len(shared), "zt_rows_on_shared_dates": int(len(Z)),
            "zt_pairs_inside_footprint_universe": len(zin),
            "detector_boards_on_shared_dates": int(len(det_set)),
            "agree": len(agree_), "zt_only_detector_missed": len(miss_),
            "recall_pct": _r(100.0 * recall, 2),
            "missed_episodes": sorted(f"{t} @ {str(pd.Timestamp(d).date())}"
                                      for t, d in miss_)[:40],
        }
    lu_real = P["lu"].to_numpy(bool)
    ok, det = _det(lu_real)
    det["detector_only_not_in_zt"] = len(
        set(zip(P["ticker"][lu_real], P["date"][lu_real])) - zin)
    det["note"] = ("RECALL-ONLY BY CONSTRUCTION. `china_zt_pool` is a PARTIAL vendor "
                   "store, so this measures the tolerant detector's recall on the pool's "
                   "OWN rows and is NOT a precision test — a detector board absent from "
                   "the pool is not evidence of a false positive.")

    def _mutate_detector():
        f = lu_real.copy()
        on = np.flatnonzero(f)
        f[on[:max(1, on.size // 20)]] = False
        return f
    checks["detector_vs_zt_pool"] = {
        "why": "gate 2(c) — cross-check the tolerant detector where coverage overlaps",
        "passed": ok, "detail": det,
        "mutation_probe": _probe(_det, _mutate_detector,
                                 "switch off 5% of the detector's board flags"),
    }

    # ── (d) dd-BAND PARTITION COMPLETENESS ────────────────────────────────────
    def _partition(bands: np.ndarray):
        labels = np.asarray(bands, dtype=object)
        known = set(COHORT_BANDS) | set(OUT_OF_COHORT_BANDS)
        unknown = sorted({str(x) for x in labels} - known)
        counts = {b: int((labels == b).sum()) for b in sorted(known)}
        total = int(labels.size)
        summed = int(sum(counts.values()))
        coh_n = int(sum(counts[b] for b in COHORT_BANDS))
        return (not unknown and summed == total), {
            "events_total": total, "band_counts": counts, "counts_sum": summed,
            "unknown_band_labels": unknown,
            "cohort_events": coh_n,
            "out_of_cohort_events": total - coh_n,
            "rule": ("every first-board event carries EXACTLY ONE W-P0 dd band; the "
                     "cohort is the disjoint union of d1/d2/d3 and the out-of-cohort "
                     "context is the disjoint union of d0 and na"),
        }
    ok, det = _partition(ev["dd_band"].astype(str).to_numpy())
    checks["dd_band_partition_complete"] = {
        "why": ("gate 2(d) — a cohort partition that silently drops or double-counts an "
                "event would make every share in this file wrong"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _partition,
            lambda: np.append(ev["dd_band"].astype(str).to_numpy(), "d9_invented_band"),
            "append an event carrying a band label outside the W-P0 registry"),
    }

    # ── (e) ERA / BOARD TABLE DISJOINTNESS ────────────────────────────────────
    def _disjoint(tables):
        bad = {}
        for name, keys in tables.items():
            ks = [str(k) for k in keys]
            if sorted(ks) != sorted(set(ks)):
                bad[name] = "duplicate group key"
            boards = {k.split("|")[0] for k in ks}
            extra = sorted(boards - set(BOARD_ORDER))
            if extra:
                bad[name] = f"non-board key(s): {extra}"
        coh = ev[ev["in_cohort"].to_numpy()]
        by_board = {b: int((coh["board_key"] == b).sum()) for b in BOARD_ORDER}
        if sum(by_board.values()) != len(coh):
            bad["board_partition"] = "per-board counts do not sum to the cohort total"
        by_era = {}
        for b in BOARD_ORDER:
            g = coh[coh["board_key"] == b]
            s = int(sum(int((g["era"] == e).sum())
                        for e in sorted(pd.unique(coh["era"]))))
            by_era[b] = s
            if s != len(g):
                bad[f"era_partition_{b}"] = "per-era counts do not sum to the board total"
        return (not bad), {"violations": bad, "cohort_by_board": by_board,
                           "era_sums_by_board": by_era,
                           "cohort_events": int(len(coh)),
                           "rule": ("boards are never pooled and no table may carry a "
                                    "pooled key; every era partition must sum to its "
                                    "own board's total")}
    tabs = {"lead_time_by_board_band": list(lead_tabs["by_board_band"]),
            "lead_time_by_board_era": list(lead_tabs["by_board_era"]),
            "order_core4_by_board": list(order_tabs["core4"]["by_board"]),
            "order_core4_by_board_band": list(order_tabs["core4"]["by_board_band"]),
            "pairwise_by_board_band": list(order_tabs["pairwise"]["by_board_band"]),
            "presence_by_board_band": list(presence["by_board_band"])}
    ok, det = _disjoint(tabs)
    checks["era_board_table_disjointness"] = {
        "why": ("gate 2(e) — the target-class law: main / chinext10 / chinext20 / star "
                "are four populations and may share no cell, and era tables must "
                "partition their own board"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _disjoint,
            lambda: {**tabs, "lead_time_by_board_band":
                     list(lead_tabs["by_board_band"]) + ["ALL_BOARDS|d1_m20_m35"]},
            "add a pooled 'ALL_BOARDS' key to an output table"),
    }

    # ── (f) THE ARMING DEFINITION ITSELF ──────────────────────────────────────
    # An oscillating series must arm at the START OF ITS FINAL TRUE-RUN, not at its first.
    def _arming_of(f: np.ndarray, e: int):
        st = w1.streak_lengths(np.asarray(f, dtype=bool))
        eve = e - 1
        if not f[eve]:
            return None, False
        s = eve - int(st[eve]) + 1
        return (e - s), bool(s <= e - ARMING_LOOKBACK)

    T, F = True, False
    OSC = np.array([T] * 4 + [F] + [T] * 3 + [F, F] + [T] * 6, dtype=bool)   # n=16
    OSC = np.concatenate([np.zeros(60, dtype=bool), OSC])                     # e = 76
    CASES_TRUE = [
        # (label, series, event_pos, expected_lead, expected_censored)
        ("oscillator_final_run_not_first", OSC, 76, 6, False),
        ("armed_exactly_at_the_eve", np.array([F] * 75 + [T]), 76, 1, False),
        ("false_at_the_eve_is_not_armed", np.array([T] * 70 + [F] * 6), 76, None, False),
        ("run_reaching_the_window_edge_is_censored",
         np.array([F] * 10 + [T] * 66), 76, 66, True),
    ]

    def _arming_check(cases):
        bad, seen = [], []
        for label, series, e, exp_lead, exp_cens in cases:
            got_lead, got_cens = _arming_of(np.asarray(series, dtype=bool), e)
            rec = {"case": label, "expected_lead": exp_lead, "got_lead": got_lead,
                   "expected_censored": exp_cens, "got_censored": got_cens}
            seen.append(rec)
            if got_lead != exp_lead or bool(got_cens) != bool(exp_cens):
                bad.append(rec)
        return (not bad), {
            "cases": seen, "failures": bad,
            "definition": ("arming = start of the FINAL true-run ending at the eve; "
                           "lead = event_pos - run_start; censored when the run reaches "
                           f"the first position of the {ARMING_LOOKBACK}-session window"),
            "why_the_oscillator_matters": (
                "the oscillator's FIRST true-run starts at position 60 (lead 16) and its "
                "FINAL true-run starts at position 70 (lead 6). An implementation that "
                "returned the first run would report 16 and this check would fail."),
        }
    ok, det = _arming_check(CASES_TRUE)
    checks["arming_is_final_true_run"] = {
        "why": ("gate 2(f) — the arming rule is the whole instrument; an oscillating "
                "footprint must arm at the start of its LAST run, not its first"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _arming_check,
            lambda: [("oscillator_asserted_at_FIRST_run", OSC, 76, 16, False)],
            "assert the FIRST-true-run answer (lead 16) for the oscillator — the "
            "naive/wrong semantics, which the check must reject"),
    }

    # ── (g) the pin resolves — every cited W-P0 line still holds its symbol ────
    w1_lines = W1_PATH.read_text().splitlines()

    def _pin(symbols):
        bad = {}
        for name, (ln, needle) in symbols.items():
            line = w1_lines[ln - 1] if 0 < ln <= len(w1_lines) else ""
            if needle not in line:
                bad[name] = {"expected_line": ln, "needle": needle,
                             "found": line.strip()[:80]}
        return (not bad), {"symbols_pinned": len(symbols), "unresolved": bad,
                           "w1_line_count": len(w1_lines)}
    ok, det = _pin(PIN_SYMBOLS)
    checks["pin_line_numbers_resolve"] = {
        "why": ("gate 1 — the pin must name REAL source lines. A W-P0 edit that shifts "
                "them would otherwise rot this module's pin comment silently"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _pin, lambda: {**PIN_SYMBOLS,
                           "build_panel": (PIN_SYMBOLS["build_panel"][0] + 5,
                                           PIN_SYMBOLS["build_panel"][1])},
            "shift a pinned line number by +5 (simulates a W-P0 edit above it)"),
    }

    # ── (h) STOP-SHIP reference scan (main() re-runs it over the emitted prose) ─
    self_src = Path(__file__).read_text()
    scan_targets = {"pb_case_decomposition.py": self_src}
    ok, det = stop_ship_scan(scan_targets)
    checks["stop_ship_reference_scan"] = {
        "why": ("gate 4 — DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT; zero references to "
                "withdrawn artifacts, grep-verified in the receipt"),
        "passed": ok, "detail": det,
        "ruling_cited": "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT",
        "mutation_probe": _probe(
            stop_ship_scan,
            lambda: {**scan_targets,
                     "synthetic": f"this sentence cites {WITHDRAWN_TOKENS[6]} table 3"},
            "introduce a withdrawn-artifact reference into a scanned surface"),
    }

    n_pass = sum(1 for c in checks.values() if c["passed"])
    n_probe = sum(1 for c in checks.values() if c["mutation_probe"]["detected"])
    return {
        "checks": checks,
        "summary": {"checks_run": len(checks), "checks_passed": n_pass,
                    "mutation_probes_detected": n_probe,
                    "all_passed": n_pass == len(checks),
                    "all_probes_detected": n_probe == len(checks)},
        "doctrine": ("A check that cannot fail is a defect. Every check above is paired "
                     "with a mutation that it MUST detect; `detected: false` anywhere "
                     "means the check is vacuous and the run is not evidence."),
    }


# ── stage 7 — receipts ────────────────────────────────────────────────────────


def build_vintage(w1_sha: str) -> dict:
    v = OrderedDict([
        ("base_sha", _git("merge-base", "HEAD", "origin/main")),
        ("build_head_sha", _git("rev-parse", "HEAD")),
        ("raw_store_commit", _git("log", "-1", "--format=%H", "--",
                                  "data/china_stocks_raw")),
        ("members_commit", _git("log", "-1", "--format=%H", "--",
                                "data/china_search/members.parquet")),
        ("st_snapshot_commit", _git("log", "-1", "--format=%H", "--",
                                    "data/china_st/st_snapshot.parquet")),
        ("zt_pool_commit", _git("log", "-1", "--format=%H", "--",
                                "data/china_zt_pool/pool.parquet")),
        ("w1_pin_commit", _git("log", "-1", "--format=%H", "--",
                               "research/cn_prophet_audit/washout_onset_w1.py")),
        ("w1_sha256", w1_sha),
    ])
    # SHALLOW-CLONE HAZARD, disclosed rather than papered over. In a shallow checkout
    # `git log -1 -- <path>` cannot walk past the graft, so a path untouched inside the
    # visible history resolves to the GRAFT COMMIT — a stamp that reads like provenance
    # and is not. Any stamp equal to a graft is relabelled, and the fact is stamped.
    graft = set()
    gd = Path(_git("rev-parse", "--git-common-dir"))
    gf = gd if gd.is_absolute() else (REPO / gd)
    sp = gf / "shallow"
    if sp.exists():
        graft = {ln.strip() for ln in sp.read_text().splitlines() if ln.strip()}
    v["repo_is_shallow"] = bool(graft)
    v["shallow_graft_commits"] = sorted(graft)
    hit = sorted(k for k, val in v.items()
                 if isinstance(val, str) and val in graft)
    for k in hit:
        v[k] = f"SHALLOW_BOUNDARY_UNRESOLVED({v[k]})"
    v["stamps_unresolved_by_shallow_graft"] = hit
    v["determinism"] = ("no wall-clock, runtime or hostname enters either receipt; the "
                        "artifact date is a frozen constant. Two consecutive TZ=UTC runs "
                        "at the same commit are byte-identical.")
    return v


AMENDMENTS = [
    {"id": "A1",
     "what": "The EVE is the name's previous PANEL session, not its previous calendar "
             "session, and the eve->event pair must sit inside W-P0's own "
             "MAX_STEP_GAP_DAYS = 21 step rule.",
     "why": "china_stocks_raw encodes suspensions as zero-volume stale-price placeholder "
            "rows, which W-P0's live-bar law already excludes from the panel. Without "
            "the step rule a name resuming after a long suspension would be credited "
            "with an 'eve' from before the halt — a state read months before the board "
            "and presented as the day before it.",
     "risk_controlled_by": "the step rule is W-P0's OWN pre-registered constant (L354), "
                           "not a new one; `eve_to_event_calendar_days` is carried on "
                           "every event and its distribution is in the JSON."},
    {"id": "A2",
     "what": "Events with fewer than ARMING_LOOKBACK = 60 prior sessions on their own "
             "axis are EXCLUDED from the arming and order tables (they remain in the "
             "cohort and presence tables), and the exclusion count is printed.",
     "why": "A shorter window produces a censoring bound BELOW 60, which would break the "
            "ordering assumption the censored quantile rule rests on (every censored "
            "lead >= every uncensored one). Mixing those events in would make a median "
            "silently wrong rather than visibly censored.",
     "risk_controlled_by": "`arming_ineligible_short_lookback` is printed per board in "
                           "the cohort tables; the arming tables carry their own "
                           "honest-N, which is the eligible subset."},
    {"id": "A3",
     "what": "The 'complete order' tables run on the pre-registered CORE-4 "
             "(dd_le_m20, under_ma200, confluence_long, sector_deep35_ge40); the full "
             "8-footprint signature counts are emitted to the JSON only.",
     "why": "An 8-way signature over a censoring-aware alphabet is sparse enough that "
            "nearly every event is its own singleton — a list, not a pattern. The CORE-4 "
            "is the operator's own named footprint families (program home sec.1) and was "
            "fixed in the pre-registration block before any signature was counted.",
     "risk_controlled_by": "both are computed and both are in the receipt; the writeup "
                           "states which one each table is on, and the full-8 counts are "
                           "one key away in the JSON."},
    {"id": "A4",
     "what": "Chips (W-P0 S5b winner / trajectory) join skipped — attach_conditioners is "
             "called with chips=None.",
     "why": "The P-B footprint list is washout / basing / confluence / sector / quiet-"
            "base / volume. S5b is none of those and its store begins long after most of "
            "the cohort, so joining it would add a column that is null for 14 of 15 "
            "years.",
     "risk_controlled_by": "W-P0's own None branch sets the S5b bands to 'na'; no S5b "
                           "column appears in any table here."},
    {"id": "A5",
     "what": "Vintage stamps that resolve to a SHALLOW-CLONE GRAFT commit are relabelled "
             "`SHALLOW_BOUNDARY_UNRESOLVED(<sha>)` rather than printed as provenance.",
     "why": "In a shallow checkout `git log -1 -- <path>` stops at the graft, so a path "
            "untouched inside the visible history resolves to the graft commit. That "
            "reads exactly like a real store vintage and is not one. This run was "
            "deepened until the stamps resolved; the guard exists so a future shallow "
            "run cannot emit a confident wrong stamp.",
     "risk_controlled_by": "`vintage.repo_is_shallow`, `vintage.shallow_graft_commits` "
                           "and `vintage.stamps_unresolved_by_shallow_graft` are all in "
                           "the receipt, and a bare `::warning` is emitted on any hit."},
]

ORE_LEDGER = [
    "THE COMPARISON ARM. The single most valuable follow-up and deliberately NOT built "
    "here: a matched non-winner cohort (names in the same dd band, same board, same "
    "session, that did NOT print a board) decomposed the same way. That is an "
    "INFERENTIAL study and it needs a PREREGISTRATION — matched-control construction, "
    "era-preserving null, date-clustered inference, and the volatility-matched control "
    "W-P0 already had to add. Reading a precedence rate here as evidence of selection "
    "would be exactly the error that preregistration exists to prevent.",
    "ARMING ON THE BANDED FORMS. Only the eight BOOLEAN footprints have armings; a band "
    "transition (say b2_21_60 -> b3_61_120) is also an arming-like event and is not "
    "measured. Cheap to add once the boolean anatomy is read.",
    "INTRADAY / CHIP FOOTPRINTS remain P-C: auction demand, seal-time structure and "
    "chip-concentration shifts cannot arm in this instrument because the histories do "
    "not exist in this checkout.",
    "SUSPENSION-AWARE CONFLUENCE. W-P0 replicates production's close-only, volume-blind "
    "indicator input, so suspension placeholder closes enter the 3D session grouping. "
    "The suspension-aware variant is W-P0's own logged ore and is inherited unchanged.",
    "LEAD-TIME BEYOND 60 SESSIONS. The censored block is a floor, not a distribution. A "
    "longer lookback would resolve the slow footprints' true arming ages; 60 was fixed "
    "in the pre-registration and is not re-shopped after seeing the censoring rate.",
]

DOES_NOT_ESTABLISH = [
    "NO COMPARISON ARM, therefore NO selection skill and NO predictive claim. Every "
    "number in this file is computed on WINNERS — names that did print a first board. "
    "There is no matched non-winner cohort, no market baseline, no random draw. A "
    "footprint present in 90% of winners may be present in 90% of everything; this "
    "artifact cannot tell you which, and does not try. The comparison arm is ore, "
    "reserved for a preregistered study.",
    "NO lift, no t-statistic, no interval, no p-value, no effect size. None is computed "
    "and none may be inferred by dividing two numbers in this file.",
    "NO CAUSALITY, in either direction. That a footprint armed before a board is a "
    "statement about the order of two observations on the same tape. It is not evidence "
    "that the footprint produced the board, that the board was produced by anything "
    "measured here, or that either would recur.",
    "ARMING-ORDER STATISTICS ARE DESCRIPTIVE OF WINNERS ONLY. A precedence rate of X% "
    "means: among winners where both footprints were armed, one armed first X% of the "
    "time. It is not a conditional probability of a board and cannot be read as one.",
    "CENSORED LEADS ARE A FLOOR, NOT A VALUE. `>=60` (rendered `≥60` in the writeup) "
    "means the footprint was already "
    "true throughout the whole lookback window. The true arming age is unknown and is "
    "never imputed; a footprint with a high censoring rate has an UNMEASURED lead-time "
    "distribution, not a long one.",
    "SURVIVORS ONLY, LARGE-CAP SLICE. The footprint plane is W-P0's curated survivor "
    "universe; delisted names are absent, so every event here is an event on a name that "
    "lived. Nothing supports a claim about small caps in either direction.",
    "BACK-ADJUSTED BASIS. The tolerant detector runs on back-adjusted bars, so the "
    "cohort is a tolerant-detector cohort and not an exchange-exact legal-limit cohort. "
    "The residual is measured in verify.detector_vs_zt_pool, not assumed away. The "
    "reopen path to authority-tier limit work is unchanged and this artifact makes no "
    "claim to be on it (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT).",
    "NOTHING ABOUT THE WITHDRAWN W1-W3 CONSTRUCTIONS. No number and no artifact from "
    "them is cited (grep-verified in verify.stop_ship_reference_scan).",
    "NO PRICE OR RETURN CLAIM for any named episode, including the worked example. What "
    "is printed for a case is its footprint state and its event dates; the earlier case "
    "exhibit's price and return claims remain withdrawn under their own stamp.",
    "CURRENT SECTOR MEMBERSHIP. The sector-washout footprint applies today's sector map "
    "to 15 years of history (W-P0's own caveat); it is not a point-in-time sector "
    "statistic and eras are not comparable on it without that qualifier.",
]


# ── stage 8 — the writeup ─────────────────────────────────────────────────────


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(out)


def _hn(h) -> str:
    return f"{h['events']} ev / {h['names']} names / {h['sessions']} sess"


def build_md(p: dict) -> str:
    L = []
    A = L.append
    coh = p["cohort"]
    A(f"# P-B — case decomposition of the 300363-class first-board winners "
      f"({p['artifact_date']})")
    A("")
    A(f"Authority: `{p['authority']}`. Tier: {p['tier']}.")
    A("")
    A("**Winners only. There is no comparison arm.** Every count, order and distribution "
      "below describes names that DID print a first limit board out of a washout state. "
      "No lift, no t-statistic, no interval and no selection-skill claim appears anywhere "
      "in this artifact — the matched non-winner study is ore (§9) and needs its own "
      "preregistration.")
    A("")
    A(f"Governing ruling: `{p['governing_ruling']}`. Program home: "
      "`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md` §3 (the P-B row). "
      "Pinned definitions: `washout_onset_w1.py` (W-P0), **imported — not re-derived**.")
    A("")
    A("---")
    A("")

    # §1
    A("## 1. What was read, and how the cohort is built")
    A("")
    pm = p["footprint_plane"]
    A(f"One store: `data/china_stocks_raw`, through W-P0's own `build_panel()` over "
      f"W-P0's own window **{pm['window'][0]} → {pm['window'][1]}** — "
      f"{pm['panel_rows']:,} live bars, {pm['panel_names']:,} names, "
      f"{pm['panel_sessions']:,} sessions. No embedded outcome column is read anywhere; "
      "the tolerant detector and the cold rule are W-P0's, reached by import.")
    A("")
    A("A cohort **event** is a tolerant limit-up close whose **eve** — the name's "
      "previous panel session — was **cold** (no tolerant board in the prior 20 "
      "sessions). Every state in this file is read at the eve, so nothing is measured on "
      "the board bar itself. The eve→event pair must sit inside W-P0's own 21-day "
      "closure-tolerant step rule (§8 A1).")
    A("")
    A(f"**Honest-N, whole run.** {_hn(coh['all_first_board_events'])} first-board events; "
      f"**{_hn(coh['in_cohort'])} in cohort** (dd250 ≤ −20% at the eve).")
    A("")
    ooc = coh["out_of_cohort_context_only"]
    A(f"**Out of cohort, reported once as context and used nowhere else:** "
      f"{_hn(ooc['total'])} — of which "
      + ", ".join(f"`{b}` {ooc['by_band'][b]['events']} ev" for b in OUT_OF_COHORT_BANDS)
      + " (`d0_gt_m20` = the drawdown was shallower than −20%; `na` = W-P0's 250-session "
        "high was not yet measurable, fewer than 200 bars of history). A first board "
        "printed from a shallower drawdown is a different physical object and is not "
        "folded in; an unmeasurable one is not silently treated as shallow.")
    A("")

    # §2
    A("## 2. Cohort — boards never pooled, eras never averaged")
    A("")
    A("`chinext10` (SZ 300x/301x **before** 2020-08-24) and `chinext20` (on/after) are "
      "two populations, and neither shares a cell with `main` or `star`.")
    A("")
    rows = []
    for b in BOARD_ORDER:
        c = coh["per_board"][b]
        rows.append([f"`{b}`", _hn(c["total"])]
                    + [c["by_dd_band"][x]["events"] for x in COHORT_BANDS]
                    + [_hn(c["arming_eligible"]),
                       c["arming_ineligible_short_lookback"]])
    A(md_table(["board", "cohort honest-N", "d1 (−20..−35]", "d2 (−35..−50]", "d3 (≤−50)",
                "arming-eligible honest-N", "excluded: <60 sess lookback"], rows))
    A("")
    A("_Arming-eligible = at least 60 prior sessions on the name's own axis (§8 A2). "
      "Excluded events stay in the cohort and presence tables._")
    A("")
    A("### Per era (W-P0's own era boundaries, keyed on the event year)")
    A("")
    eras = sorted({e for b in BOARD_ORDER for e in coh["per_board"][b]["by_era"]})
    rows = []
    for b in BOARD_ORDER:
        c = coh["per_board"][b]["by_era"]
        rows.append([f"`{b}`"] + [
            (f"{c[e]['events']} / {c[e]['names']}n" if e in c else "—") for e in eras])
    A(md_table(["board"] + [e.replace("_", " ") for e in eras], rows))
    A("")
    A("_Cells are `events / distinct names`. An empty cell is a board that did not exist "
      "in that era (chinext20 begins 2020-08-24), not a zero._")
    A("")

    # §3
    A("## 3. Footprint presence at the eve")
    A("")
    A("Share of cohort events whose footprint was TRUE on the eve. These are presence "
      "shares among winners — they are not conditional board probabilities and cannot be "
      "read as any. **Two columns are true by construction and are not findings:** DD20 "
      "is 100% everywhere because the cohort IS the dd250 ≤ −20% class, and DD35 is 0% "
      "in `d1` and 100% in `d2`/`d3` because the bands are cuts of the same series. They "
      "are printed so the partition is auditable, not because they carry information.")
    A("")
    for b in BOARD_ORDER:
        keys = [k for k in p["presence"]["by_board_band"] if k.startswith(b + "|")]
        if not keys:
            continue
        A(f"**`{b}`**")
        A("")
        rows = []
        for k in sorted(keys):
            cell = p["presence"]["by_board_band"][k]
            rows.append([f"`{k.split('|')[1]}`", _hn(cell["honest_n"])]
                        + [f"{cell['footprint_shares'][f]['share_pct']}%" for f in FKEYS])
        A(md_table(["dd band", "honest-N"] + [FSHORT[f] for f in FKEYS], rows))
        A("")
    A("Legend: " + " · ".join(f"**{FSHORT[f]}** {FOOTPRINTS[f][0]}" for f in FKEYS) + ".")
    A("")
    A("_Full band distributions (`below_band`, `dur_band`, `sect35_band`, `volz_band`) "
      "per board × dd band × era are in the JSON receipt under `presence`._")
    A("")

    # §4
    A("## 4. Arming order")
    A("")
    A(f"**Arming** = the start of the FINAL true-run ending at the eve. A footprint that "
      f"oscillates arms at the start of its LAST run, never its first "
      f"(`verify.arming_is_final_true_run`). **Lead** = sessions from the arming session "
      f"to the board. A footprint already true throughout the whole "
      f"{ARMING_LOOKBACK}-session window is **censored** and printed `≥{ARMING_LOOKBACK}` "
      "— a floor, never a value.")
    A("")
    A("### 4a. Most frequent complete orders (CORE-4)")
    A("")
    A("Over events where all four of the operator's named families armed: **DD20** "
      "(washout depth), **MA200** (basing), **CONF** (terminal confluence), **SECT** "
      "(sector-wide washout). Censored footprints form one leading tied group "
      f"`{{…}}≥{ARMING_LOOKBACK}` because their mutual order is unknowable from the "
      "window; uncensored ones follow earliest-first with their lead in parentheses.")
    A("")
    for b in BOARD_ORDER:
        cell = p["arming_order"]["core4"]["by_board"].get(b)
        if not cell:
            continue
        A(f"**`{b}`** — all four armed on {cell['events_all_keys_armed']} of "
          f"{cell['events_in_group']} arming-eligible cohort events "
          f"({cell['share_all_keys_armed_pct']}%); {cell['names']} names, "
          f"{cell['sessions']} sessions, {cell['distinct_signatures']} distinct orders.")
        A("")
        A(md_table(["arming order (earliest → latest)", "events", "% of all-four-armed"],
                   [[f"`{t['signature']}`", t["events"], f"{t['pct_of_all_armed']}%"]
                    for t in cell["top"]]))
        A("")
    A("_Per dd band × era signatures, and the full 8-footprint signature counts, are in "
      "the JSON under `arming_order`._")
    A("")
    A("### 4b. Pairwise precedence (CORE-4 pairs)")
    A("")
    A("Among events where BOTH footprints armed: how often the row's first-named "
      "footprint armed earlier. Pairs where both are censored are **unresolved** — never "
      "a tie and never a coin flip — and same-session armings are excluded from the "
      "strict denominator. Both counts are printed.")
    A("")
    for b in BOARD_ORDER:
        cell = p["arming_order"]["pairwise"]["by_board"].get(b)
        if not cell:
            continue
        rows = []
        for ai in range(len(CORE4)):
            for bi in range(ai + 1, len(CORE4)):
                a, bb = CORE4[ai], CORE4[bi]
                r = cell.get(f"{a}|{bb}") or cell.get(f"{bb}|{a}")
                if not r:
                    continue
                flip = f"{a}|{bb}" not in cell
                pct = r["pct_a_before_b"]
                if flip and pct is not None:
                    pct = _r(100.0 - pct, 2)
                rows.append([f"`{FSHORT[a]}` before `{FSHORT[bb]}`",
                             f"{pct}%" if pct is not None else "—",
                             r["strict_denominator"], r["n_both_armed"],
                             r["n_unresolved_both_censored"], r["n_same_session"]])
        if rows:
            A(f"**`{b}`**")
            A("")
            A(md_table(["precedence", "rate", "strict denom", "both armed",
                        "unresolved (both censored)", "same session"], rows))
            A("")
    A("_All 28 pairs per board × dd band × era are in the JSON under "
      "`arming_order.pairwise`._")
    A("")

    # §5
    A("## 5. Lead-time distributions")
    A("")
    A("Sessions from arming to the board, per footprint. Quantiles use the nearest-rank "
      f"rule with the censored block at the top of the order, so a quantile landing "
      f"inside it prints `≥{ARMING_LOOKBACK}` rather than an imputed number. `armed%` is "
      "the share of the group's events on which the footprint was armed at all.")
    A("")
    for b in BOARD_ORDER:
        cell = p["lead_times"]["by_board"].get(b)
        if not cell:
            continue
        bandk = sorted(k for k in p["lead_times"]["by_board_band"]
                       if k.startswith(b + "|"))
        A(f"**`{b}`** — honest-N {_hn(cell['honest_n'])} (arming-eligible cohort events)")
        A("")
        rows = []
        for f in FKEYS:
            q = cell["footprints"][f]
            r = [f"`{FSHORT[f]}`", f"{q['armed_pct']}%", q["n_armed"],
                 _fmt_q(q["q1"]), _fmt_q(q["median"]), _fmt_q(q["q3"]),
                 f"{q['censored_pct']}%" if q["censored_pct"] is not None else "—"]
            for k in bandk:
                bq = p["lead_times"]["by_board_band"][k]["footprints"][f]
                r.append(f"{_fmt_q(bq['median'])} (n={bq['n_armed']})")
            rows.append(r)
        A(md_table(["footprint", "armed%", "n armed", "Q1", "median", "Q3",
                    f"cens ≥{ARMING_LOOKBACK}"]
                   + [f"med `{k.split('|')[1]}`" for k in bandk], rows))
        A("")
    A("_The last three columns are the median lead inside each dd band, with that band's "
      "own armed count. Per board × era and per board × dd band × era distributions, "
      "with Q1/Q3 and censoring rates on every cell, are in the JSON under `lead_times`._")
    A("")

    # §6
    A(f"## 6. Worked example — `{WORKED_EXAMPLE_TICKER}`, board "
      f"{str(WORKED_EXAMPLE_BOARD_DATE.date())}")
    A("")
    w = p["worked_example"]
    if w.get("status") != "IN COHORT":
        A(f"**{w['status']}** — {w.get('why', '')}")
        A("")
    else:
        A(f"The genesis case. Board `{w['board_date']}`, eve `{w['eve_date']}`, board key "
          f"`{w['board_key']}`, era `{w['era']}`, sector `{w['sector']}`.")
        A("")
        A(f"**{w['claims_stamp']}**")
        A("")
        es = w["eve_state"]
        A("State at the eve:")
        A("")
        A(md_table(["dd250", "dd band", "duration band", "below-200DMA band",
                    "sector deep35 band", "sector deep35 %", "vol-z band"],
                   [[es["dd250"], f"`{es['dd_band']}`", f"`{es['dur_band']}`",
                     f"`{es['below_band']}`", f"`{es['sect35_band']}`",
                     es["sect_deep35_pct"], f"`{es['volz_band']}`"]]))
        A("")
        A("Full footprint arming timeline:")
        A("")
        A(md_table(["footprint", "true at eve", "armed on", "lead (sessions to board)",
                    "censored"],
                   [[f"`{FSHORT[f]}` — {FOOTPRINTS[f][0].split('(')[0].strip()}",
                     "yes" if w["arming_timeline"][f]["at_eve"] else "no",
                     w["arming_timeline"][f]["arming_session"] or "—",
                     w["arming_timeline"][f]["lead_sessions"]
                     if w["arming_timeline"][f]["lead_sessions"] is not None else "—",
                     "yes" if w["arming_timeline"][f]["censored_at_lookback_edge"]
                     else "no"]
                    for f in FKEYS]))
        A("")
        A(f"CORE-4 arming order: `{w['core4_signature']}`")
        A("")
        A(f"Full 8-footprint arming order: `{w['full_signature']}`")
        A("")
        A(f"Footprint tape, the last {WORKED_EXAMPLE_TAIL} sessions into the board "
          "(`•` true, `·` false):")
        A("")
        A(md_table(["session"] + [FSHORT[f] for f in FKEYS] + ["mark"],
                   [[r["date"]] + ["•" if r[FSHORT[f]] else "·" for f in FKEYS]
                    + ["**board**" if r["is_board"] else
                       ("**eve**" if r["is_eve"] else "")]
                    for r in w["footprint_tape_last_sessions"]]))
        A("")

    # §7
    A("## 7. Verification")
    A("")
    s = p["verify"]["summary"]
    A(f"**{s['checks_passed']} of {s['checks_run']} checks passed; "
      f"{s['mutation_probes_detected']} of {s['checks_run']} mutation probes detected "
      "their mutation.**")
    A("")
    A("_A check that cannot fail is a defect. Every check is paired with a mutation it "
      "MUST detect; `detected: false` anywhere means the check is vacuous and the run is "
      "not evidence._")
    A("")
    A(md_table(["check", "result", "probe", "mutation applied"],
               [[f"`{k}`", "pass" if c["passed"] else "**FAIL**",
                 "detected" if c["mutation_probe"]["detected"] else "**VACUOUS**",
                 c["mutation_probe"]["mutation"]]
                for k, c in p["verify"]["checks"].items()]))
    A("")
    d = p["verify"]["checks"]["detector_vs_zt_pool"]["detail"]
    A(f"**Detector cross-check.** On the {d['shared_dates']} sessions where "
      f"`china_zt_pool` and the footprint plane both have coverage, "
      f"{d['zt_pairs_inside_footprint_universe']} pool rows fall inside the footprint "
      f"universe and the tolerant detector agrees on {d['agree']} — recall "
      f"**{d['recall_pct']}%**. One-directional by construction: `china_zt_pool` is a "
      "PARTIAL vendor store, so this is a RECALL measurement on the pool's own rows and "
      "is not a precision test.")
    A("")
    nl = p["verify"]["checks"]["no_lookahead_armings_and_footprints"]["detail"]
    A(f"**No-lookahead.** {nl['tickers_sampled']} names rebuilt with every bar after each "
      f"cut scaled by {nl['prices_scaled_by']}, at three cuts spanning the history. The "
      "state is re-read at FIXED `(ticker, eve)` anchors, because a corruption that "
      "starts after the eve necessarily rewrites the board bar — re-extracting the event "
      "set would compare a different set of events and report the corruption doing its "
      "job as a leak.")
    A("")
    A(md_table(["cut", "anchors", "armings changed", "pre-cut footprint cells changed",
                "pre-cut rows", "anchors where corruption starts the next session"],
               [[r["cut"], r["anchors"], r["armings_changed"],
                 r["pre_cut_footprint_cells_changed"], f"{r['pre_cut_rows_compared']:,}",
                 r["anchors_with_corruption_starting_the_next_session"]]
                for r in nl["per_cut"]]))
    A("")
    A("The last column is the literal *strictly after the eve* case: those anchors have "
      "the corruption beginning on the very next session. It is small by construction — "
      "it requires a cut to land on an anchor's own eve — and it is not what carries the "
      "check. What carries it is that the ENTIRE tape after each cut is rewritten while "
      "every anchor's 60-session arming window and 250-session footprint lookbacks sit "
      "wholly before it. The probe scales a two-year slab INSIDE the pre-cut history "
      "instead — which must move both columns, because every footprint here is a ratio "
      "and a uniform whole-history rescale would leave them bit-identical for the wrong "
      "reason.")
    A("")
    cw = p["verify"]["checks"]["cold_window_ejects_a_planted_board"]["detail"]
    A(f"**Cold window.** Planting a tolerant board {cw.get('planted_offset_sessions')} "
      f"sessions before `{cw.get('probe_ticker')} @ {cw.get('probe_event_date')}` ejects "
      "it from the first-board set; the probe plants the same board 25 sessions back — "
      "outside the prior-20 window — where the event must survive.")
    A("")

    # §8
    A("## 8. What this does NOT establish")
    A("")
    for x in p["does_not_establish"]:
        A(f"- {x}")
    A("")

    # §9
    A("## 9. Ore ledger — mapped, not built")
    A("")
    for x in p["ore_ledger"]:
        A(f"- {x}")
    A("")

    # §10
    A("## 10. Amendments — every deviation declared")
    A("")
    for a in p["amendments"]:
        A(f"**{a['id']} — {a['what']}**")
        A("")
        A(f"- why: {a['why']}")
        A(f"- controlled by: {a['risk_controlled_by']}")
        A("")

    # §11
    A("## 11. Provenance")
    A("")
    v = p["vintage"]
    A(md_table(["stamp", "value"],
               [[f"`{k}`", f"`{v[k]}`"] for k in
                ("base_sha", "build_head_sha", "raw_store_commit", "members_commit",
                 "st_snapshot_commit", "zt_pool_commit", "w1_pin_commit", "w1_sha256")]))
    A("")
    A("Every store stamp is verified to be an ancestor of the build head before either "
      "file is written (the A4 provenance guard); a checkout that moved mid-run refuses "
      "to write rather than emit polluted provenance. A stamp that resolves to a "
      "shallow-clone graft is relabelled rather than printed as provenance (§10 A5): "
      f"`repo_is_shallow` = `{v['repo_is_shallow']}`, unresolved stamps "
      f"`{v['stamps_unresolved_by_shallow_graft'] or 'none'}`. Consecutive runs of this "
      "instrument are byte-identical — no wall-clock value enters either receipt.")
    A("")
    A(f"Pinned definitions: `washout_onset_w1.py` @ sha256 `{v['w1_sha256'][:16]}…`, "
      "**imported**. Inherited limits travel with the pin: the footprint plane is a "
      "curated large-cap **survivor** slice (delisted names absent); "
      "`china_stocks_raw` is **back-adjusted**, so this is a tolerant-detector cohort "
      "and not an exchange-exact legal-limit one; and the sector footprint applies "
      "today's sector map to 15 years of history.")
    A("")
    return "\n".join(L) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("P-B — case decomposition of the 300363-class first-board winners", flush=True)
    w1, w1_sha = load_w1()
    print(f"  [1/7] pinned W-P0 imported  sha256={w1_sha[:16]}…", flush=True)

    panel, pmeta = build_footprint_panel(w1)
    panel = derive_footprints(panel)
    print(f"  [2/7] footprint plane  {pmeta['panel_rows']:,} rows  "
          f"{pmeta['panel_names']:,} names  {pmeta['panel_sessions']:,} sessions",
          flush=True)

    ev = extract_events(panel, w1)
    coh = cohort_tables(ev)
    print(f"  [3/7] cohort  {coh['all_first_board_events']['events']:,} first-board "
          f"events  {coh['in_cohort']['events']:,} in cohort", flush=True)

    armed, lead, cens = compute_armings(panel, ev, w1)
    arm = arming_frame(ev, armed, lead, cens)
    print(f"  [4/7] armings  {len(arm):,} event x footprint records", flush=True)

    presence = OrderedDict([
        ("by_board_band", presence_tables(ev, ["board_key", "dd_band"])),
        ("by_board_era", presence_tables(ev, ["board_key", "era"])),
        ("by_board_band_era", presence_tables(ev, ["board_key", "dd_band", "era"])),
    ])
    lead_tabs = OrderedDict([
        ("by_board", lead_table(arm, "board_key")),
        ("by_board_band", lead_table(arm, ["board_key", "dd_band"])),
        ("by_board_era", lead_table(arm, ["board_key", "era"])),
        ("by_board_band_era", lead_table(arm, ["board_key", "dd_band", "era"])),
    ])
    order_tabs = OrderedDict([
        ("core4", OrderedDict([
            ("by_board", order_signatures(ev, armed, lead, cens, CORE4, "board_key")),
            ("by_board_band", order_signatures(ev, armed, lead, cens, CORE4,
                                               ["board_key", "dd_band"])),
            ("by_board_era", order_signatures(ev, armed, lead, cens, CORE4,
                                              ["board_key", "era"])),
        ])),
        ("full8", OrderedDict([
            ("by_board", order_signatures(ev, armed, lead, cens, FKEYS, "board_key")),
        ])),
        ("pairwise", OrderedDict([
            ("by_board", pairwise_precedence(ev, armed, lead, cens, ["board_key"])),
            ("by_board_band", pairwise_precedence(ev, armed, lead, cens,
                                                  ["board_key", "dd_band"])),
            ("by_board_era", pairwise_precedence(ev, armed, lead, cens,
                                                 ["board_key", "era"])),
        ])),
    ])
    wex = worked_example(panel, ev, armed, lead, cens)
    print("  [5/7] presence + order + lead-time tables + worked example built", flush=True)

    verify = verify_battery(w1, w1_sha, panel, ev, armed, lead, cens, arm, coh,
                            presence, lead_tabs, order_tabs)
    sm = verify["summary"]
    print(f"  [6/7] verify  {sm['checks_passed']}/{sm['checks_run']} passed  "
          f"{sm['mutation_probes_detected']}/{sm['checks_run']} probes detected",
          flush=True)

    if not sm["all_passed"]:
        bad = sorted(k for k, c in verify["checks"].items() if not c["passed"])
        print(f"::error title=pb-verify-failed::P-B verify battery failed: "
              f"{', '.join(bad)}", flush=True)
    if not sm["all_probes_detected"]:
        bad = sorted(k for k, c in verify["checks"].items()
                     if not c["mutation_probe"]["detected"])
        print(f"::error title=pb-vacuous-check::P-B mutation probe undetected "
              f"(the check cannot fail): {', '.join(bad)}", flush=True)
    excl = sum(coh["per_board"][b]["arming_ineligible_short_lookback"]
               for b in BOARD_ORDER)
    if excl:
        print(f"::notice title=pb-short-lookback::{excl} cohort event(s) excluded from "
              f"the arming tables for fewer than {ARMING_LOOKBACK} prior sessions — "
              f"counted per board in the receipt, never silently dropped", flush=True)

    vintage = build_vintage(w1_sha)
    if vintage["stamps_unresolved_by_shallow_graft"]:
        print(f"::warning title=pb-shallow-vintage::vintage stamp(s) "
              f"{', '.join(vintage['stamps_unresolved_by_shallow_graft'])} resolve to a "
              f"shallow-clone graft and are relabelled, not printed as provenance — "
              f"deepen the checkout (git fetch --deepen) for real store vintages",
              flush=True)

    payload = OrderedDict([
        ("instrument", "pb_case_decomposition"),
        ("wave", "CN LIMIT-MOVE ALPHA — P-B: case decomposition of the 300363-class "
                 "first-board winners"),
        ("artifact_date", ARTIFACT_DATE),
        ("authority", AUTHORITY),
        ("tier", TIER_STAMP),
        ("governing_ruling", "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT"),
        ("program_home", "research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md (§3 P-B)"),
        ("pre_registration_lives_in", "the module docstring of pb_case_decomposition.py"),
        ("pin", {
            "source": "research/cn_prophet_audit/washout_onset_w1.py",
            "mode": "IMPORTED (module is import-safe — execution is guarded behind "
                    "`if __name__ == \"__main__\"` at W-P0 L2285 and import does no work "
                    "beyond constant binding and an input-store existence check; nothing "
                    "copied, nothing re-derived)",
            "w1_sha256": w1_sha,
            "symbols": {k: f"L{ln}" for k, (ln, _n) in PIN_SYMBOLS.items()},
            "symbols_verified_by": "verify.pin_line_numbers_resolve",
        }),
        ("definitions", {
            "cohort": {
                "event": "a W-P0 tolerant limit-up close (`lu`, W-P0 L986)",
                "eve": "the name's previous PANEL session (live, in-window)",
                "cold_at_eve": "W-P0's `cold` at the eve (L990) — no tolerant board in "
                               "the prior 20 sessions",
                "step_rule_calendar_days": int(w1.MAX_STEP_GAP_DAYS),
                "bands": list(COHORT_BANDS),
                "out_of_cohort_bands": list(OUT_OF_COHORT_BANDS),
                "boards": list(BOARD_ORDER),
            },
            "footprints": OrderedDict((k, v[0]) for k, v in FOOTPRINTS.items()),
            "footprint_short_codes": FSHORT,
            "core4": list(CORE4),
            "band_columns": dict(BAND_COLS),
            "arming": {
                "lookback_sessions": ARMING_LOOKBACK,
                "rule": "the START of the FINAL true-run ending at the eve; an "
                        "oscillating footprint arms at the start of its LAST run, never "
                        "its first",
                "implementation": "run_start = eve_pos - streak_lengths(f)[eve_pos] + 1, "
                                  "on W-P0's own helper (L535)",
                "lead": "event_pos - run_start; armed exactly at the eve -> 1; "
                        "uncensored leads lie in [1, 59]",
                "censored": f">= {ARMING_LOOKBACK}, a FLOOR and never a value — the run "
                            "reaches the first position of the lookback window",
                "quantile_rule": "nearest rank with the censored block sorted to the top "
                                 "of the order; a quantile landing inside it prints "
                                 f">={ARMING_LOOKBACK} rather than an imputed number",
                "precedence_rule": "exactly one censored -> resolved (the censored one "
                                   "armed earlier); both censored -> UNRESOLVED, never a "
                                   "tie; equal uncensored leads -> SAME-SESSION, excluded "
                                   "from the strict denominator, which is printed",
                "eligibility": f"at least {ARMING_LOOKBACK} prior sessions on the name's "
                               "own axis (see amendments A2)",
            },
        }),
        ("footprint_plane", pmeta),
        ("cohort", coh),
        ("presence", presence),
        ("arming_order", order_tabs),
        ("lead_times", lead_tabs),
        ("worked_example", wex),
        ("verify", verify),
        ("does_not_establish", DOES_NOT_ESTABLISH),
        ("ore_ledger", ORE_LEDGER),
        ("amendments", AMENDMENTS),
        ("survivorship_stamp", w1.SURVIVORSHIP_STAMP),
        ("vintage", vintage),
    ])

    # A4 provenance-stability guard — every path stamp must be reachable from the build
    # head, else the checkout moved mid-run and the stamps are polluted. Refuse to write.
    _head = payload["vintage"]["build_head_sha"]
    for _k in ("raw_store_commit", "members_commit", "st_snapshot_commit",
               "zt_pool_commit", "w1_pin_commit"):
        _c = payload["vintage"][_k]
        if _c.startswith("SHALLOW_BOUNDARY_UNRESOLVED(") or _c == "UNAVAILABLE":
            continue
        if subprocess.run(["git", "merge-base", "--is-ancestor", _c, _head],
                          cwd=REPO, capture_output=True).returncode != 0:
            raise SystemExit(
                f"vintage stamp {_k}={_c} is not an ancestor of build head {_head} — "
                "checkout moved mid-run; refusing to write polluted provenance")

    md = build_md(payload)

    # The STOP-SHIP scan must cover the EMITTED PROSE, not just the source that generated
    # it. Re-run it over both surfaces and record the honest two-surface result.
    final_ok, final_det = stop_ship_scan({
        "pb_case_decomposition.py": Path(__file__).read_text(),
        OUT_MD.name: md,
    })
    ss = payload["verify"]["checks"]["stop_ship_reference_scan"]
    ss["passed"], ss["detail"] = final_ok, final_det
    if not final_ok:
        raise SystemExit(
            f"withdrawn-artifact reference(s) found: {final_det['hits']} — "
            "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT; refusing to write")

    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=False) + "\n")
    OUT_MD.write_text(md)
    print(f"  [7/7] wrote {OUT_JSON.relative_to(REPO)} "
          f"({OUT_JSON.stat().st_size / 1e6:.2f} MB) and {OUT_MD.relative_to(REPO)} "
          f"({OUT_MD.stat().st_size / 1e3:.1f} kB, "
          f"{len(md.splitlines())} lines)", flush=True)

    # A failing check or a vacuous one must make the RUN red, even though the receipts are
    # written — they are the diagnosis surface.
    return 0 if (sm["all_passed"] and sm["all_probes_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
