# Options / Market Memory context audit — the 4,096 ledger bound

**Adjudication, 2026-08-13.** Raised by PR #5524 §"Flagged, not acted on" item 2, which measured a
scheduled failure in the options-intelligence estate and correctly declined to act on it inside a
CI heal. This document is the decision it asked for.

---

## §0 Verdict

**A preregistration v2 is the only honest fix, and it has a hard deadline of roughly 2026-08-20.
There is no stopgap.**

The obvious cheap cure — bounding the audit's input at the auditor level, which is where PR #5524
cured its sibling problem — is **closed**, not by taste but by measurement: it would manufacture
nulls inside a live preregistered evidence family (§4). The other reachable shortcut, a shadow
validator module that leaves the pinned file untouched, passes the pin's *check* while defeating
the pin's *purpose*, and is rejected in §5.

What ships now (§6) is therefore not a fix. It is an early-warning tripwire that converts a silent
dated outage into an actionable CI signal, plus the removal of one bound that was contradicting the
repo's own sizing of the same file. The actual fix is chartered in §7.

---

## §1 What fires, and when

`data/options_signal_episode/episodes.jsonl` grows every nightly checkpoint and is never pruned.
**Four** ceilings sit at 4,096, and only the first is movable:

| # | Bound | Location | Movable? |
|---|---|---|---|
| 1 | `_MAX_LEDGER_ROWS = 4_096` | `scripts/audit_options_market_memory_context.py:28` | **yes** — auditor is unpinned |
| 2 | `_MAX_REFERENCES = 4_096` — caps `len(references)` **and** every source artifact's `record_count` | `engine/options_market_memory_context.py:43,929,962` | **no** — byte-pinned |
| 3 | campaign-replay corpus caps on `episodes` and `h60_outcomes` | `engine/options_market_memory_context.py:677-680` | **no** — byte-pinned |
| 4 | receipt HEAD `reference_count <= 4096` | `engine/options_market_memory_receipt_store.py:403` | **no** — byte-pinned |

Both engine files are pinned by
`research/options_estate/sparse_selector_preregistration_receipt_v1.json` under
`selector_rule.required_truth_receipts.konseki.contract_receipts[]`, as
`reference_validator_implementation` (45,021 B / `7d3b410f…`, verified byte-identical on the tree)
and `receipt_store_validator_implementation` (21,818 B). Three
`contracts/options/options.market_memory_context_*.schema.json` files and
`config/market_memory_canary.v1.json` are pinned alongside them.

Probed directly against the pinned validator: `record_count=4096` passes, `4097` raises
`source artifact record count is invalid`; 4,097 episodes or h60 rows fed to the campaign replay
raise `campaign … corpus exceeds the bounded reference set`.

### The countdown is ~6-7 sessions, not ~3 nights

PR #5524 read the growth as "~822 rows/night". The ledger has been written exactly **twice**:

```
  384 rows  2026-08-11  feat(options): land durable PIT episode ledgers (#5324)
1,206 rows  2026-08-13  options-pit: durable episode checkpoint 2026-08-13
```

The +822 was a **two-session catch-up**, not one night — bucketed by `session_date` it is
`2026-08-11: 307` and `2026-08-12: 515`. Per-session mint across the three observed sessions is
**384 / 307 / 515** (mean 402). Headroom is 2,890 rows, so the wall falls **5.6-7.2 sessions out —
about 2026-08-20/21**.

Treat that as a range, not a date. Mint volume is event-density-driven, not universe-driven:
2026-08-12 produced the *most* episodes (515) from the *fewest* tickers (31), one ticker alone
contributing 168. A volatile week compresses it.

`outcomes_h60.jsonl` is a second capped source artifact and must be tracked too, and for it the
**byte** dimension binds first: 969 rows at 1,985 B/row projects to ~8.13 MiB at 4,096 rows, so its
8 MiB `_source_artifact` cap fires just *before* its row cap. It trails episodes by roughly 9-10
sessions, so it is not the near-term deadline — but a rows-only instrument would let it walk
through the wall.

### Blast radius

`scripts/project_market_memory_context.py:170` calls `publish_live_audit` with no `try`/`except`,
after the trusted projection has already published. The nightly `macro-market-memory-context` unit
fails every night thereafter, the options context receipt stops refreshing, and
`tests/test_market_memory_trusted.py::test_options_context_live_audit_replays_the_frozen_repository_corpus`
turns main red fleet-wide.

---

## §2 4,096 is an anomaly, not a considered sizing

The repo has already sized **this exact artifact**, deliberately and with evidence.
`engine/neuralweb/market_memory_production_records.py:55,74-76`:

```python
SOURCE_ARTIFACT_REL = "data/options_signal_episode/episodes.jsonl"
...
MAX_SOURCE_BYTES = 48 * 1024 * 1024
MAX_SOURCE_DELTA_BYTES = 16 * 1024 * 1024
MAX_SOURCE_ROWS = 25_000
```

`research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md:1723-1728`
records the work behind those numbers — a hostile cold-store test at 10,384 rows / 15.8 MiB
measuring 340.5 MiB peak RSS and 79.3 s against the service's 2 GiB / 300 s limits — and closes
with the standing instruction:

> "Reaching that mark requires a separately reviewed chunked-store v2; operators must not silently
> raise v1 bounds."

So the same file is governed by two capacities that differ by **6× in rows and 6× in bytes**. The
25,000 figure is reasoned and tested; 4,096 is a generic bound that arrived in a validator and was
never sized against this artifact. That asymmetry — not the countdown — is the real argument for
v2: the fix is to make the pinned bound agree with the sizing the house already did, once,
deliberately, rather than to bend the audit's meaning around the anomaly.

---

## §3 Why the audited input must shrink, if anything shrinks

The receipt binds a source artifact per audited path carrying `sha256`, `bytes` and `record_count`,
and the pinned validator caps `record_count` at 4,096. It also *couples* the two
(`engine/options_market_memory_context.py:1100-1109`):

```python
if (source_counts["data/options_signal_episode/episodes.jsonl"]
        != counts["episode_references"] ...):
    _fail("audit owner source counts differ from reference counts")
```

`record_count` is therefore forced equal to the episode reference count. Emitting fewer references
while still binding the whole file is not merely dishonest, it is **arithmetically impossible**.
Nor can a fifth artifact be added: `_SOURCE_PATHS` is frozen inside the pinned engine and
`build_audit_receipt` requires exactly those four in that order.

So if anything is to be bounded, it must be **the audited input itself**. §4 is why it cannot be.

---

## §4 Why windowing the audit is closed — the measurement that decided it

The preregistration does not only pin bytes; it binds this receipt into a decision path.
`selector_rule.required_truth_receipts.konseki`:

```
owner_binding            = campaign_v2_final_member_episode/v1
publication_binding      = authenticated_current_private_head_contains_exact_reference/v1
missing_or_absent_action = abstain
exact_absence_reason     = exact_requested_as_of_context_absent
```

A proposal is admissible only when the authenticated current private HEAD contains the exact
reference for the candidate campaign's **final-member episode**. An episode whose reference is
absent from the HEAD produces an abstention that is, downstream,
**indistinguishable from a genuine `exact_requested_as_of_context_absent` null**. Evicting owners
to save a buffer would be manufacturing evidence nulls in a preregistered family — the one thing
the estate's epistemics forbid outright.

The question is then purely empirical: could a bounded window still cover everything the binding
can reach? **No.** Measured on `data/options_signal_campaign/campaigns.jsonl` — campaign v2 is
live and nightly-written by `scripts/build_options_signal_campaign.py`:

```
campaign v2 rows                      1,146
distinct final-member episodes        1,146   (one per row)
final members by session   08-10: 369 | 08-11: 288 | 08-12: 489
member source_row range               1 .. 1206     (ledger has 1,206 rows)
```

Campaign v2 forms a campaign for ~95% of episodes, its bindings reach the **first row of the
ledger**, and the bound set grows 1:1 with the ledger forever. There is no newest-anchored window,
no budget, and no retention rule that covers it. **The (b) branch is closed on measurement, not on
preference.**

For the same reason, freezing the audit at the closed v1-era 384-row prefix is worse, not safer: it
evicts every future episode at once.

---

## §5 Options considered and rejected

**Rotate or shard the episode ledger.** Closed. `market_memory_production_records.py:62,707-748`
hashes the first `ACTIVATION_PREFIX_ROWS = 384` rows against a pinned digest, pins
`ACTIVATION_LAST_EPISODE_ID`, requires `record_count >= 384` and enforces append-order by
`available_at`; dropping the head raises `pre-activation owner source prefix mutated`. Campaign v2
additionally pins `source_episode_prefix` as the exact leading byte prefix with 1-based
`source_row` indices, so sharding renumbers and invalidates every published campaign row. The path
itself is `const` in two schemas.

**A shadow v2 validator module — explicitly rejected.** Copying the engine to a new module with a
larger bound and pointing the auditor at it would leave the pinned file untouched, so
`build_options_sparse_selector_prereg.py --check` would stay green and every pinned digest would
still match. It must not be done. The pin exists so that the receipt is produced by *that exact
reviewed validator*; satisfying the byte check with an unreviewed sibling is reinterpreting the
registration in place, which
`research/options_estate/OPTIONS_SPARSE_SELECTOR_PREREG.md:183-185` forbids in terms:

> "Any candidate, decision, lifecycle, quote, or metric rule change creates a new version and a new
> forward cohort. This registration cannot be reinterpreted in place."

Recording it here because it is the cheapest-looking path and a future session will find it.

**Raise the pinned constant in place.** Not available. The pin is byte-granular, so it cannot
distinguish a rule change from a buffer change; any edit moves `selector_rule_sha256` and trips
`origin_main_hosting_requirement` with failure action
`global_abstain_new_version_and_future_nyse_boundary_required`. There is also no v2 machinery:
`build_options_sparse_selector_prereg.py` exposes only `--repo-root` and `--check`, and the v1
schema pins every `version_fence` field — including `rule_change_policy` — as a JSON Schema
`const`.

---

## §6 What ships in this PR

Not a fix — a tripwire and one honest correction. Confined to
`scripts/audit_options_market_memory_context.py` and `tests/test_market_memory_trusted.py`; no
pinned byte moves.

1. The auditor's own unpinned read bounds go to **25,000 rows / 48 MiB**, matching §2's sizing of
   the same file, so the auditor stops being the first thing to fail and stops contradicting the
   repo's considered capacity. This buys nothing on its own — the binding ceiling becomes the
   pinned 4,096 — and the comment says so.
2. A two-tier tripwire on `episodes.jsonl` and `outcomes_h60.jsonl` independently, over **both**
   the row and the byte dimension (the byte tiers are the same fraction of the pinned 8 MiB
   ceiling that the row tiers are of 4,096, so it is one declared rule rather than two — and it is
   what keeps h60, whose byte cap binds first, from slipping past a rows-only instrument). At
   **2,600 rows** it emits a GitHub `::warning` annotation — naming the count, the headroom in rows
   and sessions, the pinned ceiling, and §7 as the owner of the fix — without failing. At **3,600
   rows** it fails.

   The split is deliberate. A single early hard-fail would red main fleet-wide and block every
   unrelated PR for a week over a deadline that has not arrived; a single late one would leave
   barely a session of lead time, which cannot buy a preregistration v2. So the warn tier fires
   about three sessions out and the fail tier about one — the latter still landing *before* the
   nightly unit starts crashing rather than after. The test also asserts the pinned ceiling it
   guards is still 4,096, so it cannot silently stop guarding.

The currently-red campaign replay (`campaigns.jsonl` 8 rows vs 20 derived from the grown ledger) is
**not** touched here: PR #5524 owns that heal and is armed.

---

## §7 Chartered: preregistration v2

Required before ~2026-08-20. Scope, in the house pattern already set by campaign v1→v2 (a new
frozen document plus a new implementation, with v1 left byte-frozen):

* A new receipt schema, builder and receipt — v1's schema cannot express a v2 rule.
* A new forward NYSE boundary, since `selector_effective_freeze_at` and the benchmark fields are
  `const`. **This resets the forward cohort**, which is the real price of the cut and the reason it
  is an operator-visible act rather than a maintenance patch.
* Bounds sized against §2's 25,000 rows / 48 MiB rather than a larger arbitrary number, so the wall
  does not simply move. Size `outcomes_h60.jsonl` as a first-class capped source at the same time,
  and size it on **bytes**: at 1,985 B/row it reaches the 8 MiB artifact cap at ~4,225 rows, so its
  byte dimension is the binding one and a row-only v2 sizing would under-provision it.

The cohort reset is cheap **today** and gets more expensive every session: the selector is
currently `selector_active: false` with `candidate_count: 0`, all authority flags false, and the
audited `data/options_signal_episode/campaigns.jsonl` byte-frozen with no writer — so essentially
no forward evidence is being abandoned right now. That argues for cutting v2 promptly rather than
at the deadline.

---

## §8 Carried, not fixed here

**237 episodes carry no H+60 outcome, and it is not a post-close-mint transient.** PR #5524 §3
flagged `osep_70fb17ad11445cca4f3f7c4b` as one episode worth confirming. Measured: **237 of 1,206**
episodes have no row in `outcomes_h60.jsonl`, spread evenly across every session (08-10: 83,
08-11: 72, 08-12: 82 — about 20% of each).

The cause is structural, deliberate and already unit-tested. `derive_h60_outcome`
(`engine/options_signal_episode.py:2506`) returns a **non-persisted** `pending` with reason
`aligned_exit_crosses_session_close` whenever the cadence-aligned exit lands on or after the
session close — which happens for any ticker whose intraday source is hourly and whose anchor falls
in the final bar. `tests/test_options_signal_episode.py` pins exactly this as
`test_coarse_aligned_exit_at_close_stays_pending_without_causal_contract`, and the code's own note
explains that persisting a coarse label would be irreproducible.

So the next run re-derives the identical pending result: **this is not a lane that will pick it
up**, and nothing bounds or alerts on the pending set. It belongs to the episode outcome contract,
not to this bound — it wants either an accepted-forever disclosure with a bounded pending census,
or a finer intraday source — and should be adjudicated by the options program on its own.
