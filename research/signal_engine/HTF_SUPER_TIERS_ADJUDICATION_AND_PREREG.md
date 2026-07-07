# HTF Super-Tiers (S1/S2) + Codex Momentum-Confluence Docket — Adjudication & Pre-Registration

Date: 2026-07-06
Adjudicator: Fable (main loop)
Inputs: `MOMENTUM_CONFLUENCE_UPGRADE_BRAINSTORM_BY_CODEX.md` (external Codex brainstorm, 2026-07-06),
operator note (same morning): S1/S2 higher-timeframe tier idea.
Evidence basis: repo census 2026-07-06 (three Sonnet lanes) against `TIERED_CASCADE.md`,
`TIER_ENTRY_DEEPDIVE.md`, `DURABLE_BOTTOM_FRAMEWORK.md`, setup-species reports, ESX masterplan
graveyard, Oracle P8, and live engine code.

---

## Part 1 — Codex docket rulings (R-MC1..R-MC10)

The Codex memo's architecture read is CORRECT (trigger grammar is sound; selectivity belongs in an
orthogonal context layer; macro/regime is sizing/veto, not trigger). But most of its concrete
proposals are already built, already killed, or already pre-registered here. Rulings:

| # | Codex proposal | Ruling | Basis |
|---|---|---|---|
| R-MC1 | Cohort washout + RS repair + anti-chase overlay on T2/T3 | **DUP — no new work.** | Cohort washout = COILED (shipped, `engine/coiled.py`, OOS clean15 +7.5pp). RS repair = S7 (phase-0 MIXED, holdout CIs straddle 0 — stays phase0). Anti-chase = shipped (`stock_score._EXT_PENALTY`, F3). The "triple-lock" combo was RUN in S7 phase-0 and FAILED holdout. Codex's 315-fire `candidate_1_cohort_rs_antichase` is a re-derivation of the same lane on a different harness; our OOS evidence supersedes. |
| R-MC2 | Deep 2W washout + **calm base (ATR contraction)** + T2/T3 | **PARTIAL: calm-base leg KILLED; 2W-washout leg already owned.** | ATR-calm/VCP was FALSIFIED wrong-sign in Durable-Bottom H2 (calm-base = the LOSING side, stop-outs 46-48%, worst in program; ESX graveyard). Do not resurrect via Codex Experiment 2. The 2W-washout context leg is shipped (`setup_tier.py` W2_STOCH_WASHOUT) and is G-T2X Overlay #1. |
| R-MC3 | Sector-cycle-phase sponsorship gate | **ROUTE to G-T2X Overlay #3 (already pre-registered).** No separate build. |
| R-MC4 | Volume/participation confirmation | **KILLED (H4) except the one pre-registered slice.** OBV-div / up-down ratio / cap-spike all falsified as positive filters (H4). Fire-day turnover z>0 survives ONLY as G-T2X Overlay #2. |
| R-MC5 | Trap veto (monthly dwell / failed-fire / RS new-low) | **KILL as veto — evidence is INVERTED.** failed2 is S6 FUEL inside COILED (+4.29pp clean, −4.9pp stop-out OOS); monthly-washout filters NULL (Oracle P8 S-W3); H5 trap_state ≈ 0. Codex Experiment 4 would subtract a confirmed positive. |
| R-MC6 | Leader-reset species (near 52W high + shallow cross) | **WATCH — novel taxonomy, weak priors, no build this wave.** Shallow-is-safer already known (TIERED_CASCADE §4); near_52w_high IC 21d = −0.0155 (anti-predictive) in our measurement floor. A separate "leader reset" display species is legitimate taxonomy but earns at most a future phase-0; queued behind existing docket. |
| R-MC7 | Breadth/regime book-level permission layer | **DUP/KILLED as hard gate.** Regime display/sizing machinery shipped; hard per-name breadth gates falsified (exposure artifact, ESX graveyard). NW regime lens survives ONLY as G-T2X Overlay #4. |
| R-MC8 | Options context (GEX/charm/IV/skew) | **DUP — owned by Options masterplans.** Display/bounded-tilt only; S-FRONT-CHARM stamping pending W-OVC. No new work here. |
| R-MC9 | `entry_armed_state` sidecar + A+/A/B/C/Trap board classes | **KILL the taxonomy; the features are either shipped, killed, or inside G-T2X.** The class system depends on legs ruled dead above (trap veto, calm base) and collides with the shipped three-label board contract (P2.4) and postcross BASED/SHAKEN. W-ARM "armed" already FAILED OOS (W8-A). |
| R-MC10 | "Run G-T2X exactly as pre-registered" | **AUTHORIZE — this is the docket's best action.** G-T2X (TIER_ENTRY_DEEPDIVE §6) is locked and has never run. Execute verbatim: no threshold tuning, nulls printed. If an overlay's point-in-time input cannot be reconstructed (e.g. NW L3 regime lens history), that overlay is reported NOT-RUN — no proxy improvisation. |

**Net-new value in the Codex memo:** (a) the reminder that G-T2X is sitting unrun; (b) the
higher-timeframe exhaustion framing ("old capitulation, fresh repair") which converges with the
operator's independent S1/S2 note — handled in Part 2; (c) the leader-reset naming (watch-listed).
Everything else is dup or contradicted by our own OOS evidence. This matches the standing pattern
for external memos (~60-75% redundancy).

---

## Part 2 — S1/S2 HTF super-tiers: pre-registered descriptive study (G-HTF1)

### Operator hypothesis (verbatim intent)

- **S1**: confluence of MACD(-RSI) and StochRSI on **2W and 3D timeframes together**.
- **S2**: confluence on **3D and 1W**, plus a **pending confluence within 1 tick on the 2W**.

These sit ABOVE T1 as rarer, higher-timeframe-sponsored states. Novelty check: nothing in the repo
computes 2W MACD-RSI today (2W StochRSI exists in `setup_tier`/`entry_primitives`; weekly MACD-RSI
exists only as the `wbull` confirm leg). ESX Amendment-3 A2 (`w2_stoch_turn`) is adjacent
(single-leg 2W stoch turn) but not the two-TF confluence; A2 remains queued and is NOT consumed by
this study. Codex's base-trigger datapoint (1W MACD + 2W StochRSI: 14,544 fires, 56% stop-out,
60.6% durable-bottom, broad universe) is the unconditioned cousin — informative prior that HTF
confluence alone is NOT stop-safe and needs the 3D leg + freshness discipline.

### Frozen definitions (all completed-bucket, leak-free; formulas identical to `confluence_tiers`)

Per-timeframe "confluence-active" state on TF ∈ {3D, 1W, 2W}:
- MACD-RSI (RSI14 → EMA14−EMA60, signal EMA5) **crossed up within FW native bars**, AND
- StochRSI (14,14,3,3) K crossed up D **within CONF_W=8 native bars**, K≥D still true.

Bars: 3D via `_tf_bars(c,3)` (session buckets, known-date mapped) — identical to production.
1W via `W-FRI` completed resample; 2W via `2W-FRI` completed resample (same convention as
`entry_primitives._completed_resample`). No incomplete tail buckets in confirmed legs.

- **S1** := 2W confluence-active AND 3D confluence-active.
- **S2** := 3D confluence-active AND 1W confluence-active AND **2W pending**:
  2W MACD-RSI hist < 0, slope > 0, projected cross within **btc ≤ 1.0 native 2W bar**
  (same `-h/slope` extrapolation as `imm2`; leak-free by construction).
  - Variant S2a: MACD-pending only (stoch leg free) — primary.
  - Variant S2b: additionally 2W StochRSI K−D gap narrowing (K−D > its prior-bar value) or crossed.
- Freshness sweep (pre-declared, both printed, no post-hoc picking): FW ∈ {1, 2} native bars.
- `not_topped` veto applied as in production (3D basis).

Event = onset (state False → True). Fill = next session close (e+1, grading-law convention).

### Rulers (descriptive; identical to TIERED_CASCADE for comparability)

Per variant × market: n fires, n tickers, stop-out% under −5% hard stop / 20d triple-barrier,
clean%, MFE%/MAE, `fill_premium_20d`, median lead/lag vs T1 and T2 onsets, overlap fraction with
T1/T2-active days, 60d durable-bottom rate (reuse the bottom-study definition from
`research/bottom_signal_backtest`), 21d & 63d SPY-excess with month-block bootstrap CI
(1000 reps, seed 42), plus 120d/240d excess (long-hold ladder; overlap-noted, descriptive only).
S2 additionally: **repaint rate** of the pending-2W leg when the 2W bucket completes (provisional
basis — the S-tier analogue of the T3 repaint measurement).

Panel: the 219/224-name curated US parquet panel (`data/stocks/` in the main checkout),
2010→present. CN panel optional second pass if runtime permits; absence is printed, not hidden.

### Pre-declared display-shipping gates (this is a DISPLAY tier, not an alpha claim)

Ship S2 as a board-visible tier/badge iff: n ≥ 80 panel-wide, stop-out ≤ 48% (i.e. not worse than
T4's 43.1% by more than ~5pp), repaint of the pending leg ≤ 20% (else it ships with a provisional
flag like T3), and fill_premium not worse than T1's. Ship S1 as a rarity badge regardless of n
(expected rare), provided stop-out ≤ 50%; if n < 30 label it "ultra-rare, descriptive". Neither
tier affects board ORDER until the operator ratifies weights against the printed numbers
(§8 TIERED_CASCADE precedent). Board-ledger grading picks new tier names up automatically via the
`by_tier_cascade` slice — forward accrual is free.

Expected failure mode, stated up front: S1 (2W confirmed) may fill far above the trough
(T1 already fills ~10.9% over; a 2W confirmation should be worse) — in that case its correct role
is **durability/long-hold context**, not entry, and the verdict will say so. Nulls are printed.

---

## Part 3 — Build waves (this program)

- **W1 (parallel): G-HTF1 study** (Part 2, Sonnet build + Opus stats red-team) and
  **G-T2X run** (R-MC10, verbatim per TIER_ENTRY_DEEPDIVE §6, Sonnet build + Opus red-team).
- **W2: engine ship** — S1/S2 into `confluence_tiers.cascade()`/`tier_stream()` as
  display tiers + HTF sidecar fields, `signal_gate` plumbing (rank/wn untouched until ratified),
  board badges (US/CN/HK templates), tests, species-registry amendment.
- **W3: Terminal suites** (charting-app repo) — make the two mockup placeholders REAL:
  "Confluence Score" = T1-T4(+S) cascade bridge (per-symbol tier slice → chip + chart badge);
  "Sniper Regime" = setup/washout regime bridge (`setup_tier` / COILED state). Ships display-only.
- **W4: PRs, same-day squash-merge; memory + program notes.**

---

## Part 4 — W1 outcomes (2026-07-06, post Opus red-team)

- **G-T2X executed per §6 (first run):** OV1/OV2/OV5 KILL by the pre-registered relative rule; OV3/OV4 NOT-RUN (no PIT history — no proxies improvised). Caveats: kills are rule-triggered, not statistically decisive (base CI straddles zero); OV1/OV5 US flip sign across halves (H1+ / H2−) — re-probe eligible under the regime-change lens, come-back ≥2027-01. Full results: G_T2X_RESULTS.md.
- **G-HTF1: S1 SHIPS as a DISPLAY badge (rank-neutral).** Corrected same-ruler picture: stop-out 27.2% vs T1 30.4% (close-only; 35.0% vs 37.5% intraday-low) — a real ~3pp safety edge; 21d excess +0.90% CI [+0.16,+1.67] (S1 ⊂ T1-active, not an independent edge); fills 0.9pp WORSE than T1; fires at/after T1 → role = late HTF-sponsorship / durability badge (long-hold context), NOT an earlier entry. FW=2 ratified (641 fires; consistency with production FRESH_TICKS=2).
- **S2 PARKED per pre-declared gates** — fill_premium FAILS vs same-ruler T1 (9.6-10.1% vs 7.2%), 21d/63d excess negative-to-null, pending-leg repaint UNMEASURED. Ships as a SHADOW field only (`htf.s2` computed nightly, not displayed) so live repaint + forward evidence accrue; revisit ≥2026-10.
- **Operator note:** the original S1/S2 hypothesis expected earlier entries; the data reversed the timing read (S fires are late confirmations). The durable value is HTF sponsorship context — aligned with the long-hold program lens.
