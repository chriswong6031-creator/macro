"""scripts/build_flow_surface.py — intraday Flow-Surface snapshot store.

Materializes the per-strike net-premium surface store consumed by the Terminal
"Flow Surface" pane (charting-app terminal/lib/surfaceContract.ts + flowSource.ts).
This is the DATA half of the feature; the renderer half already shipped.

Store contract (RECON.md §2, MASTERPLAN §3 Lane T item 5; shapes pinned by the
Terminal fixtures public/data/surface_idx_fixture.json + surface_fixture.json):

  R2 key  live_flow/surface/{ROOT}/idx.json        → SurfaceIndex
          live_flow/surface/{ROOT}/{HHMM}.json     → SurfaceFrame

  SurfaceIndex = {date, stamps:["HHMM",…] ascending, latest, cadenceSec, cadence?, root?, source?}
  SurfaceFrame = {spot, price_levels:[…] ascending, time_steps:["HH:MM",…],
                  grids:{netprem:[[levelIdx][timeIdx]]}, asof, cadence,
                  metrics?, session_date?, root?}

  Grid orientation (surfaceContract.ts buildHeatBars): grids[metric][levelIdx][timeIdx].
  Rows = price_levels (one per strike, ascending); columns = time_steps realized so far
  today (one per written stamp). Dimensions are len(price_levels) × len(time_steps).

Column semantics — the honest, well-defined per-strike signal the poller can supply:
  The live_flow poller accumulates root_strikes[root][strike] = {call_prem, put_prem, vol}
  as a CUMULATIVE day-to-date rollup (engine/live_flow.py). It does NOT retain per-strike
  per-minute history. So each stamp's netprem column = per strike (call_prem - put_prem),
  i.e. the cumulative session net premium at that strike as of the stamp. Appending one
  column per stamp builds the levels×time matrix the surface pane replays — matching the
  competitor's per-strike-session model (RECON §2: replay & live share one path, one
  immutable snapshot per stamp, server does the math). Nothing is forward-filled.

Cadence honesty (surfaceContract.ts header law — "never pretend a cadence it doesn't have"):
  cadenceSec / cadence are carried verbatim from the ACTUAL write interval. Wired into the
  live_flow poller main loop, that interval is live_flow.cadence_sec (config.yml; 120s = the
  "2-min" label). The poller's full-day re-pull means every cycle's root_strikes is the
  true cumulative to-now, so a 120s cadence is honest for these cumulative columns; we never
  claim a finer cadence than the loop that calls us.

Ledger law: this is a live intraday artifact (like feed_current / tide_current) — it writes
  ONLY to the gitignored staging dir data/live_flow_out/surface/ and uploads to R2. It never
  advances a forward ledger; nightly remains the sole advancer of those.

Idempotency: writing the same stamp twice overwrites that stamp's column in place (the frame
  is keyed by stamp position in time_steps), never duplicating it. Safe to re-run a cycle.

Usage:
  # Dry-run against a synthetic session (prints one idx + snapshot, validates shapes, no IO)
  python -m scripts.build_flow_surface --dry-run
  python -m scripts.build_flow_surface --dry-run --root SPY --stamps 8

  # Programmatic (wired in live_flow_poller.main): build_and_stage_surfaces(...)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Stdlib zoneinfo — repo convention (engine/options_flow.py, live_flow_poller.py).
ET = ZoneInfo("America/New_York")

# R2 prefix for the surface store (under the existing live_flow/ TTL prefix so the
# poller's 48h archive-prune conventions and the Terminal's r2Key both resolve it).
R2_SURFACE_PREFIX = "live_flow/surface/"

# Local staging dir name under data/live_flow_out/ (gitignored — .gitignore:318).
SURFACE_OUT_SUBDIR = "surface"

# Default roots for the store (config live_flow.surface_roots overrides / extends).
DEFAULT_SURFACE_ROOTS = ["SPY", "QQQ", "IWM"]

# Wave 1 fills netprem; Wave 2 (Lane G) adds the intraday dealer-exposure greek grids.
# The grids map stays OPEN (named keys) — the Terminal surface pane feature-detects which
# grid keys are present (gex/dex/vanna/charm), so adding these is purely additive.
METRIC_NETPREM = "netprem"
# Greek metric grids, same levels×time orientation as netprem (append-a-column per stamp).
# Names match the Terminal's greek-tab feature-detect keys + engine/gex_engine conventions:
#   gex   = dealer $gamma exposure per 1% move   (sign·gamma·oi·mult·S²·pm)
#   dex   = dealer $delta exposure               (sign·delta·oi·mult·S)
#   vanna = dealer vanna-notional                (sign·vanna·oi·mult·S·pm)   ["VEX"]
#   charm = dealer charm-notional per day        (sign·(charm/365)·oi·mult·S) ["CEX"]
METRIC_GEX = "gex"
METRIC_DEX = "dex"
METRIC_VANNA = "vanna"
METRIC_CHARM = "charm"
GREEK_METRICS = (METRIC_GEX, METRIC_DEX, METRIC_VANNA, METRIC_CHARM)

# Human cadence labels for the honesty stamp, keyed by the true write interval (seconds).
_CADENCE_LABELS = {60: "1-min", 120: "2-min", 300: "5-min", 600: "10-min", 900: "15-min"}


def cadence_label(cadence_sec: int) -> str:
    """Human cadence label for an interval in seconds (honesty stamp).

    Falls back to "<n>-min" (rounded) for uncommon intervals, or "<n>s" under a minute.
    Never invents a finer cadence than the caller's true write interval.
    """
    try:
        s = int(cadence_sec)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s in _CADENCE_LABELS:
        return _CADENCE_LABELS[s]
    if s < 60:
        return f"{s}s"
    return f"{round(s / 60)}-min"


def stamp_hhmm(dt: datetime) -> str:
    """'HHMM' stamp (index key) for an ET-localized datetime."""
    return dt.astimezone(ET).strftime("%H%M")


def stamp_hhcolonmm(dt: datetime) -> str:
    """'HH:MM' time-step label (frame time axis) for an ET-localized datetime."""
    return dt.astimezone(ET).strftime("%H:%M")


def hhmm_to_hhcolonmm(hhmm: str) -> str:
    """'HHMM' → 'HH:MM'. The index carries stamps as HHMM; the frame's time_steps as HH:MM."""
    hhmm = str(hhmm)
    if len(hhmm) == 4 and hhmm.isdigit():
        return f"{hhmm[:2]}:{hhmm[2:]}"
    return hhmm


def net_prem_by_strike(root_strikes: dict) -> dict[float, float]:
    """Cumulative net premium per strike from a root's strike rollup.

    root_strikes: {strike_str → {call_prem, put_prem, vol}} (engine/live_flow.py rollup).
    Returns {strike_float → call_prem - put_prem}. Non-numeric strikes/values are skipped
    (never fabricated). Empty in → empty out.
    """
    out: dict[float, float] = {}
    for stk_str, sv in (root_strikes or {}).items():
        try:
            strike = float(stk_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(sv, dict):
            continue
        call = float(sv.get("call_prem", 0.0) or 0.0)
        put = float(sv.get("put_prem", 0.0) or 0.0)
        out[strike] = call - put
    return out


# ── intraday greek grids: tape → per-contract quotes → dealer exposure ──────────────
# The netprem column comes from the poller's CUMULATIVE root_strikes rollup. The GREEK
# grids need per-contract mid QUOTES + expiry + prior-day OI, which that rollup discards.
# extract_cycle_quotes() pulls the freshest NBBO mid per (exp,strike,right) from the raw
# trade-tape the poller already fetched this cycle (calls_df/puts_df), so no extra API
# call is made. compute_greek_grids (engine/intraday_greeks) then solves IV + greeks and
# aggregates per-strike GEX/DEX/VANNA/CHARM using the EOD engine's dealer conventions.


def _year_fraction(exp_str: str, session_date: str) -> float | None:
    """Year-fraction to expiry (T) from an expiration date and the session date.

    Both ISO 'YYYY-MM-DD' (or a timestamp whose first 10 chars are the date). 0DTE →
    a small positive floor (never 0 or negative, which would blow up BS). Returns None on
    an unparseable/expired date (past the session date).
    """
    try:
        exp_d = datetime.fromisoformat(str(exp_str)[:10]).date()
        sess_d = datetime.fromisoformat(str(session_date)[:10]).date()
    except (TypeError, ValueError):
        return None
    days = (exp_d - sess_d).days
    if days < 0:
        return None
    # 0DTE carries intraday time value; floor at ~4 hours so late-day 0DTE greeks stay finite.
    return max(days / 365.0, (4.0 / 24.0) / 365.0)


def extract_cycle_quotes(
    calls_df,
    puts_df,
    *,
    session_date: str,
    near_dte_cap_days: int | None = 90,
) -> list[dict]:
    """Freshest per-contract NBBO mid this cycle, from the raw trade-tape frames.

    calls_df / puts_df: the poller's bulk_trade_quote output (row-per-fill tape) with
    columns root, expiration, strike, right, trade_timestamp, bid, ask (collectors/
    thetadata._normalize_trade_quote_df). For each (expiration, strike, right) we keep the
    LAST row by trade_timestamp — the most recent NBBO for that contract — and compute
    mid = (bid+ask)/2. Contracts with no positive bid/ask, or an expiry beyond
    near_dte_cap_days (the poller's chain coverage cap), are dropped.

    Returns a list of {exp_str, exp_years, strike, right('C'/'P'), mid} dicts — the input
    compute_greek_grids expects (minus oi, which is joined separately from the OI snapshot).
    Coverage honesty is intrinsic: a strike with no traded contract this cycle simply is
    not in the list, so it contributes 0 and is not counted toward greek coverage.
    """
    import pandas as pd  # local import — pure-python callers (dry-run) never hit this

    frames = []
    for df in (calls_df, puts_df):
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            frames.append(df)
    if not frames:
        return []
    tape = pd.concat(frames, ignore_index=True)

    need = {"expiration", "strike", "right", "bid", "ask", "trade_timestamp"}
    if not need.issubset(set(tape.columns)):
        return []

    tape = tape.copy()
    tape["bid"] = pd.to_numeric(tape["bid"], errors="coerce")
    tape["ask"] = pd.to_numeric(tape["ask"], errors="coerce")
    tape["strike"] = pd.to_numeric(tape["strike"], errors="coerce")
    # Clean (non-underscore) grouping columns — pandas itertuples() mangles names that
    # start with '_' into positional accessors, so keep them itertuples-safe.
    tape["cright"] = tape["right"].astype(str).str.upper().str[:1]
    tape["cexp"] = tape["expiration"].astype(str).str[:10]
    # Keep only rows with a usable two-sided quote.
    tape = tape[(tape["bid"] > 0) & (tape["ask"] > 0) & (tape["strike"] > 0)]
    if tape.empty:
        return []

    # Freshest quote per contract = last row by trade_timestamp.
    tape = tape.sort_values("trade_timestamp")
    last = tape.groupby(["cexp", "strike", "cright"], as_index=False).last()

    out: list[dict] = []
    for row in last.itertuples(index=False):
        exp_str = row.cexp
        T = _year_fraction(exp_str, session_date)
        if T is None:
            continue
        if near_dte_cap_days is not None and T > (near_dte_cap_days + 1) / 365.0:
            continue
        bid = float(row.bid); ask = float(row.ask)
        mid = (bid + ask) / 2.0
        right = row.cright
        if right not in ("C", "P") or mid <= 0:
            continue
        out.append({
            "exp_str": exp_str,
            "exp_years": T,
            "strike": float(row.strike),
            "right": right,
            "mid": mid,
        })
    return out


def oi_by_contract(oi_df) -> dict[tuple, float]:
    """Map {(exp_str, strike_float, right): open_interest} from an OI snapshot frame.

    oi_df: collectors.thetadata.snapshot_open_interest output (columns root, expiration,
    strike, right, snapshot_ts, open_interest) — EOD t-1 positions (the OI-timing law:
    OI does not update intraday, so one pull per root per day is correct and NOT a leak).
    Returns {} on an empty/malformed frame. Non-numeric OI rows are skipped.
    """
    out: dict[tuple, float] = {}
    if oi_df is None:
        return out
    try:
        import pandas as pd
        if not isinstance(oi_df, pd.DataFrame) or oi_df.empty:
            return out
        need = {"expiration", "strike", "right", "open_interest"}
        if not need.issubset(set(oi_df.columns)):
            return out
        for row in oi_df.itertuples():
            try:
                exp = str(getattr(row, "expiration"))[:10]
                strike = float(getattr(row, "strike"))
                right = str(getattr(row, "right")).upper()[:1]
                oi = float(getattr(row, "open_interest"))
            except (TypeError, ValueError):
                continue
            if right in ("C", "P") and oi >= 0:
                out[(exp, strike, right)] = oi
    except Exception as e:  # noqa: BLE001
        log.debug("surface: oi_by_contract failed: %s", e)
    return out


def greek_columns_for_stamp(
    quotes: list[dict],
    *,
    oi_map: dict[tuple, float] | None = None,
    spot: float | None = None,
    spot_fallback: float | None = None,
) -> dict:
    """Compute this stamp's per-strike greek exposures + walls + coverage from quotes.

    Joins each quote to its prior-day OI (oi_map keyed by (exp_str,strike,right)), then
    calls engine.intraday_greeks.compute_greek_grids (which mirrors the EOD dealer-sign /
    GEX / DEX / VEX / CEX conventions). Contracts with no OI match contribute nothing
    (honest — a strike with unknown positioning carries no measured dealer exposure).

    Returns:
      {
        "by_strike": {gex:{strike→val}, dex:{…}, vanna:{…}, charm:{…}},
        "walls": {"flip":…, "callWall":…, "putWall":…},   # camelCase per Terminal contract
        "coverage": 0..1,
        "spot": float|None,
        "spot_source": "parity"|"prev_close"|"explicit"|"none",
        "n_contracts": int,
      }
    or an empty-shaped dict (all-empty maps, coverage 0) when nothing is computable.
    """
    empty = {
        "by_strike": {m: {} for m in GREEK_METRICS},
        "walls": {"flip": None, "callWall": None, "putWall": None},
        "coverage": 0.0, "spot": spot if spot is not None else spot_fallback,
        "spot_source": "none", "n_contracts": 0,
    }
    if not quotes:
        return empty
    try:
        from engine.intraday_greeks import compute_greek_grids
    except Exception as e:  # noqa: BLE001 — engine import must never break netprem writes
        log.warning("surface: intraday_greeks import failed (%s) — greek grids skipped", e)
        return empty

    oi_map = oi_map or {}
    contracts: list[dict] = []
    for qd in quotes:
        key = (str(qd.get("exp_str"))[:10], float(qd["strike"]),
               str(qd.get("right")).upper()[:1])
        oi = oi_map.get(key)
        if oi is None or oi <= 0:
            continue  # no prior-day OI → no dealer-exposure contribution (honest)
        contracts.append({
            "exp_years": qd["exp_years"], "strike": qd["strike"],
            "right": qd["right"], "mid": qd["mid"], "oi": oi,
        })

    # Coverage denominator = the union of strikes that had a usable quote this cycle
    # (whether or not OI matched) — so a low OI-match rate reads as low coverage honestly.
    union_strikes = sorted({float(q["strike"]) for q in quotes})

    if not contracts:
        # Quotes existed but none matched OI → coverage 0 against the quoted-strike union.
        e = dict(empty)
        e["spot_source"] = "none"
        return e

    gg = compute_greek_grids(
        contracts, spot=spot, spot_fallback=spot_fallback, union_strikes=union_strikes,
    )
    by_strike = {
        METRIC_GEX: {k: v for k, v in zip(gg.strikes, gg.gex)},
        METRIC_DEX: {k: v for k, v in zip(gg.strikes, gg.dex)},
        METRIC_VANNA: {k: v for k, v in zip(gg.strikes, gg.vex)},
        METRIC_CHARM: {k: v for k, v in zip(gg.strikes, gg.cex)},
    }
    return {
        "by_strike": by_strike,
        "walls": {"flip": gg.flip, "callWall": gg.call_wall, "putWall": gg.put_wall},
        "coverage": gg.coverage,
        "spot": gg.spot,
        "spot_source": gg.spot_source,
        "n_contracts": gg.n_contracts,
    }


def append_stamp(
    prior: dict | None,
    *,
    stamp: str,
    time_step: str,
    net_by_strike: dict[float, float],
    spot: float | None,
    asof: str,
    cadence_sec: int,
    session_date: str,
    root: str,
    round_ndigits: int = 0,
    greek_by_strike: dict[str, dict[float, float]] | None = None,
    walls: dict | None = None,
    coverage: float | None = None,
    greek_round_ndigits: int = 2,
) -> dict:
    """Return a new full-day SurfaceFrame with this stamp's column appended (idempotent).

    `prior` is the previously-staged frame for this root today (or None on the first stamp).
    The strike grid (price_levels) is the UNION of all strikes seen across stamps, kept
    ascending; a level absent from an earlier stamp reads 0.0 in that earlier column (the
    strike simply had no cumulative premium yet). Re-appending an existing stamp overwrites
    that column in place — never duplicated (idempotent per stamp).

    Grids are grids[metric][levelIdx][timeIdx], all dimensions len(price_levels) ×
    len(time_steps). `netprem` is always present (Wave 1). When `greek_by_strike` is given
    (Wave 2 / Lane G: {"gex":{strike→val}, "dex":…, "vanna":…, "charm":…}), those grids are
    appended in the SAME orientation — one column per stamp, unioned strike rows, 0.0 where
    a strike had no greek this cycle (honest: no traded/OI'd contract there).

    Per-stamp `walls` ({flip,callWall,putWall}) and `coverage` (0..1 greek coverage) are
    column-aligned lists carried on the frame (walls_path / coverage_path) so frame_for_stamp
    can surface the walls/coverage AS OF each replayed stamp.
    """
    prior = prior or {}
    prior_levels: list[float] = [float(x) for x in (prior.get("price_levels") or [])]
    prior_steps: list[str] = list(prior.get("time_steps") or [])
    prior_stamps: list[str] = list(prior.get("stamps") or [])
    prior_grids: dict = dict(prior.get("grids") or {})
    prior_spot_path: list = list(prior.get("spot_path") or [])
    prior_walls_path: list = list(prior.get("walls_path") or [])
    prior_cov_path: list = list(prior.get("coverage_path") or [])

    # Which metric grids does this frame carry? netprem always; greek metrics once any
    # stamp has supplied them (a prior frame may already have them, or this stamp does).
    greek_by_strike = greek_by_strike or {}
    active_greeks = [m for m in GREEK_METRICS
                     if m in prior_grids or m in greek_by_strike]
    all_metrics = [METRIC_NETPREM] + active_greeks
    # Per-metric strike→value map for THIS stamp (netprem + each active greek).
    stamp_values: dict[str, dict[float, float]] = {METRIC_NETPREM: net_by_strike}
    for m in active_greeks:
        stamp_values[m] = greek_by_strike.get(m, {})

    # Column index for this stamp: reuse if the stamp already exists (idempotent overwrite),
    # else append a new trailing column.
    if stamp in prior_stamps:
        col_idx = prior_stamps.index(stamp)
        stamps = list(prior_stamps)
        time_steps = list(prior_steps)
    else:
        col_idx = len(prior_stamps)
        stamps = prior_stamps + [stamp]
        time_steps = prior_steps + [time_step]

    n_cols = len(stamps)

    # Union of strikes across ALL metrics: prior levels ∪ every metric's strikes this stamp.
    level_set = set(prior_levels)
    for vals in stamp_values.values():
        level_set |= set(float(k) for k in vals.keys())
    price_levels = sorted(level_set)
    lvl_index = {lvl: i for i, lvl in enumerate(price_levels)}

    grids: dict[str, list[list[float]]] = {}
    for metric in all_metrics:
        nd = round_ndigits if metric == METRIC_NETPREM else greek_round_ndigits
        prior_grid = list(prior_grids.get(metric) or [])
        # Rebuild at (len(price_levels) × n_cols); missing cells default to 0.0 (honest).
        grid: list[list[float]] = [[0.0] * n_cols for _ in price_levels]
        # Copy prior columns into the (possibly widened) grid.
        for old_li, old_lvl in enumerate(prior_levels):
            new_li = lvl_index.get(old_lvl)
            if new_li is None:
                continue
            old_row = prior_grid[old_li] if old_li < len(prior_grid) else []
            for cj in range(min(len(old_row), n_cols)):
                grid[new_li][cj] = old_row[cj]
        # Write this stamp's column (overwriting if it already existed).
        for lvl, val in stamp_values.get(metric, {}).items():
            li = lvl_index.get(float(lvl))
            if li is not None and val is not None:
                try:
                    grid[li][col_idx] = round(float(val), nd)
                except (TypeError, ValueError):
                    grid[li][col_idx] = 0.0
        grids[metric] = grid

    # spot_path tracks the spot at each column (materializer detail; the fixture uses it to
    # resolve a per-stamp spot on replay). Keep it column-aligned.
    spot_path = list(prior_spot_path)
    while len(spot_path) < n_cols:
        spot_path.append(None)
    spot_path[col_idx] = spot

    # walls / coverage per column (aligned to stamps) — only meaningful when greeks present.
    walls_path = list(prior_walls_path)
    cov_path = list(prior_cov_path)
    while len(walls_path) < n_cols:
        walls_path.append(None)
    while len(cov_path) < n_cols:
        cov_path.append(None)
    if walls is not None:
        walls_path[col_idx] = walls
    if coverage is not None:
        cov_path[col_idx] = coverage

    out = {
        "spot": spot,
        "price_levels": price_levels,
        "time_steps": time_steps,
        "grids": grids,
        "asof": asof,
        "cadence": cadence_label(cadence_sec),
        "metrics": all_metrics,
        "session_date": session_date,
        "root": root,
        # Materializer bookkeeping (harmless extras — the Terminal validator ignores them
        # and the fixture path reads `stamps`/`spot_path` for replay truncation):
        "stamps": stamps,
        "spot_path": spot_path,
    }
    # Only carry walls/coverage bookkeeping once greeks are present (keeps the Wave-1
    # netprem-only frame byte-identical to before).
    if active_greeks:
        out["walls_path"] = walls_path
        out["coverage_path"] = cov_path
    return out


def build_index(frame: dict, *, session_date: str, cadence_sec: int, root: str,
                source: str = "poller") -> dict:
    """Build the SurfaceIndex from a full-day frame. latest === stamps[-1] (contract law).

    checkIndexFilesContract (surfaceContract.ts) requires: stamps match the written files,
    and latest is the last stamp (or null when empty). We derive both from the frame so the
    idx and the snapshot files can never disagree.
    """
    stamps: list[str] = list(frame.get("stamps") or [])
    return {
        "date": session_date,
        "stamps": stamps,
        "latest": stamps[-1] if stamps else None,
        "cadenceSec": int(cadence_sec),
        "cadence": cadence_label(cadence_sec),
        "root": root,
        "source": source,
        # idx-level as-of (fixture parity — the newest frame's timestamp). Optional per the
        # isSurfaceIndex validator; carried so the UI can stamp the index freshness honestly.
        "asof": frame.get("asof", ""),
    }


def frame_for_stamp(full_frame: dict, stamp: str) -> dict:
    """Truncate a full-day frame to the realized-so-far window for `stamp` (replay view).

    Mirrors the Terminal's flowSource.ts `surface:` fixture logic: time_steps + each grid row
    are sliced to columns up to and including `stamp`; spot resolves from spot_path at that
    column. This is the exact per-stamp SurfaceFrame written to {HHMM}.json. Unknown stamp →
    the full day (never fabricated).
    """
    stamps: list[str] = list(full_frame.get("stamps") or [])
    times: list[str] = list(full_frame.get("time_steps") or [])
    idx = stamps.index(stamp) if stamp in stamps else -1
    upto = idx + 1 if idx >= 0 else len(times)
    grids_full = full_frame.get("grids") or {}
    grids = {m: [row[:upto] for row in g] for m, g in grids_full.items()}
    spot_path = full_frame.get("spot_path") or []
    spot = spot_path[upto - 1] if (spot_path and upto - 1 < len(spot_path) and upto >= 1) else full_frame.get("spot")
    out = {
        "spot": spot,
        "price_levels": list(full_frame.get("price_levels") or []),
        "time_steps": times[:upto],
        "grids": grids,
        "asof": full_frame.get("asof", ""),
        "cadence": full_frame.get("cadence", ""),
        "metrics": list(full_frame.get("metrics") or list(grids_full.keys())),
        "session_date": full_frame.get("session_date", ""),
        "root": full_frame.get("root", ""),
    }
    # Per-stamp walls + greek coverage AS OF the replayed stamp (Lane G). Only emitted when
    # the frame carries greek grids; the value is that stamp's own snapshot (walls are a
    # point-in-time read, never forward-filled).
    walls_path = full_frame.get("walls_path")
    cov_path = full_frame.get("coverage_path")
    col = upto - 1
    if walls_path is not None and 0 <= col < len(walls_path):
        w = walls_path[col]
        out["walls"] = w if w is not None else {"flip": None, "callWall": None, "putWall": None}
    if cov_path is not None and 0 <= col < len(cov_path):
        c = cov_path[col]
        out["coverage"] = {"greeks": c if c is not None else 0.0}
    return out


# ── validators (mirror surfaceContract.ts, for the dry-run self-check + tests) ──────

def is_surface_index(x: object) -> bool:
    """Port of surfaceContract.ts isSurfaceIndex."""
    if not isinstance(x, dict):
        return False
    return (
        isinstance(x.get("date"), str)
        and isinstance(x.get("stamps"), list)
        and all(isinstance(s, str) for s in x["stamps"])
        and (x.get("latest") is None or isinstance(x.get("latest"), str))
        and isinstance(x.get("cadenceSec"), int)
        and not isinstance(x.get("cadenceSec"), bool)
    )


def is_surface_frame(x: object) -> bool:
    """Port of surfaceContract.ts isSurfaceFrame."""
    if not isinstance(x, dict):
        return False
    return (
        isinstance(x.get("price_levels"), list)
        and isinstance(x.get("time_steps"), list)
        and isinstance(x.get("grids"), dict)
        and isinstance(x.get("asof"), str)
        and isinstance(x.get("cadence"), str)
    )


def check_index_files_contract(index: dict, available_stamps: list[str]) -> dict:
    """Port of surfaceContract.ts checkIndexFilesContract.

    {ok, missing, extra, latestOk}: missing = stamps promised by the index with no file;
    extra = files present the index doesn't list; latestOk = latest is the last stamp.
    """
    idx_stamps = list(index.get("stamps") or [])
    idx_set = set(idx_stamps)
    avail_set = set(available_stamps)
    missing = [s for s in idx_stamps if s not in avail_set]
    extra = [s for s in available_stamps if s not in idx_set]
    if not idx_stamps:
        latest_ok = index.get("latest") is None
    else:
        latest_ok = index.get("latest") == idx_stamps[-1]
    return {
        "ok": not missing and not extra and latest_ok,
        "missing": missing,
        "extra": extra,
        "latestOk": latest_ok,
    }


def validate_frame_dims(frame: dict) -> None:
    """Assert the grid is exactly len(price_levels) × len(time_steps) for every metric.

    Raises ValueError on any mismatch — a materializer self-check the caller can gate on.
    """
    n_levels = len(frame.get("price_levels") or [])
    n_steps = len(frame.get("time_steps") or [])
    for metric, grid in (frame.get("grids") or {}).items():
        if len(grid) != n_levels:
            raise ValueError(
                f"grid[{metric}] has {len(grid)} rows, expected {n_levels} (price_levels)"
            )
        for li, row in enumerate(grid):
            if len(row) != n_steps:
                raise ValueError(
                    f"grid[{metric}][{li}] has {len(row)} cols, expected {n_steps} (time_steps)"
                )


# ── staging + upload (mirror live_flow_poller conventions) ─────────────────────────

def _surface_out_dir(root: str) -> Path:
    """data/live_flow_out/surface/{ROOT}/ (gitignored staging; created on demand)."""
    from lib import config  # local import — keeps pure functions importable without config
    p = config.data_dir() / "live_flow_out" / SURFACE_OUT_SUBDIR / root.upper()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json_atomic(path: Path, obj: dict) -> Path:
    """Atomic JSON write (tmp + rename), mirroring live_flow_poller._write_json."""
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(path)
    return path


def _load_prior_full_frame(root: str) -> dict | None:
    """Load the staged full-day frame for this root today, or None.

    The full frame (with `stamps`/`spot_path`) is kept in a private staging file
    `_full.json` alongside the per-stamp public files, so the next cycle can append a
    column without re-reading every {HHMM}.json. Session rollover (a new date) is handled
    by the caller passing session_date; a stale-date full frame is ignored.
    """
    try:
        f = _surface_out_dir(root) / "_full.json"
        if f.exists():
            return json.loads(f.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("surface: prior full-frame load failed for %s: %s", root, e)
    return None


def build_and_stage_surfaces(
    *,
    root_strikes_by_root: dict,
    roots: list[str],
    session_date: str,
    asof: str,
    cadence_sec: int,
    now: datetime | None = None,
    spot_by_root: dict | None = None,
    quotes_by_root: dict | None = None,
    oi_by_root: dict | None = None,
    spot_fallback_by_root: dict | None = None,
) -> list[tuple[Path, str]]:
    """Build + stage the surface store for each root; return [(local_path, r2_key), …].

    Called from the live_flow poller main loop AFTER ticker JSONs are built, with the
    cycle's tide_day_state["root_strikes"]. For each root it:
      1. computes this stamp's net-premium column from the cumulative strike rollup,
      2. (Lane G) if per-contract quotes are supplied for the root, computes this stamp's
         GEX/DEX/VANNA/CHARM columns + walls + greek coverage (engine/intraday_greeks),
      3. appends them to the staged full-day frame (idempotent per stamp),
      4. writes the per-stamp {HHMM}.json (truncated replay frame) + idx.json,
      5. re-writes the private _full.json staging frame,
    and returns the (local_path, r2_key) pairs for the caller to upload via _upload_r2.

    Lane-G inputs (all optional — absent → netprem-only frame, unchanged Wave-1 behavior):
      quotes_by_root       : {ROOT → [ {exp_str,exp_years,strike,right,mid}, … ]} from
                             extract_cycle_quotes (freshest NBBO per contract this cycle).
      oi_by_root           : {ROOT → {(exp_str,strike,right) → open_interest}} from the OI
                             snapshot (EOD t-1 positions).
      spot_fallback_by_root: {ROOT → prev_close} used only when parity spot can't resolve.

    Roots with an empty strike rollup this cycle are skipped (no column written) so an
    empty cycle never blanks a good prior frame — mirrors the ticker "skip empty" guard.
    Greek failure for a root NEVER blocks its netprem column (try/except-fenced): a greek
    exception logs and the netprem-only frame is still written.
    Never raises for a single root; a bad root is logged and skipped.
    """
    now = now or datetime.now(timezone.utc)
    stamp = stamp_hhmm(now)
    time_step = stamp_hhcolonmm(now)
    spot_by_root = spot_by_root or {}
    quotes_by_root = quotes_by_root or {}
    oi_by_root = oi_by_root or {}
    spot_fallback_by_root = spot_fallback_by_root or {}
    out: list[tuple[Path, str]] = []

    for root in roots:
        root_u = root.upper()
        try:
            rstk = (root_strikes_by_root or {}).get(root_u) or (root_strikes_by_root or {}).get(root) or {}
            net = net_prem_by_strike(rstk)
            if not net:
                log.info("surface: skip %s (no strike rollup this cycle)", root_u)
                continue

            prior = _load_prior_full_frame(root_u)
            # Session rollover guard: drop a prior frame from a different session date.
            if prior and prior.get("session_date") not in (None, "", session_date):
                prior = None

            spot = spot_by_root.get(root_u, spot_by_root.get(root))

            # ── Lane G: greek columns (fenced — a greek failure must not lose netprem) ──
            greek_by_strike = None
            walls = None
            coverage = None
            try:
                # The whole quote→greek path is fenced (incl. the lookups) so a malformed
                # quotes_by_root can NEVER blank a root's netprem column.
                quotes = quotes_by_root.get(root_u) or quotes_by_root.get(root)
                if quotes:
                    oi_map = oi_by_root.get(root_u) or oi_by_root.get(root) or {}
                    spot_fb = spot_fallback_by_root.get(root_u, spot_fallback_by_root.get(root))
                    gcols = greek_columns_for_stamp(
                        quotes, oi_map=oi_map, spot=spot, spot_fallback=spot_fb)
                    greek_by_strike = gcols["by_strike"]
                    walls = gcols["walls"]
                    coverage = gcols["coverage"]
                    # If parity resolved a spot and none was passed, adopt it for the column.
                    if spot is None and gcols.get("spot") is not None:
                        spot = gcols["spot"]
                    log.info(
                        "surface: %s greeks stamp=%s coverage=%.2f n_contracts=%d spot=%s(%s)",
                        root_u, stamp, coverage or 0.0, gcols.get("n_contracts", 0),
                        gcols.get("spot"), gcols.get("spot_source"))
            except Exception as ge:  # noqa: BLE001 — netprem must still write
                log.warning("surface: greek columns failed for %s (netprem still written): %s",
                            root_u, ge)
                greek_by_strike = walls = coverage = None

            full = append_stamp(
                prior,
                stamp=stamp,
                time_step=time_step,
                net_by_strike=net,
                spot=spot,
                asof=asof,
                cadence_sec=cadence_sec,
                session_date=session_date,
                root=root_u,
                greek_by_strike=greek_by_strike,
                walls=walls,
                coverage=coverage,
            )
            validate_frame_dims(full)

            index = build_index(full, session_date=session_date, cadence_sec=cadence_sec, root=root_u)
            snap = frame_for_stamp(full, stamp)

            out_dir = _surface_out_dir(root_u)
            # Private staging frame (full day + bookkeeping) — never uploaded.
            _write_json_atomic(out_dir / "_full.json", full)
            # Public files (uploaded to R2).
            idx_path = _write_json_atomic(out_dir / "idx.json", index)
            snap_path = _write_json_atomic(out_dir / f"{stamp}.json", snap)

            out.append((idx_path, f"{R2_SURFACE_PREFIX}{root_u}/idx.json"))
            out.append((snap_path, f"{R2_SURFACE_PREFIX}{root_u}/{stamp}.json"))
            log.info("surface: staged %s stamp=%s levels=%d steps=%d metrics=%d",
                     root_u, stamp, len(full["price_levels"]), len(full["time_steps"]),
                     len(full.get("metrics") or []))
        except Exception as e:  # noqa: BLE001
            log.warning("surface: build failed for %s: %s", root_u, e)
            continue

    return out


def resolve_surface_roots(cfg: dict, root_gross_today: dict | None = None) -> list[str]:
    """Resolve the surface root list: config live_flow.surface_roots (or defaults) + top-N actives.

    config live_flow.surface_roots overrides the base list; surface_top_n (default 0) appends
    that many additional roots by day gross premium (cheap: reuses the cycle's root_gross_today,
    no extra fetch). Deduped, order-preserving.
    """
    base = [r.upper() for r in (cfg.get("surface_roots") or DEFAULT_SURFACE_ROOTS)]
    top_n = int(cfg.get("surface_top_n", 0) or 0)
    extra: list[str] = []
    if top_n > 0 and root_gross_today:
        ranked = sorted(root_gross_today.items(), key=lambda kv: kv[1], reverse=True)
        extra = [r.upper() for r, _ in ranked[: top_n * 3]]  # oversample, dedup below trims
    seen: set[str] = set()
    outl: list[str] = []
    for r in base + extra:
        if r not in seen:
            seen.add(r)
            outl.append(r)
        if top_n > 0 and len(outl) >= len(base) + top_n:
            break
    return outl


# ── dry-run: synthetic session, printed + validated, zero IO ────────────────────────

def _synthetic_session(root: str, n_stamps: int, cadence_sec: int,
                       with_greeks: bool = True) -> dict:
    """Build a full-day frame over `n_stamps` synthetic cycles (dense enough that the paint
    look is visible). Deterministic; no randomness, no network, no filesystem.

    Sinusoidal per-strike net premium with a moving hot pocket near spot — the shape the
    Terminal fixtures use so the shader's two-band signature shows in crops. When
    `with_greeks`, each stamp also synthesizes a small option chain (BS-priced at a known
    IV, with ASYMMETRIC call/put OI so the gamma walls are non-trivial), routes it through
    the REAL greek engine (extract-free — quotes are built directly), and appends the
    gex/dex/vanna/charm columns — so the dry-run validates the actual intraday-greek path,
    not a mock.
    """
    import math

    session_date = "2026-07-06"
    spot0 = 600.0
    strikes = [spot0 - 25 + 5 * i for i in range(11)]  # 575..625 step 5
    open_min = 9 * 60 + 30  # 09:30 ET
    exp_years = 5.0 / 365.0  # ~1-week tenor
    # Asymmetric OI: heavier calls above spot, heavier puts below (a plausible dealer book)
    # so the call-wall / put-wall land on distinct strikes rather than cancelling.
    def _oi(strike: float, right: str) -> float:
        base = 3000.0
        if right == "C":
            return base + max(0.0, strike - spot0) * 40.0
        return base + max(0.0, spot0 - strike) * 55.0

    full: dict | None = None
    for k in range(n_stamps):
        minute = open_min + k * (cadence_sec // 60)
        hh, mm = divmod(minute, 60)
        stamp = f"{hh:02d}{mm:02d}"
        time_step = f"{hh:02d}:{mm:02d}"
        spot = spot0 + 6 * math.sin(k / 6.0)
        # Cumulative net premium per strike: grows over the day (∝ k), signed by moneyness,
        # with a hot pocket that drifts with spot.
        net: dict[float, float] = {}
        for s in strikes:
            dist = abs(s - spot)
            hot = math.exp(-((s - spot) ** 2) / (2 * 8.0 ** 2))  # gaussian near spot
            sign = 1.0 if s >= spot else -1.0
            net[s] = round(sign * (k + 1) * 1_000_000 * (0.3 + hot) - dist * 5_000, 0)
        asof = f"{session_date}T{hh:02d}:{mm:02d}:00-04:00"

        greek_by_strike = walls = coverage = None
        if with_greeks:
            try:
                from engine.intraday_greeks import bs_price
                import numpy as _np
                iv = 0.20
                quotes: list[dict] = []
                oi_map: dict[tuple, float] = {}
                exp_str = "2026-07-13"
                for s in strikes:
                    for right, is_call in (("C", True), ("P", False)):
                        px = float(bs_price(spot, _np.array([s]), _np.array([exp_years]),
                                            _np.array([iv]), _np.array([is_call]))[0])
                        if px <= 0.02:
                            continue
                        quotes.append({"exp_str": exp_str, "exp_years": exp_years,
                                       "strike": float(s), "right": right, "mid": px})
                        oi_map[(exp_str, float(s), right)] = _oi(s, right)
                gcols = greek_columns_for_stamp(quotes, oi_map=oi_map, spot=round(spot, 2))
                greek_by_strike = gcols["by_strike"]
                walls = gcols["walls"]
                coverage = gcols["coverage"]
            except Exception:  # noqa: BLE001 — dry-run greeks are best-effort
                greek_by_strike = walls = coverage = None

        full = append_stamp(
            full, stamp=stamp, time_step=time_step, net_by_strike=net, spot=round(spot, 2),
            asof=asof, cadence_sec=cadence_sec, session_date=session_date, root=root,
            greek_by_strike=greek_by_strike, walls=walls, coverage=coverage,
        )
    return full or {}


def dry_run(root: str = "SPY", n_stamps: int = 6, cadence_sec: int = 120) -> dict:
    """Produce a sample idx + a mid-session snapshot + the latest snapshot, validate them
    against the ported contract, and return a report dict. No filesystem, no network.
    """
    full = _synthetic_session(root, n_stamps, cadence_sec)
    index = build_index(full, session_date=full.get("session_date", ""), cadence_sec=cadence_sec, root=root)
    stamps = list(full.get("stamps") or [])
    latest = stamps[-1] if stamps else ""
    mid = stamps[len(stamps) // 2] if stamps else ""
    latest_frame = frame_for_stamp(full, latest)
    mid_frame = frame_for_stamp(full, mid)

    # Contract self-checks (mirror the Terminal validators).
    checks = {
        "isSurfaceIndex": is_surface_index(index),
        "isSurfaceFrame(latest)": is_surface_frame(latest_frame),
        "isSurfaceFrame(mid)": is_surface_frame(mid_frame),
        "indexFilesContract(full)": check_index_files_contract(index, stamps)["ok"],
        "latest===stamps[-1]": index.get("latest") == (stamps[-1] if stamps else None),
        "cadenceHonest": index.get("cadenceSec") == cadence_sec and bool(index.get("cadence")),
    }
    # Dim checks throw on failure; capture as booleans (covers EVERY metric grid incl. greeks).
    try:
        validate_frame_dims(latest_frame)
        checks["dims(latest)=levels×steps"] = True
    except ValueError:
        checks["dims(latest)=levels×steps"] = False
    try:
        validate_frame_dims(mid_frame)
        checks["dims(mid)=levels×steps"] = True
    except ValueError:
        checks["dims(mid)=levels×steps"] = False

    # ── Lane G greek-grid checks (present iff the synthetic session built greeks) ──
    lf_metrics = set(latest_frame.get("metrics") or [])
    has_greeks = bool(set(GREEK_METRICS) & lf_metrics)
    if has_greeks:
        checks["greekMetricsPresent(gex,dex,vanna,charm)"] = all(
            m in latest_frame["grids"] for m in GREEK_METRICS)
        # Every greek grid must be levels×steps too (validate_frame_dims already covers it,
        # but assert the orientation explicitly for the report).
        nlev = len(latest_frame["price_levels"]); nstp = len(latest_frame["time_steps"])
        checks["greekGridsAreLevelsBySteps"] = all(
            len(latest_frame["grids"][m]) == nlev
            and all(len(r) == nstp for r in latest_frame["grids"][m])
            for m in GREEK_METRICS)
        # Walls + coverage surfaced on the replayed frames (honest nulls allowed).
        checks["wallsPresent"] = "walls" in latest_frame and set(latest_frame["walls"]) >= {
            "flip", "callWall", "putWall"}
        cov = (latest_frame.get("coverage") or {}).get("greeks")
        checks["coveragePresent(0..1)"] = (
            isinstance(cov, (int, float)) and 0.0 <= float(cov) <= 1.0)
        # Mid frame's gex grid has strictly fewer columns than latest (greek replay
        # truncation is real, not forward-filled). Column count = time steps realized.
        mid_gex = mid_frame["grids"].get(METRIC_GEX) or []
        lat_gex = latest_frame["grids"].get(METRIC_GEX) or []
        mid_cols = len(mid_gex[0]) if mid_gex else 0
        lat_cols = len(lat_gex[0]) if lat_gex else 0
        checks["greekReplayTruncates"] = lat_cols > 0 and mid_cols < lat_cols

    return {
        "root": root,
        "cadenceSec": cadence_sec,
        "index": index,
        "latest_stamp": latest,
        "mid_stamp": mid,
        "latest_frame": latest_frame,
        "mid_frame": mid_frame,
        "has_greeks": has_greeks,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow-Surface snapshot store materializer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print + validate a synthetic idx/snapshot; no IO. (default action)")
    parser.add_argument("--root", default="SPY", help="Root for the dry-run sample")
    parser.add_argument("--stamps", type=int, default=6, help="Synthetic stamp count for the dry-run")
    parser.add_argument("--cadence-sec", type=int, default=120,
                        help="True write interval for the honesty stamp (default 120 = poller cadence)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Default (and only) CLI action is the dry-run — the live path is invoked in-process
    # from the poller loop, never as a standalone cron (no second, unrelated cadence).
    report = dry_run(root=args.root, n_stamps=args.stamps, cadence_sec=args.cadence_sec)

    print("=== SurfaceIndex (live_flow/surface/{}/idx.json) ===".format(args.root))
    print(json.dumps(report["index"], indent=2))
    print("\n=== SurfaceFrame @ mid stamp {} (live_flow/surface/{}/{}.json) ===".format(
        report["mid_stamp"], args.root, report["mid_stamp"]))
    print(json.dumps(report["mid_frame"], indent=2, default=str))
    print("\n=== SurfaceFrame @ latest stamp {} — shape summary ===".format(report["latest_stamp"]))
    lf = report["latest_frame"]
    def _dims(m):
        g = lf["grids"].get(m)
        return [len(g), len(g[0]) if g else 0] if g is not None else None
    print(json.dumps({
        "spot": lf["spot"],
        "n_price_levels": len(lf["price_levels"]),
        "n_time_steps": len(lf["time_steps"]),
        "grid_dims(netprem)": _dims(METRIC_NETPREM),
        "grid_dims(gex)": _dims(METRIC_GEX),
        "grid_dims(dex)": _dims(METRIC_DEX),
        "grid_dims(vanna)": _dims(METRIC_VANNA),
        "grid_dims(charm)": _dims(METRIC_CHARM),
        "walls": lf.get("walls"),
        "coverage": lf.get("coverage"),
        "cadence": lf["cadence"],
        "metrics": lf["metrics"],
    }, indent=2, default=str))

    if report.get("has_greeks"):
        print("\n=== greek grids @ latest stamp {} — last-column (per-strike net dealer exposure) ===".format(
            report["latest_stamp"]))
        pls = lf["price_levels"]
        sample = {"price_levels": pls}
        for m in GREEK_METRICS:
            g = lf["grids"].get(m)
            if g:
                sample[m + "[:, last]"] = [round(row[-1], 2) for row in g]
        sample["walls"] = lf.get("walls")
        sample["coverage"] = lf.get("coverage")
        print(json.dumps(sample, indent=2, default=str))
        print("(DISPLAY-ONLY dealer-exposure MAP — long-call/short-put sign is an assumption, "
              "levels are where hedging concentrates, not targets; nulls/0 = no quoted+OI'd "
              "contract at that strike this cycle.)")

    print("\n=== contract self-checks (mirror surfaceContract.ts + Lane G greek grids) ===")
    print(json.dumps(report["checks"], indent=2))

    all_ok = all(report["checks"].values())
    print("\nALL CHECKS PASS" if all_ok else "\nCHECKS FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
