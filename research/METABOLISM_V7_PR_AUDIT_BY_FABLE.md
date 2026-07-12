# Metabolism v7 — PR Audit (the loop reviews its own code before it goes live)

**Status:** RATIFIED design 2026-07-12; ships with this doc + the AUDIT stage.
**Owner program:** `autonomic-loop` (extends v4 First Breath, v5 Durability, v6 Lobe Genesis).
**Operator directive (2026-07-12):** does the orchestrator audit PRs? — and allow the loop to merge and go live.
**Method:** file:line census of the merge lane's gate sequence + this Fable adjudication.

---

## 0. Executive ruling — proposal-approval is not code-approval

Census finding, verified in `scripts/metabolism_merge.py:run_merge_lane`: the merge lane gates each build-lane draft PR on exactly three things — a two-key ADJUDICATE grant (`_is_two_key_granted`, step 3), CI green (`_pr_ci_green`, step 4), and the self-mod fence (`_fence_check_pr`, step 5) — then rebase-merges. Merging to `main` triggers `render.yml` (`on: push: branches:[main]`), so **merge is go-live**. The lane is cron-armed (12:15 UTC) and uses `METABOLISM_MERGE_PAT`. It is ready to ship code to production the moment `AUTONOMY_PAUSED=false`.

The gap: **the two-key grant authorizes the PROPOSAL — the idea, before any code exists.** Nothing in the pipeline ever reads the DIFF the sonnet build agent actually wrote. A build that (a) passes CI but silently does the wrong thing, (b) drifts beyond the proposal's scope, (c) introduces a correctness or security regression CI doesn't catch, or (d) subtly diverges from its fitness contract, would merge and go live unreviewed. The self-mod fence catches only IMMUTABLE-set edits; CI catches only what the test suite asserts. Neither is a code review.

Throughout this whole build program, every loop-authored PR was adversarially reviewed by an Opus reviewer before merge (manually, by the operator's session). The loop must institutionalize that: **the two-key on the idea gets a third key on the code.**

**The ruling:** add an AUDIT stage between BUILD and MERGE — a deterministic containment re-check plus an adversarial Opus code auditor that reads the realized diff against its proposal and emits approve/reject. The merge lane requires an AUDIT-APPROVE record as a new fail-closed gate. This is what makes autonomous merge SAFE, not just possible. Everything stays inert behind `AUTONOMY_PAUSED`; nothing here arms the loop.

---

## 1. Rulings (R-V7-1 … R-V7-6)

**R-V7-1 — Code review is a merge gate, deterministic-first.** A new stage AUDIT reviews each build-lane draft PR of the cycle. Order of authority (mirrors R-AUT-1): a DETERMINISTIC pre-screen runs first and is fail-closed; the LLM auditor runs only if it passes, and the LLM can only REJECT (veto) or approve-within-the-envelope — it can NEVER approve something the deterministic screen rejected. The deterministic pre-screen:
(a) **Foreign-file containment** — every changed file must be inside the proposal's declared `target_files` (plus `data/metabolism/`); defense-in-depth ahead of the build lane's own check, re-verified on the FINAL diff.
(b) **Immutable-set re-check** — no `check_self_mod_fence.IMMUTABLE_PATTERNS` path touched (belt-and-suspenders with merge step 5).
(c) **Diff-budget sanity** — reject a diff whose size exceeds `audit_max_diff_lines` (new budget key) — a runaway build never merges unattended.
Any deterministic failure → verdict REJECT, no LLM call.

**R-V7-2 — The adversarial auditor is Opus, and defaults to reject.** When the deterministic screen passes, a headless **opus-pinned** auditor session (never sonnet — sonnet builds, opus audits; key-pool dispatched, same broker lane machinery as the build lane) reads the diff + the proposal + its fitness contract + the immutable list and is instructed: REJECT if the diff does more or less than the proposal authorized (scope creep / drift), introduces a correctness or security defect, touches anything it shouldn't, diverges from the fitness contract, or you are not confident it is safe to ship unattended — **default to REJECT under any uncertainty.** It emits `{verdict, confidence, findings[], rationale}`. It may only remove approval, never manufacture it (R-AUT-1).

**R-V7-3 — Merge requires a fresh, matching AUDIT-APPROVE.** `run_merge_lane` gains step 5.5: `_audit_approved(pr_number, head_sha, root)` — an approve verdict must exist for THIS pr AND be stamped with the PR's current head SHA (so a post-audit force-push invalidates it; re-audit required). Fail-closed: no audit record, a reject, or a SHA mismatch → the PR is skipped (`audit_not_approved`), never merged.

**R-V7-4 — Everything observable + inert.** The AUDIT stage writes `data/metabolism/audit/<pr>.json` and a governance `metabolism_audit` event (append-only), surfaced on the admin console like other stages. `AUTONOMY_PAUSED` double-gated (job `if:` + in-script exact-`false`), fails closed on any error (a broken auditor blocks merges, never waves them through), `if: failure()` operator notify. Cron 11:45 UTC (after BUILD 10:45, before MERGE 12:15).

**R-V7-5 — Merge-and-go-live is hereby the ratified end state, behind five gates.** With AUDIT in place, an autonomous merge to production passes: (1) two-key proposal grant, (2) CI green, (3) self-mod fence, (4) deterministic diff containment, (5) adversarial Opus code approval — plus the standing capability-broker/immutable fences and the operator's always-available pause switch. This is a defensible autonomy grant: the loop cannot ship code to production that an independent adversarial reviewer would not approve.

**R-V7-6 — Refusals.** The auditor itself authors nothing (read-only review; it never edits the diff — the fix is a fresh BUILD session, not an auditor patch; see R-V7-7). No bypass of the audit gate for any tier. No LLM-originated approval outside the deterministic envelope. The audit does not replace VERIFY (fitness grading, post-merge) — it is pre-merge code correctness/containment, a different question.

**R-V7-7 — A rejection cycles back with a fix plan, bounded, then parks (operator directive 2026-07-12).** An audit REJECT is not terminal: the auditor's `findings[]` + `rationale` become a remediation directive that re-dispatches a fresh BUILD session for the SAME proposal, committing a fix to the SAME PR branch — so the same PR updates, its head SHA changes (invalidating any approval, R-V7-3), and AUDIT re-runs on the fix next cycle. This is the code-review analogue of R-V5-1's re-attemptable-then-park: a rejection is a re-attemptable terminal state with the auditor's findings injected into the build task prompt ("your prior attempt was rejected for X, Y, Z — fix exactly these, stay within the same target_files"). It is BOUNDED by `max_audit_rebuild_attempts` (new budget key, default 2); after the cap the proposal PARKS with an operator insight (`audit_rebuild_exhausted`), the rejected draft PR is left for operator review, and the proposal is never silently dropped nor infinitely rebuilt. The remediation counter is durable (committed to the journal — the R-V5-1 lesson: an uncommitted counter resets every checkout and the bound never bites). The auditor never patches the code itself; only a new fenced, sonnet-pinned BUILD session does — so remediation inherits every build-lane safety property (immutable refusal, foreign-file containment, target-file allowlist).

---

## 2. Build (single wave, ships with this doc)

- `engine/metabolism/audit.py` — `audit_pr(pr_number, proposal, diff_text, head_sha, root) -> dict`: deterministic screen (R-V7-1) → opus LLM review (R-V7-2, via `engine.llm_auth` with an `oauth_pool_lane`, opus model) → combined verdict → write record + governance event. NEVER-RAISE; any error → reject.
- `scripts/metabolism_audit.py` — CLI + `--scan` (cron) mode: discover build-lane draft PRs for the cycle, fetch each proposal + `gh pr diff`, run `audit_pr`, journal. `AUTONOMY_PAUSED` first-action gate.
- `.github/workflows/metabolism-audit.yml` — cron `45 11 * * *`, double-gate, key-pool secrets, `METABOLISM_MERGE_PAT` for `gh`, failure notify.
- `scripts/metabolism_merge.py` — `run_merge_lane` step 5.5 `_audit_approved` gate (fail-closed, SHA-matched).
- `config/metabolism_budget.yml` — `audit_max_diff_lines` (R-V7-1c) + `audit_lane` capability note.
- `docs/METABOLISM_ARMING_CHECKLIST.md` — note the AUDIT gate in the workflow table + day-1 watch row.
- Tests: deterministic reject (foreign-file / immutable / oversize), LLM-reject path, approve requires BOTH, merge lane refuses un-audited / stale-SHA / rejected PR, fail-closed on missing record, pause no-op.

Sequencing: single PR; the merge-lane gate and the audit stage ship together so there is never a window where merge runs without the gate wired.
