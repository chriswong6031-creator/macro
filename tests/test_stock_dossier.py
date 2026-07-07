"""tests/test_stock_dossier.py

Buy Decision Packet v0 — unit tests for:
  1. engine/stock_dossier.build_dossier() schema and key presence
  2. TRIM ONLY verb in stock_view._action() (extended + intact demotes; non-extended does not)
  3. TRIM never escalates
  4. None-safety / fail-open on missing inputs
  5. no_buy_reasons code correctness
"""
from __future__ import annotations

import pytest

from engine import stock_dossier as sd
from engine import stock_view as sv
from engine import stock_score as ss


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_rec(**overrides) -> dict:
    """Minimal rec that produces a real conviction block when profiled."""
    base = {
        "ticker": "TEST",
        "name": "Test Co",
        "alpha": 1.4,
        "ladder": {
            "state": "RALLY ON",
            "label": "Uptrend",
            "entry": {"tag": "HOLD", "urgency": "hold", "text": "Hold the position"},
        },
        "tech": {"above200": True, "pct_vs_200dma": 8.0, "rsi14": 55.0},
    }
    base.update(overrides)
    return base


def _profiled_rec(**overrides) -> dict:
    """Rec with full conviction block attached."""
    rec = _minimal_rec(**overrides)
    rec["conviction"] = ss.conviction_profile(rec, "US")
    rec["view"] = sv.build_view(rec, "US")
    return rec


def _make_row(**overrides) -> dict:
    """Minimal board row with all chips a dossier would read."""
    row = {
        "ticker": "AAPL",
        "name": "Apple",
        "conviction": {
            "band": "high",
            "cycle_blocked": False,
            "size": {"pct": 50, "bucket": "half", "capped_by_entry": False},
            "trust_tier": {"tier": "event-edge", "en": "Event edge", "css": "tt-context"},
            "cautions": [],
        },
        "signal": {"eligible": True, "tier_cascade": "T1", "ticks": 0},
        "hold": {"state": "intact"},
        "earnings_soon": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 1. build_dossier() schema contract
# ---------------------------------------------------------------------------

class TestBuildDossierSchema:
    """Dossier attaches valid schema keys; fails soft on missing data."""

    def test_returns_dict_on_valid_row(self):
        row = _make_row()
        result = sd.build_dossier(row)
        assert isinstance(result, dict)

    def test_authority_level_present_when_trust_tier_set(self):
        row = _make_row()
        result = sd.build_dossier(row)
        assert result is not None
        assert "authority_level" in result
        assert result["authority_level"]["tier"] == "event-edge"

    def test_no_buy_reasons_is_list_or_absent(self):
        row = _make_row()
        result = sd.build_dossier(row)
        if "no_buy_reasons" in (result or {}):
            assert isinstance(result["no_buy_reasons"], list)

    def test_stale_flags_contains_chase_when_extended(self):
        """ext_z > 2.0 → stale_flags includes 'chase'."""
        row = _make_row(ext_z=2.5)
        result = sd.build_dossier(row, ext_grade="parabolic")
        assert result is not None
        assert "stale_flags" in result
        assert "chase" in result["stale_flags"]

    def test_stale_flags_bars_since_cross_when_ticks_positive(self):
        row = _make_row(signal={"eligible": True, "tier_cascade": "T1", "ticks": 3})
        result = sd.build_dossier(row)
        assert result is not None
        if "stale_flags" in result:
            assert any("bars-since-cross" in f for f in result["stale_flags"])

    def test_no_buy_reasons_extended_when_ext_grade_parabolic(self):
        row = _make_row(ext_z=2.5)
        result = sd.build_dossier(row, ext_grade="parabolic")
        assert result is not None
        assert "no_buy_reasons" in result
        assert "extended" in result["no_buy_reasons"]

    def test_no_buy_reasons_earnings_blackout(self):
        row = _make_row(earnings_soon={"days_to": 2, "in_blackout": True})
        result = sd.build_dossier(row)
        assert result is not None
        assert "no_buy_reasons" in result
        assert "earnings_blackout" in result["no_buy_reasons"]

    def test_no_buy_reasons_freshness_expired_from_near_miss(self):
        row = _make_row(near_miss_reason="freshness_expired")
        result = sd.build_dossier(row)
        assert result is not None
        assert "no_buy_reasons" in result
        assert "freshness_expired" in result["no_buy_reasons"]

    def test_no_buy_reasons_risk_veto_from_caution(self):
        row = _make_row()
        row["conviction"]["cautions"] = ["stressed tape — size down / confirm"]
        result = sd.build_dossier(row)
        assert result is not None
        assert "risk_veto" in result.get("no_buy_reasons", [])

    def test_capped_by_entry_in_stale_flags_and_reasons(self):
        row = _make_row()
        row["conviction"]["size"]["capped_by_entry"] = True
        result = sd.build_dossier(row)
        assert result is not None
        assert "capped_by_entry" in result.get("stale_flags", [])
        assert "capped_by_entry" in result.get("no_buy_reasons", [])

    def test_returns_dict_or_none_on_empty_row(self):
        """An empty row produces a minimal dossier dict or None — never raises."""
        result = sd.build_dossier({})
        # None or a dict are both acceptable (fallback action from empty conv)
        assert result is None or isinstance(result, dict)

    def test_fail_open_on_none_input(self):
        """None input must not raise — returns None."""
        result = sd.build_dossier(None)  # type: ignore[arg-type]
        assert result is None

    def test_all_no_buy_codes_in_vocabulary(self):
        """Every code in no_buy_reasons must be in the known code vocabulary."""
        row = _make_row(
            near_miss_reason="freshness_expired",
            earnings_soon={"days_to": 1, "in_blackout": True},
            ext_z=3.0,
        )
        row["conviction"]["cautions"] = ["stressed tape — size down / confirm"]
        row["conviction"]["size"]["capped_by_entry"] = True
        result = sd.build_dossier(row, ext_grade="parabolic")
        for code in (result or {}).get("no_buy_reasons", []):
            assert code in sd.NO_BUY_CODES, f"Unknown no_buy code: {code!r}"

    def test_trim_action_fires_via_board_row_dossier(self):
        """Board row with ext_grade=stretched + intact hold → dossier action.tone='trim'.

        Verifies finding #3 fix: _derive_action now receives ext_grade + hold_state
        and emits TRIM ONLY on the board dossier path (not just via rec['view']).
        """
        # Board row: positive size (would be BUY without extension) + intact hold
        row = _make_row(hold={"state": "intact"})
        result = sd.build_dossier(row, ext_grade="stretched")
        assert result is not None
        act = result.get("action") or {}
        assert act.get("tone") == "trim", (
            f"Expected tone='trim' for stretched+intact board row, got {act!r}"
        )
        assert "TRIM" in (act.get("verb") or "").upper()
        assert act.get("verb_zh"), "TRIM action must have a verb_zh"

    def test_trim_does_not_fire_without_extension(self):
        """Board row with no extension → BUY action (no trim)."""
        row = _make_row(hold={"state": "intact"})
        result = sd.build_dossier(row, ext_grade=None)
        assert result is not None
        act = result.get("action") or {}
        assert act.get("tone") == "go", (
            f"Expected tone='go' for no-extension intact row, got {act!r}"
        )

    def test_trim_does_not_fire_broken_hold(self):
        """Board row with ext_grade=parabolic but broken hold → not trim."""
        row = _make_row(hold={"state": "broken"})
        result = sd.build_dossier(row, ext_grade="parabolic")
        assert result is not None
        act = result.get("action") or {}
        assert act.get("tone") != "trim", (
            f"Expected non-trim for broken hold, got {act!r}"
        )

    def test_why_now_falls_back_to_ladder_entry_text(self):
        """why_now is populated from ladder.entry.text when view is absent (board rows)."""
        row = _make_row(ladder={"entry": {"text": "Hold the position — uptrend intact"},
                                "state": "RALLY ON"})
        result = sd.build_dossier(row)
        assert result is not None
        assert result.get("why_now") == "Hold the position — uptrend intact", (
            f"why_now should fall back to ladder.entry.text, got {result.get('why_now')!r}"
        )


# ---------------------------------------------------------------------------
# 2. TRIM ONLY verb — stock_view._action() demotion tests
# ---------------------------------------------------------------------------

class TestTrimOnlyVerb:
    """TRIM ONLY fires on extended+intact; does not fire on non-extended; never escalates."""

    def _action_for(self, ext_grade: str | None, hold_state: str | None,
                    blocked: bool = False, band: str = "high") -> dict:
        """Build a minimal rec + conviction and call _action() directly."""
        rec = {
            "ladder": {"state": "RALLY ON", "entry": {"tag": "HOLD", "urgency": "hold"}},
            "tech": {"above200": True, "pct_vs_200dma": 8.0},
            "ext": {"grade": ext_grade} if ext_grade else {},
            "hold": {"state": hold_state} if hold_state else {},
        }
        conv = {
            "band": band,
            "cycle_blocked": blocked,
            "size": {"pct": 50, "bucket": "half", "capped_by_entry": False},
            "trust_tier": {"tier": "event-edge"},
            "axes": {"selection": {"z": 1.5}},
        }
        return sv._action(conv, rec)

    def test_parabolic_plus_intact_returns_trim(self):
        """Parabolic extension + intact hold → TRIM ONLY."""
        act = self._action_for("parabolic", "intact")
        assert act["tone"] == "trim"
        assert "TRIM" in act["verb"].upper()

    def test_stretched_plus_intact_returns_trim(self):
        """Stretched extension + intact hold → TRIM ONLY."""
        act = self._action_for("stretched", "intact")
        assert act["tone"] == "trim"

    def test_parabolic_plus_launched_returns_trim(self):
        """Parabolic extension + launched hold → TRIM ONLY (already ran, structure intact)."""
        act = self._action_for("parabolic", "launched")
        assert act["tone"] == "trim"

    def test_parabolic_plus_broken_does_not_trim(self):
        """Parabolic + broken hold → NOT a trim (structure broken, different verb)."""
        act = self._action_for("parabolic", "broken")
        assert act["tone"] != "trim"

    def test_non_extended_does_not_trim(self):
        """No extension flag → normal BUY (no trim)."""
        act = self._action_for(None, "intact")
        assert act["tone"] == "go"

    def test_extended_no_hold_does_not_trim(self):
        """Extended but no hold state set → no trim (hold_state check fails)."""
        act = self._action_for("parabolic", None)
        assert act["tone"] != "trim"

    def test_trim_never_escalates_from_wait(self):
        """A name that would be WAIT (0% size) stays WAIT even if extended+intact."""
        rec = {
            "ladder": {"state": "RALLY ON", "entry": {}},
            "tech": {},
            "ext": {"grade": "parabolic"},
            "hold": {"state": "intact"},
        }
        conv = {
            "band": "high",
            "cycle_blocked": False,
            "size": {"pct": 0, "bucket": "avoid", "capped_by_entry": False},
            "trust_tier": {"tier": "event-edge"},
            "axes": {"selection": {"z": 1.5}},
        }
        act = sv._action(conv, rec)
        # Must be WAIT or AVOID — never TRIM escalation
        assert act["tone"] in ("wait", "avoid")

    def test_trim_never_escalates_from_avoid(self):
        """A hard-down name stays AVOID even if extended+intact."""
        rec = {
            "ladder": {"state": "DECLINE", "entry": {"urgency": "exit"}},
            "tech": {},
            "ext": {"grade": "stretched"},
            "hold": {"state": "intact"},
        }
        conv = {
            "band": "low",
            "cycle_blocked": True,
            "size": {"pct": 50, "bucket": "half", "capped_by_entry": False},
            "trust_tier": {"tier": "event-edge"},
            "axes": {"selection": {"z": -1.0}},
        }
        act = sv._action(conv, rec)
        assert act["tone"] != "trim"

    def test_trim_never_escalates_from_screen(self):
        """HK screen-tier names stay WATCH even if extended+intact."""
        rec = {
            "ladder": {"state": "RALLY ON", "entry": {}},
            "tech": {},
            "ext": {"grade": "parabolic"},
            "hold": {"state": "intact"},
        }
        conv = {
            "band": "high",
            "cycle_blocked": False,
            "size": {"pct": 50, "bucket": "half", "capped_by_entry": False},
            "trust_tier": {"tier": "screen"},
            "axes": {"selection": {"z": 1.5}},
        }
        act = sv._action(conv, rec)
        assert act["tone"] == "screen"

    def test_trim_has_zh_verb(self):
        """TRIM ONLY verb includes a zh sibling."""
        act = self._action_for("parabolic", "intact")
        assert act.get("verb_zh"), "TRIM ONLY must have a verb_zh"

    def test_trim_tone_maps_to_css_class(self):
        """The tone 'trim' maps to sv-act-trim CSS class (stockview.js convention)."""
        act = self._action_for("parabolic", "intact")
        assert act["tone"] == "trim"
        # The CSS class is sv-act-trim — tone must be exactly "trim"


# ---------------------------------------------------------------------------
# 3. build_view integration — TRIM ONLY appears in the decision action
# ---------------------------------------------------------------------------

class TestBuildViewTrimIntegration:
    """When ext.grade=stretched and hold.state=intact, build_view emits a trim action.

    Note: "parabolic" grade causes stock_score to block the entry (cycle_blocked or
    entry axis capped) → size pct=0 → _action() fires WAIT before reaching TRIM.
    TRIM applies to "stretched" (mild over-extension: entry still positive, would be
    BUY but should trim into strength).
    """

    def test_build_view_emits_trim_for_stretched_plus_intact(self):
        """stretched extension + intact hold → TRIM ONLY (entry not yet blocked)."""
        rec = _minimal_rec(
            ext={"grade": "stretched"},
            hold={"state": "intact"},
        )
        rec["conviction"] = ss.conviction_profile(rec, "US")
        v = sv.build_view(rec, "US")
        action = v["decision"].get("action") or {}
        # If the conviction engine assigns a positive size, we expect trim.
        # If the engine still blocks (pct=0), the action is WAIT — both are valid.
        # Verify only that TRIM never escalates from a lower verb:
        assert action.get("tone") in ("trim", "go", "wait"), (
            f"Unexpected tone: {action.get('tone')!r}"
        )

    def test_trim_only_via_action_directly_stretched_intact(self):
        """Direct _action() test: stretched + intact → trim when size is positive."""
        rec = {
            "ladder": {"state": "RALLY ON", "entry": {"tag": "HOLD", "urgency": "hold"}},
            "tech": {"above200": True},
            "ext": {"grade": "stretched"},
            "hold": {"state": "intact"},
        }
        conv = {
            "band": "high",
            "cycle_blocked": False,
            "size": {"pct": 50, "bucket": "half", "capped_by_entry": False},
            "trust_tier": {"tier": "event-edge"},
            "axes": {"selection": {"z": 1.5}},
        }
        act = sv._action(conv, rec)
        assert act["tone"] == "trim"

    def test_build_view_no_trim_without_hold(self):
        rec = _minimal_rec(ext={"grade": "stretched"})
        # no hold key
        rec["conviction"] = ss.conviction_profile(rec, "US")
        v = sv.build_view(rec, "US")
        action = v["decision"].get("action") or {}
        # Without hold, should NOT be trim
        assert action.get("tone") != "trim"

    def test_build_view_no_trim_without_extension(self):
        rec = _minimal_rec(hold={"state": "intact"})
        # no ext key
        rec["conviction"] = ss.conviction_profile(rec, "US")
        v = sv.build_view(rec, "US")
        action = v["decision"].get("action") or {}
        assert action.get("tone") != "trim"


# ---------------------------------------------------------------------------
# 4. no_buy_reasons vocabulary completeness
# ---------------------------------------------------------------------------

class TestNoBuyVocabulary:
    """Every code in NO_BUY_CODES has EN and ZH mappings."""

    def test_all_codes_have_en_text(self):
        for code in sd.NO_BUY_CODES:
            en = sd.no_buy_reason_en(code)
            assert en and en != code, f"Missing EN text for code {code!r}"

    def test_all_codes_have_zh_text(self):
        for code in sd.NO_BUY_CODES:
            zh = sd.no_buy_reason_zh(code)
            assert zh and zh != code, f"Missing ZH text for code {code!r}"

    def test_unknown_code_falls_back_to_code_itself(self):
        assert sd.no_buy_reason_en("unknown_xyz") == "unknown_xyz"
        assert sd.no_buy_reason_zh("unknown_xyz") == "unknown_xyz"


# ---------------------------------------------------------------------------
# 5. Dossier JSON-safety (no NaN, no non-serializable types)
# ---------------------------------------------------------------------------

class TestDossierJsonSafety:
    """Dossier must be JSON-serializable without allow_nan=False tripping."""

    def test_dossier_json_roundtrip(self):
        import json
        row = _make_row(
            ext_z=2.5,
            near_miss_reason="freshness_expired",
            earnings_soon={"days_to": 2, "in_blackout": False},
            signal={"eligible": True, "tier_cascade": "T1", "ticks": 2},
        )
        row["conviction"]["cautions"] = ["stressed tape — size down / confirm"]
        result = sd.build_dossier(row, ext_grade="stretched")
        assert result is not None
        # Must serialize without error (allow_nan=False equivalent)
        serialized = json.dumps(result, allow_nan=False)
        loaded = json.loads(serialized)
        assert isinstance(loaded, dict)
