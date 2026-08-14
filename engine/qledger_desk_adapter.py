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
#: P0d C2.4 — the refusal classes a control construction can land in. They are
#: SEPARATE because one operator lever fixes only one of them: `no_sector_source`
#: is a WIRING defect (no resolver was passed at all — demand_chain's state until
#: this PR), `sector_absent` is a coverage gap in the universe file,
#: `vocabulary_unmapped` is census D0-2's alias mismatch (the one that killed
#: intel_hub's controls for four months), and `control_equals_subject_or_bench`
#: is C2.2's self-netting refusal. Collapsing them into one "missing" bucket
#: would report the same number for "nobody wired it" and "one ADR is off-index".
CONTROL_REFUSAL_NO_SOURCE = "no_sector_source"
CONTROL_REFUSAL_SECTOR_ABSENT = "sector_absent"
CONTROL_REFUSAL_VOCABULARY = "vocabulary_unmapped"
CONTROL_REFUSAL_SELF_OR_BENCH = "control_equals_subject_or_bench"

#: How many distinct offending `sector` values the `::warning` samples. The
#: SAMPLE is the load-bearing part: a bare count says "controls are missing", the
#: values say "the file is handing us 'Technology' and the map wants 'Information
#: Technology'" — which is exactly what would have caught D0-1/D0-2 from a
#: nightly log instead of from a four-months-later census.
_CONTROL_WARN_SAMPLE = 5


def _empty_stats(family: str, *, dry_run: bool, source_error: str | None) -> dict[str, Any]:
    return {
        "family": family, "dry_run": bool(dry_run), "source_error": source_error,
        "n_rows": 0, "n_skipped_no_call": 0, "n_region_excluded": 0,
        "n_retrospective_skipped": 0, "n_candidates": 0,
        "n_accepted": 0, "n_rejected": 0, "clock_started": False, "error": None,
        # P0d C2.4 — the control outcome of every candidate, counted. None/0 is
        # the honest shape for a family that produced no candidates.
        "control_policy": None, "n_control_valid": 0, "n_control_missing": 0,
        "control_refusals": {},
    }


def _classify_control(claim: dict, *, has_resolver: bool) -> str | None:
    """The C2.4 refusal class for ONE candidate claim, or None when its control
    leg is VALID.

    Read off the CLAIM, never off a duck-typed resolver protocol: `make_claim`
    has already stored both `sector` (the resolved vocabulary value) and
    `control` (its own `control_for_sector` lookup), so the claim itself carries
    the whole causal chain and no second implementation of the resolution can
    drift from the one that actually registered."""
    if qledger.control_leg_is_valid(claim):
        return None
    if not has_resolver:
        # No `sector_of` was passed at all — every claim of this run is
        # uncontrolled BY WIRING, which is a different (and much louder) finding
        # than a data gap.
        return CONTROL_REFUSAL_NO_SOURCE
    if not str(claim.get("sector") or "").strip():
        return CONTROL_REFUSAL_SECTOR_ABSENT
    if not str(claim.get("control") or "").strip():
        return CONTROL_REFUSAL_VOCABULARY
    # A control that IS present but did not pass `control_leg_is_valid` can only
    # be C2.2's self-netted / bench-relabelling case.
    return CONTROL_REFUSAL_SELF_OR_BENCH


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

    `sector_of` — the registration-time control construction (P0d C2.3):
    `subject ticker -> sector NAME`, which `translate_row` hands to
    `qledger.make_claim(sector=...)`, which resolves the sector ETF itself. The
    resolver must return a GICS sector NAME, never an ETF ticker (census D0-1 in
    reverse); `qledger.membership_gics_sector_of(root)` is the canonical one.
    Whatever it returns, EVERY candidate's control outcome is counted into
    `n_control_valid` / `n_control_missing` / `control_refusals` (C2.4), and a
    `matched_control_required` family with any missing control emits one
    `::warning` naming the split and the offending vocabulary values — silence is
    how a dead control wiring survives four months.

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

    # ----------------------------------------------------------------------- #
    # P0d C2.4 — COUNT THE CONTROL OUTCOME OF EVERY CANDIDATE.
    #
    # "A silent None is the defect class that stayed dead four months": a control
    # lookup that misses returns None, a null control is a LEGAL claim state, and
    # nothing anywhere alarmed — so intel_hub registered 454 sector-stamped,
    # zero-controlled claims and the census had to find it by reading the store
    # (DSC:CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL). Null-tolerance
    # is correct for display tiers and lethal for evidence wiring unless the
    # caller counts the refusal, which is what this block is.
    #
    # Classified BEFORE registration so a `dry_run` reports the same numbers the
    # live path would, and read off the candidate claims themselves (see
    # `_classify_control`) rather than by re-resolving the sector a second time.
    # ----------------------------------------------------------------------- #
    stats["control_policy"] = qledger.family_control_policy(family)[0]
    unmapped_sectors: list[str] = []
    for claim in candidates:
        refusal = _classify_control(claim, has_resolver=sector_of is not None)
        if refusal is None:
            stats["n_control_valid"] += 1
            continue
        stats["n_control_missing"] += 1
        stats["control_refusals"][refusal] = stats["control_refusals"].get(refusal, 0) + 1
        if refusal == CONTROL_REFUSAL_VOCABULARY:
            sector = str(claim.get("sector") or "").strip()
            if sector and sector not in unmapped_sectors:
                unmapped_sectors.append(sector)

    if (stats["control_policy"] == qledger.CONTROL_POLICY_REQUIRED
            and stats["n_control_missing"] > 0):
        # ONE annotation per run, and a BARE print with the `::` starting the
        # line — a logger's prefixing formatter turns this into an invisible
        # `WARNING ::warning ...` that GitHub silently drops (house law, pinned
        # by tests/test_gh_annotation_line_start.py).
        split = ", ".join(f"{k}={v}" for k, v in sorted(stats["control_refusals"].items()))
        sample = (f" unmapped sector value(s) seen: "
                  f"{', '.join(repr(s) for s in unmapped_sectors[:_CONTROL_WARN_SAMPLE])}."
                  if unmapped_sectors else "")
        print(f"::warning title={family}-qledger-control-missing::{family} is "
              f"matched_control_required (P0d C2.3) but {stats['n_control_missing']} "
              f"of {len(candidates)} prospective candidate(s) carry NO valid "
              f"control leg this run ({stats['n_control_valid']} valid). "
              f"Refusals: {split}.{sample} An uncontrolled claim can never carry "
              f"matched-control evidence for this family (contract C4.1/C5.1)",
              flush=True)
        log.warning("qledger[%s]: %d/%d candidates uncontrolled (%s)%s",
                    family, stats["n_control_missing"], len(candidates), split,
                    f"; unmapped sectors: {unmapped_sectors[:_CONTROL_WARN_SAMPLE]}"
                    if unmapped_sectors else "")

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
