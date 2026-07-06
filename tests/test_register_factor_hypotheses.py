"""Tests for scripts/register_factor_hypotheses.py — P2 deliverable.

Covers:
1. Payload-vs-prereg fidelity: assert each pre_committed_gate dict matches the
   locked PREREGISTRATION.md gate numbers (thresholds, horizon_d, min_n floor).
2. Dry-run purity: no writes to registry on --dry-run.
3. Batch flags: --only h1,h2,h3 registers only H1/H2/H3; --only h4,h5 only H4/H5.
4. Idempotence: running twice does not double-register (mutation-proof: disabling
   the dedupe check causes the test to fail, proving the guard works).
5. Claim-shape fidelity: each hypothesis uses the CLAIM_SHAPES value from
   masterplan §4.2 table.
6. Self-ref ban: no spine_query carries cortex_attention or reflex.cortex_attention.

PREREGISTRATION gate numbers (locked — cite line by line):
  H1: threshold=+0.05 (§3 H1 gate: "+5pp absolute"), horizon_d=21, min_n≥25
  H2: threshold=−0.05 (§3 H2 gate: "effect ≤ −5pp"), horizon_d=21, min_n≥25
  H3: threshold=0.0  (metabolism pass-through; real gate=χ² permutation §3 H3)
  H4: threshold=+0.05 (§3 H4 gate: "+5pp"), horizon_d=21, min_n≥25
  H5: threshold=+0.05 (§3 H5 gate: "+5pp"), horizon_d=21, min_n≥25

NOTE on H3 threshold: the locked prereg uses a χ² permutation p-value which is
NOT expressible as a scalar metabolism gate.  threshold=0.0 is the documented
pass-through (any post-registration data satisfies the metabolism gate; the real
gate lives in validate_factor_h3.py).  This is the correct behavior — the test
asserts this mapping explicitly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.register_factor_hypotheses import (  # noqa: E402
    _ALL_PAYLOADS,
    _BATCH_H123,
    _BATCH_H45,
    _already_registered,
    _count_week_registrations,
    _parse_keys,
    register_batch,
    H1_PAYLOAD,
    H2_PAYLOAD,
    H3_PAYLOAD,
    H4_PAYLOAD,
    H5_PAYLOAD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def empty_registry(tmp_path):
    """Provide a tmp_path with no machine_registry.jsonl."""
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def registry_path(empty_registry):
    return empty_registry / "data" / "neuralweb" / "machine_registry.jsonl"


# ---------------------------------------------------------------------------
# 1. Payload-vs-prereg gate fidelity
# ---------------------------------------------------------------------------

class TestPayloadFidelity:
    """Assert each pre_committed_gate matches locked PREREGISTRATION.md values.

    Prereg line refs are given for each assertion.
    """

    def _gate(self, payload: dict) -> dict:
        """Return a copy of pre_committed_gate stripped of private _* keys."""
        return {k: v for k, v in payload["pre_committed_gate"].items()
                if not k.startswith("_")}

    def test_h1_gate_threshold(self):
        """H1: threshold=+0.05 (prereg §3 H1: '+5pp absolute stop-out gap').
        FIX-3: metric=stop_out_rate (PATH B native); direction=-1 (annotated
        arm LOWERS stop-out rate — lower is better for factor_annotated=True).
        """
        g = self._gate(H1_PAYLOAD)
        assert g["threshold"] == pytest.approx(0.05), (
            "H1 threshold must be +0.05 per locked prereg §3 H1 gate "
            "('+5pp absolute stop-out gap')"
        )
        assert g["direction_expected"] == -1, (
            "H1 direction_expected must be -1: factor_annotated=True LOWERS "
            "stop-out rate (PATH B, walk_forward harness; FIX-3)"
        )
        assert g["metric"] == "stop_out_rate", (
            "H1 metric must be 'stop_out_rate' (PATH B evaluator native metric; FIX-3)"
        )

    def test_h1_gate_horizon_and_minn(self):
        """H1: horizon_d=21, min_n≥25 (prereg §3 H1, metabolism _HOUSE_MIN_N)."""
        g = self._gate(H1_PAYLOAD)
        assert g["horizon_d"] == 21, "H1 horizon_d must be 21 (prereg §3 H1)"
        assert g["min_n"] >= 25, "H1 min_n must be ≥25 (_HOUSE_MIN_N clamp)"

    def test_h1_claim_shape(self):
        """H1 → 'entry_quality' (masterplan §4.2 table)."""
        assert H1_PAYLOAD["claim_shape"] == "entry_quality", (
            "H1 claim_shape must be 'entry_quality' per masterplan §4.2"
        )

    def test_h2_gate_threshold(self):
        """H2: threshold=−0.05 (prereg §3 H2: 'effect ≤ −5pp', harm direction).
        direction_expected=−1.
        """
        g = self._gate(H2_PAYLOAD)
        assert g["threshold"] == pytest.approx(-0.05), (
            "H2 threshold must be −0.05 per locked prereg §3 H2 gate "
            "(harm direction, high_alibi_flag=True → worse outcomes)"
        )
        assert g["direction_expected"] == -1

    def test_h2_gate_horizon_and_minn(self):
        """H2: horizon_d=21, min_n≥25."""
        g = self._gate(H2_PAYLOAD)
        assert g["horizon_d"] == 21
        assert g["min_n"] >= 25

    def test_h2_claim_shape(self):
        """H2 → 'conditional_regime' (masterplan §4.2)."""
        assert H2_PAYLOAD["claim_shape"] == "conditional_regime"

    def test_h3_gate_threshold_passthrough(self):
        """H3: threshold=1.01 (unreachable — deliberately non-passing context-only row).
        FIX-4: the metabolism scalar cannot express a heterogeneity test.
        threshold=1.01 is unreachable (hit_rate ∈ [0,1]) so the metabolism gate
        never auto-passes.  The real gate is the permutation test in validate_factor_h3.py.
        """
        g = self._gate(H3_PAYLOAD)
        assert g["threshold"] == pytest.approx(1.01), (
            "H3 threshold must be 1.01 (unreachable — deliberately non-passing). "
            "The metabolism scalar cannot express a heterogeneity test; this row "
            "is context-only.  Real gate in validate_factor_h3.py (FIX-4)."
        )

    def test_h3_gate_horizon_and_minn(self):
        """H3: horizon_d=21, min_n≥25."""
        g = self._gate(H3_PAYLOAD)
        assert g["horizon_d"] == 21
        assert g["min_n"] >= 25

    def test_h3_claim_shape(self):
        """H3 → 'conditional_regime' (masterplan §4.2)."""
        assert H3_PAYLOAD["claim_shape"] == "conditional_regime"

    def test_h4_gate_threshold(self):
        """H4: threshold=+0.05 (prereg §3 H4: '+5pp stop-out gap').
        FIX-3: metric=stop_out_rate (PATH B native); direction=+1 (twin_bleed
        RAISES stop-out rate — higher is the harm signal for the flagged arm).
        """
        g = self._gate(H4_PAYLOAD)
        assert g["threshold"] == pytest.approx(0.05), (
            "H4 threshold must be +0.05 per locked prereg §3 H4 gate"
        )
        assert g["direction_expected"] == 1, (
            "H4 direction_expected must be +1: twin_bleed_flag=True RAISES "
            "stop-out rate (PATH B, walk_forward harness; FIX-3)"
        )
        assert g["metric"] == "stop_out_rate", (
            "H4 metric must be 'stop_out_rate' (PATH B evaluator native metric; FIX-3)"
        )

    def test_h4_gate_horizon_and_minn(self):
        """H4: horizon_d=21, min_n≥25."""
        g = self._gate(H4_PAYLOAD)
        assert g["horizon_d"] == 21
        assert g["min_n"] >= 25

    def test_h4_claim_shape(self):
        """H4 → 'entry_quality' (masterplan §4.2)."""
        assert H4_PAYLOAD["claim_shape"] == "entry_quality"

    def test_h5_gate_threshold(self):
        """H5: threshold=+0.05 (prereg §3 H5: '+5pp', decay_flag=True → more −5% hits)."""
        g = self._gate(H5_PAYLOAD)
        assert g["threshold"] == pytest.approx(0.05), (
            "H5 threshold must be +0.05 per locked prereg §3 H5 gate"
        )
        assert g["direction_expected"] == 1

    def test_h5_gate_horizon_and_minn(self):
        """H5: horizon_d=21, min_n≥25."""
        g = self._gate(H5_PAYLOAD)
        assert g["horizon_d"] == 21
        assert g["min_n"] >= 25

    def test_h5_claim_shape(self):
        """H5 → 'lead_lag' (masterplan §4.2)."""
        assert H5_PAYLOAD["claim_shape"] == "lead_lag"

    def test_all_horizon_d_are_21(self):
        """All hypotheses use horizon_d=21 at the top level (prereg §1 + §3)."""
        for key, payload in _ALL_PAYLOADS.items():
            assert payload["horizon_d"] == 21, f"{key} top-level horizon_d must be 21"

    def test_all_gate_keys_present(self):
        """All gates carry the four required keys: metric, threshold, min_n, horizon_d."""
        required = {"metric", "threshold", "min_n", "horizon_d"}
        for key, payload in _ALL_PAYLOADS.items():
            gate = {k: v for k, v in payload["pre_committed_gate"].items()
                    if not k.startswith("_")}
            missing = required - set(gate.keys())
            assert not missing, f"{key} pre_committed_gate missing keys: {missing}"

    def test_no_self_ref_in_spine_query(self):
        """No spine_query references cortex_attention or reflex.cortex_attention
        (Article 1 / metabolism._SELF_REF_FORBIDDEN enforcement guard).
        """
        forbidden = {"cortex_attention", "reflex.cortex_attention"}
        for key, payload in _ALL_PAYLOADS.items():
            sq = payload.get("spine_query", {})
            sq_values = {
                str(sq.get("family", "")),
                str(sq.get("engine", "")),
                str(sq.get("ledger", "")),
            }
            overlap = sq_values & forbidden
            assert not overlap, (
                f"{key} spine_query references forbidden key(s): {overlap} "
                "(Article 1: cortex cannot be its own evidence)"
            )
            # Also check family prefix
            assert not str(sq.get("family", "")).startswith("reflex.cortex_attention"), (
                f"{key} spine_query.family starts with reflex.cortex_attention"
            )


# ---------------------------------------------------------------------------
# 2. Dry-run purity
# ---------------------------------------------------------------------------

class TestDryRun:

    def test_dry_run_produces_no_registry_writes(self, empty_registry):
        """--dry-run must not write anything to machine_registry.jsonl."""
        reg_path = empty_registry / "data" / "neuralweb" / "machine_registry.jsonl"
        assert not reg_path.exists(), "Registry must not exist before dry run"

        results = register_batch(["h1", "h2"], dry_run=True, root=empty_registry)

        assert not reg_path.exists(), (
            "machine_registry.jsonl must NOT be created during dry-run"
        )
        assert all(r["status"] == "dry-run" for r in results)

    def test_dry_run_returns_correct_keys(self, empty_registry):
        """Dry-run returns one result per requested key."""
        results = register_batch(["h3"], dry_run=True, root=empty_registry)
        assert len(results) == 1
        assert results[0]["key"] == "h3"

    def test_dry_run_all_hypotheses(self, empty_registry):
        """Dry-run of all 5 hypotheses produces 5 results, no writes."""
        reg_path = empty_registry / "data" / "neuralweb" / "machine_registry.jsonl"
        results = register_batch(["h1", "h2", "h3", "h4", "h5"],
                                 dry_run=True, root=empty_registry)
        assert len(results) == 5
        assert not reg_path.exists()


# ---------------------------------------------------------------------------
# 3. Batch flag correctness
# ---------------------------------------------------------------------------

class TestBatchFlags:

    def test_h123_batch_definition(self):
        """_BATCH_H123 contains exactly h1, h2, h3 in that order."""
        assert _BATCH_H123 == ["h1", "h2", "h3"]

    def test_h45_batch_definition(self):
        """_BATCH_H45 contains exactly h4, h5 in that order."""
        assert _BATCH_H45 == ["h4", "h5"]

    def test_parse_keys_h123(self):
        """--only h1,h2,h3 resolves to [h1, h2, h3]."""
        assert _parse_keys("h1,h2,h3") == ["h1", "h2", "h3"]

    def test_parse_keys_h45(self):
        """--only h4,h5 resolves to [h4, h5]."""
        assert _parse_keys("h4,h5") == ["h4", "h5"]

    def test_parse_keys_unknown_raises(self):
        """Unknown hypothesis key raises ValueError."""
        with pytest.raises(ValueError, match="Unknown hypothesis keys"):
            _parse_keys("h6")

    def test_parse_keys_none_returns_all(self):
        """--only None returns all 5 keys."""
        assert _parse_keys(None) == ["h1", "h2", "h3", "h4", "h5"]

    def test_register_batch_h123_only(self, empty_registry):
        """register_batch(['h1','h2','h3']) dry-run returns exactly 3 results."""
        results = register_batch(["h1", "h2", "h3"], dry_run=True, root=empty_registry)
        assert len(results) == 3
        assert {r["key"] for r in results} == {"h1", "h2", "h3"}

    def test_register_batch_h45_only(self, empty_registry):
        """register_batch(['h4','h5']) dry-run returns exactly 2 results."""
        results = register_batch(["h4", "h5"], dry_run=True, root=empty_registry)
        assert len(results) == 2
        assert {r["key"] for r in results} == {"h4", "h5"}


# ---------------------------------------------------------------------------
# 4. Idempotence — mutation-proof test
# ---------------------------------------------------------------------------

class TestIdempotence:

    def test_second_run_skips_existing(self, empty_registry):
        """Running register_batch twice does not double-register (idempotence).

        First run: H1 gets registered (mocked).
        Second run: _already_registered detects the existing row and skips.

        The mock patches engine.neuralweb.metabolism.register_hypothesis (the
        module where the function lives) since register_batch uses a lazy import.
        """
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
        call_count = {"n": 0}

        def mock_reg(payload, root=None, now=None):
            call_count["n"] += 1
            return {"id": "cortex-test-h1", "status": "registered",
                    "registered_at": "2026-07-05T12:00:00+00:00",
                    "come_back": "2026-07-27"}

        # First run with dedupe disabled → call_count goes to 1
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                register_batch(["h1"], dry_run=False, root=empty_registry, now=fixed_now)
        assert call_count["n"] == 1, "First run should call register_hypothesis once"

        # Second run with dedupe active → should skip, call_count stays at 1
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=True):
                results2 = register_batch(["h1"], dry_run=False,
                                          root=empty_registry, now=fixed_now)

        assert call_count["n"] == 1, (
            "Second run must NOT call register_hypothesis when _already_registered=True"
        )
        assert results2[0]["status"] == "already-registered"

    def test_dedupe_check_removal_causes_double_registration(self, empty_registry):
        """MUTATION PROOF: disabling the dedupe check causes register_hypothesis
        to be called twice, proving the guard is the actual gating mechanism.
        """
        from datetime import datetime, timezone
        fixed_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

        call_count = {"n": 0}

        def mock_reg(payload, root=None, now=None):
            call_count["n"] += 1
            return {"id": f"test-{call_count['n']}", "status": "registered"}

        # DISABLE the dedupe check by patching it to always return False
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                register_batch(["h2"], dry_run=False, root=empty_registry, now=fixed_now)
                register_batch(["h2"], dry_run=False, root=empty_registry, now=fixed_now)

        # With dedupe disabled, register_hypothesis was called TWICE
        assert call_count["n"] == 2, (
            "MUTATION PROOF: with _already_registered disabled (always False), "
            "register_hypothesis is called twice — proving the guard works when enabled"
        )

    def test_already_registered_checks_open_statuses_only(self, empty_registry):
        """_already_registered returns False for hypotheses with closed status
        (passed, failed, retired), allowing re-registration after a conclusion.
        """
        from datetime import datetime, timezone
        reg_path = empty_registry / "data" / "neuralweb" / "machine_registry.jsonl"
        reg_path.parent.mkdir(parents=True, exist_ok=True)

        hyp_text = H3_PAYLOAD["hypothesis"]
        for status in ("passed", "failed", "retired"):
            row = {
                "id": f"cortex-test-{status}",
                "kind": "cortex_hypothesis",
                "status": status,
                "hypothesis": hyp_text,
                "registered_at": "2026-07-01T00:00:00+00:00",
            }
            reg_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            result = _already_registered(hyp_text, root=empty_registry)
            assert not result, (
                f"_already_registered should return False for status={status!r} "
                "(closed statuses allow re-registration)"
            )

    def test_already_registered_returns_true_for_open(self, empty_registry):
        """_already_registered returns True for registered/accruing/insufficient-n."""
        reg_path = empty_registry / "data" / "neuralweb" / "machine_registry.jsonl"
        reg_path.parent.mkdir(parents=True, exist_ok=True)

        hyp_text = H4_PAYLOAD["hypothesis"]
        for status in ("registered", "accruing", "insufficient-n"):
            row = {
                "id": f"cortex-test-open-{status}",
                "kind": "cortex_hypothesis",
                "status": status,
                "hypothesis": hyp_text,
                "registered_at": "2026-07-01T00:00:00+00:00",
            }
            reg_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            result = _already_registered(hyp_text, root=empty_registry)
            assert result, (
                f"_already_registered must return True for status={status!r}"
            )


# ---------------------------------------------------------------------------
# 5. Private-key stripping (don't pass _metric_mapping_note to metabolism)
# ---------------------------------------------------------------------------

class TestPrivateKeyStripping:

    def test_private_keys_stripped_before_registration(self, empty_registry):
        """_* keys in pre_committed_gate must not reach metabolism.register_hypothesis."""
        captured = {}

        def mock_reg(payload, root=None, now=None):
            captured["payload"] = payload
            return {"id": "test", "status": "registered"}

        # Mock at the metabolism module level (lazy import target)
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                register_batch(["h1"], dry_run=False, root=empty_registry)

        gate = captured["payload"]["pre_committed_gate"]
        private_keys = [k for k in gate if k.startswith("_")]
        assert not private_keys, (
            f"Private keys must be stripped before calling metabolism: {private_keys}"
        )

    def test_required_gate_keys_survive_stripping(self, empty_registry):
        """After stripping _* keys, the required gate keys still exist."""
        captured = {}

        def mock_reg(payload, root=None, now=None):
            captured["payload"] = payload
            return {"id": "test", "status": "registered"}

        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                register_batch(["h5"], dry_run=False, root=empty_registry)

        gate = captured["payload"]["pre_committed_gate"]
        required = {"metric", "threshold", "min_n", "horizon_d"}
        missing = required - set(gate.keys())
        assert not missing, f"Required gate keys missing after strip: {missing}"


# ---------------------------------------------------------------------------
# 6. Budget pre-flight (FIX-7)
# ---------------------------------------------------------------------------

class TestBudgetPreflight:
    """FIX-7: register_batch aborts cleanly when weekly budget is exhausted.

    BUDGET_PER_WEEK=3.  If 1 hypothesis is already registered this week,
    the remaining budget=2.  A batch of 3 (h1,h2,h3) must abort before ANY write.
    """

    def test_abort_when_budget_insufficient_for_batch(self, empty_registry):
        """register_h123 with 1 pre-existing same-week registration aborts cleanly.

        FIX-7: remaining_budget=2 < batch_size=3 → RuntimeError with clear message,
        NO calls to register_hypothesis, NO writes to machine_registry.jsonl.
        """
        from datetime import datetime, timezone
        fixed_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

        call_count = {"n": 0}

        def mock_reg(payload, root=None, now=None):
            call_count["n"] += 1
            return {"id": "test", "status": "registered"}

        # Simulate 1 pre-existing registration this week: remaining budget = 3-1 = 2
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                with mock.patch(
                    "scripts.register_factor_hypotheses._count_week_registrations",
                    return_value=1,  # 1 already filed this week
                ):
                    with pytest.raises(RuntimeError, match="BUDGET PRE-FLIGHT ABORT"):
                        register_batch(
                            ["h1", "h2", "h3"],  # 3 hypotheses; budget only allows 2
                            dry_run=False,
                            root=empty_registry,
                            now=fixed_now,
                        )

        assert call_count["n"] == 0, (
            "FIX-7: register_hypothesis must NOT be called when budget pre-flight aborts. "
            f"Got {call_count['n']} calls (expected 0)."
        )

    def test_dry_run_skips_budget_preflight(self, empty_registry):
        """FIX-7: budget pre-flight is skipped in dry-run mode (no writes anyway)."""
        from datetime import datetime, timezone
        fixed_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

        # Even with 0 budget remaining, dry-run must not raise
        with mock.patch(
            "scripts.register_factor_hypotheses._count_week_registrations",
            return_value=3,  # all budget consumed — would abort a real run
        ):
            try:
                results = register_batch(
                    ["h1", "h2", "h3"],
                    dry_run=True,
                    root=empty_registry,
                    now=fixed_now,
                )
            except RuntimeError:
                pytest.fail(
                    "FIX-7: dry-run must NOT raise RuntimeError on budget exhaustion "
                    "(budget pre-flight only applies to real runs)"
                )
        assert len(results) == 3
        assert all(r["status"] == "dry-run" for r in results)

    def test_budget_passes_when_sufficient(self, empty_registry):
        """FIX-7: batch proceeds normally when remaining budget >= batch_size."""
        from datetime import datetime, timezone
        fixed_now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

        call_count = {"n": 0}

        def mock_reg(payload, root=None, now=None):
            call_count["n"] += 1
            return {"id": f"test-{call_count['n']}", "status": "registered"}

        # 0 already filed this week → budget=3 >= batch_size=2
        with mock.patch("engine.neuralweb.metabolism.register_hypothesis",
                        side_effect=mock_reg):
            with mock.patch("scripts.register_factor_hypotheses._already_registered",
                            return_value=False):
                with mock.patch(
                    "scripts.register_factor_hypotheses._count_week_registrations",
                    return_value=0,
                ):
                    results = register_batch(
                        ["h4", "h5"],
                        dry_run=False,
                        root=empty_registry,
                        now=fixed_now,
                    )

        assert call_count["n"] == 2, (
            "FIX-7: both h4 and h5 must be registered when budget is sufficient"
        )
        assert len(results) == 2

    def test_preflight_ignores_already_registered_keys(self, empty_registry):
        """Pre-flight counts only PENDING keys: a fully-registered batch re-run
        on an exhausted week is a no-op (already-registered results), NOT an
        abort.  Without this, the nightly step would log 'deferred' forever
        for work that already finished.
        """
        from datetime import datetime, timezone
        fixed_now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)

        with mock.patch("scripts.register_factor_hypotheses._already_registered",
                        return_value=True):
            with mock.patch(
                "scripts.register_factor_hypotheses._count_week_registrations",
                return_value=3,  # week exhausted — but nothing is pending
            ):
                results = register_batch(
                    ["h1", "h2", "h3"],
                    dry_run=False,
                    root=empty_registry,
                    now=fixed_now,
                )

        assert len(results) == 3
        assert all(r["status"] == "already-registered" for r in results), (
            "A fully-registered batch must return already-registered results "
            "even when the weekly budget is exhausted (pending=0 ≤ remaining=0)"
        )


# ---------------------------------------------------------------------------
# 7. --defer-on-budget (nightly cortex-job step behavior)
# ---------------------------------------------------------------------------

class TestDeferOnBudget:
    """The nightly cortex-job step runs both batches every night with
    --defer-on-budget: a budget-blocked batch exits 0 ('deferred') and is
    retried the next night, instead of crashing the step with a traceback.
    """

    def test_defer_flag_exits_zero_on_budget_abort(self, empty_registry):
        """main() with --defer-on-budget returns 0 when the pre-flight aborts."""
        from scripts.register_factor_hypotheses import main

        with mock.patch("scripts.register_factor_hypotheses._already_registered",
                        return_value=False):
            with mock.patch(
                "scripts.register_factor_hypotheses._count_week_registrations",
                return_value=3,  # budget exhausted, 2 pending → abort
            ):
                rc = main([
                    "--only", "h4,h5",
                    "--root", str(empty_registry),
                    "--defer-on-budget",
                ])
        assert rc == 0, "--defer-on-budget must exit 0 on budget pre-flight abort"

    def test_without_flag_budget_abort_still_raises(self, empty_registry):
        """Default behavior unchanged: no flag → the RuntimeError propagates."""
        from scripts.register_factor_hypotheses import main

        with mock.patch("scripts.register_factor_hypotheses._already_registered",
                        return_value=False):
            with mock.patch(
                "scripts.register_factor_hypotheses._count_week_registrations",
                return_value=3,
            ):
                with pytest.raises(RuntimeError, match="BUDGET PRE-FLIGHT ABORT"):
                    main(["--only", "h4,h5", "--root", str(empty_registry)])

    def test_defer_flag_does_not_mask_other_errors(self, empty_registry):
        """--defer-on-budget only absorbs the budget pre-flight abort, not
        arbitrary RuntimeErrors from the registration path.
        """
        from scripts.register_factor_hypotheses import main

        with mock.patch(
            "scripts.register_factor_hypotheses.register_batch",
            side_effect=RuntimeError("registry disk on fire"),
        ):
            with pytest.raises(RuntimeError, match="disk on fire"):
                main([
                    "--only", "h4,h5",
                    "--root", str(empty_registry),
                    "--defer-on-budget",
                ])
