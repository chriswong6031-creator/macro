#!/usr/bin/env python3
"""CN LIMIT-MOVE ALPHA — P-A1: the DESCRIPTIVE read of the actual Prophet pick panel.

    TZ=UTC python3 research/cn_prophet_audit/pa1_panel_read.py

AUTHORITY: `none_research_display_only`.  Nothing in this file or its receipts ranks,
sizes, gates, alerts or trades.  This instrument COUNTS and LISTS.  It computes no lift,
no t-statistic, no interval, no null, no comparison against any non-panel baseline, and
no inference row of any kind — by charter (`P_A_PANEL_CHARTER_2026-08-11.md` sec.4/sec.5),
because the panel is 27 sessions of ONE era, entirely in-sample of the current regime, and
its genesis stream is frozen at 5 sessions.  The inference battery is P-A2 and it is
accrual-gated: no stream is measured until it reaches >=120 distinct sessions AND spans
>=2 `own_market_regime` segments.  Partial peeks are forbidden; that gate was
pre-registered in the charter before this file was written.

STOP-SHIP compliance: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` governs.  This instrument
cites no withdrawn artifact and no W1-W3 construction or number.  A grep-verified
receipt of that fact is emitted with every run (`verify.stop_ship_reference_scan`).

WHAT THIS READS
---------------
Two in-repo point-in-time ledgers, READ-ONLY, vintage-stamped by data commit:

  A. `data/china_standout_track/board.parquet`      — the surfaced board (what was seen)
  B. `data/china_prophet_rank/candidates.parquet`   — the pre-gate scored universe

Both are owned by the standout-track program; this instrument consumes and never writes
them, and never reconciles their disagreements (charter term 5 — same-day board-vs-
candidates contradiction is a known, formally flagged defect of the WRITE path, reported
here per stream and left standing).

PER-DEFINITION CONDITIONING IS MANDATORY (charter term 2)
---------------------------------------------------------
A `board_definition` is a different instrument, not a different day of the same one.  The
five streams — legacy / cn_prophet_v2 / cn_prophet_v2_shadow / cn_prophet_v3 /
cn_reversal_watch_v1 — are NEVER pooled anywhere in this file.  Every table is stamped
with its stream, its session count and its distinct-name honest-N.  `cn_prophet_v2` is
the genesis stream and it is FROZEN — superseded by v3 on 2026-08-06 at 5 sessions — and
that fact is printed wherever v2 appears.

QUARANTINED COLUMNS (charter term 3)
------------------------------------
`fwd_mfe_5`, `fwd_mfe_10`, `fwd_mfe_21`, `fwd_mfe_63`, `terminal_state_clean15_126`,
`terminal_state_clean8_21`, `post_cushion_breach`, `level` are NEVER read.  The forward
and terminal-state columns are computed by the ledger's own writer on the DIVIDEND-
ADJUSTED `china_stocks` plane, and `level` carries the writer's pre-settle stamping
caveat.  This instrument loads both parquets through an explicit column ALLOWLIST, so
the quarantined columns are not merely unused — they are never materialised.
`verify.quarantined_columns` proves it on every loaded frame and can fail (mutation
probe included).

BOARD OUTCOMES ARE RE-DERIVED, NEVER READ (charter term 4)
-----------------------------------------------------------
First-board incidence comes from `data/china_stocks_raw` through W-P0's own tolerant
detector (close >= round(prev_close * (1 + width), 2) * (1 - 0.002)), reached by IMPORT
rather than by re-implementation — see THE PIN below.

RIGHT-CENSORING IS REPORTED, NEVER COUNTED AS A NEGATIVE
---------------------------------------------------------
The store ends at the panel's own last session, so a pick made near the end has no
complete H-session forward window.  W-P0's `win_ok_H` marks those rows unevaluable and
its `fb_H` is therefore False on them — which is "window incomplete", NOT "no board".
Reporting those as zeros would be the endpoint-null error.  Every incidence table here is
a TRICHOTOMY:

    board_within_H            a tolerant board occurred in T+1..T+H  (an OBSERVED event —
                              still an event when the window is incomplete)
    no_board_window_complete  W-P0's win_ok_H holds and no board occurred
    censored_no_board_yet     window incomplete and no board observed so far

W-P0's own `fb_H` count is printed beside the trichotomy for pin-faithfulness.

THE PIN (charter sec.5 requirement 1 — no third re-derivation of the oracle math)
---------------------------------------------------------------------------------
Every footprint, band, state name and the limit detector are IMPORTED from
`research/cn_prophet_audit/washout_onset_w1.py` (W-P0, the pinned definitions).  The
module is import-safe: it guards execution behind `if __name__ == "__main__"` (line 2285)
and does no work at import beyond constant binding and input-store existence checks.
Nothing is copied.  Pinned symbols and their W-P0 source lines, as of the vintage stamped
in the receipt (`pin.w1_sha256` fixes the exact file this ran against):

    LIMIT_CLOSE_TOL            L353    the 0.002 tolerant cushion
    COLD_LOOKBACK_K            L357    K=20 no-board lookback defining a COLD bar
    DD_LOOKBACK / DD_MINP      L371    250-session high for the drawdown footprint
    MA_LEN / MA_MINP           L372    the 200DMA footprint
    RV_LEN / RV_RANK_LOOKBACK  L373    the quiet-base footprint
    LOW252 / LOW252_MINP       L375    52w-low distance
    confluence_states()        L823    S1 — the Terminal confluence transcription
    process_ticker()           L947    per-name bars -> lu / cold / dd250 / bands inputs;
                                       the tolerant detector itself is L986, the forward
                                       first-board columns are L1043-L1053
    build_panel()              L1088   the full-cross-section loop over china_stocks_raw
    _band()                    L1154   the left-open/right-closed band convention
    attach_conditioners()      L1173   S4 sector washout breadth + f4 heat + the bands
    build_state_masks()        L1243   the pre-registered STATE REGISTRY, used verbatim
    _git()                     L591    vintage stamping helper
    SURVIVORSHIP_STAMP         L401    inherited verbatim — see below

INHERITED LIMITS (they travel with the pin; restating them is not optional)
---------------------------------------------------------------------------
* SURVIVORSHIP.  The footprint plane is W-P0's curated large-cap survivor slice.
  Delisted names are absent.  Nothing here extrapolates to small caps.
* BACK-ADJUSTED BASIS.  `china_stocks_raw` is back-adjusted OHLCV (W-P0 BASIS NOTE, L49),
  so a reconstructed prev-close/close ratio can sit a hair off the exchange's tick-rounded
  legal limit.  `verify.detector_vs_zt_pool` measures exactly that residual and names
  every miss.
* The panel is the standout-track ledger's own history.  It is not a random sample of
  anything, and this file makes no claim that it is.

DECLARED DEVIATIONS from a bare W-P0 invocation are listed in `amendments` in both
receipts and in the writeup's Amendments section.  There are three, all mechanical, all
receipted; none touches the oracle math.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "research" / "cn_prophet_audit"
W1_PATH = OUT_DIR / "washout_onset_w1.py"
OUT_JSON = OUT_DIR / "PA1_PANEL_READ_2026-08-11.json"
OUT_MD = OUT_DIR / "PA1_PANEL_READ_2026-08-11.md"

BOARD_P = REPO / "data" / "china_standout_track" / "board.parquet"
CAND_P = REPO / "data" / "china_prophet_rank" / "candidates.parquet"
ZT_P = REPO / "data" / "china_zt_pool" / "pool.parquet"
RAW_DIR = REPO / "data" / "china_stocks_raw"

# ── frozen parameters of THIS read ────────────────────────────────────────────

ARTIFACT_DATE = "2026-08-11"

# The panel's forward evaluation edge.  Pinned (not discovered) so the artifact is
# reproducible: `verify.window_extension` proves the raw store actually reaches it and
# that extending W-P0's audit edge to it does not move a single limit-width rule.
PANEL_WINDOW_END = pd.Timestamp("2026-08-11")
# Output-row trim only.  Every rolling footprint is computed by W-P0 on each name's FULL
# series before this filter is applied, so trimming cannot change a footprint value; it
# only bounds the size of the frame we carry.  `verify.window_trim_is_output_only` pins it.
PANEL_WINDOW_START = pd.Timestamp("2026-05-01")

HORIZONS = (5, 10)

STREAM_ORDER = ("legacy", "cn_prophet_v2", "cn_prophet_v2_shadow", "cn_prophet_v3",
                "cn_reversal_watch_v1")
FROZEN_STREAM = "cn_prophet_v2"
FROZEN_STREAM_FACT = ("FROZEN — the genesis stream; superseded by cn_prophet_v3 on "
                      "2026-08-06 at 5 sessions. It will not accrue further.")

WORKED_EXAMPLE_TICKER = "300363.SZ"
WORKED_EXAMPLE_DATE = pd.Timestamp("2026-08-05")

TIER_STAMP = ("display / audit tier — descriptive counts and episode lists only; not a "
              "promotion, not a gate, not a ranker, not a sizing input; no expectancy, "
              "no lift and no inference is quoted anywhere in this artifact")

# ── the quarantine (charter term 3) ───────────────────────────────────────────

QUARANTINED = (
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63",
    "terminal_state_clean15_126", "terminal_state_clean8_21",
    "post_cushion_breach", "level",
)

# Explicit ALLOWLISTS. The quarantined columns are never materialised.
BOARD_COLS = [
    "date", "ticker", "board_definition", "board_rank", "lane", "tier",
    "prophet_score", "prophet_bottom_quality", "washout", "washout_2w", "species_id",
    "setup", "stage", "hold_state", "entry_status", "own_market_regime",
]
CAND_COLS = [
    "stamp_date", "ticker", "board_definition", "score_rank", "prophet_score",
    "raw_eligible", "buyable", "gate_reason", "gate_state", "gate_tier", "gate_sub",
    "lane", "stage",
]

# Tokens that must not appear in this instrument or its receipts (STOP-SHIP scan).
# ASSEMBLED FROM FRAGMENTS ON PURPOSE: this instrument scans its OWN source text for
# these tokens, so writing them as literals here would guarantee a false positive and
# make the check useless. No full token ever appears verbatim in this file.
_WAVES = ("1", "2", "3")
_ADJ, _LEG, _LIM, _TAPE = "adjusted", "legal", "limit", "tape"
WITHDRAWN_TOKENS = tuple(
    [f"cn_limit_alpha_w{i}" for i in _WAVES]
    + [f"limit_alpha_w{i}" for i in _WAVES]
    + [f"W{i}_RESULTS" for i in _WAVES]
    + [f"cn_limit_washout_w{i}" for i in _WAVES]
    + [f"{_ADJ}_{_TAPE}_{_LEG}_{_LIM}", f"{_LEG}_{_LIM}_on_{_ADJ}"]
)

# The pin, as (symbol -> (W-P0 line, the token that must appear on it)). This is not
# decoration: `verify.pin_line_numbers_resolve` re-reads W-P0 and fails if any pinned line
# no longer holds its symbol, so a future edit to W-P0 cannot silently rot the pin comment
# in this module's docstring.
PIN_SYMBOLS = OrderedDict([
    ("LIMIT_CLOSE_TOL", (353, "LIMIT_CLOSE_TOL")),
    ("COLD_LOOKBACK_K", (357, "COLD_LOOKBACK_K")),
    ("DD_LOOKBACK/DD_MINP", (371, "DD_LOOKBACK")),
    ("MA_LEN/MA_MINP", (372, "MA_LEN")),
    ("RV_LEN/RV_RANK_LOOKBACK", (373, "RV_LEN")),
    ("LOW252/LOW252_MINP", (375, "LOW252")),
    ("SURVIVORSHIP_STAMP", (401, "SURVIVORSHIP_STAMP")),
    ("_git", (591, "def _git")),
    ("confluence_states", (823, "def confluence_states")),
    ("process_ticker", (947, "def process_ticker")),
    ("w1_min_history_gate", (948, "len(df) < 400")),
    ("tolerant_detector", (986, "LIMIT_CLOSE_TOL")),
    ("build_panel", (1088, "def build_panel")),
    ("_band", (1154, "def _band")),
    ("attach_conditioners", (1173, "def attach_conditioners")),
    ("build_state_masks", (1243, "def build_state_masks")),
])

# W-P0's minimum-history gate, a bare literal at its L948
# (`if df is None or len(df) < 400`). Pinned here so the PIT check can prove that every
# unmeasured pick is THAT gate declining to measure, rather than a silent data gap.
W1_MIN_HISTORY_BARS = 400


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
    """Import W-P0 by path. Returns (module, sha256, orig_window_end)."""
    if not W1_PATH.exists():
        raise SystemExit(
            f"MISSING PIN SOURCE: {W1_PATH}\n"
            "P-A1 imports every footprint definition from W-P0 and re-derives none of "
            "them. Run this on a checkout of main where that file is tracked.")
    sha = hashlib.sha256(W1_PATH.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("_pa1_w1", W1_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pa1_w1"] = mod
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
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return _r(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    return o


# ── stage 1 — load the two PIT stores (allowlisted) ───────────────────────────


def load_stores():
    board = pd.read_parquet(BOARD_P, columns=BOARD_COLS)
    board["date"] = pd.to_datetime(board["date"])
    cand = pd.read_parquet(CAND_P, columns=CAND_COLS)
    cand["stamp_date"] = pd.to_datetime(cand["stamp_date"])
    board = board.sort_values(["date", "board_definition", "ticker"],
                              kind="mergesort").reset_index(drop=True)
    cand = cand.sort_values(["stamp_date", "board_definition", "ticker"],
                            kind="mergesort").reset_index(drop=True)
    return board, cand


def stream_meta(board: pd.DataFrame, cand: pd.DataFrame) -> "OrderedDict":
    out: "OrderedDict[str, dict]" = OrderedDict()
    for s in STREAM_ORDER:
        g = board[board["board_definition"] == s]
        c = cand[cand["board_definition"] == s]
        out[s] = {
            "board_rows": int(len(g)),
            "board_sessions": int(g["date"].nunique()),
            "board_distinct_names": int(g["ticker"].nunique()),
            "board_span": [str(g["date"].min().date()), str(g["date"].max().date())]
            if len(g) else None,
            "candidates_rows": int(len(c)),
            "candidates_sessions": int(c["stamp_date"].nunique()),
            "candidates_distinct_names": int(c["ticker"].nunique()),
            "frozen": s == FROZEN_STREAM,
            "frozen_note": FROZEN_STREAM_FACT if s == FROZEN_STREAM else None,
        }
    return out


# ── stage 2 — the footprint plane (imported W-P0 math, unchanged) ─────────────


def build_footprint_panel(w1):
    """W-P0's own panel, over the P-A1 window. No footprint math is re-implemented."""
    w1.WINDOW_START = PANEL_WINDOW_START
    w1.WINDOW_END = PANEL_WINDOW_END
    panel, pmeta = w1.build_panel()
    panel, cmeta = w1.attach_conditioners(panel, None)
    panel = panel.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)
    pmeta = dict(pmeta)
    pmeta["sector_coverage_pct"] = cmeta.get("sector_coverage_pct")
    pmeta["chips_join"] = cmeta.get("chips_join")
    pmeta["panel_window"] = [str(PANEL_WINDOW_START.date()), str(PANEL_WINDOW_END.date())]
    pmeta["panel_rows"] = int(len(panel))
    pmeta["panel_sessions"] = int(panel["date"].nunique())
    pmeta["panel_names"] = int(panel["ticker"].nunique())
    return panel, pmeta


def add_forward_board_distance(panel: pd.DataFrame) -> pd.DataFrame:
    """Sessions from each bar to the NEXT tolerant board, and forward bars available.

    Reads only W-P0's own `lu` flag — this is an index scan over an already-computed
    detector output, not a second detector.
    """
    panel = panel.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)
    dist = np.full(len(panel), -1, dtype=np.int64)     # -1 == no board ahead in-store
    avail = np.zeros(len(panel), dtype=np.int64)
    for idx in panel.groupby("ticker", sort=True).indices.values():
        idx = np.sort(idx)
        lu = panel["lu"].to_numpy()[idx].astype(bool)
        n = idx.size
        pos = np.arange(n)
        avail[idx] = n - 1 - pos
        lu_pos = np.flatnonzero(lu)
        if lu_pos.size:
            nxt = np.searchsorted(lu_pos, pos, side="right")
            has = nxt < lu_pos.size
            d = np.full(n, -1, dtype=np.int64)
            d[has] = lu_pos[nxt[has]] - pos[has]
            dist[idx] = d
    panel["dist_next_board"] = dist
    panel["fwd_bars_available"] = avail
    return panel


# ── stage 3 — footprint presence at pick time + the agreement matrix ──────────

FOOTPRINTS = OrderedDict([
    ("wp0_washout_dd_le_m20", ("dd250 <= -20% off the 250-session high (W-P0 S2, the "
                               "shallowest washout-depth cut)")),
    ("wp0_washout_dd_le_m35", ("dd250 <= -35% off the 250-session high (W-P0 S2, deep)")),
    ("wp0_under_ma200", "close below the 200DMA (W-P0 S3)"),
    ("wp0_confluence_long", "S1 3D confluence long-state active (W-P0 S1)"),
    ("wp0_confluence_cb_recent", "S1 3D crossover-bull within 2 3D-bars (W-P0 S1)"),
    ("wp0_quiet_base", "20-bar realised-vol rank in the bottom third (W-P0 S5a)"),
    ("wp0_sector_deep35_ge40", ("40%+ of the name's sector members 35%+ off their own "
                                "250-session highs, leave-one-out (W-P0 S4)")),
    ("wp0_cold", "no tolerant board in the prior 20 sessions incl. T (W-P0 COLD_LOOKBACK_K)"),
])


def derive_footprints(panel: pd.DataFrame) -> pd.DataFrame:
    """Boolean footprints, every one a direct reading of a W-P0-produced column."""
    dd = panel["dd250"].to_numpy(np.float64)
    sect = panel["sect35_band"].to_numpy()
    out = panel.copy()
    out["wp0_washout_dd_le_m20"] = np.isfinite(dd) & (dd <= -0.20)
    out["wp0_washout_dd_le_m35"] = np.isfinite(dd) & (dd <= -0.35)
    out["wp0_under_ma200"] = panel["under_ma"].to_numpy(bool)
    out["wp0_confluence_long"] = panel["s1_3d_long"].to_numpy(bool)
    out["wp0_confluence_cb_recent"] = panel["s1_3d_cb_recent"].to_numpy(bool)
    out["wp0_quiet_base"] = panel["base_flag"].to_numpy(bool)
    out["wp0_sector_deep35_ge40"] = np.isin(sect, ("s2_40_60", "s3_gt60"))
    out["wp0_cold"] = panel["cold"].to_numpy(bool)
    return out


PANEL_JOIN_COLS = [
    "date", "ticker", "sector", "board_key", "cold", "lu", "dd250", "dd_band",
    "dur_band", "under_ma", "below_band", "sect35_band", "sect_deep35_pct", "volz_band",
    "base_flag", "s1_3d_long", "s1_3d_cb_recent", "s1_dot_recent", "s1_2d_rising",
    "dist_next_board", "fwd_bars_available",
] + list(FOOTPRINTS) + [f"{p}_{h}" for h in HORIZONS for p in ("fb", "win_ok")]


def join_board_to_footprints(board: pd.DataFrame, panel: pd.DataFrame):
    k = panel[PANEL_JOIN_COLS]
    m = board.merge(k, on=["date", "ticker"], how="left", indicator=True)
    matched = m[m["_merge"] == "both"].drop(columns=["_merge"]).reset_index(drop=True)
    missing = m[m["_merge"] == "left_only"][
        ["date", "ticker", "board_definition", "board_rank"]].reset_index(drop=True)
    return matched, missing


ENGINE_STAMPS = OrderedDict([
    ("engine_washout", "board.parquet `washout` (the writer's own washout flag)"),
    ("engine_species_cn_washout", "board.parquet `species_id` == 'cn_washout'"),
])


def add_engine_stamps(mm: pd.DataFrame) -> pd.DataFrame:
    mm = mm.copy()
    mm["engine_washout"] = mm["washout"].fillna(False).astype(bool)
    mm["engine_species_cn_washout"] = (mm["species_id"].astype("string")
                                       .fillna("") == "cn_washout")
    return mm


AGREEMENT_PAIRS = (
    ("engine_washout", "wp0_washout_dd_le_m20"),
    ("engine_washout", "wp0_washout_dd_le_m35"),
    ("engine_washout", "wp0_under_ma200"),
    ("engine_washout", "wp0_confluence_long"),
    ("engine_washout", "wp0_sector_deep35_ge40"),
    ("engine_species_cn_washout", "wp0_washout_dd_le_m20"),
    ("engine_species_cn_washout", "wp0_under_ma200"),
)


def agreement_matrix(mm: pd.DataFrame) -> "OrderedDict":
    """Per stream, per (engine stamp x W-P0 footprint): the full 2x2 in COUNTS."""
    out: "OrderedDict[str, dict]" = OrderedDict()
    for s in STREAM_ORDER:
        g = mm[mm["board_definition"] == s]
        cells: "OrderedDict[str, dict]" = OrderedDict()
        for e, f in AGREEMENT_PAIRS:
            ev = g[e].to_numpy(bool)
            fv = g[f].to_numpy(bool)
            cells[f"{e}__x__{f}"] = {
                "both_true": int((ev & fv).sum()),
                "engine_only": int((ev & ~fv).sum()),
                "wp0_only": int((~ev & fv).sum()),
                "both_false": int((~ev & ~fv).sum()),
                "engine_true_total": int(ev.sum()),
                "wp0_true_total": int(fv.sum()),
                "rows": int(len(g)),
            }
        out[s] = {
            "rows_with_footprints": int(len(g)),
            "sessions": int(g["date"].nunique()),
            "distinct_names": int(g["ticker"].nunique()),
            "frozen": s == FROZEN_STREAM,
            "frozen_note": FROZEN_STREAM_FACT if s == FROZEN_STREAM else None,
            "cells": cells,
        }
    return out


def _episodes(frame: pd.DataFrame, mask) -> list:
    d = frame[mask][["date", "ticker"]]
    return sorted(f"{t} @ {pd.Timestamp(x).date()}"
                  for x, t in zip(d["date"], d["ticker"]))


def divergent_names(mm: pd.DataFrame, engine: str, foot: str) -> "OrderedDict":
    """Per stream, the named episodes where the two notions disagree. Divergence is data."""
    out: "OrderedDict[str, dict]" = OrderedDict()
    for s in STREAM_ORDER:
        g = mm[mm["board_definition"] == s]
        ev = g[engine].to_numpy(bool)
        fv = g[foot].to_numpy(bool)
        out[s] = {
            "rows": int(len(g)),
            "sessions": int(g["date"].nunique()),
            "distinct_names": int(g["ticker"].nunique()),
            "frozen": s == FROZEN_STREAM,
            "frozen_note": FROZEN_STREAM_FACT if s == FROZEN_STREAM else None,
            "engine_true_wp0_false": _episodes(g, ev & ~fv),
            "engine_false_wp0_true": _episodes(g, ~ev & fv),
            "distinct_names_engine_only": int(g[ev & ~fv]["ticker"].nunique()),
            "distinct_names_wp0_only": int(g[~ev & fv]["ticker"].nunique()),
        }
    return out


# ── stage 4 — board incidence with explicit censoring ─────────────────────────


def incidence(mm: pd.DataFrame) -> "OrderedDict":
    out: "OrderedDict[str, dict]" = OrderedDict()
    for s in STREAM_ORDER:
        g = mm[mm["board_definition"] == s]
        per_h: "OrderedDict[str, dict]" = OrderedDict()
        dist = g["dist_next_board"].to_numpy(np.int64)
        for H in HORIZONS:
            ok = g[f"win_ok_{H}"].to_numpy(bool)
            hit = (dist >= 1) & (dist <= H)
            complete_miss = (~hit) & ok
            censored = (~hit) & (~ok)
            eps = g[hit][["date", "ticker", "dist_next_board"]]
            per_h[f"H{H}"] = {
                "picks": int(len(g)),
                "board_within_H": int(hit.sum()),
                "no_board_window_complete": int(complete_miss.sum()),
                "censored_no_board_yet": int(censored.sum()),
                "distinct_names_with_board": int(g[hit]["ticker"].nunique()),
                "wp0_fb_flag_count": int(g[f"fb_{H}"].to_numpy(bool).sum()),
                "wp0_win_ok_count": int(ok.sum()),
                "episodes": sorted(
                    f"{t} @ {str(pd.Timestamp(x).date())} (+{int(d)} sessions)"
                    for x, t, d in zip(eps["date"], eps["ticker"],
                                       eps["dist_next_board"])),
            }
        cold = g["wp0_cold"].to_numpy(bool)
        cold_h: "OrderedDict[str, dict]" = OrderedDict()
        for H in HORIZONS:
            ok = g[f"win_ok_{H}"].to_numpy(bool)
            hit = (dist >= 1) & (dist <= H)
            cold_h[f"H{H}"] = {
                "cold_picks": int(cold.sum()),
                "board_within_H": int((cold & hit).sum()),
                "no_board_window_complete": int((cold & ~hit & ok).sum()),
                "censored_no_board_yet": int((cold & ~hit & ~ok).sum()),
            }
        out[s] = {
            "picks": int(len(g)),
            "sessions": int(g["date"].nunique()),
            "distinct_names": int(g["ticker"].nunique()),
            "frozen": s == FROZEN_STREAM,
            "frozen_note": FROZEN_STREAM_FACT if s == FROZEN_STREAM else None,
            "any_pick": per_h,
            "cold_at_pick_first_board": cold_h,
        }
    return out


# ── stage 5 — same-day board vs candidates contradiction (reported, not reconciled) ──


def contradictions(mm: pd.DataFrame, cand: pd.DataFrame) -> "OrderedDict":
    c = cand.rename(columns={"stamp_date": "date"})
    j = mm.merge(c[["date", "ticker", "board_definition", "score_rank", "raw_eligible",
                    "buyable", "gate_reason"]],
                 on=["date", "ticker", "board_definition"], how="left",
                 suffixes=("", "_cand"), indicator=True)
    out: "OrderedDict[str, dict]" = OrderedDict()
    for s in STREAM_ORDER:
        g = j[j["board_definition"] == s]
        both = g[g["_merge"] == "both"]
        blocked = both[~both["buyable"].fillna(True).astype(bool)]
        reasons = (blocked["gate_reason"].astype("string").fillna("(none)")
                   .value_counts().to_dict())
        out[s] = {
            "board_rows": int(len(g)),
            "sessions": int(g["date"].nunique()),
            "distinct_names": int(g["ticker"].nunique()),
            "matched_in_candidates": int(len(both)),
            "absent_from_candidates": int((g["_merge"] == "left_only").sum()),
            "surfaced_but_not_buyable": int(len(blocked)),
            "distinct_names_surfaced_but_not_buyable": int(blocked["ticker"].nunique()),
            "gate_reason_counts": {str(k): int(v) for k, v in
                                   sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))},
            "contradiction_test_evaluable": bool(len(both)),
            "not_evaluable_reason": (
                None if len(both) else
                "the candidates ledger carries no rows under this board_definition, and "
                "joining across definitions would be the pooling the charter forbids"),
            "frozen": s == FROZEN_STREAM,
            "frozen_note": FROZEN_STREAM_FACT if s == FROZEN_STREAM else None,
            "note": ("Reported per stream and NOT reconciled — the write path owns this "
                     "disagreement (charter term 5)."),
        }
    return out


# ── stage 6 — the worked example ──────────────────────────────────────────────


def worked_example(board: pd.DataFrame, cand: pd.DataFrame, mm: pd.DataFrame,
                   panel: pd.DataFrame) -> dict:
    t, d = WORKED_EXAMPLE_TICKER, WORKED_EXAMPLE_DATE
    b = board[(board["ticker"] == t) & (board["date"] == d)]
    row = mm[(mm["ticker"] == t) & (mm["date"] == d)]
    cs = cand[cand["ticker"] == t].sort_values("stamp_date")
    same_day = cs[cs["stamp_date"] == d]
    pr = panel[(panel["ticker"] == t) & (panel["date"] >= d)].sort_values("date")

    board_row = None
    if len(b):
        r = b.iloc[0]
        board_row = {
            "date": str(d.date()), "ticker": t,
            "board_definition": str(r["board_definition"]),
            "board_rank": int(r["board_rank"]), "lane": str(r["lane"]),
            "tier": str(r["tier"]), "prophet_score": _r(r["prophet_score"], 2),
            "washout": bool(r["washout"]), "washout_2w": _r(r["washout_2w"], 2),
            "species_id": str(r["species_id"]),
            "prophet_bottom_quality": _r(r["prophet_bottom_quality"], 2),
            "hold_state": str(r["hold_state"]),
            "own_market_regime": str(r["own_market_regime"]),
        }
    cand_row = None
    if len(same_day):
        r = same_day.iloc[0]
        cand_row = {
            "stamp_date": str(d.date()), "ticker": t,
            "board_definition": str(r["board_definition"]),
            "score_rank": int(r["score_rank"]), "prophet_score": _r(r["prophet_score"], 2),
            "raw_eligible": bool(r["raw_eligible"]), "buyable": bool(r["buyable"]),
            "gate_reason": str(r["gate_reason"]), "gate_state": str(r["gate_state"]),
        }
    fps = None
    if len(row):
        r = row.iloc[0]
        fps = OrderedDict([
            ("dd250", _r(r["dd250"], 4)), ("dd_band", str(r["dd_band"])),
            ("under_ma200", bool(r["under_ma"])), ("below_band", str(r["below_band"])),
            ("sector", str(r["sector"])), ("sect35_band", str(r["sect35_band"])),
            ("sect_deep35_pct", _r(r["sect_deep35_pct"], 2)),
            ("quiet_base", bool(r["base_flag"])),
            ("confluence_long", bool(r["s1_3d_long"])),
            ("confluence_cb_recent", bool(r["s1_3d_cb_recent"])),
            ("cold_at_pick", bool(r["cold"])),
            ("dist_next_board_sessions", int(r["dist_next_board"])),
            ("fwd_bars_available", int(r["fwd_bars_available"])),
        ])
        for H in HORIZONS:
            dn = int(r["dist_next_board"])
            hit = 1 <= dn <= H
            fps[f"H{H}_status"] = ("board_within_H" if hit else
                                   ("no_board_window_complete" if bool(r[f"win_ok_{H}"])
                                    else "censored_no_board_yet"))
            fps[f"H{H}_wp0_fb_flag"] = bool(r[f"fb_{H}"])
            fps[f"H{H}_wp0_win_ok"] = bool(r[f"win_ok_{H}"])
    forward = [{"date": str(pd.Timestamp(x).date()), "tolerant_board": bool(l),
                "dd250": _r(dd, 4), "under_ma200": bool(u)}
               for x, l, dd, u in zip(pr["date"], pr["lu"], pr["dd250"], pr["under_ma"])]
    decay = [{"stamp_date": str(pd.Timestamp(x).date()),
              "board_definition": str(bd), "score_rank": int(sr),
              "prophet_score": _r(ps, 2), "buyable": bool(bu), "gate_reason": str(gr)}
             for x, bd, sr, ps, bu, gr in zip(
                 cs["stamp_date"], cs["board_definition"], cs["score_rank"],
                 cs["prophet_score"], cs["buyable"], cs["gate_reason"])]
    return {
        "ticker": t, "pick_date": str(d.date()),
        "board_row": board_row,
        "candidates_row_same_session": cand_row,
        "wp0_footprints_at_pick": fps,
        "forward_tape_from_pick": forward,
        "candidates_trajectory": decay,
        "reading": (
            "The washout-species lane surfaced the name at board rank 1 on the same "
            "session that the buyability gate blocked it for being a counter-trend name "
            "with no 200-day reclaim. Both statements are the ledger's own; P-A1 reports "
            "them side by side and reconciles neither."),
    }


# ── stage 7 — verify battery (every check carries a mutation probe) ───────────


def _probe(fn, mutate, label):
    """Run `fn` on mutated input; the check is a defect unless the mutation is DETECTED."""
    try:
        passed, _ = fn(mutate())
    except Exception as exc:  # noqa: BLE001
        return {"mutation": label, "detected": True, "via": f"raised {type(exc).__name__}"}
    return {"mutation": label, "detected": (not passed), "via": "check returned failure"}


def verify_battery(w1, w1_sha, board, cand, panel, mm, missing, agree, inc) -> dict:
    checks: "OrderedDict[str, dict]" = OrderedDict()

    # (e) quarantined columns — proof on every loaded frame
    def _quar(frames):
        bad = {}
        for name, cols in frames.items():
            hit = sorted(set(cols) & set(QUARANTINED))
            if hit:
                bad[name] = hit
        return (not bad), {"violations": bad}
    frames_real = {"board": list(board.columns), "candidates": list(cand.columns),
                   "footprint_panel": list(panel.columns),
                   "joined": list(mm.columns)}
    ok, det = _quar(frames_real)
    checks["quarantined_columns"] = {
        "why": ("charter term 3 — the dividend-adjusted forward/terminal columns and "
                "`level` must never be materialised by this instrument"),
        "passed": ok, "detail": det,
        "quarantined": list(QUARANTINED),
        "mutation_probe": _probe(
            _quar, lambda: {**frames_real, "board": list(board.columns) + ["fwd_mfe_5"]},
            "inject fwd_mfe_5 into the board frame's column list"),
    }

    # (c) keep-first key verification on BOTH parquets
    def _keys(pair):
        b, c = pair
        b_dt = b.duplicated(["date", "ticker", "board_definition"]).sum()
        c_dt = c.duplicated(["stamp_date", "ticker", "board_definition"]).sum()
        coll = b[b.duplicated(["date", "ticker"], keep=False)]
        return (b_dt == 0 and c_dt == 0), {
            "board_dupes_on_effective_key": int(b_dt),
            "candidates_dupes_on_effective_key": int(c_dt),
            "board_effective_key": ["date", "ticker", "board_definition"],
            "candidates_effective_key": ["stamp_date", "ticker", "board_definition"],
            "board_dupes_on_date_ticker_only": int(
                b.duplicated(["date", "ticker"]).sum()),
            "same_day_cross_definition_collisions": sorted(
                f"{t} @ {str(pd.Timestamp(x).date())} :: " + " + ".join(
                    sorted(coll[(coll['ticker'] == t) & (coll['date'] == x)]
                           ['board_definition'].astype(str)))
                for x, t in {(x, t) for x, t in zip(coll["date"], coll["ticker"])}),
            "collision_resolution": (
                "(date, ticker) is NOT the key — the same ticker legitimately appears on "
                "one session under two definitions, each carrying its own rank. P-A1 "
                "never de-duplicates across definitions: a collision row is counted once "
                "inside EACH of its own streams and never pooled."),
        }
    ok, det = _keys((board, cand))
    checks["keep_first_key"] = {
        "why": "charter term 2 — verify and STAMP the effective key before using any row",
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _keys, lambda: (pd.concat([board, board.iloc[[0]]], ignore_index=True), cand),
            "duplicate one board row on its full effective key"),
    }

    # (a) PIT availability of every footprint at every pick date.
    #     A pick with no footprint is only acceptable when W-P0's OWN pinned gate declined
    #     to measure it. Every exception must classify into one of those gates; an
    #     unexplained hole is a silent data gap and fails the check.
    st_set, _st_note = w1.load_st_cohort()

    def _classify_missing(t, d):
        f = RAW_DIR / f"{t}.parquet"
        if not f.exists():
            return "raw_file_absent"
        if t in st_set:
            return "st_cohort_excluded_by_w1"
        try:
            raw = pd.read_parquet(f)
        except Exception:  # noqa: BLE001
            return "raw_file_unreadable"
        if len(raw) < W1_MIN_HISTORY_BARS:
            return f"below_w1_min_history_{W1_MIN_HISTORY_BARS}_bars(n={len(raw)})"
        if pd.Timestamp(d) not in pd.DatetimeIndex(raw.index):
            return "no_raw_bar_on_pick_date"
        return "UNEXPLAINED"

    def _pit(pair):
        m, miss = pair
        holes = {}
        for f in FOOTPRINTS:
            na = int(m[f].isna().sum())
            if na:
                holes[f] = na
        bandna = {c: int((m[c].astype("string") == "na").sum())
                  for c in ("dd_band", "below_band", "sect35_band")
                  if int((m[c].astype("string") == "na").sum())}
        classified = sorted(
            f"{t} @ {str(pd.Timestamp(x).date())} [{s}] :: {_classify_missing(t, x)}"
            for x, t, s in zip(miss["date"], miss["ticker"], miss["board_definition"]))
        unexplained = [c for c in classified if c.endswith("UNEXPLAINED")]
        return (not unexplained and not holes), {
            "board_rows_total": int(len(m) + len(miss)),
            "board_rows_with_footprints": int(len(m)),
            "board_rows_without_footprints": int(len(miss)),
            "unexplained_holes": len(unexplained),
            "footprint_nulls": holes,
            "band_na_counts": bandna,
            "missing_episodes_classified": classified,
            "rule": ("PASS requires zero null footprints on measured picks AND that every "
                     "unmeasured pick classify into a W-P0 gate — not merely that few "
                     "are missing."),
        }
    ok, det = _pit((mm, missing))
    checks["pit_footprint_availability"] = {
        "why": ("charter sec.5(2a) — every pinned footprint must be computable from bars "
                "available AT the pick date, for every pick, or the exception must be "
                "W-P0's own gate declining to measure"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _pit, lambda: (mm, pd.concat([missing, mm.iloc[[0]][
                ["date", "ticker", "board_definition", "board_rank"]]],
                ignore_index=True)),
            "declare a pick on a full-history name as having no footprint "
            "(must classify UNEXPLAINED)"),
    }

    # (b) detector cross-check vs the zt pool, on shared dates only
    zt = pd.read_parquet(ZT_P, columns=["ticker", "date", "consec_boards"])
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
            "shared_dates": len(shared),
            "zt_rows_on_shared_dates": int(len(Z)),
            "zt_pairs_inside_footprint_universe": len(zin),
            "detector_boards_on_shared_dates": int(len(det_set)),
            "agree": len(agree_),
            "zt_only_detector_missed": len(miss_),
            "recall_pct": _r(100.0 * recall, 2),
            "missed_episodes": sorted(f"{t} @ {str(pd.Timestamp(d).date())}"
                                      for t, d in miss_),
        }
    lu_real = P["lu"].to_numpy(bool)
    ok, det = _det(lu_real)
    det["detector_only_not_in_zt"] = len(
        set(zip(P["ticker"][lu_real], P["date"][lu_real])) - zin)
    det["note"] = (
        "One-directional by construction. `china_zt_pool` is a PARTIAL vendor pool (its "
        "`asof` postdates its `date`), so this measures the detector's RECALL on the "
        "pool's own rows and is NOT a precision test — a detector board absent from the "
        "pool is not evidence of a false positive.")

    def _mutate_detector():
        f = lu_real.copy()
        on = np.flatnonzero(f)
        f[on[:max(1, on.size // 20)]] = False
        return f
    checks["detector_vs_zt_pool"] = {
        "why": "charter sec.5(2b) — cross-check the tolerant detector where coverage overlaps",
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _det, _mutate_detector,
            "switch off 5% of the detector's board flags"),
    }

    # (d) definition-stream disjointness of every output table
    def _disjoint(tables):
        bad = {}
        for name, keys in tables.items():
            ks = list(keys)
            if sorted(ks) != sorted(set(ks)):
                bad[name] = "duplicate stream key"
            extra = sorted(set(ks) - set(STREAM_ORDER))
            if extra:
                bad[name] = f"non-stream key(s): {extra}"
        rows_by_stream = {s: int((mm["board_definition"] == s).sum())
                          for s in STREAM_ORDER}
        if sum(rows_by_stream.values()) != len(mm):
            bad["partition"] = "per-stream row counts do not sum to the joined total"
        return (not bad), {"violations": bad, "rows_by_stream": rows_by_stream,
                           "joined_rows": int(len(mm))}
    tabs = {"agreement_matrix": list(agree), "incidence": list(inc)}
    ok, det = _disjoint(tabs)
    checks["definition_stream_disjointness"] = {
        "why": ("charter term 2 — a board_definition is a different instrument; no output "
                "table may pool streams or carry a pooled key"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _disjoint, lambda: {**tabs, "agreement_matrix": list(agree) + ["ALL_STREAMS"]},
            "add a pooled 'ALL_STREAMS' key to an output table"),
    }

    # (f) window extension is a no-op on the limit-width rules, and the store reaches it
    def _win(end):
        boards = ("main", "chinext", "star")
        moved = {b: [w1.limit_width_for_date(b, pd.Timestamp("2026-08-07")),
                     w1.limit_width_for_date(b, end)]
                 for b in boards
                 if w1.limit_width_for_date(b, pd.Timestamp("2026-08-07"))
                 != w1.limit_width_for_date(b, end)}
        reach = pd.Timestamp(panel["date"].max())
        return (not moved and reach == PANEL_WINDOW_END), {
            "wp0_audit_edge": "2026-08-07",
            "pa1_edge": str(pd.Timestamp(end).date()),
            "limit_width_rules_that_moved": moved,
            "panel_last_session": str(reach.date()),
        }
    ok, det = _win(PANEL_WINDOW_END)
    checks["window_extension"] = {
        "why": ("declared deviation 1 — P-A1 evaluates picks made after W-P0's audit edge, "
                "so the edge is extended; this proves the extension moves no width rule"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _win, lambda: pd.Timestamp("2019-01-01"),
            "move the edge across a real limit-width rule change (2019)"),
    }

    # (g) STOP-SHIP reference scan. Source only at this stage; main() re-runs it over the
    # emitted writeup as well and overwrites this result before either receipt is written.
    self_src = Path(__file__).read_text()
    scan_targets = {"pa1_panel_read.py": self_src}
    ok, det = stop_ship_scan(scan_targets)
    checks["stop_ship_reference_scan"] = {
        "why": ("charter sec.5(4) — DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT; zero references "
                "to withdrawn artifacts, grep-verified in the receipt"),
        "passed": ok, "detail": det,
        "ruling_cited": "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT",
        "mutation_probe": _probe(
            stop_ship_scan,
            lambda: {**scan_targets,
                     "synthetic": f"this sentence cites {WITHDRAWN_TOKENS[6]} table 3"},
            "introduce a withdrawn-artifact reference into a scanned surface"),
    }

    # (i) the pin itself resolves — every cited W-P0 line still holds its symbol
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
        "why": ("charter sec.5(1) — the pin must name real source lines. A W-P0 edit that "
                "shifts them would otherwise rot this module's pin comment silently"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _pin, lambda: {**PIN_SYMBOLS,
                           "build_panel": (PIN_SYMBOLS["build_panel"][0] + 5,
                                           PIN_SYMBOLS["build_panel"][1])},
            "shift a pinned line number by +5 (simulates a W-P0 edit above it)"),
    }

    # (h) the trim is output-only — footprints are computed on each name's FULL series
    def _trim(sample):
        t, d = sample
        raw = pd.read_parquet(RAW_DIR / f"{t}.parquet")
        bars_before = int((raw.index < PANEL_WINDOW_START).sum())
        row = panel[(panel["ticker"] == t) & (panel["date"] == d)]
        finite = bool(len(row) and np.isfinite(float(row["dd250"].iloc[0])))
        # a 250-session high cannot be finite from a window that holds < 200 bars
        return (bars_before >= w1.DD_MINP and finite), {
            "probe_name": t, "probe_date": str(pd.Timestamp(d).date()),
            "bars_before_window_start": bars_before,
            "dd250_finite_at_probe": finite,
            "dd_minp_required": int(w1.DD_MINP),
        }
    ok, det = _trim((WORKED_EXAMPLE_TICKER, WORKED_EXAMPLE_DATE))
    checks["window_trim_is_output_only"] = {
        "why": ("declared deviation 2 — the output trim must not truncate any rolling "
                "footprint; a finite 250-session drawdown inside a 3-month window proves "
                "the lookback ran on the full series"),
        "passed": ok, "detail": det,
        "mutation_probe": _probe(
            _trim, lambda: (WORKED_EXAMPLE_TICKER, pd.Timestamp("1999-01-04")),
            "probe a date with no panel row (no footprint can be proven finite)"),
    }

    n_pass = sum(1 for c in checks.values() if c["passed"])
    n_probe = sum(1 for c in checks.values() if c["mutation_probe"]["detected"])
    return {
        "checks": checks,
        "summary": {
            "checks_run": len(checks), "checks_passed": n_pass,
            "mutation_probes_detected": n_probe,
            "all_passed": n_pass == len(checks),
            "all_probes_detected": n_probe == len(checks),
        },
        "doctrine": ("A check that cannot fail is a defect. Every check above is paired "
                     "with a mutation that it MUST detect; `detected: false` anywhere "
                     "means the check is vacuous and the run is not evidence."),
    }


# ── stage 8 — receipts ────────────────────────────────────────────────────────


def build_vintage(w1_sha: str) -> dict:
    v = {
        "base_sha": _git("merge-base", "HEAD", "origin/main"),
        "build_head_sha": _git("rev-parse", "HEAD"),
        "board_store_commit": _git("log", "-1", "--format=%H", "--",
                                   "data/china_standout_track/board.parquet"),
        "candidates_store_commit": _git("log", "-1", "--format=%H", "--",
                                        "data/china_prophet_rank/candidates.parquet"),
        "raw_store_commit": _git("log", "-1", "--format=%H", "--",
                                 "data/china_stocks_raw"),
        "zt_pool_commit": _git("log", "-1", "--format=%H", "--",
                               "data/china_zt_pool/pool.parquet"),
        "w1_pin_commit": _git("log", "-1", "--format=%H", "--",
                              "research/cn_prophet_audit/washout_onset_w1.py"),
        "w1_sha256": w1_sha,
    }
    return v


AMENDMENTS = [
    {"id": "A1", "what": "Forward evaluation edge extended from W-P0's 2026-08-07 audit "
                         "edge to 2026-08-11.",
     "why": "P-A1 must read picks made on 2026-08-10 and 2026-08-11, which lie beyond "
            "W-P0's edge. The store reaches 2026-08-11.",
     "risk_controlled_by": "verify.window_extension — proves no limit-width rule differs "
                           "between the two edges and that the store actually reaches the "
                           "new one. No footprint definition is touched."},
    {"id": "A2", "what": "Panel OUTPUT rows trimmed to sessions on/after 2026-05-01.",
     "why": "P-A1 needs the full market cross-section only on and around the 27 panel "
            "sessions; carrying 15 years of rows would cost memory and change nothing.",
     "risk_controlled_by": "verify.window_trim_is_output_only — W-P0 computes every "
                           "rolling footprint on each name's FULL series before applying "
                           "this filter, so the trim cannot move a value; a finite "
                           "250-session drawdown inside the trimmed frame proves it."},
    {"id": "A3", "what": "Chips (S5b winner/trajectory) join skipped — attach_conditioners "
                         "is called with chips=None.",
     "why": "The charter's footprint list is washout / confluence / sector. S5b is neither "
            "and is not read anywhere in this artifact.",
     "risk_controlled_by": "W-P0's own None branch sets the S5b bands to 'na'; no S5b "
                           "column appears in any table here."},
    {"id": "A4", "what": "Board incidence is reported as a three-way censoring status "
                         "alongside W-P0's own fb_H flag, rather than as fb_H alone.",
     "why": "fb_H requires win_ok_H, so a board that DID occur inside an incomplete "
            "window reads as False. On the worked example that would have turned an "
            "observed board into a null.",
     "risk_controlled_by": "The trichotomy reads only W-P0's own `lu` flags (an index scan "
                           "over an already-computed detector output, not a second "
                           "detector), and W-P0's fb_H / win_ok_H counts are printed "
                           "beside it in every table."},
]

BASIS_AND_RULING = (
    "The tolerant detector runs on `data/china_stocks_raw`, which is BACK-ADJUSTED "
    "(W-P0's BASIS NOTE) — so this artifact states its basis rather than implying an "
    "exchange-exact one. `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` withdrew the "
    "adjusted-plane limit tape and its descendants from AUTHORITY: nothing derived from "
    "that plane may be graded, ranked, gated, sized, alerted, traded, promoted, or shown "
    "as a current probability. P-A1 does none of those things — it is a display-tier "
    "count of ledger rows and detector events, the charter's own mandated construction "
    "(term 4: re-derive board outcomes from `china_stocks_raw` with the tolerant "
    "detector, the W-P0 pattern). The residual cost of the basis is not hidden: it is "
    "MEASURED in `verify.detector_vs_zt_pool` and both misses are named. The reopen path "
    "to authority-tier limit work is unchanged and this artifact makes no claim to be on "
    "it: that requires the unadjusted vendor plane with integer-cent equality and "
    "exchange half-up validation, per the ruling's own reopen terms."
)

DOES_NOT_ESTABLISH = [
    "NO selection skill. That the panel's names carry a footprint, or that some later "
    "printed a board, says nothing about whether the panel SELECTED them well. This "
    "artifact contains no comparison against any non-panel baseline — not the market, "
    "not a matched cohort, not a random draw of names with the same footprints. Without "
    "a comparison arm, an incidence count is a description of the panel and nothing more.",
    "NO lift, no significance, no interval, no effect size. None is computed, and none "
    "may be inferred by dividing two numbers in this file. The panel is 27 sessions of a "
    "single era, entirely in-sample of the current regime; the genesis stream is frozen "
    "at 5 sessions. Those honest-Ns cannot support inference and the charter forbids "
    "attempting it until the P-A2 accrual gate opens (>=120 sessions AND >=2 regime "
    "segments on a SINGLE stream).",
    "NO cross-stream comparison. The five definitions are five instruments. That one "
    "stream shows more of something than another is a statement about two different "
    "measuring devices observed over different, short, non-overlapping windows.",
    "NOTHING about the withdrawn W1-W3 constructions. This artifact cites no number and "
    "no artifact from them (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT; grep-verified in "
    "verify.stop_ship_reference_scan).",
    "NO price or return claim for any named episode, including the worked example. Board "
    "incidence here is an EVENT count from the tolerant detector; the case study's "
    "price/return claims remain withdrawn under their own stamp.",
    "NO resolution of the two ledgers' disagreement. Where the board surfaced a name the "
    "gate blocked, both readings are printed and neither is corrected. The write path "
    "owns that defect.",
    "NO extrapolation beyond the survivor slice. The footprint plane is W-P0's curated "
    "large-cap survivors; delisted names are absent from it, so every count here is "
    "measured on names that lived.",
    "NO claim that a footprint CAUSES a board, in either direction, and no claim that the "
    "engine's stamp or the W-P0 footprint is the correct one where they diverge. "
    "Divergence is reported as data.",
]


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def fmt_names(lst, cap=40):
    if not lst:
        return "_none_"
    if len(lst) <= cap:
        return ", ".join(f"`{x}`" for x in lst)
    return (", ".join(f"`{x}`" for x in lst[:cap])
            + f" … (+{len(lst) - cap} more; full list in the JSON receipt)")


def build_md(p: dict) -> str:
    S = p["streams"]
    A = p["agreement_matrix"]
    I = p["incidence"]
    C = p["contradictions"]
    W = p["worked_example"]
    V = p["verify"]
    L = []
    ap = L.append
    ap(f"# P-A1 — descriptive read of the Prophet pick panel ({ARTIFACT_DATE})")
    ap("")
    ap(f"Authority: `none_research_display_only`. Tier: {TIER_STAMP}.")
    ap("")
    ap("Counts and episode lists only. **No lift, no t-statistic, no interval, no "
       "inference row appears anywhere in this artifact** — by charter, because the panel "
       "is 27 sessions of one era with a frozen genesis stream. The inference battery "
       "(P-A2) is accrual-gated at >=120 sessions AND >=2 regime segments on a single "
       "stream; partial peeks are forbidden.")
    ap("")
    ap("Governing ruling: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`. Spec: "
       "`P_A_PANEL_CHARTER_2026-08-11.md`. Pinned definitions: `washout_onset_w1.py` "
       "(W-P0), imported — not re-derived.")
    ap("")
    ap("---")
    ap("")
    ap("## 1. What was read")
    ap("")
    ap("Two in-repo point-in-time ledgers, read-only, through an explicit column "
       "allowlist. The quarantined columns (`fwd_mfe_*`, `terminal_state_*`, "
       "`post_cushion_breach`, `level`) are **never materialised** — they run on the "
       "dividend-adjusted plane and are not evidence here. Board outcomes are re-derived "
       "from `data/china_stocks_raw` with W-P0's own tolerant detector.")
    ap("")
    rows = []
    for s in STREAM_ORDER:
        m = S[s]
        rows.append([f"`{s}`" + (" **(frozen)**" if m["frozen"] else ""),
                     m["board_sessions"], m["board_rows"], m["board_distinct_names"],
                     " → ".join(m["board_span"]) if m["board_span"] else "—",
                     m["candidates_rows"] or "—"])
    ap(md_table(["definition stream", "board sessions", "board rows",
                 "distinct names (honest-N)", "span", "candidates rows"], rows))
    ap("")
    ap(f"**`{FROZEN_STREAM}` is {FROZEN_STREAM_FACT}** This fact is repeated beside every "
       "table below in which it appears; its five sessions are not a small sample of an "
       "ongoing process, they are the whole of it.")
    ap("")
    ap("Streams are never pooled. Each is a different instrument observed over a "
       "different, short window.")
    ap("")
    ap("**Basis, and the standing ruling.** " + BASIS_AND_RULING)
    ap("")
    ap("## 2. Footprint presence at pick time — the agreement matrix")
    ap("")
    ap("For every board row, W-P0's pinned footprints are re-derived from bars available "
       "at that pick date and crossed with the ledger writer's own stamps. Counts are "
       "row counts within the stream. `engine only` = the writer stamped it and the W-P0 "
       "footprint did not; `W-P0 only` = the reverse.")
    ap("")
    pit = V["checks"]["pit_footprint_availability"]["detail"]
    ap(f"Footprint availability: **{pit['board_rows_with_footprints']} of "
       f"{pit['board_rows_total']}** board rows carry a full footprint set at their own "
       f"pick date. The {pit['board_rows_without_footprints']} without one are named in "
       "§6.")
    ap("")
    for s in STREAM_ORDER:
        a = A[s]
        ap(f"### `{s}`" + (" — **FROZEN STREAM**" if a["frozen"] else ""))
        ap("")
        ap(f"honest-N: **{a['sessions']} sessions**, **{a['distinct_names']} distinct "
           f"names**, {a['rows_with_footprints']} board rows with footprints."
           + (f" {FROZEN_STREAM_FACT}" if a["frozen"] else ""))
        ap("")
        rows = []
        for key, c in a["cells"].items():
            e, f = key.split("__x__")
            rows.append([f"`{e}`", f"`{f}`", c["both_true"], c["engine_only"],
                         c["wp0_only"], c["both_false"], c["engine_true_total"],
                         c["wp0_true_total"]])
        ap(md_table(["engine stamp", "W-P0 footprint", "both", "engine only", "W-P0 only",
                     "neither", "engine true (all)", "W-P0 true (all)"], rows))
        ap("")
    ap("### Divergent names — `washout` (engine) vs `dd250 <= -20%` (W-P0)")
    ap("")
    ap("Divergence is data, not error. The two notions are not the same measurement: the "
       "writer's flag is a composite state stamp, W-P0's is a drawdown depth off the "
       "250-session high.")
    ap("")
    D = p["divergent_names"]
    for s in STREAM_ORDER:
        d = D[s]
        ap(f"**`{s}`**" + (" (frozen)" if s == FROZEN_STREAM else "")
           + f" — honest-N {d['sessions']} sessions / {d['distinct_names']} distinct "
             f"names / {d['rows']} rows. Engine-only "
             f"{len(d['engine_true_wp0_false'])} rows "
             f"({d['distinct_names_engine_only']} names); W-P0-only "
             f"{len(d['engine_false_wp0_true'])} rows ({d['distinct_names_wp0_only']} names).")
        ap("")
        ap(f"- engine `washout` true, W-P0 drawdown shallower than -20%: "
           f"{fmt_names(d['engine_true_wp0_false'])}")
        ap(f"- W-P0 drawdown at/below -20%, engine `washout` false: "
           f"{fmt_names(d['engine_false_wp0_true'])}")
        ap("")
    ap("## 3. First-board incidence within H ∈ {5, 10} sessions")
    ap("")
    ap("Re-derived with W-P0's tolerant detector from `china_stocks_raw` — never from an "
       "embedded column. **Right-censoring is reported, not counted as a negative:** the "
       "store ends at the panel's last session, so a pick made near the end has no "
       "complete forward window. A board observed inside an incomplete window is still an "
       "observed board; only *absence* is ambiguous there.")
    ap("")
    ap("`board within H` = a tolerant board occurred in T+1..T+H. `no board (complete)` = "
       "the window closed with none. `censored` = window still open, none yet. W-P0's own "
       "`fb_H` flag is printed beside them: it requires a complete window, so it counts "
       "only the boards in the first column whose window also closed.")
    ap("")
    for s in STREAM_ORDER:
        i = I[s]
        ap(f"### `{s}`" + (" — **FROZEN STREAM**" if i["frozen"] else ""))
        ap("")
        ap(f"honest-N: **{i['sessions']} sessions**, **{i['distinct_names']} distinct "
           f"names**, {i['picks']} picks."
           + (f" {FROZEN_STREAM_FACT}" if i["frozen"] else ""))
        ap("")
        rows = []
        for H in HORIZONS:
            a = i["any_pick"][f"H{H}"]
            c = i["cold_at_pick_first_board"][f"H{H}"]
            rows.append([f"H={H}", a["picks"], a["board_within_H"],
                         a["no_board_window_complete"], a["censored_no_board_yet"],
                         a["distinct_names_with_board"], a["wp0_fb_flag_count"],
                         f"{c['board_within_H']} / {c['cold_picks']}"])
        ap(md_table(["horizon", "picks", "board within H", "no board (complete)",
                     "censored", "distinct names w/ board", "W-P0 `fb_H`",
                     "cold-at-pick: board / picks"], rows))
        ap("")
        eps = i["any_pick"][f"H{HORIZONS[0]}"]["episodes"]
        ap(f"- episodes with a board within H={HORIZONS[0]}: {fmt_names(eps, 30)}")
        ap("")
    ap("A `cold at pick` row is one with no tolerant board in the prior 20 sessions, so a "
       "board inside the window is genuinely that name's FIRST board rather than the "
       "continuation of a run.")
    ap("")
    ap("## 4. Same-day board vs candidates — reported, never reconciled")
    ap("")
    ap("The two ledgers disagree by construction on some sessions: the board surfaces a "
       "name the buyability gate blocks. This is a known, formally flagged defect of the "
       "WRITE path. P-A1 prints both readings per stream and corrects neither.")
    ap("")
    ap("The candidates ledger carries only two definition labels — `cn_prophet_v2` and "
       "`cn_prophet_v3`. Because streams are never pooled, a board row from `legacy`, "
       "`cn_prophet_v2_shadow` or `cn_reversal_watch_v1` has no same-definition "
       "candidates row to disagree with, and the test is simply **not evaluable** on "
       "those three. Joining them to another definition's rows would be exactly the "
       "pooling this charter forbids, so it is not done.")
    ap("")
    rows = []
    for s in STREAM_ORDER:
        c = C[s]
        gr = list(c["gate_reason_counts"].items())
        cell = "; ".join(f"`{k}` ({v})" for k, v in gr[:3]) if gr else "—"
        if len(gr) > 3:
            cell += f" … (+{len(gr) - 3} more)"
        evaluable = "yes" if c["matched_in_candidates"] else "**not evaluable**"
        rows.append([f"`{s}`" + (" (frozen)" if c["frozen"] else ""),
                     f"{c['sessions']} / {c['distinct_names']}", c["board_rows"],
                     c["matched_in_candidates"], evaluable,
                     c["surfaced_but_not_buyable"],
                     c["distinct_names_surfaced_but_not_buyable"], cell])
    ap(md_table(["stream", "honest-N sessions / names", "board rows",
                 "matched in candidates", "contradiction test",
                 "surfaced but not buyable", "distinct names", "gate reasons on blocked rows"],
                rows))
    ap("")
    ap("On the two evaluable streams the contradiction is **rare but real**, and the "
       "genesis row-pair (§5) is one of its instances. Rarity is not a defence: the "
       "disagreement is between two ledgers written by the same nightly process on the "
       "same session, and P-A1 leaves it standing for the write path to own.")
    ap("")
    ap("## 5. Worked example — `300363.SZ`, pick date 2026-08-05")
    ap("")
    if W["board_row"]:
        b = W["board_row"]
        ap(f"**Board row ({b['board_definition']}, frozen stream).** rank "
           f"**{b['board_rank']}**, lane `{b['lane']}`, tier `{b['tier']}`, "
           f"prophet score {b['prophet_score']}, `washout={b['washout']}`, "
           f"`washout_2w={b['washout_2w']}`, `species_id='{b['species_id']}'`, "
           f"bottom quality {b['prophet_bottom_quality']}, "
           f"hold state `{b['hold_state']}`, regime `{b['own_market_regime']}`.")
        ap("")
    if W["candidates_row_same_session"]:
        c = W["candidates_row_same_session"]
        ap(f"**Candidates row, same session.** score rank **{c['score_rank']}**, "
           f"prophet score {c['prophet_score']}, `raw_eligible={c['raw_eligible']}`, "
           f"`buyable={c['buyable']}`, gate reason "
           f"*\"{c['gate_reason']}\"*, gate state `{c['gate_state']}`.")
        ap("")
    ap("The same session, the same name, the same writer: surfaced at board rank 1 by the "
       "washout-species lane while the buyability gate blocked it for being a "
       "counter-trend name with no 200-day reclaim. Both statements are the ledger's own. "
       "P-A1 reconciles neither.")
    ap("")
    if W["wp0_footprints_at_pick"]:
        f = W["wp0_footprints_at_pick"]
        ap("**W-P0 footprints at the pick date** (re-derived from bars available on "
           "2026-08-05):")
        ap("")
        ap(md_table(["footprint", "value"],
                    [[f"`{k}`", f"`{v}`"] for k, v in f.items()]))
        ap("")
        ap(f"The gate's prose and the footprint agree on the substance: "
           f"`under_ma200={f['under_ma200']}`, in W-P0's `{f['below_band']}` band "
           f"(61-120 consecutive sessions below the 200DMA), "
           f"{abs(f['dd250']) * 100:.1f}% off its 250-session high, in a sector where "
           f"{f['sect_deep35_pct']}% of the other members are also 35%+ down. The name "
           "was exactly what the gate said it was — which is the whole point of the "
           "row-pair: the lane surfaced it FOR the state the gate rejected it for.")
        ap("")
        st5 = f["H5_status"]
        ap(f"**Board outcome, re-derived.** The next tolerant board came "
           f"**{f['dist_next_board_sessions']} sessions** after the pick. At H=5 the "
           f"status is `{st5}`; W-P0's own `fb_5` flag reads "
           f"`{f['H5_wp0_fb_flag']}` because `win_ok_5` is "
           f"`{f['H5_wp0_win_ok']}` — only "
           f"{f['fwd_bars_available']} forward sessions exist in the store, so the "
           "5-session window never closed. **This is precisely why the trichotomy "
           "exists**: reported as `fb_5` alone, an observed board would have printed as a "
           "null.")
        ap("")
    ap("Forward tape from the pick (tolerant-detector flags only — no price or return "
       "claim is made):")
    ap("")
    ap(md_table(["date", "tolerant board", "dd250", "under 200DMA"],
                [[r["date"], r["tolerant_board"], r["dd250"], r["under_ma200"]]
                 for r in W["forward_tape_from_pick"]]))
    ap("")
    ap("The candidates ledger's own trajectory for the name across the following "
       "sessions, including its migration to the `cn_prophet_v3` definition:")
    ap("")
    ap(md_table(["stamp date", "definition", "score rank", "prophet score", "buyable",
                 "gate reason"],
                [[r["stamp_date"], f"`{r['board_definition']}`", r["score_rank"],
                  r["prophet_score"], r["buyable"], r["gate_reason"]]
                 for r in W["candidates_trajectory"]]))
    ap("")
    ap("## 6. Verification")
    ap("")
    sm = V["summary"]
    ap(f"**{sm['checks_passed']} of {sm['checks_run']} checks passed; "
       f"{sm['mutation_probes_detected']} of {sm['checks_run']} mutation probes "
       f"detected their mutation.**")
    ap("")
    ap(f"_{V['doctrine']}_")
    ap("")
    rows = []
    for name, c in V["checks"].items():
        rows.append([f"`{name}`", "pass" if c["passed"] else "**FAIL**",
                     "detected" if c["mutation_probe"]["detected"] else "**VACUOUS**",
                     c["mutation_probe"]["mutation"]])
    ap(md_table(["check", "result", "mutation probe", "mutation applied"], rows))
    ap("")
    d = V["checks"]["detector_vs_zt_pool"]["detail"]
    ap(f"**Detector cross-check.** On the {d['shared_dates']} sessions where "
       f"`china_zt_pool` and the footprint plane both have coverage, "
       f"{d['zt_pairs_inside_footprint_universe']} pool rows fall inside the footprint "
       f"universe and the tolerant detector agrees on {d['agree']} of them — recall "
       f"**{d['recall_pct']}%**. The {d['zt_only_detector_missed']} misses: "
       f"{fmt_names(d['missed_episodes'])}. {d['note']}")
    ap("")
    pitd = V["checks"]["pit_footprint_availability"]["detail"]
    if pitd["missing_episodes_classified"]:
        ap(f"**Footprint availability exceptions.** "
           f"{pitd['board_rows_without_footprints']} of {pitd['board_rows_total']} board "
           f"rows have no W-P0 footprint, and every one classifies into a W-P0 gate "
           f"({pitd['unexplained_holes']} unexplained): "
           f"{fmt_names(pitd['missing_episodes_classified'])}. That is the pinned "
           "definition declining to measure a name with too little history, not a data "
           "gap — and the check fails if any exception cannot be classified, so 'few "
           "missing' is not what earns the pass.")
        ap("")
    kd = V["checks"]["keep_first_key"]["detail"]
    ap(f"**Effective keep-first key.** `board.parquet` is keyed on "
       f"`{' + '.join(kd['board_effective_key'])}` and `candidates.parquet` on "
       f"`{' + '.join(kd['candidates_effective_key'])}` — zero duplicates on either. "
       f"`(date, ticker)` alone is **not** the key: "
       f"{kd['board_dupes_on_date_ticker_only']} same-day cross-definition collision(s) "
       f"exist — {fmt_names(kd['same_day_cross_definition_collisions'])}. "
       f"{kd['collision_resolution']}")
    ap("")
    ap("## 7. What this does NOT establish")
    ap("")
    for line in DOES_NOT_ESTABLISH:
        ap(f"- {line}")
    ap("")
    ap("## 8. Amendments — every deviation declared")
    ap("")
    ap("Deviations from a bare W-P0 invocation. All mechanical; none touches the oracle "
       "math, which is imported rather than re-derived.")
    ap("")
    for a in AMENDMENTS:
        ap(f"**{a['id']} — {a['what']}**")
        ap("")
        ap(f"- why: {a['why']}")
        ap(f"- controlled by: {a['risk_controlled_by']}")
        ap("")
    ap("## 9. Provenance")
    ap("")
    v = p["vintage"]
    ap(md_table(["stamp", "value"], [[f"`{k}`", f"`{val}`"] for k, val in v.items()]))
    ap("")
    ap("Every store stamp is verified to be an ancestor of the build head before this "
       "file is written (the A4 provenance guard); a checkout that moved mid-run refuses "
       "to write rather than emit polluted provenance. Consecutive runs of this "
       "instrument are byte-identical — no wall-clock value enters either receipt.")
    ap("")
    ap(f"Pinned definitions: `washout_onset_w1.py` @ sha256 `{v['w1_sha256'][:16]}…`, "
       "imported. Inherited limits travel with the pin: the footprint plane is a curated "
       "large-cap **survivor** slice (delisted names absent), and `china_stocks_raw` is "
       "**back-adjusted**, which is the measured source of the detector's residual misses "
       "above.")
    ap("")
    return "\n".join(L) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("P-A1 — descriptive read of the Prophet pick panel", flush=True)
    w1, w1_sha = load_w1()
    print(f"  [1/7] pinned W-P0 imported  sha256={w1_sha[:16]}…", flush=True)

    board, cand = load_stores()
    streams = stream_meta(board, cand)
    print(f"  [2/7] stores loaded  board={len(board):,} rows  "
          f"candidates={len(cand):,} rows  (quarantined columns not materialised)",
          flush=True)

    panel, pmeta = build_footprint_panel(w1)
    panel = add_forward_board_distance(panel)
    panel = derive_footprints(panel)
    print(f"  [3/7] footprint plane  {pmeta['panel_rows']:,} rows  "
          f"{pmeta['panel_names']:,} names  {pmeta['panel_sessions']} sessions",
          flush=True)

    mm, missing = join_board_to_footprints(board, panel)
    mm = add_engine_stamps(mm)
    agree = agreement_matrix(mm)
    div = divergent_names(mm, "engine_washout", "wp0_washout_dd_le_m20")
    print(f"  [4/7] joined  {len(mm):,} board rows with footprints  "
          f"{len(missing)} without", flush=True)

    inc = incidence(mm)
    contra = contradictions(mm, cand)
    wex = worked_example(board, cand, mm, panel)
    print("  [5/7] incidence + contradictions + worked example built", flush=True)

    verify = verify_battery(w1, w1_sha, board, cand, panel, mm, missing, agree, inc)
    sm = verify["summary"]
    print(f"  [6/7] verify  {sm['checks_passed']}/{sm['checks_run']} passed  "
          f"{sm['mutation_probes_detected']}/{sm['checks_run']} probes detected",
          flush=True)

    if not sm["all_passed"]:
        bad = sorted(k for k, c in verify["checks"].items() if not c["passed"])
        print(f"::error title=pa1-verify-failed::P-A1 verify battery failed: "
              f"{', '.join(bad)}", flush=True)
    if not sm["all_probes_detected"]:
        bad = sorted(k for k, c in verify["checks"].items()
                     if not c["mutation_probe"]["detected"])
        print(f"::error title=pa1-vacuous-check::P-A1 mutation probe undetected "
              f"(the check cannot fail): {', '.join(bad)}", flush=True)

    pit = verify["checks"]["pit_footprint_availability"]["detail"]
    if pit["board_rows_without_footprints"]:
        print(f"::notice title=pa1-footprint-gap::{pit['board_rows_without_footprints']} "
              f"board row(s) carry no W-P0 footprint (minimum-history gate); named in the "
              f"receipt", flush=True)
    censored_total = sum(inc[s]["any_pick"][f"H{max(HORIZONS)}"]["censored_no_board_yet"]
                         for s in STREAM_ORDER)
    if censored_total:
        print(f"::notice title=pa1-right-censored::{censored_total} pick(s) are "
              f"right-censored at H={max(HORIZONS)} — reported as censored, never as "
              f"absence", flush=True)

    payload = OrderedDict([
        ("instrument", "pa1_panel_read"),
        ("wave", "CN LIMIT-MOVE ALPHA — P-A1: descriptive read of the Prophet pick panel"),
        ("artifact_date", ARTIFACT_DATE),
        ("authority", "none_research_display_only"),
        ("tier", TIER_STAMP),
        ("governing_ruling", "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT"),
        ("basis_and_ruling", BASIS_AND_RULING),
        ("charter", "research/cn_prophet_audit/P_A_PANEL_CHARTER_2026-08-11.md"),
        ("pin", {
            "source": "research/cn_prophet_audit/washout_onset_w1.py",
            "mode": "IMPORTED (module is import-safe; nothing copied, nothing re-derived)",
            "w1_sha256": w1_sha,
            "symbols": {k: f"L{ln}" for k, (ln, _n) in PIN_SYMBOLS.items()},
            "symbols_verified_by": "verify.pin_line_numbers_resolve",
            "forward_first_board_cols": "L1043-L1053 (win_ok_H / fb_H construction)",
        }),
        ("inputs", {
            "board": "data/china_standout_track/board.parquet (READ-ONLY, allowlisted)",
            "candidates": "data/china_prophet_rank/candidates.parquet (READ-ONLY, allowlisted)",
            "footprint_source": "data/china_stocks_raw (via imported W-P0 build_panel)",
            "detector_crosscheck": "data/china_zt_pool/pool.parquet",
            "board_columns_loaded": BOARD_COLS,
            "candidates_columns_loaded": CAND_COLS,
            "quarantined_never_loaded": list(QUARANTINED),
        }),
        ("footprint_definitions", {k: v for k, v in FOOTPRINTS.items()}),
        ("engine_stamp_definitions", dict(ENGINE_STAMPS)),
        ("streams", streams),
        ("footprint_plane_meta", pmeta),
        ("agreement_matrix", agree),
        ("divergent_names", div),
        ("incidence", inc),
        ("contradictions", contra),
        ("worked_example", wex),
        ("verify", verify),
        ("does_not_establish", DOES_NOT_ESTABLISH),
        ("amendments", AMENDMENTS),
        ("vintage", build_vintage(w1_sha)),
    ])

    # A4 provenance-stability guard — every path stamp must be reachable from the build
    # head, else the checkout moved mid-run and the stamps are polluted. Refuse to write.
    _head = payload["vintage"]["build_head_sha"]
    for _k in ("board_store_commit", "candidates_store_commit", "raw_store_commit",
               "zt_pool_commit", "w1_pin_commit"):
        _c = payload["vintage"][_k]
        if _c != "UNAVAILABLE" and subprocess.run(
                ["git", "merge-base", "--is-ancestor", _c, _head],
                cwd=REPO, capture_output=True).returncode != 0:
            raise SystemExit(
                f"vintage stamp {_k}={_c} is not an ancestor of build head {_head} — "
                "checkout moved mid-run; refusing to write polluted provenance")

    md = build_md(payload)

    # The STOP-SHIP scan must cover the EMITTED PROSE, not just the source that generated
    # it. Re-run it over both surfaces and record the honest two-surface result.
    final_ok, final_det = stop_ship_scan({
        "pa1_panel_read.py": Path(__file__).read_text(),
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
          f"({OUT_MD.stat().st_size / 1e3:.1f} kB)", flush=True)

    # A failing check or a vacuous one must make the RUN red, even though the receipts are
    # written — they are the diagnosis surface.
    return 0 if (sm["all_passed"] and sm["all_probes_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
