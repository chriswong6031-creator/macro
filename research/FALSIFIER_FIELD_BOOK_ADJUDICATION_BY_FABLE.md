# Falsifier Field Book — Adjudication (by Fable)

**Date:** 2026-07-12
**Source:** `research/FALSIFIER_FIELD_BOOK_FOR_FABLE.md` (external ChatGPT/Codex study, committed as-received; 24 dated break/false-alarm case timelines across the six hold archetypes, produced against the LHB charter's field-guide phase)
**Method:** 3-lane live-EDGAR date verification (Sonnet, 72+ accession checks + per-case numeric spot checks) + 4-probe Opus methodology red-team + repo observable-mapping lane + Fable adjudication.
**Program:** long-hold. This document is the calibration record the W3 builds (A1 packet, A2 pilot, A6 routing) must cite.

---

## 0. Verification verdict

**24/24 cases verified clean against live EDGAR.** Every load-bearing accession exists, every form type matches, every filing date is exact to the day — including two accepted-after-midnight edge cases (Allakos 2021-12-22, Immunomedics) and the Hertz dual-anchor (2020-05-22 press announcement vs 2020-05-26 Item 1.03 filing, both disclosed by the book). Numeric spot checks (UA gross-margin bp, VFC inventory spread, 2U FCF/share to the dollar, ULTA margin bp) reproduce exactly. The red-team independently reproduced all seven lead-day counts, both medians, the 5/12 coincident fraction, and the 37.5% mid-cap audit.

This is the highest-provenance external intake this repo has received. The paper's dates may be cited downstream without re-verification; its *interpretations* carry the amendments below.

## 1. Rulings (FFB-R1 … FFB-R9)

- **FFB-R1 (adoption).** The field book is ADOPTED as the calibration evidence base for the A1/A2/A6 contracts. The understanding-before-backtest requirement for those builds is SATISFIED. W3 of the LHB charter is UNBLOCKED, with thresholds entering only in the amended forms below.
- **FFB-R2 (honest coverage, adopted verbatim).** A1's coverage claim is pinned to the book's own arithmetic: the two-filing contract gave advance review in **7 of 12 true breaks (58%)**; **5 of 12 were visible only coincident with the break** (Hertz, Twilio, FibroGen, Allakos, US Silica). Display copy adopts: *"A6 is a hard-stop bus, not a lead generator."* No surface may imply fundamental falsifiers catch most breaks early.
- **FFB-R3 (false-alarm arm partition).** The 12-case false-alarm arm is partitioned before any statistic is cited: (a) **genuine de-escalations** — TXRH, ULTA, AMZN, FDX, ADSK, MU, FCX, AXSM, IMMU; (b) **refusal-driven non-adjudications** — CVNA, OKTA: the acquisition-scope guard *declined to adjudicate*; a refusal says nothing about survivability and never enters a recovery statistic; (c) **multi-year-challenge outlier** — TEVA (challenge open 1,929 days): excluded from every recovery-speed prior. Any cited recovery median must declare its clock basis: two-print-confirmation **552.5d** and first-recovery **514d** are printed together or not at all.
- **FFB-R4 (contracted-growth single-sensor demotion).** Both contracted-growth true breaks (Fastly, Twilio) break on the same RPO sensor — one with zero lead. The "~10% cumulative RPO decline" prior is DEMOTED to a single-sensor, single-lead observation (n=2, same mechanism); it may not be cited as an archetype threshold until a non-RPO contracted-growth true break is added to the book. The included-pair redundancy contradicts the book's own rejection logic (it rejected Peabody/Covia for duplication); noted for the next book revision. A5's deferral is reconfirmed independently by the mapping lane: quarterly RPO is not machine-readable historically (75-ticker annual store only).
- **FFB-R5 (anchor-selection rule, forward law).** Break anchor = the earliest **filed operating/financial print or legal terminal event** at which the registered thesis is objectively wrong. Discretionary management actions (layoffs, strategy reversals, guidance withdrawals without prints) are corroboration, never anchors. Under this rule the two longest non-terminal leads (Stitch Fix 210d — anchored to a layoffs/CEO-reversal 8-K; Fastly 207d) are treated as **upper bounds**. Honest lead summary for display: median 93.5d across all 12 true breaks, 162d across the 7 that led, with the two 200d+ leads flagged anchor-sensitive.
- **FFB-R6 (regime concentration).** Seven of the false-alarm onsets share the 2022 inflation/rate regime; their recoveries are conditioned on the same 2022→23 mean-reversion — effectively one macro draw, not ten independent ones (house time-confound law). Recovery statistics are regime-conditioned descriptions, never population base rates. The book's own §"limits" line (counts are not base rates) is elevated to a binding display rule.
- **FFB-R7 (50/50 construction bias, direction stated).** Thresholds tuned to separate a deliberately balanced 12/12 set will **over-fire** in a break-rare population. All book thresholds enter the A2 pilot as *review-opening* levels only (`challenged` ceiling, never `broken`), and the pilot's locked coverage/base-rate report — not the book — is the calibrator.
- **FFB-R8 (store-mapping deltas, binding on W3 specs).**
  1. A2 pilot legs computable now: gross-margin YoY (quarterly store; `gross_profit` null ~42%, consolidated-GAAP proxy caveat where the book used restaurant/segment margin); receivables/inventory/contract-liability legs activate when the LHB-R6 quarterly backfill lands (W2a).
  2. **New gap (logged):** quarterly `cfo`/`capex` are ~66% null structurally (many filers tag YTD-only on 10-Qs). B2's quarterly self-funding legs are demoted to annual grain until a YTD-differencing lane exists; a differencing enhancement to `backfill_edgar_quarterly.py` is authorized as future data work, unscheduled.
  3. **New gap (logged):** cash-runway per the book = cash + marketable securities; our store carries cash-only tags. Biotech runway reads (A9 archetype card) are materially understated until `MarketableSecuritiesCurrent`-class tags are added — a prerequisite stamped onto any future A9 revival.
  4. Diluted weighted-average shares are not collected; FCF/share uses basic-shares-outstanding proxy with a visible disclosure.
- **FFB-R9 (directional findings adopted as contract copy).** Adopted into the A1 archetype cards and A2/A6 routing rules: margin-compression *magnitude* does not separate breaks from false alarms (the peer/second-fact context does); inventory/RPO builds require a second independent demand-or-cash fact before `challenged`; Item 5.02 and Form 4 activity never fire alone; acquisition/scope changes produce `unverifiable`, never evidence either way.

## 2. What this changes for W3

The A1/A2/A6 builds proceed with: FFB-R2 coverage copy, FFB-R5 lead framing, FFB-R7 threshold posture, FFB-R8 store constraints, FFB-R9 card copy. No hypothesis slots are touched (nothing here is a statistical claim; LH-R12 budget remains 29/40). No DO_NOT_REBUILD rows: nothing was killed — two priors were demoted and two data gaps logged.

## 3. Provenance

Book committed as-received; misreadings corrected here, never edited there. Date verification lanes' full evidence lives in the session verification record (72+ live-EDGAR checks). The one register nit: TR-TB-1's two anchors (public announcement 2020-05-22, Item 1.03 2020-05-26) are both real and both disclosed — under FFB-R5 the *filed* 8-K is the anchor of record.
