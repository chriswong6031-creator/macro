# W2 mockup gate — Portfolio Intelligence workspace

Artifact for the W2 mockup gate of the Watchlist + Portfolio CEO revamp
(`research/MASTERMIND_WATCHLIST_PORTFOLIO_W0_COMMISSIONING_PACKET_2026-08-12.md` §5/§12,
CEO handoff §14–§17). **Not production code.** The commissioning session reviews the crops
and pins this as the exact design for the W2 builder.

- Mockup: `workspace.html` — self-contained, opens standalone.
  Harness: `?state=anon-empty|anon-analyzed|portfolio|watchlists|chips`, `&theme=light`,
  `&lang=zh`, `&bare=1` (hides the harness bar; all crops are `bare`).
- Crops: `crops/` — 5 states × {desktop dark EN, desktop light EN, desktop ZH, 390 dark EN,
  390 dark ZH} = 25 PNGs at 2× device scale, full-page (viewports 1440×900 and 390×844).
  The harness is byte-deterministic **except** for the `05_savechip` set: the `Saving…` chip's
  `chippulse` dot animation is sampled at whatever phase the shot lands on, so those five re-render
  with ~248 differing pixels every time. Re-shoot them only when state (e) actually changes.

---

## 1. The signature: **the Book Seam**

One signature, spent deliberately. It is the **BOOK READ card treatment**, not the attention
stack — and the attention stack was the runner-up, rejected for a specific reason (§1.3).

**What it is.** Under the book read's plain-language sentence sit two hairline rails of equal
width, one segment per position, same order:

```
        ┌──────────── 75% of the money ─────────────┐
MONEY  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░▨▨]     ← every position
                                    ┆▒▒▒▒▒┆          ← the overhang
RISK   [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░◌ ]      ← modeled risk only
        └───────────── 85% of the risk ─────────────┘
```

Top rail = each position's share of the **money**. Bottom rail = its share of the **modeled
risk**. A bracket over each rail names the dominant cluster's share; a dashed guide drops from
the money edge and a faint wash covers the ground the risk bracket takes but the money bracket
does not. The difference between the two bracket widths *is* the finding.

**Why this and not a KPI tile row.** The frontend-design skill names "a big number with a small
label, supporting stats, and a gradient accent" as the template answer, and the CEO handoff §16
explicitly asks for less "pile of unrelated cards". The single truest thing a portfolio engine
can tell someone — and the thing their brokerage app cannot — is that **the sizes they chose are
not the risks they took**. That deserves the page's one memorable device. The book read is
therefore a *sentence* at 30px with the computed figures set heavier and in tabular mono
("These **12** positions move like about **3** bets."), and the seam is the sentence's evidence.

**The honesty is the design — the part I'd defend hardest.** A position the risk model does not
cover (IBIT here) is hatched on the money rail — it is real money — and drawn as an **empty
outline** on the risk rail, and it is excluded from the risk denominator. The coverage
disclosure the doctrine requires in words is *also* rendered as a shape. The compliant thing
and the beautiful thing are the same object, which is why the device survives review pressure
in a way a decorative graphic would not.

**Direction-neutral by construction.** The seam paints only from `--link` and `--muted`, never
from `--up`/`--down`. Under `html[data-lang="zh"]` the direction pair swaps (红涨绿跌) and the
seam is untouched — correct, because it encodes *composition*, not direction.

### 1.1 It is not the count ladder, and does not borrow it

The count ladder is reserved to the Board archetype (P0 packet §330 anti-sameness contract).
Four properties keep these distinct:

| | Count ladder (Board) | Book Seam (this page) |
|---|---|---|
| Cell meaning | a **stage enum** category | one **individual position** |
| Arithmetic law | integer cells summing to the page's canonical total | two continuous **100% distributions** |
| Interaction | cells **are** the filter control | read-only; hover names the position |
| Claim | "how many setups exist" | "money and risk are split differently" |

Neither holdings table borrows ladder geometry either — no cell strip, no counted filter row.

### 1.2 What I *did* adopt from the P0 packet (system law, not archetype device)

**Stage is encoded by weight, never by hue** (P0 §0, binding all pages): Early = dashed outline ·
Confirming = half-filled · Confirmed = solid strong ink · Losing steam = solid muted · Running
hot = solid muted **overshooting its own end cap** · Broke down = hollow, struck · Not covered =
dotted, dimmed. This survives the zh direction flip and never collides with the `--up`/`--down`
inks. **Violet stays lock-only** (`.mx-tier-gate--prophet`, `#7c5cff`) — it appears in exactly
two places, both meaning *locked*.

### 1.3 Why not the attention stack

"What needs attention" is content-identical to Archetype A's `.chg-row` (name · change clause ·
stance verb · chevron) on `start.html`. Making it *this* page's signature would collide with A
head-on. So it **composes** that grammar rather than reinventing it, and stays visually quiet.

---

## 2. Primitives composed, and where each came from

No new token system, no new header family, no new card grammar.

| Composed | Source | Use here |
|---|---|---|
| Full token set (`--bg/--panel/--panel2/--text/--muted/--line`, `--up/--down`, `--warn/--act/--ok`, `--link/--info`, glass + `gbtn` sets, `--ink-*` rungs) | `templates/theme.css` — copied **verbatim**, values unchanged | every colour on the page |
| `.mx-tier-gate` / `--prophet` / `-copy` / `-eyebrow` / `-mark` / `-actions` / `-primary` / `-signin` | `templates/tier_preview.css` — copied verbatim | the anonymous save gate |
| `.gbtn` + `-sm` + `-cta` recipe | `theme.css` gbtn block | every button |
| `.pos` / `.neg` → `--ink-up` / `--ink-down` | `theme.css` | since-entry figures only |
| `.l-en` / `.l-zh` dual emit + `html[data-lang="zh"]` CJK stack | `theme.css:337-347` | all bilingual copy |
| `data-tip-en` / `data-tip-zh` (LENS contract) | `theme.css:1615` | every Tier-2 receipt (197 tips) |
| aurora `body::before`, both themes | `theme.css` | page backdrop |
| `.chg-row` grammar (name · clause · stance · chevron) | P0 packet Archetype A | the attention stack |
| `.tbl-filter` search field styling | `theme.css:894` | table filters |

**Institutionalize PR-0 is not on `origin/main`** (verified: no type ramp, no `.empty-why`, no
stage field in `theme.css` at `e0ed5f89b9a`). Per packet §11 I therefore composed what exists and
minted **no parallel primitives**: the type ramp is page-local literals, and the empty-state
explanation is a plain `.empty-why`-shaped paragraph, not a claimed shared class. Every
page-local class is `ws-`/`bk-`/`seam-`/`att-`/`rc-` prefixed so PR-0 can land without collision.

**Type.** `--font-ui` (Inter) for all words. `--font-mono` + `tabular-nums` **only on figures** —
and the ZH event dates deliberately drop `.fig`, because "8月27日" contains *words* and mono
numerals are for figures, never words. Page ramp: 30 / 21 / 17 / 15 / 13 / 12.5 / 11 / 10.

**Palette decision.** One accent — `--link` (`#7aa7e0` dark / `#285fff` light) — carries every
interactive affordance *and* the seam's cluster fill. Direction inks are reserved to figures;
`--warn` is reserved to attention severity; violet is reserved to locks. Four reserved meanings,
no fifth hue introduced.

---

## 3. Responsive strategy for the dense table at 390px

Verified at 390×844: **all rows present, all visible, `scrollWidth - clientWidth = 0`, zero
console errors** — 55/55 watchlist, 12/12 holdings, 8/8 anonymous.

Not `overflow-x` on the table. Below 720px each `<tr>` becomes a **CSS grid of named areas** —
semantic `<table>` markup is preserved, only `display` changes — and the header row is visually
hidden (kept for assistive tech). Two deliberate demotions, chosen so the row still answers the
job it exists for:

**Holdings (3 lines):**
```
"sym  val  exp"     SYMBOL + company            value + weight    ⌄
"sig  att  exp"     stage mark + word           attention flag
"meta meta exp"     next event
```
Demoted into the row drawer: **Day**, **Since entry**, **Risk share**.

**Watchlist (3 lines) — a different template, on purpose:**
```
"sym  val  exp"     SYMBOL + company            last price        ⌄
"sig  att  exp"     stage mark + word           risk flag
"meta chg  exp"     next event                  Δ since last visit
```
Demoted: **Sector/theme**. **Δ-since-visit is deliberately NOT demoted** — the list header
promises "4 changed since your last visit", so dropping the column that shows *which four*
would break the page's own contract at exactly the width where scanning is hardest. This is why
the two tables have different mobile templates rather than one shared reduction.

**Δ column, both widths:** unchanged rows render **blank**, not `—`. Only the four changed names
carry ink, and the header count disambiguates blank-as-"nothing happened" from missing data.

---

## 4. Honest-data handling (what is deliberately absent)

- **Day column** — the quotes Worker is dormant, so every Day cell is `—` with a Tier-2 cue
  ("Live day change is not wired up yet… everything else on this row is from last night's
  close"). Never a stale or synthesised number.
- **Anonymous Since-entry** — a pasted list has no cost basis, so it is `—` with a cue, not
  `0.0%`. (An earlier draft printed `0.0%` in green across all eight rows; that was a fabricated
  figure and was removed.)
- **Anonymous Value column** — collapses to weight only. No money is invented from a name list.
- **Mode-switch counts** — driven by state. An anonymous visitor has no saved lists, so the
  counts are **absent**, never borrowed from the signed-in mock.
- **Anonymous Signal column** — `.mx-tier-gate` lock shells, not blur. Board-tier stage reads
  are simply not delivered, so nothing to blur; the cell says what unlocks them.
- **Risk-share bars** — one shared scale (full bar = 30% of book risk), printed once in the
  Risk Center, with the number beside every bar as the truth.
- **Market books** — zero-position books render disabled with `—`, and the strip carries the
  never-mix-currencies law as its trailing subline in the holdings toolbar (§7d).

---

## 5. Doctrine tensions hit

1. **The brief's theme mechanism is inverted relative to the codebase — I followed the
   codebase.** The spawn brief says "dark is keyed on `:root[data-theme="dark"]`". It is not.
   `templates/theme.css:252-260` documents the opposite at length: dark is the **bare `:root`
   plane** and light overrides via `html[data-theme="light"]`, because the pre-paint head script
   sets no attribute at all for a first-time visitor, so a `[data-theme="dark"]` rule matches
   nothing on the live site — while still measuring green in any harness that sets the attribute
   explicitly. The mockup keys dark on bare `:root`. **The W2 builder must do the same**, and the
   brief's line should be corrected before it is copied into another spawn prompt. Restated as a
   binding rule, with the selectors, in §7a.

2. **Market books sat after the thing they filter (packet §5 order) — RESOLVED, ruled into the
   toolbar.** The ruled IA listed MARKET BOOKS last in Portfolio mode, but a filter placed below
   its table is a usability defect. The first pass did not redesign the ruled structure; it left
   the chips in the ruled position and raised the IA amendment rather than taking it as a builder
   decision. **The commissioning session ruled the amendment in:** the strip is now the second
   line of the holdings toolbar, the standalone bottom section is gone, and Watchlists mode stays
   books-free. The disclosure line ("Showing **all 12** · all books") stays exactly where it was
   and keeps its packet §11 job — curing the silently-shortening persisted book filter. Full
   semantics in §7d.

3. **Stance vocabulary vs. the no-imperatives rule — RESOLVED, ruled as standing.** The doctrine's
   ratified stance set includes "Act" and "Protect gains", which read close to trade instructions
   on a page showing someone's actual money. I used only the safely descriptive subset —
   **Watch · Get ready · No action** — plus a plain "Nothing here needs a decision today." for the
   book read (Law 1 is satisfied even when the honest answer is *nothing*). The commissioning
   session ratified this as the rule for portfolio surfaces, not a one-page preference: §7b.

4. **Stage names as plain words.** Early sign / Confirming / Confirmed / Losing steam / Running
   hot / Broke down are PR-0's user-facing stage lexicon, used here as plain English with a
   two-character ZH twin (初现 / 确认中 / 已确认 / 转弱 / 过热 / 已失效). If PR-0 lands a
   different lexicon, the builder adopts PR-0's — these are not competing names.

5. **The Concentration tab was duplicating the seam's claim.** First draft had both saying
   "seven tech names, 75% of money, 85% of risk". One dominant idea per section, no duplicate
   content: the seam keeps the **cluster** claim, the tab now carries the **single-name** claim
   ("One name, NVDA, carries a quarter of this book's risk on a sixth of its money").

## 6. ZH copy notes

Written as Chinese product copy, not translated English. Notable choices:
**组合透视** for "Portfolio Intelligence" (透视 = see-through/x-ray, which is what the page does)
over the literal 投资组合情报; **持仓** / **自选股** for the two modes — 自选股 is *the* term
every Chinese brokerage uses for a watchlist; "12 只持仓，实际只相当于大约 3 个方向。" leads with
the count and uses 方向 (directions/bets), the natural Chinese framing, rather than calquing
"move like". Placeholders use a `data-ph-en`/`data-ph-zh` pair set at paint and on language
change — an attribute cannot hold the dual-emit spans, which is the same reason translated copy
never goes in `title=`. **Zero `title=` attributes on the page** (verified across all 5 states ×
2 languages), and zero banned glance-tier vocabulary.

Two later additions, same rule — Chinese product copy, not translated English:

- The book-strip label is **分市场** ("by market"), not a calque of "books". EN keeps the
  product's own noun (*Books* — the page says "this book" throughout); ZH takes the label every
  Chinese brokerage would use for the same control. The two are not literal twins on purpose.
- The entry-price footnote ends **不会进入我们的信号计算** ("does not enter our signal
  computation") rather than a literal rendering of "never feeds our signals" — 进入…计算 is how
  a Chinese product says a value is excluded from a model.

---

## 7. Builder inheritance — rulings the W2 build must carry

Four decisions that are settled, not open. None of them changes a pixel in these crops; they are
here so the next session inherits them instead of re-deriving them.

### (a) Theme mechanism — dark is the bare plane

`:root` **is** the dark theme. Light is the override:

```css
:root                     { /* dark — a first-time visitor has NO data-theme at all */ }
html[data-theme="light"]  { /* light — wins on specificity 0,1,1 vs 0,1,0        */ }
```

**`html[data-theme="dark"]` selectors ship DEAD on this codebase.** The pre-paint head script
sets no attribute for a first-time visitor, so such a rule matches nothing on the live site —
while still measuring green in any harness that sets the attribute explicitly, which is exactly
why the defect survives review. `templates/theme.css:252-260` documents this at length. Key dark
on bare `:root`; see §5.1.

### (b) Stance vocabulary — portfolio surfaces are descriptive only

Portfolio surfaces use **Watch · Get ready · No action**, plus a plain "Nothing here needs a
decision today." when the honest answer is *nothing*.

**"Act" and "Protect gains" are barred from holdings surfaces.** Both sit in the doctrine's
ratified stance set (Law 1) and both stay legal on other surfaces — but on a page showing
someone's actual positions they read as trade instructions rather than descriptions of state.
Doctrine Law 1 is fully satisfied by the descriptive subset: every row still answers "so what do
I do", including when the answer is "nothing". See §5.3.

### (c) The 390px holdings column set

Below 720px each `<tr>` becomes a CSS grid of named areas — semantic `<table>` markup preserved,
only `display` changes (§3). The split is not a build-time judgement call; it is this list.

**Rendered inline at 390** — three lines, `"sym val exp" / "sig att exp" / "meta meta exp"`:

| Area | Cell | Carries |
|---|---|---|
| `sym` | `.c-sym` | SYMBOL + company name |
| `val` | `.c-val` | position value + weight % |
| `sig` | `.c-sig` | stage mark + plain stage word |
| `att` | `.c-att` | attention flag |
| `meta` | `.c-evt` | next event |
| `exp` | `.c-exp` | row-drawer toggle (spans all three lines) |

**Demoted to the row drawer at 390** — `display:none` in the row, reachable only by opening it:

| Cell | Column | Why demoting it is safe |
|---|---|---|
| `.c-day` | Day | every cell is `—` while the quotes Worker is dormant (§4) |
| `.c-since` | Since entry | a check-in figure, not a scan figure |
| `.c-rc` | Risk share | the Risk Center one screen down is entirely about this |

The watchlist uses a **different** mobile template on purpose (`"meta chg exp"`), because
Δ-since-visit has to survive the reduction — the list header promises "4 changed since your last
visit". Reasoning in §3.

### (d) Book-chip semantics

Pinned by the commissioning session, verbatim:

> The book chips filter the HOLDINGS TABLE VIEW only; BOOK READ, the attention stack, and the
> Risk Center always describe the WHOLE portfolio; when a book is active the disclosure line
> reads "Showing 11 of 12 — United States book"; the sentence "Each book totals in its own
> currency. We never add two currencies into one number." survives as the strip's
> subline/tooltip.

As built: the strip is the **second line of the holdings toolbar** — one `.tbl-bar` control block,
`.tbl-top` above and `.tbl-books` below, with a single hairline under both, so a filter never
reads as its own section. The label's hover carries the views-not-portfolios rule; the currency
law is the strip's trailing subline, pushed right by `margin-left:auto` in the same grammar
`.tbl-foot` already uses, and dropping to its own line below 1080px.

`.tbl-scope` is the disclosure line and it is load-bearing, not decoration: it is what stops a
persisted book filter from silently shortening the list (packet §11). At 390 the chips scroll
**inside `.books-strip`** — the same `overflow-x:auto` + hidden-scrollbar technique `.rc-tabs`
already uses on this page — so the page itself never scrolls sideways (verified 0px).

**Watchlists mode has no books**, by rule. `.tbl-bar` scopes the border removal, so the
watchlist's own `.tbl-top` is untouched — verified bit-identical across all five watchlist crops.

---

### (e) What the W2 build changed, and why — folded in from the implementation record

The four rulings above were written before the build. These are the decisions the build
itself had to make, folded here from `crops/impl/IMPLEMENTATION_DELTAS.md` §2 now that
this file is on `main` (the fold was deferred to whichever wave landed after the mockup
gate; W3 is that wave). They are part of the pinned record — a later builder inherits
them rather than re-deriving them.

**D1 — Watchlists mode gains an add-a-name field.** The pinned mockup is a static
artifact, so it shows no control for adding a name; the real page must have one. A
`.srch`-styled input sits in `.wl-head` after the list picker, with the existing
suggestion dropdown. No new grammar — it is the same `.srch` the toolbar filter uses.

**D2 — Scenario Lab shipped as a labelled shell.** The pinned mockup writes out the
lab's copy; the packet scoped the pre-trade check to a later wave. The `<details>` row
was present in the pinned position with its pinned summary line, and its body said what
it would do and that it landed next wave, rather than presenting a control that did
nothing. *(Superseded by W3, which gave it its real body — see (g).)*

**D3 — Risk Center: Concentration was live, the other five tabs were labelled shells.**
Per the W2 scope. Each shell stated the one question its tab would answer, in plain
words, plus "Being built — this tab lands in the next wave". No fake panels.
*(Superseded by W3 — see (g).)*

**D4 — The regime read moved from a rail to the book read's subline.** The pinned design
gives BOOK READ a `sec-sub` ("Quiet tape · nothing crossed a line overnight"); the
pre-existing `#wri_rail` was a separate tinted strip. The rail's own state tint was
dropped with it: the subline is quiet muted text, and a state ramp there would introduce
a fifth reserved hue on a page whose palette decision allows four.

**D5 — The condition-count line is retired, not ported.** It answered "how much of the
book is this summary about"; the pinned design answers the same question better with the
attention stack's "5 of 12 positions" section header. Two sentences answering one
question, one line apart, was the defect.

**D6 — Coverage disclosure splits into two sentences on a multi-market book.** The seam
can only draw ONE currency (the page's own toolbar states that law), so when the book
spans markets the rails describe the LEAD book and the line says which: "The two lines
above read your US stocks book — 12 of 15 positions." The uncovered count is then over
exactly the set the rails drew. The pinned single-market mockup had no occasion for this.

**D7 — The engine-state → plain-word stage map is a build decision the mockup did not
specify.** The mockup names the seven stage words; the engine emits nine states plus a
`LIMITED` sentinel. The map is fixed, lives in `templates/watchlist.js`, and only ever
de-escalates: `BOTTOM WATCH` (a downtrend near a low) becomes *Broke down*, not *Early
sign*; `COUNTERTREND BOUNCE` (an unconfirmed turn) becomes *Early sign*, not
*Confirming*; anything unknown becomes *Not covered*. Pinned by
`tests/test_watchlist_workspace_js.py`.

**D8 — The anonymous headline uses weight and market concentration, not sector.** The
A9 ruling allows "via public metadata, else weight-only concentration". A name's sector
is only on this page via the gated `stockdata/index.json`, so the build takes the stated
fallback. Recorded in full in packet §14 A9.

**D9 — The pinned "Sort: Value" toolbar button is absent; sorting moved to the column
headers.** The mockup shows a `Sort: Value` button beside "Add position". The built table
has sortable column headers instead (`aria-sort`, click to toggle) — the same affordance
in the place a reader already looks for it, and it sorts by any column rather than
cycling one. The button would have been a second control for a subset of what the headers
already do. If the commissioning session wants the pinned control back, it is additive.

**D10 — The anonymous entry panel persists above the analysis; the mockup replaced it.**
In the pinned state (b) the paste box is gone once the book is read. Built, it collapses
to a compact single-line header plus the textarea and the weighting control, and stays.
Reason: the weighting mode is the visitor's most likely SECOND action ("what if these are
percentages?"), and re-deriving the whole read is one click from there. Removing the panel
would mean re-entering the book to change one control. Recorded as a deliberate departure,
not an oversight — the commissioning session may rule it back.

### (f) Rulings the W2 build absorbed, including its own residual

Folded from `crops/impl/IMPLEMENTATION_DELTAS.md` §3 and §3a. The round-2 rulings below
are binding on later waves in the same way (a)–(d) are.

- **§7(a)–(d) as built** — dark keyed on bare `:root` with no `[data-theme="dark"]`
  selector anywhere in `watchlist.html.j2`; the stance set held to Watch · Get ready ·
  No action plus "Nothing here needs a decision today."; the 390 column set demoted Day,
  Since entry, Risk share and Sector to the drawer while the watchlist kept its own
  template so Δ-since-visit survives; book chips filter the holdings table view only.
- **§1 the signature** — one Book Seam, drawn in one function (`WS.seam` in
  `watchlist.js`), fed by both the anonymous and the signed-in path. No second renderer
  exists, which is why a row's risk share and the seam's rail cannot disagree.
- **§4 honest data** — Day is always "—" with its Tier-2 cue; anonymous Since-entry is
  "—" with a cue rather than a fabricated 0.0%; the anonymous Value column collapses to
  weight; mode-switch counts are absent for a visitor with nothing saved.
- **§6 ZH** — zero `title=` attributes in the workspace markup; placeholders use the
  `data-ph-en`/`data-ph-zh` pair; ZH dates drop `.fig` because they contain words.

**Round-2 rulings absorbed (binding):**

- **zh stage word for `BOTTOM WATCH`** (supersedes D7's zh half). EN *Broke down* stands.
  The zh word is **已破位** (describes the break), not **已失效** (declares the read
  invalid): 已失效 is an engine-verdict word, and a display tier may only ever
  de-escalate.
- **Δ-since-visit down marker.** The marker and the *aging* stage word both rendered
  **转弱**, making a movement marker and a stage read indistinguishable in Chinese. The
  marker is **转跌** ("turned down", matching its EN); the stage keeps 转弱.
- **The seam is capped at 24 segments with a disclosed tail.** One segment per position
  overflowed the PAGE at 100 names on 390px (measured 86px). The rail draws the 23
  largest and folds the rest into one labelled segment; both denominators and both
  brackets are still computed over ALL positions, so capping moves pixels and never
  arithmetic. **A later surface reusing the seam inherits that separation and must not
  re-derive math over the capped view.**
- **Share counts never speak as money.** Anonymously there is no price plane, so Shares
  mode carries a `unit` through every derived figure — headline, because-line, seam
  label, bracket, segment tooltips, the Weight column header and the coverage line all
  say *share count* — and one line states that turning share counts into position sizes
  needs prices, which arrive with the free account.
- **Non-directional uses of `--down` were repainted to `--act`.** The remove-hover, the
  modal error line and the failure toast painted from the DIRECTION token, so under
  红涨绿跌 an error message turned GREEN. Health tokens do not swap, which is exactly why
  they exist. **Severity and error surfaces use `--act` and must not flip.**

**W2's own recorded residual, carried forward unchanged.** During the render-lag window —
and only during it — the legacy card grid renders **without the Risk Desk role badge**
(the `EXIT REVIEW` / `TAKE-PROFIT REVIEW` chips and the per-lane chips beside them). The
cause is `decorateCards`/`paintLanes`, which lived in the braid block W2 deleted and are
not part of the restored `lg*` path; the lane ENGINE survives untouched (`roleBadge`,
`laneRead`, `laneRows` are all still exported and still feed the workspace drawer).
Accepted rather than restored: the window closes the moment the render lane bakes
`site/watchlist.html`, after which the legacy path is never taken again, and the badge is
not part of the design that replaces it.

### (g) W3 — the Risk Center's six tabs (supersedes D2 and D3)

W3 replaced the five labelled shells and the Scenario Lab shell with real reads over the
engines that already existed. No estimator changed. The rulings a later wave inherits:

- **One dominant idea per tab, and no tab repeats another's claim.** The seam owns the
  cluster claim; Concentration owns the single-name claim; **Weak links owns risk PER
  DOLLAR** — the money-vs-risk ratio — which is why it is not a second concentration
  ranking. Pinned by a test that asserts all six claim sentences are distinct.
- **The tabs are computed in ONE pass and published, never recomputed per tab.**
  `watchlist_risk.js` builds all six strings from the same two RiskCore reads and hands
  them to `watchlist.js` to paint, the same split the seam uses. Two tabs cannot describe
  different books.
- **A tab with nothing to say says what it would say, and why it cannot.** The "being
  built" shells became thin-book fallbacks: the tab's own question in plain words plus
  "Add at least two positions the nightly model covers and this fills in." A tab never
  shows an empty panel and never borrows another tab's answer.
- **"No twins" is a finding, not an empty state.** On an orthogonalized model with real
  per-name idio vol, most equity pairs sit well below the 0.70 line — so Correlation
  prints the closest pair and its number anyway. Saying only "no pair crosses 0.70" would
  read as "these names are unrelated", which is false.
- **The falling-days lens reports BOTH directions.** A book can tighten under stress and
  it can also spread. Both counts print under the bars whichever way the comparison came
  out, so an ordinary result never looks like a missing read.
- **`factorBets`' diagonal-only approximation is disclosed where the grouping is shown.**
  The per-name dominant factor is argmax of `b²·F_kk` — the diagonal of F only — so the
  force a name is filed under can differ from the book-level ranking for the same ticker.
  The Factors tab carries that sentence in plain words. Fixing the approximation is a math
  change and stays out of a presentation wave; disclosing it does not.
- **Ladder geometry is reused, never re-invented.** The pair, event and money-vs-risk rows
  are the Concentration ladder with a different left column — same track, same shared-scale
  law, read-only. None of them is the Board's count ladder: no cell is a category, no cell
  is a filter control, every track is a continuous share.
- **Two bars in one row share ONE scale.** Weak links first normalised money and risk
  independently, so the name with the largest money drew a full bar, the name with the
  largest risk drew a full bar, and the row the headline was about drew neither — the
  picture contradicted its own sentence. On a shared scale the finding is what you see.
- **Tier-2 receipts ride the sentence, not a `?` glyph.** `.wri-q` belonged to the braid
  hero W2 deleted and is styled nowhere on this page, so it rendered as a bare question
  mark. The page's own pattern is `data-tip-en`/`data-tip-zh` on the element carrying the
  copy, wired to the LENS popover by `theme.js`. Technical quantities (a net beta, a
  variance share) live there and never at glance tier.
- **The Scenario Lab states its default size.** `W4_DEFAULT_DOLLARS = 10000` is kept and
  explained in the copy under the form: a round number that makes two runs comparable, not
  drawn from the reader's book and not a suggested size. WRI-R3 is unchanged — no
  optimizer, no recommended sizing, no imperatives; an unmodeled candidate gets an honest
  null rather than invented figures.

**Round-2 rulings absorbed into (g), binding on later waves:**

- **A semantic class is not a spare visual channel.** `is-ballast` means "this position
  offsets the book". Borrowing it to mark one of two LENSES changed what it means AND
  broke the picture — its fill fails contrast against the track, so the larger of the
  two bars read as an empty one. If two rows need distinguishing, distinguish them with
  their labels, not by reaching for a class that already carries a meaning.
- **A shared scale needs headroom.** A bar pinned at 100% with no unfilled tail cannot be
  read as a proportion. Ladders round their scale up (to the next 5%) and print it.
- **Never branch display copy on a compound engine flag.** `RiskCore.read().diverges` is
  an OR over two unrelated findings (the book collapses; a pair becomes a twin only under
  stress). Branching one sentence on the OR let one finding print the other's words. Use
  the specific predicate, and give each finding its own sentence.
- **Every tab that reads the factor model carries the SAME two disclosures** — the
  unmodeled names and the market coverage — including the DEFAULT tab. Non-US names are
  stripped before RiskCore sees them, so they never appear in `coverage.unmodeled`; only
  the market sentence discloses them, and a tab without it is silently describing a
  subset of someone's book.
- **A surface may only name what it renders.** If the copy points at a ticker, that
  ticker's row is on screen — or the copy picks a different one.
- **zh singular/plural pronouns are a real distinction** (它 / 它们), not an English
  artifact to be ignored.
- **Fix the dead class in the file you are already editing.** Deferring a three-line CSS
  fix to a later wave while editing the exact template it lands in costs more than taking
  it, and ships a known defect in the meantime.

---

### (h) W4 — the per-ticker Intelligence Drawer

W4 composed the drawer out of artifacts that already exist: no estimator changed, no
engine was added, and — the property that decides whether a 100-name list survives it —
no fetch was added. Every field it reads comes out of the same `stockdata/<T>.json` the
row already hydrated for its own cells, so opening a drawer is string concatenation over
an object the page is holding anyway. The rulings a later wave inherits:

- **Honest absence is a MECHANISM, not a habit.** Every section builder returns a ROW,
  never `''`, and the row names WHAT is missing ("no options plane for this name
  tonight") rather than saying nothing. A section that renders nothing and a section
  with nothing to report are the same pixels, and only one of them is information.
  `tests/test_watchlist_drawer_js.py` runs every builder over an EMPTY payload and reds
  if any returns a blank, so the next person to add a section cannot quietly skip theirs.
- **And the gate is TWO-SIDED, or it certifies its own failure.** Because every section
  degrades honestly, a drawer composed over no artifacts renders thirteen well-worded
  rows all saying "not covered" — a screenshot indistinguishable from a working drawer
  on a quiet name. The wave's success criterion and its total failure look identical.
  So the crop harness asserts a rich name renders almost NO absent rows and a sparse one
  renders SOME BUT NOT ALL. **Any later gate over an honest-degradation surface needs
  both halves**; the "it degrades honestly" half alone is satisfied by having no data.
- **A surface may only name what it renders — including what it MEASURED.** The CEO's
  Tier-2 list asks for USD, oil, China and BTC/Gold sensitivity, and for retail flow and
  Congress trades. No per-name artifact carries any of them, so the drawer does not
  mention them and each row's tip states the set that WAS measured. Naming an exposure
  we did not measure is the failure this rule exists to prevent.
- **A LANE reports a state; a SECTION may report the mechanism behind it.** The `rates`
  lane says "not very rate-sensitive"; Macro sensitivity says "rate risk runs through
  its market / growth beta, not a distinct duration leg". Those are different claims and
  may sit together. Two rows repeating one claim may not — the §7(g) no-duplicate-claim
  rule is about the CLAIM, not the topic.
- **Two escaping rules, because the two slots are different languages.** The row
  painter's `en`/`zh` slots are MARKUP and stay caller-escaped (callers interpolate
  `<span class="fig">`). The `tip` slots are ATTRIBUTE TEXT and are escaped BY THE
  PAINTER. "Callers escape" is a fine rule where a mistake prints a stray tag; it is the
  wrong rule where a mistake breaks OUT of `data-tip-en="…"` and turns the rest of the
  row into attributes — a failure with no visible symptom, in the slot nobody looks at.
- **An engine string written as an instruction is not display copy.**
  `entry_signal.action` reads "take a half position here, or wait for the weekly to
  turn". Holdings surfaces are descriptive only, so Tier 1 reads `headline`. Check any
  new engine field for the imperative voice before surfacing it.
- **A route that 200s is not a route that works.** `stock.html?t=<T>` shipped for a
  wave: a real page, a real 200, an empty dossier, and nothing a link checker can see
  (`stock.html` reads `location.hash`, plus `?ticker=` via a boot shim). Canonical links
  are verified against the TARGET'S OWN READER, and the accepted parameter set is pinned
  by a test so a change there fails loudly.
- **A hide that was never verified is not a hide.** The W2/W3 crop harnesses hide the
  chat launcher with four selectors, none of which it carries — the widget is
  `#mmb-launch`, and that rule has been a no-op in every crop those harnesses took. W4's
  harness derives the id from the rendered page and then asserts the computed style went
  to `none`. **Any harness that suppresses something for a screenshot must prove the
  suppression worked**, or the crop silently documents whatever it failed to hide.
- **The stance vocabulary is ONE vocabulary in two files.** §7(b)'s Watch · Get ready ·
  No action lives in `portfolio.js` (which runs signed-out) and in `watchlist_risk.js`
  (which never does), so neither can import the other. A test asserts the two literal
  sets are byte-equal rather than trusting them to stay in step. The event carve-out is
  part of the precedence: an earnings date inside five days raises the events lane to
  `elev`, but that is something to BE READY for, not something wrong — the same way the
  book-level attention stack files it.
**Round-2 rulings absorbed into (h), binding on later waves:**

- **An engine field written in the trading voice is not display copy, and it is not an
  edge case.** `entry_signal.headline` carries an imperative on **66.6%** of the library;
  `alerts.pinned` on **80.2%** of the names that have one. Any engine string reaching a
  user surface needs a TOTAL de-imperative map keyed on the engine's own **enum**, not on
  the text — a text key silently falls through to passthrough the day someone fixes a
  typo upstream — and its fallback must be derived from other fields, never the string
  itself. A map with a passthrough fallback is not a map.
- **A severity mark that fires on most rows is not a mark, it is the background.** Check
  the DISTRIBUTION of any state token before shipping it: Watch measured 93.5%, ownership
  `watch` 92.8%. And when a mark needs re-deriving, look first for an instrument that is
  ALREADY graded — `roleBadge` had three rungs and an `if (role)` was flattening them —
  rather than inventing a threshold.
- **One topic, one severity owner.** If a lane already reports severity on a subject, a
  section about the same subject reports FACTS and no state. Two severity claims about
  one topic dilute each other and neither can be trusted.
- **A staleness guard on the chip is not a staleness guard on the read.** A past
  `earnings.next_date` was correctly kept out of the countdown chip and still rendered
  "reports <date>" in a confident `ok` — on 1,197 of 1,205 names. Guard the state and the
  sentence, not just the decoration.
- **A harness must not write into committed evidence before it has judged it.** Shoot to
  a temp dir, assert, promote on success. A failing run must leave the committed crops
  untouched, and a module-scope `main()` means even `--help` overwrites them.
- **A gate that checks a control EXISTS has not checked the control.** The chevron that
  rendered, rotated and opened nothing would pass any existence check. Operate it.
- **Choose an evidence artifact by MEASURING, and refuse stub-grade inputs.** The
  "degraded name" crop was shot over a 1,354-byte stub against a 59,273-byte median, and
  the crop could not show it — an honest-degradation scene and a no-data scene are the
  same picture. Size AND field presence, asserted before the browser starts.
- **A guard must be able to tell a rule from its explanation.** Three tests in this wave
  failed on their own comments (`stock.html?t=`, `title=`, the gain-protection phrase).
  Match the EMIT shape, not the prose.
- **A SKIP is not a PASS.** A node-shelled suite with node absent exits 0 having proved
  nothing. On CI, absent tooling is a failure.
- **Derive the set a coverage test iterates.** A hand-written class list covers exactly
  what its author thought of, which is how `.wri-rail-chain` sat unstyled from #3527.
- **Never latch a wave boundary into a test.** Hardcoding `?v=7` reds the NEXT legitimate
  bump; assert monotonicity against `origin/main` so the check retires itself on merge.

- **A one-name factor group is a FINDING, not a label.** `clusterLabel` returns
  `members[0]` for a group of one, so passing its label through printed "filed under
  AAPL" inside AAPL's own drawer. Carry the facts (which force, how many names) and word
  them at the surface: "moves on its own — nothing else here is grouped with it".
