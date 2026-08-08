# GovTribe clean-room study — 2026-08-07

**Program:** Government Revenue Foresight (MastermindX lobe)
**Status:** research note. Docs only. No `data/`, `engine/`, or collector change is proposed or made here.
**Authority above this file:** `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` (product/architecture) and `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md` (implementation checkpoint, Wave numbering). Where this file and either of those disagree, they win and this file is the thing that is wrong.

**One-line verdict.** GovTribe is a complete, well-built product for a user we do not serve: the bidder. Nothing on its public surface answers an investor question, so there is no product to converge on — but three of its *entity distinctions* (agency→forecast, vehicle-above-IDV, parent/child awardee rollup) name joins we genuinely cannot make today, and two of its public data-model cautions independently confirm rules we already enforce.

---

## 1. Scope and method

### What was read

Public, unauthenticated surfaces only, read on 2026-08-06/07:

| # | URL | Surface class | Depth |
|---|---|---|---|
| 1 | https://govtribe.com/ | Marketing (homepage, nav, AI example prompts, testimonials) | Read |
| 2 | https://govtribe.com/solutions/researchers-and-consultants | Persona page | Read |
| 3 | https://govtribe.com/use-cases/strategic-leadership | Use-case page | Read |
| 4 | https://govtribe.com/use-cases/competitive-intelligence | Use-case page | Read |
| 5 | https://govtribe.com/features/funding-analysis | Feature/report page | Read |
| 6 | https://govtribe.com/features/new-entrants | Feature/report page | Read |
| 7 | https://govtribe.com/features/vehicle-analysis | Feature/report page | Read |
| 8 | https://govtribe.com/features/beacon | Feature page | Read |
| 9 | https://govtribe.com/plans | Pricing | Read |
| 10 | https://blog.govtribe.com/autonomous-warfare-market-snapshot-june-2026 | Public blog post | Read |
| 11 | https://govtribe.com/docs/data-model | Public data-model reference (docs.govtribe.com redirects here) | Read |
| 12 | https://govtribe.com/docs/data-model/guides/source-identifiers-and-record-matching | Public docs guide | Read |
| 13 | https://govtribe.com/docs/data-model/guides/federal-award-values-and-transactions | Public docs guide | Read |
| 14 | https://govtribe.com/docs/govtribe-for-agents | Public docs (agent/MCP layer) | Read |
| 15 | https://govtribe.com/user-guide/what-is.../participants/federal-agencies | Public user guide | Read |
| 16 | https://govtribe.com/user-guide/what-is.../opportunities/federal-contract-opportunities | Public user guide | Read |
| 17 | https://docs.highergov.com/market-intelligence/research-federal-contractors-and-grant-recipients | Public docs (comparison point) | Read |

**17 public sources cited as evidence.**

Four further persona URLs were *enumerated from the Solutions nav* but not individually opened, and no claim in this file rests on them: `https://govtribe.com/solutions/federal-contractors`, `https://govtribe.com/solutions/state-and-local-contractors`, `https://govtribe.com/solutions/grant-seekers`, `https://govtribe.com/solutions/government-agencies`. They are listed because *the absence of an investor persona in that enumeration* is itself a finding (§2), and the enumeration is only meaningful if the full list is shown.

### Clean-room statement

No credentials were used, requested, or sought. No authenticated page, trial, or workspace was accessed. No account was created and no form was submitted. No HTML, CSS, JavaScript, prompt text, image, export, or database record was copied, and no UI was cloned or pixel-matched. What was extracted is limited to (a) jobs-to-be-done — the questions the product exists to answer — and (b) data-model concepts — the entities and relationships the vocabulary implies. This is the boundary already set in the masterplan §6 "Clean-room boundary", and it is a load-bearing constraint here for the additional reason recorded there: GovTribe's published API license expressly restricts using that API to replicate its user experience, so our system uses government sources and original computation only.

### Not accessible clean-room — recorded, not papered over

1. **The authenticated GovTribe application** (search UI, saved searches, pipelines, GovTribe AI chat beyond the static example transcript on the homepage) sits behind `/login` and a 7-day trial signup. Not accessed.
2. **Live GovTribe AI / MCP tool responses.** The docs describe the tool contracts; calling the tools requires an authenticated MCP connection and consumes billed credits. Not accessed.
3. **Funding Analysis, New Entrants, and Vehicle Analysis report outputs.** Each feature page gates the actual report behind a signup form. Only the public marketing description of each report was read; nothing is claimed here about what the reports actually contain.
4. **Zapier and Unanet integration behaviour** beyond one-line marketing descriptions. No public unauthenticated deep docs were located.
5. **Case studies and media-coverage posts** (GovTribe × Knowesis, × MSI Consulting, × PORTCO) were listed on the blog nav but not opened — time-boxed in favour of the use-case, pricing, and data-model pages.
6. **The comparison sweep is materially incomplete.** The second research pass was framed as covering GovTribe, HigherGov (plus its public GitHub API repo and the Tango/MakeGov API), Deltek GovWin IQ, Bloomberg Government, GSA's Forecast of Contracting Opportunities, and the GAO bid-protest docket — but the transcript delivered to this file is truncated mid-sentence and carries citable evidence for only three of those URLs (sources 15–17 above). **No claim in this file rests on GovWin IQ, Bloomberg Government, the HigherGov GitHub repo, the Tango/MakeGov API, the GSA forecast portal, or the GAO docket.** Where §3 and §6 reference forecast records or protest status, the *investor rationale* is ours and the *government-native source* is named as an unverified target to be checked publicly before any build — not as something this study confirmed.

That last item is the honest form of the coverage rule we apply to our own data: a bounded pass with a declared cap is a valid result; a bounded pass presented as complete is not.

---

## 2. Jobs-to-be-done, split by audience

### 2.1 The finding, stated plainly

GovTribe's public surface is organised end-to-end around helping a bidder win the next contract. It names six use cases and five industry personas, and **none of the personas is an investor, analyst, or allocator**. This is not a gap we can exploit by re-labelling a persona page; it is a statement about what the whole product is for. The closest-sounding surfaces resolve, on reading, to capture work.

### 2.2 Capture / BD jobs — dominant, and NOT our user

| Job | Evidence | Source |
|---|---|---|
| Find winnable work before the RFP drops | "Opportunity Identification — find winnable work early… get ahead of competitors before the RFP drops" | 1 |
| Run capture reviews with better win probability | "Capture Management — enter reviews with data-backed strategies and a higher win probability" | 1 |
| Write compliant, persuasive proposals faster | "Proposal Management — write stronger proposals faster… stay compliant and persuasive" | 1 |
| Decide where to point my own BD resources | "Strategic Leadership — …which agencies to pursue, how to approach them, which vehicles to leverage… allocate resources wisely"; "Plan Agency Market Entry — …before you commit substantial BD resources" | 3, 5 |
| Find primes/subs to team with | "Teaming & Partner Identification — find the right primes or subs" | 1 |
| Sharpen price-to-win and Black Hat | "…power price-to-win analysis and Black Hat reviews"; "Benchmark win rates by agency… analyze task order cadence to anticipate recompetes" | 4 |
| Build relationships with government buyers pre-RFP | "Beacon — …Proactively engage with government buyers and potential teaming partners before RFPs are released" | 8 |
| Decide whether to bid for, ride, or sub onto a vehicle | "…identifying whether it's best for you to compete to win (or hold) the vehicle or schedule, or to subcontract to someone who is already on a schedule" | 7 |
| Detect new competitors entering my market | "New Entrants — …early alerts on new competitors… proactively adjust your strategies and bidding tactics" | 6 |

Three corroborating reads, because a taxonomy can be marketing while the product is something else — here the product agrees with the taxonomy:

- **The live AI example prompts** are the actual day-to-day questions: build a compliance matrix for a named market research effort; compare win themes on recent notices against my company's capabilities; map a competitor's pursuits to my offerings and recommend three teaming angles; find the predecessor and incumbent for a named contract; build a targeted teaming longlist prioritising 8(a)/HUBZone/WOSB/SDVOSB (source 1). Every one is proposal- or capture-side.
- **The agent/MCP layer**, the part of their stack architecturally closest to an LLM-driven investor surface, is scoped to the same three jobs: "research markets, qualify opportunities, organize capture work, and explain source data without guessing" (source 14).
- **The pricing axes** are seats (1 / up to 5 / custom), pursuits (up to 10 / unlimited), contact-data depth, and record-export caps (50 / 3,000 / 25,000), with AI/MCP metered in prepaid credits (source 9). Those are licensing units for one company's BD operation. Nothing scales with breadth of issuer or ticker coverage.
- **Even the social proof** is bidder-side: "pipeline has expanded by about 3X", "25% increase in our bid to win ratio", "scale from $1M to $50M in federal revenue" (source 1). There is no testimonial about sizing a position or changing a read on a holding.

### 2.3 Investor jobs — essentially absent

The register we intend to serve — *what changed, who benefits, how big, how soon, how certain, and how confident should I be* — does not appear on any surface read.

- **"Research & Consulting" is not investment research.** The persona page is explicit that it serves people "writing a report, advising a client, or tracking trends across the market" with the same feature set as every other persona, and its case study is two government contractors tired of sifting through data (source 2). "Research" here means procurement research.
- **"Analysts" means capture analysts.** The Competitive Intelligence page says GovTribe "helps analysts, capture managers, and consultants turn rumor into evidence" — and the deliverables it names are price-to-win, win-rate benchmarking, and recompete cadence (source 4). Those calibrate a bid, not a forward-return thesis.
- **"Risk" and "growth" mean the contractor's own P&L.** Strategic Leadership is the closest lexical overlap with investor language — "drive growth while mitigating risk", "how your own pipelines are exposed", "Spot risks early… recompetes, spend shifts, ceiling limits, and competitor moves" (source 3) — and it never becomes risk to a shareholder's position.
- **The one artifact shaped like investor output stops short of the investor question.** The public autonomous-warfare market snapshot prints obligated-versus-ceiling dollars by named vendor and program — e.g. a General Atomics UAV test-asset award at $3.26B ceiling against $367.4M obligated, and DARPA LONGSHOT Phase III at $103.4M ceiling against $101.9M obligated — grouped by opportunity, agency, program, vendor, and key award. The closing call to action is faster pursuit decisions for contractors. Nothing in it discusses what any award means for the awardee's reported revenue, its timing of recognition, its margin, or its materiality to a listed company (source 10).

**Why that last point matters more than the rest of this section.** The data supports the investor question and the product does not ask it. That is the whole opening: it is not a data moat we have to out-collect, it is a framing nobody on this surface is doing. It also means we get no free validation of demand from their marketing — the absence of investor language is evidence about *their* target, not evidence that investors want this. Our demand evidence has to come from somewhere else.

---

## 3. Data-model ideas worth adopting

Filter applied: an idea earns a place here **only** if it answers an investor question our shipped rails cannot answer today. Ideas that are merely interesting, merely well-executed, or merely capture-side are excluded on purpose. Everything below is display/context-tier by construction — none of it originates a signal or moves authority.

### 3.1 Agency → forecast (pre-award pipeline, before any award exists)

- **Investor question.** Is there any public forward-pipeline signal attached to issuer X's agencies or programs *before* an award or even a solicitation exists?
- **Entities / joins.** A `forecast` record type distinct from `opportunity`, joined `agency → forecast`, then later `forecast → opportunity → award` where a source-native linkage exists. GovTribe's public user guide treats forecasts as a separate record type on the agency node: agencies connect vertically (department → bureau → office → command) and horizontally to opportunities, awards, vehicles, IDVs, subawards, grants — **and to a distinct federal-forecast record** (source 15).
- **Do our rails reach it?** No. Our forward spine advances *existing awards* only. Wave 10 rail 4 (SAM lifecycle) is the nearest planned rail and is opportunity-level — a forecast precedes a solicitation, so it sits one step earlier than anything on the plan except Wave 13's "procurement forecasts" line item.
- **Wave.** Wave 10 as a new rail; today it lives in Wave 13 (breadth). See §6 item 7 for the argument to move it.
- **Hazard to encode before anything is built.** An agency forecast is a *plan*, not an obligation, and agencies revise and drop them. It must carry an explicit "plan, not obligation" state, must never advance a candidate, and must never be summed with obligated dollars. The government-native source for this (GSA's Forecast of Contracting Opportunities) is named but **was not verified in this study** — see §1 item 6.

### 3.2 A `vehicle` node above IDV

- **Investor question.** Is issuer X even *on* the instrument the money will flow through, and what share of spend under that shared vehicle goes to it versus its competitors?
- **Entities / joins.** A `contract_vehicle` entity distinct from an IDV record, with a vendor-membership edge, sitting above `IDV → task order/award`. Two independent public confirmations that this is a real distinction and not a naming quirk: GovTribe's opportunity guide describes filtering opportunities as "connected to Multiple Award Schedule" *through vehicle filters, separately from the IDV record itself* (source 16), and its Vehicle Analysis page frames the whole feature at vehicle level (source 7). HigherGov's public API surface likewise lists "Contract Vehicles" as a separate endpoint class from "Contract IDVs" (referenced in the second pass; the specific repo URL was not delivered and is not cited).
- **Do our rails reach it?** Partially, and not at the level that answers the question. Wave 8 shipped an IDV relationship foundation — at the 2026-08-06 checkpoint, 24 selected/count-verified IDVs, 15 complete-detail parents, 452 relationship observations, 26 receipts, and zero exact bridges into the prime dossier. An IDV record cannot express "issuer X holds a seat on vehicle V", which is the thing an investor needs before believing a task-order stream is reachable.
- **Wave.** Wave 10 rail 1 (IDV child bridge), extended with a vehicle node.
- **Hazard.** The vehicle must come from a source-native identifier. A vehicle inferred from award-title text, or a seat inferred from a single task order, is exactly the "do not call an IDV relationship a vehicle seat without source proof" prohibition already in the handoff.

### 3.3 Parent/child awardee hierarchy — adopt the *question*, refuse the *method*

- **Investor question.** What is the total federal obligation attributable to issuer X *including every subsidiary and every additional UEI/CAGE it controls*, and how does an acquisition change that series?
- **Entities / joins.** `public_company → ownership_edge → legal_entity → {UEI, CAGE, recipient}`, with the rollup computed across all reviewed children. HigherGov's public docs describe exactly this layer: children "can represent a subsidiary, an acquired company, or just an additional UEI or Cage Code created by the Parent Awardee", and a parent's analytics include all child awards (source 17).
- **Do our rails reach it?** The *schema* does — masterplan §9.1/§9.2/§9.3 model `legal_entity`, `public_company`, and `ownership_edge`, and Wave 9D is precisely reviewed-issuer-graph expansion. The *coverage* does not: one reviewed issuer (PLTR, `recipient-graph:reviewed:2026-08-03:pltr-v1`, two exact legal entities and two identifiers) against a 21-company backlog at the checkpoint.
- **Wave.** Wave 9D, as an addition to the acceptance gates rather than a new rail.
- **Hazard — and this is the most valuable thing in the whole study.** The same public doc concedes two things we must refuse. First, "awardee hierarchies are inferred from government-reported award data" and may need manual verification. Second, acquired subsidiaries are presented "on a pro forma past performance basis from the date of the acquired awardees' formation" (source 17). A pro-forma restatement that credits an acquirer with a subsidiary's pre-acquisition history is a **point-in-time violation**: it makes the past look different today than it looked then, which is the single failure mode our bitemporal contract exists to prevent. Adopt the rollup; record how each edge was established; refuse the retroactive re-attribution as a default series.

### 3.4 DoD acquisition program as a first-class join key

- **Investor question.** Which named acquisition program is the money attached to, and does that program's budget line move *before* its awards do?
- **Entities / joins.** `dod_acquisition_program` as a node, joined `budget_program_line → program → award` on official PE/line/program identifiers. GovTribe's public data model lists "DOD acquisition program" as a top-level entity alongside awards, IDVs, vehicles, transactions, sub-awards, forecasts, and vendors (source 11).
- **Do our rails reach it?** Foundations only. Wave 8 shipped DoD budget-line and budget-edge *schema*, and the checkpoint records the production rail as unavailable with no budget-to-issuer beneficiary claims.
- **Wave.** Wave 10 rail 2 (DoD budget graph).
- **Hazard.** The program identifier is the *only* non-semantic bridge between appropriated dollars and award dollars. Our standing prohibition — never allocate a budget line to a company by semantic similarity — means the program node is load-bearing: no program identifier, no edge, and the honest answer is a null.

### 3.5 First-observation recipient cohort — the honest form of "new entrants"

- **Investor question.** Has a competitor started winning in a program or agency where issuer X is the incumbent — i.e. is incumbency eroding before it shows up in a recompete loss?
- **Entities / joins.** A first-observation cohort read over `(agency, NAICS/PSC, program) × recipient`, using the first-seen semantics the award-event spine already establishes. GovTribe ships this as a report ("identify emerging competitors in your market", source 6); their framing is defensive bid tactics, ours would be incumbency erosion.
- **Do our rails reach it?** Structurally half-way. Wave 9C shipped the event spine whose entire design distinguishes a first baseline observation from a post-baseline event — that *is* first-seen. What is missing is the recipient-cohort dimension and any notion of a competitor set.
- **Wave.** Wave 10 rail 5 (recompete outcome / displacement), where displacement and share-gain labels already belong.
- **Hazard.** Within a bounded collection universe, "new entrant" means *new to what we observed*, not new to the market. Presented without that state it is a fabricated fact. This is the same class of error as calling a bounded partial collection complete.

### 3.6 Deliberately NOT adopted

- **Buyer/contact intelligence (Beacon).** Its job is pre-RFP outreach to government buyers — an activity that requires being a prospective vendor. Structurally unavailable and irrelevant to an outside investor (source 8). Recorded as a negative case so nobody re-proposes it later.
- **Pursuit/pipeline/stage workspace types** in their data model (source 11). Capture CRM. Wave 13 already says investor foresight comes before CRM parity.
- **Match percentage / estimated competition / probable value.** See §4.4.

---

## 4. What we must NOT copy, and why

### 4.1 The clean-room fence itself

No credentials, ever, including any offered by anyone. No authenticated pages. No signup, no trial, no form submission. No copying of HTML, CSS, JavaScript, prompts, copy text, images, exports, or database records. No pixel-cloning of any UI. No use of a competitor API to recreate a substitute service where its licence forbids that use — GovTribe's published API licence does forbid exactly that (recorded in masterplan §6). This is not a formality: our differentiator is that every figure traces to a public or licensed source we can show, and a single copied record makes that claim untrue for the whole product.

### 4.2 Unattributed aggregates

Their public market snapshot prints ceiling and obligated dollars by named vendor with no per-figure receipt, no `observed_at`, and no statement of the collection universe those totals were computed over (source 10). For a marketing post that is fine. For us it is disqualifying: an aggregate we cannot decompose into receipted rows with an as-of clock is not evidence, it is an assertion. Every rolled-up figure we render must carry its receipt, its clock, and its coverage state — including when the honest coverage state is "bounded partial".

### 4.3 Inferred entity resolution, and pro-forma history

Two distinct prohibitions, both drawn from source 17 and both already law here:

- **Never fuzzy.** Hierarchies "inferred from government-reported award data" are a reasonable product choice for a bidder tool and an unacceptable one for an attribution claim about a listed issuer. Our rule stands: no mapping from a discovery ticker, name similarity, web snippet, or LLM assertion; every active edge reviewable from immutable evidence. Their own docs telling users to manually verify is the strongest possible argument for our stricter bar.
- **Never pro-forma.** Restating an acquired entity's history under the acquirer from the acquired entity's *formation* date rewrites what was knowable when. If we ever show a pro-forma series it must be a separately named, explicitly labelled view — never the default, and never the series a grader reads.

The same fence applies to retrieval: semantic search is a fine way to *find* a record and a forbidden way to *join* one. No semantic-similarity-only issuer or program join.

### 4.4 Numbers that look modelled and are not

GovTribe's published pursuit probability is user-entered, and "probable value" is estimated value multiplied by that user-entered probability (recorded in masterplan §5.2/§4 from their public plan and user-guide material). HigherGov surfaces a match percentage and estimated competition/value. None of these is dishonest in its own context, and all of them would be dishonest in ours, because our user reads a number on our page as *our* claim about the world. Rules that follow: no fused AI score; no composite that hides which leg is missing; every displayed estimate labelled as an estimate with reproducible inputs; contradiction shown beside the thesis rather than averaged into it. This is why Wave 9E's shadow packet is specified as named, separately inspectable legs with the candidate set byte-identical when the packet is absent.

### 4.5 Freshness claims we could not honestly make

Refresh cadences advertised by incumbents (opportunity refresh in the ~15–20 minute class, awards daily — recorded in masterplan §4) describe their pipelines, not ours. Our own SAM key is quota-gated to roughly 00–01 UTC for scheduled collection, so a 30-minute scheduler does **not** mean 30-minute upstream polling, and claiming intraday SAM freshness without a higher-tier key and production evidence would be a false statement about our own system. At the 2026-08-06 checkpoint the honest state was: awards/actions about five days old against a four-day SLA, opportunities unavailable, event spine `projection_state_absent`. Those states must be designed states on the page, not hidden behind a generic "live" chip.

### 4.6 The capture jobs-to-be-done themselves

Building the six-use-case taxonomy from §2.2 would give a non-bidder audience a bidder's CRM. It is the most seductive item on this list because it is the best-specified part of their product and the easiest to copy well. Wave 13 already fences it: investor foresight before capture parity, and no wave spent reproducing capture-management features while the forward event grader is still empty.

---

## 5. Where we are already ahead

Stated as facts about shipped code and current production state, not as positioning. Every number below is the 2026-08-06 checkpoint and must be re-verified live before reuse.

1. **Content-addressed receipts and source-health metadata** on the bounded USAspending award/action rail, with exact prime-award dossiers carrying content-addressed canonical/public twins and generation-bound APIs. No surface read in this study exposes a per-figure receipt.
2. **Point-in-time correctness as a build constraint, not a feature.** Bitemporal semantics on the award rail; separate source, effective, observed, and known-at clocks; the standing prohibition on backfilling current state as historical knowledge; and the rule that a first baseline emits zero events. Wave 9C's verification went further than the contract required — a second run over the same accrued root added +0 snapshot rows and +0 action-version rows with an unchanged projection generation, proving the declared schema round-trips without fabricating source revisions.
3. **Explicit coverage and uncertainty states rather than a single "coverage" number.** The subaward rail distinguishes complete, verified-zero, high-count-only, run-cap-only, and not-selected; awards distinguish bounded partial (safety cap, `hasNext=true`) from source exhaustion; award-dollar coverage is computed independently from entity-count coverage.
4. **Exact issuer attribution with reviewer-bound evidence.** The reviewed graph carries valid-from, valid-to, known-at, evidence hash, reviewer, and review status per edge, with explicit unresolved / ambiguous / stale / partial-coverage states — against an incumbent that publicly describes its hierarchy as inferred. Our constraint is coverage breadth (one reviewed issuer, `PLTR`, exact UEIs `FSY4LVSBGWB7` and `HNN4F9JZWDY8`; 21-company backlog; a proposal tool reaching 19/21 as candidates for review, not as mappings), which Wave 9D addresses. Narrow-and-exact is recoverable; broad-and-fuzzy is not.
5. **Honest nulls, shipped.** Zero candidates today with a stable ledger ID, and `projection_state_absent` surfaced through the API rather than smoothed over. A zero-candidate product is the correct current result and is treated as such in the handoff: identity coverage, attractive UI, large award values, and ticker-search provenance are not catalysts.
6. **A prospective grader with a versioned pre-registration.** `research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md` (GRV-FA1, v3.0.0, registered 2026-08-06 before the first candidate exists, with an amendment law that freezes it once the first issuance row lands) plus `engine/government_revenue/candidate_grader.py` and its guard. **No public surface read in this study describes forward-outcome grading of the vendor's own outputs.** That is a statement about what is publicly documented, not a claim that no such practice exists internally.
7. **Fail-closed authority.** All Government Revenue candidate authority flags are false; the lobe is display/context-only; Wave 9F's acceptance gate is that Prophet's membership, rank, confidence, size, gates, and execution are byte-identical with the adapter on or off, and that a malformed or slow packet fails open to Prophet's pre-existing decision. Nothing here originates a signal, and an LLM may not originate, escalate, or self-authorise one.

Two of their public docs also *independently confirm* rules we already enforce, which is worth recording because independent confirmation is cheap and rare:

- **UEI-based exact matching is the industry-correct bar.** Their source-identifiers guide distinguishes an internal record key from a UEI and instructs readers to "use uei when matching organizations to federal source systems" (source 12). Our exact-attribution rule is not an idiosyncratic self-imposed handicap.
- **Obligated / ceiling / transaction values are a genuine, well-known hazard.** Their award-values guide separates award-level obligated dollars from ceiling value ("a potential or maximum value… should not be used as committed spending") from transaction-level values, and warns against adding award-level obligated dollars to transaction-level values for the same award without a deliberate reconciliation workflow (source 13). Our prohibition on conflating obligations, ceilings, backlog, bookings, and revenue is the same rule — and it currently exists in prose without a machine-checked guard. See §6 item 8.

---

## 6. Prioritised delta to our wave plan

Ordered by *value per unit of build risk*, not by wave number. Every item is display/context-tier. **Nothing in this list promotes authority, originates a signal, changes candidate membership or ordering, or alters any Prophet or Neural Web decision** — items that would touch selection are deliberately written as annotation-only. Nothing here is a build order; the wave owner adjudicates.

| # | Wave | Addition | Why (one line) |
|---|---|---|---|
| 1 | 9D | Record a `hierarchy_evidence_class` on every ownership edge, and forbid pro-forma backfill of an acquired entity's pre-acquisition awards as a default series | The incumbent's own docs concede hierarchies are inferred and restated pro forma; our expansion must state how each edge was established and never rewrite what was knowable when |
| 2 | 9D | Expose the issuer-level dollar rollup across all reviewed UEIs as an explicitly bounded figure, reported separately from entity-count coverage | "Total federal obligation attributable to issuer X" is the first investor question and is unanswerable from a single-UEI view |
| 3 | 10 rail 1 | Add a source-native `vehicle` node above IDV, with a vendor-membership edge | Vehicle-level membership and share is the only way to ask whether issuer X can reach a task-order stream; an IDV record cannot express a seat |
| 4 | 10 rail 2 | Make the DoD acquisition program a first-class join key between budget lines and awards, keyed on official PE/line/program identifiers | The program identifier is the only non-semantic bridge from appropriated dollars to award dollars; without it the honest answer is a null |
| 5 | 10 rail 5 | Add a first-observation recipient-cohort read (the honest "new entrants"), stated as new-to-our-observed-universe | Incumbency erosion is an investor question and first-seen is already a property of the shipped event spine, so this is a read, not a new collection |
| 6 | 10 (promote from 13) | GAO bid-protest status as a display-only annotation leg beside an already-emitted event — never a filter on the candidate set | Protest is a timing-risk qualifier on revenue recognition and matters at event time, not at breadth time; source not verified in this study (§1 item 6) |
| 7 | 10 (promote from 13) | Agency forecast records as a distinct pre-award entity, joined agency→forecast, carrying a "plan, not obligation" state | It is the only public pre-award pipeline signal and it sits one step earlier than the SAM lifecycle rail; it must never advance a candidate; source not verified in this study |
| 8 | 10 gates | A machine-checked non-additivity guard: award-level obligated dollars may not be summed with transaction-level values in the same rendered figure | The incumbent publishes this exact caution in its own public docs; our equivalent prohibition exists in prose with no test behind it |
| 9 | 11 | Make the ceiling / obligated / bookings / backlog / GAAP-revenue distinction a rendering contract — the label travels beside every figure, not in a footnote | The one public artifact closest to investor output prints ceiling and obligated side by side with no revenue-translation caveat; that confusion is what we sell against |

**Two things this list deliberately does not do.** It does not propose any capture, teaming, pipeline, or buyer-contact surface — those are §4.6 and Wave 13. And it does not propose an authority change of any kind: items 1–9 are data-model, coverage-state, guard, and rendering additions, and the authority path remains Wave 12's gauntlet after Wave 9G produces prospective evidence.

---

## Appendix — source ledger

Sources 1–17 are enumerated with URLs in §1. **17 public sources cited as evidence**, all unauthenticated, plus 4 nav-enumerated persona URLs on which no claim rests. Claims attributed to `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` (refresh cadences, pursuit-probability construction, API licence terms) come from that document's earlier study and were **not** re-read from the public web in this pass; they are cited as internal records, not as fresh public verification.
