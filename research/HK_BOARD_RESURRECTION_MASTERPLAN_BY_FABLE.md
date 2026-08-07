# HK Board Resurrection — port the priority engine, free the leaders, recalibrate the veto (masterplan by Fable)

Date: 2026-08-02 · Status: CHARTERED — operator-directed (2026-08-02: "HK board only has 3 picks…
failed to signal buys on mega caps like Alibaba, Tencent, JD, Xiaomi, Meituan, KC, PDD… complete
failure… surgical precision assessment and figure out what to do"). Program id:
`hk_board_resurrection`. Build opens AFTER the Prophet Board Priority Engine PR (#4331) merges —
the port depends on `engine/us_board_rank.py`. Siblings: `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`
(the machinery being ported), autopsy evidence below (diagnostic lane, 2026-08-02, reproduced
`eligible: 5/156` independently).

---

## §1 The autopsy (all numbers independently recomputed 2026-08-02)

- Board state: universe 156 → eligible 5 → buy 3 (ZTE, Galaxy Ent, Zhejiang Shibao — zero
  mega-caps). `board_track: null`; the board's OWN health leg reports the ledger write failed.
- The seven witnesses (0700/9988/9618/1810/3690/1024 + 9961.HK — Trip.com Group, TCOM's HK
  twin; identity corrected 2026-08-03: this doc originally called 9961.HK "PDD's HK twin", but
  PDD Holdings has no HK listing — the measured numbers below are for the tickers as listed,
  so they stand; the seventh witness was Trip.com, not PDD) all bottomed
  2026-06-26 (HSI YTD low, index-wide washout) and ran +8.7%…+44.0% by 07-31; six of seven beat
  HSI (+14.2%). Across the 25-session leg each was buy-eligible for a 2–6 session cameo
  (Kuaishou 2/25 … Meituan 6/25); on most days ZERO of the seven were eligible simultaneously.
  Tencent/Alibaba/Xiaomi were absent from every lane for the final ~3 weeks; Meituan sat in
  LAGGARDS for 2.5 weeks of a +44% rally, composite-ranked 4th-worst of 156 (below distressed
  developers) because the entry-axis extension penalty contaminates the selection composite.
- Funnel: 68% of rejections = the 200-dma reclaim-and-hold veto (calibrated on 110 US names,
  one-shot 2-bar reclaim test, NO periodic re-test — Kuaishou has been blocked on a single
  2026-05-06 marker for ~3 months); 22% = FRESH_TICKS=2 staleness (JD validated 07-15, stale by
  07-18); universe itself was stuck at 73/160 names until 07-16 (126-session beta-alignment
  gate).
- The sharpest fact: `engine/hk_leadership.py`'s cohort read (DEFAULT_COHORT = exactly the
  witness list) flagged `leaders_participating` from 07-11 with broad breadth climbing
  21.6%→71.2% — while board eligibility fell 47→5 (−90%) over the same tape. The system had
  the right answer in a display-fenced organ (HKRV-R5) the board cannot hear.
- Track ledger: n_matured 0 (first read ~2026-08-24) — no empirical defense of the current
  design exists; 29.6% of logged calls suspended (HK microstructure, no delisting archive).

## §0 ACCEPTANCE GATES (binding on the build)

- **G1 — The witnesses are visible.** On a 2026-07-31 fixture: all seven witnesses appear on
  the rebuilt board — in leaders (momentum-selected, hk_leadership-boosted), ran (recently
  fired, sessions-since + % since), or a live/setting-up stage — each with an honest stance
  chip. A fixture test pins ≥5 of 7.
- **G2 — Leaders lane exists for HK** (us_board_rank leaders v2 parameterized for HK: 3-month
  total-return z, intact-trend gates, `hk_leadership` cohort membership as the theme-boost
  analog + chip). Display-tier, stance "watch — don't chase", forward-graded from ship date.
- **G3 — Ran lane exists for HK** (marker/fresh_bars anchored, fail-closed on unknown age —
  the B3 discipline from the US review applies from day one).
- **G4 — Stage buckets + filters + featured + priority score** ported (hk_prophet_v1, same
  frozen constants; entry map shared; edge leg = alpha percentile; disclosure block; featured
  requirements incl. sector cap; NEW badges). Rendering = the unified-grid idiom (US/CN
  parity); the old flat 3-row board dies.
- **G5 — Laggards stop using the entry-contaminated composite.** Laggards key = selection-axis
  (residual alpha) only. A Meituan-class row (selection z > 0, entry z ≪ 0) must be
  structurally unable to enter laggards. Fixture-pinned.
- **G6 — ~~The 200-dma veto gets a measurement, not a hot-patch.~~ SUPERSEDED FOR HK BY
  OPERATOR RULING 2026-08-03.** Original text: ship display-tier relief first (G1-G4 make
  blocked names VISIBLE with the blocking reason named); the veto itself changes only via
  prereg — offline scan machinery over the HK panel measuring (a) re-test cadence variants,
  (b) HK-depth reclaim windows, with forward comparison before any admission change.

  **What happened:** G6's own display-tier relief worked. The `vetoed` lane printed 12
  refused names — 0700/9988/1810/1211/2318/0268/3888/1093/0867 among them — and the operator
  ordered the gate removed ("remove HK gate. It is a complete failure to have blocked the
  buys to incredible wins"). Shipped as `hk_prophet_v2`.

  **The mechanism finding, which outlives the directive:** the reclaim leg is
  *unsatisfiable by construction* for a deep drawdown. A name 17% below its 200-day average
  cannot close above it within 2 bars, so every buy signal it fires is auto-blocked until it
  has already recovered — i.e. until the move is over. For the deep-washout bounce setups
  that dominate this tape it was never a risk judgement; it was arithmetic. Verified on the
  committed panel: 6 of 9 witness July markers flip `block`→`take` at their original signal
  dates (Xiaomi 07-06, Alibaba 07-10, Meituan 07-03, Ping An 07-10, CSPC 06-26, China
  Medical 06-25); BYD and Kingdee stay blocked on the next-bar hold, which is an honest
  reason rather than an impossible one.

  **Scope:** HK only, via `signal_gate.gate(..., reclaim_veto=False)`. KEPT on both policies:
  the bearish-divergence veto and the next-bar hold. US/CN keep the original policy AND this
  prereg discipline — nothing here licenses touching them.

  **The cost, measured and disclosed on the board:** ~⅓ more names; over 26 years the
  unblocked cohort earns ≈0 excess vs HSI (mean +0.55%/20d, CI crossing zero) and carries
  deeper drawdown (median 60d MAE −9.0% vs −7.4%; P(excess<−20%) 5.8%→7.9%). Absolute
  peak-after-entry across the live blocked population was positive for 54/54 names (median
  +5.2%, five ≥+15%), which is the product case for admitting them. **The washout regime
  that motivated the ruling is NOT gradeable** — zero readable post-2026-06-26 cells at any
  horizon. This is a bet on that regime, not a finding about it; re-run the harness after
  2026-10-20 (`scratchpad/veto_measure/`) and let `hk_prophet_v2`'s forward ledger settle it.

  **Still open under the original G6 spirit:** the *bearish-divergence* veto measured a null
  in HK (blocks 1,148 signals for no measurable return cost and no drawdown benefit) — the
  cheaper leg to relax if more breadth is wanted, and it deserves the prereg G6 describes.
- **G7 — Plumbing heals.** The board_track ledger write failure diagnosed and fixed (health
  leg green); the 126-session beta-gate universe gap gets a fallback (name admitted with
  beta=null context rather than silently dropped) or a disclosed exclusion count.
- **G8 — PDD question answered.** Determine why PDD (NASDAQ, NDX constituent) is absent from
  all US lanes and either admit it to the US universe properly or document the exclusion.
  (Premise corrected 2026-08-03: PDD Holdings has NO HK listing — 9961.HK is Trip.com Group,
  TCOM's twin, not PDD's — so there is no HK-side PDD exposure to fall back on; the US lane
  is the ONLY channel, which raises this gate's weight. HK-side PDD exposure exists only
  diffusely via KWEB's holdings.)
- **G9 — Ship discipline.** Same PR chain; screenshots light/dark/EN/ZH; fail-soft on pre-v1
  artifacts; forward cohorts wired into the HK grader; no "validated" language.

## §1b BUILD FINDINGS (engine lane, 2026-08-02 — all recomputed on the committed
## `data/hk_search/closes_deep.parquet` panel, 157 names through 2026-07-31)

**§1 reproduces exactly.** The 06-26 → 07-31 leg: 1024 +8.7%, 0700 +15.4%, 9961
+20.1%, 9988 +30.7%, 9618 +32.4%, 1810 +34.4%, 3690 +44.0%; HSI +14.2%; six of
seven beat the index. Cascade-eligible on 07-31: 5 of 157.

**But the witnesses are not "leaders" on any frame wider than that 25-session leg**,
and this is the fact the build had to design around:

| name | vs 200-dma | off 52w high | 63d total return | cascade |
|---|---|---|---|---|
| 0700.HK | −11.2% | −29.0% | +0.3% | ineligible |
| 9988.HK | −15.6% | −36.7% | −10.3% | ineligible |
| 9618.HK | **+10.5%** | −10.6% | +8.2% | ineligible |
| 1810.HK | −17.3% | −51.6% | −4.5% | ineligible |
| 3690.HK | **+3.7%** | −31.2% | +11.2% | ineligible |
| 1024.HK | −26.1% | −52.4% | +0.4% | ineligible |
| 9961.HK | −18.8% | −39.8% | −12.2% | ineligible |

Panel context: 58/157 names hold their 200-dma, median off-high −21.3%, and 71/157
clear the US leaders lane's −20% near-high floor — so the US gates are **not**
structurally unreachable in HK. HSI itself is above its 200-dma and 7.5% off its
high. The witnesses are the damaged tail of a healthy tape, bouncing.

**Consequence for G1: a faithful port surfaces 2 of 7** (9618 in leaders, 3690 in
ran). The other five fail `above200`, correctly. Meeting G1 by relaxing that gate
would have been the hot-patch G6 forbids — and would have measured nothing.

**Resolution — the `vetoed` lane** (G6's "display-tier relief… blocked names VISIBLE
with the blocking reason named", built as a lane rather than left as a copy note).
Admission: cascade-ineligible ∧ last marker is a `buy`/`rebuy` ∧ that marker's
quality is `block` ∧ weekly still bull ∧ not marked down. It prints the marker date,
sessions since, **the move since the marker**, and the block reason in plain words.
48 names qualify on 07-31; 39 of them on the same `counter-trend, no
200-reclaim/hold` string. Cohort members are emitted unconditionally, the rest fill
to a cap of 12 by move desc, capped at a 63-session staleness window.

**Measured witness visibility: 5 of 7 through the display lanes, 6 of 7 on the
page** (corrected 2026-08-03 — the first measurement replayed the lanes with an
EMPTY exclusion set, which is not how the builder calls them). Under production
arguments — `exclude = buy ∪ watch`, `dedup_name=norm_company`, momentum over the
enriched panel — the lanes place 9618 (leaders), 3690 (ran), 0700 / 9988 / 1810
(vetoed). **1024.HK is on the WATCH STRIP**, which claims its ticker before the
vetoed lane runs; it is visible there, under a strip header that reads "strong edge,
blocked entry (wait for a base)" — so the *fact* of a blocked entry is carried, but
the marker date and the specific block reason are NOT (those print only in the
vetoed lane). No new surface was built for it; the gap is recorded here.
9961.HK stays dark and honestly so: outside the mega-cap cohort, −12% on the
quarter, and its post-marker move does not beat the non-cohort field. G1's ≥5 pin is
met against the PRODUCTION measurement with no gate loosened. The lane is
deliberately self-critical — it exists to print what the board missed, so it is
working when it reads badly. It is also the G6 study's product-side receipt: 1024.HK
has been blocked on a single 2026-05-06 marker for 59 sessions.

## §1c G7 / G8 — answered

**G7 (ledger).** NOT a write failure. `data/board_ledger/hk_board.parquet` is
healthy — 347 rows through 2026-07-31, including that session's 13.
`board_ledger.append_board` returns 0 **by design** when `CN_LANE != "asia"` (the
PR-R10 lane gate; the nightly asia-close lane is the sole advancer, house law).
`CN_LANE` is set only in `asia-close.yml`, so every `render.yml` /
`engine-render.yml` re-render — i.e. most merges to main — raised a false alarm on a
healthy store. Git archaeology is unambiguous: `asia dashboards` commits ship
`health: []` and a real `board_track`; the same-day `engine-render` re-renders ship
the alarm. **Fixed on the caller, never the gate** (the gate is correct and pinned by
`tests/test_board_ledger_lane_gates.py`): off-lane logs and moves on; an on-lane zero
still raises the health row.

**G7 (universe gap).** Already healed before this build —
`build_hk_library.hk_beta_close_panel`'s deep-panel overlay fixed the 126-session
causal-beta `min_periods` drop that stuck the universe at 73/160 (its docstring
carries the diagnosis). Universe now reads 156. What remains is ordinary coverage
loss, and it is now **printed** rather than inferred: `universe_excluded` +
`universe_source_rows` on the artifact.

**G8 (PDD).** Not a universe bug — no fix warranted, and none made. PDD is already
in the roster (`config.yml` `stock_search.extra_tickers` + `extra_names`) with fresh
data (`data/yahoo/PDD.parquet`, 2,014 rows through 2026-07-31). It reaches `cand`
and is scored. It is absent from the lanes because it fails each on its merits: no
live confluence cross (`eligible: False`, `tier_cascade: None`), 17th-percentile
3-month momentum (too weak for the 15-slot leaders lane), and a composite damped
toward zero by `stock_score._axis_selection`'s confidence floor, because PDD carries
none of the three event legs (no SUE, no insider, no revision coverage). That last
part is **categorical, not PDD-specific**: 0 of the 14 China/HK ADRs in
`extra_tickers` have SUE or revision coverage. BIDU proves there is no ADR exclusion
— it is on tonight's buy lane, on a live T2 cross. Admitting PDD "properly" would
mean extending three nightly collectors to the `extra_tickers` roster (a
data-collection expansion), or loosening a documented scoring floor (a
promotion-gated methodology change). Neither is in this program's scope.
**Verdict: documented exclusion. 9961.HK carries the HK-side exposure**, and it now
has a lane that can show it.

## §2 Sequencing

1. This charter merges with PR #4331 (docs-only addition).
2. Build session (next): port lane (builder) + HK template lane (designer, unified-grid
   idiom) + G6 measurement prereg (doc). Est. one session with the US/CN patterns as
   reference.
3. G6 study runs offline; veto recalibration promotes only through the prereg.

## §2b Follow-ups opened by the adversarial review (2026-08-03)

- **Display-lane forward grading needs its OWN book (§8-class).** leaders / ran /
  vetoed were briefly appended to `data/board_ledger/hk_board.parquet` alongside the
  buy lane. They must not be: `append_board` assigns `board_pos` by list position and
  the ledger's rank-IC is Spearman(board_pos, forward excess) over a date's rows, so
  ~30 rows carrying no entry claim, no `edge_z` and no rank were taking positions in
  the graded board's own rank sample. They are display-tier by charter (§3 below,
  `hk_board_rank.DISPLAY_TIER_LANES`) and now get **no ledger writes at all**. Grading
  them remains a real question — it needs a separate store (or an explicitly
  non-graded column) whose rows never enter the buy lane's rank sample, plus its own
  pre-registered read date. Nothing accrues for them until that book exists.
- **Era fence shipped with the re-sort.** `board_ledger` gained a nullable
  `board_definition` column; HK stamps `hk_prophet_v1`, and `scorecard()` scopes
  rank-IC and IC-eligible dates to the newest definition (CN
  `china_standout_track._latest_definition_frame` pattern). Pre-stamp rows and CA
  keep their legacy pooled behaviour unchanged.

## §3 Fences

- signal_gate/`signal_quality` shared files: HK-specific parameters only via the G6 prereg —
  never a silent shared-constant change (the file also serves US/CN).
- hk_leadership stays display-tier until its own forward record supports promotion (HKRV-R5);
  its use here (leaders-lane boost + chips) is display-tier context, not rank/size/gate on the
  graded buy lane.
- Era/ledger continuity discipline (CN G5 pattern) applies if any board definition stamp
  changes.

## §4 The thin-board diagnosis (2026-08-07) — why a healthy board printed two cards

Operator, 2026-08-07 (screenshot of the live board): "HK board only shows two picks, a
ridiculous thing. Need to assess why … and look to upgrade Hong Kong Prophet by learning
from China Prophet."

**The funnel, recomputed on the 2026-08-06 runner panel** (`data/hk_stocks/*.HK.parquet`,
158 names, `signal_gate.gate(..., reclaim_veto=False)` — the shipped hk_prophet_v2
admission):

| bucket | names | share |
|---|---:|---:|
| ELIGIBLE (T2 fresh cross ×2, eligible-no-tier ×1) | 3 | 1.9% |
| held take, aged past FRESH_TICKS or topped ("the rally is weeks old") | 79 | 50% |
| buy fired, blocked on the next-bar hold | 61 | 39% |
| flat (last marker sell/cut) | 12 | 7.6% |
| bearish-divergence veto | 2 | 1.3% |
| insufficient history | 1 | — |

Cross-market, same night: CN 204 eligible of 1,665 (12.3%), US 114 of 1,576 (7.2%,
07-31 artifact), HK 3 of 156 (1.9%). The two-card board is the product of TWO
multiplicative facts — a 156-name universe (10× smaller than CN's) and a
fresh-cross-only admission on a tape whose washout leg ran in late June. Neither is a
defect in the v2 gate: 142 of the 155 non-eligible names' last marker IS a buy — the
board did not miss the wave, the wave is simply five weeks old and the page had nothing
to say about "what is setting up next".

**What China Prophet does about the identical situation, and what transfers:**

1. **The W8-R1 ripening shelf** (SHIPPED HERE, 2026-08-07): CN keeps a lifecycle shelf
   of NON-eligible names whose weekly setups are live (2W washout / fresh 1W washout
   cross / imminent 2W MACD), zoned READY / BASING by
   `engine.setup_tier.assign_ripening_zone`, watch-words only. Ported as
   `hk_board_rank.build_ripening_rows` + the `ripening` array + the shelf section in
   `templates/hk.html.j2` (same `theme.css` `.rip-*` card system → visual parity for
   free). HK caps: READY 6 / total 12 (CN 16/32, ~10× universe); CN's FALLING sink is
   deliberately NOT ported (the laggards strip already owns "weakest — avoid" here).
   Same-night measurement: the shelf holds 12 real rows (6 READY / 6 BASING) on the
   panel where the buy lane holds 2 — the board's actionable-or-watch surface goes
   2 → 14 cards with zero admission change, zero ledger writes, zero score authority.
   It lives INSIDE the setting-up filter bucket (the vetoed-inside-blocked precedent).

2. **CN's lossless lanes over the eligible set** (`partition_board_rows`:
   featured / more_actionable / late_or_unfillable / forming): NOT needed at HK's
   scale — 3 eligible names cannot be "lost", and the HK stage buckets already group
   them. Revisit only if HK eligibility breadth ever approaches CN's.

3. **Nightly self-grading audit** (`engine/cn_prophet_audit.py` — loser/miss telemetry,
   rank-effectiveness): the HK forward book (`hk_track_ledger`, first read ~2026-08-24)
   is the prerequisite. OPEN — charter an `hk_prophet_audit` once n_matured > 0; until
   then there is nothing to audit and a report over zero matured rows would be theater.

4. **Theme tape** ("top sector — where are the picks", `engine/cn_theme_tape.py`): HK
   has no THS-concept equivalent; the nearest organ is `hk_leadership` (cohort) +
   sector strips. OPEN as a design question, not a port — do not force CN's basket
   grammar onto a market without basket data.

5. **Prime-window entry ordering (CN v3 R1) and relay guard (R3)**: CN-era MEASUREMENTS
   (407 matured episodes; n=7,816 chase events). They do NOT travel as facts — HK gets
   them only via its own matured cohort + a fresh prereg. FORBIDDEN to copy the
   `_ENTRY_VALUE` reordering onto HK on CN evidence.

6. **The cheapest HK-native breadth lever stays the bearish-divergence veto prereg**
   (§0 G6 note: 1,148 blocked signals, measured null on return AND drawdown) — that is
   an admission change and runs through prereg, not through this display-tier program.

**Fences reaffirmed for the shelf:** display-tier only (`DISPLAY_TIER_LANES` names it);
no entry claim, no priority score, no graded-ledger writes (`graded_board_rows` is
buy+watch only, pinned by `TestLedgerIsTheGradedBoardOnly`); buy-lane membership
byte-identical. The shelf is context accrual — any promotion (rank/size/gate authority)
requires its own pre-registered gauntlet per house epistemics.
