# Ratio Lens — pairwise ratio intelligence & rotation localization (Oracle-owned)

**Status:** REGISTRATION + MASTERPLAN (W0). Merged-before-results per Oracle Constitution §I.3.
**Adjudicator:** Fable (main loop), 2026-07-11. **Red-team:** 2 Opus lanes (§8), dispositions binding.
**Owner program:** oracle (NW-U6: Oracle is the rotation lobe; Neural Web never re-implements rotation detection).
**Operator directive (2026-07-11):** use ratios between baskets/subsectors (mag7/semis, semis/memory, software/hardware…) to (a) find pair-trade candidates and (b) localize rotations precisely instead of reading aggregate XLK — tracking ratio level, velocity, stretch, washout/basing, and multi-timeframe confluence, while respecting that these are correlations, not causations.

---

## §0. The gap this fills (census-grounded)

Nothing in the repo computes a **pairwise ratio series between two named nodes** as a first-class object. The house RS convention is `ret − cross-sectional median` (zero-sum by identity); Oracle's panel/episodes/Time Machine, `subsector_rotation.py`'s RRG quadrants, and the Turn Desk all run on that cross-sectional construct. Snapshot ratio reads exist (`engine/index_leadership.py:ratio_read`, `engine/etf_pulse.py` style pairs, `engine/sectors.py:pair_ratios_snapshot`) but have no state machine, no stretch/anchor read, no decomposition, no ledger, no taxonomy. The 2026-H1 lesson motivating this program: memory (MU +158% YTD, SOXX +99%) vs NVDA (+24%) / MAGS (flat) was invisible at XLK/SMH granularity — SMH's NVDA+TSM ~25% weight muffled the loudest subsector rotation of the year.

**What this program is:** a display-tier Oracle organ that computes a **frozen, curated registry of ratio pairs** over a 3-level taxonomy, prints level / pace / stretch / anchor / washout states with **numerator-vs-denominator decomposition in absolute returns**, renders a **decomposition tree** that localizes where inside tech the rotation is occurring, and accrues a pre-registered expected-null forward ledger for the pair-maturity states.

**What this program is NOT:** not a signal (no rank/gate/size/escalate authority — AUTHORITY block all-false); not a pairs-trading executor; not an episode/onset machine (Turn Desk owns onset+routing+destination); not a lead-lag tensor extension (frozen at 6/90 per TOP3-O2); not "money flow" anything (naming-fraud fence).

---

## §1. Rulings (RL-R1..R16)

- **RL-R1 (placement).** Oracle-owned: `engine/oracle/ratio_lens.py` + `scripts/build_oracle_ratio_lens.py`. Neural Web consumes `ratio_lens.json` read-only via a `_compose_ratio_lens()` world_state composer (W3). Any re-implementation outside Oracle violates NW-U6.
- **RL-R2 (registry is law).** Pairs, taxonomy, state definitions, and horizons live in a curated config (`data/oracle/ratio_pairs.json`) whose **content hash is frozen at W1 merge**. Adding/removing pairs or redefining states = a reviewed amendment PR that appends to §9 and re-freezes the hash. This is the multiplicity fence (red-team M5): the implicit-claim universe is pre-declared, one qledger family, no silent growth.
- **RL-R3 (zero-sum fence — decomposition law).** Every displayed ratio move MUST be decomposed into its legs' **absolute returns** ("memory +4.1% / logic −0.2%"). No output may gate, rank, or threshold on cross-sectional dispersion or any `ret − cross-node-aggregate` construct (that is the killed R-4 object). The localization surface is a **descriptive decomposition tree** — per parent, children's absolute returns printed side-by-side — with **no locus ranking, no dispersion gate, no destination/routing fields** (red-team M3/M5 disposition).
- **RL-R4 (move-shape labels).** Pair moves carry a shape label computed from leg signs with a dead-band: `one-sided` (legs opposite sign, or weaker-leg |move| < 0.25 × stronger-leg), `shared-tide-up`, `shared-tide-down`, `mixed`. Plain words only; the terms "rotation"/"reallocation" may describe *one-sided* moves in copy but NEVER as a fired state key, and "money routing"/"flow" vocabulary is forbidden (TOP3-O2).
- **RL-R5 (long-history honesty).** Pre-2021 history ships **only** on ETF/index pairs (an ETF price is its own PIT membership record). Custom-basket pair series start at `max(members' store coverage, seed_date 2023-05-09)`, carry the Tier-M survivorship watermark inline, and **no pre-seed reconstruction ships** — current-membership-backwards is a survivorship double-book (SNDK+WDC pre-2025 were one enterprise; dead DRAM makers never enter), and a label does not cure it (red-team M1/M2 disposition).
- **RL-R6 (anchor honesty).** Mean-reversion "anchor" claims: OU `b` fit on ≥252 daily bars with a time-preserving bootstrap CI. A half-life number prints **only** when b is significantly negative AND the CI upper bound < 252d; otherwise the pair states `NO ANCHOR — trend, not rope` with no number (no rolling-60d ADF gate, no bare point estimates — red-team M7 disposition). A 20-session one-directional z-drift prints as a descriptive "persistent one-way move" note, not a "break test."
- **RL-R7 (stretch/pace grammar, descriptive).** Per pair on `L = ln(A) − ln(B)` (inner-join of valid bars only; no forward-fill; effective common start printed per pair): z of L on rolling 63d and 252d windows; pace = ΔL over 1w/1m/3m at weekly rate; weekly StochRSI washout on L (watermarked "not characterized on ratio inputs — descriptive"); percentile of L vs trailing 3y. Velocity/pace/accel fields are **descriptive and may never become decision keys** without their own registered gauntlet (factor-rotation-velocity kill stands).
- **RL-R8 (maturity states + stance vocabulary).** Display states: `TRENDING` · `EXTENDED` (|z252|≥2) with a printed `pace: building/steady/fading` fact · `BASING` (washout present + weekly momentum turn) · `NO ANCHOR`. The pace-fading fact is a measurement, NEVER framed as "pre-reversion" (red-team M4). Stances per DESIGN_DOCTRINE: EXTENDED → "Watch — don't chase"; BASING → "Get ready — needs a trigger"; NO ANCHOR → "Trend, not rope — don't fade it"; TRENDING → "Ride, don't add late." No buy/sell/direction/target/forecast keys (contract + FORBIDDEN_KEYS walk in tests).
- **RL-R9 (forward ledger prereg — expected-null).** qledger family `ratio_lens.v1`. Unit = pair-state transition (EXTENDED on/off, BASING on/off, one-sided-move flag day). Outcomes: forward 21d and 63d log-ratio move + each leg's absolute move (reversion-capture-shaped ruler at 21d; 63d factor conventions do NOT apply to these states). Declared expectation: **NULL** — states are context until proven otherwise. Any future evaluation uses calendar-episode clustering (ticker-cluster time-confound law); the cumulative implicit-claim count prints in the artifact. Promotion to any authority = new prereg + full gauntlet; display-tier accrual is never blocked by nulls (house epistemics).
- **RL-R10 (fences restated, binding).** (a) Ratio-cycle position, if ever computed, NEVER enters entry confluence (DO_NOT_REBUILD row 33). (b) No cross-sectional-dispersion gate anywhere (row 34 / R-4). (c) No LLM-originated states/scores. (d) No extension of the O1 lead-lag tensor or flow-routing cells. (e) No episode/onset/destination fields (Turn Desk separation; `sector_rotation_schedule.v1` stays DO-NOT-BUILD). (f) The word "validated" never appears on these surfaces.
- **RL-R11 (scope fence vs existing ratio homes).** Broad risk ratios stay where they live: XLY/XLP, XLU legs, copper/gold (risk radar / `sectors.pair_ratios_snapshot`), style pairs IWM/SPY, RSP/SPY, QQQ/SPY, IWF/IWD (etf_pulse), index-leadership DRIVERS (RSP/SPY, IWM/SPY, IWF/IWD, XLK/RSP). Ratio Lens owns the **tech/AI-complex taxonomy pairs** and links to, not duplicates, those homes.
- **RL-R12 (dividend-drift bar).** Per pair, trailing-12m yield differential prints; pairs >100bps use total-return legs (`{id}__level_tr` exists in `data/basket_levels`) or suppress anchor/stretch statistics. Stats never run on quarterly-rebalanced traded references (MAGS): traded references are display-only quotes; all statistics run on our EW legs (red-team M6 disposition).
- **RL-R13 (compute placement).** Builder runs in the **`oracle_offrender` job** (self-hosted, off the 67-min render path), following the `build_oracle_timemachine.py` pattern: new step + `config/dag.yml` entry; artifact committed to `site/oracledata/ratio_lens.json`; ledger `data/oracle/ratio_lens_ledger.jsonl` COLLECT_LANE=nightly-gated, atomic keep-first (red-team arch-M1 disposition). Input provenance pinned: `data/yahoo` ETF closes + `data/baskets/ohlcv` member parquets + `data/basket_levels/us.parquet` — never Oracle panel parquets (absent at render; arch-M3).
- **RL-R14 (cycles integration deferred — joint ruling required).** Running the Cycle-owned kernel (`record_series`) on Oracle-owned ratio series crosses CYC-U1 in the unruled direction. The sector_cycles "Ratios" tab is **PARKED** pending a joint Cycle+Oracle ruling (arch-M4). Display co-presentation of ratio states NEXT TO cycle state on existing pages remains legal (the row-33 kill fences tested confluence, not side-by-side display — HEALTHCARE note :181 narrowing).
- **RL-R15 (#2129 adjacency).** The pair registry defines display pairs only. It encodes NO macro-prior/complex-prior semantics for AI-capex baskets; that framing belongs to the in-flight W8b prereg (#2129, operator-ratification-gated) and is not pre-empted here.
- **RL-R16 (shared-beta disclosure).** Each pair prints the trailing 126d correlation of its two legs; above 0.85 the pair carries a "shared-tide dominated — ratio reads are second-order" chip (red-team m10). Disjointness law: pairs with name-overlap coefficient O = Σ min(w_A, w_B) > 10% are not registered; the single borderline case (mag7/ai_semiconductors, O ≈ 8.3% via NVDA) ships with the overlap printed and NVDA's contribution visible in the decomposition row.

---

## §2. Taxonomy + frozen pair registry v1

Three-level display taxonomy (curated group-level config — legal per the TI-R2 pattern; per-ticker revenue-exposure tags remain DEFERRED):

```
us_market (RSP ref)
├── megacap: mag7
├── semis: ai_semiconductors · memory_storage · semicap_equipment · non_ai_tech(analog/legacy)
├── software: non_ai_software · cybersecurity · (ai_software EXCLUDED as pair leg: 7-name overlap w/ non_ai_software; ai_infra EXCLUDED: rollup, contains ai_semiconductors)
└── ai_capex_chain: data_center_power · power_grid · nuclear_power (display context; no macro-prior semantics — RL-R15)
```

**Tier-L ETF pairs (deep history, data/yahoo, stat-bearing):**

| pair | legs | history | reads as |
|---|---|---|---|
| SMH/SPY | 2000→ | 26y | semis vs market |
| SMH/QQQ | 2000→ | 26y | semis vs big tech |
| _SOX/QQQ | 1994→ | 32y | semis (index) vs big tech |
| IGV/SMH | 2001→ | 25y | software vs semis (the software/hardware read) |
| IGV/QQQ | 2001→ | 25y | software vs big tech |
| QQQ/RSP | 2003→ | 23y | mega-growth vs equal-weight market |
| SMH/RSP | 2003→ | 23y | semis vs equal-weight market |

**Tier-M basket pairs (EW legs, seed→, survivorship-watermarked, disjoint unless noted):**

| pair | overlap | reads as |
|---|---|---|
| memory_storage / ai_semiconductors | ∅ | memory vs AI logic — the 2026 supercycle read |
| memory_storage / semicap_equipment | ∅ | memory vs equipment |
| ai_semiconductors / semicap_equipment | ∅ | designers vs enablers |
| ai_semiconductors / non_ai_tech | ∅ | AI silicon vs legacy/analog hardware |
| non_ai_software / ai_semiconductors | ∅ | software vs AI hardware |
| cybersecurity / non_ai_software | ∅ | security vs core SaaS |
| mag7 / ai_semiconductors | NVDA (O≈8.3%, printed) | mega-caps vs semis (traded ref: MAGS/SMH quote-only) |
| data_center_power / ai_semiconductors | ∅ | capex chain: power vs chips |

Registry hash frozen at W1. Known low-purity members inherited from membership.json (AVGO ~40% software post-VMware; WDC 19.9% SNDK residual; ANET networking-not-semi) are disclosed in the registry's `purity_notes`, not silently re-curated here — membership changes go through the baskets program.

## §3. Per-pair computed record (schema `ratio_lens.v1`)

`level` (rebased L), `eff_start`, `legs{a,b}` with 1w/1m/3m absolute returns, `decomp` (leg contributions to ΔL), `shape` (RL-R4), `z63`, `z252`, `pct_3y`, `pace{1w,1m,3m}` + `pace_trend` fact, `anchor{status, half_life?, ci}` (RL-R6), `washout_w` (watermarked), `state` + `stance` (RL-R8), `leg_corr_126` + shared-tide chip (RL-R16), `yield_diff_bps` (RL-R12), `drift_note`, `overlap_pct`, `watermark`. Contract: AUTHORITY all-false; FORBIDDEN keys absent; `disclosure` string embeds the expected-null declaration.

## §4. Decomposition tree (localization surface)

Per taxonomy parent: children's 1w/1m **absolute** returns side-by-side + the parent's own move — so "was XLK's move semis or software, and inside semis was it memory?" is answered by reading three rows. No ranking, no gate, no routing (RL-R3). The tree cites pair rows for detail.

## §5. Surfaces (W2, mockups-first law)

New page `ratio_lens.html` (nav: US → Sector Central submenu) + a compact context strip on sector_central. Glance tier: pair rows in plain words ("Memory vs AI chips — memory far ahead; pace fading · Watch — don't chase"), decomposition tree, EN/ZH, receipts (z, window, n, watermark, expected-null) on hover/Tier-2. dtp-* idiom if any tape-like element. Builders receive mockup screenshots before build (terminal-ui-quality-bar law).

## §6. Build waves

- **W0 (this PR):** masterplan/registration + Constitution §VII amendment line.
- **W1:** `data/oracle/ratio_pairs.json` + `engine/oracle/ratio_lens.py` (pure compute) + `scripts/build_oracle_ratio_lens.py` + offrender step + dag.yml + synapse.yml (artifact + ledger, all 11 fields, consumers) + SIGNAL_BUS regen + `tests/test_oracle_ratio_lens.py` (AUTHORITY/forbidden-keys/lane-gate/idempotency/exit-0) **added to ci.yml whitelist** + experiments registry come-back entry.
- **W2:** surfaces per §5 (after first nightly artifact exists).
- **W3:** NW `_compose_ratio_lens` (synapse consumers updated) + us_stocks per-basket context chip (display-only; no lane_hint/ranking changes) + per-pair field guide (understanding-before-backtest law: playbook first, rulers derive from it later).
- **PARKED:** sector_cycles Ratios tab (RL-R14 joint ruling); total-return leg upgrade for >100bps pairs; any promotion prereg (come-back 2026-10-15).

## §7. Clocks

- 2026-08-15: first ledger-health read (accrual only, no verdicts).
- 2026-10-15: field-guide review + decide whether any state earns a promotion prereg (needs ≥ ~40 clustered transitions; expect not yet).
- 2027-01-15: Tier-M pairs first survivorship-clean re-read; joint Cycle+Oracle ruling revisit.

## §8. Red-team record (2026-07-11, 2 Opus lanes — dispositions inline above)

Stats lane: M1 store-depth fabrication → RL-R5; M2 survivorship double-book → RL-R5; M3 CSD-locus = killed rs gate → RL-R3/R4 (locus ranking dropped); M4 STALLING smuggled reversion signal → RL-R8/R9; M5 unbounded multiplicity → RL-R2/R9; M6 dividend drift + MAGS reference → RL-R12; M7 60d-ADF unsound → RL-R6; m8 double-ledgering → single ledger unit (pair-state); m9 shape dead-band → RL-R4; m10 economic overlap → RL-R16; m11 alignment seams → RL-R7; m12 descriptive-fields-feeding-states → state function reads only registered inputs, enforced in tests; m13 63d ruler mismatch → RL-R9/R14.
Architecture lane: M1 job placement → RL-R13; M2 grammar addition + oscillator watermark → RL-R7 + §VII amendment; M3 panel inputs absent → RL-R13 provenance pin; M4 CYC-U1 reverse direction → RL-R14 (parked); M5 open-tensor/Turn-Desk duplication → RL-R3/R10; M6 FT-R6/TI-R3 not citable authority → this doc IS the registration; M7 fences restated → RL-R10; m8 #2129 adjacency → RL-R15; m9 ci.yml whitelist → §6 W1; m10 lane gate → RL-R13; m11 watermark inline → RL-R5; nit12 naming → single stem `ratio_lens` everywhere.

## §9. Amendment log

- 2026-07-11 — v1 registered (Fable), registry hash to be frozen at W1 merge.
