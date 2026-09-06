# F08 Portfolio / Alerts / Monitoring — reference compositions

**Operation:** `marketontology-f08-portfolio-alerts-20260826-fable-001` · macro#6819 · MAS-149
**Tier:** mockup / reference only. Nothing in production imports these files; no route, no
data store, no product code is touched. They exist to fix the **composition, hierarchy and
state vocabulary** of the monitoring surface *before* the first build wave, per the Sol ruling
recorded at `research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md` §10.

**Binding inputs:** `docs/DESIGN_DOCTRINE.md` (content law — wins on conflict) ·
`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` (visual/composition law) · the F08 architecture
freeze (product law) · `research/MARKET_ONTOLOGY_F08_ARCHAEOLOGY_CENSUS_2026-09-04.md`.

**Files.** `f08_refs.css` is the shared vocabulary; `f08_refs.js` is a theme + language toggle
and nothing else. Each sheet reads `?theme=dark|light&lang=en|zh` from the query string so all
four quadrants can be captured headless. Every sheet links the real `templates/theme.css`, so
they track shipped token law rather than a private copy.

---

## 0 · What was decided (read this before building anything)

**Archetype.** `monitor` (G) — primary job "keep me current on my names, alerts and news",
L1 budget 4, identity device the since-you-were-here timeline, mobile reduction "timeline
only". The four L1 sections are: **the answer** (hero) · **since you were here** (timeline) ·
**what you own** (holdings) · **what you're watching** (conditions). The surface lives in the
Terminal shell (freeze §9); the sheets render the shell as a labelled empty slot because it is
owned elsewhere.

**The signature: the watch rail.** Freeze §4 makes `last_attempt` and `last_success` two
separate displayed facts and §3 adds `source_asof` as a third. Most products bury all three in
a 10px grey corner stamp. Here the proof of watching is the **second-largest object on the
page**, directly under the verdict word, because "we are actually looking" is this product's
value and the honest place for it is the furniture, not a footnote.

One shared time axis (now at the right edge) carries up to three lanes — **Checks** (did the
evaluator run, did it succeed), **Data** (how old is the material we answer from), **Alerts**
(did the notification leave the building). A lane whose two marks coincide is calm and prints
"no gap". A lane whose marks separate draws the **span** between them, and the span *is* the
alarm. That is what makes stale and outage look different at a glance: **outage stretches the
Checks lane, stale stretches the Data lane, a delivery failure stretches the Alerts lane** —
and the calm sheets have no span at all.

**The denominator instrument: the coverage ledger.** A labelled row on the same left rail as
the lanes: a segmented bar (live / fallback / not covered / unresolved / unknown) plus the same
fact in plain words. An empty book shows an empty *track*, not an absent widget. Freeze §5 /
G2 are satisfied on the page, not in a tooltip.

**The four-state read vocabulary carries FORM as well as hue** (design system §5, "hue is never
alone"): `READ_OK` has no chip at all — calm wears no badge; `READ_OK_ZERO` is a hollow chip
("Nothing yet"); `READ_NO_COVERAGE` is a **dashed** chip ("Not covered") in provisional ink —
never calm, never outage; `READ_UNAVAILABLE` is a solid `--act` chip ("Can't read"); stale is a
solid `--warn` chip. Identity-unresolved is a dashed neutral chip ("Not identified").

**Copy law.** Glance tier only: plain verbs, no internal state names, no raw slugs, no
untranslated statistics, one as-of per panel, one merged footnote per panel. Falsifier and
refutation language is absent by construction — the event card's fourth row is **"What would
close it"**, never a verdict about a thesis. Every alert explains condition, affected
positions, direction, mechanism, timeframe, freshness, authority ceiling and notification
outcome, and every evidence disclosure ends with the authority line
`context_and_user_decision_support — context for your decision, never an instruction to trade`.
Internal ids, clocks, evaluator fields and dedup keys live **only** inside `<details>`
disclosures, which are keyboard-reachable by construction (hover is never the only path).

**Fixture.** AAPL 120 @182.30 (2024-11-12) · NVDA 40 @92.10 (2024-06-03) · MSFT 55 @388.00
(2025-02-20) · XOM 200 @104.55 (2025-08-14) · TM 80 @178.90 (2025-05-06) · a second AAPL row
10 @231.00 (2026-07-01) · PRIVCO 100 sh (unresolvable). **7 rows → 6 positions** (one duplicate
Apple row folded) → **5 included, 1 excluded**. That arithmetic is printed on every sheet that
has a book. Market prices are fixture values chosen to make the composition legible; every
sheet carries a persistent "FIXTURE DATA, NOT A LIVE BOOK" band so no artifact here can be
mistaken for a record.

---

## 1 · Theme art direction — the two directions, and what differs

Dark and light share information architecture, component semantics, spacing and type scales,
state meanings, ordering, copy and interaction. They deliberately do **not** share material
mechanism. Token substitution alone was never the light design.

**DARK — the watch floor.** Depth is built from **luminance**. The hero sits in a low radial
field on `#0f1115` with no border. Panels are `--panel` hairlines with no resting shadow;
grouping is a luminance step. Trouble comes *toward* you: a degraded panel lifts to `--panel2`,
takes a restrained inner rim and a very low outer bloom. The watch rail's axis is a bright
hairline, its span is a soft luminous field with an outer glow, its marks are discs sitting in
that light. Timeline dots are filled on a luminous spine.

**LIGHT — the printed watch log.** Depth is built from **structure**. The hero becomes a white
**masthead plate** on the cool `#f7f8fa` canvas with a hairline foot and a tight cool shadow —
a letterhead, never a tinted field, because a field on white is the documented stain. Panels
rest on shadow, not on luminance, and a degraded panel does **not** lift a tint step (that is
the highlighter smear); it takes the callout idiom — ≤8% wash, 3px state rail, deepened ink —
plus a tighter, cooler shadow. The watch rail's axis is *engraved* (hairline plus a white
under-highlight), its span is a **diagonal hatch inside a 1px state border** — a printed
measurement rather than a glow — and its marks are hard squares with a hairline. Timeline dots
are hollow rings; only the entry you have not read yet is filled.

### The mechanisms that intentionally differ

| # | Mechanism | Dark | Light | Why it cannot be the same |
|---|---|---|---|---|
| 1 | Hero ground | radial luminance field, no border | white masthead plate, hairline foot, cool shadow | a luminance field on white is a pastel stain (doctrine §5.8) |
| 2 | Panel grouping | `--panel` on `--bg`, luminance step to `--panel2` | white on a deeper canvas + hairline + shadow | panel≈bg is the flatness bug; light has no luminance headroom |
| 3 | Degraded emphasis | lifts to `--panel2` + inner rim + low outer bloom | stays white-ish, ≤8% wash + 3px rail + deepened ink + tighter shadow | an accent-tinted row on white is a highlighter smear |
| 4 | Watch-rail span (the signature) | soft luminous field + outer glow | diagonal hatch inside a 1px state border, no glow | a bloom on paper reads as a smudge; a hatch reads as a measurement |
| 5 | Watch-rail marks | discs with a soft halo | squares with a hairline and a 1px drop | a haloed disc has nothing to sit in on white |
| 6 | Watch-rail axis | bright hairline at 13% text | engraved: `--line` hairline + white under-highlight | white needs a shadow edge to read as a rule, not a scratch |
| 7 | Coverage ledger | butted saturated segments on a dark track | 1px gaps + 1px track border + tint bed under a denser hatch | neutral and hatched segments vanish on white — an excluded slice that looks like empty track is the exact disclosure failure the bar exists to prevent |
| 8 | Timeline spine + dots | luminous spine, filled dots, halo on unread | engraved spine, hollow ring dots, filled only when unread | ink-on-paper: a filled dot is the emphasis, so it must be spent on the unread one |
| 9 | Superseded entry (sheet 09) | demoted by dropping luminance (`opacity .68`) | demoted by lifting ink toward the paper (ink mixed 74% toward `--panel`) | opacity on white greys the *panel* too; light demotes by ink weight |
| 10 | CTA hover | soft `--link` bloom | **ring**, not glow: a tighter border and a flat tint | blooms become pastel stains on white (doctrine §5.8) |
| 11 | Resting elevation | none — dark rests on luminance | `0 1px 2px` + `0 12px 26px -20px` cool shadow | the two themes never carry the same resting elevation mechanism |

Unchanged across themes by design: hierarchy and reading order, the L1 section set, the type
ramp and weights, the state vocabulary and its forms, word budgets, all copy, the 900px and
430px breakpoints, the archetype-G mobile reduction, focus rings, and every disclosure.

**Direction ink** binds to `--up`/`--down`, so 红涨绿跌 flips gains to red under `data-lang="zh"`
in both themes; **health ink** (`--ok/--warn/--act`) never flips, because an outage is an outage
in every language. Both behaviours are visible in the evidence set.

---

## 2 · The ten sheets

Every row's per-theme treatment is the §1 system applied; the column below names what is
**specific to that state**.

### 01 · `01_loaded_material_change.html` — loaded book, one material new change (the hero)
The composition the other nine are variations of, and the G7 proof. First viewport at
1440×900 answers, in this order: **portfolio state** (verdict "Steady", value, day and
since-bought moves) → **the most material new change** (timeline lead, "Oil supply tightened",
09:12, unread ring) → **which holdings** (Exxon 22.5% direct, Nvidia 7.5% second-order, as
weight chips) → **why it matters** (direction / how it travels / timeframe / what would close
it, in plain words) → **confidence and coverage limits** (the watch rail with no gap in any
lane, and the coverage ledger reading 6 positions from 7 rows, 5 valued, 1 unidentified) →
**one next action** ("Watch this path", a monitoring act, never a trade).
· **Dark-specific:** the calm hero field is achromatic — a market event is not health, not a
single direction and not provisional, so under the reserved-hue law it earns attention from
weight and placement, and the one accent is spent only on the unread marker.
· **Light-specific:** the masthead plate carries the whole answer block, so the timeline panel
below reads as the second document on the desk rather than a continuation of the header.

### 02 · `02_empty_calm.html` — valid empty portfolio (calm is lawful here)
`READ_OK_ZERO`. Calm with **proof-of-run**: the Checks and Data lanes still run and still print
both clocks, which is the whole point — a zero book is not an unchecked book. The coverage
ledger shows an **empty track** with "0 positions from 0 rows. Nothing excluded, nothing
folded, nothing hidden." The timeline is a full-weight sentence with a mandatory why
("it is empty because your book is empty — not because a check failed") plus an
"already working" line. Loading would be a skeleton; this is a sentence — the two are
structurally different states.
· **Per theme:** the empty coverage track is a dashed hairline in dark and a dashed hairline on
a white bed in light, so it never reads as a failed render.

### 03 · `03_stale_holdings.html` — old `source_asof` renders STALE, never calm ⚠ load-bearing
Verdict **"Out of date"**. The Checks lane is clean and green; the **Data lane carries the long
span** — the source answers every request and keeps returning the same 16:00 vintage, so the
run is `outcome=partial` and the served `source_asof` is re-stamped to the fallback vintage
(the `build_bonds` defect, cured on the surface). Today's move prints **"not available while
prices are old"**, never a bare dash and never a stale number wearing a live label. Two price
conditions show **Paused**, and the copy says a paused condition is still your condition. The
coverage ledger's basis segment is `fallback`, not `live`.
· **Dark-specific:** the amber span glows under the rail; the two degraded panels lift a
luminance step.
· **Light-specific:** the amber span is hatched inside a border and the panels take the amber
callout wash — the page reads like a document stamped "as of yesterday", not like a page
someone tinted.

### 04 · `04_source_outage.html` — monitoring degraded, last successful check named ⚠ load-bearing
Verdict **"Not watching"** — two plain words that cannot be mistaken for calm. The **Checks
lane** carries a 3h 12m span between a hollow last-clean-read mark at 06:29 and a **failed**
attempt mark (an ✕ disc) at 09:41; the Data lane is frozen with it; the Alerts lane is quiet and
says so. The book value demotes to muted with a **"Last known · 06:29"** chip and the sentence
"we are not updating this figure". The coverage ledger goes to a hatched unknown bar — an
unreadable book is *unknown*, not "100% bad" — and prints the last-known denominator labelled
as last-known. Per-holding values are **withheld**, deliberately: three-hour-old numbers sitting
in a table look current. The error names what failed **and** what still works, with a retry.
· **Dark-specific:** the red hero field and the panel rim make the outage arrive out of the
dark. · **Light-specific:** no field at all — the plate stays white and the alarm is carried by
ink, hatch and rail, which is what keeps a light outage from reading as decoration.

### 05 · `05_partial_identity.html` — excluded AND counted, denominator on the page
Verdict **"Partly covered"**. The book moves to the **main column** because it is the subject
(a deliberate per-state composition change, and the one that also keeps the subject inside the
mobile reduction). PRIVCO carries a dashed **"Not identified"** chip, "not valued" in both
numeric columns, and a *What we tried* disclosure that ends with what we did **not** do —
value it at zero, drop the row, or quietly shrink the denominator. Toyota carries a dashed
**"Not covered live"** chip with its own disclosure: identity resolved, no intraday line, valued
from the previous close, in book value but out of today's move — which is why the day figure
reads "+851.00 today — Toyota is not in it". The coverage ledger runs three segments and ends
"Every total on this page covers **5 of 6**".
· **Per theme:** this is the sheet where the light hatch tuning matters most — the two absence
segments sit on a tint bed under a denser hatch so neither can be read as empty track.

### 06 · `06_notification_failed.html` — typed `failed`, retried, never reads delivered ⚠ load-bearing
Verdict **"Not delivered"**. The Checks and Data lanes stay green and the **Alerts lane** takes
the span — the failure is scoped, visibly, to the telling rather than the watching, and the
book value is printed normally with "your book is fine — only the notification failed". The
fired alert row carries **"Not delivered · retry 2 of 5"** and the line "you are reading this
because it is on your timeline, not because it reached you". A second message shows
**"Waiting to send"** — a fire with no terminal delivery state renders pending and is
distinguishable from delivered. Delivery state sits on the condition it belongs to, not in a
separate log. The disclosure carries the mailer status, the `idem_key` derived from the fire
event, and the rule that retry drains the outbox and never re-evaluates.

### 07 · `07_duplicate_event.html` — duplicate folded once, disclosed, rendered once
Verdict "Steady": a duplicate is not a degraded state, and pretending otherwise would be its
own dishonesty. The lead event carries a **"Seen twice · shown once"** chip and a disclosure
naming both arrivals, the keep-first rule, and the three things a repeat can never do (mint a
second entry, re-fire, re-send). The holdings panel carries the *other* fold — two Apple rows,
one position — as its own disclosure with the weighted cost and the reason it matters
(a total over raw rows double-counts your Apple weight). Two different fold laws, both printed.

### 08 · `08_resolved_condition.html` — disarm → re-arm as a visible lifecycle
Conditions move to the **main column**. The fired condition shows a **lifecycle rail**
(Set → Watching → Fired 08:12 → **Closed** → Re-arm) drawn in **weight and fill only, never
hue**, per the design system's rail law. Its footer says plainly that a closed watch stops
checking, that re-arming clears the fired stamp and starts a fresh watch, and that the fire
that already happened stays on the timeline either way. Two re-arm affordances (same level /
new level) are offered as *monitoring* actions. The still-running conditions show their own
rails, so "closed" and "watching" are distinguishable without reading a word.

### 09 · `09_replay_correction.html` — append-only record, correction linked on the same timeline
Verdict **"Corrected"**. The 09:03 correction leads and carries a dashed **"Corrects the 08:12
entry below"** link; the 08:12 entry stays on the timeline, visibly **superseded**, with
"kept on your record". Nothing is deleted and nothing is edited in place. The disclosure states
the restatement (92.40 → 91.15), the effect on the record, the effect on the watch (re-armed at
the user's own level), and the effect on delivery (**no second send** — a correction is a
record, not a new alert). The 09:20 replay is deliberately **not** a timeline entry: it fired
nothing and sent nothing, so it is a receipt below the timeline rather than news above it.
· **Dark-specific:** superseded demotes by luminance. · **Light-specific:** superseded demotes
by lifting the ink toward the paper, because dropping opacity on white would grey the panel too.

### 10 · `10_signed_out.html` — 401 is not an empty book
The one sheet that is **not** the monitor composition: archetype-`utility` focus — a single card
on the canvas, zero ambient in both themes, no watch rail, no counts, no numbers. The card's
whole job is to keep three states apart: signed out (401), empty book (200 with zero rows,
sheet 02) and unreadable source (503, sheet 04), with the disclosure naming all three and the
line "collapsing any two of them is the defect this sheet exists to prevent". It still tells the
user that monitoring keeps running on their account while they are away.

---

## 3 · Responsive

| Viewport | Composition |
|---|---|
| **1440** | hero across the full measure; below it a 1.55 / 1 grid — timeline in the main column, holdings over conditions in the rail (sheets 05 and 08 swap which side holds the subject) |
| **1024** | same two columns at 1.32 / 1; the watch rail's label gutter narrows to 78px; nothing re-flows or drops |
| **390** | the archetype-G reduction, implemented as re-composition rather than a squeezed desktop: the hero (verdict, value, watch rail, coverage) and the **timeline only**, then counted link-outs — "Your holdings · 6 positions", "What you're watching · 3 conditions" — so every demoted module has a named landing. Watch-rail lanes stack label-over-track; the mechanism block collapses to label-over-value; the "since you bought" column drops out of the table; the shell slot is hidden. No page scrolls horizontally at any width; wide tables scroll inside their own container. |

Accessibility floor held: exactly one `h1` per sheet, panels head with `h2`, focus-visible rings
on every control and disclosure, evidence reachable by keyboard (a `<details>`, never a hover),
touch targets ≥40px effective, `prefers-reduced-motion` kills every transition and every
pseudo-element by name. Nothing on these sheets animates — motion is a status channel and
nothing here is live.

---

## 4 · Evidence

`shots/` — filenames are `<sheet>_<viewport>_<theme>_<lang>.png`, captured headless at
device-scale 1. Mobile frames are captured through a 390px iframe harness (headless Chrome
clamps `--window-size` below ~500px, which silently renders a wider layout and clips it — the
harness makes the 390 frames real rather than cropped), so the 390 files show the true 390 CSS
viewport inside a grey surround with the viewport printed above it.

- Sheets **01, 03, 04, 06** (the load-bearing degraded set): 1440×900 and 390 × {dark, light} ×
  {EN, ZH} — 8 frames each.
- Sheets **02, 05, 07, 08, 09, 10**: 1440×900 dark·EN and light·ZH; 390 dark·ZH and light·EN —
  4 frames each, covering all four theme × language quadrants across the two viewports.
- Tablet: `01_1024_*` and `05_1024_*` in dark·EN and light·ZH.

**Measured, not eyeballed.** A DOM probe ran all 10 sheets × {dark, light} × {EN, ZH} at a
narrow and a wide viewport (40 combos) and asserted, per combo: zero horizontal overflow
(`scrollWidth − clientWidth == 0`), exactly one language rendered (visible `.l-en` and `.l-zh`
counts are N and 0, never both), `data-theme` and `data-lang` resolved as requested, a painted
`body` background in both themes, and exactly one `h1`. **40 checked, 0 failures.** That probe
is what caught the one real defect in this set: the hero plate's ±28px bleed exceeded the
container's 16px gutter at narrow widths and pushed the page 12px past the viewport on nine of
ten sheets — a horizontal page scroll that reads as nothing in a screenshot. The plate's
horizontal inset now tracks `.f8`'s padding at every breakpoint. Static checks: no `title=`
attribute anywhere (translated text in `title=` is CI-guarded), no emoji, no hex literal
outside comments.

---

## 5 · What a build wave inherits, and what it must still decide

**Inherited (do not re-derive):** the archetype and its four L1 sections; the watch rail as the
proof-of-run instrument and its three lanes; the coverage ledger and the folded-position
arithmetic; the four-state read vocabulary and its forms; the verdict-word vocabulary; the
evidence-disclosure boundary; the two art directions and the eleven mechanism differences; the
390 reduction and its link-out landings; all Tier-1 copy in both languages.

**Still open (not decided here, and not decidable here):**

1. **Component landing.** These sheets use page-local `.f8-*` classes at mockup tier. Production
   must land the new primitives under the `.mx-*` namespace in `templates/theme.css` plus the
   specimen, in the PR that first uses them (design system §11.2). The watch rail and the
   coverage ledger are **new components** and go to the design lane, not to a builder, for that
   landing; everything else maps onto existing primitives (`.panel`, `.mtile` anatomy, `.dtp`
   freshness family, the `.mx-empty` family, `.mx-disc`, `.gbtn`).
2. **The metric adoption matrix** (freeze §1) is still the V2 entry gate. These sheets show
   book value, cost basis, day move and position weight only — quantities that need no risk
   library. No concentration, factor, liquidity or annualised metric appears anywhere here,
   deliberately: a builder may neither fork nor invent a formula before the matrix is ratified.
3. **Freshness budgets.** The sheets print a 20-minute price budget and a ~5-minute check
   cadence as fixture values. The real budgets per lane, and the delivery drain's user-visible
   latency budget, are V4 packet decisions (freeze §8) — the *display* of a budget is fixed
   here, its value is not.
4. **Intraday receipt sink.** Whether the intraday lanes get a receipt path in the workflow
   commit whitelist, or are declared unreceipted, is an operator/DEC decision (freeze §4). If
   unreceipted, the Checks lane may not claim intraday resolution and the copy on sheets 01 and
   03 must degrade to the nightly cadence it can actually prove.
5. **The `.dtp` reconciliation.** The watch rail overlaps the shipped `.dtp` freshness family in
   subject but not in shape (`.dtp` states one clock; the rail states two or three and the span
   between them). Whether the rail extends `.dtp` or sits beside it is a design-lane call at
   component landing.
