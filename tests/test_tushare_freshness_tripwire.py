"""The Tushare plane must not be able to go cold silently.

The failure this guards is not "a collector broke" — it is that NOTHING SAID SO.
tushare_client returns None for every failure it has, callers omit the leg rather
than write a zero, and asia-close's collect step never fails on one source. Each
of those is individually correct; together they let flow_hist and moneyflow freeze
at 2026-07-24 and still render on flow_velocity.html on 2026-08-06.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.check_tushare_freshness import (  # noqa: E402
    MAX_SESSIONS_BEHIND,
    evaluate,
    selftest,
    sessions_between,
)

WORKFLOW = _ROOT / ".github" / "workflows" / "asia-close.yml"


def test_selftest_passes() -> None:
    assert selftest() == 0


def test_the_real_incident_is_caught() -> None:
    """2026-07-24 data still being served on 2026-08-06 must read stale."""
    status, behind = evaluate("2026-07-24", date(2026, 8, 6))
    assert status == "stale"
    assert behind > MAX_SESSIONS_BEHIND, f"only {behind} sessions behind — threshold too slack"


def test_check_is_anchored_to_the_calendar_not_to_the_store_itself() -> None:
    """The property the whole tripwire rests on.

    A self-relative check — newest row vs the store's own newest row, or vs a
    sibling that froze in the same outage — reads FRESH during a total outage,
    because a frozen feed is perfectly self-consistent. Only an anchor that keeps
    advancing on its own can see a gap. So the same store date must flip from
    fresh to stale purely because the expected session moved forward.
    """
    frozen = "2026-07-24"
    assert evaluate(frozen, date(2026, 7, 27))[0] == "fresh"
    assert evaluate(frozen, date(2026, 8, 6))[0] == "stale"


def test_a_healthy_plane_does_not_trip_over_a_weekend() -> None:
    """Friday data read on Monday must stay quiet, or the warning becomes noise."""
    assert evaluate("2026-07-31", date(2026, 8, 3))[0] == "fresh"   # Fri -> Mon
    assert evaluate("2026-08-05", date(2026, 8, 6))[0] == "fresh"   # yesterday


def test_unreadable_dates_never_read_fresh() -> None:
    """Fail loud, not open: a store whose date column changed shape is not 'fine'."""
    assert evaluate(None, date(2026, 8, 6))[0] == "absent"
    assert evaluate("not-a-date", date(2026, 8, 6))[0] == "stale"
    assert sessions_between("", date(2026, 8, 6)) > MAX_SESSIONS_BEHIND


def test_tripwire_runs_in_the_lane_that_collects_the_data() -> None:
    """A guard nobody invokes is decoration — pin the wiring, not just the script."""
    y = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_tushare_freshness.py" in y, \
        "asia-close no longer runs the tripwire — the plane can go cold silently again"
    assert y.index("scripts.collect --group asia") < y.index("check_tushare_freshness"), \
        "the tripwire must run AFTER collection, or it grades the previous run's stores"


def test_annotation_starts_the_line_and_is_flushed(capsys: pytest.CaptureFixture[str]) -> None:
    """GitHub drops an annotation that does not start its line.

    Every builder here logs with a prefixing formatter, so `log.warning("::warning …")`
    emits `WARNING ::warning …` and vanishes from the Actions summary while reviewing
    as a live alarm. This asserts the emitted shape, not the wording.
    """
    src = (_ROOT / "scripts" / "check_tushare_freshness.py").read_text(encoding="utf-8")
    assert not re.search(r"log(?:ger)?\.\w+\(\s*f?[\"']::", src), \
        "annotation emitted through a logger — GitHub will silently drop it"
    assert 'flush=True' in src, "stdout is block-buffered when piped in CI"

    import scripts.check_tushare_freshness as m

    monkey = [("tushare/flow_hist.parquet", "tushare_moneyflow")]
    real_stores, real_latest = m.STORES, m._latest_date
    m.STORES = tuple(monkey)
    m._latest_date = lambda rel: "2026-07-24"
    try:
        m.run()
    finally:
        m.STORES, m._latest_date = real_stores, real_latest
    line = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert line, "no annotation emitted for a stale plane"
    assert line[0].startswith("::warning"), f"annotation must start the line, got: {line[0][:40]!r}"
