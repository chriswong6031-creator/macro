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
