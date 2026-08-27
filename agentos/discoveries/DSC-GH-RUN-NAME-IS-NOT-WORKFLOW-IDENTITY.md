---
key: GH-RUN-NAME-IS-NOT-WORKFLOW-IDENTITY
claim: >
  The GitHub REST field `name` on `GET /actions/runs/{id}` (and on the
  `workflow_run` webhook envelope) reports the RENDERED `run-name:` of the
  triggering workflow, NOT the workflow's `name:`. The two coincide only while
  the workflow declares no `run-name:`, so any identity assertion written
  against `name` is latent breakage that fires the moment a sibling PR adds or
  edits `run-name:` — a change that looks unrelated and touches a different
  file. `path` (and `workflow_id`) are the GitHub-assigned identity and are
  stable across run-name edits. Measured: daily.yml gained
  `run-name: daily ${{ github.event.schedule || github.event_name }}` in #5723
  (cc6f53f6, 2026-08-15T08:01Z); `run.name` became `daily 30 23 * * *`, and
  scripts/ci/retry_daily_engine_setup_cancel.py — which asserted
  `run["name"] == "daily"` — refused every nightly from the very next slot,
  failing 28 consecutive times over 11 days with `run is not the daily workflow`.
falsifier: >
  `gh api /repos/OWNER/REPO/actions/runs/<id> --jq '{name, display_title, path}'`
  on any run of a workflow that declares `run-name:`. If `name` came back equal
  to the workflow's `name:` rather than the rendered run-name, this is refuted.
  Receipt 2026-08-26 on daily run 32912351235:
  `{"name":"daily 30 23 * * *","display_title":"daily 30 23 * * *","path":".github/workflows/daily.yml"}`.
so_what: >
  Never assert workflow identity on `run.name` in a watchdog, gate, or arbiter —
  pin `path` instead. Two further consequences a future session needs. (1) The
  break is INVISIBLE to the workflow that caused it: #5723 was a correct daily.yml
  DST fix and its own lane went green; only the sibling consumer died, so a
  `run-name:` edit must trigger a grep for consumers of that run's `name`.
  (2) A watchdog whose every invocation errors is indistinguishable on dashboards
  from a watchdog with nothing to do — the lane was 100% red for 11 days and no
  instrument named it. When a recovery lane's failure rate is 100%, suspect a
  contract break against its OWN trigger, not the condition it guards.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  PR #6466. Root cause: .github/workflows/daily.yml:5 (`run-name:`, added
  cc6f53f6 / #5723) vs scripts/ci/retry_daily_engine_setup_cancel.py:26 pre-fix
  (`EXPECTED_WORKFLOW_NAME = "daily"`) consumed at `_validate_run`.
  Failure receipt: run 32945166048 step log,
  `##[error]run is not the daily workflow`, exit 1.
  Failure census: `gh run list --workflow daily-engine-setup-retry.yml --limit 200`
  = 33 failure / 14 success, unbroken failure from run #20 (2026-08-15T23:43Z,
  the first nightly after cc6f53f6) through #47 (2026-08-26T07:55Z).
  API semantics receipt: run 32912351235 (above).
  Read-only replay of the real `decide_retry` over all 29 `daily` runs on main
  since 2026-08-15: 0/29 admitted before the fix, 29/29 after, 0 retry-eligible
  in both — so the outage burned ~28 scheduled runs but starved no nightly.
scope: [macro, .github/workflows/**, scripts/ci/**]
confidence: verified
---

## Detail

`run-name:` is documented as display metadata, which is exactly why it is dangerous:
it reads as cosmetic to the author editing it, and GitHub surfaces it through the same
`name` key that carries the workflow name when no `run-name:` is set. Nothing in the
API response marks which of the two you received.

The blast radius is one-directional and quiet. The workflow that adds `run-name:`
cannot fail from it. Only a *consumer* that treats `name` as identity breaks, and a
`workflow_run` consumer is by construction a different file, usually written by a
different session at a different time. Here the consumer was last touched 2026-08-09
(#5096) and the producer changed 2026-08-15 (#5723); no test caught it because
`tests/test_daily_engine_setup_retry.py` fixed `"name": "daily"` in its own fixture,
so the suite stayed green against a shape production had stopped producing.

Fixing the identity assertion exposed a second defect of the same species that the
first had masked: a daily cancelled during an upstream job never creates the `engine`
job at all (daily run 32194718597: two job rows, `collect` cancelled, zero `engine`
rows), and the controller raised a *contract violation* on that ordinary shape. A
misclassified no-op and a misclassified identity both surface as a red lane, and the
outer one hides the inner one — so after repairing a 100%-failing gate, re-run the
real logic over real payloads rather than trusting that one fix restored the lane.
