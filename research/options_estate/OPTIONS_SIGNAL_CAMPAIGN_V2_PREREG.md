# Options signal campaign v2 — frozen preregistration

Status: rule and authority freeze at exactly `2026-08-11T13:24:00Z`, before
canonical v2 publication. The immutable 2026-08-10 episode corpus was already
available when this contract was designed. Any revision whose final member
predates the freeze is therefore labeled `retrospective_context` and cannot be
counted as forward evidence. A final-member clock at or after the freeze is
`prospective_after_rule_freeze`.

The pre-existing eight-row `options.signal_campaign/v1` threshold cohort is a
frozen legacy retrospective ledger. It is neither this canonical contract nor
evidence for selection, optimization, lifecycle promotion, sizing, trading, or
training. Its bytes must never be rewritten by the v2 producer.

## Purpose and authority

`options.signal_campaign/v2` is an append-only census of exact-contract option
flow episodes. It preserves how membership evolves without interpreting opening
versus closing intent or turning repeated prints into a directional call.

Every revision and outcome is research-only and `training_eligible=false`.
Origination, selection, score, rank, gate, size, issue, trade, pick publication,
escalation, option-P&L, Neural Web, and Prophet-training authority are all false.
No public or private decision surface consumes these artifacts.

## Frozen grouping and revision rule

1. Strictly validate every `options.signal_episode/v1` source row; reject
   duplicate keys, duplicate episode ids, duplicate source identities, non-finite
   numbers, malformed clocks, and non-canonical strikes.
2. Group exactly by `(session_date, ticker, right, expiration, strike_key)`.
   Preserve exact numeric strike identity rather than coercing through IEEE-754.
3. Admit every valid group, including a singleton. There is no premium,
   frequency, side, unusualness, or outcome threshold and no ranking/truncation.
4. Order members by `(available_at, episode_id)`. The stable `campaign_id` is a
   hash of schema, frozen grouping policy, and the complete group key.
5. The first observed source prefix emits revision 1 containing its full ordered
   member set. A later source-prefix extension emits a new revision with the same
   campaign id, an incremented revision number, and an exact supersedes link.
6. Existing members and their canonical source rows may not shrink, reorder, or
   drift. A new member must lie beyond the prior committed source prefix.
7. Descriptive totals and side counts are raw census evidence only. Intent stays
   unavailable/soft and disposition stays `abstain`.

Each revision binds the exact episode prefix by path, record count, canonical
prefix SHA-256, and bytes. Member receipts include source row and canonical row
SHA-256. `formed_at` is exactly the final member's availability clock.

## Frozen outcome rule

Emit at most one `options.signal_campaign_outcome/v1` row for each immutable
revision and each horizon `h60`, `eod`, `1d`, `3d`, `5d`, and `10d`.

- The only label anchor is the revision's final member. Its source outcome must
  use the same `horizon_anchor` as the campaign's `formed_at`.
- Underlying return, MFE, and MAE are copied from that one exact receipt-bound
  source row. They are never averaged or aggregated across members.
- Other member outcomes are reference-only coverage receipts. Their presence,
  absence, or values cannot change membership or the anchor label.
- Complete source outcomes must retain the frozen Polygon price receipt. Honest
  terminal-incomplete rows may carry null price-receipt fields.
- Option P&L is unavailable and all option return/MFE/MAE fields remain null
  until an executable point-in-time bid/ask path exists under a later contract.
- If the final-member outcome is not yet present, the revision/horizon remains
  pending and is retried by a later normal nightly run.

## Sole writer, order, and crash recovery

`scripts/build_options_signal_campaign.py`, through
`engine/options_signal_campaign.py`, is the sole normal-nightly producer. It
runs only after the episode builder succeeds and owns exactly:

- `data/options_signal_campaign/campaigns.jsonl`;
- `data/options_signal_campaign/outcomes.jsonl`; and
- `data/options_signal_campaign/checkpoint.json`.

The engine first validates every committed source/output row and the previous
checkpoint, then plans revisions and outcomes from exact prefixes. It atomically
replaces the revision ledger, atomically replaces the outcome ledger, and writes
the deterministic checkpoint last. A crash before checkpoint is replayable: the
next run validates the already-landed append-only bytes and produces the same
checkpoint. Source or output shrink/drift fails closed.

The workflow publishes those exact three files in a narrow metadata replay.
Episode publication separately owns exactly episodes, H+60 outcomes, session
outcomes, and the episode checkpoint. A late visible gate fails the engine job
if either builder or either narrow publisher fails, after unrelated rendering
has had a chance to finish. Each narrow publisher builds an unreachable
`commit-tree` candidate and never advances local `HEAD`; timeout or cancellation
cannot strand an unverified commit or make newer upstream bytes appear locally
modified. The broad engine commit restores/unstages all seven owned paths rather
than smuggling a refused append through `git add data/`.

## Required falsifiers and promotion gate

- shuffled in-memory group/map enumeration over one exact immutable source prefix
  produces byte-identical revisions and outcomes; rewriting or shuffling the
  source ledger itself is prefix drift and fails closed;
- final-member clocks immediately before, exactly at, and immediately after the
  frozen instant classify as retrospective, prospective, and prospective;
- adjacent integer strikes above `2^53` remain distinct exact campaign keys;
- singleton groups persist and threshold-based admission cannot reappear;
- late members append linked revisions; backdated insertion, shrink, reorder,
  source drift, duplicate semantic keys, and forged receipts fail closed;
- a campaign label always equals the final member's exact source outcome and
  never a member average or hindsight-selected row;
- output append followed by pre-checkpoint crash replays byte-identically;
- non-nightly execution cannot write; the legacy v1 ledger hash is unchanged;
- every authority flag remains identically false.

This wave proves only canonical publication and prospective evidence accrual.
Selector, optimizer, lifecycle, Today/Pulse, rank, size, trade, publication, and
training phases remain gated until their own versioned preregistration, adequate
prospective sample, leakage audit, stability checks, and explicit authority
promotion all pass. No row count observed before this freeze is a success target.
