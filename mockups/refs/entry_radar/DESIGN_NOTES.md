# Live Entry Radar — W8 reference design notes

**Status:** REFERENCE ONLY. Not production. Not self-approved.
**Workstream:** `WS:LIVE-ENTRY-RADAR` · Wave W8 / PR-8
**Authority:** operator design directive 2026-08-13 + `DEC:LER-PROPHET-BOARD-IS-DESIGN-REFERENCE`
**Pinned Prophet Board (session start, after `git fetch origin main`):**

| Pin | SHA |
|---|---|
| `origin/main` | `cc6f53f619f439683a4da7aa366843aef6079768` |
| R4 merge PR #5560 | **`168a9be006914441051cff393927ce465e39138e`** |
| `mockups/refs/institutionalize/us_stocks` tree | **`d540f493a097cb37f3f91e4c7bc81a39b876d069`** |

See `PINNED_PROPHET_REFERENCE.md`. The PR-body SHA `9995603e` is the pre-squash branch head and is **not** on `origin/main`.

How to run:

```bash
python3 -m http.server 8793 --directory mockups/refs/entry_radar
# ?theme=dark|light  ?lang=en|zh  ?state=board|quiet|…  ?chrome=0
```

---

## 0. Product question (must be instant)

| Surface | Question |
|---|---|
| Prophet Board | What do we want to own? |
| **Live Entry Radar** | **Where is an observable entry opportunity developing right now, through which expert, why, and how fresh is the evidence?** |

The header purpose line states Radar's question in plain words. A sister line under it names the distinction so a reader coming from Prophet does not read this as Own-It.

**Not inherited from Prophet:** seven-cell plan lifecycle (Watch / Ready / Entered / Delivering / Overtime / Invalidated / Resolved as *plan* cells), Own-It / Featured-as-conviction, Priority-as-a-number, entry/target/void levels, stance Buy/Wait/Hold/Avoid as the card's ruling verb. Candidate/featured hues use `--er-life` (slate-indigo, direction-neutral) — never `--pv-buy` (flips red under `html[data-lang=zh]` because it is derived from `--up`) and never `--ok` (that green is the same family as ZH `--down`). Tape change still uses `--ink-up/--ink-down`.

**Inherited from Prophet (sister language):** tokens, card geometry (12px radius, 74px hero, 232px grid min), typography/density, chip anatomy, featured aura *as a Best-lane mark only* (computed from the Best filter — the same set, not a silent 2-card glow), hover/drawer disclosure, light-mode white card plane, zh direction-ink flip, weight-only lifecycle marks, freshness banner grammar, 390px single-column that *fits* (not `overflow-x: hidden`), visible `:focus-visible`, `prefers-reduced-motion`.

---

## 1. Information architecture

### Header
- Title: Live Entry Radar / 实时入场雷达
- Purpose ≤ one sentence (contract §14)
- Session stamp + synthetic/degraded pill + as-of
- Unmissable REFERENCE banner (page chrome + in-flow note)
- Probe Set headline integer
- Lifecycle ladder: **Probing · Pre-candidate · Candidate** (live enclosure) | **Invalidated · Expired** (terminal, outside the live sum)
- Expert lanes: All · **Best · unranked** (count dashed — not a W6 rank) · Grey Dot · 1D Washout · 1D Turn · Deep Washout · Intelligence · **C4 context-only (not a filter, not a fire)**

Lane mapping (contract §14 names → W3 detector ids):

| Lane | Detector | Fires? |
|---|---|---|
| Grey Dot | `G0_GREY_DOT@1` | yes · nightly · confirmed |
| 1D Washout | `C1_1D_LIVE_WASHOUT@1` | yes · 1D LIVE provisional |
| 1D Turn | `C2_1D_TURN@1` | yes · six variants, never blended |
| Deep Washout | `C3_1D_4H_RECOVERY@1` | yes · confirmed 4H |
| Intelligence | `C5_BOTTOM_WATCH@1` | yes · event-bound |
| *(not a lane)* | `C4_MTF_TURN@1` | **never** · `role=stratification_only` |

### Card (glance) — W8 founding subset, **not** contract §14 complete
1. Hero spark *or* printed null at equal 74px (VTC-301 lesson). Stale has a path; it must not print “No path yet.”
2. Lifecycle chip + expert identity chip (G0/C1/C2/C3/C5). Overlay wraps (sister `flex-wrap: wrap` at `calc(100% - 122px)`). The overlay does **not** repeat the LIFECYCLE axis — that word already sits in the body next to the weight mark; duplicating it overflowed Pre-candidate under the price. Expert keeps its axis. C2 variant lives on the marks row / drawer — not the overlay.
3. Live/session quote (em-dash when unavailable — never invented)
4. Ticker + bilingual name. **Not a link** — founding surface has no `stock.html`.
5. Priority slot: **em-dash** on the card. One board-level line says `Priority ACCRUING — W6 has not measured a rank.` Never a number.
6. Cohort line; C2 variant chip when present; C4 context chip when present; multi-expert count
7. Weight mark + lifecycle word + Why control
8. One-line mechanical why-candidate
9. False-start count when history exists (not tooltip-only)
10. Footer: freshness in plain words + as-of (wraps; not nowrap-clipped)

**Reserved, not omitted** (ACCRUING / UNAVAILABLE / BLOCKED_DATA until W4) — do not teach W9 that their absence is law:
- Glance component states: 1D Stoch / MACD-RSI / Structure / Lobe evidence
- Zone + invalidation on the glance footer (invalidation is drawer-only in this reference)

### Drawer (Why) — W8 founding subset, **not** contract §14 complete
Why here → why armed → why candidate/fired → C2 variant → C4 context → invalidation → expiry → Opportunity **NOT YET MEASURED** → clocks (`known_at` / as-of) → false-start history → sibling expert lanes.

**Reserved drawer slots** (ACCRUING / UNAVAILABLE until W4): why-now, what is recovering, still structurally strong, risk geometry / asymmetry, what else sees it (lobes), trustworthiness / sample, fire-path mini chart (arm / trough / turn / promotion).

Why-now copy is mechanical. No “huge upside”, no “92% likely”, no “AI says buy”, no “validated”.

---

## 2. States that must stay visually distinct

| State | Treatment |
|---|---|
| 1D LIVE provisional | dashed lifecycle chip + dashed provisional freshness; never “Daily confirmed” |
| G0 nightly confirmed | `nightly · confirmed` |
| C3 confirmed 4H | `confirmed 4H` — not provisional |
| Stale | dashed card, no featured aura, no hover lift, banner on the page |
| Unavailable / raw-basis | condition is **null**; freshness footer says UNAVAILABLE; lifecycle chip stays the lifecycle word (dashed/muted). Not a non-fire |
| Degraded evaluator | header pill + banner; cards demoted |
| Invalidated false start | terminal weight + struck mark; ledger row kept |
| Expired | terminal muted weight; ledger row kept |
| False-start history | counted on the card, listed in the drawer |
| Multi-expert ticker | **one card per (ticker, expert)** — never one generic “entry signal” |
| Quiet / no candidates | empty well; Probe Set stays the live probe universe (not forced to 0) |
| C4 | dashed “C4 · context only”; cannot be a lane filter; cannot be `data-expert` on a card |

---

## 3. No fabricated edge

W8 is before W6/W7. The reference **refuses**:

- Research Priority numbers
- Opportunity / probability / expected-return numbers
- “validated” / “edge confirmed” language
- Fake conversion of Radar episodes into Prophet plans

Slots exist so W9 does not have to invent layout later. Priority is one board-level `ACCRUING` line plus an em-dash on the card. Opportunity prints `NOT YET MEASURED`. Missing §14 glance/drawer slots are reserved as `ACCRUING` / `UNAVAILABLE` / `BLOCKED_DATA` — they are not secretly complete.

---

## 4. Fixtures

Every row is `synthetic: true`. Tickers are `REF.*` / `FIX.*`. Prices are demo overlays and the page says so.

Required states (query `?state=`): `quiet`, `g0`, `c1`, `c2`, `c3`, `c5`, `multi`, `expired`, `invalidated`, `history`, `stale`, `unavailable`, `raw`, `degraded`, `partial`, `board` (many), `anon`, `ipo`, `lobe`.

---

## 5. R3/R4 defects we do **not** inherit

From the R4 closure ledger (PR #5560), Radar refuses:

- Card with no route (PRC-301) — **PRC-301 is not closed.** Founding surface has no `stock.html`. Cards are not links. A `#ticker` hash with no matching id is the same defect restated. Honest form is no link until a real destination exists.
- Anon gate promising levels the card bans (PRC-302) — copy lists what Radar actually shows
- Header that can only say “settled close” (PRC-305) — freshness branches
- Chartless 24px void (VTC-301) — equalised 74px printed null. Stale is a freshness fact and keeps its path. Unavailable / raw-basis / degraded / terminal print Path unavailable / refused / retained / closed. “No path yet” is only for a true missing spark.
- Stance/tape one-colour collision (DA-002) — tape uses `--ink-up/--ink-down`; lifecycle uses `--er-life`, never `--pv-buy` or `--ok`
- Amber as a single meaning (VTC-304) — **not fully inherited.** Stale / degraded / false-start use `--warn` (caution). Pre-candidate still uses `--pv-wait` (forming, not caution). Words disambiguate; do not tell W9 amber is single-meaning.

---

## 6. i18n / theme / a11y

- EN and ZH are first-class; hierarchy is structural (`.l-en` / `.l-zh`), not a string swap that collapses slots
- Dark and light are both design targets; light cards sit on a white plane
- zh flips **direction** inks only (红涨绿跌); lifecycle marks never reference `--up/--down`
- Visible `:focus-visible` on ladder, lanes, Why, clear
- `prefers-reduced-motion` kills hover lift
- No emoji as functional icons (caution banner is a CSS border + words)
- Critical states (stale, unavailable, C4-not-a-fire, false-start history, provisional) are on the card, not tooltip-only
- 390px: one column that fits. Do not pin “no hscroll” with `overflow-x: hidden`. Overlay wraps (sister rule); C2 variant is not in the overlay. At ≤720px the purpose sentence stays; the sister “not Prophet” line may hide. Never drop both.

---

## 7. What W9 may copy vs must wait

See `W9_IMPLEMENTATION_HANDOFF.md`.
