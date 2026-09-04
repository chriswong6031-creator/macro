# W3 frozen spec — point-in-time observation history, transitions, corrections

`child: macro-flow-observatory-v2-w3-history-corrections-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §5 (corrections law), §10 (replay vector)`
`design authority: this spec. Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. A product-level append-only observation ledger exists, advanced only by the guarded
   lanes, with revision rows that never mutate closed observations; deterministic replay
   reconstructs what was knowable at any first-known time.
2. State transitions, onset, age, prior state, and rank change derive from the ledger
   (state_log remains ONLY the run/health journal — the split is documented in both
   modules' docstrings).
3. change_summary's `source_revisions[]` is real: a revised observation produces a
   revision row, a REVISED marker in what-changed, and no duplicate transition.
4. Same inputs → byte-identical ledger tail; duplicate advance idempotent; non-owner
   lanes cannot mutate; missing session ≠ transition; stale session does not advance age.
5. UI: state age renders on group rows ("3rd session in this state" form), prior state
   in the row LENS, revision markers in what-changed. EN/ZH parity; evidence crops for
   the new UI bits (dark+light EN 1440 minimum — this wave's UI delta is small).
6. Targeted suites green (2 known pre-existing cn_theme_tape failures excepted);
   contract-delta 0 introduced (new test file wired in the same commit); canonical
   rebuild committed; PR DRAFT/unlabeled; tree clean.

## 1. Ledger (`engine/flow_observatory/history.py`, new)

`data/flow_observatory/observations.parquet` — append-only. One row per
(entity_kind, entity_id, effective_session, revision_id):

| column | type | notes |
|---|---|---|
| entity_kind | str | `theme` \| `aggregate` \| `market` |
| entity_id | str | theme id / `southbound` / `market_read.themes` etc. |
| effective_session | date | the market session the observation describes |
| revision_id | int | 0 for first belief; +1 per correction |
| first_known_at | timestamp (UTC) | when OUR pipeline first held this belief |
| revised_at | timestamp or null | set on revision rows only |
| vel | float/null · abs_value float/null · quadrant str · state str · rank int/null | product observation |
| coverage_n | int/null · status str | leg/coverage context at observation time |

API: `append_observations(path, session, entities, now)` (guarded by the same
`asia_advance_enabled() or nightly_advance_enabled()` gate; idempotent: identical
values for an existing (entity, session) key → no row; changed values → revision row
with revision_id+1, revised_at=now; closed rows NEVER mutated in place — parquet
rewrite preserves prior rows byte-identically), `latest(path)` (max revision per key),
`replay(path, at)` (rows with first_known_at ≤ at, max revision among those),
`derive_states(ledger, entity)` → ordered per-session series with
`state_started/state_age_sessions/prior_state/rank_change` (skip-gap rule: a session
absent from the ledger creates no transition and does not advance age),
`revision_receipts(ledger, session)` → change_summary.source_revisions[].

Bootstrap: the ledger starts empty (state_log has no product rows on main yet — the
first guarded lane run after W1/W2 populates both). `derive_states` over an empty or
single-session ledger yields honest nulls ("first tracked session" note preserved).
Do NOT backfill from git history.

## 2. Wiring

- `changes.py`: `compute_changes` gains the ledger as its transition/rank source
  (state_log summaries stay as fallback until the ledger has ≥2 sessions — document
  the fallback and test both paths); `source_revisions` populated from
  `revision_receipts`. A revision produces a REVISED what-changed row, never a
  duplicate transition row.
- `contract.py`: per-row `state_started/state_age_sessions/prior_state/rank_change`
  now come from `derive_states` when ledger depth allows; sources[] `first_known_at`
  now real (from the leg's first ledger appearance) — closes the W1 limitation.
- Builder: appends observations after validate() passes, same lane gate, before
  desk.json write; ledger append failure logs + annotates but never kills the build.
- What-changed UI: revision row form EN "{name}: {session} data revised" ZH
  "{name}：{session}数据已修正" with LENS carrying old→new detail.
- Row age form: EN "session {n} in this state" ZH "本状态第{n}个交易日" (LENS: prior
  state + started date).

## 3. Tests (`tests/test_flow_observatory_history.py`, new — wire into the flow lane
run: step + ci.yml path gates in the SAME commit; add `data/flow_observatory/` paths
nowhere — data files are not CI path subjects)

1. append → same inputs → byte-identical file (hash compare);
2. duplicate advance idempotent (no new rows);
3. changed value → revision row; original row byte-preserved; `latest` returns the
   revision; `replay(before revised_at)` returns the original;
4. replay excludes observations first-known after the replay instant;
5. onset survives multiple same-state sessions; prior_state correct across a
   transition; missing session creates no transition and does not advance age;
6. stale session (leg status STALE at observation time) does not advance state age
   (age freezes; test the frozen-age path);
7. rank_change compares consistent universes (an entity absent from the prior session
   → rank_change null, not a fabricated delta);
8. non-owner lane (gate env unset) cannot append;
9. revision produces source_revisions[] + REVISED change row and no duplicate
   transition;
10. fallback path: ledger depth <2 → state_log-derived summaries still serve, with the
    "first tracked session" null note;
11. mutation M1: make append_observations mutate a closed row in place → tests 3 and 1
    fail (paste output).

## 4. Real proof (PR body)

Deterministic replay demo over a fixture ledger (3 sessions + 1 revision) showing
latest vs replay(t) divergence; UI crops of age + revision rows; bootstrap state
disclosed (empty ledger until first guarded lane run — first_known_at appears from
then); performance note (append is O(sessions×entities) parquet rewrite — measure at
22 themes × 250 sessions and state the cost; if >2s, propose partitioning in
DEVIATIONS, do not implement unasked); authority context_only.
