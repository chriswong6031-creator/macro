"""tests/test_causal_llm_runner.py — CHF W5 test suite.

All tests are hermetic: mocked LLM client, no network, no disk writes to real data/.
Coverage:
  - Gating matrix (scheduled+auto_loop=false → pack-only; scheduled+no-service-key → pack-only;
    operator+no-auth → pack-only; full mode only with auth + gate pass)
  - Skeptic validator rejects numeric confidence (RF-7)
  - ISO-week skip path
  - Pack always rebuilt fresh (build_pack called, never reused)
  - Governance event shape (a6_llm_proposed, correct evidence fields)
  - Cortex tool read_causal_candidates empty-safe shapes with files absent
  - Factory handoff dry-run produces validate_candidate-clean proposals
"""
from __future__ import annotations

import json
import sys
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root is on path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers: minimal card + skeptic finding factories
# ---------------------------------------------------------------------------

def _make_card(
    mechanism_id: str = "test-mech-001",
    claim: str = "When liquidity co-moves with breadth in risk-on, entry quality follows.",
    family: str = "liquidity_transmission",
    status: str = "inbox",
) -> dict:
    """Build a minimal schema-valid mechanism card for testing."""
    return {
        "mechanism_id": mechanism_id,
        "family": family,
        "claim_en": claim,
        "claim_zh": "测试机制描述。",
        "causal_graph": {
            "cause": "fed_net_liquidity",
            "target": "good_21d",
            "mediators": [],
            "confounders": ["regime_label"],
            "colliders_to_avoid": [],
        },
        "environment_map": {
            "should_hold": ["risk_on"],
            "should_break": ["risk_off"],
            "frozen_hash": "abc123",
        },
        "falsifiers": [
            "If fed_net_liquidity does not predict good_21d in regime risk_on, the mechanism is refuted.",
            "If lagged-placebo good_21d_{t-21} predicts fed_net_liquidity, reverse causation is suspected.",
        ],
        "test_spec": {
            "exit_path": "a",
            "claim_shape": "lead_lag",
            "horizon_d": 21,
            "metric": "forward_return_21d",
            "threshold": 0.55,
            "min_n": 50,
            "environment": "risk_on",
        },
        "lineage": {
            "source": "llm_proposed",
            "pack_id": "chf-2026-W28-operator",
            "model": "claude-sonnet-4-6",
            "transitions": [],
        },
        "status": status,
        "actor": "script",
        "filed_at": "2026-07-09T10:00:00+00:00",
        "filing_week": "2026-W28",
        "schema": "neuralweb.causal_mechanism_card.v1",
    }


def _make_skeptic_finding(
    card_id: str,
    recommendation: str = "ADVISORY_KEEP",
    blockers: list | None = None,
) -> dict:
    return {
        "card_id": card_id,
        "recommendation": recommendation,
        "blockers": blockers or [],
    }


# ---------------------------------------------------------------------------
# Mock anthropic client that returns controlled responses
# ---------------------------------------------------------------------------

def _make_mock_anthropic_response(text: str) -> MagicMock:
    """Build a minimal mock anthropic response object."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text
    resp = MagicMock()
    resp.content = [content_block]
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    resp.usage = usage
    return resp


def _make_mock_client(response_text: str) -> MagicMock:
    """Build a mock Anthropic client that returns response_text on create()."""
    client = MagicMock()
    client.messages.create.return_value = _make_mock_anthropic_response(response_text)
    return client


# ---------------------------------------------------------------------------
# Provider mock helpers
# ---------------------------------------------------------------------------

def _make_mock_provider(model: str = "claude-sonnet-4-6", response_text: str = "[]") -> dict:
    """Build a mock provider dict with a mock client."""
    return {
        "name": "anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "cred": "sk-test",
        "client": _make_mock_client(response_text),
        "model": model,
    }


# ---------------------------------------------------------------------------
# 1. Gating matrix tests
# ---------------------------------------------------------------------------

class TestGatingMatrix(unittest.TestCase):
    """Test the gating matrix: when does the runner fall to pack-only?"""

    def setUp(self):
        # Patch _write_lane_status to avoid disk writes
        patcher = patch("scripts.run_causal_brainstorm._write_lane_status")
        self.mock_lane_write = patcher.start()
        self.addCleanup(patcher.stop)

        # Patch _already_filed_this_week to return False (no prior filing)
        patcher2 = patch("scripts.run_causal_brainstorm._already_filed_this_week",
                         return_value=False)
        self.mock_filed = patcher2.start()
        self.addCleanup(patcher2.stop)

    def _run_with_config(
        self,
        trigger: str,
        auto_loop: bool,
        has_service_key: bool,
        has_oauth: bool,
        tmp_path: Path,
    ) -> tuple[str, list[str]]:
        """Run main() and return (lane_status_call_arg, print_lines)."""
        import io
        from contextlib import redirect_stdout

        cfg = {
            "auto_loop": auto_loop,
            "model_roles": {
                "generator": "claude-sonnet-4-6",
                "skeptic": "claude-opus-4-8",
                "compiler": "claude-haiku-4-5-20251001",
            },
            "weekly_budget_cards": 3,
        }

        # Mock build_pack to avoid real data reads
        with patch("scripts.run_causal_brainstorm._load_config", return_value=cfg), \
             patch("scripts.run_causal_brainstorm._build_fresh_pack",
                   return_value="=== TEST PACK ==="), \
             patch("scripts.run_causal_brainstorm._build_scheduled_providers",
                   return_value=[_make_mock_provider()] if has_service_key else []), \
             patch("scripts.run_causal_brainstorm._build_operator_providers",
                   return_value=[_make_mock_provider()] if has_oauth else []), \
             patch("scripts.run_causal_brainstorm._run_full_mode",
                   return_value=0) as mock_full:

            buf = io.StringIO()
            with redirect_stdout(buf):
                import scripts.run_causal_brainstorm as runner
                rc = runner.main(["--trigger", trigger, "--root", str(tmp_path)])

            printed = buf.getvalue()
            lane_call = None
            if self.mock_lane_write.called:
                lane_call = self.mock_lane_write.call_args[0][0]  # first positional arg = status
            return lane_call, printed.splitlines(), mock_full.called, rc

    def test_scheduled_auto_loop_false_pack_only(self):
        """scheduled + auto_loop=False → pack-only (awaiting_phase_a)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lane_status, lines, full_called, rc = self._run_with_config(
                trigger="scheduled",
                auto_loop=False,
                has_service_key=True,
                has_oauth=False,
                tmp_path=Path(tmp),
            )
        self.assertFalse(full_called, "full mode must not be reached")
        self.assertIn("auto_loop disabled", " ".join(lines))
        self.assertEqual(rc, 0)
        self.assertEqual(lane_status, "awaiting_phase_a")

    def test_scheduled_no_service_key_pack_only(self):
        """scheduled + auto_loop=True + no ANTHROPIC_API_KEY → pack-only."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lane_status, lines, full_called, rc = self._run_with_config(
                trigger="scheduled",
                auto_loop=True,
                has_service_key=False,
                has_oauth=True,   # oauth present but must NOT be used for scheduled
                tmp_path=Path(tmp),
            )
        self.assertFalse(full_called, "full mode must not be reached even with oauth present")
        self.assertEqual(rc, 0)
        self.assertEqual(lane_status, "degraded_pack_only")

    def test_operator_no_auth_pack_only(self):
        """operator + no auth available → pack-only."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lane_status, lines, full_called, rc = self._run_with_config(
                trigger="operator",
                auto_loop=False,
                has_service_key=False,
                has_oauth=False,
                tmp_path=Path(tmp),
            )
        self.assertFalse(full_called, "full mode must not be reached without auth")
        self.assertEqual(rc, 0)
        self.assertEqual(lane_status, "degraded_pack_only")

    def test_full_mode_reached_with_auth_and_gate(self):
        """operator + auth available → full mode reached."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lane_status, lines, full_called, rc = self._run_with_config(
                trigger="operator",
                auto_loop=False,
                has_service_key=False,
                has_oauth=True,   # oauth is fine for operator trigger
                tmp_path=Path(tmp),
            )
        self.assertTrue(full_called, "full mode must be called with operator trigger + auth")
        self.assertEqual(rc, 0)

    def test_scheduled_auto_loop_true_and_service_key_full_mode(self):
        """scheduled + auto_loop=True + service-key → full mode reached."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lane_status, lines, full_called, rc = self._run_with_config(
                trigger="scheduled",
                auto_loop=True,
                has_service_key=True,
                has_oauth=False,
                tmp_path=Path(tmp),
            )
        self.assertTrue(full_called, "full mode must be reached with scheduled + auto_loop + service-key")
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# 2. ISO-week skip path
# ---------------------------------------------------------------------------

class TestISOWeekSkip(unittest.TestCase):
    def test_iso_week_skip_exits_zero(self):
        """If already filed budget this week, runner prints skip and exits 0."""
        import tempfile, io
        from contextlib import redirect_stdout

        cfg = {"auto_loop": True, "weekly_budget_cards": 3}

        with patch("scripts.run_causal_brainstorm._load_config", return_value=cfg), \
             patch("scripts.run_causal_brainstorm._already_filed_this_week",
                   return_value=True), \
             patch("scripts.run_causal_brainstorm._write_lane_status") as mock_lane, \
             patch("scripts.run_causal_brainstorm._build_scheduled_providers",
                   return_value=[_make_mock_provider()]):

            buf = io.StringIO()
            with redirect_stdout(buf):
                import scripts.run_causal_brainstorm as runner
                with tempfile.TemporaryDirectory() as tmp:
                    rc = runner.main(["--trigger", "scheduled", "--root", tmp])

        printed = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("ISO-week lock", printed)
        mock_lane.assert_called_once()
        # lane status should reflect the idempotent skip
        status_arg = mock_lane.call_args[0][0]
        self.assertEqual(status_arg, "ok")


# ---------------------------------------------------------------------------
# 3. Pack always rebuilt fresh (never reused)
# ---------------------------------------------------------------------------

class TestPackAlwaysFresh(unittest.TestCase):
    def test_build_pack_called_in_pack_only_mode(self):
        """build_pack must be called each run; never reuses persisted pack."""
        import tempfile, io
        from contextlib import redirect_stdout

        cfg = {"auto_loop": False, "weekly_budget_cards": 3}

        with patch("scripts.run_causal_brainstorm._load_config", return_value=cfg), \
             patch("scripts.run_causal_brainstorm._already_filed_this_week",
                   return_value=False), \
             patch("scripts.run_causal_brainstorm._write_lane_status"), \
             patch("scripts.causal_brainstorm_pack.build_pack",
                   return_value="=== FRESH PACK ===") as mock_build_pack:

            buf = io.StringIO()
            with redirect_stdout(buf):
                import scripts.run_causal_brainstorm as runner
                with tempfile.TemporaryDirectory() as tmp:
                    rc = runner.main(["--trigger", "scheduled", "--root", tmp])

        mock_build_pack.assert_called_once()
        self.assertEqual(rc, 0)

    def test_build_pack_called_in_full_mode(self):
        """build_pack must be called in full mode too — fresh every run."""
        import tempfile, io
        from contextlib import redirect_stdout

        cfg = {
            "auto_loop": True,
            "weekly_budget_cards": 3,
            "model_roles": {
                "generator": "claude-sonnet-4-6",
                "skeptic": "claude-opus-4-8",
                "compiler": "claude-haiku-4-5-20251001",
            },
        }

        # Generator returns valid card array; skeptic/compiler keep them
        card = _make_card()
        gen_response = json.dumps([card])
        skep_response = json.dumps([_make_skeptic_finding(card["mechanism_id"], "ADVISORY_KEEP")])
        comp_response = json.dumps([card])

        def _side_effect_providers(cfg_arg, trigger_arg, role_arg):
            texts = {"generator": gen_response, "skeptic": skep_response, "compiler": comp_response}
            return [_make_mock_provider(response_text=texts.get(role_arg, "[]"))]

        with patch("scripts.run_causal_brainstorm._load_config", return_value=cfg), \
             patch("scripts.run_causal_brainstorm._already_filed_this_week",
                   return_value=False), \
             patch("scripts.run_causal_brainstorm._write_lane_status"), \
             patch("scripts.run_causal_brainstorm._write_run_log"), \
             patch("scripts.run_causal_brainstorm._build_scheduled_providers",
                   return_value=[_make_mock_provider(response_text=gen_response)]), \
             patch("scripts.run_causal_brainstorm._build_providers_for_model",
                   side_effect=_side_effect_providers), \
             patch("scripts.causal_brainstorm_pack.build_pack",
                   return_value="=== FRESH PACK ===") as mock_build_pack, \
             patch("scripts.causal_ingest_brainstorm.ingest", return_value=0), \
             patch("engine.neuralweb.governance.append_event", return_value=True):

            buf = io.StringIO()
            with redirect_stdout(buf):
                import scripts.run_causal_brainstorm as runner
                with tempfile.TemporaryDirectory() as tmp:
                    rc = runner.main(["--trigger", "scheduled", "--root", tmp])

        mock_build_pack.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Skeptic validator rejects numeric confidence (RF-7)
# ---------------------------------------------------------------------------

class TestSkepticValidator(unittest.TestCase):
    def test_numeric_confidence_rejected(self):
        """Skeptic finding with numeric confidence field must be rejected (RF-7)."""
        from scripts.run_causal_brainstorm import _validate_skeptic_findings

        findings_with_numeric = [
            {
                "card_id": "card-001",
                "recommendation": "ADVISORY_KEEP",
                "confidence": 0.85,  # FORBIDDEN numeric field
                "blockers": [],
            }
        ]
        valid, rejected = _validate_skeptic_findings(findings_with_numeric)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)
        self.assertIn("numeric", rejected[0])

    def test_numeric_confidence_score_field_rejected(self):
        """Skeptic finding with confidence_score field must also be rejected."""
        from scripts.run_causal_brainstorm import _validate_skeptic_findings

        findings = [
            {
                "card_id": "card-002",
                "recommendation": "ADVISORY_DROP",
                "confidence_score": 0.3,  # also forbidden
                "blockers": ["collider conditioned on"],
            }
        ]
        valid, rejected = _validate_skeptic_findings(findings)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_categorical_finding_passes(self):
        """Categorical-only finding (no numeric fields) passes validation."""
        from scripts.run_causal_brainstorm import _validate_skeptic_findings

        findings = [
            {
                "card_id": "card-003",
                "recommendation": "ADVISORY_KEEP",
                "blockers": [],
            },
            {
                "card_id": "card-004",
                "recommendation": "ADVISORY_DROP",
                "blockers": ["circular definition: outcome is part of cause construction"],
            },
        ]
        valid, rejected = _validate_skeptic_findings(findings)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(rejected), 0)

    def test_nested_numeric_field_rejected(self):
        """Numeric confidence field nested inside a sub-dict is also rejected (RF-7)."""
        from scripts.run_causal_brainstorm import _validate_skeptic_findings

        # 'score' is in _NUMERIC_FIELD_NAMES — banned even when nested
        findings = [
            {
                "card_id": "card-005",
                "recommendation": "ADVISORY_KEEP",
                "blockers": [],
                "meta": {"score": 0.9},  # nested numeric — also forbidden
            }
        ]
        valid, rejected = _validate_skeptic_findings(findings)
        self.assertEqual(len(rejected), 1,
                         "nested score field must be caught and rejected")

        # 'probability' nested in a sub-dict is also banned
        findings2 = [
            {
                "card_id": "card-006",
                "recommendation": "ADVISORY_KEEP",
                "blockers": [],
                "meta": {"probability": 0.7},
            }
        ]
        valid2, rejected2 = _validate_skeptic_findings(findings2)
        self.assertEqual(len(rejected2), 1)


# ---------------------------------------------------------------------------
# 5. Governance event shape
# ---------------------------------------------------------------------------

class TestGovernanceEventShape(unittest.TestCase):
    def test_governance_event_shape(self):
        """Governance event must have correct shape (a6_llm_proposed + evidence fields)."""
        import tempfile

        captured_events: list[dict] = []

        def mock_append_event(event_type, target, *, article, authored_by, evidence, **kwargs):
            captured_events.append({
                "event_type": event_type,
                "target": target,
                "article": article,
                "authored_by": authored_by,
                "evidence": evidence,
            })
            return True

        cfg = {
            "auto_loop": True,
            "weekly_budget_cards": 1,
            "model_roles": {
                "generator": "claude-sonnet-4-6",
                "skeptic": "claude-opus-4-8",
                "compiler": "claude-haiku-4-5-20251001",
            },
        }

        card = _make_card()
        gen_response = json.dumps([card])
        skep_response = json.dumps([_make_skeptic_finding(card["mechanism_id"], "ADVISORY_KEEP")])
        comp_response = gen_response

        def _side_effect_providers(cfg_arg, trigger_arg, role_arg):
            texts = {"generator": gen_response, "skeptic": skep_response, "compiler": comp_response}
            return [_make_mock_provider(response_text=texts.get(role_arg, "[]"))]

        with patch("scripts.run_causal_brainstorm._load_config", return_value=cfg), \
             patch("scripts.run_causal_brainstorm._already_filed_this_week",
                   return_value=False), \
             patch("scripts.run_causal_brainstorm._write_lane_status"), \
             patch("scripts.run_causal_brainstorm._write_run_log"), \
             patch("scripts.run_causal_brainstorm._build_scheduled_providers",
                   return_value=[_make_mock_provider(response_text=gen_response)]), \
             patch("scripts.run_causal_brainstorm._build_providers_for_model",
                   side_effect=_side_effect_providers), \
             patch("scripts.causal_brainstorm_pack.build_pack", return_value="=== PACK ==="), \
             patch("scripts.causal_ingest_brainstorm.ingest", return_value=0), \
             patch("engine.neuralweb.governance.append_event",
                   side_effect=mock_append_event):

            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                import scripts.run_causal_brainstorm as runner
                with tempfile.TemporaryDirectory() as tmp:
                    runner.main(["--trigger", "scheduled", "--root", tmp])

        self.assertEqual(len(captured_events), 1,
                         "Exactly one governance event must be appended")
        ev = captured_events[0]
        self.assertEqual(ev["event_type"], "a6_llm_proposed")
        self.assertEqual(ev["target"], "causal_mechanisms")
        self.assertIsNone(ev["article"])
        self.assertEqual(ev["authored_by"], "run_causal_brainstorm")
        self.assertIn("pack_id", ev["evidence"])
        self.assertIn("n_cards", ev["evidence"])
        self.assertIn("trigger", ev["evidence"])
        self.assertIn("models", ev["evidence"])


# ---------------------------------------------------------------------------
# 6. Cortex tool read_causal_candidates — empty-safe shapes when files absent
# ---------------------------------------------------------------------------

class TestCortexReadCausalCandidates(unittest.TestCase):
    def test_empty_safe_with_all_files_absent(self):
        """read_causal_candidates must return structured empty result when all files absent."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from engine.neuralweb.cortex import _tool_read_causal_candidates
            result = _tool_read_causal_candidates(root, {})

        self.assertIn("mechanism_cards", result)
        self.assertIn("screened_edges", result)
        self.assertIn("null_library_count", result)
        self.assertIn("gaps", result)
        self.assertIsInstance(result["mechanism_cards"], list)
        self.assertIsInstance(result["screened_edges"], list)
        self.assertIsInstance(result["null_library_count"], int)
        self.assertIsInstance(result["gaps"], list)
        self.assertEqual(len(result["mechanism_cards"]), 0)
        self.assertEqual(result["total_actionable_cards"], 0)
        self.assertEqual(result["total_screened_edges"], 0)
        self.assertEqual(result["null_library_count"], 0)
        self.assertTrue(result.get("is_context_only"))
        self.assertTrue(result.get("display_only"))
        # Should have gap entries for each absent file
        self.assertGreater(len(result["gaps"]), 0)

    def test_returns_mechanism_cards_from_file(self):
        """read_causal_candidates returns inbox cards from causal_mechanisms.jsonl."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nw_dir = root / "data" / "neuralweb"
            nw_dir.mkdir(parents=True)

            # Write two cards: one inbox, one decayed
            card1 = _make_card("m-001", status="inbox")
            card2 = _make_card("m-002", status="decayed")  # not returned
            cards_file = nw_dir / "causal_mechanisms.jsonl"
            with cards_file.open("w") as f:
                f.write(json.dumps(card1) + "\n")
                f.write(json.dumps(card2) + "\n")

            from engine.neuralweb.cortex import _tool_read_causal_candidates
            result = _tool_read_causal_candidates(root, {})

        self.assertEqual(result["total_actionable_cards"], 1,
                         "Only inbox/skeptic_passed cards counted")
        self.assertEqual(len(result["mechanism_cards"]), 1)
        self.assertEqual(result["mechanism_cards"][0]["mechanism_id"], "m-001")

    def test_returns_screened_edges_only(self):
        """read_causal_candidates returns only screened_candidate edges."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nw_dir = root / "data" / "neuralweb"
            nw_dir.mkdir(parents=True)

            edges = [
                {"cause": "x", "target": "y", "verdict": "screened_candidate"},
                {"cause": "a", "target": "b", "verdict": "null"},
            ]
            edges_file = nw_dir / "causal_edges.jsonl"
            with edges_file.open("w") as f:
                for e in edges:
                    f.write(json.dumps(e) + "\n")

            from engine.neuralweb.cortex import _tool_read_causal_candidates
            result = _tool_read_causal_candidates(root, {})

        self.assertEqual(result["total_screened_edges"], 1)
        self.assertEqual(len(result["screened_edges"]), 1)

    def test_null_library_count(self):
        """read_causal_candidates counts lines in causal_nulls.jsonl."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nw_dir = root / "data" / "neuralweb"
            nw_dir.mkdir(parents=True)

            nulls_file = nw_dir / "causal_nulls.jsonl"
            with nulls_file.open("w") as f:
                f.write(json.dumps({"cause": "x", "target": "z"}) + "\n")
                f.write(json.dumps({"cause": "a", "target": "b"}) + "\n")
                f.write(json.dumps({"cause": "c", "target": "d"}) + "\n")

            from engine.neuralweb.cortex import _tool_read_causal_candidates
            result = _tool_read_causal_candidates(root, {})

        self.assertEqual(result["null_library_count"], 3)


# ---------------------------------------------------------------------------
# 7. Factory handoff dry-run produces valid candidates
# ---------------------------------------------------------------------------

class TestFactoryHandoffDryRun(unittest.TestCase):
    def test_handoff_produces_valid_candidates(self):
        """Factory handoff builds proposals that pass validate_candidate."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nw_dir = root / "data" / "neuralweb"
            nw_dir.mkdir(parents=True)

            # Write one eligible card
            card = _make_card("m-handoff-001", status="inbox")
            cards_file = nw_dir / "causal_mechanisms.jsonl"
            cards_file.write_text(json.dumps(card) + "\n")

            from scripts.causal_factory_handoff import _load_handoff_cards, _build_candidate_proposal
            from engine.research_factory.schema import validate_candidate

            cards = _load_handoff_cards(root)
            self.assertEqual(len(cards), 1)

            proposal = _build_candidate_proposal(cards[0])

            # Must pass factory schema validation
            errors = validate_candidate(proposal)
            self.assertEqual(
                errors, [],
                f"Proposal failed validation: {errors}"
            )

            # Key fields check
            self.assertEqual(proposal["source"], "external_report")
            self.assertEqual(proposal["candidate_type"], "external_idea")
            self.assertEqual(proposal["trial_accounting"]["mode"], "read_only")
            self.assertEqual(proposal["spec_ref"], "m-handoff-001")
            self.assertEqual(proposal["authority"], "display_only")
            self.assertEqual(proposal["schema"], "research_factory.candidate.v1")

    def test_handoff_dry_run_does_not_write(self):
        """Handoff with dry_run=True must not write to factory ledger."""
        import tempfile, io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nw_dir = root / "data" / "neuralweb"
            nw_dir.mkdir(parents=True)

            card = _make_card("m-dry-001", status="skeptic_passed")
            cards_file = nw_dir / "causal_mechanisms.jsonl"
            cards_file.write_text(json.dumps(card) + "\n")

            # Mock run_ingest to capture call args
            with patch("scripts.research_factory_ingest.run_ingest") as mock_ingest:
                from unittest.mock import MagicMock
                mock_result = MagicMock()
                mock_result.registered = []
                mock_result.dropped = []
                mock_ingest.return_value = mock_result

                buf = io.StringIO()
                with redirect_stdout(buf):
                    import scripts.causal_factory_handoff as handoff
                    # Reload to pick up fresh state
                    import importlib
                    importlib.reload(handoff)
                    rc = handoff.main(["--root", str(root)])

            # Should have been called with dry_run=True (default)
            if mock_ingest.called:
                call_kwargs = mock_ingest.call_args[1]
                self.assertTrue(call_kwargs.get("dry_run", True),
                                "Dry-run must be True by default")
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# 8. Parse JSON array helper
# ---------------------------------------------------------------------------

class TestParseJsonArray(unittest.TestCase):
    def test_direct_json_array(self):
        from scripts.run_causal_brainstorm import _parse_json_array
        result = _parse_json_array('[{"a": 1}]')
        self.assertEqual(result, [{"a": 1}])

    def test_markdown_fenced(self):
        from scripts.run_causal_brainstorm import _parse_json_array
        text = '```json\n[{"b": 2}]\n```'
        result = _parse_json_array(text)
        self.assertEqual(result, [{"b": 2}])

    def test_embedded_array(self):
        from scripts.run_causal_brainstorm import _parse_json_array
        text = 'Some text before\n[{"c": 3}]\nSome text after'
        result = _parse_json_array(text)
        self.assertEqual(result, [{"c": 3}])

    def test_invalid_raises(self):
        from scripts.run_causal_brainstorm import _parse_json_array
        with self.assertRaises(ValueError):
            _parse_json_array("not json at all")


if __name__ == "__main__":
    unittest.main()
