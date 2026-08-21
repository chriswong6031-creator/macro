# IMCE-CELH-1 — CELH Cycle Autopsy (records-only) — V1

## Wave A1 of `WS:CYCLE-PATTERN-ISSUER-MECHANISM`, per `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §13

**Status:** Records-only research artifact. `candidate_not_registered` — this document performs no trial, computes no outcome, and grants no authority.
**Authority:** Research/display only. All ranking, gating, sizing, escalation, origination, and trading authority fields are FALSE. No authority is granted, implied, or reserved by this document.
**Commissioned by:** Fable (COO), after Sol's release of the IMCE-00 architecture freeze (PR #6127, merged `ec44ae7d1659` 2026-08-21T03:55Z), per freeze §13 wave A1.
**Descriptive-forever notice (D9):** CELH is descriptive forever. Nothing in this document, present or future, may enter an inferential sample or be cited as evidence of issuer-specific forecast skill. §9a of the frozen contract bars every historical CELH cell from any status above `DESCRIPTIVE`, unconditionally, regardless of count.
**Zero-outcome-computation attestation [G8-B1]:** This document computes, tabulates, or mentions **no** forward price change, return, drawdown, or path statistic after any event date. §5 (the fixed-telemetry EVENT record) ends at each event's own completed-bar state. Outcome fields attach to events only after the IMCE-03 (A4) criteria commit — a wave not authorized here.
**Binding spec:** `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §7.1, §9, §13, D4, D5; `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` §4; `agentos/handoffs/CYCLE-PATTERN-ISSUER-MECHANISM-2026-08-20.md` (G1/G2 receipts). This record does not redesign that architecture; it executes freeze §13 A1 verbatim: *"2018–2026 source chronology + three-clock timeline + epochs + fixed-telemetry EVENT record (dates and completed-bar states only) under ONE named construction + prospective observation registration. No model, no score, no p-value, and no forward-return/outcome computation of any kind — outcome fields attach to events only after the A4 criteria commit."*
**Date:** 2026-08-20/21.

---

# 0. Provenance note on this record's sourcing

The frozen freeze document (§7.1, §10 row G1) summarizes census findings — six epochs, wedge legs, a 13-month retro-disclosure exhibit, seven contradiction rows — but does not reproduce the underlying G1 packet's itemized, dated source list; that packet is not among the documents landed in this repository. Per this wave's commission, this record performs its own primary-source census directly against SEC EDGAR (`data.sec.gov`, 10 req/s, declared User-Agent `MacroDashboard-Research contact:research@macrodashboard.example (IMCE-CELH-1 wave A1)`) and CELH investor-relations exhibits filed with the SEC (both rights-`GO` per freeze §8), retrieved 2026-08-20. Every fact below carries its exact SEC accession/exhibit citation. Where this record's own construction (epoch boundaries E0, E3, E4, E5; four of the seven contradiction rows) is **not** a verbatim reproduction of G1's original packet, that is stated explicitly — see §7 Gaps in the closing section. The two facts G1's summary states as frozen rulings (E1 ends 2023-12-31, E2 starts 2024-01-01, both operating-clock) are treated as binding here, not re-derived.

CIK: `0001341766` (Celsius Holdings, Inc., Nasdaq: CELH), confirmed via `https://data.sec.gov/submissions/CIK0001341766.json`.

---

# 1. 2018–2026 source chronology

Every entry carries `event_time` (when the fact occurred on the operating clock — i.e., the reporting period the disclosure describes) and `available_at` (the date a market participant could first know it, i.e., the SEC filing date). All figures are GAAP consolidated revenue unless stated otherwise; retail-scanner figures are issuer-disclosed Circana citations (`issuer_claim_numeric` evidence class per D2, rights disposition `CIRCANA_ISSUER_DISCLOSED` GO_LIMITED per freeze §8).

## 1.1 Quarterly and annual revenue disclosures

| event_time (period) | available_at (filed) | Form / exhibit | Revenue (USD) | Source |
|---|---|---|---|---|
| Q1 2018 (end 2018-03-31) | 2018-05-10 | 10-Q | $12,059,976 | `sec.gov/.../s110007_10q.htm` |
| Q2 2018 | 2018-08-09 | 10-Q | $9,298,327 | `sec.gov/.../s111924_10q.htm` |
| Q3 2018 | 2018-11-08 | 10-Q | $16,565,316 | `sec.gov/.../s113852_10q.htm` |
| FY2018 (end 2018-12-31) | 2019-03-14 | 10-K | $52,603,986 | `sec.gov/.../s116616_10k.htm` |
| Q1 2019 | 2019-05-09 | 10-Q | $14,485,650 | XBRL `us-gaap:Revenues` |
| Q2 2019 | 2019-08-08 | 10-Q | $16,121,929 | XBRL `us-gaap:Revenues` |
| Q3 2019 | 2019-11-07 | 10-Q | $20,423,847 | XBRL `us-gaap:Revenues` |
| FY2019 | 2020-03-12 | 10-K | $75,146,546 | XBRL `us-gaap:Revenues` |
| Q1 2020 | 2020-05-12 | 10-Q | $28,184,889 | XBRL `us-gaap:Revenues` |
| Q2 2020 | 2020-08-06 | 10-Q | $30,037,227 | XBRL `us-gaap:Revenues` |
| Q3 2020 | 2020-11-12 | 10-Q | $36,839,149 | XBRL `us-gaap:Revenues` |
| FY2020 | 2021-03-11 | 10-K | $130,725,777 | XBRL `us-gaap:Revenues` |
| Q1 2021 | 2021-05-13 | 10-Q | $50,034,879 | XBRL `us-gaap:Revenues` |
| Q2 2021 | 2021-08-12 | 10-Q | $65,073,323 | XBRL `us-gaap:Revenues` |
| Q3 2021 | 2021-11-12 | 10-Q | $94,909,100 | XBRL `us-gaap:Revenues` |
| FY2021 | 2022-03-16 | 10-K | $314,271,559 | XBRL `us-gaap:Revenues` |
| Q1 2022 | 2022-05-10 | 10-Q | $133,388,000 | XBRL `us-gaap:Revenues` |
| Q2 2022 | 2022-08-09 | 10-Q | $154,020,000 | XBRL `us-gaap:Revenues` |
| **Q3 2022** (straddles PepsiCo effective date, see §1.2) | 2022-11-09 | 10-Q | $188,233,000 | XBRL `us-gaap:Revenues` |
| FY2022 | 2023-03-01 | 10-K | $653,604,000 | XBRL `us-gaap:Revenues` |
| Q1 2023 | 2023-05-09 (original) | 10-Q | $259,939,000 | XBRL `us-gaap:Revenues` — **no inventory-buildup caveat disclosed at original filing** |
| Q2 2023 | 2023-08-08 | 10-Q | $325,883,000 | XBRL `us-gaap:Revenues` |
| Q3 2023 | 2023-11-07 | 10-Q | $384,757,000 | XBRL `us-gaap:Revenues` |
| FY2023 | 2024-02-29 | 10-K | $1,318,014,000 | XBRL |
| Q1 2024 | 2024-05-07 | 10-Q + 8-K ex-99.1 | $355,708,000 (+37% YoY) | see §1.3 (retro-disclosure) |
| Q2 2024 | 2024-08-06 | 10-Q | $401,977,000 | XBRL |
| Q3 2024 | 2024-11-06 | 10-Q + 8-K ex-99.1 | $265,748,000 (**−31.0%** YoY vs $384.8M) | see §1.4 (sign-flip) |
| FY2024 | 2025-03-03 | 10-K | $1,355,630,000 | XBRL (Q4'24 derived: $332,197,000) |
| Q1 2025 | 2025-05-06 | 10-Q + 8-K ex-99.1 | $329,276,000 (−7.4% YoY) | see §1.5 |
| Q2 2025 | 2025-08-08 | 10-Q | $739,259,000 (post-Alani close) | XBRL |
| Q3 2025 | 2025-11-06 | 10-Q + 8-K ex-99.1 | $725,106,000 | see §1.6 (base-effect) |
| FY2025 | 2026-03-02 | 10-K | $2,515,269,000 | XBRL (Q4'25 derived: $721,628,000) |
| Q1 2026 | 2026-05-07 | 10-Q + 8-K ex-99.1 | $782,615,000 (+138% YoY, Alani/Rockstar-driven) | see §1.7 (load-in) |
| Q2 2026 | 2026-08-06 | 10-Q + 8-K ex-99.1 | $817,925,000 | see §1.8 |

All quarterly figures 2018–2023 sourced from `us-gaap:Revenues`; 2023–2026 comparatives additionally cross-checked against `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` (both via `data.sec.gov/api/xbrl/companyconcept/CIK0001341766/...`), values agree exactly at every overlap point (e.g. Q3 2024 $265,748,000 reported identically under both tags across the 2024-11-06 and 2025-11-07 filings).

## 1.2 Structural/distribution events

| event_time | available_at | Event | Source |
|---|---|---|---|
| 2022-08-01 | 2022-08-01 | PepsiCo long-term US distribution agreement + $550M convertible-preferred investment (~8.5–11% stake), effective same day | 8-K accession `0001829126-22-014925`, ex-99.1: *"Celsius & PepsiCo Announce Long-Term Distribution Agreement and Investment"* |
| 2025-02-20 | 2025-02-20 | Membership Interest Purchase Agreement signed to acquire Alani Nutrition LLC ("Alani Nu") from Congo Brands | 8-K accession `0001341766-25-000018` (items 1.01/2.02/3.02/7.01/9.01) |
| 2025-04-01 | 2025-04-01 | Alani Nu acquisition **closed** | 8-K accession `0001341766-25-000069`: *"Completion of the Acquisition of Alani Nutrition LLC. As previously reported, on February 20, 2025, Celsius Holdings, Inc. ... entered into a Membership Interest Purchase Agreement ... with Alani Nutrition LLC"* |
| 2025-08-28 | 2025-08-28 | Rockstar Energy (US/Canada) acquisition closed | Cross-referenced in 8-K ex-99.1 filed 2026-05-07: *"Celsius Holdings acquired the Rockstar Energy brand in the U.S. and Canada on August 28, 2025."* (original closing 8-K not independently re-fetched this wave — typed gap, §7) |

## 1.3 Q1 2023 pipeline-fill retro-disclosure (event_time / available_at split, 13-month lag)

- **event_time:** Q1 2023 (period 2023-01-01 → 2023-03-31).
- **First disclosure of the raw figure:** 10-Q filed 2023-05-09 (`available_at` for the bare $259,939,000 revenue number). This original filing carries **no inventory-buildup caveat**.
- **Retro-disclosure of the mechanism (`available_at`):** 2024-05-07, 8-K accession `0001341766-24-000031`, exhibit `ex991111q2024.htm` (Q1 2024 earnings release), verbatim quote:

  > "...offset in part by inventory movements within our largest distributor where first quarter 2024 inventory days on hand declined versus the fourth quarter resulting in an approximate $20 million impact, **while first quarter 2023 revenue benefited from an inventory buildup of approximately $25 million**. Ongoing inventory fluctuations may be expected in subsequent quarters because our largest distributor constituted 62% of our total North American sales during the first quarter of 2024."

- **Lag:** 2023-03-31 (event_time, quarter end) → 2024-05-07 (available_at, mechanism disclosed) = **13.2 months**. A decision-time read of Q1 2023 growth (originally reported +94.9% YoY vs Q1 2022's $133.388M) structurally could not net the ~$25M buildup — it was not knowable until 13 months later. This is the canonical cautionary exhibit named in freeze D4.

## 1.4 Q3 2024 sign-flip (retail vs. revenue)

8-K accession `0001341766-24-000095`, exhibit `ex9913q2024.htm`, filed 2024-11-06 (available_at). event_time = Q3 2024 (period ended 2024-09-30). Verbatim:

> "For the three months ended Sept. 30, 2024, revenue was approximately $265.7 million, compared to $384.8 million for the three months ended Sept. 30, 2023. Revenue from our largest distributor declined $123.9 million... primarily driven by the distributor's inventory optimization. ... **Retail sales of Celsius in total U.S. MULO Plus with Convenience grew by 7.1% year over year in the third quarter of 2024 as reported by Circana for the last-thirteen-week period ended Sept. 29, 2024.**"

Revenue: $265.7M vs $384.8M = **−31.0%** YoY. Retail scanner (Circana): **+7.1%** YoY. Same quarter, opposite sign — the wedge named `mechanism_hypothesis`-class in freeze §7.1.

## 1.5 Q1 2025

8-K accession `0001341766-25-000081`, ex-99.1, filed 2025-05-06. event_time = Q1 2025 (ended 2025-03-31, the last full quarter **before** the Alani close on 2025-04-01). Verbatim:

> "While revenue was down year over year, retail scanner data showed a 2% increase in dollar sales for the thirteen weeks ended Mar. 30, 2025... **CELSIUS® retail sales declined 3% year over year** with a dollar share of 10.9%... **Alani Nu® retail sales increased 88% year over year**, reaching a 5.3% dollar share... Combined, the Celsius Holdings portfolio captured a 16.2% dollar share."

Revenue $329.276M vs Q1 2024 $355.708M = −7.4% YoY.

## 1.6 Q3 2025 base-effect

8-K accession `0001341766-25-000138`, ex-99.1, filed 2025-11-06. event_time = Q3 2025 (ended 2025-09-30). Verbatim:

> "CELSIUS brand revenue grew 44% in the third quarter compared to the same period last year. The CELSIUS brand's third quarter 2025 U.S. scanner growth rate was 13%..."

## 1.7 Q1 2026 Alani distributor-transition load-in

8-K accession `0001341766-26-000035`, ex-99.1, filed 2026-05-07. event_time = Q1 2026 (ended 2026-03-31). Verbatim:

> "The increase reflected the acquisitions of Alani Nu on April 1, 2025, and Rockstar Energy on August 28, 2025. **Alani Nu achieved record sales of approximately $368.1 million in the first quarter of 2026, benefiting from significant ongoing customer demand as well as increased orders from our largest distributor as Alani Nu moved out of its prior distribution system and into the PepsiCo distribution system.** ... CELSIUS brand revenue increased approximately 6% in the first quarter of 2026... Retail sales of the Celsius Holdings portfolio (CELSIUS, Alani Nu and Rockstar Energy) in U.S. tracked channels (MULO+ w/C) increased 29.8%... CELSIUS brand retail sales increased 6%... Alani Nu retail sales increased 100.0%... Rockstar Energy retail sales decreased 13% year over year."**

Per freeze §4–6 [G8-M8], the causal attribution that this "increased orders" language repeats the 2022–23 pipeline-fill signature is an `mechanism_hypothesis`-class record — a source-backed hypothesis with a competing explanation (genuine distributor-transition stocking of a *new* logistics pipeline is mechanically different from a *demand-side* pull-forward), never an observed fact. **This document does not assert it repeated; it registers the hypothesis and its named falsifier in §4.**

## 1.8 Q2 2026

8-K accession `0001341766-26-000047`, ex-99.1, filed 2026-08-06. event_time = Q2 2026 (ended 2026-06-30). Verbatim:

> "**CELSIUS brand revenue decreased by approximately 11.7% in the second quarter of 2026** compared to the same period last year, reflecting increased trade and promotional investment, **shipment timing related to inventory rebalancing**, softness in the club channel, a planned moderation in innovation activity during the period, and **SKU optimization initiatives** implemented in conjunction with the integrat[ion of Alani Nu and Rockstar Energy]."

---

# 2. Three-clock timeline (D4)

Per freeze D4, every observation carries a stamp on one or more of three clocks: **operating** (when the underlying business fact occurred), **accounting-translation** (when GAAP recognition/restatement converts the fact into a reported number), and **market-recognition** (`available_at` — when a market participant could first read it). This record's chronology (§1) already tags every entry with `event_time` (operating/accounting-translation, since GAAP quarters are defined on the operating calendar) and `available_at` (market-recognition). Two worked examples make the three-clock separation concrete:

| Fact | Operating clock | Accounting-translation clock | Market-recognition clock |
|---|---|---|---|
| Q1 2023 ~$25M inventory buildup | Jan–Mar 2023 (goods physically moved into distributor inventory) | Reflected inside the Q1 2023 GAAP revenue print filed 2023-05-09 (recognized as ordinary revenue, no separate line item) | **2024-05-07** — the buildup's existence as a *distinct mechanism* was not knowable until the Q1 2024 comparative-quarter commentary named it |
| Alani Nu distributor-system migration | Ongoing through Q1 2026 (physical inventory moving from the prior distribution system into PepsiCo's system) | Consolidated into Alani Nu's $368.1M Q1 2026 segment revenue, filed 2026-05-07 | 2026-05-07 (same filing — no separate lag here; contrast with the Q1 2023 case, where the mechanism's *description* lagged its *number* by 13 months) |

The load-bearing lesson: **a number's `available_at` and its causal explanation's `available_at` can differ.** The Q1 2023 revenue figure itself was known 2023-05-09; the *fact that it was inflated by a pipeline fill* was not known until 2024-05-07. Any decision-time read taken between those two dates would have priced Q1 2023 as clean organic growth. This asymmetry is why the epoch boundaries in §3 are explicitly operating-clock, not recognition-clock, boundaries.

---

# 3. Epochs (E0–E5)

**Clock-stamp notice [G8-M2], stated per freeze §7.1 requirement:** every boundary below is an **operating-clock** boundary — valid for describing when the underlying business regime changed. E1's end (2023-12-31) and E2's start (2024-01-01) are **FROZEN** exactly as ruled in freeze §7.1/§9a: two boundary amendments, both operating-clock. E0's start, E1's start, E2's end, and E3/E4/E5's boundaries are **this wave's own construction**, anchored to verified primary-source structural events (§1.2) — not a verbatim reproduction of G1's original epoch table, which is not among the documents landed for this wave (see §7 Gaps). **Any future partition of a recognition-outcome statistic must use recognition-clock (`available_at`) boundaries instead of these** — an epoch dated to an operating-clock date no market participant could know (e.g. E2's 2024-01-01, vs. its first partial recognition on 2024-05-07 and full recognition on 2024-11-06) is look-ahead if used to slice an outcome series. No outcome series exists in this document, so the boundaries below are used descriptively only.

| Epoch | Operating-clock window | Structural anchor | Wedge-measurable? |
|---|---|---|---|
| **E0** | 2018-01-01 → 2022-07-31 | Pre-PepsiCo, organic/legacy distribution build (revenue $12.1M Q1'18 → $154.0M Q2'22) | **No** — typed absence `not_available_for_date`; no comparable 13-week retail-scanner series is disclosed for this window in the sources reviewed this wave. Not backfillable. |
| **E1** | 2022-08-01 → **2023-12-31** [FROZEN, freeze §7.1] | PepsiCo distribution agreement effective 2022-08-01; national scale-up; FY2022 $653.6M → FY2023 $1,318.0M (+101.7%) | **No** — same typed-absence rule; E0/E1 "cannot support wedge measurement" per freeze §7.1 verbatim. |
| **E2** | **2024-01-01** [FROZEN, freeze §7.1] → 2025-03-31 | Distributor destocking / channel correction; Q3 2024 trough (−31.0% revenue vs +7.1% retail, §1.4); ends the day before the Alani close | **Yes** — Q1 2024 (§1.3/§1.1), Q3 2024 (§1.4) both disclose comparable 13-week retail-scanner windows alongside revenue. |
| **E3** | 2025-01-01 → 2025-03-31 *(overlaps E2's tail by this wave's construction — see note below)* | Single-brand (pre-Alani) stabilization quarter; Q1 2025 revenue −7.4% YoY vs portfolio retail +2% (§1.5) | **Yes** — §1.5. |
| **E4** | 2025-04-01 → 2025-08-27 | Alani Nu integration ramp, post-close, pre-Rockstar | **Yes, per-brand** — first per-brand retail split available in the Q1 2025 release (§1.5, filed just before this window opens) and continuing into Q3 2025 (§1.6). |
| **E5** | 2025-08-28 → present (2026-08-20) | Multi-brand portfolio distribution ramp: Rockstar close, Alani's migration into the PepsiCo distribution system (§1.7), concurrent SKU optimization / shipment-rebalancing language (§1.8) | **Yes, per-brand** — Q1 2026 (§1.7) and Q2 2026 (§1.8) both disclose CELSIUS/Alani Nu/Rockstar retail splits alongside consolidated and brand-level revenue. |

**Boundary note:** E2 and E3 overlap in this wave's construction (E2 runs through 2025-03-31 while E3 begins 2025-01-01) because the frozen G1 packet did not hand this wave an exact E2 end-date, and Q1 2025 data (§1.5) plausibly reads as either "still destocking" (revenue still down YoY) or "early stabilization" (retail scanner has turned positive at the portfolio level). This wave resolves the ambiguity by presenting E3 as a *candidate* sub-partition rather than collapsing it into E2 — flagged explicitly as an open construction question for A2/a future wave, not silently resolved. Per freeze law (§4–6), this overlap itself does not smuggle in a statistical claim: no cell, count, or promotion status is computed over either window in this document.

Satisfying `research/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` §2's bar rule: CELH is `DESCRIPTIVE` at 0 historical cells "by rule, not by count" [A1] — nothing above changes that; these epochs are descriptive partitions of the chronology, not trial cells.

---

# 4. Phase-state narrative (D5 vocabulary only)

Per freeze D5, CELH's mechanism-local descriptive state vector uses exactly four terms: `channel_destocking`, `shipment_rebalance`, `assortment_reset`, `distribution_ramp`. **Every assignment below is `mechanism_hypothesis`-class evidence [G8-M8]** — a source-backed causal attribution, never `derived_deterministic` — and carries a mandatory named falsifier and a competing explanation, per freeze §4–6. None of these assignments computes, implies, or requires a forward-return figure.

| Epoch | D5 phase-state assigned | Source-backed grounds | Named falsifier | Competing explanation |
|---|---|---|---|---|
| E0 | *(none — pre-mechanism-scope)* | No D5 term applies; typed `not_applicable`. Pre-PepsiCo distribution had not yet reached the scale at which pipeline-fill/destocking dynamics are disclosed in issuer commentary. | N/A | N/A |
| E1 | `distribution_ramp`, with an undisclosed-at-the-time `shipment_rebalance` component later revealed by §1.3 | PepsiCo agreement (§1.2) is unambiguous `distribution_ramp` evidence (`issuer_claim_directional`, upgraded to `observed_numeric` for the revenue trajectory). The retro-disclosed $25M buildup (§1.3) is `mechanism_hypothesis`-class evidence that a `shipment_rebalance` (inventory-level, not demand-level, growth) contributed to E1's headline. | If the buildup had instead reflected genuine incremental end-consumer demand pulled forward (not distributor inventory), the subsequent 2024 destocking magnitude would not correlate with the 2023 buildup magnitude — a test this record does not run (would require a forward statistic, out of scope). | The $25M could alternatively be measurement noise in distributor-reported inventory days-on-hand rather than a true pipeline fill; the issuer's own language ("benefited from an inventory buildup") is `issuer_claim_numeric`, not an independently audited figure. |
| E2 | `channel_destocking` | Direct issuer language: "inventory movements... where... inventory days on hand declined," "distributor's inventory optimization" (§1.3, §1.4); revenue −31.0% at trough (§1.4) against positive retail scanner (+7.1%) is the textbook destocking signature (sell-in falling while sell-through holds). | If a genuine demand-side deceleration were the true driver, retail scanner sales would also have fallen (or comparably decelerated) — they did not; they rose. This is the falsifier the sign-flip (§1.4, CX-1 below) exists to record. | Alternative: broad-based promotional/billback normalization (gross margin fell 440bp in Q3 2024, per §1.4's source) independent of any inventory-level story — the margin move is consistent with either explanation and does not discriminate between them. |
| E3 | `shipment_rebalance` | "Retail scanner data showed a 2% increase... while revenue was down year over year" (§1.5) — sell-in and sell-through have not yet converged, consistent with an ongoing rebalancing rather than either a completed destocking or a resumed ramp. | If E3 were actually still `channel_destocking`, per-brand retail should be flat-to-negative across both CELSIUS and Alani; instead CELSIUS retail is −3% while Alani Nu retail is +88% (§1.5) — a genuinely mixed signal, not uniform destocking. | Alternative: this could equally be read as `assortment_reset` if the CELSIUS-vs-Alani divergence reflects deliberate SKU/portfolio-mix shifting rather than inventory-timing effects; the sources reviewed this wave do not disambiguate. |
| E4 | `distribution_ramp` | Alani Nu close (2025-04-01, §1.2) mechanically adds a new brand into Celsius's distribution infrastructure. | N/A within this wave's source set — no contradicting per-brand data was located for this narrow window (pre-Q3'25 release). | N/A |
| E5 | `distribution_ramp` (Rockstar addition, Alani's PepsiCo-system migration, §1.7) **and concurrently** `shipment_rebalance` + `assortment_reset` (Q2 2026, §1.8) | Direct issuer language, verbatim in §1.8: "shipment timing related to inventory rebalancing" (`shipment_rebalance`) and "SKU optimization initiatives" (`assortment_reset`) — both appearing in the SAME quarter as an active `distribution_ramp` (Rockstar/Alani integration). | If E5 were purely `distribution_ramp` with no rebalancing, CELSIUS brand revenue should not have independently declined −11.7% (§1.8) in the same quarter the portfolio was still integrating two new brands; the decline is the falsifier for a "pure ramp, no friction" reading. | Alternative: the −11.7% CELSIUS decline could be pure `channel_destocking` recurrence rather than `shipment_rebalance` — the issuer's own language names "shipment timing" specifically, which this record treats as the stronger textual match, but the two D5 terms are adjacent and not perfectly separable from the language available. |

## 4.1 Seven contradiction/counterexample rows

Three are named verbatim in freeze §7.1 (CX-1, CX-2, CX-3); four are this wave's own primary-source construction, not a reproduction of G1's original seven (flagged, §7 Gaps).

| # | Provenance | Row |
|---|---|---|
| **CX-1** | freeze §7.1 (named) | Q3 2024 sign-flip: retail **+7.1%** vs revenue **−31.0%**, same 13-week window (§1.4). |
| **CX-2** | freeze §7.1 (named) | Failed bounce: Q3 2025 CELSIUS brand revenue **+44%** (base-effect against the 2024 trough) → Q2 2026 CELSIUS brand revenue **−11.7%** (§1.6, §1.8). |
| **CX-3** | freeze §7.1 (named), `mechanism_hypothesis`-class | Alani Q1 2026 distributor-transition load-in ("increased orders from our largest distributor as Alani Nu moved out of its prior distribution system and into the PepsiCo distribution system," §1.7) — an `mechanism_hypothesis` that this echoes the 2022–23 pipeline-fill signature, **not an observed fact**. |
| **CX-4** | this wave (A1) | Q1 2023 ~$25M inventory buildup (§1.3): the *original* Q1 2023 10-Q (filed 2023-05-09) disclosed the revenue number with **no** buildup caveat; the caveat appeared only 13.2 months later. A decision-time read at any point in that window would have treated Q1 2023 as clean organic growth. |
| **CX-5** | this wave (A1) | Q1 2024 wedge points the **opposite** direction from CX-1: revenue **+37%** while retail scanner **+72.1%** (§1.1/§1.3's release) — revenue *understated* sell-through strength that quarter, the mirror image of CX-1. |
| **CX-6** | this wave (A1) | Q1 2025 per-brand divergence concealed inside one consolidated headline: portfolio revenue −7.4% YoY, while CELSIUS retail −3% and Alani Nu retail **+88%** moved in opposite directions at the brand level (§1.5). |
| **CX-7** | this wave (A1) | Q1 2026 three-brand divergence inside a single `distribution_ramp` epoch (E5): CELSIUS organic **+6%**, Alani Nu retail **+100.0%**, Rockstar retail **−13%** (§1.7) — demonstrating that a single epoch-level phase-state label is not uniform across a multi-brand portfolio. |

---

# 5. Fixed-telemetry EVENT record

**Named construction (frozen, D3.1 / contract §4):** classic **MACD(12, 26, 9)** applied to **2-week bars**, the house stock-technicals default — `engine/technicals.macd_hist` semantics (`ema12 = close.ewm(span=12, min_periods=12).mean(); ema26 = close.ewm(span=26, min_periods=26).mean(); macd = ema12 - ema26; signal = macd.ewm(span=9, min_periods=9).mean(); hist = macd - signal`), fed the 2-week bar series. This is the OTHER house 2W construction than `engine/canon.py`'s `w2_bull` (RSI-MACD, params 14/14/60/5, used by the confluence contract) — the contract (§4) explicitly names this one as `R_t`'s fixed-anchor field, and the construction-naming law (freeze D3.1) requires every recognition field to name which construction it binds to. **This record names it: classic 12-26-9, never the RSI-MACD.**

2-week bars are built with the house canon convention (`engine/canon.py:_resample_weekly`, rule `"2W-FRI"`): a calendar-anchored resample taking the last daily close in each Friday-ending 2-week bucket. This is the same bucketing rule the canon uses for `w2_bull` — only the indicator parameters differ.

## 5.1 Canonical price store

- **Store path:** `data/yahoo/CELH.parquet` (via `lib.store.read('yahoo', 'CELH')`).
- **Extraction method (sparse worktree):** `git show origin/main:data/yahoo/CELH.parquet` into a scratch file (this worktree omits `data/` — sparse checkout).
- **SHA-256 of the extracted bytes:** `73979534198cb0b173cbfe107aa8ca125a5a8ccaa95b7b39fc566ab8353525e2`
- **Origin/main commit last touching this path:** `5a6f02a75675d4f29f658dcf3eb340cd6fb8e770` (2026-08-12).
- **Coverage:** 4,921 daily bars, 2007-01-22 → 2026-08-12 — matching G2's receipted coverage exactly ("4,921 daily bars 2007-01-22..2026-08-12," per the handoff), confirming this record reads the identical store version G2 read.
- **Warm-up:** classic MACD(12,26,9) on 2W-FRI bars needs `26 + 9 = 35` bars of `min_periods` before the signal line is defined; the first fully-warm bar in this store is **2008-05-02**. No event before this date is reported; this is warm-up, not a data gap (consistent with freeze §7.1's "no events before ~2010 is MACD warm-up, not a gap [G8-v5]" disclosure about G2's tape — see §5.3 for the one discrepancy this creates).
- **Completed-bar rule:** the store's daily coverage ends 2026-08-12 (a Wednesday); the `2W-FRI` bucket ending 2026-08-14 (the next Friday) is therefore an **incomplete** bar (missing Thu/Fri) and is excluded from the event record below. No cross event falls in that bucket, so this exclusion is moot for the results but is stated for completeness.

## 5.2 Completed-bar crossover events (classic 2W MACD(12,26,9), full available history)

State column values are the indicator's own reading **at** the completed bar named — no value in this table reflects any bar after the named date.

| Event date (completed 2W-FRI bar) | Direction | MACD line | Signal line | Histogram |
|---|---|---|---|---|
| 2008-05-02 | bullish | −1.4269 | −1.5606 | +0.1337 |
| 2009-11-27 | bearish | +0.4104 | +0.4500 | −0.0396 |
| 2011-02-18 | bullish | −0.3134 | −0.3140 | +0.0005 |
| 2013-01-04 | bearish | −0.0170 | −0.0167 | −0.0003 |
| 2013-02-01 | bullish | −0.0166 | −0.0168 | +0.0002 |
| 2013-02-15 | bearish | −0.0169 | −0.0168 | −0.0001 |
| 2013-03-01 | bullish | −0.0159 | −0.0166 | +0.0007 |
| 2013-12-20 | bearish | +0.0093 | +0.0100 | −0.0007 |
| 2014-03-14 | bullish | +0.0221 | +0.0107 | +0.0115 |
| 2014-07-04 | bearish | +0.0307 | +0.0311 | −0.0003 |
| 2015-02-13 | bullish | +0.0117 | +0.0042 | +0.0075 |
| 2015-09-11 | bearish | +0.1329 | +0.1487 | −0.0158 |
| 2016-05-06 | bullish | +0.0524 | +0.0474 | +0.0050 |
| 2016-07-15 | bearish | +0.0553 | +0.0567 | −0.0013 |
| 2016-12-02 | bullish | +0.0311 | +0.0288 | +0.0022 |
| 2017-07-28 | bearish | +0.1435 | +0.1469 | −0.0034 |
| 2017-08-25 | bullish | +0.1580 | +0.1484 | +0.0096 |
| 2017-12-01 | bearish | +0.2068 | +0.2070 | −0.0003 |
| **2019-03-22** | **bullish** | −0.0616 | −0.0731 | +0.0115 |
| **2019-09-20** | **bearish** | −0.0230 | −0.0120 | −0.0110 |
| **2019-11-29** | **bullish** | −0.0202 | −0.0333 | +0.0130 |
| **2020-04-03** | **bearish** | +0.0759 | +0.0783 | −0.0024 |
| **2020-05-15** | **bullish** | +0.1034 | +0.0784 | +0.0250 |
| **2021-08-20** | **bearish** | +3.9111 | +3.9663 | −0.0552 |
| **2021-09-03** | **bullish** | +4.2660 | +4.0262 | +0.2397 |
| **2021-11-26** | **bearish** | +4.2229 | +4.5381 | −0.3152 |
| **2022-07-08** | **bullish** | +0.5513 | +0.2922 | +0.2591 |
| **2023-02-03** | **bearish** | +3.0024 | +3.1061 | −0.1037 |
| **2023-05-12** | **bullish** | +2.3863 | +2.2390 | +0.1473 |
| **2023-11-24** | **bearish** | +6.7804 | +6.8384 | −0.0580 |
| **2024-03-01** | **bullish** | +6.7485 | +5.8279 | +0.9206 |
| **2024-06-21** | **bearish** | +8.5093 | +9.1514 | −0.6421 |
| **2025-03-28** | **bullish** | −7.3482 | −7.6557 | +0.3074 |
| **2025-12-05** | **bearish** | +2.1049 | +2.5908 | −0.4860 |

Bold rows fall inside the 2018–2026 chronology window (§1). Full-history total: **34 events** (17 bullish, 17 bearish), 2008-05-02 → 2025-12-05. **No event, value, or state after any listed date is reported.** No forward return, drawdown, or path statistic of any kind was computed to produce this table.

## 5.3 Cross-check against G2's quarantined tape (disclosure only, per freeze §9)

Freeze §10 (row G2) and §7.1 receipt the prior census lane's own descriptive tape: "16 completed-bar 2W bullish crosses 2011–2025, 1 two-bar whipsaw, 7/16 non-positive at +63td." That tape is quarantined unregistered design-context evidence — no display, no citation of its outcome fields, per freeze §9. This wave's construction was fixed independently from the frozen contract §4 language, then applied to the same store; the following are **date/count-level** cross-checks only (never outcome-level, since G2's +63td path fields are quarantined and were never read by this wave):

- **Bullish-cross count, 2011–2025 window:** this record's reconstruction yields exactly **16** bullish crosses (2011-02-18 through 2025-03-28) — matching G2's receipted count exactly. This is strong corroboration that the two lanes used the same construction and the same store version.
- **Whipsaw:** G2 names exactly one two-bar whipsaw in that window. This record's reconstruction contains **multiple** short-latency reversal pairs in 2011–2025: two 2-bar candidates (2013-01-04 bearish → 2013-02-01 bullish; 2017-07-28 bearish → 2017-08-25 bullish) and two 1-bar candidates (2013-02-01 bullish → 2013-02-15 bearish; 2021-08-20 bearish → 2021-09-03 bullish). This record cannot identify which specific pair G2's "1 two-bar whipsaw" refers to, since G2's own dated event list is not reproduced in the landed documents available to this wave — **typed gap**, not resolved here.
- **Pre-2010 events:** freeze §7.1 states G2's tape shows "no events before ~2010... MACD warm-up, not a gap." This record's reconstruction contains **two** pre-2010 events (2008-05-02 bullish, 2009-11-27 bearish) that would contradict a literal "zero events before 2010" reading, though both sit inside this record's own warm-up disclosure window (§5.1) and are flagged, not asserted as reliable signal. **Typed gap**, not resolved here — possibly explained by a stricter warm-up convention in G2's original construction that this wave did not reproduce exactly.

---

# 6. Prospective observation registration

This section is **declarative registration only — it creates no ledger rows, no `declared_budget` trial-ledger entries, and no CPI truth rows.** It names what will be observed prospectively, per `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` §4's frozen `R_t` field list, and the cadence/attachment rule from that contract's §13 and §15a.

## 6.1 Fields to be observed (verbatim from the frozen contract §4, `R_t`)

- Canonical relative-strength fields.
- Weekly state.
- **Fixed-anchor 2W MACD line/signal/histogram and closed-bar flag** — the exact construction fixed and demonstrated in §5 of this record (classic 12-26-9 on 2W-FRI bars).
- Revisions only from captured historical snapshots (never current-snapshot backfill, per contract §6 item 10).
- Positioning only on knowable/publication dates.
- Event reaction fields frozen by a canonical event ID.

Alongside `R_t`, the mechanism vector `M_t` (contract §4) will be drawn from source-backed evidence per §1's chronology methodology (SEC EDGAR filings + CELH IR exhibits, both rights-`GO`), with the ordinal-sensor law applied wherever a directional-only field (not applicable to CELH's own disclosures, which are cardinal) would otherwise be miscast as cardinal.

## 6.2 Cadence

Per contract §13 (Prospective law), unchanged and not amended by this record:

- Nightly is the sole forward-ledger advancer.
- First observation wins for a cutoff/episode.
- No historical backfill into the prospective cohort.
- Corrections append and supersede; they never rewrite the original decision-time packet.
- Market and mechanism outcomes accrue separately.
- Live and backtest badges never blend.
- Two separate counters are maintained: `n_blocks_hist` and `n_blocks_prosp`.

## 6.3 Attachment rule

Outcome fields — any forward price, return, drawdown, or path statistic keyed to an event date in §5.2 — **attach to that event only after the IMCE-03 (A4) criteria commit** (freeze §13, contract §15a's two-commit discipline: the criteria commit strictly precedes the runner/outcome commit). No such commit has occurred; A4 is not authorized by this wave. Until it is, every event in §5.2 remains a bare completed-bar state with **zero attached outcome of any kind** — exactly the fence this record was commissioned to hold.

## 6.4 Minimum prospective share

Per contract §13 [A24], "a preregistered minimum prospective share is required before any promotion" — value TBD at registration (IMCE-03), not set by this record. This record does not set or imply a value.

---

# 7. Gaps (typed, not resolved here)

- **Epoch table (§3):** E0's start, E1's start, E2's end, and E3/E4/E5's exact boundaries are this wave's own construction from primary-source structural events, not a verbatim reproduction of G1's original epoch table (that packet is not among the documents landed for this wave). Only E1's end (2023-12-31) and E2's start (2024-01-01) are reproduced as frozen rulings from freeze §7.1/§9a.
- **Contradiction rows CX-4 through CX-7 (§4.1):** constructed by this wave from primary sources, not a reproduction of four of G1's original seven rows (only CX-1/CX-2/CX-3 are named verbatim in the landed freeze text).
- **G2 whipsaw identity (§5.3):** this wave cannot identify which specific short-latency reversal pair G2's "1 two-bar whipsaw" refers to; G2's dated event list is not reproduced in the landed documents.
- **Pre-2010 event discrepancy (§5.3):** this wave's reconstruction contains two pre-2010 events; freeze §7.1 states G2's tape shows none before ~2010. Not resolved — possibly a warm-up-convention difference between this wave's construction and G2's original.
- **Rockstar Energy acquisition (§1.2):** sourced from a cross-reference inside a later (2026-05-07) press release, not from Rockstar's own original closing 8-K, which was not independently fetched this wave.
- **Retail-scanner series for E0/E1 (§3):** not located in the sources reviewed this wave; typed absence (`not_available_for_date`), not asserted as nonexistent.
