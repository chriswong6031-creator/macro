# China Pick Lab — A-share candidate books on forward entry ledgers (masterplan by Fable)

Date: 2026-07-09 · Status: ADJUDICATED — build authorized (display-tier)
Program id: `china_pick_lab` · Sibling of: `research/PICK_LAB_MASTERPLAN_BY_FABLE.md` (US)
Operator directive: 2026-07-09 session — "unique to China… first principles assessment of
China and its A-share market; two flagships on the surface UI; testing button to the
candidate baskets."

---

## §1 Problem statement and diagnosis

The CN board today is gated by the **US-fit confluence cascade** (T1–T4, identical
machinery), while the one validated A-share cross-sectional edge — **flat, unconditioned
3-month within-sector reversal** (Sharpe 0.67 gross full-era, FDR-survivor;
`reports/china-reversal-gated.md`) — enters only as a rank tiebreaker inside a composite
that `potential_score` then overwrites with `edge_mult=1`. This is the documented
**gate-vs-edge divorce** (root cause R2, `research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md`
§3a). The operator's "fast movers get missed by the 2D/3D gate" complaint applies
*doubly* to A-shares: a mean-reverting, retail-flow, limit-up-punctuated tape where
confirmed breakouts are already extended (which is why `CN_TIER_FRAC=0.30` was already
flattened vs US 0.45).

First-principles reading of what actually pays in A-shares (from the verdict ledger
`research/china_alpha/phase1/phase0-verdicts.md` + CN-SYS spine):

- **Mean reversion pays; momentum does not.** Cross-sectional momentum in every tested
  form is FALSIFIED on deep history. The edge is *when everyone has puked*, not *what is
  leading*.
- **Confirmation destroys the edge.** Every turn-confirmation/quality/reclaim gate on
  reversal flipped excess negative (+0.56 → −0.29 %/mo). "China edge = WHEN not
  WHICH-subsector."
- **Policy and liquidity regimes dominate.** The 10-phase cycle tape, participation
  regimes and policy impulse describe the *state machine* the tape runs on; the lab is
  the instrument to measure whether conditioning entries on these states adds anything.
- **Structure/flow beats price-derived signals.** The open (not-killed) constructions
  are flow-structural: deep-discount blocks ≤−15% (+3.45%/21d probationary),
  institutional LHB seats (+1.57%/21d accruing), A/H discount (H-side).
- **Execution is a first-class constraint.** T+1 settlement, board-aware daily limits
  (10/20/30/5%), sealed limit-ups unfillable next open. Close-to-close grading
  overstates realized entry by ~0.9–1.1pp; the ledger must not inherit that lie.

## §2 Rulings (CNPL-R1..R12)

- **CNPL-R1 (tier).** Same as PL-R1: display-tier; the lab ranks/gates NOTHING in
  production. CN board rank weights remain untouched (CN-SYS-R7 stands; flagship-2 is a
  *parallel surface lane*, not a re-weight of the existing board).
- **CNPL-R2 (frozen configs).** Same as PL-R2 (config_hash; changes ship as v2 books).
- **CNPL-R3 (ruler).** Primary ruler for all CN entry books: **21-session excess vs CSI
  300 (`510300.SS`)**, with 5/10/63-session descriptive ladder, MFE/MAE over 25 sessions.
  Inverse book graded as avoid-accuracy (expected negative). Absolute return recorded
  alongside (a policy-put tape can make everything "win"; excess is the verdict column).
- **CNPL-R4 (execution law).** Fires stamp `limit_state`/`fillable` at fire close. A
  fire that is `sealed_up` at fire close is **logged but marked unfillable and excluded
  from grading** (counted honestly in `skipped_unfillable`). Exec = next session; fill
  price = next-session **(H+L)/2** from the raw nominal store (`fill_basis="hl2"`),
  falling back to close (`fill_basis="close"`) when raw OHLC is absent. ST/*ST names are
  excluded from all book universes (5% bands + delisting tail).
- **CNPL-R5 (controls).** `cnlab_random_ctrl` + universe buy-anytime base rate are
  mandatory scoreboard columns (lift framing, same as PL-R5).
- **CNPL-R6 (context-artifact use).** CN-SYS context_only artifacts (cycle phase,
  participation, policy impulse, microstructure packets) **are legal lab-book inputs**:
  the lab is display-tier and exists precisely to accrue the track record that could
  later earn such conditioning authority (build-first doctrine). Their production
  authority (`cannot_do: rank/size/gate`) is unchanged. This does not touch the
  cross-engine-hard-gate ruling: nothing here gates a production engine.
- **CNPL-R7 (limit-data direction).** CN-SYS-R3 stands: limit-up/zt data may only be
  used in AVOID/veto direction. The lab's only limit-data book is the **inverse**
  `cnlab_chase_avoid` (expected negative). No book uses limit-up/lianban as a buy input.
- **CNPL-R8 (lane).** CN lab runs in the **asia-close lane** (CN-SYS-R11): runner after
  the CN library rebuild completes, ≤2 min budget, `CN_LANE=asia` required for any
  ledger append (non-asia invocations are honest no-ops). Artifacts must be covered by
  the ASIA job's commit globs (post-#1963 the US job excludes asia-owned data).
- **CNPL-R9 (store honesty).** Books that need runner-local stores (block tape, LHB)
  emit zero picks with a visible `data_gap` flag when the store is absent (worktree/CI
  runs); they accrue only on the runner. Never fabricate.
- **CNPL-R10 (no CN long-hold grids in v1).** Deferred deliberately: CN fundamentals
  coverage is thin, the validated observation is "junk beats quality / cheap is a value
  trap" (archetypes are context-only), and no CN long-hold program exists to receive the
  evidence. Revisit only with its own prereg.
- **CNPL-R11 (headline hypotheses).** (a) The edge-first flagship-2 (Reversion Desk)
  vs the cascade-gated flagship-1 — the gate-vs-edge divorce, finally measured live;
  (b) the 1D-velocity family on a fast tape. First operator read: **2026-08-20**.
- **CNPL-R12 (determinism + word law).** Same as PL-R12; "validated" only where already
  earned (the reversal edge may be described as validated ONLY via the existing
  allowlisted claims; new books never).

## §3 Candidate registry (20 books)

Defaults: max 12 picks/day; refire lockout 21 sessions; universe = CN search universe
(~800 names) minus ST/*ST; liquidity floor `close ≥ ¥2` and 20d turnover ≥ ¥30M (null
turnover ⇒ `liq_unknown` flag); every book excludes `fillable == False` names at fire
time (that is an executability screen, not a signal).

### Family A — the validated edge + CN-validated conditioners (Reversion)

| # | engine_id | Construction (frozen v1) | Rank by |
|---|---|---|---|
| 1 | `cnlab_rev_pure` | Deepest-quintile within-sector 3m return (the validated flat construction, as a book; NO confirmation/quality/reclaim gates — those are FALSIFIED) | reversal depth |
| 2 | `cnlab_rev_washout` | book-1 ∩ `washout_2w` (WASHOUT_BONUS is CN-gate-validated; distinct from killed turn-confirmation — cites §8) | reversal depth |
| 3 | `cnlab_rev_coiled` | book-1 ∩ (COILED or STAR) (cohort-washout CN-validated: clean15 +7.33pp n=10,784) | COILED bonus, then depth |
| 4 | `cnlab_rev_lowvol` | book-1 ∩ lowest-vol tercile (low-vol validated as sleeve tilt) | reversal depth |

### Family B — 1D velocity, CN-adapted (operator thesis on a fast tape)

| 5 | `cnlab_1d_pure` | 1D RSI-MACD cross-up ≤2 sessions AND 1D StochRSI k×d cross-up ≤8 AND 1D from_os AND rsi_10 < 70 | composite of freshness + depth |
| 6 | `cnlab_1d_phase` | book-5 base AND cycle_phase ∈ {ACCUMULATION, POLICY_PUT, LIQUIDITY_IGNITION, RECOVERY/REPAIR} (constructive phases; CNPL-R6 shadow conditioning) | phase confidence |
| 7 | `cnlab_1d_participation` | book-5 base AND participation regime ∈ {institutional_accumulation, retail_ignition} AND risk ∉ {frothy, fire_sale} | freshness |
| 8 | `cnlab_1d_blastoff` | 1D MACD cross ≤3 AND 3D MACD not yet crossed AND above_ma120 AND NOT chase_veto (the cohort the 2D/3D gate misses, minus the chase names) | 5d relative strength |

### Family C — structure/flow (the open constructions, formalized on ledgers)

| 9 | `cnlab_block_discount` | Block trade at ≤−15% discount within last 10 sessions (probationary +3.45%/21d construction; store-honest per CNPL-R9) | discount depth |
| 10 | `cnlab_lhb_inst` | LHB institutional net-buy ≥2 seats within 5 sessions (ACCRUING construction; raw hot-money flag is killed — inst seats only) | seat count |
| 11 | `cnlab_policy_put` | policy_impulse ∈ {market_rescue, easing} AND drawdown > 30% from 2y high AND above 20d low (policy-put bottom fishing) | drawdown depth |
| 12 | `cnlab_theme_laggard` | Member of a THS/theme basket with basket breadth ≥ 80% AND own 21d return in bottom half of basket AND NOT chase_veto (laggard-in-hot-theme catch-up; adjacent kills cited §8) | breadth × laggardness |

### Family D — washout/panic regimes (buy fear, first principles)

| 13 | `cnlab_capitulation_beta` | cycle_phase ∈ {CAPITULATION, DELEVERAGING} (else book is dormant) AND name drawdown > 40% (junk-beats-quality regime: buy what fell most when the MARKET capitulates) | drawdown depth |
| 14 | `cnlab_qvix_panic` | qvix_z > 2.0 AND name in deepest-dd quintile AND NOT sealed_down at fire (vol-panic extreme entry; distinct from killed SLF-051 margin direction — §8) | dd depth |
| 15 | `cnlab_star_20cm` | 688xxx/300xxx (±20% boards) only: book-5 1D confluence AND above_ma120 AND NOT chase_veto (wider limits ⇒ faster information incorporation ⇒ 1D timing worth more) | freshness |
| 16 | `cnlab_chase_avoid` | **INVERSE (avoid):** chase_veto flagged (sealed_up or 5d run ≥15%) — the legal AVOID-direction use of limit data (CNPL-R7); expected NEGATIVE 21d excess | 5d run desc |

### Family E — defensive + ablations + control

| 17 | `cnlab_lowvol_defensive` | Lowest-vol sleeve top-12 (validated tilt as standing defensive book) | inverse vol |
| 18 | `cnlab_dividend_ma120` | dividend_defensive archetype AND above_ma120 AND dd < 15% (SOE-dividend/中特估 defensive persistence thesis; archetype used in shadow only) | dividend context |
| 19 | `cnlab_flagship_nogate` | Current CN board composite rank WITHOUT the US confluence-cascade gate (the gate-vs-edge divorce ablation, measured) | composite |
| 20 | `cnlab_random_ctrl` | 12 deterministic-random liquid names, seed sha256(engine_id+asof) | random |

## §4 Flagship-2 — the Reversion Desk (surface UI, china_stocks.html)

The second flagship the operator asked for, built ONLY from validated/CN-native pieces:

- **Rank:** within-sector 3m reversal depth (deepest quintile) — flat, no gates.
- **Bonuses (rank-order only):** washout_2w (+0.5), COILED (+0.25)/STAR (+0.15),
  extension penalty (−0.5×ext) — exactly the CN-validated `_cn_bonus` vocabulary.
- **Executability screens (not signals):** drop `fillable == False`, drop ST.
- **Chips (display context, never gates):** 1D/3D oscillator state, cycle-phase,
  participation regime, chase/T+1-risk, CN_PROFILE drawdown-radar de-escalation chip.
- Computed inside `build_china_library` (all inputs in scope; O(seconds) re-rank),
  emitted as `site/factordata/china_reversion_desk.json` + a vm key, rendered as a
  featured lane on `china_stocks.html` next to the existing board (flagship-1).
- Its daily top-12 is ALSO mirrored into the lab ledger as book
  `cnlab_flagship2_mirror` (ledger id only, not counted in the 20 — it rides the same
  grading machinery so the two flagships are compared on the same ruler).

## §5 Measurement — shared machinery, CN parameters

Reuses `engine/pick_lab/` (ledger/grade/book) generalized with a market profile:

```
market="CN": benchmark=510300.SS (store.read("china", ...)),
calendar = price-store trading index (no CN calendar lib exists; the panel index is law),
fires: data/china_pick_lab/fires.jsonl (+ grades.jsonl),
fill: next-session (H+L)/2 from data/china_stocks_raw/<T>.parquet (fill_basis recorded),
executability: sealed_up at fire ⇒ unfillable ⇒ excluded from grading (honest counter),
extra fire stamps: board, limit_width, limit_state, t_plus_one_risk, cycle_phase,
                   participation_regime, policy_impulse, qvix_z
```

Floors, dedup, effective-N, ACCRUING discipline: identical to PL-R4/PL-R5. Scoreboard
adds `skipped_unfillable` and `data_gap` columns (CNPL-R4/R9 honesty).

**Snapshot:** producer block at the end of `scripts/build_china_library.py` (same
never-fatal pattern as US; the close panel, washout/COILED/gate/extension structures are
all in scope there). Enrichment join (runner): `site/chinastatedata/*.json` (phase,
participation, policy, microstructure name packets) + qvix + THS basket membership.
Persisted to `data/china_pick_lab/snapshots/<YYYY-MM>.parquet`.

## §6 Architecture and wiring

```
engine/pick_lab/cn.py                      # CN market profile + CN candidate functions
engine/pick_lab/registry_cn.py            # the 20 books above (+ flagship2 mirror id)
scripts/build_china_pick_lab.py           # asia-lane runner (≤2 min, CN_LANE=asia, exit 0 always)
data/china_pick_lab/{snapshots/,fires.jsonl,grades.jsonl}
site/labdata/china_pick_lab.json          # horizon_role: entry
site/china_stocks_lab.html                # rendered by the runner (standalone page)
site/factordata/china_reversion_desk.json # flagship-2 (produced by build_china_library)
```

Wiring: runner step in the asia-close workflow AFTER the CN library rebuild (so
tonight's snapshot + chinastatedata are on disk), with the asia job's commit globs
covering `data/china_pick_lab/` + `site/labdata/` + `site/china_stocks_lab.html`
(verify against post-#1963 glob carve-outs). Synapse: register snapshot tape
(infrastructure), lab artifact (`horizon_role: entry`), reversion-desk artifact
(`horizon_role: entry`, display), update count pins. Template edits to
`templates/china.html.j2` are verified with the vm-snapshot fast-render harness
(build_china is ~20 min; do not iterate on the full build).

## §7 UI

- `china_stocks.html` (mode="stocks"): flagship-1 board untouched; new **Reversion Desk**
  featured lane (flagship-2) + `🧪 实验室 / Lab` button → `china_stocks_lab.html`.
- `china_stocks_lab.html`: same 4-tab structure as the US lab (Scoreboard / 1D Velocity
  CN / All Books / Method), EN/ZH, empty-state honest, chase_avoid clearly NOT-buys,
  data_gap flags visible on store-dependent books. No Long-Hold tab (CNPL-R10).

## §8 Kill-registry adjacency (cited at registration)

| Book | Standing kill nearby | Why distinct |
|---|---|---|
| 2,3,4 | Reversal confirmation/quality/reclaim gates FALSIFIED | conditioners are CN-validated *bonuses* (washout/COILED/low-vol), not turn-confirmation or quality floors; book-1 anchors the flat construction |
| 5–8,15 | FALS-OSC oscillator covariate family NULL (cycle program); CN momentum FALSIFIED | those were market-level covariates / cross-sectional momentum; these are per-name entry-timing constructions, new |
| 8,12,16 | Limit-up/lianban continuation FALSIFIED as buy; CN-SYS-R3 | 8/12 use chase_veto as EXCLUSION; 16 is the inverse (avoid) book |
| 9 | Block-trade PREMIUM as accumulation FALSIFIED (wrong sign) | book 9 is the inverted leg (≤−15% DISCOUNT), the probationary +3.45%/21d construction |
| 10 | LHB raw hot-money flag FALSIFIED (wrong sign) | inst-seat ≥2 leg only (the accruing construction) |
| 12 | Basket TS-momentum + rank-IC rotation FALSIFIED; low-breadth conditioning FALSIFIED | book 12 buys the LAGGARD inside a high-breadth theme (catch-up, not continuation), name-level not basket-level |
| 13,14 | SLF-051 margin impulse FAIL/NULL | phase/QVIX conditioning, not margin ROC; direction is reversion into panic, not crash prediction |
| all | Subsector-state gates on reversal FALSIFIED (hurts vs flat in every era) | NO book gates reversal by subsector state; sector context appears only as chips |
| — | cn_supply_absorption CLOSED (#1951) | not re-proposed; book 9 is the block-tape *discount* leg, a different family |

## §9 Clocks

- **2026-08-20** — first operator read (with US lab): flagship-2 vs flagship-1 gap,
  1D family signs, dead books pruned to v2.
- **2026-10-09** — floor-eligible verdict window (n≥25/≥3mo/≥6 dates) for
  high-frequency books; alive books get gauntlet preregs.
- **2026-07-29** — CN-SYS-R7 board-weights clock (owned by the CN system program; if the
  board re-weights, flagship-1 mirror comparisons re-baseline).
