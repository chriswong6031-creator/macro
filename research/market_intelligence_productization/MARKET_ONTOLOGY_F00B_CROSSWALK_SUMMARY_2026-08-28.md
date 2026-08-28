# Market Ontology F00B — Current Capability Crosswalk (2026-08-28)

Operation: `marketontology-f00b-current-owner-crosswalk-20260828-sol-001`
Parent program: `marketontology-complete-parity-fanout-20260826-sol-001` (F00, `WS:MARKET-OS`)
Linear projection: MAS-170 (UNVERIFIED this session — Linear MCP unauthenticated; intent taken from the Sol carrier text on C0BSBM78V1N/1787906810.553069)
Base: Macro main `5542999e890f4719d18b5a0c764b418cdd4201ce` · Skillpack `Mastermind@e023f9b4df388814286d42462af0e86a64eea563` v1.0.1

## What this is

One current, executable parity crosswalk over the frozen scope: the 88-row
authenticated adoption ledger (`MARKET_ONTOLOGY_COMPLETE_PARITY_ADOPTION_LEDGER_2026-08-26.csv`)
plus the 42-row current-public delta ledger
(`MARKET_ONTOLOGY_CURRENT_PUBLIC_DELTA_LEDGER_2026-08-26.csv`), overlaying each row
with its **current** canonical owner, proven capability state, exact evidence,
missing journey, source/rights dependency, authority ceiling, active sibling
carrier, and recommended next disposition. This is an OVERLAY artifact — the
historical baseline ledgers are not rewritten.

Row data: `MARKET_ONTOLOGY_F00B_CURRENT_CAPABILITY_CROSSWALK_2026-08-28.csv` (130 rows,
zero UNKNOWN/UNOWNED, zero empty cells outside the optional notes column; 27
rows carry an explicit UNVERIFIED flag somewhere in the row rather than a
silent claim).

Capability states use the house vocabulary at PROVEN tier: docs/spec/merged infra
are not production proof; a sibling program counts only at its proven capability tier.

## Completion claim and #6611 reconciliation

**Claim: `COARSE_CROSSWALK_COMPLETE` — nothing more.** Per the merged granular
full-parity ratchet (#6611, merge `532fe442`;
DEC:MARKET-ONTOLOGY-GRANULAR-FULL-PARITY-BEYOND-PARITY-RATCHET): the 88 + delta
rows are coarse anchors, not proof of granular absorption; this artifact is the
coarse F00C owner-map input and never `COVERAGE_COMPLETE` or `PARITY_COMPLETE`.
Priority controls sequencing, never inclusion — no disposition in this crosswalk
(including `RESEARCH_CONTEXT_ONLY`) is an exclusion, and `REJECTED_BY_DESIGN`
candidates reject a mechanism only, never the lawful underlying job, which
requires a stronger equivalent or adjudicated impossibility before closure.
F00A (exact P1 admission), F00C (zero-loss granular reconciliation), and F00D
(beyond-parity synthesis) remain separate gates outside this child.

**Owner resolution law (Sol repair 2026-08-28):** every row's `current_owner` is
a lawful responsibility owner (workstream/lane + canonical owner route). Absence
of an implementation is recorded only in `capability_state`/`evidence`/`notes`,
never in the owner field. Verified (second audit + systematic pass): all 130
owner cells carry an explicit `WS:`/lane responsibility binding, and zero owner
cells carry none/unassigned/unresolved/unowned language.

## Counts

Capability state (130 rows, post-audit): **NOT_BUILT 59 · PARTIAL 49 · SPEC_ONLY 11 ·
BUILT_NOT_PROVEN 6 · PROVEN_LIVE 5** (BROKEN 0, DARK_OR_DISCONNECTED 0,
REJECTED_BY_DESIGN 0 — rejection candidates are recorded in notes pending Sol rulings).

Disposition: **BUILD_NEW 50 · UPGRADE_EXISTING 42 · PROJECTION_OVER_EXISTING 20 ·
RESEARCH_CONTEXT_ONLY 15 · PROVEN_EXISTING 3** (REJECTED_BY_DESIGN 0 as final
disposition; candidates flagged in notes: MO-PAID-048/050 absent a license,
MO-DELTA-040, and the authority-tier semantics of MO-PAID-024/MO-DELTA-006).

Per-lane state matrix:

| Lane | rows | PROVEN_LIVE | BUILT_NOT_PROVEN | PARTIAL | SPEC_ONLY | NOT_BUILT |
|---|---|---|---|---|---|---|
| F01 macro/markets | 12 | 1 | 0 | 7 | 0 | 4 |
| F02 policy/geo | 10 | 0 | 0 | 4 | 1 | 5 |
| F03 options | 16 | 2 | 4 | 6 | 2 | 2 |
| F04 ontology/transmission | 9 | 0 | 0 | 5 | 1 | 3 |
| F05 event/impact | 4 | 0 | 0 | 2 | 1 | 1 |
| F06 security research | 3 | 0 | 0 | 2 | 0 | 1 |
| F07 valuation/scenario | 5 | 0 | 0 | 0 | 0 | 5 |
| F08 portfolio/alerts | 7 | 0 | 0 | 2 | 0 | 5 |
| F09 capital/materials | 29 | 0 | 2 | 10 | 0 | 17 |
| F10 quant/analogs | 5 | 0 | 0 | 2 | 0 | 3 |
| F11 research workspace | 6 | 0 | 0 | 2 | 4 | 0 |
| F12 team/API/platform | 18 | 2 | 0 | 2 | 2 | 12 |
| F13 ops/learning | 6 | 0 | 0 | 5 | 0 | 1 |

## Biggest already-existing capabilities (do NOT rebuild)

1. **Options context estate (F03)** — the deepest single-lane substrate: EOD chain
   workspace (`build_options_command` → `templates/options.html.j2`, PROVEN_LIVE),
   expected move (PROVEN_LIVE), OI concentration + dealer-gamma display estate
   (display-tier, DNR-bounded), vol/skew/term surfaces (PARTIAL), ThetaData T1 spine
   (PROVEN_LIVE per AD-1T1), measured trade+NBBO microstructure (BUILT_NOT_PROVEN on
   HOLD carriers #6585/#6576). The #6604 C0 masterplan owns consolidation.
2. **Mastermind chat (F11)** — `engine/neuralweb/brain_gateway.py` + `/api/brain/*`
   is production-live as a general Live-Market-Packet assistant (audit receipts:
   `/api/brain/me` 200, grounded `/api/brain/chat` reply); the Workspace-Chat
   *capability* is PARTIAL — it needs binding to future research objects, and
   Workspace Chat is among the held-back surfaces per
   DEC:MARKET-INTEL-PRODUCTIZATION-NO-NEW-WORKSTREAM — but never a new assistant.
3. **Billing/entitlement/auth (F12)** — full Stripe lifecycle (`app/billing.py`) and
   entitlement display are PROVEN_LIVE single-user; Supabase auth + account prefs PARTIAL.
4. **Portfolio holdings truth (F08)** — A1A/A1B accepted in production
   (DEC:MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION); every portfolio row is a projection
   over this proven substrate, not a new store.
5. **Macro monitoring surfaces (F01)** — regime engine (nightly), bonds/curve hub,
   FX hub, commodity dashboard, AI Daily Brief (PROVEN_LIVE): parity work is depth
   and governance projection, not construction.
6. **Event spine (F05)** — nightly chronicle event spine + state_log actively
   producing on main; MO-DELTA-001 "Market Feed" is an alias of this substrate.
7. **Capital-structure/special-situations engines (F09)** — 19 `engine/capital_structure/*`
   modules, special-situations classifiers, beneficial ownership, commodity context —
   real display-tier organs lacking only product assembly.
8. **Eval OS measurement law (F13)** — explanation memory, trial ledger, Calibration
   Lab score signal/desk theses today; institutional memory for user claims is a
   projection over this law.

## Biggest true gaps (nothing to upgrade — genuinely missing)

1. **F07 valuation/scenario: 5/5 NOT_BUILT** — no valuation model, no scenario
   engine, no consensus-estimate source anywhere in the repo (verified negative);
   FIF substrate is golden-fixture AAPL-only, production issuer service NOT_BUILT.
2. **F12 tenancy: 12/18 NOT_BUILT** — no team/tenant/seat/role/workspace concept,
   no public API, no API keys, no outbound webhooks in either repo.
3. **F09 capital-markets workbenches** — all named workbenches/tapes/monitors
   (Capital Need, Windows, Transaction Tape, Issuer, Bridge, M&A, ECM, DCM,
   Precedents) unbuilt as products; Transaction-Tape-class rows carry a hard
   **licensed deal-flow data** rights gate with no contract in the repo.
4. **F11 research objects** — no user-facing Thesis/Notes/RMS object model exists;
   everything hinges on one Thesis-identity build (MO-PAID-046/047/053), over which
   RMS and the amendment lifecycle are projections.
5. **Geospatial tracking (F02) + chokepoints (F09)** — military/maritime/satellite
   and chokepoint monitoring are NOT_BUILT **and rights-gated** (D0R registry:
   imagery/logistics REJECT unless licensed); Chairman/commercial gates precede any build.
6. **K5-gated opportunity surfaces (F04/F05)** — Opportunity Map/Radar projections,
   arbitrage scanner, ranked implications all wait on the K2-C→K3-D→K5 acceptance
   chain; none of the competitor's calibrated authority fields
   (direction/confidence/priced%) are inheritable absent Mastermind's own
   calibrated promotion proof (Sol amendment honored across rows).

## Sol amendment reconciliation (1787907339.753029)

- **Persistent analysis lifecycle**: covered *in parts* by existing organs —
  `engine/falsifier_tripwires.py` (ARMED/FIRED/EXPIRED state machine + latch),
  `engine/macro_thesis.py` (append-only revision lineage, operator-diary tier),
  nightly forward-log grading. The genuine gap is the final step only: *reopening a
  saved user analysis with the named change applied*. Scoped INSIDE MO-PAID-046/047/053
  as a projection composing those two existing patterns over the future user Thesis
  object. **No new row minted; no second lifecycle.**
- **RMS decision workflow depth**: reconciled as workflow-state fields/projections
  over the same Thesis/Condition/Monitor identities (F11's own object law) plus the
  F12 tenant boundary for Coverage Universe/assigned-analyst; Catalyst Workflow and
  Team Workspace are typed-Condition/shared-object projections. **No new engines.
  Open dependency: the F12 tenant/access-model freeze (named unresolved by F11 itself).**
- **Competitor Opportunity/impact surface**: preserved as context evidence only;
  authority ceilings on MO-PAID-024/042 and MO-DELTA-005/006 explicitly refuse the
  advertised direction/confidence/expected-impact/priced% semantics absent
  calibrated promotion.

## Active sibling collisions (crosswalk, do not duplicate)

| Carrier | State | Owns |
|---|---|---|
| #6604 Options Intelligence C0 masterplan | OPEN HOLD-FOR-SOL | F03 consolidation; Structure Builder/catalyst-workflow commissioning |
| #6585 / #6576 OA1T ThetaData microstructure | OPEN HOLD-FOR-SOL | F03 flow/trade-interpretation substrate (BUILT_NOT_PROVEN) |
| #6529 Stock Identity W3-final | OPEN (unclaimed) | F10 analog-lab substrate (episodes W1/W2 done, W3+ unbuilt) |
| #6522 GMI Theme Graph finish-and-fold | OPEN | F04 theme/transmission substrate (D2C→W3C sequence) |
| #6582 / #6598 Eval OS freeze + E1 qledger | OPEN | F10/F13 measurement law |
| #6528 Market Memory recharter | OPEN DRAFT | F13-adjacent memory governance |
| #6514 K3-D economic propagation | OPEN HOLD-FOR-SOL | F04/F05 causal layer; blocks K5 |
| K2-C #6533 | MERGED, NOT Sol-accepted | F09 institutional ownership; post-merge repair is an explicit adjudication point |
| #6526 A1B badge refresh | OPEN | F08 portfolio surface nit |
| #6596 CRG R0 | OPEN | F12 cross-repo contract governance (no new Contract Bus authorized) |
| #6543 Rates/Inflation Command F0 | OPEN awaiting_ci | F01 rates axis |
| LER program (#6599) | MERGED/FROZEN | The existing Radar MO-PAID-042 projects over — never a duplicate lifecycle |

## Preservation findings — P-001..P-006 (consumed at ACCEPTED preservation-evidence tier)

Source: the final preservation audit, now MERGED/ACCEPTED via PR #6610 (merge
`471597e00baf` from source head `a7ff402a`). It is consumed here at its
accepted **preservation-evidence** tier: the classifications below map
P-001..P-006 onto EXISTING 88+delta rows/families/owners — they mint no new
parity rows. Preserved invariants from the accepted source:
`SAFE_TO_LOSE_MARKETONTOLOGY_ACCESS: NO`; the exact-byte P1 corpus remains an
`OPEN_IMPORT_GATE`; P-003/P-005 persistence is UNPROVEN (no thesis/issuer/
monitor was created); P-006 is route/schema evidence only; and nothing inherits
competitor direction/confidence/priced% authority semantics absent calibrated
promotion.

- **P-001 Ticker Impact Ledger** (event → typed AssumptionChange → durable
  per-ticker log): lane F06/F07; owner WS:MARKET-OS (F06) + FIF (F07); proposed
  state NOT_BUILT (entity-level bridge absent; adjacent rows MO-PAID-021/022);
  proposed disposition UPGRADE_EXISTING over MO-PAID-021/022 — not a new
  financial-truth store; ceiling research_display_only.
- **P-002 Composed ticker-options "current read"** (composition law over live
  primitives): lane F03; owner WS:MARKET-OS (F03) + Options C0 (#6604) +
  WS:ADVANCED-DATA-OPTIONS; proposed state PARTIAL (primitives live/display-tier,
  composition absent); disposition UPGRADE_EXISTING; ceiling research/decision-
  support context until its own source/timing/evaluation law is accepted.
- **P-003 Catalyst-to-options state machine** (catalyst→exposure→structure→saved
  thesis→change monitor; persistence unproven): lanes F03/F11/F08; owner
  WS:MARKET-OS (F03 lane) + future F11 Thesis object; proposed state SPEC_ONLY;
  disposition BUILD_NEW folded into MO-PAID-070/MO-DELTA-033; ceiling
  research_expression_only; persistence must be tested separately.
- **P-004 Research-terminal continuation graph** (event-to-next-research-surface
  transition is the preservation unit): lane F04 (cross-lane accountant); owner
  WS:MARKET-OS (F04); proposed state NOT_BUILT (transition unit); disposition
  PROJECTION_OVER_EXISTING; ceiling research_priority_only; destination
  persistence unproven.
- **P-005 Capital-markets issuer state cycle** (one returning issuer analysis
  over the F09 workbenches): lane F09; owner WS:MARKET-OS (F09) +
  capital-markets owners; proposed state NOT_BUILT (cycle; constituent engines
  PARTIAL); disposition BUILD_NEW as depth reconciliation — no parallel
  capital-structure truth plane; ceiling context/human_research_only.
- **P-006 Indexed public route families as preservation evidence** (public
  record schema + route-family shape): lane F13/F00 evidence plane; owner F00
  program control + K1 Evidence Foundation; an evidence-retention obligation,
  not a capability row; disposition RESEARCH_CONTEXT_ONLY; no bulk copying of
  event prose/data is licensed.

#6610 landed (merge `471597e00baf`); the mapping above is its accepted-tier
consumption. F00's required next action from the accepted audit stands: recover
and hash-verify the original public-P1 V5 CSV/JSON before any future
`SAFE_TO_LOSE_MARKETONTOLOGY_ACCESS: YES` conclusion.

## UNVERIFIED register (bounded, explicit)

27 rows carry inline UNVERIFIED flags; the load-bearing ones: MAS-170 Linear intent
(unauthenticated MCP); options producer wiring for vol/term/expected-move
(ThetaData vs legacy polygon_gex path); live-artifact freshness receipts for
display surfaces (sparse tree omits site/ and data/ by design); existence of any
licensed deal-flow/rating/maritime/sovereign data contract *outside* the repo
(census can only prove "no reference found in code/docs"); Supabase-console-level
account deletion; non-US legislative source coverage; commodity-family coverage
beyond oil; charting-app subdirectories beyond api/terminal/supabase.

## Proposed next fanout set (for Sol; smallest set that unblocks the most rows)

1. **F11 Thesis-object vertical** (MO-PAID-046→047→053 + amendment lifecycle):
   one bounded build unlocking 6 F11 rows + MO-DELTA-007 projection + RMS depth.
2. **F12 tenancy foundation** (team/tenant/roles over existing Supabase+Stripe):
   prerequisite for 12 NOT_BUILT F12 rows and F11 Coverage Universe.
3. **F07 valuation source decision** (Sol/Chairman): consensus-estimates
   source/rights ruling before any valuation build — 5/5 rows blocked on it.
4. **F09 rights docket** (Sol/Chairman): licensed deal-flow, rating-actions,
   maritime/chokepoint, sovereign-ownership — one consolidated rights adjudication
   gates ~10 rows across F09/F02.
5. **F01/F13 cheap projections**: premarket AM Edition, reference
   indicators/glossary over site_semantics, notification-preferences wiring —
   low-risk UPGRADE_EXISTING / PROJECTION_OVER_EXISTING batch.
6. **Existing-carrier accelerations** (no new programs): K3-D repair (#6514), Options
   C0 (#6604), GMI fold (#6522) — each unblocks multiple crosswalk rows on acceptance.

## Method

Nine read-only routed census workers (one per lane cluster) over repo evidence
(engine/, app/, templates/, scripts/, agentos/, config/, research/, plus the
charting-app repo for F12), synthesized and adjudicated in the receiving session;
independent adversarial spot audit of one row per family F01-F13 by a separate
reviewer. Audit outcome: 9/13 PASS; 4 corrections applied before commit —
MO-PAID-054 state downgraded PROVEN_LIVE→PARTIAL (assistant live, workspace
capability not), MO-PAID-045/020 sibling status refreshed (Stock Identity #6529
program start now bound to its carrier, no longer unclaimed), MO-PAID-071
citation fixed; plus the auditor's out-of-scope flag on MO-PAID-072 resolved
(display receipt live, producer path kept UNVERIFIED). The audit added live
production receipts for aibrief.html, options.html, /api/billing/config
(pk_live), and /api/brain. A second independent audit on the repaired head
(post Sol REQUEST_REPAIR) passed 11/13 rows and its corrections were applied:
MO-PAID-074 ceiling rewritten to the Prophet conditional-fusion truth and
disposition downgraded to UPGRADE_EXISTING, the WS:/lane owner-binding standard
enforced on all 130 rows, the UNVERIFIED register corrected to 27, and the
competitor-authority refusal made explicit on the MO-PAID-024/042 and
MO-DELTA-005 ceilings. Sparse-worktree limits (site/, data/ absent) are
recorded as UNVERIFIED receipts rather than silently upgraded or downgraded states.
