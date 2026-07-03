# Exemplar Forensics — 688306.SS (均普智能 / Ningbo PIA Automation)

**Date:** 2026-07-03 · **Board render as-of:** 2026-07-02 · **Analyst:** Phase-1 reader (worktree `lucid-knuth-523979`)

## HEADLINE — the premise is false

**688306.SS is NOT a pick the current board surfaced.** It does not appear anywhere in the rendered board `site/china_stocks.html` (0 hits, worktree AND main checkout), and a live run of the production gate on the worktree's own 2026-07-02 price cache returns `eligible=False, tier=None, weight=0.0`, reason **"buy blocked by filter: failed reclaim-and-hold"**. The stock is down **-35.5% from its 52w high**, its reversal fuel is **negative** (rev_z = -0.35, rank 1129/1471), it is **not coiled**, and its conviction band is **"neutral / Mid-pack" (score 40)**. The owner's designation of this as a "GREAT pick the board surfaced" is contradicted by every field the system holds. What the forensics *do* show is a name that briefly qualified as a fresh T2 buy from ~2026-06-22 through 2026-07-01 (a choppy, net-negative 9-day window) and was then **correctly dropped on the 2026-07-02 render bar** when its bounce faltered and the validated buy-filter fired.

I proceeded on the answerable question — *why did the board NOT surface it, and what is the full system state* — per fable-mode §3.9 (surface the mismatch, proceed on the corrected path).

---

## 1. LOCATE

| Surface | Result | Evidence |
|---|---|---|
| Ticker form | `688306.SS` (STAR/科创板, `.SS` suffix, matches 688xxx rule) | `data/china_search/closes.parquet` column `688306.SS` present (`python`: cols matching = `['688306.SS']`) |
| `closes.parquet` (worktree) | Present, 1037 obs, 2022-03-22 → 2026-07-02 | live read of `data/china_search/closes.parquet` |
| `members.parquet` (worktree) | Present: name `均普智能 / Ningbo PIA Automation Holding Corp.`, sector **`Consumer Cyclical`** (yfinance GICS bucket), mktcap **30.0 亿** | `data/china_search/members.parquet` row `688306.SS` |
| Per-stock JSON (worktree) | **ABSENT** — `site/chinastockdata/` is EMPTY (0 files) in worktree; R2-gated by design (memory `r2-data-plane`) | `ls site/chinastockdata/ \| wc -l` = 0 |
| Per-stock JSON (fallback) | `688306.SS.json` exists only in main checkout, **asof 2026-06-26 (STALE, pre-render)** | `/Users/chriswong/Documents/Cluade/Macro Dashboard/site/chinastockdata/688306.SS.json` — **FLAGGED as main-checkout fallback, used only for cross-check** |
| Board artifact / `site/factordata/` | worktree `site/factordata/` has no china file containing 688306 | `grep -rln 688306 site/factordata/` = empty |
| **Rendered board `china_stocks.html`** | **NOT PRESENT** — 0 hits. Board carries 168 tickers incl. 17 other 688/STAR names, but not 688306 | `grep -c 688306 site/china_stocks.html` = 0; `grep -oE '[0-9]{6}\.(SS\|SZ)' \| sort -u \| wc -l` = 168 |
| `baskets_china_ths.html` | Present — member of **16 THS concept baskets** | `site/baskets_china_ths.html` BASKETS json |

**No rendered rank, no chip, no color exist for this name — because it is not on the board.**

---

## 2. SYSTEM STATE (live engine run on worktree 2026-07-02 cache)

Run: `PYTHONPATH=$PWD python3` → `engine.signal_gate.gate('688306.SS', s)` + `engine.confluence_tiers.cascade(s)`.

| Field | Value | Source |
|---|---|---|
| gate `tier_cascade` | **None** | live `gate()` |
| gate `eligible` | **False** | live `gate()` |
| gate `weight` | **0.0** | live `gate()` |
| gate `reason` | **"buy blocked by filter: failed reclaim-and-hold"** | live `gate()`; filter at `engine/signal_quality.py:179` |
| gate `ticks` | 4 | live `gate()` |
| gate `fresh_bars` | 9 | live `gate()` |
| last marker (compact) | `{date: 2026-06-18, type: rebuy, quality: block, reason: failed reclaim-and-hold}` | `signal_gate.compact(v)` |
| cascade `not_topped` | **False** (topped/rolled-over → never a fresh buy) | live `cascade()`; logic `engine/confluence_tiers.py:225-226` |
| cascade `asof` | 2026-07-02 | live `cascade()` |
| `is_buyable` | **False** | `signal_gate.is_buyable(v)` |
| **rev_z** | **-0.35** (rank 1129/1471, 23.3 pctile — sits ABOVE sector avg → negative reversal fuel) | live `china_reversal.reversal_watch(...)` `rev_z_all['688306.SS']` |
| in reversal top-16 watch | **No** | same run |
| sector (members) | **Consumer Cyclical** (yfinance bucket) | `members.parquet` |
| THS baskets | **16** (see §Themes) | `baskets_china_ths.html` |

**Fallback JSON cross-check (asof 2026-06-26, STALE, main checkout — flagged):**
- `conviction.score = 40`, `band = "neutral" / "Mid-pack"`, `composite_z = -0.435`, `verdict` starts "Neut…"
- `conviction.size = {bucket: "quarter", pct: 25, capped_by_entry: true, vol_mult: 0.74}`
- `ladder = {state: "BOTTOM WATCH", label: "NEARING A LOW", action: "GET READY", dir: "down", score: 10, regime: "bull"}`
- `entry_signal = {status: "wait_pullback", urgency: "later", headline: "Wait for the pullback"}`
- `risk_sizing = {vol_ann_pct: 35.9, size_mult: 0.74}`
- `vol_squeeze = {state: "EXPANSION", coiled: FALSE, days_compressed: 0, bbwp: 78, hv_pctile: 84}` → **not coiled; vol already elevated (move underway, not loading)**
- `washout_2w`: no explicit `washout_2w` key found in this JSON; the reversal axis (`rev_z=-0.35`) and ladder ("NEARING A LOW", not "washed out & turning") both read the name as still-falling, not a confirmed 2w washout. **washout_2w = not-flagged / False (bounded by: no key in fallback JSON + negative rev_z).**
- `mtf.D`: `stoch_cross_dn: true`, `macd_approaching_dn: true`, `rsi14=42` → daily momentum turning DOWN, consistent with the topped read.

Every held field agrees: **mid-pack, still bottoming, wait-don't-buy, not coiled.**

**Sector state:** 688306's members-file sector is the yfinance "Consumer Cyclical" bucket, which the china sector pages (`sector_central_china`, Shenwan-style taxonomy) do NOT carry per-name — 688306 does not appear in `sector_central_china_data.js` or `sector_cycles_china_data.js` (both `grep -c` = 0; those files are sector-level). Its plausible home sectors on those pages — **Advanced Manufacturing = "Bottoming"** and **Autos & NEV Makers = "Bottoming"** — are consistent with a washed-out basing name, but I **cannot assign one canonical sector_state** because of the taxonomy mismatch. Reported as **Advanced Manufacturing = Bottoming (caveated)**.

---

## 3. PRICE FORENSICS

Live from `closes.parquet['688306.SS']`, last close 9.63 (2026-07-02):

| Window | Return |
|---|---|
| ret_5d | **+3.44%** |
| ret_20d | **+7.94%** |
| ret_60d | **+8.18%** |
| ret_120d | **-16.25%** |
| off_52w_high | **-35.5%** (52w high 14.94 on 2025-09-18) |

**Path shape: washed-out → sharp dead-cat bounce → faltering.** NOT clean "based → running", NOT straight momentum.
- 52w high 14.94 (2025-09-18) → ground down to **52w low 8.37 on 2026-06-11** (-43.9% from high).
- Sharp bounce **8.37 → 10.43 by 2026-06-18 (+24.6% in 5 sessions)** — a rebuy marker fired 06-18.
- Pulled back to 8.86 (06-26), re-bounced 10.10 (06-30), **faltered to 9.63 (07-02)**.

**Cross timeline & board capture (scalar cascade, the path the builder uses):**
| Asof | Tier | not_topped | ticks | eligible |
|---|---|---|---|---|
| 2026-06-30 | **T2** (w 0.8) | True | 0 | **Yes** |
| 2026-07-01 | **T2** (w 0.8) | True | 1 | **Yes** |
| **2026-07-02 (render)** | **None** | **False** | 3 | **No — DROPPED** |

(Vectorized `tier_stream` labels the same window T1 rather than T2 — a known display/path difference between the vectorized and scalar cascade; both agree the name was ELIGIBLE 06-22→07-01 and both DROP it by 07-02. The scalar `cascade()` is authoritative for the board.)

**Earliest-flagging signal & capture math:** The **cascade (T1/T2) was the earliest of our signals to fire — 2026-06-22** — but that is **AFTER the entire +24.6% initial thrust** (8.37→10.43, 06-11→06-18) had already happened. rev_z never flagged it (stayed negative). No washout_2w, no COILED (vol in EXPANSION). Basket tailwind (see §Themes) was persistent but is a theme-level, not name-level, entry signal. So the board's eligible window **captured ~0% of the sharp move and ~9 net-negative days** (10.23 on 06-22 → 9.63 on 07-02 = **-5.9%**), then rejected the name. **Days of run captured ≈ 9 (net -5.9%); percent of the up-move captured ≈ 0% (signal fired after the thrust).**

---

## 4. UI CONTRADICTIONS

**There is NO card/row for 688306 on the board** — so there are no rendered chips to trace. This absence is itself the finding: the UI is *consistent* with the engine (blocked → not shown). The "contradiction" is between the **owner's claim** ("GREAT surfaced pick") and **every engine field**:

| Owner claim | Engine reality | Source |
|---|---|---|
| Board surfaced it | Not on board (0 hits) | `grep site/china_stocks.html` |
| Great pick | conviction band "neutral/Mid-pack", score 40, composite_z -0.435 | fallback JSON `conviction` |
| (implied fresh buy) | gate blocked "failed reclaim-and-hold"; cascade not_topped=False | `signal_gate.gate` live |
| (implied strong) | -35.5% off 52w high; rev_z -0.35 (negative fuel) | live price + reversal |
| (implied setup) | ladder "BOTTOM WATCH / NEARING A LOW / dir=down"; entry_signal "wait_pullback" | fallback JSON |
| (implied coiled/loading) | vol_squeeze coiled=FALSE, EXPANSION, bbwp 78, hv 84 pctile | fallback JSON |

Had it *stayed* on the board (it was eligible through 07-01), the only genuinely confusing UI would have been a **T2 fresh-buy chip on a name -35% off its high with negative reversal fuel and a "wait_pullback" entry_signal** — the momentum-cascade axis and the reversal/entry axis disagree. That tension traces to: cascade grades the short-TF MACD/StochRSI cross (`engine/confluence_tiers.py`) independent of the reversal fuel axis (`engine/china_reversal.py`) and the reclaim-and-hold entry filter (`engine/signal_quality.py:179`). On 07-02 the filter won and the name dropped — the correct resolution.

---

## 5. FEATURE VECTOR

| key | value | note |
|---|---|---|
| on_board_rank | **not on board** | 0 hits in `site/china_stocks.html`; gate `eligible=False` |
| ui_label | **none (not rendered)**; nearest system label = ladder "BOTTOM WATCH / NEARING A LOW" | fallback JSON (stale 06-26) |
| ui_score | **none rendered**; conviction score = **40** ("Mid-pack") | fallback JSON |
| ui_chips | **none rendered** | — |
| tier | **None** (was T2 06-30→07-01, dropped 07-02) | live scalar `cascade()` |
| ticks_since_cross | **4** (gate) / cascade `ticks=3` on 07-02 bar | live `gate()` / `cascade()` |
| ext_since_cross_pct | **-4.65%** (last eligible cross 06-30 @10.10 → 07-02 @9.63) | live price |
| rev_z | **-0.35** (rank 1129/1471, 23.3 pctile; negative fuel) | live `reversal_watch` |
| washout_2w | **False / not-flagged** (no key in fallback JSON; rev_z negative) — bounded by those two checks | fallback JSON + reversal |
| coiled | **False** (vol_squeeze EXPANSION, bbwp 78, hv_pctile 84) | fallback JSON |
| off_52w_high_pct | **-35.5%** | live price |
| ret_5d | **+3.44%** | live price |
| ret_20d | **+7.94%** | live price |
| ret_60d | **+8.18%** | live price |
| ret_120d | **-16.25%** | live price |
| sector | **Consumer Cyclical** (yfinance bucket) | `members.parquet` |
| sector_state | **Bottoming** (via Advanced Manufacturing/Autos&NEV homes; CAVEAT: no exact per-name mapping — taxonomy mismatch) | `sector_central_china_data.js` |
| strongest_theme | **Solid-State Battery (固态电池)** | `baskets_china_ths.html` perf |
| theme_rel20 | **+35.6%** (Solid-State Battery 20d rel) | `baskets_china_ths.html` perf.20d.rel |
| earliest_flagging_signal | **cascade T1/T2 momentum cross, 2026-06-22** (fired AFTER the +24.6% thrust; rev_z/washout/coiled never fired) | live `tier_stream`/`cascade` |
| days_of_run_captured | **~9 days, net -5.9%** (eligible 06-22→07-01, dropped 07-02); ~0% of the up-move captured | live `cascade` + price |

**16 THS baskets & 20d rel (context):** Solid-State Battery +35.6%, Medical Devices +19.6%, New Industrialization +18.5%, Hydrogen +16.6%, NEV +16.0%, Sensors +14.1%, Ophthalmic +13.8%, Autonomous Driving +12.9%, Humanoid Robots +12.7%, Common Prosperity +9.2%, DeepSeek AI +7.7%, Reducers/Gearboxes +7.1%, Auto Thermal Mgmt +6.1%, AI Agents +5.4%, mmWave Radar +2.1%, BCI -6.4%. Strong theme tailwind, weak individual name — the divergence the board exists to arbitrate.

---

## Method / data-provenance notes
- All signal state is derived **LIVE** from the worktree's own `data/china_search/closes.parquet` (mtime Jul 3 04:45, runs through 2026-07-02, matching the board's as-of) via the worktree's `engine/`. This is authoritative and needs no fallback.
- The only **main-checkout fallback** used: `site/chinastockdata/688306.SS.json` (**asof 2026-06-26, STALE**), for cross-checking held conviction/ladder/entry/vol fields — its every field corroborates the live verdict. The worktree `site/chinastockdata/` is empty (R2-gated).
- No code or data modified.
