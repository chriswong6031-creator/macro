---
key: NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB
claim: >
  daily.yml fires as a DST-paired cron, so each night produces TWO scheduled
  runs: the wrong-DST one exits in about six seconds reporting run-level
  SUCCESS with every job skipped, while the run that actually builds executes
  for hours and frequently reports run-level CANCELLED or FAILURE from a late
  job long after its engine job already succeeded and pushed its commit.
  A nightly artifact therefore cannot be attributed from run-level
  event/status/conclusion; only the engine JOB's conclusion and time window can
  attribute it.
falsifier: >
  gh api repos/{owner}/{repo}/actions/runs/<id>/jobs --jq '.jobs[] |
  select(.name=="engine") | "\(.conclusion) \(.started_at) \(.completed_at)"'
  on the run you believe produced an artifact. If the engine job reads
  "skipped" the run built nothing regardless of a green run-level conclusion;
  if it reads "success" with a window bracketing the artifact commit's
  timestamp, that run is the producer regardless of a red run-level conclusion.
so_what: >
  Any session recording a production receipt for a nightly artifact must
  resolve the engine job before naming a run id, and must not treat a
  six-second run-level SUCCESS as proof a bake occurred or a run-level
  CANCELLED as proof it did not. This matters for every capability ledger,
  closeout receipt and staleness diagnosis that cites a nightly run.
kind: runtime
verified_at: 2026-08-26
verified_by: >
  gh api repos/mastermindx-market-intelligence/macro/actions/runs/32790724676/jobs
  --jq '.jobs[] | "\(.name) \(.conclusion)"' — and the same call for run
  32786919396, run 32908543584 and run 32912351235.
  Run 32790724676 (created 2026-08-24T23:45:03Z, run-level completed/success,
  updated 6 seconds later) shows engine | completed/SKIPPED with every
  downstream job skipped, and produced nothing. Run 32786919396 (created
  2026-08-24T22:54:58Z, run-level completed/CANCELLED) shows engine |
  completed/SUCCESS 2026-08-25T03:04:41Z -> 05:49:32Z and is the true producer
  of engine commit be061c6d49e9 at 05:42:31Z, inside that window. The same
  shape repeats the following night: run 32908543584 engine success
  2026-08-26T03:27:14Z -> 06:23:13Z produced commit 576959b11804 at 06:15:15Z,
  while sibling run 32912351235 reported success in six seconds.
scope:
  - ".github/workflows/daily.yml"
  - "agentos/**"
  - "research/**"
confidence: verified
---

The trap is that the misleading signal is the GREEN one. A scout census, and
then a records PR built on it (#6413), both attributed the first SRC-A1
collection to run 32790724676 because that run alone reported
`event: schedule, conclusion: success` — a shape that reads exactly like a
healthy nightly. It had skipped every job.

The DST guard is working as designed: the wrong-DST firing self-exits cleanly,
which is why it reports success. The consequence is that run-level conclusion
is anti-correlated with having done the work, and the honest attribution
signal sits one level down in the jobs list.
