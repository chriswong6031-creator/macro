# Mastermind Master Product Design System — V1

**Program:** Mastermind Product Design System & Experience Convergence, Wave 0.
**Status:** BINDING once merged — the visual/composition constitution for every customer-facing
Mastermind surface in this repo. Content law stays with `docs/DESIGN_DOCTRINE.md` (on conflict,
the doctrine wins). Information architecture stays with
`research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md`. The five P0 reference pages stay with
`research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` — nothing here reopens its red-teamed rulings.
**Authority:** Fable main loop (design synthesis + adjudication); bounded sonnet census lane
(current-main delta audit); independent Opus red-team before freeze (§18). No model approved its
own critical design work.
**Companions (this PR):** `research/DESIGN_MIGRATION_FACTORY_V1.md` (migration packets, ratchet,
launch docket), `mockups/design_system/specimen.html` (the executable specimen — the visual
constitution), `mockups/design_system/macro_reference.html` (the dense-dashboard reference).
**Production impact of this PR: none.** Wave 0 defines law and reference artifacts; production
migration begins only through the migration factory. Token additions land via DS-PR-0 (factory
doc §5), never ride this document.

---

## 0. How to use this document

A future agent asking *"what does a Mastermind page look like, how much information belongs on
it, how does it behave in light and dark, which components am I allowed to use, and which
architecture does this route belong to"* gets the answer here, in this order:

1. Find the route's **archetype** — §10 table (or `page_registry` overrides once DS-PR-1 adds
   the field). The archetype fixes the page's job, layout, first-level module budget, mobile
   reduction, and identity device.
2. Compose ONLY **canonical components** — §11 inventory. If a needed component is not there,
   the gap goes to the design lane (opus+ per CLAUDE.md §Model routing); builders never invent.
3. Style with **tokens only** — §2. A hex literal, ad-hoc radius, or new font stack on a
   migrated surface is a defect (ratchet: factory doc §6).
4. Compose density by **§9 law** — primary question, answer first, budgets, one-integer rule.
5. Verify against the **specimen** (`mockups/design_system/specimen.html`) and the archetype's
   reference page, in **both themes and both languages**, before ship (doctrine §5 checklist).

If two sources disagree: DESIGN_DOCTRINE (content) > this document (visual/composition law) >
the archetype reference page (worked example) > any individual live page. A live page is never
precedent — that is what "the answer depends on whichever page was redesigned most recently"
means, and it is the failure mode this document exists to end.

---

## 1. Brand personality — calm institutional intelligence

Mastermind is the desk that already did the reading. The product must feel intelligent because
it **compresses** complexity, not because it exposes it. The engine may know 400 things; the
page shows seven, and each of the seven says what happened, why it matters, and what to do.

Personality in five words each:

- **Dark — the command center.** Graphite surfaces, luminance depth, instrument calm. Nothing
  blinks that isn't live. It should feel like the lights are low because the desk is working.
- **Light — the research workspace.** Paper, structure, air. White panels on a cool canvas,
  hairline discipline, shadow instead of glow. It should feel like a printed institutional
  note that happens to be alive.

They are **two art directions of one system, never a palette inversion** (doctrine §5.8). Every
canonical component carries both treatments by construction (§12).

**The reserved-hue law (the system's signature principle).** On Mastermind surfaces, hue is a
reserved word. Color appears only when it *means* one of five things:

| Meaning | Tokens | Notes |
|---|---|---|
| Market direction | `--up`/`--down` → `--ink-up`/`--ink-down` | flips under zh 红涨绿跌, double-flips under light×zh |
| Health / severity | `--ok`/`--warn`/`--act` (+inks) | never flips — red is always danger |
| Wayfinding / action | `--link`/`--info` (+inks) | the one brand accent |
| Provisional/epistemic tier | `--prov`(+ink) | direction-neutral by construction |
| Locked content | violet, `--mx-tier-accent` | **lock-only** — never on data (packet §0) |

Everything else is achromatic: text, muted, line, panels. A colored element with none of these
five meanings is decoration, and decoration is a defect on an institutional surface. The one
sanctioned ambient exception is the site aurora (§16) — brand atmosphere at `z-index:-1`,
alpha-tuned per theme, never touching legibility.

**Typography as identity.** One family — Inter, self-hosted, CN-deliverable — used across an
extreme weight range: 900 for the wordmark and verdict words, 400–600 for everything else,
tabular figures for every numeral column. The institutional signature is *weight contrast and
numeric discipline*, not a second typeface. This is a deliberate choice, not a default: a serif
display would cost mainland font delivery, fight CJK parity, and read as editorial dressing on
what is an instrument panel. The verdict word at `--fs-display` (46px, 800, −.03em) IS the
display face of this product.

---

## 2. Token system — extends `templates/theme.css`, never parallels it

`theme.css` is the single source of truth for color, and becomes the single source for the
scales below. **No new `:root` token family may be created outside it** on product surfaces
(`--bci-*`, `--wri-*`, `landing.css`'s root set are migration debt, §11.3). Page-local tokens
are permitted only as *derivations* of theme tokens (`--pv-*` and `--ms-*` are the compliant
pattern: local names bound to theme values at the top of a scope).

### 2.1 Canonical today (KEEP — already law)

Surfaces `--bg/--panel/--panel2/--line`; text `--text/--muted`; direction `--up/--down` with
the zh/light flip matrix; health `--ok/--warn/--act`; accent `--link/--info`; quadrants
`--q1..q4` (flip-aware); Prophet verbs `--pv-*`; provisional `--prov`; text-grade inks
`--ink-*` (the fill-vs-text separation and its hue-keyed light rungs are settled law — see the
ink ceiling note, theme.css:171–295); glass family `--glass-*`; buttons `--gbtn-*`; scrollbars
`--sb-*`; fonts `--font-ui/--font-mono` (+`--num` alias); shadows
`--card-shadow/--popover-shadow/--glass-shadow`; chart backstop `--chart-bg`.

### 2.2 New scales (to land in `theme.css :root` via DS-PR-0 — values are minted at today's
shipped pixels so the token landing repaints nothing)

**Type ramp** — promote the 11-step ramp from `dashboard.html.j2:1641` verbatim (this is the
packet's PR-0(a); restated here as the site ramp so no one re-derives it):

```
--fs-display:46px  hero verdict word          --fs-body:14px   base copy
--fs-num-xl:38px   big board scores           --fs-h3:14px     subsection titles (700)
--fs-h1:28px       page title (800, -.02em)   --fs-sm:12.5px   secondary copy / table body
--fs-num-lg:22px   secondary numerals         --fs-label:11px  eyebrows · caps (.08em)
--fs-h2:17px       panel titles (700, -.01em) --fs-micro:10px  dense ticks · table heads
--fs-md:15px       lead body / strong figures
```

Weight pairings are part of the ramp: display/h1 800 · h2/h3 700 · body 400–500 · eyebrow 600.
`html body` base stays 15px; dashboards set `font-size:var(--fs-body)` at their shell.

**Spacing scale** — an 8-step rhythm named from the estate's own dominant values:

```
--sp-1:4px  --sp-2:8px  --sp-3:12px  --sp-4:16px  --sp-5:20px  --sp-6:24px  --sp-7:32px  --sp-8:44px
```

Canonical uses: panel padding `16px 18px` (as `html body .panel` ships today); grid gap 18px;
section-to-section 28px (–sp-6 + optical 4); page gutter ≥16px mobile / ≥24px desktop; footer
band `--sp-8`. Law: **layout gaps** (grid gaps, section margins, panel padding) snap to the
scale on migrated surfaces; ±2px *optical* nudges inside a component (e.g. `.dtp`'s 9px row
padding) are tuning, not violations — the scale governs the skeleton, not the glyph.

**Radius scale** — five stops, minted at shipped values (49 live values collapse into these at
migration; nothing repaints on token landing):

```
--r-ctl:8px (chips, inputs, small buttons) · --r-btn:10px (gbtn, tiles) ·
--r-card:12px (cards) · --r-panel:14px (top-level panels) · --r-pill:999px
```

**Elevation ladder** — dark builds depth by *luminance*, light by *shadow + border*; the ladder
formalizes the four shadow tokens that already exist plus one new hover stop:

| Level | Surface | Dark mechanism | Light mechanism |
|---|---|---|---|
| E0 | canvas `--bg` | aurora only | aurora (airy alphas) |
| E1 | resting panel/card | `--panel` + `--line` hairline + `--card-shadow` | white + `--line` + `--card-shadow` |
| E2 | raised/hover/nested | `--panel2` step, or `--shadow-hover` *(new: `0 14px 30px -16px color-mix(in srgb, var(--link) 40%, transparent)` — the shipped card-hover shadow, tokenized)* | same token; light resolves softer via its shadow colors |
| E3 | floating (popover/menu/tooltip) | glass family (`--glass-*`, `--popover-shadow`) | glass light block (already tuned) |

Law: **nesting depth ≤ 2.** A `--panel2` surface may sit inside a `--panel`; nothing nests
inside `--panel2`. Boxes-in-boxes-in-boxes is how dashboards rot.

**Motion tokens** — three durations, two easings (values are the estate's shipped ones):

```
--t-fast:.16s (color/border state) · --t-med:.2s (lifts, reveals) · --t-slow:.55s (sweeps)
--ease-std:ease · --ease-lift:cubic-bezier(.2,.7,.3,1)
```

Motion law in §7.

**Chart series scale** — display charts get a categorical scale derived from estate DNA
(direction hues excluded — they mean direction; violet excluded — it means locked):

```
--ser-1: #5b9bf0 / light #2f63c4   (subject — the info blue)
--ser-2: #d4a017 / light #8f6a04   (comparison — the quad gold)
--ser-3: #0ea5e9 / light #0284c7   (second comparison — the aurora cyan)
--ser-4: #e08b45 / light #b06a25   (last resort — the orange)
```

Law: `--ser-1` is always the subject; **a display chart with more than 4 series is mis-tiered —
demote to a table or split the chart.** A series that *means* direction uses `--up/--down`
(so zh flips it); a series that means health uses the health tokens. Series hues never carry
text — labels print in `--text`/`--muted` (or the `--ink-*` rung if a label must take the hue).

### 2.3 Token naming law

Extend in place; never fork. New semantic needs → new tokens IN `theme.css`, named for meaning
(`--prov`, not `--blue2`), with a light twin and — if ever printed as text — an ink rung
(`--ink-<name>` per the shipped formula). Consumers write `var(--ink-x, var(--x))` fallbacks
(cache-stale law, theme.css:195). Remember the ink ceiling: an ink rung keyed to a HUE breaks
when the hue is itself a mix — re-measure, don't copy percentages (theme.css:262–279 is the
worked example).

---

## 3. Surface hierarchy

Exactly four planes (E0–E3, §2.2). Assignments:

- **Canvas** carries only chrome, page header, and section headers — never data.
- **Panel (E1)** is the unit of *one answer*: one panel = one question answered. A panel with
  two unrelated jobs is two panels.
- **Panel2 (E2)** is for *members of a set inside a panel* (tiles, rows, cells) or transient
  raised states. Not a second independent card system.
- **Glass (E3)** floats: menus, LENS popovers, sheets. Glass never rests in the page flow.

The `--panel/--panel2` luminance step IS the dark theme's depth. In light the same step reads
as white-on-tint; the canvas (#f7f8fa) must stay perceptibly deeper than panels — "panel ≈ bg"
is the flatness bug (doctrine §5.8).

---

## 4. Typography law

- `--font-ui` for words. `--font-mono` for **figures, tickers, code, axis ticks — never for
  words** (not headings, not labels, not verdicts; the memory-law "mono numerals are for
  figures, never words").
- Numeral columns always `.tnum` (`font-variant-numeric:tabular-nums`) so figures never jitter.
- Eyebrow (`.eyebrow`) is the house section label: 600, `--fs-label`, caps, `.08em`, `--muted`.
- Verdict words: `--fs-display`/800/−.03em, ink from the state's `--ink-*` rung.
- zh: CJK stack leads under `html[data-lang="zh"]` (shipped); **letter-spacing 0 on CJK
  headings** (shipped); zh copy is written native-shaped, never calqued (memory: "ZH was
  English-shaped"); word budgets apply to zh separately (a 14-word EN clause is ~14–20 hanzi,
  not a literal translation of every clause).
- Line length on reading surfaces (archetype F): 62–74ch measure, 1.55–1.65 leading.
- No page introduces a font stack. `--sc-num`, `--wri-mono`, `--fig` and the other parallel
  page-local font tokens are migration debt: rebind to `--font-mono`/`--font-ui` at migration.

---

## 5. Color law

§1's reserved-hue law governs *when* color may appear; this section governs *how*.

- **Fill-grade vs text-grade.** The raw state palette is fill-grade (tints, bars, borders,
  ≥3:1 non-text uses). Any state printed as text ≤18px uses its `--ink-*` rung. This is the
  estate's deepest accessibility machinery — never bypass it with a literal.
- **Direction is never assumed from hue.** zh mode swaps `--up/--down` (红涨绿跌), light×zh
  re-keys the ink percentages, and the `.rrx/.igx` gauge remaps show how a *directional* gauge
  that happens to use health tokens gets scoped remapping rather than a global flip. New
  directional UI binds to `--up/--down`-derived tokens only — a literal green/red is a defect
  the zh audience sees inverted.
- **Health never flips.** `--ok/--warn/--act` encode safety, not direction.
- **One accent.** `--link` is the only wayfinding hue; hover glows, focus rings, active tabs,
  selected states all derive from it via `color-mix`. A second decorative accent is a defect.
- **Violet is lock-only** (packet §0). It never lands on data, charts, or states.
- **Quadrant hues** (`--q1..q4`) are the regime vocabulary and flip with zh; position markers
  within a quadrant frame use measurement ink, never a category hue (memory law: hue=category,
  ink=measurement; `--q1/--q3` swap under zh).
- **Tinted chips** derive from `--c` + `color-mix` (the shipped badge machinery). New chip
  states extend the `--c` assignment lists in theme.css — they do not mint hexes.

---

## 6. Iconography

The monoline set in `templates/_icons.html.j2` (24×24, `stroke=currentColor`, 2px-ish strokes,
3-column legibility budget at 13px) is the only icon language. DS-PR-0 promotes its base CSS
(`.ic-svg`, sizing, `.ic-spin`) into `theme.css` per the partial's own header note. Emoji are
never UI icons (doctrine §5.8) — they read as clip-art on white and render inconsistently
headless; the sanctioned uses of emoji are zero on migrated surfaces (the plain-English lane
glyphs 🟢🔵🏃🟠⚪ on the shipped action boards are grandfathered until their surfaces migrate
to the icon set — factory packets name this). Icons inherit ink from context — that is what
makes theme/zh flips free — so an icon never sets its own fill.

---

## 7. Motion law

Motion is a status channel, not garnish:

- **Live data pulses; settled data doesn't.** `.dtp-dot` animates only in live states —
  shipped, and now law: an animated element must encode a live/ongoing fact.
- **Hover lift** = `translateY(-1px..-2px)` at `--t-med/--ease-lift`, only on *clickable*
  containers. **Tabs and toggles never move** (shipped rule; prevents layout wander).
- **One breathing element per page maximum** — the primary CTA (`gbtn-cta`), desktop pointers
  only (`pointer:coarse` holds the resting state — measured main-thread cost, theme.css:482).
- **Reveals**: content entrance is opacity/8px-rise at `--t-med`, once, on section reveal;
  illus draw-on-reveal owns chart entrances. No parallax, no scroll-jacking (operator veto:
  active-only panels, no viewport hijack).
- **Reduced motion kills everything above by name** — including `::before/::after` sweep
  pseudos (memory law: a reduced-motion block that doesn't name pseudos ships dead sweeps).
- Durations/easings only from §2.2 tokens.

---

## 8. Chart styling

- **Display-tier charting = `lib/illus.py` + `illus.css/js`** (SSR SVG, draw-on-reveal ink,
  waterline dual-tint for zero-anchored series, honest null slots, theme/zh via CSS vars).
  Operator-mandated; compliance is 9/247 templates — the largest doctrine gap in the estate —
  so *every migration packet carries an illus line item* (factory §4).
- Series colors from §2.2 `--ser-*`; direction series from `--up/--down`; ≤4 series.
- Axis/tick text `--fs-micro` mono; gridlines `--line` at ≤50% alpha; no chart borders inside
  panels (the panel is the frame — `.chart{border-radius:8px}` stays for the legacy Plotly
  slates).
- **Plotly stays only on Tier-3 study surfaces** (real trading charts, labs) and on the
  charting stack; `--chart-bg` keeps legacy dark-rendered charts legible in light mode until
  their surfaces migrate to illus or the charting stack.
- Heatmaps: cell fill is fill-grade tint; cell text uses ink rungs; **1px gaps + track border
  in light** (neutral segments vanish on white — doctrine §5.8).
- Every chart answers a stated question in its caption position (eyebrow or `figcaption`), or
  it is decoration (§9 removal test).

---

## 9. Information density & progressive disclosure — page-composition law

The doctrine's GLANCE → HOVER → STUDY tiers (`docs/DESIGN_DOCTRINE.md` §1) made copy lawful.
This section makes **page composition** lawful. The failure mode it exists to kill, named: **a
dashboard is a briefing, not a museum of everything its engine knows.** Nearly every engine
output elevated into visible UI, first-level panels of equal visual importance, and internal
architecture leaking into the customer's cognitive model are the census-measured defects.

1. **Primary-question law.** Every page declares ONE primary user question (the registry
   carries it; the census §2 table seeded P0). The page's first content element answers it —
   the VerdictHero (§11) on decision surfaces, the board ladder on discovery surfaces, the
   plan cards on plans. If a module doesn't serve the primary question or a declared secondary
   job, it is not on the page.
2. **Above-fold budget.** At 1440×900: chrome + the answer + at most two supporting modules.
   At 390w: the answer within one swipe. (Packet §A/§B worked examples.)
3. **First-level section budget.** L1 sections per archetype are §10 law — default 5, hard
   ceiling 7 on any page ("the engine may know 400 things; the page may show seven"). Equal
   visual weight across L1 sections is itself a defect: the answer outweighs support (type
   scale + placement, per archetype layout).
4. **Tier-1 statistic test.** A number earns always-visible placement only if it passes all
   three: (a) it can change what the user does today; (b) it arrives with its meaning in plain
   words (doctrine Law 3); (c) it is not derivable from another visible number. Everything
   else is Tier 2 (LENS) or Tier 3 (detail/tab).
5. **The one-integer law** (the packet's count cure, generalized estate-wide). One canonical
   count per population per page, printed once; every other integer describing that population
   is a quote, a labelled slice, or a computed difference. Two modules disagreeing about the
   same quantity is the estate's signature defect (us_stocks stated its size six ways; macro
   printed two terminal rates in one sentence) — at review, a contradiction between two
   visible numbers fails the page, whichever number is right.
6. **As-of law.** One freshness stamp per panel (`.dtp`-family), one page-level session stamp
   in chrome. Duplicate timestamps merge. ~100 per-page `*asof*` variants are migration debt
   onto `.dtp-asof`.
7. **Receipts law.** Study IDs, `n=`, window specs, internal state enums live in LENS tips
   (`data-tip-*`, receipt line `data-tip-rc-*`) or Tier-3 pages — never at rest. The compliant
   null-disclosure form is plain-words-on-Tier-1 + receipt-on-Tier-2 (doctrine Law 5).
8. **Demotion rule + the caveat exception** (ratified census §5.3, packet §G.5, now law):
   when in doubt, demote to hover — **except a caveat that changes how the headline number
   should be read, which must sit beside the headline** (the macro dial-cap case). Demotion is
   for mechanics, never for honesty.
9. **Tabs / accordions / drawers.** Tabs = parallel *tasks* on one subject (dossier evidence
   groups); tab names are task words, state in the URL hash. Accordion/`<details>` = optional
   depth under one task (methodology, receipts). Drawer/sheet = cross-page utilities (alerts,
   settings). Never tabs for sequential narrative; never accordions as a dumping ground —
   an accordion's collapsed line must still say what's inside and why to open it. On mobile,
   tabs become a scrolled strip, never an accordion (packet §E).
10. **Raw tables** are Tier-2/3 material: behind a tab, a "table view" toggle, or a detail
    page. A table at L1 shows ≤8 rows + counted "See all N". Tables scroll inside their own
    container, never the page (no horizontal page scroll, any viewport, ever).
11. **Duplicate statistics across panels**: the second occurrence is removed or becomes a
    quote-link to the first ("47 setups — board ↑"). Constants never repeat per-row (doctrine
    Law 4).
12. **Empty / loading / stale / error are designed states** (§11 `.empty` family):
    loading = skeleton at true geometry, no words; empty = full-weight market-facing sentence
    with a mandatory why (`.empty-why`); stale = `.dtp` behind-state + one line; error = names
    what failed AND what still works, with retry — never a bare `—`, never pipeline telemetry
    ("appears after the first nightly run" is build-ops leaking into customer copy).
    **Loading ≠ empty is structural** (skeleton vs sentence).
13. **What gets removed rather than restyled.** At migration, a module is deleted from the
    page (capability preserved behind a link/tab/detail page) when it fails the Tier-1 test
    (rule 4) AND has no Tier-2 home, or when it duplicates another module's answer, or when it
    exists because the engine produces the number rather than because the user asked a
    question. **Deletion and demotion are design acts of equal rank with addition.** Every
    removal gets a named landing (the packet's demotion-landing-table pattern) — demoted, not
    deleted, is the default; deleted-with-no-landing requires the packet to say so.

---

## 10. Canonical page archetypes

Nine archetypes cover the estate. Each fixes: primary job, canonical layout, L1 budget,
disclosure pattern, mobile reduction, allowed primitives, and one **identity device** no other
archetype may borrow (anti-sameness, extending packet §G.6). The Terminal workspace keeps its
own doctrine (adjudicated divergence, census §3.4) and is listed only for mapping completeness.

| | Archetype | Primary job | L1 budget | Identity device |
|---|---|---|---|---|
| A | **Command Center** | "What changed; what deserves attention now" | 5 | two-column command layout + `.chg-row` stance rows |
| B | **Discovery Board** | "Which opportunities, at what stage, which can I act on" | 5 | the count ladder |
| C | **Instrument Analyzer** | "What is this thing; has it changed; what would change my mind" | 5 | decision header + dated lifecycle rail / task tabset |
| D | **Regime Dashboard** | "What regime am I in; what would change that read" | 6 | regime VerdictHero + "what we're watching" band |
| E | **Intelligence Desk** | "What is the desk seeing in this domain" | 6 | dated brief cards with graded source chips |
| F | **Research / Editorial** | "Read the work" | n/a (reading column) | measure-limited column + TOC rail |
| G | **Monitor** | "Keep me current on my names/alerts/news" | 4 | the change-log timeline (since-you-were-here) |
| H | **Marketing / Conversion** | "Should I trust this; what do I get; what happens when I click" | 7 bands | live dated product output as proof |
| I | **Utility** | auth, account, legal, 404 | 1 card | single-card focus, zero ambient |

**Canonical layouts** (desktop → mobile):

- **A**: full-width state band → 2/3 primary answer column + 1/3 rail → full-width band.
  Mobile: primary market + first 3 rows in one swipe (packet §A is the worked contract).
- **B**: header + ladder → filterable card grid (≤40) → groups band → context tabs → record.
  Mobile: ladder pinned, one lane via stance selector (packet §B).
- **C**: decision header → rail/what-changed → two-column quality/evidence (never re-blended
  on mobile — divided and re-labelled) → watching band → Tier-3 disclosure (packet §C/§E).
- **D**: VerdictHero (regime word + plain clause + dial/meter) → what-changed rows →
  2-col driver panels (≤4) → watching band → link-out tabs for depth. Mobile: hero + chips +
  first driver panel; drivers collapse to a swipe strip. Reference: `macro_reference.html`.
- **E**: desk header (one as-of) → lead brief (the one thing today) → brief cards (≤6, dated,
  source-chipped) → watch table (≤8 rows) → methodology link band. Mobile: lead + 3 cards.
- **F**: title block → measure column with pull-stats as `.callout` → TOC rail ≥1200w only.
- **G**: since-stamp header → change timeline grouped by day → managed-list table → quiet
  empty state ("quiet tape" vocabulary). Mobile: timeline only.
- **H**: proof-first hero (live artifact, dated) → 3-band value → plan/CTA → FAQ. Landing's
  15.5-screen scroll is the anti-pattern; ≤8 mobile screens.
- **I**: one centered card on canvas, `_public_nav` or bare brand, no aurora emphasis, no
  second CTA.

**P0 route mapping** (18 census rows): `/` H · `start.html` A · `macro.html` D ·
`us_stocks.html` B · `china.html` D · `hk.html` D · `confluence_screener.html` B ·
`research_vault.html` F · `plans.html` H · `products/*` H(×3) · Terminal 4 routes = workspace
(own doctrine) · `mastermind:portfolio_desk` G (its repo's lane). Beyond P0, by family:
per-market stock boards B; baskets/allocation/heatmaps B; sector/subsector/rotation/basket
detail + `stocks/<T>` + `/prophet/<T>` C; market/country/cycles/bonds/forex/commodities D;
intel/policy/altdata/forensics/capital-structure/smart-money desks E; reports/vault/foresight/
methodology/measurement/neural_web F; watchlist/alerts/news G; landing/plans/products H;
auth/account/legal/404 I.

**Dense-dashboard reference ruling (Wave-0 deliverable 6).** Candidates evaluated: `macro.html`
vs `china.html`. Measured (delta lane, factory §8 provenance): macro renders **13 first-level
sections** (regime hero, command scorecard, markets tiles, what-to-do, events, release radar,
fed path, sentiment, sector temperature, alerts, policy monitor, AI brief, where-next);
china renders **14** of nearly identical composition. Both are museums against this doc's
D-budget of 6. **macro.html is selected** as the reference: (a) it is the higher-scoring
candidate (20/30 vs 18/30) with the estate's best regime hero — the reference builds on
strength instead of entangling with china's open data-truth defects (regime named two ways,
policy in both directions — engine-lane work, not design); (b) it is P0 #3 and the estate's
main anonymous SEO entry — highest reach per pixel; (c) the two pages share the `mx4/mx5`
idiom family, so the reference transfers to china/hk mechanically as follower migrations —
china becomes the first Archetype-D consumer and the test that the reference generalizes.
The reference (`mockups/design_system/macro_reference.html`) compresses 13 L1 sections → 5
(hero+caveat · what changed · four drivers · watching band · named deep links), every demoted
module keeping a named landing.

**Path for the remaining ~290 registry rows:** DS-PR-1 (factory §5) adds `archetype` to
`config/product_experience/page_registry_overrides.yml` for every row, seeded from the family
mapping above; ambiguous rows (~a dozen desks) get adjudicated in that PR's review. From then
on the registry is the routing answer, and a page that can't be assigned an archetype is a
page that shouldn't exist (merge it into one that can).

---

## 11. Component system

### 11.1 Canonical inventory (compose these; builders never invent)

| Component | Canonical implementation | Disposition |
|---|---|---|
| PageShell / PageHeader | `_site_nav.html.j2` family + `.site-footer` + page h1 block; F.2 adds Plans/auth presence | **KEEP/EXTEND** |
| VerdictHero | **NEW `.vh`** — eyebrow · verdict word (`--fs-display`, state ink) · one plain clause ≤14 words · stance verb · one `.dtp` stamp · LENS receipt. Canonized from the macro gauge header / hk command panel / packet §C decision header | **NEW (DS-PR-0)** |
| Section header | **NEW `.sec`** — `.eyebrow` + h2 (`--fs-h2`) + optional `?` LENS tip + optional per-panel as-of slot; one anatomy for every panel title | **NEW (DS-PR-0)** |
| Surface / Panel | `.panel` (E1) / `.panel2` surfaces; `.card` as the clickable variant | **KEEP** — the one base |
| Metric | `.mtile` anatomy (label / value `--fs-num-lg` `.tnum` / delta with direction ink / micro tag) | **EXTEND** — promote as the Metric primitive |
| SignalCard | `.pvcard` + `pv_css()` (Prophet); generic signals = `.card` + stance chip | **KEEP** (Prophet-scoped) |
| DecisionRow | `.chg-row` (name · change clause ≤14w · stance verb · chevron) | **NEW** (packet PR-0) |
| Table | **NEW `.tbl`** — th `--fs-micro` caps `.08em` · cells `--fs-sm` `.tnum` · hairline rows · hover row tint · in-container scroll · ≤8 rows at L1 | **NEW (DS-PR-0)** |
| Tabs / FilterBar | `.tabset` (tasks, hash state; packet §E) · `.ladder` control form (packet §B) · `.segbtn` segmented | **NEW/KEEP** |
| Status / Freshness | `.dtp` family — the only freshness/session language; `.dtp-chip` states live/pre/warn/stale/behind | **KEEP/EXTEND** (rollout) |
| Tooltip / Evidence receipt | LENS (`data-tip-en/zh`, `data-tip-rc-*`) — the only popover | **KEEP** |
| ChartFrame | illus (`lib/illus.py` + `illus.css/js`) | **KEEP/EXTEND** (compliance sweep via factory) |
| Empty / Loading / Error / Stale | `.empty` + mandatory `.empty-why` (5 sanctioned causes, packet §F.3); skeletons at true geometry; `.dtp` behind-states | **NEW** (packet PR-0) |
| TierLock | `.mx-tier-gate` + F.1 slot contract + light ghost rule | **KEEP/EXTEND** |
| Callout | **NEW `.callout`** — quiet tint + 3px state rail + deepened ink (the light-safe highlight idiom); replaces accent-tinted highlight rows | **NEW (DS-PR-0)** |
| Detail disclosure | **NEW `.disc`** — styled `<details>`: summary states content + reason to open; used for methodology/receipts | **NEW (DS-PR-0)** |
| Icon | `_icons.html.j2` + base CSS promoted | **KEEP/EXTEND** |
| Buttons | `.gbtn` family (+`-cta/-quiet/-sm/-lg/-pill/-icon`) | **KEEP** |
| Count ladder | `.ladder` (packet §0 signature; B-only as headline device, C echoes as rail). **Naming caution:** `winner_health.html.j2` already ships a page-local `.ladder` (delta audit, factory §8) — PR-0 renames the primitive (`.mx-ladder`) or proves no leak before landing | **NEW** (packet PR-0) |

### 11.2 New-component discipline

A builder needing a non-inventory component escalates to the design lane; the component lands
in `theme.css` + the specimen page in the same PR that first uses it, with both themes + zh +
mobile shown. **The specimen is the registry of allowed components** — if it isn't on the
specimen, it isn't canonical.

### 11.3 The nine rival card systems — dispositions

| System | Disposition |
|---|---|
| `theme.css` `.card/.panel/.mtf-card` | **KEEP** — the base + sanctioned variants |
| `.pvcard` (Prophet) | **KEEP** — flagship-scoped |
| `landing.css` (`.matrix-card`, `.pcard`, its `:root` set) | **MIGRATE** onto theme tokens during the plans/landing reference builds (packet §D already orders this) |
| `macro-desk.css` (specificity reskin over 5 pages) | **RETIRE** at those pages' migration — reskins are how divergence compounds |
| `biocatalyst.css` (`--bci-*` fourth token root) | **MIGRATE** token root → theme tokens; keep layout classes |
| `capital_structure.css` `.cs-*`, `fundamental_forensics.css` `.ff-*`, `stock_seasonality.css` `.sx-*`, `market_memory.css` `.mm-*` | **MIGRATE** — rebind local tokens to theme tokens at each page's migration packet; classes may stay as scoped layout |
| `chat.css` `.glass-card` | **MIGRATE** onto `--glass-*` tokens |
| `navigation-refresh.css` `.fan-card` | **KEEP** (nav-internal, already token-bound) |
| `fundamental_forensics.css` `--ff-*` root (born post-census, 2026-08-11 — delta audit, factory §8) | **MIGRATE** token root → theme tokens; the freshest proof the ratchet is needed |

The as-of (~100 variants) and empty-state (~82 variants) consolidations ride the same packets:
rebind to `.dtp-asof` / `.empty` at migration, never as a big-bang sweep.

---

## 12. Light-mode design contract (component-level)

Light is judged as a design, not as "does it render" (doctrine §5.8). The rule of art
direction: **dark earns depth with luminance and restrained bloom; light earns depth with
structure — surface, border, whitespace, controlled shadow.** Component law:

| Component | Dark treatment | Light treatment (never mechanical recolor) |
|---|---|---|
| Card / panel | `--panel` on `#0f1115`, hairline `--line`, `--card-shadow` micro-edge | white on `#f7f8fa`, 16%-ink hairline, soft `--card-shadow`; canvas stays deeper than panel |
| Raised / nested | `--panel2` luminance step | `#eef1f6` tint step + hairline; shadow only if interactive |
| Glow / bloom (hover, CTA halo) | `color-mix(--link …)` soft bloom | **ring, not glow**: 1px `--link`-mix border + tight shadow; blooms become pastel stains on white |
| Accent rails / highlight rows | accent-tinted row fill | `.callout` idiom: ≤8% tint + 3px rail + deepened ink (highlighter smear ban) |
| Gradients / aurora | jewel-tone alphas (20/16/14%) | airy alphas (9/8/7%) — same geometry, lighter ink |
| Charts (illus) | ink strokes on transparent, waterline dual-tint | same geometry; series use light twins; gridlines from light `--line`; **no dark slates** |
| Legacy Plotly slates | native dark | keep `--chart-bg:#11151c` island until migrated (approved exception §16) |
| Heatmaps | saturated fill-grade cells | tint cells + ink text + **1px gaps + track border** |
| Tooltips / menus (glass) | dark glass + heavy drop | light glass block (shipped): brighter fill, airy shadow, crisp top sheen |
| Locked content | blur teaser | **ghost**: `blur(5px) saturate(.35) opacity≈.46` (promoted unscoped in packet PR-0) |
| Tables | hairline rows on panel | same + row-hover tint from `--panel2`; zebra only in dense Tier-3 tables |
| Hero surfaces | luminance field + verdict ink | structured white card or quiet tint band; verdict ink from light rungs; **no full-bleed color fields** |
| Status chips | tint + ink (shipped machinery) | identical machinery — the ink rungs re-key automatically |
| Focus ring | 2px `--link`-mix outline | same (shipped) — visible on white by construction |
| Shadows | broad, dark, low-opacity | smaller, cooler, lower-opacity (shipped `--popover-shadow` pattern) |

Acceptance for any migrated surface: both-theme screenshots; the light shot reviewed as a
design (would a stranger believe light was designed first?); the §5.8 idiom list checked by
name.

---

## 13. Bilingual law

- Every Tier-1 string ships an EN and a native-shaped ZH twin (`.l-en/.l-zh` dual-emit or
  builder lexicons). No EN state names inside zh copy; no translated text in `title=`
  (CI-guarded) — LENS `data-tip-zh` is the hover home.
- Direction inks flip (红涨绿跌); quadrants flip; health never flips; Prophet verbs rebind
  (all shipped). New directional UI must demo the flip on the specimen before ship.
- zh headings drop tracking; CJK stack leads; `--fs-*` ramp is shared (CJK reads larger at
  equal px — budgets in characters, not translated word counts).
- Layout must survive zh string widths (2-char stage words, wider verbs) — the packet's
  zh×390w geometry checks generalize: **every acceptance screenshot set is ×2 languages**.

---

## 14. Accessibility floor

- Text ≤18px: ≥4.5:1 on its actual painted surface (ink rungs exist for exactly this — the
  worst surface, not the average one, is the measure; tinted chips are darker than their panel).
- Non-text boundaries that carry affordance (button outlines, focus, segmented controls):
  ≥3:1 (the 2026-08-03 estate pass set `--line` and `--gbtn-brd` floors — do not lower them).
- Focus-visible ring on every interactive element (`:where(...)` low-specificity pattern).
- Hover is never the only path to content: LENS opens on tap; anything hover-revealed is
  reachable on touch and keyboard.
- Touch targets ≥40×40 effective; long-press never selects on icon controls (shipped).
- `prefers-reduced-motion` per §7; `pointer:coarse` de-animates breathing.
- Semantic structure: exactly one h1; panels head with h2 (4 of 13 P0 pages render zero h1
  today — migration packets carry the fix).

---

## 15. Responsive law

- Breakpoints: 900px (nav collapse — shipped), 760/640px (grid collapses — shipped patterns),
  390w is the design floor. Wide content scrolls inside its container; **the page never
  scrolls horizontally** (5 of 13 P0 pages fail today; every packet carries the check).
- Each archetype declares its mobile reduction (§10) as *deliberate re-composition* — never
  "the desktop stack, squeezed": reductions choose what survives the fold, and demoted modules
  get link-outs, not deletion.
- Density on mobile: L1 budget −1 (a 5-section desktop page shows 4 meaningful bands in the
  first two swipes); tables become row cards only when the packet says so.
- The nav sheet, chip strips, and stance selectors are the sanctioned mobile idioms; no
  hover-only affordances survive on touch.

---

## 16. Approved exceptions (closed list — extending it requires operator sign-off)

1. **The aurora backdrop** — the one ambient color; both-theme alphas fixed in theme.css.
2. **The landing hero gradient identity** — operator-vetoed as brand identity; the landing
   may keep its hero art direction (content law still applies to its copy/proof).
3. **Terminal divergence** — the Terminal keeps its own doctrine/theme (census §3.4
   adjudication); IA and vocabulary converge, pixels don't, until a post-launch program says
   otherwise.
4. **Plotly dark slates on Tier-3** study/lab surfaces + `--chart-bg` island in light.
5. **Bitcoin Vector / hub legacy pages** — the self-contained vector family mirrors glass
   values inline (theme.js/`_vector_polish` sync note); they migrate last (P3).
6. **`stocks/` SEO dossier shell** stays free/ungated (packet §E flag) — an access rule that
   shapes design (locks appear only on premium groups).
7. **Grandfathered lane emoji** on shipped action boards until those surfaces migrate (§6).

Everything else follows the law. "It was already like that" is migration debt, not precedent.

---

## 17. The executable specimen

`mockups/design_system/specimen.html` renders the constitution: tokens, type ramp, spacing/
radius/elevation, every canonical component in §11.1, the density laws as do/don't pairs, and
the archetype identity devices — side-by-side across dark/light (toggle), EN/ZH (toggle),
desktop/390w (frame toggle). It links the real `templates/theme.css` so it always reflects
current law, and carries the proposed DS-PR-0 tokens in a clearly-marked local block that is
deleted when DS-PR-0 lands. Builders inspect it before touching any customer surface; review
compares rendered work against it. It is a mockup — nothing imports it in production.

---

## 18. Red-team record

**PENDING.** This document is not frozen until an independent Opus red-team pass has reviewed
the full Wave-0 set (this doc, the factory doc, both mockups) and its actual findings and
dispositions are recorded here. No model approves its own critical design work; this section
is written only from the reviewer's real output, never in advance.

---

*Wave-0 provenance: census + IA + packet (#5401) as primary evidence; current-main delta audit
2026-08-12 recorded in the factory doc §8 (foundation files unchanged since census; `--ff-*`
root and `.ladder` collision found and dispositioned);
theme.css/dashboard.html.j2/_icons read directly. Operator directives honored: DESIGN_DOCTRINE
law, model-routing design lane, DNR:KILL-FUSED-COMPOSITE / DNR:KILL-PROPHET-POP-MERGE /
DNR:KILL-PUBLIC-INTERNALS, #3821 falsifier-language ruling, zh 红涨绿跌 conventions,
reserved-violet lock hue.*
