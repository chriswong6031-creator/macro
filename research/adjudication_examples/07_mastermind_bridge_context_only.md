# Mastermind Bridge — Context-Only Birth, Five Authority Booleans All False

**Source:** PRs #1567 (W1 Macro compiler), #1680 (W-B claim_reliability bridge key). Primary doc: `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

The Neural Web needed a bridge artifact that would give the Mastermind trading bot awareness of Neural Web synthesis (verdict, radar, contradictions, breadth, rotation, data-health) and per-candidate NW context (bottom sensors, options entry, graph conflicts). The question was: what authority shape allows context to cross the repo boundary without violating Article 1 or introducing scoring?

## What was decided (the holding)

- **Context-only birth:** the bridge is born with `is_context_only: true` and all five Mastermind context authority booleans false: `can_add_candidates`, `can_raise_size`, `can_loosen_cap`, `can_act_on_cortex_prose`, `can_change_regime` — all false at birth. Promotions (shrink-only direction) require pre-registered shadow definitions, accrued shadow evidence, Fable review, and a registry come-back date.
- **Dark ship default OFF:** `MASTERMIND_NW_CONTEXT` defaults OFF. The reader, runlog audit rows, and shadow-input accrual run from day one regardless of the flag (posture-decider discipline); only prompt and plane injection are gated.
- **Pre-registered arming condition:** after at least 5 consecutive builds with `nw_context status=present` (fresh, no reader errors) in the runlog, the operator may set `MASTERMIND_NW_CONTEXT=1` without further Fable review — the ruling IS the review for prompt-text-only promotion. Come-back 2026-07-19.
- **Staleness only shrinks:** stale/absent context disappears from prompts and planes; it can never make a book more aggressive. Verified: `_net_posture_tilt` counts only `status=='validated'` planes; absent/None-direction planes cannot create or lower a disagreement.
- **250-row / 200-KB caps:** candidate context is capped at 250 rows (with `gap_notes` entry on truncation) and 200 KB total. Expected real size 60-120 KB.
- **Candidate scope rule:** `candidate_context` covers only tickers named on `us_standouts` or `altdata/mastermind`, plus radar tickers ONLY where actionable NW context exists (bottom_state not WATCH, or trigger_tier non-null, or options row exists). Not all ~334 union tickers.
- **No names beyond candidate universe in prompts — CI-enforced:** the book_context block carries counts and macro-level contradiction records only; a CI test asserts no bottom-sensors symbol outside the intake union appears in serialized `book_context`.
- **Cortex prose stays out of seat prompts:** `seat_prompt_block()` excludes cortex prose; W2 carries a sentinel test proving memo text can never appear in seat-prompt output.
- **Mastermind does NOT join macro vendor stale:** the reader is NOT added to `macro_refresh._ANCHOR_DEFS` — an advisory artifact must not be able to mark the whole macro vendor stale.
- **`claim_reliability` bridge key (PR #1680):** adds `lobes['claim_reliability']` reading `site/qledger/track_record.json` (display, additive); mandatory standing_law honesty string emitted per desk; NO schema version bump (additive and backward-compatible); bridge remains dark (MASTERMIND_NW_CONTEXT defaults OFF).

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Cross-repo context bridge (context-only, auth all-false) | public/private boundary (new artifact) | **T2** (CONSTITUTIONAL) | Full packet + panel + operator sign-off |
| Dark ship default OFF | privacy/authority floor | **T0** (ROUTINE — deferred promotion already approved) | Operator sets flag after arming condition met |
| Pre-registered arming condition (>=5 builds) | conditional authority unlock | **T1** (CONSEQUENTIAL — pre-approved by Fable) | Operator action per pre-registered condition |
| `claim_reliability` bridge key (additive, display) | additive display field, no new authority | **T0** (ROUTINE) | Opus alone |
| 250-row/200-KB caps | ops/privacy floor | **T0** (ROUTINE) | Ops; no packet required |
| Candidate scope restriction | privacy enumeration | **T1** (CONSEQUENTIAL, per RUL-SUCC-11) | Opus + packet with field-level enumeration |

The cross-repo bridge is T2 at birth (public/private boundary change, new public artifact). The bridge artifact's all-false authority booleans are the T2 pre-condition that makes subsequent T0/T1 partial unlocks possible — any change to any authority boolean requires a new Tier 2 packet (RUL-SUCC-11 privacy floor).

## Lenses that did the work

- **Privacy (RUL-SUCC-11):** the dominant lens. The five authority booleans in `mastermind_context.py` are the privacy floor — all must remain false for a Tier 0 or Tier 1 decision. Proof that all five are unchanged is required in any packet touching the bridge (RUL-SUCC-11 hard-block if missing). The field-level enumeration of new fields (candidate_context, book_context, lobes) was required for the original T2 packet.
- **Authority:** `is_context_only: true` and `authorized=false` on all five booleans are machine-checkable via `tests/test_mastermind_context.py`. The bridge artifact carries the standing law string about kernel FDR clearance and de-escalation-only promotion direction.
- **Collision:** Mastermind transport was zero-touch: git sparse checkout of `site` already materializes `site/neuralwebdata/` on the bot's next refresh — no new sync plumbing needed.
- **Ops budget:** staleness-only-shrinks is the key safety property: a degraded or absent NW artifact cannot increase the book's aggressiveness. This is verified by an acceptance test (NW plane cannot appear in tilt contributors when status is not `'validated'`).

## Citable holding

A cross-repo context bridge is born with all authority booleans false and dark-ship default OFF; the five Mastermind context authority booleans in `mastermind_context.py` are the privacy floor (RUL-SUCC-11) and proof of their unchanged state is required in any future packet touching the bridge artifact.

## Ruling IDs

RUL-SUCC-11 (privacy floor — five authority booleans); §1.7 dark-ship ruling; arming condition; RUL-C2 (`claim_reliability` naming)
