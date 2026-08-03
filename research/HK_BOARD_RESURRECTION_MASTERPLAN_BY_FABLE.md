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
- The seven witnesses (0700/9988/9618/1810/3690/1024 + 9961.HK as PDD's HK twin) all bottomed
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
- **G6 — The 200-dma veto gets a measurement, not a hot-patch.** Ship display-tier relief
  first (G1-G4 make blocked names VISIBLE with the blocking reason named). The veto itself
  changes only via prereg: offline scan machinery (US gate-width pattern) over the HK panel
  measuring (a) re-test cadence variants (the one-shot no-retest defect), (b) HK-depth reclaim
  windows, with forward comparison before any admission change. Pre-registered before the
  first grade is read.
- **G7 — Plumbing heals.** The board_track ledger write failure diagnosed and fixed (health
  leg green); the 126-session beta-gate universe gap gets a fallback (name admitted with
  beta=null context rather than silently dropped) or a disclosed exclusion count.
- **G8 — PDD question answered.** Determine why PDD (NASDAQ, NDX constituent) is absent from
  all US lanes and either admit it to the US universe properly or document the exclusion;
  9961.HK carries the HK-side exposure either way.
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

**Measured witness visibility: 6 of 7** — 9618 (leaders), 3690 (ran), 0700 / 9988 /
1810 / 1024 (vetoed). 9961.HK stays dark and honestly so: outside the mega-cap
cohort, −12% on the quarter, and its post-marker move does not beat the non-cohort
field. G1's ≥5 pin is met with no gate loosened. The lane is deliberately
self-critical — it exists to print what the board missed, so it is working when it
reads badly. It is also the G6 study's product-side receipt: 1024.HK has been
blocked on a single 2026-05-06 marker for 59 sessions, and the lane says so.

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

## §3 Fences

- signal_gate/`signal_quality` shared files: HK-specific parameters only via the G6 prereg —
  never a silent shared-constant change (the file also serves US/CN).
- hk_leadership stays display-tier until its own forward record supports promotion (HKRV-R5);
  its use here (leaders-lane boost + chips) is display-tier context, not rank/size/gate on the
  graded buy lane.
- Era/ledger continuity discipline (CN G5 pattern) applies if any board definition stamp
  changes.
