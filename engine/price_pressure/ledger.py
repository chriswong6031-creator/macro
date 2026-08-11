"""engine.price_pressure.ledger — the point-in-time event ledger (masterplan §5).

``data/price_pressure/events.parquet``, one row per (ticker, shock date, side),
unique on that key.  Two blocks with DIFFERENT contracts, stated here because
conflating them is how a PIT ledger quietly becomes a lookahead artifact:

**Identity / PIT block** — frozen at t0, never rewritten.  Every field is
computable from data that existed at the close of t0.  Nothing in it can move
when tomorrow's bars arrive.  It has exactly ONE sanctioned exception,
``complete_vix_stamps`` (prereg §10.1): a NULL ``vix_pctile`` — the shape a row
takes when the FRED store trailed the tape on its harvest night — may be filled
once with t0's own close percentile, against an immutable receipt.  A non-null
stamp stays immutable, and no other column is reachable from that seam.

**Grading block** — advanced by the nightly as windows mature.  A horizon field
is NULL until its window has fully elapsed (no partial peeking).  The display
``state`` is a different contract again: it is "the realized path as of the last
close", stamped with ``state_asof``, and it is not a horizon grade.

House rules this module implements literally:

* **No early close** (review BLOCKER 4).  A 100% retrace on day 3 sets
  ``days_to_first_100pct_retrace = 3`` and the row still grades at 21d and 60d.
  Closing on the good news and letting the bad news run to the window is exactly
  the upside-only path censoring the gauntlet exists to prevent.
* **Terminals are window-end grades, not flips**, so the 2-consecutive-close
  debounce (DNR:KILL-ONE-TICK-ESCALATION) applies to DISPLAY states only.
* **Dead tape stays in the denominator.**  Bars that stop more than
  ``DEAD_TAPE_SESSIONS`` before the store's newest session grade
  ``DELISTED_OR_HALTED`` — inside the terminal shares, never dropped
  (resolution-conditioned denominators delete losers).  A row whose window
  simply has not elapsed yet stays OPEN and is counted as open.
* **Nightly is the sole writer** (``engine.ledger_lane.nightly_advance_enabled``).
  Any lane may compute; only the nightly lane may persist.
* **Eras**: ``backfill`` = the frozen historical seed, ``gap`` = harvested by
  the self-healing catch-up between the seed and go-live, ``forward`` = seen on
  its own night.  §7 evidence is forward-era only, so era is never rewritten.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
from engine.price_pressure import (
    DEAD_TAPE_SESSIONS,
    ENGINE_VERSION,
    EPISODE_JOIN_SESSIONS,
    LEDGER_HORIZONS,
    LOG_DENOM_FLOOR,
    RETRACE_FULL,
    RETRACE_PARTIAL,
    SLIDE_FRAC,
    TERMINAL_PRIMARY,
    TERMINAL_SECONDARY,
)

log = logging.getLogger("price_pressure.ledger")

LEDGER_REL: tuple[str, ...] = ("price_pressure", "events.parquet")

ERAS: tuple[str, ...] = ("backfill", "gap", "forward")
#: Eras the historical backfill must never touch (masterplan §5 / §7).
PROTECTED_ERAS: frozenset[str] = frozenset({"gap", "forward"})

KEY: tuple[str, ...] = ("date", "ticker", "side")

#: Display-state vocabulary (§5.1), exhaustive on the running retrace fraction.
DOWN_STATES = ("SHOCK", "SLIDING", "HOLDING", "RETRACING")
UP_STATES = ("SHOCK", "EXTENDING", "HOLDING", "FADING")
DELISTED = "DELISTED_OR_HALTED"

# Identity block — frozen at t0.
IDENTITY_COLUMNS: tuple[str, ...] = (
    "date", "ticker", "side", "era", "harvested_asof", "engine_version",
    "sector", "peer_basis", "basket", "basket_ret", "basket_resid",
    "ret", "peer_ret", "resid", "resid_z", "resid_sd", "price",
    "vol_multiple", "txn_multiple", "avg_trade_size_rel", "clv", "gap",
    "intraday_ret", "amihud_rel", "spread_shock", "prior5_resid", "run_sign",
    "dollar_adv_med", "pos52", "dist_52w_low",
    "earn8k", "mat8k", "edgar_covered", "revisions_covered", "family",
    "panel_shock_count", "panel_share_z2", "spy_ret_z", "peer_shock_count",
    "vix_pctile",
)

# Grading block — advanced by the nightly.
GRADING_COLUMNS: tuple[str, ...] = (
    "episode_id", "first_of_episode", "followup_shock",
    *(f"first_in_{h}" for h in LEDGER_HORIZONS),
    *(f"fwd{h}" for h in LEDGER_HORIZONS),
    *(f"retrace_{h}" for h in LEDGER_HORIZONS),
    "max_adverse_resid", "max_favorable_resid", "days_to_first_100pct_retrace",
    "sessions_elapsed", "truncated", "dead_tape",
    "state", "state_pending", "state_updated", "state_asof",
    f"terminal_state_{TERMINAL_PRIMARY}d", f"terminal_state_{TERMINAL_SECONDARY}d",
    "closed", "closed_at", "graded_asof",
)

LEDGER_COLUMNS: tuple[str, ...] = IDENTITY_COLUMNS + GRADING_COLUMNS

_BOOL_COLUMNS = frozenset({
    "earn8k", "mat8k", "edgar_covered", "revisions_covered",
    "first_of_episode", "followup_shock", "truncated", "dead_tape", "closed",
    *(f"first_in_{h}" for h in LEDGER_HORIZONS),
})
_STR_COLUMNS = frozenset({
    "ticker", "side", "era", "harvested_asof", "engine_version", "sector",
    "peer_basis", "basket", "family", "episode_id", "state", "state_pending",
    "state_updated", "state_asof", "closed_at", "graded_asof",
    f"terminal_state_{TERMINAL_PRIMARY}d", f"terminal_state_{TERMINAL_SECONDARY}d",
})

#: Harvest columns -> ledger names.  Pure renames; `peer_ret` and `resid_sd` are
#: algebra on two harvested columns (see detect.harvest), never a second pipeline.
_HARVEST_RENAME = {
    "abn_volume": "vol_multiple",
    "abn_txn": "txn_multiple",
    "dv_med": "dollar_adv_med",
    "close": "price",
}


# ---------------------------------------------------------------------------
# paths and IO
# ---------------------------------------------------------------------------

def ledger_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*LEDGER_REL)


def empty_ledger() -> pd.DataFrame:
    """A correctly-typed, zero-row ledger — the shape every reader can rely on."""
    cols: dict[str, pd.Series] = {}
    for c in LEDGER_COLUMNS:
        if c == "date":
            cols[c] = pd.Series(dtype="datetime64[ns]")
        elif c in _BOOL_COLUMNS:
            cols[c] = pd.Series(dtype="bool")
        elif c in _STR_COLUMNS:
            cols[c] = pd.Series(dtype="object")
        else:
            cols[c] = pd.Series(dtype="float64")
    return pd.DataFrame(cols)


def read_ledger(data_root: Path) -> pd.DataFrame:
    """Read the stored ledger, or an empty typed frame.  Never raises."""
    p = ledger_path(data_root)
    if not p.exists():
        return empty_ledger()
    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001 — a torn ledger must not kill the lane
        log.warning("price_pressure: ledger unreadable at %s (%s)", p, exc)
        return empty_ledger()
    return _coerce(df)


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Force the canonical column set, order and dtypes — the byte-stability seam."""
    out = pd.DataFrame(index=df.index)
    for c in LEDGER_COLUMNS:
        if c == "date":
            out[c] = pd.to_datetime(df[c]).dt.normalize() if c in df else pd.NaT
        elif c in _BOOL_COLUMNS:
            out[c] = (df[c].fillna(False).astype(bool) if c in df
                      else pd.Series(False, index=df.index, dtype="bool"))
        elif c in _STR_COLUMNS:
            if c in df:
                s = df[c].astype("object")
                out[c] = s.where(s.notna(), None)
            else:
                out[c] = pd.Series([None] * len(df), index=df.index, dtype="object")
        else:
            out[c] = (pd.to_numeric(df[c], errors="coerce").astype("float64") if c in df
                      else pd.Series(np.nan, index=df.index, dtype="float64"))
    return out.reset_index(drop=True)


def write_ledger(df: pd.DataFrame, data_root: Path, *,
                 require_nightly_lane: bool = True) -> dict:
    """Persist the ledger — gated on the nightly lane (house law).

    ``require_nightly_lane=False`` is the test/backfill seam only; the backfill
    is an operator-run one-shot off CI, which is exactly the case the gate is
    not meant to catch.
    """
    if not ledger_write_allowed(require_nightly_lane=require_nightly_lane):
        log.info("price_pressure: ledger write skipped (COLLECT_LANE != nightly)")
        return {"written": False, "reason": "off_nightly_lane", "rows": int(len(df))}
    p = ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = sort_ledger(_coerce(df))
    out.to_parquet(p, index=False)
    return {"written": True, "rows": int(len(out)), "path": str(p),
            "closed": int(out["closed"].sum()), "open": int((~out["closed"]).sum())}


def ledger_write_allowed(*, require_nightly_lane: bool = True) -> bool:
    """Whether this process is the sanctioned writer for the persisted ledger."""
    return not require_nightly_lane or _ledger_advance_enabled()


def sort_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical STORAGE order: ascending (date, ticker, side).

    Deliberately not the display order.  Lists shown to a human are
    most-recent-first then ticker (``display_order``); a stored frame sorted that
    way would churn its whole byte layout every night.
    """
    return df.sort_values(list(KEY), kind="stable").reset_index(drop=True)


def display_order(df: pd.DataFrame) -> pd.DataFrame:
    """The one ordering any human-facing list may use: newest first, then ticker.

    Ordering by |resid_z| would be a ranking, and this artifact's authority block
    says it cannot rank (masterplan §9, review finding 11).
    """
    if df.empty:
        return df
    out = df.copy()
    out["_d"] = pd.to_datetime(out["date"])
    out = out.sort_values(["_d", "ticker", "side"],
                          ascending=[False, True, True], kind="stable")
    return out.drop(columns="_d").reset_index(drop=True)


# ---------------------------------------------------------------------------
# pure math (unit-tested)
# ---------------------------------------------------------------------------

def retrace_fraction(fwd: float | None, resid0: float | None, side: str) -> float | None:
    """Share of the t0 residual given back, in ONE consistent log space (§5).

        down:  frac = fwd_h / (−log1p(resid_t0))
        up:    frac = −fwd_h / ( log1p(resid_t0))

    ``fwd_h`` is already the LSR cumulative of ``log1p(resid)``, so the same
    transform sits on both sides of the ratio.  ``resid_t0`` is clipped exactly
    as ``derive`` clips it before the cumsum, so a shared numerator/denominator
    convention is guaranteed rather than assumed.

    Returns None when the denominator is degenerate (|log1p(r0)| below
    ``LOG_DENOM_FLOOR``): a near-zero t0 residual makes the ratio explode, and a
    null is the honest print.
    """
    if fwd is None or resid0 is None:
        return None
    f, r0 = float(fwd), float(resid0)
    if not np.isfinite(f) or not np.isfinite(r0):
        return None
    l0 = float(np.log1p(np.clip(r0, -0.9, 5.0)))
    if not np.isfinite(l0) or abs(l0) < LOG_DENOM_FLOOR:
        return None
    return f / (-l0) if side == "down" else -f / l0


def classify_display(frac: float | None, side: str) -> str | None:
    """§5.1 display bucket — EXHAUSTIVE on the retrace fraction, no dead zone."""
    if frac is None or not np.isfinite(frac):
        return None
    if frac >= RETRACE_PARTIAL:
        return "RETRACING" if side == "down" else "FADING"
    if frac <= SLIDE_FRAC:
        return "SLIDING" if side == "down" else "EXTENDING"
    return "HOLDING"


def terminal_grade(frac: float | None, side: str, horizon: int) -> str | None:
    """§5.1 window-end grade.  No debounce: this is not a flip, it is a reading."""
    if frac is None or not np.isfinite(frac):
        return None
    suffix = f"_{horizon}D"
    if frac >= RETRACE_FULL:
        return ("RECOVERED" if side == "down" else "GAVE_BACK") + suffix
    if frac >= RETRACE_PARTIAL:
        return "PARTIAL" + suffix
    return ("ACCEPTED_LOWER" if side == "down" else "KEPT") + suffix


def resolve_state(candidates: list[str | None]) -> tuple[str, str | None, int | None]:
    """Run the 2-consecutive-close debounce over a daily candidate sequence.

    ``candidates[k]`` is the bucket implied by the close at t0+k+1, or None when
    that close is missing.  Returns ``(state, state_pending, flip_offset)`` where
    ``flip_offset`` is the 1-based session offset of the last flip.

    A single qualifying close only ever sets ``state_pending``
    (DNR:KILL-ONE-TICK-ESCALATION); a missing close is a NON-observation that
    clears both the pending badge and the run, so a hole in the tape can never
    combine with a much later close to look like two in a row.
    """
    state, pending, prev, flip = "SHOCK", None, None, None
    for k, cand in enumerate(candidates, start=1):
        if cand is None:
            pending, prev = None, None
            continue
        if cand == state:
            pending, prev = None, cand
            continue
        if prev == cand:
            state, pending, flip = cand, None, k
        else:
            pending = cand
        prev = cand
    return state, pending, flip


def catchup_window(sessions: pd.DatetimeIndex, ledger_max: pd.Timestamp | None, *,
                   lookback: int = 5, min_sessions: int = 15,
                   cap: int = 90) -> pd.DatetimeIndex:
    """The self-healing re-harvest window (masterplan §6 / §4.0).

    From (ledger max − ``lookback`` sessions) to the store's newest session, never
    shorter than ``min_sessions`` and never longer than ``cap``.  The overlap is
    the point: a night that ran against a lagging store snapshot is silently
    re-harvested the next night, and the (ticker,date,side) key makes the re-run
    idempotent.  An empty ledger takes the ``cap`` tail — a nightly must never
    accidentally become the historical backfill.
    """
    sessions = pd.DatetimeIndex(sessions)
    if not len(sessions):
        return sessions
    if ledger_max is None or pd.isna(ledger_max):
        return sessions[-cap:]
    pos = int(sessions.searchsorted(pd.Timestamp(ledger_max).normalize()))
    win = sessions[max(0, pos - lookback):]
    if len(win) < min_sessions:
        win = sessions[-min_sessions:]
    if len(win) > cap:
        win = win[-cap:]
    return win


# ---------------------------------------------------------------------------
# identity rows
# ---------------------------------------------------------------------------

def identity_rows(ev: pd.DataFrame, *, era: str, harvested_asof: str,
                  sectors: pd.Series, peer_basis: pd.DataFrame,
                  breadth: pd.DataFrame, peer_shocks: pd.DataFrame,
                  spy_z: pd.Series, vix_pct: pd.Series,
                  pos_frames: dict[str, pd.DataFrame],
                  revisions_covered: set[str]) -> pd.DataFrame:
    """Assemble the frozen identity block from a harvest plus PIT context."""
    if ev.empty:
        return empty_ledger()
    out = ev.rename(columns=_HARVEST_RENAME).copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["era"] = era
    out["harvested_asof"] = harvested_asof
    out["engine_version"] = ENGINE_VERSION
    out["peer_ret"] = out["ret"].astype("float64") - out["resid"].astype("float64")
    out["sector"] = out["ticker"].map(sectors.to_dict()).astype("object")
    out["revisions_covered"] = out["ticker"].isin(revisions_covered)

    def _norm(frame: pd.DataFrame) -> pd.DataFrame:
        f = frame.copy()
        f.index = pd.DatetimeIndex(f.index).normalize()
        return f

    def _cell(frame: pd.DataFrame, default=np.nan):
        frame = _norm(frame)
        vals = []
        for t, dt in zip(out["ticker"], out["date"]):
            v = default
            if t in frame.columns and dt in frame.index:
                v = frame.at[dt, t]
            vals.append(v)
        return vals

    def _bydate(series: pd.Series) -> dict:
        s = series.copy()
        s.index = pd.DatetimeIndex(s.index).normalize()
        return s.to_dict()

    out["peer_basis"] = ["sector" if bool(v) else "market"
                         for v in _cell(peer_basis, False)]
    out["pos52"] = _cell(pos_frames["pos52"])
    out["dist_52w_low"] = _cell(pos_frames["dist_52w_low"])

    for col in ("panel_shock_count", "panel_share_z2"):
        out[col] = out["date"].map(_bydate(breadth[col])) if col in breadth else np.nan
    out["spy_ret_z"] = out["date"].map(_bydate(spy_z))
    out["vix_pctile"] = out["date"].map(_bydate(vix_pct))

    peers = _norm(peer_shocks)
    peer_counts = []
    for sec, dt in zip(out["sector"], out["date"]):
        v = np.nan
        if isinstance(sec, str) and sec in peers.columns and dt in peers.index:
            v = float(peers.at[dt, sec])
        peer_counts.append(v)
    out["peer_shock_count"] = peer_counts

    return sort_ledger(_coerce(out))


# ---------------------------------------------------------------------------
# the ONE sanctioned write into the frozen identity block (prereg §10.1)
# ---------------------------------------------------------------------------

#: The single identity-block field a completion may ever fill.  Named as a
#: constant so the exception is greppable and so the guard below reads off the
#: same name the caller does.
COMPLETABLE_COLUMN = "vix_pctile"


def complete_vix_stamps(df: pd.DataFrame,
                        completions: list[dict] | tuple[dict, ...]) -> pd.DataFrame:
    """Fill NULL ``vix_pctile`` cells named by ``completions``.  Nothing else.

    The identity block is frozen at t0 and this is its ONLY sanctioned
    exception, registered in ``research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md``
    §3/§10.1: the VIXCLS store trails the tape by one session at the 22:30Z
    harvest, so a forward row typically stamps NULL through no property of its
    own, and under §9's exclusion rule both evidence arms would have starved to
    zero forever.  A null-at-harvest stamp is therefore completed ONCE with
    t0's own close percentile — an exact late-arriving value, never a
    forward-fill, never a revision.

    Each completion is ``{"pos", "ticker", "date", "side", "vix_pctile"}`` where
    ``pos`` is a POSITIONAL index into ``df``.  The key fields are not
    decoration: they are re-checked against the row at that position, so a
    caller that hands over a stale plan raises instead of stamping the wrong
    name.  Three invariants are asserted BEFORE the frame is returned —

    * every target cell was null (a non-null stamp is immutable, §3);
    * ``vix_pctile`` only ever gains values, never loses one;
    * every OTHER column, the row order and the row count are untouched.

    Structural, not conventional: the function writes into exactly one column by
    name and then proves the rest of the frame is byte-semantics-identical.
    """
    if df.empty or not len(completions):
        return df
    out = df.copy()
    col = COMPLETABLE_COLUMN
    before = pd.to_numeric(df[col], errors="coerce")
    vals = before.to_numpy(dtype="float64", copy=True)

    dates = pd.to_datetime(df["date"]).dt.normalize()
    tickers = df["ticker"].to_numpy()
    sides = df["side"].to_numpy()
    for c in completions:
        pos = int(c["pos"])
        if not (0 <= pos < len(out)):
            raise AssertionError(f"complete_vix_stamps: position {pos} outside the ledger")
        key = (pd.Timestamp(dates.iloc[pos]), str(tickers[pos]), str(sides[pos]))
        want = (pd.Timestamp(c["date"]).normalize(), str(c["ticker"]), str(c["side"]))
        if key != want:
            raise AssertionError(
                f"complete_vix_stamps: row {pos} is {key}, plan says {want}")
        if not np.isnan(vals[pos]):
            raise AssertionError(
                f"complete_vix_stamps: {want} already stamped {vals[pos]!r} — "
                "a non-null stamp is immutable (prereg §3)")
        v = float(c[col])
        if not np.isfinite(v):
            raise AssertionError(f"complete_vix_stamps: {want} completion value {v!r}")
        vals[pos] = v
    out[col] = vals

    after = pd.to_numeric(out[col], errors="coerce")
    filled = before.isna() & after.notna()
    if int(filled.sum()) != len(completions):
        raise AssertionError("complete_vix_stamps: filled cell count != completions")
    if not after[before.notna()].equals(before[before.notna()]):
        raise AssertionError("complete_vix_stamps: an existing stamp moved")
    if bool((before.notna() & after.isna()).any()):
        raise AssertionError("complete_vix_stamps: an existing stamp was cleared")
    others = [c for c in out.columns if c != col]
    if not out[others].equals(df[others]):
        raise AssertionError("complete_vix_stamps: a column outside vix_pctile moved")
    return out


# ---------------------------------------------------------------------------
# episodes and per-horizon freshness
# ---------------------------------------------------------------------------

def _session_positions(dates: pd.Series, sessions: pd.DatetimeIndex) -> np.ndarray:
    """Position of each date on a session axis that covers the ledger AND the panel."""
    axis = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(sessions).normalize())
                                   | set(pd.to_datetime(dates).dt.normalize())))
    return axis.searchsorted(pd.to_datetime(dates).dt.normalize().to_numpy())


def assign_episodes(df: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Episode ids, follow-up flags and the per-horizon ``first_in_h`` freshness.

    A same-side shock landing within ``EPISODE_JOIN_SESSIONS`` sessions of the
    NEWEST shock already in an open episode joins it, so a three-day flush is one
    episode rather than three "independent" observations.  The id is anchored on
    the episode's first date, which never moves — recomputing over a grown ledger
    is therefore stable, and a re-run is byte-identical.

    ``first_in_h`` (no same-side shock in the prior h sessions) is the honest-N
    key the base-rate tables use, and it is PER HORIZON on purpose: a 5d table
    and a 21d table do not have the same independence problem.
    """
    if df.empty:
        return df
    out = df.copy()
    pos = _session_positions(out["date"], sessions)
    out["_pos"] = pos
    out = out.sort_values(["ticker", "side", "_pos"], kind="stable")

    ep_ids: list[str] = []
    first_of: list[bool] = []
    firsts: dict[int, list[bool]] = {h: [] for h in LEDGER_HORIZONS}
    prev_key: tuple[str, str] | None = None
    anchor_date: str | None = None
    last_pos: int | None = None
    hist: list[int] = []
    for tic, side, p, dt in zip(out["ticker"], out["side"], out["_pos"], out["date"]):
        key = (tic, side)
        if key != prev_key:
            prev_key, anchor_date, last_pos, hist = key, None, None, []
        if last_pos is None or (p - last_pos) > EPISODE_JOIN_SESSIONS:
            anchor_date = pd.Timestamp(dt).strftime("%Y-%m-%d")
            first_of.append(True)
        else:
            first_of.append(False)
        ep_ids.append(f"{tic}:{side}:{anchor_date}")
        for h in LEDGER_HORIZONS:
            firsts[h].append(not any((p - q) <= h for q in hist))
        hist.append(int(p))
        # Only the last max-horizon window can ever matter, so the scan stays O(1)
        # rather than growing with a name's whole shock history.
        hist = [q for q in hist if (p - q) <= max(LEDGER_HORIZONS)]
        last_pos = int(p)

    out["episode_id"] = ep_ids
    out["first_of_episode"] = first_of
    out["followup_shock"] = [not b for b in first_of]
    for h in LEDGER_HORIZONS:
        out[f"first_in_{h}"] = firsts[h]
    return sort_ledger(_coerce(out.drop(columns="_pos")))


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------

def grade(df: pd.DataFrame, cum: pd.DataFrame, sessions: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    """Advance every OPEN row against the realized residual path.  Pure.

    Closed rows are immutable and are skipped; a row whose ticker or date is no
    longer in the panel window is ungradeable this run and is left exactly as it
    was, rather than being silently re-graded against a frame that cannot see it.
    """
    stats = {"advanced": 0, "closed": 0, "skipped_closed": 0, "ungradeable": 0}
    if df.empty:
        return df, stats
    out = df.copy()
    sessions = pd.DatetimeIndex(sessions)
    last = len(sessions) - 1
    spos = {d: i for i, d in enumerate(sessions.normalize())}
    cum_cols = set(cum.columns)
    cache: dict[str, tuple[np.ndarray, int]] = {}
    grade_asof = sessions[-1].strftime("%Y-%m-%d") if last >= 0 else None

    # Only the five fields grading reads are materialised: a 35k-row x 70-column
    # to_dict("records") is ~2.5M Python objects for no reason.
    tickers = out["ticker"].to_numpy()
    dates = pd.to_datetime(out["date"]).dt.normalize().to_numpy()
    sides = out["side"].to_numpy()
    resids = pd.to_numeric(out["resid"], errors="coerce").to_numpy(dtype="float64")
    closed_flags = out["closed"].fillna(False).astype(bool).to_numpy()

    updates: dict[int, dict] = {}
    for k, ridx in enumerate(out.index):
        if closed_flags[k]:
            stats["skipped_closed"] += 1
            continue
        tic = tickers[k]
        d0 = pd.Timestamp(dates[k])
        if tic not in cum_cols or d0 not in spos:
            stats["ungradeable"] += 1
            continue
        got = cache.get(tic)
        if got is None:
            col = cum[tic].to_numpy(dtype="float64")
            fin = np.flatnonzero(np.isfinite(col))
            got = (col, int(fin[-1]) if fin.size else -1)
            cache[tic] = got
        col, last_finite = got
        i = spos[d0]
        elapsed = int(min(TERMINAL_SECONDARY, last - i))
        base = col[i]
        if not np.isfinite(base):
            stats["ungradeable"] += 1
            continue
        path = (col[i + 1: i + 1 + elapsed] - base) if elapsed > 0 else np.empty(0)
        updates[ridx] = _grade_one(str(sides[k]), float(resids[k]), path, elapsed,
                                   i, last, last_finite, sessions, grade_asof)
        stats["advanced"] += 1
        if updates[ridx].get("closed"):
            stats["closed"] += 1

    if updates:
        # Column-wise assignment through an object staging dtype: a 35k-row
        # ledger x ~25 grading fields is ~900k scalar .at writes otherwise, and
        # pandas 3 rejects several of those on dtype grounds anyway.  _coerce
        # re-types everything on the way out.
        upd_df = pd.DataFrame.from_records(list(updates.values()),
                                           index=list(updates.keys()))
        for c in upd_df.columns:
            out[c] = out[c].astype("object")
            out.loc[upd_df.index, c] = upd_df[c].to_numpy()
    return _coerce(out), stats


def _grade_one(side: str, r0: float, path: np.ndarray, elapsed: int, i: int,
               last: int, last_finite: int, sessions: pd.DatetimeIndex,
               grade_asof: str | None) -> dict:
    """All grading fields for one open row.  See the module docstring's contracts."""
    fracs = [retrace_fraction(float(v) if np.isfinite(v) else None, r0, side) for v in path]

    upd: dict = {"sessions_elapsed": float(elapsed), "graded_asof": grade_asof}

    # Dead tape: the name's last observation sits well behind the store's newest
    # session AND inside this row's own grading window, so the window can never
    # complete. That is a delisting/halt, not a young row.
    dead = bool(last_finite >= 0 and last_finite < last - DEAD_TAPE_SESSIONS
                and last_finite <= i + TERMINAL_SECONDARY)
    upd["dead_tape"] = dead

    truncated = dead
    for h in LEDGER_HORIZONS:
        fwd = frac = None
        if h <= elapsed:
            v = path[h - 1]
            if np.isfinite(v):
                fwd = float(v)
                frac = fracs[h - 1]
            else:
                truncated = True
        upd[f"fwd{h}"] = fwd if fwd is not None else np.nan
        upd[f"retrace_{h}"] = frac if frac is not None else np.nan
    upd["truncated"] = bool(truncated)

    good = np.array([f for f in fracs if f is not None], dtype="float64")
    if good.size:
        upd["max_favorable_resid"] = float(np.nanmax(good))
        upd["max_adverse_resid"] = float(np.nanmin(good))
    else:
        upd["max_favorable_resid"] = np.nan
        upd["max_adverse_resid"] = np.nan

    # Observational only — it never closes the row (review BLOCKER 4).
    hit = next((k for k, f in enumerate(fracs, start=1) if f is not None and f >= 1.0), None)
    upd["days_to_first_100pct_retrace"] = float(hit) if hit is not None else np.nan

    state, pending, flip = resolve_state([classify_display(f, side) for f in fracs])
    upd["state"] = state
    upd["state_pending"] = pending
    upd["state_asof"] = (sessions[i + elapsed].strftime("%Y-%m-%d") if elapsed > 0
                         else sessions[i].strftime("%Y-%m-%d"))
    upd["state_updated"] = (sessions[i + flip].strftime("%Y-%m-%d")
                            if flip is not None else None)

    for h, label in ((TERMINAL_PRIMARY, f"terminal_state_{TERMINAL_PRIMARY}d"),
                     (TERMINAL_SECONDARY, f"terminal_state_{TERMINAL_SECONDARY}d")):
        if h <= elapsed and np.isfinite(path[h - 1]):
            upd[label] = terminal_grade(fracs[h - 1], side, h)
        elif dead:
            upd[label] = DELISTED          # a loser that left the tape stays in the table
        else:
            upd[label] = None              # calendar-censored: still open, counted as open

    tail = upd[f"terminal_state_{TERMINAL_SECONDARY}d"]
    upd["closed"] = bool(tail)
    upd["closed_at"] = (sessions[min(i + TERMINAL_SECONDARY, last)].strftime("%Y-%m-%d")
                        if tail else None)
    return upd


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def merge(stored: pd.DataFrame, fresh: pd.DataFrame, *, mode: str,
          asof_session: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict]:
    """Idempotent union of a stored ledger and a fresh harvest, keyed on (date,ticker,side).

    ``mode="nightly"``  — never rewrites an existing row.  New rows take
    ``era="forward"`` when they landed on ``asof_session`` (harvested on their
    own night) and ``era="gap"`` otherwise, because a row the catch-up found
    days late is not forward-era evidence (§7).

    ``mode="backfill"`` — refreshes ``era="backfill"`` rows and REFUSES to touch
    anything already ``forward`` or ``gap``, so a re-seed can never overwrite
    accrued forward evidence.
    """
    if mode not in ("nightly", "backfill"):
        raise ValueError(f"unknown merge mode {mode!r}")
    stored = _coerce(stored) if len(stored) else empty_ledger()
    fresh = _coerce(fresh) if len(fresh) else empty_ledger()
    stats = {"stored": int(len(stored)), "harvested": int(len(fresh)),
             "appended": 0, "refreshed": 0, "protected": 0, "era_forward": 0,
             "era_gap": 0}

    skey = set(map(tuple, stored[list(KEY)].to_numpy())) if len(stored) else set()
    protected = (set(map(tuple, stored.loc[stored["era"].isin(PROTECTED_ERAS), list(KEY)]
                         .to_numpy())) if len(stored) else set())

    if mode == "backfill":
        keep = stored[stored["era"].isin(PROTECTED_ERAS)] if len(stored) else stored
        stats["protected"] = int(len(keep))
        fkeys = list(map(tuple, fresh[list(KEY)].to_numpy())) if len(fresh) else []
        take = [k not in protected for k in fkeys]
        add = fresh.loc[take].copy() if len(fresh) else fresh
        add["era"] = "backfill"
        stats["refreshed"] = int(len(add))
        merged = pd.concat([keep, add], ignore_index=True) if len(keep) else add
        return sort_ledger(_coerce(merged)), stats

    fkeys = list(map(tuple, fresh[list(KEY)].to_numpy())) if len(fresh) else []
    take = [k not in skey for k in fkeys]
    add = fresh.loc[take].copy() if len(fresh) else fresh
    if len(add):
        asof = pd.Timestamp(asof_session).normalize() if asof_session is not None else None
        eras = ["forward" if (asof is not None and pd.Timestamp(d).normalize() == asof)
                else "gap" for d in add["date"]]
        add["era"] = eras
        stats["era_forward"] = int(sum(1 for e in eras if e == "forward"))
        stats["era_gap"] = int(sum(1 for e in eras if e == "gap"))
    stats["appended"] = int(len(add))
    merged = pd.concat([stored, add], ignore_index=True) if len(stored) else add
    return sort_ledger(_coerce(merged)), stats
