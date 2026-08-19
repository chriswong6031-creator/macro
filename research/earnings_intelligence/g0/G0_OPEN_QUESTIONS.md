# G0 Open Questions

**Commission:** MASTERMIND GROK-G0  
**Stop rule:** research only. E2 remains the product next_action. FIF-2 remains stopped.

---

## MISSION

Audit Earnings Intelligence + FIF + market-reaction capabilities and produce the event-clock and historical casebook needed for a Post-Event Reinterpretation extension under the existing Earnings owner.

## WHAT I VERIFIED

- Ownership: Earnings owns event/document/claim; FIF owns filing facts/packets; neither is missing. No second store minted.
- Two-clock firewall exists on `company_event.v1` and FIF packet query cutoffs.
- Live AAPL `event_workspace.v1` generation `f709a0a6ec514282d5769e7d` is HTTP 200, `authority=context_only`, reaction `not_joined`, Q&A empty, consensus unlicensed, `basis_match=false`, lifecycle clocks **collapsed** to `generated_at`.
- Wire still forces transcript-only completeness; promotion forbids `market_reaction`.
- 154 winner-case YAML blocks parse; 60 earnings-relevant rows mapped as **candidates**.
- Matsumoto, Pronk, Roelofsen 2011 abstract opened: Q&A incrementally more informative than prepared remarks vs the PR.

## WHAT I COULD NOT VERIFY

- After-hours / premarket / open phase for any CEI source.
- Per-source `available_at` on the live workspace (fields absent).
- FIF-1R2 merge/Sol acceptance after this SHA.
- Any licensed consensus vintage.
- Any structured `qa_exchange.v1`.
- Full texts of Ball/Brown, Bernard/Thomas, DellaVigna/Pollet.
- Intraday AH prints.

## CODE / SOURCE RECEIPTS

See `G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md` §1–3. Live curl of the public R2 marker and AAPL workspace this session.

## OUTPUT ARTIFACTS

| File | Role |
|---|---|
| `G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md` | Native-source clocks vs G0 frontier |
| `G0_INFORMATION_FRONTIER_SPEC_DRAFT.md` | Draft objects; freeze still wins |
| `G0_REACTION_GEOMETRY_INPUT_MATRIX.md` | Display-only legs and fences |
| `G0_POST_EVENT_CASEBOOK.md` | 68 rows (8 estate + 60 historical) |
| `G0_ACADEMIC_RESEARCH_REVIEW.md` | Incremental-info literature |
| `G0_OPEN_QUESTIONS.md` | This file |

## ASSUMPTIONS

- Default for `HEADLINE_AVAILABLE`: same Exhibit 99.1, two receipts (alert vs full body), not a new document kind — unless product says otherwise.
- G0 does not jump the E2 queue.
- Winner-case `t0_hypothesis` is a research date, not `source_available_at`.

## PIT RISKS

1. Collapsed clocks on the live flagship (`observed_at == source_available_at == generated_at`).
2. Yahoo/yfinance estimate snapshots used as history (lookahead).
3. Using `latest_restated` FIF policy while rendering an earlier frontier.
4. Treating Wire `generated_at` as print time.
5. Filling missing options/revisions with zero.

## RIGHTS RISKS

- `blocked_rights` is non-mintable; do not display third-party transcript bodies on public Wire beyond the admitted excerpt grammar.
- Golden corpus is synthetic; do not cite as a real call.
- Academic PDFs not retrieved; do not paste copyrighted abstracts beyond what the opened pages already show.

## OPEN QUESTIONS

### Product / contract

1. **Does E2 still ship first?** Default **yes** (`WS:EARNINGS-INTELLIGENCE-OS` next_action). G0 is research overlay, not a reason to widen E2.
2. **Headline vs full release:** two receipts on one document, or a new `document_kind`? Default: two receipts.
3. **May `sources[]` on `event_workspace.v1` grow clocks without a schema bump?** Validator currently requires exact `WORKSPACE_KEYS` but source object keys are not a closed map in `validate_event_workspace` beyond list-ness. **UNKNOWN** whether adding `available_at` to a source object is additive-legal. Must be answered before implementation; do not silently extend.
4. **Is `FILING_RECONCILED` allowed to wait on FIF-7?** Default **yes**. Binding a 10-Q into CEI completeness without FIF is a second statement model — forbidden.
5. **Session phase helper:** which calendar (NYSE, listing MIC, issuer HQ)? Default: listing MIC; else `unknown`.

### Data

6. Who licenses consensus if beat/miss is ever to be legal? Until then the archetype “headline beat / deep weakness” stays **ungradeable**.
7. Will CEI ever hold intraday bars, or is first-close the finest legal reaction?
8. Can `equity_revisions` vintages be joined by `evt_cik…` without lookahead?
9. Is `collector_filing_unjoinable` on live AAPL still true on a later generation, or only on `f709a0a6ec514282d5769e7d`?

### Casebook

10. Which 10 of the 60 H-rows should be the **golden reinterpretation set** (full frontier fill, not just t0)? Suggested seed: NVDA 2023, APP 2024, CHWY 2022 (three rungs), PINS 2024, U 2021, CRWD 2023, PLTR 2024, AAPL live, BAC corpus, SMCI 2024 (with explicit later-accounting fence).
11. Where do Q&A-driven exemplars come from if the estate has no exchange objects? External transcript providers imply **rights**. Do not scrape them in a later wave without a rights registry.

### Authority

12. Opportunity-evidence already cased incorporation. Confirm G0 remains an Earnings **consumer** of that library, not a competing owner. This census assumes that (no conflict found).
13. Group-reads sympathy vs event-level mechanism (E8): G0 must not steal E8.

## RECOMMENDATIONS

1. Do **not** build a new store. Next product code is still E2.
2. Next *research* fill: per-source clocks on one workspace fixture (AAPL) without collapsing to `generated_at`.
3. Keep `basis_match=false` → no beat/miss as the only currently honest CEI archetype.
4. Treat winner cases as the historical geometry library; fill frontier cells as typed absences until receipts exist.
5. Open the remaining PEAD/attention PDFs before any promotion-bearing sentence.

## NO-BUILD / DO-NOT-INFER WARNINGS

- No new Earnings store. No second program key.
- No trading signal. No PEAD rebuild. No Prophet change.
- Do not infer causality from co-movement.
- Do not use present-day GEX to explain 2023 NVDA.
- Do not convert missing options/revisions to zero.
- Do not use LLM prose as a Q&A deflection label or a reinterpretation verdict (`DNR:KILL-LLM-ORIGINATION`, `DNR:KILL-LLM-FRAME-TAGS`).
- Do not start FIF-2 or FIF-7 from this PR.
- Do not edit E0/E1/E2 freeze documents (FIF landmine: those files are owned by the Earnings freeze PR).
- Do not calendar-gate risk (`DNR:KILL-CALENDAR-GATED-RISK`).
