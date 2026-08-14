# Duplicate open ticker+direction keys — adjudication, 2026-08-13

Scope: the three ticker+direction keys PR #5524 surfaced as carrying two open Prophet US
plans — `FCX-BULL`, `MDB-BULL`, `HEI-BULL` — and the question it referred to this program:
does the W1 re-origination block need extending to cover the durable nightly checkpoint's
origination path?

Authority tier: display. Nothing here promotes, ranks, or sizes anything; it rules on plan
identity and on which of two artifacts a reader should treat as live.

## 0. Ruling

**Each pair is already resolved, and no plan needs retiring by hand.** In all three the older
artifact was audit-quarantined on 2026-08-08, and quarantine is this program's retirement
verb: a quarantined plan is withdrawn from the published index, its management state stops
advancing, and it can never emit a forward-ledger row.

| key | LIVE plan | retired plan | retired how |
|---|---|---|---|
| `FCX-BULL` | `FCX-BULL-20260731` (recorded 2026-08-09) | `FCX-BULL-20260730` | quarantined 2026-08-08 |
| `MDB-BULL` | `MDB-BULL-20260731` (recorded 2026-08-09) | `MDB-BULL-20260803` | quarantined 2026-08-08 |
| `HEI-BULL` | `HEI-BULL-20260723` (recorded 2026-08-12) | `HEI-BULL-20260731` | quarantined 2026-08-08 |

**Scope of "no action needed" — one exception, found by review.** The claim holds for every
consumer that reads the published index or the correction overlay, which is every user-facing
surface. It does NOT hold for `engine/prophet_miss_audit.py:334-359`: `load_plan_assets()`
globs `site/prophet/plans/*.json` and counts every file's `asset` with no overlay import and no
quarantine check, feeding the conversion **numerator** of the lane `config/dag.yml:1648` names
as the sole forward advancer of `data/prophet_miss_audit/forward_log.jsonl`. So a quarantined
plan is still live for one accruing internal store. No template, page, or API reads it, so
nothing user-facing is wrong — but §7 now carries it as an open item rather than this
adjudication asserting a clean sweep it only checked three surfaces for.

**The W1 re-origination block does NOT need extending.** It behaved exactly as designed, and
the design is deliberate: `scripts/build_prophet.py` excludes quarantined plans before
computing the open-key set, under the comment *"An audit-quarantined plan is not actionable
and must not monopolise the ticker's future opportunity slot."* Quarantining the older plan
freed the slot; the later bake filled it. That is the intended behaviour of a quarantine, not
a bypass of a block.

What was actually wrong is narrower and elsewhere: the duplicate-open-key **census** counted
quarantined plans as open, so it disagreed with the origination path about what "open" means.
The census was the wrong one. Fixed in this PR by giving both readers one definition.

## 1. The reported hypothesis is refuted

PR #5524 flagged the three pairs and proposed: *"All three are keyed on FORMATION date while
`signal_date` is days later, which is plausibly how they slip a block keyed on the
signal-dated id."*

That mechanism does not exist. The block is keyed on ticker+direction and never on the dated
id:

- `engine/prophet_bridge.py:770` — `plan_key(ticker, direction) -> "<TICKER>-<DIRECTION>"`,
  documented as *"the identity the re-origination block is keyed on"*.
- `engine/prophet_bridge.py:4102-4113` — the block itself, `key = plan_key(ticker, "BULL")`,
  running *after* the same-id duplicate check so the two counts stay distinguishable.
- Live receipt: `site/prophet/index.json` → `intake.reorigination_blocked_keys` reads
  `["CSR-BULL"]` — a bare ticker+direction key, not an id.

There is also no second origination path to extend. `originate_plans` has exactly one
production caller (`scripts/build_prophet.py:1614`); the *"checkpoint Prophet outputs to main"*
step (`.github/workflows/daily.yml:2608`) is git plumbing that commits files the nightly had
already written, and it contains no call into `originate_plans`, `_make_id`, or `plan_key`.
The three plans read as "checkpoint-lane" only because the checkpoint commit is what happened
to carry them to main.

## 2. Root cause — two definitions of "open" for one concept

Origination's definition, `scripts/build_prophet.py:1580-1586`: a plan holds its
ticker+direction slot unless it is closed in `data/prophet/ledger.jsonl` **or** audit-quarantined.

The census's definition, `tests/test_prophet_outage_backfill.py::TestOnePlanPerEpisodeOnTheShippedTree._open_keys`:
a plan holds its slot unless it is closed in the ledger. Quarantine is not read at all.

So a lawful re-origination — quarantine frees the slot, the next bake fills it — presents to
the census as a name that acquired a second open plan. Three lawful re-originations later, a
cross-lane count tipped over a hand-typed ceiling and took the fleet red.

## 3. Receipts

**The quarantine is a 2026-08-08 chronology-audit disposition.** `data/prophet/plan_corrections.jsonl`
carries, for each of the three retired ids, a row with `field: integrity_status`,
`new_value: quarantined`, `corrected_at: 2026-08-08`, `basis: "chronology audit disposition"`,
and `evidence.audit_receipt: research/prophet_us_audit/OUTAGE_PLAN_CHRONOLOGY_2026-08-08.json`.
The stated reason is that the plan was published on an outage-era clock.

**Quarantine already retires a plan — three independent surfaces agree.**

1. *Not published.* `site/prophet/index.json` lists 179 plans; none of the twelve entries in
   `plan_integrity.quarantined_ids` is among them. Each pair's live member is listed, alone.
2. *Not managed.* Every quarantined plan's management state is frozen at `asof 2026-08-08` —
   the quarantine date — while every other open plan advanced to `2026-08-12`. The management
   loop reads `actionable_plans` (`scripts/build_prophet.py:1734`), which excludes them. This
   holds for all ten quarantined plans that have a state file, not only the three here.
3. *Not gradeable.* The index states the effect in its own words: *"quarantined plans cannot
   emit live instructions or ledger rows."*

**The HEI refill was earned.** `HEI` sits on the 2026-08-12 board
(`site/factordata/us_standouts.json`) as a `buy` row in state `TURN SIGNALED` — a live
admission on a freed slot, which is what the bake originated `HEI-BULL-20260723` from.

**This is shown for HEI only.** Review caught the over-reach: the two 2026-08-09 refills were
never checked the same way, and they are the ones that warrant it. The quarantine reason for
all three predecessors was *"outage-era plan was published after its entry-price session"*, and
`FCX-BULL-20260731` and `MDB-BULL-20260731` both sit in the lag-2 cohort
(`recorded_at 2026-08-09`, `price_basis_date 2026-08-07`) — the same chronology signature their
predecessors were retired for. The 2026-08-08 audit's window is `2026-08-03 → 2026-08-08`, so
it structurally could not have assessed a cohort recorded on 08-09. Fourteen other shipped
plans share the property and none is flagged, so this is not a finding — but "the system
working, not a leak" is asserted rather than shown for two of the three, and the cohort is
§7's first open item.

**The block was not starved of inputs.** The 2026-08-13 origination receipt
(`data/prophet/origination_receipts/31649984834-1-f29436e0235c17b0.json`) records
`source_checkout: 40baa147fa254e7a154777cf51aa0cf1311287e4`; that tree carries 176 plan files
including `site/prophet/plans/HEI-BULL-20260731.json`. The older sibling was on disk. The
block saw it, and correctly declined to let a quarantined artifact hold the slot.

**The census, recomputed both ways on the shipped tree:**

| definition | open keys | duplicate keys |
|---|---|---|
| ledger-closed only (the census as written) | 158 | 11 |
| ledger-closed **and** quarantined (origination's own rule) | 150 | **8** |

The 8 are `APPF-BULL`, `BDC-BULL`, `CELH-BULL`, `CLF-BULL`, `ENOV-BULL`, `LPG-BULL`,
`PAHC-BULL`, `PI-BULL` — every one a genuine pre-W1 legacy pair, none carrying a `recorded_at`,
none written by any post-block lane. All three quarantine-derived pairs leave the census.

## 4. Why the first two entered silently

The ratchet was `len(doubled) <= 10`, a ceiling over a population it did not own. Walked
across the checkpoints:

| tree | duplicate keys |
|---|---|
| `2dfebf35dbd` (2026-08-06, before the quarantine) | 9 |
| `56260d0a7b1^` (before the 2026-08-09 checkpoint) | 8 |
| `56260d0a7b1` (FCX + MDB minted) | **10** |
| `f9140631d37^` | 10 |
| `f9140631d37` (HEI minted) | 11 |

The live population had drifted to 8 while the ceiling stayed at 10, so the first two
additions landed exactly ON the ceiling and passed. The third tipped it. A count ratchet over
a moving cross-lane population cannot distinguish "two were added" from "nothing happened" —
it only reports the net, and it spends its slack silently. Both #5524 and #5525 replace the
count with a membership set, which is the right shape — a set cannot bank slack.

## 5. What changed, and who owns which half

The heal is in two independent halves, in two PRs, deliberately not raced:

**The census half — PR #5525, already in flight, not duplicated here.** It teaches
`TestOnePlanPerEpisodeOnTheShippedTree._open_keys` to apply the same correction overlay
`build_prophet` applies, and replaces the count ratchet with a membership set. Its reasoning is
the same as §2's, reached independently: *"Counting those files as open is a census of the
wrong store."* This adjudication does not touch `tests/test_prophet_outage_backfill.py`; three
open PRs were already rewriting that file and a fourth would only deadlock them.

**The structural half — this PR.** #5525 re-derives the quarantine overlay inside the test,
which heals today's disagreement but leaves two implementations of one rule, free to drift
again. So `open_plan_keys` (`scripts/build_prophet.py`) now takes the quarantined-id set and
applies the exclusion itself: the rule lives with the definition and the nightly caller can no
longer forget it. New tests in `tests/test_prophet_w1_intake_repair.py` pin that the parameter
is load-bearing and that no quarantined plan holds a slot on the shipped tree.

Scoped deliberately to the nightly caller. The outage-replay lane also calls `open_plan_keys`,
but its quarantine SOURCE is separately broken — `_quarantined_plan_ids_at` resolves 0 ids
against 12 quarantined plans, because it reads `integrity_status` off a correction row (no
shipped row carries that key) and collects the correction id rather than the plan id. PR #5529
owns that fix. Routing that lane through the new parameter here would have been
behaviour-identical only by faithfully preserving the bug, so this PR leaves the file alone.

Behaviour of the live origination path is unchanged; the refactor is proven identical against
the real tree.

One observation on #5525, for its own author to take or leave: its `_LEGACY_DOUBLED_KEYS` set
still lists `FCX-BULL` and `MDB-BULL`, which its own comment notes quarantine has already
retired from the actionable doubled set. They are inert once the overlay is applied — nothing
fails — but they are described as pre-W1 legacy pairs and they are not: both were minted
2026-08-09, after the block shipped. The genuine pre-W1 debt still open is the eight named in
§3.

## 6. Deliberately not done

- **No frozen artifact was deleted, rewritten, or re-stamped.** Deleting a frozen per-ticker
  file freezes its ledger rows; the retired plans stay on disk exactly as published. Their
  withdrawal is carried by the correction overlay, which is append-only by design.
- **No new lifecycle verb.** "Retired" already has two implementations — a terminal ledger row
  and an audit quarantine. A third would be a third thing to disagree with.
- **The W1 block is untouched.** It was correct. Its guard reads
  `if active_keys and key in active_keys`; for a set that is exactly equivalent to
  `key in active_keys`, so the truthiness test is a `None` guard and not a fail-open.
- **`verify_collisions` is untouched.** Its incumbent set is cut at `LIVE_WINS_FROM = 2026-08-10`
  and the three retired plans carry no raw `recorded_at`, so they were never candidates there.

## 7. Open items for the program

1. **The 2026-08-09 lag-2 cohort is unassessed.** Sixteen shipped plans carry
   `recorded_at − price_basis_date == 2` against a bimodal `{0: 50, 2: 16}` split, including
   both refills this adjudication blessed. That is the same shape the 2026-08-08 audit
   quarantined the predecessors for, and the audit's window closed before the cohort existed.
   Either the lag is benign at 2 sessions and the audit's threshold says so, or sixteen plans
   are owed the same look. Nobody has answered which.

2. **`engine/prophet_miss_audit.py` counts quarantined plans as real.** It globs the plans dir
   with no overlay, so the conversion numerator on `data/prophet_miss_audit/forward_log.jsonl`
   includes twelve retired plans. Internal telemetry only, but it is an accruing forward store
   and every night it runs it accrues the wrong number. Smallest honest fix is the same one
   this PR made for `open_plan_keys`: read the overlay, do not re-implement the rule.

3. **#5071's `tier_cascade` leg was never adjudicated as a population change.** It narrowed the
   admitted set on roughly 19% of board days measured across 59 days since 2026-07-01, while
   `TestAdmittedPopulationIsUnchanged` was asserting the population was byte-identical and
   #4481's own body had promised exactly that. Whether the leg was authorised is a question for
   the #5071 thread or the §6.5 shadow-ledger charter — and that charter is not in the tree
   (`research/ANTICIPATION_ENGINE*.md` carries no §6.5 section, despite two docstrings citing
   it). The tier-leg heal itself belongs to #5524; this row is the governance question
   underneath it, which no PR currently owns.

4. ~~Are any of the other nine quarantined names silently missing from the board?~~ **Checked,
   clear.** `APH`, `ELAN`, `FHI`, `GE`, `NUE`, `SE`, `SYY`, `WB`, `ZWS` appear in neither the
   `buy` nor the `watch` lane of the 2026-08-12 board. They stopped ranking; nothing is being
   suppressed. Only `HEI` of the twelve is on the current board, and its slot was refilled.

5. A reader who fetches `site/prophet/plans/<ID>.json` directly still sees a retired plan that
   looks live: the file carries no quarantine marker, because the marker lives in the
   correction overlay. The published index is correct and the Terminal reads the index, so
   nothing user-facing is wrong today — but a `site/prophet/plans` consumer that bypasses the
   index would be. Worth a display-tier `integrity_status` echo on the published plan payload
   if such a consumer ever appears.
