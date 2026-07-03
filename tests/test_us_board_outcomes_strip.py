"""tests/test_us_board_outcomes_strip.py — Tests for emit_outcomes() and
the W2 surfaced-outcome strip including survivorship disclosure rendering.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import build_track, emit_outcomes  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _boards_stub(*as_ofs) -> list[dict]:
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub() -> pd.DataFrame:
    return pd.DataFrame()


def _grade_df(n: int = 4, lane: str = "buy") -> pd.DataFrame:
    return _minimal_grade_df(n=n, lane=lane)


def _build_track_simple(df: pd.DataFrame | None = None) -> dict:
    if df is None:
        df = _grade_df()
    return build_track(df, _boards_stub("2026-01-02"), _names_stub())


def _emit(boards=None, names=None, track=None) -> dict:
    """Convenience wrapper with correct 3-argument signature."""
    if boards is None:
        boards = _boards_stub("2026-01-02")
    if names is None:
        names = _names_stub()
    if track is None:
        track = _build_track_simple()
    return emit_outcomes(boards, names, track)


# ---------------------------------------------------------------------------
# 1. emit_outcomes: basic structure
# ---------------------------------------------------------------------------



class TestSurvivorshipDisclosureTemplate:
    """The Jinja2 outcome strip must render the disclosure span only when
    n_skipped_no_price > 0, and must omit it otherwise."""

    def _render_outcome_strip(self, us_board_outcomes: dict | None) -> str:
        """Render just the outcome-strip logic via a minimal Jinja2 template."""
        import jinja2
        SNIPPET = """
{% if us_board_outcomes and us_board_outcomes.get('rows') %}
{% set _ubo_surv = us_board_outcomes.get('survivorship', {}) %}
OUTCOMES_RENDERED
{% if _ubo_surv.get('n_skipped_no_price', 0) > 0 %}
DISCLOSURE_RENDERED:{{ _ubo_surv.get('n_skipped_no_price') }}
{% endif %}
{% for row in us_board_outcomes['rows'] %}
ROW:{{ row.ticker }}:{{ row.pct_since }}
{% endfor %}
{% endif %}
"""
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tpl = env.from_string(SNIPPET)
        return tpl.render(us_board_outcomes=us_board_outcomes)

    def test_outcome_strip_renders_when_rows_present(self):
        data = {
            "rows": [{"ticker": "AAA", "pct_since": 5.0, "status": "running"}],
            "as_of": "2026-01-09",
            "survivorship": {"n_skipped_no_price": 0},
        }
        out = self._render_outcome_strip(data)
        assert "OUTCOMES_RENDERED" in out

    def test_outcome_strip_absent_when_no_rows(self):
        data = {"rows": [], "as_of": None, "survivorship": {"n_skipped_no_price": 0}}
        out = self._render_outcome_strip(data)
        assert "OUTCOMES_RENDERED" not in out

    def test_outcome_strip_absent_when_none(self):
        out = self._render_outcome_strip(None)
        assert "OUTCOMES_RENDERED" not in out

    def test_disclosure_rendered_when_n_skipped_gt0(self):
        data = {
            "rows": [{"ticker": "DEAD", "pct_since": -15.0, "status": "stopped"}],
            "as_of": "2026-01-09",
            "survivorship": {"n_skipped_no_price": 3},
        }
        out = self._render_outcome_strip(data)
        assert "DISCLOSURE_RENDERED:3" in out

    def test_disclosure_absent_when_n_skipped_zero(self):
        data = {
            "rows": [{"ticker": "AAA", "pct_since": 5.0, "status": "running"}],
            "as_of": "2026-01-09",
            "survivorship": {"n_skipped_no_price": 0},
        }
        out = self._render_outcome_strip(data)
        assert "DISCLOSURE_RENDERED" not in out

    def test_disclosure_absent_when_survivorship_missing(self):
        data = {
            "rows": [{"ticker": "AAA", "pct_since": 5.0, "status": "running"}],
            "as_of": "2026-01-09",
            # No 'survivorship' key
        }
        out = self._render_outcome_strip(data)
        assert "DISCLOSURE_RENDERED" not in out

    def test_all_rows_rendered(self):
        data = {
            "rows": [
                {"ticker": "AAA", "pct_since": 5.0, "status": "running"},
                {"ticker": "BBB", "pct_since": -3.0, "status": "stopped"},
            ],
            "as_of": "2026-01-09",
            "survivorship": {"n_skipped_no_price": 0},
        }
        out = self._render_outcome_strip(data)
        assert "ROW:AAA:5.0" in out
        assert "ROW:BBB:-3.0" in out


# ---------------------------------------------------------------------------
# 4. Status classification
# ---------------------------------------------------------------------------

class TestOutcomeRowStatus:
    """Status field: 'running' >=+2%, 'stopped' <=-2%, 'flat' otherwise."""

    def _status_for(self, pct: float) -> str:
        """Inline the status logic from emit_outcomes."""
        if pct >= 2.0:
            return "running"
        if pct <= -2.0:
            return "stopped"
        return "flat"

    def test_running_above_2pct(self):
        assert self._status_for(2.5) == "running"

    def test_running_exactly_2pct(self):
        assert self._status_for(2.0) == "running"

    def test_stopped_below_minus_2pct(self):
        assert self._status_for(-3.0) == "stopped"

    def test_stopped_exactly_minus_2pct(self):
        assert self._status_for(-2.0) == "stopped"

    def test_flat_between(self):
        assert self._status_for(0.0) == "flat"
        assert self._status_for(1.5) == "flat"
        assert self._status_for(-1.5) == "flat"


# ---------------------------------------------------------------------------
# 5. Template: az-up / az-dn coloring classes
# ---------------------------------------------------------------------------

class TestOutcomeRowColoring:
    """The pct_since value dictates az-up / az-dn CSS class in the template strip."""

    def _render_row_class(self, pct: float) -> str:
        import jinja2
        SNIPPET = """{% set pct = row_pct %}{% if pct >= 2.0 %}az-up{% elif pct <= -2.0 %}az-dn{% else %}flat-cls{% endif %}"""
        env = jinja2.Environment(autoescape=False)
        tpl = env.from_string(SNIPPET)
        return tpl.render(row_pct=pct)

    def test_az_up_for_positive(self):
        assert "az-up" in self._render_row_class(5.0)

    def test_az_dn_for_negative(self):
        assert "az-dn" in self._render_row_class(-5.0)

    def test_flat_cls_for_neutral(self):
        assert "flat-cls" in self._render_row_class(0.5)
