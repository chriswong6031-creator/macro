# The Ad Master Paper — how MastermindX ads are made

**Owner:** studio (creative) × operator (taste gate) · **Created:** 2026-07-28 (round 2)
**Companion docs:** `research/AD_CENTRAL_MASTERPLAN.md` (testing spine), `research/AD_CENTRAL_HANDOFF.md`
(gates H-1…H-6), `docs/DESIGN_DOCTRINE.md` (content law). Assets this paper governs:
`mockups/refs/ad_central/round2/`.

This paper exists because round 1 (6 ads, 2026-07-27) was **rejected as a set**, and two
follow-up sessions failed the same way. The operator's specifics (2026-07-28): the ads were
*incomplete* — sections of a website, not standalone units — and *wrongly sized* — too small
for mobile feeds. Every rule below is a rejection reason turned into law.

---

## §0 ACCEPTANCE GATES — an ad is not done unless every gate is green

**AG-1 — Standalone completeness (the 3-second stranger test).** An ad is seen for ~3
seconds by someone who has never heard of us, at phone scale, with no surrounding page.
In one glance it must answer: **who this is** (brand mark + category line), **what I get**
(feature proof in the illustration), **why it matters to me** (headline aimed at a real
pain), **why now** (offer + scarcity), **what to do** (CTA). A beautiful fragment that
answers three of five is a website section, not an ad — round 1's exact failure.

**AG-2 — Real placement dimensions.** Ship only at the canvases in §4.1
(1080×1080, 1080×1350, 1200×628 logical; PNG exports at those exact pixel sizes).
Dimensions are verified programmatically by the renderer, not by eye. A 540–720px
"card" is a mockup, not a creative.

**AG-3 — Mobile legibility floor.** On a 1080-wide canvas: headline ≥ 84px (a locked phrase that cannot break into ≤19-character lines takes a third line rather than a smaller size; 76px is the absolute floor), subline ≥ 40px,
feature chips ≥ 27px, offer text ≥ 30px, micro-footer ≥ 22px. Verify at 25% zoom — that is
feed scale. If any load-bearing text needs squinting at 25%, it fails.

**AG-4 — One company.** Ads use the landing's own tokens (§4.2), the landing's typeface law
(Inter / system bold — the operator explicitly rejected decorative faces), and the product's
own widget idioms redrawn at ad scale. No stock art, no foreign gradients, no invented UI.
An approved ad and the site must look like the same hand.

**AG-5 — Claims substantiated.** Every number traces to a shipping surface (§6). Banned:
"hundreds of data points" (unsubstantiated — 34 context keys), competitor names
(debrand law), the word "validated" (CI-enforced), performance promises, invented
signals presented as live reads. Illustration data reuses the landing's own demo
dataset (already public, marked `demo`) or real graded calls — never fresh inventions.

**AG-6 — Offer block complete and truthful.** Every ad carries: **7-day free trial** +
**Founding 50% off — $75/mo** (vs the $149/mo monthly rate; billed $900/yr) + scarcity
line **availability-framed** ("2,000 founding memberships · the allotment shrinks daily"),
never "claimed/signed up" (founding-allotment law). No hardcoded live counts that rot
(no "1,754 left" in a static creative).

**AG-7 — The human gate.** No ad enters an arena, a paid plane, or a public feed without
the operator's approval recorded via `engine/marketing/ad_review.py`. This paper never
overrides H-1…H-6. Rejections get specific reasons; the reasons feed §9.

**AG-8 — Honest voice survives advertising.** Stance language over hype ("watch, don't
chase" is on-brand; "guaranteed winners" is a firing offense). Any ad whose **copy or hero
element quotes actionable levels** (entry zones, stops — e.g. entry, ai-no) carries the
micro-line "Research tools — not investment advice." in place of the "allotment shrinks
daily" clause; a demo-tagged ZONE inside a background widget sliver does not trigger it.
The product's honesty is a selling point, not a liability to hide.

---

## §1 What an ad is (the completeness law)

An ad is a **complete argument compressed into one glance**, structured as three reads:

1. **First read (0.5s): the headline.** Usually the only thing read. It must work alone.
2. **Second read (1s): the picture.** The illustration is *proof*, not decoration — real
   product widgets showing the thing the headline promised.
3. **Third read (1.5s): the deal.** Offer bar: trial, founding price, scarcity, CTA, domain.

The reader who stops after read one should still know what we are (category line sits at
the top with the brand). The reader who reaches read three should have zero unanswered
questions blocking a tap.

**The anti-section rule:** if an ad would look at home embedded mid-page on the landing,
it is not an ad. Ads carry their own context; sections borrow the page's.

## §2 Audience and pain map

US/global retail active investors and swing traders, prosumer tier — people who already
pay for one or more tools and still feel behind. Each pain maps to a desk that answers it:

| Pain (their words) | Desk that answers | Ad concepts |
|---|---|---|
| "I'm always late — I see the move after it happened" | Theme rotation lanes, Prophet stages | rotation, signals |
| "I buy falling knives / chase tops" | Stage engine (Base→Turn→Ready→Trend), entry zones | knife, entry |
| "I don't know when the whole tape is risky" | Market risk score + regime read | risk, read |
| "Funds and insiders know things I can't see" | 13F flows, insider & Congress tape | filings |
| "Options flow is invisible to me" | Intraday flow desk | flow |
| "Research takes my whole evening" | Nightly rebuild + Mastermind AI | read, ai-no |
| "Pro tools cost $20k+ and I'm priced out" | The whole desk at $75/mo founding | price, desk, founding |
| "Charting apps are toys or cost extra" | Terminal, free forever | terminal |

## §3 Message architecture

**Headline classes** (choose one per ad; never blend two):
- **Category claim** (traditional, unsaturated-market play): says plainly what we are.
  "Your personal market intelligence desk." Works because almost nobody else says it.
- **Pain flip** (creative): names the reader's scar, then the fix is the illustration.
  "Don't be the one catching the knife."
- **Feature proof**: one desk, made vivid. "Follow the filings, not the feed."
- **Price anchor**: the value arbitrage. "A $24,000 desk. Yours for $2.50 a day."
- **Honesty signature**: the differentiator no competitor will copy.
  "Finally, an AI that says 'not yet.'"

**Rules:** ≤ 9 words hard cap, ≤ 7 preferred. Plain verbs, no jargon, no internal vocab
(doctrine Law 2 applies to ads). Esoteric is allowed only if the picture resolves it
within the same glance. Subline ≤ 18 words, adds the mechanism ("how"), never repeats
the headline. Feature chips are 1–3 words each, 3–6 chips, drawn from: Stock signals ·
Risk score · Theme rotation · 13F & insiders · Options flow · AI analyst · Free terminal ·
Nightly rebuild. Chip rows are either ONE full row or TWO balanced rows (3+3, or the
founding 2×2) — never a widow chip alone on row 2 (round-2 review law, 2026-07-28).

**Offer bar (standard, every ad):** `7-DAY FREE TRIAL` · `FOUNDING · 50% OFF — $75/mo` ·
CTA pill `Try Pro free` · micro: `2,000 founding memberships · allotment shrinks daily ·
mastermind-x.com`. Offer-focused ads may add `$900/yr locked in for as long as you stay`.
CTA verbs: *Try Pro free* / *Open the desk* / *See today's read*. Never "Submit",
"Learn more", or "Sign up".

## §4 Visual system

### §4.1 Canvases (the only sizes that exist)

| Canvas | Aspect | Placements | Notes |
|---|---|---|---|
| **1080×1350** | 4:5 | Meta/IG feed (mobile-native max) | design master; most room |
| **1080×1080** | 1:1 | X feed + promoted, Meta, universal | required on every concept |
| **1200×628** | 1.91:1 | X website card, link ads | landscape adaptation, flagship concepts |

Design at logical size; export PNG at ≥1× exactly (renderer verifies). X minimums
(800×800 / 800×418) are exceeded by construction. Stories (1080×1920) derive from the
4:5 master by extending the plate — not built by default.

### §4.2 Palette (landing tokens, verbatim — no new colors)

Paper mode (default): bg `#f7f8fa`, panel `#ffffff`, hairlines `#eaecf0`/`#dfe3e9`,
ink `#1c2430`, soft `#34404f`, muted `#5d6b7e`, faint `#8a95a4`.
Accents: blue `#285fff` (CTA, links; ink `#1c47cc`, wash `#eef2ff`), green `#1f8b41`
(+wash `#e9f5ec`), red `#c12f2f` (+wash `#faeceb`), gold `#b07d05` (+wash `#faf3e2`),
violet `#7862e0` (founding/pricing only), teal `#0f9d8f` (sparingly).
Dark plate mode: `#0b1120` ground, panels `#111a2e`-ish derived, same accent hues.
Gradient allowance: the hero's blue→violet→teal text gradient on **at most one word or
one short payoff phrase (≤4 words, one per ad)** — e.g. price's "Yours: $2.50 a day."
(amended 2026-07-28); the founding card's violet wash; the faded-candle plate (§4.5).
Nothing else.

### §4.3 Type (Inter only — operator's ruling)

Inter 800/900 for headlines (−0.02em tracking), 600/700 for chrome and chips, 500 for
sublines, tabular numerals for figures. Uppercase kickers at +0.08em tracking. On a
1080-wide canvas: headline 84–120px, subline 40–48px, kicker 28–30px, chips 27–30px,
offer 30–38px, micro 22–24px. ZH variants (when built): same scale, PingFang SC stack
behind Inter, 红涨绿跌 directional colors flip.

### §4.4 The signature: dealt scorecards

The brand's one memorable visual is the landing's "neural cover" — real product cards
dealt across porcelain. Ads recompose it: **hero widget front and large** (the desk the
ad is about), 1–3 supporting cards fanned behind at ±2–5° rotation, 24–48px offsets,
`--sh-lift`/`--sh-deep` shadows, faces from the widget library (§4.6). The fan shows
breadth while the hero makes the point. Cards are redrawn at ad scale (bigger type than
the site), never screenshots.

### §4.5 The dark plate + faded candle field

For terminal/flow/entry concepts: ground `#0b1120`; behind the content sits a candle
field (SVG candlesticks, green/red at 10–16% opacity) with a radial/linear mask fading
to nothing toward the text zones. Candles echo the terminal's real chart idiom (wicks,
MA ribbon optional). The field whispers "live market" without fighting the copy —
built once in `_ads.css` (`.candle-field`), reused, never re-improvised.

### §4.6 Widget library (redrawn product surfaces)

`prophet-card` (NEAR chip, sparkline, EDGE score, Base/Turn/Ready/Trend dots, ZONE band,
date) · `gauge-card` (arc dial, score, regime chip, stance line) · `lanes-board` (BUY NOW /
ALMOST READY / TAKE PROFITS / STAND ASIDE chips) · `flows-13f` (fund rows with signed bars)
· `insider-tape` (BUY/SELL rows with roles) · `options-tape` (sweep/block rows, dark) ·
`mm-chat` (user bubble, "reading the boards" status, answer + receipt bubbles) ·
`terminal-frame` (browser chrome + candles + watchlist, dark) · `founding-card` (price
strike, meter, save badge) · `read-card` (regime chip + dial + stance). Data inside them
is the landing's demo set (VCTR 83 / ENOV 75 / IVZ 90, XLE 74, gauge 57 Mixed / 68 Risk-on,
NVDA 199–203/191, Appaloosa/Coatue/Millennium rows) — public, consistent, defensible;
specific-signal widgets keep the site's small `demo` as-of tag.

## §5 Copy law

- Word budgets are hard: headline ≤ 9, subline ≤ 18, chips ≤ 3, stance lines verbatim
  from the product where possible ("watch, don't chase").
- Banned: `validated` (CI), competitor proper nouns, "hundreds of …" without a source,
  "signed up/claimed" for founding counts, guaranteed/riskless/perfect-return framing,
  internal state names (IGNITION, UPTURN_CONFIRMED …), untranslated stats on the glance
  layer (an EDGE number may appear inside a widget — never in a headline), and
  institutional-**usage** claims — "used by quant firms / trusted by institutions" is an
  adoption claim no surface can back (round-3 ruling, 2026-08-02); the compliant form is
  the comparative ("institutions pay $24,000 a year for desks like this").
- Numbers in copy only when §6 backs them. Rot-resistant phrasing preferred ("2,000
  founding memberships" is stable; "1,754 left" is not).
- Voice: confident, plain, a little dry. The product says "windows, not certainties" —
  ads never promise what the product refuses to.

## §6 Claim passports (source of truth for every figure)

| Claim in ads | Source surface |
|---|---|
| "7-day free trial" / "Try Pro free for 7 days" | landing pricing CTAs (`templates/index.html`) |
| "Founding 50% off — $75/mo" | pricing: `data-annual="$75"` vs `data-monthly="$149"` |
| "Billed $900 a year" / "locked in for as long as you stay" | pricing founding terms |
| "2,000 founding memberships · allotment shrinks daily" | pricing founding block (enforced, #3856) |
| "SAVE $888 A YEAR" (Pro) | landing founding badge as of 2026-08-02 — $149/mo monthly ×12 = $1,788 vs $900 annual (supersedes the retired "SAVE $408" $109-anchor badge) |
| "SAVE $288 A YEAR" (Essential) | landing Essential badge — $99/mo monthly ×12 = $1,188 vs $900 annual |
| "Launch offer: up to 50% off" | platform-level: Pro $149→$75 = 49.7%; Essential $99→$75 = 24% — "up to" is load-bearing |
| Buy · Near · Wait · Hold · Avoid / 0–100 edge / four-stage lifecycle / exact entry zones | landing Prophet section (`#f-prophet`) |
| "2,700+ stock dossiers" | landing pricing matrix, dossiers row |
| "356 tracked funds" (13F) | landing Smart Money section |
| "34 themes, four lanes" | landing Theme Rotations section |
| "Terminal free forever / nothing to install" | landing Terminal section |
| "Rebuilt nightly" | nightly pipeline; landing "rebuilt nightly" as-of tags |
| "Insider & Congress trades as filings land" | landing Insider & Congress section |
| "$24,000 a year" institutional desks | public list prices of major institutional terminals (~$22–27k/yr), debranded |
| "$2.50 a day" | $900/yr ÷ 365 = $2.47, rounded **up** |
| NVDA entry 199–203 / stop 191, "gate shut since Jul 14" | landing Mastermind demo exchange |

Adding a new number to an ad = adding a row here first. If a row cannot be written,
the number does not ship (the "hundreds of data points" lesson).

## §7 Concept registry (round 2)

| slug | class | headline | mode | sizes |
|---|---|---|---|---|
| desk | category | Your personal market intelligence desk. | paper | 1350·1080·628 |
| signals | category/feature | Institutional-grade stock signals. | paper | 1350·1080·628 |
| price | price anchor | A $24,000 desk. Yours for $2.50 a day. | paper+violet | 1350·1080 |
| risk | pain flip | Know when the market has your back. | paper | 1350·1080 |
| rotation | pain flip | See the rotation before your watchlist does. | paper | 1350·1080 |
| knife | pain flip | Don't be the one catching the knife. | paper | 1350·1080 |
| entry | pain flip | Time the entry. Keep the stop. | dark | 1350·1080 |
| ai-no | honesty signature | Finally — an AI that says "not yet." | paper | 1350·1080·628 |
| filings | feature proof | Follow the filings, not the feed. | paper | 1350·1080 |
| flow | feature proof | See the size hit the tape. | dark | 1350·1080 |
| terminal | feature/free | A real terminal, in your browser. Free. | dark | 1350·1080·628 |
| founding | offer | Founding rate: 50% off, locked in. | paper+violet | 1350·1080·628 |
| read | ritual | Wake up to a market already read. | paper | 1350·1080 |

Full copy blocks (subline, chips, illustration recipe) live beside the sources in
`mockups/refs/ad_central/round2/SPECS.md`.

## §8 Process (for every future ad session)

1. **Read the taste corpus first**: `ad_review.taste_notes(root='.')` + §9 here. Re-proposing
   a rejected shape means the system has not learned.
2. Concept → §7-style registry row → copy locked against §5/§6 **before** any pixel.
3. Build in `mockups/refs/ad_central/round2/` (or the round's dir): shared `_ads.css`,
   one HTML per concept×size, `render.py` to export + verify PNGs.
4. Self-audit against §0. Then a fresh-eyes review pass (checklist = the gates).
5. Show the operator **rendered PNGs at placement size** in a gallery + PR body. Record
   the verdict via `ad_review.record(...)` — approvals unlock arenas, rejections demand
   reasons which append to §9.
6. Only after approval: enroll via `ad_creative.build(...)` (claims get passports,
   over-limit copy refuses) → arena per the masterplan. Paid spend stays behind G-A.

## §9 Taste corpus (rejections → law; append, never delete)

- **R1 (2026-07-27, set of 6):** "not robust enough to be considered for live split
  testing." Specifics (operator, 2026-07-28): (a) ads were partial page-sections —
  no standalone identity/offer/context → AG-1; (b) wrong dimensions, too small for
  mobile → AG-2/AG-3. Also from the R1 postmortem: invented AVGO signal in the
  illustration (→ AG-5), unbacked "eight terminals" comparison (→ §6), feature
  inventory without outcome framing (→ §2 pain-first).
- **Standing operator taste:** plain bold system type, no decorative faces (2026-07-26
  font ruling); "beautiful illustration and design" reusing the site's own elements;
  name concrete desks, not uncountable abstractions.
- **R2 reviewer sweep (2026-07-28, independent Opus pass before the operator gate):** 13
  confirmed findings, all resolved same-day. The one blocker is the lesson: **a struck
  price and a savings badge must be computable against the same anchor** — the founding
  card paired was-$149 (monthly anchor) with SAVE $408 (annual-anchor math). Cards now
  mirror the landing's $109 annual anchor; offer bars alone carry the $149→$75 monthly
  50%-off. Also: an illustration must not contradict its own copy (knife's "five weeks"
  vs 26 rendered days; entry's stop line drawn above 10 candle lows it called the swing
  low) — the chart is a claim. Occlusion re-lands: ghost trails never under the solid
  chip, slivers carry identity atoms only (tk, stages) with nm/zone dropped rather than
  amputated.
- **R2 internal review (2026-07-28, caught before the operator saw them)** — the four
  defect classes that recur, now checked on every file: (a) **bottom clip** — vertical
  budget blown, offer/micro cut (risk 4:5, rotation 4:5, founding 628); (b) **auto-wrap
  headline** — a locked phrase left to wrap chooses ugly breaks; always explicit `<br>`,
  three clean lines beat a smaller size (risk 4:5); (c) **non-atomic occlusion** — a
  half-covered chip/pill reads as a floating blob (rotation's +5.4% pill); (d) **offer
  overflow** — long cell text pushes the CTA off-canvas (terminal 4:5; fix the cell, not
  the CTA). The renderer catches none of these — only looking at the PNG does.
