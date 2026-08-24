# FIF-3A4R — Cross-filing fact lineage protocol

Status: **SPEC_ONLY / CANDIDATE FOR SOL**. Not accepted AgentOS authority.
Not built. Not shipped. Not a runtime provider. Not a second ledger.

Research wave only. Do not code FIF-3A4 from this file until Sol accepts or
amends the candidate.

Replay census: `research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json`
Replay tool: `research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py`

Base HEAD at freeze: `2df738a154acc6feae96e2ad0a6d289d3ab0f4a7`.
Sol-observed main at commission: `cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208`
(ancestor of freeze HEAD; A3 product owners empty-diff).

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
`XBRL_CONFIRMATION`. That changes `occurrence_id` (identity payload includes
`event_type` and `revision_of`) and rewrites accepted A3 source identity.

**Rejected:** appending a third `XBRL_CONFIRMATION` `RawFactOccurrence` while
keeping A2 `FILED`. After the confirmation clock, `_select_source_group`
still sees two roots unless a suppression law hides A2 `FILED`. That is two
identities for one physical fact, plus a ledger-SHA change.

`FactEventType.XBRL_CONFIRMATION` already exists on the kernel as a revision
type that requires `revision_of` and is **absent** from
`_REPORTED_REVISION_EVENT_TYPES` / packet `REPORTED_REVISION_EVENT_TYPES`.
Keep that enum as a reserved conversion-time exclusive type. A4R v1 must
**not** stamp it onto accepted A2 `FILED` rows. The v1 relation name lives on
the evidence receipt, not on the occurrence.

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
| `exact_complete_confirmation_candidate` | **131** |
| of which empty-dimension | 38 |
| of which dimensioned | 93 |
| of which core-mapped (any dimensions) | 46 |
| of which **query-relevant** (empty-dimension, core-mapped, non-nil) | **15** |
| `precision_different_value_consistent` | 1 |
| `changed_value` | 1 |
| `incomplete_dimensional_scope` | 0 |
| `custom_unmapped_taxonomy` | 0 |
| `ambiguous_duplicate_group` | 0 |
| `multiple_possible_parent` | 0 |
| `nil_state_difference` | 0 |
| `unit_context_concept_mismatch` at logical-key overlap | 0 |

Ledger SHA of the replayed A3 ledger remains
`ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8`.

Census payload SHA-256 (canonical JSON excluding the digest field):
`d705de0dddab9761441aa9649b973dcd2f7ac2c265282658446b8bba6a8d4be0`.
Written file SHA-256:
`e405b4094e8905a9384fb1aef3c694c2e6b7244eabd7164ba3f73082822d0018`.

### 2.1 Safe v1 confirmation candidates

**All 131** `exact_complete_confirmation_candidate` rows are lawful fact-level
confirmation candidates: same filer family (`sec-edgar` / CIK `0000320193`),
same `logical_key`, `dimensions_known=true`, unique parent/child after the
existing within-document duplicate collapse, identical `parsed_value` and
identical `decimals`/`precision` tokens, taxonomy `us-gaap` or `dei`.

They are **not** SEC-called confirmations. They are Mastermind typed lineage
interpretations.

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

The other 116 exact candidates remain lawful **dimensional or unmapped**
confirmations. They must not be used as consolidated core-metric parents.
`consolidated_only` already ignores non-empty dimensions
(`query.py` `_fact_dimensions_allowed`).

### 2.2 Not confirmation

**Changed value (1):** `us-gaap:OtherAssetsNoncurrent` instant `2025-09-27`.
A1 `83727000000` (`f-177`, `f-674`, agreeing within-document duplicates).
A2 `72634000000` (`f-185`). Intervals do not overlap at `decimals=-6`.
No confirmation edge. No automatic `AMENDMENT`, `COMPARATIVE_RECAST`,
`RESTATEMENT`, or `SOURCE_CORRECTION`. Separate auditable evidence would be
required to type a reported revision.

**Precision-different, value-consistent (1):** `us-gaap:LongTermDebt`
instant `2025-09-27`. A1 `90678000000` `decimals=-6`. A2 `90700000000`
`decimals=-8`. `_duplicates_agree` is true (existing interval law). Exact
parsed-value and accuracy-token equality is false. **v1 confirmation
excludes this.** A later expansion may reuse `_duplicates_agree` rather than
invent a second tolerance. Unmapped; not the core `long_term_debt` alias
(`us-gaap:LongTermDebtNoncurrent` `78328000000` is the mapped exact row).

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
`XBRL_CONFIRMATION` is therefore a **Mastermind** relation type.

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
| `XBRL_CONFIRMATION` | fact | 131 exact candidates; query uses the 15 consolidated mapped rows | links roots for `LATEST_KNOWN_AS_OF` only after evidence clock; not a restatement |
| `AMENDMENT` | fact, requires filing-level `/A` **and** fact-level evidence | none | reported revision |
| `COMPARATIVE_RECAST` | fact, requires explicit recast evidence | none (Other Assets is a changed value without evidence) | reported revision |
| `RESTATEMENT` | fact, requires ASC 250-class evidence | none | reported revision |
| `SOURCE_CORRECTION` | fact, requires source-correction evidence | none | reported revision |

Form `/A`, later `accepted_at`, same report period, same concept, or same
value **alone** cannot mint any reported-revision type.

Filing-level relationships stay on `sec_document_spine`. Fact-level
relationships stay on lineage-evidence receipts pointing at occurrence ids.

---

## 5. v1 confirmation rule (conservative)

Mint `XBRL_CONFIRMATION` evidence iff all of:

1. Same `SourceIdentity.source` family and same `entity_id`.
2. Same `logical_key`.
3. `dimensions_known is True` on every participating occurrence.
4. After `_duplicates_agree` collapse, each filing has exactly one
   duplicate group (unique parent, unique child).
5. Same unit semantic key (already implied by `logical_key`).
6. Complete numeric equality: identical nil state, identical canonical
   `parsed_value`, identical `decimals` and `precision` tokens.
7. Child `accepted_at` is not before parent `accepted_at`.
8. Taxonomy is `us-gaap` or `dei` (custom overlap is a separate class; AAPL
   had zero custom overlaps).

Fail closed otherwise. Do not invent `revision_of` because a later filing
repeats the period.

Precision-different consistent values reuse `_duplicates_agree` if Sol later
widens v1. Do not add a second tolerance algorithm. AAPL has exactly one
such row (`us-gaap:LongTermDebt`).

---

## 6. Architecture comparison

### 6.1 Remint / reclassify the child occurrence

Mechanism: change A2 `FILED` into `XBRL_CONFIRMATION` with `revision_of=A1`.

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
  set. `XBRL_CONFIRMATION` as a receipt type is not an occurrence
  `event_type`. Result remains “no eligible explicitly typed reported
  revision vintage”.
- Packet `revisions[]` iterates ledger events whose `event_type` is in
  `REPORTED_REVISION_EVENT_TYPES`. Confirmation receipts are not those
  events. They do not appear.

If instead a third `XBRL_CONFIRMATION` occurrence is minted **and** A2
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
system_available_at     # when this rule/receipt became system-known
comparison_basis        # exact_parsed_value_and_accuracy_tokens
                        # (v1.1 may add duplicate_consistency_interval)
logical_key
positive_evidence       # object or null
refusal_reason          # string or null
```

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
rule/receipt exists). Both must pass, mirroring occurrence lineage-ready
clocks.

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
8. `us-gaap:OtherAssetsNoncurrent` never receives `XBRL_CONFIRMATION`.
9. `us-gaap:LongTermDebt` 90,678M vs 90,700M is refused by v1 exact equality
   even though `_duplicates_agree` is true.
10. FIP1 hashes remain byte-identical when `lineage_evidence` is absent.
11. Hostile extra keys / true attestation flags on the evidence collection
    are private 503, matching delivery fail-closed.
12. Querying A2-only before A2 `accepted_at` cannot see A2 or the receipt.

Do not modify `query.py` in A4R to make the golden example pass. The later
build may change `query.py` only to consume cutoff-visible evidence as a
general root-unification law, never as an AAPL special case.

---

## 10. Expected implementation paths (FIF-3A4, not this wave)

**Would need to change (after Sol accepts):**

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

**Must not change:**

- `engine/fundamental_forensics/raw_ledger.py` occurrence identity,
  `logical_key`, `_duplicates_agree`, `FactEventType` membership of
  `XBRL_CONFIRMATION` in `_REVISION_TYPES`.
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

---

## 11. Unresolved questions for Sol

1. Accept cutoff-visible evidence overlay as the architecture, or reject in
   favor of `LINEAGE_ARCHITECTURE_BLOCKED`?
2. Keep v1 confirmation at exact parsed-value and accuracy tokens (131 AAPL
   rows; 15 query-relevant), or widen immediately to `_duplicates_agree`
   (adds the one `LongTermDebt` 90,678M vs 90,700M row)?
3. Should query-relevant confirmation be further restricted to empty
   dimensions (recommended: yes, because `consolidated_only` already does
   that), while still recording dimensional exact matches as fact-level
   receipts that do not feed core metrics?
4. Where should `system_available_at` for the first AAPL receipts be
   pinned — implementation merge time, a dedicated rule `available_at` in
   governance, or a golden fixture clock after `2026-08-23T07:02:13Z`?
5. Sequence next: implement FIF-3A4 against AAPL only, or freeze this
   protocol and keep FIF-3 on another issuer without lineage?

This file is not an accepted `DEC`. Sol rules.

---

## 12. Current-main collision

Sol-observed: `cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208`.
Freeze HEAD / current `origin/main` at research closeout:
`2df738a154acc6feae96e2ad0a6d289d3ab0f4a7`.
Sol-observed is an ancestor of freeze HEAD. STOP-file diff against
`origin/main` for
`ixbrl_raw_ledger.py`, `query_service.py`, `sec_document_spine.py`,
`app/forensics.py`, `query.py`, `raw_ledger.py`, `metric_registry.py`,
and A1/A2 fixtures: **empty**.
Main moved past Sol-observed on skip-ci / government-revenue / marketing
paths only.
No A3 product collision. No runtime query behavior change in this wave.
