# D4 — Company Financial Truth Bridge (IRDM only) · frozen spec

**Wave:** D4 (Sol-authorized 2026-08-20 after D3 acceptance). D5+ NOT authorized.
**Baseline:** origin/main `1d70b40c63e35228dfb561cc9d07233ca8cedd9f` @ 2026-08-20T17:43:27Z.
**Charter:** put the reviewed P00032 government fact beside the canonical
company-financial owner's latest usable IRDM truth so a user can separately
answer: (1) what did the government record say, (2) what does Iridium
currently report through Mastermind's canonical owner, (3) is there a
receipt-bound denominator making those comparable. If (3) is not provably
yes, the product says `not_comparable` and materiality/ratio stays null.

## §0 Acceptance gates (not done unless)

1. **P00032 is byte/semantic stable.** The government block renders ONLY
   facts read from the already-published GovRev workspace artifact:
   `HC101319C0006 / P00032`, obligation `$18,416,666.66`, effective/action
   `2026-05-12`, first known to Mastermind `2026-08-12`, late discovery,
   official receipt link. Nothing in the company rail may retime, rename, or
   reinterpret them; company-packet variation must not change one byte of the
   government block.
2. **Obligation is never labeled** revenue, backlog, bookings, sales, cash,
   or free cash flow — in EN or ZH, in any state.
3. **Comparison defaults closed.** `comparison_state = not_comparable`,
   denominator = null, materiality_ratio = null. The ONLY path to a ratio is
   an owner packet asserting an issuer-attributed denominator with
   receipt-bound source, entity scope, metric semantic, period, unit/currency,
   known/restatement clock, and a basis compatible with a federal obligation —
   which `company_intelligence_context.v1` structurally never provides.
   Therefore this wave renders **no ratio on any input** and proves it
   hostile: a packet with revenue facts present still yields `not_comparable`
   + null ratio; a backlog-flavored commentary string still creates no
   attribution.
4. **Company rail shows only owner-asserted facts, with the owner's clocks.**
   Source = `GET /api/company-intelligence/{ticker}` (same-origin), schema
   `company_intelligence_context.v1`, already consumed per-ticker by
   `site/assets/js/company-intelligence-dossier.js` (precedent). Displayed:
   fiscal period + call_date, earnings_history/transcript-lineage metrics
   (e.g. revenue growth %), up to 2+2 highlights whose `field_lineage` is
   `earnings_history`, `claim_citations_pending` state as an honest
   wording-verification chip, `generated_at` as the packet clock, source
   statuses. **Excluded:** any field whose lineage is `score_overlay`
   (keeps D4 outside the E2 overlay ban), estimates (none exist → nothing
   rendered, never zero), prices.
5. **Fail-closed unavailability.** Fetch error, HTTP ≠ 200, `available:false`,
   or `schema !== 'company_intelligence_context.v1'` → explicit
   "Company packet unavailable" (公司数据包不可用) state — never zero, never
   an empty card, never a spinner that lives forever. Unknown extra fields are
   ignored; missing optional fields render as absent, not as failure.
6. **Restatement law.** A newer owner packet (later `generated_at` /
   different latest_event) advances ONLY the company rail on next load. The
   government block's source is the immutable GovRev artifact; test with two
   packet fixtures that government bytes are identical.
7. **No new truth store.** Zero writes under `data/government_revenue/` or
   anywhere else; zero engine/producer changes; no Earnings Wire HTML
   parsing (`irdm-2026q1-call-record.html` is never fetched or read); the
   bridge module's only network read is `/api/company-intelligence/`.
8. **No browser-side division or numeric inference.** No arithmetic on the
   obligation or any company figure; owner prose (e.g. "$46 million") is
   displayed verbatim as commentary. LLM-free surface; no model calls.
9. **IRDM only.** The bridge renders for ticker `IRDM` alone (frozen golden
   constant). Other company dossiers are byte-unchanged. No 31-issuer
   cockpit.
10. **Page-weight law.** `RAW_HTML_BUDGET_BYTES` stays `303_104` — D4 may
    NOT raise it. Bridge logic lives in `templates/government-revenue-dossiers.js`
    (paired plain-copy asset, outside the fence); the inline template gains
    only a small host section + minimal CSS. Local bake
    (`scripts.build_government_revenue._write_site_projection`) proves the
    baked page under budget before merge. If it cannot fit, STOP and return
    to Sol.
11. **Bilingual + integrated.** EN/ZH labels (ZH uses 披露 never 申报; no
    证伪/refuted vocabulary); owner prose stays EN (no invented
    translations). Four-block structure (GOVERNMENT FACT / COMPANY TRUTH /
    COMPARISON / RESEARCH QUESTION) rendered as a proper inspector section
    matching the existing dossier idiom (target composition:
    `research/defense_intelligence/evidence/compositions/d2-company-dossier-irdm.html`),
    desktop/tablet/mobile, no overflow.
12. **Display/context authority only.** No rank/score/gate/size/entry/
    execution; `is_neuralweb_trade_candidate` untouched.

## §1 Owner preflight result (recorded 2026-08-20)

Classification: **A on the v1 context plane, with the richer packet absent.**

- `event_workspace.v1`: AAPL-only by construction
  (`scripts/refresh_event_workspaces.py` hardcodes `apple_registry()` /
  `ticker="AAPL"` / `FLAGSHIP_EVENT_ID`; only issuer builder is
  `apple_issuer()`; zero IRDM in that plane). **No IRDM event workspace
  exists** — D4 does not create one and does not promote the Earnings Wire
  source into one (case B is not made case A).
- `company_intelligence_context.v1`: the canonical owner's closed per-ticker
  read API **serves IRDM live** — probe 2026-08-20:
  `GET https://www.mastermind-x.com/api/company-intelligence/IRDM` → 200,
  `available:true`, `generated_at 2026-08-20T06:52:58Z`, `status partial`,
  `latest_event cie_77ff210df9c064c3b2fe4aa1` (FY2026 Q1, call 2026-04-23),
  `claim_citations_pending:true`, `authority context_only`,
  `field_lineage` per field, `sources[]` with per-kind status/citation
  precision. Anonymous 200 (public bounded wire).
- Denominator: the packet asserts growth percentages and prose highlights
  only — no issuer-attributed absolute denominator, no backlog figure, no
  P00032 attribution (its government commentary names SDA; P00032 is DISA).
  → comparison stays `not_comparable`; candidate `materiality` already
  records `exact_issuer_attributed_denominator_not_available`.
- Auto-upgrade path (recorded, NOT built): if the earnings owner later
  publishes an IRDM `event_workspace.v1` generation, the
  `event_workspaces/manifest.json` aliases map gains an IRDM key; a later
  authorized wave may upgrade the company rail to that packet. D4 freezes on
  the v1 context API.

## §2 Data sources (all read-only, all pre-existing)

- Government block: the P00032 event object from the already-loaded GovRev
  workspace (match `award.piid === 'HC101319C0006'` + modification `P00032`
  within events carrying ticker IRDM; fields: amount, effective_at,
  known_at/first_seen_at, is_late_discovery, official source URL). Reuses
  D3's clock vocabulary (Took effect / First known to Mastermind).
- Comparison block: the IRDM candidate's `materiality` object from the
  already-published candidate artifacts (`comparison_state`, `reason_code`,
  `issuer_attributed_denominator`, `materiality_ratio`) — producer-asserted;
  UI performs no computation. Candidate missing → render the default
  not-comparable copy (fail closed).
- Company block: `GET /api/company-intelligence/IRDM` at view time.
- Research question block: static bilingual copy — watch the next company
  print / owner packet for a lawful transmission bridge; windows, not
  certainties.

## §3 UI placement

New inspector section for `r.kind === 'company' && ticker === 'IRDM'`,
rendered by a new factory `createGovernmentRevenueCompanyBridge` in
`templates/government-revenue-dossiers.js` (idiom: identical wiring shape to
`createGovernmentRevenueIdentityAtlas` — host div in the inline template,
`loadCompany(ticker)` / `invalidate()` lifecycle). Section order: after
Identity Atlas + Award history, before Cross-links. Four sub-blocks:

1. **GOVERNMENT FACT / 政府事实** — P00032 · $18.4167M obligation · Took
   effect May 12, 2026 · First known Aug 12, 2026 · Late discovery ·
   official receipt link. Label vocabulary: "obligation / 拨款义务" only.
2. **COMPANY TRUTH / 公司披露** — owner packet facts per §0 gate 4, or the
   explicit unavailable state.
3. **COMPARISON / 可比性** — "Not comparable — no issuer-attributed
   denominator has been asserted" (不可比 — 尚无发行人归属的分母) from the
   candidate materiality block; ratio row absent (not "0", not "—" as a
   value claim).
4. **RESEARCH QUESTION / 研究问题** — static watch copy.

## §4 Tests (new suite `tests/test_government_revenue_company_bridge.py`)

Node UI-harness driven (extend `tests/test_government_revenue_ui.py`
`_run_runtime` with a company-intelligence fetch stub + load the shipped
`government-revenue-dossiers.js` against committed artifacts, per the D2
harness precedent). Hostile families:

- T1 government stability: bridge on/off, packet present/absent/mutated →
  government block innerHTML identical; P00032 values exact.
- T2 label law: rendered section text never contains
  revenue/backlog/bookings/cash/FCF adjacent to the obligation amount; EN+ZH.
- T3 revenue-no-denominator: packet with `metrics.revenue_growth_pct` and
  revenue-prose highlights → comparison still not_comparable, no ratio node.
- T4 backlog-no-attribution: packet highlight containing the word "backlog"
  → displayed verbatim as commentary, zero attribution copy, comparison
  unchanged.
- T5 unavailable typing: fetch 404 / network error / `available:false` /
  wrong schema → "Company packet unavailable" state; no zeros, no spinner.
- T6 estimates null: no estimate vocabulary anywhere in the section.
- T7 restatement: packet A then packet B (later generated_at) → company
  block updates, government block bytes identical.
- T8 no-wire-parsing + single-endpoint: the bridge module's fetch targets
  are exactly `/api/company-intelligence/…`; `irdm-2026q1-call-record` never
  requested (harness records all fetch URLs).
- T9 IRDM-only: a non-IRDM company inspector renders no bridge section.
- T10 lineage filter: a field whose lineage is `score_overlay` is not
  rendered even when present.

CI wiring: add the suite to a `run:` step in `.github/ci/legacy-jobs.yml`
AND `.github/workflows/ci.yml` paths (contract-delta law). Template edits
require the byte-matching `site/` twin in the same PR
(`python -m scripts.check_template_site_sync --fix`).

## §5 Non-changes

No engine/producer edits; no schema edits; no new artifacts; no Earnings
Wire parser; no estimates plane; no event_workspace producer for IRDM; no
change to candidate materiality values; no fence raise; no Prophet/Neural
Web/rank authority; no D5.
