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

Granular dispositions (130): NEW_BOUNDED_BUILD 46 · UPGRADE_EXISTING_OWNER 40 ·
PROJECTION_ONLY 20 · BLOCKED_RIGHTS 7 · CONTEXT_ONLY 7 · PENDING_SOL_RULING 5 ·
EXACT_EQUIVALENT 5.

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

## Five dockets for explicit Sol ruling (facts + principal recommendation)

1. **MO-PAID-048 (military asset tracking)** — D0R registry row 38: Imagery/logistics =
   "REJECT unless licensed"; no lawful source integrated; row's own notes name it a
   REJECTED_BY_DESIGN candidate absent a license. *Recommendation:* ratify
   REJECTED_BY_DESIGN-until-licensed — the mechanism is rejected while unlicensed, the
   lawful job is preserved behind an explicit Chairman/commercial licensing gate.
2. **MO-PAID-050 (satellite tracking)** — same D0R row; Planet/Maxar-class gate; only
   repo "satellite" hit is a sector keyword (`engine/altdata_models.py:274`).
   *Recommendation:* same ruling as 048.
3. **MO-DELTA-040 (enterprise deployment planner)** — owner is the commercial/product-ops
   layer with no intelligence-truth ownership; F12 tenancy is 12/18 NOT_BUILT.
   *Recommendation:* REJECTED_BY_DESIGN-now for a single-tenant product; preserve the job
   for a post-tenancy revisit clause.
4. **MO-PAID-024 (arbitrage scanner authority)** — ceiling refuses competitor
   direction/confidence/expected-impact/priced% absent calibrated promotion (Sol
   amendment `1787907339.753029`; K2-C→K3-D→K5 chain all short of acceptance).
   *Recommendation:* ratify the refusal as permanent row law — the fields are inheritable
   only via Mastermind's own K5 + Eval-OS calibrated promotion; no interim surface.
5. **MO-DELTA-006 (ranked-catalyst Opportunity Map)** — same amendment; row's own note:
   "permissible now only as plain uncalibrated research-priority list."
   *Recommendation:* ratify that split — the uncalibrated research-priority list is
   lawful now; every calibrated field waits on K5 promotion.

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
governed wrap); **(f) buildable-now F09 slices** needing no rights gate: 059/D018
maturity-wall from EDGAR XBRL, 062/D021 covenant-text extraction, 064 premium-math,
D029 coverage matrix; **(g) F08 pair-children**: delivery path (027/085), event→position
mapping with the D042 schema (028/D042), user-portfolio risk projection (036/D014);
**(h) F10 output-surface child** (039/D016); **(i) F02 children**: D031 base-map +
sanctions overlay (rights-clear layers only), D032 implementation-state machine, plus an
F02 owner-resolution memo (006/034 carry explicit owner-unresolved flags).

## Program-level items surfaced upward

- The **MO-PAID-020 renderer repair is unclaimed** inside WS:MARKET-OS — Program CEO
  visibility requested (blocks the second-issuer journey for F06 and B1B-B6).
- The **D2C→W3C fold-sequence status** could not be confirmed from module docstrings;
  asked on the Program CEO carrier rather than guessed.
- **MO-PAID-038 is a deliberate HOLD** (DEC:MARKET-INTEL-PRODUCTIZATION-NO-NEW-WORKSTREAM
  names ResearchStudy Workbench HELD) — a release decision, never a schedulable build.

No capability promotion, no rank/size/gate/trade authority, no new stores or planes are
created by this artifact. Falsifier vocabulary stays off user-facing surfaces (#3821).
