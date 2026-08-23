#!/usr/bin/env python3
"""scripts/topup_thetadata_day.py — ThetaData T1 store top-up + daily maintainer.

WHY THIS EXISTS (R0.2, Options Superintelligence masterplan 2026-07-31)
─────────────────────────────────────────────────────────────────────────────
ThetaData's EOD report for session T is not available on T's evening — measured
2026-07-31 20:42 ET: greeks/oi/eod for that day's session all returned 0 rows.
The report lands overnight (OPRA OI ~03:30 PT / 06:30 ET). The nightly backfill
refresh pass runs at ~16:10 ET and therefore only ever captures T-1. This
script started as a bounded pre-open top-up (N roots x 1 day) and is extended
here (AD-1T1, `research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md`, R2) into
the canonical full-universe DAILY incremental maintainer of the T1 store, so a
normal market-day run keeps a lawful S/D source pair at >=90% AD-universe
coverage without the whole-year re-pull the old daily keepalive used.

THREE MODES
─────────────────────────────────────────────────────────────────────────────
    python -m scripts.topup_thetadata_day --roots SPY,QQQ [--date YYYY-MM-DD]
        Legacy bounded mode — byte-compatible behavior (§G). Pulls ONE session
        eod/oi/greeks for the named roots and merges into the store.

    python -m scripts.topup_thetadata_day --roots @universe --date YYYY-MM-DD
        Explicit catch-up (F10): same 3-tier one-day ensure as the legacy mode,
        but over the FULL resolved T1 universe. This is the runbook's tool for
        gaps of >=2 sessions — NOT the daily mode, which never sweeps history.

    python -m scripts.topup_thetadata_day --daily [--workers N] [--deadline-min M] [--force-run]
        Market-wide incremental daily mode (§A-§D). Gate-checked (F4), ensures
        exactly the S/D cells of §A4 for the full T1 universe, and writes a
        `daily_refresh` health receipt into the store's `_manifest.json`.

MERGE SEMANTICS
─────────────────────────────────────────────────────────────────────────────
The backfill's year-overwrite writer is DESTRUCTIVE for partial ranges, so this
script never calls it. Per root x tier it: reads the existing {YYYY}.parquet,
drops any rows already carrying the target date, appends the fresh day's rows,
sorts by date, and writes atomically (tmp -> os.replace). The next evening's
refresh pass re-pulls the whole year for these roots and overwrites — the
top-up rows are superseded by identical vendor data, so the store never forks.

WRITER EXCLUSION (§B)
─────────────────────────────────────────────────────────────────────────────
Every mutating writer of the T1 store (this script's legacy/@universe/daily
modes, and `scripts/backfill_thetadata_eod.py`) acquires a non-blocking
`fcntl.flock` on `{store}/_writer.lock` before its first parquet mutation. A
refusal mutates NOTHING (not even `_manifest.json`) and is announced with a
single JSON line (`{"event": "writer_locked", ...}`). The legacy/@universe
modes keep their existing exit-1 refusal shape; `--daily` exits 0 on refusal
(F14 — repeated nonzero exits would poison `launchctl print`'s LastExitStatus
as a daily false alarm).

Exit codes:
    Legacy / @universe modes: 0 = every requested root now has rows for the
        date (or already did); 2 = vendor has no data yet for ANY root;
        1 = partial, OR blocked (backfill running / lock refused).
    --daily mode: 0 = healthy receipt, no-op gate, OR lock refusal (F14);
        1 = partial or failed receipt.

Usage:
    python -m scripts.topup_thetadata_day --roots SPY,QQQ --date 2026-07-30
    python -m scripts.topup_thetadata_day --roots SPY   # date defaults to the
                                                        # last weekday before today
    python -m scripts.topup_thetadata_day --roots @universe --date 2026-07-30
    python -m scripts.topup_thetadata_day --daily
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import math
import subprocess
import sys
import time as _time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date as _date, datetime, time as _time_of_day, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.thetadata_store import resolve_thetadata_store  # noqa: E402
from lib import nyse_calendar  # noqa: E402

log = logging.getLogger("topup_thetadata_day")

TIERS = ("eod", "oi", "greeks")

# AD1T1-FROZEN-BY-FABLE: production --workers default for `--daily`. The
# 1/2/4/6 quiet-window benchmark ladder (spec §F) is in flight; Fable sets the
# final value before the PR leaves draft review. Every call site and every
# test reads this constant — never the literal.
_DAILY_WORKERS_DEFAULT = 2

_MAX_WORKERS = 6                 # hard vendor-safety cap (§A1) — Terminal ceiling is 8
# (RF7, R3) 65 min — the plist's four fire points are >=70 min apart (§E), so
# a run holding the lock for the full deadline still releases it before the
# NEXT fire; 100 min would let one held lock swallow a whole retry-ladder rung.
_DEFAULT_DEADLINE_MIN = 65       # §F2
_GATE_TIME_ET = _time_of_day(16, 10)
_REPROBE_FETCH_FAILED_FRACTION = 0.25   # F5
_S_SUSPECT_VENDOR_EMPTY_FRACTION = 0.50  # F12
# (N1, R3 verify-pass) minimum EOD[S]-attempted-roots floor before the
# s_suspect_non_session ratio means anything: max(5, ceil(5% of the T1
# universe)). Below this, eod_s_attempted is too small a sample either way.
_S_SUSPECT_MIN_ATTEMPT_FRACTION = 0.05

WRITER_LOCK_NAME = "_writer.lock"

_PRESENT_STATES = {"already_present", "complete"}


# ── legacy helpers (§G byte-compatibility — unchanged behavior) ─────────────
def _last_weekday_before(d: _date) -> _date:
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def _backfill_running() -> bool:
    try:
        rc = subprocess.run(["pgrep", "-f", "backfill_thetadata_eod"],
                            capture_output=True, check=False)
        return rc.returncode == 0
    except OSError:
        return False


def _tmp_path(dest: Path) -> Path:
    """(F9) `{YYYY}.parquet.tmp` — deliberately does NOT end in `.parquet`, so
    store readers' `*.parquet` glob (e.g. `engine/thetadata_store.py`) never
    matches a tmp file left behind by a SIGKILL between write and replace. The
    old `{YYYY}.tmp.parquet` shape (via `Path.with_suffix`) DID match that
    glob — a killed writer could double a root's rows on the next read."""
    return dest.with_name(dest.name + ".tmp")


def _write_atomic(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(dest)
    df.to_parquet(tmp, index=False)
    tmp.replace(dest)


def _merge_day(store: Path, tier: str, root: str, day: _date,
               fresh: pd.DataFrame) -> int:
    """Merge one day's rows into {store}/{tier}/{ROOT}/{YYYY}.parquet.

    Returns the number of rows now present for `day` in that parquet.
    """
    dest = store / tier / root.upper() / f"{day.year}.parquet"
    fresh = fresh.copy()
    fresh["date"] = pd.to_datetime(fresh["date"], errors="coerce")
    day_ts = pd.Timestamp(day)
    fresh = fresh[fresh["date"] == day_ts]
    if fresh.empty:
        return 0
    if dest.exists():
        existing = pd.read_parquet(dest)
        existing["date"] = pd.to_datetime(existing["date"], errors="coerce")
        kept = existing[existing["date"] != day_ts]
        merged = pd.concat([kept, fresh], ignore_index=True)
    else:
        merged = fresh
    merged = merged.sort_values("date").reset_index(drop=True)
    _write_atomic(merged, dest)
    return int(len(fresh))


def _has_day(store: Path, tier: str, root: str, day: _date) -> bool:
    dest = store / tier / root.upper() / f"{day.year}.parquet"
    if not dest.exists():
        return False
    try:
        col = pd.read_parquet(dest, columns=["date"])
    except Exception:  # noqa: BLE001 — unreadable parquet = treat as absent
        return False
    return bool((pd.to_datetime(col["date"], errors="coerce")
                 == pd.Timestamp(day)).any())


# ── writer exclusion (§B) ────────────────────────────────────────────────────
@contextmanager
def _writer_lock(store: Path):
    """Crash-safe advisory flock guarding ALL mutating writers of the T1 store.

    `fcntl.flock(LOCK_EX | LOCK_NB)` on `{store}/_writer.lock` (local APFS —
    flock is reliable there). The lock FILE persisting is harmless: the LOCK
    dies with the file descriptor, so process death (including SIGKILL)
    releases ownership and no stale file can wedge the source. Yields True if
    acquired, False if refused."""
    store.mkdir(parents=True, exist_ok=True)
    lock_path = store / WRITER_LOCK_NAME
    fh = open(lock_path, "a+")
    acquired = False
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def _emit_writer_locked(mode: str) -> None:
    """(§B) Machine-readable single-line refusal record to stdout."""
    print(json.dumps({"event": "writer_locked", "mode": mode}), flush=True)


def _sweep_stale_tmp(store: Path) -> int:
    """(F9, extended RF9/R3) Sweep stale tmp files under the flock at
    daily-mode startup.

    Sweeps BOTH the new `{YYYY}.parquet.tmp` shape this build writes and the
    legacy `{YYYY}.tmp.parquet` shape the pre-F9 writer used (a SIGKILL under
    the old naming could still be on disk from before this deploy — and the
    old shape is the one that actually corrupts reads, since it matches the
    store readers' `*.parquet` glob). (RF9) Also sweeps STORE-ROOT `*.tmp`
    files — a SIGKILL mid `_write_daily_receipt`/`_write_manifest` leaves
    `_manifest.json.tmp` sitting at the store root, not under a tier dir."""
    count = 0
    if not store.exists():
        return 0
    for tier in TIERS:
        tier_dir = store / tier
        if not tier_dir.exists():
            continue
        for pattern in ("*/*.parquet.tmp", "*/*.tmp.parquet"):
            for p in tier_dir.glob(pattern):
                try:
                    p.unlink()
                    count += 1
                except OSError:
                    pass
    for p in store.glob("*.tmp"):
        try:
            p.unlink()
            count += 1
        except OSError:
            pass
    return count


# ── legacy / @universe bounded 3-tier one-day ensure (§G) ───────────────────
def _run_bounded(store: Path, roots: list[str], day: _date) -> int:
    """3-tier one-day ensure for `roots` on `day` (legacy contract; §G).

    Returns the legacy exit-code triple: 0 = every root now has rows for the
    date (or already did); 2 = vendor has no data yet for ANY root; 1 = partial.
    """
    from collectors import thetadata as td

    if not td.reachable():
        log.error("topup: theta terminal unreachable — nothing pulled")
        return 2

    complete = 0
    empty = 0
    for root in roots:
        if all(_has_day(store, t, root, day) for t in TIERS):
            log.info("topup: %s %s already in store (all tiers) — skipping", root, day)
            complete += 1
            continue
        try:
            pulls = {
                "eod":    td.bulk_eod(root, 0, day, day),
                "oi":     td.bulk_open_interest(root, 0, day, day),
                "greeks": td.bulk_greeks(root, 0, day, day, order=3),
            }
        except Exception as e:  # noqa: BLE001
            log.warning("topup: %s %s pull failed: %s", root, day, e)
            continue
        rows = {}
        got_all = True
        for tier in TIERS:
            df = pulls[tier]
            if df is None or df.empty:
                rows[tier] = 0
                got_all = False
                continue
            rows[tier] = _merge_day(store, tier, root, day, df)
            if rows[tier] == 0:
                got_all = False
        if sum(rows.values()) == 0:
            empty += 1
            log.info("topup: %s %s — vendor has no rows yet (eod/oi/greeks all empty)",
                     root, day)
        else:
            log.info("topup: %s %s merged rows eod=%d oi=%d greeks=%d",
                     root, day, rows["eod"], rows["oi"], rows["greeks"])
            if got_all:
                complete += 1

    log.info("topup: %s — %d/%d roots complete, %d vendor-empty",
             day, complete, len(roots), empty)
    if complete == len(roots):
        return 0
    if empty == len(roots):
        return 2
    return 1


# ── daily incremental mode (§A-§D) ───────────────────────────────────────────
@dataclass(frozen=True)
class RunContext:
    """Immutable daily-mode run context (F3) — S/D resolved EXACTLY ONCE,
    before the worker pool starts. No worker may consult the wall clock."""
    D: _date
    S: _date | None
    forced: bool


def _resolve_daily_context(now: datetime, *, forced: bool) -> RunContext | None:
    """(F4) Exact calendar/time derivation for the daily gate.

    `now` may be any aware datetime (naive is treated as UTC, matching this
    repo's other calendar helpers); it is converted to America/New_York here.
    `expected_last_session()` is FORBIDDEN on this path — its 17:00 ET settle
    buffer would return S when asked for D at the 16:15-window fire.

    Returns None for a lawful no-op (non-session day, or before 16:10 ET)
    unless `forced`. Returns a RunContext with `S=None` when the calendar
    cannot resolve the prior session (session_n_back failure) — the caller
    aborts that as a `failed` run.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_et = now.astimezone(nyse_calendar.ET)
    today_et = now_et.date()

    gate_open = (nyse_calendar.is_session(today_et)
                and now_et.time() >= _GATE_TIME_ET)
    if not gate_open and not forced:
        return None

    D = today_et if nyse_calendar.is_session(today_et) \
        else nyse_calendar.last_session_on_or_before(today_et)
    S = nyse_calendar.session_n_back(D, 1)
    return RunContext(D=D, S=S, forced=forced)


@dataclass
class RootResult:
    root: str
    state: str
    cells: dict = field(default_factory=dict)
    failure_reason: str | None = None


def _ensure_one_cell(store: Path, tier: str, root: str, day: _date,
                     fetch_fn: Callable[[], pd.DataFrame | None]) -> str:
    """Ensure one (tier, root, day) cell (§A4). Returns the cell's terminal
    state: already_present | complete | vendor_empty | fetch_failed |
    date_unresolved."""
    if _has_day(store, tier, root, day):
        return "already_present"
    df = fetch_fn()
    if df is None:
        # (F5) the collector returns None indistinguishably for timeouts,
        # stream truncation, non-200s, and parse failures — fetch_failed is
        # a deliberate superset, not a cause classification.
        return "fetch_failed"
    if df.empty:
        return "vendor_empty"
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    day_ts = pd.Timestamp(day)
    rows_returned = len(d)
    rows_for_target_date = int((d["date"] == day_ts).sum())
    if rows_for_target_date == 0:
        # (F6) rows came back, but none carry the target date after
        # normalization — distinct from vendor_empty (an EMPTY frame).
        log.warning("topup daily: %s %s %s date_unresolved "
                   "(rows_returned=%d rows_for_target_date=0)",
                   root, tier, day, rows_returned)
        return "date_unresolved"
    _merge_day(store, tier, root, day, df)
    return "complete"


def _ensure_daily_root(store: Path, root: str, S: _date, D: _date, td) -> RootResult:
    """Per-root ensure of the four §A4 cells, in the §A5 sequential order
    (eod[S] -> oi[S] -> oi[D] -> greeks[S]). (F11) ANY exception from vendor,
    parse, or parquet read/write is mapped to a root-level `failed` state —
    no exception may escape a worker into the pool."""
    cells: dict[str, str] = {}
    try:
        cells["eod_S"] = _ensure_one_cell(
            store, "eod", root, S, lambda: td.bulk_eod(root, 0, S, S))
        cells["oi_S"] = _ensure_one_cell(
            store, "oi", root, S, lambda: td.bulk_open_interest(root, 0, S, S))
        cells["oi_D"] = _ensure_one_cell(
            store, "oi", root, D, lambda: td.bulk_open_interest(root, 0, D, D))
        cells["greeks_S"] = _ensure_one_cell(
            store, "greeks", root, S, lambda: td.bulk_greeks(root, 0, S, S, order=3))
    except Exception as e:  # noqa: BLE001 — F11 catch-all
        return RootResult(root=root, state="failed", cells=cells,
                          failure_reason=type(e).__name__)
    return RootResult(root=root, state=_classify_root_state(cells), cells=cells)


def _classify_root_state(cells: dict[str, str]) -> str:
    """Aggregate a root's four §A4 cell states into ONE per-root terminal
    state (Fable ruling, 2026-08-22 — restates the ladder against three
    binding constraints):

      1. `complete`       ONLY if all four cells are present (already_present
                          or complete) AFTER this run.
      2. `already_present` ONLY if all four cells were ALREADY present before
                          this run touched the vendor (zero vendor calls for
                          this root).
      3. ANY cell-level problem (fetch_failed / date_unresolved on a needed
         cell, or the whole root vendor_empty) means the root is NOT
         `complete` — full stop, no matter how many other cells landed.

    The aggregate is the WORST outstanding cell, worst-first:

        fetch_failed > date_unresolved > vendor_empty (ALL four) > partial
        > already_present > complete

    `partial` is the residual bucket: "some cells landed, some did not" —
    e.g. 3 cells complete + 1 vendor_empty is `partial`, NEVER `complete`.
    A root with 3 complete cells + 1 fetch_failed is `fetch_failed` (worse
    than partial) — also never `complete`. Only a uniform vendor_empty
    across ALL four cells earns the dedicated `vendor_empty` label (the
    "root has no options at all" shape); a partial vendor_empty mix falls
    through to `partial` like any other incomplete mix.
    """
    values = list(cells.values())
    if any(v == "fetch_failed" for v in values):
        return "fetch_failed"
    if any(v == "date_unresolved" for v in values):
        return "date_unresolved"
    if all(v == "vendor_empty" for v in values):
        return "vendor_empty"
    if all(v in _PRESENT_STATES for v in values):
        # All four present. already_present ONLY when EVERY cell was
        # already_present (zero vendor calls); any cell that had to be
        # fetched (state == "complete") demotes the whole root to "complete".
        if all(v == "already_present" for v in values):
            return "already_present"
        return "complete"
    return "partial"


def _panel_present(cells: dict, key: str) -> bool:
    return cells.get(key) in _PRESENT_STATES


def _s_panel_ok(r: RootResult) -> bool:
    return (_panel_present(r.cells, "eod_S") and _panel_present(r.cells, "oi_S")
            and _panel_present(r.cells, "greeks_S"))


def _run_daily_pool(store: Path, t1_universe: list[str], td, *,
                    workers: int, deadline_min: float, ctx: RunContext,
                    ) -> tuple[dict[str, RootResult], bool, bool]:
    """Dispatch the worker pool over `t1_universe` (§A5, §F2, §F5).

    Returns (results, deadline_exceeded, terminal_lost_mid_run). Stops
    DISPATCHING new roots once the deadline elapses (roots already in flight
    are drained, never abandoned) and, once fetch_failed exceeds 25% of
    processed roots, re-probes `td.reachable()` exactly once — a False
    re-probe aborts the run without dispatching further work (F5).
    """
    deadline_at = _time.monotonic() + max(0.0, deadline_min) * 60
    results: dict[str, RootResult] = {}
    deadline_exceeded = False
    terminal_lost_mid_run = False
    reprobed = False
    workers = max(1, workers)
    roots_iter = iter(t1_universe)
    in_flight: dict = {}

    def _record(fut, root) -> None:
        try:
            results[root] = fut.result()
        except Exception as e:  # noqa: BLE001 — belt-and-suspenders; workers
            # already catch everything internally (F11).
            results[root] = RootResult(root=root, state="failed",
                                       failure_reason=type(e).__name__)

    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        for _ in range(workers):
            try:
                r = next(roots_iter)
            except StopIteration:
                break
            in_flight[executor.submit(_ensure_daily_root, store, r, ctx.S, ctx.D, td)] = r

        while in_flight and not terminal_lost_mid_run:
            done, _pending = wait(list(in_flight.keys()), timeout=1.0,
                                  return_when=FIRST_COMPLETED)
            if not done:
                if _time.monotonic() >= deadline_at:
                    deadline_exceeded = True
                    break
                continue
            for f in done:
                r = in_flight.pop(f)
                _record(f, r)

            fetch_failed_n = sum(1 for res in results.values()
                                 if res.state == "fetch_failed")
            if (not reprobed and results
                    and fetch_failed_n / len(results) > _REPROBE_FETCH_FAILED_FRACTION):
                reprobed = True
                if not td.reachable():
                    terminal_lost_mid_run = True
                    break

            if _time.monotonic() >= deadline_at:
                deadline_exceeded = True
                break

            while len(in_flight) < workers:
                try:
                    r = next(roots_iter)
                except StopIteration:
                    break
                in_flight[executor.submit(_ensure_daily_root, store, r, ctx.S, ctx.D, td)] = r
    finally:
        if in_flight:
            if terminal_lost_mid_run:
                # (RF12, R3) A future may have already finished in the gap
                # between the reprobe decision and this loop — gather ANY
                # already-completed result before cancelling the rest.
                # `cancel()` on an already-running/finished future is a
                # harmless no-op; discarding a landed result would make
                # completed work vanish from the receipt's counts.
                for f in list(in_flight):
                    if f.done():
                        _record(f, in_flight[f])
                    else:
                        f.cancel()
            else:
                for f in as_completed(list(in_flight)):
                    _record(f, in_flight[f])
        executor.shutdown(wait=True)

    if len(results) < len(t1_universe) and not terminal_lost_mid_run:
        deadline_exceeded = True
    return results, deadline_exceeded, terminal_lost_mid_run


def _source_coverage_gate() -> float:
    """Import, never a second literal (§D)."""
    from engine.options_intel_brief import CONFIG
    return CONFIG["SOURCE_COVERAGE_GATE"]


def _daily_universe() -> list[str]:
    from scripts.backfill_thetadata_eod import _resolve_universe
    return _resolve_universe()


def _ad_universe() -> list[str]:
    from engine.options_universe import gex_symbols
    return [s.upper() for s in gex_symbols()]


def _aggregate_daily(results: dict[str, RootResult], t1_universe: list[str],
                     ad_universe: list[str]) -> dict:
    ad_set = set(ad_universe)

    eod_S = sum(1 for r in results.values() if _panel_present(r.cells, "eod_S"))
    greeks_S = sum(1 for r in results.values() if _panel_present(r.cells, "greeks_S"))
    oi_S = sum(1 for r in results.values() if _panel_present(r.cells, "oi_S"))
    oi_D = sum(1 for r in results.values() if _panel_present(r.cells, "oi_D"))

    complete_t1_roots = sum(1 for r in results.values() if _s_panel_ok(r))
    complete_ad_roots = sum(1 for root, r in results.items()
                            if root in ad_set and _s_panel_ok(r))
    chain_next_ad_roots = sum(1 for root, r in results.items()
                              if root in ad_set and _panel_present(r.cells, "oi_D"))

    ad_universe_count = len(ad_universe)
    ad_coverage_pct = (complete_ad_roots / ad_universe_count) if ad_universe_count else 0.0

    failure_counts: dict[str, int] = {}
    failure_examples: list[dict] = []
    for root, r in results.items():
        reason = r.failure_reason
        if reason is None and r.state in ("fetch_failed", "date_unresolved", "failed"):
            reason = r.state
        if reason:
            failure_counts[reason] = failure_counts.get(reason, 0) + 1
            if len(failure_examples) < 10:
                failure_examples.append({"root": root, "reason": reason})

    # (RF8, R3) Denominator = roots with an ACTUAL EOD[S] vendor attempt this
    # run — "already_present" roots never touched the vendor and must not
    # dilute the ratio (a steady-state ladder re-fire where most roots are
    # already_present would otherwise make a real closure invisible: e.g. 2
    # already_present + 2 fresh vendor_empty used to read as 2/4=50% — not
    # over the >50% bar — instead of the true 2/2=100% among roots actually
    # asked). A cell that never even reached "eod_S" (root failed earlier)
    # is likewise not an attempt. Zero attempts => flag False (never divide
    # by zero, never guess).
    #
    # (N1, R3 verify-pass) RF8's fix over-corrected the OTHER direction: a
    # TINY attempted set makes the ratio noisy the opposite way — falsified
    # live: 19 already_present roots + 1 genuinely option-less root gives
    # eod_s_attempted=1, eod_s_vendor_empty=1, ratio=1.0 (100%), a spurious
    # flag from a SINGLE root. A minimum-attempt floor guards both directions
    # at once: below the floor, the sample is too small to say anything about
    # "is today a session" and the flag is False regardless of the ratio.
    eod_s_attempted = sum(1 for r in results.values()
                         if r.cells.get("eod_S") not in (None, "already_present"))
    eod_s_vendor_empty = sum(1 for r in results.values()
                             if r.cells.get("eod_S") == "vendor_empty")
    min_attempts_floor = max(5, math.ceil(_S_SUSPECT_MIN_ATTEMPT_FRACTION * len(t1_universe)))
    s_suspect_non_session = (eod_s_attempted >= min_attempts_floor
                             and (eod_s_vendor_empty / eod_s_attempted
                                  > _S_SUSPECT_VENDOR_EMPTY_FRACTION))

    return {
        "t1_universe_count": len(t1_universe),
        "ad_universe_count": ad_universe_count,
        "eod_S_roots": eod_S,
        "greeks_S_roots": greeks_S,
        "oi_S_roots": oi_S,
        "oi_D_roots": oi_D,
        "complete_t1_roots": complete_t1_roots,
        "complete_ad_roots": complete_ad_roots,
        "ad_coverage_pct": ad_coverage_pct,
        "chain_next_ad_roots": chain_next_ad_roots,
        "failure_counts_by_reason": failure_counts,
        "failure_examples": failure_examples,
        "s_suspect_non_session": s_suspect_non_session,
    }


def _write_daily_receipt(store: Path, receipt: dict) -> None:
    """(§D) Read-modify-write `_manifest.json`, preserving every OTHER
    top-level key (backfill's store/n_roots/per_root/updated_at, and any
    unknown key) — only `daily_refresh` is replaced. (F16) An unreadable
    manifest logs ONE warning and is treated as empty (fail-open); this
    writer never raises on a corrupt read."""
    p = store / "_manifest.json"
    preserved: dict = {}
    if p.exists():
        try:
            preserved = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001 — F16 fail-open
            log.warning("topup daily: unreadable manifest %s (%s: %s) — "
                       "regenerating fresh, preserving nothing", p,
                       type(e).__name__, e)
            preserved = {}
    doc = dict(preserved)
    doc["daily_refresh"] = receipt
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str, sort_keys=True))
    tmp.replace(p)


def _daily_main(*, workers: int, deadline_min: float, forced: bool,
                now_fn: Callable[[], datetime] | None = None) -> int:
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    started_at = datetime.now(timezone.utc)

    ctx = _resolve_daily_context(now_fn(), forced=forced)
    if ctx is None:
        log.info("topup daily: gate closed (non-session day or before 16:10 ET) "
                 "— clean no-op, no receipt")
        return 0

    try:
        store = Path(resolve_thetadata_store(
            required=True, purpose="daily incremental T1 maintainer"))
    except Exception as e:  # noqa: BLE001
        log.error("topup daily: no thetadata store: %s", e)
        return 1

    # (HARDENING, R3) A `with` statement would let an OSError from opening
    # the lock file (read-only store, ENOSPC) propagate as a bare traceback.
    # Acquire manually so that failure mode is a clean logged `failed`
    # outcome instead — the flock-refused (acquired=False) path is untouched.
    lock_cm = _writer_lock(store)
    try:
        acquired = lock_cm.__enter__()
    except OSError as e:
        log.error("topup daily: cannot open writer lock at %s (%s: %s) — "
                 "store may be read-only or full — aborting as failed, no receipt",
                 store / WRITER_LOCK_NAME, type(e).__name__, e)
        return 1

    try:
        if not acquired:
            _emit_writer_locked("daily")
            log.warning("topup daily: writer lock held by another process — "
                       "refusing (no mutation, no receipt)")
            return 0   # F14

        def _finish(status: str, **extra) -> dict:
            finished_at = datetime.now(timezone.utc)
            receipt = {
                "source": "thetadata",
                "mode": "incremental_daily",
                "S": ctx.S.isoformat() if ctx.S else None,
                "D": ctx.D.isoformat(),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "elapsed_sec": (finished_at - started_at).total_seconds(),
                "worker_count": workers,
                "status": status,
                "forced": forced,
                "t1_universe_count": None,
                "ad_universe_count": None,
                "eod_S_roots": None,
                "greeks_S_roots": None,
                "oi_S_roots": None,
                "oi_D_roots": None,
                "complete_t1_roots": None,
                "complete_ad_roots": None,
                "ad_coverage_pct": None,
                "chain_next_ad_roots": None,
                "deadline_exceeded": False,
                "stale_tmp_swept": 0,
                "s_suspect_non_session": False,
                "failure_counts_by_reason": {},
                "failure_examples": [],
                "terminal_health": None,
            }
            receipt.update(extra)
            _write_daily_receipt(store, receipt)
            return receipt

        if ctx.S is None:
            _finish("failed",
                   failure_counts_by_reason={"session_resolution_failed": 1},
                   failure_examples=[{"root": None,
                                     "reason": "session_resolution_failed"}])
            log.error("topup daily: session_n_back(%s, 1) returned None — aborting", ctx.D)
            return 1

        stale_tmp_swept = _sweep_stale_tmp(store)

        # (F7/RF5) pgrep breadcrumb — ADVISORY ONLY in --daily. The flock is
        # the sole refusal authority here; this never blocks, it only leaves
        # an operator-visible trail (an orphaned backfill child, or a
        # concurrent manual run, can leave a false-positive pgrep hit for as
        # long as the orphan lives — a refusal on that basis would be wrong).
        if _backfill_running():
            log.warning("topup daily: backfill_thetadata_eod appears to be "
                       "running (pgrep advisory only in --daily — continuing; "
                       "the flock already granted exclusive access)")

        from collectors import thetadata as td
        if not td.reachable():
            _finish("failed", terminal_health="unreachable",
                   stale_tmp_swept=stale_tmp_swept)
            log.error("topup daily: theta terminal unreachable — aborting before pulls")
            return 1

        try:
            t1_universe = _daily_universe()
            ad_universe = _ad_universe()
        except Exception as e:  # noqa: BLE001
            _finish("failed", terminal_health="reachable",
                   stale_tmp_swept=stale_tmp_swept,
                   failure_counts_by_reason={type(e).__name__: 1})
            log.error("topup daily: universe resolution failed: %s", e)
            return 1

        results, deadline_exceeded, terminal_lost = _run_daily_pool(
            store, t1_universe, td, workers=workers,
            deadline_min=deadline_min, ctx=ctx)

        agg = _aggregate_daily(results, t1_universe, ad_universe)

        if terminal_lost:
            _finish("failed", terminal_health="lost_mid_run",
                   stale_tmp_swept=stale_tmp_swept,
                   deadline_exceeded=deadline_exceeded, **agg)
            log.error("topup daily: fetch_failed > 25%% of attempted roots and "
                     "the re-probe found the terminal unreachable — aborting "
                     "as failed (terminal_lost_mid_run)")
            return 1

        gate = _source_coverage_gate()
        healthy = agg["ad_coverage_pct"] >= gate
        # (RF2, R3) deadline_exceeded FORCES partial — a run that ran out of
        # wall-clock time is by definition unfinished, no matter how much
        # coverage the roots it DID reach happened to hit. Never let a
        # high-coverage partial pool read as `healthy`.
        status = "partial" if deadline_exceeded else ("healthy" if healthy else "partial")
        _finish(status, terminal_health="reachable",
               stale_tmp_swept=stale_tmp_swept,
               deadline_exceeded=deadline_exceeded, **agg)
        log.info("topup daily: S=%s D=%s ad_coverage=%.1f%% status=%s "
                "deadline_exceeded=%s", ctx.S, ctx.D,
                agg["ad_coverage_pct"] * 100, status, deadline_exceeded)
        return 0 if status == "healthy" else 1
    finally:
        lock_cm.__exit__(None, None, None)


# ── CLI ───────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="ThetaData T1 store top-up + daily incremental maintainer.")
    ap.add_argument("--roots", default=None,
                    help="comma-separated roots, or '@universe' for the "
                         "resolved T1 universe (explicit catch-up, F10)")
    ap.add_argument("--date", default=None,
                    help="session date YYYY-MM-DD (default: last weekday before today)")
    ap.add_argument("--daily", action="store_true",
                    help="market-wide incremental daily mode (mutually "
                         "exclusive with --roots/--date)")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"--daily worker pool size (default {_DAILY_WORKERS_DEFAULT}; "
                         f"hard cap {_MAX_WORKERS})")
    ap.add_argument("--deadline-min", type=float, default=_DEFAULT_DEADLINE_MIN,
                    help="--daily hard wall-clock deadline in minutes (F2)")
    ap.add_argument("--force-run", action="store_true",
                    help="--daily: bypass the session/time gate for diagnostics "
                         "ONLY; stamps forced=true in the receipt")
    return ap


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.daily and (args.roots is not None or args.date is not None):
        ap.error("--daily is mutually exclusive with --roots/--date")
    if not args.daily and args.roots is None:
        ap.error("--roots is required unless --daily is given")
    if args.workers is not None and args.workers > _MAX_WORKERS:
        ap.error(f"--workers must be <= {_MAX_WORKERS} (hard vendor-safety cap)")

    if args.daily:
        workers = args.workers if args.workers is not None else _DAILY_WORKERS_DEFAULT
        return _daily_main(workers=workers, deadline_min=args.deadline_min,
                           forced=args.force_run)

    # ---- legacy / @universe bounded mode ----
    try:
        store = Path(resolve_thetadata_store(required=True, purpose="pre-open day top-up"))
    except Exception as e:  # noqa: BLE001
        log.error("topup: no thetadata store: %s", e)
        return 1

    if args.roots.strip() == "@universe":
        from scripts.backfill_thetadata_eod import _resolve_universe
        roots = _resolve_universe()
        log.info("topup: @universe resolved to %d roots", len(roots))
    else:
        roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]

    day = (_date.fromisoformat(args.date) if args.date
           else _last_weekday_before(_date.today()))

    if _backfill_running():
        log.warning("topup: backfill_thetadata_eod is running — skipping merge "
                    "entirely (never race the year-overwrite writer)")
        return 1

    try:
        with _writer_lock(store) as acquired:
            if not acquired:
                _emit_writer_locked("legacy")
                log.warning("topup: writer lock held by another process — refusing")
                return 1
            return _run_bounded(store, roots, day)
    except OSError as e:
        # (HARDENING, R3) — read-only store / ENOSPC opening the lock file:
        # a clean logged failure, never a bare traceback.
        log.error("topup: cannot open writer lock at %s (%s: %s) — store may be "
                 "read-only or full", store / WRITER_LOCK_NAME, type(e).__name__, e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
