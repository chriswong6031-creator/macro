# PR-0B — cn_prophet_v4 telemetry preservation (builder commission)

**Program:** `WS:CHINA-ALPHA-INTELLIGENCE` wave `pr0b` · **Route:** build (Sonnet `builder`)
**Authority:** `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` §13 PR-0B; `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`.
**Spawn note:** paste this file as the commission; SECTION labels below are the routed-spawn contract.

ROUTE: build

MISSION: Prospectively persist the full `intel_interest` anatomy into the
canonical China candidate research plane, so future causal diagnosis of the
live champion's ordering is possible. Today the plane persists NONE of it.

WHY: `cn_prophet_v4` (live champion since 2026-08-15) orders by
`intel_interest_score`, but `data/china_prophet_rank/candidates.parquet` — the
canonical full-universe research population — records no intel fields at all,
and even the live board JSON keeps only a compact subset. Every nightly that
passes without this telemetry is a nightly whose champion-ordering anatomy is
unrecoverable (historical recomputation is never described as prospective
served history — masterplan §15.23). This is the R4 (v4-vs-v3) and L-track
diagnosis substrate.

SCOPE:
- Verified pins (2026-08-19): compute site `engine/china_intel_interest.py:284`
  `interest_score()` returns (L323-338) `definition, basis, score, signal_core,
  signal_source, edge_remaining, edge_components, gap, lead_up, gap_mult,
  falsifier_penalty, falsifiers, drivers, excludes`. The board attaches a
  subset via `engine/china_board_rank.py:471-505` `_attach_intel()`
  (`intel_interest_score`, `intel_interest_basis`, compact `row["intel"]`).
  The candidate-plane writer `engine/china_prophet_shadow.py` `_row_record`
  (L359-470; columns L53-98) carries NO intel keys — confirmed absent.
- Add the full anatomy to the candidate plane's per-row record: score, basis,
  definition, signal_core, signal_source, edge_remaining, edge_components,
  gap, lead_up, gap_mult, falsifier_penalty, falsifiers, drivers, excludes,
  plus an `intel_unavailable_reason` for names where the coverage-atomic guard
  refused (missing/coverage failure is never zero — masterplan §15.22).
  Complex components serialize as JSON strings if the parquet schema needs it —
  follow the plane's existing `_OBJECT_COLUMNS` pattern.
- SINGLE-COMPUTE INVARIANT: one `interest_score()` evaluation per name per
  nightly, shared between the board attach and the candidate-plane record —
  find the seam in the nightly build orchestration (`scripts/build_china_library.py`
  → `engine/china_board_rank.py` / `engine/china_prophet_shadow.py`) and pass
  the computed map through rather than computing twice. If the plumbing truly
  forces a second compute, a test must assert board-attached and plane-persisted
  shared fields are equal for the same name/date.

OUT OF SCOPE: No rank/ordering change of any kind (v4 ordering, v3 shadow,
lanes, gates, caps untouched). No historical backfill and no fabricated served
values — new columns are absent/null for all pre-merge rows. No new store, no
schema fork: extend the existing plane in place (schema-union, keep-first
append semantics preserved). No edits to `engine/china_standout_track.py` or
any grading surface. No `data/` bytes committed from your session (nightly is
the sole advancer of `data/`; this worktree family is sparse — NEVER
`git add` a `data/` diff).

FROZEN SPEC: The masterplan §13 PR-0B block + the pins above. Field names
match `interest_score()` return keys prefixed `intel_` where a bare name would
collide with existing plane columns.

OWNED FILES: `engine/china_prophet_shadow.py`, the orchestration seam that
feeds it (minimal touch), new/extended tests. Nothing else.

TESTS: (1) unit: fixture record through the extended `_row_record` shows the
full anatomy and null-safety for refused names; (2) equality: board-attach vs
plane-persist share values for the same input (or single-compute demonstrated
structurally); (3) ordering-invariance: rank output on a fixture population is
byte-identical pre/post change; (4) schema: append to an existing fixture
parquet with old columns succeeds (schema-union). Run targeted tests only —
NOT the full suite in a sparse tree.

NOT DONE UNLESS: all four tests green; zero diff in any ordering/board output
on fixtures; no `data/` in the PR diff; `python3 scripts/agentos.py validate`
still exit 0; PR merged (own the ship loop: commit → push → PR → arm
merge-on-green → merged) and the WS record wave `pr0b` flipped to
**`BUILT_NOT_PROVEN`** — NOT `done` — in the same PR.

COMPLETION LAW (masterplan §0-bis, binding): merge proves BUILT; the real
nightly proves LIVE. Wave `pr0b` flips to `done` ONLY when a real production
nightly has written new candidate-plane rows carrying the intel anatomy and
the receipt is recorded in the WS record (run id + verification output). The
verification a follow-up session runs against a full checkout:
`git log --oneline -1 -- data/china_prophet_rank/` then read the newest rows
and assert `intel_` columns non-null for covered names and
`intel_unavailable_reason` set for refused names. Your PR body must state
this proof is deferred-prospective, name that command, and name whose job the
flip is (the follow-up verification session, never yours at merge time).

RETURN: STATUS / RESULT / EVIDENCE (test outputs, PR number, ordering-invariance
proof) / GAPS / DEVIATIONS.
