"""Tests for engine/qledger_ui.py — the D10 honesty chip view-model.

Covers:
  * chip_for_desk: correct state, css_class, label, label_zh for all states
  * absent / None track_record → always UNGRADED chip (never hidden, never error)
  * ACCRUING chip shows correct n/GRADED_MIN_DATES counts
  * GRADED chip with hit_rate → green; without or < 0.5 → red
  * smallest-horizon priority: 5d data shows before 63d data
  * chips_for_desks builds a full mapping, None-safe
  * load_track_record returns {} when file absent (never raises)
  * template smoke: ql_chip macro renders something non-empty for all states
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.qledger import GRADED_MIN_DATES, STATE_ACCRUING, STATE_GRADED, STATE_UNGRADED
from engine.qledger_ui import (
    chip_for_desk,
    chips_for_desks,
    load_track_record,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _tr(desk: str, horizon: int, n_dates: int,
        hit_rate: float | None = None,
        wilson_ci_low: float | None = None) -> dict:
    """Minimal synthetic track_record.json payload for one desk at one horizon."""
    from engine.qledger import derive_state
    state = derive_state(n_dates)
    block = {
        "n_obs": n_dates,
        "n_dates": n_dates,
        "hit_rate": hit_rate,
        "excess_mean": 0.01 if hit_rate and hit_rate >= 0.5 else -0.01,
        "wilson_ci_low": wilson_ci_low,
        "state": state,
    }
    return {
        "generated_at": "2026-07-02T00:00:00+00:00",
        "grade_horizons": [5, 21, 63],
        "graded_min_dates": GRADED_MIN_DATES,
        "by_desk": {desk: {str(horizon): block}},
        "by_family": {},
        "counts": {"n_claims": 1, "n_grades": n_dates, "n_placebo": 0, "n_rejected": 0},
    }


# --------------------------------------------------------------------------- #
# chip_for_desk: UNGRADED
# --------------------------------------------------------------------------- #

class TestChipUngraded:
    def test_absent_track_record_gives_ungraded(self):
        chip = chip_for_desk("alt_data", {})
        assert chip["state"] == STATE_UNGRADED

    def test_none_track_record_gives_ungraded(self):
        chip = chip_for_desk("alt_data", None)
        assert chip["state"] == STATE_UNGRADED

    def test_missing_desk_gives_ungraded(self):
        tr = _tr("other_desk", 5, n_dates=0)
        chip = chip_for_desk("alt_data", tr)
        assert chip["state"] == STATE_UNGRADED

    def test_ungraded_css_class(self):
        chip = chip_for_desk("alt_data", None)
        assert chip["css_class"] == "ql-chip-ungraded"

    def test_ungraded_n_dates_zero(self):
        chip = chip_for_desk("alt_data", None)
        assert chip["n_dates"] == 0

    def test_ungraded_label_contains_n0(self):
        chip = chip_for_desk("alt_data", None)
        assert "n=0" in chip["label"]

    def test_ungraded_label_zh_present(self):
        chip = chip_for_desk("alt_data", None)
        assert chip["label_zh"]

    def test_ungraded_horizon_none(self):
        chip = chip_for_desk("alt_data", None)
        assert chip["horizon_d"] is None


# --------------------------------------------------------------------------- #
# chip_for_desk: ACCRUING
# --------------------------------------------------------------------------- #

class TestChipAccruing:
    def _accruing_chip(self, n_dates: int = 10) -> dict:
        tr = _tr("alt_data", 5, n_dates=n_dates)
        return chip_for_desk("alt_data", tr)

    def test_state_is_accruing(self):
        assert self._accruing_chip(10)["state"] == STATE_ACCRUING

    def test_css_class_is_accruing(self):
        assert self._accruing_chip(10)["css_class"] == "ql-chip-accruing"

    def test_label_shows_counts(self):
        chip = self._accruing_chip(7)
        # Plain-word label: "early — 7d of evidence" — must include n_dates
        # (DESIGN_DOCTRINE Law 2: plain-word state, stats demoted to hover/detail).
        assert "7" in chip["label"]
        # The denominator (GRADED_MIN_DATES) is now demoted to hover/detail tier,
        # not shown in the glance label — confirm n_dates present and label is human.
        assert "evidence" in chip["label"] or "early" in chip["label"]

    def test_label_zh_present(self):
        chip = self._accruing_chip(7)
        assert chip["label_zh"]

    def test_n_dates_matches(self):
        chip = self._accruing_chip(12)
        assert chip["n_dates"] == 12

    def test_horizon_d_set(self):
        chip = self._accruing_chip(10)
        assert chip["horizon_d"] == 5

    def test_boundary_accruing_at_24(self):
        # 24 dates < GRADED_MIN_DATES(25) → still ACCRUING
        chip = self._accruing_chip(24)
        assert chip["state"] == STATE_ACCRUING

    def test_boundary_graded_at_25(self):
        tr = _tr("alt_data", 5, n_dates=25, hit_rate=0.6)
        chip = chip_for_desk("alt_data", tr)
        assert chip["state"] == STATE_GRADED


# --------------------------------------------------------------------------- #
# chip_for_desk: GRADED
# --------------------------------------------------------------------------- #

class TestChipGraded:
    def _graded_chip(self, hit_rate: float | None,
                     wilson_ci_low: float | None = None,
                     n_dates: int = 30) -> dict:
        tr = _tr("alt_data", 5, n_dates=n_dates,
                 hit_rate=hit_rate, wilson_ci_low=wilson_ci_low)
        return chip_for_desk("alt_data", tr)

    def test_graded_positive_css(self):
        chip = self._graded_chip(hit_rate=0.65)
        assert chip["css_class"] == "ql-chip-graded-pos"

    def test_graded_negative_css(self):
        chip = self._graded_chip(hit_rate=0.40)
        assert chip["css_class"] == "ql-chip-graded-neg"

    def test_graded_none_hit_rate_defaults_to_pos(self):
        # no direction claims → hit_rate None → show as positive (not a bad signal)
        chip = self._graded_chip(hit_rate=None)
        assert chip["css_class"] == "ql-chip-graded-pos"

    def test_graded_label_shows_hit_pct(self):
        chip = self._graded_chip(hit_rate=0.72)
        assert "72%" in chip["label"]

    def test_graded_label_shows_ci_when_present(self):
        chip = self._graded_chip(hit_rate=0.72, wilson_ci_low=0.55)
        assert "CI" in chip["label"]
        assert "55%" in chip["label"]

    def test_graded_label_zh_present(self):
        chip = self._graded_chip(hit_rate=0.6)
        assert chip["label_zh"]

    def test_graded_state(self):
        chip = self._graded_chip(hit_rate=0.6)
        assert chip["state"] == STATE_GRADED

    def test_exact_50pct_is_positive(self):
        # hit_rate == 0.5 → not < 0.5 → graded-pos (tie goes to positive)
        chip = self._graded_chip(hit_rate=0.5)
        assert chip["css_class"] == "ql-chip-graded-pos"


# --------------------------------------------------------------------------- #
# smallest-horizon priority
# --------------------------------------------------------------------------- #

class TestHorizonPriority:
    def _multi_horizon_tr(self, h5_dates: int, h21_dates: int,
                          h63_dates: int) -> dict:
        """Track record with data at multiple horizons."""
        from engine.qledger import derive_state

        def _block(n: int) -> dict:
            return {
                "n_obs": n, "n_dates": n,
                "hit_rate": 0.6 if n >= GRADED_MIN_DATES else None,
                "excess_mean": 0.01, "wilson_ci_low": None,
                "state": derive_state(n),
            }

        by_desk = {"alt_data": {}}
        if h5_dates:
            by_desk["alt_data"]["5"] = _block(h5_dates)
        if h21_dates:
            by_desk["alt_data"]["21"] = _block(h21_dates)
        if h63_dates:
            by_desk["alt_data"]["63"] = _block(h63_dates)
        return {
            "by_desk": by_desk, "by_family": {},
            "grade_horizons": [5, 21, 63], "graded_min_dates": GRADED_MIN_DATES,
            "counts": {"n_claims": 1, "n_grades": 1, "n_placebo": 0, "n_rejected": 0},
        }

    def test_prefers_5d_when_available(self):
        tr = self._multi_horizon_tr(h5_dates=10, h21_dates=20, h63_dates=30)
        chip = chip_for_desk("alt_data", tr)
        assert chip["horizon_d"] == 5

    def test_falls_back_to_21d_when_no_5d(self):
        tr = self._multi_horizon_tr(h5_dates=0, h21_dates=15, h63_dates=30)
        chip = chip_for_desk("alt_data", tr)
        assert chip["horizon_d"] == 21

    def test_falls_back_to_63d_when_only_63d(self):
        tr = self._multi_horizon_tr(h5_dates=0, h21_dates=0, h63_dates=30)
        chip = chip_for_desk("alt_data", tr)
        assert chip["horizon_d"] == 63

    def test_no_data_gives_none_horizon(self):
        tr = self._multi_horizon_tr(h5_dates=0, h21_dates=0, h63_dates=0)
        chip = chip_for_desk("alt_data", tr)
        assert chip["horizon_d"] is None


# --------------------------------------------------------------------------- #
# chips_for_desks
# --------------------------------------------------------------------------- #

class TestChipsForDesks:
    def test_all_desks_present(self):
        desks = ["alt_data", "radar", "intel_hub"]
        chips = chips_for_desks(desks, {})
        assert set(chips.keys()) == set(desks)

    def test_empty_track_record_gives_ungraded_for_all(self):
        desks = ["alt_data", "radar"]
        chips = chips_for_desks(desks, {})
        for d in desks:
            assert chips[d]["state"] == STATE_UNGRADED

    def test_none_track_record_safe(self):
        chips = chips_for_desks(["alt_data"], None)
        assert chips["alt_data"]["state"] == STATE_UNGRADED

    def test_populated_desk_chip(self):
        tr = _tr("radar", 21, n_dates=30, hit_rate=0.7)
        chips = chips_for_desks(["alt_data", "radar"], tr)
        assert chips["radar"]["state"] == STATE_GRADED
        assert chips["alt_data"]["state"] == STATE_UNGRADED


# --------------------------------------------------------------------------- #
# load_track_record
# --------------------------------------------------------------------------- #

class TestLoadTrackRecord:
    def test_absent_file_returns_empty(self, tmp_path):
        result = load_track_record(tmp_path)
        assert result == {}

    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "site" / "qledger"
        p.mkdir(parents=True)
        payload = {"by_desk": {}, "counts": {"n_claims": 5}}
        (p / "track_record.json").write_text(json.dumps(payload))
        result = load_track_record(tmp_path)
        assert result["counts"]["n_claims"] == 5

    def test_corrupt_json_returns_empty(self, tmp_path):
        p = tmp_path / "site" / "qledger"
        p.mkdir(parents=True)
        (p / "track_record.json").write_text("{bad json}")
        result = load_track_record(tmp_path)
        assert result == {}

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "site" / "qledger"
        p.mkdir(parents=True)
        (p / "track_record.json").write_text("")
        result = load_track_record(tmp_path)
        assert result == {}


# --------------------------------------------------------------------------- #
# template smoke test
# --------------------------------------------------------------------------- #

class TestTemplateSmokeAltData:
    """Render the alt_data chip macro and confirm chip HTML appears."""

    def _render_chip_macro(self, chip: dict) -> str:
        """Minimal Jinja2 render of just the ql_chip macro from alt_data template."""
        from jinja2 import Environment
        tmpl_src = (
            "{%- macro ql_chip(chip) -%}"
            "{% if chip %}"
            "<span class=\"ql-chip {{ chip.css_class }}\">"
            "<span class=\"l-en\">{{ chip.label }}</span>"
            "<span class=\"l-zh\">{{ chip.label_zh }}</span></span>"
            "{% else %}"
            "<span class=\"ql-chip ql-chip-ungraded\">"
            "<span class=\"l-en\">UNGRADED · n=0</span>"
            "<span class=\"l-zh\">未评级 · n=0</span></span>"
            "{% endif %}"
            "{%- endmacro %}"
            "{{ ql_chip(chip) }}"
        )
        env = Environment(autoescape=False)
        t = env.from_string(tmpl_src)
        return t.render(chip=chip)

    def test_ungraded_chip_renders(self):
        chip = chip_for_desk("alt_data", {})
        html = self._render_chip_macro(chip)
        assert "ql-chip-ungraded" in html
        assert "n=0" in html

    def test_accruing_chip_renders(self):
        tr = _tr("alt_data", 5, n_dates=10)
        chip = chip_for_desk("alt_data", tr)
        html = self._render_chip_macro(chip)
        assert "ql-chip-accruing" in html
        assert "10" in html

    def test_graded_pos_chip_renders(self):
        tr = _tr("alt_data", 5, n_dates=30, hit_rate=0.65)
        chip = chip_for_desk("alt_data", tr)
        html = self._render_chip_macro(chip)
        assert "ql-chip-graded-pos" in html
        assert "65%" in html

    def test_graded_neg_chip_renders(self):
        tr = _tr("alt_data", 5, n_dates=30, hit_rate=0.40)
        chip = chip_for_desk("alt_data", tr)
        html = self._render_chip_macro(chip)
        assert "ql-chip-graded-neg" in html

    def test_none_chip_renders_ungraded(self):
        """When chip is None the macro must fall back to UNGRADED."""
        html = self._render_chip_macro(None)
        assert "ql-chip-ungraded" in html

    def test_bilingual_spans_present(self):
        chip = chip_for_desk("alt_data", {})
        html = self._render_chip_macro(chip)
        assert 'class="l-en"' in html
        assert 'class="l-zh"' in html
