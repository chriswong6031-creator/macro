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

## §R Results

*(appended by `early_admission_bakeoff.py` run; frozen numbers in
`early_admission_bakeoff_results.json`)*
