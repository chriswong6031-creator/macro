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

## 8. K2-C semantic-owner repair (2026-09-03) — repaired proof + limitation

**Operation key:** `alpha-k2c-semantic-owner-repair-20260828-sol-001`
**Commission:** `agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-31-k2c-semantic-owner-repair-commission.md`
**Controlling decisions:** `agentos/decisions/DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-STATE-2026-08-28.md`,
`agentos/decisions/DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP.md`.

### 8.1 The defect this repair killed

The §7 positive receipt above (and every other pre-repair `PILOT_COMPILED`
receipt) was reached from a single 13F row's `investment_discretion=="SOLE"`
alone, while the receipt's own `security_binding.dataos_security_id`
simultaneously stayed `null`. Two independent local-authorship defects made
that possible: `_vehicle_decision()` read a per-position AUTHORITY field
(`investment_discretion`) as vehicle STYLE, and `build_recipe()` minted
`mcx_filer_<CIK>` / `mce_filer_<CIK>_v1` / `veh_filer_<CIK>` /
`vie_filer_<CIK>_v1` as `resolution_state:"resolved"` manager-complex/vehicle
identity straight from the filer CIK. Both are now deleted. `_vehicle_decision`
no longer exists on the module at all (`tests/test_institutional_13f_adapter_
contract.py::test_investment_discretion_never_selects_vehicle_semantics`), and
no `mcx_filer_`/`mce_filer_`/`veh_filer_`/`vie_filer_` string can appear in any
receipt this module can produce
(`::test_cik_is_not_manager_complex_identity`).

### 8.2 The repaired law

`run_pilot` gained one keyword-only seam,
`owner_semantics: Mapping[str, Any] | None = None`, validated strictly and
atomically by `_validate_owner_semantics`: any single missing, empty,
wrong-typed, unresolved (the security seam's own unresolved sentinel is
never proof of resolution — the exact defect a 2026-09-03 adversarial
review found still open, R1), not a well-formed `SEC:` identity under
`lib.dataos.identity`'s own grammar, structurally partial (missing any of
the SPECIFIC fields this adapter itself reads out of an epoch -- never the
full K2-B `managerComplexEpoch`/`vehicleEpoch` schema, which the K2-B
compiler enforces once a recipe reaches it, R2), or internally
self-contradictory (`status=="unresolved"` alongside
`resolution_state=="resolved"`, R2) component invalidates the WHOLE payload
— never partial trust. The gate runs **before any recipe construction**:
when either the security seam or the manager/vehicle seam is unresolved,
`run_pilot` now returns

```json
{
 "state": "PILOT_OWNER_SEMANTICS_UNRESOLVED",
 "compiled_observation_state": null,
 "recipe": null,
 "compiled": null,
 "measure": {"state": "not_compiled", "reason": "owner_semantics_unresolved"},
 "security_binding": {
  "key_type": "cusip", "cusip": "<request cusip>",
  "dataos_security_id": null,
  "dataos_resolution": "unresolved_no_authoritative_cusip_plane"
 },
 "owner_semantics": {
  "security": {"resolved": false, "resolution": "unresolved_no_authoritative_cusip_plane"},
  "manager_vehicle": {"resolved": false, "resolution": "unresolved_no_canonical_manager_vehicle_owner"},
  "provenance": null
 }
}
```

with every other block (`schema`, `receipt_id`, `adapter_version`,
`persistence`, `owner_payloads_copied`, `authority`, `request`, `periods`
(both, including the raw `investment_discretion` value, honestly reported and
feeding no semantics), `denominators`) computed identically to the positive
path. `build_recipe` no longer accepts `investment_discretion`; it instead
requires owner-supplied `manager_complex_epoch`, `vehicle_epoch`, and
`security` mappings and carries them **verbatim** (no minting, no
`resolution_state`/`status` stamping) into the K2-B recipe. Full worked
example (from the repaired module's own test fixture world — a SOLE-discretion
two-period read, cutoff 2026-08-01, no `owner_semantics` supplied):

```json
{
 "adapter_version": "1.0.0",
 "authority": {"can_gate": false, "can_open_entry": false, "can_originate": false, "can_rank": false, "can_size": false},
 "compiled": null,
 "compiled_observation_state": null,
 "measure": {"reason": "owner_semantics_unresolved", "state": "not_compiled"},
 "owner_semantics": {
  "manager_vehicle": {"resolution": "unresolved_no_canonical_manager_vehicle_owner", "resolved": false},
  "provenance": null,
  "security": {"resolution": "unresolved_no_authoritative_cusip_plane", "resolved": false}
 },
 "periods": {
  "current": {"row": {"cusip": "037833100", "investment_discretion": "SOLE", "ssh_prn_amt": "140", "ssh_prn_type": "SH"}, "filing": {"accession": "0001792167-26-000002"}},
  "previous": {"row": {"cusip": "037833100", "investment_discretion": "SOLE", "ssh_prn_amt": "100", "ssh_prn_type": "SH"}, "filing": {"accession": "0001792167-26-000001"}}
 },
 "persistence": "none",
 "receipt_id": "i13fpilot_8b39157644b8f9693cd6e47b6bd1a26ed2134bf06edd90aa87221966b9d01978",
 "recipe": null,
 "schema": "institutional_intelligence.owner_read_receipt/v1",
 "security_binding": {"cusip": "037833100", "dataos_resolution": "unresolved_no_authoritative_cusip_plane", "dataos_security_id": null, "key_type": "cusip"},
 "state": "PILOT_OWNER_SEMANTICS_UNRESOLVED"
}
```

(elided fields match §7's shape verbatim; `periods` truncated above for
brevity — the full receipt carries every field this doc's §7 examples do).

**Correction (R4, 2026-09-03 adversarial review finding).** The paragraph
above previously claimed this was "the exact receipt the §7 filer (CIK
0001792167, CUSIP 037833100) would now produce" for §7's own positive read.
That is false: this worked example comes from the repaired module's own
SYNTHETIC test-fixture world (filer CIK 0001792167, CUSIP 037833100 — AAPL —
is that fixture's own filer/security, not any real filer's). §7's real
production positive is a DIFFERENT filer/security entirely — Custos Family
Office, LLC (CIK 0001904423) × ABBVIE INC (CUSIP 00287Y109). CIK 0001792167
appears in §7 only as the *refusal* case (Meeder Advisory Services,
`filing_not_found`, since the production catalog plane began capture
2026-08-09 and never retained Meeder's earlier Q1 filing) — never as §7's
positive. This session has no production store credentials/network access,
so §7's real production positive has NOT been re-read post-repair; whether
it now yields `PILOT_OWNER_SEMANTICS_UNRESOLVED` (the expected outcome,
since no repo owner supplies `owner_semantics` for it) remains unverified,
not merely unstated.

### 8.3 Owner-primitive limitation (per the commission's blocker contract)

No repository code — searched across `lib/`, `engine/`, `scripts/`,
`collectors/`, `app/` for any construction of a recipe's
`manager_complex_epochs`/`vehicle_epochs` list — produces a lawful
`owner_semantics` payload today; the adapter module itself is the only
producer, and it now *requires* the seam rather than authoring it
(`tests/test_institutional_13f_adapter_contract.py::
test_no_repo_producer_supplies_owner_manager_vehicle_epochs`). No
owner-native CUSIP→Data OS `SEC:` resolution surface exists either.

**Correction (R5a, 2026-09-03 adversarial review finding).** This
subsection previously called that fact "consistent with"
`DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP`. It is not. That DEC's
`answer`/`rationale` explicitly chose to carry the Data OS axis "as a typed
unresolved field" and its supersession note frames `dataos_resolution`
staying unresolved as the ONGOING lawful state until a future Data OS
commission fills it — i.e. the DEC deliberately held the Data OS axis
non-load-bearing (`"the Data OS gap is carried as typed unresolved rather
than being load-bearing"`, its own §"alternatives" reasoning). This §8
repair's R1 fix makes that axis strictly load-bearing instead: a positive
is now unreachable whenever `dataos_resolution` is the unresolved sentinel,
full stop. That is an INVERSION of the DEC's stance, taken under this
later, merged commission's authority (the K2-C semantic-owner repair
commission and its governing `DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-STATE-
2026-08-28`) — not a continuation or an application of the earlier DEC.
Minting a formal supersession record for
`DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP` is Sol's call, not this
worker packet's; this correction only stops the doc from misdescribing the
relationship as agreement. Consequently:

- `missing_security_owner_primitive`: no repo owner resolves a 13F row's
  `cusip` to a Data OS `SEC:` identity (`lib/dataos/identity.py` +
  `data/reference/security_master.parquet` carry no `cusip` vendor-alias
  space per `DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP`'s evidence).
- `missing_manager_vehicle_owner_primitive`: no repo owner supplies a
  resolved K2-B `managerComplexEpoch`/`vehicleEpoch` pair keyed off a 13F
  filer/vehicle; K2-B (`lib/institutional_intelligence.py`) is a pure
  compiler over caller-supplied epochs, never their producer.
- The CLI (`main`/`_build_arg_parser`) carries **no** `owner_semantics` flag
  by design (frozen spec point 8): a human-injected override would be
  precisely the back door this repair exists to close. Its real-world
  outcome on any input is therefore always the
  `PILOT_OWNER_SEMANTICS_UNRESOLVED` terminal receipt shown in §8.2.
- The ONE test-only STRUCTURAL fixture
  (`tests/test_institutional_13f_adapter_contract.py::
  _structural_owner_semantics`) proves the gate machinery correctly routes a
  fully owner-resolved binding into the K2-B compiler and that compiled
  output stays uninjectable — it is explicitly commented as NOT evidence any
  production owner can supply these values, and is never presented as a
  production positive.

**Result:** this repair closes the false-positive bug entirely (no
`owner_semantics` producer exists → every current real-world read is now
`PILOT_OWNER_SEMANTICS_UNRESOLVED`, never a laundered positive), but it
cannot itself deliver a real owner-backed semantic positive — that requires a
separate Data OS CUSIP-identity commission and a separate institutional/K2-B
manager-vehicle-epoch commission, per the commission's owner-primitive-blocker
contract. K2-C therefore remains `PARTIAL / NOT SOL-ACCEPTED` for a real
positive, while the false-positive defect itself is closed.

### 8.4 Adversarial review repair (2026-09-03) — blocker + three MAJOR findings

An independent adversarial review of the §8 repair (head `2774c3f481be`)
found the false-positive claim above was itself still false, plus three
MAJOR findings. All five are fixed in
`lib/institutional_13f_adapter.py`/`tests/test_institutional_13f_adapter_
contract.py`, inside the same frozen four-path ceiling and without any new
owner primitive:

- **R1 (BLOCKER).** `_validate_owner_semantics` checked BOTH K2-B epochs for
  `resolution_state=="resolved"` but checked the security seam only for
  non-emptiness, so `dataos_resolution=="unresolved_no_authoritative_cusip_
  plane"` (the schema's own UNRESOLVED sentinel) was accepted as proof of
  resolution and still reached `state=PILOT_COMPILED` — verbatim the
  commission's `do_not_redo` clause "do not call an unresolved security
  binding positive." Repaired: the sentinel is now refused outright, and
  `dataos_security_id` must additionally parse as a well-formed `SEC:`
  security identity under `lib.dataos.identity.parse_id` (asking the owner
  whether the string is well-formed under its OWN grammar — never
  resolving, minting, or mapping one). Falsifier:
  `test_unresolved_security_sentinel_cannot_prove_a_positive`.
- **R2 (MAJOR — atomicity).** The validator inspected only each epoch's
  `resolution_state`, so a structurally partial epoch was accepted and then
  escaped `run_pilot` as an uncaught `InstitutionalIntelligenceError` out of
  `build_recipe`/`validate_recipe`. Repaired: presence and non-empty string
  type of exactly the keys this adapter itself consumes
  (`_MANAGER_COMPLEX_EPOCH_REQUIRED_KEYS`, `_VEHICLE_EPOCH_REQUIRED_KEYS`)
  is now checked, plus a `status=="unresolved"`-with-`resolution_
  state=="resolved"` self-contradiction refusal. Falsifier:
  `test_partial_owner_epoch_is_refused_not_raised`.
- **R3 (MAJOR — provenance survival).** The `owner_semantics` receipt block
  was emitted ONLY on the unresolved path (where `provenance` is always
  `None`); the positive path emitted no such block, discarding the
  validated `provenance.owner`/`reference_id` once a recipe was reached —
  two receipts proven by two DIFFERENT owners were byte-identical and
  shared one `receipt_id`. Repaired: the block is now emitted on the
  positive path too, carrying the owner's `provenance` verbatim. Falsifier:
  `test_owner_provenance_is_recorded_and_distinguishes_receipts`.
- **R4 (MAJOR — wrong exemplar).** §8.2's worked example was mislabelled as
  what "the §7 filer (CIK 0001792167, CUSIP 037833100)" would now produce;
  corrected in place above (§8.2) — that pairing is the repaired module's
  own SYNTHETIC test-fixture world, not §7's real production positive
  (Custos Family Office, CIK 0001904423 × ABBVIE, CUSIP 00287Y109). §7's
  real positive has not been re-read post-repair.
- **R5 (minor — two wording corrections).** (a) §8.3 previously claimed
  this repair is "consistent with" `DEC-K2C-SECURITY-BINDING-IS-OWNER-
  NATIVE-CUSIP`; corrected below (§8.3) — that DEC explicitly held the Data
  OS axis "carried as typed unresolved rather than being load-bearing,"
  while this repair makes it strictly load-bearing (no positive is
  reachable without it). That is an INVERSION of the DEC's stance under
  this later, merged commission's authority, not a continuation of it;
  minting a formal supersession record is Sol's call, not this repair's.
  (b) `tests/test_institutional_13f_adapter_contract.py::
  test_no_repo_producer_supplies_owner_manager_vehicle_epochs`'s docstring
  said it "Greps the repository"; corrected in place — it greps exactly
  five directories for one syntactic dict-literal-key form, with named
  blind spots (non-literal construction, non-`.py` files, directories
  outside the five searched).

