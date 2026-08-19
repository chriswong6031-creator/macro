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
7. **Prophet did not "know."** Tech share of buyable was ~12% on both 08-17 and 08-18. Buyable N collapsed because live gates fired **on** 08-18, not because a duration sidecar pre-empted tech.
8. **SK Hynix 40tn buyback is an impulse on 08-19, CLOCK_PARTIAL, not durable repair.**

## Hypothesis scorecard

Predictive family `{H1,H2,H3}` is **not passed**. Emission-log N is 15 LC rows / 33 RR rows. Current incident cannot be the only positive case.

| ID | Verdict | Why |
|---|---|---|
| GD-H1 | UNDERPOWERED as predictive; **coverage-true** on this incident | LC already BROKEN; 08-18 high-duration residual ≥3%/≥5% on SMH/SOXX over 1 session. Historical test from the emission log is impossible (log starts broken). Truncate-recompute not run. |
| GD-H2 | UNAVAILABLE / weak | VIX 14–15, not extreme (good for the "level isn't the thing" clause). Realized-variance acceleration vs design-era 80th **not computed**. MOVE/VVIX missing. |
| GD-H3 | tail **UNAVAILABLE**; standalone auction **still disallowed**; proxy **UNTESTED** | WI tail absent. SLF-006 and D2 remain null priors. |
| GD-H4 | descriptive **PASS on this session**; lead **not claimed** | Same-session only. |
| GD-H5 | **NULL** on 08-18 EOD counts; returns **UNAVAILABLE** | Tech still largest CN buyable group. No 08-17 board. No session returns. |
| GD-H6 | **PASS as refutation of fixed-sign** | Zero 7-day + soft FR007 + outright migration. |
| GD-H7 | **UNRESOLVED** | Impulse same day as KR breakdown. |
| GD-H8 | **SPLIT / UNDERPOWERED** | US+TW+JP US-hours residuals yes; CN no; KR official clock 08-19. Lead claim forbidden. |

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
3. **"Prophet was defensive so the stack worked."** Falsified by 12% tech share both days and by 29 buyable tech names on 08-17.
4. **"PBOC drained liquidity and caused it."** Falsified by soft FR007 and outright migration.
5. **"Korea crashed 8% and transmitted."** Wrong clock if that sentence uses EWY as KOSPI.
6. **"We should promote H1 because 08-18 looks like H1."** Forbidden. One incident, no design-era test, LC log too short.
7. **"latest.json proves the system said BROKEN at 10:00."** No. Nightly/EOD emission. Intra-day claims BLOCKED.

An independent `reviewer` pass on these files is still the packet's acceptance item. This section is the author's attack, not a substitute for that pass.

## Constructions

**Worth shadowing in GD-5 (no live authority):**

- Dual-read transport: LC state next to Market State / Risk Radar with authority labels. Wiring only. No new score.
- Named `auction_concession_proxy_v1` × already-BROKEN LC × next-session long-yield confirmation — **after** a design-era test, not from this incident.

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
