---
workstream: MARKET-OS
date: 2026-08-24
session: coo-fable-b1a-20260824
status: delivered-held
---

# B1A security_state.v1 golden AAPL vertical — delivered, held for Sol

## What happened

The Chairman dispatched the prepared B1A commission directly on 2026-08-24
("K1 has been closed. We're starting next thing. Take full ownership of Market
OS B1A"), which satisfies the WS:ALPHA-INTELLIGENCE-INTEGRATION K1-boundary
hold's "separate explicit commission" requirement. All four dispatch gates were
receipt-verified: A1A canonical (#6310 merged e743db23); K1 accepted by Sol
(source b7b861a2, #6319 merged 696afbb5, closeout #6356 merged dc6a4d59);
fresh census clean (no B1/security-state/dossier lane in open PRs, branches, or
worktrees; A1B #6335 fenced and untouched; DeepVue #6359 paths disjoint); the
live AAPL event workspace fetched over HTTPS and hash-verified
(generation 6d56c84a3ac23b8954e59ee7, event evt_cik0000320193_2026q3_results,
sha256 c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db,
lifecycle complete, suitable-with-flags: 6 closed-vocabulary warnings, no
correction cycle observed yet).

The commission's binding identity rider was adjudicated BEFORE product code:
an adversarial opus analysis executed the proof against the committed
artifacts and returned BLOCKED_IDENTITY_BRIDGE at the general-renderer
altitude; the Fable adjudication passed the gate instance-scoped under the
dispatch's "exact owner-backed chain" clause. Both positions and all receipts
are preserved in DEC:MARKET-OS-B1A-IDENTITY-GATE-OWNER-BACKED-CHAIN — the
dissent is not summarized away, and its falsification cases became mandatory
compiler refusal fixtures.

Implementation shipped in one held PR (three commits + records):
contract schema (contracts/market_os/security_state.v1.schema.json, closed,
authority all-false consts), pure zero-I/O compiler (engine/security_state.py,
R1–R9 receipt chain refusal-first, six typed legs, K1 Ref/Block/Recipe
cik-native composition, frozen strongest-unresolved-fact rule, content hash,
last-good/first-failure), producer stage (scripts/build_stock_library.py,
frozen ("AAPL",) allowlist, exception-contained, one R2 fetch/night, compact
index projection), and the server-rendered Decision Spine consumer
(templates/ticker.html.j2 + scripts/build_ticker_pages.py, insert-only,
CSS gated on security_state so non-AAPL pages are byte-identical).

## verified: (each claim names its command)

- Gate receipts: `gh api graphql` PRs 6310/6319/6356 → MERGED shas above; #6335 OPEN/DRAFT.
- Live workspace: HTTPS fetch + sha256 == manifest entry (c3b9495028c0…, 22450 bytes).
- Master rows: pandas over data/reference parquets in read-only macro-main,
  byte-identical to branch HEAD (`git cat-file` comparison in the analyst run):
  SEC:US-XNAS-AAPL → ISS:US-XNAS-AAPL RESOLVED, issuer_cik 0000320193,
  evidence sec_company_tickers 2026-08-18, no migrations; CIK maps to exactly
  one issuer; issuer holds exactly one security.
- Contract tests: `python3 -m pytest tests/test_security_state_contract.py -q`
  → 42 passed (independently re-run by the orchestrator). Coverage: 14
  commission cases + 5 identity refusal fixtures (VMRK-shaped tombstone,
  GOOG-shaped multi-security CIK, migration row, workspace CIK mismatch, R9
  corroboration divergence → PARTIAL not BLOCKED) + mutation kills + K1
  receipts (validators pass; compile_recipe compiled, included=1, on subject
  cik:0000320193; negative path refuses) + content_sha256 stability.
- Live mutation kills demonstrated (introduce → red → revert → green):
  authority.can_rank leak (compiler self-refuses), hash-stability break,
  R1 tombstone check disable.
- Golden object: identity_proof PROVEN, dominant_degradation PARTIAL (honest:
  Prophet leg UNAVAILABLE + K1 v1 freshness-unknown), content_sha256
  cfecf1282d8c59f8d265529e040f9d04ed7e31caaa3b23d8ab22c88cd74c0138,
  recipe erp_5687f42d2acac8826110a5952a4d0ba0d662453577258fe8145214ab98b90d19,
  block ebl_5b86ed829a65b95f6f82bc5a856f8f74b6af2825013681b8fe2ed21b72924c97.
- Consumer regression: `python3 -m pytest tests/test_ticker_pages.py -q` →
  125 passed, 2 failed — both reproduce on unmodified HEAD (pre-existing; one
  requires sparse-omitted site/assets), re-verified by the orchestrator.
- Non-AAPL byte-identity: designer sha256 receipts (control-msft
  b0828a884dff…, control-no-spine 3d7ae0d91dbb…, before == after, empty diffs).
- Browser proof: 82 files under verify_shots/b1a/ — golden + stale +
  missing-event + corrected + no-user-context + degraded-mix +
  compiler-failure at 1440/820/390 × light/dark, 17 zh captures, hero chip
  set, 16 drilldown dialogs; zero-horizontal-overflow receipts at all widths
  (probe lifts overflow-x:clip and enumerates offending elements: 0);
  keyboard open/trap/Escape/focus-return verified.
- agentos: `python3 scripts/agentos.py validate` → 0 errors.

## do_not_redo

- Do not re-run the identity adjudication absent new artifacts — the dissent
  is preserved verbatim in the DEC; re-arguing without new evidence is churn.
- Do not widen SECURITY_STATE_TICKERS beyond ("AAPL",) — expansion is BLOCKED
  on the owner-routed ListingAlias→ListingKey renderer + K1 vocabulary triple
  (Sol repair item NO_GENERAL_NAMESPACE_RENDERER).
- Do not make the K1 four-owner golden fixture pass; do not edit
  contracts/evidence_foundation/* or lib/evidence_foundation.py.
- Do not arm merge-on-green on the B1A PR; the recorded HOLD-FOR-SOL is a
  merge barrier binding every merge path.
- Do not call this production proof: capability is BUILT_NOT_PROVEN until Sol
  merges and the nightly + render lanes produce the live object and page.
- Do not re-shoot the browser matrix; the 82-file set on the PR head is the
  design evidence of record.

## danger_areas

- build_stock_library.py security_state stage is exception-contained by
  design; preserve the last-good vs first-failure distinction (cases 12/13)
  and never let the stage lose the blob write.
- The compiler reads issuer_cik from the DECLARED master artifacts directly
  because lib.dataos.identity.SecurityIssuerRow omits the column
  (CIK_LEG_UNOWNED_ACCESS, printed in every object). If Sol lands the reader
  repair, switch to it and delete the direct read.
- change-leg staleness is a CONSUMER display policy v1 (>120d past
  fiscal_period.calendar_end while still the current alias target) — the owner
  has no freshness policy for event_workspace.v1; never present it as owner
  truth.
- R7/R8 evaluate vacuously when no workspace exists this cycle so "no current
  event" presents as change-leg absence, not a fake identity refusal — do not
  "fix" this into a refusal.
- The spine's drilldown dialogs live at the dialog layer (not inside the
  section) because .mod's backdrop-filter would become the containing block
  for position:fixed — do not "tidy" them into the section.

## next_action

Sol reviews the held PR: the identity adjudication (with dissent), the
implementation, and the browser evidence. On acceptance: merge; the nightly
daily.yml produces the live AAPL security_state block; the render lane
rebuilds site/stocks/AAPL.html; production browser proof then completes
commission §13 Step 5 and the capability advances BUILT_NOT_PROVEN →
PROVEN_LIVE. After acceptance, B1B (Terminal/Desk projection over the frozen
surface) is the next separate commission; any second issuer additionally
requires the identity-renderer repair.
