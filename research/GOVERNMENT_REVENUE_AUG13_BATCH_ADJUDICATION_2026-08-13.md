# Government Revenue — adjudication of the 2026-08-13 candidate batch and the projection PIT seam

Date: 2026-08-13. Trigger: PR #5509 (CI heal for packs 6+8) flagged, without acting on,
two review items for this program: (1) the fifteen candidates commit `40baa147fa2`
("SAM opportunity evidence 2026-08-13T02:18Z") added to
`data/government_revenue/latest.json` and `candidate_ledger.jsonl` — historical
`effective_at` dates under a fresh collection stamp, the same *shape* as the
erroneous-historical-issuance incident #5247/#5268 quarantined; and (2) an engine
residual: `build_candidate_queue` applies no point-in-time filter against the caller's
`generated_at`, so frozen-generation replays admit newly-known events.

Status of this document: program adjudication, display-tier. It confers no authority,
promotes nothing, and changes no registered rule. Red-teamed per the adjudication
coverage gate (opus reviewer pass, 2026-08-13) before merge — §"Adversarial review"
records what that pass verified, refuted, and added.

---

## Item 1 — the fifteen 2026-08-13 candidates: VERDICT — legitimate forward issuance; NO quarantine

**The batch: 15 ledger rows, `generated_at 2026-08-13T02:18:01Z`, all
`known_at 2026-08-12T23:50:04.442107Z` (one collection pass).** Issuers IRDM, NOC (×3),
GD (×6), KTOS (×2), LDOS (×2), LHX. Families: 11 `award_obligation_change`,
4 `award_ceiling_change`. Rails: 6 `usaspending_award_action`, 9
`usaspending_award_snapshot`. `effective_at`: 11 rows at 2026-05-11/12, 4 rows at
2026-08-10. All rows display-tier `context_only` (`can_rank/size/gate/originate/escalate`
all false), `candidate_state awaiting_crosscheck`, materiality ratio null with printed
reason code (`exact_issuer_attributed_denominator_not_available`).

### Why this is not the #5247/#5268 class

The incident class is defined by its own reviewed artifacts, not by surface shape:

1. **The quarantined 8 were pre-activation knowledge, backfilled.** Their events'
   first-seen `known_at` is 2026-08-08T11:58:31Z — *before* the projection was
   structurally able to emit candidates (the relationship-enum defect closed the lobe
   until the 2026-08-09 fix lanes). The suppression manifest
   (`config/government_revenue/candidate_historical_suppressions.v1.json`,
   reviewed 2026-08-09T22:01:43Z) recorded the human decision `do_not_backfill` with
   reason code **`pre_fix_candidate_became_visible_after_frozen_empty_projection`** for
   exactly those eight source identities. Workflow run `31354784751` issued them anyway
   at 2026-08-10T04:15Z; the issuance-correction manifest
   (`candidate_issuance_corrections.v1.json`, decision
   `quarantine_erroneous_historical_issuance`) quarantined them by exact issued source
   identity. The error was **issuing knowledge the live engine never surfaced in real
   time, against a standing reviewed suppression** — a fabricated track-record entry.

2. **The fifteen are post-activation knowledge, surfaced at the first opportunity.**
   First-seen `known_at` 2026-08-12T23:50:04Z (the collector preserves first-seen
   `known_at` across runs — the incident's own eight still sit at 2026-08-08T11:58:31Z
   in the same store). Snapshot collections ran 08-07, 08-08, 08-09, 08-10T23:32Z, then
   08-12T23:50Z — nothing between; the prior projection (2026-08-12T16:14Z,
   `b768c0daf10`) predates the collection and the next projection (02:18Z,
   `40baa147fa2`) issued them. **No frozen generation sits between their
   becoming-known and their issuance** — the exact property whose violation defines
   the incident. Nothing was backfilled; no reviewed suppression covers them.

3. **The correction machinery says so itself.** Policy is
   `exact_issued_source_identity_only`; its limitation text authorizes "no wildcard,
   ticker, issuer, time-range, graph, or future-source rule", and a genuinely new
   observation remains eligible by design. There is zero contract-identity overlap —
   and zero *ticker* overlap (incident: 8× HII; batch: GD/NOC/IRDM/KTOS/LDOS/LHX):
   incident PIIDs N0002415C2114 / N0002416C2116 / N0002423C2307 / N0002418C2307 vs
   batch PIIDs HC101319C0006 / N0001918C1037 / N0002416C2229 / N0002424C2301 /
   47QFCA20C0019 / 89243318CFE000003 / FA881919C0002.

4. **The snapshot rows are genuine second-observation deltas, not first sightings in
   disguise.** All seven batch PIIDs carry `first_seen_at 2026-08-07T19:38:30Z` in the
   snapshot store; the 08-12 rows diff real state moves (e.g. GD `N0002424C2301`
   total obligation 2.5058B → 3.3631B; LHX `FA881919C0002` ceiling 702.586M →
   703.650M with obligation flat, matching its `award_ceiling_change` family). A true
   first observation routes to `new_award`/`award_discovered_late` with a *computed*
   flag (`award_events.py:1648-1650`) and, for `new_award`, is refused as a candidate
   unless the flag is exactly false (`candidates.py:1256-1257`).

### The historical effective dates are the feed's normal metabolism, not an incident signature

The ~92-day gap between `effective_at` and `known_at` matches the DoD delayed-publication
cycle (USAspending publishes DoD actions ~90 days after action date;
`latest.json` declares `source.reporting_lag_months: 3`): the incident cohort ran
2026-05-08 → 2026-08-08 and this batch runs 2026-05-11/12 → 2026-08-12 — the lag window
rolling forward day for day. Six of the seven batch PIIDs are DoD (Navy `N000…`,
DISA `HC1013…`, Air Force `FA8819…`); the two ~2-day-lag rows are GSA (`47QFCA…`) and
a civilian award (`8924…`). **This inflow recurs at collection cadence** — observed
near-daily (08-07, 08-08 ×2, 08-09, 08-10, 08-12, with a ~48h gap before this batch),
every pass the wire completes. "Historical award surfacing under a fresh collection
stamp" is what a lagged official feed looks like when it is working; it cannot by
itself distinguish an incident from a Tuesday. (That recurrence is also why #5509's
cardinality fix — deriving expected counts from the copied vintage instead of pinning
literals — was the right heal.)

### The `is_late_discovery: false` rows are the documented hardcode, and grading is fenced — today by composition

- The threshold is `DEFAULT_LATE_DISCOVERY_DAYS = 45` (`award_events.py:42`): 92-day
  gaps compute `true`, 2-day gaps compute `false`.
- The 6 action-rail rows carry the flag honestly per
  `engine/government_revenue/award_events.py::_is_late_discovery`: the 4 May-dated ones
  are `true`, the 2 fresh 2026-08-10 ones are `false` — all six are first-observation
  action rows (`prior_source_identity: null`), so all six flags were *computed*.
- The 9 snapshot-rail change rows carry `false` **by construction** (`award_events.py:1681`
  hardcodes it for diff-derived change events — a change observed between two of our own
  consecutive collections). The flag answers "was this award's *first entry* stale",
  not "is this change's effective date old". The candidate row publishes `effective_at`
  and `known_at` side by side, so the gap is visible in the data; see the display
  caveat below for where the *surface* does not say it.
- **The graded family is protected for this batch.** GRV-FA1
  (`research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md` §1) admits only
  action-rail `award_obligation_change` rows whose `source_event.is_late_discovery` is
  **exactly false**, fail-closed on absent/non-boolean. Of the fifteen: only
  **KTOS 47QFCA20C0019** and **LDOS 89243318CFE000003** (both effective 2026-08-10,
  genuinely fresh, computed-false) can enter grading; the 4 late action rows abstain as
  late discoveries; the 9 snapshot rows abstain on the rail fence (§7.6.4 records why
  the snapshot delta is a different measurement — restatement, late-posted correction,
  and genuine new obligation are indistinguishable in a balance diff).
- **But the fence holds by composition, not construction** (red-team finding): there is
  a *second* hardcoded-`false` site on the **action rail** — `award_events.py:1756`,
  `action_revised` (a second observation of the same action identity). A future
  `action_revised` correcting a stale action would enter GRV-FA1 carrying a flag that
  was never computed. This batch escapes only because all six action events are
  first-observations. Named follow-up below.

### Honest caveats (kept, not fixed away)

- First-seen `known_at` proves when *our collector* first saw an event, not when
  USAspending first published it. If the bounded sampler saw late, the grader's entry
  rule (first session strictly after `known_at`) scores stale-ish news as fresh — a
  bias **toward null** at promotion time, and the rows the engine itself flags late
  abstain regardless.
- **The sharper measurement risk is power, not contamination** (red-team finding): the
  two rows that survive every GRV-FA1 clause are both `action_type: C` incremental
  funding mods against old ceilings (KTOS $3.45M on a 466.3M SBIR III ceiling; LDOS
  $3.11M ≈ 0.3% of a 1.2B contract; both `potential_award_amount` unchanged). If the
  surviving cohort is systematically composed of treasury-mechanics funding actions,
  GRV-FA1 can measure a null for reasons unrelated to whether government-revenue events
  move stocks. The prereg already declares a null an acceptable success; this
  composition note is recorded so a future null is *read* correctly — "no signal in
  incremental funding mechanics" is not "no signal in government revenue".

### Disposition

**No quarantine. The batch stands as issued.** Display-tier accrual with printed nulls
is exactly what the epistemics law ships freely; the crosscheck and grader layers are
the gates that decide whether any of it ever matters. No new suppression entry, no
correction entry, no ledger surgery. The reviewed-correction machinery remains scoped to
the eight incident rows.

What WOULD have flipped this verdict, for the next reviewer's speed: (a) any of the
fifteen sharing an exact source identity with a suppressed/corrected row; (b) first-seen
`known_at` predating the 2026-08-09 activation (pre-fix knowledge surfacing post-fix);
(c) evidence the collector re-stamped rather than preserved first-seen `known_at`
(faking freshness); (d) a standing reviewed rule forbidding late-discovered issuance —
none exists: the only hard issuance ban is family-scoped to `new_award`
(`candidates.py:1256-1257`; doctrine
`research/GOVERNMENT_REVENUE_WAVE9_DEFENSE_CATALYST_CANDIDATE_LEDGER_2026-08-03.md`
§candidate doctrine), `research/DO_NOT_REBUILD.md` carries no govrev/late-discovery
row, and the prereg deliberately handles staleness by *abstention at grading*, not by
refusing display-tier issuance.

### Named follow-ups (out of scope here, chipped to the program)

1. **Display honesty for hardcoded-`false` snapshot rows.**
   `templates/government_revenue.html.j2:270` renders the flag as binary copy —
   "Late discovery/延迟发现" vs "Observed in live window/在实时窗口内观测" — so the seven
   snapshot rows with 92-day effective→known gaps assert *"Observed in live window"* in
   both languages. That is the one path that violates the flag's own stated purpose
   (`award_events.py:1709-1715`: the presentation layer must not imply a fresh catalyst
   merely because it was first observed now). The candidate radar
   (`templates/government-revenue-candidate-radar.js`) never surfaces the flag; cards
   head with `candidate_state · known_at` and keep `effective_at` in the Tier-2
   receipt. Fix belongs with the display/copy lane (either compute a gap-aware label,
   or stop equating "not a late first-discovery" with "live window").
2. **Close the `action_revised` uncomputed-flag seam** (`award_events.py:1756`) before
   any revised action can reach GRV-FA1 with a never-computed `false` — compute the
   flag from the revision's own clocks, or make the grader's fence require a
   first-observation action. Note the prereg's amendment window is permanently closed
   (post-registration incident notice, 2026-08-10), so the fix must live at the event
   layer or as a new registration, never as a quiet grader edit.

---

## Item 2 — `build_candidate_queue` and the frozen-clock replay seam: VERDICT — intended semantics; contract now documented; no engine behavior change

**The seam, precisely.** `engine/government_revenue/candidates.py::build_candidate_queue`
admits events on `known_at <= analysis_as_of`, where
`analysis_as_of = end_of_UTC_day(latest_payload.as_of)` — a boundary that can sit up to
a day **after** the caller's `generated_at` (the shipped 2026-08-13 queue: `as_of`
23:59:59Z vs `generated_at` 04:43:09Z — 19h16m of headroom). The caller's
`generated_at` is an output stamp, never a knowledge filter, so the engine alone will
happily project a payload that kept growing under a frozen stamp. That is the flagged
residual.

**Why that is the intended contract, not a production gap:** the function is a *pure
projection of one payload vintage*; point-in-time honesty is owned by the caller that
selects the inputs, and every production caller enforces it fail-closed before any
projected observation is used:

| Surface | Caller | Fence (before observations are used) |
|---|---|---|
| Issuance (writes the ledger) | `scripts/build_government_revenue_candidates.py` | **per-observation refusal** — `"current candidate observation is after the frozen generated_at clock"` (`:619-622`) — plus document-clock refusals for latest/workspace (`:304-309`) and the reviewed graph (`:350-351`) |
| Render verify | same file, `verify_candidate_artifacts` | replays under the persisted state's clock and requires current `latest_sha256` / `workspace_bundle_id` / `workspace_sha256` / graph digest to equal the recorded state (`:1580-1588`) before `current_observations` is consumed (`:1607`) — drift refuses |
| API serve | `app/government_revenue.py` | binds the same content hashes to `projection_state` (`:844-861`) before the `build_candidate_observations` call (`:863`); any mismatch → HTTP 503, no degraded branch |

So the write path is **structurally** PIT-clean at per-observation granularity, and the
read paths replay only byte-exact recorded vintages. `engine/government_revenue/
shadow_context.py` is not a caller (its `candidates` reference is a provenance string,
not an import), and Prophet annotation re-verifies the display-only authority fence
independently.

**The unfenced replayer was the incident-correction *test* fixture** (byte-frozen
8-row incident state paired with the live canonical boundary) — which is precisely what
detonated on 2026-08-13 when the fifteen arrived. PR #5509 (in flight at adjudication
time, not yet merged) heals it by pruning the copied boundary to events whose
`change.known_at` is at or before the incident's `issued_projection_generated_at`
(helper `restrict_boundary_to_known_through`, added to
`tests/government_revenue_candidate_fixture.py` by that PR; the clock is read from the
reviewed correction manifest, never hand-typed).

**Residuals actually worth holding** (sharpened by the red-team pass):

1. **The engine seam's contract lived nowhere** — a future caller could repeat the
   fixture's mistake in production code without tripping anything until the store next
   grew. Closed by this adjudication: `build_candidate_queue`'s docstring now states
   the boundary semantics, the caller's replay duty, and points here.
2. **The replay path's PIT protection is content-binding alone.**
   `verify_candidate_artifacts` calls `build_candidate_observations` directly
   (`:1568`), bypassing the issuance path that carries the per-observation clock
   refusal — so a recorded state that satisfies the digests but was not produced by the
   issuance path would replay post-`generated_at` observations silently. Exposure today
   requires a hand-built state blob that passes four content digests, i.e. not a live
   shape; declined as a behavior change now, named as the correct upgrade if a new
   replayer class or state producer ever appears: surface the `:619-622` per-observation
   refusal inside `verify_candidate_artifacts` (and the API twin) as well.
3. **No engine behavior change.** A per-event PIT clamp inside `build_candidate_queue`
   would be redundant with the issuance fence, would put new refusal paths on the
   render lane for zero live exposure, and would repurpose a pure function's signature.
   Declined.

---

## Adversarial review (coverage-gate pass, 2026-08-13)

Opus red-team, briefed to refute both conclusions, independently reproduced the batch
numerics, PIID/ticker disjointness, authority flags, and GRV-FA1 admission set, and ran
three attacks that failed: sample-churn-as-fake-changes (refuted via `first_seen_at`
2026-08-07 + real state deltas), missed-earlier-generation (refuted via the collection
and projection timeline), and doctrine-forbids-late-issuance (refuted: the only ban is
`new_award`-scoped). It **corrected this document on three points**, folded in above:
the write-path fence is the per-observation refusal at `:619-622` (not the
document-level clocks alone, and "payload `as_of` is the knowledge boundary" was the
wrong framing — `as_of` is looser than the run clock by up to a day); the true replay
residual is `verify_candidate_artifacts` bypassing that refusal with content-binding as
sole protection; and references to #5509's fixture helpers must be stated as in-flight
PR content, not current-tree fact. It also contributed the `action_revised` seam, the
funding-mod power caveat, and the display-honesty defect, all recorded above.

## Cross-references

- Incident + machinery: PR #5247, PR #5268,
  `config/government_revenue/candidate_historical_suppressions.v1.json`,
  `config/government_revenue/candidate_issuance_corrections.v1.json`.
- The flag + heal that commissioned this review: PR #5509 (in flight), which also adds
  `restrict_boundary_to_known_through` / derived cardinality to
  `tests/government_revenue_candidate_fixture.py`.
- Grader fences: `research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md` §1, §7.6.4.
- Open sibling lanes at adjudication time (no scope collision): #5516 (producer-proof
  wiring in `government-revenue-live.yml`), #5511/#5518 (derived census/coverage
  constants), #5424 (defense20 graph), #5432/#5437 (API access posture).
