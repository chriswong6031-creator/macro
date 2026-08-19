# GD-1 event timeline

Clocks are observation vs authority, separately. End state of this wave:
**REPAIR_UNRESOLVED_AT_CUTOFF** (2026-08-19). Do not truncate at a selloff low.

`known_at` that is missing is labeled. Anticipatory language is refused on those rows.

## Precursor (already true before 2026-08-01)

| Clock | Observation | Authority | Evidence |
|---|---|---|---|
| First LC emission in this checkout | 2026-07-17 `BROKEN`, dislocation true, med_dd −29.6%, carnage EMA 81% | display-only | `data/leadership_crack/forward_log.jsonl` first row |
| Prior named episode | 2026-06-23 memory unwind; 2026-07-02 KOSPI/SK Hynix session | n/a (prior) | `engine/risk_state.py` docstring; `research/SECOND_ACT_NOTE.md` |
| Last US RISK_OFF in window | 2026-07-29 Market State `RISK_OFF` score 40 | advisory | MS forward_log |
| Design-era boundary | 2026-07-31 LC still `BROKEN` | display-only | LC forward_log |

First **useful fragility observation that is actually emitted:** 2026-07-17 LC `BROKEN`. Earlier fragility may exist but this log does not contain it.

## Policy / funding

| Event | event_time | available_at | Observation | Authority |
|---|---|---|---|---|
| PBOC 3m outright tender announced | 2026-08-04 | first_seen 2026-08-04T12:03Z | 5000 bn, 3 months | context |
| 7-day RR 630/465/50/10/10/180 bn | 2026-08-03..10 | same-day first_seen | Gross 7-day shrinking | context |
| Zero 7-day RR | 2026-08-11..14, 17..18 | 08-11..14 first_seen same day; **08-17 first_seen 2026-08-18T09:00Z** | amount_bn=0 | context |
| 6m outright tender announced | 2026-08-13 | first_seen 2026-08-14T09:41Z | 10000 bn, 6 months | context |
| FR007 | 2026-08-07..18 | store has no published_at | 1.41–1.43, soft | context |

Classification **after** transmission (GD-H6): **TOOL_MIGRATION**, not tightening. Soft funding + zero 7-day is not adverse by itself.

## Treasury auctions (results only)

| Auction | high_yield | BTC | available_at | WI tail |
|---|---|---|---|---|
| 2026-08-11 3y | 4.291 | 2.71 | ~13:00 ET result | UNAVAILABLE |
| 2026-08-12 10y | 4.683 | 2.53 | ~13:00 ET result | UNAVAILABLE |
| 2026-08-13 30y | 5.216 | 2.39 | ~13:00 ET result | UNAVAILABLE |

DGS30 (latest-revised, descriptive): 5.21 on 2026-08-13 → 5.31 on 2026-08-17. VIX 14.3–15.5. Not an extreme vol level.

## Transmission / breakdown (descriptive closes)

US session close-to-close (%), observation price = prior close:

| Session | SPY | QQQ | SMH | SOXX | XLK | XLP | XLV | EWY | EWT | EWJ | FXI | KOSPI (_KS11, KR session) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-17 | −0.47 | −0.16 | +1.06 | +1.58 | +0.16 | −1.64 | −0.19 | +2.98 | +0.68 | −0.04 | +0.60 | (no KR bar 08-17) |
| 2026-08-18 | −0.68 | −1.69 | −4.09 | −4.96 | −2.47 | +1.06 | +1.60 | −8.13 | −3.16 | −2.85 | −0.11 | −1.55 |
| 2026-08-19 | US bar not in store | | | | | | | | | | | −4.75 (volume light) |

Do **not** treat EWY −8.13% on the US 08-18 session as the KOSPI cash clock. Korea cash 08-18 is −1.55%. Korea 08-19 is −4.75% and may be unsettled.

## Organ states vs tape

| Session | LC | Market State | US Risk Radar | KR Risk Radar | Defensible product message |
|---|---|---|---|---|---|
| 2026-08-13 | BROKEN (display) | RISK_ON 77 | caution, no alert, advisory | calm | "Leadership cohort still broken. Headline risk is risk-on. These are different organs." |
| 2026-08-17 | BROKEN; vel healed | RISK_ON 77 | watch, no alert | (no 08-17 row) | Same dual-read. 30y +10bp since 08-13 is a rates observation, not an authorized alert. |
| 2026-08-18 | BROKEN again deeper med_dd | RISK_ON 76; radar **calm**; recovery de-escalation eligible | **calm**, no alert | calm | Honest message: leadership still broken; radar de-escalated into the US semi down-session. Do not say "risk-on therefore safe." |
| 2026-08-19 | no US LC row yet | no US row | — | **calm** on KR −4.75% | KR radar did not confirm breakdown. |

## Repair

| Clock | Status |
|---|---|
| SK Hynix BOD acquire-and-cancel 40tn KRW | Impulse **2026-08-19**, CLOCK_PARTIAL (secondary press 16:59 KST). Starts 2026-08-20. |
| Cross-asset confirmation | **Not yet.** Same-day Korea session still the breakdown session. US 08-19 bar absent. |
| Terminal | **REPAIR_UNRESOLVED_AT_CUTOFF** |

## Required-question answers (clocks only)

- **First useful fragility observation:** 2026-07-17 LC `BROKEN` (first emission). Fragility is pre-incident.
- **First trigger observation (lawful):** 2026-08-13 30y auction result (BTC 2.39, hy 5.216) is a candidate trigger *receipt*, not a proven tail. WI tail unavailable. 2026-08-17 +10bp 30y is confirmation of long-yield move, latest-revised.
- **First transmission confirmation:** 2026-08-18 US session: SMH −4.09%, SOXX −4.96%, XLK −2.47% vs SPY −0.68%; XLP/XLV positive residuals. Same-session GD-H4 shape.
- **First breakdown confirmation:** Same 2026-08-18 US high-beta residual (SOXX −5% class). SPY itself is not a 3% drawdown that day.
- **First cross-market contagion confirmation:** **Split.** US-hours EWY/EWT/EWJ sold with semis on 08-18. Official KOSPI confirmation is 2026-08-19 −4.75% (possibly unsettled). FXI −0.11% on 08-18 is **not** China confirmation.
- **First repair impulse:** 2026-08-19 SK Hynix BOD, CLOCK_PARTIAL.
- **Earliest possible repair confirmation:** Not yet. Need persistence through two settled sessions across trigger, breadth, and cohort.
- **Organ with evidence, no authority:** Leadership Crack (BROKEN the whole window, display-only).
- **Organ that de-escalated incorrectly relative to later clocks:** Market State (RISK_ON) and US Risk Radar (calm on 08-18); KR Radar (calm on 08-19). "Incorrect" here is descriptive vs subsequent residual damage, not a proven false-negative rate.
- **Stale source:** CN Risk Radar (last emission 2026-07-16).
- **Earliest defensible on-page alert:** A **dual-read** ("leadership still broken / radar risk-on") was defensible from 2026-07-17 onward as display context. A **new-entry restriction** was not authorized by any organ and is not granted by this replay.
- **Scoped new-entry restriction:** See Prophet counterfactual. Coverage-blocked for the full board. Not a policy.
