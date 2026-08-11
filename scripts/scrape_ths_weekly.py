"""Weekly, receipted, complete-or-fail re-scrape of the 同花顺 concept-board taxonomy.

WHY THIS EXISTS (the defect it closes)
--------------------------------------
The THS membership plane looked alive and was not.  Three correct-in-isolation
decisions composed into a two-year-shaped hole:

  * ``collectors/china_ths_concepts.py`` (the scraper) and
    ``scripts/seed_china_ths_baskets.py`` (the seeder) appear in ZERO workflows.
    The 2026-07-08 snapshot was a one-off hand-run bundled with a feature commit.
  * ``data/baskets_china_ths/membership.json`` therefore froze on 2026-06-30 and
    has not moved since.
  * ``scripts/build_baskets_china_ths.py --snapshot`` DOES run nightly, and every
    night it hashes today's membership.json against the newest dated side-car,
    matches, logs a dedup skip and exits 0.  ~35 consecutive green nights that
    stamped nothing, because nothing upstream was refreshing the input.

So the point-in-time membership store the theme/relay program is blocked on had
exactly two snapshots, eight days apart, over six weeks — while every signal
stayed green.  This script is the missing producer: a NON-agent, resumable,
receipted full-taxonomy scrape wired into the CN collection lane once a week.

COMPLETE-OR-FAIL, NOW AT THE RUN LEVEL (masterplan G0.4)
--------------------------------------------------------
The collector already refuses to record a PARTIAL member list for one board
(``ThsTruncated``): a truncated board is indistinguishable from a genuinely
smaller one, and recording it makes the seeder read the missing tail as a mass
exit.  The identical hazard exists one level up, and nothing enforced it there:
a RUN that resolves 200 of 373 boards writes a dated side-car that is missing
173 boards outright, and the seeder's auto-import loop enumerates only what the
newest side-car contains (``seed_china_ths_baskets.py`` line 373), so every
unscraped concept would silently VANISH from membership.json.

Hence: the scrape runs into a STAGING directory, and the dated file is promoted
into ``data/baskets_china_ths/snapshots/`` only when every attempted concept
resolved.  A partial attempt leaves NO side-car — it leaves a receipt saying
``complete: false`` and the names it could not page, and its staged progress so
the next attempt on the same date resumes instead of restarting.

RECEIPTS (the other half — silence must be impossible)
------------------------------------------------------
Every attempt writes ``data/baskets_china_ths/receipts/scrape_<date>.json``
(contract: ``contracts/baskets_china_ths/scrape_receipt.v1.schema.json``).
Without it, "the scrape ran and THS is unchanged" and "the scrape has been dead
for a month" are the same empty directory — which is the exact failure above,
one layer out.  ``scripts/check_membership_snapshot_freshness.py`` reads these
receipts and warns when no COMPLETE scrape has landed inside its budget.

THROTTLING (why one pass is not enough)
---------------------------------------
THS IP-throttles bursts hard; the collector stops early after
``_MAX_CONSEC_EMPTY`` consecutive failures and documents "running it a few times
across cool-downs accumulates full coverage".  This driver automates exactly
that: up to ``--max-passes`` resumable passes separated by ``--cooldown-seconds``,
inside a hard ``--budget-minutes`` wall so the CI job can never outrun its
timeout.  Progress persists after every board, so a pass that dies mid-taxonomy
costs nothing but its own remaining time.

Usage:
    python -m scripts.scrape_ths_weekly                 # full taxonomy, today (UTC)
    python -m scripts.scrape_ths_weekly --as-of 2026-08-15 --budget-minutes 30
    python -m scripts.scrape_ths_weekly --selftest      # pure-logic pins, no network
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("scrape_ths_weekly")

SUITE = "baskets_china_ths"
RECEIPT_SCHEMA = "baskets_china_ths.scrape_receipt.v1"
SOURCE = "q.10jqka.com.cn"
WRITER = "scripts.scrape_ths_weekly"

#: Scrape target — OUTSIDE snapshots/, so a run killed mid-taxonomy can never
#: leave a partial dated file where the seeder or the PIT backfill would read it
#: as an authoritative board list.
STAGING_DIR = "scrape_staging"
RECEIPTS_DIR = "receipts"

DEFAULT_MAX_PASSES = 4
DEFAULT_COOLDOWN_SECONDS = 300.0
DEFAULT_BUDGET_MINUTES = 150.0


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _suite_dir() -> Path:
    return config.data_dir() / SUITE


def staging_path(as_of: str) -> Path:
    return _suite_dir() / STAGING_DIR / f"{as_of}.json"


def snapshot_path(as_of: str) -> Path:
    return _suite_dir() / "snapshots" / f"{as_of}.json"


def receipt_path(as_of: str) -> Path:
    return _suite_dir() / RECEIPTS_DIR / f"scrape_{as_of}.json"


# ---------------------------------------------------------------------------
# Pure helpers (no network, no clock — the selftest pins these)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unresolved(names: list[str], result: dict) -> list[str]:
    """Concept names with no COMPLETE member list in ``result``.

    An empty list in the result counts as unresolved, deliberately: the
    collector records a board only after paging it fully, and treats an empty
    return as the throttle signature rather than as a genuinely empty board.
    """
    return [n for n in names if not result.get(n)]


def build_receipt(*, as_of: str, started_at: str, finished_at: str,
                  names: list[str], result: dict, passes: int,
                  budget_minutes: float, budget_exhausted: bool,
                  promoted: bool, pit_rows_added: int,
                  note: str = "") -> dict:
    """The scrape receipt for one attempt — the artifact, not a log line.

    ``complete`` is the load-bearing field and is computed, never asserted: it is
    true only when every attempted concept resolved.  ``promoted`` is forced
    false whenever ``complete`` is false, so the receipt can never claim a
    side-car that a partial scrape is forbidden to leave behind.
    """
    missing = unresolved(names, result)
    fetched = [n for n in names if result.get(n)]
    complete = not missing and bool(names)
    return {
        "schema": RECEIPT_SCHEMA,
        "date": as_of,
        "started_at": started_at,
        "finished_at": finished_at,
        "concepts_attempted": len(names),
        "concepts_fetched": len(fetched),
        "members_total": sum(len(result.get(n) or []) for n in fetched),
        "complete": complete,
        "truncated": sorted(missing),
        "source": SOURCE,
        "writer": WRITER,
        "passes": passes,
        "budget_minutes": float(budget_minutes),
        "budget_exhausted": bool(budget_exhausted),
        "promoted": bool(promoted and complete),
        "pit_rows_added": int(pit_rows_added),
        "note": note,
    }


def _write_receipt(as_of: str, receipt: dict) -> Path:
    p = receipt_path(as_of)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _membership_pit_lane() -> str | None:
    """The collection lane, resolved FAIL-CLOSED from ``CN_LANE`` (no default).

    Same resolver contract as ``scripts.build_baskets_china_ths._membership_pit_lane``:
    the PIT store is append-only and keep-FIRST per snapshot_date, so whoever
    stamps a date owns it forever and a permissive default would let a hand-run
    decide the published point-in-time answer.  Only asia-close.yml sets
    ``CN_LANE: asia``; everything else resolves None and appends nothing.
    """
    import os  # noqa: PLC0415 — local to the lane-resolution path

    return (os.environ.get("CN_LANE") or "").strip() or None


def _ingest_to_pit() -> int:
    """Fold the freshly promoted side-car into the per-suite PIT parquet.

    Reuses the store's own ``backfill_from_json_snapshots``, which is keep-FIRST
    on ``(snapshot_date, basket_id, ticker)`` and skips dates already stored — so
    running it here AND again from tonight's ``--snapshot`` step is a no-op the
    second time.  Doing it in this run rather than waiting for the next nightly
    is what keeps the parquet's newest snapshot_date coherent with the newest
    side-car on the same day the side-car lands.  Never fatal.
    """
    try:
        from engine import basket_membership_pit as pit  # noqa: PLC0415

        res = pit.backfill_from_json_snapshots(SUITE, lane=_membership_pit_lane())
        rows = int(res.get("rows_added") or 0)
        log.info("membership PIT backfill: +%d rows (dates=%s%s)", rows,
                 ",".join(res.get("dates") or []) or "none",
                 f", {res['reason']}" if res.get("reason") else "")
        return rows
    except Exception as exc:  # noqa: BLE001 — additive, never fatal
        log.warning("membership PIT backfill failed (%s)", exc)
        return 0


# ---------------------------------------------------------------------------
# The scrape
# ---------------------------------------------------------------------------

def run(*, as_of: str | None = None, max_passes: int = DEFAULT_MAX_PASSES,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        budget_minutes: float = DEFAULT_BUDGET_MINUTES,
        names: list[str] | None = None) -> int:
    """Scrape the full THS taxonomy into staging; promote + ingest only if complete.

    Always exits 0 by design.  This is a collection step inside a lane whose
    contract is graceful degradation; a throttled vendor must not red a lane that
    landed every other store.  The teeth are the receipt plus
    ``scripts/check_membership_snapshot_freshness.py``, which warns when no
    complete scrape has landed inside its budget.
    """
    from collectors import china_ths_concepts as ths  # noqa: PLC0415 — network import

    as_of = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    started_at = _utc_now()
    deadline = time.monotonic() + budget_minutes * 60.0

    canonical = snapshot_path(as_of)
    if canonical.exists():
        log.info("THS re-scrape: %s already promoted — nothing to do", canonical.name)
        return 0

    if names is None:
        names = sorted(ths.concept_code_map().keys())
    if not names:
        log.error("THS re-scrape: empty concept taxonomy — cannot scrape")
        _write_receipt(as_of, build_receipt(
            as_of=as_of, started_at=started_at, finished_at=_utc_now(), names=[],
            result={}, passes=0, budget_minutes=budget_minutes,
            budget_exhausted=False, promoted=False, pit_rows_added=0,
            note="concept map unavailable (akshare name endpoint + disk cache both empty)"))
        return 0

    stage = staging_path(as_of)
    stage.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {}
    if stage.exists():
        try:
            result = json.loads(stage.read_text(encoding="utf-8"))
            log.info("THS re-scrape: resuming staged attempt — %d/%d boards already resolved",
                     len(result), len(names))
        except Exception as exc:  # noqa: BLE001 — a bad staging file restarts the attempt
            log.warning("THS re-scrape: staged file unreadable (%s) — starting fresh", exc)
            result = {}

    passes = 0
    budget_exhausted = False
    for attempt in range(1, max_passes + 1):
        todo = unresolved(names, result)
        if not todo:
            break
        if time.monotonic() >= deadline:
            budget_exhausted = True
            log.warning("THS re-scrape: %.0fm budget exhausted with %d board(s) unresolved",
                        budget_minutes, len(todo))
            break
        passes = attempt
        log.info("THS re-scrape pass %d/%d — %d board(s) to resolve",
                 attempt, max_passes, len(todo))
        try:
            result = ths.snapshot(todo, as_of=as_of, resume=True, snap_dir=stage.parent)
        except Exception as exc:  # noqa: BLE001 — a vendor outage is not a lane failure
            log.warning("THS re-scrape pass %d raised (%s) — keeping staged progress", attempt, exc)
            try:
                result = json.loads(stage.read_text(encoding="utf-8")) if stage.exists() else result
            except Exception:  # noqa: BLE001
                pass
        if unresolved(names, result) and attempt < max_passes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                budget_exhausted = True
                break
            nap = min(cooldown_seconds, remaining)
            log.info("THS re-scrape: cooling down %.0fs before pass %d", nap, attempt + 1)
            time.sleep(nap)

    missing = unresolved(names, result)
    complete = not missing
    promoted = False
    pit_rows = 0
    if complete:
        # PROMOTE: staging -> canonical. Only now does anything downstream — the
        # seeder's enumeration, the PIT backfill, the freshness tripwire — see it.
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage), str(canonical))
        promoted = True
        log.info("THS re-scrape: promoted %s (%d boards, %d member slots)",
                 canonical.name, len(result), sum(len(v or []) for v in result.values()))
        pit_rows = _ingest_to_pit()
    else:
        log.warning("THS re-scrape INCOMPLETE: %d/%d boards resolved — no side-car promoted "
                    "(a partial dump would read to the seeder as %d vanished boards). "
                    "Staged at %s for the next attempt on this date.",
                    len(names) - len(missing), len(names), len(missing), stage)

    receipt = build_receipt(
        as_of=as_of, started_at=started_at, finished_at=_utc_now(), names=names,
        result=result, passes=passes, budget_minutes=budget_minutes,
        budget_exhausted=budget_exhausted, promoted=promoted, pit_rows_added=pit_rows)
    p = _write_receipt(as_of, receipt)
    log.info("THS re-scrape receipt: %s (complete=%s, %d/%d boards, %d member slots)",
             p.name, receipt["complete"], receipt["concepts_fetched"],
             receipt["concepts_attempted"], receipt["members_total"])
    return 0


# ---------------------------------------------------------------------------
# Selftest (pure logic — no network, no clock)
# ---------------------------------------------------------------------------

def selftest() -> int:
    names = ["A", "B", "C"]
    full = {"A": [{"ticker": "1"}], "B": [{"ticker": "2"}], "C": [{"ticker": "3"}]}
    part = {"A": [{"ticker": "1"}], "B": []}
    kw = dict(as_of="2026-08-15", started_at="2026-08-15T00:00:00Z",
              finished_at="2026-08-15T01:00:00Z", passes=1, budget_minutes=10.0,
              budget_exhausted=False, pit_rows_added=0)
    ok = build_receipt(names=names, result=full, promoted=True, **kw)
    bad = build_receipt(names=names, result=part, promoted=True, **kw)
    checks = [
        (unresolved(names, part) == ["B", "C"], "an empty board counts as unresolved"),
        (ok["complete"] is True and ok["truncated"] == [], "a full result is complete"),
        (ok["members_total"] == 3, "member slots are counted across boards"),
        (bad["complete"] is False, "a partial result is never complete"),
        (bad["truncated"] == ["B", "C"], "the receipt names the unresolved boards"),
        # The rule the whole design rests on: a partial attempt may not claim a
        # side-car, even when the caller passes promoted=True by mistake.
        (bad["promoted"] is False, "a partial attempt can never report promoted"),
        (build_receipt(names=[], result={}, promoted=False, **kw)["complete"] is False,
         "an empty taxonomy is not vacuously complete"),
    ]
    failed = [m for good, m in checks if not good]
    for m in failed:
        print(f"selftest FAIL: {m}")
    print("scrape_ths_weekly selftest: " + ("OK" if not failed else f"{len(failed)} failure(s)"))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=None, help="date stamp (default: today UTC)")
    ap.add_argument("--max-passes", type=int, default=DEFAULT_MAX_PASSES,
                    help="resumable cool-down passes (THS throttles bursts)")
    ap.add_argument("--cooldown-seconds", type=float, default=DEFAULT_COOLDOWN_SECONDS)
    ap.add_argument("--budget-minutes", type=float, default=DEFAULT_BUDGET_MINUTES,
                    help="hard wall-clock budget; must stay under the CI job timeout")
    ap.add_argument("--selftest", action="store_true", help="pure-logic pins, no network")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    return run(as_of=a.as_of, max_passes=a.max_passes,
               cooldown_seconds=a.cooldown_seconds, budget_minutes=a.budget_minutes)


if __name__ == "__main__":
    raise SystemExit(main())
