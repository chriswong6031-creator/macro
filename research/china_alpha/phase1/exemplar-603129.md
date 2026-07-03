# Exemplar forensics — 603129 (Zhejiang CFMOTO Power / 春风动力)

**Auditor pass:** phase-1 exemplar reverse-engineering. **Date:** 2026-07-03.
**Ticker form:** `603129.SS` (Shanghai main board, 60xxxx → `.SS`). Confirmed as the exact
column key in `data/china_search/closes.parquet` (command output below) and as the `data-sym`
in the render.

> **Data-provenance flags (read first):**
> - The board artifact `site/factordata/china_standouts.json` and `closes.parquet` are present
>   **in this worktree** — the board forensics below are on worktree data, not fallback.
> - The per-stock detail JSON `site/chinastockdata/603129.SS.json` does **NOT** exist in the
>   worktree (`site/chinastockdata/` is absent here). I read the **main-checkout fallback** at
>   `/Users/chriswong/Documents/Cluade/Macro Dashboard/site/chinastockdata/603129.SS.json`.
>   That file is **stale** — `asof: 2026-06-26`, spot 244.0 — vs the board's `as_of 2026-07-02`.
>   Every number I quote from it is tagged **[per-stock JSON · stale 06-26]**. The authoritative,
>   current system state is the board record inside `china_standouts.json` (`data_through 2026-07-02`).

---

## 0. TL;DR

603129 sits at **board rank #2 of 110** in the "⚡ Standout individual stocks" grid on
`site/china_stocks.html`. It is a genuine **washed-out → based → running** name (swing low
220.49 on 06-11, +13.2% over 20d, +8.9% over the last 5 sessions into 259.50). But it earns
rank #2 almost entirely from **stacked ranking bonuses** (2W-washout +0.50 and COILED +0.25),
not from its middling base setup score (0.61) and not from the validated A-share reversal edge
(its `rev_z` is **−0.66**, i.e. it is on the *strong* side of its sector, the opposite of a
reversal candidate). The board's own displayed conviction score is **26/100 ("Watch")** and its
entry gauge reads **HOLD — don't add here** — both correct reads that "already run" names should
show. The card is therefore internally contradictory by design: high rank, low score, HOLD.

Two structural facts dominate this exemplar:
1. **It was caught on the last day it was eligible.** Running the gate live, 603129 is T1-eligible
   only *through 2026-07-01* (ticks=2); by 2026-07-02 it rolls off ("held but topped/rolled-over —
   no longer a fresh entry", ticks=3). The board froze the 07-01 signal onto an `as_of 07-02` page.
2. **The whole board is under a QVIX *panic* regime** ("halt new chases, even oversold names keep
   falling") and a CN drawdown radar at *caution* (sleeve ×0.90). 603129 is surfaced as a top pick
   into a market the board itself is telling you to stand down in.

---

## 1. LOCATE

### 1.1 closes.parquet column
```
$ PYTHONPATH=$PWD python3 -c "... pd.read_parquet('data/china_search/closes.parquet') ..."
matching cols: ['603129.SS']
index name: Date shape: (1224, 1506)
```
Series: n=1224, 2021-06-15 → **2026-07-02**, last close **259.50**.

### 1.2 Per-stock JSON
`site/chinastockdata/603129.SS.json` — **only in main checkout** (fallback). Top-level keys:
`alpha, anticipation, asof, consensus, conviction, cycle, early, earnings, entry_signal,
fundamentals, history_days, ladder, mtf, name, positioning, risk_sizing, season_*, sector,
tech, ticker, tv, val_pctile, view, vol_squeeze`. **`asof: 2026-06-26`** (stale).

### 1.3 Board artifact
Builder `scripts/build_china_library.py` writes the standout board to
`site/factordata/china_standouts.json` (L1348) — enriched from `china_setups.json` (L1269).
Both use `rank_by: "confluence"`. 603129 is at **`buy` index 1 → rank #2** (command output §2).
`as_of: 2026-07-02`, `data_through: 2026-07-02`.

### 1.4 Rendered card
`site/china_stocks.html`, card at **line 1305** (`<a class="nbcard nb-up" href="china_lookup.html#603129.SS">`).
Counting `nbcard` anchors, exactly **1 card precedes it (600267.SS) → it is card #2**, inside the
`#standouts` panel titled "⚡ Standout individual stocks" (html L40).

**Every rendered label / chip / color on the 603129 card (html L1305–1394):**
| Element | Rendered value | class / color |
|---|---|---|
| Card border | green (up) | `nbcard nb-up` |
| Ticker / name | 603129.SS · Zhejiang Cfmoto Power / 春风动力 | — |
| Signal gate chip | **✓ BUY · T1·1.0** ("deep-oversold cross", date 2026-07-01) | `sig-gate sig-take` |
| Price | 259.50 | `nb-px` |
| Sector | Consumer Cyclical / 可选消费 | `nb-sub` |
| Washout chip | **🌊 2W washout** | `nb-washout` |
| Coiled chip | **⚡ Coiled** | `nb-coiled` |
| Quality chip | **Q ~** (ROE 24.49 · PE 23.6 · Piotroski 3/9 · z 0.31) | `nb-q nb-q-avg` |
| Off-high | **−11.2% off 52w high** | `nb-offh` |
| Conviction score | **26** · "ready" | `nb-cscore band-neutral` |
| Verdict | **Uptrend — hold, add on dips** | `nb-verdict` |
| Entry block | **Hold — don't add here**; buy zone 235.80–243.60 (−7.6%); cycle day 14/23–44 | `nb-entry nbe-hold`, dot `a1` |
| Axes | SEL 46 · ENT 54 · TWD no-data · QUAL no-data | `nb-axes` |
| State | **UPTREND** | `nb-state` |
| Size | **⚖ 0.81×** (vol 27.2%, inv-vol ×0.81, regime ×1.0) | `nb-size sz-dn` |
| Alpha | **α +0.74** · rank **#26/115** | `nb-az az-up` |

Note the card renders **no extended/💥 chip** (unlike the #1 card 600267, which carries a
`vf-exp "Already moving"` chip) — 603129's `extension.extended = false` (score 0.028), so it is
not flagged as extended even though it just ran +8.9% in 5 days.

---

## 2. SYSTEM STATE (authoritative = board record, `china_standouts.json`, `data_through 2026-07-02`)

```
$ ... find 603129 in china_standouts.json['buy'] ...
=== FOUND 603129 at buy index 1 (rank 2) ===
```

| Field | Value | Source |
|---|---|---|
| board rank | **#2 / 110** | `buy` index 1 |
| rank_by | confluence | `china_standouts.json.rank_by` |
| conviction.score (displayed) | **26** | `conviction.score` |
| conviction.band | **neutral / "Watch"** | `conviction.band`, `band_en` |
| conviction.potential.score | 26 (tier "watch") | `conviction.potential` |
| potential components | fuel **0.192**, trigger 0.63, survive 0.88, tailwind 1.0, confidence 0.9, edge 1.0 | `conviction.potential.components` |
| potential reasoning | "stressed tape — size down" | `conviction.potential.reasoning` |
| **rank_pctile** | **70** | `conviction.rank_pctile` (the overwritten within-board percentile) |
| verdict | "Uptrend — hold, add on dips" | `conviction.verdict` |
| composite_z | −0.08 | `conviction.composite_z` |
| validation_status | neutral_ic | `conviction.validation_status` |
| trust_tier | reversal ("validated but high-variance, not a buy list") | `conviction.trust_tier` |
| **ladder.state** | RALLY ON → label **UPTREND**, dir **up** | board `state`/`label`/`dir` |
| entry_signal.status | **hold** (act_level 1) | `entry_signal.status` |
| entry buy_zone | 235.8–243.6 (−7.6% from spot) | `entry_signal.buy_zone` |
| entry stop / chase_above | 220.5 / 259.5 | `entry_signal` |
| entry cycle_pos | dc_day 14, band [23,44], 32% through, phase "mid" | `entry_signal.cycle_pos` |
| risk_sizing | vol_ann 27.2%, inv_vol ×0.81, regime ×1.0, **size_mult 0.81** | `risk_sizing` |
| **cascade tier** | **T1**, weight **1.0**, sub "deep" | `signal.tier_cascade`/`weight`/`tier_sub` |
| **ticks since cross** | **2**, fresh_bars 4, bars_to_cross null, provisional false | `signal.ticks`/`fresh_bars` |
| signal.asof | **2026-07-01** (one session behind board as_of) | `signal.asof` |
| **washout_2w** | **true** | board `washout_2w` |
| **coiled** | coiled=**true**, star false, washout_ctx true, cohort **0.726**, div false, **bonus 0.25** | `coiled` |
| extension | extended=**false**, score 0.028, "+2.0σ vs 20d MA", turn_ratio 1.284 | `extension` |
| rev_z | **−0.66** | `conviction.axes.selection.basis[rev_z].z` and `china_reversal.json.rev_z_all['603129.SS']` |
| alpha (z) | **+0.74** ("intact"), sector_rank **#26/115** | `alpha`/`sector_rank`/`sector_n` |
| quality | ROE 24.49, PE 23.6, Piotroski 3, z 0.31, band "avg" (DISPLAY only) | `quality` |
| consensus | 18 reports, 18 buy, fwd PE 16.5 | **[per-stock JSON · stale 06-26]** |
| sector | Consumer Cyclical (Yahoo taxonomy) | board `sector` |

### 2.1 LIVE cascade + gate (independent recompute on `closes.parquet['603129.SS']`)
This is the single most important finding of the exemplar. The board's tier is **frozen at the
07-01 data**; recomputing live shows the name **rolling off eligibility a day later**:

```
through 2026-07-02: gate.eligible=False tier=None  wt=0.0 ticks=3 | cascade.tier=None ticks=2
                    reason="held but topped/rolled-over — no longer a fresh entry"
through 2026-07-01: gate.eligible=True  tier=T1    wt=1.0 ticks=2 | reason="buy fired; forward confirmation pending"
through 2026-06-30: gate.eligible=True  tier=T2    wt=0.8 ticks=2
through 2026-06-29: gate.eligible=True  tier=T2    wt=0.8 ticks=2
through 2026-06-26: gate.eligible=True  tier=T2    wt=0.8 ticks=1
```
`engine.confluence_tiers.FRESH_TICKS = 2`. At 07-02 ticks=3 > 2 → no longer "just-crossed" →
weight 0, sinks. **The board caught 603129 on the last eligible bar.** The `china_standouts.json`
`as_of 2026-07-02` therefore ships a signal that is already stale by the time the page dates itself.

### 2.2 Theme / basket / sector memberships
- **THS concept baskets:** 603129 is in **zero** THS concepts — bare substring `603129` is
  **absent** from `data/baskets_china_ths/concept_map.json` and from the columns of
  `data/basket_levels/china_ths.parquet` (only AI / CPO / storage-chip baskets exist there).
- **baskets_china.html / sector_central_china.html:** `grep 603129` → **no hits** on either page.
  603129 does not appear on the basket page or the sector-central page at all.
- **sector_central / sector_cycles "what they say about its sector":** *Not directly answerable* —
  those pages use the Shenwan L1 taxonomy (Chinese sector names), while the board tags 603129 as
  Yahoo-style "Consumer Cyclical"; there is no shared key to join them, and the name is not rendered
  on either page. The only sector context the system actually holds for this name is the **board's
  own**: `alpha +0.74`, `sector_rank #26/115` within "Consumer Cyclical" (mid-pack on residual RS).
- **theme_rel20:** **no strongest-theme / 20d-rel exists** for this name (no basket membership).

**Net: 603129 carries NO thematic tailwind and NO reversal edge.** Its entire board case is the
cascade tier + washout + coiled bonuses.

---

## 3. PRICE FORENSICS

```
ret 5d: +8.91% | 20d: +13.23% | 60d: +9.20% | 120d: −5.94%
52w high: 292.08 | off 52w high: −11.15%   (board reports −11.2% ✓)
```
Recent path (`closes.parquet`):
```
06-11 220.49  <- swing low (also the ladder stop level)
06-16 228.24    ... chop / basing 221–244 ...
06-24 241.35  <- first WEIGHTED gate eligibility (T2)
06-26 244.00
06-29 252.76  <- first this-run washout_2w=True
06-30 255.80
07-01 255.70  <- T1 (shipped board signal)
07-02 259.50  <- rolled off eligibility (ticks=3)
```

**Path shape: washed-out → based → running.** Down from a 292 high to a 220.49 swing low
(−24.5% peak-to-trough over ~1-2 months), a ~2-week base 221–244, then a clean 6-session run
244 → 259.5 (+6.4%). It is *not* a straight-momentum name (120d return is negative) and *not* a
post-catalyst gap (no single-bar jump; the ATR is only ~1.95%). This is exactly the kind of setup
the board is designed to catch — the issue is timing, not shape.

### 3.1 First-flag timeline per signal (walk-forward on the live series)

| Signal | First flagged (this run) | Close then | Notes |
|---|---|---|---|
| COILED (`coiled.washout_ctx`) | **2026-06-18** | 221.02 | earliest — fires near the base low |
| Weighted gate / cascade **T2** | **2026-06-24** | 241.35 | first *rankable* eligibility (fresh MACD-trough) |
| 2D MACD-hist up-cross (approx) | ~2026-06-23 | 241.4 | my recompute, not the engine's exact detector |
| 3D MACD-hist up-cross (approx) | ~2026-06-28 | 255.8 | my recompute |
| **washout_2w** (2W StochRSI reclaim) | **2026-06-29** | 252.76 | *late* — fires after +14% off the low |
| Cascade **T1** upgrade | 2026-07-01 | 255.70 | shipped board state |
| rev_z contribution | never (rev_z = **−0.66**, a *headwind* not a flag) | — | validated A-share edge does NOT select this name |

**Earliest flagging signal: COILED, 2026-06-18 @ 221.02** — essentially at the base low.
**Earliest *rankable* (weighted) signal: T2 cascade, 2026-06-24 @ 241.35.**

### 3.2 Run captured vs missed
Measuring from the swing low (220.49 on 06-11) to the last board close (259.50 on 07-02) = the
+17.7% total move.
- If credited from **COILED first-flag** (06-18 @ 221.02): captured **~06-18 → 07-02 ≈ +17.4%** of
  the run — nearly the whole thing (COILED fired 1 bar into the base).
- If credited from **first rankable board signal** (T2, 06-24 @ 241.35): captured
  **241.35 → 259.50 = +7.5%**, i.e. it **missed the first ~9.5%** off the low (220.49→241.35) and
  caught the back ~7.5%.
- The **washout_2w bonus** (+0.5 on the rank blend, the single biggest lift) did not turn on until
  06-29 @ 252.76 — after +14.6% of the move was already gone.

So the board's *most weighted* evidence (washout) is the *latest* to fire. The name ranks highest
right as the easy part of the run is over — consistent with the low potential-fuel (0.192) and the
HOLD entry gauge.

---

## 4. UI CONTRADICTIONS (each traced to engine source)

The card is a study in a high rank contradicted by every conviction/entry read on it:

1. **Rank #2 but displayed score 26 ("Watch").**
   - Rank is `signal_gate.blend_sorted` output (§5), driven by cascade tier + washout/coiled
     bonuses — `scripts/build_china_library.py:1225-1230`.
   - Displayed score is `conviction.potential.score` (buy-readiness), which **overwrites** the
     panel percentile at `build_china_library.py:1036-1043` (`_c["score"] = _pot["score"]`).
     potential=26 because **fuel=0.192** (already run → little upside from here). The two numbers
     answer different questions; the card shows both without reconciling them.

2. **Rank #2 but `rank_pctile` 70 (not 90+).** The within-board percentile score (the *old*
   displayed score) is preserved as `rank_pctile` at `build_china_library.py:1041`
   (`_c["rank_pctile"] = _c.get("score")`). 70th pctile on conviction, yet rank 2 — because the
   +0.75 bonus stack (§5) lifts it far above its conviction percentile.

3. **"BUY · T1·1.0" gate chip but entry gauge says "HOLD — don't add here."**
   - Gate chip = `signal.tier_cascade`/`weight` = T1/1.0 (`build_china_library.py:1260,1279`,
     `signal_gate.compact`). It answers "did a master confluence fire?" → yes (07-01).
   - Entry gauge = `entry_signal.status = "hold"`, headline "Hold — don't add here"
     (`entry_signal`, rendered html L1325 `nbe-hold`). It answers "buy *at this price* now?" → no,
     spot is +7.6% above the buy zone (235.8–243.6). Both correct; jointly confusing.

4. **Verdict "Uptrend — hold, add on dips" while trust_tier says "not a buy list."**
   `conviction.trust_tier.tier = "reversal"` ("validated but high-variance, **not a buy list**")
   sits under a verdict that reads like a hold-and-add recommendation.

5. **α +0.74 / rank #26/115 (mid-pack) presented as a positive green chip** (`nb-az az-up`,
   html L1382) while the tooltip itself says alpha is "**not the ranking driver** (A-share momentum
   is not validated)." A green +0.74 chip on a name whose momentum factor is explicitly disclaimed.

6. **No "extended" chip despite a +8.9%/5-day run.** `extension.extended = false` (score 0.028,
   `build_china_library.py:1222` reads `extension.score`; EXT_PENALTY only bites on the score, and
   0.028 is tiny). So the anti-chase visual (the 💥 chip the #1 card carries) never renders here,
   even though potential-fuel (0.192) and the HOLD gauge both say it *has* run. The extension read
   and the fuel read disagree about whether the name is "already moving."

7. **Cross-artifact contradiction (provenance).** The per-stock detail JSON (feeding
   `china_lookup.html`) still shows **score 77 / band "constructive" / "Upper rank"** and verdict
   **"Neutral — no clear edge"** **[stale 06-26]**, contradicting the board's 26 / "Watch" /
   "Uptrend — hold". A user clicking through from the card to the lookup page sees a *different,
   higher* conviction number for the same name, because the two artifacts were built on different
   dates. (Source: `site/chinastockdata/603129.SS.json.conviction.score = 77` vs
   `china_standouts.json ... conviction.score = 26`.)

---

## 5. WHY IT RANKS #2 — the mechanism, reproduced exactly

Ranking = `signal_gate.blend_sorted(..., base_of=setup, bonus_of=_cn_bonus, tier_frac=0.30,
wn_floor=0.60)` (`build_china_library.py:1225-1230`, `EXT_PENALTY=0.5`/`WASHOUT_BONUS=0.5` at
L1184-1185, `_cn_bonus` at L1215-1223). Per-row score
(`engine/signal_gate.py:254-262`):

```
score = tier_frac·wn + (1−tier_frac)·pct + bonus
      = 0.30·wn + 0.70·pct + bonus
bonus = 0.5·washout_2w + coiled.bonus − 0.5·extension.score
```

I recomputed this on the shipped `buy` rows and it **reproduces the exact shipped order**:

```
rank | blend | ticker    | setup | tier | wt  | bonus
  1  | 1.737 | 600267.SS | 1.53  | T1   | 1.0 | +0.744
  2  | 1.647 | 603129.SS | 0.61  | T1   | 1.0 | +0.736   <== 603129 (matches shipped buy index 1)
  3  | 1.613 | 300725.SZ | 0.50  | T1   | 1.0 | +0.747
  4  | 1.386 | 002555.SZ | 1.53  | T1   | 1.0 | +0.393   <- higher setup, no washout+coiled → ranks BELOW 603129
```

**603129's bonus = +0.736** = washout 0.50 + coiled 0.25 − 0.5·0.028 (ext). Decisive proof the
bonus stack, not merit, drives the rank: **002555 has setup 1.53 (2.5× higher) and the same T1
tier, yet ranks #4 below 603129 (#2)** purely because it lacks the washout+coiled bonuses.
603129's own setup (0.61) is middling; the +0.736 lift ≈ **2.5 tier-fracs**, i.e. it lifts the
name by ~2 full tiers.

**Verdict on the "GREAT pick" designation:** the pick is *shape-correct* (real washout→base→run)
and the cascade did fire a real fresh master cross. But (a) the ranking magnitude is a
bonus-stack artifact, not conviction; (b) the two validated edges the page advertises —
**reversal (rev_z −0.66) and thematic tailwind (none)** — are both absent/negative here; (c) the
name was surfaced on its *last eligible bar* and is already rolling off; and (d) it is surfaced
into a QVIX-panic / drawdown-caution tape the board itself says to stand down in. If this counts
as a "great pick," it is great *despite* the two features the board claims are its edge, and its
alpha (if any) came from the +9.5% off the low that the board **missed** before it flagged.

---

## 6. FEATURE VECTOR (orchestrator diff keys)

| key | value | source |
|---|---|---|
| on_board_rank | **2** (of 110) | `china_standouts.json` buy idx 1; html card #2 (L1305) |
| ui_label | **UPTREND** (state RALLY ON) | board `label`/`state`; html L1376 |
| ui_score | **26** (band neutral / "Watch") | `conviction.score`; html L1317 |
| ui_chips | ✓BUY T1·1.0 · 🌊 2W washout · ⚡ Coiled · Q~ · HOLD(don't add) · α +0.74 · ⚖0.81× · −11.2% off-high | html L1309–1382 |
| tier | **T1** (weight 1.0, sub "deep") | `signal.tier_cascade` |
| ticks_since_cross | **2** (rolls to 3 → ineligible at 07-02 live) | `signal.ticks`; live gate recompute |
| ext_since_cross_pct | extension.score **0.028** ("+2.0σ vs 20d MA"); extended=**false** | `extension` |
| rev_z | **−0.66** (headwind, not a flag) | `china_reversal.json.rev_z_all`; `axes.selection.basis` |
| washout_2w | **true** (first this-run 2026-06-29) | board `washout_2w`; walk-forward |
| coiled | **true** (bonus 0.25, cohort 0.726, washout_ctx; first 2026-06-18) | `coiled`; walk-forward |
| off_52w_high_pct | **−11.2%** | board `off_high`; recompute −11.15% |
| ret_5d | **+8.91%** | closes.parquet recompute |
| ret_20d | **+13.23%** | closes.parquet recompute |
| ret_60d | **+9.20%** | closes.parquet recompute |
| ret_120d | **−5.94%** | closes.parquet recompute |
| sector | **Consumer Cyclical** (Yahoo taxonomy) | board `sector` |
| sector_state | *no page state* — not on sector_central/sector_cycles; board context = sector_rank #26/115, α +0.74 | grep (no hits); board `sector_rank` |
| strongest_theme | **none** (0 THS concepts; not on baskets_china) | concept_map / basket_levels (no 603129) |
| theme_rel20 | **n/a** (no basket membership) | — |
| earliest_flagging_signal | **COILED @ 2026-06-18 (221.02)**; earliest *rankable* = T2 cascade @ 2026-06-24 (241.35) | walk-forward gate/coiled |
| days_of_run_captured | from COILED-flag ≈ +17.4% (whole run); from first rankable T2-flag = **+7.5%** (missed the first ~9.5% off the 220.49 low) | closes.parquet recompute |

---

## 7. Commands run (for reproduction)
- `pd.read_parquet('data/china_search/closes.parquet')['603129.SS']` — series, returns, drawdown, path.
- `engine.signal_gate.gate('603129.SS', s[s.index<=cut])` and `engine.confluence_tiers.cascade(...)`
  across cutoffs 06-26 … 07-02 — the freshness-cliff / tier timeline.
- `engine.cycles._tf_state(s.resample('2W-FRI').last())` — washout_2w walk-forward.
- `engine.coiled.washout_ctx(s[...])` — coiled walk-forward.
- Blend reproduction: reimplemented `signal_gate.blend_sorted` `_score` on the shipped `buy` rows
  → exact shipped order (§5).
- `china_reversal.json.rev_z_all['603129.SS'] = -0.66`.
- greps: `603129` in `china_stocks.html` (3 hits, L1305/1307/1310), `baskets_china.html` (0),
  `sector_central_china.html` (0), `concept_map.json` (0), `china_ths.parquet` columns (0).

## 8. Open questions
- **Board freshness contract:** is `as_of 2026-07-02` with a `signal.asof 2026-07-01` intended
  (board deliberately trails the signal by a session), or a staleness bug? It causes the board to
  show T1-eligible for a name that is no longer eligible on same-day data.
- **Per-stock JSON staleness:** why is `chinastockdata/603129.SS.json` at `asof 06-26` (score 77)
  when the board is 07-02 (score 26)? Is the per-stock library on a slower cadence than the board,
  and does `china_lookup.html` therefore routinely show a different conviction than the card that
  links to it? (Only checkable against the render cadence / CI logs — not resolvable from artifacts.)
- **rev_z sign:** the page's stated edge is A-share *reversal* (beaten-down names), yet the #2 pick
  has rev_z −0.66 (a leader, not a laggard). Is surfacing non-reversal names via the cascade+bonus
  path a deliberate broadening, or does it dilute the one validated edge? (Cross-exemplar question.)
- **washout timing:** the +0.5 washout bonus (largest single lift) fires *latest* of all signals
  (after +14% of the move). Is a bonus that turns on post-run doing selection work or just
  post-hoc labeling? Needs the forward ledger (`board_track`, n_rows 182) to grade.
