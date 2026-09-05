# Intraday Flow lifecycle P0 implementation plan

> **Operation:** `intraday-flow-opportunity-lifecycle-p0-20260905-sol-001`  
> **Architecture:** `research/INTRADAY_FLOW_OPPORTUNITY_OS_RULING_2026-09-05.md`  
> **Initial base:** `macro@443fe9a6f7d98484710452dc98f1aed58011c823`  
> **Initial branch:** `sol/intraday-flow-opportunity-lifecycle-p0-20260905`  
> **Delivery mode:** one existing branch / one Draft PR / one source writer after START  
> **Release state:** `DRAFT / HOLD-FOR-SOL` until exact-head review and production proof

## Goal

Prevent any Intraday Flow card whose canonical entry window has already opened, already run, failed, become blocked, or crossed its anti-chase boundary from rendering `Almost ready` / `Base in place — waiting for the open`.

The correction must be deterministic, null-safe, bilingual, and semantically identical in:

- the pure Python stance engine;
- the nightly/fastpath builder contract;
- browser-side live recomputation;
- the generated `site/intraday_flow.html` artifact;
- regular-session and off-hours rendering.

This plan deliberately stops after lifecycle truth. It does not build persistent setup episodes, a new score, an options strategy selector, trade authority, or the wider Opportunity OS.

## Architecture boundary

### Reuse

- `engine.entry_signal` remains the canonical snapshot timing owner.
- `engine.intraday_flow.stance` remains the board lane owner.
- existing live quote, pulse, live-flow, dealer, and source-clock owners remain unchanged.
- the existing six stance lanes remain the public lane vocabulary.
- existing template → generated-site publication remains the rendering path.

### Add

A small pure timing classifier, preferably in `engine/intraday_flow.py`, with an explicit contract equivalent to:

```python
def classify_entry_timing(
    *,
    entry_status: str | None,
    current_price: float | None = None,
    chase_above: float | None = None,
) -> dict[str, object]:
    ...
```

Required states:

```text
forming
active_window
already_moving
failed_or_blocked
unknown
```

Required meanings:

```text
forming           buy_soon | await_confluence | watch | bounce_wait
active_window     buy_now | partial
already_moving    hold | extended | wait_pullback | topping
failed_or_blocked exit | avoid | blocked
unknown           missing or unrecognized status
```

A finite current price strictly above a finite positive `chase_above` forces `already_moving`, regardless of an otherwise-forming status.

The classifier must expose enough reason identity for tests and UI explanations, for example:

```text
status_forming
status_active_window
status_already_moving
status_failed_or_blocked
above_chase
status_unknown
status_missing
```

Do not infer timing from English copy, substring matching, badge text, LLM output, or options premium.

### Stance precedence

Preserve the existing take-profit safety rule as the first conservative override. Then apply lifecycle gates:

1. existing `take_profits` evidence may still win;
2. `failed_or_blocked` cannot emit a positive setup lane;
3. `already_moving` cannot emit `act` or `get_ready`; it renders the existing `watch` lane with anti-chase copy;
4. `active_window` may emit `act` only when the existing live action gate is satisfied; otherwise it renders `watch` with “entry window already opened” copy;
5. `forming` may emit `get_ready` under the existing direct precursor/structure conditions, and may advance to `act` when current live evidence itself satisfies the existing action gate;
6. `unknown` cannot emit `act` or `get_ready` and must disclose unavailable timing;
7. remaining descriptive lanes retain their existing precedence only where they do not contradict the lifecycle gate.

Every return object must carry additive, backward-compatible timing metadata such as:

```text
timing_state
timing_reason
already_started
```

Do not rename or remove existing `key`, `lane`, `en`, `zh`, or `class` fields.

## Exact scope

Expected owned paths:

```text
engine/intraday_flow.py
scripts/build_intraday_flow.py
templates/intraday_flow.html.j2
site/intraday_flow.html
tests/test_intraday_flow_timing_lifecycle.py
tests/test_intraday_flow_stance.py
tests/test_intraday_flow_lifecycle_js.py   # or an exact extension of an existing executed-JS suite
```

Optional only when directly required by existing render/test mechanics:

```text
tests/test_intraday_flow_ncp_js.py
research/INTRADAY_FLOW_OPPORTUNITY_OS_RULING_2026-09-05.md
```

No other product, data, workflow, configuration, Agent OS, options-estate, Prophet, scoring, alert, or execution paths.

## Worktree and source-continuity setup

1. Use the exact existing branch and future Draft PR. Do not create a replacement branch or PR.
2. Fresh-fetch `origin/main` and verify the current branch ancestry before editing.
3. Use a fresh operation-owned linked worktree under the repository-approved session root.
4. Opt into `site/` before reading or writing generated output:

```bash
python3 scripts/worktree_sparse.py add site
python3 scripts/worktree_sparse.py status
```

5. Verify no other open branch/PR owns the exact engine/template/test paths.
6. Read `AGENTS.md`, `CLAUDE.md`, this plan, and the architecture ruling.
7. Run the committed RED test before the first implementation edit and preserve the output in the PR/carrier.
8. Emit the operation’s separate `START` immediately before the first source modification.
9. After the first pushed implementation head and before long CI/context exposure, produce the required `CHECKPOINT_VERIFIED` source-continuity receipt.

## Task 1 — prove the missing Python behavior

**Files:**

- committed RED: `tests/test_intraday_flow_timing_lifecycle.py`
- existing regression suite: `tests/test_intraday_flow_stance.py`

Run:

```bash
python3 -m pytest \
  tests/test_intraday_flow_timing_lifecycle.py \
  tests/test_intraday_flow_stance.py -q
```

Expected initial result: failure because `stance` does not accept/obey lifecycle inputs and does not return timing metadata. Record the exact failing tests; do not weaken them to make the current implementation pass.

The RED contract must cover:

- every forming status can still reach `get_ready` under direct eligible structure;
- `buy_now` and `partial` never regress to `get_ready`;
- `hold`, `extended`, `wait_pullback`, and `topping` never regress to `get_ready`;
- `exit`, `avoid`, and `blocked` never regress to `get_ready`;
- missing and unknown statuses never emit a positive setup claim;
- current price above `chase_above` overrides a forming status;
- a full live action gate still allows `buy_now` to emit `act`;
- conservative `take_profits` behavior remains available;
- every result exposes lifecycle metadata;
- all lifecycle copy has non-empty EN and ZH forms.

## Task 2 — implement the pure timing classifier

**File:** `engine/intraday_flow.py`

1. Add normalized constant sets for the four known timing families.
2. Normalize status with trim/lowercase only; do not use substring inference.
3. Treat booleans, mappings, lists, empty strings, NaN, infinity, non-positive `chase_above`, and unparsable prices as unavailable rather than truthy.
4. Apply the finite `current_price > chase_above` override.
5. Return a deterministic immutable-shape dict or frozen dataclass projection.
6. Add focused unit tests for exact mapping and null/numeric edge cases.

Run only the new classifier tests until green, then rerun Task 1’s combined suite.

## Task 3 — make `stance` lifecycle-aware without changing its authority

**File:** `engine/intraday_flow.py`

1. Add optional keyword arguments with safe defaults:

```text
entry_status
current_price
chase_above
```

2. Call the classifier exactly once per stance evaluation.
3. Preserve the existing dealer/extension/take-profit calculations.
4. Gate `act`, `get_ready`, and positive fallback lanes by timing state per this plan.
5. Keep the six existing lane keys; anti-chase and unavailable timing use `watch` or `stand_aside`, not a seventh lane.
6. Add exact EN/ZH copy:

```text
Entry window already opened — wait for live confirmation.
入场窗口已开启 — 等待盘中确认。

Already moving — wait for a reset; do not chase.
行情已启动 — 等待重置，切勿追高。

Setup is no longer actionable.
该形态已不再可执行。

Timing unavailable — no positive setup claim.
时机数据不可用 — 不作正面形态判断。
```

7. Return `timing_state`, `timing_reason`, and `already_started` on every path, including off-hours.
8. Update old stance tests so cases that intentionally expect `get_ready` declare an explicit forming status instead of relying on missing timing.
9. Add a mutation-style assertion that changing an active/late status to forming is the only status change that re-enables `get_ready` under the same legs.

Run:

```bash
python3 -m pytest \
  tests/test_intraday_flow_timing_lifecycle.py \
  tests/test_intraday_flow_stance.py -q
```

## Task 4 — carry the canonical anti-chase boundary into the board payload

**File:** `scripts/build_intraday_flow.py`

`_extract_stockdata_context()` currently carries status, stop, buy zone, ATR, and spot but omits the top-level canonical anti-chase line.

Add only:

```text
entry_signal.chase_above
```

Use `chase_above` as the canonical field. A compatibility read of `dont_chase_line` is permitted only if the existing stockdata contract demonstrably uses it, and the emitted board contract must still use one canonical name.

Tests must prove:

- present finite value is carried exactly;
- missing/invalid remains null;
- no value is derived from buy-zone high, ATR, call wall, expected move, or current price;
- no separate anti-chase owner is created.

## Task 5 — prove browser/Python semantic parity before browser implementation

**File:** `tests/test_intraday_flow_lifecycle_js.py` or a tightly scoped extension of an existing executed-JS suite.

Use the repository’s established Node extraction/execution pattern rather than text-only assertions. Execute the actual JavaScript extracted from both:

```text
templates/intraday_flow.html.j2
site/intraday_flow.html
```

Fixtures must include at least:

```text
ASTS-like forming structure + entry_status=hold -> not get_ready
ASTS-like forming structure + entry_status=buy_now -> not get_ready unless action gate is live
entry_status=buy_soon + price above chase_above -> already_moving/watch
entry_status=buy_soon + price below chase_above -> get_ready remains possible
entry_status=exit -> stand_aside or more conservative lane
missing/unknown status -> non-positive timing-unavailable state
```

The test must compare key lifecycle fields and lane identity with Python results for the same inputs.

Run the new JS test now. Expected initial result: RED because browser code ignores lifecycle and/or no longer matches the new Python contract. Preserve the output.

## Task 6 — implement browser lifecycle semantics

**File:** `templates/intraday_flow.html.j2`

1. Add a browser timing classifier with the exact same status sets, numeric guards, precedence, state names, and reason names as Python.
2. Feed it from the leader’s canonical `entry_signal.status`, current quote/pulse price, and `entry_signal.chase_above`.
3. Apply it before `computeStance` emits a positive lane.
4. Remove the current washout fallbacks that infer L1 from:

```text
entry_signal.status containing "buy"
vol_squeeze.coiled by itself
```

Direct washout-reclaim or bounded drawdown/recovery evidence owns L1; absent direct evidence is null, not false certainty.

5. Preserve options-flow, pulse, quote, dealer, and confluence owners.
6. Preserve existing lane keys and sort semantics in this P0.
7. Add timing metadata to the rendered card’s data model and explanation, without building a material UI redesign.
8. Apply the lifecycle guard in off-hours mode too.
9. Make `isMarketHours()` weekday-aware so Saturday/Sunday cannot be treated as regular hours. Do not create a new holiday-calendar owner in this PR; a known exchange-holiday integration remains separate.
10. Keep source freshness semantics independent: missing/stale quote, pulse, or options data must not be converted into a new positive timing claim.

## Task 7 — regenerate the committed site artifact

Use the canonical builder, never hand-edit the generated HTML.

Likely command after confirming repository usage:

```bash
python3 -m scripts.build_intraday_flow --mode nightly
```

If the canonical repository command differs, use its documented entry point and record it.

Then prove:

```bash
python3 scripts/check_template_site_sync.py
```

The template and site must contain identical lifecycle logic. No direct edit to `site/intraday_flow.html` is permitted.

## Task 8 — focused verification

Run:

```bash
python3 -m pytest \
  tests/test_intraday_flow_timing_lifecycle.py \
  tests/test_intraday_flow_stance.py \
  tests/test_intraday_flow_lifecycle_js.py \
  tests/test_intraday_flow_ncp_js.py -q

git diff --check
python3 scripts/check_template_site_sync.py
python3 scripts/check_design_system.py --mode enforce-added
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_title_i18n.py
python3 scripts/check_validated_claims.py
```

Use the exact supported CLI flags discovered from each script; do not suppress a genuine failure. If a script is not directly invokable with the shown form, record the supported equivalent.

Then run the repository’s binding changed-path CI/fence commands. Do not run the full test suite in a sparse worktree.

Required semantic assertions:

- no `status.indexOf('buy')` or equivalent substring timing/washout inference remains;
- no squeeze-only washout inference remains;
- no new weighted score/rank/authority exists;
- no options-flow field can by itself create a setup lifecycle state;
- no P0 change mutates collectors, data stores, workflows, Prophet, alerts, or execution;
- existing NCP numerator and soft-signing fixes remain intact;
- existing source clocks/null semantics remain intact.

## Task 9 — product/browser evidence

Before returning the PR, produce browser evidence at:

```text
dark  / EN / 1440
light / EN / 1440
dark  / ZH / 390
light / ZH / 390
```

At minimum show:

- a true forming card still showing `Almost ready`;
- an active-window card not showing `Almost ready`;
- an already-moving/above-chase card showing anti-chase copy;
- a failed/blocked card;
- timing unknown;
- missing/stale live inputs;
- off-hours rendering;
- weekend rendering.

The evidence may use deterministic production-shaped fixtures before merge. It must not be represented as natural production proof.

## Task 10 — immutable-head return and production proof boundary

Return on the exact carrier with:

```text
operation key
branch / PR
exact head SHA and tree SHA
base SHA and ancestry
changed-path census
RED receipt
focused test receipts
binding CI status
browser evidence paths
source-continuity checkpoint
open review threads
current collision census
all unresolved defects
```

Keep the PR `DRAFT / HOLD-FOR-SOL`, with:

```text
merge-on-green absent
autoMergeRequest null
no Ready transition
no merge/deploy claim
```

After independent exact-head review and Sol release, the same source operation may proceed through merge and real publication. Production acceptance still requires:

1. a real regular-session payload through the canonical quote/pulse/options path;
2. a naturally activated or already-moving name proving no stage regression;
3. an ASTS row if ASTS naturally supplies the required state, otherwise an equivalent natural name plus a separately captured ASTS payload;
4. off-hours proof from the same published build;
5. desktop and narrow-browser proof;
6. source/freshness clocks visible and truthful;
7. the existing `WS-INTRADAY-FLOW-P0-RECOVERY` PR-4 natural-session dossier remains open until its own acceptance contract is satisfied.

## Stop condition

Stop when this one capability is implemented, tested, reviewed, and returned on the exact Draft/HOLD PR:

> A card can never regress to pre-trigger `Almost ready` after its canonical entry window has opened, run, failed, become blocked, or crossed the anti-chase line.

Do not absorb P1 persistent episode storage, OA-1T flow-quality UI, opportunity scoring, options strategy construction, alerts, or signal promotion into this PR.
