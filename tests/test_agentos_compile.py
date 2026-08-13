"""Agent OS Phase 3 — `agentos.py compile-context`.

A context bundle is TESTIMONY: a session acts on it without opening the sources.  So the
properties worth pinning are the ones that make it trustworthy rather than merely
plausible, and every one of them is asserted against a NEGATIVE fixture — an exclusion
rule with nothing to exclude is untested, and reads identically to no rule at all.

* **Every line is cited.**  On the real seeded store, every item in every section carries
  a `path` and a `why_included`.  An uncited line is a claim the reader cannot check.
* **Exclusion is by FIELD and is NAMED.**  A superseded decision, an expired discovery,
  an uncited-and-stale discovery, an older handoff and a malformed record each land in
  `excluded` with the specific reason — never silently absent, never co-equal in a
  section.
* **The boundary is structural.**  Records belonging to another program cannot appear at
  all: search hits only VOTE for a workstream, and content comes from the graph walk.
* **The cap is honest, and it never costs a constraint.**  When the budget binds,
  `omitted_due_to_budget` is a LIST with token costs, and the bundle still fits.  A silent
  truncation reads exactly like a smaller store.  HIGHER LAW is exempt from the cap
  alongside the workstream block: a bundle that spent its last tokens on file pointers
  while dropping the rows a session may not violate is worse than one that overran.
* **I4, both directions.**  Naming an unknown or malformed workstream exits 1
  (fail-CLOSED on schema); a missing sibling repo, a missing active_builds.json and a
  missing index all exit 0 with `degraded` populated (fail-OPEN on join).
* **I1 and read-only.**  Nothing here can gate anything, and the store is byte-identical
  after a run.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "agentos"
CLI = REPO / "scripts" / "agentos.py"

# Agent worktrees here are frequently CONE-MODE SPARSE, and a directory outside the cone
# is simply absent.  CI checks out the full tree, so this never skips there.
pytestmark = pytest.mark.skipif(
    not STORE.exists(),
    reason="agentos/ outside this sparse checkout — run: git sparse-checkout add agentos",
)

FROZEN = "2026-08-12T14:00:00Z"
SEED_KEYS = (
    sorted(path.stem[3:] for path in (STORE / "workstreams").glob("WS-*.md"))
    if STORE.exists() else []
)


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI with the sibling checkouts pinned ABSENT.

    Otherwise the result depends on which repos happen to exist on the machine running
    the suite — green here and red on a runner, or the reverse.
    """
    environ = dict(os.environ)
    environ.setdefault("MACRO_TERMINAL_REPO", "/nonexistent-terminal-checkout")
    environ.setdefault("MACRO_MASTERMIND_REPO", "/nonexistent-mastermind-checkout")
    if env:
        environ.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, cwd=REPO, env=environ,
    )


def _compile(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return _run("compile-context", "--now", FROZEN, *args, **kwargs)


def _bundle(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _load_cli():
    """Import scripts/agentos.py as a module, so the search seam can be injected."""
    spec = importlib.util.spec_from_file_location("agentos_compile_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _items(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for section in bundle["sections"] for item in section["items"]]


def _section(bundle: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(section for section in bundle["sections"] if section["id"] == ident)


def _tokens(item: dict[str, Any]) -> int:
    """The packer's chars/4 estimate, MIRRORED not imported.

    Importing the estimator under test would make the budget arithmetic here agree with
    the compiler by construction — including when both are wrong.
    """
    return max(1, len(item["excerpt"]) // 4)


# ------------------------------------------------------------- fixture builders
#
# Records are written as real files rather than mocked, because the compiler's whole job
# is to read this format — a fixture that skipped the frontmatter contract would test a
# different program.  `program` values are REAL keys from config/mastermind_programs.yml
# (validate hard-fails an unknown program, which would make every fixture malformed).

PROGRAM = "prophet-us"
OTHER_PROGRAM = "agentic-media"

# A REAL row in config/compiled_kill_registry.yml.  An unresolvable key degrades loudly
# and emits NOTHING, which would leave the higher-law fixture carrying only its program
# row — a fixture that silently stopped exercising the class it exists to pin.
DNR_KEY = "KILL-FUSED-SHIELD"


def _write(path: Path, front: dict[str, Any], body: str = "Fixture body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(front, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{dumped}---\n\n{body}", encoding="utf-8")


def _workstream(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "title": f"{key} in one line",
        "objective": "Ship the thing and prove it shipped.",
        "status": "active",
        "program": PROGRAM,
        "repos": ["macro"],
        "owner": "coo-fable",
        "class": "research",
        "blast_radius": "reversible",
        "ambiguity": "open",
        "waves": [{"id": "W0", "title": "First wave", "status": "todo"}],
        "next_action": "Run the next command.",
    }
    front.update(extra)
    _write(root / "workstreams" / f"WS-{key}.md", front)


def _decision(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "question": f"Should we {key.lower()}?",
        "answer": "Yes, with the stated bound.",
        "rationale": "Because the measured alternative cost more and proved less.",
        "alternatives": [{"option": "Do nothing", "why_not": "The defect recurs nightly."}],
        "evidence": ["tests/test_agentos_compile.py — this fixture"],
        "affects": ["WS:TARGET"],
        "confidence": "high",
        "reversibility": "easy",
        "decided_by": "fixture",
        "decided_at": "2026-08-01",
    }
    front.update(extra)
    _write(root / "decisions" / f"DEC-{key}.md", front)


def _discovery(root: Path, key: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "key": key,
        "claim": f"{key} behaves as described under the named repro.",
        "falsifier": "pytest tests/test_agentos_compile.py — a pass disproves it.",
        "so_what": "A future session stops re-deriving this.",
        "kind": "architecture",
        "verified_at": "2026-08-10",
        "verified_by": "pytest tests/test_agentos_compile.py",
        "scope": ["WS:TARGET"],
        "confidence": "verified",
    }
    front.update(extra)
    _write(root / "discoveries" / f"DSC-{key}.md", front)


def _handoff(root: Path, stem: str, **extra: Any) -> None:
    front: dict[str, Any] = {
        "workstream": "WS:TARGET",
        "session": "claude/fixture",
        "model": "opus",
        "mission": "Land the first wave.",
        "state_before": "Nothing existed.",
        "changed": [{"path": "scripts/agentos.py", "what": "added the compiler"}],
        "verified": [{"claim": "suite green",
                      "command": "pytest tests/test_agentos_compile.py"}],
        "unverified": [],
        "unresolved": ["Whether the budget floor is right."],
        "next_actions": ["Run the suite."],
        "do_not_redo": ["The resolution design — settled in DEC:AGENTOS-NO-TASK-STORE."],
        "danger_areas": ["The budget packer."],
        "ended_because": "complete",
    }
    front.update(extra)
    _write(root / "handoffs" / f"{stem}.md", front, "Handoff body, self-contained.\n")


@pytest.fixture()
def simple(tmp_path: Path) -> Path:
    """One workstream, one decision, one discovery — the happy shape."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"])
    _decision(root, "KEEP")
    _discovery(root, "KEEP")
    return root


@pytest.fixture()
def overfull(tmp_path: Path) -> Path:
    """Far more reachable records than any small budget can carry."""
    root = tmp_path / "agentos"
    padding = "This rationale is deliberately long so the budget binds. " * 12
    keys = [f"BULK{index:02d}" for index in range(12)]
    _workstream(
        root, "TARGET",
        decisions=[f"DEC:{key}" for key in keys],
        discoveries=[f"DSC:{key}" for key in keys],
    )
    for key in keys:
        _decision(root, key, rationale=padding)
        _discovery(root, key, claim=padding)
    return root


@pytest.fixture()
def constrained(tmp_path: Path) -> Path:
    """An EXPENSIVE workstream block sitting above cheap pointers, plus higher law.

    `overfull` cannot exercise this: its workstream block costs ~72 tokens, so higher law
    fits under any budget above the floor and the rule would be untested.  The inversion
    needs the shape of a REAL record — one that carries landmines — so that greedy
    packing reaches HIGHER LAW with only change left, and ARTIFACTS is cheap enough to
    spend it.
    """
    root = tmp_path / "agentos"
    landmine = "A landmine stated at the length a real landmine is stated at. " * 5
    padding = "This rationale is deliberately long so the budget binds. " * 12
    keys = [f"BULK{index:02d}" for index in range(6)]
    _workstream(
        root, "TARGET",
        landmines=[f"{landmine}({index})" for index in range(4)],
        do_not_redo=[f"Settled — the resolution design is closed; see DNR:{DNR_KEY}."],
        artifacts=[f"research/POINTER_{index}.md" for index in range(3)],
        decisions=[f"DEC:{key}" for key in keys],
        discoveries=[f"DSC:{key}" for key in keys],
    )
    for key in keys:
        _decision(root, key, rationale=padding)
        _discovery(root, key, claim=padding)
    return root


# --------------------------------------------------------------- the real store


def test_every_seeded_workstream_compiles_and_every_line_is_cited() -> None:
    """The acceptance gate, on real data: bounded, and nothing uncited.

    `why_included` is not decoration.  A bundle is read by a session that will not open
    the sources, so an item that cannot say why it is present is an assertion with no
    provenance — exactly what §8's "everything is cited" exists to forbid.
    """
    assert SEED_KEYS, "the seeded store has no workstreams to compile"
    for key in SEED_KEYS:
        bundle = _bundle(_compile("--workstream", key))
        assert bundle["schema"] == "context_bundle.v1"
        assert bundle["target"]["workstream"] == f"WS:{key}"
        assert bundle["target"]["resolution"] == "explicit"
        assert bundle["token_estimate"] <= bundle["token_budget"], key
        items = _items(bundle)
        assert items, f"{key} compiled to an empty bundle"
        for item in items:
            assert item["path"], f"{key}: uncited item {item['kind']}"
            assert item["why_included"], f"{key}: unexplained item {item['path']}"
            assert item["authority_class"], f"{key}: unranked item {item['path']}"
        assert _section(bundle, "workstream")["items"], f"{key} lost its own record"


def test_the_section_order_is_the_authority_order() -> None:
    """Presentation order IS the contract (WP-E) — law above evidence, always."""
    bundle = _bundle(_compile("--workstream", SEED_KEYS[0]))
    assert [section["id"] for section in bundle["sections"]] == [
        "higher_law", "workstream", "decisions", "discoveries", "handoff", "artifacts",
    ]


def test_workstream_mode_never_imports_the_retrieval_engine() -> None:
    """The index import is LAZY, and that is load-bearing, not an optimisation.

    `--workstream` must work in a checkout where `engine/` was never checked out — which
    is the normal state of a sparse agent worktree.  A module-level import would make the
    whole subcommand unusable there.
    """
    source = CLI.read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            assert "engine" not in line, f"engine imported at module scope: {line!r}"
    probe = (
        "import sys; sys.path.insert(0, %r); import importlib;"
        "m = importlib.import_module('scripts.agentos');"
        "print('LOADED:' + ','.join(k for k in sys.modules if 'context_index' in k))"
        % str(REPO)
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            cwd=REPO)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LOADED:", result.stdout


# ------------------------------------------------------------------- the budget


def test_the_budget_binds_and_says_what_it_dropped(overfull: Path) -> None:
    """A cap that truncates silently is indistinguishable from a smaller store."""
    bundle = _bundle(_compile("--root", str(overfull), "--workstream", "TARGET",
                              "--budget", "700"))
    assert bundle["token_budget"] == 700
    assert bundle["token_estimate"] <= 700, "the bundle overran its own cap"
    omitted = bundle["omitted_due_to_budget"]
    assert omitted, "24 padded records fit in 700 tokens — the packer did not run"
    for row in omitted:
        assert row["path"] and row["tokens"] > 0
        assert isinstance(row["rank"], int)
    assert _section(bundle, "workstream")["items"], (
        "the target's own record was dropped — it is the one item that never may be"
    )


def test_a_binding_cap_never_costs_a_constraint(constrained: Path) -> None:
    """HIGHER LAW is not tradable against ARTIFACTS.

    Greedy-with-continuation alone emptied the constraint class while the pointer class
    still rendered: the cheap tail fits in the change the expensive head leaves behind.
    A bundle exists to tell a cold session which constraints it may not violate, so
    losing them to a cap while keeping file paths inverts the whole point of the
    document.  Higher law therefore joins the workstream block in the always-include set,
    and the documented degenerate-budget exception extends to it — `token_estimate` may
    exceed `token_budget` only when those two packs ALONE exceed it.
    """
    def compile_at(budget: str) -> dict[str, Any]:
        return _bundle(_compile("--root", str(constrained), "--workstream", "TARGET",
                                "--budget", budget))

    uncapped = compile_at("100000")
    law = _section(uncapped, "higher_law")["items"]
    assert {item["kind"] for item in law} == {"dnr", "program"}, (
        f"the fixture stopped exercising higher law: {law}"
    )
    assert not uncapped["omitted_due_to_budget"], "100k tokens should omit nothing"

    # Tiny cap: the always-include set alone overruns it — the documented exception.
    tight = compile_at("500")
    assert _section(tight, "higher_law")["items"] == law, (
        "the cap dropped a constraint-class item"
    )
    assert tight["omitted_due_to_budget"], "12 padded records fit in 500 tokens"
    assert not [row for row in tight["omitted_due_to_budget"]
                if row["kind"] in {"dnr", "p0", "program"}], "higher law was omitted"
    assert not _section(tight, "artifacts")["items"], (
        "a pointer outlived a constraint — the exact inversion this rule forbids"
    )
    always = (_section(tight, "workstream")["items"]
              + _section(tight, "higher_law")["items"])
    assert tight["token_estimate"] == sum(_tokens(item) for item in always), (
        "the exception is bounded to the always-include set; nothing else may overrun"
    )

    # Roomier cap: with space for the always-include set, the cap binds as before.
    roomy = compile_at("900")
    assert _section(roomy, "higher_law")["items"] == law
    assert roomy["token_estimate"] <= 900, "the bundle overran a non-degenerate cap"
    assert roomy["omitted_due_to_budget"], "the packer did not run"


def test_the_budget_floor_refuses_a_degenerate_cap(overfull: Path) -> None:
    """`--budget 0` must not render an empty bundle that looks like an empty store."""
    bundle = _bundle(_compile("--root", str(overfull), "--workstream", "TARGET",
                              "--budget", "0"))
    assert bundle["token_budget"] == 500
    assert _section(bundle, "workstream")["items"]


# --------------------------------------------------------------- the exclusions


def test_a_superseded_decision_is_excluded_and_named(tmp_path: Path) -> None:
    """Supersession is why BOTH records survive; a bundle listing them as peers undoes it."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", decisions=["DEC:OLD", "DEC:NEW"])
    _decision(root, "OLD", superseded_by="DEC:NEW", decided_at="2026-07-01")
    _decision(root, "NEW", supersedes=["DEC:OLD"], decided_at="2026-08-05")
    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))

    keys = [item["key"] for item in _items(bundle)]
    assert "DEC:NEW" in keys
    assert "DEC:OLD" not in keys, "a superseded decision was rendered as current"
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:OLD"]
    assert dropped, "the superseded record vanished instead of being named"
    assert "superseded_by DEC:NEW" in dropped[0]["reason"]

    survivor = next(item for item in _items(bundle) if item["key"] == "DEC:NEW")
    assert "supersedes DEC:OLD" in survivor["excerpt"], (
        "provenance is allowed and useful; co-equality is not"
    )


def test_stale_discoveries_are_excluded_with_the_specific_reason(tmp_path: Path) -> None:
    """Both staleness rules, each with its own negative fixture and its own wording."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=["DSC:FRESH", "DSC:EXPIRED"])
    _discovery(root, "FRESH", verified_at="2026-08-10")
    _discovery(root, "EXPIRED", expires="2026-05-01", verified_at="2026-04-01")
    # Reachable by SCOPE only, so its inbound citation count is genuinely zero.
    _discovery(root, "ANCIENT", verified_at="2026-01-01", scope=["WS:TARGET"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    keys = [item["key"] for item in _items(bundle)]
    assert "DSC:FRESH" in keys
    assert "DSC:EXPIRED" not in keys
    assert "DSC:ANCIENT" not in keys

    reasons = {row["key"]: row["reason"] for row in bundle["excluded"]}
    assert reasons["DSC:EXPIRED"] == "expired 2026-05-01"
    assert reasons["DSC:ANCIENT"].startswith("uncited and ")
    assert reasons["DSC:ANCIENT"].endswith("d old")


def test_a_cited_old_discovery_survives_the_staleness_rule(tmp_path: Path) -> None:
    """Citation is the freshness signal — an old finding someone still reads is alive.

    This pins the half of the rule that is easy to lose: age alone must not evict.  A
    discovery whose only reader is a HANDOFF counts as cited, which is exactly the case
    `check_references` was fixed for and the one a second implementation would miss.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET", discoveries=[])
    _discovery(root, "OLDBUTCITED", verified_at="2026-01-01", scope=["WS:TARGET"])
    _handoff(root, "TARGET-2026-08-11", discoveries=["DSC:OLDBUTCITED"])

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    assert "DSC:OLDBUTCITED" in [item["key"] for item in _items(bundle)]
    assert not [row for row in bundle["excluded"] if row["key"] == "DSC:OLDBUTCITED"]


def test_only_the_latest_handoff_survives(tmp_path: Path) -> None:
    """Older handoffs are excluded, never merged into a composite nobody wrote."""
    root = tmp_path / "agentos"
    _workstream(root, "TARGET")
    _handoff(root, "TARGET-2026-08-01", mission="The older session.")
    _handoff(root, "TARGET-2026-08-11", mission="The newer session.")

    bundle = _bundle(_compile("--root", str(root), "--workstream", "TARGET"))
    handoffs = _section(bundle, "handoff")["items"]
    assert len(handoffs) == 1
    assert "The newer session." in handoffs[0]["excerpt"]
    dropped = [row for row in bundle["excluded"] if row["key"] == "TARGET-2026-08-01"]
    assert dropped and "older_handoff (latest: TARGET-2026-08-11)" in dropped[0]["reason"]


def test_another_programs_records_cannot_enter_the_bundle(tmp_path: Path) -> None:
    """The boundary is STRUCTURAL, not a relevance threshold.

    The decoy records share the target's vocabulary on purpose: if the walk were replaced
    by a similarity score, this is precisely the fixture that would start leaking.
    """
    root = tmp_path / "agentos"
    tempting = "Ship the thing and prove it shipped — first wave, next command."
    _workstream(root, "TARGET", decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"])
    _decision(root, "KEEP")
    _discovery(root, "KEEP")
    _workstream(root, "DECOY", program=OTHER_PROGRAM, objective=tempting,
                decisions=["DEC:DECOYONLY"], discoveries=["DSC:DECOYONLY"])
    _decision(root, "DECOYONLY", affects=["WS:DECOY"], rationale=tempting)
    _discovery(root, "DECOYONLY", scope=["WS:DECOY"], claim=tempting)

    serialized = json.dumps(_bundle(
        _compile("--root", str(root), "--workstream", "TARGET")
    ))
    assert "DECOY" not in serialized, "an unrelated program's records reached the bundle"
    assert "KEEP" in serialized, "the fixture proves nothing if the target is empty too"


# ---------------------------------------------------------------- I4, both ways


def test_missing_joins_degrade_and_still_compile(simple: Path, tmp_path: Path) -> None:
    """Fail-OPEN: no active_builds.json, no Mastermind checkout — the bundle still exists.

    This is also the CI shape: the sibling repo is never present on a runner, so a
    compiler that needed it would be red on every PR in the fleet.
    """
    _workstream(simple, "TARGET", p0="US_PROPHET_ENTRY_TIMING",
                decisions=["DEC:KEEP"], discoveries=["DSC:KEEP"],
                waves=[{"id": "W0", "title": "First wave", "status": "done", "pr": 5370}])
    result = _compile("--root", str(simple), "--workstream", "TARGET",
                      "--active-builds", str(tmp_path / "no-such-file.json"),
                      env={"MACRO_MASTERMIND_REPO": str(tmp_path / "gone")})
    bundle = _bundle(result)
    assert bundle["degraded"], "two unreadable inputs reported as clean"
    assert any("PR state unknown" in item for item in bundle["degraded"])
    assert any("p0 ids unvalidated" in item for item in bundle["degraded"])
    assert _items(bundle), "a missing join blanked the bundle"
    # The PR join degrades to a stated "unknown", never to a confident wrong state.
    assert "PR #5370 unknown" in _section(bundle, "workstream")["items"][0]["excerpt"]


def test_a_malformed_sibling_is_excluded_while_the_bundle_still_compiles(
    simple: Path
) -> None:
    """Fail-OPEN on a sibling record: named in both `excluded` and `degraded`, never rendered."""
    broken = simple / "decisions" / "DEC-KEEP.md"
    broken.write_text(
        broken.read_text(encoding="utf-8").replace("rationale:", "rationale_typo:", 1),
        encoding="utf-8",
    )
    bundle = _bundle(_compile("--root", str(simple), "--workstream", "TARGET"))
    assert "DEC:KEEP" not in [item["key"] for item in _items(bundle)]
    dropped = [row for row in bundle["excluded"] if row["key"] == "DEC:KEEP"]
    assert dropped and "malformed" in dropped[0]["reason"]
    assert any("malformed" in item and "DEC:KEEP" in item for item in bundle["degraded"])


def test_a_malformed_target_fails_closed(simple: Path) -> None:
    """Fail-CLOSED on schema: compiling around a record that lies about the org is worse
    than refusing, because the refusal is visible and the bundle would not be."""
    target = simple / "workstreams" / "WS-TARGET.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("status: active", "status: humming", 1),
        encoding="utf-8",
    )
    result = _compile("--root", str(simple), "--workstream", "TARGET")
    assert result.returncode == 1
    assert "bad-enum" in result.stdout
    assert "fail-closed" in result.stdout
    for line in result.stdout.splitlines():
        if "::error" in line or "::warning" in line:
            assert line.startswith("::"), f"annotation does not start the line: {line!r}"


def test_an_unknown_target_fails_closed(simple: Path) -> None:
    result = _compile("--root", str(simple), "--workstream", "NO-SUCH-THING")
    assert result.returncode == 1
    assert "unknown workstream WS:NO-SUCH-THING" in result.stdout


def test_the_key_prefix_is_optional(simple: Path) -> None:
    """`KEY`, `WS-KEY` and `WS:KEY` name the same record, so all three must resolve."""
    for spelling in ("TARGET", "WS-TARGET", "WS:TARGET"):
        bundle = _bundle(_compile("--root", str(simple), "--workstream", spelling))
        assert bundle["target"]["workstream"] == "WS:TARGET", spelling


# -------------------------------------------------------------- free-text tasks


def test_a_task_naming_a_key_resolves_without_the_index(simple: Path) -> None:
    """The cheapest path: a cited key is an exact answer, so no retrieval runs at all."""
    bundle = _bundle(_compile(
        "--root", str(simple), "finish the WS-TARGET first wave before the bake",
        env={"MACRO_CONTEXT_INDEX_DIR": "/nonexistent-index-dir"},
    ))
    assert bundle["target"]["resolution"] == "cited-key"
    assert bundle["target"]["workstream"] == "WS:TARGET"
    assert bundle["target"]["task"].startswith("finish the WS-TARGET")
    assert _items(bundle)


def test_free_text_resolves_through_the_existing_index(simple: Path) -> None:
    """Search hits VOTE; they never become content.

    The injected packet contains a decision path and an owned source path — neither is an
    Agent OS workstream record — and the vote still lands on the workstream that cites
    and owns them.  That is the join key doing the work retrieval could not.
    """
    agentos = _load_cli()
    store = agentos.load_store(simple, agentos._load_programs())
    seen: list[str] = []

    def fake_search(query: str) -> dict[str, Any]:
        seen.append(query)
        return {
            "schema": "context_packet.v1",
            "index_stale": False,
            "results": [
                {"path": "docs/UNRELATED.md"},
                {"path": str((simple / "decisions" / "DEC-KEEP.md"))},
                {"path": "agentos/decisions/DEC-KEEP.md"},
            ],
        }

    bundle = agentos.compile_bundle(
        store, task="why did we keep it", now=agentos._parse_moment(FROZEN),
        search_fn=fake_search,
    )
    assert seen == ["why did we keep it"], "the seam was not used"
    assert bundle["target"]["resolution"] == "search"
    assert bundle["target"]["workstream"] == "WS:TARGET"
    assert "docs/UNRELATED.md" not in json.dumps(bundle), (
        "a search hit became bundle content instead of a vote"
    )


def test_two_close_candidates_refuse_to_guess(tmp_path: Path) -> None:
    """An ambiguous resolution is a FEATURE.

    Picking one of two plausible workstreams hands the next session a confident bundle
    about the wrong work — strictly worse than no bundle, because it looks right.
    """
    root = tmp_path / "agentos"
    _workstream(root, "TARGET")
    _workstream(root, "RIVAL")
    agentos = _load_cli()
    store = agentos.load_store(root, agentos._load_programs())

    def fake_search(query: str) -> dict[str, Any]:
        return {"results": [
            {"path": "agentos/workstreams/WS-TARGET.md"},
            {"path": "agentos/workstreams/WS-RIVAL.md"},
        ]}

    bundle = agentos.compile_bundle(
        store, task="the ambiguous one", now=agentos._parse_moment(FROZEN),
        search_fn=fake_search,
    )
    assert bundle["target"]["resolution"] == "ambiguous"
    assert bundle["target"]["workstream"] is None
    assert bundle["sections"] == [], "an unresolved bundle must carry no content"
    candidates = {row["key"]: row["score"] for row in bundle["target"]["candidates"]}
    assert candidates == {"WS:TARGET": 20, "WS:RIVAL": 19}
    assert "pick one with --workstream" in bundle["no_answer_reason"]


def test_no_index_is_unresolved_not_a_crash(simple: Path, tmp_path: Path) -> None:
    """Fail-OPEN on retrieval: an unbuilt index degrades to 'name it yourself'."""
    empty = tmp_path / "empty-index"
    empty.mkdir()
    bundle = _bundle(_compile(
        "--root", str(simple), "reduce late entry in the prophet",
        env={"MACRO_CONTEXT_INDEX_DIR": str(empty)},
    ))
    assert bundle["target"]["resolution"] == "unresolved"
    assert bundle["sections"] == []
    assert any("context index unavailable" in item for item in bundle["degraded"])
    assert "pass --workstream" in bundle["no_answer_reason"]
    assert [row["key"] for row in bundle["target"]["candidates"]] == ["WS:TARGET"]


# --------------------------------------------------------- determinism, no writes


def _tree_digest(root: Path) -> list[tuple[str, str]]:
    return sorted(
        (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in root.rglob("*") if path.is_file()
    )


def test_the_same_inputs_produce_byte_identical_output(overfull: Path) -> None:
    """One clock, sorted iteration, integer weights — nothing may wobble run to run."""
    first = _compile("--root", str(overfull), "--workstream", "TARGET", "--budget", "900")
    second = _compile("--root", str(overfull), "--workstream", "TARGET", "--budget", "900")
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    text_one = _compile("--root", str(overfull), "--workstream", "TARGET",
                        "--budget", "900", "--text")
    text_two = _compile("--root", str(overfull), "--workstream", "TARGET",
                        "--budget", "900", "--text")
    assert text_one.stdout == text_two.stdout


def test_compiling_context_writes_nothing(simple: Path) -> None:
    """Read-only is a GUARANTEE, not an intention (I1): the store is a source, not a log."""
    before = _tree_digest(simple)
    assert _compile("--root", str(simple), "--workstream", "TARGET").returncode == 0
    assert _compile("--root", str(simple), "--workstream", "TARGET", "--text").returncode == 0
    assert _tree_digest(simple) == before, "compile-context modified the record store"


# ------------------------------------------------------------------ the text form


def test_text_output_states_its_authority_framings(tmp_path: Path) -> None:
    """The framings are the presentation contract: a reader must be able to tell law
    from evidence without opening the architecture doc."""
    root = tmp_path / "agentos"
    padding = "Long enough to force the packer to drop something. " * 14
    _workstream(root, "TARGET", decisions=["DEC:OLD", "DEC:NEW"] +
                [f"DEC:BULK{i}" for i in range(6)])
    _decision(root, "OLD", superseded_by="DEC:NEW")
    _decision(root, "NEW", supersedes=["DEC:OLD"])
    for index in range(6):
        _decision(root, f"BULK{index}", rationale=padding)

    result = _compile("--root", str(root), "--workstream", "TARGET",
                      "--budget", "600", "--text")
    assert result.returncode == 0, result.stdout + result.stderr
    text = result.stdout
    for framing in (
        "HIGHER LAW — outranks every Agent OS record below",
        "WORKSTREAM STATE (authoritative for state, not for permission)",
        "DECISIONS (institutional reasoning — do not override higher law)",
        "DISCOVERIES (evidence, not policy)",
        "LATEST HANDOFF (transfer state, not strategy)",
        "ARTIFACTS (pointers — read the primary source)",
    ):
        assert framing in text, f"missing authority framing: {framing}"

    assert "WS:TARGET · " in text and "WS-TARGET.md" in text, "no item citation rendered"
    assert "EXCLUDED (1)" in text and "superseded_by DEC:NEW" in text
    assert "OMITTED — BUDGET (" in text
    assert "tokens (rank " in text, "an omitted item was announced without its cost"
    assert "DEGRADED (" in text


def test_json_is_the_default_and_text_is_opt_in(simple: Path) -> None:
    """Mirrors context_index_query.py: machines get the default, humans ask for prose."""
    default = _compile("--root", str(simple), "--workstream", "TARGET")
    explicit = _compile("--root", str(simple), "--workstream", "TARGET", "--json")
    assert json.loads(default.stdout)["schema"] == "context_bundle.v1"
    assert default.stdout == explicit.stdout, "--json is an alias, not a second format"
    assert not _compile("--root", str(simple), "--workstream", "TARGET",
                        "--text").stdout.lstrip().startswith("{")


# --------------------------------------------------------------------- I1 / usage


def test_neither_or_both_targets_is_a_usage_error(simple: Path) -> None:
    assert _compile("--root", str(simple)).returncode == 2
    assert _compile("--root", str(simple), "a task", "--workstream", "TARGET").returncode == 2


def test_compile_context_holds_no_scheduling_vocabulary() -> None:
    """I1, checkable by a reviewer: nothing here can start, stop, or claim work."""
    source = CLI.read_text(encoding="utf-8")
    body = source.split("Phase 3: context compilation", 1)[1]
    for forbidden in ("def dispatch", "def assign", "def schedule", "def lease",
                      "def acquire", "subprocess.Popen", "os.system", "urllib",
                      "requests.", "socket."):
        assert forbidden not in body, f"{forbidden} has no business in a knowledge plane"


def test_the_store_this_suite_compiles_is_the_committed_one(tmp_path: Path) -> None:
    """The real store must stay valid, or every bundle above is compiled from a lie.

    `tmp_path`, never a fixed scratch directory: parallel sessions share one TMPDIR on
    this host, and a shared path turns two green suites into one flaky pair.
    """
    scratch = tmp_path / "agentos"
    shutil.copytree(STORE, scratch)
    assert _run("validate", "--root", str(scratch)).returncode == 0
