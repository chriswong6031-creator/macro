# MAS-126 CF1 Current-Main Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the existing secret-free Capacity Fabric CF1 candidate in Macro PR #6297 with protected current `main`, replace stale exact-head proof, and return the same carrier to a lawful `PARKED / HOLD-FOR-SOL` state for Sol review.

**Architecture:** Preserve the existing PR, branch, worktree, schema, and current-provider-only implementation. Merge fresh `origin/main` into the carrier without rebasing or force-pushing; current archaeology shows that only `.github/ci/legacy-jobs.yml` overlaps and a three-way merge is conflict-free. Re-run local contract, owner, no-write, secret-boundary, and Agent OS proof; publish the exact new head to the same draft PR; then obtain current hosted checks while the merge/deploy barrier remains armed.

**Tech Stack:** Python 3.14 local proof, pytest, strict JSON, Git/GitHub CLI, Macro Agent OS validator, GitHub Actions CI/fences.

**Spec:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md`

## Global Constraints

- Existing carrier only: PR `#6297`, branch `sol/executive-capacity-cf1-20260823`, worktree `/Users/chriswong/Documents/Cluade/macro-main/.warp/worktrees/mas-126-cf1`.
- Stable operation key: `MAS-126-CF1-RECONCILE-20260825`.
- Stop state: `PARKED / HOLD-FOR-SOL`; keep the PR draft, keep `merge-on-green` absent, keep native auto-merge null, and do not merge or deploy in this reconciliation slice.
- Preserve the accepted closed contract from the primary spec and all three amendments: placement, semantic identity/acquisition, and observation-null semantics.
- CF1 remains Macro-only, deterministic, no-write, existing-provider-only, and secret-free.
- Do not add Executive placement, Personal Pro login/readiness, a provider, a worker realm, a router, a provider database, a remote transport, a UI, or a credential read.
- Do not inspect credential values, `auth.json`, browser cookies, provider-home contents, Keychain secret contents, tokens, passwords, one-time codes, or account PII.
- Do not touch `/Users/chriswong/Documents/Cluade/Macro Dashboard` or `/Users/chriswong/Documents/Cluade/Mastermind`; both operator checkouts are shared/dirty.
- Never rebase, reset, stash, force-push, create a replacement branch, create a replacement PR, use `git add -A`, or use `git add .`.
- Before each push and before final review, fetch and re-pin protected `origin/main`; movement invalidates earlier current-base proof.
- If reconciliation reveals a behavioral regression, use `superpowers:systematic-debugging`, write a failing regression test first under `superpowers:test-driven-development`, and limit the repair to the CF1 contract.

---

### Task 1: Freeze the Carrier and Reconcile Protected Main

**Files:**
- Modify by three-way merge: `.github/ci/legacy-jobs.yml`
- Preserve without behavioral edits: `engine/provider_capacity.py`
- Preserve without behavioral edits: `engine/codex_provider.py`
- Preserve without behavioral edits: `engine/metabolism/budget_gate.py`
- Preserve without behavioral edits: `engine/neuralweb/key_pool.py`
- Preserve without behavioral edits: `engine/provider_health.py`
- Preserve without behavioral edits: `scripts/build_provider_capacity.py`
- Preserve without behavioral edits: `tests/test_provider_capacity.py`

**Interfaces:**
- Consumes: protected GitHub `main`; exact existing PR head; the accepted CF1 source law.
- Produces: one non-force merge commit on `sol/executive-capacity-cf1-20260823` containing current `main` plus the unchanged CF1 candidate.

- [ ] **Step 1: Re-pin carrier and protected base**

Run:

```bash
git status --short --branch
git fetch origin main sol/executive-capacity-cf1-20260823
git rev-parse HEAD
git rev-parse origin/sol/executive-capacity-cf1-20260823
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
```

Expected: worktree clean; local `HEAD` equals the remote PR head; the branch is behind current `main`; no unexplained local or remote head movement.

- [ ] **Step 2: Recheck collision surface and merge forecast**

Run:

```bash
git diff --name-status "$(git merge-base HEAD origin/main)"..origin/main -- \
  .github/ci/legacy-jobs.yml \
  agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-08-23.md \
  agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md \
  engine/codex_provider.py \
  engine/metabolism/budget_gate.py \
  engine/neuralweb/key_pool.py \
  engine/provider_capacity.py \
  engine/provider_health.py \
  scripts/build_provider_capacity.py \
  tests/test_provider_capacity.py
git merge-tree --write-tree HEAD origin/main
```

Expected: current main overlaps only `.github/ci/legacy-jobs.yml`; merge-tree exits 0 with no conflict paths. If any provider-capacity implementation path now overlaps, stop before merging and perform source-law reconciliation.

- [ ] **Step 3: Merge current protected main without rewriting carrier history**

Run:

```bash
git merge --no-ff origin/main -m "chore: reconcile CF1 with current main"
```

Expected: one merge commit, no conflict markers, no rebase, and no force operation.

- [ ] **Step 4: Prove the shared CI manifest retained both sides**

Run:

```bash
rg -n "test_provider_capacity.py" .github/ci/legacy-jobs.yml
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: exactly one registered `tests/test_provider_capacity.py` invocation remains in the provider-owner pytest step; current-main CI additions remain present; diff check is clean.

### Task 2: Re-Prove CF1 Locally on the Reconciled Head

**Files:**
- Test: `tests/test_provider_capacity.py`
- Test: `tests/test_codex_provider.py`
- Test: `tests/test_provider_health.py`
- Test: `tests/test_key_pool.py`
- Test: `tests/test_key_pool_economy.py`
- Test: `tests/test_key_pool_seven.py`
- Test: `tests/test_metabolism_budget_gate.py`
- Validate: `agentos/`

**Interfaces:**
- Consumes: reconciled CF1 source and current-main owner code.
- Produces: exact local pass counts, no-write receipt, strict secret-safe snapshot metadata, and a clean checkout.

- [ ] **Step 1: Run the focused contract and touched-owner suite**

Run:

```bash
python3 -m pytest -q \
  tests/test_provider_capacity.py \
  tests/test_codex_provider.py \
  tests/test_provider_health.py \
  tests/test_key_pool.py \
  tests/test_key_pool_economy.py \
  tests/test_key_pool_seven.py \
  tests/test_metabolism_budget_gate.py
```

Expected: all selected tests pass. Pytest temporary-directory cleanup warnings may be recorded separately but do not excuse a failed test.

- [ ] **Step 2: Run the exact CI-registered provider-owner line**

Run the command resolved from the current `.github/ci/legacy-jobs.yml` step that contains `tests/test_provider_capacity.py`, without substituting an older manifest command.

Expected: all tests in the registered line pass on the reconciled head.

- [ ] **Step 3: Validate Agent OS records**

Run:

```bash
python3 scripts/agentos.py validate
```

Expected: exit 0 and zero schema errors; unrelated warnings are counted and recorded rather than called clean.

- [ ] **Step 4: Prove real CLI contract, semantic stability, grounding, and no-write behavior**

Run:

```bash
python3 -m pytest -q \
  tests/test_provider_capacity.py::test_real_cli_is_canonical_json_and_no_write
python3 -m pytest -q tests/test_provider_capacity.py \
  -k "material or allowlist or audit or hash or secret or injection"
```

Then invoke `python3 scripts/build_provider_capacity.py` twice and parse only the strict public fields needed for the receipt: schema, generated time, snapshot hash, producer implementation identity/version/material digest, audit commit/grounding flag, provider counts, slot count, and degradation codes. Do not print raw environment, paths, account PII, credential refs, or provider-home contents.

Expected: strict `mastermind.provider_capacity.v1`; 12 reviewed inventory slots (`claude=8`, `codex=3`, `deepseek=1`); distinct generated times; stable semantic hash when source evidence is unchanged; audit commit equals current `HEAD`; material grounding true; Git/source fingerprints unchanged.

- [ ] **Step 5: Recheck the checkout**

Run:

```bash
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: no test or CLI mutation and no unexplained file change.

### Task 3: Record the Current Exact-Head Return Packet

**Files:**
- Create: `agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-08-25.md`
- Modify: `agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md`

**Interfaces:**
- Consumes: exact reconciled head, current base, and local proof.
- Produces: durable organizational recovery state that calls CF1 `BUILT_PENDING_SOL`, never merged/deployed/live, and keeps every later wave held.

- [ ] **Step 1: Write the new handoff with mechanically resolved receipts**

Create one new handoff that records:

- operation key `MAS-126-CF1-RECONCILE-20260825`;
- PR #6297 and unchanged branch/worktree identity;
- pre-reconciliation head `2df53626bae9b1a5efdf6f822a54997c0fdc3cd3`;
- the exact `origin/main` SHA merged and the resulting candidate SHA from `git rev-parse`;
- changed-file/import census relative to current main;
- exact local test commands, pass counts, warnings, Agent OS result, sanitized CLI census, semantic hash, grounding, and no-write receipt;
- hosted proof state `PENDING_EXACT_HEAD` and canonical evidence location PR #6297; do not commit guessed or pre-head hosted results into the handoff;
- capability state `BUILT_PENDING_SOL` and terminal state `PARKED / HOLD-FOR-SOL`;
- explicit negative proof that CF2-F/CF2-I, Personal Pro login/readiness, provider expansion, HF1, RF1, PF1, MH1, merge, deployment, and production use remain unstarted;
- exact next action: Sol exact-head review and explicit release decision for PR #6297.

- [ ] **Step 2: Refresh the workstream boundary without claiming acceptance**

Keep CF1 at `BUILT_PENDING_SOL`; keep CF2-F, CF2-I, RF1, HF1, PF1, and MH1 todo/held; point `next_action` to the new exact-head review packet. Do not set CF1 to done before Sol releases the hold and the carrier is merged.

- [ ] **Step 3: Validate and commit only the record paths**

Run:

```bash
python3 scripts/agentos.py validate
git diff --check
git status --short
git add -- \
  agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-08-25.md \
  agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md
git diff --cached --check
git commit -m "docs: refresh CF1 Sol return packet"
```

Expected: only the two Agent OS record paths are staged for the record commit; plan and merge history are already committed separately.

### Task 4: Publish the Same Carrier and Obtain Current Hosted Proof

**Files:**
- GitHub carrier metadata only: PR #6297 body/comment/checks.

**Interfaces:**
- Consumes: clean exact local head and protected current main.
- Produces: same draft PR at the pushed head, current hosted evidence, and a fully ratified hold.

- [ ] **Step 1: Re-pin protected main immediately before push**

Run:

```bash
git fetch origin main sol/executive-capacity-cf1-20260823
git rev-parse HEAD
git rev-parse origin/sol/executive-capacity-cf1-20260823
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
```

Expected: remote carrier head still equals the last known pre-push head. If protected main advanced after Task 1, merge it with another non-force merge and repeat Task 2 before pushing.

- [ ] **Step 2: Push only the existing branch**

Run:

```bash
git push origin sol/executive-capacity-cf1-20260823
```

Expected: ordinary fast-forward update of the existing PR head; no new PR and no force push.

- [ ] **Step 3: Refresh PR metadata while preserving the barrier**

Update PR #6297’s candidate/base/local-proof fields to the exact pushed values, mark hosted proof pending for that head, and post one new hold-refresh comment. The title/body/comment must still say `HOLD-FOR-SOL`, keep the PR draft, forbid `merge-on-green`, auto-merge, ready-for-review, merge, and deploy, and name explicit Sol release after exact-head review as the release condition.

Verify:

```bash
gh pr view 6297 --repo mastermindx-market-intelligence/macro \
  --json state,isDraft,headRefName,headRefOid,labels,autoMergeRequest,mergeable,mergeStateStatus
```

Expected: open, draft, exact branch/head, no `merge-on-green`, and `autoMergeRequest=null`.

- [ ] **Step 4: Wait for binding current-head checks at a quota-safe cadence**

Use one watcher/poller at intervals of at least 90 seconds. Require every binding check to conclude. Treat the inactive-context `ci-authority/codex/merge-queue-pilot` result as a negative control only when the current authority aggregate and `ci-authority/main` conclude green with the documented inactive-base reason.

Expected: exact-head `ci-plan`, selected packs, `contract-delta`, `ci-gate`, fences, and binding CI authority evidence are all current and concluded. A genuine current-head red is investigated and repaired under TDD; pending is not green.

- [ ] **Step 5: Publish the exact-head hosted receipt without changing the Git head**

Post one PR #6297 receipt comment containing the exact candidate head, concluded check names/results, hosted run URLs, semantic/contract evidence identifiers available from CI, and any expected negative-control explanation. Reassert that the receipt is evidence for review, not release authority.

Expected: the remote Git head remains unchanged; the hosted receipt is attached to the same PR/head that produced it; the PR remains draft and held.

- [ ] **Step 6: Load current `REVIEW_RETURN.md` and perform Sol exact-head review**

Load it from protected Mastermind commit `51f9942733b86e550bb9169d2a43462bd28e774f`, the same revision as the already-loaded Skillpack index. Review the complete diff against F0 and all amendments, not only CI.

Expected: a finding-led accept/return ruling that distinguishes built, accepted, merged, deployed, and live. If accepted, this reconciliation plan still stops at `PARKED / HOLD-FOR-SOL`; release/merge is a separately explicit Sol action after the review packet is complete.

- [ ] **Step 7: Verify final ratified hold**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/sol/executive-capacity-cf1-20260823
gh pr view 6297 --repo mastermindx-market-intelligence/macro \
  --json state,isDraft,headRefOid,labels,autoMergeRequest,statusCheckRollup
```

Expected: clean worktree; local, remote branch, and PR head agree; binding checks are concluded; PR remains draft, unarmed, unmerged, undeployed, and recoverable as `PARKED / HOLD-FOR-SOL`.
