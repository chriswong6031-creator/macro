# K2-C — Institutional Adapter Pilot: adoption map + frozen design

**Operation key:** `alpha-k2c-institutional-adapter-20260826-sol-001`
**Commission:** `agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-26-k2c-commission.md`
**Pickup main:** `13b9660f3188ed9915e750515c1502cfd33c9bf1` · collision census clean (no K2-C PR/branch).
**State:** design frozen 2026-08-27; proof receipts appended in §7 when they exist.

## 0. Acceptance gates (not done unless)

- One K2-C carrier; RED-first falsifiers for every case in the commission's
  acceptance list; focused + combined K1/K2-B/K2-C suites green; hosted CI/fences.
- One real two-period owner-read `owner → K1 → K2-B → K2-C receipt` through an
  authorized production-read principal, plus one real/owner-shaped refusal case —
  or the exact `PRODUCTION_OWNER_READ_AUTH_REQUIRED` blocker. Green CI without the
  real read is `BUILT_NOT_PROVEN`.
- No second institutional store, reader, identity plane, correction plane,
  scheduler, ranker, grader, or authority surface (§2 adoption map proves reuse).
- Adapter cannot author compiler results; every missing/ambiguous/rights/clock
  defect is typed, never numeric zero.

## 1. Owner adoption map (what exists; what K2-C composes; what it may NOT do)

All owner primitives are consumed as-is from `engine/institutional_census/**`;
K2-C adds **zero** owner code and speaks no raw R2/S3 semantics.

| Need | Existing owner primitive (adopted) |
|---|---|
| Store handle | `storage.build_institutional_13f_store(local_dir=…)` or the four `INSTITUTIONAL_13F_R2_*` env vars; fail-closed, no generic-credential fallback (`storage.py:86`) |
| Catalog discovery | `catalog.load_catalog_generation(store, report_period=…, generation_id=None)` — current pointer (sole discovery authority) or an explicit immutable generation (`catalog.py:912`) |
| Verified object reads | `storage.read_verified_object` (digest + byte-length proof, `storage.py:157`); parquet/JSON decode inside `catalog._load_generation` |
| Filing ↔ receipt binding | filing row `source_receipt_id`/`raw_sha256` → `models.raw_receipt_key` + `storage.load_raw_evidence` (receipt key-binding + raw digest proof) |
| Row schema | `catalog._HOLDINGS_FIELDS` / `_FILINGS_FIELDS` / `_MANAGER_FIELDS`; holdings PK = `(accession, infotable_sk)`, integrity `row_hash` |
| Clocks | filing/receipt `accepted_at`·`retained_at` (knowable = max of the two); generation `CatalogClocks.source_cutoff_at`·`published_at`; `report_period` is valid-time ONLY |
| Amendment lineage | filing `is_amendment`/`amendment_number`/`amendment_type`/`amends_accession`/`lineage_state`; catalog successor law `_assert_catalog_successor` |
| K1 anchoring | vocabulary owner stores `institutional_13f.raw_receipt` and `institutional_13f.catalog_generation` (both pre-registered in `contracts/evidence_foundation/vocabulary.v1.json`); `lib.evidence_foundation.validate_reference` |
| Intent semantics | `lib.institutional_intelligence.validate` / `compile_recipe` — the ONLY author of deltas/eligibility/reliability |

**Deliberate non-reads:** no `list_prefix`/generation enumeration (a historical
compile requires an explicit, caller-retained `generation_id`; the current pointer
answers only current truth); no per-CUSIP bounded read exists (bucket parquet is
whole-object verified — accepted for the pilot); no ETF/ARK/borrow/sponsor owners.

## 2. No-second-plane proof

- **Store/reader:** adapter takes a built store handle; only owner read APIs above.
- **Identity:** no new filer/vehicle/complex registry; pilot epochs are explicit
  in-recipe declarations (K2-B objects) derived from owner rows, not a registry.
- **Correction:** amendment/supersession is read from owner fields; adapter never
  writes or re-orders lineage.
- **Scheduler/authority:** no schedule, no rank/gate/size/origination/entry; the
  K2-B `ALL_FALSE_AUTHORITY` envelope is preserved end-to-end.
- **Persistence:** `persistence: none`; no owner payload is copied into any store;
  the pilot receipt carries identities, clocks, hashes, q-values, and typed states.

## 3. Security identity ruling (K1 subject = owner-native CUSIP)

Verified 2026-08-27: the repo has **no authoritative CUSIP→Data OS bridge** — the
security master's vendor-alias spaces are `yahoo`/`membership`/`ledger`/
`yahoo_fetch`/`store`/`theme_graph_native` (no `cusip` space);
`engine/entity_resolver.resolve_cusip` is context-only and
`aggregate.load_ticker_map` is display-only. Fabricating a bridge, or promoting a
display-tier map to K1-grade identity, would create the forbidden second identity
plane.

Ruling: the pilot's **requested canonical security identity is the owner-native
CUSIP** — a first-class K1 `subject_key_type` (`cusip` in
`vocabulary.v1.json`). The adapter proves `row.cusip == requested.cusip` exactly
(grammar `^[0-9A-Z]{9}$`), and the Data OS axis is carried as a **typed
unresolved** field (`dataos_security_id: null`,
`dataos_resolution: "unresolved_no_authoritative_cusip_plane"`), never silently
bridged, never dropped. Closing that gap (a rights-clean CUSIP alias space in the
security master) is future Data OS work, not K2-C.

## 4. K2-B contract extension: `source_backed_owner_row` (v1.1.0)

K2-B's `evidence_basis` enum is closed at
`{source_backed_pointer_only, synthetic_fixture_positive, synthetic_fixture_adverse}` —
a real owner-read security observation is unrepresentable today (that gap is named
in `contracts/institutional_intelligence/README.md`). K2-C adds ONE closed basis:

- `evidence_basis: "source_backed_owner_row"` — the observation MUST carry
  `owner_row_binding` (forbidden on every other basis):

```
owner_row_binding = {
  "security": {"key_type": "cusip", "cusip": "^[0-9A-Z]{9}$",
                "dataos_security_id": null|string,
                "dataos_resolution": "unresolved_no_authoritative_cusip_plane"|"alias_table_resolved"},
  "previous": <ownerPeriodBinding>,   # Q_prev provenance
  "current":  <ownerPeriodBinding>,   # Q_now provenance
}
ownerPeriodBinding = {
  "catalog_binding":    <referenceBinding to an evidence_refs entry with
                         owner_store institutional_13f.catalog_generation>,
  "raw_receipt_binding":<referenceBinding to an evidence_refs entry with
                         owner_store institutional_13f.raw_receipt>,
  "row": {"accession", "infotable_sk", "row_hash", "cusip"},
}
```

Semantic law (validator, RED-first): each binding resolves to a distinct listed
K1 ref of the right owner store; `row.accession ==` raw-receipt native
`accession`; the catalog binding's native `report_period` equals the raw ref's
world-valid `report_period`; `previous.report_period < current.report_period`;
`row.cusip == security.cusip == subject_id` (grammar `cusip:<CUSIP>`); every
sub-binding's `available_clock` is PINNED per owner store — a raw-receipt
binding's operational availability is `max(accepted_at, retained_at)` and a
catalog binding's is `clocks.published_at`, with the reference's
`freshness.clock_field` pinned to match, and the compile-time gate recomputes
availability from the reference's own clocks (never the caller-declared
binding), so a forged clock declaration is validate()-rejected rather than
silently positive; `measure.kind == "reported_share_change"` with numeric
`q_prev`/`q_now` or a typed unavailable measure. The compiled event receipt
carries `owner_row_reference_states` naming each of the four refs' PIT state
individually (absence kinds are never collapsed into one boolean). The compiler treats a valid
owner-row observation as security-bound (eligible for
`MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT`); every existing basis behaves
byte-identically (combined K1+K2-B suites are the regression gate).

`q` semantics (frozen): `q = ssh_prn_amt` with `ssh_prn_type == "SH"` (share
count); rows with `put_call` set are excluded from selection; a PRN-typed or
derivative-only position is a typed unavailable measure, never zero. Denominator:
`public_reported_sleeve` in position counts — `state: "complete"` only when the
effective filing's decoded row count equals `table_entry_total` and
`confidential_omitted` is false; otherwise `partial`/`unknown` with counts.

## 5. Adapter (`lib/institutional_13f_adapter.py`) — read path law

1. `resolve_generation(store, report_period, cutoff, generation_id=None)` —
   current pointer or explicit generation; refuse
   `generation_not_knowable_at_cutoff` when `published_at > cutoff`.
2. `select_effective_filing(generation, filer_cik, cutoff)` — 10-digit CIK; only
   filings knowable ≤ cutoff; amendment lineage resolved by owner fields with
   supersession applying only from the amendment's own knowable clock; a partial
   (non-restatement) amendment composition → typed
   `amendment_composition_unsupported`; ambiguous lineage → typed refusal.
3. `select_security_row(generation, accession, cusip)` — exact-CUSIP equity rows;
   0 → `security_not_in_filing`; >1 → `ambiguous_holdings_rows`; unit law per §4.
4. Receipt cross-check — `load_raw_evidence` receipt must match the filing row on
   `source_receipt_id`, `raw_sha256`, `accepted_at`, `report_period`, filer CIK;
   any mismatch → `source_receipt_mismatch` (hard).
5. K1 refs built deterministically for both stores/periods (mirroring the frozen
   K2-B raw-receipt reference shape); recipe assembled with explicit pilot epochs
   (decision mode from owner `investment_discretion`, `SOLE` → discretionary,
   else typed); `compile_recipe` is the only author of results.
6. Output: `institutional_owner_read_receipt.v1` — canonical-JSON, content-derived
   id, naming inputs, exact generations (id + manifest digest — generation ids
   are content-derived and re-verified on decode, so the explicit-generation
   path is digest-bound too), effective filings/accessions, asserted row
   identities (`infotable_sk`, `row_hash` — replayable against the immutable
   store; the contract validator cannot itself read the store), K1 reference
   ids, the FULL recipe (independently re-compilable: `compile_recipe` over
   `receipt["recipe"]` must reproduce `receipt["compiled"]`), q values +
   denominator receipts, typed states, and a pointer block typed by read-state
   (`read` on the current-pointer path; `not_read` on the explicit path — no
   fabricated currency claims). `state` distinguishes `PILOT_COMPILED` (eligible
   positive) from `PILOT_COMPILED_NON_POSITIVE` (lawful compile, non-positive
   observation — the top-level measure is then typed `not_compiled` with no
   q-pair) from typed refusals (including `report_periods_not_increasing`,
   checked before any read). Deterministic on identical owner inputs.
7. CLI (`python -m lib.institutional_13f_adapter …`) — read-only; env store or
   `--local-dir`; prints the receipt JSON. Store outage/timeouts raise (never
   typed absence); no retry of any effect-unknown operation (all ops are reads).

## 6. Real-proof path (authorized production-read principal)

Production credentials exist only as repo CI secrets (census/conformance lanes
map `R2_*` → `INSTITUTIONAL_13F_R2_*`; verified no local/host copy). The pilot
therefore ships `.github/workflows/smart-money-13f-k2c-pilot.yml`:
`workflow_dispatch` only, main-only, read-only, single job on
`[self-hosted, macstudio-light]`, census-style pinned venv/lock, runs the adapter
CLI for an operator-supplied filer/CUSIP/period pair, uploads the receipt
artifact. No schedule, no writes, no catalog publication. This is the smallest
lawful extension of the existing authorized principal; flagged to Sol as a scope
addition in the return.

Known context at design time: the rolling census lane has been red since
~2026-08-25 (SEC filing-index parse failures; separate outage, separate repair
lane) — historical generations remain immutable and readable, so the pilot reads
existing Q1/Q2-2026 generations; amendment freshness is degraded until that lane
heals and is disclosed in the proof receipt's caveats.

## 6b. Independent adversarial review (2026-08-27)

An opus reviewer attacked head `ffee8e11f121` across eight axes with working
reproductions. Verdict: 1 BLOCKER, 3 MAJOR, plus minors/notes — all repaired on
this carrier at `51ffcc242801` (RED-first per finding; combined focused gate
333 passing):

1. BLOCKER — owner-row PIT gate accepted caller-declared availability clocks on
   3 of 4 sub-bindings (forged `accepted_at`/`source_cutoff_at` clocks compiled
   hindsight positives). Repaired: per-store pinned clock law, validate-time and
   compile-time (§4).
2. MAJOR — non-SOLE path emitted `PILOT_COMPILED` with the refused q-pair at
   top level, and fabricated a vehicle class. Repaired: `PILOT_COMPILED_NON_POSITIVE`,
   typed measure, documented closed-enum placeholder mapping. Residual honesty
   gap flagged to Sol: K2-B's closed `vehicle_class` enum has no truthful class
   for a generic 13F reporting vehicle — a future K2-B vocabulary amendment
   candidate, deliberately NOT smuggled into this wave.
3. MAJOR — receipt pointer block asserted currency/non-supersession never read
   on the explicit-generation path. Repaired: read-state-typed pointer block.
4. Findings 4/5/7/8/9/10/12 (typed period-order refusal; row-identity claim
   softened to replayable assertion; per-ref PIT states; `retained_at`
   cross-check; explicit-path digest-boundness confirmed content-derived;
   embedded re-compilable recipe; honest unknown-denominator counts) — all
   repaired or clarified as recorded in the review packet and `51ffcc242801`.
5. Finding 6 (proof lane lacked generation-id inputs; overbroad determinism
   claim) — repaired in the workflow by the commissioning session.
6. Finding 11 — acceptance-state honesty: this carrier is `BUILT_NOT_PROVEN`
   until §7 carries a real production owner-read receipt.

## 7. Proof receipts

Real production owner-reads through the dispatch-only proof lane on main
(merge 0758de6b9a7e), 2026-08-27. Full receipts are the runs' 90-day artifacts;
the load-bearing fields are frozen here verbatim.

**Positive two-period case** — run 33058216623: Custos Family Office, LLC
(filer CIK 0001904423) × ABBVIE INC (CUSIP 00287Y109), report periods
2026-03-31 → 2026-06-30, both filings accepted 2026-08-19 (PIT-lawful at the
dispatch cutoff). Compiled `PILOT_COMPILED` /
`MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT`; q 1238 → 1279 shares — equal to the
EDGAR-published infotable rows, read from manifest-bound catalog rows with
digest-verified raw-receipt cross-checks:

```json
{
 "adapter_version": "1.0.0",
 "compiled_observation_state": "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT",
 "measure": {
  "q_now": 1279,
  "q_prev": 1238,
  "unit": "shares"
 },
 "periods": {
  "current": {
   "filing": {
    "accepted_at": "2026-08-19T17:09:13Z",
    "accession": "0001904423-26-000004",
    "is_amendment": false,
    "retained_at": "2026-08-19T18:02:53.852469Z",
    "table_entry_total": 71
   },
   "generation_id": "i13fgen_9ae95a9de85cc0ed426b09cd7db443210c8cdc5d9178aaad5859c3f8a57527cd",
   "k1_reference_ids": {
    "catalog": "efr_0e60168b2aa12bede5e11a38a9ff343cb368845a4293248a3e6699f7b8f4dbca",
    "raw": "efr_f4a7cff6fff4cd6c31c2078dec2875fe71e81a876bbfcf0a6404fc376862fe02"
   },
   "pointer": {
    "current_generation_id": "i13fgen_9ae95a9de85cc0ed426b09cd7db443210c8cdc5d9178aaad5859c3f8a57527cd",
    "pointer_updated": false,
    "state": "read",
    "superseded": false
   },
   "raw_receipt": {
    "accepted_at": "2026-08-19T17:09:13Z",
    "accession": "0001904423-26-000004",
    "receipt_id": "i13fraw_5b8961b9942e2e4fd28b92051a73d503697f457b288d1f3ed3d4566c6730a0ca",
    "retained_at": "2026-08-19T18:02:53.852469Z"
   },
   "row": {
    "cusip": "00287Y109",
    "infotable_sk": 4611686018427387905,
    "investment_discretion": "SOLE",
    "row_hash": "1de9a8cbb05a28c23c5b82cdf4112776b4412dc0e8bdcb8185d5ceafad67cd68",
    "ssh_prn_amt": "1279"
   }
  },
  "previous": {
   "filing": {
    "accepted_at": "2026-08-19T17:20:59Z",
    "accession": "0001904423-26-000005",
    "is_amendment": false,
    "retained_at": "2026-08-19T18:02:31.412337Z",
    "table_entry_total": 67
   },
   "generation_id": "i13fgen_5af282ec5c2b29ed990f9dd8bd03e7e7ff88d54ebdb79467a3aec7b7451ce6d1",
   "k1_reference_ids": {
    "catalog": "efr_c4d69e15f42d576cde771a12645723b061b07ccbdbf14bb0ae560b61b5eba589",
    "raw": "efr_475da9d22aca2db7fe1d26c5f900dddf33cdc418c9c05fa474c852c5ec945a1c"
   },
   "pointer": {
    "current_generation_id": "i13fgen_5af282ec5c2b29ed990f9dd8bd03e7e7ff88d54ebdb79467a3aec7b7451ce6d1",
    "pointer_updated": false,
    "state": "read",
    "superseded": false
   },
   "raw_receipt": {
    "accepted_at": "2026-08-19T17:20:59Z",
    "accession": "0001904423-26-000005",
    "receipt_id": "i13fraw_56465d4fc5eec6e82aabc86a8884e5784414f669077933af00365f6849742bc1",
    "retained_at": "2026-08-19T18:02:31.412337Z"
   },
   "row": {
    "cusip": "00287Y109",
    "infotable_sk": 4611686018427387905,
    "investment_discretion": "SOLE",
    "row_hash": "6948742510726735b9dddaabeae571d47570c5866f69acf9aa1b699fa0f09815",
    "ssh_prn_amt": "1238"
   }
  }
 },
 "receipt_id": "i13fpilot_5c2e14896d2afcbc43585bdec2c41e64e845455e2d68e467c1ace1a12ac64b39",
 "refusal": null,
 "request": {
  "cusip": "00287Y109",
  "cutoff": "2026-08-27T09:22:23.700168Z",
  "filer_cik": "0001904423",
  "generation_id_now": null,
  "generation_id_prev": null,
  "report_period_now": "2026-06-30",
  "report_period_prev": "2026-03-31"
 },
 "schema": "institutional_intelligence.owner_read_receipt/v1",
 "security": null,
 "state": "PILOT_COMPILED"
}
```

**Negative case (real store, owner-shaped)** — run 33058222640: same
filer/periods, grammar-valid absent CUSIP 594918105 → typed
`security_not_in_filing` (no numeric zero, no compiled block):

```json
{
 "adapter_version": "1.0.0",
 "compiled_observation_state": null,
 "measure": null,
 "receipt_id": "i13fpilot_407903ca550c408f9f54ce5dc6722253fbf230b50e5887ed4f8550ca16e5d425",
 "refusal": {
  "detail": "cusip 594918105 is not present as a non-derivative row in accession 0001904423-26-000005",
  "reason": "security_not_in_filing"
 },
 "request": {
  "cusip": "594918105",
  "cutoff": "2026-08-27T09:25:20.811787Z",
  "filer_cik": "0001904423",
  "generation_id_now": null,
  "generation_id_prev": null,
  "report_period_now": "2026-06-30",
  "report_period_prev": "2026-03-31"
 },
 "schema": "institutional_intelligence.owner_read_receipt/v1",
 "security": null,
 "state": "security_not_in_filing"
}
```

**Additional real refusal** — run 33056388159: Meeder Advisory Services
(CIK 0001792167, the K2-B frozen-fixture filer) × 67066G104 refused typed
`filing_not_found` for report_period 2026-03-31: the production catalog plane
began capture 2026-08-09, so Meeder's May-accepted Q1 filing was never retained
— a correct fail-closed answer, and the receipt that redirected subject
selection to a filer whose BOTH period filings are lawfully in the store:

```json
{
 "adapter_version": "1.0.0",
 "compiled_observation_state": null,
 "measure": null,
 "receipt_id": "i13fpilot_38a1aca37af512b68232ab5f1a44468c96c6afced7ca19a0a6125a43a03e804f",
 "refusal": {
  "detail": "no 13F filing found for filer 0001792167 in report_period 2026-03-31",
  "reason": "filing_not_found"
 },
 "request": {
  "cusip": "67066G104",
  "cutoff": "2026-08-27T08:58:43.616846Z",
  "filer_cik": "0001792167",
  "generation_id_now": null,
  "generation_id_prev": null,
  "report_period_now": "2026-06-30",
  "report_period_prev": "2026-03-31"
 },
 "schema": "institutional_intelligence.owner_read_receipt/v1",
 "security": null,
 "state": "filing_not_found"
}
```

Capability state: the owner→K1→K2-B→K2-C read path is **production-proven**
(real two-period positive + two real typed refusals). K2 closure remains Sol's
call on the operation return.

