#!/usr/bin/env python3
"""Git-archaeology retro-grader + forward-accruing ledger for the US Buy Board.

WHAT THIS IS
------------
`site/factordata/us_standouts.json` is committed daily (~90 revisions back to
2026-06-16). This script reconstructs every past board from git history, grades
every row (buy / watch / leaders / laggard lanes) at matured horizons (5d, 10d, 21d, 63d)
versus SPY and versus the name's sector ETF, and writes:

  * data/us_board_ledger/retro_grades.parquet  — one row per (as_of, lane, ticker, horizon)
  * site/factordata/us_board_track.json         — aggregated hit-rate / precision@k / Wilson-CI

It ALSO runs nightly (`--nightly`): it snapshots today's committed board into an
append-only JSONL (data/us_board_ledger/snapshots.jsonl) so the ledger keeps
accruing without depending on git blob availability, and re-grades everything that
has matured. The retro (git) and forward (snapshot) sources are unioned and
de-duplicated on (as_of, ticker, lane) — retro seeds the ledger today, snapshots
carry it forward.

HONESTY CONVENTIONS (read these — they bound every claim downstream)
--------------------------------------------------------------------
* Entry fill = the NEXT session's close after the board's as_of. Boards publish in
  the evening on the as_of date, so the earliest realistic fill is the following
  session's close (next-bar realism). Horizon h return = close[entry+h] / close[entry] - 1.
  W0.1 (B-b): forward returns and MFE are now computed via engine.grading.forward_metrics
  (the one-grader law §1.2) — same next-bar convention, same window semantics.
* PRICE BASIS (corrected 2026-08-06 — this paragraph asserted something false about its
  own inputs from inception until #4698 measured it). Name prices come from
  engine.equity_factors._closes("broad") — the breadth close caches — which are RAW:
  re-based only at an infrequent full rebuild and accruing unadjusted rows after it.
  The benchmark legs (SPY, the GICS sector ETFs) are read from data/yahoo, which IS
  back-adjusted. `excess = name_ret - benchmark_ret` therefore subtracted an adjusted
  leg from an unadjusted one, booking a name's own dividend as a loss whenever its
  measurement window straddled an ex-date. Names with no in-window ex-date agreed to the
  cent across both families, which is why the defect read as noise for two months.
  Prices are now resolved ADJUSTED-FIRST through engine.price_ladder (baskets_ohlcv →
  yahoo → data_stocks → the cache, disclosed and stamped), then extended by
  engine.grading.resolve_series (which appends the 8-K Item 1.03 dead-name imputation
  store when present). Both legs now share the adjusted basis. Every row carries its own
  `price_source` + `price_basis` stamp so a future audit reads basis off the row instead
  of re-deriving it from archaeology.
* HISTORY IS NOT RESTATED. The caches are re-based IN PLACE, so the same (ticker, date)
  reads differently on different days and a re-grade silently rewrites a published
  number: measured 2026-08-06, re-running this grader against the shipped ledger moved
  75 already-graded rows, 19 materially (worst −1.94pp, LPG 2026-06-18 H5). Price-derived
  columns are now FROZEN once a row is graded (see _merge_into_store / _FROZEN_PRICE_COLS);
  annotations and new spine columns still accrue. The pre-fix era is rows whose
  price_basis is null (see data/us_board_ledger/README.md, "Price-basis era").
* Excess return = name_ret - benchmark_ret (SPY and, separately, sector ETF).
* MAE = maximum ADVERSE excursion. We only have daily CLOSES, not intraday lows, so
  this is a CLOSE-PATH MAE: min_over_window(name_cum_ret - bench_cum_ret), in EXCESS
  terms vs SPY. It UNDER-states true intraday drawdown; labelled `mae_close_excess`.
* n is reported everywhere. ~11 trading days of matured 5d data at first run is TINY.
  Daily boards + multi-day horizons overlap heavily -> serial correlation -> the
  effective independent-sample count is a fraction of n. Wilson CIs are computed on
  the RAW n and are therefore OPTIMISTICALLY narrow; treat them as lower bounds on
  uncertainty. No strong claims. See the "caveats" block in the JSON.

Survivorship: prices now route through engine.grading.resolve_series, which appends
the dead-name terminal series (data/edgar/dead_name_prices.parquet) so a delisted
name grades at its imputed terminal value instead of vanishing. n_skipped_no_price
now counts ONLY names with no price path in either the live cache OR the dead-name
store (genuinely unresolvable). Coverage note: data/edgar/dead_name_prices.parquet
must be present (populated by collectors/edgar_deadname_prices) for this fix to be
active; when the store is absent, the grader degrades to the old live-only path and
prints a coverage note in the survivorship block.

SPINE COLUMNS (W0.1 B-b — §3.4, §5.1 sub-task 2):
  fwd_mfe_{5,10,21,63}    — max favorable excursion (via grading); rows are
    per-(as_of,ticker,lane,horizon), so each row populates ONLY its own
    horizon's fwd_mfe_{h} column (the others stay null on that row)
  terminal_state_clean15_126, terminal_state_clean8_21  — per §1.1 partition
  post_cushion_breach      — per-fire flag at horizon=21 (grading primitive)
  rate_pressure, quad_hard_label, fused_risk_label, vol_regime, risk_radar_state,
  regime_vector_degraded, vector_asof, staleness_hours  — PIT regime stamp
  archetype                — board row payload at grade time, else the PIT archetype
    store (data/archetypes/history.parquet, greatest asof_date <= as_of); null when
    the store does not classify the name.  Historical rows are filled by
    _backfill_archetype at each row's own as_of (fill-null-only)
  species_id               — RETIRED 2026-08-04 (_RETIRED_LEDGER_COLS): literal None on
    every row since inception, because no species uniquely binds this ledger. No longer
    written, and dropped from the store on merge
All nullable; existing rows keep nulls (schema-union only; keep-FIRST on dedup key).
Per-column coverage starts and the mechanisms that bound them: data/us_board_ledger/README.md.

ENTRY_STATUS DISCLOSURE LAW (2026-08-04 — battery §1: 177/403 matured buy rows,
the worst-performing cell, graded entry_status=None with no cause on record):
  entry_status_reason — non-null exactly when entry_status is null on a freshly
  graded row. Values: no_cycle_ladder / short_history / gauge_error:* (the gauge
  self-gated or raised at publish, stamped by build_stock_library as
  entry_signal_null_reason on the board row), lane_not_stamped (the ran lane
  ships no gauge BY DESIGN, us_prophet_v1 §3.5), not_assessed (writer catch-all),
  unstamped_at_publish (grader fallback: the frozen snapshot/blob carries neither
  gauge nor reason — the pre-instrumentation boards 2026-06-15..17).
  PIT: the reason describes the frozen artifact being graded, never a recomputed
  label; entry_status itself is NEVER backfilled — the 06-15..17 rows stay None.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.equity_factors import _closes  # noqa: E402
from engine.price_ladder import is_adjusted as _px_is_adjusted  # noqa: E402
from engine.grading import (  # noqa: E402
    fill_index,
    forward_metrics,
    terminal_state,
    post_cushion_breach,
    resolve_series,
    load_dead_prices,
    LIFTOFF_HORIZON_21,
    LIFTOFF_HORIZON_126,
    LIFTOFF_15,
    LIFTOFF_8,
)
from engine.regime_vector import get_vector_for_date  # noqa: E402
from engine.confluence_tiers import (  # noqa: E402 — 3D StochRSI for the ledger's target exit
    _tf_bars,
    _stoch_rsi_kd,
    _to_daily,
)

BOARD_PATH = "site/factordata/us_standouts.json"
LEDGER_DIR = ROOT / "data" / "us_board_ledger"
RETRO_PARQUET = LEDGER_DIR / "retro_grades.parquet"
SNAPSHOTS_JSONL = LEDGER_DIR / "snapshots.jsonl"
#: scripts/prophet_pit_replay.py's US registry entry names this as its pending_dir
#: (masterplan research/PROPHET_PIT_REPLAY_HARNESS_V1.md §0.4, §1). Absorbed by
#: absorb_pending_replays() below, in the --nightly path only.
PENDING_REPLAY_DIR = LEDGER_DIR / "pending_replay"
TRACK_JSON = ROOT / "site" / "factordata" / "us_board_track.json"
OUTCOMES_JSON = ROOT / "site" / "factordata" / "us_board_outcomes.json"
# TRD popup: the compact buy-lane episode ledger the Track-record dialog fetches.
# NEW artifact — never move/rename OUTCOMES_JSON or TRACK_JSON (Prophet freshness pins
# us_board_outcomes.json; us_board_track.json keeps key `per_horizon`).
LEDGER_JSON = ROOT / "site" / "factordata" / "us_track_ledger.json"

# TRD popup scoring parameters. The forced-verdict horizon is the ONE number that
# decides what the headline means, so it lives here, named, not inline.
#   10 sessions ≈ two trading weeks. Measured on the US board 2026-07-26: at H=5 the
#   desk had NO edge (profit factor 0.99, expectancy −0.01%); at H=10 it had one
#   (1.61, +0.97%). H=21 was unmeasurable — the record was 24 calendar days old and no
#   episode had 21 forward bars. Revisit once the ledger carries a quarter of dates.
LEDGER_HORIZON = 10
_OB = 80.0          # 3D StochRSI overbought — engine/hold.py LAUNCHED leg
_TROUGH_LB = 90     # trough lookback for the stop — engine/hold.py TROUGH_LB
_TROUGH_TOL = 0.97  # BROKEN below trough × 0.97 — engine/hold.py TROUGH_TOL

# First board date whose definition matches the board that ships today. Earlier boards
# are real history but a DIFFERENT INSTRUMENT, and a track record is a claim about a
# specific product:
#   * 2026-06-15..06-24 published 120 names on the `buy` key against ~780 eligible —
#     a broad screen, not a selection. The 06-15 board's own labels include DOWNTREND,
#     TOPPING and ROLLING OVER names; grading those as buy calls would be grading
#     recommendations the board never made.
#   * from 2026-06-25 the lane narrows to ~30-45 names, which is what a reader sees now.
# Those 7 boards supplied 479 of 680 matured episodes — 70% of the evidence — so
# pooling them means the headline mostly describes a product nobody can follow.
#
# Note for whoever revisits this: INCLUDING the old era is the choice that makes the
# desk look better (it lifted the average-trade interval clear of zero, 0.25–1.67 vs
# −0.78–1.93). That asymmetry is the reason to leave it out, not a reason to keep it.
# The excluded count ships in meta.history so the cut is auditable, never silent.
LEDGER_HISTORY_FROM = "2026-06-25"

# The era cut, in one sentence, so every artifact that applies it says the same thing.
# ONE RULE, ONE FILE (G3 2026-08-06): emit_ledger and build_track both read it — the
# grader used to exclude the broad-screen era from the ledger and pool it into the
# track record, publishing two records over two different products from one file.
_ERA_BASIS = (
    f"boards before {LEDGER_HISTORY_FROM} published ~120 names on the buy key against "
    "~780 eligible — a broad screen, not a selection, whose own labels included "
    "DOWNTREND and TOPPING names. Grading them would grade recommendations the board "
    "never made, so they are excluded here and in the episode ledger by the same rule."
)

# SA-W5: v2 parallel lane (sibling files, ISOLATED from main lane)
# These files NEVER touch retro_grades.parquet / us_board_track.json.
# Decision: sibling files (not co-tenancy) because the v2 board schema diverges
# (dual-gate+rotation, different lanes/fields) and polluting the main store would
# corrupt the main lane's stratifications.
V2_BOARD_PATH = "site/factordata/us_standouts_v2.json"
V2_SNAPSHOTS_JSONL = LEDGER_DIR / "snapshots_v2.jsonl"
V2_RETRO_PARQUET = LEDGER_DIR / "retro_grades_v2.parquet"
V2_TRACK_JSON = ROOT / "site" / "factordata" / "us_board_track_v2.json"
# lane names in the v2 board artifact
V2_LANES = ["entry_open", "setting_up"]

# Number of board dates (not calendar days) to look back for the outcomes strip.
OUTCOMES_LOOKBACK_BOARDS = 21
# How many exited names to render in the track-record table. The summary counts
# (n_running / n_stopped / win_rate) are ALWAYS computed over the full exited set,
# not this display slice — so the header never reads "0 stopped" just because the
# biggest movers in the cap happen to be winners.
OUTCOMES_DISPLAY_CAP = 60

HORIZONS = [5, 10, 21, 63]  # W0.1 B-b: 63d lane added per §5.1 sub-task 2
# "leaders" added 2026-07-28 (gate-width order) so the leaders strip accrues its own
# forward cohort from tonight. Purely additive: both call sites read the lane with
# `d.get(lane)` / `if lane in d`, so a snapshot or git revision without the key grades
# exactly as before.
# "ran" added 2026-08-02 (us_prophet_v1) on exactly the same terms: a NEW forward
# cohort that starts accruing from ship date. Every board before tonight has no "ran"
# key, so no history is re-graded and no existing lane's series moves. The ran lane is
# display-tier by construction (no entry claim); grading it forward is how a claim
# would EVENTUALLY be earned, not a claim being made now.
# Scope: this is the LIVE-board grader only. The v2 shadow board keeps its own lane
# vocabulary in V2_LANES and its own sibling stores — untouched here.
LANES = ["buy", "watch", "leaders", "ran", "laggards", "laggard"]
K_LIST = [1, 3, 5, 10]

# GICS sector -> SPDR sector ETF (mirrors engine/ai_desk.py _GICS_ETF, plus the
# board's occasional non-canonical sector spellings).
_GICS_ETF = {
    "Energy": "XLE", "Information Technology": "XLK", "Technology": "XLK",
    "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE",
    "Communication Services": "XLC", "Communications": "XLC",
}
BENCH = "SPY"

#: PRICE-BASIS ERA BOUNDARY (2026-08-06, this PR). Rows graded before it were priced from
#: the raw breadth caches against an adjusted benchmark; rows graded after it resolve
#: adjusted-first through engine.price_ladder. Pre-boundary rows are NOT re-graded — a
#: graded row is a point-in-time claim — so the two eras are separated by the stamp
#: instead: `price_basis == PRE_ERA_BASIS` is era 1, "adjusted"/"unadjusted" is era 2.
#: Measured at the boundary: 2,277 of 2,287 shipped rows already agreed with the adjusted
#: basis to <0.01pp (the grade-time caches happened to be re-based), so era 1 is not
#: presumed wrong — it is presumed UNVERIFIED, which is the honest word.
PRICE_BASIS_ERA_BOUNDARY = "2026-08-06"
PRE_ERA_BASIS = "unverified_pre_20260806"

#: Alarm floor for the share of freshly-graded rows whose NAME leg had no adjusted
#: counterpart and fell through to the raw breadth cache. MEASURED baseline 2026-08-06:
#: 154 of 855 board-admitted tickers have no series in baskets/ohlcv, yahoo, data/stocks
#: or baskets/extras → 1,141 of 5,538 freshly-graded rows, 20.6%. That residual is real
#: and is stamped on every row it touches; the floor sits above it so the standing hole
#: is reported quietly and only a COVERAGE REGRESSION — an adjusted store that stopped
#: being written — pages anyone. Raise it only with a fresh measurement, never to silence
#: a real drop. Closing the hole means back-filling those 154 names into an adjusted
#: store; that is a collector change, not a grader change.
_UNADJUSTED_ROW_SHARE_ALARM = 0.30


# --------------------------------------------------------------------------- #
# price loading
# --------------------------------------------------------------------------- #
def _load_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (names_closes, etf_closes).

    BASIS WARNING — the two frames returned here are NOT on the same basis. `names` is
    the breadth close caches, which are UNADJUSTED (raw closes accrued forward, re-based
    only at a full rebuild); `etfs` is data/yahoo, which is back-adjusted. Differencing
    a name return against an ETF return straight off this pair books the name's own
    distribution as a loss.

    Callers MUST pass `names` through `rebase_to_adjusted()` before grading anything
    against `etfs`. main() does; `tests/test_price_basis_graders.py` fails the build if a
    production grader stops doing it. The cache frame is still the starting point because
    it defines the panel's column set and calendar, which coverage and continuity
    reporting are denominated in.
    """
    names = _closes("broad")
    names.index = pd.to_datetime(names.index)
    names = names.sort_index()

    etf_tickers = sorted(set(_GICS_ETF.values()) | {BENCH})
    cols = {}
    ypath = ROOT / "data" / "yahoo"
    for t in etf_tickers:
        p = ypath / f"{t}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            s = df["close"] if "close" in df.columns else df.iloc[:, 0]
            s.index = pd.to_datetime(s.index)
            cols[t] = s
    etfs = pd.DataFrame(cols).sort_index()
    return names, etfs


# --------------------------------------------------------------------------- #
# ROW-PERSISTENCE LAW — the price panel must cover what the board ADMITS
# --------------------------------------------------------------------------- #
# The board's universe (scripts/build_stock_library.py::universe) is a UNION of three
# sources: data/stocks deep history, the breadth close caches, and the curated
# `stock_search.extra_tickers` extras read from the yahoo store (foreign ADRs + recent
# IPOs outside the S&P 1500). Every grader here priced from ONE of them —
# engine.equity_factors._closes("broad"), i.e. the breadth caches alone — so a name the
# board admitted through the extras lane had `tk not in names.columns` and was dropped.
#
# Observed 2026-08-05 (operator report): VALE sat in the buy lane on five board dates
# 07-24..07-31, then had ZERO rows in retro_grades.parquet and never appeared in the
# Track-record dialog. It was not delisted and not stale — data/yahoo/VALE.parquet
# carried 6,131 closes through 2026-08-03. Every name on the shipped artifact's
# `tickers_skipped` list was the same class (ASTS BIDU CRDO NET NVO NXE PL RKLB TEAM U
# UROY VALE, plus LCID from the git-archaeology boards): 13 of 13 recoverable from the
# very store the board admitted them from, ZERO genuinely unresolvable.
#
# A ticker resolved here uses the SAME dividend-adjusted yahoo closes the board itself
# read, so the price convention is unchanged; this only stops the grader from pricing a
# narrower universe than the one it is grading.
def extend_prices_to_admitted(
    names: pd.DataFrame, boards: list[dict],
) -> tuple[pd.DataFrame, dict]:
    """Widen the close panel to every ticker the boards ADMITTED.

    Returns ``(names, receipt)``. The receipt records what was recovered and what is
    still unresolvable, so the survivorship disclosure is measured, never assumed.
    Additive only: a ticker already carrying a usable column is left untouched.
    """
    from lib import store

    admitted: set[str] = set()
    for b in boards or []:
        for r in b.get("rows") or []:
            tk = r.get("ticker")
            if tk:
                admitted.add(str(tk))

    have = {c for c in getattr(names, "columns", []) if names[c].notna().any()}
    dead = set(load_dead_prices().keys())
    missing = sorted(admitted - have - dead)

    # Clip recovered history to the panel's own span. The yahoo store carries decades
    # (NVO alone has 11,406 bars) and an un-clipped union index would grow the close
    # frame from 777 rows to 11,406 — ~140 MB of mostly-NaN on the 4-core render path,
    # for history no grader here reads. The breadth panel spans ~3y, which clears both
    # lookbacks this module uses (the 200-bar StochRSI floor and the 90-bar trough).
    floor = None
    if names is not None and not getattr(names, "empty", True) and len(names.index):
        floor = pd.Timestamp(names.index.min())

    recovered: dict[str, pd.Series] = {}
    for tk in missing:
        try:
            df = store.read("yahoo", tk)
        except Exception as e:  # noqa: BLE001 — one bad parquet must not kill the grade
            print(f"[prices] admitted-store read failed for {tk} ({e})", flush=True)
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        ser = pd.to_numeric(df["close"], errors="coerce").dropna()
        if ser.empty:
            continue
        ser.index = pd.to_datetime(ser.index)
        ser = ser.sort_index()
        if floor is not None:
            ser = ser[ser.index >= floor]
        if ser.empty:
            continue
        recovered[tk] = ser

    unresolved = sorted(set(missing) - set(recovered))
    receipt = {
        "n_admitted": len(admitted),
        "n_recovered_from_admitted_store": len(recovered),
        "recovered": sorted(recovered),
        "n_unresolved": len(unresolved),
        "unresolved": unresolved[:30],
    }
    if unresolved:
        # Nulls printed, not hidden: a board name with no price ANYWHERE is a real
        # survivorship hole and the operator should see it the next morning. Bare
        # line-start print — a logger would prefix the line and GitHub would drop it.
        print("::warning title=us-board-admitted-name-unpriced::"
              f"{len(unresolved)} board name(s) have no close series in any admission "
              f"source (broad cache, dead-name store, yahoo extras): "
              f"{', '.join(unresolved[:15])} — each still ships an unscored ledger row",
              flush=True)
    if not recovered:
        return names, receipt

    add = pd.DataFrame(recovered)
    if names is None or getattr(names, "empty", True):
        out = add.sort_index()
    else:
        out = pd.concat([names, add], axis=1).sort_index()
    return out.loc[:, ~out.columns.duplicated()], receipt


# --------------------------------------------------------------------------- #
# PRICE-BASIS LAW — the name leg and the benchmark leg must share one basis
# --------------------------------------------------------------------------- #
# `_load_prices` returns names from the breadth caches (UNADJUSTED) and ETFs from
# data/yahoo (ADJUSTED). `excess_spy = nret - sret` differences them, so before #4698
# every name that went ex-distribution inside a measurement window booked its own payout
# as a loss against an unaffected SPY. Receipt (2026-06-22, CFG): cache 67.9900 vs
# adjusted 67.5514 — exactly the quarterly dividend; JPM/KO, with no in-window ex-date,
# agree to the cent, which is why this read as noise.
#
# The engine already knew: engine/desk_grader.py was hardened against this same cache on
# 2026-07-04 ("the S&P-1500 breadth close cache is SPLIT-CORRUPTED") and prices yahoo-only.
# The knowledge never propagated here. It now lives in ONE place — engine.price_ladder —
# and tests/test_price_basis_graders.py fails the build if a production grader re-hand-rolls
# a cache-first ladder against an adjusted benchmark.
#
# Coverage is NOT traded for basis purity: a name with no adjusted counterpart keeps its
# cache column and is STAMPED `closes_cache_UNADJUSTED` on every row it produces, so the
# residual is measured on the artifact instead of argued about.
def rebase_to_adjusted(
    names: pd.DataFrame, boards: list[dict],
) -> tuple[pd.DataFrame, dict]:
    """Re-base every ADMITTED name's column onto the adjusted-first ladder.

    Returns ``(names, provenance)``. Only board-admitted tickers are resolved — the panel
    carries ~1,550 columns and the grader prices a few hundred of them, so resolving the
    rest would buy nothing and cost the render path a thousand parquet opens. The column
    SET and the index are preserved, so coverage denominators (`_survivorship_block`) and
    the continuity clock are unchanged; only the VALUES of graded names move.
    """
    from engine.price_ladder import overlay_adjusted

    admitted: set[str] = set()
    for b in boards or []:
        for r in b.get("rows") or []:
            tk = r.get("ticker")
            if tk:
                admitted.add(str(tk))

    # Clip to the panel's own span for the same reason extend_prices_to_admitted does:
    # baskets/ohlcv carries history to 2014 and an un-clipped union index would grow the
    # frame by an order of magnitude on the 4-core render path, for bars no grader reads.
    start = None
    if names is not None and not getattr(names, "empty", True) and len(names.index):
        start = pd.Timestamp(names.index.min())

    return overlay_adjusted(names, sorted(admitted), start=start)


# --------------------------------------------------------------------------- #
# CONTINUITY — a dead nightly must be visible the next morning
# --------------------------------------------------------------------------- #
# The forward ledger only advances in the nightly (ledger lane-gate law), so when the
# nightly dies the snapshots simply stop and everything downstream keeps publishing the
# last good record with a stale `as_of` and no complaint. That is how the 08-02/08-03
# collect failure stayed invisible until an operator noticed a name missing three days
# later. The gap is DISCLOSED, never backfilled — no snapshot is reconstructed for a
# session on which the board did not actually run.
#
# Reference clock is the benchmark ETF close (data/yahoo/SPY.parquet), which is
# refreshed by a different lane than the board. Using the board's own price source
# would be circular: a build that never ran leaves board and price frozen together and
# reads as perfectly fresh.
def continuity_block(boards: list[dict], names: pd.DataFrame,
                     etfs: pd.DataFrame | None) -> dict:
    """Staleness of the newest board snapshot against the last completed US session."""
    last_snap = boards[-1].get("as_of") if boards else None

    ref = None
    if etfs is not None and BENCH in getattr(etfs, "columns", []):
        s = etfs[BENCH].dropna()
        if not s.empty:
            ref = pd.DatetimeIndex(s.index)
    if ref is None and names is not None and not getattr(names, "empty", True):
        ref = pd.DatetimeIndex(names.index)
    if ref is None:
        return {"last_snapshot": last_snap, "last_session": None,
                "n_stale_sessions": 0, "stale_sessions": [], "clock": None}

    last_session = str(ref.max())[:10]
    stale: list[str] = []
    if last_snap:
        cut = pd.Timestamp(last_snap)
        stale = [str(d)[:10] for d in ref[ref > cut]]

    out = {
        "last_snapshot": last_snap,
        "last_session": last_session,
        "n_stale_sessions": len(stale),
        "stale_sessions": stale[:20],
        "clock": f"{BENCH} close",
    }
    if stale:
        n = len(stale)
        out["note_en"] = (
            f"No board was recorded for the {n} session{'s' if n > 1 else ''} after "
            f"{last_snap} ({stale[0]}–{stale[-1]}). Those days are left blank in the "
            "record — nothing is filled in after the fact.")
        out["note_zh"] = (
            f"{last_snap} 之后有 {n} 个交易日没有记录榜单（{stale[0]}–{stale[-1]}）。"
            "这些日子在记录中留白，事后不做补写。")
    return out


def warn_if_stale(cont: dict) -> bool:
    """Emit the line-start staleness annotation. Returns True when it fired.

    Bare ``print`` with ``flush=True`` on purpose: every logger in this repo prefixes
    the line, and GitHub silently drops a ``::warning`` that does not start the line.
    """
    n = int(cont.get("n_stale_sessions") or 0)
    if n <= 0:
        return False
    print("::warning title=us-board-ledger-stale::"
          f"newest board snapshot is {cont.get('last_snapshot')} but the last completed "
          f"US session is {cont.get('last_session')} ({n} session(s) with no board) — "
          "the nightly forward ledger did not advance; the gap is disclosed, not backfilled",
          flush=True)
    return True


# --------------------------------------------------------------------------- #
# ZERO-ACCRUAL — a grader that records nothing must say so, and say why
# --------------------------------------------------------------------------- #
# Measured outage 2026-07-31 -> 2026-08-06: the store sat at 2,282 rows for nine days
# while the step concluded `success` every night. Nothing was broken in this module —
# the breadth close caches (engine.equity_factors._closes) froze at 2026-07-31 when the
# collect lane's "data: daily collection" commit wedged, so no horizon could mature and
# the grader correctly emitted nothing. Correct, and invisible.
#
# The trap that makes a naive alarm vacuous: grade_boards re-computes EVERY matured row
# on EVERY run and _merge_into_store is keep-fresh, so `len(df)` is re-grades, not
# accrual. The nightly of 2026-08-04 printed "[grade] 1332 new matured rows this run"
# while the store went 2282 -> 2282. A zero-row alarm keyed on the fresh frame would
# never have fired through the entire outage. It must be keyed on STORE GROWTH.
def _panel_reach(names: pd.DataFrame, boards: list[dict]) -> str | None:
    """Modal last-close date across the tickers the boards actually name.

    NOT ``names.index.max()``. extend_prices_to_admitted splices in yahoo-sourced
    columns that run ahead of the breadth caches, so the frame's index max reads fresh
    while almost every column is stale — measured on origin/main 2026-08-06, index.max()
    was 2026-08-04 while 1498 of 1540 columns ended 2026-07-31. An index-level max is
    exactly the number that let this outage look healthy."""
    if names is None or getattr(names, "empty", True) or not boards:
        return None
    tickers = {r["ticker"] for b in boards for r in b["rows"] if r.get("ticker")}
    cols = [t for t in tickers if t in names.columns]
    if not cols:
        return None
    lasts = [names[c].last_valid_index() for c in cols]
    lasts = [str(d)[:10] for d in lasts if d is not None]
    if not lasts:
        return None
    return max(set(lasts), key=lasts.count)  # modal, not max


def no_accrual_reason(*, boards: list[dict], names: pd.DataFrame, cont: dict,
                      ungraded: list[str], skipped_no_price: int) -> tuple[str, str]:
    """(slug, human clause) naming WHY a nightly added no rows. Pure — no I/O.

    The benign case (weekend, or a horizon that simply has not come round yet) and the
    malignant case (the price lane died) are indistinguishable from the board's own
    panel — a build that never ran leaves board and prices frozen together and reads as
    perfectly fresh. They are told apart by the SAME independent clock continuity_block
    already uses: the benchmark ETF close, refreshed by a different lane than the board.
    Panel behind that clock = starved. Level with it = genuinely nothing to grade.

    That is also why the alarm is never suppressed on the benign branch: the two cases
    are one branch apart, so a silent 'probably just the weekend' path would re-open the
    exact hole it is here to close. The reason slug is what makes it filterable."""
    n_board_rows = sum(len(b["rows"]) for b in boards)
    reach = _panel_reach(names, boards)
    last_session = cont.get("last_session")
    if not boards:
        return ("no_boards",
                "no board could be reconstructed at all (snapshots and git history "
                "both came back empty)")
    if n_board_rows and skipped_no_price >= n_board_rows:
        return ("no_priceable_names",
                f"not one of the {n_board_rows} board rows resolved to a price series "
                "(live cache and dead-name store both missed every name)")
    if reach and last_session and reach < last_session:
        return ("price_panel_stale",
                f"the price panel's modal last close is {reach} but the last completed "
                f"session is {last_session} — no horizon can mature past a frozen panel, "
                "so the collect lane is what has to move, not this grader")
    return ("no_new_maturity",
            f"the panel is level with the session clock ({reach or 'n/a'}) and no "
            "horizon came round this run — nothing to record")


def warn_if_no_accrual(n_added: int, *, nightly: bool, boards: list[dict],
                       names: pd.DataFrame, cont: dict, ungraded: list[str],
                       skipped_no_price: int) -> bool:
    """Emit the line-start annotation when a nightly grades but records NOTHING.

    Returns True when it fired. Bare ``print`` with ``flush=True`` per the repo's
    annotation law. `n_added` is store growth, never the fresh frame's length."""
    if not nightly or n_added > 0:
        return False
    slug, why = no_accrual_reason(boards=boards, names=names, cont=cont,
                                  ungraded=ungraded, skipped_no_price=skipped_no_price)
    newest = boards[-1]["as_of"] if boards else None
    print("::warning title=us-board-ledger-no-accrual::"
          f"the nightly added 0 rows to {RETRO_PARQUET.name} [{slug}] — {why}; "
          f"newest board on file {newest}, {len(ungraded)} board date(s) still awaiting "
          f"a first grade, {skipped_no_price} board row(s) skipped for no price. "
          "The missing days stay missing — they are disclosed, never backfilled",
          flush=True)
    return True


# --------------------------------------------------------------------------- #
# board reconstruction (git archaeology + snapshot union)
# --------------------------------------------------------------------------- #
def _git_revisions() -> list[tuple[str, str]]:
    """Every commit that touched the board artifact, newest first.

    LOUD on failure. This used to return `[]` for any git error — a wrong-and-silent
    degradation: the retro half of the ledger simply vanished and the forward
    snapshots carried on alone. Observed 2026-07-26, a transient failure here cut the
    US ledger from 680 matured episodes across 17 board days to 111 across 5, moving
    the published interval from 55.2–71.3% to 51.9–69.2% with nothing in the output to
    say the history had been truncated. A track record that silently changes size
    depending on whether a subprocess succeeded is not a track record.
    """
    proc = subprocess.run(
        ["git", "log", "--format=%H", "--", BOARD_PATH],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git log over {BOARD_PATH} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:300]} — refusing to grade on a silently truncated "
            "history; re-run once git is available."
        )
    return proc.stdout.split()


def _load_blob(sha: str) -> dict | None:
    """One board revision, or None when that revision genuinely has no board.

    LOUD on a git FAILURE, for the same reason :func:`_git_revisions` is (G2).  This
    used to read `.stdout` without ever looking at the return code, so `git show`
    failing — a corrupt object, a missing pack, an interrupted checkout — produced an
    empty string, which read as "this commit had no board" and dropped the revision
    silently.  Enough dropped revisions and the track record ships a Wilson CI computed
    over a SINGLE date while still calling itself the history.  A truncated history is
    the one thing a track record may never be quiet about: an empty stdout WITH rc=0 is
    a real absence, an empty stdout with rc!=0 is a broken read, and only the first is
    a None.
    """
    proc = subprocess.run(
        ["git", "show", f"{sha}:{BOARD_PATH}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        # A path that does not exist in this revision is a legitimate absence, not a
        # failure: the board was added at some commit, and every earlier revision
        # answers "does not exist" with rc=128.  Everything else is a broken read.
        if "does not exist" in stderr or "exists on disk, but not in" in stderr:
            return None
        raise RuntimeError(
            f"git show {sha}:{BOARD_PATH} failed (rc={proc.returncode}): "
            f"{stderr[:300]} — refusing to grade on a silently truncated history; "
            "re-run once the object store is readable."
        )
    blob = proc.stdout
    if not blob.strip():
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _dig(d: dict, *paths, default=None):
    """Tolerant nested getter: returns first path that resolves non-None.
    Each path is a tuple of keys; walks dicts, skips on any miss (schema drift)."""
    for path in paths:
        cur = d
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur and cur[k] is not None:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _row_features(r: dict) -> dict:
    """Extract grading-relevant fields, tolerant to schema drift across revisions.

    Fields moved over time: score/band/composite_z/verdict/validation_status started
    at row top-level in the very first schema (never — they were always under
    `conviction`), and later `vol_squeeze`/`act_level` nested under
    conviction.*/entry_signal.*. `signal` (with .last.quality) only appears in the
    latest schema. `align_tier` is None in the earliest revision. Every getter below
    tries the modern nested path first, then a flat fallback."""
    conv = r.get("conviction") or {}
    sig = r.get("signal") or {}
    es = r.get("entry_signal") or {}
    # entry_status disclosure law (2026-08-04): a graded row never carries a SILENT
    # entry_status null. When the board row has no entry_signal.status, the reason
    # resolves in priority order: the writer's own stamp (entry_signal_null_reason —
    # no_cycle_ladder / short_history / gauge_error:* / lane_not_stamped /
    # not_assessed), else "unstamped_at_publish" (the published row that night
    # carried neither the gauge nor a reason — the pre-instrumentation boards,
    # 2026-06-15..17, whose 442 silent-null rows were the battery §1 finding).
    # PIT: the reason is a property of the frozen snapshot/blob being graded, never
    # a recomputed label; entry_status itself is NEVER backfilled.
    _estat = _dig(r, ("entry_signal", "status"), default=es.get("status"))
    return {
        "ticker": r.get("ticker"),
        "sector": r.get("sector"),
        "alpha": _num(r.get("alpha")),
        "state": r.get("state"),
        "label": r.get("label"),
        "urgency": r.get("urgency"),
        "align_tier": r.get("align_tier"),
        "score": _num(_dig(r, ("conviction", "score"), ("score",))),
        "band": _dig(r, ("conviction", "band"), ("band",)),
        "composite_z": _num(_dig(r, ("conviction", "composite_z"), ("composite_z",))),
        "verdict": _dig(r, ("conviction", "verdict"), ("verdict",)),
        "validation_status": _dig(r, ("conviction", "validation_status"), ("validation_status",)),
        "trust_tier": _dig(r, ("conviction", "trust_tier", "tier"), ("trust_tier", "tier")),
        # entry_signal.status = the confluence-gated "buyable now" flag
        "entry_status": _estat,
        "entry_status_reason": (None if _estat is not None
                                else (r.get("entry_signal_null_reason")
                                      or "unstamped_at_publish")),
        "act_level": _num(_dig(r, ("entry_signal", "act_level"),
                               ("conviction", "act_level"), default=es.get("act_level"))),
        # signal.last.quality = block/ok — the master-veto state (latest schema only)
        "signal_quality": _dig(r, ("signal", "last", "quality"), default=None),
        "signal_last_type": _dig(r, ("signal", "last", "type"), default=None),
        "tier_cascade": _dig(r, ("signal", "tier_cascade"), default=sig.get("tier_cascade")),
        # vol_squeeze nested under conviction.* in later schemas
        "vol_squeeze": _dig(r, ("conviction", "vol_squeeze", "state"),
                            ("vol_squeeze", "state"), ("vol_squeeze",)),
        # spotlight sector ETF (later schemas carry it directly)
        "spot_sector_etf": _dig(r, ("conviction", "spotlight", "sector", "etf")),
        "off_high": _num(r.get("off_high")),
        "dispersion_state": None,  # filled from board-level below
        # COILED wave-2 ranking bonus fields (forward-ledger; None when absent/pre-schema)
        "coiled":        bool((r.get("coiled") or {}).get("coiled")),
        "coiled_star":   bool((r.get("coiled") or {}).get("star")),
        "coiled_cohort": (r.get("coiled") or {}).get("cohort"),
        # COILED-FIRE wave-4 display chip fields (forward-ledger; False/None pre-schema)
        "coiled_fire":       bool((r.get("coiled") or {}).get("fire")),
        "coiled_fire_ticks": (r.get("coiled") or {}).get("fire_ticks"),
        # G6a donor-sector per-row (constant per as_of — from board-level donor object below)
        # filled in _board_to_record after _row_features; None pre-schema
        "donor_state":  None,
        "donor_sector": None,
        # W6-C HOLD tracker: basing state after confluence anchor (per-row; None pre-schema)
        "hold_state":     _dig(r, ("hold", "state"), default=None),
        "hold_days":      _num(_dig(r, ("hold", "days_basing"), default=None)),
        "hold_inv":       _num(_dig(r, ("hold", "invalidation"), default=None)),
        "hold_anchor_src": _dig(r, ("hold", "anchor_src"), default=None),
        # W8 dual-lane fields (forward-ledger strata; None pre-schema)
        # Real live domain: 'bottoming' | 'continuation' | 'watch' | 'leader' | 'ran' |
        # None.  ('trend' and 'recovery' were the W8 design names and have NEVER been
        # written — no code path assigns them, and zero rows carry them across the full
        # ledger history; see PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md §1.1.  'ran' is
        # written by engine/us_board_rank.py.)  Fossil rows keep whatever they were
        # written with — this comment describes the producer, not the history.
        "lane":         r.get("lane"),
        "arbiter_note": r.get("arbiter_note"),      # downgrade reason from W8 arbiter | None
        # W8-B postcross lifecycle (display-only; None pre-schema)
        "postcross_based":  bool((r.get("postcross") or {}).get("based")),
        "postcross_armed":  (r.get("postcross") or {}).get("armed"),   # 'strict'|'net'|None
        "postcross_shaken": bool((r.get("postcross") or {}).get("shaken")),
        "postcross_ticks":  _num((r.get("postcross") or {}).get("ticks_since_cross")),
        # W3 evidence-stack strata (display-only; forward IC under accrual; False/None pre-schema)
        "insider_cluster":      bool((r.get("insider_buyers") or 0) >= 2),
        "gex_confirm_verdict":  _dig(r, ("gex_confirm", "verdict"), default=None),
        "altdata_conv_gte2":    bool((_dig(r, ("altdata", "convergence_score"), default=0) or 0) >= 2),
        "sue_fresh":            bool(r.get("sue_z") and (r.get("sue_fresh_days") or 999) <= 60),
        "news_burst":           bool((_dig(r, ("news_burst", "n_recent"), default=0) or 0) >= 3),
        "smartmoney_add":       bool(r.get("smartmoney_chip")),
        "has_stop_guidance":    bool(r.get("stop_guidance")),
        "confluence_k":         int((r.get("confluence_plus") or {}).get("k") or 0),
    }


def _num(x):
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def collect_boards(receipt: dict | None = None) -> list[dict]:
    """Union git-history boards with snapshot JSONL, de-dup on (as_of).

    Each element: {as_of: 'YYYY-MM-DD', dispersion_state, rank_by, rows: [ {lane, position, **features} ]}.
    Position = 0-based order within lane as published (this IS the ranking under test).

    `receipt`, when supplied, is filled with the PROVENANCE SPLIT — how many board
    dates each of the two legs actually contributed, and how many revisions of the
    board artifact git could see.  _git_revisions() is LOUD when git *errors*, but a
    truncated history is not an error: on a shallow checkout `git log -- <path>`
    exits 0 and returns one revision, so the retro half degrades to nothing while
    every other number in the run looks normal.  The split is what makes that
    visible (see warn_if_history_truncated)."""
    boards: dict[str, dict] = {}

    # 1) snapshots (forward-accruing source) — take precedence (exact bytes at build time)
    if SNAPSHOTS_JSONL.exists():
        for line in SNAPSHOTS_JSONL.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                snap = json.loads(line)
            except json.JSONDecodeError:
                continue
            b = _board_to_record(snap)
            if b:
                boards[b["as_of"]] = b
    n_from_snapshots = len(boards)

    # 2) git history (retro source) — fills any as_of not already present
    revisions = _git_revisions()
    for sha in revisions:
        d = _load_blob(sha)
        if not d:
            continue
        b = _board_to_record(d)
        if b and b["as_of"] not in boards:
            boards[b["as_of"]] = b

    if receipt is not None:
        receipt.update({
            "n_git_revisions": len(revisions),
            "n_from_snapshots": n_from_snapshots,
            "n_from_git": len(boards) - n_from_snapshots,
            "n_boards": len(boards),
        })
    return sorted(boards.values(), key=lambda x: x["as_of"])


def warn_if_history_truncated(receipt: dict) -> bool:
    """Emit the line-start annotation when the retro (git-archaeology) leg is DARK.

    Returns True when it fired.  Bare ``print`` with ``flush=True`` per the repo's
    annotation law (a logger prefixes the line and GitHub drops the annotation).

    WHY THIS EXISTS (measured 2026-08-06).  `_git_revisions` is loud on a git *error*,
    which closed the 2026-07-26 class where a failing subprocess silently halved the
    ledger.  It cannot see the other way this half dies: `actions/checkout@v4` defaults
    to ``fetch-depth: 1``, so on the nightly runner `git log -- site/factordata/
    us_standouts.json` exits 0 with ONE revision and the archaeology leg contributes
    nothing.  Evidence from the nightlies' own logs — the grader printed
    ``[boards] 13 distinct as_of dates`` (2026-07-27) and ``[boards] 17`` (2026-08-05),
    both exactly the snapshot count, while the same code over a full local checkout
    reads 524 revisions and 32 board dates.  The 15 archaeology-only dates
    (2026-06-15..06-29, 07-07, 07-08, 07-13, 07-22, 07-23) are therefore invisible to
    every nightly: 8 of them have never had a single graded row, and 2026-06-17..06-24
    are frozen at the 5d horizon because no later run could re-reach them.

    The trigger is deliberately narrow — one revision or none, while the ledger already
    knows about more than one board date. A repo that genuinely holds a single revision
    of a single board cannot trip it, and a healthy full checkout is nowhere near it."""
    n_rev = int(receipt.get("n_git_revisions") or 0)
    n_boards = int(receipt.get("n_boards") or 0)
    if n_rev > 1 or n_boards <= 1:
        return False
    print("::warning title=us-board-ledger-history-truncated::"
          f"git log over {BOARD_PATH} returned {n_rev} revision(s) but the ledger knows "
          f"{n_boards} board date(s) — this checkout is too shallow to reconstruct any "
          f"history, so the retro half of the ledger contributed "
          f"{int(receipt.get('n_from_git') or 0)} board date(s) and every board that "
          "exists only in git history is ungraded and unreachable from this run; "
          "the fix is fetch-depth: 0 on this job's checkout, not a backfill",
          flush=True)
    return True


def _board_to_record(d: dict) -> dict | None:
    as_of = d.get("as_of")
    if not as_of:
        return None
    disp = _dig(d, ("dispersion_regime", "state"), default=None)
    rank_by = d.get("rank_by")
    # G6a donor-sector: page-level object, constant for all rows in this snapshot
    _donor = d.get("donor") or {}
    _donor_state_val  = _donor.get("state") if isinstance(_donor, dict) else None
    _donor_sector_val = _donor.get("donor_sector") if isinstance(_donor, dict) else None
    rows = []
    for lane in LANES:
        lst = d.get(lane) or []
        canon_lane = "laggards" if lane == "laggard" else lane
        for pos, r in enumerate(lst):
            if not isinstance(r, dict):
                continue
            feat = _row_features(r)
            if not feat["ticker"]:
                continue
            feat["lane"] = canon_lane
            feat["position"] = pos
            feat["dispersion_state"] = disp
            # propagate page-level donor into each row for the grader
            feat["donor_state"]  = _donor_state_val
            feat["donor_sector"] = _donor_sector_val
            rows.append(feat)
    if not rows:
        return None
    return {"as_of": as_of, "dispersion_state": disp, "rank_by": rank_by, "rows": rows}


# --------------------------------------------------------------------------- #
# grading helpers
# --------------------------------------------------------------------------- #

# W0.1 B-b: _fwd_ret and _close_path_mae are DELETED.
# All forward returns now come from engine.grading.forward_metrics (one-grader law §1.2).
# Excess MAE is computed inline in grade_boards using the fill position returned by
# engine.grading.fill_index — same next-bar convention, same window semantics.

def _excess_close_path_mae(
    name_ser: pd.Series,
    bench_ser_aligned: pd.Series,
    fill: int,
    h: int,
) -> float | None:
    """Close-path excess MAE: min over bars (fill+1 .. fill+h) of
    (name_cum_ret_t - bench_cum_ret_t).  Same window as forward_metrics fwd_mdd
    (strictly forward, exclusive of the fill bar). Returns None when there are
    fewer than h bars available (not yet matured). Bench series must already be
    aligned/reindexed to name_ser's index.

    Preserves the documented convention from the original _close_path_mae:
    excess return computed as (npj/np0 - 1) - (bpj/bp0 - 1) on a bar-by-bar
    basis, taking the minimum over the window. Label: mae_close_excess.
    """
    if fill + h >= len(name_ser):
        return None
    np0 = float(name_ser.iloc[fill])
    bp0 = float(bench_ser_aligned.iloc[fill])
    if not (np.isfinite(np0) and np.isfinite(bp0) and np0 > 0 and bp0 > 0):
        return None
    worst = 0.0
    for j in range(1, h + 1):
        npj = float(name_ser.iloc[fill + j])
        bpj = float(bench_ser_aligned.iloc[fill + j])
        if not (np.isfinite(npj) and np.isfinite(bpj)):
            continue
        exc = (npj / np0 - 1.0) - (bpj / bp0 - 1.0)
        worst = min(worst, exc)
    return float(worst)


def _archetype_pit(ticker, as_of) -> str | None:
    """PIT archetype label for (ticker, as_of) — greatest asof_date <= as_of from
    data/archetypes/history.parquet, via engine.neuralweb.context_api.archetype_asof.

    The import is lazy on purpose: context_api pulls the fundamental-forensics chain at
    module import, and the CI packs install minimal deps — the grader must not carry that
    weight just to grade a board.  ImportError → None (column stays null, as before).
    Nothing broader is caught: the reader is already fail-soft on an absent store, ticker,
    or PIT-eligible row, so a genuine read failure stays LOUD instead of a silent null.
    """
    try:
        from engine.neuralweb.context_api import archetype_asof
    except ImportError:
        return None
    return archetype_asof(str(ticker), as_of)


def grade_boards(boards: list[dict], names: pd.DataFrame, etfs: pd.DataFrame,
                 _stored_df: pd.DataFrame | None = None,
                 price_sources: dict | None = None) -> pd.DataFrame:
    """Grade all matured board rows, routing all forward metrics through engine.grading
    (one-grader law §1.2). New in W0.1 B-b:

    1. GRADER: _fwd_ret/_close_path_mae removed; forward_metrics + _excess_close_path_mae used.
    2. 63d LANE: HORIZONS now includes 63 — all four horizons graded per row.
    3. SURVIVORSHIP FIX: prices resolved via resolve_series (extends live series with
       dead-name terminal values when the edgar dead-name store is present).
    4. SPINE COLUMNS: fwd_mfe_{H} for each H; terminal_state_clean15_126,
       terminal_state_clean8_21, post_cushion_breach (at horizon=21); all nullable.
    5. REGIME STAMP: PIT regime_vector fields stamped per as_of row.
    6. ARCHETYPE: from the row payload, else the PIT archetype store at this board's
       as_of.  species_id is no longer emitted (retired 2026-08-04 — see module header).
    7. IN-BATCH TENURE (FIX-5): boards processed in ascending as_of order; a running
       in-memory presence map (union of stored + freshly-graded (as_of, ticker) pairs)
       is maintained and passed to _board_tenure so consecutive dates graded in the
       same call can see each other correctly.

    RETRO-STAMP HONESTY (FIX-6):
      Historical rows ARE retro-stamped with PIT-honest board_tenure_days whenever
      re-graded.  The tenure count uses only dates strictly < as_of — verified correct.
      This is intentional and blessed: it back-fills H5's substrate honestly for rows
      that predated the board_tenure_days column.
    """
    # FIX-5: sort boards ascending by as_of so the in-batch presence map
    # accumulates in chronological order (earlier boards feed later ones).
    boards = sorted(boards, key=lambda b: b["as_of"])

    spy = etfs[BENCH].dropna() if BENCH in etfs.columns else None
    last_price_date = names.index.max()

    # W0.1 B-b: load dead-name price store once per run for resolve_series
    dead_prices = load_dead_prices()
    _dead_price_count = len(dead_prices)  # for coverage reporting

    # FIX-5: running in-memory presence map — as_of_str → set of tickers graded
    # so far in this batch.  Seeded from stored_df at the H=5 slice (same proxy
    # used by _board_tenure when scanning stored_df directly).  In-batch boards
    # add their tickers here after grading so the NEXT board can see them.
    _batch_presence: dict[str, set] = {}
    if _stored_df is not None and not _stored_df.empty:
        sub = (_stored_df[_stored_df["horizon"] == 5]
               if "horizon" in _stored_df.columns else _stored_df)
        if "as_of" in sub.columns and "ticker" in sub.columns:
            for d, g in sub.groupby("as_of"):
                _batch_presence[d] = set(g["ticker"].dropna().tolist())

    recs = []
    skipped_no_price = 0
    unadjusted_tickers: set[str] = set()
    for b in boards:
        as_of = pd.Timestamp(b["as_of"])
        as_of_str = b["as_of"]
        rank_by = b.get("rank_by")

        # W0.1 B-b scope 4: PIT regime stamp — looked up once per board date
        regime_stamp = get_vector_for_date(as_of)

        # FIX-5: collect tickers seen on this board date (any lane) for the
        # in-batch presence map — used by _board_tenure for subsequent dates.
        _board_tickers_this_date: set[str] = set()

        for feat in b["rows"]:
            tk = feat["ticker"]
            _board_tickers_this_date.add(tk)
            # W0.1 B-b scope 3: resolve_series extends live closes with dead-name terminals
            live_col = names[tk].dropna() if tk in names.columns else None
            nser = resolve_series(tk, live_col, dead_prices=dead_prices)
            if nser is None or nser.empty:
                skipped_no_price += 1
                continue

            # price-basis stamp for every row this ticker produces (see rec below).
            # `price_sources` is the provenance rebase_to_adjusted returned; a ticker
            # missing from it was never resolved through the ladder (dead-name store
            # only), which is itself worth recording rather than guessing at.
            _px_src = (price_sources or {}).get(tk)
            _px_basis = {True: "adjusted", False: "unadjusted"}.get(
                _px_is_adjusted(_px_src))
            if _px_basis == "unadjusted":
                unadjusted_tickers.add(tk)

            # fill position: strictly after as_of (next-bar entry convention)
            fill = fill_index(nser, as_of)
            if fill is None:
                continue
            entry_date = nser.index[fill]

            # benchmark series aligned to name's trading calendar
            etf_t = feat.get("spot_sector_etf") or _GICS_ETF.get(feat.get("sector") or "")

            # Compute forward_metrics for the name once for all horizons (all four h values)
            # forward_metrics handles maturity check internally (returns None for unmatured H)
            fwd = forward_metrics(nser, as_of, horizons=tuple(HORIZONS))

            # terminal_state (per-as_of, computed once for positional + rotational params)
            # These are horizon-independent state classifications — computed per fire, not per horizon
            ts_clean15 = terminal_state(
                nser, as_of,
                liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126,
            )
            ts_clean8 = terminal_state(
                nser, as_of,
                liftoff_mult=LIFTOFF_8, liftoff_horizon=LIFTOFF_HORIZON_21,
            )
            # post_cushion_breach at horizon=21 (rotational)
            pcb = post_cushion_breach(nser, as_of, horizon=LIFTOFF_HORIZON_21)

            # Pre-align benchmark series to name index (done once per name per board)
            spy_al = spy.reindex(nser.index).ffill() if spy is not None else None
            etf_al = (etfs[etf_t].reindex(nser.index).ffill()
                      if etf_t and etf_t in etfs.columns else None)

            # Benchmark forward metrics — computed ONCE per name/as_of for all horizons
            spy_fwd = (forward_metrics(spy_al, as_of, horizons=tuple(HORIZONS))
                       if spy_al is not None else {})
            etf_fwd = (forward_metrics(etf_al, as_of, horizons=tuple(HORIZONS))
                       if etf_al is not None else {})

            # archetype: board row payload first, else the PIT archetype store at this
            # board's own as_of.  The payload has never carried the field (0/2282 rows
            # measured 2026-08-04), so the PIT leg is what actually populates it.
            archetype = feat.get("archetype") or _archetype_pit(tk, as_of_str)

            for h in HORIZONS:
                # maturity check: forward_metrics returns None for unmatured H
                nret = fwd.get(f"fwd_ret_{h}")
                if nret is None:
                    continue
                # secondary maturity check: confirm horizon date is within data window
                if fill + h >= len(nser):
                    continue
                horizon_date = nser.index[fill + h]
                if horizon_date > last_price_date:
                    continue

                fwd_mfe = fwd.get(f"fwd_mfe_{h}")

                rec = {
                    "as_of": as_of_str, "entry_date": entry_date.date().isoformat(),
                    "rank_by": rank_by,
                    "horizon": h, "lane": feat["lane"], "position": feat["position"],
                    "ticker": tk, "sector": feat.get("sector"),
                    "alpha": feat.get("alpha"), "score": feat.get("score"),
                    "band": feat.get("band"), "composite_z": feat.get("composite_z"),
                    "verdict": feat.get("verdict"), "align_tier": feat.get("align_tier"),
                    "urgency": feat.get("urgency"), "state": feat.get("state"),
                    "entry_status": feat.get("entry_status"),
                    # disclosure twin: non-null exactly when entry_status is null on a
                    # freshly-graded row (see _row_features); existing stored rows keep
                    # nulls until their board is re-graded (schema-union).
                    "entry_status_reason": feat.get("entry_status_reason"),
                    "act_level": feat.get("act_level"),
                    "signal_quality": feat.get("signal_quality"),
                    "validation_status": feat.get("validation_status"),
                    "vol_squeeze": feat.get("vol_squeeze"),
                    "dispersion_state": feat.get("dispersion_state"),
                    # G6a donor-unwind rotation context (page-level, constant per as_of)
                    "donor_state": feat.get("donor_state"),
                    "donor_sector": feat.get("donor_sector"),
                    "off_high": feat.get("off_high"),
                    # W6-C HOLD tracker fields (per-row; None on pre-schema boards)
                    "hold_state":      feat.get("hold_state"),
                    "hold_days":       feat.get("hold_days"),
                    "hold_inv":        feat.get("hold_inv"),
                    "hold_anchor_src": feat.get("hold_anchor_src"),
                    # W0.2b tier_cascade
                    "tier_cascade":    feat.get("tier_cascade"),
                    # P2 — H5 substrate stamping (PREREGISTRATION.md §2.4)
                    # board_tenure_days = consecutive prior as_of RECORDS where the
                    # ticker appears in any lane; calendar gaps do not reset; a
                    # record-date absence does.  This is NOT hold_days (hold.days_basing).
                    # Column name ruling (Fable 2026-07-05): board_tenure_days is
                    # canonical — the prereg §2.4 quantity under a non-colliding name
                    # (ledger hold_days already carries days_basing); validate_factor_h5.py
                    # must read board_tenure_days.
                    # FIX-5: _presence_map=_batch_presence feeds in-batch dates so
                    # consecutive boards graded in one call see each other correctly.
                    # FIX-6: historical rows ARE retro-stamped (PIT-honest: only
                    # dates strictly < as_of_str are counted); this is intentional.
                    "board_tenure_days": _board_tenure(
                        tk, feat["lane"], as_of_str, _stored_df,
                        _presence_map=_batch_presence,
                    ),
                    # W3 evidence-stack strata (display-only; forward IC under accrual; None pre-schema)
                    "insider_cluster":   feat.get("insider_cluster"),
                    "gex_confirm_verdict": feat.get("gex_confirm_verdict"),
                    "altdata_conv_gte2": feat.get("altdata_conv_gte2"),
                    "sue_fresh":         feat.get("sue_fresh"),
                    "news_burst":        feat.get("news_burst"),
                    "smartmoney_add":    feat.get("smartmoney_add"),
                    "has_stop_guidance": feat.get("has_stop_guidance"),
                    "confluence_k":      feat.get("confluence_k"),
                    "ret": nret,
                    # W0.1 B-b spine columns (§5.1, §3.4)
                    f"fwd_mfe_{h}":      fwd_mfe,
                    # terminal_state and post_cushion_breach are per-fire, not per-horizon;
                    # stamp them on each horizon row so the parquet is self-contained.
                    "terminal_state_clean15_126": ts_clean15.get("state"),
                    "terminal_state_clean8_21":   ts_clean8.get("state"),
                    "post_cushion_breach":         pcb,
                    # regime_vector PIT stamp (§3.4; US ledger → US vector primary)
                    "rate_pressure":          regime_stamp.get("rate_pressure"),
                    "quad_hard_label":        regime_stamp.get("quad_hard_label"),
                    "fused_risk_label":       regime_stamp.get("fused_risk_label"),
                    "vol_regime":             regime_stamp.get("vol_regime"),
                    "risk_radar_state":       regime_stamp.get("risk_radar_state"),
                    "regime_vector_degraded": regime_stamp.get("regime_vector_degraded"),
                    "vector_asof":            regime_stamp.get("vector_asof"),
                    "staleness_hours":        regime_stamp.get("staleness_hours"),
                    # archetype (§3.4) — payload first, else the PIT store (see above).
                    # species_id is NOT emitted: retired 2026-08-04, _RETIRED_LEDGER_COLS.
                    "archetype":  archetype,
                    # PRICE-BASIS STAMP (2026-08-06). Which store this row's NAME leg was
                    # priced from, and whether that store is back-adjusted. The benchmark
                    # leg is always adjusted (data/yahoo), so `price_basis == "adjusted"`
                    # is the row's certificate that both legs shared one basis. A row
                    # stamped "unadjusted" is a name with no adjusted counterpart —
                    # disclosed, not dropped. NULL on every row graded before this PR:
                    # that null IS the era marker (see README "Price-basis era").
                    "price_source": _px_src,
                    "price_basis": _px_basis,
                }
                # excess vs SPY
                if spy_al is not None:
                    sret = spy_fwd.get(f"fwd_ret_{h}")
                    rec["spy_ret"] = sret
                    rec["excess_spy"] = (nret - sret) if sret is not None else None
                    rec["mae_close_excess_spy"] = _excess_close_path_mae(nser, spy_al, fill, h)
                else:
                    rec["spy_ret"] = rec["excess_spy"] = rec["mae_close_excess_spy"] = None
                # excess vs sector ETF
                if etf_al is not None:
                    eret = etf_fwd.get(f"fwd_ret_{h}")
                    rec["sector_etf"] = etf_t
                    rec["etf_ret"] = eret
                    rec["excess_sector"] = (nret - eret) if eret is not None else None
                    rec["mae_close_excess_sector"] = _excess_close_path_mae(nser, etf_al, fill, h)
                else:
                    rec["sector_etf"] = etf_t
                    rec["etf_ret"] = rec["excess_sector"] = rec["mae_close_excess_sector"] = None
                recs.append(rec)

        # FIX-5: after processing all rows for this board date, update the
        # running presence map with all tickers seen (any lane) on as_of_str.
        # This allows the NEXT board date in the same grade_boards call to see
        # these tickers when computing board_tenure_days.
        if _board_tickers_this_date:
            if as_of_str in _batch_presence:
                _batch_presence[as_of_str] = _batch_presence[as_of_str] | _board_tickers_this_date
            else:
                _batch_presence[as_of_str] = _board_tickers_this_date

    df = pd.DataFrame(recs)
    df.attrs["skipped_no_price"] = skipped_no_price
    df.attrs["dead_price_store_tickers"] = _dead_price_count
    df.attrs["unadjusted_basis_tickers"] = sorted(unadjusted_tickers)

    # Nulls printed, not hidden — but only alarm on a REGRESSION in adjusted-store
    # coverage, not on the standing residual. A steady handful of off-index names with no
    # adjusted counterpart is the known cost of not dropping them; a sudden jump means an
    # adjusted store stopped being written, which silently re-contaminates the ledger.
    # Bare line-start print: a logger prefixes the line and GitHub drops the annotation.
    if not df.empty and "price_basis" in df.columns:
        n_unadj = int((df["price_basis"] == "unadjusted").sum())
        share = n_unadj / len(df)
        if share > _UNADJUSTED_ROW_SHARE_ALARM:
            print("::warning title=us-board-price-basis-coverage::"
                  f"{n_unadj}/{len(df)} freshly-graded rows ({share:.1%}) priced a name "
                  f"from the UNADJUSTED breadth cache against an adjusted benchmark — "
                  f"above the {_UNADJUSTED_ROW_SHARE_ALARM:.0%} floor. Their own "
                  f"distributions are booked as losses. Tickers: "
                  f"{', '.join(sorted(unadjusted_tickers)[:15])}", flush=True)
    return df


# --------------------------------------------------------------------------- #
# aggregation / stats
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _hit_stats(sub: pd.DataFrame, col: str = "excess_spy") -> dict:
    vals = sub[col].dropna()
    n = len(vals)
    if n == 0:
        return {"n": 0}
    k = int((vals > 0).sum())
    lo, hi = wilson_ci(k, n)
    return {
        "n": n, "hit_rate": round(k / n, 4),
        "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
        "median_excess": round(float(vals.median()), 5),
        "mean_excess": round(float(vals.mean()), 5),
    }


def _precision_at_k(sub: pd.DataFrame, col: str = "excess_spy",
                    rank_col: str = "position", ascending: bool = True,
                    published: bool = True) -> dict:
    """P(excess>0) among the top-k by `rank_col`.

    PUBLISHED TOP-K, NOT TOP-K-OF-THE-SURVIVORS (G1, 2026-08-06)
    ------------------------------------------------------------
    `precision@k` is a claim about the k names a reader actually saw at the top of the
    board.  `head(k)` of the GRADED subset is a different question: every published row
    that failed to grade (no price, not yet matured, delisted) is skipped and the row
    BELOW it is promoted into the top-k.  On a board where position 1 is the one that
    delisted, `head(3)` scores published #2, #4 and #5 and calls the answer P@3.
    Promotion by absence is not a ranking result.

    So for the as-published order (`rank_col="position"`, the ranking under test) the
    top-k is defined by the PUBLISHED RANK — `position` is 0-based within the lane, so
    the published top-k is `position < k` — and rows missing from the graded frame are
    simply absent, never backfilled from below.  Each cell then discloses
    `published_topk_rows` / `graded_topk_rows` / `coverage`, so a thin cell is visible
    as thin rather than reported at full confidence.

    `published=False` is the honest fallback and the ONLY mode available to a
    COUNTERFACTUAL ordering (`rank_col='alpha'` / `'composite_z'`): those orders exist
    only over the rows that graded, so head-of-the-graded-subset IS their definition.
    Such cells are stamped `basis="graded_subset"` with the same coverage counts, so
    the reader can never mistake one basis for the other.
    """
    out = {}
    use_published = bool(published) and rank_col == "position"
    for k in K_LIST:
        per_board_hit = []
        per_board_mean = []
        pooled_frames = []
        published_rows = 0
        graded_rows = 0
        for _as_of, g in sub.groupby("as_of"):
            if use_published:
                # `position` is the published 0-based rank inside the lane, so the
                # published top-k is a LEVEL test, not a head() of what survived.
                pos = pd.to_numeric(g[rank_col], errors="coerce")
                topk_rows = g[pos < k]
                published_rows += k          # what the board actually showed at this k
            else:
                topk_rows = g.sort_values(rank_col, ascending=ascending).head(k)
                published_rows += min(k, len(g))
            topk = topk_rows[col].dropna()
            graded_rows += len(topk)
            if len(topk) == 0:
                continue
            pooled_frames.append(topk)
            per_board_hit.append(float((topk > 0).mean()))
            per_board_mean.append(float(topk.mean()))
        basis = "published_rank" if use_published else "graded_subset"
        if per_board_hit:
            pooled = pd.concat(pooled_frames)
            kk = int((pooled > 0).sum())
            nn = len(pooled)
            lo, hi = wilson_ci(kk, nn)
            out[f"k{k}"] = {
                "n_boards": len(per_board_hit), "n_rows": nn,
                "precision": round(float(np.mean(per_board_hit)), 4),
                "pooled_precision": round(kk / nn, 4) if nn else None,
                "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4),
                "mean_excess_topk": round(float(np.mean(per_board_mean)), 5),
                # G1 disclosure — how much of the top-k this cell could actually see.
                "basis": basis,
                "published_topk_rows": published_rows,
                "graded_topk_rows": graded_rows,
                "coverage": (round(graded_rows / published_rows, 4)
                             if published_rows else None),
            }
        else:
            out[f"k{k}"] = {
                "n_boards": 0, "n_rows": 0, "basis": basis,
                "published_topk_rows": published_rows,
                "graded_topk_rows": graded_rows,
                "coverage": (round(graded_rows / published_rows, 4)
                             if published_rows else None),
            }
    return out


def _slice_table(df: pd.DataFrame, by: str, col: str = "excess_spy") -> dict:
    if by not in df.columns:
        return {}  # pre-schema boards lacking the field — not an error
    out = {}
    for val, g in df.groupby(by, dropna=False):
        key = "None" if (val is None or (isinstance(val, float) and math.isnan(val))) else str(val)
        out[key] = _hit_stats(g, col)
    return out


def _survivorship_block(boards: list[dict], names: pd.DataFrame) -> dict:
    """Quantify the survivorship situation across the FULL board history.

    W0.1 B-b: prices are now resolved via engine.grading.resolve_series, which
    extends live closes with the dead-name terminal series from the edgar store.
    n_skipped_no_price now counts ONLY names that are absent from BOTH the live
    broad cache AND the dead-name store (genuinely unresolvable).

    The note field reports whether the dead-name store is active so the reader
    can assess residual survivor bias honestly.
    """
    cols = names.columns if isinstance(names, pd.DataFrame) else []
    live_usable = {c for c in cols if names[c].notna().any()}
    dead_prices = load_dead_prices()
    dead_usable = set(dead_prices.keys())
    all_usable = live_usable | dead_usable

    n_rows_total = n_rows_skipped = 0
    skipped: set[str] = set()
    recovered_by_dead: set[str] = set()  # in dead store but not live cache
    for b in boards:
        for feat in b.get("rows") or []:
            tk = feat.get("ticker")
            if not tk:
                continue
            n_rows_total += 1
            if tk not in all_usable:
                n_rows_skipped += 1
                skipped.add(tk)
            elif tk not in live_usable and tk in dead_usable:
                recovered_by_dead.add(tk)

    if dead_usable:
        note = (
            f"prices resolved via live broad cache ({len(live_usable)} tickers) + "
            f"edgar dead-name store ({len(dead_usable)} tickers); "
            f"{len(recovered_by_dead)} board names recovered from dead store; "
            f"n_skipped_no_price counts ONLY names absent from both sources "
            f"(likely delisted / never cached — the residual survivor bias)"
        )
    else:
        note = (
            "broad cache is current-membership only; edgar dead-name store absent "
            "(data/edgar/dead_name_prices.parquet not found — populate via "
            "collectors/edgar_deadname_prices to recover delisted names); "
            "n_skipped_no_price may include delisted names whose terminal values "
            "would have been graded if the store were present — residual survivor bias"
        )
    return {
        "n_skipped_no_price": len(skipped),
        "n_rows_skipped_no_price": n_rows_skipped,
        "n_board_rows_total": n_rows_total,
        "tickers_skipped": sorted(skipped)[:30],
        "n_recovered_by_dead_store": len(recovered_by_dead),
        "dead_store_active": bool(dead_usable),
        "dead_store_tickers": len(dead_usable),
        "note": note,
    }


def build_track(df: pd.DataFrame, boards: list[dict], names: pd.DataFrame) -> dict:
    survivorship = _survivorship_block(boards, names)
    if df.empty:
        return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "empty": True,
                "note": "no matured graded rows", "survivorship": survivorship,
                "history": {"era_from": LEDGER_HISTORY_FROM, "n_rows_excluded": 0,
                            "basis": _ERA_BASIS}}
    # ── ONE ERA RULE (G3, 2026-08-06) ────────────────────────────────────────
    # `emit_ledger` already refuses to score anything before LEDGER_HISTORY_FROM: the
    # 2026-06-15..06-24 boards published 120 names on the `buy` key against ~780
    # eligible — a broad screen, not a selection, whose own labels included DOWNTREND
    # and TOPPING names.  `build_track` pooled them anyway, so the SAME FILE published
    # two different track records over two different products and the headline one
    # described a board nobody can follow.  A track record is a claim about a specific
    # instrument; two era rules in one file means at least one of them is wrong.
    #
    # The excluded count ships in `history` so the cut is auditable, never silent —
    # and note that INCLUDING the old era is the choice that flatters the desk, which
    # is the reason to leave it out rather than a reason to keep it.
    _n_before = int(len(df))
    df = df[df["as_of"].astype(str) >= LEDGER_HISTORY_FROM]
    _n_excluded = _n_before - int(len(df))
    if df.empty:
        return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "empty": True,
                "note": (f"no matured graded rows on or after {LEDGER_HISTORY_FROM} "
                         f"({_n_excluded} pre-era row(s) excluded)"),
                "survivorship": survivorship,
                "history": {"era_from": LEDGER_HISTORY_FROM,
                            "n_rows_excluded": _n_excluded, "basis": _ERA_BASIS}}
    board_dates = sorted({b["as_of"] for b in boards})
    graded_dates = sorted(df["as_of"].unique().tolist())
    # ── ERA PARTITION (us_prophet_v1 -> v2, 2026-08-10) ──────────────────────
    # An admission change makes the old and the new board two different products, and a
    # track record is a claim about ONE instrument.  Every graded row already carries the
    # stamp it was published under (`rank_by`, written from
    # engine.us_board_rank.BOARD_DEFINITION by scripts/build_stock_library), but the
    # aggregates below used to run over the whole frame — so the file would have published
    # one headline hit-rate mixing a board that REFUSED washed-out counter-trend names with
    # a board that admits them.  `rank_by_of_matured_boards` disclosed the mixture without
    # undoing it, which is a footnote, not a fence.
    #
    # The fix mirrors engine.cn_prophet_audit.loser_telemetry, the CN sibling that already
    # states the rule: "Definitions are NEVER pooled."  `definitions` carries one fully
    # independent per_horizon block per stamp, and the top-level `per_horizon` — the key
    # site/factordata/us_board_track.json is pinned on, read by
    # engine.calibration_hub._standout_track_row and scripts/build_track_record_page — is
    # SCOPED to exactly one of them, never a pooled recomputation.
    stamps = (df["rank_by"].map(_norm_definition) if "rank_by" in df.columns
              else pd.Series(_LEGACY_ERA, index=df.index))
    definitions = []
    for definition in sorted(stamps.unique()):
        slice_ = df[stamps == definition]
        definitions.append({
            "board_definition": definition,
            "graded_dates": sorted(slice_["as_of"].astype(str).unique().tolist()),
            "graded_rows_total": int(len(slice_)),
            "per_horizon": _per_horizon(slice_),
        })
    definitions.sort(key=lambda d: (d["graded_dates"][0] if d["graded_dates"] else "",
                                    d["board_definition"]))
    headline = _headline_definition(definitions)
    per_horizon = next((d["per_horizon"] for d in definitions
                        if d["board_definition"] == headline), {})
    era_scope = {
        "board_definition": headline,
        "live_board_definition": _live_definition(),
        # True when the headline is NOT the era the board publishes today — the state the
        # first nights after an era bump are in, before any v2 row has matured.  Disclosed
        # rather than papered over: the alternative is a headline that silently borrows the
        # superseded product's record, which is the pooling this partition exists to stop.
        "headline_is_superseded": headline != _live_definition(),
        "definitions_present": [d["board_definition"] for d in definitions],
        "pooled": False,
        "note": ("per_horizon describes ONE board_definition; every era's own block is in "
                 "`definitions`. Eras are never pooled — an admission change makes two "
                 "different products (research/RECLAIM_VETO_CONDITIONAL_PREREG.md §4, "
                 "research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md §7)."),
    }
    return _assemble_track(
        df=df, board_dates=board_dates, graded_dates=graded_dates,
        survivorship=survivorship, n_excluded=_n_excluded,
        per_horizon=per_horizon, definitions=definitions, era_scope=era_scope)


#: Pre-version spellings that ARE the legacy era.  Mirrors
#: engine.cn_prophet_audit.norm_definition — without it a null stamp opens its own phantom
#: 'nan' block and splits one era's sample in two.  ``alpha`` is the US board's own
#: pre-us_prophet_v1 spelling (scripts/build_stock_library backfills `rank_by="alpha"` on
#: rows that predate the priority ranker), so it is a real era name and is NOT folded in.
_LEGACY_ERA = "legacy"
_LEGACY_STAMPS = frozenset({"", "none", "nan", "<na>", "null", "legacy"})


def _norm_definition(value) -> str:
    """Normalise a stored ``rank_by`` to the era name this ledger partitions on."""
    text = "" if value is None else str(value).strip()
    return _LEGACY_ERA if text.lower() in _LEGACY_STAMPS else text


def _live_definition() -> str:
    """The era the board publishes TONIGHT, read from the producer — never a literal.

    Imported lazily so this module keeps working (and this file keeps grading) if the
    engine package is unavailable in a stripped environment; an unreadable producer
    degrades to the legacy name, which only ever makes `headline_is_superseded` MORE
    conservative."""
    try:
        from engine.us_board_rank import BOARD_DEFINITION
        return str(BOARD_DEFINITION)
    except Exception:                                              # noqa: BLE001
        return _LEGACY_ERA


def _headline_definition(definitions: list[dict]) -> str | None:
    """Which single era the top-level `per_horizon` describes.

    The LIVE stamp when it has graded rows — the board's record should be the record of
    the board it is.  Otherwise the NEWEST era present, by first graded date: on the nights
    between an era bump and its first matured row the live block is empty, and publishing an
    empty headline there would read as an outage rather than as a young product.  Either
    way the answer is ONE era, named in `era_scope`, so the two can never mix.
    """
    if not definitions:
        return None
    live = _live_definition()
    if any(d["board_definition"] == live for d in definitions):
        return live
    return definitions[-1]["board_definition"]


def _per_horizon(df: pd.DataFrame) -> dict:
    """The per-horizon aggregate block for ONE era's graded rows.

    Extracted verbatim from build_track so the same computation can run per definition;
    it holds no policy of its own and every number it returns is unchanged."""
    per_horizon: dict = {}
    for h in HORIZONS:
        hh = df[df["horizon"] == h]
        if hh.empty:
            per_horizon[f"h{h}"] = {"n": 0}
            continue
        buy = hh[hh["lane"] == "buy"]
        block = {
            "overall_vs_spy": _hit_stats(hh, "excess_spy"),
            "overall_vs_sector": _hit_stats(hh, "excess_sector"),
            "by_lane_vs_spy": _slice_table(hh, "lane", "excess_spy"),
            "buy_lane": {
                "vs_spy": _hit_stats(buy, "excess_spy"),
                "vs_sector": _hit_stats(buy, "excess_sector"),
                "rank_by_of_matured_boards": sorted(buy["rank_by"].dropna().unique().tolist())
                if "rank_by" in buy.columns else [],
                # precision@k under the AS-PUBLISHED board order (the ranking under test)
                "precision_at_k_board_order_vs_spy": _precision_at_k(buy, "excess_spy", "position", True),
                "precision_at_k_vs_sector": _precision_at_k(buy, "excess_sector", "position", True),
                # counterfactuals: if the same names were re-ordered by alpha / composite_z
                "precision_at_k_alpha_order_vs_spy": _precision_at_k(buy, "excess_spy", "alpha", False),
                "precision_at_k_compz_order_vs_spy": _precision_at_k(buy, "excess_spy", "composite_z", False),
                "corr_position_excess": round(float(
                    buy[["position", "excess_spy"]].dropna()["position"].corr(
                        buy[["position", "excess_spy"]].dropna()["excess_spy"])), 4)
                if buy["excess_spy"].notna().sum() > 2 else None,
                "corr_alpha_excess": round(float(
                    buy[["alpha", "excess_spy"]].dropna()["alpha"].corr(
                        buy[["alpha", "excess_spy"]].dropna()["excess_spy"])), 4)
                if buy[["excess_spy", "alpha"]].dropna().shape[0] > 2 else None,
                "by_band": _slice_table(buy, "band", "excess_spy"),
                "by_verdict": _slice_table(buy, "verdict", "excess_spy"),
                "by_align_tier": _slice_table(buy, "align_tier", "excess_spy"),
                "by_entry_status": _slice_table(buy, "entry_status", "excess_spy"),
                "by_signal_quality": _slice_table(buy, "signal_quality", "excess_spy"),
                "by_urgency": _slice_table(buy, "urgency", "excess_spy"),
                "by_sector": _slice_table(buy, "sector", "excess_spy"),
                "by_dispersion": _slice_table(buy, "dispersion_state", "excess_spy"),
                # G6a donor-unwind rotation context — grades stratified by leader state
                "by_donor_state": _slice_table(buy, "donor_state", "excess_spy"),
                # W6-C HOLD tracker — grades stratified by basing state at board publication
                "by_hold_state": _slice_table(buy, "hold_state", "excess_spy"),
                # W0.2b — tier_cascade stratification (T1/T2/T3/T4). Was captured in
                # _row_features but never emitted to the graded record or stratified.
                # "None" = pre-schema boards lacking the signal.tier_cascade field.
                "by_tier_cascade":      _slice_table(buy, "tier_cascade", "excess_spy"),
                # W3 evidence-stack strata (display-only; forward IC under accrual)
                "by_insider_cluster":   _slice_table(buy, "insider_cluster", "excess_spy"),
                "by_gex_confirm":       _slice_table(buy, "gex_confirm_verdict", "excess_spy"),
                "by_altdata_conv":      _slice_table(buy, "altdata_conv_gte2", "excess_spy"),
                "by_sue_fresh":         _slice_table(buy, "sue_fresh", "excess_spy"),
                "by_news_burst":        _slice_table(buy, "news_burst", "excess_spy"),
                "by_smartmoney":        _slice_table(buy, "smartmoney_add", "excess_spy"),
                "by_stop_guidance":     _slice_table(buy, "has_stop_guidance", "excess_spy"),
                "by_confluence_k":      _slice_table(buy, "confluence_k", "excess_spy"),
                "mae_close_excess_spy": {
                    "median": round(float(buy["mae_close_excess_spy"].dropna().median()), 5)
                    if buy["mae_close_excess_spy"].notna().any() else None,
                    "n": int(buy["mae_close_excess_spy"].notna().sum()),
                },
            },
        }
        # P(fwd>0 | top-5) vs base rate for the buy lane.  G1: the top-5 is the
        # PUBLISHED top-5 (`position < 5`, 0-based), not head(5) of whatever graded —
        # `head()` promotes row 6 into the top-5 whenever a published top name has no
        # price, which reports a ranking result produced by absence.
        base = buy["excess_spy"].dropna()
        _pos = pd.to_numeric(buy["position"], errors="coerce")
        top5_frames = [buy[(buy["as_of"] == a) & (_pos < 5)]["excess_spy"].dropna()
                       for a in buy["as_of"].unique()]
        top5 = pd.concat(top5_frames) if top5_frames else pd.Series(dtype=float)
        block["buy_lane"]["p_fwd_pos_top5_vs_base"] = {
            "top5_p": round(float((top5 > 0).mean()), 4) if len(top5) else None,
            "top5_n": int(len(top5)),
            "top5_basis": "published_rank (position < 5)",
            "base_p": round(float((base > 0).mean()), 4) if len(base) else None,
            "base_n": int(len(base)),
            "lift": round(float((top5 > 0).mean() - (base > 0).mean()), 4)
            if len(top5) and len(base) else None,
        }
        per_horizon[f"h{h}"] = block
    return per_horizon


def _assemble_track(*, df, board_dates, graded_dates, survivorship, n_excluded,
                    per_horizon, definitions, era_scope) -> dict:
    """The published `us_board_track.json` payload.  Key order and every existing key are
    preserved — `definitions`/`era_scope` are strictly additive, and `per_horizon` keeps
    its name and shape (it is now ONE era's block instead of a pooled one)."""
    _n_excluded = n_excluded
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "git-archaeology + forward snapshots (unioned, de-duped on as_of)",
        "board_dates_total": len(board_dates),
        "board_dates_range": [board_dates[0], board_dates[-1]] if board_dates else None,
        "graded_dates": graded_dates,
        "graded_rows_total": int(len(df)),
        # G3 — the ONE era rule this file applies, and what it cost, stated where the
        # numbers are (not only in emit_ledger's own meta block).
        "history": {
            "era_from": LEDGER_HISTORY_FROM,
            "n_rows_excluded": _n_excluded,
            "basis": _ERA_BASIS,
        },
        "price_source": ("engine.equity_factors._closes('broad') + engine.grading.resolve_series "
                         "(extends with edgar dead-name terminals) + data/yahoo/{SPY,XL*}"),
        "price_coverage_note": (
            f"{df['ticker'].nunique()} distinct tickers graded; rows unresolvable by both "
            "live cache and dead-name store are skipped — "
            "see the `survivorship` block for the quantified exclusion count."),
        "survivorship": survivorship,
        "conventions": {
            "entry": "next session's close after as_of (next-bar realism, via engine.grading.fill_index)",
            "returns": "total-return (dividend-adjusted) closes; excess = name_ret - benchmark_ret",
            "mae": "CLOSE-PATH MAE (min excess cum-return over window); UNDER-states intraday DD",
            "benchmarks": "SPY and per-name GICS sector SPDR ETF",
            "grader": "engine.grading.forward_metrics (one-grader law §1.2, W0.1 B-b)",
            "horizons": str(HORIZONS),
        },
        "caveats": [
            "TINY n: multi-day horizons only recently matured; first runs have ~11 trading "
            "days of 5d data. Read n on every cell; no strong claims.",
            "OVERLAPPING WINDOWS: daily boards x multi-day horizons -> heavy serial "
            "correlation. Effective independent-sample count << n. Wilson CIs on raw n are "
            "OPTIMISTICALLY NARROW (lower bound on true uncertainty).",
            "SURVIVORSHIP: dead-name store (data/edgar/dead_name_prices.parquet) extends "
            "coverage; if absent, delisted names are invisible — see survivorship.dead_store_active. "
            "Residual survivor bias remains for names absent from both sources.",
            "SCHEMA DRIFT: earliest boards (2026-06-16..) had 120-row buy lanes, no watch "
            "lane, no entry_signal/signal fields; those slices show 'None'. align_tier and "
            "signal.last.quality only populate on later revisions.",
            "W3 EVIDENCE STRATA: by_news_burst has tiny sample (<= 17 tickers / board); "
            "by_smartmoney uses Q1-2026 13F (~45-day lag); by_insider_cluster uses 6-month "
            "rolling Form-4 window. All W3 strata are DISPLAY-ONLY context; no return "
            "claims until wave-8 forward-ledger accrual matures.",
            "ERA PARTITION: `per_horizon` describes the ONE board_definition named in "
            "`era_scope`, never a pool. An admission change makes the old and new board "
            "different products, so their forward records are reported side by side in "
            "`definitions` and never summed into one headline.",
        ],
        # One independent per_horizon block per era stamp found in the graded rows, ordered
        # by first graded date. Definitions are NEVER pooled (cn_prophet_audit's rule).
        "definitions": definitions,
        "era_scope": era_scope,
        "per_horizon": per_horizon,
    }


# --------------------------------------------------------------------------- #
# nightly snapshot
# --------------------------------------------------------------------------- #
def _snapshot_existing_as_of() -> set[str]:
    """The set of ``as_of`` values already present in SNAPSHOTS_JSONL."""
    existing: set[str] = set()
    if SNAPSHOTS_JSONL.exists():
        for line in SNAPSHOTS_JSONL.read_text().splitlines():
            try:
                existing.add(json.loads(line).get("as_of"))
            except json.JSONDecodeError:
                pass
    return existing


def _append_snapshot_row(row: dict) -> None:
    """Append ONE pre-shaped, trimmed row to SNAPSHOTS_JSONL.

    THE one append code path for this file — ``snapshot_today()`` and
    ``absorb_pending_replays()`` both call it, so a lane that appends the wrong bytes
    (wrong separators, no trailing newline) has exactly one place to fix rather than
    two call sites that quietly drifted apart.
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOTS_JSONL.open("a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def snapshot_today() -> str | None:
    """Append today's committed board (site/factordata/us_standouts.json working tree)
    to the append-only snapshot JSONL. Idempotent per as_of."""
    p = ROOT / BOARD_PATH
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    as_of = d.get("as_of")
    if not as_of:
        return None
    existing = _snapshot_existing_as_of()
    if as_of in existing:
        return as_of  # already snapshotted
    # store a trimmed record (lanes + the fields the grader reads) to keep the file lean
    trimmed = {"as_of": as_of, "rank_by": d.get("rank_by"),
               "dispersion_regime": {"state": _dig(d, ("dispersion_regime", "state"))}}
    # G6a donor-sector: persist the page-level donor object into the snapshot so
    # forward grades can stratify by rotation state (constant per as_of).
    if d.get("donor"):
        trimmed["donor"] = d["donor"]
    for lane in LANES:
        if lane in d:
            trimmed[lane] = d[lane]
    _append_snapshot_row(trimmed)
    return as_of


def absorb_pending_replays(*, quiet: bool = False) -> dict:
    """Absorb ``PENDING_REPLAY_DIR/*.json`` (schema ``pit_replay.pending/v1``, written
    by ``scripts/prophet_pit_replay.py``) into ``snapshots.jsonl``, through the SAME
    append path ``snapshot_today()`` uses, then delete each fully-absorbed pending
    file.

    Runs in the ``--nightly`` path, BEFORE ``collect_boards()``: once a replayed
    session's row lands in ``snapshots.jsonl`` here, ``collect_boards()`` /
    ``grade_boards()`` / ``_merge_into_store()`` pick it up through the ORDINARY
    nightly pipeline on this SAME run — no separate parquet-merge code is needed in
    this hook (masterplan research/PROPHET_PIT_REPLAY_HARNESS_V1.md §0.4: "the
    market's own nightly absorbs its pending dir through its own append + dedupe
    machinery").

    Absent/empty pending dir is an EXACT no-op: one ``is_dir()`` check, zero cost to
    every normal nightly that never sees a pending file.

    ORDER-SAFETY FINDING, RESOLVED AT THE READER (2026-08-18 orchestrator amendment):
    ``scripts/check_surface_freshness.py::check_candidates_freshness`` used to read
    this exact file in REVERSE line order and take the first ``as_of`` it finds as "the
    board's newest date" — a genuine reader of this file's APPEND ORDER, the only one
    found among the ~20 consumers grepped (see that function's own docstring/comment
    for the fix). It now takes the MAX ``as_of`` over every parsed line, so this file's
    append order is no longer load-bearing for that reader — appending a row OLDER than
    the file's current tail (the shape a delayed replay produces, e.g. backfilling
    2026-08-14 after 2026-08-17 has already snapshotted live) is a plain append, not a
    corruption. Every OTHER consumer grepped (``collect_boards`` itself sorts by
    ``as_of`` before returning; every other reader keys a dict by ``as_of`` or
    explicitly sorts before use) was already order-safe. So an out-of-order row is
    APPENDED, not refused — the same idempotent-per-``as_of`` rule as any other row —
    and a ``::notice`` names the session so a delayed absorb is visible in the nightly
    log rather than silent.
    """
    if not PENDING_REPLAY_DIR.is_dir():
        return {"absorbed": 0, "refused": 0, "dir_present": False, "files": 0}
    files = sorted(PENDING_REPLAY_DIR.glob("*.json"))
    if not files:
        return {"absorbed": 0, "refused": 0, "dir_present": True, "files": 0}

    absorbed = 0
    refused = 0
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - unreadable is disclosed, not fatal
            print(f"::warning title=pit-replay-absorb-unreadable::{path.name} is not "
                  f"readable JSON ({exc}); leaving it in place", flush=True)
            refused += 1
            continue
        if doc.get("schema") != "pit_replay.pending/v1" or doc.get("market") != "us":
            print(f"::warning title=pit-replay-absorb-schema::{path.name} does not "
                  "carry schema=pit_replay.pending/v1 market=us; leaving it in place",
                  flush=True)
            refused += 1
            continue

        rows = doc.get("rows") or []
        if not rows:
            # Nothing to absorb (e.g. the US ledger half refused at replay time and
            # only the plans half proceeded) — the pending file's only remaining job
            # was to be discoverable, and an empty rows list has nothing left to do.
            path.unlink()
            absorbed += 1
            continue

        existing = _snapshot_existing_as_of()
        dated_existing = sorted(x for x in existing if x)
        current_max = dated_existing[-1] if dated_existing else None
        ok = True
        n_absorbed_here = 0
        for row in rows:
            as_of = row.get("as_of")
            if not as_of:
                print(f"::warning title=pit-replay-absorb-no-as-of::a row in "
                      f"{path.name} carries no as_of; leaving the file in place",
                      flush=True)
                ok = False
                break
            if as_of in existing:
                n_absorbed_here += 1
                continue
            if current_max is not None and as_of < current_max:
                # Every known reader of this file is now order-safe (see the
                # docstring above), so this is a disclosed APPEND, not a refusal —
                # the row still lands, idempotent-per-as_of like any other.
                print(f"::notice title=pit-replay-absorb-out-of-order::{path.name} "
                      f"row as_of={as_of} is OLDER than the current "
                      f"{SNAPSHOTS_JSONL.name} tail ({current_max}); absorbing it "
                      "out of order (a delayed replay session) — every consumer of "
                      "this file reads by as_of value, not by append position.",
                      flush=True)
            _append_snapshot_row(row)
            existing.add(as_of)
            current_max = as_of if current_max is None else max(current_max, as_of)
            n_absorbed_here += 1
        if ok and n_absorbed_here == len(rows):
            path.unlink()
            absorbed += 1
        else:
            refused += 1

    if not quiet and files:
        print(f"[pit_replay_absorb] {absorbed} absorbed, {refused} refused, of "
              f"{len(files)} pending file(s)")
    return {"absorbed": absorbed, "refused": refused, "dir_present": True,
            "files": len(files)}


# --------------------------------------------------------------------------- #
# store management
# --------------------------------------------------------------------------- #
_DEDUP_KEYS = ["as_of", "ticker", "lane", "horizon"]

# Columns retired from the ledger schema. Dropped by NAME (never by null-ness) from
# every frame this script writes or returns, on BOTH merge exits — the legacy store
# carries them, so a retirement that only stops writing them leaves the store-merge
# carry path re-emitting the column forever.
#   species_id (retired 2026-08-04): written as a literal None on every row since
#   inception — no species uniquely binds this ledger, so it could never populate.
#   Known consumers (engine/standout_audit.py, engine/neuralweb/query.py) read it
#   through .get() and keep emitting null, unchanged.
_RETIRED_LEDGER_COLS = ["species_id"]


def _drop_retired(df: pd.DataFrame) -> pd.DataFrame:
    """Shed _RETIRED_LEDGER_COLS from a ledger frame (no-op when absent)."""
    cols = [c for c in _RETIRED_LEDGER_COLS if c in df.columns]
    return df.drop(columns=cols) if cols else df


# ---------------------------------------------------------------------------
# P2 — board tenure stamping for H5 (PREREGISTRATION.md §2.4)
# ---------------------------------------------------------------------------
# DESIGN NOTE (P2 implementation, 2026-07-05):
#
# prereg §2.4 mandates stamping `hold_days` = on-board tenure (count of
# consecutive prior as_of dates in any lane) on every NEW board row.  The
# existing `hold_days` column in the ledger already carries `hold.days_basing`
# (basing-state tenure, a DIFFERENT quantity).  Overwriting that column would
# corrupt historical rows and produce a semantically ambiguous column.
#
# COLUMN NAME RULING (Fable 2026-07-05):
#   board_tenure_days is the canonical column name for the prereg §2.4 quantity.
#   It does not collide with hold_days (which carries days_basing).
#   validate_factor_h5.py must read board_tenure_days (not hold_days).
#
# RETRO-STAMP HONESTY (FIX-6):
#   Historical rows ARE retro-stamped with PIT-honest board_tenure_days whenever
#   re-graded.  The count uses only dates strictly < as_of_str (verified correct).
#   This is intentional and blessed: it back-fills H5's substrate honestly for
#   rows that predated the board_tenure_days column.  The value is point-in-time
#   correct because it only consults dates strictly prior to the row's own as_of.
#
# TIER CASCADE:
#   `tier_cascade` is already extracted from the board row in `_row_features`
#   (line ~218) and already stamped in `grade_boards` (line ~496).  No new
#   code is needed for that field — this comment documents the audit finding.
#
# FAIL-OPEN GUARANTEE:
#   `_board_tenure` never raises.  If the existing store is absent or the
#   ticker/lane is not found, it returns None (field = NULL on new row).  NULL
#   on a new row signals "tenure not computable" and prevents H5 from treating
#   it as 0 days (which would spuriously exclude names from the ≥10 floor).

def _board_tenure(
    ticker: str,
    lane: str,
    as_of_str: str,
    stored_df: pd.DataFrame | None,
    _presence_map: dict[str, set] | None = None,
) -> int | None:
    """Compute on-board tenure = count of consecutive prior as_of dates
    where `ticker` appears in any lane in the ledger, counting back from
    the board date immediately before `as_of_str`.

    Implements PREREGISTRATION.md §2.4 definition:
      "count of consecutive prior as_of dates on which the ticker appears
       in any lane — explicitly NOT hold.days_basing"

    Parameters
    ----------
    ticker : str
    lane : str  (unused in the count; tenure counts presence in ANY lane)
    as_of_str : str  "YYYY-MM-DD"
    stored_df : pd.DataFrame | None  — the accumulated ledger (retro_grades)
                before merging today's rows (used for date enumeration).
    _presence_map : dict[str, set] | None  — optional running in-memory map
                keyed by as_of_str → set of tickers.  When provided, this is
                consulted IN ADDITION to stored_df so that consecutive as_of
                dates processed in the same grade_boards call can see each
                other (FIX-5: in-batch tenure blindness fix).  Caller must
                populate and maintain this map as each board date is graded.

    Returns
    -------
    int | None — consecutive prior dates on board, or None if not computable.

    RETRO-STAMP HONESTY (FIX-6):
      Historical rows ARE retro-stamped with PIT-honest tenure when re-graded.
      The count uses only dates strictly < as_of_str, so it is point-in-time
      correct.  This is intentional and blessed: it back-fills H5's substrate
      honestly for rows that were first graded before the board_tenure_days
      column existed.
    """
    try:
        # Build the combined date→tickers mapping from stored_df + presence_map
        date_ticker_sets: dict[str, set] = {}

        if stored_df is not None and not stored_df.empty:
            if "as_of" not in stored_df.columns or "ticker" not in stored_df.columns:
                # stored_df schema mismatch — fall through to presence_map only
                pass
            else:
                sub = (stored_df[stored_df["horizon"] == 5]
                       if "horizon" in stored_df.columns else stored_df)
                for d, g in sub.groupby("as_of"):
                    date_ticker_sets[d] = set(g["ticker"].dropna().tolist())

        # Overlay in-memory presence map (in-batch dates not yet persisted)
        if _presence_map:
            for d, tickers in _presence_map.items():
                if d in date_ticker_sets:
                    date_ticker_sets[d] = date_ticker_sets[d] | tickers
                else:
                    date_ticker_sets[d] = set(tickers)

        if not date_ticker_sets:
            return None  # no history at all

        # Unique sorted as_of dates that pre-date today's board
        all_dates = sorted(date_ticker_sets.keys())
        prior_dates = [d for d in all_dates if d < as_of_str]
        if not prior_dates:
            return 0  # first ever appearance

        # Walk backward from the last prior date, counting consecutive dates
        # where the ticker appeared.  A record-date absence stops the streak;
        # calendar gaps between record dates do not (the ledger only holds
        # trading-day as_of records, not every calendar day).
        count = 0
        for d in reversed(prior_dates):
            if ticker in date_ticker_sets.get(d, set()):
                count += 1
            else:
                break
        return count
    except Exception:  # noqa: BLE001 — fail-open
        return None


#: Price-derived measurement columns. Everything here is a function of the close panel,
#: so re-computing it after the breadth caches are re-based RESTATES a published number.
#: Everything NOT here (regime stamps, archetype, board_tenure_days, the evidence-stack
#: strata, new spine columns) is an annotation and still accrues onto historical rows —
#: that is what keeps schema-union and the backfills working.
_FROZEN_PRICE_COLS = [
    "entry_date",                                   # the fill bar itself is calendar-derived
    "ret", "spy_ret", "excess_spy", "mae_close_excess_spy",
    "sector_etf", "etf_ret", "excess_sector", "mae_close_excess_sector",
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63",
    "terminal_state_clean15_126", "terminal_state_clean8_21", "post_cushion_breach",
    "price_source", "price_basis",                  # the basis stamp travels with its row
]


def _freeze_graded_prices(fresh: pd.DataFrame, stored: pd.DataFrame,
                          key_cols: list[str]) -> pd.DataFrame:
    """Restore the STORED price-derived values onto any row that was already graded.

    A graded row is a POINT-IN-TIME CLAIM. The breadth close caches are re-based in
    place, so the same (ticker, date) reads differently on different days and a plain
    keep-FRESH merge silently rewrites history: measured 2026-08-06, re-grading the
    shipped ledger moved 75 already-published rows, 19 of them materially (worst
    −1.94pp, LPG 2026-06-18 H5). Restating a track record without saying so is worse
    than a disclosed basis change, so the measurement is frozen at first grade and the
    era is separated by the `price_basis` stamp instead (null = pre-2026-08-06).

    Only rows whose STORED `ret` is non-null are frozen — an unscored row that has now
    matured still takes the fresh grade, which is the whole point of the nightly.
    """
    if fresh.empty or stored.empty or not key_cols:
        return fresh
    if "ret" not in stored.columns:
        return fresh

    graded = stored[stored["ret"].notna()]
    if graded.empty:
        return fresh
    cols = [c for c in _FROZEN_PRICE_COLS if c in stored.columns]
    if not cols:
        return fresh

    prior = (graded.drop_duplicates(subset=key_cols, keep="last")
             .set_index(key_cols)[cols])
    out = fresh.set_index(key_cols)
    common = out.index.intersection(prior.index)
    if len(common):
        for c in cols:
            if c not in out.columns:
                out[c] = None
            out.loc[common, c] = prior.loc[common, c]
        # ERA MARKER. A row frozen at a value this ladder did not produce must not
        # inherit this ladder's stamp — that would assert a basis nobody verified. The
        # test is what the STORE knows, never what the fresh row computed: a row whose
        # stored price_basis is absent or null was graded before the boundary, so it is
        # stamped PRE_ERA_BASIS ("priced from the breadth cache at grade time, basis
        # unverified"). That makes the two eras separable in one column instead of by
        # archaeology, and it is why history is disclosed rather than restated.
        if "price_basis" in out.columns:
            if "price_basis" in graded.columns:
                prior_basis = (graded.drop_duplicates(subset=key_cols, keep="last")
                               .set_index(key_cols)["price_basis"])
                pre_mask = prior_basis.reindex(common).isna().to_numpy()
            else:
                pre_mask = np.ones(len(common), dtype=bool)   # store predates the stamp
            idx = common[pre_mask]
            if len(idx):
                out.loc[idx, "price_basis"] = PRE_ERA_BASIS
                if "price_source" in out.columns:
                    out.loc[idx, "price_source"] = None
    out = out.reset_index()
    out.attrs.update(fresh.attrs)
    out.attrs["frozen_rows"] = int(len(common))
    return out


def _merge_into_store(fresh: pd.DataFrame) -> pd.DataFrame:
    """Merge freshly-graded rows into the accumulated retro_grades.parquet store.

    Strategy: read the existing store (if any), union with fresh rows, de-duplicate
    on (as_of, ticker, lane, horizon) preferring the fresh row (it uses the latest
    price cache), and write the result back.  The merged frame is returned so the
    caller can pass it directly to build_track — guaranteeing the track is ALWAYS
    built from the full accumulated history, never just from the rows that happened
    to mature in this run.

    W0.1 B-b: schema-union — new spine columns (fwd_mfe_*, terminal_state_*,
    post_cushion_breach, regime stamp, archetype) are added to the
    stored frame with NaN/None for legacy rows that predate this PR. Merge is
    keep-FRESH on the dedup key for ANNOTATIONS, so new columns and backfills still
    reach historical rows.

    2026-08-06 — the price-derived columns are the exception. This docstring used to
    justify wholesale replacement as "a deterministic re-computation from prices"; that
    premise is false, because the breadth close caches are re-based IN PLACE and the same
    (ticker, date) reads differently on different days. Re-grading the shipped ledger on
    2026-08-06 moved 75 already-published rows, 19 materially. `_freeze_graded_prices`
    therefore restores the stored values of `_FROZEN_PRICE_COLS` on any row that already
    carries a grade. The PIT fire log is snapshots.jsonl; this parquet is the derived
    grade store, and its grades are now write-once.

    If fresh is empty AND the store already exists, the store is returned as-is
    (no write needed).  This is the key guard against the empty:true regression."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if RETRO_PARQUET.exists():
        # shed retired columns at READ time so both exits below are covered — including
        # the fresh.empty return, which would otherwise hand a retired column downstream
        # on any night that matures no new rows
        stored = _drop_retired(pd.read_parquet(RETRO_PARQUET))
    else:
        stored = pd.DataFrame()

    if fresh.empty:
        return stored  # nothing new — return the accumulated store unchanged

    if stored.empty:
        merged = fresh.copy()
    else:
        # schema-union: add any new columns from fresh to stored (legacy rows get NaN)
        for col in fresh.columns:
            if col not in stored.columns:
                stored[col] = None
        # fresh rows take precedence: drop stored rows that overlap with fresh on
        # the dedup key, then concat.
        key_cols = [c for c in _DEDUP_KEYS if c in fresh.columns and c in stored.columns]
        fresh_keys = set(map(tuple, fresh[key_cols].values.tolist()))
        mask = stored.apply(lambda r: tuple(r[k] for k in key_cols) not in fresh_keys, axis=1)
        # ...except the price-derived measurement, which is FROZEN once graded.
        fresh = _freeze_graded_prices(fresh, stored, key_cols)
        merged = pd.concat([stored[mask], fresh], ignore_index=True)

    merged = _drop_retired(merged)
    merged.to_parquet(RETRO_PARQUET, index=False)
    return merged


# W0.1 B-b: regime_vector backfill constants
_REGIME_STAMP_COLS = [
    "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
    "risk_radar_state", "regime_vector_degraded", "vector_asof", "staleness_hours",
]


def _backfill_regime_stamps(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Backfill null regime_vector stamps on historical rows where the persisted
    regime_vector.parquet covers the row's as_of date.

    §3.4 PIT constraint: reads ONLY the persisted daily vector (never latest-state).
    Only fills rows where ALL stamp columns are null (never overwrites non-null).
    Returns (updated_df, n_newly_stamped) so main() can print the unstamped count.
    """
    if df.empty:
        return df, 0

    # Identify rows that are completely unstamped
    stamp_cols_present = [c for c in _REGIME_STAMP_COLS if c in df.columns]
    if not stamp_cols_present:
        return df, 0

    unstamped_mask = df[stamp_cols_present].isna().all(axis=1)
    if not unstamped_mask.any():
        return df, 0

    newly_stamped = 0
    df = df.copy()
    for idx in df.index[unstamped_mask]:
        as_of = df.at[idx, "as_of"]
        stamp = get_vector_for_date(as_of)
        # only apply if the vector actually covers this date (vector_asof is not None)
        if stamp.get("vector_asof") is not None:
            for col in stamp_cols_present:
                df.at[idx, col] = stamp.get(col)
            newly_stamped += 1

    return df, newly_stamped


def _backfill_archetype(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Backfill null `archetype` from the PIT archetype store (FIX-6 precedent).

    Each row resolves at its OWN as_of (greatest asof_date <= as_of), so a backfilled
    label is exactly what the row would have carried at grade time — the same PIT-honest
    retro-stamp blessed for board_tenure_days.  Fill-null-only: a payload archetype is
    never overwritten, and a row the store cannot cover stays null.
    Returns (updated_df, n_newly_filled) so main() can print the still-null count.
    """
    if df.empty or not {"archetype", "ticker", "as_of"} <= set(df.columns):
        return df, 0

    null_mask = df["archetype"].isna()
    if not null_mask.any():
        return df, 0

    df = df.copy()
    # (ticker, as_of) → label.  archetype_asof caches the parquet read itself; this
    # caches the per-row PIT scan, which repeats across lanes and horizons.
    cache: dict[tuple, str | None] = {}
    n_filled = 0
    for idx in df.index[null_mask]:
        tk = df.at[idx, "ticker"]
        as_of = df.at[idx, "as_of"]
        if tk is None or pd.isna(tk) or as_of is None or pd.isna(as_of):
            continue
        key = (str(tk), str(as_of))
        if key not in cache:
            cache[key] = _archetype_pit(key[0], key[1])
        if cache[key] is None:
            continue
        df.at[idx, "archetype"] = cache[key]
        n_filled += 1

    return df, n_filled


# --------------------------------------------------------------------------- #
# outcomes strip (W2)
# --------------------------------------------------------------------------- #

def emit_outcomes(boards: list[dict], names: pd.DataFrame) -> dict:
    """Build the 'recently surfaced → outcome' strip artifact.

    Logic:
    - Collect every ticker that appeared on the BUY lane within the last
      OUTCOMES_LOOKBACK_BOARDS board dates.
    - Find tickers that are ABSENT from the CURRENT (most-recent) buy board.
    - For each such exited ticker, compute pct change from the NEXT session's close
      after first_surfaced to the close on the date it left the board.
    - Skip rows with missing prices (never fabricate) — but COUNT them: the broad
      cache is current-membership only, so a name that left the board BECAUSE it
      collapsed and got delisted is exactly the name with no price here. Silently
      dropping it tilts the displayed win/loss mix toward survivors. The count is
      emitted as summary.n_skipped_no_price so the strip header can disclose it.
    - Sort by |pct_since| desc, cap at 15 rows.
    - Include summary: n_running, n_stopped, median_pct, n_skipped_no_price.

    Returns the dict to be serialised as us_board_outcomes.json.
    Degrades to {"empty": True, ...} only when genuinely no exited names exist.

    THREE CONVENTION FIXES (G4, 2026-08-06) — all of them lowered the headline
    ---------------------------------------------------------------------------
    1. NEXT-BAR FILL.  The buy price was the close ON first_surfaced — the bar the
       board is computed from and published that evening.  It is unbuyable.  Worth
       +3.4pp of win rate and 66% of the reported average return, measured on the
       shipped artifact.  Entry is now the next session's close, the same convention
       `build_track`, `engine.grading.fill_index` and `track_scoring` already use;
       a name whose next bar has not printed is skipped and counted, never filled.
    2. MARK AT THE EXIT BAR.  Every row is an EXITED name, and each was marked at
       TODAY's close — so a name that left the board in June kept accruing July's
       move under the board's name.  The strip claims "surfaced → outcome", and the
       outcome ends when the board stopped saying it.
    3. FLATS STAY IN THE DENOMINATOR.  `win_rate` divided by running+stopped only,
       deleting every |move| <= 2% row (96 of 321 on the shipped artifact).  A flat
       is a real outcome of a buy call — it is simply not a win — and a denominator
       conditioned on the size of the result is the resolution-conditioned
       denominator that deletes exactly the rows a reader wants counted.
    """
    if not boards:
        return {"empty": True, "as_of": str(dt.date.today()), "reason": "no boards"}

    # Last OUTCOMES_LOOKBACK_BOARDS board snapshots (already sorted asc)
    window = boards[-OUTCOMES_LOOKBACK_BOARDS:]
    if not window:
        return {"empty": True, "as_of": str(dt.date.today()), "reason": "window empty"}

    current_board = window[-1]
    current_as_of = current_board.get("as_of", "")
    current_buy_tickers: set[str] = {
        r["ticker"] for r in current_board.get("rows", [])
        if r.get("lane") in ("buy", "laggards") or r.get("lane") == "buy"
    }
    # More precisely: only the "buy" lane per the invariants
    current_buy_tickers = {
        r["ticker"] for r in current_board.get("rows", [])
        if r.get("lane") == "buy"
    }

    # Build a map: ticker -> {first_surfaced, sector, lane} from the window (buy lane only)
    first_seen: dict[str, dict] = {}
    for b in window:
        as_of_str = b.get("as_of", "")
        for r in b.get("rows", []):
            if r.get("lane") != "buy":
                continue
            tk = r.get("ticker")
            if not tk:
                continue
            if tk not in first_seen:
                first_seen[tk] = {
                    "first_surfaced": as_of_str,
                    "sector": r.get("sector"),
                    "lane": r.get("lane"),
                }

    # Find tickers that were in the window's buy lane but are NOT in the current buy board
    exited = {tk: meta for tk, meta in first_seen.items() if tk not in current_buy_tickers}

    if not exited:
        return {
            "empty": True,
            "as_of": current_as_of,
            "reason": "all window tickers still on the buy board",
        }

    # Price lookups: use the broad closes DataFrame (columns=ticker, index=DatetimeIndex)
    last_price_date = names.index.max() if not names.empty else None
    rows_out = []
    # survivorship disclosure: exited names with no usable price path in the broad
    # cache (missing column / all-NaN / series ends before first_surfaced) — likely
    # delisted, i.e. the very outcomes the strip would otherwise hide.
    skipped_no_price: list[str] = []
    for tk, meta in exited.items():
        if tk not in names.columns:
            skipped_no_price.append(tk)
            continue
        ser = names[tk].dropna()
        if ser.empty:
            skipped_no_price.append(tk)
            continue

        first_surfaced_str = meta["first_surfaced"]
        try:
            first_dt = pd.Timestamp(first_surfaced_str)
        except Exception:
            continue

        # G4.1 NEXT-BAR FILL: side="right" lands on the first bar STRICTLY AFTER
        # first_surfaced.  side="left" returned the surfaced bar itself whenever that
        # date was a session — the close the board was computed from, published after
        # the bell.  Where first_surfaced is not a session both sides agree, so this
        # only ever moves the fill off an unbuyable bar.
        idx_first = ser.index.searchsorted(first_dt, side="right")
        if idx_first >= len(ser):
            # The next bar has not printed yet — in flight, not fillable. Counted as a
            # skip rather than filled at the signal bar (which is the defect above).
            skipped_no_price.append(tk)
            continue
        surfaced_price = float(ser.iloc[idx_first])
        if surfaced_price <= 0:
            continue

        # Determine exit_date: first board date in window where this ticker is absent.
        # Computed BEFORE the mark, because it IS the mark date (G4.2).
        exit_date_str = current_as_of  # fallback: use current as_of as exit date
        appeared_before = False
        for b in window:
            tickers_in_b_buy = {
                r["ticker"] for r in b.get("rows", []) if r.get("lane") == "buy"
            }
            if tk in tickers_in_b_buy:
                appeared_before = True
            elif appeared_before:
                exit_date_str = b.get("as_of", current_as_of)
                break

        # G4.2 MARK AT THE EXIT BAR: the last close at or before the date the name
        # left the board, never today's.  Falls back to the last available close only
        # when the exit date is unreadable or precedes the fill (never silently
        # extends the window past the exit).
        exit_idx = len(ser) - 1
        try:
            _exit_dt = pd.Timestamp(exit_date_str)
            _pos = ser.index.searchsorted(_exit_dt, side="right") - 1
            if _pos >= idx_first:
                exit_idx = min(_pos, len(ser) - 1)
        except Exception:
            pass
        last_price = float(ser.iloc[exit_idx])
        mark_date_str = ser.index[exit_idx].date().isoformat()
        pct_since = (last_price / surfaced_price - 1.0) * 100.0

        # days_on_board: count of board dates the ticker appeared on the buy lane
        days_on_board = sum(
            1 for b in window
            if any(r.get("ticker") == tk and r.get("lane") == "buy"
                   for r in b.get("rows", []))
        )

        if pct_since > 2.0:
            status = "running"
        elif pct_since < -2.0:
            status = "stopped"
        else:
            status = "flat"

        rows_out.append({
            "ticker": tk,
            "sector": meta.get("sector") or "",
            "first_surfaced": first_surfaced_str,
            "surfaced_price": round(surfaced_price, 2),
            "last_price": round(last_price, 2),
            "pct_since": round(pct_since, 1),
            "days_on_board": days_on_board,
            "exit_date": exit_date_str,
            # The bar `last_price` was actually read from (G4.2). Equal to the last
            # session at or before exit_date; present so a reader can check the mark
            # is not today's close on a name that left the board weeks ago.
            "mark_date": mark_date_str,
            "status": status,
            "lane": meta.get("lane") or "buy",
        })

    if not rows_out:
        return {
            "empty": True,
            "as_of": current_as_of,
            "reason": "no exited tickers had price data",
            "n_skipped_no_price": len(skipped_no_price),
            "skipped_no_price": sorted(skipped_no_price)[:15],
        }

    # Full-set metrics over EVERY exited name, computed BEFORE the display cap. These
    # feed the header + sub-line so the win/loss mix reflects the whole record, not the
    # handful of biggest movers that survive the cap. (Pre-fix, n_running / n_stopped
    # were computed post-cap and read "0 stopped" whenever the top movers were all
    # winners — contradicting win_rate on the same strip.)
    n_running = sum(1 for r in rows_out if r["status"] == "running")
    n_stopped = sum(1 for r in rows_out if r["status"] == "stopped")
    n_flat = sum(1 for r in rows_out if r["status"] == "flat")
    # G4.3: EVERY priced exited name is in the denominator. `n_running + n_stopped`
    # deleted the flats — 96 of 321 rows on the shipped artifact — and a flat is not a
    # missing outcome, it is a buy call that went nowhere. Conditioning the denominator
    # on the SIZE of the result is the same shape as conditioning it on the direction.
    _denom = n_running + n_stopped + n_flat
    win_rate = round(n_running / _denom, 3) if _denom > 0 else None
    _all_pcts = [r["pct_since"] for r in rows_out]
    avg_pct = round(sum(_all_pcts) / len(_all_pcts), 1) if _all_pcts else None
    median_pct = float(sorted(_all_pcts)[len(_all_pcts) // 2]) if _all_pcts else 0.0
    n_total = len(rows_out)

    # Sort by |pct_since| desc, cap the DISPLAY only (summary above is full-set).
    rows_out.sort(key=lambda r: abs(r["pct_since"]), reverse=True)
    rows_out = rows_out[:OUTCOMES_DISPLAY_CAP]

    return {
        "as_of": current_as_of,
        "rows": rows_out,
        "summary": {
            "n_running": n_running,
            "n_stopped": n_stopped,
            "n_flat": n_flat,
            # total exited names vs how many the display cap shows — lets the strip
            # disclose "showing N of M" when the record is longer than the cap.
            "n_total": n_total,
            "n_shown": len(rows_out),
            "median_pct": round(median_pct, 1),
            # names excluded for lack of any usable price path (see loop above) —
            # rendered as "(N names excluded: no price / delisted)" in the strip
            # header so the mix never silently reads as survivor-complete.
            "n_skipped_no_price": len(skipped_no_price),
            "skipped_no_price": sorted(skipped_no_price)[:15],
            # full-set metrics (over all exited rows, before the display cut)
            "win_rate": win_rate,
            "avg_pct": avg_pct,
            # G4 conventions, stated where the numbers are.
            "conventions": {
                "entry": "next session's close after first_surfaced (the surfaced "
                         "bar is the bar the board is computed from — unbuyable)",
                "mark": "close on the date the name left the buy board, not today's",
                "win_rate_denominator": "every priced exited name, flats included",
            },
        },
    }


# --------------------------------------------------------------------------- #
# TRD popup — buy-lane episode ledger (track_ledger/v1)
# --------------------------------------------------------------------------- #

def _load_retro_excess_21() -> dict[tuple[str, str], float]:
    """Map (as_of, ticker) -> matured 21d excess_spy (fraction) from the retro-grades
    store, for the ledger's `x`/`m` join. Read once, cheaply; empty dict when the
    store is absent (first run) or lacks a matured 21d row for a pair. Read-only —
    NEVER writes retro_grades.parquet."""
    out: dict[tuple[str, str], float] = {}
    if not RETRO_PARQUET.exists():
        return out
    try:
        df = pd.read_parquet(RETRO_PARQUET, columns=["as_of", "ticker", "horizon", "lane", "excess_spy"])
    except Exception:  # noqa: BLE001 — try full read if the column subset is unavailable
        try:
            df = pd.read_parquet(RETRO_PARQUET)
        except Exception:  # noqa: BLE001
            return out
    if df.empty or "excess_spy" not in df.columns:
        return out
    sub = df[(df["horizon"] == 21) & (df["lane"] == "buy")]
    for _i, r in sub.iterrows():
        ex = r.get("excess_spy")
        if ex is None or (isinstance(ex, float) and math.isnan(ex)):
            continue
        key = (str(r.get("as_of")), str(r.get("ticker")))
        out[key] = float(ex)
    return out


def _ob_mask(close: pd.Series) -> pd.Series | None:
    """Daily-aligned bool: the 3D StochRSI is overbought (k or d >= 80).

    The desk's OWN cycle-top read — engine/hold.py's LAUNCHED leg, pre-registered in
    research/entry_timing/WAVE6_PREREG.md §3 ("oversold → overbought"). Reused here as
    the episode's TARGET exit so the track record measures the system's own sell
    discipline instead of an arbitrary calendar date.

    CAUSAL AND — SINCE 2026-08-07 — STABLE. These are different properties and this
    docstring once claimed only the first.

    * CAUSAL (always held): known-date mapped, so a 3D bucket is only readable once
      complete and this can never peek. Truncating TRAILING bars leaves every past flag
      unchanged — pinned by tests/test_ob_mask_start_invariance.py.
    * STABLE (repaired): `_tf_bars` used to resample on `3B`, whose bin edges anchored to
      the SERIES' FIRST TIMESTAMP. `emit_ledger` calls this on the full rolling close
      cache, and the smallcap/midcap `data/*/_closes_cache.parquet` stores are a ROLLING
      window (first date moved 2023-06-27 -> 2023-07-03 across three sessions in early Aug
      2026). Moving the start re-phased every 3D bucket in the WHOLE history, so overbought
      flags from weeks ago flipped and the exit bar of an episode that closed long ago
      moved. PR #4732 migrated `_tf_bars` to an ABSOLUTE SESSION ANCHOR in place; this
      function imports it directly, so the repair reached here too.

    Measured before the repair (reports/ob_mask_track_record_blast_radius.md, regenerate
    with scripts/measure_ob_mask_track_record_blast_radius.py). Dropping 4 leading sessions
    with the end date and every retained price held IDENTICAL moved 126 of 359
    already-matured episodes (35.1%), max 28.9 pp — on zero new information. The phase
    depended on (leading bars dropped) mod 3, so a re-phase was not even monotone in how
    much history rolled off. Under the absolute anchor that controlled movement is 0 of 359.

    THE ERA BOUNDARY. `site/factordata/us_track_ledger.json` is public — the Track-record
    dialog, the hero win-rate/expectancy on the Track-record page, and the dashboard chip.
    #4732 moved every published historical number here without appearing in this file's
    diff, without a mention in its blast-radius report, and without R5's era stamp (which
    rides `cascade`/`tier_stream`/`signal_gate` — none of which this path touches). Ruled
    on 2026-08-07 (research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md §0.1): the
    `abs-session-2026-08-06` era EXTENDS to this artifact. `emit_ledger` now stamps
    `meta.anchor_era` and carries the frozen pre-era headline in `meta.pre_era`
    (engine/track_era.py), and `engine.track_ledger.atomic_write` refuses any future write
    that moves the headline without a matching stamp.
    """
    try:
        c = close.dropna()
        if len(c) < 200:
            return None
        s3, k3 = _tf_bars(c, 3)
        k, d = _stoch_rsi_kd(s3)
        return _to_daily(((k >= _OB) | (d >= _OB)).fillna(False), k3, c.index).fillna(False).astype(bool)
    except Exception:  # noqa: BLE001 — no oscillator → the episode runs to its horizon
        return None


def emit_ledger(boards: list[dict], names: pd.DataFrame,
                etfs: pd.DataFrame | None = None) -> dict:
    """Build the buy-lane EPISODE ledger for the Track-record popup.

    Grain: one row per CONTIGUOUS board run (engine.track_scoring.build_episodes) — a
    name that leaves and returns yields two episodes, each with its own entry.

    Scoring (engine.track_scoring — see that module for why each rule exists):
      * fill  = the NEXT session's close after the board date. The board is computed
                FROM the board date's close and published that evening, so the signal
                bar itself is unbuyable. The pre-2026-07-26 ledger entered on it and
                that single bar was worth +5.5pp of win rate and 69% of the reported
                average return.
      * exit  = the FIRST of: the 3D-StochRSI overbought target, a break of the
                90-session trough × 0.97 stop, or the forced HORIZON verdict. The rule
                legs may only shorten the hold — never extend it past the horizon.
      * gate  = only episodes with >= HORIZON forward bars are summarised; younger
                ones ride as st='onboard' with a live unrealised mark and are counted
                in n_inflight. Excluding by AGE is symmetric; excluding by OUTCOME is
                not, and would delete the losers (module docstring, rule 1).

    Headline metric is ABSOLUTE P&L (what a reader actually experiences); excess vs
    SPY ships alongside in each row's `x`. Survivorship: names with no usable price
    path are counted into n_skipped_no_price, never silently dropped.

    Returns the track_ledger/v1 dict (JSON-safe via engine.track_ledger.build_shell).
    """
    from engine import track_era as _te
    from engine import track_ledger as _tl
    from engine import track_scoring as _ts

    bench = {"code": "SPY", "en": "S&P 500", "zh": "标普500"}
    empty_summary = _ts.summarize([], metric="pnl", horizon=LEDGER_HORIZON)

    # ERA STAMP (ruled 2026-08-07 — research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md §0.2).
    # `_ob_mask` inherits `_tf_bars`' absolute session anchor by direct import, so the
    # buckets under every already-graded row changed when #4732 landed WITHOUT this path
    # inheriting the field that would tell a reader they changed. This says which
    # construction produced the numbers, and carries the pre-era headline it replaced so
    # nothing is overwritten. Stamped on EVERY return path, including the degenerate one —
    # a provenance field with holes is a field a reader has to already know to trust.
    era_meta = _te.us_era_meta()

    # The last session this grading run actually saw — see the priced_through block
    # below for why the artifact has to carry it. Stamped on EVERY return path,
    # including the degenerate one: a provenance field with holes in it is a field a
    # reader has to already know the shape of to trust.
    priced_through = (str(pd.DatetimeIndex(names.index).max())[:10]
                      if names is not None and not getattr(names, "empty", True) else None)

    if not boards:
        return _tl.build_shell(
            "US", str(dt.date.today()), "accruing", bench,
            summary=empty_summary, rows=[], grain="episode",
            survivorship={"n_skipped_no_price": 0},
            extra_meta={"priced_through": priced_through, **era_meta},
        )

    current_as_of = boards[-1].get("as_of", "")

    # board_day -> buy-lane tickers, plus display metadata from the LATEST board a
    # ticker appeared on (freshest sector / rank / tier).
    board_days: dict[str, set[str]] = {}
    meta_by_tk: dict[str, dict] = {}
    definition_by_admission: dict[tuple[str, str], str] = {}
    n_boards_predefinition = 0
    for b in boards:
        as_of_str = b.get("as_of", "")
        if not as_of_str:
            continue
        if as_of_str < LEDGER_HISTORY_FROM:
            n_boards_predefinition += 1        # different instrument — see the constant
            continue
        day = board_days.setdefault(as_of_str, set())
        for r in b.get("rows", []):
            if r.get("lane") != "buy":
                continue
            tk = r.get("ticker")
            if not tk:
                continue
            day.add(tk)
            meta_by_tk[tk] = {"sector": r.get("sector"), "rank": r.get("position"),
                              "tier": r.get("align_tier")}
            # The board definition belongs to the admission DATE, not to the
            # ticker's latest appearance.  A name can span an era boundary or
            # leave and re-enter under another selection instrument.
            definition_by_admission[(as_of_str, tk)] = _norm_definition(b.get("rank_by"))

    bench_ser = None
    if etfs is not None and BENCH in getattr(etfs, "columns", []):
        bench_ser = etfs[BENCH].dropna()

    rows_out: list[dict] = []
    scored: list[dict] = []
    skipped_no_price: list[str] = []
    n_inflight = 0
    _ob_cache: dict[str, pd.Series | None] = {}

    def _unscored(tk: str, d0: str) -> dict:
        """A persistent row for an episode that cannot be priced.

        ROW-PERSISTENCE LAW: an admission is a claim the desk made, and a claim it can
        no longer measure is still a claim. Pre-fix these episodes hit `continue` and
        left NOTHING in the artifact — the name was simply absent from the dialog, and
        the only trace was a count in meta.survivorship that no reader sees. A row that
        says "no price data" is auditable; a missing row is indistinguishable from a
        name that was never picked. Excluded from every summary number (it is not in
        `scored`), so the headline is unmoved.
        """
        m = meta_by_tk.get(tk, {})
        return {
            "t": tk, "nm": None, "sec": m.get("sector"), "grp": None, "d": d0,
            "e": None, "l": None, "p": None, "x": None, "dy": None,
            "st": "unscored", "m": False,
            "rk": m.get("rank"), "tr": m.get("tier"), "fl": [],
            "xr": "no price data",
            "ed": None,
            "bd": definition_by_admission.get((d0, tk)),
        }

    for ep in _ts.build_episodes(board_days):
        tk, d0 = ep["ticker"], ep["entry_date"]
        if tk not in names.columns:
            skipped_no_price.append(tk)
            rows_out.append(_unscored(tk, d0))
            continue
        ser = names[tk].dropna()
        if ser.empty:
            skipped_no_price.append(tk)
            rows_out.append(_unscored(tk, d0))
            continue
        if tk not in _ob_cache:
            _ob_cache[tk] = _ob_mask(ser)

        # stop = a break of the setup's OWN base (engine/hold.py BROKEN), not a flat
        # percentage — the trough is what the bottoming thesis rests on.
        i_sig = ser.index.searchsorted(pd.Timestamp(d0), side="left")
        stop_lvl = None
        if i_sig < len(ser):
            lo = max(0, i_sig - _TROUGH_LB)
            trough = float(ser.iloc[lo:i_sig + 1].min())
            if math.isfinite(trough) and trough > 0:
                stop_lvl = trough * _TROUGH_TOL

        sc = _ts.score_episode(ser, d0, LEDGER_HORIZON, stop_level=stop_lvl,
                               early_exit=_ob_cache[tk], bench_close=bench_ser)
        if sc is None:
            skipped_no_price.append(tk)
            rows_out.append(_unscored(tk, d0))
            continue
        if sc.get("fill_pending"):
            # Surfaced on the newest board — the T+1 fill prints tomorrow. In flight,
            # not a survivorship casualty (conflating the two inflated the skip count
            # to 22 and listed liquid names like DE and F as unpriceable).
            n_inflight += 1
            m = meta_by_tk.get(tk, {})
            rows_out.append({
                "t": tk, "nm": None, "sec": m.get("sector"), "grp": None, "d": d0,
                "e": None, "l": None, "p": None, "x": None, "dy": None,
                "st": "onboard", "m": False,
                "rk": m.get("rank"), "tr": m.get("tier"), "fl": [], "xr": None,
                "ed": None,
                "bd": definition_by_admission.get((d0, tk)),
            })
            continue

        m = meta_by_tk.get(tk, {})
        if sc["matured"]:
            st = "up" if (sc["pnl"] or 0) > 0 else "stopped"
            latest, move = sc["exit"], sc["pnl"]
            sc["board_date"] = d0
            scored.append(sc)
        else:
            st = "onboard"                     # in flight — never in the summary
            n_inflight += 1
            latest = (float(ser.iloc[-1]) if len(ser) else None)
            move = sc["mark"]

        rows_out.append({
            "t": tk, "nm": None, "sec": m.get("sector"), "grp": None,
            "d": d0,
            "e": round(sc["entry"], 2),
            "l": round(latest, 2) if latest is not None else None,
            "p": round(move, 1) if move is not None else None,
            "x": round(sc["excess"], 2) if sc.get("excess") is not None else None,
            "dy": sc["held"],
            "st": st,
            "m": bool(sc["matured"]),
            "rk": m.get("rank"), "tr": m.get("tier"),
            "fl": [],
            "xr": sc.get("exit_reason"),
            "ed": sc.get("entry_date"),
            "bd": definition_by_admission.get((d0, tk)),
        })

    summary = _ts.summarize(scored, metric="pnl", n_inflight=n_inflight,
                            n_skipped=len(skipped_no_price), horizon=LEDGER_HORIZON)
    state = _ts.publish_state(summary)

    _days = sorted(board_days)
    _extra = {"exit_rule": "3D StochRSI >= 80 target · 90d-trough x0.97 stop · "
                           f"{LEDGER_HORIZON}-session forced verdict",
              # History span, so a truncated retro read is visible in the artifact
              # instead of silently shrinking the record (see _git_revisions).
              "history": {"first_board": _days[0] if _days else None,
                          "last_board": _days[-1] if _days else None,
                          "n_boards": len(_days),
                          "scored_from": LEDGER_HISTORY_FROM,
                          "n_boards_before_current_definition": n_boards_predefinition}}
    # PRICE FRONTIER — the last session this grading run actually saw.
    #
    # Unconditional provenance, not an outage disclosure: it is the only field on the
    # artifact that says which price vintage produced these numbers. `as_of` above is the
    # last BOARD date and `continuity.last_session` is the SPY clock — a deliberately
    # different lane (see continuity_block) — so neither answers it, and on 2026-08-06
    # both were read as if they did. That night collect committed prices through 08-05
    # while this grader last ran against a cache stopping at 07-31; downstream
    # (scripts/exit_policy_study.calibrate) compared its own recomputation to this
    # summary and reported the 3-session gap as "the reconstruction drifted". With this
    # stamp the gap is legible from the file alone.
    _extra["priced_through"] = priced_through

    # Era boundary + the frozen pre-era headline (see the era_meta comment above).
    _extra.update(era_meta)

    # Outage disclosure: sessions after the newest snapshot on which no board was
    # recorded. Present in the artifact so the dialog can say so in one quiet line
    # instead of the reader inferring a healthy record from a frozen one.
    cont = continuity_block(boards, names, etfs)
    if cont.get("n_stale_sessions"):
        _extra["continuity"] = cont

    return _tl.build_shell(
        "US", current_as_of, state, bench, summary, rows_out, grain="episode",
        survivorship={"n_skipped_no_price": len(skipped_no_price),
                      "tickers_skipped": sorted(set(skipped_no_price))[:15],
                      # Post-fix these are rows in the artifact, not deletions — the
                      # count stays so the exclusion from the SUMMARY is still stated.
                      "unscored_rows_published": True},
        extra_meta=_extra,
    )


# --------------------------------------------------------------------------- #
# SA-W5: v2 parallel grader lane
# ISOLATION INVARIANT: all v2 functions write ONLY to V2_* paths.
# They NEVER read or write retro_grades.parquet / snapshots.jsonl /
# us_board_track.json — those are the main lane's exclusive files.
# standout_audit.py reads retro_grades.parquet only; v2 rows are invisible to it.
# --------------------------------------------------------------------------- #

def _v2_board_to_record(d: dict) -> dict | None:
    """Parse us_standouts_v2.json into a board record for grading.

    v2 board uses lane names 'entry_open' / 'setting_up' (V2_LANES).
    Applies the same _row_features extraction used by the main lane.
    Returns None when as_of is absent or no rows parse.
    """
    as_of = d.get("as_of")
    if not as_of:
        return None
    rows = []
    for lane in V2_LANES:
        lst = d.get("lanes", {}).get(lane) or []
        for pos, r in enumerate(lst):
            if not isinstance(r, dict):
                continue
            feat = _row_features(r)
            if not feat.get("ticker"):
                continue
            feat["lane"] = f"v2_{lane}"  # prefix keeps v2 lanes distinct from main
            feat["position"] = pos
            feat["dispersion_state"] = _dig(d, ("dispersion_regime", "state"), default=None)
            rows.append(feat)
    if not rows:
        return None
    return {"as_of": as_of, "dispersion_state": None, "rank_by": d.get("rank_by"), "rows": rows}


def snapshot_v2_today() -> str | None:
    """Append today's committed v2 board to the v2 snapshot JSONL.

    Idempotent per as_of. Writes V2_SNAPSHOTS_JSONL ONLY.
    Never reads or writes the main snapshots.jsonl.
    Returns as_of on success, None when artifact absent or empty.
    """
    p = ROOT / V2_BOARD_PATH
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None
    as_of = d.get("as_of")
    if not as_of:
        return None

    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    existing = set()
    if V2_SNAPSHOTS_JSONL.exists():
        for line in V2_SNAPSHOTS_JSONL.read_text().splitlines():
            try:
                existing.add(json.loads(line).get("as_of"))
            except json.JSONDecodeError:
                pass
    if as_of in existing:
        return as_of  # already snapshotted

    # trim to just the grader-relevant fields
    trimmed = {"as_of": as_of, "rank_by": d.get("rank_by"),
               "lanes": d.get("lanes") or {}}
    with V2_SNAPSHOTS_JSONL.open("a") as f:
        f.write(json.dumps(trimmed, separators=(",", ":")) + "\n")
    return as_of


def collect_v2_boards() -> list[dict]:
    """Load v2 boards from V2_SNAPSHOTS_JSONL only (no git-archaeology for v2).

    The v2 board started after SA-W5 merged, so there is no git history to mine.
    Returns list of board records (may be empty).
    """
    boards: dict[str, dict] = {}
    if not V2_SNAPSHOTS_JSONL.exists():
        return []
    for line in V2_SNAPSHOTS_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            snap = json.loads(line)
        except json.JSONDecodeError:
            continue
        b = _v2_board_to_record(snap)
        if b:
            boards[b["as_of"]] = b
    return sorted(boards.values(), key=lambda x: x["as_of"])


def _merge_v2_into_store(fresh: pd.DataFrame) -> pd.DataFrame:
    """Merge v2 grades into V2_RETRO_PARQUET. Never touches main RETRO_PARQUET.

    Same keep-fresh logic as _merge_into_store but isolated to v2 paths.
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if V2_RETRO_PARQUET.exists():
        # v2 rows come from the same grade_boards rec dict, so the same retirement and
        # the same legacy-carry path apply here (see _merge_into_store)
        stored = _drop_retired(pd.read_parquet(V2_RETRO_PARQUET))
    else:
        stored = pd.DataFrame()

    if fresh.empty:
        return stored

    if stored.empty:
        merged = fresh.copy()
    else:
        for col in fresh.columns:
            if col not in stored.columns:
                stored[col] = None
        key_cols = [c for c in _DEDUP_KEYS if c in fresh.columns and c in stored.columns]
        fresh_keys = set(map(tuple, fresh[key_cols].values.tolist()))
        mask = stored.apply(lambda r: tuple(r[k] for k in key_cols) not in fresh_keys, axis=1)
        # same write-once law as the main ledger: a graded row is a point-in-time claim
        fresh = _freeze_graded_prices(fresh, stored, key_cols)
        merged = pd.concat([stored[mask], fresh], ignore_index=True)

    merged = _drop_retired(merged)
    merged.to_parquet(V2_RETRO_PARQUET, index=False)
    return merged


def run_v2_lane(names: pd.DataFrame, etfs: pd.DataFrame, quiet: bool = False,
                price_sources: dict | None = None) -> None:
    """Run the v2 parallel grader lane.

    ISOLATION: reads V2_SNAPSHOTS_JSONL, writes V2_RETRO_PARQUET + V2_TRACK_JSON.
    NEVER touches retro_grades.parquet / snapshots.jsonl / us_board_track.json.
    The standout_audit organ ignores v2 rows (reads retro_grades.parquet only).
    Runtime: O(v2 board rows × horizons) — comparable to the main lane.
    """
    import time
    _t0 = time.monotonic()

    v2_boards = collect_v2_boards()
    if not v2_boards:
        if not quiet:
            print("[v2_lane] no v2 boards found — snapshot may not have fired yet")
        return

    if not quiet:
        print(f"[v2_lane] {len(v2_boards)} v2 board dates "
              f"({v2_boards[0]['as_of']}..{v2_boards[-1]['as_of']})")

    # The v2 lane admits names the v1 boards never carried, so it resolves its OWN basis
    # provenance rather than inheriting main()'s — otherwise a v2-only ticker would grade
    # against an adjusted SPY with a null price_basis stamp, which is the exact silent
    # state this PR exists to remove. `names` was already re-based for the shared names;
    # this only adds the v2-only ones.
    names, _v2_basis = rebase_to_adjusted(names, v2_boards)
    if price_sources:
        _v2_basis["price_source"] = {**price_sources, **_v2_basis["price_source"]}
    if not quiet and _v2_basis["names_on_unadjusted_basis"]:
        print(f"[v2_lane] {_v2_basis['names_on_unadjusted_basis']} v2 name(s) have no "
              f"adjusted counterpart — stamped price_basis=unadjusted")

    _pre_existing = pd.read_parquet(V2_RETRO_PARQUET) if V2_RETRO_PARQUET.exists() else None
    df = grade_boards(v2_boards, names, etfs, _stored_df=_pre_existing,
                      price_sources=_v2_basis["price_source"])
    full_df = _merge_v2_into_store(df)

    if not quiet:
        new_rows = len(df) if not df.empty else 0
        print(f"[v2_lane] {new_rows} new matured v2 rows; "
              f"store total -> {len(full_df)} rows in {V2_RETRO_PARQUET.name}")

    # Build a v2-specific track summary (separate JSON, never merged into us_board_track.json)
    # SA-W5 F5: map v2_entry_open → 'buy' before calling build_track so that
    # build_track's `lane == "buy"` filter yields non-empty buy_lane stats and
    # precision@k is computed for the primary entry lane.  This aliasing is ONLY
    # applied inside run_v2_lane (not to the parquet/snapshots — raw lanes stay
    # v2_entry_open/v2_setting_up).  The lane_mapping key stamps the emitted JSON
    # so consumers know the alias.
    _V2_LANE_MAPPING = {"v2_entry_open": "buy"}
    track_input_df = full_df.copy() if not full_df.empty else full_df
    if not track_input_df.empty and "lane" in track_input_df.columns:
        track_input_df["lane"] = track_input_df["lane"].map(
            lambda x: _V2_LANE_MAPPING.get(x, x)
        )
    track_v2 = build_track(track_input_df, v2_boards, names)
    # Label this as the v2 board track so consumers can distinguish
    track_v2["board_version"] = "v2"
    track_v2["lane_mapping"] = _V2_LANE_MAPPING
    track_v2["note"] = (
        "SA-W5 v2 parallel lane (dual-gate+rotation-priority board). "
        "Lanes: v2_entry_open (aliased to 'buy' for precision@k comparability), "
        "v2_setting_up. "
        "lane_mapping applied in track only — raw parquet/snapshots retain original lane names. "
        "ISOLATED from main board track — never included in us_board_track.json aggregates."
    )
    V2_TRACK_JSON.parent.mkdir(parents=True, exist_ok=True)
    V2_TRACK_JSON.write_text(json.dumps(track_v2, indent=1, default=str))

    elapsed = time.monotonic() - _t0
    if not quiet:
        print(f"[v2_lane] [timing] v2 lane complete in {elapsed:.1f}s → {V2_TRACK_JSON.name}")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="snapshot today's board then re-grade everything matured (cron entry point)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.nightly:
        snap = snapshot_today()
        if not args.quiet:
            print(f"[snapshot] as_of={snap} appended to {SNAPSHOTS_JSONL.name}")
        # SA-W5: v2 snapshot (parallel lane, isolated files)
        snap_v2 = snapshot_v2_today()
        if not args.quiet:
            print(f"[v2_snapshot] as_of={snap_v2} → {V2_SNAPSHOTS_JSONL.name}")
        # PIT replay absorb (research/PROPHET_PIT_REPLAY_HARNESS_V1.md §0.4): BEFORE
        # collect_boards() so an absorbed session flows through the ordinary nightly
        # pipeline on this same run. Absent/empty pending dir is an exact no-op.
        absorb_pending_replays(quiet=args.quiet)

    names, etfs = _load_prices()
    _board_receipt: dict = {}
    boards = collect_boards(_board_receipt)
    if not args.quiet:
        print(f"[boards] {len(boards)} distinct as_of dates "
              f"({boards[0]['as_of']}..{boards[-1]['as_of']}; "
              f"{_board_receipt.get('n_from_snapshots')} from snapshots, "
              f"{_board_receipt.get('n_from_git')} from "
              f"{_board_receipt.get('n_git_revisions')} git revision(s))"
              if boards else "[boards] none")
    # A shallow checkout kills the retro half silently — git log exits 0 and returns one
    # revision, so the count above degrades with nothing else in the run to say so.
    warn_if_history_truncated(_board_receipt)

    # Price what the board ADMITTED, not just what the breadth caches carry — otherwise
    # every curated-extras admission (ADRs, recent IPOs) is ungradeable forever.
    names, _price_receipt = extend_prices_to_admitted(names, boards)
    if not args.quiet:
        print(f"[prices] {names.shape[1]} priced tickers "
              f"(+{_price_receipt['n_recovered_from_admitted_store']} recovered from the "
              f"admission store: {', '.join(_price_receipt['recovered'][:15])}"
              f"{'…' if len(_price_receipt['recovered']) > 15 else ''}; "
              f"{_price_receipt['n_unresolved']} still unresolvable)")

    # PRICE-BASIS LAW: the name leg must share the benchmark's adjusted basis before any
    # excess return is taken. Must run AFTER extend_prices_to_admitted so the recovered
    # extras are stamped by the same ladder as everything else.
    names, _basis_prov = rebase_to_adjusted(names, boards)
    if not args.quiet:
        _rf = _basis_prov["resolved_from"]
        print(f"[price_basis] {_basis_prov['n_columns_rebased']} admitted columns re-based "
              f"onto the adjusted ladder ({_rf['baskets_ohlcv']} baskets_ohlcv, "
              f"{_rf['yahoo']} yahoo, {_rf['data_stocks']} data_stocks); "
              f"{_basis_prov['names_on_unadjusted_basis']} name(s) have no adjusted "
              f"counterpart and stay on the raw cache — stamped price_basis=unadjusted: "
              f"{', '.join(_basis_prov['unadjusted_tickers'][:12])}"
              f"{'…' if len(_basis_prov['unadjusted_tickers']) > 12 else ''}")

    # A dead nightly must be visible in Actions the next morning, not discovered days
    # later by an operator noticing a missing name. Never backfills — the gap is stated.
    _cont = continuity_block(boards, names, etfs)
    warn_if_stale(_cont)
    if not args.quiet and _cont.get("n_stale_sessions"):
        print(f"[continuity] newest snapshot {_cont['last_snapshot']} vs last session "
              f"{_cont['last_session']} — {_cont['n_stale_sessions']} session(s) with no board")

    # P2: load existing store BEFORE grading so _board_tenure can look up history
    _pre_existing = pd.read_parquet(RETRO_PARQUET) if RETRO_PARQUET.exists() else None
    _n_stored_before = 0 if _pre_existing is None else len(_pre_existing)
    _graded_before = (set(_pre_existing["as_of"].astype(str))
                      if _pre_existing is not None and "as_of" in _pre_existing.columns
                      else set())
    _ungraded = [b["as_of"] for b in boards if b["as_of"] not in _graded_before]
    # price_sources arrives from #4715's adjusted-first ladder; the zero-accrual
    # bookkeeping above is #4727's. Both legs are required — keep them together.
    df = grade_boards(boards, names, etfs, _stored_df=_pre_existing,
                      price_sources=_basis_prov["price_source"])
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    # Merge freshly-graded rows INTO the accumulated store, then always build the
    # track from the full store.  This prevents the empty:true regression that fires
    # whenever no *new* rows mature in a given nightly run (the store still holds
    # all previously-graded rows and must not be discarded).
    full_df = _merge_into_store(df)
    # ACCRUAL is store growth, not the size of the fresh frame. grade_boards re-computes
    # every matured row every run and the merge is keep-fresh, so len(df) counts
    # re-grades: the nightly of 2026-08-04 emitted 1332 "new matured rows" while the
    # store went 2282 -> 2282. Reporting len(df) as accrual is what made a nine-day
    # outage read as nine normal nights.
    _n_added = max(0, len(full_df) - _n_stored_before)
    if not args.quiet:
        dead_n = df.attrs.get("dead_price_store_tickers", 0)
        print(f"[grade] {_n_added} rows ADDED to the store this run "
              f"({len(df)} matured rows re-graded, skipped "
              f"{df.attrs.get('skipped_no_price', 0)} no-price rows, "
              f"dead_name_store_tickers={dead_n}); "
              f"store total -> {len(full_df)} rows in {RETRO_PARQUET.name}")
    # A nightly that records nothing for nine days is the defect underneath the defect.
    warn_if_no_accrual(_n_added, nightly=args.nightly, boards=boards, names=names,
                       cont=_cont, ungraded=_ungraded,
                       skipped_no_price=int(df.attrs.get("skipped_no_price", 0) or 0))

    # W0.1 B-b: backfill null regime stamps on historical rows where the persisted
    # regime_vector covers the as_of date (PIT-safe: reads only persisted rows ≤ as_of)
    full_df, n_newly_stamped = _backfill_regime_stamps(full_df)
    if n_newly_stamped > 0:
        full_df.to_parquet(RETRO_PARQUET, index=False)
        if not args.quiet:
            print(f"[regime_stamp] backfilled {n_newly_stamped} historical rows")
    stamp_cols_present = [c for c in _REGIME_STAMP_COLS if c in full_df.columns]
    n_unstamped = int(full_df[stamp_cols_present].isna().all(axis=1).sum()) if stamp_cols_present else len(full_df)
    if not args.quiet:
        print(f"[regime_stamp] {n_unstamped}/{len(full_df)} rows still unstamped "
              f"(regime_vector.parquet absent or no coverage for those as_of dates)")

    # Backfill null archetype from the PIT archetype store at each row's own as_of.
    # The board payload has never carried the field, so historical rows are all null
    # until this pass runs (coverage map: data/us_board_ledger/README.md).
    full_df, n_arch_filled = _backfill_archetype(full_df)
    if n_arch_filled > 0:
        full_df.to_parquet(RETRO_PARQUET, index=False)
    n_arch_null = (int(full_df["archetype"].isna().sum())
                   if "archetype" in full_df.columns else len(full_df))
    if not args.quiet:
        print(f"[archetype_stamp] backfilled {n_arch_filled} historical rows; "
              f"{n_arch_null}/{len(full_df)} rows still null "
              f"(no PIT archetype coverage)")

    track = build_track(full_df, boards, names)
    TRACK_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRACK_JSON.write_text(json.dumps(track, indent=1, default=str))
    if not args.quiet:
        print(f"[track] wrote {TRACK_JSON.relative_to(ROOT)}")
        surv = track.get("survivorship") or {}
        if surv.get("n_skipped_no_price"):
            print(f"[survivorship] {surv['n_skipped_no_price']} board tickers have no usable "
                  f"price series ({surv['n_rows_skipped_no_price']}/{surv['n_board_rows_total']} "
                  f"board rows excluded from every stat): {surv['tickers_skipped']}")
        # headline
        for h in HORIZONS:
            blk = track.get("per_horizon", {}).get(f"h{h}", {})
            bl = blk.get("buy_lane", {})
            vs = bl.get("vs_spy", {})
            if vs.get("n"):
                pk = bl.get("precision_at_k_board_order_vs_spy", {}).get("k5", {})
                pa = bl.get("precision_at_k_alpha_order_vs_spy", {}).get("k5", {})
                print(f"  h{h}d buy-lane: n={vs['n']} hit={vs['hit_rate']} "
                      f"CI[{vs['wilson_lo']},{vs['wilson_hi']}] med_exc={vs['median_excess']} "
                      f"| P@5 board={pk.get('pooled_precision')} alpha={pa.get('pooled_precision')} "
                      f"| corr(pos,exc)={bl.get('corr_position_excess')} "
                      f"rank_by={bl.get('rank_by_of_matured_boards')}")

    # W2: outcomes strip — names that left the buy board within the last 21 board dates
    try:
        outcomes = emit_outcomes(boards, names)
        OUTCOMES_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUTCOMES_JSON.write_text(json.dumps(outcomes, indent=1, default=str))
        if not args.quiet:
            if outcomes.get("empty"):
                print(f"[outcomes] empty ({outcomes.get('reason','')}) — wrote {OUTCOMES_JSON.name}")
            else:
                smry = outcomes.get("summary", {})
                print(f"[outcomes] {len(outcomes.get('rows', []))} exited names "
                      f"(running={smry.get('n_running')} stopped={smry.get('n_stopped')} "
                      f"median={smry.get('median_pct')}% "
                      f"skipped_no_price={smry.get('n_skipped_no_price', 0)}) "
                      f"→ {OUTCOMES_JSON.name}")
    except Exception as _oe:  # noqa: BLE001 — outcomes strip is additive; never fatal
        if not args.quiet:
            print(f"[outcomes] skipped ({_oe})")

    # TRD popup — buy-lane episode ledger (track_ledger/v1). Additive, never fatal:
    # a failure just leaves the ledger to bake next run; the popup's server-rendered
    # cards stay current regardless (they don't depend on this JSON).
    try:
        from engine import track_ledger as _tl
        ledger = emit_ledger(boards, names, etfs)
        if _tl.atomic_write(LEDGER_JSON, ledger) and not args.quiet:
            _lsm = ledger.get("summary", {})
            print(f"[track_ledger] {ledger.get('meta', {}).get('n_total', 0)} episodes "
                  f"(state={ledger.get('state')} win={_lsm.get('win_pct')}% "
                  f"exp={_lsm.get('expectancy_pct')}% pf={_lsm.get('profit_factor')} "
                  f"matured={_lsm.get('n_matured')} over {_lsm.get('n_board_days')} board days, "
                  f"inflight={_lsm.get('n_inflight')} "
                  f"skipped_no_price={_lsm.get('n_skipped_no_price')}) → {LEDGER_JSON.name}")
    except Exception as _le:  # noqa: BLE001 — ledger is additive; never fatal
        if not args.quiet:
            print(f"[track_ledger] skipped ({_le})")

    # SA-W5: v2 parallel grader lane — additive, never fatal, never touches main stores
    try:
        run_v2_lane(names, etfs, quiet=args.quiet,
                    price_sources=_basis_prov["price_source"])
    except Exception as _v2e:  # noqa: BLE001
        if not args.quiet:
            print(f"[v2_lane] skipped ({_v2e})")


if __name__ == "__main__":
    main()
