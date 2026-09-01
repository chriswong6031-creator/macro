# CI L3 Immutable Dependency Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-pack unpinned network dependency resolution with an immutable, execution-identity-bound Python dependency contract that can be consumed from a trusted read-only cache or, when necessary, fetched from the network using the exact same hashes.

**Architecture:** This is the executable expansion of Wave L3 in `docs/superpowers/plans/2026-08-26-ci-scope-latency-modernization.md`, not a new latency program. Preserve `legacy-jobs.yml`, `run_ci_pack.py`, `ci.pack_plan.v2`, semantic fragments, and `ci-gate`; add one checked-in dependency lock whose group digest is bound into the existing `job_exec_sha256`, one root-owned dependency cache beside the existing Git object cache, and one fresh writable venv per dependency group. Cache misses may use the network only through the same checked-in hashes and must never fall back to the manifest's raw unpinned `pip install` command.

**Tech Stack:** Python 3.12.13, pip `--report` / `--require-hashes`, GitHub Actions, existing `scripts/run_ci_pack.py`, existing `scripts/ci_semantic_proof.py`, pytest, root-owned Linux cache paths.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md` and existing L3 owner `docs/superpowers/plans/2026-08-26-ci-scope-latency-modernization.md`.

## Global Constraints

- Do not start implementation until architecture PR #6717 is merged and the current C3R-A receipt changes are either merged or explicitly proven path-disjoint on the fresh base.
- Re-pin current protected Mastermind Skillpack, current Macro `main`, current `RUNNER_CONTRACT`, and all open PRs touching the files below before START and before push.
- The dependency lock is an execution input, not a second semantic plan. `ci-plan` remains selection/partition authority and `ci-gate` remains aggregate authority.
- `ci.pack_plan.v2`, `ci.semantic_fragment.v1`, and `ci.semantic_evidence.v1` are not widened merely to carry cache telemetry.
- A dependency cache hit may improve speed but may not change the selected logical jobs, proof IDs, failed-set, or semantic result.
- Candidate jobs may read the trusted dependency cache but may never mutate it.
- Missing/corrupt/stale cache state uses the exact checked-in hash lock over a network path or fails explicitly; it never executes the raw unpinned manifest command and calls that equivalent.
- The raw manifest dependency command remains part of execution identity; the new lock digest is additional identity, not a replacement.
- Preserve the current single classified dependency-transport retry law only for the exact locked network fallback; do not add an automatic semantic-job retry.
- No result reuse, pack-count change, ownership narrowing, fourth-slot host work, JIT/cloud work, new scheduler, queue, retry ledger, proof store, or cache database enters this carrier.

---

### Task 1: Define and validate the immutable dependency lock

**Files:**
- Create: `scripts/ci_dependency_lock.py`
- Create: `config/ci_dependency_lock.v1.json`
- Create: `tests/test_ci_dependency_lock.py`
- Modify: `tests/test_ci_pack.py`

**Interfaces:**
- Consumes: `scripts.run_ci_pack.load_legacy_jobs()` and `scripts.run_ci_pack.dependency_command(job)` from the current manifest.
- Produces: `DependencyLock`, `DependencyGroup`, `load_dependency_lock(path)`, `dependency_group_for_command(lock, install_command, runner_contract)`, and CLI `resolve|verify|render-requirements`.

- [ ] **Step 1: Write the lock-model tests first**

Add these exact contract tests in `tests/test_ci_dependency_lock.py`:

```python
from pathlib import Path
import json
import pytest

from scripts import ci_dependency_lock as LOCK


def _doc() -> dict:
    requirements = [
        {"name": "pytest", "version": "9.0.2", "sha256": "1" * 64},
        {"name": "pluggy", "version": "1.6.0", "sha256": "2" * 64},
    ]
    lock_sha = LOCK.requirement_set_sha256(requirements)
    return {
        "schema": "ci.dependency_lock.v1",
        "runner_contract": "linux-x86_64/python-3.12.13/node-20",
        "groups": [{
            "install_command": "pip install pytest",
            "requirements": requirements,
            "lock_sha256": lock_sha,
        }],
    }


def test_group_identity_binds_command_runner_and_requirements(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    lock = LOCK.load_dependency_lock(path)
    group = LOCK.dependency_group_for_command(
        lock,
        "pip install pytest",
        "linux-x86_64/python-3.12.13/node-20",
    )
    assert group.group_id == LOCK.dependency_group_id(
        group.install_command, group.runner_contract, group.lock_sha256
    )


def test_lock_rejects_missing_hash_and_duplicate_distribution(tmp_path: Path) -> None:
    doc = _doc()
    doc["groups"][0]["requirements"].append(
        {"name": "PyTest", "version": "9.0.2", "sha256": "3" * 64}
    )
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(LOCK.DependencyLockError, match="duplicate distribution"):
        LOCK.load_dependency_lock(path)


def test_every_manifest_dependency_command_is_locked() -> None:
    findings = LOCK.verify_manifest_lock(
        Path(".github/ci/legacy-jobs.yml"),
        Path("config/ci_dependency_lock.v1.json"),
    )
    assert findings == []
```

Also add one mutation in `tests/test_ci_pack.py` proving a new manifest `pip install` command without a lock entry fails the dependency-lock guard rather than silently resolving live.

- [ ] **Step 2: Run the new tests and confirm RED**

Run:

```bash
python3.12 -m pytest -q tests/test_ci_dependency_lock.py tests/test_ci_pack.py -k "dependency_lock or locked"
```

Expected: import/file failures because `ci_dependency_lock.py` and the lock file do not exist.

- [ ] **Step 3: Implement the closed data model and canonical digests**

Create `scripts/ci_dependency_lock.py` with this public surface:

```python
SCHEMA = "ci.dependency_lock.v1"
HEX64 = re.compile(r"[0-9a-f]{64}")

@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    sha256: str

@dataclass(frozen=True)
class DependencyGroup:
    group_id: str
    install_command: str
    runner_contract: str
    requirements: tuple[LockedRequirement, ...]
    lock_sha256: str

@dataclass(frozen=True)
class DependencyLock:
    schema: str
    runner_contract: str
    groups: tuple[DependencyGroup, ...]
    document_sha256: str

class DependencyLockError(ValueError):
    pass


def canonical_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_set_sha256(requirements: Sequence[Mapping[str, str]]) -> str:
    normalized = sorted(
        {
            "name": canonical_distribution(str(item["name"])),
            "version": str(item["version"]),
            "sha256": str(item["sha256"]).lower(),
        }
        for item in requirements
    )
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def dependency_group_id(
    install_command: str, runner_contract: str, lock_sha256: str
) -> str:
    payload = json.dumps(
        {
            "install_command": install_command,
            "runner_contract": runner_contract,
            "lock_sha256": lock_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "dep-" + hashlib.sha256(payload.encode()).hexdigest()[:24]
```

`load_dependency_lock()` must reject unknown top-level/group/requirement keys, non-canonical duplicate names, empty versions, non-64-hex hashes, duplicate commands, mismatched `lock_sha256`, wrong schema, and wrong current runner contract. `dependency_group_for_command()` returns exactly one group or raises `DependencyLockError`.

- [ ] **Step 4: Implement deterministic resolver and renderer CLI**

The `resolve` command must enumerate unique standalone manifest dependency commands, create a clean temporary venv with Python 3.12.13, and for each command use pip's JSON report rather than scraping text:

```bash
python -m pip install --dry-run --ignore-installed --report "$report" <original requirement args>
```

For every install item, require `metadata.name`, `metadata.version`, and `download_info.archive_info.hash` of the form `sha256=<hex>`. Reject VCS/editable/local-path entries or report rows with no SHA-256. Sort requirements by canonical name and serialize the document with `sort_keys=True, indent=2` plus trailing newline.

`render-requirements --group <id>` prints only lines of this exact shape:

```text
pluggy==1.6.0 --hash=sha256:<64hex>
pytest==9.0.2 --hash=sha256:<64hex>
```

`verify` must call `verify_manifest_lock()` and exit 2 with one line-start `::error` per missing/stale command.

- [ ] **Step 5: Resolve the real current manifest once and review the checked-in lock**

Run on the exact L3 carrier's Linux/x86_64 Python-3.12.13 environment:

```bash
python3.12 scripts/ci_dependency_lock.py resolve \
  --workflow .github/ci/legacy-jobs.yml \
  --output config/ci_dependency_lock.v1.json
python3.12 scripts/ci_dependency_lock.py verify \
  --workflow .github/ci/legacy-jobs.yml \
  --lock config/ci_dependency_lock.v1.json
python3.12 -m pytest -q tests/test_ci_dependency_lock.py tests/test_ci_pack.py -k "dependency_lock or locked"
git diff --check
```

Expected: every unique manifest dependency command has exactly one immutable group; verify and tests pass. Review the generated versions/hashes as code—do not accept an unexplained resolver jump merely because JSON is valid.

- [ ] **Step 6: Commit the lock contract**

```bash
git add scripts/ci_dependency_lock.py config/ci_dependency_lock.v1.json \
  tests/test_ci_dependency_lock.py tests/test_ci_pack.py
git commit -m "ci: freeze immutable dependency lock"
```

---

### Task 2: Bind the dependency lock into semantic execution identity

**Files:**
- Modify: `scripts/ci_semantic_proof.py`
- Modify: `scripts/run_ci_pack.py`
- Modify: `tests/test_ci_semantic_proof.py`
- Modify: `tests/test_ci_pack_semantic.py`
- Modify: `tests/test_ci_dependency_lock.py`

**Interfaces:**
- Consumes: `DependencyGroup.lock_sha256` from Task 1.
- Produces: `job_exec_sha256(..., dependency_lock_sha256=...)` and `execution_profile_id(runner_contract, dependency_lock_document_sha256)`.

- [ ] **Step 1: Write RED semantic-identity mutation tests**

Extend `tests/test_ci_semantic_proof.py`:

```python
def test_job_digest_binds_dependency_lock_digest() -> None:
    base = proof.job_exec_sha256(
        dependency_install_command="pip install pytest",
        dependency_lock_sha256="a" * 64,
        timeout_minutes=10,
        runner_contract="linux-x86_64/python-3.12.13/node-20",
    )
    changed = proof.job_exec_sha256(
        dependency_install_command="pip install pytest",
        dependency_lock_sha256="b" * 64,
        timeout_minutes=10,
        runner_contract="linux-x86_64/python-3.12.13/node-20",
    )
    assert base != changed
```

Add a no-dependency control using `dependency_install_command=None` and `dependency_lock_sha256=None`, and a failure test that a dependency command paired with `None` lock digest is refused by `run_ci_pack.semantic_job_digest()`.

- [ ] **Step 2: Run and confirm RED on the old function signature**

```bash
python3.12 -m pytest -q tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py \
  tests/test_ci_dependency_lock.py -k "dependency or job_digest or execution_profile"
```

Expected: `job_exec_sha256()` rejects the new keyword and pack identity lacks lock binding.

- [ ] **Step 3: Extend `job_exec_sha256` with one explicit nullable field**

Change only the existing digest payload:

```python
def job_exec_sha256(
    *,
    dependency_install_command: str | None,
    dependency_lock_sha256: str | None,
    timeout_minutes: object,
    runner_contract: str,
) -> str:
    return canonical_sha256({
        "dependency_install_command": dependency_install_command,
        "dependency_lock_sha256": dependency_lock_sha256,
        "timeout_minutes": timeout_minutes,
        "runner_contract": runner_contract,
    })
```

Update every callsite/test explicitly. Do not hide the new digest by concatenating it into prose-only telemetry.

- [ ] **Step 4: Make `semantic_job_digest()` load the lock deterministically**

At module load, keep the current manifest as semantic source and load `config/ci_dependency_lock.v1.json` through Task 1's validator. For a job with no dependency command pass `None`; otherwise resolve exactly one group and pass its `lock_sha256`.

Add:

```python
def execution_profile_id(runner_contract: str, lock_document_sha256: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "runner_contract": runner_contract,
                "dependency_lock_document_sha256": lock_document_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return f"ci-linux-x64-{digest[:20]}"
```

This is the profile identity consumed later by C3 receipts and EC1 AMI attestation. It is derived from existing runner law plus the lock; it is not another routing authority.

- [ ] **Step 5: Prove plan and fragment semantics change only where expected**

Run:

```bash
python3.12 -m pytest -q tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
```

Expected: all semantic tests pass; dependency-bearing jobs receive new `job_exec_sha256` values; step proof IDs and selected-job inventory do not change from lock binding alone.

- [ ] **Step 6: Commit semantic binding**

```bash
git add scripts/ci_semantic_proof.py scripts/run_ci_pack.py \
  tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py tests/test_ci_dependency_lock.py
git commit -m "ci: bind dependency lock into execution identity"
```

---

### Task 3: Build and validate the root-owned read-only dependency cache

**Files:**
- Create: `ops/runner-host/pc/mastermind_ci_dependency_cache.py`
- Create: `tests/test_ci_dependency_cache.py`
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`

**Interfaces:**
- Consumes: Task 1 lock groups.
- Produces: cache root `/var/cache/mastermind-ci/python`, marker schema `mastermind.ci_dependency_cache.v1`, CLI `build-group`, `verify-group`, `verify-all`.

- [ ] **Step 1: Write RED cache ownership/hash tests**

Test a fixture directory with this exact marker contract:

```json
{
  "schema": "mastermind.ci_dependency_cache.v1",
  "group_id": "dep-...",
  "lock_sha256": "...",
  "runner_contract": "linux-x86_64/python-3.12.13/node-20",
  "files": {"pytest-9.0.2-py3-none-any.whl": "<sha256>"}
}
```

Tests must reject: wrong owner UID, group/world-writable cache/marker/wheel, missing wheel, extra unrecorded wheel, wrong wheel SHA, wrong group/lock/runner identity, and symlinks escaping the group directory.

- [ ] **Step 2: Implement `build-group` as a trusted updater only**

`build-group` renders Task 1 requirements into a temporary file and executes:

```bash
python3.12 -m pip download --only-binary=:all: --require-hashes \
  --dest "$staging" -r "$requirements"
```

Hash every downloaded file, require one verified artifact for each locked distribution, write the marker atomically, set directories `0755` and files/marker `0444`, then atomically rename staging to `<cache-root>/<group_id>`. Refuse to run when effective UID is not the configured trusted cache owner.

Candidate execution never calls `build-group`.

- [ ] **Step 3: Implement `verify-group` and `verify-all` with no network fallback**

`verify-group` reads only local bytes and exits 66 on any identity/permission/hash defect. `verify-all` walks exactly the groups in the checked-in lock; an extra unknown cache group is diagnostic but cannot satisfy a job.

- [ ] **Step 4: Run fixture proof and document deployment ownership**

```bash
python3.12 -m pytest -q tests/test_ci_dependency_cache.py
python3.12 ops/runner-host/pc/mastermind_ci_dependency_cache.py verify-all \
  --lock config/ci_dependency_lock.v1.json \
  --cache-root /tmp/mastermind-ci-dependency-cache-fixture \
  --expected-owner-uid "$(id -u)"
git diff --check
```

Document that production cache mutation belongs to the same privileged host/admin deployment discipline as `/var/cache/mastermind-ci/macro.git`; no candidate workflow receives write permission.

- [ ] **Step 5: Commit cache substrate**

```bash
git add ops/runner-host/pc/mastermind_ci_dependency_cache.py \
  tests/test_ci_dependency_cache.py docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
git commit -m "ops: add immutable CI dependency cache"
```

---

### Task 4: Materialize fresh job environments from the lock, with exact fallback semantics

**Files:**
- Modify: `scripts/run_ci_pack.py`
- Modify: `tests/test_ci_pack.py`
- Modify: `tests/test_ci_dependency_cache.py`

**Interfaces:**
- Consumes: `DependencyGroup`, cache verifier, current `_child_environment()`.
- Produces: `DependencyMaterialization` and `materialize_dependency_environment()`.

- [ ] **Step 1: Write RED cache-hit/network-fallback/refusal tests**

Define the result type in tests first:

```python
@dataclass(frozen=True)
class DependencyMaterialization:
    env: dict[str, str]
    group_id: str | None
    lock_sha256: str | None
    source: str  # none | immutable_cache | pinned_network
```

Tests must prove:

1. a valid cache uses `--no-index --find-links=<group-dir> --require-hashes -r <rendered-lock>`;
2. cache bytes are unchanged before/after materialization;
3. a missing cache uses `--require-hashes -r <rendered-lock>` over the network;
4. a corrupt/mismatched cache is **not** treated as a hit and is reported before the pinned network path;
5. the raw manifest `pip install pytest ...` command is never executed after L3;
6. one classified dependency-transport retry destroys the partial venv and repeats the exact locked network command once;
7. non-transport failure is not retried;
8. each materialization creates a fresh writable venv under `RUNNER_TEMP`.

- [ ] **Step 2: Implement the materializer while preserving child-env law**

Add in `run_ci_pack.py`:

```python
@dataclass(frozen=True)
class DependencyMaterialization:
    env: dict[str, str]
    group_id: str | None
    lock_sha256: str | None
    source: str


def materialize_dependency_environment(
    install_command: str | None,
    *,
    dependency_lock: DependencyLock,
    dependency_cache_root: Path,
    changed_files_file: str | Path | None = None,
) -> DependencyMaterialization:
    ...
```

No-dependency jobs return `source="none"` and the ordinary child env. Dependency jobs create the fresh venv, render the locked requirements into `RUNNER_TEMP`, verify cache locally, then install either:

```text
python -m pip install --disable-pip-version-check --no-index \
  --find-links=<verified group dir> --require-hashes -r <requirements>
```

or the exact fallback:

```text
python -m pip install --disable-pip-version-check \
  --require-hashes -r <requirements>
```

The fallback may never recompute versions.

- [ ] **Step 3: Wire `_run_job` to use the materialization metadata**

Replace the old `_dependency_environment()` call. Keep dependency timing around the materialization so L1 timing remains comparable. If materialization raises, convert to the existing infrastructure `dependency_failed` result; do not alter semantic step failure classification.

- [ ] **Step 4: Run focused and full pack proof**

```bash
python3.12 -m pytest -q tests/test_ci_pack.py tests/test_ci_dependency_cache.py \
  tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
git diff --check
```

Expected: valid cache hit and pinned fallback fixtures both execute the same logical jobs and emit identical semantic outcomes; raw unpinned install is unreachable.

- [ ] **Step 5: Commit runtime consumption**

```bash
git add scripts/run_ci_pack.py tests/test_ci_pack.py tests/test_ci_dependency_cache.py
git commit -m "ci: materialize jobs from immutable dependencies"
```

---

### Task 5: Extend existing receipts and prove real latency/parity

**Files:**
- Modify after fresh C3 re-pin: `scripts/capture_ci_canary_receipt.py`
- Modify after fresh C3 re-pin: `tests/test_ci_canary_tools.py`
- Modify: `.github/workflows/trusted-ci-executor.yml`
- Modify: `.github/workflows/selfhosted-ci-canary.yml`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md` or current CI latency owner named by fresh main
- Create: one dated L3 handoff under `agentos/handoffs/`

**Interfaces:**
- Consumes: current post-C3 receipt schema, `DependencyMaterialization`, Task 2 execution profile ID.
- Produces: non-authoritative dependency provenance in the existing receipt/timing path and a named natural-traffic acceptance corpus.

- [ ] **Step 1: Fresh-reconcile the receipt API before editing it**

Fetch current main and inspect C3's landed receipt fields. Preserve `execution_profile_id`, `admission_policy_version`, queue timestamps, checkout/dependency/test/wall timing, cgroup/resource fields, and current schema migration law. If those fields differ materially from this plan's names, stop for Sol rather than creating parallel synonyms.

- [ ] **Step 2: Add RED receipt tests for dependency provenance**

Require nullable fields:

```json
{
  "dependency_group_id": "dep-...",
  "dependency_lock_sha256": "<64hex>",
  "dependency_source": "immutable_cache"
}
```

For jobs/packs with mixed groups, represent the existing receipt as a sorted `dependency_materializations` array keyed by logical job/group; do not flatten multiple groups into one false value. Absence is `null`/empty, not zero or `"unknown"` masquerading as observed.

Mutation tests prove these fields never enter semantic fragment hashing and cannot change `ci-gate`.

- [ ] **Step 3: Wire workflow artifact inputs without adding a new evidence plane**

Pass the materialization sidecar emitted by `run_ci_pack.py` into `capture_ci_canary_receipt.py` beside existing timing/resources. Upload only through the existing trusted receipt/timing artifacts. Do not create a dependency-results database or required merge check.

- [ ] **Step 4: Run exact-head deterministic proof**

```bash
python3.12 -m pytest -q \
  tests/test_ci_dependency_lock.py \
  tests/test_ci_dependency_cache.py \
  tests/test_ci_pack.py \
  tests/test_ci_semantic_proof.py \
  tests/test_ci_pack_semantic.py \
  tests/test_ci_canary_tools.py
python3.12 scripts/ci_dependency_lock.py verify \
  --workflow .github/ci/legacy-jobs.yml \
  --lock config/ci_dependency_lock.v1.json
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
python3.12 scripts/agentos.py validate
git diff --check
```

- [ ] **Step 5: Prove one cache-hit canary and one pinned-network negative control**

Using the existing self-hosted canary on a current non-destructive same-repo candidate:

1. run one selected dependency-bearing pack with the root-owned dependency group present;
2. prove `dependency_source=immutable_cache`, exact group/lock/profile identity, semantic parity with hosted control, and cache bytes unchanged;
3. in a separately authorized diagnostic negative-control environment with that group intentionally absent, run the same exact locked dependency contract and prove `dependency_source=pinned_network`; no raw manifest resolver is invoked;
4. do not mutate the production cache to manufacture the negative control.

- [ ] **Step 6: Accrue measured natural traffic and apply the L3 gate**

Use the existing execution-timing corpus. Freeze at least 20 natural dependency-bearing pack observations across ordinary PR final heads. Report p50/p95 for queue, checkout, dependency preparation, test, and wall time separately. L3 PASS requires:

- dependency preparation p95 < 60 seconds for cache-hit observations;
- zero same-SHA semantic mismatches attributable to dependency route;
- zero cache mutations by candidate jobs;
- zero unpinned network resolutions;
- exact lock/profile fields present on observed dependency packs.

If the p95 gate misses, do not widen cache authority or add more runners inside L3; return measured bottleneck to Sol/L5.

- [ ] **Step 7: Adversarial review, held PR, and continuation record**

Run independent review against the exact head. Keep the implementation PR DRAFT/HOLD-FOR-SOL. The return packet must name exact head/base, changed files, lock document SHA, number of dependency groups, exact-head CI/fences, cache-hit and negative-control run IDs, natural corpus p50/p95, and any packages that required special adjudication.

- [ ] **Step 8: Commit records only after evidence exists**

```bash
git add agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md agentos/handoffs/<exact-new-L3-handoff>.md
git commit -m "records: bank immutable dependency proof"
```

The actual handoff filename is chosen once from the current Agent OS date/grammar at execution and must pass `scripts/agentos.py validate`; do not pre-create an empty placeholder.

## Stop Condition

Stop and return to Sol before expanding scope if the real current manifest contains dependency commands pip cannot lock with exact SHA-256 artifacts for the Linux/x86_64 Python-3.12.13 profile, if C3/current semantic source changed enough to require a new proof schema, if any candidate write path would need cache mutation, or if parity requires pretending the cloud/persistent execution profiles are identical before evidence proves it.

## Completion Truth

Landing L3 means `IMMUTABLE_DEPENDENCY_EXECUTION = BUILT_NOT_PROVEN` until the natural cache-hit corpus passes. Passing that corpus makes the dependency execution profile `PROVEN_LIVE` for the current persistent Linux/x86_64 route. It does not enable JIT/cloud runners, result reuse, extra capacity, or broader ownership narrowing.