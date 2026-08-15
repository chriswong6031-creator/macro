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

**Not inherited from Prophet:** seven-cell plan lifecycle (Watch / Ready / Entered / Delivering / Overtime / Invalidated / Resolved as *plan* cells), Own-It / Featured-as-conviction, Priority-as-a-number, entry/target/void levels, stance Buy/Wait/Hold/Avoid as the card's ruling verb. Candidate/featured hues use `--ok` (direction-neutral), never `--pv-buy` — that token flips red under `html[data-lang=zh]` because it is derived from `--up`. Tape change still uses `--ink-up/--ink-down`.

**Inherited from Prophet (sister language):** tokens, card geometry (12px radius, 74px hero, 232px grid min), typography/density, chip anatomy, featured aura *as a Best-lane mark only*, hover/drawer disclosure, light-mode white card plane, zh direction-ink flip, weight-only lifecycle marks, freshness banner grammar, 390px single-column / no page-level horizontal scroll, visible `:focus-visible`, `prefers-reduced-motion`.

---

## 1. Information architecture

### Header
- Title: Live Entry Radar / 实时入场雷达
- Purpose ≤ one sentence (contract §14)
- Session stamp + synthetic/degraded pill + as-of
- Unmissable REFERENCE banner (page chrome + in-flow note)
- Probe Set headline integer
- Lifecycle ladder: **Probing · Pre-candidate · Candidate** (live enclosure) | **Invalidated · Expired** (terminal, outside the live sum)
- Expert lanes: All · Best · Grey Dot · 1D Washout · 1D Turn · Deep Washout · Intelligence · **C4 context-only (not a filter, not a fire)**

Lane mapping (contract §14 names → W3 detector ids):

| Lane | Detector | Fires? |
|---|---|---|
| Grey Dot | `G0_GREY_DOT@1` | yes · nightly · confirmed |
| 1D Washout | `C1_1D_LIVE_WASHOUT@1` | yes · 1D LIVE provisional |
| 1D Turn | `C2_1D_TURN@1` | yes · six variants, never blended |
| Deep Washout | `C3_1D_4H_RECOVERY@1` | yes · confirmed 4H |
| Intelligence | `C5_BOTTOM_WATCH@1` | yes · event-bound |
| *(not a lane)* | `C4_MTF_TURN@1` | **never** · `role=stratification_only` |

### Card (glance)
1. Hero spark *or* printed null at equal 74px (VTC-301 lesson)
2. Lifecycle chip (axis labelled) + expert identity chip (G0/C1/C2/C3/C5) + C2 variant when present
3. Live/session quote (em-dash when unavailable — never invented)
4. Ticker + bilingual name
5. Priority slot: **ACCRUING** — never a number (W6 has not run)
6. Cohort line; C4 context chip when present; multi-expert count
7. Weight mark + lifecycle word + Why control
8. One-line mechanical why-candidate
9. False-start count when history exists (not tooltip-only)
10. Footer: freshness in plain words + as-of

### Drawer (Why)
Why here → why armed → why candidate/fired → C2 variant → C4 context → invalidation → expiry → Opportunity **NOT YET MEASURED** → clocks (`known_at` / as-of) → false-start history → sibling expert lanes.

Why-now copy is mechanical. No “huge upside”, no “92% likely”, no “AI says buy”, no “validated”.

---

## 2. States that must stay visually distinct

| State | Treatment |
|---|---|
| 1D LIVE provisional | dashed provisional freshness; never “Daily confirmed” |
| G0 nightly confirmed | `nightly · confirmed` |
| C3 confirmed 4H | `confirmed 4H` — not provisional |
| Stale | dashed card, no featured aura, no hover lift, banner on the page |
| Unavailable / raw-basis | condition is **null**, chip says UNAVAILABLE, not a non-fire |
| Degraded evaluator | header pill + banner; cards demoted |
| Invalidated false start | terminal weight + struck mark; ledger row kept |
| Expired | terminal muted weight; ledger row kept |
| False-start history | counted on the card, listed in the drawer |
| Multi-expert ticker | **one card per (ticker, expert)** — never one generic “entry signal” |
| Quiet / no candidates | empty well; Probe Set may still be non-zero on other states |
| C4 | dashed “C4 · context only”; cannot be a lane filter; cannot be `data-expert` on a card |

---

## 3. No fabricated edge

W8 is before W6/W7. The reference **refuses**:

- Research Priority numbers
- Opportunity / probability / expected-return numbers
- “validated” / “edge confirmed” language
- Fake conversion of Radar episodes into Prophet plans

Slots exist so W9 does not have to invent layout later. They print `ACCRUING` / `NOT YET MEASURED` / `UNAVAILABLE` / `PLACEHOLDER — FUTURE W6/W7`.

---

## 4. Fixtures

Every row is `synthetic: true`. Tickers are `REF.*` / `FIX.*`. Prices are demo overlays and the page says so.

Required states (query `?state=`): `quiet`, `g0`, `c1`, `c2`, `c3`, `c5`, `multi`, `expired`, `invalidated`, `history`, `stale`, `unavailable`, `raw`, `degraded`, `partial`, `board` (many), `anon`, `ipo`, `lobe`.

---

## 5. R3/R4 defects we do **not** inherit

From the R4 closure ledger (PR #5560), Radar refuses:

- Card with no route (PRC-301) — ticker is a real in-page link
- Anon gate promising levels the card bans (PRC-302) — copy lists what Radar actually shows
- Header that can only say “settled close” (PRC-305) — freshness branches
- Chartless 24px void (VTC-301) — equalised 74px printed null
- Stance/tape one-colour collision (DA-002) — tape uses `--ink-up/--ink-down`; lifecycle is weight-only
- Amber meaning three things (VTC-304) — amber is caution / stale only

---

## 6. i18n / theme / a11y

- EN and ZH are first-class; hierarchy is structural (`.l-en` / `.l-zh`), not a string swap that collapses slots
- Dark and light are both design targets; light cards sit on a white plane
- zh flips **direction** inks only (红涨绿跌); lifecycle marks never reference `--up/--down`
- Visible `:focus-visible` on ladder, lanes, Why, clear
- `prefers-reduced-motion` kills hover lift
- No emoji as functional icons (caution banner is a CSS border + words)
- Critical states (stale, unavailable, C4-not-a-fire, false-start history, provisional) are on the card, not tooltip-only
- 390px: one column, no page-level horizontal scroll

---

## 7. What W9 may copy vs must wait

See `W9_IMPLEMENTATION_HANDOFF.md`.
