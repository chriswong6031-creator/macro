---
key: LEGACY-JOB-IF-FALSE-IS-MANDATORY-NOT-A-FREEZE
claim: >
  `if: ${{ false }}` on a job in `.github/ci/legacy-jobs.yml` is a MANDATORY
  manifest field, not a disable switch: `run_ci_pack.py`'s validator REFUSES
  any job that omits it ("must declare `if: ${{ false }}` so GitHub does not
  allocate a duplicate runner"), because the legacy jobs are executed by
  `ci.yml`'s `ci-pack-N` matrix through `run_ci_pack.py --execute`, not by
  GitHub scheduling them directly. All 199 jobs in the manifest carry the line
  and every one of them runs. What decides whether a job's suites bind a pull
  request is the SEPARATE `gate: code | data` field — `code` packs onto the
  merge gate, `data` moves to `data-health.yml` after the nightly. `gate` is
  per-JOB, so a single data-coupled suite takes every other suite in that job
  off the merge gate with it.
falsifier: >
  `grep -cF 'if: ${{ false }}' .github/ci/legacy-jobs.yml` returning fewer than
  the job count, or a legacy job that omits the line and still passes
  `python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
  --validate-only`. Either would mean the field is a real per-job condition
  rather than a duplicate-runner guard. Equally: a `ci-pack` run whose log
  never emits `##[group]<job-id> — <step name>` for a job carrying the line.
so_what: >
  A session asked to "re-enable a dark CI job" that reads the `if: ${{ false }}`
  line as the disable will chase a freeze that does not exist, and may delete
  the line to "fix" it — which fails the manifest validator closed and takes
  down all twelve packs, i.e. the entire merge gate, for every PR in flight.
  Before concluding a suite is dark, ask the two questions that actually decide
  it: (1) which job names the suite in a `run:` step, and (2) what is that job's
  `gate:`. A `gate: data` job is not dark — read its verdict out of the newest
  `data-health.yml` run, whose packs are 6 wide, not 12.
kind: architecture
verified_at: 2026-08-21
verified_by: >
  `scripts/run_ci_pack.py:1292-1295` (the validator finding) with
  `DISABLED_IF = "${{ false }}"` at `:74`; `grep -cF 'if: ${{ false }}'
  .github/ci/legacy-jobs.yml` = 199 against 199 jobs loaded by
  `load_legacy_jobs`, split 125 `code` / 74 `data`. Executed-not-skipped proof:
  data-health run 32430236421 job `data-pack-5` logs
  `##[group]china-native-collectors — china institutional-visit tape collector
  tests (P1)` for a job carrying the line. Merge-gate proof: PR #6142 head
  470dcb1bc10059bbb401fb9c55d43f9f9385c566 shows ci-pack-0..11 all success,
  and `unrun-brain-desks` (`gate: code`, also carrying the line) is in the
  selected set. Classification origin: PR #5954, W1 of
  research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md.
scope: [macro, .github/ci/legacy-jobs.yml, scripts/run_ci_pack.py]
confidence: verified
---

Corollary measured on the same pass (2026-08-21), and the reason this record
exists rather than a one-line comment: of the **18** suites named by
`china-native-collectors`, **17 are pure-code** — they pass with `data/`
absent from disk entirely. Exactly one, `tests/test_china_news_intel_w2.py`,
reads the committed tree (`engine/entity_resolver.py:102` →
`data/baskets_china/membership.json`, nightly-rewritten) and correctly forces
the job's `gate: data`. Because `gate` is per-job, that one coupling holds the
other seventeen off the merge gate. See
[[MERGE-GATE-IS-GATED-ON-MOVING-DATA]] for why the split exists at all.
