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
`_load_event_workspace` (`:604`, `:524-548`). It takes no as-of, cutoff, generation or clock
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
2. `read_event_workspace` and `read_current_event_workspace` are **FORBIDDEN** in any
   decision-time D5 path. They may serve only a separately and visibly labelled
   "known now" research view, never `decision_admissibility = ADMISSIBLE`.
3. Selection rule: admit only revisions whose `source_available_at` is at or before the
   episode's decision cut; among those take the latest. Re-sort by `source_available_at`
   before selecting — do NOT rely on the walk's return order. Proven precedent in-house:
   `scripts/build_cycle_pattern_imce_prospective.py:214-244` and `:388-397`.
4. `WorkspaceChainIntegrityError` (`company_intelligence_reader.py:1200-1204`, `:1246-1249`)
   is a first-class outcome: a broken or dangling chain yields `UNESTIMABLE` /
   `CORRECTION_PENDING` per §13. Falling back to `read_event_workspace` is forbidden.
5. A revision that exists only after the decision cut is not discarded — it is the
   correction lineage of §13, carried beside the decision observation as later knowledge.

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

**Acceptance test (required, not optional).** Construct a real two-generation chain for one
event where generation N and generation N+1 disagree on a fact. Assert that the D5 decision
observation equals generation N's value, that the current body differs, that the correction
appears as later knowledge with its own `corrected_at` and `generation_id`, and that no field
of the decision observation changed. A fixture that exercises only one generation does not
satisfy this test.

---

## A8 — `decision_cut` is bound to B1-owned clocks; `tradable_at` is NOT_ASSERTED

**Supersedes:** §4/§5 insofar as they assume an availability owner exists for `tradable_at`,
and §5 `:158` insofar as `decision_cut` is left unbound.

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
4. When B4 lands, `tradable_at` is filled by its owner and this amendment's clause 2 is
   reopened — nothing else here is.

---

## A9 — `episode_ref` must pin the immutable generation

**Supersedes:** §4 `:119-124` `episode_ref`.

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

**Defect being repaired.** Ten of the fifteen §8.2 absence reasons cannot be produced by the
Earnings owner today: `RIGHTS_BLOCKED`, `PRODUCER_DEGRADED`, `CONFLICTED`,
`CORRECTION_PENDING`, `NOT_CAPTURED_AT_DECISION`, `INSUFFICIENT_HISTORY`, `UNESTIMABLE`,
`ACCRUING`, `NOT_COMPUTED`, plus `rights.state = BLOCKED`; `STALE` is only partially
expressible. Notably `blocked_rights` is a RESERVED, non-mintable status by deliberate design
(`engine/company_intelligence/events.py:79-83` — "a status no code path can produce is a lie in
a dropdown"), and the enforced manifest status enum is `{ready, degraded, partial, empty}`
(`engine/company_intelligence/event_workspace.py:362`).

**The law.**

1. §8.2 is a **vocabulary superset across families**, not a per-family menu. A family adapter
   may emit only those states its owner can actually mint, and the adapter must carry an
   explicit register of which ones those are.
2. Earnings v1 mintable set: `NOT_APPLICABLE`, `NOT_COVERED`, `SOURCE_UNAVAILABLE`,
   `AFTER_DECISION_CUT`, `MEASURED_NEUTRAL` (only under a named owner definition), plus the
   owner's own closed warning vocabulary `WORKSPACE_WARNINGS`
   (`event_workspace.py:99-106`) — of which `consensus_unlicensed` is the rights-relevant
   member and is how an unlicensed-consensus absence is expressed. Everything else in §8.2 is
   **unavailable to the Earnings adapter in v1** and must not be emitted.
3. A9/A7 create two exceptions that ARE mintable by D5 itself because they describe D5's own
   access outcome, not an owner state: `UNESTIMABLE` / `CORRECTION_PENDING` when the revision
   chain is broken (A7 clause 4). These are the only D5-originated absence states permitted.
4. Because `UNESTIMABLE` is otherwise unmintable, §13 `:542`'s escape hatch is load-bearing
   ONLY via A7 clause 4. Without A7 it is dead law.

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

## Reopening conditions

A7 reopens if the Earnings owner ships a genuinely as-of-aware reader; the binding table
reopens per-row if the owner renames or adds a clock. A8 clause 2 reopens when V4-B4 exists.
A10 clause 2 reopens when the owner makes a currently-reserved status mintable. A11 closes on
B1 natural acceptance. A12 reopens if the owner licenses consensus and can mint
`basis_match: True`. Product urgency reopens none of them.
