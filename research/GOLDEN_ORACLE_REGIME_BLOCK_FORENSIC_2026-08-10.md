# Golden Oracle regime-blocked entries & structure stops — cross-repo forensic

**Date:** 2026-08-10 · **Tier:** research — investigation record + upgrade charter input, **NOT a change**
· **Trigger:** operator observed ⊘ "regime-blocked" markers sitting at major bottoms (UEC ×4), a
structure stop firing immediately before HL's breakout, no NEM entry on its largest breakout, and
blocked entries at the lows of two winning CN miners (600547.SS, 002716.SZ).
· **Receipts pulled live 2026-08-10 ~05:00Z** from the VPS-served slices (regenerated 2026-08-09
23:14–23:38 UTC, 10,047 slices, refresh green, data through 2026-08-07).

> **Verdict in one line:** all five incidents are one mechanism working as designed — the Terminal's
> entry trigger is a mean-reversion oscillator turn while its veto demands trend health, a pair that
> is maximally contradictory at capitulation lows — plus one rendering-history fact (blocked fires
> were drawn as real entry stars until 2026-08-08) and zero regressions. Nothing here is a bug in the
> signal math; the cost of the veto is real, measured, and currently un-ledgered.

---

## §1 Three engines, one name

Three separate confluence implementations produce "oracle"-family verdicts (documented in
`research/prophet_us_audit/HK_ORACLE_FORENSIC_2026-08-08.md` §"third implementation"):

1. **Terminal Golden Oracle** — charting-app `signal_layer/confluence.py` + `confluence_v2.py`,
   precomputed server-side into static `terminal/public/data/<SYM>.slice.json` (writers:
   `ingest/build_polygon_universe.py` → `ingest/regen_flagship_slices.py` → `ingest/gen_slices_all.py`
   in the VPS nightly `/usr/local/bin/terminal-data`, cron 30 21 UTC). ChartPanel only draws what the
   JSON says (`terminal/components/ChartPanel.tsx` `resolveSigMarks`/`renderSignals`).
2. **Macro-dashboard `engine/signal_quality.py`** — the Prophet US/CN/HK buy-filter chain
   (`_buy_filter` → `signal_gate.gate` → `confluence_tiers` T1–T4).
3. **Macro-dashboard `engine/canon.py:421 confluence_signals`** — display-only leaf
   (per `research/STOCKINVEST_TECH_INDICATOR_SUITE_PROGRAM.md` finding #2).

They share the CB/revBuy vocabulary but run on different grids with different vetoes — Terminal and
Prophet **routinely disagree on the same chart** (UEC: Terminal ⊘+flat vs Prophet T1 "TURN
SIGNALED/BOTTOMING/PRIME" + live plan `site/prophet/plans/UEC-BULL-20260731.json` trigger 11.48).

## §2 Terminal mechanics (charting-app, receipts at cited lines)

Grid: **3D bars**; indicators MACD-on-RSI 14/60/5 × StochRSI 14/14/3/3 (80/20), weekly/2-week/monthly
confirm gates; `CONF_W=8`, `BUY_RSI_MAX=65`, `REV_BARS=3`.

- **BUY ★** `confluence.py:293`: `macd_bull & recent_b1 & confirm_bull & buy_regime_ok`
  (bull cross + StochRSI up-cross from oversold ≤8 bars ago + weekly confirm + RSI14<65).
- **REBUY** `:298`: bull cross ≤3 bars after a SELL.
- **RECLAIM** (`confluence_v2.py:619-624`): re-entry lane after a stop — needs
  `close > sell-bar close` **AND** `w_bull` **AND** `above200`.
- **SELL = structure stop** (the red STOP pill; `confluence_v2.py:455-546`, `contracts.py:270-292`):
  two-stage on the **daily** grid — ARM on a 2D RSI-MACD bear cross while 3D StochRSI ≥75 (or 3D
  stoch bear cross with k≥80), CONFIRM when a daily **close** prints below the last confirmed
  radius-3 swing low (PIT: pivot knowable at p+3) within the armed window. Reasons emitted:
  `distribution_confirmed`, `structure_break`; carries `stop_level`; flips `position_hint` flat.
- **⊘ regime-blocked** `confluence.py:315-316,342`, `contracts.py:187-194`:
  `bear_block = (~mo_bull) & (~above200) & (~w2_bull)` — **all three own-ticker trend gates bearish**
  → raw CB/revBuy stamped `quality="regime_blocked"`, never taken (`enter = (CB|revBuy) & ~bear_block`).
  Per-ticker only; the macro "Market risk" chip (`ingest/pull_macro_risk.py`, display-only) feeds none of it.
- **`quality="block"`** (hollow marker, different from ⊘): passed bear_block but failed the
  **reclaim-and-hold** leg (`confluence_v2.py:99-119`) — same family as Prophet's veto below.
- **"Awaiting confluence" Research-Desk chip is a different machine**: `signalVerdict.ts` `deskVerdict`
  reads only `intel.tape.ai_lean` from `ingest/pull_macro_intel.py` ← `entry_signal.assess`; **no
  oracle event can clear it** — only the next research-desk run.

**Why ⊘ sits at bottoms (structural, not incidental):** the trigger (StochRSI oversold-turn + RSI-MACD
cross) fires at washout lows by construction; the veto requires monthly-bear ∧ below-200 ∧ 2W-bear,
which is *most likely true* at exactly those lows. The deeper the capitulation, the more certain the
raw fire and the more certain its refusal. Confirmed prior: HK forensic 0700.HK (Jun-5 bottom fired →
`regime_blocked`; Jul-3 bottom couldn't re-fire at all — MACD never re-crossed).

**Truth-in-labeling history (the "recent update"):** the `bear_block` formula is **byte-identical
since 2026-06-26** (pickaxe + blame census, origin/master). Everything in-window changed *visibility*,
not gating: `5e47edd6` (07-10) first wired the veto's verdict into the emitted stream (git catching up
to the prod engine); `b06730bc` (07-15) stopped blocked fires from flipping the scored verdict/
`position_hint` (a blocked BUY had rendered a full-authority green Buy — META 07-15 incident);
`c9f6bc1a` (08-03) + `feceb369` (08-05) made fresh blocks HEADLINE the verdict card (amber
"Entry trigger — regime-blocked", `var(--signal)` #e8b339 — the operator's "yellow"); `7e49bade`
(08-08, HK-O1) changed the glyph — before it, regime-vetoed entries **drew solid BUY stars** (its own
comment: the operator chased 9988.HK's vetoed star) — and silenced live BUY alerts for vetoed setups
(a gap open since the alert engine's inception). Six-era A/B on identical OHLC: **byte-identical event
dates/types** — no entry-suppression regression exists; fake entries stopped looking real. Two more
context facts: `c080f5a5` (07-10) flipped the Golden Oracle overlay **OFF by default** for new
browsers (still true on master — a fresh browser shows no oracle markers until enabled), and
`25d98e8c`'s body records a ~1-day deploy regression (07-10→11) during which **every flagship BUY
rendered `regime_blocked`** until the v2 re-emission pass was added to the nightly.

## §3 The five incidents — served-slice receipts (pulled 2026-08-10)

| Name | Event | Served receipt | Aftermath (2026-08-07/09) |
|---|---|---|---|
| **UEC** | 4× ⊘ at 2023-05/2024-09/2024-12/2026-08 lows | last: `BUY 2026-08-03 (known 08-05) @10.72, quality=regime_blocked, reason "bear_block: monthly-bear & below-200 & 2W-not-bull"`; state flat | ~11.5 (+7%); Prophet side: T1 eligible, plan trigger 11.48 `pre_trigger` |
| **HL** | STOP right before breakout | `SELL 2026-07-31 basis=structure_stop stop_level=14.29 close=14.12` (armed by overbought-stoch bear cross; broke the confirmed r3 swing low); prior BUYs 05-07/05-26 take @17.59, 06-16 @15.96 + 06-25 @15.40 both `block: counter-trend, no 200-reclaim/hold` | 16.85 (+19% in 5 sessions off the stop). Both re-entry lanes shut: RECLAIM needs close>14.12 ✓ **and** above200 (200d≈18) ✗; fresh CB needs bear_block off ✗ |
| **NEM** | No entry on record breakout | last event **2026-01-30** `SELL structure_stop stop_level=113.62 close=111.86`; **no event since** — no CB fired (no 3D MACD bull cross yet), state `flat, bars_since=44, weeklyBull=false, above200=true, overbought=true` | ~112.3. RECLAIM lane: close>111.86 ✓ (marginal), above200 ✓, **w_bull ✗ — one gate short**; will admit ~28% above the low when it flips |
| **600547.SS** | ⊘ at the July low | `BUY 2026-07-03 (known 07-07) @24.59 quality=regime_blocked` (all three gates bearish); prior take-BUY 2025-12-22 @40.08, stop 2026-02-05 @45.82 | 30.97 (+26% since blocked fire). Worst re-admission trap: RECLAIM needs close>**45.82** (+48% away); fresh CB needs a new MACD cross that a V-recovery may never print |
| **002716.SZ** | ⊘ at the July low ("perfect entry") | `BUY 2026-07-23 (known 07-27) @7.69 quality=regime_blocked`; NOTE sim was still **long from 2025-12-29 take-BUY @6.92** (never stopped) — the ⊘ refused a re-add, and the header's green "BUY" chip is the *correct* scored state, not contamination | 9.11 (+18.5% since blocked fire) |
| **SI=F** (silver fut., W) | ⊘ at the early-Aug low | operator-reported rail card "Entry trigger — regime-blocked, Aug 5"; header STOP = prior structure stop; **not slice-verified** (operator: "no need to retest" — accepted as a 6th instance of the same mechanism) | 63.98 (+~10% off the low) |

**Prophet-side treatment of the same names** (`data/us_prophet_rank/candidates/2026-08.parquet`,
`data/china_prophet_rank/candidates.parquet`): NEM 08-07 `buy blocked by filter: counter-trend, held
but no 200-reclaim`, eligible=False; 600547.SS refused **six consecutive sessions** 07-31→08-07 and
002716.SZ 08-05→08-07 on the same veto strings. **Neither NEM nor 600547 was ever a genuine Prophet
pick**: the remembered "picks" are `plab_random_ctrl`/`cnlab_random_ctrl` rows (2026-07-15 NEM,
2026-07-23 600547 — the pick-lab's random-control yardstick lane, labeled as such in
`scripts/build_pick_lab.py:1022` and styled muted-italic in `templates/us_stocks_lab.html.j2:52-53`,
`authority: display_only`). The operator's three winning miner buys were made **against** every
engine's verdict; only the placebo lane "printed" them.

## §4 What is already measured (do not re-litigate pooled evidence with anecdotes)

`research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md` (frozen JSON, 353 refused fires /
1,540 names / 126 sessions): pooled refused cohort **−4.54pp** median excess vs SPY @21d (56.7%
losers vs 29.8% winners; no drawdown band positive at any horizon; per-date weighting −1.87pp on 34
clustered dates). **§6: the sign flips with the tape** — Jan–Apr drawdown −6.96pp (veto saved) vs
May–Jul recovery **+4.67pp** (veto cost; censored at 63d). HK measured the mirror and dropped the leg
(`hk_prophet_v2`, #4470: refused names +8.7%..+44%). §9 operator ruling: US keeps the veto; flat drop
**REJECTED**; only revival path = **regime-conditional construction** on the CN→US handoff §6
machinery (`research/CN_TO_US_PROPHET_HANDOFF_2026-08-04.md` — machinery **not yet built**) + fresh
prereg + `us_prophet_v1→v2` era stamp. Registry: `DNR:KILL-200DMA-RECLAIM-VETO-FLAT`.
The five incidents above are textbook members of the recovery-leg cost tail that path exists to
recover — they are **evidence for the chartered conditional, not for a flat drop**.

## §5 Defects & gaps found (each independently actionable)

1. **No shadow ledger anywhere for blocked fires.** charting-app `backtest.py`/`simulate` hard-exclude
   `bear_block` bars from the enter mask (no counterfactual arm); macro-side standing near-miss
   capture (`scripts/build_stock_library.py:3988-4008` → `track_record.log_near_misses`) grades only
   `freshness_expired`/`not_topped_veto` — the reclaim/bear-div/regime refusals are **not accrued**.
   The 08-05 packet was a one-off replay. Consequence: the ≥60-session packet re-run (§4 lawful
   prereg input, due ~late Oct 2026) will again need a bespoke replay instead of reading a ledger.
2. **State semantics, CORRECTED during this forensic:** the scored-state walk was fixed on master
   2026-07-15 (`b06730bc`: `_state()` excludes `quality=="regime_blocked"` from
   `last_scored_signal`/`position_hint`; the earlier "unfixed" read came from a stale Jul-13 branch
   checkout). Residual: the separate `last_signal` field still reflects blocked fires (600547/002716
   show `last_signal: BUY` from ⊘ fires while `last_scored_*` stays honest) — whether any surface
   keys off raw `last_signal`, and what worktree `fix-363`'s additional exclusion targets, is for the
   Terminal lane to confirm. 002716's green header "BUY" chip is the legitimate scored long from
   2025-12-29, not contamination.
3. **Served-vs-local event divergence (NEM):** local replay through Jul-08 shows 2026 stops
   Jan-30/Feb-05/May-19; the served slice's last event is Jan-30 — the served daily-grid store and
   local splice differ. Not load-bearing for this forensic's verdicts; worth one look by the terminal
   lane when touching `gen_slices_all`.
4. **Deploy last-writer-wins wrapper:** `ingest/terminal-refresh.sh` warns two installers overwrite
   `/usr/local/bin/terminal-data`. Verified live 2026-08-10: the installed wrapper is the composed
   staged nightly (flagship + full-universe marathon + `verify_publish`) — **benign tonight**, but the
   two-installer race remains a standing foot-gun.
5. **Mixed-voice surfaces:** Research-Desk chip ("Awaiting confluence"/"Neutral", from `ai_lean`) and
   the Oracle rail can contradict on the same rail; they are different machines (§2) and nothing
   documents that on-surface.
6. **Placebo-lane readability:** two of the operator's three miner buys trace to random-control
   yardstick rows read as picks. The lane IS labeled (§3) — but if a yardstick row can be remembered
   as an endorsement, the lab surface's labeling strength is worth a design pass (no ruling here).

## §6 Upgrade paths — what is legal now vs what needs a prereg

**Display-tier, buildable freely (nulls printed; no authority change):**
- **Standing blocked-fire shadow ledger** — nightly accrual of every refused entry
  (`regime_blocked` + `CT_RECLAIM_FAIL`/`CT_BOTH_FAIL` + bear-div) with forward outcomes at
  10/21/63d vs benchmark, per market, per regime state — extending the existing
  `REJECTION_TAXONOMY`/`log_near_misses` spine rather than a new system. This converts the §4
  packet re-run into a table read, powers an honest "blocked at X, now +Y%" receipt on Tier-2
  surfaces, and accrues exactly the regime-conditional evidence §4's revival path requires.
- **Blocked-cohort arm in charting-app `backtest.py`** (counterfactual trades of the ⊘ set under the
  same exit rules) — same yardstick discipline as the pick-lab random lane.
- Surface honesty: the amber card already ships; a Tier-2 hover can carry the plain-word cost/save
  framing ("this gate refuses entries like this; over the last N sessions refused entries ran …").

**Promotion-tier, ONLY via fresh prereg (per §4 ruling + house epistemics):**
- **Regime-conditional veto relaxation** (the chartered path; machinery unbuilt).
- **Relaxed reclaim leg** (N>2 bars or proximity band — the packet's named open middle).
- **Capitulation-override construction** (blocked-fire + depth/volume-climax conditions as a distinct
  entry family). Candidate constructions only; the pooled evidence today says refused fires LOSE
  −4.54pp @21 — an anecdote set of five winning miners during a gold/silver/uranium thesis leg does
  not overturn a 353-fire panel, which is precisely why the ledger (above) must accrue before any
  promotion attempt.
- Structure-stop asymmetry (stop confirms at lows; RECLAIM demands trend reclamation ~15-50% higher)
  is a legitimate prereg target of its own (e.g., a re-arm lane conditioned on the stop bar being a
  terminal flush), same discipline.

**Coordination:** charting-app worktree `shandong-gold-signal-blocking-*` (amber card, live) and
`fix-363` (state fix) are active lanes — Terminal-side changes route through them, not new lanes.
This repo's side (ledger extension, prereg charters) is unclaimed as of this writing
(`docs/ACTIVE_BUILD_MAP.md` checked 2026-08-10).

## §7 Explicit non-actions

No signal, threshold, veto, or marker behavior was changed by this forensic. No promotion is implied.
The word applied to blocked entries stays "refused", not "wrong" — §4's pooled ledger is the standing
evidence and it currently favors the veto on average while funding the conditional-relaxation charter.
