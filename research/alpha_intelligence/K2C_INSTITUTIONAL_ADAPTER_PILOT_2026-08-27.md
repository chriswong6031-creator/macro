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
`row.cusip == security.cusip == subject_id` (grammar `cusip:<CUSIP>`); both
periods' refs PIT-available at the compile cutoff via the existing K1
availability machinery (`max(accepted_at, retained_at)`; catalog
`published_at`); `measure.kind == "reported_share_change"` with numeric
`q_prev`/`q_now` or a typed unavailable measure. The compiler treats a valid
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
   id, naming inputs, exact generations (id + manifest digest), effective
   filings/accessions, row identities (`infotable_sk`, `row_hash`), K1 reference
   ids, q values + denominator receipts, typed states, embedded compiled K2-B
   receipt. Deterministic on identical owner inputs.
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

## 7. Proof receipts

*(appended after execution — empty at design freeze)*
