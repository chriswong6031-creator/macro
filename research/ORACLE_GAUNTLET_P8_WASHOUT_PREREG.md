# Oracle P8 — Washout-Confluence Gauntlet — Pre-Registration

**Status: REGISTERED before any result was computed.** Authored by Fable 2026-07-04 in response to the operator's pushback on P3, which is adjudicated as substantially correct on scope: P3 falsified *RS-acceleration continuation* (one lens), not rotation edge in general, and never tested the **washout-reversal** class — a signal Oracle's panel cannot even see (no oscillator columns). This registration tests the operator's thesis in its falsifiable form. Inherits the P3 constitution ([ORACLE_GAUNTLET_P3_PREREG.md](ORACLE_GAUNTLET_P3_PREREG.md)) wholesale; only deltas are specified here. Seed 20260704. No parameter below may be tuned after this merges.

## 1. The operator's thesis, decomposed into registered hypotheses

- **P-W1 (primary) — the standalone washout claim.** Universe: the 11 GICS sector ETFs (survivorship-clean, 1998-12→2026-07, `data/yahoo` div-adjusted closes). Entry signal, frozen: weekly bars resampled LEAK-FREE (left-label; the bar at index i uses no close dated > i — the §7/3B convention); oscillators from the FAITHFUL port (`research/signal_engine/confluence.py` — RSI-based MACD + stoch-of-RSI; never price `macd_parts`); **washout** = weekly StochRSI-K < 20 on ≥2 consecutive weekly bars within the prior 3 bars; **turn** = first weekly bar where K crosses above D. Entry at the next DAILY close after the weekly turn bar completes (no intrabar knowledge). Outcome: forward excess vs SPY at +21/+63 sessions. Registered expectation: positive, hit-rate ≥ the `sector_signals` BUY base rate (+1.10% / 56% @63d) — which is ALSO the boring baseline it must beat to justify existing (G6).
- **P-W2 (primary) — the confluence-multiplier claim.** The same entries split by Oracle rotation context **as-of the entry date** (strictly causal; no post-entry information): (a) the ETF's complex accel_z_5d > 0 (pre-onset improvement), (b) an opposite-risk complex has an active OUT episode, (c) both. Endpoint: the INCREMENT of conditioned-entry mean/hit over unconditioned P-W1, at +63d. Registered expectation: **genuinely open** — this is the single number Red Queen needs for weighting Oracle; a null increment is as valuable as a positive one and ships printed either way.
- **S-W3 (secondary) — monthly washouts.** Same construction on monthly bars (K<20, ≥1 bar, turn = K>D cross). Expected n very small (register: likely underpowered; descriptive if n<40).
- **S-W4 (secondary) — the exit mirror.** Weekly StochRSI-K > 80 washout-top + down-cross, split by Oracle rollover context; forward excess at +21/+63d (hypothesized negative).
- **S-W5 (secondary) — Tier-M echo.** P-W1 construction on the 40 theme nodes (2021→, watermarked; confirmatory only, no headline).

## 2. Gates (P3 constitution, deltas only)
G1 placebo (200 draws, matched per-ETF counts, ±10-session exclusion around real entries) · G2 block-bootstrap CI (2,000 × 21d) · G3 regime strata (VIX pctile 0.6 / SPY 200dma) · G4 era consistency (≥3 of 4 eras incl. 2023–26) · G5 one BH-FDR family at q=0.10 over ALL cells (register the count in the ledger before p-values; expected ~30–40) · G6 boring-baseline exceedance (P-W1 vs the published BUY state; P-W2 increment vs zero AND vs a random-context split placebo — conditioning on a coin flip must not produce the increment). Verdict vocabulary pre-bound as in P3: VALIDATED / DISPLAY-WITH-EDGE / NULL, primaries only eligible for VALIDATED.

## 3. Consequences pre-bound
- P-W1 VALIDATED or DISPLAY-WITH-EDGE → the oscillator/washout columns (2W/1M StochRSI state via the faithful port) get promoted INTO the Oracle panel schema (a P9 build), so Oracle natively sees washouts; the Time Machine gains washout markers.
- P-W2 increment positive and gate-passing → Oracle's bus payload gains a `washout_confluence` field and its Red Queen weight class rises from "initiator/context" toward "confirmer"; increment null → Oracle remains initiator-class in the fusion brain, stated plainly.
- All failures ship with nulls printed. No re-tuning of any frozen parameter without a new registration.

## 4. Execution
Sonnet builds `scripts/oracle_gauntlet_p8.py` + hermetic tests (leak-free resample proof: weekly bar values invariant to truncation; faithful-port parity check against `research/signal_engine/confluence.py` on a fixture; placebo validity; era/FDR reuse from P3 harness patterns). Haiku independently recomputes the P-W1 entry list count + raw mean for one ETF. Opus audits registration fidelity (resample leakage is the #1 kill; port fidelity #2; as-of-date causality of the P-W2 context #3). Fable adjudicates mechanically.

---
*Registration locked at merge. Provoked by, and answerable to, the operator's 2026-07-04 washout-confluence thesis.*
