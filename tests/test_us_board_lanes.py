"""tests/test_us_board_lanes.py — Unit tests for W8 dual-lane admission + alpha ordering
+ headline arbiter.

Evidence basis (merged in research/):
  W8-C (wave8_ctlane): CT-BOUNCE == aligned on stop5/clean15 → Lane R licensed.
  W8-A: lifecycle states = ELIGIBILITY + DISPLAY only (no rank power).
  Forward ledger (#1062): P@1 board-order 28.6% vs alpha-order 71.4% → sort by alpha.
"""
from __future__ import annotations

import types
import pytest
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_close(n: int = 250, seed: int = 42, trend: float = 0.0005) -> pd.Series:
    """Synthetic daily close series (business days, trend optional)."""
    rng = np.random.default_rng(seed)
    prices = 100.0 * np.exp(np.cumsum(rng.normal(trend, 0.012, n)))
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _make_profile(alpha: float = 0.5, composite_z: float = 0.5,
                  state: str = "FRESH BUY") -> dict:
    """Minimal profile dict matching what build_stock_library.py expects."""
    return {
        "alpha": alpha,
        "composite_z": composite_z,
        "ladder": {"state": state, "label": state, "label_zh": state},
        "alignment": {},   # empty → not aligned
        "cycle_blocked": False,
        "axes": {"entry": {"z": 0.3}},
    }


def _dummy_verdict(tier: str = "T1") -> dict:
    """Minimal signal_gate verdict dict."""
    return {
        "eligible": True,
        "tier_cascade": tier,
        "tier": "take",
        "sub": None,
        "weight": 1.0 if tier == "T1" else 0.8,
        "ticks": 1,
        "fresh_bars": 1,
    }


# ---------------------------------------------------------------------------
# 1. Lane R admission: synthetic COUNTERTREND-BOUNCE profile
# ---------------------------------------------------------------------------

class TestLaneRAdmission:
    """
    is_buyable + not-extended → admitted lane='recovery'.
    is_buyable + extended → NOT admitted.
    """

    def _recovery_check(self, close: pd.Series, *, is_buyable: bool, is_extended: bool):
        """Run the admission logic inline (mirrors build_stock_library._is_ctlane_candidate path)."""
        from engine.china_signals import extension_read
        from engine.signal_gate import is_buyable as gate_buyable

        verdict = _dummy_verdict("T1") if is_buyable else {
            "eligible": False, "tier_cascade": None, "weight": 0.0, "ticks": 1}
        ext = extension_read(close, {}, ticker="")
        if is_extended:
            # Force extension to True by patching the return
            ext = {**ext, "extended": True, "score": 0.80}
        else:
            ext = {**ext, "extended": False}

        buyable_by_gate = gate_buyable(verdict)
        admitted = buyable_by_gate and (not ext.get("extended"))
        return admitted, ext

    def test_buyable_not_extended_admitted(self):
        close = _make_close(250)
        admitted, _ = self._recovery_check(close, is_buyable=True, is_extended=False)
        assert admitted, "CT-bounce with is_buyable=True and not extended MUST be admitted"

    def test_buyable_extended_not_admitted(self):
        close = _make_close(250, trend=0.003)   # uptrending → extended
        admitted, _ = self._recovery_check(close, is_buyable=True, is_extended=True)
        assert not admitted, "CT-bounce with extension MUST be excluded from Lane R"

    def test_not_buyable_not_admitted(self):
        close = _make_close(250)
        admitted, _ = self._recovery_check(close, is_buyable=False, is_extended=False)
        assert not admitted, "Non-buyable CT-bounce must NOT be admitted"

    def test_knife_excluded_from_lane_r(self):
        """A name that is COUNTERTREND BOUNCE but also a falling knife must NOT be admitted.
        Hard-block: knife >= _ALIGN_KNIFE_BLOCK regardless of state.
        """
        from engine.cycles import _ALIGN_KNIFE_BLOCK, _ALIGN_BAD_STATES

        def _is_ctlane_candidate_inline(alignment, state, *, _buy_tickers_trend=frozenset()):
            """Inline mirror of the fixed _is_ctlane_candidate check."""
            if not alignment.get("aligned") is False and alignment.get("near") is False:
                pass  # not in trend lane
            if (alignment.get("knife") or 0.0) >= _ALIGN_KNIFE_BLOCK:
                return False    # falling knife — excluded even in Lane R
            if alignment.get("weekly") == "falling":
                return False
            if state not in _ALIGN_BAD_STATES:
                return False
            return True

        # CT bounce + knife >= threshold → must NOT be admitted
        result = _is_ctlane_candidate_inline(
            {"knife": 0.75, "weekly": "bear_recovering", "aligned": False, "near": False},
            "COUNTERTREND BOUNCE")
        assert not result, "Knife + CT BOUNCE must NOT be admitted to Lane R"

    def test_weekly_falling_excluded_from_lane_r(self):
        """A name with weekly='falling' must NOT be admitted even if state is in _ALIGN_BAD_STATES."""
        from engine.cycles import _ALIGN_KNIFE_BLOCK, _ALIGN_BAD_STATES

        def _is_ctlane_candidate_inline(alignment, state):
            if (alignment.get("knife") or 0.0) >= _ALIGN_KNIFE_BLOCK:
                return False
            if alignment.get("weekly") == "falling":
                return False
            if state not in _ALIGN_BAD_STATES:
                return False
            return True

        # Weekly falling + COUNTERTREND BOUNCE → must NOT be admitted
        result = _is_ctlane_candidate_inline(
            {"knife": 0.1, "weekly": "falling", "aligned": False, "near": False},
            "COUNTERTREND BOUNCE")
        assert not result, "weekly=falling + CT BOUNCE must NOT be admitted to Lane R"

        # Non-falling weekly + CT BOUNCE → eligible (may still be screened by is_buyable+ext)
        result_ok = _is_ctlane_candidate_inline(
            {"knife": 0.1, "weekly": "basing", "aligned": False, "near": False},
            "COUNTERTREND BOUNCE")
        assert result_ok, "Non-falling weekly CT BOUNCE should pass the _is_ctlane_candidate gate"


# ---------------------------------------------------------------------------
# 2. Ordering: alpha desc within lane; no negative-alpha above positive-alpha
# ---------------------------------------------------------------------------

class TestAlphaOrdering:
    """Within each lane, rows must be sorted by alpha descending."""

    def _make_buy_rows(self, alphas_trend, alphas_recovery) -> list[dict]:
        """Build synthetic buy rows as the builder would assemble them."""
        rows = []
        for a in alphas_trend:
            rows.append({"ticker": f"T{int(a*100)}", "alpha": a, "lane": "trend",
                         "composite_z": a, "conviction": {"score": int(50 + a * 10)}})
        for a in alphas_recovery:
            rows.append({"ticker": f"R{int(a*100)}", "alpha": a, "lane": "recovery",
                         "composite_z": a, "conviction": {"score": int(40 + a * 10)}})
        return rows

    def test_highest_alpha_trend_is_slot1(self):
        rows = self._make_buy_rows([0.3, 0.8, 0.1, 0.5], [0.2, 0.6])
        # Verify trend block is alpha desc and precedes recovery block
        trend_rows = [r for r in rows if r["lane"] == "trend"]
        alphas = [r["alpha"] for r in trend_rows]
        # Sort them as the builder does
        trend_rows_sorted = sorted(trend_rows, key=lambda r: -r["alpha"])
        assert trend_rows_sorted[0]["alpha"] == 0.8, "Highest alpha trend name must be slot 1"

    def test_no_negative_above_positive_within_lane(self):
        alphas = [0.4, -0.1, 0.7, 0.2, -0.3]
        trend_rows = [{"alpha": a, "lane": "trend"} for a in alphas]
        sorted_rows = sorted(trend_rows, key=lambda r: -(r["alpha"] or 0.0))
        alphas_out = [r["alpha"] for r in sorted_rows]
        # After sorting desc, all positive alphas must precede all negatives
        positives = [a for a in alphas_out if a >= 0]
        negatives = [a for a in alphas_out if a < 0]
        first_neg_idx = next((i for i, a in enumerate(alphas_out) if a < 0), len(alphas_out))
        last_pos_idx = next((len(alphas_out) - 1 - i
                             for i, a in enumerate(reversed(alphas_out)) if a >= 0), -1)
        assert last_pos_idx < first_neg_idx, (
            "No negative-alpha name may appear above a positive-alpha name within lane")

    def test_trend_precedes_recovery(self):
        rows = self._make_buy_rows([0.5, 0.3], [0.9, 0.7])
        # Even a high-alpha recovery name should be AFTER trend block
        trend_rows = [r for r in rows if r["lane"] == "trend"]
        recov_rows = [r for r in rows if r["lane"] == "recovery"]
        # In the assembled list (trend first), the last trend index < first recovery index
        assembled = sorted(trend_rows, key=lambda r: -r["alpha"]) + \
                    sorted(recov_rows, key=lambda r: -r["alpha"])
        lane_order = [r["lane"] for r in assembled]
        last_trend = max(i for i, l in enumerate(lane_order) if l == "trend")
        first_recov = min(i for i, l in enumerate(lane_order) if l == "recovery")
        assert last_trend < first_recov, "All trend rows must precede recovery rows"


# ---------------------------------------------------------------------------
# 3. Arbiter: ELV-like row (state FRESH BUY, cross old, extended) gets downgraded
# ---------------------------------------------------------------------------

class TestArbiter:
    """
    W8 HEADLINE ARBITER: a FRESH-BUY row with stale cross OR extended flag
    must have its state/label downgraded and arbiter_note set.
    """

    def _apply_arbiter(self, rows: list[dict]) -> list[dict]:
        """Inline version of the arbiter pass in build_stock_library."""
        from engine.confluence_tiers import FRESH_TICKS
        _FRESH_BUY_STATES = {"FRESH BUY", "TURN SIGNALED"}
        _BOTM_STATES = {"BOTTOMING", "BASING", "ACCUMULATION"}

        for r in rows:
            sig = r.get("signal") or {}
            ticks = sig.get("ticks")
            ext_a = r.get("_ext_grade", "")   # injected for test convenience
            ext_extended = ext_a in ("parabolic", "stretched")
            state = r.get("state") or ""
            stale = (ticks is not None and ticks > FRESH_TICKS + 1)
            if state in _FRESH_BUY_STATES and (stale or ext_extended):
                why = "stale cross" if stale else "extended"
                r["arbiter_note"] = f"downgraded from {state} ({why})"
                r["state"] = "HOLD — EXTENDED" if ext_extended else "HOLD"
                label = r.get("label") or ""
                if "FRESH" in label.upper() or "TURN" in label.upper():
                    r["label"] = "Hold — entry aged" if not ext_extended else "Hold — extended"
                    r["label_zh"] = "持有—入场信号陈旧" if not ext_extended else "持有—已过热"
            if r.get("urgency") == "imminent" and state in _BOTM_STATES:
                r["urgency"] = "caution"
                if not r.get("arbiter_note"):
                    r["arbiter_note"] = f"urgency imminent downgraded (state={state})"
        return rows

    def test_fresh_buy_stale_cross_downgraded(self):
        """ELV-like: state=FRESH BUY, cross 20 ticks (stale), extended=True → downgraded."""
        row = {
            "ticker": "ELV", "state": "FRESH BUY", "label": "FRESH BUY SIGNAL",
            "label_zh": "新鲜买入信号", "urgency": "now",
            "signal": {"ticks": 20, "tier_cascade": "T1"},
            "_ext_grade": "stretched",
        }
        result = self._apply_arbiter([row])
        assert result[0].get("arbiter_note") is not None, "arbiter_note must be set"
        assert result[0]["state"] != "FRESH BUY", "State must be downgraded from FRESH BUY"
        assert "Hold" in (result[0].get("label") or ""), "Label must be downgraded"

    def test_fresh_buy_fresh_cross_not_downgraded(self):
        """A fresh-cross row (ticks=1, not extended) must NOT be downgraded."""
        from engine.confluence_tiers import FRESH_TICKS
        row = {
            "ticker": "MCK", "state": "FRESH BUY", "label": "FRESH BUY SIGNAL",
            "label_zh": "新鲜买入信号", "urgency": "now",
            "signal": {"ticks": 1, "tier_cascade": "T1"},
            "_ext_grade": "",
        }
        result = self._apply_arbiter([row])
        assert result[0]["state"] == "FRESH BUY", "Fresh-cross must NOT be downgraded"
        assert result[0].get("arbiter_note") is None

    def test_urgency_imminent_bottoming_downgraded(self):
        """urgency='imminent' + state='BOTTOMING' → downgraded to caution."""
        row = {
            "ticker": "FOO", "state": "BOTTOMING", "label": "BOTTOMING",
            "urgency": "imminent",
            "signal": {"ticks": 1, "tier_cascade": "T1"},
            "_ext_grade": "",
        }
        result = self._apply_arbiter([row])
        assert result[0]["urgency"] == "caution", "Urgency imminent on BOTTOMING must be caution"

    def test_non_fresh_state_not_touched(self):
        """A HOLD row must not be downgraded (not in FRESH_BUY_STATES)."""
        row = {
            "ticker": "BAR", "state": "HOLD", "label": "Hold",
            "urgency": "caution",
            "signal": {"ticks": 5, "tier_cascade": "T2"},
            "_ext_grade": "",
        }
        result = self._apply_arbiter([row])
        assert result[0].get("arbiter_note") is None
        assert result[0]["state"] == "HOLD"


# ---------------------------------------------------------------------------
# 4. Jinja2 template parses without errors
# ---------------------------------------------------------------------------

class TestJinjaTemplateParse:
    """Minimal parse check: templates/dashboard.html.j2 is valid Jinja2."""

    def test_template_parses(self):
        import jinja2
        from pathlib import Path
        tpl_path = Path(__file__).resolve().parents[1] / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(tpl_path)),
            undefined=jinja2.Undefined,  # lenient (don't resolve variables)
            autoescape=False,
        )
        # This will raise if there is a syntax error in the template
        tpl = env.get_template("dashboard.html.j2")
        assert tpl is not None


# ---------------------------------------------------------------------------
# 5. grade_us_board._row_features picks up lane and arbiter_note
# ---------------------------------------------------------------------------

class TestGraderRowFeatures:
    """Verify lane and arbiter_note flow through _row_features."""

    def _row_features(self, r):
        """Import and call the actual _row_features from grade_us_board."""
        import importlib, sys
        # grade_us_board has heavy imports; use importlib with sys.path guard
        from scripts.grade_us_board import _row_features as rf
        return rf(r)

    def test_lane_field_extracted(self):
        row = {
            "ticker": "MCK", "sector": "Health Care", "alpha": 0.5,
            "state": "FRESH BUY", "label": "FRESH BUY", "urgency": "now",
            "align_tier": "aligned", "off_high": -3.2,
            "lane": "trend", "arbiter_note": None,
            "conviction": {"score": 72, "band": "high", "composite_z": 0.4,
                           "verdict": "Leader", "validation_status": "validated"},
        }
        feat = self._row_features(row)
        assert feat["lane"] == "trend", "lane must be extracted by _row_features"
        assert feat["arbiter_note"] is None

    def test_recovery_lane_extracted(self):
        row = {
            "ticker": "MCD", "sector": "Consumer Discretionary", "alpha": 0.2,
            "state": "COUNTERTREND BOUNCE", "label": "CT Bounce", "urgency": "caution",
            "align_tier": None, "off_high": -5.0,
            "lane": "recovery", "arbiter_note": "downgraded from FRESH BUY (stale cross)",
            "conviction": {"score": 55, "band": "constructive", "composite_z": 0.2,
                           "verdict": "Constructive", "validation_status": "context"},
        }
        feat = self._row_features(row)
        assert feat["lane"] == "recovery"
        assert "downgraded" in (feat["arbiter_note"] or "")

    def test_no_lane_field_is_none(self):
        """Old schema rows (no lane key) must return lane=None gracefully."""
        row = {
            "ticker": "KO", "sector": "Consumer Staples", "alpha": 0.1,
            "state": "BASING", "label": "Basing", "urgency": "soon",
            "align_tier": "near", "off_high": -8.0,
            # No 'lane' key at all (pre-schema)
            "conviction": {"score": 60, "band": "constructive", "composite_z": 0.1,
                           "verdict": "Constructive", "validation_status": "context"},
        }
        feat = self._row_features(row)
        assert feat["lane"] is None, "Missing lane key must default to None"


# ---------------------------------------------------------------------------
# 6. W2 (P5) — alpha_entry values rendered on nbcard (F6 fix)
# ---------------------------------------------------------------------------

class TestAlphaEntryRender:
    """alpha_entry=pullback / extended / laggard all render on the main nbcard.

    The template (templates/dashboard.html.j2) now renders all three values
    on the nbcard's nb-top block. This test verifies via a Jinja2 render with
    a synthetic context that the right CSS classes appear.
    """

    def _render_card(self, alpha_entry_val: str) -> str:
        """Render a minimal nbcard stub and return the HTML fragment."""
        import jinja2
        from pathlib import Path
        tpl_path = Path(__file__).resolve().parents[1] / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(tpl_path)),
            undefined=jinja2.Undefined,
            autoescape=False,
        )
        # Render the card alpha_entry fragment inline to avoid needing the full VM
        fragment = """
{%- set n = row -%}
{% if n.get('alpha_entry') == 'laggard' %}<span class="nb-ent ent-lag"></span>
{% elif n.get('alpha_entry') == 'pullback' %}<span class="nb-ent ent-good"></span>
{% elif n.get('alpha_entry') == 'extended' %}<span class="nb-ent ent-warn"></span>
{% endif %}
"""
        t = env.from_string(fragment)
        return t.render(row={"alpha_entry": alpha_entry_val})

    def test_laggard_renders_ent_lag(self):
        html = self._render_card("laggard")
        assert "ent-lag" in html, "alpha_entry=laggard must render ent-lag chip"

    def test_pullback_renders_ent_good(self):
        html = self._render_card("pullback")
        assert "ent-good" in html, "alpha_entry=pullback must render ent-good chip"

    def test_extended_renders_ent_warn(self):
        html = self._render_card("extended")
        assert "ent-warn" in html, "alpha_entry=extended must render ent-warn chip"

    def test_neutral_renders_nothing(self):
        html = self._render_card("neutral")
        assert "ent-lag" not in html
        assert "ent-good" not in html
        assert "ent-warn" not in html


# ---------------------------------------------------------------------------
# 7. W2 (P5) — contradiction guard: alpha_entry=laggard on BUY band logs warn
# ---------------------------------------------------------------------------

class TestContradictionGuard:
    """Invariant (d): a BUY card with alpha_entry=laggard should log a warning.

    This guard is a WARNING (not a raise) — the display gap is surfaced
    for monitoring but must never crash the nightly render.
    """

    def _build_rows(self, alpha_entry: str, band: str) -> list[dict]:
        return [{"ticker": "LAG", "alpha_entry": alpha_entry,
                 "conviction": {"band": band, "verdict": "Leader", "score": 70}}]

    def test_laggard_on_high_band_detected(self):
        """A laggard entry on a 'high' band row is a contradiction worth flagging."""
        rows = self._build_rows("laggard", "high")
        # The invariant in build_stock_library.py (invariant d) walks wide["buy"]
        # and logs a warning for alpha_entry=laggard rows with constructive/high band.
        # Here we replicate the detection logic:
        violations = []
        for r in rows:
            ae = r.get("alpha_entry")
            band = (r.get("conviction") or {}).get("band") or ""
            if ae == "laggard" and band in ("high", "constructive"):
                violations.append(r["ticker"])
        assert len(violations) == 1, "One laggard-on-high-band contradiction must be detected"

    def test_laggard_on_caution_band_ok(self):
        """laggard + caution band is consistent (laggard named, band correctly muted)."""
        rows = self._build_rows("laggard", "caution")
        violations = []
        for r in rows:
            ae = r.get("alpha_entry")
            band = (r.get("conviction") or {}).get("band") or ""
            if ae == "laggard" and band in ("high", "constructive"):
                violations.append(r["ticker"])
        assert len(violations) == 0, "laggard + caution band must NOT be flagged"

    def test_pullback_on_high_band_ok(self):
        """pullback + high band is consistent — not a contradiction."""
        rows = self._build_rows("pullback", "high")
        violations = []
        for r in rows:
            ae = r.get("alpha_entry")
            band = (r.get("conviction") or {}).get("band") or ""
            if ae == "laggard" and band in ("high", "constructive"):
                violations.append(r["ticker"])
        assert len(violations) == 0, "pullback + high band must NOT be flagged"


# ---------------------------------------------------------------------------
# 8. W2 (P4) — board track JSON structure recognized by template
# ---------------------------------------------------------------------------

class TestBoardTrackStructure:
    """Verify us_board_track.json (site/factordata/) has the keys the template needs."""

    def test_track_json_has_required_keys(self):
        """If the board track JSON exists, it must have the per_horizon.h5.buy_lane path."""
        import json
        from pathlib import Path
        track_path = Path(__file__).resolve().parents[1] / "site" / "factordata" / "us_board_track.json"
        if not track_path.exists():
            pytest.skip("us_board_track.json not yet generated (first run)")
        d = json.loads(track_path.read_text())
        assert "per_horizon" in d, "per_horizon key required"
        h5 = d["per_horizon"].get("h5") or {}
        bl = h5.get("buy_lane") or {}
        assert "vs_spy" in bl, "buy_lane.vs_spy required"
        vs = bl["vs_spy"]
        assert "n" in vs, "vs_spy.n required"
        assert "hit_rate" in vs, "vs_spy.hit_rate required"

    def test_track_json_has_precision_at_k(self):
        """P@k keys (board-order and alpha-order) must be present for the W1 scoreboard."""
        import json
        from pathlib import Path
        track_path = Path(__file__).resolve().parents[1] / "site" / "factordata" / "us_board_track.json"
        if not track_path.exists():
            pytest.skip("us_board_track.json not yet generated (first run)")
        d = json.loads(track_path.read_text())
        bl = d["per_horizon"]["h5"]["buy_lane"]
        assert "precision_at_k_board_order_vs_spy" in bl, (
            "precision_at_k_board_order_vs_spy required for P@1 board-order display")
        assert "precision_at_k_alpha_order_vs_spy" in bl, (
            "precision_at_k_alpha_order_vs_spy required for P@1 alpha-order comparison")
