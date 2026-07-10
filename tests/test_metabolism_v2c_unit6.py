"""tests/test_metabolism_v2c_unit6.py — Hermetic tests for Metabolism V2-C Unit 6.

Unit 6 = the Uncovered-Domain Scout (engine/metabolism/scout.py) + the
Revamp-vs-Fix adjudicator (engine/metabolism/revamp_adjudicator.py).

COVERAGE
--------
Scout:
  1. A domain covered by an active lobe (by SIGNATURE, not the coarse tag) is
     never proposed.
  2. An uncovered domain ACCRUES below the persistence gate (honest null).
  3. It FIRES only after >= K distinct cycles uncovered — display-tier charter.
  4. Idempotent: one standing proposal per domain (no re-propose).
  5. dry-run (emit=False) writes ZERO I/O.
  6. STRUCTURAL: the scout can only ever propose tier=display / state=proposed.
  7. An inactive lobe does NOT provide coverage.
  8. INERT: the scout never calls lifecycle.transition.

Revamp adjudicator:
  9.  < K journal rows → insufficient_evidence / accruing (honest null).
  10. Counted logic breaches, no sustained decline → logic_error / in_place_fix.
  11. Counted logic breaches + degrading trajectory → stale_construct / revamp.
  12. Regime pause → domain_shift / hold_operator (never blame the lobe).
  13. Health-excluded misses dominate → domain_shift / hold_operator.
  14. dry-run writes ZERO I/O; emit writes artifact + insight-bus row.
  15. INERT: the adjudicator never calls lifecycle.transition.

Cross-cutting safety:
  16. No LLM import in either module (deterministic; R-V2-9).
  17. Neither module writes synapse.yml or mastermind_context (INERT).
  18. Banned word 'validated' absent from user-facing source.
  19. config/nw_information_domains.yml is fenced (self-mod + grader manifest).
  20. New insight-bus kinds are registered.
  21. NEVER-RAISE on garbage input.

All tests are HERMETIC (tmp dirs, in-process, no real data/network/subprocess).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import pytest  # noqa: F401

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "data" / "metabolism" / "scout").mkdir(parents=True)
    (d / "data" / "metabolism" / "charter_proposals").mkdir(parents=True)
    (d / "data" / "metabolism" / "revamp_adjudications").mkdir(parents=True)
    (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True)
    (d / "data" / "neuralweb").mkdir(parents=True)
    (d / "config").mkdir(parents=True)
    return d


def _write_domains(root: Path, domains: list[dict], default_min: int = 3) -> None:
    import yaml  # noqa: PLC0415
    cfg = {
        "schema": "nw_information_domains.v1",
        "generated_at": "2026-07-10",
        "defaults": {"min_uncovered_cycles": default_min},
        "domains": domains,
    }
    (root / "config" / "nw_information_domains.yml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )


def _write_charters(root: Path, charters: dict) -> None:
    import yaml  # noqa: PLC0415
    (root / "config" / "lobe_charters.yml").write_text(
        yaml.dump(
            {"schema": "lobe_charters.v1", "generated_at": "2026-07-10", "charters": charters},
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _charter(lobe_id: str, *, state: str = "active", tier: str = "display",
             domain: str = "context", owner: str = "neural-web", notes: str = "") -> dict:
    return {
        "lobe_id": lobe_id,
        "tier": tier,
        "lifecycle_state": state,
        "information_domain": domain,
        "fitness_sensors": ["liveness"],
        "owner_program": owner,
        "notes": notes,
    }


def _write_budget(root: Path, max_active: int = 100, max_probation: int = 10) -> None:
    import yaml  # noqa: PLC0415
    (root / "config" / "metabolism_budget.yml").write_text(
        yaml.dump({
            "schema": "metabolism_budget.v1",
            "max_active_nonscored_lobes": max_active,
            "max_probation_lobes": max_probation,
        }, default_flow_style=False),
        encoding="utf-8",
    )


def _write_organism_state(root: Path, labels: dict) -> None:
    # labels: {lobe_id: trajectory_label}
    lobes = {lid: {"lobe_id": lid, "trajectory": {"label": lab}} for lid, lab in labels.items()}
    (root / "data" / "metabolism" / "organism_state.json").write_text(
        json.dumps({"schema": "metabolism.organism_state.v1", "lobes": lobes}),
        encoding="utf-8",
    )


def _write_journal(root: Path, lobe_id: str, rows: list[dict]) -> None:
    p = root / "data" / "metabolism" / "lifecycle" / f"{lobe_id}.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _breach(counted: bool = True, breach_type: str = "logic_breach",
            health_status: str | None = None, all_inputs_absent: bool = False) -> dict:
    return {
        "schema": "metabolism.lifecycle_journal.v1",
        "ts": "2026-07-10T00:00:00+00:00",
        "lobe_id": "x",
        "breach_type": breach_type,
        "health_status": health_status,
        "counted": counted,
        "reason": "test",
        "regime_paused": False,
        "all_inputs_absent": all_inputs_absent,
    }


# ── 1-8. Scout ─────────────────────────────────────────────────────────────────

class TestScout:
    def _one_uncovered_domain(self, root: Path, min_cycles: int = 3) -> None:
        # A universe with one covered + one uncovered domain.
        _write_domains(root, [
            {"domain_id": "context_synthesis", "label": "Context",
             "coverage_match": ["context", "attention"], "evidence_match": ["context"]},
            {"domain_id": "novel_domain", "label": "Novel",
             "coverage_match": ["novel-thing"], "evidence_match": ["novel"]},
        ], default_min=min_cycles)
        _write_charters(root, {"attention-deterministic": _charter("attention-deterministic")})
        _write_budget(root)

    def test_covered_domain_never_proposed(self):
        from engine.metabolism import scout
        root = _tmp_root()
        _write_domains(root, [
            {"domain_id": "context_synthesis", "label": "Context",
             "coverage_match": ["context", "attention"]},
        ])
        _write_charters(root, {"attention-deterministic": _charter("attention-deterministic")})
        _write_budget(root)
        res = scout.scan("c1", root=root)
        assert res["covered"] == ["context_synthesis"]
        assert res["uncovered"] == []
        assert res["emitted"] == []

    def test_uncovered_domain_accrues_below_threshold(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._one_uncovered_domain(root, min_cycles=3)
        res = scout.scan("c1", root=root)
        assert "novel_domain" in res["uncovered"]
        assert res["emitted"] == []
        assert res["accruing"] and res["accruing"][0]["domain_id"] == "novel_domain"
        assert res["accruing"][0]["uncovered_cycles"] == 1
        # No proposal file written yet.
        assert not (root / "data" / "metabolism" / "charter_proposals" / "novel_domain.json").exists()

    def test_fires_after_k_distinct_cycles(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._one_uncovered_domain(root, min_cycles=3)
        scout.scan("c1", root=root)
        scout.scan("c2", root=root)
        res = scout.scan("c3", root=root)
        assert len(res["emitted"]) == 1
        proposal = res["emitted"][0]
        assert proposal["domain_id"] == "novel_domain"
        assert proposal["uncovered_for_cycles"] == 3
        # STRUCTURAL: display-tier / proposed only — never scored.
        assert proposal["proposed_tier"] == "display"
        assert proposal["proposed_lifecycle_state"] == "proposed"
        prop_file = root / "data" / "metabolism" / "charter_proposals" / "novel_domain.json"
        assert prop_file.exists()
        # An insight-bus row was emitted.
        bus = root / "data" / "metabolism" / "insight_bus.jsonl"
        assert bus.exists()
        kinds = [json.loads(ln)["kind"] for ln in bus.read_text().splitlines() if ln.strip()]
        assert "uncovered_domain" in kinds

    def test_idempotent_no_double_propose(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._one_uncovered_domain(root, min_cycles=3)
        for c in ("c1", "c2", "c3"):
            scout.scan(c, root=root)
        prop_file = root / "data" / "metabolism" / "charter_proposals" / "novel_domain.json"
        first_mtime = prop_file.stat().st_mtime_ns
        res = scout.scan("c4", root=root)
        assert res["emitted"] == []
        assert "novel_domain" in res["already_proposed"]
        assert prop_file.stat().st_mtime_ns == first_mtime  # untouched

    def test_dry_run_writes_no_io(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._one_uncovered_domain(root, min_cycles=1)  # would fire immediately
        res = scout.scan("c1", root=root, emit=False)
        # Decision still computed:
        assert len(res["emitted"]) == 1
        # But NOTHING written:
        assert not (root / "data" / "metabolism" / "scout" / "observations.jsonl").exists()
        assert not (root / "data" / "metabolism" / "charter_proposals" / "novel_domain.json").exists()
        assert not (root / "data" / "metabolism" / "insight_bus.jsonl").exists()

    def test_coverage_by_signature_not_tag(self):
        # A lobe tagged information_domain=context but whose lobe_id matches a
        # different domain's coverage_match still covers that domain.
        from engine.metabolism import scout
        root = _tmp_root()
        _write_domains(root, [
            {"domain_id": "causal_discovery", "label": "Causal",
             "coverage_match": ["causal", "mechanism"]},
        ])
        _write_charters(root, {"causal-edges": _charter("causal-edges", domain="context")})
        _write_budget(root)
        res = scout.scan("c1", root=root)
        assert res["covered"] == ["causal_discovery"]
        assert res["uncovered"] == []

    def test_inactive_lobe_does_not_cover(self):
        from engine.metabolism import scout
        root = _tmp_root()
        _write_domains(root, [
            {"domain_id": "causal_discovery", "label": "Causal", "coverage_match": ["causal"]},
        ], default_min=99)
        _write_charters(root, {"causal-edges": _charter("causal-edges", state="demoted")})
        _write_budget(root)
        res = scout.scan("c1", root=root)
        assert res["uncovered"] == ["causal_discovery"]

    def test_survives_nondict_observation_line(self):
        # A valid-JSON-but-non-object line in observations.jsonl must NOT crash
        # the scan and silently suppress a domain that has crossed threshold.
        from engine.metabolism import scout
        root = _tmp_root()
        self._one_uncovered_domain(root, min_cycles=1)  # would fire on cycle 1
        obs = root / "data" / "metabolism" / "scout" / "observations.jsonl"
        obs.write_text('["not", "an", "object"]\n5\nnull\n', encoding="utf-8")
        res = scout.scan("c1", root=root)
        assert "error" not in res
        assert len(res["emitted"]) == 1  # not suppressed by the garbage lines

    def _covered_by(self, root: Path, lobe_id: str, label: str | None = None) -> None:
        # A universe with one domain covered by `lobe_id`; optional trajectory label.
        _write_domains(root, [
            {"domain_id": "china_market", "label": "China", "coverage_match": ["china"]},
        ])
        _write_charters(root, {lobe_id: _charter(lobe_id)})
        _write_budget(root)
        if label is not None:
            _write_organism_state(root, {lobe_id: label})

    def test_thinly_covered_when_only_covering_lobe_degrading(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._covered_by(root, "site-china-cycle-phase", label="degrading")
        res = scout.scan("c1", root=root)
        assert res["covered"] == ["china_market"]      # still covered
        assert res["uncovered"] == []
        assert res["emitted"] == []                     # NOT proposed
        assert len(res["thinly_covered"]) == 1
        assert res["thinly_covered"][0]["domain_id"] == "china_market"

    def test_healthy_coverage_not_thin(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._covered_by(root, "site-china-cycle-phase", label="compounding")
        res = scout.scan("c1", root=root)
        assert res["thinly_covered"] == []

    def test_thin_requires_all_covering_lobes_labeled(self):
        # Covered by a degrading lobe AND an unlabeled lobe → unknown health on one
        # → honest-null, NOT flagged thin.
        from engine.metabolism import scout
        root = _tmp_root()
        _write_domains(root, [
            {"domain_id": "china_market", "label": "China", "coverage_match": ["china"]},
        ])
        _write_charters(root, {
            "site-china-cycle-phase": _charter("site-china-cycle-phase"),
            "site-china-market-state": _charter("site-china-market-state"),
        })
        _write_budget(root)
        _write_organism_state(root, {"site-china-cycle-phase": "degrading"})  # other unlabeled
        res = scout.scan("c1", root=root)
        assert res["thinly_covered"] == []

    def test_thin_failopen_without_organism_state(self):
        from engine.metabolism import scout
        root = _tmp_root()
        self._covered_by(root, "site-china-cycle-phase", label=None)  # no organism_state.json
        res = scout.scan("c1", root=root)
        assert res["covered"] == ["china_market"]
        assert res["thinly_covered"] == []

    def test_empty_universe_is_silent(self):
        from engine.metabolism import scout
        root = _tmp_root()  # no domains config written
        _write_charters(root, {"attention-deterministic": _charter("attention-deterministic")})
        res = scout.scan("c1", root=root)
        assert res["universe_size"] == 0
        assert res["emitted"] == []


# ── 9-15. Revamp-vs-Fix adjudicator ────────────────────────────────────────────

class TestRevampAdjudicator:
    def test_insufficient_evidence_accrues(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach()])  # only 2 rows
        res = ra.adjudicate_lobe("lobe-x", "demoted", cycle_id="c1", root=root, emit=False)
        assert res["topology"] == ra.TOPOLOGY_INSUFFICIENT
        assert res["recommendation"] == ra.REC_ACCRUING

    def test_logic_error_recommends_in_place_fix(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach(), _breach()])
        res = ra.adjudicate_lobe(
            "lobe-x", "probation", cycle_id="c1",
            trajectory_label="stagnating", root=root, emit=False,
        )
        assert res["topology"] == ra.TOPOLOGY_LOGIC_ERROR
        assert res["recommendation"] == ra.REC_IN_PLACE_FIX
        assert res["recommended_next"]["path"] == "propose_engine_fix"

    def test_stale_construct_recommends_revamp(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach(), _breach(), _breach()])
        res = ra.adjudicate_lobe(
            "lobe-x", "demoted", cycle_id="c1",
            trajectory_label="degrading", root=root, emit=False,
        )
        assert res["topology"] == ra.TOPOLOGY_STALE_CONSTRUCT
        assert res["recommendation"] == ra.REC_REVAMP
        assert res["recommended_next"]["eligible_edge"] == ["demoted", "proposed"]

    def test_regime_pause_holds_operator(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach(), _breach()])
        res = ra.adjudicate_lobe(
            "lobe-x", "probation", cycle_id="c1",
            regime_paused=True, trajectory_label="degrading", root=root, emit=False,
        )
        assert res["topology"] == ra.TOPOLOGY_DOMAIN_SHIFT
        assert res["recommendation"] == ra.REC_HOLD_OPERATOR

    def test_health_dominant_holds_operator(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [
            _breach(counted=False, breach_type="health_miss", health_status="stale"),
            _breach(counted=False, breach_type="health_miss", health_status="missing"),
            _breach(counted=False, breach_type="health_miss", health_status="degraded"),
        ])
        res = ra.adjudicate_lobe("lobe-x", "demoted", cycle_id="c1", root=root, emit=False)
        assert res["topology"] == ra.TOPOLOGY_DOMAIN_SHIFT
        assert res["recommendation"] == ra.REC_HOLD_OPERATOR

    def test_dry_run_writes_no_io(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach(), _breach()])
        ra.adjudicate_lobe("lobe-x", "probation", cycle_id="c1",
                           trajectory_label="stagnating", root=root, emit=False)
        assert list((root / "data" / "metabolism" / "revamp_adjudications").iterdir()) == []
        assert not (root / "data" / "metabolism" / "insight_bus.jsonl").exists()

    def test_emit_writes_artifact_and_insight(self):
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        _write_journal(root, "lobe-x", [_breach(), _breach(), _breach()])
        ra.adjudicate_lobe("lobe-x", "probation", cycle_id="c1",
                           trajectory_label="stagnating", root=root, emit=True)
        art = root / "data" / "metabolism" / "revamp_adjudications" / "c1_lobe-x.json"
        assert art.exists()
        bus = root / "data" / "metabolism" / "insight_bus.jsonl"
        assert bus.exists()
        kinds = [json.loads(ln)["kind"] for ln in bus.read_text().splitlines() if ln.strip()]
        assert "revamp_recommendation" in kinds

    def test_classify_direct_call_survives_nondict_rows(self):
        # classify_failure_topology is public — a caller passing a raw list with a
        # non-dict element must not crash it.
        from engine.metabolism import revamp_adjudicator as ra
        rows = [_breach(), _breach(), _breach(), None, ["junk"]]
        out = ra.classify_failure_topology(rows, trajectory_label="degrading")
        assert out["topology"] == ra.TOPOLOGY_STALE_CONSTRUCT
        assert out["evidence"]["counted_logic_breaches"] == 3

    def test_survives_nondict_journal_row(self):
        # A non-dict journal row must NOT collapse a real logic failure into a
        # false 'insufficient_evidence' by crashing the classifier mid-loop.
        from engine.metabolism import revamp_adjudicator as ra
        root = _tmp_root()
        p = root / "data" / "metabolism" / "lifecycle" / "lobe-x.jsonl"
        with p.open("w", encoding="utf-8") as fh:
            for row in [_breach(), _breach(), _breach()]:
                fh.write(json.dumps(row) + "\n")
            fh.write("null\n")           # valid JSON, non-object
            fh.write('["garbage"]\n')    # valid JSON, non-object
        res = ra.adjudicate_lobe("lobe-x", "probation", cycle_id="c1",
                                 trajectory_label="stagnating", root=root, emit=False)
        assert res["topology"] == ra.TOPOLOGY_LOGIC_ERROR
        assert res["evidence"]["counted_logic_breaches"] == 3


# ── 16-21. Cross-cutting safety ─────────────────────────────────────────────────

class TestUnit6Safety:
    def _src(self, rel: str) -> str:
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_no_llm_import(self):
        for rel in ("engine/metabolism/scout.py", "engine/metabolism/revamp_adjudicator.py"):
            src = self._src(rel).lower()
            for banned in ("import anthropic", "import openai", "claude_code", "llm_auth",
                           "capability_broker", "key_pool"):
                assert banned not in src, f"{rel} contains {banned!r} — must be deterministic"

    def test_no_synapse_or_mastermind_write(self):
        # Neither module may write synapse.yml or a mastermind_context artifact.
        for rel in ("engine/metabolism/scout.py", "engine/metabolism/revamp_adjudicator.py"):
            src = self._src(rel)
            assert "synapse.yml" not in src, f"{rel} references synapse.yml"
            assert "mastermind_context" not in src, f"{rel} references mastermind_context"

    def test_neither_module_wires_lifecycle_transition(self):
        # INERT (R-V2-3): neither module may import the lifecycle machinery or
        # make ANY .transition() call — the only path that could emit a
        # governance event / lifecycle docket. (Checks actual code, not the
        # docstrings' negative claims: a call has an open paren, a mention
        # doesn't; an import contains 'lifecycle import'.)
        for rel in ("engine/metabolism/scout.py", "engine/metabolism/revamp_adjudicator.py"):
            src = self._src(rel)
            assert ".transition(" not in src, f"{rel} makes a .transition() call"
            assert "lifecycle import" not in src, f"{rel} imports from lifecycle"

    def test_coverage_ignores_free_text_notes(self):
        # A domain must not be marked covered by an incidental mention in a lobe's
        # free-text notes — a false-positive coverage silences a real proposal.
        from engine.metabolism import scout
        root = _tmp_root()
        _write_domains(root, [
            {"domain_id": "china_market", "label": "China", "coverage_match": ["china"]},
        ], default_min=99)
        _write_charters(root, {
            "some-lobe": _charter("some-lobe", domain="context",
                                  notes="tracks the health of the china book"),
        })
        _write_budget(root)
        res = scout.scan("c1", root=root)
        assert res["uncovered"] == ["china_market"]

    def test_banned_word_validated_absent(self):
        for rel in ("engine/metabolism/scout.py", "engine/metabolism/revamp_adjudicator.py",
                    "config/nw_information_domains.yml"):
            assert "validated" not in self._src(rel).lower(), f"{rel} uses banned word 'validated'"

    def test_config_fenced_in_self_mod(self):
        from scripts.check_self_mod_fence import IMMUTABLE_PATTERNS
        assert "config/nw_information_domains.yml" in IMMUTABLE_PATTERNS

    def test_config_in_grader_manifest(self):
        import yaml  # noqa: PLC0415
        manifest = yaml.safe_load((_ROOT / "config" / "grader_manifest.yml").read_text())
        paths = [e.get("path") for e in manifest.get("files", [])]
        assert "config/nw_information_domains.yml" in paths

    def test_insight_kinds_registered(self):
        from engine.metabolism.insight_bus import _KINDS
        assert "uncovered_domain" in _KINDS
        assert "revamp_recommendation" in _KINDS

    def test_scout_never_raises_on_garbage(self):
        from engine.metabolism import scout
        # Nonexistent root, no configs at all — must return a dict, not raise.
        res = scout.scan("c1", root=Path(tempfile.mkdtemp()))
        assert isinstance(res, dict)
        assert res["universe_size"] == 0

    def test_adjudicator_never_raises_on_garbage(self):
        from engine.metabolism import revamp_adjudicator as ra
        res = ra.adjudicate_lobe("ghost", "demoted", cycle_id="c1",
                                 root=Path(tempfile.mkdtemp()), emit=False)
        assert isinstance(res, dict)
        assert res["topology"] == ra.TOPOLOGY_INSUFFICIENT
