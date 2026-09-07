# Market Ontology F00C — Granular Closure Ledger, Wave C2 (2026-09-02)

Operation: `marketontology-coverage-semantic-closure-fable-principal-20260902-sol-001`
(Fable Project COO — Coverage / Rights / Semantic Closure; bounded child of Program CEO
`marketontology-codex-work-ceo-transition-20260829-sol-001`; principal carrier Slack
`C0BTG1BMY8K/1788318810.201599`). Base: Macro main `20cdfbad66b7` · protected Skillpack
`Mastermind@821e90f8` v1.0.1.

Row data: `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv` — an OVERLAY over
the F00B crosswalk (which is never rewritten, per its own do_not_redo). Method: seven
routed read-only census workers (lane clusters F01 / F02+F06 / F03 / F04+F05 /
F07+F08+F10+F11 / F09 / F12+F13) over repo evidence, synthesized and adjudicated
row-by-row in the receiving Fable principal. Two unintended state drifts
(MO-PAID-078 promotion, MO-DELTA-011 downgrade) were caught by a programmatic
F00B-vs-F00C state diff and reverted before commit.

## Closure claim — exactly scoped

**ADMITTED_NOW (130 rows = MO-PAID-001..088 ∪ MO-DELTA-001..042): granular-F00C tier
UNASSESSED = 0.** Every row now carries granular disposition, confirmed owner, real
producer, real consumer, missing contract/proof, correction/supersession behavior, next
bounded child, and acceptance test. **This claim covers the ADMITTED_NOW denominator
only.** BLOCKED_RETAINED_P1 (1,556 capability/method rows + 460 quality findings) remains
externally gated on the exact 28 originals + Turn-6 manifest and is untouched, unassessed,
and never blended into any percentage here.

## Counts

Granular dispositions (130, post-ruling amendment): NEW_BOUNDED_BUILD 46 ·
UPGRADE_EXISTING_OWNER 40 · PROJECTION_ONLY 21 · CONTEXT_ONLY 8 · BLOCKED_RIGHTS 7 ·
EXACT_EQUIVALENT 5 · REJECTED_BY_DESIGN 3 (ruled) · PENDING_SOL_RULING 0.

Capability states (130): NOT_BUILT 57 · PARTIAL 51 · SPEC_ONLY 11 · BUILT_NOT_PROVEN 6 ·
PROVEN_LIVE 5. Exactly two state changes vs F00B, both evidence-backed corrections:
MO-PAID-060 and MO-DELTA-019 NOT_BUILT→PARTIAL (see below). 28 rows carry refreshed or
corrected evidence; 102 carry F00B evidence forward unchanged.

## Evidence corrections vs F00B (headline findings)

1. **MO-PAID-060 / MO-DELTA-019 (Market Windows): NOT_BUILT → PARTIAL.** F00B's "no
   issuance-window module (grep clean)" is falsified: `engine/ipo_radar.py` implements
   `window_context()` (L79, "is the issuance window hot or cold RIGHT NOW") over a real
   deal calendar (`collectors/ipo_calendar.py`), SCORED=False. The IPO leg exists; the
   follow-on/HY/IG legs remain absent. Scoped-down child: extend the existing pattern.
2. **MO-PAID-013 (skew/smile): source-binding gap, not a verification gap.** F00B's
   "ThetaData canonical" framing is contradicted by `engine/options_skew.py`'s own
   docstring and code (L7, L134): skew computes from legacy `data/polygon_gex/chains/`.
   A genuine ThetaData-migration item, recorded into #6604's consolidation scope.
3. **MO-PAID-020 (owner misattribution).** The blocker for a general issuer journey —
   `NO_GENERAL_NAMESPACE_RENDERER` + `CIK_LEG_UNOWNED_ACCESS` — lives inside
   WS:MARKET-OS's own B1A record and is UNCLAIMED there; F00B's sibling text pointed at
   #6529/WS:STOCK-IDENTITY, which is a different program (behavioral fingerprints) whose
   merge was records-only. Surfaced to the Program CEO as an unclaimed dependency.
4. **#6596 (CRG R0) landed zero runtime** — 7 records files, 1,509 insertions, no code;
   its own DEC forbids becoming traffic middleman. All 13 F12 rows citing it keep their
   states; the F12 gap is real and untouched.
5. **#6543 and #6522 merges are records/architecture freezes**, not shipped product;
   their crosswalk sibling notes now read "MERGED (records-only; capabilities still
   open)". The theme-graph freeze doc names merged #6504 as the actual product-composition
   lane (verified at ship time).
6. **MO-PAID-088 evidence refined**: a `/learn` SEO hub and an economic-release calendar
   widget exist but are not in-product help/FAQ/changelog; state unchanged.
7. **Correction-contract law verified in code** for the stores future children must
   reuse: `engine/macro_thesis.py` (append-only, KEEP-FIRST on thesis_id, `amended_from`
   revision rows, never in-place edit), `engine/falsifier_tripwires.py` (FIRED sticky
   latch; un-fire only via source-version bump; `current_leg` live-re-evaluated — Ruling
   A17), `scripts/compile_capital_structure_events.py` (`correction_version`/
   `correction_of` contiguous chains), `engine/credit_momentum.py` (keep-FIRST idempotent
   forward log), theme_graph store (append-only bitemporal, max-belief_time view), K1
   contracts (append + named predecessors). No child may invent a second correction
   mechanism where one of these governs.

## UNVERIFIED burn-down (F00B register: 27 flags)

Resolved with named evidence this wave: options producer wiring (MO-PAID-012/014
ThetaData-confirmed; 013 legacy-confirmed; 072 chain named; 070 true-zero confirmed);
sovereign-fund source (030 confirmed-absent); per-issuer bond terms (066/D025
confirmed-absent at instrument level); rating-action licensing (D026 confirmed-absent);
commodity family coverage (D029 partially resolved — price/signal tier real, physical
semi supply source still unverified); priority-refresh config (057 confirmed-negative in
repo scope). Remaining open, with reasons: MO-PAID-087 (Supabase-console deletion — an
out-of-repo fact, structurally unreachable from files); MO-PAID-004 + MO-DELTA-013
(engine→template wiring, needs one module-body read pass); UI-layer freshness/branding
claims (MO-PAID-033, MO-DELTA-001, MO-PAID-001 embedding) — sparse-tree scope-imposed,
closable only with live receipts; off-repo data-contract existence (census can only
prove no reference in code/docs).

## Five dockets — RULED by Sol (Program-CEO C2 docket ruling: macro#6748 comment `5504596085`; CEO carrier `C0BTG1BMY8K/1788325004.496539`)

Facts and principal recommendations as originally filed are preserved in git history at
#6748's merged head `ccf80e31`; the controlling rulings, now folded into the ledger rows:

1. **MO-PAID-048 (military asset tracking)** — RULED `REJECTED_BY_DESIGN /
   RIGHTS_GATED_UNLICENSED`: the lawful job is preserved behind a future explicit
   licensing gate; no spend/build authority now. (D0R Imagery/logistics = REJECT unless
   licensed; recommendation ratified.)
2. **MO-PAID-050 (satellite tracking)** — RULED the same for the Planet/Maxar-class
   source.
3. **MO-DELTA-040 (enterprise deployment planner)** — RULED
   `REJECTED_BY_DESIGN_CURRENT_PRODUCT_SHAPE / DEFERRED_POST_TENANCY`: the underlying
   enterprise-deployment-planning job is preserved for a post-F12-tenancy revisit.
4. **MO-PAID-024 (arbitrage scanner authority)** — RULED `AUTHORITY_REFUSAL +
   BLOCKED_DEPENDENCY`: research-only context may exist, but
   direction/confidence/expected-impact/priced% or arbitrage authority requires separate
   K2-C + K3-D acceptance, then K5 + Eval-OS calibrated promotion.
5. **MO-DELTA-006 (ranked-catalyst Opportunity Map)** — RULED
   `SPLIT_LAWFUL_NOW_VS_CALIBRATED_HELD`: plain uncalibrated research-priority ordering
   is lawful now; calibrated ranking/impact/confidence/gate/size/trade semantics remain
   held behind K5 + Eval-OS.

The ruling additionally states, as amendment law: the `UNASSESSED=0` claim stays scoped
strictly to `ADMITTED_NOW=130` and does not close or dilute the retained P1
`1,556 + 460` denominator; this PR is not full parity; no product/trading authority and
no duplicate carriers arise from these rulings.

## Child-convergence ledger (what the 130 rows converge onto)

Existing carriers (accelerations, never duplicated): **#6604 Options C0** absorbs 14 F03
rows (commissioning owner for the catalyst-workflow family, incl. the D035 linkage layer
folded into its Catalyst Picker scope); **K2-C→K3-D→K5 chain** gates 8 F04/F05/F09 rows;
**D2C child** (`gmi-theme-pit-d2c-20260827-sol-001`) owns PIT membership-vintage
materialization, with MO-DELTA-004's exposure-mapping consumer sequenced after its
binding decision; **WS:RATES-INFLATION-COMMAND**, **WS:STOCK-IDENTITY W3**, **F08 lane
program**, **FIF-3A4R**, **K1 review** as named dependencies.

New bounded children this operation will commission (row-bound, in rough order of
leverage): **(a) F11 Thesis-object vertical** (046→047→053; downstream 031/032/054/
MO-DELTA-007) reusing the verified macro_thesis/falsifier_tripwires correction contracts —
the flagship C6 candidate; **(b) F12 tenancy foundation** (051/052/081/082/083/D041),
coordinated with WS:MARKET-OS A2-A6; **(c) F07 valuation-source ruling** (Sol/Chairman
decision gating 022/026/035/037/D017/D002); **(d) consolidated F09/F02 rights docket**
(061/D020, 064-financing, 065/D024, 068, D026 rating actions, D028 AIS, 041/D030, 049,
030-source) — one adjudication gating ~12 rows; **(e) F01/F13 cheap-projection batch**
(011 AM-Edition, D010 indicators catalog, 088 /help+changelog, D011 /glossary, 009
governed wrap); **(f) F09 slices needing no rights gate** — CORRECTED 2026-09-02 after a
verification-first build attempt: 059/D018 maturity-wall is NOT buildable-now (its
instruments-half premise was falsified — document_terms.py is registration-fee-table-only
and no debt-maturity producer exists repo-wide; a new XBRL debt-maturity ingestion child
must come first; see the corrected ledger rows), 062/D021 covenant-text RESOLVED
source-first (archaeology per Sol independent review 5093713353: NO covenant-text
producer exists — document_terms is fee-table-only and event_spine is the SEC
event/edge/review metadata spine; a filing-text/covenant extraction producer child is
required before any headroom computation), 064 premium-math unverified-premise, D029
coverage matrix DELIVERED (this head:
MARKET_ONTOLOGY_F09_COMMODITY_COVERAGE_MATRIX_2026-09-02.csv/.md); **(g) F08 pair-children**: delivery path (027/085), event→position
mapping with the D042 schema (028/D042), user-portfolio risk projection (036/D014);
**(h) F10 output-surface child** (039/D016); **(i) F02 children**: D031 base-map +
sanctions overlay (rights-clear layers only), D032 implementation-state machine, plus an
F02 owner-resolution memo (006/034 carry explicit owner-unresolved flags).

## Program-level items surfaced upward (updated by the same ruling)

- **MO-DELTA-007 contract question — CLOSED** by `MARKET_ONTOLOGY_F13_PERSONAL_ACCURACY_LEDGER_SPEC_2026-09-06.md` (packet B-F13-4): freezes the personal accuracy ledger's data contract, scoring, honest-N rule, and use ceiling. The capability itself stays blocked on the F11 Thesis-object vertical named above (row `next_bounded_child`); row state unchanged at `PROJECTION_ONLY` / `learning_only`.
- **MO-PAID-020 — RULED**: the row belongs to WS:MARKET-OS/F06; Stock Identity/Data OS
  are owner DEPENDENCIES, not child write authority. A single bounded renderer/CIK-access
  repair may be admitted only after a fresh collision census and remains
  `CAPACITY_SELECTABLE / WAITING_CAPACITY`; any owner-path mutation returns
  `OWNER_BOUNDARY_REQUIRED`. (Blocks the second-issuer journey for F06 and B1B-B6.)
- **D2C→W3C fold-sequence — ANSWERED by the same ruling**: `D2C→D2E→W3B→W3C has NOT
  executed`, because D2C still has no receiver/ACK/watcher/START. MO-PAID-043's
  gap-monitor child stays deferred on that sequence actually executing.
- **MO-PAID-038 is a deliberate HOLD** (DEC:MARKET-INTEL-PRODUCTIZATION-NO-NEW-WORKSTREAM
  names ResearchStudy Workbench HELD) — a release decision, never a schedulable build.

No capability promotion, no rank/size/gate/trade authority, no new stores or planes are
created by this artifact. Falsifier vocabulary stays off user-facing surfaces (#3821).
