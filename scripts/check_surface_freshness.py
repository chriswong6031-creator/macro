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
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from lib import config, nyse_calendar

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


def run(now: datetime | None = None, root: Path | None = None) -> int:
    """Check all artifacts; print ::warning:: for each stale one.  Always exits 0."""
    root = root or config.ROOT
    expected = str(nyse_calendar.expected_last_session(now))
    stale_count = 0
    for spec in _ARTIFACTS:
        as_of = _read_as_of(root, spec)
        actual = as_of or "MISSING"
        if not as_of or as_of < expected:
            stale_count += 1
            print(f"::warning::SURFACE STALE: {spec.path} as_of={actual} expected={expected}")
            log.warning("SURFACE STALE: %s as_of=%s expected=%s", spec.path, actual, expected)
        else:
            log.info("fresh: %s as_of=%s", spec.path, as_of)
    if stale_count == 0:
        log.info("all %d surface artifacts are fresh for session %s", len(_ARTIFACTS), expected)
    else:
        log.warning("%d/%d surface artifacts are stale (expected session %s)",
                    stale_count, len(_ARTIFACTS), expected)
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
