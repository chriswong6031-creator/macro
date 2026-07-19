"""Tests for engine.rates_inflation_command — Forward Path board.

Pure-function unit tests; no network access; file-reading tests use tmp_path.
Mirrors the style of tests/test_transmission_context.py.

Run: python3 -m pytest tests/test_rates_command.py -x -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.rates_inflation_command import (  # noqa: E402
    build_board,
    compact_state,
    diff_changes,
    build_changes,
    compose_stance,
    _compute_net_state,
    _render_cuts,
    H1_HAWKISH_THRESHOLD_BP,
    H1_DOVISH_THRESHOLD_BP,
    D1_GAP_BP_THRESHOLD,
    D3_IMPLIED_BP_LOW,
    D3_IMPLIED_BP_HIGH,
    _NET_STATE_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers to build synthetic compact states
# ---------------------------------------------------------------------------

def _cs(
    net_state="two_sided",
    hawk_score=0,
    ease_score=0,
    curve_regime="bear_steepener",
    anchoring="anchored",
    infl_dir="steady",
    implied_bp_12m=10,
) -> dict:
    return {
        "net_state": net_state,
        "hawk_score": hawk_score,
        "ease_score": ease_score,
        "curve_regime": curve_regime,
        "anchoring": anchoring,
        "infl_dir": infl_dir,
        "usd_dir": None,
        "implied_bp_12m": implied_bp_12m,
    }


# ---------------------------------------------------------------------------
# 1. Net-state machine — every branch exhaustively
# ---------------------------------------------------------------------------

class TestNetState:
    def test_repricing_hawkish_requires_h1_and_net_ge_2(self):
        state = _compute_net_state(
            hawk_score=4, ease_score=1, zq_d20_bp=20.0, h1_active=True
        )
        assert state == "repricing_hawkish"

    def test_repricing_hawkish_h1_active_exactly_net_2(self):
        state = _compute_net_state(
            hawk_score=3, ease_score=1, zq_d20_bp=20.0, h1_active=True
        )
        assert state == "repricing_hawkish"

    def test_pressure_building_when_h1_not_active_but_net_ge_2(self):
        state = _compute_net_state(
            hawk_score=4, ease_score=1, zq_d20_bp=5.0, h1_active=False
        )
        assert state == "pressure_building"

    def test_pressure_building_h1_none_net_ge_2(self):
        # H1 unavailable (None) — not active, but net >=2 -> pressure_building
        state = _compute_net_state(
            hawk_score=3, ease_score=1, zq_d20_bp=None, h1_active=None
        )
        assert state == "pressure_building"

    def test_repricing_dovish_mirror_d20_le_minus15_net_ease_ge_2(self):
        state = _compute_net_state(
            hawk_score=1, ease_score=4, zq_d20_bp=-20.0, h1_active=False
        )
        assert state == "repricing_dovish"

    def test_pressure_fading_no_dovish_h1_mirror(self):
        state = _compute_net_state(
            hawk_score=0, ease_score=3, zq_d20_bp=-5.0, h1_active=False
        )
        assert state == "pressure_fading"

    def test_pressure_fading_h1_none_ease_ge_2(self):
        state = _compute_net_state(
            hawk_score=0, ease_score=2, zq_d20_bp=None, h1_active=None
        )
        assert state == "pressure_fading"

    def test_two_sided_small_net(self):
        state = _compute_net_state(
            hawk_score=2, ease_score=2, zq_d20_bp=5.0, h1_active=False
        )
        assert state == "two_sided"

    def test_two_sided_zero_scores(self):
        state = _compute_net_state(
            hawk_score=0, ease_score=0, zq_d20_bp=0.0, h1_active=False
        )
        assert state == "two_sided"

    def test_repricing_hawkish_h1_false_blocks_repricing(self):
        # hawk-ease=4 but H1 not active -> pressure_building not repricing_hawkish
        state = _compute_net_state(
            hawk_score=5, ease_score=1, zq_d20_bp=5.0, h1_active=False
        )
        assert state == "pressure_building"

    def test_pressure_fading_not_dovish_when_d20_flat(self):
        state = _compute_net_state(
            hawk_score=1, ease_score=4, zq_d20_bp=0.0, h1_active=False
        )
        assert state == "pressure_fading"

    def test_net_state_labels_complete(self):
        """Every net_state key has EN+ZH labels."""
        for key in ["repricing_hawkish", "pressure_building",
                    "repricing_dovish", "pressure_fading", "two_sided"]:
            lbl = _NET_STATE_LABELS[key]
            assert "en" in lbl and "zh" in lbl
            assert lbl["en"] and lbl["zh"]
            assert "consensus" not in lbl["en"].lower()
            assert "共识" not in lbl["zh"]
            assert "validated" not in lbl["en"].lower()


# ---------------------------------------------------------------------------
# 2. Cuts/hikes sign rendering
# ---------------------------------------------------------------------------

class TestRenderCuts:
    def test_minus2_is_two_hikes(self):
        result = _render_cuts(-2)
        assert "hike" in result["en"].lower()
        assert "two" in result["en"].lower()
        assert "加息" in result["zh"]

    def test_plus2_is_two_cuts(self):
        result = _render_cuts(2)
        assert "cut" in result["en"].lower()
        assert "two" in result["en"].lower()
        assert "降息" in result["zh"]

    def test_zero_is_hold(self):
        result = _render_cuts(0)
        assert "hold" in result["en"].lower()
        assert "按兵" in result["zh"]

    def test_minus1_is_one_hike(self):
        result = _render_cuts(-1)
        assert "hike" in result["en"].lower()
        assert "one" in result["en"].lower()

    def test_plus1_is_one_cut(self):
        result = _render_cuts(1)
        assert "cut" in result["en"].lower()
        assert "one" in result["en"].lower()

    def test_minus3_is_three_hikes(self):
        result = _render_cuts(-3)
        assert "hike" in result["en"].lower()
        assert "three" in result["en"].lower()

    def test_none_is_unclear(self):
        result = _render_cuts(None)
        assert "unclear" in result["en"].lower() or "unclear" in result["en"]

    def test_small_fraction_is_hold(self):
        # 0.3 rounds to 0 -> hold
        result = _render_cuts(0.3)
        assert "hold" in result["en"].lower()


# ---------------------------------------------------------------------------
# 3. D1-D3 threshold checks (unit-test values, not build_board)
# ---------------------------------------------------------------------------

class TestDivergenceThresholds:
    def test_d1_threshold_constant(self):
        assert D1_GAP_BP_THRESHOLD == 50.0

    def test_d3_low_threshold(self):
        assert D3_IMPLIED_BP_LOW == 0.0

    def test_d3_high_threshold(self):
        assert D3_IMPLIED_BP_HIGH == 25.0

    def test_h1_hawkish_threshold(self):
        assert H1_HAWKISH_THRESHOLD_BP == 15.0

    def test_h1_dovish_threshold(self):
        assert H1_DOVISH_THRESHOLD_BP == -15.0


# ---------------------------------------------------------------------------
# 4. build_changes same-day idempotency
# ---------------------------------------------------------------------------

class TestBuildChanges:
    def _make_contract(self, asof, net_state="two_sided", hawk=0, ease=0) -> dict:
        return {
            "asof": asof,
            "expectations_pressure": {
                "net_state": net_state,
                "hawk_score": hawk,
                "ease_score": ease,
            },
            "board": {
                "rate_path_row": {"implied_bp_12m": 10},
                "inflation_row": {"anchoring": "anchored", "direction": "steady"},
                "risk_row": {"curve_regime_key": "bear_steepener"},
                "policy_row": {},
            },
            "changes": {"vs_asof": None, "items": []},
            "prev_state": {"as_of": None, "state": {}},
        }

    def test_first_run_no_old_returns_empty_changes(self):
        new = self._make_contract("2026-07-18")
        changes, prev = build_changes(None, new, "2026-07-18")
        assert changes["items"] == []
        assert changes["vs_asof"] is None
        assert prev["as_of"] is None

    def test_new_day_diffs_old_vs_new(self):
        old = self._make_contract("2026-07-17", net_state="two_sided")
        new = self._make_contract("2026-07-18", net_state="repricing_hawkish")
        changes, prev = build_changes(old, new, "2026-07-18")
        # There is a net_state diff
        assert any(item["key"] == "net_state" for item in changes["items"])
        assert changes["vs_asof"] == "2026-07-17"

    def test_same_day_reuses_prev_state(self):
        """Same-day rebuild reuses the stored prev_state (not old compact)."""
        old = self._make_contract("2026-07-18", net_state="two_sided")
        # Store a prev_state from yesterday
        old["prev_state"] = {
            "as_of": "2026-07-17",
            "state": _cs(net_state="pressure_building"),
        }
        new = self._make_contract("2026-07-18", net_state="repricing_hawkish")
        changes, prev = build_changes(old, new, "2026-07-18")
        # vs_asof should be the stored prev_state.as_of (2026-07-17)
        assert changes["vs_asof"] == "2026-07-17"
        # prev_state should be the stored one
        assert prev["as_of"] == "2026-07-17"

    def test_same_day_no_stored_prev_emits_empty(self):
        old = self._make_contract("2026-07-18", net_state="two_sided")
        # old has empty prev_state (first of the day)
        new = self._make_contract("2026-07-18", net_state="repricing_hawkish")
        changes, prev = build_changes(old, new, "2026-07-18")
        assert changes["items"] == []


# ---------------------------------------------------------------------------
# 5. diff_changes direction tests
# ---------------------------------------------------------------------------

class TestDiffChanges:
    def test_net_state_change_detected(self):
        prev = _cs(net_state="two_sided")
        curr = _cs(net_state="repricing_hawkish")
        items = diff_changes(prev, curr)
        assert any(i["key"] == "net_state" for i in items)

    def test_no_change_returns_empty(self):
        cs = _cs(net_state="two_sided", hawk_score=2, ease_score=2)
        assert diff_changes(cs, cs) == []

    def test_max_6_items_enforced(self):
        prev = _cs(net_state="two_sided", hawk_score=0, ease_score=0,
                   curve_regime="flat", anchoring="anchored",
                   infl_dir="steady", implied_bp_12m=10)
        curr = _cs(net_state="pressure_building", hawk_score=5, ease_score=1,
                   curve_regime="bear_steepener", anchoring="strained",
                   infl_dir="re-accelerating", implied_bp_12m=40)
        items = diff_changes(prev, curr)
        assert len(items) <= 6

    def test_none_to_value_skipped(self):
        prev = _cs(net_state=None)
        curr = _cs(net_state="two_sided")
        items = diff_changes(prev, curr)
        assert not any(i["key"] == "net_state" for i in items)

    def test_bilingual_items(self):
        prev = _cs(net_state="two_sided")
        curr = _cs(net_state="repricing_hawkish")
        items = diff_changes(prev, curr)
        for item in items:
            assert "en" in item and "zh" in item


# ---------------------------------------------------------------------------
# 6. Fail-open: missing artifacts -> all legs null, no raise, artifact emits
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_empty_root_no_raise(self, tmp_path):
        """Point build_board at an empty tmp dir — should return valid artifact, not raise."""
        result = build_board(root=tmp_path)
        assert isinstance(result, dict)
        assert result["display_only"] is True
        assert result["authority"] is False
        assert "expectations_pressure" in result
        ep = result["expectations_pressure"]
        # Legs that REQUIRE an absent artifact must be active=None (fail-open).
        # Legs that can return a definite False without input data are allowed to.
        # Key legs that need ZQ parquet / market_state / yield_curve:
        null_expected = {"H1_path_repricing", "H2_breakeven_momentum", "H5_curve_regime",
                         "H6_anchoring_strain", "E1_equity_deleveraging", "E4_credit_stress",
                         "E5_policy_easing_chain"}
        for leg in ep["legs"]:
            if leg["key"] in null_expected:
                assert leg.get("active") is None, f"Expected null leg (empty root): {leg['key']}"
        # net_state should be two_sided (all null -> 0 vs 0)
        assert ep["net_state"] == "two_sided"
        # stance should still exist
        assert "stance" in result
        assert "en" in result["stance"]
        # caveats should mention missing data
        assert any("absent" in c.lower() or "unavailable" in c.lower() or "missing" in c.lower()
                   for c in result.get("caveats", [])), result["caveats"]

    def test_no_raise_on_corrupt_json(self, tmp_path):
        """Corrupt bond_health.json -> still returns artifact."""
        bonds_dir = tmp_path / "bonds"
        bonds_dir.mkdir()
        (bonds_dir / "bond_health.json").write_text("NOT JSON")
        result = build_board(root=tmp_path)
        assert isinstance(result, dict)
        assert result["authority"] is False


# ---------------------------------------------------------------------------
# 7. Word-ban scans over emitted strings and keys
# ---------------------------------------------------------------------------

def _walk_strings(obj, path="root") -> list[tuple[str, str]]:
    """Walk dict/list recursively, yield (path, string_value) for all strings."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            results.extend(_walk_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            results.extend(_walk_strings(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        results.append((path, obj))
    return results


def _walk_keys(obj, path="root") -> list[str]:
    """Walk dict recursively, yield all key names as strings."""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_walk_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_walk_keys(item, path))
    return keys


class TestWordBans:
    @pytest.fixture(scope="class")
    def live_artifact(self):
        """Build artifact against real data (if available) or empty root."""
        try:
            return build_board()
        except Exception:
            return None

    def test_no_consensus_in_strings(self, live_artifact):
        if live_artifact is None:
            pytest.skip("No live artifact")
        for path, s in _walk_strings(live_artifact):
            assert "consensus" not in s.lower(), f"Banned word 'consensus' at {path}: {s!r}"
            assert "共识" not in s, f"Banned word '共识' at {path}: {s!r}"

    def test_no_validated_in_strings(self, live_artifact):
        if live_artifact is None:
            pytest.skip("No live artifact")
        for path, s in _walk_strings(live_artifact):
            assert "validated" not in s.lower(), f"Banned word 'validated' at {path}: {s!r}"

    def test_naming_law_keys_no_forbidden_substrings(self, live_artifact):
        if live_artifact is None:
            pytest.skip("No live artifact")
        forbidden = ["forecast", "predicted", "expected_return"]
        for key in _walk_keys(live_artifact):
            for f in forbidden:
                assert f not in key.lower(), (
                    f"Naming-law violation: key '{key}' contains banned substring '{f}'"
                )

    def test_no_consensus_in_empty_root_artifact(self, tmp_path):
        artifact = build_board(root=tmp_path)
        for path, s in _walk_strings(artifact):
            assert "consensus" not in s.lower(), f"Banned word 'consensus' at {path}: {s!r}"
            assert "共识" not in s, f"Banned word '共识' at {path}: {s!r}"
            assert "validated" not in s.lower(), f"Banned word 'validated' at {path}: {s!r}"

    def test_naming_law_empty_root(self, tmp_path):
        artifact = build_board(root=tmp_path)
        forbidden = ["forecast", "predicted", "expected_return"]
        for key in _walk_keys(artifact):
            for f in forbidden:
                assert f not in key.lower(), (
                    f"Naming-law violation: key '{key}' contains banned substring '{f}'"
                )


# ---------------------------------------------------------------------------
# 8. Schema structure tests
# ---------------------------------------------------------------------------

class TestSchema:
    @pytest.fixture(scope="class")
    def artifact(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("empty")
        return build_board(root=tmp)

    def test_schema_key(self, artifact):
        assert artifact["schema"] == "rates_command.v1"

    def test_display_only_true(self, artifact):
        assert artifact["display_only"] is True

    def test_authority_false(self, artifact):
        assert artifact["authority"] is False

    def test_board_has_four_rows(self, artifact):
        board = artifact["board"]
        assert "rate_path_row" in board
        assert "inflation_row" in board
        assert "risk_row" in board
        assert "policy_row" in board

    def test_expectations_pressure_structure(self, artifact):
        ep = artifact["expectations_pressure"]
        assert "legs" in ep
        assert "hawk_score" in ep
        assert "ease_score" in ep
        assert "net_state" in ep
        assert "state_label" in ep
        assert "en" in ep["state_label"] and "zh" in ep["state_label"]

    def test_eleven_legs_total(self, artifact):
        ep = artifact["expectations_pressure"]
        keys = [l["key"] for l in ep["legs"]]
        hawkish = [k for k in keys if k.startswith("H")]
        easing = [k for k in keys if k.startswith("E")]
        assert len(hawkish) == 6, f"Expected 6 hawkish legs, got {hawkish}"
        assert len(easing) == 5, f"Expected 5 easing legs, got {easing}"

    def test_divergence_has_three_flags(self, artifact):
        div = artifact["divergence"]
        keys = [d["key"] for d in div]
        assert "D1_dots_vs_market" in keys
        assert "D2_projection_vs_breakeven" in keys
        assert "D3_pressure_vs_market" in keys

    def test_stance_bilingual(self, artifact):
        stance = artifact["stance"]
        assert "en" in stance and "zh" in stance
        assert isinstance(stance["en"], str)
        assert isinstance(stance["zh"], str)

    def test_market_check_structure(self, artifact):
        mc = artifact["market_check"]
        assert "futures" in mc
        assert "benchmark_note_en" in mc
        assert "benchmark_note_zh" in mc

    def test_caveats_includes_futures_caveat(self, artifact):
        caveats = artifact["caveats"]
        assert any("futures" in c.lower() and "risk premium" in c.lower()
                   for c in caveats), f"Missing futures risk-premium caveat: {caveats}"

    def test_risk_row_real_speed_note(self, artifact):
        risk_row = artifact["board"]["risk_row"]
        note = risk_row.get("real_speed_note_en", "")
        assert "flags risk" in note.lower() or "risk" in note.lower()
        assert "not return" in note.lower()

    def test_risk_row_term_premium_note(self, artifact):
        risk_row = artifact["board"]["risk_row"]
        note = risk_row.get("term_premium_note_en", "")
        assert "kim-wright" in note.lower()
        assert "acm" in note.lower()


# ---------------------------------------------------------------------------
# 9. Leg structure validation
# ---------------------------------------------------------------------------

class TestLegStructure:
    @pytest.fixture(scope="class")
    def legs(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("empty2")
        artifact = build_board(root=tmp)
        return artifact["expectations_pressure"]["legs"]

    def test_all_legs_have_required_keys(self, legs):
        required = {"key", "active", "weight", "value", "detail_en", "detail_zh", "null_reason"}
        for leg in legs:
            missing = required - set(leg.keys())
            assert not missing, f"Leg {leg.get('key')} missing keys: {missing}"

    def test_null_legs_have_null_reason(self, legs):
        for leg in legs:
            if leg["active"] is None:
                assert leg["null_reason"] is not None and leg["null_reason"] != "", (
                    f"Leg {leg['key']} has active=None but null_reason is empty"
                )

    def test_active_legs_no_null_reason(self, legs):
        for leg in legs:
            if leg["active"] is not None:
                # null_reason should be None (or empty) for definite legs
                assert leg["null_reason"] is None or leg["null_reason"] == "", (
                    f"Leg {leg['key']} has active={leg['active']} but non-empty null_reason: {leg['null_reason']}"
                )


# ---------------------------------------------------------------------------
# 10. forward_log lane gate: local run should NOT create the log
# ---------------------------------------------------------------------------

class TestForwardLogLane:
    def test_forward_log_not_created_without_nightly_lane(self, tmp_path, monkeypatch):
        """builder must NOT write forward_log.jsonl unless lane == 'nightly'."""
        import os
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)

        # Build an artifact against empty root (won't write meaningful data)
        from scripts.build_rates_command import _append_forward_log
        artifact = {
            "asof": "2026-07-18",
            "expectations_pressure": {"net_state": "two_sided", "hawk_score": 0, "ease_score": 0},
            "divergence": [],
            "board": {"rate_path_row": {}},
        }
        log_path = tmp_path / "rates_command" / "forward_log.jsonl"
        _append_forward_log(tmp_path / "rates_command", artifact)
        assert not log_path.exists(), "forward_log.jsonl must NOT exist without nightly lane"

    def test_forward_log_created_with_nightly_lane(self, tmp_path, monkeypatch):
        """builder MUST write forward_log.jsonl when lane == 'nightly'."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        from scripts.build_rates_command import _append_forward_log
        artifact = {
            "asof": "2026-07-18",
            "expectations_pressure": {"net_state": "two_sided", "hawk_score": 0, "ease_score": 0},
            "divergence": [
                {"key": "D1_dots_vs_market", "active": False},
                {"key": "D2_projection_vs_breakeven", "active": None},
                {"key": "D3_pressure_vs_market", "active": False},
            ],
            "board": {"rate_path_row": {"implied_bp_12m": 10, "gap": {"gap_bp": 7}}},
        }
        out_dir = tmp_path / "rates_command"
        out_dir.mkdir()
        _append_forward_log(out_dir, artifact)
        log_path = out_dir / "forward_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["schema"] == "rates_command_flag.v1"
        assert row["asof_night"] == "2026-07-18"

    def test_forward_log_keep_first(self, tmp_path, monkeypatch):
        """Second write for same asof_night must be skipped (keep-FIRST)."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        from scripts.build_rates_command import _append_forward_log
        artifact = {
            "asof": "2026-07-18",
            "expectations_pressure": {"net_state": "two_sided", "hawk_score": 0, "ease_score": 0},
            "divergence": [],
            "board": {"rate_path_row": {}},
        }
        out_dir = tmp_path / "rates_command"
        out_dir.mkdir()
        _append_forward_log(out_dir, artifact)
        _append_forward_log(out_dir, artifact)  # second call: must skip
        log_path = out_dir / "forward_log.jsonl"
        lines = [l for l in log_path.read_text().strip().splitlines() if l.strip()]
        assert len(lines) == 1, f"Expected 1 line (keep-FIRST), got {len(lines)}"
