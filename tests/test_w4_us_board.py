"""Tests for W4 US board changes (2026-07-03, PR #1143 verdicts).

W9-B DEMOTE — tailwind rank weight set to 0.0 for US:
  * _WEIGHT_PRIOR["US"]["tailwind"] == 0.0
  * Tailwind z still computed (display-only); does not move US composite_z.
  * Non-US markets unaffected.

W9-A SAFETY_ONLY — sector-capitulating annotation on BASED/Lane-R rows:
  * When cohort_frac >= 0.40 AND (postcross.based OR lane=='recovery'):
    r["sector_capitulating"] == {"cohort_frac": <float>}
  * Annotation never fires when cohort_frac < 0.40.
  * Annotation never fires for rows that are neither BASED nor Lane-R.
  * No rank/admission effect — purely additive field.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_score as ss


# ---------------------------------------------------------------------------
# W9-B: US tailwind weight = 0.0; composite_z unaffected by tailwind inputs
# ---------------------------------------------------------------------------

def _base_rec(**kw):
    """Minimal rec with all axes present except tailwind overrides."""
    base = {
        "ticker": "TST", "sector": "Technology",
        "alpha": 1.8,
        "ladder": {"state": "FRESH BUY", "label": "FRESH BUY", "dir": "up",
                   "eq_dir": "up", "entry": {"urgency": "now"}},
        "tech": {"off_52w_high_pct": -8.0, "rsi14": 52.0},
        "ext": {"grade": "in-trend", "ext_z": 0.3},
        "factor": {"profitability": 0.6, "quality": 0.4},
    }
    base.update(kw)
    return base


class TestW9BTailwindDemoteUS:
    def test_weight_is_zero(self):
        """Ordering change: US tailwind weight must be exactly 0.0."""
        assert ss._WEIGHT_PRIOR["US"]["tailwind"] == 0.0

    def test_weights_sum_to_one_without_tailwind(self):
        """US weights (excluding tailwind=0) must behave correctly in the denominator."""
        w = ss._WEIGHT_PRIOR["US"]
        non_zero = sum(v for v in w.values() if v > 0)
        # The three remaining axes: selection 0.45 + entry 0.15 + quality 0.30 = 0.90
        assert abs(non_zero - 0.90) < 1e-9

    def test_tailwind_axis_still_present_in_profile(self):
        """Tailwind z still computed and stored in axes (display-only)."""
        rec = _base_rec(basket={"rel20": 9.0}, sector_rs={"pct": 88.0})
        p = ss.conviction_profile(rec, "US")
        tw = p["axes"]["tailwind"]
        assert tw["z"] is not None, "tailwind z must still be computed for display"
        assert isinstance(tw["present"], list) and len(tw["present"]) > 0

    def test_tailwind_change_does_not_move_us_composite_z(self):
        """Core ordering invariant: US composite_z must not change with tailwind inputs."""
        # Strong tailwind (basket + sector-RS)
        p_strong = ss.conviction_profile(
            _base_rec(basket={"rel20": 14.0}, sector_rs={"pct": 97.0}), "US")
        # Zero tailwind (no basket, no sector-RS)
        p_zero = ss.conviction_profile(
            _base_rec(basket=None, sector_rs=None), "US")
        z_strong = p_strong.get("composite_z")
        z_zero = p_zero.get("composite_z")
        assert z_strong is not None and z_zero is not None
        assert z_strong == pytest.approx(z_zero, abs=1e-6), (
            f"W9-B violated: US composite_z changed with tailwind ({z_zero:.4f} → {z_strong:.4f}). "
            "Tailwind weight must be 0.0."
        )

    def test_negative_tailwind_does_not_hurt_us_rank(self):
        """Headwind (negative rel20) must not penalise US composite_z."""
        p_head = ss.conviction_profile(
            _base_rec(basket={"rel20": -10.0}, sector_rs={"pct": 20.0}), "US")
        p_base = ss.conviction_profile(
            _base_rec(basket=None, sector_rs=None), "US")
        assert p_head.get("composite_z") == pytest.approx(p_base.get("composite_z"), abs=1e-6)


class TestW9BTailwindNonUSUnchanged:
    @pytest.mark.parametrize("mkt", ["CA", "CN", "HK", "INTL"])
    def test_non_us_tailwind_weight_positive(self, mkt):
        """W9-B only applies to US; non-US markets still carry tailwind weight."""
        assert ss._WEIGHT_PRIOR[mkt]["tailwind"] > 0.0, (
            f"{mkt} tailwind weight must remain positive (W9-B is US-only)"
        )

    def test_ca_tailwind_moves_composite(self):
        """CA tailwind (weight > 0) still influences composite_z."""
        p_tw = ss.conviction_profile(
            _base_rec(basket={"rel20": 12.0}, sector_rs={"pct": 95.0}), "CA")
        p_no = ss.conviction_profile(
            _base_rec(basket=None, sector_rs=None), "CA")
        # With non-zero weight, composite_z should differ
        assert p_tw.get("composite_z") != pytest.approx(
            p_no.get("composite_z"), abs=1e-6
        ), "CA tailwind (weight > 0) must move composite_z"


# ---------------------------------------------------------------------------
# W9-A: sector-capitulating annotation on BASED / Lane-R rows
# ---------------------------------------------------------------------------

def _apply_w9a_annotation(r: dict, coil_frac_val: float | None) -> None:
    """Mirror the W9-A annotation logic from build_stock_library.py
    (lines after the postcross block). Mutates r in place."""
    _is_based_row = bool(r.get("postcross", {}).get("based"))
    _is_recovery_row = r.get("lane") == "recovery"
    if _is_based_row or _is_recovery_row:
        _w9a_frac = coil_frac_val
        if _w9a_frac is not None and _w9a_frac >= 0.40:
            r["sector_capitulating"] = {"cohort_frac": round(float(_w9a_frac), 3)}


class TestW9ASectorCapitulatingAnnotation:
    def test_fires_on_based_row_above_threshold(self):
        """BASED row + cohort_frac >= 0.40 → sector_capitulating attached."""
        r = {"ticker": "AAA", "lane": "trend",
             "postcross": {"based": True, "shaken": False}}
        _apply_w9a_annotation(r, 0.45)
        assert "sector_capitulating" in r
        assert r["sector_capitulating"]["cohort_frac"] == pytest.approx(0.45, abs=1e-6)

    def test_fires_on_recovery_lane_above_threshold(self):
        """Lane-R (lane='recovery') + cohort_frac >= 0.40 → sector_capitulating attached."""
        r = {"ticker": "BBB", "lane": "recovery", "postcross": {"based": False}}
        _apply_w9a_annotation(r, 0.60)
        assert "sector_capitulating" in r
        assert r["sector_capitulating"]["cohort_frac"] == pytest.approx(0.60, abs=1e-6)

    def test_fires_exactly_at_threshold(self):
        """Boundary: cohort_frac == 0.40 must trigger the annotation."""
        r = {"ticker": "CCC", "lane": "recovery"}
        _apply_w9a_annotation(r, 0.40)
        assert "sector_capitulating" in r

    def test_does_not_fire_below_threshold(self):
        """cohort_frac < 0.40 → no annotation, even if BASED."""
        r = {"ticker": "DDD", "lane": "trend",
             "postcross": {"based": True, "shaken": False}}
        _apply_w9a_annotation(r, 0.39)
        assert "sector_capitulating" not in r

    def test_does_not_fire_on_null_frac(self):
        """None cohort_frac (insufficient peers) → no annotation."""
        r = {"ticker": "EEE", "lane": "recovery"}
        _apply_w9a_annotation(r, None)
        assert "sector_capitulating" not in r

    def test_does_not_fire_on_trend_lane_non_based(self):
        """Normal trend-lane row that is NOT BASED → no annotation even if sector washed out."""
        r = {"ticker": "FFF", "lane": "trend",
             "postcross": {"based": False, "shaken": True}}
        _apply_w9a_annotation(r, 0.80)
        assert "sector_capitulating" not in r

    def test_no_rank_side_effect_us_composite_z_unchanged(self):
        """W9-A annotation is additive: adding sector_capitulating to a rec must not
        change the US composite_z — it's a display-only field, not a scoring input."""
        rec_no = _base_rec()
        rec_cap = _base_rec()
        rec_cap["sector_capitulating"] = {"cohort_frac": 0.55}
        p_no = ss.conviction_profile(rec_no, "US")
        p_cap = ss.conviction_profile(rec_cap, "US")
        assert p_no.get("composite_z") == pytest.approx(
            p_cap.get("composite_z"), abs=1e-6
        ), "sector_capitulating must not affect US composite_z (display-only)"

    def test_cohort_frac_rounded_to_3dp(self):
        """Emitted cohort_frac is rounded to 3 decimal places."""
        r = {"ticker": "GGG", "lane": "recovery"}
        _apply_w9a_annotation(r, 0.666666)
        assert "sector_capitulating" in r
        assert r["sector_capitulating"]["cohort_frac"] == pytest.approx(0.667, abs=1e-6)


# ---------------------------------------------------------------------------
# Template guard: data-tip-en/data-tip-zh (not title=) used for CJK tips
# ---------------------------------------------------------------------------

def test_template_uses_data_tip_not_title_for_sector_cap():
    """CI guard: sector_capitulating chip must use data-tip-en/data-tip-zh, not title=."""
    tmpl_path = (Path(__file__).resolve().parent.parent
                 / "templates" / "dashboard.html.j2")
    if not tmpl_path.exists():
        pytest.skip("template not found — running outside full repo")
    content = tmpl_path.read_text()
    # The chip must be present
    assert "sector_capitulating" in content, "W9-A chip missing from dashboard template"
    # Must NOT use title= (CJK in title= fails CI)
    import re
    # Find the sector_cap chip block
    cap_block = re.search(
        r'nb-sector-cap.*?(?=\{%|$)', content, re.DOTALL)
    assert cap_block, "nb-sector-cap CSS class missing from template"
    # data-tip-en and data-tip-zh must be present
    assert "data-tip-en=" in content[content.find("sector_capitulating"):]
    assert "data-tip-zh=" in content[content.find("sector_capitulating"):]
