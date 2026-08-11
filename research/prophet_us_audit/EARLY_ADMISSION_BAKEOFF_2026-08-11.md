# Early-admission construction bake-off — 2026-08-11

**Charter:** operator order 2026-08-11 — "we should be admitting names that have conducted a
STOCH-RSI 3D crossover (under the 20 line; extra merit after touching the 0 bound) with a
1D MACD-RSI crossover as confirmation … expand further to find the best possible one. Actually
the grey dot is prob the best possible one." Plus: "these STOPs tend to occur literally at the
lowest point sometimes … instead of stopping when the MACD rolls over, it stops right when the
MACD has already made its lowest histogram level and is starting to arch up."

**Program home:** `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(a)/(b)/§6.9.
This file EXECUTES the two MEASURE-FIRST replays ordered there on 2026-08-08 (the early_dot
conditional table and the sell_confirm momentum-context split) and extends them with the
operator's new candidate construction and a theme-breadth conditioning lane.

**Tier:** measurement / display — no gate, rank, veto, or engine change ships from this file.
Promotion of any construction goes through the program's own sequencing (§6.0/§6.6) with a
fresh prereg. The word "validated" does not appear here as a claim.

**Non-duplication:** plan-level lateness (freeze, publication lag, entry placement) is already
measured in `ENTRY_LATENESS_FORENSIC_2026-08-07.md`; the veto economics in
`RECLAIM_VETO_PACKET_2026-08-05.md` (`DNR:KILL-200DMA-RECLAIM-VETO-FLAT` binds — nothing here
touches the veto); the regime-block anatomy in
`../GOLDEN_ORACLE_REGIME_BLOCK_FORENSIC_2026-08-10.md`. This file measures the SIGNAL
CONSTRUCTION layer only: when does each candidate trigger fire relative to the washout low it
is trying to catch, and what does an entry at that fire look like for a stop-anchored swing
process.

**The operator's process (the lens this study is scored under, per their 2026-08-11 note):**
the engine is a FILTERING machine, not an execution bot. The operator picks from surfaced
candidates, places a tight stop under the washout low, cuts losers, lets winners run. What the
gate must optimize is therefore NOT pooled win-rate — it is (1) how close to the decline low a
candidate is SURFACED, (2) whether a tight stop planted at that entry survives, (3) how much
of the subsequent leg is capturable. Recall over precision; the operator is the second-stage
filter (§6.9 R8 reframe). A construction that fires earlier with more false bounces is
acceptable IF the falses are cheap under the stop discipline and a second-stage discriminator
(theme breadth) can separate them.

---

## §1 Constructions under test (frozen before any outcome was computed)

All indicators use the house parameterization (Terminal `signal_layer`, receipts in the
regime-block forensic §2): RSI 14; StochRSI 14/14/3/3 with 80/20 bands; MACD-on-RSI 14/60/5.
3D bars resample daily bars in completed non-overlapping 3-session buckets on the engine grid;
a 3D-grid signal is knowable only at its bucket's LAST session close (G0.4). All fires are
stamped at the daily session T on which the condition became knowable; entry basis = close(T)
(sensitivity column: next session's open).

| id | construction | definition |
|---|---|---|
| **C0** | incumbent BUY (comparator) | `buy`/`rebuy` markers as published in `site/signals/<T>.json` (the store Prophet consumes) — 3D MACD-RSI bull cross + recent 3D StochRSI oversold up-cross + weekly confirm + RSI cap, as shipped |
| **C1** | operator proposal | 3D StochRSI bull cross (%K up through %D) with both lines < 20 at cross → CONFIRMED by the first 1D MACD-RSI bull cross (line up through signal) within the next 10 sessions; fire at the confirm session |
| **C1z** | C1 + zero-bound cohort | C1 fires where 3D %K printed ≤ 2 within the 10 3D-bars before the cross (reported as a split of C1, not a separate lane) |
| **C2s** | grey dot, as published | `early_markers` dates from `site/signals/<T>.json` — the engine's `m2d_s3d_early` leg (`engine/signal_quality.py:210`): 3D StochRSI %K×%D bull cross with %D-dipped-<20-within-8-bars context, while the prior CLOSED 2D RSI-MACD histogram rose 2 bars, weekly-or-oversold + RSI14<65. Identity receipts: Terminal `early_dots` = the same signature (charting-app `signal_layer/confluence_v2.py:578-610`, the 2.2px slate dot below the bar low). THIS is the operator's grey dot |
| **C2r** | grey dot, recomputed | the same leg recomputed from prices via `engine.signal_quality.signal_frame` (parity-checked against C2s on overlap; gives full metadata + coverage on names/dates the store trimmed) |
| **C3** | washout-deep grey dot | C2r, additionally requiring the 3D StochRSI cross itself to print under the 20 line (both %K and %D < 20 at the cross bar) — the operator's "crossover must be done under the 20 line" applied to the dot |
| **C4** | structure confirm | first confirmed radius-3 swing low (pivot at p, low[p] strict min of ±3 sessions, knowable at p+3) whose pivot printed while the last completed 3D StochRSI %D < 20; fire at p+3 |

Sequencing note: C1's two legs are ordered (3D washout cross first, 1D confirm second) per the
operator's description. C1 without the 1D leg and C2 without the C3 qualifier are implicitly
measured through the lane comparisons; no per-name best-of-grid selection is performed anywhere
(two-ruler kill row governs).

## §2 Ruler (per name first, pooled second — PSS §7 conventions)

Per fire (episode-deduplicated: fires of one construction within 10 sessions collapse to the
FIRST — earliest evidence is what a surface would show):

- **P_low** = min(low) over [T−45, T]: the decline low available to stop under at fire time.
- **entry-vs-low** = close(T)/P_low − 1. **Near-low rate** = share of episodes with
  entry-vs-low ≤ 5% (the U_W5 lens; ambient base ≈ 16% per the PSS charter).
- **td_to_trough** = T − argmin(low over [T−45, T+15]) in sessions; negative = fired before
  the eventual trough (knife still falling), positive = fired after it.
- **false bounce** = min(low over (T, T+15]) < P_low × 0.98 — the washout continued below the
  fire's own reference low.
- **MAE_21** = min(low over (T, T+21])/close(T) − 1.
- **Stop survival** — stop planted at P_low × 0.99: survived if no low ≤ stop through T+42.
  Tight variant: min(low(T), low(T−1)) − 0.25×ATR14.
- **MFE_42** = max(close over (T, T+42])/close(T) − 1; **R2 rate** = share reaching ≥ 2R
  (R = close(T) − stop) before the stop is hit, day-ordered on lows-then-close.
- Honest-N: episodes and names, per construction; per-name-first medians with pooled shown
  separately; half-split by time for sign stability; 2026 YTD printed as its own cell
  (current-regime answer, per the adjudication coverage gate).

## §3 Theme-breadth conditioning lane

For C1/C2/C3 episodes with basket membership: **washout breadth** = share of basket members
with 3D StochRSI %D < 20 at any point in [T−10, T]; **turn breadth** = share of members with a
C2 fire in [T−5, T]. Outcomes (false-bounce rate, stop survival, MFE_42) split by breadth
tercile computed within-construction. Read criterion (pre-stated): breadth is a useful
second-stage discriminator if the top-vs-bottom tercile false-bounce spread is ≥ 10pp with
consistent sign across the half-split — else printed as null.

## §4 Structure-stop context replay (§6.8(a)'s ordered measurement)

Structure-stop confirms recomputed through the Terminal's own machinery (charting-app
`signal_layer/confluence_v2.py` ARM→CONFIRM chain, imported and driven over the same adjusted
daily OHLC; charting-app HEAD SHA recorded in results). Metric (window pinned pre-results):
**P(confirm session lands within ±2 sessions of argmin(low) over [T−10, T+10])** — "the stop
printed at the local bottom" — plus forward +10/+21 close returns after confirm, split by
momentum context at confirm: (a) 1D MACD-RSI histogram rising over the last 2 steps vs not;
(b) 3D MACD-RSI at-or-above its signal line vs below. The macro store's own `sell` (3D CS)
markers get the same near-low audit as a secondary table. Read criterion (pre-stated, from
§6.8(a)): if the contradicted-confirm cohort (histogram already arching up) marks lows —
near-low share materially above the uncontradicted cohort with positive forward tape — the
§6.8(a) conditioning (disarm/demote to "flush watch" + re-entry watch) is supported for its
own engineering lane. STLD's 2026 stops and HL's 2026-07-31 stop (receipt: regime-block
forensic §3) must appear as named rows.

## §5 Exemplar coverage gate (leads the read-out)

Named traces printed in §R1 before any pooled number: STLD and NEM (in the 241-name store
universe: all lanes), HL and UEC (NOT in the store universe — no `site/signals` file exists
for them; traced through the recomputed lanes C1/C2r/C3/C4 and the Terminal-side stop lane
only, and excluded from pooled store-lane stats). A construction that cannot cover the
motivating exemplars does not get presented on pooled means (house law 2026-08-10).

## §6 Substrate + survivorship honesty

Prices: `data/baskets/ohlcv/<T>.parquet` (split+dividend adjusted; 2014+ for most names; read
from the current nightly-runner checkout, freshness recorded in results). Incumbent + dot
events: `site/signals/<T>.json` at origin/main (241 names, `signal_date`-stamped post-#4987).
Primary panel = the 241-name store universe ∩ priced. This is today's deep-history marker
universe — names that delisted before the store existed are absent, so outcome columns (MFE,
stop survival) carry survivorship tint; geometry columns (td_to_trough, entry-vs-low) are less
exposed but not immune. Printed, not hidden. Basket membership (`data/baskets/membership.json`,
34 curated baskets) is curated with hindsight per its own header — breadth-lane results carry
that flag. The 3D grid is the engine's absolute-session-anchor bucketing
(`ANCHOR_ERA=sq-abs-session-2026-08-06`); the three-grid discrepancy family
(`SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md`) is disclosed context — this study stamps
every synthetic fire at bucket-LAST knowability (G0.4), never the open label.

## §7 Prior-verdict engagement (the lens being reassessed)

`research/signal_engine/CONFLUENCE_TUNING.md` killed promoting any early variant (including
`m2d_s3d_early` and `m1d_s3d`) into the SCORED buy gate: on its ruler — unstopped forward
drawdown depth, location-within-the-forward-window, shakeout rate — `base3d` wins (§3b/§3c),
and §5b showed location guards "improve" only by trading less. Its own leak-free §3a
simultaneously proved the mechanism: early fires run **+4.9 days earlier and +2.6% cheaper**.
This bake-off does NOT contest that kill on its own ruler and proposes no scored-gate change.
It asks the different, §6.9-chartered question — the one
`research/signal_engine/BOTTOM_LEDGER_DESIGN.md` says the payoff-only grades cannot answer
(Proximity/Durability/Path/Payoff conflation; operator charter 2026-07-22 "pinpoint bottom
picks"): for a FILTERING machine whose operator executes with stops anchored under the decline
low, which construction SURFACES candidates closest to that low with survivable stop geometry?
A forward-window location ruler structurally favors late entries (enter after the bottom and
your entry IS the forward low); the backward, stop-anchored ruler here is the process-matched
lens. `washout_ladder_study.py`'s "63–68% stop-outs in deep washouts at every rung" (fixed
−5% close stop) is the adjacent prior on Durability — this study's stop is structural
(decline-low-anchored), so the two are comparable only directionally.

## §8 Durable-bottom vs false-start discriminator lane (operator 2026-08-11, second order — frozen before §R was viewed)

The operator's standing intent: the grey dot becomes the master signal creator; the work is
reducing false starts. On the C2r episode set, label each episode **FALSE START** if stop A
(P_low×0.99) is hit within +42 sessions OR the false-bounce condition fires; **DURABLE** if
stop A survives through +42 with no false bounce (mixed/truncated rows excluded, counted).
Feature battery (all PIT-computable at the fire session; no fitted models anywhere — this is
an ore-mapping pass, univariate splits only, per the ORE law):

1. **washout depth** — 3D %K at the cross bar (tercile), and the 0-bound flag (3D %K ≤ 2
   within the prior 10 buckets — the operator's original "harder washout" instinct).
2. **washout duration** — completed 3D buckets with %D < 20 in the current washout spell.
3. **decline depth** — close(T)/max(close over [T−126, T]) − 1 (tercile).
4. **1D confirm state** — 1D MACD-RSI: crossed at/before T (vs histogram-rising only), and
   the 1D MACD-RSI level's depth below zero at T (tercile) — "1D washout depth".
5. **structure** — higher-low flag: latest confirmed r3 swing low ≥ prior confirmed swing
   low; and distance close(T) vs latest confirmed swing low.
6. **volume signature** — max down-day volume z-score (vs 60d) within [T−15, T] (climax
   present/absent at median split), and fire-day volume vs 20d average.
7. **trend class** — above/below 200dma at T, and 63d RS vs SPY (tercile) — separates the
   leader-pullback class from deep washouts (§6.8(d) lanes).
8. **market context** — SPY's own 3D %D < 20 at T (systemic washout flag) — the PSS-F3
   lesson: systemic vs idiosyncratic lows behave differently.
9. **theme breadth** — the §3 washout/turn breadth measures (basket members only).
10. **repeat-fire** — a prior C2r fire within [T−20, T−1] whose episode false-started
    (knife-still-falling flag).

Read criteria (pre-stated): a discriminator is LIVE if the false-start-rate spread between
its extreme cells is ≥ 10pp with the same sign in both time-halves; SUGGESTIVE if ≥ 5pp
sign-stable; else null — all printed. Combinations are NOT searched (no best-of-grid); at
most the single strongest LIVE feature is cross-tabbed with theme breadth (the operator's
named candidate) as a 2×2. Output: an ore ledger ranking features with their spreads, CIs
(month-cluster bootstrap where cheap), and honest-N per cell. Promotion of any filter goes
through a fresh prereg on the program's sequencing — nothing here changes an engine.

## §R Results (run 2026-08-11; frozen numbers in `early_admission_bakeoff_results.json`, per-episode rows in `early_admission_bakeoff_episodes.parquet`)

**R0 — substrate + gates.** Panel 240 names (241 store files; SATS unpriced), prices through
2026-08-10, charter SHA `e602737841c`, charting-app SHA `687da219`. All acceptance gates PASS:
STLD C0 2026-08-07 ✓, store dot 2026-07-10 ✓, C2r reproduces it ✓. C2s↔C2r parity 96.0% on
3,760 store dots. **Measured store fact:** `early_markers` are stamped at the 3D bucket OPEN
label (3,756/3,760 moved under remapping) — every number here uses the bucket-LAST knowability
date (G0.4). Deviations (disclosed, never tuned): SPY benchmark read from `data/yahoo`;
HL's served 2026-07-31 stop reproduces only at some leading-history phases (see R4); the §8
2×2 uses the strongest NON-label-coupled feature. Substrate bounds (artifact notes N4–N6):
the panel window is the ohlcv store's ~2014+ (store events predating it dropped: 18,137 C0 /
7,202 C2s — never relocated), exposure 2,658.7 name-years; basket membership back-projects to
its 2023-05-09 seed, bounding every breadth measure to the post-2023 slice.

**R1 — exemplar coverage (leads the read-out).** STLD, the motivating chart: trough low
**216.36 on 2026-07-02**. C4 (structure confirm) fired **07-08 @ 228.80 (+5.7% off the low)**;
C1/C2/C3 all fired **07-14 @ 233.40 (+7.9%)** — the store dot's honest knowability date (its
07-10 label is the bucket OPEN); the incumbent BUY arrived **08-07 @ 262.45 (+21.3%)**, 17–20
sessions later, exactly the operator's chart narrative. The May-19 STOP confirmed at 222.90
with the local-low argmin ON the confirm session (gap 0) — and ran +23.2% in the 10 sessions
after; the Jan-07 stop was 1 session off its local low (+20.6% fwd21); the Jun-18 stop was the
one that "worked" (−8.9% fwd10). NEM: candidates surfaced it near the July lows (C1 07-09 @
94.81, +4.0% off the low) while the incumbent's own 07-27 fire was `quality=block` (vetoed) —
consistent with the regime-block forensic. HL/UEC (add-on names, store-less): the early lanes
fire INTO their deep miner washouts (HL C2r median td_to_trough −9.5 = nine sessions before
the eventual trough; false-bounce 37–60% on tiny N) — the hard-mode class where the stop
discipline, not the entry signal, carries the process.

**R2 — the bake-off (per-name-first medians; episodes/names in R2f; all signs stable across
both time-halves, R2g).**

| lane | eps | near-low% | entry vs low | td→trough | false-bounce% | stopA surv% | MFE_42 | ≥2R before stop% |
|---|---|---|---|---|---|---|---|---|
| C0 incumbent | 7,918 | **5.9** | **+10.1%** | **+14.5** | 9.1 | 73.3 | 7.5% | 9.7 |
| C1 3D<20→1D | 7,973 | 50.0 | +5.0% | +3 | 24.3 | 53.0 | 7.5% | 24.3 |
| C2s dot (store) | 3,474 | 45.0 | +5.5% | +6 | 21.4 | 54.6 | 7.1% | 22.2 |
| C2r dot (recomp) | 3,630 | 43.8 | +5.7% | +6 | 20.0 | 55.6 | 7.1% | 22.2 |
| C3 dot, cross<20 | 2,396 | 55.6 | +4.6% | +3 | 25.0 | 50.0 | 7.6% | 25.0 |
| C4 structure | 11,111 | 57.2 | +4.5% | +3 | 26.6 | 49.5 | 7.6% | 26.0 |

The incumbent is not a bottom-catcher: it fires a median **14.5 sessions after** the trough at
**+10.1%** above it, near-low only 5.9% of episodes. Every early lane halves the entry
distance (+4.5–5.7%) and multiplies the near-low rate ~7–10×, at the cost of ~2.2–2.9× the
false-bounce rate and ~20pp of structural-stop survival — and the ≥2R rate (stop under the
decline low) runs **2.3–2.7×** the incumbent's. That is the operator's thesis, quantified,
under the process-matched ruler. The ultra-tight stop B (fire-bar low − 0.25 ATR) survives
only ~23–28% everywhere — the decline-low anchor (stop A) is the viable stop, consistent with
`washout_ladder_study`'s fixed-stop finding. Median naked forward drift is small and similar
across lanes (MFE_42 ≈ 7–7.6%; excess vs SPY ≈ 0), re-confirming TIER_ENTRY_DEEPDIVE: the
edge the early lanes buy is **geometry** (where you enter and where the stop can live), not
raw pooled drift — the value case is precisely the operator's filtering-machine process.
Fire economics (R2f): C1 ≈ 3.0 episodes/name-year (same as C0), dot 1.3–1.4, C3 0.9, C4 4.2.
Confirm accounting (R2e): 672 deep 3D crosses never got a 1D confirm (filtered); median wait
when waiting = 2 sessions. C1 cohorts (R2d): zero-bound (operator's "harder washout") =
better proximity (54.6% near-low, +4.6%) but MORE false bounces (25.7% vs 22.1%) and lower
survival — deeper knives keep falling; the "more merit" reading holds for entry quality, not
for safety. 2026-YTD cell (R2h): the whole pattern holds in the current regime (C0 near-low
6.5% / +12.0% / +14td vs early lanes 40–46% / +5.2–5.9% / +2–4td); one honest wrinkle — 2026
early-lane naked excess vs SPY is negative (C1 −2.2pp @21d) while C0's is ~0: in this tape
the early fires' drift does NOT beat the index; the case rests on geometry + selection, and
§8 (below) is where false-start reduction must come from.

**R2i — coverage (why the dot alone cannot be the sole admission gate).** Share of incumbent
BUY episodes preceded (≤30 sessions) by: C1 **60.6%** (median lead 12 sessions), C4 68.7%,
dot C2r only **29.2%**, C3 20.4%. The dot is the highest-precision anticipation glyph, not a
full-recall spine: as sole gate it would front-run under a third of the moves the incumbent
eventually confirms. A recall spine needs C1 (the washout-cross + 1D confirm form) or a
C1∪C4 union — which is the TURN WATCH deck's architecture (§6.9 R8) with measured numbers
attached.

**R3 — theme breadth: NULL under the pre-stated criteria, and the sign runs AGAINST the
confirm hypothesis.** Top-vs-bottom tercile false-bounce spreads: washout-breadth C1 +2.3pp /
C2r +4.6pp / C3 −0.0pp; turn-breadth C1 +5.7pp (sign-stable) / C2r +4.2pp / C3 −1.7pp.
Nothing reaches the 10pp bar — and where breadth moves at all, HIGHER basket-wide
washout/turn breadth associates with MORE false bounces, not fewer (systemic-washout fires
are knives; the PSS-F3 lesson resurfacing). Substrate scope binds hard here: basket
membership back-projects to `seed_date=2023-05-09` (986/1,038 memberships carry exactly that
date), so the breadth lanes are measured ONLY on the post-2023 slice (~2.4k episodes) — a
substrate limit, printed, not a license to re-run elsewhere. On this evidence, pooled basket
breadth is not the refinement filter; its one conditional use appears in §R8's 2×2.

**R4 — structure stops (the §6.8(a) ordered replay; extraction parity-identical to the
Terminal machinery, 12,940 confirms).** Base rate: **34.9% of all stop confirms land within
±2 sessions of the local ±10-session low** — the "STOP at the exact low" phenomenon is real,
large, and structural (a confirm IS a close below a recent swing low; in a washout that print
clusters at capitulation). The specific §6.8(a) conditioning hypothesis as pinned — histogram
already rising at confirm — is NOT supported: that cohort is rare (110/12,786 = 0.9%) and
marks lows LESS (23.6% vs 35.0%), with weaker forward tape. Joint splits (R4d): the
near-low-marking stops are the ordinary hist-falling cohorts (34–38%). Lens limitation
disclosed rather than tuned: the strict 2-step rising definition does not even capture the
STLD May-19 receipt (hist_rising=False, 3D-bull=True at confirm) — the "arching up off the
histogram low" form the operator describes is a curvature/above-trailing-min construction and
gets its own fresh charter (no outcome-audition on this data). Forward tape after ALL stops:
median +0.7% @10 / +1.1% @21 — mildly positive; a third of stops are, in fact, local-bottom
prints. **Upstream defect found while proving parity (R4.hl_phase):** charting-app
`confluence_v2` still cuts its 2D/3D grids with first-timestamp-phased pandas `resample`, so
stop events are leading-history-dependent — HL's served 2026-07-31 stop reproduces only at
some history phases. Macro already ruled this defect class out engine-side
(`SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION`); the Terminal port has not. Handed to the
charting-app lanes (forensic §6 coordination note) — not changed here.

## §R8 Durable-vs-false-start ore ledger (frozen §8 features; C2r graded 3,596 episodes / false-start 44.8%, C1 7,881 / 47.4%; full tables `R8.*`)

**LIVE discriminators (≥10pp spread, sign-stable both halves; month-cluster CIs printed in
the tables; per-name-first spreads agree):**

| feature (direction that REDUCES false starts) | C2r spread | C1 spread |
|---|---|---|
| 3D %K higher at the cross bar (shallower oscillator washout) | −21.9pp [−26.8,−16.3] | −14.2pp |
| entry further above the latest confirmed swing low (label-coupled — partly mechanical) | −21.4pp | −16.9pp |
| 1D MACD-RSI level higher (less-washed daily momentum) | −15.0pp | −3.1 (null on C1) |
| 63d RS vs SPY stronger | −14.4pp | −15.4pp |
| decline shallower (close vs 126d high) | −13.1pp | −11.1pp |
| NO failed dot fire in the prior 20 sessions | −12.5pp | −17.2pp [11.7,22.6] |

SUGGESTIVE: higher-low r3 structure (−6.8pp C2r), above-200 (−5.4/−7.3pp), washout duration
(+6.9pp C1: LONGER washout spells false-start more), and the breadth features where they move
at all run POSITIVE — basket washout-breadth +6.0pp (C2r), turn-breadth +7.0pp (C1): MORE
basket-wide washout/turning = MORE false starts, the opposite of the confirm hypothesis
(post-2023 slice only, per §R3). NULL (printed, not hidden): BOTH volume signatures
(down-volume climax z and fire-day volume), SPY systemic-washout context, 1D-crossed-already.
The zero-bound flag runs POSITIVE (+4.3pp C2r / +5.1pp C1 SUGGESTIVE: zero-bound fires
false-start MORE, confirming R2d from the other side). One measured stamping fact worth its
own line (R0c): the chart PLOTS the dot at its bucket-open label, a median 2 sessions before
it is tradable — honoring knowability costs 8.6pp of near-low rate (53.4% plotted vs 44.8%
knowable), so the dot on the chart always looks slightly better than what any admission lane
can act on.

**The anatomy is coherent and it partially inverts the founding intuition: durable bottoms
are shallow, controlled resets in relatively strong names — the leader-pullback class
(§6.8(d) lane 2) — while the deepest-capitulation fires (K≈0, deep decline, weak RS,
repeat-failing dots) are the false-start factory.** Both halves of the operator's instinct
survive, but in different roles: deep washout maximizes entry PROXIMITY when it works (R2d:
zero-bound = +4.6% entries, near-low 54.6%), and shallow-reset context maximizes DURABILITY.
They are different axes, and the deck should carry both as context, not collapse them. The
2×2 (single pre-permitted cross-tab): the %K effect dominates theme breadth — breadth helps
only inside the deep-K cell (74.3% → 55.1% false-start), consistent with breadth-as-rescue
for knives, useless for leaders. The repeat-fire flag is the cleanest standalone filter: a
dot re-firing over the corpse of a failed dot within 20 sessions false-starts 56.7% (C2r) /
63.3% (C1) vs 44.2/46.1% ambient — CI clean of zero on both lanes.

Standing epistemic notes: ore-ledger tier — no combination search was run beyond the one 2×2;
label-coupling is flagged where mechanical; survivorship tint binds everything; any filter
built from these features promotes only through a fresh prereg (§6.0/§6.6 sequencing).

## §A Adjudication (measurement → recommendation; no engine change in this PR)

1. **The operator's direction survives its red-team on the process-matched ruler.** For a
   filtering machine whose operator stops under the decline low: the early constructions
   surface candidates at half the distance from the low, 7–10× the near-low rate, ~2.5× the
   ≥2R rate, with a false-start rate that doubles — the trade the operator explicitly
   accepted in advance. The washout-cross spine with 1D confirm (C1) is the best
   recall/geometry compromise (C0-coverage 60.6% at 12-session median lead, fire rate equal
   to the incumbent's); the grey dot (C2) is the precision/anticipation tier (fewer, slightly
   safer, earlier-per-move fires, but 29% coverage); C4 is the earliest and noisiest. The
   incumbent 3D confluence remains what it is — a trend-confirmation gate, measured here at
   +10.1%/+14.5td from the lows it follows.
2. **What this authorizes now (display-tier, already-chartered machinery):** wire the
   measured C1 construction (3D StochRSI cross <20 → 1D MACD-RSI confirm, zero-bound flag
   carried as context, not a gate) into the TURN WATCH deck / EARLY-TURN starter-class
   admission as the spine, with the dot retained as the anticipation chip — §6.9 R3/R8
   machinery, per-name "why not" receipts, starter size, window-not-certainty copy. No
   scored-authority change without the program's own prereg sequencing (§6.0/§6.6);
   CONFLUENCE_TUNING's scored-gate kill stands un-contested on its own ruler.
3. **Theme breadth is not the false-start filter** on this evidence (R3 null). The
   false-start reduction the operator wants must come from the §8 discriminator ledger
   (durable-vs-false anatomy on the dot/C1 fires) — measured next in this same file.
4. **Stops:** the fix direction is NOT the histogram-divergence disarm as originally pinned
   in §6.8(a) (R4b refutes it as constructed); the load-bearing fact is the 35% base rate of
   bottom-marking stops. The chartered follow-ups: (a) a curvature-form context study
   (hist-above-trailing-min at confirm), fresh charter, fresh data discipline; (b) the
   §6.8(a) "flush signature → re-entry watch armed" surface remains the right product shape —
   its trigger needs the §8-style feature anatomy, not the 2-step-rising split; (c) the
   charting-app grid-phasing defect (R4.hl_phase) goes to the Terminal lanes.
5. **Store hygiene follow-ups surfaced in passing:** `early_markers` are OPEN-label-stamped
   (the §6.7 signal-date defect family, now measured at 3,756/3,760) — the store should carry
   `signal_date` for dots as it now does for markers; EA/SATS carry stale store right-edges.
6. **§8 amendment to (2):** the admission spine should NOT hard-require the cross under 20 —
   that requirement selects the deep-knife class, which maximizes proximity but is the
   false-start factory (§R8). The measured shape of the operator's "master signal creator":
   surface EVERY washout-cross/dot fire at starter grade, carrying a durability-context tier
   from the LIVE discriminators — leader-reset class (shallow decline, stronger RS, higher
   cross-K, higher-low structure, no recent failed dot) vs deep-knife class (the inverse,
   where stop-outs and re-fires are the expected texture and theme-breadth rescue is worth
   showing) — plus the repeat-fire flag as the one clean standalone caution chip. This is
   exactly the shipped EARLY-TURN/TURN WATCH architecture (§6.9 R3/R8) with its conditioning
   now measured; the filter itself promotes only through a fresh prereg.
