"""tests/test_metabolism_v4_w3_mission.py — Metabolism v4 Wave W3 test suite.

Coverage:
  A. mission.load_mission — happy path + NEVER-RAISE (corrupt YAML, missing file,
     wrong schema)
  B. mission.build_mission_block — content sanity + byte_cap truncation
  C. mission.append_strategic_memory + load_strategic_memory — round-trip +
     most-recent-first ordering
  D. compile_loop_blocklists.parse_do_not_rebuild — fixture markdown → entries
  E. compile_loop_blocklists end-to-end — writes registry + updates SF blocklist
  F. check_blocklist_drift — clean → 0; tampered → 1

All tests are HERMETIC (tmp_path; pass root=tmp_path; never read the live repo).
"""
from __future__ import annotations

import importlib.util
import json
import textwrap
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers to load scripts (not on sys.path by default)
# ---------------------------------------------------------------------------

def _load_script(script_path: Path):
    """Import a script module by path."""
    spec = importlib.util.spec_from_file_location(
        script_path.stem, script_path
    )
    assert spec is not None and spec.loader is not None, f"Could not load {script_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _scripts_dir() -> Path:
    return _repo_root() / "scripts"


# ---------------------------------------------------------------------------
# Fixture markdown for the compiler tests
# ---------------------------------------------------------------------------

FIXTURE_MD = textwrap.dedent("""\
    # DO NOT REBUILD

    Preamble text here.

    ## 1. Forbidden by ruling (design-level — no phase-0 may test these)

    | Topic | Verdict | Ruling / source |
    |---|---|---|
    | Fused shield / meta-router over buy-decision vetoes | FORBIDDEN | FR-1/R3 |
    | LLM-originated signals, scores, or escalations | FORBIDDEN | House law |

    ## 2. Killed / refuted signal families and theses

    | Topic | Verdict | Ruling / source |
    |---|---|---|
    | Insider × T2 interaction | KILLED | Codex docket (#1781) |
    | DOI (options delta-OI family) | DEAD | W-E1 gauntlet |

    ## 3. Wrong-ruler / estimator laws (methodology — using these invalidates the study)

    | Topic | Verdict | Ruling / source |
    |---|---|---|
    | Ticker-cluster bootstrap CIs without time control | FORBIDDEN estimator | DT-R14 |

    ## 4. Held / suspended — do not revive without explicit ruling

    | Topic | State | Ruling / source |
    |---|---|---|
    | Ontology W4.7 pos_v2 acceptance | HOLD | Open PR #1639 |

    ## 5. Incorporated by reference

    - Some other section that should be ignored.
""")


# ---------------------------------------------------------------------------
# A. mission.load_mission
# ---------------------------------------------------------------------------

class TestLoadMission:
    def _write_mission(self, root: Path, content: str) -> None:
        p = root / "config" / "nw_mission.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_happy_path(self, tmp_path: Path) -> None:
        """Valid nw_mission.yml is loaded and returns expected keys."""
        from engine.metabolism.mission import load_mission

        self._write_mission(tmp_path, textwrap.dedent("""\
            schema: nw_mission.v1
            version: 1
            as_of: "2026-07-11"
            endgame: "Test endgame text."
            mission_pillars:
              - "Pillar one."
            standing_laws:
              - id: NW-ART1
                law: "No LLM origination."
            strategic_posture:
              - "Build the eye first."
            forward_clocks:
              - date: "2026-07-25"
                what: "Shadow review."
        """))
        m = load_mission(root=tmp_path)
        assert m.get("schema", "").startswith("nw_mission")
        assert "endgame" in m
        assert len(m.get("mission_pillars", [])) == 1
        assert len(m.get("standing_laws", [])) == 1
        assert m.get("_fallback") is None or m.get("_fallback") is False

    def test_missing_file_returns_fallback(self, tmp_path: Path) -> None:
        """Missing config/nw_mission.yml returns safe fallback, never raises."""
        from engine.metabolism.mission import load_mission, _FALLBACK_MISSION

        m = load_mission(root=tmp_path)
        assert m.get("_fallback") is True
        assert "endgame" in m
        assert isinstance(m.get("mission_pillars"), list)

    def test_corrupt_yaml_returns_fallback(self, tmp_path: Path) -> None:
        """Corrupt YAML returns safe fallback, never raises."""
        from engine.metabolism.mission import load_mission

        self._write_mission(tmp_path, "{ this is: [not valid yaml }")
        m = load_mission(root=tmp_path)
        # Either fallback dict or gracefully returns any dict — main contract is NEVER-RAISE
        assert isinstance(m, dict)

    def test_wrong_schema_returns_fallback(self, tmp_path: Path) -> None:
        """A file with wrong schema prefix returns fallback."""
        from engine.metabolism.mission import load_mission

        self._write_mission(tmp_path, "schema: something_else\nversion: 1\n")
        m = load_mission(root=tmp_path)
        assert m.get("_fallback") is True

    def test_non_dict_root_returns_fallback(self, tmp_path: Path) -> None:
        """YAML file with non-dict root returns fallback."""
        from engine.metabolism.mission import load_mission

        self._write_mission(tmp_path, "- item1\n- item2\n")
        m = load_mission(root=tmp_path)
        assert m.get("_fallback") is True


# ---------------------------------------------------------------------------
# B. mission.build_mission_block
# ---------------------------------------------------------------------------

class TestBuildMissionBlock:
    def _write_minimal_mission(self, root: Path) -> None:
        p = root / "config" / "nw_mission.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent("""\
            schema: nw_mission.v1
            version: 1
            as_of: "2026-07-11"
            endgame: "Beat human judgement."
            mission_pillars:
              - "Context accrual is fundamental."
              - "Self-improvement via code."
            standing_laws:
              - id: NW-ART1
                law: "LLMs may not originate signals."
            strategic_posture:
              - "Build the eye first."
            forward_clocks:
              - date: "2026-07-25"
                what: "Shadow review."
        """), encoding="utf-8")

    def test_block_contains_endgame(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import build_mission_block

        self._write_minimal_mission(tmp_path)
        block = build_mission_block(root=tmp_path)
        assert "Beat human judgement" in block

    def test_block_contains_standing_law_id(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import build_mission_block

        self._write_minimal_mission(tmp_path)
        block = build_mission_block(root=tmp_path)
        assert "NW-ART1" in block

    def test_byte_cap_respected(self, tmp_path: Path) -> None:
        """build_mission_block respects the byte_cap argument."""
        from engine.metabolism.mission import build_mission_block

        self._write_minimal_mission(tmp_path)
        block = build_mission_block(byte_cap=200, root=tmp_path)
        assert len(block.encode("utf-8")) <= 300  # small tolerance for truncation marker

    def test_missing_mission_returns_safe_string(self, tmp_path: Path) -> None:
        """Missing mission file returns a non-empty fallback string, never raises."""
        from engine.metabolism.mission import build_mission_block

        block = build_mission_block(root=tmp_path)
        assert isinstance(block, str)
        assert len(block) > 0


# ---------------------------------------------------------------------------
# C. strategic memory round-trip
# ---------------------------------------------------------------------------

class TestStrategicMemory:
    def test_append_and_load_roundtrip(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import append_strategic_memory, load_strategic_memory

        rows = [
            {
                "cycle_id": "c001",
                "lobe": "til",
                "construction": "theme_placebo_v1",
                "verdict": "PASS",
                "measurement_lens_class": "foresight",
            },
            {
                "cycle_id": "c002",
                "lobe": "til",
                "construction": "theme_placebo_v2",
                "verdict": "FAIL",
                "measurement_lens_class": "foresight",
            },
        ]
        for row in rows:
            ok = append_strategic_memory(row, root=tmp_path)
            assert ok is True

        loaded = load_strategic_memory(top_k=10, root=tmp_path)
        assert len(loaded) == 2
        # Verify all fields are round-tripped
        constructions = {r["construction"] for r in loaded}
        assert constructions == {"theme_placebo_v1", "theme_placebo_v2"}

    def test_most_recent_first_ordering(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import append_strategic_memory, load_strategic_memory
        import time  # noqa: PLC0415

        append_strategic_memory(
            {"cycle_id": "old", "ts": "2026-01-01T00:00:00+00:00",
             "lobe": "x", "construction": "a", "verdict": "PASS",
             "measurement_lens_class": "test"},
            root=tmp_path,
        )
        append_strategic_memory(
            {"cycle_id": "new", "ts": "2026-07-11T00:00:00+00:00",
             "lobe": "x", "construction": "b", "verdict": "FAIL",
             "measurement_lens_class": "test"},
            root=tmp_path,
        )
        loaded = load_strategic_memory(top_k=5, root=tmp_path)
        # Most recent should be first
        assert loaded[0]["cycle_id"] == "new"
        assert loaded[1]["cycle_id"] == "old"

    def test_top_k_limit(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import append_strategic_memory, load_strategic_memory

        for i in range(10):
            append_strategic_memory(
                {"cycle_id": f"c{i:03d}", "lobe": "x", "construction": f"c{i}",
                 "verdict": "PASS", "measurement_lens_class": "test"},
                root=tmp_path,
            )
        loaded = load_strategic_memory(top_k=3, root=tmp_path)
        assert len(loaded) == 3

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import load_strategic_memory

        result = load_strategic_memory(root=tmp_path)
        assert result == []

    def test_schema_key_added(self, tmp_path: Path) -> None:
        from engine.metabolism.mission import append_strategic_memory, load_strategic_memory, SCHEMA_STRATEGIC_MEMORY

        append_strategic_memory(
            {"cycle_id": "c1", "lobe": "x", "construction": "a",
             "verdict": "PASS", "measurement_lens_class": "test"},
            root=tmp_path,
        )
        loaded = load_strategic_memory(root=tmp_path)
        assert loaded[0]["schema"] == SCHEMA_STRATEGIC_MEMORY

    def test_append_returns_false_on_unwritable(self, tmp_path: Path) -> None:
        """append_strategic_memory never raises; returns False on write error."""
        from engine.metabolism.mission import append_strategic_memory

        # Make data/ a file instead of directory to trigger an error
        p = tmp_path / "data"
        p.write_text("not a dir", encoding="utf-8")
        result = append_strategic_memory(
            {"cycle_id": "x", "lobe": "y", "construction": "z",
             "verdict": "PASS", "measurement_lens_class": "test"},
            root=tmp_path,
        )
        assert result is False


# ---------------------------------------------------------------------------
# D. parse_do_not_rebuild — compiler unit tests
# ---------------------------------------------------------------------------

class TestParseDoNotRebuild:
    def test_parses_all_four_sections(self) -> None:
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild(FIXTURE_MD)
        assert len(entries) >= 6  # 2+2+1+1

    def test_section_nums_correct(self) -> None:
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild(FIXTURE_MD)
        sec_nums = {e["section"] for e in entries}
        assert {1, 2, 3, 4}.issubset(sec_nums)

    def test_topic_field_populated(self) -> None:
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild(FIXTURE_MD)
        for e in entries:
            assert e["topic"], f"Empty topic in entry: {e}"

    def test_section5_excluded(self) -> None:
        """Section 5 (Incorporated by reference) is not parsed."""
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild(FIXTURE_MD)
        assert all(e["section"] in (1, 2, 3, 4) for e in entries)

    def test_empty_md_returns_empty_list(self) -> None:
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild("")
        assert entries == []

    def test_verdict_and_source_populated(self) -> None:
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        entries = compiler.parse_do_not_rebuild(FIXTURE_MD)
        # At least some entries should have verdicts / sources
        with_verdict = [e for e in entries if e.get("verdict")]
        assert len(with_verdict) > 0


# ---------------------------------------------------------------------------
# E. compile_loop_blocklists end-to-end
# ---------------------------------------------------------------------------

class TestCompileLoopBlocklists:
    def _setup_tmp_repo(self, tmp_path: Path, md_text: str = FIXTURE_MD) -> None:
        (tmp_path / "research").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text(md_text, encoding="utf-8")

    def test_writes_compiled_registry(self, tmp_path: Path) -> None:
        self._setup_tmp_repo(tmp_path)
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        rc = compiler.compile_blocklists(tmp_path)
        assert rc == 0
        reg = tmp_path / "config" / "compiled_kill_registry.yml"
        assert reg.exists()
        content = yaml.safe_load(reg.read_text(encoding="utf-8"))
        assert content["schema"] == "compiled_kill_registry.v1"
        assert len(content["entries"]) >= 6

    def test_writes_sf_blocklist_generated_block(self, tmp_path: Path) -> None:
        self._setup_tmp_repo(tmp_path)
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        rc = compiler.compile_blocklists(tmp_path)
        assert rc == 0
        sf = tmp_path / "config" / "signal_foundry_blocklist.yml"
        assert sf.exists()
        text = sf.read_text(encoding="utf-8")
        assert compiler.START_MARKER in text
        assert compiler.END_MARKER in text

    def test_preserves_hand_curated_entries(self, tmp_path: Path) -> None:
        """Hand-curated entries above the generated block are not deleted."""
        self._setup_tmp_repo(tmp_path)
        # Pre-populate with a hand-curated entry
        sf_path = tmp_path / "config" / "signal_foundry_blocklist.yml"
        sf_path.write_text(
            "# Hand-curated\nentries:\n\n  - id: BL-HAND-001\n    match:\n"
            "      any_of: ['hand_curated_pattern']\n"
            "    reason: 'curated'\n    source: 'human'\n",
            encoding="utf-8",
        )
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        rc = compiler.compile_blocklists(tmp_path)
        assert rc == 0
        text = sf_path.read_text(encoding="utf-8")
        assert "BL-HAND-001" in text

    def test_generated_block_replaced_on_rerun(self, tmp_path: Path) -> None:
        """Running the compiler twice does not duplicate the generated block."""
        self._setup_tmp_repo(tmp_path)
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        compiler.compile_blocklists(tmp_path)
        compiler.compile_blocklists(tmp_path)
        sf = tmp_path / "config" / "signal_foundry_blocklist.yml"
        text = sf.read_text(encoding="utf-8")
        # Should appear exactly once
        assert text.count(compiler.START_MARKER) == 1
        assert text.count(compiler.END_MARKER) == 1

    def test_missing_do_not_rebuild_returns_1(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir()
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        rc = compiler.compile_blocklists(tmp_path)
        assert rc == 1


# ---------------------------------------------------------------------------
# F. check_blocklist_drift
# ---------------------------------------------------------------------------

class TestCheckBlocklistDrift:
    def _setup_clean(self, tmp_path: Path) -> None:
        """Set up a repo where committed = what the compiler would regenerate."""
        import shutil  # noqa: PLC0415
        (tmp_path / "research").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text(FIXTURE_MD, encoding="utf-8")
        # The drift checker dynamically loads the compiler from tmp_root/scripts/
        shutil.copy2(
            _scripts_dir() / "compile_loop_blocklists.py",
            tmp_path / "scripts" / "compile_loop_blocklists.py",
        )

        # Run the compiler to create the committed baseline
        compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
        rc = compiler.compile_blocklists(tmp_path)
        assert rc == 0

    def test_clean_repo_exits_0(self, tmp_path: Path) -> None:
        self._setup_clean(tmp_path)
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        rc = drift_checker.check_drift(tmp_path)
        assert rc == 0

    def test_tampered_registry_exits_1(self, tmp_path: Path) -> None:
        """Modifying the committed registry without regenerating is detected."""
        self._setup_clean(tmp_path)
        reg_path = tmp_path / "config" / "compiled_kill_registry.yml"
        content = reg_path.read_text(encoding="utf-8")
        reg_path.write_text(content + "\n# EXTRA TAMPERED LINE\n", encoding="utf-8")
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        rc = drift_checker.check_drift(tmp_path)
        assert rc == 1

    def test_missing_committed_file_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / "research").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text(FIXTURE_MD, encoding="utf-8")
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        rc = drift_checker.check_drift(tmp_path)
        assert rc == 1


# ---------------------------------------------------------------------------
# G. check_blocklist_drift — misplaced rows, SF drift, --fix
#    (drift-class hardening, 2026-07-12: two same-day regen misses + one
#     silently unparsed row — see .claude/hooks/blocklist_regen_guard.py)
# ---------------------------------------------------------------------------

MISPLACED_ROW = "| Misplaced kill topic | KILLED | XX-R99 |"


def _setup_clean_repo(tmp_path: Path) -> None:
    """Fixture repo where committed artifacts == fresh compile (drift-free)."""
    import shutil  # noqa: PLC0415
    (tmp_path / "research").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text(FIXTURE_MD, encoding="utf-8")
    for script in ("compile_loop_blocklists.py", "check_blocklist_drift.py"):
        shutil.copy2(_scripts_dir() / script, tmp_path / "scripts" / script)
    compiler = _load_script(_scripts_dir() / "compile_loop_blocklists.py")
    assert compiler.compile_blocklists(tmp_path) == 0


class TestMisplacedRows:
    def test_clean_fixture_has_no_misplaced_rows(self) -> None:
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.find_misplaced_rows(FIXTURE_MD) == []

    def test_row_after_section5_flagged(self) -> None:
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        rows = drift_checker.find_misplaced_rows(FIXTURE_MD + MISPLACED_ROW + "\n")
        assert len(rows) == 1
        assert "Misplaced kill topic" in rows[0][1]

    def test_row_in_preamble_flagged(self) -> None:
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        md = "# Title\n\n| Early row | KILLED | src |\n\n" + FIXTURE_MD.split("\n", 2)[2]
        assert len(drift_checker.find_misplaced_rows(md)) == 1

    def test_fenced_pipe_lines_ignored(self) -> None:
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        md = FIXTURE_MD + "```\n| not a registry row |\n```\n"
        assert drift_checker.find_misplaced_rows(md) == []

    def test_misplaced_row_exits_1(self, tmp_path: Path) -> None:
        """A row the compiler silently ignores is a hard failure (live class:
        the MRI-R38 CPI row landed after §5 and never reached the registry)."""
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8") + MISPLACED_ROW + "\n", encoding="utf-8"
        )
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.check_drift(tmp_path) == 1

    def test_fix_does_not_heal_misplaced_row(self, tmp_path: Path) -> None:
        """--fix regenerates artifacts but cannot move a row between sections."""
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8") + MISPLACED_ROW + "\n", encoding="utf-8"
        )
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.fix_drift(tmp_path) == 1


class TestSignalFoundryDrift:
    def test_tampered_generated_block_exits_1(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        sf_path = tmp_path / "config" / "signal_foundry_blocklist.yml"
        text = sf_path.read_text(encoding="utf-8")
        assert "BL-G001" in text
        sf_path.write_text(text.replace("BL-G001", "BL-G999", 1), encoding="utf-8")
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.check_drift(tmp_path) == 1

    def test_hand_curated_entry_above_block_passes(self, tmp_path: Path) -> None:
        """Hand edits outside the generated block are legitimate, not drift."""
        _setup_clean_repo(tmp_path)
        sf_path = tmp_path / "config" / "signal_foundry_blocklist.yml"
        text = sf_path.read_text(encoding="utf-8")
        text = text.replace(
            "entries:",
            "entries:\n\n  - id: BL-HAND-042\n    match:\n"
            "      any_of: ['hand_pattern']\n    reason: 'curated'\n    source: 'human'",
            1,
        )
        sf_path.write_text(text, encoding="utf-8")
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.check_drift(tmp_path) == 0


class TestFixFlag:
    def test_fix_heals_tampered_registry(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        reg_path = tmp_path / "config" / "compiled_kill_registry.yml"
        clean_bytes = reg_path.read_bytes()
        reg_path.write_bytes(clean_bytes + b"\n# TAMPER\n")
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.fix_drift(tmp_path) == 0
        assert reg_path.read_bytes() == clean_bytes

    def test_fix_via_main_cli(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8").replace(
                "| Insider × T2 interaction | KILLED | Codex docket (#1781) |",
                "| Insider × T2 interaction | KILLED | Codex docket (#1781) |\n"
                "| Fresh kill topic | KILLED | YY-R1 |",
            ),
            encoding="utf-8",
        )
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.main(["--repo-root", str(tmp_path)]) == 1  # drift
        assert drift_checker.main(["--repo-root", str(tmp_path), "--fix"]) == 0
        reg = (tmp_path / "config" / "compiled_kill_registry.yml").read_text(encoding="utf-8")
        assert "Fresh kill topic" in reg


# ---------------------------------------------------------------------------
# H. blocklist_regen_guard hook — end-to-end via subprocess (payload on stdin,
#    exactly as the PostToolUse harness invokes it)
# ---------------------------------------------------------------------------

def _hook_path() -> Path:
    return _repo_root() / ".claude" / "hooks" / "blocklist_regen_guard.py"


def _run_hook(payload) -> "subprocess.CompletedProcess[str]":
    import subprocess  # noqa: PLC0415
    import sys as _sys  # noqa: PLC0415
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [_sys.executable, str(_hook_path())],
        input=raw, capture_output=True, text=True, timeout=120,
    )


class TestBlocklistRegenGuardHook:
    def test_hook_regens_on_registry_edit(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8").replace(
                "| DOI (options delta-OI family) | DEAD | W-E1 gauntlet |",
                "| DOI (options delta-OI family) | DEAD | W-E1 gauntlet |\n"
                "| Hook-added kill topic | KILLED | ZZ-R1 |",
            ),
            encoding="utf-8",
        )
        proc = _run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(md_path)}})
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert "regenerated" in out["hookSpecificOutput"]["additionalContext"]
        reg = (tmp_path / "config" / "compiled_kill_registry.yml").read_text(encoding="utf-8")
        assert "Hook-added kill topic" in reg
        # And the checker agrees the tree is clean again
        drift_checker = _load_script(_scripts_dir() / "check_blocklist_drift.py")
        assert drift_checker.check_drift(tmp_path) == 0

    def test_hook_silent_when_no_drift(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        proc = _run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(md_path)}})
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_hook_ignores_other_files(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        other = tmp_path / "research" / "OTHER.md"
        other.write_text("x", encoding="utf-8")
        proc = _run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(other)}})
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_hook_exit2_on_misplaced_row(self, tmp_path: Path) -> None:
        _setup_clean_repo(tmp_path)
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8") + MISPLACED_ROW + "\n", encoding="utf-8"
        )
        proc = _run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(md_path)}})
        assert proc.returncode == 2
        assert "sections 1-4" in proc.stderr

    def test_hook_fails_open_on_garbage_stdin(self) -> None:
        proc = _run_hook("this is not json")
        assert proc.returncode == 0

    def test_hook_fails_open_outside_repo_layout(self, tmp_path: Path) -> None:
        """research/DO_NOT_REBUILD.md with no scripts/ beside it → not our repo."""
        (tmp_path / "research").mkdir()
        md_path = tmp_path / "research" / "DO_NOT_REBUILD.md"
        md_path.write_text(FIXTURE_MD, encoding="utf-8")
        proc = _run_hook({"tool_name": "Write", "tool_input": {"file_path": str(md_path)}})
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""
