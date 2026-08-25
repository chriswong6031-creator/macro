# FIF-3A4R — Cross-filing fact lineage protocol

Status: **SPEC_ONLY / SOL PASS WITH BOUNDED AMENDMENTS / HOLD-FOR-SOL**.
Not an accepted AgentOS `DEC`. Not built. Not shipped. Not a runtime
provider. Not a second ledger. Do not merge. Do not code FIF-3A4.

Sol architecture review of PR #6382 (2026-08-25): **PASS WITH BOUNDED
AMENDMENTS**. Not `LINEAGE_ARCHITECTURE_BLOCKED`. The winning architecture
is accepted **in principle**: unchanged `FILED` `RawFactOccurrence`s +
immutable cutoff-visible lineage-evidence overlay + effective-root
unification inside the existing query kernel. This file freezes the
bounded amendments. It does not mint architecture authority.

Replay census: `research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json`
Replay tool: `research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py`

Original freeze HEAD: `2df738a154acc6feae96e2ad0a6d289d3ab0f4a7`.
Sol-observed main at commission: `cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208`.
This amendment re-merges current `origin/main` and drops the unrelated
board-shadow carrier (#6386 already derived `ASOF` on main).

---

## 0. Verdict

**Winner:** a cutoff-visible lineage-evidence overlay owned by the existing
query dataset and selected by the existing `BitemporalMetricQueryEngine`,
pointing at unchanged `FILED` occurrences.

This is **not** `LINEAGE_ARCHITECTURE_BLOCKED`. One occurrence plane is
preserved. A3 historical `NOT_EVALUABLE` remains reproducible. Confirmation
does not leak into `LATEST_RESTATED` or `revisions[]` if the overlay never
mints a reported-revision `event_type`.

**Rejected:** reminting/reclassifying the A2 `FILED` occurrence as
`FactEventType.XBRL_CONFIRMATION`. That changes `occurrence_id` (identity
payload includes `event_type` and `revision_of`) and rewrites accepted A3
source identity. A1 and A2 remain `event_type=FILED`. No
`RawFactOccurrence` is reminted. No raw-ledger identity changes.

**Rejected:** appending a third confirmation `RawFactOccurrence` while
keeping A2 `FILED`. After the confirmation clock, `_select_source_group`
still sees two roots unless a suppression law hides A2 `FILED`. That is two
identities for one physical fact, plus a ledger-SHA change.

The lineage relation is `xbrl_confirmation`. That name is **not**
`FactEventType.XBRL_CONFIRMATION`. The kernel enum remains a reserved
conversion-time exclusive type, absent from `_REPORTED_REVISION_EVENT_TYPES`
/ packet `REPORTED_REVISION_EVENT_TYPES`. A4R v1 must not stamp it onto
accepted A2 `FILED` rows. The v1 relation lives on the evidence receipt.

### 0.1 Sol 2026-08-25 bounded amendments

1. **v1 stays exact.** Do not widen cross-filing confirmation to
   `_duplicates_agree`. Exact parsed numeric value + exact accuracy metadata
   is the v1 positive rule. `us-gaap:LongTermDebt` 90.678B / 90.7B remains
   `precision_consistent_unconfirmed`. XBRL duplicate consistency is useful
   evidence but does not prove cross-filing equality.
2. **Source lineage is not metric eligibility.** Preserve all lawful exact
   confirmation candidates, including dimensioned facts. Current
   consolidated query may use only facts independently admitted by the
   existing metric dimensional contract. Do not discard dimensioned lineage
   because today's core catalog is consolidated-only.
3. **Tighten positive v1 guards** as listed in §5. Nil facts stay out of v1
   unless a separate nil-confirmation contract is specified.
4. **Relation vocabulary** is lineage `xbrl_confirmation`, not occurrence
   `FactEventType.XBRL_CONFIRMATION`.
5. **Clock law** as in §8. The A4R research census timestamp does not
   authorize runtime lineage.
6. **Runtime evidence remains small.** The research census may retain
   positive and refused classifications. Runtime
   `FinancialQueryDataset.lineage_evidence` carries only accepted positive
   immutable relations. Research JSON must never be loaded by the
   production/query provider.
7. **Policy isolation.** Confirmation can affect `LATEST_KNOWN_AS_OF`.
   `AS_REPORTED` remains the original A1 `FILED` root. `LATEST_RESTATED`
   must ignore confirmations. FIF packet/revision projection must not emit
   confirmation as a reported revision.

---

## 1. Control state that A4R must not repair

After both golden filings are visible, `total_assets` instant `2025-09-27`
is `NOT_EVALUABLE` with reason
`unlinked source vintages require an explicit typed revision lineage`
(`DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE`).

Accepted identities, unchanged by this research:

| Identity | Value |
|---|---|
| A1 | `0000320193-25-000079` |
| A2 | `0000320193-26-000020` |
| Ledger SHA | `ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8` |
| AAPL response SHA | `58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0` |
| Query hash | `f8f6dc3134592c817001738cbdefb09ee1b71798ef24a8e64dc75685a6f9c7a1` |
| A1 document | `sec_document_d23a609841f9a32489dd7abc952d39622540f8a24905612bda1d43e5577860b8` |
| A2 document | `sec_document_29a36fa46a0bc5309f17bd254c3061f20c4b3de7e05898a2fec9ee58f89e8760` |
| A1 Assets occurrence | `rawfact_bc9355a292f06baaaf988b683106b2b02e3dd9c4a9555f1eb160a94643e4feaf` |
| A2 Assets occurrence | `rawfact_9669446bc8076fa26bca33a3d9a067093bddadbb28e4617318bb3de33a4eca29` |
| A1 Assets parser id | `f-181` |
| A2 Assets parser id | `f-189` |
| Assets value | `359241000000` (both filings, `decimals=-6`) |
| A1 `accepted_at` | `2025-10-31T10:01:26.000000Z` |
| A2 `accepted_at` | `2026-07-31T10:01:02.000000Z` |
| A1 `recorded_at` | `2026-08-23T00:32:31.000000Z` |
| A2 `recorded_at` | `2026-08-23T07:02:13.000000Z` |

Mechanism: `logical_key` is shared (same `source.source`, entity, concept,
context, unit) but `duplicate_group_key` includes accession/document, so each
filing is its own root. `query.py` refuses timestamp fusion when
`root_ids` has more than one member.

---

## 2. AAPL A1↔A2 overlap census (exact, not estimated)

Replay command:

```
python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
```

Identity: `RawFactOccurrence.logical_key`. Default relation is `NO_RELATION`.
Duration overlap count is **0**. Every overlapping logical key is an instant.

| Population | Count |
|---|---|
| A1 occurrences | 964 |
| A2 occurrences | 758 |
| A1 logical keys | 875 |
| A2 logical keys | 682 |
| Overlap logical keys | 133 |
| A1-only logical keys | 742 |
| A2-only logical keys | 549 |
| `no_relation` (A1-only + A2-only) | 1291 |
| Prior (pre-amendment) exact complete candidates | 131 |
| `exact_complete_confirmation_candidate` after tightened v1 | **130** |
| of which empty-dimension | 37 |
| of which dimensioned | **93** |
| of which core-mapped (any dimensions) | 46 |
| of which **query-relevant** (empty-dimension, core-mapped, non-nil) | **15** |
| `nil_confirmation_unspecified` | **1** |
| `precision_consistent_unconfirmed` | 1 |
| `changed_value` | 1 |
| `source_taxonomy_namespace_version_mismatch` | 0 |
| `event_type_not_filed` / `same_accession` / `source_family_mismatch` / `parent_not_before_child` | 0 |
| `incomplete_dimensional_scope` | 0 |
| `custom_unmapped_taxonomy` | 0 |
| `ambiguous_duplicate_group` | 0 |
| `multiple_possible_parent` | 0 |
| `nil_state_difference` | 0 |
| `unit_context_concept_mismatch` at logical-key overlap | 0 |

The 131 total **changes**. Tightened eligibility excludes the one nil-nil
pair `us-gaap:CommitmentsAndContingencies` instant `2025-09-27`
(A1 `f-203`, A2 `f-211`). Nil facts are not needed to unlock A4 numeric
query behavior and have no v1 nil-confirmation contract.

**Source-namespace-version proof:** all 133 logical-key overlaps, including
the 130 v1 exact numeric candidates, carry original Clark concept URI
`http://fasb.org/us-gaap/2025` on both A1 and A2. Mismatch count is **0**.
A2's filing-level families also include Apple custom `20260627`, but those
namespaces do not appear on the overlapping us-gaap concepts. Both golden
filings tag the overlapping us-gaap facts in the 2025 taxonomy year.

Ledger SHA of the replayed A3 ledger remains
`ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8`.

Census schema: `fif3a4r.aapl_overlap_census/v1.1`.
Census payload SHA-256 (canonical JSON excluding the digest field):
`b1577b04f553c56ba278d2057ecc07a0d23159a1d20a41339b39da4ed24c12a9`.
Written file SHA-256:
`f1481fffa18720209ba98d463c25a52b4e497bff89b2159cfa3b2d74ea63ab58`.

### 2.1 Safe v1 confirmation candidates

**All 130** `exact_complete_confirmation_candidate` rows are lawful
fact-level confirmation candidates under the tightened v1 guards in §5,
including the **93 dimensioned** rows. Source lineage is not metric
eligibility. Do not discard dimensioned lineage because today's core
catalog is `consolidated_only`.

They are **not** SEC-called confirmations. They are Mastermind typed lineage
interpretations. The lineage relation, if later minted, is
`xbrl_confirmation`. It is not `FactEventType.XBRL_CONFIRMATION`.

**Query-relevant v1 subset (15)** — empty explicit/typed dimensions, core
catalog alias, non-nil. These are the facts that
`consolidated_only` query selection can see. The control `total_assets`
instant `2025-09-27` is in this set.

| Concept | Instant | Metric | Value | A1 facts | A2 facts |
|---|---|---|---|---|---|
| `us-gaap:Assets` | 2025-09-27 | `total_assets` | 359241000000 | f-181 | f-189 |
| `us-gaap:AssetsCurrent` | 2025-09-27 | `current_assets` | 147957000000 | f-171 | f-177 |
| `us-gaap:Liabilities` | 2025-09-27 | `total_liabilities` | 285508000000 | f-201 | f-209 |
| `us-gaap:LiabilitiesCurrent` | 2025-09-27 | `current_liabilities` | 165631000000 | f-193 | f-201 |
| `us-gaap:CashAndCashEquivalentsAtCarryingValue` | 2025-09-27 | `cash_and_cash_equivalents` | 35934000000 | f-159, f-522 | f-165, f-605 |
| `us-gaap:MarketableSecuritiesCurrent` | 2025-09-27 | `short_term_investments` | 18763000000 | f-161, f-523 | f-167, f-606 |
| `us-gaap:AccountsReceivableNetCurrent` | 2025-09-27 | `accounts_receivable_net` | 39777000000 | f-163 | f-169 |
| `us-gaap:InventoryNet` | 2025-09-27 | `inventory_net` | 5718000000 | f-167 | f-173, f-647 |
| `us-gaap:PropertyPlantAndEquipmentNet` | 2025-09-27 | `property_plant_equipment_net` | 49834000000 | f-175, f-663 | f-181, f-654 |
| `us-gaap:AccountsPayableCurrent` | 2025-09-27 | `accounts_payable` | 69860000000 | f-183 | f-191 |
| `us-gaap:LongTermDebtCurrent` | 2025-09-27 | `long_term_debt_current` | 12350000000 | f-191, f-942 | f-199 |
| `us-gaap:LongTermDebtNoncurrent` | 2025-09-27 | `long_term_debt` | 78328000000 | f-195, f-944 | f-203 |
| `us-gaap:RetainedEarningsAccumulatedDeficit` | 2025-09-27 | `retained_earnings_accumulated_deficit` | -14264000000 | f-215 | f-223 |
| `us-gaap:StockholdersEquity` | 2025-09-27 | `stockholders_equity` | 73733000000 | f-219, f-268 | f-227, f-232 |
| `us-gaap:StockholdersEquity` | 2024-09-28 | `stockholders_equity` | 56950000000 | f-220, f-223, f-269 | f-233 |

Multiple parser ids on one side are **within-document complete duplicates**
that already agree under `_duplicates_agree`. They collapse to one
representative. They are not multiple parents.

The other 115 exact candidates remain lawful **dimensional or unmapped**
confirmations. They are retained as lineage candidates. They must not be
used as consolidated core-metric parents unless independently admitted by
the existing metric dimensional contract. `consolidated_only` already
ignores non-empty dimensions (`query.py` `_fact_dimensions_allowed`).

### 2.2 Not confirmation

**Nil, excluded from v1 (1):** `us-gaap:CommitmentsAndContingencies`
instant `2025-09-27`. A1 `f-203` and A2 `f-211` are both nil. Exact
namespace/version and empty dimensions match, but v1 has no nil-confirmation
contract. Class: `nil_confirmation_unspecified`. Do not mint
`xbrl_confirmation`.

**Changed value (1):** `us-gaap:OtherAssetsNoncurrent` instant `2025-09-27`.
A1 `83727000000` (`f-177`, `f-674`, agreeing within-document duplicates).
A2 `72634000000` (`f-185`). Intervals do not overlap at `decimals=-6`.
No confirmation edge. No automatic `AMENDMENT`, `COMPARATIVE_RECAST`,
`RESTATEMENT`, or `SOURCE_CORRECTION`. Separate auditable evidence would be
required to type a reported revision.

**Precision-consistent, unconfirmed (1):** `us-gaap:LongTermDebt`
instant `2025-09-27`. A1 `90678000000` `decimals=-6`. A2 `90700000000`
`decimals=-8`. Intra-instance `_duplicates_agree` is true. Exact
parsed-value and accuracy-token equality is false. **v1 stays exact and
does not widen to `_duplicates_agree`.** Class:
`precision_consistent_unconfirmed`. Duplicate consistency is useful
evidence but does not prove cross-filing equality. Unmapped; not the core
`long_term_debt` alias (`us-gaap:LongTermDebtNoncurrent` `78328000000` is
the mapped exact row).

**No relation (1291):** logical keys present in only one filing. Includes
A2 current-quarter facts with no A1 counterpart and A1 facts the 10-Q does
not reprint. Weak same-concept-and-period near-misses (4 A2
`ConcentrationRiskPercentage1` facts) differ in Apple custom member QNames
(`20250927` vs `20260627` namespaces) and are different economic identities.

---

## 3. Source law (four distinctions)

Verified this session against opened pages.

### 3.1 Within-document duplicate / accuracy consistency

XBRL 2.1 §4.10
<https://www.xbrl.org/specification/xbrl-2.1/rec-2003-12-31/xbrl-2.1-rec-2003-12-31+corrected-errata-2013-02-20.html>:

> Item X and item Y are duplicates if and only if … X is P-Equal to Y, and
> X is C-Equal to Y, and X is U-Equal to Y.

P-Equal: “Nodes are children of the identical parent.”

V-Equal uses the lesser of the two facts’ decimals/precision.

EDGAR XBRL Guide (August 2026) §9.10 Duplicate facts
<https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf>:
an instance must not have more than one fact with S-Equal names, equal
`contextRef`, and V-Equal `unitRef` unless values are consistent with having
been rounded from a single value. Same-decimals facts must be numerically
equal; different decimals use closed overlapping intervals.

XBRL Working Group Note *Handling Duplicate Facts* (2025-01-14)
<https://www.xbrl.org/WGN/xbrl-duplicates/WGN-2025-01-14/xbrl-duplicates-2025-01-14.html>
names complete vs consistent vs inconsistent duplicates **inside one report**.
It does not define a cross-filing confirmation relation.

**Implication:** this is the law already implemented by
`raw_ledger._duplicates_agree`. It does not bind two SEC accessions.

### 3.2 Cross-filing economic equality

No opened XBRL 2.1, EDGAR Guide, or Duplicates WGN clause applies the
duplicate predicate across instance documents. P-Equal cannot hold for nodes
in two files. A later 10-Q reprinting a prior year-end instant is therefore
**not** an XBRL duplicate of the 10-K fact.

Mastermind may still observe that two `FILED` occurrences share `logical_key`
and equal values. That observation is not, by itself, a restatement.

### 3.3 Filing-level amendment

17 CFR § 240.12b-15 (LII/eCFR.io text opened this session): amendments are
filed under cover of the form amended, marked with the letter “A”
(example: `10-K/A`).

EDGAR XBRL Guide on `dei:AmendmentFlag`:

> Value is true if the content of an instance changed from a previous
> submission that this amends, and false otherwise. This is not the same as
> the “/A” indicator on an EDGAR submission type; it is possible for an “/A”
> submission to amend only material that was not XBRL tagged content.

House plane: `sec_document_spine` already owns filing-level
`lineage.is_amendment` / `amends_accession` / `relationship`, and already
records that Submissions does not identify the exact prior accession an `/A`
amends.

A2 is form `10-Q`, not `10-Q/A`. Filing-level amendment evidence is absent.
Even a future `/A` would not, alone, type a fact-level parent.

### 3.4 Fact-level reported revision vs ordinary comparative reprint

Regulation S-X 10-01(c)(1) (17 CFR 210.10-01, LII text opened this session)
requires a Form 10-Q to provide an interim balance sheet as of the most
recent fiscal quarter **and** a balance sheet as of the end of the preceding
fiscal year. Reprinting year-end instants in a later 10-Q is ordinary
comparative disclosure, not a correction signal.

ASC 250 restatement is an error-correction presentation. This session did
**not** open the FASB ASC 250 primary page; restatement typing therefore
stays fail-closed until separate auditable evidence exists. It is not
implied by value equality, later acceptance time, same concept, or same
report period.

No opened primary source names a later identical reprint a “confirmation”.
`xbrl_confirmation` is therefore a **Mastermind** lineage relation type. It
is not `FactEventType.XBRL_CONFIRMATION`.

Company Facts `RevisionEvidence` is a house precedent for **explicit
evidence + `available_at` + fail-closed unique logical-key pairing**. It is
not AAPL core-metric truth (`DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY`).
It remints the child `event_type` at conversion and types every matching
logical key from an accession-level edge. Copying that onto A1/A2 would
either rewrite accepted `FILED` identity or falsely type
`OtherAssetsNoncurrent` as the same relation as `Assets`.

---

## 4. Relation taxonomy (candidate)

Default: `NO_RELATION`.

| Type | Grain | v1 AAPL A1↔A2 | Selector effect |
|---|---|---|---|
| `NO_RELATION` | fact | default, including the 1291 non-overlaps and the changed Other Assets row | unlinked roots remain N/E |
| `xbrl_confirmation` | fact | 130 exact numeric candidates; query uses the 15 consolidated mapped rows; 93 dimensioned receipts are retained as lineage | links roots for `LATEST_KNOWN_AS_OF` only after evidence clock; not a restatement |
| `AMENDMENT` | fact, requires filing-level `/A` **and** fact-level evidence | none | reported revision |
| `COMPARATIVE_RECAST` | fact, requires explicit recast evidence | none (Other Assets is a changed value without evidence) | reported revision |
| `RESTATEMENT` | fact, requires ASC 250-class evidence | none | reported revision |
| `SOURCE_CORRECTION` | fact, requires source-correction evidence | none | reported revision |

`xbrl_confirmation` is a lineage-evidence `relation_type`. It is **not**
`FactEventType.XBRL_CONFIRMATION`. A1 and A2 remain `event_type=FILED`. No
occurrence is reminted. No raw-ledger identity changes.

Form `/A`, later `accepted_at`, same report period, same concept, or same
value **alone** cannot mint any reported-revision type.

Filing-level relationships stay on `sec_document_spine`. Fact-level
relationships stay on lineage-evidence receipts pointing at occurrence ids.

---

## 5. v1 confirmation rule (exact; Sol 2026-08-25)

Mint lineage `xbrl_confirmation` evidence iff **all** of:

1. Parent and child `event_type` are `FILED`.
2. Distinct accessions.
3. Same filer/source family (`sec-edgar` and the same `entity_id`).
4. Parent `accepted_at` is strictly before child `accepted_at`.
5. Same canonical `logical_key`.
6. `dimensions_known=true` on every participating occurrence.
7. Duplicate groups are individually adjudicated with the existing
   within-document `_duplicates_agree` collapse; each filing then has
   exactly one representative (unique parent, unique child).
8. Exact parsed numeric value (`Decimal` equality).
9. Exact `decimals`/`precision` tokens.
10. Approved standard concept namespace (`TAXONOMY_NAMESPACE_POLICY` →
    `us-gaap` or `dei`).
11. Exact original source taxonomy namespace/version: parent and child
    original Clark concept URIs are identical (AAPL proof:
    `http://fasb.org/us-gaap/2025` on both sides for every overlap).
12. Neither fact is nil. Nil facts are out of v1 unless a separate
    nil-confirmation contract is specified.

Fail closed otherwise. Do not invent `revision_of` because a later filing
repeats the period. Do not widen the positive rule to `_duplicates_agree`.
Do not treat metric-catalog admission as a lineage filter.

`_duplicates_agree` remains the intra-instance diagnostic that classifies
`precision_consistent_unconfirmed` versus `changed_value`. It is not
cross-filing equality and does not mint `xbrl_confirmation`.

---

## 6. Architecture comparison

### 6.1 Remint / reclassify the child occurrence

Mechanism: change A2 `FILED` into `FactEventType.XBRL_CONFIRMATION` with `revision_of=A1`.

Breaks:

- `occurrence_id` includes `event_type`, `revision_of`, and clocks.
- A3 ledger SHA and the accepted A2 source identity change.
- Historical A3 cutoff that loads the reminted ledger no longer returns N/E.
- The physical event remains a filed 10-Q fact, not a typed revision.

Company Facts does this **at birth**, and only when evidence is supplied
before the occurrence exists. A3 A2 occurrences already exist as `FILED`.

**Reject** for accepted A3 facts.

### 6.2 Append-only classification overlay without a system clock

Mechanism: extra records pointing at unchanged occurrence ids, visible
whenever both filings are visible.

Breaks the required middle state: after both A1/A2 are knowable but before
lineage evidence exists, A3 must still return N/E. An overlay that becomes
true as soon as A2 is visible is a retroactive repair of A3.

**Reject.**

### 6.3 Cutoff-visible lineage-evidence input (winner)

Mechanism:

- `RawFactLedger.events` stay exactly the A3 `FILED` sequence.
- `FinancialQueryDataset` gains an optional immutable
  `lineage_evidence` collection, default absent/empty (A3, FIP1).
- Each receipt is cutoff-visible: eligible iff
  `source_known_at <= source_snapshot_at` and
  `system_available_at <= recorded_at`.
- `_select_source_group` computes `effective_root` from `revision_of`
  **and** eligible confirmation receipts. Two `FILED` groups that share an
  effective root are one vintage family, not two unlinked roots.
- Evidence is re-checked against current values at query time. Mutation of
  the A2 value refuses the receipt and restores N/E.

This is the same cutoff pattern as `GovernanceBundle` /
`DEC:FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE`, not a second fact ledger.

### 6.4 Can a later classification event coexist with A2 `FILED`?

**Yes, if classification is evidence, not a second occurrence.**

After a valid confirmation is visible:

- A1 `FILED` and A2 `FILED` both remain.
- They are one linked vintage family.
- `LATEST_KNOWN_AS_OF` selects the later `FILED` child (A2) by
  `source_ready` with depth still 0. Confirmation does not increment
  revision depth.
- `AS_REPORTED` still requires `revision_of is None` and `event_type is FILED`,
  then min `source_ready` → A1, the original filed root.
- `LATEST_RESTATED` still requires
  `event_type in _REPORTED_REVISION_EVENT_TYPES`. `FILED` is not in that
  set. Lineage `xbrl_confirmation` is not an occurrence `event_type`.
  Result remains “no eligible explicitly typed reported revision vintage”.
- Packet `revisions[]` iterates ledger events whose `event_type` is in
  `REPORTED_REVISION_EVENT_TYPES`. Confirmation receipts are not those
  events. They do not appear.

If instead a third confirmation occurrence is minted **and** A2
`FILED` remains, `root_ids` stays size 2 unless A2 `FILED` is suppressed.
Suppression of a true `FILED` occurrence as if withdrawn is a lie.
**Reject that design.**

---

## 7. Candidate lineage-evidence receipt

Research contract only. Must not become a mutable store or a provider
dependency of A3.

```
schema: fif3a4r.lineage_evidence_receipt/v1
receipt_id              # stable_id of the canonical payload
parent_occurrence_id    # A1 FILED occurrence
child_occurrence_id     # A2 FILED occurrence
relation_type           # xbrl_confirmation | no_relation | reserved reported types
evidence_rule_id        # e.g. mmx.fif.xbrl_confirmation
evidence_rule_version   # integer, immutable per receipt
evidence_digest         # sha256 of positive evidence or refusal body
source_known_at         # max(parent.accepted_at, child.accepted_at)
system_available_at     # first implementation: no earlier than parent/child
                        # recorded clocks, accepted A4R lineage-rule
                        # availability, and immutable receipt recording
comparison_basis        # exact_parsed_value_and_accuracy_tokens only
logical_key
positive_evidence       # object or null
refusal_reason          # string or null
```

Runtime `FinancialQueryDataset.lineage_evidence` carries **only accepted
positive immutable relations**. The research census may retain positive and
refused classifications. The census JSON is not a provider input and must
never be loaded by production/query code. The census timestamp does not
authorize runtime lineage.

`positive_evidence` (when `relation_type=xbrl_confirmation`) includes parent
and child accession, document id, parser fact ids, source spans, concept,
complete context, dimensions, unit, normalized values, decimals/precision,
and both clocks. Exactly one of `positive_evidence` or `refusal_reason` is
non-null.

Example (control `total_assets`, **not executable**, clocks illustrative of
a later implementation — `system_available_at` must postdate A3 recorded_at):

```
parent_occurrence_id: rawfact_bc9355a292f06baaaf988b683106b2b02e3dd9c4a9555f1eb160a94643e4feaf
child_occurrence_id:  rawfact_9669446bc8076fa26bca33a3d9a067093bddadbb28e4617318bb3de33a4eca29
relation_type:        xbrl_confirmation
comparison_basis:     exact_parsed_value_and_accuracy_tokens
source_known_at:      2026-07-31T10:01:02.000000Z
system_available_at:  <implementation/rule clock strictly after A3 dataset recorded_at>
parsed_value:         359241000000
```

Fail-closed dataset law, matching delivery: absent `lineage_evidence` remains
lawful (A3, FIP1). A non-null collection must be a tuple of receipts with
exact keys. Extra keys, missing clocks, or true production-attestation flags
are unavailable.

---

## 8. Clock law — three states

`source_known_at = max(parent.accepted_at, child.accepted_at)`.

For AAPL Assets: `max(2025-10-31T10:01:26.000000Z, 2026-07-31T10:01:02.000000Z)`
= `2026-07-31T10:01:02.000000Z`.

First-implementation `system_available_at` must be **no earlier than all of**:

- parent and child recorded clocks (`A1 recorded_at`
  `2026-08-23T00:32:31.000000Z`, `A2 recorded_at`
  `2026-08-23T07:02:13.000000Z`);
- accepted A4R lineage-rule availability (this Sol 2026-08-25 bounded
  amendment, not the 2026-08-24 research freeze);
- immutable lineage-evidence receipt recording.

The A4R research census timestamp itself does not authorize runtime lineage.

| State | What is visible | `total_assets` 2025-09-27 |
|---|---|---|
| Before A2 is knowable | only A1 `FILED` | VALUE from A1 |
| After A1 and A2 are knowable, evidence absent or `system_available_at` after `recorded_at` | two unlinked `FILED` roots | A3 N/E |
| After a valid confirmation receipt is cutoff-visible | same two `FILED` occurrences, one effective root | VALUE from A2 `FILED` under `LATEST_KNOWN_AS_OF`; A1 under `AS_REPORTED`; missing under `LATEST_RESTATED` |

Law: a historical A3 cutoff must not retroactively return a value where A3
returned N/E.

Implementation choice that satisfies it: the A3 golden dataset continues to
carry **empty** `lineage_evidence`. A later A4 dataset may add receipts with
`system_available_at` at the rule’s system clock. Querying the A3 dataset
cannot see A4 receipts. Querying an A4 dataset at `recorded_at` before
`system_available_at` projects empty evidence.

Do not encode confirmation by appending events into the A3 ledger object.
That changes ledger SHA `ba149bd…`.

`source_known_at` is the SEC-knowledge bound (both filings accepted).
`system_available_at` is the Mastermind-knowledge bound (the confirmation
rule and the immutable receipt exist). Both must pass, mirroring occurrence
lineage-ready clocks.

---

## 9. Future-behavior matrix (discriminating tests for a later build)

A later FIF-3A4 implementation is not done unless these fail on current A3
and pass only after evidence is wired. Do not add them in A4R.

1. `LATEST_KNOWN_AS_OF` with `recorded_at` before `system_available_at`
   preserves A3 N/E for `total_assets` instant 2025-09-27. Receipt hashes
   stay `58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0`
   when evidence is absent.
2. After a valid confirmation receipt is visible, the same cell is VALUE
   `359241000000` selected from the A2 `FILED` occurrence
   `rawfact_9669446bc8076fa26bca33a3d9a067093bddadbb28e4617318bb3de33a4eca29`.
3. `AS_REPORTED` after the same receipt still selects the A1 `FILED`
   occurrence `rawfact_bc9355a292f06baaaf988b683106b2b02e3dd9c4a9555f1eb160a94643e4feaf`.
4. `LATEST_RESTATED` after the same receipt remains missing / no eligible
   reported revision. Confirmation is not a restatement.
5. `POST /financial/revisions` (and packet `revisions[]`) does not advertise
   a confirmation row. `event_type` remains `filed` on both occurrences.
6. Mutating the A2 Assets `parsed_value` causes confirmation refusal and
   restores N/E. No silent interval rescue.
7. Incomplete dimensions, different units, different economic contexts,
   disagreeing within-document duplicates, and multiple possible parents
   fail closed (AAPL currently has 0 of those at logical-key overlap except
   as already classified).
8. `us-gaap:OtherAssetsNoncurrent` never receives `xbrl_confirmation`.
9. `us-gaap:LongTermDebt` 90,678M vs 90,700M is refused by v1 exact equality
   even though `_duplicates_agree` is true. Class remains
   `precision_consistent_unconfirmed`.
10. FIP1 hashes remain byte-identical when `lineage_evidence` is absent.
11. Hostile extra keys / true attestation flags on the evidence collection
    are private 503, matching delivery fail-closed.
12. Querying A2-only before A2 `accepted_at` cannot see A2 or the receipt.
13. `us-gaap:CommitmentsAndContingencies` nil-nil never receives v1
    `xbrl_confirmation`.
14. A historical cutoff whose `recorded_at` predates `system_available_at`
    preserves A3 N/E even after receipts exist in a later dataset.
15. Runtime `lineage_evidence` containing a refused/nil/precision row is
    unavailable; only accepted positive immutable relations are legal.

Do not modify `query.py`, `raw_ledger.py`, or `metric_registry.py` in A4R
to make the golden example pass. The later build may change `query.py` only
to consume cutoff-visible evidence as a general root-unification law, never
as an AAPL special case.

---

## 10. Expected implementation paths (FIF-3A4, not this wave)

**Would need to change (after Sol releases HOLD-FOR-SOL and authorizes FIF-3A4):**

- `engine/fundamental_forensics/query.py` — `_select_source_group` effective-root
  unification from eligible receipts; no golden special case.
- `engine/fundamental_forensics/query_service.py` — optional
  `FinancialQueryDataset.lineage_evidence`, default absent, fail-closed shape.
- A new small immutable receipt module under
  `engine/fundamental_forensics/` **or** a frozen dataclass beside the
  dataset. Not a database. Not a second ledger.
- Tests named in §9, including AAPL calibration rows from the census.
- Possibly `GoldenAaplFinancialQueryProvider` **only** to attach an empty
  evidence tuple today and a later explicit bundle — without altering
  `GOLDEN_AAPL_QUERY_ACCESSIONS` or converting A2 as a revision.

**Must not change in A4R, and A4 must not change these identities:**

- `engine/fundamental_forensics/raw_ledger.py` occurrence identity,
  `logical_key`, `_duplicates_agree`, `FactEventType` membership of
  `XBRL_CONFIRMATION` in `_REVISION_TYPES`. A4R itself makes **no**
  product modification to `query.py`, `raw_ledger.py`, or
  `metric_registry.py`.
- `engine/fundamental_forensics/metric_registry.py`.
- Frozen FIF-1 packet contract and FIP1 hashes.
- A1/A2 statement composition and statement SHAs.
- A3 ledger SHA, query hash, response SHA.
- `ixbrl_raw_ledger.py` conversion remaining `FILED` with `revision_of=None`.
- A1/A2 fixtures, parser, `sec_document_id` law.
- `revision_service.py` / packet assembler, unless a later fence is needed;
  current `revisions[]` already ignores non-reported event types.
- Production attestation, AAPL packet/revision providers, other issuers.

**Must not do:**

- Source-to-source fusion by timestamp.
- Activating `/financial/revisions` or `/financial/packet` for AAPL.
- Feeding Company Facts into AAPL core metric truth.
- Treating research census JSON as a runtime provider input.
- Loading refused census classes into runtime `lineage_evidence`.

---

## 11. Sol answers (2026-08-25) and remaining holds

Sol ruled **PASS WITH BOUNDED AMENDMENTS**. Remaining holds, not open
architecture forks:

1. Architecture: cutoff-visible overlay is accepted **in principle**. Not
   `LINEAGE_ARCHITECTURE_BLOCKED`. No accepted AgentOS `DEC` until Sol
   releases HOLD-FOR-SOL.
2. v1 stays exact. Do not widen to `_duplicates_agree`. LongTermDebt remains
   `precision_consistent_unconfirmed`.
3. Preserve dimensioned exact candidates as lineage. Query eligibility stays
   the existing metric dimensional contract. Query-relevant subset remains
   the 15 consolidated mapped empty-dimension rows.
4. `system_available_at` floor is parent/child recorded clocks, accepted A4R
   lineage-rule availability, and immutable receipt recording. The research
   census timestamp does not authorize runtime lineage.
5. Sequence: do **not** start FIF-3A4 or another issuer from this amendment.
   HOLD-FOR-SOL remains. Do not merge.

This file is still **not** an accepted `DEC`.

---

## 12. Current-main collision

Sol-observed at original commission: `cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208`.
Original freeze HEAD: `2df738a154acc6feae96e2ad0a6d289d3ab0f4a7`.
Board-shadow date-bomb carrier on #6382 is **removed**. The required
maintenance already landed as PR #6386 (`ASOF` derived from the clock).
STOP-file diff against `origin/main` for
`ixbrl_raw_ledger.py`, `query_service.py`, `sec_document_spine.py`,
`app/forensics.py`, `query.py`, `raw_ledger.py`, `metric_registry.py`,
and A1/A2 fixtures: **empty**.
No A3 product collision. No runtime query behavior change in this wave.
