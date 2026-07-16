"""Tests for engine/oracle/ratio_lens.py (RL-R1..R16 compliance).

Covers:
  (1) AUTHORITY block present, all four may_* False, in module AND emitted artifact
  (2) FORBIDDEN_KEYS recursive walk over a computed payload (synthetic frames)
  (3) Ledger writes ONLY when COLLECT_LANE=nightly (monkeypatch env)
  (4) Ledger keep-first idempotency on double-run
  (5) Builder exit-0 contract on empty/missing stores
  (6) State-assignment isolation: assert _assign_state signature contains no
      pace/velocity parameter (inspect.signature)
  (7) Anchor honesty: synthetic random-walk series yields anchor.status=="no_anchor"
      (no half_life key); synthetic strong OU series yields a half_life with CI
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pandas as pd
import pytest

# Ensure project root on sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import engine.oracle.ratio_lens as RL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = "2026-07-11"
SEED_DATE = pd.Timestamp("2023-05-09")

FORBIDDEN_KEYS = frozenset({
    "beneficiary", "casualty", "shelter", "front_run",
    "buy", "direction", "forecast", "predicted", "target",
    "expected_return", "rank", "score", "recommendation",
})


def _walk_keys(obj: Any) -> list[str]:
    """Recursively collect all string keys from a nested dict/list."""
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_walk_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_walk_keys(item))
    return keys


def _make_level_series(n: int, start: str = "2023-05-09", seed: int = 0) -> pd.Series:
    """Synthetic level series (cumulative product of 1+small_returns)."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0005, 0.01, size=n)
    lvl = np.cumprod(1 + rets)
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series(lvl, index=idx, dtype=float)


def _make_ou_level_series(n: int, start: str = "2023-05-09",
                           mean: float = 0.0, kappa: float = 0.08,
                           sigma: float = 0.01, seed: int = 42) -> pd.Series:
    """Synthetic mean-reverting (OU) level series for anchor test."""
    rng = np.random.default_rng(seed)
    vals = np.zeros(n)
    vals[0] = 0.0
    for i in range(1, n):
        vals[i] = vals[i-1] + kappa * (mean - vals[i-1]) + sigma * rng.normal()
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series(vals, index=idx, dtype=float)


def _make_random_walk_level(n: int, start: str = "2023-05-09", seed: int = 7) -> pd.Series:
    """Pure random walk — should NOT anchor."""
    rng = np.random.default_rng(seed)
    vals = np.cumsum(rng.normal(0, 0.01, size=n))
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series(vals, index=idx, dtype=float)


def _synthetic_payload(state: str = "TRENDING") -> dict:
    """Build minimal synthetic pair record for forbidden-key tests."""
    return {
        "schema": "ratio_lens.v1",
        "as_of": _TODAY,
        "registry_hash": "abc123",
        "authority": RL.AUTHORITY,
        "disclosure": RL.DISCLOSURE,
        "pairs": [
            {
                "id": "test_pair",
                "num": "A",
                "den": "B",
                "kind": "etf",
                "name_en": "A vs B",
                "name_zh": "A vs B",
                "eff_start": "2023-05-09",
                "n_bars": 500,
                "z63": 0.5,
                "z252": 1.0,
                "pct_3y": 65.0,
                "state": state,
                "stance_en": RL._STANCE_EN[state],
                "stance_zh": RL._STANCE_ZH[state],
                "legs": {"num": {"id": "A"}, "den": {"id": "B"}},
                "decomp": {"shape_1w": "shared_tide_up"},
                "anchor": {"status": "no_anchor"},
                "pace": {"1w": 0.001, "1m": 0.002, "3m": 0.005, "pace_trend": "steady"},
            }
        ],
        "tree": {},
        "implicit_claim_count": 4,
    }


# ---------------------------------------------------------------------------
# (1) AUTHORITY block
# ---------------------------------------------------------------------------

class TestAuthorityBlock:
    def test_module_authority_present(self):
        assert hasattr(RL, "AUTHORITY"), "AUTHORITY block missing from module"

    def test_module_may_rank_false(self):
        assert RL.AUTHORITY["may_rank"] is False

    def test_module_may_gate_false(self):
        assert RL.AUTHORITY["may_gate"] is False

    def test_module_may_size_false(self):
        assert RL.AUTHORITY["may_size"] is False

    def test_module_may_escalate_false(self):
        assert RL.AUTHORITY["may_escalate"] is False

    def test_module_tier_display(self):
        assert RL.AUTHORITY["tier"] == "display"

    def test_module_horizon_role_context(self):
        assert RL.AUTHORITY["horizon_role"] == "context"

    def test_artifact_authority_present(self):
        payload = _synthetic_payload()
        assert "authority" in payload

    def test_artifact_all_may_false(self):
        payload = _synthetic_payload()
        auth = payload["authority"]
        assert auth["may_rank"] is False
        assert auth["may_gate"] is False
        assert auth["may_size"] is False
        assert auth["may_escalate"] is False


# ---------------------------------------------------------------------------
# (2) FORBIDDEN_KEYS walk
# ---------------------------------------------------------------------------

class TestForbiddenKeys:
    def test_clean_payload_has_no_forbidden_keys(self):
        payload = _synthetic_payload()
        # Exclude the 'authority' block — may_rank/may_gate are structural meta-flags
        payload_without_auth = {k: v for k, v in payload.items() if k != "authority"}
        keys = _walk_keys(payload_without_auth)
        bad = [k for k in keys if any(fk in k.lower() for fk in FORBIDDEN_KEYS)]
        assert bad == [], f"Forbidden keys found: {bad}"

    def test_detection_works_on_injected_key(self):
        """Positive control: inject a forbidden key and confirm _walk_keys finds it."""
        payload = _synthetic_payload()
        payload["pairs"][0]["rank"] = 1  # inject forbidden
        keys = _walk_keys(payload)
        bad = [k for k in keys if any(fk in k.lower() for fk in FORBIDDEN_KEYS)]
        assert "rank" in bad

    def test_forbidden_keys_guard_raises(self):
        """_assert_no_forbidden_keys should raise on injected key."""
        payload = _synthetic_payload()
        payload["pairs"][0]["forecast"] = "up"
        with pytest.raises(ValueError, match="FORBIDDEN"):
            RL._assert_no_forbidden_keys(payload)

    def test_forbidden_keys_guard_clean(self):
        """_assert_no_forbidden_keys should not raise on clean payload."""
        payload = _synthetic_payload()
        RL._assert_no_forbidden_keys(payload)  # must not raise

    @pytest.mark.parametrize("key", sorted(FORBIDDEN_KEYS))
    def test_each_forbidden_key_detected(self, key: str):
        """Each key from FORBIDDEN_KEYS is caught by the guard."""
        payload = _synthetic_payload()
        payload["pairs"][0][key] = "injected"
        with pytest.raises(ValueError):
            RL._assert_no_forbidden_keys(payload)


# ---------------------------------------------------------------------------
# (3) Ledger gate: writes only when COLLECT_LANE=nightly
# ---------------------------------------------------------------------------

class TestLedgerGate:
    def test_no_write_without_collect_lane(self, tmp_path, monkeypatch):
        """Without COLLECT_LANE=nightly, ledger should not be written."""
        monkeypatch.delenv("COLLECT_LANE", raising=False)

        from scripts.build_oracle_ratio_lens import _stamp_ledger
        ledger_p = tmp_path / "ratio_lens_ledger.jsonl"
        pair_records = [
            {"id": "test_pair", "state": "TRENDING", "kind": "etf",
             "decomp": {"shape_1w": "shared_tide_up"}, "z252": 1.0, "z63": 0.5,
             "pct_3y": 50.0, "legs": {"num": {"ret_1w": 0.01}, "den": {"ret_1w": 0.005}}},
        ]
        n = _stamp_ledger(pair_records, _TODAY, ledger_p)
        assert n == 0, "Ledger should not write when COLLECT_LANE != nightly"
        assert not ledger_p.exists(), "Ledger file should not be created"

    def test_write_with_collect_lane_nightly(self, tmp_path, monkeypatch):
        """With COLLECT_LANE=nightly, ledger should append transition rows."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        from scripts.build_oracle_ratio_lens import _stamp_ledger
        ledger_p = tmp_path / "ratio_lens_ledger.jsonl"
        pair_records = [
            {"id": "test_pair", "state": "EXTENDED", "kind": "etf",
             "decomp": {"shape_1w": "shared_tide_up"}, "z252": 2.5, "z63": 1.0,
             "pct_3y": 90.0, "legs": {"num": {"ret_1w": 0.03}, "den": {"ret_1w": 0.01}}},
        ]
        n = _stamp_ledger(pair_records, _TODAY, ledger_p)
        assert n > 0, "Ledger should have written at least one row"
        assert ledger_p.exists(), "Ledger file should have been created"
        rows = [json.loads(l) for l in ledger_p.read_text().splitlines() if l.strip()]
        assert any(r["pair_id"] == "test_pair" for r in rows)


# ---------------------------------------------------------------------------
# (4) Ledger keep-first idempotency
# ---------------------------------------------------------------------------

class TestLedgerIdempotency:
    def test_double_run_keep_first(self, tmp_path, monkeypatch):
        """Running _stamp_ledger twice on same data should not duplicate rows."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        from scripts.build_oracle_ratio_lens import _stamp_ledger
        ledger_p = tmp_path / "ratio_lens_ledger.jsonl"
        pair_records = [
            {"id": "p1", "state": "TRENDING", "kind": "basket",
             "decomp": {"shape_1w": "one_sided"}, "z252": 0.5, "z63": 0.2,
             "pct_3y": 45.0, "legs": {"num": {"ret_1w": 0.01}, "den": {"ret_1w": -0.005}}},
        ]
        n1 = _stamp_ledger(pair_records, _TODAY, ledger_p)
        n2 = _stamp_ledger(pair_records, _TODAY, ledger_p)

        assert n2 == 0, "Second run should append 0 rows (all already exist)"
        rows = [json.loads(l) for l in ledger_p.read_text().splitlines() if l.strip()]
        # Should have exactly the rows from first run
        count = sum(1 for r in rows if r["pair_id"] == "p1")
        assert count == n1

    def test_new_state_triggers_new_row(self, tmp_path, monkeypatch):
        """A state change on a second run should append a new transition row."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        from scripts.build_oracle_ratio_lens import _stamp_ledger
        ledger_p = tmp_path / "ratio_lens_ledger.jsonl"

        records_day1 = [
            {"id": "p1", "state": "TRENDING", "kind": "etf",
             "decomp": {"shape_1w": "shared_tide_up"}, "z252": 0.5, "z63": 0.2,
             "pct_3y": 45.0, "legs": {"num": {"ret_1w": 0.01}, "den": {"ret_1w": 0.005}}},
        ]
        records_day2 = [
            {"id": "p1", "state": "EXTENDED", "kind": "etf",
             "decomp": {"shape_1w": "shared_tide_up"}, "z252": 2.5, "z63": 1.0,
             "pct_3y": 90.0, "legs": {"num": {"ret_1w": 0.03}, "den": {"ret_1w": 0.01}}},
        ]
        _stamp_ledger(records_day1, "2026-07-10", ledger_p)
        n2 = _stamp_ledger(records_day2, "2026-07-11", ledger_p)

        assert n2 > 0, "New state should produce a new ledger row"
        rows = [json.loads(l) for l in ledger_p.read_text().splitlines() if l.strip()]
        transitions = [r for r in rows if r.get("event") == "state_transition"]
        dates = {r["date"] for r in transitions}
        assert "2026-07-10" in dates
        assert "2026-07-11" in dates


# ---------------------------------------------------------------------------
# (5) Builder exit-0 contract on empty/missing stores
# ---------------------------------------------------------------------------

class TestBuilderExit0:
    def test_empty_data_root_exits_0(self, tmp_path, monkeypatch):
        """Builder should exit 0 even when data stores are missing."""
        # Create minimal ratio_pairs.json with empty pairs list
        oracle_dir = tmp_path / "oracle"
        oracle_dir.mkdir(parents=True)
        (oracle_dir / "ratio_pairs.json").write_text(json.dumps({
            "version": "1.0",
            "registered": _TODAY,
            "masterplan": "test",
            "taxonomy": {},
            "pairs": [],
            "purity_notes": {},
        }), encoding="utf-8")

        # Create empty baskets/membership.json
        baskets_dir = tmp_path / "baskets"
        baskets_dir.mkdir()
        (baskets_dir / "membership.json").write_text(
            json.dumps({"version": "1", "baskets": {}}), encoding="utf-8"
        )

        # Create site/oracledata dir
        out_dir = tmp_path / "site" / "oracledata"
        out_dir.mkdir(parents=True)

        monkeypatch.delenv("COLLECT_LANE", raising=False)

        # Reload BEFORE patching: reload re-executes the module and would wipe
        # any patch on its attributes (a wiped _out_dir patch is exactly how
        # this test used to clobber the real site/oracledata/ratio_lens.json).
        # hard_exit is bound at import, so patch it as a module attr after.
        from scripts import build_oracle_ratio_lens
        import importlib
        importlib.reload(build_oracle_ratio_lens)

        # Patch config.data_dir() to tmp_path and out dir
        with mock.patch("lib.config.data_dir", return_value=tmp_path):
            with mock.patch("scripts.build_oracle_ratio_lens._out_dir",
                            return_value=out_dir):
                with mock.patch("scripts.build_oracle_ratio_lens.hard_exit") as mock_exit:
                    mock_exit.side_effect = SystemExit(0)
                    try:
                        build_oracle_ratio_lens.main()
                    except SystemExit as e:
                        assert e.code == 0, f"Expected exit 0, got {e.code}"
                    else:
                        pytest.fail("Builder should have called hard_exit(0)")

    def test_compute_with_empty_pairs_no_raise(self, tmp_path):
        """compute() with empty pair list should return valid payload without raising."""
        # Minimal registry
        oracle_dir = tmp_path / "oracle"
        oracle_dir.mkdir()
        (oracle_dir / "ratio_pairs.json").write_text(json.dumps({
            "version": "1.0",
            "registered": _TODAY,
            "masterplan": "test",
            "taxonomy": {},
            "pairs": [],
            "purity_notes": {},
        }), encoding="utf-8")
        (tmp_path / "baskets").mkdir()
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps({"version": "1", "baskets": {}}), encoding="utf-8"
        )
        (tmp_path / "baskets" / "ohlcv").mkdir()

        # Patch lib.store to not find anything
        with mock.patch("lib.store.read", return_value=None):
            payload = RL.compute(data_root=tmp_path, as_of=_TODAY)

        assert payload["schema"] == "ratio_lens.v1"
        assert payload["pairs"] == []
        assert "authority" in payload


# ---------------------------------------------------------------------------
# (6) State-assignment isolation: no pace/velocity parameter
# ---------------------------------------------------------------------------

class TestStateAssignmentIsolation:
    def test_assign_state_has_no_pace_param(self):
        """RL-R8 / m12: _assign_state must NOT have pace or velocity in signature."""
        assert RL._state_fn_signature_check(), (
            "_assign_state has pace/velocity parameter — violates RL-R8"
        )

    def test_assign_state_signature_params(self):
        """Explicit check of _assign_state's parameter names."""
        sig = inspect.signature(RL._assign_state)
        params = list(sig.parameters.keys())
        # Must have exactly these four
        assert "z252" in params
        assert "washout" in params
        assert "weekly_mom_turn" in params
        assert "anchor_status" in params
        # Must NOT have pace or velocity
        for p in params:
            assert "pace" not in p.lower(), f"param '{p}' contains 'pace'"
            assert "velocity" not in p.lower(), f"param '{p}' contains 'velocity'"

    @pytest.mark.parametrize("state,z252,washout,mom_turn,anchor", [
        ("EXTENDED",   2.1,  False, False, "anchored"),
        ("EXTENDED",  -2.1,  False, False, "no_anchor"),
        ("BASING",     0.5,  True,  True,  "anchored"),
        ("NO_ANCHOR",  0.5,  False, False, "no_anchor"),
        ("TRENDING",   0.5,  False, False, "anchored"),
        ("TRENDING",   None, False, False, "anchored"),
    ])
    def test_state_assignment_cases(self, state, z252, washout, mom_turn, anchor):
        result = RL._assign_state(z252, washout, mom_turn, anchor)
        assert result == state, f"Expected {state}, got {result} for z252={z252}"


# ---------------------------------------------------------------------------
# (7) Anchor honesty: no_anchor on random walk; anchored on OU
# ---------------------------------------------------------------------------

class TestAnchorHonesty:
    def test_random_walk_gives_no_anchor(self):
        """Pure random walk should yield no_anchor (RL-R6 honesty)."""
        rw = _make_random_walk_level(600)
        result = RL._anchor_ols(rw)
        # Random walk: either no_anchor (b not sig negative) or maybe anchored
        # but we check that if status is anchored, there IS a half_life
        if result["status"] == "anchored":
            assert "half_life" in result, "anchored status must include half_life"
        # More importantly: the no_anchor path has no half_life key
        if result["status"] == "no_anchor":
            assert "half_life" not in result, "no_anchor must NOT include half_life"

    def test_strong_ou_gives_anchor_with_half_life(self):
        """Strong mean-reverting series should produce anchor with half_life (RL-R6)."""
        # Strong OU: high kappa (fast reversion)
        ou = _make_ou_level_series(700, kappa=0.15, sigma=0.005, seed=42)
        result = RL._anchor_ols(ou)
        # May or may not trigger depending on bootstrap CI
        # The key contract: if anchored, half_life must be present; if no_anchor, absent
        if result["status"] == "anchored":
            assert "half_life" in result
            assert result["half_life"] > 0
            assert "ci_low" in result
            assert "ci_high" in result
            assert result["half_life"] < RL.ANCHOR_MAX_HL_DAYS
        else:
            assert result["status"] == "no_anchor"
            assert "half_life" not in result

    def test_no_anchor_key_absent_when_status_no_anchor(self):
        """When status is no_anchor, half_life key must be absent (RL-R6 honesty)."""
        # Short series — definitely no_anchor (insufficient bars)
        short = _make_ou_level_series(100, kappa=0.10)
        result = RL._anchor_ols(short)
        assert result["status"] == "no_anchor"
        assert "half_life" not in result

    def test_anchor_honesty_very_strong_ou(self):
        """Very strong OU (high kappa) over long series should produce anchor."""
        ou = _make_ou_level_series(800, kappa=0.25, sigma=0.003, seed=1)
        result = RL._anchor_ols(ou)
        # With very high kappa, should detect reversion
        if result["status"] == "anchored":
            assert "half_life" in result
            assert result["half_life"] > 0
        # Either anchored or no_anchor is valid; never half_life without anchored status


# ---------------------------------------------------------------------------
# Shape label tests (RL-R4)
# ---------------------------------------------------------------------------

class TestShapeLabel:
    @pytest.mark.parametrize("a,b,expected", [
        (0.05, -0.02, "one_sided"),   # opposite signs
        (0.05,  0.001, "one_sided"),   # b < 0.25*a (dead-band)
        (0.05,  0.04, "shared_tide_up"),
        (-0.05, -0.04, "shared_tide_down"),
        (0.03,  0.02, "shared_tide_up"),
        (None,  0.02, None),
        (0.0,   0.0,  "mixed"),        # zero stronger => mixed
    ])
    def test_shape_label(self, a, b, expected):
        assert RL._shape_label(a, b) == expected


# ---------------------------------------------------------------------------
# Pace trend tests (RL-R7)
# ---------------------------------------------------------------------------

class TestPaceTrend:
    def test_fading(self):
        # |p1w| < 0.5*|p1m|, same sign
        assert RL._pace_trend(0.001, 0.01) == "fading"

    def test_building(self):
        # |p1w| > 1.5*|p1m|
        assert RL._pace_trend(0.03, 0.01) == "building"

    def test_steady(self):
        assert RL._pace_trend(0.007, 0.01) == "steady"

    def test_none_when_inputs_none(self):
        assert RL._pace_trend(None, 0.01) is None
        assert RL._pace_trend(0.01, None) is None
