# Long-Hold Lobe Brainstorm — Adjudication (by Fable)

**Date:** 2026-07-12
**Source paper:** `research/LONG_HOLD_LOBE_BRAINSTORM_FOR_FABLE.md` (external ChatGPT study with repo access, committed as-received for provenance; misstatements are corrected HERE, never edited there)
**Method:** 2-lane Sonnet census (governance/engine claims; data feasibility) + 4-lens Opus adversarial review (house law, statistics, feasibility, decision value) + Fable adjudication. Census claims below carry file:line evidence from the assessment run.
**Program:** long-hold (this is intake for the existing lobe; no new lobe, no new program).

---

## 0. Verdict on the paper

This is the best-calibrated external paper the lobe has received. It requests **zero hypothesis slots**, correctly deduplicates against Leader Radar (no second anticipation scanner), correctly refuses fused scores / valuation sell rules / positive-13F / index-inclusion probabilities, and §C's "what does not count as honest N" is adopted nearly verbatim as doctrine. The prior two external papers were 60–70% redundant; this one is ~15% wrong and ~85% adoptable-with-amendments.

Its failures are concentrated in **factual claims about what the repo already collects**, plus one governance end-run:

| # | Paper claim | Ground truth | Consequence |
|---|---|---|---|
| 1 | A6: "Route **existing** EDGAR item codes … EDGAR submissions already carry 8-K item codes" (§A6, ranked #3 as zero-data-cost) | `collectors/edgar_8k.py:94` hard-filters to `MATERIAL_ITEMS = {"1.01","2.01","2.03","5.02","7.01","8.01"}`. Of A6's six routing items, only 5.02 is in the store; **2.04 and 4.02 are collected nowhere in the repo**; 1.02/1.03/3.01 exist only inside the Special Situations desk universe (`engine/special_situations.py:95-103`, history since 2026-02) | A6 is blocked behind a collector-expansion PR; its #3 rank was earned on a false cost claim |
| 2 | A1's third axis "campaign/tape state: intact \| climactic \| support lost (**read-only from exit/radar**)" | No Exit/Trim engine exists (`engine/exit_trim*` NOT FOUND; planned only, `NW_FINAL3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md:189`). Existing hold states are tactical (`engine/hold.py` LAUNCHED/BROKEN/INTACT; `engine/donor.py` cracking/intact) | The axis has no source; struck from A1 v1 (LHB-R2) |
| 3 | A2's receivables leg and A5's RPO/contract-liability clock run "at filed-quarter cadence" | `statements_quarterly.parquet` (62,240 rows, 1,507 tickers) has revenue/gross_profit/CFO/capex/shares/repurchases but **no receivables, inventory, payables, or contract liabilities** (`scripts/backfill_edgar_quarterly.py` FLOW_Q/BALANCE dicts); RPO is annual-only, 75 tickers (`scripts/edgar_rpo.py`) | A2 pilots on the gross-margin leg only; A5 deferred; quarterly-store enrichment chartered (LHB-R6) |
| 4 | WA-R8 forces "one frozen construction, one ruler" and a **coverage census** can reserve a future slot | WA-R8 verbatim (`WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md:107-110`): slots require **≥8 annotated `winner_case.v1` cases + one Opus-reviewed fingerprint report + explicit Fable/operator ruling**. LR-R9 records a red team already striking the identical "census unlocks a slot" move and routing it to the WA docket | Both slot reservations DENIED as framed (LHB-R5); registry row appended |
| 5 | `material_8k_events` is an existing winner-autopsy field | It is a parquet (`data/edgar/material_8k_events.parquet`, 49,402 rows) read by `engine/altdata.py:614`; **not** a field in `engine/winner_autopsy.py`. B1's join is feasible but is net-new engine work | B1 recosted (still cheap); B1's `hard_event_reversed` leg shares A6's Item-1.02 collector gap |
| 6 | "Do not relaunch SLF-028/029/030/034" (uniform killed bucket) | SLF-028 and SLF-034 are KILLED; **SLF-029 is a live display-only candidate** (`local_phase0_ready`), SLF-030 completed display-only | Minor; B3 consumption framing survives |

Two smaller corrections: "annual cadence" for the W2 falsifiers is a data-grain fact (adjacent fiscal years), not a schedule — they compute nightly/on-demand; and the paper's `challenged|broken` de-escalation discipline is enforced by convention, not CI — the LLM-origination guard (`tests/test_constitution.py:406`) covers only the LLM path. LHB-R3 pins the deterministic-escalation rule so this stays discipline-with-a-written-law rather than vibes.

**In plain English:** the paper's philosophy ships almost intact — evidence packets, not verdicts; falsifiers, not scores; the operator keeps the playbook choice. What changes is the order (the waterfall before the packet), the honest cost (two collector/enrichment PRs the paper thought were free), and the slot discipline (WA-R8 is the only gate; no pre-reservations).

---

## 1. Rulings (LHB-R1 … LHB-R11)

- **LHB-R1 (build order).** A3 (Fundamental Delivery Waterfall) builds FIRST, not A1. A3 is the surface most likely to change a real decision on a name up 50–150% ("is the run earned?"); A1 is the scaffold it slots into. The paper's own smallest-version logic is adopted: if A3-at-onset doesn't change what evidence the operator checks, the packet won't either.
- **LHB-R2 (A1 ships two axes).** Business-evidence axis + expectation-burden axis only. The campaign/tape axis is STRUCK from v1 — its claimed source does not exist, and building a tape-state machine is exit/trim territory, not long-hold's. If an exit/trim program later ships a machine-readable campaign state, A1 may consume it read-only by amendment. A1 is operator-blind (must not know holdings — standing kill, `DO_NOT_REBUILD.md` held-position ledger row) and lives on the **admin Long-Hold page (Tier-3)**: the raw enum vocabulary is legal there and ONLY there; any future Tier-1/2 surfacing requires DESIGN_DOCTRINE plain-word translation and a stance line, by separate ruling.
- **LHB-R3 (deterministic-escalation law for hold displays).** Status enum pinned: `not_observed | no_break_observed | challenged | broken | unverifiable`. Auto-`broken` is legal ONLY from filed terminal events (8-K Item 1.03 bankruptcy/receivership; a filed primary-endpoint failure or agreement termination explicitly named in that ticker's contract). Every other trigger caps at `challenged`/review. Stale or missing evidence → `unverifiable`, never `no_break_observed`. LLMs remain extraction/de-escalation-only (existing law); this ruling extends the spirit to deterministic writers.
- **LHB-R4 (A3 refusal-first).** The waterfall is a multiplicative accounting identity with pre-declared reconciliation tolerance; any case that can't reconcile shows raw components and refuses the bars. Mandatory refusal triggers: denominator sign change, major acquisition/spin-off, accounting-standard change, and a **split guard** — per-share bridges refuse when the share count moves >20% between endpoints without corroboration (EDGAR cover-page shares are stale after splits; the split-store is still a TODO — see memory `edgar-shares-split-staleness`). Residual bar is labeled "valuation/mix/accounting residual." **A3 must NOT compute implied growth or "what must be true" CAGR — that is PR-N, and PR-N stays W3-LOCKED behind the G1 retest.** (The Opus reviewer proposed A3 emit EV/sales implied-CAGR; rejected — that jumps the W3 lock.) v1 anchors to Detector-D onset only; user-selected anchor dates are a v2 question.
- **LHB-R5 (slot reservations DENIED; WA-R8 is the only gate).** Candidate-1 and Candidate-2 are noted with interest and NOT reserved. Route: `winner_case.v1` cases (≥8) + Opus-reviewed fingerprint report + explicit ruling, per WA-R8 — a standalone coverage census does not open the budget (LR-R9 precedent, second attempted end-run in a week; registry row appended, §4). Candidate-1 additionally requires, before any future registration: (a) a **price-matched control arm** — episodes with the same run magnitude and no fundamental break — because the peer-relative gate controls sector-common shocks but not price mean-reversion at a 126d ruler on run-selected episodes; (b) the WA-R7 fence (fundamental features excluded from t0 ≥ 2024-01-01 aggregates until A2 commits), which shrinks its honest n below the paper's implication; (c) `fdr_family='long_hold'` isolation (LH-R5). Candidate-2 additionally: era window 2014+ only (WA-R4/DT-R16; the 8-K numeric item scheme post-dates 2004 and usage drifts — pre-2014 topology is not comparable).
- **LHB-R6 (quarterly-store enrichment chartered).** Add `receivables`, `inventory`, `payables`, `contract_liabilities`/`deferred_revenue` XBRL tag chains to `scripts/backfill_edgar_quarterly.py` + off-render backfill. `statements_quarterly.parquet` currently has ZERO downstream readers — its first consumer (A2/B2) brings synapse/dag registration and a schema guard, netted into the consuming PR. Display-nothing until consumed.
- **LHB-R7 (8-K item expansion chartered).** `MATERIAL_ITEMS` += `{1.02, 1.03, 2.04, 3.01, 3.02, 4.02}` in `collectors/edgar_8k.py` + off-render backfill. Precondition for A6 routing and B1's reversal leg. A6 consumes the expanded `material_8k_events` parquet — NOT the Special Situations desk engine (single-writer respected; the desk's 16-category taxonomy stays desk-owned).
- **LHB-R8 (C1 satellite, stratum-honest).** Prospective all-listed Detector-D satellite ADOPTED as accrual infrastructure: archive exchange symbol directories (security-type + exchange) prospectively + CIK mapping; strata (S&P 1500 / non-S&P US common / FPI-ADR) permanently separate. **Pooled cross-strata base rates are FORBIDDEN on every surface** — microcap breakaway populations are squeeze/blow-off-dominated; a pooled rate launders a different population under one flag. Grows the breakaway census only; touches G1 never.
- **LHB-R9 (C2 method).** Recurrent-event reuse after the frozen 63-td cooldown is legitimate. The ratified primary null is the **within-month episode-label permutation** (existing law); Andersen–Gill counting-process framing is demoted to descriptive/secondary — it smuggles a parametric dependence structure the house has not ratified. Issuer + onset-month clustering binding; ≥25 distinct onset-month blocks before any inferential sentence.
- **LHB-R10 (adopted doctrine).** The paper's §C "what does not count as honest N" list and §1 operating law (three independent axes, practitioner disagreement preserved, operator chooses the playbook) are ADOPTED as lobe doctrine and citable as `LHB-DOCTRINE`. The archetype cards (§D) are adopted as field-guide content for the admin page — display prompts, never stored authority states.
- **LHB-R11 (paper provenance).** Committed as-received. The transcript-collection assumption is already drifting (open PR #2371 collects earnings-call transcripts via free paths); nothing in this adjudication depends on transcripts either way.

---

## 2. Verdict table

| ID | Verdict | Grounds / amendment |
|---|---|---|
| A1 Falsifier packet | **ADOPT-AMENDED** | Two axes (LHB-R2); campaign axis struck; Tier-3 admin only; recost 1–2wk (provenance normalization across 4 engines with heterogeneous display dicts — not "mostly organizes shipped fields") |
| A2 Quarterly double-confirmation | **ADOPT-AMENDED (pilot)** | Gross-margin/pricing-power leg only until LHB-R6 lands; sector-level peers (11 GICS, ≥48 covered names/sector on the 1,484-name quarterly×PIT×sector intersection); per-fire peer-coverage n printed; receivables leg follows enrichment |
| A3 Delivery Waterfall | **ADOPT — build FIRST** | LHB-R1/R4. All inputs exist (~1,500 EDGAR names; EV/sales path for loss-makers). The refusal machinery IS the build (2–3wk honest, not a one-liner) |
| A4 Reinvestment-runway decay | **DEFER** | Annual-only, acquisition-contaminated incremental ratios (paper concedes); low marginal decision value vs A3; revisit after A3 ships |
| A5 Contracted-demand clock | **DEFER (data-blocked)** | Quarterly RPO/contract-liability fields don't exist; contract-liability tags ride LHB-R6 as accrual; surface waits for coverage census |
| A6 SEC hard-stop bus | **ADOPT-AMENDED, sequenced behind LHB-R7** | Rank demoted (false zero-cost claim); auto-`broken` = Item 1.03 only (LHB-R3); consumes expanded parquet, not the desk engine |
| A7 Owner-operator fracture | **DEFER** | 10b5-1 plan flags need per-filing Form 4 XML parsing (HEAVY; bulk TSV lacks them); post-transaction holdings not captured; paper itself ranked it 6th |
| A8 Capital-cycle rollover | **DEFER** | Subindustry peer groups don't exist (11 broad GICS sectors only); sector-level cohorts too coarse for capital-cycle claims |
| A9 Milestone integrity | **DEFER** | LLM-extraction-heavy, medium-low automation coverage by paper's own grade; revisit if a cheap milestone-extraction lane proves itself elsewhere |
| B1 Hardening ladder | **ADOPT (census/columns only)** | Hard/soft counts computable now from `material_8k_events` (49,402 rows; in-scope items); reversal leg waits on LHB-R7; era 2014+; slot NOT reserved (LHB-R5) |
| B2 Self-funding crossover | **ADOPT-AMENDED** | Core legs computable from quarterly store now; working-capital-timing exclusion waits on LHB-R6 fields; display-only, zero slots |
| B3 Share-supply state | **DEFER (HEAVY)** | `dilution_events` has ~1yr history, no dollar amounts, no capacity tracking; S-8 uncollected; ATM state machine is a program of its own. Passive accrual continues |
| B4 Index eligibility/announcement | **ADOPT (forward-only)** | `sp_index_changes` announce+effective dates accruing since 2026-06-08; no historical archive build; no eligibility probability (standing kill) |
| C1 All-listed satellite | **ADOPT-AMENDED** | LHB-R8: symbol-directory archival + CIK map chartered; per-stratum display only; pooled base rates forbidden |
| C2 Recurrent risk sets | **ADOPT (method-amended)** | LHB-R9: permutation primary, A–G descriptive |
| C3 Price-free EDGAR follow-through | **ADOPT (off-render lane)** | Genuinely additive, PIT-disciplined (original accessions, not restated Companyfacts), zero slots; schedule when an off-render lane frees up |
| C4 Corporate-action graph | **ADOPT (scoped)** | Extend existing bankruptcy/acquisition classifier + Form 25/15 accrual incrementally; full successor graph with S-4 consideration parsing DEFERRED (only 15 curated dead-name seeds today; special-situations forms history starts 2026-02) |
| Candidate-1 (peer-relative break) | **DENIED as framed** | LHB-R5: WA-R8 route + price-matched control arm + WA-R7 fence + FDR carve |
| Candidate-2 (soft→hard topology) | **DENIED as framed** | LHB-R5: WA-R8 route; era 2014+ |

---

## 3. Build charter (waves; display-tier throughout; no hypothesis slots spent)

- **LHB-W1 — the receipt.** A3 Delivery Waterfall v1: Detector-D-onset anchor, refusal-first (LHB-R4), admin Long-Hold page surface (new artifact path — `admin/long_hold.py` currently reads three JSON manifests and has no per-ticker detail). Ships alone so its refusal rates and coverage are visible before anything stacks on it.
- **LHB-W2 — honest data (off-render, display-nothing).** (a) LHB-R6 quarterly enrichment + backfill; (b) LHB-R7 8-K item expansion + backfill; (c) LHB-R8 symbol-directory archival collector. Three small PRs, no surfaces.
- **LHB-W3 — the packet and its feeds.** A1 two-axis packet (consuming A3 + falsifiers + clocks + funnel + capital allocation); A6 routing; A2 gross-margin pilot with locked coverage/base-rate report; B1 census columns; B2; B4 provenance fields; §D archetype cards as admin field-guide copy.
- **Unscheduled lanes:** C3, C4-scoped, C2 descriptive report — off-render research bandwidth as it frees.
- **Clocks:** LHB review 2026-10-15 (with funnel-stability 2026-10-01); B1/A2 base-rate censuses report before any WA-R8 slot conversation; G1 retest / Ruler-H unchanged ~2027-H2.

## 3.1 Answers to the paper's §H questions

| Question | Ruling |
|---|---|
| Approve A1 as canonical next build? | No — A3 first (LHB-R1); A1 is W3 of this charter |
| A3 anchored to Detector-D onset only at first? | Yes (LHB-R4) |
| Which two A2 sensors have quarterly coverage? | One: pricing-power (gross margin). Receivables waits on LHB-R6 |
| A6: reuse Special Situations codes directly or frozen artifact? | Neither — expanded `material_8k_events` parquet (LHB-R7); desk engine untouched |
| Ratify owner-operator scope before Form 4 work? | Moot — A7 deferred |
| Authorize B1 census while withholding the slot? | Yes, exactly so (LHB-R5) |
| Authorize C1 roster archival, FPI/non-S&P separate? | Yes, with pooled-rate prohibition (LHB-R8) |
| Keep the two slot candidates in recommended order? | Order noted; reservations denied; WA-R8 route for both |

---

## 4. Registry update (same PR)

Appended to `research/DO_NOT_REBUILD.md` §1: hypothesis-slot pre-reservation via standalone coverage census (bypassing WA-R8's cases+fingerprint+ruling gate) — FORBIDDEN. Second attempted end-run (LR docket round 1, this paper round 2); future external papers citing a census as slot-entitlement get summary REJECT.
