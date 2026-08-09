# Filing Forensics SEC source store — mint-policy adjudication (2026-08-08)

**Question put.** The Wave-2 immutable SEC source store mints ~121–165 files per run on a
fixed 12-ticker universe with no new information. Does a nightly re-manifest of an
unchanged accession constitute evidence worth retaining — an attestation chain of "we
looked, nothing changed" — or should identical-selection manifests dedupe to one per
`(accession, content)` with a lighter observation log?

**Ruling.** Dedupe is compliant, and is the conforming design. Nightly re-manifests of an
unchanged accession are **not** evidence and never were pre-registered as evidence; the
*observation* they imply **is** evidence and is currently recorded in the worst available
shape. Mint one manifest per `(accession, content)`; record each night's re-derivation as
an explicit append-only observation. Forward-only — nothing already synced is deleted or
rewritten.

This is a **conformance restoration**, not a new design. §10.3 of the program docket
already specified the fields this store was commissioned against, and the shipped code
diverged from them (§3).

Scope: the SEC source store written by `collectors/fundamental_forensics_acquisition.py`
and `engine/fundamental_forensics/sec_document_spine.py`, synced by
`engine/fundamental_forensics/source_sync.py`, consumed by
`engine/fundamental_forensics/disclosure_projection.py`, and run by
`.github/workflows/filing-forensics-sec.yml`. Not in scope: detector semantics
(`DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`, `DNR:HOLD-FF-NEGATIVE-PRIOR-DENOMINATOR`,
`DNR:HOLD-FF-ACCRUALS-ABSENT-FROM-MOAT-SENSORS`), which this ruling does not touch.

---

## 1. The category error

The store fuses three propositions that have different truth conditions and different
lifetimes:

| | Proposition | Changes when |
|---|---|---|
| **P1** | *Filing fact.* Accession A, form F, report date D, accepted at T, declares primary document X with digest H. | The issuer files, amends, or SEC restates. |
| **P2** | *Retention fact.* We retained exactly those bytes, beginning at R. | Never, once retained. Retention has a **beginning**, not a running value. |
| **P3** | *Observation fact.* On night N we re-fetched, re-derived, and got byte-identical content. | Every night. |

A filing manifest asserts P1 + P2. The store currently expresses **P3 by minting a fresh
copy of P1 + P2** — `_manifest_id` hashes the whole body including `clocks.recorded_at`
(`sec_document_spine.py:249-252`, `:622-630`), so a new run clock produces a new identity
for an unchanged filing, and `manifest_storage_key` puts that identity in the path
(`collectors/sec_document_spine.py:412-417`), so it produces a new object.

Four consequences follow, and each is a defect on its own terms:

1. **The manifest count measures our cron, not the issuer.** How many manifest versions
   exist for an accession is a fact about our schedule. An auditor counting them learns
   nothing about the filing.
2. **`recorded_at` no longer means what the module says it means.** The docstring declares
   "`recorded_at` is when our source plane retained the manifest"
   (`sec_document_spine.py:11`). Under nightly re-mint the newest object's `recorded_at` is
   *the last time we happened to run* — the retention *beginning* survives only in older
   objects nothing reads. The PIT claim is degraded by the mechanism meant to reinforce it.
3. **A published field reports store age as coverage.** `coverage.cached_primary_manifest_versions`
   (`disclosure_projection.py:844`) is `len(archive_versions)` — it increments nightly for
   a company that filed nothing. A field named "cached primary manifest versions" that
   grows without any filing activity tells its reader something false.
4. **Every whole-store consumer pays O(nights) to learn O(filings).** `_stored_manifest_versions`
   (`:270-284`) rglobs and fully re-validates every manifest ever persisted, per projection
   build; restore does one GET per manifest entry and sync one conditional PUT plus readback
   per file. Measured 561→1883 restored and 729→2048 synced files in three days
   (`filing-forensics-sec.yml:5-16`).

## 2. The read path has already ruled

The strongest evidence that duplicates are surplus is that **this codebase's own reader
already treats them as surplus**, in two independent places:

- `_source_compatible` (`disclosure_projection.py:254-267`) decides whether an archived
  manifest is the same filing as a freshly derived one by comparing CIK, accession, form,
  base_form, report_date, `accepted_at`, and `filed_on` — and **deliberately omits
  `recorded_at`**. The system already holds that the retention clock is not part of what
  makes a manifest the same filing.
- The selector keeps `max` by `_manifest_version_key` = `(accepted_at, recorded_at, manifest_id)`
  (`:246-251`, `:798`). Of N nightly-identical versions, exactly one is ever read. The other
  N−1 are retained, restored, re-validated, and never consulted.

A store that persists what its only reader has already classified as redundant is not
maintaining an attestation chain. It is accumulating unread bytes.

## 3. The pre-registered contract says `first_observed_at`

Neither program document pre-registers nightly re-manifests as evidence. Both specify the
opposite shape.

`research/CALCBENCH_FUNDAMENTAL_FORENSICS_ENGINE_ASSESSMENT_AND_BUILD_DOCKET_FOR_FABLE.md`
§10.3 "Filing manifest and relationship contract" (`:1327-1348`) lists the minimum filing
fields, among them:

> - source_event_at/accepted_at;
> - first_observed_at;
> - …
> - latest retrieval receipt;

**`first_observed_at`**, not a per-run recorded clock — and **one** "latest retrieval
receipt", singular, not one receipt per night. The same docket at `:820` gives the only
stated rationale for keeping several clocks, and it is about visibility of collector
latency, not about re-minting:

> MastermindX should preserve accepted_at alongside first_observed_at and retrieved_at so
> EDGAR queueing, after-cutoff handling, and collector latency remain visible.

And at `:1387` the docket pre-registers an explicit collapse-duplicates rule (at the fact
layer): *preserve every occurrence, group duplicates, collapse consistent complete
duplicates, flag inconsistent ones.* Duplicate-collapse is house doctrine, not a departure
from it.

The shipped store substituted a per-run `recorded_at` for `first_observed_at` and a
per-run manifest for the single latest receipt. **The divergence from §10.3 is exactly the
defect.** Notably the code already carries the correct two-level identity and only misuses
the upper level: `filing_id = stable_id("sec_filing", cik, accession)` is accession-stable
(`sec_document_spine.py:606`), while `manifest_id` was intended as the *content version*
and currently behaves as a *run version*.

Also on the record: the lane comment itself frames nightly-unique manifests as cost to be
contained, never as declared evidence (`filing-forensics-sec.yml:5-16`), and
`research/DO_NOT_REBUILD.md` carries no row on manifest identity, clocks-in-hash, content
addressing, dedupe, or attestation retention.

## 4. The steelman, and why it fails

**"Minting a sealed object per observation is maximally defensible — you can never be
accused of silently suppressing an observation. A log is one structure someone could
truncate."**

This argues for the log. The observation log is also append-only immutable objects created
under `If-None-Match` (`source_sync.py:801-834`), so truncation is equally prevented — and
*more* detectable: a dated per-run sequence has a checkable shape, so a missing night is
visible as a gap. A pile of hash-named duplicates has no expected cardinality, so a missing
one is undetectable by construction. Defensibility favours the log.

Further: a byte-identical-modulo-clock re-manifest does not actually record *what was
verified*. It records that a write happened. The log records the check — which digest was
recomputed, against which manifest, at what clock, with what outcome. It is strictly more
evidence, in fewer bytes.

**"Last-seen `recorded_at` is useful: it tells you the data is fresh."**

Freshness is a property of the observation, not of the filing manifest — and it is
**already served elsewhere**. The projection's own freshness clock is taken from the
retained submissions receipt, not from any manifest:
`recorded_at = str(submissions_receipt["retrieved_at"])` (`disclosure_projection.py:773`),
flowing to `value["clocks"]["recorded_at"]` (`:831`). Making manifest `recorded_at` mean
first-retention therefore costs no freshness signal that any consumer reads.

**Where the steelman does land.** "We looked and nothing changed" is genuine evidence, and
for a change-detection product it is load-bearing: a forensics engine that cannot prove it
looked is asserting absence from silence. That claim survives in full — R3 exists precisely
to carry it, explicitly and queryably, instead of leaving it implied by file multiplicity.

## 5. Ruling

- **R1 — One manifest per `(accession, content)`.** The mint becomes idempotent: before
  writing, look for a stored manifest for `(cik, accession)` whose content-bearing
  projection equals tonight's. If found, reuse it verbatim and write no manifest. If not,
  mint as today. New content ⇒ new manifest ⇒ new id, exactly as now.
- **R2 — `recorded_at` means first retention of that exact content** (`first_observed_at`
  semantics, per §10.3). Reuse carries the original clock forward; it is never rewritten.
- **R3 — An append-only observation log carries P3.** One object per run covering all
  targets, each row binding ticker, CIK, accession, the manifest reused or minted, the
  recomputed content digest, the observation clock, and an outcome in
  `{unchanged, new_content, new_filing, missing}`. This is where "we looked, nothing
  changed" lives — as an assertion, not as an artifact count.
- **R4 — Forward-only. No deletion, no rewrite.** Every object already synced stays
  exactly where it is and stays byte-restorable. The store stops *growing* by duplication;
  it does not shrink. Reclaiming historical duplicates is a **separate ruling** requiring
  proof that no `ffsecsrc_` snapshot pins them (§6).
- **R5 — The identity hash is unchanged.** `_manifest_id` keeps committing to every
  persisted field; `validate_manifest_identity` keeps enforcing it. Ids stabilise because
  their *inputs* stop moving, never because the hash was weakened. This is what keeps the
  identity tests green (§7).
- **R6 — Acquisition run receipts: correct identity, wrong transport.** `_run_id`
  legitimately hashes the run clocks — a run *is* a distinct event, so this is not the
  category error of R1 and `_run_id` keeps its current definition. The defects are that it
  writes one file per ticker per run (13/night) and that these sit inside the restorable
  tree while **no production code reads them back** (only tests reference
  `ACQUISITION_RELATIVE_ROOT`; `read_verified_submissions` reads the *raw submissions*
  receipt, a different artifact). Fold them into the R3 per-run object and move that object
  out of the restore working set: restore exists to reconstitute replay inputs, and our
  cron history is not one.

**Submissions objects are unaffected.** They are content-addressed and mega-cap submissions
JSON genuinely changes near-daily, so each new object is real new information. They become
the dominant remaining growth (~12/day ≈ 4.4k/yr). Whether an unbounded retention horizon
for daily submissions snapshots is warranted is a real question, deferred here and flagged
in §9 — it is not answered by this ruling.

**Effect.** Uninformative growth (~121–165 files/night, ~45k/yr) collapses to one
observation object per night plus a manifest only when a filing genuinely appears or
changes. The manifest set becomes bounded by filing reality (~8 per ticker, ~96 total)
rather than by store age, so `_stored_manifest_versions`, restore, sync, and the
`ffsecsrc_` snapshot enumeration all become O(filings) instead of O(filings × nights).
Remaining growth is real information.

## 6. Compat — two hard walls

**Wall 1: sealed attestations pin manifests by exact key.**
`filing_package.py:1145-1176` reads `manifests/{cik}/{accession}/{manifest_id}.json`
through a `PinnedSourceAuthority` bound to an `ffsecsrc_` source snapshot, then re-derives
`manifest_storage_key(manifest)` and requires it to equal the key it read. Any manifest
object pinned by any existing source snapshot must remain byte-restorable **forever**. This
is a live coupling, not theoretical: AAPL is both a Wave-2 target
(`config/fundamental_forensics/wave2_targets.v1.json`) and the attested-history seed
subject (`.github/workflows/attested-history-aapl-seed.yml`).

**Wall 2: immutable create refuses overwrite.** `source_sync._create_immutable`
(`:801-834`) writes under `If-None-Match` specifically so a competing writer cannot
overwrite an immutable object. Rewriting a manifest in place is structurally prohibited,
not merely unwise.

Both walls are satisfied by R4 + R5: the change is to *what tonight mints*, never to what
last night wrote. Note the direction of benefit — under R1 a sealed attestation's pinned
manifest stays the current one instead of being superseded within 24 hours.

## 7. Implementation plan

Sequenced so each phase is independently shippable and reversible.

**Phase 1 — content key (pure function, no behaviour change).**
Add `manifest_content_key(record)` to `sec_document_spine.py`: canonical-JSON digest of the
manifest body **excluding** `manifest_id`, `clocks.recorded_at`, and each document's
`retrieval.retrieved_at` / `retrieval.receipt_id`. Those three are fetch-event clocks;
`content_sha256`, `byte_length`, and `storage_key` stay in the key because they are byte
identity. Derive it *outside* the persisted body — do **not** add a field to the manifest,
or the first post-migration run re-mints every manifest once for a schema reason. Unit
tests: two manifests differing only in run clocks share a content key; any content
difference (digest, form, lineage, document set) separates them.

**Phase 2 — idempotent mint.**
In the acquisition path, before persisting, index stored manifests for `(cik, accession)`
by content key and reuse on hit. On reuse, write nothing to the manifest tree and emit an
`unchanged` observation row. On miss, mint with tonight's clocks and emit `new_content` or
`new_filing`. The index is a scan of the manifest set, which R1 makes bounded — no separate
index object is needed at this size.

**Phase 3 — observation log.**
New schema `fundamental_forensics.sec_observation_log/v1`, one immutable object per run
under a prefix **outside** the restorable source tree, carrying every target's rows plus
the run-level fields today's `run.json` holds. Retire the per-ticker receipt writes.
Immutable-create semantics identical to the rest of the store.

**Phase 4 — projection follow-through.**
`coverage.cached_primary_manifest_versions` now counts content versions rather than run
versions. Keep the field, and state the meaning at its definition site; consider a sibling
`cached_primary_observations` sourced from the log if a coverage-over-time read is wanted.

**Known-breaking, intentional.** These fail on purpose and are updated as part of the work,
with the reason recorded in the test:
- `tests/test_fundamental_forensics_acquisition.py:152,176` assert the receipt path
  `ACQUISITION_RELATIVE_ROOT / run_id / "<TICKER>.json"`. Phase 3 removes that path. Replace
  with assertions on the per-run observation object.
- Any test asserting that a second build with a *later* clock produces a *different*
  manifest id for unchanged content now asserts reuse instead.

**Expected green, and worth confirming explicitly** — R5 exists to protect these:
`tests/test_sec_document_spine.py:127-137` (three explicit clocks present),
`:181-195` (deterministic round-trip at a fixed `RECORDED_AT`), `:201-219`
(storage key binds identity). All build at a fixed clock, so an idempotent mint does not
move them.

**Verification.** Beyond unit tests: run the lane twice against an unchanged universe and
assert the manifest tree is byte-identical across runs while the observation log gains
exactly one object; then assert the published disclosure bundle's restore self-check
(`filing-forensics-sec.yml:119-173`) still passes. One live two-run probe is the acceptance
evidence — a green fixture suite alone does not demonstrate idempotence against real SEC
responses.

**Migration is a no-op by construction.** No backfill, no rewrite, no deletion. Night one
after Phase 2 finds no content-key match for any accession (nothing was indexed under one
before), mints the current generation once, and every night after reuses it.

## 8. What this ruling does not license

- Deleting or rewriting any already-synced object (R4). Historical duplicate reclamation
  needs its own ruling with `ffsecsrc_` pin proof.
- Weakening `_manifest_id`, `validate_manifest_identity`, or the storage-key binding (R5).
- Dropping `recorded_at`, `retrieved_at`, or `receipt_id` from manifests. They stay; only
  *which value* `recorded_at` carries changes, to first retention.
- Skipping the nightly fetch. The observation must be a real re-derivation from a freshly
  retrieved response, or the log asserts a check that did not happen. Content-addressed
  skipping of the ~128MB nightly re-download is a **separate** perf question (§9) and must
  not be smuggled in as part of dedupe — that would hollow out the very evidence R3 records.
- Any change to detector period basis, denominators, or sensor coverage — the three
  standing FF holds are untouched.

## 9. Riders / deferred

- **Submissions retention horizon.** After this ruling, near-daily submissions objects are
  the dominant remaining growth. Each is genuine new content, so they stay; whether
  unbounded retention is warranted is a separate ruling.
- **Nightly ~128MB SEC re-download** inside the lane — real, unaddressed, and gated by the
  last bullet of §8.
- **Sibling store.** `engine/capital_structure/source_identity.py` has its own
  `manifest_id_for`. It should be checked for the same category error; not audited here.
- **Stale synapse registration** for the old producer/cadence — Intel Hub audit territory,
  carried over from the PR #4986 chip list.

## 10. Record

- Diagnosis: PR #4986 (moved the store off the render path; added opt-in incremental
  restore/sync). This ruling answers the evidence question that PR explicitly deferred.
- Registry: `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` (§3, minted with this document).
- Sources cited inline by `path:line` against `origin/main` at `395cd541ef5`.
