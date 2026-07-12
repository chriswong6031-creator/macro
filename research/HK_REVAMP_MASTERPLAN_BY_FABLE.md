# HK Revamp — leadership visibility + honest participation (masterplan)

**Program owner:** Fable (main loop). **Status:** ACTIVE 2026-07-11. **Trigger:** the
2026-07 failure — the board benched the entire rallying mega-cap amplifier cohort
(BABA edge_z 1.15 / sb_z 2.31, Tencent, JD, Baidu, Xiaomi — all "UNCONFIRMED TURN")
while surfacing one flat low-beta name as the lone buy.

## 1. Confirmed diagnosis (all code-verified, as_of 2026-07-10)

1. **Per-name confirmation lag.** `engine/cycles.py:1038` reroutes every fresh tactical
   turn to COUNTERTREND BOUNCE unless `weekly_ok` (= regime=='bull', cycles.py:874),
   driven by the 12/26-**week** MACD cross — a 3-8 week structural lag behind a
   V-recovery. COUNTERTREND BOUNCE ∈ `_ALIGN_BAD_STATES` (cycles.py:1939) → tier=None →
   excluded from the board's eligible pool (`build_hk_library.py:1176`) before scoring
   matters. No flow/breadth/evidence path exists.
2. **The regime overlay is honest — and untouchable (R1).** risk_state Neutral (0.192 <
   0.30) was a CORRECT external read: DXY strong at every horizon (20d +1.4% / 60d
   +2.9% / 120d +2.2%), corr(DXY, USDCNY)≈0 (independent channels, both risk-off), VHSI
   live, HKD peg weak-side. Broad breadth was weak and falling (pct_above_50 21.6;
   pct_above_200 37.8→28.4 over 20d). The tape was a NARROW leadership rally.
3. **The architectural gap:** no organ can express "narrow mega-cap leadership turn +
   inbound flow against weak broad breadth." The regime gate keys on broad/external;
   the name gate benches the leaders; the signal falls between.

## 2. Measured evidence (both studies rerunnable, scripts in `scripts/`)

**Study A — confirming-turn replay** (`study_confirming_turn_replay.py`; n=220
episode-collapsed firings, southbound window 2024-07→2026-07 only):
- The southbound-flow leg adds NOTHING forward-measurable to a price turn: permutation
  deltas all null (abs20 −1.3pp p=.398; abs40 +0.9pp p=.658; held40 −0.9pp p=.917).
- Swing-hold advantage (50.2% vs 33.4% base) belongs to the PRICE structure — flow-less
  turns match it (50.5%) — and is split-half unstable (fwd40 +10.6% → +0.1%).
- HSI-excess of firings ≈ 0. Era split impossible (no southbound before 2024-07).
- **Closes this construction only** (per-name southbound accumulation as a turn
  confirmer, 20/40d, 2024-26). Re-run gate: ≥3-5y southbound history (~2027+).

**Study B — narrow leadership-cohort thrust** (`study_hk_narrow_leadership_turn.py`):
- Flow-required primary: **n=0** in the southbound window (insufficient-n, NOT a kill).
- Price-only control (n=15, 2016+, era-stable both halves): the thrust does NOT precede
  a broad HSI advance — HSI 40d mean −1.73% vs +1.55% narrow-breadth base rate, month-
  permutation p=.982 (wrong tail); 100% of episodes printed a lower HSI low within 40d.
- **But the cohort's OWN forward return is +4.9%/60d while HSI stays flat** — the state
  is real as CONCURRENT participation; its historical expression is the leaders, not
  the index.

## 3. Rulings

- **HKRV-R1 (overlay untouchable).** No re-weighting of `engine/hk_global.py` that
  flips 2026-07-10 to Risk-on. The DXY/USDCNY/peg legs earned their read. Any overlay
  change requires its own falsifier study + operator ratification.
- **HKRV-R2 (Confirming Turn is a descriptor, not a signal).** The new per-name state
  ships as a CONCURRENT description: "printed washout reclaiming above a rising
  short-term average; mainland Connect money adding." FORBIDDEN copy: any forward-edge,
  "confirmed bottom," "flow confirms," or hold-rate claim. Stance vocabulary: "watch —
  don't chase" tier. Southbound is CONTEXT ("who the marginal buyer is"), never a
  confirmer (Study A). Half-size framing only as operator-discretion display copy.
- **HKRV-R3 (participation is event-based and present-tense).** The leadership lane
  fires on a cohesion THRUST event (fraction of cohort above rising 10d MA crossing
  0.30→≥0.60 within 10 sessions), never a standing-state score (IHM §2.3 binding).
  Copy MUST be present-tense participation ("the leaders are participating; broad
  breadth has not confirmed") and MUST print the Study B null: thrusts historically did
  NOT precede broad advances; the cohort's own return is the honest framing.
- **HKRV-R4 (construction guards inherited).** Flow leg required in the participation
  construction (cn_supply_absorption kill: price-only ≡ momentum). Cross-sectional
  residual-momentum ranking stays dead. Coincident thrusts stay display-tier (MCO
  kill). Era-split law applies to any future study.
- **HKRV-R5 (authority fence).** Nothing in this program feeds rank/size/gate/K-counts.
  Board admission of the new state is SCREEN-tier visibility (the board's existing
  trust_tier). Promotion paths: fresh preregs only, earliest when southbound ≥3y.
- **HKRV-R6 (forward ledgers).** Both organs stamp forward ledgers (fwd20/40/60,
  absolute + HSI-excess, expected-NULL framing, printed on-surface — audit idiom).
- **HKRV-R7 (surfaces are mockups-first).** No surface builds before operator-ratified
  mockups (terminal-UI quality bar; DESIGN_DOCTRINE glance-tier vocabulary).
- **HKRV-R8 (program interfaces).** index_momentum.v1 tags (washout_turn, us_confirm,
  turn_breadth) join as ADDITIONAL witnesses when present (IHM owns them). mag7_regime
  rendering belongs to the Mag7 Command program — this program only consumes its
  artifact if/when it renders. Flow-leaders desk: no overlap (different universe/lens).

## 4. Waves

| Wave | Scope | Tier |
|---|---|---|
| W0 | this masterplan + both study scripts | docs |
| W1 | Confirming Turn: `confirm` witness bundle in `cycles.ladder_state` (default None = US/CN byte-identical), new state + `cycle_ontology` crosswalk + STATE_DISPLAY EN/ZH, alignment near-tier admission, HK wiring in `build_hk_library`, tests | engine, display |
| W2 | Leadership participation organ (`engine/hk_leadership.py`): cohort cohesion thrust event + southbound context + forward ledger; additive/fail-open sibling of `hk_washout_watch` | engine, display |
| W3 | Surfaces: mockups → ratification → HK board strip + macro chip (bilingual, Tier-2 receipts printing the nulls) | UI |
| W4 | Factor/EM adds: MAGS + ^KS11 collectors; HSTECH/HSI RS chip; AH-premium compression chip; southbound aggregate z; HIBOR−SOFR spread chip; rate-cut path chip (ZQ−DFF; also serves the US fed-vs-thesis divergence); USDCNH basis; EM−DM RS tile; ASHR−FXI spread; VHSI 252d percentile; `signals_oil` staleness repair | collectors + display |
| W5 | Robustness: eligible=0 health banner; southbound staleness → trading days; southbound added to `hk_freshness` sentinel; 73/160 universe-coverage logging; `_ALIGN_BAD_STATES`↔`_CYCLE_BLOCK_STATES` cross-reference; tests (ci.yml whitelist) | fixes |

## 5. Clocks

- 2026-07-25: first forward-ledger read on both organs (did the 07-01..07-10 cohort
  episode grade as participation-without-broad-advance, per Study B?).
- 2026-08-15: W4 chips freshness audit; mockup ratification checkpoint for W3 if not done.
- 2026-10-15: program review — extend, park, or register preregs.
- 2027-07 (earliest): southbound ≥3y — Study A/B flow-leg re-runs become possible.

## 6. Kill-registry appends

None. Study A/B nulls are construction-specific and recorded here (HKRV-R2/R3 copy
law), not family kills. "Not found yet" ≠ "does not exist."
