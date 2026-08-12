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
| **C1** | operator proposal | 3D StochRSI bull cross (%K up through %D) with both lines < 20 at cross → CONFIRMED by the first 1D MACD-RSI bull cross (line up through signal) within the next 10 sessions; fire at the confirm session. **As-measured deviation (D2, §RT):** the commissioning spec ALSO admitted a 1D cross already in force ≤5 sessions before the 3D cross (fires at the 3D cross date; 74% of episodes) — that form is reported as C1-relaxed, the literal ordered form as C1L |
| **C1z** | C1 + zero-bound cohort | C1 fires where 3D %K printed ≤ 2 within the 10 3D-bars before the cross (reported as a split of C1, not a separate lane) |
| **C2s** | grey dot, as published | `early_markers` dates from `site/signals/<T>.json` — the engine's `m2d_s3d_early` leg (`engine/signal_quality.py:210`): 3D StochRSI %K×%D bull cross with %D-dipped-<20-within-8-bars context, while the prior CLOSED 2D RSI-MACD histogram rose 2 bars, weekly-or-oversold + RSI14<65. Identity receipts: Terminal `early_dots` = the same signature (charting-app `signal_layer/confluence_v2.py:578-610`, the 2.2px slate dot below the bar low). THIS is the operator's grey dot |
| **C2r** | grey dot, recomputed | the same leg recomputed from prices via `engine.signal_quality.signal_frame` (parity-checked against C2s on overlap; gives full metadata + coverage on names/dates the store trimmed) |
| **C3** | washout-deep grey dot | C2r, additionally requiring the 3D StochRSI cross itself to print under the 20 line (both %K and %D < 20 at the cross bar) — the operator's "crossover must be done under the 20 line" applied to the dot |
| **C4** | structure confirm | first confirmed radius-3 swing low (pivot at p, low[p] strict min of ±3 sessions, knowable at p+3) in 3D washout context — %D < 20 evaluated on the last completed bucket **as of p+3** (knowability-conservative pin; deviation noted) ; fire at p+3 |

Sequencing note: C1's two legs are ordered (3D washout cross first, 1D confirm second) per the
operator's description. C1 without the 1D leg and C2 without the C3 qualifier are implicitly
measured through the lane comparisons; no per-name best-of-grid selection is performed anywhere
(two-ruler kill row governs).

## §2 Ruler (per name first, pooled second — PSS §7 conventions)

Per fire (episode-deduplicated: fires of one construction within 10 sessions collapse to the
FIRST — earliest evidence is what a surface would show):

- **P_low** = min(low) over [T−45, T]: the decline low available to stop under at fire time.
- **entry-vs-low** = close(T)/P_low − 1. **Near-low rate** = share of episodes with
  entry-vs-low ≤ 5% (the U_W5 lens). *Ambient base measured on THIS panel (R9g): 24.7%
  backward-anchored, 16.4% trough-referenced — the PSS charter's ~16% matches the
  trough-referenced form, so lane near-low rates are compared to 24.7% on the backward
  columns and 16.4% on the R9h trough columns.*
- **td_to_trough** = T − argmin(low over [T−45, T+15]) in sessions; negative = fired before
  the eventual trough (knife still falling), positive = fired after it.
- **false bounce** = min(low over (T, T+15]) < P_low × 0.98 — the washout continued below the
  fire's own reference low.
- **MAE_21** = min(low over (T, T+21])/close(T) − 1.
- **Stop survival** — stop planted at P_low × 0.99: survived if no low ≤ stop through T+42
  (or the data edge; rows with < 30 forward sessions are excluded and counted).
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

**R1 — exemplar coverage (leads the read-out; exact receipts R9k).** STLD, the motivating
chart: trough low **216.36 on 2026-07-02**. C4 (structure confirm) fired **07-08 @ 228.76
(+5.7% off the low)**; C1/C2/C3 all fired **07-14 @ 233.35 (+7.9%)** — the store dot's honest
knowability date (its 07-10 label is the bucket OPEN); the incumbent BUY arrived **08-07 @
262.45 (+21.3%)**, 18 sessions after the dot and 22 after the structure confirm — exactly the
operator's chart narrative. The May-19 STOP confirmed at 222.86 with the local-low argmin ON
the confirm session (gap 0) — and ran +23.2% in the 10 sessions after; the Jan-07 stop was 1
session off its local low (+20.6% fwd21); the Jun-18 stop was the one that "worked" (−8.9%
fwd10). NEM cuts the other way and is printed so (red-team item 6): the July trough was
**88.75 on 07-17**; the C1 07-09 fire @ 94.81 was a **false start** (td −6; its reference low
was breached) sitting **+6.8%** above the eventual trough, while the incumbent's 07-27 fire @
93.47 — `quality=block`, reason "counter-trend, held but no 200-reclaim" (so the product
VETOED it; consistent with the regime-block forensic) — sat **+5.3%** above that trough
(truncation-provisional: its two-sided window is still open at the data edge), closer than
the early fire. On this exemplar the early lane was earlier but wronger; pooled, the
trough-referenced comparison still favors the early lanes (R9h). HL/UEC (add-on names,
store-less): the early lanes fire INTO their deep miner washouts (HL C2r median td_to_trough
−9.5; false-bounce 37–60% on tiny N) — the hard-mode class where the stop discipline, not
the entry signal, carries the process.

**R2 — the bake-off (per-name-first medians; episodes/names in R2f; all signs stable across
both time-halves, R2g).**

| lane | eps | near-low% | entry vs low | td→trough | false-bounce% | stopA surv% | MFE_42 | ≥2R before stop% |
|---|---|---|---|---|---|---|---|---|
| C0 all published markers | 7,918 | 5.9 | +10.1% | +14.5 | 9.1 | 73.3 | 7.5% | 9.7 |
| **C0 quality=take (what the product ACTIONS; 36% of markers)** | 2,828 | 7.4 | **+10.3%** | **+18** | **3.1** | **84.3** | 8.6% | 11.4 |
| C1-relaxed (as measured; see deviation) | 7,973 | 50.0 | +5.0% | +3 | 24.3 | 53.0 | 7.5% | 24.3 |
| C1L charter-literal (fresh 1D cross only) | 3,165 | 56.0 | +4.6% | +2 | 24.5 | 50.3 | 7.5% | 27.7 |
| C2s dot (store) | 3,474 | 45.0 | +5.5% | +6 | 21.4 | 54.6 | 7.1% | 22.2 |
| C2r dot (recomp) | 3,630 | 43.8 | +5.7% | +6 | 20.0 | 55.6 | 7.1% | 22.2 |
| C3 dot, cross<20 | 2,396 | 55.6 | +4.6% | +3 | 25.0 | 50.0 | 7.6% | 25.0 |
| C4 structure | 11,111 | 57.2 | +4.5% | +3 | 26.6 | 49.5 | 7.6% | 26.0 |

Two comparator corrections from the red-team (§RT) are baked into this table. First, the
pooled C0 row mixes **64.2% `quality=block` markers the incumbent's own buy filter refuses**
— the actioned incumbent (take-only, R9a) is the honest baseline, and it is both safer and
later than the pooled row: false-bounce **3.1%**, stop-A survival **84.3%**, `+18` sessions
past the trough, with **positive** benchmark excess (+1.6pp @21d). Second, C1 as measured
contains a spec-added branch (a 1D cross already in force ≤5 sessions before the 3D cross
admits immediately — 74% of its episodes); the charter-literal ordered form (C1L) is
printed beside it and is MORE proximate (56.0% near-low, +4.6%) but much lower-recall
(1.19 fires/name-year, 6,207 unconfirmed 3D crosses).

Priced against the actioned incumbent, the honest trade is: early lanes enter **~35–45%
closer to the eventual trough** (trough-referenced medians, R9h: C1 +6.5% / C1L +5.9% / dot
+6.9% / C4 +6.2% vs C0-take ≈ +10.6%) and 15+ sessions earlier — at **6.5–8.7× the
false-bounce rate** (20–27% vs 3.1%), **~30pp less stop-A survival**, and (R9e) a mechanical
hold-42 R-multiple whose MEAN favors the early lanes over C0-all (+0.29..+0.40 vs +0.23) but
whose MEDIAN is negative for every early lane (−0.27..−1.00; stop-out share 44.7–50.8%)
while **C0-take leads on both** (mean +0.447, median +0.373, stop-out 15.7%). The naked ≥2R multiple in the table is
partly arithmetic — early-lane R targets are about half C0's (median 2R distance 10.6–12.3%
vs 20.1%) — so it describes geometry, not expectancy. The distribution shape is the point:
the early book is many small stop-outs + a fatter right tail, which monetizes ONLY under the
operator's cut-fast/let-run execution and some second-stage selection; under a
no-discretion mechanical rule, the actioned incumbent's late-and-safe book wins outright.
The ultra-tight stop B (fire-bar low − 0.25 ATR) survives only ~23–28% everywhere — the
decline-low anchor (stop A) is the viable stop, consistent with `washout_ladder_study`.
Fire economics (R2f/R9b): C1-relaxed ≈ 3.0 episodes/name-year, C1L 1.19, dot 1.3–1.4, C3
0.9, C4 4.2 — and C4 alone is dedup-rule-sensitive (keep-last near-low 50.3% vs shipped
55.5%, R9j; the other five lanes move <1.1pp). Zero-bound (R2d): better proximity (54.6% near-low), MORE false bounces
(25.7% vs 22.1%) — proximity, not durability. 2026-YTD cell (R2h): the geometry pattern
holds in the current regime (C0 near-low 6.5%/+12.0%/+14td vs early lanes
40–46%/+5.2–5.9%/+2–4td); honest wrinkle — 2026 early-lane naked excess vs SPY is negative
at BOTH horizons (C1 −2.2pp @21d, **−4.4pp @42d**) while C0's is ~0/+0.4: in this tape the
early fires' drift does not beat the index; the case rests entirely on geometry + selection.

**R2i — coverage, restated after the C1 deviation (R9b).** Share of incumbent BUY episodes
preceded (≤30 sessions): C1-relaxed **60.6%** (median lead 12), C4 68.7%, dot C2r 29.2%, C3
20.4%, **C1L only 25.0%** — under the charter's own ordered definition, C1 is NOT a recall
spine (it covers less than the dot). What carries recall is the RELAXED qualifier — "3D
washout cross with 1D MACD-RSI momentum in force or confirming within 10 sessions" — and
that form must be named for what it is wherever it is wired. The dot remains the
highest-precision anticipation glyph; a recall surface needs the relaxed form or a union
with C4 — the TURN WATCH deck's architecture (§6.9 R8), now with measured numbers.

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
±2 sessions of the local ±10-session low, versus a 15.7% random-session null on the same
frame — a 2.2× chance lift** (R9f; the lift holds 1.7–2.7× across the ±5/±10/±15 window
grid, so the phenomenon is real but the naked 35% overstates it by the null). "STOP at the
exact low" is structural (a confirm IS a close below a recent swing low; in a washout that
print clusters at capitulation). The specific §6.8(a) conditioning hypothesis as pinned — histogram
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

**Raw ledger reads (≥10pp spread, sign-stable both halves; month-cluster CIs in the tables)
— each row then re-tested under risk-equalized labels in R9d, WHICH IS WHERE THE VERDICT
LIVES:**

| feature (direction that REDUCES false starts, shipped label) | C2r spread | C1 spread | survives risk-equalization (R9d)? |
|---|---|---|---|
| 3D %K higher at the cross bar | −21.9pp [−26.8,−16.3] | −14.2pp | **NO** (−5.3 @fixed−8%, +2.4 @2ATR; −9.2 within entry-distance quintiles) |
| entry further above the latest confirmed swing low | −21.4pp | −16.9pp | **NO** (label-coupled by construction; +6.8 @fixed−8%) |
| 1D MACD-RSI level higher | −15.0pp | −3.1 (null on C1) | **NO** (−5.4 / +0.2 / −0.5) |
| 63d RS vs SPY stronger | −14.4pp | −15.4pp | **NO** (−4.3 / +1.3 / −1.2) |
| decline shallower (close vs 126d high) | −13.1pp | −11.1pp | **MAYBE** — the one feature that STRENGTHENS under fixed-% stops (−16.3/−16.5) and holds within entry-distance quintiles (−11.2/−12.8), but flips under ATR stops (+8.5/+7.1): volatility-confounded; carried to the v2 prereg, not promoted |
| NO failed dot fire in the prior 20 sessions | −12.5pp | −17.2pp | **RETRACTED — look-ahead artifact (R9c, §RT)** |

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

**Corrected verdict (post-red-team, receipts R9c/R9d/R9i): the shipped-label ledger was
mostly measuring the ruler, and one feature was leaking the future.**

- **Repeat-fire is RETRACTED.** The shipped flag conditioned on the prior fire's LABEL,
  which resolves up to 41 sessions after T. The leaked subset (25–30% of flags) is 100%
  false-start **by construction** (an unresolved prior false-start within 20 sessions means
  the shared reference low breaks after T, stopping the current episode too). PIT-only
  spread: **−2.2pp (C2r) / +0.3pp (C1)** — null; under risk-equalized labels it runs
  negative. There is no repeat-fire caution signal in this data.
- **The remaining LIVE features were largely stop-width arithmetic.** The label's stop sits
  at P_low×0.99, so stop width IS entry_vs_low (median stop distance by %K tercile: 1.92 →
  3.59 ATR). entry_vs_low itself "discriminates" −29.6pp — more than any feature. Under a
  fixed −8% or ATR-anchored stop, %K/1D-level/RS collapse to noise or flip sign (table
  above); within entry-distance quintiles they shrink 2–3×. What looked like "shallow
  resets in strong names are durable" was mostly "entries further above the reference low
  have wider stops."
- **What actually stands (R9i): the pre-vs-post-trough mix carries most of it, with a ~10pp
  per-fire residual.** Stop-A survival is **~7–11% for fires before the eventual trough**
  in every lane, and post-trough it is **88.5% for the actioned incumbent (C0-take)** vs
  **77–79% for the early lanes** (C0-all 83.9%) — so the honest decomposition is: the early
  lanes fire pre-trough **35–42%** of the time versus C0-take's **5.2%** (C0-all 14.5%),
  and even their post-trough fires give up ~10pp of survival to the actioned incumbent.
  Most of the durability cost is the mix; a real per-fire gap remains. (At episode level
  the false-bounce leg of the label is near-tautological with pre-trough firing —
  post-trough false-bounce is ~0 by construction — which is why the durable/false anatomy
  reduces to this decomposition.)
- The 2×2 was built on the %K feature and is demoted with it (kept in the artifact for the
  record). Breadth direction notes from the raw ledger (more basket-wide washout/turn =
  more false starts, post-2023 slice) survive as SUGGESTIVE texture consistent with R3.
- R0c stands: the chart PLOTS the dot at its bucket-open label, a median 2 sessions before
  it is tradable — honoring knowability costs 8.6pp of near-low rate (53.4% plotted vs
  44.8% knowable). The dot on the chart always looks slightly better than anything an
  admission lane can act on.

**So the reverse-engineerable "filter" the operator asked for is not a static feature gate
on this evidence — it is post-trough EVIDENCE.** The tradable question at T is "has the low
already printed?", and the v2 prereg should test the PIT proxies of exactly that: confirmed
r3 pivot AFTER the fire's reference low (C4's own logic, as a confirm-tier on dot/C1 fires
rather than a standalone lane), sessions-since-last-new-low ≥ k, higher-low sequence — under
risk-equalized labels (fixed-% AND ATR-anchored stops), with the §RT leak discipline. That
charter is minted as the §A6 follow-up; nothing promotes from this file.

Standing epistemic notes: ore-ledger tier — no combination search beyond the one 2×2;
label-coupling flagged; survivorship tint binds everything; any filter built from these
features promotes only through a fresh prereg (§6.0/§6.6 sequencing).

## §A Adjudication (measurement → recommendation; no engine change in this PR)

1. **The operator's direction survives — priced honestly, against the actioned incumbent.**
   For a filtering machine whose operator stops under the decline low: the early
   constructions surface candidates ~35–45% closer to the eventual trough and 15+ sessions
   earlier than the actioned incumbent (C0-take: ≈+10.6% trough-referenced, +18td), at
   6.5–8.7× its false-bounce rate and ~30pp less stop-A survival — with a mechanical-rule R
   distribution that is mean-positive/median-negative (many small stop-outs, fat right
   tail) where C0-take is positive on both. The early book therefore monetizes ONLY through
   the operator's asymmetric execution plus second-stage selection — which is the operator's
   stated process, and why this ships as a RECALL surface, not a scored gate. The incumbent
   remains what it is: a late, safe trend-confirmation gate (and its take-only cohort even
   carries positive index excess).
2. **What this authorizes now (display-tier, already-chartered machinery):** wire the
   RELAXED washout-cross form — 3D StochRSI cross <20 with 1D MACD-RSI in force or
   confirming within 10 sessions, NAMED as relaxed (the charter-literal ordered form covers
   only 25% and is not a recall spine) — into the TURN WATCH deck / EARLY-TURN starter-class
   admission as the recall spine, with the dot retained as the anticipation chip and the
   zero-bound flag as context (proximity, not durability). §6.9 R3/R8 machinery, per-name
   "why not" receipts, starter size, window-not-certainty copy. No scored-authority change
   without the program's own prereg sequencing (§6.0/§6.6); CONFLUENCE_TUNING's scored-gate
   kill stands un-contested on its own ruler.
3. **Theme breadth is not the false-start filter** on this evidence (R3 null, post-2023
   slice, direction against the confirm hypothesis where it moves). The §8 static-feature
   ledger did not deliver one either after risk-equalization (§R8) — the chartered path to
   false-start reduction is §A6's post-trough-evidence prereg.
4. **Stops:** the fix direction is NOT the histogram-divergence disarm as originally pinned
   in §6.8(a) (R4b: not supported as constructed, month-cluster CI clean); the load-bearing
   fact is the 34.9%-vs-15.7%-null rate of bottom-marking stops (2.2× chance, R9f). The chartered follow-ups: (a) a curvature-form context study
   (hist-above-trailing-min at confirm), fresh charter, fresh data discipline; (b) the
   §6.8(a) "flush signature → re-entry watch armed" surface remains the right product shape —
   its trigger needs the §8-style feature anatomy, not the 2-step-rising split; (c) the
   charting-app grid-phasing defect (R4.hl_phase) goes to the Terminal lanes.
5. **Store hygiene follow-ups surfaced in passing:** `early_markers` are OPEN-label-stamped
   (the §6.7 signal-date defect family, now measured at 3,756/3,760) — the store should carry
   `signal_date` for dots as it now does for markers; EA/SATS carry stale store right-edges.
6. **§8 outcome, as corrected (§R8/§RT):** no static feature filter survives
   risk-equalization on this evidence — the repeat-fire chip is retracted (look-ahead), and
   the %K/RS "durability tier" was mostly stop-width arithmetic (decline-depth survives as
   a volatility-confounded MAYBE). What stands is the pre/post-trough decomposition:
   survival is ~7–11% before the trough is in, versus 88.5% post-trough for the actioned
   incumbent and 77–79% for the early lanes — the mix (5.2% vs 35–42% pre-trough) carries
   most of the cost, a ~10pp per-fire gap remains. The chartered v2 prereg for false-start
   reduction therefore tests **post-trough-evidence confirm tiers on the dot/relaxed-C1
   fires** — confirmed r3 pivot above the fire's reference low, sessions-since-last-new-low
   ≥ k, higher-low sequence — under FULLY risk-equalized labels (fixed-% AND ATR stops on
   BOTH label legs; note the R9d relabels kept the false-bounce leg P_low-anchored, so they
   are partial by construction — a stop-only relabel flips %K positive) with explicit
   PIT-leak discipline. Until that runs, the deck carries the early fires with honest
   texture copy ("pre-trough fires stop out ~9 in 10; windows, not certainties"), and the
   operator remains the second-stage filter by design.

## §RT Red-team record (2026-08-11, adversarial pass per the adjudication coverage gate)

An independent Opus review lane attacked the first-draft conclusions with computational
receipts; every finding was reproduced into frozen `R9.*` tables by the study script and
the doc was rewritten from them. Material outcomes: (1) BLOCKING — the §8 repeat-fire
"cleanest filter" was a look-ahead artifact (label resolved past T; leaked subset 100%
false-start by construction; PIT-only null) → retracted everywhere. (2) BLOCKING — the
measured C1 contained a spec-added immediate-confirm branch inverting the charter's leg
order and carrying the 60.6% recall headline (charter-literal C1L covers 25.0%, below the
dot) → both forms now printed and named; §R2i/§A restated. (3) The §R8 LIVE features were
largely stop-width arithmetic (R9d risk-equalization; entry_vs_low itself out-discriminates
every feature) → §R8 verdict rewritten around the R9i pre/post-trough mix. (4) The pooled
C0 comparator mixed 64.2% `quality=block` markers the product refuses → C0-take is the
priced baseline. (5) R-normalized expectancy added (R9e). (6) NEM exemplar corrected (the
early fire was a false start; the vetoed incumbent fire was closer to the low). (7) R4's
34.9% now carries its 15.7% random null. (8) Ambient near-low re-measured on-panel
(24.7%/16.4%); prose/table reconciliations and precision fixes applied. Attacks that came
back clean: backward-P_low ruler asymmetry (the trough-referenced multiple is LARGER),
truncation symmetry, R4b thinness (month-cluster CI −11.4pp [−19.2,−2.8] strengthens the
non-support), stop-A gap-through slippage (median −0.04%), and the charter-vs-code spot
checks outside the two disclosed deviations (C1 branch, C4 %D at p+3).
