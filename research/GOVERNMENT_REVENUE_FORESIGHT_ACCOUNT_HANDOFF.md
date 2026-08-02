# Government Revenue Foresight — account handoff

Use `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` as the canonical product/architecture specification. This file is only the compact implementation checkpoint for resuming from another account.

## Current checkpoint

- Waves 1–5 are on `origin/main`: bounded USAspending award/action collection, first-seen SAM rail, bitemporal and receipt-bound ledgers, procurement workspace, premium three-pane UI, Award Tape, display-only Neural Web/Prophet context, and exact prime-award dossiers.
- Wave 5 adds a separate content-addressed `government_revenue_dossiers.v1` artifact, byte-identical canonical/public twins, stable generated-award identity, bounded company/award/action APIs with generation-bound cursors, and a progressive premium award-book/action-tape UI.
- Wave 5 also adds the strict exact-recipient graph and independent absolute-dollar coverage contracts plus fail-closed resolver helpers. It deliberately ships without fabricated mappings; no discovery ticker or fuzzy company name becomes issuer proof.
- The live and generic render workflows now carry and verify `dossiers.json`; the projection fence rejects stale, malformed, non-canonical, or mixed dossier generations.
- Wave 6 adds a separately governed official USAspending subaward evidence rail: exact prime generated-award-ID plus source-native broker-row identity, append-only version snapshots, count/detail hash receipts, activation state, ingest health, and a content-addressed canonical/public dossier twin.
- Collection is daily, keyless, and hard bounded to 160 deterministic parents, 100 rows per page, five pages per parent, 2,000 detail rows per run, and 2,000 public current identities. Parents above 500 reported subawards and parents that would breach the run cap remain explicit verified-count-only coverage; they never fabricate detail.
- First live baseline: generation `subaward-61cf42853879556a966b1589` / dossier `grsd1-77abcccf4902c93d8202b2fe`; 160 parents counted, 1,949 detail rows published, 21 complete-detail parents, 63 verified-zero parents, 66 high-count count-only parents, and 10 run-cap count-only parents, with zero collector errors.
- Public serving is precomputed-only through `/api/government-revenue/award/{award_key}/subawards` and `/api/government-revenue/subaward/{subaward_key}`. Both surfaces return parent coverage so `zero`, `not_selected`, `high_count_count_only`, and `run_cap_count_only` cannot be mistaken for complete detail.
- Wave 7 closes the subaward UI gap with a wide award-detail workspace, explicit complete/zero/count-only/not-selected coverage states, server-side subrecipient search, generation-bound cursor paging, responsive ledger rows, and a receipt drawer. Prime/action evidence remains visible if the optional subaward rail fails, and `grd1-*` is never compared with the independent `grsd1-*` generation.
- Wave 7 also adds a browser-local Research Briefcase: saved five-filter views, typed opportunity/award-change/derived-expiry alerts, a bounded local inbox, and allowlisted JSON/CSV exports. The first complete-workspace check establishes a baseline without backfill; award-change alerts remain unprimed while the official award-event rail is unavailable. There is no background delivery, account sync, email, push, or cross-device persistence claim.
- The Wave 7 checkpoint passes 338 focused Government Revenue/build/API/UI/Prophet/Neural Web and asset-contract tests plus template/site sync, JavaScript syntax, projection, and raw edge-budget guards. Its three dependency bundles use the shared `data-sync` loader contract so post-render cache stamping cannot defer them beyond the inline page bootstrap. The parity stylesheet is a canonical site-only static asset (the same repo pattern as `cycle.css`/`odds.css`); the generated HTML remains entirely owned by governed render lanes so scheduled evidence and site-wide asset sweeps cannot conflict with the feature branch.

## Truth and authority fences

- This is an original clean-room implementation over official/public data, not copied competitor code or proprietary data.
- Government Revenue remains `display/context` only. It cannot rank, size, gate, add a candidate, originate a signal, or escalate one in Prophet/Neural Web.
- Collection-scope tickers are discovery queries only. Exact reviewed UEI/CAGE/USAspending identifiers plus point-in-time ownership evidence are required for issuer attribution.
- Obligations, current award value, potential ceiling, GAAP backlog, and revenue are separate semantics.
- A reported subaward amount is self-reported subrecipient context. It is never a federal obligation/outlay, prime-award value, backlog, revenue, cash flow, or an amount to add to the prime award.
- The user-supplied competitor login must never be used or preserved.

## Resume sequence

1. Start a fresh `codex/` worktree from newly fetched `origin/main`; do not touch the shared dirty main checkout.
2. Read this file, the masterplan, repo `CLAUDE.md`, and `AGENTS.md` before editing.
3. Verify `https://mastermind-x.com/api/health`, `/government_revenue.html`, `/api/government-revenue/latest`, and one dossier API route.
4. Verify the subaward source bundle and public twins as one generation: `subaward_snapshots.parquet`, `subaward_collection_receipts.jsonl`, `subaward_projection_state.json`, `subaward_ingest_status.json`, `subaward_dossiers.json`, and `site/government-revenue-data/subaward-dossiers.json`.
5. Activate the **SAM observed-lifecycle and exact notice→award lane** only after installing a server-side `SAM_API_KEY` and completing a first active-plus-archived baseline. Label all later lifecycle history as observed after activation; never backfill historic amendments from the latest-state API.
6. Build the **DoD budget→program evidence graph** next: immutable FY budget-line receipts with request/authorization/appropriation/execution kept separate, exact PE/line/program identifiers, PDF page/hash provenance, and manually reviewed edges. Do not allocate a program line to an issuer or award by semantic similarity.
7. Then add an official USAspending **IDV→child-award identity graph** and an SBIR.gov append-only Phase I/II observation rail. Do not call an IDV relationship a vehicle seat, call an SBIR phase sequence production conversion, or build OTA progression until a source-native OTA identifier and exact lineage are available.
8. Only after prospective labels exist should calibrated bidder, award-value, revenue-timing, and beneficiary models enter shadow forward validation. They remain research context until leakage, calibration, coverage, and authority gates pass.

Every tracked change must complete the repo ship loop: focused tests, broad relevant tests, commit, PR, concluded checks, squash merge, `origin/main` evidence, deploy completion, production health, and changed-surface verification.
