# Prophet CN vs US — origination anatomy (parity receipt) — 2026-08-07

**Charter:** operator escalation 2026-08-07 ("Prophet US sucks compared to Prophet China —
figure out why CN is so good"). Anatomy only — no gate/rank change follows from this file.
Measured by an Opus review lane; sibling receipt: `ENTRY_LATENESS_FORENSIC_2026-08-07.md`.

## Headline

The two systems share ONE indicator engine, ONE tier vocabulary, and a BYTE-IDENTICAL
not_topped veto (same function, same constants: OB=80, BUY_RSI_MAX=65, FRESH_TICKS=2,
MIN_HISTORY=159 — `engine/confluence_tiers.py:428-431`). The divergence is the SELECTION
layer: **CN admits the pre-move patience statuses; US is mathematically incapable of
admitting them.**

- CN live board 2026-08-07: **24/24 rows are `bounce_wait`/`hold`/`wait_pullback`**
  (act_level 0:18, 1:6).
- US admitted set 2026-08-06: **27/27 are `buy_now`/`partial`/`buy_soon`** (act_level 3:24, 2:3),
  because `select_candidates` hard-gates `act_level >= 2` (`engine/prophet_bridge.py:440-449`)
  and `bounce_wait` maps to urgency `caution` → act_level **0** (`engine/entry_signal.py:24-33,56`).
- The US board ALREADY CARRIES 23 `bounce_wait` rows — exactly the cohort CN scores 1.0 —
  all dropped at that gate.

**The entry-value maps were deliberately inverted on 2026-08-04** (in-code note at
`engine/us_board_rank.py:113-117`): CN v3 re-ordered to the measured CN prime-window order —
`bounce_wait 1.0 … buy_soon 0.35` (`engine/china_board_rank.py:96-112`) — on evidence from 407
matured episodes (masterplan §2.3: bounce_wait 6.9% loser rate vs buy_now 30.0%). The US map
kept the trend-tape order (`buy_now 1.0 … bounce_wait 0.35`, `engine/us_board_rank.py:119-135`)
and **the US re-measurement was never run.** Stale provenance string at
`engine/us_board_rank.py:896` still claims "frozen status map, shared with the China board".

## Parity table (dimension | US | CN | anchor)

| Dimension | US | CN | file:line |
|---|---|---|---|
| Candidate lane | `us_standouts.json buy[]` (69) → second stage → 12 plans | `china_standouts.json buy[]` IS the board (24, sector cap 4); no second stage | `prophet_bridge.py:424`; `build_china_library.py:3392` |
| Timeframes | 2D/3D shared cascade | same + **weekly (1W/2W) setup layer** | `confluence_tiers.py:264-290`; `build_china_library.py:2912-2915` |
| Ripening shelf | **absent** (setup_tier imported for 2 display fields) | **live, 32 names** (16 READY / 16 BASING; e.g. "2W MACD ~0.5 bars to cross") | `build_stock_library.py:3586-3592`; `setup_tier.py:53-55,451-453` |
| Veto family | identical | identical | `confluence_tiers.py:428-431` |
| Theme/sector in rank | `theme` in ZERO_SCORE_AUTHORITY (0 pts) | `theme_timing` **15/100 pts** (WARMING/early-cycle-turn 1.0) | `us_board_rank.py:186`; `china_board_rank.py:86,312-350` |
| Theme+member double gate | `subsector_confluence.funnel()` double_buy EXISTS FOR BOTH MARKETS, wired into NEITHER board (display-only consumers) | same | `subsector_confluence.py:318-359,481-501` (docstring `:9-11`) |
| Sector turn | — | `cascade` on sector composite, display re-order only (zero authority) | `china_sector_turn.py:108,55` |
| Score weights | signal 30 / entry 25 / edge 25 / runway 10 / quality 10 | signal 30 / entry 20 / runway 15 / bottom_quality 10 / **reversal_member 10** / **theme_timing 15** | `us_board_rank.py:105-111`; `china_board_rank.py:79-87` |
| Featured statuses | `{buy_now, partial}` | `{bounce_wait, wait_pullback, hold, buy_now, partial}` | `us_board_rank.py:171`; `china_board_rank.py:116-118` |
| Freshness at origination | act_level>=2 (or >=2 OR conviction>=60 in caution), band != low | **no act_level gate**; only buy_now/partial demoted `confirmed_late` at ticks>1; patience statuses have NO tick cap | `prophet_bridge.py:440-449`; `china_board_rank.py:878-886` |
| Re-entry | `TICKER-BULL` blocked while a plan is open | keep-first per (date,ticker) — episodes re-enter | `prophet_bridge.py:318-325`; `china_standout_track.py:556-558` |
| Entry basis | asof close; invalidation = swing/2×ATR14 | **T+1 (H+L)/2**, buy_zone_low/high, `chase_above` guard | `prophet_bridge.py:204-256,332-355`; `china_standout_track.py:101` |

**Live US defect found in passing:** `us_standouts.json lane_counts.featured = 0` — all 69
blocked by `ext_z_unknown` (`engine/us_board_rank.py:86-90`). The featured lane is dark today
with no alarm.

## Top-5 structural deltas (ranked by plausible contribution to CN's earlier entries)

1. **act_level >= 2 admission gate (US-only).** Pure code gate over a status vocabulary both
   markets compute identically; CN features the statuses US drops. Portable outright.
2. **Inverted entry-value map + wider featured set.** Portable mechanism, NON-portable
   evidence: CN's ordering rests on a CN cohort (407 episodes). A US port requires a US
   re-measurement (W7 full-population stamped store makes this runnable now), not copied
   constants.
3. **Weekly setup layer + ripening shelf (CN-only lane).** Market-agnostic math; HK already
   ported it (`hk_board_rank.py:159-168,1063-1233`). The pre-cross bench is structurally
   earlier than anything the 2D/3D grid can print.
4. **Theme timing as a paid rank channel.** Mechanism ports; the edge may shrink — THS concept
   rotation is retail-flow-persistent in a way GICS rotation is not. The true theme+member
   double gate is built for both and wired to neither — not a current CN advantage.
5. **No second stage + episode re-entry.** Under a 12-slot cap fed by a late-status filter,
   "US's first look at a name is systematically its last early look." Confound stated
   plainly: A-share limit-up mechanics make early entry partly a FILL constraint (a locked
   board is unfillable) — expect a smaller effect from a US port.

**Grading confound (binding):** CN grades entry at T+1 (H+L)/2, US at asof close — CN's
measured lead is partly a grading-basis difference; the two ledgers' "days to move" are not
directly comparable.

## 300363.SZ receipt (the operator's CN example)

`china_standouts.json track_ledger.extra_records[0]` (def `cn_prophet_v2`): entered **rank 1
on 2026-08-05 at 17.52, T2, stage `early`**; peak 20.44 = **+16.7% in 2 sessions** (full 20%
ChiNext limit day 08-07). Signal-time state: `washout_2w=True`, `reversal_member=True`
(sector rank 27/150), `rev_z 2.17`, `off_high −39.9%`, `potential 85 (primed)`,
`alpha_entry=pullback`, conviction 85. That is the CN anatomy in one row: deep base + washout
fired + sector-reversal cohort + theme channel, THEN a T2 — bought in the base, not after
confirmation. US's washout organ (#4924, the CN port) is merged and DARK; `reversal_member`
has no US rank channel.

**Discrepancy flagged (do not build on this row without resolving):** the same 08-05 shadow
parquet row (`data/china_prophet_rank/candidates.parquet`) records `not_raw_eligible`,
`buyable=False`, `entry_status=await_confluence`, `score_rank 367` — contradicting `rk:1`.
A 2-session run-vs-signal-bar skew demonstrably exists in the CN lane (`signal_asof 08-06` vs
`signal_bar_asof 08-04`). CN's bookkeeping carries the same signal-date incoherence class the
US lateness forensic measured. CN is the better SELECTOR, not a clean bookkeeper.
