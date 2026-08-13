"""Agent OS record contract — scripts/agentos.py validate.

Two properties are guarded here, and the second is the one that matters:

1.  The committed `agentos/` store is valid.
2.  The validator can FAIL.  A schema checker that only ever prints "0 errors" is
    indistinguishable from one that never ran, so every hard rule gets a mutation
    that must make it fire.  Each mutation corrupts a COPY in tmp_path; the real
    store is never written to.

Also pinned: the fail-closed / fail-open split (architecture invariant I4) and the
house annotation law — GitHub annotations must START the line, emitted by a bare
print, never through a logger.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "agentos"
CLI = REPO / "scripts" / "agentos.py"

# Agent worktrees here are frequently CONE-MODE SPARSE checkouts, and a directory
# outside the cone is simply absent — which would otherwise read as "the store is
# broken" instead of "the store is not checked out".  CI checks out the full tree,
# so this never skips there; the CI step additionally runs `agentos.py validate`
# directly, which is not skippable, so an absent store cannot pass silently.
# Heal a sparse worktree with:  git sparse-checkout add agentos
pytestmark = pytest.mark.skipif(
    not STORE.exists(),
    reason="agentos/ outside this sparse checkout — run: git sparse-checkout add agentos",
)


def _validate(root: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environ = dict(os.environ)
    environ.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), "validate", "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=environ,
    )


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """An isolated copy of the committed store."""
    work = tmp_path / "agentos"
    shutil.copytree(STORE, work)
    return work


def _patch(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"mutation anchor missing in {path.name}: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --------------------------------------------------------------- green path


def test_committed_store_is_valid() -> None:
    result = _validate(STORE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 error(s)" in result.stdout


def test_every_record_type_is_present() -> None:
    """A store that silently lost a directory would still validate green."""
    assert list((STORE / "workstreams").glob("WS-*.md"))
    assert list((STORE / "decisions").glob("DEC-*.md"))
    assert list((STORE / "discoveries").glob("DSC-*.md"))


# --------------------------------------------------- mutation proofs (hard)


# (rule, relative path, anchor, replacement)
MUTATIONS: list[tuple[str, str, str, str]] = [
    ("bad-enum", "workstreams/WS-AGENT-OS.md", "status: active", "status: humming"),
    (
        "required-field",
        "workstreams/WS-PROPHET-US-ENTRY-TIMING.md",
        "next_action: Verify the 22:30Z bake (W1).",
        "",
    ),
    (
        "unknown-program",
        "workstreams/WS-GMI-THEME-GRAPH.md",
        "program: gmi-theme-graph",
        "program: not-a-real-program",
    ),
    (
        "dangling-ref",
        "workstreams/WS-AGENT-OS.md",
        "  - DEC:AGENTOS-NO-TASK-STORE",
        "  - DEC:DOES-NOT-EXIST",
    ),
    (
        # A bare key is not a citation.  Before the citation shape was enforced,
        # `depends_on: [NONEXISTENT]` validated with 0 errors and 0 warnings — the edge
        # was silently DROPPED from the graph that cycles and START NEXT walk.
        "bad-citation",
        "workstreams/WS-AGENT-OS.md",
        "  - DEC:AGENTOS-NO-TASK-STORE",
        "  - AGENTOS-NO-TASK-STORE",
    ),
    (
        "bad-date",
        "decisions/DEC-AGENTOS-NO-TASK-STORE.md",
        "decided_at: 2026-08-12",
        "decided_at: last Tuesday",
    ),
    (
        "filename-mismatch",
        "workstreams/WS-AGENT-OS.md",
        "key: AGENT-OS",
        "key: AGENT-OS-RENAMED",
    ),
    (
        "no-alternatives",
        "decisions/DEC-AGENTOS-NO-TASK-STORE.md",
        "alternatives:",
        "alternatives: []\nunused_alternatives:",
    ),
    (
        "dangling-wave-dep",
        "workstreams/WS-PROPHET-US-ENTRY-TIMING.md",
        "    depends_on: [W1]",
        "    depends_on: [W99]",
    ),
    (
        "wave-cycle",
        "workstreams/WS-AGENT-OS.md",
        "    depends_on: [W1, W2]",
        "    depends_on: [W1, W2]\n"
        "  - id: WX\n    title: cycle a\n    status: todo\n    depends_on: [WY]\n"
        "  - id: WY\n    title: cycle b\n    status: todo\n    depends_on: [WX]",
    ),
    (
        "unparseable",
        "discoveries/DSC-GOVERNANCE-JSONL-NOT-TRACKED.md",
        "kind: architecture",
        "kind: [unclosed",
    ),
]


@pytest.mark.parametrize("rule,rel,anchor,replacement", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_hard_rule_fires(store: Path, rule: str, rel: str, anchor: str, replacement: str) -> None:
    """Each hard rule must reject a record that violates it."""
    _patch(store / rel, anchor, replacement)
    result = _validate(store)
    assert result.returncode == 1, f"{rule} did not fail the run:\n{result.stdout}"
    assert rule in result.stdout, f"{rule} not named in output:\n{result.stdout}"


def test_duplicate_key_is_rejected(store: Path) -> None:
    """Only reachable alongside a filename mismatch — kept as defence in depth."""
    source = (store / "decisions" / "DEC-AGENTOS-FILE-PER-RECORD.md").read_text(encoding="utf-8")
    (store / "decisions" / "DEC-COPYCAT.md").write_text(source, encoding="utf-8")
    result = _validate(store)
    assert result.returncode == 1
    assert "duplicate-key" in result.stdout


def test_unreciprocated_supersession_is_rejected(store: Path) -> None:
    """A one-sided supersession silently forks provenance."""
    _patch(
        store / "decisions" / "DEC-AGENTOS-FILE-PER-RECORD.md",
        "decided_at: 2026-08-12",
        "decided_at: 2026-08-12\nsupersedes: [DEC:AGENTOS-NO-TASK-STORE]",
    )
    result = _validate(store)
    assert result.returncode == 1
    assert "unreciprocated-supersession" in result.stdout


# ------------------------------------------------- invariant I4, both ways


def test_warning_never_blocks(store: Path) -> None:
    """Hygiene findings warn and exit 0 — fail-open on join."""
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "claim:\n  by: claude/ghost\n  at: 2025-01-01\n  expires: 2025-01-02\nlandmines:",
    )
    result = _validate(store)
    assert result.returncode == 0, result.stdout
    assert "stale-claim" in result.stdout


# ------------------------------------- the hard/soft line, and why it moved
#
# `validate` runs UNSCOPED on every PR in the fleet, over the whole store, not over the
# diff.  So a hard rule that keys on the STATE of the work is a fleet-wide fail-closed
# gate on a knowledge record — and it is reachable without anyone writing an invalid
# record.  These tests pin the demotion; each one EXITED 1 before it.


STATE_RULES_ARE_WARNINGS: list[tuple[str, str, str, str]] = [
    (
        "active-but-complete",
        "workstreams/WS-MACRO-CONTEXT-INDEX.md",
        "    status: in_progress\n"
        "    next_action: Work the red gates in research/context_index/BENCHMARK_RESULTS.md.\n"
        '  - id: W2\n'
        '    title: "Add agentos/** as a corpus (Agent OS Phase 3 dependency)"\n'
        "    status: todo",
        "    status: done\n"
        '  - id: W2\n'
        '    title: "Add agentos/** as a corpus (Agent OS Phase 3 dependency)"\n'
        "    status: dropped",
    ),
    (
        "blocked-without-cause",
        "workstreams/WS-CN-LIMIT-ALPHA.md",
        "blocked_by:",
        "blocked_by: []\nunused_blocked_by:",
    ),
    (
        "cause-without-blocked",
        "workstreams/WS-CN-LIMIT-ALPHA.md",
        "status: blocked",
        "status: active",
    ),
]


@pytest.mark.parametrize(
    "rule,rel,anchor,replacement", STATE_RULES_ARE_WARNINGS,
    ids=[m[0] for m in STATE_RULES_ARE_WARNINGS],
)
def test_state_rules_warn_and_do_not_block(
    store: Path, rule: str, rel: str, anchor: str, replacement: str
) -> None:
    """Work-state disagreement is reported, never fatal."""
    _patch(store / rel, anchor, replacement)
    result = _validate(store)
    assert result.returncode == 0, (
        f"{rule} still hard-fails; a fleet-wide unscoped check must not gate on work "
        f"state:\n{result.stdout}"
    )
    assert rule in result.stdout, f"{rule} was demoted into silence:\n{result.stdout}"


def test_clean_merge_of_two_valid_states_validates(store: Path, tmp_path: Path) -> None:
    """THE reproduction: two green PRs, a clean git merge, and a red main.

    Branch A marks one wave done; branch B marks another dropped.  Each validates 0.
    The textual merge is clean — different lines.  The merged tree is what the fleet
    then runs `validate` over on EVERY subsequent PR, so if the merged state hard-failed,
    two individually-correct sessions would red main with no bad record anywhere.
    """
    repo = tmp_path / "merge-probe"
    shutil.copytree(store, repo / "agentos")

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    git("add", "-A")
    git("commit", "-qm", "base")

    record = repo / "agentos" / "workstreams" / "WS-MACRO-CONTEXT-INDEX.md"
    git("checkout", "-q", "-b", "branch-a")
    _patch(record, "    status: in_progress", "    status: done")
    assert _validate(repo / "agentos").returncode == 0, "branch A is a valid state"
    git("commit", "-aqm", "W1 done")

    git("checkout", "-q", "main")
    git("checkout", "-q", "-b", "branch-b")
    _patch(record, "    status: todo", "    status: dropped")
    assert _validate(repo / "agentos").returncode == 0, "branch B is a valid state"
    git("commit", "-aqm", "W2 dropped")

    git("checkout", "-q", "branch-a")
    merge = git("merge", "--no-edit", "branch-b")
    assert merge.returncode == 0, f"the merge itself must be clean:\n{merge.stdout}{merge.stderr}"

    result = _validate(repo / "agentos")
    assert result.returncode == 0, (
        "a clean merge of two individually-valid records must not red the fleet:\n"
        + result.stdout
    )


def test_bare_key_dependency_is_rejected_not_dropped(store: Path) -> None:
    """`depends_on: [FOO]` must not validate silently — the edge would vanish."""
    _patch(
        store / "workstreams" / "WS-AGENT-OS.md",
        "class: adjudication",
        "class: adjudication\ndepends_on: [TOTALLY-NONEXISTENT]",
    )
    result = _validate(store)
    assert result.returncode == 1, (
        "a bare depends_on key used to validate with 0 errors AND 0 warnings, which "
        f"silently removed an edge from the dependency graph:\n{result.stdout}"
    )
    assert "bad-citation" in result.stdout


def test_prefixed_unknown_dependency_is_still_dangling(store: Path) -> None:
    _patch(
        store / "workstreams" / "WS-AGENT-OS.md",
        "class: adjudication",
        "class: adjudication\ndepends_on: [WS:TOTALLY-NONEXISTENT]",
    )
    result = _validate(store)
    assert result.returncode == 1
    assert "dangling-ref" in result.stdout


# ------------------------------------------------- discovery admission gates


def test_unfalsifiable_discovery_is_rejected(store: Path) -> None:
    """`falsifier: no` passed a non-empty check and failed the gate it encodes."""
    _patch(
        store / "discoveries" / "DSC-GOVERNANCE-JSONL-NOT-TRACKED.md",
        "falsifier: >",
        "falsifier: it just is not\nunused_falsifier: >",
    )
    result = _validate(store)
    assert result.returncode == 1, result.stdout
    assert "unfalsifiable-claim" in result.stdout


def test_unprovable_verification_is_rejected(store: Path) -> None:
    _patch(
        store / "discoveries" / "DSC-GOVERNANCE-JSONL-NOT-TRACKED.md",
        'verified_by: "git ls-files',
        'verified_by: vibes\nunused_verified_by: "git ls-files',
    )
    result = _validate(store)
    assert result.returncode == 1, result.stdout
    assert "unprovable-verification" in result.stdout


# --------------------------------------------------------------- handoffs


HANDOFF = """---
workstream: WS:AGENT-OS
session: claude/agentos-phase2
model: opus
mission: Build the status generator.
state_before: Phase 0 landed; status and brief were stubs.
changed:
  - path: scripts/agentos.py
    what: added the status and brief subcommands
verified:
  - claim: validate still exits 0 on the real store
    command: python3 scripts/agentos.py validate
    result: "0 error(s)"
unverified: []
unresolved:
  - Whether C3 is ruled the way this session recommends.
next_actions:
  - Rule on C3.
do_not_redo:
  - Re-deriving PR state from gh; active_builds.v1 is the only source.
danger_areas:
  - validate runs unscoped on every PR in the fleet.
ended_because: complete
---

## What happened
The generator was built and the record set was repaired.
"""


def _write_handoff(store: Path, body: str) -> Path:
    target = store / "handoffs" / "AGENT-OS-2026-08-12.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def test_valid_handoff_is_counted(store: Path) -> None:
    """Handoffs used not to be validated OR counted — garbage read as an empty store.

    Asserts baseline+1, not an absolute count: the committed store legitimately
    accrues real handoffs (Phase 1 adoption), and pinning "1 handoffs" made the
    first real handoff ever written red this suite fleet-wide.
    """
    baseline = len(list((store / "handoffs").glob("*.md")))
    _write_handoff(store, HANDOFF)
    result = _validate(store)
    assert result.returncode == 0, result.stdout
    assert f"{baseline + 1} handoffs" in result.stdout


def test_garbage_handoff_is_rejected(store: Path) -> None:
    _write_handoff(store, "---\nthis: is not a handoff\nmodel: telepathy\n---\n\nSee above.\n")
    result = _validate(store)
    assert result.returncode == 1, (
        "a garbage handoff used to validate clean and was not even counted:\n"
        + result.stdout
    )


def test_handoff_verified_claim_needs_its_command(store: Path) -> None:
    _write_handoff(store, HANDOFF.replace(
        "    command: python3 scripts/agentos.py validate\n", ""))
    result = _validate(store)
    assert result.returncode == 1
    assert "unbacked-verification" in result.stdout


def test_handoff_unverified_may_be_empty_but_not_absent(store: Path) -> None:
    """An empty list is a meaningful answer; an absent key is not."""
    _write_handoff(store, HANDOFF.replace("unverified: []\n", ""))
    result = _validate(store)
    assert result.returncode == 1
    assert "'unverified'" in result.stdout


def test_handoff_body_may_not_point_at_a_conversation(store: Path) -> None:
    _write_handoff(store, HANDOFF.replace(
        "The generator was built and the record set was repaired.",
        "See above for what changed."))
    result = _validate(store)
    assert result.returncode == 1
    assert "context-free-handoff" in result.stdout


ORPHAN_DISCOVERY = """---
key: ORPHAN-PROBE
claim: An orphaned discovery exists solely to exercise the GC candidate rule.
falsifier: "grep -c ORPHAN-PROBE agentos/discoveries/ — a zero result disproves it."
so_what: A future session must not delete a discovery that a handoff still cites.
kind: architecture
verified_at: 2020-01-01
verified_by: "scripts/agentos.py:1 (fixture record, never shipped)"
scope: [macro]
confidence: verified
---

## Detail
Fixture only.
"""


def test_handoff_citation_counts_against_discovery_gc(store: Path) -> None:
    """A discovery cited ONLY by a handoff is cited — it used to read as an orphan.

    `check_references` counted citations from workstreams and decisions only, so a
    finding whose sole reader was a session handoff aged into a 90-day GC candidate.
    """
    (store / "discoveries" / "DSC-ORPHAN-PROBE.md").write_text(
        ORPHAN_DISCOVERY, encoding="utf-8")
    without = _validate(store)
    assert without.returncode == 0, without.stdout
    assert "uncited-discovery" in without.stdout, without.stdout

    _write_handoff(store, HANDOFF.replace(
        "unverified: []\n",
        "unverified: []\ndiscoveries: [DSC:ORPHAN-PROBE]\n"))
    with_citation = _validate(store)
    assert with_citation.returncode == 0, with_citation.stdout
    assert "uncited-discovery" not in with_citation.stdout


def test_phantom_artifact_warns(store: Path) -> None:
    """A record citing a file that was never there sends the next session hunting."""
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "artifacts:\n  - research/NO_SUCH_DOC.md\nlandmines:",
    )
    result = _validate(store)
    assert result.returncode == 0, "phantom paths are hygiene, not schema — must not block"
    assert "phantom-artifact" in result.stdout


def test_phantom_owns_path_warns(store: Path) -> None:
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "  - engine/prophet_*.py",
        "  - engine/ghost_dir/*.py",
    )
    result = _validate(store)
    assert result.returncode == 0
    assert "phantom-owns-path" in result.stdout


def test_cross_repo_path_is_unchecked_when_that_checkout_is_absent(
    store: Path, tmp_path: Path
) -> None:
    """An absent sibling checkout is unknowable, not wrong (I4) — no warning."""
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "artifacts:\n  - terminal:app/routes/portfolio.tsx\nlandmines:",
    )
    result = _validate(store, MACRO_TERMINAL_REPO=str(tmp_path / "no-such-checkout"))
    assert result.returncode == 0
    assert "phantom-artifact" not in result.stdout


def test_cross_repo_path_is_resolved_against_its_own_repo(store: Path, tmp_path: Path) -> None:
    """The silent FALSE PASS is the worse half of a Macro-pinned root.

    `terminal:scripts/agentos.py` exists in Macro and does not exist in Terminal.  A
    root pinned to the Macro checkout reports it as present — a clean bill of health for
    a path that is not there.
    """
    terminal = tmp_path / "terminal-checkout"
    terminal.mkdir()
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "artifacts:\n  - terminal:scripts/agentos.py\nlandmines:",
    )
    assert (REPO / "scripts" / "agentos.py").exists(), "the path must exist in MACRO"
    result = _validate(store, MACRO_TERMINAL_REPO=str(terminal))
    assert result.returncode == 0, "still a warning, never a hard failure"
    assert "phantom-artifact" in result.stdout, (
        "a Terminal path that exists only in Macro must not read as present:\n"
        + result.stdout
    )


def test_absent_store_exits_zero(tmp_path: Path) -> None:
    """A repo that has not adopted Agent OS is not a broken repo."""
    result = _validate(tmp_path / "nonexistent")
    assert result.returncode == 0
    assert "no agentos/ store" in result.stdout


def test_quiet_suppresses_warnings_but_not_errors(store: Path) -> None:
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "claim:\n  by: claude/ghost\n  at: 2025-01-01\n  expires: 2025-01-02\nlandmines:",
    )
    result = subprocess.run(
        [sys.executable, str(CLI), "validate", "--root", str(store), "--quiet"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0
    assert "stale-claim" not in result.stdout


# ------------------------------------------------------ house annotation law


def test_annotations_start_the_line(store: Path) -> None:
    """`::error`/`::warning` must START the line or GitHub silently drops them.

    This shipped dead five times in this repo before #3587 swept 69 sites, so the
    assertion is on line position, not on wording.
    """
    _patch(store / "workstreams" / "WS-AGENT-OS.md", "status: active", "status: humming")
    result = _validate(store)
    annotations = [ln for ln in result.stdout.splitlines() if "::error" in ln or "::warning" in ln]
    assert annotations, "no annotation emitted for a hard failure"
    for line in annotations:
        assert line.startswith("::"), f"annotation does not start the line: {line!r}"


def test_no_subcommand_still_announces_itself_as_a_stub() -> None:
    """Every advertised subcommand must do work or say it cannot — never exit silently.

    This test used to pin `compile-context` as a visible STUB.  Phase 3 landed it, so it
    now pins the opposite: the subcommand must produce a real bundle, and no stub
    language may survive anywhere in the CLI.  The shape of the check is deliberately
    unchanged — a subcommand that silently returns 0 having done nothing is the failure
    both versions exist to refuse.
    """
    source = CLI.read_text(encoding="utf-8")
    assert "not implemented until" not in source, "a stub announcement outlived its stub"

    usage_error = subprocess.run(
        [sys.executable, str(CLI), "compile-context"], capture_output=True, text=True, cwd=REPO
    )
    assert usage_error.returncode == 2, (
        "neither a task nor --workstream is a USAGE error, not a silent empty bundle"
    )
    assert "exactly one" in usage_error.stderr

    real = subprocess.run(
        [sys.executable, str(CLI), "compile-context", "--workstream", "AGENT-OS",
         "--now", "2026-08-12T14:00:00Z"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert real.returncode == 0, real.stdout + real.stderr
    bundle = json.loads(real.stdout)
    assert bundle["schema"] == "context_bundle.v1"
    assert any(section["items"] for section in bundle["sections"]), "an empty bundle is a stub"
