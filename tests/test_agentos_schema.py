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


def _validate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "validate", "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=REPO,
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
        "blocked-without-cause",
        "workstreams/WS-CN-LIMIT-ALPHA.md",
        "blocked_by:",
        "blocked_by: []\nunused_blocked_by:",
    ),
    ("bad-date", "workstreams/WS-AGENT-OS.md", "updated: 2026-08-12", "updated: last Tuesday"),
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
    _patch(store / "workstreams" / "WS-AGENT-OS.md", "updated: 2026-08-12", "updated: 2025-01-01")
    result = _validate(store)
    assert result.returncode == 0, result.stdout
    assert "stale-workstream" in result.stdout


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


def test_cross_repo_paths_do_not_warn(store: Path) -> None:
    """A `repo:` prefixed path lives in a sibling checkout and must not be flagged."""
    _patch(
        store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md",
        "landmines:",
        "artifacts:\n  - terminal:app/routes/portfolio.tsx\nlandmines:",
    )
    result = _validate(store)
    assert result.returncode == 0
    assert "phantom-artifact" not in result.stdout


def test_absent_store_exits_zero(tmp_path: Path) -> None:
    """A repo that has not adopted Agent OS is not a broken repo."""
    result = _validate(tmp_path / "nonexistent")
    assert result.returncode == 0
    assert "no agentos/ store" in result.stdout


def test_quiet_suppresses_warnings_but_not_errors(store: Path) -> None:
    _patch(store / "workstreams" / "WS-AGENT-OS.md", "updated: 2026-08-12", "updated: 2025-01-01")
    result = subprocess.run(
        [sys.executable, str(CLI), "validate", "--root", str(store), "--quiet"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0
    assert "stale-workstream" not in result.stdout


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


def test_stubs_are_visibly_stubs() -> None:
    """A not-yet-implemented subcommand must announce itself, never exit silently."""
    for command in ("status", "brief", "compile-context"):
        result = subprocess.run(
            [sys.executable, str(CLI), command], capture_output=True, text=True, cwd=REPO
        )
        assert result.returncode == 0
        assert "not implemented" in result.stdout, f"{command} exited silently"
