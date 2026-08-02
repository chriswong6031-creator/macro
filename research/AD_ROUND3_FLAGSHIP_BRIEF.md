# Round 3 — the flagship X flight (written brief, pre-mockup)

**Status:** WRITTEN DRAFTS ONLY — no pixels exist yet. This is §8 steps 1–2 of
`research/AD_MASTER_PAPER.md` (taste corpus read, concepts + copy locked before any
mockup), commissioned by the operator 2026-08-02: *"the previous ad designs were too
broken, and all over the place. truthfully we just want 1–2 really good ads."*
**Owner:** studio (creative) × operator (taste gate). Nothing here runs without
`ad_review.record(...)` approval (H-1 / AG-7).

**Amended 2026-08-02 (same day, operator corrections before build):** copy re-locked
for retail simplicity — see the five rulings at the end of §3. Round-3 mockups are
built against the amended copy in §4/§5/§7, not the original draft.

**The ask, verbatim reduced:** one primary ad on **Prophet + macro dashboard + sector
rotation**, positioned as an **institutional-grade intelligence platform**; a supporting
**post** with hook, core features, the **launch discount (up to 50% off)** and a
**7-day free trial** CTA. Goal chain: impression → attention → click → trial →
long-term subscription.

---

## §1 Diagnosis — why three rounds produced zero running ads

The failure mode changed each round; the lesson compounds:

1. **Round 1 (6 ads, 2026-07-27) — rejected as a set.** Website-section fragments at
   540–720px: no identity, no offer, no CTA. Fixed by AG-1/AG-2/AG-3.
2. **Round 2 (13 concepts × 31 renders, #3910) — gate-compliant, never approved.**
   Every gate passed, and the operator was handed a *portfolio to curate* instead of a
   *decision to make*. Thirteen concepts is a museum; nobody hangs a museum on a feed.
   Volume also has spend physics against it: a small budget split 13 ways never reaches
   the n-floor (100 conversions/arm, masterplan stats law) on any arm — the shotgun is
   *statistically* wrong, not just aesthetically.
3. **The codex X flights (#3877 → #3883 → #3894) — three full replacements in three
   days.** 20 creatives, then a "Category campaign" replacing them, then a hero+carousel
   set replacing that. Churn instead of refinement; none carry an approval in
   `data/marketing/ad_central/reviews.jsonl` (which today contains only round-1
   rejections — zero approvals on record, ever).

**Round-3 discipline, drawn from all three:** ship **two creatives, one axis of
difference**, both fully gate-compliant, both built to be *the* ad rather than a
candidate. Refine the survivors; never restart the set.

---

## §2 Strategy — one pain, one promise, two temperatures

### The pain (the operator's words, sharpened into one sentence)

Retail's problem is not intelligence, it's **directionlessness**: a 100-ticker
watchlist, no idea what to buy, when, at what price, or when the whole tape is
dangerous. They are drowning in content and starving for **decisions**. Institutions
have systems — screens, signals, flow desks, risk frameworks. Retail has vibes.

### The promise (what we can honestly deliver)

The whole platform compresses to: **engines re-read the entire market every night and
hand you graded decisions by morning.** Prophet's card *is* a decision rendered as UI —
ticker, BUY/WAIT verb, 0–100 edge, exact entry zone, stage. "We shed light on what is
dark" is the emotional register; "your watchlist is already read when you wake up" is
the concrete one.

### The one-glance argument (what the ad must do in 3 seconds)

Show them **the decision, not the data**. Round 2's compositions were breadth-first —
fans of widgets proving we have *lots of stuff*. The stranger doesn't want lots of
stuff; they want *the answer*. So the flagship puts **one oversized Prophet card** —
verb, edge, entry zone — as the hero, and pushes breadth into chips and post copy.
This is the anti-"all-over-the-place" rule applied *inside* the canvas, not just to
the campaign.

### Two temperatures, two creatives

- **Signal-seekers** (most retail, hotter): want to be told what to buy. → **Ad A**,
  the Prophet decision card, dark terminal plate.
- **System-skeptics** (burned before, colder, higher LTV): distrust "signals," respect
  *process*. → **Ad B**, the rotation/macro desk view, calm paper mode.

Same typeface, same tokens, same offer bar — one company, two doors. A vs B is also a
clean two-arm test the budget can actually adjudicate.

### Why honesty is a conversion feature here, not a constraint

The trial converts to a *subscription* only if the product matches the ad. An ad that
promises alpha attracts churners; an ad that promises **a nightly-rebuilt desk with a
public track record (wins and losses)** attracts subscribers. AG-8 is ROI policy, not
just ethics.

---

## §3 Claims inventory — what we may say (re-verified on the live landing, 2026-08-02)

| Say it as | Backed by |
|---|---|
| "Institutional-grade" (quality claim) | positioning language; §6 "$24,000 desk" comparative row (public institutional terminal list prices, debranded) |
| "Rebuilt nightly" / "your edge, rebuilt nightly" | nightly pipeline; landing as-of tags |
| Buy · Near · Wait · Hold · Avoid; 0–100 edge; four-stage lifecycle; exact entry zones | landing Prophet section (`#f-prophet`) |
| "Graded in public — wins and losses" | Track record & autopsies row (free tier, pricing matrix) |
| "Sector rotation in four plain-word lanes" / "34 themes" | Theme Rotations section; lanes BUY NOW / ALMOST READY / TAKE PROFITS / STAND ASIDE |
| "Macro dashboards: US · China · HK · Canada · global" | pricing matrix, dashboards row |
| "2,700+ stock dossiers" | pricing matrix, dossiers row |
| "Mastermind AI analyst" | landing Mastermind section |
| "356 tracked funds · insider & Congress desks · intraday options flow" | landing Smart Money / matrix rows |
| "Advanced charting — in the browser, nothing to install" | Terminal section; 21 core + 31 advanced modules |
| "7-day free trial" | Pro CTA: "Try Pro free for 7 days" |
| "Launch offer: up to 50% off" | Pro $149/mo monthly → $75/mo annual (49.7% ≈ "up to 50%"); Essential $99 → $75 (24%) — "up to" is load-bearing |
| "SAVE $888 A YEAR" (Pro) | $1,788 monthly-rate year vs $900 founding annual (landing badge) |
| "2,000 founding memberships · $900/yr locked in for as long as you stay" | founding block (availability-framed; enforced #3856) |

**Ruled OUT — the operator's candidate hooks that cannot ship:**

- **"Investment signals used by quant firms"** — a *usage* claim; quant firms are not
  our users. AG-5 fails it, full stop. The compliant adjacent truth is the comparative:
  *"Institutions pay $24,000 a year for desks like this"* (passported) or
  *"institutional-grade signal engineering, at a retail price."* Proposed §5 hardening:
  ban "used by [funds/institutions/professionals]" claims explicitly.
- **"AI stock signals"** — house law A7: LLMs never originate signals; ours come from
  statistical engines. The landing's own split is the model: *engines* grade signals
  ("rebuilt nightly by engines that check each other's work"), the *AI analyst* is
  Mastermind. Ads say "daily graded stock signals" / "intelligent stock signals" +
  "AI analyst included" — never "AI-generated signals."

**Operator rulings, 2026-08-02 (retail-simplicity pass — all copy below is post-ruling):**

1. **No builder jargon for freshness.** "Rebuilt nightly" / "every night" assumes the
   reader knows the site runs on a nightly build — they don't. Signals freshness is
   said as **"updated every trading day"** / "daily"; the word **"live"** is used only
   where it is literally true (live options flow, live charting) — signals themselves
   are daily, and we don't claim otherwise.
2. **The 50% goes upfront.** The launch discount is a hook, not a footer — it appears
   in the first line of post copy and as a flag at the top of the canvas, not only in
   the bottom offer bar.
3. **No geography.** US-only targeting for now — no "US · China · HK · Canada" lists,
   no language/coverage talk.
4. **No "public record / graded in public / forward ledger" talk in ads.** Users don't
   care, and it has become the house style of vibe-coded finance SaaS — it reads AI.
   (The track record stays a *product* surface; it just isn't ad copy.)
5. **No "13F".** Retail doesn't know the form number — say **"institutional flow"** /
   "what institutions are buying." General rule behind all five: customers are retail;
   reduce complexity, keep every word plain.

**R3.1 critique rulings (2026-08-02, on the first-draft renders — scores: taste 8,
style 6, content 5, structure/positioning/illustration 2):**

6. **The illustration is the centerpiece and must tell a story** — cards may never sit
   as scattered decoration. Flagship = a stacked deck of Prophet cards (many signals,
   daily); rotation = lane board flowing into a Prophet card (sector turns → stock
   gets graded).
7. **One offer, said once.** CTA = `Start 7-day free trial`; price cell = struck
   $149 → $75/mo with `LAUNCH RATE · LOCKED IN WHILE YOU STAY`. Dead: the separate
   7-DAY cell, "Try Pro free", "THEN FOUNDING RATE", "ANNUAL".
8. **Dead weight removed:** feature chip rows, the micro-footer (advice line, founding
   count, domain), the 628 kicker pills, "with an exact entry zone" in sublines, the
   ghost-trail chips. 1080s keep the small catline.
9. **The flagship headline is the operator's motto:** `KNOW WHEN TO BUY` /
   `KNOW WHAT TO BUY` — promise-of-value, answers both retail pain points instantly;
   the old "Daily stock signals. Institutional grade." demotes to the subline idea
   ("Institutional-grade signals on every stock — buy, wait or avoid, updated every
   trading day.").
10. Theme names on canvas must be widely known: the moving row is **Semiconductors**
    (verified live theme), not Payments.

---

## §4 Ad A — "THE CALL" (flagship — build this)

**Registry row:** `call` · class: category × ritual · mode: **dark plate + faded candle
field** (§4.5) · canvases: **1200×628** (X website card, primary) + **1080×1080**.

### The picture, zone by zone (1200×628; the 1080×1080 stacks the same zones vertically)

```
┌────────────────────────────────────────────────┬───────────────────────────┐
│ ◆ MASTERMINDX                ⟨LAUNCH — 50% OFF⟩│    ⌈REZI · NEAR · 83⌉     │
│                                                │   ⌈CPAY · NEAR · 90⌉      │
│  KNOW WHEN TO BUY                              │  ⌈ARLO · NEAR · 99⌉       │
│  KNOW WHAT TO BUY   ← gradient line            │  ┌─────────────────────┐  │
│                                                │  │  BUY   ·  $104.27   │  │
│  Institutional-grade signals on every          │  │  ▂▃▅▆█ sparkline    │  │
│  stock — buy, wait or avoid, updated           │  │  SBUX  ·  EDGE 89   │  │
│  every trading day.                            │  │  ●●●○ stage: Ready  │  │
│                                                │  │  ZONE $102.60–104.30│  │
│                                                │  └─────────────────────┘  │
├────────────────────────────────────────────────┴───────────────────────────┤
│  $149→$75/mo · LAUNCH RATE — LOCKED IN   [ Start 7-day free trial ]        │
└────────────────────────────────────────────────────────────────────────────┘
   (the deck of graded calls IS the ad: many signals, fresh daily — R3.1 §6)
```

- **Ground:** `#0b1120`, §4.5 candle field at 10–16% opacity masked away from the text
  column. Dark is doing two jobs: it reads *terminal/institutional*, and it pops
  against X's white/black feed chrome where round-2's porcelain concepts would blend.
- **Hero card (right ~45%):** ONE oversized `prophet-card`, −2° tilt, `--sh-lift`
  shadow, redrawn at ad scale. Data is the landing showcase's **SBUX** row — the only
  `verb: buy` card in the public demo set *and* a household name: a stranger
  recognizes Starbucks in 0.3s where VCTR buys nothing. Card carries the site's small
  `demo` as-of tag (AG-5).
- **Depth slivers:** one rotation-lane chip (`ALMOST READY`) and one gauge arc sliver
  behind the hero, identity atoms only (taste corpus: no amputated pills, nothing
  half-covered). This is how the ad touches all three commissioned pillars — Prophet
  dominant, rotation + macro present — without becoming a collage.
- **Headline (R3.1 §9 — the operator's motto):** `KNOW WHEN TO BUY` /
  `KNOW WHAT TO BUY` — caps, Inter 900, gradient on line 2. Promise-of-value: both
  retail pain points answered before the first comma.
- **Launch flag (ruling 2):** violet pill `LAUNCH — 50% OFF` top-right in the brand
  bar — the discount is visible before the fold of the first glance.
- **Subline:** `Institutional-grade signals on every stock — buy, wait or avoid,
  updated every trading day.` (13 words.)
- **Illustration (R3.1 §6 — the centerpiece):** the Prophet card STACK — SBUX BUY card
  fully legible in front, three real graded rows dealt behind as complete identity
  bars (ARLO · NEAR · 99, CPAY · NEAR · 90, REZI · NEAR · 83). The stack says "a fresh
  book of graded calls, every day" without a word of copy.
- **No chips, no micro, no 628 kicker pill** (R3.1 §7–8). Offer bar: struck $149 →
  $75/mo + `LAUNCH RATE · LOCKED IN WHILE YOU STAY` + single CTA
  `Start 7-day free trial`.
- **Offer bar:** standard AG-6 block. Because the hero quotes an actionable entry zone,
  **AG-8 fires**: the micro-line swaps "allotment shrinks daily" for **"Research tools —
  not investment advice."** while keeping the availability-framed founding count — both
  gates satisfied in one line: `2,000 founding memberships · Research tools — not
  investment advice · mastermind-x.com`.

### Why this is the flagship (the reasoning, not the vibes)

1. **The card is the pain's answer made visible.** Directionless → here is a ticker, a
   verb, a price zone, a grade. No copy could say it faster than the UI does.
2. **Headline sells the category and the cadence, plainly.** "Daily" gives the reader
   a *reason to return every day* — the retention-compatible expectation (§2) — in a
   word any stranger parses; "institutional grade" is the positioning ask verbatim.
3. **One focal point.** The direct composition-level fix for "all over the place."
4. **Product-true everything** — tokens, Inter, real widget idioms, demo-tagged data:
   the click lands on a site that looks exactly like the ad (message match = lower
   bounce, better X relevance scoring).

---

## §5 Ad B — "THE ROTATION DESK" (support — build this second)

**Registry row:** `desk-rotation` · class: pain flip / breadth · mode: **paper**
(porcelain `#f7f8fa`) · canvases: 1200×628 + 1080×1080.

### The picture

Porcelain ground, dealt-scorecards signature (§4.4): hero is the **`lanes-board`** —
four plain-word lane columns (**BUY NOW · ALMOST READY · TAKE PROFITS · STAND ASIDE**)
with 2–3 real theme chips each (landing demo set, XLE 74 family), drawn large enough
that the lane names are readable at 25% zoom — the lane names *are* the copy doing the
work. Fanned behind at ±3°: the `gauge-card` (57 · Mixed tape · stance line verbatim:
"watch, don't chase") and a `prophet-card` sliver. Brand lockup top-left, standard
offer bar bottom. No levels quoted anywhere → standard AG-6 micro (allotment clause
stays; no advice line needed).

- **Headline:** `See the rotation before your watchlist does.` (7 words) — round 2's
  strongest pain-flip line, deliberately *reused*: R2 was never rejected per-ad; the
  rejected shape was thirteen-at-once. Salvaging the best single line into a focused
  flight is what learning from the corpus looks like. (Alternative if the operator
  wants breadth explicit: `Macro to sector to stock. One nightly read.` — 8 words.)
- **Sublines:** 628 `Every theme sorted into four plain-word lanes — updated daily.`;
  1080 `Money changes lanes daily — and the stocks inside get graded: buy, wait or
  avoid.`
- **Illustration (R3.1 §6 — the two-beat story):** the lane board (moving row =
  **Semiconductors 64**, one lifted chip + arrow into BUY NOW — ghost trail deleted)
  flowing into the **full VCTR Prophet card** as co-hero: "the sector turns → the
  stocks inside get graded." Prophet blended in because rotation alone doesn't solve
  the pain (R3.1).
- **No chips, no micro, no 628 kicker pill.** Same consolidated offer bar + launch
  flag as Ad A.

### Why it exists (and why paper mode)

It catches the **system-skeptic** Ad A slides off: the reader who flinches at "signals"
but leans in at *process* — lanes, regimes, rotation. Paper mode is the landing's own
face: calm, institutional, and deliberately the visual opposite of Ad A so the flight
tests **decision-card vs system-view** — one axis, adjudicable. It also directly
carries the operator's #2 and #3 pillars (sector rotation, macro dashboard) at hero
weight rather than sliver weight.

---

## §6 Held concepts — written, not recommended for flight 1

- **C `receipt` — the graded-winners belt** (CNMD +22.3%, JXN +13.7% …, the landing's
  own delayed-winners strip). Highest raw CTR potential on fintwit — receipts are the
  native currency — but it *must* carry the survivorship disclosure ("selected because
  they worked; the live board includes wins and losses") verbatim, which eats a third
  of the canvas; performance-adjacent creative also invites X finance-ad friction and
  recruits return-chasers who churn on the first flat week. Revisit only as a
  retargeting unit with the disclosure designed in from the start, operator-gated.
- **D `torch` — "light up what you can't see"** (literal dark→light canvas split).
  The operator's own metaphor, and it's good — but on a canvas it is poetry-first,
  proof-second, and the 3-second stranger gets atmosphere instead of an answer. The
  line's home is **post copy** (V2 below), where words are cheap; on the canvas,
  pixels are too expensive for metaphor. This is a placement ruling, not a kill.

---

## §7 The post copy — three variants (the ad above the ad)

X mechanics that govern these: the first line must work standing alone (feed truncation);
the image dominates the card; a website-card creative makes the whole image the link, so
the post text's job is *priming*, not navigation. No hashtags (they date the ad and leak
taps); one CTA; the domain appears once.

### V1 — "The hook is the offer" (pairs with Ad A · flight-1 primary)

> Institutional-grade stock signals — 50% off at launch.
>
> Our engines scan the entire market and grade every standout stock: buy, wait or
> avoid, with an exact entry zone. Updated every trading day — you open the app, the
> work is already done.
>
> · Daily graded stock signals
> · Sector rotation in four plain-word lanes
> · Macro dashboards + advanced charting
> · Mastermind AI — your personal analyst
> · What institutions are buying + live options flow
>
> Founding rate: $75/mo (was $149), locked in for as long as you stay.
> Start your 7-day free trial → mastermind-x.com

*Why:* line 1 = category + discount in eight words (rulings 1–2: the 50% is the hook,
freshness is "daily," not "nightly"). "You open the app, the work is already done" is
the pain answered in plain words. Feature bullets are the operator's requested list
with zero jargon; "live" appears only on options flow, where it is true.

### V2 — "The visibility problem" (pairs with either · storytelling, cold audiences)

> Most retail investors don't have a discipline problem. They have a visibility problem.
>
> The patterns are there — in the money flows, the sector moves, the setups forming
> before the breakout. Institutions pay $24,000 a year for desks that surface them.
> Retail gets a news feed.
>
> So we built the desk: daily graded stock signals with exact entry zones, sector
> rotation in plain words, macro dashboards, advanced charting, and an AI analyst that
> reads it all with you. Our job is simple — light up what you can't see.
>
> 50% off at launch · 7-day free trial → mastermind-x.com

*Why:* empathy-first for cold audiences; diagnosis before product. The $24k comparative
does the "institutional" work with a passported number. The operator's "shed light on
what is dark" lives here, where it costs nothing and lands hard.

### V3 — "The launch" (pairs with Ad A · retargeting/warm audiences)

> Launch offer: 50% off the full desk — and the rate is locked in for as long as you
> stay.
>
> Daily stock signals. Sector rotation. Macro dashboards. Advanced charting.
> Mastermind AI. Live options flow.
>
> 2,000 founding memberships, first come, first served. When they're gone, the price
> goes up.
>
> Try Pro free for 7 days → mastermind-x.com

*Why:* pure offer + scarcity for people who already know us (site visitors, engagers).
Availability-framed scarcity only ("first come first served / price goes up"), never
"claimed" counts — founding-allotment law.

---

## §8 Flight plan

- **Formats:** 1200×628 website card first (whole image clickable — the click-optimized
  unit); 1080×1080 promoted-image as the secondary placement. No 4:5 for X (that's the
  Meta master; build it only when a Meta flight is commissioned).
- **Destination:** `https://mastermind-x.com` with
  `utm_source=x&utm_medium=paid&utm_campaign=r3_flagship&utm_content=<concept>-<variant>`.
  The landing already carries the Prophet section, pricing, and the trial CTA the ad
  promises — message match is why the destination is the landing, not the app signup.
- **Arms:** exactly two — **A×V1 vs B×V1** (creative axis, copy constant). Post-text
  tests (V1 vs V3) come *after* a creative winner, against warm audiences. One axis
  per flight; the allocator and the n-floor (100/arm) do the rest.
- **Gates unchanged:** operator review of rendered PNGs at placement size →
  `ad_review.record(...)` → arena; paid spend stays behind G-A's three arms.
- **Old assets:** round-2 renders and the codex campaign sets stay in the repo as
  corpus but are **superseded for flighting** by this brief; nothing from them enrolls
  without its own approval.

## §9 Gate self-check (AG-1…AG-8, at brief level)

| Gate | A "THE CALL" | B "THE ROTATION DESK" |
|---|---|---|
| AG-1 standalone | brand+category top, product proof hero, pain headline, offer, CTA | same |
| AG-2 dimensions | 1200×628 + 1080×1080, renderer-verified | same |
| AG-3 legibility | headline ~100px, subline 40px+, chips 27px+, checked at 25% | lane names sized as copy |
| AG-4 one company | landing tokens, Inter only, real widget idioms | same, porcelain face |
| AG-5 claims | all rows in §3; SBUX demo-tagged; no usage claims | 34 themes, lanes, demo set |
| AG-6 offer | consolidated per R3.1 §7 (operator override: no scarcity micro on canvas) | same |
| AG-7 human gate | this brief → mockups → operator PNG review | same |
| AG-8 honesty | micro line removed by operator order (R3.1 §8) — zones stay demo-tagged | same |

**Paper amendments shipped with this brief:** §6 passport table refreshed to the live
pricing surface (SAVE $888/$288 rows replacing the stale SAVE $408 anchor; "up to 50%
off" platform row; Prophet vocabulary; 2,700+ dossiers), and §5 gains an explicit ban
on institutional-*usage* claims ("used by quant firms").

## §10 Next session (the mockup round) — exact steps

1. Read this brief + paper §9 corpus (no re-reading archaeology needed — §1 is the
   summary).
2. Build `mockups/refs/ad_central/round3/`: `_ads.css` reused, `call--1200x628.html`,
   `call--1080x1080.html`, `desk-rotation--1200x628.html`,
   `desk-rotation--1080x1080.html`, `render.py` port, review `index.html`.
3. Self-audit each PNG against the four recurring defect classes (bottom clip,
   auto-wrap headline, non-atomic occlusion, offer overflow) — by *looking*, the
   renderer can't see them.
4. PR with all four PNGs inline at placement size + this brief linked; operator
   verdicts via `ad_review.record(...)`; approvals → enroll, rejections → §9 corpus.
