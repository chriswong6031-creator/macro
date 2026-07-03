# Exemplar Forensics — 300725.SZ (PharmaBlock Sciences / 药石科技)

**Owner verdict:** a GREAT pick the current China board surfaced.
**Board as_of:** 2026-07-02 · **Report date:** 2026-07-03 · **Rank:** #3 of 110 buy rows.

All claims cited to `file:line` in the worktree
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/lucid-knuth-523979`
or to a command whose output is quoted. Prices are dividend-ADJUSTED close (per MEMORY: yahoo close is total-return).

---

## 0. Data provenance & a fallback flag

- Ticker form **`300725.SZ`** (ChiNext, 300xxx → `.SZ`) confirmed as a column in
  `data/china_search/closes.parquet` (worktree copy, 1507 cols; command:
  `pyarrow.parquet ... 300725 cols: ['300725.SZ']`). Series n=1221, 2021-06-18 → 2026-07-02, last px 36.79.
- **Per-stock JSON `site/chinastockdata/` does NOT exist in this worktree.** The board render for
  the China *stocks* page reads from `site/factordata/china_standouts.json` (fresh; as_of 2026-07-02),
  which is present and authoritative — I used it. The per-name lookup JSON exists only in the
  **main checkout fallback** `/Users/chriswong/Documents/Cluade/Macro Dashboard/site/chinastockdata/300725.SZ.json`
  and is **STALE** (`asof: 2026-06-26`, 6 days behind the board). I did **not** rely on it for state; flagged per instructions.
- LIVE re-runs below use `data/china_search/closes.parquet` (worktree) through 2026-07-02, matching the board's `data_through`.

---

## 1. LOCATE — where 300725 lives

| Artifact | Path | Presence |
|---|---|---|
| Close series | `data/china_search/closes.parquet` col `300725.SZ` | present (worktree) |
| Board buy row | `site/factordata/china_standouts.json` → `buy[2]` (rank #3/110) | present |
| Setups | `site/factordata/china_setups.json` (keyed `300725.SZ`) | present |
| Alpha | `site/factordata/china_alpha.json['300725.SZ']` | present |
| Reversal | `site/factordata/china_reversal.json['300725.SZ'] = -0.52` | present |
| Rendered card | `site/china_stocks.html:1398-1467` (`nbcard nb-up`) | present |
| Per-stock lookup JSON | `site/chinastockdata/300725.SZ.json` | **absent in worktree; stale in main** |

Board writer: `scripts/build_china_library.py:1348` writes `china_standouts.json`;
rank order set by `signal_gate.blend_sorted(...)` at `:1225-1230` (`rank_by="confluence"`, `:1267`).

**Rendered card position:** DOM ordinal 4 of 110 `nbcard`s (one non-buy card precedes the strip);
buy-list index 2 → **rank #3**. `href="china_lookup.html#300725.SZ"`, class `nb-up` (green).

---

## 2. SYSTEM STATE — every field the system holds

Source: `china_standouts.json buy[2]` unless noted.

**Identity/label:** name "PharmaBlock Sciences (Nanjing), Inc. / 药石科技", `sector: "Healthcare"`,
`state: "RALLY ON"`, `label: "UPTREND"`, `urgency: "hold"`, `dir/eq_dir: "up"`.

**Conviction:** `score 43` · `band "neutral"` / `band_en "Watch"` (`观察`) · `composite_z −0.268` ·
`rank_pctile 46` · `verdict "Uptrend — hold, add on dips"` · `trust_tier: reversal`
("validated but high-variance, not a buy list", css `tt-reversal`) · `validation_status neutral_ic` ·
`provenance.uncalibrated: true`, `n_axes 2`.

- **potential** (the DISPLAYED score): `score 43`, `tier "watch"`, band "Watch";
  components `fuel 0.618 / trigger 0.63 / survive 0.88 / tailwind 1.0 / confidence 1.004 / edge 1.0`;
  reasoning `["-30% off its high — room to recover", "stressed tape — size down"]`.
  Source overwrite: `build_china_library.py:1042` `_c["score"] = _pot["score"]`; `rank_pctile` = old
  percentile preserved (`:1041`).
- **axes:** SEL z −0.269 / pct 46 (present `rev_z, alpha`, kind "mean-reversion");
  ENT z −0.267 / pct 46 (present `urgency, off-high, rsi, vol-squeeze`, blocked false);
  **TWD (tailwind) z null / pct null — NO DATA**; QUAL null.

**Ladder / alignment** (`conviction.alignment`): `aligned: false`, `overextended: true`,
`entry_tier: "Extended — wait"` (`已过热 — 等回调`), reason "Already extended (overbought / far above
the 200-day) — wait for a pullback", `weekly "bear_recovering"`, `three_day "rising"`, `daily "rolling"`,
line "Weekly bear recovering · 3-Day turn↑ · Daily —", score/quality 67.5.

**entry_signal:** `status "hold"`, headline "Hold — don't add here", action "Trend intact — hold; add on
dips toward the 10-day average.", `entry_z 33.2`, `entry_grade "light"`, buy_zone 33.65–35.22
(`−6.4%` from spot), `chase_above 36.79`, `stop 31.25`, `spot 36.79`, `atr_pct 2.43`,
horizon d3 0.33 / d21 0.34 / **d63 −0.40**, timing "opens_in_days 9–30",
cycle_pos dc_day 14 / band [23,44] / pct_through 32 / phase "mid".

**risk_sizing:** `vol_ann_pct 50.1`, `inv_vol_mult 0.44`, `regime_gross 1.0`, `size_mult 0.44`
(halved size). Conviction.size bucket "full" pct 100 but vol_mult 0.44; risk drivers `["QVIX panic"]`,
`macro_stress 0.6`.

**coiled:** `coiled: true`, star false, `washout_ctx true`, `cohort 0.748`, div false, **bonus 0.25**.

**washout_2w:** `true`.

**extension:** `score 0.007`, `extended: false`, `limit_up false`, `turn_ratio 1.724`,
`turn_spike false`, reason "+1.6σ vs 20d MA". (Note the internal tension with `alignment.overextended:true` — §4.)

**vol_squeeze:** state "EXPANSION", coiled false, days_compressed 0, `bbwp 86.0`, `hv_pctile 91.0`;
caveat "Volatility is already elevated … the move is underway, not loading … the quiet entry is already gone."

**Cascade tier + ticks (STORED):** `signal.tier_cascade "T1"`, `weight 1.0`, `ticks 2`, `fresh_bars 4`,
sub "pending", `last {date 2026-06-26, type buy, quality pending}`, asof 2026-07-01, above200 false, weekly_bull false.

**Cascade tier + ticks (LIVE, re-run this session through 2026-07-02):**
`signal_gate.gate('300725.SZ', s)` → `tier_cascade "T1"`, `weight 1.0`, `ticks 2`, `fresh_bars 3`,
sub "pending", `last {date 2026-06-29, type buy, quality pending}`, asof 2026-07-02.
The T1 is produced by the **pending-master promotion** in `signal_gate.py:189-191` (a forming
'pending' master → T1 while `not topped and fresh`); raw `confluence_tiers.cascade(...)` alone returns
`tier: null` for this series. LIVE and STORED agree on tier/ticks; the `last.date` differs (06-29 vs 06-26)
because the board snapshot is one collection cycle older.

**rev_z:** `−0.52` (`china_reversal.json`; echoed in axes.basis leg `rev_z z −0.52`, tier "validated").
Mild reversal signal, not deep.

**alpha:** `0.42` (`china_alpha.json`: total_mom 17.6, rev_1m 8.7, rev_pctile 74.0, rs 43, sector_rank 49/120).

**Basket / theme membership:** THS **"Synthetic Biology" (合成生物)**, `site/chinabasketdata/baskets_ths.json`,
category "Healthcare & Biotech", 8 members. **Basket perf: 20d ret +16.6% / rel +18.9%; 60d rel +17.7%;
5d rel +3.1%; ytd rel +16.5%.** A strong, live theme tailwind. Not in `narrative_emergence.json` or `baskets.json`.

**Sector state (`sector_central_china_data.js`, as_of 2026-07-02):**
- Market: **Risk-off — de-risking** (`risk_on −0.94`, `gate_factor 0.2`, tone "off").
- The board tags 300725 `sector: "Healthcare"` (GICS-style). sector_central uses **Shenwan** names — there is
  no "Healthcare" node. Closest = **"Pharma & Biotech"**: cycle phase Trough / "Bottoming" (pos 3.3),
  state label "Recovering" (`修复回升`, signature 30.0), conviction score 53 "Neutral", confluence 1-of-3 "low/mixed".
  So the sector is *early-recovery / bottoming*, consistent with the name's washed-out setup, but the board's
  label taxonomy does not join to it (taxonomy mismatch — §4).

---

## 3. PRICE FORENSICS

Command output (LIVE, worktree parquet through 2026-07-02):

```
ret_5d   = +6.4%
ret_20d  = +7.6%
ret_60d  = -3.0%
ret_120d = -4.4%
52w high = 52.64 (2025-07-29)   off_high = -30.1%
120d low = 31.25 (2026-06-11)   recovery since low = +17.7%
```

**Path shape: washed-out → based → early recovery** (NOT straight momentum, NOT a post-catalyst gap).
Fell −40% from the 52.64 high (2025-07) into a 31.25 low on 2026-06-11, bottomed/based for ~2 weeks,
then turned up. ret_5d/20d are positive (the bounce), but ret_60d and ret_120d are still **negative** — the
name has not yet recovered its 3-month level. off_high −30.1% ("room to recover", per potential.reasoning).
Extension is genuinely low (score 0.007, +1.6σ), so it is NOT chased on this metric.

**Cross timeline (walk of `signal_gate.gate` over the last 40 trading days):**

| date | px | tier_cascade | ticks | eligible | last buy |
|---|---|---|---|---|---|
| 2026-05-07 → 06-23 | 39→34 | None | 8–18 | **False** | 04-06 buy (blocked), then 05-21 **sell** |
| **2026-06-24** | 35.45 | **T2** | 1 | **True** | 06-24 buy pending ← FIRST FLAG |
| 2026-06-25 | 34.59 | None | 19 | False | 05-21 sell (flickered off) |
| 2026-06-26 | 33.51 | None | 19 | False | 05-21 sell |
| 2026-06-29 | 36.18 | T2 | 2 | True | 06-29 buy pending (re-fire) |
| 2026-06-30 | 36.60 | **T1** | 1 | True | 06-29 buy pending |
| 2026-07-01 | 37.88 | T1 | 1 | True | 06-29 buy pending |
| 2026-07-02 | 36.79 | T1 | 2 | True | 06-29 buy pending |

**First-flag by signal (earliest wins):**
- **washout_2w / COILED (via the fresh-cross gate): 2026-06-24 @ 35.45** — the EARLIEST board flag (T2).
  It flickered off 06-25/26, then re-fired 06-29 and matured to T1 by 06-30.
- T3/T4 *projection*: not surfaced in the stored record (`bars_to_cross: null`, no T3/T4 tier in the walk);
  I found no earlier projected-cross flag than the 06-24 T2. (Bounded by: I ran `gate()` per day, which
  layers cascade; a dedicated T3/T4-projection replay was not separately run — stated as a limit.)
- basket tailwind (Synthetic Biology): strongly positive over 20d/60d but **not wired into this name's
  tailwind axis** (TWD = null), so it never "flagged" the name in-engine.

**Run captured vs missed** (low 31.25 06-11 → spot 36.79 07-02, total **+17.7%** over 21 cal days):
- Missed low → first flag (35.45, 06-24): **+13.4% (76% of the move)**.
- Captured first flag → spot: **+3.8% (21% of the move)**, 8 calendar days.
The board is a *late, confirmation-style* entry on this name: it flags AFTER most of the bounce off the
absolute low, by design (washout-reclaim needs the reclaim to happen first).

---

## 4. UI CONTRADICTIONS — negative/confusing elements while ranked #3

Each traced to its engine source.

1. **Score "43 / ready" with band-neutral ("Watch") — yet rank #3.**
   Card `site/china_stocks.html:1410` (`nb-cscore band-neutral … ready 43`). Source: displayed score =
   `potential.score` (`build_china_library.py:1042`), which PENALISES extension and is a 0–100 readiness,
   not a rank. Rank is set independently by `blend_sorted` on cascade **tier + bonus** (§ below). So a
   "Watch/43" name legitimately sits at #3. The card tooltip even admits it: "a high score can still read 'wait'."
   → **The displayed number does not explain the rank.**

2. **"Hold — don't add here" entry banner (`nbe-hold`, red-dot a1) on a rank-#3 BUY card.**
   `:1418-1421`. Source `entry_signal.status "hold"`, headline "Hold — don't add here". The board surfaces the
   name (fresh T1 cross) but the entry gauge says the *price* is above the buy zone (spot 36.79 vs zone
   33.65–35.22, `−6.4%`). Two engines disagreeing on the same card: cascade says "fresh buy", entry gauge says "wait for a dip".

3. **"Extended — wait" / `overextended: true` inside conviction, vs `extension.extended: false`.**
   `alignment.entry_tier "Extended — wait"`, `overextended true` (from the 200-day distance / alignment engine)
   CONTRADICTS the anti-chase `extension.extended false` (score 0.007, +1.6σ, the metric that drives
   `EXT_PENALTY`). Two different "extension" definitions produce opposite reads; only the `extension.*` one
   affects rank (`_cn_bonus`, `:1222`), the `overextended` one only colors the alignment line.

4. **`d63 −0.40` forward horizon (negative 3-month expectancy) on a "GREAT pick" buy.**
   `entry_signal.horizon.d63 −0.40`. The engine's own forward read for 63 days is negative even as it lists it a buy.

5. **`trust_tier: "reversal — validated but high-variance, NOT a buy list"` on a card that IS on the buy list.**
   `conviction.trust_tier` (css `tt-reversal`). The name's edge basis is mean-reversion (SEL kind
   "mean-reversion", legs rev_z + alpha), which the engine itself flags as "not a buy list" — yet it is #3 on the buy board.

6. **TWD (tailwind) axis "no data" (`ax-na`, width 0%) despite a +18.9% 20d-rel theme.**
   `:1455-1458`. The Synthetic Biology basket is strongly positive but the tailwind axis is null
   (`axes.tailwind.z null`). A real, quantified tailwind is invisible on the card — the one unambiguously
   bullish fact about this name is the field that reads "no data".

7. **"RALLY ON" / "UPTREND" state vs ret_60d −3.0% / ret_120d −4.4%.**
   `state "RALLY ON"`, `label "UPTREND"`. True on 5/20d, but the name is still net-down over 60/120d;
   the uptrend label reflects only the recent bounce.

8. **vol_squeeze caveat "the quiet entry is already gone" (EXPANSION, bbwp 86, hv_pctile 91) on a buy.**
   `conviction.vol_squeeze.caveat`. The engine says volatility is already top-fifth — a late read — while the card is a buy.

**Why #3 despite all of the above (rank mechanics, `build_china_library.py:1184-1230`):**
`blend_sorted` orders by cascade **tier first** (T1 weight 1.0 → top), then lifts by `_cn_bonus`:
`WASHOUT_BONUS 0.5` (washout_2w true) + COILED `bonus 0.25` − `EXT_PENALTY 0.5 × ext 0.007` (≈ −0.0035).
Net bonus ≈ **+0.75** on the 0..1 blend. So the rank is bought by **T1 tier + washout + coiled**, entirely
independent of the score-43 / "Hold" / "reversal-tier" signals that dominate the visible card. The card and
the ranker are reading different fields.

---

## 5. FEATURE VECTOR (orchestrator diff table)

| key | value | source |
|---|---|---|
| on_board_rank | 3 (of 110) | `china_standouts.json buy[2]` |
| ui_label | UPTREND / "RALLY ON" · verdict "Uptrend — hold, add on dips" | card `:1400-1411` |
| ui_score | 43 ("Watch"/neutral); rank_pctile 46 | `:1410`; conviction.score/rank_pctile |
| ui_chips | `T1·1.0` (sig-pending "forming"), 🌊 2W washout, ⚡ Coiled, −30.1% off 52w high; entry "Hold — don't add here" | card `:1402-1421` |
| tier | T1 (LIVE + stored; via pending-master promotion) | gate() LIVE; `signal.tier_cascade` |
| ticks_since_cross | 2 | LIVE gate `ticks:2`; stored `signal.ticks:2` |
| ext_since_cross_pct | ~ +3.8% (first fresh flag 06-24 @35.45 → spot 36.79) | price walk §3 |
| rev_z | −0.52 | `china_reversal.json`; axes basis |
| washout_2w | true | `china_standouts.json` |
| coiled | true (bonus 0.25, cohort 0.748, washout_ctx true, star false) | conviction.coiled |
| off_52w_high_pct | −30.1% | LIVE; `off_high −30.1` |
| ret_5d | +6.4% | LIVE |
| ret_20d | +7.6% | LIVE |
| ret_60d | −3.0% | LIVE |
| ret_120d | −4.4% | LIVE |
| sector | Healthcare (board label); Shenwan≈"Pharma & Biotech" | standouts.sector; sector_central |
| sector_state | Pharma & Biotech = Trough/"Bottoming" (pos 3.3), "Recovering", conviction 53 Neutral, confluence 1/3; market Risk-off −0.94 | sector_central_china_data.js |
| strongest_theme | THS "Synthetic Biology" (合成生物, 8 members) | baskets_ths.json |
| theme_rel20 | +18.9% (20d rel; ret +16.6%) | baskets_ths.json perf |
| earliest_flagging_signal | washout_2w/COILED via fresh-cross gate, first T2 on 2026-06-24 @35.45 | gate() day-walk §3 |
| days_of_run_captured | ~8 cal days / +3.8% = 21% of the +17.7% low→spot move (missed 76% before flag) | price walk §3 |

---

## Open questions / limits
- **T3/T4 projection first-flag** not separately replayed; I ran daily `gate()` (which layers cascade) and
  saw no projected-cross earlier than the 06-24 T2. A dedicated `confluence_tiers.cascade(..., project)` replay
  would confirm whether a T4 fired pre-06-24. Stated as a limit, not a claim of absence.
- **`ext_since_cross_pct`** interpreted as "% price move since the first fresh cross" (06-24). If the orchestrator
  means "% above the cross bar on the signal's own TF", recompute — flagged so the three exemplars use one definition.
- **Fallback:** per-stock `chinastockdata/300725.SZ.json` absent in worktree; only the STALE (2026-06-26) main-checkout
  copy exists. All state above is from the FRESH worktree `factordata/china_standouts.json` (2026-07-02) + LIVE re-runs.
- **Is it actually "GREAT"?** The board caught a real washed-out→recovering ChiNext biotech in a strongly-performing
  THS theme (+18.9% 20d-rel) at a bottoming Shenwan sector — a coherent thesis. But it entered LATE (21% of the
  bounce), its own d63 expectancy is −0.40, trust_tier is "reversal / not a buy list", and the ranking (#3) is
  driven by washout+coiled+T1 bonuses that the visible card's score (43/"Hold") actively contradicts. Whether
  "great" reflects edge or a favorable single-name draw is not answerable from one exemplar.
