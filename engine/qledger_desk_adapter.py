"""engine/qledger_desk_adapter.py — desk thesis row -> Universal Scoreboard
PROSPECTIVE claim (Eval OS P3).

WHY THIS EXISTS. `engine/qledger.py` is the claims+grades substrate (the
Universal Scoreboard). Three desks already emit an engine-derived, falsifiable,
machine-checkable lean but were never registering it there:

    engine               store                             declared ruler
    engine/stock_desk.py     data/stock_desk/theses.jsonl       20 trading days
    engine/thematic_desk.py  data/thematic_desk/theses.jsonl    20 trading days
    engine/demand_ledger.py  data/demand_chain/theses.jsonl    126 trading days

This module is the TRANSLATOR + GATE between a desk's own ledger row and a
qledger claim. It is deliberately narrow:

  * DIRECTION IS NEVER INFERRED. Every desk here writes a REAL `lean` enum
    (constructive/neutral/cautious/avoid; overweight/underweight/avoid;
    outperform/underperform). Direction is a straight TABLE LOOKUP from that
    enum (`_LEAN_DIRECTION`) — never derived from a computed predicate, a
    price, or a script's own judgement (rule R4 / constitution A7 holds at
    this boundary). A lean absent from the table (stock_desk's `neutral`) is a
    declared NO-CALL and is SKIPPED, never filed as direction=0 — 71% of the
    existing qledger corpus is already direction==0/salience-only, and filing
    a desk's own explicit "I have no view" as a scored salience claim would
    grow that share with rows the desk itself refused to make a call on.

  * THE PRICEABLE LEG IS READ FROM THE ENGINE'S OWN FALSIFIER, NEVER THE
    DISPLAY LABEL. `scope_key`/`bench` are `falsifier.check.subject_ticker` /
    `.vs` — for thematic_desk that is the theme's resolved proxy ETF, never the
    unpriceable theme name. A row whose falsifier is `kind: "soft"` (no scalar
    proxy) carries no `subject_ticker` and is skipped for the same reason.

  * FORWARD-ONLY, AND THAT IS THE WHOLE POINT (CEO P3 — "the absolute
    constraint"). A prior attempt (branch `claude/eval-os-t9-adoption`, never
    merged) registered stock_desk/thematic_desk rows whose `state_asof` was
    already 1-4 completed trading sessions stale by the time the row was
    written — so the very first bar of the graded window had ALREADY PRINTED
    at registration time, i.e. the "prediction" was partly a description of a
    known past. `_outcome_not_yet_determined` is the fix: it resolves the
    claim's own window through `qledger.claim_window` (the SAME resolver
    `grade_claim` uses — one clock, reused, never reinvented) and refuses any
    claim whose fill session is not STRICTLY AFTER the registration date. A
    claim that clears this gate has NO price bar anywhere in its graded window
    yet, by construction — the outcome cannot be even partially known.

  * NO `backfilled` FLAG. The prior attempt's `backfilled=True` provenance tag
    was a decorative no-op (nothing in qledger read it, so a family built
    entirely from after-the-fact imports cleared every promotion gate exactly
    like a live-forward one — blocker B3). The fix here is not a better flag:
    it is registering NOTHING that fails the forward gate above. A rejected
    (retrospective / no-call / region-excluded) row is counted and logged, it
    is never registered under a flag that asks a future reader to remember to
    check it.

  * CALLERS PASS ONLY ROWS THEY JUST WROTE. Every call site
    (engine/stock_desk.py, engine/thematic_desk.py, engine/demand_ledger.py)
    hands this module the rows THIS run appended to its own ledger — never a
    re-read of the full committed history. A historical row already sitting in
    the store before this program existed is HISTORY; this module has no path
    that can turn it into a claim (there is no `include_backfill` switch here,
    unlike the prior attempt's adapter).

REGION SCOPE (thematic_desk only). Only `market == "us"` rows are translated.
canada/hk/china proxies have no price parquet in this repo, and the CN leg
additionally needs its own ruling against `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-
LIMIT` — both out of scope here; the census that identified the three P3
families explicitly carried this exclusion forward.

FAILURE IS LOUD AND COUNTED, NEVER SILENT. A source-collection failure
upstream of this module (the caller could not even read its own ledger) must
be told apart from "read fine, found nothing to register this run" — the first
is `source_error` (an explicit `::warning`), the second is an honest small (or
zero) `n_candidates`. A `register_batch` exception is caught, printed as a
GitHub `::error` annotation (bare `print(..., flush=True)` — never through a
logger; a prefixing log formatter would swallow the `::` prefix and the
Actions summary would show nothing, exactly the defect `tests/
test_gh_annotation_line_start.py` exists to catch), and returned in the stats
dict rather than propagated — accrual must never sink a desk's build.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable

from engine import qledger

log = logging.getLogger("qledger_desk_adapter")


# --------------------------------------------------------------------------- #
# per-family configuration — the ONLY place a family's shape is declared
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FamilyConfig:
    lean_field: str = "lean"
    #: declared lean -> direction. A lean absent from this table (a desk's own
    #: declared no-call, e.g. stock_desk's "neutral") is SKIPPED, never
    #: direction=0. Table-driven, never inferred (see module docstring).
    lean_direction: dict[str, int] = field(default_factory=dict)
    #: optional row-level gate beyond the lean table (thematic_desk's region
    #: scoping). None means every row is in scope.
    region_filter: Callable[[dict], bool] | None = None


_FAMILIES: dict[str, FamilyConfig] = {
    "stock_desk": FamilyConfig(
        lean_direction={"constructive": 1, "cautious": -1, "avoid": -1},
    ),
    "thematic_desk": FamilyConfig(
        lean_direction={"overweight": 1, "underweight": -1, "avoid": -1},
        region_filter=lambda row: str(row.get("market") or "").strip().lower() == "us",
    ),
    "demand_chain": FamilyConfig(
        lean_direction={"outperform": 1, "underperform": -1},
    ),
}


def known_families() -> tuple[str, ...]:
    return tuple(_FAMILIES)


# --------------------------------------------------------------------------- #
# translation — ONE row -> ONE claim dict, or None (never raises)
# --------------------------------------------------------------------------- #
def translate_row(row: dict, *, family: str, direction: int,
                  timestamp_quality: str,
                  sector_of: Callable[[str], str | None] | None = None) -> dict | None:
    """ONE thesis row -> ONE well-formed (unvalidated, unregistered) claim dict,
    or None when the row cannot be translated. `direction` is already resolved
    by the caller (the lean-table lookup) — this function only prices the
    engine's own falsifier leg and assembles the claim, it makes no directional
    judgement of its own.

    None (never raises) for: a non-dict row, a missing/non-dict falsifier
    check, a check with no priceable `subject_ticker`/`vs` (a `soft` predicate
    — no scalar proxy, or a declared no-call), a missing/non-positive
    `horizon_d`, a missing `state_asof`, or a missing thesis `id` (no stable
    salt is available, and an unsalted claim_id can collide with a same-day
    sibling on the same ticker — see engine/qledger.py `_claim_id`).
    """
    if not isinstance(row, dict):
        return None
    check = ((row.get("falsifier") or {}).get("check")
             if isinstance(row.get("falsifier"), dict) else None)
    if not isinstance(check, dict):
        return None
    subject = str(check.get("subject_ticker") or "").strip()
    bench = str(check.get("vs") or "").strip()
    if not subject or not bench:
        return None

    try:
        horizon_d = int(row.get("horizon_d"))
    except (TypeError, ValueError):
        return None
    if horizon_d <= 0:
        return None

    asof = str(row.get("state_asof") or row.get("asof") or "").strip()
    if not asof:
        return None

    source_id = str(row.get("id") or "").strip()
    if not source_id:
        return None

    entry = row.get("entry_levels") if isinstance(row.get("entry_levels"), dict) else {}
    subject_level = entry.get(subject)
    bench_level = entry.get(bench)

    sector = None
    if sector_of is not None:
        try:
            sector = sector_of(subject)
        except Exception:  # noqa: BLE001 — a control leg is optional, never fatal
            sector = None

    claim = qledger.make_claim(
        desk=family,
        asof=asof,
        scope_type="entity",
        scope_key=subject,
        direction=direction,
        horizon_d=horizon_d,
        timestamp_quality=timestamp_quality,
        horizon_unit=qledger.HORIZON_UNIT_TRADING,   # P3: every family declares TRADING days
        subject_level=subject_level,
        bench_level=bench_level,
        bench=bench,
        sector=sector,
        falsifier=row.get("falsifier"),
        check_by=row.get("check_by"),
        claim_family=family,
        extra={"source_id": source_id},
    )
    # Explicit salt: idempotence across re-runs AND collision safety between two
    # same-day rows on the same ticker (mirrors engine/qledger.py's own note on
    # `_claim_id`).
    claim["salt"] = source_id
    return claim


# --------------------------------------------------------------------------- #
# THE FORWARD-ONLY GATE
# --------------------------------------------------------------------------- #
REASON_RETROSPECTIVE = "retrospective_at_registration"


def outcome_not_yet_determined(claim: dict, today: date) -> tuple[bool, str]:
    """True when NO price bar in `claim`'s graded window can exist yet as of
    `today` — the CEO's forward-only test, made executable.

    Resolves the claim's window through `qledger.claim_window` — the exact
    resolver `grade_claim` itself uses (one clock, reused). A window's `hit`
    is decided by bars from `fill_date` through `exit_date`; if `fill_date`
    (the FIRST bar the window reads) is not strictly after `today`, that bar
    has already printed (or is printing today, whose close a post-close
    nightly already knows) and the outcome is no longer purely forward. Since
    `exit_date` is always >= `fill_date`, clearing this one check clears the
    entire window.

    `window is None` (market/window unresolvable — e.g. an unmapped exchange
    suffix) is NOT this gate's concern: that claim proceeds to
    `qledger.register_batch`, which refuses it through its own, already-tested
    `REJECT_CLOCK_UNRESOLVABLE` path (`_validate_claim`) — duplicating that
    logic here would be a second implementation of the same refusal.
    """
    try:
        horizon_d = int(claim.get("horizon_d"))
    except (TypeError, ValueError):
        return True, ""
    window = qledger.claim_window(claim, horizon_d)
    if window is None:
        return True, ""
    if window.fill_date <= today:
        return False, (
            f"{REASON_RETROSPECTIVE}: fill session {window.fill_date.isoformat()} is on or "
            f"before the registration date {today.isoformat()} — at least the first bar of "
            f"the graded window has already printed, so the outcome is no longer purely "
            f"forward")
    return True, ""


# --------------------------------------------------------------------------- #
# registration — translate + gate + register a batch for ONE family
# --------------------------------------------------------------------------- #
def _empty_stats(family: str, *, dry_run: bool, source_error: str | None) -> dict[str, Any]:
    return {
        "family": family, "dry_run": bool(dry_run), "source_error": source_error,
        "n_rows": 0, "n_skipped_no_call": 0, "n_region_excluded": 0,
        "n_retrospective_skipped": 0, "n_candidates": 0,
        "n_accepted": 0, "n_rejected": 0, "clock_started": False, "error": None,
    }


def register_prospective(rows: Iterable[dict], *, family: str,
                         timestamp_quality: str = "CRAWL_BOUNDED",
                         root: Path | str | None = None,
                         today: date | None = None,
                         sector_of: Callable[[str], str | None] | None = None,
                         git_sha: str | None = None,
                         dry_run: bool = False,
                         source_error: str | None = None) -> dict[str, Any]:
    """Translate + forward-gate + register ONE family's freshly-written rows.

    `rows` MUST be exactly the rows the caller's OWN ledger append just wrote
    this run — never a re-read of the full committed store (see module note).

    `source_error` — set this when the CALLER could not even collect its rows
    this run (e.g. an exception reading its own ledger). This is a DIFFERENT,
    LOUDER state than "collected fine, 0 rows to register": it short-circuits
    before any translation is attempted and emits its own `::warning`, so a
    "could not look" run is never confused with an honest zero.

    `dry_run=True` runs the EXACT same translate/gate/register_batch path
    against a throwaway temporary store (never the real `root`) so the
    reported accept/reject counts are the real registrar's own verdict, not a
    re-implementation of its rules. The temporary store is discarded when this
    call returns; nothing under `root` is touched.

    Never raises. A `register_batch` failure is caught, printed as a GitHub
    `::error` annotation, and returned in `stats["error"]` — the caller's
    build must not die over an accrual step (matches every sibling desk's
    "additive, never fatal" contract), but the failure is no longer silent
    (the prior attempt's blocker: "a total registration failure was silent
    and, for stock_desk, permanent").
    """
    stats = _empty_stats(family, dry_run=dry_run, source_error=source_error)
    if source_error:
        print(f"::warning title={family}-qledger-source-unavailable::qledger prospective "
             f"registration for {family} could not read its source rows this run "
             f"({source_error}) — this is NOT the same as 'ran and found nothing'; "
             f"nothing was attempted", flush=True)
        log.warning("qledger[%s]: source unavailable — %s", family, source_error)
        return stats

    fam_cfg = _FAMILIES.get(family)
    if fam_cfg is None:
        stats["error"] = f"unknown qledger P3 family {family!r}; known: {known_families()}"
        log.error(stats["error"])
        return stats

    today = today or datetime.now(timezone.utc).date()

    try:
        row_list = [r for r in rows]
    except Exception as exc:  # noqa: BLE001 — a bad iterable is a "could not look", not a crash
        stats["error"] = f"rows iterable raised: {exc}"
        print(f"::error title={family}-qledger-rows-error::qledger[{family}] could not "
             f"iterate its rows: {exc}", flush=True)
        log.error("qledger[%s]: rows iterable raised: %s", family, exc)
        return stats

    candidates: list[dict] = []
    for row in row_list:
        stats["n_rows"] += 1
        if not isinstance(row, dict):
            stats["n_skipped_no_call"] += 1
            continue
        if fam_cfg.region_filter is not None and not fam_cfg.region_filter(row):
            stats["n_region_excluded"] += 1
            continue
        lean = str(row.get(fam_cfg.lean_field) or "").strip().lower()
        direction = fam_cfg.lean_direction.get(lean)
        if direction is None:
            stats["n_skipped_no_call"] += 1
            continue
        claim = translate_row(row, family=family, direction=direction,
                              timestamp_quality=timestamp_quality, sector_of=sector_of)
        if claim is None:
            stats["n_skipped_no_call"] += 1
            continue
        ok, reason = outcome_not_yet_determined(claim, today)
        if not ok:
            stats["n_retrospective_skipped"] += 1
            log.info("qledger[%s]: refused claim salt=%s — %s",
                     family, claim.get("salt"), reason)
            continue
        candidates.append(claim)

    stats["n_candidates"] = len(candidates)
    if not candidates:
        if stats["n_rows"]:
            log.info(
                "qledger[%s]: %d row(s) seen, 0 registered this run "
                "(%d no-call, %d region-excluded, %d retrospective)",
                family, stats["n_rows"], stats["n_skipped_no_call"],
                stats["n_region_excluded"], stats["n_retrospective_skipped"])
        return stats

    try:
        if dry_run:
            with TemporaryDirectory(prefix="qledger_p3_dry_run_") as tmp:
                results = qledger.register_batch(candidates, root=tmp, dedupe=True)
        else:
            results = qledger.register_batch(candidates, root=root, dedupe=True)
    except Exception as exc:  # noqa: BLE001 — LOUD, never silent (blocker: silent total failure)
        stats["error"] = str(exc)
        print(f"::error title={family}-qledger-register-failed::qledger[{family}] "
             f"register_batch raised: {exc}", flush=True)
        log.error("qledger[%s]: register_batch failed: %s", family, exc)
        return stats

    stats["n_accepted"] = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "open")
    stats["n_rejected"] = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "rejected")

    if not dry_run and stats["n_accepted"] > 0:
        from engine import qledger_evidence_clock as _clock  # local import — avoid a hard
                                                              # dependency for callers that
                                                              # never actually register
        rec = _clock.record_start(
            family, horizon_d=candidates[0]["horizon_d"],
            horizon_unit=qledger.HORIZON_UNIT_TRADING, git_sha=git_sha, root=root)
        stats["clock_started"] = True
        stats["clock_record"] = rec

    return stats
