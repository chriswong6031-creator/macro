#!/usr/bin/env python3
"""scripts/build_options_intel_brief.py — AD-1 Daily EOD Options Intelligence Brief producer.

Repository adapter for ``engine/options_intel_brief.py`` (the pure scoring engine).
Contract: ``contracts/options/OPTIONS_INTEL_BRIEF_V1.md``. This script owns 100% of the
file I/O (reads §2 inputs through their existing loaders/paths, never re-ingests, never
calls a collector), then hands fully materialised in-memory frames/dicts to the engine
and writes its returned payload to ``site/options_intel_brief.json``. Zero network calls.

AD-1T0 SOURCE CUTOVER (2026-08-22, ``DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA``,
frozen spec ``research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md``): this producer no
longer reads the legacy ``data/polygon_gex/`` estate. It reads the canonical ThetaData
T1 store (``engine.thetadata_store.resolve_thetadata_store()``) directly, building its
own per-contract frames with narrow projected ``pd.read_parquet`` reads — the whole-store
convenience helpers ``engine.thetadata_store.chain()``/``make_chain_provider()`` are
PROHIBITED on this path (string ``expiry``, no ``strike_ticker``, and a forbidden
volume-weighted-strike spot fallback; spec §A). ``engine/options_intel_brief.py`` and
``engine/thetadata_store.py`` are BYTE-UNCHANGED by this wave. GEX mechanics
(``site/gex/*.json`` via ``engine.gex_confirm``) are HARD-DISABLED for the cutover (spec
§E) — legacy-Polygon-estate provenance, never read here again; ``M_gex`` reads 1.0
unconditionally until a future ThetaData-native mechanics wave.

NYSE-session arithmetic is the repository's canonical calendar module,
``lib/nyse_calendar.py`` — R1 of ``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION
_BY_FABLE.md`` ("pure rule arithmetic, zero data dependencies"; already the reference
every other nightly builder anchors sessions against, e.g. ``engine/session_anchor.py``).
This is the ONE canonical trading-calendar helper in the repo (grepped: no other module
defines a competing ``next_nyse_session``); we reuse ``session_n_forward(d, 1)`` for
"the next NYSE session" and ``sessions_apart`` for session-count arithmetic. No new
calendar is minted here (contract §1).

Atomic-write idiom mirrors the house pattern already used by
``scripts/reconcile_entry_radar.py::write_json_atomic`` (temp file in the same
directory, fsync, ``os.replace`` — a reader never observes a torn file), with the
contract's semantic no-op rule layered on top (§7): a rerun producing an identical
``receipt_id`` AND identical payload (module ``built_at_utc`` and the diagnostic-only
``_run`` block) leaves the committed bytes untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import math
import os
import sys
import tempfile
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from lib import nyse_calendar as nc  # noqa: E402
from engine import options_intel_brief as brief  # noqa: E402
from engine import options_universe  # noqa: E402 — B2: the canonical current universe
from engine import price_ladder  # noqa: E402 — §D rung 2 (adjusted-first close ladder)
from engine.thetadata_store import resolve_thetadata_store  # noqa: E402 — WP-RESOLVER, the ONLY store resolution

EARNINGS_PATH = _REPO_ROOT / "data" / "earnings" / "earnings.parquet"
PROPHET_INDEX_PATH = _REPO_ROOT / "site" / "prophet" / "index.json"
SIGNING_GATE_PATH = _REPO_ROOT / "data" / "options_flow" / "signing_gate.json"
OUT_PATH = _REPO_ROOT / "site" / "options_intel_brief.json"

_ET = ZoneInfo("America/New_York")
_CLOSE_PLUS_SETTLE_ET = dt_time(17, 0)   # matches lib.nyse_calendar's own settle buffer
_STALE_AFTER_HOURS = 36                  # contract §4 input #1 "absent >36h after close"

# ─────────────────────────────────────────────────────────────────────────────
# §C depth bound — K = max(largest CONFIG history window constant, legacy 28) + 1.
# Cited CONFIG window constants (frozen, verbatim, never altered by this wave):
#   LOOKBACK (20)           — vol-tier window + V-family spread window; LOOKBACK+1
#                             is also the summary-spot history window (§D).
#   D1_PERSIST_WINDOW (10)  — salience persistence lookback (d3).
#   DOI_TARGET_WINDOW (60)  — the named/frozen ΔOI target window (reserved; not
#                             currently read by any engine function, honoured here
#                             defensively since it is the largest named window).
# 28 is the legacy small-store depth the pre-cutover producer always had available
# (the whole committed Polygon store). Never load the ThetaData store's full
# multi-year history into the nightly (spec §C, §H).
# ─────────────────────────────────────────────────────────────────────────────
_HISTORY_WINDOW_CONSTANTS = (
    brief.CONFIG["LOOKBACK"], brief.CONFIG["D1_PERSIST_WINDOW"], brief.CONFIG["DOI_TARGET_WINDOW"],
)
_LEGACY_MIN_DEPTH = 28
K_SESSIONS = max(max(_HISTORY_WINDOW_CONSTANTS), _LEGACY_MIN_DEPTH) + 1
assert K_SESSIONS >= brief.CONFIG["LOOKBACK"] + 1, "K must cover LOOKBACK+1 (spot history, §D)"

# Buffer beyond K when scanning the calendar for full(s)/X candidates: covers the
# OI-only frontier X (one session past max(F)) plus ordinary weekend/holiday gaps
# and the occasional single-tier interior hole (§C — holes are excluded from both
# roles, so a handful of gaps inside the window must not starve the trailing-K cut).
_CANDIDATE_BUFFER = 15

_IDENT_COLS = ["root", "expiration", "strike", "right"]
_EOD_COLS = ["root", "expiration", "strike", "right", "date", "volume"]
_OI_COLS = ["root", "expiration", "strike", "right", "date", "open_interest"]
_GREEKS_COLS = ["root", "expiration", "strike", "right", "date", "implied_vol", "delta", "underlying_price"]

_DIGEST_COLS = {
    "eod": _EOD_COLS,
    "oi": _OI_COLS,
    "greeks": _GREEKS_COLS,
}

_STRIKE_TOL = 1e-6

# N3 (verify round BLOCKER, spec §A #7 as amended 2026-08-22): per-CONTRACT
# OI-baseline coverage floor -- replaces the earlier root-PRESENCE guard, which
# missed the per-contract-absence pathology (a root with exactly one surviving
# oi row read as "present" and therefore fully covered). Floor basis (live
# census): organic in-window per-root match rates min 0.825 / p5 0.939 /
# median 0.982 over 144 root-sessions, comfortably above 0.60; the pathology
# class (systemic missing print scored as zero baselines) sits far below it.
_OI_COVERAGE_FLOOR = 0.60

# N4 (verify round correction, spec §C as amended 2026-08-22): §C role-split
# floors. `_OI_MEMBERSHIP_FLOOR`/`_EOD_PATHOLOGY_FLOOR` gate `plaus(s)` (HISTORY
# membership, graded partials admitted); `_S_ROLE_BALANCE_FLOOR` gates ONLY
# whichever session wants the S role (demotion loop) and the X admission check.
_OI_MEMBERSHIP_FLOOR = 0.90    # plaus(s): n_oi(s) >= floor * n_eod(s)
_EOD_PATHOLOGY_FLOOR = 0.25    # plaus(s): n_eod(s) >= floor * n_oi(s) (blocks 3-vs-400 thinness)
_S_ROLE_BALANCE_FLOOR = 0.90   # S-role balance + X admission (unchanged 0.90 store-relative floor)


# ─────────────────────────────────────────────────────────────────────────────
# Store resolution (§G off-host self-skip).
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_store_with_diagnostics(*, purpose: str) -> Path | None:
    """Wrap ``resolve_thetadata_store(required=False)`` and, when nothing resolves,
    surface the resolver's OWN diagnostic (which already names every candidate path
    tried) as a GH-annotation-safe bare print (contract-neutral CI law: annotations
    must start the line, never go through a logger). Captured via a temporary
    handler on the resolver's logger rather than duplicating its private candidate
    list — ``engine/thetadata_store.py`` is byte-unchanged by this wave."""
    logger = logging.getLogger("engine.thetadata_store")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)
    try:
        store = resolve_thetadata_store(required=False, purpose=purpose)
    finally:
        logger.removeHandler(handler)
    if store is None:
        msg = buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else (
            "no ThetaData store candidate resolved (env THETADATA_STORE / "
            "lib.config data_dir()/thetadata_eod / ops-host worktree store)"
        )
        print(f"::warning title=options-intel-brief-store::{msg}", flush=True)
    return store


def _store_source_label(resolved: Path) -> str:
    """Best-effort provenance label for the ``store_resolution`` receipt (spec §F).
    A pure DESCRIPTION of which candidate matched — never re-implements the
    resolver's own precedence/fallback decision, which stays exclusively in
    ``engine.thetadata_store.resolve_thetadata_store``."""
    env = os.environ.get("THETADATA_STORE")
    if env and Path(env) == resolved:
        return "env"
    try:
        from lib import config  # noqa: PLC0415
        if (config.data_dir() / "thetadata_eod") == resolved:
            return "data_dir"
    except Exception:  # noqa: BLE001
        pass
    if str(resolved).rstrip("/").endswith("theta-ops-wt/data/thetadata_eod"):
        return "ops-wt"
    return "resolved"


# ─────────────────────────────────────────────────────────────────────────────
# §A — contract-identity serialization law.
# ─────────────────────────────────────────────────────────────────────────────


def _strike_ticker_and_ok(root: pd.Series, expiration: pd.Series, right: pd.Series,
                           strike: pd.Series) -> tuple[pd.Series, pd.Series]:
    """``strike_ticker = "O:" + ROOT + YYMMDD(expiration) + (C|P) + zfill8(round(strike*1000))``
    (spec §A, ROOT embedded VERBATIM — never a normalised/base symbol).

    A row failing the integrality assertion (``abs(strike*1000 - round(strike*1000))
    >= 1e-6``) or the 8-digit width assertion (``0 <= round(strike*1000) <=
    99_999_999``) gets a DELIBERATELY malformed strike field (the raw un-rounded
    ``repr`` of ``strike*1000``, which always embeds a ``.`` or an out-of-width digit
    run) instead of a rounded value — a rounded collision would manufacture a false
    ΔOI merge partner (§A bullet 2). The malformed ticker fails the engine's own
    ``_STANDARD_TICKER_RE`` (``^O:([A-Za-z.]+)(\\d{6})[CP]\\d{8}$``) and is therefore
    routed through ``contract_identity_split`` to the SAME adjusted/nonstandard
    exclusion path a genuinely adjusted OCC ticker takes — byte-identical to the
    engine's legacy exclusion semantics (§A bullet 4), with zero new adapter-side
    regex of our own. A nonstandard (digit-suffixed) ROOT needs no special handling
    here either: embedded verbatim, it already fails that same engine regex's
    letters-only root group.

    m1/m2 (review round, 2026-08-22): a non-finite strike (``NaN``, ``+-inf``) or a
    non-positive one (``<= 0``) is ALSO routed to the malformed-field exclusion path
    — never a crash on the ``.astype("int64")`` cast (a non-finite value raised
    there pre-fix) and never a lawful-looking ``00000000``/collision-prone ticker
    for a genuine zero/negative strike.

    M3 (MAJOR, review round): ``right`` outside ``{C, P}`` after upper-casing —
    any other string, or a genuine ``NaN``/``None`` — is embedded as the sentinel
    ``"X"`` rather than coerced to ``"P"``. ``"X"`` is not a member of the engine's
    ``[CP]`` character class, so the ticker fails ``_STANDARD_TICKER_RE`` and is
    routed through the SAME exclusion path — never a forged, lawful-looking put
    ticker that could collide with a real put and zero out Q_oi through the frozen
    merge (spec §A bullet 6).

    Returns ``(strike_ticker, integrality_and_width_ok)`` — the second element is a
    diagnostic only (tests inspect it directly; ``right`` validity is NOT folded
    into it — an invalid ``right`` is excluded purely via the ticker's own failure
    of the engine's regex, so this remains "integrality+width only" as before);
    the actual exclusion is always performed by the frozen engine regex on the
    returned ticker string.
    """
    idx = root.index
    strike_num = pd.to_numeric(strike, errors="coerce")
    strike_f64 = strike_num.astype("float64")
    finite = pd.Series(np.isfinite(strike_f64.to_numpy()), index=idx)
    positive = (strike_f64 > 0).fillna(False)
    raw = strike_f64 * 1000.0
    # m1 (review round): substitute a finite 0.0 for any non-finite `raw` BEFORE
    # rounding/casting -- purely to keep the `.astype("int64")` cast alive (a
    # non-finite value raised IntCastingNaNError/ValueError there pre-fix).
    # `width_ok` below is already unconditionally False for these rows via
    # `finite & positive &`, so the substituted value never reaches a ticker.
    raw_safe = raw.where(finite, 0.0)
    rounded = raw_safe.round()
    integral_ok = finite & positive & ((raw_safe - rounded).abs() < _STRIKE_TOL)
    width_ok = integral_ok & (rounded >= 0) & (rounded <= 99_999_999)
    strike_int = rounded.fillna(0).astype("int64")
    good_field = strike_int.astype(str).str.zfill(8)
    # PERF NIT (verify round): the malformed-field build below (`raw.map(str)`)
    # is a Python-level per-element call -- materialise it ONLY when at least
    # one row actually needs it. The common/hot case (every strike lawful,
    # `width_ok.all()`) short-circuits straight to `good_field`, identical
    # exclusion behavior (nothing downstream ever reads `bad_field` when no row
    # is masked out by `.where`).
    if bool(width_ok.all()):
        strike_field = good_field
    else:
        # `.map(str)` (never `.astype(str)`) — pandas' modern string dtype makes
        # `.astype(str)` PRESERVE a non-finite float as a real null instead of
        # stringifying it (verified: pandas 3.0 turns NaN/inf into a missing value
        # under `.astype(str)`, not the text "nan"/"inf"), which would silently
        # smuggle an actual null into the "malformed ticker" field instead of the
        # deliberately-malformed STRING the exclusion path depends on. `.map(str)`
        # calls Python's own `str()` per element, always returning real text.
        bad_field = "BAD" + raw.map(str)
        strike_field = good_field.where(width_ok, bad_field)

    exp_dt = pd.to_datetime(expiration, errors="coerce")
    yymmdd = exp_dt.dt.strftime("%y%m%d")
    yymmdd = yymmdd.where(exp_dt.notna(), "BADDATE")

    right_is_na = right.isna() if hasattr(right, "isna") else pd.Series([False] * len(right), index=idx)
    right_upper = right.astype(str).str.upper()
    right_ok = (~right_is_na) & right_upper.isin(["C", "P"])
    cp = right_upper.where(right_ok, "X")

    ticker = "O:" + root.astype(str) + yymmdd + cp + strike_field
    return ticker, width_ok.fillna(False)


# ─────────────────────────────────────────────────────────────────────────────
# ThetaData store reads — narrow projected reads only (§A: chain()/make_chain_
# provider() are PROHIBITED on this path).
# ─────────────────────────────────────────────────────────────────────────────


def _warn_corrupt_file(tier: str, path: Path, exc: Exception,
                        corrupt_counter: dict[str, int] | None) -> None:
    """N5 (verify round, MINOR): the ONE shared corrupt/unreadable-year-file
    warning + counter increment — both ``_latest_known_date`` and
    ``_read_universe_tier_range`` route through this single form so a corrupt
    file always yields a consistent ``::warning`` wording AND a counted
    ``store_resolution.corrupt_files`` entry (pre-fix, ``_latest_known_date``'s
    own corrupt-read encounters were silently swallowed — invisible in receipt
    state — while ``_read_universe_tier_range``'s were counted; two different
    message texts for the SAME condition). Bare line-start ``print`` per the
    repo's CI-annotation law (never through a logger; ``flush=True`` since
    stdout is block-buffered when piped in CI)."""
    print(f"::warning title=options-intel-brief-corrupt-file::corrupt/unreadable "
          f"{tier} file {path}: {exc}", flush=True)
    if corrupt_counter is not None:
        corrupt_counter[tier] = corrupt_counter.get(tier, 0) + 1


def _latest_known_date(store: Path, universe_roots: Sequence[str],
                        corrupt_counter: dict[str, int] | None = None) -> str | None:
    """Cheap ceiling scan: for each universe root's EOD tier, the newest calendar
    year file present, then that file's own max ``date`` value (a single-column
    projected read — a few KB regardless of the file's row count). This — NEVER
    wall-clock ``now`` — anchors the trailing-K committed-session CANDIDATE window
    (§C) ONLY. It is NOT the staleness anchor (m9, review round, 2026-08-22): the
    staleness check is evaluated separately against ``max(committed_sessions)``
    EXACTLY (§C/§F — BLOCKER B3 caught this function's own newest-EOD-date
    previously double-cast as the staleness anchor too, which drifted on a Monday
    build — eod through Friday, oi through Monday — to a 77h-stale false
    ``STALE_SOURCE`` with zero cards every Monday).

    N5 (verify round): ``corrupt_counter`` (when supplied) is incremented via
    the SAME ``_warn_corrupt_file`` helper ``_read_universe_tier_range`` uses,
    so one corrupt file yields one consistent count everywhere, never a
    silently-dropped encounter here alone."""
    best: str | None = None
    for root in universe_roots:
        root_dir = store / "eod" / str(root).upper()
        if not root_dir.is_dir():
            continue
        years = sorted((int(p.stem) for p in root_dir.glob("*.parquet") if p.stem.isdigit()), reverse=True)
        for year in years:
            path = root_dir / f"{year}.parquet"
            try:
                col = pd.read_parquet(path, columns=["date"])["date"]
            except Exception as exc:  # noqa: BLE001 — fall back to an OLDER year for this root
                _warn_corrupt_file("eod", path, exc, corrupt_counter)
                continue
            if col.empty:
                continue
            d = str(pd.to_datetime(col).max().date())
            if best is None or d > best:
                best = d
            break  # this root's newest readable date found; move to the next root
    return best


def _candidate_window(anchor: date, k: int) -> tuple[list[str], str]:
    """Ascending ISO session strings for the trailing ``(k + buffer)`` NYSE sessions
    ending at (or before) ``anchor``, plus a query-range END extended one more NYSE
    session (covers the OI-only frontier X, which can print exactly one session past
    the newest ``full(s)`` member — §C)."""
    last = nc.last_session_on_or_before(anchor)
    n = k + _CANDIDATE_BUFFER - 1
    start = nc.session_n_back(last, n) or last
    candidate = [d.isoformat() for d in nc.sessions_between(start, last)]
    ext = nc.session_n_forward(last, 1)
    query_end = ext.isoformat() if ext is not None else candidate[-1]
    return candidate, query_end


def _read_universe_tier_range(store: Path, tier: str, roots: Sequence[str], *,
                               start: str, end: str, columns: Sequence[str],
                               corrupt_counter: dict[str, int] | None = None) -> pd.DataFrame:
    """One projected ``pd.read_parquet`` per (root, year) spanned by ``[start, end]``,
    predicate-pushed on ``date`` (mirrors the house range-read idiom already used by
    ``engine.thetadata_store.eod_volume_history_before``/``eod_sessions_before`` —
    never the whole-store ``chain()``/``make_chain_provider()`` convenience helpers,
    which are prohibited on this path per spec §A). ``root``/``right`` are normalised
    to upper-case and ``date`` to a canonical ISO string so eod/oi/greeks merge
    cleanly on identity regardless of on-disk casing."""
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    frames: list[pd.DataFrame] = []
    for root in roots:
        root_u = str(root).upper()
        root_dir = store / tier / root_u
        if not root_dir.is_dir():
            continue
        for year in range(start_ts.year, end_ts.year + 1):
            path = root_dir / f"{year}.parquet"
            if not path.is_file():
                continue
            try:
                frame = pd.read_parquet(
                    path, columns=list(columns),
                    filters=[("date", ">=", start_ts), ("date", "<=", end_ts)],
                )
            except Exception:  # noqa: BLE001
                try:
                    frame = pd.read_parquet(path, columns=list(columns))
                except Exception as exc:  # noqa: BLE001
                    # m6 (review round): a corrupt/unreadable year parquet must be
                    # VISIBLE -- a line-start ::warning plus a receipt-bound count
                    # (store_resolution.corrupt_files) -- never only a debug log,
                    # while still degrading gracefully (this root/year's slice is
                    # simply skipped, never a crash). N5 (verify round): routed
                    # through the SAME `_warn_corrupt_file` helper `_latest_known_
                    # date` now also uses -- one consistent message + count.
                    _warn_corrupt_file(tier, path, exc, corrupt_counter)
                    continue
                d = pd.to_datetime(frame["date"], errors="coerce")
                frame = frame[(d >= start_ts) & (d <= end_ts)]
            if frame.empty:
                continue
            frame = frame.copy()
            frame["root"] = root_u
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=list(columns))
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date.astype(str)
    if "right" in out.columns:
        out["right"] = out["right"].astype(str).str.upper()
    if "expiration" in out.columns:
        out["expiration"] = pd.to_datetime(out["expiration"], errors="coerce").dt.normalize()
    return out


def _select_committed_sessions(candidate: list[str], n_eod: pd.Series,
                                n_oi: pd.Series) -> tuple[list[str], list[str], dict[str, Any]]:
    """§C role-split predicate (N4 correction, verify round 2026-08-22 — REPLACES
    the earlier SYMMETRIC 0.90 ``full()`` floor, a regression: it converted an
    eod-trails-oi store (>10% divergence) into a total MIXED_VINTAGE blackout
    (present=0, cov=None) whenever the imbalance broke calendar-adjacency across
    most of history, where graded INSUFFICIENT_COVERAGE is the honest state).

    Roles are split:

      plaus(s) := is_nyse_session(s) AND n_eod(s) > 0
                  AND n_oi(s) >= 0.90 * n_eod(s)   -- OI baseline coverage vs
                                                       s's own eod population
                  AND n_eod(s) >= 0.25 * n_oi(s)   -- pathology floor only
                                                       (blocks 3-vs-400 thinness)
      F        = ascending [s : plaus(s)]           -- HISTORY membership;
                                                       graded partials admitted

    The STRICT (near-)symmetric 0.90 balance is required only of whichever
    session wants the S role: while F is non-empty and
    ``n_eod(max F) < 0.90 * n_oi(max F)``, that session is demoted out of F —
    it stays D/X-eligible, never S, and can never flip ``as_of_session``. X is
    the single NYSE session after the final (post-demotion) ``max(F)``,
    admitted iff ``n_oi(X) >= 0.90 * n_eod(max F)`` — a demoted session is
    naturally the X candidate when it is exactly that next session (the
    ordinary mid-capture-partial-latest-session shape). X's own admission
    floor stays the ASYMMETRIC store-relative check spec §C already specifies —
    X is OI-only by construction, so there is no ``n_eod(X)`` to be symmetric
    against.

    Returns ``(committed_sessions, F, decision_info)`` — ``committed_sessions =
    sorted(F ∪ {X if admitted})`` feeds the frozen ``select_settled_pair``; ``F``
    alone bounds what actually gets materialised (§C depth bound — X is OI-only
    and never gets a full chain frame). ``decision_info`` (N2, spec §F) is
    ``{"candidate_decisions": [(s, plaus_bool, balanced_bool), ...]`` for EVERY
    candidate in order, plus ``"counts": {session: (n_eod, n_oi)}`` for ONLY the
    decision-critical sessions — the final ``max(F)``, every demoted session,
    and the X candidate (admitted or not)."""
    def plaus(s: str) -> bool:
        ne = int(n_eod.get(s, 0))
        no = int(n_oi.get(s, 0))
        return (nc.is_session(date.fromisoformat(s)) and ne > 0
                and no >= _OI_MEMBERSHIP_FLOOR * ne
                and ne >= _EOD_PATHOLOGY_FLOOR * no)

    def balanced(s: str) -> bool:
        ne = int(n_eod.get(s, 0))
        no = int(n_oi.get(s, 0))
        return ne >= _S_ROLE_BALANCE_FLOOR * no

    plaus_map = {s: plaus(s) for s in candidate}
    balanced_map = {s: balanced(s) for s in candidate}

    F = [s for s in candidate if plaus_map[s]]
    demoted: list[str] = []
    while F:
        s_max = max(F)
        if balanced_map[s_max]:
            break
        F.remove(s_max)
        demoted.append(s_max)

    committed = set(F)
    counts: dict[str, tuple[int, int]] = {}
    if F:
        s_max = max(F)
        counts[s_max] = (int(n_eod.get(s_max, 0)), int(n_oi.get(s_max, 0)))
    for s in demoted:
        counts[s] = (int(n_eod.get(s, 0)), int(n_oi.get(s, 0)))

    if F:
        s_max = max(F)
        x_date = nc.session_n_forward(date.fromisoformat(s_max), 1)
        if x_date is not None:
            x = x_date.isoformat()
            ne_base = int(n_eod.get(s_max, 0))
            no_x = int(n_oi.get(x, 0))
            counts[x] = (int(n_eod.get(x, 0)), no_x)
            if ne_base > 0 and no_x >= _S_ROLE_BALANCE_FLOOR * ne_base:
                committed.add(x)

    decision_info = {
        "candidate_decisions": [(s, bool(plaus_map[s]), bool(balanced_map[s])) for s in candidate],
        "counts": counts,
    }
    return sorted(committed), F, decision_info


def _lawful_pairs(sessions: list[str]) -> dict[str, str]:
    sset = set(sessions)
    out = {}
    for a in sessions:
        b = nc.session_n_forward(date.fromisoformat(a), 1)
        if b is not None and b.isoformat() in sset:
            out[a] = b.isoformat()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §D spot ladder.
# ─────────────────────────────────────────────────────────────────────────────


def _rung2_spot(root: str, session: str) -> tuple[float, str | None, str] | None:
    """Returns ``(value, price_source, last_index_date)`` on acceptance, else
    ``None``. B2 (BLOCKER, review round): the caller must bind ALL THREE of these
    into the rung-2 receipt, not just the fact that rung 2 fired — a rung-2 close
    change must move ``receipt_id`` even though the acceptance conditions (below)
    are unchanged."""
    r = price_ladder.resolve_close(root, asof=session)
    if not r.ok or r.adjusted is not True:
        return None
    last_date = str(r.series.index.max().date())
    if last_date != session:
        return None
    val = float(r.series.iloc[-1])
    if not (math.isfinite(val) and val > 0):
        return None
    return val, getattr(r, "price_source", None), last_date


def _resolve_root_spot(root: str, session: str, rung1_val: float | None, *,
                        rung2_detail: dict[str, dict[str, Any]] | None = None) -> tuple[float | None, int]:
    """§D frozen ladder: rung1 (ThetaData greeks median) -> rung2 (adjusted-first
    price ladder, exact-date-match only) -> rung3 absent. The volume-weighted-strike
    proxy is FORBIDDEN in any score-affecting position (never implemented here).

    ``rung2_detail`` (B2, review round) — when supplied, a rung-2 acceptance
    records ``{"value", "price_source", "last_index_date"}`` for ``root`` so the
    caller can bind the actually-consumed close (not a constant descriptor) into
    the ``gex_summary`` receipt (spec §F)."""
    if rung1_val is not None and math.isfinite(rung1_val) and rung1_val > 0:
        return float(rung1_val), 1
    v2 = _rung2_spot(root, session)
    if v2 is not None:
        val, price_source, last_date = v2
        if rung2_detail is not None:
            rung2_detail[root] = {"value": val, "price_source": price_source, "last_index_date": last_date}
        return val, 2
    return None, 3


# ─────────────────────────────────────────────────────────────────────────────
# Per-session frame assembly (§A identity + §B PIT mapping).
# ─────────────────────────────────────────────────────────────────────────────

_CHAIN_COLUMNS = ["underlying", "strike_ticker", "expiry", "K", "T", "iv", "delta",
                   "is_call", "oi", "volume", "spot"]
_CHAIN_NEXT_COLUMNS = ["underlying", "strike_ticker", "expiry", "is_call", "oi"]


def _dedupe_full_row(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    return df.drop_duplicates()


def _find_conflicting_roots(*frames: pd.DataFrame) -> set[str]:
    """§A bullet 5 — post-(full-row-)dedup uniqueness assert per (session, root):
    any remaining rows sharing the identity key (root, expiration, strike, right)
    differ in some OTHER column (exact duplicates were already dropped), so the
    ENTIRE root is excluded for this session — never row-level silent dedup, never
    a whole-board crash. Checked across every tier's slice for the session; a
    conflict in ANY tier excludes the root from ALL tiers for that session."""
    excluded: set[str] = set()
    for df in frames:
        if df is None or df.empty:
            continue
        dup = df.duplicated(subset=_IDENT_COLS, keep=False)
        if dup.any():
            excluded.update(df.loc[dup, "root"].astype(str).unique().tolist())
    return excluded


def _assemble_chain_frame(eod_s: pd.DataFrame, oi_s: pd.DataFrame, greeks_s: pd.DataFrame,
                           session: str, *, record_rungs: dict[str, int],
                           record_rung2_detail: dict[str, dict[str, Any]] | None = None
                           ) -> tuple[pd.DataFrame, dict[str, set[str]], dict[str, float], dict[str, float]]:
    """Build one session's per-contract chain frame with the engine's declared
    production schema (spec §B row 'dtypes'): ``underlying`` category, ``expiry``
    datetime64, ``K``/``T``/``iv``/``delta``/``oi``/``volume``/``spot`` float32,
    ``is_call`` bool, plus ``strike_ticker`` str (the join key ``doi_lean`` uses).

    Returns ``(frame, excluded_by_reason, rung1_by_root, oi_match_rates)`` —
    ``excluded_by_reason`` is ``{reason: {root, ...}}`` with two reasons possible:
    ``conflicting_duplicate`` (§A bullet 5) and ``oi_baseline_absent`` (§A bullet 7
    as amended by verify-round N3, below). ``rung1_by_root`` is the RAW per-root
    median ``underlying_price`` (§D rung 1, independent of whether the ladder
    ultimately fell through to rung 2/3 for the ``spot`` column) — the same raw
    basis §D requires for ``summary_spot``. ``oi_match_rates`` is the measured
    per-contract match rate for every root EXCLUDED via ``oi_baseline_absent``
    (spec §A #7's "record ... the measured rate"); empty for any other exclusion
    reason and for roots that were not excluded at all.
    """
    eod_s, oi_s, greeks_s = _dedupe_full_row(eod_s), _dedupe_full_row(oi_s), _dedupe_full_row(greeks_s)
    excluded_by_reason: dict[str, set[str]] = {}
    conflicting_roots = _find_conflicting_roots(eod_s, oi_s, greeks_s)
    if conflicting_roots:
        excluded_by_reason["conflicting_duplicate"] = set(conflicting_roots)
        eod_s = eod_s[~eod_s["root"].astype(str).isin(conflicting_roots)] if not eod_s.empty else eod_s
        oi_s = oi_s[~oi_s["root"].astype(str).isin(conflicting_roots)] if not oi_s.empty else oi_s
        greeks_s = greeks_s[~greeks_s["root"].astype(str).isin(conflicting_roots)] if not greeks_s.empty else greeks_s

    if eod_s.empty:
        return pd.DataFrame(columns=_CHAIN_COLUMNS), excluded_by_reason, {}, {}

    # N3 (verify round BLOCKER, spec §A #7 as amended 2026-08-22): OI-baseline
    # availability is a PER-CONTRACT-COVERAGE precondition, not root presence.
    # The earlier root-PRESENCE guard ("does this root have ANY oi row this
    # session") missed per-contract absence -- a root with exactly ONE
    # surviving oi row (out of e.g. 168 contracts) read as "present" and
    # therefore fully covered, which is how the reviewer's one-row reproduction
    # flipped Q_oi +0.50 -> -0.89. For each root materialised in eod_s this
    # session:
    #   match_rate = |oi_keys(s,root) ∩ eod_keys(s,root)| / |eod_keys(s,root)|
    # on the (expiration, strike, right) identity within the root (zero-oi-rows
    # is simply the rate=0.0 case of the SAME bucket). match_rate < FLOOR
    # excludes the ENTIRE root from this session's frame; the exclusion
    # diagnostic records BOTH the reason and the measured rate. Row-level
    # eod\oi gaps ABOVE the floor keep their ordinary NaN->0 fill downstream
    # (a genuine new listing has a true zero baseline and is never excluded by
    # this check).
    _ident_no_root = ["expiration", "strike", "right"]
    eod_keys_by_root: dict[str, set[tuple]] = {
        str(root): set(map(tuple, grp[_ident_no_root].itertuples(index=False, name=None)))
        for root, grp in eod_s.groupby(eod_s["root"].astype(str))
    }
    oi_keys_by_root: dict[str, set[tuple]] = {}
    if oi_s is not None and not oi_s.empty:
        oi_keys_by_root = {
            str(root): set(map(tuple, grp[_ident_no_root].itertuples(index=False, name=None)))
            for root, grp in oi_s.groupby(oi_s["root"].astype(str))
        }

    oi_absent_roots: set[str] = set()
    oi_match_rates: dict[str, float] = {}
    for root, ekeys in eod_keys_by_root.items():
        n_eod_keys = len(ekeys)
        if n_eod_keys == 0:
            continue  # unreachable in practice (grouped from a non-empty eod_s)
        okeys = oi_keys_by_root.get(root, set())
        match_rate = len(ekeys & okeys) / n_eod_keys
        if match_rate < _OI_COVERAGE_FLOOR:
            oi_absent_roots.add(root)
            oi_match_rates[root] = match_rate

    if oi_absent_roots:
        excluded_by_reason.setdefault("oi_baseline_absent", set()).update(oi_absent_roots)
        eod_s = eod_s[~eod_s["root"].astype(str).isin(oi_absent_roots)]
        if not greeks_s.empty:
            greeks_s = greeks_s[~greeks_s["root"].astype(str).isin(oi_absent_roots)]

    if eod_s.empty:
        return pd.DataFrame(columns=_CHAIN_COLUMNS), excluded_by_reason, {}, oi_match_rates

    merged = eod_s
    if not oi_s.empty:
        merged = merged.merge(oi_s[_IDENT_COLS + ["open_interest"]], on=_IDENT_COLS, how="left")
    else:
        merged = merged.assign(open_interest=np.nan)

    rung1_by_root: dict[str, float] = {}
    if not greeks_s.empty and "underlying_price" in greeks_s.columns:
        up = pd.to_numeric(greeks_s["underlying_price"], errors="coerce")
        rung1_by_root = greeks_s.assign(_up=up).groupby("root")["_up"].median().dropna().to_dict()
        merged = merged.merge(greeks_s[_IDENT_COLS + ["implied_vol", "delta"]], on=_IDENT_COLS, how="left")
    else:
        merged["implied_vol"] = np.nan
        merged["delta"] = np.nan

    roots_here = sorted(merged["root"].astype(str).unique())
    resolved_spot: dict[str, float | None] = {}
    for r in roots_here:
        val, rung = _resolve_root_spot(r, session, rung1_by_root.get(r), rung2_detail=record_rung2_detail)
        resolved_spot[r] = val
        record_rungs[r] = rung

    ticker, _ok = _strike_ticker_and_ok(merged["root"], merged["expiration"], merged["right"], merged["strike"])
    expiry_dt = pd.to_datetime(merged["expiration"], errors="coerce")
    s_ts = pd.Timestamp(session)
    T = ((expiry_dt - s_ts).dt.days / 365.0).clip(lower=0.0)

    out = pd.DataFrame({
        "underlying": merged["root"].astype(str).astype("category"),
        "strike_ticker": ticker.astype(str),
        "expiry": expiry_dt,
        "K": pd.to_numeric(merged["strike"], errors="coerce").astype("float32"),
        "T": T.astype("float32"),
        "iv": pd.to_numeric(merged["implied_vol"], errors="coerce").astype("float32"),
        "delta": pd.to_numeric(merged["delta"], errors="coerce").astype("float32"),
        "is_call": merged["right"].astype(str).str.upper().eq("C"),
        "oi": pd.to_numeric(merged["open_interest"], errors="coerce").astype("float32"),
        "volume": pd.to_numeric(merged["volume"], errors="coerce").astype("float32"),
        "spot": merged["root"].astype(str).map(resolved_spot).astype("float32"),
    })
    return out, excluded_by_reason, rung1_by_root, oi_match_rates


def _build_chain_next(oi_d: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, set[str]]]:
    """``chain_next`` (D) — OI TIER ROWS DATED D ONLY, 5 columns (spec §B):
    identity + ``open_interest`` -> ``underlying``, ``strike_ticker``, ``expiry``,
    ``is_call``, ``oi``.

    Leak barrier (corrected wording, review round 2026-08-22, spec §B): this is a
    FILTERING guarantee, not a never-opened one. No eod/greeks VALUE dated D is
    ever materialised into a scored frame by this function or by ``build()`` — D's
    eod/greeks tiers are simply never passed to it — but session-presence counting
    for the §C predicate (``build()``'s own ``n_eod``/``n_oi`` computation) may
    legitimately read D-dated eod identity/date columns across the wider candidate
    range when such rows exist; those presence counts bind into the
    ``session_presence`` receipt (§F), so a genuine D-dated row-population change
    that could move ``as_of_session`` still moves ``receipt_id``."""
    if oi_d is None or oi_d.empty:
        return pd.DataFrame(columns=_CHAIN_NEXT_COLUMNS), {}
    oi_d = _dedupe_full_row(oi_d)
    conflicting_roots = _find_conflicting_roots(oi_d)
    excluded_by_reason: dict[str, set[str]] = {"conflicting_duplicate": set(conflicting_roots)} if conflicting_roots else {}
    if conflicting_roots:
        oi_d = oi_d[~oi_d["root"].astype(str).isin(conflicting_roots)]
    if oi_d.empty:
        return pd.DataFrame(columns=_CHAIN_NEXT_COLUMNS), excluded_by_reason
    ticker, _ok = _strike_ticker_and_ok(oi_d["root"], oi_d["expiration"], oi_d["right"], oi_d["strike"])
    out = pd.DataFrame({
        "underlying": oi_d["root"].astype(str).astype("category"),
        "strike_ticker": ticker.astype(str),
        "expiry": pd.to_datetime(oi_d["expiration"], errors="coerce"),
        "is_call": oi_d["right"].astype(str).str.upper().eq("C"),
        "oi": pd.to_numeric(oi_d["open_interest"], errors="coerce").astype("float32"),
    })
    return out, excluded_by_reason


# ─────────────────────────────────────────────────────────────────────────────
# §F receipts — per-(session, tier) row digests over CONSUMED columns only.
# ─────────────────────────────────────────────────────────────────────────────


def _canon_float(v: Any) -> float | None:
    """m3 (review round, 2026-08-22): normalise ``-0.0`` to ``0.0`` before any
    digest formats it — ``f"{-0.0:.6f}"`` preserves the sign (``"-0.000000"``),
    which would hash a tiny negative-noise value (e.g. an option ``delta`` at the
    money) differently from an economically-identical positive-noise value."""
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fv):
        return None
    return 0.0 if fv == 0.0 else fv


def _canonical_row(cols: list[str], values: tuple) -> str:
    parts = []
    for k, v in zip(cols, values):
        if isinstance(v, float):
            if not math.isfinite(v):
                parts.append(f"{k}=NaN")
            else:
                parts.append(f"{k}={_canon_float(v):.6f}")   # m3: -0.0 -> 0.0 before repr
        elif v is None or pd.isna(v):
            parts.append(f"{k}=None")
        else:
            parts.append(f"{k}={v}")
    return "|".join(parts)


def _tier_session_digest(df: pd.DataFrame, tier: str, session: str) -> str:
    """sha256 over the canonically-sorted, fixed-decimal-repr rows of ``df`` dated
    ``session`` — CONSUMED columns only (spec §F). Never ``hash_pandas_object``; an
    empty/absent slice hashes to the stable sha256-of-nothing (a real, honest
    "zero rows this session" digest, not a null sentinel)."""
    cols = _DIGEST_COLS[tier]
    rows: list[str] = []
    if df is not None and not df.empty and "date" in df.columns:
        sub = df.loc[df["date"] == session]
        if not sub.empty:
            sub = sub.copy()
            sub["root"] = sub["root"].astype(str).str.upper()
            sub["expiration"] = pd.to_datetime(sub["expiration"], errors="coerce").dt.date.astype(str)
            sub["right"] = sub["right"].astype(str).str.upper()
            sub["strike"] = pd.to_numeric(sub["strike"], errors="coerce")
            for c in cols:
                if c not in sub.columns:
                    sub[c] = np.nan
            for c in cols:
                if c not in ("root", "expiration", "right", "date"):
                    sub[c] = pd.to_numeric(sub[c], errors="coerce").astype("float64")
            for rec in sub[cols].itertuples(index=False, name=None):
                rows.append(_canonical_row(cols, rec))
    rows.sort()
    h = hashlib.sha256()
    for r in rows:
        h.update(r.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Non-chain §2 inputs — UNCHANGED by the ThetaData cutover (earnings/Prophet/
# signing-gate live outside the options-chain estate).
# ─────────────────────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_earnings(symbols: list[str]) -> tuple[dict[str, str | None], bool]:
    if not EARNINGS_PATH.exists():
        return {s: None for s in symbols}, False
    try:
        df = pd.read_parquet(EARNINGS_PATH, columns=["next_date"])
    except Exception:
        return {s: None for s in symbols}, False
    nd = df["next_date"].to_dict()
    return {s: nd.get(s) for s in symbols}, True


def _load_prophet() -> tuple[dict[str, str | None], dict[str, str | None], dict[str, bool],
                              dict[str, str | None], str | None]:
    """B4 — read BOTH Prophet domains from ``site/prophet/index.json``: ``plans[]``
    (``entry_status``/``lifecycle_state``/``closed``) and ``intake.receipts.groups``
    (bucket ``reason``, e.g. ``ran_too_far``/``already_open``/``not_ready``). Returns
    ``(entry_status, lifecycle_state, closed, group_reason, asof)``, all keyed by
    symbol; the two-domain precedence resolution itself is pure and lives in the engine
    (``prophet_plan_state``/``prophet_group_state``/``prophet_state_combined``).

    A symbol with more than one ``plans[]`` entry (a resolved/invalidated history entry
    alongside a live one) keeps its first OPEN (``closed`` False) record and ignores
    later entries — once an open record is found, a later closed one never overwrites it.
    """
    if not PROPHET_INDEX_PATH.exists():
        return {}, {}, {}, {}, None
    try:
        payload = json.loads(PROPHET_INDEX_PATH.read_text())
    except Exception:
        return {}, {}, {}, {}, None

    entry_status: dict[str, str | None] = {}
    lifecycle_state: dict[str, str | None] = {}
    closed: dict[str, bool] = {}
    for pl in (payload.get("plans") or []):
        asset = pl.get("asset")
        if not asset:
            continue
        if asset in closed and not closed[asset]:
            continue  # already hold an OPEN record for this asset — never displaced
        entry_status[asset] = pl.get("entry_status")
        lifecycle_state[asset] = pl.get("lifecycle_state")
        closed[asset] = bool(pl.get("closed"))

    # F13 (2026-08-18): a ticker can appear in MORE THAN ONE intake.receipts.groups
    # bucket in the same file (e.g. both `not_ready` and `ran_too_far`); the keep
    # must resolve by the SAME ruled precedence B4 already uses for cross-domain
    # collisions (EXTENDED > ALREADY_OPEN > NOT_READY > READY > OTHER), never by
    # file/array order — a `setdefault` silently kept whichever bucket happened to
    # be enumerated first, which rendered a genuinely `ran_too_far`/EXTENDED name
    # as "Entry not ready yet" whenever `not_ready` preceded it in the array.
    group_reason: dict[str, str | None] = {}
    groups = (((payload.get("intake") or {}).get("receipts") or {}).get("groups")) or []
    for g in groups:
        reason = g.get("reason")
        for entry in (g.get("names") or []):
            ticker = entry.get("ticker") if isinstance(entry, dict) else entry
            if not ticker:
                continue
            if ticker not in group_reason or (
                brief.prophet_group_precedence_rank(reason)
                < brief.prophet_group_precedence_rank(group_reason[ticker])
            ):
                group_reason[ticker] = reason

    return entry_status, lifecycle_state, closed, group_reason, payload.get("asof")


def _load_signing_gate() -> tuple[bool, str | None]:
    if not SIGNING_GATE_PATH.exists():
        return False, None
    try:
        payload = json.loads(SIGNING_GATE_PATH.read_text())
    except Exception:
        return False, None
    return bool(payload.get("direction_reliable")), payload.get("asof")


def _gex_cfg() -> dict[str, Any]:
    """F2a — the ``polygon.gex`` config block, read INDEPENDENTLY of
    ``options_universe.gex_symbols()``'s own internal resolution (mirrors it exactly:
    same nested-get chain) so this fail-closed diagnostic probe never touches that
    call's signature or its existing zero-arg test monkeypatch surface across the
    whole b1-b5 fixture family. (Config key stays ``polygon.gex`` — a config-schema
    rename is out of scope for this data-source cutover.)"""
    from lib import config as _config
    return (_config.load().get("polygon", {}) or {}).get("gex", {}) or {}


# ─────────────────────────────────────────────────────────────────────────────
# Staleness (wall-clock; the ONE place `now` may be read — engine never sees it).
# ─────────────────────────────────────────────────────────────────────────────


def _sessions_apart_str(a: str | None, b: str | None) -> int | None:
    """String-date wrapper for ``lib.nyse_calendar.sessions_apart`` — the engine deals
    only in ISO session strings (it never imports a calendar module itself)."""
    if a is None or b is None:
        return None
    return nc.sessions_apart(date.fromisoformat(a), date.fromisoformat(b))


def _session_n_forward_str(d: str, n: int) -> str:
    got = nc.session_n_forward(date.fromisoformat(d), n)
    return got.isoformat() if got is not None else d


def _is_stale(newest_session: str, now: datetime) -> bool:
    close_dt = datetime.combine(date.fromisoformat(newest_session), _CLOSE_PLUS_SETTLE_ET, tzinfo=_ET)
    hours = (now.astimezone(timezone.utc) - close_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    return hours > _STALE_AFTER_HOURS


# ─────────────────────────────────────────────────────────────────────────────
# Atomic write + semantic no-op (house idiom, contract §7).
# ─────────────────────────────────────────────────────────────────────────────


def write_json_atomic(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        body = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _semantic_unchanged(existing_path: Path, new_payload: dict[str, Any]) -> bool:
    """True iff a prior artifact exists with the same receipt_id AND identical payload
    once ``built_at_utc`` AND the diagnostic-only ``_run`` block are excluded (contract
    §7 — never churn git on a semantic no-op). ``_run`` carries the resolved store's
    ABSOLUTE path (m5) and per-tier corrupt-file counts — neither is hashed into
    ``receipt_id`` and neither should force a rewrite on a pure host/path migration."""
    if not existing_path.exists():
        return False
    try:
        old = json.loads(existing_path.read_text())
    except Exception:
        return False
    if old.get("receipt_id") != new_payload.get("receipt_id"):
        return False
    strip = lambda d: {k: v for k, v in d.items() if k not in ("built_at_utc", "_run")}  # noqa: E731
    return strip(old) == strip(new_payload)


# ─────────────────────────────────────────────────────────────────────────────
# Main.
# ─────────────────────────────────────────────────────────────────────────────


def build(*, now: datetime | None = None, out_path: Path = OUT_PATH,
          ignore_staleness: bool = False) -> dict[str, Any] | None:
    """Returns the built payload, or ``None`` when the ThetaData store cannot be
    resolved off-host (spec §G self-skip — the caller must leave the committed
    artifact untouched and exit 0, never crash the nightly)."""
    now = now or datetime.now(timezone.utc)

    store = _resolve_store_with_diagnostics(purpose="options_intel_brief")
    if store is None:
        return None

    # m5 (review round, 2026-08-22): the `store_resolution` receipt's `sha256`
    # binds the resolver SOURCE TAG (env/data_dir/ops-wt) only, never the
    # absolute path — a host/path migration with identical data must not churn
    # `receipt_id`. The `path` field ALSO stops being the absolute path (the
    # WHOLE receipt dict is hashed by `brief.receipt_id()`, not just its own
    # `sha256` field, so a raw absolute path there would keep churning
    # `receipt_id` even with the `sha256` fix alone) — it becomes a stable
    # logical URI instead. The actual resolved absolute path is recorded ONLY in
    # the diagnostic `_run` block (never hashed, never compared for the §7
    # semantic no-op — see `_semantic_unchanged`).
    source_tag = _store_source_label(store)
    corrupt_files: dict[str, int] = {}
    store_receipt: dict[str, Any] = {
        "logical_source": "store_resolution", "path": f"thetadata://store/{source_tag}",
        "asof": None, "sha256": brief.sha256_of({"source": source_tag}),
        "state": "ok", "corrupt_files": 0,
    }
    input_receipts: list[dict[str, Any]] = [store_receipt]

    def _run_block() -> dict[str, Any]:
        return {
            "store_resolution": {"resolved_path": str(store), "source": source_tag},
            "corrupt_files_by_tier": dict(sorted(corrupt_files.items())),
        }

    # B2 — the canonical current universe, resolved ONCE (unchanged call signature —
    # engine/options_universe.py is a shared plane, never touched here).
    universe = options_universe.gex_symbols()
    universe_sha = brief.sha256_of(sorted(universe))
    input_receipts.append({
        "logical_source": "universe_resolution", "path": "engine/options_universe.py::gex_symbols",
        "asof": None, "sha256": universe_sha, "count": len(universe),
        "state": "ok" if universe else "missing",
    })

    anchor_str = _latest_known_date(store, universe, corrupt_counter=corrupt_files)
    if anchor_str is None:
        # Nothing dated in the store for this universe at all — no lawful pair is
        # even conceivable. Same MIXED_VINTAGE shape the frozen engine already uses.
        panel = brief.SessionPanel(
            as_of_session=None, oi_counted_date=None, pending_session=None,
            pending_reason=None, chains_by_session={}, chain_next=None, lawful_pairs={},
        )
        watermarks = {"chains_session_S": None, "chains_session_D": None,
                      "summaries_max_session": None, "events_loaded": False,
                      "prophet_asof": None, "signing_gate_asof": None}
        payload = brief.build_intel_brief(
            panel, source_watermarks=watermarks, input_receipts=input_receipts,
            built_at_utc=now.isoformat(), sessions_apart_fn=_sessions_apart_str,
            session_n_forward_fn=_session_n_forward_str,
        )
        payload["_run"] = _run_block()
        return payload

    candidate, query_end = _candidate_window(date.fromisoformat(anchor_str), K_SESSIONS)
    eod_all = _read_universe_tier_range(store, "eod", universe, start=candidate[0], end=query_end,
                                         columns=_EOD_COLS, corrupt_counter=corrupt_files)
    oi_all = _read_universe_tier_range(store, "oi", universe, start=candidate[0], end=query_end,
                                        columns=_OI_COLS, corrupt_counter=corrupt_files)
    greeks_all = _read_universe_tier_range(store, "greeks", universe, start=candidate[0], end=query_end,
                                            columns=_GREEKS_COLS, corrupt_counter=corrupt_files)
    store_receipt["corrupt_files"] = sum(corrupt_files.values())

    n_eod = eod_all.groupby("date")["root"].nunique() if not eod_all.empty else pd.Series(dtype="int64")
    n_oi = oi_all.groupby("date")["root"].nunique() if not oi_all.empty else pd.Series(dtype="int64")
    committed_sessions, F, decision_info = _select_committed_sessions(candidate, n_eod, n_oi)

    # N2 (verify round, narrows M1+M2(b)): `session_presence` receipt — sha256
    # over (a) the ordered per-candidate (session, plaus_bool, balanced_bool)
    # decision tuples, plus (b) the exact (n_eod, n_oi) counts for ONLY the
    # decision-critical sessions (final max(F), every demoted session, and the
    # X candidate). This still binds every presence fact that can move S/D
    # selection (M1's property survives), while a count drift on a
    # never-materialised candidate that flips no decision boolean no longer
    # churns `receipt_id` (spec §F).
    presence_payload = {
        "decisions": decision_info["candidate_decisions"],
        "counts": sorted(decision_info["counts"].items()),
    }
    input_receipts.append({
        "logical_source": "session_presence", "path": "thetadata://session_presence",
        "asof": anchor_str, "sha256": brief.sha256_of(presence_payload),
        "member_count": len(decision_info["candidate_decisions"]),
        "state": "ok" if decision_info["candidate_decisions"] else "missing",
    })

    S, D, pending = brief.select_settled_pair(committed_sessions, lambda d: (
        nc.session_n_forward(date.fromisoformat(d), 1).isoformat()
        if nc.session_n_forward(date.fromisoformat(d), 1) else None
    ))
    lawful_pairs = _lawful_pairs(committed_sessions)

    if S is None:
        # No lawful pair at all — MIXED_VINTAGE. Engine handles this branch directly
        # off a SessionPanel with as_of_session=None; still supply the receipts
        # already gathered above so the header/receipt path is exercised honestly.
        panel = brief.SessionPanel(
            as_of_session=None, oi_counted_date=None, pending_session=pending,
            pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
            chains_by_session={}, chain_next=None, lawful_pairs=lawful_pairs,
        )
        watermarks = {"chains_session_S": None, "chains_session_D": None,
                      "summaries_max_session": None, "events_loaded": False,
                      "prophet_asof": None, "signing_gate_asof": None}
        payload = brief.build_intel_brief(
            panel, source_watermarks=watermarks, input_receipts=input_receipts,
            built_at_utc=now.isoformat(), sessions_apart_fn=_sessions_apart_str,
            session_n_forward_fn=_session_n_forward_str,
        )
        payload["_run"] = _run_block()
        return payload

    # §C depth bound: materialise only the trailing K NYSE sessions of F (the
    # OI-only frontier X, if admitted, is NEVER materialised as a full chain frame —
    # only its OI tier is ever opened, for chain_next below).
    load_sessions = [s for s in F if s <= S][-K_SESSIONS:]

    chains_by_session: dict[str, pd.DataFrame] = {}
    identity_root_exclusions: dict[str, list[dict[str, str]]] = {}
    rung_by_session: dict[str, dict[str, int]] = {}
    rung1_history: dict[str, dict[str, float]] = {}
    rung2_detail_by_session: dict[str, dict[str, dict[str, Any]]] = {}

    def _record_exclusions(session_key: str, by_reason: dict[str, set[str]],
                            rates: dict[str, float] | None = None) -> None:
        if not by_reason:
            return
        entries = list(identity_root_exclusions.get(session_key, []))
        seen = {(e["root"], e["reason"]) for e in entries}
        for reason, roots in by_reason.items():
            for r in sorted(roots):
                key = (r, reason)
                if key not in seen:
                    seen.add(key)
                    entry: dict[str, Any] = {"root": r, "reason": reason}
                    # N3 (verify round): the ``oi_baseline_absent`` diagnostic
                    # carries the measured per-contract match rate alongside the
                    # reason (spec §A #7 — "record ... the measured rate").
                    if rates is not None and r in rates:
                        entry["rate"] = round(rates[r], 6)
                    entries.append(entry)
        identity_root_exclusions[session_key] = sorted(entries, key=lambda e: (e["root"], e["reason"]))

    for s in load_sessions:
        eod_s = eod_all[eod_all["date"] == s] if not eod_all.empty else eod_all
        oi_s = oi_all[oi_all["date"] == s] if not oi_all.empty else oi_all
        greeks_s = greeks_all[greeks_all["date"] == s] if not greeks_all.empty else greeks_all
        rung_map_s: dict[str, int] = {}
        rung2_detail_s: dict[str, dict[str, Any]] = {}
        frame, excluded_by_reason, rung1_by_root, oi_match_rates = _assemble_chain_frame(
            eod_s, oi_s, greeks_s, s, record_rungs=rung_map_s, record_rung2_detail=rung2_detail_s)
        chains_by_session[s] = frame
        _record_exclusions(s, excluded_by_reason, oi_match_rates)
        rung_by_session[s] = rung_map_s
        rung1_history[s] = rung1_by_root
        rung2_detail_by_session[s] = rung2_detail_s

    oi_d = oi_all[oi_all["date"] == D] if not oi_all.empty else oi_all
    chain_D, excluded_d_by_reason = _build_chain_next(oi_d)
    _record_exclusions(D, excluded_d_by_reason)

    # §F chains domain — per-(session, tier) digests over the RAW, pre-exclusion
    # slice (the "consumed" set is "actually opened", the F1-precedent framing —
    # a root's data can be OPENED and hashed even when a same-session identity
    # conflict later excludes it from scoring).
    chains_files: dict[str, str] = {}
    for s in load_sessions:
        chains_files[f"thetadata://eod/{s}"] = _tier_session_digest(eod_all, "eod", s)
        chains_files[f"thetadata://oi/{s}"] = _tier_session_digest(oi_all, "oi", s)
        chains_files[f"thetadata://greeks/{s}"] = _tier_session_digest(greeks_all, "greeks", s)
    chains_files[f"thetadata://oi/{D}"] = _tier_session_digest(oi_all, "oi", D)
    chains_root = brief.sha256_of(sorted(chains_files.items())) if chains_files else None

    composite_S = brief.sha256_of([
        chains_files.get(f"thetadata://eod/{S}"), chains_files.get(f"thetadata://oi/{S}"),
        chains_files.get(f"thetadata://greeks/{S}"),
    ])
    input_receipts.append({
        "logical_source": "chains_S", "path": f"thetadata://composite/{S}",
        "asof": S, "sha256": composite_S,
        "state": "ok" if not chains_by_session[S].empty else "missing",
    })
    input_receipts.append({
        "logical_source": "chains_D", "path": f"thetadata://oi/{D}",
        "asof": D, "sha256": chains_files.get(f"thetadata://oi/{D}"),
        "state": "ok" if not chain_D.empty else "missing",
    })
    input_receipts.append({
        "logical_source": "chains_manifest", "path": "thetadata://chains",
        "asof": S, "sha256": chains_root, "member_count": len(chains_files),
        "state": "ok" if chains_files else "missing",
    })
    if identity_root_exclusions:
        input_receipts.append({
            "logical_source": "identity_root_exclusions", "path": "thetadata://identity_exclusions",
            "asof": S,
            "sha256": brief.sha256_of(sorted(
                (s, sorted((e["root"], e["reason"], e.get("rate")) for e in v))
                for s, v in identity_root_exclusions.items()
            )),
            "member_count": sum(len(v) for v in identity_root_exclusions.values()),
            "state": "ok",
        })
    else:
        input_receipts.append({
            "logical_source": "identity_root_exclusions", "path": "thetadata://identity_exclusions",
            "asof": S, "sha256": None, "member_count": 0, "state": "missing",
        })

    present_names = sorted(brief.session_metrics(chains_by_session[S]).keys())

    # F2a — fail CLOSED (producer-only) when the config wants baskets folded in
    # (`include_baskets: true`) but the resolved universe came back no larger than
    # the config anchor list — the observable signature of
    # `options_universe.baskets_universe()`'s own swallowed-error empty return.
    gex_cfg = _gex_cfg()
    _anchor_list = list(gex_cfg.get("symbols") or options_universe.DEFAULT_ANCHORS)
    n_anchors = len({str(t).upper() for t in _anchor_list})
    if bool(gex_cfg.get("include_baskets", False)) and len(universe) <= n_anchors:
        panel = brief.SessionPanel(
            as_of_session=S, oi_counted_date=D, pending_session=pending,
            pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
            chains_by_session=chains_by_session, chain_next=chain_D, lawful_pairs=lawful_pairs,
        )
        watermarks = {
            "chains_session_S": S, "chains_session_D": D, "summaries_max_session": None,
            "events_loaded": False, "prophet_asof": None, "signing_gate_asof": None,
        }
        partial_manifest = {
            "gex_summary": {"root": None, "member_count": 0, "files": {}},
            "gex_confirm": {"root": None, "member_count": 0, "files": {}},
            "chains": {"root": chains_root, "member_count": len(chains_files),
                       "files": dict(sorted(chains_files.items()))},
        }
        payload = brief.degraded_payload(
            reason="UNIVERSE_RESOLUTION_FAILED", panel=panel, source_watermarks=watermarks,
            input_receipts=input_receipts, built_at_utc=now.isoformat(),
            source_manifest=partial_manifest,
        )
        payload["_run"] = _run_block()
        return payload

    # §D spot ladder — summary_spot (per-session median greeks underlying_price,
    # trailing LOOKBACK+1 committed-window sessions <= S, rung-1 raw basis only —
    # NEVER the ladder-resolved `spot` column, which may fall through to rung 2).
    window_sessions = load_sessions[-(brief.CONFIG["LOOKBACK"] + 1):]
    summary_spot: dict[str, list[float]] = {}
    for sym in present_names:
        vals = []
        for s in window_sessions:
            v = rung1_history.get(s, {}).get(sym)
            if v is not None and math.isfinite(v) and v > 0:
                vals.append(float(v))
        summary_spot[sym] = vals

    rung_map_S = {sym: r for sym, r in rung_by_session.get(S, {}).items() if sym in present_names}
    input_receipts.append({
        "logical_source": "spot_authority",
        "path": "engine/price_ladder.py::resolve_close + thetadata greeks underlying_price",
        "asof": S, "sha256": brief.sha256_of(sorted(rung_map_S.items())),
        "count": len(rung_map_S), "state": "ok" if rung_map_S else "missing",
    })

    # §E — P/GEX mechanics HARD-DISABLED for the cutover. `site/gex/*.json` is
    # legacy-Polygon-estate provenance; never read here again, regardless of any
    # `meta.asof == S` date coincidence. gex_verdict stays permanently empty so
    # `m_gex_multiplier` reads 1.0 for every card (M_gex ≡ 1.0).
    gex_verdict: dict[str, str | None] = {}

    event_date, events_loaded = _load_earnings(present_names)
    (prophet_entry_status, prophet_lifecycle_state, prophet_plan_closed,
     prophet_group_reason, prophet_asof) = _load_prophet()
    direction_reliable, signing_gate_asof = _load_signing_gate()

    # gex_summary domain (§F): the spot/summary-spot authority manifest — rung-2
    # price-ladder resolutions actually consumed + the derived spot-history slices
    # (logical URIs; empty when nothing was consumed).
    #
    # B2 (BLOCKER, review round): the rung-2 hash used to be a CONSTANT descriptor
    # (`{"rung": 2, "asof": S, "symbol": sym}`) — changing the underlying rung-2
    # close value left `receipt_id` unchanged while the scored board changed.
    # Every rung-2 symbol now binds the actually-CONSUMED resolved close VALUE
    # (fixed-decimal repr via `_canon_float`), the ladder `price_source` tag, and
    # the series LAST INDEX DATE — a rung-2 close change, or a rung-1<->rung-2
    # transition, must move `receipt_id` (spec §F).
    rung2_detail_S = rung2_detail_by_session.get(S, {})
    gex_summary_files: dict[str, str] = {}
    for sym in present_names:
        hist = summary_spot.get(sym) or []
        if hist:
            gex_summary_files[f"thetadata://spot_history/{sym}"] = brief.sha256_of(hist)
        if rung_map_S.get(sym) == 2:
            detail = rung2_detail_S.get(sym) or {}
            gex_summary_files[f"priceladder://resolve_close/{sym}"] = brief.sha256_of({
                "rung": 2, "asof": S, "symbol": sym,
                "value": _canon_float(detail.get("value")),
                "price_source": detail.get("price_source"),
                "last_index_date": detail.get("last_index_date"),
            })
    summary_root = brief.sha256_of(sorted(gex_summary_files.items())) if gex_summary_files else None

    source_manifest = {
        "gex_summary": {"root": summary_root, "member_count": len(gex_summary_files),
                         "files": dict(sorted(gex_summary_files.items()))},
        "gex_confirm": {"root": None, "member_count": 0, "files": {}},
        "chains": {"root": chains_root, "member_count": len(chains_files),
                   "files": dict(sorted(chains_files.items()))},
    }

    input_receipts.append({
        "logical_source": "earnings", "path": str(EARNINGS_PATH.relative_to(_REPO_ROOT)),
        "asof": S, "sha256": _sha256_file(EARNINGS_PATH),
        "state": "ok" if events_loaded else "missing",
    })
    input_receipts.append({
        "logical_source": "prophet_index", "path": str(PROPHET_INDEX_PATH.relative_to(_REPO_ROOT)),
        "asof": prophet_asof, "sha256": _sha256_file(PROPHET_INDEX_PATH),
        "state": "ok" if PROPHET_INDEX_PATH.exists() else "missing",
    })
    input_receipts.append({
        "logical_source": "signing_gate", "path": str(SIGNING_GATE_PATH.relative_to(_REPO_ROOT)),
        "asof": signing_gate_asof, "sha256": _sha256_file(SIGNING_GATE_PATH),
        "state": "ok" if SIGNING_GATE_PATH.exists() else "missing",
    })
    input_receipts.append({
        "logical_source": "gex_summary_manifest", "path": "thetadata://spot_history+priceladder",
        "asof": S, "sha256": summary_root, "member_count": len(gex_summary_files),
        "state": "ok" if gex_summary_files else "missing",
    })
    input_receipts.append({
        "logical_source": "gex_confirm_manifest", "path": "thetadata://gex_confirm",
        "asof": S, "sha256": None, "member_count": 0, "state": "missing",
    })

    # B3 (BLOCKER, review round): the staleness anchor is `max(committed_sessions)`
    # EXACTLY (spec §C) — NEVER `anchor_str` (`_latest_known_date`'s newest-EOD-date
    # ceiling scan, which only bounds the candidate window, §C). The pre-fix code
    # anchored staleness on `anchor_str` too, which drifted on a Monday build (eod
    # through Friday, oi through Monday) to a 77h-stale false STALE_SOURCE with
    # zero cards. `committed_sessions` is guaranteed non-empty here (S is not None).
    staleness_anchor = max(committed_sessions)
    stale = (not ignore_staleness) and _is_stale(staleness_anchor, now)

    panel = brief.SessionPanel(
        as_of_session=S, oi_counted_date=D, pending_session=pending,
        pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
        chains_by_session=chains_by_session, chain_next=chain_D, lawful_pairs=lawful_pairs,
        summary_spot=summary_spot, gex_verdict=gex_verdict, gex_bound_to_S=True,
        event_date=event_date, events_loaded=events_loaded,
        prophet_entry_status=prophet_entry_status, prophet_lifecycle_state=prophet_lifecycle_state,
        prophet_plan_closed=prophet_plan_closed, prophet_group_reason=prophet_group_reason,
        prophet_asof=prophet_asof,
        signing_gate_direction_reliable=direction_reliable, signing_gate_asof=signing_gate_asof,
        universe=universe, stale=stale,
    )

    watermarks = {
        "chains_session_S": S, "chains_session_D": D,
        "summaries_max_session": (S if any(summary_spot.values()) else None),
        "events_loaded": events_loaded, "prophet_asof": prophet_asof,
        "signing_gate_asof": signing_gate_asof,
    }

    payload = brief.build_intel_brief(
        panel, source_watermarks=watermarks, input_receipts=input_receipts,
        built_at_utc=now.isoformat(), sessions_apart_fn=_sessions_apart_str,
        session_n_forward_fn=_session_n_forward_str, source_manifest=source_manifest,
    )
    payload["_run"] = _run_block()
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--ignore-staleness", action="store_true",
                     help="diagnostic only: score the newest committed session even if "
                          "it is older than the >36h freshness rule. Never used by the "
                          "nightly lane; for local verification of the scoring math "
                          "against a deliberately frozen test store.")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    payload = build(out_path=out_path, ignore_staleness=args.ignore_staleness)

    if payload is None:
        # §G off-host self-skip: the warning was already emitted by
        # _resolve_store_with_diagnostics(); leave the committed artifact untouched
        # and exit 0 — never crash the nightly on a store-less runner.
        print("::notice title=options-intel-brief::ThetaData store unresolved off-host "
              "-- self-skip, artifact bytes left untouched", flush=True)
        return 0

    if _semantic_unchanged(out_path, payload):
        print(f"::notice title=options-intel-brief::semantic no-op — {out_path} unchanged "
              f"(receipt_id={payload.get('receipt_id')})", flush=True)
    else:
        write_json_atomic(out_path, payload)
        print(f"::notice title=options-intel-brief::wrote {out_path} "
              f"(receipt_id={payload.get('receipt_id')})", flush=True)

    print("=== options.intel_brief/v1 header ===")
    for k in ("as_of_session", "oi_counted_date", "pending_session", "pending_reason",
              "board_state", "board_reason", "eligibility", "receipt_id", "config_hash"):
        print(f"  {k}: {payload.get(k)}")
    sm = payload.get("source_manifest") or {}
    for domain in ("gex_summary", "gex_confirm"):
        d = sm.get(domain) or {}
        print(f"  source_manifest.{domain}: member_count={d.get('member_count')} root={d.get('root')}")
    print("state counts:")
    print(f"  opportunities={len(payload.get('opportunities') or [])} "
          f"(overflow={payload.get('opportunities_overflow')}) "
          f"event_board={len(payload.get('event_board') or [])} "
          f"risk_warnings={len(payload.get('risk_warnings') or [])} "
          f"no_signal_exemplar={'yes' if payload.get('no_signal_exemplar') else 'no'}")
    print("top-6 opportunities:")
    for c in (payload.get("opportunities") or [])[:6]:
        print(f"  {c['symbol']:6s} {c['direction']:10s} R={c['research_priority_score']:4d} "
              f"es={c['evidence_strength']:.3f} ec={c['evidence_confidence']:.3f} "
              f"({c['evidence_confidence_band']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
