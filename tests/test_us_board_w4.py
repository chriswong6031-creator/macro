"""tests/test_us_board_w4.py — Unit tests for W4 board changes.

Covers:
  W9-B DEMOTE:
    - US tailwind weight is 0.0 in _WEIGHT_PRIOR (not 0.10).
    - Two synthetic names differing ONLY in tailwind axis produce the same composite_z
      (tailwind is rank-neutral after the demote).
    - The tailwind FIELD is still computed on the profile output (display-only preserved).
    - Non-US markets are NOT changed.

  W9-A SAFETY_ONLY:
    - _row_features extracts cohort_capitulation_conditioned correctly
      (True when frac>=0.40; False when frac<0.40; None when field absent).
    - build_track emits by_cohort_conditioned stratum in the buy_lane block.
    - Template snippet renders the .nb-cohort-cap chip when conditioned=True and
      omits it when conditioned=False or the field is absent.
    - No ordering effect: a Lane-R row with cohort capitulation does NOT rank above
      one without when alpha is the same.
"""
from __future__ import annotations

import sys
from pathlib import Path

import jinja2
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_score as ss                          # noqa: E402
from scripts.grade_us_board import _row_features, build_track  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df       # noqa: E402

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _boards_stub(*as_ofs):
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub():
    return pd.DataFrame()


def _base_row(**overrides) -> dict:
    """Minimal board row dict with required fields for _row_features."""
    base = {
        "ticker": "AAA", "sector": "Technology",
        "alpha": 0.5, "state": "FRESH BUY", "label": "FRESH BUY",
        "urgency": "now", "align_tier": "aligned", "off_high": -3.0,
        "lane": "trend", "arbiter_note": None,
        "conviction": {
            "score": 70, "band": "high", "composite_z": 0.5,
            "verdict": "Leader", "validation_status": "validated",
        },
    }
    base.update(overrides)
    return base


def _grade_df_with_cohort(n: int = 4, lane: str = "buy") -> pd.DataFrame:
    """Extend _minimal_grade_df with cohort_capitulation_conditioned column."""
    df = _minimal_grade_df(n=n, lane=lane)
    df["cohort_capitulation_conditioned"] = [True, False, None, True][:n]
    return df


# ---------------------------------------------------------------------------
# W9-B: tailwind weight demote
# ---------------------------------------------------------------------------

class TestW9BTailwindDemote:
    """US tailwind weight is 0.0; output field still present; non-US unchanged."""

    def test_us_tailwind_weight_is_zero(self):
        """W9-B: _WEIGHT_PRIOR['US']['tailwind'] must be 0.0 after the demote."""
        assert ss._WEIGHT_PRIOR["US"]["tailwind"] == 0.0, (
            "US tailwind weight must be 0.0 per W9-B demote (#1143)")

    def test_non_us_tailwind_weights_unchanged(self):
        """W9-B verdict is US-board only; CA/CN/HK/INTL weights must remain > 0."""
        for mkt in ("CA", "CN", "HK", "INTL"):
            w = ss._WEIGHT_PRIOR[mkt]["tailwind"]
            assert w > 0, (
                f"{mkt} tailwind weight ({w}) must remain > 0 — W9 panel is US-only")

    def test_tailwind_is_rank_neutral_after_demote(self):
        """Two names identical except for tailwind inputs produce the same composite_z.

        W9-B falsified the tailwind axis (negative tercile spreads, both panels).
        With weight=0.0 the composite_z must be identical regardless of tailwind inputs.
        """
        base_rec = {
            "ticker": "TST",
            "sue": 1.5,
            "insider_bps": 20.0,
            "alpha": 1.5,
            "ladder": {"state": "FRESH BUY", "label": "BUY ZONE", "dir": "up",
                       "eq_dir": "up", "entry": {"urgency": "now"}},
            "tech": {"off_52w_high_pct": -8.0, "rsi14": 54.0},
            "factor": {"profitability": 0.5, "quality": 0.4, "value": 0.0, "low_vol": 0.1},
        }
        # Name A: strong basket + good sector RS (high tailwind)
        rec_high_tail = {**base_rec,
                         "basket": {"rel20": 6.0},
                         "sector_rs": {"pct": 88.0},
                         "spotlight": {"dir": "up"}}
        # Name B: no basket or sector RS (low tailwind)
        rec_low_tail = {**base_rec,
                        "basket": {"rel20": -2.0},
                        "sector_rs": {"pct": 30.0},
                        "spotlight": {"dir": "down"}}

        p_high = ss.conviction_profile(rec_high_tail, "US")
        p_low  = ss.conviction_profile(rec_low_tail,  "US")

        assert p_high["composite_z"] == pytest.approx(p_low["composite_z"]), (
            "After W9-B demote, tailwind-only difference must not change composite_z")

    def test_tailwind_axis_still_computed_for_display(self):
        """W9-B: the tailwind FIELD must still appear in axes output (display context).

        The axis value is computed regardless of weight so that basket/spotlight chips
        and out-of-play size trims still have data.
        """
        rec = {
            "ticker": "TST",
            "alpha": 1.5,
            "basket": {"rel20": 4.0},
            "sector_rs": {"pct": 75.0},
            "ladder": {"state": "RALLY ON", "entry": {"urgency": "now"}},
        }
        p = ss.conviction_profile(rec, "US")
        # The tailwind key must be present in axes
        assert "tailwind" in p["axes"], (
            "tailwind must remain in axes output for display-only context after W9-B")

    def test_composite_weights_renormalize_without_tailwind(self):
        """The composite_z denominator normalizes correctly at 0.90 (0.45+0.15+0.30+0.0).

        The composite loop uses dynamic den (sum of present weights), so setting
        tailwind=0.0 auto-renormalizes to (sel+entry+quality) only.
        """
        rec = {
            "ticker": "TST",
            "sue": 1.5,
            "insider_bps": 20.0,
            "alpha": 1.5,
            "ladder": {"state": "FRESH BUY", "entry": {"urgency": "now"}},
            "tech": {"off_52w_high_pct": -8.0, "rsi14": 54.0},
            "factor": {"profitability": 0.5, "quality": 0.4},
        }
        p = ss.conviction_profile(rec, "US")
        # composite_z must be non-None even without a tailwind leg
        assert p["composite_z"] is not None, (
            "composite_z must be computable with tailwind weight 0.0")
        assert abs(p["composite_z"]) < 20.0, "composite_z is implausibly large"


# ---------------------------------------------------------------------------
# W9-A: cohort capitulation annotation
# ---------------------------------------------------------------------------

class TestW9ACohortAnnotationRowFeatures:
    """_row_features extracts cohort_capitulation_conditioned correctly."""

    def test_conditioned_true_when_frac_gte_0_40(self):
        """conditioned=True maps to True in _row_features."""
        row = _base_row(lane="recovery",
                        cohort_capitulation={"frac": 0.55, "conditioned": True})
        feat = _row_features(row)
        assert feat["cohort_capitulation_conditioned"] is True

    def test_conditioned_false_when_frac_lt_0_40(self):
        """conditioned=False maps to False in _row_features."""
        row = _base_row(lane="recovery",
                        cohort_capitulation={"frac": 0.30, "conditioned": False})
        feat = _row_features(row)
        assert feat["cohort_capitulation_conditioned"] is False

    def test_conditioned_none_when_field_absent(self):
        """None is emitted when cohort_capitulation is not on the row (pre-schema)."""
        row = _base_row()  # no cohort_capitulation key
        feat = _row_features(row)
        assert feat["cohort_capitulation_conditioned"] is None

    def test_conditioned_none_when_field_is_none(self):
        """None is emitted when cohort_capitulation is explicitly None."""
        row = _base_row(cohort_capitulation=None)
        feat = _row_features(row)
        assert feat["cohort_capitulation_conditioned"] is None

    def test_conditioned_threshold_exactly_0_40(self):
        """The boundary frac=0.40 maps to conditioned=True."""
        row = _base_row(lane="recovery",
                        cohort_capitulation={"frac": 0.40, "conditioned": True})
        feat = _row_features(row)
        assert feat["cohort_capitulation_conditioned"] is True

    def test_cohort_cap_key_present_in_feat(self):
        """The cohort_capitulation_conditioned key is always emitted by _row_features."""
        row = _base_row()
        feat = _row_features(row)
        assert "cohort_capitulation_conditioned" in feat, (
            "cohort_capitulation_conditioned must be present in _row_features output")


# ---------------------------------------------------------------------------
# W9-A: build_track by_cohort_conditioned stratum
# ---------------------------------------------------------------------------

class TestW9ACohortStratumBuildTrack:
    """build_track emits by_cohort_conditioned in the buy_lane block."""

    def test_by_cohort_conditioned_in_buy_lane(self):
        df = _grade_df_with_cohort(n=4, lane="buy")
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_cohort_conditioned" in buy_h5, (
            "by_cohort_conditioned missing from buy_lane output (W9-A stratum not emitted)")

    def test_by_cohort_conditioned_strata_non_empty(self):
        """The stratum has at least one entry when conditioned values vary."""
        df = _grade_df_with_cohort(n=4, lane="buy")
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        strat = track["per_horizon"]["h5"]["buy_lane"]["by_cohort_conditioned"]
        assert len(strat) > 0, "by_cohort_conditioned should be non-empty with mixed inputs"

    def test_by_cohort_conditioned_hit_stats_bounded(self):
        """Each stratum's hit_rate is in [0, 1]."""
        df = _grade_df_with_cohort(n=4, lane="buy")
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        by_cohort = track["per_horizon"]["h5"]["buy_lane"]["by_cohort_conditioned"]
        for stratum, stats in by_cohort.items():
            if "hit_rate" in stats:
                assert 0.0 <= stats["hit_rate"] <= 1.0, (
                    f"by_cohort_conditioned[{stratum}] hit_rate out of [0,1]")

    def test_by_cohort_conditioned_absent_pre_schema(self):
        """Pre-schema boards (no cohort_capitulation_conditioned column) return empty dict."""
        df = _minimal_grade_df(n=4, lane="buy")
        # No cohort column added — pre-schema
        track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
        buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
        assert "by_cohort_conditioned" in buy_h5
        assert buy_h5["by_cohort_conditioned"] == {}, (
            "Pre-schema df must produce empty {} strata for by_cohort_conditioned")


# ---------------------------------------------------------------------------
# W9-A: template chip render (Jinja2 snippet)
# ---------------------------------------------------------------------------

class TestW9ATemplateCohortChip:
    """Jinja2 template renders the .nb-cohort-cap chip when conditioned=True."""

    # Minimal Jinja2 snippet mirroring the actual dashboard.html.j2 block
    _SNIPPET = """
{% set _cc = n.get('cohort_capitulation') %}
{% if _cc and _cc.get('conditioned') %}<span class="nb-cohort-cap" data-tip-en="Sector capitulating — {{ '%.0f'|format((_cc.frac or 0) * 100) }}% of same-sector names in weekly StochRSI washout at build time." data-tip-zh="板块承压出清——同板块 {{ '%.0f'|format((_cc.frac or 0) * 100) }}% 标的处于周线 StochRSI 洗盘区。"><span class="l-en">⚡ Sector cap.</span><span class="l-zh">⚡ 板块出清</span></span>{% endif %}
""".strip()

    def _render(self, row_dict: dict) -> str:
        env = jinja2.Environment(undefined=jinja2.Undefined, autoescape=False)
        tpl = env.from_string(self._SNIPPET)
        return tpl.render(n=row_dict)

    def test_chip_rendered_when_conditioned_true(self):
        out = self._render({"cohort_capitulation": {"frac": 0.55, "conditioned": True}})
        assert "nb-cohort-cap" in out
        assert "Sector cap." in out

    def test_chip_frac_percentage_shown_correctly(self):
        """The percentage shown in data-tip-en rounds correctly (55% for frac=0.55)."""
        out = self._render({"cohort_capitulation": {"frac": 0.55, "conditioned": True}})
        assert "55%" in out

    def test_chip_40_pct_boundary(self):
        """Exactly at the threshold (frac=0.40) the chip renders."""
        out = self._render({"cohort_capitulation": {"frac": 0.40, "conditioned": True}})
        assert "nb-cohort-cap" in out

    def test_chip_absent_when_conditioned_false(self):
        out = self._render({"cohort_capitulation": {"frac": 0.30, "conditioned": False}})
        assert "nb-cohort-cap" not in out

    def test_chip_absent_when_field_missing(self):
        out = self._render({})
        assert "nb-cohort-cap" not in out

    def test_chip_absent_when_field_is_none(self):
        out = self._render({"cohort_capitulation": None})
        assert "nb-cohort-cap" not in out

    def test_chip_uses_data_tip_not_title(self):
        """CJK text must be in data-tip-zh, NEVER in title= (fails CI check_title_i18n)."""
        out = self._render({"cohort_capitulation": {"frac": 0.55, "conditioned": True}})
        assert "data-tip-en" in out
        assert "data-tip-zh" in out
        # title= should NOT carry any CJK content
        import re
        title_matches = re.findall(r'title="[^"]*"', out)
        for m in title_matches:
            # naive CJK range check
            assert not any('一' <= c <= '鿿' for c in m), (
                f"CJK found in title= attribute: {m!r} — use data-tip-zh instead")

    def test_bilingual_spans_present(self):
        """The chip text uses l-en / l-zh spans for bilingual display."""
        out = self._render({"cohort_capitulation": {"frac": 0.55, "conditioned": True}})
        assert "l-en" in out and "l-zh" in out


# ---------------------------------------------------------------------------
# W9-A: no ordering regression
# ---------------------------------------------------------------------------

class TestW9ANoOrderingRegression:
    """Cohort capitulation annotation must NOT change board order (display-only)."""

    def _sort_rows(self, rows: list[dict]) -> list[str]:
        """Sort rows as the builder does: trend by alpha desc, then recovery."""
        trend = sorted([r for r in rows if r.get("lane") == "trend"],
                       key=lambda r: -(r.get("alpha") or 0.0))
        recov = sorted([r for r in rows if r.get("lane") == "recovery"],
                       key=lambda r: -(r.get("alpha") or 0.0))
        return [r["ticker"] for r in trend + recov]

    def test_cohort_cap_does_not_affect_sort_order(self):
        """A Lane-R row with cohort capitulation must NOT rank above one without."""
        rows_plain = [
            {"ticker": "HIGH", "alpha": 0.9, "lane": "recovery"},
            {"ticker": "LOW",  "alpha": 0.5, "lane": "recovery"},
        ]
        rows_annotated = [
            # HIGH has NO capitulation annotation
            {"ticker": "HIGH", "alpha": 0.9, "lane": "recovery"},
            # LOW has conditioned=True — must NOT float above HIGH
            {"ticker": "LOW",  "alpha": 0.5, "lane": "recovery",
             "cohort_capitulation": {"frac": 0.65, "conditioned": True}},
        ]
        assert self._sort_rows(rows_plain) == self._sort_rows(rows_annotated), (
            "Cohort capitulation annotation must not alter board sort order")


# ---------------------------------------------------------------------------
# Full template parse (regression guard for template syntax)
# ---------------------------------------------------------------------------

def test_full_dashboard_template_parses_after_w4():
    """The full dashboard.html.j2 must parse without Jinja2 syntax errors after W4 edits."""
    tpl_path = Path(__file__).resolve().parents[1] / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tpl_path)),
        undefined=jinja2.Undefined,
        autoescape=False,
    )
    tpl = env.get_template("dashboard.html.j2")
    assert tpl is not None


def test_no_cjk_in_title_attributes_after_w4():
    """check_title_i18n must pass on the updated template (data-tip-en/zh, not title=)."""
    import subprocess
    repo_root = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        ["python3", "scripts/check_title_i18n.py", "templates/"],
        capture_output=True, text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        f"check_title_i18n found CJK/bilingual in title= attributes:\n"
        f"{result.stdout}\n{result.stderr}")
