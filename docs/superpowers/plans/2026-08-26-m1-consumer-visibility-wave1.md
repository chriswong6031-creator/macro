# M1 Consumer Visibility Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one read-only M1 Macro consumer census command plus stronger wrong-account transport regression coverage so a fresh operator can deterministically see every loaded/recent Macro dependency and detect unlawful repository identity before any migration mutation.

**Architecture:** Implement a single Python inspector that reads bounded launchd/plist/Git/filesystem evidence and emits one versioned JSON model plus a table projection; it performs no fetch, reset, launchctl mutation, service trigger, remote shell, or credential-value read. Every subprocess uses an absolute executable, fixed argv grammar, sanitized environment, hostile local-Git configuration neutralization, bounded output, and a timeout. Extend the existing `check_macro_anon_dependency.py` fence to reject old-personal-owner Git transport targets while preserving human citation allowances. Wave 1 implementation stops after code/CI and an immutable reviewed head; a separately released post-merge step obtains one real read-only M1 census receipt. Classification remains a Sol/operator act and no consumer remote is changed.

**Tech Stack:** Python 3 stdlib (`argparse`, `dataclasses`, `datetime`, `json`, `pathlib`, `plistlib`, `re`, `stat`, `subprocess`), pytest, existing Macro CI/fence framework, macOS `launchctl` for production proof only.

**Spec:** `docs/superpowers/specs/2026-08-26-m1-macro-consumer-hardening-design.md`

## Global Constraints

- Canonical execution/evidence carrier remains GitHub #6432; MAS-137/MAS-140 are projection only.
- Current protected Sol Skillpack for release review: `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`, schema `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1` compatible. Re-pin again before implementation/host proof.
- Chairman-approved architecture head: `afc01c8ffeb6299b1b801637230b478f403ea8fe`; released/reconciled design head: `18590a9d8bdd5832b11229ddbe714447764effd7`; reviewed Macro base: `463bb3b4b708a4748fc65a04250366ca94205186`.
- No M1 mutation in Wave 1: no `launchctl enable/disable/bootstrap/bootout/kickstart`, no Git fetch/pull/reset/checkout/clean/rebase, no remote/config write, no file deletion/move, no mount/storage/listener/runner action.
- `/Users/chriswong/flow-ops-wt` is inspect-only; never normalize its deliberate detached/dirty state.
- `com.macro.live-breadth` must remain disabled/unloaded; its retired state is evidence, not a migration target.
- Native macOS persistent-disabled output must normalize both exact spellings `=> true` and `=> disabled`; `false`, `enabled`, duplicate/inexact rows, and ambiguous output are not accepted as disabled evidence. This compatibility constraint was introduced at protected Mastermind commit `acc7ebc4...` and remains binding in the current `af43f356...` Skillpack.
- The inspector never prints or persists private-key bytes, token values, `.env` contents, arbitrary environment values, raw remote URLs, credential-helper values, SSH stderr, or full process environments. Raw Git URL/config values are transient classification inputs only and must be discarded before report/error construction.
- Git inspection must neutralize repository-local host-execution seams (including `core.fsmonitor` and hooks), recursive submodule/status behavior, inherited `GIT_*` control variables, global/system config, prompts, and optional index locks before any `status` probe. A hostile `core.fsmonitor` fixture must prove no marker process executes.
- Launchctl inspection is restricted to `/bin/launchctl print-disabled gui/<uid>` and `/bin/launchctl print gui/<uid>/<validated-label>` with fixed label/domain grammar, bounded output, a timeout, and fail-closed error parsing. Unit tests assert exact argv construction and refusal before subprocess launch.
- The inspector may label deterministic evidence (`wrong_owner`, `anonymous_transport`, `loaded`, `disabled`, `explicit_machine_identity`) but may not emit organizational decisions such as `KEEP_AUTHENTICATE` or `RETIRE_DUPLICATE`.
- No new durable registry, inventory database, daemon, scheduler, queue, cursor, credential broker, or truth store.
- TDD is mandatory: each production behavior starts with a failing test, the worker must run it and observe the expected failure before implementation.
- Existing anonymous-dependency fence behavior and precision allowances must not regress.
- Wave 1 does not depend on the 2026-08-30 Index/GEX natural-time receipt; overall private-cutover readiness still does.

---

## File Map

- Create `scripts/inspect_m1_macro_consumers.py` — pure parsers/data model + bounded read-only host probes + CLI/output contract.
- Create `tests/test_m1_macro_consumer_inspector.py` — Linux/hermetic unit tests for launchd parsing, plist extraction, checkout evidence, redaction, JSON/table output, and exit semantics.
- Modify `scripts/check_macro_anon_dependency.py` — add old-owner SSH/SCP transport detection without broadening to human citation bans.
- Modify `tests/test_macro_anon_dependency_guard.py` — non-vacuity + precision tests for old-owner transport shapes and canonical-org SSH allowance.
- Create `docs/M1_MACRO_CONSUMER_INSPECTION_RUNBOOK.md` — exact read-only invocation, output interpretation, failure behavior, and #6432 return packet.
- Do not modify `.github/workflows/*`, runner policy, launchd plists, host deploy trees, Git remotes, Agent OS records, or credential files in the implementation PR. Agent OS closeout happens only after real-host proof is accepted.

---

### Task 1: Freeze the census data model and exact launchd disabled-state parser

**Files:**
- Create: `scripts/inspect_m1_macro_consumers.py`
- Create: `tests/test_m1_macro_consumer_inspector.py`

**Interfaces:**
- Produces: `parse_launchctl_disabled(output: str, label: str) -> tuple[bool, str | None]`
- Produces: frozen dataclasses `GitIdentityEvidence`, `CheckoutEvidence`, `ServiceEvidence`, `CensusReport`
- Consumes later: Tasks 2–3 build evidence using these exact structures.

- [ ] **Step 1: Write failing tests for the two accepted disabled spellings and refusal cases**

Add to `tests/test_m1_macro_consumer_inspector.py`:

```python
import pytest

from scripts import inspect_m1_macro_consumers as census


@pytest.mark.parametrize("state", ("true", "disabled"))
def test_parse_launchctl_disabled_accepts_native_disabled_spellings(state: str) -> None:
    label = "com.macro.live-breadth"
    raw = f'disabled services = {{\n    "{label}" => {state}\n}}\n'
    assert census.parse_launchctl_disabled(raw, label) == (True, state)


@pytest.mark.parametrize(
    "raw",
    (
        '"com.macro.live-breadth" => false\n',
        '"com.macro.live-breadth" => enabled\n',
        '"com.macro.live-breadth-extra" => disabled\n',
        '"com.macro.live-breadth" => disabled extra\n',
        '"com.macro.live-breadth" => disabled\n"com.macro.live-breadth" => true\n',
    ),
)
def test_parse_launchctl_disabled_rejects_false_ambiguous_or_inexact_rows(raw: str) -> None:
    with pytest.raises(census.InspectionError, match="LAUNCHCTL_DISABLED_STATE_INVALID"):
        census.parse_launchctl_disabled(raw, "com.macro.live-breadth")
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: collection/import failure because `scripts.inspect_m1_macro_consumers` does not exist yet.

- [ ] **Step 3: Add the minimal parser and data model**

Create `scripts/inspect_m1_macro_consumers.py` with these public structures first:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import re

SCHEMA = "macro.m1_consumer_census.v1"
_CANONICAL_REPO_SSH = "git@github.com:mastermindx-market-intelligence/macro.git"
_OLD_OWNER = "chriswong6031-creator"
_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class InspectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitIdentityEvidence:
    canonical_repo: bool
    wrong_owner: bool
    anonymous_transport: bool
    explicit_machine_identity: bool
    ambient_fallback_possible: bool
    write_capability_observed: bool


@dataclass(frozen=True, slots=True)
class CheckoutEvidence:
    path: str
    head: str | None
    detached: bool | None
    dirty_tracked_count: int | None
    dirty_untracked_count: int | None
    remote_states: tuple[str, ...]
    fetch_head_mtime: str | None
    git_identity: GitIdentityEvidence
    inspection_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceEvidence:
    service_id: str
    plist_path: str
    loaded: bool | None
    enabled: bool | None
    disabled_observed_state: str | None
    active: bool | None
    entrypoint: str | None
    working_directory: str | None
    environment_names: tuple[str, ...]
    checkout: CheckoutEvidence | None
    last_execution: str | None
    hazards: tuple[str, ...]
    inspection_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CensusReport:
    schema: str
    observed_at: str
    hostname: str
    services: tuple[ServiceEvidence, ...]
    complete_for_cutover: bool


def parse_launchctl_disabled(output: str, label: str) -> tuple[bool, str | None]:
    if _LABEL_RE.fullmatch(label) is None or len(output.encode("utf-8")) > 256 * 1024:
        raise InspectionError("LAUNCHCTL_DISABLED_STATE_INVALID")
    matches: list[str] = []
    for line in output.splitlines():
        match = re.fullmatch(r'\s*"([^"\r\n]+)"\s*=>\s*(\S+)\s*', line)
        if match is not None and match.group(1) == label:
            matches.append(match.group(2))
    if not matches:
        return (False, None)
    if len(matches) != 1 or matches[0] not in {"true", "disabled"}:
        raise InspectionError("LAUNCHCTL_DISABLED_STATE_INVALID")
    return (True, matches[0])
```

The no-match case is `(False, None)` because `print-disabled` omitting a label is evidence that it is not persistently disabled, while an inexact/contradictory row is malformed evidence.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: disabled-state tests pass.

- [ ] **Step 5: Commit the parser/data-model slice**

```bash
git add scripts/inspect_m1_macro_consumers.py tests/test_m1_macro_consumer_inspector.py
git commit -m "feat(ops): define M1 consumer census contract"
```

---

### Task 2: Parse plists and derive bounded service-to-checkout candidates without secrets

**Files:**
- Modify: `scripts/inspect_m1_macro_consumers.py`
- Modify: `tests/test_m1_macro_consumer_inspector.py`

**Interfaces:**
- Produces: `parse_plist(path: Path) -> dict[str, object]`
- Produces: `service_definition(path: Path) -> tuple[str, str | None, str | None, tuple[str, ...], tuple[Path, ...]]`
- Consumes: Task 1 dataclasses.
- Contract: environment **names only**; no `.env` or environment values.

- [ ] **Step 1: Write a failing plist extraction test using a real binary/XML plist writer**

```python
import plistlib


def test_service_definition_emits_env_names_and_checkout_candidates_without_values(tmp_path) -> None:
    plist_path = tmp_path / "com.mastermind.optionshub.plist"
    plist_path.write_bytes(plistlib.dumps({
        "Label": "com.mastermind.optionshub",
        "ProgramArguments": [
            "/bin/bash",
            "/Users/chriswong/hub-ops-wt/scripts/run_optionshub.sh",
        ],
        "WorkingDirectory": "/Users/chriswong/hub-ops-wt",
        "EnvironmentVariables": {
            "PYTHONPATH": "/Users/chriswong/hub-ops-wt",
            "SECRET_TOKEN": "must-never-appear",
        },
    }))

    label, entrypoint, cwd, env_names, candidates = census.service_definition(plist_path)
    assert label == "com.mastermind.optionshub"
    assert entrypoint == "/Users/chriswong/hub-ops-wt/scripts/run_optionshub.sh"
    assert cwd == "/Users/chriswong/hub-ops-wt"
    assert env_names == ("PYTHONPATH", "SECRET_TOKEN")
    assert Path("/Users/chriswong/hub-ops-wt") in candidates
    rendered = repr((label, entrypoint, cwd, env_names, candidates))
    assert "must-never-appear" not in rendered
```

Also add one test where `WorkingDirectory` is absent but an absolute script path identifies a checkout candidate, and one malformed plist test expecting `InspectionError("PLIST_INVALID")`.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: `AttributeError` for missing `service_definition`.

- [ ] **Step 3: Implement minimal plist parsing and candidate extraction**

Use stdlib `plistlib`; accept only a non-empty string `Label`, string-list `ProgramArguments`, optional string `WorkingDirectory`, and dict `EnvironmentVariables`. Derive candidates only from absolute `WorkingDirectory`, absolute argv paths, and absolute values of explicitly non-secret path variables such as `PYTHONPATH`; never include arbitrary environment values in returned data.

Implement a private helper:

```python
_SAFE_PATH_ENV_NAMES = frozenset({"PYTHONPATH"})


def _checkout_candidates(doc: dict[str, object]) -> tuple[Path, ...]:
    candidates: set[Path] = set()
    cwd = doc.get("WorkingDirectory")
    if isinstance(cwd, str) and Path(cwd).is_absolute():
        candidates.add(Path(cwd))
    for arg in doc.get("ProgramArguments", []):
        if isinstance(arg, str) and Path(arg).is_absolute():
            candidates.add(Path(arg).parent)
    env = doc.get("EnvironmentVariables", {})
    if isinstance(env, dict):
        for name in _SAFE_PATH_ENV_NAMES:
            value = env.get(name)
            if isinstance(value, str):
                for part in value.split(":"):
                    if part and Path(part).is_absolute():
                        candidates.add(Path(part))
    return tuple(sorted(candidates, key=str))
```

Walk candidate parents only up to the filesystem root later when resolving a `.git` boundary; do not recursively crawl sibling directories.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: plist tests pass; secret value never appears.

- [ ] **Step 5: Commit**

```bash
git add scripts/inspect_m1_macro_consumers.py tests/test_m1_macro_consumer_inspector.py
git commit -m "feat(ops): inspect M1 launchd definitions safely"
```

---

### Task 3: Add read-only Git checkout and repository-identity evidence

**Files:**
- Modify: `scripts/inspect_m1_macro_consumers.py`
- Modify: `tests/test_m1_macro_consumer_inspector.py`

**Interfaces:**
- Produces: `classify_remote(url: str) -> tuple[bool, bool, bool]` representing `(canonical_repo, wrong_owner, anonymous_transport)`.
- Produces: `inspect_checkout(path: Path, run_git: Callable[..., CompletedProcess[str]] = _run_git) -> CheckoutEvidence | None`.
- No network command is allowed.

- [ ] **Step 1: Write failing remote-classification tests**

```python
@pytest.mark.parametrize(
    "url, expected",
    (
        ("git@github.com:mastermindx-market-intelligence/macro.git", (True, False, False)),
        ("ssh://git@github.com/mastermindx-market-intelligence/macro.git", (True, False, False)),
        ("https://github.com/mastermindx-market-intelligence/macro.git", (True, False, True)),
        ("git@github.com:chriswong6031-creator/macro.git", (False, True, False)),
        ("https://github.com/chriswong6031-creator/macro.git", (False, True, True)),
        ("git@github.com:mastermindx-market-intelligence/other.git", (False, False, False)),
    ),
)
def test_classify_remote(url, expected) -> None:
    assert census.classify_remote(url) == expected
```

- [ ] **Step 2: Write failing local-repository tests proving no network or host-code execution occurs**

Create a temporary Git repository with `git init`, one commit, then set `origin` to the old-owner URL. Monkeypatch `census._run_git` with a wrapper that records argv and delegates to `/usr/bin/git`; call `inspect_checkout(repo)`. Assert:

```python
assert evidence.git_identity.wrong_owner is True
assert evidence.git_identity.anonymous_transport is False
assert all("fetch" not in argv for argv in observed_commands)
assert all("pull" not in argv for argv in observed_commands)
assert all("reset" not in argv for argv in observed_commands)
```

Also assert dirty tracked/untracked counts using one modified tracked file plus one untracked file.

Create a second repository whose local config points `core.fsmonitor` at a marker executable. Run `inspect_checkout(repo)` and assert the marker file is absent afterward. Record every subprocess argv and assert the status probe contains the high-precedence `core.fsmonitor=false`, hook neutralization, and submodule-recursion refusal before `status`.

Add a third fixture with a token-bearing HTTPS remote and a shell-form `credential.helper`. Build both JSON and table output, trigger one sanitized inspection error, and assert the token, raw remote, and helper value are absent from every output/exception/diagnostic string.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: missing `classify_remote`/`inspect_checkout` failures.

- [ ] **Step 4: Implement read-only Git probes**

The production wrapper invokes the absolute `/usr/bin/git` with `shell=False`, a five-second timeout, a 256-KiB stdout/stderr ceiling, `--no-optional-locks`, and high-precedence neutralization before the exact read-only command grammar:

```text
-c core.fsmonitor=false
-c core.hooksPath=/dev/null
-c submodule.recurse=false
-c status.submoduleSummary=false
```

Allowed command suffixes are limited to:

```text
rev-parse --show-toplevel
rev-parse HEAD
symbolic-ref -q --short HEAD
status --porcelain=v1 --untracked-files=all --ignore-submodules=all
remote -v
config --no-includes --local --get core.sshCommand
config --no-includes --worktree --get core.sshCommand
config --no-includes --local --name-only --get-regexp ^url\.
config --no-includes --worktree --name-only --get-regexp ^url\.
config --no-includes --local --name-only --get-regexp ^credential\.helper$
config --no-includes --worktree --name-only --get-regexp ^credential\.helper$
```

Construct the subprocess environment from a small allowlist rather than copying `os.environ`: fixed `PATH=/usr/bin:/bin`, `LANG=C`, `LC_ALL=C`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, and no inherited `GIT_*`, SSH-agent, askpass, pager, or credential variables. The wrapper rejects every argv not matching the full grammar with `InspectionError("READ_ONLY_COMMAND_REFUSED")` before child creation. Do not emit raw stdout/stderr on error.

`explicit_machine_identity=True` only when the local/worktree `core.sshCommand` (or service definition evidence later) visibly selects an SSH identity path and includes `IdentitiesOnly=yes`; never infer this from an SSH URL alone. `ambient_fallback_possible=True` if the observed local SSH command lacks `IdentitiesOnly=yes` or allows an agent, or if local/worktree URL rewrites/credential helpers are present. Raw remote and config values are used only to derive booleans plus the bounded `remote_states` enum values `canonical_ssh`, `canonical_https_anon`, `wrong_owner`, `other`, and `unknown`; the values themselves are discarded before evidence construction. `write_capability_observed` remains `False` in Wave 1 because the inspector does not test writes.

`FETCH_HEAD` is inspected only with `Path.stat()`; if absent, return `None`.

- [ ] **Step 5: Verify GREEN**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

Expected: remote classification + local repository evidence tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/inspect_m1_macro_consumers.py tests/test_m1_macro_consumer_inspector.py
git commit -m "feat(ops): report M1 Macro checkout identity"
```

---

### Task 4: Assemble the bounded host census, JSON/table output, and fail-closed exit semantics

**Files:**
- Modify: `scripts/inspect_m1_macro_consumers.py`
- Modify: `tests/test_m1_macro_consumer_inspector.py`

**Interfaces:**
- Produces: `build_report(plist_paths: Sequence[Path], *, launchctl_disabled_output: str, launchctl_probe: Callable[[str], tuple[bool | None, bool | None, bool | None]], hostname: str, now: datetime) -> CensusReport`
- Produces: `probe_launchctl(label: str, *, uid: int = os.getuid(), run_launchctl: Callable[..., CompletedProcess[str]] = _run_launchctl) -> tuple[bool | None, bool | None, bool | None]`
- Produces CLI: `python3 scripts/inspect_m1_macro_consumers.py --plist <path> [--plist <path> ...] --format json|table`
- Exit `0`: complete read-only census with no inspection errors.
- Exit `65`: malformed/ambiguous/incomplete evidence; still emits the bounded report to stdout when possible.
- CLI has no mutation verbs.

- [ ] **Step 1: Write failing JSON schema and deterministic-order tests**

Build two synthetic plists in reverse input order and monkeypatch checkout/launchctl probes. Assert parsed JSON has:

```python
assert payload["schema"] == "macro.m1_consumer_census.v1"
assert payload["observed_at"].endswith("+00:00")
assert [row["service_id"] for row in payload["services"]] == sorted(...)
assert "classification" not in json.dumps(payload)
assert "KEEP_AUTHENTICATE" not in json.dumps(payload)
```

Assert `environment_names` contains only names and no fixture secret values.

- [ ] **Step 2: Write failing incomplete-evidence tests**

Cases:

1. malformed plist → report contains `PLIST_INVALID`, exit 65;
2. duplicate disabled-state rows → `LAUNCHCTL_DISABLED_STATE_INVALID`, exit 65;
3. inaccessible checkout candidate → service remains present with `inspection_errors`, exit 65;
4. clean complete census → exit 0.

- [ ] **Step 3: Write failing retired-breadth state test**

For `com.macro.live-breadth`, feed `=> disabled` plus a launchctl probe returning `(loaded=False, active=False, enabled=False)` and assert the report preserves:

```python
service.enabled is False
service.loaded is False
service.disabled_observed_state == "disabled"
```

The inspector must not label it `RETIRE_DUPLICATE` or `PROVEN_LIVE`.

- [ ] **Step 3a: Write failing production launchctl-wrapper tests**

Mock child creation and assert exact argv for a valid label:

```text
/bin/launchctl print-disabled gui/<uid>
/bin/launchctl print gui/<uid>/<label>
```

Assert label injection (`/`, whitespace, shell metacharacters, oversized labels), a non-`gui/<decimal-uid>` domain, mutation verbs, missing/duplicate `state = ...` rows, oversized output, timeout, and unexpected nonzero exits all raise a bounded `InspectionError` without starting an unapproved child. An exact supported native service-missing result may map to `(loaded=False, active=False, enabled=<disabled parser result>)`; every other nonzero result remains incomplete evidence. Raw launchctl stderr is never copied into the report.

- [ ] **Step 4: Run tests and verify RED**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

- [ ] **Step 5: Implement report assembly and CLI**

CLI must require explicit plist inputs in v1. Do **not** implement an unbounded `/Library/LaunchAgents` recursive scan. The production operator can derive the bounded input set with an explicit shell glob/list after a read-only census; future automatic discovery can be separately reviewed if needed.

`probe_launchctl` uses `/bin/launchctl`, `shell=False`, a five-second timeout, the same bounded-output discipline as Git, and a fixed `PATH`/locale environment with no inherited `DYLD_*` or other loader/control variables. `print` output must contain exactly one parseable `state = ...` row when the service is loaded; `active=True` only for exact `running`, `active=False` for a single recognized non-running native state, and otherwise `None` plus an inspection error. `enabled` is derived only from the exact `print-disabled` parser, never from process activity.

Use `json.dumps(asdict(report), sort_keys=True, indent=2)` for JSON. Table columns are a projection of the same report model only:

```text
SERVICE | LOADED | DISABLED | CHECKOUT | REMOTE_STATE | LAST_EXECUTION | HAZARDS
```

`REMOTE_STATE` is one of evidence-only values: `canonical_ssh`, `canonical_https_anon`, `wrong_owner`, `other`, `unknown`.

- [ ] **Step 6: Verify focused suite GREEN**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

- [ ] **Step 7: Compile and CLI-help smoke**

```bash
python -m py_compile scripts/inspect_m1_macro_consumers.py
python scripts/inspect_m1_macro_consumers.py --help
```

Expected: compile succeeds; help exposes only read-only inspection options.

- [ ] **Step 8: Commit**

```bash
git add scripts/inspect_m1_macro_consumers.py tests/test_m1_macro_consumer_inspector.py
git commit -m "feat(ops): emit bounded M1 consumer census"
```

---

### Task 5: Extend the existing repository fence to old-owner Git transports

**Files:**
- Modify: `scripts/check_macro_anon_dependency.py`
- Modify: `tests/test_macro_anon_dependency_guard.py`

**Interfaces:**
- Existing `find_anonymous_macro_dependencies(text: str, path: str) -> list[Finding]` remains the public test seam.
- Add finding shape `wrong_owner_transport`.
- No broad ban on `chriswong6031-creator` citations.

- [ ] **Step 1: Write failing non-vacuity tests for old-owner SSH transport**

Add:

```python
@pytest.mark.parametrize(
    "snippet",
    [
        'REMOTE = "git@github.com:chriswong6031-creator/macro.git"\n',
        'REMOTE = "git@github.com:chriswong6031-creator/macro/"\n',
        'REMOTE = "ssh://git@github.com/chriswong6031-creator/macro.git"\n',
        'REMOTE = "ssh://git@github.com/chriswong6031-creator/macro/"\n',
        'git remote set-url origin git@github.com:chriswong6031-creator/macro.git\n',
    ],
)
def test_old_owner_git_transport_is_flagged(snippet: str) -> None:
    findings = find_anonymous_macro_dependencies(snippet, "scripts/synthetic.sh")
    assert "wrong_owner_transport" in _shapes(findings)
```

- [ ] **Step 2: Write failing precision tests**

```python
@pytest.mark.parametrize(
    "snippet",
    [
        'REMOTE = "git@github.com:mastermindx-market-intelligence/macro.git"\n',
        'PR = "https://github.com/chriswong6031-creator/macro/pull/6363"\n',
        'CMT = "https://github.com/chriswong6031-creator/macro/commit/deadbeef"\n',
        'OTHER = "git@github.com:chriswong6031-creator/not-macro.git"\n',
    ],
)
def test_canonical_ssh_and_human_old_owner_citations_are_not_wrong_owner_transport(snippet: str) -> None:
    findings = find_anonymous_macro_dependencies(snippet, "scripts/synthetic.sh")
    assert "wrong_owner_transport" not in _shapes(findings)
```

- [ ] **Step 3: Run only the new fence tests and verify RED**

```bash
python -m pytest tests/test_macro_anon_dependency_guard.py -q
```

Expected: the old-owner SSH cases are not yet classified as `wrong_owner_transport`.

- [ ] **Step 4: Implement the minimal transport-specific regex**

Add a pattern keyed only to the old owner + `macro` repo, for SCP and SSH URL forms:

```python
_OLD_OWNER = re.escape("chriswong6031-creator")

"wrong_owner_transport": re.compile(
    rf"(?:git@github\.com:{_OLD_OWNER}/{_REPO}(?:\.git)?/?|"
    rf"ssh://git@github\.com/{_OLD_OWNER}/{_REPO}(?:\.git)?/?)"
    rf"(?=[\"'\s]|$)"
),
```

Do not add `chriswong6031-creator` as a generic banned string. Existing HTTP old-owner repo-root detection remains in the current anonymous rule.

- [ ] **Step 5: Run the complete guard suite**

```bash
python -m pytest tests/test_macro_anon_dependency_guard.py -q
```

Expected: all existing precision/non-vacuity/allowlist tests plus new transport tests pass.

- [ ] **Step 6: Run the guard itself**

```bash
python scripts/check_macro_anon_dependency.py
```

Expected: exit 0 on the implementation tree; any real newly exposed wrong-owner executable/config occurrence is a finding to investigate, not automatically allowlist.

- [ ] **Step 7: Commit**

```bash
git add scripts/check_macro_anon_dependency.py tests/test_macro_anon_dependency_guard.py
git commit -m "fix(security): fence old-owner Macro Git transports"
```

---

### Task 6: Add the operator runbook and prove the implementation stays read-only

**Files:**
- Create: `docs/M1_MACRO_CONSUMER_INSPECTION_RUNBOOK.md`
- Modify: `tests/test_m1_macro_consumer_inspector.py`

**Interfaces:**
- Runbook command uses explicit plist paths and writes output only to operator-chosen stdout/file redirection.
- No runtime mutation command appears in the normal procedure.

- [ ] **Step 1: Add failing runtime command-refusal tests, then retain a source-level tripwire**

Mock the subprocess constructor and call the Git and launchctl wrappers with every prohibited operation: Git `fetch`, `pull`, `reset`, `clean`, `checkout`, `remote set-url`, malformed `config`, a `status` suffix that removes `--ignore-submodules=all`, and launchctl `enable`, `disable`, `bootstrap`, `bootout`, and `kickstart`. Assert each call raises `InspectionError("READ_ONLY_COMMAND_REFUSED")` and the mock child was never called. Also prove inherited `GIT_*`, `SSH_*`, `DYLD_*`, askpass, pager, and credential variables never enter the child environment.

Keep this source-level test as a secondary regression tripwire:

```python
def test_inspector_source_contains_no_mutating_launchctl_or_git_verbs() -> None:
    text = (REPO_ROOT / "scripts" / "inspect_m1_macro_consumers.py").read_text()
    for token in (
        "launchctl enable",
        "launchctl disable",
        "launchctl bootstrap",
        "launchctl bootout",
        "launchctl kickstart",
        '"fetch"',
        '"pull"',
        '"reset"',
        '"clean"',
        '"checkout"',
        '"remote", "set-url"',
    ):
        assert token not in text
```

If quoting causes a false positive in documentation strings, move the subprocess argv allowlist into a constant and assert the constant equals the explicit read-only verb set instead of weakening the test.

- [ ] **Step 2: Run the inspector suite and verify the runtime refusal tests fail before the grammar is explicit**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py -q
```

- [ ] **Step 3: Make the complete read-only Git/launchctl argv grammars explicit in production code**

Expose immutable full-prefix/suffix specifications rather than trusting only the first verb. At minimum, the wrappers must bind the absolute executables and the fixed safety prefixes described in Tasks 3–4; the allowed command suffixes remain explicit immutable tuples. A first-token-only allowlist is insufficient because `remote set-url` and malformed `config` share otherwise allowed first verbs.

Diagnostic constants may still summarize the allowed verbs:

```python
_ALLOWED_GIT_COMMANDS = frozenset({"rev-parse", "symbolic-ref", "status", "remote", "config"})
_ALLOWED_LAUNCHCTL_COMMANDS = frozenset({"print", "print-disabled"})
```

The subprocess wrapper must refuse anything outside the complete grammar with `InspectionError("READ_ONLY_COMMAND_REFUSED")` before child creation.

- [ ] **Step 4: Write the runbook with exact production procedure**

`docs/M1_MACRO_CONSUMER_INSPECTION_RUNBOOK.md` must contain:

1. purpose and authority boundary;
2. preflight: re-pin Skillpack/current Macro head and re-read #6432;
3. explicit warning that output is evidence, not `KEEP_AUTHENTICATE`/`RETIRE_DUPLICATE` authority;
4. exact example invocation:

```bash
python3 scripts/inspect_m1_macro_consumers.py \
  --plist "$HOME/Library/LaunchAgents/com.mastermind.optionshub.plist" \
  --plist "$HOME/Library/LaunchAgents/com.mastermind.levelsseal.plist" \
  --plist "$HOME/Library/LaunchAgents/com.mastermind.levelsgrader.plist" \
  --plist "$HOME/Library/LaunchAgents/com.macro.live-breadth.plist" \
  --format json > /tmp/m1-macro-consumer-census.json
```

The example is illustrative; operator must re-census current relevant plist names before proof and must not assume this list is exhaustive.

5. JSON/table field meanings;
6. exit 65 meaning “incomplete/ambiguous evidence — STOP for Sol”; 
7. secret-handling rules;
8. no-mutation law;
9. `flow-ops-wt` special preservation rule;
10. current native disabled-state compatibility (`true` and `disabled` accepted);
11. #6432 return packet fields: exact code head, command, host/time, census SHA-256, services discovered, unresolved inspection errors, evidence-only hazards, confirmation of zero host mutation.

- [ ] **Step 5: Run focused suites and compile**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py tests/test_macro_anon_dependency_guard.py -q
python -m py_compile scripts/inspect_m1_macro_consumers.py scripts/check_macro_anon_dependency.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/M1_MACRO_CONSUMER_INSPECTION_RUNBOOK.md scripts/inspect_m1_macro_consumers.py tests/test_m1_macro_consumer_inspector.py
git commit -m "docs(ops): define M1 consumer inspection procedure"
```

---

### Task 7: Full repository validation, adversarial review, and immutable implementation return

**Files:**
- No new scope unless a test/review defect directly concerns Wave 1 files.

**Interfaces:**
- Produces an immutable PR head for Sol review.
- Does not run the M1 production census until implementation has passed Sol code review/merge gate.

- [ ] **Step 1: Re-pin collision state before opening the implementation PR**

Read current:

```text
protected Skillpack master SHA
Macro main SHA
open PRs touching:
  scripts/inspect_m1_macro_consumers.py
  scripts/check_macro_anon_dependency.py
  tests/test_m1_macro_consumer_inspector.py
  tests/test_macro_anon_dependency_guard.py
  docs/M1_MACRO_CONSUMER_INSPECTION_RUNBOOK.md
#6432 / MAS-137 state
```

If a colliding carrier exists, stop for Sol; do not rebase/reset over it.

- [ ] **Step 2: Run the discriminating local pack**

```bash
python -m pytest tests/test_m1_macro_consumer_inspector.py tests/test_macro_anon_dependency_guard.py -q
python -m py_compile scripts/inspect_m1_macro_consumers.py scripts/check_macro_anon_dependency.py
python scripts/check_macro_anon_dependency.py
python3 scripts/agentos.py validate
```

Expected: all commands exit 0; Agent OS may have pre-existing warnings but zero errors.

- [ ] **Step 3: Run broader repository CI selected by current authority**

Do not invent a new CI workflow. Push/open the PR and use existing `ci`, `fences`, and `ci-authority` semantics. Record exact run IDs and conclusions for the immutable head.

- [ ] **Step 4: Adversarial review against the design**

Reviewer must explicitly try to falsify:

- inspector can trigger/mutate launchd;
- inspector can run network Git operations;
- repository-local `core.fsmonitor`, hooks, submodule recursion, or inherited `GIT_*`/loader variables can execute host code during inspection;
- output can leak env/key/token values;
- raw remote URLs or credential-helper values can reach JSON, table output, errors, or diagnostics;
- malformed launchctl labels/domains or a first-verb-only allowlist can escape the fixed argv grammar;
- `=> disabled` is misread as enabled/unknown;
- malformed duplicate launchctl rows are accepted;
- canonical org SSH is falsely rejected;
- old-owner PR/commit citations are falsely rejected;
- old-owner SCP/SSH acquisition target escapes the fence;
- output invents organizational classifications;
- filesystem discovery becomes an unbounded crawl;
- `flow-ops-wt` receives any write;
- new registry/credential/control plane was introduced.

Any material failure returns to the same PR for bounded repair; no second carrier.

- [ ] **Step 5: Return to Sol with immutable implementation packet**

Return:

```text
Skillpack pin
Macro base and implementation head
changed files
focused test command + result
Agent OS validate result
hosted CI/fences/authority run IDs + conclusions
adversarial review verdict
proof that no M1/runtime mutation occurred
exact command proposed for real M1 proof
known gaps/collisions
```

STOP. Do not run the real M1 proof merely because CI is green unless the commission/PR explicitly authorizes that proof step.

---

### Task 8: After Sol accepts/merges Wave 1, obtain one real read-only M1 census receipt

**Files:**
- No implementation files unless the real proof exposes a defect; defects return to a bounded repair PR under the same logical Wave 1 carrier.
- Durable Agent OS closeout is a separate records commit/PR only after Sol accepts the proof.

**Interfaces:**
- Input: exact merged Wave 1 implementation SHA installed/read on M1 without altering service state.
- Output: census JSON digest + concise #6432 receipt.

- [ ] **Step 1: Re-pin current authority and prove the implementation bytes used on M1**

Record current protected Skillpack, current Macro main, exact inspector blob/hash, M1 hostname/hardware identity, and wall-clock timestamp.

- [ ] **Step 2: Run only read-only preflight**

Confirm no target service is being mutated by another carrier. Confirm `com.macro.live-breadth` remains disabled/unloaded. Do not repair anything in this step.

- [ ] **Step 3: Run the bounded census**

Use the runbook with the current explicit relevant plist set and save JSON to a temporary operator path. Compute:

```bash
shasum -a 256 /tmp/m1-macro-consumer-census.json
```

- [ ] **Step 4: Validate the receipt itself**

Require:

- schema exactly `macro.m1_consumer_census.v1`;
- all explicitly supplied services represented;
- environment names only, no secret values;
- no inspection errors for a `complete_for_cutover=true` result;
- retired breadth shows disabled/unloaded without an organizational classification;
- `flow-ops-wt` identity is observed only, not mutated;
- current `hub-ops-wt`, `theta-ops-wt`, `fund-engine-wt`, and any newly discovered active/recent dependencies are surfaced for Sol classification where applicable;
- shell history/service state/Git state comparison shows zero mutation attributable to the inspector.

- [ ] **Step 5: Post the evidence to #6432 and return to Sol**

Post exact code SHA, host/time, invocation shape (no secrets), JSON SHA-256, service count, hazards/unknowns, and `complete_for_cutover` value. Do not perform Wave 2 authentication/retirement acts in the same proof step.

- [ ] **Step 6: Close Wave 1 organizationally only on Sol PASS**

On Sol PASS, update the correct Agent OS workstream/discovery/handoff and MAS-137 projection to state that M1 consumer visibility is `PROVEN_LIVE`; immediately name Wave 2’s first classification/collision action. If proof is incomplete, keep Wave 1 `BUILT_NOT_PROVEN` or `PARTIAL` as appropriate.

---

## Plan Self-Review Results

- **Spec coverage:** Wave 1 covers Component A (host inspector) and Component B (wrong-owner fence), including secret safety, launchd disabled-state compatibility, ephemeral evidence, no organizational authority, bounded discovery, read-only proof, and no M1 mutation. Components C/D migration/proof are deliberately deferred to later plans except that this wave creates the evidence needed to commission them.
- **Placeholder scan:** no `TBD`, `TODO`, “similar to”, or unspecified error-handling steps remain.
- **Type consistency:** Task 1 dataclasses and `parse_launchctl_disabled` feed Tasks 2–4; Task 3 `classify_remote` feeds report assembly; fence retains its current `Finding` interface with one new `wrong_owner_transport` shape.
- **Scope check:** Wave 1 is independently useful and testable. It does not implement authenticated consumer migration, natural publisher verification, runner/storage work, trusted CI, or repository visibility changes.

## Execution Choice

Recommended: **Subagent-/operator-driven execution** because this is a bounded implementation with a strong written contract and an important independent review gate. A fresh worker should implement Tasks 1–7; Sol then performs immutable-head review and authorizes Task 8 read-only M1 proof. Inline execution is acceptable only if the session can maintain the same TDD and review separation.
