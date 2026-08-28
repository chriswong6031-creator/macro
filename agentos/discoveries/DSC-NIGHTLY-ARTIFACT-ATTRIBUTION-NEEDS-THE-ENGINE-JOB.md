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
  For SRC-A1 specifically there is a STRICTLY STRONGER method that needs no
  Actions API call at all: the artifact's own `collection_session_id` is
  `sha256` of the canonical tuple `("src-a1", "yfinance", ("github_run",
  <run_id>))`, so a candidate run id can be confirmed or refuted from the
  parquet body alone. Prefer that when the artifact carries such an id;
  fall back to the engine-job window for artifacts that do not.
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

## Cryptographic confirmation for SRC-A1 artifacts

`_default_collection_session_id` (`collectors/equity_revisions.py`) hashes
`("src-a1", _EXPECTATION_PROVIDER, ("github_run", os.environ["GITHUB_RUN_ID"]))`
through `_canonical_sha256`, so the run identity is embedded in every row.
Recomputing that hash for each candidate run settles attribution outright:

| candidate run | sha256 prefix | verdict |
|---|---|---|
| `32786919396` | `74cfd4a7162056b1…` | equals C1's `collection_session_id` |
| `32908543584` | `d9fa989a6c9e3b82…` | equals C2's `collection_session_id` |
| `32790724676` (skip-twin) | `02cba011439313e5…` | appears nowhere in the data |
| `32912351235` (skip-twin) | `e08943d447a5b6b6…` | appears nowhere in the data |

This independently confirms the engine-job finding and definitively refutes the
skip-twin attribution that reached the 2026-08-25 records. Method credit: a
parallel K3E session (PR `#6469`) surfaced it; verified here before adoption.
