# CI L3 Immutable Dependency Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-pack unpinned network dependency resolution with an immutable, execution-identity-bound Python dependency contract that can be consumed from a trusted read-only cache or, when necessary, fetched from the network using the exact same hashes.

**Architecture:** This is the executable expansion of Wave L3 in `docs/superpowers/plans/2026-08-26-ci-scope-latency-modernization.md`, not a new latency program. Preserve `legacy-jobs.yml`, `run_ci_pack.py`, `ci.pack_plan.v2`, semantic fragments, and `ci-gate`; add one checked-in dependency lock whose group digest is bound into the existing `job_exec_sha256`, one root-owned dependency cache beside the existing Git object cache, and one fresh writable venv per dependency group. Cache misses may use the network only through the same checked-in hashes and must never fall back to the manifest's raw unpinned `pip install` command.

**Tech Stack:** Python 3.12.13, pip JSON reports / `--require-hashes`, GitHub Actions, existing `scripts/run_ci_pack.py`, existing `scripts/ci_semantic_proof.py`, pytest, root-owned Linux cache paths.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md` and existing L3 owner `docs/superpowers/plans/2026-08-26-ci-scope-latency-modernization.md`.

## Global Constraints

- Do not start implementation until architecture PR #6717 is merged and current C3 receipt changes are merged or explicitly proven path-disjoint on the fresh base.
- Re-pin current protected Mastermind Skillpack, Macro `main`, current `RUNNER_CONTRACT`, and all open PRs touching this plan's paths before START and before push.
- The dependency lock is an execution input, not a second semantic plan. `ci-plan` remains selection/partition authority and `ci-gate` remains aggregate authority.
- `ci.pack_plan.v2`, `ci.semantic_fragment.v1`, and `ci.semantic_evidence.v1` are not widened merely to carry cache telemetry.
- A dependency cache hit may improve speed but may not change selected logical jobs, proof IDs, failed-set, or semantic result.
- Candidate jobs may read the trusted dependency cache but never mutate it.
- Missing/corrupt/stale cache state uses the exact checked-in hash lock over a network path or fails explicitly; it never executes the raw unpinned manifest command and calls that equivalent.
- The raw manifest dependency command remains part of execution identity; the new lock digest is additional identity, not a replacement.
- Preserve the current single classified dependency-transport retry law only for the exact locked network fallback; do not add semantic-job retry.
- No result reuse, pack-count change, ownership narrowing, fourth-slot host work, JIT/cloud work, new scheduler, queue, retry ledger, proof store, or cache database enters L3.

---

### Task 1: Define and validate the immutable dependency lock

**Files:**
- Create: `scripts/ci_dependency_lock.py`
- Create: `config/ci_dependency_lock.v1.json`
- Create: `tests/test_ci_dependency_lock.py`
- Modify: `tests/test_ci_pack.py`

**Interfaces:**
- Consumes: `scripts.run_ci_pack.load_legacy_jobs()` and `scripts.run_ci_pack.dependency_command(job)`.
- Produces: `DependencyLock`, `DependencyGroup`, `load_dependency_lock(path)`, `dependency_group_for_command(...)`, and CLI `resolve|verify|render-requirements`.

- [ ] **Step 1: Write the lock-model tests first**

Add:

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
    return {
        "schema": "ci.dependency_lock.v1",
        "runner_contract": "linux-x86_64/python-3.12.13/node-20",
        "groups": [{
            "install_command": "pip install pytest",
            "requirements": requirements,
            "lock_sha256": LOCK.requirement_set_sha256(requirements),
        }],
    }


def test_group_identity_binds_command_runner_and_requirements(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    lock = LOCK.load_dependency_lock(path)
    group = LOCK.dependency_group_for_command(
        lock, "pip install pytest", "linux-x86_64/python-3.12.13/node-20"
    )
    assert group.group_id == LOCK.dependency_group_id(
        group.install_command, group.runner_contract, group.lock_sha256
    )


def test_lock_rejects_duplicate_distribution(tmp_path: Path) -> None:
    doc = _doc()
    doc["groups"][0]["requirements"].append(
        {"name": "PyTest", "version": "9.0.2", "sha256": "3" * 64}
    )
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(LOCK.DependencyLockError, match="duplicate distribution"):
        LOCK.load_dependency_lock(path)


def test_every_manifest_dependency_command_is_locked() -> None:
    assert LOCK.verify_manifest_lock(
        Path(".github/ci/legacy-jobs.yml"),
        Path("config/ci_dependency_lock.v1.json"),
    ) == []
```

Also add a mutation in `tests/test_ci_pack.py` proving a new manifest `pip install` command without a lock entry fails the dependency-lock guard rather than resolving live.

- [ ] **Step 2: Run and confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_dependency_lock.py tests/test_ci_pack.py -k "dependency_lock or locked"
```

Expected: import/file failures because the lock code/file do not exist.

- [ ] **Step 3: Implement the closed data model and canonical digests**

Create:

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
    normalized = [
        {
            "name": canonical_distribution(str(item["name"])),
            "version": str(item["version"]),
            "sha256": str(item["sha256"]).lower(),
        }
        for item in requirements
    ]
    normalized.sort(key=lambda item: (item["name"], item["version"], item["sha256"]))
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def dependency_group_id(install_command: str, runner_contract: str, lock_sha256: str) -> str:
    payload = json.dumps(
        {"install_command": install_command,
         "runner_contract": runner_contract,
         "lock_sha256": lock_sha256},
        sort_keys=True, separators=(",", ":"),
    )
    return "dep-" + hashlib.sha256(payload.encode()).hexdigest()[:24]
```

`load_dependency_lock()` rejects unknown keys, non-canonical duplicate names, empty versions, non-64-hex hashes, duplicate commands, mismatched digests/schema, and wrong current runner contract. `dependency_group_for_command()` returns exactly one group or raises.

- [ ] **Step 4: Implement deterministic resolver and renderer CLI**

`resolve` enumerates unique standalone manifest dependency commands, creates a clean Python-3.12.13 venv, and uses pip JSON report:

```bash
python -m pip install --dry-run --ignore-installed --report "$report" <original requirement args>
```

For every install row require name/version and SHA-256 from `download_info.archive_info.hashes.sha256`; accept legacy `archive_info.hash` only when it is exactly `sha256=<64hex>`. Reject VCS/editable/local-path rows or rows without SHA-256. Sort by canonical distribution name and serialize with `sort_keys=True, indent=2` plus trailing newline.

`render-requirements --group dep-id` prints only:

```text
pluggy==1.6.0 --hash=sha256:<64hex>
pytest==9.0.2 --hash=sha256:<64hex>
```

`verify` calls `verify_manifest_lock()` and exits 2 with line-start `::error` for every missing/stale command.

- [ ] **Step 5: Resolve the real current manifest once and review it as code**

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

Expected: each unique dependency command has exactly one immutable group. Review generated package/version/hash deltas; resolver validity alone is not acceptance.

- [ ] **Step 6: Commit**

```bash
git add scripts/ci_dependency_lock.py config/ci_dependency_lock.v1.json \
  tests/test_ci_dependency_lock.py tests/test_ci_pack.py
git commit -m "ci: freeze immutable dependency lock"
```

---

### Task 2: Bind the lock into semantic execution identity

**Files:**
- Modify: `scripts/ci_semantic_proof.py`
- Modify: `scripts/run_ci_pack.py`
- Modify: `tests/test_ci_semantic_proof.py`
- Modify: `tests/test_ci_pack_semantic.py`
- Modify: `tests/test_ci_dependency_lock.py`

**Interfaces:**
- Consumes: `DependencyGroup.lock_sha256`.
- Produces: `job_exec_sha256(..., dependency_lock_sha256=...)` and deterministic `execution_profile_id(...)`.

- [ ] **Step 1: Write RED semantic mutations**

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

Add no-dependency control with both dependency fields `None`, plus refusal when a dependency command has `None` lock digest.

- [ ] **Step 2: Confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py \
  tests/test_ci_dependency_lock.py -k "dependency or job_digest or execution_profile"
```

Expected: old digest signature/pack identity fails.

- [ ] **Step 3: Extend the existing digest payload explicitly**

```python
def job_exec_sha256(
    *, dependency_install_command: str | None,
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

Update every callsite/test explicitly. Do not hide lock identity in telemetry only.

- [ ] **Step 4: Bind `semantic_job_digest()` and derive one profile identity**

Load `config/ci_dependency_lock.v1.json` through Task 1 validator. Dependency-free jobs pass `None`; dependency jobs resolve exactly one group and pass its digest.

Add:

```python
def execution_profile_id(runner_contract: str, lock_document_sha256: str) -> str:
    payload = json.dumps(
        {"runner_contract": runner_contract,
         "dependency_lock_document_sha256": lock_document_sha256},
        sort_keys=True, separators=(",", ":"),
    )
    return "ci-linux-x64-" + hashlib.sha256(payload.encode()).hexdigest()[:20]
```

This identity later feeds C3/EC1 receipts; it is derived evidence, not routing authority.

- [ ] **Step 5: Prove semantics**

```bash
python3.12 -m pytest -q tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
```

Expected: dependency job execution IDs change due to new bound input; step IDs and selected-job inventory do not change from lock binding alone.

- [ ] **Step 6: Commit**

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
- Cache root: `/var/cache/mastermind-ci/python`.
- Marker schema: `mastermind.ci_dependency_cache.v1`.
- CLI: `build-group`, `verify-group`, `verify-all`.

- [ ] **Step 1: Write RED ownership/hash tests**

Fixture marker:

```json
{
  "schema": "mastermind.ci_dependency_cache.v1",
  "group_id": "dep-fixture",
  "lock_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "runner_contract": "linux-x86_64/python-3.12.13/node-20",
  "files": {"pytest-9.0.2-py3-none-any.whl": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
}
```

Reject wrong owner UID, group/world-writable path/marker/wheel, missing/extra wheel, wrong hash/group/runner identity, and symlinks escaping group directory.

- [ ] **Step 2: Implement trusted `build-group`**

Render locked requirements then:

```bash
python3.12 -m pip download --only-binary=:all: --require-hashes \
  --dest "$staging" -r "$requirements"
```

Hash each artifact, require exact locked distributions, write marker atomically, set dirs `0755`, files/marker `0444`, then atomically rename staging to `<cache-root>/<group_id>`. Refuse build when effective UID differs from configured trusted owner. Candidate execution never calls build.

- [ ] **Step 3: Implement local-only verification**

`verify-group` performs no network. `verify-all` walks exactly checked-in groups; an extra unknown cache group is diagnostic but cannot satisfy a job.

- [ ] **Step 4: Prove and commit**

```bash
python3.12 -m pytest -q tests/test_ci_dependency_cache.py
git diff --check
git add ops/runner-host/pc/mastermind_ci_dependency_cache.py \
  tests/test_ci_dependency_cache.py docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
git commit -m "ops: add immutable CI dependency cache"
```

---

### Task 4: Materialize fresh job environments from the lock

**Files:**
- Modify: `scripts/run_ci_pack.py`
- Modify: `tests/test_ci_pack.py`
- Modify: `tests/test_ci_dependency_cache.py`

**Interfaces:**
- Produces `DependencyMaterialization` and `materialize_dependency_environment()`.

- [ ] **Step 1: Write RED cache-hit/fallback/refusal tests**

```python
@dataclass(frozen=True)
class DependencyMaterialization:
    env: dict[str, str]
    group_id: str | None
    lock_sha256: str | None
    source: str  # none | immutable_cache | pinned_network
```

Prove valid cache uses `--no-index --find-links ... --require-hashes`; cache bytes unchanged; missing/corrupt cache uses exact `--require-hashes` network fallback; raw manifest command is unreachable; one classified transport retry recreates venv and repeats the same lock once; non-transport failure is not retried; each environment is fresh under `RUNNER_TEMP`.

- [ ] **Step 2: Implement the materializer**

```python
def materialize_dependency_environment(
    install_command: str | None,
    *,
    dependency_lock: DependencyLock,
    dependency_cache_root: Path,
    changed_files_file: str | Path | None = None,
) -> DependencyMaterialization:
    ...
```

No-dependency returns ordinary child env/source `none`. Dependency jobs create venv, render lock to `RUNNER_TEMP`, verify cache locally, then install either:

```text
python -m pip install --disable-pip-version-check --no-index --find-links=GROUP \
  --require-hashes -r REQUIREMENTS
```

or exact fallback:

```text
python -m pip install --disable-pip-version-check --require-hashes -r REQUIREMENTS
```

Fallback never recomputes versions.

- [ ] **Step 3: Wire `_run_job` without changing failure authority**

Keep current dependency timing around materialization. Materialization errors become existing infrastructure `dependency_failed`; semantic-step failure classification is unchanged.

- [ ] **Step 4: Prove and commit**

```bash
python3.12 -m pytest -q tests/test_ci_pack.py tests/test_ci_dependency_cache.py \
  tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
git diff --check
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
- Modify: `agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-L3-IMMUTABLE-DEPENDENCY-ENVIRONMENTS-2026-09-01.md`

**Interfaces:**
- Consumes current post-C3 receipt schema, `DependencyMaterialization`, and Task 2 profile ID.
- Produces dependency provenance only in existing receipt/timing artifacts.

- [ ] **Step 1: Fresh-reconcile receipt API**

Inspect current main C3 fields and preserve `execution_profile_id`, `admission_policy_version`, queue timestamps, checkout/dependency/test/wall timing and cgroup/resource schema law. If names/contracts materially differ, stop for Sol rather than add synonyms.

- [ ] **Step 2: Add RED receipt provenance tests**

For each logical job/group represent sorted records:

```json
{
  "logical_job_id": "example",
  "dependency_group_id": "dep-fixture",
  "dependency_lock_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "dependency_source": "immutable_cache"
}
```

Use a `dependency_materializations` array for mixed groups. Absence is empty/null, not zero or fake observed value. Mutation tests prove receipt fields never enter semantic fragment hashing and cannot make `ci-gate` green.

- [ ] **Step 3: Wire existing workflow artifacts only**

Pass the materialization sidecar emitted by `run_ci_pack.py` into current `capture_ci_canary_receipt.py` beside timing/resources. Upload only through existing trusted receipt/timing artifacts. No dependency-results DB/check.

- [ ] **Step 4: Deterministic proof**

```bash
python3.12 -m pytest -q \
  tests/test_ci_dependency_lock.py tests/test_ci_dependency_cache.py tests/test_ci_pack.py \
  tests/test_ci_semantic_proof.py tests/test_ci_pack_semantic.py tests/test_ci_canary_tools.py
python3.12 scripts/ci_dependency_lock.py verify \
  --workflow .github/ci/legacy-jobs.yml --lock config/ci_dependency_lock.v1.json
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
python3.12 scripts/agentos.py validate
git diff --check
```

- [ ] **Step 5: Prove cache-hit canary + pinned-network negative control**

Use current self-hosted canary on a non-destructive same-repo candidate. One dependency-bearing pack must prove cache hit, exact group/lock/profile, parity and unchanged cache bytes. A separately authorized diagnostic environment with that group absent must run the same locked network fallback and prove no raw resolver. Do not mutate production cache to manufacture the negative control.

- [ ] **Step 6: Accrue natural traffic**

Freeze at least 20 natural dependency-bearing pack observations. Report p50/p95 queue, checkout, dependency prep, test, wall separately. L3 PASS requires dependency-prep p95 <60s for cache hits, zero route-attributable same-SHA mismatch, zero candidate cache mutations, zero unpinned resolution, and exact lock/profile receipts.

- [ ] **Step 7: Review, held PR, durable records**

Independent review exact head. Keep implementation PR DRAFT/HOLD-FOR-SOL. Return exact head/base/files, lock document SHA, group count, CI/fences, canary/negative-control IDs and natural p50/p95.

```bash
git add agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md \
  agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md \
  agentos/handoffs/CI-L3-IMMUTABLE-DEPENDENCY-ENVIRONMENTS-2026-09-01.md
git commit -m "records: bank immutable dependency proof"
```

Run `python3.12 scripts/agentos.py validate` before commit.

## Stop Condition

Stop for Sol if current manifest dependencies cannot be locked to exact SHA-256 Linux/x86_64 Python-3.12.13 artifacts, current semantic/receipt law requires a new proof plane, candidate cache mutation becomes necessary, or parity would require pretending different execution profiles are identical.

## Completion Truth

Landing L3 is `IMMUTABLE_DEPENDENCY_EXECUTION = BUILT_NOT_PROVEN` until natural cache-hit corpus passes. Passing makes the dependency execution profile `PROVEN_LIVE` for the current persistent Linux/x86_64 route. It does not enable JIT/cloud runners, result reuse, extra capacity, or broader ownership narrowing.