# GD-1 results and adjudication

**Prereg freeze:** `663fb02b500c` (content sha256 `13df565d…f17b3`) before August outcome columns were opened.
**Incident terminal:** `REPAIR_UNRESOLVED_AT_CUTOFF` on 2026-08-19.
**Authority granted:** none.

This document attacks the Chairman-shaped story as hard as the clocks allow. Nulls stay null.

## What the clocks actually support

1. **Fragility was old.** Leadership Crack was already `BROKEN` at the first emission (2026-07-17) and stayed `BROKEN` through 2026-08-18. August is not when leadership broke.
2. **Headline risk de-escalated into the US semi down-session.** Market State was `RISK_ON` 2026-08-12..18. US Risk Radar went caution → watch → **calm** on 2026-08-18. Recovery copy said de-escalation eligible. That is the disconnected-evidence finding.
3. **PBOC zero 7-day is not tightening.** Six zero 7-day days with FR007 ~1.41–1.43 and large outright 3m/6m tenders = **TOOL_MIGRATION**. GD-H6's "no fixed sign" holds on this incident.
4. **2026-08-18 US session is a same-session transmission confirmation, not a lead.** SOXX −4.96%, SMH −4.09%, XLP/XLV up vs SPY −0.68%. GD-H4 descriptive shape prints. It does not print as a predictor.
5. **China did not confirm on 2026-08-18.** FXI −0.11%. CN board still tech-heavy buyable. GD-H5/H8 China legs are **null** for that session.
6. **Korea cash and EWY disagree.** Do not write "Korea −8% on 08-18." KOSPI 08-18 −1.55%; 08-19 −4.75% (possibly incomplete). EWY −8.13% is a US-hours proxy.
7. **Prophet did not "know."** On **pit_live** rows only, tech was 29/127 buyable (22.8%) on 08-17 and 6/52 (11.5%) on 08-18. Live `n_raw` is 2936 both days. An unfiltered 12%/12% read mixed 08-17 `recomputed_history` into the denominator and is withdrawn. Gates still fired same-session; 29 live tech names were buyable the day before.
8. **SK Hynix 40tn buyback is an impulse on 08-19, CLOCK_PARTIAL, not durable repair.**

## Hypothesis scorecard

Predictive family `{H1,H2,H3}` is **not passed**. Emission-log N is 15 LC rows / 33 RR rows. Current incident cannot be the only positive case.

| ID | Verdict | Why |
|---|---|---|
| GD-H1 | UNDERPOWERED as predictive; **not coverage-true as labeled** | LC already BROKEN. SMH residual vs SPY 08-17→08-18 = −3.41%; SOXX residual = −4.28%. The registered ≥3% residual **prints on those two names**; the ≥5% residual **does not**. Absolute SOXX −4.96% is not a residual. Registered object is LC-cohort median (`n_total=42`); not computed; PIT membership not reconstructed → that object stays **BLOCKED**, not a silent substitute. |
| GD-H2 | UNAVAILABLE / weak | FRED VIX ends 08-17 at 15.19; Yahoo `_VIX` 08-18 is 15.84. Design-era 80th ~22.7. Level baseline quiet. `drv_spy_5d` / `vol_accel` **not computed**. MOVE/VVIX missing. |
| GD-H3 | tail **UNAVAILABLE**; standalone auction **still disallowed**; proxy **UNTESTED**; yield-confirmation **does not fire as written** | WI tail absent. Auction-day 08-13 DGS30 **fell** 3bp (5.24→5.21). 08-13→08-17 +10bp is not registered `d_dgs30_3d`. 08-12→08-17 is +7bp, equal to (not exceeding) a design-era 80th of +7bp on this FRED file. `accel_long_nom` as preregistered would not fire on a strict exceed. |
| GD-H4 | **UNDERPOWERED** (N=1); lead **not claimed** | Same-session confirmer shape is visible on SMH/SOXX + XLP/XLV, but the registered LC-cohort share ≤ −2% was not computed, and XLK residual −1.79% would not count as ≤ −2% for that name. One incident cannot PASS. |
| GD-H5 | **NULL** on 08-18 EOD counts; returns **UNAVAILABLE** | Tech still largest CN buyable group. No 08-17 board. No session returns. |
| GD-H6 | **PASS as refutation of a fixed sign**; positive TOOL_MIGRATION is **provisional** | Zero 7-day + soft FR007 refutes tightening. Outright 3m/6m rows have `awarded_bn` NaN (tenders). 08-17 bulletin `first_seen` is 2026-08-18T09:00Z, not same-day. |
| GD-H7 | **UNRESOLVED** | Impulse same day as KR breakdown. |
| GD-H8 | **SPLIT / UNDERPOWERED** | US high-beta residuals yes; CN no. TW/JP were read off EWT/EWJ (US-hours ETFs), not venue-cash vs own 20-session median. KOSPI 08-18 volume is **0.0** — treat as a stub, not a settled cash confirmation. KR official −4.75% is 08-19, volume light. Lead claim forbidden. |

Baselines: a VIX-level rule would have been **quiet** (VIX ~15). A 50-day MA break on SPY is **not** what fired (SPY 08-18 still above the early-August print). The trivial vol-level baseline does **not** match the 08-18 residual damage. That does **not** promote GD-H1 — it only says the obvious VIX-level baseline was also blind.

## Failure mode (the useful engineering result)

| Layer | Finding |
|---|---|
| Missing data | 000660.KS, WI tail, MOVE, Anticipation/Velocity stores, CN radar August, LC prehistory |
| Clock | EWY vs KOSPI; FRED latest-revised yields; LC/MS nightly holes |
| Thresholding | not the issue — we did not retune |
| De-escalation | Market State + US/KR radars de-escalated while LC stayed BROKEN |
| Transport | LC display-only; nothing consumed it as a new-entry restriction |
| Authority | No organ had authority to restrict Prophet new entries. Evidence existed; policy did not. |

Earliest **defensible product message** (not an action): from 2026-07-17, a dual-read chip. Earliest **defensible scoped new-entry restriction:** **none** from existing organs. A sidecar would be a new GD-5/6 construction and is not authorized here.

## Adversarial attack (this session)

Attempts to explain the findings as hindsight / correlated features / wrong clocks:

1. **"LC BROKEN is just the July crash still decaying."** Partly true — that is the precursor. It does not excuse RISK_ON + calm radar on 08-18. Dual-read still holds.
2. **"08-18 was just a vol event."** VIX 15.19. Absolute VIX is the killed baseline. Residual damage was cohort-specific, not SPY −3%.
3. **"Prophet was defensive so the stack worked."** Falsified as a *forecast*: 29 **pit_live** buyable tech names on 08-17. The withdrawn 12%/12% line cannot be used either for or against a share-stability story.
4. **"PBOC drained liquidity and caused it."** Falsified by soft FR007 and outright migration.
5. **"Korea crashed 8% and transmitted."** Wrong clock if that sentence uses EWY as KOSPI.
6. **"We should promote H1 because 08-18 looks like H1."** Forbidden. One incident, no design-era test, LC log too short.
7. **"latest.json proves the system said BROKEN at 10:00."** No. Nightly/EOD emission. Intra-day claims BLOCKED.

Independent reviewer (`01a01955-708f-7491-b800-016849b05246`) **broke** the 12%/12% tech-share line (recomputed-history contamination), the ≥5% residual label on SMH/SOXX, the GD-H4 PASS, and the 30y +10bp confirmation. Those are withdrawn or relabeled above. Surviving: LC BROKEN dual-read vs RISK_ON/calm; EWY≠KOSPI; China non-confirm; PBOC not-tightening; repair unresolved; no live authority.

## Constructions

**Not GD-5 eligible under prereg §10** (no design-era PASS). Descriptive residue Fable may keep in the envelope, still **not** a builder commission:

- Dual-read **observation**: LC BROKEN sat next to Market State RISK_ON / US RR calm. Wiring that as product is a later authority decision, not a GD-1 grant.
- `auction_concession_proxy_v1` remains UNTESTED. Do not hand a builder the interaction.

**Rejected / refuted:**

- Standalone bad-auction → equities (prior null + packet ban)
- Zero 7-day PBOC = tightening (refuted on this tape)
- "Prophet knew" / defensive-composition-as-forecast (refuted)
- Absolute VIX threshold (DNR, and VIX was not extreme)
- Any construction that needs WI tail, 000660.KS, or intraday board quotes **until those clocks exist**

**Must remain shadow:** every sidecar policy, every hazard probability, every new-entry restriction.

**May enter a GD-2 descriptive envelope now:** the dual-read timeline, PBOC tool-migration classification, 08-18 same-session H4 table, Prophet gate-reason distribution, EWY≠KOSPI clock warning.

## Explicit non-authority

GD-1 grants **no** live market, Prophet, or Portfolio authority.

## One next research action

Truncate-and-recompute `leadership_crack.v1` from 2016–2026-07-31 on existing US basket membership **as a labeled `def_current_cf`**, freeze the design-era 80th percentile of `d_dgs10_3d`/`d_dgs30_3d`, and test GD-H1 with episode-level N. Do not use August 2026 to pick the percentile. If WI remains missing, leave GD-H3 tail blocked.

If that recompute cannot reconstruct PIT membership, return BLOCKED and stop.
