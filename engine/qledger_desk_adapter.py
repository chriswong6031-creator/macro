"""engine/qledger_desk_adapter.py — POOL_DESKS thesis row → Universal Scoreboard
claim (Intelligence Evaluation OS, T9 adoption wave 1).

WHY THIS EXISTS.  engine/qledger.py is the claims+grades substrate, and its value
is LINEAR IN TIME and QUADRATIC IN ADOPTION: a claim registered tonight has a
matured verdict in N days; a claim not registered tonight can never be
reconstructed, because the whole point is that the prediction is recorded BEFORE
the outcome exists.  Wave 1 wires three desks that already emit an
engine-derived, machine-checkable predicate but were never registering.

WHAT IT IS NOT.  It is a TRANSLATOR, never an originator (house constitution A7 /
brief R4).  Every field of the claim is lifted verbatim from a field the desk's
own engine already wrote:

    direction    <- sign of the ENGINE's own refutation predicate
                    (falsifier.check.op + .threshold), never a lean table here
    horizon_d    <- the row's own declared ruler (falsifier.check.horizon_d
                    mirrors it), never shortened to reach a faster verdict
    scope.key    <- falsifier.check.subject_ticker (the engine-resolved,
                    priceable instrument — for thematic_desk that is the theme's
                    proxy ETF, not the unpriceable theme label)
    bench        <- falsifier.check.vs, READ not defaulted (a desk benched
                    against XIC.TO must never silently become SPY)
    entry_levels <- the row's own PIT entry_levels {subject: px, bench: px}
    check_by     <- the row's own check_by
    falsifier    <- the row's own falsifier object, verbatim

If a row does not already carry a direction and a level, this module does not get
to invent one — it SKIPS the row.

DIRECTION SIGN, DERIVED FROM THE REFUTATION PREDICATE.  Every one of these desks
writes its falsifier as "what would prove me wrong":

    {"kind": "rel_return", "subject_ticker": "NOW", "vs": "SPY",
     "op": "<", "threshold": -0.05, "horizon_d": 126}

means "I am refuted if NOW UNDERperforms SPY by 5%", i.e. the desk is LONG the
subject vs the bench => direction = +1.  The mirror (op ">", threshold +0.05) is
"refuted if it OUTperforms" => direction = -1.  Nothing else maps.

A `kind: "soft"` row is a DECLARED NO-CALL (stock_desk's neutral lean, a theme
with no scalar proxy), and it is SKIPPED — never filed as direction=0.  direction
0 means SALIENCE, whose `hit` is null by construction; 71% of the existing corpus
is already direction==0, which overstates the directional evidence 3.5x.  Growing
that share with rows the desk itself declared unscoreable would be the exact
self-deception this program exists to end.

IDEMPOTENCE.  Every claim carries an explicit `salt` = the source thesis id, so
claim_id = sha1(desk|asof|scope_key|horizon_d|direction|source_id) is stable
across re-runs and two same-day rows on the same ticker cannot collide into one.
(scripts/build_whitehouse.py sets no salt and silently under-counts for exactly
this reason — every adapter here sets one, and a row with no usable id is
skipped rather than registered unsalted.)

COST.  Registration always goes through qledger.register_batch — ONE store read
and ONE append for the whole night.  register() re-scans the entire 45k-row
claims file per call (its own COST NOTE calls it quadratic); a per-row loop is
banned here.

NEVER FATAL.  Every public entry point degrades: a failure logs and returns a
stats dict, and never raises into a desk's build path.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from engine import qledger

log = logging.getLogger("qledger_desk_adapter")

# The two engine-emitted predicate kinds that carry a relative-return direction.
# `soft` (and anything unknown) is a declared no-call and is skipped.
DIRECTIONAL_KINDS = ("rel_return", "theme_rel_return")


def direction_from_check(check: Any) -> int | None:
    """Sign of the ENGINE's own refutation predicate, or None when the row makes
    no directional call.

    +1  refuted by UNDERperformance  (op "<", negative threshold)  -> long
    -1  refuted by OUTperformance    (op ">", positive threshold)  -> short
    None  soft / unknown kind / malformed op-threshold pair        -> skip

    The op and the threshold must AGREE. A `{"op": "<", "threshold": +0.05}` pair
    is not a predicate any of these engines emits; treating it as directional
    would be this module guessing, so it returns None.
    """
    if not isinstance(check, dict):
        return None
    if check.get("kind") not in DIRECTIONAL_KINDS:
        return None
    op = str(check.get("op") or "").strip()
    try:
        threshold = float(check.get("threshold"))
    except (TypeError, ValueError):
        return None
    if op == "<" and threshold < 0:
        return 1
    if op == ">" and threshold > 0:
        return -1
    return None


def _as_int(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def claim_from_thesis(row: dict, *, desk: str, claim_family: str,
                      timestamp_quality: str,
                      sector_of: Callable[[str], str | None] | None = None,
                      backfilled: bool = False) -> dict | None:
    """Translate ONE POOL_DESKS thesis row into a claim, or None when the row is
    not a directional, priceable, identifiable claim.

    Returns None (and never raises) for: a non-dict row, a soft/no-call
    predicate, a missing subject/bench/horizon/asof, or a missing thesis id
    (which would force an unsalted claim_id — see the module note).
    """
    if not isinstance(row, dict):
        return None
    check = ((row.get("falsifier") or {}).get("check")
             if isinstance(row.get("falsifier"), dict) else None)
    direction = direction_from_check(check)
    if direction is None:
        return None

    subject = str((check or {}).get("subject_ticker") or "").strip()
    bench = str((check or {}).get("vs") or "").strip()
    if not subject or not bench:
        return None

    # The engine's own declared ruler. The row's horizon_d is authoritative; the
    # predicate mirrors it, and is the fallback only when the row omits it.
    horizon_d = _as_int(row.get("horizon_d")) or _as_int((check or {}).get("horizon_d"))
    if horizon_d is None:
        return None

    asof = str(row.get("state_asof") or "").strip()
    if not asof:
        return None

    source_id = str(row.get("id") or "").strip()
    if not source_id:
        # No stable salt is available, and an unsalted claim_id collides with any
        # same-day, same-direction sibling on this ticker. Skip loudly rather than
        # register an under-count.
        return None

    entry = row.get("entry_levels") if isinstance(row.get("entry_levels"), dict) else {}
    subject_level = entry.get(subject)
    bench_level = entry.get(bench)

    sector = None
    if sector_of is not None:
        try:
            sector = sector_of(subject)
        except Exception:  # noqa: BLE001 — a control is optional, never fatal
            sector = None

    extra: dict[str, Any] = {
        "source_id": source_id,
        "source_lean": row.get("lean"),
        "source_conviction": row.get("conviction"),
    }
    if backfilled:
        # R3: a backfilled row accrues as CONTEXT, not as live-forward evidence.
        # Marked on the row itself so no reader has to infer it from dates.
        extra["backfilled"] = True
        extra["backfill_note"] = ("registered from the desk's committed ledger on "
                                  "adapter activation — the thesis was pre-registered "
                                  "in its own ledger before the outcome existed, but "
                                  "the qledger row is not a live-forward record")

    claim = qledger.make_claim(
        desk=desk,
        asof=asof,
        scope_type="entity",
        scope_key=subject,
        direction=direction,
        horizon_d=horizon_d,
        timestamp_quality=timestamp_quality,
        subject_level=subject_level,
        bench_level=bench_level,
        bench=bench,
        sector=sector,
        falsifier=row.get("falsifier"),
        check_by=row.get("check_by"),
        claim_family=claim_family,
        extra=extra,
    )
    # Explicit salt — idempotence across re-runs AND collision safety between two
    # same-day rows on the same ticker (see the module note).
    claim["salt"] = source_id
    return claim


def claims_from_theses(rows: Iterable[dict], *, desk: str, claim_family: str,
                       timestamp_quality: str,
                       sector_of: Callable[[str], str | None] | None = None,
                       forward_ids: Sequence[str] | set[str] | None = None,
                       ) -> tuple[list[dict], dict]:
    """Translate many rows. Returns (claims, stats).

    `forward_ids` — the ids written by THIS run. When given, any row outside it is
    stamped `backfilled=True`. When None, every row is treated as forward.
    """
    fwd = set(forward_ids) if forward_ids is not None else None
    claims: list[dict] = []
    n_rows = 0
    n_skipped = 0
    n_backfilled = 0
    for row in rows:
        n_rows += 1
        src = str((row or {}).get("id") or "") if isinstance(row, dict) else ""
        is_backfill = bool(fwd is not None and src not in fwd)
        claim = claim_from_thesis(row, desk=desk, claim_family=claim_family,
                                  timestamp_quality=timestamp_quality,
                                  sector_of=sector_of, backfilled=is_backfill)
        if claim is None:
            n_skipped += 1
            continue
        if is_backfill:
            n_backfilled += 1
        claims.append(claim)
    return claims, {
        "desk": desk,
        "n_rows": n_rows,
        "n_claims": len(claims),
        "n_skipped_no_call": n_skipped,
        "n_backfilled": n_backfilled,
    }


def _dedupe_keep_first(rows: Iterable[dict]) -> list[dict]:
    """Keep the FIRST row per thesis id — the same first-wins law the desk
    ledgers themselves enforce (engine.desk_ledger). A ledger carrying two rows
    under one id (stock_desk's pre-run_token era) must never register the second,
    arbitrary lean."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        out.append(r)
    return out


def register_theses(rows: Iterable[dict], *, desk: str, claim_family: str,
                    timestamp_quality: str, root: Path | str | None = None,
                    sector_of: Callable[[str], str | None] | None = None,
                    forward_ids: Sequence[str] | set[str] | None = None,
                    warn_when_empty: bool = True) -> dict:
    """Translate + register a batch of thesis rows into the Universal Scoreboard.

    ONE store read, ONE append (qledger.register_batch, dedupe=True) — so a
    re-run of the same night is a no-op, not a duplicate.

    Emits a bare `::warning` (never through a logger — a prefixing formatter makes
    GitHub silently drop the annotation) when the desk produced NO claims, so a
    silently disabled or dark desk lane is visible in the Actions summary.

    Never raises. Returns the stats dict.
    """
    stats: dict[str, Any] = {"desk": desk, "n_rows": 0, "n_claims": 0,
                             "n_skipped_no_call": 0, "n_backfilled": 0,
                             "n_accepted": 0, "n_rejected": 0}
    try:
        rows = _dedupe_keep_first(rows)
        claims, stats = claims_from_theses(
            rows, desk=desk, claim_family=claim_family,
            timestamp_quality=timestamp_quality, sector_of=sector_of,
            forward_ids=forward_ids)
        stats.setdefault("n_accepted", 0)
        stats.setdefault("n_rejected", 0)
        if claims:
            results = qledger.register_batch(claims, root=root, dedupe=True)
            # `n_accepted` counts claims the ledger holds in status=open after this
            # call — NEW rows AND rows a previous run already registered (register_batch
            # returns the stored row for a dedupe hit). It is deliberately NOT a
            # "rows appended tonight" counter: deriving that would cost a second full
            # scan of the 45k-row store per desk per night, and idempotence is proven
            # by the store's size, not by this number.
            stats["n_accepted"] = sum(
                1 for r in results if isinstance(r, dict) and r.get("status") == "open")
            stats["n_rejected"] = sum(
                1 for r in results if isinstance(r, dict) and r.get("status") == "rejected")
        if warn_when_empty and not claims:
            print(f"::warning title={desk}-no-claims::"
                  f"qledger adapter registered 0 claims for desk {desk} "
                  f"({stats.get('n_rows', 0)} ledger row(s) seen, "
                  f"{stats.get('n_skipped_no_call', 0)} declared no-call) — "
                  f"the desk is disabled, dark, or emitted only soft predicates",
                  flush=True)
        log.info("qledger[%s]: %d claim(s) from %d row(s) "
                 "(%d no-call skipped, %d backfilled, %d accepted, %d rejected)",
                 desk, stats["n_claims"], stats["n_rows"],
                 stats["n_skipped_no_call"], stats["n_backfilled"],
                 stats["n_accepted"], stats["n_rejected"])
    except Exception as exc:  # noqa: BLE001 — accrual must never sink a build
        log.warning("qledger[%s] registration failed: %s", desk, exc)
        stats["error"] = str(exc)
    return stats


def read_ledger(path: Path | str) -> list[dict]:
    """Read a desk theses.jsonl. Never raises; a missing/rotten file reads as []."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(row, dict):
                out.append(row)
    except Exception as exc:  # noqa: BLE001
        log.warning("qledger adapter: unreadable ledger %s: %s", p, exc)
        return []
    return out


def register_ledger(ledger_path: Path | str, *, desk: str, claim_family: str,
                    timestamp_quality: str, root: Path | str | None = None,
                    forward_ids: Sequence[str] | set[str] | None = None,
                    sector_of: Callable[[str], str | None] | None = None,
                    row_filter: Callable[[dict], bool] | None = None,
                    include_backfill: bool = True) -> dict:
    """Register a desk's committed ledger (optionally filtered).

    `include_backfill=False` restricts registration to `forward_ids` — the rows
    THIS run appended. That is the correct mode for a ledger whose historical ids
    are not unique (stock_desk carries 110 duplicated ids with CONTRADICTORY
    leans inside one id, so a salt=id backfill would keep one arbitrary lean out
    of up to sixteen).
    """
    rows = read_ledger(ledger_path)
    if row_filter is not None:
        rows = [r for r in rows if _safe_filter(row_filter, r)]
    if not include_backfill:
        fwd = set(forward_ids or ())
        rows = [r for r in rows if str(r.get("id") or "") in fwd]
    return register_theses(rows, desk=desk, claim_family=claim_family,
                           timestamp_quality=timestamp_quality, root=root,
                           sector_of=sector_of, forward_ids=forward_ids)


def _safe_filter(fn: Callable[[dict], bool], row: dict) -> bool:
    try:
        return bool(fn(row))
    except Exception:  # noqa: BLE001
        return False
