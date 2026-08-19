---
document_type: execution_handoff
target_operator: Fable
title: HK + Canada Prophet Revamp — Hardened Execution Handoff
date: 2026-08-18
status: READY_FOR_EXECUTION
research_status: COMPLETE_AFTER_SIX_PASSES
primary_repo: mastermindx-market-intelligence/macro
secondary_repo: mastermindx-market-intelligence/Mastermind
terminal_repo: mastermindx-market-intelligence/mastermind-terminal
observed_macro_main: e554e15b419ad8371e68b020a56cb2bad108de75
observed_mastermind_main: b5e45be20a752b689e08a88d15816ef26fb2c45c
observed_terminal_main: e0ee554a8f8f94f353766a75f022a59afaed6a9a
proposed_agentos_workstream: WS:PROPHET-HK-CA-REVAMP
agentos_note: >
  This is an execution packet, not yet a valid AgentOS handoff record.
  Create/validate the workstream first, then point it at this artifact or mint
  the canonical agentos/handoffs record from the template in this document.
---

# HK + Canada Prophet Revamp — Hardened Fable Handoff

## 0. Mission

This is the final execution packet after six research passes plus a hardening pass.

The research phase is complete. Do not restart broad factor archaeology unless implementation reveals a concrete contradiction with a frozen fact here.

The shared constitution is:

> **Copy the US/China authority architecture, not their factor recipes.**
>
> **Discover broadly. Preserve what happened. Rank market-native intelligence. Gate entry independently. Promote narrowly. Grade cohorts separately.**

The two market failures are different:

| Market | Primary failure | Required response |
|---|---|---|
| Hong Kong | False negatives / candidate-recall starvation | Broaden discovery while keeping official promotion narrow |
| Canada | False positives / semantic-authority corruption | Repair truth and measurement before attempting new selection alpha |

The first implementation wave is **Canada truth repair**, not a new model.

---

# 1. Freshness pin and critical evidence

## 1.1 Main pins observed

- `macro`: `e554e15b419ad8371e68b020a56cb2bad108de75`
- `Mastermind`: `b5e45be20a752b689e08a88d15816ef26fb2c45c`
- `mastermind-terminal`: `e0ee554a8f8f94f353766a75f022a59afaed6a9a`

A compare from macro `ad1aa0a4ab3db659c3ac76834b2c07f5ff7b6ddc` to `e554e15b419ad8371e68b020a56cb2bad108de75` showed one intervening White House/data-site commit and no HK/Canada/Prophet code-path changes.

Before every authority-changing PR:

```bash
git fetch origin
git rev-parse origin/main
git status --short
git worktree list
```

After merge, verify the bytes that actually landed on `origin/main`. Do not reason from the local pushed commit alone.

## 1.2 Load-bearing anchors

### Canada production
- `scripts/build_canada_library.py`, fetched blob `abecee07c215369315b36d63bb8bb7427c429b02`
  - still contains stale "Alpha-led" doctrine
  - applies Branch-B ordering inside `compute_canada_standouts()`
  - later re-sorts that board using obsolete composite/confluence logic before writing `canada_standouts.json`
  - loads anticipation gate with `_load_gate("US")`
- `tests/test_canada_build.py`, blob `f0dc4d8b4a56230740c839024ffa7705ae10556e`
  - proves rendering semantics on a synthetic VM
  - does not prove persisted artifact order == page order == ledger order

### Evaluation
- `engine/board_ledger.py`, blob `ca5e842c5f03126cccca55a9eba6a03751852133`
  - keep-FIRST dedupe on `(date, ticker)`
  - `board_definition` exists
  - rank-IC is definition-scoped
  - group metrics/hit-rate remain pooled across definitions
  - next-bar fills, suspension exclusion, market-relative excess, MFE and terminal states already exist
- `tests/test_board_ledger.py`, blob `1e386c476227b02534b357b19537e942765f7e99`
  - explicitly pins keep-FIRST `(date,ticker)`

### HK production
- `engine/hk_board_rank.py`, blob `a937c0f705efe98f42ec220fdb720584f508a9af`
  - current definition `hk_prophet_v2`
  - imports shared US priority machinery/weights
- `engine/hk_stock_signals.py`, blob `cd6c2c66c783482f9de57c14aad16f01581c44dd`
  - explicitly frames the current fused edge as screen/flow-value-exposure, not validated selection alpha

### Research
- `reports/c7-canada-momentum-phase0.md`, blob `110e0a2f0090c88b88452d8e145209718916e633`: Canada Branch B; residual momentum ACCRUE
- `reports/c1-commodity-sector-phase0.md`, blob `561661be565fd89e171f7fc4632bbc8170011f3f`: oil→XEG ACCRUE at sector level, not name alpha
- `reports/hkca-h3-phase0.md`, blob `fca877b366b8815fcd6f9b70ed23b43326b307d1`: H3 DSR 0.879, ACCRUE
- `reports/hkca-x1-phase0.md`, blob `56d74b2ab692011672c60004959d4a99f21a15ab`: A-twin 1M lead DSR 0.846, ACCRUE

### Downstream
- Mastermind `portfolio/registry.py`, blob `f5eb632d8f2d8dfcdbe11abb19076f9d746b38fe`: HK Brain active; Canada absent
- Mastermind `brain/hk_mcp.py`, blob `6318c86203a8264843fbccfb0f844dce7394f109`: consumes `factordata/hk_standouts.json`

### Canonical architecture
- US V4 freeze: candidate != pick; discovery/maturity/availability/intelligence/uncertainty/outcome are separate; missing != zero; no feedback loop; no alternate grader; no cross-era pooling.
- PIT replay harness: US/CN/HK implemented; Canada explicitly unresolved on bake lane, price surface, capture stores, session semantics.
- AgentOS: knowledge plane only, not dispatch/gating/runtime authority.

---

# 2. Frozen diagnosis

## 2.1 Hong Kong

HK frequently had useful information outside the official admission path while the official funnel was too dependent on fresh-cross/cascade semantics. The resurrection autopsy found severe admission starvation and cases where leadership/display organs saw the move while the board did not.

Later display shelves improved visible breadth but did not change graded admission/ranking. Removing the impossible 200DMA reclaim gate improved recall but did not prove generic selection alpha.

Therefore HK must:
1. broaden upstream candidate recall;
2. preserve candidate observations prospectively;
3. rank with HK-native evidence families;
4. keep entry availability independent;
5. keep official-pick authority narrow.

Do not solve HK by tightening the gate further, and do not solve it by calling every visible shelf row a pick.

## 2.2 Canada

Canada research said Branch B, composite suppressed, screen/ripe-list authority, residual momentum ACCRUE.

Production still contains stale alpha-led machinery and a second sort after Branch-B ordering. Historical Canada board rows also lack a clean definition fence for selection metrics.

Therefore Canada's first problem is **epistemic plumbing**, not alpha discovery.

---

# 3. Non-negotiable laws

1. Candidate is not pick.
2. Screen is not validated selection alpha.
3. Entry timing is not stock-selection evidence.
4. Sector opportunity is not issuer selection.
5. Missing is not zero.
6. Stale is not missing.
7. A board output may not feed its own upstream score.
8. Historical eras are never relabeled.
9. Current-model performance may not silently pool legacy definitions.
10. The incumbent remains published while a challenger accrues unless promotion explicitly changes authority.
11. Same-population ranking and population-changing discovery are different experiments.
12. No challenger gets a private grader.
13. HK/CA do not create a permanent second generic candidate identity/lifecycle plane.
14. No HK retune silently changes shared US scoring behavior.
15. Workflow green is not settlement; production-reader/source-session proof is required.
16. Proposed schema is not existing truth.
17. No winner is selected in advance.
18. No performance claim is made from a cohort whose selection definition cannot be reconstructed.
19. Forward evidence clocks are never reset because results are inconvenient.
20. Post-merge `origin/main` bytes beat local intent.


# 4. Authority matrix

| Plane | Canonical owner | HK/CA allowed responsibility | Forbidden |
|---|---|---|---|
| Security/company identity | existing identity/Data OS owners | consume IDs and listing identity | mint competing identity truth |
| Candidate discovery | market adapter / future V4 candidate plane | market-native candidate reasons, high-recall observations | imply endorsement |
| Candidate lifecycle | V4 canonical candidate-episode plane when available | attach market events/reads | create permanent second generic episode OS |
| Intelligence families | market adapters + governed Fusion owner | define family inputs/status/provenance | build ungoverned parallel master ranker |
| Cross-family fusion | Conditional Fusion/governed registry | market configuration/families | fork fusion machinery |
| Entry availability | deterministic entry authority | market-specific structural inputs | let score/theme waive blockers |
| Risk hygiene | existing risk/placement modules | demote/block where authorized | masquerade risk screen as alpha |
| Outcome grading | Evaluation OS / `engine.grading` | cohort definitions/stamps | alternate return calculator |
| Board publication | current market builders | publish promoted definition only | publish shadow as live |
| Brain/autonomous use | Mastermind runtime | consume accepted public board | consume experimental challenger pre-promotion |
| AgentOS | knowledge plane | ownership/decisions/discoveries/handoffs | dispatch, gate or arbitrate liveness |

---

# 5. Hard STOP conditions

If any condition below is reached, stop the wave and record it. Do not route around it inside the same PR.

## Canada STOPs

- `canada_standouts.json`, page VM and ledger cannot be proven to derive from one ordered canonical board.
- Any second rank transform remains after canonical Branch-B ordering.
- A live consumer of the Canada artifact cannot be resolved before a breaking schema change.
- Legacy Canada rows would need rewriting to produce clean current-definition metrics.
- A current-definition scorecard can only be obtained by deleting historical rows.
- Canada PIT replay would require synthesizing vintage rows instead of executing vintage lane code.
- A name-ranking proposal uses C1 oil sector state as if it were proven issuer alpha.

## HK STOPs

- Challenger work requires changing shared US `SCORE_WEIGHTS`.
- Shadow collection requires overwriting `hk_standouts.json`.
- Candidate discovery is judged using visible-card count alone.
- H3 or X1 is promoted merely because it is close to 0.90.
- Challenger uses board rank/featured/manual-selection state as an upstream feature.
- Placement/risk flags are credited as positive alpha without separate evidence.

## Shared STOPs

- New code duplicates Evaluation OS, Stock Identity, Theme Graph, Earnings Intelligence or generic candidate lifecycle ownership.
- A same `(date,ticker)` incumbent row must be overwritten to store a population-changing challenger.
- Unknown required availability input defaults to pass.
- An absent evidence family defaults to numerical zero.
- Post-merge main bytes disagree with intended PR content.
- One PR changes discovery, ranking and entry authority together without a written exception.

---

# 6. Canada P0A — single canonical truth

## 6.1 Exact defect

Current Canada flow effectively does:

1. compute candidate setups;
2. apply Branch-B order;
3. stamp Branch-B metadata;
4. later apply obsolete composite/confluence sorting to `wide["buy"]`;
5. apply entry-open-first again;
6. write the raw artifact;
7. separately derive the page-facing path.

This permits **Branch-B labels over non-Branch-B order**.

That is a production defect, not a research disagreement.

## 6.2 Required target

There must be one canonical Canadian board object per session.

Recommended conceptual API:

```python
canonical = build_canada_board(...)
```

Proposed shape, not existing contract:

```yaml
as_of: YYYY-MM-DD
board_definition: ca_prophet_branch_b_v1
authority: screen
selection_status: accruing
official_pick_authority: false
rank_basis: momentum_screen_accruing
rows:
  - ticker: ...
    board_pos: 1
    group: entry_open|setting_up|watch
    screen_evidence: ...
    entry_signal: ...
```

The existing `buy` transport key may survive temporarily, but only as a projection of canonical rows. It must never be separately ranked.

## 6.3 Parity invariant

For an owed Canada session:

```text
ordered_tickers(canonical board)
==
ordered_tickers(canada_standouts.json canonical projection)
==
ordered_tickers(page view-model canonical projection)
==
ordered_tickers(board-ledger current-definition calls)
```

If display-only rows exist outside the graded cohort, name and hash that difference explicitly.

## 6.4 Proposed PR: CA-TRUTH

### Owns
- `scripts/build_canada_library.py`
- `scripts/build_canada.py`
- `templates/canada.html.j2` only if additive authority language requires it
- `tests/test_canada_build.py`
- contract-export paths only if additive fields require them

### Must change
- remove second post-Branch-B re-sort;
- remove duplicate independent page ordering;
- define one canonical ordered board;
- stamp first prospective Canada `board_definition`;
- add explicit screen authority semantics;
- preserve compatibility transport if consumer census is incomplete.

### Must not change
- C7 research verdict;
- selection-alpha claim;
- universe;
- TSXV coverage;
- board-ledger dedupe key;
- US/HK code;
- entry thresholds.

### Definition boundary
Recommended proposed name:

`ca_prophet_branch_b_v1`

If naming has advanced by execution time, use the next lawful definition. Never backfill it onto legacy rows.

### Required tests
- `test_canada_canonical_board_is_single_source_of_truth`
- `test_canada_artifact_page_order_parity`
- `test_canada_ledger_order_matches_canonical_board`
- `test_canada_no_second_sort_after_branch_b`
- `test_canada_legacy_buy_key_is_projection_not_authority`
- `test_canada_current_rows_stamp_board_definition`
- `test_canada_legacy_rows_remain_unstamped`
- `test_canada_official_pick_authority_false_under_branch_b`

### Mutation kills
Each must fail:
- re-add `_combine_key` sort;
- call `entry_open_first` after Branch-B order;
- swap two artifact rows only;
- omit `board_definition`;
- set official-pick authority true;
- independently regenerate page order.

### Production proof
After first owed TSX session:
- correct source session;
- page/artifact ordered cohort match;
- ledger current rows carry new definition;
- legacy rows remain unchanged;
- Branch B still honest;
- no Canada autonomous consumer newly armed.

---

# 7. Canada P0B — era-clean evaluation

## 7.1 Defect

`board_ledger.scorecard()` fences rank statistics to the latest definition but leaves group-level selection metrics pooled.

For Canada, a clean new board could therefore still display a hit rate contaminated by the old ambiguous era.

That must be fixed before anyone quotes a new Canada win rate.

## 7.2 Target contract

Recommended additive shape:

```yaml
market: CA
current_definition:
  board_definition: ca_prophet_branch_b_v1
  n: ...
  n_buy: ...
  n_ic_dates: ...
  rank_ic: ...
  hit_rate_21d: ...
  by_group: ...
  mean_excess: ...
  terminal_states: ...
historical_context:
  legacy_rows: ...
  definitions: ...
  note: historical context only; not current-model track record
```

Do not delete old grading. Do not relabel it.

## 7.3 Proposed PR: LEDGER-ERA

### Owns
- `engine/board_ledger.py`
- `tests/test_board_ledger.py`
- scorecard consumers only if needed

### Must change
- definition-scope current selection metrics;
- preserve all historical grading;
- expose historical/legacy context explicitly;
- keep fill/suspension/benchmark behavior unchanged.

### Must not change
- dedupe identity;
- stored historical definitions;
- next-bar rule;
- suspension rule;
- benchmark semantics;
- forward outcome values.

### Required tests
- `test_ca_current_definition_hit_rate_excludes_legacy`
- `test_ca_current_definition_by_group_excludes_legacy`
- `test_ca_current_definition_n_excludes_legacy`
- `test_ca_historical_context_keeps_legacy`
- `test_hk_existing_definition_behavior_does_not_regress`
- `test_rank_ic_definition_fence_still_holds`
- `test_keep_first_date_ticker_still_holds`

### Mutation kills
- use all-era frame for current hit rate;
- restamp legacy rows;
- drop legacy rows;
- include suspended rows;
- use signal-bar instead of next-bar fill.

---

# 8. Explicit board-ledger non-change

Do **not** globally migrate the live board ledger from:

```text
(date, ticker)
```

to:

```text
(date, ticker, board_definition)
```

Reasons:
- current tests pin keep-FIRST `(date,ticker)`;
- HK PIT replay absorption relies on current semantics;
- same-session identity would change across mature consumers;
- HK/CA remediation does not require that blast radius.

Use challenger-specific storage instead.

---

# 9. Challenger storage contract

## 9.1 Same-population rank challenger

Question:

> Given the exact same candidates, does the challenger order them better?

Pair challenger fields to the incumbent observation/outcome.

Recommended fields:

```yaml
incumbent_definition: ...
incumbent_rank: ...
challenger_definition: ...
challenger_rank: ...
challenger_score_raw: ...
challenger_score_conservative: ...
challenger_coverage: ...
```

No second outcome clock. No private grader. Prefer one active ranking challenger per market unless the governed Fusion owner explicitly supports more.

## 9.2 Population-changing discovery challenger

Question:

> Does a broader/different origination process surface opportunities the incumbent never sees?

Use a separate **zero-authority research observation store**.

Proposed minimal grain:

```text
session_date
market
ticker/security reference
challenger_definition
candidate_origin
first_seen_at
emergence reads
native family statuses/values
availability read
visible_to_user=false
published_authority=false
```

It must not mint:
- new company/security identity truth;
- new generic lifecycle truth;
- new outcome labels;
- new earnings/theme truth;
- production board authority.

When canonical V4 `prophet.candidate_episode/v1` is available cross-market, adopt/migrate rather than maintaining a permanent duplicate.


# 10. Hong Kong program

## 10.1 Freeze incumbent

Current incumbent:

`hk_prophet_v2`

It remains the published definition until a challenger passes promotion.

Do not call the experimental definition `v3` merely because work starts. Mint the next production definition only at promotion.

## 10.2 Discovery objective

The new HK discovery plane optimizes **opportunity recall**, not card count.

Candidate origins may include, only with explicit deterministic definitions:

- structural washout/reclaim emergence;
- leadership emergence;
- ripening/pre-confluence;
- aged-but-still-structurally-valid turn;
- recent blocked-signal receipt;
- HK-native evidence onset;
- A/H dislocation emergence;
- A-twin lead/read-through emergence.

These are candidate reasons, not buy reasons.

No producer cap. UI caps are allowed.

The research store must preserve enough data to answer:

> Was this opportunity visible to the research system before it won?

## 10.3 Initial HK family table

| Family | Starting status | Allowed role |
|---|---|---|
| H3 A/H own-history discount | ACCRUING | selection evidence |
| X1 A-twin 1M momentum lead | ACCRUING | selection evidence |
| Southbound level | context | positioning/context |
| Southbound delta ranker | measured negative / NO-GO | not rank authority |
| Connect inclusion | NO-GO | not alpha |
| beta-neutral RS | screen | candidate/intelligence input only until separately promoted |
| HK global-beta/regime fit | context | exposure/context |
| HK leadership | context/discovery | discovery/tiebreak/display |
| placement/rights/open-offer | risk hygiene | demotion/blocking only |
| confluence/cascade | availability/maturity | entry/timing, not intelligence |

### Null law

For every family:

```text
NOT_APPLICABLE != UNAVAILABLE != STALE != PARTIAL != 0
```

Recommended shared status vocabulary:

- `MEASURED`
- `PARTIAL`
- `STALE`
- `NOT_APPLICABLE`
- `UNAVAILABLE`
- `ACCRUING`
- `RIGHTS_BLOCKED`
- `PRODUCER_DEGRADED`

A name with no A-share twin must never receive A/H score `0`.

## 10.4 Fusion/rank boundary

Do not retune shared US `SCORE_WEIGHTS`.

Do not create a permanent ungoverned `hk_master_score`.

HK owns:
- family adapters;
- family status/provenance;
- market-specific configuration;
- candidate-origination semantics.

Conditional Fusion/governed ranking infrastructure owns:
- cross-family fusion machinery;
- anti-double-counting;
- family registry rules;
- shadow race machinery where applicable.

If governed Fusion cannot yet host HK cleanly, build a narrow shadow adapter, not a second permanent fusion OS.

## 10.5 Availability

Availability remains independent.

A name may be:
- highly interesting + `WAIT_PULLBACK`;
- highly interesting + `RAN_DONT_CHASE`;
- highly interesting + `UNAVAILABLE_DATA`;
- moderately interesting + `ENTRY_OPEN`.

Score never waives blockers.

Placement risk remains independent hygiene.

Maturity/confirmation does not itself grant permission to buy.

## 10.6 Shadow publication law

Before promotion:

```text
challenger -> research store only
incumbent hk_prophet_v2 -> hk_standouts.json -> HK Brain
```

Never:

```text
challenger -> hk_standouts.json for "just a test"
```

HK Brain already consumes the published artifact. Therefore publishing the challenger is an authority transition.

---

# 11. Canada program after P0

## 11.1 Freeze Branch B as the honest incumbent

After CA-TRUTH and LEDGER-ERA, Canada should have:

- a clean prospective definition;
- screen authority;
- one canonical order;
- era-clean evaluation;
- no validated stock-selection-alpha claim.

That is the baseline a challenger must beat.

## 11.2 Research decomposition

Target decomposition:

```text
sector opportunity/context
    ->
issuer/name intelligence
    ->
entry availability
```

Do not fuse these into one score at birth.

### Sector opportunity

C1 oil→XEG may be typed:

`ACCRUING sector opportunity/context`

It may not directly name winning issuers.

Gold/copper remain NO-GO unless a new preregistered mechanism is tested.

### Name intelligence

Residual momentum is one ACCRUING family, not the authority.

The issuer-selection problem remains open.

New mechanisms require preregistration and an explicit economic/causal story.

### Entry

Confluence and `entry_signal` remain entry/timing.

They may improve entry quality.

They may not be credited as selection alpha.

## 11.3 Inherited US gate audit

Current Canada code loads:

```python
_load_gate("US")
```

Every inherited component must receive one of four explicit dispositions:

- `STRUCTURAL_COMMON`
- `MARKET_VALIDATED`
- `SCREEN_SHADOW`
- `RETIRE`

An unclassified inherited US gate may not become binding in a new Canada authority definition.

## 11.4 No TSXV in the initial revamp

Do not expand to TSXV in the first Canada model program.

Reasons:
- current TSX names panel already has survivorship limits;
- PIT replay is unresolved;
- issuer-selection authority is unresolved;
- TSXV adds liquidity/identity/regime complexity and degrees of freedom.

TSXV can be a later explicitly chartered universe expansion.

---

# 12. Canada artifact-semantics migration

The legacy transport key `buy` is semantically dangerous.

Do not immediately break it until consumers are censused.

## Stage A — additive compatibility

Recommended additive fields:

```yaml
board_definition: ca_prophet_branch_b_v1
authority: screen
selection_status: accruing
official_pick_authority: false
legacy_buy_key_semantics: ripe_list_screen
```

The legacy `buy` key becomes a projection.

No consumer may infer official-pick authority from membership alone.

## Stage B — breaking schema only after consumer census

Preferred canonical vocabulary:

```yaml
candidates: [...]
entry_available: [...]
official_picks: [...]
```

Field names are proposals.

All projections must come from one source object.

A compatibility alias, if temporarily required, must be mechanical and explicitly deprecated.

---

# 13. Unresolved `bot:canada_book` consumer

Macro's artifact contract declares a Canada-book consumer while current visible Mastermind source has no Canada bot/registry entry.

Possible states:
- stale manifest;
- external/deployed consumer;
- incomplete visible source estate.

Do not guess.

Before a breaking Canada schema change:

1. search current Macro/Mastermind/Terminal sources;
2. inspect manifest/export consumers;
3. inspect deployment/runtime references available to Fable;
4. resolve whether `bot:canada_book` is live, stale or external;
5. write a Discovery/Decision if the answer is durable.

Until then, use additive compatibility fields.

---

# 14. Evaluation design

Win rate is not enough.

Each authority plane has its own race.

## 14.1 Candidate-discovery race

Metrics:
- eventual-winner recall;
- time-to-first-surface;
- candidate MFE;
- candidate MAE;
- clean-liftoff rate;
- dead-money/stopped rate;
- catastrophic-outcome rate;
- omitted-winner/top-K regret;
- coverage/degraded rate.

A discovery system does not win by surfacing more names alone.

## 14.2 Ranking race

Use the **same candidate population**.

Metrics:
- rank-IC;
- top-1/top-5/top-decile excess;
- clean-liftoff rate by rank bucket;
- MFE/MAE by rank bucket;
- catastrophic loss frequency;
- coverage-adjusted performance;
- rank stability where relevant.

No credit for a broader candidate set.

## 14.3 Availability race

Use the **same selected names**.

Metrics:
- return conditional on `ENTRY_OPEN`;
- MFE after entry;
- MAE after entry;
- `RAN_DONT_CHASE` frequency;
- stopped/dead-money frequency;
- wait-pullback opportunity cost;
- stale/unavailable-data rate.

No credit as selection alpha.

## 14.4 Official-pick race

Only this cohort may eventually support statements like:

> Prophet official picks had X% positive 21-day market-relative outcomes.

Never substitute candidate/screen performance.

Never quote the user's observed Canada ~30% as independently verified.

---

# 15. Evidence clocks and promotion

## 15.1 Existing research bars

Where applicable, retain the governing program's existing discipline:

- DSR >= 0.90;
- predeclared HAC-t threshold;
- multiple-testing correction where search/family exists;
- split/era stability;
- effective-N honesty;
- survivorship bound;
- no leakage;
- no post-result metric substitution.

Do not lower the bar because:
- H3 is 0.879;
- X1 is 0.846;
- C1 oil is 0.541;
- C7 residual momentum looks intuitively useful.

ACCRUE means ACCRUE.

## 15.2 Board-race promotion additionally requires

- same-tape incumbent/challenger comparison for the declared plane;
- enough independent sessions/episodes to avoid one-regime promotion;
- no unresolved liveness/coverage defect;
- no unexplained family-availability asymmetry;
- complete authority stamps;
- production-reader proof on shadow telemetry;
- written promotion decision;
- reversible definition switch;
- incumbent remains prospectively available as shadow where feasible.

Do not invent a new sample-size threshold if a governing owner already has one. Reuse the owner.

---

# 16. PIT and local context

## 16.1 Local regime

Do not build a second HK/CA local-regime history store.

Use the existing point-in-time signal archive for prospective research context.

Do not backfill pre-archive local regimes from mutable `regime_history.parquet`.

If local regime becomes a live rank feature, that is a new authority decision with its own provenance/freshness contract.

## 16.2 Canada replay

Canada PIT replay remains unresolved.

Parallel work may fill:
- bake slot/lane;
- price surface;
- capture stores;
- session validity;
- control fidelity;
- stage-and-absorb hook.

This is required before reconstructed historical Canada sessions support retrospective same-tape claims.

It is **not** required before honest forward shadow accrual begins.

---

# 17. Liveness is model correctness

For each owed session, acceptance must prove the production reader is on the correct source session.

Recommended settlement receipt:

```yaml
market: HK|CA
owed_session: ...
source_asof: ...
artifact_asof: ...
board_definition: ...
rank_basis: ...
authority: ...
universe_count: ...
canonical_board_count: ...
ordered_ticker_digest: ...
page_projection_digest: ...
ledger_projection_digest: ...
degraded_sources: [...]
served_bundle_sha: ...
```

Preferred invariant:

```text
artifact canonical digest
==
page canonical projection digest
==
ledger canonical cohort digest
```

If display-only rows are intentionally outside the graded cohort, compute a separate display digest and name the difference.

Workflow green without this proof is insufficient.


# 18. PR / wave graph

## Wave 0 — collision and consumer preflight

### W0-A

Actions:
- re-pin main;
- compile/read AgentOS context for overlapping Prophet/Fusion/Eval work;
- grep `owns_paths`;
- run `git worktree list`;
- resolve `bot:canada_book` enough to choose additive vs breaking compatibility;
- verify no sibling PR owns P0 paths.

Exit only when path ownership is clear.

---

## Wave 1 — CA-TRUTH

**Goal:** one canonical Branch-B board, one prospective definition, explicit screen authority.

Entry gates:
- W0 complete;
- no conflicting worktree/PR on owned paths.

Exit gates:
- parity tests green;
- mutation kills green;
- no second sort;
- no legacy restamp;
- artifact/page/ledger same current cohort;
- post-merge `origin/main` byte proof;
- first owed-session reader proof.

Rollback:
- revert producer code;
- preserve any already-written new-definition rows as historical receipts;
- never relabel them.

---

## Wave 2 — LEDGER-ERA

**Goal:** current-definition selection metrics are era-clean.

Depends on Wave 1.

Exit:
- current-definition hit rate excludes legacy;
- current-definition group metrics exclude legacy;
- legacy remains queryable;
- HK behavior does not regress;
- keep-FIRST identity untouched.

---

## Wave 3 — SHADOW-CONTRACT

**Goal:** lawful challenger storage for ranking and discovery.

Depends on Wave 2.

Exit:
- same-pop ranking shadows share outcome truth;
- population-changing discovery cannot collide with production rows;
- shadow store has zero publish authority;
- no alternate grader.

---

## Wave 4 — LOCAL-CONTEXT-ADAPTER

**Goal:** standard prospective reader over existing HK/CA signal archive.

Can run parallel after Wave 2.

Exit:
- no mutable-history backfill;
- archive is not silently promoted into live ranking authority;
- timestamps/nulls explicit.

---

## Wave 5 — HK-DISCOVERY-SHADOW

**Goal:** broaden candidate recall upstream without touching live publication.

Depends on Wave 3.

Exit:
- prospective high-recall observation store populated;
- every row has deterministic candidate reason;
- no producer cap;
- no `hk_standouts.json` change;
- no HK Brain change.

---

## Wave 6 — HK-NATIVE-INTEL

**Goal:** explicit HK family registry/adapters/status semantics.

Depends on Wave 5.

Exit:
- H3/X1 remain ACCRUING;
- NO-GO families cannot contribute positive rank;
- missing != zero;
- no shared US weight changes;
- no board-derived input.

---

## Wave 7 — HK-RANK-RACE

**Goal:** same-population HK-native rank challenger vs `hk_prophet_v2`.

Depends on Wave 6.

Exit:
- exact same candidates;
- same outcomes;
- paired ranks;
- coverage reported;
- live artifact unchanged.

---

## Wave 8 — HK-ORIGINATION-RACE

**Goal:** evaluate broader discovery separately from ranking.

Depends on Waves 5-7.

Exit:
- candidate-recall metrics separated from rank metrics;
- no promotion from card count;
- no publication change.

---

## Wave 9 — CA-NATIVE-INTEL

**Goal:** explicit sector/name/entry authority separation.

Depends on Waves 1-4.

Exit:
- C1 oil typed sector context only;
- residual momentum typed ACCRUING family only;
- inherited US gate classified;
- no generic composite authority.

---

## Wave 10 — CA-RANK-RACE

**Goal:** challenger ranking on the same clean Branch-B population.

Depends on Wave 9.

Exit:
- same population;
- same outcomes;
- no official-pick claim;
- live artifact unchanged.

---

## Wave 11 — CA-SECTOR-NAME-ACCRUAL

**Goal:** prospective sector-opportunity -> issuer evidence studies.

Depends on Wave 9.

Exit:
- mechanisms preregistered;
- no C1 sector-to-name assumption;
- no killed-family resurrection without a new hypothesis.

---

## Wave 12 — CA-PIT-REPLAY

**Goal:** resolve general PIT harness registry for Canada.

Can proceed in parallel after Wave 2.

Exit:
- control pass;
- complete declared price surface;
- session validation;
- capture stores;
- vintage-lane row creation;
- stage-and-absorb;
- fail-closed gap handling.

---

## Wave 13 — promotion

Separate HK and Canada decisions.

No shared "revamp complete" switch.

HK can promote while Canada remains Branch B.

Canada can remain permanently screen-only if no issuer-selection edge earns promotion.

---

## Wave 14 — Canada Brain

Mastermind follow-up only after Canada information-product authority is trustworthy.

Not part of initial Prophet repair.

---

# 19. Mandatory adversarial tests

## 19.1 Canada truth
- artifact/page/ledger ordered-ticker parity;
- second-sort reintroduction fails;
- Branch-B metadata/order coupling;
- current rows definition stamped;
- legacy rows untouched;
- screen authority explicit;
- legacy `buy` cannot imply official pick.

## 19.2 Evaluation
- current-definition hit rate fenced;
- current-definition by-group fenced;
- historical context preserved;
- suspension excluded;
- next-bar unchanged;
- benchmark unchanged;
- keep-FIRST unchanged.

## 19.3 Shadow substrate
- same-pop challenger cannot change production membership;
- population-changing challenger cannot write production row;
- challenger cannot overwrite same ticker/date incumbent;
- one outcome clock;
- no alternate grader.

## 19.4 Null/family semantics
- A/H no-twin => `NOT_APPLICABLE`, not zero;
- missing feed => `UNAVAILABLE`/`PARTIAL`;
- stale => `STALE`;
- stale family excluded from current score unless contract explicitly says otherwise;
- unavailable family cannot improve conservative score via denominator artifacts.

## 19.5 Anti-feedback
Poison:
- board rank;
- featured flag;
- manual selection;
- plan status;
- live lane.

Prove upstream intelligence is unchanged.

## 19.6 Availability
- poison intelligence score and prove availability unchanged;
- remove required availability input and prove unavailable/not-ready, never green.

## 19.7 HK publication
- inject extreme challenger score and prove `hk_standouts.json` remains incumbent pre-promotion;
- prove HK Brain receives no challenger-only row.

## 19.8 Liveness
- stale artifact fails owed-session proof;
- green workflow + stale content still fails;
- degraded cache/source is named;
- artifact/page/ledger digest mismatch fails.

## 19.9 Post-merge proof
After each authority-changing merge:
- fetch/show relevant `origin/main` bytes;
- compare to intended contract;
- treat mismatch as blocker even if CI merged green.

---

# 20. Rollback law

Rollback is a **definition switch**, not historical erasure.

Never:
- delete losing shadow rows;
- relabel old definitions;
- reset evidence clocks;
- rewrite historical scores under new code;
- silently pool rolled-back/restored eras;
- erase a promoted definition because it disappointed.

If the restored implementation is contract-equivalent to a prior definition, it may resume under it.

If materially changed, it is a new definition.

---

# 21. Do-not-redo register

Do not:
- revive HK residual momentum as primary alpha;
- promote Southbound delta ranker;
- use Connect inclusion as alpha;
- use generic HK deep-loser reversal;
- promote H3 at DSR 0.879;
- promote X1 at DSR 0.846;
- treat ripening-card count as candidate success;
- treat placement risk as positive alpha;
- restore Canada residual momentum as primary authority;
- call C1 oil a name-level edge;
- revive gold/copper transmission without new preregistered mechanism;
- revive COILED-CA;
- revive generic Canada bank seasonality on the old sample;
- call US confluence Canada selection alpha;
- expand to TSXV during initial repair;
- retune shared US weights for HK;
- change discovery + rank + entry in one race;
- globally migrate board-ledger identity;
- backfill Canada definitions;
- create duplicate grader/identity/lifecycle/theme/earnings systems;
- publish HK challenger pre-promotion;
- automate Canada Brain before Prophet authority is trustworthy;
- claim Canada ~30% was independently reproduced;
- promise a future win-rate target before an era-clean cohort exists.

---

# 22. Definition of done

## 22.1 HK

"Done" is not "14 cards instead of 2."

Done means:
- broad legitimate early opportunities are preserved;
- candidate recall is measurable;
- intelligence is HK-native and evidence-typed;
- entry is independent;
- official promotion is narrow;
- incumbent/challenger compare on same tape;
- Brain consumes only promoted authority;
- forward evidence supports the promoted definition.

Illustrative product state, not a target:

```text
30 candidates worth research
8 rank highly on current HK-native intelligence
3 have valid current entry
2 have earned official-pick authority
```

## 22.2 Canada

"Done" is not "higher momentum score."

Done means:
- one board truth;
- one clean prospective era;
- current track record does not pool legacy;
- screen authority explicit;
- sector context separated from issuer selection;
- entry separated from selection;
- official picks may remain empty until earned;
- future Canada Brain has a trustworthy contract.

Illustrative product state, not a target:

```text
20 screen candidates
6 have acceptable entry structure
energy has an accruing sector tailwind
0 names have validated official-pick authority yet
```

That is better than false precision.

---

# 23. Fable's exact first actions

Execute in this order:

1. Re-pin current main.
2. Run AgentOS collision/context checks.
3. Resolve `bot:canada_book` enough to select additive vs breaking compatibility.
4. Open **CA-TRUTH only**.
5. Prove canonical board parity and mint first prospective Canada definition.
6. Post-merge verify `origin/main` bytes and first owed-session production receipt.
7. Open **LEDGER-ERA**.
8. Only after both are accepted, open challenger substrate work.
9. Begin HK discovery shadow and Canada native-intelligence work in parallel only where path ownership does not collide.
10. Do not publish a new HK/Canada definition until a separate promotion decision.

The sequencing law is:

> **Repair truth -> repair measurement -> create shadow substrate -> accrue -> compare -> promote.**

Not:

> new score -> new cards -> declare improvement.


# 24. AgentOS integration packet

This document is intentionally not pretending the new workstream already exists.

## 24.1 Proposed workstream

Proposed key:

`WS:PROPHET-HK-CA-REVAMP`

Before using it:
- search `agentos/workstreams/`;
- confirm the key does not already exist;
- confirm no more specific current HK/Canada Prophet workstream owns the same paths;
- verify `program` against `config/mastermind_programs.yml`;
- verify any P0 reference against Mastermind strategic state;
- run `python3 scripts/agentos.py validate`.

Recommended metadata:
- owner: `Fable`
- class: `build`
- blast_radius: `user_facing`
- ambiguity: `scoped`
- repos: `[macro, mastermind]`

Recommended path ownership is deliberately narrow:

```yaml
owns_paths:
  - scripts/build_canada_library.py
  - scripts/build_canada.py
  - engine/board_ledger.py
  - engine/hk_board_rank.py
  - engine/hk_stock_signals.py
  - scripts/build_hk_library.py
  - tests/test_canada_build.py
  - tests/test_board_ledger.py
  - research/*HK*CANADA*
```

Do **not** claim generic Fusion, Evaluation OS, Identity or V4 lifecycle paths owned elsewhere.

## 24.2 Recommended workstream waves

```yaml
waves:
  - id: ca-truth
    title: Canada canonical board truth
    status: todo
  - id: ledger-era
    title: Era-clean HK/CA scorecard semantics
    status: todo
    depends_on: [ca-truth]
  - id: shadow-contract
    title: Rank/discovery shadow substrate
    status: todo
    depends_on: [ledger-era]
  - id: hk-discovery
    title: HK candidate-recall shadow
    status: todo
    depends_on: [shadow-contract]
  - id: hk-intel
    title: HK native intelligence adapters
    status: todo
    depends_on: [hk-discovery]
  - id: hk-race
    title: HK ranking and discovery races
    status: todo
    depends_on: [hk-intel]
  - id: ca-intel
    title: Canada sector/name/entry authority split
    status: todo
    depends_on: [shadow-contract]
  - id: ca-race
    title: Canada rank and sector-name accrual
    status: todo
    depends_on: [ca-intel]
  - id: ca-pit
    title: Canada PIT replay resolution
    status: todo
    depends_on: [ledger-era]
  - id: promotion
    title: Separate market promotion adjudications
    status: todo
    depends_on: [hk-race, ca-race]
```

If HK and Canada are later split into child workstreams, preserve this packet as the integration artifact. Do not duplicate all architecture prose into two drifting copies.

## 24.3 Handoff template for implementation sessions

Once the workstream exists, mint the canonical AgentOS handoff under:

`agentos/handoffs/PROPHET-HK-CA-REVAMP-YYYY-MM-DD.md`

The handoff must conform to `agentos.handoff.v1`.

Template:

```yaml
---
workstream: WS:PROPHET-HK-CA-REVAMP
session: <branch-or-worktree>
model: fable
ended_because: complete|ci_handoff|blocked|context_budget|crashed
mission: >
  <exact wave mission>
state_before: >
  <what origin/main did before the session>
changed:
  - path: <path>
    what: <exact change>
verified:
  - claim: <specific claim>
    command: <command>
    result: <result>
unverified:
  - claim: <remaining uncertain claim>
    what_would_verify: <specific verifier>
unresolved:
  - <remaining issue>
next_actions:
  - <concrete ordered action>
do_not_redo:
  - <settled non-action that prevents duplicate work>
danger_areas:
  - <fragile seam>
prs: [<number>]
---
```

Do not use "see above" or rely on session memory.

A cold stranger must be able to continue from the handoff alone.

## 24.4 AgentOS operating discipline

Before starting a wave:

```bash
python3 scripts/agentos.py compile-context --workstream PROPHET-HK-CA-REVAMP --text --budget 6000
grep -rl "owns_paths" agentos/workstreams/
git worktree list
```

Treat AgentOS claims as advisory only.

Do not infer live worker activity from a claim record.

Do not hand-edit generated AgentOS rollups.

One independently useful capability per PR.

---

# 25. Final acceptance checklist

## Truth
- [ ] Canada has one canonical board producer.
- [ ] Artifact/page/ledger current-cohort parity proven.
- [ ] Canada clean definition starts prospectively.
- [ ] Legacy rows are unchanged.
- [ ] HK incumbent remains explicit.

## Measurement
- [ ] Current-definition Canada selection metrics are era-clean.
- [ ] Same-pop rank races share one outcome truth.
- [ ] Population-changing discovery has separate zero-authority observations.
- [ ] Candidate/rank/availability/official-pick metrics are separated.

## Architecture
- [ ] Missing != zero.
- [ ] Stale != missing.
- [ ] No board feedback loop.
- [ ] No shared US-weight retune for HK.
- [ ] No duplicate generic lifecycle/identity/grader.
- [ ] Fusion ownership respected.
- [ ] Evaluation ownership respected.

## Publication
- [ ] HK challenger cannot reach live artifact pre-promotion.
- [ ] HK Brain consumes only accepted authority.
- [ ] Canada legacy transport semantics explicit.
- [ ] Breaking Canada schema waits for consumer resolution.

## Data/PIT
- [ ] Local regime research uses PIT archive.
- [ ] No mutable-history backfill is presented as PIT.
- [ ] Canada PIT replay is resolved, or historical replay claims remain forbidden.

## Liveness
- [ ] Owed-session source/served proof exists.
- [ ] Stale artifact cannot pass because workflow is green.
- [ ] Degraded sources are named.
- [ ] Post-merge `origin/main` byte proof is complete.

## Promotion
- [ ] Promotion metrics were predeclared.
- [ ] Evidence clock was not reset.
- [ ] No threshold was lowered post-result.
- [ ] Challenger beat incumbent on the declared job.
- [ ] Rollback is a definition switch, not erasure.

---

# 26. Final directive

Fable should begin implementation with **CA-TRUTH**.

Do not start by improving HK score weights.

Do not start by training a Canada ranker.

Do not start by adding Canada Brain.

The fastest lawful path is:

```text
Canada truth repair
    ->
era-clean evaluation
    ->
shadow substrate
    ->
HK high-recall discovery + HK-native intelligence
    ||
Canada sector/name/entry separation
    ->
forward races
    ->
separate promotion decisions
    ->
Canada Brain only after Canada Prophet earns a trustworthy authority contract
```

The settled research conclusion is:

> **HK needs better recall without authority inflation.**
>
> **Canada needs better authority precision without suppressing the screen.**
>
> **Both need evidence-preserving architecture before they need another score.**
