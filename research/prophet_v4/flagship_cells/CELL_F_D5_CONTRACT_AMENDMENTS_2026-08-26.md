# Cell F — D5 contract amendments, 2026-08-26

**Status:** binding amendments to
`research/prophet_v4/flagship_cells/CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md`
(the "2026-08-22 contract"), continuing the amendment series A1–A6 recorded in
`CELL_F_D5_ADVERSARIAL_REVIEW_AMENDMENTS_2026-08-22.md`.

**Why this document exists.** The 2026-08-22 contract was authored 853 commits before current
`main` and before the canonical candidate-episode plane (B1) existed. A fresh adversarial
review on 2026-08-26 against current code found its epistemic core correct and worth keeping,
and found three defects that would have caused a builder to ship a correctness failure. These
amendments repair those three defects and correct two overstated capability claims. The
2026-08-22 text is preserved as authored; where a clause below is superseded, the original
carries an inline `AMENDED 2026-08-26` marker pointing here.

**What is NOT reopened.** The following remain binding exactly as written and were re-checked
against current code: Context Vector preservation as a separate append-only PIT substrate
(§1, §15, §19.3); the three-namespace fence between evidence family, semantic head and Fusion
member (§3); evidence roots are not economic independence (§10); missing is never zero, false,
or neutral, and measured neutral requires positive owner measurement (§8.2, §8.3); corrections
append and never rewrite decision-time belief (§13); trajectory is transport-only and
owner-native (§14.1); the all-false authority block and the absence of any composite/confidence
/count score (§0.10, §12, §19.5); reference-versus-copy discipline (§9); and Entry Radar
`mastermind.live_entry_episode.v1` is not a substitute for `prophet.candidate_episode/v1`
(§4.1).

---

## A7 — Decision-time access law for the Earnings family (closes the point-in-time seam)

**Supersedes:** the unqualified reading of §19.4 ("read source owners through existing
public/load APIs") and §20 required-scope item 4 ("source-ref the full workspace") as they
apply to decision-time observations.

**Defect being repaired.** The canonical Earnings reader
`read_event_workspace` (`engine/neuralweb/company_intelligence_reader.py:581-622`) honours only
`event_id` (`:589`) and resolves the **current** published marker/generation via
`_load_event_workspace` (called at `:599`; defined `:524-548`). It takes no as-of, cutoff, generation or clock
parameter. Because the body it returns still carries `lifecycle.source_available_at` and
`lifecycle.observed_at` (`engine/company_intelligence/event_workspace.py:269-276`) from the
original release, a builder can read a **post-cut corrected** body, observe a pre-cut
`source_available_at`, and conclude `decision_admissibility = ADMISSIBLE` — satisfying the
contract's stated test at §7.1 while presenting corrected numbers as decision-time belief.
The §13 escape hatch (`UNESTIMABLE` / `CORRECTION_PENDING` when version history cannot be
reconstructed) never fires, because that reader cannot reveal that a correction exists.

**The law.**

1. For any D5 **decision-time** observation in the Earnings family, the ONLY lawful access
   path is `read_all_event_source_revisions` / `read_event_source_revisions`
   (`engine/neuralweb/company_intelligence_reader.py:1150-1276`), which walks
   `previous_generation_id` and verifies each predecessor's bytes against
   `previous_manifest_sha256`.
2. `read_event_workspace` (`:581-622`; it calls `_load_event_workspace` at `:599`) and
   `read_current_event_workspace` are **FORBIDDEN** as the source of any decision-time
   observation BODY. They may serve only a separately and visibly labelled "known now"
   research view, never `decision_admissibility = ADMISSIBLE`. The prohibition is scoped to
   bodies deliberately: id discovery via `find_current_event_id_for_company` (`:1036-1076`)
   also resolves the CURRENT marker, so the candidate event-id SET is not itself
   point-in-time. An event that exists only post-cut is representable — it resolves to
   `AFTER_DECISION_CUT` — but an event superseded off the current nest can go unseen, and that
   limit must be disclosed rather than silently inherited.
3. **Admission is a CONJUNCTION over both clocks — never `source_available_at` alone.** A
   revision is admissible at cut `C` only if `source_available_at <= C` **AND**
   `observed_at <= C`; for a correction generation, also `generated_at <= C`. The owner
   enforces only the one-sided relation `observed_at >= source_available_at`
   (`engine/company_intelligence/events.py:249-252`), so `source_available_at <= C < observed_at`
   is a legal and expected state — a filing available 16:05 ET that the nightly collector
   observed at 22:00 ET, judged against a 16:30 ET cut. Admitting on `source_available_at`
   alone ships evidence the running system did not possess, which is lookahead: the exact
   defect this amendment exists to close. A revision failing only the `observed_at` test is
   serialized as `value_state = ABSENT`, `absence_reasons = [NOT_CAPTURED_AT_DECISION]`, and
   `decision_admissibility = AFTER_DECISION_CUT` — §8.2's `value_state` is closed over
   `PRESENT | MEASURED_NEUTRAL | ABSENT`, so "present but inadmissible" has no representation
   and must not be improvised. The clocks currently collapse on
   the live object (`G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md:98`), so this defect is **latent
   today** — the law must be correct for when that degradation is repaired, and a builder may
   not lean on the collapse.
4. **Selection among admissible revisions.** Take the greatest `source_available_at`; break a
   tie on the greatest `observed_at`; if a tie still remains, fail closed with `CONFLICTED`
   rather than picking a winner. Order explicitly by clock — never by the walk's return order,
   and never by position, which a non-consecutive `A -> B -> A` source revert would make
   meaningless. Proven precedent: `scripts/build_cycle_pattern_imce_prospective.py:214-244`
   and `:388-397`.
5. **Null and unknown clocks are NAMED, never silently skipped.** The owner emits
   `lifecycle.source_available_at` as `None` when it has no clock
   (`engine/company_intelligence/event_workspace.py:269-276`), and forbids the field entirely
   when `clock_state == "unknown"` (`engine/company_intelligence/qa_exchange.py:396-399`). A
   revision missing either admission clock cannot be proven pre-cut, so it is **not
   admissible**, and its exclusion is reported as `UNKNOWN` with the missing clock named. The
   cited precedent skips such rows silently (`build_cycle_pattern_imce_prospective.py:237-239`,
   `:396`); D5 may reuse its ordering discipline but NOT its silence — an unnamed skip produces
   "no admissible revision", which is the absence-masquerade §8 forbids.
6. **The mandated reader is a SOURCE-revision reader, not a BODY-revision reader — say so to
   the consumer.** `_dedupe_carry_forward_hops` (`company_intelligence_reader.py:1136-1147`)
   collapses consecutive revisions sharing a `source_sha256`, and `_receipt_from_revision`
   (`:1110-1134`) derives `source_sha256` ONLY from a source whose `kind == "issuer_release"`,
   defaulting to `None`. Consequences that MUST be modelled rather than assumed away: for an
   event with no `issuer_release` source every generation's `source_sha256` is `None`, so the
   whole chain collapses to one revision and a genuine correction to `facts`/`deltas`/
   `guidance` is **invisible to the only reader this law permits**. D5 therefore carries a
   typed `correction_lineage_state` per observation: `OBSERVED` (a distinct source revision was
   seen), `NONE_IN_CHAIN` (chain walked, no correction), or `NOT_OBSERVABLE` (no
   `issuer_release` source, so corrections cannot be detected through this path). Rendering
   `NOT_OBSERVABLE` as "no correction" is forbidden.
7. `WorkspaceChainIntegrityError` is a first-class outcome. It is raised at
   `company_intelligence_reader.py:1194`, `:1208`, `:1232` and `:1241` in the chain walk, and
   at `:1065`, `:1070`, `:1075` inside `find_current_event_id_for_company` (def `:1036`); the
   snapshot loader proper is `_load_workspace_snapshot` at `:472`. A broken or dangling chain yields
   `UNESTIMABLE` / `CORRECTION_PENDING` per §13, and **the raised exception's message must be
   recorded in the observation receipt** — those two states may be emitted only with that
   receipt present, so a builder cannot reach for them whenever a read is inconvenient.
   Falling back to `read_event_workspace` is forbidden.
8. A revision that exists only after the decision cut is not discarded — it is the correction
   lineage of §13, carried beside the decision observation as later knowledge.

**Clock binding table.** The 2026-08-22 contract names clocks abstractly (§7); the Earnings
owner's real field names differ. This binding is normative — a builder may not guess it.

| Contract clock (§7) | Earnings owner field | Notes |
|---|---|---|
| `source_published_at` | per-source `event_source_clock.v1.source_available_at`; event-level `lifecycle.source_available_at` | When `clock_state == "unknown"` the owner FORBIDS `source_available_at` (`engine/company_intelligence/qa_exchange.py:396-399`); map to `NOT_ASSERTED`, never substitute another clock |
| `known_at` | `lifecycle.observed_at` | Owner refuses a transition observed before its source was available (`engine/company_intelligence/events.py:16-19`) |
| `captured_at` | per-source `event_source_clock.v1.system_recorded_at` | The system's own acquisition clock; never `generated_at` |
| `computed_at` | workspace `generated_at` | Generation mint time (`event_workspace.py:76`) |
| `corrected_at` | `generated_at` of the later generation carrying the correction, paired with its `generation_id` | Append-only; never rewrites the earlier version |
| `source_effective_at` | **NOT_ASSERTED** | The owner asserts no effective clock for `earnings_results`; `fiscal_period` is identity, not a clock |
| `decision_at` | episode-owned — see A8 | |
| `tradable_at` | **NOT_ASSERTED** — see A8 | |

**Known degradation, disclose it.** `G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md:98` records that
`generated_at` currently collapses to equal both lifecycle clocks on the live object. Equality
of these clocks is therefore a **measurement degradation to disclose**, not evidence that the
clocks agree. A builder must not infer distinctness it has not observed.

**Acceptance test (required, not optional).** Construct a two-generation chain for one event
where generation N and generation N+1 disagree on a fact, and drive it through the REAL reader
rather than a stub. Cover BOTH event classes: one event WITH an `issuer_release` source (where
the correction is visible and `correction_lineage_state = OBSERVED`) and one WITHOUT (where the
chain collapses and the honest answer is `NOT_OBSERVABLE`, never "no correction"). Add a third
case where `source_available_at <= cut < observed_at`, asserting `NOT_CAPTURED_AT_DECISION`
rather than admission. Assert that the D5 decision observation equals generation N's value, that
the current body differs, that the correction appears as later knowledge with its own
`corrected_at` and `generation_id`, and that no field of the decision observation changed. A
test that exercises only one generation does not satisfy this.

**Why the chain must be constructed, and why that makes A7 more urgent rather than less.**
Measured 2026-08-26 against live production:
`read_event_source_revisions("evt_cik0000320193_2026q3_results")` returns exactly ONE revision,
`lifecycle_state = "complete"`, `source_available_at = 2026-07-30T20:30:28Z`. No published
event currently carries a multi-generation correction chain — `DEFAULT_MAX_CHAIN_HOPS` is 500
so the walk is not bounded early, and `_dedupe_carry_forward_hops`
(`company_intelligence_reader.py:1136-1147`) collapses only CONSECUTIVE byte-identical
`source_sha256`, so a real correction would not have been hidden. The correction path is
therefore **unexercised in production today**. A builder developing against live data would
never meet a correction, would see `read_event_workspace` and the revision walk agree on every
event, and could ship the naive reader without any symptom — until the first real correction
lands and silently rewrites decision-time history. That is precisely why this access law is
normative rather than advisory.

---

## A8 — `decision_cut` is bound to B1-owned clocks; `tradable_at` is NOT_ASSERTED

**Supersedes:** §4/§5 insofar as they assume an availability owner exists for `tradable_at`,
and §5's REQUIRED `decision_cut` row insofar as it is left unbound.

**Defect being repaired.** §5 makes `decision_cut` REQUIRED and §7 lists `decision_at` and
`tradable_at` as "episode-owned" / "episode/availability-owned". B1 as merged
(`878930b3b2f9849e120391fa461ed528f32d2e3c`) emits neither: the projected episode row
(`engine/us_candidate_episode.py:415-440`) carries `opened_at`, `opened_session`,
`last_observed_at` and the event stream, and nothing named `decision` or `tradab`. No US
availability plane exists — `ENTRY_OPEN` appears only in `engine/hk_discovery_challenger.py`
and `scripts/build_canada_library.py`. V4-B4 is not built.

**The law.**

1. `decision_cut` for D5 v1 is defined **over clocks B1 already owns**: the episode's
   `opened_at` and `opened_session`, together with the `known_at`-bearing episode event
   stream. This is a **reference** to owner-issued values, not a new clock. D5 mints nothing.
2. `tradable_at` is `NOT_ASSERTED` with basis "no US availability owner exists; V4-B4 not
   built", exactly as the §7 named-null law provides. It is not synthesised, not defaulted to
   `decision_at`, and not omitted silently.
3. A builder may NOT synthesise a decision cut from any other source. Deriving a cut from a
   ranking, a board, a plan, a session calendar, or a Radar row would mint the second candidate
   lifecycle that §21 and `DSC:PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1` forbid.
4. **The cut is pinned to one episode generation.** `opened_at` and `opened_session` are both
   members of `PATCHABLE_FIELDS` (`engine/us_candidate_episode.py:50-60`), so a later
   correction generation may legitimately change them. A D5 object therefore states the cut
   together with the B1 `generation_id` it was read from, per A9. A cut quoted without its
   generation is unpinned and may silently drift.
5. **Disclose what `opened_at` is.** It is composed, not raw:
   `opened_at = max(anchor.time, known_at)` (`engine/us_candidate_episode.py:897`; the re-arm
   path composes it the same way at `:890-897`). That is exactly why referencing it mints nothing and why it can never
   precede knowledge — but it also means that when `anchor.time > known_at` the interval
   `(known_at, anchor.time]` is a real window in which the structural anchor **postdates** the
   moment the system knew of it, so the cut sits later than knowledge by that interval. D5
   carries `anchor.time` and `known_at` alongside the cut so a consumer can see the window
   rather than inferring a single instant.
6. When B4 lands, `tradable_at` is filled by its owner and this amendment's clause 2 is
   reopened — nothing else here is.

---

## A9 — `episode_ref` must pin the immutable generation

**Supersedes:** §4's `episode_ref` definition. (Cited by section, not line: the inline markers this commit adds shift the 2026-08-22 file's line numbers.)

**Defect being repaired.** As written, `episode_ref` cannot pin an immutable parent: it
carries no `generation_id`, and B1's `PATCHABLE_FIELDS` permit `opened_at` to change across
generations. A D5 object referencing only `episode_id` can silently re-bind to a different
parent state.

**The law.** `episode_ref` MUST carry the B1 `generation_id` (`peg:<64 hex>`) that was HEAD at
adaptation time, alongside `episode_id`. A D5 object is bound to that exact generation. If the
parent episode is later `RETRACTED`, `IDENTITY_SUPERSEDED`, or re-armed, the existing D5 object
is **not** rewritten; a new object is emitted against the new generation and the prior one is
marked superseded, per the §13 append law.

---

## A10 — Per-family mintability register: the missingness vocabulary is a superset

**Supersedes:** §8.2 insofar as it implies every absence reason is available for every family.

**Defect being repaired.** §8.2 lists fifteen typed absence reasons as one closed vocabulary,
which reads as a per-family menu. It is not. Most of them have no Earnings owner behind them —
notably `RIGHTS_BLOCKED`, whose owner-side analogue `blocked_rights` is a RESERVED,
deliberately non-mintable status (`engine/company_intelligence/events.py:83`, subtracted from
`INTELLIGENCE_STATUS` at `:84`, on the stated ground at `:76-77` that "a status no code path
can produce is a lie in a dropdown"). The enforced manifest status enum is
`{ready, degraded, partial, empty}` (`engine/company_intelligence/event_workspace.py:362`), and
the owner's closed warning vocabulary is `WORKSPACE_WARNINGS` (`:99-106`), whose
rights-relevant member is `consensus_unlicensed` (`:102`).

**The law.**

1. §8.2 is a **vocabulary superset ACROSS families**, not a per-family menu. Each family
   adapter carries an explicit register classifying every one of the fifteen reasons.
2. **Vocabulary separation is normative.** `absence_reasons[]` carries ONLY §8.2 members.
   `AFTER_DECISION_CUT` is a `decision_admissibility` value (§7.1) and belongs in that field.
   `MEASURED_NEUTRAL` is a `value_state` (§8.2) and belongs in that field. Owner warning
   strings (`consensus_unlicensed`, ...) are neither — they pass through in a distinct
   `owner_warnings[]` field, unaltered and untranslated. Mixing these three vocabularies into
   `absence_reasons[]` would force a builder to invent the mapping, which this contract
   forbids.
3. **Earnings v1 register — all fifteen classified, no residue.**

   *Owner-backed and mintable (3):* `NOT_APPLICABLE` (the event type does not apply to the
   subject), `NOT_COVERED` (issuer outside the owner's coverage set), `SOURCE_UNAVAILABLE`
   (the reader's `fetch_failed` disposition, `company_intelligence_reader.py:1012-1033`).
   The reader's third disposition, `not_published`, maps to `NOT_COVERED`: the owner has no
   object for this event. Collapsing the two is forbidden in BOTH directions — the reader's
   own docstring (`:1019-1022`) warns that letting a transient CDN blip mint "the issuer had
   no event" is the failure this three-way split exists to prevent, and the converse, dressing
   a genuine absence as a fetch failure, hides real coverage truth.

   *Owner-backed but only PARTIAL (1):* `STALE` — the owner has no staleness clock; it is
   expressible only as a coarse `completeness.<axis>.status` degradation, so it may be emitted
   only with that owner status quoted as its basis, never from a D5-invented freshness rule.

   *D5-originated, describing D5's OWN access or join outcome (6):* `UNESTIMABLE` and
   `CORRECTION_PENDING` (A7 clause 7 chain break — permitted ONLY with the raised
   `WorkspaceChainIntegrityError` message in the receipt), `NOT_CAPTURED_AT_DECISION`
   (A7 clause 3, `source_available_at <= cut < observed_at`), `UNKNOWN` (A7 clause 5, an
   admission clock is null or `clock_state == "unknown"`), `IDENTITY_UNRESOLVED` (A13 clause 3,
   the issuer bridge does not resolve), and `CONFLICTED` (A7 clause 4 unbreakable tie, or A13
   clause 4 identity ambiguity).

   *Not mintable in Earnings v1 (5):* `RIGHTS_BLOCKED` (owner analogue is RESERVED; an
   unlicensed-consensus absence is carried as the owner warning `consensus_unlicensed` in
   `owner_warnings[]`, never as this reason), `INSUFFICIENT_HISTORY`, `ACCRUING`,
   `PRODUCER_DEGRADED`, `NOT_COMPUTED` — the owner defines none of these and D5 may not
   originate them.

   3 + 1 + 6 + 5 = 15. A reason absent from this register is a contract error, not a builder's
   judgement call.
4. The six D5-originated states are consistent with "D5 never originates domain facts" because
   each describes D5's own access or join outcome, not an owner state — the same distinction
   B1 already makes when it mints `IDENTITY_UNRESOLVED` / `ISSUER_UNRESOLVED` about its own
   intake (`engine/us_candidate_episode_intake.py:153-156`). None of them may be used to
   characterise the subject, the issuer, or the market.
5. Because `UNESTIMABLE` is otherwise unmintable, §13's escape hatch is reachable ONLY via A7
   clause 7. Without A7 it is dead law.

---

## A11 — §19.1 canonical episode gate: status corrected

**Supersedes:** §19.1 in full.

§19.1 states that `prophet.candidate_episode/v1` exists only in research documents and that no
canonical B1 runtime implementation exists. That was true on 2026-08-22 and is now false.
B1 merged as `878930b3b2f9849e120391fa461ed528f32d2e3c` (PR #6405) at 2026-08-26T00:13:07Z.

**Current true status: MERGED / BUILT_NOT_PROVEN.** The plane has not yet produced a
production generation. Its nightly writer is schedule-only
(`.github/workflows/daily.yml:6443-6444`) and had not executed as of this amendment;
`data/us_prophet_rank/episodes/` does not yet exist on `main`. The gate therefore moves from
BLOCKING-because-unbuilt to **BLOCKING-because-unproven**, and clears on natural-production
acceptance of B1 from the first qualifying ordinary scheduled `daily.yml` run whose head
contains the B1 merge — not by dispatch, rerun, replay, or report mode.

**Operational note, load-bearing.** A run whose head SHA predates the B1 merge does **not**
qualify even though `us_prophet_ledgers` checks out `ref: main` and re-pulls
(`daily.yml:6411-6414`). GitHub pins the workflow definition to the triggering commit, so a
newly merged workflow **step** cannot appear in an already-started run; only library code is
refreshed. Verified 2026-08-26 against run `32908543584`, whose `us_prophet_ledgers` job ran at
07:30–07:35Z with post-B1 code on disk and no `reconcile_us_candidate_episodes` step in its log.

---

## A12 — §14.2 Earnings trajectory row corrected

**Supersedes:** the Earnings row of §14.2.

The Earnings owner defines exactly one native revision-comparison concept, `metric_delta.v1`,
and it currently ships `basis_match: False` — `basis_match: True` is refused outright
(`engine/company_intelligence/event_workspace.py:341-342`) and `beat`/`miss` keys are forbidden
unless `basis_match` is true (`:343-344`). The guidance status enum
(`introduced|reiterated|raised|cut|withdrawn|absent`) is documented at
`research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md:66` but is not enforced in code, and
only `"introduced"` has ever been minted, on a single issuer.

**The law.** Earnings trajectory in D5 v1 is limited to: the owner's `metric_delta.v1` as
transported (including its `basis_match: False`), and guidance status where the owner actually
emitted one. No surprise magnitude, no freshness-decay score, no estimate-revision velocity —
the owner defines none of these. Where the contract's six trajectory dimensions have no
owner-native meaning, they are absent, per §14.1.

---

## A13 — Episode-to-Earnings identity bridge: `company_id` is TWO different namespaces

**Adds to:** §4 (identity grain) and §20 required-scope item 1. Nothing is superseded; this
closes a gap the 2026-08-22 contract did not anticipate because B1 did not exist.

**The hazard.** Both planes carry a field literally named `company_id`, and they are
**different identifier spaces**:

- B1 episode `company_id` is the Data OS **issuer_id** (ISS namespace), obtained from
  `spine.issuers.issuer_of_security(security_id)` (`engine/us_candidate_episode_intake.py:152`,
  `:162`), per `DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS` R1.
- Earnings `company_id` is CIK-anchored, `cik:` + 10 zero-padded digits
  (`engine/company_intelligence/identity.py:50-58`).

A join on `company_id == company_id` therefore returns nothing, or worse, silently matches
nothing while looking like an honest empty family. This is precisely the "producer outage
masquerading as sparse applicability" failure §8 forbids, arriving through identity rather than
through coverage.

**The lawful bridge, and its limit.** `reference.issuer_master` carries BOTH keys —
`ISSUER_MASTER_COLUMNS = ("issuer_id", "cik", "legal_name", ...)`
(`scripts/build_security_master.py:188-196`), present in production at
`data/reference/issuer_master.parquet`. The lawful path is therefore:

```
episode.company_id (issuer_id)  ->  issuer_master.cik  ->  company_id_for_cik(cik)  ->  Earnings company_id
```

Two constraints on using it:

1. **The canonical reader does not expose it.** `IssuerMaster`'s row shape
   (`SecurityIssuerRow`, `lib/dataos/identity.py:760-779`) is deliberately narrow —
   `security_id`, `issuer_id`, `issuer_state`, `listing_key` — and carries no `cik`. D5 may NOT
   read `issuer_master.parquet` behind the canonical reader's back; that mints a second identity
   reader, which §11's no-second-identity-plane rule forbids. The bridge requires a bounded,
   owner-coordinated extension of the canonical Data OS issuer reader to expose the issuer CIK.
   Until that exists, the join is **UNRESOLVED**.
2. **It is a current-registrant observation, not a point-in-time lineage claim.** The issuer
   reader deliberately carries no `asof` parameter and its own contract states the CIK evidence
   proves who owns a ticker TODAY and "never what the issuer mapping was on a past date"
   (`lib/dataos/identity.py:792-802`). For prospective D5 — episodes opened now against
   current earnings events — that is adequate AND must be disclosed as an identity-resolution
   state, never presented as a proven historical binding.

**The law.**

1. The episode-to-Earnings binding is resolved ONLY through the issuer_id -> cik -> `cik:` path
   above, through the canonical Data OS issuer reader.
2. A **ticker-string join is forbidden here**, in every form — including the owner's own
   `select_current_event_from_aliases` `TICKER/YYYYQn` alias path
   (`engine/company_intelligence/event_workspace.py:632-712`). The governing ruling is
   conditional, not blanket: `research/prophet_v4/D1_D5_READINESS_RULING.md:52` reads "no
   family joins on ticker strings **when canonical identity is required**". Binding a canonical
   episode to a canonical evidence object is precisely a case where canonical identity is
   required, so the condition is met and the join is forbidden. That the owner offers a ticker
   alias API for its own display purposes does not make it lawful for D5.
3. Where the bridge cannot be resolved, the family is `IDENTITY_UNRESOLVED` with the reason
   named. B1 already models exactly this distinction with two typed states,
   `IDENTITY_UNRESOLVED` and `ISSUER_UNRESOLVED`
   (`engine/us_candidate_episode_intake.py:153-156`); D5 mirrors that vocabulary rather than
   inventing one. A10 clause 3 classifies this as a D5-originated state about D5's own join,
   not a claim about an owner fact, and clause 3 of that register explicitly admits it.
4. Identity ambiguity fails **closed**. The Earnings owner already raises on an ambiguous
   fiscal-period mapping (`event_workspace.py:693-699`) and on alias collision (`:429-447`).
   D5 propagates that as `CONFLICTED` — an existing §8.2 member — never picking a winner and
   never inventing a new absence reason for it.
5. An unresolved or ambiguous identity is never rendered as "no evidence". The consumer must be
   able to tell "we could not bind this episode to an issuer" from "this issuer had no earnings
   evidence by the decision cut".

**Acceptance test.** One episode whose issuer resolves to a CIK with a real event workspace, and
one episode whose issuer does NOT resolve — asserting the second yields `IDENTITY_UNRESOLVED`
with a named reason and NOT an empty-but-healthy Earnings family.

---

## Reopening conditions

A7 reopens if the Earnings owner ships a genuinely as-of-aware reader; the binding table
reopens per-row if the owner renames or adds a clock. A8 clause 2 reopens when V4-B4 exists.
A10 clause 2 reopens when the owner makes a currently-reserved status mintable. A11 closes on
B1 natural acceptance. A12 reopens if the owner licenses consensus and can mint
`basis_match: True`. A13 clause 1 closes when the canonical Data OS issuer reader exposes the
issuer CIK; clause 2 reopens only if that reader gains a genuine as-of parameter. Product urgency reopens none of them.
