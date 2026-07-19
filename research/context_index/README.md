# Macro Context Index — Benchmark

## Version

v1, frozen 2026-07-18, 81 questions (CTX-001..CTX-081).

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

Promotion gates (from research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md CXI-R5/CXI-R6):

- Global: >=90% Recall@10 across all 81 rows.
- Adjudication-replay family: >=90% Recall@10 on rows with `family: adjudication_replay`.
- Governance precision: >=95% precision on A0/A1 governance answers (A0 = CLAUDE.md; A1 = configs/ruling-graph/kill-registry).

## Append-only policy

This file is append-only after a freeze tag. Rows are never edited post-freeze except by
adjudicated fix passes. This pass (v1 freeze, 2026-07-18) is the first and only adjudicated
fix pass for the v1 benchmark.

Future questions append after CTX-081 and receive the next sequential id. A new eval run
records a new version tag; prior runs remain unchanged.

## Families

| Family | Count | Description |
|---|---|---|
| `location` | 9 | Where does X live? |
| `code` | 8 | What does function/file X do? |
| `governance` | 10 | Is X allowed? What ruling applies? |
| `current_state` | 4 | What is the current status of X? |
| `gotcha` | 8 | What trap/failure mode exists for X? |
| `architecture` | 8 | How does system X fit together? |
| `contract` | 4 | What schema/contract governs X? |
| `research` | 6 | What is the finding/verdict on X? |
| `freshness` | 1 | How stale is artifact X allowed to be? |
| `operations` | 1 | Operational question |
| `adjudication_replay` | 12 | Does the repo already cover this proposed work? |
| `negative_control` | 10 | Negative controls (no_answer expected) |

See research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md CXI-R5 for the minimum family
floors (>=10 negative controls, >=10 governance/superseded tests met).
