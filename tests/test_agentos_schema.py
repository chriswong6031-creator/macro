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

import datetime as _dt
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
SEED_KEYS = (
    sorted(path.stem[3:] for path in (STORE / "workstreams").glob("WS-*.md"))
    if STORE.exists() else []
)

pytestmark = [
    pytest.mark.skipif(
        not STORE.exists(),
        reason="agentos/ outside this sparse checkout — run: git sparse-checkout add agentos",
    ),
    pytest.mark.skipif(
        not SEED_KEYS,
        reason="agentos/workstreams/ holds no records in this checkout — "
               "run: git sparse-checkout add agentos",
    ),
]


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
        "bad-wave",
        "workstreams/WS-AGENT-OS.md",
        "  - id: W4",
        "  - id: 4",
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
        "    depends_on: [W1, W2, W2B]",
        "    depends_on: [W1, W2, W2B]\n"
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


# ------------------------------------------------------------ supersession
#
# `superseded_by` is the ONE field in the schema that deletes a live record from every
# compiled context bundle, and it was entirely unvalidated: any truthy string evicted a
# current decision forever while `validate` printed "0 error(s)", and `false`/`0`/`""` —
# the same intent, typed differently — did not evict at all.  A field that removes
# institutional reasoning from the document a cold session reads has to be the most
# checked field here, not the least.


@pytest.mark.parametrize("junk", ["no", "DEC-NEW", "false", "[DEC:A, DEC:B]", "''"])
def test_a_junk_superseded_by_is_rejected(store: Path, junk: str) -> None:
    """Every shape that is not exactly one `DEC:KEY` citation is refused.

    `no` is the expensive one: a plausible thing to type, it used to EVICT the record it
    was written on.  `DEC-NEW` is the bare-key shape `_citations` exists to refuse, and
    two replacements is not a supersession at all — supersession has one successor.
    """
    _patch(
        store / "decisions" / "DEC-AGENTOS-FILE-PER-RECORD.md",
        "decided_at: 2026-08-12",
        f"decided_at: 2026-08-12\nsuperseded_by: {junk}",
    )
    result = _validate(store)
    assert result.returncode == 1, f"superseded_by: {junk} validated clean:\n{result.stdout}"
    assert "bad-supersession" in result.stdout


def test_a_superseded_by_naming_nothing_is_rejected(store: Path) -> None:
    """A record retired in favour of one that does not exist loses its reasoning.

    Well-shaped and still wrong: the citation resolves against nothing, so the bundle would
    drop the old record while pointing at a replacement nobody can open.
    """
    _patch(
        store / "decisions" / "DEC-AGENTOS-FILE-PER-RECORD.md",
        "decided_at: 2026-08-12",
        "decided_at: 2026-08-12\nsuperseded_by: DEC:NO-SUCH-DECISION",
    )
    result = _validate(store)
    assert result.returncode == 1
    assert "dangling-ref" in result.stdout
    assert "superseded_by" in result.stdout


def test_a_one_sided_supersession_warns_but_never_blocks(store: Path) -> None:
    """DELIBERATELY the softer half of the reciprocity rule.

    `superseded_by` on the OLD record is how decision.schema.yml documents supersession —
    "set on the OLD record" — so the new record failing to list `supersedes` is untidy
    provenance, not a broken store.  Hard in this direction would make the schema's own
    worked example fail validation.
    """
    _patch(
        store / "decisions" / "DEC-AGENTOS-FILE-PER-RECORD.md",
        "decided_at: 2026-08-12",
        "decided_at: 2026-08-12\nsuperseded_by: DEC:AGENTOS-NO-TASK-STORE",
    )
    result = _validate(store)
    assert result.returncode == 0, result.stdout
    assert "one-sided-supersession" in result.stdout
    assert "::warning" in result.stdout


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
    # These two anchor on WS-CN-LIMIT-ALPHA's LIVE top-level state and must CREATE
    # the inconsistent state from it (2026-08-14: the record moved blocked->active
    # with no blocked_by, which silently broke the previous anchors — a mutation
    # that only works while a real program stays blocked is a fixture landmine).
    # If the record's top-level status changes again, update the anchors so the
    # replacement still manufactures the rule's inconsistency by itself.
    (
        "blocked-without-cause",
        "workstreams/WS-CN-LIMIT-ALPHA.md",
        "status: active",
        "status: blocked",
    ),
    (
        "cause-without-blocked",
        "workstreams/WS-CN-LIMIT-ALPHA.md",
        "status: active",
        "status: active\nblocked_by:\n  - schema-probe cause (test-injected)",
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


def test_bare_supersedes_key_is_rejected_not_dropped(store: Path) -> None:
    """`supersedes: [FOO]` must not validate silently — `_refs` drops the bare key,
    which used to skip the reciprocity check entirely (the superseded_by defect class,
    one field over)."""
    _patch(
        store / "decisions" / "DEC-AGENTOS-READINESS-FEEDS-THE-AGENDA.md",
        "supersedes: [DEC:AGENTOS-START-NEXT-VS-AGENDA]",
        "supersedes: [AGENTOS-START-NEXT-VS-AGENDA]",
    )
    result = _validate(store)
    assert result.returncode == 1, (
        "a bare supersedes key used to validate clean while silently skipping the "
        f"reciprocity check:\n{result.stdout}"
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

    The expensive part of this contract is breadth, not process isolation.  One real CLI
    invocation proves argparse/transport wiring; the all-workstream sweep then reuses one
    parsed Store in-process.  Spawning one Python interpreter per workstream reparsed the
    entire Agent OS graph ~40 times and made this single contract dominate merge-gate wall
    time without proving a different behavior.
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

    # One true process boundary pins the public CLI. Argparse behavior does not vary by
    # workstream key, so repeating the process boundary for every record adds cost, not
    # coverage.
    representative = SEED_KEYS[0]
    real = subprocess.run(
        [sys.executable, str(CLI), "compile-context", "--workstream", representative,
         "--now", "2026-08-12T14:00:00Z"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert real.returncode == 0, real.stdout + real.stderr
    real_bundle = json.loads(real.stdout)
    assert real_bundle["schema"] == "context_bundle.v1"
    assert any(section["items"] for section in real_bundle["sections"]), (
        f"WS:{representative} compiled to an empty bundle — a stub in everything but name"
    )

    # Breadth is still exhaustive. Load/validate the committed graph once, then compile
    # every seeded workstream through the same production compiler. Git timestamps and
    # repo SHA have dedicated contracts elsewhere; neutralising those read-only joins here
    # prevents this breadth proof from becoming a history benchmark.
    import importlib.util

    spec = importlib.util.spec_from_file_location("agentos_schema_breadth", CLI)
    assert spec is not None and spec.loader is not None
    agentos = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agentos)
    parsed_store = agentos.load_store(STORE, agentos._load_programs())
    hard = [problem for problem in parsed_store.problems if problem.hard]
    assert not hard, "the committed store must be valid before breadth compilation"
    now = agentos._parse_moment("2026-08-12T14:00:00Z")
    assert now is not None

    original_git_dates = agentos.git_dates
    original_repo_sha = agentos._repo_sha
    agentos.git_dates = lambda _path: (None, None)
    agentos._repo_sha = lambda: "test-sha"
    try:
        for key in SEED_KEYS:
            bundle = agentos.compile_bundle(
                parsed_store,
                workstream=key,
                now=now,
                builds=None,
                degraded=agentos.Degraded(),
            )
            assert bundle["schema"] == "context_bundle.v1"
            assert bundle["target"]["workstream"] == f"WS:{key}"
            assert any(section["items"] for section in bundle["sections"]), (
                f"WS:{key} compiled to an empty bundle — a stub in everything but name"
            )
    finally:
        agentos.git_dates = original_git_dates
        agentos._repo_sha = original_repo_sha


# ------------------------------------------- Project Recovery R8-B1 typed wait


def _wait_workstream() -> dict[str, object]:
    return {
        "key": "TEST-WAIT",
        "title": "Test wait",
        "objective": "Exercise the typed intentional-wait contract.",
        "status": "active",
        "program": "test-program",
        "repos": ["macro"],
        "owner": "fable",
        "class": "research",
        "blast_radius": "reversible",
        "ambiguity": "specified",
        "waves": [{"id": "w1", "title": "Accrue", "status": "todo"}],
        "next_action": "Accrue prospectively.",
    }


def _wait_hard(rec: dict[str, object]):
    from scripts import agentos

    return [
        problem
        for problem in agentos.check_workstream(
            rec,
            Path("agentos/workstreams/WS-TEST-WAIT.md"),
            {"test-program"},
        )
        if problem.hard
    ]


def test_workstream_wait_accepts_closed_valid_shape() -> None:
    rec = _wait_workstream()
    rec["wait"] = {
        "kind": "natural_evidence",
        "review_after": "2026-09-25",
        "condition": "Review whether the preregistered prospective sample matured.",
    }
    assert _wait_hard(rec) == []


@pytest.mark.parametrize(
    "wait,message_fragment",
    [
        (
            {
                "kind": "until_ready",
                "review_after": "2026-09-25",
                "condition": "Not a registered kind.",
            },
            "kind",
        ),
        ({"kind": "natural_evidence"}, "review_after"),
        (
            {
                "kind": "external_action",
                "review_after": "next week",
                "condition": "Operator action remains outstanding.",
            },
            "review_after",
        ),
        (
            {
                "kind": "external_action",
                "review_after": "2026-09-25",
                "condition": "Operator action remains outstanding.",
                "auto_extend": True,
            },
            "auto_extend",
        ),
    ],
)
def test_workstream_wait_rejects_malformed_closed_contract(
    wait: dict[str, object], message_fragment: str
) -> None:
    rec = _wait_workstream()
    rec["wait"] = wait
    hard = _wait_hard(rec)
    assert any(problem.rule == "bad-wait" for problem in hard)
    assert any(message_fragment in problem.message for problem in hard)


def test_wave_wait_uses_same_contract_and_rejects_blank_condition() -> None:
    rec = _wait_workstream()
    wave = rec["waves"][0]
    assert isinstance(wave, dict)
    wave["wait"] = {
        "kind": "calendar_window",
        "review_after": "2026-09-01",
        "condition": "  ",
    }
    hard = _wait_hard(rec)
    assert any(problem.rule == "bad-wait" for problem in hard)
    assert any("condition" in problem.message for problem in hard)


def _inject_valid_waits(store: Path) -> None:
    record = store / "workstreams" / "WS-AGENT-OS.md"
    _patch(
        record,
        "waves:\n",
        "wait:\n"
        "  kind: natural_evidence\n"
        "  review_after: 2026-09-25\n"
        "  condition: Review whether the preregistered prospective sample matured.\n"
        "waves:\n",
    )
    _patch(
        record,
        "    status: done\n    pr: 5472",
        "    status: done\n"
        "    wait:\n"
        "      kind: calendar_window\n"
        "      review_after: 2026-09-01\n"
        "      condition: Review at the declared calendar window.\n"
        "    pr: 5472",
    )


def test_typed_wait_projects_into_state_without_date_serialization_failure(store: Path) -> None:
    from scripts import agentos

    _inject_valid_waits(store)
    parsed = agentos.load_store(store, agentos._load_programs())
    assert not [problem for problem in parsed.problems if problem.hard]
    now = agentos._parse_moment("2026-08-27T15:00:00Z")
    assert now is not None

    original_git_dates = agentos.git_dates
    agentos.git_dates = lambda _path: (None, None)
    try:
        state = agentos.build_state(
            parsed,
            now=now,
            degraded=agentos.Degraded(),
            builds=None,
            p0_status=None,
            worktrees={"count": 0, "branches": [], "uncommitted": []},
        )
    finally:
        agentos.git_dates = original_git_dates

    row = next(item for item in state["workstreams"] if item["key"] == "AGENT-OS")
    assert row["wait"] == {
        "kind": "natural_evidence",
        "review_after": "2026-09-25",
        "condition": "Review whether the preregistered prospective sample matured.",
    }
    first_wave = next(item for item in row["wave_detail"] if item["id"] == "W0")
    assert first_wave["wait"] == {
        "kind": "calendar_window",
        "review_after": "2026-09-01",
        "condition": "Review at the declared calendar window.",
    }
    json.dumps(state, sort_keys=True)


def test_typed_wait_projects_into_context_target_and_wave_excerpt(store: Path) -> None:
    from scripts import agentos

    _inject_valid_waits(store)
    parsed = agentos.load_store(store, agentos._load_programs())
    now = agentos._parse_moment("2026-08-27T15:00:00Z")
    assert now is not None

    original_git_dates = agentos.git_dates
    original_repo_sha = agentos._repo_sha
    agentos.git_dates = lambda _path: (None, None)
    agentos._repo_sha = lambda: "test-sha"
    try:
        first = agentos.compile_bundle(
            parsed,
            workstream="AGENT-OS",
            now=now,
            builds=None,
            degraded=agentos.Degraded(),
        )
        second = agentos.compile_bundle(
            parsed,
            workstream="AGENT-OS",
            now=now,
            builds=None,
            degraded=agentos.Degraded(),
        )
    finally:
        agentos.git_dates = original_git_dates
        agentos._repo_sha = original_repo_sha

    assert first["target"]["wait"] == {
        "kind": "natural_evidence",
        "review_after": "2026-09-25",
        "condition": "Review whether the preregistered prospective sample matured.",
    }
    workstream_item = next(
        item
        for section in first["sections"]
        for item in section["items"]
        if item.get("kind") == "workstream" and item.get("key") == "WS:AGENT-OS"
    )
    assert "wait: calendar_window" in workstream_item["excerpt"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_wait_schema_mirror_names_closed_contract() -> None:
    mirror = (REPO / "agentos" / "schema" / "workstream.schema.yml").read_text(
        encoding="utf-8"
    )
    for term in (
        "natural_evidence",
        "external_dependency",
        "calendar_window",
        "external_action",
        "review_after",
        "condition",
    ):
        assert term in mirror


@pytest.mark.parametrize(
    "wait",
    [
        # An unhashable authored `kind` — `kind:` followed by a YAML block sequence, or
        # the flow typo `kind: {natural_evidence}` which PyYAML resolves to a mapping.
        {"kind": ["natural_evidence"], "review_after": "2026-09-25", "condition": "c"},
        {"kind": {"natural_evidence": None}, "review_after": "2026-09-25", "condition": "c"},
        # Unknown keys of INCOMPARABLE types.  Authored YAML resolves bare `no:`/`on:` to
        # bools and `2026-09-01:` to a date, so the closed-contract check — the very rule
        # that exists to reject extra keys — is what a mixed-key mapping reaches first.
        {"kind": "natural_evidence", "review_after": "2026-09-25", "condition": "c",
         1: "a", "zz": "b"},
        {"kind": "natural_evidence", "review_after": "2026-09-25", "condition": "c",
         None: "a", "zz": "b"},
        # Pattern-shaped but not a day.  A review date nobody can arrive at is malformed.
        {"kind": "natural_evidence", "review_after": "2026-13-45", "condition": "c"},
    ],
)
def test_hostile_wait_is_reported_not_raised(wait: dict[str, object]) -> None:
    """A malformed wait must come back as a typed `bad-wait` finding at BOTH scopes.

    Every input here used to raise out of ``check_workstream``, which turns a record-level
    validation finding into a crash of the whole fleet-wide `validate` run — the one
    outcome a validator may never have.
    """
    at_workstream = _wait_workstream()
    at_workstream["wait"] = wait
    assert [p.rule for p in _wait_hard(at_workstream)] == ["bad-wait"]

    at_wave = _wait_workstream()
    waves = at_wave["waves"]
    assert isinstance(waves, list) and isinstance(waves[0], dict)
    waves[0]["wait"] = wait
    assert [p.rule for p in _wait_hard(at_wave)] == ["bad-wait"]


@pytest.mark.parametrize(
    "review_after",
    ["2026-09-25", "2020-01-01", _dt.date(2026, 9, 25), _dt.date(2020, 1, 1)],
)
def test_wait_review_after_accepts_dates_including_past_ones(review_after: object) -> None:
    """A PAST `review_after` is an OVERDUE REVIEW, not an expiry — it stays schema-valid."""
    rec = _wait_workstream()
    rec["wait"] = {
        "kind": "external_action",
        "review_after": review_after,
        "condition": "Operator action remains outstanding.",
    }
    assert _wait_hard(rec) == []
