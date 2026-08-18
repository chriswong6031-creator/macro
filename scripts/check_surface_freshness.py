"""Surface-freshness sentinel (FT-R8) — assert key site artifacts carry the expected
NYSE session in their as_of field.

WHAT: reads a fixed list of first-class surface artifacts and checks that each one's
`as_of` (or `asof`) equals the expected NYSE session from lib.nyse_calendar, using the
same logic as scripts/check_price_store_freshness.py and the same run-before-midnight-ET
handling.

CONTRACT (warn-only): prints a GHA annotation line
  ::warning::SURFACE STALE: <artifact> as_of=<actual> expected=<expected>
for every stale artifact and exits 0 always.  The sentinel is additive — it never
breaks the render.  Its annotations appear in the job summary and can drive alerting
from a separate hook without blocking the build.

When an artifact is absent from the filesystem the warning includes `as_of=MISSING`.

CALLED FROM: scripts/build_baskets.py (end of main, inside its own try/except) so
every nightly run evaluates freshness after all sub-builds complete.

RUN STANDALONE:
  python -m scripts.check_surface_freshness          # live mode
  python -m scripts.check_surface_freshness --selftest
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config, nyse_calendar  # noqa: E402

log = logging.getLogger("check_surface_freshness")


class ArtifactSpec(NamedTuple):
    path: str            # relative to config.ROOT
    as_of_key: str = "as_of"   # JSON key holding the session date string


# Authoritative list of first-class surface artifacts (FT-R8).
# Each must carry as_of == expected NYSE session after a healthy nightly.
_ARTIFACTS: list[ArtifactSpec] = [
    ArtifactSpec("data/allocation/latest_us.json"),
    ArtifactSpec("site/allocationdata/allocation.json"),
    ArtifactSpec("site/basketdata/baskets.json"),
    ArtifactSpec("site/basketdata/oracle_state.json"),
    ArtifactSpec("site/basketdata/sector_pulse.json"),
    ArtifactSpec("site/basketdata/turn_watch.json"),  # FTR W4 basket turn-watch organ
    ArtifactSpec("site/factordata/us_standouts.json"),  # CSP-W5 FT-R8 registration
]


def _read_as_of(root: Path, spec: ArtifactSpec) -> str | None:
    """Return the as_of string from the artifact, or None if absent/unreadable."""
    p = root / spec.path
    try:
        d = json.loads(p.read_text())
        val = d.get(spec.as_of_key)
        if val is None:
            val = d.get("asof")       # oracle_state uses "asof" not "as_of" in some versions
        return str(val) if val is not None else None
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("could not read %s: %s", spec.path, e)
        return None


#: Sessions behind at which a stale surface stops being a late render and becomes an
#: outage worth waking someone for. ONE session behind is routine — a render that lands
#: either side of a close, a lane that publishes on the next run. TWO or more means a
#: session produced no artifact at all, which is the shape of the 2026-08-01..08-06
#: incident: the board sat at as_of=2026-07-31 for six days while every night printed
#: `SURFACE STALE` into a job summary nobody reads.
ESCALATE_SESSIONS_BEHIND = 2


def _escalate(stale: list[tuple[str, str]], worst: int, expected: str) -> None:
    """Push the staleness digest to the ops spine. NEVER raises, never blocks.

    ONE digest, not one alert per surface: six `SURFACE STALE` lines describing a single
    frozen board is one incident, and six pushes is how an operator learns to mute the
    channel. push_ops_alert's per-lane dedup then keeps a persistent outage to roughly a
    daily reminder rather than a nightly repeat.

    Why this exists: on 2026-08-04 this sentinel emitted eight staleness annotations and
    nothing consumed them. The board stayed frozen until 08-06, when the operator noticed
    the prices were wrong. The detection was never the gap — every fact needed to diagnose
    it was already in the job summary. This routes it somewhere with a reader.
    """
    try:
        from engine.alert_triage import push_ops_alert

        names = ", ".join(path for path, _ in stale[:6])
        more = f" (+{len(stale) - 6} more)" if len(stale) > 6 else ""
        push_ops_alert(
            source="surface_freshness",
            type_="surfaces_stale",
            message=(
                f"{len(stale)} surface artifact(s) stale — worst is {worst} session(s) "
                f"behind (expected {expected}). {names}{more}. A surface this far behind "
                f"means a session published nothing; check the nightly's engine job and "
                f"data/breadth/_closes_cache.parquet's tip before trusting any board."
            ),
            severity="major",
            lane="surface_freshness",
            window_hours=20,
        )
    except Exception as e:  # noqa: BLE001 — a sentinel must never break the render
        log.warning("surface-freshness escalation failed (%s) — annotations still stand", e)


#: Sessions the US Context Vector store may trail the board's own as_of before it
#: alarms. The comparison is DIFFERENTIAL on purpose — candidates vs the board the
#: same bake writes, not vs the calendar — so it fires precisely on the
#: silent-sibling shape: boards advancing nightly while append_candidates returns
#: 0 into a log line nobody reads (P0 2026-08-14: four sessions dark while
#: snapshots.jsonl advanced every night). A whole-nightly outage keeps board and
#: candidates stale TOGETHER; that incident belongs to the board's own sentinels
#: above, not this one.
CANDIDATES_TRAIL_SESSIONS = 2


def check_candidates_freshness(root: Path, now: datetime | None = None) -> int | None:
    """US Context Vector store freshness vs the board ledger. Returns the gap in
    sessions (None = not measurable in this checkout). Warn-only, never raises.

    MISSING parts while the board exists count as maximally behind — a store
    that is not there stamped nothing.
    """
    del now  # differential check — wall clock does not enter the comparison
    board_path = root / "data" / "us_board_ledger" / "snapshots.jsonl"
    store = root / "data" / "us_prophet_rank" / "candidates"
    if not board_path.exists():
        return None   # thin/sparse checkout, or no board yet — nothing to compare
    board_as_of: date | None = None
    try:
        raw_lines = board_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:  # noqa: BLE001 — an unreadable ledger is another sentinel's subject
        log.debug("candidates freshness: board ledger unreadable (%s)", e)
        raw_lines = []
    # MAX over every parsed line, not the first line found scanning in reverse.
    # scripts/prophet_pit_replay.py (research/PROPHET_PIT_REPLAY_HARNESS_V1.md) can
    # absorb a replayed session's row OUT OF ORDER — appended after a newer session
    # has already snapshotted live — so "last line in the file" is no longer a synonym
    # for "newest as_of"; only the max over all rows is. This reads the whole file
    # rather than stopping at the first parseable line, which costs one full pass
    # instead of a partial reverse scan but is the only answer that stays correct once
    # the file's append order is no longer monotonic.
    #
    # Build commission F7: each line is parsed under its OWN try/except-continue —
    # previously the whole loop shared one try/except around the file read, so a
    # single torn line mid-file raised OUT of the loop and silently truncated the
    # max-scan to whatever had been seen before that line, exactly the "no longer a
    # synonym" case this comment already warns about (a later, genuinely newer line
    # could sit past the torn one and never get scanned).
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            val = json.loads(line).get("as_of")
            if not val:
                continue
            parsed = date.fromisoformat(str(val))
        except Exception as e:  # noqa: BLE001 — one torn line must not abort the scan
            log.debug("candidates freshness: skipping unreadable board-ledger line (%s)", e)
            continue
        if board_as_of is None or parsed > board_as_of:
            board_as_of = parsed
    if board_as_of is None:
        return None

    newest: date | None = None
    parts = sorted(store.glob("*.parquet")) if store.is_dir() else []
    if parts:
        try:
            import pandas as pd
        except Exception:  # noqa: BLE001 — minimal-deps lane
            return None
        for part in parts[-2:]:   # stamps are appended to the newest monthly parts
            try:
                stamps = pd.read_parquet(part, columns=["stamp_date"])["stamp_date"].dropna()
            except Exception as e:  # noqa: BLE001
                log.debug("candidates freshness: %s unreadable (%s)", part.name, e)
                continue
            for value in stamps.unique():
                try:
                    d = date.fromisoformat(str(value))
                except ValueError:
                    continue
                if newest is None or d > newest:
                    newest = d

    if newest is None:
        gap = 99   # board exists, store has no readable stamp at all
        actual = "MISSING"
    elif newest >= board_as_of:
        return 0
    else:
        from datetime import timedelta
        gap = len(nyse_calendar.sessions_between(newest + timedelta(days=1), board_as_of))
        actual = str(newest)
    if gap > CANDIDATES_TRAIL_SESSIONS:
        print("::warning title=us-context-vector-stale::US Context Vector store "
              f"newest stamp_date={actual} trails board as_of={board_as_of} by "
              f"{gap} session(s) — boards are advancing while append_candidates "
              "stamps nothing (silent-sibling shape); read the engine job's "
              "us-context-vector-quiet annotations for the per-night reason",
              flush=True)
        log.warning("US Context Vector store stale: newest=%s board=%s gap=%d",
                    actual, board_as_of, gap)
        try:
            from engine.alert_triage import push_ops_alert

            push_ops_alert(
                source="surface_freshness",
                type_="us_context_vector_stale",
                message=(
                    f"US Context Vector candidates store newest stamp_date={actual} "
                    f"trails board as_of={board_as_of} by {gap} sessions. The board "
                    "is advancing while the PIT context store stamps nothing — "
                    "check the engine job's us-context-vector-quiet annotations."
                ),
                severity="major",
                lane="us_context_vector_freshness",
                window_hours=20,
            )
        except Exception as e:  # noqa: BLE001 — a sentinel must never break the render
            log.warning("candidates-freshness escalation failed (%s) — annotation stands", e)
    else:
        log.info("US Context Vector store: newest=%s board=%s gap=%d (<= %d) — ok",
                 actual, board_as_of, gap, CANDIDATES_TRAIL_SESSIONS)
    return gap


def run(now: datetime | None = None, root: Path | None = None) -> int:
    """Check all artifacts; print ::warning:: for each stale one.  Always exits 0."""
    root = root or config.ROOT
    try:
        check_candidates_freshness(root, now)
    except Exception as e:  # noqa: BLE001 — the sentinel never breaks the render
        log.warning("candidates freshness check failed (%s)", e)
    expected_date = nyse_calendar.expected_last_session(now)
    expected = str(expected_date)
    stale: list[tuple[str, str]] = []
    for spec in _ARTIFACTS:
        as_of = _read_as_of(root, spec)
        actual = as_of or "MISSING"
        if not as_of or as_of < expected:
            stale.append((spec.path, actual))
            print(f"::warning::SURFACE STALE: {spec.path} as_of={actual} expected={expected}")
            log.warning("SURFACE STALE: %s as_of=%s expected=%s", spec.path, actual, expected)
        else:
            log.info("fresh: %s as_of=%s", spec.path, as_of)
    stale_count = len(stale)
    if stale_count == 0:
        log.info("all %d surface artifacts are fresh for session %s", len(_ARTIFACTS), expected)
        return 0
    log.warning("%d/%d surface artifacts are stale (expected session %s)",
                stale_count, len(_ARTIFACTS), expected)

    # How far behind is the WORST one? A MISSING artifact has no date to measure, so it
    # counts as maximally behind — an artifact that is not there published nothing.
    worst = 0
    for _path, actual in stale:
        if actual == "MISSING":
            worst = max(worst, ESCALATE_SESSIONS_BEHIND)
            continue
        try:
            worst = max(worst, nyse_calendar.sessions_behind(date.fromisoformat(actual), now))
        except Exception:  # noqa: BLE001 — an unparseable as_of is not this sentinel's subject
            continue
    if worst >= ESCALATE_SESSIONS_BEHIND:
        _escalate(stale, worst, expected)
    else:
        log.info("worst surface is %d session(s) behind (< %d) — annotation only, no page",
                 worst, ESCALATE_SESSIONS_BEHIND)
    return 0   # warn-only — never blocks the render (FT-R8)


def selftest() -> int:
    """Synthetic assertions — used by `--selftest` and the test suite."""
    from datetime import date

    root_tmp = None
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Build the minimal artifact structure for a fresh scenario.
        expected = str(nyse_calendar.expected_last_session(
            datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)))  # 03:00 UTC = prior session

        for spec in _ARTIFACTS:
            p = tmp / spec.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"as_of": expected}))

        rc = run(now=datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc), root=tmp)
        assert rc == 0, f"fresh scenario returned {rc}"

        # Poison one artifact — should still return 0 (warn-only).
        # Capture stdout so the synthetic ::warning:: line doesn't surface as a real GHA
        # annotation if --selftest is ever wired into a CI step.
        import io, contextlib
        spec0 = _ARTIFACTS[0]
        (tmp / spec0.path).write_text(json.dumps({"as_of": "2020-01-01"}))
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            rc = run(now=datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc), root=tmp)
        assert rc == 0, f"stale scenario must still exit 0 (warn-only), got {rc}"
        assert "SURFACE STALE" in _buf.getvalue(), "stale scenario should have printed a warning"

    log.info("check_surface_freshness selftest passed")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Surface-freshness sentinel (FT-R8)")
    ap.add_argument("--selftest", action="store_true",
                    help="Run synthetic assertions and exit 0/1")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return run()


if __name__ == "__main__":
    import sys
    sys.exit(main())
