"""Acceptance suite for the Grey Deer settled risk envelope (GD-2).

Every test here pins one FROZEN constraint from
`research/grey_deer/commissions/GD-2_SETTLED_ENVELOPE_COMMISSION_2026-08-19.md` §0 and
the architecture freeze §5.2.  If a future change makes one of these fail, the change
is wrong until Sol re-freezes the contract — these are not style tests.

The headline test is `TestGD1PermanentRegressionFixture`: the accepted 2026-08-18
dual-read (trend RISK_ON 76 / leadership BROKEN / radar calm 53.9) must survive
composition WITHOUT being averaged into a middle score.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.risk_envelope import (
    DATA_STATE_VOCABULARY,
    DEFINITION_ID,
    SCHEMA,
    STAGE_VOCABULARY,
    EnvelopeContractError,
    SourceRead,
    assert_v0_stage,
    canonical_json,
    compose_envelope,
)
from scripts.build_risk_envelope import build_sources, build

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "risk_envelope" / "gd1_dual_read_2026-08-18.json"
_COMPOSER = _REPO_ROOT / "engine" / "risk_envelope.py"
_SCHEMA_FILE = _REPO_ROOT / "contracts" / "risk_envelope.schema.json"

_T0 = "2026-08-19T00:00:00Z"
_T1 = "2026-08-19T06:30:00Z"


def _compose(sources, session="2026-08-18", observed=_T0, produced=_T0):
    return compose_envelope(
        sources=sources, market="US", source_session=session,
        observed_at=observed, produced_at=produced, as_of=session, revision="settled",
    )


@pytest.fixture(scope="module")
def gd1():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gd1_envelope(gd1):
    sources = build_sources(gd1["market_state"], gd1["leadership_crack"], gd1["session"])
    return _compose(sources, session=gd1["session"])


# ══ §0.4 — THE PERMANENT REGRESSION FIXTURE ═══════════════════════════════════

class TestGD1PermanentRegressionFixture:
    """The accepted GD-1 dual-read must compose to three separate carried truths."""

    def test_fixture_inputs_are_the_accepted_dual_read(self, gd1):
        # Guards the fixture itself against silent regeneration from live data.
        assert gd1["market_state"]["verdict"] == "RISK_ON"
        assert gd1["market_state"]["score"] == 76
        assert gd1["market_state"]["radar"]["state"] == "calm"
        assert gd1["market_state"]["radar"]["top_score"] == 53.9
        assert gd1["leadership_crack"]["state"] == "BROKEN"

    def test_measured_state_is_risk_on_carried_verbatim(self, gd1_envelope):
        ms = gd1_envelope["measured_state"]
        assert ms["verdict"] == "RISK_ON"
        assert ms["score"] == 76          # verbatim — not 65, not 70, not rescaled
        assert ms["usable"] is True

    def test_broken_leadership_is_carried_alongside_not_averaged_away(self, gd1_envelope):
        sources = {s["source_id"]: s for s in gd1_envelope["provenance"]["sources"]}
        lead = sources["leadership-crack-latest"]
        assert lead["state"] == "BROKEN"           # source-native, verbatim
        assert lead["hazard_stage"] == "TRANSMITTING"
        assert gd1_envelope["hazard_summary"]["stage"] in ("FRAGILE", "TRANSMITTING", "BREAKDOWN")

    def test_coherence_is_contradictory(self, gd1_envelope):
        assert gd1_envelope["coherence"]["state"] == "CONTRADICTORY"

    def test_the_contradiction_is_named_explicitly(self, gd1_envelope):
        kinds = {c["kind"] for c in gd1_envelope["coherence"]["contradictions"]}
        assert "trend_vs_hazard" in kinds
        pair = next(c for c in gd1_envelope["coherence"]["contradictions"]
                    if c["kind"] == "trend_vs_hazard")
        assert pair["left_state"] == "RISK_ON"
        assert pair["right_state"] == "BROKEN"

    def test_calm_radar_is_carried_but_does_not_cancel_the_broken_cohort(self, gd1_envelope):
        sources = {s["source_id"]: s for s in gd1_envelope["provenance"]["sources"]}
        radar = sources["risk-radar-us"]
        assert radar["state"] == "calm"
        assert radar["score"] == 53.9                  # verbatim
        assert radar["hazard_stage"] == "NONE"
        # …and the composed stage is still the damaged one. A calm vote never pulls down.
        assert gd1_envelope["hazard_summary"]["stage"] == "TRANSMITTING"
        assert {c["kind"] for c in gd1_envelope["coherence"]["contradictions"]} >= {"hazard_split"}

    def test_no_blended_or_averaged_number_appears_anywhere(self, gd1_envelope):
        """The two scores are 76 and 53.9. No mean/midpoint of them may exist."""
        blob = canonical_json(gd1_envelope)
        for forbidden in ("64.95", "64.9", "65.0", "\"score\":65", "\"score\":64"):
            assert forbidden not in blob, f"blended value {forbidden!r} leaked into the envelope"
        scores = re.findall(r'"score":([0-9.]+)', blob)
        assert sorted(set(scores)) == ["53.9", "76"], f"unexpected score set {scores}"


# ══ §0.1 — PURE COMPOSER ══════════════════════════════════════════════════════

class TestComposerPurity:
    """No I/O and no clock reads inside composition — asserted against the source."""

    def test_composer_reads_no_clock_and_no_disk(self):
        tree = ast.parse(_COMPOSER.read_text(encoding="utf-8"))
        banned_attrs = {"now", "utcnow", "today", "time", "monotonic", "read_text",
                        "write_text", "open", "getenv", "urlopen"}
        banned_names = {"open", "input"}
        offences = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr in banned_attrs:
                    offences.append(f"line {node.lineno}: .{fn.attr}()")
                if isinstance(fn, ast.Name) and fn.id in banned_names:
                    offences.append(f"line {node.lineno}: {fn.id}()")
        assert not offences, f"composer is not pure: {offences}"

    def test_composer_imports_nothing_impure(self):
        tree = ast.parse(_COMPOSER.read_text(encoding="utf-8"))
        banned = {"os", "pathlib", "datetime", "time", "requests", "urllib", "subprocess", "random"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & banned), f"composer imports impure modules: {imported & banned}"

    def test_instants_are_arguments_not_defaults(self):
        src = [SourceRead(source_id="a", role="measured_state", state="RISK_ON", score=1,
                          as_of="2026-08-18", required=True)]
        e1 = _compose(src, observed=_T0, produced=_T0)
        e2 = _compose(src, observed=_T1, produced=_T1)
        assert e1["observed_at"] != e2["observed_at"]
        # …but the semantic answer, and therefore the bundle id, is unchanged.
        assert e1["bundle_id"] == e2["bundle_id"]


# ══ §0.7 — SOURCE-ORDER INVARIANCE + BYTE STABILITY ═══════════════════════════

class TestDeterminism:

    def _three(self):
        return [
            SourceRead(source_id="market-state-latest", role="measured_state",
                       state="RISK_ON", score=76, as_of="2026-08-18", required=True),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       state="BROKEN", as_of="2026-08-18", required=True,
                       hazard_stage="FRAGILE"),
            SourceRead(source_id="risk-radar-us", role="hazard_evidence",
                       state="calm", score=53.9, as_of="2026-08-18", hazard_stage="NONE"),
        ]

    def test_source_order_invariance(self):
        import itertools
        base = canonical_json(_compose(self._three()))
        for perm in itertools.permutations(self._three()):
            assert canonical_json(_compose(list(perm))) == base

    def test_byte_stable_on_identical_inputs(self):
        a = canonical_json(_compose(self._three()))
        b = canonical_json(_compose(self._three()))
        assert a == b

    def test_bundle_id_changes_when_a_state_changes(self):
        base = _compose(self._three())
        changed = self._three()
        changed[1] = SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                                state="INTACT", as_of="2026-08-18", required=True,
                                hazard_stage="NONE")
        assert _compose(changed)["bundle_id"] != base["bundle_id"]

    def test_duplicate_source_ids_are_refused(self):
        dupe = self._three() + [self._three()[0]]
        with pytest.raises(EnvelopeContractError):
            _compose(dupe)


# ══ §0.3 — THE NULL LAW: null ≠ NONE ≠ 0 ══════════════════════════════════════

class TestNullLaw:

    def _measured(self):
        return SourceRead(source_id="market-state-latest", role="measured_state",
                          state="RISK_ON", score=76, as_of="2026-08-18", required=True)

    def test_missing_required_hazard_source_nulls_the_stage(self):
        e = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       present=False, required=True),
        ])
        assert e["hazard_summary"]["stage"] is None
        assert e["hazard_summary"]["stage_reason"] == "required_coverage_unavailable"

    def test_stale_required_hazard_source_nulls_the_stage(self):
        e = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       state="INTACT", as_of="2026-08-11", stale=True, required=True,
                       hazard_stage="NONE"),
        ])
        assert e["hazard_summary"]["stage"] is None, "a stale calm source cast a calm vote"

    def test_stale_source_never_casts_a_calm_vote_over_a_fresh_damaged_one(self):
        e = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       state="BROKEN", as_of="2026-08-18", required=True,
                       hazard_stage="BREAKDOWN"),
            SourceRead(source_id="risk-radar-us", role="hazard_evidence",
                       state="calm", score=0, as_of="2026-08-01", stale=True,
                       hazard_stage="NONE"),
        ])
        assert e["hazard_summary"]["stage"] == "BREAKDOWN"
        assert "risk-radar-us" in e["hazard_summary"]["unreadable_sources"]
        assert "risk-radar-us" not in e["hazard_summary"]["contributing_sources"]

    def test_none_requires_fresh_required_coverage_and_a_positive_result(self):
        e = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       state="INTACT", as_of="2026-08-18", required=True, hazard_stage="NONE"),
        ])
        assert e["hazard_summary"]["stage"] == "NONE"
        assert e["hazard_summary"]["stage_reason"] == "observed_settled_evidence"

    def test_null_is_not_none_and_not_zero(self):
        unknown = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       present=False, required=True),
        ])
        known_clear = _compose([
            self._measured(),
            SourceRead(source_id="leadership-crack-latest", role="hazard_evidence",
                       state="INTACT", as_of="2026-08-18", required=True, hazard_stage="NONE"),
        ])
        assert unknown["hazard_summary"]["stage"] is None
        assert known_clear["hazard_summary"]["stage"] == "NONE"
        assert unknown["hazard_summary"]["stage"] != known_clear["hazard_summary"]["stage"]
        assert unknown["hazard_summary"]["stage"] != 0
        # …and in JSON they serialize differently too (null vs "NONE"), never as 0.
        assert '"stage":null' in canonical_json(unknown)
        assert '"stage":"NONE"' in canonical_json(known_clear)

    def test_score_zero_is_a_real_reading_not_a_missing_one(self):
        e = _compose([
            SourceRead(source_id="market-state-latest", role="measured_state",
                       state="RISK_OFF", score=0, as_of="2026-08-18", required=True),
        ])
        assert e["measured_state"]["score"] == 0
        assert e["measured_state"]["score"] is not None
        assert e["measured_state"]["usable"] is True

    def test_stale_measured_state_nulls_the_verdict_rather_than_guessing(self):
        e = _compose([
            SourceRead(source_id="market-state-latest", role="measured_state",
                       state="RISK_ON", score=76, as_of="2026-08-11", stale=True, required=True),
        ])
        assert e["measured_state"]["verdict"] is None
        assert e["measured_state"]["score"] is None
        assert e["measured_state"]["as_of"] == "2026-08-11"   # the clock is still shown


# ══ §0.2 — BIRTH AUTHORITY: DESCRIPTIVE ONLY ══════════════════════════════════

class TestBirthAuthority:

    def test_every_authority_boolean_is_hard_false(self, gd1_envelope):
        auth = gd1_envelope["authority"]
        assert auth["envelope_may_rank"] is False
        assert auth["envelope_may_gate"] is False
        assert auth["envelope_may_size"] is False
        assert auth["envelope_may_execute"] is False
        assert auth["policy_actions_require_individual_authority"] is True

    def test_anticipatory_stages_are_not_in_the_vocabulary(self):
        assert "ARMED" not in STAGE_VOCABULARY
        assert "TRIGGERING" not in STAGE_VOCABULARY
        assert set(STAGE_VOCABULARY) == {"NONE", "FRAGILE", "TRANSMITTING", "BREAKDOWN"}

    @pytest.mark.parametrize("stage", ["ARMED", "TRIGGERING", "CONTAGION", "RESOLVED", "EXPIRED"])
    def test_anticipatory_stage_is_refused_at_the_contract_boundary(self, stage):
        with pytest.raises(EnvelopeContractError):
            assert_v0_stage(stage)
        with pytest.raises(EnvelopeContractError):
            SourceRead(source_id="x", role="hazard_evidence", hazard_stage=stage)

    def test_no_predictive_probability_field_exists(self, gd1_envelope):
        blob = canonical_json(gd1_envelope).lower()
        for word in ("probability", "forecast", "predict", "likelihood", "odds", "p_"):
            assert word not in blob, f"predictive vocabulary {word!r} leaked into the envelope"

    def test_zero_policies_and_normal_posture(self, gd1_envelope):
        assert gd1_envelope["policies"] == []
        assert gd1_envelope["episodes"] == []
        ps = gd1_envelope["policy_summary"]
        assert ps["posture"] == "NORMAL"
        assert ps["active_policy_ids"] == []
        assert ps["policy_count"] == 0
        assert ps["basis"] == "zero_active_policies"
        assert ps["display_only"] is True


# ══ §0.6 — LEGACY EXCLUSION ═══════════════════════════════════════════════════

class TestLegacyRiskStateExclusion:
    """`engine/risk_state.py`'s fused score must never enter composer arithmetic."""

    def test_composer_never_imports_or_names_legacy_risk_state(self):
        src = _COMPOSER.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in src.split("\n")
            if not line.lstrip().startswith("#")
        )
        # The module docstring names it once, deliberately, as an exclusion receipt;
        # strip string literals so only real code references can trip this.
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + [getattr(node, "module", "") or ""]
                assert not any("risk_state" in n for n in names), "composer imports legacy risk_state"
            if isinstance(node, ast.Attribute):
                assert "risk_state" not in node.attr
        assert "risk_state.compute" not in code
        assert "fused" not in code.lower().replace("fused score", "")

    def test_builder_never_reads_the_legacy_artifact(self):
        src = (_REPO_ROOT / "scripts" / "build_risk_envelope.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + [getattr(node, "module", "") or ""]
                assert not any("risk_state" in n for n in names)


# ══ CONTRACT SHAPE ════════════════════════════════════════════════════════════

class TestContractShape:

    REQUIRED_TOP_LEVEL = [
        "schema", "definition_id", "market", "revision", "bundle_id", "source_session",
        "clocks_as_of", "measured_state", "hazard_summary", "episodes", "policies",
        "policy_summary", "data_state", "coherence", "coverage", "freshness",
        "correction", "provenance", "authority",
    ]

    def test_freeze_skeleton_keys_all_present(self, gd1_envelope):
        # freeze §5.2 skeleton — `clocks` is carried as the as_of/observed_at/
        # produced_at/stale_after quartet rather than a nested object.
        for key in [k for k in self.REQUIRED_TOP_LEVEL if k != "clocks_as_of"]:
            assert key in gd1_envelope, f"missing contract key {key}"
        for clock in ("as_of", "observed_at", "produced_at", "stale_after"):
            assert clock in gd1_envelope, f"missing clock {clock}"

    def test_schema_and_definition_id(self, gd1_envelope):
        assert gd1_envelope["schema"] == SCHEMA == "mastermind.risk_envelope/v1"
        assert gd1_envelope["definition_id"] == DEFINITION_ID

    def test_data_state_in_vocabulary(self, gd1_envelope):
        assert gd1_envelope["data_state"] in DATA_STATE_VOCABULARY

    def test_per_source_clocks_are_carried_separately(self, gd1_envelope):
        per = gd1_envelope["freshness"]["per_source"]
        assert set(per) == {"market-state-latest", "leadership-crack-latest", "risk-radar-us"}
        for sid, entry in per.items():
            assert "as_of" in entry and "state" in entry, sid

    def test_envelope_validates_against_the_committed_schema(self, gd1_envelope):
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
        jsonschema.validate(gd1_envelope, schema)

    def test_schema_forbids_anticipatory_stages(self):
        schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
        enum = schema["properties"]["hazard_summary"]["properties"]["stage"]["enum"]
        assert "ARMED" not in enum and "TRIGGERING" not in enum
        assert None in enum, "schema must permit null (not lawfully knowable)"


# ══ BUILDER / ADAPTERS ════════════════════════════════════════════════════════

class TestSettledBuilder:

    def test_adapters_carry_source_native_states_verbatim(self, gd1):
        reads = {s.source_id: s for s in
                 build_sources(gd1["market_state"], gd1["leadership_crack"], gd1["session"])}
        assert reads["market-state-latest"].state == "RISK_ON"
        assert reads["market-state-latest"].score == 76
        assert reads["leadership-crack-latest"].state == "BROKEN"
        assert reads["risk-radar-us"].state == "calm"
        assert reads["risk-radar-us"].score == 53.9

    def test_missing_artifacts_degrade_rather_than_crash(self):
        reads = build_sources(None, None, None)
        env = _compose(reads, session=None)
        assert env["hazard_summary"]["stage"] is None
        assert env["measured_state"]["verdict"] is None
        assert env["data_state"] == "UNKNOWN"

    def test_off_session_source_is_flagged_not_silently_accepted(self, gd1):
        ms = dict(gd1["market_state"])
        lead = dict(gd1["leadership_crack"], asof="2026-08-11")
        env = _compose(build_sources(ms, lead, gd1["session"]), session=gd1["session"])
        assert "leadership-crack-latest" in env["freshness"]["off_session_sources"]
        assert env["freshness"]["all_on_session"] is False
        assert env["hazard_summary"]["stage"] is None   # required + off-session ⇒ null

    def test_live_build_produces_a_schema_valid_envelope(self):
        jsonschema = pytest.importorskip("jsonschema")
        env = build(now=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc))
        if not env.get("source_session"):
            pytest.skip("settled market-state artifact not present in this checkout")
        jsonschema.validate(env, json.loads(_SCHEMA_FILE.read_text(encoding="utf-8")))
        assert env["authority"]["envelope_may_gate"] is False
