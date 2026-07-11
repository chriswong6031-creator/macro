# User-First Design Doctrine

Status: **HOUSE LAW** for all user-facing surfaces. Operator-ordered 2026-07-10 after the
Turn Watch complaint ("showing a turn watch, but doesn't actually give clear details on
what to do — too technical, not user friendly"). This is the third strike of the same
class (Terminal 3/10 rating 2026-07-07; tape-band veto 2026-07-10) — so it is now law,
not taste.

**The law in one sentence: a human glancing at a primary dashboard must get the signal,
what it means, and what to do about it in seconds — everything else earns its place
behind a hover or a click.**

Users come for fast, accurate signals and data. They do not come to read. Big paragraphs,
internal vocabulary, unexplained numbers, and complex comparisons on a primary surface
are defects, exactly like a wrong number would be.

---

## 1. The three tiers (progressive disclosure)

Every piece of copy lives on exactly one tier. Deciding the tier is the design act.

| Tier | Where | Job | Budget |
|---|---|---|---|
| **1 · GLANCE** | always-visible on primary dashboards | state + stance + one plain line | title ≤ 4 words; subtitle ≤ 14 words; row ≤ 1 line; footer ≤ 1 sentence |
| **2 · HOVER** | `data-tip-en/zh`, `.act-pop-src` popovers, `?` help tips | mechanics, definitions, base rates, provenance, receipts | ≤ ~80 words per tip; structured (label: value) beats prose |
| **3 · STUDY** | detail pages, lab pages, committee/oracle/methodology surfaces | full technical depth, freely | none |

Primary dashboards (Tier 1 surfaces): the landing hub, `us_stocks`, `macro`,
`macro_context`, `baskets`, `allocation`, `china`, `china_intel`, `hk`, `news`,
`intraday_flow`, and any future top-nav page. Detail pages (`basket_detail`,
per-stock pages, labs, committee) are Tier 3 surfaces — but their top-of-page header
still follows Tier 1 rules, because that's where the eye lands.

**The demotion rule:** when in doubt, demote. Nothing is lost by moving detail to a
hover; attention is lost by not moving it.

## 2. The five laws

### Law 1 — Stance or it doesn't ship
Every signal panel answers "**so what do I do?**" in plain words on Tier 1 — even when
the honest answer is *nothing*. The stance vocabulary:

> **Act** · **Get ready** · **Watch — don't chase** · **Protect gains** · **Stand aside** · **Ignore**

"Watch, don't chase" is a complete, honest, useful stance. A panel that shows a state
with no stance (the old Turn Watch) makes the user do the analyst's job.

### Law 2 — Plain words on Tier 1
Banned from the glance tier (sanctioned homes: Tier 2/3):

- **Internal vocabulary:** slow reco, IGNITION, WATCH (as a state name), UPTURN_CONFIRMED,
  expected-null, forward meter, display-tier / display context only, organ, lobe, kernel,
  K-of-N, confluence (as jargon), Oracle P8 (any internal study/ruling ID), gauntlet, prereg
- **Backtest statistics untranslated:** n=, FDR, IC, z-score, t-stat, percentile ranks,
  base rates written as bare percentages
- **Raw machine slugs:** `us_sector_staples` → "Staples". Display names always; prettified
  fallback if the name map fails (never block render on a name lookup)
- **Unexplained acronyms and thresholds** ("K≥3 incl. ≥1 weekly/2W leg")
- **Comparative constructions that need a manual** ("multi-timeframe divergence",
  "cross-sectional momentum rank-IC")

Rewrite, don't delete: every banned term has a plain translation —

| Internal | Tier 1 plain English | Tier 1 中文 |
|---|---|---|
| Turn Watch — multi-timeframe divergence | Early turn signs | 早期拐点迹象 |
| IGNITION | Strong sign | 较强迹象 |
| WATCH (state) | Early sign | 初步迹象 |
| N members UPTURN_CONFIRMED | N stocks turning up | N只成分股转强 |
| slow reco: HOLD | still rated Hold | 主评级仍为「持有」 |
| T+1 58% fade (n=26) | about 6 in 10 of these faded within a day (26 past cases) | 历史26次中约六成一天内消退 |
| expected-null forward meter, display context only | a heads-up, not a buy signal | 仅为提示，非买入信号 |

### Law 3 — Numbers carry meaning
A number on Tier 1 must arrive with its interpretation. "58% fade" is a statistic;
"about 6 in 10 of these faded within a day" is information. Raw scores, percentiles, and
z-values are decoration unless the sentence around them says what big/small means and
what to do differently because of it. Precision belongs on Tier 2 ("58.3%, n=26,
window 2021-2026"); meaning belongs on Tier 1.

### Law 4 — Word budgets are hard limits
Tier 1 budgets (Law §1 table) are enforced at review like the render budget is at build.
If the copy doesn't fit, the content is mis-tiered — demote, don't compress into
denser jargon. One as-of stamp per panel. One footnote per panel (merge, never stack).
No duplicate timestamps, no stacked micro-disclaimers, no per-row repetition of a
constant (the old strip printed "T+1 58% fade" on every row — a constant belongs in the
footer, once).

### Law 5 — Honesty survives translation
User-first **never** means overclaiming. The epistemics laws still bind on every tier:
nulls printed, "validated" CI-guarded, no LLM-originated escalation, no interpretive
spin words on tape rows (giveback / dead-cat / bounce — banned by adversarial ruling,
\#2208). What changes is the *language* of honesty:

- The null is stated in **plain words on Tier 1**: "a heads-up, not a buy signal —
  most of these faded within a day."
- The **receipt** (study ID, n, window, tier) moves to Tier 2: "backtested basket-level
  turn = null edge (Oracle P8, n=26); slow reco labels unchanged; display tier."
- Plain-word disclosure on Tier 1 + receipt on Tier 2 **is** the compliant form of
  "nulls printed, not hidden." Jargon disclosure ("expected-null forward meter") is the
  *non-compliant* form — it discloses nothing to the person it's addressed to.

## 3. Ratified patterns (case law — reuse, don't reinvent)

- **Plain-English lanes** (#2206, us_stocks action board): 🟢 Buy now · 🔵 Almost ready ·
  🏃 In favour · 🟠 Take profits · ⚪ Stand aside. Lane names ARE stances. Unknown states
  route to the cautious lane.
- **Hover popover row anatomy** (#2206): calm one-line rows; full detail (signal age,
  breadth, overlays, two-reads) in a `.act-pop-src` popover cloned on hover.
- **Self-labeling chip strip** (#2208, `.dtp-*`): the state token IS the label
  (LIVE · 15-MIN DELAYED / SETTLED CLOSE), one as-of, full display names (wrap, never
  truncate), honest shared-scale bars, flow demoted to data-tips, one merged footnote.
- **`?` help tip on the panel h2** (MTF table): the sanctioned Tier 2 home for mechanics.
- **Vetoed idioms — do not clone:** the old ftr-tape band (raw slugs, rank numbers,
  pill spam, "Live" over settled data, fake magnitude bars, stacked disclaimers) — still
  present on `baskets` / `allocation` / `basket_detail`; port the `.dtp` idiom instead.

## 4. The worked example — Turn Watch, before → after

**Before (shipped in #2071, vetoed 2026-07-10):**

> **⚡ TURN WATCH — MULTI-TIMEFRAME DIVERGENCE**
> `[⚡ IGNITION]` Memory & Storage — slow reco: HOLD (as-of 07-09) · T+1 58% fade
> *Expected-null forward meter (basket-level turn fired NULL in backtest, Oracle P8). Slow reco labels unchanged. T+1 flip base rate: 58% fade (n=26). Display context only.*

Every failure at once: jargon title, internal state names, internal vocabulary
("slow reco"), a per-row repeated statistic, a footer that is pure epistemics jargon —
and **no stance anywhere**.

**After (this PR):**

> **⚡ EARLY TURN SIGNS** — *Bounce attempts in groups we still rate Hold/Avoid. Watch — don't chase.*
> `[STRONG SIGN]` Memory & Storage · still rated Hold *(hover: full receipt)*
> *Not a buy signal: in 26 past cases, about 6 in 10 of these early signs faded within a day. If the turn is real, the lanes below upgrade on their own.* `?`→ *(technical receipt)*

Same data, same honesty, same gate logic — a human can now consume it in three seconds
and knows exactly what to do (nothing yet; re-check these names; trust the board to
upgrade).

## 5. Builder checklist (pre-ship, every user-facing PR)

1. **The 5-second test:** a cold reader states what the panel means and what to do.
   If they can't, it fails — regardless of how accurate it is.
2. Every panel has a stance (Law 1), even "nothing — watch."
3. No banned vocabulary on Tier 1 (Law 2 table); receipts live on Tier 2.
4. Numbers translated (Law 3); budgets respected (Law 4); one as-of, one footnote.
5. Bilingual parity: ZH copy is equally plain — never raw EN state names dropped into
   ZH text (`慢速评级: HOLD` is a defect). No translated text in `title=` (CI-guarded);
   use `data-tip-en`/`data-tip-zh`.
6. Mockups first for new surfaces; builders get actual screenshots, not prose specs;
   browser-verify against production-shaped data before ship (curl status is theater) —
   the standing quality-bar law.
7. Honesty intact: nulls disclosed in plain words, no "validated" (CI), no invented
   certainty, no spin vocabulary.

## 6. Enforcement

- This document is linked from `CLAUDE.md` §House laws — every session sees it.
- Review stages of UI workflows must check the diff against §5 explicitly.
- **Follow-up (ratchet guard):** a CI vocabulary lint (banned Tier 1 tokens outside
  tooltip/popover/hidden elements) applied to a compliant-surface whitelist that grows
  as surfaces are ported. Not built yet — build it once the §7 backlog is ported, so it
  never reddens main on legacy debt.

## 7. Census appendix — violations to port (2026-07-10)

Inventory from an 11-surface census (sonnet census lanes + opus adversarial rank,
2026-07-10). **Volume: roughly 120–150 distinct primary-tier violations across 10
surfaces.** By kind: internal-vocab/state-enum leaks ~45–55 (largest class);
acronym-soup ~30–35; number-without-meaning ~20–25; stat-dump ~15–20 (the
"n=26 / 58% fade" footer alone recurs in ~8 primary-tier spots); wall-of-text ~12–15;
raw-slug ~8–10; no-stance ~6–8. Port opportunistically when touching a surface, or as
dedicated copy-tier PRs. Top verified offenders:

| # | Surface | Offense | Where |
|---|---|---|---|
| 1 | us_stocks | Turn Watch strip: jargon title + "Expected-null forward meter…Oracle P8…n=26" always-visible footer, no stance | ~~dashboard.html.j2:5414~~ **FIXED in this PR** |
| 2 | baskets | ftr-tw-card: raw IGNITION/WATCH states, "cross-sec z / sibling rs_z+ / complex_confirm" leg slugs, same Oracle-P8 footer | baskets.html.j2:681–706 |
| 3 | china | "Context chips / **背景芯片**" — developer label leaked as a section heading; ZH literally means silicon chip. Raw `who_controls` slugs nearby | china.html.j2:964,968 |
| 4 | baskets/allocation/basket_detail | "T+1 violent-flip base rate: 58% fade (n=26) · flip-confirmation lens" footer replicated on 3+ surfaces | baskets.html.j2:453; allocation.html.j2:239; basket_detail.html.j2:198 |
| 5 | us_stocks/macro | "α-ranked names that have triggered the MACD-2D × StochRSI-3D confluence buy" subtitle; sector-setups h2 repeats it | dashboard.html.j2:6320,6525,6567 |
| 6 | china_intel | Ranking formula exposed in always-visible prose ("opportunity = signal × edge-remaining × leading-gap"); bare scores with no scale | china_intel.html.j2:412,549 |
| 7 | news | Calibration board: raw wilson_low_5d/wilson_high_5d thresholds + "earned-authority gate" architecture talk (inside a `<details>` — borderline) | news.html.j2:686 |
| 8 | china | Ripening Shelf cards: "2W Stoch · MACD D hist (d=−0.8) · 2W MACD ETA" acronym column at rest | china.html.j2:2035–2068 |
| 9 | basket_detail | ~90-word always-visible disclaimer ("T1–T4 confluence… T3* provisional… cycle blocks"); tier badges show internal stage names | basket_detail.html.j2:582–590,664 |
| 10 | allocation | "What is actually **validated**" / "The **validated** edge is…" in user copy — house-law word (CI checker `check_validated_claims.py`); verify allowlist status | allocation.html.j2:503,537 |
| 11 | baskets | Vetoed rank-# tape idiom still shipping (`#1…#34` mr-rank) — standing-ruling violation, port to `.dtp` | baskets.html.j2:572 |
| 12 | us_stocks | "⚡ Coiled·FIRE" chip — machine-state enum + vol-squeeze jargon at rest | dashboard.html.j2:5879 |

Census-distilled good patterns beyond §3 (canonize): question-as-subheading framing
("do they confirm stocks?", "is this regime ending?"); number-with-meaning pairing
(ratio + broad/narrowing/narrow word label; dial with Panic/Neutral/Euphoria anchors);
lightweight honesty chips ("~" approx prefix, "≈15-min delayed bars",
"IN FAVOUR — NO ENTRY" instead of a false green); slug-to-label translation dicts at
render (STANCE_ZH / BAND_ZH pattern) — extend them to the leak sites rather than
inventing new mechanisms; non-verbal encodings (K/7 dot-bars, quadrant colors,
severity dots) that need no vocabulary at all.
