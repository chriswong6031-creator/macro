# Wave-5 pre-registration v2 — BASED / RETEST: post-cross re-admission (written BEFORE the runs)

> Authored by Fable 2026-07-02 (v1), revised to v2 SAME DAY after a 4-reviewer adversarial panel
> (findings + resolutions logged in §9; no runs occurred between v1 and v2). Fifth wave of the
> `DURABLE_BOTTOM_FRAMEWORK.md` program — its §2 tripwires and §4 constitution bind verbatim.
> Problem statement: `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md`. This file is a
> FIXED INPUT for runner sessions: hypotheses, definitions, and gates may not be "improved" mid-run.
> Later additions go under §9 with multiplicity acknowledged.

---

## 0. The question, and its honest scope

The confluence gate admits only "just-crossed / about-to-cross" (`FRESH_TICKS=2` + not-topped).
The owner observes (June 2026: MCD/KO/COKE) that US names which crossed 1–3 weeks ago and did NOT
launch — fading/basing near the cross — can be superior entries, especially when the sector leads.
Live recon corrected the anecdote's shape: these are **post-cross retraces toward the base**
(KO never closed above its cross bar; MCD broke its pre-cross 10d low), not tight flags.

Two candidate re-admission paths, both co-primary (§5):
- **BASED** (a state): post-cross window, never launched, structurally intact above the trough.
- **RETEST-FIRE** (an event): a fresh 2D RSI-MACD re-cross fires *inside* that window (KO 06-26 is
  a live instance) — currently killed by the 3D `macd_bear` veto / `recent3` expiry.

**Honest scope limit (panel critical #2):** both candidates operate on the confluence-cascade /
RSI-MACD layer. They **cannot rescue MCD**, whose live blocker is `signal_quality`'s 200MA-reclaim
filter (MCD trades ~10% below its 200MA). MCD motivates sub-form (c) of the problem audit; that
sub-form (a 200-reclaim relaxation conditioned on cohort leadership, audit D3) is explicitly
DEFERRED to a future registered wave. KO is the flagship in-scope case.

**Decision this wave feeds:** whether BASED and/or RETEST earn a display chip + forward-ledger
fields on the US boards. Never a hard gate, never a rank change, this wave.

## 1. Priors on record (ledger-consistent; v1's strongest prior was struck by the panel)

- ~~"The confirmation-wait is worth ~11pp; a held base is that wait at ~0 premium"~~ — STRUCK.
  It contradicted the framework's own H0 ledger row ("the 11pp stop gap IS the wait itself; no
  causal stratum recovers it") and mis-analogized: the keeper's wait selects **advance**
  (reclaim-and-hold above a level); BASED selects **flatness**. These are different behaviors.
- Corrected prior: post-cross conditioning at j≥7 is a *different information set* than the H0
  bar-t features (H0 does not bind it), but the only *validated* post-cross selection is
  advance-shaped. Whether flatness carries any selection is exactly what is tested. Stop-out
  improvement vs P2: **uncertain**. Clean15/dead-money: the live axes. To measure whether the
  keeper's *level-content* (not mere flatness) drives any edge, E_BASED is stratified by
  `ext_j ≥ 0` vs `< 0` and by above/below-200MA at entry.
- Cohort interaction: any real edge should CONCENTRATE in sector-favorable cells (rotation-queue
  mechanism; validated cousin H6). A uniform edge is suspicious. The 63d-leadership stratifier is
  a NEW, UNVALIDATED feature (weakly correlated with h6 cohort, r≈−0.12, so both run) — it must
  clear sign-stability on its own before being read as confirming the owner's intuition.
- Unconditioned staleness is known-bad (ENTRY_QUALITY >20 trading-day band). The claim under test
  is that the structurally-intact, never-launched SUBSET beats its correct parent class (P2).
- Vol confound on record: BASED mechanically selects low realized vol; fixed barriers flatter it
  on stop5. The ATR co-primary (G5b) decides whether any stop edge is real.

## 2. Fire sets & panels

- Triggers: `base3d` and `m2d_s3d` (tuning_harness VARIANTS), analyzed separately.
- **Ladder dedupe: 21 trading days per name, first fire kept** (a ladder study must not spawn
  overlapping ladders off 8d-spaced burst fires; the wave-4 8d convention is retained only as a
  diagnostic re-read). Dedupe selects on prior fires only (backward-looking).
- Panels: deep US `data/stocks/*.parquet` (211 names, min_bars 1500, eval_start 2012-01-01; time
  halves pre/post 2020-01-01; ticker halves even/odd) → decisive OOS on baskets
  `data/baskets/ohlcv/*.parquet` (2,336 names, min_bars 1000, eval_start 2015-01-01). CN deferred.
- Fill rule: entry policies fill at `entry_bar + 1` close; `compute_outcomes`/`compute_outcomes_w2`
  reused verbatim (wave1.py:180, wave2.py:272). Cohort machinery: wave-2 d-matrix with FIX-1
  ISO-string serialization and FIX-2 TF-native rolling order.
- **Common fully-observed fire set (panel must-fix):** a fire enters the study ONLY if the LATEST
  possible entry has a full window: `i + LADDER_MAX + 1 + 126 ≤ n` (LADDER_MAX = 30). Every policy
  is scored on this identical fire set — no per-policy end-of-panel censoring.

## 3. The post-cross ladder, states, and entry policies (all causal at day j)

For each deduped fire at signal bar `i` (cross close `Pc = close[i]`), daily `j = i+1 .. i+30`:

- `maxup_j = max(close[i..j])/Pc − 1` (bars ≤ j only); `ext_j = close[j]/Pc − 1`
- `trough_ref T = min(close[max(0,i−90) .. i])` — exactly the wave-1 capit window (91 bars incl. i).
  Sole primary (v1's 3-variant fork was shown vacuous on the anecdote names; a divergent-subset
  diagnostic replaces it: report BASED verdict deltas only on fires where the 10d-min or Pc×0.95
  variants actually change BROKEN).
- `BROKEN_j`  : `min(close[i+1..j]) < T × 0.97`
- `OBP_j` (**OB-persist**): 3D StochRSI k or d printed ≥ 80 on ANY bar in `[i..j]` (sticky — a
  transient overbought excursion marks the launch as begun; panel critical #1, the JNJ loophole)
- `LAUNCHED_j`: `maxup_j > 0.05` OR `OBP_j` (**mechanism-anchored: the launch threshold IS the
  ext ceiling** — one number, no hand-set band; v1's [−6%,+5%] ext band is deleted)
- **`BASED_j`**: `j − i ∈ [7, 24]` AND NOT `LAUNCHED_j` AND NOT `BROKEN_j`.
  (No explicit ext floor: the floor is the trough line itself via BROKEN — name-specific,
  mechanism-true. The implicit ceiling is +5% via maxup.)

**Entry policies (one entry per fire per policy; identical fire set; fill at bar+1 close):**
- `E_FRESH` — at `i+1`. The incumbent baseline.
- `P1 = E_STALE_i7` — enters at `i+7` for EVERY fire in the common set, with **NO launch, break,
  extension, or OB condition** (a fire that launched or broke in `[i+1,i+7]` is entered at i+7 at
  whatever price prevails). Pure immortal-time floor; reported, never a gate anchor.
- `P2 = E_SURVIVE_i7` — enters at `i+7` iff NOT `LAUNCHED_{i+7}` AND NOT `BROKEN_{i+7}`. **The
  correct parent class**: isolates the 7-day survival option. All BASED-vs-parent gates anchor here.
- `E_BASED` — at the FIRST `j ≥ i+7` with `BASED_j`. Fires eligible for P2 but never producing a
  BASED entry are counted as informative dropout and reported (drop fraction + a Kaplan-Meier-style
  fire-survival curve over `[i+1, i+24]`).
- `E_DIP7` (**placebo**) — enters every P2-surviving fire at its LOWEST close in `[i+7, i+24]`
  ("buy the local dip, no state required"). E_BASED must beat this (G5i) or the chip is a dip-buy
  in disguise. NOTE: E_DIP7 is deliberately hindsight-located (the placebo needs to be the
  strongest dip-buyer); it is a benchmark, never a candidate.
- `E_LAUNCHED` — first `j` with `LAUNCHED_j` (negative control; G5e).
- `E_RETEST` (co-primary, **frozen parameterization, non-sweepable**): first `j ∈ [i+3, i+30]`
  where a fresh 2D RSI-MACD cross-up fires — located via `to_daily(cross, known, di, 'event')`
  known-date mapping (NEVER the resample bin label; assertion required that no fill precedes the
  2D bar's known date) — AND NOT `LAUNCHED_j` AND NOT `BROKEN_j` AND 3D RSI14 < 65.
  Deliberately absent: the 3D `macd_bear` veto and the `recent3` window (the two live blockers
  under test). Deliberately present: the launch/broken/OB-persist guard (panel: RSI14<65 alone is
  weaker than the stoch-OB guard it replaces).

## 4. Axes, honesty lenses, and descriptives

Per policy × trigger × panel: `stop5`, `clean15`, `dead_money`, `premium-over-trough`, `mfe63/
mae63`, `days_to_10`, n, per-name stats.
- **ATR co-primary:** `stop_atr`/`clean_atr`, stop = 1.5×ATR63, target = 4.5×ATR63, where ATR63 =
  the wave-1 ewm `atrp` basis (wave1.py:357-370) **evaluated at the fill bar using only bars ≤
  fill_idx** — no forward window, explicit §7 checklist line.
- **Inference (all gate clauses):** point estimates must clear their thresholds at the **90%
  block-bootstrap lower bound, clustered on (name × 63-trading-day calendar block)**. Gate n-floors
  additionally require ≥60 distinct names and ≥40 distinct 63d calendar blocks contributing.
- Splits: time halves, ticker halves, **excl-staples+healthcare**, **excl-2025-01-01+ entries**.
- Strata: h6 cohort ≥ 0.40; 63d leadership (TRAILING: peers' mean `close[i]/close[i−63]−1` minus
  SPY same, bars ≤ i only — likewise 252d chronic-laggard); vol quintiles (ATR63%); `ext_j ≥ 0`
  vs `< 0` at entry; above/below-200MA at entry; H2-contrast cell (`capit_age ≥ 15 ∧ atr_crush
  ≤ 0.60`, wave-1 definitions, at the entry bar).
- **Descriptives (headline, non-binding):**
  - *visibility-at-liftoff*: among fires whose E_FRESH outcome was clean15=1, fraction where
    `tier_stream` showed no eligible tier on the liftoff day — defined as the first bar with close
    ≥ 1.05 × (min close over `[fill, that bar]`) — vs visibility under BASED. Descriptive only.
  - *natural re-trigger rate*: fraction of BASED windows containing a fresh incumbent T1/T2/T3
    re-fire (how much the gate already self-heals).
  - *live-board sizing*: BASED/RETEST counts on the current surfaced us_standouts universe, AND
    separately the count of audit-class names excluded UPSTREAM by `_entry_ok`/alignment (the
    MCD-shaped population the board never sees). Owner reviews at ship time; not a numeric gate.
  - *anchor-divergence study (ship-blocking check, panel critical #4):* compute BASED on both the
    study raw-cross anchor (resample '3B') and the live `signal_gate` take_date anchor
    (session-grouped 3D) across the live universe; report the `j−i` and `ext` delta distribution.
    The SHIPPED chip anchors on the live take_date. If anchors disagree by >2 bars on a material
    fraction (>20%) of live names, the ship is blocked pending reconciliation.

## 5. Multiplicity

Co-primaries: **two ship decisions** — BASED chip; RETEST marker. Margins on the RETEST family are
tightened (Holm-style) relative to BASED (see G5r). Diagnostic cells (trigger `base3d`, the 8d
dedupe re-read, trough divergent-subset, all strata) cannot ship anything this wave; they may only
be PROMOTED to a future wave's primary. The band-edge stability sweep (G5j) is a GATE, not a
license to pick the best cell.

## 6. Gates (pre-committed; bootstrap lower bounds per §4)

- **G5a existence (deep panel, primary = E_BASED on m2d_s3d):**
  n(E_BASED) ≥ 400 (+ name/block floors) AND
  stop5(E_BASED) ≤ stop5(P2) − 3pp AND clean15(E_BASED) ≥ clean15(P2) − 1pp AND
  non-inferior to E_FRESH (stop5 +1pp / clean15 −2pp / dead_money +1.5pp margins) AND
  **strictly better than E_FRESH on ≥1 primary axis by ≥ 1pp** (no Pareto-loss chip).
- **G5b ATR honesty:** the G5a stop clauses hold on `stop_atr` (vol-artifact kill).
- **G5c anecdote independence:** G5a inequalities at half margins hold excl-staples+healthcare AND
  excl-2025+ entries.
- **G5d baskets OOS:** G5a direction replicates; n ≥ 1,200; both time halves same sign.
- **G5e launched control + named fixture:** stop5(E_LAUNCHED) ≥ stop5(E_FRESH) + 3pp OR
  clean15(E_LAUNCHED) ≤ clean15(E_FRESH) − 3pp. AND the **JNJ-2026 fixture**: neither E_BASED nor
  E_RETEST enters JNJ (cross 2026-06-05) before its launch leg — fails on sight if violated
  (verified pre-run as a unit test; OB-persist is the mechanism that must exclude it).
- **G5f H2 distinction (rewritten):** evaluated only if pooled |stop5(E_BASED) − stop5(P2)| ≥ 2pp.
  Requires stop5(E_BASED) − stop5(P2) ≤ −1.0pp INSIDE NOT-h2_good cells (n ≥ 300), AND E_BASED
  inside h2_good not worse than P2 inside h2_good by > 2pp (the falsified object must not be
  where the edge lives, nor a hidden disaster).
- **G5g per-name majority:** among names with ≥3 fires in both E_BASED and P2: fraction where
  E_BASED stop5 ≤ P2's AND clean15 within 2pp ≥ **55% deep / 52% baskets**, ticker-half stable
  (consciously above 50% — closes the wave-4 median-carried soft spot).
- **G5i placebo:** E_BASED beats E_DIP7 on stop5 by ≥ 1pp AND clean15 not worse by > 1pp.
- **G5j definitional stability:** the G5a verdict signs are unchanged under maxup-threshold
  {4%, 5%, 6%} × trough tolerance {0.96, 0.97, 0.98} (3×3 sweep). A verdict that flips on one
  knob edge is not a verdict.
- **G5r RETEST (co-primary family, tightened):** frozen §3 params; non-inferior to E_FRESH
  (stop5 +0.5pp / clean15 −1pp) AND to E_BASED (stop5 +0.5pp / clean15 −1pp); overlap audit ≤ 50%
  of E_RETEST entries already incumbent-eligible that day; JNJ fixture (G5e) applies; the shipped
  marker discloses the 2D provisional-repaint flag (reuse `sig.provisional` machinery, measured
  23.8% US repaint).

**Ship rule & shape (display-only, minimal surface):** BASED chip iff G5a–G5j; RETEST marker iff
additionally G5r. Ship = fields nested under `row['coiled']` exactly like the `coiled_fire`
precedent — `based` (bool), `based_ext` (float, ext at surfacing), `based_ticks` (int),
`retest` (bool), `retest_src` ('m1d'|'m2d') — **NO `entry_signal` status change this wave**
(the based_watch status + W6 fix-7 map interaction is deferred until forward grades justify it;
the known card-vs-chip tension is accepted and documented). Live computation anchors on
`signal_gate` take_date (§4 anchor study). **Required ship-PR touch list:** `engine/coiled.py`
(based/retest computation), `scripts/build_stock_library.py` (~1567-1576 chip injection),
`scripts/grade_us_board.py` `_extract` allowlist (~:160-196 — REQUIRED, else the fields snapshot
but never grade), `templates/dashboard.html.j2` chip (dual-span i18n, LEX strings). NOTHING
touches `BUYABLE_TIERS`, setups.json, or discovery gating. Kill rule: failed gates → candidate
does not ship; falsified cells appended to DURABLE_BOTTOM_FRAMEWORK §8 with numbers.

## 7. Leak-audit checklist (runner fills in the report; every line explicit)

1. Common fully-observed fire set: `i + 31 + 126 ≤ n` enforced once for all policies.
2. Per-policy fill = entry_bar + 1; no policy fills before its signal is knowable.
3. E_RETEST 2D cross located via `to_daily(...,'event')` known-date path; assertion: no fill
   precedes the 2D bar's known date.
4. ATR63 for barriers computed from bars ≤ fill_idx only (ewm atrp basis, read at fill).
5. Leadership/laggard returns TRAILING, windows end at bar i.
6. `maxup_j`/`BROKEN_j`/`OBP_j` windows bounded ≤ j; OB-persist scans `[i..j]` only.
7. trough_ref uses `close[max(0,i−90)..i]` — pre-entry bars only, identical to wave-1 capit basis.
8. P1 "survives to i+7" = bar existence + §2 common-set membership ONLY (no price condition).
9. Cohort matrix ISO-serialized (FIX-1); TF-native rolling before to_daily (FIX-2).
10. 21d dedupe keeps first fire, backward-looking only.
11. dead_money end-of-panel dilution: common-set guard makes windows full; state so.
12. tier_stream (visibility) is completed-bucket basis; provisional divergence disclosed.
13. E_DIP7 is hindsight-located BY DESIGN (placebo benchmark only, never a candidate).
14. JNJ-2026 fixture unit test runs BEFORE the panel runs.
15. No label field used as an input anywhere.

## 8. Deliverables

`research/entry_timing/wave5.py` (imports wave1/wave2 primitives; new code only for ladder,
policies, ATR barriers, bootstrap), `WAVE5_REPORT.md` (all axes/splits/gates, KM fire-survival
curve, drop fractions, leak audit §7 filled, anchor-divergence table), parquets under
`research/entry_timing/_out/`. Verdict rows appended to `DURABLE_BOTTOM_FRAMEWORK.md` §8.

## 9. Amendment log (v1 → v2, adversarial panel 2026-07-02, pre-run)

| # | reviewer | severity | finding | resolution in v2 |
|---|----------|----------|---------|------------------|
| 1 | mechanism | critical | JNJ qualifies as BASED (verified: fill 06-22, +9.4% run after) — transient-OB loophole + ext/maxup mismatch | OB-persist `OBP_j`; launch threshold = ext ceiling = 5%; named JNJ fixture in G5e; ext band deleted |
| 2 | mechanism | critical | No candidate rescues MCD (200MA-reclaim block, different layer); prereg advertised what it can't produce | §0 honest scope; MCD sub-form deferred to a future registered wave; KO = flagship case |
| 3 | mechanism | major | Zero-premium prior contradicts H0 ledger; keeper selects advance, BASED selects flatness | Prior struck & rewritten (§1); ext≥0 and above/below-200 strata added |
| 4 | mechanism | major | trough 3-variant fork vacuous (byte-identical on anecdotes); ext band [−6,+5] anecdote-fitted | Single mechanism trough + divergent-subset diagnostic; band replaced by mechanism anchors; G5j stability gate |
| 5 | statistics | critical | E_STALE_ALL "survives" ambiguity → immortal-time collapse | P1 redefined availability-only; correct parent P2 added; gates re-anchored to P2 |
| 6 | statistics | critical | Parent class must isolate the survival option; informative dropout unhandled | P1/P2/E_BASED decomposition; dropout fraction + KM curve required |
| 7 | statistics | major | n≥400/±1pp hollow under overlap+clustering | 90% block-bootstrap lower bounds; name/block floors; dedupe 21d primary |
| 8 | statistics | major | G5r let a diagnostic ship (multiplicity leak) | RETEST promoted co-primary, params frozen, margins tightened |
| 9 | statistics | major | G5a could pass a Pareto-loss candidate; G5f ill-defined near zero | Incumbent-superiority floor added; G5f rewritten absolute (+guard) |
| 10 | statistics | major | Wave-4 per-name soft spot inherited ungated | G5g per-name majority 55/52 |
| 11 | statistics | minor | Entry endogeneity (buys local flatness) flatters barriers | E_DIP7 placebo + G5i |
| 12 | statistics | minor | ">60 names revisit" was a hidden gate | Demoted to owner-review descriptive |
| 13 | causality | major | Differential end-of-panel censoring across policies | §2 common fully-observed fire set |
| 14 | causality | major | RETEST bin-label vs known-date 1-bar leak | §3/§7 event-mapping requirement + assertion |
| 15 | causality | major | ATR63 unimplemented/under-specified; co-primary could leak | §4 causal ATR spec + checklist line |
| 16 | causality | minor | Leadership/laggard window direction unspecified | TRAILING pinned (§4) |
| 17 | causality | minor | visibility local-min knob unpinned | Pinned: min close over [fill, bar] (§4) |
| 18 | causality | minor | trough window off-by-one vs wave-1 capit | Aligned to `close[i−90..i]` |
| 19 | engine | critical | Study anchor (resample 3B) ≠ live anchor (§7 take_date) | §4 anchor-divergence study; ship anchors on take_date; >2-bar/20% block rule |
| 20 | engine | critical | Ledger fields not gradeable (_extract allowlist) | §6 field names pinned; grade_us_board patch on required touch list |
| 21 | engine | major | based_watch would be rewritten by W6 fix-7 urgency map | entry_signal change DEFERRED; pure chip ship (coiled_fire precedent) |
| 22 | engine | major | BASED names may not reach the board (inclusion upstream) | §4 sizing split: surfaced universe vs upstream-excluded count |
| 23 | engine | minor | RETEST inherits 2D provisional repaint undisclosed | G5r provisional disclosure |
| 24 | engine | minor | RETEST lacked its own blasted-off guard | Launch/broken/OB-persist guard added to E_RETEST |

### Post-panel amendments (owner testimony 2026-07-02, registered PRE-RUN: wave5.py authored but
### zero panel outputs exist; verified `_out/` contains no wave5 artifacts at registration time)

**Owner's mechanism testimony (June-2026 episode):** the defensive bases were caused by capital
refusing to fully rotate out of semi/memory leadership until that trade CONFIRMED its unwind —
partial flows held the bases (absorption) but breakout momentum arrived only with the donor
unwind. Healthcare made higher highs (rotation arrived there first); staples (MCD) had shakeouts
below shallow lows to destroy weak hands and absorb liquidity before launching.

| # | amendment | registration |
|---|-----------|--------------|
| 25 | **DONOR-UNWIND stratum (wave-5b).** At each entry bar: donor = top-1 GICS sector by trailing 126d equal-weight return (from the sector d-matrix members, bars ≤ entry only); `donor_unwind` = fresh weekly RSI-MACD bearish cross on the donor EW composite within the trailing 4 weeks OR donor 20d EW return < 0 while still top-ranked. PREDICTION (two-sided commitments): clean15 of E_BASED concentrates in donor-unwind cells; dead_money concentrates in donor-intact cells. Must hold across the FULL panel (2012+), not only 2025-26 — an effect that exists only in the anecdote's episode is a regime story, not a mechanism. | Diagnostic ONLY this wave: computed on the wave-5 fire parquets AFTER the §6 gate verdicts are frozen; cannot affect the wave-5 ship decision; promotable to a wave-6 primary. Multiplicity: +1 registered stratum family (2 cells). |
| 26 | **SPRING stratum (wave-5b).** Within `[i+1 .. entry_j]`: `spring` = (min close < pre-cross 10d min `min(close[i−10..i−1])`) AND (close[entry_j] > that 10d min) — undercut the SHALLOW low and reclaimed it by entry, while never breaking the cycle-trough BROKEN line (else the fire is already excluded). Price-only by design (H4's falsification bars volume legs). PREDICTION: spring-present E_BASED entries have higher clean15 / lower dead_money than no-spring; effect expected strongest in low-beta/staples cohorts. | Same wave-5b discipline as #25. Multiplicity: +1 stratum family. |
| 27 | **Age-ceiling suspicion on record.** The owner's mechanism implies base duration is EXOGENOUS (donor's unwind timeline), so the registered [7,24]-day window may expire good bases right before launch in slow-unwind regimes — the FRESH_TICKS mistake reproduced one level up. The window STANDS for wave-5 (no mid-flight tuning); the ladder edge-vs-j diagnostic curve is the pre-named arbiter, and a wave-6 window extension is pre-authorized as a registered follow-up iff the j-curve shows the edge persisting to the ceiling. | Note only; no definition change. |
