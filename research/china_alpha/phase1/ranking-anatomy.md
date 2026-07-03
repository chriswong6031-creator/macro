# China Stocks Board — Ranking + UI Contradiction Anatomy

**Scope:** `china_stocks.html` standout board (the per-stock card strip).
**Date:** 2026-07-03. **Data as_of on live board:** 2026-07-02.
**Worktree:** `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/lucid-knuth-523979`

**Bottom line (verified this session):** The board's ROW ORDER and the board's DISPLAYED
gauges (score, band, verdict, dir, entry status, label) are governed by **different quantities**
that are never reconciled. Rank is `setup × cascade-tier + washout/coiled bonus − extension
penalty`. The big number on the card is the **potential/buy-readiness score**, which *overwrites*
the rank-percentile at `build_china_library.py:1042` and is **not a rank input**. Measured
`Spearman(board_rank, displayed_score) = −0.189` (n=110) — effectively decoupled. On the live
board **85 of 110 rows are band=low, 78 are dir=caution, 77 read entry="extended"**, yet all sit
in the buy list because the cascade tier put them there. This is the mechanism behind the owner's
complaint.

> **DATA-SOURCE CAVEAT (flag):** `site/chinastockdata/` (the per-stock JSONs) does **not exist in
> this worktree** — it is R2-gated (`ls site/chinastockdata/` → "No such file or directory"). All
> per-stock reads (688306, conviction provenance) use the **main-checkout fallback**
> `/Users/chriswong/Documents/Cluade/Macro Dashboard/site/chinastockdata/`, which is dated
> 2026-06-28 and is **4 days staler** than the worktree board JSONs (2026-07-03 04:45). The board
> JSONs themselves (`site/factordata/china_setups.json`, `china_standouts.json`) DO exist fresh in
> the worktree and are the primary evidence below.

---

## 1. THE EXACT ORDER — rank formula as pseudocode

### 1.1 Call chain
1. `build_china_library.py` main() scores the candidate universe, builds `sig_verdict[ticker]`
   (the confluence-gate verdict from `signal_gate.gate`) for every name.
2. Eligible rows (`sig_verdict[t].eligible == True`) are ordered by
   **`signal_gate.blend_sorted(...)`** at `build_china_library.py:1225-1230`.
3. `blend_sorted` returns the list; it is then passed through `_diversify` (a per-sector cap
   reorder, `build_china_library.py:1240-1251`), truncated to `[:110]`, and written to
   `china_setups.json` (`:1267-1270`) and `china_standouts.json` (`wide`, `:1274`).
4. `scripts/build_china.py:801-802` calls `compute_china_standouts(setups, ...)`, which enriches
   each row **in place and DELIBERATELY DOES NOT RE-SORT**
   (`build_china_library.py:546-549`: *"we deliberately do NOT entry-open-first re-sort here"*).
5. Template iterates `setups.buy` in list order (`templates/china.html.j2:1222`
   `{% for n in setups.buy %}`). **List order == blend_sorted order == the final rank.**

### 1.2 The `_cn_bonus` closure (`build_china_library.py:1215-1223`)
```
WASHOUT_BONUS = 0.5     # :1184  — 2W StochRSI washout-reclaim lift (~one tier)
EXT_PENALTY   = 0.5     # :1185  — anti-chase extension demote (~one tier)
COILED_BONUS  = 0.25    # engine/coiled.py:43  — cohort-washout confirmed
STAR_EXTRA    = 0.15    # engine/coiled.py:44  — extra for STAR (coiled ∩ bull_div)
# (coiled+star max additive = 0.40; FIRE adds NO rank change — display only, :1202-1210)

def _cn_bonus(r):
    b  = 0.5  if r.washout_2w else 0.0                    # WASHOUT_BONUS
    b += coiled_by[r.ticker].bonus or 0.0                 # 0.0 | 0.25 | 0.40
    ext = float(r.extension.score or 0.0)                 # 0.0 .. 1.0 continuous
    return b - 0.5 * ext                                  # net additive lift on the 0..1 blend
```

### 1.3 The blend score inside `blend_sorted` (`signal_gate.py:254-262`)
```
tf = 0.30                                   # CN_TIER_FRAC  (build_china_library.py:1190)
wf = 0.60                                   # CN_WN_FLOOR   (build_china_library.py:1190)
base_of(r) = r.setup or 0.0                 # build_china_library.py:1228
w = sig_verdict[r].weight                   # cascade weight: T1=1.0 T2=0.8 T3=0.6 T4=0.4
                                            #   (engine/confluence_tiers WEIGHTS)

def _score(r):
    b  = _cn_bonus(r)                                       # from 1.2 above
    w  = verdict.weight or 0.0
    if not w:  return -1.0 + b                              # ineligible/weightless sinks
    wn = clamp((w - 0.4) / 0.6, 0, 1)                       # T1->1.0 T2->0.667 T3->0.333 T4->0.0
    wn = 0.60 + 0.40 * wn                                   # CN flatten -> T1=1.0 T2=0.867 T3=0.733 T4=0.60
    pct = bisect_right(sorted_setups, r.setup) / n          # setup PERCENTILE in pool (0..1)
    return 0.30 * wn + 0.70 * pct + b                       # convex blend + additive bonus/penalty
# sorted(items, key=_score, reverse=True)  -> highest _score first
```

**Every term, with magnitude and range:**

| Term | Source | Range on the 0..1 scale | Notes |
|------|--------|-------------------------|-------|
| `0.30 · wn` (cascade tier) | `signal_gate.py:262`, tf=0.30 | T1=0.300, T2=0.260, T3=0.220, T4=0.180 | flatten floor 0.60 compresses T1↔T4 gap to just **0.12** |
| `0.70 · pct` (setup percentile) | `signal_gate.py:262`, 1−tf=0.70 | 0.000 .. 0.700 | **dominant term**; `setup` is the reversal/alpha base, NOT the displayed score |
| `+0.50` washout_2w | `_cn_bonus`, :1184 | 0 or +0.50 | ~1.6 tiers of lift; own-name 2W StochRSI reclaim |
| `+0.25 / +0.40` coiled/star | `coiled.py:43-44` | 0, +0.25, or +0.40 | cohort washout; STAR = ∩ bull_div |
| `−0.50 · ext.score` extension | `_cn_bonus`, :1223 | 0 .. −0.50 | continuous; **only 2 of 110 live rows have ext.extended=true** |

**Net rank score range ≈ −0.5 (heavily extended, weakest setup, no bonus) to ~+1.9 (T1 + top
setup pct + washout + star).** The tier term's total swing (0.12) is dwarfed by the setup
percentile (0.70) and by a single washout bonus (0.50).

**KEY DECOUPLING FACTS:**
- `base_of = r.setup` (reversal/alpha composite), **not** `conviction.score`.
- The displayed `conviction.score` is the **potential/buy-readiness** score, written over the
  rank-percentile at `build_china_library.py:1041-1043`:
  `_c["rank_pctile"] = _c.get("score"); _c["score"] = _pot["score"]`. Rank never reads `_pot`.
- Measured on the live board: `Spearman(rank, displayed_score) = −0.189` (p=0.048, n=110) — the
  score users see explains **~4%** of rank variance. `Spearman(rank, setup) = −0.619` — the hidden
  `setup` base is 3× stronger. (`scipy.stats.spearmanr` on `china_standouts.json`, this session.)

---

## 2. RENDER PATH — every visible element → engine source field

### 2.1 There is no `templates/china_stocks.html.j2`
`china_stocks.html` is produced by rendering **`templates/china.html.j2` with `mode="stocks"`**:
`scripts/build_china.py:859-860`:
```
html_st = tmpl.render(**vm, mode="stocks")
(site / "china_stocks.html").write_text(html_st)
```
`vm["setups"]` is the enriched `compute_china_standouts(...)` output (`build_china.py:802`); on
empty it falls back to persisted `china_standouts.json` (`build_china.py:821-825`). The card block
is `templates/china.html.j2:1197-1317` (`#standouts` panel).

### 2.2 Per-card element → source-field map (template line → row field)

| Card element | Template | Row field / engine source |
|---|---|---|
| Ticker | `:1226` `nb-tk` | `n.ticker` |
| Name | `:1227` `nb-nm` | `n.name` |
| **Signal badge (T1..T4 tier)** | `:1228` `_sig_badge.html.j2` (`n.signal`) | `signal_gate.compact(sig_verdict[t])` → `tier_cascade` (`build_china_library.py:1260`) |
| Price | `:1229` `nb-px` | `n.price` (per-stock JSON `tech.price`) |
| Sector | `:1231` | `n.sector` |
| **🌊 2W washout chip** | `:1231` `nb-washout` | `n.washout_2w` — **a rank bonus term** (+0.5) surfaced as a chip |
| **⚡ Coiled / ★STAR / FIRE chip** | `:1231` `nb-coiled` | `n.coiled.{coiled,star,fire}` — coiled/star **are rank terms** (+0.25/+0.40); FIRE is display-only |
| **⚠ extended chip** | `:1231` `nb-ext` | `n.extension.extended` — the anti-chase `−0.5·score` term; **fires on only 2 live rows** |
| Q quality chip | `:1231` `nb-q` | `n.quality.band` — display-only, explicitly "never in the ranking" |
| off-52w-high | `:1231` `nb-offh` | `n.off_high` |
| **Sparkline color** | `:1232` `spark_svg` | colored by `n.dir` (up→--up, down→--down, else --muted), `build_china_library.py:543-544` / `:1016-1018` |
| **Score (big number)** | `:1236` `nb-cscore` | `n.conviction.score` = **potential_score** (`build_china_library.py:1042`) — NOT a rank input |
| **Band color of score** | `:1236` `band-{{c.band}}` | `n.conviction.band` = potential band (`:1043`); CSS bands high/constructive/neutral/low at `:198-203` |
| **Verdict text** | `:1237` `nb-verdict` | `n.conviction.verdict` (e.g. "Countertrend bounce — not…", "Uptrend — hold, add on dip") |
| Alignment line (🟢/🟡) | `:1240-1249` `nb-align` | `n.conviction.alignment` gated on `n.align_tier in [aligned,near]` (`build_china_library.py:1259`) |
| **Entry gauge (buy_now/wait_pullback/extended/hold/topping)** | `:1256` `nbe-{{es.status}}` | `n.entry_signal.status` — **gauge 2, independent of rank**; CSS warn border for hold/extended/topping at `:170-171` |
| Buy-zone price | `:1261-1266` | `n.entry_signal.buy_zone` |
| Cycle-day bar | `:1268-1273` | `n.entry_signal.cycle_pos` |
| 4 axes (SEL/ENT/TWD/QUAL) | `:1279-1287` | `n.conviction.axes[*].pct` |
| **Headline label (state)** | `:1290` `nb-state` `td(n.label or n.state)` | `n.label` = cycle **ladder.state** ("BOTTOMING"/"UPTREND"/"UNCONFIRMED TURN") — independent cycle gauge |
| 🛡🔄 confluence chip | `:1291` | `n.confluence` = in reversal-watch ∩ low-vol sleeve |
| **⚖ size chip (×mult)** | `:1292` `nb-size` | `n.risk_sizing.size_mult` — inverse-vol; independent of rank |
| α / sector-rank / entry tag | `:1294-1301` | `n.alpha`, `n.sector_rank`, `n.alpha_entry` |
| vol-squeeze / margin-crowd chips | `:1304-1310` | `n.conviction.vol_squeeze.state`, `n.conviction.risk.components.fragility` |
| cautions / notes | `:1311-1312` | `n.conviction.cautions`, `n.conviction.notes` |

**Card container class `nb-{{ n.dir }}`** (`:1224`) — the whole card's accent is driven by
`n.dir` (up/caution/down), an independent cycle-direction read, again not the rank.

---

## 3. CONTRADICTION MATRIX

### 3.1 Rank vs each loud element — can they disagree, and why

| Element | Independent of rank? | Disagreement mechanism |
|---|---|---|
| **Displayed score** (`conviction.score`) | YES | Rank = `setup×tier + bonuses`; score = `potential_score` (overwritten at :1042). Different formulas. rho=−0.189. |
| **Band color** (`conviction.band`) | YES | Band is the potential band; a `low` band name ranks high whenever its `setup` percentile + T1 tier + bonuses win. |
| **Verdict text** | YES | Verdict is capped by cycle state (a downtrend reads "Countertrend bounce — not confirmed") but rank ignores cycle state — only the confluence tier + setup matter. |
| **Entry status** ("extended"/"hold") | YES | `entry_signal.status` is gauge-2 (cycle/vol timing). Rank's own extension term is `n.extension` (a *different* field). A name can read entry="extended" while `n.extension.extended=false`, so it takes **no** rank penalty. |
| **`n.dir` / card accent / sparkline color** | YES | `dir` is cycle direction; not a rank term. `dir=caution` names dominate the top. |
| **Headline label** (BOTTOMING/UPTREND/UNCONFIRMED TURN) | YES | ladder.state; not a rank term. |
| **Size chip** (×mult ≤ 0.9) | YES | inverse-vol sizing; low size = high vol, orthogonal to rank. |
| **🌊 washout / ⚡ coiled chips** | **NO (aligned)** | These chips *are* the +0.5 / +0.25-0.40 rank terms. When they show, they genuinely explain a lift — but the card never says so. |
| **⚠ extended chip** (`n.extension.extended`) | **NO (aligned, when it fires)** | This is the −0.5·score term. But it fires on only **2 of 110** rows, so it almost never explains anything visible. |
| Signal badge (T1..T4) | **NO (aligned)** | The tier is `0.30·wn` of the rank. But its swing is only 0.12 after the CN flatten — a T2 easily outranks a T1. |

**Summary:** 8 of the loudest visible fields (score, band, verdict, dir, entry-status, sparkline
color, headline label, size) are **structurally independent of rank**. Only the two positive chips
(washout, coiled) and the tier badge are rank-aligned, and the one negative rank term (extension)
is nearly always dark. So the card offers the user **no visible field that reliably tracks why the
row is where it is.**

### 3.2 Live top-15 (from `site/factordata/china_standouts.json`, as_of 2026-07-02)

`rank_setup` = `n.setup` (rank base). `DISP` = displayed `conviction.score`. `+[]` = positive rank
chips present. `NEG[]` = negative-reading visible fields.

```
#1  600267.SS  setup=1.530 T1  DISP=46 constructive  vd="Buy zone — cycle turning up"      dir=up       BOTTOMING        +[washout,coil]  NEG[size=0.53x]
#2  603129.SS  setup=0.610 T1  DISP=26 neutral        vd="Uptrend — hold, add on dip"       dir=up       UPTREND          +[washout,coil]  NEG[band=neutral, verdict~hold, entry=hold, size=0.81x]
#3  300725.SZ  setup=0.500 T1  DISP=43 neutral        vd="Uptrend — hold, add on dip"       dir=up       UPTREND          +[washout,coil]  NEG[band=neutral, verdict~hold, entry=hold, size=0.44x]
#4  002555.SZ  setup=1.530 T1  DISP=63 constructive   vd="Buy zone — cycle turning up"      dir=up       BOTTOMING        +[coil*STAR]     NEG[size=0.77x]
#5  002602.SZ  setup=1.070 T2  DISP=13 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil*STAR*FIRE] NEG[band=low, entry=extended, size=0.73x, dir=caution]
#6  300765.SZ  setup=0.310 T1  DISP=41 neutral        vd="Uptrend — hold, add on dip"       dir=up       UPTREND          +[washout,coil]  NEG[band=neutral, verdict~hold, entry=hold, size=0.40x]
#7  600129.SS  setup=-0.530 T2 DISP=14 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[washout,coil*] NEG[band=low, entry=extended, size=0.52x, dir=caution]
#8  000800.SZ  setup=-0.320 T1 DISP=10 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[washout,coil]  NEG[band=low, entry=extended, dir=caution]
#9  601059.SS  setup=0.480 T2  DISP=39 neutral        vd="Uptrend — hold, add on dip"       dir=up       UPTREND          +[coil*STAR]     NEG[band=neutral, verdict~hold, entry=hold, size=0.67x]
#10 601089.SS  setup=0.330 T1  DISP=13 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil*STAR]     NEG[band=low, entry=extended, size=0.49x, dir=caution]
#11 002099.SZ  setup=0.950 T1  DISP=13 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil]          NEG[band=low, entry=extended, size=0.57x, dir=caution]
#12 002444.SZ  setup=0.420 T2  DISP= 8 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil*STAR*FIRE] NEG[band=low, entry=extended, size=0.49x, dir=caution]
#13 600201.SS  setup=0.790 T1  DISP=11 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil]          NEG[band=low, entry=extended, size=0.69x, dir=caution]
#14 000061.SZ  setup=0.920 T2  DISP=13 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil*FIRE]     NEG[band=low, entry=extended, size=0.86x, dir=caution]
#15 600475.SS  setup=0.580 T1  DISP=12 LOW            vd="Countertrend bounce — not conf"   dir=caution  UNCONFIRMED TURN +[coil]          NEG[band=low, entry=extended, size=0.53x, dir=caution]
```

**Live contradictions flagged:**
- **Rows #5, #7–#15 (10 of the top 15)** carry `band=low`, `dir=caution`, verdict *"Countertrend
  bounce — not confirmed"*, entry *"extended"* — every visible gauge reads negative — yet they
  rank in the top 15 on cascade tier + coiled/washout bonus alone.
- **Ordering inversion #5 (DISP=13) above #6 (DISP=41):** #5 is band=low; #6 is neutral. #5 ranks
  higher because setup=1.07 vs 0.31. The displayed score is the opposite of the rank.
- **#7 has `setup=−0.53` (negative base) yet ranks #7** — the washout+coiled bonuses (+0.5+~0.25)
  floated a negative-setup, band=low, caution name into the top 7.
- **Board-wide (n=110):** 85 band=low, 78 dir=caution, 77 entry="extended", only 6 constructive +
  3 high. **19 of the top 30 are band=low.** (Counter over `china_standouts.json`, this session.)
- **Only 2 of 110 rows** (`002250.SZ`, `002020.SZ`) actually have `extension.extended=true`. So the
  *anti-chase* mechanism the owner is worried about is nearly inert; the "extended" the user SEES
  is the **entry_signal.status** chip (a timing read), which carries **no rank penalty**.

**Owner-designated picks:**
- **300725.SZ → ranks #3.** Present and near the top. But shows DISP=43, band=**neutral**,
  verdict *"Uptrend — hold, add on dip"*, entry=**hold**, size 0.44×. The card tells the user to
  *wait/hold* while ranking it 3rd — a direct rank-vs-verdict contradiction.
- **603129.SS → ranks #2.** DISP=26, band=**neutral**, verdict *"Uptrend — hold, add on dip"*,
  entry=**hold**, size 0.81×. Same pattern: top-2 rank, "hold"/neutral card.
- **688306.SH/.SS → NOT on the board at all** (absent from all 122 board tickers). Per the
  main-checkout fallback JSON it is `ladder.state = "BOTTOM WATCH"`, `conviction.score=40/neutral`,
  `entry_signal.status = "wait_pullback"`, `anticipation.as_of = 2026-06-26`. It has **no persisted
  gate verdict** (the `sig_verdict` is computed at build time and only lives on board rows), so I
  **cannot prove the exact exclusion reason from persisted data** — the most likely cause is the
  confluence gate finding no fresh T1–T4 cross (`signal_gate.gate` → not eligible), since
  "BOTTOM WATCH" + "wait_pullback" is consistent with a not-yet-crossed base. **Unverifiable from
  the artifacts available in this worktree; would need a build-time `sig_verdict` dump to confirm.**

---

## 4. RECONCILIATION OPTIONS (for the orchestrator — NOT implemented)

Ordered by contradictions-eliminated per unit effort.

### Option A — Per-row "why ranked here" reason chip (RECOMMENDED first move)
Emit the top 1–2 rank contributors as a visible chip (e.g. "T1 · washout +0.5" or "setup pct 0.94").
`blend_sorted` already computes every term; expose them on the row instead of discarding.
- **Eliminates:** the *"users cannot tell why"* half of the complaint for **all 110 rows** — the
  #7 negative-setup-but-washout case becomes self-explaining.
- **Does NOT eliminate:** the substantive rank-vs-verdict disagreement (a "hold" name still ranks
  high). It makes the contradiction legible, not gone.
- **Breaks:** nothing structural; `_score` must return components (small refactor of the closure
  to return a dict, or a parallel `_score_debug`).
- **Effort:** LOW (1 engine function + 1 template chip).

### Option B — Single arbiter: make loud fields a function of the quiet rank
Recompute the displayed score/band directly from the rank score (or blend potential *into* rank so
one number drives both). i.e. the card's big number becomes the rank score's percentile.
- **Eliminates:** the score↔rank inversion (#5>#6), the rho=−0.189 decoupling, band-low-in-top
  entirely — by construction they can no longer disagree.
- **Breaks:** the *deliberate* two-gauge design (buy-readiness "act now" vs rank "where to look").
  The potential_score exists precisely to answer "rise FROM HERE?" and was chosen over the rank
  percentile at :1032-1043. Collapsing them **discards** that distinction and the anti-chase
  penalty baked into potential. Also breaks the legend copy (`:1216`) and the US-parity two-gauge
  model.
- **Effort:** MED (changes semantics; needs owner sign-off; touches potential-score consumers).

### Option C — Demotion rules: negative gauges hard-cap rank
Make the loud negatives *actual* rank terms: e.g. band=low caps the row below all band≥neutral;
entry="extended"/dir=caution applies a real penalty (today only `n.extension.extended` does, and it
fires 2×/110).
- **Eliminates:** the 10-of-15 "everything reads negative but ranks top" cases — band=low /
  caution names sink out of the head.
- **Breaks:** the validated CN thesis that **A-share edge is mean-reversion, and a still-basing
  "countertrend/UNCONFIRMED" washout is exactly what the reversal edge wants to buy** (see
  `CHINA_STOCKS_OVERHAUL.md` / brainstorm §8). Hard-capping band=low would demote the reversal
  setups the board is *designed* to surface — risks inverting the validated signal. High
  regression risk; must be gated by a backtest.
- **Effort:** MED-HIGH (must re-validate against the reversal edge; otherwise it degrades alpha).

### Option D — Edge-vs-Timing two-glyph split (clean conceptual fix)
Split each card into two explicit glyphs: **EDGE** (why it ranks: tier + setup + bonuses → the rank
score) and **TIMING** (entry gauge + cycle state → act-now/wait/hold). Rank strictly on EDGE; the
TIMING glyph is allowed to say "wait" on a #2-ranked name without it reading as a contradiction.
- **Eliminates:** *every* contradiction in §3 conceptually — they stop being contradictions because
  the card names two axes and says which drives order. 300725/603129 "rank #2/#3, timing=hold"
  becomes coherent.
- **Breaks:** requires the big displayed number to become the EDGE/rank score (so it overlaps
  Option B's semantic change) OR a redesign that shows both numbers. Most UI surface area of the
  four; the legend, axes block, and entry block all need re-labeling.
- **Effort:** HIGH (UI redesign) but highest contradiction-coverage; A is the cheap down-payment on
  the same idea.

**Verdict for orchestrator:** ship **A** immediately (legibility, zero thesis risk), then decide
between **B/D** (both require owner sign-off on collapsing or explicitly splitting the two gauges).
**C is the riskiest** — it can silently degrade the validated mean-reversion edge and must not ship
without a backtest.

---

## Appendix — commands run (this session)
- Rank formula: read `signal_gate.py:223-264`, `build_china_library.py:1178-1230, 1036-1043,
  546-549`, `engine/coiled.py:40-44`.
- Render path: `grep` render calls in `build_china.py` → `:859-860` (mode="stocks"),
  card block `templates/china.html.j2:1197-1317`.
- Live board: `site/factordata/china_standouts.json` (as_of 2026-07-02); distributions +
  `scipy.stats.spearmanr(rank, displayed_score)=−0.189`, `(rank, setup)=−0.619`.
- 688306: only in main-checkout fallback `site/chinastockdata/688306.SS.json` (2026-06-28);
  worktree `site/chinastockdata/` absent (R2-gated) — **flagged**.
