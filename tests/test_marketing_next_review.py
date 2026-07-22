"""engine.marketing next_review — must be computed from cadence, never a hardcoded date.

Regression cover for the audit finding that every department clock + the CMO improvement
loop hardcoded next_review="2026-07-25", so all "next review" dates went permanently stale."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.marketing.departments import _next_review  # noqa: E402
from engine.marketing.cmo import improvement_loop_state  # noqa: E402


def test_next_review_is_computed_from_cadence():
    ref = date(2026, 7, 22)
    assert _next_review("daily", ref) == "2026-07-23"          # +1 day
    assert _next_review("weekly", ref) == (ref + timedelta(days=7)).isoformat()
    # a future ref stays ahead of it (never a fixed past literal)
    assert _next_review("daily") > date.today().isoformat()
    assert _next_review("weekly") > date.today().isoformat()


def test_cmo_improvement_loop_next_review_not_hardcoded():
    r = improvement_loop_state(loop_state="observing")
    nr = r.get("next_review")
    assert nr and nr != "2026-07-25"          # the old time-bomb literal is gone
    assert nr > date.today().isoformat()      # and it is in the future
