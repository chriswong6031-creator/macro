"""Polygon options-OI accrual — the GEX FOUNDATION (display / research only).

Each run snapshots the configured underlyings' option chains via Polygon and:
  1. writes the RAW per-strike chain to data/polygon_gex/chains/{YYYY-MM-DD}.parquet
     — SESSION-partitioned & append-only (never rewrites history, so the daily
     ``git add data/`` adds exactly one small blob). This is the per-strike OI
     history the Cboe path discards and that CANNOT be backfilled: open interest is
     point-in-time only.
  2. upserts a per-underlying compute_gex summary to data/polygon_gex/summary_{SYM}
     .parquet (1 row/session, mirroring the Cboe gex_{SYM} frames so the two sources
     are directly comparable; feeds the future validate-gated GEX drawdown leg).
  3. appends a per-session health-receipt attempt to
     data/polygon_gex_health/{YYYY-MM-DD}.json (AD-1C0, 2026-08-19) — a sidecar,
     never mutating the chain parquet, that turns a failed/partial capture into a
     diagnosable REASON census instead of a bare empty snapshot. See _health_dir()
     for why it is a SIBLING of data/polygon_gex/ rather than nested inside it.

STAMP = THE SESSION THE SNAPSHOT DESCRIBES, NOT THE RUN DATE (2026-08-06 repair).
The accrual used to stamp ``datetime.now(timezone.utc).date()``. A nightly run that
lands at 01:24 UTC carries the PREVIOUS ET session's closing chain, so the whole store
sat one session forward of the market it measures — and the write-side session gate then
refused every Saturday-UTC run, which is a FRIDAY-evening ET accrual. Session 2026-07-31
(the first Friday after the gate landed) was lost that way: runs fired on both 08-01 and
08-02 and both were refused before the fetch, and polygon OI cannot be backfilled.
``_resolve_session`` fixes both halves at once — see its docstring.

No-op without POLYGON_API_KEY. Never raises into the caller — collect.py wraps this
additively, exactly like the FRED-vintages / basket-extras steps. See
collectors/polygon_options.py and engine/gex_engine.py.

History is FORWARD-ONLY here: this writer never deletes or re-dates a stored file. The
one-off repair of the pre-2026-08-06 run-date stamps lives in its own audited script,
``scripts/migrate_polygon_gex_session_stamps.py``.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.polygon_options import PolygonOptions, REASON_CODES  # noqa: E402
from engine.gex_engine import compute_gex  # noqa: E402
from lib import config, store, nyse_calendar  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "polygon_gex"
# the compute_gex summary fields persisted per underlying (matches cboe GexAdapter._row)
SUMMARY_KEYS = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")

# AD-1C0 — a session's stored capture is HEALTHY at/above this coverage; below it
# (but with rows captured) it is PARTIAL; zero rows captured is FAILED. See the
# FIRST-WRITER QUALITY RULE in accrue() for what each verdict is allowed to do.
SOURCE_HEALTH_FLOOR = 0.90

# B2 addendum (coordinator ruling, 2026-08-19) — the store-referenced shrink
# tripwire in accrue() fires when the most recent PRIOR session's stored chain
# has at least this many times as many underlyings as the CURRENTLY resolved
# universe. 3x never fires on a legitimate trim (e.g. 12 -> 10) but always
# fires on a 375 -> ~10 anchors-only collapse. See accrue()'s comment for why
# this closes the attack path the exists()-scoped membership check cannot see
# (an ABSENT membership file in a degraded/sparse/husk checkout).
STORE_SHRINK_FACTOR = 3

# Decisions that ANCHOR the stored chain's CURRENT authoritative state: either a
# decision that actually WROTE the parquet (wrote/replaced_partial/forced), one
# that re-established the receipt's ground truth after corruption
# (receipt_recovered — touches no chain bytes, but B3 requires the corruption
# event itself to become the new anchor so a later run never falls back to a
# 'healthy' default), or a TRAILING write_pending (B3 trigger 2 — see
# accrue()'s write-ahead sequence: a write_pending entry is appended BEFORE
# to_parquet with the FULL census/health the write is ABOUT to produce, so a
# crash between that append and the final decision entry still leaves the
# receipt self-describing the parquet that DID get written, instead of
# silently falling through to legacy-healthy). This is only ever consulted
# when the chain parquet is confirmed to exist (accrue() gates the whole
# lookup on path.exists()), so a trailing write_pending reached here is
# necessarily the "parquet written, finalize-entry crashed" case — never the
# "crashed before to_parquet" one, which never reaches this lookup at all
# (path.exists() is false, so accrue() proceeds straight to a fresh write).
# Every other decision (skipped_*, nothing_captured) is a SKIP: it describes
# an attempt, not a change to what's on disk, and must be invisible here.
_STATE_ANCHOR_DECISIONS = ("wrote", "replaced_partial", "forced", "receipt_recovered",
                          "write_pending")


class _CorruptReceipt(Exception):
    """A health-receipt file EXISTS but cannot be parsed as {"attempts": [...]}
    — raised by _read_receipt so the caller can never confuse "corrupt" with
    "absent" (the B3 defect: corruption used to fail OPEN to healthy)."""


def _resolve_session(as_of) -> date:
    """The NYSE session a snapshot taken at `as_of` describes.

    A ``datetime`` (or None) is an ACCRUAL INSTANT — "snapshot the chains now" — and the
    session it describes is ``expected_last_session``: the most recent session whose
    16:00 ET close plus a settle buffer has passed. A ``date`` is an EXPLICIT session
    (the ``--date`` CLI path and the tests) and is taken at face value.

    ``nyse_calendar.session_date()`` is the WRONG helper here even though it is the house
    default for artifact stamps. It calls the whole ET calendar day "the session" so that
    the intraday fastpath can stamp the session IN PROGRESS; at 02:24 ET Wednesday it
    returns Wednesday, but a chain snapshotted then carries TUESDAY's closing state.
    Measured: the file stamped 2026-07-08 (committed 07-08 06:24Z) has SPY spot 747.71,
    exactly the yahoo close of 07-07. ``expected_last_session`` returns 07-07.

    ``datetime`` is a subclass of ``date``, so the isinstance checks must be in this order.
    """
    if isinstance(as_of, datetime):
        return nyse_calendar.expected_last_session(as_of)
    if isinstance(as_of, date):
        return as_of
    return nyse_calendar.expected_last_session()


def _chains_dir():
    d = config.data_dir() / GROUP / "chains"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _health_dir():
    # NOT data/polygon_gex/health/ (the FROZEN SPEC's literal path) — a SIBLING top-
    # level directory instead, deliberately outside data/polygon_gex/ (DEVIATION,
    # see the packet's DEVIATIONS section). tests/test_polygon_gex_session_stamps.py
    # ::test_no_stray_files_shadow_the_chains_glob (unowned, pinned, not touched by
    # this packet) hard-fails on ANY entry under data/polygon_gex/ that is not
    # "chains" or a "summary_*.parquet" file; a subdirectory there would break that
    # invariant the first time the nightly ever writes a receipt. This directory is
    # still named/co-located right next to data/polygon_gex/, satisfying the spec's
    # intent ("next to the chain store") without colliding with that check.
    d = config.data_dir() / f"{GROUP}_health"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _receipt_path(session: date) -> Path:
    return _health_dir() / f"{session.isoformat()}.json"


def _read_receipt(session: date) -> list[dict] | None:
    """The stored ``attempts`` list for `session`, or None when NO receipt file
    exists at all — either a brand-new session, or a LEGACY chains file
    predating this sidecar (rule 4 of the first-writer quality rule treats that
    as healthy).

    RAISES _CorruptReceipt when a receipt file EXISTS but cannot be parsed as
    {"attempts": [...]} (B3, AD-1C0 review). The pre-fix version caught this
    and returned None — indistinguishable from "no receipt", which made
    corruption fail OPEN: `_stored_health` treated it as a legacy healthy
    session and happily let a later run overwrite/replace it. The caller
    (accrue()) must always handle this distinctly via _recover_corrupt_receipt.
    """
    path = _receipt_path(session)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        attempts = data.get("attempts") if isinstance(data, dict) else None
        if not isinstance(attempts, list):
            raise ValueError("receipt is not a {'attempts': [...]} document")
        return attempts
    except (OSError, ValueError) as e:
        raise _CorruptReceipt(str(e)) from e


def _write_receipt_attempts(session: date, attempts: list[dict]) -> None:
    """Atomic whole-list write: tmp file (PID + UUID suffix — m11, so two
    concurrent writers for the SAME session can never collide on one tmp name)
    then rename. NEVER mutates the chain parquet; this is a sidecar only."""
    path = _receipt_path(session)
    payload = {"session": session.isoformat(), "attempts": attempts}
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _recover_corrupt_receipt(session: date, exc: _CorruptReceipt,
                             now: datetime) -> list[dict]:
    """B3 ruling (AD-1C0 review): a receipt exists but cannot be parsed. Fail
    toward IMMUTABILITY, never destroy evidence, never mislabel:
      1. preserve the corrupt file by renaming it aside to
         <session>.json.corrupt-<capture-instant-compact> — NEVER overwritten
         again, so the raw evidence survives for a human to inspect.
      2. the stored CHAIN is now treated as immutable (PIT protection wins over
         recoverability — corruption must never look like license to
         overwrite/replace a real capture).
      3. a FRESH attempts list starts with one entry: decision
         "receipt_recovered", health "unknown_receipt_corrupt" (never
         "healthy" — that was the original defect), prior_receipt_corrupt=True.
      4. a bare line-start ::warning (never a logger — see
         tests/test_gh_annotation_line_start).
      5. (N7, AD-1C0 round 2) CONCURRENT-RECOVERY SAFE: if the rename fails
         with FileNotFoundError specifically, another recoverer most likely
         already won this exact race between our failed read and this rename
         attempt — renamed `path` aside and written its own fresh receipt
         there. Re-read `path`; if it now parses, ADOPT its attempts instead
         of clobbering the winner with a second, redundant recovery entry.
    Returns the fresh (or adopted) attempts list so the caller can proceed as
    if it had just read a normal (if minimal) receipt.
    """
    path = _receipt_path(session)
    compact_ts = now.strftime("%Y%m%dT%H%M%S%fZ")
    corrupt_aside = path.with_name(f"{path.name}.corrupt-{compact_ts}")
    try:
        path.replace(corrupt_aside)
    except FileNotFoundError:
        try:
            adopted = _read_receipt(session)
        except _CorruptReceipt:
            adopted = None   # still corrupt (or corrupt again) -- fall through
        if adopted is not None:
            log.info("polygon: receipt %s recovery race — adopting a "
                     "concurrent recoverer's fresh receipt instead of "
                     "overwriting it", session)
            return adopted
        corrupt_aside = None
    except OSError as move_exc:  # noqa: BLE001 — losing the evidence copy must
        # never crash the run; recovery still proceeds without it.
        log.warning("polygon: could not preserve corrupt receipt %s aside: %s",
                    path.name, move_exc)
        corrupt_aside = None
    print(
        f"::warning title=polygon-health-receipt::session {session} health receipt "
        f"was corrupt ({exc}) — preserved aside as "
        f"{corrupt_aside.name if corrupt_aside else '(preserve FAILED)'}; the stored "
        f"chain is now treated as IMMUTABLE with UNKNOWN health (never re-labelled "
        f"healthy, never retro-replaced)", flush=True)
    attempts = [{
        "capture_instant": now.isoformat(),
        "requested_underlyings": None, "attempted_underlyings": None,
        "successful_underlyings": None, "coverage_pct": None,
        "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        "decision": "receipt_recovered", "health": "unknown_receipt_corrupt",
        "prior_receipt_corrupt": True,
    }]
    _write_receipt_attempts(session, attempts)
    return attempts


def _stored_state_entry(attempts: list[dict] | None) -> dict | None:
    """The entry describing the CURRENT authoritative state of the stored
    parquet: the most recent attempt whose decision is a _STATE_ANCHOR_DECISION
    (wrote/replaced_partial/forced/receipt_recovered). Every SKIP-shaped
    decision (skipped_*, nothing_captured) is invisible here by design — it
    describes a rejected/no-op ATTEMPT, not a change to what is on disk, so it
    must never be mistaken for the store's ground truth (M12, audit + accrue()
    both read through this one function so they can never disagree)."""
    if not attempts:
        return None
    for entry in reversed(attempts):
        if entry.get("decision") in _STATE_ANCHOR_DECISIONS:
            return entry
    return None


def _stored_health(attempts: list[dict] | None) -> str:
    """Health of whatever is CURRENTLY stored, given its receipt's attempts (or
    None for a session with no receipt at all). A legacy chain file — or a
    receipt carrying no anchor entry — is treated as healthy: immutable, never
    retro-replaced (rule 4)."""
    anchor = _stored_state_entry(attempts)
    return (anchor or {}).get("health") or "healthy"


def _carry_forward(entry: dict | None) -> dict | None:
    """Reuse a prior write's census numbers for a SKIP attempt's receipt row, so a
    reader scanning the attempts list sees a continuous picture of the store
    instead of a gap on every no-op run. m10: aborted_early/failure_examples
    ride along too, not just failure_reasons."""
    if entry is None:
        return None
    return {
        "requested_underlyings": entry.get("requested_underlyings"),
        "attempted_underlyings": entry.get("attempted_underlyings"),
        "successful_underlyings": entry.get("successful_underlyings"),
        "coverage_pct": entry.get("coverage_pct"),
        "failure_reasons": entry.get("failure_reasons") or {},
        "failure_examples": entry.get("failure_examples") or {},
        "aborted_early": entry.get("aborted_early", False),
    }


def _health_verdict(coverage_pct: float, captured_rows: int) -> str:
    """healthy: coverage_pct >= SOURCE_HEALTH_FLOOR. partial: rows were captured
    but coverage sits under the floor. failed: zero rows captured — an
    all-symbol failure, which must never again be reasonless."""
    if captured_rows <= 0:
        return "failed"
    return "healthy" if coverage_pct >= SOURCE_HEALTH_FLOOR else "partial"


def _coerce_unknown_reasons(census: dict) -> dict:
    """m14: any failure_reasons/failure_examples key OUTSIDE the frozen
    REASON_CODES set (collectors.polygon_options) is folded into other_failure
    rather than propagated verbatim, so a future typo'd or novel reason string
    can never silently bypass the closed reason taxonomy this whole system is
    built on. Logged, not silent — an unknown code is itself worth knowing about."""
    reasons = dict(census.get("failure_reasons") or {})
    examples = {k: list(v) for k, v in (census.get("failure_examples") or {}).items()}
    unknown = sorted(k for k in reasons if k not in REASON_CODES)
    if unknown:
        log.warning("polygon: unknown failure reason code(s) %s coerced to "
                    "other_failure", unknown)
        for k in unknown:
            reasons["other_failure"] = reasons.get("other_failure", 0) + reasons.pop(k)
        for k in [k for k in examples if k not in REASON_CODES]:
            bucket = examples.setdefault("other_failure", [])
            for sym in examples.pop(k):
                if len(bucket) < 3:
                    bucket.append(sym)
    out = dict(census)
    out["failure_reasons"] = reasons
    out["failure_examples"] = examples
    return out


def _append_health_attempt(session: date, *, decision: str, health: str,
                           census: dict | None, now: datetime,
                           extra: dict | None = None) -> None:
    """Append one attempt entry to the session's health-receipt sidecar
    (data/polygon_gex_health/<session>.json — see _health_dir()'s docstring for
    why this is not the nested data/polygon_gex/health/ path). Called on EVERY
    accrual that reaches a real trading session — including no-op skips — so a
    session's health history is never reasonless. NEVER mutates the chain
    parquet; this is a sidecar only. Reads through _read_receipt/
    _recover_corrupt_receipt so an append can never itself be the write that
    silently papers over a corrupt file."""
    try:
        attempts = list(_read_receipt(session) or [])
    except _CorruptReceipt as e:
        attempts = _recover_corrupt_receipt(session, e, now)
    attempts.append({
        "capture_instant": now.isoformat(),
        "requested_underlyings": (census or {}).get("requested_underlyings"),
        "attempted_underlyings": (census or {}).get("attempted_underlyings"),
        "successful_underlyings": (census or {}).get("successful_underlyings"),
        "coverage_pct": (census or {}).get("coverage_pct"),
        "failure_reasons": (census or {}).get("failure_reasons") or {},
        # m10: persisted alongside failure_reasons, not just carried in the
        # in-memory census.
        "failure_examples": (census or {}).get("failure_examples") or {},
        "aborted_early": (census or {}).get("aborted_early", False),
        "decision": decision,
        "health": health,
        **(extra or {}),
    })
    _write_receipt_attempts(session, attempts)


def _et_calendar_date(instant: datetime) -> date:
    """The RAW ET calendar date of `instant` — deliberately NO weekend/holiday
    rollback (unlike nyse_calendar.session_date()). M7's same-day vintage guard
    needs the literal calendar date: a Saturday capture must NOT count as "the
    same day" as the Friday session it resolves to, or every weekend catch-up
    run would look like a legitimate same-day recapture window."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(nyse_calendar.ET).date()


def _drop_orphan_summary_rows(session: date, symbols: set[str]) -> None:
    """M8 (AD-1C0 review): when a REPLACED capture (replaced_partial, or a
    --force over an existing file) drops symbols the OLD vintage had, their
    summary_<SYM>.parquet must not keep a stale row at this session — that row
    would silently go on describing a chain snapshot the just-overwritten,
    single-vintage data/polygon_gex/chains/<session>.parquet no longer
    contains. Read-modify-write per symbol; a symbol with no summary file, or
    none with this session's row, is a no-op. Uses store._path — the SAME
    sanitized path store.upsert() writes to, so a symbol with special
    characters in its ticker never desyncs the read/write path."""
    if not symbols:
        return
    ts = pd.Timestamp(session)
    for sym in sorted(symbols):
        name = f"summary_{sym}"
        df = store.read(GROUP, name)
        if df is None or df.empty or ts not in df.index:
            continue
        out = df.drop(index=ts)
        p = store._path(GROUP, name)  # noqa: SLF001 — same path upsert() itself uses
        if out.empty:
            p.unlink(missing_ok=True)
        else:
            out.to_parquet(p)
        log.info("polygon: dropped orphaned summary row %s @ %s (discarded "
                 "vintage — symbol absent from the replacement capture)", sym, session)


def _store_shrink_reference(chains_dir: Path, health_dir: Path, asof: date) -> int | None:
    """The shrink tripwire's reference count, or None when there is nothing at
    all to compare against (a fresh environment — the tripwire stays silent).

    N2 ruling (AD-1C0 round 2): receipt-AWARE. A prior night that only
    captured a PARTIAL chain (say 20 of a 375-name universe) disarms a
    parquet-only reference — the next night's anchors-only collapse (10) would
    read as 20 >= 3x10=30? FALSE, silently passing. But that partial night's
    own health receipt still remembers what was actually REQUESTED that night
    (375), which is the true signal of how big the universe used to be. The
    reference is therefore max(the most recent PRIOR session's stored chain's
    captured underlying count, the most recent PRIOR session's receipt's
    largest recorded requested_underlyings) — independently found (they need
    not be the same session). Legacy sessions with a chain but no receipt fall
    back to the captured count alone (unchanged prior behavior). 'Prior' is
    strictly-before `asof` (a lexical compare on the ISO stem is exact for
    YYYY-MM-DD filenames): this must never compare the session accrue() is
    CURRENTLY processing against itself."""
    asof_iso = asof.isoformat()
    candidates: list[int] = []

    prior_chains = sorted(p for p in chains_dir.glob("*.parquet") if p.stem < asof_iso)
    if prior_chains:
        latest_chain = prior_chains[-1]
        try:
            df = pd.read_parquet(latest_chain, columns=["underlying"])
            candidates.append(int(df["underlying"].nunique()))
        except Exception as e:  # noqa: BLE001 — a reference read must never crash the run
            log.warning("polygon: could not read %s for the store-shrink "
                        "tripwire reference: %s", latest_chain.name, e)

    prior_receipts = sorted(p for p in health_dir.glob("*.json") if p.stem < asof_iso)
    if prior_receipts:
        latest_receipt = prior_receipts[-1]
        try:
            data = json.loads(latest_receipt.read_text())
            attempts = data.get("attempts") if isinstance(data, dict) else None
            if isinstance(attempts, list):
                reqs = [a.get("requested_underlyings") for a in attempts
                       if isinstance(a.get("requested_underlyings"), int)]
                if reqs:
                    candidates.append(max(reqs))
        except (OSError, ValueError) as e:
            log.warning("polygon: could not read %s for the store-shrink "
                        "tripwire receipt reference: %s", latest_receipt.name, e)

    return max(candidates) if candidates else None


def _compact(raw: pd.DataFrame) -> pd.DataFrame:
    """Shrink the daily raw file (it commits every run): float32 numerics + a
    categorical underlying ~halve it with no analytical cost (float32's ~16M-int
    precision covers any OI)."""
    out = raw.copy()
    for c in ("K", "T", "oi", "iv", "gamma", "delta", "volume", "spot"):
        if c in out.columns:
            out[c] = out[c].astype("float32")
    out["underlying"] = out["underlying"].astype("category")
    return out


def _summarize(raw: pd.DataFrame, sym: str, cfg: dict) -> pd.DataFrame | None:
    """compute_gex over one underlying's stored chain -> 1-row/day summary frame.
    Returns None when the chain has no iv-bearing strikes to trust."""
    sub = raw[raw["underlying"] == sym].dropna(subset=["iv"])
    if sub.empty:
        return None
    spot = float(sub["spot"].iloc[0])
    gx = cfg["gex"]
    ecfg = {k: gx[k] for k in ("contract_multiplier", "pct_move",
                               "strike_window_pct", "max_expiry_days") if k in gx}
    ecfg["r"] = gx.get("r", 0.043)
    ecfg["q"] = (cfg.get("div_yield") or {}).get(sym, 0.0)
    summ = compute_gex(sub[["K", "T", "iv", "oi", "is_call", "expiry"]], spot, ecfg, symbol=sym)
    asof = pd.Timestamp(sub["asof"].iloc[0]).normalize()
    return pd.DataFrame({k: [summ.get(k)] for k in SUMMARY_KEYS}, index=[asof])


def accrue(as_of=None, *, force: bool = False, _now: datetime | None = None) -> dict:
    """Snapshot + persist one SESSION. Returns a small status dict (logging/tests).

    `_now` is a private testing hook (the accrual INSTANT used for the health
    receipt's capture_instant and M7's same-day vintage check) — defaults to the
    real clock; production callers never pass it.
    """
    now = _now or datetime.now(timezone.utc)
    cfg = config.load().get("polygon")
    if not cfg:
        log.info("polygon: no config section — skip")
        return {"status": "no_config"}
    client = PolygonOptions()
    if not client.enabled():
        log.info("polygon: POLYGON_API_KEY absent — skip (no-op)")
        return {"status": "no_key"}

    asof = _resolve_session(as_of)
    from engine.options_universe import baskets_universe, gex_symbols
    gx_cfg = cfg.get("gex") or {}
    symbols = gex_symbols(gx_cfg)
    log.info("polygon: snapshotting %d underlyings for session %s "
             "(%d anchors + baskets=%s)", len(symbols), asof,
             len(gx_cfg.get("symbols") or []), gx_cfg.get("include_baskets", False))
    # WRITE-SIDE SESSION GATE (M7 2026-07-29; re-scoped 2026-08-06). `asof` is now the
    # SESSION the snapshot describes (see _resolve_session), not the UTC run date, so on
    # the datetime path — every scheduled run — this gate is ALWAYS TRUE and never fires.
    # That is the point: it used to reject Saturday/Sunday UTC, i.e. the Friday-evening
    # and weekend ET runs, and session 2026-07-31 was permanently lost to it. What still
    # routes through here is the EXPLICIT `--date`/test path, where a caller can name a
    # day the market never opened; that is a caller error and is still refused.
    if not nyse_calendar.is_session(asof):
        # Bare line-start print (never a logger — see tests/test_gh_annotation_line_start).
        print(f"::notice title=polygon-session-gate::{asof} is not an NYSE session - "
              f"chain snapshot and summaries skipped, store left unadvanced", flush=True)
        log.info("polygon: %s is not a trading session — nothing accrued", asof)
        return {"status": "non_session", "date": asof.isoformat(),
                "session": asof.isoformat()}

    # FIRST-WRITER QUALITY RULE (2026-08-19, AD-1C0 — supersedes the plain
    # 2026-08-06 first-writer-wins guard). Session stamping means several runs
    # resolve to the SAME session: the Friday evening run, then Saturday's,
    # Sunday's, and Monday's pre-open one all describe Friday. A stored HEALTHY
    # session (>=SOURCE_HEALTH_FLOOR coverage) is IMMUTABLE — checked here, BEFORE
    # the fetch, so a repeat run of an already-good session still spends no API
    # quota, same as before. A stored PARTIAL session is the one case that needs a
    # fetch before deciding: only a STRICTLY better capture may replace it (see the
    # decision block below), so control falls through instead of returning here. A
    # LEGACY chain file with no receipt at all is treated as healthy (immutable) —
    # it predates this sidecar and must never be retro-replaced. `--force` keeps
    # full override semantics regardless of any of the above. A CORRUPT receipt
    # (B3) is recovered — preserved aside, never destroyed — and its recovery
    # entry is itself immutable/unknown, never a silent fallback to "healthy".
    path = _chains_dir() / f"{asof.isoformat()}.parquet"
    existed_before = path.exists()
    stored_attempts: list[dict] | None = None
    stored_last: dict | None = None
    stored_health: str | None = None
    if path.exists() and not force:
        try:
            stored_attempts = _read_receipt(asof)
        except _CorruptReceipt as e:
            stored_attempts = _recover_corrupt_receipt(asof, e, now)
        stored_last = _stored_state_entry(stored_attempts)
        stored_health = _stored_health(stored_attempts)
        if stored_health != "partial":
            print(f"::notice title=polygon-session-present::session {asof} already stored - "
                  f"keeping the first (closest-to-close) snapshot, skipping this run "
                  f"(pass --force to overwrite)", flush=True)
            log.info("polygon: session %s already stored — no-op (first writer wins)", asof)
            _append_health_attempt(asof, decision="skipped_already_healthy",
                                   health=stored_health, census=_carry_forward(stored_last),
                                   now=now)
            return {"status": "already_present", "date": asof.isoformat(),
                    "session": asof.isoformat(), "path": str(path)}
        log.info("polygon: session %s stored capture is PARTIAL (below the %.0f%% floor) "
                 "— re-fetching to check for a strictly-better replacement",
                 asof, SOURCE_HEALTH_FLOOR * 100)

    # N1 ruling (AD-1C0 round 2): --force bypasses BOTH universe gates below —
    # a forced diagnostic run is the operator explicitly overriding the
    # quality machinery, and the gates would otherwise be an unremovable wedge
    # under exactly the condition force exists to escape. The resulting write
    # still lands as decision "forced" (see below), which is itself the
    # receipt's record that a bypass happened.
    if not force:
        # B2 ruling (AD-1C0 review): fail CLOSED on a degraded universe. When
        # config expects baskets (`include_baskets: true`) but the membership
        # file resolves to ZERO members, the universe silently collapses from
        # ~300+ names down to just the config anchors. Without this gate that
        # shrunken capture reports 100% COVERAGE against its own (wrong)
        # denominator, is graded "healthy", and becomes IMMUTABLE forever
        # under rule 1 — freezing the store at a handful of ETFs even after
        # the membership file comes back. Refuse to fetch or write at all.
        #
        # Scoped to membership_path.exists(): the file EXISTS but resolved to
        # zero members (corrupted/truncated content, or every member marked
        # removed) — not merely ABSENT. In production the file is a
        # committed, nightly-maintained artifact, so "exists but empty" is
        # the realistic incident shape (a bad write), while "absent" is the
        # ordinary state of any environment (dev, CI, a fresh worktree) that
        # has simply never run the basket-membership builder —
        # engine.options_universe's own contract calls a missing file a
        # graceful degradation, not an incident, and gating on it
        # unconditionally would refuse to accrue in every such environment.
        membership_path = config.data_dir() / "baskets" / "membership.json"
        membership_degraded = (gx_cfg.get("include_baskets", False)
                               and membership_path.exists() and not baskets_universe())

        # B2 ADDENDUM (coordinator ruling, 2026-08-19): the membership-file
        # check above is deliberately blind to the file being simply ABSENT
        # — that is the ordinary state of a fresh/dev/CI environment (see the
        # comment above), so gating on absence would fight the pinned
        # graceful-degradation contract. But that same exemption is exactly
        # the reviewer's real attack path: a degraded/sparse/husk checkout
        # with NO membership file at all would sail through the check above
        # and silently accrue an anchors-only capture graded "healthy" at
        # 100% of its own shrunken denominator. The STORE ITSELF is the only
        # self-contained witness available here that the universe used to be
        # materially bigger: if the reference (see _store_shrink_reference —
        # N2-amended to also consider a prior night's receipt-recorded
        # requested_underlyings, not just its captured chain) is >=
        # STORE_SHRINK_FACTOR times the CURRENTLY resolved universe, treat it
        # exactly like the membership-file check — refuse to fetch or write.
        # A fresh environment with no stored chains/receipts has no reference
        # and proceeds normally, which is what keeps every pinned unowned
        # fixture (whose stored chains carry a single underlying — reference
        # 1, never >= 3xN) untouched.
        #
        # N1 ruling: scoped to include_baskets=TRUE only. Baskets OFF is the
        # operator's DECLARED anchors-only intent (a documented config
        # revert), never a silent collapse — checking the shrink tripwire
        # against it turned a legitimate `include_baskets: false` revert into
        # a PERMANENT WEDGE (a large historical chain on disk would forever
        # outsize the now-intentionally-smaller anchors-only universe).
        store_shrink_ref = None
        if gx_cfg.get("include_baskets", False):
            store_shrink_ref = _store_shrink_reference(_chains_dir(), _health_dir(), asof)
        store_shrunk = (store_shrink_ref is not None
                        and store_shrink_ref >= STORE_SHRINK_FACTOR * len(symbols))

        if membership_degraded or store_shrunk:
            reason_detail = (
                "include_baskets is true but the basket membership universe "
                "resolved to ZERO members" if membership_degraded else
                f"the most recent prior reference had {store_shrink_ref} "
                f"underlyings — >= {STORE_SHRINK_FACTOR}x the {len(symbols)} "
                f"currently resolved — the universe likely collapsed")
            census = _coerce_unknown_reasons({
                "requested_underlyings": len(symbols), "attempted_underlyings": 0,
                "successful_underlyings": 0, "coverage_pct": 0.0,
                "failure_reasons": {"universe_resolution_failed": 1},
                "failure_examples": {}, "aborted_early": True,
            })
            print(f"::warning title=polygon-universe-degraded::session {asof}: "
                  f"{reason_detail} — refusing to fetch/write against a collapsed "
                  f"universe ({len(symbols)} names)", flush=True)
            log.warning("polygon: universe resolution failed for %s (%s)", asof, census)
            _append_health_attempt(asof, decision="nothing_captured", health="failed",
                                   census=census, now=now)
            return {"status": "failed", "date": asof.isoformat(), "session": asof.isoformat(),
                    "health": "failed", "census": census}

    result = client.snapshot(symbols, asof)
    # New contract: snapshot() returns (raw_df, census), and requested_underlyings
    # is ALWAYS the current gex_symbols() resolution (never hard-coded). A legacy/
    # test double may still return a bare DataFrame (the pre-AD-1C0 contract): it
    # cannot report a true attempt/failure census against the full universe, so
    # rather than inventing a bogus PARTIAL verdict against symbols it never even
    # tried, treat whatever it returned as complete — this is exactly the old
    # first-writer-wins semantics, preserved for any caller not yet upgraded to
    # the (raw, census) contract. m17: anything else (None, a list, a string...)
    # is a hard programming error, not a shape to silently paper over.
    if isinstance(result, tuple):
        raw, census = result
        census = dict(census)
        census["requested_underlyings"] = len(symbols)
    elif isinstance(result, pd.DataFrame):
        raw = result
        successful = (int(raw["underlying"].nunique())
                     if not raw.empty and "underlying" in raw.columns else 0)
        census = {
            "attempted_underlyings": successful, "successful_underlyings": successful,
            "requested_underlyings": successful,
            "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        }
    else:
        raise TypeError(
            f"PolygonOptions.snapshot() returned {type(result).__name__!r}; expected "
            f"(DataFrame, census) or a bare DataFrame (legacy)")
    census = _coerce_unknown_reasons(census)
    census["coverage_pct"] = (round(census["successful_underlyings"]
                                    / census["requested_underlyings"], 4)
                              if census["requested_underlyings"] else 0.0)

    if raw.empty:
        # Zero-capture runs keep status "empty" for consumer compat, but now carry
        # health "failed" plus the full census — an all-symbol failure can never
        # again be reasonless. Nothing is written; a stored partial (if any) is
        # untouched. m13: the receipt decision is "nothing_captured" (never
        # "skipped_not_better", which is reserved for a real comparison against a
        # stored capture that this attempt failed to beat).
        health = _health_verdict(census["coverage_pct"], 0)
        log.warning("polygon: snapshot empty — nothing accrued (%s)", census)
        _append_health_attempt(asof, decision="nothing_captured", health=health,
                               census=census, now=now)
        return {"status": "empty", "date": asof.isoformat(), "session": asof.isoformat(),
                "health": health, "census": census}

    health = _health_verdict(census["coverage_pct"], len(raw))
    if force:
        decision = "forced"
    elif stored_health != "partial":
        # No prior file existed (stored_health is None here — the branch above
        # already returned for every case where a file existed and was immutable).
        decision = "wrote"
    else:
        stored_successful = (stored_last or {}).get("successful_underlyings") or 0
        stored_coverage = (stored_last or {}).get("coverage_pct") or 0.0
        strictly_better = (census["successful_underlyings"] > stored_successful
                           and (health == "healthy"
                                or census["coverage_pct"] - stored_coverage >= 0.10))
        if not strictly_better:
            decision = "skipped_not_better"
        elif _et_calendar_date(now) != asof:
            # M7 ruling: a partial may be replaced ONLY inside the SAME-DAY
            # capture window — the new capture_instant's ET calendar date must
            # equal the session it is replacing. Saturday/Sunday/Monday-preopen
            # runs all resolve to Friday's session but are NOT Friday; without
            # this, a stale weekend re-run could keep "improving" a session days
            # after its real capture window closed. The attempt is still
            # recorded (skipped_wrong_day), never silently dropped.
            decision = "skipped_wrong_day"
        else:
            decision = "replaced_partial"

    if decision in ("skipped_not_better", "skipped_wrong_day"):
        log.info("polygon: session %s new capture (%d ok, %.1f%% coverage) was not "
                 "applied (%s) — keeping the existing file",
                 asof, census["successful_underlyings"], census["coverage_pct"] * 100,
                 decision)
        _append_health_attempt(asof, decision=decision, health=stored_health,
                               census=census, now=now)
        return {"status": "already_present", "date": asof.isoformat(), "session": asof.isoformat(),
                "path": str(path), "health": stored_health, "census": census}

    # M8 (AD-1C0 review): capture the OLD vintage's symbol set BEFORE the
    # overwrite below, so a replacement (replaced_partial, or --force over an
    # existing file) can clean up any summary_<SYM>.parquet rows whose symbol is
    # not in the NEW capture — otherwise those rows silently keep describing a
    # chain snapshot the single-vintage overwrite below just erased.
    old_symbols: set[str] = set()
    if existed_before and decision in ("replaced_partial", "forced"):
        try:
            old_chain = pd.read_parquet(path)
            old_symbols = set(map(str, old_chain["underlying"].unique()))
        except Exception as e:  # noqa: BLE001 — cleanup must never block the write
            log.warning("polygon: could not read prior chain %s for orphan-summary "
                        "cleanup: %s", path.name, e)

    # B3 trigger-2 ruling (AD-1C0 round 2) — WRITE-AHEAD receipt entry, BEFORE
    # to_parquet: a "write_pending" attempt carrying the FULL census and the
    # health THIS write is about to produce. Two crash windows this closes:
    #   * crash between THIS append and the parquet write below: path never
    #     gets created, so path.exists() is False on the next run and the
    #     immutable-skip gate above never even executes — proceeds to a fresh
    #     write untouched by this entry (nothing to disarm).
    #   * crash AFTER the parquet write but BEFORE the FINAL decision entry
    #     at the bottom of this function: the receipt's trailing entry is
    #     this "write_pending" one, but the parquet IS on disk.
    #     _stored_state_entry now recognizes a trailing write_pending as an
    #     anchor — "the capture self-describes" — so the next run reads THIS
    #     entry's health (a 40% capture stays "partial", never a silent
    #     fallback to "healthy") instead of skipping past it to legacy-healthy.
    _append_health_attempt(asof, decision="write_pending", health=health,
                           census=census, now=now)

    # 1. raw per-strike chain, session-partitioned (append-only, git-friendly).
    # `decision` is one of wrote/replaced_partial/forced here — a single-vintage
    # overwrite either way, never a merge of captures.
    _compact(raw).to_parquet(path)
    log.info("polygon: wrote raw chain %s (%d rows, %d underlyings) decision=%s health=%s",
             path.name, len(raw), raw["underlying"].nunique(), decision, health)

    if old_symbols:
        new_symbols = set(map(str, raw["underlying"].unique()))
        _drop_orphan_summary_rows(asof, old_symbols - new_symbols)

    # 2. per-underlying compute_gex summary (reuse the engine — no new math)
    n_summ = 0
    for sym in symbols:
        try:
            row = _summarize(raw, sym, cfg)
            if row is not None:
                store.upsert(GROUP, f"summary_{sym}", row, outlier_col=None)
                n_summ += 1
        except Exception as e:  # noqa: BLE001 — one symbol must not abort the rest
            log.warning("polygon summary %s failed: %s", sym, e)

    _append_health_attempt(asof, decision=decision, health=health, census=census, now=now)
    return {"status": "ok", "rows": int(len(raw)),
            "underlyings": int(raw["underlying"].nunique()),
            "summaries": n_summ, "date": asof.isoformat(),
            "session": asof.isoformat(), "health": health, "census": census}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="",
                    help="YYYY-MM-DD SESSION to store (default: the session the current "
                         "instant describes, per nyse_calendar.expected_last_session)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an already-stored session (default: first writer wins)")
    args = ap.parse_args()
    asof = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    log.info("polygon accrual: %s", accrue(asof, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
