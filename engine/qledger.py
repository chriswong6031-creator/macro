"""engine/qledger.py — the Universal Scoreboard (§2.2 of
research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md).

The ONE claims+grades substrate every scored number must pass through. It
generalises three ledger patterns already in the tree:
  * data/altdata/theses.jsonl rows — PIT `entry_levels {subject, bench}`,
    an engine-derived `falsifier`, `check_by`, `status`.
  * engine/radar_ic.py post-#904 — per-horizon grading, `horizon_d`-stamped
    snapshots, forward relative-return vs a benchmark.
  * engine/ai_desk.py — the price layer (`_close_series` with the S&P-1500
    breadth-cache fallback, `_level_asof`) and proxy-vs-bench scoring.

This module is the W1 CONTRACT the four W1 builders map their existing ledgers
onto by *adapter* — it does not itself write adapters, the nightly runner, or UI
(those are builder/W1-runner scope). It owns:
  * the CLAIM schema + `register()` validation (§2.2, D4, [P2]).
  * the GRADE model — multi-horizon [5,21,63] capped by the claim's horizon_d,
    matched-control excess, per-timestamp_quality embargo ([P2]).
  * the TRACK-RECORD emit — per-desk / per-claim-family, honest `n_dates`
    (independent date clusters, [P1]/§5), Wilson-CI lower bound, and the
    UNGRADED / ACCRUING / GRADED state chip the UI reads (D10).
  * the placebo-tape schema slot (`is_placebo`, D3) so B3's sampler just calls
    `register()`.

Price helpers are REUSED, never reinvented — the same parquet layer the whole
suite grades on.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

# Reuse the exact price layer the rest of the suite grades on. `_close_series`
# has the breadth-cache fallback so subjects beyond the ~153 yahoo parquets are
# still scorable; `_level_asof`/`close_at`/`covers` share it.
from engine.ai_desk import _GICS_ETF, _level_asof
from engine import ai_desk as _aidesk  # module ref: tests monkeypatch ai_desk._close_series
from engine.ai_desk_scorer import _close_at, _covers
from lib import config

log = logging.getLogger("qledger")


def _json_default(o: Any):
    """json.dumps `default=` for the claim/grade store.

    qledger is the serialization boundary for dicts assembled by many desks and
    stamped here with the US regime_vector (read from a parquet). A parquet read
    yields numpy scalars (np.int64/float64/bool_), which json.dumps cannot
    serialize natively — a single leaked np.int64 raised TypeError and, under a
    broad except in a caller, silently zeroed a whole batch of claims. Every
    claim-write routes through this so no numpy scalar can ever break the ledger.
    """
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    item = getattr(o, "item", None)   # numpy scalar → native python
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return str(o)


# --------------------------------------------------------------------------- #
# store layout
# --------------------------------------------------------------------------- #
_CLAIMS_FILE = ("data", "qledger", "claims.jsonl")
_GRADES_FILE = ("data", "qledger", "grades.jsonl")
_TRACK_FILE = ("site", "qledger", "track_record.json")

# --------------------------------------------------------------------------- #
# frozen enums (the contract — builders MUST use these literals)
# --------------------------------------------------------------------------- #
SCOPE_TYPES = ("entity", "basket", "sector", "macro")
DIRECTIONS = (-1, 0, 1)                     # 0 == salience-only (§2.3, D5)

# The grading clock. Every claim grades at each horizon in GRADE_HORIZONS that is
# ≤ its own horizon_d (D2 — "grade every open claim at 5/21/63d simultaneously").
GRADE_HORIZONS = (5, 21, 63)

# timestamp_quality enum + embargo, verbatim from [P2] / §2.2. `embargo` is the
# minimum delay applied to the entry anchor before a claim is gradeable; the
# special cases (EVENT_DATE / SNAPSHOT_DATE / CORRUPTED) are handled in
# `_embargo_ok` rather than as a timedelta.
_DEFAULT_BENCH = "SPY"

TIMESTAMP_QUALITY = {
    # name              -> (embargo_minutes, gradeable, note)
    "CRAWL_BOUNDED":   (0,        True,  "crawl time bounds the event; no embargo"),
    "PUBLISHER_STATED": (15,      True,  "publisher pubDate; +15min (reject pubDate < crawl-48h upstream)"),
    "DISCLOSURE_DATE": (1440,     True,  "regulatory disclosure; +1 business day"),
    "EVENT_DATE":      (0,        False, "event date is NOT a valid entry anchor"),
    "SNAPSHOT_DATE":   (0,        False, "point-in-time snapshot; display-only"),
    "CORRUPTED":       (0,        False, "corrupted timestamp; blocked + alert"),
}

# claim lifecycle status
STATUS_OPEN = "open"
STATUS_GRADED = "graded"       # all in-scope horizons matured
STATUS_REJECTED = "rejected"   # failed registration validation (kept for audit)

# track-record state chips (D10 / spec D10, "the chip states the UI reads")
STATE_UNGRADED = "UNGRADED"    # n_dates == 0
STATE_ACCRUING = "ACCRUING"    # 0 < n_dates < GRADED_MIN_DATES
STATE_GRADED = "GRADED"        # n_dates >= GRADED_MIN_DATES
GRADED_MIN_DATES = 25          # §3: n_graded >= 25 DATES (not overlapping obs)


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(root: Path | str | None) -> Path:
    return Path(root) if root else config.ROOT


def _claim_id(desk: str, asof: str, scope_key: str, horizon_d: int,
              direction: int, salt: str = "") -> str:
    """Deterministic, collision-resistant id. Stable across re-registration of
    the same logical claim so adapters are idempotent (like radar's snapshot_key
    and altdata's `{asof}-{ticker}-altconv`)."""
    raw = f"{desk}|{asof}|{scope_key}|{horizon_d}|{direction}|{salt}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def body_hash(body: str) -> str:
    """sha256 of a text body — the `source_id` convention shared with
    qual_extraction.v1 (§2.4) and the Missing-Tape body-hash leg (D8). Exposed
    here so desks stamp a stable id without importing the extraction lane."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def in_scope_horizons(horizon_d: int) -> list[int]:
    """The horizons a claim of this horizon_d grades at: every GRADE_HORIZON
    ≤ horizon_d, and always at least the claim's own horizon (so a horizon_d < 5
    claim still grades once, at its own clock)."""
    hs = [h for h in GRADE_HORIZONS if h <= horizon_d]
    if not hs:
        hs = [horizon_d]
    return hs


# --------------------------------------------------------------------------- #
# benchmark / control resolution
# --------------------------------------------------------------------------- #
def default_bench_for(scope_type: str, scope_key: str) -> str:
    """The benchmark a scope grades against when the caller does not name one.
    entity/basket/sector -> SPY; a sector scope whose key is a GICS name still
    grades vs SPY at the claim level (the sector-matched *control* is the second
    leg, resolved separately). Macro claims MUST name their own bench (D4) — this
    returns SPY only as a non-macro default."""
    return _DEFAULT_BENCH


def control_for_sector(sector_name: str | None) -> str | None:
    """Sector-matched control ETF for entity/basket/sector claims (the second
    grading leg, D4). Returns None when the sector is unknown — a null control is
    a valid, honestly-recorded state (excess-vs-control simply stays null)."""
    if not sector_name:
        return None
    return _GICS_ETF.get(sector_name)


# --------------------------------------------------------------------------- #
# CLAIM SCHEMA + registrar
# --------------------------------------------------------------------------- #
def _validate_claim(claim: dict) -> tuple[bool, str]:
    """Structural validation. Returns (ok, reason). Rejection is a first-class
    outcome — register() records rejected claims with status='rejected' so the
    fraction going dark under D4 is itself logged (D4: "the fraction that goes
    dark under this constraint is itself logged and reported")."""
    if not isinstance(claim, dict):
        return False, "claim is not an object"

    desk = str(claim.get("desk") or "").strip()
    if not desk:
        return False, "missing desk"

    asof = str(claim.get("asof") or "").strip()
    try:
        pd.Timestamp(asof)
    except Exception:  # noqa: BLE001
        return False, f"asof not a date: {asof!r}"

    scope = claim.get("scope")
    if not isinstance(scope, dict):
        return False, "missing scope object"
    stype = scope.get("type")
    skey = str(scope.get("key") or "").strip()
    if stype not in SCOPE_TYPES:
        return False, f"scope.type not in {SCOPE_TYPES}: {stype!r}"
    if not skey:
        return False, "missing scope.key"

    direction = claim.get("direction")
    if direction not in DIRECTIONS:
        return False, f"direction not in {DIRECTIONS}: {direction!r}"

    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        return False, "horizon_d not an int"
    if horizon_d <= 0:
        return False, f"horizon_d must be positive: {horizon_d}"

    tq = claim.get("timestamp_quality")
    if tq not in TIMESTAMP_QUALITY:
        return False, f"timestamp_quality not in enum: {tq!r}"
    if tq == "CORRUPTED":
        return False, "timestamp_quality=CORRUPTED is blocked (D2/[P2])"

    bench = str(claim.get("bench") or "").strip()

    # D4: macro claims MUST name a machine-checkable observable at registration,
    # else they are rejected. "Machine-checkable" == a bench key we can price
    # (a ticker/series in the parquet layer). We validate it is *named*; whether
    # it resolves is a data-availability question the grader reports, not a
    # registration failure — but an empty/placeholder bench is rejected here.
    if stype == "macro":
        if not bench or bench.upper() in ("SPY", "NONE", "NULL"):
            return False, ("macro claim must name a machine-checkable observable "
                           "as `bench` (a rate/FX/breadth series) — D4")

    entry = claim.get("entry_levels")
    if entry is not None and not isinstance(entry, dict):
        return False, "entry_levels must be an object or null"

    return True, ""


# W0 Stage B-e (§3.4): the US regime_vector stamp keys carried on every claim row.
# qledger is a US-lane desk/family ledger → US vector is the PRIMARY stamp
# (same convention as track_record #1139 and grade_us_board #1142).
_REGIME_STAMP_KEYS = (
    "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
    "risk_radar_state", "regime_vector_degraded", "vector_asof",
    "staleness_hours",
)


@lru_cache(maxsize=512)
def _regime_stamp_cached(asof: str) -> tuple:
    null = {k: None for k in _REGIME_STAMP_KEYS}
    if not asof:
        return tuple(null.items())
    try:
        from engine.regime_vector import get_vector_for_date  # noqa: PLC0415
        raw = get_vector_for_date(asof)
        out = {k: raw.get(k) for k in _REGIME_STAMP_KEYS}
        return tuple(out.items())
    except Exception as exc:  # noqa: BLE001
        log.debug("regime stamp lookup failed for %s: %s", asof, exc)
        return tuple(null.items())


def _regime_stamp_for_asof(asof: str) -> dict:
    """PIT US regime_vector stamp for a claim's asof date (§3.4).

    Reads ONLY the persisted daily vector (data/regime/regime_vector.parquet,
    last committed row with date ≤ asof) — never recomputes from latest-state
    sources. All-None stamp when the vector is absent or covers no such date.
    Cached per asof-date string: a 2,800-claim batch on one asof costs one
    parquet read, not 2,800.
    """
    return dict(_regime_stamp_cached(asof))


def _prepare_claim(claim: dict) -> dict:
    """Validate + stamp ONE claim into its stored form (shared by register()
    and register_batch(); extracted so batch registration is semantically
    identical to N single calls)."""
    ok, reason = _validate_claim(claim)

    scope = claim.get("scope") if isinstance(claim.get("scope"), dict) else {}
    horizon_d = 0
    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        horizon_d = 0

    cid = claim.get("claim_id") or _claim_id(
        str(claim.get("desk") or ""),
        str(claim.get("asof") or ""),
        str(scope.get("key") or ""),
        horizon_d,
        claim.get("direction") if claim.get("direction") in DIRECTIONS else 0,
        salt=str(claim.get("salt") or ""),
    )

    stored = dict(claim)
    stored["claim_id"] = cid
    stored["timestamp"] = _now_iso()
    stored["status"] = STATUS_OPEN if ok else STATUS_REJECTED
    if not ok:
        stored["reject_reason"] = reason
    stored.setdefault("is_placebo", bool(claim.get("is_placebo", False)))
    # normalise the two grading legs so the grader never guesses
    stored.setdefault("bench", default_bench_for(scope.get("type"), scope.get("key")))
    stored.setdefault("control", None)
    stored.pop("salt", None)

    # W0 Stage B-e (§3.4): US regime_vector PIT stamp at registration time.
    if stored.get("vector_asof") is None:
        stamp = _regime_stamp_for_asof(str(claim.get("asof") or ""))
        for k, v in stamp.items():
            if stored.get(k) is None:
                stored[k] = v
    # Schema consistency across the five Stage-B ledgers. Nothing in
    # data/species/registry.json binds ledger="qledger" (qualitative desk
    # ledger, desk/family granularity) → both are null today by design.
    stored.setdefault("species_id", None)
    stored.setdefault("archetype", None)
    return stored


def register(claim: dict, root: Path | str | None = None,
             *, dedupe: bool = True) -> dict:
    """Register ONE claim. Validates against the schema, stamps `claim_id`,
    `timestamp`, and `status`, then appends to data/qledger/claims.jsonl.

    Returns the stored claim dict (with `status` in {open, rejected}). Rejected
    claims ARE persisted (audit trail for the D4 dark-fraction report) but never
    graded. Registration is idempotent by claim_id when `dedupe=True`.

    The `is_placebo` slot (D3) rides through untouched — B3's sampler registers
    placebo claims via this same call.

    COST NOTE (W0 Stage B-e): the dedupe scan re-reads the whole claims file —
    O(file) PER CALL. Loop-callers must use register_batch() (one read, one
    write for the whole batch); at ~2,800 calls/day the loop pattern was
    quadratic in ledger size.
    """
    root = _root(root)
    stored = _prepare_claim(claim)
    cid = stored["claim_id"]

    p = root.joinpath(*_CLAIMS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)

    if dedupe:
        for existing in load_claims(root):
            if existing.get("claim_id") == cid:
                return existing  # idempotent — adapters re-run freely

    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stored, ensure_ascii=False, default=_json_default) + "\n")
    return stored


def register_batch(claims: Iterable[dict], root: Path | str | None = None,
                   *, dedupe: bool = True) -> list[dict]:
    """Register MANY claims with ONE store read and ONE append write
    (§5.1 sub-task 3 / §5.2 — required before any volume increase).

    Semantically identical to calling register() once per claim, including
    idempotent dedupe by claim_id (keep-FIRST: the store's existing row wins;
    within the batch, the first occurrence of a claim_id wins and later
    duplicates return that stored row).

    Per-claim error isolation: a claim whose preparation raises yields
    {"status": "error", "error": "..."} in its result slot; the rest of the
    batch still registers (a batch with one invalid claim never loses the
    valid ones — schema-invalid claims don't raise, they persist as
    status="rejected" exactly as register() does).

    Returns one stored dict per input claim, in input order.
    """
    root = _root(root)
    p = root.joinpath(*_CLAIMS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing_by_id: dict[str, dict] = {}
    if dedupe:
        for c in load_claims(root):          # ONE read for the whole batch
            existing_by_id.setdefault(str(c.get("claim_id")), c)

    results: list[dict] = []
    new_rows: list[dict] = []
    for claim in claims:
        try:
            stored = _prepare_claim(claim)
        except Exception as exc:  # noqa: BLE001 — isolate, never sink the batch
            log.warning("register_batch: claim preparation failed: %s", exc)
            results.append({"status": "error", "error": str(exc)})
            continue
        cid = stored["claim_id"]
        if dedupe and cid in existing_by_id:
            results.append(existing_by_id[cid])
            continue
        new_rows.append(stored)
        if dedupe:
            existing_by_id[cid] = stored
        results.append(stored)

    if new_rows:
        with p.open("a", encoding="utf-8") as fh:  # ONE write for the batch
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
    return results


def backfill_regime_stamps(root: Path | str | None = None) -> dict:
    """§3.4 backfill: fill missing regime stamps on existing claim rows ONLY
    from the persisted daily vector for dates it covers (PIT-safe by
    construction) — never reconstructed from latest-state sources.

    Fill-null-only (keep-FIRST): an existing non-null value is never altered.
    Atomic rewrite, and only when at least one row gained a stamp. Returns
    {n_claims, n_backfilled, n_unstamped, n_precoverage} — the nightly runner
    prints the residual unstamped count (§3.4 requires it visible).

    R-CI3 provenance law: every backfilled row receives
      regime_stamp_basis='recomputed_history'
    This MUST NOT be overwritten to 'pit_live' by query.py (the
    query.py:1094-1102 clobber guard checks _no_basis = basis is None, so
    pre-existing 'recomputed_history' values survive unchanged).
    Claims whose asof predates regime_vector.parquet coverage stay
    vector_asof=None and are counted in n_precoverage.
    """
    root = _root(root)
    p = root.joinpath(*_CLAIMS_FILE)
    claims = _read_jsonl(p)
    if not claims:
        return {"n_claims": 0, "n_backfilled": 0, "n_unstamped": 0, "n_precoverage": 0}

    # Guard: A-share and HK symbols must not receive US regime_vector rich stamps.
    _SKIP_SUFFIXES = (".SS", ".SZ", ".HK")
    n_skipped = 0
    n_precoverage = 0

    n_backfilled = 0
    for c in claims:
        if c.get("vector_asof") is None:
            scope_key = str((c.get("scope") or {}).get("key") or "")
            if any(scope_key.endswith(sfx) for sfx in _SKIP_SUFFIXES):
                n_skipped += 1
                continue
            stamp = _regime_stamp_for_asof(str(c.get("asof") or ""))
            if stamp.get("vector_asof") is not None:
                for k, v in stamp.items():
                    if c.get(k) is None:
                        c[k] = v
                # R-CI3: mark as recomputed from history, never pit_live
                # Only set if not already present (keep-FIRST rule).
                if c.get("regime_stamp_basis") is None:
                    c["regime_stamp_basis"] = "recomputed_history"
                n_backfilled += 1
            else:
                # asof predates regime_vector.parquet coverage — stays null
                n_precoverage += 1

    if n_skipped:
        log.info("backfill_regime_stamps: skipped %d A-share/HK claim(s) (.SS/.SZ/.HK)", n_skipped)
    if n_precoverage:
        log.info(
            "backfill_regime_stamps: %d claim(s) predate regime_vector coverage — vector_asof stays null",
            n_precoverage,
        )

    n_unstamped = sum(1 for c in claims if c.get("vector_asof") is None)
    if n_backfilled:
        tmp = p.with_name(p.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for c in claims:
                fh.write(json.dumps(c, ensure_ascii=False, default=_json_default) + "\n")
        tmp.replace(p)
    return {
        "n_claims": len(claims),
        "n_backfilled": n_backfilled,
        "n_unstamped": n_unstamped,
        "n_precoverage": n_precoverage,
    }


def make_claim(*, desk: str, asof: str, scope_type: str, scope_key: str,
               direction: int, horizon_d: int,
               timestamp_quality: str,
               subject_level: float | None = None,
               bench: str | None = None,
               bench_level: float | None = None,
               control: str | None = None,
               falsifier: Any = None,
               check_by: str | None = None,
               sector: str | None = None,
               is_placebo: bool = False,
               claim_family: str | None = None,
               extra: dict | None = None) -> dict:
    """Adapter helper — build a well-formed claim dict from the fields a W1
    builder already has, so desks map existing ledger rows into claims WITHOUT
    copying validation/scoring logic (§2.2 "adapter helpers").

    * `bench` defaults to the scope's default (SPY for non-macro). Macro callers
      MUST pass a named observable or register() rejects the claim (D4).
    * `control` defaults to the sector-matched ETF derived from `sector`.
    * `entry_levels` is assembled as {subject, bench} — the altdata PIT model,
      generalised (subject key == scope_key).
    * `check_by` defaults to asof + horizon_d business days (ai_desk convention).
    """
    bench = bench or default_bench_for(scope_type, scope_key)
    if control is None:
        control = control_for_sector(sector)

    entry_levels: dict[str, float] = {}
    if subject_level is not None:
        entry_levels["subject"] = round(float(subject_level), 6)
    if bench_level is not None:
        entry_levels["bench"] = round(float(bench_level), 6)

    if check_by is None:
        try:
            check_by = (pd.Timestamp(asof) +
                        pd.offsets.BusinessDay(int(horizon_d))).date().isoformat()
        except Exception:  # noqa: BLE001
            check_by = None

    claim: dict[str, Any] = {
        "desk": desk,
        "asof": asof,
        "scope": {"type": scope_type, "key": scope_key},
        "direction": direction,
        "horizon_d": int(horizon_d),
        "entry_levels": entry_levels,
        "bench": bench,
        "control": control,
        "falsifier": falsifier,
        "check_by": check_by,
        "timestamp_quality": timestamp_quality,
        "is_placebo": bool(is_placebo),
        "claim_family": claim_family or desk,
    }
    if sector:
        claim["sector"] = sector
    if extra:
        claim.update(extra)
    return claim


# --------------------------------------------------------------------------- #
# store readers
# --------------------------------------------------------------------------- #
def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def load_claims(root: Path | str | None = None) -> list[dict]:
    return _read_jsonl(_root(root).joinpath(*_CLAIMS_FILE))


def load_grades(root: Path | str | None = None) -> list[dict]:
    return _read_jsonl(_root(root).joinpath(*_GRADES_FILE))


# --------------------------------------------------------------------------- #
# forward relative return — grading fill semantics (W0 Stage B-e)
# --------------------------------------------------------------------------- #
# THE STAMPED DISCONTINUITY (§5.1 sub-task 3): before Stage B-e, _fwd_ret used
# asof-entry semantics (entry = close ON/BEFORE the claim's asof — the same-bar
# convention the measurement law bans: it flatters mean-reversion claims by
# filling at the trough close). From Stage B-e on, entry = the first close
# STRICTLY AFTER the entry date (the one-grader next-bar convention; the exit
# window is anchored at the fill so the horizon length is preserved).
#
# The convention change is a GRADE-HISTORY DISCONTINUITY and is stamped, never
# silent: every new grade row carries fill_convention="next_bar" +
# entry_fill_date; rows already in grades.jsonl lack the field and are read as
# "asof_legacy". Legacy graded values are NEVER rewritten (keep-FIRST).
# compute_track_record() reports row counts per convention.
FILL_NEXT_BAR = "next_bar"
FILL_ASOF_LEGACY = "asof_legacy"


def _fill_entry(ticker: str, root: Path,
                entry_date: str) -> tuple[float | None, pd.Timestamp | None]:
    """Next-bar fill: (entry_price, fill_ts) = first close STRICTLY AFTER
    entry_date. (None, None) when the series is absent or has no later bar."""
    try:
        s = _aidesk._close_series(ticker, root)
        if s is None or s.empty:
            return None, None
        fwd = s[s.index > pd.Timestamp(entry_date)]
        if not len(fwd):
            return None, None
        return float(fwd.iloc[0]), fwd.index[0]
    except Exception as e:  # noqa: BLE001
        log.debug("_fill_entry(%s,%s): %s", ticker, entry_date, e)
        return None, None


def _fwd_ret(ticker: str, root: Path, start_date: str, horizon_d: int,
             *, fill_convention: str = FILL_NEXT_BAR) -> float | None:
    """Total return of `ticker` over `horizon_d` calendar days.

    next_bar (default, Stage B-e): entry = first close STRICTLY AFTER
    start_date; exit = close ON/BEFORE fill+horizon_d, and only when the
    series actually covers the exit day (never grade a shortened window).

    asof_legacy: the pre-Stage-B-e math (entry = close ON/BEFORE start_date;
    exit = close ON/BEFORE start+horizon_d) — kept ONLY so tests and audits
    can reproduce how legacy grade rows were computed. No production path
    grades with it anymore.

    None when price unavailable. Returns the RAW return (excess is computed
    against bench/control at the grader level so both legs share one entry).
    """
    try:
        if fill_convention == FILL_ASOF_LEGACY:
            end_ts = (pd.Timestamp(start_date) +
                      pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
            e0 = _level_asof(ticker, root, start_date)
            e1 = _close_at(ticker, root, end_ts)
            if None in (e0, e1) or not e0:
                return None
            return round(e1 / e0 - 1.0, 6)

        e0, fill_ts = _fill_entry(ticker, root, start_date)
        if e0 is None or not e0 or fill_ts is None:
            return None
        s = _aidesk._close_series(ticker, root)
        end_ts = fill_ts + pd.Timedelta(days=horizon_d)
        if s.index.max() < end_ts:
            return None            # exit day not covered yet — not matured
        w = s[s.index <= end_ts]
        if not len(w):
            return None
        e1 = float(w.iloc[-1])
        return round(e1 / e0 - 1.0, 6)
    except Exception as e:  # noqa: BLE001
        log.debug("_fwd_ret(%s,%s,%s): %s", ticker, start_date, horizon_d, e)
        return None


def _matured(root: Path, start_date: str, horizon_d: int,
             today: date, tickers: Iterable[str]) -> bool:
    """A horizon is matured when it is old enough AND every leg's price cache
    covers the exit day (radar_ic._is_matured, generalised to N legs)."""
    try:
        snap = pd.Timestamp(start_date)
        if (pd.Timestamp(today) - snap).days < horizon_d:
            return False
        end_ts = (snap + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        return all(_covers(t, root, end_ts) for t in tickers if t)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# EMBARGO
# --------------------------------------------------------------------------- #
def _embargo_ok(claim: dict) -> tuple[bool, bool]:
    """(gradeable, embargo_applied) per timestamp_quality ([P2]).

    * CRAWL_BOUNDED   -> gradeable, no embargo.
    * PUBLISHER_STATED -> gradeable, embargo applied (+15min at entry).
    * DISCLOSURE_DATE  -> gradeable, embargo applied (+1bd at entry).
    * EVENT_DATE       -> NOT gradeable as an entry anchor (never).
    * SNAPSHOT_DATE    -> display-only, NOT graded.
    * CORRUPTED        -> blocked (never reaches here — rejected at register()).

    The actual +15min / +1bd shift is on the ENTRY ANCHOR; since qledger's entry
    is a daily close (the finest resolution the parquet layer offers), the
    +15min case cannot move the close and is recorded via `embargo_applied` for
    audit. The +1bd case shifts the effective entry date used by the grader.
    """
    tq = claim.get("timestamp_quality")
    spec = TIMESTAMP_QUALITY.get(tq)
    if spec is None:
        return False, False
    minutes, gradeable, _ = spec
    return bool(gradeable), bool(minutes > 0)


def _entry_date(claim: dict) -> str:
    """The effective entry date after embargo. DISCLOSURE_DATE shifts +1bd; all
    others anchor at asof (the +15min PUBLISHER case cannot move a daily close)."""
    asof = str(claim.get("asof"))
    if claim.get("timestamp_quality") == "DISCLOSURE_DATE":
        try:
            return (pd.Timestamp(asof) +
                    pd.offsets.BusinessDay(1)).date().isoformat()
        except Exception:  # noqa: BLE001
            return asof
    return asof


# --------------------------------------------------------------------------- #
# GRADING
# --------------------------------------------------------------------------- #
def grade_claim(claim: dict, root: Path | str | None = None,
                today: date | str | None = None) -> list[dict]:
    """Grade ONE open claim at every in-scope, matured horizon. Returns a list of
    grade rows (may be empty when nothing has matured). Pure/read-only — the
    nightly runner is what appends these; this is the contract the runner calls.

    A grade row (grades.jsonl schema):
      {claim_id, horizon_d, graded_at, subject_ret, bench_ret, control_ret,
       excess, hit, embargo_applied, fill_convention, entry_fill_date}

    W0 Stage B-e: rows grade under the next-bar fill convention and say so
    (fill_convention="next_bar" + the subject leg's entry_fill_date). Rows
    written before Stage B-e lack the field and are read as "asof_legacy";
    their graded values are never rewritten (keep-FIRST — the discontinuity
    is stamped, not silent).

    * `excess` = subject_ret - bench_ret (the primary leg).
    * `control_ret` = matched sector-control return (null when no control), for
      the second leg the promotion gate reads (excess-vs-control).
    * `hit` uses the claim direction: +1 -> excess>0; -1 -> excess<0; 0
      (salience-only) -> hit is null (salience claims grade magnitude via the
      placebo tape, not direction — §2.3/D3).
    """
    root = _root(root)
    today_dt = (today if isinstance(today, date)
                else pd.Timestamp(today).date() if today else date.today())

    gradeable, embargo_applied = _embargo_ok(claim)
    if not gradeable:
        return []

    scope = claim.get("scope") or {}
    subject = scope.get("key")
    bench = claim.get("bench") or _DEFAULT_BENCH
    control = claim.get("control")
    direction = claim.get("direction")
    start = _entry_date(claim)

    try:
        horizon_d = int(claim.get("horizon_d"))
    except Exception:  # noqa: BLE001
        return []

    rows: list[dict] = []
    for h in in_scope_horizons(horizon_d):
        legs = [subject, bench] + ([control] if control else [])
        if not _matured(root, start, h, today_dt, legs):
            continue
        subj = _fwd_ret(subject, root, start, h)
        bench_ret = _fwd_ret(bench, root, start, h)
        if subj is None or bench_ret is None:
            continue
        ctrl = _fwd_ret(control, root, start, h) if control else None
        excess = round(subj - bench_ret, 6)
        if direction == 1:
            hit: bool | None = excess > 0
        elif direction == -1:
            hit = excess < 0
        else:                       # salience-only: no directional hit
            hit = None
        _, fill_ts = _fill_entry(subject, root, start)
        rows.append({
            "claim_id": claim.get("claim_id"),
            "horizon_d": h,
            "graded_at": _now_iso(),
            "subject_ret": subj,
            "bench_ret": bench_ret,
            "control_ret": ctrl,
            "excess": excess,
            "hit": hit,
            "embargo_applied": embargo_applied,
            # W0 Stage B-e: the stamped fill convention (see module note)
            "fill_convention": FILL_NEXT_BAR,
            "entry_fill_date": (str(fill_ts.date()) if fill_ts is not None
                                else None),
        })
    return rows


# --------------------------------------------------------------------------- #
# WILSON CI + track-record aggregation
# --------------------------------------------------------------------------- #
def wilson_ci_low(hits: int, n: int, z: float = 1.96) -> float | None:
    """Lower bound of the Wilson score interval for a binomial proportion.
    None when n == 0. The promotion gate (§3) reads this lower bound vs 0.

    Wilson is used (not normal-approx) because n is small and p can be near 0/1;
    the lower bound is the honest floor the gate requires to exceed 0.
    """
    if n <= 0:
        return None
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
    return round((centre - margin) / denom, 6)


def _date_cluster(asof: str) -> str:
    """The independent-date key ([P1]/§5 overlapping-observation illusion). One
    claim's asof date is one cluster; n_dates counts DISTINCT asof dates so
    overlapping/autocorrelated obs never inflate n. This is the honest n."""
    try:
        return pd.Timestamp(asof).date().isoformat()
    except Exception:  # noqa: BLE001
        return str(asof)


def derive_state(n_dates: int) -> str:
    """UNGRADED (n_dates==0) | ACCRUING (0<n_dates<25) | GRADED (n_dates>=25).
    The chip the UI reads (D10)."""
    if n_dates <= 0:
        return STATE_UNGRADED
    if n_dates < GRADED_MIN_DATES:
        return STATE_ACCRUING
    return STATE_GRADED


def _family_key(claim: dict, by: str) -> str | None:
    if by == "desk":
        return claim.get("desk")
    if by == "family":
        return claim.get("claim_family") or claim.get("desk")
    return None


def _aggregate(claims: list[dict], grades: list[dict],
               by: str, horizon_d: int) -> dict[str, dict]:
    """Aggregate grade rows into per-group track-record stats at ONE horizon.
    `by` in {'desk','family'}. Groups exclude placebo claims from the headline
    hit-rate (placebo is the counterfactual, graded separately by B3)."""
    cid_meta = {c["claim_id"]: c for c in claims if c.get("claim_id")}

    # group -> {n_obs, hits, excess_sum, date_set}
    acc: dict[str, dict] = {}
    for g in grades:
        if int(g.get("horizon_d", -1)) != horizon_d:
            continue
        c = cid_meta.get(g.get("claim_id"))
        if c is None or c.get("is_placebo"):
            continue
        key = _family_key(c, by)
        if key is None:
            continue
        a = acc.setdefault(key, {"n_obs": 0, "hits": 0, "graded_hits": 0,
                                 "excess_sum": 0.0, "dates": set()})
        a["n_obs"] += 1
        a["excess_sum"] += float(g.get("excess") or 0.0)
        a["dates"].add(_date_cluster(c.get("asof")))
        hit = g.get("hit")
        if hit is not None:                 # directional claim contributes a hit
            a["graded_hits"] += 1
            if hit:
                a["hits"] += 1

    out: dict[str, dict] = {}
    for key, a in acc.items():
        n_obs = a["n_obs"]
        n_dates = len(a["dates"])
        gh = a["graded_hits"]
        hit_rate = round(a["hits"] / gh, 6) if gh else None
        excess_mean = round(a["excess_sum"] / n_obs, 6) if n_obs else None
        ci_low = wilson_ci_low(a["hits"], gh) if gh else None
        out[key] = {
            "n_obs": n_obs,
            "n_dates": n_dates,          # the honest n
            "hit_rate": hit_rate,
            "excess_mean": excess_mean,
            "wilson_ci_low": ci_low,
            "state": derive_state(n_dates),
        }
    return out


def _placebo_magnitude(claims: list[dict], grades: list[dict]) -> dict:
    """Compute per-horizon magnitude stats for the placebo tape (D3).

    Reports the mean |excess| across ALL placebo grades at each horizon,
    split by placebo_path ('covered_ticker' entity claims vs 'fallback_no_ticker'
    bench-basket claims). The UI's scoreboard reads this to display the
    "beat placebo" comparison.

    n_fallback is the count of sampled events that had no covered ticker and
    fell back to the bench-basket path (a diagnostic for placebo tape quality).
    """
    cid_meta = {c["claim_id"]: c for c in claims
                if c.get("claim_id") and c.get("is_placebo")}
    if not cid_meta:
        return {}

    per_h: dict[str, dict] = {}
    for g in grades:
        cid = g.get("claim_id")
        c = cid_meta.get(cid)
        if c is None:
            continue
        h = int(g.get("horizon_d", -1))
        if h < 0:
            continue
        path = str(c.get("placebo_path") or "unknown")
        exc = g.get("excess")
        if exc is None:
            continue
        bucket = per_h.setdefault(str(h), {})
        agg = bucket.setdefault(path, {"n": 0, "abs_excess_sum": 0.0})
        agg["n"] += 1
        agg["abs_excess_sum"] += abs(float(exc))

    out: dict[str, dict] = {}
    for h_str, paths in per_h.items():
        h_out: dict[str, Any] = {}
        total_n = 0
        total_abs = 0.0
        for path, agg in paths.items():
            n = agg["n"]
            mean_abs = round(agg["abs_excess_sum"] / n, 6) if n else None
            h_out[path] = {"n_grades": n, "mean_abs_excess": mean_abs}
            total_n += n
            total_abs += agg["abs_excess_sum"]
        h_out["overall"] = {
            "n_grades": total_n,
            "mean_abs_excess": round(total_abs / total_n, 6) if total_n else None,
        }
        out[h_str] = h_out

    # Fallback rate: fraction of sampled events with no covered ticker
    n_fallback_claims = sum(
        1 for c in cid_meta.values() if c.get("placebo_path") == "fallback_no_ticker"
    )
    # Claims are registered per-horizon × per-ticker; count unique events instead
    fallback_event_ids = {
        c.get("event_id") for c in cid_meta.values()
        if c.get("placebo_path") == "fallback_no_ticker"
    }
    covered_event_ids = {
        c.get("event_id") for c in cid_meta.values()
        if c.get("placebo_path") == "covered_ticker"
    }
    out["_meta"] = {
        "n_placebo_claims": len(cid_meta),
        "n_covered_events": len(covered_event_ids),
        "n_fallback_events": len(fallback_event_ids),
        "fallback_rate": (
            round(len(fallback_event_ids) /
                  (len(fallback_event_ids) + len(covered_event_ids)), 4)
            if (fallback_event_ids or covered_event_ids) else None
        ),
    }
    return out


def compute_track_record(root: Path | str | None = None) -> dict:
    """Build the track_record.json payload — per desk and per claim-family, at
    each grade horizon. Does not write; `emit_track_record` persists it. Pure so
    it is trivially testable and the nightly runner controls IO."""
    root = _root(root)
    claims = load_claims(root)
    grades = load_grades(root)

    by_desk: dict[str, dict] = {}
    by_family: dict[str, dict] = {}
    for h in GRADE_HORIZONS:
        for grp, dest in (("desk", by_desk), ("family", by_family)):
            stats = _aggregate(claims, grades, grp, h)
            for key, s in stats.items():
                dest.setdefault(key, {})[str(h)] = s

    n_placebo = sum(1 for c in claims if c.get("is_placebo"))
    n_rejected = sum(1 for c in claims if c.get("status") == STATUS_REJECTED)
    # W0 Stage B-e honesty lines: the stamped fill-convention split (rows
    # lacking the field predate the next-bar migration = asof_legacy) and the
    # §3.4 residual regime-unstamped claim count.
    conv_counts: dict[str, int] = {}
    for g in grades:
        k = str(g.get("fill_convention") or FILL_ASOF_LEGACY)
        conv_counts[k] = conv_counts.get(k, 0) + 1
    n_unstamped = sum(1 for c in claims if c.get("vector_asof") is None)
    return {
        "generated_at": _now_iso(),
        "grade_horizons": list(GRADE_HORIZONS),
        "graded_min_dates": GRADED_MIN_DATES,
        "by_desk": by_desk,
        "by_family": by_family,
        "placebo_magnitude": _placebo_magnitude(claims, grades),  # D3 counterfactual
        "counts": {
            "n_claims": len(claims),
            "n_grades": len(grades),
            "n_placebo": n_placebo,
            "n_rejected": n_rejected,     # the D4 dark-fraction numerator
            "grades_by_fill_convention": conv_counts,   # stamped discontinuity
            "n_claims_unstamped_regime": n_unstamped,   # §3.4 residual
        },
    }


def emit_track_record(root: Path | str | None = None) -> dict:
    """Compute and write site/qledger/track_record.json. Returns the payload.
    Data write precedes any render (the macro#895 class fixed architecturally,
    §2.5) — this is a data write, callers render from the file."""
    root = _root(root)
    payload = compute_track_record(root)
    p = root.joinpath(*_TRACK_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# --------------------------------------------------------------------------- #
# PROMOTION LADDER — §3 gate + auto-demote
# --------------------------------------------------------------------------- #
# Ladder rungs in order; a family can only move up one rung at a time (gate
# required at each step) and can auto-demote if the rolling CI falls below 0.
LADDER_RUNGS = ("DISPLAY", "SHADOW", "CONFIRMER", "SCORED")
_RUNG_IDX = {r: i for i, r in enumerate(LADDER_RUNGS)}

# Block-bootstrap: minimum number of distinct date clusters required to pass §3.
PROMOTION_MIN_DATES = GRADED_MIN_DATES   # 25 — same constant, aliased for clarity


class PromotionResult:
    """Outcome of a promotion_check() call.

    Attributes:
        eligible:       True if the §3 gate would permit promotion to CONFIRMER.
        reason:         Human-readable explanation of the gate result.
        n_dates:        Number of independent date clusters in the grade set.
        wilson_ci_low:  Wilson CI lower bound (None if n_dates == 0).
        current_state:  derive_state() chip value.
        demote:         True if the rolling CI has gone negative — auto-demote is warranted.
        pinned_reason:  Suggested pin reason string (mirrors narrative_regime precedent).
    """
    __slots__ = ("eligible", "reason", "n_dates", "wilson_ci_low",
                 "current_state", "demote", "pinned_reason")

    def __init__(self, eligible: bool, reason: str, n_dates: int,
                 ci_low: float | None, current_state: str,
                 demote: bool = False, pinned_reason: str = "") -> None:
        self.eligible = eligible
        self.reason = reason
        self.n_dates = n_dates
        self.wilson_ci_low = ci_low
        self.current_state = current_state
        self.demote = demote
        self.pinned_reason = pinned_reason

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reason": self.reason,
            "n_dates": self.n_dates,
            "wilson_ci_low": self.wilson_ci_low,
            "current_state": self.current_state,
            "demote": self.demote,
            "pinned_reason": self.pinned_reason,
        }


def promotion_check(claim_family: str, horizon: int,
                    root: Path | str | None = None,
                    control_only: bool = False) -> PromotionResult:
    """Evaluate the §3 promotion gate for a claim_family at a given horizon.

    §3 gate (SHADOW → CONFIRMER):
      1. n_dates >= 25 (independent date clusters, the honest n [P1])
      2. Wilson-CI lower bound of excess hit-rate vs matched control > 0 at the
         claim's horizon (not vs SPY — vs control; SPY excess is the headline,
         control excess is the gate)
      3. Rolling check: if wilson_ci_low <= 0 on the trailing window → demote.

    The block-bootstrap stability check (§3: "across date clusters") and the
    incremental-information check ("incremental over price+VIX baseline") are
    noted in the result but their implementation is deferred to the W6 composite
    validator — this function gates on the two hard numeric criteria.

    Args:
        claim_family: The `claim_family` tag (matches qledger claims.jsonl rows).
        horizon:      The horizon_d to check (typically 5, 21, or 63).
        root:         Repo root; defaults to config.ROOT.
        control_only: When True, evaluate excess vs control_ret rather than bench.
                      §3 specifies "vs matched control" as the gate leg.

    Returns:
        PromotionResult with eligible/reason/n_dates/wilson_ci_low/demote.
    """
    root = _root(root)
    claims = load_claims(root)
    grades = load_grades(root)

    # Index claims by claim_id for fast lookup
    cid_meta = {
        c["claim_id"]: c for c in claims
        if c.get("claim_id") and c.get("claim_family") == claim_family
        and not c.get("is_placebo")
    }

    if not cid_meta:
        return PromotionResult(
            eligible=False,
            reason=f"No claims found for claim_family={claim_family!r}",
            n_dates=0, ci_low=None,
            current_state=STATE_UNGRADED,
        )

    # Collect grade rows at the target horizon for this family
    hits = 0
    graded_hits = 0
    dates: set[str] = set()

    for g in grades:
        if int(g.get("horizon_d", -1)) != horizon:
            continue
        c = cid_meta.get(g.get("claim_id"))
        if c is None:
            continue
        dates.add(_date_cluster(c.get("asof", "")))

        hit = g.get("hit")
        if hit is not None:
            graded_hits += 1
            # Use control_ret leg when control_only=True; fall back to primary leg
            if control_only:
                ctrl = g.get("control_ret")
                subj = g.get("subject_ret")
                bench = g.get("bench_ret")
                if ctrl is not None and subj is not None and bench is not None:
                    # excess vs control = subject_ret - control_ret
                    ctrl_excess = subj - ctrl
                    if ctrl_excess > 0:
                        hits += 1
                elif hit:
                    hits += 1   # fall back to primary hit when control unavailable
            elif hit:
                hits += 1

    n_dates = len(dates)
    current_state = derive_state(n_dates)
    ci_low = wilson_ci_low(hits, graded_hits) if graded_hits else None

    # §3 gate criterion 1: n_dates
    if n_dates < PROMOTION_MIN_DATES:
        return PromotionResult(
            eligible=False,
            reason=(f"n_dates={n_dates} < {PROMOTION_MIN_DATES} required. "
                    f"State: {current_state}. "
                    f"Need {PROMOTION_MIN_DATES - n_dates} more independent date clusters."),
            n_dates=n_dates, ci_low=ci_low,
            current_state=current_state,
        )

    # §3 gate criterion 2: wilson_ci_low > 0
    if ci_low is None:
        return PromotionResult(
            eligible=False,
            reason=(f"n_dates={n_dates} OK but no directional hits recorded "
                    f"(graded_hits={graded_hits}) — cannot compute Wilson CI. "
                    f"Family may be salience-only (direction=0); salience families "
                    f"gate on |excess| > placebo instead."),
            n_dates=n_dates, ci_low=None,
            current_state=current_state,
        )

    # Auto-demote check: CI <= 0 on a family that was previously above the bar
    demote = ci_low <= 0.0
    pinned_reason = ""
    if demote:
        pinned_reason = (
            f"claim_family={claim_family!r} horizon={horizon}d: "
            f"rolling Wilson CI lower bound={ci_low:.4f} <= 0 at "
            f"n_dates={n_dates}. Auto-demote one rung. "
            f"Pinned as of {_now_iso()[:10]} (narrative_regime precedent)."
        )
        return PromotionResult(
            eligible=False,
            reason=f"Wilson CI lower bound {ci_low:.4f} <= 0 — AUTO-DEMOTE warranted. "
                   f"{pinned_reason}",
            n_dates=n_dates, ci_low=ci_low,
            current_state=current_state,
            demote=True, pinned_reason=pinned_reason,
        )

    # Both gates pass
    return PromotionResult(
        eligible=True,
        reason=(f"§3 gate PASS at horizon={horizon}d: "
                f"n_dates={n_dates} >= {PROMOTION_MIN_DATES}, "
                f"Wilson CI lower bound={ci_low:.4f} > 0. "
                f"Block-bootstrap stability and incremental-information checks "
                f"(price+VIX baseline) are delegated to the W6 composite validator."),
        n_dates=n_dates, ci_low=ci_low,
        current_state=current_state,
    )


def emit_ladder_states(root: Path | str | None = None,
                       families: list[str] | None = None) -> dict:
    """Run promotion_check at every GRADE_HORIZON for each claim_family found in
    claims.jsonl and emit the results into track_record.json under 'ladder_states'.

    Called by grade_qledger.py at end-of-collect so the ladder state is always
    current alongside the grade stats. Returns the per-family results dict.
    """
    root = _root(root)
    claims = load_claims(root)
    all_families = families or list({
        c.get("claim_family") or c.get("desk")
        for c in claims
        if not c.get("is_placebo") and (c.get("claim_family") or c.get("desk"))
    })

    results: dict[str, dict] = {}
    for fam in sorted(all_families):
        fam_res: dict[str, dict] = {}
        for h in GRADE_HORIZONS:
            pr = promotion_check(fam, h, root=root, control_only=True)
            fam_res[str(h)] = pr.as_dict()
        results[fam] = fam_res

    # Merge into the existing track_record if it exists, else write fresh
    tr_path = root.joinpath(*_TRACK_FILE)
    payload: dict = {}
    if tr_path.exists():
        try:
            payload = json.loads(tr_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
    payload["ladder_states"] = results
    payload["ladder_states_at"] = _now_iso()
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return results
