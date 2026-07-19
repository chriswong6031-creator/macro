# Macro Context Index — Benchmark

## Version

v1.2, frozen 2026-07-18, 96 questions (CTX-001..CTX-096).

### Amendment log

- **v1.3 (2026-07-18, adjudicated with CXI-2):** 13 `adjudication_replay` rows re-golded
  from `mode: research`/`operations` to `mode: adjudication`. The rows' mode fields were
  authored before CXI-2 defined mode semantics; `research` mode excludes killed/forbidden
  results, which made the flagship family unpassable by construction (a vetting session
  asking "was this killed?" uses adjudication mode, which includes kills). Queries, golden
  sources, and statuses unchanged. First eval (BENCHMARK_RESULTS.md): global 51.5%, replay
  50.0%, governance precision 60.0% — gates FAIL, printed honestly; dominant miss class is
  negative controls 0/10 (no no-answer score floor yet — first CXI-2.x iteration target).

- **v1.2 (2026-07-18, CXI-R16):** 15 cross-repo questions appended (CTX-082..CTX-096)
  covering Terminal (charting-app) and Mastermind placement/adjudication-replay, contracts,
  location, gotcha, doctrine, and negative-control families per CXI-R16. External-repo
  rows carry `visibility: private`; their `project` field is set to the owning project
  key (`terminal` or `mastermind`) so the eval harness opens the correct per-project DB.
  External-repo source paths in `required_sources` and notes use the stored scheme
  `repo://<project-key>/<relpath>` (e.g. `repo://terminal/signal_layer/contracts.py`).
  Status histogram: 59 active / 14 forbidden / 9 killed / 2 superseded / 12 no_answer.
  Paths verified against disk on 2026-07-18 (Sonnet builder + Opus audit + Fable fix pass).
  Eval of CTX-082..096 requires Terminal and Mastermind projects opted-in; results reported
  as a separate family block per CXI-R16.
  Audit notes: a third new negative control was authored but regolded to `contract`
  (CTX-094) after audit found committed Golden-Oracle Sharpe fixtures — a false null
  corrected beats a quota met (new-block negatives = 2, total no_answer = 12). CTX-085
  regolded to `macro-dashboard`/shared: the OAuth-rotation replay's honest answer is that
  macro's own `engine/neuralweb/key_pool.py` is the origin implementation (Mastermind's
  `key_rotor.py` is its credited port, kept as acceptable cross-repo corroboration).

- **v1.1 (2026-07-18, adjudicated):** CTX-010 regolded and CTX-068 notes amended after the
  UWP operator override (#2967, PRD Amendment 1) struck the PRD-R1 placement ban the same
  day as the v1 freeze. CTX-010 is now a supersession test (`required_status: superseded`):
  correct retrieval must surface the amended registry row + UWP masterplan, not the
  pre-override prohibition. Status histogram: 47 active / 14 forbidden / 9 killed /
  1 superseded / 10 no_answer. This event is itself evidence for the program: a governance
  golden went stale in under 24 hours, which is exactly the freshness/authority problem the
  Context Index exists to surface (docket §5, Failure 4).

## required_status vocabulary

Values are drawn from the `context_document.v1` status enum ratified in CXI-R4:

| Value | Meaning |
|---|---|
| `active` | Source is current and authoritative |
| `historical` | Source is dated but not superseded |
| `superseded` | Source has been replaced by a newer document |
| `killed` | Topic killed/struck/falsified/refuted by ruling (typically DO_NOT_REBUILD §2) |
| `forbidden` | Topic forbidden/illegal/do-not-build by ruling (DO_NOT_REBUILD §1 FORBIDDEN/ILLEGAL/DON'T-TEST/DO-NOT-BUILD verdicts) |
| `deferred` | Topic held or suspended (DO_NOT_REBUILD §4) |
| `unknown` | Status could not be determined from canonical sources |
| `no_answer` | Negative control — no document satisfying the query exists in the repo |

The `no_answer` sentinel is not part of the `context_document.v1` enum; it is the grading
marker for negative-control rows where an honest "not found" packet is the correct answer.

## Grading rule

A retrieval result satisfies a benchmark row when:

- Every file listed in `required_sources` appears in the top-10 retrieved results.
- The labeled `required_status` is returned in the result packet for each required source.
- For `no_answer` rows: the packet is an honest null/empty answer with no fabricated source.

Rows with `acceptable_sources` may use those sources to supplement or corroborate but are
not required in top-10.

Promotion gates (from research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md CXI-R5/CXI-R6/CXI-R16):

- Global: >=90% Recall@10 across all 96 rows (shared-visibility rows only for the baseline run).
- Adjudication-replay family: >=90% Recall@10 on rows with `family: adjudication_replay`.
- Governance precision: >=95% precision on A0/A1 governance answers (A0 = CLAUDE.md; A1 = configs/ruling-graph/kill-registry).
- Cross-repo block (CTX-082..CTX-096): evaluated separately with Terminal and Mastermind projects opted-in; reported as a distinct family block in the eval report (CXI-R16).

## Append-only policy

This file is append-only after a freeze tag. Rows are never edited post-freeze except by
adjudicated fix passes (see Amendment log).

Future questions append after CTX-081 and receive the next sequential id. A new eval run
records a new version tag; prior runs remain unchanged.

## Families

| Family | Count | Description |
|---|---|---|
| `location` | 11 | Where does X live? |
| `code` | 8 | What does function/file X do? |
| `governance` | 11 | Is X allowed? What ruling applies? |
| `current_state` | 4 | What is the current status of X? |
| `gotcha` | 10 | What trap/failure mode exists for X? |
| `architecture` | 8 | How does system X fit together? |
| `contract` | 7 | What schema/contract governs X? |
| `research` | 6 | What is the finding/verdict on X? |
| `freshness` | 1 | How stale is artifact X allowed to be? |
| `operations` | 1 | Operational question |
| `adjudication_replay` | 16 | Does the repo already cover this proposed work? |
| `negative_control` | 13 | Negative controls (no_answer expected) |

v1.2 cross-repo note: rows CTX-082..CTX-096 reference Terminal (charting-app) and
Mastermind paths using the stored source_uri scheme `repo://<project-key>/<relpath>`
(e.g. `repo://terminal/signal_layer/contracts.py`, `repo://mastermind/MAINTENANCE.md`).
Each row's `project` field names the owning project so the eval harness opens the correct
per-project DB. These rows carry `visibility: private` and are only graded when those
projects are opted-in per CXI-R16.

See research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md CXI-R5/CXI-R16 for the minimum
family floors and cross-repo eval instructions.
