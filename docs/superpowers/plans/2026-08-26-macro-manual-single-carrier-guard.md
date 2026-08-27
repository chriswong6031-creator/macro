# Macro Manual Single-Carrier Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give correctly-behaving Claude/Fable/Codex/Grok manual sessions one deterministic, race-safe remote Git carrier for an Agent-OS-backed modifying wave, so an accidental duplicate session stops before project modification instead of opening a sibling implementation branch.

**Architecture:** `scripts/commission_preflight.py` is a bounded Git-carrier guard, not a scheduler or task store. It derives identity from `WORK_ID`, uses a create-only remote branch claim as the contested object, classifies existing carriers without takeover, and exposes a read-only context/status surface. Repository instructions and existing SessionStart hook configs point every major manual harness at the same law; Agent OS remains advisory and Executive OS remains the future primary admission owner.

**Tech Stack:** Python 3 stdlib, git CLI, optional `gh` CLI for richer PR classification, pytest, PyYAML BaseLoader for workflow-trigger tests, existing Claude/Codex/Grok JSON hook configs.

**Spec:** Mastermind `docs/superpowers/specs/2026-08-26-single-carrier-duplicate-dispatch-design.md`, approved design commit `83456d4f4b8496da44049271779a07bcf368fbf9`.

## Global Constraints

- A3 starts only after A2 is merged and the current protected Sol Skillpack is reloaded from one exact protected Mastermind SHA.
- A3 is the bootstrap exception: because the guard does not exist yet, Sol creates exactly one canonical A3 carrier after current collision archaeology; no sibling A3 branch is allowed.
- Frozen A3 identity is `WORK_ID: WS:CHAIRMAN-CONTROL-ROOM#SCG-A3`, `OPERATION_KEY: ws-1a2cf7ff85edc2c97ebf023856b94ab8`, `CARRIER_BRANCH: claude/op-ws-1a2cf7ff85edc2c97ebf023856b94ab8`.
- Frozen canary identity is `WORK_ID: WS:CHAIRMAN-CONTROL-ROOM#SCG-A3-CANARY`, `OPERATION_KEY: ws-995450fb918503e28f4bdbfc71b2eb00`, `CARRIER_BRANCH: claude/op-ws-995450fb918503e28f4bdbfc71b2eb00`.
- Work identity domain is exactly `b"mastermind.agentos.work_identity.v1\x00"`.
- The only canonical mutation made by a successful claim is the real remote Git carrier branch; no database/file lease/queue/claim service is added.
- Agent OS `claim` remains advisory and is never read as a permission gate by `commission_preflight.py`.
- Existing Executive OS, Slack/MCP ingress, provider routing, worker lifecycle, Linear and product runtime are non-goals.
- Existing transport-specific branch/session names do not change the logical operation key.
- No automatic takeover, remote-branch deletion, reset, force-push, sibling branch, random key, or provider suffix is allowed after collision.
- Remote/Git ambiguity fails closed for modifying work.
- `review` and `status` perform no remote writes and never switch the current branch.
- Carrier creation must start zero unintended product/deploy/publish workflows.
- Manual V0 is not described as perfect pre-edit enforcement for a manually launched Codex/Grok process that deliberately ignores repository law. The acceptance claim is limited to correctly-behaving sessions plus the tested carrier primitive.

---

## Sol-owned bootstrap before the implementation worker starts

A3 cannot use code that does not yet exist to claim itself. After A2 merges, Sol performs these steps once:

1. Fetch current Macro `origin/main` and re-check open PRs/branches touching `scripts/`, `.claude/`, `.codex/`, `.grok/`, `CLAUDE.md`, `AGENTS.md`, and `WS-CHAIRMAN-CONTROL-ROOM.md`.
2. Confirm no existing carrier exists for `claude/op-ws-1a2cf7ff85edc2c97ebf023856b94ab8`.
3. Create exactly that branch from the reconciled current `origin/main`; this is the one bootstrap carrier for A3.
4. Give the worker the A2-format preamble with the exact A3 identity above and `MODE: modifying`.
5. The first A3 commit registers `SCG-A3` and `SCG-A3-CANARY` as waves under `WS:CHAIRMAN-CONTROL-ROOM`; future sessions then have durable organizational identity for both implementation and proof.

No other A3 branch is valid.

---

### Task 1: Register the A3 organizational waves and pin the identity derivation API

**Files:**
- Modify: `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`
- Create: `scripts/commission_preflight.py`
- Create: `tests/test_commission_preflight.py`

**Interfaces:**
- Consumes: A2’s exact `WORK_ID`/operation-key law.
- Produces: `Identity`, `compose_work_id()`, `derive_operation_key()`, `carrier_branch()`, and a `context` CLI subcommand used by later tasks/harness wiring.

- [ ] **Step 1: Register the two durable waves before implementation code**

Add these wave rows to `WS-CHAIRMAN-CONTROL-ROOM.md` without changing unrelated current P0B/ASD next-action truth:

```yaml
  - id: SCG-A3
    title: Manual single-carrier duplicate-dispatch guard
    status: in_progress
    next_action: >
      Build the deterministic Git carrier preflight on the exact canonical A3 branch,
      prove local/bare-remote concurrency, then run the separately identified SCG-A3-CANARY
      before Sol acceptance. Agent OS remains advisory and must not become the lock.
  - id: SCG-A3-CANARY
    title: Two-session manual carrier collision proof
    status: todo
    depends_on: [SCG-A3]
    next_action: >
      From the A3 candidate head, launch two disposable detached session worktrees against
      the same canary WORK_ID and prove exactly one remote carrier claim succeeds while the
      loser stops before project modification and carrier creation starts no high-impact workflow.
```

Add the approved Mastermind design artifact to the existing `artifacts:` list if it is not already present:

```yaml
  - mastermind:docs/superpowers/specs/2026-08-26-single-carrier-duplicate-dispatch-design.md
```

Run:

```bash
python3 scripts/agentos.py validate
```

Expected: `0 errors`.

Commit this records-only bootstrap:

```bash
git add agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md
git commit -m "records(ccr): register single-carrier guard waves"
```

- [ ] **Step 2: Write the failing identity/context tests**

Create the first part of `tests/test_commission_preflight.py`:

```python
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import commission_preflight as cp


DOMAIN = b"mastermind.agentos.work_identity.v1\x00"


def test_identity_vectors_are_exact() -> None:
    vectors = {
        "WS:ALPHA-INTELLIGENCE-INTEGRATION#K3E-SRC-A1P": "ws-1198dccd042baab74b88a44e3ee5fb3b",
        "WS:CHAIRMAN-CONTROL-ROOM#A2": "ws-3ed8ecdbc8b6af7c5d5fa205fdd7db1a",
        "WS:EXECUTIVE-CAPACITY-FABRIC#CF2-F": "ws-54230ac4a84ff4b93528db1db5f2a905",
        "WS:CHAIRMAN-CONTROL-ROOM#SCG-A3": "ws-1a2cf7ff85edc2c97ebf023856b94ab8",
        "WS:CHAIRMAN-CONTROL-ROOM#SCG-A3-CANARY": "ws-995450fb918503e28f4bdbfc71b2eb00",
    }
    for work_id, expected in vectors.items():
        assert cp.derive_operation_key(work_id) == expected
        assert expected == "ws-" + hashlib.sha256(DOMAIN + work_id.encode()).hexdigest()[:32]


def test_compose_identity_rejects_malformed_parts() -> None:
    with pytest.raises(cp.PreflightError):
        cp.compose_work_id("CHAIRMAN-CONTROL-ROOM", "SCG-A3")
    with pytest.raises(cp.PreflightError):
        cp.compose_work_id("WS:CHAIRMAN-CONTROL-ROOM", "bad wave")


def test_context_is_read_only_and_names_the_stop_states(capsys: pytest.CaptureFixture[str]) -> None:
    assert cp.main(["context"]) == 0
    out = capsys.readouterr().out
    assert "SINGLE-CARRIER" in out
    assert "DUPLICATE_ACTIVE" in out
    assert "RECONCILE_REQUIRED" in out
    assert "ALREADY_FINISHED" in out
    assert "CONFLICT" in out
```

- [ ] **Step 3: Run the tests and confirm import/function failures**

```bash
pytest -q tests/test_commission_preflight.py -k 'identity or context'
```

Expected: collection/import failure because `scripts/commission_preflight.py` does not yet exist.

- [ ] **Step 4: Implement the pure identity API and `context` command**

Create `scripts/commission_preflight.py` with these exact public constants/signatures as the foundation; later tasks extend the same file rather than creating another carrier module:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SCHEMA = "mastermind.manual_carrier_preflight.v1"
CLAIM_SCHEMA = "mastermind.manual_carrier_claim.v1"
WORK_ID_DOMAIN = b"mastermind.agentos.work_identity.v1\x00"
CARRIER_PREFIX = "claude/op-"
EXPECTED_ORIGIN_MARKER = "mastermindx-market-intelligence/macro"
WORKSTREAM_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
WAVE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
OPERATION_KEY_RE = re.compile(r"^ws-[0-9a-f]{32}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

ALLOWED_STATES = frozenset({"CLAIMED", "CLAIMED_SELF"})
STOP_STATES = frozenset({
    "DUPLICATE_ACTIVE",
    "RECONCILE_REQUIRED",
    "ALREADY_FINISHED",
    "CONFLICT",
    "BASE_STALE",
    "UNAVAILABLE",
})
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_STOP = 20


class PreflightError(ValueError):
    pass


@dataclass(frozen=True)
class Identity:
    workstream: str
    wave: str
    work_id: str
    operation_key: str
    carrier_branch: str


def compose_work_id(workstream: str, wave: str) -> str:
    if WORKSTREAM_RE.fullmatch(workstream) is None:
        raise PreflightError("workstream must be an exact WS:<KEY> citation")
    if WAVE_RE.fullmatch(wave) is None:
        raise PreflightError("wave has an unsupported form")
    return f"{workstream}#{wave}"


def derive_operation_key(work_id: str) -> str:
    return "ws-" + hashlib.sha256(
        WORK_ID_DOMAIN + work_id.encode("utf-8")
    ).hexdigest()[:32]


def carrier_branch(operation_key: str) -> str:
    if OPERATION_KEY_RE.fullmatch(operation_key) is None:
        raise PreflightError("operation_key does not match the deterministic manual form")
    return CARRIER_PREFIX + operation_key


def identity(workstream: str, wave: str) -> Identity:
    work_id = compose_work_id(workstream, wave)
    operation_key = derive_operation_key(work_id)
    return Identity(
        workstream=workstream,
        wave=wave,
        work_id=work_id,
        operation_key=operation_key,
        carrier_branch=carrier_branch(operation_key),
    )


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(" | ".join(f"{key}={value}" for key, value in payload.items()))


def _context() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "state": "CONTEXT",
        "message": (
            "SINGLE-CARRIER: modifying commissions with WORK_ID/OPERATION_KEY must run "
            "commission_preflight.py claim before project edits; DUPLICATE_ACTIVE, "
            "RECONCILE_REQUIRED, ALREADY_FINISHED, CONFLICT, BASE_STALE and UNAVAILABLE "
            "are stop states; never mint a sibling key/branch to bypass a collision."
        ),
    }
```

Add `argparse` handling for `context`, `claim`, `status`, and `review`, but for this task `claim/status/review` may raise `PreflightError("not implemented")`; Task 2 replaces those temporary bodies before the task is committed.

- [ ] **Step 5: Run the identity/context tests**

```bash
pytest -q tests/test_commission_preflight.py -k 'identity or context'
```

Expected: all selected tests pass.

Do not commit the temporary unimplemented `claim/status/review` state; continue directly into Task 2 before the next commit.

---

### Task 2: Implement the atomic remote claim and exact failure semantics

**Files:**
- Modify: `scripts/commission_preflight.py`
- Modify: `tests/test_commission_preflight.py`

**Interfaces:**
- Consumes: `Identity` and deterministic carrier branch from Task 1.
- Produces: `claim(root, ident, supplied_operation_key, base_sha, worker_label=None) -> dict`, atomic create-only remote claim, and stable machine states/exit codes.

- [ ] **Step 1: Add bare-remote test helpers and the first-claim/mismatch/dirty-base tests**

Append this helper pattern to `tests/test_commission_preflight.py`:

```python
def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _repo_with_bare_origin(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    clone = tmp_path / "clone"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True, capture_output=True)
    subprocess.run(("git", "init", "-b", "main", str(seed)), check=True, capture_output=True)
    _git(seed, "config", "user.name", "Test")
    _git(seed, "config", "user.email", "test@example.com")
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    subprocess.run(("git", "clone", "--branch", "main", str(remote), str(clone)), check=True, capture_output=True)
    _git(clone, "config", "user.name", "Worker")
    _git(clone, "config", "user.email", "worker@example.com")
    return remote, clone, _git(clone, "rev-parse", "HEAD")
```

Use `monkeypatch` to replace `cp.EXPECTED_ORIGIN_MARKER` with the temporary bare-remote path string for local tests so repository-identity validation remains exercised rather than disabled.

Add tests that prove:

```python
ident = cp.identity("WS:CHAIRMAN-CONTROL-ROOM", "SCG-A3-CANARY")
result = cp.claim(clone, ident, ident.operation_key, base_sha, worker_label="test-a")
assert result["state"] == "CLAIMED"
assert result["carrier_branch"] == ident.carrier_branch
assert result["claim_commit"]
```

and separately:

```python
with pytest.raises(cp.PreflightError):
    cp.claim(clone, ident, "ws-" + "0" * 32, base_sha)
```

and dirty-tree refusal:

```python
(clone / "dirty.txt").write_text("dirty\n", encoding="utf-8")
result = cp.claim(clone, ident, ident.operation_key, base_sha)
assert result["state"] == "CONFLICT"
assert _git(clone, "ls-remote", "--heads", "origin", f"refs/heads/{ident.carrier_branch}") == ""
```

- [ ] **Step 2: Implement the Git primitives and claim-message contract**

Add these concrete helpers to `scripts/commission_preflight.py`:

```python
def _run_git(root: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _git_stdout(root: Path, *args: str) -> str:
    proc = _run_git(root, *args)
    if proc.returncode != 0:
        raise PreflightError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _claim_message(ident: Identity, base_sha: str, worker_label: str | None) -> str:
    lines = [
        "MMX-MANUAL-CARRIER-CLAIM-V1",
        f"schema: {CLAIM_SCHEMA}",
        f"work_id: {ident.work_id}",
        f"operation_key: {ident.operation_key}",
        f"base_sha: {base_sha}",
    ]
    if worker_label:
        lines.append(f"worker_label: {worker_label}")
    return "\n".join(lines) + "\n"


def _build_claim_commit(root: Path, ident: Identity, base_sha: str, worker_label: str | None) -> str:
    tree = _git_stdout(root, "show", "-s", "--format=%T", base_sha)
    proc = _run_git(
        root,
        "commit-tree",
        tree,
        "-p",
        base_sha,
        input_text=_claim_message(ident, base_sha, worker_label),
    )
    if proc.returncode != 0:
        raise PreflightError(proc.stderr.strip() or "git commit-tree failed")
    return proc.stdout.strip()
```

The claim commit must use the exact base tree, so `git diff-tree --no-commit-id --name-only -r <claim_commit>` is empty.

- [ ] **Step 3: Implement the create-only remote-ref claim**

Use the absent-ref lease exactly once:

```python
def _push_create_only(root: Path, branch: str, commit_sha: str) -> subprocess.CompletedProcess[str]:
    ref = f"refs/heads/{branch}"
    return _run_git(
        root,
        "push",
        "origin",
        f"--force-with-lease={ref}:",
        f"{commit_sha}:{ref}",
    )
```

Before relying on it, the unit test must demonstrate that the repository’s supported Git version treats the empty expected value as “remote ref must not exist.” If the local bare-remote race test does not discriminate, replace only this helper with an equivalent atomic create-only Git-ref operation; do not weaken to check-then-push.

- [ ] **Step 4: Implement `claim()` preconditions and effect-known failure handling**

`claim()` must perform this exact order:

1. recompute identity and refuse supplied operation-key mismatch before any fetch/push;
2. validate full lowercase `base_sha` shape;
3. verify `origin` contains `EXPECTED_ORIGIN_MARKER`;
4. require `git status --porcelain` empty;
5. `git fetch --prune origin main`;
6. require the exact base commit exists and is an ancestor of `refs/remotes/origin/main`; otherwise return `BASE_STALE`;
7. if current branch already equals the carrier, defer to Task 3’s `CLAIMED_SELF` validation;
8. if the remote carrier already exists, defer to Task 3 classification and perform zero push;
9. create the no-tree-change claim commit;
10. call `_push_create_only()` exactly once;
11. if push loses, classify the now-existing carrier; never retry under another key/branch;
12. if push wins, fetch the exact remote carrier and `git switch --create <carrier> --track origin/<carrier>`;
13. if local switch fails after a successful remote push, return `RECONCILE_REQUIRED` with `remote_claim_committed: true` and the exact `claim_commit`; never delete/retry automatically.

Successful payload shape:

```python
{
    "schema": SCHEMA,
    "state": "CLAIMED",
    "work_id": ident.work_id,
    "operation_key": ident.operation_key,
    "carrier_branch": ident.carrier_branch,
    "base_sha": base_sha,
    "claim_commit": claim_commit,
    "remote_claim_committed": True,
}
```

- [ ] **Step 5: Add the two-process race test**

Create two independent clones from one temporary bare remote, configure both identities, then launch `claim` through the CLI simultaneously using `subprocess.Popen`. Assert:

```python
states = {payload_a["state"], payload_b["state"]}
assert "CLAIMED" in states
assert len([p for p in (payload_a, payload_b) if p["state"] == "CLAIMED"]) == 1
assert len(_git(seed_or_clone, "ls-remote", "--heads", "origin", f"refs/heads/{ident.carrier_branch}").splitlines()) == 1
```

The losing process must return `EXIT_STOP`, create no second remote branch and leave its project tree byte-clean.

- [ ] **Step 6: Run the atomic-claim tests**

```bash
pytest -q tests/test_commission_preflight.py -k 'identity or context or claim or race or dirty or mismatch or base'
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the identity + atomic claim capability**

```bash
git add scripts/commission_preflight.py tests/test_commission_preflight.py
git commit -m "feat(fleet): claim one deterministic remote carrier"
```

---

### Task 3: Classify existing carriers without takeover and implement read-only `status`/`review`

**Files:**
- Modify: `scripts/commission_preflight.py`
- Modify: `tests/test_commission_preflight.py`

**Interfaces:**
- Consumes: remote carrier created by Task 2.
- Produces: `CLAIMED_SELF`, `DUPLICATE_ACTIVE`, `RECONCILE_REQUIRED`, `ALREADY_FINISHED`, `CONFLICT`, plus zero-write `status`/`review` modes.

- [ ] **Step 1: Add a claim-message parser and tests for incompatible metadata**

Implement:

```python
def _parse_claim_message(message: str) -> dict[str, str] | None:
    lines = message.splitlines()
    if not lines or lines[0] != "MMX-MANUAL-CARRIER-CLAIM-V1":
        return None
    values: dict[str, str] = {}
    for line in lines[1:]:
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        values[key] = value
    if values.get("schema") != CLAIM_SCHEMA:
        return None
    required = {"work_id", "operation_key", "base_sha"}
    return values if required.issubset(values) else None
```

Test an existing branch whose claim marker names a different `work_id` and assert `CONFLICT`, never takeover.

- [ ] **Step 2: Implement remote-branch fetch/read without switching the worktree**

Use a dedicated remote-tracking ref only:

```python
def _fetch_carrier(root: Path, branch: str) -> str | None:
    remote_ref = f"refs/remotes/origin/{branch}"
    proc = _run_git(
        root,
        "fetch",
        "--quiet",
        "origin",
        f"refs/heads/{branch}:{remote_ref}",
    )
    if proc.returncode != 0:
        return None
    return _git_stdout(root, "rev-parse", remote_ref)
```

Find the first commit message in carrier history containing `MMX-MANUAL-CARRIER-CLAIM-V1`; do not assume the branch tip remains the claim commit after implementation commits are pushed.

- [ ] **Step 3: Add local worktree and optional GitHub-PR evidence**

Implement local worktree inspection from:

```bash
git worktree list --porcelain
```

A different worktree holding `refs/heads/<carrier>` is positive `DUPLICATE_ACTIVE` evidence.

For cross-clone visibility, optionally invoke:

```bash
gh pr list --repo mastermindx-market-intelligence/macro --head <carrier> --state all --limit 100 --json number,state,isDraft,mergedAt,url,headRefName
```

Rules:

- any merged PR for the carrier -> `ALREADY_FINISHED`;
- any open PR for the carrier -> `DUPLICATE_ACTIVE`;
- `gh` unavailable/rate-limited does not free the carrier; with an existing remote branch and no stronger evidence return `RECONCILE_REQUIRED`;
- closed-unmerged PR -> `RECONCILE_REQUIRED`;
- absence of a PR is never permission to take over an existing remote branch.

- [ ] **Step 4: Implement `CLAIMED_SELF` narrowly**

Return `CLAIMED_SELF` only when all hold:

- current branch equals the canonical carrier;
- the branch history contains a valid claim marker;
- marker `work_id`, `operation_key`, and `base_sha` equal the current invocation;
- current HEAD descends from that claim commit.

A new/different worktree on an existing carrier is not self merely because `worker_label` matches.

- [ ] **Step 5: Implement `status` and `review` as zero-remote-write modes**

Both may run `git ls-remote`, `git fetch` into remote-tracking refs, `git worktree list`, and `gh pr list`. They must never run `git push`, `git switch`, `git branch`, `git reset`, `git rebase`, `gh pr create/edit/merge`, or Agent OS writes.

Add a test that monkeypatches `_run_git`/`subprocess.run`, calls `status` and `review`, and asserts the captured argv contains no forbidden mutation verbs.

- [ ] **Step 6: Run the complete preflight unit suite**

```bash
pytest -q tests/test_commission_preflight.py
```

Expected: all tests pass, including the real two-process bare-remote race.

- [ ] **Step 7: Commit classification/read-only behavior**

```bash
git add scripts/commission_preflight.py tests/test_commission_preflight.py
git commit -m "feat(fleet): reconcile existing commission carriers"
```

---

### Task 4: Wire one shared worker law and prove carrier creation is workflow-inert

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `.claude/settings.json`
- Modify: `.codex/hooks.json`
- Modify: `.grok/hooks/sparse-worktree.json`
- Create: `tests/test_commission_worker_wiring.py`
- Create: `tests/test_commission_carrier_workflow_safety.py`

**Interfaces:**
- Consumes: `commission_preflight.py context/claim` from Tasks 1–3.
- Produces: one parity worker law across Claude/Codex/Grok, SessionStart visibility, and a repository-wide regression preventing future push workflows from silently targeting `claude/op-*` carriers.

- [ ] **Step 1: Create failing parity/hook tests**

Create `tests/test_commission_worker_wiring.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = "<!-- SINGLE-CARRIER-COMMISSION-LAW:START -->"
END = "<!-- SINGLE-CARRIER-COMMISSION-LAW:END -->"


def _section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert START in text and END in text
    return text.split(START, 1)[1].split(END, 1)[0].strip()


def _session_start_commands(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    commands: list[str] = []
    for group in doc["hooks"]["SessionStart"]:
        for hook in group.get("hooks", []):
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(command)
    return commands


def test_claude_and_agents_single_carrier_law_are_byte_equal() -> None:
    assert _section(ROOT / "CLAUDE.md") == _section(ROOT / "AGENTS.md")


def test_major_manual_harnesses_load_the_same_context_command() -> None:
    configs = (
        ROOT / ".claude/settings.json",
        ROOT / ".codex/hooks.json",
        ROOT / ".grok/hooks/sparse-worktree.json",
    )
    for path in configs:
        commands = _session_start_commands(path)
        assert any("commission_preflight.py" in command and " context" in command for command in commands)
```

Run:

```bash
pytest -q tests/test_commission_worker_wiring.py
```

Expected: fail because the parity section and context commands are absent.

- [ ] **Step 2: Add the exact parity section to both `CLAUDE.md` and `AGENTS.md`**

Insert the same bytes in both files near the shared session/workspace rules:

```markdown
<!-- SINGLE-CARRIER-COMMISSION-LAW:START -->
### Single-carrier modifying commissions

When a Sol/Chairman handoff contains `MODE: modifying` plus `WORK_ID`, `OPERATION_KEY`, `BASE_SHA`, and `CARRIER_BRANCH`, run `python3 scripts/commission_preflight.py claim ...` with those exact values **before the first project edit**. The command recomputes the operation key and canonical carrier from `WORK_ID`; never replace them with a session/provider/timestamp suffix.

`DUPLICATE_ACTIVE`, `RECONCILE_REQUIRED`, `ALREADY_FINISHED`, `CONFLICT`, `BASE_STALE`, and `UNAVAILABLE` are stop states for modifying work. Do not create another branch, delete/reset/force-push the carrier, or retry under another key. Report/review the existing carrier and reconcile it under current Sol law.

`MODE: review_only` does not claim the carrier and performs no project modification. Agent OS claims are visibility only and never grant execution permission.

Manual V0 assumes a correctly-behaving session invokes preflight; Executive OS will eventually move this admission before worker launch.
<!-- SINGLE-CARRIER-COMMISSION-LAW:END -->
```

- [ ] **Step 3: Add one read-only `context` hook command to each existing SessionStart config**

Add this command as an additional SessionStart hook without replacing sparse-worktree or ship-loop hooks:

```text
python3 "$(git rev-parse --show-toplevel)/scripts/commission_preflight.py" context
```

For `.claude/settings.json`, use `$CLAUDE_PROJECT_DIR` instead of command substitution to match existing local convention:

```text
python3 "$CLAUDE_PROJECT_DIR/scripts/commission_preflight.py" context
```

Use timeout `10` and status message `Loading single-carrier commission law`.

Do not add a claimed pre-edit Codex/Grok enforcement mechanism that the harness cannot prove. This wiring is visibility/context only.

- [ ] **Step 4: Add the workflow-safety census regression**

Create `tests/test_commission_carrier_workflow_safety.py`:

```python
from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
CARRIER = "claude/op-ws-0123456789abcdef0123456789abcdef"


def _items(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _ordered_match(patterns: list[str], branch: str) -> bool:
    matched = False
    for raw in patterns:
        negative = raw.startswith("!")
        pattern = raw[1:] if negative else raw
        if fnmatch.fnmatchcase(branch, pattern):
            matched = not negative
    return matched


def _push_selects_carrier(push: object) -> bool:
    if not isinstance(push, dict):
        return True
    branches = _items(push.get("branches"))
    branches_ignore = _items(push.get("branches-ignore"))
    if branches:
        return _ordered_match(branches, CARRIER)
    if branches_ignore:
        return not any(fnmatch.fnmatchcase(CARRIER, pattern) for pattern in branches_ignore)
    return True


def test_no_push_workflow_targets_manual_carrier_namespace() -> None:
    offenders: list[str] = []
    for path in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if not isinstance(doc, dict):
            continue
        events = doc.get("on")
        if not isinstance(events, dict) or "push" not in events:
            continue
        if _push_selects_carrier(events["push"]):
            offenders.append(path.name)
    assert offenders == [], f"carrier branch would trigger push workflows: {offenders}"
```

If this test finds an offender, update only that workflow’s `push` branch filter so product/deploy/publish behavior remains unchanged on `main` while `claude/op-*` is explicitly excluded. Do not blanket-disable PR checks; PR CI must still run normally once a PR is opened.

- [ ] **Step 5: Run wiring/workflow tests plus existing worktree tests**

```bash
pytest -q \
  tests/test_commission_worker_wiring.py \
  tests/test_commission_carrier_workflow_safety.py \
  tests/test_sparse_worktree_profile.py \
  tests/test_worktree_placement.py \
  tests/test_agent_worktree_roots.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit worker wiring and workflow safety**

```bash
git add \
  CLAUDE.md AGENTS.md \
  .claude/settings.json .codex/hooks.json .grok/hooks/sparse-worktree.json \
  tests/test_commission_worker_wiring.py \
  tests/test_commission_carrier_workflow_safety.py
git commit -m "feat(fleet): wire single-carrier commission preflight"
```

---

### Task 5: Run the real two-worktree canary, record proof, and close A3 truthfully

**Files:**
- Modify: `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`
- Create: `agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-26-single-carrier-guard.md`
- Verify: all A3 implementation/test/hook files

**Interfaces:**
- Consumes: candidate A3 head from Tasks 1–4.
- Produces: real GitHub carrier collision receipt, zero-workflow-side-effect receipt, durable Agent OS closeout, and the exact limitation that manually launched noncompliant workers are not claimed blocked pre-edit.

- [ ] **Step 1: Run the complete focused suite before touching the live remote canary**

```bash
pytest -q \
  tests/test_commission_preflight.py \
  tests/test_commission_worker_wiring.py \
  tests/test_commission_carrier_workflow_safety.py \
  tests/test_sparse_worktree_profile.py \
  tests/test_worktree_placement.py \
  tests/test_agent_worktree_roots.py
python3 scripts/agentos.py validate
git diff --check
```

Expected: all tests pass, Agent OS reports zero errors, diff check is clean.

- [ ] **Step 2: Push the candidate A3 head on its canonical implementation branch**

Confirm:

```bash
test "$(git branch --show-current)" = "claude/op-ws-1a2cf7ff85edc2c97ebf023856b94ab8"
git push -u origin HEAD
```

Do not create a sibling branch if this fails; reconcile the exact carrier.

- [ ] **Step 3: Create two disposable detached worktrees from the candidate head**

From the donor checkout:

```bash
CANARY_A=.claude/worktrees/scg-a3-canary-a
CANARY_B=.claude/worktrees/scg-a3-canary-b
git worktree add --detach "$CANARY_A" HEAD
git worktree add --detach "$CANARY_B" HEAD
BASE_SHA=$(git rev-parse origin/main)
```

Both worktrees begin detached so neither owns an alternate implementation branch before the claim.

- [ ] **Step 4: Launch the two claimers concurrently and assert exactly one winner in memory**

Run this from the donor root:

```bash
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

roots = [
    Path(".claude/worktrees/scg-a3-canary-a"),
    Path(".claude/worktrees/scg-a3-canary-b"),
]
base = subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
cmd = [
    "python3", "scripts/commission_preflight.py", "claim",
    "--workstream", "WS:CHAIRMAN-CONTROL-ROOM",
    "--wave", "SCG-A3-CANARY",
    "--operation-key", "ws-995450fb918503e28f4bdbfc71b2eb00",
    "--base", base,
    "--json",
]
procs = [
    subprocess.Popen(cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for root in roots
]
results = []
for proc in procs:
    stdout, stderr = proc.communicate()
    payload = json.loads(stdout.strip().splitlines()[-1])
    results.append((proc.returncode, payload, stderr))
print(json.dumps(results, indent=2))
states = [payload["state"] for _, payload, _ in results]
assert states.count("CLAIMED") == 1, states
losers = [state for state in states if state != "CLAIMED"]
assert losers and losers[0] in {"DUPLICATE_ACTIVE", "RECONCILE_REQUIRED"}, states
winner = next(payload for _, payload, _ in results if payload["state"] == "CLAIMED")
assert winner["carrier_branch"] == "claude/op-ws-995450fb918503e28f4bdbfc71b2eb00"
assert winner["remote_claim_committed"] is True
PY
```

This is the real shared-clone/session-worktree proof. The separate unit race already proves the same primitive across independent clones against a bare remote.

- [ ] **Step 5: Prove the live canary carrier triggered zero workflow runs**

Query the GitHub Actions API for the exact canary branch:

```bash
CARRIER='claude/op-ws-995450fb918503e28f4bdbfc71b2eb00'
for _ in 1 2 3 4 5 6; do
  COUNT=$(gh api -X GET repos/mastermindx-market-intelligence/macro/actions/runs -f branch="$CARRIER" --jq '.total_count')
  test "$COUNT" = "0" || break
  sleep 5
done
test "$COUNT" = "0"
```

Expected: zero workflow runs for the raw branch-claim push. PR checks later are unaffected and are allowed/required.

- [ ] **Step 6: Clean up the disposable canary only after exact-tip reconciliation**

Read the canary remote tip and the winning claim SHA from the canary output. Delete the remote canary branch only if they are byte-equal and no PR exists for the canary branch:

```bash
gh pr list --repo mastermindx-market-intelligence/macro --head "$CARRIER" --state all --json number --jq 'length'
```

Expected: `0`.

Then remove the disposable worktrees, delete the exact remote branch, and delete the local canary branch only after no worktree holds it. If the remote tip changed, a PR appeared, or any identity is ambiguous, **do not clean it up**; return `RECONCILE_REQUIRED` to Sol.

- [ ] **Step 7: Update the Agent OS waves and write the closeout handoff**

Set `SCG-A3` and `SCG-A3-CANARY` to `done` only after Steps 1–6 pass. Add the A3 PR number to `SCG-A3.pr` once the PR exists.

Create `agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-26-single-carrier-guard.md` using the repository’s current handoff schema. Populate it from actual receipts, with these required truths:

- mission: manual duplicate modifying sessions share one deterministic carrier;
- changed: script, worker-law parity, hook context, workflow safety, workstream waves;
- verified: deterministic vectors, independent-clone bare-remote race, live two-worktree GitHub canary, zero branch-push workflow runs, focused tests, Agent OS validation;
- unverified: a manually launched Codex/Grok process that deliberately ignores repository law before preflight is not claimed blocked;
- unresolved: Executive cross-transport logical-operation admission remains B1/B2 and is not started;
- next action: use this guard on subsequent manual commissions; hold Executive schema work until separately re-pinned/commissioned;
- do_not_redo: no Agent OS hard lease, no new queue/DB, no sibling branch on collision;
- danger_areas: remote-claim effect-known/local-switch failure must reconcile, not retry; branch-creation workflow topology must remain inert.

Run:

```bash
python3 scripts/agentos.py validate
```

Expected: zero errors.

- [ ] **Step 8: Commit the proof/closeout**

```bash
git add \
  agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md \
  agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-26-single-carrier-guard.md
git commit -m "records(ccr): prove manual single-carrier guard"
```

- [ ] **Step 9: Open the A3 PR and require normal CI + Sol adversarial review**

The PR body must distinguish:

```text
PROVEN by this carrier: correctly-behaving manual sessions with the same frozen WORK_ID cannot both acquire modifying carriers; one remote branch wins; loser stops; raw claim push is workflow-inert.
NOT proven: Executive cross-transport dedupe; automatic worker dispatch; perfect pre-edit blocking of a manual worker that ignores repository law; Agent OS liveness/authority.
```

Wait for all binding checks to conclude. Sol reviews the exact head against the approved design before merge.

- [ ] **Step 10: Stop**

A3 is complete only when the implementation PR is merged, the live two-worktree canary receipt is durable, the exact manual limitation is recorded, and the first canonical carrier remains compatible with the normal PR/CI flow. Do not start Executive B1/B2 from this worker.
