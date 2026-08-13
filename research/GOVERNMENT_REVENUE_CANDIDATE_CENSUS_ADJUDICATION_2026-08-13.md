# Government Revenue — candidate census adjudication, 2026-08-13

Chartered by `research/GOVERNMENT_REVENUE_FORESIGHT_HANDOFF_2026-08-11.md` §3 item 2
("govrev identity & vintage hygiene package"). This document rules on **one** item of
that package — the candidate census that reddened main — and records what it did *not*
touch, so the remaining items stay chartered rather than silently closed.

## §0 The question

Main was red on two `if: ${{ false }}` legacy jobs, visible only on full-suite runs:

| pack | job | failures |
|---|---|---|
| ci-pack-6 | `unrun-government-revenue` | 2 |
| ci-pack-3 | `unrun-government-revenue-candidate-projection` | 6 |

Every one was the same arithmetic: `assert 23 == 8` (and one `assert 24 == 9`).
The candidate store had grown from 8 rows to 23.

The charter asked whether the 15 new candidates are

- **(a)** real new award-event candidates requiring review before suppression, or
- **(b)** an artifact of a graph republish re-timing frozen rows
  (`observation_id` embeds the reviewed-graph digest, `candidates.py:1692`).

## §1 Ruling: (a), and they were never suppression-eligible

**(b) is ruled out mechanically, not by argument.** The reviewed recipient graph is
still `recipient-graph:reviewed:2026-08-08:defense19-v1`, digest `0733a966…`, in both
the live graph file and `candidate_projection_state.json`. Defense20 (#5424) has not
merged. The re-timing channel never fired.

Positive evidence for (a):

1. **All 8 reviewed identities rebuild byte-exact** from live source — same
   `candidate_id`, same `observed_known_at` (`2026-08-08T11:58:31.364765+00:00`), zero
   field drift. A re-timing artifact would have moved exactly these rows and nothing
   else; it moved none of them.
2. The 15 sit on **7 award records that appear nowhere in the reviewed 8**, at a fresh
   `observed_known_at` of `2026-08-12T23:50:04.442107+00:00`.
3. **6 of the 15 are on the `usaspending_award_action` rail**, which had never produced
   a candidate. This is the handoff §0.3 action-rail unlock landing — a predicted
   success, not a defect.
4. **The nightly already disposed of them correctly, through the reviewed gate.**
   `candidate_projection_status.json` at `2026-08-13T02:20:28Z`: `status: ok`,
   `candidate_count: 15`, `ledger_line_count: 23`, `source_health.status: ok`. The queue
   carries `by_state: {awaiting_crosscheck: 15}`, tier `display`, `context_only: true`,
   `can_rank/size/gate/originate: false`. The 8 incident rows remain quarantined by the
   issuance-correction contract.

So the 15 were **issued forward**, which is the correct disposition. They are not
historical rows awaiting a do-not-backfill decision, and
`config/government_revenue/candidate_historical_suppressions.v1.json` is **correct at 8
and must not grow**. Regenerating it would have auto-issued 15 unreviewed
`do_not_backfill` decisions, with a `reviewed_at` no human reviewed, against rows that
were never suppression-eligible.

## §2 The defect is in the test tier, on an axis already ruled once

`tests/government_revenue_candidate_fixture.py` states the design: both candidate suites
**deliberately** project the live committed generation, "a live probe over the artifact
the site actually ships, which a frozen fixture cannot be." That module exists because
#4406 hand-typed a wall-clock literal (`2026-08-03T15:00:00+00:00`) that detonated the
moment the collection lane advanced, and its docstring states the rule:

> re-typing a fresher literal only re-arms the same bomb for the next collection

That fix generalized the **clock** axis by derivation. The **census** axis was left
hand-typed. `== 8` was the census of the 2026-08-09 vintage, and it detonated on the
first forward issuance. Both named wrong fixes fail for the same reason the clock fix
did: `>= 8` deletes the review gate, and `== 23` re-arms the bomb for candidate 24.

**Ruling: derive the census the way the clock is derived.**
`canonical_candidate_census()` reads the projection's own committed receipt — written by
a *previous* run of a *different* code path than the rebuild under test, so an assertion
against it is cross-artifact agreement, not a receipt checking itself. The receipt is
bound before it is believed: `workspace_bundle_id` must match the committed source
bundle, and the append-only ledger must still hash and measure as recorded. On the
2026-08-09 vintage the derivation returns `8` exactly — a strict generalization.

### What replaced the count's protection

The count was standing in for a real gate. It is now stated explicitly, in the engine's
own terms:

- `pure source total == append-only audit ledger` — facts kept, none erased.
- `pure total − quarantined == published active count` — facts scoped, not deleted.
  (On 2026-08-09 this read `8 − 8 == 0`, matching the "honestly zero-active" queue.)
- **No row escapes review**: every currently visible row must be accounted for either by
  a ledger issuance or by a reviewed historical suppression. A first-seen candidate in
  neither still hard-fails, which is what the manifest's limitations clause promises.

Detonation-proven (mutations chosen to pass every upstream validator):

| mutation | result |
|---|---|
| a forward issuance vanishes from the audit ledger | RED — names the orphaned `candidate_id` |
| published active count disagrees with source−quarantine | RED — `assert (23 - 8) == 16` |
| ledger no longer hashes as its receipt recorded | RED — census refuses to be a census |
| source bundle advances past its receipt | RED — names "collection lane advanced without a projection" |

The reviewed-cohort byte equality is defended in depth rather than by this test alone:
any byte edit to the suppression manifest breaks the corrections manifest's
`original_review.manifest_sha256` binding first (handoff §2.4's artifact-to-artifact
clock binding, untouched here). That assertion is the backstop, not the only line.

## §3 The incident replay: a frozen vintage freezes its SOURCE too

Two of the six projection failures were not census literals. They were
`ValueError: candidate correction activation changed the incident ledger` — the engine
refusing, correctly.

`candidates.py` permits a first activation only on a run that observes the incident
ledger unchanged (`generated_at == activated_at` ⇒ `append_count == 0`). The replay
paired the frozen 8-row incident ledger with a **live** source, which held only while
the live source still yielded exactly those 8 rows. Production activated once, at
`2026-08-10T04:30:14Z`, and activation is durable — no run can ever legitimately
first-activate against today's source again. **The engine is right; the replay's premise
went stale.**

This reverses one sentence of `_incident_correction_root`'s docstring, which claimed
freezing the canonical inputs "is what would break". That was right about the *clock*
and wrong about the *source*. A closed incident's source is as immutable as its ledger.

`tests/fixtures/government_revenue/issuance_incident_5fc18d5/canonical_source.tar.xz`
now carries `latest.json`, `workspace.json`, and `recipient_entity_graph.json` exactly as
commit `5fc18d5aac8` published them (6.6 MB raw → 168 KB compressed), with per-file
digests in `canonical_source.receipt.json` and an extraction-time digest check — a frozen
vintage that can drift is not a frozen vintage. The run clock stays live-derived on
purpose: it need only sit *forward* of every source instant, which a live clock over a
frozen-older source satisfies by construction.

This discharges handoff §2.5's standing rule ("a frozen incident vintage freezes its
GRAPH too"; "every new frozen fixture must include its graph bytes") for this fixture.
Because the graph bytes travel with it, the replay is **already correct for the
defense20 republish**, which re-times `observation_id` through the digest it embeds.

## §4 Deliberately NOT done

- **The suppression manifest was not regenerated and not re-timed.** `reviewed_at`
  `2026-08-09T22:01:43+00:00`, its predecessor pin, and all 8 `do_not_backfill`
  decisions are byte-unchanged.
- **No assertion was loosened.** Every `==` remains an `==`; only the right-hand side
  stopped being a hand-typed vintage.
- **No engine or production behavior changed.** This PR touches tests and one test
  fixture only. The nightly was already green and already correct.
- **The other five items of the §3.2 hygiene package remain open and chartered**:
  the LHX/NOC phantom retraction, GM GDLS share evidence, the `observation_id ⊃
  graph_digest` keep-vs-decouple decision, evidence-id content-addressing, and
  `parent_recipient_uei` as a structured corroborator. The `observation_id` root cause
  is *contained* here (frozen fixtures now carry their graph bytes), not *decided*.
- **The 15 forward candidates were not graded, ranked, or promoted.** They sit at
  `awaiting_crosscheck`, display tier, exactly where the nightly put them.

## §5 Sibling lane

#5424 (defense20-v1 graph publish, DRAFT) also edits
`tests/test_government_revenue_candidates.py`. Its change is on the **clock** axis
(`_suppression_identity` by exclusion, so a graph republish cannot re-time the equality)
and on the graph-vintage constants (19→20 reviewed issuers, BWXT leaving the
`mapping_needed` set). Those constants are deliberately left alone here so #5424 rebases
cleanly. Its `== 8` and its `{usaspending_award_snapshot}` rail assertion are superseded
by this PR; both changes are complementary, neither is a substitute for the other.
