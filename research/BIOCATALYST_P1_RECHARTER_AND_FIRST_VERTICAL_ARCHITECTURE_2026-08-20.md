# BioCatalyst P1-0 — Post-P0 Recharter and First-Vertical Architecture Freeze

- **Status:** ARCHITECTURE FREEZE — no runtime implementation in this wave (P1-0 charter).
- **Date:** 2026-08-20. Session: `claude/biocatalyst-p1-recharter` (Fable orchestrator, COO seat).
- **Commissioned by:** Sol P1-0 post-P0 recharter directive (the MAS-74 "separate Sol post-P0 adjudication" named by `agentos/handoffs/BIOCATALYST-RECOVERY-V2-2026-08-20-p0-production-closeout.md`).
- **Fresh main at session start:** `8ce996e5cab4c57ddf962856a78e82d013588e49` (2026-08-20T18:18:59Z).
- **Supersedes nothing; composes with:** PR #6052 (merged `427d676de1a3ba086e4b63480018ecd733dd666e`), PR #6090 (merged `e4c2e3b9f83585d7de812ccc55336c6e7fd9d897`), PR #5909 (merged `9711c60d3067f1908a7822008ffd7a8b23171854`), open records PR #6092 (its two closeout commits are cherry-picked into this branch with authorship preserved), draft PR #5821 (candidate only, NOT authority).
- **Binding laws honored:** `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`, `DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK`, `DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN`, `DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK`, `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE`, `DEC:BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI`, `DNR:KILL-PHASE3-START-WEIGHT` (display-tier catalyst chips lawful; scored Phase-3-START weight killed on the tested construction).

---

## §0 Acceptance gates for the FIRST implementation PR (binding; phrased "not done unless")

The P1-1 implementation PR frozen in §10 is **not done unless**:

1. A real entitled browser journey on the deployed production process shows the Catalyst Radar — Trial Milestones surface with **nonzero rows** rendered from the live public generation (measured feasible today: a ≥180-day horizon over event kinds {primary_completion, completion} yields ≥1 row on the current 4-NCT cohort, ≥3 at 365 days — §9 falsification table) (same evidence standard as `research/biocatalyst_recovery_v2/P0_C2R2_PRODUCTION_ACCEPTANCE_2026-08-20.md`): served process/commit identity captured, route timings, no 524, no 5xx, unsigned 401 intact.
2. Every §9 state is reachable and typed: populated, partial-coverage (denominator disclosed), unresolved-issuer, revised-date (with lineage visible), cancelled/terminated, stale, source-outage, locked (entitlement), valid-empty-with-reason. No generic unavailable state without a reason code.
3. Each radar row's evidence drill-down resolves to a real stored source receipt (generation artifact + record-history version chain where present).
4. Zero mutation of the frozen soak surface (§8 file list): `config/biocatalyst_sources.yml` byte-identical, launch manifest untouched, cohort untouched, no collector cadence change, `engine/sector_intelligence/launch_slo_verifier.py` untouched.
5. No score, probability, materiality, rank, or composite anywhere in payload or UI (deterministic source facts only; `authority: facts_and_context_only`).
6. New test suite actually RUNS in CI (check `config/unrun_test_baseline.json` grandfathering; a new engine module must be declared in every curated `scope: exclusive` CI job whose closure reaches it, or `contract-delta` reds the PR).
7. Bilingual EN/ZH surface text; no translated text in `title=` attributes; glance-tier wording per `docs/DESIGN_DOCTRINE.md` (no internal state names, no raw slugs front-facing).
8. PR body carries before/after screenshots of the entitled journey and the row-count + generation digest of the proof read.

---

## §1 Reality baseline (what is actually true at current head)

**P0 is done and proven on the live path.** PR #6052 (request-local retention of admitted generation artifacts) merged 2026-08-20T12:15:14Z; PR #6090 (evidence-only acceptance receipt) merged 12:57:05Z and records **BIOCATALYST P0 — PROVEN_LIVE**: a real entitled Chrome session against `macro-api` MainPID 2529475 serving commit `427d676de1a` completed the `_read_bundle()` journeys — health 200/fresh (coverage 4/4), Trial Screen 200 with four real NCT rows, facets 200, milestones lawful-empty 200, change-tape 200 with 25 rows, prospective-changes lawful `baseline_not_established`, covered trial dossier 200, peer-set resolve 200 (2 requested / 1 covered / 1 uncovered), unsigned 401, invalid-sort 400, no 524/5xx, entitled routes ~4.5–7.9 s inside the ~30 s edge budget.

**The visible workbench is the 4-NCT ClinicalTrials.gov canary cohort** (`NCT04528082`, `NCT05020236`, `NCT06602479`, `NCT07218380`), live public generation `ctgov_run_20260820T120032611932Z_e679bb3d2518`, schema 1.6.0, `coverage_class=current_only`. P0 recovered a **truth boundary**, not a product. This wave turns that substrate into the beginning of the actual product without reopening P0.

**Two CT.gov producers exist and must not be conflated:** (a) the BioCatalyst-native B1/B2 lane (operator-armed VPS timers `app/deploy/macro-biocatalyst*.timer`, dark-by-default, "never enabled by update.sh") which populates the live public generation the product serves — the fresh 2026-08-20T12:00:33Z generation proves it is armed and producing in production; (b) the general altdata collector `collectors/clinicaltrials.py` (nightly `scripts.collect`, `data/clinicaltrials/trials.parquet`, ticker-keyed, no milestone dates) — display/context tier, look-ahead-selected pre-2019 per `DNR:KILL-PHASE3-START-WEIGHT`, and NOT the product's truth plane. The product reads (a) only.

---

## §2 Durable-state reconciliation performed in this PR

- **`WS:BIOCATALYST-RECOVERY-V2` → done.** Open records PR #6092 (branch `chatgpt1/mas-71-biocatalyst-p0-accepted-reconcile`) already wrote the correct closeout: `status: done`, P0-C2R2 done (#6052), P0-C2-PROD-ACCEPT done (#6090 = canonical production receipt), production hydration PROVEN_LIVE, recovery not widened into parity/alpha/Prophet. Rather than collide with that in-flight lane, its two content commits (+1 schema fix) are **cherry-picked into this branch with `-x` (authorship preserved)**; if #6092 merges first these patches drop out on rebase, and if this PR merges first #6092 becomes an empty diff and can close. Verdict on the directive's open question: the recovery objective is **fully done** — no narrowly-named reliability follow-up remains inside the recovery workstream. The one operational reliability observation (entitled route latency 4.5–7.9 s is proven-lawful but not comfortable) is carried as a P1 concern inside the first vertical (§10), not as a reopened recovery wave, per the closeout's own no-widen law.
- **`WS:BPC-JV-RECON` reconciled to #5909-merged reality.** #5909 merged 2026-08-19T19:51:49Z as `9711c60d3067f1908a7822008ffd7a8b23171854`; every "complete pending merge of PR #5909" phrase is repaired. RECON-0 = done (merged). SNAPSHOT-ONBOARD remains **todo** (Sol commissioning owed). CONTINUOUS-RECON remains **todo**. The prohibition on runtime `biopharmcatalyst_jv_snapshot` source-registry insertion until the post-soak successor-registry/successor-launch-manifest transition is **unchanged and re-affirmed**. No duplicate lifecycle store is minted.
- **PR #5821 remains draft architecture.** Its federation thesis (BioCatalyst keeps clinical/regulatory truth; a "Biopharma Cycle Intelligence" subprogram owns market-episode/expectation layers; Market Memory stays the horizontal fabric) is a candidate requiring current-head reconciliation. This freeze neither adopts nor rejects it; the first vertical below is federation-neutral — it builds inside the BioCatalyst truth plane either way. BCI adjudication stays with Sol.

---

## §3 Current capability ledger (canonical statuses, current head `8ce996e5cab4`)

Statuses: PROVEN_LIVE / BUILT_NOT_PROVEN / PARTIAL / DARK_OR_DISCONNECTED / BROKEN / SPEC_ONLY / NOT_BUILT / REJECTED_BY_DESIGN. A schema or dark collector is never called shipped.

| # | Capability | Status | Evidence anchor |
|---|---|---|---|
| 1 | Clinical current-state (CT.gov canary collection → public generation) | **PROVEN_LIVE** (cohort-limited: 4 NCTs) | Fresh generation `ctgov_run_20260820T120032611932Z`; health coverage 4/4 (#6090) |
| 2 | Clinical history / record-history revision chain | **PARTIAL** | `b2_history_canary` default-enabled, 4-NCT allowlist; `engine/biocatalyst/history.py` live; history breadth = canary only |
| 3a | Change tape | **PROVEN_LIVE** | Change-tape 200 with 25 rows (#6090) |
| 3b | First-seen / prospective changes | **BUILT_NOT_PROVEN** | Endpoint live but lawful `baseline_not_established` — no populated proof yet |
| 4 | Trial Screen | **PROVEN_LIVE** | #6090 entitled matrix; `app/biocatalyst.py:3694`; `templates/biocatalyst.html.j2` mode `screen` |
| 5 | Peer matrix (exact-cohort resolver) | **PROVEN_LIVE** (resolver only) | `engine/biocatalyst/peer_matrix.py` — caller-supplied cohort; comparables *discovery* NOT_BUILT |
| 6 | Trial-level dossier | **PROVEN_LIVE** | `/trials/{nct_id}` 200 (#6090) |
| 7 | Company/asset dossier | **NOT_BUILT** | No company-level dossier surface exists (grep receipts in census) |
| 8 | Sponsor→issuer identity | **PARTIAL** | `engine/biocatalyst/sponsor_identity.py` + map: 33 rows `reviewed_admitted`, 16 `ambiguous_queued`, 1 unreviewed, 36 universe tickers unmapped; display-context ceiling `A1_EXPLAIN` |
| 9 | Company/security identity estate (adjacent) | **PROVEN_LIVE** (estate) | `company_identity.v1`: `company_id`=`cik:…`, `security_id`=`mic:ticker`, PIT `ListingAlias` |
| 10 | Drug/asset identity | **NOT_BUILT** | No intervention identity model anywhere; Trial Screen filters lexically |
| 11 | FDA / Drugs@FDA | **PARTIAL** | General `collectors/openfda.py` accrues `data/openfda/approvals.parquet` nightly (display-tier); BioCatalyst B4A lane dark-by-design, **no deploy unit**, `production_ingest_allowed: false`, rights `review_required_before_b4` |
| 12 | Prospective PDUFA evidence | **NOT_BUILT — blocked on plane-authority ruling (§11.3)** | No lawful prospective source exists today: "`pdufa_date` remains a forbidden claim on Drugs@FDA. Forward PDUFA is an issuer-disclosure problem owned by the corporate plane" (BPC RECON-0 freeze). The claim-on-Drugs@FDA is what is rejected by design; the capability itself is buildable once Sol rules on the source plane |
| 13 | Catalyst calendar (readout/milestone) | **PARTIAL** | Milestones tab + `/trials/milestones` live, lawful-empty on 4-NCT next_90d cut; no broader calendar |
| 14 | Pipelines (company-level) | **NOT_BUILT** | `engine/theme_clinical.py` is theme-aggregate confluence context in a sibling program, not a pipeline product |
| 15 | Cash/runway/dilution | **SPEC_ONLY** | `engine/capital_structure/biocatalyst_pit_adapter.py` exists, test-only callers, `_LIMITATIONS` includes `no_cash_burn_runway_or_dilution_calculation`; capital_structure `UNAVAILABLE_CAPABILITIES` names `cash_runway` |
| 16 | Historical catalyst outcomes corpus | **SPEC_ONLY** | `config/biocatalyst_outcome_family_policy.yml`: "It produces nothing… every family `clock_not_opened`… nothing accrues" |
| 17 | Biotech Market Pulse | **NOT_BUILT** | No biotech-specific market surface; general heatmap/pulse estates are not biotech-scoped |
| 18 | Options (biotech lens) | **NOT_BUILT** (lens) | Options estate itself exists and is macro-owned display-tier (`engine/options_hub.py`; program `options-intelligence`: macro=implementation_owner, terminal=renderer) — a composition target, not a gap to rebuild |
| 19 | Alerts/watchlists (biotech events) | **NOT_BUILT** (integration) | Plug point exists: `(date, rule)`-keyed `engine/alerts.py` / `data/alerts/watchlist_alerts.jsonl` / `alert_triage` |
| 20 | API (read/query) | **PROVEN_LIVE** | 10 entitled endpoints in `app/biocatalyst.py`; bulk **export** NOT_BUILT |
| 21 | BPC licensed snapshots (macro side) | **SPEC_ONLY** | Identity `biopharmcatalyst_jv_snapshot` frozen (#5909); zero runtime registration; bytes live in Mastermind |
| 22 | Neural Web hooks | **NOT_BUILT** | Zero `biocatalyst` entries in `config/synapse.yml`; sibling biopharma-seasonality lobe is a different program |
| 23 | Prophet coupling | **NOT_BUILT** (by stage design) | Part 07 §15 five-stage ladder; Stage 0 not yet entered; no authority this wave |

---

## §4 Functional-parity job ledger — reconciled to current head

The corpus's Part 03 §H1 benchmark table literally holds **33 rows, not 32** (the "8/32" / "24/32" counts cite a separate pre-V2 internal ledger that is never reproduced in the corpus — flagged as a permanent denominator caveat; this document adopts the 33-row §H1 table as the canonical job list going forward). Columns: **Src** = source truth; **Rights** = rights state; **PIT** = temporal/point-in-time requirement; **Id** = identity dependency; **Prod/Cons** = current producer/consumer; **Missing edge** = the exact absent link; **Soak** = can ship before soak close 2026-08-26T02:00Z (Y/N); **Succ** = requires post-soak successor registry (Y/N).

P1-priority jobs (the ledger that matters this wave):

| Job | Src | Rights | PIT | Id | Prod/Cons today | Exact missing edge | Soak | Succ |
|---|---|---|---|---|---|---|---|---|
| Clinical readout calendar (first lawful rung = **Radar — Trial Milestones**; a true *readout/topline-announcement* calendar additionally needs issuer-disclosure evidence the registry does not carry) | CT.gov v2 + record-history (both production-allowed, live) | US-gov facts — clean | known_at + date precision + revision lineage — **already collected** | NCT source-native; sponsor→issuer partial OK w/ unresolved state | B1/B2 lane → milestones endpoint live | Milestone→catalyst-event projection + radar surface + evidence drill | **Y** (read-only over live generation; 4-NCT breadth) | N for slice-1; Y for cohort breadth |
| FDA calendar (approvals context) | `data/openfda/approvals.parquet` (nightly, display-tier) | openFDA per-dataset review owed for product tier | approval actions are retrospective facts | ApplNo source-native; sponsor map partial | General collector runs; no biocatalyst consumer | Rights review (b4) + typed product projection | N (product-tier use needs rights review) | Y |
| PDUFA calendar (prospective) | **none lawful today** — forbidden claim on Drugs@FDA; issuer-disclosure problem owned by corporate plane; BPC JV = finite snapshot | Drugs@FDA `review_required_before_b4`; SEC `unavailable_to_biocatalyst` (no duplicate ingest); JV = Chairman finite-snapshot rights | announcement-time known_at; revision/cancel chains from disclosures | issuer identity + drug/asset identity (NOT_BUILT) | none / none | An entire lawful prospective-source plane (corporate-plane composition or post-soak JV seed) | **N** | **Y** + Sol plane ruling |
| Historical catalysts | JV snapshot (capture-time observations) + CT.gov history | Chairman finite-snapshot rights; no export-time backjoin | capture-time only; `DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT` (no historical PIT prices) | same as PDUFA + outcome grammar | outcome policy SPEC_ONLY / none | SNAPSHOT-ONBOARD commissioning (Sol) | N | Y |
| Earnings calendar (biotech lens) | existing earnings estate | in-estate | already modeled | `company_id` | earnings_narrative live / no biotech lens | thin lens over existing estate | Y (out of BioCatalyst plane) | N |
| Drug pipeline screener | CT.gov (per-company rollup) | clean | current-state + change | **drug/asset identity NOT_BUILT** — blocking | B1 lane / none | asset identity model, then rollup | N (cohort=4 makes it vacuous) | Y |
| Company pages / dossier | joins of everything above | mixed | mixed | sponsor→issuer + asset identity | trial dossier only | the joined surfaces it would join | N (inputs missing) | Y |
| Trial Insights (dossier deepening) | CT.gov + history | clean | record-history versions | NCT | live | incremental enrichment | Y | N |
| Cash database / Burn-runway | capital_structure + FIF (SEC facts) | in-estate | bitemporal (built) | `company_id`; sponsor map partial | BC-C2 adapter (test-only) / none | runway computation is a **named non-capability** of capital_structure — needs owner-plane decision (§11) | N | N (not soak-bound; plane-authority-bound) |
| Options data (biotech lens) | existing options estate (macro-owned, display-tier) | in-estate | OI lag law honored by estate | `security_id` | options_hub live / no biotech join | biotech cohort join once issuer identity broadens | N (vacuous at 4 NCTs) | Y (breadth) |
| Notifications/alerts | existing alerts estate | in-estate | event-keyed | event ids from Radar | alerts estate live / no biotech rules | catalyst-event alert rules AFTER Radar exists | N (needs Radar first) | N |
| API access (expand) | existing product API | entitled | n/a | n/a | 10 endpoints live | radar endpoint (slice-1); bulk export later | Y (slice-1 endpoint) | N |
| Market Pulse family (7 rows: dashboard, premarket, gainers/losers, unusual volume, treemap, movers scatter, XBI/IBB) | existing market-data planes | in-estate | intraday/EOD estates live | `security_id` universe def | market estates live / no biotech scoping | a biotech universe definition + thin composition; **explicitly not the first vertical** (directive) | Y technically | N |

P2/P3 jobs (IPO calendar, med-device calendar+pipeline, conference calendar, foreign approvals, historical PoS, analyst ratings (licensed), insider/13F, M&A, model portfolios, catalyst impact table, historical notifications): all NOT_BUILT, unchanged from corpus priorities; none is a candidate first vertical; device/CDRH work additionally barred from starting out of #5909 (`DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE`) and openFDA producer is a stub (`DSC:BPC-OPENFDA-PRODUCER-IS-STUB`).

---

## §5 First post-P0 vertical — adjudication

Candidates compared against: primary user value; machine/intelligence value; differentiation/moat; source+rights readiness; PIT correctness; identity readiness; current production coverage; reusable architecture unlocked; time to one genuinely useful browser journey; active-soak constraints.

**A. Catalyst Radar — Regulatory/PDUFA (Sol's prior).** Highest thematic centrality — and the **worst end-to-end readiness of the four**. There is no lawful prospective-PDUFA source at current head: the RECON-0 freeze makes `pdufa_date` a *forbidden claim* on Drugs@FDA; forward PDUFA is an issuer-disclosure problem **owned by the corporate plane** (SEC ingest is `unavailable_to_biocatalyst` by registry law, `config/biocatalyst_sources.yml` `rights_state: owned_by_corporate_plane`); the BPC JV snapshot is post-soak + SNAPSHOT-ONBOARD-commissioning gated and is capture-time-only evidence; Drugs@FDA itself is `production_ingest_allowed: false` with rights review owed and the B4A worker has no deployment unit.

*Steelman for the prior, engaged directly:* the soak closes in six days; the §11.3 plane ruling and the Drugs@FDA rights review are decisions, not engineering months — so why not freeze PDUFA architecture now and build the day the gates open? Answer: because the gates PDUFA needs are not merely closed, they are **unopenable by any BioCatalyst act**. Even a same-day Sol ruling plus a same-day rights review yields an *approved-actions* (retrospective) spine, not a forward PDUFA date: the missing artifact is a **cross-plane issuer-disclosure evidence contract that does not exist in any form** — its duration is unknown and it is another plane's to produce. That is categorically different from B, whose missing edge is one projection module over already-published artifacts. (The earlier draft's "multi-week dead zone" phrasing was unmeasured and is withdrawn in favor of this exact formulation.)

**B. Catalyst Radar — Trial Milestones.** CT.gov v2 is the only **launch-critical** production-allowed source in the registry, and its record-history sibling `clinicaltrials_gov_record_history` is the **second** production-allowed source — the one that supplies the revision-lineage differentiator (full contiguous registry version history 0..N per NCT, cap 64, with 100% coverage of the served cohort: the `b2_history_canary` allowlist IS the b1 current NCT set). The estate has already built precisely the hard parts: watermark/snapshot chains (known_at), record-history revision chains, `study_date_changed` facts with before/after values surfaced into the public read model, change classification, typed states, entitled serving. The missing edge is one bounded projection (milestone → catalyst event with date precision + revision lineage) plus one surface upgrade (the live Milestones tab becomes the Radar) plus evidence drill-down. Differentiation is real: BioPharmCatalyst shows *a date*; this shows **the date plus its revision history, precision (`ESTIMATED` vs `ACTUAL` rendered honestly), and primary evidence** — date-slippage intelligence nobody gets from a static calendar. (Caveat kept honest: whether the four launch-cohort trials each carry a `study_date_changed` fact is unverified until implementation reads the collected history; the *capability* is proven end-to-end in contract.) Machine value: milestone events are F4 catalyst-family members of Part 07 §15's ladder (display-tier now, ladder later). PIT correct by construction. Identity: NCT source-native (accepted law), issuer chip via the 33 admitted sponsor rows with a designed `unresolved` state for the rest.

*Semantic honesty (naming law for this vertical):* a CT.gov **primary completion date is when the last participant is measured for the primary outcome — it is NOT the sponsor's topline readout announcement**, which is a later, issuer-controlled disclosure the registry does not carry. The vertical is therefore named **Trial Milestones**, its rows say "Primary completion" / "Study completion". *(Tightened by Sol P1-0R, 2026-08-20: public wording must use "Trial milestone", "Primary completion", "Study completion", "days to milestone", and must NOT label a registry completion date a "readout", "catalyst date", or market event — the earlier qualified-"readout" allowance is withdrawn.)* The full readout/topline-announcement calendar is a future capability requiring issuer-disclosure evidence (same cross-plane class as PDUFA, §11.3).

**C. Company/Asset Dossier.** A join surface whose inputs (pipelines, cash/runway, catalysts, asset identity) do not exist yet; building it first inverts the dependency order.

**D. Market Pulse.** Explicitly ruled out as a first vertical by the directive ("do not choose generic Market Pulse merely because market data already exists"); unlocks no event/evidence spine.

### Verdict

**First vertical = B: Catalyst Radar — Trial Milestones**, explicitly architected as the **catalyst-event spine** whose second tenant is Regulatory/PDUFA.

*Boundary reversal, named for ratification:* the live milestones endpoint's own docstring says it is "**deliberately not a catalyst calendar**: it neither infers an event timing nor treats a registry date as an approval, outcome, or market signal" (`app/biocatalyst.py`, echoed in the 2026-08-02 parity handoff: "A registry date is not automatically a market catalyst"). Graduating that monitor into a *Catalyst Radar* evolves this boundary, and Sol must ratify the evolution explicitly (§11.1), not discover it later. What is preserved: the radar still makes **no** approval/outcome/market-signal claim — every row is a registry schedule fact with provenance, and the radar's added value is watchability (ordering, revision lineage, evidence), not signal. What changes: registry milestone dates are now presented *as watchable catalyst-class events* under the catalyst-event spine identity.

**Sol's prior is falsified in its specific pick and preserved in its intent.** The prior's rationale — "creates a reusable event/evidence/identity spine" — is exactly what B builds; A merely *needs* that spine while being unable to feed it from any lawful source today. Current-main archaeology proves B has materially better end-to-end readiness on every readiness criterion (source, rights, PIT, identity, producer, consumer, soak) without shrinking the product: the spine is designed regulatory-tenant-ready from day one (`event_kind` vocabulary includes regulatory kinds; §6), and PDUFA becomes the spine's second tenant the moment its source plane unlocks (§11 hands Sol the plane ruling that gates it). This is re-sequencing, not de-scoping.

---

## §6 Catalyst-event architecture (the spine — binding for the first slice and every later tenant)

Honors `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE` precisely. Mechanical note that makes the law concrete: `company_event.v1` ids are minted as `canonical_event_id(company_id, fiscal_period, event_type)` with a closed six-member fiscal `event_type` vocabulary — a catalyst has no `fiscal_period`, so it structurally cannot be an `evt_cik…` id. **Composition therefore means: reuse the company estate's identity vocabulary and lifecycle/publication-clock discipline; never its fiscal ID space; and mint no parallel generic event bus** — the catalyst event is a projection inside the existing BioCatalyst evidence plane (`engine/biocatalyst/`), not a new horizontal.

How the first slice obtains each required element:

| Element | Source, exactly |
|---|---|
| **Event identity** | Source-native, deterministic: `nct:{NCT_ID}:{milestone_kind}` (e.g. `nct:NCT05020236:primary_completion`) for trial-milestone events; regulatory tenants later use their own source-native keys (Drugs@FDA ApplNo action ids, per accepted law). Never `ticker+date+drug` (that shape stays `jv_reconciliation_match_key` only). |
| **Issuer/company identity** | `company_identity.v1` vocabulary — `company_id` (`cik:…`) / `security_id` (`mic:ticker`) resolved through `engine/biocatalyst/sponsor_identity.py` **only for `reviewed_admitted` rows**; everything else renders the typed `unresolved_sponsor` state. No fuzzy matching (prohibited use in the map itself). |
| **Asset identity** | Explicit unresolved state. Drug/asset identity is NOT_BUILT; the slice displays the CT.gov intervention name as a lexical label and never mints an asset id. |
| **Scheduled date + precision** | CT.gov date fields with their native precision (month vs day) AND registry date type (`ESTIMATED`/`ACTUAL`/`UNKNOWN`) — both first-class fields, rendered honestly ("Nov 2026 (Est.)" vs "2026-11-14 (Actual)"). Semantic limits are law (§5): completion date ≠ announcement date; values are sponsor-submitted registry facts, not government-verified outcomes. |
| **known_at** | Capture timestamp from the evidence-store watermark/generation chain (never wall-clock at render). |
| **Revision/cancellation history** | Record-history version chain (b2 canary) + change-tape classification; status transitions (terminated/withdrawn/suspended) project to `cancelled`-class states. First complete poll in an epoch establishes baseline and emits no change (existing prospective law). |
| **Source evidence** | Drill-down resolves to the stored generation artifact + record-history version receipts — the primary evidence IS the product's trust story. |
| **Rights** | US-government source facts; display lawful; per-row `source` chip. |
| **Correction lineage** | Supersession discipline borrowed from `company_event.v1` lifecycle states (discovered→scheduled→rescheduled→…→cancelled) and the earnings-manifest "cannot supersede same revision" rule; every revision row keeps its predecessor pointer. |
| **Coverage/freshness** | Generation stamp + health state; denominator honesty: "covering N of M cohort trials" with the cohort size disclosed (4 during soak). |

**Deterministic vs model:** everything above is a deterministic source fact. **No event probability, no materiality score, no investment rank in this slice** (charter; also `DNR:KILL-PHASE3-START-WEIGHT` for scored constructions; LLMs originate nothing per A7).

---

## §7 BPC snapshot role

Chairman-approved finite-snapshot rights preserved verbatim (`DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN`): storage, repository/product incorporation, and research are authorized; there is no continuing BPC feed; export-time Price/IV/OI/EM/mcap may never backjoin onto older catalyst dates as if known then (capture-time observations only, `DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT` reinforces that no historical PIT price plane exists to fake it with).

**Ruling for the first vertical: the slice uses NEITHER the JV snapshot NOR Mastermind owner-plane evidence — it runs entirely on BioCatalyst's own CT.gov evidence plane.** The JV snapshot's product roles (history seed, reconstruction oracle, outcome corpus, capture-time observation layer) all activate **post-soak, after SNAPSHOT-ONBOARD is separately commissioned by Sol**, and enter runtime only through the successor registry (`DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK`). When they do, provenance is explicit per row (`observed_at` capture stamps, `licensed_finite_snapshot` class), never blended silently with continuously-collected rows. No JV insertion into the active source registry during the current soak — reaffirmed, not bypassed.

---

## §8 Active soak boundary — blocker classification

Frozen until 2026-08-26T02:00:00Z (window verified in `config/biocatalyst_launch_slo_manifest.yml`: `soak.window_start/window_end`; registry hash-bound via `source_registry_sha256 bf19c50a…`): `config/biocatalyst_sources.yml`, the launch manifest, CT.gov cadence/opportunity rule, fixed cohort (incl. the `b2_history_canary` 4-NCT allowlist), freshness budget, denominator law, `engine/sector_intelligence/launch_slo_verifier.py`.

Classification of P1 work:

- **NOT soak-blocked (may be built and shipped now):** the entire §10 first slice. It reads the already-published public generation and evidence artifacts through the P0-proven read path, adds no source, changes no cadence, touches no frozen file. Read-only product consumers are the established lawful pattern (Trial Screen/Change Tape are exactly that).
- **Post-soak gated (architecture done now, runtime later, no bypass):** cohort expansion beyond 4 NCTs; `biopharmcatalyst_jv_snapshot` runtime registration; Drugs@FDA/openFDA activation (also rights-review gated); any machine-enforced JV registry test. **Sequencing law (amended by Sol P1-0R, 2026-08-20):** `2026-08-26T02:00:00Z` is the end of the frozen observation window, **not automatic expansion authority**. The required first act after the window closes is: freeze the exact soak evidence → adjudicate pass/fail against the frozen freshness law → then commission the successor-registry/successor-launch-manifest transition already specified step-by-step in `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md` §Priority-0 (freeze 336-opening evidence snapshot → raw_telemetry → telemetry_generation → replay drills → typed ci_validation → successor manifest preserving every frozen field → `verify_biocatalyst_launch_slo_evidence` → record failures without deleting opportunities). Only after that transition may runtime JV registration, approved Drugs@FDA source changes, or cohort expansion land. If the predecessor soak fails under its frozen freshness law, record the failure and require the appropriate new prospective successor window — elapsed time is never silently treated as a pass.
- **Plane-authority gated (not soak-bound at all):** prospective-PDUFA sourcing (corporate-plane composition ruling, §11) and cash/runway computation (capital-structure plane ruling, §11).

---

## §9 Experience architecture — Catalyst Radar — Trial Milestones, first slice

**The user job:** "What trial milestone is coming, when, has the date moved, whose is it, and what's the evidence?" — answered at a glance, no wall of machine prose.

**Surface:** the existing Milestones tab on the BioCatalyst page graduates into **Catalyst Radar — Trial Milestones** (same page, same entitlement, no new route family). Rows ordered by time-to-event. Each row (glance tier): trial short title · phase chip · issuer chip (ticker when resolved) · event kind (plain words: "Primary completion" / "Study completion") · scheduled date with honest precision AND registry date type (Est./Actual) · days to milestone · a **date-moved chip** when revision history exists ("moved +3 mo · Aug 12") · condition. Hover/expand (tier 2): full revision lineage, known_at stamps, sponsor line, intervention name, link to trial dossier, **evidence drill-down** to the stored source receipt and record-history versions.

**Feasibility falsified with real data (public CT.gov v2 registry values read 2026-08-20 for this adjudication; the production radar reads the frozen generation, whose source dataset is 2026-08-19):**

| NCT | Primary completion | Study completion | Status |
|---|---|---|---|
| NCT04528082 (Amgen) | 2030-02-07 Est. | 2030-12-17 Est. | Recruiting |
| NCT05020236 (Pfizer) | **2026-02-26 Actual — already reached** | 2027-05-31 Est. | Recruiting |
| NCT06602479 (AbbVie-sponsored) | **2026-12-18 Est.** | 2027-05-07 Est. | Recruiting |
| NCT07218380 (Lilly) | 2029-10 Est. (month precision) | 2033-05 Est. (month precision) | Recruiting |

Accounting for the endpoint's whole-interval containment filter and generation-date anchor: **`next_90d` → 0 rows** (this is exactly the P0 lawful-empty), **`next_180d` → 1 row** (NCT06602479 primary completion), **`next_365d` → 3 rows** (adds two study completions in May 2027). **The first slice therefore defaults to a ≥365-day horizon** (with kinds {primary_completion, completion}), and §0 gate 1 is satisfiable on the live cohort today. NCT05020236's already-reached ACTUAL primary completion is the real-data exemplar for the "occurred" filter state, and NCT07218380's month-precision dates exercise honest-precision rendering.

**Typed states (all must exist; most already do in the estate):**

| State | Behavior |
|---|---|
| Landing | Radar list, nearest event first; coverage line "Tracking N upcoming events across M covered trials" |
| Useful populated | Rows as above; default horizon ≥365d (measured: 3 rows on the current cohort — falsification table above); never padded |
| Partial coverage | Denominator disclosed: "Current cohort: 4 registered trials" + plain-word note that coverage expands after the source-quality soak concludes |
| Stale snapshot | Health/generation stamp drives a quiet "data as of …" chip; absolute stamp, never a frozen delta |
| Unresolved company/asset | Issuer chip renders "Sponsor: Pfizer (issuer unmapped)" — never a guessed ticker; asset always lexical |
| Conflicting dates | Both source fields shown with their precisions; no silent pick |
| Corrected/revised date | Date-moved chip + full lineage on expand; predecessor value visible, struck through |
| Cancelled event | Trial terminated/withdrawn/suspended renders a terminal state with the status transition receipt; row drops from default view, kept under a "changed" filter |
| Source outage | Existing typed `source_outage` state, plain words ("source unreachable — last good read …") |
| Entitlement failure | Existing locked state (401 path proven) |
| Valid empty | Lawful-empty with reason ("no upcoming milestones in the next N days for covered trials") — already the proven behavior, now with the reason sentence |

**Real-data reference composition (registry values above; 365-day horizon; production values come from the frozen generation at render time):**

```
CATALYST RADAR — TRIAL MILESTONES            data as of 2026-08-20 12:00 UTC · cohort: 4 trials
────────────────────────────────────────────────────────────────────────────────────────────
▸ Migraine study — Ph 2                Primary completion   Dec 18, 2026 (Est.)   in ~4 mo
   NCT06602479 · sponsor: AbbVie (issuer pending review)    evidence ▸ · history ▸
▸ Migraine study — Ph 2                Study completion     May 7, 2027 (Est.)    in ~8.5 mo
   NCT06602479                                              evidence ▸ · history ▸
▸ Elranatamab study — Ph 3 · PFE       Study completion     May 31, 2027 (Est.)   in ~9 mo
   NCT05020236 · multiple myeloma                           evidence ▸ · history ▸
── occurred ────────────────────────────────────────────────────────────────────────────────
▸ Elranatamab study — Ph 3 · PFE       Primary completion   Feb 26, 2026 (Actual) reached
   NCT05020236 · multiple myeloma                           evidence ▸ · history ▸
────────────────────────────────────────────────────────────────────────────────────────────
Beyond horizon: Apremilast peds (AMGN, primary completion Feb 2030) · Vepugratinib (LLY, Oct 2029 — month precision)
Registry dates are sponsor-submitted estimates, not announcement dates. Coverage expands after
the current source-quality soak window closes (Aug 26).
```

(The AbbVie rows deliberately exercise the unresolved-issuer state with a real case — the sponsor row resolves only if `reviewed_admitted` at render time; the Pfizer "occurred" row exercises the actual-vs-estimated and past-event states; the beyond-horizon line keeps the 4-trial denominator honest.)

---

## §10 First implementation slice — FROZEN (exactly one independently useful PR)

**P1-1: Catalyst Radar — Trial Milestones** — source/read-adapter → temporal catalyst event → identity → bounded API → one useful Radar surface → evidence drill-down → entitled browser proof. One PR. Not a mega-build; no calendars-plus-dossiers-plus-options-plus-alerts.

Scope (all inside existing planes; zero frozen-surface mutation):

1. `engine/biocatalyst/catalyst_events.py` (new, pure projection module): validated trial snapshots + record-history + change-tape → `catalyst_event` rows per §6 (source-native id, scheduled date + precision, known_at, revision lineage, issuer resolution state, typed terminal states). Deterministic; no network; no new storage plane — projects at read time from the admitted generation artifacts exactly as existing `_read_bundle()` consumers do.
2. `app/biocatalyst.py`: one bounded entitled endpoint `GET /api/biocatalyst/v1/catalyst-radar` (site_full, same generation-read pattern #6052 fixed; request-local; pagination + horizon params; typed states).
3. `templates/biocatalyst.html.j2` / `.js` / `.css`: Milestones tab → Catalyst Radar — Trial Milestones per §9 (EN/ZH; glance tier + expand tier; evidence drill-down to receipts).
4. Tests: unit (projection determinism, revision lineage, precision handling, unresolved-issuer, cancelled, valid-empty) + API contract + the §0 acceptance journey. **Wire the suite so it actually runs** (§0 gate 6).
5. Entitled production proof per §0 gates 1–3 (same receipt standard as #6090).

Explicit exclusions: no source-registry change, no collector change, no cohort change, no JV data, no Drugs@FDA, no scores/probabilities, no alerts, no Neural Web registration (a `tier: display` synapse entry is deferred until the artifact stabilizes — registration is a one-line YAML follow-up, not slice scope), no Prophet, no company dossier. Implementation model routing: Sonnet `builder` on a frozen spec; design deltas within the existing BioCatalyst page idiom (no new visual language — this is not a taste-as-deliverable surface; the §9 composition is the spec).

**Continuation handoff with the full commission text: `research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md`.**

---

## §11 Decisions returned to Sol / Chairman

> **P1-0R authority-closure status (Sol, 2026-08-20):** items 1–5 are ruled.
> 1 → `DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR` is Sol-ratified
> (container = Catalyst Radar; first lane = Trial Milestones / registry
> schedule facts; binding public wording law). 2 → the P1 home is
> `WS:BIOCATALYST-CORE-PRODUCT` (P1-1 = first wave, commissioned when the
> P1-0R PR merges after Sol review). 3 →
> `DEC:BIOCATALYST-PDUFA-TRUTH-IS-CORPORATE-DISCLOSURE-PLANE`. 4 →
> `DEC:BIOCATALYST-CASH-RUNWAY-OWNED-BY-CAPITAL-STRUCTURE`. 5 → the
> sequencing law is amended in §8 (soak-evidence freeze → pass/fail
> adjudication → successor transition; window close grants no expansion
> authority); the concrete post-soak commissioning acts (SNAPSHOT-ONBOARD,
> Drugs@FDA b4 rights review, cohort expansion policy) remain future Sol
> acts in that order. 6 (BCI #5821) remains open and unchanged.
> The Sol-ratified public wording law supersedes any contrary wording that
> survives elsewhere in this document.

1. **Ratify the first-vertical revision AND the named boundary evolution** (§5): Trial Milestones before Regulatory/PDUFA on the shared spine — this falsifies Sol's stated prior on readiness evidence — and the graduation of the "deliberately not a catalyst calendar" milestone monitor into the Catalyst Radar (boundary reversal named in §5 Verdict; the no-signal discipline is preserved, the catalyst-event framing is what changes). Sol should confirm or veto both before P1-1 is commissioned.
2. **Workstream home for P1 implementation.** This wave deliberately creates no new runtime workstream (`WS:BIOCATALYST-RECOVERY-V2` is closed and must not become the catch-all; `WS:BPC-JV-RECON` is snapshot archaeology). The architecture evidence says P1 needs a home with `owns_paths` over `engine/biocatalyst/` product surfaces — question returned to Sol rather than minted here.
3. **Prospective-PDUFA source plane.** Forward PDUFA is issuer-disclosure truth owned by the corporate plane (RECON-0 law). Options: (a) corporate-plane 8-K/PR evidence composition consumed by BioCatalyst; (b) post-soak JV snapshot as capture-time seed; (c) both with explicit provenance. Cross-plane ownership → Sol.
4. **Cash/runway computation ownership.** `cash_runway` is a named non-capability of capital_structure; the BC-C2 adapter explicitly refuses it. Someone must own the computation (capital-structure plane vs BioCatalyst consuming raw observations) before the Burn/Runway job can exist → Sol.
5. **Post-soak sequencing bundle** (single adjudication recommended): successor-registry transition execution → SNAPSHOT-ONBOARD commissioning → Drugs@FDA rights review (b4) → cohort expansion policy (breadth, denominator law successor).
6. **BCI federation (#5821)** remains a draft candidate awaiting Sol; nothing in this freeze depends on it either way.

## §12 Standing prohibitions carried forward (unchanged by this wave)

No Prophet authority; no Neural Web authority; no composite BioCatalyst score; no JV runtime registration during soak; no scored catalyst constructions (`DNR:KILL-PHASE3-START-WEIGHT` scope); no SEC duplicate ingest; no ticker+date+drug identity; no parallel event bus; no fabricated historical PIT; falsifier language never front-facing.
