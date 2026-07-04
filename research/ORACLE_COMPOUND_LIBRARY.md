# Oracle Compound Library — the hypothesis ledger

**What this is.** The DISCOVERY-tier hypothesis space for Oracle-as-Red-Queen-feeder, generated mechanism-first (why money moves → what footprint it must leave), per the operator's 2026-07-04 rebalance directive: *Fable generates and adjudicates; cheap models screen; the gauntlet fires only at promotion.* Every screen run against this library MUST append a row to the Trial Ledger (§7) — mining is allowed here *because it is counted*; the promotion-stage FDR uses the true search width (the Harvey-Liu-Zhu answer to the factor zoo).

**Phase rules.**
- **Tier 0 (generation, Fable):** this document. Compounds ranked by mechanism-plausibility × data-availability × orthogonality-to-what-exists.
- **Tier 1 (screening, cheap models):** fast, promiscuous, unregistered. Output = effect size + n + era-split direction, appended to §7. No claim language ever leaves Tier 1.
- **Tier 2 (promotion):** a compound with a Tier-1 effect ≥ the economic floor (|63d excess| ≥ 1% or hit ≥ 55% at n ≥ 100) AND a mechanism story gets ONE registered gauntlet shot (machinery: `scripts/oracle_gauntlet_p3.py`/`p8.py`, ~100s). Verdict vocabulary from P3.

**Standing empirical anchors** (already measured, twice-verified): washout×opposite-complex-rollover = +1.14% increment vs size-matched chance (cond_b, n=194, the program's standout accruing cell); acceleration-conditioned entries NEGATIVE (late = bad); XLE washouts +1.79% pooled-27y; cohesion_chg = the one FDR-surviving group_flow leg (stress-conditional); sector personalities visibly heterogeneous.

---

## Family A — Conservation / routing compounds (*money must go somewhere*)

Mechanism: benchmarked funds can't go to cash; mandates force selling X to buy Y. Rotation ≠ liquidation, and the difference is *sink-presence*.

- **A1 — Empirical source→sink pairing.** Generalize cond_b: condition sink-entries on source-outflow where the pair comes from the measured Flow-Routing Matrix (not fixed risk-opposites). The routing matrix already exists; the 6 placebo-surviving cells are the seed pairs. *Data: have. Priority: 1.*
- **A2 — Cascade breadth as signal strength.** The June rotation was a 3-week cascade THROUGH a complex (foundries→compute→litho→memory). Condition entries on N≥3 same-complex subsector rollovers within K sessions — breadth of exit as conviction multiplier for the sink. *Data: have (episode catalog). Priority: 1.*
- **A3 — ROTATION vs LIQUIDATION vs ACCUMULATION regime tag.** When sources roll over WITH a sink accelerating = rotation (buy the sink); when everything rolls with NO sink = de-risking/liquidation (different playbook: defensives/cash, buy nothing); all-sinks-no-sources = broad accumulation. Oracle currently cannot distinguish these three states — this is arguably the single most valuable state variable it could hand Red Queen. *Data: have. Priority: 1 — this is a build, not just a screen.*

## Family B — Sector-personality compounds (*sectors are different animals*)

Mechanism: response-type is a property of the holder base + business cycle exposure, so it's semi-stable and learnable.

- **B1 — Personality classification, then personality-appropriate entries.** Classify every sector/subsector on trailing history into {mean-reverter, trender, rate-proxy, idiosyncratic} via its own washout-response and trend-persistence stats; apply the entry that matches the class (washout-buys for mean-reverters; breakout/onset for trenders; rate-conditioned for proxies; skip systematics for idiosyncratics — stock-pick there instead). Converts "per-sector mining" into ONE hypothesis: *personality classes exist and persist*. XLE (+1.79%) vs pooled (+0.45%) is the existence hint. *Data: have. Priority: 1.*
- **B2 — Cycle-clock conditioning for cyclicals.** For known cyclical complexes (semis/memory, energy, shipping), condition washouts on cycle phase from the existing sector_cycles engine — a washout in early-cycle ≠ late-cycle. *Data: have (sector_cycles). Priority: 2.*
- **B3 — The weirdos as dispersion alpha.** Screen for subsectors with LOW correlation to all complexes (unmodeled by systematic flows) — systematic edges won't live there, but stock-picking dispersion does; route those to the stock desk, not Oracle. A *negative* routing rule is still information. *Priority: 3.*

## Family C — Velocity-shift microstructure (*the operator's turn-entry, layered*)

Mechanism: turns are where discretionary+systematic flows flip sign; multi-timeframe confluence is the cheapest institutional-footprint detector.

- **C1 — The full timing ladder.** P8 tested only the weekly layer. The operator's actual trade: 2W washout (condition) + weekly K/D cross (setup) + DAILY MACD/StochRSI confluence within X days (trigger) — the same T1-T4 cascade already validated for stocks in signal_gate, applied at sector level. Screen the daily-trigger overlay on the P8 entry set. *Data: have. Priority: 1.*
- **C2 — Washout divergence.** Price lower-low with RS-velocity higher-low at the washout = seller exhaustion. *Data: have (panel). Priority: 2.*
- **C3 — Turnover signature at the turn.** turnover_z spike on the turn bar (capitulation→absorption). Panel already carries turnover_z and nothing consumes it. *Priority: 2.*
- **C4 — Cohesion collapse→rebuild.** Cohesion falls through the washout (idiosyncratic selling), jumps on the turn (coordinated buying = institutional re-entry). Builds on the ONE validated group_flow leg (cohesion_chg, stress-conditional). Compound: washout + cohesion_chg > q75 on the turn bar. *Priority: 1 — highest mechanism-quality per unit data.*

## Family D — Macro-regime conditioning compounds

Mechanism: the same sector signal is a different animal in different regimes (the operator's Fama-French point, literally).

- **D1 — The rates confound, weaponized.** DEFENSIVE_ROTATION died because defensive rallies were "rates fell" in disguise. Invert it: tag every sector by rate-beta; rate-proxy washouts are buyable only when bond vol (TLT realized) is subsiding; rotation-driven washouts only when rates are quiet. The confound becomes the conditioner. *Data: have. Priority: 1.*
- **D2 — Dollar/commodity axes** for energy/materials/industrials entries (DXY trend, copper-gold). *Data: have. Priority: 2.*
- **D3 — Liquidity-regime gate** (net-liquidity engine exists): washouts in expanding vs contracting liquidity. *Priority: 2.*

## Family E — Positioning / options compounds (accruing data — the operator's later quest)

Mechanism: dealer mechanics and crowding are *mechanical* flows — the least efficient information in the stack.

- **E1 — Fear-spent washouts:** washout + sector-member IV percentile falling from its spike (fear priced and now decaying) vs IV still rising. *Data: skew/chains accruing since 2026-06; screenable ~2027. Priority: parked-accruing.*
- **E2 — GEX flip reclaim as turn trigger** for the index-adjacent sectors. *Parked-accruing.*
- **E3 — Crowding unwind detection:** cohesion spike + negative returns = crowded unwind in progress (don't catch); cohesion already low at the low = uncrowded washout (catch). *Data: have NOW via cohesion — screen this one. Priority: 2.*

## Family F — Information-flow compounds

Mechanism: information diffuses through supply chains and reporting calendars at measurable lags.

- **F1 — Earnings read-through:** early reporters in a complex (TSM-type anchors) surprise → conditional drift for the complex's late reporters. *Data: have (earnings calendar + panel). Priority: 2.*
- **F2 — Revision-breadth turn:** analyst revision breadth (already collected) turning up while price still washed out. *Priority: 2.*
- **F3 — Policy-catalyst timing:** FedReg/policy calendar events (institutional program W1b) as washout-resolution catalysts for policy-sensitive sectors. *Priority: 3.*

---

## §6. What Oracle should BUILD next (not screen — build), in order
1. **A3 regime tag** (rotation/liquidation/accumulation) into `oracle_state.json` — pure composition of existing episode data; Red Queen's most valuable missing input.
2. **B1 personality layer** — per-node response-type classification, refreshed quarterly, shipped as display + a conditioning column.
3. **C1/C4 columns in the panel** (daily-confluence trigger state; cohesion-rebuild flag) so future screens are one groupby, not one harness.

## §7. Trial Ledger (append-only; every Tier-1 screen logs here)
| date | compound | screener | universe/era | effect | n | direction-consistent eras | promoted? |
|---|---|---|---|---|---|---|---|
| 2026-07-04 | P8 P-W1 (pre-library) | Fable gauntlet | 11 ETFs 1999→ | +0.45%@63d, 50.7% | 629 | 3/4 | NULL |
| 2026-07-04 | P8 cond_b ≈ A1-seed | Fable gauntlet | 11 ETFs 1999→ | +1.14% inc, 55.2% | 194 | — | accruing |

## §8. Tier-1 screening protocol (for ChatGPT/Codex/Haiku — copy-paste spec)
Inputs: `data/oracle/panel_{s,m}.parquet`, `episodes_{s,m}.parquet`, `graph_m.json` (schemas in engine/oracle/panel.py COLUMN_SCHEMA). Rules: causal joins only (features as-of entry date); report effect size + n + per-era direction (1999-2014/2015-19/2020-22/2023-26) + the exact filter code; NO claim language; append the ledger row. A screen is ~50 lines of pandas. Wide search encouraged — every run logged.
