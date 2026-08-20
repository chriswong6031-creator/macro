---
key: SEMANTIC-ELIGIBILITY-IS-ROLE-DEPENDENT
claim: >
  A CI semantic unit's ELIGIBILITY differs between the pr_head and main roles,
  so a logical job can be eligible to BLOCK a session's Stop on a pr_head
  artifact while never being eligible to CLEAR on any main artifact. ci.yml
  plans both roles with `--gate code` (120 of the manifest's 194 legacy jobs);
  the 74 `gate: data` jobs run on data-health.yml, which emits no semantic
  evidence at all. Any head planned before that split (W2, 2026-08-19) froze
  blocking units for `gate: data` jobs, and ship_loop_guard's descendant-PASS
  witness search can never match them.
falsifier: >
  A main-role ci.yml artifact carrying a `gate: data` logical_job_id (e.g.
  house-law-registry, signal-contract) would refute the permanence; measured
  absent across main runs 32248437793, 32254503694, 32257813740, 32267640863
  (green) and 32259996789, 32273305792, 32282099239 (red). Re-uniting the two
  roles' job sets — data-health emitting main-role semantic evidence, or the
  gate split being reverted — would retire this record.
so_what: >
  Never reason about a frozen semantic red as "wait for main to heal it"
  without first asking whether MAIN PLANS THAT JOB AT ALL. ship_loop_guard now
  reads main's eligible inventory from the same bounded artifact window
  (ci_semantic_proof.main_role_job_inventory) and retires units main never
  plans, naming each in the release note; every remaining blocking unit now
  prints `main-eligible=yes|no|unknown` so a session can tell instantly
  whether waiting is futile. Cost of not knowing: PR #5936 merged clean and
  its session could not Stop across seven post-merge main runs plus a
  one-hour ancestry watcher.
kind: constraint
verified_at: 2026-08-19
verified_by: "ci-semantic-plan artifacts of runs 32223270543 (pr_head: 117 eligible / 77 skipped of 194, both data jobs present) and 32267640863 (main: full suite, skipped_jobs 0, 120 eligible, neither job present); .github/ci/legacy-jobs.yml gate census 120 code / 74 data; fix + tests in scripts/ci_semantic_proof.py and .claude/hooks/ship_loop_guard.py"
scope:
  - "macro"
  - ".claude/hooks/ship_loop_guard.py"
  - "scripts/ci_semantic_proof.py"
  - ".github/workflows/data-health.yml"
confidence: verified
---

Background: `research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md` (W2
is the gate split that created the asymmetry).
